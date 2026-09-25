"""PostgreSQL SELECT/WHERE statement assembly for `PostgresCell` (R-37
WP-4c, PG3 + PG2 + `_bind_value`, design `MODULE_REFACT_ARCHITECTURE_V1.md`
D-4: "SQL builder は capability を持たない").

A pure leaf: every function here takes already-validated request-derived
values (a `Predicate`, a column name, a bound value, an already-decided
page_size/order_spec/cursor-position) and returns a `psycopg.sql`
fragment, a (fragment, params) pair, or a bound parameter value -- none of
them opens a connection, calls `_run`, or reads a principal, a capability
document, or the catalog. `postgres.PostgresCell` keeps a delegation
attribute for each of the eight functions (the `_select_statement =
staticmethod(_select_statement)` form); its existing call sites
(`query`/`_apply`/`_insert`/`_update`/`_delete`/`_apply_upsert`/
`apply_schema`) keep the same `self.`-qualified form --
`_select_statement`/`_append_revision_predicate` each gain one
`revision_column` argument, taking the revision column name as a required
argument instead of reading a module constant, so this module never
imports `postgres.py` (which would be circular). `_run`, transaction/lock
ownership, and driver-exception mapping all stay in `postgres.py`.
"""
from __future__ import annotations

from typing import Any

from psycopg import sql
from psycopg.types.json import Jsonb

from .errors import fail, violation
from .postgres_like import _escape_like_literal

_COMPARISON_OPERATORS: dict[str, sql.SQL] = {
    "eq": sql.SQL("="),
    "ne": sql.SQL("<>"),
    "lt": sql.SQL("<"),
    "lte": sql.SQL("<="),
    "gt": sql.SQL(">"),
    "gte": sql.SQL(">="),
}


def _select_statement(
    entity: str,
    select: list[str],
    where_sql: sql.Composed | None,
    order_spec: list[tuple[str, str]],
    page_size: int,
    revision_column: str,
) -> sql.Composed:
    columns = sql.SQL(", ").join(sql.Identifier(f) for f in select)
    revision = sql.SQL("{col}::text").format(col=sql.Identifier(revision_column))
    statement = sql.SQL("SELECT {columns}, {revision} FROM {table}").format(columns=columns, revision=revision, table=sql.Identifier(entity))
    if where_sql is not None:
        statement = sql.SQL("{base} WHERE {where}").format(base=statement, where=where_sql)
    statement = sql.SQL("{base} ORDER BY {order}").format(base=statement, order=_order_by_sql(order_spec))
    # NULL placement (ASC -> NULLS LAST, DESC -> NULLS FIRST) is PostgreSQL's own default when no NULLS clause is given, which is exactly the semantics `ApplicationCell._sort_key` was written to match -- no explicit NULLS FIRST/LAST needed here. Likewise, a
    # plain (untyped/JSONB) column's own cross-type ordering (ascending:
    # String < Number < Boolean < Array < Object) falls directly out of
    # PostgreSQL's native `jsonb` comparison operators.
    #
    # keyset paging (design D-3 (4)): the caller's own keyset predicate (if
    # any) is already folded into `where_sql` above, so this statement's
    # own `LIMIT` is a look-ahead `size+1`, with no `OFFSET` clause.
    # `page_size` is always a server-computed, already-validated positive
    # integer (never client-supplied text) by this point -- `sql.Literal`
    # here is composing a trusted value, the same pattern `_set_timeouts`
    # already uses for its own computed values.
    # history: CH-0026
    return sql.SQL("{base} LIMIT {limit}").format(base=statement, limit=sql.Literal(int(page_size) + 1))


def _keyset_predicate_sql(order_spec: list[tuple[str, str]], cursor_values: list[Any], field_types: dict[str, str | None]) -> tuple[sql.Composed, list[Any]]:
    """The keyset predicate that replaces `OFFSET` (design D-3 (4)): the
    dictionary/lexicographic expansion of `order_spec` against the last
    page's own ordering values `cursor_values` --

        (f1 >op1> v1)
        OR (f1 =eq= v1 AND f2 >op2> v2)
        OR (f1 =eq= v1 AND f2 =eq= v2 AND ... AND id > vid)

    with each term's comparison branched on whether its own cursor value
    is NULL, so NULL is treated as the largest value in both directions
    (asc -> NULLS LAST, desc -> NULLS FIRST -- PostgreSQL's own default,
    the same total order `inmemory_sort._sort_key` gives the in-memory
    cell). `cursor_values` is index-aligned with `order_spec` (tie-break
    included) and has already passed `paging.decode_and_check_page_
    cursor`'s own count/type check, so every zip below is total.
    """
    clauses: list[sql.Composed] = []
    params: list[Any] = []
    for i, (field_name, direction) in enumerate(order_spec):
        column = sql.Identifier(field_name)
        term_parts: list[sql.Composed] = []
        for j in range(i):
            prior_field, _prior_direction = order_spec[j]
            prior_value = cursor_values[j]
            prior_column = sql.Identifier(prior_field)
            if prior_value is None:
                term_parts.append(sql.SQL("{col} IS NULL").format(col=prior_column))
            else:
                term_parts.append(sql.SQL("{col} = {ph}").format(col=prior_column, ph=sql.Placeholder()))
                params.append(_bind_value(prior_value, field_types.get(prior_field)))
        value = cursor_values[i]
        if value is None:
            greater = sql.SQL("FALSE") if direction == "asc" else sql.SQL("{col} IS NOT NULL").format(col=column)
        else:
            operator = sql.SQL(">") if direction == "asc" else sql.SQL("<")
            if direction == "asc":
                greater = sql.SQL("(({col} IS NOT NULL AND {col} {op} {ph}) OR {col} IS NULL)").format(col=column, op=operator, ph=sql.Placeholder())
            else:
                greater = sql.SQL("({col} IS NOT NULL AND {col} {op} {ph})").format(col=column, op=operator, ph=sql.Placeholder())
            params.append(_bind_value(value, field_types.get(field_name)))
        term_parts.append(greater)
        clauses.append(sql.SQL(" AND ").join(term_parts))
    return sql.SQL("(") + sql.SQL(" OR ").join(clauses) + sql.SQL(")"), params


def _order_by_sql(order_spec: list[tuple[str, str]]) -> sql.Composed:
    parts = [
        sql.SQL("{col} {direction}").format(col=sql.Identifier(field_name), direction=sql.SQL("ASC" if direction == "asc" else "DESC"))
        for field_name, direction in order_spec
    ]
    return sql.SQL(", ").join(parts)


def _bind_value(value: Any, field_type: str | None) -> Any:
    """R-7 addendum (M-B, confirmed empirically against a real server): a JSON `null` must bind as SQL `NULL` for every column shape, typed or untyped -- `Jsonb(None)` would instead produce the JSONB literal `'null'::jsonb` for an untyped column, which would make `is_null` predicates and `order_by` NULL placement diverge from `ApplicationCell`'s own null semantics. A non-null value binds as a native parameter for a scalar-typed column (`string`/`integer`/`number`/`boolean`) or wrapped in `Jsonb(...)` for an untyped column *or* an `object`/`array` one -- the latter two are still physically `jsonb` underneath their DOMAIN (object/array DOMAIN unification), so psycopg must still be told to serialize the value as jsonb, exactly as for an untyped column.

    History: CH-0041
    """
    if value is None:
        return None
    if field_type is None or field_type in ("object", "array"):
        return Jsonb(value)
    return value


def _append_revision_predicate(where_sql: sql.Composed | None, where_params: list[Any], expected_revision: str | None, revision_column: str) -> tuple[sql.Composed | None, list[Any]]:
    """an `expected_revision` precondition is folded into the same WHERE clause as the caller's own predicate (`<predicate> AND _r2db_revision::text = $expected`), so the comparison and the write are one atomic statement (the contract's revision-precondition clause 5) rather than a separate read-then-write.

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

    History: CH-0045
    """
    if expected_revision is None:
        return where_sql, list(where_params)
    revision_clause = sql.SQL("{col}::text = {ph}").format(col=sql.Identifier(revision_column), ph=sql.Placeholder())
    combined = sql.SQL("{w} AND {r}").format(w=where_sql, r=revision_clause) if where_sql is not None else revision_clause
    return combined, list(where_params) + [expected_revision]


def _where_clause(where: list[Predicate], field_types: dict[str, str | None]) -> tuple[sql.Composed | None, list[Any]]:
    if not where:
        return None, []
    fragments: list[sql.Composed] = []
    params: list[Any] = []
    for predicate in where:
        fragment, values = _predicate_sql(predicate, field_types.get(predicate.field))
        fragments.append(fragment)
        params.extend(values)
    return sql.SQL(" AND ").join(fragments), params


def _text_expression(column: sql.Identifier, field_type: str | None) -> sql.Composed:
    """The text form of `column` that `contains`/`matches` compare
    against. "非 text 列は従来どおり ::text に対して適用" -- a typed non-text column's plain `::text` cast is exactly this (a numeric/boolean column's text representation carries no quoting ambiguity). An *untyped* (JSONB-equivalent) column is different:
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

    History: CH-0053
    """
    if field_type is None:
        return sql.SQL("(") + column + sql.SQL(" #>> '{}')")
    return column + sql.SQL("::text")


def _predicate_sql(predicate: Predicate, field_type: str | None) -> tuple[sql.Composed, list[Any]]:
    column = sql.Identifier(predicate.field)
    if predicate.operator == "is_null":
        return sql.SQL("{col} IS NULL").format(col=column), []
    if predicate.operator == "in":
        # M-3 (rulings addendum 2)/R-2: unreachable in practice -- both
        # call sites of `_where_clause` (`query`/`_apply` above (in `postgres.py`)) already
        # run `_validate_predicate_types` first, which now rejects an
        # empty/non-list `in` value at the shared choke point before
        # any SQL is built. Kept as a defensive fallback with the same
        # 4-key vocabulary that choke point uses (never a bare
        # `fail()`), mirroring `_predicate_sql`'s "Unsupported filter
        # operator" fallback below.
        if not isinstance(predicate.value, list) or not predicate.value:
            fail("VALIDATION_FAILED", "Filter value is incompatible with the selected operator.", details=violation("request_schema", field="where"))
        placeholders = sql.SQL(", ").join(sql.Placeholder() for _ in predicate.value)
        # each element gets the same per-column type-aware bind (native for a typed column, `Jsonb(...)` for an untyped one, SQL NULL for a JSON null) as every other value position -- never a blanket `Jsonb(v)`.
        # history: CH-0054
        return sql.SQL("{col} IN ({items})").format(col=column, items=placeholders), [_bind_value(v, field_type) for v in predicate.value]
    if predicate.operator in ("contains", "matches"):
        text_column = _text_expression(column, field_type)
        if predicate.operator == "contains":
            # literal substring containment -- `%`/`_`/`\` in the value are escaped before being wrapped in `%...%`, so no character of the value is ever interpreted as a wildcard. `_validate_predicate_types`
            # (called by every caller of this method) has already
            # required `predicate.value` to be a string by this point.
            # history: CH-0055
            escaped = _escape_like_literal(predicate.value)
            pattern = f"%{escaped}%"
        else:
            # the client's pattern already uses exactly SQL LIKE's own wildcard grammar (`%`/`_`/`\`-escape) -- bound as-is, no transformation.
            # history: CH-0056
            pattern = predicate.value
        return sql.SQL("{col} LIKE {ph} ESCAPE '\\'").format(col=text_column, ph=sql.Placeholder()), [pattern]
    operator = _COMPARISON_OPERATORS.get(predicate.operator)
    if operator is None:
        # Unreachable in practice: `predicate.validate()` (called by
        # `validate_predicates`, upstream of every caller here) already
        # rejects any operator outside `structured.OPERATORS` (now in `mutation_binding.py`). Kept as
        # an explicit, fixed-literal-only fallback rather than trusting
        # that invariant silently (D-4: "operators map to fixed
        # literals"). this is a redundant application-level shape backstop, not a storage-rejection translation -- so it is NOT allowlist-eligible (`layer_rule`'s defence-in-depth exemption is for backend/storage denials only); it carries the same 4-key vocabulary `Predicate.validate`'s own operator check uses (`errors.violation("capability", ...)`), no field-index available this deep, so a generic `"where"` path.
        # history: CH-0057
        fail("VALIDATION_FAILED", "Unsupported filter operator.", details=violation("capability", field="where"))
    return sql.SQL("{col} {op} {ph}").format(col=column, op=operator, ph=sql.Placeholder()), [_bind_value(predicate.value, field_type)]
