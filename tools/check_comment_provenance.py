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
_HISTORY_TOKEN_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.ASCII)
    for p in (
        # `(?<![A-Za-z0-9])` (v0.4 review round 2) instead of `\b`: an
        # underscore directly before "WP-" (`_WP-3`) is itself a word
        # character, so `\b` would see no boundary there and miss it --
        # this lookbehind only excludes a letter/digit immediately before,
        # so "_WP-3" and "作業WP-3" (with re.ASCII above) are both caught.
        r"(?<![A-Za-z0-9])WP-[0-9A-Za-z-]+",
        r"\bPhase \d+",
        # Inflected forms (v0.4 review round 2): "reviews"/"reviewed" etc.
        r"\breview(?:s|ed|er|ers)?\b",
        r"\bround \d+\b",
        r"\b20\d\d-\d\d-\d\d\b",
        r"差し戻し",
        r"監督裁定",
        r"supervisor ruling",
        r"\bblocker\b",
    )
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
# provenance tag if it names a file -- ANY `.ext` (not just .md/.py, e.g.
# `migrations/0008_x.sql`) -- or a word containing a path separator that
# is not itself just a slash-joined ID list (`SI-08/R-5` is NOT a path:
# every segment already looks like a bare/protected ID), or the words
# "roadmap" / "spec" anywhere in it, or a VERSIONED DOCUMENT NAME (0b
# review round 3 supervisor ruling (a)(i)): `contract <version>`,
# `design <version>`, or `<document name> v<version>`, version being
# `\d+(\.\d+)+` or `v\d+(\.\d+)*`. In any of these cases NO bare ID in the
# same parens/label is removable, even one that would otherwise qualify,
# because the file/roadmap/spec/versioned-document reference is what the
# ID is qualified by (protection covers the WHOLE parenthetical or label,
# not only the ID adjacent to the tag).
#
# `_FILENAME_EXT_RE` is deliberately the WIDE form (any `.<alnum>` run,
# not just letter-led) -- narrowing it (as an earlier revision of this
# file did, to stop `1.7.0` from being mistaken for a file extension)
# silently lost protection for `contract 1.7.0 D-5`-shaped text, which
# relied on that side effect. The versioned-document check below is the
# INTENDED way to protect such text; the wide filename regex is restored
# because erring toward "still protected" is safer than erring toward
# "no longer protected" (supervisor ruling (a), 0b review round 3).
_FILENAME_EXT_RE = re.compile(r"\.[A-Za-z0-9]+\b")
_PROVENANCE_WORD_RE = re.compile(r"\b(?:roadmap|spec)\b")
_VERSION_TOKEN = r"(?:\d+(?:\.\d+)+|v\d+(?:\.\d+)*)"
_VERSIONED_DOC_RE = re.compile(
    r"\b(?:contract|design)\s+" + _VERSION_TOKEN + r"\b"
    r"|\b[A-Za-z][\w-]*\s+v\d+(?:\.\d+)*\b",
    re.IGNORECASE,
)


def _looks_like_path_word(word: str) -> bool:
    if "/" not in word:
        return False
    segments = word.split("/")
    if len(segments) < 2:
        return False
    return any(
        not (_BARE_ID_RE.match(seg) or seg.startswith(_PROTECTED_ID_PREFIXES))
        for seg in segments
    )


def _has_versioned_document_reference(text: str) -> bool:
    return bool(_VERSIONED_DOC_RE.search(text))


def _parens_has_provenance_tag(inner: str) -> bool:
    if (
        _FILENAME_EXT_RE.search(inner)
        or _PROVENANCE_WORD_RE.search(inner)
        or _has_versioned_document_reference(inner)
    ):
        return True
    return any(_looks_like_path_word(chunk) for chunk in re.split(r"[,;\s]+", inner))

# design §4.2 (5): the frozen, change-set-0-measured baseline (2026-09-14,
# both peers' `src/`: 0 hits), now detected via AST name resolution (v0.4
# review fix (f)) rather than a source-text regex, so it also catches
# `from inspect import getsource` + a bare `getsource(...)` call.
_DOCSTRING_DEPENDENT_BASELINE: frozenset[str] = frozenset()
_DOC_ACCESS_ATTRS: frozenset[str] = frozenset({"getdoc", "getsource", "getcomments"})

# design §4.2 (6): non-emptiness floor, counted across BOTH peers combined
# (never per peer). Change set 0 leaves this at 0; change set 1 raises it
# to 1 (work order §2.2, "触るファイル" table).
MIN_CH_IDS = 0

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
    return "\n\n".join(" ".join(g) for g in groups)


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
    return "\n\n".join(" ".join(g) for g in groups)


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


# ---------------------------------------------------------------------------
# design §4.1 (4): mechanical parenthetical-content removal (v0.4 review
# fix (b)): a parenthetical's content is split into WORDS on `, ` `/` `;`
# and plain whitespace -- so "see SI-08 WP-3" is 3 words, not 1 -- and only
# a word that is ENTIRELY a §4.1 (5) history token, or a bare ID with no
# provenance tag co-located in the same parens, may be removed. Original
# separators are preserved and only the removed words (plus one adjacent
# separator each) disappear -- the rest of the parenthetical is untouched
# byte-for-byte, never rejoined with a different separator.
# ---------------------------------------------------------------------------
def _is_removable_word(word: str, has_provenance_tag: bool) -> bool:
    word = word.strip()
    if not word:
        return False
    for pat in _HISTORY_TOKEN_PATTERNS:
        if pat.search(word):
            return True
    if has_provenance_tag:
        return False
    if _BARE_ID_RE.match(word) and not word.startswith(_PROTECTED_ID_PREFIXES):
        return True
    return False


_PAREN_SPLIT_RE = re.compile(r"([,/;\s]+)")


def _strip_allowed_parens(sentence: str) -> str:
    def repl(m: re.Match[str]) -> str:
        leading_ws, inner = m.group(1), m.group(2)
        has_tag = _parens_has_provenance_tag(inner)
        parts = _PAREN_SPLIT_RE.split(inner)
        word_positions = [i for i in range(0, len(parts), 2) if parts[i].strip()]
        if not word_positions:
            return m.group(0)
        flags = {i: _is_removable_word(parts[i], has_tag) for i in word_positions}
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
        new_inner = "".join(parts)
        return leading_ws + "(" + new_inner + ")"

    result = re.sub(r"(\s?)\(([^()]*)\)", repl, sentence)
    result = re.sub(r" {2,}", " ", result)
    return result.strip()


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


def _label_word_tokens(text: str) -> list[tuple[str, bool]]:
    """[(token, is_content_word), ...] per design §8.1's word-counting
    rules: a backtick span is one (content) word; an UNPROTECTED ID
    immediately followed by a parenthesized digit/roman-numeral branch
    (`(4)`, `(ii)`) merges into one NON-content word (a protected ID
    such as `SI-08 (2)` never merges); remaining parens are unwrapped
    (brackets dropped, content flows into the flat stream); a history
    token, an unprotected bare ID, or "and"/"or"/"、" is one non-content
    word; a symbol-only fragment does not count as a word at all."""
    placeholders: dict[str, bool] = {}

    def make_placeholder(is_content: bool) -> str:
        tok = f"\x00W{len(placeholders)}\x00"
        placeholders[tok] = is_content
        return tok

    working = _BACKTICK_SPAN_RE.sub(lambda m: make_placeholder(True), text)
    working = _ID_BRANCH_RE.sub(lambda m: make_placeholder(False), working)
    working = working.replace("(", " ").replace(")", " ")

    tokens: list[tuple[str, bool]] = []
    for raw in working.split():
        t = raw.strip(",;")
        if not t:
            continue
        if t in placeholders:
            tokens.append((t, placeholders[t]))
            continue
        if t in _CONNECTIVE_WORDS:
            tokens.append((t, False))
            continue
        if any(pat.search(t) for pat in _HISTORY_TOKEN_PATTERNS):
            tokens.append((t, False))
            continue
        if _BARE_ID_RE.match(t) and not t.startswith(_PROTECTED_ID_PREFIXES):
            tokens.append((t, False))
            continue
        tokens.append((t, True))
    return tokens


def _label_provenance_tag_present(text: str) -> bool:
    """Same §4.1 (4)/(6) origin-tag detection as `_parens_has_provenance_tag`
    (filename, `roadmap`/`spec`, path word, or a versioned document name),
    applied to the WHOLE label (not just inside one parenthetical) --
    review round: "ファイル名・roadmap・specが同じラベルにあれば、そのID
    は出所付き"."""
    if (
        _FILENAME_EXT_RE.search(text)
        or _PROVENANCE_WORD_RE.search(text)
        or _has_versioned_document_reference(text)
    ):
        return True
    return any(
        _looks_like_path_word(chunk) for chunk in re.split(r"[,;()\s]+", text)
    )


def _label_has_provenance_marker(text: str) -> bool:
    """Condition (1): a §4.1 (5) history token, or an unprotected bare ID
    that is NOT itself provenance-tagged elsewhere in the label."""
    if any(pat.search(text) for pat in _HISTORY_TOKEN_PATTERNS):
        return True
    ids = _ANY_ID_RE.findall(text)
    unprotected = [i for i in ids if not i.startswith(_PROTECTED_ID_PREFIXES)]
    if not unprotected:
        return False
    return not _label_provenance_tag_present(text)


def _label_has_protected_reference(text: str) -> bool:
    """Review-round supervisor ruling (L1/L10): a label containing a
    protected reference (SI-/C-/CCR-, or a bare ID that is provenance-
    tagged) is never removable, even if it also carries a qualifying (5)
    token elsewhere (e.g. "SI-08 WP-3:")."""
    ids = _ANY_ID_RE.findall(text)
    if any(i.startswith(_PROTECTED_ID_PREFIXES) for i in ids):
        return True
    unprotected = [i for i in ids if not i.startswith(_PROTECTED_ID_PREFIXES)]
    return bool(unprotected) and _label_provenance_tag_present(text)


def _label_japanese_char_count(text: str) -> int:
    """Bracket CHARACTERS are excluded, but their CONTENT counts (review
    round fix (b)) -- only `(`/`)` themselves, plus history tokens and
    IDs, are stripped before counting."""
    working = text.replace("(", "").replace(")", "")
    for pat in _HISTORY_TOKEN_PATTERNS:
        working = pat.sub("", working)
    working = _ANY_ID_RE.sub("", working)
    return len(re.sub(r"\s+", "", working))


def _label_qualifies(text: str) -> bool:
    if any(p.search(text) for p in _NEGATION_PATTERNS):
        return False
    if _label_has_protected_reference(text):
        return False
    if not _label_has_provenance_marker(text):
        return False
    tokens = _label_word_tokens(text)
    content_count = sum(1 for _t, is_content in tokens if is_content)
    if content_count > 3:
        return False
    if len(tokens) > 12:
        return False
    if _JAPANESE_CHAR_RE.search(text) and _label_japanese_char_count(text) > 24:
        return False
    return True


def _strip_leading_label(sentence: str) -> str:
    """The separator is looked for OUTSIDE backtick code spans only
    (review round fix (b))."""
    spans = [(m.start(), m.end()) for m in _BACKTICK_SPAN_RE.finditer(sentence)]

    def _inside_span(pos: int) -> bool:
        return any(start <= pos < end for start, end in spans)

    for m in _LABEL_SEPARATOR_RE.finditer(sentence):
        if _inside_span(m.start()):
            continue
        label = sentence[: m.start()]
        if not _label_qualifies(label):
            return sentence
        return sentence[m.end() :]
    return sentence


def _is_allowed_reduction(kind: str, old_full_text: str, new_retained_text: str) -> tuple[bool, str]:
    """design §4.1 (3)+(4)+(6): `new_retained_text` must be reachable from
    `old_full_text` by deleting whole sentences (order preserved) and/or
    applying, to a kept sentence, the (4) mechanical parenthetical
    removal and/or the (6) leading-label removal (v0.5; (6) may be
    followed by (4) on what remains) -- nothing else (no reorder, no
    added word, no dropped negation, no mid-sentence line-wrap deletion)."""
    old_sentences = split_sentences(_flatten(kind, old_full_text))
    new_sentences = split_sentences(_flatten(kind, new_retained_text))
    j = 0
    for ns in new_sentences:
        found = False
        while j < len(old_sentences):
            candidate = old_sentences[j]
            j += 1
            label_stripped = _strip_leading_label(candidate)
            allowed = {
                candidate,
                _strip_allowed_parens(candidate),
                label_stripped,
                _strip_allowed_parens(label_stripped),
            }
            if ns in allowed:
                found = True
                break
        if not found:
            return False, f"retained text has no order-preserving match in the original block for: {ns!r}"
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
def _added_lines(old_source: str, new_source: str) -> list[tuple[int, str]]:
    old_lines = old_source.splitlines()
    new_lines = new_source.splitlines()
    sm = difflib.SequenceMatcher(a=old_lines, b=new_lines, autojunk=False)
    added: list[tuple[int, str]] = []
    for tag, _i1, _i2, j1, j2 in sm.get_opcodes():
        if tag in ("insert", "replace"):
            for k in range(j1, j2):
                added.append((k + 1, new_lines[k]))
    return added


def check_no_added_history_tokens(old_source: str, new_source: str) -> list[tuple[int, str, str]]:
    hits: list[tuple[int, str, str]] = []
    for lineno, line in _added_lines(old_source, new_source):
        for pat in _HISTORY_TOKEN_PATTERNS:
            if pat.search(line):
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
                                companion_lookup: dict[str, str]) -> list[str]:
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
    then re-labeled as if it had "moved via history" from g)."""
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
        same_scope = [
            i for i, ob in enumerate(old_blocks)
            if not consumed[i] and ob.dedented == companion_text and old_positions[i][0] == nb_scope
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
            ok, reason = _is_allowed_reduction(nb.kind, companion_text, nb.retained_text)
            if not ok:
                errors.append(f"FAIL (§4.1 (3)) {rel_path}:{nb.start_line} {reason}")

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
            rel_path, old_source, new_source, old_blocks, new_blocks, companion_lookup
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
