"""`ops.py` `_build_parser` -- help text for `apply-platform-migration`
and the two `--data-process-count-total`/`--control-process-count-total`
`inventory` arguments (R-53 work order section 1), and the same
subcommand's section-heading comment and `cmd_apply_platform_migration`
docstring (R-55 work order section 1).

Covers: the platform-migration subcommand's own help enumerates its
accepted filenames by deriving them from `_PLATFORM_MIGRATION_FILENAMES`
itself (never a hardcoded digit string), never mentions "work package",
and carries the confirmed replacement sentence pointing at the runbook's
gated procedure; the two process-count-total arguments each carry their
own confirmed WORST-CASE wording and never claim to report the count
"actually running"; and the production instruction `ops.py`'s own file
body carries -- in the section-heading comment and in the subcommand
function's docstring -- is that same single instruction, naming that
same single runbook section, instead of restating a subset of that
section's own preconditions (section 10.10's preconditions still name
the isolated proof, the independent audit and the requester's
approval).
"""
from __future__ import annotations

import argparse
import ast
import inspect
import re
from pathlib import Path

import mitatedb_api.ops as ops


def _subparsers_action(parser: argparse.ArgumentParser) -> argparse._SubParsersAction:
    return next(a for a in parser._subparsers._group_actions if a.dest == "command")


def _apply_platform_migration_help(parser: argparse.ArgumentParser) -> str:
    action = next(
        a for a in _subparsers_action(parser)._choices_actions
        if a.dest == "apply-platform-migration"
    )
    return action.help


def _inventory_argument_help(parser: argparse.ArgumentParser, dest: str) -> str:
    inventory_parser = _subparsers_action(parser).choices["inventory"]
    action = next(a for a in inventory_parser._actions if a.dest == dest)
    return action.help


def test_apply_platform_migration_help_enumeration_is_derived_from_the_constant(monkeypatch):
    """Completion condition 1: the help text's number enumeration
    tracks `_PLATFORM_MIGRATION_FILENAMES` itself, rather than being
    hardcoded -- a synthetic filename appended to the constant appears
    (by its own leading 4 digits) in a freshly built parser's help."""
    synthetic = ops._PLATFORM_MIGRATION_FILENAMES + ("0099_synthetic_test_only.sql",)
    assert len(synthetic) >= 1
    monkeypatch.setattr(ops, "_PLATFORM_MIGRATION_FILENAMES", synthetic)
    help_text = _apply_platform_migration_help(ops._build_parser())
    expected_enum = "/".join(name[:4] for name in synthetic)
    assert expected_enum in help_text
    assert "0099" in help_text


def test_apply_platform_migration_help_never_mentions_work_package_and_has_the_confirmed_sentence():
    """Completion condition 2: the old "this work package" sentence is
    gone, and the confirmed replacement sentence is present verbatim."""
    help_text = _apply_platform_migration_help(ops._build_parser())
    assert "work package" not in help_text
    assert (
        "Against production, run it only through the runbook's gated procedure "
        "(docs/cloud-run-cloud-sql.md section 10)"
    ) in help_text


def test_data_process_count_total_help_is_the_confirmed_worst_case_text():
    """Completion condition 3 (data side): the confirmed WORST-CASE
    wording is present verbatim and "actually running" is gone."""
    help_text = _inventory_argument_help(ops._build_parser(), "data_process_count_total")
    assert "actually running" not in help_text
    assert help_text == (
        "WORST-CASE Data-plane process count: the sum of the process ceilings of every "
        "revision that can serve at the same time, plus the NEW candidate's own ceiling "
        "(a positive integer, used for connection demand). Never the number of instances "
        "running at the moment of the read -- omit to leave item (8) unknown"
    )


def test_control_process_count_total_help_is_the_confirmed_worst_case_text():
    """Completion condition 3 (control side): the confirmed WORST-CASE
    wording is present verbatim and "actually running" is gone."""
    help_text = _inventory_argument_help(ops._build_parser(), "control_process_count_total")
    assert "actually running" not in help_text
    assert help_text == (
        "WORST-CASE Control-plane process count: the sum of the process ceilings of every "
        "revision that can serve at the same time, plus the NEW candidate's own ceiling. "
        "Never the number of instances running at the moment of the read -- omit (with "
        "--control-not-deployed absent too) to leave item (8) unknown"
    )


def test_thread_limit_help_is_pinned():
    """`--thread-limit`'s own help text, pinned verbatim."""
    help_text = _inventory_argument_help(ops._build_parser(), "thread_limit")
    assert help_text == (
        "the NEW-basis revision's own declared MITATEDB_THREAD_LIMIT value (a positive "
        "integer) -- always required for item (8) (--data-process-count-total can never be "
        "entirely old-basis); omit to leave item (8) unknown"
    )


def test_data_process_count_old_basis_help_is_pinned():
    """`--data-process-count-old-basis`'s own help text, pinned verbatim."""
    help_text = _inventory_argument_help(ops._build_parser(), "data_process_count_old_basis")
    assert help_text == (
        "the count, within --data-process-count-total, of Data-plane processes still on the "
        "OLD basis (sized by --concurrency rather than by --thread-limit's own "
        "role_pool_size) -- 0 declares none are; omit to leave item (8) unknown"
    )


def test_concurrency_help_names_the_old_basis_condition():
    """`--concurrency`'s own help text names
    the old-basis revision explicitly, ties its requirement to
    `--data-process-count-old-basis` being 1 or more, and limits the
    `unknown`-on-omission claim to that same condition."""
    help_text = _inventory_argument_help(ops._build_parser(), "concurrency")
    assert help_text == (
        "the OLD-basis revision's own declared MITATEDB_MAX_CONCURRENCY value (a positive "
        "integer) -- meaningful, and required, only while --data-process-count-old-basis "
        "declares 1 or more processes still on the old basis (omitting it there leaves item "
        "(8) unknown); must itself be omitted when --data-process-count-old-basis is 0"
    )


# ---------------------------------------------------------------------------
# R-55 work order section 1: the same instruction in `ops.py`'s own text.
# ---------------------------------------------------------------------------

#: the one production instruction -- confirmed in R-53 for the help text
#: and in R-55 (work order section 1.2) for the two source-text places.
CONFIRMED_PRODUCTION_SENTENCE = (
    "Against production, run it only through the runbook's gated procedure "
    "(docs/cloud-run-cloud-sql.md section 10)."
)

#: preconditions the two source-text places used to restate. They are
#: still in force -- section 10.10 of the runbook names them -- so the
#: code names section 10 instead of repeating a subset of them here;
#: R-53 had already put the help text in that same form.
RESTATED_PRECONDITION_PHRASES = ("isolated proof", "requester approval")

_RUNBOOK_SECTION_RE = re.compile(r"docs/cloud-run-cloud-sql\.md section (\d+)")

_SECTION_HEADING_FIRST_LINE = (
    "# `apply-platform-migration` -- applies a run of one or more"
)


def _ops_source() -> str:
    """`ops.py`'s own file body -- deliberately the text on disk, not
    `inspect.getsource`, so that a `#` comment (which never reaches any
    runtime object) is inside what these tests observe."""
    return Path(ops.__file__).read_text(encoding="utf-8")


def _flatten_prose(text: str) -> str:
    """One line of prose out of a wrapped comment block or docstring:
    each line loses a leading `#` and its surrounding whitespace, and
    what is left is joined on single spaces, so a sentence a line wrap
    splits is still one contiguous string."""
    parts = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            stripped = stripped[1:].strip()
        parts.append(stripped)
    return " ".join(" ".join(parts).split())


def _apply_platform_migration_section_comment(source: str) -> str:
    """The `# ===`-ruled section-heading comment block that introduces
    the `apply-platform-migration` family, taken as the maximal run of
    `#` lines around its own first content line."""
    lines = source.splitlines()
    index = next(
        i for i, line in enumerate(lines) if line.startswith(_SECTION_HEADING_FIRST_LINE)
    )
    start, end = index, index + 1
    while start > 0 and lines[start - 1].startswith("#"):
        start -= 1
    while end < len(lines) and lines[end].startswith("#"):
        end += 1
    return "\n".join(lines[start:end])


def _cmd_apply_platform_migration_docstring(source: str) -> str:
    """`cmd_apply_platform_migration`'s docstring, read out of the file
    body via `ast` rather than off the imported function object."""
    module = ast.parse(source)
    node = next(
        n for n in module.body
        if isinstance(n, ast.FunctionDef) and n.name == "cmd_apply_platform_migration"
    )
    return inspect.cleandoc(ast.get_docstring(node, clean=False))


def test_ops_source_no_longer_restates_the_runbook_preconditions():
    """R-55 completion condition 1: `ops.py`'s own file body restates
    none of the runbook's preconditions any more, and the observation
    target is non-empty -- the confirmed sentence is present at least
    twice (the section-heading comment and the docstring). The phrases
    are looked for in the FLATTENED body, never the raw text.
    """
    source = _ops_source()
    flattened = _flatten_prose(source)
    assert flattened.count(CONFIRMED_PRODUCTION_SENTENCE) >= 2
    for phrase in RESTATED_PRECONDITION_PHRASES:
        assert phrase not in flattened


def test_section_comment_and_docstring_carry_the_confirmed_production_sentence():
    """R-55 completion condition 2 (first half): the section-heading
    comment and `cmd_apply_platform_migration`'s docstring each carry
    the confirmed sentence, once whitespace and the comment's own `# `
    prefixes are normalized away."""
    source = _ops_source()
    places = {
        "section-heading comment": _flatten_prose(
            _apply_platform_migration_section_comment(source)
        ),
        "cmd_apply_platform_migration docstring": _flatten_prose(
            _cmd_apply_platform_migration_docstring(source)
        ),
    }
    for name, flattened in places.items():
        assert flattened, name
        assert CONFIRMED_PRODUCTION_SENTENCE in flattened, name
        for phrase in RESTATED_PRECONDITION_PHRASES:
            assert phrase not in flattened, name


def test_help_comment_and_docstring_name_one_and_the_same_runbook_section():
    """R-55 completion condition 2 (second half): the help text (R-53),
    the section-heading comment and the docstring are one instruction --
    all three name the runbook, each exactly once, and all three name
    the same section of it."""
    source = _ops_source()
    places = {
        "help": _apply_platform_migration_help(ops._build_parser()),
        "section-heading comment": _flatten_prose(
            _apply_platform_migration_section_comment(source)
        ),
        "cmd_apply_platform_migration docstring": _flatten_prose(
            _cmd_apply_platform_migration_docstring(source)
        ),
    }
    sections = {name: _RUNBOOK_SECTION_RE.findall(text) for name, text in places.items()}
    assert all(len(found) == 1 for found in sections.values()), sections
    assert {found[0] for found in sections.values()} == {"10"}, sections
