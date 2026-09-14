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
"""
from __future__ import annotations

import argparse
import ast
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
_PROTECTED_ID_PREFIXES: tuple[str, ...] = ("SI-", "C-", "CCR-")
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


def _clean_filename_candidate(raw: str) -> str:
    text = raw[1:-1] if raw.startswith("`") and raw.endswith("`") and len(raw) >= 2 else raw
    return re.sub(r"\s+", "", text)


def _filename_candidates(text: str) -> list[str]:
    return [m.group(0) for m in _FILENAME_CANDIDATE_RE.finditer(text)]


def _is_real_filename_candidate(raw: str, real_paths: frozenset[str]) -> bool:
    cleaned = _clean_filename_candidate(raw)
    if cleaned in real_paths:
        return True
    # v0.7 follow-up supervisor ruling: a filename with NO path separator
    # (e.g. `CONTROL_MAPPING.md`, referencing the real, uniquely-named
    # `security/CONTROL_MAPPING.md`) still counts as a provenance tag if
    # its basename matches EXACTLY ONE path in the tree -- 0 matches (it
    # really doesn't exist) or >=2 matches (ambiguous, e.g. `README.md`)
    # both leave it a removable history token, same as before. `cleaned`
    # itself is compared AS-IS here (never reduced to its own basename),
    # so a "/"-containing candidate (e.g. `x/CONTROL_MAPPING.md`) can
    # never coincidentally match a real path's basename this way -- an
    # earlier, now-removed `if "/" in cleaned: return False` guard was
    # unreachable dead code given this (fixed by e2e fixture
    # test_review_slash_path_basename_match_not_real_is_green, not by a
    # guard clause).
    basename_matches = [p for p in real_paths if p.rpartition("/")[2] == cleaned]
    return len(basename_matches) == 1


def _has_real_filename_reference(text: str, real_paths: frozenset[str]) -> bool:
    return any(_is_real_filename_candidate(c, real_paths) for c in _filename_candidates(text))


_SUBSCRIPT_RE = re.compile(r"^[A-Z]{1,2}$|^\d+$")
# Matches the opaque placeholder `_strip_allowed_parens` substitutes for a
# globally pre-merged ID+branch-number pair -- never a real path segment,
# so it must never make `_looks_like_path_word` misfire on the ARTIFACT of
# that substitution (e.g. "I-6/\x00Y0\x00" for "I-6/D-5 (5)").
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
    remainder = _FILENAME_CANDIDATE_RE.sub(" ", inner)
    for chunk in re.split(r"[,;\s]+", remainder):
        if _looks_like_path_word(chunk):
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
# change set 0d review round (item 3): a line-wrap that splits an ID mid-
# token (e.g. `SI-` at the end of one comment/docstring line, `08` at the
# start of the next) must rejoin WITHOUT the usual single space, so the
# flattened text reads "SI-08" and the protected-reference / (4)/(6)
# machinery -- all of which run on this SAME flattened text -- see it as
# one token, not two. Scoped NARROWLY to an ID-shaped split (the
# accumulated text ends in an ID PREFIX -- 1-6 uppercase letters then a
# hyphen -- and the next line starts with a digit): a real-corpus check
# (r2db `postgres.py`, e.g. "confirmed-\ndestructive", "table-\nlevel")
# showed an ordinary lowercase, hyphenated English compound word wrapped
# across lines is deliberately rendered with A SPACE after the hyphen in
# this corpus's own "retained" (single-line) form -- joining EVERY
# trailing hyphen without a space would silently break those, matching
# neither the old nor the intended behavior for prose.
_HYPHEN_ID_WRAP_RE = re.compile(r"\b[A-Z]{1,6}-$")


def _join_wrapped_lines(group: list[str]) -> str:
    result = group[0]
    for line in group[1:]:
        if _HYPHEN_ID_WRAP_RE.search(result) and line[:1].isdigit():
            result += line
        else:
            result += " " + line
    return result


def _flatten_comment(text: str) -> str:
    groups: list[list[str]] = [[]]
    for line in text.splitlines():
        stripped = line.strip()
        content = stripped[1:] if stripped.startswith("#") else stripped
        if content.startswith(" "):
            content = content[1:]
        content = content.strip()
        if content == "":
            if groups[-1]:
                groups.append([])
        else:
            groups[-1].append(content)
    groups = [g for g in groups if g]
    return "\n\n".join(_join_wrapped_lines(g) for g in groups)


def _flatten_docstring(text: str) -> str:
    groups: list[list[str]] = [[]]
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == "":
            if groups[-1]:
                groups.append([])
        else:
            groups[-1].append(stripped)
    groups = [g for g in groups if g]
    return "\n\n".join(_join_wrapped_lines(g) for g in groups)


def _flatten(kind: str, text: str) -> str:
    return _flatten_comment(text) if kind == "comment" else _flatten_docstring(text)


def split_sentences(flattened_text: str) -> list[str]:
    """Splits already-flattened text (single spaces within a paragraph,
    `\\n\\n` between paragraphs) into sentences. Splits only on a sentence-
    final punctuation mark (`.?!` need trailing whitespace; `。` splits
    immediately, design v0.4, and keeps any immediately-following closing
    bracket(s) `」』）)】` attached to the sentence that just ended -- P4,
    review round 2) or a paragraph break -- never on a bare line wrap.
    Abbreviations and backtick code spans are protected so their internal
    periods never split a sentence."""
    protected = flattened_text
    placeholders: dict[str, str] = {}
    for idx, abbr in enumerate(_ABBREVIATIONS):
        token = f"\x00A{idx}\x00"
        placeholders[token] = abbr
        protected = protected.replace(abbr, token)
    for idx, span in enumerate(re.findall(r"`[^`]*`", protected)):
        token = f"\x00B{idx}\x00"
        placeholders[token] = span
        protected = protected.replace(span, token, 1)

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

    working = _FILENAME_CANDIDATE_RE.sub(
        lambda m: make(m.group(0), _is_real_filename_candidate(m.group(0), real_paths)), text
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
    if _FILENAME_CANDIDATE_RE.fullmatch(word) and not _is_real_filename_candidate(word, real_paths):
        return True
    if has_provenance_tag:
        return False
    if _BARE_ID_RE.match(word) and not word.startswith(_PROTECTED_ID_PREFIXES):
        return True
    return False


_PAREN_SPLIT_RE = re.compile(r"([,/;\s]+)")


def _strip_allowed_parens(sentence: str, real_paths: frozenset[str]) -> str:
    # An ID+branch-number pair ("D-5 (5)") is the ONLY source of a paren
    # NESTED inside another ("(I-6/D-5 (5))", design §9 row 5) -- it is
    # merged into one opaque, ALWAYS-removable placeholder across the
    # WHOLE sentence FIRST, before the outer-paren regex ever runs. This
    # keeps that regex a plain, non-nested `\(([^()]*)\)`: attempting
    # instead to make the outer regex itself nesting-aware (an earlier
    # version of this function did) risks over-matching across two
    # unrelated parenthetical groups in dense, heavily-parenthesized real
    # prose, silently deleting content between them.
    id_branch_placeholders: dict[str, str] = {}

    def merge_id_branch(m: re.Match[str]) -> str:
        tok = f"\x00Y{len(id_branch_placeholders)}\x00"
        id_branch_placeholders[tok] = m.group(0)
        return tok

    working_sentence = _ID_BRANCH_RE.sub(merge_id_branch, sentence)

    def repl(m: re.Match[str]) -> str:
        leading_ws, inner = m.group(1), m.group(2)
        has_tag = _parens_has_provenance_tag(inner, real_paths)
        slash_subscripts = _slash_id_subscripts(inner)
        working, placeholders = _premerge_tokens(inner, real_paths)
        parts = _PAREN_SPLIT_RE.split(working)
        word_positions = [i for i in range(0, len(parts), 2) if parts[i].strip()]
        if not word_positions:
            return m.group(0)

        def is_removable(i: int) -> bool:
            token = parts[i]
            if token in id_branch_placeholders:
                return True
            if token in placeholders:
                _original, is_content = placeholders[token]
                return not is_content
            return _is_removable_word(token, has_tag, real_paths, slash_subscripts)

        flags = {i: is_removable(i) for i in word_positions}
        if all(flags[i] for i in word_positions):
            return ""
        if not any(flags[i] for i in word_positions):
            return m.group(0)
        for i in sorted((i for i in word_positions if flags[i]), reverse=True):
            if i - 1 >= 0:
                del parts[i - 1 : i + 1]
            elif i + 1 < len(parts):
                del parts[i : i + 2]
            else:
                del parts[i : i + 1]

        def restore(s: str) -> str:
            for tok, (orig, _is_content) in placeholders.items():
                s = s.replace(tok, orig)
            return s

        remaining_words = [restore(parts[i]).strip() for i in range(0, len(parts), 2) if parts[i].strip()]
        if remaining_words and all(_KIND_WORD_RE.match(w) for w in remaining_words):
            return ""
        new_inner = restore("".join(parts))
        return leading_ws + "(" + new_inner + ")"

    result = re.sub(r"(\s?)\(([^()]*)\)", repl, working_sentence)
    for tok, orig in id_branch_placeholders.items():
        result = result.replace(tok, orig)
    result = re.sub(r" {2,}", " ", result)
    return result.strip()


# design v0.7 supervisor ruling (change set 0c follow-up, refined a
# second time): every operation in §4.1 (3)/(4)/(6) and §9 rules 1-4 is a
# PERMISSION ("してよい"), never an obligation. `_strip_allowed_parens`
# above computes ONE particular (maximal) reduction; the functions below
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
    inner: str, real_paths: frozenset[str], id_branch_placeholders: dict[str, str]
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
    preceding separator exactly UNLESS they end up first in the output."""
    has_tag = _parens_has_provenance_tag(inner, real_paths)
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
            return True
        if token in placeholders:
            _orig, is_content = placeholders[token]
            return not is_content
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
    words = _paren_words_removable(inner, real_paths, id_branch_placeholders)
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
        original_span = leading_ws + "(" + restore_text(inner) + ")"
        next_txt = texts[i + 1]
        if target.startswith(original_span, pos):
            pos += len(original_span)
            continue
        if (
            next_txt
            and target.startswith(next_txt, pos)
            and _paren_span_reachable(leading_ws, inner, "", real_paths, id_branch_placeholders)
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
                if _paren_span_reachable(leading_ws, inner, candidate_span, real_paths, id_branch_placeholders):
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
        if not _paren_span_reachable(leading_ws, inner, candidate_span, real_paths, id_branch_placeholders):
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
    r"\b((?!" + "|".join(re.escape(p) for p in _PROTECTED_ID_PREFIXES) + r"|WP-)"
    r"[A-Z]{1,6}-\d+[a-z]?"
    r"|WP-[0-9A-Za-z-]+)\s*(" + _BRANCH_PAREN + r")"
)
_CONNECTIVE_WORDS = frozenset({"and", "or", "、"})
_JAPANESE_CHAR_RE = re.compile(r"[぀-ヿ㐀-鿿＀-￯]")
_ANY_ID_RE = re.compile(r"\b[A-Z]{1,6}-\d+[a-z]?\b")
_NEGATION_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.ASCII | re.IGNORECASE)
    for p in (r"\bnever\b", r"\bnot\b", r"\bno\b", r"\bmust\s+not\b", r"\bdon't\b", r"\bcannot\b")
) + (re.compile("ない"), re.compile("禁止"), re.compile("しない"))


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
        if _FILENAME_CANDIDATE_RE.fullmatch(t) and not _is_real_filename_candidate(t, real_paths):
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
    remainder = _FILENAME_CANDIDATE_RE.sub(" ", text)
    for chunk in re.split(r"[,;()\s]+", remainder):
        if _looks_like_path_word(chunk):
            return True
    return False


def _label_has_provenance_marker(text: str, real_paths: frozenset[str]) -> bool:
    """Condition (1): a §4.1 (5) history token, or an unprotected bare ID
    that is NOT itself provenance-tagged elsewhere in the label."""
    if any(pat.search(text) for pat in _HISTORY_TOKEN_PATTERNS):
        return True
    ids = _ANY_ID_RE.findall(text)
    unprotected = [i for i in ids if not i.startswith(_PROTECTED_ID_PREFIXES)]
    if not unprotected:
        return False
    return not _label_provenance_tag_present(text, real_paths)


def _label_has_protected_reference(text: str, real_paths: frozenset[str]) -> bool:
    """Review-round supervisor ruling (L1/L10): a label containing a
    protected reference (SI-/C-/CCR-, or a bare ID that is provenance-
    tagged) is never removable, even if it also carries a qualifying (5)
    token elsewhere (e.g. "SI-08 WP-3:")."""
    ids = _ANY_ID_RE.findall(text)
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
    working = _ANY_ID_RE.sub("", working)
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
    ids = _ANY_ID_RE.findall(sentence)
    if any(i.startswith(_PROTECTED_ID_PREFIXES) for i in ids):
        return True
    if _SPEC_SECTION_RE.search(sentence):
        return True
    if _has_versioned_document_reference(sentence):
        return True
    if _has_real_filename_reference(sentence, real_paths):
        return True
    return False


def _first_protected_sentence(text: str, kind: str, real_paths: frozenset[str]) -> str | None:
    """change set 0d review round (item 1): when a WHOLE block is moved
    away with nothing retained in code (`retained_text` empty), the
    entire source text -- every sentence of it -- disappears from the
    code just as surely as an in-place whole-sentence deletion would;
    check it the SAME way, sentence by sentence, rather than skipping
    the check entirely just because there is no `_is_allowed_reduction`
    call to hang it on."""
    for sentence in split_sentences(_flatten(kind, text)):
        if _sentence_has_protected_reference(sentence, real_paths):
            return sentence
    return None


def _is_allowed_reduction(
    kind: str, old_full_text: str, new_retained_text: str, real_paths: frozenset[str]
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
    old_sentences = split_sentences(_flatten(kind, old_full_text))
    new_sentences = split_sentences(_flatten(kind, new_retained_text))
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
def _strip_docstrings_for_ast(tree: ast.Module) -> ast.Module:
    doc_node_types = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    for node in ast.walk(tree):
        if not isinstance(node, doc_node_types):
            continue
        if node.body:
            first = node.body[0]
            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
            ):
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


def _iter_companion_sections(path: Path) -> list[tuple[str, str]]:
    """[(CH-ID, section_body)] in file order, WITHOUT de-duplication --
    duplicate detection needs the raw list."""
    text = path.read_text(encoding="utf-8")
    headings = list(_HEADING_RE.finditer(text))
    out: list[tuple[str, str]] = []
    for i, m in enumerate(headings):
        start = m.end()
        end = headings[i + 1].start() if i + 1 < len(headings) else len(text)
        out.append((m.group(1), text[start:end]))
    return out


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


def _load_companion_lookup(repo_root: Path, peer: str) -> dict[str, str]:
    """{CH-ID: fenced block content} for one peer, merged across its
    companion dir and pair.md. Last-one-wins on a duplicate heading is
    fine here -- duplication itself is a separate --register failure."""
    merged: dict[str, str] = {}
    for path in _companion_files(repo_root, peer):
        for ch_id, body in _iter_companion_sections(path):
            content = _fenced_content(body)
            if content is not None:
                merged[ch_id] = content
    return merged


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


def check_provenance_semantics(rel_path: str, old_source: str, new_source: str,
                                old_blocks: list[Block], new_blocks: list[Block],
                                companion_lookup: dict[str, str],
                                real_paths: frozenset[str]) -> list[str]:
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
    even has)."""
    errors: list[str] = []
    consumed = [False] * len(old_blocks)
    old_positions = _block_positions(old_source, old_blocks)
    new_positions = _block_positions(new_source, new_blocks)

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
            # Containment (fixed per reviewer report on q4repo/rev-cs2,
            # postgres.py CH-0001 false-red): the basis block need not
            # sentence-match the companion VERBATIM -- change set 1 (and
            # any earlier one) may already have applied (3)(4)(6)+§9 to
            # it, so its retained text is only a FURTHER reduction of the
            # companion's original, unreduced text. Require that it be
            # DERIVABLE from the companion via the same allowed-reduction
            # machinery, not that every sentence appear byte-for-byte.
            if ob.retained_text:
                ok, reason = _is_allowed_reduction(ob.kind, companion_text, ob.retained_text, real_paths)
                if not ok:
                    errors.append(
                        f"FAIL (§4.1 (2)) {rel_path}:{nb.start_line} basis block for {ch_id} is "
                        f"not derivable from the existing companion section: {reason}"
                    )
                    continue
            if nb.retained_text:
                ok, reason = _is_allowed_reduction(nb.kind, ob.retained_text, nb.retained_text, real_paths)
                if not ok:
                    errors.append(f"FAIL (§4.1 (3)) {rel_path}:{nb.start_line} {reason}")
            elif ob.retained_text:
                # change set 0d review round (item 1): nothing kept in
                # code at all -- the basis's own retained text (already
                # itself a reduction) is being moved away in full; every
                # one of ITS sentences must be checked too.
                protected = _first_protected_sentence(ob.retained_text, ob.kind, real_paths)
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
        if nb.retained_text:
            ok, reason = _is_allowed_reduction(nb.kind, companion_text, nb.retained_text, real_paths)
            if not ok:
                errors.append(f"FAIL (§4.1 (3)) {rel_path}:{nb.start_line} {reason}")
        else:
            # change set 0d review round (item 1): first move, nothing
            # kept in code -- check the FULL companion text (everything
            # that is disappearing from the source) sentence by sentence.
            protected = _first_protected_sentence(companion_text, nb.kind, real_paths)
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

    new_plain_by_key: dict[tuple[str, str], list[tuple[int, str]]] = {}
    for i, nb in enumerate(new_blocks):
        if nb.history_id is not None:
            continue
        new_plain_by_key.setdefault(new_positions[i], []).append((nb.start_line, nb.dedented))

    for key in sorted(set(remaining_old_by_key) | set(new_plain_by_key)):
        old_seq = [text for _line, text in remaining_old_by_key.get(key, [])]
        new_entries = new_plain_by_key.get(key, [])
        new_seq = [text for _line, text in new_entries]
        if old_seq == new_seq:
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
    # design §9 rule 2: real-path membership is read from the BASIS
    # revision's own tree, once per invocation (never the working tree).
    real_paths = _tree_paths(repo_root, rev)

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

        new_blocks = extract_all_blocks(new_source)
        old_blocks = extract_all_blocks(old_source)
        total_new_blocks += len(new_blocks)

        for msg in check_provenance_semantics(
            rel_path, old_source, new_source, old_blocks, new_blocks, companion_lookup, real_paths
        ):
            print(msg, file=out)
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
