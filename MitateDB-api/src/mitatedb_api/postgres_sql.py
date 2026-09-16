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
"""

from psycopg import sql

from .backend import SQL_OPERATOR_TOKENS

# m-7: operator-token and ORDER BY direction lookups, precomposed as
# `sql.SQL` constants (never a bare Python string concatenated with `+`
# into a statement fragment).
_OPERATOR_SQL = {name: sql.SQL(token) for name, token in SQL_OPERATOR_TOKENS.items()}
_DIRECTION_SQL = {"asc": sql.SQL("ASC"), "desc": sql.SQL("DESC")}


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
