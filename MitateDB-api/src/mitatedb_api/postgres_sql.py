"""PostgreSQL WHERE-fragment assembly for `PostgresBackend` (R-37 WP-4a,
BP3, design `MODULE_REFACT_ARCHITECTURE_V1.md` D-4: "SQL builder は
capability を持たない").

A pure leaf: `_where_sql` takes already-validated `Filter` values and
returns a `psycopg.sql` fragment plus its bound parameter list -- it never
opens a connection, never calls `_execute`, and never checks a principal,
capability, or catalog. `backend_postgres.py` keeps the delegation
attribute (`_where_sql = staticmethod(_where_sql)`) so its five existing
call sites (`update_in_transaction`/`delete_in_transaction`/`read`/
`update`/`delete`) are unchanged; `insert` never calls `_where_sql`. The
ORDER BY / LIMIT assembly, `_execute`, timeout, and driver-exception
translation in `read()` all stay in `backend_postgres.py`.

Design docs/design/PHASE11_KEYSET_PAGING_V1.md D-2a/D-3 (4): `_keyset_
predicate_sql` builds the dictionary/lexicographic keyset predicate that
replaces `OFFSET`, and `_NULLS_SQL` is the explicit `NULLS LAST`/`NULLS
FIRST` clause `read()`'s own ORDER BY assembly appends per term (asc ->
NULLS LAST, desc -> NULLS FIRST, matching PostgreSQL's own default so the
keyset predicate's NULL branch below agrees with the actual row order).
Both values `order_spec`/`cursor_values` reach here already validated and
already encoded by `cell.ApplicationCell` -- this module never checks a
value's declared type or domain.
"""

from psycopg import sql

from .backend import SQL_OPERATOR_TOKENS

# m-7: operator-token and ORDER BY direction lookups, precomposed as
# `sql.SQL` constants (never a bare Python string concatenated with `+`
# into a statement fragment).
_OPERATOR_SQL = {name: sql.SQL(token) for name, token in SQL_OPERATOR_TOKENS.items()}
_DIRECTION_SQL = {"asc": sql.SQL("ASC"), "desc": sql.SQL("DESC")}
_NULLS_SQL = {"asc": sql.SQL("NULLS LAST"), "desc": sql.SQL("NULLS FIRST")}


def _where_sql(filters):
    if not filters:
        return sql.SQL(""), []
    clauses = []
    params = []
    for item in filters:
        column = sql.Identifier(item.field)
        if item.operator == "in":
            placeholders = sql.SQL(", ").join(sql.Placeholder() for _ in item.value)
            clauses.append(sql.SQL("{} IN ({})").format(column, placeholders))
            params.extend(item.value)
        else:
            clauses.append(sql.SQL("{} {} %s").format(column, _OPERATOR_SQL[item.operator]))
            params.append(item.value)
    return sql.SQL(" WHERE ") + sql.SQL(" AND ").join(clauses), params


def _keyset_predicate_sql(order_spec, cursor_values):
    """The keyset predicate that replaces `OFFSET` (design D-3 (4)): the
    dictionary/lexicographic expansion of `order_spec` against the last
    page's own ordering values `cursor_values` --

        (f1 >op1> v1)
        OR (f1 =eq= v1 AND f2 >op2> v2)
        OR (f1 =eq= v1 AND f2 =eq= v2 AND ... AND _mdb_row > v_row)

    with each term's comparison branched on whether its own cursor value
    is NULL, so NULL is treated as the largest value in both directions
    (asc -> NULLS LAST, desc -> NULLS FIRST, `_NULLS_SQL` above).
    `cursor_values` is index-aligned with `order_spec` (the `_mdb_row`
    tie-break included) and has already passed `cell.ApplicationCell`'s
    own count/type check, so every zip below is total.
    """
    clauses = []
    params = []
    for i, (field_name, direction) in enumerate(order_spec):
        column = sql.Identifier(field_name)
        term_parts = []
        for j in range(i):
            prior_field, _prior_direction = order_spec[j]
            prior_value = cursor_values[j]
            prior_column = sql.Identifier(prior_field)
            if prior_value is None:
                term_parts.append(sql.SQL("{col} IS NULL").format(col=prior_column))
            else:
                term_parts.append(sql.SQL("{col} = %s").format(col=prior_column))
                params.append(prior_value)
        value = cursor_values[i]
        if value is None:
            greater = sql.SQL("FALSE") if direction == "asc" else sql.SQL("{col} IS NOT NULL").format(col=column)
        else:
            operator = sql.SQL(">") if direction == "asc" else sql.SQL("<")
            if direction == "asc":
                greater = sql.SQL("(({col} IS NOT NULL AND {col} {op} %s) OR {col} IS NULL)").format(col=column, op=operator)
            else:
                greater = sql.SQL("({col} IS NOT NULL AND {col} {op} %s)").format(col=column, op=operator)
            params.append(value)
        term_parts.append(greater)
        clauses.append(sql.SQL(" AND ").join(term_parts))
    return sql.SQL("(") + sql.SQL(" OR ").join(clauses) + sql.SQL(")"), params
