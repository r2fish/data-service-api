#!/usr/bin/env python3
"""Small Cloud Run revision proxy for an unchanged Mitate Application client."""
from __future__ import annotations

import http.server
import os
import urllib.error
import urllib.parse
import urllib.request


def required(name: str) -> str:
    value = os.environ.get(name, "")
    if not value or "\n" in value or "\r" in value:
        raise RuntimeError(f"missing_or_invalid_{name}")
    return value


UPSTREAM = required("F9_PROXY_UPSTREAM_URL").rstrip("/")
AUDIENCE = required("F9_PROXY_UPSTREAM_AUDIENCE")
PORT = int(os.environ.get("PORT", "8080"))
METADATA_URL = "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity?audience=" + urllib.parse.quote(AUDIENCE, safe="")


def identity_token() -> str:
    request = urllib.request.Request(METADATA_URL, headers={"Metadata-Flavor": "Google"})
    with urllib.request.urlopen(request, timeout=5) as response:
        token = response.read().decode("utf-8").strip()
    if not token:
        raise RuntimeError("empty_identity_token")
    return token


class Proxy(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        self.forward()

    def do_POST(self) -> None:  # noqa: N802
        self.forward()

    def forward(self) -> None:
        if not self.path.startswith(("/v1/", "/health")):
            self.send_error(404)
            return
        if not self.headers.get("Authorization", "").startswith("Bearer "):
            self.send_error(401)
            return
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length) if length else None
        headers = {key: value for key, value in self.headers.items() if key.lower() not in {"host", "content-length", "x-serverless-authorization"}}
        headers["X-Serverless-Authorization"] = f"Bearer {identity_token()}"
        request = urllib.request.Request(UPSTREAM + self.path, data=body, headers=headers, method=self.command)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                result = response.read()
                self.send_response(response.status)
                for key, value in response.headers.items():
                    if key.lower() not in {"connection", "transfer-encoding"}:
                        self.send_header(key, value)
                self.end_headers()
                self.wfile.write(result)
        except urllib.error.HTTPError as error:
            result = error.read()
            self.send_response(error.code)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(result)
        except (OSError, RuntimeError, ValueError):
            self.send_error(502)

    def log_message(self, format: str, *args: object) -> None:
        print("f9-revision-proxy request completed", flush=True)


http.server.ThreadingHTTPServer(("0.0.0.0", PORT), Proxy).serve_forever()
