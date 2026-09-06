#!/usr/bin/env python3
"""rewrite_hash_refs.py -- data-service-api commit-hash reference rewriter.

WP-9 (docs/work-orders/WORK_ORDER_PHASE7_EVIDENCE_AND_PUBLICATION_V1.md) /
design docs/design/PHASE7_EVIDENCE_REPRODUCIBILITY_AND_PUBLICATION_V1.md
D-1 (iv) (2) and Sec.9 step 2: after `git filter-repo --replace-text` rewrites
every commit in this repository's history, every commit-hash reference
*inside the tracked documents themselves* (design decisions, work orders,
the conditions register, ...) still names the OLD sha. This tool reads the
commit-map that `git filter-repo` emits (lines of "<old-sha> <new-sha>",
optionally preceded by an "old new" header line) and rewrites every hex-like
token in the target documents that uniquely front-matches an old sha to the
same-length front part of the corresponding new sha.

Standard library only. No external dependency (mirrors
tools/public_value_scan.py's convention).

Candidate token shape: a word-bounded run of 7-40 lowercase hex characters
(`\\b[0-9a-f]{7,40}\\b`) that contains AT LEAST ONE digit AND AT LEAST ONE
letter -- an all-digit run ("1234567") or all-letter run ("abcdefg") is not
hash-shaped enough to be a candidate at all and is silently skipped (not
even reported as unmatched).

Every remaining candidate is classified into exactly one of four verdicts:

  replaced   -- the token front-matches EXACTLY ONE old sha in the
                commit-map. Replaced (in --apply) with the same-length
                front part of that sha's new value.
  ambiguous  -- the token front-matches TWO OR MORE old shas. Never
                replaced (silently guessing which commit was meant would be
                wrong). Reported and, under --check/--apply, makes the run
                fail.
  unmatched  -- the token does not front-match any old sha at all.
                Reported (an unmatched token might be a rewrite gap -- a
                document referencing a commit missing from the commit-map --
                or something the allow-list should have caught).
  allowed    -- the token matched an exclusion (a built-in structural
                false-positive shape, or a user-supplied --allow /
                --allow-file entry) and was never looked up at all. Common
                false-positive shapes for a bare hex-token scan: a fragment
                of a hyphenated UUID, a fragment of a longer hex digest
                (sha256/sha512) than the regex's own 40-char cap can ever
                produce whole, and a locator-style credential_id
                (`crd-...`/`ctl-...`) whose hex suffix alone is hash-shaped.
                See DEFAULT_ALLOW_REASONS below and the WP-9 report for the
                current-tree dry-run classification that produced them.

No exit path prints a real secret: the only values this tool ever prints
are commit shas (front parts) and document tokens that already sit in
version control -- sha are not "real values" under
docs/security/public-repository-policy.md.

Modes:
  --check   list + counts only, no writes. Non-zero exit if ambiguous or
            unmatched is >0.
  --apply   writes the `replaced` substitutions. If any ambiguous token
            exists, refuses to write anything and exits non-zero (an
            ambiguous token proves the commit-map is not yet safe to apply
            unattended). unmatched tokens do not block a write -- they are
            reported, not fatal, since a well-tuned allow-list should carry
            most non-hash-reference tokens to `allowed` before this stage.
  --verify  (run AFTER --apply) re-scans the target files for any token
            that still front-matches an old sha (regardless of unique /
            ambiguous) -- i.e. a residual, un-rewritten reference. Non-zero
            exit if any residual is found (completion condition 2).
  --self-test  runs this file's own embedded test scenarios (synthetic
            commit-map + synthetic documents in a tmp dir) and exits 0/1.
            conformance-tests/ deliberately does not host a test for this
            script (WP-9 scope note), and `tools/` is not in the root
            pytest `testpaths` (see pyproject.toml) -- adding it there is
            an undesigned extension (常設規律 5), so this embedded
            self-test is the primary gate-safe verification path.
            tools/tests/test_rewrite_hash_refs.py additionally wraps the
            same scenarios as ordinary pytest tests for manual/CI-adjacent
            runs; it is never collected by the root suite.

Output line format:  <path>:<line> | <token> | <verdict>[ -> <replacement>]
Summary line:        # replaced=N ambiguous=N unmatched=N allowed=N
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Candidate token extraction
# ---------------------------------------------------------------------------
HEX_TOKEN_RE = re.compile(r"\b[0-9a-f]{7,40}\b")
_UUID_RE = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b"
)
_HEXRUN_CHARS = set("0123456789abcdef")
_CRDID_PREFIX_RE = re.compile(r"[a-z]{2,5}[-_]$")


def has_digit_and_alpha(token: str) -> bool:
    """Exclude all-digit ("1234567") and all-letter ("abcdefg") runs -- not
    hash-shaped enough to be a candidate (work order WP-9 spec)."""
    return any(c.isdigit() for c in token) and any(c.isalpha() for c in token)


# ---------------------------------------------------------------------------
# Default (built-in) allow reasons -- structural false-positive shapes.
# Mirrors tools/public_value_scan.py's own UUID/hex-run-context style
# (r3_number_in_hex_or_uuid_context) per the WP-9 spec's "same exclusion
# rules as the existing scanner".
# ---------------------------------------------------------------------------
DEFAULT_ALLOW_REASONS = (
    "uuid_fragment",
    "long_hex_digest",
    "credential_id_prefix",
    "content_digest",
    "obviously_synthetic",
)


def default_allow_reason(line: str, start: int, end: int, token: str) -> str | None:
    """Return a DEFAULT_ALLOW_REASONS name if `token` (at line[start:end]) is
    a known false-positive shape, else None. `line` is the single source
    line the token was found on (used for context only)."""
    # uuid_fragment: token's span lies fully inside a canonical
    # 8-4-4-4-12 UUID (the 4-char groups are already excluded by the
    # candidate's own 7-40 length floor, but the 8- and 12-char groups
    # are not).
    for m in _UUID_RE.finditer(line):
        if m.start() <= start and end <= m.end():
            return "uuid_fragment"

    # long_hex_digest: token sits inside a contiguous run of lowercase hex
    # characters longer than the regex's own 40-char cap could ever match
    # whole (e.g. a sha256/sha512 digest). HEX_TOKEN_RE's \b anchors mean
    # this can only happen if the run is broken by a non-hex-but-word
    # character somewhere the token itself doesn't span; kept as a
    # defensive, explicitly-named check per the WP-9 spec's example list
    # rather than relying on that being unreachable in practice.
    lo, hi = start, end
    while lo > 0 and line[lo - 1] in _HEXRUN_CHARS:
        lo -= 1
    while hi < len(line) and line[hi] in _HEXRUN_CHARS:
        hi += 1
    if hi - lo > 40:
        return "long_hex_digest"

    # credential_id_prefix: a locator-style credential_id whose hex suffix
    # alone is hash-shaped, e.g. "crd-0123456789abcdef" / "ctl-...". The
    # underscore form ("crd_...") can never reach HEX_TOKEN_RE in the first
    # place (underscore is a \w character, so \b never fires between it and
    # the hex run) -- this branch exists for the hyphen form, which does.
    prefix_ctx = line[max(0, start - 6):start]
    if _CRDID_PREFIX_RE.search(prefix_ctx):
        return "credential_id_prefix"

    # content_digest: a container-image / artifact digest written as
    # "sha256:<hex>" (possibly truncated with an ellipsis in prose). Not a
    # git object name, so never in a commit-map (WP-9 rehearsal, 2026-09-06).
    # Also the prose form "sha256 `968d…`" / "sha256=…" used when a checksum
    # is quoted (truncated with an ellipsis) in design records.
    if "sha256" in line[max(0, start - 12):start].lower():
        return "content_digest"

    # obviously_synthetic: the ascending digit run or a single repeated
    # character -- documentation examples of hex-shaped ids, never real
    # object names (same shape rule as public_value_scan.py R4).
    tok = line[start:end]
    if tok == "0123456789abcdef"[: end - start] or len(set(tok)) == 1:
        return "obviously_synthetic"

    return None


def compile_user_allow_patterns(patterns: list[str], allow_file: str | None) -> list[re.Pattern]:
    compiled = [re.compile(p) for p in patterns]
    if allow_file:
        for raw in Path(allow_file).read_text(encoding="utf-8").splitlines():
            raw = raw.strip()
            if not raw or raw.startswith("#"):
                continue
            compiled.append(re.compile(raw))
    return compiled


def user_allow_reason(token: str, patterns: list[re.Pattern]) -> str | None:
    for pat in patterns:
        if pat.fullmatch(token):
            return f"allow:{pat.pattern}"
    return None


# ---------------------------------------------------------------------------
# commit-map parsing
# ---------------------------------------------------------------------------
_SHA_RE = re.compile(r"[0-9a-f]{7,40}")


def parse_commit_map(path: str) -> list[tuple[str, str]]:
    """Parse a `git filter-repo` commit-map: an optional "old new" header
    line, then lines of "<old-full-sha> <new-full-sha>". Malformed / blank
    lines are skipped."""
    pairs: list[tuple[str, str]] = []
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    for idx, raw in enumerate(lines):
        line = raw.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) != 2:
            continue
        old, new = parts
        if idx == 0 and old.lower() == "old" and new.lower() == "new":
            continue
        if not _SHA_RE.fullmatch(old) or not _SHA_RE.fullmatch(new):
            continue
        pairs.append((old, new))
    return pairs


def classify_token(token: str, commit_map: list[tuple[str, str]]) -> tuple[str, str | None]:
    matches = [pair for pair in commit_map if pair[0].startswith(token)]
    if len(matches) == 1:
        return "replaced", matches[0][1][: len(token)]
    if len(matches) == 0:
        return "unmatched", None
    return "ambiguous", None


def residual_matches(token: str, commit_map: list[tuple[str, str]]) -> int:
    """Used by --verify: count of old shas `token` still front-matches,
    regardless of uniqueness. >0 means an un-rewritten reference remains."""
    return sum(1 for old, _new in commit_map if old.startswith(token))


# ---------------------------------------------------------------------------
# File selection
# ---------------------------------------------------------------------------
def _git_ls_files(pathspec: list[str]) -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-files", *pathspec],
        capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    return out


def resolve_target_files(paths: list[str] | None) -> list[str]:
    if paths:
        seen: set[str] = set()
        out: list[str] = []
        for p in paths:
            for rel in _git_ls_files([p]):
                if rel not in seen:
                    seen.add(rel)
                    out.append(rel)
        return out
    return _git_ls_files(["*.md"])


# ---------------------------------------------------------------------------
# Scan / rewrite core
# ---------------------------------------------------------------------------
class Finding:
    __slots__ = ("path", "lineno", "token", "verdict", "replacement", "reason")

    def __init__(self, path, lineno, token, verdict, replacement=None, reason=None):
        self.path = path
        self.lineno = lineno
        self.token = token
        self.verdict = verdict
        self.replacement = replacement
        self.reason = reason


def process_text(
    rel: str,
    text: str,
    commit_map: list[tuple[str, str]],
    user_patterns: list[re.Pattern],
    disable_default_allow: bool,
    apply: bool,
    findings: list[Finding],
) -> tuple[str, bool]:
    out_lines: list[str] = []
    changed = False
    for lineno, raw_line in enumerate(text.splitlines(keepends=True), start=1):

        def repl(m: re.Match) -> str:
            nonlocal changed
            tok = m.group(0)
            if not has_digit_and_alpha(tok):
                return tok
            start, end = m.start(), m.end()
            reason = None if disable_default_allow else default_allow_reason(raw_line, start, end, tok)
            if reason is None:
                reason = user_allow_reason(tok, user_patterns)
            if reason is not None:
                findings.append(Finding(rel, lineno, tok, "allowed", reason=reason))
                return tok
            verdict, replacement = classify_token(tok, commit_map)
            findings.append(Finding(rel, lineno, tok, verdict, replacement))
            if apply and verdict == "replaced":
                changed = True
                return replacement
            return tok

        out_lines.append(HEX_TOKEN_RE.sub(repl, raw_line))
    return "".join(out_lines), changed


def read_text(full: Path) -> str | None:
    try:
        data = full.read_bytes()
    except OSError:
        return None
    if b"\x00" in data:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def run_scan(
    files: list[str],
    commit_map: list[tuple[str, str]],
    user_patterns: list[re.Pattern],
    disable_default_allow: bool,
    apply: bool,
) -> tuple[list[Finding], dict[str, str]]:
    findings: list[Finding] = []
    to_write: dict[str, str] = {}
    for rel in files:
        full = REPO_ROOT / rel
        text = read_text(full)
        if text is None:
            continue
        new_text, changed = process_text(
            rel, text, commit_map, user_patterns, disable_default_allow, apply, findings
        )
        if apply and changed:
            to_write[rel] = new_text
    return findings, to_write


def run_verify(
    files: list[str],
    commit_map: list[tuple[str, str]],
    user_patterns: list[re.Pattern],
    disable_default_allow: bool,
) -> list[Finding]:
    residual: list[Finding] = []
    for rel in files:
        full = REPO_ROOT / rel
        text = read_text(full)
        if text is None:
            continue
        for lineno, raw_line in enumerate(text.splitlines(keepends=True), start=1):
            for m in HEX_TOKEN_RE.finditer(raw_line):
                tok = m.group(0)
                if not has_digit_and_alpha(tok):
                    continue
                start, end = m.start(), m.end()
                reason = None if disable_default_allow else default_allow_reason(raw_line, start, end, tok)
                if reason is None:
                    reason = user_allow_reason(tok, user_patterns)
                if reason is not None:
                    continue
                n = residual_matches(tok, commit_map)
                if n > 0:
                    residual.append(Finding(rel, lineno, tok, "residual", reason=f"front-matches {n} old sha(s)"))
    return residual


def print_findings(findings: list[Finding]) -> None:
    for f in findings:
        if f.verdict == "replaced":
            print(f"{f.path}:{f.lineno} | {f.token} | {f.verdict} -> {f.replacement}")
        elif f.reason:
            print(f"{f.path}:{f.lineno} | {f.token} | {f.verdict} ({f.reason})")
        else:
            print(f"{f.path}:{f.lineno} | {f.token} | {f.verdict}")


def print_summary(findings: list[Finding]) -> dict[str, int]:
    counts = {"replaced": 0, "ambiguous": 0, "unmatched": 0, "allowed": 0}
    for f in findings:
        if f.verdict in counts:
            counts[f.verdict] += 1
    print(
        "# replaced={replaced} ambiguous={ambiguous} unmatched={unmatched} allowed={allowed}".format(**counts)
    )
    return counts


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Rewrite git commit-hash references inside tracked documents to "
            "match a `git filter-repo` commit-map, after a history rewrite "
            "(WP-9 / design D-1 (iv) (2), Sec.9 step 2)."
        )
    )
    p.add_argument("commit_map", nargs="?", help="path to the filter-repo commit-map file")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="list + counts only, no writes")
    mode.add_argument("--apply", action="store_true", help="write replacements (refuses if any ambiguous)")
    mode.add_argument("--verify", action="store_true", help="post-apply: fail if any old sha reference remains")
    mode.add_argument("--self-test", action="store_true", help="run embedded self-test scenarios and exit")
    p.add_argument(
        "--paths", nargs="*", default=None,
        help="git pathspec(s) to restrict target files (default: all *.md tracked files)",
    )
    p.add_argument(
        "--allow", action="append", default=[],
        help="regex (fullmatch against the raw token) to mark as allowed; repeatable",
    )
    p.add_argument("--allow-file", default=None, help="file of one regex/literal-token per line (# comments ok)")
    p.add_argument(
        "--no-default-allow", action="store_true",
        help="disable the built-in structural allow reasons (uuid_fragment / long_hex_digest / credential_id_prefix)",
    )
    return p


def _require_mode(args) -> None:
    if not (args.check or args.apply or args.verify or args.self_test):
        raise SystemExit("one of --check / --apply / --verify / --self-test is required")
    if not args.self_test and not args.commit_map:
        raise SystemExit("commit_map is required unless --self-test")


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    _require_mode(args)

    if args.self_test:
        return self_test()

    commit_map = parse_commit_map(args.commit_map)
    user_patterns = compile_user_allow_patterns(args.allow, args.allow_file)
    files = resolve_target_files(args.paths)

    if args.verify:
        residual = run_verify(files, commit_map, user_patterns, args.no_default_allow)
        for f in residual:
            print(f"{f.path}:{f.lineno} | {f.token} | {f.verdict} ({f.reason})")
        print(f"# verify residual={len(residual)}")
        return 1 if residual else 0

    apply = bool(args.apply)
    findings, to_write = run_scan(files, commit_map, user_patterns, args.no_default_allow, apply=apply)
    counts = {"replaced": 0, "ambiguous": 0, "unmatched": 0, "allowed": 0}
    for f in findings:
        counts[f.verdict] += 1

    if args.apply:
        if counts["ambiguous"] > 0:
            print_findings(findings)
            print_summary(findings)
            print("# apply refused: ambiguous > 0, no files written")
            return 1
        for rel, new_text in to_write.items():
            (REPO_ROOT / rel).write_text(new_text, encoding="utf-8")
        print_findings(findings)
        print_summary(findings)
        print(f"# files_written={len(to_write)}")
        return 0

    # --check (default mode if none of --apply/--verify/--self-test given
    # but --check also not given -- treat bare invocation as --check)
    print_findings(findings)
    print_summary(findings)
    return 1 if (counts["ambiguous"] > 0 or counts["unmatched"] > 0) else 0


# ---------------------------------------------------------------------------
# --self-test
# ---------------------------------------------------------------------------
def self_test() -> int:
    failures: list[str] = []

    def check(label: str, cond: bool) -> None:
        status = "PASS" if cond else "FAIL"
        print(f"[self-test] {status}: {label}")
        if not cond:
            failures.append(label)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)

        # -- synthetic commit-map -------------------------------------------------
        # A and B share a 7-char prefix ("aa11111", digit+letter mixed so it is
        # itself a valid candidate token) -> ambiguous.
        # C has an 8-char prefix unique among all three -> replaceable. Every
        # short prefix used below deliberately mixes a digit and a letter,
        # because an all-letter run (like a naive "aaaaaaa"/"deadbee") is
        # excluded from candidacy entirely (has_digit_and_alpha) and would
        # never reach classify_token in the first place.
        old_a = "aa11111" + "a" * 33
        new_a = "bb22222" + "c" * 33
        old_b = "aa11111" + "b" * 33
        new_b = "cc33333" + "d" * 33
        old_c = "de1adb0" + "c" * 33
        new_c = "fe2edf0" + "e" * 33
        commit_map_path = tmp_path / "commit-map.txt"
        commit_map_path.write_text(
            "old new\n"
            f"{old_a} {new_a}\n"
            f"{old_b} {new_b}\n"
            f"{old_c} {new_c}\n",
            encoding="utf-8",
        )
        commit_map = parse_commit_map(str(commit_map_path))
        check("commit-map parses 3 pairs", len(commit_map) == 3)

        # -- scenario 1: unique prefix -> replaced ---------------------------------
        doc_unique = tmp_path / "doc_unique.md"
        doc_unique.write_text("see commit de1adb0 for details\n", encoding="utf-8")
        findings: list[Finding] = []
        new_text, changed = process_text(
            "doc_unique.md", doc_unique.read_text(encoding="utf-8"),
            commit_map, [], False, apply=True, findings=findings,
        )
        replaced = [f for f in findings if f.verdict == "replaced"]
        check("unique prefix classified as replaced", len(replaced) == 1 and replaced[0].token == "de1adb0")
        check("unique prefix replaced with same-length new front", "fe2edf0" in new_text and "de1adb0" not in new_text)

        # -- scenario 2: non-unique short hash -> ambiguous, NOT replaced ----------
        doc_ambig = tmp_path / "doc_ambig.md"
        doc_ambig.write_text("see commit aa11111 for details\n", encoding="utf-8")
        findings2: list[Finding] = []
        new_text2, changed2 = process_text(
            "doc_ambig.md", doc_ambig.read_text(encoding="utf-8"),
            commit_map, [], False, apply=True, findings=findings2,
        )
        ambiguous = [f for f in findings2 if f.verdict == "ambiguous"]
        check("non-unique short hash classified as ambiguous", len(ambiguous) == 1 and ambiguous[0].token == "aa11111")
        check("ambiguous token left untouched by apply", "aa11111" in new_text2 and not changed2)

        # -- scenario 3: unmatched token -----------------------------------------
        doc_unmatched = tmp_path / "doc_unmatched.md"
        doc_unmatched.write_text("random token 0123abc appears here\n", encoding="utf-8")
        findings3: list[Finding] = []
        process_text(
            "doc_unmatched.md", doc_unmatched.read_text(encoding="utf-8"),
            commit_map, [], False, apply=False, findings=findings3,
        )
        unmatched = [f for f in findings3 if f.verdict == "unmatched"]
        check("token absent from commit-map classified as unmatched", len(unmatched) == 1 and unmatched[0].token == "0123abc")

        # -- scenario 4: default-allow structural exclusions ----------------------
        doc_allow = tmp_path / "doc_allow.md"
        doc_allow.write_text(
            "uuid 1a2b3c4d-5e6f-7a8b-9c0d-1e2f3a4b5c6d here; "
            "id crd-0123456789fedcba too\n",
            encoding="utf-8",
        )
        findings4: list[Finding] = []
        process_text(
            "doc_allow.md", doc_allow.read_text(encoding="utf-8"),
            commit_map, [], False, apply=False, findings=findings4,
        )
        allowed_reasons = {f.reason for f in findings4 if f.verdict == "allowed"}
        check(
            "uuid fragment classified as allowed (uuid_fragment)",
            "uuid_fragment" in allowed_reasons,
        )
        check(
            "hyphenated credential_id hex suffix classified as allowed (credential_id_prefix)",
            "credential_id_prefix" in allowed_reasons,
        )
        non_allow_verdicts = {f.verdict for f in findings4} - {"allowed"}
        check("no allowed-shape token also falls through to another verdict", not non_allow_verdicts)

        # -- scenario 5: --allow / --allow-file user patterns ----------------------
        doc_user_allow = tmp_path / "doc_user_allow.md"
        doc_user_allow.write_text("synthetic id feedbee1 must not resolve\n", encoding="utf-8")
        user_patterns = compile_user_allow_patterns(["feedbee1"], None)
        findings5: list[Finding] = []
        process_text(
            "doc_user_allow.md", doc_user_allow.read_text(encoding="utf-8"),
            commit_map, user_patterns, False, apply=False, findings=findings5,
        )
        check(
            "user --allow pattern short-circuits lookup",
            len(findings5) == 1 and findings5[0].verdict == "allowed" and findings5[0].reason.startswith("allow:"),
        )

        # -- scenario 6 (mutation 2 target): --verify catches a residual old sha --
        doc_residual = tmp_path / "doc_residual.md"
        doc_residual.write_text("still references de1adb0, unfortunately\n", encoding="utf-8")
        # Simulate --verify's own residual test directly against this text,
        # without depending on REPO_ROOT file layout (run_verify itself reads
        # REPO_ROOT / rel, which this tmp-dir scenario is not under):
        residual_here = []
        for lineno, raw_line in enumerate(doc_residual.read_text(encoding="utf-8").splitlines(keepends=True), start=1):
            for m in HEX_TOKEN_RE.finditer(raw_line):
                tok = m.group(0)
                if not has_digit_and_alpha(tok):
                    continue
                if default_allow_reason(raw_line, m.start(), m.end(), tok):
                    continue
                if residual_matches(tok, commit_map) > 0:
                    residual_here.append(tok)
        check("verify detects an un-rewritten old-sha reference as residual", "de1adb0" in residual_here)

        # -- scenario 7: a fully-rewritten document has zero residual --------------
        doc_clean = tmp_path / "doc_clean.md"
        doc_clean.write_text("now references fe2edf0, all good\n", encoding="utf-8")
        residual_clean = []
        for lineno, raw_line in enumerate(doc_clean.read_text(encoding="utf-8").splitlines(keepends=True), start=1):
            for m in HEX_TOKEN_RE.finditer(raw_line):
                tok = m.group(0)
                if not has_digit_and_alpha(tok):
                    continue
                if default_allow_reason(raw_line, m.start(), m.end(), tok):
                    continue
                if residual_matches(tok, commit_map) > 0:
                    residual_clean.append(tok)
        check("verify reports zero residual for an already-rewritten document", residual_clean == [])

        # -- scenario 8: candidate exclusion for digit-only / letter-only ---------
        check("all-digit token is not a candidate", not has_digit_and_alpha("1234567"))
        check("all-letter token is not a candidate", not has_digit_and_alpha("abcdefg"))
        check("mixed digit+letter token IS a candidate", has_digit_and_alpha("a1b2c3d"))

        # -- scenario 9: long_hex_digest exercised directly. HEX_TOKEN_RE's own
        # \b anchors mean it can never itself extract a >40-char contiguous
        # lowercase-hex run as a <=40-char token (both ends of such a run
        # would need a genuine word/non-word transition, which a homogeneous
        # hex run does not have in its interior) -- so this branch is called
        # directly against a synthetic 64-char digest line, proving the
        # function's own logic rather than relying on an unreachable path.
        digest = ("e3b0c44298fc1c14" * 4)[:64]
        assert len(digest) == 64
        line = f"sha256:{digest}\n"
        start = line.index(digest)
        end = start + 40  # a hypothetical 40-char sub-match within the run
        check(
            "long_hex_digest fires for a token embedded in a >40-char hex run",
            default_allow_reason(line, start, end, digest[:40]) == "long_hex_digest",
        )

    if failures:
        print(f"# self-test FAILED: {len(failures)} failure(s): {failures}")
        return 1
    print("# self-test OK: all scenarios passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
