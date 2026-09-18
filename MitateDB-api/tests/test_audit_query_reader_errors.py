"""`PostgresAuditQueryStore.query`'s own `psycopg.Error` handling: before
this file existed, any `psycopg.Error` raised while connecting/executing/
fetching (including a `QueryCanceled` from the `mitatedbsvc_auditreader`
role's own `statement_timeout`, migration `0013_role_statement_timeouts.
sql`) propagated unclassified out of `query`, the only reader method in
this peer's own platform-side store family with no `except psycopg.Error`
at all.

`query` now classifies in the same two-stage shape every other
platform-side store in this peer already uses:

- `psycopg.errors.InsufficientPrivilege` (a PERMANENT privilege/grant
  misconfiguration) becomes `StorageConfigurationError`.
- every OTHER `psycopg.Error` (including `QueryCanceled`) becomes
  `AuditReaderUnavailable`, a distinct class from `StorageConfiguration
  Error`/`AuthorizationStateUnavailable`/`AuditSinkUnavailable` (see that
  class's own docstring, `errors.py`).

Six properties, each pinned by its own test:

1. an unclassified `psycopg.Error` raised inside `query` becomes
   `AuditReaderUnavailable` and the connection is still closed.
2. a REAL PostgreSQL `QueryCanceled` -- provoked deterministically by
   holding an `ACCESS EXCLUSIVE` lock on both audit tables on a separate
   connection while the `mitatedbsvc_auditreader` role's own `statement_
   timeout` is temporarily shortened, never by racing a sleep against a
   query -- hits the same `AuditReaderUnavailable` path.
3. the raised exception's own message never carries the underlying
   backend error's raw text (no DSN, no SQL, no PostgreSQL error string).
4. a real `/control/v1/audit/query` request that hits the `QueryCanceled`
   path answers 503 `SERVICE_UNAVAILABLE` with no such text in the body.
5. `psycopg.errors.InsufficientPrivilege` specifically becomes
   `StorageConfigurationError`, not `AuditReaderUnavailable`.
6. `AuditReaderUnavailable` is listed explicitly in `control_http.py`'s
   own `_CLASSIFY_ORDER` (the classification path), not left to that
   table's exhaustive-by-construction fallback.
"""
from __future__ import annotations

import asyncio
import contextlib

import httpx
import psycopg
import pytest
from psycopg import sql

from mitatedb_api import audit_query
from mitatedb_api.audit_query import PostgresAuditQueryStore
from mitatedb_api.control_http import _CLASSIFY_ORDER, create_control_app
from mitatedb_api.control_plane import (ControlPlaneLimits, ControlPlaneService,
                                        InMemoryControlBackend, bootstrap_control_credential)
from mitatedb_api.errors import AuditReaderUnavailable, StorageConfigurationError

from .control_plane_harness import control_platform  # noqa: F401 (fixture)

_APP_PEPPER = "audit-query-reader-errors-app-pepper-x"
_CONTROL_PEPPER = "audit-query-reader-errors-ctl-pepper-x"
_GENEROUS_LIMITS = ControlPlaneLimits(
    applications=10, credentials_per_application=5, control_requests_per_minute=200,
    audit_requests_per_minute=200,
)
BASE_URL = "http://mitatedb-audit-query-reader-errors.example.invalid"


def _bearer_auth(bearer: str) -> dict[str, str]:
    return {"authorization": f"Bearer {bearer}"}


class _FakeCursor:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    def __enter__(self) -> "_FakeCursor":
        return self

    def __exit__(self, *exc_info: object) -> bool:
        return False

    def execute(self, *args: object, **kwargs: object) -> None:
        raise self._exc


class _FakeConn:
    """Stands in for a `psycopg.Connection` whose cursor always raises a
    given `psycopg.Error` -- lets the mock-level tests below drive `query`
    without a real PostgreSQL server, and counts `close()` calls so a test
    can pin that the connection is closed even on the error path."""

    def __init__(self, exc: Exception) -> None:
        self._exc = exc
        self.close_count = 0

    def cursor(self) -> _FakeCursor:
        return _FakeCursor(self._exc)

    def close(self) -> None:
        self.close_count += 1


def test_query_wraps_an_unclassified_psycopg_error_as_audit_reader_unavailable_and_still_closes_the_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_conn = _FakeConn(psycopg.OperationalError("synthetic backend failure"))
    monkeypatch.setattr(audit_query.psycopg, "connect", lambda *a, **k: fake_conn)
    store = PostgresAuditQueryStore("postgresql://placeholder.invalid/db", schema="mitatedb_registry")

    with pytest.raises(AuditReaderUnavailable):
        store.query(event_classes=None, after=None, limit=5, visibility_lag_ms=0)

    assert fake_conn.close_count == 1


def test_query_wraps_insufficient_privilege_as_storage_configuration_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_conn = _FakeConn(psycopg.errors.InsufficientPrivilege("synthetic privilege defect"))
    monkeypatch.setattr(audit_query.psycopg, "connect", lambda *a, **k: fake_conn)
    store = PostgresAuditQueryStore("postgresql://placeholder.invalid/db", schema="mitatedb_registry")

    with pytest.raises(StorageConfigurationError):
        store.query(event_classes=None, after=None, limit=5, visibility_lag_ms=0)

    assert fake_conn.close_count == 1


def _set_auditreader_statement_timeout(admin_dsn: str, role: str, value: str) -> None:
    admin = psycopg.connect(admin_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute(sql.SQL("ALTER ROLE {} SET statement_timeout = {}").format(
                sql.Identifier(role), sql.Literal(value)))
    finally:
        admin.close()


def _read_auditreader_statement_timeout(admin_dsn: str, role: str) -> str:
    """Reads the role's own PRE-existing `statement_timeout` straight from
    `pg_roles.rolconfig` (the same catalog `ALTER ROLE ... SET` writes to)
    -- never a hardcoded literal -- so the scenario below can restore
    EXACTLY the value that was in place before it shortened the timeout."""
    admin = psycopg.connect(admin_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute("SELECT rolconfig FROM pg_catalog.pg_roles WHERE rolname = %s", (role,))
            row = cur.fetchone()
    finally:
        admin.close()
    rolconfig = row[0] if row else None
    if rolconfig:
        for entry in rolconfig:
            if entry.startswith("statement_timeout="):
                return entry.split("=", 1)[1]
    raise AssertionError(f"role {role!r} has no statement_timeout set in pg_roles.rolconfig")


@contextlib.contextmanager
def _query_canceled_scenario(control_platform, *, timeout_ms: int = 200):
    """Deterministically provokes a `QueryCanceled` on the auditreader role:
    holds an `ACCESS EXCLUSIVE` lock on both audit tables on a SEPARATE
    connection for the whole `with` block, while the role's own `statement_
    timeout` (migration `0013_role_statement_timeouts.sql`'s own mechanism)
    is shortened to `timeout_ms`. Any `query` issued inside the block
    blocks on the lock until its own (now much shorter) statement_timeout
    cancels it -- the outcome never depends on how long anything sleeps,
    only on the lock still being held. The shortening ALTER and the lock
    connection both sit inside the outer `try`, so a failure anywhere
    after the shortening (including `psycopg.connect` itself) still runs
    the `finally` that restores the role's own pre-existing statement_
    timeout (read via `pg_roles.rolconfig`, never a hardcoded literal)."""
    role = f"{control_platform.prefix}svc_auditreader"
    original_timeout = _read_auditreader_statement_timeout(control_platform.admin_dsn, role)
    lock_conn = None
    try:
        _set_auditreader_statement_timeout(control_platform.admin_dsn, role, f"{timeout_ms}ms")
        lock_conn = psycopg.connect(control_platform.provision_dsn)
        with lock_conn.cursor() as cur:
            cur.execute(sql.SQL("LOCK TABLE {} IN ACCESS EXCLUSIVE MODE").format(
                sql.Identifier(control_platform.registry_schema, "control_audit")))
            cur.execute(sql.SQL("LOCK TABLE {} IN ACCESS EXCLUSIVE MODE").format(
                sql.Identifier(control_platform.registry_schema, "application_audit")))
        try:
            yield
        finally:
            lock_conn.rollback()
    finally:
        if lock_conn is not None:
            lock_conn.close()
        _set_auditreader_statement_timeout(control_platform.admin_dsn, role, original_timeout)


def test_query_canceled_under_a_held_lock_becomes_audit_reader_unavailable(control_platform) -> None:
    store = PostgresAuditQueryStore(control_platform.auditreader_dsn, schema=control_platform.registry_schema)

    with _query_canceled_scenario(control_platform):
        with pytest.raises(AuditReaderUnavailable) as excinfo:
            store.query(event_classes=None, after=None, limit=5, visibility_lag_ms=0)

    assert "audit reader backend unavailable" in str(excinfo.value)


def test_reader_error_message_never_carries_the_raw_backend_text(monkeypatch: pytest.MonkeyPatch) -> None:
    marker = ("dbname=mitatedb_platform user=mitatedbsvc_auditreader password=not-a-real-secret "
              "host=10.0.0.9 SELECT event_id FROM mitatedb_registry.control_audit")
    fake_conn = _FakeConn(psycopg.OperationalError(marker))
    monkeypatch.setattr(audit_query.psycopg, "connect", lambda *a, **k: fake_conn)
    store = PostgresAuditQueryStore("postgresql://placeholder.invalid/db", schema="mitatedb_registry")

    with pytest.raises(AuditReaderUnavailable) as excinfo:
        store.query(event_classes=None, after=None, limit=5, visibility_lag_ms=0)

    assert marker not in str(excinfo.value)


async def _post_audit_query(app, bearer: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        return await client.post("/control/v1/audit/query", headers=_bearer_auth(bearer), json={"limit": 5})


def test_http_audit_query_response_is_service_unavailable_without_backend_detail_leak(control_platform) -> None:
    backend = InMemoryControlBackend(app_pepper=_APP_PEPPER, control_pepper=_CONTROL_PEPPER)
    reader = PostgresAuditQueryStore(control_platform.auditreader_dsn, schema=control_platform.registry_schema)
    service = ControlPlaneService(
        backend, limits=_GENEROUS_LIMITS, audit_reader=reader, audit_visibility_lag_ms=0,
    )
    with backend.unit_of_work() as work:
        credential_id, bearer = bootstrap_control_credential(backend.control_credential_store, backend.append_audit, work=work)
    rotated = service.rotate_credential(bearer, credential_id)
    app = create_control_app(service, request_bytes_limit=1_048_576)

    with _query_canceled_scenario(control_platform):
        response = asyncio.run(_post_audit_query(app, rotated["secret"]))

    assert response.status_code == 503
    body = response.json()
    assert body["code"] == "SERVICE_UNAVAILABLE"
    text = response.text
    dsn_fragment = control_platform.auditreader_dsn
    role_fragment = f"{control_platform.prefix}svc_auditreader"
    sql_fragment = "SELECT"
    pg_error_fragment = "canceling statement"
    assert dsn_fragment not in text
    assert role_fragment not in text
    assert sql_fragment not in text
    assert pg_error_fragment not in text


def test_audit_reader_unavailable_is_explicitly_classified_not_left_to_the_exhaustive_fallback() -> None:
    """`control_http.py::_classify` falls through an EMPTY match to a
    hardcoded `"SERVICE_UNAVAILABLE"` default -- so an entry MISSING from
    `_CLASSIFY_ORDER` would still answer the same HTTP code via that
    fallback, and a purely behavioral/HTTP-level test could not tell the
    two apart. This test instead pins the table's own CONTENT (the same
    discipline `http.py::_CLASSIFY_ORDER` already applies for `AuditSink
    Unavailable`, by its own comment: "so that fallback's own 'pragma: no
    cover' comment stays true")."""
    assert (AuditReaderUnavailable, "SERVICE_UNAVAILABLE") in _CLASSIFY_ORDER
