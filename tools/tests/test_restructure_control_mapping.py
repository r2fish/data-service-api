"""tools/tests/test_restructure_control_mapping.py -- fixture tests for the
`security/CONTROL_MAPPING.md` restructure generate/check pair (design
docs/design/CONTROL_MAPPING_RESTRUCTURE_V1.md, WP-1; axis-table corrective
per monitor ruling 2026-09-14, WP-3 audit `cm-audit-misassign.md`).
Deliberately NOT under `conformance-tests/` and NOT in pyproject.toml's
`testpaths` (same convention as `tools/tests/test_change_class.py`).

Both `tools/restructure_control_mapping.py` (generation) and
`tools/check_control_mapping_restructure.py` (independent checking) are
imported here by file path (never as installed packages), and exercised
through their own pure, git-free entry points -- `generate_from_text` and
`check_from_texts` -- on small, hand-built "old table" fixtures, never on
the real `security/CONTROL_MAPPING.md` (that file is exercised by
`conformance-tests/test_control_mapping_register.py` and by WP-2's own
generation/check runs against the real base revision).

Axis assignment is table-driven, not rule-inferred (the former R0-R6
ladder and its fixture tests are RETIRED -- a WP-3 audit found 38 of 418
real claims misassigned by rule, all traceable to structural flaws in the
rules themselves; see `docs/design/CONTROL_MAPPING_RESTRUCTURE_V1.md` for
the corrective ruling). Fixtures below build their own small axis table
(`heads`, `axes` dicts, matching `load_axes_table`'s own return shape) by
decomposing the fixture's own cells and pairing each claim with an
explicit axis the test names -- never inferred.

Run directly:
    ./.venv/bin/python -m pytest tools/tests/test_restructure_control_mapping.py -q
"""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest

_TOOLS_DIR = Path(__file__).resolve().parents[1]


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, _TOOLS_DIR / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


rcm = _load("rcm_under_test", "restructure_control_mapping.py")
chk = _load("chk_under_test", "check_control_mapping_restructure.py")


# ---------------------------------------------------------------------------
# fixture builders
# ---------------------------------------------------------------------------

PREAMBLE_FIXTURE = """# Security Invariant Control Mapping

Status: **Implementation mapping template**

This document maps common Security Invariants to platform-specific controls. It is intentionally not the source of truth for the invariants themselves.

**Update convention** (phase 7 WP-7 (i), requester ruling 4 --
`docs/design/PHASE7_EVIDENCE_REPRODUCIBILITY_AND_PUBLICATION_V1.md` §5):
「訂正は現行行を書き換え、旧文は履歴へ移す」-- a correction rewrites the
current row below in place, and the superseded text it replaces is moved,
verbatim and unedited, into the per-ID companion file
`CONTROL_MAPPING_HISTORY.md` (headings there are the bare ID only, e.g.
`## SI-14`, so a row's own `[history](CONTROL_MAPPING_HISTORY.md#si-14)`
link resolves to a real GitHub anchor). Each row keeps only today's control
and its evidence -- test names, `file:line`, and any disclosed scope limits
-- plus that one link; it is not a place to re-accumulate the next
correction's own narrative. This file holds exactly one `|`-started table
(`conformance-tests/test_control_mapping_register.py` parses on that
assumption); do not add a second one, and keep every cell as one continuous
line (no raw `|` or embedded newline inside a cell).

**Cell-length cap measurement** (差し戻し rework round 3, 監督裁定 2026-09-06 item
C-1/B-2; re-measured 2026-09-10, WP-9): this file's longest cell is still
SI-14's r2db-api control/evidence cell, now 15,122 characters (15,065 on
2026-09-06, the figure `conformance-tests/test_control_mapping_register.py`'s
own comment records). Its `MAX_CELL_LENGTH = 15200` is that 2026-09-06
measurement plus a 135-char margin, unchanged (78 left today), set independently
of `conformance-tests/CONDITIONS.md`'s own cap (per C-1: a shared cap left that
file's own guard nearly inert; design section 13/WP-8 keeps its own copy)."""

TABLE_HEADER = "| Invariant | r2db-api control/evidence | MitateDB-api control/evidence | Common conformance evidence |"
TABLE_DIVIDER = "|---|---|---|---|"

TAIL_FIXTURE = """

## CCR-14 control-plane compromise boundedness (R-11)

This is a fixture CCR-14 section body, unchanged by the restructure.

## Rule

A blank/TBD mapping is not permission to weaken an invariant."""

PEER_COL = {"r2db-api": 1, "MitateDB-api": 2, "Common": 3}


def make_row(sid: str, name: str, r2db: str, mitate: str, common_no_link: str, frag: str | None = None) -> str:
    frag = frag or sid.lower()
    common = f"{common_no_link} [history](CONTROL_MAPPING_HISTORY.md#{frag})"
    return f"| {sid} {name} | {r2db} | {mitate} | {common} |"


def make_old_file(rows: list[str], preamble: str = PREAMBLE_FIXTURE, tail: str = TAIL_FIXTURE) -> str:
    return preamble + "\n\n" + TABLE_HEADER + "\n" + TABLE_DIVIDER + "\n" + "\n".join(rows) + tail


def build_axes_table(old_text: str, axes_by_key: dict[tuple[str, str], list[str]]):
    """Build (heads, axes) dicts in `load_axes_table`'s own return shape,
    by decomposing `old_text`'s actual cells and pairing each claim (in
    decomposition order) with the caller-supplied axis list for that
    (sid, peer) -- axes are never inferred here, only declared, matching
    how the real `tools/control_mapping_axes.tsv` is authored (initial
    values from a one-time script, then hand-corrected per the WP-3
    audit)."""
    old = rcm.OldFile(old_text)
    heads: dict[tuple[str, str, int], str] = {}
    axes: dict[tuple[str, str, int], str] = {}
    for cells in old.rows:
        sid = re.match(r"^(SI-\d+)", cells[0]).group(1)
        for peer, col in PEER_COL.items():
            cell = cells[col]
            if peer == "Common":
                cell = rcm.strip_history_link(cell)
            claims = rcm.decompose(cell)
            axis_list = axes_by_key.get((sid, peer))
            if axis_list is None:
                raise KeyError(f"no axis list supplied for ({sid}, {peer}); claims: {claims}")
            assert len(axis_list) == len(claims), (
                f"({sid}, {peer}): {len(claims)} claims decomposed but {len(axis_list)} axes supplied: {claims}"
            )
            for k, (c, ax) in enumerate(zip(claims, axis_list)):
                heads[(sid, peer, k)] = c[:60]
                axes[(sid, peer, k)] = ax
    return heads, axes


def write_axes_tsv(tmp_path: Path, heads: dict, axes: dict) -> Path:
    path = tmp_path / "axes.tsv"
    with open(path, "w", encoding="utf-8") as f:
        f.write("si\tpeer\tindex\thead\taxis\n")
        for key in heads:
            si, peer, index = key
            f.write(f"{si}\t{peer}\t{index}\t{heads[key]}\t{axes[key]}\n")
    return path


# ---------------------------------------------------------------------------
# section 3.1 decomposition -- unit tests (unaffected by the axis-table
# corrective: decompose() itself is unchanged)
# ---------------------------------------------------------------------------


def test_decompose_cuts_before_bold_label():
    cell = "Plain lead-in text **Label**: the labelled part continues here."
    claims = rcm.decompose(cell)
    assert claims == [
        "Plain lead-in text",
        "**Label**: the labelled part continues here.",
    ]


def test_decompose_cuts_after_period_space_and_semicolon_space():
    cell = "First sentence. Second clause; third clause."
    claims = rcm.decompose(cell)
    assert claims == ["First sentence.", "Second clause;", "third clause."]


@pytest.mark.parametrize("abbr", ["vs.", "e.g.", "i.e.", "..."])
def test_decompose_does_not_cut_after_abbreviation_period(abbr):
    cell = f"Compare A {abbr} B in the next clause. Then this new claim starts."
    claims = rcm.decompose(cell)
    assert len(claims) == 2
    assert claims[0] == f"Compare A {abbr} B in the next clause."
    assert claims[1] == "Then this new claim starts."


def test_decompose_does_not_cut_after_abbreviation_inside_backticks():
    # "vs." and "..." occurring INSIDE a backtick span must never be
    # treated as a cut/abbreviation boundary at all -- the tick-masking
    # keeps the whole span untouched regardless of its punctuation.
    cell = "See `a vs. b ...` for the comparison. Next claim follows."
    claims = rcm.decompose(cell)
    assert claims == ["See `a vs. b ...` for the comparison.", "Next claim follows."]


def test_decompose_abbreviation_exception_never_applies_to_semicolon():
    # A ';' segment can never end with a '.'-ending abbreviation string, so
    # the exception must never suppress a ';' cut.
    cell = "Clause ending vs.; next clause here."
    claims = rcm.decompose(cell)
    assert claims == ["Clause ending vs.;", "next clause here."]


def test_decompose_does_not_cut_inside_backtick_span():
    cell = "See `a.b; c(d)` for details. Second claim follows."
    claims = rcm.decompose(cell)
    assert claims == ["See `a.b; c(d)` for details.", "Second claim follows."]


def test_decompose_does_not_cut_inside_parens_outside_backticks():
    cell = "Outer text (with an inner. clause; here) continues. Next claim."
    claims = rcm.decompose(cell)
    assert claims == [
        "Outer text (with an inner. clause; here) continues.",
        "Next claim.",
    ]


def test_decompose_preserves_all_non_whitespace_characters():
    cell = (
        "First bit `code(with.semis;and.periods)` and more text. "
        "**Bold Label**: labelled content here; more content; final part."
    )
    claims = rcm.decompose(cell)
    rebuilt = " ".join(claims)
    assert "".join(rebuilt.split()) == "".join(cell.split())


def test_decompose_drops_empty_claims_and_strips_whitespace():
    cell = "  Leading space claim.    Trailing space claim.   "
    claims = rcm.decompose(cell)
    assert claims == ["Leading space claim.", "Trailing space claim."]
    assert all(c == c.strip() for c in claims)


def test_check_no_forbidden_markup_stops_on_escaped_pipe():
    with pytest.raises(rcm.GenerationError):
        rcm.check_no_forbidden_markup("some text with an escaped \\| pipe")


def test_check_no_forbidden_markup_stops_on_br_tag():
    with pytest.raises(rcm.GenerationError):
        rcm.check_no_forbidden_markup("some text with a <br> tag")


def test_check_no_forbidden_markup_accepts_clean_text():
    rcm.check_no_forbidden_markup("perfectly ordinary text with `code` and | not escaped")


def test_checker_check_no_forbidden_markup_stops_on_escaped_pipe():
    """Code review item (d): the CHECKER got its own copy of this stop
    check (it previously had none at all)."""
    with pytest.raises(chk.CheckError):
        chk.check_no_forbidden_markup("some text with an escaped \\| pipe")


def test_checker_check_no_forbidden_markup_stops_on_br_tag():
    with pytest.raises(chk.CheckError):
        chk.check_no_forbidden_markup("some text with a <br> tag")


def test_checker_check_no_forbidden_markup_accepts_clean_text():
    chk.check_no_forbidden_markup("perfectly ordinary text with `code` and | not escaped")


def test_checker_check_from_texts_stops_red_on_forbidden_markup_in_old_text():
    with pytest.raises(chk.CheckError):
        chk.check_from_texts("old text with an escaped \\| pipe", "irrelevant new text")


# ---------------------------------------------------------------------------
# axis table: loading and 1:1-with-decomposition validation
# ---------------------------------------------------------------------------


def test_load_axes_table_reads_rows_and_rejects_duplicate_keys(tmp_path):
    path = tmp_path / "axes.tsv"
    path.write_text(
        "si\tpeer\tindex\thead\taxis\n"
        "SI-90\tr2db-api\t0\tFirst claim head\tControl\n"
        "SI-90\tr2db-api\t1\tSecond claim head\tEvidence\n"
    )
    heads, axes = rcm.load_axes_table(path)
    assert heads[("SI-90", "r2db-api", 0)] == "First claim head"
    assert axes[("SI-90", "r2db-api", 1)] == "Evidence"


def test_load_axes_table_rejects_duplicate_row_for_same_key(tmp_path):
    path = tmp_path / "axes.tsv"
    path.write_text(
        "si\tpeer\tindex\thead\taxis\n"
        "SI-90\tr2db-api\t0\tFirst claim head\tControl\n"
        "SI-90\tr2db-api\t0\tFirst claim head\tStatus\n"  # duplicate (si, peer, index) key
    )
    with pytest.raises(rcm.GenerationError, match="duplicate"):
        rcm.load_axes_table(path)


def test_load_axes_table_rejects_duplicate_head_within_the_same_si_peer(tmp_path):
    """Monitor ruling 2026-09-14, code review item 2: two DIFFERENT index
    rows for the same (si, peer) sharing the identical `head` -- e.g. a
    copy-paste authoring mistake -- must stop generation red, even though
    the (si, peer, index) keys themselves are not duplicated."""
    path = tmp_path / "axes.tsv"
    path.write_text(
        "si\tpeer\tindex\thead\taxis\n"
        "SI-90\tr2db-api\t0\tSame head text repeated by mistake\tControl\n"
        "SI-90\tr2db-api\t1\tSame head text repeated by mistake\tEvidence\n"
    )
    with pytest.raises(rcm.GenerationError, match="duplicate head"):
        rcm.load_axes_table(path)


def test_load_axes_table_allows_the_same_head_across_different_si_peer_keys(tmp_path):
    # The duplicate-head guard is scoped to one (si, peer); the same short
    # head text recurring in a DIFFERENT (si, peer) is not an error.
    path = tmp_path / "axes.tsv"
    path.write_text(
        "si\tpeer\tindex\thead\taxis\n"
        "SI-90\tr2db-api\t0\tShared short head\tControl\n"
        "SI-91\tr2db-api\t0\tShared short head\tEvidence\n"
    )
    heads, axes = rcm.load_axes_table(path)
    assert heads[("SI-90", "r2db-api", 0)] == "Shared short head"
    assert heads[("SI-91", "r2db-api", 0)] == "Shared short head"


def test_load_axes_table_rejects_unknown_axis_value(tmp_path):
    path = tmp_path / "axes.tsv"
    path.write_text("si\tpeer\tindex\thead\taxis\nSI-90\tr2db-api\t0\tsome head\tNotAnAxis\n")
    with pytest.raises(rcm.GenerationError):
        rcm.load_axes_table(path)


def test_assign_axes_from_table_matches_a_correct_table_cleanly():
    claims_by_key = {("SI-90", "r2db-api"): ["First claim.", "Second claim."]}
    heads = {("SI-90", "r2db-api", 0): "First claim.", ("SI-90", "r2db-api", 1): "Second claim."}
    axes = {("SI-90", "r2db-api", 0): "Control", ("SI-90", "r2db-api", 1): "Evidence"}
    result = rcm.assign_axes_from_table(claims_by_key, heads, axes)
    assert result == {("SI-90", "r2db-api", 0): "Control", ("SI-90", "r2db-api", 1): "Evidence"}


def test_assign_axes_from_table_missing_row_stops_red():
    claims_by_key = {("SI-90", "r2db-api"): ["First claim.", "Second claim."]}
    heads = {("SI-90", "r2db-api", 0): "First claim."}  # index 1 row deleted
    axes = {("SI-90", "r2db-api", 0): "Control"}
    with pytest.raises(rcm.GenerationError, match="missing"):
        rcm.assign_axes_from_table(claims_by_key, heads, axes)


def test_assign_axes_from_table_head_mismatch_stops_red():
    claims_by_key = {("SI-90", "r2db-api"): ["First claim.", "Second claim."]}
    heads = {("SI-90", "r2db-api", 0): "First claim.", ("SI-90", "r2db-api", 1): "Second claim CHANGED."}
    axes = {("SI-90", "r2db-api", 0): "Control", ("SI-90", "r2db-api", 1): "Evidence"}
    with pytest.raises(rcm.GenerationError, match="head mismatch"):
        rcm.assign_axes_from_table(claims_by_key, heads, axes)


def test_assign_axes_from_table_surplus_row_stops_red():
    # A table row exists for an index the (sid, peer) never reaches (only
    # 1 claim decomposed, but the table has an index-1 row too).
    claims_by_key = {("SI-90", "r2db-api"): ["Only claim."]}
    heads = {("SI-90", "r2db-api", 0): "Only claim.", ("SI-90", "r2db-api", 1): "Extra row head."}
    axes = {("SI-90", "r2db-api", 0): "Control", ("SI-90", "r2db-api", 1): "Status"}
    with pytest.raises(rcm.GenerationError, match="surplus"):
        rcm.assign_axes_from_table(claims_by_key, heads, axes)


def test_assign_axes_from_table_surplus_row_for_an_absent_si_peer_stops_red():
    # A table row names an (sid, peer) that never even appears among the
    # document's own decomposed claims.
    claims_by_key = {("SI-90", "r2db-api"): ["Only claim."]}
    heads = {
        ("SI-90", "r2db-api", 0): "Only claim.",
        ("SI-99", "Common", 0): "A row for a nonexistent SI.",
    }
    axes = {("SI-90", "r2db-api", 0): "Control", ("SI-99", "Common", 0): "Status"}
    with pytest.raises(rcm.GenerationError, match="surplus"):
        rcm.assign_axes_from_table(claims_by_key, heads, axes)


# ---------------------------------------------------------------------------
# full pipeline -- byte-exact small fixture (code review item (c): compares
# the FULL generated output and the FULL assignment log, not substring
# presence checks; the fixture exercises a backtick-internal "..." and a
# "vs." abbreviation as well as the ordinary '. '/'; ' cuts)
# ---------------------------------------------------------------------------


def test_generate_from_text_small_fixture_byte_exact():
    rows = [
        make_row(
            "SI-90",
            "Fixture Alpha",
            r2db=(
                "Topology deny rules plus per-credential role/scope records; "
                "negative topology and isolation tests; "
                "see `a vs. b ...` for the comparison; "
                "production containment evidence not yet present."
            ),
            mitate="`identifiers.py` validation; not a coverage gap here.",
            common_no_link="lateral tests, `test_x.py`, and `test_y.py`",
        ),
    ]
    old = make_old_file(rows)
    axes_by_key = {
        ("SI-90", "r2db-api"): ["Control", "Evidence", "Control", "Status"],
        ("SI-90", "MitateDB-api"): ["Control", "Control"],
        ("SI-90", "Common"): ["Evidence"],
    }
    heads, axes = build_axes_table(old, axes_by_key)
    full, log = rcm.generate_from_text(old, (heads, axes))

    expected_full = (
        "# Security Invariant Control Mapping\n"
        "\n"
        "Status: **Implementation mapping template**\n"
        "\n"
        "Version: **2.0** (2026-09-14; structure only, content unchanged -- "
        "docs/design/CONTROL_MAPPING_RESTRUCTURE_V1.md)\n"
        "\n"
        "This document maps common Security Invariants to platform-specific "
        "controls. It is intentionally not the source of truth for the "
        "invariants themselves.\n"
        "\n"
        "Each claim is one bullet under its invariant, subsection (r2db-api / "
        "MitateDB-api / Common) and axis (Control / Evidence / Status); "
        "`- —` marks an axis with no claim.\n"
        "\n"
        "**Update convention** (phase 7 WP-7 (i), requester ruling 4 --\n"
        "`docs/design/PHASE7_EVIDENCE_REPRODUCIBILITY_AND_PUBLICATION_V1.md` §5):\n"
        "「訂正は現行行を書き換え、旧文は履歴へ移す」-- a correction rewrites the\n"
        "current claim below in place, and the superseded text it replaces is moved,\n"
        "verbatim and unedited, into the per-ID companion file\n"
        "`CONTROL_MAPPING_HISTORY.md` (headings there are the bare ID only, e.g.\n"
        "`## SI-14`, so a section's own `[history](CONTROL_MAPPING_HISTORY.md#si-14)`\n"
        "link resolves to a real GitHub anchor). Each section keeps only today's control\n"
        "and its evidence -- test names, `file:line`, and any disclosed scope limits\n"
        "-- plus that one link; it is not a place to re-accumulate the next\n"
        "correction's own narrative. This file holds no `|`-started table\n"
        "(`conformance-tests/test_control_mapping_register.py` parses on that\n"
        "assumption); do not add one, and keep every claim as one bullet on one\n"
        "line (no embedded newline inside a claim).\n"
        "\n"
        "**Length cap measurement** (差し戻し rework round 3, 監督裁定 2026-09-06 item\n"
        "C-1/B-2; re-measured 2026-09-10, WP-9): this file's longest (SI, subsection) block is still\n"
        "SI-14's r2db-api block, now 15,122 characters (15,065 on\n"
        "2026-09-06, the figure `conformance-tests/test_control_mapping_register.py`'s\n"
        "own comment records). Its `MAX_BLOCK_LENGTH = 15200` is that 2026-09-06\n"
        "measurement plus a 135-char margin, unchanged (78 left today), set independently\n"
        "of `conformance-tests/CONDITIONS.md`'s own cap (per C-1: a shared cap left that\n"
        "file's own guard nearly inert; design section 13/WP-8 keeps its own copy). "
        "A block is one subsection's claims (r2db-api, MitateDB-api or Common) joined "
        "by single spaces. Each physical line is also capped at `MAX_LINE_LENGTH = 300`.\n"
        "\n"
        "## SI-90 Fixture Alpha\n"
        "\n"
        "[history](CONTROL_MAPPING_HISTORY.md#si-90)\n"
        "\n"
        "### r2db-api\n"
        "\n"
        "#### Control\n"
        "\n"
        "- Topology deny rules plus per-credential role/scope records;\n"
        "- see `a vs. b ...` for the comparison;\n"
        "\n"
        "#### Evidence\n"
        "\n"
        "- negative topology and isolation tests;\n"
        "\n"
        "#### Status\n"
        "\n"
        "- production containment evidence not yet present.\n"
        "\n"
        "### MitateDB-api\n"
        "\n"
        "#### Control\n"
        "\n"
        "- `identifiers.py` validation;\n"
        "- not a coverage gap here.\n"
        "\n"
        "#### Evidence\n"
        "\n"
        "- —\n"
        "\n"
        "#### Status\n"
        "\n"
        "- —\n"
        "\n"
        "### Common\n"
        "\n"
        "#### Control\n"
        "\n"
        "- —\n"
        "\n"
        "#### Evidence\n"
        "\n"
        "- lateral tests, `test_x.py`, and `test_y.py`\n"
        "\n"
        "#### Status\n"
        "\n"
        "- —\n"
        "\n"
        "## CCR-14 control-plane compromise boundedness (R-11)\n"
        "\n"
        "This is a fixture CCR-14 section body, unchanged by the restructure.\n"
        "\n"
        "## Rule\n"
        "\n"
        "A blank/TBD mapping is not permission to weaken an invariant.\n"
    )
    assert full == expected_full

    expected_log = [
        ("SI-90", "r2db-api", 0, "Control"),
        ("SI-90", "r2db-api", 1, "Evidence"),
        ("SI-90", "r2db-api", 2, "Control"),
        ("SI-90", "r2db-api", 3, "Status"),
        ("SI-90", "MitateDB-api", 0, "Control"),
        ("SI-90", "MitateDB-api", 1, "Control"),
        ("SI-90", "Common", 0, "Evidence"),
    ]
    assert log == expected_log

    code, line = chk.check_from_texts(old, full)
    assert code == 0, line
    assert "missing=0 added=0 moved=0 reordered=0 unbalanced=0" in line
    assert "chars=identical" in line


# ---------------------------------------------------------------------------
# WP-1 completion-condition mutation table (design section 7, row 1):
# the CHECKER's own V1-V8 checks must each go red on the named mutation.
# ---------------------------------------------------------------------------


def _base_fixture_pair():
    rows = [
        make_row(
            "SI-90",
            "Fixture Alpha",
            r2db="First r2db claim here. Second r2db claim follows.",
            mitate="Solo MitateDB claim.",
            common_no_link="Solo common claim.",
        ),
        make_row(
            "SI-91",
            "Fixture Beta",
            r2db="A totally different r2db claim.",
            mitate="Another MitateDB claim.",
            common_no_link="Another common claim.",
        ),
    ]
    old = make_old_file(rows)
    axes_by_key = {
        ("SI-90", "r2db-api"): ["Control", "Control"],
        ("SI-90", "MitateDB-api"): ["Control"],
        ("SI-90", "Common"): ["Evidence"],
        ("SI-91", "r2db-api"): ["Control"],
        ("SI-91", "MitateDB-api"): ["Control"],
        ("SI-91", "Common"): ["Evidence"],
    }
    heads, axes = build_axes_table(old, axes_by_key)
    full, _log = rcm.generate_from_text(old, (heads, axes))
    return old, full


def test_mutation_delete_one_claim_is_missing_1():
    old, full = _base_fixture_pair()
    mutated = full.replace("- Second r2db claim follows.\n", "")
    code, line = chk.check_from_texts(old, mutated)
    assert code == 1
    assert "missing=1 added=0" in line


def test_mutation_add_one_word_is_missing_1_added_1():
    old, full = _base_fixture_pair()
    mutated = full.replace(
        "- Second r2db claim follows.",
        "- Second r2db claim follows now.",
    )
    code, line = chk.check_from_texts(old, mutated)
    assert code == 1
    assert "missing=1 added=1" in line


def test_mutation_move_claim_to_a_different_si_is_moved_1():
    old, full = _base_fixture_pair()
    mutated = full.replace("- Second r2db claim follows.\n", "", 1)
    mutated = mutated.replace(
        "- A totally different r2db claim.\n",
        "- A totally different r2db claim.\n- Second r2db claim follows.\n",
        1,
    )
    code, line = chk.check_from_texts(old, mutated)
    assert code == 1
    assert "missing=0 added=0 moved=1" in line


def test_mutation_swap_two_claims_in_same_axis_is_reordered_1():
    old, full = _base_fixture_pair()
    mutated = full.replace(
        "- First r2db claim here.\n- Second r2db claim follows.",
        "- Second r2db claim follows.\n- First r2db claim here.",
    )
    code, line = chk.check_from_texts(old, mutated)
    assert code == 1
    assert "missing=0 added=0 moved=0 reordered=1" in line


def test_mutation_change_one_char_of_si_name_is_sections_differs():
    old, full = _base_fixture_pair()
    mutated = full.replace("## SI-90 Fixture Alpha", "## SI-90 Fixture Alphb")
    code, line = chk.check_from_texts(old, mutated)
    assert code == 1
    assert "sections=differs" in line


def test_mutation_change_history_fragment_breaks_link():
    old, full = _base_fixture_pair()
    mutated = full.replace(
        "[history](CONTROL_MAPPING_HISTORY.md#si-90)",
        "[history](CONTROL_MAPPING_HISTORY.md#si-99)",
    )
    code, line = chk.check_from_texts(old, mutated)
    assert code == 1
    assert "history=1/2" in line


def test_mutation_duplicate_history_link_breaks_history_count():
    old, full = _base_fixture_pair()
    mutated = full.replace(
        "[history](CONTROL_MAPPING_HISTORY.md#si-90)",
        "[history](CONTROL_MAPPING_HISTORY.md#si-90) [history](CONTROL_MAPPING_HISTORY.md#si-90)",
    )
    code, line = chk.check_from_texts(old, mutated)
    assert code == 1
    assert "history=1/2" in line


def test_mutation_change_one_char_of_ccr14_is_ccr14_differs():
    old, full = _base_fixture_pair()
    mutated = full.replace(
        "This is a fixture CCR-14 section body, unchanged by the restructure.",
        "This is a fixture CCR-14 section body, unchangedXby the restructure.",
    )
    code, line = chk.check_from_texts(old, mutated)
    assert code == 1
    assert "ccr14=differs" in line


def test_mutation_change_preamble_word_outside_p1_to_p4_is_preamble_differs():
    old, full = _base_fixture_pair()
    mutated = full.replace(
        "This document maps common Security Invariants to platform-specific controls.",
        "This document maps common Security Invariants to platform-specific systems.",
    )
    code, line = chk.check_from_texts(old, mutated)
    assert code == 1
    assert "preamble=differs" in line


def test_mutation_delete_one_backtick_is_unbalanced_1():
    rows = [
        make_row(
            "SI-90",
            "Fixture Alpha",
            r2db="See `test_something.py` for coverage.",
            mitate="Solo MitateDB claim.",
            common_no_link="Solo common claim.",
        ),
    ]
    old = make_old_file(rows)
    axes_by_key = {
        ("SI-90", "r2db-api"): ["Evidence"],
        ("SI-90", "MitateDB-api"): ["Control"],
        ("SI-90", "Common"): ["Evidence"],
    }
    heads, axes = build_axes_table(old, axes_by_key)
    full, _log = rcm.generate_from_text(old, (heads, axes))
    mutated = full.replace("`test_something.py`", "`test_something.py")
    code, line = chk.check_from_texts(old, mutated)
    assert code == 1
    assert "unbalanced=1" in line


def test_mutation_dropped_decomposition_character_is_chars_differs(monkeypatch):
    """Code review item (b): "分解関数を、切れ目の文字を1つ落とす版に
    差し替える" -- monkeypatch BOTH scripts' own `decompose` to a version
    that drops one character right at a cut boundary, so BOTH the
    generator's output and the checker's own independent re-decomposition
    of the old cell are affected identically (a real swapped-in buggy
    decompose function would affect both, since each script calls its OWN
    `decompose` at the point named below). Asserts `missing=0 added=0`
    (the claim COUNT and total multiset-adjacent character content still
    look consistent enough not to trip V2) and `chars=differs` (V8 catches
    the dropped character)."""
    old, full = _base_fixture_pair()

    # Capture each module's TRUE original `decompose` before patching --
    # rcm's and chk's are two independently-written implementations (the
    # whole point of the generate/check split), so each gets its own
    # dropping wrapper built on its own original, not a shared one.
    original_rcm_decompose = rcm.decompose
    original_chk_decompose = chk.decompose

    def make_dropping_decompose(original):
        def dropping_decompose(cell: str) -> list[str]:
            claims = original(cell)
            if claims:
                claims[0] = claims[0][:-1]  # drop the last character of the first claim
            return claims

        return dropping_decompose

    monkeypatch.setattr(rcm, "decompose", make_dropping_decompose(original_rcm_decompose))
    monkeypatch.setattr(chk, "decompose", make_dropping_decompose(original_chk_decompose))

    axes_by_key = {
        ("SI-90", "r2db-api"): ["Control", "Control"],
        ("SI-90", "MitateDB-api"): ["Control"],
        ("SI-90", "Common"): ["Evidence"],
        ("SI-91", "r2db-api"): ["Control"],
        ("SI-91", "MitateDB-api"): ["Control"],
        ("SI-91", "Common"): ["Evidence"],
    }
    heads, axes = build_axes_table(old, axes_by_key)
    buggy_full, _log = rcm.generate_from_text(old, (heads, axes))

    code, line = chk.check_from_texts(old, buggy_full)
    assert code == 1
    assert "missing=0 added=0" in line
    assert "chars=differs" in line


# ---------------------------------------------------------------------------
# WP-1 completion-condition mutation table (design section 7, row 2), as
# amended by the axis-table corrective: the GENERATOR must enforce the
# table's own 1:1-with-decomposition contract (covered above); its
# decomposition (section 3.1) is otherwise fully covered by the unit tests
# above.
# ---------------------------------------------------------------------------


def test_v6_preamble_check_uses_the_declared_max_line_length():
    """Sanity check that V6 recomputes the expected preamble using the
    NEW file's own declared MAX_LINE_LENGTH, not a hard-coded number --
    otherwise every real fixture (whose longest line differs from the
    real document's 1400) would spuriously fail V6."""
    rows = [
        make_row(
            "SI-90",
            "Fixture Alpha",
            r2db="Short claim.",
            mitate="Short claim.",
            common_no_link="Short claim.",
        ),
    ]
    old = make_old_file(rows)
    axes_by_key = {
        ("SI-90", "r2db-api"): ["Control"],
        ("SI-90", "MitateDB-api"): ["Control"],
        ("SI-90", "Common"): ["Evidence"],
    }
    heads, axes = build_axes_table(old, axes_by_key)
    full, _log = rcm.generate_from_text(old, (heads, axes))
    assert "MAX_LINE_LENGTH = 1400" not in full  # fixture's longest line is much shorter
    code, line = chk.check_from_texts(old, full)
    assert code == 0, line
    assert "preamble=identical" in line
