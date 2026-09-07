#!/usr/bin/env python3
"""check_doc_refs.py -- guard against a silently-broken document ID
reference: every reference to a globally-unique ID family (SI-NN, C-NN,
CCR-NN, roadmap G-N/P-N/R-N, phase ledger L{phase}-N) must resolve to a
definition that actually lives in that family's canonical file.

Design: docs/design/DEVELOPMENT_PROCESS_HYGIENE_V1.md D-2. Work order:
docs/work-orders/WORK_ORDER_DEVELOPMENT_PROCESS_HYGIENE_V1.md WP-2.

This is a *preventive* check, the same shape as tools/check_collection_floor.py:
as of the design's own measurement (D-2 / section 1.2(1)), the repository
already has zero dangling references in every family covered here. This
script exists to keep that true as the repository grows, not to report
today's defects.

Families and canonical files (script-internal constants; changing this
table -- adding a family, renaming a canonical file, adding a phase prefix
-- is a separate, explicit commit, exactly like COLLECTION_FLOOR's own
bump discipline):

    SI      security/SECURITY_INVARIANTS_V1.md            heading  "### SI-NN"
    C       conformance-tests/CONDITIONS.md                table row, bare first cell
    CCR     spec/CCR_DISPOSITION.md                        table row, bare first cell
    G/P/R   docs/design/ROADMAP_POST_PHASE7_V1.md          table row, **bold** first cell
    L{phase} one file per known phase prefix (L4..L9, LQ4)  first "**...**" bold
              span whose content STARTS WITH the token,     span occurrence
              anywhere in that phase's canonical file(s)
              (not limited to line-start / bullet position)

Token grammar is fixed PER FAMILY to that family's own numbering
convention (design D-2, v1.3の訂正: 族ごとの桁 -- a family-wide `\\d+` let a
document-local, non-conformance number such as
docs/design/R2DB_SERVICE_LAYER_ARCHITECTURE.md §5.3's `C-1`..`C-5` design
constants, and `C-0x` placeholders, be mistaken for C-family references):
zero-padded 2-digit families SI/C/CCR (`SI-NN`, `C-NN`, `CCR-NN`, optional
`[a-z]` suffix); non-zero-padded 1-2-digit families G/P/R (`G-N`, `P-N`,
`R-N`, one or two digits, optional `[a-z]` suffix); non-zero-padded 1-2-digit
L-family (`L{phase}-N`, same digit shape, known phase prefixes unchanged).
A number of 3 or more digits (e.g. `C-100`) matches no family under the
current numbering convention; if that convention ever needs one, update
this file's per-family constants in their own explicit commit, exactly
like COLLECTION_FLOOR's own bump discipline -- do not silently widen the
pattern back to `\\d+`.

A "definition" only exists inside a family's own canonical file(s) --
scanning every other file's tables/bold text for something that merely
*looks* like a definition would let a copied/transcribed table (a
documented, intentional practice in this repository, design section
1.2(2)) masquerade as the source of truth once the real one is deleted.
Definitions are read directly from the canonical path(s), independent of
the scanned-file set.

Scan scope for *references* (all of `.md`, no code-comment scanning):
docs/ spec/ security/ conformance-tests/ (recursive) plus README.md,
CLAUDE.md, and tools/*.md (non-recursive). This deliberately includes the
canonical files themselves and docs/work-orders/HANDOVER_*.md (history,
never rewritten) -- no exemption list, on purpose (design D-2's "赤が出た
ときの一般規則"): a rare, genuine token/ID collision inside a HANDOVER_*.md
file (never rewritten) is the one case allowed into KNOWN_NON_IDS below,
by an explicit commit that records the reason.

A different repository's own ID family (currently just Mitate's `DM-NNNN`)
is a legitimate cross-repository reference, not a defect: it is reported
under "external references" but never makes this script exit non-zero.

Exit code:
    0 -- every family's canonical file(s) could be read, AND every
         reference found in the scanned `.md` files resolves to a
         definition in its family's canonical file(s) (external-prefix
         references and KNOWN_NON_IDS entries aside).
    1 -- any of: a family's canonical file could not be read (this is
         checked BEFORE the reference scan runs, and is fatal by itself --
         an unreadable canonical file is never treated as "zero
         definitions, therefore nothing to check"); OR at least one
         reference has no definition in its family's canonical file(s).

Standard library only (tools/public_value_scan.py convention) -- no
external dependency, no subprocess, no dependence on `sys.executable`.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Scan target set (design D-2 "走査対象"): all `.md` under these directories
# (recursive), plus these specific root files, plus tools/*.md (NOT
# recursive -- tools/tests/*.md, if any ever existed, is not in scope).
# ---------------------------------------------------------------------------
_SCAN_DIRS = ("docs", "spec", "security", "conformance-tests")
_SCAN_ROOT_FILES = ("README.md", "CLAUDE.md")


def iter_scan_files(repo_root: Path) -> list[Path]:
    files: set[Path] = set()
    for d in _SCAN_DIRS:
        base = repo_root / d
        if base.is_dir():
            for p in base.rglob("*.md"):
                if p.is_file():
                    files.add(p)
    for name in _SCAN_ROOT_FILES:
        p = repo_root / name
        if p.is_file():
            files.add(p)
    tools_dir = repo_root / "tools"
    if tools_dir.is_dir():
        for p in tools_dir.glob("*.md"):
            if p.is_file():
                files.add(p)
    return sorted(files)


def read_lines(path: Path) -> list[str] | None:
    """Returns the file's lines, or None if it cannot be read at all --
    callers must treat None as fatal, never as "zero lines, zero
    definitions, carry on"."""
    try:
        return path.read_text(encoding="utf-8", errors="strict").splitlines()
    except OSError:
        return None
    except UnicodeDecodeError:
        return None


def relpath(repo_root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(repo_root))
    except ValueError:
        return str(path)


# ---------------------------------------------------------------------------
# Simple families: one canonical file, definitions matched by a single
# per-line regex against that file's own lines.
#
# Digit-count fragments (design D-2, v1.3の訂正: 族ごとの桁): each family's
# token grammar is fixed to ITS OWN numbering convention, not a shared
# `\d+` -- see the module docstring's "Token grammar" paragraph for why.
# ---------------------------------------------------------------------------
_DIGITS_ZERO_PADDED_2 = r"\d{2}"  # SI-NN / C-NN / CCR-NN
_DIGITS_UNPADDED_1_2 = r"\d{1,2}"  # G-N / P-N / R-N / L{phase}-N

_BOLD_ROW_TMPL = r"^\|\s*\*\*({prefix}-{digits}[a-z]?)\*\*\s*\|"
# Leading table cell whose content STARTS with the ID -- not necessarily
# the cell's entire content. conformance-tests/CONDITIONS.md's cells are
# the bare ID alone; spec/CCR_DISPOSITION.md's CCR-13/14/15 rows carry a
# short descriptive title in the SAME first cell ("CCR-13 行の指し示し可能性
# | ..."), so matching only up to the next "|" would miss them.
_BARE_ROW_TMPL = r"^\|\s*({prefix}-{digits}[a-z]?)\b"

SIMPLE_FAMILIES: dict[str, dict] = {
    "SI": {
        "ref_re": re.compile(r"\bSI-\d{2}[a-z]?\b"),
        "canonical": "security/SECURITY_INVARIANTS_V1.md",
        "def_re": re.compile(r"^#{1,6}\s*(SI-\d{2}[a-z]?)\b"),
    },
    "C": {
        "ref_re": re.compile(r"\bC-\d{2}[a-z]?\b"),
        "canonical": "conformance-tests/CONDITIONS.md",
        "def_re": re.compile(_BARE_ROW_TMPL.format(prefix="C", digits=_DIGITS_ZERO_PADDED_2)),
    },
    "CCR": {
        "ref_re": re.compile(r"\bCCR-\d{2}[a-z]?\b"),
        "canonical": "spec/CCR_DISPOSITION.md",
        "def_re": re.compile(_BARE_ROW_TMPL.format(prefix="CCR", digits=_DIGITS_ZERO_PADDED_2)),
    },
    "G": {
        "ref_re": re.compile(r"\bG-\d{1,2}[a-z]?\b"),
        "canonical": "docs/design/ROADMAP_POST_PHASE7_V1.md",
        "def_re": re.compile(_BOLD_ROW_TMPL.format(prefix="G", digits=_DIGITS_UNPADDED_1_2)),
    },
    "P": {
        "ref_re": re.compile(r"\bP-\d{1,2}[a-z]?\b"),
        "canonical": "docs/design/ROADMAP_POST_PHASE7_V1.md",
        "def_re": re.compile(_BOLD_ROW_TMPL.format(prefix="P", digits=_DIGITS_UNPADDED_1_2)),
    },
    "R": {
        "ref_re": re.compile(r"\bR-\d{1,2}[a-z]?\b"),
        "canonical": "docs/design/ROADMAP_POST_PHASE7_V1.md",
        "def_re": re.compile(_BOLD_ROW_TMPL.format(prefix="R", digits=_DIGITS_UNPADDED_1_2)),
    },
}

# ---------------------------------------------------------------------------
# L-family: one reference regex spanning every known phase prefix, but each
# token's definition must live in ITS OWN phase's canonical file(s) --
# never merely somewhere with a matching bold span. LQ4 has two canonical
# files (design D-2 / section 1.2(4)); both must be readable.
# ---------------------------------------------------------------------------
L_REF_RE = re.compile(r"\bL(?:Q4|[4-9])-\d{1,2}[a-z]?\b")
# Known behavior of this pattern (kept simple on purpose, design D-2
# 開示事項): it matches within a single line only -- a "**...**" span split
# across a line break is never found, which only makes this check MORE
# fail-loud (a real definition can be missed and reported dangling, never
# the reverse). It also pairs each "**" with the NEXT "**" on the same
# line; an odd number of "**" on one line (e.g. "2**3の見積りでL7-1は**重要**
# である") therefore produces a span whose content did not start life
# between a matched pair. collect_l_definitions guards against exactly
# this by requiring the span's content to START WITH the ID token (see
# its own docstring) -- a token merely appearing mid-span, as it would in
# that example, is never treated as a definition.
_BOLD_SPAN_RE = re.compile(r"\*\*(.+?)\*\*")

PHASE_CANONICAL: dict[str, tuple[str, ...]] = {
    "L4": ("docs/design/PHASE4_DURABLE_AUDIT_SINK_V1.md",),
    "L5": ("docs/design/PHASE5_CONTRACT_150_AND_LIMIT_RANGE_V1.md",),
    "L6": ("docs/design/PHASE6_CONTRACT_160_CLIENT_DISCOVERY_V1.md",),
    "L7": ("docs/design/PHASE7_EVIDENCE_REPRODUCIBILITY_AND_PUBLICATION_V1.md",),
    "L8": ("docs/design/PHASE8_EFFECTIVE_BOUNDS_AND_HYGIENE_V1.md",),
    "L9": ("docs/design/PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md",),
    "LQ4": (
        "docs/design/Q4_DB_SIDE_SINGLE_TRUTH_V1.md",
        "docs/design/PHASE7_EVIDENCE_REPRODUCIBILITY_AND_PUBLICATION_V1.md",
    ),
}

# ---------------------------------------------------------------------------
# External prefixes: a real, legitimate reference to another repository's
# own ID family. Reported, never counted as a dangling reference in any
# family above (design D-2 exclusion rule (a)).
# ---------------------------------------------------------------------------
EXTERNAL_PREFIXES: tuple[str, ...] = ("DM",)


def external_ref_re() -> re.Pattern[str]:
    alternation = "|".join(re.escape(p) for p in EXTERNAL_PREFIXES)
    return re.compile(r"\b(?:" + alternation + r")-\d+[a-z]?\b")


# ---------------------------------------------------------------------------
# Known, deliberately-accepted token/definition-format collisions inside a
# file this project never rewrites (a HANDOVER_*.md, design D-2's "赤が出た
# ときの一般規則" (2)). Each entry is (relative_path, exact_token). Adding
# an entry is a separate, explicit commit with the reason in the commit
# message. Initial value is empty (design D-2: "初期値は空である").
# ---------------------------------------------------------------------------
KNOWN_NON_IDS: frozenset[tuple[str, str]] = frozenset()


def check_canonical_readability(repo_root: Path) -> list[str]:
    """Returns a list of human-readable error strings, one per canonical
    file that could not be read. An empty list means every canonical file
    for every family (including both LQ4 files) was readable. This check
    runs BEFORE any reference is examined -- an unreadable canonical file
    must never be treated as "zero definitions, therefore clean" (the same
    fail-loud principle as tools/check_collection_floor.py)."""
    errors: list[str] = []
    for family, spec in SIMPLE_FAMILIES.items():
        path = repo_root / spec["canonical"]
        if read_lines(path) is None:
            errors.append(
                f"ERROR: family {family}: could not read canonical file {spec['canonical']}"
            )
    for prefix, rels in PHASE_CANONICAL.items():
        for rel in rels:
            path = repo_root / rel
            if read_lines(path) is None:
                errors.append(
                    f"ERROR: family L ({prefix}): could not read canonical file {rel}"
                )
    return errors


def check_scan_readability(repo_root: Path, scan_files: list[Path]) -> list[str]:
    """Returns a list of human-readable error strings, one per scan-target
    file (the *reference* side, as opposed to check_canonical_readability's
    canonical-file side) that could not be read -- non-UTF-8 content or an
    OS-level read failure alike. An empty list means every scan-target file
    was readable. This mirrors check_collection_floor.py's and
    check_canonical_readability's own fail-loud principle: a `.md` file
    nobody can read must never be silently skipped by collect_references
    and reported as "zero references in it, therefore clean" -- it might
    be hiding a dangling reference from every reader, human or script."""
    errors: list[str] = []
    for path in scan_files:
        rel = relpath(repo_root, path)
        try:
            path.read_text(encoding="utf-8", errors="strict")
        except OSError as exc:
            errors.append(f"{rel}: unreadable ({exc})")
        except UnicodeDecodeError as exc:
            errors.append(f"{rel}: unreadable ({exc})")
    return errors


def collect_simple_definitions(
    repo_root: Path, family: str
) -> dict[str, tuple[str, int]]:
    """Definitions for a SIMPLE_FAMILIES entry, read directly from its own
    canonical file only -- never from the general scanned-file set."""
    spec = SIMPLE_FAMILIES[family]
    canonical_rel = spec["canonical"]
    lines = read_lines(repo_root / canonical_rel)
    defs: dict[str, tuple[str, int]] = {}
    if lines is None:
        return defs
    def_re = spec["def_re"]
    for i, line in enumerate(lines, start=1):
        m = def_re.match(line)
        if m:
            defs.setdefault(m.group(1), (canonical_rel, i))
    return defs


def collect_l_definitions(repo_root: Path) -> dict[str, tuple[str, int]]:
    """Definitions for the L-family: for each known phase prefix, scan
    ONLY that prefix's own canonical file(s) (never the general scanned-
    file set, via iter_scan_files or otherwise) for a "**...**" bold span
    whose content STARTS WITH a token of that same prefix -- a token that
    merely appears, bold or not, in a DIFFERENT phase's canonical file is
    not a definition (that is the "転記/transcription" hazard design D-2
    calls out, section 1.2(2)), and a token that appears only in the
    MIDDLE of a bold span is not a definition either (see the
    "starts-with" note above _BOLD_SPAN_RE for why)."""
    defs: dict[str, tuple[str, int]] = {}
    for prefix, rels in PHASE_CANONICAL.items():
        for rel in rels:
            lines = read_lines(repo_root / rel)
            if lines is None:
                continue
            for i, line in enumerate(lines, start=1):
                for span in _BOLD_SPAN_RE.finditer(line):
                    m = L_REF_RE.match(span.group(1))
                    if m is None:
                        continue
                    token = m.group(0)
                    if token.split("-", 1)[0] != prefix:
                        continue
                    defs.setdefault(token, (rel, i))
    return defs


def collect_references(
    repo_root: Path, scan_files: list[Path], ref_re: re.Pattern[str]
) -> list[tuple[str, int, str]]:
    """Every occurrence of ref_re across every scanned file, INCLUDING
    lines inside canonical files themselves, fenced code blocks, tables,
    and links -- design D-2 deliberately does not carve out exceptions for
    any of those (section "開示事項")."""
    hits: list[tuple[str, int, str]] = []
    for path in scan_files:
        lines = read_lines(path)
        if lines is None:
            continue
        rel = relpath(repo_root, path)
        for i, line in enumerate(lines, start=1):
            for m in ref_re.finditer(line):
                hits.append((rel, i, m.group(0)))
    return hits


def l_canonical_description(prefix: str) -> str:
    rels = PHASE_CANONICAL.get(prefix, ())
    return " and ".join(rels) if rels else "(unknown phase prefix)"


def run(repo_root: Path, out=None, err=None) -> int:
    out = sys.stdout if out is None else out
    err = sys.stderr if err is None else err

    readability_errors = check_canonical_readability(repo_root)
    if readability_errors:
        for line in readability_errors:
            print(line, file=err)
        print(
            "check_doc_refs FAILED: a canonical file could not be read; "
            "refusing to report a clean result (see tools/check_collection_floor.py's "
            "same fail-loud principle).",
            file=err,
        )
        return 1

    scan_files = iter_scan_files(repo_root)

    scan_errors = check_scan_readability(repo_root, scan_files)
    if scan_errors:
        for line in scan_errors:
            print(line, file=err)
        print(
            "check_doc_refs FAILED: a scan-target file could not be read; "
            "refusing to report a clean result (a file no one can read might "
            "be hiding a dangling reference from every reader).",
            file=err,
        )
        return 1

    # Dangling entries carry (rel, lineno, token, message) so the final
    # report can be sorted by NUMERIC line number (design D-2 / R-I) --
    # sorting the formatted "file:line: ..." strings themselves would sort
    # ":10" before ":2" lexically.
    dangling: list[tuple[str, int, str, str]] = []
    family_counts: list[tuple[str, int, int]] = []

    for family, spec in SIMPLE_FAMILIES.items():
        defs = collect_simple_definitions(repo_root, family)
        refs = collect_references(repo_root, scan_files, spec["ref_re"])
        family_counts.append((family, len(defs), len(refs)))
        canonical_rel = spec["canonical"]
        for rel, lineno, token in refs:
            if token in defs:
                continue
            if (rel, token) in KNOWN_NON_IDS:
                continue
            message = f"{rel}:{lineno}: {token} has no definition in {canonical_rel}"
            dangling.append((rel, lineno, token, message))

    l_defs = collect_l_definitions(repo_root)
    l_refs = collect_references(repo_root, scan_files, L_REF_RE)
    family_counts.append(("L", len(l_defs), len(l_refs)))
    for rel, lineno, token in l_refs:
        if token in l_defs:
            continue
        if (rel, token) in KNOWN_NON_IDS:
            continue
        prefix = token.split("-", 1)[0]
        canonical_desc = l_canonical_description(prefix)
        message = f"{rel}:{lineno}: {token} has no definition in {canonical_desc}"
        dangling.append((rel, lineno, token, message))

    external_hits = collect_references(repo_root, scan_files, external_ref_re())

    # Per-family definition/reference counts are printed UNCONDITIONALLY,
    # not only on a clean run -- a scanning/regex regression that makes a
    # whole family go vacuous (0 definitions or 0 references) must be
    # visible even on a run that is separately failing for an unrelated
    # dangling reference elsewhere (design D-2 T-6, "空振り禁止").
    for family, ndefs, nrefs in family_counts:
        print(f"{family}: definitions={ndefs} references={nrefs}", file=out)

    if external_hits:
        # Same numeric-line-number reasoning as `dangling` below (R-I).
        by_token: dict[str, list[tuple[str, int]]] = {}
        for rel, lineno, token in external_hits:
            by_token.setdefault(token, []).append((rel, lineno))
        print("external references (reported only, no definition required):", file=out)
        for token in sorted(by_token):
            locations = ", ".join(
                f"{rel}:{lineno}" for rel, lineno in sorted(by_token[token])
            )
            print(f"  {token}: {locations}", file=out)

    if dangling:
        for _, _, _, message in sorted(dangling, key=lambda entry: entry[:3]):
            print(message, file=out)
        print(f"check_doc_refs FAILED: {len(dangling)} dangling reference(s)", file=out)
        return 1

    print("check_doc_refs OK: 0 dangling references", file=out)
    return 0


def main() -> int:
    return run(REPO_ROOT)


if __name__ == "__main__":
    sys.exit(main())
