#!/usr/bin/env python3
"""public_value_scan.py -- data-service-api public-repository value scanner.

Machine-checkable enforcement of docs/security/public-repository-policy.md.
Scans tracked files (or an explicit file list, as passed by pre-commit) for
value shapes that must never appear in this public repository: real
hostnames/FQDNs, e-mail addresses, cloud project identifiers, credential_id
locators, IAM principals/service accounts, working-machine absolute paths,
and common secret-key shapes.

Standard library only. No external dependency (see design
docs/design/PHASE7_EVIDENCE_REPRODUCIBILITY_AND_PUBLICATION_V1.md D-2: an
existing secret scanner such as gitleaks/trufflehog was rejected because
this tool targets *operational identifiers*, not generic secrets, and must
not pull an external repository into the pre-commit hook).

Rules implemented: R1 (e-mail), R2_url (scheme URL), R2_fqdn (bare FQDN),
R3 (GCP project id / project number), R4 (credential_id locator shape),
R5 (IAM principal / service account), R6 (working-machine absolute path),
R8 (common secret-key shapes: PEM / AKIA / ghp_ / xox / AIza).

R7 (personal names) is OUT OF SCOPE and NOT IMPLEMENTED: personal names are
not expressible as a reliable regex (see design Appendix A.4). This is a
"not checked" gap, not a "zero found" result -- do not read a clean R7-less
run as evidence that no personal name is present. Human review is
responsible for R7.

Common exclusion (placeholder substrings): a matched token is re-evaluated
after removing every placeholder substring it contains -- `<UPPER_SNAKE>`
and `REPLACE_ME_*` -- and only flagged if what remains still matches the
rule. A placeholder merely *prefixed* onto a real value does not hide it,
because the real value's own characters survive the substring removal and
are still tested (see design D-2, "part of the token, not the whole
token").

Output line format (never the raw matched value):
    <path>:<line> | <RULE> | <first3>...<length>

Exit code: 0 if no rule flags anything, 1 otherwise.

Known gaps (recorded per docs/work-orders/OPERATING_CONDITIONS.md 1.12-71:
a gap that cannot let a contract violation or a Security Invariant breach
through the completion gate is recorded here and not filed in the ledger):
    1. not detected: a deny-suffix host that sits INSIDE another URL's
       query string.
       why: `R2_URL_RE` matches a URL greedily up to whitespace or a
       delimiter, so a nested `https://...` inside a query string is
       part of ONE match and only the outer host is ever classified
       against the allow/deny sets.
       caught by: ledger R-46 (OPEN, not accepted): fix before the
       public flip; until then human review of URLs in query strings.
    2. not detected: personal names (R7) -- see the R7 paragraph above.
       why: same paragraph (not expressible as a reliable regex).
       caught by: human review, as that paragraph states.
    3. not detected: a bare FQDN whose TLD is outside `R2_FQDN_TLDS`
       (com/net/org/jp/io/cloud/info/biz), and any value shape no rule
       describes at all.
       why: the TLD set is deliberately narrow (design Appendix A.1: a
       broad set reproduced attribute-chain false positives such as
       `self.dev`), and the scanner is a fixed rule list (see "Rules
       implemented" above).
       caught by: human review before publication, against
       `docs/security/public-repository-policy.md` (accepted).
    4. not detected: a real value in a file this tool is handed by a
       bare, worktree-relative path while it runs from a different
       checkout of the tool itself.
       why: a relative path resolves against `REPO_ROOT` (this script's
       OWN location, `Path(__file__).resolve().parent.parent`), not
       against the tree under review -- a main checkout's copy of this
       tool given a worktree-relative path silently scans the unmodified
       main-checkout file instead.
       caught by: passing the worktree's own absolute path whenever the
       file under review lives only in a worktree (accepted; no floor or
       cross-checkout resolution is implemented).
    5. over-detected, not under-detected: `R3_project_id` cannot tell a
       `pt.py`/`mutate.py` log filename (`mutate-YYYYMMDD-NNNNNN`/
       `pt-YYYYMMDD-NNNNNN`) from a real GCP project id/number.
       why: the trailing `-NNNNNN` (6 digits) satisfies
       `R3_PROJECT_ID_RE` exactly like a real suffix would; the rule
       carries no log-filename exception.
       caught by: the reporting convention of not writing a `pt.py`/
       `mutate.py` log filename into a tracked document; human review
       for the rare document that does (a log-name reference is not
       itself a public-value violation).
"""
from __future__ import annotations

import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Common exclusion: placeholder substrings (docs/security/public-repository-
# policy.md "placeholder convention" / design D-1 (ii), D-2).
# ---------------------------------------------------------------------------
PLACEHOLDER_RE = re.compile(r"<[A-Z0-9_]+>|REPLACE_ME[A-Z0-9_]*")

# Illustrative ellipsis used by *this repository's own documents* (D-1 (i)'s
# table and D-2's rule table, and the phase 7 work order that quotes them)
# to describe the SHAPE of a forbidden absolute path without writing a real
# one, e.g. "`/Users/…`" / "`/home/…`" / "`C:\\Users\\…`". These are not
# placeholder tokens (they don't match PLACEHOLDER_RE) so they need their
# own, narrow exclusion. Only a match that is *exactly* prefix + ellipsis
# (nothing else) is excluded -- a real path that happens to be followed by
# an ellipsis elsewhere in the line is unaffected because the match itself
# would contain more than the prefix.
_ELLIPSIS_CHARS = ("\u2026", "...")


def _is_illustrative_ellipsis(matched: str, prefix: str) -> bool:
    rest = matched[len(prefix):]
    return rest in _ELLIPSIS_CHARS


def strip_placeholders(token: str) -> str:
    return PLACEHOLDER_RE.sub("", token)


def _strip_placeholders_with_cuts(line: str) -> tuple[str, list[int]]:
    """Remove placeholder substrings from `line`, returning the residual
    string together with the RESIDUAL-STRING positions where a removal
    happened (WP-1 rework item 1 / audit finding H-A).

    Each entry in `cuts` is a zero-width position in the OUTPUT string --
    the point where the two pieces of literal text on either side of an
    excised placeholder were spliced together. A rule match found in the
    residual string is judged `placeholder_removed` only when one of these
    cut points falls at or inside THAT match's own span (see
    `_span_touches_cut` and `scan_line` below) -- not merely because some
    placeholder was removed somewhere else on the same line. This makes
    the exclusion per-token/span, matching design D-2's wording ("トークン
    から placeholder 部分文字列を除去した残りに対して各規則を再適用す
    る"), and closes the line-wide reading that let a `<UPPER_SNAKE>`
    placeholder anywhere on a line license an unrelated real value
    elsewhere on that same line.
    """
    out_parts: list[str] = []
    cuts: list[int] = []
    pos = 0
    out_len = 0
    for m in PLACEHOLDER_RE.finditer(line):
        piece = line[pos:m.start()]
        out_parts.append(piece)
        out_len += len(piece)
        cuts.append(out_len)
        pos = m.end()
    out_parts.append(line[pos:])
    return "".join(out_parts), cuts


def _span_touches_cut(cuts: list[int], start: int, end: int) -> bool:
    return any(start <= c <= end for c in cuts)


def mask(s: str) -> str:
    s = s.strip()
    if len(s) <= 3:
        return f"{s}...{len(s)}"
    return f"{s[:3]}...{len(s)}"


# ---------------------------------------------------------------------------
# Shared domain-level helpers, used by R1 / R2_url / R2_fqdn / R5.
#
# (a) Structurally-invalid-DNS / bare-generic-suffix artifacts. Common
#     exclusion (placeholder substring removal) is judged per matched
#     token/span (WP-1 rework item 1 / H-A), not over the whole line: a
#     match's `placeholder_removed` is true only when a placeholder was
#     actually removed at or touching THAT match's own span (see
#     `_span_touches_cut`), so a placeholder elsewhere on the same line
#     does not license an unrelated real value. When a placeholder sits
#     immediately adjacent to a dot on both sides of the SAME host, the
#     match collapses into a double-dot / leading-dot / doubled-hyphen
#     shape (e.g. "mitatedb-data-<GCP_PROJECT_NUMBER>.<REGION>.run.app"
#     residualizes to "mitatedb-data-..run.app", and the host match's own
#     span covers both removed placeholders). None of these shapes is a
#     resolvable real DNS name (a label cannot be empty), so treating them
#     as "still hits the rule" would be reporting an artifact of
#     redaction, not a real value. This check does NOT touch a match that
#     is fully-formed real content with no such artifact touching its own
#     span (that is exactly what mutation 3, the placeholder-prefix-hides-
#     a-real-value case, must still catch: a real value has no doubled
#     delimiter of its own and is not merely the bare deny suffix by
#     itself -- and a placeholder positioned elsewhere on the line no
#     longer excuses it, per H-A).
# (b) A documentation-only synthetic project label ("example-project", as
#     used throughout MitateDB-api/docs/cloud-run-cloud-sql.md) -- this
#     predates the phase 7 placeholder-convention consolidation (D-1 (ii):
#     `<UPPER_SNAKE>` / `REPLACE_ME_*` / `*.example.invalid`) but is
#     unambiguously a synthetic label, not a real project id.
# ---------------------------------------------------------------------------
def _domain_has_example_label(domain: str) -> bool:
    """Narrowed per WP-1 rework item 2: only the exact first label
    `example-project` is treated as a synthetic project label (previously
    any label equal to `example` or merely *starting with* `example-`
    qualified, which let an unrelated real label such as
    `example-production` slip through as if it were the documented
    MitateDB-api/docs/cloud-run-cloud-sql.md synthetic project id)."""
    labels = domain.lower().split(".")
    return bool(labels) and labels[0] == "example-project"


def _is_malformed_or_bare_artifact(
    host: str, generic_bare_suffixes=(), placeholder_removed: bool = False
) -> bool:
    """Detect a redaction artifact left behind by placeholder-substring
    removal (design D-2 common exclusion), e.g.
    "mitatedb-data-<GCP_PROJECT_NUMBER>.<REGION>.run.app" residualizing to
    "mitatedb-data-..run.app".

    Narrowed per WP-1 rework item 3: the leading/trailing-dot-or-hyphen and
    doubled-delimiter (".." / "--") checks are artifacts of placeholder
    removal specifically, so they apply ONLY when a placeholder was
    actually removed touching the specific match's own span being tested
    (`placeholder_removed is True`; narrowed from line-wide to span-wide per
    WP-1 rework item 1 / H-A -- see `_span_touches_cut`) -- otherwise a real
    host or e-mail that legitimately contains "--" (a hyphenated label) or
    punycode ("xn--...") would be misclassified as a malformed artifact and
    silently excluded merely because some unrelated placeholder happened to
    sit elsewhere on the same line. The bare
    generic-suffix branch (`h in generic_bare_suffixes`, e.g. a lone
    "run.app" token with no other label) is NOT a placeholder-removal
    artifact -- it is inherently non-identifying on its own -- so it stays
    unconditional.
    """
    h = host.lower().rstrip(".")
    if h in generic_bare_suffixes:
        return True
    if not placeholder_removed:
        return False
    if h.startswith(".") or h.startswith("-"):
        return True
    if ".." in h or "--" in h:
        return True
    return False


# ---------------------------------------------------------------------------
# R1 -- e-mail
# Allow: example.* / *.invalid / *.test / users.noreply.github.com /
#        anthropic.com
# ---------------------------------------------------------------------------
R1_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def r1_domain_allowed(domain: str, placeholder_removed: bool = False) -> bool:
    d = domain.lower().rstrip(".")
    if d == "example" or d.startswith("example."):
        return True
    if d == "invalid" or d.endswith(".invalid"):
        return True
    if d == "test" or d.endswith(".test"):
        return True
    if d == "users.noreply.github.com" or d.endswith(".users.noreply.github.com"):
        return True
    if d == "anthropic.com" or d.endswith(".anthropic.com"):
        return True
    if _domain_has_example_label(d):
        return True
    if _is_malformed_or_bare_artifact(d, placeholder_removed=placeholder_removed):
        return True
    return False


# ---------------------------------------------------------------------------
# R2_url -- scheme URL
# Deny (always flag): *.run.app, *.cloudfunctions.net
# Allow: localhost, 127.0.0.1, metadata.google.internal (exact only,
#        R2_url only -- see R2_URL_ALLOW_HOST_EXACT), github.com,
#        pypi.org, python.org, postgresql.org, json-schema.org,
#        cloud.google.com, *.googleapis.com, official docs (sqlite.org:
#        SQLite datatype reference cited by
#        MitateDB-api/src/mitatedb_api/backend_sqlite.py)
# ---------------------------------------------------------------------------
R2_URL_RE = re.compile(r"https?://[^\s\"'`<>()\[\]{}]+", re.IGNORECASE)
# IGNORECASE here too: if this failed to match an uppercase-scheme URL
# already matched by R2_URL_RE above, host extraction would silently fail
# (host="") and the URL would never reach the host-based rules below --
# defeating the point of making R2_URL_RE itself case-insensitive (rework
# item 5).
R2_URL_HOST_RE = re.compile(r"^https?://([^/:\s]+)", re.IGNORECASE)

R2_ALLOW_HOST_EXACT = {"localhost", "127.0.0.1"}
R2_URL_ALLOW_HOST_EXACT = {
    # The GCE metadata server's fixed hostname, reached from every GCP VM
    # to fetch instance identity tokens. Used in a `http://` URL in
    # MitateDB-api/docs/f9-execution-assets-v1/f9-revision-proxy.py:22. A
    # public, documented GCP constant, not a project-specific value (the
    # audience value appended to the URL is a runtime variable, not a
    # literal). Exact match only, not a suffix: a suffix entry would also
    # allow a real subdomain of this host (e.g. a hypothetical
    # `sub.metadata.google.internal`), which is not this one specific,
    # fixed hostname. Applies to R2_url only -- the source occurrence is a
    # scheme URL, not a bare FQDN, so this entry is not read by
    # r2_fqdn_flag (a bare `metadata.google.internal` mention is outside
    # R2_fqdn's TLD-limited set regardless, see R2_FQDN_TLDS below).
    "metadata.google.internal",
}
R2_ALLOW_HOST_SUFFIXES = (
    "github.com",
    "pypi.org",
    "python.org",
    "postgresql.org",
    "json-schema.org",
    "cloud.google.com",
    "googleapis.com",
    "sqlite.org",  # official docs: MitateDB-api/src/mitatedb_api/backend_sqlite.py:30
    "gcr.io",  # official docs / public registry host, e.g. gcr.io/cloud-builders/docker
    "anthropic.com",
    # cloudfunctions.net is a deny suffix for R2_url (a *scheme* URL naming a
    # real Cloud Functions endpoint is always flagged, checked before this
    # allow-list is consulted) but is NOT part of R2_fqdn's deny set per
    # design D-2 (R2_fqdn's own denylist is run.app / gserviceaccount.com
    # only) -- a bare, scheme-less mention of the domain (as in this design
    # document's own rule-description table) is in scope for neither rule.
    "cloudfunctions.net",
)
R2_URL_DENY_HOST_SUFFIXES = ("run.app", "cloudfunctions.net")


def _host_suffix_match(host: str, suffixes) -> bool:
    h = host.lower().rstrip(".")
    for suf in suffixes:
        if h == suf or h.endswith("." + suf):
            return True
    return False


def _last_label_cannot_be_a_tld(host: str) -> bool:
    """A host whose LAST label contains a hyphen (and is not an IDN `xn--`
    label) cannot be a public internet name: no TLD contains a hyphen. Such
    tokens are fragments -- typically a synthetic URL split across two
    string literals, where the `.example.invalid` suffix sits on the next
    line (WP-9 preflight, 2026-09-06: history mode saw exactly that shape).
    Deny-suffix hosts (`*.run.app`, `*.cloudfunctions.net`,
    `*.gserviceaccount.com`) always end in a hyphen-free label, so this
    never waves a deny-suffix host through."""
    last = host.lower().rstrip(".").rsplit(".", 1)[-1]
    return "-" in last and not last.startswith("xn--")


def r2_url_flag(host: str, placeholder_removed: bool = False) -> bool:
    h = host.lower().rstrip(".")
    if _last_label_cannot_be_a_tld(h):
        return False
    # Rework item 2: the deny suffixes (run.app / cloudfunctions.net) are
    # checked before ANY GENERIC allow determination -- including the
    # ALLOW_HOST_EXACT / "." shortcut / r1_domain_allowed's malformed-
    # artifact fallback / ALLOW_HOST_SUFFIXES checks below -- so a
    # deny-suffix host can never be waved through by an allow rule that was
    # only ever meant for a different, unrelated host shape. Only the deny
    # branch's own three narrow, specifically-scoped exceptions apply here:
    # a bare generic suffix by itself, a placeholder-redaction artifact, or
    # the one pre-existing, narrowly-scoped synthetic project label
    # (`example-project`, D-2 / MitateDB-api/docs/cloud-run-cloud-sql.md) --
    # none of those is the kind of broad, unrelated allow-listing this
    # reordering is meant to stop from taking precedence over a deny suffix.
    if _host_suffix_match(h, R2_URL_DENY_HOST_SUFFIXES):
        if _domain_has_example_label(h):
            return False
        return not _is_malformed_or_bare_artifact(
            h, R2_URL_DENY_HOST_SUFFIXES, placeholder_removed
        )
    if h in R2_ALLOW_HOST_EXACT:
        return False
    if h in R2_URL_ALLOW_HOST_EXACT:
        return False
    if "." not in h:
        return False  # not a resolvable FQDN shape at all
    if r1_domain_allowed(h, placeholder_removed):
        return False  # shared placeholder-domain convention: *.invalid / *.test / example.*
    if _host_suffix_match(h, R2_ALLOW_HOST_SUFFIXES):
        return False
    if _is_malformed_or_bare_artifact(h, placeholder_removed=placeholder_removed):
        return False
    return True


# ---------------------------------------------------------------------------
# R2_fqdn -- bare FQDN. TLD-limited set (design D-2, L7-4): a broad TLD set
# reproduces short-TLD/attribute-chain false positives (`self.dev`,
# `self.app`); the set below is the one measured to reach zero true
# positives over the tracked tree (design
# docs/design/PHASE7_EVIDENCE_REPRODUCIBILITY_AND_PUBLICATION_V1.md
# Appendix A.1, re-run against the WP-1 rework as the tree scan's
# `total_flagged=0` aggregate line).
# Allow (exact only, R2_fqdn only): a corporate domain -- see
# R2_FQDN_ALLOW_HOST_EXACT below.
# ---------------------------------------------------------------------------
R2_FQDN_RE = re.compile(r"\b[a-z0-9-]+(?:\.[a-z0-9-]+)+\b", re.IGNORECASE)
R2_FQDN_TLDS = {"com", "net", "org", "jp", "io", "cloud", "info", "biz"}
R2_FQDN_DENY_SUFFIXES = ("run.app", "gserviceaccount.com")
R2_FQDN_BARE_GENERIC = {"run.app", "gserviceaccount.com", "iam.gserviceaccount.com"}
R2_FQDN_ALLOW_HOST_EXACT = {
    # Google's own corporate domain, exact match only. This is the bare
    # FQDN used as the GCR image-path namespace in the `FROM` line of
    # MitateDB-api/docs/f9-execution-assets-v1/Dockerfile:3 (Google's
    # official Cloud SDK base image). A public Google constant, not a
    # project-specific value. Exact match only, not a suffix: a suffix
    # entry would also allow any real subdomain of this host by matching
    # at the label boundary, not just this one exact hostname. Applies to
    # R2_fqdn only -- the source occurrence is a bare FQDN inside an image
    # path, not a scheme URL, so a scheme URL naming this same host is
    # still flagged by r2_url_flag (not covered by this exact-match set).
    "google.com",
}


def _is_code_attribute_chain(h: str) -> bool:
    """Narrow, measured exception (design
    docs/design/PHASE7_EVIDENCE_REPRODUCIBILITY_AND_PUBLICATION_V1.md
    Appendix A.1 / D-2, L7-4): even after
    limiting the TLD set (L7-4), a 2-label `word.info` shape still collides
    with a Python attribute-access chain (`conn.info`,
    r2db-api/src/r2db_api/postgres.py:477 -- `conn.info.transaction_status`
    truncated to its first two labels by the bare-FQDN regex). Real
    `*.info` domains in practice carry a distinguishing brand label
    (hyphens/digits); a short, pure-lowercase-identifier, hyphen-free,
    digit-free 2-label token ending in `.info` is far more likely to be
    source code than a real hostname. Scoped to `.info` only -- this is
    the one TLD in the finalized set observed to collide; it does not
    weaken run.app / gserviceaccount.com / iam.gserviceaccount.com, which
    have their own dedicated (and unconditional) deny handling above."""
    labels = h.split(".")
    if len(labels) != 2 or labels[1] != "info":
        return False
    first = labels[0]
    return bool(re.fullmatch(r"[a-z][a-z0-9_]{0,5}", first)) and "-" not in first


def r2_fqdn_flag(host: str, placeholder_removed: bool = False) -> bool:
    h = host.lower().rstrip(".")
    if _last_label_cannot_be_a_tld(h):
        return False
    # Rework item 2: deny suffixes checked before any generic allow
    # determination (see r2_url_flag above for the same reordering and its
    # three narrow, specifically-scoped exceptions).
    if _host_suffix_match(h, R2_FQDN_DENY_SUFFIXES):
        if _domain_has_example_label(h):
            return False
        return not _is_malformed_or_bare_artifact(
            h, R2_FQDN_BARE_GENERIC, placeholder_removed
        )
    if h in R2_ALLOW_HOST_EXACT:
        return False
    if h in R2_FQDN_ALLOW_HOST_EXACT:
        return False
    if r1_domain_allowed(h, placeholder_removed):
        return False  # shared placeholder-domain convention: *.invalid / *.test / example.*
    if _host_suffix_match(h, R2_ALLOW_HOST_SUFFIXES):
        return False
    if _is_code_attribute_chain(h):
        return False
    last_label = h.rsplit(".", 1)[-1]
    if last_label not in R2_FQDN_TLDS:
        return False
    return True


# ---------------------------------------------------------------------------
# R3 -- GCP project identifier. "name-NNNNNN" project id, and 12-digit
# project number. UUID / hex-token internals are out of scope (a 12-digit
# run that is part of a longer hex/UUID literal is not a project number).
# ---------------------------------------------------------------------------
R3_PROJECT_ID_RE = re.compile(r"\b[a-z][a-z0-9-]{4,28}-\d{6}\b")
R3_PROJECT_NUMBER_RE = re.compile(r"\b\d{12}\b")
_UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)
_HEXRUN_CHARS = set("0123456789abcdefABCDEF-")


def r3_number_in_hex_or_uuid_context(line: str, start: int, end: int) -> bool:
    for m in _UUID_RE.finditer(line):
        if m.start() <= start and end <= m.end():
            return True
    i, j = start, end
    while i > 0 and line[i - 1] in _HEXRUN_CHARS:
        i -= 1
    while j < len(line) and line[j] in _HEXRUN_CHARS:
        j += 1
    span = line[i:j]
    if len(span) > (end - start) and any(c in "abcdefABCDEF" for c in span):
        return True
    return False


# ---------------------------------------------------------------------------
# R4 -- credential_id locator shape. Synthetic values are allowed ONLY when
# an explicit "synthetic" annotation appears on the SAME line as the value
# or on the line immediately BEFORE it (WP-1 rework item 6, narrowing from
# whole-file granularity: a "synthetic" word anywhere in a large document
# -- e.g. one credential_id example far away in a design doc -- previously
# licensed every other credential_id-shaped token in that same file, real
# ones included).
# ---------------------------------------------------------------------------
R4_CREDENTIAL_RE = re.compile(r"\b[a-z]{2,5}_[0-9a-f]{16}\b")


def _r4_obviously_synthetic(val: str) -> bool:
    """The hex half is the ascending digit run `0123456789abcdef` or a single
    repeated character -- shapes no issued credential_id takes, used only as
    documentation examples (WP-9 preflight, 2026-09-06)."""
    hexpart = val.split("_", 1)[1]
    return hexpart == "0123456789abcdef" or len(set(hexpart)) == 1


def r4_synthetic_annotation_nearby(line: str, prev_line: str) -> bool:
    return "synthetic" in line.lower() or "synthetic" in prev_line.lower()


# ---------------------------------------------------------------------------
# R5 -- IAM principal / service account. No domain allow-list per design
# D-2 table ("--"): a real SA/principal always flags. The negative
# lookbehind on R5_IAM_PRINCIPAL_RE excludes the one structural
# false-positive shape checked in this repo -- a `scheme://user:password@`
# DSN, where the literal word "user" immediately before ":" is a
# credential-placeholder label, not the IAM `user:` principal prefix.
# ---------------------------------------------------------------------------
R5_IAM_SA_RE = re.compile(r"\b[a-z0-9-]+@[a-z0-9.-]+\.iam\.gserviceaccount\.com\b")
R5_IAM_PRINCIPAL_RE = re.compile(
    r"(?<!/)\b(?:serviceAccount|user):[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
)


def r5_sa_domain_allowed(domain: str, placeholder_removed: bool = False) -> bool:
    return _domain_has_example_label(domain) or _is_malformed_or_bare_artifact(
        domain, placeholder_removed=placeholder_removed
    )


def r5_principal_domain_allowed(email: str, placeholder_removed: bool = False) -> bool:
    domain = email.split("@", 1)[1] if "@" in email else ""
    return r1_domain_allowed(domain, placeholder_removed)


# ---------------------------------------------------------------------------
# R6 -- working-machine absolute path.
#
# Two narrow exclusions, both load-bearing only in their specific shape:
#  * "empty first segment": the identifying username segment right after
#    the prefix was entirely a placeholder (already removed by common
#    exclusion), e.g. "/home/<VPS_USER>/r2-vps/apps/r2db-api" residualizes
#    to "/home//r2-vps/apps/r2db-api" -- the redacted part is exactly the
#    part that would identify a real account; the static project-layout
#    suffix that survives is already public elsewhere in this repository
#    (CLAUDE.md: "project/r2-vps/apps/r2db-api").
#  * container account directive: a bare `/home/<name>` with no further
#    path segment, on a Dockerfile `WORKDIR`/`USER` line, names the
#    in-container service account, not a developer workstation user.
# ---------------------------------------------------------------------------
# Path-tail char class built separately from each prefix below so this
# module's own source does not contain a contiguous "/Users/<chars>" (etc.)
# run that would trip its own rule when the scanner scans itself.
_R6_TAIL = r"[^\s\"'`<>]+"
R6_USERS_RE = re.compile("/Users/" + _R6_TAIL)
R6_HOME_RE = re.compile("/home/" + _R6_TAIL)
R6_WINPATH_RE = re.compile(r"C:\\Users\\" + _R6_TAIL)


def _r6_empty_first_segment(matched: str, prefix: str) -> bool:
    rest = matched[len(prefix):]
    first_seg = rest.split("/", 1)[0]
    return first_seg == ""


def _r6_dockerfile_container_account(matched: str, prefix: str, line: str) -> bool:
    rest = matched[len(prefix):]
    if "/" in rest:
        return False
    return re.match(r"^(WORKDIR|USER)\s", line.strip()) is not None

# ---------------------------------------------------------------------------
# R8 -- common secret-key shapes (PEM / AKIA / ghp_ / xox / AIza). Deliberately
# narrow -- see design D-2 table; no generic base64/hex-run heuristic (that
# was a prototype-only exploration, not part of the confirmed rule set, and
# adding it now would be an undesigned extension, ruled out under 常設規律5).
# ---------------------------------------------------------------------------
R8_PEM_RE = re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")
R8_AKIA_RE = re.compile(r"\bAKIA[0-9A-Z]{16}\b")
R8_GHP_RE = re.compile(r"\bghp_[A-Za-z0-9]{36}\b")
R8_XOX_RE = re.compile(r"\bxox[abp]-[A-Za-z0-9-]+\b")
R8_AIZA_RE = re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")


class Scanner:
    """Stateful per-run scanner: findings + counts, plus the two exclusion
    kill-switches used only by the counter-examples (A: placeholder
    exclusion, B: absolute-path ellipsis exclusion) that prove those
    exclusions are load-bearing rather than vacuous."""

    def __init__(self, disable_placeholder_exclusion: bool = False,
                 disable_ellipsis_exclusion: bool = False):
        self.disable_placeholder_exclusion = disable_placeholder_exclusion
        self.disable_ellipsis_exclusion = disable_ellipsis_exclusion
        self.findings: list[tuple[str, int, str, str]] = []
        self.counts: Counter[str] = Counter()
        # R4 line-adjacency state (rework item 6): the previous raw line seen
        # for the CURRENT path, reset whenever the path changes so a
        # "synthetic" annotation on the last line of one file never leaks
        # into the first line of the next.
        self._r4_last_path: str | None = None
        self._r4_prev_line: str = ""

    def _residual(self, line: str) -> tuple[str, list[int]]:
        if self.disable_placeholder_exclusion:
            return line, []
        return _strip_placeholders_with_cuts(line)

    def _flag(self, path: str, lineno: int, rule: str, matched: str) -> None:
        self.counts[f"{rule}:flagged"] += 1
        self.findings.append((path, lineno, rule, mask(matched)))

    def scan_line(self, path: str, lineno: int, line: str) -> None:
        residual_line, cuts = self._residual(line)
        # WP-1 rework item 1 / H-A: `placeholder_removed` is no longer a
        # single line-wide boolean. It is computed separately for EACH
        # rule match below, from whether a placeholder was actually removed
        # at or touching that match's own span (`_span_touches_cut`) --
        # per design D-2's per-token wording. A `<UPPER_SNAKE>` placeholder
        # elsewhere on the same line no longer excuses an unrelated real
        # value's own malformed-artifact check (`cuts` is always `[]` when
        # disable_placeholder_exclusion is set, since then `_residual` is
        # the identity function and nothing was ever removed).

        if path != self._r4_last_path:
            self._r4_prev_line = ""

        # R1 email
        for m in R1_EMAIL_RE.finditer(residual_line):
            if not re.search(r'[A-Za-z0-9]', m.group(0).split('@', 1)[0]):
                # A local part made only of symbols ('+', '-', '.') is not an
                # e-mail address; it is a diff marker or punctuation glued to an
                # '@'-decorator (WP-9 preflight, 2026-09-06).
                continue
            val = m.group(0)
            self.counts["R1_email:total"] += 1
            domain = val.split("@", 1)[1]
            placeholder_removed = _span_touches_cut(cuts, m.start(), m.end())
            if r1_domain_allowed(domain, placeholder_removed):
                self.counts["R1_email:excluded"] += 1
            else:
                self._flag(path, lineno, "R1_email", val)

        # R2 url
        for m in R2_URL_RE.finditer(residual_line):
            val = m.group(0)
            self.counts["R2_url:total"] += 1
            host_m = R2_URL_HOST_RE.match(val)
            host = host_m.group(1) if host_m else ""
            placeholder_removed = _span_touches_cut(cuts, m.start(), m.end())
            if r2_url_flag(host, placeholder_removed):
                self._flag(path, lineno, "R2_url", val)
            else:
                self.counts["R2_url:excluded"] += 1

        # R2 bare fqdn
        for m in R2_FQDN_RE.finditer(residual_line):
            val = m.group(0)
            self.counts["R2_fqdn:total"] += 1
            placeholder_removed = _span_touches_cut(cuts, m.start(), m.end())
            if r2_fqdn_flag(val, placeholder_removed):
                self._flag(path, lineno, "R2_fqdn", val)
            else:
                self.counts["R2_fqdn:excluded"] += 1

        # R3 project id
        for m in R3_PROJECT_ID_RE.finditer(residual_line):
            val = m.group(0)
            self.counts["R3_project_id:total"] += 1
            self._flag(path, lineno, "R3_project_id", val)

        # R3 project number (with UUID/hex-run exclusion, checked against
        # the residual line so a placeholder-adjacent number is unaffected)
        for m in R3_PROJECT_NUMBER_RE.finditer(residual_line):
            val = m.group(0)
            self.counts["R3_project_number:total"] += 1
            if r3_number_in_hex_or_uuid_context(residual_line, m.start(), m.end()):
                self.counts["R3_project_number:excluded"] += 1
            else:
                self._flag(path, lineno, "R3_project_number", val)

        # R4 credential_id -- synthetic annotation must be on this line or
        # the immediately preceding line (rework item 6), not merely
        # anywhere in the file.
        for m in R4_CREDENTIAL_RE.finditer(residual_line):
            val = m.group(0)
            self.counts["R4_credential_id:total"] += 1
            if r4_synthetic_annotation_nearby(line, self._r4_prev_line) or _r4_obviously_synthetic(val):
                self.counts["R4_credential_id:synthetic"] += 1
            else:
                self._flag(path, lineno, "R4_credential_id", val)

        # R5 IAM
        for m in R5_IAM_SA_RE.finditer(residual_line):
            val = m.group(0)
            self.counts["R5_iam_sa:total"] += 1
            domain = val.split("@", 1)[1]
            placeholder_removed = _span_touches_cut(cuts, m.start(), m.end())
            if r5_sa_domain_allowed(domain, placeholder_removed):
                self.counts["R5_iam_sa:excluded"] += 1
            else:
                self._flag(path, lineno, "R5_iam_sa", val)
        for m in R5_IAM_PRINCIPAL_RE.finditer(residual_line):
            val = m.group(0)
            self.counts["R5_iam_principal:total"] += 1
            placeholder_removed = _span_touches_cut(cuts, m.start(), m.end())
            if r5_principal_domain_allowed(val, placeholder_removed):
                self.counts["R5_iam_principal:excluded"] += 1
            else:
                self._flag(path, lineno, "R5_iam_principal", val)

        # R6 absolute paths (ellipsis exclusion applies only to the exact
        # prefix+ellipsis illustrative shape; the placeholder exclusion
        # above already handles `<...>`/REPLACE_ME-suffixed paths since it
        # runs over residual_line before these regexes see it)
        for rule, rx, prefix in (
            ("R6_users_path", R6_USERS_RE, "/Users/"),
            ("R6_home_path", R6_HOME_RE, "/home/"),
            ("R6_winpath", R6_WINPATH_RE, "C:\\Users\\"),
        ):
            for m in rx.finditer(residual_line):
                val = m.group(0)
                self.counts[f"{rule}:total"] += 1
                if not self.disable_ellipsis_exclusion and _is_illustrative_ellipsis(val, prefix):
                    self.counts[f"{rule}:excluded"] += 1
                elif _r6_empty_first_segment(val, prefix):
                    self.counts[f"{rule}:excluded"] += 1
                elif _r6_dockerfile_container_account(val, prefix, line):
                    self.counts[f"{rule}:excluded"] += 1
                else:
                    self._flag(path, lineno, rule, val)

        # R8 secret shapes
        for rule, rx in (
            ("R8_pem", R8_PEM_RE),
            ("R8_akia", R8_AKIA_RE),
            ("R8_ghp", R8_GHP_RE),
            ("R8_xox", R8_XOX_RE),
            ("R8_aiza", R8_AIZA_RE),
        ):
            for m in rx.finditer(residual_line):
                val = m.group(0)
                self.counts[f"{rule}:total"] += 1
                self._flag(path, lineno, rule, val)

        self._r4_prev_line = line
        self._r4_last_path = path

    def scan_text(self, path: str, text: str) -> None:
        for i, line in enumerate(text.splitlines(), start=1):
            self.scan_line(path, i, line)


def get_tracked_text_files() -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-files"],
        capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    return [rel for rel in out if not rel.startswith(".venv/")]


def read_text(path: Path) -> str | None:
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if b"\x00" in data:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def scan_tree(file_list: list[str] | None, scanner: Scanner) -> int:
    rels = file_list if file_list is not None else get_tracked_text_files()
    n_scanned = 0
    for rel in rels:
        full = REPO_ROOT / rel if not Path(rel).is_absolute() else Path(rel)
        text = read_text(full)
        if text is None:
            continue
        n_scanned += 1
        scanner.scan_text(rel, text)
    return n_scanned


def scan_history(scanner: Scanner) -> tuple[int, int]:
    """`git log --all -p -m` over the whole repository. Counts only; findings
    are still masked the same way but location is best-effort (current file
    marker from the diff header + a running patch-line counter), since a
    stable path:line does not exist across the whole rewritten history.

    `-m` is required (rework item 4): plain `git log -p` shows NO diff at
    all for a merge commit, so any real value that entered history only
    through a merge commit (and not also through a non-merge commit) would
    never be scanned -- 84 of this repository's 207 commits are merges. `-m`
    makes git log show each merge commit's diff against every parent, which
    is the closest `git log` gives to "the content a merge commit actually
    carries" without hand-rolling blob enumeration."""
    proc = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "log", "--all", "-p", "-m"],
        capture_output=True, text=True, check=True,
    )
    text = proc.stdout
    current_file = "(history)"
    n_commits = 0
    n_lines = 0
    for lineno, line in enumerate(text.splitlines(), start=1):
        n_lines += 1
        if line.startswith("commit "):
            n_commits += 1
            continue
        if line.startswith("+++ b/") or line.startswith("--- a/"):
            current_file = line[6:]
            continue
        # Patch content lines carry a one-character diff marker ('+', '-' or
        # ' ') that is NOT part of the file content. Strip exactly one marker
        # before scanning: left in place, a leading '+' becomes the local
        # part of an e-mail match (a plus sign directly before an at-sign and a dotted decorator name reads as R1), which flooded
        # the history mode with false positives (WP-9 preflight, 2026-09-06).
        if line[:1] in "+- " and not (line.startswith("+++") or line.startswith("---")):
            line = line[1:]
        scanner.scan_line(f"history:{current_file}", lineno, line)
    return n_commits, n_lines


def print_report(scanner: Scanner, n_scanned: int, mode: str, count_key: str = "files_scanned") -> None:
    for path, lineno, rule, masked in scanner.findings:
        print(f"{path}:{lineno} | {rule} | {masked}")
    print(f"# mode={mode} {count_key}={n_scanned} total_flagged={len(scanner.findings)}")
    for key in sorted(scanner.counts):
        print(f"# {key} = {scanner.counts[key]}")
    print(
        "# R7 (personal names): NOT CHECKED -- not expressible as a regex; "
        "human review only. A clean run above does not mean no personal "
        "name is present."
    )


def build_arg_parser():
    import argparse

    p = argparse.ArgumentParser(
        description=(
            "Scan for real hostnames, e-mail addresses, cloud project "
            "identifiers, credential_id locators, IAM principals/service "
            "accounts, working-machine absolute paths, and common secret-key "
            "shapes that must never appear in this public repository. "
            "R7 (personal names) is intentionally NOT implemented: it is "
            "not expressible as a reliable regex, so it is left to human "
            "review rather than approximated."
        )
    )
    p.add_argument("files", nargs="*", help="specific files to scan (pre-commit passes these)")
    p.add_argument(
        "--history",
        action="store_true",
        help=(
            "scan `git log --all -p -m` (all commits, including each "
            "merge commit's diff against every parent) instead of the tree"
        ),
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    scanner = Scanner()

    if args.history:
        n_commits, n_lines = scan_history(scanner)
        print_report(scanner, n_scanned=n_commits, mode="history", count_key="commits_scanned")
        print(f"# history_patch_lines_scanned = {n_lines}")
    else:
        file_list = args.files if args.files else None
        n_scanned = scan_tree(file_list, scanner)
        print_report(scanner, n_scanned, mode="tree")

    return 1 if scanner.findings else 0


if __name__ == "__main__":
    sys.exit(main())
