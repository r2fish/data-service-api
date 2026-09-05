"""Phase 4 ledger closure WP-B3 (L4-6, design P4-D17 -- 作業指示書
WORK_ORDER_PHASE4_LEDGER_CLOSURE_V1.md §1 L4-6 が正本): the HTTP
conformance adapter (`conformance_adapter_r2db_http.py`) constructs its own
`PostgresApplicationAuditSink` writer connection ad hoc, inside its own
`__init__` (`:862-865`), never through `r2db_api.main.build_app` -- the
existing composition-root timeout tests
(`test_application_audit.py:499`/`:563`) never exercise THIS object at all.
A mutation dropping either `statement_timeout_ms=`/
`idle_in_transaction_session_timeout_ms=` keyword from that adapter
construction call site would previously survive both `r2db-api/tests` (no
test touches this object) and `conformance-tests` (backend-agnostic, no
PostgreSQL session-setting assertions) undetected.

Same method the existing composition-root tests already use (`P4-D17`):
build the REAL adapter, borrow a connection from ITS OWN sink's pool, and
`SHOW statement_timeout` / `SHOW idle_in_transaction_session_timeout` --
not a hand-constructed stand-in `PostgresApplicationAuditSink` (which would
only prove the sink class itself works, never that the adapter's own
construction call site actually passes the two keywords -- exactly P4-D17
review point 1).

Distinguishable from the untouched server default (P4-D17 review point 2):
this test reads the real cluster's own compiled-in default via a bare
admin connection FIRST, then asserts the adapter's own value differs from
it (not merely "is truthy") -- the module-level default the adapter always
requests (`DEFAULT_AUDIT_STATEMENT_TIMEOUT_MS`/`DEFAULT_AUDIT_IDLE_TIMEOUT_
MS`, both 5000ms) is asserted for its literal value too, so a mutation
that drops the kwargs (falling back to the server's own default, typically
"0" = disabled) goes red on both assertions.

Building the real `R2DBHttpConformanceAdapter` is heavyweight (provisions
a throwaway PostgreSQL platform database + roles, runs every migration) --
this is unavoidable: it is the only way to observe the object the adapter
itself constructs, not a second, adapter-shaped stand-in (P4-D17 review
point 1's exact concern). `adapter.close()` in `finally` sweeps every
throwaway artifact this test creates, mirroring the conformance suite's
own established per-adapter teardown discipline.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "conformance"))

# Phase 6 WP-2 (design docs/design/PHASE6_CONTRACT_160_CLIENT_DISCOVERY_
# V1.md D-2): `conformance_adapter_r2db_http` imports `r2db_api.control_
# main`, whose module-level `app = build_control_app()` reads real
# `os.environ` the instant that module is first imported in this process
# -- `R2DB_DATA_BASE_URL`/`R2DB_CONTROL_BASE_URL` are now required there.
# `setdefault` (never overwriting an already-set value) mirrors `test_
# audit_query.py`'s own identical placeholder pattern for the SAME
# import-order hazard -- these values are never actually read by anything
# this test constructs (the real adapter builds its own control stack via
# `assemble_control_stack(..., surfaces=_SURFACES)`, not `build_control_
# app`), they exist only to satisfy the module-level side effect.
os.environ.setdefault("R2DB_DATA_BASE_URL", "https://r2db-http-writer-timeouts-test.example.invalid/v1")
os.environ.setdefault("R2DB_CONTROL_BASE_URL", "https://r2db-http-writer-timeouts-control-test.example.invalid/control/v1")

import psycopg  # noqa: E402

import conformance_adapter_r2db_http as _http_module  # noqa: E402
from r2db_api.credential_store import (  # noqa: E402
    DEFAULT_AUDIT_IDLE_TIMEOUT_MS,
    DEFAULT_AUDIT_STATEMENT_TIMEOUT_MS,
)
from r2db_api.pg_timeouts import ms_from_pg_timeout_text  # noqa: E402

ADMIN_DSN_ENV = "R2DB_TEST_ADMIN_DSN"
ADMIN_DSN_DEFAULT = "host=/tmp port=5432 dbname=postgres"


def _admin_dsn() -> str:
    return os.environ.get(ADMIN_DSN_ENV, ADMIN_DSN_DEFAULT)


def _show(conn: "psycopg.Connection", setting: str) -> str:
    with conn.cursor() as cur:
        cur.execute(f"SHOW {setting}")
        return cur.fetchone()[0]


def test_http_conformance_adapter_audit_writer_connection_has_statement_and_idle_timeouts_set() -> None:
    with psycopg.connect(_admin_dsn()) as admin_conn:
        cluster_default_statement_timeout_ms = ms_from_pg_timeout_text(_show(admin_conn, "statement_timeout"))
        cluster_default_idle_timeout_ms = ms_from_pg_timeout_text(_show(admin_conn, "idle_in_transaction_session_timeout"))

    adapter = _http_module.build_adapter()
    try:
        with adapter._application_durable_audit._pool.connection() as conn:  # noqa: SLF001 -- adapter-internal reach-in, test-only (mirrors test_application_audit.py's own established convention)
            statement_timeout_ms = ms_from_pg_timeout_text(_show(conn, "statement_timeout"))
            idle_timeout_ms = ms_from_pg_timeout_text(_show(conn, "idle_in_transaction_session_timeout"))
    finally:
        adapter.close()

    assert statement_timeout_ms == DEFAULT_AUDIT_STATEMENT_TIMEOUT_MS
    assert idle_timeout_ms == DEFAULT_AUDIT_IDLE_TIMEOUT_MS
    # Distinguishable from the untouched server default -- otherwise a
    # mutation dropping the adapter's own kwargs would coincidentally still
    # read as "configured" (P4-D17 review point 2).
    assert statement_timeout_ms != cluster_default_statement_timeout_ms
    assert idle_timeout_ms != cluster_default_idle_timeout_ms
