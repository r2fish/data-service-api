"""2-store reconciliation (WP-5 flip, design v1.2 R-8 / WP-4 handoff item
i): a credential issued IN-BAND, through `/control/v1`-equivalent
operations (`issue_credential_inband`), must be readable by the SAME
application-plane `authenticate()` path a real client uses -- not a
second, adapter-only shadow representation of "this credential exists".

This property is NOT exercised by any existing common conformance test:
`test_c14_authority_boundary.py`'s own "declared status agrees with real
behavior" vector checks only that `issue_credential_inband(...).secret` is
a non-empty string, never that the resulting credential actually
authenticates -- a control-plane backend that silently mints a DIFFERENT
row than the one it reports back to the caller would pass that check
while being genuinely broken. This file closes that gap directly, for
both registered MitateDB-api adapters, following the same `sys.path`
convention `test_conformance_public_surface_coverage.py`/`test_
conformance_adapter_mitatedb_http_sweep_scope.py` already establish for
importing a conformance-adapter module from this test directory.

In-process: `conformance_adapter_mitatedb.py`'s own `_ReconciledControl
Backend` writes application-plane credential rows directly into `auth.
CredentialStore` (the SAME store `MitateDataService.open_session`/
`authenticate()` reads) -- this is real, adapter-internal wiring, not
product code, so this is the ONLY place it can be tested.

HTTP: reconciliation is structural (`control_plane.PostgresCredential
Registry` and `credential_store_postgres.PostgresCredentialStore` are two
Python representations of the SAME `<schema>.credentials` PostgreSQL
table) -- this test is nonetheless real, end-to-end evidence of that
structural claim, not an assumption.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "conformance"))

import conformance_adapter_mitatedb as _inprocess_module  # noqa: E402
import conformance_adapter_mitatedb_http as _http_module  # noqa: E402


def test_inprocess_inband_issued_credential_authenticates_for_real() -> None:
    adapter = _inprocess_module.build_adapter()
    try:
        control_actor = adapter.control_credential()
        app_id = "recon_probe_inprocess_1"
        adapter.register_application_inband(control_actor, app_id)

        handle = adapter.issue_credential_inband(control_actor, app_id, "runtime")

        # The real proof: authenticate() must succeed using EXACTLY the
        # id/secret ControlPlaneService reported back -- not a value this
        # test fabricates, and not a value read back out of internal
        # state. A backend that stores a DIFFERENT credential_id/secret
        # than the one it returns (this file's own mutation-injection
        # target) makes this raise `ConformanceDenial`.
        session = adapter.authenticate(handle)
        scope = adapter.scope_of(session)
        assert scope.application_id == app_id
        assert scope.role == "runtime"

        # And the reverse direction: an out-of-band control-plane LIST
        # (also in-band here) must show the SAME row.
        listed = adapter.list_credentials(control_actor)
        assert any(row["credential_id"] == handle.credential_ref for row in listed)
    finally:
        adapter.close()


def test_http_inband_issued_credential_authenticates_for_real() -> None:
    if not _http_reachable():
        raise AssertionError(
            "MitateDB-api (http+postgres) requires a reachable local PostgreSQL server "
            f"({_http_module.ADMIN_DSN_ENV}={_http_module._admin_dsn()!r}) -- this test must not skip "
            "(design R-8's own 'skip 禁止' condition)."
        )
    adapter = _http_module.build_adapter()
    try:
        control_actor = adapter.control_credential()
        app_id = "recon_probe_http_1"
        # Unlike the in-process adapter, an in-band `register_application_
        # inband` alone leaves the application UNPROVISIONED (no real
        # database/cell exists yet, R-4's own two-state registry) --
        # `provision_application` (out-of-band) is what gives this
        # composition a real `ApplicationCell` to authenticate against at
        # all. Reconciliation itself is about the CREDENTIAL row, not the
        # provisioning state, so this test provisions for real and issues
        # the credential in-band against the already-provisioned app.
        adapter.provision_application(app_id)

        handle = adapter.issue_credential_inband(control_actor, app_id, "runtime")
        session = adapter.authenticate(handle)
        scope = adapter.scope_of(session)
        assert scope.application_id == app_id
        assert scope.role == "runtime"

        listed = adapter.list_credentials(control_actor)
        assert any(row["credential_id"] == handle.credential_ref for row in listed)

        adapter.deprovision_application(app_id)
    finally:
        adapter.close()


def _http_reachable() -> bool:
    import psycopg
    try:
        conn = psycopg.connect(_http_module._admin_dsn(), connect_timeout=5)
        conn.close()
        return True
    except Exception:
        return False
