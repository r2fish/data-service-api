"""Static read of the r2db-api nginx server-block template
(`r2db-api/deploy/nginx/r2dbsvc-api-8443.conf.example`): the `Host` header
each of its two `location` blocks forwards to its upstream (ledger R-121).

What this test pins, one property: the `location` blocks that proxy
(`proxy_pass`) are exactly `/v1/` and `/control/v1/`, each carries exactly
one `proxy_set_header Host $http_host;` -- the client's own `Host` header,
port included -- and no `location` block forwards `$host` (the name
alone). The application builds a redirect's `Location` from the `Host` it
receives, and the template's listener is on 8443, not the scheme's default
port: with `$host`, a client that followed the application's own
trailing-slash redirect would be sent to the same name on 443, the
existing production service, and a client that re-sends its credentials
across such a redirect would carry its bearer there.
`conformance-tests/socket_harness.py`'s conf mirrors this template; its
own behaviour is measured there, over both socket plugs
(`conformance-tests/test_wire_entry.py::
test_socket_redirect_location_keeps_the_declared_authority`).

The template is read as nginx reads it: a `#` starts a comment to the end
of the line, `location <path> {` opens a block and `}` closes it, directive
names compare case-insensitively, and a directive is `name args... ;`. A
directive that survives only inside a comment is absent here; a `location`
nested inside another is refused rather than misread. The test first
asserts that both proxied `location` blocks exist and each carries exactly
one `Host` directive, so it never passes on an empty read.
"""
from __future__ import annotations

from pathlib import Path

TEMPLATE = Path(__file__).resolve().parents[1] / "deploy" / "nginx" / "r2dbsvc-api-8443.conf.example"

#: The two `location` blocks the template proxies, in file order; every
#: other `location` (the catch-all `/`) proxies nothing.
PROXIED_LOCATIONS = ("/v1/", "/control/v1/")


def _locations(template: Path) -> dict[str, tuple[bool, list[str]]]:
    """`{location path: (proxies, [value of each `proxy_set_header Host`
    directive])}` for every `location` block of the template, comments
    stripped; `proxies` is whether the block carries a `proxy_pass`."""
    found: dict[str, tuple[bool, list[str]]] = {}
    current: str | None = None
    depth = 0
    for raw in template.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        words = line.rstrip(";").split()
        name = words[0].lower()
        if name == "location" and line.endswith("{"):
            assert current is None, f"{template.name}: location {words[1]!r} nested inside location {current!r}"
            current = words[1]
            depth = 1
            assert current not in found, f"{template.name}: duplicate location {current!r}"
            found[current] = (False, [])
            continue
        if current is None:
            continue
        if line.endswith("{"):
            depth += 1
        elif line == "}":
            depth -= 1
            if depth == 0:
                current = None
        elif name == "proxy_pass":
            found[current] = (True, found[current][1])
        elif name == "proxy_set_header" and len(words) >= 2 and words[1].lower() == "host":
            assert len(words) == 3, f"{template.name}: malformed Host directive {line!r} in location {current!r}"
            found[current][1].append(words[2])
    return found


def test_both_proxied_locations_forward_the_clients_own_host_header_with_its_port() -> None:
    locations = _locations(TEMPLATE)
    proxied = tuple(path for path, (proxies, _hosts) in locations.items() if proxies)
    assert proxied == PROXIED_LOCATIONS, (
        f"{TEMPLATE.name}: the locations that proxy are {proxied!r}, expected {PROXIED_LOCATIONS!r}"
    )
    for location in PROXIED_LOCATIONS:
        hosts = locations[location][1]
        assert len(hosts) == 1, f"{TEMPLATE.name}: location {location!r} carries {len(hosts)} Host directives, expected 1"
        assert hosts == ["$http_host"], (
            f"{TEMPLATE.name}: location {location!r} forwards Host {hosts[0]!r}, expected '$http_host'"
        )
    for location, (_proxies, hosts) in locations.items():
        assert "$host" not in hosts, f"{TEMPLATE.name}: location {location!r} forwards Host $host"
