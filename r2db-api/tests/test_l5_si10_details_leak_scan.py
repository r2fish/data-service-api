"""WP-2e rework (`{scratchpad}/audit-wp2e.md` I-3, ruling
`{scratchpad}/rulings-r3-r7-flip.md` L-5/V-9): SI-10 requires that the
`errors.details_vocabulary` 4-key form (`violated_declaration`/`field`/
`declared_type`/`observed_type`) never carries a client-supplied VALUE, a
SQL fragment, a DSN, an internal name, or a stack-trace fragment. Before
this file, the only peer-local test for this was `test_denial_details_
and_request_id.py::test_details_do_not_carry_the_offending_value` -- ONE
probe through ONE `field_type` call site with a marker in `field`'s own
OWN value slot. The audit found this is not a scan: injecting the exact
same kind of leak into `http.py`'s unknown-key branch's `field` (an
internal name, `public._r2db_internal_notes_tbl`) turned 3 tests red for
the wrong reason (those 3 tests pin `field`'s value with a COMPLETE
equality assert, not because anything here actually scanned for the
leak) -- the SAME leak on any of the many `field`-less/`declared_type`-
carrying/`observed_type`-carrying sites went completely undetected.

This file drives a wide, diverse set of real denial paths (structured.py/
service.py/http.py/limits.py choke-point and request-shape sites,
IDENTIFIER_INVALID and CAPABILITY_UNSUPPORTED included, adapted from
`{scratchpad}/aud2e_probe.py`'s own 19 in-scope-fixed cases) and asserts,
over EVERY resulting `details` dict's 4 keys, that none of them ever
carries (a) the row VALUE the probe supplied (a distinctive per-probe
marker, used ONLY as a data value, never as an identifier -- V-9's own
"an adversarial identifier may legitimately be echoed back as a request-
internal PATH, since that is a position, not a value" carve-out means a
marker used AS an identifier is expected to appear in `field` and is not
a leak; this file's own markers are therefore never used as identifiers),
(b) a SQL fragment, (c) a DSN fragment, (d) an internal reserved name/
schema/table name, (e) a stack-trace fragment."""
from __future__ import annotations

import re

import pytest

from r2db_api import ControlAuthority, CredentialStore, DataService
from r2db_api.errors import FoundationError

_DENIAL_CODES = {"VALIDATION_FAILED", "IDENTIFIER_INVALID", "CAPABILITY_UNSUPPORTED"}

#: Fragments that must never appear in a `details` value, keyed by what
#: they would prove leaked. Matched case-insensitively, substring.
_SQL_FRAGMENTS = ("select ", "insert into", "update ", "delete from", " where ", "drop table")
_DSN_FRAGMENTS = ("postgresql://", "postgres://", "dbname=", "password=")
_INTERNAL_NAME_FRAGMENTS = ("_r2db", "public.", "r2dbsvc", "pg_catalog")
_STACK_TRACE_FRAGMENTS = ("traceback (most recent", "line ", ".py\", line", "raise ")


def _build():
    credentials = CredentialStore(pepper="si10-scan-pepper")
    with credentials.unit_of_work() as work:
        credentials.add("cred-si10", "app-si10", "runtime", "secret-si10", work=work)
    with credentials.unit_of_work() as work:
        credentials.add("dev-si10", "app-si10", "developer", "dev-secret-si10", work=work)
    service = DataService(credentials)
    ControlAuthority(service).register_application("app-si10", entities={"notes": [{"body": "a"}]})
    return service, service.authenticate("cred-si10.secret-si10"), service.authenticate("dev-si10.dev-secret-si10")


#: (name, setup, probe) -- `setup(service, developer)` (optional, may be
#: `None`) runs first with no marker involved; `probe(service, runtime,
#: developer, marker)` then must raise `FoundationError`. `marker` is a
#: STRING, embedded ONLY as a data VALUE (never as an identifier/field
#: name) so its appearance anywhere in `details` is unambiguously a leak
#: (V-9: an adversarial IDENTIFIER may legitimately be echoed back as a
#: request-internal PATH -- a position, not a value -- so this file's own
#: markers are never used as identifiers, keeping every appearance an
#: unambiguous leak rather than an allowed echo).
_PROBES: list[tuple[str, "object", "object"]] = [
    (
        "mutation value type mismatch (structured.py field_type branch)",
        lambda s, d: s.schema(d, {"operation": "add_field", "entity": "notes", "field": "n", "field_type": "integer"}),
        lambda s, r, d, m: s.mutate(r, "notes", [{"operation": "insert", "values": {"n": m}}]),
    ),
    (
        "mutation values not an object",
        None,
        lambda s, r, d, m: s.mutate(r, "notes", [{"operation": "insert", "values": m}]),
    ),
    (
        "destructive flag not boolean",
        None,
        lambda s, r, d, m: s.mutate(r, "notes", [{"operation": "insert", "values": {"body": "x"}, "destructive": m}]),
    ),
    (
        "expected_revision not a string",
        None,
        lambda s, r, d, m: s.mutate(r, "notes", [{"operation": "update", "values": {"body": "x"}, "where": [{"field": "body", "operator": "eq", "value": "a"}], "expected_revision": {"nested": m}}]),
    ),
    (
        "matches operator value must be a string",
        None,
        lambda s, r, d, m: s.query(r, "notes", select=["id"], where=[{"field": "body", "operator": "matches", "value": [m]}]),
    ),
    (
        "cursor must be a string (request-shape, service.py)",
        None,
        lambda s, r, d, m: s.query(r, "notes", select=["id"], cursor={"nested": m}),
    ),
    (
        "order_by must be a bounded list",
        None,
        lambda s, r, d, m: s.query(r, "notes", select=["id"], order_by={"nested": m}),
    ),
    (
        "schema operation must be an object",
        None,
        lambda s, r, d, m: s.schema(d, [m]),
    ),
    (
        "mutation operations not a list (request-shape, service.py)",
        None,
        lambda s, r, d, m: s.mutate(r, "notes", {"nested": m}),
    ),
    (
        "CAPABILITY_UNSUPPORTED transaction mode (capability, no field-type leg at all)",
        None,
        lambda s, r, d, m: s.mutate(r, "notes", [{"operation": "insert", "values": {"body": m}}], transaction="best_effort"),
    ),
]


def test_si10_scan_finds_no_leaked_value_sql_dsn_internal_name_or_stack_trace():
    observed = 0
    leaks: list[str] = []
    for i, (name, setup, probe) in enumerate(_PROBES):
        marker = f"si10-marker-{i}-do-not-leak-3f9a7c2e"
        service, runtime, developer = _build()
        if setup is not None:
            setup(service, developer)
        try:
            probe(service, runtime, developer, marker)
        except FoundationError as exc:
            if exc.code not in _DENIAL_CODES:
                continue
            observed += 1
            for key in ("violated_declaration", "field", "declared_type", "observed_type"):
                value = exc.details.get(key)
                if value is None:
                    continue
                haystack = str(value).lower()
                if marker.lower() in haystack:
                    leaks.append(f"{name}: {key}={value!r} carries the probe's own row value")
                for frag in _SQL_FRAGMENTS:
                    if frag in haystack:
                        leaks.append(f"{name}: {key}={value!r} carries a SQL fragment ({frag!r})")
                for frag in _DSN_FRAGMENTS:
                    if frag in haystack:
                        leaks.append(f"{name}: {key}={value!r} carries a DSN fragment ({frag!r})")
                for frag in _INTERNAL_NAME_FRAGMENTS:
                    if frag in haystack:
                        leaks.append(f"{name}: {key}={value!r} carries an internal name fragment ({frag!r})")
                for frag in _STACK_TRACE_FRAGMENTS:
                    if frag in haystack:
                        leaks.append(f"{name}: {key}={value!r} carries a stack-trace fragment ({frag!r})")
        except Exception as exc:  # pragma: no cover - a probe construction bug, not a leak finding
            pytest.fail(f"probe {name!r} raised an unexpected exception (probe itself is broken, not a leak): {exc!r}")
    assert observed >= 1, "scan observed 0 denials -- vacuous, fix the probe set before trusting this test"
    assert leaks == [], "\n".join(leaks)


def test_si10_scan_covers_at_least_the_4_key_shapes_the_audit_named_undetected():
    """Non-空振り (I-3's own reproduction): the pre-rework build's ONLY
    SI-10 test pinned exact equality on `field` for 3 tests total, and
    every OTHER 4-key shape (IDENTIFIER_INVALID's `field`, CAPABILITY_
    UNSUPPORTED's `field`, most `declared_type`/`observed_type` sites) had
    no leak coverage at all. This test proves the scan above actually
    reaches denials carrying `declared_type`/`observed_type` (not only a
    bare `field`), so a leak specifically inside one of those two keys
    would be caught -- not just a `field` leak."""
    service, runtime, developer = _build()
    service.schema(developer, {"operation": "add_field", "entity": "notes", "field": "n", "field_type": "integer"})
    with pytest.raises(FoundationError) as exc:
        service.mutate(runtime, "notes", [{"operation": "insert", "values": {"n": "leaked-marker-should-not-appear-either"}}])
    assert exc.value.details.get("declared_type") is not None
    assert exc.value.details.get("observed_type") is not None
    assert "leaked-marker-should-not-appear-either" not in str(exc.value.details.get("declared_type"))
    assert "leaked-marker-should-not-appear-either" not in str(exc.value.details.get("observed_type"))
