"""Q4 phase WP-0 (design docs/design/Q4_DB_SIDE_SINGLE_TRUTH_V1.md D-1
(b)(ii), work order §4 WP-0 完了条件 1/2): `r2db_api.pg_timeouts.
ms_from_pg_timeout_text`, promoted to `src` from three independent
per-peer test-file copies (see `pg_timeouts.py`'s own module docstring
for the full provenance). This file replaces the local copy that used to
live in `tests/test_conformance_adapter_r2db_http_audit_writer_timeouts.
py` -- that file now imports the same function from `src` instead of
defining its own (完了条件 2).

Non-vacuity (常設規律 1, work order §4 WP-0 非 vacuity 要件): each unit
gets its OWN parametrize case, never one case asserting every unit at
once -- a single combined assertion would not say WHICH unit broke.

Rework round (supervisor ruling 2026-09-05, 裁定 B / work order §4 WP-0
差し戻し指示 3): code review round 1 (Opus) found the first pass of this
module handled only `{ms, min, s}` plus unitless -- `h`/`d` were untested
above (only asserted in the transpose-guard test below) and `us` did not
exist yet -- and, separately, that the `ms` branch could not parse a
fractional value (`'1.5ms'` raised `ValueError`) while every OTHER unit's
branch already scaled via `float()`. The fractional/half-to-even cases
below are the review's own MEASURED expected values (pure-function, no PG
connection -- `ms_from_pg_timeout_text` never touches a socket), not
values assumed ahead of running them:
`'1.5ms' -> 2`, `'0.0015s' -> 2`, `'5000us' -> 5`.
"""
from __future__ import annotations

import pytest

from r2db_api.pg_timeouts import ms_from_pg_timeout_text


@pytest.mark.parametrize(
    ("text", "expected_ms"),
    [
        pytest.param("5000ms", 5000, id="ms"),
        pytest.param("5s", 5000, id="s"),
        pytest.param("5min", 300_000, id="min"),
        pytest.param("2h", 7_200_000, id="h"),
        pytest.param("1d", 86_400_000, id="d"),
        pytest.param("5000us", 5, id="us"),
        pytest.param("4321", 4321, id="unitless"),
    ],
)
def test_ms_from_pg_timeout_text_normalizes_each_unit_individually(text, expected_ms):
    assert ms_from_pg_timeout_text(text) == expected_ms


@pytest.mark.parametrize("text", ["0", ""])
def test_ms_from_pg_timeout_text_zero_and_empty_string_are_both_zero(text):
    """`SHOW statement_timeout` renders a disabled timeout as bare `0`,
    no unit suffix -- and PostgreSQL's own GUC machinery treats `0` as
    "unlimited" for these two settings (design D-1 (b)(i)), so this
    function must never mistake it for "unset"."""
    assert ms_from_pg_timeout_text(text) == 0


def test_ms_from_pg_timeout_text_h_and_d_do_not_transpose_digits():
    """Review point 2 (work order §4 WP-0 レビューが必ず探すべき点): `h` =
    3,600,000ms, `d` = 86,400,000ms -- distinct literal expectations so a
    transposed-digit mutation (e.g. 360,000 for `h`) is caught, not just
    "some large number"."""
    assert ms_from_pg_timeout_text("1h") == 3_600_000
    assert ms_from_pg_timeout_text("1d") == 86_400_000


def test_ms_from_pg_timeout_text_space_between_number_and_unit_is_a_regression_case():
    """裁定 B / レビュー再実施の回帰ケース: a rendering with a literal
    space between the number and its unit (`'5 s'`) must still parse --
    PostgreSQL itself never emits this form, but the probe that surfaced
    the `us`/fractional-`ms` gaps (`{scratchpad}/probe_ms.py`) exercised
    it too, and it must not silently regress while `_PATTERN` is being
    rewritten to add `us` and fractional support."""
    assert ms_from_pg_timeout_text("5 s") == 5000


@pytest.mark.parametrize(
    ("text", "expected_ms"),
    [
        pytest.param("1.5ms", 2, id="fractional-ms-rounds-half-to-even-up"),
        pytest.param("0.0015s", 2, id="fractional-s-scales-to-1.5ms-rounds-half-to-even-up"),
        pytest.param("2.5ms", 2, id="fractional-ms-rounds-half-to-even-down"),
    ],
)
def test_ms_from_pg_timeout_text_fractional_values_round_half_to_even(text, expected_ms):
    """裁定 B: fractional GUC values are accepted (PostgreSQL itself
    accepts a fractional multiplier) and rounded HALF-TO-EVEN after
    scaling to milliseconds, matching PostgreSQL's own internal `rint()`-
    based rounding, rather than truncated (which would have silently
    rounded `'1.5ms'` down to `1`). `1.5` and `2.5` are the two smallest
    values whose ordinary "round half up" and "round half to even"
    results DIFFER for `2.5` (up: 3, even: 2) while agreeing for `1.5`
    (both give 2) -- included together so a mutation to "round half up"
    is caught by the `2.5` case even though it would pass the `1.5` one."""
    assert ms_from_pg_timeout_text(text) == expected_ms
