"""C-09 -- security-relevant auditability, observed through audit_query
(SI-10, SI-14).

design: docs/design/PHASE4_DURABLE_AUDIT_SINK_V1.md §8.1 (the 4 vectors),
§8.4 (SurfaceAbsent's extended meaning), work order docs/work-orders/
PHASE4_DURABLE_AUDIT_SINK_WORK_ORDER.md WP-1 (supplementary rulings 1 and
2). Registered here via `@pytest.mark.condition("C-09")` (module-level
`pytestmark`).

This file was added in phase 4 WP-1: it makes C-09 executable through the
common conformance port for the first time (`CONDITIONS.md`'s prior status
for C-09 was "not yet executable (common suite) -- peer-local evidence
only"). **All four registered adapters now take the PROVIDED branch** --
the r2db pair since WP-2(b), the MitateDB pair since WP-3(b) (merge
`e60eb1e`, the same commit that removed the whole-registry guard's
`xfail`) -- so the 4 vectors below and both guards observe a real durable
audit sink through a real `audit_query`, on every one of them. The
`SurfaceAbsent` dispatch (design §8.4's own declare-first extension) is
retained and still correct for a deployment whose own
`capabilities().audit_query.status` is not `enabled`/`partial`, but no
currently-registered adapter reaches it. Written when no peer had flipped
yet, against the real eventual dispatch shape -- so the flips needed no
change to this file beyond removing that one `xfail`.

Declare-first dispatch (work order WP-1 supplementary ruling 1, mirrored on
`ConformanceAdapter.audit_query`'s own docstring and `SurfaceAbsent`'s):
`audit_query` is undeclared or declared anything other than `enabled`/
`partial` -> the port raises `SurfaceAbsent` WITHOUT presenting any request
at all (an extension of `SurfaceAbsent`'s classic "no callable exists"
meaning to also cover "this deployment declares it does not provide the
audit surface" -- see `adapter.SurfaceAbsent`'s own docstring). `audit_query`
declared `enabled`/`partial` -> the port presents a real request and
returns either `PROVIDED` (the raw `AuditResult` document) or
`ConformanceDenial` (a genuine contract-code denial, e.g. `FORBIDDEN` for
an application credential) -- never `SurfaceAbsent` in that branch.

The 4 vectors (design §8.1 / §9.2 property 4):

1. **Observability**: a destructive operation performed through the
   ordinary application plane becomes visible through `audit_query`.
   Scoped to fail-closed-class events only (design §8.1 vector 1's own
   scoping) -- these are written to the durable sink before the response
   (D-2/D-3), so visibility lag alone (`audit_visibility_lag_ms()`, never a
   fixed `sleep`) makes them observable.
2. **Secret absence**: no `audit.forbidden_fields` member appears as an
   event KEY, and no reusable secret/verifier value appears as an event
   VALUE. `actor_id`/`target_id`/`application_id`/`request_id`/`event_id`
   are never themselves treated as forbidden -- they are attribution
   identifiers SI-14 requires, not secrets (design §8.1 vector 2 / review
   m-1).
3. **Authority separation**: an application credential is refused
   `FORBIDDEN` on the control host's `audit_query`. The common port has no
   distinct "present this same request against the data-plane host"
   operation (port v1.8 added exactly the 3 methods the work order named,
   `audit_query`/`flush_audit_buffer`/`audit_visibility_lag_ms`, none of
   which parametrized over host; `flush_audit_buffer` is gone since port
   v1.19) -- the data-plane host's own
   `CAPABILITY_UNSUPPORTED` reply to the identical path string (design
   §7.5/§8.1 vector 3: two hosts answering differently is not a
   contradiction, since each is stating a true fact about itself) is
   peer-local evidence (`r2db-api`'s/`MitateDB-api`'s own `test_data_plane_
   host_audit_query_still_refuses_with_capability_unsupported`, shipped in
   WP-2(b)/WP-3(b)), disclosed here as a known boundary of what this
   common-suite vector can mechanically check, not silently assumed proven.
4. **No mutation/deletion surface**: no application-authority-reachable
   operation can author, override, update, or delete audit evidence
   (contract `audit.immutability`). Two layers, neither alone sufficient
   (audit packet finding: a port-ABC-only check can never see a mutating
   surface the port simply never exposed a method for): (i) the port ABC
   itself declares `audit_query` as the only audit-shaped operation, and
   it is read-only by construction (no `destructive`/`confirmation`
   parameter); (ii) each REAL, registered peer is additionally observed
   -- an HTTP-shaped adapter is probed with real `DELETE`/`PUT`/`PATCH`
   requests against both the canonical and alias audit-query paths on the
   control host (never 2xx), an in-process adapter has the real Python
   object(s) `control_audit_events()` itself reads introspected for any
   public callable shaped like `delete`/`purge`/`truncate`/`clear`/
   `remove`. No new port method is added for this -- both peer-observing
   forms reach through each concrete adapter's own existing private
   internals (`_control_send`, `_control_audit`/`_control_service`),
   never through the abstract port.

Two vacuity guards (work order WP-1 supplementary ruling 2), following
`test_c16_cross_entity_atomicity.py`'s own vacuity-guard style (a
registry-wide loop collecting each adapter's own reason, never a bare
`assert False`):

- `test_c09_declared_capability_implies_provided_branch` -- the INDIVIDUAL
  guard. Always active (no `xfail`): an adapter declaring `contract_version
  >= 1.4.0` (semver-tuple compared, never string-compared) AND `audit_query:
  enabled`/`partial` MUST take the PROVIDED branch. Vacuous while no adapter
  declared 1.4.0; load-bearing since WP-2(b), and now binding on all 4.
- `test_c09_every_control_surface_adapter_takes_the_provided_branch` -- the
  WHOLE-REGISTRY guard. It requires EVERY registered adapter with a control
  surface (`control_plane` status `enabled`/`partial` -- currently all 4,
  derived from the registry and each adapter's own declaration, never a
  hardcoded name list) to take the PROVIDED branch. Registered in WP-1 with
  `@pytest.mark.xfail(strict=True, ...)` because that was false until the
  LAST flip; `strict=True` meant an unexpected green (a premature partial
  flip, or a weakened guard) would fail loudly rather than pass silently.
  **The `xfail` was removed in WP-3(b)'s own flip commit** (work order §2.1
  / §6 item 8b), so this guard now runs plain and green.

Phase 5 WP-1 addendum (docs/design/PHASE5_CONTRACT_150_AND_LIMIT_RANGE_V1.md
§3 D-1/D-2, docs/work-orders/WORK_ORDER_PHASE5_CONTRACT_150_V1.md WP-1,
fix-round F-1/F-2/F-3): contract 1.5.0 makes `operation`/`target_kind`
declared vocabularies (`capabilities().audit_query.operations`/
`.target_kinds`, the same declare-the-hazard posture `event_class`
already had under 1.4.0), and same-label-amends 1.4.0's own unconditional
obligation (b) to scope its credential acceptance to the control
surface's `audit_query` control endpoint. This file's vector 1 no longer
correlates on a hand-enumerated candidate set (the former two module-
level frozenset constants this WP removed outright, never kept as a
fallback); three new same-shaped "declaration agreement" vectors instead
check that every event `audit_query` actually returns carries a value
inside the peer's OWN declared vocabulary for `event_class` (1.4.0
conditional; red only for the classes THIS suite's own session actually
observes -- a peer's full declared vocabulary is pinned by its own
peer-local (e) equality and snapshot test, not by this vector), and
`operation`/`target_kind` (both 1.5.0 conditional, vacuous until a peer
flips). A new unconditional vector (`test_c09_data_plane_host_audit_
query_alias_rejects_control_credential_unless_cohosted`, port v1.9's
`audit_query_on_data_plane_host` + `control_surface_cohosted_with_data_
plane()`) observes the amended obligation (b) directly against the
DATA-plane host's own alias, judged against the adapter's own DECLARED
topology fact rather than a live cross-check of response content --
registered `xfail`-free, since it is unconditional and both currently-
registered peers (both declaring non-cohosted) are already conformant. A
second whole-registry vacuity guard (`test_c09_every_control_surface_
adapter_declares_1_5_0`) was registered `xfail(strict=True)` in WP-1,
mirroring the 1.4.0 whole-registry guard's own WP-1 -> last-flip-WP arc --
**the `xfail` was removed in WP-3's own flip commit** (r2db-api flipped in
WP-2, MitateDB-api in WP-3; the guard now runs plain and green on all 4
plugs).
"""
from __future__ import annotations

import inspect
import time
from typing import Any, Mapping, Sequence

import pytest

from adapter import (
    UNCLASSIFIED,
    VALID_CONFIRMATION,
    ConformanceAdapter,
    ConformanceDenial,
    SurfaceAbsent,
    fresh_identifier,
    load_contract,
    signature_forbids_parameters,
    surfaces_cohosted,
)
from conftest import registered_adapters

pytestmark = pytest.mark.condition("C-09")


# --- shared helpers ----------------------------------------------------


def _semver_tuple(version: str) -> tuple[int, int, int]:
    """Parses a `"X.Y.Z"` string into a comparable tuple of ints -- NEVER a
    string comparison (work order WP-1 review point 4: `"1.10.0" < "1.4.0"`
    under string ordering, a genuine bug class this parsing avoids).

    Review F-6: a component that does not parse as a plain int (e.g. a
    pre-release suffix like `"1.4.0-rc1"`) makes the WHOLE version compare
    BELOW any real 1.4.0 release, rather than raising `ValueError` out of
    this helper. Both guards that call this gate an OBLIGATION ("this
    adapter must take the PROVIDED branch") on the version meeting a
    floor -- an unparseable version must never be silently coerced into
    satisfying that floor (this would be the wrong, fail-OPEN direction
    for a gate that ADDS a requirement); comparing below the floor is the
    fail-closed direction and is also simply correct, since a version this
    helper cannot even parse has not affirmatively demonstrated it meets
    1.4.0's own obligations.
    """
    parts = (version.split(".") + ["0", "0", "0"])[:3]
    try:
        return (int(parts[0]), int(parts[1]), int(parts[2]))
    except (ValueError, TypeError):
        return (0, 0, 0)


def _control_plane_status(adapter) -> str:
    """The peer's own declared `control_plane` capability status, read from
    its real, application-plane `capability_document()` -- mirrors
    `test_c14_authority_boundary.py`'s own identically-named helper
    (each test module owns its own copy, this suite's existing convention,
    e.g. `test_c11_response_schema_conformance.py`'s own `_assert_surface_
    absent_claim`)."""
    document = adapter.capability_document()
    capabilities = document.get("capabilities")
    assert isinstance(capabilities, dict), (
        f"{adapter.name}: capability_document() has no 'capabilities' mapping -- {document!r}"
    )
    control_plane = capabilities.get("control_plane")
    assert isinstance(control_plane, dict) and "status" in control_plane, (
        f"{adapter.name}: capability_document()['capabilities'] has no 'control_plane' entry carrying a "
        f"'status' key -- got {control_plane!r}"
    )
    return control_plane["status"]


def _audit_query_declaration(adapter) -> tuple[str, str]:
    """Reads `(contract_version, audit_query_status)` off the peer's own
    real `control_capabilities()` document, via this adapter's own
    privileged `control_credential()` -- never via an application
    credential, which `control_plane.authority` fails closed on
    `control_capabilities` itself (the same reasoning each adapter's own
    `_audit_query_status()` helper documents)."""
    control_actor = adapter.control_credential()
    document = adapter.control_capabilities(control_actor)
    status = document.get("capabilities", {}).get("audit_query", {}).get("status", "unavailable")
    return document.get("contract_version", "0.0.0"), status


def _declared_audit_vocabulary(document: Mapping[str, Any], key: str) -> frozenset[str]:
    """Reads one of `audit_query`'s own declared vocabulary keys
    (`event_classes`/`operations`/`target_kinds`, contract 1.4.0 item 4 /
    1.5.0 subordinate ruling 10 item 1) off a REAL `control_capabilities()`
    document -- never a hardcoded set. Declare-the-hazard (D-7): the
    contract places no enum on any of these three keys, only the shape
    "each implementation's own declared list"."""
    return frozenset(document.get("capabilities", {}).get("audit_query", {}).get(key, []))


def _assert_audit_surface_absent_claim(adapter, exc: SurfaceAbsent) -> None:
    """Independently re-verifies an `audit_query`-shaped `SurfaceAbsent`
    claim (design §8.4's extended meaning) the same 3-part way every other
    `SurfaceAbsent` claim on this port is re-verified (mirrors
    `test_c11_response_schema_conformance.py`'s own `_assert_surface_
    absent_claim` / `test_c14_authority_boundary.py`'s own helper of the
    same shape) -- never taken on an adapter's bare word."""
    violations = set(signature_forbids_parameters(exc.surface, exc.forbidden_parameters))
    exempt = set(exc.exempt_parameters)
    assert violations == exempt, (
        f"{adapter.name}: SurfaceAbsent's signature_forbids_parameters violations {sorted(violations)!r} "
        f"do not exactly equal its declared exempt_parameters {sorted(exempt)!r}"
    )
    declared = {f.lower() for f in exc.forbidden_parameters}
    assert "audit" in declared, (
        f"{adapter.name}: SurfaceAbsent's forbidden_parameters {exc.forbidden_parameters!r} does not "
        "include 'audit' -- a narrower fragment set could pass signature_forbids_parameters vacuously"
    )
    declared_surface = set(exc.surface)
    public_surface = set(adapter.public_operation_callables())
    assert declared_surface >= public_surface, (
        f"{adapter.name}: SurfaceAbsent's declared surface omits "
        f"{[c for c in public_surface if c not in declared_surface]!r} of the peer's own real "
        "public_operation_callables()"
    )


def _dispatch_audit_query(adapter, actor, request: Mapping[str, Any]):
    """Runs `adapter.audit_query(actor, request)` and classifies the
    outcome as one of `"surface_absent"` (independently re-verified) /
    `"provided"` (a real `AuditResult`-shaped mapping) / `"denied"` (a
    `ConformanceDenial`). Raises `AssertionError` on anything else (a
    successful call returning a non-mapping, or a mapping missing
    `events`) -- never silently accepted."""
    try:
        result = adapter.audit_query(actor, request)
    except SurfaceAbsent as exc:
        _assert_audit_surface_absent_claim(adapter, exc)
        return "surface_absent", exc
    except ConformanceDenial as exc:
        return "denied", exc
    assert isinstance(result, Mapping) and "events" in result, (
        f"{adapter.name}: audit_query(actor, {request!r}) succeeded but did not return an AuditResult-shaped "
        f"mapping (missing 'events') -- got {result!r}"
    )
    return "provided", result


def _event_identity(event: Mapping[str, Any]) -> Any:
    """A per-event identity suitable for baseline set-difference (audit
    packet §6.3): `event_id` ALONE is not a safe identity key across the
    `audit_query` UNION -- the contract itself states so
    (`audit.query_ordering`, CCR_DISPOSITION.md subordinate ruling 9(a)
    item 2: "`event_id` の一意性は各耐久表の PK でしか保証されず...`plane`
    を第2キーに入れないと...跨表衝突で全順序が壊れる"), so vector 1's own
    baseline-diff below must not rely on `event_id` alone either -- an
    application-plane event that happens to collide with a PRE-EXISTING
    control-plane event's `event_id` would otherwise be silently absorbed
    into the baseline (a false negative). Prefers the opaque `cursor`
    field when present (design D-6: each event's own unique position) --
    falls back to `(plane, event_id)`, the SAME compound key the contract
    itself defines as sufficient, when a peer's real `AuditResult` does
    not (yet) carry `cursor` on every event.
    """
    cursor = event.get("cursor")
    if cursor is not None:
        return ("cursor", cursor)
    return ("plane_event_id", event.get("plane"), event.get("event_id"))


def _require_provided(adapter, actor, request: Mapping[str, Any]) -> Mapping[str, Any]:
    """Dispatches `audit_query` and requires the PROVIDED branch, raising a
    clear, diagnostic `AssertionError` for `denied`/`surface_absent`
    instead of silently discarding the form (review F-6): a caller that
    already confirmed a PROVIDED branch is reachable earlier in the SAME
    test (via an initial `_dispatch_audit_query` probe) must never let a
    LATER call's non-PROVIDED outcome degrade into an opaque `TypeError`
    on `result["events"]` -- e.g. `_, result = _dispatch_audit_query(...)`
    blindly unpacking a `(form, exception)` pair as if it were always
    `(form, document)`.
    """
    form, outcome = _dispatch_audit_query(adapter, actor, request)
    assert form == "provided", (
        f"{adapter.name}: expected the PROVIDED audit_query branch (already confirmed reachable earlier in "
        f"this test), got {form!r} instead: {outcome!r}"
    )
    return outcome


def _walk_audit_events(adapter, actor, page_limit: int = 1000, max_pages: int = 500) -> Mapping[str, Any]:
    """Reads `audit_query` to its last page: each page's last event's
    `cursor` is the next request's `after`, and the walk ends on an empty
    page (or an event without a cursor). Returns `{"events": [every event
    in order]}`. A single `{"limit": 1000}` read sees only the OLDEST 1000
    events, so once a platform holds more than that the newest events sit
    outside the page and a test looking for one of them fails for a reason
    that has nothing to do with the peer. `max_pages` only stops a cursor
    that never advances from looping forever."""
    events: list[Any] = []
    after = None
    for _ in range(max_pages):
        request: dict[str, Any] = {"limit": page_limit}
        if after is not None:
            request["after"] = after
        page = _require_provided(adapter, actor, request)["events"]
        if not page:
            return {"events": events}
        events.extend(page)
        cursor = page[-1].get("cursor") if isinstance(page[-1], Mapping) else None
        if cursor is None:
            return {"events": events}
        after = cursor
    raise AssertionError(
        f"{adapter.name}: audit_query still returned events after {max_pages} pages of {page_limit} -- "
        "the cursor does not advance the read"
    )


def _dispatch_audit_query_on_data_plane_host(adapter, actor, request: Mapping[str, Any]):
    """Twin of `_dispatch_audit_query` for port v1.9's `audit_query_on_
    data_plane_host` (D-2, CCR_DISPOSITION.md subordinate ruling 10 item
    2) -- classifies the outcome the identical 3-way
    ("surface_absent"/"provided"/"denied") shape, so this test file has
    exactly one dispatch idiom, not two divergent ones."""
    try:
        result = adapter.audit_query_on_data_plane_host(actor, request)
    except SurfaceAbsent as exc:
        _assert_audit_surface_absent_claim(adapter, exc)
        return "surface_absent", exc
    except ConformanceDenial as exc:
        return "denied", exc
    assert isinstance(result, Mapping) and "events" in result, (
        f"{adapter.name}: audit_query_on_data_plane_host(actor, {request!r}) succeeded but did not return an "
        f"AuditResult-shaped mapping (missing 'events') -- got {result!r}"
    )
    return "provided", result


def _require_denied_with(adapter, form: str, outcome: Any, code: str) -> None:
    """Requires a dispatched `(form, outcome)` pair (`_dispatch_audit_
    query`/`_dispatch_audit_query_on_data_plane_host`'s own return shape)
    to be the DENIED form with EXACTLY `code` -- never a different denial
    code (even a plausible-looking one, e.g. `CAPABILITY_UNSUPPORTED`/
    `FORBIDDEN`), never `provided`, never `surface_absent`. The first
    helper in this file that checks a denial's own CODE rather than only
    its FORM (`_require_provided` only ever checks form)."""
    assert form == "denied", (
        f"{adapter.name}: expected the DENIED branch with code {code!r}, got {form!r} instead: {outcome!r}"
    )
    assert outcome.code == code, (
        f"{adapter.name}: expected ConformanceDenial({code!r}), got {outcome.code!r} instead: {outcome!r}"
    )


# --- vector 1: observability --------------------------------------------


def test_c09_v1_fail_closed_events_are_observable_through_audit_query(adapter, fx):
    control_actor = adapter.control_credential()
    form, outcome = _dispatch_audit_query(adapter, control_actor, {"limit": 1})
    if form == "surface_absent":
        return
    if form == "denied":
        raise AssertionError(
            f"{adapter.name}: control_credential() was refused on audit_query with {outcome.code!r} -- a "
            "genuine control credential must never be denied its own read-only audit surface"
        )

    # PROVIDED. Review F-1: the row inserted below is set up BEFORE the
    # baseline snapshot, so the insert's own event (a non-destructive
    # `data_operation` event, design §7.3) is never counted as "new" below
    # -- only the DESTRUCTIVE DELETE that follows the baseline snapshot
    # can be. The new event is identified by EVENT_ID SET DIFFERENCE
    # against that baseline (the "time window" the review's own "あるべき
    # 形" names), never by a value this test injected into row data riding
    # along as `target_id` -- `target_id` is contract-reserved for a
    # single target CREDENTIAL/APPLICATION id (`audit.fields_note`), never
    # a data row key (design docs/design/PHASE4_DURABLE_AUDIT_SINK_V1.md,
    # its "target_id は当面すべて NULL になる" paragraph).
    session = fx.runtime_a
    entity = fx.shared_entity
    marker = fresh_identifier("c09v1")
    adapter.insert(session, entity, {"item_key": 1, "label": "c09v1", "probe_key": marker, "probe_value": marker})

    baseline = _walk_audit_events(adapter, control_actor)
    baseline_ids = {_event_identity(event) for event in baseline["events"] if isinstance(event, Mapping)}

    adapter.delete(session, entity, "probe_key", marker, destructive=True, confirmation=VALID_CONFIRMATION)

    # The delete's event is written durably before commit (design D-2/D-3),
    # so visibility lag alone -- never a fixed sleep -- makes the delete
    # above observable.
    time.sleep(adapter.audit_visibility_lag_ms() / 1000)
    result = _walk_audit_events(adapter, control_actor)
    events = result["events"]
    new_events = [
        event for event in events
        if isinstance(event, Mapping) and _event_identity(event) not in baseline_ids
    ]
    assert new_events, (
        f"{adapter.name}: no new audit_query event appeared after the destructive delete "
        f"(baseline had {len(baseline_ids)} event(s))"
    )

    # 1.4.0 obligation (design docs/design/PHASE5_CONTRACT_150_AND_LIMIT_
    # RANGE_V1.md §6.1's own "(i) is a subset of (ii)" framing): the
    # destructive delete's own new event(s) must be scoped to THIS
    # application -- `operation`/`target_kind` are no longer correlated
    # here against a hand-enumerated candidate set (phase 5 WP-1, D-1:
    # the candidate-set mechanism that used to stand in for this is
    # replaced by the declared-vocabulary subset vectors below, which see
    # ALL returned events, not only this window's own new ones).
    scoped_events = [event for event in new_events if event.get("application_id") == fx.app_a]
    assert scoped_events, (
        f"{adapter.name}: none of the {len(new_events)} new event(s) after the destructive delete are scoped to "
        f"application_id={fx.app_a!r} -- new events: {new_events!r}"
    )

    # 1.5.0 conditional obligation (D-1, CCR_DISPOSITION.md subordinate
    # ruling 10 item 1): for a 1.5.0-declaring peer whose own audit_query
    # is enabled/partial, the destructive delete's own application_id-
    # scoped event(s) must ALSO carry an operation/target_kind pair that
    # is a member of THIS peer's own declared audit_query.operations/
    # target_kinds vocabulary -- read from a REAL control_capabilities()
    # document, never a hardcoded set. A 1.4.0-declaring peer takes only
    # the application_id-scoping obligation above (work order WP-1 §4
    # "1.4.0 の peer は従来どおりの vector 1... だけを課される").
    contract_version, _status = _audit_query_declaration(adapter)
    if _semver_tuple(contract_version) < (1, 5, 0):
        return
    document = adapter.control_capabilities(control_actor)
    declared_operations = _declared_audit_vocabulary(document, "operations")
    declared_target_kinds = _declared_audit_vocabulary(document, "target_kinds")
    assert any(
        event.get("operation") in declared_operations and event.get("target_kind") in declared_target_kinds
        for event in scoped_events
    ), (
        f"{adapter.name}: none of the {len(scoped_events)} application_id-scoped new event(s) after the "
        "destructive delete carry an operation/target_kind pair that is a member of this peer's OWN declared "
        f"audit_query.operations/target_kinds vocabulary -- declared operations={sorted(declared_operations)!r}, "
        f"target_kinds={sorted(declared_target_kinds)!r}, events: {scoped_events!r}"
    )


# --- vector 2: secret absence --------------------------------------------


def test_c09_v2_no_forbidden_field_key_or_reusable_secret_value_appears(adapter, fx):
    contract = load_contract()
    forbidden_fields = set(contract["audit"]["forbidden_fields"])
    # Identifiers SI-14 itself requires as attribution -- never forbidden,
    # even though some (actor_id) are literally credential ids (design
    # §8.1 vector 2 / review m-1).
    identifier_fields = {"actor_id", "target_id", "application_id", "request_id", "event_id"}

    control_actor = adapter.control_credential()
    form, outcome = _dispatch_audit_query(adapter, control_actor, {"limit": 1})
    if form == "surface_absent":
        return
    if form == "denied":
        raise AssertionError(
            f"{adapter.name}: control_credential() was refused on audit_query with {outcome.code!r}"
        )

    # PROVIDED. Issue the application credential AFTER the branch probe
    # (never before -- issuing one on every SurfaceAbsent adapter would be
    # wasted setup) and wait `audit_visibility_lag_ms()` (never a fixed
    # sleep) before querying again: review F-5 -- without this wait, the
    # issuance event this test's own strongest assertion depends on (a
    # just-issued REAL secret never appears verbatim) could still be
    # sitting outside visibility, silently degrading that assertion to
    # scanning only pre-existing events.
    application_credential = adapter.issue_credential(fx.app_a, "runtime")
    time.sleep(adapter.audit_visibility_lag_ms() / 1000)
    result = _walk_audit_events(adapter, control_actor)

    events = result["events"]
    for event in events:
        assert isinstance(event, Mapping), f"{adapter.name}: audit_query event is not a mapping: {event!r}"
        for key, value in event.items():
            assert key not in forbidden_fields, (
                f"{adapter.name}: audit_query event carries forbidden_fields key {key!r} (SI-10) -- {event!r}"
            )
            if key in identifier_fields or not isinstance(value, str):
                continue
            assert value != control_actor.secret, (
                f"{adapter.name}: audit_query event field {key!r} carries the control actor's own credential "
                "secret verbatim"
            )
            assert value != application_credential.secret, (
                f"{adapter.name}: audit_query event field {key!r} carries a real application credential "
                "secret verbatim"
            )
            lowered = value.lower()
            for sql_fragment in ("select ", "insert into", "drop table", "delete from", "update "):
                assert sql_fragment not in lowered, (
                    f"{adapter.name}: audit_query event field {key!r} looks like SQL text: {value!r}"
                )


# --- vector 3: authority separation --------------------------------------


def test_c09_v3_application_credential_is_forbidden_on_the_control_host_audit_query(adapter, fx):
    application_credential = adapter.issue_credential(fx.app_a, "runtime")
    form, outcome = _dispatch_audit_query(adapter, application_credential, {"limit": 1})
    if form == "surface_absent":
        # Declare-first: audit_query is not provided at all, so no actor
        # -- application credential included -- ever reaches a real
        # authority check here. This is the only reachable branch as of
        # WP-1 for every currently-registered adapter.
        return
    assert form == "denied", (
        f"{adapter.name}: an application credential's audit_query request unexpectedly succeeded "
        f"(PROVIDED) -- application credentials must be denied per contract endpoints.audit_query."
        f"semantics / control_endpoints.audit_query.semantics"
    )
    assert outcome.code == "FORBIDDEN", (
        f"{adapter.name}: an application credential's audit_query request was denied with "
        f"{outcome.code!r}, expected FORBIDDEN"
    )


# --- vector 4: no mutation/deletion surface ------------------------------


def _assert_port_abc_has_no_audit_mutation_surface() -> None:
    """Structural, port-wide check (adapter-independent): `audit_query` is
    the ONLY audit-shaped operation the `ConformanceAdapter` ABC declares
    at all, and it is read-only by construction. Necessary but NOT
    sufficient on its own (audit packet finding, completion condition 8):
    a mutating surface the PORT never exposes could still exist on the
    real PEER underneath it, unreachable through this port and therefore
    invisible to this check alone -- `test_c09_v4_no_audit_mutation_or_
    deletion_surface_exists` (below) additionally observes each real,
    registered peer, per adapter, and this structural check is never the
    sole basis for that test's own green.
    """
    audit_shaped_methods = [name for name in vars(ConformanceAdapter) if "audit" in name.lower()]
    assert audit_shaped_methods, "introspection found zero audit-shaped methods on ConformanceAdapter -- scanner assumption changed"
    mutating_fragments = ("delete", "mutate", "update", "author", "revise", "edit", "write", "insert")
    offending = [
        name for name in audit_shaped_methods
        if any(fragment in name.lower() for fragment in mutating_fragments)
    ]
    assert not offending, (
        f"ConformanceAdapter declares audit-shaped method(s) with a mutating-looking name: {offending!r} -- "
        "the common port itself must never expose an authoring/deletion surface for audit evidence "
        "(contract audit.immutability)"
    )
    params = set(inspect.signature(ConformanceAdapter.audit_query).parameters)
    assert "destructive" not in params and "confirmation" not in params, (
        f"ConformanceAdapter.audit_query carries a destructive/confirmation parameter ({params!r}) -- "
        "audit_query is a read-only operation and must never grow the destructive-confirmation vocabulary"
    )


# Fragments a real audit-mutation surface's name would plausibly contain
# (audit packet's own instruction) -- checked against BOTH the wire (HTTP
# adapters, as HTTP verbs) and real Python objects (in-process adapters,
# as public method names), never against the port ABC alone.
_MUTATING_HTTP_METHODS = ("DELETE", "PUT", "PATCH")
_MUTATING_NAME_FRAGMENTS = ("delete", "purge", "truncate", "clear", "remove")


def _assert_wire_verb_rejected(adapter, control_actor, method: str, path: str) -> None:
    """Sends a REAL `method` request to `path` against the CONTROL host
    (never the data-plane host), using this adapter's own private
    `_control_send` (the same helper every in-band port method on this
    concrete HTTP adapter already uses -- reused here, not reimplemented,
    so this probe's auth-header construction never drifts from the
    adapter's own real one). This is NOT gated behind `audit_query`'s own
    declare-first check (audit packet instruction): declare-first governs
    the `audit_query` POST specifically (port v1.8 §18.2); the absence of
    a MUTATING verb on this path is a structural fact independent of
    whether `audit_query` itself is declared available, and remains
    observable either way.

    `_control_send` raises `ConformanceDenial` for ANY non-2xx response
    (a genuine classified contract code, or `UNCLASSIFIED` for a bare
    404/405 Starlette routing rejection -- both are an honest "this verb/
    route does not exist or is refused" answer here, unlike `audit_query`
    POST's OWN truthfulness test, which rejects `UNCLASSIFIED` because
    THAT path declares itself `enabled`). A 2xx success is the only
    disqualifying outcome.
    """
    try:
        result = adapter._control_send(method, path, control_actor)  # noqa: SLF001
    except ConformanceDenial:
        return
    raise AssertionError(
        f"{adapter.name}: {method} {path} against the control host succeeded ({result!r}) instead of being "
        "rejected -- a mutating verb against the audit surface must never succeed (contract audit.immutability)"
    )


def test_c09_v4_no_audit_mutation_or_deletion_surface_exists(adapter):
    """Declared scope, fixed by supervisor ruling P4-D18 (2026-09-03,
    `docs/design/PHASE4_DURABLE_AUDIT_SINK_V1.md` §5.1 / §11.1 L4-8; the
    same disposition (P4-D18 by name, and that it DEFERS rather than
    closes the ledger item) is condensed onto the C-09 row of
    `CONDITIONS.md`, with the verbatim ruling text kept in
    `CONDITIONS_HISTORY.md#c-09` -- keep the disposition in agreement,
    not the wording). What this vector guarantees adapter-independently is
    a STRUCTURAL property of the common port itself (the ABC check above);
    what it adds per adapter -- real wire verbs on both audit paths, or
    introspection of the real audit objects an in-process adapter reads --
    reaches only the surface an adapter can see. Neither half reaches a
    peer's audit-mutation surface at the DATABASE level: that absence is
    guaranteed by GRANTs (application-plane writer INSERT-only on
    `application_audit`, audit reader SELECT-only on both audit tables)
    and is pinned over bare connections by each peer's OWN suite, not
    here. P4-D18 therefore leaves this vector as it is with that scope
    stated -- rebuilding it into a peer-observing form would yield no new
    safety outcome -- rather than closing the ledger item.
    """
    _assert_port_abc_has_no_audit_mutation_surface()

    if hasattr(adapter, "_control_send"):
        # HTTP-shaped adapter (`r2db-api-http`/`MitateDB-api-http`): real
        # wire probes against BOTH the canonical control_endpoints path
        # and the endpoints.audit_query alias (contract 1.4.0 item 7),
        # both against the control host.
        control_actor = adapter.control_credential()
        for path in ("/v1/audit/query", "/control/v1/audit/query"):
            for method in _MUTATING_HTTP_METHODS:
                _assert_wire_verb_rejected(adapter, control_actor, method, path)
        return

    # In-process adapter (`r2db-api`/`MitateDB-api`): introspects the REAL
    # objects `control_audit_events()` itself reads (the durable-sink
    # facade and the control-plane service facade `audit_query`'s own
    # PROVIDED branch would delegate to) -- never the port ABC again.
    audit_objects = [
        obj for obj in (getattr(adapter, "_control_audit", None), getattr(adapter, "_control_service", None))
        if obj is not None
    ]
    assert audit_objects, (
        f"{adapter.name}: neither _control_audit nor _control_service is reachable on this adapter -- "
        "the introspection target list is stale (this adapter's own internal attribute names changed)"
    )
    offending = []
    for obj in audit_objects:
        cls = type(obj)
        for name, member in vars(cls).items():
            if name.startswith("_") or not inspect.isfunction(member):
                continue
            if any(fragment in name.lower() for fragment in _MUTATING_NAME_FRAGMENTS):
                offending.append(f"{cls.__qualname__}.{name}")
    assert not offending, (
        f"{adapter.name}: a real audit-relevant object reachable from this adapter (the same sink/service "
        f"control_audit_events() itself reads) exposes mutating-looking public callable(s): {offending!r} -- "
        "contract audit.immutability"
    )


# --- declaration agreement (宣言整合): returned events ⊆ declared vocabulary ---
#
# Phase 5 WP-1 (design docs/design/PHASE5_CONTRACT_150_AND_LIMIT_RANGE_V1.md
# §6.1, work order docs/work-orders/WORK_ORDER_PHASE5_CONTRACT_150_V1.md
# WP-1 §4): the common suite's first machine check that EVERY event
# `audit_query` actually returns carries a value that is a member of this
# peer's OWN declared vocabulary for that field -- not merely that a NEW
# event correlates with one after a specific probe (vector 1's own,
# narrower, scoping). Three same-shaped vectors, one per field:
# `event_class` (1.4.0 conditional obligation (4), CCR_DISPOSITION.md
# subordinate ruling 9 item 4) and `operation`/`target_kind` (1.5.0
# conditional obligation, subordinate ruling 10 item 1 -- vacuous until a
# peer declares 1.5.0, work order WP-1 completion condition 9).
#
# Fix-round U-1 (2nd independent audit): the prior revision of these 3
# vectors queried `audit_query` once, unconditionally, and treated an
# EMPTY `events` list as vacuously passing its own subset check -- a real
# non-vacuity gap the audit's mutation (vi) exposed: on the two HTTP-
# shaped plugs, `audit_query`'s real control-audit trail happened to be
# empty at the point in the session these tests ran, so the subset check
# never had anything to check and the vector was silently vacuous for
# HALF the registry, not "load-bearing on all 4" as previously claimed.
# Each vector below now (a) generates a KNOWN durable event via a real
# in-band `register_application_inband` call (`application_lifecycle`
# class -- durable by construction on both peers' control planes, no
# coalescing there, confirmed by source: r2db-api's
# `control_plane.py::ControlPlaneService.register_application` and
# MitateDB-api's `control_plane.py`'s own `register_application` both
# emit `event_class="application_lifecycle"`/`operation=
# "register_application"`/`target_kind="application"` -- so this probe
# needs no data-plane fixture at all, unlike vector 1's own destructive-
# delete probe), (b) polls `audit_query` for up to `audit_visibility_
# lag_ms() + 2000`ms (capped at 30000ms total) until at least one event
# comes back -- never a fixed sleep, (c) asserts the result is genuinely
# non-empty BEFORE running the subset check (a real, asserted
# precondition, not an implicit hope). Mutation-verified (see docstrings
# below): dropping the probe's own `application_lifecycle` class from a
# peer's declared vocabulary now turns ALL FOUR of that peer's plugs red
# (not only the in-process one).
#
# What this half does NOT reach (disclosed, `CONDITIONS.md`'s C-09 row):
# the REVERSE direction -- a declared vocabulary member the peer's real
# emit sites never actually produce -- is not machine-checked here; that
# half is carried by each peer's own local AST equality (`U == D ∪ N`).


def _assert_returned_field_subset_of_declaration(
    adapter, field: str, declared: frozenset[str], events: Sequence[Mapping[str, Any]]
) -> None:
    """Shared shape for the 3 declaration-agreement vectors. Fix-round F-6:
    strict reading of the contract's own finalized wording ("every event
    it returns MUST carry values drawn from the declared sets",
    `versioning.version_binding`'s 1.5.0 paragraph) -- a MISSING/`None`
    `field`, or a non-`Mapping` event, is itself a violation, not merely a
    value present but outside the declared set. Every currently-registered
    peer's real emit sites always set `operation`/`target_kind`/
    `event_class` explicitly (never omitted), so this strict reading is
    not expected to be vacuous-by-omission in practice."""
    offending = [
        event for event in events
        if not isinstance(event, Mapping) or event.get(field) is None or event[field] not in declared
    ]
    assert not offending, (
        f"{adapter.name}: {len(offending)} audit_query event(s) do not carry a {field!r} value drawn from this "
        f"peer's own declared vocabulary {sorted(declared)!r}: {offending!r}"
    )


def _require_nonvacuous_provided(adapter, control_actor, request: Mapping[str, Any]) -> Mapping[str, Any]:
    """Fix-round U-1: generates a KNOWN durable event (a real in-band
    `register_application_inband` call -- `application_lifecycle` class,
    durable by construction on both planes, no data-plane fixture needed),
    then polls `audit_query` for up to `audit_visibility_lag_ms() + 2000`ms
    (capped at 30000ms total) until it returns at least one event, and
    asserts that non-emptiness as a REQUIRED precondition -- never a
    silent vacuous pass. The probe application is deprovisioned afterward
    (test-harness-only cleanup; the durable audit row it already produced
    is immutable and unaffected -- contract `audit.immutability`)."""
    probe_app_id = fresh_identifier("c09decl")
    adapter.register_application_inband(control_actor, probe_app_id)
    try:
        deadline_ms = min(adapter.audit_visibility_lag_ms() + 2000, 30000)
        waited_ms = 0
        poll_interval_s = 0.25
        result: Mapping[str, Any] = {"events": []}
        while True:
            result = _require_provided(adapter, control_actor, request)
            if result.get("events"):
                result = _walk_audit_events(adapter, control_actor, int(request.get("limit", 1000)))
                break
            if waited_ms >= deadline_ms:
                break
            time.sleep(poll_interval_s)
            waited_ms += int(poll_interval_s * 1000)
    finally:
        adapter.deprovision_application(probe_app_id)
    events = result.get("events") or []
    assert events, (
        f"{adapter.name}: audit_query returned zero events after polling for {waited_ms}ms (deadline "
        f"{deadline_ms}ms) following a real register_application_inband probe of {probe_app_id!r} -- this "
        "vector requires at least one real event to check a non-vacuous subset relation against, and must "
        "never silently pass on an empty result"
    )
    return result


def test_c09_declaration_agreement_event_class(adapter):
    """1.4.0 conditional obligation (4) (CCR_DISPOSITION.md subordinate
    ruling 9 item 4) already requires a declared `event_classes`
    vocabulary; this is the common suite's own first check that every
    RETURNED event obeys it -- previously only each peer's own peer-local
    AST scan (`test_declared_audit_event_classes_change_only_
    deliberately`-adjacent machinery) checked this, never the common
    suite.

    Fix-round F-1 / U-1 (corrected claim, 2nd independent audit): this
    vector is red only for the event_class VALUES actually observed among
    the events `audit_query` returns during this test -- it is NOT a
    fixed-point check of a peer's ENTIRE declared vocabulary (that stays
    the job of each peer's own peer-local (e) equality and declared-
    vocabulary snapshot test). As of this fix round, the observed set is
    GUARANTEED non-empty and known to include at least `application_
    lifecycle` on all four currently-registered adapters (`_require_
    nonvacuous_provided`'s own real in-band `register_application_inband`
    probe, above, always causes this class to be emitted and observed
    before the subset check runs -- fix-round U-1; before that fix, two
    of the four adapters' own real control-audit trail happened to be
    empty at the point in the session this vector ran, so this vector
    was silently vacuous on those two plugs).
    Mutation-verified: dropping `application_lifecycle` -- the class the
    probe above actually causes to be emitted -- from a peer's own
    declared `event_classes` turns this red on ALL FOUR of that peer's
    plugs (both in-process and HTTP-shaped), not only the in-process one.
    """
    contract_version, status = _audit_query_declaration(adapter)
    if _semver_tuple(contract_version) < (1, 4, 0) or status not in ("enabled", "partial"):
        return
    control_actor = adapter.control_credential()
    result = _require_nonvacuous_provided(adapter, control_actor, {"limit": 1000})
    document = adapter.control_capabilities(control_actor)
    declared = _declared_audit_vocabulary(document, "event_classes")
    _assert_returned_field_subset_of_declaration(adapter, "event_class", declared, result["events"])


def test_c09_declaration_agreement_operation(adapter):
    """1.5.0 conditional obligation (D-1, CCR_DISPOSITION.md subordinate
    ruling 10 item 1). Vacuous until a peer declares 1.5.0 with
    `audit_query` enabled/partial (no adapter does as of phase 5 WP-1 --
    peer flips land in WP-2/WP-3). Fix-round U-1: kept in the SAME
    non-vacuous-probe skeleton as `test_c09_declaration_agreement_event_
    class` above (`_require_nonvacuous_provided`), even though the version
    gate makes it currently unreachable -- so the shape is already correct
    for WP-2/WP-3's own flip, not a retrofit deferred to that WP."""
    contract_version, status = _audit_query_declaration(adapter)
    if _semver_tuple(contract_version) < (1, 5, 0) or status not in ("enabled", "partial"):
        return
    control_actor = adapter.control_credential()
    result = _require_nonvacuous_provided(adapter, control_actor, {"limit": 1000})
    document = adapter.control_capabilities(control_actor)
    declared = _declared_audit_vocabulary(document, "operations")
    _assert_returned_field_subset_of_declaration(adapter, "operation", declared, result["events"])


def test_c09_declaration_agreement_target_kind(adapter):
    """1.5.0 conditional obligation (D-1, CCR_DISPOSITION.md subordinate
    ruling 10 item 1). Vacuous until a peer declares 1.5.0 with
    `audit_query` enabled/partial (no adapter does as of phase 5 WP-1 --
    peer flips land in WP-2/WP-3). Fix-round U-1: same non-vacuous-probe
    skeleton as the other two declaration-agreement vectors above."""
    contract_version, status = _audit_query_declaration(adapter)
    if _semver_tuple(contract_version) < (1, 5, 0) or status not in ("enabled", "partial"):
        return
    control_actor = adapter.control_credential()
    result = _require_nonvacuous_provided(adapter, control_actor, {"limit": 1000})
    document = adapter.control_capabilities(control_actor)
    declared = _declared_audit_vocabulary(document, "target_kinds")
    _assert_returned_field_subset_of_declaration(adapter, "target_kind", declared, result["events"])


# --- unconditional obligation (b), same-label addendum: data-plane host --


def test_c09_data_plane_host_audit_query_alias_rejects_control_credential_unless_cohosted(adapter):
    """Contract 1.4.0's unconditional obligation (b), same-label-addended
    by CCR_DISPOSITION.md subordinate ruling 10 item 2 (design docs/
    design/PHASE5_CONTRACT_150_AND_LIMIT_RANGE_V1.md §3 D-2). Registered
    `xfail`-free (work order WP-1 completion condition 10) -- this is an
    UNCONDITIONAL obligation, unlike every other vector in this file that
    branches on `contract_version`/`audit_query` status: both currently-
    registered peers already declare 1.4.0 and are already conformant.

    Fix-round F-2/F-3: dispatch is judged against this deployment's OWN
    declared topology fact -- never against a live cross-check of
    returned event content (the prior revision's "overlap with a real
    control-host query" mechanism is REMOVED: it could not distinguish a
    genuinely co-hosted acceptance from one that happened to overlap by
    coincidence, and inspected response CONTENT rather than the
    deployment's own declared TOPOLOGY, the property this obligation is
    actually about).

    **Port v1.10 (phase 6 WP-1, design docs/design/
    PHASE6_CONTRACT_160_CLIENT_DISCOVERY_V1.md §6.1 item 2, D-2,
    `docs/design/CONFORMANCE_ADAPTER_V1.md` §20.3)**: the topology fact
    itself comes from `adapter.surfaces_cohosted(adapter.capability_
    document())` -- a 1.6.0+ peer's own declared `surfaces.data`/
    `surfaces.control` origins. Phase 6 WP-3 追補 (supervisor ruling
    2026-09-04, brief item D): the pre-1.6.0 topology-declaration
    fallback this call site originally also passed (the WP-1 port
    revision's own second argument, since removed along with the adapter
    method that provided it) is gone -- both peers now declare 1.6.0
    unconditionally, so `surfaces_cohosted` is surfaces-derived only. The
    OBSERVED OUTCOME is unchanged (every currently-registered adapter's
    `data`/`control` `surfaces` origins still resolve to `False` here,
    the same value the removed fallback always returned -- work order
    WP-1 completion condition 11's own "置換が挙動を変えないことの実測",
    now load-bearing against the fallback's removal rather than its
    introduction).

    - `provided`: conformant ONLY when `surfaces_cohosted(...)` resolves
      `True` (a deployment that co-hosts both surfaces, `versioning.
      control_discovery`'s own "convenience, not a requirement"). Under a
      NON-cohosted resolution (every currently-registered adapter today),
      `provided` is RED -- this is what catches a port-level identity
      mistake, e.g. an implementation that accidentally forwards to
      `audit_query`'s own control-host call instead of genuinely
      presenting to the data host (mutation-verified below: `return
      self.audit_query(actor, request)` in place of a real data-host call
      turns this red on both r2db plugs).
    - `denied`: must be EXACTLY `AUTH_INVALID` (this deployment's data
      host holds no control-credential store) regardless of the cohosted
      resolution -- a cohosted deployment MAY still keep separate stores.
      `CAPABILITY_UNSUPPORTED`/`FORBIDDEN`/any other denial code is
      non-conformant either way.
    """
    # Phase 6 WP-3 追補 (supervisor ruling 2026-09-04, brief item D): the
    # pre-1.6.0 `fallback=adapter.control_surface_cohosted_with_data_
    # plane` argument is removed alongside that now-deleted port method --
    # `surfaces_cohosted` is surfaces-derived only, both peers declaring
    # 1.6.0 unconditionally.
    cohosted = surfaces_cohosted(adapter.capability_document())
    control_actor = adapter.control_credential()
    form, outcome = _dispatch_audit_query_on_data_plane_host(adapter, control_actor, {"limit": 1})
    if form == "surface_absent":
        return
    if form == "provided":
        assert cohosted, (
            f"{adapter.name}: audit_query_on_data_plane_host returned PROVIDED, but surfaces_cohosted(...) "
            "resolves False -- a non-cohosted deployment's data-plane host must never answer a control/audit "
            "credential (a PROVIDED outcome is conformant only when the deployment's own declared topology "
            "says both surfaces are genuinely co-hosted)"
        )
        return
    _require_denied_with(adapter, form, outcome, "AUTH_INVALID")


# ---------------------------------------------------------------------------
# Phase 6 WP-3 追補 (mutation-testing finding, supervisor ruling 2026-09-04):
# work order §4 WP-3 完了条件20 ("申告メソッドの消滅... 判定が実際に使われ
# ていることの実測") names `test_c09_audit_evidence_on_data_plane_host`
# above as the vector that should turn red if `adapter.surfaces_cohosted`
# is broken (e.g. mutated to unconditionally return `True`). Empirically,
# it does NOT: every currently-registered adapter's own data-plane host
# genuinely never answers a control/audit request (`form` is always
# "denied", never "provided"), so the `assert cohosted` branch above
# (only reached when `form == "provided"`) is structurally UNREACHABLE
# for the whole current registry -- a fail-OPEN mutation of `surfaces_
# cohosted` (always `True`) passes the full suite unnoticed (measured).
# This is a real gap, not a product-code defect: `surfaces_cohosted`
# itself was never directly unit-tested anywhere (grep across this
# repository, confirmed before adding this test). The test below closes
# it directly, with synthetic `CapabilityDocument`-shaped dicts, needing
# no adapter/dispatch machinery at all -- it observes `surfaces_cohosted`
# itself, not an indirect, currently-unreachable consequence of it.
# Product code is untouched.
# ---------------------------------------------------------------------------


def test_surfaces_cohosted_resolves_true_only_for_matching_origins_and_false_otherwise() -> None:
    """Direct unit coverage of `adapter.surfaces_cohosted` (port v1.10,
    design section 6.1 item 2) -- same-origin data/control base URLs
    resolve `True`; differing host, differing port, a pre-1.6.0
    `contract_version`, and a missing `surfaces`/`surfaces.control` each
    resolve `False`. Path is deliberately irrelevant to the origin
    comparison (`/v1` vs `/control/v1` on the SAME host:port still
    co-hosted)."""
    same_origin = {
        "contract_version": "1.6.0",
        "surfaces": {
            "data": {"base_url": "https://mtdb.example.invalid:8443/v1"},
            "control": {"base_url": "https://mtdb.example.invalid:8443/control/v1"},
        },
    }
    assert surfaces_cohosted(same_origin) is True

    different_host = {
        "contract_version": "1.6.0",
        "surfaces": {
            "data": {"base_url": "https://data.example.invalid/v1"},
            "control": {"base_url": "https://control.example.invalid/control/v1"},
        },
    }
    assert surfaces_cohosted(different_host) is False

    different_port = {
        "contract_version": "1.6.0",
        "surfaces": {
            "data": {"base_url": "https://mtdb.example.invalid:8443/v1"},
            "control": {"base_url": "https://mtdb.example.invalid:9443/control/v1"},
        },
    }
    assert surfaces_cohosted(different_port) is False

    pre_1_6_0 = {
        "contract_version": "1.5.0",
        "surfaces": same_origin["surfaces"],
    }
    assert surfaces_cohosted(pre_1_6_0) is False

    no_surfaces = {"contract_version": "1.6.0"}
    assert surfaces_cohosted(no_surfaces) is False

    control_absent = {
        "contract_version": "1.6.0",
        "surfaces": {"data": same_origin["surfaces"]["data"]},
    }
    assert surfaces_cohosted(control_absent) is False


# --- declaration truthfulness --------------------------------------------


def test_c09_declared_enabled_audit_query_actually_answers(adapter):
    """WP-1 supplementary ruling 1 item 2's own truthfulness requirement:
    an `enabled`/`partial` declaration must mean a real request gets a
    real, classified answer -- a 404/405/unclassified response is exactly
    as much a defect as a `SurfaceAbsent` claim from an adapter that never
    presented the request (design §8.4). Vacuously green as of WP-1: no
    adapter yet declares `audit_query` enabled/partial."""
    _, status = _audit_query_declaration(adapter)
    if status not in ("enabled", "partial"):
        return
    control_actor = adapter.control_credential()
    try:
        result = adapter.audit_query(control_actor, {"limit": 1})
    except ConformanceDenial as exc:
        assert exc.code != UNCLASSIFIED, (
            f"{adapter.name}: declares audit_query {status!r} but a real request answered UNCLASSIFIED "
            "(a 404/405/unrecognized response) instead of a genuine contract-code denial"
        )
        return
    assert isinstance(result, Mapping) and "events" in result


def test_c09_audit_walk_follows_the_cursor_through_every_page(adapter):
    """`_walk_audit_events` reads every page: with pages of half the events
    (so three control requests, well inside a plug's control rate bound) it
    returns every event a page of 1000 returns. A walk that stopped after
    the first page would return half of them and fail here. The platform
    holds at least the two events this test's own probe application's
    register / deprovision produce, so the read is never vacuous."""
    _, status = _audit_query_declaration(adapter)
    if status not in ("enabled", "partial"):
        return
    control_actor = adapter.control_credential()
    probe_app_id = fresh_identifier("c09walk")
    adapter.register_application_inband(control_actor, probe_app_id)
    try:
        time.sleep(adapter.audit_visibility_lag_ms() / 1000)
    finally:
        adapter.deprovision_application(probe_app_id)
    by_thousand = _walk_audit_events(adapter, control_actor, page_limit=1000)["events"]
    assert len(by_thousand) >= 2, (
        f"{adapter.name}: the platform shows {len(by_thousand)} event(s) after this test's own probe "
        "application was registered -- the paged read below would be vacuous"
    )
    page_limit = (len(by_thousand) + 1) // 2
    by_halves = _walk_audit_events(adapter, control_actor, page_limit=page_limit)["events"]
    identities = {_event_identity(event) for event in by_halves}
    assert len(identities) == len(by_halves), f"{adapter.name}: the paged walk returned an event twice"
    assert {_event_identity(event) for event in by_thousand} <= identities, (
        f"{adapter.name}: the walk in pages of {page_limit} missed {len(by_thousand) - len(identities & {_event_identity(e) for e in by_thousand})} "
        f"of the {len(by_thousand)} events a page of 1000 returns"
    )


# --- vacuity guards -------------------------------------------------------


def test_c09_declared_capability_implies_provided_branch(adapter):
    """Individual guard (work order WP-1 supplementary ruling 2). Always
    active -- no `xfail`. Vacuous while no adapter declared
    `contract_version >= 1.4.0`; load-bearing since WP-2(b), and binding on
    all four registered adapters since WP-3(b)."""
    contract_version, status = _audit_query_declaration(adapter)
    if _semver_tuple(contract_version) < (1, 4, 0) or status not in ("enabled", "partial"):
        return
    control_actor = adapter.control_credential()
    form, outcome = _dispatch_audit_query(adapter, control_actor, {"limit": 1})
    assert form == "provided", (
        f"{adapter.name}: declares contract_version {contract_version!r} (>= 1.4.0) and audit_query "
        f"status {status!r}, but a real control-credential audit_query request did not take the PROVIDED "
        f"branch (got {form!r}: {outcome!r})"
    )


def test_c09_every_control_surface_adapter_takes_the_provided_branch():
    """Whole-registry guard (work order WP-1 supplementary ruling 2 /
    supervisor ruling v1.2-1): EVERY registered adapter with a control
    surface (`control_plane` status `enabled`/`partial`) must take the
    PROVIDED audit_query branch -- not "at least one", not "one per
    form". Carried `xfail(strict=True)` from WP-1 through WP-2(b) (false
    until every peer declared 1.4.0 `audit_query: enabled`); WP-3(b) is
    the LAST flip (MitateDB-api's own `contract_version`/`audit_query`
    flip lands in the SAME commit as this `xfail` removal, work order
    §2.1 / §6 item 8b) -- this test now runs un-xfailed and must be
    genuinely green, not merely un-skipped.

    The target set is derived mechanically from the live registry
    (`registered_adapters()` + each adapter's own real `control_plane`
    status), never a hardcoded adapter-name list -- a future peer joining
    the registry with a control surface is picked up automatically rather
    than silently exempted.
    """
    control_surface_adapters: list[str] = []
    non_provided_reasons: list[str] = []
    for name, adapter_obj in registered_adapters().items():
        if _control_plane_status(adapter_obj) not in ("enabled", "partial"):
            continue
        control_surface_adapters.append(name)
        control_actor = adapter_obj.control_credential()
        form, outcome = None, None
        try:
            form, outcome = _dispatch_audit_query(adapter_obj, control_actor, {"limit": 1})
        except AssertionError as exc:
            non_provided_reasons.append(f"{name}: {exc}")
            continue
        if form != "provided":
            non_provided_reasons.append(f"{name}: took the {form!r} branch ({outcome!r})")

    assert control_surface_adapters, (
        "no registered adapter has a control surface at all -- this guard is vacuous by construction, "
        "which is itself a finding (every currently-registered adapter is expected to declare "
        "control_plane enabled as of phase 3.5)"
    )
    assert not non_provided_reasons, (
        "not every control-surface-bearing registered adapter took the PROVIDED audit_query branch: "
        f"{non_provided_reasons!r} (control-surface adapters checked: {control_surface_adapters!r})"
    )


def test_c09_every_control_surface_adapter_declares_1_5_0():
    """Whole-registry guard for D-1 (CCR_DISPOSITION.md subordinate ruling
    10 item 1; work order docs/work-orders/WORK_ORDER_PHASE5_CONTRACT_150_
    V1.md WP-1 §1 D-4). Registered `xfail(strict=True)` in WP-1 -- false
    until every registered adapter with a control surface had flipped to
    `contract_version` 1.5.0. **The `xfail` was removed in WP-3's own flip
    commit** (both r2db-api, WP-2, and MitateDB-api, WP-3, now declare
    1.5.0 on every control-surface-bearing plug), so this guard now runs
    plain and green -- mirrors `test_c09_every_control_surface_adapter_
    takes_the_provided_branch`'s own WP-1 -> WP-3(b) arc exactly, and is
    written in the SAME shape: a non-parametrized function that walks
    `registered_adapters()` itself (never a hardcoded adapter-name list),
    deriving its target set from `control_plane` status, never from
    `audit_query`'s own status (D-1's obligation binds on the DECLARED
    version, independent of whether `audit_query` itself is enabled -- the
    same distinction the whole-registry PROVIDED-branch guard above draws
    between `control_plane` and `audit_query`).
    """
    control_surface_adapters: list[str] = []
    not_1_5_0: list[str] = []
    for name, adapter_obj in registered_adapters().items():
        if _control_plane_status(adapter_obj) not in ("enabled", "partial"):
            continue
        control_surface_adapters.append(name)
        contract_version, _status = _audit_query_declaration(adapter_obj)
        if _semver_tuple(contract_version) < (1, 5, 0):
            not_1_5_0.append(f"{name}: declares {contract_version!r}")

    assert control_surface_adapters, (
        "no registered adapter has a control surface at all -- this guard is vacuous by construction"
    )
    assert not not_1_5_0, (
        f"not every control-surface-bearing registered adapter declares contract_version >= 1.5.0: "
        f"{not_1_5_0!r} (control-surface adapters checked: {control_surface_adapters!r})"
    )
