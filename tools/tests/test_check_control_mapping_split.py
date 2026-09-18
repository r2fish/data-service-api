"""tools/tests/test_check_control_mapping_split.py -- fixture tests for
`tools/check_control_mapping_split.py` (design
docs/design/CONTROL_MAPPING_MULTI_BLOCK_V0_1.md v0.4, section 6). Loaded by
file path, never as an installed package (same convention as
`tools/tests/test_restructure_control_mapping.py`). Every fixture below is
a small, hand-built heading/bullet-form document -- work order
docs/work-orders/WORK_ORDER_R50_CONTROL_MAPPING_MULTI_BLOCK_V1.md W1-16:
this suite never reads `security/CONTROL_MAPPING.md`, the real repository
state, or `git` history; `--base`'s git-reading path
(`check_control_mapping_split.read_old_file`) is exercised only through
`check_from_texts`, which takes both texts as plain strings.

Run directly:
    ./.venv/bin/python -m pytest tools/tests/test_check_control_mapping_split.py -q
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parents[1]


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, _TOOLS_DIR / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


split = _load("ccms_under_test", "check_control_mapping_split.py")


# ---------------------------------------------------------------------------
# fixture builders (mirrors conformance-tests/test_control_mapping_register.py's
# own builders in shape, duplicated rather than imported: this file is
# standard-library only and must not import a pytest-carrying module)
# ---------------------------------------------------------------------------


def _axis_lines(bullets: tuple[str, ...]) -> str:
    lines = bullets if bullets else ("—",)
    return "\n".join(f"- {b}" for b in lines)


def _subblock(heading: str, control=("control claim",), evidence=("evidence claim",), status=("—",)) -> str:
    return (
        f"{heading}\n\n"
        f"#### Control\n\n{_axis_lines(control)}\n\n"
        f"#### Evidence\n\n{_axis_lines(evidence)}\n\n"
        f"#### Status\n\n{_axis_lines(status)}\n\n"
    )


def _si(sid: str, name: str, body: str) -> str:
    return f"## {sid} {name}\n\n[history](CONTROL_MAPPING_HISTORY.md#{sid.lower()})\n\n{body}"


def _doc(sections_text: str) -> str:
    return (
        "# Security Invariant Control Mapping\n\n"
        "Status: **Implementation mapping template**\n\n"
        f"{sections_text}"
        "## CCR-14 Something\n\nSome CCR-14 text.\n\n"
        "## Rule\n\nSome rule text.\n"
    )


def _parse(text: str):
    return split.ParsedFile(text)


# ---------------------------------------------------------------------------
# self-match: identical old/new text -> every counter zero, exit 0
# ---------------------------------------------------------------------------


def test_identical_old_and_new_is_an_all_zero_match():
    text = _doc(
        _si("SI-01", "One", _subblock("### r2db-api") + _subblock("### MitateDB-api") + _subblock("### Common"))
    )
    code, line = split.check_from_texts(text, text)
    assert code == 0, line
    assert line == (
        "missing=0 added=0 moved=0 empty_axis_added=0 empty_axis_removed=0 "
        "subsequence=ok preamble=identical ccr14=identical rule=identical"
    ), line


# ---------------------------------------------------------------------------
# W1-12: no body-text global pairing -- a claim moved to a DIFFERENT SI
# must show up as both missing and added, never folded into moved
# ---------------------------------------------------------------------------


def test_move_to_a_different_si_is_missing_and_added_not_moved():
    old = _doc(
        _si("SI-01", "One", _subblock("### r2db-api", control=("shared claim",), evidence=("—",)))
        + _si("SI-02", "Two", _subblock("### r2db-api", control=("—",), evidence=("—",)))
    )
    new = _doc(
        _si("SI-01", "One", _subblock("### r2db-api", control=("—",), evidence=("—",)))
        + _si("SI-02", "Two", _subblock("### r2db-api", control=("shared claim",), evidence=("—",)))
    )
    old_p, new_p = _parse(old), _parse(new)
    missing, added, _mc, _ac = split.check_missing_added(old_p, new_p)
    moved = split.check_moved(old_p, new_p)
    assert (missing, added, moved) == (1, 1, 0), (
        f"a claim moved to a different SI must be counted as missing=1 added=1 moved=0 "
        f"(no global text pairing), got missing={missing} added={added} moved={moved}"
    )


# ---------------------------------------------------------------------------
# 訂正註 1 S-3: `moved` pairs each (sid, peer, axis, body) 4-tuple's
# bullets FIFO between old and new and counts the pairs whose sub-block
# NAME differs -- comparing only the new side (whether it landed on a
# named block) cannot tell "stayed on the same named block" (unmoved)
# from "moved back from a named block to the default one" (moved), and it
# double-charges an already-split document compared to itself.
# ---------------------------------------------------------------------------


def test_moved_is_zero_when_an_already_split_document_is_compared_to_itself():
    text = _doc(
        _si(
            "SI-01",
            "One",
            _subblock("### r2db-api") + _subblock("### r2db-api -- topic", control=("named claim",), evidence=("—",)),
        )
    )
    old_p, new_p = _parse(text), _parse(text)
    assert split.check_moved(old_p, new_p) == 0, (
        "an already-split document compared to itself must be moved=0 (nothing changed sub-block)"
    )


def test_moved_is_one_when_a_bullet_moves_from_a_named_subblock_back_to_default():
    old = _doc(
        _si(
            "SI-01",
            "One",
            _subblock("### r2db-api", control=("aaa",))
            + _subblock("### r2db-api -- topic", control=("bbb",), evidence=("—",)),
        )
    )
    new = _doc(
        _si(
            "SI-01",
            "One",
            _subblock("### r2db-api", control=("aaa", "bbb"))
            + _subblock("### r2db-api -- topic", control=("—",), evidence=("—",)),
        )
    )
    old_p, new_p = _parse(old), _parse(new)
    assert split.check_moved(old_p, new_p) == 1, (
        "a bullet moved from a named sub-block back to the default one must be moved=1"
    )


# ---------------------------------------------------------------------------
# W1-13: '- —' is excluded from the main multiset; net new/removed
# placeholders are counted on a separate counter
# ---------------------------------------------------------------------------


def test_new_empty_axis_placeholder_is_counted_separately_from_the_main_multiset():
    old = _doc(_si("SI-01", "One", _subblock("### r2db-api", status=("real claim",))))
    new = _doc(
        _si(
            "SI-01",
            "One",
            _subblock("### r2db-api", status=("—",))
            + _subblock("### r2db-api -- topic", status=("real claim",)),
        )
    )
    old_p, new_p = _parse(old), _parse(new)
    added, removed = split.check_empty_axis(old_p, new_p)
    assert (added, removed) == (1, 0), (
        f"a Status axis that goes from real content (old) to a NEW '- —' placeholder (new, on the "
        f"default sub-block, while the real claim moves to a named one) must count as "
        f"empty_axis_added=1 empty_axis_removed=0, got added={added} removed={removed}"
    )


# ---------------------------------------------------------------------------
# W1-14: each (sid, peer, axis, subblock)'s matched original indices must
# be a strictly increasing subsequence of the old (sid, peer, axis) order
# ---------------------------------------------------------------------------


def test_subsequence_ok_when_a_subblocks_bullets_keep_their_relative_order():
    old = _doc(_si("SI-01", "One", _subblock("### r2db-api", control=("one", "two", "three"))))
    new = _doc(
        _si("SI-01", "One", _subblock("### r2db-api -- topic", control=("one", "two", "three"), evidence=("—",)))
    )
    assert split.check_subsequence(_parse(old), _parse(new)) is True


def test_subsequence_violation_when_a_subblock_reorders_its_bullets():
    old = _doc(_si("SI-01", "One", _subblock("### r2db-api", control=("one", "two", "three"))))
    new = _doc(
        _si("SI-01", "One", _subblock("### r2db-api -- topic", control=("three", "one"), evidence=("—",)))
    )
    assert split.check_subsequence(_parse(old), _parse(new)) is False, (
        "a sub-block whose bullets appear out of their original relative order must be a subsequence violation"
    )


# ---------------------------------------------------------------------------
# CCR-14 / Rule invariance always gates exit code; preamble does not
# (design section 6, point 6 -- a legitimate split rewrites the preamble)
# ---------------------------------------------------------------------------


def test_ccr14_difference_fails_the_check():
    old = _doc(_si("SI-01", "One", _subblock("### r2db-api")))
    new = old.replace("Some CCR-14 text.", "A different CCR-14 text.")
    code, line = split.check_from_texts(old, new)
    assert code == 1 and "ccr14=differs" in line, line


def test_rule_difference_fails_the_check():
    """W1-15: the '## Rule' section must be verbatim-unchanged (design
    section 6, point 6)."""
    old = _doc(_si("SI-01", "One", _subblock("### r2db-api")))
    new = old.replace("Some rule text.", "A different rule text.")
    code, line = split.check_from_texts(old, new)
    assert code == 1 and "rule=differs" in line, line


def test_preamble_difference_alone_does_not_fail_the_check():
    old = _doc(_si("SI-01", "One", _subblock("### r2db-api")))
    new = old.replace("Status: **Implementation mapping template**", "Status: **Implementation mapping template v2**")
    code, line = split.check_from_texts(old, new)
    assert code == 0 and "preamble=differs" in line, line


# ---------------------------------------------------------------------------
# 訂正註 1 S-2: `--expect "<line>"` turns the by-hand summary-line
# comparison into a machine gate (`apply_expect`), and a `preamble=differs`
# result gets a unified diff of just the two preambles.
# ---------------------------------------------------------------------------


def test_expect_mismatch_when_a_bullet_is_lost_exits_1():
    old = _doc(_si("SI-01", "One", _subblock("### r2db-api", control=("one", "two"))))
    new = _doc(_si("SI-01", "One", _subblock("### r2db-api", control=("one",))))
    code, line = split.check_from_texts(old, new)
    all_zero_line = (
        "missing=0 added=0 moved=0 empty_axis_added=0 empty_axis_removed=0 "
        "subsequence=ok preamble=identical ccr14=identical rule=identical"
    )
    adjusted = split.apply_expect(code, line, all_zero_line)
    assert adjusted == 1, (
        f"a lost bullet's aggregate line must mismatch an all-zero --expect and exit 1, "
        f"got line={line!r} adjusted_code={adjusted}"
    )


def test_expect_match_exits_0():
    old = _doc(_si("SI-01", "One", _subblock("### r2db-api")))
    code, line = split.check_from_texts(old, old)
    adjusted = split.apply_expect(code, line, line)
    assert adjusted == 0, (line, adjusted)


def test_preamble_diff_is_empty_when_preambles_are_identical():
    old = _doc(_si("SI-01", "One", _subblock("### r2db-api")))
    assert split.preamble_diff(_parse(old), _parse(old)) == ""


def test_preamble_diff_shows_the_changed_preamble_line():
    old = _doc(_si("SI-01", "One", _subblock("### r2db-api")))
    new = old.replace("Status: **Implementation mapping template**", "Status: **Implementation mapping template v2**")
    diff = split.preamble_diff(_parse(old), _parse(new))
    assert "-Status: **Implementation mapping template**" in diff, diff
    assert "+Status: **Implementation mapping template v2**" in diff, diff


def test_unrecognized_subblock_heading_raises_check_error():
    old = _doc(_si("SI-01", "One", _subblock("### r2db-api")))
    new = old.replace("### r2db-api", "### NotAPeer")
    try:
        split.check_from_texts(old, new)
    except split.CheckError:
        pass
    else:
        raise AssertionError("expected CheckError for an unrecognized sub-block heading")
