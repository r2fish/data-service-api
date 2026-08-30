"""`ControlPlaneService` against the real-PostgreSQL backend, plus topology
executable evidence (WP-4, design v1.2 R-4/R-8, §3 WP-4 row: "topology 実行
可能証拠 -- r2db の AuthorityTopology/test_topology.py 相当"). Mirrors the
behavioural coverage `test_control_plane_service.py` already gives the
in-memory backend, at a smaller scale (a handful of representative cases,
not full duplication), plus grant-boundary tests only PostgreSQL can prove:
control_audit is append-only by GRANT (not merely by convention), and the
application-plane process role cannot reach the control tables at all.
"""
from __future__ import annotations

from typing import Iterator

import psycopg
import pytest

from .control_plane_harness import control_platform  # noqa: F401 (fixture)
from mitatedb_api.control_credential_store_postgres import PostgresControlCredentialStore
from mitatedb_api.control_plane import (ControlPlaneLimits, ControlPlaneService,
                                        PostgresApplicationRegistry, PostgresControlBackend,
                                        PostgresCredentialRegistry, bootstrap_control_credential)
from mitatedb_api.errors import (AuthenticationError, AuthorizationError, CapabilityError,
                                 ConflictError, DestructiveConfirmationRequired, NotFoundError,
                                 ResourceLimitError)

_APP_PEPPER = "control-plane-postgres-app-pepper-x"
_CONTROL_PEPPER = "control-plane-postgres-ctl-pepper-x"


@pytest.fixture
def backend(control_platform) -> Iterator[PostgresControlBackend]:
    applications = PostgresApplicationRegistry(control_platform.controlplane_dsn, schema=control_platform.registry_schema)
    credentials = PostgresCredentialRegistry(control_platform.controlplane_dsn, pepper=_APP_PEPPER,
                                             schema=control_platform.registry_schema)
    control_credentials = PostgresControlCredentialStore(control_platform.controlplane_dsn, pepper=_CONTROL_PEPPER,
                                                         schema=control_platform.registry_schema)
    yield PostgresControlBackend(applications=applications, credentials=credentials,
                                 control_credentials=control_credentials,
                                 audit_schema=control_platform.registry_schema, dsn=control_platform.controlplane_dsn)
    conn = psycopg.connect(control_platform.provision_dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            schema = control_platform.registry_schema
            cur.execute(f"DELETE FROM {schema}.credentials")
            cur.execute(f"DELETE FROM {schema}.control_credentials")
            cur.execute(f"DELETE FROM {schema}.applications")
            cur.execute(f"DELETE FROM {schema}.control_audit")
    finally:
        conn.close()


def _bootstrapped(backend, limits=None):
    with backend.unit_of_work() as work:
        credential_id, secret = bootstrap_control_credential(backend.control_credential_store, backend.append_audit, work=work)
    service = ControlPlaneService(backend, limits=limits or ControlPlaneLimits(
        applications=5, credentials_per_application=2, control_requests_per_minute=90))
    rotated = service.rotate_credential(credential_id, secret, credential_id)
    return service, credential_id, rotated["secret"]


def test_register_issue_list_revoke_round_trip_against_real_postgres(backend) -> None:
    service, cid, secret = _bootstrapped(backend)
    service.register_application(cid, secret, "pgapp")
    issued = service.issue_credential(cid, secret, "pgapp", "runtime")
    listing = service.list_credentials(cid, secret)
    ids = {row["credential_id"] for row in listing["credentials"]}
    assert issued["credential_id"] in ids
    assert cid in ids

    revoked = service.revoke_credential(cid, secret, issued["credential_id"])
    assert revoked["revoked"] is True


def test_credentials_per_application_bound_excludes_revoked_against_real_postgres(backend) -> None:
    service, cid, secret = _bootstrapped(backend, limits=ControlPlaneLimits(
        applications=5, credentials_per_application=1, control_requests_per_minute=90))
    service.register_application(cid, secret, "boundedpg")
    first = service.issue_credential(cid, secret, "boundedpg", "runtime")
    with pytest.raises(ResourceLimitError):
        service.issue_credential(cid, secret, "boundedpg", "runtime")
    service.revoke_credential(cid, secret, first["credential_id"])
    second = service.issue_credential(cid, secret, "boundedpg", "runtime")
    assert second["credential_id"] != first["credential_id"]


def test_role_control_refused_before_target_resolution_against_real_postgres(backend) -> None:
    service, cid, secret = _bootstrapped(backend)
    with pytest.raises(CapabilityError):
        service.issue_credential(cid, secret, "no_such_app_at_all", "control")


def test_revoke_last_active_control_credential_gate_against_real_postgres(backend) -> None:
    service, cid, secret = _bootstrapped(backend)
    with pytest.raises(DestructiveConfirmationRequired) as excinfo:
        service.revoke_credential(cid, secret, cid)
    phrase = excinfo.value.details["required_confirmation"]
    result = service.revoke_credential(cid, secret, cid, destructive=True, confirmation=phrase)
    assert result["revoked"] is True
    with pytest.raises(AuthenticationError):
        service.control_capabilities(cid, secret)


def test_must_rotate_forbids_ordinary_operations_against_real_postgres(backend) -> None:
    with backend.unit_of_work() as work:
        cid, secret = bootstrap_control_credential(backend.control_credential_store, backend.append_audit, work=work)
    service = ControlPlaneService(backend)
    with pytest.raises(AuthorizationError):
        service.register_application(cid, secret, "shouldnotregister")


def test_application_not_found_against_real_postgres(backend) -> None:
    service, cid, secret = _bootstrapped(backend)
    with pytest.raises(NotFoundError):
        service.set_application_enabled(cid, secret, "ghost", False)


def test_duplicate_registration_is_conflict_against_real_postgres(backend) -> None:
    service, cid, secret = _bootstrapped(backend)
    service.register_application(cid, secret, "dup")
    with pytest.raises(ConflictError):
        service.register_application(cid, secret, "dup")


# ==========================================================================
# Topology executable evidence (design §3 WP-4 row / R-4 / SI-00/SI-01):
# real, bare psycopg connections -- never through a facade -- proving the
# actual grant boundary a would-be attacker or a defective future call site
# would run into.
# ==========================================================================


def test_control_plane_role_cannot_select_its_own_audit_table(control_platform) -> None:
    """control_audit is append-only by GRANT, not merely by application-code
    convention (migration 0002: `GRANT INSERT ON ... control_audit` and
    NOTHING else to `mitatedbsvc_controlplane`) -- a bare `SELECT` from the
    control-plane role's own connection must be refused by PostgreSQL
    itself, before any Python code runs at all."""
    conn = psycopg.connect(control_platform.controlplane_dsn)
    try:
        with conn.cursor() as cur:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                cur.execute(f"SELECT * FROM {control_platform.registry_schema}.control_audit LIMIT 1")
    finally:
        conn.rollback()
        conn.close()


def test_control_plane_role_can_insert_into_its_own_audit_table(control_platform) -> None:
    """The positive half of the same boundary: INSERT (this role's one
    granted verb on this table) succeeds."""
    conn = psycopg.connect(control_platform.controlplane_dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"INSERT INTO {control_platform.registry_schema}.control_audit "
                "(event_id, event_class, occurred_at, operation, outcome) "
                "VALUES (%s, %s, now(), %s, %s)",
                ["topology-test-event", "topology_probe", "topology_probe", "allow"],
            )
        conn.commit()
    finally:
        conn.close()
    # Read back via the OWNER role (R-8's own separate-reader convention --
    # the control-plane role itself structurally cannot do this read, as
    # the test immediately above proves).
    reader = psycopg.connect(control_platform.provision_dsn)
    try:
        with reader.cursor() as cur:
            cur.execute(
                f"SELECT event_id FROM {control_platform.registry_schema}.control_audit "
                "WHERE event_id = %s", ["topology-test-event"])
            row = cur.fetchone()
        assert row is not None
    finally:
        reader.rollback()
        reader.close()


def test_application_plane_role_has_no_privilege_on_control_credentials(control_platform) -> None:
    """R-4 process-role separation: `mitatedbsvc_api` (the application-plane
    read-only role, migration 0002) has NO grant of any kind on
    `control_credentials` -- it cannot even SELECT it, let alone write."""
    conn = psycopg.connect(control_platform.api_dsn)
    try:
        with conn.cursor() as cur:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                cur.execute(f"SELECT * FROM {control_platform.registry_schema}.control_credentials LIMIT 1")
    finally:
        conn.rollback()
        conn.close()


def test_application_plane_role_has_no_privilege_on_control_audit(control_platform) -> None:
    conn = psycopg.connect(control_platform.api_dsn)
    try:
        with conn.cursor() as cur:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                cur.execute(f"SELECT * FROM {control_platform.registry_schema}.control_audit LIMIT 1")
    finally:
        conn.rollback()
        conn.close()


def test_application_plane_role_can_still_read_applications_and_credentials(control_platform) -> None:
    """Negative-boundary tests alone would not distinguish "correctly
    scoped" from "broken entirely" -- this positive control proves
    `mitatedbsvc_api` retains exactly the read access R-4 intends
    (`applications`/`credentials`, its own `authenticate()` path)."""
    conn = psycopg.connect(control_platform.api_dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT count(*) FROM {control_platform.registry_schema}.applications")
            cur.execute(f"SELECT count(*) FROM {control_platform.registry_schema}.credentials")
    finally:
        conn.rollback()
        conn.close()
