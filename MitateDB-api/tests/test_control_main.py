"""`control_main.build_control_app` / `control_composition.build_control_
service` (WP-5 flip, design v1.2 R-6/R-7/R-9) -- the literal
`uvicorn mitatedb_api.control_main:app` entry point, tested directly.

`control_composition.build_control_service` itself is ALSO reachable as
`mitatedb_api.main.build_control_service` (a re-export kept for
`test_main.py`'s own pre-existing call sites, WP-4) -- this file exercises
it via the NEW module directly, and additionally proves the ASGI-mounting
half (`control_http.create_control_app`) that `test_main.py` does not
touch at all.

`mitatedb_api.control_main` ends with a module-level `app = build_control_
app()`, which reads `os.environ` immediately on import (design v1.2 §8
m-10, mirroring `mitatedb_api.main`'s own identical `app = build_app()`
pattern) -- this file's own `control_main_module` fixture imports it
EXACTLY ONCE, with `os.environ` populated from a real, throwaway-
provisioned platform (`monkeypatch`, cleared automatically at teardown),
mirroring `test_main.py`'s own `main_module` fixture convention for the
identical reason. Every test then calls `control_main_module.build_
control_app` directly with its OWN explicit `env` dict -- never relying on
the cached module-level `app` object itself, which stays bound to
whichever env happened to be active on the very first import.
"""
from __future__ import annotations

import asyncio
import sys

import httpx
import psycopg
import pytest
from psycopg import sql

from .control_plane_harness import control_platform  # noqa: F401 (fixture)
from mitatedb_api.control_composition import build_control_service
from mitatedb_api.control_plane import bootstrap_control_credential
from mitatedb_api.credential_wire import split_bearer_locator

BASE_URL = "http://mitatedb-control-main-test.invalid"

_APP_PEPPER = "control-main-test-app-pepper-00000"
_CONTROL_PEPPER = "control-main-test-ctl-pepper-00000"


def _env(control_platform, **overrides) -> dict[str, str]:
    # Q4 phase (design D-2, work order §4 WP-2 変更対象 D): `MITATEDB_
    # DATA_BASE_URL`/`MITATEDB_CONTROL_BASE_URL` are REMOVED env vars (F-2)
    # -- `surfaces` now comes from `<registry>.platform_declarations`,
    # already seeded by `control_plane_harness.bootstrap_control_platform`
    # (both `data`/`control`, matching this composition root's own
    # unconditional requirement for a control surface).
    env = {
        "MITATEDB_CREDENTIAL_PEPPER": _APP_PEPPER,
        "MITATEDB_CONTROL_CREDENTIAL_PEPPER": _CONTROL_PEPPER,
        "MITATEDB_CONTROLPLANE_DSN": control_platform.controlplane_dsn,
        "MITATEDB_PLATFORM_SCHEMA": control_platform.registry_schema,
    }
    env.update(overrides)
    return env


@pytest.fixture
def control_main_module(control_platform, monkeypatch):
    """Imports `mitatedb_api.control_main` exactly once (cached in
    `sys.modules` for the rest of the process either way) with
    `os.environ` populated from a real, throwaway-provisioned platform,
    then returns the module object so tests can call its own
    `build_control_app` function directly with their own `env` dicts."""
    if "mitatedb_api.control_main" not in sys.modules:
        for key, value in _env(control_platform).items():
            monkeypatch.setenv(key, value)
        import mitatedb_api.control_main  # noqa: F401
    import mitatedb_api.control_main as control_main_module
    return control_main_module


@pytest.fixture(autouse=True)
def _clean_control_state(control_platform):
    import psycopg
    yield
    conn = psycopg.connect(control_platform.provision_dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            schema = control_platform.registry_schema
            cur.execute(f"DELETE FROM {schema}.control_credentials")
            cur.execute(f"DELETE FROM {schema}.control_audit")
            cur.execute(f"DELETE FROM {schema}.credentials")
            cur.execute(f"DELETE FROM {schema}.applications")
    finally:
        conn.close()


def _run(coro):
    return asyncio.run(coro)


async def _aget(app, path, *, headers=None) -> httpx.Response:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE_URL) as client:
        return await client.get(path, headers=headers or {})


async def _apost(app, path, *, headers=None, json_body=None) -> httpx.Response:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE_URL) as client:
        if json_body is not None:
            return await client.post(path, json=json_body, headers=headers or {})
        return await client.post(path, headers=headers or {})


def test_build_control_app_missing_required_env_fails_loudly(control_main_module, control_platform) -> None:
    env = _env(control_platform)
    del env["MITATEDB_CONTROLPLANE_DSN"]
    with pytest.raises(RuntimeError, match="MITATEDB_CONTROLPLANE_DSN"):
        control_main_module.build_control_app(env)


def test_build_control_app_rejects_identical_peppers(control_main_module, control_platform) -> None:
    # `assert_pepper_separation` raises `ValueError` directly (a
    # configuration error, not a `RuntimeError` "missing env" failure) --
    # matches `test_main.py::test_control_service_factory_rejects_
    # identical_peppers`'s own identical expectation for the SAME
    # underlying `control_composition.build_control_service` call.
    env = _env(control_platform, MITATEDB_CONTROL_CREDENTIAL_PEPPER=_APP_PEPPER)
    with pytest.raises(ValueError):
        control_main_module.build_control_app(env)


@pytest.mark.parametrize(
    "removed_var,value",
    [
        ("MITATEDB_AUDIT_STATEMENT_TIMEOUT_MS", ""),
        ("MITATEDB_AUDIT_STATEMENT_TIMEOUT_MS", "5000"),
        ("MITATEDB_AUDIT_IDLE_TIMEOUT_MS", ""),
        ("MITATEDB_AUDIT_IDLE_TIMEOUT_MS", "5000"),
        ("MITATEDB_DATA_BASE_URL", ""),
        ("MITATEDB_DATA_BASE_URL", "https://removed-env.example.invalid/v1"),
        ("MITATEDB_CONTROL_BASE_URL", ""),
        ("MITATEDB_CONTROL_BASE_URL", "https://removed-env.example.invalid/control/v1"),
    ],
)
def test_build_control_service_rejects_every_removed_env_var_through_the_real_composition_root(
    control_platform, removed_var: str, value: str,
) -> None:
    """{scratchpad}/wp12-audit-gaps.md G5 (WP-2 completion condition
    23(a)): the control-plane half of the same gap `test_main.py::test_
    build_app_rejects_every_removed_env_var_through_the_real_composition_
    root` closes for the data plane -- `reject_removed_timeout_env`/
    `reject_removed_surface_env` were exercised ONLY as bare function
    calls in `test_platform_declarations.py`, never through `build_
    control_service` itself (`control_composition.py:104-105`). 8 cases:
    {the 2 removed timeout vars, the 2 removed surface vars} x {empty
    string, a real-looking value}."""
    env = _env(control_platform)
    env[removed_var] = value
    with pytest.raises(RuntimeError, match="no longer read"):
        build_control_service(env)


def test_build_control_app_mounts_a_real_working_control_v1_surface(control_main_module, control_platform) -> None:
    """End-to-end proof that `control_main.build_control_app` (the literal
    uvicorn entry point) produces a genuinely working `/control/v1`
    surface -- not merely that `build_control_service` alone works
    (`test_main.py`'s own pre-existing coverage), and not merely that
    `control_http.create_control_app` alone works against a hand-built
    service (`test_control_http_unmounted.py`'s own WP-4 coverage). This
    is the one test exercising the actual composition WP-5 adds."""
    app = control_main_module.build_control_app(_env(control_platform))

    # Bootstrap out-of-band (the ceremony core directly, mirroring what
    # `python -m mitatedb_api.ops bootstrap` does against the SAME
    # PostgreSQL platform) -- this app has no bootstrap endpoint of its
    # own by contract.
    service = build_control_service(_env(control_platform))
    backend = service._backend  # test-only reach-in, mirrors test_main.py's own convention
    with backend.unit_of_work() as work:
        credential_id, secret = bootstrap_control_credential(backend.control_credential_store, backend.append_audit, work=work)

    rotate_resp = _run(_apost(app, f"/control/v1/credentials/{credential_id}/rotate",
                              headers={"authorization": f"Bearer {secret}"}))
    assert rotate_resp.status_code == 200, rotate_resp.text
    # Phase 6 WP-3 (design D-1(d)): the `/control/v1/.../rotate` response's
    # own `secret` is now the complete bearer (`control_http.py::_with_
    # composed_secret`) -- used verbatim, never recomposed with `credential_id`.
    secret = rotate_resp.json()["secret"]
    auth_header = {"authorization": f"Bearer {secret}"}

    caps_resp = _run(_aget(app, "/control/v1/capabilities", headers=auth_header))
    assert caps_resp.status_code == 200, caps_resp.text
    document = caps_resp.json()
    assert document["capabilities"]["control_plane"]["status"] == "enabled"
    # R-6: `request_bytes` is declared `enforced` from the very first
    # commit that mounts anything at all (m-10) -- real enforcement, same
    # commit as the mount itself (`control_http.RequestByteBoundMiddleware`,
    # sized from THIS service's own `limits.request_bytes`, R-6/control_
    # main.py's own module docstring).
    assert document["limit_enforcement"]["request_bytes"] == "enforced"

    register_resp = _run(_apost(app, "/control/v1/applications", headers=auth_header,
                                json_body={"application_id": "controlmainapp"}))
    assert register_resp.status_code == 200, register_resp.text
    assert register_resp.json() == {"application_id": "controlmainapp", "enabled": True}

    issue_resp = _run(_apost(app, "/control/v1/credentials", headers=auth_header,
                             json_body={"application_id": "controlmainapp", "role": "runtime"}))
    assert issue_resp.status_code == 200, issue_resp.text
    assert issue_resp.json()["role"] == "runtime"


def test_build_control_app_capabilities_document_is_a_startup_snapshot_not_re_read_per_request(control_main_module, control_platform) -> None:
    """N-3 (monitor ruling 2026-09-05, delta review §4): the control-plane
    half of completion condition 27 (U-3, startup snapshot) had no test --
    only the data-plane half did (`test_main.py::test_build_app_
    capabilities_document_is_a_startup_snapshot_not_re_read_per_request`).
    `build_control_service` reads `platform_declarations` exactly ONCE and
    passes `surfaces=` into `ControlPlaneService.__init__` (`self.
    _surfaces`) -- `control_capabilities()` never re-reads the DB -- so
    this pins behavior that already exists (裁定: 設計外の機構は足さない),
    mirroring r2db-api's own sibling test in `test_surfaces_env.py`."""
    app = control_main_module.build_control_app(_env(control_platform))

    service = build_control_service(_env(control_platform))
    backend = service._backend  # test-only reach-in, mirrors this file's own convention
    with backend.unit_of_work() as work:
        credential_id, secret = bootstrap_control_credential(backend.control_credential_store, backend.append_audit, work=work)

    rotate_resp = _run(_apost(app, f"/control/v1/credentials/{credential_id}/rotate",
                              headers={"authorization": f"Bearer {secret}"}))
    assert rotate_resp.status_code == 200, rotate_resp.text
    secret = rotate_resp.json()["secret"]
    auth_header = {"authorization": f"Bearer {secret}"}

    before = _run(_aget(app, "/control/v1/capabilities", headers=auth_header))
    assert before.status_code == 200, before.text
    before_surfaces = before.json()["surfaces"]

    schema = control_platform.registry_schema
    admin = psycopg.connect(control_platform.provision_dsn, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute(
                sql.SQL("UPDATE {table} SET value = %s::jsonb WHERE key = 'surfaces'").format(
                    table=sql.Identifier(schema, "platform_declarations")),
                ['{"data": {"base_url": "https://control-snapshot-changed.example.invalid/v1"}, '
                 '"control": {"base_url": "https://control-snapshot-changed.example.invalid/control/v1"}}'],
            )
        try:
            after = _run(_aget(app, "/control/v1/capabilities", headers=auth_header))
            assert after.status_code == 200, after.text
            assert after.json()["surfaces"] == before_surfaces
        finally:
            import json
            with admin.cursor() as cur:
                cur.execute(
                    sql.SQL("UPDATE {table} SET value = %s::jsonb WHERE key = 'surfaces'").format(
                        table=sql.Identifier(schema, "platform_declarations")),
                    [json.dumps(before_surfaces)],
                )
    finally:
        admin.close()


def test_build_control_app_request_bytes_limit_matches_the_declared_one(control_main_module, control_platform) -> None:
    """R-7: "宣言値と enforce 値が同一ソースから出ることを構造で保証する" --
    a custom `MITATEDB_CONTROL_REQUEST_BYTES_LIMIT` really changes what the
    ASGI middleware enforces, not only what `control_capabilities()`
    reports."""
    env = _env(control_platform, MITATEDB_CONTROL_REQUEST_BYTES_LIMIT="256")
    app = control_main_module.build_control_app(env)

    service = build_control_service(env)
    backend = service._backend
    with backend.unit_of_work() as work:
        credential_id, secret = bootstrap_control_credential(backend.control_credential_store, backend.append_audit, work=work)
    rotate_resp = _run(_apost(app, f"/control/v1/credentials/{credential_id}/rotate",
                              headers={"authorization": f"Bearer {secret}"}))
    # Phase 6 WP-3 (design D-1(d)): the `/control/v1/.../rotate` response's
    # own `secret` is now the complete bearer (`control_http.py::_with_
    # composed_secret`) -- used verbatim, never recomposed with `credential_id`.
    secret = rotate_resp.json()["secret"]
    auth_header = {"authorization": f"Bearer {secret}"}

    caps_resp = _run(_aget(app, "/control/v1/capabilities", headers=auth_header))
    assert caps_resp.json()["limits"]["request_bytes"] == 256

    oversized = {"application_id": "a" * 1024}
    response = _run(_apost(app, "/control/v1/applications", headers=auth_header, json_body=oversized))
    assert response.status_code == 413
    assert response.json()["code"] == "LIMIT_EXCEEDED"


# ===========================================================================
# Phase 4 ledger closure WP-B3 (L4-7(i), design §11.1 未起票 -- 作業指示書
# WORK_ORDER_PHASE4_LEDGER_CLOSURE_V1.md §1 L4-7(i) が正本): the two tests
# below (`test_build_control_service_declares_audit_query_...`) exercise
# `build_control_service` directly -- the lower-level assembly helper --
# never `control_main.build_control_app` itself, the literal `uvicorn
# mitatedb_api.control_main:app` entry point. A composition-root bug that
# only breaks `build_control_app`'s OWN `MITATEDB_AUDIT_DSN` env-var read
# (e.g. a typo'd env var name at that specific call site) would go
# undetected by either existing test. Same name as r2db-api's own
# `tests/test_audit_query.py` `test_build_control_app_declares_audit_query_
# status_from_r2db_audit_dsn_env` (work order §4 WP-B3 completion condition
# 4), adapted to this peer's own `MITATEDB_AUDIT_DSN` env var and bearer-
# token format (`{credential_id}.{secret}`, mirroring this file's own
# `test_build_control_app_mounts_a_real_working_control_v1_surface`).
# ===========================================================================


def test_build_control_app_declares_audit_query_status_from_mitatedb_audit_dsn_env(control_main_module, control_platform) -> None:
    """`control_composition.build_control_service`'s own `audit_dsn = env.
    get("MITATEDB_AUDIT_DSN") or None` read (`control_composition.py:169`)
    must reach a real `GET /control/v1/capabilities` response two ways,
    built through `control_main.build_control_app` itself -- the literal
    entry-point factory, not `build_control_service` directly:
    `MITATEDB_AUDIT_DSN` unset -> `audit_query: {"status": "unavailable"}`
    (D-5 M-4's declared default), and set to this module's own real
    `auditreader` DSN -> `audit_query.status != "unavailable"` (`"enabled"`
    with a real, positive `visibility_lag_ms`)."""
    base_env = _env(control_platform)
    assert "MITATEDB_AUDIT_DSN" not in base_env

    service = build_control_service(base_env)
    backend = service._backend  # test-only reach-in, mirrors this file's own established convention
    with backend.unit_of_work() as work:
        credential_id, secret = bootstrap_control_credential(backend.control_credential_store, backend.append_audit, work=work)

    # MITATEDB_AUDIT_DSN unset entirely -- the D-5 M-4 default.
    unavailable_app = control_main_module.build_control_app(dict(base_env))
    rotate_resp = _run(_apost(unavailable_app, f"/control/v1/credentials/{credential_id}/rotate",
                              headers={"authorization": f"Bearer {secret}"}))
    assert rotate_resp.status_code == 200, rotate_resp.text
    # Phase 6 WP-3 (design D-1(d)): the `/control/v1/.../rotate` response's
    # own `secret` is now the complete bearer (`control_http.py::_with_
    # composed_secret`) -- used verbatim, never recomposed with `credential_id`.
    secret = rotate_resp.json()["secret"]
    auth_header = {"authorization": f"Bearer {secret}"}

    caps_resp = _run(_aget(unavailable_app, "/control/v1/capabilities", headers=auth_header))
    assert caps_resp.status_code == 200, caps_resp.text
    assert caps_resp.json()["capabilities"]["audit_query"] == {"status": "unavailable"}

    # MITATEDB_AUDIT_DSN set to the real mitatedbsvc_auditreader DSN this
    # module's own `control_platform` fixture provisions -- same rotated
    # credential (same underlying control-plane database), a fresh app.
    enabled_env = dict(base_env)
    enabled_env["MITATEDB_AUDIT_DSN"] = control_platform.auditreader_dsn
    enabled_app = control_main_module.build_control_app(enabled_env)
    caps_resp = _run(_aget(enabled_app, "/control/v1/capabilities", headers=auth_header))
    assert caps_resp.status_code == 200, caps_resp.text
    assert caps_resp.json()["capabilities"]["audit_query"]["status"] != "unavailable"


def test_build_control_service_declares_audit_query_unavailable_without_audit_dsn(control_platform) -> None:
    """WP-3(b) review round 2 instruction 3 (supervisor-forwarded fix): no
    peer-local test previously pinned `build_control_service`'s own
    `MITATEDB_AUDIT_DSN`-absent path -- `_env()` never sets it, so the
    resulting service must declare `audit_query: {"status":
    "unavailable"}` (D-5 M-4), never `enabled`."""
    env = _env(control_platform)
    assert "MITATEDB_AUDIT_DSN" not in env
    service = build_control_service(env)
    backend = service._backend  # test-only reach-in, mirrors this file's own existing convention
    with backend.unit_of_work() as work:
        credential_id, bearer = bootstrap_control_credential(backend.control_credential_store, backend.append_audit, work=work)
    secret = bearer
    rotated = service.rotate_credential(secret, credential_id)
    rotated_secret = rotated["secret"]
    document = service.control_capabilities(rotated_secret)
    assert document["capabilities"]["audit_query"] == {"status": "unavailable"}


def test_build_control_service_declares_audit_query_enabled_with_audit_dsn(control_platform) -> None:
    """WP-3(b) review round 2 instruction 3 (supervisor-forwarded fix):
    the twin of the test immediately above -- setting `MITATEDB_AUDIT_DSN`
    (here, the real `mitatedbsvc_auditreader` DSN migration 0005
    provisions, `control_platform.auditreader_dsn`) must flip the
    composition root's own declaration to `enabled`, with a real,
    non-zero `visibility_lag_ms` (never a bare presence check)."""
    env = _env(control_platform, MITATEDB_AUDIT_DSN=control_platform.auditreader_dsn)
    service = build_control_service(env)
    backend = service._backend
    with backend.unit_of_work() as work:
        credential_id, bearer = bootstrap_control_credential(backend.control_credential_store, backend.append_audit, work=work)
    secret = bearer
    rotated = service.rotate_credential(secret, credential_id)
    rotated_secret = rotated["secret"]
    document = service.control_capabilities(rotated_secret)
    audit_query = document["capabilities"]["audit_query"]
    assert audit_query["status"] == "enabled"
    assert isinstance(audit_query["visibility_lag_ms"], int) and audit_query["visibility_lag_ms"] > 0
    # The route itself genuinely answers, not merely the declaration --
    # confirms `build_control_service`'s own `audit_reader` wiring is a
    # real, working `PostgresAuditQueryStore`, not merely a truthy stub.
    result = service.audit_query(rotated_secret, {"limit": 1})
    assert "events" in result


def _count_control_authentication_denials(control_platform) -> int:
    """Counts only rows shaped exactly like `ControlPlaneService.
    _authenticate`'s own except-`AuthenticationError` denial
    (`event_class`/`reason_code`/`target_kind` per `control_plane.py:1256-
    1258`) with `actor_id IS NULL` folded directly into the `WHERE`
    clause -- review B-1's "never record the client-claimed id" discipline
    (`_deny_audit` is never passed an `actor_id` on this path), asserted
    here as a query-level constraint rather than a separate row fetch."""
    conn = psycopg.connect(control_platform.provision_dsn)
    try:
        with conn.cursor() as cur:
            table = sql.Identifier(control_platform.registry_schema, "control_audit").as_string(conn)
            cur.execute(
                f"SELECT count(*) FROM {table} WHERE event_class = 'authentication_denial' "
                "AND reason_code = 'AUTH_INVALID' AND target_kind = 'control_credential' "
                "AND actor_id IS NULL"
            )
            (count,) = cur.fetchone()
    finally:
        conn.close()
    return count


def test_control_http_durably_audits_a_nul_locator_as_auth_invalid_not_503(control_main_module, control_platform) -> None:
    """WP-3 差し戻し 最終ラウンド (supervisor ruling 2026-09-04, 裁定 3,
    review F4), the control-plane counterpart of `test_application_audit.
    py::test_http_service_durably_audits_a_nul_locator_as_auth_invalid_
    not_503` -- same regression, same fix, the CONTROL boundary
    (`control_main.build_control_app`/`control_http.py`) instead of the
    data-plane one: before `credential_wire.split_bearer_locator`'s own
    NUL-byte check existed, a bearer with a NUL (U+0000) byte in either
    locator half would have reached `psycopg` as a real query parameter
    deep inside `control_credential_store_postgres.
    PostgresControlCredentialStore.authenticate`, which maps a raw
    `psycopg.Error` to `AuthorizationStateUnavailable` (503) instead of
    the durably-audited `AuthenticationError` (401) every OTHER malformed
    shape already produced. `split_bearer_locator` now rejects a NUL in
    either half before any lookup, so this test fixes both halves of that
    regression over REAL HTTP + REAL PostgreSQL: (1) the response is `401
    AUTH_INVALID`, never `503`; (2) `ControlPlaneService._authenticate`'s
    own `except AuthenticationError` branch durably records the denial
    (`event_class="authentication_denial"`, `reason_code="AUTH_INVALID"`,
    `target_kind="control_credential"`) with `actor_id` left `None`
    (`_deny_audit` is never passed one on this path).

    Unlike the data-plane store, `ControlPlaneService._deny_audit` writes
    one row per call with NO coalescing layer in front of it (mirrors
    `conformance-tests/test_c15_bootstrap_reset_lifecycle.py`'s own
    established "two distinct malformed presentations -> two distinct
    durable rows" C-15 property) -- so this test asserts a delta of
    exactly +1 per NUL-bearing locator presented, immediately after each
    one, rather than a single aggregate delta across both."""
    app = control_main_module.build_control_app(_env(control_platform))
    for locator in ("crd_\x00nulid.secret", "crd_nulid.sec\x00ret"):
        before = _count_control_authentication_denials(control_platform)
        response = _run(_aget(app, "/control/v1/capabilities", headers={"authorization": f"Bearer {locator}"}))
        assert response.status_code == 401, f"NUL locator {locator!r} returned {response.status_code}, not 401: {response.text}"
        assert response.json()["code"] == "AUTH_INVALID"
        after = _count_control_authentication_denials(control_platform)
        assert after - before == 1, f"NUL locator {locator!r}: expected exactly one new durable denial row, before={before} after={after}"
