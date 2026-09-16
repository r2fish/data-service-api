"""Phase 4 ledger closure WP-B3 (L4-6, design P4-D17) originally added this
file because the HTTP conformance adapter (`conformance_adapter_r2db_http.
py`) constructs its own `PostgresApplicationAuditSink` writer connection ad
hoc, inside its own `__init__`, never through `r2db_api.main.build_app` --
a mutation dropping either timeout keyword from that adapter construction
call site would previously survive both `r2db-api/tests` and
`conformance-tests` undetected.

Q4 phase WP-1 (design docs/design/Q4_DB_SIDE_SINGLE_TRUTH_V1.md D-1(b), work
order docs/work-orders/WORK_ORDER_Q4_DB_SIDE_SINGLE_TRUTH_V1.md WP-1 change
table D): `PostgresApplicationAuditSink.__init__` no longer HAS a
`statement_timeout_ms`/`idle_in_transaction_session_timeout_ms` keyword at
all -- the mechanism L4-6 guarded against (a dropped keyword silently
reverting to the untouched cluster default) is now impossible to reintroduce
SILENTLY: passing either keyword back would raise `TypeError` immediately,
at the adapter's own construction call site, the instant that call runs (in
this repository's own `r2db-api/tests` suite, well before any conformance
run). This file is repurposed rather than deleted, to still guard the two
things that remain genuinely observable and worth pinning:

  1. The adapter's own writer connection genuinely carries NO explicit
     session-level override -- it reflects the SAME value a bare admin
     connection sees (this adapter's own throwaway platform database is
     provisioned only through migration `0007` (`MIGRATION_NAMES` in
     `conformance_adapter_r2db_http.py`), never `0008` -- design §3.11
     point 4: "r2db HTTP plugは...宣言表の読み出し経路を通らない" -- so
     `r2dbsvc_api`'s `pg_db_role_setting` role setting the REAL composition
     root relies on, migration 0008, is never applied here either; this
     connection is governed by the bare PostgreSQL cluster default, full
     stop). A regression that reintroduced a hardcoded SESSION `SET` at
     this ONE call site (bypassing the removed constructor parameter
     entirely, e.g. via a raw `cur.execute("SET ...")` some future edit
     adds back) would make this assertion fail.
  2. `PostgresApplicationAuditSink.__init__`'s signature genuinely no
     longer accepts either keyword (a regression guard against silently
     reintroducing the removed SESSION-`SET` mechanism as a compatibility
     shim, forbidden by work order §7 prohibition 8 -- "互換シムを作らな
     い。二形式受理を置かない").
"""
from __future__ import annotations

import inspect
import os
import pathlib
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "conformance"))

# Q4 phase WP-1 (design D-2(f)): `R2DB_DATA_BASE_URL`/`R2DB_CONTROL_BASE_
# URL` are REMOVED -- `r2db_api.control_main`'s module-level `app = build_
# control_app()` (triggered by `import conformance_adapter_r2db_http`
# below, which imports `r2db_api.control_main` for `assemble_control_
# stack`) now rejects them outright (F-2) if defined at all, so the two
# `os.environ.setdefault` calls a prior phase placed here are gone;
# `build_control_app()` itself remains zero-network after this phase too
# (see that module's own docstring), so this file's own import still never
# touches the network for that unused module-level `app`.

import psycopg  # noqa: E402

import conformance_adapter_r2db_http as _http_module  # noqa: E402
from r2db_api.credential_store import PostgresApplicationAuditSink  # noqa: E402

ADMIN_DSN_ENV = "R2DB_TEST_ADMIN_DSN"


def _admin_dsn() -> str:
    dsn = os.environ.get(ADMIN_DSN_ENV)
    if not dsn:
        raise RuntimeError(
            f"{ADMIN_DSN_ENV} is not set (or is empty). "
            "tools/testpg/dsa_testpg.py sets it for each test run; "
            "there is no shared-cluster default."
        )
    return dsn


def _show(conn: "psycopg.Connection", setting: str) -> str:
    with conn.cursor() as cur:
        cur.execute(f"SHOW {setting}")
        return cur.fetchone()[0]


def test_postgres_application_audit_sink_no_longer_accepts_a_timeout_kwarg() -> None:
    """Q4 phase WP-1 (design D-1(b), work order §7 prohibition 8): a
    regression guard against silently reintroducing the removed SESSION-
    `SET` mechanism as a compatibility shim -- `PostgresApplicationAuditSink.
    __init__` must not accept `statement_timeout_ms`/`idle_in_transaction_
    session_timeout_ms` (or ANY keyword named after either GUC) at all."""
    parameters = inspect.signature(PostgresApplicationAuditSink.__init__).parameters
    assert "statement_timeout_ms" not in parameters
    assert "idle_in_transaction_session_timeout_ms" not in parameters


def test_http_conformance_adapter_audit_writer_connection_has_no_explicit_session_override() -> None:
    """Q4 phase WP-1 (design §3.11 point 4): this adapter's own writer
    connection deliberately never exercises the DB-side role-setting
    mechanism (migration `0008` is never applied to its throwaway platform
    database) -- so its effective `statement_timeout`/`idle_in_transaction_
    session_timeout` must equal the SAME value a bare admin connection on
    the same cluster sees, proving neither this adapter's own construction
    call site NOR `_RolePool` issues any override at all."""
    with psycopg.connect(_admin_dsn()) as admin_conn:
        cluster_default_statement_timeout = _show(admin_conn, "statement_timeout")
        cluster_default_idle_timeout = _show(admin_conn, "idle_in_transaction_session_timeout")

    adapter = _http_module.build_adapter()
    try:
        with adapter._application_durable_audit._pool.connection() as conn:  # noqa: SLF001 -- adapter-internal reach-in, test-only (mirrors test_application_audit.py's own established convention)
            statement_timeout = _show(conn, "statement_timeout")
            idle_timeout = _show(conn, "idle_in_transaction_session_timeout")
    finally:
        adapter.close()

    assert statement_timeout == cluster_default_statement_timeout
    assert idle_timeout == cluster_default_idle_timeout


def test_http_conformance_adapter_never_mentions_the_removed_surface_env_vars() -> None:
    r"""Completion condition 14 (design D-2(f)): `grep -n "R2DB_DATA_BASE_URL
    \|R2DB_CONTROL_BASE_URL" conformance_adapter_r2db_http.py` must be 0
    hits -- the adapter no longer needs the two `os.environ.setdefault`
    placeholder calls a prior phase placed there (see this adapter file's
    own header comment)."""
    import re

    adapter_path = pathlib.Path(_http_module.__file__)
    text = adapter_path.read_text()
    hits = re.findall(r"R2DB_DATA_BASE_URL|R2DB_CONTROL_BASE_URL", text)
    assert hits == []
