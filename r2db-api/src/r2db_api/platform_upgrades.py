"""Q4 phase WP-3 (design docs/design/Q4_DB_SIDE_SINGLE_TRUTH_V1.md D-3(f),
work order docs/work-orders/WORK_ORDER_Q4_DB_SIDE_SINGLE_TRUTH_V1.md WP-3;
surface pinned by supervisor ruling 2026-09-05,
design docs/design/Q4_DB_SIDE_SINGLE_TRUTH_V1.md §5 U-1 / U-2, §3.8 F-12):

The per-application platform-upgrade LEDGER this package's own package
constant (`PLATFORM_UPGRADE_NUMBERS`) is checked against -- the "pending =
{package numbers} - {ledger numbers}" set-difference calculation the cell
open time check (`postgres.PostgresCell.verify_platform_upgrades_applied`)
and `ops upgrade-applications`/`ops upgrade-status` (design D-4/D-5) both
consume, plus the F-12 message (design §3.8) the cell open time check
raises verbatim.

Peer-local names/signatures (supervisor ruling 2026-09-05): `PLATFORM_
UPGRADE_NUMBERS`, `LEDGER_TABLE_NAME`, `UPGRADE_SCRIPT_VARIABLE`, and
`PEER_MODULE` are peer-specific VALUES (r2db `_r2db_platform_upgrades`/
`app_slug`/`{9}`, MitateDB `_mdb_platform_upgrades`/`app_id`/`{6, 8}`) --
never placed on the cross-peer isomorphism table (`_ISOMORPHIC_TARGETS`,
`tests/test_audit_query.py`). Every OTHER symbol below (`PlatformUpgradeError`,
`discover_upgrade_scripts`, `read_applied_upgrade_numbers`, `pending_
upgrade_numbers`, `require_application_upgrades_applied`, `_f12_message`,
`summarize_upgrade_run`, `ApplicationUpgradeResult`) is a same-name/same-
signature symbol MitateDB-api's own WP-4 realization will carry too -- WP-4
adds the corresponding `_ISOMORPHIC_TARGETS` rows for both WPs at once
(work order §3: "対応表への行追加は「対」の後半WPのみが行う"); this WP does
not touch that table.

Design D-3(f)/U-2 (requester ruling 2026-09-05): "未適用 = {パッケージ定数の
番号集合} - {台帳の番号集合}" is a SET difference, never a "greater than the
ledger's own max recorded number" comparison -- the latter can never detect
a HOLE (a ledger `{10}` missing `9`), which the requester ruling names
explicitly as the reason v1.0's "max number" design was rejected (design
D-4(b)).

Fail-fast/fail-closed split, mirrored from `platform_declarations.py`'s own
header: `PlatformUpgradeError` is raised for one purpose only -- naming
pending platform upgrades to a cell's own caller (`postgres.PostgresCell.
verify_platform_upgrades_applied`), which maps it to the ONE user/API-facing
condition this whole phase introduces (F-12, `SERVICE_UNAVAILABLE`, design
§3.8's own header note: cell open time, not startup, and the only condition
of this whole Q4 phase visible in an HTTP response at all -- SI-10 forbids
this message from carrying a DSN, credential, internal hostname, or any
OTHER declared value; F-12's own message carries only the missing upgrade
numbers and the next `ops` command to run).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

import psycopg
from psycopg import sql

#: This peer's own module path, named in the F-12 message's "next ops
#: command" (design §3.8, same convention as `platform_declarations.
#: PEER_MODULE`). Peer-local (no cross-peer sharing, requester ruling
#: 2026-09-03) -- kept as this module's OWN constant rather than importing
#: `platform_declarations.PEER_MODULE` (identical value, but WP-3's own
#: module must not depend on WP-1's for a value this isomorphic-surface
#: ruling already classifies as "peer 固有").
PEER_MODULE = "r2db_api"

#: The per-application platform-upgrade ledger table this peer's `0003`
#: template and `0009` (and every future per-app upgrade script) create in
#: `public`, inside every application's own database (design D-3(a)).
LEDGER_TABLE_NAME = "_r2db_platform_upgrades"

#: The complete set of per-application upgrade numbers THIS SHIPPED VERSION
#: of r2db-api knows about (design D-3(f)/§8: r2db's own per-app upgrade
#: series had one member, `0009`, joined by Phase 9 WP-2a's `0010` -- the
#: R-2 field-constraints side table, reusing this exact mechanism per that
#: work order's own cited precedent, docs/design/PHASE9_CONTRACT_170_
#: DECLARATION_AND_VERIFICATION_V1.md §3 D-2 "根拠"). Kept in three-way
#: sync with (a) the `NNNN_..._upgrade.sql` scripts actually present under
#: `migrations/` and (b) `0003_provision_application.sql`'s own ledger
#: seed list -- `tests/test_platform_upgrade_ledger_scan.py::test_real_
#: migrations_three_way_match` (WP-0, its `xfail` removed in this same
#: WP-3 commit) closes the "forgot to bump this constant" gap
#: mechanically (design §10, U-2's own "代償" clause).
PLATFORM_UPGRADE_NUMBERS: frozenset[int] = frozenset({9, 10})

#: The psql `-v` variable name every r2db per-application upgrade script
#: (and `ops upgrade-applications`' own `psql` invocation) uses to pass the
#: target application's slug in (design §3.10's own peer-pair table: r2db
#: `app_slug`, MitateDB `app_id` -- r2db's existing `0003`/`0004` templates
#: already use this exact name).
UPGRADE_SCRIPT_VARIABLE = "app_slug"

_UPGRADE_SCRIPT_NAME_RE = re.compile(r"^(\d{4})_.*_upgrade\.sql$")


class PlatformUpgradeError(RuntimeError):
    """Raised by `require_application_upgrades_applied` when this
    application's own ledger is missing one or more per-application
    upgrades this package requires (design D-3(f)). The caller (`postgres.
    PostgresCell.verify_platform_upgrades_applied`) maps this to F-12 --
    `SERVICE_UNAVAILABLE` -- never lets it propagate as an internal
    exception."""


def discover_upgrade_scripts(migrations_dir: Path) -> dict[int, Path]:
    """Design D-3(d)/§8.1: every file directly under `migrations_dir` whose
    name matches the per-application upgrade naming convention (`NNNN_
    <name>_upgrade.sql`), keyed by its own de-zero-padded number. A pure
    function of the directory's current contents -- callers needing the
    on-disk migrations directory (`ops upgrade-applications`) resolve that
    path themselves and pass it in; this function never guesses a location
    of its own."""
    discovered: dict[int, Path] = {}
    for path in sorted(migrations_dir.glob("*.sql")):
        match = _UPGRADE_SCRIPT_NAME_RE.match(path.name)
        if match is not None:
            discovered[int(match.group(1))] = path
    return discovered


def read_applied_upgrade_numbers(conn: "psycopg.Connection", *, ledger_table_name: str) -> Optional[frozenset[int]]:
    """The set of `upgrade_number` values currently recorded in this
    application's own ledger (`public.<ledger_table_name>`), read on
    `conn` (an already-open connection to that application's own database
    -- this function never opens or closes one itself, mirroring `platform_
    declarations.read_platform_declarations`'s own `conn`-not-`dsn`
    convention).

    Returns `None` -- never an empty set -- when the ledger table itself
    does not exist yet (a `UndefinedTable` from PostgreSQL, caught here):
    design D-3(f) treats "no ledger table at all" as a DISTINCT state from
    "ledger table exists but is empty" only insofar as `pending_upgrade_
    numbers` below folds both into "every known number is pending" -- but
    callers that care about the distinction (e.g. `ops upgrade-status`'s
    own `applied = []` for a never-provisioned-with-a-ledger application)
    can still tell them apart from this return value alone. Any OTHER
    `psycopg.Error` propagates uncaught -- this function does not treat a
    real connectivity/permission failure as "no ledger".

    `conn`'s own transaction is rolled back before returning on the
    `UndefinedTable` path: PostgreSQL marks a transaction as aborted the
    instant one of its statements fails server-side, whether or not the
    Python exception that statement raised was caught -- leaving `conn`
    usable for whatever the caller runs next (mirrors `ops.py`'s own
    `cmd_show_declarations` UndefinedTable handling).
    """
    try:
        with conn.cursor() as cur:
            cur.execute(sql.SQL("SELECT upgrade_number FROM public.{}").format(sql.Identifier(ledger_table_name)))
            return frozenset(row[0] for row in cur.fetchall())
    except psycopg.errors.UndefinedTable:
        conn.rollback()
        return None


def pending_upgrade_numbers(applied: Optional[frozenset[int]], available: frozenset[int]) -> tuple[int, ...]:
    """Pure function (design D-3(f)/D-4(b)): the SET DIFFERENCE `available -
    applied`, ascending -- never a "greater than the ledger's own max"
    comparison, which cannot detect a hole (requester ruling 2026-09-05,
    U-2: "v1.0の『台帳の最大番号より大きい』は誤り"). `applied is None` (no
    ledger table at all, `read_applied_upgrade_numbers`'s own sentinel)
    means every number in `available` is pending."""
    if applied is None:
        return tuple(sorted(available))
    return tuple(sorted(available - applied))


def _f12_message(*, application_id: str, pending: Sequence[int], ops_module: str) -> str:
    """Design §3.8 F-12, verbatim (`<peer>` -> `ops_module`, `<未適用の
    番号…>` -> a comma-joined ascending list). `application_id` is part of
    this function's own pinned signature (supervisor ruling 2026-09-05,
    design docs/design/Q4_DB_SIDE_SINGLE_TRUTH_V1.md §5 U-1 / U-2, §3.8
    F-12) but, per the verbatim design text itself, is NOT interpolated
    into the message body -- F-12 is the
    one condition of this whole phase visible in an HTTP response (SI-10),
    and the design's own message intentionally names no application
    identifier, DSN, credential, internal hostname, or declared value."""
    numbers = ", ".join(str(n) for n in pending)
    return (
        f"This application's storage is missing platform upgrade(s) {numbers}: the deployment must apply them "
        f"before this application can serve requests. Run 'python -m {ops_module}.ops upgrade-applications' "
        f"(its '--dry-run' shows applied and pending per application), then retry."
    )


def require_application_upgrades_applied(
    conn: "psycopg.Connection", *, ledger_table_name: str, expected: frozenset[int], application_id: str, ops_module: str,
) -> None:
    """Design D-3(f)/§3.7 data-plane step 10 -- the cell open time check
    (U-2): raises `PlatformUpgradeError` (F-12's own text) if this
    application's own ledger is missing any number in `expected`; does
    nothing otherwise. `conn` must already be open against THIS
    application's own database (the runtime role's own `SELECT`, U-2 --
    the caller, `postgres.PostgresCell.verify_platform_upgrades_applied`,
    supplies its own runtime pool connection)."""
    applied = read_applied_upgrade_numbers(conn, ledger_table_name=ledger_table_name)
    pending = pending_upgrade_numbers(applied, expected)
    if pending:
        raise PlatformUpgradeError(_f12_message(application_id=application_id, pending=pending, ops_module=ops_module))


@dataclass(frozen=True)
class ApplicationUpgradeResult:
    """One application's own outcome from one `ops upgrade-applications`
    run (design D-4(d)'s own per-application output line) -- also reused,
    with every list empty except `pending_after`, by `ops upgrade-status`.
    `database_name` is `None` for a registry row that has never completed
    provisioning -- the DEFAULT (no `--application`) enumeration excludes
    these rows entirely before this dataclass is ever built, but an
    explicit `--application <id>` naming such a row DOES construct one
    (M-1, supervisor ruling 2026-09-05, 差し戻し後 delta 監査):
    `applied_before`/`applied_after` are both `()`, `pending_after` is
    every number this package requires, and `failed` carries that same
    full set for a real (non-dry-run) invocation -- `()` only under
    `--dry-run`, which never attempts anything. `cmd_upgrade_applications`
    prints one line of this per application, and `summarize_upgrade_run`
    below reduces the whole run to a single exit code."""

    application_id: str
    database_name: Optional[str]
    applied_before: tuple[int, ...]
    applied_after: tuple[int, ...]
    pending_after: tuple[int, ...]
    failed: tuple[int, ...]
    skipped: tuple[int, ...]
    cleanup_sql: Optional[str]
    failure_detail: Optional[str] = None


def summarize_upgrade_run(results: Sequence[ApplicationUpgradeResult], *, dry_run: bool) -> int:
    """Pure function (design D-4(e)): the exit code `ops upgrade-
    applications` returns for a completed run (never a use error or an
    enumeration failure -- both of those are raised, not returned, by the
    caller, before this function is ever reached).

        0  every application's own `pending_after` is empty (`--dry-run`
           included) and no application failed
        3  at least one application's own `failed` is non-empty (never
           returned when `dry_run` is true -- a dry run applies nothing,
           so nothing can fail)
        4  `dry_run` is true and at least one application's own `pending_
           after` is non-empty
    """
    if dry_run:
        return 4 if any(result.pending_after for result in results) else 0
    return 3 if any(result.failed for result in results) else 0
