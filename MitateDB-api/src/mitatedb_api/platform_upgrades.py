"""Q4 phase D-3/D-4/D-5 (docs/design/Q4_DB_SIDE_SINGLE_TRUTH_V1.md v1.3):
per-application platform-upgrade ledger (`public.<ledger table>`, one per
application database) and the pure helpers `ops upgrade-applications` /
`ops upgrade-status` and the cell-open-time check (F-12, D-3(f)) share.

Reference-implementation module (task brief; design docs/design/
Q4_DB_SIDE_SINGLE_TRUTH_V1.md §5 U-1 / U-2, §3.8 F-12): every name,
signature and body below is
shared verbatim with r2db-api's own same-named realization -- peer
differences close entirely over the ARGUMENTS a caller passes in
(`ledger_table_name`, `expected`, `application_id`, `ops_module`), never
over a literal `mitatedb`/`MITATEDB`/`r2db`/`R2DB` string baked into a
pinned function's own body. The four PEER-LOCAL constants below
(`LEDGER_TABLE_NAME`, `PLATFORM_UPGRADE_NUMBERS`, `UPGRADE_SCRIPT_
VARIABLE`, `PEER_MODULE`) are the exception -- peer-specific VALUES the
isomorphism table (`tests/test_audit_query.py::_ISOMORPHIC_TARGETS`)
does not pin (mirrors `platform_declarations.py`'s own `REMOVED_TIMEOUT_
ENV`/`REMOVED_SURFACE_ENV` treatment).

Fail-fast/fail-closed shape: every function here either returns a
validated value or raises `PlatformUpgradeError`. Unlike `platform_
declarations.PlatformDeclarationError` (a STARTUP-only failure, never
surfaced over HTTP), `PlatformUpgradeError` raised by `require_
application_upgrades_applied` IS surfaced -- at cell-open time, mapped by
the caller (`backend_postgres.PostgresBackend.__init__`) to `errors.
StorageConfigurationError`, which `http.py`'s own `_CLASSIFY_ORDER` maps
to the contract's `SERVICE_UNAVAILABLE` code (design §3.8: "F-12 だけは
起動時ではなく cell open 時であり、API 応答として利用者に届く"). The
message text (`_f12_message`) is therefore held to SI-10 -- no DSN,
credential, internal hostname, or declared value, only the missing
upgrade numbers and the next `ops` command to run.

Peer-local, independently maintained (no cross-peer sharing, requester
ruling 2026-09-03) -- the isomorphic helpers below are pinned isomorphic
to r2db-api's own same-named realizations by `_ISOMORPHIC_TARGETS`
(`tests/test_audit_query.py`).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

import psycopg
from psycopg import sql

#: This peer's own per-application ledger table name (design D-3(a)) --
#: created by `migrations/0003_provision_application.sql` (new
#: applications) and `migrations/0008_platform_upgrades_upgrade.sql`
#: (existing ones). Never the sibling peer's table name (`_r2db_platform_
#: upgrades`) -- excluded from the isomorphism table by design (peer-
#: specific VALUE, same treatment as `platform_declarations.
#: REMOVED_TIMEOUT_ENV`).
LEDGER_TABLE_NAME = "_mdb_platform_upgrades"

#: The complete set of per-application upgrade numbers THIS package's own
#: shipped migrations set requires every application database to carry
#: (design D-3(f), §8: MitateDB = {6, 8, 9} -- `0006_declared_field_types_
#: upgrade.sql` predates this WP's own ledger discipline, `0008_platform_
#: upgrades_upgrade.sql` is Q4 phase's own, `0009_field_constraints_
#: upgrade.sql` is Phase 9 WP-3a's own (design docs/design/
#: PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md D-2 (1)/(4)):
#: `enum_json`/`nullable` columns on `_mdb_field_types`). D-3(d)
#: regulation (d)'s three-way static check (`tests/test_platform_upgrade_
#: ledger_scan.py::test_real_migrations_three_way_match`) holds this set,
#: the real `migrations/*_upgrade.sql` file-number set, and `0003`'s own
#: seed list to the SAME set mechanically -- forgetting to add a new
#: number here when a new per-application upgrade script ships is caught
#: by CI, not left to operator discipline (design §9.4 step 5).
PLATFORM_UPGRADE_NUMBERS: frozenset[int] = frozenset({6, 8, 9})

#: The `psql -v` variable name this peer's own per-application upgrade
#: scripts (and `0003`/`0004`) take for the target application id --
#: `app_id` on MitateDB, `app_slug` on r2db-api (design §3.10). Excluded
#: from the isomorphism table (peer-specific VALUE).
UPGRADE_SCRIPT_VARIABLE = "app_id"

#: `<peer>` in the F-12 message's own "next ops command" (design §3.8),
#: matching `platform_declarations.PEER_MODULE`.
PEER_MODULE = "mitatedb_api"

_UPGRADE_SCRIPT_NAME_RE = re.compile(r"^(\d{4})_.*_upgrade\.sql$")


class PlatformUpgradeError(RuntimeError):
    """Raised by `require_application_upgrades_applied` when an
    application database's own ledger is missing one or more platform
    upgrades this package requires (F-12, design D-3(f)). The caller
    (`backend_postgres.PostgresBackend.__init__`, at cell-open time) maps
    this to `errors.StorageConfigurationError` -- this class itself is
    never mapped to a contract error code directly, and never raised at
    process-startup time (that is `platform_declarations.
    PlatformDeclarationError`'s own territory, a different failure
    class for a different moment, design §3.8's own F-1..F-11/F-13 vs.
    F-12 distinction)."""


def discover_upgrade_scripts(migrations_dir: Path) -> dict[int, Path]:
    """Design D-3(d)/§8.1: maps every file in `migrations_dir` matching
    the per-application-upgrade naming convention (`NNNN_<name>_
    upgrade.sql`) to its own de-zero-padded upgrade number. Pure/read-only
    (a directory listing, no SQL parsing) -- `ops upgrade-applications`
    uses this to resolve a pending number to the script file that applies
    it; the static ledger scanner (`tests/test_platform_upgrade_ledger_
    scan.py`) has its own, separately-pinned copy of the identical naming
    regex (`NAME_RE`) for its own, different purpose (classifying scripts
    into 適合/違反/免除/対象外, not resolving a number to a path) and is
    not this function's caller."""
    discovered: dict[int, Path] = {}
    for path in sorted(migrations_dir.glob("*.sql")):
        match = _UPGRADE_SCRIPT_NAME_RE.match(path.name)
        if match is not None:
            discovered[int(match.group(1))] = path
    return discovered


def read_applied_upgrade_numbers(conn: "psycopg.Connection", *, ledger_table_name: str) -> Optional[frozenset[int]]:
    """Design D-3(f): the set of upgrade numbers this application
    database's own ledger already records -- `None` if the ledger table
    itself does not exist yet (an application database provisioned before
    this WP's own per-application upgrade script has run, or a brand-new
    one whose `0003` template revision has not yet shipped), never an
    empty set for that case (an empty set would mean "the table exists
    and genuinely has zero rows", a different, real state `ON CONFLICT DO
    NOTHING` re-application could produce and this function must not
    conflate with "the table itself is absent"). Any OTHER `psycopg.Error`
    propagates uncaught -- only `UndefinedTable` is a recognized,
    expected absence."""
    try:
        with conn.cursor() as cur:
            cur.execute(sql.SQL("SELECT upgrade_number FROM public.{}").format(sql.Identifier(ledger_table_name)))
            return frozenset(row[0] for row in cur.fetchall())
    except psycopg.errors.UndefinedTable:
        conn.rollback()
        return None


def pending_upgrade_numbers(applied: Optional[frozenset[int]], available: frozenset[int]) -> tuple[int, ...]:
    """Design D-4(b): pure set difference, in ascending order -- `applied
    is None` (no ledger table at all) means every number in `available`
    is pending. NEVER a "largest applied number" comparison (design D-4(b)
    calls that v1.0 form an error: a ledger holding `{8}` with `6` missing
    must report `6` as pending forever, not only until some larger number
    is recorded)."""
    if applied is None:
        return tuple(sorted(available))
    return tuple(sorted(available - applied))


def _f12_message(*, application_id: str, pending: Sequence[int], ops_module: str) -> str:
    """Design §3.8 F-12, verbatim (design §5 U-2's own "明示メッセージ"
    instruction, requester ruling 2026-09-05). `application_id` is accepted
    (and validated by every caller before this point) but deliberately NOT
    interpolated into the message text below -- the verbatim design text
    names no per-application detail at all (the requesting principal
    already knows which application it authenticated against; SI-10 bars
    DSN/credential/internal-hostname/declared-value leakage, not an
    application id the caller already supplied, but the design's own F-12
    wording simply does not include one, and this function copies that
    wording verbatim rather than paraphrasing it)."""
    numbers = ", ".join(str(n) for n in pending)
    return (
        f"This application's storage is missing platform upgrade(s) {numbers}: the deployment must apply them "
        f"before this application can serve requests. Run 'python -m {ops_module}.ops upgrade-applications' "
        f"(its '--dry-run' shows applied and pending per application), then retry."
    )


def require_application_upgrades_applied(
    conn: "psycopg.Connection", *, ledger_table_name: str, expected: frozenset[int], application_id: str, ops_module: str,
) -> None:
    """Design D-3(f)/§3.7 data-plane steps 9-10, F-12: the cell-open-time
    check -- reads `conn`'s own application database ledger (the RUNTIME
    role's `SELECT`-only connection, design D-3(a)/U-2) and raises
    `PlatformUpgradeError` if any number in `expected` is not yet recorded
    there (a missing ledger table counts as every number pending, `read_
    applied_upgrade_numbers`'s own `None` case). Called once per
    application, at the point this package "opens" that application's own
    storage boundary (`backend_postgres.PostgresBackend.__init__`) --
    never at process startup (design §3.7's own explicit contrast: the
    ledger lives INSIDE the application database, which this process does
    not connect to until it serves that specific application)."""
    applied = read_applied_upgrade_numbers(conn, ledger_table_name=ledger_table_name)
    pending = pending_upgrade_numbers(applied, expected)
    if pending:
        raise PlatformUpgradeError(_f12_message(application_id=application_id, pending=pending, ops_module=ops_module))


@dataclass(frozen=True)
class ApplicationUpgradeResult:
    """One application's own outcome from one `ops upgrade-applications`
    run (design D-4(d)'s own per-application output line) -- also reused,
    with every list empty except `pending_after`, by `ops upgrade-status`
    (D-5: "`upgrade-applications --dry-run` はこれと同じ集計を出す").
    `database_name` is `None` for a registry row that has never completed
    provisioning -- the DEFAULT (no `--application`) enumeration excludes
    these rows entirely before this dataclass is ever built (D-4(a)), but
    an explicit `--application <id>` naming such a row DOES construct one
    (M-1/M-2(d), supervisor ruling 2026-09-05, 差し戻し後 delta 監査):
    `applied_before`/`applied_after` are both `()`, `pending_after` is
    every number this package requires, and `failed` carries that same
    full set for a real (non-dry-run) invocation -- `()` only under
    `--dry-run`, which never attempts anything."""
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
    """Design D-4(e)'s own two result-dependent exit codes (the other
    three -- 1 enumeration failure, 2 usage error -- are raised before any
    `ApplicationUpgradeResult` exists, so this function never produces
    them): `dry_run=True` returns 4 if any application still has a
    pending upgrade, else 0; `dry_run=False` returns 3 if any application
    failed to apply at least one upgrade, else 0. Pure function -- no I/O,
    no `sys.exit`, so the CLI's own `main()` -> `SystemExit` translation
    (or a test asserting the return value directly) is the caller's own
    concern."""
    if dry_run:
        return 4 if any(result.pending_after for result in results) else 0
    return 3 if any(result.failed for result in results) else 0


__all__ = [
    "LEDGER_TABLE_NAME",
    "PEER_MODULE",
    "PLATFORM_UPGRADE_NUMBERS",
    "UPGRADE_SCRIPT_VARIABLE",
    "ApplicationUpgradeResult",
    "PlatformUpgradeError",
    "discover_upgrade_scripts",
    "pending_upgrade_numbers",
    "read_applied_upgrade_numbers",
    "require_application_upgrades_applied",
    "summarize_upgrade_run",
]
