"""Phase 4 ledger closure WP-B3 (L4-6, design P4-D17 -- 作業指示書
WORK_ORDER_PHASE4_LEDGER_CLOSURE_V1.md §1 L4-6 が正本): the HTTP
conformance adapter (`conformance_adapter_mitatedb_http.py`) constructs its
own `PostgresApplicationAuditSink` writer connection ad hoc, inside its own
`__init__` (`:613-616`), never through `mitatedb_api.main.build_app` -- the
existing composition-root timeout tests
(`test_application_audit.py:491`/`:667`) never exercise THIS object at
all. A mutation dropping either `statement_timeout_ms=`/
`idle_in_transaction_session_timeout_ms=` keyword from that adapter
construction call site would previously survive both `MitateDB-api/tests`
(no test touches this object) and `conformance-tests` (backend-agnostic,
no PostgreSQL session-setting assertions) undetected.

Same method the existing composition-root tests already use (`P4-D17`):
build the REAL adapter, ask ITS OWN sink for a fresh connection
(`PostgresApplicationAuditSink._connect()` -- this peer's sink opens a new
connection per call rather than pooling, see `test_application_audit_
writer_connection_has_statement_and_idle_timeouts_set`'s own identical
`sink._connect()` pattern), and `SHOW statement_timeout` / `SHOW
idle_in_transaction_session_timeout` -- not a hand-constructed stand-in
`PostgresApplicationAuditSink` (which would only prove the sink class
itself works, never that the adapter's own construction call site actually
passes the two keywords -- exactly P4-D17 review point 1).

Distinguishable from the untouched server default (P4-D17 review point 2):
this test reads the real cluster's own compiled-in default via a bare
admin connection FIRST, then asserts the adapter's own value differs from
it -- the module-level default the adapter always requests
(`DEFAULT_AUDIT_STATEMENT_TIMEOUT_MS`/`DEFAULT_AUDIT_IDLE_TIMEOUT_MS`, both
5000ms) is asserted for its literal value too, so a mutation that drops
the kwargs (falling back to the server's own default, typically "0" =
disabled) goes red on both assertions.

Building the real `MitateDBHttpConformanceAdapter` is heavyweight
(provisions a throwaway PostgreSQL platform database + roles, runs every
migration) -- this is unavoidable: it is the only way to observe the
object the adapter itself constructs, not a second, adapter-shaped
stand-in (P4-D17 review point 1's exact concern). `adapter.close()` in
`finally` sweeps every throwaway artifact this test creates, mirroring the
conformance suite's own established per-adapter teardown discipline (also
this file's own sibling `test_conformance_adapter_mitatedb_http_sweep_
scope.py`'s `sys.path` convention).
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "conformance"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "conformance-tests"))

import psycopg  # noqa: E402

import conformance_adapter_mitatedb_http as _http_module  # noqa: E402
from mitatedb_api.application_audit import (  # noqa: E402
    DEFAULT_AUDIT_IDLE_TIMEOUT_MS,
    DEFAULT_AUDIT_STATEMENT_TIMEOUT_MS,
)

# Reuses `test_application_audit.py`'s own `_ms_from_pg_timeout_text` --
# PostgreSQL's `SHOW` renders the GUC in whichever unit divides it evenly
# ("5000ms" as "5s"), so a bare string-equality assertion would be
# unit-dependent; re-implementing the same parsing here would duplicate,
# and risk drifting from, that file's own established, more complete
# parser (min/s/ms/bare-"0" cases).
from .test_application_audit import _ms_from_pg_timeout_text  # noqa: E402,F401

ADMIN_DSN_ENV = "MITATEDB_TEST_ADMIN_DSN"
ADMIN_DSN_DEFAULT = "host=/tmp port=5432 dbname=postgres"


def _admin_dsn() -> str:
    return os.environ.get(ADMIN_DSN_ENV, ADMIN_DSN_DEFAULT)


def _show_ms(conn: "psycopg.Connection", setting: str) -> int:
    with conn.cursor() as cur:
        cur.execute(f"SHOW {setting}")
        return _ms_from_pg_timeout_text(cur.fetchone()[0])


def test_http_conformance_adapter_audit_writer_connection_has_statement_and_idle_timeouts_set() -> None:
    admin_conn = psycopg.connect(_admin_dsn())
    try:
        cluster_default_statement_timeout_ms = _show_ms(admin_conn, "statement_timeout")
        cluster_default_idle_timeout_ms = _show_ms(admin_conn, "idle_in_transaction_session_timeout")
    finally:
        admin_conn.close()

    adapter = _http_module.build_adapter()
    try:
        conn = adapter._application_durable_audit._connect()  # noqa: SLF001 -- adapter-internal reach-in, test-only (mirrors test_application_audit.py's own established convention)
        try:
            statement_timeout_ms = _show_ms(conn, "statement_timeout")
            idle_timeout_ms = _show_ms(conn, "idle_in_transaction_session_timeout")
        finally:
            conn.close()
    finally:
        adapter.close()

    assert statement_timeout_ms == DEFAULT_AUDIT_STATEMENT_TIMEOUT_MS
    assert idle_timeout_ms == DEFAULT_AUDIT_IDLE_TIMEOUT_MS
    # Distinguishable from the untouched server default -- otherwise a
    # mutation dropping the adapter's own kwargs would coincidentally still
    # read as "configured" (P4-D17 review point 2). Review fix (M1): the
    # admin-side default is now parsed through the SAME `_ms_from_pg_
    # timeout_text` and compared as milliseconds-to-milliseconds -- the
    # prior `f"{ms}ms" != cluster_default_text` string form was
    # unit-dependent (PostgreSQL renders "5000ms" as "5s"), so it would
    # have PASSED even when the two values were numerically equal,
    # silently failing to guard what it claims to (mirrors r2db-api's own
    # `test_conformance_adapter_r2db_http_audit_writer_timeouts.py`).
    assert statement_timeout_ms != cluster_default_statement_timeout_ms
    assert idle_timeout_ms != cluster_default_idle_timeout_ms
