"""Phase 4 ledger closure WP-B3 (L4-6, design P4-D17 -- 作業指示書
WORK_ORDER_PHASE4_LEDGER_CLOSURE_V1.md §1 L4-6 が正本): the HTTP
conformance adapter (`conformance_adapter_mitatedb_http.py`) constructs its
own `PostgresApplicationAuditSink` writer connection ad hoc, inside its own
`__init__`, never through `mitatedb_api.main.build_app` -- the existing
composition-root timeout tests (`test_application_audit.py`) never
exercise THIS object at all.

Q4 phase (design docs/design/Q4_DB_SIDE_SINGLE_TRUTH_V1.md D-1(b), work
order §4 WP-2 変更対象 D): SUPERSEDES the original P4-D17 form of this
test. `PostgresApplicationAuditSink` no longer accepts ANY timeout
constructor argument at all (the `SET SESSION` mechanism P4-D17 guarded is
REMOVED product code) -- so there is no longer a `statement_timeout_ms=`/
`idle_in_transaction_session_timeout_ms=` keyword pair a mutation could
drop from the adapter's own construction call site. What COULD still
regress: the adapter's own `_bootstrap_platform` forgetting to apply
migration `0007_platform_declarations.sql` (or a caller reintroducing an
explicit override) -- either would leave the writer connection's real
GUCs at the bare PostgreSQL cluster default (typically unlimited/`0`)
rather than the role-level declaration this adapter's own bootstrap
applies (R-105, design docs/design/SLOW_CALL_PHASE_TESTS_V0_1.md D-1:
`CONFORMANCE_AUDIT_STATEMENT_TIMEOUT_MS`/`_IDLE_TIMEOUT_MS`, 1000ms/2000ms
-- overwritten after migration `0007`'s own shipped 5000ms/5000ms seed,
not that seed itself). The mechanism below
(build the real adapter, read its own sink's real connection via `SHOW`,
compare against a fresh admin connection's own bare default) still proves
exactly that -- it is now a proof that the DECLARATIONS-based mechanism
reached this object, not that an explicit kwarg did.

Same method the original test used: build the REAL adapter, ask ITS OWN
sink for a fresh connection (`PostgresApplicationAuditSink._connect()` --
this peer's sink opens a new connection per call rather than pooling), and
`SHOW statement_timeout` / `SHOW idle_in_transaction_session_timeout` --
not a hand-constructed stand-in `PostgresApplicationAuditSink` (which
would only prove the sink class itself works, never that the adapter's
own `_bootstrap_platform` actually applied `0007`).

Distinguishable from the untouched server default (P4-D17 review point 2):
this test reads the real cluster's own compiled-in default via a bare
admin connection FIRST, then asserts the adapter's own value differs from
it -- the adapter's own conformance-deployment role-level value
(`conformance_adapter_mitatedb_http.CONFORMANCE_AUDIT_STATEMENT_TIMEOUT_MS`/
`_IDLE_TIMEOUT_MS`, R-105) is asserted for its literal value too, so a
mutation that drops `_bootstrap_platform`'s own `ALTER ROLE` step (leaving
migration `0007`'s own shipped 5000ms/5000ms seed in place) OR that drops
migration `0007` itself from `_bootstrap_platform`'s own list (falling
back to the server's own default, typically "0" = disabled) goes red on
both assertions.

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
from mitatedb_api import platform_declarations  # noqa: E402

# Q4 phase WP-0 (design D-1 (b)(ii), work order §4 WP-0 完了条件 2): was
# `from .test_application_audit import _ms_from_pg_timeout_text` -- now
# imports the same normalization directly from `src` (promoted there so
# Q4 WP-2's own startup double-check can share it), rather than through
# a test-file-to-test-file import. PostgreSQL's `SHOW` renders the GUC in
# whichever unit divides it evenly ("5000ms" as "5s"), so a bare
# string-equality assertion would be unit-dependent.
from mitatedb_api.pg_timeouts import ms_from_pg_timeout_text  # noqa: E402

ADMIN_DSN_ENV = "MITATEDB_TEST_ADMIN_DSN"


def _admin_dsn() -> str:
    dsn = os.environ.get(ADMIN_DSN_ENV)
    if not dsn:
        raise RuntimeError(
            f"{ADMIN_DSN_ENV} is not set (or is empty). "
            "tools/testpg/dsa_testpg.py sets it for each test run; "
            "there is no shared-cluster default."
        )
    return dsn


def _show_ms(conn: "psycopg.Connection", setting: str) -> int:
    with conn.cursor() as cur:
        cur.execute(f"SHOW {setting}")
        return ms_from_pg_timeout_text(cur.fetchone()[0])


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

    assert statement_timeout_ms == _http_module.CONFORMANCE_AUDIT_STATEMENT_TIMEOUT_MS
    assert idle_timeout_ms == _http_module.CONFORMANCE_AUDIT_IDLE_TIMEOUT_MS
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


def test_http_conformance_adapter_declares_the_conformance_deployment_visibility_lag() -> None:
    """R-105 (design docs/design/SLOW_CALL_PHASE_TESTS_V0_1.md D-1): this
    adapter's peer declares `audit_visibility_lag_ms` as the sum of the
    adapter's OWN conformance-deployment module constants
    (`CONFORMANCE_AUDIT_STATEMENT_TIMEOUT_MS` + `_IDLE_TIMEOUT_MS` +
    `VISIBILITY_LAG_CLOCK_SKEW_MARGIN_MS`) -- checked (1) against that
    same-source sum, (2) against the literal `4000` (design D-1: "両辺同
    源の穴を塞ぐ" -- guards the two module constants drifting away from
    the value both this plug and r2db-api's own HTTP plug must agree on),
    and (3) against `platform_declarations.derive_visibility_lag_ms` fed
    the SAME catalog rows `mitatedb_api.control_composition` itself reads
    at startup (`read_platform_declarations`/`read_declared_role_
    timeouts` over `audit_writer_roles`) -- proving the declared value is
    genuinely the catalog-derived one, not a coincidentally-equal literal
    somewhere else in the adapter."""
    adapter = _http_module.build_adapter()
    try:
        lag_ms = adapter.audit_visibility_lag_ms()

        conn = psycopg.connect(adapter._platform.controlplane_dsn)  # noqa: SLF001 -- adapter-internal reach-in, test-only (mirrors this file's own established convention)
        try:
            declarations = platform_declarations.read_platform_declarations(
                conn, schema=adapter._platform.schema,  # noqa: SLF001
                ops_module=platform_declarations.PEER_MODULE, migration=platform_declarations.MIGRATION_NUMBER,
            )
            catalogs = [
                platform_declarations.read_declared_role_timeouts(
                    conn, role, ops_module=platform_declarations.PEER_MODULE, migration=platform_declarations.MIGRATION_NUMBER,
                )
                for role in declarations.audit_writer_roles
            ]
        finally:
            conn.close()
    finally:
        adapter.close()

    assert lag_ms == (
        _http_module.CONFORMANCE_AUDIT_STATEMENT_TIMEOUT_MS
        + _http_module.CONFORMANCE_AUDIT_IDLE_TIMEOUT_MS
        + platform_declarations.VISIBILITY_LAG_CLOCK_SKEW_MARGIN_MS
    )
    assert lag_ms == 4000
    assert platform_declarations.derive_visibility_lag_ms(catalogs) == lag_ms
