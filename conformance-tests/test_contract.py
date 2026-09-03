"""Implementation-independent smoke checks for the common machine contract."""
import copy
import json
import re
from pathlib import Path

from schema_check import validate


ROOT = Path(__file__).parents[1]


def test_contract_is_machine_readable_and_has_required_sections():
    contract = json.loads((ROOT / "spec" / "data-service-api.v1.json").read_text())
    for section in ("security", "versioning", "endpoints", "structured_operations", "transactions", "errors", "limits", "lifecycle", "audit"):
        assert section in contract
    assert contract["limits"]["finite_required"] is True
    sql_rule = contract["structured_operations"]["sql"]
    assert sql_rule.startswith("No public operation accepts SQL")
    assert all("sql" not in endpoint["path"].lower() for endpoint in contract["endpoints"].values())
    assert contract["schemas"]["MutationRequest"]["properties"]["operations"]["items"]["$ref"] == "#/definitions/Mutation"
    assert contract["definitions"]["Mutation"]["additionalProperties"] is False
    assert all(value > 0 for value in contract["limits"]["example_profile"].values())


def test_contract_has_separate_control_and_application_authority():
    contract = json.loads((ROOT / "spec" / "data-service-api.v1.json").read_text())
    assert contract["security"]["roles"] == ["runtime", "developer", "control", "audit"]
    assert contract["endpoints"]["audit_query"]["auth"] == "control or audit"
    assert contract["endpoints"]["schema"]["auth"] == "developer"


def test_contract_defines_peer_neutral_capability_status_and_response_shape():
    contract = json.loads((ROOT / "spec" / "data-service-api.v1.json").read_text())
    status = contract["capability_status"]
    assert set(status["status_enum"]) == {"enabled", "partial", "unavailable", "planned"}
    assert "deployment_required" in status["enforcement_enum"]
    capability = contract["schemas"]["CapabilityDocument"]
    assert capability["properties"]["capabilities"]["additionalProperties"]["required"] == ["status"]
    assert capability["properties"]["limit_enforcement"]["additionalProperties"]["enum"] == status["enforcement_enum"]


def test_contract_requires_published_authorization_propagation_bound():
    contract = json.loads((ROOT / "spec" / "data-service-api.v1.json").read_text())
    capability = contract["schemas"]["CapabilityDocument"]
    assert "authorization_propagation_bound_ms" in capability["required"]
    bound_schema = capability["properties"]["authorization_propagation_bound_ms"]
    assert bound_schema["type"] == "integer"
    assert bound_schema["minimum"] == 0
    assert "propagation_bound" in contract["lifecycle"]


def test_contract_states_audit_sink_failure_policy():
    contract = json.loads((ROOT / "spec" / "data-service-api.v1.json").read_text())
    policy = contract["audit"]["sink_failure_policy"]
    assert isinstance(policy, str) and policy
    assert "fails the operation closed" in policy
    assert "bounded buffer" in policy
    assert "explicit operational alert" in policy


def test_all_ccrs_have_disposition_records():
    # CCR ids are discovered from the change-request documents themselves, not
    # hardcoded: a newly raised CCR must not be able to slip past this check
    # merely because nobody remembered to widen a range here.
    requests = sorted((ROOT).glob("*/contracts/COMMON_CONTRACT_CHANGE_REQUEST.md"))
    assert requests, "no common contract change-request document was found"
    raised = set()
    for document in requests:
        raised.update(re.findall(r"CCR-\d{2}", document.read_text()))
    assert len(raised) >= 12
    text = (ROOT / "spec" / "CCR_DISPOSITION.md").read_text()
    missing = sorted(identifier for identifier in raised if identifier not in text)
    assert not missing, f"raised CCRs without a disposition record: {missing}"
    assert "却下・保留となるCCRはない" in text


def test_contract_declares_1_5_0():
    # Phase 5 WP-1 (docs/design/PHASE5_CONTRACT_150_AND_LIMIT_RANGE_V1.md
    # §3 D-1/D-2, CCR_DISPOSITION.md subordinate ruling 10): the version
    # bump itself, pinned so a future revert of just this one line is
    # caught here rather than only by whichever other test happens to
    # touch contract_version. Supersedes the 1.4.0 pin (phase 4 WP-1,
    # subordinate ruling 9) this test itself carried before -- 1.4.0 is
    # already published, so this file never re-adds a standalone
    # "declares 1.4.0" test: any implementation still declaring 1.4.0 or
    # earlier is exercised by version_binding's own retroactivity rule,
    # not by a dedicated pin here for a version this document no longer
    # declares.
    contract = json.loads((ROOT / "spec" / "data-service-api.v1.json").read_text())
    assert contract["contract_version"] == "1.5.0"


def test_contract_audit_fields_include_optional_target_id_and_it_is_not_forbidden():
    # §1-C: target_id is an additive, OPTIONAL member of audit.fields (present
    # only for single-target events), and must not collide with the separate
    # forbidden_fields vocabulary (an identifier, not a secret).
    contract = json.loads((ROOT / "spec" / "data-service-api.v1.json").read_text())
    audit = contract["audit"]
    assert "target_id" in audit["fields"]
    assert "target_id" not in audit["forbidden_fields"]


def test_credentials_result_with_must_rotate_is_invalid_under_1_2_0_shape_valid_under_1_3_0():
    """Positive control for §1-B/§1-G (design doc's own m-1 correction):
    an additive-only contract change can never make a previously-VALID
    instance invalid (the accepted set only grows), so the meaningful
    regression check runs the other direction -- a `CredentialsResult` row
    carrying the NEW `must_rotate` field must be REJECTED by the 1.2.0-era
    closed schema shape (`additionalProperties: false` with no `must_rotate`
    property) and ACCEPTED by the current (1.3.0) schema.

    The 1.2.0-shape half is not read from git history (there is no repo
    convention for checking out a prior contract revision inside this
    suite); instead it is reconstructed by deep-copying the CURRENT
    `CredentialsResult` schema and deleting the `must_rotate` property this
    WP just added. This reconstruction is exact for this one property
    because `must_rotate` is the only 1.3.0 change to `CredentialsResult`'s
    row schema (§1 lists no other edit to this schema) -- removing it
    recovers the 1.2.0 closure being tested against.
    """
    contract = json.loads((ROOT / "spec" / "data-service-api.v1.json").read_text())
    current_row_schema = contract["schemas"]["CredentialsResult"]["properties"]["credentials"]["items"]

    legacy_row_schema = copy.deepcopy(current_row_schema)
    assert "must_rotate" in legacy_row_schema["properties"], (
        "CredentialsResult.credentials[] no longer declares must_rotate -- this reconstruction "
        "of the 1.2.0-era shape (current schema minus must_rotate) is no longer meaningful"
    )
    del legacy_row_schema["properties"]["must_rotate"]

    row_with_must_rotate = {
        "credential_id": "c1", "role": "control", "enabled": True, "revoked": False,
        "must_rotate": True,
    }

    legacy_violations = validate(row_with_must_rotate, legacy_row_schema, contract)
    assert legacy_violations, (
        "a CredentialsResult row carrying must_rotate must be rejected by the reconstructed "
        "1.2.0-era schema (additionalProperties: false, no must_rotate property) -- got no violations"
    )

    current_violations = validate(row_with_must_rotate, current_row_schema, contract)
    assert not current_violations, (
        f"a CredentialsResult row carrying must_rotate must be accepted by the current (1.3.0) "
        f"schema -- got violations: {current_violations}"
    )

    # must_rotate stays optional: a row omitting it entirely remains valid too
    # (application credentials, where the concept does not exist -- §1-B).
    row_without_must_rotate = {"credential_id": "c2", "role": "runtime", "enabled": True, "revoked": False}
    assert not validate(row_without_must_rotate, current_row_schema, contract)


def test_control_endpoint_audit_role_acceptance_matches_1_3_0_declaration():
    # Independent-review M-2 (i): §1-D's auth flip has no other regression pin
    # -- a future accidental revert of just these three "auth" values (or a
    # widening of issue_credential's) would otherwise go unnoticed by any
    # other test in this suite.
    contract = json.loads((ROOT / "spec" / "data-service-api.v1.json").read_text())
    control_endpoints = contract["control_endpoints"]
    assert control_endpoints["control_capabilities"]["auth"] == "control or audit"
    assert control_endpoints["list_applications"]["auth"] == "control or audit"
    assert control_endpoints["list_credentials"]["auth"] == "control or audit"
    # Every other control endpoint -- issue_credential included -- stays
    # control-only; audit role is not granted anywhere beyond the three
    # read-only endpoints above.
    assert control_endpoints["issue_credential"]["auth"] == "control"


def test_contract_1_3_0_prose_pins():
    # Independent-review M-2 (ii): substring pins for §1 A/D/E/F, following
    # this file's existing style (see test_contract_has_separate_control_and_
    # application_authority's exact-match pin at :29 and test_contract_states_
    # audit_sink_failure_policy's substring pins at :57-59) -- each of these
    # sentences currently has no dedicated regression test of its own.
    contract = json.loads((ROOT / "spec" / "data-service-api.v1.json").read_text())

    # §1-A: batch_entities bounds DISTINCT entity names, not operation count.
    cross_entity_semantics = contract["endpoints"]["cross_entity_mutate"]["semantics"]
    assert "distinct entity names" in cross_entity_semantics

    # §1-E: per-application issuance freeze refusal code.
    issue_credential_semantics = contract["control_endpoints"]["issue_credential"]["semantics"]
    assert "frozen application is refused with FORBIDDEN" in issue_credential_semantics

    # §1-F: atomic_mutation's operations vocabulary clarification.
    atomic_mutation = contract["capability_status"]["defined"]["atomic_mutation"]
    assert "the mutation vocabulary the batch execution surface executes" in atomic_mutation

    # §1-D: audit role is fail-closed (FORBIDDEN) on every control endpoint
    # other than the three read-only ones.
    authority = contract["control_plane"]["authority"]
    assert "fails it closed with FORBIDDEN" in authority


# ---------------------------------------------------------------------------
# Phase 4 WP-1 (docs/design/PHASE4_DURABLE_AUDIT_SINK_V1.md §5 P4-D4,
# CCR_DISPOSITION.md subordinate ruling 9): positive controls for each of
# the 8 contract 1.4.0 items, per this WP's own completion condition 3 --
# "8件の各項目に対応する契約文言が存在することを、契約文書を読む positive
# control で固定する". Each test below pins the SPECIFIC prose/shape a
# future accidental revert of just that one item would otherwise leave
# undetected by any other test in this suite (mirrors this file's own
# existing style, e.g. test_contract_1_3_0_prose_pins above).
# ---------------------------------------------------------------------------


def test_audit_query_after_is_an_opaque_cursor():
    # item 1: AuditQueryRequest.after's opaque-cursor semantics.
    contract = json.loads((ROOT / "spec" / "data-service-api.v1.json").read_text())
    cursor_note = contract["audit"]["query_cursor"]
    assert "opaque cursor" in cursor_note
    assert "VALIDATION_FAILED" in cursor_note
    # The schema shape itself is unchanged by this item (after was already
    # a bare string) -- the opaque-cursor reading is a semantics
    # clarification, not a new property, so AuditQueryRequest.after stays a
    # plain string in the schema.
    after_schema = contract["schemas"]["AuditQueryRequest"]["properties"]["after"]
    assert after_schema == {"type": "string"}


def test_audit_result_event_carries_plane_and_cursor():
    # items 2 and 3: total order (recorded_at, plane, event_id) and the
    # plane field addition -- both documented in audit.query_ordering /
    # audit.query_event_fields_note. AuditResult.events[] itself needs no
    # schema edit (subordinate ruling 7(A) already left it open), which
    # this test also pins: adding plane/recorded_at/cursor/count to a real
    # event must not need, and must not have received, a property list.
    contract = json.loads((ROOT / "spec" / "data-service-api.v1.json").read_text())
    ordering_note = contract["audit"]["query_ordering"]
    assert "(recorded_at, plane, event_id)" in ordering_note
    fields_note = contract["audit"]["query_event_fields_note"]
    for token in ("plane", "recorded_at", "cursor", "count"):
        assert token in fields_note, f"audit.query_event_fields_note does not mention {token!r}"
    event_item_schema = contract["schemas"]["AuditResult"]["properties"]["events"]["items"]
    assert "properties" not in event_item_schema, (
        "AuditResult.events[] item schema gained a fixed properties list -- subordinate ruling 7(A) "
        "deliberately left this shape open (audit.fields is itself an additive vocabulary); plane/"
        "recorded_at/cursor/count must remain documented prose, not a schema-enforced property set"
    )


def test_event_class_is_a_declared_vocabulary():
    # item 4: event_class is a per-implementation declared vocabulary, not
    # a fixed contract enum -- and no schema in this document defines one.
    contract = json.loads((ROOT / "spec" / "data-service-api.v1.json").read_text())
    vocabulary_note = contract["audit"]["query_event_class_vocabulary"]
    assert "does not enumerate a fixed event_class enum" in vocabulary_note
    assert "audit_query.event_classes" in vocabulary_note
    # AuditQueryRequest.event_classes stays a bare, unconstrained array (no
    # enum) -- this item is a documentation clarification, never a schema
    # closure against a fixed value set.
    event_classes_schema = contract["schemas"]["AuditQueryRequest"]["properties"]["event_classes"]
    assert "enum" not in json.dumps(event_classes_schema)


def test_audit_role_is_accepted_on_audit_query():
    # item 5: audit-role acceptance on audit_query, integrated into the
    # same control_plane.authority sentence subordinate ruling 8 already
    # extended for the three read-only endpoints -- so this pin exercises
    # the UPDATED sentence, not a new, separate one.
    contract = json.loads((ROOT / "spec" / "data-service-api.v1.json").read_text())
    authority = contract["control_plane"]["authority"]
    assert "audit_query" in authority
    assert "control_capabilities, list_applications, list_credentials, and" in authority
    # control_endpoints.audit_query itself also declares the widened auth.
    assert contract["control_endpoints"]["audit_query"]["auth"] == "control or audit"


def test_audit_events_is_a_documented_reserved_name():
    # item 6: the audit_events reserved collection/entity name, previously
    # an undocumented implementation-only reservation (both MitateDB
    # backends), now documented in structured_operations.
    contract = json.loads((ROOT / "spec" / "data-service-api.v1.json").read_text())
    assert "audit_events" in contract["structured_operations"]["reserved_entity_names"]
    note = contract["structured_operations"]["reserved_entity_names_note"]
    assert "audit_events" in note


def test_audit_query_endpoint_classification_moved_to_control_endpoints_with_an_alias():
    # item 7: audit_query's canonical home is now control_endpoints, at
    # /control/v1/audit/query, with endpoints.audit_query (/v1/audit/query)
    # explicitly RETAINED (never deleted -- this contract's own additive-
    # only discipline) as a one-minor-version alias of the identical
    # operation.
    contract = json.loads((ROOT / "spec" / "data-service-api.v1.json").read_text())
    control_audit_query = contract["control_endpoints"]["audit_query"]
    assert control_audit_query["method"] == "POST"
    assert control_audit_query["path"] == "/control/v1/audit/query"
    assert control_audit_query["auth"] == "control or audit"
    assert control_audit_query["request"] == "AuditQueryRequest"
    assert control_audit_query["response"] == "AuditResult"

    # The pre-1.4.0 application-surface entry is untouched in shape and
    # still present -- only a deprecation_note is added, never a removal.
    legacy_audit_query = contract["endpoints"]["audit_query"]
    assert legacy_audit_query["path"] == "/v1/audit/query"
    assert legacy_audit_query["method"] == "POST"
    assert legacy_audit_query["request"] == "AuditQueryRequest"
    assert legacy_audit_query["response"] == "AuditResult"
    assert "alias" in legacy_audit_query["deprecation_note"]
    assert "one further minor version" in legacy_audit_query["deprecation_note"]


def test_audit_requests_per_minute_is_a_declared_limit_class():
    # item 8: a new, separate limits.classes member for audit_query's own
    # pre-auth window, distinct from control_requests_per_minute.
    contract = json.loads((ROOT / "spec" / "data-service-api.v1.json").read_text())
    assert "audit_requests_per_minute" in contract["limits"]["classes"]
    # Every pre-existing class member is still present -- this item only
    # adds a member, it never narrows the vocabulary (additive-only).
    assert "control_requests_per_minute" in contract["limits"]["classes"]
    note = contract["limits"]["audit_requests_per_minute_note"]
    assert "control_requests_per_minute" in note
    assert "separate" in note or "does not also charge" in note


def test_version_binding_1_4_0_obligations_are_conditional_on_providing_audit_query():
    # Completion condition 5: the 1.4.0 version_binding section must read as
    # a CONDITIONAL obligation set for the audit_query-specific items (only
    # binding when that implementation's own audit_query capability is
    # enabled/partial), with an explicit statement that an implementation
    # may declare 1.4.0 while audit_query stays unavailable and remain
    # fully conformant -- never as an unconditional provision requirement
    # (monitor ruling 8: an unconditional reading would mean a deployment
    # with no AUDIT_DSN configured could not honestly declare 1.4.0 at
    # all).
    contract = json.loads((ROOT / "spec" / "data-service-api.v1.json").read_text())
    version_binding = contract["versioning"]["version_binding"]
    assert "1.4.0" in version_binding
    assert "subordinate ruling 9" in version_binding
    assert "conditional" in version_binding
    assert "audit_query as something other than unavailable" in version_binding
    assert "remains fully conformant to 1.4.0" in version_binding
    # The unconditional half is present too -- item 6 (reserved name) and
    # the audit-role/route-registration half of item 5 bind regardless of
    # audit_query's own status.
    assert "unconditional" in version_binding
    assert "audit_events is a reserved entity/collection name" in version_binding


def test_version_binding_1_4_0_unconditional_and_conditional_counts_agree():
    """Review F-2: `version_binding`'s own stated COUNT of unconditional
    1.4.0 obligations ("Two"/"Three"/...) must match how many lettered
    items it actually enumerates immediately after that sentence, and
    `CCR_DISPOSITION.md`'s subordinate ruling 9(b) restatement of the same
    split must agree with the contract, not drift from it independently.

    This is a REGRESSION guard, not merely a positive control: the review
    found this exact drift once already (item 7 was split into an
    unconditional half (c) -- the contract-level classification fact --
    and a conditional half (5) -- the peer actually answering both paths
    -- growing 8 candidate items into 9 markers without the summary count
    word being updated), and `test_version_binding_1_4_0_obligations_are_
    conditional_on_providing_audit_query` above only checks SUBSTRINGS, so
    it could not have caught a count mismatch like this on its own.
    """
    contract = json.loads((ROOT / "spec" / "data-service-api.v1.json").read_text())
    version_binding = contract["versioning"]["version_binding"]

    count_words = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9}
    unconditional_match = re.search(r"(\w+) of those obligations are unconditional", version_binding)
    assert unconditional_match, "version_binding's 1.4.0 unconditional-count sentence was not found verbatim"
    stated_word = unconditional_match.group(1).lower()
    assert stated_word in count_words, f"unrecognized count word {stated_word!r} in version_binding"
    stated_unconditional = count_words[stated_word]

    conditional_marker = "The remaining 1.4.0 obligations are conditional"
    assert conditional_marker in version_binding, f"expected marker sentence {conditional_marker!r} not found"
    unconditional_section = version_binding[unconditional_match.start():version_binding.index(conditional_marker)]
    # Only top-level lettered markers immediately preceded by "; " or ": "
    # or "and " count as list items -- a bare "(a)" appearing inside some
    # OTHER sentence should not inflate the count, though none currently do.
    unconditional_markers = re.findall(r"\((?:a|b|c|d|e|f|g|h|i|j)\)", unconditional_section)
    assert len(unconditional_markers) == len(set(unconditional_markers)), (
        f"unconditional 1.4.0 obligation markers are not each unique: {unconditional_markers!r}"
    )
    assert len(unconditional_markers) == stated_unconditional, (
        f"version_binding says {unconditional_match.group(1)!r} ({stated_unconditional}) unconditional 1.4.0 "
        f"obligations but its own list enumerates {len(unconditional_markers)}: {unconditional_markers!r}"
    )

    requires_marker = "1.4.0 additionally requires"
    assert requires_marker in version_binding, f"expected marker phrase {requires_marker!r} not found"
    conditional_section = version_binding[version_binding.index(requires_marker):]
    # Only a "(N)" immediately preceded by a list separator (": ", "; ", or
    # "and ") counts as a real list-item marker -- item (1)'s own body text
    # contains a forward cross-reference ("the ordering in (2)") that is a
    # bare "(2)" NOT preceded by any of these separators, which a naive
    # `\(\d\)` scan would double-count as a second "(2)" marker.
    conditional_markers = re.findall(r"(?:: |; |and )\((\d)\)", conditional_section)
    assert len(conditional_markers) == len(set(conditional_markers)) and conditional_markers, (
        f"conditional 1.4.0 obligation markers are not unique/non-empty: {conditional_markers!r}"
    )
    stated_conditional = len(conditional_markers)

    disposition_text = (ROOT / "spec" / "CCR_DISPOSITION.md").read_text().replace("**", "")
    assert f"{stated_unconditional}件は無条件" in disposition_text, (
        f"CCR_DISPOSITION.md subordinate ruling 9(b) does not restate {stated_unconditional}件は無条件, "
        "matching versioning.version_binding's own unconditional count"
    )
    assert f"{stated_conditional}件は" in disposition_text and "条件付き義務である" in disposition_text, (
        f"CCR_DISPOSITION.md subordinate ruling 9(b) does not restate {stated_conditional}件, matching "
        "versioning.version_binding's own conditional count"
    )


# ---------------------------------------------------------------------------
# Phase 5 WP-1 fix-round (work order v1.2 §0.1 standing discipline 4, WP-1
# completion condition 18): a literal string pin for the requester-finalized
# English -- the 1.4.0 unconditional obligation (b) same-label addendum (one
# block, CCR_DISPOSITION.md subordinate ruling 10 item 2) and the 1.5.0
# paragraph's 4 finalized sentences (subordinate ruling 10 item 1) -- so a
# future accidental edit to this prose is caught by an assertion INDEPENDENT
# of the contract file itself, not only by eyeballing a diff. Normalization
# is deliberately narrow (the exact 4 operations the work order names):
# backtick removal, "**" removal, em dash "—" unified with ASCII "--" (never
# just stripped -- stripping alone is what let a prior revision of this pin
# silently fail to match sentence 1, whose reference text uses "—" while the
# contract itself uses "--"), and whitespace collapsed to single spaces. No
# other transformation (no case-folding, no punctuation removal).
# ---------------------------------------------------------------------------

PIN_1_4_0_OBLIGATION_B_ADDENDUM = (
    "this acceptance is scoped to the control surface's `audit_query` control endpoint (the "
    "canonical `POST /control/v1/audit/query`, and its alias as served on the control host — the "
    "same host scoping `endpoints.audit_query.deprecation_note` already states, and this "
    "document's own 1.4.0 conditional obligation (5) below, which requires both paths to answer "
    "as the identical operation). A data-plane host is not thereby obliged to authenticate "
    "control or audit credentials merely because it declares `control_plane` as something other "
    "than `unavailable`; where such a host holds no control-credential store, it may refuse a "
    "control or audit credential presented on its own `POST /v1/audit/query` alias as an unknown "
    "credential (`AUTH_INVALID`); it is not thereby required to accept, verify, or forward it. "
    "Co-hosting both surfaces in one process remains permitted (`versioning.control_discovery`) "
    "and is not what this scoping addresses"
)

PIN_1_5_0_SENTENCE_1 = (
    "Since 1.5.0 (subordinate ruling 10, item 1, conditional): `operations` and `target_kinds` "
    "are vocabularies each implementation declares for itself at "
    "`capabilities().audit_query.operations` / `.target_kinds` — the sets of values the "
    "`operation` and `target_kind` fields of events returned by `audit_query` can take."
)

PIN_1_5_0_SENTENCE_2 = (
    "As with `event_classes`, this contract enumerates no fixed enum and requires no particular "
    "member (declare-the-hazard)."
)

PIN_1_5_0_SENTENCE_3 = (
    "An implementation declaring 1.5.0 or higher whose `audit_query` is other than `unavailable` "
    "MUST declare both, and every event it returns MUST carry values drawn from the declared "
    "sets; the same superset relation holds for `event_classes`, stated here explicitly."
)

PIN_1_5_0_SENTENCE_4 = (
    "`audit_query.operations` is the vocabulary of the audit row's `operation` field and is "
    "unrelated to `capability_status.defined.atomic_mutation.operations`, which enumerates the "
    "executable mutation verbs."
)


def _normalize_prose_for_pin(text: str) -> str:
    """The work order's own 4 named normalizations, and only those: strip
    backticks and `**`; unify em dash "—" with ASCII "--" (never simply
    strip either one -- unifying is what makes the reference text, written
    with "—", compare equal to the contract's own "--" spelling); collapse
    whitespace runs to single spaces. No case-folding, no punctuation
    removal beyond that."""
    text = text.replace("`", "").replace("**", "")
    text = text.replace("—", "--")
    return " ".join(text.split())


def test_contract_pins_the_requester_finalized_1_4_0_and_1_5_0_prose():
    """Fix-round (2nd independent audit, mechanical check 1): pins the
    requester-finalized English verbatim (normalized) into an assertion,
    rather than leaving verbatim-ness as something only a human diff review
    confirmed. Checks both `versioning.version_binding` (all 5 blocks) and
    `audit.query_operation_vocabulary`/`query_target_kind_vocabulary` (the
    4 sentence-1-4 block, which fix-round U-2 placed identically in both
    notes)."""
    contract = json.loads((ROOT / "spec" / "data-service-api.v1.json").read_text())
    version_binding = _normalize_prose_for_pin(contract["versioning"]["version_binding"])
    query_operation_vocabulary = _normalize_prose_for_pin(contract["audit"]["query_operation_vocabulary"])
    query_target_kind_vocabulary = _normalize_prose_for_pin(contract["audit"]["query_target_kind_vocabulary"])

    assert _normalize_prose_for_pin(PIN_1_4_0_OBLIGATION_B_ADDENDUM) in version_binding, (
        "versioning.version_binding no longer contains the requester-finalized 1.4.0 unconditional "
        "obligation (b) same-label addendum (subordinate ruling 10 item 2) verbatim"
    )
    # Sentences 1-3 belong in version_binding itself (the 1.5.0 obligation
    # text); sentence 4 (the atomic_mutation.operations disambiguation) is
    # deliberately placed ONLY in the audit-section notes, never duplicated
    # into version_binding -- confirmed correct placement, not an omission
    # (1st independent audit, "(B) 1.5.0 段落" table: "sentence 4: ...
    # PRESENT (逐語) ... audit.query_operation_vocabulary 末尾"). All 4
    # sentences are required verbatim in BOTH audit-section notes (fix-round
    # U-2 placed the identical 4-sentence block in both).
    for name, sentence in (
        ("sentence 1", PIN_1_5_0_SENTENCE_1),
        ("sentence 2", PIN_1_5_0_SENTENCE_2),
        ("sentence 3", PIN_1_5_0_SENTENCE_3),
    ):
        normalized_sentence = _normalize_prose_for_pin(sentence)
        assert normalized_sentence in version_binding, (
            f"versioning.version_binding no longer contains the requester-finalized 1.5.0 {name} verbatim"
        )
    for name, sentence in (
        ("sentence 1", PIN_1_5_0_SENTENCE_1),
        ("sentence 2", PIN_1_5_0_SENTENCE_2),
        ("sentence 3", PIN_1_5_0_SENTENCE_3),
        ("sentence 4", PIN_1_5_0_SENTENCE_4),
    ):
        normalized_sentence = _normalize_prose_for_pin(sentence)
        assert normalized_sentence in query_operation_vocabulary, (
            f"audit.query_operation_vocabulary no longer contains the requester-finalized 1.5.0 {name} verbatim"
        )
        assert normalized_sentence in query_target_kind_vocabulary, (
            f"audit.query_target_kind_vocabulary no longer contains the requester-finalized 1.5.0 {name} verbatim"
        )
