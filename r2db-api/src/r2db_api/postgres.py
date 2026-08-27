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
- No method on this class -- public or private -- accepts a `str` and
  executes it. `_run`, the single choke point every statement passes
  through, is typed to accept only `psycopg.sql.Composed`/`psycopg.sql.SQL`
  and raises `TypeError` for anything else. This is a type-level property of
  the file, not a convention: every SQL fragment built anywhere below is
  constructed via `sql.SQL(...)`/`sql.Identifier`/`sql.Literal`/
  `sql.Placeholder`, never an f-string or `%`-formatted plain string.

This module does not duplicate validation. Identifier syntax, the operator
allowlist, mutation shape, and destructive-confirmation logic are imported
from `r2db_api.structured` and are the exact same functions `ApplicationCell`
uses -- see that module's "Shared validation/planning boundary" section.
This file only adds what is inherently PostgreSQL-specific: catalog lookup
against a live schema, SQL composition, session/transaction/timeout
handling, and per-role connection pooling.

Data model: every field declared via `create_entity`/`add_field` becomes a
`JSONB` column. The common contract's structured operations do not carry
per-field types (`SchemaOperationRequest.field_type` is accepted by the
schema but not by this foundation's own operation-shape allowlist), and the
in-memory reference cell stores arbitrary JSON-shaped Python values per
field with no static typing -- JSONB is the direct PostgreSQL analogue that
preserves that same dynamic-value semantics. One consequence worth noting
for callers: JSONB has a total, defined ordering across all JSON types, so
`lt`/`lte`/`gt`/`gte` comparisons that would raise `TypeError` against
mismatched Python types in `ApplicationCell` typically do not raise here;
they instead produce a deterministic (if occasionally surprising)
`ORDER`-consistent boolean. This is a legitimate cross-backend semantic
difference the Security Invariants explicitly allow (implementations are
not required to share a physical data model), not a validation gap: both
backends still reject bad identifiers/operators/shapes identically.
"""
from __future__ import annotations

import json
import queue
import threading
from contextlib import contextmanager
from typing import Any, Callable, Iterator, Sequence

import psycopg
from psycopg import sql
from psycopg.pq import TransactionStatus
from psycopg.types.json import Jsonb

from .backend import StorageBackend as _StorageBackend
from .errors import fail
from .limits import ResourceLimits
from .structured import (
    Predicate,
    bind_mutation,
    bind_schema_operation,
    require_destructive_confirmation,
    validate_identifier,
    validate_predicates,
    validate_projection,
)

_REVISION_TABLE = "_r2db_schema_revision"

_COMPARISON_OPERATORS: dict[str, sql.SQL] = {
    "eq": sql.SQL("="),
    "ne": sql.SQL("<>"),
    "lt": sql.SQL("<"),
    "lte": sql.SQL("<="),
    "gt": sql.SQL(">"),
    "gte": sql.SQL(">="),
}


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

    def __init__(self, dsn: str, *, schema: str, maxconn: int = 4) -> None:
        self._dsn = dsn
        self._schema = schema
        self._maxconn = max(1, maxconn)
        self._queue: "queue.Queue[psycopg.Connection[Any]]" = queue.Queue(maxsize=self._maxconn)
        self._lock = threading.Lock()
        self._created = 0

    def _connect(self) -> "psycopg.Connection[Any]":
        conn = psycopg.connect(self._dsn, autocommit=False)
        with conn.cursor() as cur:
            _run(cur, sql.SQL("SET search_path TO {}").format(sql.Identifier(self._schema)))
        conn.commit()
        return conn

    def _acquire(self) -> "psycopg.Connection[Any]":
        try:
            return self._queue.get_nowait()
        except queue.Empty:
            pass
        with self._lock:
            if self._created < self._maxconn:
                self._created += 1
                return self._connect()
        return self._queue.get()

    @contextmanager
    def connection(self) -> Iterator["psycopg.Connection[Any]"]:
        conn = self._acquire()
        try:
            if conn.closed:
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
            recycled = False
            if keep and not conn.closed:
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


class PostgresCell:
    """A `StorageBackend` over one application's PostgreSQL schema.

    `application_id` and `schema` are supplied by the caller (the control
    plane), never derived from client request content (D-3: "physical
    schema name is assigned by the control plane, not derived from client
    input"). `runtime_dsn`/`developer_dsn` are two separate, already
    fully-formed connection strings authenticating as this application's
    `runtime` and `developer` PostgreSQL roles respectively (provisioned by
    `r2db-api/migrations/`, see `r2db-api/docs/`); this class never embeds a
    control-plane credential and never widens a connection's role at
    runtime, so schema-changing operations physically execute under the
    `developer` role (DDL-capable on this schema only) while queries and
    data mutations physically execute under the `runtime` role (DML only) --
    a second, DB-enforced layer under the `developer: bool` check already
    performed by `bind_schema_operation` (SI-03 defence in depth).
    """

    def __init__(self, application_id: str, schema: str, *, runtime_dsn: str, developer_dsn: str, runtime_role: str, developer_role: str, pool_size: int = 4) -> None:
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
        self._runtime = _RolePool(runtime_dsn, schema=schema, maxconn=pool_size)
        self._developer = _RolePool(developer_dsn, schema=schema, maxconn=pool_size)

    def close(self) -> None:
        self._runtime.close_all()
        self._developer.close_all()

    # ---- catalog -----------------------------------------------------

    def catalog(self) -> list[dict[str, Any]]:
        with self._runtime.connection() as conn:
            with conn.transaction():
                fields_by_entity = self._load_catalog(conn)
        return [{"entity": name, "fields": sorted(fields_by_entity[name])} for name in sorted(fields_by_entity)]

    def _load_catalog(self, conn: "psycopg.Connection[Any]") -> dict[str, set[str]]:
        """The catalog-verification step D-4 requires before any client
        identifier may be composed with `sql.Identifier`: this is the live
        set of tables/columns that actually exist in this application's
        schema right now, queried from `information_schema` (never from
        request content), inside the same transaction as the operation
        being validated.
        """
        statement = sql.SQL(
            "SELECT t.table_name, c.column_name "
            "FROM information_schema.tables t "
            "LEFT JOIN information_schema.columns c "
            "ON c.table_schema = t.table_schema AND c.table_name = t.table_name "
            "WHERE t.table_schema = {schema} AND t.table_type = 'BASE TABLE' AND t.table_name <> {revision_table}"
        ).format(schema=sql.Placeholder(), revision_table=sql.Placeholder())
        with conn.cursor() as cur:
            _run(cur, statement, [self.schema, _REVISION_TABLE])
            rows = cur.fetchall()
        result: dict[str, set[str]] = {}
        for table_name, column_name in rows:
            fields = result.setdefault(table_name, set())
            if column_name is not None:
                fields.add(column_name)
        return result

    # ---- query ---------------------------------------------------------

    def query(self, entity: str, *, select: list[str], where: list[Predicate], page_size: int, limits: ResourceLimits, deadline: float | None = None, clock: Callable[[], float] | None = None) -> list[dict[str, Any]]:
        if deadline is not None and clock is not None:
            limits.check_deadline(deadline, clock)
        validate_identifier(entity)
        if page_size <= 0:
            fail("LIMIT_EXCEEDED", "Page size must be positive.", status=413, details={"resource": "result_items", "limit": limits.result_items})
        with self._runtime.connection() as conn:
            timeout_ms = self._timeout_ms(limits, deadline, clock)
            try:
                with conn.transaction():
                    self._set_timeouts(conn, timeout_ms)
                    catalog = self._load_catalog(conn)
                    if entity not in catalog:
                        fail("NOT_FOUND", "Entity was not found.", status=404)
                    known_fields = catalog[entity]
                    validate_projection(select, known_fields)
                    validate_predicates(where, known_fields)
                    limits.check("query_complexity", len(where) + len(select))
                    where_sql, where_params = self._where_clause(where)
                    statement = self._select_statement(entity, select, where_sql, page_size)
                    with conn.cursor() as cur:
                        _run(cur, statement, where_params)
                        rows = cur.fetchall()
            except psycopg.errors.QueryCanceled:
                fail("LIMIT_EXCEEDED", "Operation exceeds the execution budget.", status=413, details={"resource": "execution_ms", "limit": limits.execution_ms})
            except psycopg.errors.LockNotAvailable:
                fail("LIMIT_EXCEEDED", "Operation exceeds the execution budget.", status=413, details={"resource": "execution_ms", "limit": limits.execution_ms})
            except psycopg.Error:
                fail("SERVICE_UNAVAILABLE", "The database could not complete the request.", status=503)
        limits.check("result_items", min(len(rows), page_size))
        if deadline is not None and clock is not None:
            limits.check_deadline(deadline, clock)
        return [dict(zip(select, row)) for row in rows]

    def _select_statement(self, entity: str, select: list[str], where_sql: sql.Composed | None, page_size: int) -> sql.Composed:
        columns = sql.SQL(", ").join(sql.Identifier(f) for f in select)
        statement = sql.SQL("SELECT {columns} FROM {table}").format(columns=columns, table=sql.Identifier(entity))
        if where_sql is not None:
            statement = sql.SQL("{base} WHERE {where}").format(base=statement, where=where_sql)
        return sql.SQL("{base} LIMIT {limit}").format(base=statement, limit=sql.Literal(int(page_size)))

    # ---- mutations -------------------------------------------------------

    def transact(self, entity: str, operations: list[dict[str, Any]], limits: ResourceLimits, *, deadline: float | None = None, clock: Callable[[], float] | None = None) -> int:
        if deadline is not None and clock is not None:
            limits.check_deadline(deadline, clock)
        validate_identifier(entity)
        if not operations:
            fail("VALIDATION_FAILED", "At least one mutation is required.")
        limits.check("batch_items", len(operations))
        affected = 0
        with self._runtime.connection() as conn:
            timeout_ms = self._timeout_ms(limits, deadline, clock)
            try:
                with conn.transaction():
                    self._set_timeouts(conn, timeout_ms)
                    catalog = self._load_catalog(conn)
                    if entity not in catalog:
                        fail("NOT_FOUND", "Entity was not found.", status=404)
                    known_fields = catalog[entity]
                    for operation in operations:
                        affected += self._apply(conn, entity, operation, known_fields)
                        limits.check("result_items", affected)
                    if deadline is not None and clock is not None:
                        limits.check_deadline(deadline, clock)
            except psycopg.errors.QueryCanceled:
                fail("LIMIT_EXCEEDED", "Operation exceeds the execution budget.", status=413, details={"resource": "execution_ms", "limit": limits.execution_ms})
            except psycopg.errors.LockNotAvailable:
                fail("LIMIT_EXCEEDED", "Operation exceeds the execution budget.", status=413, details={"resource": "execution_ms", "limit": limits.execution_ms})
            except psycopg.Error:
                fail("SERVICE_UNAVAILABLE", "The database could not complete the request.", status=503)
        # `conn.transaction()` rolls back the *entire* batch on any
        # exception (including a `FoundationError` raised by a later
        # operation), giving the whole batch one real database transaction
        # (D-5) in place of `ApplicationCell`'s in-memory deepcopy/restore.
        return affected

    def _apply(self, conn: "psycopg.Connection[Any]", entity: str, operation: dict[str, Any], known_fields: set[str]) -> int:
        bound = bind_mutation(operation, known_fields)
        table = sql.Identifier(entity)
        if bound.operation == "insert":
            return self._insert(conn, table, bound.values)
        where_sql, where_params = self._where_clause(bound.where)
        if bound.operation == "delete":
            require_destructive_confirmation(bound.destructive, bound.confirmation, "DELETE", "Delete requires explicit destructive confirmation.")
            return self._delete(conn, table, where_sql, where_params)
        updated = self._update(conn, table, bound.values, where_sql, where_params)
        if bound.operation == "upsert" and updated == 0:
            return self._insert(conn, table, bound.values)
        return updated

    def _insert(self, conn: "psycopg.Connection[Any]", table: sql.Identifier, values: dict[str, Any]) -> int:
        if not values:
            statement = sql.SQL("INSERT INTO {table} DEFAULT VALUES").format(table=table)
            params: list[Any] = []
        else:
            columns = sql.SQL(", ").join(sql.Identifier(key) for key in values)
            placeholders = sql.SQL(", ").join(sql.Placeholder() for _ in values)
            statement = sql.SQL("INSERT INTO {table} ({columns}) VALUES ({placeholders})").format(table=table, columns=columns, placeholders=placeholders)
            params = [Jsonb(v) for v in values.values()]
        with conn.cursor() as cur:
            _run(cur, statement, params)
        return 1

    def _update(self, conn: "psycopg.Connection[Any]", table: sql.Identifier, values: dict[str, Any], where_sql: sql.Composed | None, where_params: list[Any]) -> int:
        if not values:
            return self._count(conn, table, where_sql, where_params)
        assignments = sql.SQL(", ").join(sql.SQL("{col} = {ph}").format(col=sql.Identifier(key), ph=sql.Placeholder()) for key in values)
        statement = sql.SQL("UPDATE {table} SET {assignments}").format(table=table, assignments=assignments)
        params = [Jsonb(v) for v in values.values()]
        if where_sql is not None:
            statement = sql.SQL("{base} WHERE {where}").format(base=statement, where=where_sql)
            params = params + where_params
        with conn.cursor() as cur:
            _run(cur, statement, params)
            return cur.rowcount

    def _delete(self, conn: "psycopg.Connection[Any]", table: sql.Identifier, where_sql: sql.Composed | None, where_params: list[Any]) -> int:
        statement = sql.SQL("DELETE FROM {table}").format(table=table)
        params: list[Any] = []
        if where_sql is not None:
            statement = sql.SQL("{base} WHERE {where}").format(base=statement, where=where_sql)
            params = where_params
        with conn.cursor() as cur:
            _run(cur, statement, params)
            return cur.rowcount

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

    # ---- predicate/WHERE composition ------------------------------------

    def _where_clause(self, where: list[Predicate]) -> tuple[sql.Composed | None, list[Any]]:
        if not where:
            return None, []
        fragments: list[sql.Composed] = []
        params: list[Any] = []
        for predicate in where:
            fragment, values = self._predicate_sql(predicate)
            fragments.append(fragment)
            params.extend(values)
        return sql.SQL(" AND ").join(fragments), params

    def _predicate_sql(self, predicate: Predicate) -> tuple[sql.Composed, list[Any]]:
        column = sql.Identifier(predicate.field)
        if predicate.operator == "is_null":
            return sql.SQL("{col} IS NULL").format(col=column), []
        if predicate.operator == "in":
            if not isinstance(predicate.value, list) or not predicate.value:
                fail("VALIDATION_FAILED", "Filter value is incompatible with the selected operator.")
            placeholders = sql.SQL(", ").join(sql.Placeholder() for _ in predicate.value)
            return sql.SQL("{col} IN ({items})").format(col=column, items=placeholders), [Jsonb(v) for v in predicate.value]
        if predicate.operator == "contains":
            needle = predicate.value if isinstance(predicate.value, str) else _json_text(predicate.value)
            return sql.SQL("{col}::text LIKE {ph}").format(col=column, ph=sql.Placeholder()), [f"%{needle}%"]
        operator = _COMPARISON_OPERATORS.get(predicate.operator)
        if operator is None:
            # Unreachable in practice: `predicate.validate()` (called by
            # `validate_predicates`, upstream of every caller here) already
            # rejects any operator outside `structured.OPERATORS`. Kept as
            # an explicit, fixed-literal-only fallback rather than trusting
            # that invariant silently (D-4: "operators map to fixed
            # literals").
            fail("VALIDATION_FAILED", "Unsupported filter operator.", details={"field": predicate.field})
        return sql.SQL("{col} {op} {ph}").format(col=column, op=operator, ph=sql.Placeholder()), [Jsonb(predicate.value)]

    # ---- schema ----------------------------------------------------------

    def apply_schema(self, operation: dict[str, Any], *, developer: bool, limits: ResourceLimits, deadline: float | None = None, clock: Callable[[], float] | None = None) -> int:
        bound = bind_schema_operation(operation, developer=developer)
        with self._developer.connection() as conn:
            timeout_ms = self._timeout_ms(limits, deadline, clock)
            try:
                with conn.transaction():
                    self._set_timeouts(conn, timeout_ms)
                    catalog = self._load_catalog(conn)
                    current_objects = sum(len(fields) + 1 for fields in catalog.values())
                    if bound.operation == "create_entity":
                        projected = current_objects + 1 + len(bound.fields)
                    elif bound.operation == "add_field":
                        projected = current_objects + 1
                    else:  # drop_entity
                        projected = current_objects - (len(catalog.get(bound.entity, set())) + 1)
                    limits.check("schema_objects", projected)
                    if deadline is not None and clock is not None:
                        limits.check_deadline(deadline, clock)
                    if bound.operation == "create_entity":
                        if bound.entity in catalog:
                            fail("CONFLICT", "Entity already exists.", status=409)
                        self._create_entity(conn, bound.entity, bound.fields)
                    elif bound.operation == "drop_entity":
                        if bound.entity not in catalog:
                            fail("NOT_FOUND", "Entity was not found.", status=404)
                        require_destructive_confirmation(bound.destructive, bound.confirmation, "DROP_ENTITY", "Drop requires explicit destructive confirmation.")
                        self._drop_entity(conn, bound.entity)
                    else:  # add_field
                        if bound.entity not in catalog:
                            fail("NOT_FOUND", "Entity was not found.", status=404)
                        if bound.field in catalog.get(bound.entity, set()):
                            fail("CONFLICT", "Field already exists.", status=409)
                        self._add_field(conn, bound.entity, bound.field)
                    revision = self._bump_revision(conn)
            except psycopg.errors.QueryCanceled:
                fail("LIMIT_EXCEEDED", "Operation exceeds the execution budget.", status=413, details={"resource": "execution_ms", "limit": limits.execution_ms})
            except psycopg.errors.LockNotAvailable:
                fail("LIMIT_EXCEEDED", "Operation exceeds the execution budget.", status=413, details={"resource": "execution_ms", "limit": limits.execution_ms})
            except psycopg.Error:
                fail("SERVICE_UNAVAILABLE", "The database could not complete the request.", status=503)
        return revision

    def _create_entity(self, conn: "psycopg.Connection[Any]", entity: str, fields: tuple[str, ...]) -> None:
        if fields:
            columns = sql.SQL(", ").join(sql.SQL("{col} JSONB").format(col=sql.Identifier(f)) for f in fields)
            statement = sql.SQL("CREATE TABLE {table} ({columns})").format(table=sql.Identifier(entity), columns=columns)
        else:
            statement = sql.SQL("CREATE TABLE {table} ()").format(table=sql.Identifier(entity))
        with conn.cursor() as cur:
            _run(cur, statement)
            self._apply_row_level_security(cur, entity)

    def _apply_row_level_security(self, cur: "psycopg.Cursor[Any]", entity: str) -> None:
        """D-3's third layer: RLS as defence-in-depth underneath schema
        separation and the two distinct DB roles. Schema+role separation
        already makes cross-application access structurally unreachable (a
        role never receives any grant on another application's schema at
        all), so this policy's job is to survive a *future* misconfiguration
        -- e.g. an accidental broader grant, or a schema-per-application
        assumption someday collapsing to a shared schema -- rather than to
        be the primary control. It restricts every row in every table this
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

    def _drop_entity(self, conn: "psycopg.Connection[Any]", entity: str) -> None:
        statement = sql.SQL("DROP TABLE {table}").format(table=sql.Identifier(entity))
        with conn.cursor() as cur:
            _run(cur, statement)

    def _add_field(self, conn: "psycopg.Connection[Any]", entity: str, field: str) -> None:
        statement = sql.SQL("ALTER TABLE {table} ADD COLUMN {col} JSONB").format(table=sql.Identifier(entity), col=sql.Identifier(field))
        with conn.cursor() as cur:
            _run(cur, statement)

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


def _json_text(value: Any) -> str:
    return json.dumps(value, sort_keys=True)


# Checked, not just claimed: `PostgresCell` must present the exact same call
# surface as `ApplicationCell` (design D-1). See `backend.py` for the
# equivalent assertion covering `ApplicationCell`.
assert issubclass(PostgresCell, _StorageBackend), "PostgresCell must conform to StorageBackend (design D-1)"

__all__ = ["PostgresCell"]
