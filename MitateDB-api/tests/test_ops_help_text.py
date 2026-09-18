"""`ops.py` `_build_parser` -- help text for `apply-platform-migration`
and the two `--data-process-count-total`/`--control-process-count-total`
`inventory` arguments (R-53 work order section 1).

Covers: the platform-migration subcommand's own help enumerates its
accepted filenames by deriving them from `_PLATFORM_MIGRATION_FILENAMES`
itself (never a hardcoded digit string), never mentions "work package",
and carries the confirmed replacement sentence pointing at the runbook's
gated procedure; the two process-count-total arguments each carry their
own confirmed WORST-CASE wording and never claim to report the count
"actually running".
"""
from __future__ import annotations

import argparse

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
