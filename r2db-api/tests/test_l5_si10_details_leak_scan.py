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
IDENTIFIER_INVALID and CAPABILITY_UNSUPPORTED included -- M-5, `{scratchpad}
/audit-wp2e-2.md` R-6 -- adapted from `{scratchpad}/aud2e_probe.py`'s own
19 in-scope-fixed cases) and asserts, over EVERY resulting `details`
dict's 4 keys, that none of them ever carries (a) the row VALUE the probe
supplied (a distinctive per-probe marker), (b) a SQL fragment, (c) a DSN
fragment, (d) an internal reserved name/schema/table name, (e) a stack-
trace fragment, (f) a value outside `observed_type`'s own fixed
vocabulary (M-5: a Python type name such as `str`/`int` would leak
exactly this way). V-9's own "an adversarial identifier may legitimately
be echoed back as a request-internal PATH, since that is a position, not
a value" carve-out means a marker used as the identifier being validated
is NOT itself a leak if the resulting `field` is a FIXED path constant
independent of that identifier's own text (`"entity"`, `"field"`,
`"operations/0/operation"`, an `<n>`-indexed `"order_by/<i>"`/`"select"`)
-- several probes below do exactly this (the marker IS the invalid
identifier) precisely because it stays unambiguous.

Ruling N-1 (`{scratchpad}/rulings-r3-r7-flip.md` 追補 3): a mutation
`values` dict KEY used to be the one identifier-syntax position whose
`field` was BUILT FROM the identifier's own text (`operations/<i>/values/
<key>`), which is exactly the C-03 `test_identifier_positions_reject_
every_payload` regression N-1 closes -- an adversarial key echoed
verbatim through that f-string. N-1 fixes every identifier-syntax call
site to stop at the CONTAINER position instead (`operations/<i>/values`,
never `.../<key>`), so a marker used as a `values` key is now ALSO safe
to use directly below, and doing so is this file's own regression probe
for the fix (M-5/L-5: "denial's `field` for an invalid identifier must
never contain that identifier")."""
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
    # M-5 (`{scratchpad}/audit-wp2e-2.md` R-6, ruling addendum 2): the
    # audit found `_PROBES` never once fired IDENTIFIER_INVALID (fully
    # absent) or exercised a CAPABILITY_UNSUPPORTED site whose `field`
    # names a request position -- the 5 probes below close that. Every
    # `field` these produce is a FIXED path constant ("entity"/"field"/
    # "operations/0/operation") independent of the marker's own value, so
    # -- unlike a values-KEY or where-field probe, where the marker would
    # legitimately become part of the path itself (V-9's carve-out) --
    # the marker appearing in `field` here is unambiguously a leak, never
    # an allowed echo. The marker's own hyphens (`si10-marker-N-...`)
    # already violate `IDENTIFIER`'s `[A-Za-z0-9_]` grammar, so it can be
    # used directly as the invalid identifier itself without any extra
    # corruption.
    (
        "IDENTIFIER_INVALID entity name syntax",
        None,
        lambda s, r, d, m: s.query(r, m, select=["id"]),
    ),
    (
        "IDENTIFIER_INVALID select field syntax",
        None,
        lambda s, r, d, m: s.query(r, "notes", select=[m]),
    ),
    (
        "IDENTIFIER_INVALID order_by field syntax",
        None,
        lambda s, r, d, m: s.query(r, "notes", select=["id"], order_by=[{"field": m}]),
    ),
    (
        "IDENTIFIER_INVALID add_field name syntax (reserved-prefix-shaped, request-shape)",
        None,
        lambda s, r, d, m: s.schema(d, {"operation": "add_field", "entity": "notes", "field": m, "field_type": "string"}),
    ),
    # Ruling N-1 (`{scratchpad}/rulings-r3-r7-flip.md` 追補 3, L-5 regression
    # probe): the marker used AS the malformed mutation `values` dict key
    # itself -- the exact C-03 `test_identifier_positions_reject_every_
    # payload` regression this ruling closes (the key used to be echoed
    # verbatim into `field` via `operations/<i>/values/<key>`). `field`
    # must now be the container position `operations/0/values` only, never
    # containing the marker's own text -- the generic scan below already
    # asserts this (marker not present in ANY of the 4 keys), so this
    # probe is this file's own direct exercise of that assertion for the
    # bug N-1 fixed.
    (
        "IDENTIFIER_INVALID mutation values key syntax (marker used AS the key itself)",
        None,
        lambda s, r, d, m: s.mutate(r, "notes", [{"operation": "insert", "values": {m: "x"}}]),
    ),
    (
        "CAPABILITY_UNSUPPORTED mutation operation not supported (choke point, field = operations/<i>/operation)",
        None,
        lambda s, r, d, m: s.mutate(r, "notes", [{"operation": "replace", "values": {"body": m}}]),
    ),
    (
        "CAPABILITY_UNSUPPORTED upsert with no declared uniqueness key (choke point, field = operation)",
        None,
        lambda s, r, d, m: s.mutate(r, "notes", [{"operation": "upsert", "values": {"body": m}}]),
    ),
]


#: M-5: the contract's own `observed_type` vocabulary (`errors.
#: observed_type_of`'s docstring) -- a value from OUTSIDE this set (a
#: Python type name such as `str`/`int`/`list`/`dict`, which is exactly
#: what `type(value).__name__` or a bare `str(type(value))` would leak)
#: is a distinct kind of disclosure the earlier 4 fragment categories
#: cannot catch on their own (none of them are substrings of a Python
#: type name), named explicitly by ruling L-5/M-5.
_OBSERVED_TYPE_VOCAB = {"string", "integer", "number", "boolean", "object", "array", "null", "absent"}


def test_si10_scan_finds_no_leaked_value_sql_dsn_internal_name_or_stack_trace():
    observed_by_code: dict[str, int] = {code: 0 for code in _DENIAL_CODES}
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
            observed_by_code[exc.code] += 1
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
                if key == "observed_type" and value not in _OBSERVED_TYPE_VOCAB:
                    leaks.append(f"{name}: {key}={value!r} is outside the observed_type vocabulary (Python type-name leak)")
        except Exception as exc:  # pragma: no cover - a probe construction bug, not a leak finding
            pytest.fail(f"probe {name!r} raised an unexpected exception (probe itself is broken, not a leak): {exc!r}")
    # M-5: strengthened from a single `observed >= 1` vacuum floor to one
    # per vocabulary CODE -- the pre-M-5 floor was satisfied entirely by
    # VALIDATION_FAILED probes while IDENTIFIER_INVALID/CAPABILITY_
    # UNSUPPORTED were never observed at all (the audit's own finding).
    for code, count in observed_by_code.items():
        assert count >= 1, f"scan observed 0 denials of {code} -- vacuous for this code, fix the probe set before trusting this test"
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
