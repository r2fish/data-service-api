"""Static read of the r2db-api nginx server-block template
(`r2db-api/deploy/nginx/r2dbsvc-api-8443.conf.example`): the `Host` header
each of its two `location` blocks forwards to its upstream (ledger R-121).

What this test pins, one property: both proxied `location` blocks (`/v1/`
and `/control/v1/`) carry `proxy_set_header Host $http_host;` -- the
client's own `Host` header, port included -- and no `location` block
forwards `$host` (the name alone). The application builds a redirect's
`Location` from the `Host` it receives, and the template's listener is on
8443, not the scheme's default port: with `$host`, a client that followed
the application's own trailing-slash redirect would be sent to the same
name on 443, the existing production service, carrying its bearer.
`conformance-tests/socket_harness.py`'s conf mirrors this template; its
own behaviour is measured there, over both socket plugs
(`conformance-tests/test_wire_entry.py::
test_socket_redirect_location_keeps_the_declared_authority`).

The template is read as nginx reads it: a `#` starts a comment to the end
of the line, `location <path> {` opens a block and `}` closes it, and a
directive is `name args... ;`. A directive that survives only inside a
comment is absent here. The test first asserts that both `location` blocks
exist and each carries exactly one `Host` directive, so it never passes on
an empty read.
"""
from __future__ import annotations

from pathlib import Path

TEMPLATE = Path(__file__).resolve().parents[1] / "deploy" / "nginx" / "r2dbsvc-api-8443.conf.example"

#: The two `location` blocks the template proxies, in file order; every
#: other `location` (the catch-all `/`) proxies nothing.
PROXIED_LOCATIONS = ("/v1/", "/control/v1/")


def _host_directives(template: Path) -> dict[str, list[str]]:
    """`{location path: [value of each `proxy_set_header Host` directive]}`
    for every `location` block of the template, comments stripped."""
    found: dict[str, list[str]] = {}
    current: str | None = None
    depth = 0
    for raw in template.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        words = line.rstrip(";").split()
        if words[0] == "location" and line.endswith("{"):
            current = words[1]
            depth = 1
            assert current not in found, f"{template.name}: duplicate location {current!r}"
            found[current] = []
            continue
        if current is not None:
            if line.endswith("{"):
                depth += 1
            elif line == "}":
                depth -= 1
                if depth == 0:
                    current = None
                continue
            if words[:2] == ["proxy_set_header", "Host"]:
                assert len(words) == 3, f"{template.name}: malformed Host directive {line!r} in location {current!r}"
                found[current].append(words[2])
    return found


def test_both_proxied_locations_forward_the_clients_own_host_header_with_its_port() -> None:
    hosts = _host_directives(TEMPLATE)
    for location in PROXIED_LOCATIONS:
        assert location in hosts, f"{TEMPLATE.name}: no location {location!r} block (found {sorted(hosts)!r})"
        assert len(hosts[location]) == 1, (
            f"{TEMPLATE.name}: location {location!r} carries {len(hosts[location])} Host directives, expected 1"
        )
        assert hosts[location] == ["$http_host"], (
            f"{TEMPLATE.name}: location {location!r} forwards Host {hosts[location][0]!r}, expected '$http_host'"
        )
    for location, values in hosts.items():
        assert "$host" not in values, f"{TEMPLATE.name}: location {location!r} forwards Host $host"
