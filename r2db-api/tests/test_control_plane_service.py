"""CCR-14 WP-3: `ControlPlaneService` -- processing order, must_rotate gate,
R-6 same-transaction/denial audit (+ sink fault injection, fail-closed),
R-7 limits, credential/application lifecycle semantics, and R-11 deterrence
declarations. Tested against a real PostgreSQL server as well as the
in-memory backend, mirroring `test_control_plane_store.py`'s own platform-
fixture conventions (§5.3 C-5: must not be skipped).

Design this file is written against: docs/design/
R2DB_CCR14_CONTROL_PLANE_V1.md v1.5, §1 (operation catalog), §2
(must_rotate/R-8), §3 (R-7 limits), §4 (R-6 audit), §5 (R-11 declarations),
§6 (test list this file implements item-for-item), §10/§11 (WP-1/WP-2
supervisor decisions).
"""
from __future__ import annotations

from contextlib import contextmanager
import os
import secrets
import subprocess
import sys
import types
from pathlib import Path
from typing import Iterator

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from r2db_api.audit import ControlAuditSink
from r2db_api.auth import ControlAuthContext, ControlCredentialStore, CredentialStore
from r2db_api.control_plane import ControlPlaneService, InMemoryControlBackend, PostgresControlBackend
from r2db_api.credential_store import (
    PostgresApplicationRegistry,
    PostgresControlAuditSink,
    PostgresControlCredentialStore,
    PostgresCredentialStore,
)
from r2db_api.errors import FoundationError
from r2db_api.limits import ControlPlaneLimits
from r2db_api.service import ControlAuthority, DataService
from r2db_api.structured import revoke_last_control_credential_confirmation_phrase

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"
ADMIN_DSN_ENV = "R2DB_TEST_ADMIN_DSN"
ADMIN_DSN_DEFAULT = "host=/tmp port=5432 dbname=postgres"
PEPPER = "synthetic-test-pepper-control-plane-service-app-0000"
CONTROL_PEPPER = "synthetic-test-pepper-control-plane-service-ctl-0000"

MIGRATION_NAMES = (
    "0001_bootstrap_control_plane.sql",
    "0002_provisioning_functions.sql",
    "0003_provision_application.sql",
    "0004_deprovision_application.sql",
    "0005_credential_store.sql",
    "0006_control_plane_http.sql",
)

# Generous defaults so ordinary tests never accidentally collide with a
# limit under test -- tests exercising R-7 pass their own tight
# `ControlPlaneLimits` explicitly instead of relying on these.
_GENEROUS_LIMITS = ControlPlaneLimits(applications=100_000, credentials_per_application=100_000, control_requests_per_minute=100_000)


# ===========================================================================
# PostgreSQL platform fixture (duplicated from `test_control_plane_store.py`
# per this repository's own established precedent of not taking cross-test-
# module import dependencies).
# ===========================================================================


def _admin_dsn() -> str:
    return os.environ.get(ADMIN_DSN_ENV, ADMIN_DSN_DEFAULT)


def _dsn_with(base_dsn: str, **overrides: str) -> str:
    params = conninfo_to_dict(base_dsn)
    params.update(overrides)
    return make_conninfo(**params)


def _run_psql(dsn: str, path: Path, variables: dict[str, str] | None = None) -> None:
    command = ["psql", dsn, "-v", "ON_ERROR_STOP=1"]
    for key, value in (variables or {}).items():
        command += ["-v", f"{key}={value}"]
    command += ["-f", str(path)]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"psql failed running {path.name}:\n{result.stdout}\n{result.stderr}")


def _require_admin_connection() -> None:
    dsn = _admin_dsn()
    try:
        conn = psycopg.connect(dsn, connect_timeout=5)
        conn.close()
    except Exception as exc:  # pragma: no cover - environment-dependent
        pytest.fail(
            "test_control_plane_service.py requires a reachable local PostgreSQL "
            f"server. Connecting with {ADMIN_DSN_ENV}={dsn!r} failed: {exc}. These "
            "tests must not be skipped (§5.3 C-5).",
            pytrace=False,
        )


def _sweep_prefix(admin_dsn: str, prefix: str) -> None:
    import time

    admin = psycopg.connect(admin_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute("SELECT datname FROM pg_database WHERE datname LIKE %s", [f"{prefix}%"])
            leftover_databases = [row[0] for row in cur.fetchall()]
            for database in leftover_databases:
                for attempt in range(8):
                    cur.execute(
                        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                        "WHERE datname = %s AND pid <> pg_backend_pid() AND backend_type = 'client backend'",
                        [database],
                    )
                    try:
                        cur.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(database)))
                        break
                    except psycopg.errors.ObjectInUse:
                        admin.rollback()
                        time.sleep(0.2 * (attempt + 1))
            cur.execute("SELECT rolname FROM pg_roles WHERE rolname LIKE %s", [f"{prefix}%"])
            leftover_roles = [row[0] for row in cur.fetchall()]
            for role in leftover_roles:
                cur.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(role)))
    finally:
        admin.close()


def _provision_platform(tmp_path_factory: pytest.TempPathFactory) -> types.SimpleNamespace:
    _require_admin_connection()
    admin_dsn = _admin_dsn()
    prefix = f"r2dbcps{secrets.token_hex(4)}"
    control_role = f"{prefix}_control"
    api_role = f"{prefix}_api"
    controlplane_role = f"{prefix}_controlplane"
    platform_db = f"{prefix}_platform"
    schema = f"{prefix}_registry"
    control_password = secrets.token_urlsafe(24)
    api_password = secrets.token_urlsafe(24)
    controlplane_password = secrets.token_urlsafe(24)

    rewritten_dir = tmp_path_factory.mktemp("r2db_cps_migrations")
    rewritten: dict[str, Path] = {}
    for name in MIGRATION_NAMES:
        text = (MIGRATIONS_DIR / name).read_text().replace("r2dbsvc", prefix)
        out = rewritten_dir / name
        out.write_text(text)
        rewritten[name] = out

    try:
        _run_psql(admin_dsn, rewritten["0001_bootstrap_control_plane.sql"], {"control_password": control_password})
        control_dsn = _dsn_with(admin_dsn, user=control_role, password=control_password, dbname=platform_db)
        _run_psql(control_dsn, rewritten["0002_provisioning_functions.sql"])
        _run_psql(control_dsn, rewritten["0005_credential_store.sql"], {"api_password": api_password})
        _run_psql(control_dsn, rewritten["0006_control_plane_http.sql"], {"controlplane_password": controlplane_password})
    except Exception:
        _sweep_prefix(admin_dsn, prefix)
        raise

    controlplane_dsn = _dsn_with(admin_dsn, user=controlplane_role, password=controlplane_password, dbname=platform_db)

    return types.SimpleNamespace(
        prefix=prefix,
        admin_dsn=admin_dsn,
        control_dsn=control_dsn,
        controlplane_dsn=controlplane_dsn,
        schema=schema,
    )


@pytest.fixture(scope="module")
def platform(tmp_path_factory: pytest.TempPathFactory) -> Iterator[types.SimpleNamespace]:
    info = _provision_platform(tmp_path_factory)
    try:
        yield info
    finally:
        _sweep_prefix(info.admin_dsn, info.prefix)


@contextmanager
def _control_audit_renamed_away(platform: types.SimpleNamespace) -> Iterator[None]:
    """Postgres fault injection (mirrors `test_control_plane_store.py`'s
    identical technique): renames `control_audit` out from under a running
    process so any INSERT against it fails, then renames it back on exit --
    used to exercise R-6's fail-closed guarantee (state-change abort, denial
    -> 503) against a *real* PostgreSQL error, not a simulated one."""
    rename_away = sql.SQL("ALTER TABLE {table} RENAME TO control_audit_fault_injected").format(table=sql.Identifier(platform.schema, "control_audit"))
    rename_back = sql.SQL("ALTER TABLE {schema}.control_audit_fault_injected RENAME TO control_audit").format(schema=sql.Identifier(platform.schema))
    with psycopg.connect(platform.control_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(rename_away)
        conn.commit()
    try:
        yield
    finally:
        with psycopg.connect(platform.control_dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(rename_back)
            conn.commit()


# ===========================================================================
# Harness: builds a `ControlPlaneService` against either backend behind one
# shared test-facing surface, so every test below runs unchanged against
# both (work order §6: "全テストをin-memory/Postgres両backendで回す").
# ===========================================================================


def _memory_harness(limits: ControlPlaneLimits) -> types.SimpleNamespace:
    credentials = CredentialStore(pepper=PEPPER)
    data_service = DataService(credentials)
    authority = ControlAuthority(data_service)
    control_credentials = ControlCredentialStore(pepper=CONTROL_PEPPER)
    backend = InMemoryControlBackend(authority, control_credentials)
    audit = ControlAuditSink()
    service = ControlPlaneService(backend, audit=audit, limits=limits, clock=lambda: _clock_state["now"])

    def seed_control_credential(credential_id: str, secret: str, *, must_rotate: bool = True) -> None:
        with control_credentials.unit_of_work() as work:
            control_credentials.add(credential_id, secret, work=work)
        if not must_rotate:
            with control_credentials.unit_of_work() as work:
                control_credentials.rotate(credential_id, secret, work=work)

    def revoke_control_credential_directly(credential_id: str) -> None:
        with control_credentials.unit_of_work() as work:
            control_credentials.set_state(credential_id, revoked=True, work=work)

    def disable_control_credential_directly(credential_id: str) -> None:
        with control_credentials.unit_of_work() as work:
            control_credentials.set_state(credential_id, enabled=False, work=work)

    def audit_events() -> list[dict]:
        return [dict(event) for event in audit.events()]

    def inject_audit_fault(exc: Exception | None) -> None:
        audit.inject_fault(exc)

    def cleanup() -> None:
        pass

    return types.SimpleNamespace(
        kind="memory",
        service=service,
        seed_control_credential=seed_control_credential,
        revoke_control_credential_directly=revoke_control_credential_directly,
        disable_control_credential_directly=disable_control_credential_directly,
        audit_events=audit_events,
        inject_audit_fault=inject_audit_fault,
        cleanup=cleanup,
        authority=authority,
        credentials_store=credentials,
        control_credentials_store=control_credentials,
        audit_sink=audit,
    )


def _postgres_harness(platform: types.SimpleNamespace, limits: ControlPlaneLimits) -> types.SimpleNamespace:
    # The service itself connects with the least-privilege `r2dbsvc_
    # controlplane` role (`controlplane_dsn`) -- exactly the role/DSN a real
    # deployment's control-plane HTTP process would use (design R-3). Every
    # operation below therefore runs inside the real 0006 GRANT boundary,
    # not merely against a fully-privileged connection that happens to work.
    applications = PostgresApplicationRegistry(platform.controlplane_dsn, schema=platform.schema)
    credentials = PostgresCredentialStore(platform.controlplane_dsn, pepper=PEPPER, schema=platform.schema)
    control_credentials = PostgresControlCredentialStore(platform.controlplane_dsn, pepper=CONTROL_PEPPER, schema=platform.schema)
    backend = PostgresControlBackend(applications=applications, credentials=credentials, control_credentials=control_credentials)
    audit = PostgresControlAuditSink(platform.controlplane_dsn, schema=platform.schema)
    service = ControlPlaneService(backend, audit=audit, limits=limits, clock=lambda: _clock_state["now"])

    # Seeding a control credential (bootstrap-equivalent) needs INSERT on
    # `control_credentials`, which `r2dbsvc_controlplane` deliberately does
    # NOT have (R-3 -- issuance is out-of-band only) -- exactly like the real
    # `python -m r2db_api.ops bootstrap` ritual, seeding here connects as
    # `r2dbsvc_control` instead. Reading audit rows back for verification
    # needs SELECT on `control_audit`, which `r2dbsvc_controlplane` also does
    # not have (R-3/MA-2: append-only from that role, not even readable back
    # by the writer) -- so verification reads go through this same `r2dbsvc_
    # control`-connected sink too.
    seed_store = PostgresControlCredentialStore(platform.control_dsn, pepper=CONTROL_PEPPER, schema=platform.schema)
    read_sink = PostgresControlAuditSink(platform.control_dsn, schema=platform.schema)

    def seed_control_credential(credential_id: str, secret: str, *, must_rotate: bool = True) -> None:
        with seed_store.unit_of_work() as work:
            seed_store.add(credential_id, secret, work=work)
        if not must_rotate:
            with seed_store.unit_of_work() as work:
                seed_store.rotate(credential_id, secret, work=work)

    def revoke_control_credential_directly(credential_id: str) -> None:
        with seed_store.unit_of_work() as work:
            seed_store.set_state(credential_id, revoked=True, work=work)

    def disable_control_credential_directly(credential_id: str) -> None:
        with seed_store.unit_of_work() as work:
            seed_store.set_state(credential_id, enabled=False, work=work)

    _columns = ("event_id", "event_class", "occurred_at", "request_id", "application_id", "actor_type", "actor_id", "role", "operation", "target_kind", "outcome", "reason_code")

    def audit_events() -> list[dict]:
        return [dict(zip(_columns, row)) for row in read_sink.events()]

    def inject_audit_fault(exc: Exception | None) -> None:
        raise NotImplementedError("Postgres fault injection uses `_control_audit_renamed_away(platform)` around the call under test, not this hook")

    def cleanup() -> None:
        applications.close()
        credentials.close()
        control_credentials.close()
        audit.close()
        seed_store.close()
        read_sink.close()

    return types.SimpleNamespace(
        kind="postgres",
        service=service,
        seed_control_credential=seed_control_credential,
        revoke_control_credential_directly=revoke_control_credential_directly,
        disable_control_credential_directly=disable_control_credential_directly,
        audit_events=audit_events,
        inject_audit_fault=inject_audit_fault,
        cleanup=cleanup,
        platform=platform,
        credentials_store=credentials,
        control_credentials_store=control_credentials,
    )


# A mutable "now" shared with each harness's injected `clock` callable
# (work order §3: "窓の時刻源は注入可能に") -- module-level so both harness
# builders' lambdas close over the same cell; each rate-limit test resets it
# to `0.0` at the start (`_clock_state["now"] = 0.0`) and advances it
# explicitly, rather than depending on real wall-clock time (deterministic,
# and avoids a ~60s real sleep to test window rollover).
_clock_state = {"now": 0.0}


def _build_harness(kind: str, platform: types.SimpleNamespace | None, limits: ControlPlaneLimits | None = None) -> types.SimpleNamespace:
    _clock_state["now"] = 0.0
    limits = limits or _GENEROUS_LIMITS
    if kind == "memory":
        return _memory_harness(limits)
    assert platform is not None, "postgres harness requires the `platform` fixture"
    return _postgres_harness(platform, limits)


def _fresh_id(prefix: str) -> str:
    return f"{prefix}{secrets.token_hex(6)}"


def _find_audit_row_by_request_id(h: types.SimpleNamespace, request_id: str) -> dict | None:
    """MI-4 (round-2 review): match audit rows by the exact `request_id` a
    test itself supplied, rather than an `actor_id`-in-a-set heuristic --
    the Postgres harness shares one module-scoped `control_audit` table
    across every "postgres"-kind test in this file, so any heuristic weaker
    than an exact, test-chosen `request_id` risks matching another test's
    residue instead of (or as well as) this test's own row."""
    matches = [event for event in h.audit_events() if event.get("request_id") == request_id]
    assert len(matches) <= 1, f"request_id {request_id!r} is expected to be unique per probe, found {len(matches)} rows"
    return matches[0] if matches else None


@contextmanager
def _faulted_audit_sink(h: types.SimpleNamespace, kind: str, platform: types.SimpleNamespace) -> Iterator[None]:
    """MA-3: the shared fault-injection mechanics `test_state_change_sink_
    fault_injection_aborts_the_state_change` uses across all three unit-of-
    work families, factored out so each scenario branch only states what it
    does, not how the fault is injected."""
    if kind == "memory":
        h.inject_audit_fault(RuntimeError("simulated sink failure"))
        try:
            yield
        finally:
            h.inject_audit_fault(None)
    else:
        with _control_audit_renamed_away(platform):
            yield


BACKENDS = ("memory", "postgres")


# ===========================================================================
# Section 1: processing order (work order §6 item 1).
# ===========================================================================


@pytest.mark.parametrize("kind", BACKENDS)
def test_rate_limit_precedes_authentication_and_is_not_audited(kind, platform):
    h = _build_harness(kind, platform, limits=ControlPlaneLimits(applications=1000, credentials_per_application=1000, control_requests_per_minute=1))
    try:
        with pytest.raises(FoundationError) as exc1:
            h.service.capabilities("bogus-secret-1")
        assert exc1.value.code == "AUTH_INVALID"
        before = len(h.audit_events())
        assert before == 1  # the AUTH_INVALID denial was durably recorded

        with pytest.raises(FoundationError) as exc2:
            h.service.capabilities("bogus-secret-2")
        assert exc2.value.code == "LIMIT_EXCEEDED"
        assert exc2.value.status == 429
        assert "audited" not in exc2.value.details

        after = len(h.audit_events())
        assert after == before, "rate-limit refusals must not add a durable audit row"
    finally:
        h.cleanup()


@pytest.mark.parametrize("kind", BACKENDS)
def test_check_rate_and_rate_precharged_charge_exactly_once(kind, platform):
    """CCR-14 WP-4 round-2 (independent review MAJOR-1): `check_rate()` is
    the public wrapper `control_http.py` calls before it does anything else
    (including reading a request body), charging one token itself; the
    caller then passes `rate_precharged=True` into the operation method it
    calls next so the window is not charged a second time for the same
    logical request -- this is the call pattern `control_http.py` uses on
    every one of its 11 endpoints. Pinned directly at the service level here
    (`test_control_http.py` pins the same thing end-to-end over HTTP)."""
    h = _build_harness(kind, platform, limits=ControlPlaneLimits(applications=1000, credentials_per_application=1000, control_requests_per_minute=2))
    try:
        # One `check_rate()` + one `rate_precharged=True` call = exactly one
        # token, not two -- two such pairs exhaust a bound of 2.
        h.service.check_rate()
        with pytest.raises(FoundationError) as exc1:
            h.service.capabilities("bogus-secret-1", rate_precharged=True)
        assert exc1.value.code == "AUTH_INVALID"  # not LIMIT_EXCEEDED -- the pair only spent 1 token

        h.service.check_rate()
        with pytest.raises(FoundationError) as exc2:
            h.service.capabilities("bogus-secret-2", rate_precharged=True)
        assert exc2.value.code == "AUTH_INVALID"

        # 2 tokens spent against a bound of 2 -- a third `check_rate()` alone
        # now trips it.
        with pytest.raises(FoundationError) as exc3:
            h.service.check_rate()
        assert exc3.value.code == "LIMIT_EXCEEDED"
    finally:
        h.cleanup()

    # A separate harness: `rate_precharged=True` with no preceding
    # `check_rate()` call never charges the window at all -- confirms the
    # flag is a pure skip of the internal charge, not a differently-priced
    # one of its own.
    h2 = _build_harness(kind, platform, limits=ControlPlaneLimits(applications=1000, credentials_per_application=1000, control_requests_per_minute=1))
    try:
        for _ in range(5):
            with pytest.raises(FoundationError) as exc:
                h2.service.capabilities("bogus-secret", rate_precharged=True)
            assert exc.value.code == "AUTH_INVALID"
    finally:
        h2.cleanup()


@pytest.mark.parametrize("kind", BACKENDS)
def test_role_control_issuance_refused_regardless_of_application_state(kind, platform):
    h = _build_harness(kind, platform, limits=ControlPlaneLimits(applications=1000, credentials_per_application=1, control_requests_per_minute=100_000))
    try:
        cred_id = _fresh_id("ctl_")
        secret = "actor-secret-" + secrets.token_urlsafe(8)
        h.seed_control_credential(cred_id, secret, must_rotate=False)

        # (i) application does not exist at all.
        with pytest.raises(FoundationError) as exc:
            h.service.issue_credential(secret, "no_such_app_xyz", "control")
        assert exc.value.code == "CAPABILITY_UNSUPPORTED"

        # (ii) application exists but is disabled.
        app_id = _fresh_id("rc")
        h.service.register_application(secret, app_id)
        h.service.set_application_enabled(secret, app_id, False)
        with pytest.raises(FoundationError) as exc:
            h.service.issue_credential(secret, app_id, "control")
        assert exc.value.code == "CAPABILITY_UNSUPPORTED"

        # (iii) application at its credentials_per_application limit.
        app_id2 = _fresh_id("rc")
        h.service.register_application(secret, app_id2)
        h.service.issue_credential(secret, app_id2, "runtime")  # consumes the limit of 1
        with pytest.raises(FoundationError) as exc:
            h.service.issue_credential(secret, app_id2, "control")
        assert exc.value.code == "CAPABILITY_UNSUPPORTED"
    finally:
        h.cleanup()


@pytest.mark.parametrize("kind", BACKENDS)
def test_must_rotate_gate_precedes_target_resolution(kind, platform):
    h = _build_harness(kind, platform)
    try:
        cred_id = _fresh_id("ctl_")
        secret = "mr-secret-" + secrets.token_urlsafe(8)
        h.seed_control_credential(cred_id, secret, must_rotate=True)

        with pytest.raises(FoundationError) as exc:
            h.service.set_application_enabled(secret, "definitely_absent_app", True)
        assert exc.value.code == "FORBIDDEN"
        assert exc.value.code != "NOT_FOUND"
    finally:
        h.cleanup()


# ===========================================================================
# Section 2: must_rotate allow-list (work order §6 item 2).
# ===========================================================================


@pytest.mark.parametrize("kind", BACKENDS)
def test_must_rotate_allow_list_and_full_access_after_self_rotate(kind, platform):
    h = _build_harness(kind, platform)
    try:
        cred_id = _fresh_id("ctl_")
        secret = "gate-secret-" + secrets.token_urlsafe(8)
        h.seed_control_credential(cred_id, secret, must_rotate=True)

        # Allowed while must_rotate: capabilities.
        caps = h.service.capabilities(secret)
        assert caps["role"] == "control"

        # Every other operation -- all 9 service methods minus the 2 allowed
        # (capabilities, self-rotate), MI-5 (round-2 review) -- is FORBIDDEN,
        # including rotating a *different* id. Target ids below need not
        # exist: the gate fires before target resolution regardless (design
        # order (3) gate -> ... -> (6) resolution), so a made-up id still
        # gets FORBIDDEN, never NOT_FOUND.
        app_id = _fresh_id("gt")
        with pytest.raises(FoundationError) as exc:
            h.service.register_application(secret, app_id)
        assert exc.value.code == "FORBIDDEN"
        with pytest.raises(FoundationError) as exc:
            h.service.list_applications(secret)
        assert exc.value.code == "FORBIDDEN"
        with pytest.raises(FoundationError) as exc:
            h.service.set_application_enabled(secret, app_id, False)
        assert exc.value.code == "FORBIDDEN"
        with pytest.raises(FoundationError) as exc:
            h.service.list_credentials(secret)
        assert exc.value.code == "FORBIDDEN"
        with pytest.raises(FoundationError) as exc:
            h.service.issue_credential(secret, app_id, "runtime")
        assert exc.value.code == "FORBIDDEN"
        with pytest.raises(FoundationError) as exc:
            h.service.rotate_credential(secret, "ctl_totally_different_id00")
        assert exc.value.code == "FORBIDDEN"
        with pytest.raises(FoundationError) as exc:
            h.service.revoke_credential(secret, "crd_totally_different_id00")
        assert exc.value.code == "FORBIDDEN"
        with pytest.raises(FoundationError) as exc:
            h.service.set_credential_enabled(secret, "crd_totally_different_id00", False)
        assert exc.value.code == "FORBIDDEN"

        # The gate denial itself is durably audited, attributed to this
        # test's own actor (the shared Postgres platform's `control_audit`
        # table also carries other tests' rows, so filter on actor_id, not
        # index 0).
        events = h.audit_events()
        gate_denials = [e for e in events if e.get("reason_code") == "FORBIDDEN" and e["outcome"] == "deny" and e.get("actor_id") == cred_id]
        assert len(gate_denials) >= 1

        # Allowed while must_rotate: rotating itself.
        rotated = h.service.rotate_credential(secret, cred_id)
        new_secret = rotated["secret"]
        assert rotated["credential_id"] == cred_id

        # Old secret no longer authenticates at all.
        with pytest.raises(FoundationError):
            h.service.capabilities(secret)

        # Full access now.
        app_id2 = _fresh_id("gt")
        result = h.service.register_application(new_secret, app_id2)
        assert result == {"application_id": app_id2, "enabled": True}
    finally:
        h.cleanup()


# ===========================================================================
# Section 3: same-transaction audit + sink fault injection (work order §6
# item 3).
# ===========================================================================


@pytest.mark.parametrize("kind", BACKENDS)
def test_each_state_change_adds_exactly_one_audit_row(kind, platform):
    h = _build_harness(kind, platform)
    try:
        cred_id = _fresh_id("ctl_")
        secret = "audit-secret-" + secrets.token_urlsafe(8)
        h.seed_control_credential(cred_id, secret, must_rotate=False)

        before = len(h.audit_events())
        app_id = _fresh_id("ad")
        h.service.register_application(secret, app_id)
        assert len(h.audit_events()) == before + 1

        h.service.set_application_enabled(secret, app_id, False)
        assert len(h.audit_events()) == before + 2

        issued = h.service.issue_credential(secret, app_id, "runtime")
        assert len(h.audit_events()) == before + 3

        h.service.rotate_credential(secret, issued["credential_id"])
        assert len(h.audit_events()) == before + 4

        h.service.set_credential_enabled(secret, issued["credential_id"], False)
        assert len(h.audit_events()) == before + 5

        h.service.revoke_credential(secret, issued["credential_id"])
        assert len(h.audit_events()) == before + 6

        # MA-3: extend past application-credential operations to cover the
        # control_credentials unit-of-work family too (rotate + disable on a
        # *second* control credential, distinct from the actor).
        target_id = _fresh_id("ctl_")
        target_secret = "audit-target-secret-" + secrets.token_urlsafe(8)
        h.seed_control_credential(target_id, target_secret, must_rotate=False)
        after_seed = len(h.audit_events())  # seeding itself is out-of-band, not via the service -- no row expected

        h.service.rotate_credential(secret, target_id)
        assert len(h.audit_events()) == after_seed + 1

        h.service.set_credential_enabled(secret, target_id, False)
        assert len(h.audit_events()) == after_seed + 2
    finally:
        h.cleanup()


@pytest.mark.parametrize("kind", BACKENDS)
@pytest.mark.parametrize(
    "scenario",
    ["register_application", "issue_credential", "revoke_credential", "set_credential_enabled_control"],
)
def test_state_change_sink_fault_injection_aborts_the_state_change(kind, platform, scenario):
    """MA-3: covers all three unit-of-work families -- `applications`
    (`register_application`), `credentials` (`issue_credential`/`revoke_
    credential`), and `control_credentials` (`set_credential_enabled` against
    a control credential target). Each scenario asserts both that the
    faulted call itself returns `SERVICE_UNAVAILABLE` (503) and that the
    underlying state genuinely did not persist (via direct store probes
    where the service's own read surface cannot distinguish "not yet
    applied" from "successfully reverted disable" -- e.g. `enabled=True`
    both before any call and after a correctly-rolled-back one)."""
    h = _build_harness(kind, platform)
    try:
        cred_id = _fresh_id("ctl_")
        secret = "fault-secret-" + secrets.token_urlsafe(8)
        h.seed_control_credential(cred_id, secret, must_rotate=False)

        def _assert_authority_trail_unchanged(before: int) -> None:
            # MI-1: checked immediately after the faulted call, BEFORE any
            # clean retry -- a retry legitimately adds its own new
            # `ControlAuthority` event, so this must never be checked after
            # one (that would silently pass even if rollback truncation were
            # broken, as long as the retry itself succeeded).
            if kind == "memory":
                assert len(h.authority.audit_events()) == before

        if scenario == "register_application":
            app_id = _fresh_id("fl")
            authority_events_before = len(h.authority.audit_events()) if kind == "memory" else None
            with _faulted_audit_sink(h, kind, platform):
                with pytest.raises(FoundationError) as exc:
                    h.service.register_application(secret, app_id)
                assert exc.value.code == "SERVICE_UNAVAILABLE"
                assert exc.value.status == 503
            _assert_authority_trail_unchanged(authority_events_before)
            # Not persisted -- registering the same id again must succeed
            # cleanly (a lingering row would raise CONFLICT instead).
            result = h.service.register_application(secret, app_id)
            assert result == {"application_id": app_id, "enabled": True}

        elif scenario == "issue_credential":
            app_id = _fresh_id("fl")
            h.service.register_application(secret, app_id)
            before_count = len([r for r in h.service.list_credentials(secret)["credentials"] if r.get("application_id") == app_id])
            authority_events_before = len(h.authority.audit_events()) if kind == "memory" else None
            with _faulted_audit_sink(h, kind, platform):
                with pytest.raises(FoundationError) as exc:
                    h.service.issue_credential(secret, app_id, "runtime")
                assert exc.value.code == "SERVICE_UNAVAILABLE"
                assert exc.value.status == 503
            _assert_authority_trail_unchanged(authority_events_before)
            after_count = len([r for r in h.service.list_credentials(secret)["credentials"] if r.get("application_id") == app_id])
            assert after_count == before_count, "faulted issue_credential must not have persisted a credential row"
            issued = h.service.issue_credential(secret, app_id, "runtime")
            assert issued["application_id"] == app_id

        elif scenario == "revoke_credential":
            app_id = _fresh_id("fl")
            h.service.register_application(secret, app_id)
            issued = h.service.issue_credential(secret, app_id, "runtime")
            authority_events_before = len(h.authority.audit_events()) if kind == "memory" else None
            with _faulted_audit_sink(h, kind, platform):
                with pytest.raises(FoundationError) as exc:
                    h.service.revoke_credential(secret, issued["credential_id"])
                assert exc.value.code == "SERVICE_UNAVAILABLE"
                assert exc.value.status == 503
            _assert_authority_trail_unchanged(authority_events_before)
            _enabled, revoked = h.credentials_store.get_state(issued["credential_id"])
            assert revoked is False, "faulted revoke_credential must not have persisted the revocation"
            result = h.service.revoke_credential(secret, issued["credential_id"])
            assert result["revoked"] is True

        else:  # set_credential_enabled_control
            target_id = _fresh_id("ctl_")
            target_secret = "fault-target-secret-" + secrets.token_urlsafe(8)
            h.seed_control_credential(target_id, target_secret, must_rotate=False)
            with _faulted_audit_sink(h, kind, platform):
                with pytest.raises(FoundationError) as exc:
                    h.service.set_credential_enabled(secret, target_id, False)
                assert exc.value.code == "SERVICE_UNAVAILABLE"
                assert exc.value.status == 503
            # Control-credential operations never go through `ControlAuthority`
            # at all (design: it has no control-credential concept) -- MI-1's
            # secondary-trail concern does not apply here, nothing to check.
            enabled, _revoked = h.control_credentials_store.get_state(target_id)
            assert enabled is True, "faulted set_credential_enabled(control) must not have persisted the disable"
            result = h.service.set_credential_enabled(secret, target_id, False)
            assert result["enabled"] is False
    finally:
        h.cleanup()


# ===========================================================================
# Section 4: durable denial recording (work order §6 item 4).
# ===========================================================================


@pytest.mark.parametrize("kind", BACKENDS)
def test_denial_audit_insert_failure_becomes_503_for_every_denial_kind(kind, platform):
    h = _build_harness(kind, platform, limits=ControlPlaneLimits(applications=1000, credentials_per_application=1000, control_requests_per_minute=100_000))
    try:
        cred_id = _fresh_id("ctl_")
        secret = "denyfault-secret-" + secrets.token_urlsafe(8)
        h.seed_control_credential(cred_id, secret, must_rotate=False)

        mr_cred_id = _fresh_id("ctl_")
        mr_secret = "denyfault-mr-secret-" + secrets.token_urlsafe(8)
        h.seed_control_credential(mr_cred_id, mr_secret, must_rotate=True)

        app_id = _fresh_id("df")
        h.service.register_application(secret, app_id)

        def _expect_503(body):
            with pytest.raises(FoundationError) as exc:
                body()
            assert exc.value.code == "SERVICE_UNAVAILABLE"
            assert exc.value.status == 503
            assert "audited" not in exc.value.details

        if kind == "memory":
            h.inject_audit_fault(RuntimeError("simulated sink failure"))
            try:
                _expect_503(lambda: h.service.capabilities(None))  # MA-1: AUTH_REQUIRED is audited too
                _expect_503(lambda: h.service.capabilities("totally-bogus-secret"))
                _expect_503(lambda: h.service.list_applications(mr_secret))
                _expect_503(lambda: h.service.issue_credential(secret, app_id, "control"))
            finally:
                h.inject_audit_fault(None)
        else:
            with _control_audit_renamed_away(platform):
                _expect_503(lambda: h.service.capabilities(None))
                _expect_503(lambda: h.service.capabilities("totally-bogus-secret"))
                _expect_503(lambda: h.service.list_applications(mr_secret))
                _expect_503(lambda: h.service.issue_credential(secret, app_id, "control"))
    finally:
        h.cleanup()


@pytest.mark.parametrize("kind", BACKENDS)
def test_authentication_denials_are_durably_audited_with_truthful_attribution(kind, platform):
    """MA-1 (AUTH_REQUIRED must be durably audited -- the cheapest possible
    probe against this surface must leave the same trace a garbage-secret
    probe does) + MA-2, both halves (attribution truthfulness): an
    *unattributed* denial (no secret at all, or a secret matching no
    credential) gets the plain "recorded" R-11 declaration and an audit row
    with `actor_id` `None`; an *identified-but-refused* denial (AUTH_REVOKED,
    or a matching-but-disabled AUTH_INVALID) gets the "attributed" R-11
    declaration, an audit row whose `actor_id` really is the refused
    credential's own id -- and that id appears nowhere in the *response*
    (R-8/§8 m-7: no existence-distinction leak via `details`)."""
    h = _build_harness(kind, platform)
    try:
        recorded_text = "This request is durably recorded; not even a control credential can erase that record."
        attributed_text = "This request is durably recorded and attributed to the credential that made it; not even a control credential can erase that record."

        cred_id = _fresh_id("ctl_")
        secret = "attr-secret-" + secrets.token_urlsafe(8)
        h.seed_control_credential(cred_id, secret, must_rotate=False)

        disabled_id = _fresh_id("ctl_")
        disabled_secret = "attr-disabled-secret-" + secrets.token_urlsafe(8)
        h.seed_control_credential(disabled_id, disabled_secret, must_rotate=False)
        h.disable_control_credential_directly(disabled_id)

        # (MA-1) AUTH_REQUIRED -- no secret at all -- unattributed, recorded.
        req_no_secret = _fresh_id("req")
        with pytest.raises(FoundationError) as exc:
            h.service.capabilities(None, request_id=req_no_secret)
        assert exc.value.code == "AUTH_REQUIRED"
        assert exc.value.details.get("audited") is True
        assert exc.value.details.get("attribution") == recorded_text
        row = _find_audit_row_by_request_id(h, req_no_secret)
        assert row is not None, "AUTH_REQUIRED must add a durable audit row (MA-1)"
        assert row.get("actor_id") is None

        # AUTH_INVALID -- a secret matching no credential at all -- unattributed, recorded.
        req_no_match = _fresh_id("req")
        with pytest.raises(FoundationError) as exc:
            h.service.capabilities("wrong-secret-entirely", request_id=req_no_match)
        assert exc.value.code == "AUTH_INVALID"
        assert exc.value.details.get("attribution") == recorded_text
        row = _find_audit_row_by_request_id(h, req_no_match)
        assert row is not None
        assert row.get("actor_id") is None

        # AUTH_INVALID -- matches a real, disabled credential -- attributed.
        req_disabled = _fresh_id("req")
        with pytest.raises(FoundationError) as exc:
            h.service.capabilities(disabled_secret, request_id=req_disabled)
        assert exc.value.code == "AUTH_INVALID"
        assert exc.value.details.get("attribution") == attributed_text
        assert set(exc.value.details.keys()) == {"audited", "attribution"}, "no new key beyond the declarations, and no credential_id"
        for value in exc.value.details.values():
            assert disabled_id not in str(value), "identified credential_id must never reach the response"
        row = _find_audit_row_by_request_id(h, req_disabled)
        assert row is not None
        assert row.get("actor_id") == disabled_id
        assert row.get("actor_type") == "control_credential"

        # AUTH_REVOKED -- matches a real, revoked credential -- attributed.
        h.revoke_control_credential_directly(cred_id)
        req_revoked = _fresh_id("req")
        with pytest.raises(FoundationError) as exc:
            h.service.capabilities(secret, request_id=req_revoked)
        assert exc.value.code == "AUTH_REVOKED"
        assert exc.value.details.get("attribution") == attributed_text
        assert set(exc.value.details.keys()) == {"audited", "attribution"}
        for value in exc.value.details.values():
            assert cred_id not in str(value)
        row = _find_audit_row_by_request_id(h, req_revoked)
        assert row is not None
        assert row.get("actor_id") == cred_id
        assert row.get("actor_type") == "control_credential"
    finally:
        h.cleanup()


# ===========================================================================
# Section 5: R-7 limits (work order §6 item 5).
# ===========================================================================


@pytest.mark.parametrize("kind", BACKENDS)
def test_applications_limit_at_exact_bound(kind, platform):
    # The Postgres harness shares one module-scoped platform (and therefore
    # one `applications` table) across every "postgres"-kind test in this
    # file -- the bound is set relative to whatever is already registered,
    # not an assumed-empty table, so this test is order-independent.
    seed_credential_id = _fresh_id("ctl_")
    seed_secret = "applim-seed-secret-" + secrets.token_urlsafe(8)
    seed_harness = _build_harness(kind, platform)
    try:
        seed_harness.seed_control_credential(seed_credential_id, seed_secret, must_rotate=False)
        baseline = len(seed_harness.service.list_applications(seed_secret)["applications"])
    finally:
        seed_harness.cleanup()

    limits = ControlPlaneLimits(applications=baseline + 2, credentials_per_application=1000, control_requests_per_minute=100_000)
    h = _build_harness(kind, platform, limits=limits)
    try:
        cred_id = _fresh_id("ctl_")
        secret = "applim-secret-" + secrets.token_urlsafe(8)
        h.seed_control_credential(cred_id, secret, must_rotate=False)

        h.service.register_application(secret, _fresh_id("al"))
        h.service.register_application(secret, _fresh_id("al"))
        with pytest.raises(FoundationError) as exc:
            h.service.register_application(secret, _fresh_id("al"))
        assert exc.value.code == "LIMIT_EXCEEDED"
        assert exc.value.details["resource"] == "applications"
        assert exc.value.details["limit"] == baseline + 2
        # Opus review M-1(b): a representative behavioral (runtime)
        # assertion of `limit_class` on a real response, complementing
        # `test_limit_class_vocabulary.py`'s static AST scan (which proves
        # every call site *declares* it, not that a real response actually
        # carries the value this test asserts).
        assert exc.value.details["limit_class"] == "applications"
    finally:
        h.cleanup()


@pytest.mark.parametrize("kind", BACKENDS)
def test_credentials_per_application_limit_ignores_revoked_rows(kind, platform):
    limits = ControlPlaneLimits(applications=1000, credentials_per_application=1, control_requests_per_minute=100_000)
    h = _build_harness(kind, platform, limits=limits)
    try:
        cred_id = _fresh_id("ctl_")
        secret = "credlim-secret-" + secrets.token_urlsafe(8)
        h.seed_control_credential(cred_id, secret, must_rotate=False)
        app_id = _fresh_id("cl")
        h.service.register_application(secret, app_id)

        issued = h.service.issue_credential(secret, app_id, "runtime")
        with pytest.raises(FoundationError) as exc:
            h.service.issue_credential(secret, app_id, "runtime")
        assert exc.value.code == "LIMIT_EXCEEDED"
        assert exc.value.details["resource"] == "credentials_per_application"
        assert exc.value.details["limit"] == 1
        assert exc.value.details["limit_class"] == "credentials_per_application"  # Opus review M-1(b)

        # Revoking the existing credential frees the slot -- a revoked
        # credential must never count against this limit (R-7).
        h.service.revoke_credential(secret, issued["credential_id"])
        issued2 = h.service.issue_credential(secret, app_id, "runtime")
        assert issued2["credential_id"] != issued["credential_id"]
    finally:
        h.cleanup()


@pytest.mark.parametrize("kind", BACKENDS)
def test_control_requests_per_minute_limit_and_window_recovery(kind, platform):
    limits = ControlPlaneLimits(applications=1000, credentials_per_application=1000, control_requests_per_minute=2)
    h = _build_harness(kind, platform, limits=limits)
    try:
        cred_id = _fresh_id("ctl_")
        secret = "ratelim-secret-" + secrets.token_urlsafe(8)
        h.seed_control_credential(cred_id, secret, must_rotate=False)

        h.service.capabilities(secret)
        h.service.capabilities(secret)
        with pytest.raises(FoundationError) as exc:
            h.service.capabilities(secret)
        assert exc.value.code == "LIMIT_EXCEEDED"
        assert exc.value.status == 429
        assert exc.value.details["resource"] == "control_requests_per_minute"
        assert exc.value.details["limit_class"] == "control_requests_per_minute"  # Opus review M-1(b)

        # Window rollover: advancing the injected clock past 60s frees the
        # window without a real wall-clock sleep (work order §3: the time
        # source must be injectable).
        _clock_state["now"] += 61
        h.service.capabilities(secret)  # must succeed again
    finally:
        h.cleanup()


# ===========================================================================
# Section 6: semantics (work order §6 item 6).
# ===========================================================================


@pytest.mark.parametrize("kind", BACKENDS)
def test_issued_secret_appears_only_in_the_response(kind, platform):
    h = _build_harness(kind, platform)
    try:
        cred_id = _fresh_id("ctl_")
        secret = "sem-secret-" + secrets.token_urlsafe(8)
        h.seed_control_credential(cred_id, secret, must_rotate=False)
        app_id = _fresh_id("sm")
        h.service.register_application(secret, app_id)
        req_id = _fresh_id("req")
        issued = h.service.issue_credential(secret, app_id, "developer", request_id=req_id)

        listing = h.service.list_credentials(secret)
        for row in listing["credentials"]:
            assert "secret" not in row
            assert "verifier" not in row
            assert "must_rotate" not in row

        # MI-3: the control row's own shape -- `role == "control"` and no
        # `application_id` key at all (design §2), distinct from an
        # application-credential row's `role` (`runtime`/`developer`) and
        # `application_id` presence.
        control_rows = [row for row in listing["credentials"] if row["credential_id"] == cred_id]
        assert len(control_rows) == 1
        assert control_rows[0]["role"] == "control"
        assert "application_id" not in control_rows[0]

        for event in h.audit_events():
            for value in event.values():
                if isinstance(value, str):
                    assert issued["secret"] not in value

        # MI-6 (supervisor ruling): the audit `role` field names the ACTOR's
        # role, always "control" for a control-plane operation -- never the
        # *issued* credential's own role (here, "developer"), which earlier
        # code mistakenly wrote into this same field.
        issue_row = _find_audit_row_by_request_id(h, req_id)
        assert issue_row is not None
        assert issue_row.get("role") == "control"
    finally:
        h.cleanup()


@pytest.mark.parametrize("kind", BACKENDS)
def test_rotate_semantics_revoked_refused_disabled_allowed(kind, platform):
    h = _build_harness(kind, platform)
    try:
        cred_id = _fresh_id("ctl_")
        secret = "rot-secret-" + secrets.token_urlsafe(8)
        h.seed_control_credential(cred_id, secret, must_rotate=False)
        app_id = _fresh_id("rt")
        h.service.register_application(secret, app_id)
        issued = h.service.issue_credential(secret, app_id, "runtime")

        # disabled -> rotate allowed.
        h.service.set_credential_enabled(secret, issued["credential_id"], False)
        rotated = h.service.rotate_credential(secret, issued["credential_id"])
        assert rotated["credential_id"] == issued["credential_id"]
        assert rotated["secret"] != issued["secret"]

        # revoked -> rotate refused.
        issued2 = h.service.issue_credential(secret, app_id, "runtime")
        h.service.revoke_credential(secret, issued2["credential_id"])
        with pytest.raises(FoundationError) as exc:
            h.service.rotate_credential(secret, issued2["credential_id"])
        assert exc.value.code == "VALIDATION_FAILED"
    finally:
        h.cleanup()


@pytest.mark.parametrize("kind", BACKENDS)
def test_revoke_is_terminal_and_enable_does_not_un_revoke(kind, platform):
    h = _build_harness(kind, platform)
    try:
        cred_id = _fresh_id("ctl_")
        secret = "term-secret-" + secrets.token_urlsafe(8)
        h.seed_control_credential(cred_id, secret, must_rotate=False)
        app_id = _fresh_id("tm")
        h.service.register_application(secret, app_id)
        issued = h.service.issue_credential(secret, app_id, "runtime")

        result = h.service.revoke_credential(secret, issued["credential_id"])
        assert result["revoked"] is True

        result2 = h.service.set_credential_enabled(secret, issued["credential_id"], True)
        assert result2["revoked"] is True
    finally:
        h.cleanup()


@pytest.mark.parametrize("kind", BACKENDS)
def test_application_credential_revoke_accepts_q1_fields_without_inspecting_them(kind, platform):
    """Contract 1.2.0 `destructive_confirmation.non_destructive_requests`
    (design docs/design/DESTRUCTIVE_CONFIRMATION_V1.md R-3): an application
    credential's revocation never meets the "last remaining active control
    credential" gate condition at all, so `destructive`/`confirmation` are
    accepted (schema-valid) but never inspected -- this is now a NARROWER
    claim than this test's own pre-WP-3 name implied (which read as "no
    revoke ever inspects these fields" -- no longer true now that the last-
    active-control-credential gate exists, see `test_revoking_the_last_
    live_control_credential_requires_confirmation` below for that path).
    """
    h = _build_harness(kind, platform)
    try:
        cred_id = _fresh_id("ctl_")
        secret = "q1-secret-" + secrets.token_urlsafe(8)
        h.seed_control_credential(cred_id, secret, must_rotate=False)
        app_id = _fresh_id("q1")
        h.service.register_application(secret, app_id)
        issued = h.service.issue_credential(secret, app_id, "runtime")

        result = h.service.revoke_credential(secret, issued["credential_id"])
        assert result["revoked"] is True

        issued2 = h.service.issue_credential(secret, app_id, "runtime")
        result2 = h.service.revoke_credential(
            secret, issued2["credential_id"], destructive=False, confirmation="not the real confirmation phrase at all"
        )
        assert result2["revoked"] is True
    finally:
        h.cleanup()


@pytest.mark.parametrize("kind", BACKENDS)
def test_revoking_a_non_last_control_credential_accepts_q1_fields_without_inspecting_them(kind, platform):
    """The task-list's other named non-gate path (design docs/design/
    DESTRUCTIVE_CONFIRMATION_V1.md R-3/Q1-D1): revoking a control credential
    that is NOT the last remaining active one never meets the gate
    condition either -- only application-credential revoke was covered by
    the test immediately above. Two live control credentials exist here
    (the seeded `cred_id` plus a second one); revoking the second one,
    unconfirmed, must succeed and must leave `cred_id` itself untouched.
    """
    h = _build_harness(kind, platform)
    try:
        cred_id = _fresh_id("ctl_")
        secret = "q1-secret-" + secrets.token_urlsafe(8)
        h.seed_control_credential(cred_id, secret, must_rotate=False)
        _ensure_sole_active_control_credential(h, cred_id)

        second_id = _fresh_id("ctl_")
        second_secret = "q1-secret2-" + secrets.token_urlsafe(8)
        h.seed_control_credential(second_id, second_secret, must_rotate=False)

        # Two live control credentials now exist -- `second_id` is not the
        # last one, so its revoke is never gated.
        result = h.service.revoke_credential(secret, second_id)
        assert result["revoked"] is True

        # `cred_id` itself is untouched and still fully live.
        caps = h.service.capabilities(secret)
        assert caps["role"] == "control"
    finally:
        h.cleanup()


@pytest.mark.parametrize("kind", BACKENDS)
def test_revoke_credential_rejects_truthy_non_boolean_destructive_and_non_string_confirmation(kind, platform):
    """Review blocker B-1 (control plane, service level): `ControlPlaneService.
    revoke_credential` type-checks its own `destructive`/`confirmation`
    parameters UNCONDITIONALLY -- before `_locate_credential` even runs,
    regardless of whether this particular revoke would ever meet the gate
    condition. A truthy-but-non-boolean `destructive` (the string `"true"`)
    and a non-string `confirmation` (an int) must each be rejected as
    `VALIDATION_FAILED`, and the target credential must remain untouched.
    """
    h = _build_harness(kind, platform)
    try:
        cred_id = _fresh_id("ctl_")
        secret = "b1-secret-" + secrets.token_urlsafe(8)
        h.seed_control_credential(cred_id, secret, must_rotate=False)
        _ensure_sole_active_control_credential(h, cred_id)

        with pytest.raises(FoundationError) as exc:
            h.service.revoke_credential(secret, cred_id, destructive="true", confirmation="whatever")
        assert exc.value.code == "VALIDATION_FAILED"

        with pytest.raises(FoundationError) as exc:
            h.service.revoke_credential(secret, cred_id, destructive=True, confirmation=12345)
        assert exc.value.code == "VALIDATION_FAILED"

        # untouched by either rejected attempt.
        caps = h.service.capabilities(secret)
        assert caps["role"] == "control"
    finally:
        h.cleanup()


@pytest.mark.parametrize("kind", BACKENDS)
def test_revoking_an_already_revoked_different_credential_is_never_gated_by_target_identity(kind, platform):
    """Opus review minor m-1: the gate's "is this the last active one"
    judgment must check the TARGET credential's own identity against the
    sole active row, not merely that exactly one active row exists overall
    -- `len(active_ids) == 1 and active_ids[0] == credential_id`, never
    `len(active_ids) == 1` alone. With exactly one live control credential
    (`cred_id`), revoking a DIFFERENT, already-revoked credential must
    never be gated: it executes unconditionally (an idempotent no-op),
    unconfirmed."""
    h = _build_harness(kind, platform)
    try:
        cred_id = _fresh_id("ctl_")
        secret = "m1-secret-" + secrets.token_urlsafe(8)
        h.seed_control_credential(cred_id, secret, must_rotate=False)
        _ensure_sole_active_control_credential(h, cred_id)

        other_id = _fresh_id("ctl_")
        other_secret = "m1-other-secret-" + secrets.token_urlsafe(8)
        h.seed_control_credential(other_id, other_secret, must_rotate=False)
        h.revoke_control_credential_directly(other_id)  # already revoked -- not an active row

        # Exactly one active row (cred_id) exists now -- revoking the
        # OTHER, already-revoked credential must not be gated.
        result = h.service.revoke_credential(secret, other_id)
        assert result["revoked"] is True

        # cred_id itself is untouched and still fully live.
        caps = h.service.capabilities(secret)
        assert caps["role"] == "control"
    finally:
        h.cleanup()


@pytest.mark.parametrize("kind", BACKENDS)
def test_issuance_to_a_disabled_application_is_allowed(kind, platform):
    h = _build_harness(kind, platform)
    try:
        cred_id = _fresh_id("ctl_")
        secret = "dis-secret-" + secrets.token_urlsafe(8)
        h.seed_control_credential(cred_id, secret, must_rotate=False)
        app_id = _fresh_id("da")
        h.service.register_application(secret, app_id)
        h.service.set_application_enabled(secret, app_id, False)

        issued = h.service.issue_credential(secret, app_id, "runtime")
        assert issued["application_id"] == app_id
    finally:
        h.cleanup()


def _ensure_sole_active_control_credential(h: types.SimpleNamespace, keep_id: str) -> None:
    """Test-only setup helper (not a product concern): the `platform`
    fixture backing the `postgres` harness is module-scoped (real
    PostgreSQL schema, shared across every test in this module), so control
    credentials seeded by earlier tests in this same module run can remain
    live (enabled and not revoked) here -- unlike the `memory` harness,
    which builds a brand-new, empty `ControlCredentialStore` per test, so
    this is a genuine no-op there. Revokes every OTHER live row directly
    (bypassing the service layer entirely, the same store-level access
    `seed_control_credential` itself uses) so the gate's own "exactly one
    active row" precondition is genuinely true regardless of what earlier
    tests left behind.
    """
    if h.kind != "postgres":
        return
    for credential_id, enabled, revoked in h.control_credentials_store.list_all():
        if credential_id != keep_id and enabled and not revoked:
            h.revoke_control_credential_directly(credential_id)


@pytest.mark.parametrize("kind", BACKENDS)
def test_revoking_the_last_live_control_credential_requires_confirmation(kind, platform):
    """Contract 1.2.0 `destructive_confirmation` (design docs/design/
    DESTRUCTIVE_CONFIRMATION_V1.md R-3): revoking the LAST remaining active
    (enabled and not revoked) control credential now requires a valid
    confirmation -- this WP's own effectivization of the previously-pending
    Q-1 question (superseding this test's own pre-WP-3 name/behavior, which
    asserted this was unconditionally permitted). Unconfirmed -> denied with
    the four-key declaration; confirmed with the real, freshly-computed
    phrase -> executes, and the credential is genuinely revoked (`AUTH_
    REVOKED` on the next authenticated call, unchanged from before this WP).
    """
    h = _build_harness(kind, platform)
    try:
        cred_id = _fresh_id("ctl_")
        secret = "last-secret-" + secrets.token_urlsafe(8)
        h.seed_control_credential(cred_id, secret, must_rotate=False)
        _ensure_sole_active_control_credential(h, cred_id)

        with pytest.raises(FoundationError) as exc:
            h.service.revoke_credential(secret, cred_id)
        assert exc.value.code == "DESTRUCTIVE_CONFIRMATION_REQUIRED"
        assert exc.value.status == 409
        details = exc.value.details
        for key in ("required_confirmation", "consequence", "reversible_alternative", "recovery"):
            assert key in details, f"missing declaration key {key!r}: {details!r}"
        assert isinstance(details["required_confirmation"], str) and details["required_confirmation"]
        assert isinstance(details["consequence"], str) and details["consequence"]
        assert details["required_confirmation"] == revoke_last_control_credential_confirmation_phrase(cred_id)

        # the credential is still fully live -- an unconfirmed probe never
        # executes (SI-09).
        caps = h.service.capabilities(secret)
        assert caps["role"] == "control"

        result = h.service.revoke_credential(
            secret, cred_id, destructive=True, confirmation=details["required_confirmation"]
        )
        assert result["revoked"] is True
        with pytest.raises(FoundationError) as exc:
            h.service.capabilities(secret)
        assert exc.value.code == "AUTH_REVOKED"
    finally:
        h.cleanup()


@pytest.mark.parametrize("kind", BACKENDS)
def test_revoking_the_last_live_control_credential_denial_carries_audited_and_attribution(kind, platform):
    """r2db-local test (design docs/design/DESTRUCTIVE_CONFIRMATION_V1.md
    R-3; moved here from C-06's own V7 per that vector's own docstring,
    review M-7 supervisor ruling -- the contract itself declares `audited`
    an OPTIONAL, code-agnostic key, never a `DESTRUCTIVE_CONFIRMATION_
    REQUIRED`-specific requirement, so this stays r2db-local rather than
    promoted into the common suite): the gate's own denial goes through
    `_deny`, which durably records the denial and attaches truthful
    `audited: true`/`attribution` declarations alongside the four contract-
    required keys on the SAME `details` mapping.
    """
    h = _build_harness(kind, platform)
    try:
        cred_id = _fresh_id("ctl_")
        secret = "aud-secret-" + secrets.token_urlsafe(8)
        h.seed_control_credential(cred_id, secret, must_rotate=False)
        _ensure_sole_active_control_credential(h, cred_id)

        before_events = len(h.audit_events())
        with pytest.raises(FoundationError) as exc:
            h.service.revoke_credential(secret, cred_id)
        details = exc.value.details
        assert details.get("audited") is True, f"audited: true was not attached to the gate denial: {details!r}"
        assert isinstance(details.get("attribution"), str) and details["attribution"], (
            f"attribution was not attached to the gate denial: {details!r}"
        )
        # every one of the contract's own four declarations still present
        # alongside audited/attribution (design R-3: "audited 等が同居する").
        for key in ("required_confirmation", "consequence", "reversible_alternative", "recovery"):
            assert key in details

        # Opus review M-3: `audited: true` must be backed by a REAL, durable
        # audit row -- not merely a details key the response happens to
        # carry. Reads the audit sink back (an independent connection/pool
        # from the state-changing `control_credentials_unit_of_work` the
        # gate's own denial fires from inside, per `_deny`'s own updated
        # docstring) and confirms the denial event genuinely landed.
        after_events = h.audit_events()
        assert len(after_events) == before_events + 1, (
            f"expected exactly one new durable audit event for this denial -- before={before_events}, "
            f"after={len(after_events)}"
        )
        denial_event = after_events[-1]
        assert denial_event["outcome"] == "deny"
        assert denial_event["reason_code"] == "DESTRUCTIVE_CONFIRMATION_REQUIRED"
        assert denial_event["actor_id"] == cred_id

        # ... and the credential itself is genuinely NOT revoked (the gate
        # denial must never have a side effect on the credential it denied
        # revoking) -- it still authenticates.
        caps = h.service.capabilities(secret)
        assert caps["role"] == "control"
    finally:
        h.cleanup()


class _GateOrderProbeBackend:
    """`ControlBackend` test double (WP-3 mutation-injection completion
    condition (vi), design docs/design/DESTRUCTIVE_CONFIRMATION_V1.md R-3/
    WP-0 MA-2): a minimal, deterministic way to catch the exact mutation
    that same condition names -- moving the gate's own "is this the last
    active control credential" judgment to before `control_credentials_
    unit_of_work` opens (or after it closes), rather than inside it.

    `control_credentials_unit_of_work` hands out a `_Work` token that is
    `active` only for the duration of the `with` block; `control_
    credentials_locked` (the method `ControlPlaneService.revoke_credential`
    calls to make that judgment) asserts the token it was given is still
    `active` at the moment it is called. A real, live PostgreSQL connection
    (`PostgresControlCredentialStore.list_all_for_update`'s own `FOR UPDATE`
    lock, exercised directly and deterministically by `test_control_plane_
    store.py::test_control_credentials_locked_scan_serializes_against_a_
    concurrent_scan`) is what actually SERIALIZES two real concurrent
    revokes against each other in production; this test double instead
    verifies, without any real concurrency or timing dependence, that
    `ControlPlaneService`'s own orchestration calls that locking read at
    the one call site where its serialization guarantee is real -- inside
    the open transaction, not before or after it.
    """

    class _Work:
        def __init__(self) -> None:
            self.active = False

    def __init__(self, *, credential_id: str) -> None:
        self._credential_id = credential_id
        self.locked_call_count = 0

    def authenticate(self, secret):
        return ControlAuthContext("ctl_probe_actor", False)

    def credential_state(self, credential_id):
        return None  # never an application credential on this double

    def control_credential_state(self, credential_id):
        if credential_id == self._credential_id:
            return (True, False)  # enabled, not revoked
        return None

    @contextmanager
    def control_credentials_unit_of_work(self):
        work = self._Work()
        work.active = True
        try:
            yield work
        finally:
            work.active = False

    def control_credentials_locked(self, work):
        self.locked_call_count += 1
        assert getattr(work, "active", False) is True, (
            "control_credentials_locked was called while its own control_credentials_unit_of_work's "
            "`work` token was not active -- the gate's judgment must be made INSIDE the same "
            "transaction as the state change (design R-3/WP-0 MA-2), never before it opens or after "
            "it closes"
        )
        return [(self._credential_id, True, False)]

    def set_control_credential_state(self, credential_id, *, enabled, revoked, work):
        assert getattr(work, "active", False) is True, (
            "set_control_credential_state was called outside the open control_credentials_unit_of_work"
        )


class _NullAudit:
    def append(self, **kwargs):
        return None


def test_revoke_credential_gate_judgment_is_made_inside_the_open_transaction():
    """Deterministic, non-timing-dependent counterpart to `test_control_
    plane_store.py::test_control_credentials_locked_scan_serializes_
    against_a_concurrent_scan` -- see `_GateOrderProbeBackend`'s own
    docstring. Constructs a real `ControlPlaneService` against the probe
    backend above (a single control credential, the gate's own
    precondition) and calls the real, unmodified `revoke_credential` --
    the probe's own internal assertion is what actually catches mutation
    (vi) ("gate 判定を uow 外へ"): if the real orchestration is ever changed
    to read `control_credentials_locked` before opening (or after closing)
    the transaction, this test fails immediately and unconditionally,
    regardless of any real thread scheduling.
    """
    credential_id = "ctl_probe_only"
    backend = _GateOrderProbeBackend(credential_id=credential_id)
    service = ControlPlaneService(backend, audit=_NullAudit())

    with pytest.raises(FoundationError) as exc:
        service.revoke_credential("irrelevant-secret", credential_id)
    assert exc.value.code == "DESTRUCTIVE_CONFIRMATION_REQUIRED"
    assert backend.locked_call_count == 1


@pytest.mark.parametrize("kind", BACKENDS)
def test_credential_id_operations_resolve_across_both_tables(kind, platform):
    """Design §2: id resolution queries both stores, never trusting the
    `crd_`/`ctl_` prefix as semantics -- exercised here by disabling both an
    application credential and a control credential through the exact same
    `set_credential_enabled` service method."""
    h = _build_harness(kind, platform)
    try:
        cred_id = _fresh_id("ctl_")
        secret = "dual-secret-" + secrets.token_urlsafe(8)
        h.seed_control_credential(cred_id, secret, must_rotate=False)

        second_control_id = _fresh_id("ctl_")
        second_control_secret = "dual-secret2-" + secrets.token_urlsafe(8)
        h.seed_control_credential(second_control_id, second_control_secret, must_rotate=False)

        app_id = _fresh_id("dl")
        h.service.register_application(secret, app_id)
        issued = h.service.issue_credential(secret, app_id, "runtime")

        app_result = h.service.set_credential_enabled(secret, issued["credential_id"], False)
        assert app_result == {"credential_id": issued["credential_id"], "enabled": False, "revoked": False}

        control_result = h.service.set_credential_enabled(secret, second_control_id, False)
        assert control_result == {"credential_id": second_control_id, "enabled": False, "revoked": False}

        with pytest.raises(FoundationError) as exc:
            h.service.set_credential_enabled(secret, "no_such_id_at_all", True)
        assert exc.value.code == "NOT_FOUND"
    finally:
        h.cleanup()


@pytest.mark.parametrize("kind", BACKENDS)
def test_negative_paths_validation_conflict_not_found(kind, platform):
    """MI-2 (round-2 review): the shape/target-resolution refusals not
    otherwise exercised as a side effect of some other test -- invalid
    `application_id`, duplicate registration, `set_application_enabled` on a
    missing application, and an invalid `role` on issuance. (No-secret ->
    `AUTH_REQUIRED` is covered by `test_authentication_denials_are_durably_
    audited_with_truthful_attribution`, MA-1's own dedicated test.)"""
    h = _build_harness(kind, platform)
    try:
        cred_id = _fresh_id("ctl_")
        secret = "neg-secret-" + secrets.token_urlsafe(8)
        h.seed_control_credential(cred_id, secret, must_rotate=False)

        # invalid application_id -> VALIDATION_FAILED
        with pytest.raises(FoundationError) as exc:
            h.service.register_application(secret, "Not-A-Valid-Slug!")
        assert exc.value.code == "VALIDATION_FAILED"
        with pytest.raises(FoundationError) as exc:
            h.service.register_application(secret, "")
        assert exc.value.code == "VALIDATION_FAILED"
        with pytest.raises(FoundationError) as exc:
            h.service.register_application(secret, 12345)
        assert exc.value.code == "VALIDATION_FAILED"

        # duplicate register -> CONFLICT
        app_id = _fresh_id("ng")
        h.service.register_application(secret, app_id)
        with pytest.raises(FoundationError) as exc:
            h.service.register_application(secret, app_id)
        assert exc.value.code == "CONFLICT"

        # set_application_enabled on a missing app -> NOT_FOUND
        with pytest.raises(FoundationError) as exc:
            h.service.set_application_enabled(secret, "no_such_app_at_all_xyz", True)
        assert exc.value.code == "NOT_FOUND"

        # invalid role on issue -> VALIDATION_FAILED
        with pytest.raises(FoundationError) as exc:
            h.service.issue_credential(secret, app_id, "superuser")
        assert exc.value.code == "VALIDATION_FAILED"
        with pytest.raises(FoundationError) as exc:
            h.service.issue_credential(secret, app_id, None)
        assert exc.value.code == "VALIDATION_FAILED"
    finally:
        h.cleanup()


# ===========================================================================
# Section 7: R-11 deterrence declarations (work order §6 item 7).
# ===========================================================================


@pytest.mark.parametrize("kind", BACKENDS)
def test_deterrence_declarations_present_absent_and_futility(kind, platform):
    # control_requests_per_minute=2: the register_application call below
    # consumes the first slot, the AUTH_INVALID probe consumes the second,
    # and the third call (capabilities(secret)) is the one that must observe
    # LIMIT_EXCEEDED.
    h = _build_harness(kind, platform, limits=ControlPlaneLimits(applications=1000, credentials_per_application=1000, control_requests_per_minute=2))
    try:
        cred_id = _fresh_id("ctl_")
        secret = "decl-secret-" + secrets.token_urlsafe(8)
        h.seed_control_credential(cred_id, secret, must_rotate=False)
        app_id = _fresh_id("dc")
        h.service.register_application(secret, app_id)  # consumes rate slot 1 of 2

        # AUTH_INVALID -> audited + attribution, no futility.
        with pytest.raises(FoundationError) as exc:
            h.service.capabilities("bogus")
        assert exc.value.details.get("audited") is True
        assert "attribution" in exc.value.details
        assert "futility" not in exc.value.details

        # Rate-limit denial -> no audited flag at all.
        with pytest.raises(FoundationError) as exc:
            h.service.capabilities(secret)
        assert exc.value.code == "LIMIT_EXCEEDED"
        assert "audited" not in exc.value.details

        # role=control -> audited + attribution + futility (separate,
        # unlimited-rate harness so the capability denial itself is reached
        # cleanly).
        h2 = _build_harness(kind, platform, limits=ControlPlaneLimits(applications=1000, credentials_per_application=1000, control_requests_per_minute=100_000))
        try:
            cred_id2 = _fresh_id("ctl_")
            secret2 = "decl-secret2-" + secrets.token_urlsafe(8)
            h2.seed_control_credential(cred_id2, secret2, must_rotate=False)
            app_id2 = _fresh_id("dc")
            h2.service.register_application(secret2, app_id2)
            with pytest.raises(FoundationError) as exc:
                h2.service.issue_credential(secret2, app_id2, "control")
            assert exc.value.details.get("audited") is True
            assert "attribution" in exc.value.details
            assert exc.value.details.get("futility")
        finally:
            h2.cleanup()
    finally:
        h.cleanup()


@pytest.mark.parametrize("kind", BACKENDS)
def test_audited_true_round_trips_to_a_real_audit_row_for_every_denial_kind(kind, platform):
    """R-11's own truthfulness requirement, mechanically verified (work
    order §6 item 7): whenever a denial's `details` claims `audited: true`,
    a matching durable `control_audit` row must actually exist -- for every
    denial kind this service produces (`AUTH_REQUIRED`, `AUTH_INVALID`,
    must_rotate `FORBIDDEN`, `role=control` `CAPABILITY_UNSUPPORTED`).

    MI-4 (round-2 review): each probe passes its own fresh `request_id` and
    is matched *by that exact id*, not by an `actor_id`-in-a-set heuristic --
    the Postgres harness shares one `control_audit` table across every
    "postgres"-kind test in this module, so a weaker match could silently
    pass by matching a different test's leftover row instead of this one's
    own."""
    h = _build_harness(kind, platform)
    try:
        cred_id = _fresh_id("ctl_")
        secret = "rt-secret-" + secrets.token_urlsafe(8)
        h.seed_control_credential(cred_id, secret, must_rotate=False)
        mr_cred_id = _fresh_id("ctl_")
        mr_secret = "rt-mr-secret-" + secrets.token_urlsafe(8)
        h.seed_control_credential(mr_cred_id, mr_secret, must_rotate=True)
        app_id = _fresh_id("rv")
        h.service.register_application(secret, app_id)

        probes = []

        req_id = _fresh_id("req")
        with pytest.raises(FoundationError) as exc:
            h.service.capabilities(None, request_id=req_id)
        probes.append((req_id, exc.value))

        req_id = _fresh_id("req")
        with pytest.raises(FoundationError) as exc:
            h.service.capabilities("definitely-not-a-real-secret", request_id=req_id)
        probes.append((req_id, exc.value))

        req_id = _fresh_id("req")
        with pytest.raises(FoundationError) as exc:
            h.service.list_applications(mr_secret, request_id=req_id)
        probes.append((req_id, exc.value))

        req_id = _fresh_id("req")
        with pytest.raises(FoundationError) as exc:
            h.service.issue_credential(secret, app_id, "control", request_id=req_id)
        probes.append((req_id, exc.value))

        for req_id, denial in probes:
            assert denial.details.get("audited") is True
            row = _find_audit_row_by_request_id(h, req_id)
            assert row is not None, f"no durable audit row found for a denial claiming audited=true (code={denial.code}, request_id={req_id})"
            assert row.get("reason_code") == denial.code
            assert row["outcome"] == "deny"
    finally:
        h.cleanup()


# ===========================================================================
# Section 8: capabilities document (work order §6 item 8).
# ===========================================================================


@pytest.mark.parametrize("kind", BACKENDS)
def test_capabilities_document_shape_and_injected_limits(kind, platform):
    limits = ControlPlaneLimits(applications=42, credentials_per_application=7, control_requests_per_minute=99)
    h = _build_harness(kind, platform, limits=limits)
    try:
        cred_id = _fresh_id("ctl_")
        secret = "caps-secret-" + secrets.token_urlsafe(8)
        h.seed_control_credential(cred_id, secret, must_rotate=False)

        caps = h.service.capabilities(secret)
        assert caps["contract_version"] == "1.2.0"
        assert caps["capabilities"]["control_plane"]["status"] == "enabled"
        assert caps["capabilities"]["audit_query"]["status"] == "unavailable"
        assert caps["limits"] == {"applications": 42, "credentials_per_application": 7, "control_requests_per_minute": 99}
        assert caps["limit_enforcement"] == {"applications": "enforced", "credentials_per_application": "enforced", "control_requests_per_minute": "enforced"}
        assert caps["authorization_propagation_bound_ms"] == 0
        assert caps["role"] == "control"

        # must_rotate does not block capabilities (R-5).
        mr_cred_id = _fresh_id("ctl_")
        mr_secret = "caps-mr-secret-" + secrets.token_urlsafe(8)
        h.seed_control_credential(mr_cred_id, mr_secret, must_rotate=True)
        caps2 = h.service.capabilities(mr_secret)
        assert caps2["role"] == "control"
    finally:
        h.cleanup()


# ===========================================================================
# Section 9: ControlAuthority delegation + `work=` backward compatibility
# (work order §6 item 9).
# ===========================================================================


def test_in_memory_backend_delegates_application_and_credential_lifecycle_to_control_authority():
    """work order §6 item 9: the in-memory backend's register/issue/enable/
    disable must go *through* `ControlAuthority`, not bypass it -- observed
    here via `ControlAuthority`'s own pre-existing in-memory audit trail (a
    completely separate sink from `control_audit`), which only ever receives
    an event when `ControlAuthority`'s own methods actually ran."""
    h = _memory_harness(_GENEROUS_LIMITS)
    try:
        cred_id = _fresh_id("ctl_")
        secret = "deleg-secret-" + secrets.token_urlsafe(8)
        h.seed_control_credential(cred_id, secret, must_rotate=False)

        before = len(h.authority.audit_events())
        app_id = _fresh_id("dg")
        h.service.register_application(secret, app_id)
        after_register = h.authority.audit_events()
        assert len(after_register) == before + 1
        assert after_register[-1]["operation"] == "register_application"

        h.service.set_application_enabled(secret, app_id, False)
        after_disable = h.authority.audit_events()
        assert len(after_disable) == before + 2
        assert after_disable[-1]["operation"] == "disable_application"

        issued = h.service.issue_credential(secret, app_id, "runtime")
        after_issue = h.authority.audit_events()
        assert len(after_issue) == before + 3
        assert after_issue[-1]["operation"] == "issue_credential"

        h.service.set_credential_enabled(secret, issued["credential_id"], False)
        after_disable_cred = h.authority.audit_events()
        assert len(after_disable_cred) == before + 4
        assert after_disable_cred[-1]["operation"] == "set_credential_state"
    finally:
        h.cleanup()


def test_control_authority_work_parameter_defaults_preserve_existing_callers():
    """`ControlAuthority.issue_credential`/`.set_credential_state`'s new
    `work=None` keyword-only parameter (CCR-14 WP-3, service.py) must not
    change behaviour for a caller that omits it -- the exact pre-WP-3 call
    form every existing test in this repository already uses."""
    credentials = CredentialStore(pepper=PEPPER)
    data_service = DataService(credentials)
    authority = ControlAuthority(data_service)
    authority.register_application("legacy-app")
    authority.issue_credential("legacy-cred", "legacy-app", "runtime", "legacy-secret")
    context = credentials.authenticate("legacy-secret")
    assert context.application_id == "legacy-app"
    authority.set_credential_state("legacy-cred", enabled=False)
    with pytest.raises(FoundationError) as exc:
        credentials.authenticate("legacy-secret")
    assert exc.value.code == "AUTH_INVALID"


# ===========================================================================
# Section 10: `control_plane.py` stays importable without `psycopg` (round-2
# review MI-10) -- mirrors `r2db_api/__init__.py`'s own documented property
# for the top-level package.
# ===========================================================================


def test_control_plane_module_importable_and_usable_without_psycopg() -> None:
    """A fresh subprocess (never a manipulation of *this* process' `sys.
    modules`/import machinery, which risks corrupting later tests in this
    same session) blocks `import psycopg` and confirms `r2db_api.control_
    plane` still imports, and a fully in-memory `ControlPlaneService` still
    constructs and runs one operation end to end -- `PostgresControlBackend`
    is never touched by a caller that only wants the in-memory backend, so
    it must not force a `psycopg` dependency onto that caller (MI-10)."""
    script = (
        "import sys\n"
        "sys.path.insert(0, %r)\n"
        "sys.modules['psycopg'] = None  # any subsequent 'import psycopg' raises ImportError\n"
        "import r2db_api.control_plane as cp\n"
        "from r2db_api.auth import ControlCredentialStore, CredentialStore\n"
        "from r2db_api.audit import ControlAuditSink\n"
        "from r2db_api.service import ControlAuthority, DataService\n"
        "credentials = CredentialStore(pepper='psycopg-optional-pepper')\n"
        "data_service = DataService(credentials)\n"
        "authority = ControlAuthority(data_service)\n"
        "control_credentials = ControlCredentialStore(pepper='psycopg-optional-ctl-pepper')\n"
        "with control_credentials.unit_of_work() as work:\n"
        "    control_credentials.add('ctl_probe0000000', 'probe-secret', work=work)\n"
        "    control_credentials.rotate('ctl_probe0000000', 'probe-secret', work=work)\n"
        "backend = cp.InMemoryControlBackend(authority, control_credentials)\n"
        "service = cp.ControlPlaneService(backend, audit=ControlAuditSink())\n"
        "caps = service.capabilities('probe-secret')\n"
        "assert caps['role'] == 'control'\n"
        "print('OK')\n"
    ) % (str(Path(__file__).resolve().parents[1] / "src"),)
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert "OK" in result.stdout
