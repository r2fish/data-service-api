"""Port-level tests for `ConformanceAdapter.wire_entry` and `WireEntry`
(port v1.21, `docs/design/CONFORMANCE_ADAPTER_V1.md` section 31).

`wire_entry(application_id)` gives a client that holds only the contract a
way onto a surface's wire: the declared data base URL, a send function that
carries one request exactly as given over the plug's own transport, and the
bearer secret of one runtime and one developer credential. These tests pin
the port, not a condition: they run over the registered plugs whose
`transport_kind` is not `"in_process"` (the two `asgi` and the two `socket`
plugs) and, separately, over the in-process plugs, which have no wire.

The selection is made once, at module import, from the built registry
(`registered_adapters()`), and the number of wire plugs is asserted there
(`_WIRE_ADAPTER_NAMES`). Every test except the one over `WireEntry`'s own
field table takes the session-scoped `adapter` fixture through an indirect
`pytest.mark.parametrize("adapter", ...)` and asserts, first, that its own `xdist_group` marker names that same adapter
(`conftest.py`'s `pytest_collection_modifyitems` derives the group from the
`adapter` parameter): a test that did not take `adapter` that way would fall
into the shared `registry-guards` group, and the real surface it starts
would then be scheduled with every whole-registry guard of the suite.

What each test observes is measured over real plugs. "Carries only" is
observed at the transport hand-over point -- `httpx.ASGITransport.
handle_async_request` and `httpx.AsyncHTTPTransport.handle_async_request`,
wrapped by a recording spy -- so the assertion compares the `httpx.Request`
that reaches the transport with the values given to `send`. What happens
after that point (a socket plug's nginx and its upstream) is not observed.

Synthetic values only: the secrets are issued by the plug for a throwaway
Application; no test writes one into a message.
"""
from __future__ import annotations

import dataclasses
import json
import socket

import httpx
import pytest

from adapter import WireEntry, fresh_identifier, load_contract
from conftest import registered_adapters

_WIRE_ADAPTER_NAMES: tuple[str, ...] = tuple(
    name for name, obj in registered_adapters().items() if getattr(obj, "transport_kind", None) != "in_process"
)
assert len(_WIRE_ADAPTER_NAMES) == 4, (
    f"expected exactly four registered adapters whose transport_kind is not 'in_process' "
    f"(the two asgi and the two socket plugs), found {len(_WIRE_ADAPTER_NAMES)}: {_WIRE_ADAPTER_NAMES!r}"
)

_IN_PROCESS_ADAPTER_NAMES: tuple[str, ...] = tuple(
    name for name, obj in registered_adapters().items() if getattr(obj, "transport_kind", None) == "in_process"
)
assert len(_IN_PROCESS_ADAPTER_NAMES) == 2, (
    f"expected exactly two registered adapters whose transport_kind is 'in_process', "
    f"found {len(_IN_PROCESS_ADAPTER_NAMES)}: {_IN_PROCESS_ADAPTER_NAMES!r}"
)

_SOCKET_ADAPTER_NAMES: tuple[str, ...] = tuple(
    name for name, obj in registered_adapters().items() if getattr(obj, "transport_kind", None) == "socket"
)
assert len(_SOCKET_ADAPTER_NAMES) == 2, (
    f"expected exactly two registered adapters whose transport_kind is 'socket', "
    f"found {len(_SOCKET_ADAPTER_NAMES)}: {_SOCKET_ADAPTER_NAMES!r}"
)

_WIRE = pytest.mark.parametrize("adapter", _WIRE_ADAPTER_NAMES, indirect=True)
_SOCKET = pytest.mark.parametrize("adapter", _SOCKET_ADAPTER_NAMES, indirect=True)
_IN_PROCESS = pytest.mark.parametrize("adapter", _IN_PROCESS_ADAPTER_NAMES, indirect=True)

_CONTRACT = load_contract()
_BASE_PATH: str = _CONTRACT["versioning"]["base_path"]
_CAPABILITIES_PATH: str = _CONTRACT["endpoints"]["capabilities"]["path"]


def _assert_own_group(request: pytest.FixtureRequest) -> None:
    """The item's own `xdist_group` marker names the adapter this item was
    parametrized with (see this module's docstring)."""
    callspec = getattr(request.node, "callspec", None)
    expected = callspec.params.get("adapter") if callspec is not None else None
    assert expected is not None, f"{request.node.nodeid}: not parametrized through the `adapter` fixture"
    marker = request.node.get_closest_marker("xdist_group")
    assert marker is not None, f"{request.node.nodeid}: carries no xdist_group marker"
    assert marker.kwargs.get("name") == expected, (
        f"{request.node.nodeid}: xdist_group is {marker.kwargs.get('name')!r}, expected {expected!r}"
    )


def _url(entry: WireEntry, path: str) -> str:
    """The URL of an endpoint path: the declared data base URL without its
    own base path, then `path` (the contract states endpoint paths with the
    base path included)."""
    assert entry.base_url.endswith(_BASE_PATH), f"declared base URL {entry.base_url!r} does not end with {_BASE_PATH!r}"
    return entry.base_url.removesuffix(_BASE_PATH) + path


def _bearer(secret: str) -> tuple[tuple[str, str], ...]:
    return (("Authorization", "Bearer " + secret),)


@pytest.fixture(scope="module")
def wire(adapter):
    """One isolated surface and one wire entry per wire plug, shared by the
    tests of this module (`isolated_application_surface()` is where the port
    says the entry is taken, after `provision_application`)."""
    with adapter.isolated_application_surface() as iso:
        application_id = fresh_identifier("wireentry")
        iso.provision_application(application_id)
        yield iso, iso.wire_entry(application_id)


@_WIRE
def test_wire_entry_declares_the_data_base_url_and_a_runtime_request_succeeds(
    adapter, wire, request: pytest.FixtureRequest
) -> None:
    """The entry's `base_url` is the `surfaces.data.base_url` this surface's
    own capability document declares, and `send` carries a `GET` for the
    capability document, authenticated with `runtime_secret`, to a success
    response that is a JSON document."""
    _assert_own_group(request)
    iso, entry = wire
    declared = iso.capability_document()["surfaces"]["data"]["base_url"]
    assert entry.base_url == declared
    status, headers, body = entry.send("GET", _url(entry, _CAPABILITIES_PATH), _bearer(entry.runtime_secret), None)
    assert status == 200, f"{adapter.name}: GET {_CAPABILITIES_PATH} answered {status}"
    assert body, f"{adapter.name}: GET {_CAPABILITIES_PATH} answered an empty body"
    assert any(name.lower() == "content-type" for name, _ in headers), f"{adapter.name}: no content-type header returned"


@_WIRE
def test_wire_entry_secrets_are_the_runtime_and_the_developer_credential(
    adapter, wire, request: pytest.FixtureRequest
) -> None:
    """Each secret authenticates as the role it is named for: the capability
    document `send` reads with it declares that role (`role`)."""
    _assert_own_group(request)
    _iso, entry = wire
    observed = {}
    for named, secret in (("runtime", entry.runtime_secret), ("developer", entry.developer_secret)):
        status, _headers, body = entry.send("GET", _url(entry, _CAPABILITIES_PATH), _bearer(secret), None)
        assert status == 200, f"{adapter.name}: the {named} secret was answered {status}"
        observed[named] = json.loads(body).get("role")
    assert observed == {"runtime": "runtime", "developer": "developer"}, f"{adapter.name}: roles read back {observed!r}"


class _RecordingSpy:
    """Wraps one transport class's `handle_async_request` and records every
    `httpx.Request` that reaches it (headers as raw pairs, body as bytes)."""

    def __init__(self, transport_class: type, monkeypatch: pytest.MonkeyPatch) -> None:
        self.requests: list[httpx.Request] = []
        original = transport_class.handle_async_request
        recorded = self.requests

        async def handle_async_request(transport, request):
            recorded.append(request)
            return await original(transport, request)

        monkeypatch.setattr(transport_class, "handle_async_request", handle_async_request)


def _spies(monkeypatch: pytest.MonkeyPatch) -> list[_RecordingSpy]:
    return [_RecordingSpy(httpx.ASGITransport, monkeypatch), _RecordingSpy(httpx.AsyncHTTPTransport, monkeypatch)]


def _all_requests(spies: list[_RecordingSpy]) -> list[httpx.Request]:
    return [request for spy in spies for request in spy.requests]


def _unframed(request: httpx.Request) -> list[tuple[str, str]]:
    return [
        (name.decode("latin-1"), value.decode("latin-1"))
        for name, value in request.headers.raw
        if name.lower() not in (b"host", b"content-length")
    ]


@_WIRE
def test_send_hands_the_transport_exactly_the_request_it_was_given(
    adapter, wire, monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest
) -> None:
    """At the transport hand-over point the `httpx.Request` carries the
    method, the URL (character for character), the header pairs (order and
    spelling, apart from `Host` and `Content-Length`) and the body given to
    `send`. The URL's host is `localhost` -- not the declared one -- so a
    plug that rewrote the URL toward its own surface's address would show."""
    _assert_own_group(request)
    _iso, entry = wire
    spies = _spies(monkeypatch)
    declared = httpx.URL(entry.base_url)
    url = str(declared.copy_with(host="localhost", path=_CAPABILITIES_PATH, query=b"first=1&second=%2F"))
    headers = (("X-Probe-One", "a"), ("x-probe-two", "B"), ("X-Probe-One", "c"))
    body = b'{"carried": "as given"}'
    entry.send("POST", url, headers, body)
    recorded = _all_requests(spies)
    assert len(recorded) == 1, f"{adapter.name}: {len(recorded)} requests reached a transport, expected 1"
    reached = recorded[0]
    assert reached.method == "POST"
    assert str(reached.url) == url
    assert _unframed(reached) == list(headers)
    assert reached.content == body


@_WIRE
def test_send_does_not_follow_a_redirect(
    adapter, wire, monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest
) -> None:
    """A request for the capability path with a trailing slash is answered
    with a redirect on all four plugs (measured: 307, `Location` the path
    without the slash). `send` returns that 3xx as it is, and exactly one
    request reaches a transport."""
    _assert_own_group(request)
    _iso, entry = wire
    spies = _spies(monkeypatch)
    status, headers, _body = entry.send("GET", _url(entry, _CAPABILITIES_PATH + "/"), (), None)
    assert 300 <= status < 400, f"{adapter.name}: expected a redirect status, got {status}"
    assert any(name.lower() == "location" for name, _ in headers), f"{adapter.name}: redirect carries no Location header"
    assert len(_all_requests(spies)) == 1, f"{adapter.name}: a redirect was followed"


@_WIRE
def test_secrets_never_appear_in_repr_or_in_an_assert_failure_message(
    adapter, wire, request: pytest.FixtureRequest
) -> None:
    """`repr(entry)` and the failure text an `assert` on an entry produces
    show neither secret. Observed on the plug's own entry and on an entry
    built here from sentinel secrets (a plug's real secret could not prove
    absence of a value the test cannot name)."""
    _assert_own_group(request)
    _iso, entry = wire
    sentinels = ("sentinel-runtime-secret-0001", "sentinel-developer-secret-0002")
    synthetic = WireEntry(
        base_url="https://db.example.invalid/v1",
        send=entry.send,
        runtime_secret=sentinels[0],
        developer_secret=sentinels[1],
    )
    for candidate, secrets_in_it in ((entry, (entry.runtime_secret, entry.developer_secret)), (synthetic, sentinels)):
        empty = [index for index, secret in enumerate(secrets_in_it) if not secret]
        assert not empty, f"{adapter.name}: secret(s) number {empty} are empty, so their absence cannot be shown"
        shown = repr(candidate)
        with pytest.raises(AssertionError) as failure:
            assert candidate is None
        leaked_in_repr = [index for index, secret in enumerate(secrets_in_it) if secret in shown]
        leaked_in_failure = [index for index, secret in enumerate(secrets_in_it) if secret in str(failure.value)]
        assert not leaked_in_repr, f"{adapter.name}: secret(s) number {leaked_in_repr} appear in repr(entry)"
        assert not leaked_in_failure, f"{adapter.name}: secret(s) number {leaked_in_failure} appear in an assert failure message"


def test_wire_entry_secret_fields_are_excluded_from_repr_and_comparison() -> None:
    """The two secret fields of `WireEntry` are declared with
    `repr=False` and `compare=False`: neither `repr(entry)` nor the
    explanation pytest gives for a comparison between entries is built from
    a secret field. Observed on the dataclass's own field table, because the
    wording of a comparison's explanation depends on pytest's verbosity."""
    by_name = {f.name: f for f in dataclasses.fields(WireEntry)}
    assert {"runtime_secret", "developer_secret"} <= set(by_name)
    for name in ("runtime_secret", "developer_secret"):
        assert by_name[name].repr is False, f"{name}: the field is shown in repr"
        assert by_name[name].compare is False, f"{name}: the field takes part in comparison"
    others = [f.name for f in dataclasses.fields(WireEntry) if f.name not in ("runtime_secret", "developer_secret")]
    assert others == ["base_url", "send"], f"unexpected non-secret fields {others!r}"


@_WIRE
def test_send_refuses_a_method_or_url_that_is_not_in_the_http_librarys_normal_form(
    adapter, wire, monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest
) -> None:
    """A lower-case method, a host with upper-case letters and a path with
    dot segments are each written differently by the HTTP library than they
    were given, and a fragment or a userinfo part never reaches the request
    line at all. `send` raises `ValueError` for each and nothing reaches a
    transport -- a request is carried as given or refused, never carried in
    a rewritten form."""
    _assert_own_group(request)
    _iso, entry = wire
    spies = _spies(monkeypatch)
    canonical = _url(entry, _CAPABILITIES_PATH)
    declared = httpx.URL(entry.base_url)
    cases = (
        ("get", canonical),
        ("GET", canonical.replace(declared.host, "LocalHost", 1)),
        ("GET", _url(entry, _BASE_PATH + "/a/../b")),
        ("GET", canonical + "#fragment"),
        ("GET", canonical.replace("://", "://user@", 1)),
    )
    for method, url in cases:
        with pytest.raises(ValueError):
            entry.send(method, url, (), None)
    assert _all_requests(spies) == [], f"{adapter.name}: a refused request reached a transport"


@_SOCKET
def test_send_raises_on_a_refused_connection(adapter, wire, request: pytest.FixtureRequest) -> None:
    """A URL on a loopback port nobody listens on (a port that was bound and
    closed) makes `send` raise a transport error; it returns no status."""
    _assert_own_group(request)
    _iso, entry = wire
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        closed_port = probe.getsockname()[1]
    url = f"http://127.0.0.1:{closed_port}{_CAPABILITIES_PATH}"
    with pytest.raises(httpx.TransportError):
        entry.send("GET", url, (), None)


@_IN_PROCESS
def test_in_process_plugs_have_no_wire_and_raise_assertion_error(
    adapter, request: pytest.FixtureRequest
) -> None:
    """A plug whose `transport_kind` is `in_process` raises `AssertionError`
    naming `in_process` from `wire_entry`, on an isolated surface after
    `provision_application`; it returns no send function."""
    _assert_own_group(request)
    assert adapter.transport_kind == "in_process"
    with adapter.isolated_application_surface() as iso:
        application_id = fresh_identifier("wireentry")
        iso.provision_application(application_id)
        with pytest.raises(AssertionError) as raised:
            iso.wire_entry(application_id)
    assert "in_process" in str(raised.value), f"{adapter.name}: the AssertionError does not name in_process"


@pytest.mark.parametrize("adapter", _WIRE_ADAPTER_NAMES, indirect=True)
def test_wire_entry_items_carry_their_own_xdist_group(adapter, request: pytest.FixtureRequest) -> None:
    """Every item of this module is grouped under its own adapter's name
    (`_assert_own_group`), checked on its own here so a change to how the
    items are parametrized turns this test red even if no other test of the
    module reads the marker."""
    _assert_own_group(request)
    assert adapter.transport_kind != "in_process"
