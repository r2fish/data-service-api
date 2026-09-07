"""tools/tests/test_check_doc_refs.py -- pytest wrapper around
tools/check_doc_refs.py's own scenarios (WP-2).

Deliberately NOT under `conformance-tests/` and NOT discoverable by the root
suite: `tools/` is not in pyproject.toml's `[tool.pytest.ini_options]
testpaths`, and adding it there is an undesigned extension outside WP-2's
scope (same convention as tools/tests/test_rewrite_hash_refs.py -- see that
file's own docstring).

Run directly:
    ./.venv/bin/python -m pytest tools/tests/test_check_doc_refs.py -q
"""
from __future__ import annotations

import importlib.util
import io
import re
import sys
from pathlib import Path

_MODULE_PATH = Path(__file__).resolve().parents[1] / "check_doc_refs.py"
_spec = importlib.util.spec_from_file_location("check_doc_refs", _MODULE_PATH)
cdr = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("check_doc_refs", cdr)
_spec.loader.exec_module(cdr)  # type: ignore[union-attr]

REPO_ROOT = Path(__file__).resolve().parents[2]


def _run(repo_root: Path) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    code = cdr.run(repo_root, out=out, err=err)
    return code, out.getvalue(), err.getvalue()


def _dangling_lines(out: str) -> list[str]:
    return [line for line in out.splitlines() if "has no definition in" in line]


def _write(root: Path, rel: str, content: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def _append(root: Path, rel: str, line: str) -> None:
    """Appends a line to a file _build_minimal_tree already wrote, without
    disturbing its existing content -- used by tests that need to add one
    more bold span or reference to an already-populated canonical file."""
    p = root / rel
    existing = p.read_text(encoding="utf-8") if p.exists() else ""
    p.write_text(existing + line, encoding="utf-8")


def _build_minimal_tree(tmp_path: Path, *, omit: str | None = None) -> Path:
    """Common precondition for every synthetic-tree test except the
    missing-canonical one (work order WP-2 manifest, "合成ツリーの共通前提"):
    every family's canonical file is placed in minimal, valid form, so a
    missing-canonical failure never masks the one thing a given test is
    actually checking. `omit` (a SIMPLE_FAMILIES key, or an L-family phase
    prefix such as "L4"/"LQ4") skips that one phase's OWN placeholder-
    writing loop iteration entirely -- used only by the missing-canonical-
    file tests. For a SIMPLE_FAMILIES key, or an L-family prefix whose
    canonical file(s) are exclusive to it, this omits that file entirely.
    For "LQ4" specifically, this does NOT omit both of LQ4's two canonical
    files: PHASE_CANONICAL's LQ4 entry shares one of its two files
    (PHASE7_EVIDENCE_REPRODUCIBILITY_AND_PUBLICATION_V1.md) with the L7
    entry, which still runs its own loop iteration and writes that file --
    so omit="LQ4" leaves exactly ONE of LQ4's two canonical files missing
    (Q4_DB_SIDE_SINGLE_TRUTH_V1.md), never both."""
    root = tmp_path / "repo"
    content_by_rel: dict[str, list[str]] = {}

    def add(rel: str, line: str) -> None:
        content_by_rel.setdefault(rel, []).append(line)

    if omit != "SI":
        add("security/SECURITY_INVARIANTS_V1.md", "### SI-00 — Placeholder")
    if omit != "C":
        add("conformance-tests/CONDITIONS.md", "| C-00 | placeholder |")
    if omit != "CCR":
        add("spec/CCR_DISPOSITION.md", "| CCR-01 | placeholder |")
    if omit not in ("G", "P", "R"):
        add("docs/design/ROADMAP_POST_PHASE7_V1.md", "| **G-1** | placeholder |")
        add("docs/design/ROADMAP_POST_PHASE7_V1.md", "| **P-1** | placeholder |")
        add("docs/design/ROADMAP_POST_PHASE7_V1.md", "| **R-1** | placeholder |")
    for prefix, rels in cdr.PHASE_CANONICAL.items():
        if prefix == omit:
            continue
        for rel in rels:
            add(rel, f"- **{prefix}-1 placeholder**")

    for rel, lines in content_by_rel.items():
        _write(root, rel, "\n".join(lines) + "\n")
    return root


# ---------------------------------------------------------------------------
# 2-1 (T-1)
# ---------------------------------------------------------------------------
def test_dangling_reference_exits_nonzero(tmp_path):
    root = _build_minimal_tree(tmp_path)

    code, out, err = _run(root)
    assert code == 0, f"minimal tree must start clean; got exit {code}, output:\n{out}{err}"
    assert _dangling_lines(out) == []

    _write(root, "docs/design/OTHER.md", "See SI-99 for details.\n")
    code, out, err = _run(root)
    assert code != 0
    lines = _dangling_lines(out)
    assert len(lines) == 1
    assert "SI-99" in lines[0]
    assert "has no definition in" in lines[0]


# ---------------------------------------------------------------------------
# 2-2 (T-2)
# ---------------------------------------------------------------------------
def test_bold_row_outside_canonical_file_is_not_a_definition(tmp_path):
    root = _build_minimal_tree(tmp_path)
    _write(root, "docs/design/OTHER_DEF.md", "| **P-9** | transcribed, not the source |\n")

    code, out, err = _run(root)
    assert code != 0
    lines = _dangling_lines(out)
    assert any("P-9" in line for line in lines), out


# ---------------------------------------------------------------------------
# 2-3 (T-3)
# ---------------------------------------------------------------------------
def test_external_prefix_is_reported_not_failed(tmp_path):
    root = _build_minimal_tree(tmp_path)
    _write(root, "docs/design/OTHER_EXTERNAL.md", "See DM-0099 for the peer's own id.\n")

    code, out, err = _run(root)
    assert code == 0, f"external-only reference must not fail; got exit {code}, output:\n{out}{err}"
    assert "DM-0099" in out


# ---------------------------------------------------------------------------
# 2-4 (T-4) -- the ONLY synthetic tree that omits a canonical file.
# ---------------------------------------------------------------------------
def test_missing_canonical_file_is_never_clean(tmp_path):
    root = _build_minimal_tree(tmp_path, omit="SI")

    code, out, err = _run(root)
    assert code != 0
    combined = (out + err).lower()
    assert "could not read" in combined


# ---------------------------------------------------------------------------
# 2-5 (T-5) -- real repository.
# ---------------------------------------------------------------------------
def test_real_repository_has_no_dangling_reference():
    code, out, err = _run(REPO_ROOT)
    assert code == 0, (
        "real repository must have 0 dangling document-ID references; "
        f"got exit {code}. Dangling lines:\n" + "\n".join(_dangling_lines(out))
    )


# ---------------------------------------------------------------------------
# 2-6 (T-6) -- real repository, no-vacuous-scan guard.
# ---------------------------------------------------------------------------
def test_every_family_has_definitions_and_references():
    code, out, err = _run(REPO_ROOT)
    counts: dict[str, tuple[int, int]] = {}
    for line in out.splitlines():
        m = re.match(r"^(\w+): definitions=(\d+) references=(\d+)$", line)
        if m:
            counts[m.group(1)] = (int(m.group(2)), int(m.group(3)))

    expected_families = ("SI", "C", "CCR", "G", "P", "R", "L")
    for family in expected_families:
        assert family in counts, f"family {family} missing from output:\n{out}"
        ndefs, nrefs = counts[family]
        assert ndefs >= 1, f"family {family} has 0 definitions (scan is vacuous): {out}"
        assert nrefs >= 1, f"family {family} has 0 references (scan is vacuous): {out}"


# ---------------------------------------------------------------------------
# 2-7 (T-7) -- design D-2 (v1.3 の訂正: 族ごとの桁): a document-local number
# in the C family's un-padded, single-digit shape (`C-1`) is NOT a C-family
# reference -- the family's own numbering convention is zero-padded 2-digit
# (`C-00`, `C-01`, ...), so a single-digit token belongs to no family here
# and must never be counted as dangling.
# ---------------------------------------------------------------------------
def test_document_local_single_digit_c_number_is_not_a_family_reference(tmp_path):
    root = _build_minimal_tree(tmp_path)
    _write(
        root,
        "docs/design/OTHER_LOCAL_CONSTANTS.md",
        "This design imposes local constraints C-1 through C-5, which are "
        "not conformance conditions.\n",
    )

    code, out, err = _run(root)
    assert code == 0, f"a document-local C-1..C-5 must not be flagged; got exit {code}, output:\n{out}{err}"
    assert _dangling_lines(out) == []
    m = re.search(r"^C: definitions=(\d+) references=(\d+)$", out, re.MULTILINE)
    assert m is not None, out
    # The minimal tree's own C-00 reference (in CONDITIONS.md itself) is the
    # only genuine C-family reference; C-1..C-5 must not inflate this count.
    assert int(m.group(2)) == 1, f"C-1..C-5 leaked into the C family reference count: {out}"


# ---------------------------------------------------------------------------
# 2-8 (T-8) -- design D-2 (v1.3 の訂正): a lettered-suffix token in the C
# family's own zero-padded shape (`C-05a`) IS a legitimate C-family
# reference, and must still go red (fail loud) when no definition for it
# exists in the canonical file.
# ---------------------------------------------------------------------------
def test_suffixed_c_family_token_without_definition_is_dangling(tmp_path):
    root = _build_minimal_tree(tmp_path)
    _write(root, "docs/design/OTHER_SUFFIXED.md", "See C-05a for the added vector.\n")

    code, out, err = _run(root)
    assert code != 0
    lines = _dangling_lines(out)
    assert any("C-05a" in line for line in lines), out


# ---------------------------------------------------------------------------
# R-A (code review rework 2) -- the L-family's own version of T-2: a bold
# span in a file OTHER than the phase's own canonical file must not be
# treated as a definition. Before this test, a mutation that sourced
# collect_l_definitions from the general scanned-file set instead of
# PHASE_CANONICAL's own paths passed all 8 prior tests unnoticed.
# ---------------------------------------------------------------------------
def test_l_family_definition_outside_canonical_file_is_not_a_definition(tmp_path):
    root = _build_minimal_tree(tmp_path)
    _write(
        root,
        "docs/design/OTHER_L8_TRANSCRIPTION.md",
        "- **L8-9 転記であって定義ではない**\n",
    )

    code, out, err = _run(root)
    assert code != 0, (
        f"a bold span outside L8's own canonical file must not define L8-9; "
        f"got exit {code}, output:\n{out}{err}"
    )
    lines = _dangling_lines(out)
    assert any("L8-9" in line for line in lines), out


# ---------------------------------------------------------------------------
# R-B (code review rework 2) -- the L-family's cross-phase prefix guard:
# a bold span in a DIFFERENT phase's canonical file must not define a
# token whose own prefix doesn't match that file's phase, even though
# LQ4 shares one of its two canonical files with L7's own. Before this
# test, a mutation that deleted the `token.split("-", 1)[0] != prefix`
# guard passed all 8 prior tests unnoticed.
# ---------------------------------------------------------------------------
def test_l_family_cross_phase_prefix_is_not_a_definition(tmp_path):
    root = _build_minimal_tree(tmp_path)
    # Q4_DB_SIDE_SINGLE_TRUTH_V1.md is LQ4's own canonical file (not shared
    # with L7) -- a bold L4-* span placed there must never define an L4
    # token, since it was scanned only because the LQ4 loop iteration
    # visited it, not because it is L4's own canonical file.
    _append(
        root,
        "docs/design/Q4_DB_SIDE_SINGLE_TRUTH_V1.md",
        "- **L4-7 cross-phase transcription, not a definition**\n",
    )
    _write(root, "docs/design/OTHER_L4_REF.md", "See L4-7 for details.\n")

    code, out, err = _run(root)
    assert code != 0, (
        f"an L4-* bold span inside LQ4's own canonical file must not define "
        f"L4-7; got exit {code}, output:\n{out}{err}"
    )
    lines = _dangling_lines(out)
    assert any("L4-7" in line for line in lines), out


# ---------------------------------------------------------------------------
# R-C (code review rework 2) -- LQ4 has TWO canonical files; missing either
# one alone must be non-zero. Before this test, `omit="SI"` was the only
# missing-canonical scenario exercised, so a mutation that deleted the
# entire PHASE_CANONICAL loop from check_canonical_readability passed all
# 8 prior tests unnoticed. omit="LQ4" leaves exactly ONE of LQ4's two
# files missing (Q4_DB_SIDE_SINGLE_TRUTH_V1.md -- see _build_minimal_tree's
# own docstring for why the other, shared with L7, still gets written).
# ---------------------------------------------------------------------------
def test_missing_one_of_two_lq4_canonical_files_is_never_clean(tmp_path):
    root = _build_minimal_tree(tmp_path, omit="LQ4")

    code, out, err = _run(root)
    assert code != 0
    combined = out + err
    assert "could not read" in combined.lower()
    assert "Q4_DB_SIDE_SINGLE_TRUTH_V1.md" in combined


# ---------------------------------------------------------------------------
# R-D (code review rework 2, supervisor ruling) -- a scan-target file that
# cannot be read (non-UTF-8 here) must never be silently skipped: it might
# be hiding a dangling reference (SI-99 below) from every reader. Before
# this test/fix, such a file was skipped by collect_references and the run
# reported a clean "0 dangling references" result.
# ---------------------------------------------------------------------------
def test_unreadable_scan_target_is_never_silently_skipped(tmp_path):
    root = _build_minimal_tree(tmp_path)
    bad = root / "docs" / "design" / "BAD_ENCODING.md"
    bad.parent.mkdir(parents=True, exist_ok=True)
    bad.write_bytes(b"\xff\xfe not valid UTF-8, and SI-99 is dangling in here\n")

    code, out, err = _run(root)
    assert code != 0, (
        f"an unreadable scan-target file must never yield a clean result; "
        f"got exit {code}, output:\n{out}{err}"
    )
    combined = (out + err).lower()
    assert "unreadable" in combined
    assert "bad_encoding.md" in combined


# ---------------------------------------------------------------------------
# R-F (code review rework 2, supervisor ruling) -- an unpaired "**" on a
# line must not manufacture a false definition. `_BOLD_SPAN_RE` pairs each
# "**" with the next one on the same line; on a line with an odd count of
# "**", the resulting span's content did not start life between a matched
# pair and may contain an ID token in its middle. collect_l_definitions
# only accepts a span whose content STARTS WITH the token -- L7-2 here
# appears only mid-span, so it must stay dangling, not become "defined".
# ---------------------------------------------------------------------------
def test_unpaired_bold_delimiter_is_not_a_false_definition(tmp_path):
    root = _build_minimal_tree(tmp_path)
    _append(
        root,
        "docs/design/PHASE7_EVIDENCE_REPRODUCIBILITY_AND_PUBLICATION_V1.md",
        "2**3 の見積りで L7-2 は **重要** である\n",
    )
    _write(root, "docs/design/OTHER_L7_REF.md", "See L7-2 for details.\n")

    code, out, err = _run(root)
    assert code != 0, (
        f"L7-2 must not be treated as defined by an unpaired '**'; "
        f"got exit {code}, output:\n{out}{err}"
    )
    lines = _dangling_lines(out)
    assert any("L7-2" in line for line in lines), out


# ---------------------------------------------------------------------------
# R-I (code review rework 2) -- dangling lines must be sorted by NUMERIC
# line number, not by sorting the formatted "file:line: ..." string (which
# would sort ":10" before ":2"). Two dangling references in the same file,
# ten lines apart, exercise the difference directly.
# ---------------------------------------------------------------------------
def test_dangling_lines_sorted_by_numeric_line_number(tmp_path):
    root = _build_minimal_tree(tmp_path)
    lines = (
        ["intro", "See SI-97 here."]
        + ["filler"] * 7
        + ["See SI-96 here."]
    )
    assert len(lines) == 10
    _write(root, "docs/design/OTHER_ORDERING.md", "\n".join(lines) + "\n")

    code, out, err = _run(root)
    assert code != 0
    dangling = _dangling_lines(out)
    line_2 = next(line for line in dangling if "SI-97" in line)
    line_10 = next(line for line in dangling if "SI-96" in line)
    assert dangling.index(line_2) < dangling.index(line_10), (
        f"dangling output must be ordered by numeric line number (2 before "
        f"10), not by string comparison of 'file:line:'; got:\n{out}"
    )
