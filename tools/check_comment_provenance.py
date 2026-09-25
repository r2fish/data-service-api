#!/usr/bin/env python3
"""check_comment_provenance.py -- comment/docstring provenance guard for the
code-comment-history移動 effort (design docs/design/CODE_COMMENT_PROVENANCE_V1.md
v0.4, work order docs/work-orders/WORK_ORDER_CODE_COMMENT_PROVENANCE_CS1.md
change set 0; revised after the change-set-0 code review, monitor ruling
2026-09-14).

Two independent modes, matching design D-3/D-4:

    --base <rev> <src path>...
        Change-time diff check (design §4.1 (1)-(5)) between the working
        tree's current `<src path>` and its content at git revision `<rev>`
        (read via `git show <rev>:<path>`, never `git checkout`). Never run
        in CI (D-4); a reviewer re-runs it by hand against the same `<rev>`.
        A changeset that adds or edits a companion correction record
        (design §9.3 rule 6) must run this against every `<src path>`
        carrying that CH-ID, since the standing rev-vs-itself guard only
        ever reads HEAD's own committed records.

    --register
        Standing repository-wide check (design §4.2, items 1-6) over the
        working tree's `docs/code-history/` register and both peers' `src/`
        trees. CI's `tools-tests` job runs this file's own self-test suite
        (`tools/tests/test_comment_provenance.py`), which itself exercises
        `--register` against the real repository as one of its cases;
        `--register` is not separately invoked by CI outside that self-test.

Design boundary (§3): only comments and docstrings under each peer's
`src/` are in scope. `tests/` and `conformance-tests/` are never scanned by
either mode. Trailing/inline comments (`x = 1  # ...`) are never part of a
history block either way (design v0.4): they are excluded from block
extraction below the same as always, but an added trailing comment is
still scanned by the (5) added-history-token check, since that check reads
whole diff lines, not extracted blocks.

Standard library only (tools/public_value_scan.py / tools/check_doc_refs.py
convention) -- no external dependency, no dependence on `sys.executable`.

Exit code: 0 if the requested mode found nothing to flag, 1 otherwise (or if
a required file could not be read/parsed -- an unreadable input is never
treated as "nothing to check").

Known gaps (recorded per docs/work-orders/OPERATING_CONDITIONS.md 1.12-71:
a gap that cannot let a contract violation or a Security Invariant breach
through the completion gate is recorded here and not filed in the ledger):
    1. not detected: whether a `file:line` position reference written
       inside a src docstring/comment resolves to anything (one measured
       staleness; ledger R-96).
       why: both modes reason about BLOCK provenance (registration,
       CH-ID, block keys); the content a reference points at is never
       read.
       caught by: for `security/CONTROL_MAPPING.md`, R-88's own checks
       in `conformance-tests/test_control_mapping_register.py` (the
       section starting at its `# R-88` comment); for the conformance
       `.py` files, `conformance-tests/test_conformance_docstring_
       position_refs.py` (R-95); for both peers' `src/` and `tests/`,
       code review -- accepted for now, since an allow table and a floor
       would have to be designed first (ledger R-96, closed into this
       entry 2026-09-23).
    2. not detected: a replacement of the statement FOLLOWING a
       CH-ID-less block by a different statement of the same AST kind.
       why: the section 4.1 (2) block key re-pairs an old/new `replace`
       span when the AST kind matches (and the name too, for def/class),
       so a same-kind substitute keeps the key stable (design
       docs/design/CODE_COMMENT_PROVENANCE_V1.md v0.26 records this
       limit).
       caught by: code review (accepted: the alternative is the false
       red this key was built to remove).
    3. not detected: the difference between a moved block and a
       docstring written for the FIRST time on a function that already
       exists at the base rev -- that shows up as a section 4.1 (2) red
       reading `old 0, new 1`.
       why: (2) counts CH-ID-less blocks per scope, and a new block that
       carries no history has no receptacle of its own.
       caught by: a human reading that red and judging it a justified
       one (accepted; this is what R-67's own change set did).
    4. not detected: a history token or a registered block that appears
       OUTSIDE both peers' `src/` (tests/, conformance-tests/, tools/,
       docs/ other than the register itself).
       why: design section 3's scope -- see "Design boundary (section
       3)" above.
       caught by: `--register`'s own checks over `docs/code-history/`
       and both peers' `src/`, plus code review (accepted).
    5. not detected: a companion duplicate placed under
       `docs/archive/docs/code-history/<peer>/*.md`.
       why: `_companion_files`'s enumeration of a peer's companions is a
       NON-RECURSIVE glob scoped to `docs/code-history/<peer>/` itself
       (design docs/design/DOC_ARCHIVE_SPLIT_V1.md D-3 (ii)); anything
       under `docs/archive/` sits outside that one directory, so it is
       never enumerated, moved or not.
       caught by: the registry's own canonical `docs/code-history/` tree
       is never moved to `docs/archive/` (design DOC_ARCHIVE_SPLIT_V1.md
       section 6), so this gap has no live instance to catch.
    6. not detected: a comment/docstring change under review when this
       tool's own root checkout copy is run against a worktree's paths.
       why: `REPO_ROOT` (`Path(__file__).resolve().parent.parent`) is
       this tool's OWN copy's location, not the tree being reviewed --
       running a main checkout's copy of this script against a
       worktree's `src/` paths silently checks the main checkout's own
       `docs/code-history/` and `src/` trees instead of the worktree's
       edited ones.
       caught by: a worktree-based review runs the worktree's own copy
       of this tool (`cd` into the worktree, or an absolute path under
       it), never the root checkout's copy with worktree-relative
       arguments (accepted; no cross-checkout resolution is
       implemented).
"""
from __future__ import annotations

import argparse
import ast
import copy
import difflib
import inspect
import re
import subprocess
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Peers (design §3 scope: both peers' `src/` only).
# ---------------------------------------------------------------------------
PEERS: tuple[str, ...] = ("r2db-api", "MitateDB-api")
PEER_SRC_DIRS: dict[str, str] = {
    "r2db-api": "src/r2db_api",
    "MitateDB-api": "src/mitatedb_api",
}

# ---------------------------------------------------------------------------
# design §4.1 (5): the explicit history-token word list, verbatim (v0.3),
# compiled with re.ASCII (v0.4 review fix) so `\b`/`\d` never treat a
# Japanese character as a "word" character -- without it, a token glued
# directly onto Japanese text with no separating space or punctuation
# (e.g. "作業WP-3で", "2026-09-14に") would silently fail to match, because
# Python's default Unicode `\w` counts CJK ideographs as word characters
# and so sees no boundary between them and the token.
# R- / L- / D- are deliberately NOT in this list (handled by §3's judgment
# table instead, on a per-block-moved basis, never by this blanket scan).
# ---------------------------------------------------------------------------
_REVIEW_FID_TOKEN_RE = re.compile(
    r"\breview(?: round)? (?:F-\d+[a-z]?|\(F-\d+[a-z]?\))(?![A-Za-z0-9_])",
    re.ASCII | re.IGNORECASE,
)
# design 9.2 rule 1 (Z0i-1 (B), change set 0i; F2/F3 code-review fix,
# M1): the "review (F-n)" form can ALSO occur as a standalone TOP-LEVEL
# parenthetical whose OWN content is just the F-ID, with "review"/
# "review round" sitting in the surrounding sentence prose immediately
# before the "(" -- outside the paren's own inner text, so this
# pattern's premerge (which only ever sees one paren's own inner
# content, or a plain run of flat text with no parens at all) never
# spans across that paren boundary to find it (real corpus: MitateDB
# `http.py` CH-0198, "round-1 review (F-2) found this pair..."). The
# pattern's own SECOND alternative, `\(F-n\)`, is a BALANCED closed
# paren (not two independently optional `(`/`)`, which would also
# match a dangling "review (F-2" or "review F-2)"), and the trailing
# `(?![A-Za-z0-9_])` stops it from swallowing part of a longer token.
# `_sentence_reachable` checks whether a match of THIS SAME pattern's
# own `(F-n)` alternative ends flush with a given paren's own close and,
# if so, tells `_paren_words_removable` (`preceded_by_review`) to treat
# a bare F-ID that is that ONE paren's entire content as a removable
# history token too -- deriving the flag from this ONE shared pattern
# (M1), never a separate, independently-maintained prefix regex.

_HISTORY_TOKEN_PATTERNS: tuple[re.Pattern[str], ...] = (
    # `(?<![A-Za-z0-9])` (v0.4 review round 2) instead of `\b`: an
    # underscore directly before "WP-" (`_WP-3`) is itself a word
    # character, so `\b` would see no boundary there and miss it -- this
    # lookbehind only excludes a letter/digit immediately before, so
    # "_WP-3" and "作業WP-3" (with re.ASCII) are both caught.
    re.compile(r"(?<![A-Za-z0-9])WP-[0-9A-Za-z-]+", re.ASCII),
    # design §9 rule 1 (v0.6, change set 0c): multi-word history tokens,
    # case-insensitive. "round \d+" is excluded when immediately followed
    # by a unit word (decimal/digit(s)/place(s)/significant) -- that is a
    # numeric-precision phrase, not a history round number.
    re.compile(r"\bphase \d+", re.ASCII | re.IGNORECASE),
    # design 9.2 rule 1 (v0.18, change set 0i, Z0i-1 (B)): a REVIEW
    # POINTER naming an F-ID ("review F-2", "review round F-5", "review
    # (F-2)") is ONE history token, span and all -- an indicated
    # review-round pointer, not the executable-check F-ID it happens to
    # share a number with. Placed BEFORE the plain "review" entry below
    # so `_premerge_tokens` merges the WHOLE span first (the same
    # compiled pattern object, `_REVIEW_FID_TOKEN_RE`, is reused
    # unchanged by `_protected_reference_ids` (M1) to strip this span
    # before protected-ID extraction, in the other three of the four
    # 9.2 "使う箇所"). Known constraint (9.2 (b)): an indication-less
    # pointer (bare "F-2" with no "review" beside it) stays protected,
    # the same protection-favoring bias as 0d's own known constraint.
    _REVIEW_FID_TOKEN_RE,
    # Inflected forms (v0.4 review round 2): "reviews"/"reviewed" etc.
    re.compile(r"\breview(?:s|ed|er|ers)?\b", re.ASCII),
    re.compile(
        r"\bround \d+\b(?!\s+(?:decimal|digits?|places?|significant)\b)",
        re.ASCII | re.IGNORECASE,
    ),
    re.compile(r"\b20\d\d-\d\d-\d\d\b", re.ASCII),
    re.compile(r"差し戻し"),
    re.compile(r"監督裁定"),
    # design §9 rule 1: broadened from "supervisor ruling" alone to the
    # (supervisor|supervisory|monitor|requester) ruling family, case-
    # insensitive.
    re.compile(r"\b(?:supervisor|supervisory|monitor|requester) ruling\b", re.ASCII | re.IGNORECASE),
    re.compile(r"\bblocker\b", re.ASCII),
)

# design D-2: the only two canonical reference-line forms. `_DOC_HIST_LINE_RE`
# carries re.MULTILINE (v0.4 review fix): `_referenced_ids_in_source` and
# `_reference_format_violations` need it to `.finditer()`/`.search()` a
# multi-line docstring embedded mid-file, where `^`/`$` must anchor each
# line, not just the start/end of the whole source string. Matching it
# against an already-isolated single line (`_split_marker`,
# `_reference_format_violations`'s per-line `.match(stripped)`) is
# unaffected by the flag either way.
_HASH_REF_RE = re.compile(r"^# history: (CH-\d{4})$")
# `\s*` prefix/suffix (v0.4 review fix (c)): in the RAW source file, a
# docstring's own lines carry the enclosing def/class's indentation (e.g.
# `    History: CH-0001` inside a function), so a strict column-0 match
# would never find it there -- only in the already-dedented (cleandoc'd)
# canonical block text `_split_marker` compares against. MULTILINE lets
# `^`/`$` anchor per physical line when this is `.finditer()`-scanned
# against a whole multi-line source (`_referenced_ids_in_source`); it is a
# no-op when matched against an already-isolated single-line string
# (`_split_marker`, `_reference_format_violations`'s per-line `.match`).
_DOC_HIST_LINE_RE = re.compile(r"^\s*History: (CH-\d{4})\s*$", re.MULTILINE)
# Loose detector for "looks like a CH-ID token, of any digit length" --
# used only to find candidates for the canonical-format check (§4.2-4),
# never to decide what counts as "referenced" (that stays strict, 4 digits
# only, via _HASH_REF_RE / _DOC_HIST_LINE_RE above).
_CH_ID_LOOSE_RE = re.compile(r"\bCH-\d+\b")

# design §4.1 (4): a "bare ID lacking a provenance tag in the same parens"
# is removable; SI-/C-/CCR- are always provenance-tagged, never removable.
_BARE_ID_RE = re.compile(r"^[A-Z]{1,6}-\d+[a-z]?$")
# design 9.2 rule 1 (v0.18, change set 0i, monitor ruling Z0i-1): "F-"
# (the F-ID hazard-declaration family, e.g. `F-1` .. `F-16`) is a
# PROTECTED prefix, exactly like SI-/C-/CCR- -- never a removable bare
# ID, and never merged with a following branch-number parenthetical
# (`_ID_BRANCH_RE`'s exclusion list is built FROM this tuple, so
# `F-4b(ii)` is automatically excluded from that merge too, the same
# way `SI-08(2)` already was -- see 9.2's own note on this).
_PROTECTED_ID_PREFIXES: tuple[str, ...] = ("SI-", "C-", "CCR-", "F-")
# A parenthetical (or, for §4.1 (6), a whole label) carries its own
# provenance tag if it names a file that is REAL (design §9 rule 2, v0.6,
# change set 0c -- see `_has_real_filename_reference` below), or a word
# containing a path separator that is not itself just a slash-joined ID
# list (`SI-08/R-5` is NOT a path: every segment already looks like a
# bare/protected ID), or the words "roadmap" / "spec" anywhere in it, or a
# VERSIONED DOCUMENT NAME (0b review round 3 supervisor ruling (a)(i)):
# `contract <version>`, `design <version>`, or `<document name>
# v<version>`, version being `\d+(\.\d+)+` or `v\d+(\.\d+)*`. In any of
# these cases NO bare ID in the same parens/label is removable, even one
# that would otherwise qualify, because the file/roadmap/spec/versioned-
# document reference is what the ID is qualified by (protection covers
# the WHOLE parenthetical or label, not only the ID adjacent to the tag).
# Recognized file extensions ONLY -- deliberately NOT "any letter-led
# `.suffix`": that wider form (an earlier revision of this file used it)
# mistook an ordinary dotted identifier inside backticks (`` `information_
# schema.columns.domain_name` ``, `` `create_entity` `` has none at all)
# for a filename candidate, wrongly subjecting it to §9 rule 2's real-path
# check and deleting it as a "fake filename" once it inevitably failed
# that check -- corrupting unrelated code references, discovered against
# the real r2db `postgres.py` (basis 5d12799, CH-0001 module docstring).
_KNOWN_FILE_EXTENSIONS: tuple[str, ...] = (
    "md", "py", "sql", "json", "yaml", "yml", "txt", "toml", "cfg", "ini",
    "sh", "js", "ts", "html", "css",
)
_EXT_SUFFIX = r"\.(?:" + "|".join(_KNOWN_FILE_EXTENSIONS) + r")\b"
_FILENAME_EXT_RE = re.compile(_EXT_SUFFIX, re.IGNORECASE)
_PROVENANCE_WORD_RE = re.compile(r"\b(?:roadmap|spec)\b")
_VERSION_TOKEN = r"(?:\d+(?:\.\d+)+|v\d+(?:\.\d+)*)"
_VERSIONED_DOC_RE = re.compile(
    r"\b(?:contract|design)\s+" + _VERSION_TOKEN + r"\b"
    r"|\b[A-Za-z][\w-]*\s+v\d+(?:\.\d+)*\b",
    re.IGNORECASE,
)

# design §9 rule 2 (v0.6, change set 0c): a filename-looking string is
# only a provenance tag if it REALLY EXISTS in the repository tree at the
# relevant revision (design §9's "出所になるファイル名は、リポジトリ内に
# 実在するパスだけ") -- `{scratchpad}/...` and an unqualified working-note
# name (`rulings-r5-r6.md`) never exist there, so they are never tags;
# instead they are themselves history tokens (removable, uncounted as
# content). A backtick span, and a path that a physical line-wrap broke in
# two (already rejoined with a single space by `_flatten_comment`/
# `_flatten_docstring` well before this point), are matched as ONE
# candidate; internal whitespace is stripped before the tree-membership
# check so a wrap-broken path still matches its real, unbroken form.
_FILENAME_CANDIDATE_RE = re.compile(
    r"`[^`]*/[^`]*`"                      # backtick span containing a path separator
    r"|`[^`]*" + _EXT_SUFFIX + r"`"       # backtick span ending in a KNOWN extension
    r"|\{[^}\s]*\}/[^\s,;()]+"            # bare `{...}/...` (e.g. `{scratchpad}/...`)
    r"|[^\s,;()`]*" + _EXT_SUFFIX,        # bare token ending in a KNOWN extension
    re.IGNORECASE,
)
_BARE_FILENAME_CANDIDATE_RE = re.compile(
    r"\{[^}\s]*\}/[^\s,;()`]+"            # bare `{...}/...` (e.g. `{scratchpad}/...`)
    r"|[^\s,;()`]*" + _EXT_SUFFIX,        # bare token ending in a KNOWN extension
    re.IGNORECASE,
)


def _clean_filename_candidate(raw: str) -> str:
    text = raw[1:-1] if raw.startswith("`") and raw.endswith("`") and len(raw) >= 2 else raw
    return re.sub(r"\s+", "", text)


def _filename_span_matches(text: str) -> list[tuple[int, int, str]]:
    """0f Item 1 fix (supervisor-reported bug present since 4bc9535): the
    OLD approach ran `_FILENAME_CANDIDATE_RE.finditer` directly over the
    whole text. Its backtick-span alternatives (`` `[^`]*/[^`]*` `` etc.)
    match a literal backtick ... backtick pair WITHOUT tracking which
    backtick is an "opener" and which is a "closer" -- so given
    "`a` below (design docs/design/X_V1.md R-2): a plain `SELECT` here.",
    the pattern happily starts at the CLOSING backtick of `` `a` `` and
    ends at the OPENING backtick of `` `SELECT` ``, since the run between
    them contains a "/" and no backtick. That swallows the entire bare
    path "docs/design/X_V1.md" into one bogus, non-real "candidate"
    (` below (design docs/design/X_V1.md R-2): a plain `), so the bare
    path is never seen as its own candidate and never recognized as a
    real, protected path.

    Fixed by pairing backticks front-to-back FIRST (0th+1st backtick is
    one span, 2nd+3rd is the next, ...; a trailing unmatched backtick is
    not treated as a span at all), then looking for path-shaped content
    (a) INSIDE each properly-paired span (checked against the span's own
    inner text, for a "/" or a known extension) and (b) in the residue
    OUTSIDE every span (checked with the bare-token-only patterns, which
    never themselves consume a backtick). This finds the sandwiched bare
    path as a candidate in its own right, independent of the backtick
    spans on either side of it."""
    tick_positions = [m.start() for m in re.finditer("`", text)]
    pairs = [
        (tick_positions[i], tick_positions[i + 1])
        for i in range(0, len(tick_positions) - 1, 2)
    ]
    covered = bytearray(len(text))
    for start, end in pairs:
        for k in range(start, end + 1):
            covered[k] = 1

    spans: list[tuple[int, int, str]] = []
    for start, end in pairs:
        inner = text[start + 1 : end]
        if "/" in inner or _FILENAME_EXT_RE.search(inner):
            spans.append((start, end + 1, text[start : end + 1]))

    idx = 0
    n = len(text)
    while idx < n:
        if covered[idx]:
            idx += 1
            continue
        j = idx
        while j < n and not covered[j]:
            j += 1
        segment = text[idx:j]
        for m in _BARE_FILENAME_CANDIDATE_RE.finditer(segment):
            if m.group(0):
                spans.append((idx + m.start(), idx + m.end(), m.group(0)))
        idx = j

    spans.sort(key=lambda s: s[0])
    return spans


def _sub_filename_candidates(text: str, repl) -> str:
    """Pairing-aware equivalent of `_FILENAME_CANDIDATE_RE.sub(repl, text)`
    (0f Item 1 fix) -- see `_filename_span_matches`."""
    pieces: list[str] = []
    pos = 0
    for start, end, matched in _filename_span_matches(text):
        if start < pos:
            continue  # defensive: skip any accidental overlap
        pieces.append(text[pos:start])
        pieces.append(repl(matched) if callable(repl) else repl)
        pos = end
    pieces.append(text[pos:])
    return "".join(pieces)


def _is_filename_candidate_fullmatch(word: str) -> bool:
    """Pairing-aware equivalent of `_FILENAME_CANDIDATE_RE.fullmatch(word)`
    (0f Item 1 fix) -- `word` qualifies only if it is ENTIRELY one single
    candidate span, not a partial or multi-span run."""
    spans = _filename_span_matches(word)
    return len(spans) == 1 and spans[0][0] == 0 and spans[0][1] == len(word)


def _filename_candidates(text: str) -> list[str]:
    return [s[2] for s in _filename_span_matches(text)]


_QUALNAME_LOCATION_SUFFIX_RE = re.compile(r"(?:::[A-Za-z_][A-Za-z0-9_.]*(?:\(\))?)+\Z")
_LINE_LOCATION_SUFFIX_RE = re.compile(r":\d+(?:-\d+)?\Z")


def _strip_location_suffix(candidate: str) -> str:
    """design 9.2 rule 2 (Z0i-3 (A), monitor ruling; F1 code-review fix):
    strip a trailing `:line` or `:line-line` range FIRST, then a
    trailing `::qualname` (ALL `::`-joined segments, e.g. `::Cls::meth`,
    M4) -- a segment MAY itself be a DOTTED Python qualname
    (`::ApplicationCell.transact`, the dominant real-corpus form) and MAY
    carry a trailing call-suffix `()` (`::entities()`) -- BEFORE the
    real-path membership check below -- so `http.py::get_catalog`,
    `` `cell.py::ApplicationCell.transact` `` and
    `r2db-api/src/r2db_api/limits.py:16-20` are matched against their
    real underlying path, rather than rejected as fake merely because of
    the location suffix appended to it. Line MUST be stripped BEFORE
    qualname: a candidate combining both (`::get_catalog:12`) would
    otherwise leave the qualname segment behind uncleaned, since the
    qualname pattern is anchored at the string's end (`\\Z`) and a
    trailing `:12` blocks it from matching there at all."""
    candidate = _LINE_LOCATION_SUFFIX_RE.sub("", candidate)
    candidate = _QUALNAME_LOCATION_SUFFIX_RE.sub("", candidate)
    return candidate


def _is_real_filename_candidate(raw: str, real_paths: frozenset[str]) -> bool:
    cleaned = _strip_location_suffix(_clean_filename_candidate(raw))
    if cleaned in real_paths:
        return True
    # design 9.2 rule 2 (change set 0i, monitor ruling): a MULTI-SEGMENT
    # candidate ("/" in cleaned -- a bare single-segment basename is
    # rule 3's job below, not this one) with no EXACT match is still
    # real if it is a proper suffix of some real path, split only at a
    # "/" boundary -- never mid-segment (a suffix like
    # "rity/CONTROL_MAPPING.md", cut out of the middle of
    # "security/CONTROL_MAPPING.md", is never real, since there is no
    # "/" immediately before "rity" in that real path). This is how a
    # peer-relative reference written WITHOUT its own peer's directory
    # prefix ("migrations/0003_provision_application.sql" for
    # "MitateDB-api/migrations/0003_provision_application.sql",
    # "r2db_api/ops.py" for "r2db-api/src/r2db_api/ops.py") is
    # recognized as real.
    if "/" in cleaned and any(p.endswith("/" + cleaned) for p in real_paths):
        return True
    # v0.7 follow-up supervisor ruling, WIDENED by design 9.2 rule 3
    # (Z0i-2 (A), change set 0i, monitor ruling): a filename with NO
    # path separator (e.g. `CONTROL_MAPPING.md`, or a basename shared by
    # both peers such as `service.py`/`ops.py`/`http.py`) still counts
    # as a provenance tag if its basename matches ONE OR MORE paths in
    # the tree -- 0 matches (it really doesn't exist) leaves it a
    # removable history token, same as before; ambiguity (`README.md`,
    # or a basename both peers happen to share) is no longer
    # disqualifying by itself, since the protecting condition is "does a
    # real file answer to this name", not "which real file, uniquely"
    # (the identity of the file is not what protection is judging --
    # OPERATING_CONDITIONS.md 1.7's "no proxy measure" ruling; the cost
    # of this widening is measured in the work order). `cleaned` itself
    # is compared AS-IS here (never reduced to its own basename), so a
    # "/"-containing candidate can never coincidentally match a real
    # path's basename this way.
    basename_matches = [p for p in real_paths if p.rpartition("/")[2] == cleaned]
    return len(basename_matches) >= 1


def _has_real_filename_reference(text: str, real_paths: frozenset[str]) -> bool:
    return any(_is_real_filename_candidate(c, real_paths) for c in _filename_candidates(text))


_SUBSCRIPT_RE = re.compile(r"^[A-Z]{1,2}$|^\d+$")
# Matches the opaque placeholder `_sentence_reachable`'s own ID+branch
# merge substitutes for a globally pre-merged ID+branch-number pair --
# never a real path segment, so it must never make `_looks_like_path_word`
# misfire on the ARTIFACT of that substitution (e.g. "I-6/\x00Y0\x00" for
# "I-6/D-5 (5)").
_ID_BRANCH_PLACEHOLDER_RE = re.compile(r"^\x00Y\d+\x00$")


def _looks_like_path_word(word: str) -> bool:
    """A slash-joined word is path-like only if some segment is neither
    ID-shaped, protected-prefixed, NOR a §9 rule 4 bare subscript (1-2
    uppercase letters or digits alone) -- without the subscript
    exception, `M-3/D` would be misread as a path (design §9 rule 4
    deliberately leaves this judgment unchanged for GENUINE paths like
    `docs/design/X.md`, whose segments are ordinary words)."""
    if "/" not in word:
        return False
    segments = word.split("/")
    if len(segments) < 2:
        return False
    return any(
        not (
            _BARE_ID_RE.match(seg)
            or seg.startswith(_PROTECTED_ID_PREFIXES)
            or _SUBSCRIPT_RE.match(seg)
            or _ID_BRANCH_PLACEHOLDER_RE.match(seg)
        )
        for seg in segments
    )


def _has_versioned_document_reference(text: str) -> bool:
    return bool(_VERSIONED_DOC_RE.search(text))


def _parens_has_provenance_tag(inner: str, real_paths: frozenset[str]) -> bool:
    if (
        _has_real_filename_reference(inner, real_paths)
        or _PROVENANCE_WORD_RE.search(inner)
        or _has_versioned_document_reference(inner)
    ):
        return True
    # The generic path-word fallback (design §9 rule 4: "パス語の判定は
    # 変えない") is for a directory-shaped chunk WITHOUT its own filename
    # candidate shape (e.g. extension-less "docs/R-5"). A filename
    # candidate (`{scratchpad}/...`, backtick span, `.ext`) was already
    # resolved -- as real or fake -- by the check above, so every such
    # span is blanked out FIRST (as one atomic unit, even a backtick span
    # with an internal wrap-join space, which `[,;\s]+`-splitting alone
    # would otherwise tear into two bogus path-shaped fragments) before
    # the remainder is split into chunks. Letting an unresolved fragment
    # of a non-real filename fall through here would make it count as a
    # tag anyway via this older, reality-blind path (§9 rule 2 must win).
    remainder = _sub_filename_candidates(inner, " ")
    for chunk in re.split(r"[,;\s]+", remainder):
        if _looks_like_path_word(chunk):
            return True
    return False


def _balanced_paren_spans(sentence: str) -> list[tuple[int, int]]:
    """design 9.2 rule 4 (nested parens, change set 0i): every BALANCED
    `(...)` pair in `sentence`, INCLUDING nested ones -- unlike the flat
    `\\(([^()]*)\\)` regex used elsewhere in this file, which only ever
    matches a pair with no further paren inside it, so a genuinely
    nested pair (e.g. `(see docs/design/X_V1.md §3 (D-4, WP-2))`) is
    found here even though only its INNERMOST pair is ever matched by
    that flat regex. A simple stack scan; an unmatched `(` or `)`
    (design 9.2 known constraint (a): 51 of 5,233 sentences at
    `f0637d9`) contributes no span for that character."""
    stack: list[int] = []
    spans: list[tuple[int, int]] = []
    for i, ch in enumerate(sentence):
        if ch == "(":
            stack.append(i)
        elif ch == ")" and stack:
            start = stack.pop()
            spans.append((start, i + 1))
    return spans


def _has_enclosing_tagged_paren(
    sentence: str, paren_start: int, paren_end: int, real_paths: frozenset[str]
) -> bool:
    """design 9.2 rule 4 (change set 0i, monitor ruling): does some OTHER
    paren pair in `sentence` that STRICTLY encloses `[paren_start,
    paren_end)` itself carry a §4.1 (4)/§9 rule 2 provenance tag,
    checked the SAME way a non-nested paren's own tag is
    (`_parens_has_provenance_tag`, over the enclosing pair's own full
    inner text, ID+branch pairs already merged away by the caller so no
    literal nested parens remain from those)? Known constraint (Z0i-6):
    scoped to `sentence` only, never across a sentence boundary."""
    for start, end in _balanced_paren_spans(sentence):
        if start < paren_start and end > paren_end:
            if _parens_has_provenance_tag(sentence[start + 1 : end - 1], real_paths):
                return True
    return False


# design §4.2 (5): the frozen, change-set-0-measured baseline (2026-09-14,
# both peers' `src/`: 0 hits), now detected via AST name resolution (v0.4
# review fix (f)) rather than a source-text regex, so it also catches
# `from inspect import getsource` + a bare `getsource(...)` call.
_DOCSTRING_DEPENDENT_BASELINE: frozenset[str] = frozenset()
_DOC_ACCESS_ATTRS: frozenset[str] = frozenset({"getdoc", "getsource", "getcomments"})

# design §4.2 (6): non-emptiness floor, counted across BOTH peers combined
# (never per peer). Change set 0 leaves this at 0; change set 1 raises it
# to 1 (work order §2.2, "触るファイル" table).
MIN_CH_IDS = 1

_ABBREVIATIONS: tuple[str, ...] = ("e.g.", "i.e.", "vs.", "...")
# design §4.1 (3) + v0.4 review fix (e), extended in review round 2 (P4):
# `.?!` need trailing whitespace to end a sentence (so a decimal point or
# ellipsis mid-sentence is not mistaken for one); `。` ends a sentence
# immediately, without needing trailing whitespace (Japanese prose rarely
# has any) -- AND, when one or more Japanese/Western closing brackets
# (`」』）)】`) immediately follow it, those stay attached to the sentence
# that just ended, not the next one (e.g. "「A。」B。" splits after "」",
# not right after "。", so the retained sentence is "「A。」" whole).
# Boundary text is captured (not just matched via lookbehind, which cannot
# be variable-width) so `split_sentences` can re-attach the punctuation
# and any closing brackets to the sentence that precedes them, while a
# paragraph break (`\n\n+`) attaches nothing.
_SENTENCE_BOUNDARY_RE = re.compile(r"([.?!]\s+|。[」』）)】]*\s*|\n\n+)")
_REQUIRED_SECTION_LINES: dict[str, re.Pattern[str]] = {
    "moved from": re.compile(r"^- moved from: `[^`]+`", re.MULTILINE),
    "parent commit": re.compile(r"^- parent commit: `[0-9a-f]{7,40}`", re.MULTILINE),
    "kind": re.compile(r"^- kind: (?:comment|docstring)\s*$", re.MULTILINE),
}
_HEADING_RE = re.compile(r"^## (CH-\d{4})\s*$", re.MULTILINE)
# design v0.4 ruling: a docstring that itself contains ``` needs a longer
# fence in the companion so its content is never mistaken for the closing
# fence -- the opening fence's own backtick run length (3 or more) is
# detected and the matching close must use that same length.
_FENCE_OPEN_RE = re.compile(r"^(`{3,})[^\n]*\n", re.MULTILINE)


# ---------------------------------------------------------------------------
# Block model (design D-2 "塊との対応"): a maximal same-indent run of `#`
# comment lines (blank-line-terminated), or a Module/Class/Function/
# AsyncFunction docstring. Correspondence between an old and a new block is
# always taken via CH-ID (v0.3), never by position.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Block:
    kind: str  # "comment" | "docstring"
    start_line: int
    end_line: int
    dedented: str  # full canonical text, AS ORIGINALLY WRITTEN (a trailing
    # recognized history-marker line, if any, stays IN this field -- it is
    # what a companion section's fenced block must byte-match when this is
    # an OLD block. Use `history_id`/`retained_text` for the NEW-side view).
    history_id: str | None
    retained_text: str  # `dedented` minus a trailing recognized marker
    # line, stripped. Empty when the block is either marker-free (nothing
    # moved) or fully moved (retained_text == "" and history_id is set).


def _is_excluded_standalone_comment(line: str, lineno: int) -> bool:
    """design §3 "対象外": shebang, PEP263 encoding declaration, and the
    `type: ignore` / `noqa` / `pragma` family are never part of a history
    block, on either side of a diff. A trailing/inline comment on a code
    line (`x = 1  # ...`) is excluded structurally already, by the caller
    only ever considering a line that STARTS with `#` after stripping
    leading whitespace (design v0.4 ruling)."""
    stripped = line.strip()
    if lineno == 1 and stripped.startswith("#!"):
        return True
    if lineno <= 2 and stripped.startswith("#") and "coding" in stripped and (
        "coding:" in stripped or "coding=" in stripped
    ):
        return True
    if re.match(r"^#\s*(type:\s*ignore\b|noqa\b|pragma\b)", stripped, re.IGNORECASE):
        return True
    return False


def _split_marker(kind: str, dedented: str) -> tuple[str | None, str]:
    lines = dedented.splitlines()
    if not lines:
        return None, ""
    last = lines[-1].strip()
    pat = _HASH_REF_RE if kind == "comment" else _DOC_HIST_LINE_RE
    m = pat.match(last)
    if not m:
        return None, dedented.strip()
    retained = "\n".join(lines[:-1]).strip()
    return m.group(1), retained


def _make_block(kind: str, start: int, end: int, dedented: str) -> Block:
    history_id, retained = _split_marker(kind, dedented)
    return Block(
        kind=kind,
        start_line=start,
        end_line=end,
        dedented=dedented,
        history_id=history_id,
        retained_text=retained,
    )


def extract_comment_blocks(source: str) -> list[Block]:
    lines = source.splitlines()
    blocks: list[Block] = []
    n = len(lines)
    i = 0
    while i < n:
        line = lines[i]
        stripped = line.strip()
        lineno = i + 1
        if stripped.startswith("#") and not _is_excluded_standalone_comment(line, lineno):
            indent = line[: len(line) - len(line.lstrip())]
            run = [line]
            start = lineno
            j = i + 1
            while j < n:
                nxt = lines[j]
                nxt_stripped = nxt.strip()
                nxt_indent = nxt[: len(nxt) - len(nxt.lstrip())]
                if (
                    nxt_stripped.startswith("#")
                    and nxt_indent == indent
                    and not _is_excluded_standalone_comment(nxt, j + 1)
                ):
                    run.append(nxt)
                    j += 1
                else:
                    break
            dedented = textwrap.dedent("\n".join(run)).strip("\n")
            blocks.append(_make_block("comment", start, j, dedented))
            i = j
        else:
            i += 1
    return blocks


def extract_docstring_blocks(source: str) -> list[Block]:
    tree = ast.parse(source)
    blocks: list[Block] = []
    doc_node_types = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    for node in ast.walk(tree):
        if not isinstance(node, doc_node_types):
            continue
        if not node.body:
            continue
        first = node.body[0]
        if not (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            continue
        # design v0.4 ruling: docstring provenance is matched on the value
        # AFTER `inspect.cleandoc` (i.e. Python's own docstring-indentation
        # convention), never on the raw source byte span -- this is that
        # single canonicalization point; every later comparison in this
        # file works from this `dedented` value, not from source bytes.
        dedented = inspect.cleandoc(first.value.value)
        start = first.lineno
        end = getattr(first, "end_lineno", start)
        blocks.append(_make_block("docstring", start, end, dedented))
    return blocks


def extract_all_blocks(source: str) -> list[Block]:
    return sorted(
        extract_comment_blocks(source) + extract_docstring_blocks(source),
        key=lambda b: b.start_line,
    )


# ---------------------------------------------------------------------------
# design §4.1 (3) preprocessing: "コメント塊は各行の # と先頭空白を除いて空白
# 1つで連結し、docstring は行を連結する". A content-less `#` line (or blank
# docstring line) is a paragraph break, preserved here as a blank line so
# `split_sentences` can also break there -- never on a bare line wrap.
# ---------------------------------------------------------------------------
# change set 0e (supervisor ruling, corrects change set 0d review round
# item 3): a line-wrap that splits an identifier/path/compound word mid-
# token must rejoin WITHOUT the usual single space, so the flattened text
# reads e.g. "control_main.py" / "violated_declaration" / "already-
# committed", never "control_main. py" / "violated_ declaration" /
# "already- committed" -- and the protected-reference / (4)/(6) machinery
# -- all of which run on this SAME flattened text -- sees one token, not
# two. The change-set-0d-era hypothesis that an ordinary hyphenated
# English compound (e.g. "confirmed-\ndestructive", "table-\nlevel")
# deliberately keeps its space was WRONG: real-corpus review (change set
# 3 re-review, 2026-09-14) found `postgres.py` itself already carrying
# the broken "confirmed- destructive" / "table- level" forms -- these are
# instances of the SAME bug, not a deliberately-spaced style. The rule is
# now general (§9e below), not scoped to ID-shaped splits.
_JOIN_EXTENSIONS = frozenset(
    {"py", "md", "sql", "json", "toml", "yaml", "yml", "txt", "sh", "tsv", "html", "js", "ts"}
)
_JOIN_EXTENSION_RE = re.compile(r"[A-Za-z]+")


def _is_word_char(c: str) -> bool:
    return c.isalnum() or c == "_"


_CJK_PUNCTUATION = "、。「」『』（）〔〕【】・…〜々〇！？：；［］〈〉《》"


def _is_cjk_char(c: str) -> bool:
    """change set 0h, predicate B condition 9: is `c` a CJK character --
    Han (`\\u4e00`-`\\u9fff`, plus CJK Unified Ideographs Extension A
    `\\u3400`-`\\u4dbf`, change set 5), Hiragana (`\\u3040`-`\\u309f`),
    Katakana (fullwidth `\\u30a0`-`\\u30ff`, plus halfwidth
    `\\uff66`-`\\uff9f`, change set 5), or one of the CJK punctuation
    marks (`、` `。` the bracket/ellipsis-shaped marks that appear
    inside Japanese prose, the iteration mark `々` and the ideographic
    zero `〇` (change set 5, both live in the same CJK Symbols and
    Punctuation block as `、`/`。`), and the fullwidth punctuation
    `！？：；［］〈〉《》` (change set 5) -- all of `_CJK_PUNCTUATION`)
    -- used ONLY to detect a line-wrap boundary that split two CJK
    characters with no space in the basis, since Japanese prose carries
    no spaces between words at all and a line wrap there must always
    rejoin with zero space, never the single space `_join_wrapped_lines`
    inserts by default for an ordinary (English) word boundary.
    Deliberately NOT extended to fullwidth alphanumerics (design v0.14,
    supervisor ruling 2026-09-15): those were not part of the ruling's
    scope. Known constraint (design v0.14 §9): normalization strips a
    space between two CJK characters wherever it appears, not only at a
    basis line wrap, so adding or removing an in-line space between CJK
    characters is invisible to the comparison."""
    if not c:
        return False
    if c in _CJK_PUNCTUATION:
        return True
    cp = ord(c)
    return (
        0x4E00 <= cp <= 0x9FFF  # Han (CJK Unified Ideographs)
        or 0x3400 <= cp <= 0x4DBF  # Han, CJK Unified Ideographs Extension A (change set 5)
        or 0x3040 <= cp <= 0x309F  # Hiragana
        or 0x30A0 <= cp <= 0x30FF  # Katakana (fullwidth)
        or 0xFF66 <= cp <= 0xFF9F  # Katakana (halfwidth, change set 5)
    )


def _joined_identifier_at_boundary(accumulated: str, next_line: str) -> str:
    """The candidate CamelCase identifier formed by concatenating the
    identifier-shaped run ending `accumulated` with the identifier-
    shaped run starting `next_line` -- used ONLY by predicate B's rule
    5 to check against `_tracked_identifier_set`."""
    left_m = re.search(r"[A-Za-z_][A-Za-z0-9_]*$", accumulated)
    right_m = re.search(r"^[A-Za-z0-9_]*", next_line)
    left = left_m.group(0) if left_m else ""
    right = right_m.group(0) if right_m else ""
    return left + right


def _is_join_sensitive_boundary(accumulated: str, next_line: str, identifier_set: frozenset[str]) -> bool:
    """change set 0e, predicate B (supervisor ruling 2026-09-15, final
    unification): is the whitespace/line-wrap BETWEEN `accumulated`
    (everything flattened so far in this paragraph) and `next_line`
    actually spurious -- i.e. should this boundary join with ZERO space
    instead? THE SAME predicate is used for normalization (comparison),
    detection, and joining a fresh multi-line wrap -- no separate
    broader/narrower variants (an earlier round's split between a broad
    "collapse all backtick-internal whitespace" normalization and a
    narrow detection rule produced both false greens, e.g. `` `conn.
    transaction()` ``/`self. _rate_windows` staying undetected because
    normalization silently absorbed the mismatch, and false reds, e.g.
    `` `except FoundationError` ``/`is None` being forced together
    because a bare lowercase-to-uppercase check had no way to tell a
    genuine CamelCase split from two ordinary separate words). Checked
    against the text immediately either side of the boundary, and
    against whether the boundary sits inside an OPEN backtick span (odd
    backtick count in `accumulated`). Nine triggers:
    (1) `accumulated` ends `<word char>_` and `next_line` starts with a
        word character -- regardless of backtick state;
    (2) `accumulated` ends `<word char>-` (a SINGLE hyphen, not part of
        `--`) and `next_line` starts with a word character --
        regardless of backtick state;
    (3) INSIDE an open backtick span, `accumulated` ends `.` and
        `next_line` starts with a word character -- backtick content is
        code, where `.` is always attribute/method/path access, never a
        sentence-ending period;
    (4) OUTSIDE any backtick span, `accumulated` ends `.` and
        `next_line` starts with one of `_JOIN_EXTENSIONS` -- a file
        extension split right after the dot, deliberately NOT triggered
        by an ordinary sentence-final `.` followed by a new sentence;
    (5) INSIDE an open backtick span, `accumulated` ends with a
        LOWERCASE English letter and `next_line` starts with an
        UPPERCASE English letter, AND ONLY IF the identifier formed by
        joining the two sides (`_joined_identifier_at_boundary`) is
        itself a member of `identifier_set` (every identifier-shaped
        token the basis tree's own tracked `src`/`spec`/`docs` files
        contain, from `_tracked_identifier_set`) -- a CamelCase/
        PascalCase split (`` `Application Cell.transact` `` ->
        `` `ApplicationCell.transact` `` since `ApplicationCell` is a
        real class in this codebase). The identifier-set guard is what
        keeps two genuinely separate words that merely happen to sit
        lowercase-then-uppercase across a wrap -- `id ASC`, `except
        FoundationError`, `is None` -- from being folded into a token
        (`idASC`, `exceptFoundationError`, `isNone`) that never actually
        occurs as one identifier anywhere in the tree: none of those
        joined forms are real tracked identifiers, so rule 5 does not
        fire for them and the space stays REQUIRED, exactly like any
        other real word boundary (`` `SHARE MODE` ``, `` `foo bar` ``,
        an ALL-CAPS pair or two lowercase words, which never satisfy
        "lowercase-then-uppercase" in the first place).
    (6) `accumulated` ends `/`, the character immediately BEFORE that
        `/` is NOT a space (0f Item 2 fix, supervisor ruling
        2026-09-15: a genuinely SPACED path-like expression such as
        `a / b` must keep its space when wrapped right after the `/`,
        not be joined with zero space -- only a `/` that itself sits
        directly against the preceding text, with no space before it,
        is a real path/module separator), and `next_line` starts with
        a word character OR a backtick -- regardless of backtick state
        (a path/module split right after `/`, e.g. `` `cell.py`/
        `backend_sqlite.py` `` or `docs/design/SOME_FILE.md`);
    (7) INSIDE an open backtick span, `accumulated` ends `(`, `[`, or
        `=`, the character immediately BEFORE that is a word character
        or `(`/`[` (this is what excludes an ordinary spaced assignment
        like `a = b`, where the character right before `=` is a space,
        not a word character or bracket), and `next_line` starts with
        any NON-whitespace character -- a call/subscript/kwarg opening
        split right after the punctuation (`` `HttpService(
        ...)` ``, `` `role="audit"` ``);
    (8) `accumulated` ends with a backtick that OPENS a span (i.e. the
        count of backticks in `accumulated`, INCLUDING this one, is
        ODD) and `next_line` starts with any NON-whitespace character
        -- the wrap falls immediately after the opening backtick
        itself, before any content (`` `
        contract_field_types` `` -> `` `contract_field_types` ``).
        Deliberately excludes a CLOSING backtick (even count) followed
        by ordinary English, a quote mark, `*` (markdown emphasis)
        followed by English, an `=`-rule separator line (the character
        before a `=` that is itself part of a `====` run is another
        `=`, not a word character or bracket, so rule 7 does not fire),
        and a `<->` arrow (`-` there is preceded by `<`, not a word
        character, so rule 2 already does not fire).
    (9) change set 0h: `accumulated` ends with a CJK character (Han,
        Hiragana, Katakana, or a CJK punctuation mark such as `、`/`。`
        -- `_is_cjk_char`) AND `next_line` starts with a CJK character
        -- regardless of backtick state. Japanese prose has no spaces
        between words at all, so a line wrap that falls between two CJK
        characters (`いかなる` wrapped as `い` / `かなる`) must always
        rejoin with zero space; the single-space default that rules
        1-8 leave in place for an ordinary English word boundary is
        itself the corruption here (`い かなる`, `無効化 中`).
    Deliberately NOT a trigger: any other backtick-internal boundary
    with no marker at all (a multi-word SQL/expression fragment quoted
    whole in backticks, e.g. `` `<predicate> AND _r2db_revision::text =
    $expected` `` wrapped mid-phrase) -- confirmed by the requirement
    that `--base HEAD` stays green on unchanged, already-correct
    source."""
    if not accumulated or not next_line:
        return False
    inside_backticks = accumulated.count("`") % 2 == 1
    last = accumulated[-1]
    prev = accumulated[-2] if len(accumulated) >= 2 else ""
    nxt = next_line[0]
    if last == "_" and _is_word_char(prev) and _is_word_char(nxt):
        return True
    if last == "-" and prev != "-" and _is_word_char(prev) and _is_word_char(nxt):
        return True
    if last == "." and inside_backticks and _is_word_char(nxt):
        return True
    if last == "." and not inside_backticks:
        m = _JOIN_EXTENSION_RE.match(next_line)
        if m and m.group(0).lower() in _JOIN_EXTENSIONS:
            return True
    if inside_backticks and last.isalpha() and last.islower() and nxt.isalpha() and nxt.isupper():
        joined = _joined_identifier_at_boundary(accumulated, next_line)
        if joined in identifier_set:
            return True
    if last == "/" and prev != " " and (_is_word_char(nxt) or nxt == "`"):
        return True
    if inside_backticks and last in "([=" and (_is_word_char(prev) or prev in "([") and nxt != " ":
        return True
    if last == "`" and inside_backticks and nxt != " ":
        return True
    if _is_cjk_char(last) and _is_cjk_char(nxt):
        return True
    return False


def _join_wrapped_lines(group: list[str], identifier_set: frozenset[str]) -> str:
    result = group[0]
    for line in group[1:]:
        if _is_join_sensitive_boundary(result, line, identifier_set):
            result += line
        else:
            result += " " + line
    return result


def _comment_line_groups(text: str) -> list[list[str]]:
    """Paragraphs of per-line content for a comment block -- the SAME
    per-line stripping `_flatten_comment` uses, factored out so change
    set 0e's detection pass (`find_broken_line_wrap_joins`) walks
    line-by-line boundaries identically to how flattening joins them.

    change set 0g review round 2 (supervisor ruling 2026-09-15): a
    Sphinx-style `#:`-prefixed line (`#: some attribute doc`) has its
    OWN two-character line-start marker, `#:`, not just `#` -- stripping
    only the `#` left a stray leading `:` (plus, previously, one space)
    behind as if it were CONTENT, e.g. "#: this was inlined" flattening
    to ": this was inlined" instead of "this was inlined". Joined into a
    single sentence with a preceding line, that leftover `:` lands mid-
    sentence ("... : previously inlined") -- change set 4's `ops.py`
    CH-0321 compaction did exactly this, and went undetected because the
    SAME (buggy) stripping was applied to the companion's own basis text
    too, so both sides carried the identical stray `: ` and matched each
    other. `#:` is recognized ONLY as a line-start marker (a bare `#:`
    appearing mid-line, inside otherwise-plain content, is untouched --
    it is not this block's own comment-prefix at all)."""
    groups: list[list[str]] = [[]]
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#:"):
            content = stripped[2:]
        elif stripped.startswith("#"):
            content = stripped[1:]
        else:
            content = stripped
        if content.startswith(" "):
            content = content[1:]
        content = content.strip()
        if content == "":
            if groups[-1]:
                groups.append([])
        else:
            groups[-1].append(content)
    return [g for g in groups if g]


def _is_colon_style_block(dedented: str) -> bool:
    """change set 0g review round 2 (supervisor ruling 2026-09-15):
    detects a Sphinx-style `#:`-prefixed comment block -- True only when
    the block has at least one non-blank line and EVERY such line starts
    with the two-character `#:` marker (not merely `#`). A block mixing
    `#:` and plain `#` lines is treated as NOT colon-style (the safer,
    ambiguous-favors-no default). Only meaningful for `kind == "comment"`
    text (a docstring has no `#` at all, so it is never colon-style)."""
    lines = [ln for ln in dedented.splitlines() if ln.strip()]
    if not lines:
        return False
    return all(ln.strip().startswith("#:") for ln in lines)


def _flatten_comment(text: str, identifier_set: frozenset[str] = frozenset()) -> str:
    return "\n\n".join(_join_wrapped_lines(g, identifier_set) for g in _comment_line_groups(text))


def _docstring_line_groups(text: str) -> list[list[str]]:
    """Paragraphs of per-line content for a docstring block -- see
    `_comment_line_groups`."""
    groups: list[list[str]] = [[]]
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == "":
            if groups[-1]:
                groups.append([])
        else:
            groups[-1].append(stripped)
    return [g for g in groups if g]


def _flatten_docstring(text: str, identifier_set: frozenset[str] = frozenset()) -> str:
    return "\n\n".join(_join_wrapped_lines(g, identifier_set) for g in _docstring_line_groups(text))


def _line_groups(kind: str, text: str) -> list[list[str]]:
    return _comment_line_groups(text) if kind == "comment" else _docstring_line_groups(text)


def find_broken_line_wrap_joins(
    kind: str, basis_dedented: str, new_dedented: str, identifier_set: frozenset[str] = frozenset()
) -> list[tuple[str, str]]:
    """change set 0e (detection): walk `basis_dedented` (the pristine
    companion text, or the immediate basis block's own dedented text)
    paragraph by paragraph, exactly as `_flatten_comment`/
    `_flatten_docstring` do, and find every line-wrap boundary predicate
    B (`_is_join_sensitive_boundary`) says must join with ZERO space (a
    genuine mid-token wrap in the basis). For each, build the CORRECT
    (zero-space) and BROKEN (one-space) short context strings and check
    whether `new_dedented` -- the current code, wherever it stands in
    its own reduction -- contains the BROKEN form as a literal
    substring. A hit means somewhere along the way (a rewrite, a partial
    reduction) the mid-token wrap got flattened with a naive single
    space instead of zero, corrupting the identifier/path/word.

    change set 5 fix (supervisor ruling 2026-09-15): for a boundary
    triggered ONLY by condition 9 (both `accumulated[-1]` and `line[0]`
    are CJK, `_is_cjk_char`), the context tokens are the single
    characters on each side, `ltok = accumulated[-1]` / `rtok =
    line[0]`, NOT the full `\\S+` run either side of the boundary. A
    `\\S+` run can span an entire CJK sentence with no ASCII space
    inside it at all, so a SEPARATE, unrelated space corruption
    elsewhere in that same run (not at this boundary) breaks the
    literal-substring match for the whole run and hides a genuine
    condition-9 break at this boundary (r2db `control_plane.py:1380`,
    CH-0281: the run after the boundary, `line`, contains a second,
    later space after `。` that has nothing to do with THIS boundary;
    matching that whole run as one literal string failed to find the
    boundary's own broken join, `超過 は`, even though it was present).
    The single-character short context is only ever used for a pure
    condition-9 boundary; every other condition (1-8) keeps the
    original `\\S+` token context, since those already anchor on
    ASCII/backtick punctuation that does not suffer from this failure
    mode. Returns (correct, broken) pairs actually found broken; empty
    if none."""
    hits: list[tuple[str, str]] = []
    for group in _line_groups(kind, basis_dedented):
        accumulated = group[0]
        for line in group[1:]:
            if _is_join_sensitive_boundary(accumulated, line, identifier_set):
                if _is_cjk_char(accumulated[-1]) and _is_cjk_char(line[0]):
                    ltok, rtok = accumulated[-1], line[0]
                else:
                    ltok_m = re.search(r"\S+$", accumulated)
                    rtok_m = re.search(r"^\S+", line)
                    ltok = ltok_m.group(0) if ltok_m else accumulated
                    rtok = rtok_m.group(0) if rtok_m else line
                correct = ltok + rtok
                broken = ltok + " " + rtok
                if broken in new_dedented:
                    hits.append((correct, broken))
                accumulated += line
            else:
                accumulated += " " + line
    return hits


def _normalize_join_whitespace(flat_text: str, identifier_set: frozenset[str] = frozenset()) -> str:
    """change set 0e (comparison normalization): applied to ALREADY-
    flattened text (single space within a paragraph, a blank line --
    i.e. "\\n\\n" -- between paragraphs), collapse a SINGLE SPACE at
    each boundary predicate B (`_is_join_sensitive_boundary` -- the SAME
    predicate used for detection and for a fresh join, per the
    2026-09-15 unification ruling) recognizes. This makes a "broken"
    form (a stray single space already baked in as literal text -- from
    an older round's own flatten-time mistake, frozen in git history,
    or a companion/source edited by hand) and its "fixed" (zero-space)
    form compare EQUAL for every existing derivability check, while a
    genuine word boundary (`id ASC`, `except FoundationError`) is left
    alone -- an over-eager over-join of one of THOSE now correctly
    fails to compare equal to the basis, since B is false there and the
    space is required. Never touches a paragraph break: only a literal
    single SPACE character is ever a removal candidate."""
    out: list[str] = []
    i = 0
    n = len(flat_text)
    while i < n:
        ch = flat_text[i]
        if ch == " " and out and _is_join_sensitive_boundary("".join(out), flat_text[i + 1 :], identifier_set):
            i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _flatten(kind: str, text: str, identifier_set: frozenset[str] = frozenset()) -> str:
    flat = _flatten_comment(text, identifier_set) if kind == "comment" else _flatten_docstring(text, identifier_set)
    return _normalize_join_whitespace(flat, identifier_set)


def split_sentences(flattened_text: str) -> list[str]:
    """Splits already-flattened text (single spaces within a paragraph,
    `\\n\\n` between paragraphs) into sentences. Splits only on a sentence-
    final punctuation mark (`.?!` need trailing whitespace; `。` splits
    immediately, design v0.4, and keeps any immediately-following closing
    bracket(s) `」』）)】` attached to the sentence that just ended -- P4,
    review round 2) or a paragraph break -- never on a bare line wrap.
    Abbreviations and backtick code spans are protected so their internal
    periods never split a sentence.

    change set 0h (bug fix): backtick spans are hidden BEFORE abbreviation
    substitution runs, not after. Hiding abbreviations first let an
    abbreviation textually INSIDE a backtick span (e.g. the literal `...`
    in `` `cursor.execute(...)` ``) get replaced by its own `\\x00A{n}\\x00`
    placeholder first; the backtick-span regex then captured that
    placeholder AS PART OF the span's "original" text, so `restore()`'s
    single left-to-right pass restored the B-token back to text that
    still contained an unrestored `\\x00A{n}\\x00` sequence (A-tokens are
    restored earlier in insertion order, before the B-token substitution
    that reintroduces one). Hiding backtick spans first makes their
    content opaque to the abbreviation pass entirely, so nothing is ever
    substituted inside a span in the first place -- restoring the B-token
    later yields the untouched original bytes, `...` included."""
    protected = flattened_text
    placeholders: dict[str, str] = {}
    for idx, span in enumerate(re.findall(r"`[^`]*`", protected)):
        token = f"\x00B{idx}\x00"
        placeholders[token] = span
        protected = protected.replace(span, token, 1)
    for idx, abbr in enumerate(_ABBREVIATIONS):
        token = f"\x00A{idx}\x00"
        placeholders[token] = abbr
        protected = protected.replace(abbr, token)

    # `_SENTENCE_BOUNDARY_RE` is used with a capturing group, so
    # `re.split` interleaves [text, boundary, text, boundary, ..., text].
    # A `.?!`/`。` boundary's punctuation (and any closing brackets) is
    # re-attached to the sentence that precedes it; a paragraph-break
    # boundary (`\n\n+`) attaches nothing and simply ends the sentence.
    raw_parts = _SENTENCE_BOUNDARY_RE.split(protected)
    sentences: list[str] = []
    buf = ""
    for i, part in enumerate(raw_parts):
        if i % 2 == 0:
            buf += part
            continue
        if part.startswith("\n"):
            sentences.append(buf)
            buf = ""
        else:
            buf += part.rstrip()
            sentences.append(buf)
            buf = ""
    if buf:
        sentences.append(buf)

    def restore(s: str) -> str:
        for token, orig in placeholders.items():
            s = s.replace(token, orig)
        return s

    return [restore(p).strip() for p in sentences if restore(p).strip()]


# design §9 rule 1 (v0.6, change set 0c): the multi-word history tokens
# that need pre-merging into ONE unit before any whitespace-based word
# split (`_PAREN_SPLIT_RE` / `_label_word_tokens`'s `.split()`) -- without
# this, "monitor ruling" would be tested word-by-word ("monitor" alone,
# "ruling" alone), and neither half matches the 2-word pattern on its own.
# This is the exact same subset of `_HISTORY_TOKEN_PATTERNS` whose source
# pattern contains a literal space.
_MULTIWORD_HISTORY_TOKEN_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    pat for pat in _HISTORY_TOKEN_PATTERNS if " " in pat.pattern
)

# design §9 rule 4 (v0.6, change set 0c): a `/`-joined ID sequence (`M-3/D`)
# splits into separate IDs; a bare 1-2-uppercase-letter or digits-only
# fragment counts as an ID too WHEN it continues a real (unprotected) ID
# across a `/` (so `TCP/IP`, `read/write`, `enable/disable` -- none of
# which start with a hyphen-digit ID -- never match). Protected IDs
# (`SI-08/R-5`) are deliberately excluded from the base-ID alternative, so
# they stay fully protected via the existing protected-prefix rule.
_SLASH_ID_CONTINUATION_RE = re.compile(
    r"\b(?:(?!" + "|".join(re.escape(p) for p in _PROTECTED_ID_PREFIXES) + r")[A-Z]{1,6}-\d+[a-z]?)"
    r"((?:/(?:[A-Z]{1,2}|\d+))+)\b"
)


def _slash_id_subscripts(text: str) -> frozenset[str]:
    subs: set[str] = set()
    for m in _SLASH_ID_CONTINUATION_RE.finditer(text):
        subs.update(part for part in m.group(1).split("/") if part)
    return frozenset(subs)


# design §3 exclusion 2 ("出所を明示した参照だけ" -- SI-/C-/CCR- protected):
# `SI-08/R-5` needs NO dedicated slash-group protection here -- `SI-08`
# already blocks its OWN removal via the ordinary protected-prefix check
# (unconditionally, regardless of `has_provenance_tag`), and `R-5` was
# never swept into `_slash_id_subscripts` for this text (that regex's
# base-ID alternative excludes a protected prefix), so `R-5` falls through
# to the plain bare-ID rule and stays independently removable -- exactly
# design §9 rule 4's own boundary example ("SI-08/R-5 → 保護参照を含むので
# 消せない" describes the GROUP being excluded from rule 4's own new
# slash-splitting shortcut, not a change to R-5's pre-existing, correct,
# stand-alone removability).

# design §9 rule 3 (v0.6, change set 0c): once (4) has removed >=1 word
# from a parenthetical, if ONLY provenance KIND words remain (design /
# contract / spec / roadmap / ruling / review, case-insensitive), the
# whole parenthetical goes too -- but a parenthetical that held ONLY kind
# words from the start (`(design)`) is never touched by this.
_KIND_WORD_RE = re.compile(r"^(?:design|contract|spec|roadmap|ruling|review)$", re.IGNORECASE)


# ---------------------------------------------------------------------------
# design §4.1 (4): mechanical parenthetical-content removal (v0.4 review
# fix (b)): a parenthetical's content is split into WORDS on `, ` `/` `;`
# and plain whitespace -- so "see SI-08 WP-3" is 3 words, not 1 -- and only
# a word that is ENTIRELY a §4.1 (5) history token, a bare ID with no
# provenance tag co-located in the same parens, a NON-real filename (§9
# rule 2), or a `/`-continuation ID subscript (§9 rule 4), may be removed.
# Original separators are preserved and only the removed words (plus one
# adjacent separator each) disappear -- the rest of the parenthetical is
# untouched byte-for-byte, never rejoined with a different separator.
# ---------------------------------------------------------------------------
def _premerge_tokens(text: str, real_paths: frozenset[str]) -> tuple[str, dict[str, tuple[str, bool]]]:
    """Merges, into single opaque placeholders BEFORE any `/`/whitespace
    split, in this order: (1) a filename candidate (backtick span, or a
    bare `{...}/...`- or `.ext`-suffixed token) -- removable (non-
    content) unless it is REAL (§9 rule 2); (2) a multi-word history
    token (§9 rule 1); (3) an ID (bare or a §4.1 (5) token such as `WP-`)
    immediately followed by a parenthesized digit/roman-numeral branch
    number. All three are shared, byte-identical, between §4.1 (4)'s
    parenthetical reduction and §4.1 (6)'s label word-count. Returns
    (working_text, {placeholder: (original_text, is_content)})."""
    placeholders: dict[str, tuple[str, bool]] = {}

    def make(original: str, is_content: bool) -> str:
        tok = f"\x00X{len(placeholders)}\x00"
        placeholders[tok] = (original, is_content)
        return tok

    working = _sub_filename_candidates(
        text, lambda matched: make(matched, _is_real_filename_candidate(matched, real_paths))
    )
    for pat in _MULTIWORD_HISTORY_TOKEN_PATTERNS:
        working = pat.sub(lambda m: make(m.group(0), False), working)
    working = _ID_BRANCH_RE.sub(lambda m: make(m.group(0), False), working)
    return working, placeholders


def _is_removable_word(
    word: str, has_provenance_tag: bool, real_paths: frozenset[str],
    slash_subscripts: frozenset[str] = frozenset(),
) -> bool:
    word = word.strip()
    if not word:
        return False
    for pat in _HISTORY_TOKEN_PATTERNS:
        if pat.search(word):
            return True
    if word in slash_subscripts:
        return True
    if _is_filename_candidate_fullmatch(word) and not _is_real_filename_candidate(word, real_paths):
        return True
    if has_provenance_tag:
        return False
    if _BARE_ID_RE.match(word) and not word.startswith(_PROTECTED_ID_PREFIXES):
        return True
    return False


_PAREN_SPLIT_RE = re.compile(r"([,/;\s]+)")


# design v0.7 supervisor ruling (change set 0c follow-up, refined a
# second time): every operation in §4.1 (3)/(4)/(6) and §9 rules 1-4 is a
# PERMISSION ("してよい"), never an obligation -- an earlier maximal-
# reduction helper (deleted as dead code with no callers, F5 code-review
# fix) computed ONE particular (maximal) reduction; the functions below
# instead answer "is THIS specific candidate sentence one of the
# reductions a human editor could legally have stopped at". The FIRST
# version of this (kept only in history) enumerated every subset of a
# parenthetical's removable words -- a combinatorial blow-up capped at a
# fixed word count, which then wrongly rejected a correct PARTIAL
# reduction in a long, multi-parenthetical sentence once that cap was
# exceeded. The supervisor ruling that followed requires instead: each
# independent SITE (each parenthetical; the leading label) is judged on
# its own -- "left untouched" or "one of its own allowed reductions" --
# and the candidate sentence is verified against the combination those
# per-site choices imply by a single LEFT-TO-RIGHT scan (no enumeration
# of combinations across sites, and so no cap on sentence length).
def _paren_words_removable(
    inner: str, real_paths: frozenset[str], id_branch_placeholders: dict[str, str],
    enclosing_tag: bool = False, preceded_by_review: bool = False,
) -> list[tuple[str | None, str, bool]]:
    """The ordered (prev_separator, word_text, is_removable) sequence for
    one `(...)`'s content -- `prev_separator` is the exact separator text
    (restored) immediately preceding this word in the ORIGINAL content
    (`,` / `/` / `;` / whitespace, possibly combined, e.g. `", "`), or
    None for the very first word. word_text is restored to its original
    spelling (filename candidates, multi-word history tokens, and
    id+branch pairs un-merged). Removing a word takes its OWN preceding
    separator with it (design §4.1 (4)'s original word+adjacent-separator
    deletion mechanic) -- kept words must reproduce their ORIGINAL
    preceding separator exactly UNLESS they end up first in the output.

    `enclosing_tag` (design 9.2 rule 4, change set 0i, monitor ruling):
    True when some OTHER paren pair enclosing THIS one, in the same
    sentence, itself carries a provenance tag (`_has_enclosing_tagged_paren`,
    computed once per match by the caller, `_sentence_reachable`) -- an
    ID+branch pair inside an untagged paren that is itself inside a
    tagged one is still protected, the tag reaching inward exactly the
    way it would if the words were not nested at all.

    `preceded_by_review` (design 9.2 rule 1, Z0i-1 (B), change set 0i;
    F2 code-review fix, M1): True when a match of the SAME shared
    `_REVIEW_FID_TOKEN_RE` pattern's own `(F-n)` alternative ends flush
    with THIS paren's own close -- i.e. this paren IS that match's
    `(F-n)` tail (computed by the caller) -- a bare F-ID that is this
    paren's ENTIRE content is a removable history token in that case,
    the same shared pattern gives the in-parens "review F-n"/"review
    round F-n" forms."""
    has_tag = _parens_has_provenance_tag(inner, real_paths) or enclosing_tag
    slash_subscripts = _slash_id_subscripts(inner)
    working, placeholders = _premerge_tokens(inner, real_paths)
    parts = _PAREN_SPLIT_RE.split(working)

    def restore(s: str) -> str:
        for tok, (orig, _is_content) in placeholders.items():
            s = s.replace(tok, orig)
        for tok, orig in id_branch_placeholders.items():
            s = s.replace(tok, orig)
        return s

    def is_removable(token: str) -> bool:
        if token in id_branch_placeholders:
            # design 9.2 rule 4 (change set 0i, monitor ruling; F6
            # code-review fix): a bare ID + branch-number pair
            # ("D-5(ii)") is protected exactly like a lone bare ID
            # would be, when this paren (or one enclosing it) carries a
            # tag; a history-token + branch pair ("WP-6d (ii)") stays
            # removable regardless -- told apart from a bare ID via
            # `_ID_BRANCH_RE`'s own two NAMED alternatives (`history_id`
            # vs `bare_id`), re-matched against the ORIGINAL merged
            # text here, rather than a duplicated `"WP-"` literal proxy.
            if _ID_BRANCH_RE.fullmatch(id_branch_placeholders[token]).group("history_id"):
                return True
            return not has_tag
        if token in placeholders:
            _orig, is_content = placeholders[token]
            return not is_content
        if preceded_by_review and re.fullmatch(r"F-\d+[a-z]?", token.strip(), re.ASCII):
            return True
        return _is_removable_word(token, has_tag, real_paths, slash_subscripts)

    words: list[tuple[str | None, str, bool]] = []
    for i in range(0, len(parts), 2):
        if parts[i].strip():
            prev_sep = restore(parts[i - 1]) if i > 0 else None
            words.append((prev_sep, restore(parts[i]).strip(), is_removable(parts[i])))
    return words


def _paren_target_pairs(
    target_inner: str, real_paths: frozenset[str]
) -> list[tuple[str | None, str]] | None:
    """The (prev_separator, word_text) sequence for a CANDIDATE (already
    real, restored) parenthetical's inner text, tokenized the SAME way
    `_paren_words_removable` tokenizes the original (pre-merging filename
    candidates / multi-word history tokens / id+branch pairs into one
    atomic word each, so e.g. a backtick path containing "/" compares as
    ONE word, not shattered by a naive comma/slash/whitespace split).
    Returns None if `target_inner` has a DANGLING separator at its very
    start or end (no word on that side) -- always invalid, regardless of
    word content, since a valid reduction never leaves an orphaned
    separator behind (design review: T3/T4, e.g. "(R-5, SI-08)" ->
    "(, SI-08)" or "(M-3/D)" -> "(/D)")."""
    working, placeholders = _premerge_tokens(target_inner, real_paths)
    parts = _PAREN_SPLIT_RE.split(working)
    if not parts or not parts[0].strip() or not parts[-1].strip():
        return None

    def restore(s: str) -> str:
        for tok, (orig, _is_content) in placeholders.items():
            s = s.replace(tok, orig)
        return s

    pairs: list[tuple[str | None, str]] = []
    for i in range(0, len(parts), 2):
        if not parts[i].strip():
            return None  # a separator-only slot in the MIDDLE -- malformed
        prev_sep = restore(parts[i - 1]) if i > 0 else None
        pairs.append((prev_sep, restore(parts[i]).strip()))
    return pairs


def _paren_span_reachable(
    leading_ws: str, inner: str, candidate_span: str, real_paths: frozenset[str],
    id_branch_placeholders: dict[str, str],
    enclosing_tag: bool = False, preceded_by_review: bool = False,
) -> bool:
    """Is `candidate_span` (either "", the untouched `leading_ws(inner)`,
    or some `leading_ws(reduced inner)`) one allowed outcome for this one
    `(...)`? A single linear pass over this parenthetical's own words --
    no subset enumeration, so no length limit. `inner` may still contain
    RAW id+branch placeholders (needed by `_paren_words_removable`'s own
    word classification); `candidate_span` is always real, restored text,
    so the untouched-original comparison must restore `inner` too."""
    restored_inner = inner
    for tok, orig in id_branch_placeholders.items():
        restored_inner = restored_inner.replace(tok, orig)
    original_full = leading_ws + "(" + restored_inner + ")"
    if candidate_span == original_full:
        return True
    words = _paren_words_removable(
        inner, real_paths, id_branch_placeholders, enclosing_tag, preceded_by_review
    )
    if not words:
        return False
    if candidate_span == "":
        # design §9 rule 3: ONLY for a parenthetical where (4) already
        # removed >=1 word ("(4) で語が減った括弧に限り") -- a parens that
        # held nothing but kind words from the START (nothing removable at
        # all) must stay untouched, never swept to "".
        removed_any = any(removable for _sep, _w, removable in words)
        remaining = [w for _sep, w, removable in words if not removable]
        if not remaining:
            return removed_any
        if not removed_any:
            return False
        return all(_KIND_WORD_RE.match(w) for w in remaining)
    if not (candidate_span.startswith(leading_ws + "(") and candidate_span.endswith(")")):
        return False
    target_inner = candidate_span[len(leading_ws) + 1 : -1]
    # Tokenize `target_inner` the SAME way `_paren_words_removable` tokenized
    # the original `inner` (pre-merging filename candidates / multi-word
    # history tokens / id+branch pairs into one atomic word each) AND
    # track separators, not just words: a kept word must reproduce its
    # OWN original preceding separator exactly (unless it ends up first),
    # and a dangling separator with no word on one side is never valid
    # (design review round: T1-T4).
    target_pairs = _paren_target_pairs(target_inner, real_paths)
    if target_pairs is None:
        return False
    j = 0
    for prev_sep, word, removable in words:
        if j < len(target_pairs) and target_pairs[j][1] == word and (
            j == 0 or target_pairs[j][0] == prev_sep
        ):
            j += 1
        elif removable:
            continue
        else:
            return False
    return j == len(target_pairs)


def _sentence_reachable(sentence: str, target: str, real_paths: frozenset[str]) -> bool:
    """Is `target` reachable from `sentence` by, independently at each
    `(...)` site, leaving it untouched or applying one of its own allowed
    reductions (§4.1 (4) / §9 rules 1-4, each a permission -- v0.7
    supervisor ruling)? Text OUTSIDE any parenthetical is never reduced
    (rule 4 is scoped to parenthetical content only) and so must match
    `target` verbatim; each parenthetical's own span in `target` is
    located via the FIXED, literal text immediately following it (no
    combination search across independent sites)."""
    id_branch_placeholders: dict[str, str] = {}

    def merge_id_branch(m: re.Match[str]) -> str:
        tok = f"\x00Y{len(id_branch_placeholders)}\x00"
        id_branch_placeholders[tok] = m.group(0)
        return tok

    working_sentence = _ID_BRANCH_RE.sub(merge_id_branch, sentence)
    matches = list(re.finditer(r"(\s?)\(([^()]*)\)", working_sentence))

    def restore_text(s: str) -> str:
        for tok, orig in id_branch_placeholders.items():
            s = s.replace(tok, orig)
        return s

    texts: list[str] = []
    cursor = 0
    for m in matches:
        texts.append(restore_text(working_sentence[cursor : m.start()]))
        cursor = m.end()
    texts.append(restore_text(working_sentence[cursor:]))

    pos = 0
    for i, txt in enumerate(texts[:-1]):
        if not target.startswith(txt, pos):
            return False
        pos += len(txt)
        leading_ws, inner = matches[i].group(1), matches[i].group(2)
        # design 9.2 rule 4 (change set 0i): computed ONCE per matched
        # paren, over `working_sentence` (ID+branch pairs already merged
        # into single-char placeholders, so any literal "(" "/" ")"
        # remaining there is a genuinely separate, nested paren pair).
        enclosing_tag = _has_enclosing_tagged_paren(
            working_sentence, matches[i].start(2) - 1, matches[i].end(2) + 1, real_paths
        )
        preceded_by_review = any(
            t.end() == matches[i].end(2) + 1 and t.group(0).endswith(")")
            for t in _REVIEW_FID_TOKEN_RE.finditer(working_sentence)
        )
        original_span = leading_ws + "(" + restore_text(inner) + ")"
        next_txt = texts[i + 1]
        if target.startswith(original_span, pos):
            pos += len(original_span)
            continue
        if (
            next_txt
            and target.startswith(next_txt, pos)
            and _paren_span_reachable(
                leading_ws, inner, "", real_paths, id_branch_placeholders, enclosing_tag, preceded_by_review
            )
        ):
            continue  # this parenthetical fully (and validly) removed
        if next_txt:
            # `next_txt` (fixed anchor text) can itself occur MULTIPLE
            # times inside a reduced parenthetical's own possible spans
            # (e.g. `next_txt="."` coincides with the dots inside a kept
            # version number like "1.7.0" or "v1.2") -- try every
            # occurrence at/after `pos` as a candidate end boundary and
            # accept the first one for which the parenthetical's own
            # content is actually reachable, rather than committing to
            # just the FIRST occurrence found.
            found_end = None
            search_from = pos
            while True:
                end = target.find(next_txt, search_from)
                if end == -1:
                    break
                candidate_span = target[pos:end]
                if _paren_span_reachable(
                    leading_ws, inner, candidate_span, real_paths, id_branch_placeholders,
                    enclosing_tag, preceded_by_review,
                ):
                    found_end = end
                    break
                search_from = end + 1
            if found_end is None:
                return False
            pos = found_end
            continue
        if i == len(matches) - 1:
            # trailing parenthetical with nothing fixed after it (the
            # sentence ends right at/after it) -- its span runs to the
            # end of `target`.
            end = len(target)
        else:
            # a genuinely empty gap before the NEXT parenthetical (two
            # parens back-to-back with no separating text) -- this one
            # cannot claim any of that following parenthetical's span.
            end = pos
        candidate_span = target[pos:end]
        if not _paren_span_reachable(
            leading_ws, inner, candidate_span, real_paths, id_branch_placeholders,
            enclosing_tag, preceded_by_review,
        ):
            return False
        pos = end
    if not target.startswith(texts[-1], pos):
        return False
    pos += len(texts[-1])
    return pos == len(target)


# ---------------------------------------------------------------------------
# design §4.1 (6), v0.5 (change set 0b, supervisor ruling; tightened in
# the 0b review): mechanical removal of a leading history LABEL --
# "Ruling U-7 (WP-6d): reason." -> "reason." A label is the text from the
# sentence's start up to the FIRST separator (`: ` / `：` / ` -- ` /
# ` — `) found OUTSIDE any backtick code span, qualifying only if ALL of:
#   (1) it contains >=1 §4.1 (5) history token, or an unprotected bare ID
#       that is not itself provenance-tagged (same §4.1 (4) origin-tag
#       detection, applied to the WHOLE label -- a filename/`roadmap`/
#       `spec` reference anywhere in the label tags every bare ID in it);
#   (2) it is <=12 words (ALWAYS, Japanese included) and, additionally,
#       if it contains any Japanese character, <=24 characters once
#       bracket CHARACTERS (not their content) / history tokens / IDs are
#       removed;
#   (3) it has <=3 CONTENT words (everything except history tokens, IDs,
#       brackets, "and"/"or"/"、");
#   (4) it contains NO negation word (never/not/no/must not/don't/cannot,
#       ない/禁止/しない) and NO protected reference (SI-/C-/CCR-, or a
#       bare ID that is provenance-tagged per (1)) -- review-round
#       supervisor ruling L1/L10: such text is never treated as a label,
#       regardless of (1)-(3).
# Only the label and its separator are removed; the text after the
# separator is kept byte-for-byte (no lowercasing or other reshaping).
# (4) may be applied afterward to what remains (design v0.4 §8.1 "(4)と
# の併用").
# ---------------------------------------------------------------------------
_LABEL_SEPARATOR_RE = re.compile(r": |：| -- | — ")
_BACKTICK_SPAN_RE = re.compile(r"`[^`]*`")
_BRANCH_PAREN = r"\((?:\d+|[IVXLCDMivxlcdm]+)\)"
# 0b review round 4 (supervisor ruling): the branch-number merge applies
# to an unprotected bare ID AND to a §4.1 (5) history token (`WP-6d
# (ii)`), not only to a bare ID -- so "WP-" is carved out of the bare-ID
# alternative (`(?!...|WP-)`) and given its OWN alternative below, using
# the exact same token shape as `_HISTORY_TOKEN_PATTERNS`'s WP- entry.
# This is deliberately NOT left to the format overlap between "WP-6d" and
# the bare-ID shape (`[A-Z]{1,6}-\d+[a-z]?`, which "WP-6d" also happens to
# match): that overlap is coincidental for a short suffix and would not
# hold for e.g. "WP-abc123", so the merge is anchored to the actual
# history-token grammar instead.
_ID_BRANCH_RE = re.compile(
    r"\b(?:(?P<bare_id>(?!" + "|".join(re.escape(p) for p in _PROTECTED_ID_PREFIXES) + r"|WP-)"
    r"[A-Z]{1,6}-\d+[a-z]?)"
    r"|(?P<history_id>WP-[0-9A-Za-z-]+))\s*(" + _BRANCH_PAREN + r")"
)
_CONNECTIVE_WORDS = frozenset({"and", "or", "、"})
_JAPANESE_CHAR_RE = re.compile(r"[぀-ヿ㐀-鿿＀-￯]")
_ANY_ID_RE = re.compile(r"\b[A-Z]{1,6}-\d+[a-z]?\b")
_NEGATION_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.ASCII | re.IGNORECASE)
    for p in (r"\bnever\b", r"\bnot\b", r"\bno\b", r"\bmust\s+not\b", r"\bdon't\b", r"\bcannot\b")
) + (re.compile("ない"), re.compile("禁止"), re.compile("しない"))


_PROTECTED_ID_EXTRACT_RE = re.compile(
    r"(?<![A-Za-z0-9_])[A-Z]{1,6}-\d+[a-z]?(?![A-Za-z0-9_])", re.ASCII
)


def _protected_reference_ids(text: str) -> list[str]:
    """Shared protected-ID extraction (design 9.2 "使う箇所", M1, change
    set 0i): strip every `review F-n` / `review round F-n` / `review
    (F-n)` span first (Z0i-1 (B) -- an indicated review-round pointer is
    a history token, never a protected reference), then extract every
    ID-shaped token with ASCII word boundaries (M2) -- Python's Unicode
    `\\w`/`\\b` treats a Hiragana/Katakana/Kanji character as a word
    character, so a plain `\\b` would see no boundary, and miss the ID
    entirely, right after an ID glued directly onto Japanese text with
    no separating space or punctuation (`F-12だけは`). Returns every
    id-shaped token found, not only protected-prefixed ones -- callers
    filter by `_PROTECTED_ID_PREFIXES` themselves, exactly as they did
    with the plain `_ANY_ID_RE.findall` this replaces at all three of
    the four 9.2 "使う箇所" that need free-text extraction (the fourth,
    §4.1 (4)'s parenthetical word removal, gets the same
    `_REVIEW_FID_TOKEN_RE` pattern through `_HISTORY_TOKEN_PATTERNS`/
    `_premerge_tokens` instead, since that path already merges
    multi-word tokens before any word-level check runs)."""
    stripped = _REVIEW_FID_TOKEN_RE.sub(" ", text)
    return _PROTECTED_ID_EXTRACT_RE.findall(stripped)


def _label_word_tokens(text: str, real_paths: frozenset[str]) -> list[tuple[str, bool]]:
    """[(token, is_content_word), ...] per design §8.1's word-counting
    rules: a backtick span is one (content) word (UNLESS it is a non-real
    filename, §9 rule 2, in which case it is a history token instead); a
    multi-word history token (§9 rule 1) merges into one non-content word
    BEFORE any split; an UNPROTECTED ID immediately followed by a
    parenthesized digit/roman-numeral branch (`(4)`, `(ii)`) merges into
    one NON-content word (a protected ID such as `SI-08 (2)` never
    merges); remaining parens are unwrapped (brackets dropped, content
    flows into the flat stream); a history token, an unprotected bare ID,
    a non-real filename, a `/`-continuation ID subscript (§9 rule 4), or
    "and"/"or"/"、" is one non-content word; a symbol-only fragment does
    not count as a word at all."""
    slash_subscripts = _slash_id_subscripts(text)
    working, placeholders = _premerge_tokens(text, real_paths)
    working = working.replace("(", " ").replace(")", " ")

    tokens: list[tuple[str, bool]] = []
    for raw in working.split():
        t = raw.strip(",;")
        if not t:
            continue
        if t in placeholders:
            _original, is_content = placeholders[t]
            tokens.append((t, is_content))
            continue
        if t in _CONNECTIVE_WORDS:
            tokens.append((t, False))
            continue
        if any(pat.search(t) for pat in _HISTORY_TOKEN_PATTERNS):
            tokens.append((t, False))
            continue
        if t in slash_subscripts:
            tokens.append((t, False))
            continue
        if _is_filename_candidate_fullmatch(t) and not _is_real_filename_candidate(t, real_paths):
            tokens.append((t, False))
            continue
        if _BARE_ID_RE.match(t) and not t.startswith(_PROTECTED_ID_PREFIXES):
            tokens.append((t, False))
            continue
        tokens.append((t, True))
    return tokens


def _label_provenance_tag_present(text: str, real_paths: frozenset[str]) -> bool:
    """Same §4.1 (4)/(6) origin-tag detection as `_parens_has_provenance_tag`
    (a REAL filename -- §9 rule 2, `roadmap`/`spec`, path word, or a
    versioned document name), applied to the WHOLE label (not just inside
    one parenthetical) -- review round: "ファイル名・roadmap・specが同じ
    ラベルにあれば、そのIDは出所付き"."""
    if (
        _has_real_filename_reference(text, real_paths)
        or _PROVENANCE_WORD_RE.search(text)
        or _has_versioned_document_reference(text)
    ):
        return True
    remainder = _sub_filename_candidates(text, " ")
    for chunk in re.split(r"[,;()\s]+", remainder):
        if _looks_like_path_word(chunk):
            return True
    return False


def _label_has_provenance_marker(text: str, real_paths: frozenset[str]) -> bool:
    """Condition (1): a §4.1 (5) history token, or an unprotected bare ID
    that is NOT itself provenance-tagged elsewhere in the label."""
    if any(pat.search(text) for pat in _HISTORY_TOKEN_PATTERNS):
        return True
    ids = _protected_reference_ids(text)
    unprotected = [i for i in ids if not i.startswith(_PROTECTED_ID_PREFIXES)]
    if not unprotected:
        return False
    return not _label_provenance_tag_present(text, real_paths)


def _label_has_protected_reference(text: str, real_paths: frozenset[str]) -> bool:
    """Review-round supervisor ruling (L1/L10): a label containing a
    protected reference (SI-/C-/CCR-, or a bare ID that is provenance-
    tagged) is never removable, even if it also carries a qualifying (5)
    token elsewhere (e.g. "SI-08 WP-3:"). design 9.2 "使う箇所" (M3,
    change set 0i, monitor ruling): also calls the SAME sentence-level
    protected-reference check §4.1 (3) uses (protected ID, `spec §`, a
    versioned document name, a real path) -- a label carrying, say, a
    real filename reference must be just as unremovable as a whole
    sentence carrying one, not only an ID."""
    if _sentence_has_protected_reference(text, real_paths):
        return True
    ids = _protected_reference_ids(text)
    if any(i.startswith(_PROTECTED_ID_PREFIXES) for i in ids):
        return True
    unprotected = [i for i in ids if not i.startswith(_PROTECTED_ID_PREFIXES)]
    return bool(unprotected) and _label_provenance_tag_present(text, real_paths)


def _label_japanese_char_count(text: str) -> int:
    """Bracket CHARACTERS are excluded, but their CONTENT counts (review
    round fix (b)) -- only `(`/`)` themselves, plus history tokens and
    IDs, are stripped before counting."""
    working = text.replace("(", "").replace(")", "")
    for pat in _HISTORY_TOKEN_PATTERNS:
        working = pat.sub("", working)
    working = _PROTECTED_ID_EXTRACT_RE.sub("", working)
    return len(re.sub(r"\s+", "", working))


def _label_qualifies(text: str, real_paths: frozenset[str]) -> bool:
    if any(p.search(text) for p in _NEGATION_PATTERNS):
        return False
    if _label_has_protected_reference(text, real_paths):
        return False
    if not _label_has_provenance_marker(text, real_paths):
        return False
    tokens = _label_word_tokens(text, real_paths)
    content_count = sum(1 for _t, is_content in tokens if is_content)
    if content_count > 3:
        return False
    if len(tokens) > 12:
        return False
    if _JAPANESE_CHAR_RE.search(text) and _label_japanese_char_count(text) > 24:
        return False
    return True


def _strip_leading_label(sentence: str, real_paths: frozenset[str]) -> str:
    """The separator is looked for OUTSIDE backtick code spans only
    (review round fix (b))."""
    spans = [(m.start(), m.end()) for m in _BACKTICK_SPAN_RE.finditer(sentence)]

    def _inside_span(pos: int) -> bool:
        return any(start <= pos < end for start, end in spans)

    for m in _LABEL_SEPARATOR_RE.finditer(sentence):
        if _inside_span(m.start()):
            continue
        label = sentence[: m.start()]
        if not _label_qualifies(label, real_paths):
            return sentence
        return sentence[m.end() :]
    return sentence


_SPEC_SECTION_RE = re.compile(r"\bspec\s*§", re.IGNORECASE)


def _sentence_has_protected_reference(sentence: str, real_paths: frozenset[str]) -> bool:
    """design §4.1 (3), change set 0d (supervisor ruling): a whole
    sentence may never be deleted outright if it carries a protected
    reference -- an SI-/C-/CCR- id, a `spec §` reference, a versioned
    document name (§3), or a path that really exists in the basis tree
    (basename-unique match included, §9 rule 2). Reuses the SAME
    protected-reference detection already used elsewhere in this file --
    no new judgment logic. Mechanically removing a history token from
    WITHIN a KEPT sentence via (4)/(6) is unaffected by this (only whole-
    sentence deletion is restricted). HTTP status codes and error-code
    vocabulary are deliberately NOT protected here -- left to audit/
    conformance review, not this tool."""
    ids = _protected_reference_ids(sentence)
    if any(i.startswith(_PROTECTED_ID_PREFIXES) for i in ids):
        return True
    if _SPEC_SECTION_RE.search(sentence):
        return True
    if _has_versioned_document_reference(sentence):
        return True
    if _has_real_filename_reference(sentence, real_paths):
        return True
    return False


def _first_protected_sentence(
    text: str, kind: str, real_paths: frozenset[str], identifier_set: frozenset[str] = frozenset()
) -> str | None:
    """change set 0d review round (item 1): when a WHOLE block is moved
    away with nothing retained in code (`retained_text` empty), the
    entire source text -- every sentence of it -- disappears from the
    code just as surely as an in-place whole-sentence deletion would;
    check it the SAME way, sentence by sentence, rather than skipping
    the check entirely just because there is no `_is_allowed_reduction`
    call to hang it on."""
    for sentence in split_sentences(_flatten(kind, text, identifier_set)):
        if _sentence_has_protected_reference(sentence, real_paths):
            return sentence
    return None


def _is_allowed_reduction(
    kind: str,
    old_full_text: str,
    new_retained_text: str,
    real_paths: frozenset[str],
    identifier_set: frozenset[str] = frozenset(),
) -> tuple[bool, str]:
    """design §4.1 (3)+(4)+(6)+§9: `new_retained_text` must be reachable
    from `old_full_text` by deleting whole sentences (order preserved)
    and/or applying, to a kept sentence, ANY ALLOWED SUBSET of the (4)
    mechanical parenthetical-word removals (each a PERMISSION, not an
    obligation -- v0.7 supervisor ruling) and/or the (6) leading-label
    removal (v0.5, itself an atomic permission; (6) may be followed by
    (4) on what remains) -- nothing else (no reorder, no added word, no
    dropped negation, no mid-sentence line-wrap deletion). Because every
    (4)/§9-rule-1-4 word removal and the §9 rule 3 kind-word-residue
    sweep are permissions rather than obligations, a sentence that
    stopped at a PARTIAL reduction (e.g. change set 1 removing an id
    from a parenthetical but leaving a lone kind word like "(ruling)"
    behind, instead of also sweeping it per rule 3) is just as valid as
    the maximal one; `_sentence_reachable` checks each independent site
    (each parenthetical; the leading label) on its own via a single
    left-to-right scan, with no combination search and no length limit
    (second v0.7 follow-up ruling: the original subset-enumeration form
    of this capped parenthetical size to avoid a combinatorial blow-up,
    which wrongly rejected a valid partial reduction once a sentence had
    enough removable words)."""
    old_sentences = split_sentences(_flatten(kind, old_full_text, identifier_set))
    new_sentences = split_sentences(_flatten(kind, new_retained_text, identifier_set))
    j = 0
    for ns in new_sentences:
        found = False
        while j < len(old_sentences):
            candidate = old_sentences[j]
            j += 1
            label_stripped = _strip_leading_label(candidate, real_paths)
            if _sentence_reachable(candidate, ns, real_paths) or (
                label_stripped != candidate and _sentence_reachable(label_stripped, ns, real_paths)
            ):
                found = True
                break
            # `candidate` is being deleted WHOLE (change set 0d, design
            # §4.1 (3) supervisor ruling): never allowed if it carries a
            # protected reference.
            if _sentence_has_protected_reference(candidate, real_paths):
                return False, f"cannot delete a whole sentence carrying a protected reference: {candidate!r}"
        if not found:
            return False, f"retained text has no order-preserving match in the original block for: {ns!r}"
    for candidate in old_sentences[j:]:
        if _sentence_has_protected_reference(candidate, real_paths):
            return False, f"cannot delete a whole sentence carrying a protected reference: {candidate!r}"
    return True, ""


# ---------------------------------------------------------------------------
# design §4.1 (1): code unchanged (docstrings excluded, line numbers
# excluded via include_attributes=False -- a pure line-shift is green).
# ---------------------------------------------------------------------------
def _is_docstring_stmt(stmt: ast.stmt) -> bool:
    """design §4.1 (1)'s own docstring shape: a bare string-constant `Expr`
    statement. The ONE definition `_strip_docstrings_for_ast` (below, a
    leading `node.body[0]`) and `_token_for_stmt` (R-63 WP-1 code review
    round 1, 低 "docstring の範囲": only at `is_first`, never mid-body)
    both use -- so "what counts as a docstring" is never defined twice."""
    return (
        isinstance(stmt, ast.Expr)
        and isinstance(stmt.value, ast.Constant)
        and isinstance(stmt.value.value, str)
    )


def _strip_docstrings_for_ast(tree: ast.Module) -> ast.Module:
    doc_node_types = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    for node in ast.walk(tree):
        if not isinstance(node, doc_node_types):
            continue
        if node.body and _is_docstring_stmt(node.body[0]):
            node.body = node.body[1:] or [ast.Pass()]
    return tree


def ast_signature(source: str) -> str:
    tree = ast.parse(source)
    tree = _strip_docstrings_for_ast(tree)
    return ast.dump(tree, include_attributes=False)


def _first_diff_line(old_source: str, new_source: str) -> int:
    old_lines = old_source.splitlines()
    new_lines = new_source.splitlines()
    sm = difflib.SequenceMatcher(a=old_lines, b=new_lines, autojunk=False)
    for tag, _i1, _i2, j1, j2 in sm.get_opcodes():
        if tag != "equal":
            return (j1 + 1) if j1 < len(new_lines) else max(len(new_lines), 1)
    return 1


# ---------------------------------------------------------------------------
# design §4.1 (5): no history token in an added line, file-wide (this
# includes a trailing/inline comment on an added or changed code line,
# design v0.4 ruling -- it operates on raw diff lines, not extracted
# blocks, so it was already covering that case; the ruling just records it
# as deliberate).
# ---------------------------------------------------------------------------
def _added_lines(old_source: str, new_source: str) -> list[tuple[int, str, str]]:
    """(new_lineno, new_line_text, old_chunk_text) for each changed line
    in an "insert" or "replace" diff opcode. `old_chunk_text` is the
    WHOLE replaced region (its lines joined with "\\n"), not just the one
    corresponding old line -- a token can shift lines within the same
    edited region -- and is "" for a pure insert (nothing old to compare
    against, so every token in it is unconditionally new)."""
    old_lines = old_source.splitlines()
    new_lines = new_source.splitlines()
    sm = difflib.SequenceMatcher(a=old_lines, b=new_lines, autojunk=False)
    added: list[tuple[int, str, str]] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag in ("insert", "replace"):
            old_chunk = "\n".join(old_lines[i1:i2]) if tag == "replace" else ""
            for k in range(j1, j2):
                added.append((k + 1, new_lines[k], old_chunk))
    return added


def check_no_added_history_tokens(old_source: str, new_source: str) -> list[tuple[int, str, str]]:
    """design §4.1 (5), supervisor ruling (0c review): flag only a history
    token that did NOT already exist somewhere in the basis block's own
    (replaced) text -- a token-level diff against the basis, not a blanket
    "any history token on a changed line" scan. A partial reduction that
    keeps an EXISTING token untouched (e.g. "(WP-3, round 2, R-5)" ->
    "(round 2)") is not itself an added-history-token violation; only a
    genuinely NEW token (absent from the basis) is."""
    hits: list[tuple[int, str, str]] = []
    for lineno, line, old_chunk in _added_lines(old_source, new_source):
        for pat in _HISTORY_TOKEN_PATTERNS:
            if any(m.group(0) not in old_chunk for m in pat.finditer(line)):
                hits.append((lineno, line, pat.pattern))
                break
    return hits


# ---------------------------------------------------------------------------
# docs/code-history/ companion parsing (shared by --base and --register).
# ---------------------------------------------------------------------------
def _companion_files(repo_root: Path, peer: str) -> list[Path]:
    files: list[Path] = []
    peer_dir = repo_root / "docs" / "code-history" / peer
    if peer_dir.is_dir():
        files.extend(sorted(peer_dir.glob("*.md")))
    pair_path = repo_root / "docs" / "code-history" / "pair.md"
    if pair_path.is_file():
        files.append(pair_path)
    return files


def _companion_rel_paths_from_tree(peer: str, tree_paths: frozenset[str]) -> list[str]:
    """Core of the rev-based enumeration below, factored out so a caller
    that must tell a genuinely EMPTY tree apart from a FAILED tree read
    (`_tree_paths_or_none`) can supply its own `tree_paths` instead of
    going through `_tree_paths`'s own fail-toward-empty contract."""
    peer_prefix = f"docs/code-history/{peer}/"
    rel_paths = sorted(
        p for p in tree_paths
        if p.startswith(peer_prefix) and p.endswith(".md") and "/" not in p[len(peer_prefix):]
    )
    pair_rel = "docs/code-history/pair.md"
    if pair_rel in tree_paths:
        rel_paths.append(pair_rel)
    return rel_paths


def _companion_rel_paths(repo_root: Path, peer: str, rev: str | None = None) -> list[str]:
    """The same companion-file SET `_companion_files` lists from the
    working tree -- that peer's own `docs/code-history/<peer>/*.md`
    (non-recursive) plus the shared `docs/code-history/pair.md` -- as
    repo-relative POSIX path strings. With `rev` given, the set is read
    from `rev`'s own git tree (`_tree_paths`) instead of the working
    tree, so a caller can enumerate exactly what the working tree would
    show, at an earlier snapshot (design docs/design/CODE_COMMENT_PROVENANCE_V1.md
    §9.3 rule 1: a companion whose only section lives in `pair.md` must
    still be found this way)."""
    if rev is None:
        return [str(p.relative_to(repo_root)) for p in _companion_files(repo_root, peer)]
    return _companion_rel_paths_from_tree(peer, _tree_paths(repo_root, rev))


def _iter_companion_sections_from_text(text: str) -> list[tuple[str, str]]:
    """[(CH-ID, section_body)] in file order, WITHOUT de-duplication --
    duplicate detection needs the raw list. Split out of
    `_iter_companion_sections` so a rev-based read (`_git_show`, never
    `Path.read_text`) can share the exact same section-splitting logic."""
    headings = list(_HEADING_RE.finditer(text))
    out: list[tuple[str, str]] = []
    for i, m in enumerate(headings):
        start = m.end()
        end = headings[i + 1].start() if i + 1 < len(headings) else len(text)
        out.append((m.group(1), text[start:end]))
    return out


def _iter_companion_sections(path: Path) -> list[tuple[str, str]]:
    """[(CH-ID, section_body)] in file order, WITHOUT de-duplication --
    duplicate detection needs the raw list."""
    return _iter_companion_sections_from_text(path.read_text(encoding="utf-8"))


def _fenced_content(body: str) -> str | None:
    """The content of the section's fenced block, matching a CLOSING fence
    of the SAME backtick-run length as the opening one (design v0.4: a
    docstring containing ``` needs a longer fence so its own content is
    never mistaken for the close)."""
    m = _FENCE_OPEN_RE.search(body)
    if m is None:
        return None
    fence = m.group(1)
    start = m.end()
    close_re = re.compile(r"^" + re.escape(fence) + r"\s*$", re.MULTILINE)
    close_m = close_re.search(body, start)
    if close_m is None:
        return None
    return body[start : close_m.start()].rstrip("\n")


def _load_companion_lookup(repo_root: Path, peer: str, rev: str | None = None) -> dict[str, str]:
    """{CH-ID: fenced block content} for one peer, merged across its
    companion dir and pair.md. Last-one-wins on a duplicate heading is
    fine here -- duplication itself is a separate --register failure.

    `rev` (design docs/design/CODE_COMMENT_PROVENANCE_V1.md §9.3 rule 6):
    when given, every companion file is read from `rev`'s own git tree
    instead of the working tree. `run_base`'s own re-edit basis always
    keeps reading the WORKING TREE's companion (`rev=None`, §9.3 rule 1)
    -- the fenced block itself must reflect a working-tree rewrite, or
    that rewrite would go undetected. This parameter exists for a caller
    that must read source, companion, and corrections from one shared
    snapshot (e.g. a rev-vs-itself comparison)."""
    merged: dict[str, str] = {}
    for rel_path in _companion_rel_paths(repo_root, peer, rev):
        text = (
            (repo_root / rel_path).read_text(encoding="utf-8")
            if rev is None else _git_show(repo_root, rev, rel_path)
        )
        if text is None:
            continue
        for ch_id, body in _iter_companion_sections_from_text(text):
            content = _fenced_content(body)
            if content is not None:
                merged[ch_id] = content
    return merged


@dataclass(frozen=True)
class Correction:
    """One append-only correction record for a CH-ID's companion section
    (design docs/design/CODE_COMMENT_PROVENANCE_V1.md v0.11 §9, change set
    0g, supervisor ruling 2026-09-15).

    A companion section's original fenced block is captured once, at move
    time, and is NEVER edited afterward -- not even when the code it
    describes is later fact-fixed (R-22, commit 1715e18) to correct a
    protected sentence that (rightly) no longer matches the code. Instead,
    a correction entry is appended below the original fenced block, inside
    the SAME `## CH-XXXX` section, in this fenced format (chosen to match
    the section's own established shape -- a `- key: value` metadata line,
    then fenced content):

        ### correction: 2026-09-15

        - reason: one-line reason the sentence no longer matched the code

        old:
        ```
        <the exact old sentence, one line>
        ```

        new:
        ```
        <the exact new sentence, one line>
        ```

    Corrections are append-only (the original block above this is never
    touched) and are applied, in FILE ORDER, to the FLATTENED basis text
    before any derivability/0d/predicate-B check runs (`_apply_corrections`)
    -- so a second correction may legitimately CHAIN on the first (its own
    `old` text existing in the basis only after the first has already been
    applied). `_parse_corrections` builds these from a section's raw text;
    `--register` (§9f) validates their format; `run_base`/the rev-vs-itself
    check apply them via `_apply_corrections` when building the basis for
    derivability."""
    ch_id: str
    date: str
    reason: str
    old: str
    new: str


_CORRECTION_HEADING_RE = re.compile(r"^### correction: (\d{4}-\d{2}-\d{2})\s*$", re.MULTILINE)
_CORRECTION_REASON_RE = re.compile(r"^- reason: (.+)$", re.MULTILINE)
_CORRECTION_OLD_MARKER_RE = re.compile(r"^old:\s*$", re.MULTILINE)
_CORRECTION_NEW_MARKER_RE = re.compile(r"^new:\s*$", re.MULTILINE)


def _parse_corrections(ch_id: str, path: Path | str, body: str) -> tuple[list[Correction], list[str]]:
    """[Correction, ...] plus [format-error, ...] for one CH-ID section's
    body (everything after its `## CH-XXXX` heading). A malformed entry
    (missing date/reason/old/new, markers out of order, or an old/new
    fence that never closes or is empty) is a format error, never
    silently skipped -- `--register` (§9f) reports these, and so does
    `run_base`'s own basis-building, since a correction that cannot be
    parsed can never be safely applied."""
    headings = list(_CORRECTION_HEADING_RE.finditer(body))
    corrections: list[Correction] = []
    errors: list[str] = []
    for i, m in enumerate(headings):
        date = m.group(1)
        start = m.end()
        end = headings[i + 1].start() if i + 1 < len(headings) else len(body)
        chunk = body[start:end]
        reason_m = _CORRECTION_REASON_RE.search(chunk)
        old_marker_m = _CORRECTION_OLD_MARKER_RE.search(chunk)
        new_marker_m = _CORRECTION_NEW_MARKER_RE.search(chunk)
        if reason_m is None:
            errors.append(f"{path} {ch_id} correction {date}: missing '- reason:' line")
            continue
        if (
            old_marker_m is None
            or new_marker_m is None
            or old_marker_m.start() > new_marker_m.start()
        ):
            errors.append(f"{path} {ch_id} correction {date}: missing 'old:'/'new:' markers (in order)")
            continue
        old_content = _fenced_content(chunk[old_marker_m.end():new_marker_m.start()])
        new_content = _fenced_content(chunk[new_marker_m.end():])
        if old_content is None or not old_content.strip():
            errors.append(f"{path} {ch_id} correction {date}: 'old:' has no (non-empty) fenced block")
            continue
        if new_content is None or not new_content.strip():
            errors.append(f"{path} {ch_id} correction {date}: 'new:' has no (non-empty) fenced block")
            continue
        corrections.append(
            Correction(
                ch_id=ch_id, date=date, reason=reason_m.group(1).strip(),
                old=old_content.strip(), new=new_content.strip(),
            )
        )
    return corrections, errors


def _load_corrections_lookup(
    repo_root: Path, peer: str, rev: str | None = None,
) -> tuple[dict[str, list[Correction]], list[str]]:
    """{CH-ID: [Correction, ...]} for one peer, merged across its companion
    dir and pair.md (see `_companion_rel_paths`) -- plus every format error
    encountered (§9f) while parsing them.

    `rev` (design docs/design/CODE_COMMENT_PROVENANCE_V1.md §9.3 rules 1
    and 6): the same rev-capable read `_load_companion_lookup` offers.
    `run_base` uses it to load the BASIS revision's own correction
    records (never the working tree) for its re-edit-path prefix check
    and stage-A basis; a rev-vs-itself comparison uses it for BOTH
    sides.

    A basis-side read that cannot actually be completed is reported
    (§9f), never silently folded into "0 corrections": that would push
    every correction on the unreadable path into `pending`, which
    disables the append-only prefix check (design §9.3 rule 2) for
    every CH-ID it covers. Three distinct failures are checked, in
    order, each returning immediately: `rev` itself failing to resolve
    at all (`_rev_tree_readable`); `rev`'s own companion-tree read
    (`git ls-tree`, via `_tree_paths_or_none`) failing outright, told
    apart from a tree that genuinely has no matching paths yet (design
    §9.3 rule 1's own, legitimate, 0-corrections case); and a path the
    tree enumeration DOES list, but whose own `git show` then fails --
    `rev`'s tree said the path exists, so a read failure at that point
    is a genuine problem, not "the basis rev has no such file"."""
    merged: dict[str, list[Correction]] = {}
    errors: list[str] = []
    if rev is None:
        rel_paths = _companion_rel_paths(repo_root, peer, None)
    else:
        if not _rev_tree_readable(repo_root, rev):
            errors.append(f"{peer}: basis revision {rev!r} could not be read (git rev-parse failed)")
            return merged, errors
        tree_paths = _tree_paths_or_none(repo_root, rev)
        if tree_paths is None:
            errors.append(
                f"{peer}: basis revision {rev!r}'s companion tree could not be enumerated "
                "(git ls-tree failed)"
            )
            return merged, errors
        rel_paths = _companion_rel_paths_from_tree(peer, tree_paths)
    for rel_path in rel_paths:
        if rev is None:
            text = (repo_root / rel_path).read_text(encoding="utf-8")
        else:
            text = _git_show(repo_root, rev, rel_path)
            if text is None:
                errors.append(
                    f"{peer}: {rel_path} is listed in {rev!r}'s tree but could not be "
                    "read (git show failed)"
                )
                continue
        for ch_id, body in _iter_companion_sections_from_text(text):
            corrections, errs = _parse_corrections(ch_id, rel_path, body)
            if corrections:
                merged.setdefault(ch_id, []).extend(corrections)
            errors.extend(errs)
    return merged, errors


def _correction_relaxes_protection(old: str, new: str, real_paths: frozenset[str]) -> str | None:
    """change set 0g review round (supervisor ruling 2026-09-15, "hole"
    fix): a correction record must never be usable to let a protected
    reference in its `old` sentence quietly disappear in `new` -- adding
    one is fine, but dropping one would bypass 0d's own whole-sentence-
    deletion guard (a sentence 0d would never let vanish outright could
    otherwise be "corrected" into one that no longer carries what made it
    protected, then deleted freely by ordinary derivation). Uses the SAME
    detection primitives 0d itself uses (`_ANY_ID_RE`/
    `_PROTECTED_ID_PREFIXES`, `_SPEC_SECTION_RE`,
    `_has_versioned_document_reference`, `_filename_candidates`/
    `_is_real_filename_candidate`). A real path that changed is NOT an
    exception to this, even for an otherwise-legitimate reason (the file
    was renamed/moved) -- per the ruling, that stays a hard red, left for
    a human to re-escalate as its own, separately reviewed decision,
    never silently absorbed by this correction mechanism. Returns an
    error string, or None if nothing protected was lost."""
    old_ids = frozenset(i for i in _protected_reference_ids(old) if i.startswith(_PROTECTED_ID_PREFIXES))
    new_ids = frozenset(_protected_reference_ids(new))
    lost_ids = sorted(i for i in old_ids if i not in new_ids)
    if lost_ids:
        return f"protected reference(s) {lost_ids!r} dropped (old: {old!r}, new: {new!r})"

    old_real_paths = frozenset(
        _strip_location_suffix(_clean_filename_candidate(c)) for c in _filename_candidates(old)
        if _is_real_filename_candidate(c, real_paths)
    )
    # Z0i-4f: strip the location suffix here too, the same way
    # `_is_real_filename_candidate` already strips it (Z0i-3) before the
    # real-path membership check above -- otherwise a correction that
    # only swaps a `:line-line` range for a `::qualname` (or vice versa)
    # on the SAME real path is misread as dropping that path, since the
    # uncleaned old form (`...ops.py:541-550`) never matches the
    # uncleaned new form (`...ops.py::_run_deprovision_script`). A
    # correction that drops the path itself is still refused: its
    # stripped form then has no match in `new_candidates_cleaned` at
    # all.
    new_candidates_cleaned = frozenset(
        _strip_location_suffix(_clean_filename_candidate(c)) for c in _filename_candidates(new)
    )
    lost_paths = sorted(p for p in old_real_paths if p not in new_candidates_cleaned)
    if lost_paths:
        return f"real path(s) {lost_paths!r} dropped (old: {old!r}, new: {new!r})"

    if _SPEC_SECTION_RE.search(old) and not _SPEC_SECTION_RE.search(new):
        return f"'spec §' reference dropped (old: {old!r}, new: {new!r})"
    if _has_versioned_document_reference(old) and not _has_versioned_document_reference(new):
        return f"versioned document reference dropped (old: {old!r}, new: {new!r})"
    return None


def _apply_corrections(
    kind: str, basis_text: str, corrections: list[Correction],
    real_paths: frozenset[str], identifier_set: frozenset[str],
) -> tuple[str, str | None]:
    """Applies a CH-ID's own correction entries, IN ORDER, to the
    FLATTENED basis text -- so a corrected sentence's exact wording is
    matched the same way every other sentence comparison in this file
    already ignores a mid-block line wrap (via `_flatten`). `_flatten` is
    idempotent when re-applied to already-flattened text (single spaces
    within a paragraph, `\\n\\n` between paragraphs, both already in their
    reduced/normalized form), which is why the result below is safe to
    feed straight into `_is_allowed_reduction`/`_first_protected_sentence`
    in place of the raw companion text -- those functions flatten their
    input themselves, and doing so a second time changes nothing. Each
    correction's `old` text must occur EXACTLY ONCE in the basis as
    corrected by every PRIOR entry -- 0 occurrences (stale/mistyped) or
    >=2 (ambiguous) is a hard error, never silently resolved by picking
    the first/last match. Each correction is also checked
    (`_correction_relaxes_protection`) for silently dropping a protected
    reference the `old` sentence carried -- a 0d-bypass hole a supervisor
    ruling closed. Returns (corrected_text, error); error is None on
    success."""
    working = _flatten(kind, basis_text, identifier_set)
    for corr in corrections:
        protection_err = _correction_relaxes_protection(corr.old, corr.new, real_paths)
        if protection_err:
            return working, f"correction {corr.date}: {protection_err}"
        count = working.count(corr.old)
        if count != 1:
            return working, (
                f"correction {corr.date} old sentence occurs {count} time(s) in the basis "
                f"(expected exactly 1): {corr.old!r}"
            )
        working = working.replace(corr.old, corr.new, 1)
    return working, None


def _correction_prefix_mismatch(
    base_corrections: list[Correction], working_corrections: list[Correction],
) -> str | None:
    """design docs/design/CODE_COMMENT_PROVENANCE_V1.md §9.3 rule 2: the
    basis revision's own correction list for a CH-ID must be a verbatim
    (date, reason, old, and new all compared) PREFIX of the working
    tree's list for the same CH-ID -- an edited, deleted, or reordered
    basis-side entry breaks the prefix at the first position where the
    two no longer match position-for-position, so a swap is caught the
    same way an edit is. Returns an error string, or None if the prefix
    holds."""
    if len(base_corrections) > len(working_corrections):
        return (
            f"basis correction list has {len(base_corrections)} entries, the working-tree "
            f"list has only {len(working_corrections)} (an entry was deleted)"
        )
    for i, base_corr in enumerate(base_corrections):
        work_corr = working_corrections[i]
        if (
            (base_corr.date, base_corr.reason, base_corr.old, base_corr.new)
            != (work_corr.date, work_corr.reason, work_corr.old, work_corr.new)
        ):
            return (
                f"basis correction #{i + 1} ({base_corr.date}) does not match the working-tree "
                "entry at the same position verbatim (edited, deleted, or reordered)"
            )
    return None


def _apply_pending_corrections(
    kind: str, basis_text: str, pending: list[Correction],
    real_paths: frozenset[str], identifier_set: frozenset[str],
) -> tuple[str, str | None, str | None]:
    """design docs/design/CODE_COMMENT_PROVENANCE_V1.md §9.3 rule 3:
    applies a CH-ID's PENDING correction entries (present in the working
    tree but not yet in the basis revision's own companion record, per
    `_correction_prefix_mismatch`) to the FLATTENED text of the re-edited
    block's own current, committed wording (`ob.retained_text`) -- the
    stage-B basis for a same-changeset reword. Unlike `_apply_corrections`
    (which always requires exactly one occurrence, since it is folding
    corrections that are already final against the companion's frozen
    original), a pending correction's `old` sentence may legitimately be
    ABSENT: 0 occurrences applies no change (an earlier sentence deletion
    already removed it, never an error), exactly 1 occurrence replaces
    it, and 2+ occurrences is still a hard error (ambiguous). Each
    pending correction is checked (`_correction_relaxes_protection`) the
    same way `_apply_corrections` does. Returns (corrected_text, error,
    section); error and section are both None on success, section is the
    diagnostic tag the caller prefixes its own `FAIL (...)` line with
    (`§9f` for every error below, `§9.4` for the two §9.4 rule 1 errors).

    design docs/design/CODE_COMMENT_PROVENANCE_V1.md §9.4 rule 1: when
    `old` occurs 0 times verbatim in the basis (it is written in the
    receiving end's own wording, while THIS block's own earlier (4)/(6)
    reduction already dropped part of what `old` names), the 0-occurrence
    branch no longer assumes the sentence is simply gone -- it first
    looks, among the basis's own sentences, for exactly one that `old`
    itself reduces to (`_sentence_reachable`, tried against `old` and,
    failing that, against `old` with its own leading label stripped).
    None is still a no-op; two or more distinct reductions is a hard
    error (ambiguous which one the correction meant). Finding exactly
    one reduction is not yet enough to replace it, though: unlike an
    exact (whole-text) match of `old` itself, whose uniqueness the
    literal `working.count(corr.old) != 1` check above already
    guarantees, a reduction found this way is only a SENTENCE-level
    match -- its own literal text can still occur more than once in
    `working` as a plain substring (e.g. inside a different, longer
    sentence that happens to end the same way), so replacing it with
    `str.replace(..., 1)` could silently rewrite the wrong occurrence.
    The literal occurrence count of the reduction itself is therefore
    checked the same way an exact match's would be before it is ever
    replaced; anything other than exactly 1 is its own §9.4 error,
    distinct from the ambiguous-candidates error above."""
    working = _flatten(kind, basis_text, identifier_set)
    for corr in pending:
        protection_err = _correction_relaxes_protection(corr.old, corr.new, real_paths)
        if protection_err:
            return working, f"correction {corr.date}: {protection_err}", "§9f"
        count = working.count(corr.old)
        if count == 0:
            label_stripped_old = _strip_leading_label(corr.old, real_paths)
            candidates = [
                s for s in split_sentences(working)
                if _sentence_reachable(corr.old, s, real_paths)
                or (
                    label_stripped_old != corr.old
                    and _sentence_reachable(label_stripped_old, s, real_paths)
                )
            ]
            if not candidates:
                continue
            if len(candidates) > 1:
                return working, (
                    f"pending correction {corr.date}: old sentence occurs 0 time(s) verbatim "
                    f"in the basis block, and {len(candidates)} of its sentences are reductions "
                    "of it (ambiguous): " + ", ".join(repr(c) for c in candidates)
                ), "§9.4"
            reduction = candidates[0]
            occurrences = working.count(reduction)
            if occurrences != 1:
                return working, (
                    f"pending correction {corr.date}: old sentence occurs 0 time(s) verbatim "
                    f"in the basis block, its reduction {reduction!r} occurs {occurrences} "
                    "time(s) (ambiguous)"
                ), "§9.4"
            working = working.replace(reduction, corr.new, 1)
            continue
        if count != 1:
            return working, (
                f"correction {corr.date} old sentence occurs {count} time(s) in the basis "
                f"(expected exactly 1): {corr.old!r}"
            ), "§9f"
        working = working.replace(corr.old, corr.new, 1)
    return working, None, None


# ---------------------------------------------------------------------------
# --base: design §4.1 (1)-(5), per source path.
# ---------------------------------------------------------------------------
def _git_show(repo_root: Path, rev: str, rel_path: str) -> str | None:
    try:
        proc = subprocess.run(
            ["git", "show", f"{rev}:{rel_path}"],
            cwd=repo_root,
            capture_output=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    try:
        return proc.stdout.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _tree_paths(repo_root: Path, rev: str) -> frozenset[str]:
    """design §9 rule 2 (v0.6, change set 0c): every path that REALLY
    EXISTS in `rev`'s git tree (recursive), as repo-relative POSIX paths
    -- `--base`'s basis for "is this filename real", read from the basis
    REVISION's tree (`git ls-tree`), never the working tree (a later
    rename must not silently change the verdict). `--register` (no single
    revision) uses `_tree_paths(repo_root, "HEAD")`. An unreadable/absent
    tree yields an EMPTY set (fail toward "nothing is real", i.e. toward
    treating more things as history tokens -- never silently toward
    protecting something that cannot be confirmed)."""
    try:
        proc = subprocess.run(
            ["git", "ls-tree", "-r", "--name-only", "-z", rev],
            cwd=repo_root,
            capture_output=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return frozenset()
    if proc.returncode != 0:
        return frozenset()
    try:
        names = proc.stdout.decode("utf-8").split("\0")
    except UnicodeDecodeError:
        return frozenset()
    return frozenset(n for n in names if n)


def _tree_paths_or_none(repo_root: Path, rev: str) -> frozenset[str] | None:
    """The same `git ls-tree` read as `_tree_paths`, except a genuine
    read failure (a non-zero exit, an `OSError`/timeout, or undecodable
    output) returns `None` instead of being folded into the same empty
    set a legitimately-empty tree also produces. `_tree_paths` itself,
    and every one of its other callers relying on its documented
    fail-toward-empty contract, is unchanged; this exists only for a
    caller (the basis-record enumeration in `_load_corrections_lookup`)
    that must tell the two apart and FAIL on a genuine read failure."""
    try:
        proc = subprocess.run(
            ["git", "ls-tree", "-r", "--name-only", "-z", rev],
            cwd=repo_root,
            capture_output=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    try:
        names = proc.stdout.decode("utf-8").split("\0")
    except UnicodeDecodeError:
        return None
    return frozenset(n for n in names if n)


def _rev_tree_readable(repo_root: Path, rev: str) -> bool:
    """Whether `rev` resolves to a real commit at all (`git rev-parse
    --verify`) -- catches a bad SHA or an otherwise unresolvable/
    unreachable rev before any tree read is even attempted. A rev that
    resolves fine but whose OWN tree read then fails (a `git ls-tree`
    subprocess error) is a separate condition `_tree_paths_or_none`
    checks; this function does not attempt to distinguish that case."""
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}"],
            cwd=repo_root,
            capture_output=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


_IDENTIFIER_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _tracked_identifier_set(repo_root: Path, rev: str) -> frozenset[str]:
    """change set 0e §9e rule 5 (supervisor ruling 2026-09-15, unified
    predicate B): every identifier-shaped token (`[A-Za-z_][A-Za-z0-9_]*`)
    that appears ANYWHERE in the tracked `src`/`spec`/`docs` files at
    `rev`'s tree -- the basis for "is this really an identifier this
    codebase uses" for the CamelCase-inside-backtick join trigger,
    guarding it against joining two genuinely separate words that merely
    happen to sit lowercase-then-uppercase across a line wrap (`id ASC`,
    `except FoundationError`, `is None`) into a token that is not
    actually a real identifier anywhere in the tree. One `git grep`
    across the whole tree at `rev` (never the working tree, for the
    same reason `_tree_paths` reads from `rev`) -- built ONCE per
    `--base`/`--register` invocation, not once per boundary check. An
    unreadable/absent tree yields an EMPTY set (fails toward "not a
    real identifier", i.e. toward requiring the space, never toward
    silently permitting an over-join that cannot be confirmed)."""
    try:
        proc = subprocess.run(
            ["git", "grep", "-I", "-h", "-o", "-E", _IDENTIFIER_TOKEN_RE.pattern, rev,
             "--", "r2db-api/src", "MitateDB-api/src", "spec", "docs"],
            cwd=repo_root,
            capture_output=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired):
        return frozenset()
    # git grep exits 1 when there are simply no matches (not an error).
    if proc.returncode not in (0, 1):
        return frozenset()
    try:
        text = proc.stdout.decode("utf-8")
    except UnicodeDecodeError:
        return frozenset()
    return frozenset(text.splitlines())


_SCOPE_TYPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


def _scope_and_anchor_for_block(tree: ast.Module, block: Block) -> tuple[str, str]:
    """design v0.4 P3, implemented per the supervisor ruling (round 3, "P3
    の紐づけを実装する"): a block's key is (scope, anchor) where `anchor`
    identifies -- by AST STRUCTURAL POSITION, never a line number -- the
    statement in the scope's OWN body that the block immediately precedes.

    Descends from the module, at each level picking the current scope's
    direct body and recursing into a child FunctionDef/AsyncFunctionDef/
    ClassDef only when the block's line range falls within that child's
    OWN span (so a block between a decorator and its `def` -- outside the
    FunctionDef's [lineno, end_lineno], since `lineno` is the `def` line,
    not the decorator's -- stays attached to the PARENT scope, anchored on
    the FunctionDef statement itself, exactly like design v0.4 review
    round 3 requires it to). `scope_key` is the dotted NAME path (never a
    line number, so a pure line-shift elsewhere leaves it unchanged --
    §4.1 (1)'s own green case). `anchor` is `stmt#<index>` (the 0-based
    index, within the scope's own body list, of the first statement whose
    `lineno` is greater than the block's `end_line`) or `"<end>"` if the
    block is the last thing in the scope -- both stable across a pure
    line-shift because §4.1 (1) passing guarantees the body's own
    statement list is structurally unchanged, only line numbers move."""
    node: ast.AST = tree
    scope_names: list[str] = []
    body: list[ast.stmt] = tree.body
    while True:
        descended = False
        for child in body:
            if isinstance(child, _SCOPE_TYPES):
                start = child.lineno
                end = getattr(child, "end_lineno", start)
                if start <= block.start_line <= end:
                    scope_names.append(child.name)
                    node = child
                    body = child.body
                    descended = True
                    break
        if not descended:
            break
    scope_key = ".".join(scope_names) if scope_names else "<module>"
    anchor = "<end>"
    for idx, stmt in enumerate(body):
        if stmt.lineno > block.end_line:
            anchor = f"stmt#{idx}"
            break
    return scope_key, anchor


def _block_positions(source: str, blocks: list[Block]) -> list[tuple[str, str]]:
    tree = ast.parse(source)
    return [_scope_and_anchor_for_block(tree, b) for b in blocks]


def _sibling_occurrence(body: list[ast.stmt], idx: int) -> int:
    """R-63 WP-1 code review round 1 (重大 1): how many EARLIER elements of
    `body` (before `idx`) are a scope sharing `body[idx]`'s own name --
    0-based occurrence order among same-named siblings. Python allows
    same-named sibling scopes (`@property`/`@x.setter`, `@overload`), and
    the plain dotted name alone does not tell them apart."""
    child = body[idx]
    return sum(
        1 for other in body[:idx]
        if isinstance(other, _SCOPE_TYPES) and other.name == child.name
    )


def _scope_bodies_by_identity(tree: ast.Module) -> dict[str, list[ast.stmt]]:
    """R-63 WP-1 code review round 1 (重大 1, option (a)): maps every
    scope's INTERNAL identity -- dotted name with `#k` (`_sibling_
    occurrence`) appended at EVERY level, e.g. `C#0.value#1` for a
    `@x.setter` that is the 2nd child of `C` named `value` -- to that
    scope's OWN `body` list. Collision-free even when same-named sibling
    scopes exist, unlike a plain-dotted-name map (which the display key
    from `_scope_and_anchor_for_block`, used for error text and the final
    §4.1 (2) key, still deliberately stays -- only this internal J-1
    alignment cache needed disambiguating)."""
    bodies: dict[str, list[ast.stmt]] = {}

    def walk(node: ast.AST, path: list[str]) -> None:
        key = ".".join(path) if path else "<module>"
        body: list[ast.stmt] = node.body  # type: ignore[attr-defined]
        bodies[key] = body
        for idx, child in enumerate(body):
            if isinstance(child, _SCOPE_TYPES):
                walk(child, path + [f"{child.name}#{_sibling_occurrence(body, idx)}"])

    walk(tree, [])
    return bodies


def _internal_scope_key_and_body_for_block(tree: ast.Module, block: Block) -> tuple[str, list[ast.stmt]]:
    """R-63 WP-1 code review round 1 (重大 1, option (b)): the SAME line-
    containment descent as `_scope_and_anchor_for_block`, but returning the
    `#k`-suffixed internal identity (matching `_scope_bodies_by_identity`)
    together with the scope's own body -- fetched directly by this descent,
    never by a name lookup back into a dict, so a block belonging to one
    same-named sibling (the setter) can never be resolved against another
    (the getter)'s body."""
    path: list[str] = []
    body: list[ast.stmt] = tree.body
    while True:
        descended = False
        for idx, child in enumerate(body):
            if isinstance(child, _SCOPE_TYPES):
                start = child.lineno
                end = getattr(child, "end_lineno", start)
                if start <= block.start_line <= end:
                    path.append(f"{child.name}#{_sibling_occurrence(body, idx)}")
                    body = child.body
                    descended = True
                    break
        if not descended:
            break
    return (".".join(path) if path else "<module>"), body


def _internal_scope_and_anchor_for_block(tree: ast.Module, block: Block) -> tuple[str, str]:
    """R-89: the SAME `#k`-disambiguated
    INTERNAL scope identity `_internal_scope_key_and_body_for_block` uses,
    together with the block's own anchor index within that scope's body --
    never the plain dotted name (`_scope_and_anchor_for_block`'s own
    display key), so the `_plain_block_keys` byte-identity gate below
    cannot mistake one same-named sibling scope (a `@property`/`@x.setter`
    pair, an `@overload` group, two same-named module-level `def`s) for
    another: a block moved from the getter's body to the setter's, even
    when both bodies' own following statements were independently
    rewritten, must not slip through as "the same old key" merely because
    their DISPLAY names collide."""
    internal_key, body = _internal_scope_key_and_body_for_block(tree, block)
    anchor = "<end>"
    for idx, stmt in enumerate(body):
        if stmt.lineno > block.end_line:
            anchor = f"stmt#{idx}"
            break
    return internal_key, anchor


def _token_for_stmt(stmt: ast.stmt, is_first: bool) -> tuple:
    """R-63 WP-1 (J-1; code review round 1, 重大 2 and 低 "docstring の
    範囲"): the per-statement token used to align a scope's OLD body to
    its NEW body. `def`/`class` compare by (kind, name) so renaming the
    statement itself, not merely editing its body, is a different
    statement. `Assign`/`AnnAssign`/`AugAssign` compare by (kind, target's
    `ast.dump`) -- never the value -- so a value-only edit (WP-1
    completion condition 7) still aligns to the same statement and keeps
    the block attached to it. `is_first` (true only for `body[0]` of the
    scope `stmt` itself belongs to, i.e. exactly design §4.1 (1)'s own
    docstring shape via `_is_docstring_stmt`) is tokenized by shape only,
    never its text, so editing docstring wording alone never perturbs the
    alignment of the statements around it -- a bare string Expr NOT at
    that position is an ordinary statement, content-sensitive like any
    other (低: the SAME `_is_docstring_stmt` definition (1) uses, not a
    separate one). Every other statement is tokenized from a DEEP COPY
    recursively stripped of every docstring it contains, anywhere in its
    own subtree, via `_strip_docstrings_for_ast` (重大 2: without this, a
    docstring buried inside a non-scope compound statement -- `if`/`try`,
    which this alignment's shallow per-scope walk never descends into as
    its own scope -- still leaks into the ENCLOSING statement's `ast.dump`,
    so editing it would wrongly perturb an unrelated sibling block's own
    key). The real tree is never touched -- only the copy is stripped."""
    if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return ("func", stmt.name)
    if isinstance(stmt, ast.ClassDef):
        return ("class", stmt.name)
    if isinstance(stmt, ast.Assign):
        return ("assign", tuple(ast.dump(t) for t in stmt.targets))
    if isinstance(stmt, (ast.AnnAssign, ast.AugAssign)):
        return ("assign", ast.dump(stmt.target))
    if is_first and _is_docstring_stmt(stmt):
        return ("docstring",)
    return ("stmt", ast.dump(_strip_docstrings_for_ast(copy.deepcopy(stmt))))


def _align_scope_bodies(old_body: list[ast.stmt], new_body: list[ast.stmt]) -> dict[int, int]:
    """R-63 WP-1 (J-1): aligns one scope's OLD body to its NEW body via a
    token-per-statement `difflib.SequenceMatcher` (`autojunk=False`),
    returning NEW-body-index -> OLD-body-index for every position inside a
    matching block. A new-body index absent from the mapping has no OLD
    counterpart at that position: either it is a statement added by this
    diff, or one moved here from elsewhere in the same body -- either way
    J-2 treats it as "new" for anchoring purposes."""
    old_tokens = [_token_for_stmt(s, i == 0) for i, s in enumerate(old_body)]
    new_tokens = [_token_for_stmt(s, i == 0) for i, s in enumerate(new_body)]
    mapping: dict[int, int] = {}
    matcher = difflib.SequenceMatcher(None, old_tokens, new_tokens, autojunk=False)
    for match in matcher.get_matching_blocks():
        for k in range(match.size):
            mapping[match.b + k] = match.a + k
    return mapping


def _replace_pairs(old_body: list[ast.stmt], new_body: list[ast.stmt]) -> dict[int, int]:
    """R-89 (docs/design/CODE_COMMENT_PROVENANCE_V1.md §4.1 (2), D-1): maps
    NEW-body-index -> OLD-body-index for statement pairs that the SAME
    token alignment `_align_scope_bodies` uses (`_token_for_stmt`,
    `difflib.SequenceMatcher`) puts in a `replace` opcode -- a rewrite of
    one statement into another at the same relative position, never an
    `insert`/`delete`/`equal` one (those are `_align_scope_bodies`'s own
    job; this function reads the SAME matcher output but keeps a disjoint
    half of it, and never changes what `_align_scope_bodies` itself
    returns -- J-1's own OLD/NEW correspondence is untouched).

    A `replace` region of old length `i2-i1` and new length `j2-j1` pairs
    only the first `min(i2-i1, j2-j1)` positions, old i-th with new i-th
    (a length mismatch leaves the remainder unpaired, falling through to
    the ordinary insert/delete handling in `_plain_block_keys`). A pair is
    kept only when the two statements are the SAME AST node type, and --
    for `def`/`class` specifically -- also share the SAME name: renaming a
    function or substituting a different kind of statement is not treated
    as "the same statement, rewritten" (design D-1's own limitation, D-2
    (vi): substituting a DIFFERENT statement of the SAME kind at that
    position, e.g. calling a different function, is indistinguishable
    from an in-place rewrite by this rule alone -- a block anchored there
    stays paired to its old key even though the statement it now precedes
    says something else)."""
    old_tokens = [_token_for_stmt(s, i == 0) for i, s in enumerate(old_body)]
    new_tokens = [_token_for_stmt(s, i == 0) for i, s in enumerate(new_body)]
    pairs: dict[int, int] = {}
    matcher = difflib.SequenceMatcher(None, old_tokens, new_tokens, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag != "replace":
            continue
        for k in range(min(i2 - i1, j2 - j1)):
            oi, ni = i1 + k, j1 + k
            old_stmt, new_stmt = old_body[oi], new_body[ni]
            if type(old_stmt) is not type(new_stmt):
                continue
            if isinstance(old_stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) \
                    and old_stmt.name != new_stmt.name:
                continue
            pairs[ni] = oi
    return pairs


def _plain_block_keys(old_source: str, new_source: str,
                       new_blocks: list[Block]) -> list[tuple[tuple[str, str], bool]]:
    """R-63 WP-1 (D-1, J-1, J-2); extended by R-89 (D-1) for the `replace`-
    pair byte-identity gate below. The (scope, anchor) key and "deletable"
    flag used for the CH-ID-less half of §4.1 (2), for every block in
    `new_blocks` (a block WITH a CH-ID never reads this list -- its
    correspondence is decided earlier, by scope name only).

    A block whose own scope does not exist in the OLD tree at all (D-1: the
    scope itself is new) is always deletable -- describing a brand-new
    symbol can never collide with an existing key, because no OLD block is
    ever keyed under a scope OLD does not have. Verbatim-copying an
    existing block to sit beside a new symbol is allowed by this same rule
    too, as long as the original stays put: 原本が残る限り許す (the
    original's OWN key is unaffected, since the copy's key routes to
    wherever it sits, D-1's "new symbol" scope).

    Otherwise the block's key is the OLD index of the first statement,
    after the block, that has an OLD counterpart under the scope's J-1
    alignment (`"<end>"` if none) -- J-2's "transparent" new-statement
    skip. It is deletable exactly when the statement it immediately
    precedes, in the NEW body, has NO OLD counterpart (D-2: a block placed
    immediately before an EXISTING statement is never deletable, even if a
    later, unrelated new statement follows somewhere in the same body).

    R-89 (design §4.1 (2), D-1): when that immediately-following statement
    has no J-1 counterpart but IS one half of a `_replace_pairs` pair
    (same AST node type; same name too, for `def`/`class`), the block is
    treated as pointing at the SAME old key as before -- but only when
    there is an OLD block, in that SAME internal scope (`#k`-disambiguated,
    `_internal_scope_and_anchor_for_block` -- R-89),
    sitting at that exact old index, whose own text (dedented, byte-for-
    byte) matches the new block's. This byte-identity gate is load-
    bearing: rewriting the following statement alone can never smuggle a
    DIFFERENT block's text past an unrelated old block's key, because the
    gate only ever recognizes the block's own, unmodified original AT THE
    SAME internal scope -- a block moved between two same-named sibling
    scopes (a `@property`/`@x.setter` pair, an `@overload` group, two
    same-named module-level `def`s) is never excused by this gate even
    when both scopes' own following statements were independently
    rewritten, because their internal identities differ even though their
    DISPLAY names collide. Editing the block's own text is still an
    unaccounted-for change (falls through, unpaired, to the ordinary
    forward search below) even when the following statement is a
    `replace` partner.

    The scope used to key and align (code review round 1, 重大 1) is the
    `#k`-disambiguated INTERNAL identity (`_scope_bodies_by_identity` /
    `_internal_scope_key_and_body_for_block`), never the plain dotted name
    -- only the DISPLAY half of the returned key (first element) stays the
    plain dotted name, unchanged, for error text and to keep merging
    same-named siblings' surviving blocks into one comparison exactly like
    `_scope_and_anchor_for_block` always has. The byte-identity gate above
    reads the OLD tree's CH-ID-less blocks keyed by that SAME internal
    scope identity, for the reason given above -- never the plain
    scope_key."""
    old_tree = ast.parse(old_source)
    new_tree = ast.parse(new_source)
    old_scope_bodies = _scope_bodies_by_identity(old_tree)
    old_plain_blocks = [b for b in extract_all_blocks(old_source) if b.history_id is None]
    old_plain_positions = [_internal_scope_and_anchor_for_block(old_tree, b) for b in old_plain_blocks]
    alignment_cache: dict[str, dict[int, int]] = {}
    replace_pairs_cache: dict[str, dict[int, int]] = {}
    keys: list[tuple[tuple[str, str], bool]] = []
    for nb in new_blocks:
        scope_key = _scope_and_anchor_for_block(new_tree, nb)[0]
        internal_key, body = _internal_scope_key_and_body_for_block(new_tree, nb)
        if internal_key not in old_scope_bodies:
            keys.append(((scope_key, "<newscope>"), True))
            continue
        old_body = old_scope_bodies[internal_key]
        alignment = alignment_cache.get(internal_key)
        if alignment is None:
            alignment = _align_scope_bodies(old_body, body)
            alignment_cache[internal_key] = alignment
        j = next((i for i, stmt in enumerate(body) if stmt.lineno > nb.end_line), None)
        deletable = j is not None and j not in alignment
        anchor = "<end>"
        paired_anchor = None
        if deletable and j is not None:
            replace_pairs = replace_pairs_cache.get(internal_key)
            if replace_pairs is None:
                replace_pairs = _replace_pairs(old_body, body)
                replace_pairs_cache[internal_key] = replace_pairs
            oi = replace_pairs.get(j)
            if oi is not None:
                candidate = (internal_key, f"stmt#{oi}")
                if any(
                    pos == candidate and ob.dedented == nb.dedented
                    for ob, pos in zip(old_plain_blocks, old_plain_positions)
                ):
                    paired_anchor = f"stmt#{oi}"
        if paired_anchor is not None:
            anchor = paired_anchor
            deletable = False
        else:
            while j is not None and j < len(body):
                if j in alignment:
                    anchor = f"stmt#{alignment[j]}"
                    break
                j += 1
        keys.append(((scope_key, anchor), deletable))
    return keys


def _old_sequence_reachable(old_seq: list[str], new_entries: list[tuple[int, str, bool]]) -> bool:
    """R-63 WP-1 (D-1/D-2, J-2): whether `old_seq` (the surviving CH-ID-less
    OLD blocks at one (scope, anchor) key, in file order) can be produced
    from `new_entries` by deleting only entries marked deletable -- an
    order-preserving subsequence test. Each NEW entry either matches the
    next unconsumed OLD text (advancing past it) or, if deletable, is
    skipped; a non-deletable entry that matches nothing keeps this key red
    (D-2: an existing target still rejects an unaccounted-for addition)."""
    reach = {0}
    for _line, text, deletable in new_entries:
        nxt: set[int] = set()
        for i in reach:
            if i < len(old_seq) and old_seq[i] == text:
                nxt.add(i + 1)
            if deletable:
                nxt.add(i)
        reach = nxt
        if not reach:
            break
    return len(old_seq) in reach


def check_provenance_semantics(rel_path: str, old_source: str, new_source: str,
                                old_blocks: list[Block], new_blocks: list[Block],
                                companion_lookup: dict[str, str],
                                real_paths: frozenset[str],
                                identifier_set: frozenset[str] = frozenset(),
                                corrections_lookup: dict[str, list[Correction]] | None = None,
                                base_corrections_lookup: dict[str, list[Correction]] | None = None) -> list[str]:
    """design §4.1 (2)+(3)+(4), correspondence taken via CH-ID (v0.3).

    v0.4 P3 (review rounds 2-3): a new block WITHOUT a CH-ID is compared
    against the OLD blocks left over after CH-ID claims are resolved,
    keyed by (scope, anchor) (see `_scope_and_anchor_for_block`), as an
    ORDERED sequence per key -- not a multiset. This catches: two blocks
    swapped in place (a multiset comparison would miss it, {A, B} == {B,
    A}); a block moved to precede a DIFFERENT statement in the SAME scope
    (the anchor changes even when scope-level order alone would not
    reveal it, e.g. a single block in that scope); a duplicate identical
    block silently dropped (the sequence's length changes); and a block
    rewritten in place without a CH-ID (a SEPARATE, blank-line-detached
    block nearby claiming to have moved the whole original text does not
    give the rewritten text an old counterpart, so it is an unaccounted-
    for "extra" element).

    CH-ID matching itself (review round 4, ":704-707", tightened round 5)
    requires an unconsumed old block in the SAME SCOPE as the referencing
    new block, in file order -- there is NO cross-scope fallback. A
    scope-blind "first match anywhere" would let a reference in the wrong
    scope hide behind a byte-identical block that happens to live
    somewhere else entirely (e.g. a block silently relocated from f to g,
    then re-labeled as if it had "moved via history" from g).

    Q-4 supervisor ruling (0c): if the BASIS block for a new CH-ID
    reference ALREADY carries that same id (it was migrated before and is
    being mechanically reduced further now), no new id is allocated and
    the existing companion section is never rewritten (D-1). Instead: (a)
    every SENTENCE of the basis block's own retained text must already
    appear, verbatim, among the companion's sentences (the companion is a
    strict superset -- the snapshot from the ORIGINAL, earlier move); (b)
    the new block's retained text must be an allowed (3)(4)(6)+§9
    reduction of the BASIS block's retained text (not of the full
    companion text, which may hold sentences the basis block no longer
    even has).

    change set 0g: `corrections_lookup` (§9's append-only correction
    records, `_parse_corrections`) is applied to a CH-ID's companion text
    -- via `_apply_corrections` -- BEFORE it is used as the "basis" for
    any `_is_allowed_reduction`/`_first_protected_sentence` call below.
    The companion's raw fenced content itself is never rewritten by this;
    only the in-memory basis text used for derivability is corrected. A
    correction whose own `old` sentence cannot be found (exactly once) in
    the basis is reported here (§9f) and that block's checks are skipped
    for this CH-ID, rather than silently falling back to the uncorrected
    (and, by construction, now-wrong) basis.

    design docs/design/CODE_COMMENT_PROVENANCE_V1.md §9.3 (work order
    docs/work-orders/WORK_ORDER_R68_PROVENANCE_SAME_CHANGESET_REWORD_V1.md):
    `base_corrections_lookup` carries the BASIS revision's own correction
    records for the re-edit path only -- `None` (the default) is treated
    as identical to `corrections_lookup` itself, reproducing the
    pre-existing judgment (every correction is already committed, nothing
    pending). When it differs from `corrections_lookup`, a CH-ID's
    working-tree correction list must extend the basis list by a
    verbatim prefix (`_correction_prefix_mismatch`); the remainder
    (pending) is applied to the re-edited block's OWN current wording,
    never to the companion's original text, so a same-changeset reword
    can be recorded and applied together."""
    errors: list[str] = []
    consumed = [False] * len(old_blocks)
    old_positions = _block_positions(old_source, old_blocks)
    new_positions = _block_positions(new_source, new_blocks)
    corrections_lookup = corrections_lookup or {}
    base_corrections_lookup = corrections_lookup if base_corrections_lookup is None else base_corrections_lookup

    def _corrected_basis(text: str, ch_id: str, kind: str) -> tuple[str | None, str | None]:
        basis, err = _apply_corrections(
            kind, text, corrections_lookup.get(ch_id, []), real_paths, identifier_set
        )
        return (None, err) if err else (basis, None)

    for j, nb in enumerate(new_blocks):
        if nb.history_id is None:
            continue
        ch_id = nb.history_id
        companion_text = companion_lookup.get(ch_id)
        if companion_text is None:
            errors.append(
                f"FAIL (§4.1 (2)) {rel_path}:{nb.start_line} companion section for {ch_id} not found"
            )
            continue
        nb_scope = new_positions[j][0]

        # Q-4: the basis block for this same CH-ID already exists (a
        # re-edit of an already-migrated block), takes priority over a
        # fresh "first move" match.
        reedit_candidates = [
            i for i, ob in enumerate(old_blocks)
            if not consumed[i] and ob.history_id == ch_id and old_positions[i][0] == nb_scope
        ]
        if reedit_candidates:
            match_idx = reedit_candidates[0]
            ob = old_blocks[match_idx]
            consumed[match_idx] = True

            # design §9.3 rule 2: the basis revision's own correction
            # list must be a verbatim prefix of the working tree's list;
            # the remainder (pending) is what a same-changeset reword may
            # apply below (rule 3).
            working_corrections = corrections_lookup.get(ch_id, [])
            base_corrections = base_corrections_lookup.get(ch_id, [])
            prefix_err = _correction_prefix_mismatch(base_corrections, working_corrections)
            if prefix_err:
                errors.append(f"FAIL (§9.3 (2)) {rel_path}:{nb.start_line} {ch_id}: {prefix_err}")
                continue
            pending = working_corrections[len(base_corrections):]

            # design §9.3 rule 4: EVERY working-tree correction (base and
            # pending together), applied in file order to the companion's
            # own pristine text, must succeed here -- unconditionally, for
            # every re-edited block, whether or not it still retains any
            # text. It is independent of the base/pending basis built
            # below, and when pending is empty the two coincide.
            _, full_corr_err = _corrected_basis(companion_text, ch_id, ob.kind)
            if full_corr_err:
                errors.append(f"FAIL (§9f) {rel_path}:{nb.start_line} {ch_id}: {full_corr_err}")
                continue

            # Containment (fixed per reviewer report on q4repo/rev-cs2,
            # postgres.py CH-0001 false-red): the basis block need not
            # sentence-match the companion VERBATIM -- change set 1 (and
            # any earlier one) may already have applied (3)(4)(6)+§9 to
            # it, so its retained text is only a FURTHER reduction of the
            # companion's original, unreduced text. Require that it be
            # DERIVABLE from the companion via the same allowed-reduction
            # machinery, not that every sentence appear byte-for-byte.
            # design §9.3 rule 1: this basis uses only the BASIS
            # revision's own corrections (never the pending ones).
            if ob.retained_text:
                basis_text, corr_err = _apply_corrections(
                    ob.kind, companion_text, base_corrections, real_paths, identifier_set
                )
                if corr_err:
                    errors.append(f"FAIL (§9f) {rel_path}:{nb.start_line} {ch_id}: {corr_err}")
                    continue
                ok, reason = _is_allowed_reduction(ob.kind, basis_text, ob.retained_text, real_paths, identifier_set)
                if not ok:
                    errors.append(
                        f"FAIL (§4.1 (2)) {rel_path}:{nb.start_line} basis block for {ch_id} is "
                        f"not derivable from the existing companion section: {reason}"
                    )
                    continue

            # design §9.3 rule 3: the stage-B basis is the basis block's
            # OWN current wording, with only the PENDING corrections
            # applied -- never the companion's full, uncorrected-by-base
            # text, so a sentence a prior change set already deleted can
            # never be revived through a pending correction that happens
            # to still name it.
            pending_basis, pending_err, pending_section = _apply_pending_corrections(
                ob.kind, ob.retained_text, pending, real_paths, identifier_set
            )
            if pending_err:
                # `pending_section` is `_apply_pending_corrections`'s own
                # call: `§9.4` for its rule 1 (0-for-0, but resolvable or
                # ambiguous among the basis's own reductions of `old`)
                # errors, `§9f` for every other one -- never guessed here
                # from the message text.
                errors.append(f"FAIL ({pending_section}) {rel_path}:{nb.start_line} {ch_id}: {pending_err}")
                continue
            if nb.retained_text:
                ok, reason = _is_allowed_reduction(nb.kind, pending_basis, nb.retained_text, real_paths, identifier_set)
                if not ok:
                    errors.append(f"FAIL (§4.1 (3)) {rel_path}:{nb.start_line} {reason}")
            elif pending_basis.strip():
                # change set 0d review round (item 1): nothing kept in
                # code at all -- the basis's own retained text (already
                # itself a reduction, and now carrying any pending
                # correction, design §9.3 rule 4) is being moved away in
                # full; every one of ITS sentences must be checked too.
                protected = _first_protected_sentence(pending_basis, ob.kind, real_paths, identifier_set)
                if protected is not None:
                    errors.append(
                        f"FAIL (§4.1 (3)) {rel_path}:{nb.start_line} cannot move the whole block away "
                        f"-- it still carries a protected reference: {protected!r}"
                    )
            continue

        same_scope = [
            i for i, ob in enumerate(old_blocks)
            if not consumed[i]
            and ob.history_id is None
            and ob.dedented == companion_text
            and old_positions[i][0] == nb_scope
        ]
        # design v0.4 P3 (review round 5, supervisor ruling): NO cross-
        # scope fallback -- a CH-ID's companion must byte-match an
        # unconsumed old block in the SAME scope as the referencing new
        # block, or this is a FAIL. Falling back to any unconsumed old
        # block elsewhere would let a reference in the wrong scope (e.g.
        # a block silently relocated from f to g, then re-labeled as if
        # it had "moved via history" from g) hide behind a byte-identical
        # block that happens to live somewhere else entirely.
        match_idx = same_scope[0] if same_scope else None
        if match_idx is None:
            errors.append(
                f"FAIL (§4.1 (2)) {rel_path}:{nb.start_line} companion {ch_id} does not "
                f"byte-match any (remaining) original block in the same scope ({nb_scope!r})"
            )
            continue
        consumed[match_idx] = True
        basis_text, corr_err = _corrected_basis(companion_text, ch_id, nb.kind)
        if corr_err:
            errors.append(f"FAIL (§9f) {rel_path}:{nb.start_line} {ch_id}: {corr_err}")
            continue
        if nb.retained_text:
            ok, reason = _is_allowed_reduction(nb.kind, basis_text, nb.retained_text, real_paths, identifier_set)
            if not ok:
                errors.append(f"FAIL (§4.1 (3)) {rel_path}:{nb.start_line} {reason}")
        else:
            # change set 0d review round (item 1): first move, nothing
            # kept in code -- check the FULL companion text (everything
            # that is disappearing from the source) sentence by sentence.
            protected = _first_protected_sentence(basis_text, nb.kind, real_paths, identifier_set)
            if protected is not None:
                errors.append(
                    f"FAIL (§4.1 (3)) {rel_path}:{nb.start_line} cannot move the whole block away "
                    f"-- it still carries a protected reference: {protected!r}"
                )

    # Q-4: an old block that carried its OWN CH-ID and was never consumed
    # (no new block claimed it -- e.g. its id was swapped for a different
    # section's id) gets its own clear error, instead of silently falling
    # into the CH-ID-less "plain sequence" comparison below (where it does
    # not belong and would still fail, just less legibly).
    for i, ob in enumerate(old_blocks):
        if consumed[i] or ob.history_id is None:
            continue
        errors.append(
            f"FAIL (§4.1 (2)) {rel_path}:{ob.start_line} basis block's own {ob.history_id} "
            "reference was not matched by any new block (a different CH-ID was substituted?)"
        )
        consumed[i] = True

    remaining_old_by_key: dict[tuple[str, str], list[tuple[int, str]]] = {}
    for i, ob in enumerate(old_blocks):
        if consumed[i]:
            continue
        remaining_old_by_key.setdefault(old_positions[i], []).append((ob.start_line, ob.dedented))

    # R-63 WP-1 (D-1/D-2, J-1, J-2): a CH-ID-less new block's key is no
    # longer its own NEW-tree structural position (`new_positions`, which
    # only the CH-ID-matching code above still uses, for `nb_scope`) but
    # the OLD-aligned key from `_plain_block_keys`, together with whether
    # this particular block is allowed to be an unmatched addition.
    plain_keys = _plain_block_keys(old_source, new_source, new_blocks)
    new_plain_by_key: dict[tuple[str, str], list[tuple[int, str, bool]]] = {}
    for i, nb in enumerate(new_blocks):
        if nb.history_id is not None:
            continue
        key, deletable = plain_keys[i]
        new_plain_by_key.setdefault(key, []).append((nb.start_line, nb.dedented, deletable))

    for key in sorted(set(remaining_old_by_key) | set(new_plain_by_key)):
        old_seq = [text for _line, text in remaining_old_by_key.get(key, [])]
        new_entries = new_plain_by_key.get(key, [])
        new_seq = [text for _line, text, _deletable in new_entries]
        if _old_sequence_reachable(old_seq, new_entries):
            continue
        line = new_entries[0][0] if new_entries else remaining_old_by_key[key][0][0]
        errors.append(
            f"FAIL (§4.1 (2)) {rel_path}:{line} scope/anchor {key!r}: the sequence of CH-ID-less "
            f"blocks changed (old {len(old_seq)}, new {len(new_seq)}) -- a block was added, "
            "removed, or moved to a different statement without a CH-ID reference"
        )
    return errors


def run_base(repo_root: Path, rev: str, rel_paths: list[str], out=sys.stdout, err=sys.stderr) -> int:
    had_failure = False
    total_new_blocks = 0
    companion_cache: dict[str, dict[str, str]] = {}
    corrections_cache: dict[str, dict[str, list[Correction]]] = {}
    # design §9.3 rule 1: the BASIS revision's own correction records,
    # read once per peer via `rev` (never the working tree) -- the
    # re-edit path's stage-A basis and prefix check (§9.3 rules 1-2).
    base_corrections_cache: dict[str, dict[str, list[Correction]]] = {}
    # design §9 rule 2: real-path membership is read from the BASIS
    # revision's own tree, once per invocation (never the working tree).
    real_paths = _tree_paths(repo_root, rev)
    # change set 0e predicate B rule 5: identifier membership is read
    # from the BASIS revision's tree too, once per invocation.
    identifier_set = _tracked_identifier_set(repo_root, rev)

    for rel_path in rel_paths:
        old_source = _git_show(repo_root, rev, rel_path)
        if old_source is None:
            print(f"FAIL (§4.1) {rel_path}: could not read {rel_path} at {rev} via git show", file=out)
            had_failure = True
            continue
        try:
            new_source = (repo_root / rel_path).read_text(encoding="utf-8")
        except OSError as exc:
            print(f"FAIL (§4.1) {rel_path}: could not read working-tree file ({exc})", file=out)
            had_failure = True
            continue

        try:
            old_sig = ast_signature(old_source)
            new_sig = ast_signature(new_source)
        except SyntaxError as exc:
            print(f"FAIL (§4.1 (1)) {rel_path}: could not parse ({exc})", file=out)
            had_failure = True
            continue
        if old_sig != new_sig:
            line = _first_diff_line(old_source, new_source)
            print(f"FAIL (§4.1 (1)) {rel_path}:{line} code changed (AST differs, docstrings excluded)", file=out)
            had_failure = True

        for lineno, line_text, pat in check_no_added_history_tokens(old_source, new_source):
            print(
                f"FAIL (§4.1 (5)) {rel_path}:{lineno} added line carries a history token "
                f"({pat}): {line_text.strip()!r}",
                file=out,
            )
            had_failure = True

        peer = Path(rel_path).parts[0]
        if peer not in companion_cache:
            companion_cache[peer] = _load_companion_lookup(repo_root, peer)
        companion_lookup = companion_cache[peer]
        if peer not in corrections_cache:
            corrections_lookup, corrections_errors = _load_corrections_lookup(repo_root, peer)
            for corr_err in corrections_errors:
                print(f"FAIL (§9f) {corr_err}", file=out)
                had_failure = True
            corrections_cache[peer] = corrections_lookup
        corrections_lookup = corrections_cache[peer]
        if peer not in base_corrections_cache:
            base_corrections_lookup, base_corrections_errors = _load_corrections_lookup(repo_root, peer, rev=rev)
            for corr_err in base_corrections_errors:
                print(f"FAIL (§9f) {corr_err}", file=out)
                had_failure = True
            base_corrections_cache[peer] = base_corrections_lookup
        base_corrections_lookup = base_corrections_cache[peer]

        new_blocks = extract_all_blocks(new_source)
        old_blocks = extract_all_blocks(old_source)
        total_new_blocks += len(new_blocks)

        for msg in check_provenance_semantics(
            rel_path, old_source, new_source, old_blocks, new_blocks, companion_lookup, real_paths,
            identifier_set, corrections_lookup, base_corrections_lookup,
        ):
            print(msg, file=out)
            had_failure = True

        # change set 0e §2: for every block with a companion (moved or
        # reused), the companion is the pristine basis with the ORIGINAL
        # line wrapping -- check it for broken line-wrap joins.
        for nb in new_blocks:
            if nb.history_id is None:
                continue
            basis_text = companion_lookup.get(nb.history_id)
            if basis_text is None:
                continue
            for correct, broken in find_broken_line_wrap_joins(nb.kind, basis_text, nb.dedented, identifier_set):
                print(
                    f"FAIL (§9e) {rel_path}:{nb.start_line} broken line-wrap join for "
                    f"{nb.history_id}: {broken!r} should be {correct!r} (zero space)",
                    file=out,
                )
                had_failure = True
            # change set 0g review round 2: the basis's own `#:` Sphinx-
            # style comment marker must not have been silently lost.
            # Checked against `nb.retained_text` (the block's own content
            # lines), never `nb.dedented` -- `dedented` still carries the
            # trailing `# history: CH-XXXX` marker line, which is ALWAYS
            # plain `#` by construction and would otherwise make every
            # single-line-retained `#:` block a false positive.
            if (
                nb.kind == "comment"
                and nb.retained_text
                and _is_colon_style_block(basis_text)
                and not _is_colon_style_block(nb.retained_text)
            ):
                print(
                    f"FAIL (§9f) {rel_path}:{nb.start_line} {nb.history_id}: "
                    "'#:' Sphinx-style comment marker lost (basis used '#:' lines, new block does not)",
                    file=out,
                )
                had_failure = True

    if had_failure:
        return 1
    print(f"comment provenance OK: {total_new_blocks} blocks checked", file=out)
    return 0


# ---------------------------------------------------------------------------
# --register: design §4.2, items 1-6.
# ---------------------------------------------------------------------------
def _iter_peer_py_files(repo_root: Path, peer: str) -> list[Path]:
    src_dir = repo_root / peer / PEER_SRC_DIRS[peer]
    if not src_dir.is_dir():
        return []
    return sorted(p for p in src_dir.rglob("*.py") if p.is_file())


def _referenced_ids_in_source(source: str) -> set[str]:
    ids: set[str] = set()
    for line in source.splitlines():
        m = _HASH_REF_RE.match(line.strip())
        if m:
            ids.add(m.group(1))
    for m in _DOC_HIST_LINE_RE.finditer(source):
        ids.add(m.group(1))
    return ids


def _reference_format_violations(source: str) -> list[tuple[int, str]]:
    """A line containing anything that LOOKS LIKE a CH-ID (any digit
    length, design v0.4: a 5+-digit `CH-NNNNN` is a format violation, not
    silently ignored) but whose stripped form does not match either
    canonical whole-line form is a violation."""
    violations: list[tuple[int, str]] = []
    for i, line in enumerate(source.splitlines(), start=1):
        if _CH_ID_LOOSE_RE.search(line):
            stripped = line.strip()
            if _HASH_REF_RE.match(stripped) or _DOC_HIST_LINE_RE.match(stripped):
                continue
            violations.append((i, line))
    return violations


def _source_has_doc_access(source: str) -> bool:
    """design §4.2 (5), v0.4 review fix (f), widened in review round 2:
    AST name resolution, not a source-text regex -- detects `__doc__`
    access (`x.__doc__` or a bare `__doc__`), `getattr(x, "__doc__")`,
    `inspect.getdoc` / `inspect.getsource` / `inspect.getcomments` (any
    object, not just literally named `inspect`), and the same three names
    called bare after `from inspect import X [as Y]` -- resolving the
    alias `Y` back to its real name `X` before checking it against
    `_DOC_ACCESS_ATTRS`, rather than checking the alias itself (a plain
    `from inspect import getsource as gs; gs(...)` was previously missed
    because "gs" is not one of the three names). An unparsable file is
    treated as a hit (fail loud), never as "nothing to check"."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return True
    # local name -> real `inspect.<name>` target for `from inspect import
    # X [as Y]` (Y is the key, X is the value -- may be identical).
    from_inspect: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "inspect":
            for alias in node.names:
                from_inspect[alias.asname or alias.name] = alias.name
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == "__doc__":
            return True
        if isinstance(node, ast.Name) and node.id == "__doc__":
            return True
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr in _DOC_ACCESS_ATTRS:
                return True
            if isinstance(func, ast.Name) and from_inspect.get(func.id) in _DOC_ACCESS_ATTRS:
                return True
            if isinstance(func, ast.Name) and func.id == "getattr" and len(node.args) >= 2:
                second = node.args[1]
                if isinstance(second, ast.Constant) and second.value == "__doc__":
                    return True
    return False


def _docstring_dependent_hits(repo_root: Path) -> list[str]:
    hits: list[str] = []
    for peer in PEERS:
        for path in _iter_peer_py_files(repo_root, peer):
            source = path.read_text(encoding="utf-8", errors="replace")
            if _source_has_doc_access(source):
                hits.append(str(path.relative_to(repo_root)))
    return hits


def run_register(repo_root: Path, out=sys.stdout, err=sys.stderr) -> int:
    had_failure = False

    def fail(msg: str) -> None:
        nonlocal had_failure
        print(msg, file=out)
        had_failure = True

    pair_path = repo_root / "docs" / "code-history" / "pair.md"
    pair_sections = _iter_companion_sections(pair_path) if pair_path.is_file() else []
    pair_headings = {ch_id for ch_id, _body in pair_sections}

    # design §4.2-1 (v0.4 review fix (d)): resolved per peer, against that
    # peer's OWN companion dir plus pair.md -- never the other peer's dir.
    peer_own_sections: dict[str, list[tuple[str, str, Path]]] = {}
    all_sections: list[tuple[str, str, Path]] = []
    for peer in PEERS:
        peer_dir = repo_root / "docs" / "code-history" / peer
        secs: list[tuple[str, str, Path]] = []
        if peer_dir.is_dir():
            for path in sorted(peer_dir.glob("*.md")):
                for ch_id, body in _iter_companion_sections(path):
                    secs.append((ch_id, body, path))
                    all_sections.append((ch_id, body, path))
        peer_own_sections[peer] = secs
    for ch_id, body in pair_sections:
        all_sections.append((ch_id, body, pair_path))

    # §4.2-2: a CH-ID heading is unique across ALL companion files combined.
    occ_paths: dict[str, list[Path]] = {}
    for ch_id, _body, path in all_sections:
        occ_paths.setdefault(ch_id, []).append(path)
    for ch_id, paths in sorted(occ_paths.items()):
        if len(paths) > 1:
            locs = ", ".join(str(p.relative_to(repo_root)) for p in paths)
            fail(f"FAIL (§4.2 2) {ch_id} heading appears more than once: {locs}")

    # §4.2-3: every OCCURRENCE (not just the first) is non-empty, has the 3
    # required lines, and has a fenced block (v0.4 review fix (d)).
    for ch_id, body, path in all_sections:
        rel = path.relative_to(repo_root)
        if not body.strip():
            fail(f"FAIL (§4.2 3) {rel} {ch_id}: section is empty")
            continue
        for name, pat in _REQUIRED_SECTION_LINES.items():
            if not pat.search(body):
                fail(f"FAIL (§4.2 3) {rel} {ch_id}: missing required '{name}' line")
        if _fenced_content(body) is None:
            fail(f"FAIL (§4.2 3) {rel} {ch_id}: section has no fenced block")

    # §9f (change set 0g): every correction entry appended under a CH-ID
    # section, in ANY companion file, must itself be well-formed (date,
    # reason, and a non-empty old/new fenced block each) -- `--register`
    # is where this format is validated; whether a correction's `old`
    # sentence actually occurs in the basis is a `run_base`/rev-vs-itself
    # concern (it needs the block's own kind and the current source).
    for ch_id, body, path in all_sections:
        _corrections, corr_errors = _parse_corrections(ch_id, path, body)
        for corr_err in corr_errors:
            fail(f"FAIL (§9f) {corr_err}")

    referenced_by_peer: dict[str, set[str]] = {}
    total_referenced: set[str] = set()
    for peer in PEERS:
        refs: set[str] = set()
        occurrence_total: dict[str, int] = {}
        for path in _iter_peer_py_files(repo_root, peer):
            source = path.read_text(encoding="utf-8", errors="replace")
            for line in source.splitlines():
                m = _HASH_REF_RE.match(line.strip())
                if m:
                    occurrence_total[m.group(1)] = occurrence_total.get(m.group(1), 0) + 1
                    refs.add(m.group(1))
            for m in _DOC_HIST_LINE_RE.finditer(source):
                occurrence_total[m.group(1)] = occurrence_total.get(m.group(1), 0) + 1
                refs.add(m.group(1))
            for lineno, line in _reference_format_violations(source):
                rel = path.relative_to(repo_root)
                fail(f"FAIL (§4.2 4) {rel}:{lineno} non-canonical CH-ID reference form: {line.strip()!r}")
        # §4.2-3 (v0.4 review fix (d)): counts every occurrence across every
        # file in the peer, not just distinct files -- 2 files with the
        # same ID once each, and 1 file with the same ID twice, both trip
        # this the same way (design requires exactly 1 occurrence total).
        for ch_id, count in sorted(occurrence_total.items()):
            if count > 1:
                fail(f"FAIL (§4.2 3) {peer}: {ch_id} appears {count} times in src/ (expected exactly once)")
        referenced_by_peer[peer] = refs
        total_referenced |= refs

    for peer in PEERS:
        own_headings = {ch_id for ch_id, _b, _p in peer_own_sections[peer]}
        companion_ids_for_peer = own_headings | pair_headings
        for ch_id in sorted(referenced_by_peer[peer] - companion_ids_for_peer):
            fail(f"FAIL (§4.2 1) {peer}: {ch_id} referenced in src/ but has no companion section")
        for ch_id in sorted(own_headings - referenced_by_peer[peer]):
            fail(f"FAIL (§4.2 1) {peer}: {ch_id} companion section is an orphan (not referenced in src/)")

    # pair.md (v0.4 review fix (d)): a registered ID must be referenced by
    # BOTH peers' src/ exactly once each -- neither side is an orphan.
    for ch_id in sorted(pair_headings):
        in_r2 = ch_id in referenced_by_peer["r2db-api"]
        in_mitate = ch_id in referenced_by_peer["MitateDB-api"]
        if not in_r2 and not in_mitate:
            fail(f"FAIL (§4.2 1) pair.md: {ch_id} is an orphan (referenced by neither peer)")
        elif in_r2 != in_mitate:
            side = "r2db-api" if in_r2 else "MitateDB-api"
            fail(f"FAIL (§4.2 1) pair.md: {ch_id} is referenced only by {side} (expected both peers)")

    # A plain (non-pair.md) ID must stay peer-exclusive: the same CH-ID
    # referenced by BOTH peers' src/ without a pair.md registration is a
    # collision, not a legitimate shared id (v0.4 review fix (d)).
    both = referenced_by_peer["r2db-api"] & referenced_by_peer["MitateDB-api"]
    for ch_id in sorted(both - pair_headings):
        fail(f"FAIL (§4.2 1) {ch_id} is referenced by both peers' src/ but is not registered in pair.md")

    # §4.2-5: docstring-dependent construct set must equal the frozen baseline.
    hits = _docstring_dependent_hits(repo_root)
    if set(hits) != _DOCSTRING_DEPENDENT_BASELINE:
        for h in sorted(hits):
            fail(f"FAIL (§4.2 5) unexpected docstring-dependent construct in {h}")

    # §4.2-6: non-emptiness, counted across BOTH peers combined.
    if len(total_referenced) < MIN_CH_IDS:
        fail(f"FAIL (§4.2 6) total CH-ID count {len(total_referenced)} < MIN_CH_IDS {MIN_CH_IDS}")

    scanned_count = sum(len(_iter_peer_py_files(repo_root, peer)) for peer in PEERS)
    if had_failure:
        print("check_comment_provenance --register FAILED", file=out)
        return 1
    print(
        f"comment provenance register OK: {scanned_count} files scanned, "
        f"{len(total_referenced)} CH-IDs",
        file=out,
    )
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    parser = argparse.ArgumentParser(prog="check_comment_provenance.py")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--base", metavar="REV", help="git revision to diff comments/docstrings against")
    mode.add_argument("--register", action="store_true", help="run the standing docs/code-history register checks")
    parser.add_argument("paths", nargs="*", help="source paths (only with --base)")
    args = parser.parse_args(argv)

    if args.register:
        if args.paths:
            print("error: --register takes no path arguments", file=sys.stderr)
            return 2
        return run_register(REPO_ROOT)

    if not args.paths:
        print("error: --base requires at least one <src path>", file=sys.stderr)
        return 2
    return run_base(REPO_ROOT, args.base, args.paths)


if __name__ == "__main__":
    sys.exit(main())
