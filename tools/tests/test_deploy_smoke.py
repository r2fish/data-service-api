"""tools/tests/test_deploy_smoke.py -- `tools/deploy_smoke.py` follows no
redirect in answer to a request that carries a credential (contract
`versioning.url_composition`).

Deliberately NOT under `conformance-tests/` and not discoverable by the root
suite (same convention as the other files in this directory). Run directly:
    ./.venv/bin/python -m pytest tools/tests/test_deploy_smoke.py -q

Two loopback HTTP servers on ephemeral ports: the first answers every request
with a 302 whose `Location` names the second; the second records what it is
sent. Synthetic values only.
"""
from __future__ import annotations

import http.server
import importlib.util
import sys
import threading
from pathlib import Path

import pytest

_MODULE_PATH = Path(__file__).resolve().parents[1] / "deploy_smoke.py"
_spec = importlib.util.spec_from_file_location("deploy_smoke", _MODULE_PATH)
ds = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("deploy_smoke", ds)
_spec.loader.exec_module(ds)  # type: ignore[union-attr]

SENTINEL_KEY = "sentinel-api-key-not-a-real-credential"


class _Recorder(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args) -> None:  # silence
        return

    def _record(self) -> None:
        self.server.received.append((self.command, self.path, self.headers.get("Authorization")))  # type: ignore[attr-defined]

    def do_GET(self) -> None:  # noqa: N802
        self._record()
        redirect_to = getattr(self.server, "redirect_to", None)
        if redirect_to is not None:
            self.send_response(302)
            self.send_header("Location", redirect_to)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        body = b'{"contract_version": "0.0.0"}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _serve(redirect_to: str | None):
    server = http.server.HTTPServer(("127.0.0.1", 0), _Recorder)
    server.received = []  # type: ignore[attr-defined]
    server.redirect_to = redirect_to  # type: ignore[attr-defined]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


@pytest.fixture()
def two_servers():
    second = _serve(None)
    second_url = f"http://127.0.0.1:{second.server_address[1]}/elsewhere"
    first = _serve(second_url)
    try:
        yield first, second, second_url
    finally:
        for server in (first, second):
            server.shutdown()
            server.server_close()


def test_request_follows_no_redirect_and_sends_no_credential_to_the_target(two_servers) -> None:
    first, second, _second_url = two_servers
    url = f"http://127.0.0.1:{first.server_address[1]}/v1/capabilities"
    status, parsed = ds._request("GET", url, api_key=SENTINEL_KEY)
    # the observation exists: the first server saw the request and its bearer
    assert first.received == [("GET", "/v1/capabilities", f"Bearer {SENTINEL_KEY}")], first.received
    assert 300 <= status < 400, status
    assert parsed is None
    assert second.received == [], f"the redirect target received a request: {second.received!r}"


def test_a_redirect_is_a_stage_failure_that_names_neither_the_key_nor_the_location(two_servers) -> None:
    first, second, second_url = two_servers
    base = f"http://127.0.0.1:{first.server_address[1]}"
    with pytest.raises(ds.SmokeStageError) as caught:
        ds._stage_capabilities(base, SENTINEL_KEY)
    message = str(caught.value)
    assert first.received, "the first server saw no request"
    assert "302" in message, message
    assert SENTINEL_KEY not in message and second_url not in message, message
    assert second.received == []


def test_a_connection_failure_message_carries_no_key() -> None:
    probe = http.server.HTTPServer(("127.0.0.1", 0), _Recorder)
    port = probe.server_address[1]
    probe.server_close()  # nothing listens on this port any more
    with pytest.raises(ds.SmokeStageError) as caught:
        ds._request("GET", f"http://127.0.0.1:{port}/v1/capabilities", api_key=SENTINEL_KEY)
    message = str(caught.value)
    assert "could not connect" in message, message
    assert SENTINEL_KEY not in message, message
