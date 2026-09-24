"""PostgreSQL storage backend (R-2/R-3).

R-2 choke point: values are always bound as psycopg parameters, never
string-interpolated into SQL text. Identifiers reach this module already
syntax-checked by the shared allowlist (``identifiers.validate_identifier``,
re-applied here defensively as this module's own first gate too -- cheap,
and keeps this file's own safety property self-contained rather than
depending entirely on the caller having done it) and, for every identifier
that names something ALREADY EXPECTED TO EXIST (a collection/field a
read/write/filter references), additionally checked against this
database's own live catalog by ``field_domains`` before it is ever used --
only *new* names (``create_collection``/``add_field``) skip that second
stage, for the obvious reason that a name being created cannot already be
in the catalog; PostgreSQL's own ``DuplicateTable``/``DuplicateColumn``
still catches a collision there. Every identifier is composed into a
statement exclusively via ``psycopg.sql.Identifier`` -- this module never
builds a statement by embedding a name into a plain Python string.

Execution itself is centralized in ``_execute``, the ONLY function in this
module allowed to call ``cursor.execute`` directly: it rejects (``TypeError``,
at runtime, not merely by convention) anything that is not already a
``psycopg.sql.SQL``/``psycopg.sql.Composed`` object -- a bare Python
``str`` in particular -- so no method anywhere in this file has a route to
execute raw, string-interpolated SQL even by future accident.

WP-1 independent review B-1 (blocker): a value whose Python-level SHAPE
was acceptable (`cell.ApplicationCell._normalize_value`'s own
str/int/float/bool/None/dict/list check) can still MISMATCH the declared
PostgreSQL column type it is bound against (e.g. a string bound to a
`BIGINT` column, or an out-of-range integer bound to one) -- PostgreSQL
then raises a driver-level error (`InvalidTextRepresentation`,
`NumericValueOutOfRange`, ...) that used to escape this module's own
`errors.FoundationError` boundary entirely, AND left the connection in
PostgreSQL's own aborted-transaction state (every subsequent statement on
that connection failing with `InFailedSqlTransaction` until an explicit
`ROLLBACK`) because only the narrower `UniqueViolation`/`UndefinedTable`
handlers called `rollback()`. Fixed with two independent layers, per the
review's own two-layer split:

(i) ``field_domains`` reports each column's own DOMAIN category (`"text"`/
`"int32"`/`"int64"`/`"float"`, derived from this backend's own `_TYPES`
mapping via a live `information_schema.columns.data_type` query -- the
SAME live-catalog query `field_domains` already performs for stage-2
identifier validation, now also answering "what domain does this column
accept" in the same round trip). `encode_value(value, domain=...)`
deterministically rejects a value outside its target column's domain
BEFORE any statement reaches the database -- the SQLite backend's own
`encode_value` ignores `domain` entirely (matching WP-1 P3 round 2
instruction #1's own precedent: SQLite's more permissive behavior for the
embedded-NUL case stays UNCHANGED here too; SQLite's column affinity is
dynamic, so there is no equivalent mismatch to detect there).

(ii) every DML/DDL method below now has a FINAL, catch-all
``except psycopg.Error`` (after any more specific handler) that always
calls the correct connection's own `rollback()` before re-raising a
classified `errors.ValidationError` -- so a genuinely unanticipated
PostgreSQL-level rejection (anything layer (i) did not already catch)
still (a) never leaves a connection aborted for the next call on the same
cell, and (b) never leaks a raw `psycopg.Error` past this module's own
boundary. This is a deliberately conservative, defensive backstop, not a
precise error classification -- by the time layer (i) is in place, this
branch should be effectively unreachable for realistic client input; it
exists only so an unanticipated case still fails safely (connection
recovers, caller gets a classified exception) rather than poisoning the
connection for every future call.

This is not a port of r2db-api's own ``postgres.py`` (R-2's closing
paragraph: "the peer implementations are never shared" -- two independent
implementations of the same safety property is what gives the common
conformance suite its own detection power). Notable, deliberate
differences from that peer's own design: no pooling (this foundation
serializes every operation through ``cell.ApplicationCell``'s own lock
already, so a single persistent connection per role is sufficient for this
WP; connection pooling/limits are future-work, design v1.1 §7), no row
addressability (``row_addressability`` stays declared ``unavailable`` --
see ``insert``'s own docstring for why its ``rowid`` return value uses
PostgreSQL's ``ctid`` rather than a stable published address), and no Row
Level Security (this foundation's primary isolation wall is
database-per-application, R-1 -- RLS as an additional layer is future-work,
design v1.1 §7, not this WP's own containment boundary).
"""

import functools
import json
import time

import psycopg
from psycopg import sql
from psycopg.pq import TransactionStatus

from .backend import UNCHANGED
from .config import FoundationConfig
from .errors import (AuditSinkUnavailable, ConflictError, NotFoundError,
                     PlatformUpgradePending, ResourceLimitError,
                     StorageConfigurationError, ValidationError, violation)
from .identifiers import validate_identifier
from .field_types import FOUNDATION_TYPE_TO_CONTRACT_TYPE as _FOUNDATION_TYPE_TO_CONTRACT_TYPE
from . import platform_upgrades
# R-79 (WO §2.1 D-1/D-2): the counting cursor/connection subclasses
# `__init__` (below) uses instead of plain `psycopg.connect`, and the
# `pg_prepared_statements` probe `prepared_stats` (below) calls -- all
# byte-identical to `r2db_api.psycopg_counting` (a same-named test in
# `tests/` pins the sha256 match; rework 指摘 3 moved the
# probe itself there so it is not duplicated per peer).
from .psycopg_counting import CountingConnection, prepared_stats_skeleton, probe_prepared_statements
# `_INT_DOMAIN_RANGES`/`_check_domain` are re-exported for facade
# compatibility (design D-2); not referenced elsewhere in this module.
from .postgres_value_domain import _INT_DOMAIN_RANGES, _validate_value_domain, _check_domain
from .postgres_reserved_names import _RESERVED_EXACT, _RESERVED_PREFIX, _check_reserved_name
from .postgres_types import _TYPE_SQL, _DOMAIN_BY_DATA_TYPE, _TEXT_DOMAIN_BY_DECLARED_TYPE
from .postgres_sql import _DIRECTION_SQL, _where_sql


def _guard_pending_platform_upgrades(method):
    """Q4 rework (supervisor ruling 2026-09-05, H-1(a)): decorates every
    `PostgresBackend` method below that touches THIS application's own
    storage. `PostgresBackend.__init__` no longer raises when this
    application's own platform-upgrade ledger is missing an entry --  it
    stores the F-12 message on `self._pending_platform_upgrade_message`
    instead (`None` when nothing is pending) so `main.py::build_app`'s
    own eager per-application construction loop completes and every
    OTHER served application's cell opens normally. This decorator is
    the single place the deferred `errors.PlatformUpgradePending` (F-12)
    actually gets raised -- at the moment a real request against THIS
    specific, refusing cell reaches its backend, never earlier. Raises
    the dedicated `PlatformUpgradePending` subclass (never the bare
    `StorageConfigurationError`) so `http.py::_problem_for_exception`'s
    own `isinstance` narrowing can let JUST this one message reach the
    HTTP response verbatim (design §3.8: "F-12だけは...API応答として
    利用者に届く") without changing what every OTHER `StorageConfig
    urationError` site in this file surfaces on the wire."""
    @functools.wraps(method)
    def _wrapped(self, *args, **kwargs):
        if self._pending_platform_upgrade_message is not None:
            raise PlatformUpgradePending(self._pending_platform_upgrade_message)
        return method(self, *args, **kwargs)
    return _wrapped


# Bookkeeping table name (provisioned by `migrations/0003_provision_
# application.sql`, mirroring r2db-api's own `_r2db_schema_revision`
# table -- an independently-designed table of the same SHAPE, not shared
# code, matching R-2's own "no code sharing between peers" principle
# applied here to the migrations set instead).
#
# m-1 (independent review correction): this table is NOT excluded from
# `field_domains`'s own visible catalog by any special-case filter in this
# module (unlike r2db-api's own `_r2db_schema_revision` exclusion, which
# IS filtered out of that peer's catalog view) -- an application-level
# `field_domains("_mdb_schema_revision")` call would in fact return its
# real columns if one were ever issued. The REAL defenses that keep it
# unreachable from application code are two independent, structural ones:
# (a) `identifiers._IDENTIFIER` requires a name to start with `[a-z]`, so
# the leading underscore alone makes `"_mdb_schema_revision"` fail the
# SHARED syntax allowlist before this module is ever consulted (`cell.py`'s
# own `_identifier` gate), and (b) even if that gate were bypassed, the
# runtime role this backend's own `_runtime` connection authenticates as
# has NO grant of any kind on this table (`migrations/0003_provision_
# application.sql` creates it BEFORE the `ALTER DEFAULT PRIVILEGES`
# statement runs, so that statement's future-tables grant never reaches
# it) -- `tests/test_postgres.py`'s own dedicated tests exercise both of
# these directly.
_SCHEMA_REVISION_TABLE = "_mdb_schema_revision"

# Phase 6 WP-3 (design D-3, §1.5 finding 2a): the declared-type registry
# itself -- provisioned by `migrations/0003_provision_application.sql`
# for a new application, retrofitted onto an existing one by
# `migrations/0006_declared_field_types_upgrade.sql`. Same access-pattern
# reasoning as `_SCHEMA_REVISION_TABLE` immediately above (developer-
# connection only; the runtime role gets no grant on it at all -- created
# before `ALTER DEFAULT PRIVILEGES` in both migrations).
_FIELD_TYPES_TABLE = "_mdb_field_types"

# Q4 phase (design docs/design/Q4_DB_SIDE_SINGLE_TRUTH_V1.md D-3(a)/(e)(i),
# work order docs/work-orders/WORK_ORDER_Q4_DB_SIDE_SINGLE_TRUTH_V1.md §4
# WP-4 変更対象 C): the per-application platform-upgrade ledger -- same
# access-pattern reasoning as `_SCHEMA_REVISION_TABLE`/`_FIELD_TYPES_TABLE`
# above for EXCLUSION purposes (`schema_count`'s own accounting must never
# count this bookkeeping table towards `FoundationConfig.max_schema_
# objects`, design D-3(e)(i): "放置すると全 application の schema_objects
# 会計が +1 ずれる"), but UNLIKE those two, the runtime role DOES hold a
# grant on it (`SELECT` only, design D-3(a)/U-2) -- read directly by
# `platform_upgrades.require_application_upgrades_applied` below, over the
# runtime connection, at cell-open time.
_PLATFORM_UPGRADES_TABLE = platform_upgrades.LEDGER_TABLE_NAME

# Phase 9 WP-3c (design D-5, 追補 2 S-a; 監督裁定集約 rulings-r5-r6.md
# I-1): the per-application idempotency-record side table -- provisioned
# by `migrations/0003_provision_application.sql` for a new application,
# retrofitted onto an existing one by `migrations/0010_idempotency_
# records_upgrade.sql`. UNLIKE `_SCHEMA_REVISION_TABLE`/`_FIELD_TYPES_
# TABLE` (developer-connection only) and LIKE `_PLATFORM_UPGRADES_TABLE`
# (runtime holds a real grant), this table is written from BOTH
# connections: `ApplicationCell.transact`'s own batch path writes it over
# `self._runtime` (the same connection the batch's own DML already runs
# on, so the record lands in the SAME transaction, I-1), while `create_
# collection`/`add_field`/`alter_field_constraints`'s own `idempotency_
# record` parameter writes it over `self._developer` (the same connection
# their own DDL already runs on) -- created AFTER `ALTER DEFAULT
# PRIVILEGES FOR ROLE developer_role` in `0003` (and granted explicitly in
# `0010`, for an existing application whose ledger predates this table),
# so the runtime role holds full DML (`SELECT`/`INSERT`/`UPDATE`/
# `DELETE`), not the read-only `SELECT` `_PLATFORM_UPGRADES_TABLE` grants
# it.
_IDEMPOTENCY_TABLE = "_mdb_idempotency"

# Ruling U-7 (`{scratchpad}/review2/frame.md` F-①, WP-6d): two-int
# `pg_advisory_lock(namespace, hashtext(key))` namespace for the
# PER-KEY idempotency lock -- see `idempotency_begin` below.
#
# Code-review fix F8 (Opus review 2): the rationale this comment
# carried before this fix was FALSE and is corrected here (the constant
# itself is unaffected). It claimed a namespace of 0 would land in the
# SAME lock space the single-bigint form `ops.py::_RITUAL_ADVISORY_
# LOCK_KEY` (761761761, a `pg_advisory_xact_lock`) uses, risking a
# collision between a bootstrap/reset ritual's lock and an idempotency-
# key lock. PostgreSQL actually keeps those two key spaces disjoint by
# construction, regardless of namespace value: the 1-argument
# `pg_advisory_[xact_]lock(bigint)` form and the 2-argument
# `pg_advisory_[xact_]lock(int, int)` form record different `objsubid`
# values in `pg_locks` (1 for the 1-argument form, 2 for the
# 2-argument form) -- so `pg_advisory_xact_lock(761761761)` and
# `pg_advisory_lock(0, 761761761)` are two DIFFERENT locks, never the
# same one, even though they would superficially "look like" the same
# 64-bit id under a naive `(namespace << 32 | hashtext(key))` encoding.
# This namespace constant is still a large, distinctive value, far from
# both `_RITUAL_ADVISORY_LOCK_KEY` and `_IDEMPOTENCY_COUNT_ADVISORY_
# LOCK_KEY` below -- kept for HUMAN legibility (so two DIFFERENT lock
# families never share a suspiciously similar-looking id in a
# `pg_locks` dump), not because a collision with the 1-argument form
# was ever actually possible.
_IDEMPOTENCY_KEY_LOCK_NAMESPACE = 76176100
# Ruling U-7: table-level (not per-key) advisory lock serializing
# `idempotency_reserve`'s COUNT-then-write across DIFFERENT keys (D-5
# (iii)) -- same family as `ops.py::_RITUAL_ADVISORY_LOCK_KEY` (a
# single, fixed 64-bit `pg_advisory_xact_lock` key), a DIFFERENT
# constant from it (that lock guards bootstrap/reset ritual ordering;
# this one guards `idempotency_entries` capacity accounting -- two
# independent serialization points that must never share one lock id).
_IDEMPOTENCY_COUNT_ADVISORY_LOCK_KEY = 761761762

# m-1 (independent review correction, extended Q4 phase WP-4; Phase 9
# WP-3c adds `_IDEMPOTENCY_TABLE`): the full set of this package's own
# bookkeeping table names `schema_count()` excludes from its
# `application`-level accounting -- a plain tuple, not a `frozenset`, so
# the SQL `NOT IN (%s, %s, %s, %s)` parameter list below stays in a
# fixed, readable order matching this declaration.
_BOOKKEEPING_TABLES = (_SCHEMA_REVISION_TABLE, _FIELD_TYPES_TABLE, _PLATFORM_UPGRADES_TABLE, _IDEMPOTENCY_TABLE)

# The internal row-order column every collection table carries (design
# docs/design/PHASE11_KEYSET_PAGING_V1.md D-2's own table). Not a
# bookkeeping TABLE (`_BOOKKEEPING_TABLES` above
# lists tables `schema_count()` excludes) -- this is a COLUMN every real
# collection table has, added here by `create_collection` below and by
# `migrations/0015_row_order_column_upgrade.sql` for a collection that
# predates this column. `GENERATED ALWAYS AS IDENTITY` so no INSERT path
# can ever supply its own value. `cell.ApplicationCell._visible_field_
# domains` is the only place that hides it from request-shape/catalog
# logic -- this backend's own `field_domains` reports it like any other
# physical column, unchanged.
_ROW_ORDER_COLUMN = "_mdb_row"


def _execute(cursor, statement, params=()):
    """R-2 choke point. The ONLY call to `cursor.execute` in this module."""
    if not isinstance(statement, (sql.SQL, sql.Composed)):
        raise TypeError(
            "PostgresBackend._execute refuses a %s; only psycopg.sql.SQL/"
            "Composed objects may reach the database (R-2 choke point)"
            % (type(statement).__name__,)
        )
    cursor.execute(statement, params)
    return cursor


class PostgresBackend:
    """Two persistent connections per application cell.

    `developer_conn` (this application's own PostgreSQL DEVELOPER role --
    schema owner, DDL authority) executes every schema-mutating and
    catalog-reading statement; `runtime_conn` (this application's own
    PostgreSQL RUNTIME role -- DML only, per R-1's provisioning grants)
    executes every data statement. This is R-1's own role separation
    enforced a second time, structurally, underneath this foundation's own
    application-level `_require_developer`/`_require_data` gates (`cell.
    py`): even a code defect that let a non-developer principal reach
    `create_collection` at the Python level would still hit PostgreSQL's
    own `InsufficientPrivilege` the moment it attempted DDL over
    `runtime_conn`, because this backend never even attempts DDL there.
    """

    def __init__(self, runtime_dsn, developer_dsn, *, application_id=None, max_execution_ms: int | None = None):
        self._runtime = CountingConnection.connect(runtime_dsn, autocommit=False)
        self._developer = CountingConnection.connect(developer_dsn, autocommit=False)
        # R-87: the constructed upper bound the developer-connection
        # catalog reads below (`schema_count`/`field_domains`/`field_
        # types`/`all_field_types`/`field_constraints`/`field_types_and_
        # constraints`/`all_field_constraints`/`schema_revision`) pass to
        # `self._set_timeouts` at the start of their own transaction,
        # unconditionally -- independent of any caller-supplied value
        # (a bare construction, e.g. this module's own test suite, gets
        # `FoundationConfig`'s class-attribute default, never an unbound
        # read). `None` keeps this the deployment's declared
        # `execution_ms` (`MITATEDB_MAX_EXECUTION_MS` via `FoundationConfig.
        # from_env`); an explicit value overrides it for tests/tooling.
        self._catalog_timeout_ms = (
            max_execution_ms if max_execution_ms is not None else FoundationConfig.max_execution_ms
        )
        # Q4 phase (design docs/design/Q4_DB_SIDE_SINGLE_TRUTH_V1.md D-3(f),
        # §3.7 data-plane steps 9-10, F-12; requester ruling 2026-09-05
        # U-2, reworked by supervisor ruling 2026-09-05 H-1(a)): "cell
        # open" for THIS peer -- the served set is static configuration
        # this WP applies eagerly at startup for every served application
        # (`main.py::build_app`'s own docstring), so there is no later,
        # per-request "first open" moment to hook instead -- IS the
        # moment this backend's own two persistent connections come into
        # existence, once per served application. `application_id=None`
        # (test/tooling callers that construct a bare `PostgresBackend`
        # with no application context at all, e.g. `tests/test_postgres.
        # py`'s own low-level catalog/RLS probes) skips this check
        # entirely -- those callers are not exercising a served
        # application's own storage boundary.
        #
        # H-1(a) rework: this constructor no longer RAISES when this
        # application's own ledger is missing an upgrade -- before this
        # rework, raising here out of `main.py::build_app`'s own eager
        # `for application_id in ids` loop took the WHOLE PROCESS down
        # the moment even ONE served application's ledger had a pending
        # upgrade, refusing every OTHER served application too (review
        # H-1). Instead this constructor stores the F-12 message on
        # `self._pending_platform_upgrade_message` (`None` when nothing
        # is pending); `build_app` still completes and every OTHER
        # served application's cell serves normally. Every public
        # storage-touching method below is decorated with `_guard_
        # pending_platform_upgrades`, which raises `errors.
        # StorageConfigurationError` (F-12) -- mapped by `http.py::
        # _CLASSIFY_ORDER` to the contract's `SERVICE_UNAVAILABLE` code
        # -- the moment a request actually reaches THIS application's
        # own refusing cell.
        self._pending_platform_upgrade_message = None
        if application_id is not None:
            try:
                try:
                    platform_upgrades.require_application_upgrades_applied(
                        self._runtime, ledger_table_name=platform_upgrades.LEDGER_TABLE_NAME,
                        expected=platform_upgrades.PLATFORM_UPGRADE_NUMBERS, application_id=application_id,
                        ops_module=platform_upgrades.PEER_MODULE,
                    )
                finally:
                    # `require_application_upgrades_applied` only ever
                    # reads (a `SELECT`, or nothing at all if `UndefinedTable`
                    # already rolled the runtime connection back itself) --
                    # this `rollback()` closes out that read-only
                    # transaction either way.
                    self._runtime.rollback()
            except platform_upgrades.PlatformUpgradeError as exc:
                # design §3.8 F-12: the ONLY platform-upgrade condition
                # that reaches an API response. H-1(a): the message is
                # HELD here, not raised -- both connections stay open (a
                # refusing cell is otherwise a normal, live cell; only
                # every storage-touching method on it refuses) so a
                # later `ops upgrade-applications` run followed by a
                # process restart is the only way this application's own
                # cell becomes a normal one again.
                self._pending_platform_upgrade_message = str(exc)

    def close(self):
        self._runtime.close()
        self._developer.close()

    def prepared_stats(self):
        """R-79 (WO §1.2 D-2, completion condition 9): probe both
        persistent connections this backend holds, labelled `runtime@
        <pid>`/`developer@<pid>` (`conn.info.backend_pid`, the same public
        attribute r2db-api's own pool-based `label` uses -- a re-connect
        shows up as the pid changing). Unlike r2db-api's pool, there is no
        queue to drain/refill here -- these two connections are held
        directly for this cell's whole lifetime, so there is nothing to
        return anywhere afterwards. `cell.py::ApplicationCell.prepared_
        stats()` is the caller, under `self._lock`.

        A probe that raises may leave its connection mid-transaction
        (aborted) -- if the failure happened after the probe's own SELECT
        but before its `commit()` (rework 指摘 5): rolled
        back here so this backend's own persistent connection is never
        left aborted for the NEXT real request on it (mutation M25 drops
        this rollback). This does lose whatever was prepared on that
        connection (F2), but a connection already stuck aborted from a
        probe failure is not a state worth preserving prepared statements
        over."""
        rows = []
        for role_name, conn in (("runtime", self._runtime), ("developer", self._developer)):
            label = f"{role_name}@{conn.info.backend_pid}"
            try:
                rows.append(probe_prepared_statements(conn, label))
            except Exception as exc:  # noqa: BLE001 -- reported as probed=False/error=<class name> (D-2, WO §6.1 H-4)
                if conn.info.transaction_status != TransactionStatus.IDLE:
                    conn.rollback()
                rows.append(prepared_stats_skeleton(conn, label, error=type(exc).__name__))
        return rows

    def check_reserved(self, value, label):
        # WP-3e rework T1 (追補2 M-1): the reserved-name half of the
        # identifier choke point `cell.ApplicationCell._identifier`
        # always applies together with `identifiers.validate_identifier`
        # (that module's own docstring names this exact pairing) -- not
        # a defence-in-depth backstop for a check the cell layer already
        # performs itself (this backend is the ONLY place PostgreSQL's
        # own `pg_`-prefixed reservations are known), so it carries the
        # same `identifier_syntax` vocabulary `validate_identifier`
        # itself uses, `field` = `label` (the same per-call-site request
        # position `_identifier` already passes to both stages).
        _check_reserved_name(value, label)

    # ------------------------------------------------------------------
    # catalog (developer connection -- schema owner)
    # ------------------------------------------------------------------
    @_guard_pending_platform_upgrades
    def schema_count(self):
        try:
            with self._developer.cursor() as cur:
                self._set_timeouts(cur, self._catalog_timeout_ms)
                _execute(cur, sql.SQL(
                    "SELECT count(*) FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_name NOT IN (%s, %s, %s, %s)"
                ), list(_BOOKKEEPING_TABLES))
                count = cur.fetchone()[0]
        except (psycopg.errors.QueryCanceled, psycopg.errors.LockNotAvailable):
            self._developer.rollback()
            raise ResourceLimitError("operation exceeds the execution budget", limit_class="execution_ms")
        except psycopg.Error as exc:
            self._developer.rollback()
            raise ValidationError("storage backend rejected the request") from exc
        else:
            self._developer.commit()
        return count

    @_guard_pending_platform_upgrades
    def field_domains(self, collection):
        """Live catalog lookup (R-2 stage 2) doubling as the value-domain
        source B-1 (i) needs: for every column of `collection`, this
        database's own `information_schema.columns.data_type` is mapped
        back to a domain category `encode_value` can validate a bound
        value against. Raises `errors.NotFoundError` if `collection` does
        not exist -- the same existence-check role the pre-B-1
        `field_names` method played.

        Phase 6 WP-3 (design D-3, L6-1 (v)): a physical `text` column's
        own domain is no longer a single shared `"text"` bucket
        (`_DOMAIN_BY_DATA_TYPE`'s own corrected comment above) (in `postgres_types.py`) -- it is
        looked up in the declared-type REGISTRY instead
        (`_TEXT_DOMAIN_BY_DECLARED_TYPE`), which is the only place that
        can recover which of `string`/`object`/`array`/`json` the column
        actually is. A `text`-physical column absent from the registry
        (should not occur for any field this peer's own `create_
        collection`/`add_field` created after this WP -- see
        `create_collection`'s own registry-write below) degrades to
        `"string"`, never a crash.
        """
        validate_identifier(collection, "entity")
        try:
            with self._developer.cursor() as cur:
                self._set_timeouts(cur, self._catalog_timeout_ms)
                _execute(cur, sql.SQL(
                    "SELECT column_name, data_type FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = %s "
                    "ORDER BY ordinal_position"
                ), [collection])
                rows = cur.fetchall()
                declared = self._field_types_locked(cur, collection) if rows else {}
        except (psycopg.errors.QueryCanceled, psycopg.errors.LockNotAvailable):
            self._developer.rollback()
            raise ResourceLimitError("operation exceeds the execution budget", limit_class="execution_ms")
        except psycopg.errors.UndefinedTable as exc:
            self._developer.rollback()
            # WP-3 差し戻し 最終ラウンド (supervisor ruling 2026-09-04,
            # 裁定 6, review F9): `_mdb_field_types` missing entirely means
            # migration 0006 was never applied to this application DB -- an
            # OPERATOR/DEPLOYMENT defect, never a client mistake. Before
            # this fix every read/write on an un-migrated DB surfaced as
            # `ValidationError` (contract `VALIDATION_FAILED`, a CLIENT
            # fault code) -- fail-closed either way, but the wrong fault
            # attribution. `StorageConfigurationError` is this peer's own
            # existing "permanent misconfiguration, not a client mistake"
            # class (`credential_store_postgres.py`'s identical `
            # InsufficientPrivilege` precedent), mapping to `SERVICE_
            # UNAVAILABLE` at the HTTP boundary instead.
            raise StorageConfigurationError(
                "the storage backend refused this read due to a missing declared-field-type registry "
                "(migration 0006 not applied to this application database)"
            ) from exc
        except psycopg.Error as exc:
            self._developer.rollback()
            raise ValidationError("storage backend rejected the request") from exc
        else:
            self._developer.commit()
        if not rows:
            raise NotFoundError("collection not found")
        domains = {}
        for name, data_type in rows:
            if data_type in _DOMAIN_BY_DATA_TYPE:
                domains[name] = _DOMAIN_BY_DATA_TYPE[data_type]
            else:
                domains[name] = _TEXT_DOMAIN_BY_DECLARED_TYPE.get(declared.get(name), "string")
        return domains

    def _field_types_locked(self, cur, collection):
        """Reads `_mdb_field_types` over an ALREADY-OPEN cursor (shares
        the caller's own transaction/commit-or-rollback, `field_domains`/
        `field_types` alike -- never a second, independent connection
        round trip)."""
        _execute(cur, sql.SQL("SELECT field, declared_type FROM {} WHERE entity = %s")
                  .format(sql.Identifier(_FIELD_TYPES_TABLE)), [collection])
        return {field: declared_type for field, declared_type in cur.fetchall()}

    @_guard_pending_platform_upgrades
    def field_types(self, collection):
        """Phase 6 WP-3 (design D-3): see `backend.StorageBackend.
        field_types`'s own contract -- the single source of truth `GET
        /v1/catalog` (`http.py::get_catalog`) and the cell-layer choke
        point (`cell.py::_prepare_values`/`_bind_filters`) both read.
        Existence-checked the same way `field_domains` is (an entity with
        no columns at all cannot exist on this backend)."""
        validate_identifier(collection, "entity")
        try:
            with self._developer.cursor() as cur:
                self._set_timeouts(cur, self._catalog_timeout_ms)
                _execute(cur, sql.SQL(
                    "SELECT count(*) FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = %s"
                ), [collection])
                (exists,) = cur.fetchone()
                declared = self._field_types_locked(cur, collection) if exists else {}
        except (psycopg.errors.QueryCanceled, psycopg.errors.LockNotAvailable):
            self._developer.rollback()
            raise ResourceLimitError("operation exceeds the execution budget", limit_class="execution_ms")
        except psycopg.errors.UndefinedTable as exc:
            self._developer.rollback()
            # See `field_domains`'s own identical rework above -- same
            # operator/deployment-fault attribution, same class.
            raise StorageConfigurationError(
                "the storage backend refused this read due to a missing declared-field-type registry "
                "(migration 0006 not applied to this application database)"
            ) from exc
        except psycopg.Error as exc:
            self._developer.rollback()
            raise ValidationError("storage backend rejected the request") from exc
        else:
            self._developer.commit()
        if not exists:
            raise NotFoundError("collection not found")
        return declared

    @_guard_pending_platform_upgrades
    def all_field_types(self):
        """Phase 6 WP-3 (design D-3): see `backend_sqlite.SQLiteBackend.
        all_field_types`'s identical docstring -- `GET /v1/catalog`'s
        sole data source."""
        try:
            with self._developer.cursor() as cur:
                self._set_timeouts(cur, self._catalog_timeout_ms)
                _execute(cur, sql.SQL("SELECT entity, field, declared_type FROM {}")
                          .format(sql.Identifier(_FIELD_TYPES_TABLE)))
                rows = cur.fetchall()
        except (psycopg.errors.QueryCanceled, psycopg.errors.LockNotAvailable):
            self._developer.rollback()
            raise ResourceLimitError("operation exceeds the execution budget", limit_class="execution_ms")
        except psycopg.errors.UndefinedTable as exc:
            self._developer.rollback()
            # See `field_domains`'s own identical rework above -- same
            # operator/deployment-fault attribution, same class.
            raise StorageConfigurationError(
                "the storage backend refused this read due to a missing declared-field-type registry "
                "(migration 0006 not applied to this application database)"
            ) from exc
        except psycopg.Error as exc:
            self._developer.rollback()
            raise ValidationError("storage backend rejected the request") from exc
        else:
            self._developer.commit()
        result: dict = {}
        for entity, field, declared_type in rows:
            result.setdefault(entity, {})[field] = declared_type
        return result

    @staticmethod
    def _decode_constraint_row(enum_json, nullable_value):
        """Phase 9 WP-3a (design D-2 (1)/(4)): `_mdb_field_types.enum_json`
        (a JSON-array TEXT column, `NULL` when this field declares no
        `enum`) / `.nullable` (a real `boolean` column, migration
        0009_field_constraints_upgrade.sql) -> the same `{"nullable":
        bool, "enum": [...]}` shape `backend_sqlite.SQLiteBackend`'s own
        in-memory registry carries -- `"enum"` present only when
        `enum_json` is not `NULL`."""
        constraints = {"nullable": bool(nullable_value)}
        if enum_json is not None:
            constraints["enum"] = json.loads(enum_json)
        return constraints

    def _field_constraints_locked(self, cur, collection):
        """Reads `_mdb_field_types.enum_json`/`.nullable` over an
        ALREADY-OPEN cursor -- same sharing discipline as
        `_field_types_locked` immediately above."""
        _execute(cur, sql.SQL("SELECT field, enum_json, nullable FROM {} WHERE entity = %s")
                  .format(sql.Identifier(_FIELD_TYPES_TABLE)), [collection])
        return {
            field: self._decode_constraint_row(enum_json, nullable_value)
            for field, enum_json, nullable_value in cur.fetchall()
        }

    @_guard_pending_platform_upgrades
    def field_constraints(self, collection):
        """Phase 9 WP-3a (design D-2 (1)/(4)): see `backend.
        StorageBackend.field_constraints`'s own contract -- the single
        source of truth `GET /v1/catalog` and the cell-layer choke point
        (`cell.py::_prepare_values`, never `_bind_filters`) both read.
        Existence-checked the same way `field_types` is."""
        validate_identifier(collection, "entity")
        try:
            with self._developer.cursor() as cur:
                self._set_timeouts(cur, self._catalog_timeout_ms)
                _execute(cur, sql.SQL(
                    "SELECT count(*) FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = %s"
                ), [collection])
                (exists,) = cur.fetchone()
                declared = self._field_constraints_locked(cur, collection) if exists else {}
        except (psycopg.errors.QueryCanceled, psycopg.errors.LockNotAvailable):
            self._developer.rollback()
            raise ResourceLimitError("operation exceeds the execution budget", limit_class="execution_ms")
        except psycopg.errors.UndefinedTable as exc:
            self._developer.rollback()
            raise StorageConfigurationError(
                "the storage backend refused this read due to a missing declared-field-type registry "
                "(migration 0006 not applied to this application database)"
            ) from exc
        except psycopg.Error as exc:
            self._developer.rollback()
            raise ValidationError("storage backend rejected the request") from exc
        else:
            self._developer.commit()
        if not exists:
            raise NotFoundError("collection not found")
        return declared

    def _field_types_and_constraints_locked(self, cur, collection):
        """Code review §2 C / 監督裁定 C: `field_types`'s own
        `declared_type` and `field_constraints`'s own `enum_json`/
        `nullable` live on the SAME `_mdb_field_types` row -- this reads
        all three columns in the ONE query `_field_types_locked`/
        `_field_constraints_locked` used to make as TWO independent
        round trips against that identical row.

        History: CH-0525
        """
        _execute(cur, sql.SQL(
            "SELECT field, declared_type, enum_json, nullable FROM {} WHERE entity = %s"
        ).format(sql.Identifier(_FIELD_TYPES_TABLE)), [collection])
        types: dict = {}
        constraints: dict = {}
        for field, declared_type, enum_json, nullable_value in cur.fetchall():
            types[field] = declared_type
            constraints[field] = self._decode_constraint_row(enum_json, nullable_value)
        return types, constraints

    @_guard_pending_platform_upgrades
    def field_types_and_constraints(self, collection):
        """Code review §2 C / 監督裁定 C (P-8/G-4 performance
        finding): see `backend.StorageBackend.field_types_and_
        constraints`'s own contract -- `field_types` and `field_
        constraints` merged into the single query `_field_types_and_
        constraints_locked` above makes. `cell.py::_prepare_values` (and,
        via the pair it returns, `_check_missing_required_fields`) is
        the sole caller -- every other reader of `field_types`/`field_
        constraints` keeps calling one of those two on their own,
        unchanged. Existence-checked the same way both are.

        History: CH-0526
        """
        validate_identifier(collection, "entity")
        try:
            with self._developer.cursor() as cur:
                self._set_timeouts(cur, self._catalog_timeout_ms)
                _execute(cur, sql.SQL(
                    "SELECT count(*) FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = %s"
                ), [collection])
                (exists,) = cur.fetchone()
                types, constraints = self._field_types_and_constraints_locked(cur, collection) if exists else ({}, {})
        except (psycopg.errors.QueryCanceled, psycopg.errors.LockNotAvailable):
            self._developer.rollback()
            raise ResourceLimitError("operation exceeds the execution budget", limit_class="execution_ms")
        except psycopg.errors.UndefinedTable as exc:
            self._developer.rollback()
            raise StorageConfigurationError(
                "the storage backend refused this read due to a missing declared-field-type registry "
                "(migration 0006 not applied to this application database)"
            ) from exc
        except psycopg.Error as exc:
            self._developer.rollback()
            raise ValidationError("storage backend rejected the request") from exc
        else:
            self._developer.commit()
        if not exists:
            raise NotFoundError("collection not found")
        return types, constraints

    @_guard_pending_platform_upgrades
    def all_field_constraints(self):
        """Phase 9 WP-3a (design D-2 (1)/(4)): see `backend_sqlite.
        SQLiteBackend.all_field_constraints`'s identical docstring --
        `GET /v1/catalog`'s sole data source for `field_constraints`."""
        try:
            with self._developer.cursor() as cur:
                self._set_timeouts(cur, self._catalog_timeout_ms)
                _execute(cur, sql.SQL("SELECT entity, field, enum_json, nullable FROM {}")
                          .format(sql.Identifier(_FIELD_TYPES_TABLE)))
                rows = cur.fetchall()
        except (psycopg.errors.QueryCanceled, psycopg.errors.LockNotAvailable):
            self._developer.rollback()
            raise ResourceLimitError("operation exceeds the execution budget", limit_class="execution_ms")
        except psycopg.errors.UndefinedTable as exc:
            self._developer.rollback()
            raise StorageConfigurationError(
                "the storage backend refused this read due to a missing declared-field-type registry "
                "(migration 0006 not applied to this application database)"
            ) from exc
        except psycopg.Error as exc:
            self._developer.rollback()
            raise ValidationError("storage backend rejected the request") from exc
        else:
            self._developer.commit()
        result: dict = {}
        for entity, field, enum_json, nullable_value in rows:
            result.setdefault(entity, {})[field] = self._decode_constraint_row(enum_json, nullable_value)
        return result

    @_guard_pending_platform_upgrades
    def alter_field_constraints(self, collection, field, *, enum=UNCHANGED, nullable=None, audit_hook=None,
                                deadline=None, dry_run=False, idempotency_record=None):
        """Phase 9 WP-3a (design D-2 (5)/(6), 実装の形 4, F-6, 監督裁定
        S-g): see `backend.StorageBackend.alter_field_constraints`'s own
        contract. Unlike `create_collection`/`add_field` above (whose own
        "read the live catalog, then DDL in a later transaction" shape
        `field_domains` embodies), this method never leaves the developer
        connection's own transaction between its existing-row SELECT and
        its registry UPDATE -- both happen inside the SAME `with self.
        _developer.cursor()` block, committed (or rolled back) together
        as the LAST step of this one method. The developer connection
        reads real APPLICATION DATA rows here (not only the catalog) --
        safe because this application's own developer role OWNS every
        entity table it creates (`create_collection`/`add_field` above),
        and PostgreSQL grants a table's owner every privilege on it,
        `SELECT` included, with no separate `GRANT` required (F-6,
        `migrations/0003_provision_application.sql`)."""
        validate_identifier(collection, "entity")
        validate_identifier(field, "field")
        timeout_ms = self._timeout_ms(deadline)
        hook_fired = False
        try:
            with self._developer.cursor() as cur:
                if timeout_ms is not None:
                    self._set_timeouts(cur, timeout_ms)
                _execute(cur, sql.SQL(
                    "SELECT declared_type, enum_json, nullable FROM {} WHERE entity = %s AND field = %s"
                ).format(sql.Identifier(_FIELD_TYPES_TABLE)), [collection, field])
                row = cur.fetchone()
                if row is None:
                    raise NotFoundError("field not found")
                declared_type, current_enum_json, current_nullable = row
                new_nullable = bool(current_nullable) if nullable is None else nullable
                # Code review §2 A / 監督裁定 A: tri-state
                # `enum` -- `UNCHANGED` (default) keeps the field's
                # current `enum` (decoded from the row already read
                # above); an explicit `None` CLEARS it; any other value
                # (an already-validated, non-empty list) SETS/REPLACES
                # it. This is the SAME three-way rule `backend_sqlite.
                # SQLiteBackend.alter_field_constraints` applies.
                # history: CH-0528
                if enum is UNCHANGED:
                    new_enum = json.loads(current_enum_json) if current_enum_json is not None else None
                elif enum is not None:
                    new_enum = list(enum)
                else:
                    new_enum = None
                # Code review §2 F / 監督裁定 F: locks
                # `collection` IN SHARE ROW EXCLUSIVE MODE before scanning
                # its existing rows, inside this SAME transaction -- this
                # blocks a concurrent INSERT/UPDATE/DELETE (ROW
                # EXCLUSIVE) on this table for the rest of this
                # transaction while still permitting concurrent SELECTs
                # (ACCESS SHARE), so no other session's write can land a
                # newly-violating row in the window between this scan
                # and this same transaction's own COMMIT below. The
                # single-transaction placement (実装の形 4, S-g) alone
                # only closes "registry updated while a row still went
                # unscanned"; under READ COMMITTED (this connection's own
                # default) it does not, by itself, close this phantom-
                # write window -- this lock does.
                #
                # R-35 (Phase 10, WP-6d-i review): the original fix used
                # plain `SHARE MODE`, which does not conflict with itself
                # -- two concurrent `alter_field`/`add_field` calls on the
                # SAME entity could both acquire it here, then each block
                # at its own later `ALTER TABLE` (ACCESS EXCLUSIVE)
                # waiting on the other's SHARE lock, a guaranteed mutual
                # wait broken only by PostgreSQL's deadlock detector
                # aborting one side with an error rather than the two
                # calls simply serializing. `SHARE ROW EXCLUSIVE`
                # conflicts with itself, so the second caller instead
                # waits here, at LOCK TABLE, and proceeds only once the
                # first transaction commits or rolls back -- it still
                # excludes concurrent row writers (ROW EXCLUSIVE) exactly
                # as plain SHARE did, so the scan property above is
                # unchanged.
                # history: CH-0529
                _execute(cur, sql.SQL("LOCK TABLE {} IN SHARE ROW EXCLUSIVE MODE").format(sql.Identifier(collection)))
                _execute(cur, sql.SQL("SELECT {} FROM {}").format(
                    sql.Identifier(field), sql.Identifier(collection)))
                violation = None
                for (value,) in cur.fetchall():
                    if value is None:
                        if new_nullable is False:
                            violation = "nullable"
                            break
                        continue
                    if new_enum is not None:
                        decoded = bool(value) if declared_type == "boolean" else value
                        if decoded not in new_enum:
                            violation = "enum"
                            break
                if violation is not None:
                    # Code review §2 D / 監督裁定 D: `field`
                    # names a POSITION IN THE REQUEST (design D-3 (2)),
                    # not the entity field name -- see `backend_sqlite.
                    # SQLiteBackend.alter_field_constraints`'s identical
                    # comment for why that position is `violation` itself.
                    # history: CH-0530
                    raise ConflictError(
                        "existing rows violate the constraints this alter_field would establish",
                        details={"field": violation, "violated_declaration": violation},
                    )
                # Phase 9 WP-3b (design D-4 (4)): the registry UPDATE and
                # revision bump are skipped for a dry run -- the scan
                # above (and its possible `ConflictError`) already ran
                # for real either way, SAME refusal for dry_run and real.
                new_enum_json = json.dumps(new_enum) if new_enum is not None else None
                if not dry_run:
                    _execute(cur, sql.SQL(
                        "UPDATE {} SET enum_json = %s, nullable = %s WHERE entity = %s AND field = %s"
                    ).format(sql.Identifier(_FIELD_TYPES_TABLE)), [new_enum_json, new_nullable, collection, field])
                    self._bump_schema_revision(cur)
                _execute(cur, sql.SQL("SELECT revision FROM {} WHERE id = TRUE")
                          .format(sql.Identifier(_SCHEMA_REVISION_TABLE)))
                new_revision = cur.fetchone()[0]
                # Phase 9 WP-3b: `descriptor`'s OTHER, pre-existing fields
                # -- same-cursor read, so a real (non-dry-run) call's own
                # UPDATE above is already visible here (read-your-own-
                # writes); a dry run's is not, since nothing was written.
                existing_types, existing_constraints = self._field_types_and_constraints_locked(cur, collection)
            # Phase 9 WP-3c rework (design D-5, I-1/I-8): built here,
            # BEFORE the commit/rollback branch below, from `new_enum`/
            # `new_nullable` (already resolved above) and `existing_
            # types`/`existing_constraints` (already read back, real,
            # inside the SAME transaction) -- reused for both this
            # method's own idempotency write below and its final `return`
            # further down, never a second, independently constructed
            # copy.
            new_field_constraints = {"nullable": new_nullable}
            if new_enum is not None:
                new_field_constraints["enum"] = list(new_enum)
            descriptor = {
                "entity": collection,
                "fields": sorted(existing_types),
                "field_types": existing_types,
                "field_constraints": {**existing_constraints, field: new_field_constraints},
            }
            if dry_run:
                self._developer.rollback()
            else:
                if audit_hook is not None:
                    audit_hook.pre_commit()
                    hook_fired = True
                # Phase 9 WP-3c (design D-5, I-1/I-8): `new_revision` was
                # already read back for real, inside this SAME
                # transaction, above.
                if idempotency_record is not None:
                    key, digest, now_ms, req_id = idempotency_record
                    response_json = json.dumps({
                        "committed": True, "revision": str(new_revision), "descriptor": descriptor,
                        "request_id": req_id,
                    })
                    self._write_idempotency_row(self._developer, key, digest, response_json, now_ms)
                self._developer.commit()
        except (psycopg.errors.QueryCanceled, psycopg.errors.LockNotAvailable):
            self._developer.rollback()
            raise ResourceLimitError("operation exceeds the execution budget", limit_class="execution_ms")
        except (NotFoundError, ConflictError):
            self._developer.rollback()
            raise
        except psycopg.errors.UndefinedTable:
            self._developer.rollback()
            raise NotFoundError("collection not found")
        except psycopg.Error as exc:
            self._developer.rollback()
            if hook_fired:
                audit_hook.commit_failed()
                raise AuditSinkUnavailable(
                    "the durable audit sink recorded this operation but the data commit failed"
                ) from exc
            raise ValidationError("storage backend rejected the request") from exc
        except Exception:
            self._developer.rollback()
            raise
        # `descriptor` was already built above (Phase 9 WP-3c rework),
        # before the commit/rollback branch -- reused verbatim here.
        return new_revision, descriptor

    @_guard_pending_platform_upgrades
    def schema_revision(self):
        try:
            with self._developer.cursor() as cur:
                self._set_timeouts(cur, self._catalog_timeout_ms)
                _execute(cur, sql.SQL("SELECT revision FROM {} WHERE id = TRUE")
                          .format(sql.Identifier(_SCHEMA_REVISION_TABLE)))
                row = cur.fetchone()
        except (psycopg.errors.QueryCanceled, psycopg.errors.LockNotAvailable):
            self._developer.rollback()
            raise ResourceLimitError("operation exceeds the execution budget", limit_class="execution_ms")
        except psycopg.Error as exc:
            self._developer.rollback()
            raise ValidationError("storage backend rejected the request") from exc
        else:
            self._developer.commit()
        return row[0] if row else 0

    def _bump_schema_revision(self, cur):
        _execute(cur, sql.SQL("UPDATE {} SET revision = revision + 1 WHERE id = TRUE")
                  .format(sql.Identifier(_SCHEMA_REVISION_TABLE)))

    # ------------------------------------------------------------------
    # DDL (developer connection only -- R-1)
    # ------------------------------------------------------------------
    @_guard_pending_platform_upgrades
    def create_collection(self, name, fields, *, field_types=None, field_constraints=None, audit_hook=None,
                          deadline=None, dry_run=False, idempotency_record=None):
        validate_identifier(name, "collection")
        definitions = []
        for field, field_type in fields.items():
            validate_identifier(field, "field")
            definitions.append(sql.SQL("{} {}").format(sql.Identifier(field), _TYPE_SQL[field_type]))
        # Design docs/design/PHASE11_KEYSET_PAGING_V1.md D-2's own table:
        # every NEW collection carries the
        # internal row-order column from the start -- an existing
        # collection (provisioned before this column existed) gets it
        # retrofitted by `migrations/0015_row_order_column_upgrade.sql`
        # instead. Not reachable through `fields`/`field_types` (the
        # client-declared columns validated above): `identifiers.py`'s
        # own leading-`_` syntax rejection already makes this exact name
        # un-declarable, so no client request can ever collide with it.
        definitions.append(sql.SQL("{} BIGINT GENERATED ALWAYS AS IDENTITY").format(
            sql.Identifier(_ROW_ORDER_COLUMN)))
        statement = sql.SQL("CREATE TABLE {} ({})").format(
            sql.Identifier(name), sql.SQL(", ").join(definitions)
        )
        # Phase 6 WP-3 (design D-3): robust to a direct caller that
        # bypasses `cell.py` (e.g. this repository's own tests, which call
        # this method straight against the backend) and supplies no
        # `field_types` at all, or only a partial one -- every name in
        # `fields` not covered gets the SAME backfill-rule fallback
        # `cell.ApplicationCell.create_collection` itself applies.
        field_types = dict(field_types or {})
        for field, physical_type in fields.items():
            field_types.setdefault(field, _FOUNDATION_TYPE_TO_CONTRACT_TYPE[physical_type])
        # Phase 9 WP-3a (design D-2 (1)/(4)): same robustness fallback for
        # `field_constraints` -- a name in `fields` `field_constraints`
        # (partial) omits gets `{"nullable": True}`, no `enum` (contract
        # `SchemaOperationRequest.field_constraints.description`).
        resolved_constraints = {}
        for field in fields:
            declared = dict((field_constraints or {}).get(field) or {})
            declared.setdefault("nullable", True)
            resolved_constraints[field] = declared
        field_types_statement = sql.SQL(
            "INSERT INTO {} (entity, field, declared_type, enum_json, nullable) VALUES (%s, %s, %s, %s, %s)"
        ).format(sql.Identifier(_FIELD_TYPES_TABLE))
        # Phase 4 (design PHASE4_DURABLE_AUDIT_SINK_V1.md D-2, review M-6):
        # `commit()` moved INSIDE this `try` (it used to run in an `else:`
        # clause, OUTSIDE the try/except -- a raise from `commit()` itself
        # used to propagate as a raw, unclassified exception, never
        # reaching this method's own `except psycopg.Error` translation at
        # all). `audit_hook.pre_commit()` -- when this schema op is
        # dispatched through `cell.py` -- runs as the LAST statement before
        # `self._developer.commit()`, still inside this same try: a raise
        # from it (an `AuditSinkUnavailable`, not a `psycopg.Error`) is
        # caught by the final `except Exception` below, which rolls back
        # the still-uncommitted DDL before propagating (fail-closed by
        # construction, D-2 item 2: schema operations are unconditionally
        # fail-closed). `hook_fired` distinguishes "the durable pre-commit
        # write itself failed" (no error row needed -- nothing was
        # committed to correct) from "the durable write succeeded but
        # THIS backend's own commit then failed" (D-2's error-row case).
        hook_fired = False
        timeout_ms = self._timeout_ms(deadline)
        try:
            with self._developer.cursor() as cur:
                if timeout_ms is not None:
                    self._set_timeouts(cur, timeout_ms)
                _execute(cur, statement)
                # Phase 9 WP-3b (design D-4 (4)): the revision bump and
                # the declared-type registry write are both skipped for a
                # dry run -- the DDL above already ran for real either
                # way, so a dry run reaches the SAME `DuplicateTable` ->
                # `ConflictError` a real call would.
                if not dry_run:
                    self._bump_schema_revision(cur)
                    # Phase 6 WP-3 (design D-3): the declared-type
                    # registry write lands in the SAME transaction as the
                    # DDL above -- atomic by construction (a failure/
                    # rollback below undoes both together, never one
                    # without the other).
                    for field in fields:
                        constraints = resolved_constraints[field]
                        enum_json = json.dumps(constraints["enum"]) if "enum" in constraints else None
                        _execute(cur, field_types_statement,
                                 [name, field, field_types[field], enum_json, constraints["nullable"]])
                _execute(cur, sql.SQL("SELECT revision FROM {} WHERE id = TRUE")
                          .format(sql.Identifier(_SCHEMA_REVISION_TABLE)))
                new_revision = cur.fetchone()[0]
            if dry_run:
                self._developer.rollback()
            else:
                if audit_hook is not None:
                    audit_hook.pre_commit()
                    hook_fired = True
                # Phase 9 WP-3c (design D-5, I-1/I-8): the idempotency
                # record is written as the LAST statement before this
                # backend's own commit -- same connection, same
                # transaction as the DDL above, exactly like `audit_hook.
                # pre_commit()` immediately above it. `new_revision` was
                # already read back for real, inside this SAME
                # transaction, above -- unlike `backend_sqlite.
                # SQLiteBackend`'s own in-process counterpart, nothing
                # here is a prediction. The stored response mirrors this
                # method's own final `return` below verbatim (same
                # `name`/`fields`/`field_types`/`resolved_constraints`
                # locals), so a later replay is byte-identical to what an
                # uncached call would have returned.
                if idempotency_record is not None:
                    key, digest, now_ms, req_id = idempotency_record
                    response_json = json.dumps({
                        "committed": True, "revision": str(new_revision),
                        "descriptor": {
                            "entity": name, "fields": sorted(fields), "field_types": dict(field_types),
                            "field_constraints": {f: dict(c) for f, c in resolved_constraints.items()},
                        },
                        "request_id": req_id,
                    })
                    self._write_idempotency_row(self._developer, key, digest, response_json, now_ms)
                self._developer.commit()
        except (psycopg.errors.QueryCanceled, psycopg.errors.LockNotAvailable):
            self._developer.rollback()
            raise ResourceLimitError("operation exceeds the execution budget", limit_class="execution_ms")
        except psycopg.errors.DuplicateTable:
            self._developer.rollback()
            raise ConflictError("collection already exists")
        except psycopg.Error as exc:
            self._developer.rollback()
            if hook_fired:
                audit_hook.commit_failed()
                raise AuditSinkUnavailable(
                    "the durable audit sink recorded this operation but the data commit failed"
                ) from exc
            raise ValidationError("storage backend rejected the request") from exc
        except Exception:
            # Covers `audit_hook.pre_commit()` itself raising
            # `AuditSinkUnavailable` (never a `psycopg.Error`, so the
            # branch above does not catch it) -- the DDL above already ran
            # on this connection but was never committed; roll it back
            # before letting the failure propagate.
            self._developer.rollback()
            raise
        return new_revision, {
            "entity": name,
            "fields": sorted(fields),
            "field_types": dict(field_types),
            "field_constraints": {f: dict(c) for f, c in resolved_constraints.items()},
        }

    @_guard_pending_platform_upgrades
    def add_field(self, collection, field, field_type, *, contract_type=None, enum=None, nullable=None,
                  audit_hook=None, deadline=None, dry_run=False, idempotency_record=None):
        validate_identifier(collection, "entity")
        validate_identifier(field, "field")
        statement = sql.SQL("ALTER TABLE {} ADD COLUMN {} {}").format(
            sql.Identifier(collection), sql.Identifier(field), _TYPE_SQL[field_type]
        )
        # Phase 6 WP-3 (design D-3): same robustness fallback as
        # `create_collection` above, for a direct caller supplying no
        # `contract_type`.
        if contract_type is None:
            contract_type = _FOUNDATION_TYPE_TO_CONTRACT_TYPE[field_type]
        # Phase 9 WP-3a (design D-2 (1)/(4)): `nullable=None` (no explicit
        # declaration) resolves to the contract default `True`, matching
        # `create_collection`'s own identical fallback above.
        resolved_nullable = True if nullable is None else nullable
        enum_json = json.dumps(list(enum)) if enum is not None else None
        field_types_statement = sql.SQL(
            "INSERT INTO {} (entity, field, declared_type, enum_json, nullable) VALUES (%s, %s, %s, %s, %s)"
        ).format(sql.Identifier(_FIELD_TYPES_TABLE))
        # Phase 4: same `commit()`-inside-`try` + pre-commit-hook structure
        # as `create_collection` above -- see that method's own comment.
        hook_fired = False
        timeout_ms = self._timeout_ms(deadline)
        try:
            with self._developer.cursor() as cur:
                if timeout_ms is not None:
                    self._set_timeouts(cur, timeout_ms)
                if resolved_nullable is False:
                    # M-6 (監督裁定, WP-3a rework 2, 2026-09-07): mirrors
                    # `alter_field_constraints`'s own existing-row rule
                    # (LOCK TABLE ... IN SHARE ROW EXCLUSIVE MODE, inside
                    # this SAME transaction, before the scan), for a NEW
                    # field instead of an existing one -- a NEW field
                    # declaring `nullable: false` on an entity that
                    # already holds rows would leave every one of them
                    # holding `null` in it (there being no earlier value
                    # for it to have held), so it is refused the same
                    # way. Checked BEFORE the DDL below, so a conflicting
                    # call changes NOTHING -- no column, no registry row,
                    # no revision bump; this cursor's own transaction
                    # rolls back whole (`except ... self._developer.
                    # rollback()` below, the same as every other failure
                    # path here).
                    #
                    # R-35 (Phase 10, WP-6d-i review): plain `SHARE MODE`
                    # does not conflict with itself, so two concurrent
                    # `add_field`/`alter_field` calls on the SAME entity
                    # could both acquire it, then each block at its own
                    # later `ALTER TABLE` (ACCESS EXCLUSIVE) waiting on
                    # the other's SHARE lock -- a guaranteed mutual wait,
                    # broken only by PostgreSQL's deadlock detector
                    # aborting one side with an error instead of the two
                    # calls simply serializing. `SHARE ROW EXCLUSIVE`
                    # conflicts with itself, so the second caller instead
                    # waits here, at LOCK TABLE, and proceeds only once
                    # the first transaction commits or rolls back -- it
                    # still excludes concurrent row writers (ROW
                    # EXCLUSIVE) exactly as plain SHARE did, so the scan
                    # property above is unchanged.
                    _execute(cur, sql.SQL("LOCK TABLE {} IN SHARE ROW EXCLUSIVE MODE").format(sql.Identifier(collection)))
                    _execute(cur, sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(collection)))
                    (existing_rows,) = cur.fetchone()
                    if existing_rows > 0:
                        raise ConflictError(
                            "add_field declaring nullable: false on an entity that already holds rows "
                            "would leave every existing row holding null in the new field",
                            details={"violated_declaration": "nullable", "field": "nullable"},
                        )
                # Phase 9 WP-3b: the entity's OTHER, pre-existing fields,
                # read BEFORE this call's own DDL/registry write -- used
                # for `descriptor` below, dry_run or not (a dry run never
                # writes the new field to the registry at all, so it must
                # come from this call's own arguments instead, exactly
                # like `backend_sqlite.SQLiteBackend.add_field`).
                existing_types, existing_constraints = self._field_types_and_constraints_locked(cur, collection)
                _execute(cur, statement)
                # Phase 9 WP-3b (design D-4 (4)): the revision bump and
                # registry write are both skipped for a dry run -- the
                # DDL above already ran for real either way, so a dry run
                # reaches the SAME `DuplicateColumn`/`UndefinedTable` ->
                # `ConflictError`/`NotFoundError` a real call would.
                if not dry_run:
                    self._bump_schema_revision(cur)
                    # Phase 6 WP-3 (design D-3): same-transaction registry
                    # write as `create_collection` above.
                    _execute(cur, field_types_statement, [collection, field, contract_type, enum_json, resolved_nullable])
                # WP-3a rework 3 (real, measured bug -- SchemaOperationResult.
                # revision is `required` unconditionally, `contract/data-
                # service-api.v1.json`'s own `schemas.SchemaOperationResult.
                # required`): same same-transaction readback `alter_field_
                # constraints` above already performs -- this method used to
                # bump the counter but never read it back, so the caller had
                # no revision to report at all.
                _execute(cur, sql.SQL("SELECT revision FROM {} WHERE id = TRUE")
                          .format(sql.Identifier(_SCHEMA_REVISION_TABLE)))
                new_revision = cur.fetchone()[0]
            # Phase 9 WP-3c rework (design D-5, I-1/I-8): built here,
            # BEFORE the commit/rollback branch below -- see `alter_field_
            # constraints`'s own identical rework comment above.
            new_field_constraints = {"nullable": resolved_nullable}
            if enum is not None:
                new_field_constraints["enum"] = list(enum)
            descriptor = {
                "entity": collection,
                "fields": sorted(set(existing_types) | {field}),
                "field_types": {**existing_types, field: contract_type},
                "field_constraints": {**existing_constraints, field: new_field_constraints},
            }
            if dry_run:
                self._developer.rollback()
            else:
                if audit_hook is not None:
                    audit_hook.pre_commit()
                    hook_fired = True
                # Phase 9 WP-3c (design D-5, I-1/I-8): see `create_
                # collection`'s own identical comment above.
                if idempotency_record is not None:
                    key, digest, now_ms, req_id = idempotency_record
                    response_json = json.dumps({
                        "committed": True, "revision": str(new_revision), "descriptor": descriptor,
                        "request_id": req_id,
                    })
                    self._write_idempotency_row(self._developer, key, digest, response_json, now_ms)
                self._developer.commit()
        except (psycopg.errors.QueryCanceled, psycopg.errors.LockNotAvailable):
            self._developer.rollback()
            raise ResourceLimitError("operation exceeds the execution budget", limit_class="execution_ms")
        except psycopg.errors.DuplicateColumn:
            self._developer.rollback()
            raise ConflictError("field already exists")
        except psycopg.errors.UndefinedTable:
            self._developer.rollback()
            raise NotFoundError("collection not found")
        except psycopg.Error as exc:
            self._developer.rollback()
            if hook_fired:
                audit_hook.commit_failed()
                raise AuditSinkUnavailable(
                    "the durable audit sink recorded this operation but the data commit failed"
                ) from exc
            raise ValidationError("storage backend rejected the request") from exc
        except Exception:
            self._developer.rollback()
            raise
        return new_revision, descriptor

    # ------------------------------------------------------------------
    # values (R-2/B-1 value-domain gate) -- see the module-level
    # `_validate_value_domain`/`_check_domain` functions below (both in
    # `postgres_value_domain.py`), which hold
    # ALL of the actual logic. `encode_value` is a thin instance-method
    # wrapper only so it satisfies the shared `StorageBackend.encode_value`
    # call shape (`cell.py` always calls it as `self._backend.
    # encode_value(...)`); the real logic is deliberately free-standing,
    # connection-independent functions (m-8, independent review round 2:
    # "layer (i) 単体テストは接続不要であるべき" -- `tests/test_postgres.
    # py` calls these two directly, with no `platform`/`app_a` fixture and
    # no live PostgreSQL server involved at all).
    # ------------------------------------------------------------------
    def encode_value(self, value, domain=None, *, field=None, declared_type=None):
        return _validate_value_domain(value, domain, field=field, declared_type=declared_type)

    # ------------------------------------------------------------------
    # DML (runtime connection only -- R-1)
    # ------------------------------------------------------------------
    _where_sql = staticmethod(_where_sql)

    @_guard_pending_platform_upgrades
    def insert(self, collection, fields, params, *, deadline=None):
        # PostgreSQL 12+ has no per-row OID by default and this
        # foundation's own entity tables carry no server-assigned primary
        # key/serial column of any kind (unlike r2db-api's own `address`
        # concept -- this foundation declares `row_addressability:
        # unavailable`, and nothing in this return value is part of that
        # capability's own public surface: `conformance/
        # conformance_adapter_mitatedb.py::attempt_mutation_with_addresses`
        # already documents that this foundation's `insert()` return shape
        # carries nothing address-shaped and always reports `None`).
        # `ctid` is PostgreSQL's own always-present physical row locator
        # system column -- an opaque `(block,offset)` pair, returned here
        # as its string form purely as an "insert succeeded, here is SOME
        # backend-native handle" value. Unlike SQLite's own `rowid`
        # (stable across an `UPDATE`), PostgreSQL's `ctid` changes on
        # `UPDATE`/`VACUUM` -- a real, deliberate asymmetry between the
        # two backends' own `rowid` values, harmless here because no
        # caller (this test suite included) treats the returned value as
        # a stable long-term identity.
        columns = sql.SQL(", ").join(sql.Identifier(f) for f in fields)
        placeholders = sql.SQL(", ").join(sql.Placeholder() for _ in fields)
        statement = sql.SQL("INSERT INTO {} ({}) VALUES ({}) RETURNING ctid").format(
            sql.Identifier(collection), columns, placeholders
        )
        timeout_ms = self._timeout_ms(deadline)
        try:
            with self._runtime.cursor() as cur:
                if timeout_ms is not None:
                    self._set_timeouts(cur, timeout_ms)
                _execute(cur, statement, params)
                rowid = str(cur.fetchone()[0])
        except (psycopg.errors.QueryCanceled, psycopg.errors.LockNotAvailable):
            self._runtime.rollback()
            raise ResourceLimitError("operation exceeds the execution budget", limit_class="execution_ms")
        except psycopg.errors.UniqueViolation:
            self._runtime.rollback()
            raise ConflictError("write conflicts with a constraint")
        except psycopg.errors.UndefinedTable:
            self._runtime.rollback()
            raise NotFoundError("collection not found")
        except psycopg.Error as exc:
            # B-1 (ii): defensive backstop -- see this module's own
            # top-of-file docstring. Guarantees `self._runtime` is never
            # left aborted for the next call on this cell.
            self._runtime.rollback()
            raise ValidationError("storage backend rejected the request") from exc
        else:
            self._runtime.commit()
        return {"rowid": rowid}

    @_guard_pending_platform_upgrades
    def insert_in_transaction(self, collection, fields, params):
        # No commit/rollback here (unlike `insert` above): this runs
        # inside a transaction the seam's own `transact()` already opened
        # via `begin()` and will `commit()`/`rollback()` once, after every
        # operation in the batch (`cell.py::transact`'s own `except`
        # clause calls `self._backend.rollback()`, which is sufficient to
        # clear a psycopg connection's own aborted-transaction state after
        # an exception raised here). Low-level driver errors are still
        # translated to this shared `errors.FoundationError` vocabulary
        # here (mirroring `insert()`'s own translation) so `cell.py`'s
        # `transact()` never needs to name a backend-native exception type
        # (R-3).
        columns = sql.SQL(", ").join(sql.Identifier(f) for f in fields)
        placeholders = sql.SQL(", ").join(sql.Placeholder() for _ in fields)
        statement = sql.SQL("INSERT INTO {} ({}) VALUES ({}) RETURNING ctid").format(
            sql.Identifier(collection), columns, placeholders
        )
        try:
            with self._runtime.cursor() as cur:
                _execute(cur, statement, params)
                rowid = str(cur.fetchone()[0])
        # Phase 8 WP-1a rework 1 (裁定 2): the SAME
        # `execution_ms` mapping `insert()` above already has -- not rolled
        # back here either (same B-1 (ii) reasoning as every other
        # `except` clause in this method: the OUTER `transact()`
        # (`cell.py`) is the single rollback point for the whole batch).
        # `begin()`'s own `SET LOCAL statement_timeout`/`lock_timeout`
        # (module-level comment above `_timeout_ms`) is what makes this
        # exception reachable from an operation running INSIDE a batch,
        # not only a standalone single-operation call -- every HTTP
        # mutation reaches the database through this exact `..._in_
        # transaction` family (`cell.py::transact`, `http.py::post_mutate`
        # always dispatches through it), so leaving this mapping out here
        # left the whole HTTP mutation surface unable to ever observe a
        # real `LIMIT_EXCEEDED`/`execution_ms` denial (review finding 2).
        # history: CH-0537
        except (psycopg.errors.QueryCanceled, psycopg.errors.LockNotAvailable):
            raise ResourceLimitError("operation exceeds the execution budget", limit_class="execution_ms")
        except psycopg.errors.UniqueViolation:
            raise ConflictError("write conflicts with a constraint")
        except psycopg.errors.UndefinedTable:
            raise NotFoundError("collection not found")
        except psycopg.Error as exc:
            # B-1 (ii): translated, not rolled back here -- the OUTER
            # `transact()` (`cell.py`) always calls `self._backend.
            # rollback()` in its own `except` clause once this propagates,
            # which is the single rollback point for the whole batch.
            raise ValidationError("storage backend rejected the request") from exc
        return {"rowid": rowid}

    @_guard_pending_platform_upgrades
    def update_in_transaction(self, collection, fields, params, filters):
        # P3-D2 (WP-1.5): no commit/rollback here (unlike `update` below)
        # -- mirrors `insert_in_transaction`'s own reasoning above. Runs
        # inside the transaction the seam's own `transact()` already
        # opened via `begin()` and will `commit()`/`rollback()` once,
        # after every operation in the batch.
        assignments = sql.SQL(", ").join(
            sql.SQL("{} = %s").format(sql.Identifier(f)) for f in fields
        )
        statement = sql.SQL("UPDATE {} SET {}").format(sql.Identifier(collection), assignments)
        where, where_params = self._where_sql(filters)
        statement = statement + where
        try:
            with self._runtime.cursor() as cur:
                _execute(cur, statement, list(params) + where_params)
                updated = cur.rowcount
        # Phase 8 WP-1a rework 1 (裁定 2): see `insert_in_transaction`'s own
        # identical `except` clause immediately above for why this mapping
        # (not rolled back here -- the outer `transact()` is the single
        # rollback point) is required on every `..._in_transaction` method,
        # not only the standalone `update()`.
        except (psycopg.errors.QueryCanceled, psycopg.errors.LockNotAvailable):
            raise ResourceLimitError("operation exceeds the execution budget", limit_class="execution_ms")
        except psycopg.errors.UndefinedTable:
            raise NotFoundError("collection not found")
        except psycopg.Error as exc:
            # B-1 (ii): translated, not rolled back here -- the OUTER
            # `transact()` (`cell.py`) always calls `self._backend.
            # rollback()` in its own `except` clause once this propagates.
            raise ValidationError("storage backend rejected the request") from exc
        return {"updated": updated}

    @_guard_pending_platform_upgrades
    def delete_in_transaction(self, collection, filters):
        # P3-D2 (WP-1.5): no commit/rollback here (unlike `delete` below)
        # -- same reasoning as `update_in_transaction` immediately above.
        # `cell.ApplicationCell` has already run this request through the
        # same declare-and-echo confirmation choke `delete()` itself uses
        # before this is ever called.
        statement = sql.SQL("DELETE FROM {}").format(sql.Identifier(collection))
        where, params = self._where_sql(filters)
        statement = statement + where
        try:
            with self._runtime.cursor() as cur:
                _execute(cur, statement, params)
                deleted = cur.rowcount
        # Phase 8 WP-1a rework 1 (裁定 2): see `insert_in_transaction`'s own
        # identical `except` clause for why this mapping is required here
        # too (not rolled back here -- the outer `transact()` is the
        # single rollback point).
        except (psycopg.errors.QueryCanceled, psycopg.errors.LockNotAvailable):
            raise ResourceLimitError("operation exceeds the execution budget", limit_class="execution_ms")
        except psycopg.errors.UndefinedTable:
            raise NotFoundError("collection not found")
        except psycopg.Error as exc:
            raise ValidationError("storage backend rejected the request") from exc
        return {"deleted": deleted}

    @_guard_pending_platform_upgrades
    def read(self, collection, selected, filters, order_by, limit, *, deadline=None):
        columns = sql.SQL(", ").join(sql.Identifier(x) for x in selected)
        statement = sql.SQL("SELECT {} FROM {}").format(columns, sql.Identifier(collection))
        where, where_params = self._where_sql(filters)
        statement = statement + where
        if order_by is not None:
            # WP-3: `order_by` is always `None` or a non-empty LIST of
            # `(field, direction)` tuples now (`cell.py::_bind_order_by`),
            # multi-field sort included -- a pre-WP-3 single-field caller
            # already reaches this as a one-element list.
            #
            # M-4 (independent review, consistency fix): an unexpected
            # `direction` here used to raise a raw, untranslated `KeyError`
            # (this dict lookup runs BEFORE the `try/except psycopg.Error`
            # block below, so that block never saw it) -- never reachable
            # through `cell.py`'s own allowlist today, but the identical
            # defense-in-depth reasoning `backend_sqlite.py`'s own
            # `_DIRECTION_TOKENS` lookup now documents applies here too:
            # this backend's own SQL-composition step should fail with a
            # classified `errors.ValidationError`, not an uncaught
            # `KeyError`, regardless of what `cell.py` currently allows
            # through.
            try:
                terms = sql.SQL(", ").join(
                    sql.SQL("{} {}").format(sql.Identifier(field), _DIRECTION_SQL[direction])
                    for field, direction in order_by
                )
            except KeyError as exc:
                # WP-3e rework T1 (追補2 M-1): same literal denial
                # `cell.ApplicationCell._bind_order_by` already carries
                # (`errors.details_vocabulary.enum`) -- this comment's own
                # "defense-in-depth" framing above describes an
                # UNREACHABLE-today re-implementation of that exact cell-
                # layer check, not a storage-layer translation with no
                # in-memory sibling, so it gets the same 4-key `details`
                # (no per-item index survives the generator above, so
                # `field` stays the non-indexed `order_by/direction`
                # position, same convention `identifiers.validate_
                # identifier`'s own module comment documents for a
                # position that cannot be pinned to one list index here).
                raise ValidationError(
                    "invalid order direction",
                    details=violation("enum", field="order_by/direction", declared_type="string"),
                ) from exc
            statement = statement + sql.SQL(" ORDER BY ") + terms
        statement = statement + sql.SQL(" LIMIT %s")
        params = list(where_params) + [limit]
        timeout_ms = self._timeout_ms(deadline)
        try:
            with self._runtime.cursor() as cur:
                if timeout_ms is not None:
                    self._set_timeouts(cur, timeout_ms)
                _execute(cur, statement, params)
                columns_desc = [c.name for c in cur.description]
                rows = [dict(zip(columns_desc, row)) for row in cur.fetchall()]
        except (psycopg.errors.QueryCanceled, psycopg.errors.LockNotAvailable):
            self._runtime.rollback()
            raise ResourceLimitError("operation exceeds the execution budget", limit_class="execution_ms")
        except psycopg.errors.UndefinedTable:
            self._runtime.rollback()
            raise NotFoundError("collection not found")
        except psycopg.Error as exc:
            self._runtime.rollback()
            raise ValidationError("storage backend rejected the request") from exc
        else:
            self._runtime.commit()
        return rows

    @_guard_pending_platform_upgrades
    def update(self, collection, fields, params, filters, *, deadline=None):
        assignments = sql.SQL(", ").join(
            sql.SQL("{} = %s").format(sql.Identifier(f)) for f in fields
        )
        statement = sql.SQL("UPDATE {} SET {}").format(sql.Identifier(collection), assignments)
        where, where_params = self._where_sql(filters)
        statement = statement + where
        timeout_ms = self._timeout_ms(deadline)
        try:
            with self._runtime.cursor() as cur:
                if timeout_ms is not None:
                    self._set_timeouts(cur, timeout_ms)
                _execute(cur, statement, list(params) + where_params)
                updated = cur.rowcount
        except (psycopg.errors.QueryCanceled, psycopg.errors.LockNotAvailable):
            self._runtime.rollback()
            raise ResourceLimitError("operation exceeds the execution budget", limit_class="execution_ms")
        except psycopg.errors.UndefinedTable:
            self._runtime.rollback()
            raise NotFoundError("collection not found")
        except psycopg.Error as exc:
            self._runtime.rollback()
            raise ValidationError("storage backend rejected the request") from exc
        else:
            self._runtime.commit()
        return {"updated": updated}

    @_guard_pending_platform_upgrades
    def delete(self, collection, filters, audit_hook=None, *, deadline=None):
        statement = sql.SQL("DELETE FROM {}").format(sql.Identifier(collection))
        where, params = self._where_sql(filters)
        statement = statement + where
        # Phase 4 (design D-2, review M-6): same `commit()`-inside-`try` +
        # pre-commit-hook structure as `create_collection`/`add_field`
        # above -- `cell.ApplicationCell.delete` has already run this
        # request through `_validate_delete_confirmation` before this is
        # ever called, so every call here is confirmed-destructive and
        # therefore unconditionally fail-closed class (D-2 item 1).
        hook_fired = False
        timeout_ms = self._timeout_ms(deadline)
        try:
            with self._runtime.cursor() as cur:
                if timeout_ms is not None:
                    self._set_timeouts(cur, timeout_ms)
                _execute(cur, statement, params)
                deleted = cur.rowcount
            if audit_hook is not None:
                audit_hook.pre_commit()
                hook_fired = True
            self._runtime.commit()
        except (psycopg.errors.QueryCanceled, psycopg.errors.LockNotAvailable):
            self._runtime.rollback()
            raise ResourceLimitError("operation exceeds the execution budget", limit_class="execution_ms")
        except psycopg.errors.UndefinedTable:
            self._runtime.rollback()
            raise NotFoundError("collection not found")
        except psycopg.Error as exc:
            self._runtime.rollback()
            if hook_fired:
                audit_hook.commit_failed()
                raise AuditSinkUnavailable(
                    "the durable audit sink recorded this operation but the data commit failed"
                ) from exc
            raise ValidationError("storage backend rejected the request") from exc
        except Exception:
            self._runtime.rollback()
            raise
        return {"deleted": deleted}

    # ------------------------------------------------------------------
    # execution_ms (Phase 8 WP-1a, design D-1 "実装の形" 3): a real
    # `SET LOCAL statement_timeout`/`lock_timeout`, computed from the
    # residual budget `cell.ApplicationCell._limit_gate`'s own wall-clock
    # `deadline` still has left -- r2db `postgres.py::_timeout_ms`/`_set_
    # timeouts` (`:1936-1959`) is the matching reference realization
    # (independent code, P-6).
    # ------------------------------------------------------------------

    def _timeout_ms(self, deadline):
        if deadline is None:
            return None
        remaining_ms = max(0.0, (deadline - time.monotonic()) * 1000)
        return max(1, int(remaining_ms))

    def _set_timeouts(self, cur, timeout_ms):
        """`SET LOCAL` (not session-wide `SET`): scoped to the current
        transaction only, automatically discarded on commit/rollback --
        never leaking onto the next call this persistent connection
        serves. `timeout_ms` is always a server-computed `int` (from
        `_timeout_ms` above), never request content, so `sql.Literal`
        (necessary -- PostgreSQL's `SET` grammar has no bind-placeholder
        position here) composes a trusted value, not untrusted text."""
        statement_timeout = sql.SQL("SET LOCAL statement_timeout = {t}").format(t=sql.Literal(f"{timeout_ms}ms"))
        lock_timeout = sql.SQL("SET LOCAL lock_timeout = {t}").format(t=sql.Literal(f"{timeout_ms}ms"))
        _execute(cur, statement_timeout)
        _execute(cur, lock_timeout)

    @_guard_pending_platform_upgrades
    def begin(self, *, deadline=None):
        # psycopg3 connections (`autocommit=False`) already implicitly
        # start a transaction on first use; nothing to do beyond ensuring
        # no stale transaction is left open from a previous call.
        self._runtime.rollback()
        # Phase 8 WP-1a: `transact()`'s own multi-operation envelope sets
        # the timeout ONCE, here, for the whole batch's transaction --
        # `SET LOCAL` stays in effect for every statement `insert_in_
        # transaction`/`update_in_transaction`/`delete_in_transaction`
        # below run until this same transaction commits or rolls back.
        timeout_ms = self._timeout_ms(deadline)
        if timeout_ms is not None:
            with self._runtime.cursor() as cur:
                self._set_timeouts(cur, timeout_ms)

    def commit(self):
        self._runtime.commit()

    def rollback(self):
        self._runtime.rollback()

    # ------------------------------------------------------------------
    # Phase 9 WP-3c (design D-5, 追補 2 S-a/S-b; 監督裁定集約
    # rulings-r5-r6.md I-1): idempotency records, `public._mdb_idempotency`
    # (per-application upgrade 0010).
    #
    # Ruling U-7 (`{scratchpad}/review2/frame.md` F-①, WP-6d):
    # PRE-WP-6d, lookup/reap/count ran over `self._runtime` as a plain,
    # small, SELF-COMMITTING read/delete -- a SEPARATE transaction from
    # whichever connection the eventual WRITE later landed on
    # (`record_idempotency`, `self._runtime`; the 3 DDL methods' own
    # `idempotency_record` parameter, `self._developer`, via `_write_
    # idempotency_row`). That gap is exactly F-①'s race: two concurrent
    # requests for the SAME key each ran their own self-committing
    # lookup, both saw "no record", and both went on to execute.
    #
    # `idempotency_begin`/`idempotency_reserve` below REPLACE that
    # self-committing trio (`idempotency_get`/`idempotency_reap_expired`/
    # `idempotency_count`, removed) with two methods that run DIRECTLY on
    # a caller-supplied `conn` (code-review fix F6, Opus review 2, ruled
    # in -- see `idempotency_connection`'s own docstring below for why
    # this is passed through rather than resolved internally from a
    # `for_developer` flag as an earlier version of this fix did) --
    # `self._developer` or `self._runtime`, the SAME connection the
    # caller's own eventual write will later land on. Code-review fix F1
    # (Opus review 2, blocker) corrects what this paragraph used to claim
    # here: each method commits ITSELF, immediately, right after its own
    # reap/lookup or COUNT -- it does NOT stay open inside one
    # transaction shared with the caller's later write (on the `transact`
    # path, `cell.py`'s own `self._backend.begin(deadline=deadline)`,
    # called for pass 2 after this returns, opens with `self._runtime.
    # rollback()`, which silently discarded an uncommitted reap DELETE
    # here before this fix). What actually closes the SAME race a shared
    # transaction would have closed for r2db is the SESSION-scoped
    # `pg_advisory_lock` each method takes FIRST, before touching the
    # table -- not `pg_advisory_xact_lock` (a session lock, unlike a
    # transaction-scoped one, survives this method's own commit, so it
    # still spans the read and the later write) -- see each method's own
    # docstring for which lock and why. `cell.py`'s `_idempotency_check`
    # is the only caller, resolving `conn` once via `idempotency_
    # connection` (`for_developer=False`: `transact`, over `self.
    # _runtime`; `True`: `create_collection`/`add_field`/`alter_field`,
    # over `self._developer`) and threading that SAME handle through
    # `idempotency_begin`/`idempotency_reserve`/`idempotency_unlock`.
    # ------------------------------------------------------------------

    def idempotency_connection(self, *, for_developer=False):
        return self._developer if for_developer else self._runtime

    def _write_idempotency_row(self, conn, key, digest, response_json, now_ms):
        """Writes (or replaces) one record over `conn`'s OWN currently
        open transaction -- never commits/rolls back itself; the caller
        (either `record_idempotency` below, right before `self._runtime.
        commit()`, or a DDL method's own pre-commit point, right before
        `self._developer.commit()`) owns that. `ON CONFLICT ... DO UPDATE`
        (not a bare `INSERT`) so a stale, not-yet-reaped row for this
        exact key (a benign race -- the caller already confirmed no
        ACTIVE record exists before reaching this point) is replaced
        rather than raising `UniqueViolation`."""
        statement = sql.SQL(
            "INSERT INTO {} (key, digest, response_json, created_at_ms) VALUES (%s, %s, %s, %s) "
            "ON CONFLICT (key) DO UPDATE SET digest = EXCLUDED.digest, "
            "response_json = EXCLUDED.response_json, created_at_ms = EXCLUDED.created_at_ms"
        ).format(sql.Identifier(_IDEMPOTENCY_TABLE))
        with conn.cursor() as cur:
            _execute(cur, statement, [key, digest, response_json, now_ms])

    @_guard_pending_platform_upgrades
    def idempotency_begin(self, key, now_ms, retention_ms, *, conn, deadline=None):
        """Ruling U-7 (WP-6d): `conn` (code-review fix F6, Opus review 2,
        ruled in) is the WRITING connection this keyed entry point will
        eventually commit on -- resolved ONCE by the caller, via
        `idempotency_connection`, and passed through here rather than
        re-resolved internally (see that method's own docstring for why):
        `self._developer` for the 3 DDL methods, `self._runtime` for
        `transact` (default).

        `deadline` (code-review fix F2, Opus review 2, should-fix):
        without this, `pg_advisory_lock` below waits UNBOUNDED for a
        second process holding the same key's lock -- and since `cell.
        py` also holds this cell's own in-process `self._lock` (an
        `RLock`) for a keyed request's entire lookup -> execute -> store
        window, an unbounded wait here stalls every OTHER request this
        same cell would otherwise serve too, not merely this one key.
        `_timeout_ms(deadline)`/`_set_timeouts` (this class's own Phase 8
        WP-1a helpers, module comment above `_timeout_ms`) are reused
        here exactly as every other backend method already uses them --
        `SET LOCAL lock_timeout`/`statement_timeout`, scoped to this
        method's own transaction, bounding how long `pg_advisory_lock`
        may block before PostgreSQL cancels it (mirrors r2db-api's own
        `postgres.py::_set_timeouts` preceding its own lock acquisition).
        A timed-out lock wait raises `psycopg.errors.LockNotAvailable`/
        `QueryCanceled`, mapped below to `ResourceLimitError(limit_class=
        "execution_ms")` -- the SAME error class every other lock/
        statement-timeout site on this backend already maps to (`insert`/
        `update`/`delete_in_transaction` etc.), not a hang.

        M-1 (WP-6d, MitateDB-specific realization of U-7 -- CLAUDE.md
        "platform-specific controls may differ...when they provide the
        SAME required safety outcome"): `r2db-api`'s own U-7 fix uses a
        transaction-scoped `pg_advisory_xact_lock`, correct THERE
        because `r2db_api.postgres.PostgresCell` wraps an ENTIRE keyed
        request in ONE `with conn.transaction():` from lookup through
        store. This backend cannot do that: `field_domains`/`schema_
        revision` (and every other catalog read `cell.py` calls between
        the idempotency lookup and the eventual DDL/DML write) are each
        their OWN SELF-COMMITTING round trip on this SAME connection
        (measured: an xact lock taken here would be released the moment
        ANY one of those later self-commits, long before this key's own
        write). This method therefore takes a SESSION-scoped
        `pg_advisory_lock` instead -- released ONLY by an explicit
        `idempotency_unlock` call (`cell.py`'s `_idempotency_pg_scope`
        context manager calls it in a `finally`, guaranteeing release on
        EVERY exit: replay, CONFLICT, LIMIT_EXCEEDED, pass-1-equivalent
        validation failure, execution failure, or success) -- a session
        lock survives every intervening self-commit on this connection,
        closing the SAME race `pg_advisory_xact_lock` closes for r2db,
        by the SAME mechanism (a second concurrent request for the SAME
        key blocks here until the first's session releases it), just
        with an explicit instead of an implicit release point.

        Reaps expired records, then looks up `key`, over `conn`
        (whichever connection `idempotency_connection`'s own
        `for_developer` selected for this request) -- and commits
        immediately (code-review fix F1, Opus review 2): the read and
        the caller's later write do NOT share one transaction on the
        `transact` path (`for_developer=False`) -- `cell.py::transact`'s
        own `self._backend.begin(deadline=deadline)`, called for pass 2
        AFTER this method returns, opens with `self._runtime.rollback()`,
        which would silently discard this method's own reap DELETE if it
        were left uncommitted (measured: it did, before this fix -- see
        this method's own commit-site comment below for the concrete
        reproduction). What DOES span both this lookup and the caller's
        eventual write is the SESSION-scoped advisory lock taken above --
        a lock survives this commit (unlike an xact-scoped one), so a
        second concurrent request for the SAME key still blocks here
        until the first's `idempotency_unlock` releases it, restoring
        the SAME pre-WP-6d reap/serialization semantics this docstring's
        earlier "one transaction" wording incorrectly described.

        The lock key: two-int form (`_IDEMPOTENCY_KEY_LOCK_NAMESPACE`,
        `hashtext(key)`), not a bare `hashtext(key)::bigint` -- `hashtext`
        alone is only a 32-bit hash, so a bare-bigint lock would crowd
        every key's lock into the SAME narrow space `_IDEMPOTENCY_
        COUNT_ADVISORY_LOCK_KEY`/`ops.py::_RITUAL_ADVISORY_LOCK_KEY`
        also occupy; namespacing the high 32 bits keeps per-key locks
        visibly separate (mirrors `r2db-api`'s own identical reasoning).
        A `hashtext` collision between two DIFFERENT keys only over-
        serializes (accepted) -- it can never under-serialize. The DB
        is per-Application, so the raw key alone is Application-scoped
        already (I-5) -- no extra scoping component is needed.

        Returns `{"digest": str, "response_json": str}` for `key`, or
        `None` if this Application has no (unexpired) record for it --
        identical shape to the pre-WP-6d `idempotency_get` this method
        replaces (removed, along with `idempotency_reap_expired`, both
        folded in here so the lock/reap/lookup happen as one step,
        never as separate round trips a concurrent session could
        interleave between)."""
        timeout_ms = self._timeout_ms(deadline)
        try:
            with conn.cursor() as cur:
                # Code-review fix F2 (Opus review 2, should-fix): set
                # BEFORE acquiring the lock below -- see this method's
                # own docstring for why an unbounded wait here is worse
                # than on most other backend calls (it stalls this
                # cell's own in-process `self._lock` too).
                if timeout_ms is not None:
                    self._set_timeouts(cur, timeout_ms)
                _execute(cur, sql.SQL("SELECT pg_advisory_lock(%s, hashtext(%s))"),
                          [_IDEMPOTENCY_KEY_LOCK_NAMESPACE, key])
                _execute(cur, sql.SQL("DELETE FROM {} WHERE %s - created_at_ms > %s")
                          .format(sql.Identifier(_IDEMPOTENCY_TABLE)), [now_ms, retention_ms])
                _execute(cur, sql.SQL("SELECT digest, response_json FROM {} WHERE key = %s")
                          .format(sql.Identifier(_IDEMPOTENCY_TABLE)), [key])
                row = cur.fetchone()
            # Code-review fix F1 (Opus review 2, blocker): commit HERE,
            # immediately -- not left open for the caller's own eventual
            # commit/rollback as the docstring above used to claim. On
            # the `transact` path (`for_developer=False`), `cell.py`'s
            # `transact` calls `self._backend.begin(deadline=deadline)`
            # for pass 2 AFTER this method returns, and `begin()` opens
            # with `self._runtime.rollback()` (discarding whatever
            # uncommitted work sits on this connection) -- so leaving the
            # reap DELETE uncommitted here silently discarded it on every
            # keyed `transact` call (verified: `idempotency_retention_ms
            # =1`, two keyed transacts left BOTH keys' rows in the table,
            # never reaped -- on `main`, before WP-6d, the reap was its
            # own self-committing round trip and correctly left only the
            # new key's row). The SESSION advisory lock taken above is
            # untouched by this commit (`pg_advisory_lock`, not `_xact` --
            # a session lock survives commit/rollback on its own
            # connection, same as every self-committing catalog read
            # `cell.py` runs between this call and the eventual write);
            # it is what actually serializes a same-key race, not this
            # transaction boundary -- see this method's own docstring
            # above. Correct on the DDL path (`for_developer=True`,
            # `conn` is `self._developer`) too: that connection commits
            # once per DDL call already (`create_collection`/`add_field`/
            # `alter_field`'s own terminal `self._developer.commit()`),
            # so committing the reap+lookup here simply closes it out a
            # statement earlier than before, same as the `transact` path.
            conn.commit()
        except (psycopg.errors.QueryCanceled, psycopg.errors.LockNotAvailable):
            # Code-review fix F2: the SAME mapping every other lock/
            # statement-timeout site on this backend already uses
            # (`insert`/`update`/`delete_in_transaction` etc.) -- a
            # bounded wait for a same-key advisory lock that expires
            # surfaces as a real, classified `LIMIT_EXCEEDED` refusal,
            # never an unbounded hang.
            conn.rollback()
            raise ResourceLimitError("operation exceeds the execution budget", limit_class="execution_ms")
        except psycopg.Error as exc:
            conn.rollback()
            raise ValidationError("storage backend rejected the request") from exc
        if row is None:
            return None
        digest, response_json = row
        return {"digest": digest, "response_json": response_json}

    @_guard_pending_platform_upgrades
    def idempotency_reserve(self, *, conn, deadline=None):
        """Ruling U-7 (WP-6d): table-level, SESSION-scoped advisory
        lock (same `pg_advisory_lock`-not-`_xact` reasoning as
        `idempotency_begin` above -- self-commits between this COUNT
        and the eventual write would release an xact lock early too)
        serializing this COUNT-then-write across DIFFERENT keys (D-5
        (iii)). Released by the SAME `idempotency_unlock` call that
        releases `idempotency_begin`'s own per-key lock (`cell.py`'s
        `_idempotency_pg_scope`) -- unconditionally, whether or not this
        method was ever reached (a replay short-circuits before it;
        `pg_advisory_unlock` on a lock this session never took simply
        returns `false`, never an error). Replaces the pre-WP-6d
        self-committing `idempotency_count` (removed).

        `LOCK TABLE public.{_IDEMPOTENCY_TABLE} IN SHARE MODE` was
        considered and rejected for this purpose: two concurrent SHARE
        holders never conflict with EACH OTHER (SHARE only conflicts
        with ROW EXCLUSIVE and stronger), so both would pass the COUNT
        and only then deadlock against each other's own subsequent
        INSERT (which needs ROW EXCLUSIVE) -- see the WP-6d report for
        the Phase 9 R-2 precedent's own lock-mode finding.
        `pg_advisory_lock` has no such self-conflict-free class: a
        second holder of the SAME key always waits for the first.

        `deadline` (code-review fix F2, Opus review 2, should-fix):
        identical purpose as `idempotency_begin`'s own parameter of the
        same name -- bounds how long this method's own `pg_advisory_
        lock` (the table-level count lock, a DIFFERENT key than
        `idempotency_begin`'s per-key lock) may wait. `conn` (code-review
        fix F6): the SAME handle a paired `idempotency_begin` call in
        this same request already used -- see `idempotency_connection`'s
        own docstring for why this is passed through rather than
        re-resolved."""
        timeout_ms = self._timeout_ms(deadline)
        try:
            with conn.cursor() as cur:
                if timeout_ms is not None:
                    self._set_timeouts(cur, timeout_ms)
                _execute(cur, sql.SQL("SELECT pg_advisory_lock(%s)"), [_IDEMPOTENCY_COUNT_ADVISORY_LOCK_KEY])
                _execute(cur, sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(_IDEMPOTENCY_TABLE)))
                (count,) = cur.fetchone()
            # Code-review fix F1 (Opus review 2, blocker): commit HERE,
            # immediately, for the identical reason `idempotency_begin`
            # above now does -- this COUNT would otherwise sit open on
            # `conn` until the caller's own eventual commit/rollback,
            # and on the `transact` path that window is discarded by
            # `self._backend.begin(deadline=deadline)`'s own `self.
            # _runtime.rollback()` before it is ever reached. A bare
            # `SELECT count(*)` leaves nothing for that rollback to
            # discard either way (unlike `idempotency_begin`'s own
            # reap DELETE), so this commit is here for symmetry and to
            # close out the SESSION-scoped `pg_advisory_lock` acquired
            # above's surrounding transaction promptly, not because a
            # correctness bug was measured on this specific method.
            conn.commit()
        except (psycopg.errors.QueryCanceled, psycopg.errors.LockNotAvailable):
            # Code-review fix F2: same mapping as `idempotency_begin`
            # above -- see that method's own comment.
            conn.rollback()
            raise ResourceLimitError("operation exceeds the execution budget", limit_class="execution_ms")
        except psycopg.Error as exc:
            conn.rollback()
            raise ValidationError("storage backend rejected the request") from exc
        return count

    def idempotency_unlock(self, key, *, conn):
        """Ruling U-7 (WP-6d): releases BOTH session-scoped advisory
        locks `idempotency_begin`/`idempotency_reserve` above may have
        taken for THIS request, on `conn` -- always both, unconditionally
        (a lock never taken this session simply reports `false`,
        harmlessly). `conn` (code-review fix F6, Opus review 2, ruled in)
        is the SAME handle `idempotency_begin`/`idempotency_reserve`
        above used for THIS request -- `cell.py`'s `_idempotency_pg_
        scope` obtains it ONCE, from `idempotency_connection`, at
        scope-open, and passes it here too, rather than this method
        re-resolving `for_developer` independently (see `idempotency_
        connection`'s own docstring for why that distinction matters).
        Called from `_idempotency_pg_scope`'s own context manager, in a
        `finally`, so it runs on EVERY exit from a keyed critical
        section: replay, CONFLICT, LIMIT_EXCEEDED, a pass-1-equivalent
        validation failure, an execution failure, or success.

        `conn.rollback()` FIRST is not optional: an exception raised
        between `idempotency_begin` and here (a validation failure with
        no explicit rollback of its own -- unlike `transact`'s/each DDL
        method's own terminal `except psycopg.Error`/`except Exception`
        clause, which already rolls back before this ever runs) can
        leave `conn` in PostgreSQL's own aborted-transaction state,
        where EVERY further statement (including `pg_advisory_unlock`
        itself) is rejected until a `ROLLBACK`. This call is therefore
        always safe to reach in ANY state -- already clean (a no-op),
        merely open (discarded, matching every other failure path's own
        rollback), or aborted (cleared)."""
        conn.rollback()
        with conn.cursor() as cur:
            _execute(cur, sql.SQL("SELECT pg_advisory_unlock(%s, hashtext(%s))"),
                      [_IDEMPOTENCY_KEY_LOCK_NAMESPACE, key])
            _execute(cur, sql.SQL("SELECT pg_advisory_unlock(%s)"), [_IDEMPOTENCY_COUNT_ADVISORY_LOCK_KEY])
        conn.commit()

    @_guard_pending_platform_upgrades
    def record_idempotency(self, key, digest, response_json, now_ms):
        """`ApplicationCell.transact`'s own single-batch write path --
        called directly, immediately before `self._runtime.commit()`
        (the SAME connection/transaction the batch's own `..._in_
        transaction` DML calls already ran on, I-1); a failed batch never
        reaches this line (the caller's own execution loop raises first,
        never calling this method), so this write and the batch's own
        commit share the identical fate."""
        self._write_idempotency_row(self._runtime, key, digest, response_json, now_ms)

    def idempotency_discard_pending(self, key):
        """Phase 9 WP-3cd closure (K-5, N-8): a real no-op HERE -- unlike
        `SQLiteBackend`'s own private, non-transactional dict, this
        backend's `record_idempotency` above writes to the SAME real
        PostgreSQL connection/transaction `self.commit()`/`self.rollback
        ()` already govern, so a `self.commit()` failure's own `self.
        rollback()` already undoes the row this method would otherwise
        need to discard -- there is nothing left pending to clean up by
        the time `ApplicationCell.transact`'s `except Exception:` handler
        reaches this call. Declared (not simply inherited/omitted) so a
        future reader sees this backend was considered, not skipped."""
        return None
