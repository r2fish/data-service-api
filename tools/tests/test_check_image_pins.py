"""tools/tests/test_check_image_pins.py -- pytest wrapper around
tools/check_image_pins.py's own scenarios (Phase 10 WP-2, roadmap R-19).

Deliberately NOT under `conformance-tests/` and NOT discoverable by the
root suite: `tools/` is not in pyproject.toml's `[tool.pytest.ini_options]
testpaths` (same convention as tools/tests/test_check_doc_refs.py and
tools/tests/test_rewrite_hash_refs.py -- see either file's own docstring).

Run directly:
    ./.venv/bin/python -m pytest tools/tests/test_check_image_pins.py -q

Each test name below is cited verbatim in this WP's own manifest
completion-condition/mutation table; do not rename one without updating
that table.
"""
from __future__ import annotations

import importlib.util
import io
import sys
from pathlib import Path

_MODULE_PATH = Path(__file__).resolve().parents[1] / "check_image_pins.py"
_spec = importlib.util.spec_from_file_location("check_image_pins", _MODULE_PATH)
cip = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("check_image_pins", cip)
_spec.loader.exec_module(cip)  # type: ignore[union-attr]


def _run(
    freeze_text: str,
    constraints_text: str,
    required: "tuple[str, ...]" = (),
) -> "tuple[int, str]":
    out = io.StringIO()
    code = cip.run(freeze_text, constraints_text, required=required, out=out)
    return code, out.getvalue()


def test_mismatch_detected() -> None:
    """Completion conditions 1 and 2 (manifest table). Two mutations turn
    this test red: (a) making the comparison always report OK (never
    emit a mismatch) fails the second assertion group below; (b) removing
    the equality check (e.g. replacing `!=` with something that never
    fires) fails it the same way. Both scenarios below assert on a real
    observed line/count -- never a vacuous pass."""
    matching_freeze = "anyio==4.15.0\nclick==8.5.0\n"
    matching_constraints = "anyio==4.15.0\nclick==8.5.0\n"
    code, out = _run(matching_freeze, matching_constraints)
    assert code == 0
    assert "image pins OK: 2 packages checked" in out

    mismatched_freeze = "anyio==4.15.0\nclick==8.6.0\n"
    code, out = _run(mismatched_freeze, matching_constraints)
    assert code == 1
    assert "MISMATCH: click image=8.6.0 constraints=8.5.0" in out


def test_exclusions_are_not_compared() -> None:
    """Completion condition 3. `pip`/`setuptools`/`wheel`/the image's own
    distribution name must never be compared, even when they are absent
    from constraints.txt or pinned to a wildly different version there --
    emptying the exclusion set (mutation) makes every one of these four
    show up as a MISMATCH line, turning this red."""
    freeze_text = (
        "pip==99.0.0\n"
        "setuptools==99.0.0\n"
        "wheel==99.0.0\n"
        "data-service-mitatedb-foundation==0.1.0\n"
        "anyio==4.15.0\n"
    )
    constraints_text = "anyio==4.15.0\n"
    code, out = _run(freeze_text, constraints_text)
    assert code == 0
    assert "image pins OK: 1 packages checked" in out
    assert "MISMATCH" not in out


def test_absent_pin_is_mismatch() -> None:
    """Completion condition 4. A package the image has but constraints.txt
    never mentions must fail with an explicit `constraints=absent` line --
    deleting the absent-check (mutation) makes this pass silently instead,
    turning this red."""
    freeze_text = "anyio==4.15.0\nnewpkg==1.0.0\n"
    constraints_text = "anyio==4.15.0\n"
    code, out = _run(freeze_text, constraints_text)
    assert code == 1
    assert "MISMATCH: newpkg image=1.0.0 constraints=absent" in out


def test_name_normalization() -> None:
    """Completion condition 5. `Foo_Bar` (image) and `foo-bar`
    (constraints.txt) must be treated as the same package -- removing
    normalization (mutation) makes this report a MISMATCH/absent line
    instead of OK, turning this red."""
    freeze_text = "Foo_Bar==1.0.0\n"
    constraints_text = "foo-bar==1.0.0\n"
    code, out = _run(freeze_text, constraints_text)
    assert code == 0
    assert "image pins OK: 1 packages checked" in out


def test_editable_and_direct_reference_lines_are_skipped() -> None:
    """`-e ...` editable lines and `name @ ...` direct references are not
    `name==version` pins (both shapes appear in real `pip freeze` output
    for an editable/self-referential install) -- `check_image_pins.py`
    does not special-case either shape; both simply fail to match
    `_PIN_RE` (which has no embedded-whitespace shape at all) and fall
    through to the general SKIP counter (supervisor ruling 2026-09-08).
    This asserts both halves of that: the two lines are never compared
    as MISMATCH/absent, AND they are visibly counted (`skipped lines: 2`)
    rather than disappearing with no trace. Removing the SKIP counting
    path (mutation: `parse_pins` stops incrementing `skipped`, or `run`
    stops printing it) leaves the `skipped lines: 2` assertion unmet,
    turning this red -- while a mutation that instead started comparing
    these two shapes as ordinary pins would turn `test_mismatch_detected`
    red at the same time (no version to compare for either shape here)."""
    freeze_text = (
        "-e git+https://example.invalid/pkg.git#egg=editable-pkg\n"
        "data-service-mitatedb-foundation @ file:///build\n"
        "anyio==4.15.0\n"
    )
    constraints_text = "anyio==4.15.0\n"
    code, out = _run(freeze_text, constraints_text)
    assert code == 0
    assert "image pins OK: 1 packages checked" in out
    assert "MISMATCH" not in out
    assert "skipped lines: 2" in out


def test_zero_checked_is_a_failure() -> None:
    """An empty (or fully-excluded) freeze must not report a vacuous
    success -- `checked == 0` is its own distinct failure, separate from
    `MISMATCH:`/`MISSING REQUIRED:`, so it cannot be mistaken for "no
    problems found". Removing this floor (mutation: dropping the
    `checked == 0` branch in `run`) makes this pass with exit 0 and
    `image pins OK: 0 packages checked` instead, turning this red."""
    code, out = _run("", "anyio==4.15.0\n")
    assert code == 1
    assert "image pins FAILED: 0 packages checked (vacuous)" in out


def test_missing_required_package_is_a_failure() -> None:
    """`--require <name>` must fail when that name never appears in the
    freeze output at all (e.g. a runtime dependency the image quietly
    stopped installing) -- an absent package is not a "mismatch" (it is
    simply not a key in `image_pins` to compare), so the freeze-vs-
    constraints diff alone cannot catch this; `--require` is the
    dedicated check for it. Removing the `--require` check (mutation:
    `missing_required` always computed as `[]`) makes this pass despite
    `starlette` being absent, turning this red."""
    freeze_text = "anyio==4.15.0\n"
    constraints_text = "anyio==4.15.0\nstarlette==0.40.0\n"
    code, out = _run(freeze_text, constraints_text, required=("starlette",))
    assert code == 1
    assert "MISSING REQUIRED: starlette not found in freeze output" in out
