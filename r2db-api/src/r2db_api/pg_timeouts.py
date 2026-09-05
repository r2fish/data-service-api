"""Q4 phase WP-0 (design docs/design/Q4_DB_SIDE_SINGLE_TRUTH_V1.md D-1
(b)(ii), work order docs/work-orders/WORK_ORDER_Q4_DB_SIDE_SINGLE_TRUTH_
V1.md §4 WP-0 変更対象 A; supervisor ruling 2026-09-05): normalizes a
PostgreSQL GUC's textual rendering (as returned by `SHOW <setting>`, or as
stored verbatim in `pg_db_role_setting.setconfig`'s `key=value` entries)
to milliseconds, so a caller can compare two timeout values numerically
without ever comparing the raw unit-dependent strings PostgreSQL renders
them as -- `SHOW statement_timeout` renders `5000ms` as `5s` (whichever
unit divides the value evenly), so a bare string comparison between a
declared value and an effective value would go wrong whenever the two
happen to be written in different (but numerically equal) units.

Promoted here from three independent per-peer test-file copies (design
D-1 (b)(ii); the verbatim source was `MitateDB-api/tests/
test_application_audit.py`'s own `_ms_from_pg_timeout_text`, duplicated a
second time in `r2db-api/tests/
test_conformance_adapter_r2db_http_audit_writer_timeouts.py`, and
imported a third time by `MitateDB-api/tests/
test_conformance_adapter_mitatedb_http_audit_writer_timeouts.py`) so that
Q4 WP-1/WP-2's own startup-time double-check (design D-1 (b)(ii): the
declared `pg_db_role_setting` value vs. the writer connection's own
effective `pg_settings` value) can share this SAME normalization on both
sides, in product code, not test scaffolding. Placement and name fixed
by supervisor ruling 2026-09-05 (no implementer discretion): this module,
this function name (no leading underscore, unlike the test-file copies it
replaces).

Unit set (rework round, supervisor ruling 2026-09-05, work order §4 WP-0
差し戻し指示 3 / 裁定 B): PostgreSQL's OWN accepted unit set for this GUC
class -- verbatim from PostgreSQL 16's own HINT text on an invalid unit,
`Valid units for this parameter are "us", "ms", "s", "min", "h", and
"d".` -- plus unitless (= ms). The FIRST implementation of this module (in
the same WP, before this rework) omitted `us` entirely and could not
parse a fractional value handed to the `ms` branch (`'1.5ms'` raised
`ValueError`, since that branch called bare `int()` on the digits before
the suffix instead of going through the same float/Decimal scaling path
every other unit already used) -- code review round 1 (Opus, work order
§4 WP-0 レビューが必ず探すべき点) caught both.

Fractional values are accepted for every unit (PostgreSQL itself accepts
a fractional multiplier, e.g. `ALTER ROLE ... SET statement_timeout =
'1.5s'`), then scaled to milliseconds and rounded HALF-TO-EVEN (matching
PostgreSQL's own internal `rint()`-based rounding when it converts a GUC
value to its base unit) rather than truncated -- truncation would have
silently rounded `'1.5ms'` down to `1`, discarding a real half-millisecond
that could tip a subsequent numeric-equality comparison the wrong way.
Measured (pure-function, no PG connection; see test_pg_timeouts.py):
`'1.5ms'` -> `2`, `'0.0015s'` -> `2`, `'5000us'` -> `5`.

Peer-local, independently maintained (not shared/imported across peers,
per the requester's no-cross-peer-code-sharing ruling 2026-09-03) --
pinned identical to MitateDB-api's own copy of this same module by the
`_ISOMORPHIC_TARGETS` table in each peer's own
`tests/test_audit_query.py`.
"""
from __future__ import annotations

import re
from decimal import ROUND_HALF_EVEN, Decimal

# PostgreSQL 16's own accepted unit set for this GUC class (verbatim HINT
# text, design D-1 (b)(ii), supervisor ruling 2026-09-05): "us", "ms",
# "s", "min", "h", and "d". Values are each unit's own millisecond
# multiplier, expressed as `Decimal` (never `float`) so that scaling a
# textual, decimal-literal input (`'0.0015s'`) can never pick up binary
# floating-point representation error before the half-to-even rounding
# step below.
_UNIT_MULTIPLIER_MS: dict[str, Decimal] = {
    "us": Decimal("0.001"),
    "ms": Decimal(1),
    "s": Decimal(1_000),
    "min": Decimal(60_000),
    "h": Decimal(3_600_000),
    "d": Decimal(86_400_000),
}

# Longest units first so the alternation cannot short-circuit on a
# prefix of a longer unit; anchored at both ends (`^...$`) so this is
# purely defensive, not load-bearing (a non-anchored match would already
# require the FULL remaining text to be consumed by an alternative, since
# there is nothing else in the pattern after the unit group -- but
# ordering longest-first documents the intent instead of relying on that
# incidental anchoring behavior alone).
_PATTERN = re.compile(r"^([+-]?\d+(?:\.\d+)?)\s*(min|us|ms|h|d|s)?$")


def ms_from_pg_timeout_text(text: str) -> int:
    """Parses one PostgreSQL timeout GUC's textual rendering into whole
    milliseconds. `text` is either a `SHOW <setting>` result (e.g. `5s`,
    `4321ms`, `0`) or one `key=value` entry already split out of a
    `pg_db_role_setting.setconfig` array (whose values PostgreSQL stores
    VERBATIM, exactly as written by `ALTER ROLE ... SET`, never
    normalized to a canonical unit -- so this same parser handles both
    sources). `"0"` and `""` both mean 0 (PostgreSQL renders a disabled
    timeout as bare `0`, no unit suffix); every other unitless string is
    parsed as a (possibly fractional) number already in milliseconds.

    Accepts the unit set PostgreSQL itself accepts for this GUC class --
    `{us, ms, s, min, h, d}` -- plus unitless (= ms); a fractional
    quantity is accepted for every unit (`'1.5s'`, `'0.0015s'`), scaled to
    milliseconds via `Decimal` (never `float`, to avoid binary
    floating-point representation error on a decimal-literal input), then
    rounded HALF-TO-EVEN to a whole millisecond count -- matching
    PostgreSQL's own internal `rint()`-based rounding, never truncated.
    Raises `ValueError` for anything else (an unrecognized unit, garbage
    text, scientific notation) -- this repository's own callers only ever
    hand this function a `SHOW`/`pg_settings`/`pg_db_role_setting`
    rendering, so an unparseable value means something upstream is
    already broken and should fail loudly, not silently coerce to 0."""
    text = text.strip()
    if text in ("0", ""):
        return 0
    match = _PATTERN.match(text)
    if match is None:
        raise ValueError(f"not a recognized PostgreSQL timeout GUC rendering: {text!r}")
    number_text, unit = match.groups()
    multiplier = _UNIT_MULTIPLIER_MS[unit] if unit else Decimal(1)
    scaled_ms = Decimal(number_text) * multiplier
    return int(scaled_ms.to_integral_value(rounding=ROUND_HALF_EVEN))
