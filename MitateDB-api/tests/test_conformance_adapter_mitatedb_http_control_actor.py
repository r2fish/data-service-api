"""Unit tests for `MitateDBHttpConformanceAdapter`'s control credential
cache/repair machinery: denial classification on the public probe
(`control_credential`), the no-probe internal path
(`_ensure_control_actor`/`_privileged_control_send`), and the shared cache
between a shared surface and every `isolated_application_surface()` copy.

None of these tests build a real adapter (no PostgreSQL connection, no real
HTTP server): the adapter under test is constructed via
`object.__new__(MitateDBHttpConformanceAdapter)` and every collaborator it
would otherwise reach for (`_control_send`, the out-of-band ops CLI
wrappers, `HttpService`/`create_app`/`_build_client`) is a plain fake this
file installs directly. `sys.path` setup mirrors this directory's own
`test_conformance_adapter_mitatedb_http_audit_writer_timeouts.py`.
"""
from __future__ import annotations

import os
import sys
import types

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "conformance"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "conformance-tests"))

import pytest  # noqa: E402

import conformance_adapter_mitatedb_http as _http_module  # noqa: E402
from mitatedb_api.config import FoundationConfig  # noqa: E402

_ADAPTER_NAME = _http_module.MitateDBHttpConformanceAdapter.name


def _denial(code: str) -> "_http_module.ConformanceDenial":
    return _http_module.ConformanceDenial(code=code, adapter=_ADAPTER_NAME, native_type="FakeHttpFailure")


def _forbid(reason: str):
    def _raise(*_args, **_kwargs):
        raise AssertionError(reason)

    return _raise


def _make_adapter(*, credential_ref: str | None, secret: str | None) -> "_http_module.MitateDBHttpConformanceAdapter":
    """Builds a `MitateDBHttpConformanceAdapter` without running its real
    `__init__` (no PostgreSQL, no HTTP server) and seeds the shared-cache
    holder with the given (possibly absent) credential."""
    adapter = object.__new__(_http_module.MitateDBHttpConformanceAdapter)
    holder = _http_module._ControlCredentialHolder()  # noqa: SLF001 -- test-only reach-in, this file's own subject
    holder.ref = credential_ref
    holder.secret = secret
    adapter._control_credential_holder = holder  # noqa: SLF001
    return adapter


def test_control_credential_propagates_limit_exceeded_without_reset() -> None:
    adapter = _make_adapter(credential_ref="ctl_old", secret="secret_old")
    calls: list[dict] = []

    def fake_control_send(method, path, actor, *, json_body=None):
        calls.append({"method": method, "path": path, "ref": actor.credential_ref})
        raise _denial("LIMIT_EXCEEDED")

    adapter._control_send = fake_control_send  # noqa: SLF001
    adapter._run_reset_ops_cli = _forbid("reset ritual must not run on a LIMIT_EXCEEDED probe denial")  # noqa: SLF001
    adapter._run_ops_cli = _forbid("bootstrap ritual must not run on a LIMIT_EXCEEDED probe denial")  # noqa: SLF001
    adapter._control_credentials_has_any = _forbid("must not even check bootstrap-vs-reset")  # noqa: SLF001

    with pytest.raises(_http_module.ConformanceDenial) as excinfo:
        adapter.control_credential()

    assert excinfo.value.code == "LIMIT_EXCEEDED"
    assert calls == [{"method": "GET", "path": "/control/v1/capabilities", "ref": "ctl_old"}]
    assert adapter._control_credential_holder.ref == "ctl_old"  # noqa: SLF001 -- unchanged, no repair ran
    assert adapter._control_credential_holder.secret == "secret_old"  # noqa: SLF001


def test_control_credential_repairs_once_on_auth_invalid() -> None:
    adapter = _make_adapter(credential_ref="ctl_old", secret="secret_old")
    calls: list[str] = []

    def fake_control_send(method, path, actor, *, json_body=None):
        calls.append(path)
        if path == "/control/v1/capabilities":
            raise _denial("AUTH_INVALID")
        assert path == "/control/v1/credentials/ctl_new/rotate"
        return {"secret": "secret_final"}

    adapter._control_send = fake_control_send  # noqa: SLF001
    reset_calls: list[int] = []

    def fake_run_reset_ops_cli():
        reset_calls.append(1)
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")

    adapter._run_reset_ops_cli = fake_run_reset_ops_cli  # noqa: SLF001
    adapter._run_ops_cli = _forbid("bootstrap must not run when a control credential already exists")  # noqa: SLF001
    adapter._control_credentials_has_any = lambda: True  # noqa: SLF001
    adapter._parse_issued_stdout = lambda stdout: ("ctl_new", "secret_mid")  # noqa: SLF001

    handle = adapter.control_credential()

    assert handle == _http_module.ControlCredentialHandle(credential_ref="ctl_new", secret="secret_final")
    assert calls == ["/control/v1/capabilities", "/control/v1/credentials/ctl_new/rotate"]
    assert reset_calls == [1]
    assert adapter._control_credential_holder.ref == "ctl_new"  # noqa: SLF001
    assert adapter._control_credential_holder.secret == "secret_final"  # noqa: SLF001


def test_internal_control_call_sends_no_probe_when_cache_is_live() -> None:
    adapter = _make_adapter(credential_ref="ctl_live", secret="secret_live")
    calls: list[str] = []

    def fake_control_send(method, path, actor, *, json_body=None):
        calls.append(path)
        assert path == "/control/v1/capabilities"
        assert method == "GET"
        return {"capabilities": {"audit_query": {"status": "enabled", "visibility_lag_ms": 4000}}}

    adapter._control_send = fake_control_send  # noqa: SLF001
    adapter.control_credential = _forbid(  # noqa: SLF001
        "the internal path must never call the public probing control_credential()")
    adapter._run_reset_ops_cli = _forbid("cache is live -- no repair should run")  # noqa: SLF001
    adapter._run_ops_cli = _forbid("cache is live -- no repair should run")  # noqa: SLF001

    status = adapter._audit_query_status()  # noqa: SLF001
    assert status == "enabled"
    assert calls == ["/control/v1/capabilities"]

    lag_ms = adapter.audit_visibility_lag_ms()
    assert lag_ms == 4000
    assert calls == ["/control/v1/capabilities", "/control/v1/capabilities"]


def test_internal_control_call_resends_only_on_auth_denial() -> None:
    # Leg (a): a transient LIMIT_EXCEEDED denial on the real operation
    # itself propagates unchanged, with no resend and no reset ritual.
    limit_adapter = _make_adapter(credential_ref="ctl_x", secret="secret_x")
    limit_calls: list[str] = []

    def fake_control_send_limit(method, path, actor, *, json_body=None):
        limit_calls.append(path)
        raise _denial("LIMIT_EXCEEDED")

    limit_adapter._control_send = fake_control_send_limit  # noqa: SLF001
    limit_adapter._run_reset_ops_cli = _forbid("LIMIT_EXCEEDED must never trigger the reset ritual")  # noqa: SLF001
    limit_adapter._run_ops_cli = _forbid("LIMIT_EXCEEDED must never trigger the reset ritual")  # noqa: SLF001
    limit_adapter._control_credentials_has_any = _forbid("must not even check bootstrap-vs-reset")  # noqa: SLF001

    with pytest.raises(_http_module.ConformanceDenial) as excinfo:
        limit_adapter._privileged_control_send("GET", "/control/v1/capabilities")  # noqa: SLF001

    assert excinfo.value.code == "LIMIT_EXCEEDED"
    assert limit_calls == ["/control/v1/capabilities"]

    # Leg (b): an AUTH_INVALID denial on the real operation runs the reset
    # ritual exactly once and resends exactly once, with the NEW secret.
    auth_adapter = _make_adapter(credential_ref="ctl_x", secret="secret_x")
    auth_calls: list[tuple[str, str]] = []

    def fake_control_send_auth(method, path, actor, *, json_body=None):
        auth_calls.append((path, actor.secret))
        if path == "/control/v1/capabilities" and actor.secret == "secret_x":
            raise _denial("AUTH_INVALID")
        if path == "/control/v1/credentials/ctl_y/rotate":
            return {"secret": "secret_y_final"}
        if path == "/control/v1/capabilities" and actor.secret == "secret_y_final":
            return {"capabilities": {}}
        raise AssertionError(f"unexpected _control_send call: {path!r} secret={actor.secret!r}")

    auth_adapter._control_send = fake_control_send_auth  # noqa: SLF001
    reset_calls: list[int] = []

    def fake_run_reset_ops_cli():
        reset_calls.append(1)
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")

    auth_adapter._run_reset_ops_cli = fake_run_reset_ops_cli  # noqa: SLF001
    auth_adapter._run_ops_cli = _forbid("bootstrap must not run when a control credential already exists")  # noqa: SLF001
    auth_adapter._control_credentials_has_any = lambda: True  # noqa: SLF001
    auth_adapter._parse_issued_stdout = lambda stdout: ("ctl_y", "secret_y_mid")  # noqa: SLF001

    result = auth_adapter._privileged_control_send("GET", "/control/v1/capabilities")  # noqa: SLF001

    assert result == {"capabilities": {}}
    assert reset_calls == [1]
    capability_calls = [call for call in auth_calls if call[0] == "/control/v1/capabilities"]
    assert len(capability_calls) == 2
    assert capability_calls[0][1] == "secret_x"
    assert capability_calls[1][1] == "secret_y_final"  # the resend used the NEW secret, never the old one


class _FakeControlClient:
    async def aclose(self) -> None:
        return None


def test_isolated_surface_repair_is_seen_by_parent(monkeypatch) -> None:
    adapter = _make_adapter(credential_ref="ctl_old", secret="secret_old")
    adapter._application_config = FoundationConfig()  # noqa: SLF001
    adapter._gate = None  # noqa: SLF001 -- unused: HttpService is faked below
    adapter._audit_router = None  # noqa: SLF001 -- unused: HttpService is faked below

    calls: list[tuple[str, str]] = []

    def fake_control_send(method, path, actor, *, json_body=None):
        calls.append((path, actor.secret))
        if path == "/control/v1/credentials/ctl_new/rotate":
            return {"secret": "secret_final"}
        if path == "/control/v1/capabilities" and actor.secret == "secret_final":
            return {}
        raise AssertionError(f"unexpected _control_send call: {path!r} secret={actor.secret!r}")

    adapter._control_send = fake_control_send  # noqa: SLF001
    reset_calls: list[int] = []

    def fake_run_reset_ops_cli():
        reset_calls.append(1)
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")

    adapter._run_reset_ops_cli = fake_run_reset_ops_cli  # noqa: SLF001
    adapter._run_ops_cli = _forbid("bootstrap must not run when a control credential already exists")  # noqa: SLF001
    adapter._control_credentials_has_any = lambda: True  # noqa: SLF001
    adapter._parse_issued_stdout = lambda stdout: ("ctl_new", "secret_mid")  # noqa: SLF001

    monkeypatch.setattr(_http_module, "HttpService", lambda *a, **k: object())
    monkeypatch.setattr(_http_module, "create_app", lambda *a, **k: object())
    monkeypatch.setattr(
        _http_module.MitateDBHttpConformanceAdapter, "_build_client",
        lambda self, app, base_url: _FakeControlClient(),
    )

    with adapter.isolated_application_surface() as iso:
        repaired = iso._repair_control_actor()  # noqa: SLF001 -- simulates a real auth-denial repair happening on the copy
        assert repaired == _http_module.ControlCredentialHandle(credential_ref="ctl_new", secret="secret_final")
        # The parent's own holder already sees the copy's repair -- proves
        # the two sides share ONE cache object, not two value-copies
        # (the holder shared with isolated copies).
        assert adapter._control_credential_holder.ref == "ctl_new"  # noqa: SLF001
        assert adapter._control_credential_holder.secret == "secret_final"  # noqa: SLF001

    assert reset_calls == [1]

    handle = adapter.control_credential()

    assert handle == _http_module.ControlCredentialHandle(credential_ref="ctl_new", secret="secret_final")
    # The parent's own later probe never re-triggers the reset ritual: the
    # copy's repair is still the one and only ritual run.
    assert reset_calls == [1]
