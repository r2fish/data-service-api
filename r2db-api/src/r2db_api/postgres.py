"""`PostgresCell`: a `StorageBackend` (design D-1) over PostgreSQL via psycopg 3.

Design constraints this file is written to satisfy (design D-4):

- Values reach PostgreSQL exclusively through server-side bind parameters
  (via `psycopg.sql.Placeholder()` and a parameter list passed to
  `cursor.execute(...)`) or, for JSON-shaped values, `psycopg.types.json.Jsonb`
  -- never through string interpolation.
- Identifiers (table/column names) are composed only with `psycopg.sql.
  Identifier`, and only after (a) the shared syntax allowlist in
  `r2db_api.structured` and (b) verification against this application's
  *live* PostgreSQL catalog (`information_schema`), via `_load_catalog`.
  Syntax validation alone would still admit a well-formed but unknown
  identifier; the catalog check is what closes that gap.
- Operators and sort directions map to a fixed table of `sql.SQL` literals
  (`_COMPARISON_OPERATORS`); no operator string from a request is ever
  written into SQL text.
- No method on this class -- public or private -- accepts request-derived
  content and executes it as a `str`. `_run`, the single choke point every
  *client-influenced* statement passes through, is typed to accept only
  `psycopg.sql.Composed`/`psycopg.sql.SQL` and raises `TypeError` for
  anything else. Every SQL fragment built anywhere below that carries a
  client-supplied identifier/operator/value is constructed via
  `sql.SQL(...)`/`sql.Identifier`/`sql.Literal`/`sql.Placeholder`, never an
  f-string or `%`-formatted plain string, and never bypasses `_run`. The
  one exception, by design, not oversight: `_RolePool._liveness_check`'s
  pool-health probe (`cur.execute("SELECT 1")`) is a fixed, zero-argument
  literal with no request content anywhere near it -- a connection-pool
  implementation detail unrelated to any application-plane operation, and
  the only `.execute(...)` call in this file that does not go through
  `_run`.

This module does not duplicate validation. Identifier syntax, the operator
allowlist, mutation shape, and destructive-confirmation logic are imported
from `r2db_api.structured` and are the exact same functions `ApplicationCell`
uses -- see that module's "Shared validation/planning boundary" section.
This file only adds what is inherently PostgreSQL-specific: catalog lookup
against a live schema, SQL composition, session/transaction/timeout
handling, and per-role connection pooling.

Data model (CCR-13, docs/design/R2DB_CCR13_STORAGE_V1.md R-1/R-2/R-4/R-7):
`create_entity` always provisions a server-assigned `id bigint GENERATED
ALWAYS AS IDENTITY PRIMARY KEY` (the row address) and an invisible
`_r2db_revision uuid NOT NULL DEFAULT gen_random_uuid()` (the per-row
optimistic-concurrency token), ahead of the caller's own declared fields.
Those own fields default to `JSONB` (`create_entity` never carries a
`field_type` -- rejected at the shared `bind_schema_operation` boundary);
`add_field`'s own optional `field_type` maps `string`/`integer`/`number`/
`boolean` to `TEXT`/`BIGINT`/`DOUBLE PRECISION`/`BOOLEAN` respectively, and
`object`/`array` to the two DOMAINs `migrations/0003_provision_application.
sql` provisions per application database, `_r2db_json_object`/
`_r2db_json_array` -- each a `jsonb` DOMAIN with a `jsonb_typeof(VALUE)`
CHECK, so PostgreSQL's own catalog (`information_schema.columns.
domain_name`) is what lets `_load_catalog` tell "declared as object" apart
from "declared as array" apart from "untyped JSONB" (WP-3 review, "object/
array の DOMAIN 型統一": a bare `jsonb` column cannot report this
distinction at all). `id`/`_r2db_revision` require PostgreSQL 13+
(`gen_random_uuid()` is a built-in as of that version).

Two layers validate a value written to an `object`/`array` column: `_check_
type` (shared with `ApplicationCell`, `r2db_api.structured`) refuses a
non-dict/non-list value with `VALIDATION_FAILED` naming only the field --
this is what a well-behaved client actually sees. The DOMAIN's own
`jsonb_typeof` CHECK is a second, defence-in-depth layer underneath that:
a real server-side invariant that should never fire if `_check_type` is
doing its job, so a CHECK violation is left to fall through to this
module's ordinary `SERVICE_UNAVAILABLE` mapping (a true "this should never
happen" backstop, not a validation response) rather than being decoded and
re-surfaced as a second `VALIDATION_FAILED` path.

Two legitimate, accepted cross-backend semantic differences remain: an
untyped (JSONB) column has no per-column type in the shared `r2db_api.
structured` vocabulary (`None`), so `lt`/`lte`/`gt`/`gte` comparisons that
would raise `TypeError` against mismatched Python types in `ApplicationCell`
typically do not raise here -- PostgreSQL's own jsonb ordering is total
across JSON types, producing a deterministic (if occasionally surprising)
`ORDER`-consistent boolean instead. And a `jsonb` (or `_r2db_json_object`/
`_r2db_json_array`-domain) column's own storage normalizes the value it is
given -- an object's key order is not the order it was written in JSON
source (PostgreSQL's own `(byte length, byte value)` order, `r2db_api.
structured._jsonb_text` reproduces this for `contains`/`matches`'s own
text-form comparison, WP-3 review N-1/N-2), and a duplicate key collapses
to its last-written value, silently, the same way a plain Python `dict`
literal with a repeated key would -- `ApplicationCell`, storing the Python
value directly with no serialization round-trip, does not normalize either
of these at write time, though a query response's item order/shape is
otherwise identical between the two backends for every value this
contract's type vocabulary can express. Both are what the Security
Invariants allow (implementations are not required to share a physical
data model), not validation gaps: both backends still reject bad
identifiers/operators/shapes, and the exact same errors/precedence for
every other checked property (addressability, uniqueness, revision
preconditions, `contains`/`matches` literal/wildcard semantics against
SQL's own three-valued logic, and object/array typing), identically.
"""
from __future__ import annotations

import os
import queue
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Callable, Iterator, Sequence

import psycopg
from psycopg import sql
from psycopg.pq import TransactionStatus
from psycopg.types.json import Jsonb

from .audit_hook import ApplicationAuditHook
from .backend import StorageBackend as _StorageBackend
from .errors import fail
from .limits import ResourceLimits
from .structured import (
    BoundMutation,
    MutationOutcome,
    Predicate,
    QueryOutcome,
    _check_type,
    _decode_cursor,
    _encode_cursor,
    _resolve_order_by,
    _shape_hash,
    _validate_predicate_types,
    _reject_reserved_entity_name,
    bind_mutation,
    bind_schema_operation,
    delete_confirmation_phrase,
    drop_entity_confirmation_phrase,
    drop_index_confirmation_phrase,
    require_destructive_confirmation,
    validate_identifier,
    validate_page_size,
    validate_predicates,
    validate_projection,
)

_REVISION_TABLE = "_r2db_schema_revision"
# Contract 1.1.0 (CCR-13, docs/design/R2DB_CCR13_STORAGE_V1.md R-1/R-3/R-4):
# every entity table this backend creates now carries a server-assigned
# `id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY` (the row address) and
# an invisible `_r2db_revision uuid` column (the per-row optimistic-
# concurrency token) alongside its declared JSONB/typed fields.
_ID_COLUMN = "id"
_REVISION_COLUMN = "_r2db_revision"
_RESERVED_INTERNAL_PREFIX = "_r2db"

# R-2/R-7: `add_field`'s `field_type` maps to a real PostgreSQL column
# type; `create_entity`'s own fields (which never carry a `field_type` --
# rejected at the shared `bind_schema_operation` boundary) and an
# `add_field` with no `field_type` both keep the pre-CCR-13 default, JSONB.
# `object`/`array` map to the two DOMAINs `migrations/0003_provision_
# application.sql` provisions in every application database (WP-3 review,
# "object/array の DOMAIN 型統一") -- not bare `JSONB`, which cannot report
# which of the two a column was declared as. `sql.Identifier` (not
# `sql.SQL`) is used for these two: they are catalog objects (domain
# names), not built-in type keywords.
_FIELD_TYPE_SQL: dict[str, "sql.SQL | sql.Identifier"] = {
    "string": sql.SQL("TEXT"),
    "integer": sql.SQL("BIGINT"),
    "number": sql.SQL("DOUBLE PRECISION"),
    "boolean": sql.SQL("BOOLEAN"),
    "object": sql.Identifier("_r2db_json_object"),
    "array": sql.Identifier("_r2db_json_array"),
}
_JSONB_SQL = sql.SQL("JSONB")

# The two DOMAIN types' own bare names (as `information_schema.columns.
# domain_name` reports them -- unqualified, WP-3 review confirmed
# empirically), mapped back to the shared `r2db_api.structured` vocabulary
# string `_load_catalog` reports for such a column's declared type.
_DOMAIN_TO_DECLARED: dict[str, str] = {
    "_r2db_json_object": "object",
    "_r2db_json_array": "array",
}

# The inverse mapping, used by `_load_catalog` to recover each column's
# declared type (in the shared `r2db_api.structured` vocabulary: "string"/
# "integer"/"number"/"boolean", or `None` for untyped/JSONB-equivalent) from
# PostgreSQL's own `information_schema.columns.data_type` reporting, for a
# column that is *not* one of the two DOMAINs above (`_DOMAIN_TO_DECLARED`
# is consulted first -- see `_load_catalog`). `id` also happens to be
# `bigint` (looked up through this same table -- it is not a distinct
# physical type from a user-declared `field_type: "integer"` column, only a
# distinct *role*, which `_load_catalog` tracks separately).
_SQL_TYPE_TO_DECLARED: dict[str, str] = {
    "text": "string",
    "bigint": "integer",
    "double precision": "number",
    "boolean": "boolean",
}

# `_RolePool`'s own bounded-wait defaults (review fix: neither of these
# existed before -- a connect attempt against an unreachable target had no
# timeout at all, and a caller waiting for a pooled connection to free up
# waited on `queue.Queue.get()` with no timeout either). Both are
# constructor parameters, not environment-tunable knobs like `R2DB_POOL_*`
# below: they bound worst-case latency for a single acquisition, not
# steady-state pool sizing, and a caller (a test, most concretely) that
# needs a different value passes it directly to `_RolePool`/`PostgresCell`/
# `PostgresCredentialStore`.
_DEFAULT_CONNECT_TIMEOUT_S = 5
_DEFAULT_ACQUIRE_TIMEOUT_S = 10.0

_COMPARISON_OPERATORS: dict[str, sql.SQL] = {
    "eq": sql.SQL("="),
    "ne": sql.SQL("<>"),
    "lt": sql.SQL("<"),
    "lte": sql.SQL("<="),
    "gt": sql.SQL(">"),
    "gte": sql.SQL(">="),
}


def _escape_like_literal(value: str) -> str:
    """Q-2 (案i): `contains` is literal substring containment -- no
    character of the value is ever interpreted as a `LIKE` wildcard. `\\`
    must be escaped first, before `%`/`_`, so a value already containing a
    backslash does not have that backslash re-interpreted as escaping the
    `%`/`_` markers this function itself inserts.
    """
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@dataclass
class _TableInfo:
    """One entity table's live shape, as re-derived from PostgreSQL's own
    catalog by `PostgresCell._load_catalog` on every call (never cached
    across calls, never trusted as a standing assumption -- D-4/R-1).

    `columns`: declared field name -> declared type in the shared
    `r2db_api.structured` vocabulary (`"string"`/`"integer"`/`"number"`/
    `"boolean"`/`"object"`/`"array"`), or `None` for an untyped/JSONB-
    equivalent column. `"object"`/`"array"` are recovered from PostgreSQL's
    own `information_schema.columns.domain_name` (WP-3 review, "object/
    array の DOMAIN 型統一") -- a plain `jsonb` column with no domain
    reports `None`. Includes `"id"` (always `"integer"`); never includes
    the invisible `"_r2db_revision"` column (R-3/R-4).

    `indexes`: client index name -> `{"physical": <table>__<index> name,
    "fields": (declared field name, ...), "unique": bool}`, covering every
    index `PostgresCell.apply_schema`'s own `create_index` has created on
    this table (both unique and non-unique -- SI-08/R-5: both count toward
    `schema_objects`), excluding the primary key on `id` (R-1/§2: an
    address, not a domain uniqueness declaration).
    """

    columns: dict[str, str | None]
    indexes: dict[str, dict[str, Any]]


def _run(cursor: "psycopg.Cursor[Any]", statement: sql.Composed | sql.SQL, params: Sequence[Any] = ()) -> None:
    """The single execution choke point. Typed to accept only a composed
    psycopg SQL object -- never `str` -- so a raw string cannot reach the
    database from anywhere in this file, as a checked property rather than a
    convention (design D-4).
    """
    if not isinstance(statement, (sql.Composed, sql.SQL)):
        raise TypeError("PostgresCell only executes psycopg.sql.Composed/SQL objects, never str")
    cursor.execute(statement, list(params))


class _RolePool:
    """A small connection pool dedicated to exactly one (login role,
    database, schema) triple.

    Design D-3 calls out a specific hazard: a pool shared across roles that
    uses `SET ROLE`/`search_path` per checkout leaks the previous borrower's
    authority into the next one if the release-time reset is ever missed.
    This class avoids that hazard structurally rather than by remembering to
    reset: every connection this pool ever hands out is opened with
    `psycopg.connect(dsn)` where `dsn` already authenticates as one fixed
    role, and `search_path` is set exactly once, at connection-open time, to
    one fixed schema -- never touched again for that connection's lifetime,
    and never reused by a different role or a different application (each
    `PostgresCell` owns its own pools). There is no `SET ROLE` anywhere in
    this file. A role switch on a shared connection simply never happens, so
    there is nothing to reset and nothing to forget to reset.

    `r2db_api/tests/test_postgres.py::test_pool_never_leaks_role_or_schema_
    across_applications` is the executable check for this: it interleaves
    heavy use of two applications' pools and asserts every connection drawn
    from either one reports its own fixed role/schema, never the other's.
    """

    def __init__(self, dsn: str, *, schema: str, maxconn: int = 4, connect_timeout: int = _DEFAULT_CONNECT_TIMEOUT_S, acquire_timeout: float = _DEFAULT_ACQUIRE_TIMEOUT_S, statement_timeout_ms: int | None = None, idle_in_transaction_session_timeout_ms: int | None = None) -> None:
        self._dsn = dsn
        self._schema = schema
        self._maxconn = max(1, maxconn)
        self._queue: "queue.Queue[psycopg.Connection[Any]]" = queue.Queue(maxsize=self._maxconn)
        self._lock = threading.Lock()
        self._created = 0
        self._connect_timeout = connect_timeout
        self._acquire_timeout = acquire_timeout
        # Phase 4 (design PHASE4_DURABLE_AUDIT_SINK_V1.md D-6/N-3): SESSION-
        # level (not `SET LOCAL` -- these must survive for this connection's
        # entire lifetime, not just one transaction, unlike `PostgresCell.
        # _set_timeouts`'s per-request `SET LOCAL`) `statement_timeout`/
        # `idle_in_transaction_session_timeout`, set once at connect time
        # (below) and never touched again. `None` (the default -- every
        # `_RolePool` caller except the two audit-writer sinks) means "do
        # not set either" -- this pool is otherwise used for ordinary
        # application data-plane connections, which must not silently
        # acquire a new timeout policy as a side effect of this WP. Only
        # `PostgresApplicationAuditSink`/`PostgresControlAuditSink`
        # (`credential_store.py`) pass a concrete value here: D-6's
        # visibility-lag derivation (`statement_timeout +
        # idle_in_transaction_session_timeout + 1s`) depends on both being
        # enforced on the connection that writes `application_audit`/
        # `control_audit`, never on an unrelated pool silently inheriting
        # them.
        self._statement_timeout_ms = statement_timeout_ms
        self._idle_in_transaction_session_timeout_ms = idle_in_transaction_session_timeout_ms
        # Set by `retire()` (called only by `SharedPoolManager`, below, when
        # this pool is evicted -- idle timeout or LRU cap). A retired pool
        # keeps serving any connection a caller already checked out (see
        # `connection()`'s `finally` below), it simply never re-queues one on
        # return; the pool drains to zero connections and stops being handed
        # out for new acquisitions once every outstanding checkout returns.
        self._retired = False

    def _connect(self) -> "psycopg.Connection[Any]":
        # `connect_timeout` (a real libpq connection parameter, merged into
        # `self._dsn`'s already-parsed conninfo by `psycopg.connect`'s own
        # kwargs-override-conninfo behaviour) bounds how long a single
        # connect attempt can take against an unreachable/blackholed target.
        # Without this, a target that never responds at the TCP level (as
        # opposed to an immediate `ECONNREFUSED`) can block for the
        # platform's default TCP connect timeout -- minutes, not seconds --
        # which is exactly the kind of unbounded wait `_acquire` below must
        # not be exposed to while holding `self._lock` (see that method's
        # own comment on why `_connect()` is never called under the lock).
        conn = psycopg.connect(self._dsn, autocommit=False, connect_timeout=self._connect_timeout)
        with conn.cursor() as cur:
            _run(cur, sql.SQL("SET search_path TO {}").format(sql.Identifier(self._schema)))
            # Phase 4 (design D-6/N-3): SESSION-level, set once here (never
            # `SET LOCAL` -- unlike `PostgresCell._set_timeouts`'s
            # per-request `SET LOCAL statement_timeout`, this must survive
            # every transaction this pooled connection is ever reused for,
            # for its entire lifetime -- this connection is never reused by
            # a different role/purpose, `_RolePool`'s own class docstring).
            # `SHOW statement_timeout`/`SHOW idle_in_transaction_session_
            # timeout` against a connection from this pool is the executable
            # check (`r2db-api/tests/test_application_audit.py::test_audit_
            # write_connections_have_statement_and_idle_in_transaction_
            # timeouts_set`).
            if self._statement_timeout_ms is not None:
                _run(cur, sql.SQL("SET SESSION statement_timeout = {t}").format(t=sql.Literal(f"{self._statement_timeout_ms}ms")))
            if self._idle_in_transaction_session_timeout_ms is not None:
                _run(cur, sql.SQL("SET SESSION idle_in_transaction_session_timeout = {t}").format(t=sql.Literal(f"{self._idle_in_transaction_session_timeout_ms}ms")))
        conn.commit()
        return conn

    def _acquire(self) -> "psycopg.Connection[Any]":
        try:
            return self._queue.get_nowait()
        except queue.Empty:
            pass
        # Reserve a slot (increment `_created`) and release the lock
        # *before* calling `_connect()` -- a real, previously-shipped bug
        # this class had: `_connect()` used to run while `self._lock` was
        # held, so every thread contending for a new connection against an
        # unreachable target serialized on this lock for the full connect
        # attempt, and a failed `_connect()` never rolled its reservation
        # back. `maxconn` consecutive failures against an unreachable
        # target therefore permanently pinned `_created` at `maxconn`, so
        # every later `_acquire()` call fell straight through to the
        # untimed `self._queue.get()` below and blocked forever -- even
        # once the target became reachable again, since nothing ever put a
        # connection back on this empty queue. `r2db_api/tests/
        # test_postgres.py::test_role_pool_recovers_after_connect_failures_
        # are_exhausted_and_target_becomes_reachable` and
        # `test_credential_persistence.py::
        # test_authenticate_never_hangs_across_repeated_pool_exhaustion_and_
        # recovers_once_reachable` are the executable checks for this fix.
        reserved = False
        with self._lock:
            if self._created < self._maxconn:
                self._created += 1
                reserved = True
        if reserved:
            try:
                return self._connect()
            except Exception:
                with self._lock:
                    self._created = max(0, self._created - 1)
                raise
        # Every slot is claimed by a connection some other caller currently
        # holds (or that is itself mid-`_connect()` on another thread) --
        # wait for one to be returned, but never unboundedly: a
        # `queue.Empty` here (nothing returned within `acquire_timeout`) is
        # re-raised as a `psycopg.OperationalError`, the same exception
        # type an actual failed connection attempt would raise, so every
        # existing `except psycopg.Error` call site in this file and in
        # `r2db_api.credential_store` already handles it correctly (fail-
        # closed to `SERVICE_UNAVAILABLE`/`AUTH_STATE_UNAVAILABLE`, never a
        # silent hang).
        try:
            return self._queue.get(timeout=self._acquire_timeout)
        except queue.Empty:
            raise psycopg.OperationalError(
                f"timed out after {self._acquire_timeout}s waiting for an available pooled connection (pool exhausted at maxconn={self._maxconn})"
            )

    def _liveness_check(self, conn: "psycopg.Connection[Any]") -> bool:
        """`pool_pre_ping` equivalent: a connection dequeued from `self._
        queue` may have been sitting idle long enough for the *server* to
        have terminated it (an operator's `pg_terminate_backend`, an idle
        session timeout, a network blip) without the client-side socket
        ever observing that -- `psycopg.Connection.closed` stays `0` in
        that case until something actually tries to use the connection.
        Checking `conn.closed` alone therefore misses exactly the failure
        mode a pool most needs to catch. This runs one cheap round trip
        (`SELECT 1`) on every checkout and reports whether the connection is
        actually usable; a dead connection is closed here (the caller is
        responsible for replacing it, not for reusing it in this state).
        """
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
            # A `SELECT` inside `autocommit=False` opens a transaction; roll
            # it back immediately so the connection is handed to the caller
            # IDLE, exactly as `_connect()` leaves a freshly opened one --
            # the ping itself must be invisible to whatever runs next.
            conn.rollback()
            return True
        except Exception:
            try:
                conn.close()
            except Exception:
                pass
            return False

    @contextmanager
    def connection(self) -> Iterator["psycopg.Connection[Any]"]:
        conn = self._acquire()
        try:
            if conn.closed or not self._liveness_check(conn):
                conn = self._connect()
            yield conn
        finally:
            # No `return` (or any other flow-control statement) anywhere in
            # this block: inside a generator's `finally`, `return` silently
            # swallows whatever exception was propagating through `yield`
            # above -- a real bug caught by this file's own tests (a
            # `FoundationError` raised by the caller was being discarded
            # instead of reaching them). Recycling the connection is
            # therefore expressed as a plain if/else with no early exit, so
            # an exception from the `try` block always continues propagating
            # once this `finally` finishes.
            keep = True
            try:
                if conn.closed:
                    keep = False
                elif conn.info.transaction_status != TransactionStatus.IDLE:
                    # Defence in depth: even though `conn.transaction()`
                    # leaves connections IDLE on both success and exception,
                    # a connection is never returned to the pool mid
                    # transaction. Nothing about role/schema is touched here.
                    conn.rollback()
            except Exception:
                keep = False
            with self._lock:
                retired = self._retired
            recycled = False
            if keep and not retired and not conn.closed:
                try:
                    self._queue.put_nowait(conn)
                    recycled = True
                except queue.Full:
                    recycled = False
            if not recycled:
                try:
                    conn.close()
                except Exception:
                    pass
                with self._lock:
                    self._created = max(0, self._created - 1)

    def close_all(self) -> None:
        while True:
            try:
                conn = self._queue.get_nowait()
            except queue.Empty:
                break
            try:
                conn.close()
            except Exception:
                pass
        with self._lock:
            self._created = 0

    def retire(self) -> None:
        """Take this pool permanently out of service: called only by
        `SharedPoolManager` when this pool is evicted (idle timeout or LRU
        cap), never by `PostgresCell` directly. Every connection currently
        sitting idle in the queue is closed immediately -- those are safe to
        drop right now. Any connection presently checked out by a caller
        (mid-query, mid-transaction) is left completely alone here: closing
        it out from under an in-flight operation is exactly the "random
        failure under load" hazard this method exists to avoid. Setting
        `self._retired` instead makes `connection()`'s own `finally` block
        (above) close that connection -- instead of re-queuing it -- the
        moment its caller returns it normally, which is the only place a
        checked-out connection is ever safe to retire.
        """
        with self._lock:
            self._retired = True
        self.close_all()


def _env_int(name: str, default: int) -> int:
    """Read an `int`-valued setting the way the rest of this package does
    (`R2DB_`-prefixed environment variables, e.g. `R2DB_CREDENTIAL_PEPPER`
    in `auth.py`) -- a bare `os.environ.get` rather than a `pydantic`
    settings object, since this package (unlike the SQLAlchemy-based
    reference implementation this design is adapted from) has no
    `Settings`/`get_settings()` of its own. An unset, empty, or unparsable
    value silently falls back to `default` rather than raising: these are
    pool-tuning knobs, not required configuration, and a malformed value at
    startup should degrade to a sane default, not crash the process.
    """
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass
class _PoolManagerEntry:
    pool: "_RolePool"
    last_used: float


class SharedPoolManager:
    """The fix for this module's connection-pooling defect: a single,
    process-wide cache of `_RolePool` instances keyed by `(application_id,
    role)`, shared across every `PostgresCell` -- not one pair of pools per
    cell, held forever, as before.

    Design, adapted from the currently deployed reference implementation
    (`r2-vps/apps/r2db-api/src/r2db_api/pools.py::AppPoolManager`, a
    SQLAlchemy engine cache with the same two properties) to this package's
    hand-rolled psycopg pooling:

    - **Idle eviction.** A pool unused for `R2DB_POOL_IDLE_SECONDS` (default
      300) is retired the next time *any* key is looked up here -- eviction
      is swept lazily, on access, exactly like the reference implementation,
      not on a background timer.
    - **An LRU cap on live pools (`R2DB_POOL_CACHE_MAX`, default 32).** This
      is the property that actually decouples the connection ceiling from
      the number of applications: `PostgresCell.__init__` no longer creates
      a pool eagerly at all, it only registers a `(dsn, schema, maxconn)`
      recipe with this manager and asks for the live pool by key on every
      use (`_PoolHandle`, below). However many applications exist, at most
      `cache_max` *pools* are ever open at once, each capped at
      `maxconn` connections (default `R2DB_POOL_SIZE + R2DB_POOL_MAX_
      OVERFLOW` = 2 + 2 = 4, matching the reference implementation's
      effective per-application capacity) -- an absolute ceiling of
      `cache_max * maxconn` connections cluster-wide (default 32 * 4 = 128,
      itself still an operator-facing figure to size against `max_
      connections`, but no longer one that grows with application count).

    Eviction never closes a connection a caller currently has checked out
    -- see `_RolePool.retire()`. It closes idle connections in the pool's
    queue immediately and lets any in-flight one finish and be closed on
    return.

    A default instance (`default_pool_manager`, below) is what `PostgresCell`
    uses when no `pool_manager` is supplied, so this behaves as a drop-in
    fix with no caller changes required. Tests (and any caller that wants
    isolated pool-cache behaviour, e.g. a short idle interval to make
    eviction observable) construct their own `SharedPoolManager` and pass it
    to `PostgresCell(..., pool_manager=...)` explicitly.
    """

    def __init__(self, *, idle_seconds: int | None = None, cache_max: int | None = None, pool_size: int | None = None, pool_max_overflow: int | None = None) -> None:
        self._lock = threading.Lock()
        self._entries: dict[tuple[str, str], _PoolManagerEntry] = {}
        self._idle_seconds = idle_seconds if idle_seconds is not None else _env_int("R2DB_POOL_IDLE_SECONDS", 300)
        self._cache_max = max(1, cache_max if cache_max is not None else _env_int("R2DB_POOL_CACHE_MAX", 32))
        base = pool_size if pool_size is not None else _env_int("R2DB_POOL_SIZE", 2)
        overflow = pool_max_overflow if pool_max_overflow is not None else _env_int("R2DB_POOL_MAX_OVERFLOW", 2)
        self._default_maxconn = max(1, base + overflow)

    def _evict_locked(self, now: float) -> None:
        """Called at the top of every `get_pool()`, under `self._lock`
        (mirrors `AppPoolManager._evict_idle_locked`): first retire every
        pool idle longer than `self._idle_seconds`, then -- independently --
        retire the least-recently-used pool(s) until at most `self._cache_
        max` remain. The two sweeps are separate passes for the same reason
        the reference implementation keeps them separate: an application
        that is still within its idle window but pushed out by the cap is a
        different, and more important, condition than one that simply went
        quiet -- the cap is what actually bounds total connections
        regardless of how many applications exist, per this class's
        docstring.
        """
        stale = [key for key, entry in self._entries.items() if now - entry.last_used > self._idle_seconds]
        for key in stale:
            entry = self._entries.pop(key)
            entry.pool.retire()

        while len(self._entries) > self._cache_max:
            oldest_key = min(self._entries.items(), key=lambda item: item[1].last_used)[0]
            entry = self._entries.pop(oldest_key)
            entry.pool.retire()

    def get_pool(self, key: tuple[str, str], dsn: str, *, schema: str, maxconn: int | None = None) -> "_RolePool":
        """Return the live pool for `key`, creating one (lazily, as before)
        if none is cached, and refresh its recency so it survives the next
        idle sweep. `dsn`/`schema`/`maxconn` are only consulted the moment a
        pool is (re)created for this key -- once cached, a lookup for the
        same key returns the existing pool as-is, exactly like the
        reference implementation, which also only reads its connection
        settings at first creation for a given key.
        """
        now = time.monotonic()
        with self._lock:
            self._evict_locked(now)
            entry = self._entries.get(key)
            if entry is not None:
                entry.last_used = now
                return entry.pool
            pool = _RolePool(dsn, schema=schema, maxconn=maxconn if maxconn is not None else self._default_maxconn)
            self._entries[key] = _PoolManagerEntry(pool=pool, last_used=now)
            return pool

    def release(self, key: tuple[str, str]) -> None:
        """Explicitly retire and drop the cached pool for `key`, if any --
        called by `PostgresCell.close()` (via `_PoolHandle.close()`). This is
        distinct from idle/LRU eviction (which only ever runs as a side
        effect of some *other* key's `get_pool()` call): closing a cell is an
        immediate, caller-driven release of exactly its own two pools,
        independent of this manager's lazy sweep and of whatever else is
        cached for other applications.
        """
        with self._lock:
            entry = self._entries.pop(key, None)
        if entry is not None:
            entry.pool.retire()

    def dispose_all(self) -> None:
        """Retire every cached pool right now, regardless of key. Intended
        for process shutdown / test-suite teardown, not for routine use --
        routine release of one application's pools is `release()`, above."""
        with self._lock:
            entries = list(self._entries.values())
            self._entries.clear()
        for entry in entries:
            entry.pool.retire()


class _PoolHandle:
    """`PostgresCell`'s own `self._runtime`/`self._developer` attribute: a
    thin, stateless-between-calls handle that resolves the live `_RolePool`
    from `SharedPoolManager` on every `.connection()` call rather than
    holding a direct reference to one pool for the cell's whole lifetime.
    That indirection is what makes eviction and recreation transparent to
    `PostgresCell` and its callers: if the pool behind this key was retired
    (idle timeout or LRU cap) since the last call, the next `.connection()`
    simply gets a freshly created one back from the manager -- same `dsn`/
    `schema`, so it authenticates as exactly the same single fixed role as
    before (D-3/§10.1: still no `SET ROLE`, still one role per pool) -- with
    no special handling required here or in `PostgresCell`.
    """

    def __init__(self, manager: SharedPoolManager, key: tuple[str, str], dsn: str, schema: str, maxconn: int | None) -> None:
        self._manager = manager
        self._key = key
        self._dsn = dsn
        self._schema = schema
        self._maxconn = maxconn

    @contextmanager
    def connection(self) -> Iterator["psycopg.Connection[Any]"]:
        pool = self._manager.get_pool(self._key, self._dsn, schema=self._schema, maxconn=self._maxconn)
        with pool.connection() as conn:
            yield conn

    def close(self) -> None:
        self._manager.release(self._key)


# The process-wide default `PostgresCell` uses when no `pool_manager` is
# supplied explicitly -- constructed once at import time, reading
# `R2DB_POOL_*` from the environment then (§ SharedPoolManager docstring).
# Sized (and shaped) so the total ceiling stops scaling with the number of
# applications; see `r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md` §4 for
# the resulting bounded arithmetic and how to size it for a given cluster.
default_pool_manager = SharedPoolManager()


class PostgresCell:
    """A `StorageBackend` over one application's own PostgreSQL database
    (architecture §8, "D-3 改訂": database-per-application, not
    schema-per-application -- each application's entities live in that
    database's `public` schema; `schema` below is `"public"` for every
    application, and the isolation boundary is which *database* a
    connection's DSN names, not a schema name inside a shared one).

    `application_id` and `schema` are supplied by the caller (the control
    plane), never derived from client request content (D-3: "the physical
    namespace is assigned by the control plane, not derived from client
    input" -- true of both the database name and the schema name within
    it). `runtime_dsn`/`developer_dsn` are two separate, already
    fully-formed connection strings authenticating as this application's
    `runtime` and `developer` PostgreSQL roles respectively, each already
    naming this application's own database (provisioned by
    `r2db-api/migrations/`, see `r2db-api/docs/`); this class never embeds a
    control-plane credential and never widens a connection's role at
    runtime, so schema-changing operations physically execute under the
    `developer` role (DDL-capable on this database's `public` schema only)
    while queries and data mutations physically execute under the `runtime`
    role (DML only) -- a second, DB-enforced layer under the `developer:
    bool` check already performed by `bind_schema_operation` (SI-03
    defence in depth).

    Connection pooling (D-3/§10.1, and the fix this class's `_runtime`/
    `_developer` attributes are part of): each is a `_PoolHandle` onto a
    pool owned by `pool_manager` -- `default_pool_manager` (module-level, a
    single process-wide `SharedPoolManager`) unless a caller supplies its
    own, e.g. a test that wants an isolated cache with a short idle
    interval. No pool is created here at construction time; `PostgresCell`
    itself now holds nothing heavier than DSNs and a pool-cache key
    (`application_id`, role) until something actually calls `.connection()`.
    Because the cache is shared across every `PostgresCell` instance rather
    than private to each one, the number of live pools is bounded by
    `pool_manager`'s own cap regardless of how many applications exist --
    see `SharedPoolManager`'s docstring and `r2db-api/docs/
    POSTGRES_PROVISIONING_RUNBOOK.md` §4 for the resulting arithmetic.
    `pool_size`, same as before, is this cell's own requested per-pool
    connection cap (`None` defers to `pool_manager`'s configured default,
    itself `R2DB_POOL_SIZE + R2DB_POOL_MAX_OVERFLOW` unless overridden) --
    it is only consulted the moment a pool is actually (re)created for this
    cell's key, exactly like every other pool setting here.
    """

    def __init__(self, application_id: str, schema: str, *, runtime_dsn: str, developer_dsn: str, runtime_role: str, developer_role: str, pool_size: int | None = None, pool_manager: SharedPoolManager | None = None) -> None:
        validate_identifier(schema)
        self.application_id = application_id
        self.schema = schema
        # Role *names* (not credentials) are needed at table-creation time to
        # embed the RLS policy (see `_create_entity`): D-3's third,
        # defence-in-depth layer, on top of schema separation and the two
        # distinct DB roles. They are control-plane-assigned constants, the
        # same trust level as `schema` above -- never taken from a client
        # request.
        validate_identifier(runtime_role)
        validate_identifier(developer_role)
        self._runtime_role = runtime_role
        self._developer_role = developer_role
        manager = pool_manager if pool_manager is not None else default_pool_manager
        self._pool_manager = manager
        self._runtime = _PoolHandle(manager, (application_id, "runtime"), runtime_dsn, schema, pool_size)
        self._developer = _PoolHandle(manager, (application_id, "developer"), developer_dsn, schema, pool_size)

    def close(self) -> None:
        """Release this cell's own two pools back to the shared manager
        (`SharedPoolManager.release`, via `_PoolHandle.close`) -- retiring
        them immediately rather than waiting for idle/LRU eviction. This
        matters beyond tidiness: `application_id` is a cache key this
        manager is shared on, and a caller that deprovisions this
        application (dropping its database/roles) and later reprovisions
        the *same* `application_id` must not have a new `PostgresCell` for
        it silently hand back a stale pool of connections authenticated
        against credentials that no longer exist.
        """
        self._runtime.close()
        self._developer.close()

    # ---- catalog -----------------------------------------------------

    def catalog(self) -> list[dict[str, Any]]:
        with self._runtime.connection() as conn:
            with conn.transaction():
                info = self._load_catalog(conn)
        result: list[dict[str, Any]] = []
        for name in sorted(info):
            table_info = info[name]
            unique_keys = [
                {"name": index_name, "fields": list(index_info["fields"])}
                for index_name, index_info in sorted(table_info.indexes.items())
                if index_info["unique"]
            ]
            result.append(
                {
                    "entity": name,
                    "fields": sorted(table_info.columns),
                    # R-1/R-2/§2: every entity this backend provisions is
                    # server-addressed, mutable, and never reuses an
                    # address within one entity's lifetime -- there is no
                    # per-entity toggle for any of this (R-1: "クライアント
                    # は区分を選べない").
                    "mutation_class": "mutable",
                    "address_fields": [_ID_COLUMN],
                    "address_reuse": "never",
                    "unique_keys": unique_keys,
                }
            )
        return result

    def _load_catalog(self, conn: "psycopg.Connection[Any]") -> dict[str, "_TableInfo"]:
        """The catalog-verification step D-4 requires before any client
        identifier may be composed with `sql.Identifier`: this is the live
        set of tables/columns/unique-indexes that actually exist in this
        application's schema right now, queried from `information_schema`/
        `pg_catalog` (never from request content), inside the same
        transaction as the operation being validated.

        R-1's declaration-completeness guard also lives here: every entity
        table this backend's own `_create_entity` provisions always carries
        a `bigint GENERATED ALWAYS AS IDENTITY` `id` column and a `uuid`
        `_r2db_revision` column -- if even one entity table does not
        actually have both (this deployment has never provisioned one that
        doesn't, but this is re-derived from live catalog state on every
        call rather than trusted as a standing assumption), publishing this
        application's catalog at all would be a false `mutable`/
        `address_fields`/`revision_preconditions` declaration for that
        entity (contract `declaration_required`: "must not be advertised as
        enabled unless every entity can produce one"). This fails the whole
        call closed (`SERVICE_UNAVAILABLE`) rather than silently omitting
        the offending entity or downgrading its declaration, naming only
        the offending entities (never a column value) in `details`.
        """
        columns_statement = sql.SQL(
            "SELECT c.table_name, c.column_name, c.data_type, c.is_identity, c.domain_name "
            "FROM information_schema.tables t "
            "JOIN information_schema.columns c "
            "ON c.table_schema = t.table_schema AND c.table_name = t.table_name "
            "WHERE t.table_schema = {schema} AND t.table_type = 'BASE TABLE' AND t.table_name <> {revision_table}"
        ).format(schema=sql.Placeholder(), revision_table=sql.Placeholder())
        # Every unique index (composite or single-column) on any of this
        # application's tables, excluding the primary key (`id`'s own PK is
        # the address, not a domain uniqueness declaration -- R-1/§2) and
        # excluding partial/expression indexes (`create_index` never
        # produces either, so any that exist were not created by this
        # backend and are not a shape it understands). `NOT idx.indisunique`
        # rows (plain, non-unique indexes `create_index(unique=False)`
        # creates) are included too -- SI-08/R-5: an index is a real
        # resource and counts toward `schema_objects` whether or not it is
        # a uniqueness declaration.
        indexes_statement = sql.SQL(
            "SELECT c.relname AS table_name, i.relname AS index_name, idx.indisunique, "
            "array_agg(a.attname ORDER BY k.ord) AS fields "
            "FROM pg_index idx "
            "JOIN pg_class c ON c.oid = idx.indrelid "
            "JOIN pg_class i ON i.oid = idx.indexrelid "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "JOIN LATERAL unnest(idx.indkey::int2[]) WITH ORDINALITY AS k(attnum, ord) ON true "
            "JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = k.attnum "
            "WHERE n.nspname = {schema} AND NOT idx.indisprimary "
            "AND idx.indexprs IS NULL AND idx.indpred IS NULL "
            "GROUP BY c.relname, i.relname, idx.indisunique"
        ).format(schema=sql.Placeholder())

        tables: dict[str, dict[str, str | None]] = {}
        identity_ok: dict[str, bool] = {}
        revision_ok: dict[str, bool] = {}
        with conn.cursor() as cur:
            _run(cur, columns_statement, [self.schema, _REVISION_TABLE])
            for table_name, column_name, data_type, is_identity, domain_name in cur.fetchall():
                columns = tables.setdefault(table_name, {})
                if column_name == _ID_COLUMN:
                    identity_ok[table_name] = data_type == "bigint" and is_identity == "YES"
                    columns[_ID_COLUMN] = "integer"
                elif column_name == _REVISION_COLUMN:
                    revision_ok[table_name] = data_type == "uuid"
                    # Never a known/selectable field (R-3/R-4).
                elif column_name.startswith(_RESERVED_INTERNAL_PREFIX):
                    continue
                else:
                    # WP-3 review, object/array DOMAIN unification: a
                    # column declared via one of this backend's own two
                    # JSON-shape DOMAINs reports its domain name here --
                    # checked first, since `data_type` alone (always
                    # `jsonb` for either domain) cannot distinguish them.
                    # A plain, non-domain column (including bare `jsonb`)
                    # falls through to the ordinary data-type mapping.
                    declared = _DOMAIN_TO_DECLARED.get(domain_name) if domain_name else None
                    if declared is None:
                        declared = _SQL_TYPE_TO_DECLARED.get(data_type)
                    columns[column_name] = declared

        offenders = sorted(
            name for name in tables
            if not identity_ok.get(name, False) or not revision_ok.get(name, False)
        )
        if offenders:
            fail(
                "SERVICE_UNAVAILABLE",
                "An entity table does not satisfy the required id/revision declaration.",
                status=503,
                details={"entities": offenders},
            )

        indexes: dict[str, dict[str, dict[str, Any]]] = {name: {} for name in tables}
        with conn.cursor() as cur:
            _run(cur, indexes_statement, [self.schema])
            for table_name, index_name, is_unique, fields in cur.fetchall():
                if table_name not in tables:
                    continue
                prefix = f"{table_name}__"
                if not index_name.startswith(prefix):
                    # Not one of this backend's own indexes (R-5's physical
                    # naming convention) -- ignore rather than misreport it
                    # under a fabricated client name.
                    continue
                client_name = index_name[len(prefix):]
                indexes[table_name][client_name] = {"physical": index_name, "fields": tuple(fields), "unique": bool(is_unique)}

        return {name: _TableInfo(columns=columns, indexes=indexes.get(name, {})) for name, columns in tables.items()}

    # ---- query ---------------------------------------------------------

    def query(
        self,
        entity: str,
        *,
        select: list[str],
        where: list[Predicate],
        page_size: int,
        limits: ResourceLimits,
        order_by: list[dict[str, Any]] | None = None,
        cursor: str | None = None,
        deadline: float | None = None,
        clock: Callable[[], float] | None = None,
    ) -> QueryOutcome:
        if deadline is not None and clock is not None:
            limits.check_deadline(deadline, clock)
        validate_identifier(entity)
        _reject_reserved_entity_name(entity)  # WP-2(b) fix round 2, item C
        validate_page_size(page_size, limits)
        with self._runtime.connection() as conn:
            timeout_ms = self._timeout_ms(limits, deadline, clock)
            try:
                with conn.transaction():
                    self._set_timeouts(conn, timeout_ms)
                    catalog = self._load_catalog(conn)
                    if entity not in catalog:
                        fail("NOT_FOUND", "Entity was not found.", status=404)
                    table_info = catalog[entity]
                    known_fields = set(table_info.columns)
                    validate_projection(select, known_fields)
                    validate_predicates(where, known_fields)
                    # R-6: identifier/catalog-checked order_by, with a
                    # deterministic trailing `id ASC` tie-break appended
                    # whenever the caller's own order_by does not already
                    # mention `id` -- the exact same shared function
                    # `ApplicationCell.query` uses, so both backends accept/
                    # reject the same order_by shapes identically.
                    order_spec = _resolve_order_by(order_by, known_fields)
                    order_by_count = len(order_by) if order_by else 0
                    limits.check("query_complexity", len(where) + len(select) + order_by_count)
                    # R-7, corrigendum M-9: validate every predicate's value
                    # type before touching stored rows at all -- the same
                    # shared function and the same ordering `ApplicationCell.
                    # query` uses.
                    _validate_predicate_types(where, table_info.columns)
                    # R-6: the cursor's opaque shape hash binds the
                    # Application scope, entity, and the full query shape
                    # (select/where/order_by/size) -- decoded (and
                    # validated) here, before any SQL referencing it runs.
                    shape = _shape_hash(self.application_id, entity, select, where, order_spec, page_size)
                    offset = 0
                    if cursor is not None:
                        offset = _decode_cursor(cursor, shape)
                    where_sql, where_params = self._where_clause(where, table_info.columns)
                    statement = self._select_statement(entity, select, where_sql, order_spec, offset, page_size)
                    with conn.cursor() as cur:
                        _run(cur, statement, where_params)
                        rows = cur.fetchall()
            except psycopg.errors.QueryCanceled:
                fail("LIMIT_EXCEEDED", "Operation exceeds the execution budget.", status=413, details={"resource": "execution_ms", "limit_class": "execution_ms", "limit": limits.execution_ms})
            except psycopg.errors.LockNotAvailable:
                fail("LIMIT_EXCEEDED", "Operation exceeds the execution budget.", status=413, details={"resource": "execution_ms", "limit_class": "execution_ms", "limit": limits.execution_ms})
            except psycopg.Error:
                fail("SERVICE_UNAVAILABLE", "The database could not complete the request.", status=503)
        # R-6: `rows` was fetched with `LIMIT page_size + 1` (the look-ahead
        # row, if present, is never returned to the caller -- it only
        # signals `has_more`); `min(len(rows), page_size)` therefore equals
        # `page_size` whenever at least `page_size` rows matched, or the
        # true (smaller) match count otherwise -- exactly the quantity
        # `ApplicationCell.query`'s own equivalent check computes from its
        # full (unbounded) in-memory match list, before it slices to a
        # window.
        limits.check("result_items", min(len(rows), page_size))
        if deadline is not None and clock is not None:
            limits.check_deadline(deadline, clock)
        has_more = len(rows) > page_size
        page_rows = rows[:page_size]
        # Every row was selected as `select ++ [_r2db_revision::text]`
        # (`_select_statement`, below) -- the revision is always the last
        # column, index-aligned with `page_rows` (R-4: capability
        # `revision_preconditions: enabled` means every entity is mutable,
        # so a query response always includes revisions).
        items = [dict(zip(select, row[:-1])) for row in page_rows]
        revisions = [row[-1] for row in page_rows]
        next_cursor = _encode_cursor(offset + page_size, shape) if has_more else None
        return QueryOutcome(items=items, revisions=revisions, has_more=has_more, next_cursor=next_cursor)

    def _select_statement(
        self,
        entity: str,
        select: list[str],
        where_sql: sql.Composed | None,
        order_spec: list[tuple[str, str]],
        offset: int,
        page_size: int,
    ) -> sql.Composed:
        columns = sql.SQL(", ").join(sql.Identifier(f) for f in select)
        revision = sql.SQL("{col}::text").format(col=sql.Identifier(_REVISION_COLUMN))
        statement = sql.SQL("SELECT {columns}, {revision} FROM {table}").format(columns=columns, revision=revision, table=sql.Identifier(entity))
        if where_sql is not None:
            statement = sql.SQL("{base} WHERE {where}").format(base=statement, where=where_sql)
        statement = sql.SQL("{base} ORDER BY {order}").format(base=statement, order=self._order_by_sql(order_spec))
        # R-6: NULL placement (ASC -> NULLS LAST, DESC -> NULLS FIRST) is
        # PostgreSQL's own default when no NULLS clause is given, which is
        # exactly the semantics `ApplicationCell._sort_key` was written to
        # match -- no explicit NULLS FIRST/LAST needed here. Likewise, a
        # plain (untyped/JSONB) column's own cross-type ordering (ascending:
        # String < Number < Boolean < Array < Object) falls directly out of
        # PostgreSQL's native `jsonb` comparison operators.
        #
        # `offset`/`page_size` are always server-computed, already-validated
        # non-negative integers (never client-supplied text) by this point
        # -- `sql.Literal` here is composing a trusted value, the same
        # pattern `_set_timeouts` already uses for its own computed values.
        return sql.SQL("{base} OFFSET {offset} LIMIT {limit}").format(base=statement, offset=sql.Literal(int(offset)), limit=sql.Literal(int(page_size) + 1))

    def _order_by_sql(self, order_spec: list[tuple[str, str]]) -> sql.Composed:
        parts = [
            sql.SQL("{col} {direction}").format(col=sql.Identifier(field_name), direction=sql.SQL("ASC" if direction == "asc" else "DESC"))
            for field_name, direction in order_spec
        ]
        return sql.SQL(", ").join(parts)

    # ---- mutations -------------------------------------------------------

    def transact(self, entity: str, operations: list[dict[str, Any]], limits: ResourceLimits, *, deadline: float | None = None, clock: Callable[[], float] | None = None, audit_hook: ApplicationAuditHook | None = None) -> MutationOutcome:
        if deadline is not None and clock is not None:
            limits.check_deadline(deadline, clock)
        validate_identifier(entity)
        _reject_reserved_entity_name(entity)  # WP-2(b) fix round 2, item C
        if not operations:
            fail("VALIDATION_FAILED", "At least one mutation is required.")
        limits.check("batch_items", len(operations))
        affected = 0
        assigned_addresses: list[dict[str, Any]] = []
        # Phase 4 (design D-2/D-10): whether this batch passed through the
        # DESTRUCTIVE_CONFIRMATION_V1 choke -- see `ApplicationCell.
        # transact`'s identical comment (D-10 parity).
        destructive = False
        # Set the instant `audit_hook.pre_commit()` returns successfully --
        # everything that can still fail after that point is this method's
        # OWN data commit (the implicit `conn.commit()` `conn.transaction()`
        # issues on normal `with`-block exit), never the audit write again.
        # This is what lets the `except psycopg.Error` clause below tell
        # "the durable audit row committed but the data commit then failed"
        # (D-2's error-row case) apart from every other psycopg failure.
        hook_fired = False
        with self._runtime.connection() as conn:
            timeout_ms = self._timeout_ms(limits, deadline, clock)
            try:
                with conn.transaction():
                    self._set_timeouts(conn, timeout_ms)
                    catalog = self._load_catalog(conn)
                    if entity not in catalog:
                        fail("NOT_FOUND", "Entity was not found.", status=404)
                    table_info = catalog[entity]
                    for operation in operations:
                        if deadline is not None and clock is not None:
                            # WP-2 review M-2 parity: per-operation deadline
                            # check, not only before/after the whole batch.
                            limits.check_deadline(deadline, clock)
                        count, address, op_destructive = self._apply(conn, entity, operation, table_info)
                        affected += count
                        destructive = destructive or op_destructive
                        if address is not None:
                            assigned_addresses.append(address)
                        limits.check("result_items", affected)
                    if deadline is not None and clock is not None:
                        limits.check_deadline(deadline, clock)
                    # Phase 4 (design D-2): the pre-commit hook is the LAST
                    # statement inside this `with conn.transaction():`
                    # block -- a raise here propagates straight through the
                    # block's own `__exit__`, which rolls the data
                    # transaction back exactly like any other exception
                    # raised inside it (no special-casing needed at this
                    # call site: fail-closed by construction).
                    if destructive and audit_hook is not None:
                        audit_hook.pre_commit()
                        hook_fired = True
            except psycopg.errors.QueryCanceled:
                fail("LIMIT_EXCEEDED", "Operation exceeds the execution budget.", status=413, details={"resource": "execution_ms", "limit_class": "execution_ms", "limit": limits.execution_ms})
            except psycopg.errors.LockNotAvailable:
                fail("LIMIT_EXCEEDED", "Operation exceeds the execution budget.", status=413, details={"resource": "execution_ms", "limit_class": "execution_ms", "limit": limits.execution_ms})
            except psycopg.errors.UniqueViolation as exc:
                self._fail_unique_conflict(entity, exc)
            except psycopg.errors.DataError:
                self._fail_client_value()
            except psycopg.Error:
                # Phase 4 (design D-2, error-row rule): `hook_fired` is only
                # `True` once the durable pre-commit row has already
                # committed on its own (separate) connection -- so an
                # exception reaching here after that point can only be this
                # method's own data commit failing. Record the durable
                # `outcome="error"` row for the same `request_id` (still
                # fail-closed: this call may itself raise `FoundationError`
                # SERVICE_UNAVAILABLE, which is exactly what happens next
                # regardless of whether it does).
                if hook_fired and audit_hook is not None:
                    audit_hook.commit_failed()
                fail("SERVICE_UNAVAILABLE", "The database could not complete the request.", status=503)
        # `conn.transaction()` rolls back the *entire* batch on any
        # exception (including a `FoundationError` raised by a later
        # operation), giving the whole batch one real database transaction
        # (D-5) in place of `ApplicationCell`'s in-memory deepcopy/restore.
        # `assigned_addresses` (CCR-13, R-5) lists, in operation order, the
        # address of every operation that resolved to an insert (a plain
        # `insert`, or an `upsert` whose declared key found no existing
        # row) -- an `upsert` that resolved to an update contributes
        # nothing here, exactly like `ApplicationCell.transact`.
        return MutationOutcome(affected=affected, assigned_addresses=assigned_addresses, destructive=destructive)

    def _fail_unique_conflict(self, entity: str, exc: "psycopg.errors.UniqueViolation") -> None:
        """R-5, corrigendum M-5: map a real PostgreSQL `UniqueViolation`
        (raised naturally by any INSERT/UPDATE that collides with a
        `create_index(unique=True)`-declared index -- including one other
        than the key an `upsert` used for its own existence test, R-5's
        "既存重複は CONFLICT") to the contract's `CONFLICT`, disclosing at
        most the client-recognizable index name and never PostgreSQL's own
        DETAIL text, constraint/index internals, or any row value. `exc.
        diag.constraint_name` is PostgreSQL's own (physical) index name; it
        is only ever used here to look up the corresponding client name by
        stripping this backend's own `{entity}__` naming convention -- never
        surfaced to the caller directly.
        """
        physical = exc.diag.constraint_name or ""
        prefix = f"{entity}__"
        details: dict[str, Any] = {}
        if physical.startswith(prefix):
            details = {"index": physical[len(prefix):]}
        fail("CONFLICT", "A declared uniqueness key would be violated.", status=409, details=details)

    def _fail_client_value(self) -> None:
        """R-7 addendum (WP-3 review blocker-2): a `psycopg.errors.
        DataError` (SQLSTATE class 22 -- e.g. `NumericValueOutOfRange`, or
        a NUL byte PostgreSQL's `text`/`jsonb` storage cannot hold at all)
        is always a decisive, deterministic client-supplied-value bug, not
        a transient server condition -- `VALIDATION_FAILED`, never
        `SERVICE_UNAVAILABLE` (which reads as "retry", and an AI agent
        client retrying an identical, never-succeeding request is exactly
        the failure mode this refusal exists to prevent). This is a second,
        defence-in-depth layer underneath the shared boundary's own value-
        domain checks (`r2db_api.structured._check_type`'s integer-range/
        NUL-byte validation, `_validate_wildcard_pattern`'s grammar check)
        -- those already refuse every value this maps today before it ever
        reaches SQL, so reaching this handler in practice means either
        check has a gap, not that this handler is the primary defence.
        Fixed message, no `details`: unlike `_fail_unique_conflict` above,
        a single `DataError` from a whole batch/statement cannot be
        reliably attributed to one specific field from this generic catch
        site, so no field name is guessed at (`errors.disclosure`: never
        wrong information is safer than no information).
        """
        fail("VALIDATION_FAILED", "A value in this request is not acceptable to the underlying storage.")

    def _bind_value(self, value: Any, field_type: str | None) -> Any:
        """R-7 addendum (WP-2 review M-B, confirmed empirically against a
        real server): a JSON `null` must bind as SQL `NULL` for every
        column shape, typed or untyped -- `Jsonb(None)` would instead
        produce the JSONB literal `'null'::jsonb` for an untyped column,
        which would make `is_null` predicates and `order_by` NULL placement
        diverge from `ApplicationCell`'s own null semantics. A non-null
        value binds as a native parameter for a scalar-typed column
        (`string`/`integer`/`number`/`boolean`) or wrapped in `Jsonb(...)`
        for an untyped column *or* an `object`/`array` one -- the latter
        two are still physically `jsonb` underneath their DOMAIN (WP-3
        review, object/array DOMAIN unification), so psycopg must still be
        told to serialize the value as jsonb, exactly as for an untyped
        column.
        """
        if value is None:
            return None
        if field_type is None or field_type in ("object", "array"):
            return Jsonb(value)
        return value

    def _apply(self, conn: "psycopg.Connection[Any]", entity: str, operation: dict[str, Any], table_info: "_TableInfo") -> tuple[int, dict[str, Any] | None, bool]:
        field_types = table_info.columns
        known_fields = set(field_types)
        bound = bind_mutation(operation, known_fields)

        if bound.operation == "insert":
            # R-7, corrigendum M-9: value types are validated before
            # anything is sent to the database.
            for key, value in bound.values.items():
                _check_type(value, field_types.get(key), key)
            row_id = self._insert(conn, entity, bound.values, field_types)
            return 1, {"address": {"id": row_id}}, False

        if bound.operation == "upsert":
            count, address = self._apply_upsert(conn, entity, bound, table_info)
            return count, address, False

        # update / delete: R-7, corrigendum M-9 -- validate every value's
        # type (predicate values, and for `update` the write values too)
        # before executing anything, symmetric with the `insert` branch
        # above and with `ApplicationCell._apply`.
        _validate_predicate_types(bound.where, field_types)
        if bound.operation == "update":
            for key, value in bound.values.items():
                _check_type(value, field_types.get(key), key)

        where_sql, where_params = self._where_clause(bound.where, field_types)

        if bound.operation == "delete":
            # R-4, corrigendum m-5: destructive confirmation is checked
            # before any precondition-related outcome (never resolves to a
            # PRECONDITION_FAILED/NOT_FOUND).
            require_destructive_confirmation(
                bound.destructive, bound.confirmation,
                delete_confirmation_phrase(entity, bound.where, self._read_schema_revision(conn)),
                "Delete requires explicit destructive confirmation.",
                consequence="Rows matching the filter are permanently deleted; there is no in-band restore.",
                reversible_alternative=None,
                recovery=None,
            )
            # Phase 4 (design D-2): reaching this point means the
            # confirmation choke above did not raise -- confirmed-
            # destructive, same signal `ApplicationCell._apply` returns.
            affected = self._delete(conn, entity, where_sql, where_params, bound.expected_revision)
            return affected, None, True

        affected = self._update(conn, entity, bound.values, where_sql, where_params, field_types, bound.expected_revision)
        return affected, None, False

    def _append_revision_predicate(self, where_sql: sql.Composed | None, where_params: list[Any], expected_revision: str | None) -> tuple[sql.Composed | None, list[Any]]:
        """R-4: an `expected_revision` precondition is folded into the same
        WHERE clause as the caller's own predicate (`<predicate> AND
        _r2db_revision::text = $expected`), so the comparison and the write
        are one atomic statement (the contract's revision-precondition
        clause 5) rather than a separate read-then-write.

        The comparison casts the `uuid` column to `text` rather than
        binding `expected_revision` as a (contextually inferred) `uuid`
        parameter: `expected_revision` is an arbitrary contract-opaque
        client string (`bind_mutation` only bounds its length, since the
        contract never requires it to look like a UUID), and PostgreSQL
        raises a hard `invalid input syntax for type uuid` error -- not
        just "does not match" -- for a non-UUID-shaped one. `ApplicationCell`
        stores/compares revisions as plain Python strings, so a garbage
        `expected_revision` there simply fails to match any row (resolving
        to `PRECONDITION_FAILED`/`NOT_FOUND` the normal way); casting to
        `text` here is what keeps that same "never matches, never raises"
        behaviour on this backend too, instead of a `SERVICE_UNAVAILABLE`
        this predicate's own value should never be able to trigger.
        """
        if expected_revision is None:
            return where_sql, list(where_params)
        revision_clause = sql.SQL("{col}::text = {ph}").format(col=sql.Identifier(_REVISION_COLUMN), ph=sql.Placeholder())
        combined = sql.SQL("{w} AND {r}").format(w=where_sql, r=revision_clause) if where_sql is not None else revision_clause
        return combined, list(where_params) + [expected_revision]

    def _resolve_precondition_miss(self, conn: "psycopg.Connection[Any]", table: sql.Identifier, where_sql: sql.Composed | None, where_params: list[Any]) -> None:
        """R-4, corrigendum M-2: when a revision-qualified UPDATE/DELETE
        affects zero rows, re-evaluate the caller's own predicate alone (no
        revision clause), in the same transaction, to decide which of the
        two failures applies -- `PRECONDITION_FAILED` (a row exists, but its
        revision was not the one asserted) or `NOT_FOUND` (no row matches
        the predicate at all, so there was no row to assert about).
        """
        if self._exists(conn, table, where_sql, where_params):
            fail("PRECONDITION_FAILED", "The row's revision no longer matches the supplied precondition.", status=412)
        fail("NOT_FOUND", "No row matches the supplied filter.", status=404)

    def _exists(self, conn: "psycopg.Connection[Any]", table: sql.Identifier, where_sql: sql.Composed | None, where_params: list[Any]) -> bool:
        inner = sql.SQL("SELECT 1 FROM {table}").format(table=table)
        if where_sql is not None:
            inner = sql.SQL("{base} WHERE {where}").format(base=inner, where=where_sql)
        statement = sql.SQL("SELECT EXISTS({inner})").format(inner=inner)
        with conn.cursor() as cur:
            _run(cur, statement, where_params if where_sql is not None else [])
            row = cur.fetchone()
            return bool(row[0]) if row else False

    def _insert(self, conn: "psycopg.Connection[Any]", entity: str, values: dict[str, Any], field_types: dict[str, str | None]) -> int:
        table = sql.Identifier(entity)
        if not values:
            statement = sql.SQL("INSERT INTO {table} DEFAULT VALUES RETURNING {id}").format(table=table, id=sql.Identifier(_ID_COLUMN))
            params: list[Any] = []
        else:
            columns = sql.SQL(", ").join(sql.Identifier(key) for key in values)
            placeholders = sql.SQL(", ").join(sql.Placeholder() for _ in values)
            statement = sql.SQL("INSERT INTO {table} ({columns}) VALUES ({placeholders}) RETURNING {id}").format(table=table, columns=columns, placeholders=placeholders, id=sql.Identifier(_ID_COLUMN))
            params = [self._bind_value(v, field_types.get(k)) for k, v in values.items()]
        with conn.cursor() as cur:
            _run(cur, statement, params)
            row = cur.fetchone()
        return int(row[0])

    def _update(
        self,
        conn: "psycopg.Connection[Any]",
        entity: str,
        values: dict[str, Any],
        where_sql: sql.Composed | None,
        where_params: list[Any],
        field_types: dict[str, str | None],
        expected_revision: str | None,
    ) -> int:
        table = sql.Identifier(entity)
        if expected_revision is None and not values:
            # R-4, corrigendum M-1: this branch is only reachable without a
            # precondition -- `bind_mutation` already rejects an empty-
            # `values` `update` carrying `expected_revision` outright, so a
            # precondition is never silently discarded here.
            return self._count(conn, table, where_sql, where_params)
        full_where_sql, full_params = self._append_revision_predicate(where_sql, where_params, expected_revision)
        revision_bump = sql.SQL("{col} = gen_random_uuid()").format(col=sql.Identifier(_REVISION_COLUMN))
        if values:
            assignments = sql.SQL(", ").join(sql.SQL("{col} = {ph}").format(col=sql.Identifier(key), ph=sql.Placeholder()) for key in values)
            set_clause = sql.SQL("{assignments}, {revision}").format(assignments=assignments, revision=revision_bump)
            value_params = [self._bind_value(v, field_types.get(k)) for k, v in values.items()]
        else:
            set_clause = revision_bump
            value_params = []
        statement = sql.SQL("UPDATE {table} SET {set} WHERE {where}").format(table=table, set=set_clause, where=full_where_sql)
        with conn.cursor() as cur:
            _run(cur, statement, value_params + full_params)
            affected = cur.rowcount
        if affected == 0 and expected_revision is not None:
            self._resolve_precondition_miss(conn, table, where_sql, where_params)
        return affected

    def _delete(self, conn: "psycopg.Connection[Any]", entity: str, where_sql: sql.Composed | None, where_params: list[Any], expected_revision: str | None) -> int:
        table = sql.Identifier(entity)
        full_where_sql, full_params = self._append_revision_predicate(where_sql, where_params, expected_revision)
        statement = sql.SQL("DELETE FROM {table} WHERE {where}").format(table=table, where=full_where_sql)
        with conn.cursor() as cur:
            _run(cur, statement, full_params)
            affected = cur.rowcount
        if affected == 0 and expected_revision is not None:
            self._resolve_precondition_miss(conn, table, where_sql, where_params)
        return affected

    def _count(self, conn: "psycopg.Connection[Any]", table: sql.Identifier, where_sql: sql.Composed | None, where_params: list[Any]) -> int:
        statement = sql.SQL("SELECT COUNT(*) FROM {table}").format(table=table)
        params: list[Any] = []
        if where_sql is not None:
            statement = sql.SQL("{base} WHERE {where}").format(base=statement, where=where_sql)
            params = where_params
        with conn.cursor() as cur:
            _run(cur, statement, params)
            row = cur.fetchone()
            return row[0] if row else 0

    def _apply_upsert(self, conn: "psycopg.Connection[Any]", entity: str, bound: "BoundMutation", table_info: "_TableInfo") -> tuple[int, dict[str, Any] | None]:
        """R-5 / §0.5 Q-1 (adjudicated 案B). Mirrors `ApplicationCell.
        _apply_upsert`'s exact key-selection and error-precedence rules;
        the only difference is execution: two real SQL statements
        (`INSERT ... ON CONFLICT (<key>) DO NOTHING RETURNING id`, then --
        only if that inserted nothing -- `UPDATE ... WHERE <key eq>`)
        instead of an in-memory existence check, per corrigendum M-4 (never
        relying on `xmax`-based "was this an insert or update" tricks).
        """
        field_types = table_info.columns
        declared = {name: info for name, info in table_info.indexes.items() if info["unique"]}
        if not declared:
            fail("CAPABILITY_UNSUPPORTED", "Upsert requires a declared domain uniqueness key.")
        if bound.unique_key is not None:
            if bound.unique_key not in declared:
                fail("NOT_FOUND", "No declared uniqueness key matches unique_key.", status=404)
            key_name = bound.unique_key
        elif len(declared) == 1:
            key_name = next(iter(declared))
        else:
            fail("VALIDATION_FAILED", "unique_key is required when an entity declares more than one uniqueness key.")
        if bound.where:
            fail("VALIDATION_FAILED", "Upsert does not accept a filter; its existence test is the entity's declared uniqueness key.")
        key_fields: tuple[str, ...] = declared[key_name]["fields"]
        for key_field in key_fields:
            if bound.values.get(key_field) is None:
                fail("VALIDATION_FAILED", "Upsert values must include every uniqueness key field.", details={"field": key_field})
        # R-7, corrigendum M-9: type-check before any SQL runs, symmetric
        # with insert/update above.
        for key, value in bound.values.items():
            _check_type(value, field_types.get(key), key)

        table = sql.Identifier(entity)
        key_where_sql = sql.SQL(" AND ").join(sql.SQL("{col} = {ph}").format(col=sql.Identifier(f), ph=sql.Placeholder()) for f in key_fields)
        key_where_params = [self._bind_value(bound.values[f], field_types.get(f)) for f in key_fields]
        update_values = {k: v for k, v in bound.values.items() if k not in key_fields}
        revision_bump = sql.SQL("{col} = gen_random_uuid()").format(col=sql.Identifier(_REVISION_COLUMN))
        if update_values:
            assignments = sql.SQL(", ").join(sql.SQL("{col} = {ph}").format(col=sql.Identifier(k), ph=sql.Placeholder()) for k in update_values)
            set_clause = sql.SQL("{a}, {r}").format(a=assignments, r=revision_bump)
            update_value_params = [self._bind_value(v, field_types.get(k)) for k, v in update_values.items()]
        else:
            set_clause = revision_bump
            update_value_params = []

        if bound.expected_revision is not None:
            # R-5: a precondition never resolves an upsert to an insert --
            # no key match is NOT_FOUND (via `_resolve_precondition_miss`),
            # exactly like update/delete.
            full_where_sql, full_params = self._append_revision_predicate(key_where_sql, key_where_params, bound.expected_revision)
            statement = sql.SQL("UPDATE {table} SET {set} WHERE {where}").format(table=table, set=set_clause, where=full_where_sql)
            with conn.cursor() as cur:
                _run(cur, statement, update_value_params + full_params)
                affected = cur.rowcount
            if affected == 0:
                self._resolve_precondition_miss(conn, table, key_where_sql, key_where_params)
            return 1, None

        columns = sql.SQL(", ").join(sql.Identifier(k) for k in bound.values)
        placeholders = sql.SQL(", ").join(sql.Placeholder() for _ in bound.values)
        conflict_columns = sql.SQL(", ").join(sql.Identifier(f) for f in key_fields)
        insert_statement = sql.SQL("INSERT INTO {table} ({cols}) VALUES ({phs}) ON CONFLICT ({conflict}) DO NOTHING RETURNING {id}").format(
            table=table, cols=columns, phs=placeholders, conflict=conflict_columns, id=sql.Identifier(_ID_COLUMN)
        )
        insert_params = [self._bind_value(v, field_types.get(k)) for k, v in bound.values.items()]
        with conn.cursor() as cur:
            _run(cur, insert_statement, insert_params)
            row = cur.fetchone()
        if row is not None:
            return 1, {"address": {"id": int(row[0])}}

        update_statement = sql.SQL("UPDATE {table} SET {set} WHERE {where} RETURNING {id}").format(table=table, set=set_clause, where=key_where_sql, id=sql.Identifier(_ID_COLUMN))
        with conn.cursor() as cur:
            _run(cur, update_statement, update_value_params + key_where_params)
            row = cur.fetchone()
        if row is None:
            # M-4: the row this INSERT's ON CONFLICT saw was removed by a
            # concurrent transaction before this UPDATE could find it --
            # neither statement resolved, so the whole batch rolls back as
            # a concurrent-modification conflict rather than silently
            # inserting a second time.
            fail("CONFLICT", "The row was concurrently modified.", status=409)
        return 1, None

    # ---- predicate/WHERE composition ------------------------------------

    def _where_clause(self, where: list[Predicate], field_types: dict[str, str | None]) -> tuple[sql.Composed | None, list[Any]]:
        if not where:
            return None, []
        fragments: list[sql.Composed] = []
        params: list[Any] = []
        for predicate in where:
            fragment, values = self._predicate_sql(predicate, field_types.get(predicate.field))
            fragments.append(fragment)
            params.extend(values)
        return sql.SQL(" AND ").join(fragments), params

    def _text_expression(self, column: sql.Identifier, field_type: str | None) -> sql.Composed:
        """The text form of `column` that `contains`/`matches` compare
        against. R-7: "非 text 列は従来どおり ::text に対して適用" -- a
        typed non-text column's plain `::text` cast is exactly this (a
        numeric/boolean column's text representation carries no quoting
        ambiguity). An *untyped* (JSONB-equivalent) column is different:
        PostgreSQL's own `::text` cast on jsonb returns the JSON text
        representation, which wraps a JSON **string** value in literal
        double quotes (`"hello"`, not `hello`) -- silently breaking a full-
        string-anchored `matches` pattern and shifting every `contains`
        substring offset by one quote character, for exactly the columns
        most likely to hold free-text data. `#>> '{}'` (the same "unwrap a
        top-level jsonb scalar to text" idiom `->>`/`#>>` use for a keyed
        value) recovers the bare string PostgreSQL's own client already
        knows, and returns the same non-quoted text `::text` would for a
        non-string JSON scalar (number/boolean/null) or an object/array --
        it only differs from `::text` in the case that would otherwise be
        wrong. This is what keeps the two backends' behaviour for a string-
        typed field in parity, whether the client declared it via `add_field
        field_type: "string"` or left it untyped.
        """
        if field_type is None:
            return sql.SQL("(") + column + sql.SQL(" #>> '{}')")
        return column + sql.SQL("::text")

    def _predicate_sql(self, predicate: Predicate, field_type: str | None) -> tuple[sql.Composed, list[Any]]:
        column = sql.Identifier(predicate.field)
        if predicate.operator == "is_null":
            return sql.SQL("{col} IS NULL").format(col=column), []
        if predicate.operator == "in":
            if not isinstance(predicate.value, list) or not predicate.value:
                fail("VALIDATION_FAILED", "Filter value is incompatible with the selected operator.")
            placeholders = sql.SQL(", ").join(sql.Placeholder() for _ in predicate.value)
            # R-7, corrigendum m-7: each element gets the same per-column
            # type-aware bind (native for a typed column, `Jsonb(...)` for
            # an untyped one, SQL NULL for a JSON null) as every other
            # value position -- never a blanket `Jsonb(v)`.
            return sql.SQL("{col} IN ({items})").format(col=column, items=placeholders), [self._bind_value(v, field_type) for v in predicate.value]
        if predicate.operator in ("contains", "matches"):
            text_column = self._text_expression(column, field_type)
            if predicate.operator == "contains":
                # Q-2 (案i): literal substring containment -- `%`/`_`/`\`
                # in the value are escaped before being wrapped in
                # `%...%`, so no character of the value is ever
                # interpreted as a wildcard. `_validate_predicate_types`
                # (called by every caller of this method) has already
                # required `predicate.value` to be a string by this point.
                escaped = _escape_like_literal(predicate.value)
                pattern = f"%{escaped}%"
            else:
                # Q-2 (補足案): the client's pattern already uses exactly
                # SQL LIKE's own wildcard grammar (`%`/`_`/`\`-escape) --
                # bound as-is, no transformation.
                pattern = predicate.value
            return sql.SQL("{col} LIKE {ph} ESCAPE '\\'").format(col=text_column, ph=sql.Placeholder()), [pattern]
        operator = _COMPARISON_OPERATORS.get(predicate.operator)
        if operator is None:
            # Unreachable in practice: `predicate.validate()` (called by
            # `validate_predicates`, upstream of every caller here) already
            # rejects any operator outside `structured.OPERATORS`. Kept as
            # an explicit, fixed-literal-only fallback rather than trusting
            # that invariant silently (D-4: "operators map to fixed
            # literals").
            fail("VALIDATION_FAILED", "Unsupported filter operator.", details={"field": predicate.field})
        return sql.SQL("{col} {op} {ph}").format(col=column, op=operator, ph=sql.Placeholder()), [self._bind_value(predicate.value, field_type)]

    # ---- schema ----------------------------------------------------------

    def apply_schema(self, operation: dict[str, Any], *, developer: bool, limits: ResourceLimits, deadline: float | None = None, clock: Callable[[], float] | None = None, audit_hook: ApplicationAuditHook | None = None) -> int:
        bound = bind_schema_operation(operation, developer=developer)
        # Phase 4 (design D-2/D-10): see `transact`'s identical `hook_fired`
        # comment -- `True` only once the durable pre-commit row has
        # already committed on its own connection, which is what lets the
        # `except psycopg.Error` clause below tell a post-hook data-commit
        # failure apart from every other failure.
        hook_fired = False
        with self._developer.connection() as conn:
            timeout_ms = self._timeout_ms(limits, deadline, clock)
            try:
                with conn.transaction():
                    self._set_timeouts(conn, timeout_ms)
                    catalog = self._load_catalog(conn)
                    # Object accounting mirrors `ApplicationCell.apply_
                    # schema` exactly (R-5: an index is a real resource and
                    # counts toward `schema_objects` too, SI-08): one object
                    # per entity table plus one per declared field
                    # (`id` included, `_r2db_revision` never counted, same
                    # as `ApplicationCell.schema`'s own dict), plus one per
                    # index (unique or not).
                    current_objects = sum(len(info.columns) + 1 for info in catalog.values()) + sum(len(info.indexes) for info in catalog.values())
                    if bound.operation == "create_entity":
                        projected = current_objects + 1 + 1 + len(bound.fields)  # entity + id + declared fields
                    elif bound.operation == "add_field":
                        projected = current_objects + 1
                    elif bound.operation == "drop_entity":
                        info = catalog.get(bound.entity)
                        columns_len = len(info.columns) if info is not None else 0
                        indexes_len = len(info.indexes) if info is not None else 0
                        projected = current_objects - (columns_len + 1) - indexes_len
                    elif bound.operation == "create_index":
                        projected = current_objects + 1
                    else:  # drop_index
                        projected = current_objects - 1
                    limits.check("schema_objects", projected)
                    if deadline is not None and clock is not None:
                        limits.check_deadline(deadline, clock)
                    if bound.operation == "create_entity":
                        # WP-2(b) review B-2 (supervisor ruling): defense-
                        # in-depth -- `bind_schema_operation` above already
                        # rejects this exact name (structured.py's own
                        # `_reject_reserved_entity_name`, the real, load-
                        # bearing check for BOTH cell implementations), but
                        # this backend's own physical-DDL layer re-checks
                        # it directly too, mirroring MitateDB's per-backend
                        # `check_reserved` redundancy rather than relying
                        # solely on the shared caller never being bypassed.
                        _reject_reserved_entity_name(bound.entity)
                        if bound.entity in catalog:
                            fail("CONFLICT", "Entity already exists.", status=409)
                        self._create_entity(conn, bound.entity, bound.fields)
                    elif bound.operation == "drop_entity":
                        if bound.entity not in catalog:
                            fail("NOT_FOUND", "Entity was not found.", status=404)
                        require_destructive_confirmation(
                            bound.destructive, bound.confirmation,
                            drop_entity_confirmation_phrase(bound.entity, self._read_schema_revision(conn)),
                            "Drop requires explicit destructive confirmation.",
                            consequence="The entity and all of its rows and indexes are permanently destroyed; re-creating an entity of the same name creates a new entity, not a restore.",
                            reversible_alternative=None,
                            recovery=None,
                        )
                        self._drop_entity(conn, bound.entity)
                    elif bound.operation == "add_field":
                        if bound.entity not in catalog:
                            fail("NOT_FOUND", "Entity was not found.", status=404)
                        if bound.field in catalog[bound.entity].columns:
                            fail("CONFLICT", "Field already exists.", status=409)
                        self._add_field(conn, bound.entity, bound.field, bound.field_type)
                    elif bound.operation == "create_index":
                        if bound.entity not in catalog:
                            fail("NOT_FOUND", "Entity was not found.", status=404)
                        table_info = catalog[bound.entity]
                        for index_field in bound.index_fields:
                            if index_field not in table_info.columns:
                                fail("NOT_FOUND", "Field was not found.", status=404)
                        if bound.index in table_info.indexes:
                            fail("CONFLICT", "Index already exists.", status=409)
                        self._create_index(conn, bound.entity, bound.index, bound.index_fields, bound.unique)
                    else:  # drop_index
                        if bound.entity not in catalog:
                            fail("NOT_FOUND", "Entity was not found.", status=404)
                        table_info = catalog[bound.entity]
                        if bound.index not in table_info.indexes:
                            fail("NOT_FOUND", "Index was not found.", status=404)
                        # R-5, corrigendum M-6: dropping a unique index
                        # removes a guardrail and can silently re-enable
                        # upsert -- SI-09 destructive confirmation applies
                        # exactly like drop_entity.
                        require_destructive_confirmation(
                            bound.destructive, bound.confirmation,
                            drop_index_confirmation_phrase(bound.entity, bound.index, self._read_schema_revision(conn)),
                            "Dropping an index requires explicit destructive confirmation.",
                            consequence="The index is destroyed; query semantics are unaffected, only performance (and any uniqueness guarantee it enforced) are lost.",
                            reversible_alternative=None,
                            recovery="create_index with the same definition restores it -- an index carries no data of its own, so this fully restores a non-unique index; recreating a UNIQUE index re-validates existing rows against that uniqueness and can instead fail with CONFLICT if data written after the drop now violates it.",
                        )
                        self._drop_index(conn, table_info.indexes[bound.index]["physical"])
                    revision = self._bump_revision(conn)
                    # Phase 4 (design D-2, item 2): unconditional -- every
                    # schema operation is fail-closed class. Last statement
                    # inside this `with conn.transaction():` block, same
                    # reasoning as `transact`'s identical comment.
                    if audit_hook is not None:
                        audit_hook.pre_commit()
                        hook_fired = True
            except psycopg.errors.QueryCanceled:
                fail("LIMIT_EXCEEDED", "Operation exceeds the execution budget.", status=413, details={"resource": "execution_ms", "limit_class": "execution_ms", "limit": limits.execution_ms})
            except psycopg.errors.LockNotAvailable:
                fail("LIMIT_EXCEEDED", "Operation exceeds the execution budget.", status=413, details={"resource": "execution_ms", "limit_class": "execution_ms", "limit": limits.execution_ms})
            except psycopg.errors.UniqueViolation as exc:
                # R-5: `create_index(unique=True)` against data that
                # already violates the requested uniqueness.
                self._fail_unique_conflict(bound.entity, exc)
            except psycopg.errors.DataError:
                self._fail_client_value()
            except psycopg.Error:
                # Phase 4 (design D-2, error-row rule): see `transact`'s
                # identical comment.
                if hook_fired and audit_hook is not None:
                    audit_hook.commit_failed()
                fail("SERVICE_UNAVAILABLE", "The database could not complete the request.", status=503)
        return revision

    def _create_entity(self, conn: "psycopg.Connection[Any]", entity: str, fields: tuple[str, ...]) -> None:
        # R-1/R-4: every entity table gets a server-assigned `id` address
        # (`GENERATED ALWAYS AS IDENTITY`, so the sequence is never
        # rewound by any statement reachable through this public API -- see
        # R-1's "採番識別子の非推論条項"/property-5 note) and an invisible,
        # per-row `_r2db_revision` (PostgreSQL 13+'s built-in
        # `gen_random_uuid()`), ahead of the caller's own declared fields
        # (always JSONB -- `create_entity` never carries a `field_type`,
        # R-2). `"id"`/`"_r2db_revision"` are hardcoded server literals
        # here, never client input, so composing them as fixed SQL text
        # (rather than through `sql.Identifier`) does not reopen the
        # identifier-injection surface D-4 closes for client-supplied names.
        id_column = sql.SQL("id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY")
        revision_column = sql.SQL("{col} uuid NOT NULL DEFAULT gen_random_uuid()").format(col=sql.Identifier(_REVISION_COLUMN))
        declared_columns = [sql.SQL("{col} JSONB").format(col=sql.Identifier(f)) for f in fields]
        all_columns = sql.SQL(", ").join([id_column, revision_column] + declared_columns)
        statement = sql.SQL("CREATE TABLE {table} ({columns})").format(table=sql.Identifier(entity), columns=all_columns)
        with conn.cursor() as cur:
            _run(cur, statement)
            self._apply_row_level_security(cur, entity)
            # §8.5 condition 3(b): do not depend on remembering that the
            # line above ran correctly. Re-derive, from live catalog state
            # in the same transaction, whether *every* table in this
            # application's database (not just the one just created) has
            # RLS enabled and forced -- and refuse to let this CREATE TABLE
            # commit if not. This is what makes RLS coverage a checked
            # invariant rather than a convention: a future bug in
            # `_apply_row_level_security`, or a table created by some other
            # code path entirely, is caught here, before commit, not
            # discovered later by an operator. See
            # `verify_row_level_security` below for the same check exposed
            # standalone (used by `r2db-api/tests/test_postgres.py` and
            # available for an operator/health-check to call at any time,
            # independent of a schema change happening at all).
            offenders = self._rls_offenders(cur)
            if offenders:
                fail(
                    "SERVICE_UNAVAILABLE",
                    "Row level security is not enabled and forced on every table in this application's database.",
                    status=503,
                    details={"tables": offenders},
                )

    def _apply_row_level_security(self, cur: "psycopg.Cursor[Any]", entity: str) -> None:
        """D-3's third layer: RLS as defence-in-depth underneath the
        database boundary and the two distinct DB roles (architecture §8,
        "D-3 改訂": each application now owns its own PostgreSQL database,
        not merely its own schema inside one shared database -- the
        database boundary is the primary wall, since PostgreSQL admits no
        cross-database query path at all without FDW/dblink, which this
        deployment never grants). This policy's job is to survive a
        *future* misconfiguration of that primary wall -- e.g. an
        accidental broader `CONNECT` grant -- rather than to be the
        primary control itself. It restricts every row in every table this
        cell creates to being visible/writable only by this application's
        own two roles, checked by PostgreSQL itself via `current_user`, not
        by anything this Python process asserts about itself.
        """
        table = sql.Identifier(entity)
        _run(cur, sql.SQL("ALTER TABLE {table} ENABLE ROW LEVEL SECURITY").format(table=table))
        _run(cur, sql.SQL("ALTER TABLE {table} FORCE ROW LEVEL SECURITY").format(table=table))
        policy = sql.Identifier(f"{entity}_application_isolation")
        _run(
            cur,
            sql.SQL("CREATE POLICY {policy} ON {table} USING (current_user IN ({runtime}, {developer})) WITH CHECK (current_user IN ({runtime}, {developer}))").format(
                policy=policy,
                table=table,
                runtime=sql.Literal(self._runtime_role),
                developer=sql.Literal(self._developer_role),
            ),
        )

    def _rls_offenders(self, cur: "psycopg.Cursor[Any]") -> list[str]:
        """The live list of base tables in this application's database
        (current schema, i.e. `public`) that do NOT have both `ENABLE ROW
        LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY` set right now,
        according to PostgreSQL's own catalog -- never this Python
        process's memory of what it thinks it did. `_r2db_schema_revision`
        (provisioned by `migrations/0003_provision_application.sql`,
        already RLS-protected there) is excluded the same way
        `_load_catalog` excludes it from the application-visible catalog.
        Ordered so callers get a deterministic offender list.
        """
        statement = sql.SQL(
            "SELECT c.relname FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = current_schema() AND c.relkind = 'r' AND c.relname <> {revision_table} "
            "AND (c.relrowsecurity = false OR c.relforcerowsecurity = false) "
            "ORDER BY c.relname"
        ).format(revision_table=sql.Placeholder())
        _run(cur, statement, [_REVISION_TABLE])
        return [row[0] for row in cur.fetchall()]

    def verify_row_level_security(self) -> None:
        """Standalone form of the same check `_create_entity` runs inline
        after every `CREATE TABLE` (§8.5 condition 3(b)): confirms every
        base table in this application's database has RLS both enabled and
        forced, independent of any schema change happening right now.
        Callable at any time -- by a test, or by an operator/health-check
        script -- as a live verification against real catalog state, not a
        cached or point-in-time claim. Raises `FoundationError` naming the
        offending tables if any are found; does nothing (no return value)
        if the database is clean.

        `migrations/0003_provision_application.sql` additionally installs
        an always-available SQL-level equivalent of this same query,
        `public._r2db_missing_rls`, directly inside every application's own
        database, so this property can also be checked with `psql` (or any
        other client) without going through `PostgresCell`/Python at all.
        """
        with self._developer.connection() as conn:
            with conn.transaction():
                with conn.cursor() as cur:
                    offenders = self._rls_offenders(cur)
        if offenders:
            fail(
                "SERVICE_UNAVAILABLE",
                "Row level security is not enabled and forced on every table in this application's database.",
                status=503,
                details={"tables": offenders},
            )

    def _drop_entity(self, conn: "psycopg.Connection[Any]", entity: str) -> None:
        statement = sql.SQL("DROP TABLE {table}").format(table=sql.Identifier(entity))
        with conn.cursor() as cur:
            _run(cur, statement)

    def _add_field(self, conn: "psycopg.Connection[Any]", entity: str, field: str, field_type: str | None) -> None:
        # R-2: `field_type` maps to a real typed column; omitted keeps the
        # pre-CCR-13 default, JSONB.
        column_type = _FIELD_TYPE_SQL.get(field_type, _JSONB_SQL) if field_type is not None else _JSONB_SQL
        statement = sql.SQL("ALTER TABLE {table} ADD COLUMN {col} {type}").format(table=sql.Identifier(entity), col=sql.Identifier(field), type=column_type)
        with conn.cursor() as cur:
            _run(cur, statement)

    def _create_index(self, conn: "psycopg.Connection[Any]", entity: str, index_name: str, fields: tuple[str, ...], unique: bool) -> None:
        # R-5: the physical index name is `{entity}__{index}` -- `bind_
        # schema_operation` has already rejected any client index name
        # containing `__` or whose composed length would exceed the
        # identifier limit, so this composition is unambiguous to invert
        # (`_load_catalog` does exactly that). `entity`/`index_name` are
        # plain Python strings built from already-validated identifiers;
        # `sql.Identifier` below is what actually makes this safe to send
        # to PostgreSQL (it quotes/escapes the resulting name regardless of
        # content), not the string concatenation itself.
        physical_name = f"{entity}__{index_name}"
        columns = sql.SQL(", ").join(sql.Identifier(f) for f in fields)
        unique_keyword = sql.SQL("UNIQUE ") if unique else sql.SQL("")
        statement = sql.SQL("CREATE {unique}INDEX {name} ON {table} ({columns})").format(unique=unique_keyword, name=sql.Identifier(physical_name), table=sql.Identifier(entity), columns=columns)
        with conn.cursor() as cur:
            _run(cur, statement)

    def _drop_index(self, conn: "psycopg.Connection[Any]", physical_name: str) -> None:
        statement = sql.SQL("DROP INDEX {name}").format(name=sql.Identifier(physical_name))
        with conn.cursor() as cur:
            _run(cur, statement)

    def _read_schema_revision(self, conn: "psycopg.Connection[Any]") -> int:
        """Read-only counterpart to `_bump_revision` below (design docs/
        design/DESTRUCTIVE_CONFIRMATION_V1.md R-2 item 1, WP-0 m-1): a plain
        `SELECT` of the current `schema_revision`, in the SAME transaction
        as the pending schema operation, used to compute a `drop_entity`/
        `drop_index` confirmation phrase's own state fingerprint before the
        destructive-confirmation gate runs (and therefore before this same
        transaction's own `_bump_revision` call increments it again).
        `migrations/0003_provision_application.sql` inserts this table's one
        row (`revision = 0`) at provisioning time, so the `SELECT` always
        finds it in practice; the `0` fallback below exists only so this
        method never raises on a row that -- against that expectation --
        turns out to be missing, mirroring `_bump_revision`'s own
        insert-if-missing defensiveness without itself writing anything.
        """
        table = sql.Identifier(_REVISION_TABLE)
        select = sql.SQL("SELECT revision FROM {table}").format(table=table)
        with conn.cursor() as cur:
            _run(cur, select)
            row = cur.fetchone()
            return int(row[0]) if row is not None else 0

    def _bump_revision(self, conn: "psycopg.Connection[Any]") -> int:
        table = sql.Identifier(_REVISION_TABLE)
        update = sql.SQL("UPDATE {table} SET revision = revision + 1 RETURNING revision").format(table=table)
        with conn.cursor() as cur:
            _run(cur, update)
            row = cur.fetchone()
            if row is None:
                insert = sql.SQL("INSERT INTO {table} (id, revision) VALUES (TRUE, 1) RETURNING revision").format(table=table)
                _run(cur, insert)
                row = cur.fetchone()
            return int(row[0])

    # ---- session/timeout ---------------------------------------------------

    def _timeout_ms(self, limits: ResourceLimits, deadline: float | None, clock: "Callable[[], float] | None") -> int:
        budget_ms = limits.execution_ms
        if deadline is not None and clock is not None:
            remaining_ms = max(0.0, (deadline - clock()) * 1000)
            budget_ms = min(budget_ms, max(1, int(remaining_ms)))
        return max(1, int(budget_ms))

    def _set_timeouts(self, conn: "psycopg.Connection[Any]", timeout_ms: int) -> None:
        """One request = one transaction (D-5): `statement_timeout` and
        `lock_timeout` are set with `SET LOCAL`, so they apply only to the
        current transaction and are automatically discarded on commit or
        rollback -- never leaking onto the next transaction this pooled
        connection is reused for. The timeout value passed here is always a
        server-computed `int` (derived from `ResourceLimits.execution_ms`
        and the caller's deadline, never from request content), so
        `sql.Literal` -- necessary because PostgreSQL's `SET` grammar does
        not accept a bind placeholder in this position -- is composing a
        trusted value, not interpolating untrusted text.
        """
        statement_timeout = sql.SQL("SET LOCAL statement_timeout = {t}").format(t=sql.Literal(f"{timeout_ms}ms"))
        lock_timeout = sql.SQL("SET LOCAL lock_timeout = {t}").format(t=sql.Literal(f"{timeout_ms}ms"))
        with conn.cursor() as cur:
            _run(cur, statement_timeout)
            _run(cur, lock_timeout)


# Checked, not just claimed: `PostgresCell` must present the exact same call
# surface as `ApplicationCell` (design D-1). See `backend.py` for the
# equivalent assertion covering `ApplicationCell`.
assert issubclass(PostgresCell, _StorageBackend), "PostgresCell must conform to StorageBackend (design D-1)"

__all__ = ["PostgresCell", "SharedPoolManager", "default_pool_manager"]
