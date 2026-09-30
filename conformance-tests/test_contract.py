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


def test_contract_declares_1_13_0():
    # CCR_DISPOSITION.md subordinate ruling 18: the version bump itself,
    # pinned so a future revert of just this one line is caught here rather
    # than only by whichever other test happens to touch contract_version.
    # This file carries one "declares" pin, for the version the contract
    # declares today; an implementation still declaring an earlier version
    # is exercised by version_binding's own retroactivity rule. Both
    # peers' own runtime declaration (`capabilities_document.py`/
    # `control_plane.py`) moves in the commit that lands the real behavior,
    # not in the commit that changes the contract text
    # (`versioning.version_binding`: a version-flip "must land in the same
    # commit as the real behavior change it claims").
    contract = json.loads((ROOT / "spec" / "data-service-api.v1.json").read_text())
    assert contract["contract_version"] == "1.13.0"


# ---------------------------------------------------------------------------
# Phase 10 WP-5a (contract 1.8.0, design docs/design/
# PHASE10_DEPLOYMENT_EVIDENCE_V1.md §3 D-5 (i), CCR_DISPOSITION.md
# subordinate ruling 13): completion conditions 1-4 and 6 (work order §2
# WP-5 table). The 3 sentences/entry below are copied VERBATIM from the
# monitor-finalized fixed-text file (scratchpad/phase10/fixed-text-1.8.0.md)
# -- never paraphrased (OPERATING_CONDITIONS.md §1.5 items 35/36).
# ---------------------------------------------------------------------------

FIXED_1_8_0_CAPABILITY_STATUS_RULE = (
    "limit_enforcement values describe the whole deployment reachable at the declared surfaces "
    "base URL, never one server process: a peer declares enforced for a limit class only when the "
    "bound holds across every process that may serve that base URL at the same time, and declares "
    "deployment_required when the bound is held per process and more than one process may serve "
    "that base URL."
)

FIXED_1_8_0_LIMITS_PROFILE_SUFFIX = (
    "Enforcement scope is the deployment behind the declared base URL (capability_status.rules); a "
    "bound kept in per-process memory is enforced for the deployment only while exactly one process "
    "serves that base URL."
)

# Phase 10 WP-5c (contract 1.8.0 addendum, supervisor ruling U-9
# 2026-09-08): 1.8.0's `conditional` list is no longer empty. The addendum
# adds one conditional obligation -- concurrent sends of one
# idempotency_key are serialized -- carried in exactly the shape the 1.7.0
# entry's own conditional items carry ({"obligation", "capability"}).
FIXED_1_8_0_OBLIGATIONS_ENTRY = {
    "version": "1.8.0",
    "subordinate_ruling": 13,
    "unconditional": ["limit_enforcement_scoped_to_deployment_behind_base_url"],
    "conditional": [
        {
            "obligation": "idempotency_concurrent_same_key_sends_serialized",
            "capability": ["idempotency"],
        }
    ],
}

# The full key set of `limits` BEFORE 1.8.0 (phase 9 state) -- completion
# condition 2 requires (2) to land inside the EXISTING `profile` string,
# never as a new sibling key; this snapshot is what makes "no new key"
# mechanically checkable rather than merely eyeballed.
_PRE_1_8_0_LIMITS_KEYS = frozenset({
    "audit_requests_per_minute_note",
    "classes",
    "enum_members",
    "example_profile",
    "finite_required",
    "profile",
    "request_budget",
})


def test_contract_pins_the_1_8_0_ruling_sentences_verbatim():
    """Completion conditions 1-3 (work order §2 WP-5 table): the 3
    monitor-finalized 1.8.0 pieces land at their designated contract
    locations, byte-for-byte -- (1) as `capability_status.rules`' 5th
    (index 4) array element, (2) appended to the END of `limits.profile`'s
    existing string (condition 2: never a new key), and (3) as
    `versioning.obligations`' 1.8.0 entry, carrying exactly the same 4
    keys every other entry in that array carries (condition 3).

    Phase 11 WP-1 (design docs/design/PHASE11_MIN_COMMON_PROFILE_V1.md §6.1,
    §15 裁定 2): contract 1.9.0 appends a 6th `capability_status.rules`
    element after the 1.8.0 one, so the 1.8.0 rule is no longer the array's
    LAST element -- the pin below moved from `rules[-1]` to `rules[4]` (the
    same element, an index fixed to its 1.8.0-era position rather than to
    "whatever is last"), and `len(rules) == 5` moved to `== 6`. The
    monitor-finalized 1.8.0 text itself is not touched by this move."""
    contract = json.loads((ROOT / "spec" / "data-service-api.v1.json").read_text())

    # (1) capability_status.rules.
    rules = contract["capability_status"]["rules"]
    assert len(rules) == 6, (
        f"expected 6 capability_status.rules (4 pre-1.8.0 + 1.8.0's own rule + 1.9.0's own rule), got {len(rules)}: {rules!r}"
    )
    assert rules[4] == FIXED_1_8_0_CAPABILITY_STATUS_RULE

    # (2) limits.profile -- condition 2.
    limits = contract["limits"]
    assert isinstance(limits["profile"], str)
    assert limits["profile"].endswith(FIXED_1_8_0_LIMITS_PROFILE_SUFFIX), (
        f"limits.profile does not end with the monitor-finalized 1.8.0 sentence verbatim: {limits['profile']!r}"
    )
    key_diff = set(limits.keys()) ^ _PRE_1_8_0_LIMITS_KEYS
    assert not key_diff, (
        f"limits gained/lost a key -- 1.8.0's (2) must land inside the existing `profile` STRING, "
        f"never as a new sibling key: {sorted(key_diff)}"
    )

    # (3) versioning.obligations -- condition 3. Phase 11 WP-1 (design
    # docs/design/PHASE11_MIN_COMMON_PROFILE_V1.md §6.2 (2), code review
    # return R4(a), 2026-09-24): appends a 1.9.0 entry after the 1.8.0 one,
    # so the 1.8.0 entry is no longer last -- pinned by an index fixed to
    # its 1.8.0-era position (obligations[6]), the same form §15 裁定 2
    # applies to capability_status.rules[4]. The 1.9.0 entry follows at
    # index 7 (pinned separately by test_contract_pins_the_1_9_0_texts_verbatim).
    obligations = contract["versioning"]["obligations"]
    assert obligations[6] == FIXED_1_8_0_OBLIGATIONS_ENTRY, (
        f"versioning.obligations[6] does not byte-match the monitor-finalized 1.8.0 entry: {obligations[6]!r}"
    )
    assert obligations[6]["version"] == "1.8.0"
    assert set(obligations[6].keys()) == {"version", "subordinate_ruling", "unconditional", "conditional"}


PIN_1_9_0_CAPABILITY_STATUS_RULE = (
    'Optional, in the sense the second rule above gives that word, means outside common_baseline: every operation common_baseline.operations names is required of an implementation declaring the contract version common_baseline.rule binds, and every other target operation stays optional and may be unavailable.'
)

PIN_1_9_0_VERSION_BINDING_PARAGRAPH = (
    "Only an implementation declaring 1.9.0 or higher additionally claims conformance to the obligations 1.9.0 introduces (subordinate ruling 14). Those obligations are unconditional in the same sense as every obligation enumerated above -- they bind simply by declaring 1.9.0, independent of any capability's own status: (a) every operation common_baseline.operations names is executable -- it is not answered with CAPABILITY_UNSUPPORTED, and no capability it needs is declared unavailable; and (b) its capability document carries operation_catalog_url, and the document served at that URL is byte-identical to this contract version's own derived operation catalog. Because common_baseline names operations these capabilities govern, an implementation declaring 1.9.0 declares none of application_catalog, schema_operations, structured_query, atomic_mutation, constraint_declarations, dry_run, idempotency or request_budget as unavailable; every obligation an earlier version made conditional on exactly those capabilities therefore binds unconditionally at 1.9.0, and is not restated here. 1.9.0 introduces no obligation on what a client must send: a request valid under 1.8.0 stays valid. An implementation still declaring 1.8.0 is not held to any 1.9.0-only obligation retroactively."
)

FIXED_1_9_0_COMMON_BASELINE = {
  "purpose": "The operations a client may compose without reading capability_status first. Anything not named here stays optional in the sense capability_status.rules already gives that word.",
  "operations": [
    "capability discovery on the data surface (GET /v1/capabilities)",
    "catalog discovery (GET /v1/catalog)",
    "create_entity and add_field under a developer credential, including the enum and nullable members of field_constraints",
    "insert",
    "predicate query with the operators eq, ne, lt, lte, gt, gte and in, together with order_by and the size member of page",
    "predicate-addressed update and delete -- never row-addressed; a delete follows the declare-and-echo protocol destructive_confirmation defines",
    "request-level dry_run and the plan it returns",
    "idempotency_key: the key recorded with its request digest, and a resend of the same key with the same body answered from that record, carrying the original request_id, without executing again",
    "a request's own budget",
    "declared enum and nullable constraints enforced on every value written"
  ],
  "capabilities": [
    "application_catalog",
    "schema_operations",
    "structured_query",
    "atomic_mutation",
    "constraint_declarations",
    "dry_run",
    "idempotency",
    "request_budget"
  ],
  "rule": "An implementation declaring this contract version or higher executes every operation named here: it answers none of them with CAPABILITY_UNSUPPORTED, and it declares none of the capabilities common_baseline.capabilities names as unavailable. This is a floor, not a ceiling -- it neither requires nor forbids anything outside the list. A capability declared partial stays conformant as long as its own unsupported list names nothing this list names, and as long as the operations list it publishes to a credential of the role an operation names here carries that operation: schema_operations, for instance, is read under a developer credential, which is the credential this list names for create_entity and add_field. The request_id and details obligations 1.7.0 already binds unconditionally continue to apply to every operation named here. The floor is about what a deployment provides, not about what one entity's own catalog declaration admits: where row_addressability is provided, mutation_classes.rule continues to decide each entity, and an entity declaring a class that does not support update or delete still refuses them with CAPABILITY_UNSUPPORTED -- a refusal the client reads from the catalog before sending, not one it must discover by trying.",
  "outside": "Named here to remove doubt, these are NOT in the floor and remain governed by each implementation's own declaration: the contains, matches and is_null operators; upsert; cross-entity mutation; row_addressability (mutation classes and row addresses); revision_preconditions; audit_query on the data surface; best_effort_transactions; create_index, drop_index, drop_entity and jobs; and page.cursor and the continuation a non-null next_page would offer -- a peer may always answer next_page: null."
}

FIXED_1_9_0_OBLIGATIONS_ENTRY = {
  "version": "1.9.0",
  "subordinate_ruling": 14,
  "unconditional": [
    "common_baseline_operations_executable",
    "operation_catalog_url_published_byte_identical"
  ],
  "conditional": []
}

FIXED_1_9_0_ENDPOINT_OPERATION_CATALOG = {
  "method": "GET",
  "path": "/v1/operation-catalog",
  "auth": "runtime or developer",
  "response": "OperationCatalogDocument",
  "semantics": "Served by an implementation declaring 1.9.0 or higher; an implementation declaring a lower version is not held to it.",
  "roles": [
    "runtime",
    "developer"
  ],
  "requires_capability": [],
  "atomicity": "none"
}

FIXED_1_9_0_SCHEMA_OPERATION_CATALOG_DOCUMENT = {
  "type": "object",
  "additionalProperties": False,
  "required": [
    "$comment",
    "contract_version",
    "operations"
  ],
  "properties": {
    "$comment": {
      "type": "string"
    },
    "contract_version": {
      "type": "string"
    },
    "operations": {
      "type": "array",
      "items": {
        "$ref": "#/definitions/OperationCatalogEntry"
      }
    }
  }
}

FIXED_1_9_0_DEFINITION_OPERATION_CATALOG_ENTRY = {
  "type": "object",
  "additionalProperties": False,
  "required": [
    "name",
    "method",
    "path",
    "roles",
    "requires_capability",
    "atomicity",
    "destructive",
    "request_schema",
    "response_schema"
  ],
  "properties": {
    "name": {
      "type": "string"
    },
    "method": {
      "type": "string"
    },
    "path": {
      "type": "string"
    },
    "roles": {
      "type": "array",
      "items": {
        "type": "string"
      }
    },
    "requires_capability": {
      "type": "array",
      "items": {
        "type": "string"
      }
    },
    "atomicity": {
      "enum": [
        "atomic",
        "none",
        "atomic_unless_best_effort"
      ]
    },
    "destructive": {
      "type": "boolean"
    },
    "request_schema": {
      "type": [
        "string",
        "null"
      ]
    },
    "response_schema": {
      "type": [
        "string",
        "null"
      ]
    }
  }
}


def test_contract_pins_the_1_9_0_texts_verbatim():
    """Phase 11 WP-1 code review return R1 (高, 2026-09-24): the
    requester-finalized 1.9.0 texts (design docs/design/
    PHASE11_MIN_COMMON_PROFILE_V1.md §6, requester ruling U-1/U-4 = (α))
    had no string/dict pin -- any 3-copy-identical paraphrase of them
    passed every WP-1 check. Pins all 5, in the same "constant + docstring
    + review-fix comment" form the 1.6.0/1.7.0/1.8.0 pins already use:
    (a) common_baseline (dict equality, full object), (b)
    capability_status.rules[5], (c) the 1.9.0 version_binding paragraph
    (substring, same normalization the 1.6.0/1.8.0 paragraph pins use),
    (d) versioning.obligations[7] (dict equality, the 1.9.0 entry), and
    (e) endpoints.operation_catalog plus the 2 new schemas (dict
    equality)."""
    contract = json.loads((ROOT / "spec" / "data-service-api.v1.json").read_text())

    # (a) common_baseline -- full object, dict equality.
    assert contract["common_baseline"] == FIXED_1_9_0_COMMON_BASELINE, (
        f"common_baseline does not byte-match the requester-finalized 1.9.0 (α) text: "
        f"{contract['common_baseline']!r}"
    )

    # (b) capability_status.rules[5].
    rules = contract["capability_status"]["rules"]
    assert rules[5] == PIN_1_9_0_CAPABILITY_STATUS_RULE, (
        f"capability_status.rules[5] does not byte-match the requester-finalized 1.9.0 text: {rules[5]!r}"
    )

    # (c) the 1.9.0 version_binding paragraph, placed after the 1.8.0
    # paragraph and before the version-flip discipline sentence.
    version_binding = contract["versioning"]["version_binding"]
    assert _normalize_prose_for_pin(PIN_1_9_0_VERSION_BINDING_PARAGRAPH) in _normalize_prose_for_pin(
        version_binding
    ), "versioning.version_binding no longer contains the requester-finalized 1.9.0 paragraph verbatim"
    idx_1_8_0_retro = version_binding.index("is not held to any 1.8.0-only obligation retroactively.")
    idx_1_9_0_paragraph = version_binding.index("Only an implementation declaring 1.9.0 or higher")
    idx_version_flip = version_binding.index("A peer's version-flip")
    assert idx_1_8_0_retro < idx_1_9_0_paragraph < idx_version_flip, (
        "the 1.9.0 version_binding paragraph is not placed directly after the 1.8.0 paragraph and "
        "before the version-flip discipline sentence"
    )

    # (d) versioning.obligations[7] -- the 1.9.0 entry, dict equality.
    obligations = contract["versioning"]["obligations"]
    assert obligations[7] == FIXED_1_9_0_OBLIGATIONS_ENTRY, (
        f"versioning.obligations[7] does not byte-match the requester-finalized 1.9.0 entry: {obligations[7]!r}"
    )

    # (e) endpoints.operation_catalog and the 2 new schemas, dict equality.
    assert contract["endpoints"]["operation_catalog"] == FIXED_1_9_0_ENDPOINT_OPERATION_CATALOG, (
        f"endpoints.operation_catalog does not byte-match the design §6.6 entry: "
        f"{contract['endpoints']['operation_catalog']!r}"
    )
    assert contract["schemas"]["OperationCatalogDocument"] == FIXED_1_9_0_SCHEMA_OPERATION_CATALOG_DOCUMENT, (
        f"schemas.OperationCatalogDocument does not byte-match the design §6.6 schema: "
        f"{contract['schemas']['OperationCatalogDocument']!r}"
    )
    assert contract["definitions"]["OperationCatalogEntry"] == FIXED_1_9_0_DEFINITION_OPERATION_CATALOG_ENTRY, (
        f"definitions.OperationCatalogEntry does not byte-match the design §6.6 definition: "
        f"{contract['definitions']['OperationCatalogEntry']!r}"
    )



def _subordinate_ruling_numbers_in_ccr_disposition() -> set[int]:
    """Own copy of `test_contract_history_register.py`'s identically-
    purposed helper (this suite's convention: each test module owns its
    own copy, e.g. `test_c09_audit_evidence.py`'s docstring). Finds every
    numbered item under `spec/CCR_DISPOSITION.md`'s "### 従属判断 --
    すべて裁定済み" heading."""
    text = (ROOT / "spec" / "CCR_DISPOSITION.md").read_text()
    lines = text.splitlines()
    heading_marker = "### 従属判断"
    heading_line_idx = None
    for i, line in enumerate(lines, start=1):
        if line.strip().startswith(heading_marker):
            heading_line_idx = i
            break
    assert heading_line_idx is not None, f"CCR_DISPOSITION.md has no {heading_marker!r} heading"
    numbers: set[int] = set()
    item_re = re.compile(r"^(\d{1,2})\.\s+\*\*")
    for i, line in enumerate(lines, start=1):
        if i <= heading_line_idx:
            continue
        m = item_re.match(line)
        if m:
            numbers.add(int(m.group(1)))
    return numbers


def test_versioning_obligations_subordinate_rulings_exist_in_ccr_disposition():
    """Completion condition 6: every `subordinate_ruling` number named in
    `versioning.obligations` (including 1.8.0's own 13) must exist as a
    numbered item under `spec/CCR_DISPOSITION.md`'s "### 従属判断 --
    すべて裁定済み" heading -- a contract obligation whose disposition
    record was dropped, or never existed, is caught here rather than only
    informally."""
    contract = json.loads((ROOT / "spec" / "data-service-api.v1.json").read_text())
    valid_numbers = _subordinate_ruling_numbers_in_ccr_disposition()
    assert valid_numbers, "found 0 numbered subordinate rulings in spec/CCR_DISPOSITION.md"

    obligations = contract["versioning"]["obligations"]
    assert obligations, "versioning.obligations is empty -- this check would be vacuous"
    missing = sorted(
        entry["subordinate_ruling"]
        for entry in obligations
        if entry["subordinate_ruling"] not in valid_numbers
    )
    assert not missing, (
        f"versioning.obligations names subordinate_ruling number(s) with no matching numbered item "
        f"in spec/CCR_DISPOSITION.md: {missing}"
    )


# Phase 10 WP-5b (contract 1.8.0, supervisor ruling 2026-09-08): the
# monitor-finalized version_binding paragraph for 1.8.0 (fixed text (5),
# scratchpad/phase10/fixed-text-1.8.0.md), copied verbatim -- unlike the
# WP-5a pieces above, this was NOT part of WP-5a's own scope (that report's
# open design question); the supervisor's disposition is that it belongs
# in version_binding itself, placed directly after the 1.7.0 paragraph and
# before the retroactive-denial enumeration (ruling item 1), and that the
# `_VERSION_BINDING_PROSE_EXCEPTIONS = {"1.8.0"}` carve-out WP-5a added to
# test_operation_catalog_register.py's test_obligations_version_set_
# matches_the_prose is removed rather than kept (ruling items 2-3).
#
# Phase 10 WP-5c (contract 1.8.0 addendum, supervisor ruling U-9
# 2026-09-08): this paragraph was rewritten before 1.8.0 reached `main`.
# 1.8.0 now introduces TWO obligations -- the unconditional
# enforcement-scope one WP-5a/5b already carried, and one conditional
# obligation gated on the `idempotency` capability (concurrent sends of
# one key are serialized). The pin below is the monitor-finalized
# replacement text, copied verbatim.
#
# Note the deliberate "One of those obligations is unconditional" wording
# ("is", not "are"): test_operation_catalog_register.py's
# `_UNCONDITIONAL_COUNT_RE` matches only "N of those obligations are
# unconditional", so 1.8.0 still states no machine-read unconditional
# count and that file's "exactly 3 versions state one (1.4.0, 1.6.0,
# 1.7.0)" assertion is unchanged.
PIN_1_8_0_VERSION_BINDING_PARAGRAPH = (
    "Only an implementation declaring 1.8.0 or higher additionally claims conformance to the obligations "
    "1.8.0 introduces (subordinate ruling 13). One of those obligations is unconditional in the same sense "
    "as every obligation enumerated above -- it binds simply by declaring 1.8.0, independent of any "
    "capability's own status: every limit_enforcement value it publishes describes the whole deployment "
    "reachable at the declared surfaces base URL, never one server process, so it declares enforced for a "
    "limit class only when the bound holds across every process that may serve that base URL at the same "
    "time, and declares deployment_required when the bound is held per process and more than one process "
    "may serve that base URL. The remaining 1.8.0 obligation is conditional, in the same sense 1.4.0's, "
    "1.6.0's and 1.7.0's own conditional lists are: it binds only insofar as the implementation's own "
    "capabilities() declares idempotency as something other than unavailable: (1) two requests carrying the "
    "same idempotency_key that arrive together are serialized so that at most one of them executes, the "
    "other being answered after the first commits as a resend -- from the record where the digests agree, "
    "with CONFLICT where they differ -- and the idempotency_entries bound is evaluated under that same "
    "serialization (structured_operations.idempotency.record). 1.8.0 introduces no obligation on what a "
    "client must send: a request valid under 1.7.0 stays valid."
)

# Phase 10 WP-5c: the sentence pair appended to the END of
# `structured_operations.idempotency.record` by the same addendum,
# monitor-finalized and copied verbatim. Pinned separately from
# PIN_1_7_0_IDEMPOTENCY_RECORD (which pins the 1.7.0 body and is a
# containment check, so it stays green under an append) so that deleting
# the addendum sentence is caught rather than silently tolerated.
PIN_1_8_0_IDEMPOTENCY_RECORD_CONCURRENT_SENDS = (
    "This holds for concurrent sends as well: two requests carrying the same key that arrive together are "
    "serialized by the implementation so that at most one of them executes; the other is answered after the "
    "first commits as a resend -- from the record where the digests agree, with CONFLICT where they differ "
    "-- or, where the first failed and left no record, executes as a new request. The idempotency_entries "
    "bound is evaluated under that same serialization, so two concurrent requests recording different keys "
    "cannot both pass a check that only one of them would pass in sequence."
)

# New (contract 1.8.0): the single-item retroactive-denial row for
# 1.7.0-declaring peers, following the same pattern PIN_1_7_0_RETROACTIVE_
# DENIAL_ROW_1_6_0 above documents for the 1.6.0/1.7.0 transition.
PIN_1_8_0_RETROACTIVE_DENIAL_ROW_1_7_0 = "is not held to any 1.8.0-only obligation retroactively"


def test_contract_pins_the_1_8_0_version_binding_paragraph_verbatim():
    """WP-5b (supervisor ruling 2026-09-08, items 1-2): monitor-finalized
    fixed text (5) is present verbatim in versioning.version_binding,
    directly after the 1.7.0 paragraph and before the (mechanically
    extended) retroactive-denial enumeration; and the new single-item
    1.7.0-declaring retroactive-denial row exists too."""
    contract = json.loads((ROOT / "spec" / "data-service-api.v1.json").read_text())
    version_binding = contract["versioning"]["version_binding"]

    assert _normalize_prose_for_pin(PIN_1_8_0_VERSION_BINDING_PARAGRAPH) in _normalize_prose_for_pin(version_binding), (
        "versioning.version_binding no longer contains the monitor-finalized 1.8.0 paragraph "
        "(fixed text (5)) verbatim"
    )
    assert PIN_1_8_0_RETROACTIVE_DENIAL_ROW_1_7_0 in version_binding, (
        "versioning.version_binding is missing the new 1.7.0-declaring retroactive-denial row"
    )

    # Placement: fixed text (5) must sit between the end of the 1.7.0
    # paragraph and the retroactive-denial enumeration (ruling item 1),
    # not merely somewhere in version_binding.
    anchor_1_7_0_end = "and a request valid under 1.6.0 stays valid."
    idx_1_7_0_end = version_binding.index(anchor_1_7_0_end)
    idx_1_8_0_paragraph = version_binding.index("Only an implementation declaring 1.8.0 or higher")
    idx_retroactive_row = version_binding.index(PIN_1_8_0_RETROACTIVE_DENIAL_ROW_1_7_0)
    assert idx_1_7_0_end < idx_1_8_0_paragraph < idx_retroactive_row, (
        "the 1.8.0 version_binding paragraph is not placed directly after the 1.7.0 paragraph and "
        "before the retroactive-denial enumeration"
    )


def test_contract_pins_the_1_8_0_concurrent_same_key_addendum_verbatim():
    """WP-5c (supervisor ruling U-9 2026-09-08): the addendum sentence pair
    sits at the END of `structured_operations.idempotency.record`, verbatim
    (it is the normative home the version_binding conditional obligation
    points at), and 1.8.0's `versioning.obligations` conditional entry names
    a capability that actually exists in `capability_status.defined`."""
    contract = json.loads((ROOT / "spec" / "data-service-api.v1.json").read_text())
    record = contract["structured_operations"]["idempotency"]["record"]
    assert record.rstrip().endswith(PIN_1_8_0_IDEMPOTENCY_RECORD_CONCURRENT_SENDS), (
        "structured_operations.idempotency.record does not end with the monitor-finalized 1.8.0 "
        f"addendum sentences verbatim: {record[-400:]!r}"
    )

    obligations_by_version = {entry["version"]: entry for entry in contract["versioning"]["obligations"]}
    conditional = obligations_by_version["1.8.0"]["conditional"]
    assert len(conditional) == 1, f"1.8.0 conditional list should hold exactly 1 element, got {conditional!r}"
    defined = set(contract["capability_status"]["defined"])
    for capability in conditional[0]["capability"]:
        assert capability in defined, (
            f"1.8.0 conditional obligation names capability {capability!r}, not in capability_status.defined"
        )
    assert set(conditional[0].keys()) == {"obligation", "capability"}, (
        "1.8.0's conditional item does not carry the same 2 keys 1.7.0's conditional items carry: "
        f"{sorted(conditional[0])}"
    )


# Phase 11 keyset paging WP-1 (contract 1.10.0 -- renumbered from a
# provisional 1.9.0 when main's 1.9.0 was taken in -- design
# docs/design/PHASE11_KEYSET_PAGING_V1.md D-1, CCR_DISPOSITION.md
# subordinate ruling 15): the monitor-finalized fixed text for 1.10.0
# (keyset paging), copied verbatim from the requester-confirmed
# scratchpad file (OPERATING_CONDITIONS.md §1.5 items 35/36) -- never
# paraphrased. All 7 obligations are conditional on `structured_query`; there
# is no unconditional 1.10.0 obligation.
FIXED_1_10_0_OBLIGATIONS_ENTRY = {
    "version": "1.10.0",
    "subordinate_ruling": 15,
    "unconditional": [],
    "conditional": [
        {"obligation": "query_results_are_totally_ordered", "capability": ["structured_query"]},
        {"obligation": "next_page_is_non_null_exactly_when_more_rows_follow", "capability": ["structured_query"]},
        {"obligation": "next_page_is_a_stateless_keyset_cursor", "capability": ["structured_query"]},
        {"obligation": "query_cursor_is_bound_to_application_entity_where_and_order_by", "capability": ["structured_query"]},
        {"obligation": "unusable_query_cursor_refused_as_a_request_schema_violation", "capability": ["structured_query"]},
        {"obligation": "unchanged_row_returned_exactly_once_across_a_traversal", "capability": ["structured_query"]},
        {"obligation": "omitted_page_size_defaults_to_the_least_of_1000_and_the_result_items_bounds", "capability": ["structured_query"]},
    ],
}

PIN_1_10_0_VERSION_BINDING_PARAGRAPH = (
    "Only an implementation declaring 1.10.0 or higher additionally claims conformance to the obligations "
    "1.10.0 introduces (subordinate ruling 15). Every 1.10.0 obligation is conditional, in the same sense "
    "1.4.0's, 1.6.0's, 1.7.0's and 1.8.0's own conditional lists are: each binds only insofar as the "
    "implementation's own capabilities() declares structured_query as something other than unavailable: (1) "
    "the items a query returns are totally ordered, in the order structured_operations.paging.ordering "
    "defines -- the request's own order_by, completed by a tie-break of the implementation's own choosing, "
    "which this contract does not name -- so that two identical requests decided against unchanged stored "
    "content return the identical sequence; (2) QueryResult.next_page is non-null exactly when at least one "
    "further row follows this page's last item in that order, and null exactly when none does; (3) where it "
    "is non-null, it is a keyset cursor as structured_operations.paging.cursor defines it -- an opaque token "
    "encoding that last item's own position in that order, never an offset or a count, holding no "
    "server-side state, and a request carrying it returns the rows that follow that position; (4) a cursor "
    "is bound to the Application, the entity, the request's where and the request's order_by, and stays "
    "valid across a change of select or page.size (structured_operations.paging.binding); (5) a cursor that "
    "fails to decode, whose ordering values do not match, in number or in type, the terms of that order, or "
    "whose recorded binding names a different Application, entity, where or order_by than the request "
    "presenting it, is refused with VALIDATION_FAILED, details.violated_declaration: request_schema and "
    "details.field: page/cursor; (6) across the pages of one traversal, a row that exists throughout it and "
    "whose ordering-term values do not change during it is returned exactly once; and (7) a request that "
    "carries no page.size is answered as though it carried the page.size equal to the least of 1000 "
    "(Page.size's own maximum), the implementation's declared limits.result_items, and the request's own "
    "budget.result_items where it carries one, and its page holds at most that many items "
    "(structured_operations.paging.next_page). 1.10.0 introduces no obligation on what a client must send: "
    "page.cursor remains optional wherever it appears, and a request valid under 1.9.0 stays valid in "
    "shape. A cursor an implementation issued before its own version-flip need not remain usable across it; "
    "such a request is refused as structured_operations.paging.refusal describes, and the client restarts "
    "the traversal. An implementation still declaring 1.9.0 is not held to any 1.10.0-only obligation "
    "retroactively."
)

PIN_1_10_0_RETROACTIVE_DENIAL_ROW_1_9_0 = "is not held to any 1.10.0-only obligation retroactively"


def test_contract_pins_the_1_10_0_obligations_entry_verbatim():
    """Completion condition 1: `versioning.obligations`' 1.10.0 entry
    byte-matches the monitor-finalized entry -- 7 conditional obligations
    bound to `structured_query`, 0 unconditional."""
    contract = json.loads((ROOT / "spec" / "data-service-api.v1.json").read_text())
    obligations = contract["versioning"]["obligations"]
    # Pinned by an index fixed to its 1.10.0-era position (obligations[8],
    # after 1.9.0's own entry at [7]) -- the same form the 1.8.0 entry's
    # obligations[6] and capability_status.rules[4] pins use, so a later
    # version appending its own entry leaves this pin untouched.
    assert obligations[8] == FIXED_1_10_0_OBLIGATIONS_ENTRY, (
        f"versioning.obligations[8] does not byte-match the monitor-finalized 1.10.0 entry: {obligations[8]!r}"
    )
    assert obligations[8]["version"] == "1.10.0"
    assert set(obligations[8].keys()) == {"version", "subordinate_ruling", "unconditional", "conditional"}


def test_contract_pins_the_1_10_0_version_binding_paragraph_verbatim():
    """Completion condition 2: the monitor-finalized 1.10.0 paragraph --
    including its own trailing 1.9.0-declaring retroactive-denial sentence
    -- is present verbatim in versioning.version_binding, and occupies
    EXACTLY the text between the 1.8.0-declaring retroactive-denial
    sentence that ends the 1.9.0 paragraph and the start of the 1.11.0
    paragraph (an equality check, not a mere containment check, so a
    further, unaccounted-for sentence slipped in between the two anchors is
    caught here too). Right edge follows contract 1.11.0 (subordinate
    ruling 16): the 1.11.0 paragraph now sits between the 1.10.0 paragraph
    and the version-flip sentence, so this test's own right anchor moves
    from the version-flip sentence to the start of the 1.11.0 paragraph;
    the 1.10.0 paragraph's own text (PIN_1_10_0_VERSION_BINDING_PARAGRAPH)
    is unchanged."""
    contract = json.loads((ROOT / "spec" / "data-service-api.v1.json").read_text())
    version_binding = contract["versioning"]["version_binding"]

    assert PIN_1_10_0_VERSION_BINDING_PARAGRAPH in version_binding, (
        "versioning.version_binding no longer contains the monitor-finalized 1.10.0 paragraph verbatim"
    )
    assert PIN_1_10_0_RETROACTIVE_DENIAL_ROW_1_9_0 in version_binding, (
        "versioning.version_binding is missing the new 1.9.0-declaring retroactive-denial row"
    )

    anchor_1_8_0_retroactive = "An implementation still declaring 1.8.0 is not held to any 1.9.0-only obligation retroactively."
    idx_1_8_0_retroactive_end = version_binding.index(anchor_1_8_0_retroactive) + len(anchor_1_8_0_retroactive)
    idx_1_11_0_paragraph = version_binding.index("Only an implementation declaring 1.11.0")
    between = version_binding[idx_1_8_0_retroactive_end:idx_1_11_0_paragraph]
    assert between == " " + PIN_1_10_0_VERSION_BINDING_PARAGRAPH + " ", (
        "the text between the 1.8.0-declaring retroactive row and the start of the 1.11.0 paragraph is not "
        f"exactly the monitor-finalized 1.10.0 paragraph (surrounded by one space on each side): {between!r}"
    )


# Contract 1.11.0 (CCR_DISPOSITION.md subordinate ruling 16): the
# monitor-finalized fixed text unifying both peers' refusal of a field name
# a query's select/where/order_by, or a mutation's values/where, names but
# the entity does not declare -- copied verbatim from the
# requester-confirmed scratchpad file (OPERATING_CONDITIONS.md §1.5 items
# 35/36) -- never paraphrased. The single obligation is unconditional (it
# does not depend on any capability's own status).
FIXED_1_11_0_OBLIGATIONS_ENTRY = {
    "version": "1.11.0",
    "subordinate_ruling": 16,
    "unconditional": ["undeclared_field_name_refused_as_validation_failed_request_schema"],
    "conditional": [],
}

PIN_1_11_0_VERSION_BINDING_PARAGRAPH = (
    "Only an implementation declaring 1.11.0 or higher additionally claims conformance to the obligation "
    "1.11.0 introduced (subordinate ruling 16), unconditional in the same sense as every unconditional "
    "obligation enumerated above: an undeclared field name, at any of the positions "
    "errors.details_vocabulary.undeclared_field names, is refused as that entry states -- VALIDATION_FAILED, "
    "violated_declaration request_schema, field naming the position -- and no other code is a conforming "
    "refusal of it. An implementation still declaring 1.10.0 is not held to any 1.11.0-only obligation "
    "retroactively."
)

PIN_1_11_0_RETROACTIVE_DENIAL_ROW_1_10_0 = "is not held to any 1.11.0-only obligation retroactively"

PIN_1_11_0_UNDECLARED_FIELD_VOCABULARY = (
    "A request that names a field the entity does not declare -- an entry of a query's select, where or "
    "order_by, a key of a mutation's values, or the field of a mutation's where predicate -- is refused with "
    "VALIDATION_FAILED, violated_declaration request_schema and field naming the position that carries the "
    "undeclared name (select/<i>, where/<i>/field, order_by/<i>/field, operations/<i>/values/<name>, "
    "operations/<i>/where/<j>/field); declared_type and observed_type are absent, since no declaration "
    "exists for that name. Schema operations that address a field by name are outside this rule. NOT_FOUND "
    "is not a conforming refusal of an undeclared field name at these positions."
)


def test_contract_pins_the_1_11_0_obligations_entry_verbatim():
    """Completion condition 1: `versioning.obligations`' 1.11.0 entry
    byte-matches the monitor-finalized entry -- 1 unconditional obligation,
    0 conditional."""
    contract = json.loads((ROOT / "spec" / "data-service-api.v1.json").read_text())
    obligations = contract["versioning"]["obligations"]
    # Pinned by an index fixed to its 1.11.0-era position (obligations[9],
    # after 1.10.0's own entry at [8]) -- the same form the 1.10.0 entry's
    # own obligations[8] pin uses, so a later version appending its own
    # entry leaves this pin untouched.
    assert obligations[9] == FIXED_1_11_0_OBLIGATIONS_ENTRY, (
        f"versioning.obligations[9] does not byte-match the monitor-finalized 1.11.0 entry: {obligations[9]!r}"
    )
    assert obligations[9]["version"] == "1.11.0"
    assert set(obligations[9].keys()) == {"version", "subordinate_ruling", "unconditional", "conditional"}


def test_contract_pins_the_1_11_0_version_binding_paragraph_verbatim():
    """Completion condition 2: the monitor-finalized 1.11.0 paragraph --
    including its own trailing 1.10.0-declaring retroactive-denial sentence
    -- is present verbatim in versioning.version_binding, and occupies
    EXACTLY the text between the 1.9.0-declaring retroactive-denial
    sentence that ends the 1.10.0 paragraph and the start of the 1.12.0
    sentence (an equality check, not a mere containment check, so a
    further, unaccounted-for sentence slipped in between the two anchors is
    caught here too). Right edge follows contract 1.12.0 (subordinate
    ruling 17): its one sentence sits between the 1.11.0 paragraph and the
    version-flip sentence; the 1.11.0 paragraph's own text is unchanged."""
    contract = json.loads((ROOT / "spec" / "data-service-api.v1.json").read_text())
    version_binding = contract["versioning"]["version_binding"]

    assert PIN_1_11_0_VERSION_BINDING_PARAGRAPH in version_binding, (
        "versioning.version_binding no longer contains the monitor-finalized 1.11.0 paragraph verbatim"
    )
    assert PIN_1_11_0_RETROACTIVE_DENIAL_ROW_1_10_0 in version_binding, (
        "versioning.version_binding is missing the new 1.10.0-declaring retroactive-denial row"
    )

    anchor_1_9_0_retroactive = "An implementation still declaring 1.9.0 is not held to any 1.10.0-only obligation retroactively."
    idx_1_9_0_retroactive_end = version_binding.index(anchor_1_9_0_retroactive) + len(anchor_1_9_0_retroactive)
    idx_1_12_0_sentence = version_binding.index("1.12.0 introduces no obligation")
    between = version_binding[idx_1_9_0_retroactive_end:idx_1_12_0_sentence]
    assert between == " " + PIN_1_11_0_VERSION_BINDING_PARAGRAPH + " ", (
        "the text between the 1.9.0-declaring retroactive row and the start of the 1.12.0 sentence is not exactly "
        f"the monitor-finalized 1.11.0 paragraph (surrounded by one space on each side): {between!r}"
    )


def test_contract_pins_the_1_11_0_undeclared_field_vocabulary_verbatim():
    """Completion condition 3: `errors.details_vocabulary.undeclared_field`
    byte-matches the monitor-finalized text."""
    contract = json.loads((ROOT / "spec" / "data-service-api.v1.json").read_text())
    dv = contract["errors"]["details_vocabulary"]
    assert dv["undeclared_field"] == PIN_1_11_0_UNDECLARED_FIELD_VOCABULARY, (
        f"errors.details_vocabulary.undeclared_field does not byte-match the monitor-finalized text: "
        f"{dv['undeclared_field']!r}"
    )


# The 6 `structured_operations.paging` clauses, copied verbatim from the
# requester-confirmed scratchpad file (Q-3, design §5.1, C-1 through C-6).
PIN_1_10_0_PAGING_ORDERING = (
    "The items QueryResult returns are totally ordered. The request's own order_by names the leading "
    "terms of that order, and where order_by is absent the implementation's own default leads; in "
    'either case the implementation completes the order with a tie-break of its own, so that no two '
    "rows of an entity ever compare equal. That tie-break is the implementation's own and this "
    'contract does not name it: a client does not rely on which it is, and where it is not one of the '
    "entity's declared fields, it is never returned as a field of an item and cannot be selected, "
    'filtered or ordered on. Two identical requests decided against unchanged stored content return '
    "the identical sequence of items. How strings compare (collation), where an ordering term's "
    'values include null, and how values that are not a string, number or boolean -- including an '
    "untyped field's values of differing JSON type -- compare, are the implementation's own; this "
    'version does not require two implementations to place them alike, and a client that needs a '
    'placement it can rely on orders by a field whose values it controls.'
)
PIN_1_10_0_PAGING_NEXT_PAGE = (
    "QueryResult.next_page is non-null exactly when at least one further row follows this page's last "
    'item in the order paging.ordering defines, and null exactly when none does. A null next_page is '
    "therefore the service's statement that this page ends the result -- what lets a client know it "
    'has read the whole of it, rather than inferring completeness from a page that came back shorter '
    'than page.size. An implementation may decide this by reading one row beyond the requested '
    'page.size and returning only page.size items. A client never constructs a next_page value '
    'itself; it only echoes the value it received back as Page.cursor on a later request. Where a '
    'request carries no page.size, it is answered as though it carried the page.size equal to the '
    "least of 1000 (Page.size's own maximum), the implementation's declared limits.result_items, and "
    "the request's own budget.result_items where it carries one; its page holds at most that many "
    'items, and next_page reports, in the same terms, whether any row follows the page it returned.'
)
PIN_1_10_0_PAGING_CURSOR = (
    'The value next_page carries is a keyset cursor: an opaque token encoding the position of this '
    "page's last item in the order paging.ordering defines -- that row's own ordering values together "
    "with the implementation's tie-break -- and never an offset, a row count, or an index a client "
    'could compute for itself. A request that carries a cursor returns, in the order paging.ordering '
    "defines, the rows that follow the position it encodes, under that request's own where and "
    'order_by as they stand when the request is decided. It holds no server-side state: nothing on '
    'the service expires, is evicted, or must be cleaned up, there is no bound on how many cursors '
    'may exist, and a cursor is not attached to a session, a connection or a credential. Its internal '
    'structure is opaque; an implementation may change that structure without a contract change, and '
    'no client may depend on it. This contract states no performance figure and none is claimed here. '
    'A cursor is neither signed nor encrypted: it is a recoverable encoding of the ordering values of '
    "a row the client has already received -- its own data, never another Application's -- and a "
    'client that stores or forwards a cursor forwards those values with it. An implementation is not '
    'required to detect a well-formed token it did not itself issue; the binding paging.binding '
    'defines is what keeps such a token inside the Application, entity, where and order_by it names, '
    'and a client that alters one receives an arbitrary position within its own result or a refusal, '
    "never another Application's rows."
)
PIN_1_10_0_PAGING_BINDING = (
    'A cursor is bound to the Application it was issued under, the entity it was issued against, and '
    "that request's own where and order_by; it is valid on a later request that repeats all four -- "
    'the same where predicates, in any order, and the same order_by -- and is refused under any '
    'other, as paging.refusal describes. select and page.size are deliberately outside that binding: '
    'neither changes where a row sits in the order, so a client may narrow or widen its projection '
    'between pages, and may continue from the cursor it already holds with a smaller page.size after '
    'a LIMIT_EXCEEDED refusal, without restarting the traversal.'
)
PIN_1_10_0_PAGING_REFUSAL = (
    'A cursor that fails to decode, whose ordering values do not match, in number or in type, the '
    "terms of this request's own order as paging.ordering defines it, or whose recorded binding names "
    'a different Application, entity, where or order_by than the request presenting it, is refused '
    'with VALIDATION_FAILED, details.violated_declaration: request_schema and details.field: '
    'page/cursor. The refusal names that position in the request and nothing else: not what the token '
    'decoded to, not what it was bound to, and not whether the Application or entity it names exists. '
    'A client that receives it restarts the traversal rather than adjusting the token.'
)
PIN_1_10_0_PAGING_TRAVERSAL = (
    'A traversal is a first request together with the successive requests that each echo back the '
    'next_page they received. Across the pages of one traversal, a row that exists throughout it and '
    'whose values for the ordering terms do not change during it is returned exactly once. A row '
    'inserted or deleted while the traversal is in progress is returned once or not at all; a row '
    'whose values for the ordering terms change during it may be returned twice, once, or not at all, '
    'since each page is decided against the order as it then stands. No further statement is made '
    'about concurrent change: this version defines paging, not a snapshot, and a client needing a '
    'stable point in time obtains it some other way.'
)

PIN_1_10_0_PAGING_CLAUSES = {
    'ordering': PIN_1_10_0_PAGING_ORDERING,
    'next_page': PIN_1_10_0_PAGING_NEXT_PAGE,
    'cursor': PIN_1_10_0_PAGING_CURSOR,
    'binding': PIN_1_10_0_PAGING_BINDING,
    'refusal': PIN_1_10_0_PAGING_REFUSAL,
    'traversal': PIN_1_10_0_PAGING_TRAVERSAL,
}


def test_contract_pins_the_1_10_0_paging_section_verbatim_and_placement():
    """Completion condition 3: the 6 `structured_operations.paging` clauses
    byte-match the monitor-finalized text (design §5.1 C-1 through C-6)
    verbatim, and `paging` sits between `upsert` and `revision_preconditions`
    -- the position design D-1 names (「query 系の語が並ぶ位置」)."""
    contract = json.loads((ROOT / "spec" / "data-service-api.v1.json").read_text())
    so = contract["structured_operations"]
    assert "paging" in so, "structured_operations.paging is missing"
    paging = so["paging"]
    assert set(paging.keys()) == set(PIN_1_10_0_PAGING_CLAUSES.keys())
    for key, pin in PIN_1_10_0_PAGING_CLAUSES.items():
        assert paging[key] == pin, (
            f"structured_operations.paging.{key} does not byte-match the monitor-finalized text verbatim: {paging[key]!r}"
        )

    keys = list(so.keys())
    assert keys.index("upsert") < keys.index("paging") < keys.index("revision_preconditions"), (
        f"structured_operations.paging is not placed between upsert and revision_preconditions: {keys!r}"
    )


def test_contract_pins_the_1_10_0_page_cursor_schema():
    """Completion condition 4: Page.cursor carries no maxLength (requester
    ruling Q-5 = (a), design D-1 (D)) -- {"type": "string"} exactly, no
    sibling key."""
    contract = json.loads((ROOT / "spec" / "data-service-api.v1.json").read_text())
    cursor_schema = contract["definitions"]["Page"]["properties"]["cursor"]
    assert cursor_schema == {"type": "string"}, (
        f"Page.cursor no longer matches the monitor-finalized 1.10.0 schema (no maxLength): {cursor_schema!r}"
    )


def test_contract_packaged_copies_are_byte_identical():
    """Completion condition 4: the 3 packaged copies of the contract JSON
    (spec/ + both peers' own `contract/` packages) are byte-for-byte
    identical, verified by sha256 rather than a mere length/spot check."""
    import hashlib

    paths = {
        "spec": ROOT / "spec" / "data-service-api.v1.json",
        "r2db-api": ROOT / "r2db-api" / "src" / "r2db_api" / "contract" / "data-service-api.v1.json",
        "MitateDB-api": ROOT / "MitateDB-api" / "src" / "mitatedb_api" / "contract" / "data-service-api.v1.json",
    }
    digests = {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in paths.items()}
    assert len(set(digests.values())) == 1, (
        f"the 3 packaged contract copies are not byte-identical: {digests}"
    )


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
    # application_authority's exact-match pin at `conformance-tests/test_contract.py` :28 and test_contract_states_
    # audit_sink_failure_policy's substring pins at `conformance-tests/test_contract.py` :57-59) -- each of these
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


# Contract 1.12.0 (CCR_DISPOSITION.md subordinate ruling 17): the contract no
# longer names the shape of the audit_requests_per_minute window. Both texts
# are copied verbatim from the ruling's own record.
PIN_1_12_0_AUDIT_WINDOW_NOTE = (
    "A pre-authentication window governing the audit_query endpoint specifically (both its canonical and "
    "alias paths, control_endpoints.audit_query/endpoints.audit_query.deprecation_note), separate from "
    "control_requests_per_minute: an implementation publishing this class enforces it as audit_query's "
    "own window and does not also charge audit_query requests against control_requests_per_minute, so "
    "that a high-frequency audit_query poller cannot exhaust the same window a break-glass control-plane "
    "operation (e.g. revoke_credential) depends on. This contract does not define the shape of that "
    "window: an implementation may count over a sliding 60-second window or over fixed 60-second windows,"
    " and in either case it admits no more than the declared number of audit_query requests within any "
    "one window it counts over. A client does not rely on where a window begins or ends."
)

PIN_1_12_0_VERSION_BINDING_SENTENCE = (
    "1.12.0 introduces no obligation (subordinate ruling 17): it withdraws the word fixed from "
    "limits.audit_requests_per_minute_note, so that this contract no longer defines the shape of the "
    "audit_requests_per_minute window, and an implementation conforming to 1.11.0 conforms to 1.12.0 "
    "without a behavior change."
)


def test_contract_pins_the_1_12_0_audit_window_note_verbatim():
    """`limits.audit_requests_per_minute_note` byte-matches the 1.12.0
    text: it states no window shape, keeps the bound a client plans on (no
    more than the declared number within any one window the implementation
    counts over) and keeps the window separate from
    control_requests_per_minute."""
    contract = json.loads((ROOT / "spec" / "data-service-api.v1.json").read_text())
    note = contract["limits"]["audit_requests_per_minute_note"]
    assert note == PIN_1_12_0_AUDIT_WINDOW_NOTE
    assert "fixed window " not in note
    assert "does not define the shape of that window" in note


def test_contract_pins_the_1_12_0_version_binding_sentence_verbatim():
    """The 1.12.0 sentence occupies EXACTLY the text between the
    1.10.0-declaring retroactive-denial sentence that ends the 1.11.0
    paragraph and the start of the 1.13.0 paragraph, and 1.12.0 adds no
    `versioning.obligations` entry (it introduces no obligation). Right
    edge follows contract 1.13.0 (subordinate ruling 18): its paragraph
    sits between the 1.12.0 sentence and the version-flip sentence; the
    1.12.0 sentence's own text is unchanged."""
    contract = json.loads((ROOT / "spec" / "data-service-api.v1.json").read_text())
    version_binding = contract["versioning"]["version_binding"]
    anchor = "An implementation still declaring 1.10.0 is not held to any 1.11.0-only obligation retroactively."
    idx_anchor_end = version_binding.index(anchor) + len(anchor)
    idx_1_13_0_paragraph = version_binding.index("Only an implementation declaring 1.13.0 or higher")
    between = version_binding[idx_anchor_end:idx_1_13_0_paragraph]
    assert between == " " + PIN_1_12_0_VERSION_BINDING_SENTENCE + " ", (
        "the text between the 1.10.0-declaring retroactive row and the start of the 1.13.0 paragraph is not exactly "
        f"the 1.12.0 sentence (surrounded by one space on each side): {between!r}"
    )
    versions = [entry["version"] for entry in contract["versioning"]["obligations"]]
    assert "1.12.0" not in versions
    assert versions[9] == "1.11.0"
    assert versions[10] == "1.13.0"


# Contract 1.13.0 (CCR_DISPOSITION.md subordinate ruling 18). Summary (not
# the confirmed text; the confirmed text is PIN_1_13_0_PROCESS_LOSS_POLICY
# below): a service process that stops without completing a graceful
# shutdown loses neither the audit event of an answered operation nor the
# count of an answered denial occurrence. The three texts are copied
# verbatim from the confirmed-text file (OPERATING_CONDITIONS.md section
# 1.5 items 35/36) -- never paraphrased. The one obligation is
# unconditional (it does not depend on any capability's own status).
PIN_1_13_0_PROCESS_LOSS_POLICY = (
    "An implementation declaring 1.13.0 or higher loses, when a service process stops without completing "
    "a graceful shutdown, neither the audit event of an operation whose response the service had already "
    "returned nor the count of any denial occurrence whose response the service had already returned. A "
    "buffer that such a stop can empty is therefore not the bounded buffer sink_failure_policy permits."
)

# `audit.sink_failure_policy` as the contract declared it at 1.12.0 (the
# value at the base of the contract 1.13.0 change set); 1.13.0 leaves it
# byte-identical.
PIN_SINK_FAILURE_POLICY_AS_OF_1_12_0 = (
    "Failure to durably record an authentication/authorization denial, a credential or Application lifecycle "
    "change, a destructive or privilege-sensitive operation, or a security-control failure fails the operation "
    "closed. Failure to record an ordinary data-operation event may be absorbed by a bounded buffer that raises "
    "an explicit operational alert; it must not silently discard events without that alert."
)

PIN_1_13_0_VERSION_BINDING_PARAGRAPH = (
    "Only an implementation declaring 1.13.0 or higher additionally claims conformance to the obligation "
    "1.13.0 introduced (subordinate ruling 18), unconditional in the same sense as every unconditional "
    "obligation enumerated above: audit.process_loss_policy -- a service process that stops without "
    "completing a graceful shutdown loses neither the audit event of an operation whose response the "
    "service had already returned nor the count of any denial occurrence whose response the service had "
    "already returned. An implementation still declaring 1.12.0 is not held to any 1.13.0-only "
    "obligation retroactively."
)

FIXED_1_13_0_OBLIGATIONS_ENTRY = {
    "version": "1.13.0",
    "subordinate_ruling": 18,
    "unconditional": ["audit_evidence_of_answered_requests_survives_abrupt_process_stop"],
    "conditional": [],
}


def test_contract_pins_the_1_13_0_process_loss_policy_verbatim():
    """`audit.process_loss_policy` byte-matches the confirmed text, sits
    right after `audit.sink_failure_policy`, and leaves
    `sink_failure_policy` itself untouched (the 1.13.0-or-higher
    qualifier is what keeps a 1.12.0-or-lower implementation's bounded
    buffer permitted)."""
    contract = json.loads((ROOT / "spec" / "data-service-api.v1.json").read_text())
    audit = contract["audit"]
    assert audit["process_loss_policy"] == PIN_1_13_0_PROCESS_LOSS_POLICY, (
        f"audit.process_loss_policy does not byte-match the confirmed text: {audit['process_loss_policy']!r}"
    )
    keys = list(audit)
    assert keys.index("process_loss_policy") == keys.index("sink_failure_policy") + 1
    assert "An implementation declaring 1.13.0 or higher" in audit["process_loss_policy"]
    assert audit["sink_failure_policy"] == PIN_SINK_FAILURE_POLICY_AS_OF_1_12_0, (
        f"audit.sink_failure_policy changed from its 1.12.0 text: {audit['sink_failure_policy']!r}"
    )


def test_contract_pins_the_1_13_0_obligations_entry_verbatim():
    """`versioning.obligations` ends with the 1.13.0 entry, byte-matching
    the confirmed entry -- 1 unconditional obligation, 0 conditional."""
    contract = json.loads((ROOT / "spec" / "data-service-api.v1.json").read_text())
    obligations = contract["versioning"]["obligations"]
    # Pinned by an index fixed to its 1.13.0-era position (obligations[10],
    # after 1.11.0's own entry at [9]; 1.12.0 adds none) -- the same form
    # the earlier entries' pins use, so a later version appending its own
    # entry leaves this pin untouched.
    assert obligations[10] == FIXED_1_13_0_OBLIGATIONS_ENTRY, (
        f"versioning.obligations[10] does not byte-match the confirmed 1.13.0 entry: {obligations[10]!r}"
    )
    assert set(obligations[10].keys()) == {"version", "subordinate_ruling", "unconditional", "conditional"}
    assert len(obligations[10]["unconditional"]) == 1


def test_contract_pins_the_1_13_0_version_binding_paragraph_verbatim():
    """The confirmed 1.13.0 paragraph -- including its own trailing
    1.12.0-declaring retroactive-denial sentence -- occupies EXACTLY the
    text between the 1.12.0 sentence and the version-flip sentence (an
    equality check, not a containment check, so a further sentence
    slipped in on either side is caught here too)."""
    contract = json.loads((ROOT / "spec" / "data-service-api.v1.json").read_text())
    version_binding = contract["versioning"]["version_binding"]
    assert PIN_1_13_0_VERSION_BINDING_PARAGRAPH in version_binding, (
        "versioning.version_binding no longer contains the confirmed 1.13.0 paragraph verbatim"
    )
    idx_1_12_0_end = version_binding.index(PIN_1_12_0_VERSION_BINDING_SENTENCE) + len(PIN_1_12_0_VERSION_BINDING_SENTENCE)
    idx_version_flip = version_binding.index("A peer's version-flip")
    between = version_binding[idx_1_12_0_end:idx_version_flip]
    assert between == " " + PIN_1_13_0_VERSION_BINDING_PARAGRAPH + " ", (
        "the text between the 1.12.0 sentence and the version-flip sentence is not exactly "
        f"the confirmed 1.13.0 paragraph (surrounded by one space on each side): {between!r}"
    )
    assert "An implementation still declaring 1.12.0 is not held to any 1.13.0-only obligation retroactively." in between


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
    # Phase 6 WP-1: bound the 1.4.0 conditional section at the START of the
    # NEXT version paragraph (1.5.0's own "Only an implementation declaring
    # ... additionally claims conformance" opener), not at the end of the
    # whole version_binding string -- otherwise a later version's own
    # "(1)"/"(2)"-style markers (e.g. the 1.6.0 paragraph's conditional
    # items (1)/(2), added subordinate ruling 11) would double-count here.
    next_paragraph_marker = "Only an implementation declaring 1.5.0"
    assert next_paragraph_marker in version_binding, f"expected marker phrase {next_paragraph_marker!r} not found"
    conditional_section = version_binding[version_binding.index(requires_marker):version_binding.index(next_paragraph_marker)]
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

# Phase 9 WP-1 (contract 1.7.0, R-10 (B), design docs/design/
# PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md §3 D-9, §5 U-6 S-e):
# stripping removed this sentence's leading provenance clause ("Since 1.5.0
# (subordinate ruling 10, item 1, conditional): ") from `audit.
# query_operation_vocabulary` / `audit.query_target_kind_vocabulary` (both
# manifest-stripped paths) but NOT from `versioning.version_binding` (an
# `unstripped: true` manifest path -- the clause stays woven into that
# cumulative narrative). The requester-finalized normative sentence is
# identical in both places; only the leading clause differs. PIN_1_5_0_
# SENTENCE_1 (with the clause) still matches version_binding;
# PIN_1_5_0_SENTENCE_1_STRIPPED (without it) matches the two audit-section
# notes. This is the ONLY one of the 15 pre-1.7.0 PIN constants that R-10
# (B) stripping actually moves (§6.3, monitor ruling S-e) -- every other
# constant in this file matches its target unchanged.
PIN_1_5_0_SENTENCE_1 = (
    "Since 1.5.0 (subordinate ruling 10, item 1, conditional): `operations` and `target_kinds` "
    "are vocabularies each implementation declares for itself at "
    "`capabilities().audit_query.operations` / `.target_kinds` — the sets of values the "
    "`operation` and `target_kind` fields of events returned by `audit_query` can take."
)

PIN_1_5_0_SENTENCE_1_STRIPPED = (
    "`operations` and `target_kinds` "
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
        ("sentence 1 (stripped)", PIN_1_5_0_SENTENCE_1_STRIPPED),
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
    # The (still-prefixed) sentence 1 must NOT appear in these two
    # (stripped) paths -- confirms the strip actually removed the leading
    # provenance clause rather than the comparison merely happening to
    # succeed via substring containment of the stripped form within the
    # unstripped one.
    assert _normalize_prose_for_pin(PIN_1_5_0_SENTENCE_1) not in query_operation_vocabulary
    assert _normalize_prose_for_pin(PIN_1_5_0_SENTENCE_1) not in query_target_kind_vocabulary

# ---------------------------------------------------------------------------
# Phase 6 WP-1 (docs/work-orders/WORK_ORDER_PHASE6_CONTRACT_160_V1.md v1.2 WP-1
# item 9, standing discipline 4; CCR_DISPOSITION.md subordinate ruling 11):
# literal string pins for the requester-finalized English of confirmed-prose
# blocks (1)-(5) (scratchpad/phase6-contract-prose.md, section headings
# reproduced in the comments below) plus the 1.6.0-only extension of the 4
# pre-existing retroactive-denial sentences in versioning.version_binding.
# Normalization mirrors _normalize_prose_for_pin above (backtick / "**" /
# em-dash-to-"--" / whitespace collapse only -- no case-folding, no other
# punctuation removal). Each assertion below extracts from a SPECIFIC JSON
# path (never a raw whole-file grep), per standing discipline 1 (no vacuous
# pin): a pin that only matched somewhere in the raw file text could pass
# even if the confirmed prose ended up in the wrong schema location.
# ---------------------------------------------------------------------------

# (1) security.schemes.* description / CredentialIssued.secret / CredentialRotated.secret (D-1)
PIN_1_6_0_ITEM_1_SECRET_IS_BEARER = """`CredentialIssued.secret` — and the `secret` a rotate response returns, wherever this contract defines one — **is the complete bearer token for the surface that credential is for**: a client presents that exact string, verbatim, as `Authorization: Bearer <secret>`; an application credential on the application surface, a control or audit credential on the control surface (`security.schemes.control_credential` continues to state that application credentials are not accepted there). A client MUST NOT compose it from, split it into, or derive it from any other field of the response — `credential_id` is returned as its own field, for naming the credential in later control operations, and is never something a client extracts from the secret. Its internal structure is opaque; an implementation may change that structure without a contract change, and no client may depend on it. The service still stores only a verifier/digest and never returns the secret again."""

# (2) CapabilityDocument.surfaces description (D-2)
PIN_1_6_0_ITEM_2_SURFACES = """`surfaces` names the absolute base URLs at which this deployment's own surfaces are reached, **as declared by the deployer** — never derived, and never to be inferred by a client from the URL it happened to use. `surfaces.data.base_url` ends at `versioning.base_path`; `surfaces.control.base_url` ends at `versioning.control_base_path`. **The data surface's capability document and the control surface's own capability document return the same `surfaces` object**, so a client holding either base URL can reach the other surface, and either document, fetched again at its own declared URL, answers with the same `contract_version` and the same `surfaces` — the rest of each document remains scoped to the credential presented. A deployment declaring `control_plane` as `unavailable` omits `surfaces.control`. Neither URL ends in a trailing slash, so that appending a path to it yields exactly one separator. Whether the two surfaces share a host is read from the **origins** (scheme, host and port — not the path) of these two URLs — the co-hosting `versioning.control_discovery` permits — and is never assumed; where `surfaces.control` is absent, the surfaces are not co-hosted. **Where the two surfaces run as separate processes, both are configured from the same declaration**: neither can verify the other's document, so a deployment whose two documents disagree is non-conformant, and a client is given no rule for preferring one over the other."""

# (3) field-type vocabulary json + EntityDescriptor.field_types + SchemaOperationRequest.field_types (D-3)
# Phase 9 WP-1 (contract 1.7.0, §5 U-8 #28, design docs/design/
# PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md §3 D-2): the middle
# ("The catalog reports only facts...") sentence was revised because 1.6.0's
# wording ("declares neither nullability... nor whether a field is
# required") became false once 1.7.0 gives schema operations a notion of
# nullability (field_constraints). This revision is independent of R-10 (B)
# stripping -- it is a meaning change to this PIN's own text, not a
# provenance-marker removal -- and is why this PIN is one of the 7 that
# move for 1.7.0 even though its json_path is also one of the 26 stripped
# ones (the stripped provenance prefix was never part of this PIN's text to
# begin with; the PIN already excluded it, matching the live contract value
# both before and after stripping).
PIN_1_6_0_ITEM_3_FIELD_TYPES = """The field-type vocabulary gains a seventh member, `json`, meaning **any JSON value**. **A field created without a declared type has type `json`** — this names an existing default rather than introducing a new one, and there is no "unknown" member of the vocabulary: every field carries a real type.

`EntityDescriptor.field_types` maps every name in `fields` to that field's type, drawn from that same vocabulary. What a client declared — through `SchemaOperationRequest.field_types` on `create_entity`, or `field_type` on `add_field` — is what the catalog reports back, and a field for which no type was declared reports `json`. Where a schema operation later redeclares a field's type, the catalog reports the type most recently declared. **The catalog reports only facts this contract's own schema operations can establish**: nullability and enum membership through `field_constraints`, and neither default values nor a notion of required distinct from `nullable: false`, because no schema operation defined here establishes either; a later version that gives schema operations such a notion gives it to the catalog in that same version.

`object` and `array` are narrower than `json`: a field declared `json` accepts **any** JSON value, including but not limited to objects and arrays, while a field declared `object` or `array` accepts only that shape — and the catalog reports the narrower word it was declared with, never rounding it up to `json`.

`SchemaOperationRequest.field_types` and `EntityDescriptor.field_types` share one object shape but not one coverage rule: **the request's object may be partial** — any name in `fields` that it omits is created with type `json` — while **the catalog's object is always total over that entity's own `fields`**. `SchemaOperationRequest.field_types` is **never required**: a `create_entity` naming only `fields` remains a valid request, creating `json` fields. A `field_types` naming a field the request's own `fields` does not name, a `field_types` value outside this vocabulary, or a `field_types` sent without `fields`, each fails `VALIDATION_FAILED`; none of the three is silently ignored. `add_field` continues to carry a single `field_type` for the single field it adds."""

# (4) versioning.version_binding 1.6.0 paragraph
# Phase 9 WP-1 (contract 1.7.0, §5 U-8 #24 = (a)): the paragraph's own final
# sentence (a retroactive-denial row for 1.5.0-declaring peers) is widened
# from "1.6.0-only" alone to "1.6.0-only or 1.7.0-only", to keep this one
# subject (which version denies which later-only obligation to which
# earlier-declaring peer) in a single place rather than splitting it
# between this paragraph and the new 1.7.0 one.
# Phase 10 WP-5b (contract 1.8.0, supervisor ruling 2026-09-08, subordinate
# ruling 13): widened AGAIN, mechanically, from "1.6.0-only or 1.7.0-only"
# to "1.6.0-only, 1.7.0-only, or 1.8.0-only" -- the same extension applied
# to this sentence for 1.7.0 above, applied once more for 1.8.0.
PIN_1_6_0_VERSION_BINDING_PARAGRAPH = """Only an implementation declaring 1.6.0 or higher additionally claims conformance to the obligations 1.6.0 introduces (subordinate ruling 11). **Two of those obligations are unconditional in the same sense as every obligation enumerated above** — they bind simply by declaring 1.6.0, independent of any capability's own status: (a) its `GET /v1/capabilities` document carries `surfaces.data.base_url`, the absolute base URL of its own data surface, and — where a control surface is provided at all (`control_plane` other than `unavailable`, the same precondition subordinate rulings 8 and 9 already carry) — both surfaces' capability documents additionally carry `surfaces.control.base_url`, each document carrying the same `surfaces`; and (b) the `secret` returned by any issue or rotate path it offers, in band or out of band, is accepted verbatim as a bearer token on the surface that credential is for, with no composition, splitting, or derivation required of the client (`security.schemes`). **The remaining 1.6.0 obligations are conditional**, in the same sense 1.4.0's own conditional list is: they bind only insofar as the implementation's own `capabilities()` declares the named capability as something other than `unavailable`. Where it declares `application_catalog` as something other than `unavailable`: (1) every `EntityDescriptor` it returns carries `field_types`, total over that entity's own `fields`, reporting `json` for any field created without a declared type. Where it declares `schema_operations` as something other than `unavailable`: (2) a `create_entity` it executes accepts `field_types` and creates each field named there with the type declared there, and an `add_field` it executes accepts every member of the seven-member vocabulary, `json` included; a `field_types` naming a field outside the request's own `fields`, carrying a value outside that vocabulary, or sent without `fields`, is refused with `VALIDATION_FAILED`. **1.6.0 introduces no obligation on what a client must send**: `SchemaOperationRequest.field_types` is optional wherever it appears, and a request valid under 1.5.0 stays valid. An implementation still declaring 1.5.0 is not held to any 1.6.0-only, 1.7.0-only, or 1.8.0-only obligation retroactively."""

# (5-current) structured_operations.upsert sentence BEFORE the D-3(vii) edit
# -- pinned so the manual "obligation count unchanged (2)" audit trail (WP-1
# completion condition 5) has a machine-checkable anchor for what the FIRST
# obligation's wording was, and so this test fails loudly if a future edit
# silently drops the untouched first half of the sentence.
PIN_1_6_0_UPSERT_SENTENCE_BEFORE = """upsert on an entity without a declared uniqueness key, and upsert or update on an entity not declaring the mutable class, fail with CAPABILITY_UNSUPPORTED."""

# (5) structured_operations.upsert sentence AFTER the D-3(vii) same-label
# addendum (item 4; not placed in the 1.6.0 version_binding paragraph).
PIN_1_6_0_UPSERT_SENTENCE_AFTER = """upsert on an entity without a declared uniqueness key fails with `CAPABILITY_UNSUPPORTED`; and, where `row_addressability` is provided (other than `unavailable`) — the same precondition `mutation_classes.rule` carries for the declaration itself — upsert or update on an entity not declaring the mutable class fails with `CAPABILITY_UNSUPPORTED` as well. An implementation that does not provide `row_addressability` does not thereby declare a mutation class for any entity, and this sentence does not refuse the mutations its own `atomic_mutation` capability declares."""

# The 4 pre-existing retroactive-denial sentences (1.1.0 / 1.2.0 / 1.3.0 /
# 1.4.0 rows), each extended AGAIN with a ", or 1.7.0-only" / " or 1.7.0-only"
# member (phase 9 WP-1, §5 U-8 #23) on top of the 1.6.0-only member phase 6
# already added -- the 5th row (1.5.0 vs 1.6.0-only/1.7.0-only) is supplied
# by confirmed-prose block (4) itself (its own last sentence) and is covered
# by PIN_1_6_0_VERSION_BINDING_PARAGRAPH above, not repeated here. These 4
# constants are renamed PIN_1_7_0_* (their content now includes the
# 1.7.0-only member; the old PIN_1_6_0_RETROACTIVE_DENIAL_ROW_* names are
# retired rather than kept as an intermediate, now-incorrect value).
#
# Phase 10 WP-5b (contract 1.8.0, supervisor ruling 2026-09-08, subordinate
# ruling 13): each of these 4 rows is widened AGAIN, mechanically, adding
# ", or 1.8.0-only" on top of the "..., or 1.7.0-only" member phase 9
# already added -- the same treatment PIN_1_6_0_VERSION_BINDING_PARAGRAPH's
# own trailing sentence and PIN_1_7_0_RETROACTIVE_DENIAL_ROW_1_6_0 (below)
# receive. Names are kept as PIN_1_7_0_* (they were never renamed to
# PIN_1_8_0_* -- only their content changes, following the same
# no-intermediate-rename convention the comment above already states).
PIN_1_7_0_RETROACTIVE_DENIAL_ROW_1_1_0 = (
    "is not held to any 1.2.0-only, 1.3.0-only, 1.4.0-only, 1.5.0-only, 1.6.0-only, 1.7.0-only, or 1.8.0-only "
    "obligation retroactively"
)
PIN_1_7_0_RETROACTIVE_DENIAL_ROW_1_2_0 = (
    "is not held to any 1.3.0-only, 1.4.0-only, 1.5.0-only, 1.6.0-only, 1.7.0-only, or 1.8.0-only "
    "obligation retroactively"
)
PIN_1_7_0_RETROACTIVE_DENIAL_ROW_1_3_0 = (
    "is not held to any 1.4.0-only, 1.5.0-only, 1.6.0-only, 1.7.0-only, or 1.8.0-only obligation retroactively"
)
PIN_1_7_0_RETROACTIVE_DENIAL_ROW_1_4_0 = (
    "is not held to any 1.5.0-only, 1.6.0-only, 1.7.0-only, or 1.8.0-only obligation retroactively"
)
# New (contract 1.8.0): the single-item row for 1.6.0-declaring peers,
# widened from "1.7.0-only" alone (phase 9 WP-1's own new sentence,
# introduced -- not extended -- alongside the 1.7.0 paragraph) to
# "1.7.0-only or 1.8.0-only".
PIN_1_7_0_RETROACTIVE_DENIAL_ROW_1_6_0 = "is not held to any 1.7.0-only or 1.8.0-only obligation retroactively"


def test_contract_pins_the_requester_finalized_1_6_0_prose():
    """Phase 6 WP-1 completion conditions 1, 2, 3, 17: the requester-finalized
    confirmed-prose blocks (1)-(5) are present verbatim (normalized) at their
    specific contract JSON paths, and the 4 pre-existing retroactive-denial
    sentences each gained their 1.6.0-only member."""
    contract = json.loads((ROOT / "spec" / "data-service-api.v1.json").read_text())

    # --- (1): 4 locations, all identical (mirrors the existing precedent of
    # audit.query_operation_vocabulary / query_target_kind_vocabulary sharing
    # one identical block verbatim). ---
    pin1_normalized = _normalize_prose_for_pin(PIN_1_6_0_ITEM_1_SECRET_IS_BEARER)
    application_credential_description = contract["security"]["schemes"]["application_credential"]["description"]
    control_credential_description = contract["security"]["schemes"]["control_credential"]["description"]
    credential_issued_secret_description = contract["schemas"]["CredentialIssued"]["properties"]["secret"]["description"]
    credential_rotated_secret_description = contract["schemas"]["CredentialRotated"]["properties"]["secret"]["description"]
    for name, extracted in (
        ("security.schemes.application_credential.description", application_credential_description),
        ("security.schemes.control_credential.description", control_credential_description),
        ("schemas.CredentialIssued.properties.secret.description", credential_issued_secret_description),
        ("schemas.CredentialRotated.properties.secret.description", credential_rotated_secret_description),
    ):
        assert extracted, f"{name} is empty -- item 1 prose was not placed there"
        assert pin1_normalized in _normalize_prose_for_pin(extracted), (
            f"{name} no longer contains the requester-finalized item 1 (D-1) prose verbatim"
        )

    # --- (2): CapabilityDocument.surfaces, an ADDED optional property -- also
    # confirms `required` was not touched (item 2's own "required は変えない"). ---
    capability_document = contract["schemas"]["CapabilityDocument"]
    assert "surfaces" not in capability_document["required"], (
        "CapabilityDocument.required must not gain 'surfaces' -- it is an optional key (D-2)"
    )
    surfaces_schema = capability_document["properties"]["surfaces"]
    surfaces_description = surfaces_schema["description"]
    assert surfaces_description, "CapabilityDocument.properties.surfaces.description is empty"
    assert _normalize_prose_for_pin(PIN_1_6_0_ITEM_2_SURFACES) in _normalize_prose_for_pin(surfaces_description), (
        "CapabilityDocument.properties.surfaces.description no longer contains the requester-finalized "
        "item 2 (D-2) prose verbatim"
    )
    # Review fix F2 (WP-1 code review): the STRUCTURE of `surfaces` was
    # entirely unpinned -- only its description string was checked above.
    # Review mutation alpha (dropping the nested `required: ["base_url"]`
    # from surfaces.data / surfaces.control in spec + both packaged copies
    # simultaneously) passed undetected through this file plus
    # test_schema_check.py plus test_c11_document_conformance.py (52
    # passed) before this fix. Pin the shape directly, including the
    # supervisor-directed addition of `surfaces.required == ["data"]`
    # (surfaces.data.base_url is an UNCONDITIONAL 1.6.0 obligation per
    # version_binding's own item (a); confirmed prose is unchanged by this
    # -- it already says a control_plane: unavailable deployment omits
    # ONLY surfaces.control, never surfaces.data).
    assert surfaces_schema["type"] == "object"
    assert surfaces_schema["additionalProperties"] is False
    assert surfaces_schema["required"] == ["data"], (
        "CapabilityDocument.properties.surfaces.required must be exactly ['data'] -- surfaces.data.base_url "
        "is unconditional wherever surfaces itself is present, while surfaces.control stays omittable"
    )
    assert set(surfaces_schema["properties"]) == {"data", "control"}
    for surface_name in ("data", "control"):
        surface_entry_schema = surfaces_schema["properties"][surface_name]
        assert surface_entry_schema["type"] == "object"
        assert surface_entry_schema["additionalProperties"] is False
        assert surface_entry_schema["required"] == ["base_url"], (
            f"CapabilityDocument.properties.surfaces.properties.{surface_name}.required must be ['base_url']"
        )
        assert surface_entry_schema["properties"]["base_url"]["type"] == "string"

    # --- (3): field_type enum gains json (7th member); EntityDescriptor.field_types
    # and SchemaOperationRequest.field_types both carry the identical item 3 prose. ---
    seven_word_vocabulary = ["string", "integer", "number", "boolean", "object", "array", "json"]
    field_type_enum = contract["schemas"]["SchemaOperationRequest"]["properties"]["field_type"]["enum"]
    assert field_type_enum == seven_word_vocabulary, (
        f"SchemaOperationRequest.field_type enum is no longer the 7-word vocabulary: {field_type_enum!r}"
    )
    entity_descriptor_field_types = contract["definitions"]["EntityDescriptor"]["properties"]["field_types"]
    schema_operation_request_field_types = contract["schemas"]["SchemaOperationRequest"]["properties"]["field_types"]
    assert entity_descriptor_field_types["additionalProperties"]["enum"] == seven_word_vocabulary
    assert schema_operation_request_field_types["additionalProperties"]["enum"] == seven_word_vocabulary
    pin3_normalized = _normalize_prose_for_pin(PIN_1_6_0_ITEM_3_FIELD_TYPES)
    for name, schema in (
        ("definitions.EntityDescriptor.properties.field_types", entity_descriptor_field_types),
        ("schemas.SchemaOperationRequest.properties.field_types", schema_operation_request_field_types),
    ):
        description = schema["description"]
        assert description, f"{name}.description is empty"
        assert pin3_normalized in _normalize_prose_for_pin(description), (
            f"{name}.description no longer contains the requester-finalized item 3 (D-3) prose verbatim"
        )
    # `fields` itself (string array) is untouched by item 3 (D-3 keeps it a
    # plain string-array; only `field_types` is new).
    assert contract["schemas"]["SchemaOperationRequest"]["properties"]["fields"]["type"] == "array"

    # --- (4): the 1.6.0 version_binding paragraph, verbatim. ---
    version_binding = contract["versioning"]["version_binding"]
    assert _normalize_prose_for_pin(PIN_1_6_0_VERSION_BINDING_PARAGRAPH) in _normalize_prose_for_pin(version_binding), (
        "versioning.version_binding no longer contains the requester-finalized 1.6.0 paragraph verbatim"
    )

    # --- 1.6.0-only retroactive-denial extension: the 4 pre-existing rows
    # (now also carrying their 1.7.0-only member -- see
    # test_contract_pins_the_requester_finalized_1_7_0_prose for the
    # dedicated 1.7.0 pin of this same fact; kept here too since this test
    # is what the phase 6 completion condition it documents still refers
    # to). ---
    for name, row in (
        ("1.1.0 row", PIN_1_7_0_RETROACTIVE_DENIAL_ROW_1_1_0),
        ("1.2.0 row", PIN_1_7_0_RETROACTIVE_DENIAL_ROW_1_2_0),
        ("1.3.0 row", PIN_1_7_0_RETROACTIVE_DENIAL_ROW_1_3_0),
        ("1.4.0 row", PIN_1_7_0_RETROACTIVE_DENIAL_ROW_1_4_0),
    ):
        assert row in version_binding, (
            f"versioning.version_binding's retroactive-denial {name} does not carry its 1.6.0-only "
            f"and 1.7.0-only members: {row!r}"
        )

    # --- item 4 (D-3 (vii)): the upsert same-label addendum, NOT placed in
    # the 1.6.0 paragraph -- pinned separately (WP-1 completion condition 2). ---
    upsert = contract["structured_operations"]["upsert"]
    upsert_normalized = _normalize_prose_for_pin(upsert)
    assert _normalize_prose_for_pin(PIN_1_6_0_UPSERT_SENTENCE_BEFORE) not in upsert_normalized, (
        "structured_operations.upsert still contains the PRE-edit sentence verbatim -- "
        "the D-3(vii) same-label addendum was not applied"
    )
    assert _normalize_prose_for_pin(PIN_1_6_0_UPSERT_SENTENCE_AFTER) in upsert_normalized, (
        "structured_operations.upsert does not contain the requester-finalized D-3(vii) replacement sentence verbatim"
    )
    # The addendum lives in the upsert section body, never duplicated into
    # the 1.6.0 version_binding paragraph (item 4 is same-label, not a new
    # 1.6.0-labelled obligation) -- WP-1 completion condition 2. Review fix
    # F1 (WP-1 code review, scratchpad/review-wp1/review-wp1-160.md): this
    # MUST check the real contract text (`version_binding`, already
    # extracted above), not the test's own PIN_1_6_0_VERSION_BINDING_
    # PARAGRAPH literal -- the literal is what THIS test expects to find
    # inside version_binding, so asserting against it can never detect a
    # future revision that duplicates the row_addressability qualifier
    # INTO version_binding as well (the pin's own `in` substring check
    # would stay green either way).
    assert "row_addressability" not in version_binding, (
        "versioning.version_binding must not carry the D-3(vii) row_addressability qualifier -- "
        "it is a same-label addendum to structured_operations.upsert only (completion condition 2), "
        "never a new 1.6.0-labelled obligation"
    )
    # Phase 11 WP-1 (work order §7.1 訂正註 2026-09-24, 監督裁定 1): scoped to
    # the 1.6.0 paragraph alone, not the whole version_binding string -- the
    # 1.9.0 paragraph (design docs/design/PHASE11_MIN_COMMON_PROFILE_V1.md
    # §6.2 (1)) legitimately names atomic_mutation as one of
    # common_baseline.capabilities' 8 members, an unrelated fact from the
    # D-3(vii) leak this assertion originally guards against.
    _1_6_0_start = version_binding.index("Only an implementation declaring 1.6.0")
    _1_6_0_end = version_binding.index("Only an implementation declaring", _1_6_0_start + 1)
    version_binding_1_6_0_paragraph = version_binding[_1_6_0_start:_1_6_0_end]
    assert "atomic_mutation" not in version_binding_1_6_0_paragraph, (
        "versioning.version_binding's 1.6.0 paragraph must not carry the D-3(vii) atomic_mutation "
        "qualifier -- it is a same-label addendum to structured_operations.upsert only (completion "
        "condition 2), never a new 1.6.0-labelled obligation. (A later version's own paragraph -- "
        "e.g. 1.9.0's common_baseline.capabilities enumeration -- may legitimately name "
        "atomic_mutation for an unrelated reason; this check is scoped to the 1.6.0 paragraph alone.)"
    )
    assert "mutation_classes.declaration_required" not in upsert, (
        "the D-3(vii) addendum must not cite mutation_classes.declaration_required as its authority (v1.3 G9)"
    )


# ---------------------------------------------------------------------------
# Phase 9 WP-1 (contract 1.7.0, docs/work-orders/WORK_ORDER_PHASE9_CONTRACT_170_V1.md
# v1.0 (v1.3 aligned) §2 WP-1 (5); design docs/design/
# PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md §3 D-1..D-9):
# literal string pins for the requester-finalized English "契約文案" blocks --
# copied verbatim from the design document (standing discipline 4; no
# paraphrase). Unlike the phase 6 PIN blocks above, these blocks are plain
# running prose in the design doc itself (no backtick/`**` markdown), so no
# additional normalization beyond whitespace-collapse is needed for most of
# them; `_normalize_prose_for_pin` is still used for consistency (it is a
# no-op on backtick/`**` for text that has none).
# ---------------------------------------------------------------------------

#
# Phase 10 WP-5b (contract 1.8.0, supervisor ruling 2026-09-08): TRUNCATED
# from its original end -- the trailing sentence ("An implementation still
# declaring 1.6.0 is not held to any 1.7.0-only obligation retroactively.")
# is no longer textually adjacent to this paragraph in the live contract:
# monitor-finalized fixed text (5) (scratchpad/phase10/fixed-text-1.8.0.md)
# is inserted directly after this paragraph and before that sentence
# (supervisor ruling item 1: "1.7.0 の段落の直後(遡及不適用の列挙の前)"), so
# a pin ending in that sentence could no longer match as one contiguous
# substring. That sentence (now widened to add ", or 1.8.0-only") is pinned
# separately below as PIN_1_7_0_RETROACTIVE_DENIAL_ROW_1_6_0, checked with
# plain `in version_binding` containment -- the same non-contiguous style
# already used for the 1.1.0-1.4.0 rows in this same test.
PIN_1_7_0_VERSION_BINDING_PARAGRAPH = (
    "Only an implementation declaring 1.7.0 or higher additionally claims conformance to the obligations 1.7.0 introduces (subordinate ruling 12). Two of those obligations are unconditional in the same sense as every obligation enumerated above -- they bind simply by declaring 1.7.0, independent of any capability's own status: (a) every denial it answers with VALIDATION_FAILED, IDENTIFIER_INVALID or CAPABILITY_UNSUPPORTED carries the details keys errors.details_vocabulary requires for that code, with violated_declaration drawn from the closed vocabulary named there, and carries no row value, no suggested value, no corrective action and no internal name; and (b) every successful QueryResult, MutationResult and SchemaOperationResult it returns carries request_id, the same identifier its own audit evidence for that request carries. The remaining 1.7.0 obligations are conditional, in the same sense 1.4.0's and 1.6.0's own conditional lists are: they bind only insofar as the implementation's own capabilities() declares the named capability -- or, where two are named, both of them -- as something other than unavailable. Where it declares constraint_declarations and schema_operations both as something other than unavailable: (1) a create_entity it executes accepts field_constraints, an add_field and an alter_field it executes accept enum and nullable, each field is created or altered with the constraints declared there, those constraints are enforced on every value written to that field, and an alter_field whose declared constraints existing rows would violate is refused in full with CONFLICT, changing nothing. Where it declares constraint_declarations and application_catalog both as something other than unavailable: (2) every EntityDescriptor it returns carries field_constraints, total over that entity's own fields, reporting nullable: true and no enum for a field that declares neither. Where it declares dry_run as something other than unavailable: (3) a request carrying dry_run receives the decision the identical request without it would receive -- the same code and the same details on a refusal, the same affected count on a success -- and leaves no externally visible state change, subject to the two consumptions structured_operations.dry_run.external_effects names; and a plan it returns is deterministic, and is verified by recomputation on the real request, refusing with PRECONDITION_FAILED where it no longer agrees. Where it declares idempotency as something other than unavailable: (4) an idempotency_key is recorded with a digest of the request it accompanied, in the same transaction as that request's own effects; the same key with the same digest, resent within idempotency_retention_ms, returns the original result without re-executing, including the original request_id; and the same key with a different digest is refused with CONFLICT. Where it declares request_budget as something other than unavailable: (5) a budget narrows a bound downward only, a budget above the deployed value or naming a class that does not apply to that endpoint is refused with VALIDATION_FAILED, and exceeding a narrowed bound is refused with LIMIT_EXCEEDED naming that limit class. 1.7.0 introduces no obligation on what a client must send: dry_run, plan, budget, field_constraints, enum, nullable, and SchemaOperationRequest.idempotency_key are optional wherever they appear, and a request valid under 1.6.0 stays valid."
)

PIN_1_7_0_VIOLATED_DECLARATION_VOCABULARY = (
    "A closed vocabulary of eleven values naming which declaration a denial reports as violated: request_schema (the request does not match this contract's own request schema for that endpoint), identifier_syntax (an identifier does not match the identifier syntax this contract declares), field_type (a value does not match the field's declared type), enum (a non-null value is not a member of the field's declared enum), nullable (a null was written to, or a required value omitted from, a field declared nullable: false), capability (this deployment does not provide the operation or field the request names), budget (the request's own budget declaration is itself invalid -- a class that does not apply to this endpoint, a value above the deployed bound, or a non-integer), unsupported_field (a field this version gives no meaning to, carried where the request schema can still receive it), plan (a plan token does not match the request and schema state it is presented against), idempotency_key (the same key was resent with a different request digest), and constraint_declaration (a field_constraints, enum or nullable declaration is itself invalid: an enum on a field whose type admits none, an empty or duplicated enum, a member outside the field's declared type, or a declaration naming a field the request does not create). The required-key rules above bind VALIDATION_FAILED, IDENTIFIER_INVALID and CAPABILITY_UNSUPPORTED only; any other code's denial may carry violated_declaration drawn from this same vocabulary without being required to -- PRECONDITION_FAILED carries plan, and CONFLICT carries idempotency_key, or enum/nullable where an alter_field is refused because existing rows would violate the constraints it declares. Every value a details key carries under this vocabulary is a statement of declared fact: never a row value, never a suggested value, never a corrective action, never SQL, and never an internal name (SI-10 constrains the content of every details value regardless of key name, as errors.details_vocabulary.open already states)."
)

PIN_1_7_0_OBLIGATIONS_NOTE = (
    "obligations is a machine-readable index of what version_binding states in prose: for each version label, the numbered contract decision that introduced it, the obligations that bind unconditionally, and the obligations that bind only where the named capabilities are declared as something other than unavailable. Where an entry names more than one capability, all of them must be so declared for that obligation to bind. This index is derived from version_binding and does not replace it: every limiting clause, exception, same-label addendum and scoping sentence lives in the prose, and where the two could be read as disagreeing, the prose is the contract. The two are held in agreement mechanically -- the set of version labels must match between them, and so must each version's own count of unconditional obligations, where the prose states one."
)

PIN_1_7_0_REQUEST_BUDGET = (
    "budget lets one request ask for a smaller bound than the deployment's own, and only a smaller one. Where a request carries budget.<class>, the bound in force for that request is the smaller of the deployment's declared value for that class and the requested value; a request whose budget.<class> exceeds the deployment's own declared value is refused with VALIDATION_FAILED and details.violated_declaration: budget, rather than being silently reduced -- a client that asked for more than the deployment allows has misread the deployment's own declaration, and telling it so is more useful than granting it less than it asked for. Exceeding a bound that is in force because a budget narrowed it is refused exactly as exceeding the deployed bound is: LIMIT_EXCEEDED with details.limit_class naming that class, without distinguishing which of the two values was the smaller. Three classes are budgetable in this version: result_items, execution_ms and batch_items. Each applies only where it has meaning: result_items and execution_ms on a query; execution_ms and batch_items on a single-entity or cross-entity mutation; execution_ms alone on a schema operation. result_items is not budgetable on a mutation: it bounds the rows a query returns, and this version does not give one request a way to narrow how many rows its own mutation may affect. A budget naming a class that does not apply to the endpoint it was sent to, or carrying a value that is not an integer of at least 1, is refused with VALIDATION_FAILED, details.violated_declaration: budget and details.field naming that class within budget; it is not ignored. Every one of those refusals belongs to validating the request itself: a budget is checked where this contract's own request shape is checked, before target existence, destructive confirmation and precondition evaluation, so a request that is both unconfirmed and carrying an invalid budget is refused for the budget first. budget never raises a bound, never introduces a class outside limits.classes, and never changes what this deployment declares at capability discovery -- the declared values remain the deployment's own, and a budget is one request's own narrowing of them."
)

PIN_1_7_0_DRY_RUN_DECISION = (
    "dry_run asks the service to reach the same decision it would reach for the identical request without it, and then to leave nothing behind. A dry-run request is subject to the same gates a real one is -- authentication, role, request rate and concurrency, request size, operation depth, request shape, capability availability, and validation -- and any refusal it receives is the refusal the real request would receive, with the same code and the same details: authorization refusals, destructive-confirmation refusals, precondition refusals and limit refusals are all part of what a dry run decides, not steps it skips. Where it is not refused, it answers with the same response schema the real request answers with, carrying committed: false, the affected count the real request would have produced, and a plan. A dry-run mutation does not carry assigned_addresses: the addresses a real execution would assign are not settled, and reporting them would be a false statement rather than a preview. A dry-run schema operation carries descriptor, the EntityDescriptor the entity would have afterwards. Its revision is the Application's schema revision as it stands now -- the revision the plan was taken against -- and not the revision the operation would establish, which for the same reason assigned_addresses is withheld is not settled until it commits."
)

PIN_1_7_0_DRY_RUN_EXTERNAL_EFFECTS = (
    'A dry run leaves no externally visible state change: no row, no catalog entry, no schema revision, no idempotency record, and no audit event is created, changed or removed by it. Two consumptions are deliberately outside that statement. First, a dry run is a request, and consumes this deployment\'s own request-rate and concurrency bounds exactly as a real request does -- a bound a client could avoid by asking for a dry run would not be a bound. Second, where an implementation assigns addresses from a non-transactional sequence, a dry run may consume a value from that sequence; it never returns the value it consumed, and the consumed value is not reused, which is what EntityDescriptor.address_reuse: never already declares. An idempotency_key presented on a dry-run request is neither recorded nor looked up: the dry run is not deduplicated against earlier requests, and does not make a later resend of the same key a duplicate. This is stated rather than left to the reader as "ignored", because a client that resends after a dry run must be able to know that its first real send is genuinely the first.'
)

PIN_1_7_0_DRY_RUN_PLAN = (
    "plan is an opaque but deterministic token: it is computed from the request itself together with the Application's own schema revision -- the same value SchemaOperationResult.revision reports -- as it stood when the request was decided, and holds no server-side state -- there is nothing on the service that expires, is evicted, or must be cleaned up, and two dry runs of the identical request against unchanged schema return the identical token. The token is computed over this request as this contract defines it -- the request object this endpoint's own request schema names, not the bytes a particular transport delivered it in -- taking every field of that object except plan itself, which cannot contain its own digest, and dry_run, whose value necessarily differs between the dry run and the real request it plans. Every other field, including budget, transaction, confirmation and idempotency_key, is part of what the token commits to: a real request differing from the dry run in any of them is a different request, and the token no longer agrees. The digest is taken over that object serialized with its keys in lexicographic order, without insignificant whitespace, and without escaping non-ASCII characters, as UTF-8; the token an implementation returns is its own representation of that digest together with the revision. A client may present the token it received back on the real request. Where it does, the service recomputes the token by the same rule and executes only if the two agree; where they disagree -- because the request differs, or because any schema operation on that Application advanced its revision in between -- the request is refused with PRECONDITION_FAILED and details.violated_declaration: plan, and nothing is executed. Because that revision is the Application's own, a schema operation on any entity of the same Application invalidates a plan taken against any other: the token names the Application's schema state, not one entity's. A plan is a precondition, and is evaluated where destructive_confirmation.evaluation_order places precondition evaluation -- after confirmation validity and before execution -- so a request that is both unconfirmed and carrying a stale plan is refused for the missing confirmation first. A plan is never required: a real request that omits it executes on the service's own current state, exactly as it did before this version."
)

PIN_1_7_0_IDEMPOTENCY_RECORD = (
    "An idempotency_key is recorded together with a deterministic digest of the request it was sent with, and the record is written in the same transaction as the effects it records: a key is present exactly when the request it names committed. A request that fails leaves no record, so resending it is a new attempt, not a duplicate. Within idempotency_retention_ms of the recorded request, resending the same key with the same request digest returns that original request's own recorded result -- the whole MutationResult or SchemaOperationResult, including its request_id -- without executing anything a second time. Resending the same key with a different request digest is refused with CONFLICT and details.violated_declaration: idempotency_key; the denial does not disclose the earlier request. A key whose retention has elapsed is treated as absent: the resend is a new request, and an implementation may delete elapsed records lazily. A key is scoped to one Application: the same key presented under a different credential of the same Application is the same key, because the atomic unit this contract defines is scoped to one Application's storage. Where recording a new key would exceed idempotency_entries after elapsed records are reclaimed, the request is refused with LIMIT_EXCEEDED and details.limit_class: idempotency_entries, before it executes rather than after. A replayed SchemaOperationResult carries the revision the original execution produced, which is the revision that execution established, not necessarily the entity's revision now. The digest is taken over the request object this endpoint's own request schema names, excluding idempotency_key itself, plan and dry_run, and is otherwise computed exactly as structured_operations.dry_run.plan describes: every other field, including budget, transaction and confirmation, is part of what a resend must match. A resend that matches a retained record is answered from that record before target existence, destructive confirmation and any precondition are evaluated -- after this request's own authentication, authorization and bounds, which it consumes like any other request. Without that placement a resent destructive operation could not be answered from its record at all: its target no longer exists, and destructive_confirmation.phrase_construction recomputes a phrase against state the first execution already changed."
)

PIN_1_7_0_IDEMPOTENCY_CORRELATION = (
    "Idempotency and audit evidence are correlated through request_id, not through the key: a resend answers with the original execution's own request_id, which is the identifier that execution's audit events carry, so a client holding only its own responses can tell which single execution its repeated sends resolved to. The key itself is not written to audit events."
)

PIN_1_7_0_IDEMPOTENCY_KEY_SECRECY = (
    "A client MUST NOT place a credential, token, password, private key, or any other secret in an idempotency_key. The key is not a member of audit.forbidden_fields, and this version writes it neither to audit events nor to any response -- but neither of those facts makes a secret safe to use as a key. A key is a client-chosen name for one request, is compared for equality against other clients' keys within the same Application, and may be retained for as long as idempotency_retention_ms declares; a value that must not be guessable, resent, or retained does not belong in it."
)

PIN_1_7_0_FIELD_CONSTRAINTS_REQUEST = (
    "field_constraints declares, per field, the two constraints this version defines: nullable (whether that field accepts a null value) and enum (the closed set of non-null values that field accepts). On create_entity it is an object keyed by field name and may be partial -- any name in fields it omits is created with no enum and nullable: true. On add_field and alter_field the same two constraints are carried as the request's own top-level enum and nullable, for the single field the operation names. nullable defaults to true, which is what a field created before this version, or created without the key, already is: this names an existing default rather than introducing a new one. A field declared nullable: false requires a non-null value on insert -- an operation that omits it is refused -- and cannot be set to null by update or upsert. An upsert that resolves to an insert is refused on the same rule; an upsert that resolves to an update is not, because it writes no value to that field. enum constrains non-null values only; whether null is accepted is decided by nullable alone, and a field may declare both. An enum is a non-empty list of distinct values, each of the field's own declared type, and is declarable only on a field whose type is string, integer, number or boolean: an enum on an object, array or json field, an empty or duplicated enum, an enum member outside the field's declared type, a field_constraints naming a field the request's own fields does not name, or a field_constraints sent without fields, each fails VALIDATION_FAILED; none of them is silently ignored. Constraints bind writes only: a query predicate is never refused for carrying a value outside a field's enum -- such a value simply matches no row."
)

PIN_1_7_0_FIELD_CONSTRAINTS_ENTITY_DESCRIPTOR = (
    "field_constraints reports, for every one of this entity's own fields, the constraints currently in force on it: nullable, always present, and enum, present only on a field that declares one. Like field_types, and unlike the request-side object of the same name, this object is always total over that entity's own fields. What a client declared -- through SchemaOperationRequest.field_constraints on create_entity, or enum/nullable on add_field or alter_field -- is what the catalog reports back, and a field for which nothing was declared reports nullable: true and no enum. This is the same-version catalog reporting the 1.6.0 field_types description reserves for whichever later version gives schema operations a notion of nullability: this is that version, and the notion it gives is exactly these two constraints -- not default values, and no notion of a required field beyond what nullable: false itself requires on insert."
)

PIN_1_7_0_ALTER_FIELD = (
    "alter_field redeclares the constraints of one existing field: it sets, replaces or clears that field's enum, and switches its nullable. It does not redeclare that field's type -- an alter_field carrying field_type fails VALIDATION_FAILED -- because converting values already stored under one type into another is not defined by this version. Before it changes anything, an alter_field verifies every existing row of the entity against the constraints it would establish, within the same transaction as the change itself; where even one row would violate them, the whole operation is refused with CONFLICT and nothing is changed. The denial names the field and which declaration it would violate, and never the offending values, nor how many rows there are. A committed alter_field advances the entity's schema revision. A constraint the request omits is left as it is; enum: null clears the field's enum, and on add_field enum: null means the same as omitting it. An add_field declaring nullable: false on an entity that already holds rows is refused with CONFLICT on the same rule, because every existing row would hold null in the new field. An alter_field carrying neither enum nor nullable declares nothing and is refused with VALIDATION_FAILED; it does not advance the schema revision."
)

# Work order §6 訂正註 6 (supervisor ruling, post-WP-1-audit, 2026-09-07): the
# 5 supervisor-finalized confirmed-prose values recorded in design v1.4 §5
# U-8 #30-#32 (WP-1a review L-6 / M-4) were placed in the contract during
# WP-1 implementation but never gained a string pin here -- the audit's own
# mutation (`endpoint_fields_note.requires_capability`'s "must" -> "should",
# changed identically in all 3 packaged copies) stayed green under the full
# suite, showing the normative strength of that sentence was unpinned.
# Standing discipline 4 applies exactly as it does to the §3 D-1..D-9
# blocks above; copied verbatim from design v1.4 §5 U-8 #30-#32, which
# itself records the contract JSON's own values verbatim.
PIN_1_7_0_SCHEMA_OPERATION_RESULT_DESCRIPTOR = (
    "The entity's descriptor -- as it would read afterwards (dry_run), or as committed."
)

# Phase 11 WP-1 (design docs/design/PHASE11_MIN_COMMON_PROFILE_V1.md §6.3,
# §15 v1.0 confirmation, requester ruling U-4 = (α)): the 1.7.0-era pin this
# constant replaced (removed in the same commit) is superseded, whole-value,
# by the 1.9.0 (α) text below --
# `operation_catalog_url` becomes a 1.9.0-or-higher obligation, so the pin
# moves to the new text in the same commit as the version bump, the same
# version-flip pin-migration discipline this file already applies elsewhere
# (e.g. PIN_1_6_0_VERSION_BINDING_PARAGRAPH's own history). Copied verbatim
# from design §6.3's (α) code block; the (β) alternative the design also
# records is not pinned here because it was not the ruling.
PIN_1_9_0_CAPABILITY_DOCUMENT_OPERATION_CATALOG_URL = (
    "Required of an implementation declaring 1.9.0 or higher: the absolute URL at which a client "
    "reaches this deployment's own operation_catalog operation. The document served there is "
    "byte-identical to the derived operation catalog of the contract version this capability "
    "document declares. The URL is not required to sit under this deployment's surfaces.data.base_url: "
    "a deployment serving the document from elsewhere -- a content delivery network, for instance -- "
    "names that URL here. An implementation declaring a lower version may publish it or not, as before."
)

PIN_1_7_0_ENDPOINT_FIELDS_NOTE_ROLES = (
    "roles lists the roles an endpoint accepts a credential of, restating auth in the vocabulary of "
    "security.roles (application meaning both runtime and developer). Being accepted is not a promise "
    "of success: an accepted role is still subject to every other gate the endpoint applies, and auth "
    "remains the prose the two are held in agreement with."
)

PIN_1_7_0_ENDPOINT_FIELDS_NOTE_REQUIRES_CAPABILITY = (
    "requires_capability names the capabilities a deployment must declare as something other than "
    "unavailable for the endpoint to be provided at all; where a deployment declares any of them "
    "unavailable, the endpoint is not provided and a request to it is refused with CAPABILITY_UNSUPPORTED. "
    "It does not list the capabilities that merely extend an endpoint when present -- dry_run, idempotency, "
    "request_budget and constraint_declarations -- which are discovered from the capability document and "
    "from versioning.obligations."
)

PIN_1_7_0_ENDPOINT_FIELDS_NOTE_ATOMICITY = (
    "atomicity places each endpoint under transactions: atomic (one atomic unit per request), none (a "
    "read, or a control operation that declares no unit), or atomic_unless_best_effort (atomic unless a "
    "capability declaring best_effort semantics is invoked for that request)."
)


def test_contract_pins_the_requester_finalized_1_7_0_prose():
    """Phase 9 WP-1 completion conditions 7, 8, 9, 10, 21: the
    requester-finalized confirmed-prose blocks for contract 1.7.0 are
    present verbatim (normalized) at their specific contract JSON paths."""
    contract = json.loads((ROOT / "spec" / "data-service-api.v1.json").read_text())

    version_binding = contract["versioning"]["version_binding"]
    assert _normalize_prose_for_pin(PIN_1_7_0_VERSION_BINDING_PARAGRAPH) in _normalize_prose_for_pin(version_binding), (
        "versioning.version_binding no longer contains the requester-finalized 1.7.0 paragraph verbatim"
    )
    for row in (
        PIN_1_7_0_RETROACTIVE_DENIAL_ROW_1_1_0,
        PIN_1_7_0_RETROACTIVE_DENIAL_ROW_1_2_0,
        PIN_1_7_0_RETROACTIVE_DENIAL_ROW_1_3_0,
        PIN_1_7_0_RETROACTIVE_DENIAL_ROW_1_4_0,
        PIN_1_7_0_RETROACTIVE_DENIAL_ROW_1_6_0,
    ):
        assert row in version_binding, f"versioning.version_binding is missing retroactive-denial row: {row!r}"

    obligations_note = contract["versioning"]["obligations_note"]
    assert _normalize_prose_for_pin(PIN_1_7_0_OBLIGATIONS_NOTE) in _normalize_prose_for_pin(obligations_note)

    request_budget = contract["limits"]["request_budget"]
    assert _normalize_prose_for_pin(PIN_1_7_0_REQUEST_BUDGET) in _normalize_prose_for_pin(request_budget)

    details_vocabulary = contract["errors"]["details_vocabulary"]
    violated_declaration_vocabulary = details_vocabulary["violated_declaration_vocabulary"]
    assert _normalize_prose_for_pin(PIN_1_7_0_VIOLATED_DECLARATION_VOCABULARY) in _normalize_prose_for_pin(
        violated_declaration_vocabulary
    )
    # the closed vocabulary is exactly eleven words, named in the pin itself.
    assert violated_declaration_vocabulary.count("eleven values") == 1

    dry_run = contract["structured_operations"]["dry_run"]
    assert _normalize_prose_for_pin(PIN_1_7_0_DRY_RUN_DECISION) in _normalize_prose_for_pin(dry_run["decision"])
    assert _normalize_prose_for_pin(PIN_1_7_0_DRY_RUN_EXTERNAL_EFFECTS) in _normalize_prose_for_pin(
        dry_run["external_effects"]
    )
    assert _normalize_prose_for_pin(PIN_1_7_0_DRY_RUN_PLAN) in _normalize_prose_for_pin(dry_run["plan"])

    idempotency = contract["structured_operations"]["idempotency"]
    assert _normalize_prose_for_pin(PIN_1_7_0_IDEMPOTENCY_RECORD) in _normalize_prose_for_pin(idempotency["record"])
    assert _normalize_prose_for_pin(PIN_1_7_0_IDEMPOTENCY_CORRELATION) in _normalize_prose_for_pin(
        idempotency["correlation"]
    )
    assert _normalize_prose_for_pin(PIN_1_7_0_IDEMPOTENCY_KEY_SECRECY) in _normalize_prose_for_pin(
        idempotency["key_secrecy"]
    )

    field_constraints_request = contract["schemas"]["SchemaOperationRequest"]["properties"]["field_constraints"][
        "description"
    ]
    assert _normalize_prose_for_pin(PIN_1_7_0_FIELD_CONSTRAINTS_REQUEST) in _normalize_prose_for_pin(
        field_constraints_request
    )
    field_constraints_entity_descriptor = contract["definitions"]["EntityDescriptor"]["properties"][
        "field_constraints"
    ]["description"]
    assert _normalize_prose_for_pin(PIN_1_7_0_FIELD_CONSTRAINTS_ENTITY_DESCRIPTOR) in _normalize_prose_for_pin(
        field_constraints_entity_descriptor
    )

    alter_field = contract["structured_operations"]["alter_field"]
    assert _normalize_prose_for_pin(PIN_1_7_0_ALTER_FIELD) in _normalize_prose_for_pin(alter_field)


def test_contract_pins_the_supervisor_finalized_1_7_0_prose():
    """Work order §6 訂正註 6 (supervisor ruling, post-WP-1-audit): pins the
    5 supervisor-finalized confirmed-prose values recorded in design v1.4
    §5 U-8 #30-#32 -- schemas.SchemaOperationResult.properties.descriptor.
    description, schemas.CapabilityDocument.properties.operation_catalog_url.
    description, and the 3 endpoint_fields_note values (roles /
    requires_capability / atomicity) -- verbatim (normalized). The audit's
    own mutation (endpoint_fields_note.requires_capability's "must" ->
    "should", changed identically in all 3 packaged copies) demonstrated
    these 5 values had no string pin: the full suite stayed green.

    Phase 11 WP-1 (design docs/design/PHASE11_MIN_COMMON_PROFILE_V1.md §6.3,
    §15 v1.0 confirmation): of those original 5, the
    operation_catalog_url.description value is superseded whole-value by
    contract 1.9.0's (α) obligation text (requester ruling U-4 = (α)); the
    other 4 stay pinned to their original 1.7.0-era text unchanged."""
    contract = json.loads((ROOT / "spec" / "data-service-api.v1.json").read_text())

    descriptor_description = contract["schemas"]["SchemaOperationResult"]["properties"]["descriptor"]["description"]
    assert _normalize_prose_for_pin(PIN_1_7_0_SCHEMA_OPERATION_RESULT_DESCRIPTOR) in _normalize_prose_for_pin(
        descriptor_description
    ), "schemas.SchemaOperationResult.properties.descriptor.description no longer carries the U-8 #30 prose verbatim"

    operation_catalog_url_description = contract["schemas"]["CapabilityDocument"]["properties"][
        "operation_catalog_url"
    ]["description"]
    assert _normalize_prose_for_pin(
        PIN_1_9_0_CAPABILITY_DOCUMENT_OPERATION_CATALOG_URL
    ) in _normalize_prose_for_pin(operation_catalog_url_description), (
        "schemas.CapabilityDocument.properties.operation_catalog_url.description no longer carries the "
        "phase 11 WP-1 (1.9.0, U-4 = (α)) prose verbatim"
    )

    endpoint_fields_note = contract["endpoint_fields_note"]
    assert set(endpoint_fields_note) == {"roles", "requires_capability", "atomicity"}
    for key, pin in (
        ("roles", PIN_1_7_0_ENDPOINT_FIELDS_NOTE_ROLES),
        ("requires_capability", PIN_1_7_0_ENDPOINT_FIELDS_NOTE_REQUIRES_CAPABILITY),
        ("atomicity", PIN_1_7_0_ENDPOINT_FIELDS_NOTE_ATOMICITY),
    ):
        assert _normalize_prose_for_pin(pin) in _normalize_prose_for_pin(endpoint_fields_note[key]), (
            f"endpoint_fields_note.{key} no longer carries the U-8 #32 prose verbatim"
        )


def test_contract_1_7_0_structure_and_additive_only():
    """Phase 9 WP-1 completion conditions 2, 3, 4, 6, 9, 13, 14, 15, 17:
    structural assertions the design work order's completion-condition list
    fixes directly against the parsed contract (as distinct from the
    literal-prose pins above)."""
    contract = json.loads((ROOT / "spec" / "data-service-api.v1.json").read_text())

    # condition 3: capability_status.defined gains exactly 3 new words -> 14.
    defined = contract["capability_status"]["defined"]
    assert len(defined) == 14, sorted(defined)
    for name in ("constraint_declarations", "dry_run", "request_budget"):
        assert name in defined

    # condition 4: limits.classes gains enum_members -> 17; example_profile -> 16.
    assert len(contract["limits"]["classes"]) == 17
    assert "enum_members" in contract["limits"]["classes"]
    assert len(contract["limits"]["example_profile"]) == 16
    assert contract["limits"]["example_profile"]["enum_members"] == 64
    assert "enum_members" in contract["limits"]

    # condition 6: errors.details_vocabulary gains 5 new blocks.
    dv = contract["errors"]["details_vocabulary"]
    for key in ("VALIDATION_FAILED", "IDENTIFIER_INVALID", "CAPABILITY_UNSUPPORTED", "violated_declaration_vocabulary", "layer_rule"):
        assert key in dv, f"errors.details_vocabulary is missing {key!r}"
    assert set(dv["VALIDATION_FAILED"]) == {"violated_declaration", "field", "declared_type", "observed_type"}
    assert set(dv["IDENTIFIER_INVALID"]) == {"violated_declaration", "field"}
    assert set(dv["CAPABILITY_UNSUPPORTED"]) == {"violated_declaration", "field"}
    # existing LIMIT_EXCEEDED / common_optional / open / cross_reference untouched (禁止事項 2).
    assert dv["LIMIT_EXCEEDED"] == {
        "limit_class": "string, required. Must be a member of limits.classes -- the specific finite-resource class this request exceeded."
    }

    # condition 9: structured_operations.alter_field independent section.
    assert isinstance(contract["structured_operations"]["alter_field"], str)
    assert contract["structured_operations"]["alter_field"]

    # condition 2 / 15 / 17 / new-field additive check: schema additions are
    # all optional, and `required` arrays are byte-for-byte unchanged (this
    # is also checked exhaustively by the WP-1a mutation-testing report; here
    # we pin the specific `required` arrays completion condition 2 names).
    for schema_name, expected_required in (
        ("QueryRequest", ["select"]),
        ("MutationRequest", ["operations"]),
        ("ScopedMutationRequest", ["operations"]),
        ("SchemaOperationRequest", ["operation", "entity"]),
        ("QueryResult", ["items", "next_page"]),
        ("MutationResult", ["committed", "affected"]),
        ("SchemaOperationResult", ["committed", "revision"]),
    ):
        assert contract["schemas"][schema_name]["required"] == expected_required, (
            f"schemas.{schema_name}.required changed -- 1.7.0 additions must all be optional"
        )
    for field, schema_name in (
        ("field_constraints", "SchemaOperationRequest"),
        ("enum", "SchemaOperationRequest"),
        ("nullable", "SchemaOperationRequest"),
        ("dry_run", "SchemaOperationRequest"),
        ("plan", "SchemaOperationRequest"),
        ("budget", "SchemaOperationRequest"),
        ("idempotency_key", "SchemaOperationRequest"),
        ("dry_run", "MutationRequest"),
        ("plan", "MutationRequest"),
        ("budget", "MutationRequest"),
        ("dry_run", "ScopedMutationRequest"),
        ("plan", "ScopedMutationRequest"),
        ("budget", "ScopedMutationRequest"),
        ("budget", "QueryRequest"),
        ("request_id", "QueryResult"),
        ("request_id", "MutationResult"),
        ("plan", "MutationResult"),
        ("request_id", "SchemaOperationResult"),
        ("plan", "SchemaOperationResult"),
        ("descriptor", "SchemaOperationResult"),
    ):
        assert field in contract["schemas"][schema_name]["properties"], f"{schema_name}.{field} missing"

    assert contract["schemas"]["SchemaOperationRequest"]["properties"]["idempotency_key"] == {
        "type": "string",
        "maxLength": 128,
    }, "SchemaOperationRequest.idempotency_key must be the same shape as the existing MutationRequest/ScopedMutationRequest one"

    # condition 13/14: 20 endpoint entries all carry roles/requires_capability/atomicity,
    # atomicity drawn from the fixed 3-word vocabulary. Phase 11 WP-1 (design
    # docs/design/PHASE11_MIN_COMMON_PROFILE_V1.md §6.6) adds endpoints.
    # operation_catalog, moving the count from 19 (7 + 12) to 20 (8 + 12).
    atomicity_vocab = {"atomic", "none", "atomic_unless_best_effort"}
    n = 0
    for section in ("endpoints", "control_endpoints"):
        for name, entry in contract[section].items():
            n += 1
            assert "roles" in entry and entry["roles"], f"{section}.{name}.roles missing/empty"
            assert "requires_capability" in entry, f"{section}.{name}.requires_capability missing"
            assert entry["atomicity"] in atomicity_vocab, f"{section}.{name}.atomicity {entry['atomicity']!r} not in {atomicity_vocab}"
    assert n == 20

    # condition 33 (capability_status.defined naming, via roles) and D-8:
    # roles values are drawn only from the 4-word role enum.
    role_vocab = {"runtime", "developer", "control", "audit"}
    for section in ("endpoints", "control_endpoints"):
        for name, entry in contract[section].items():
            assert set(entry["roles"]) <= role_vocab, f"{section}.{name}.roles has a value outside {role_vocab}"

    # condition 15: destructive_confirmation.applies_to unchanged (1 char),
    # applies_to_structured is 1:1 with it.
    dc = contract["destructive_confirmation"]
    assert dc["applies_to"] == [
        "Mutation.operation == \"delete\"",
        "ScopedMutation.operation == \"delete\"",
        "SchemaOperationRequest.operation in (\"drop_entity\", \"drop_index\")",
        "CredentialRevokeRequest revoking the last remaining active control credential",
        "future destructive operations inherit this same definition",
    ], "destructive_confirmation.applies_to must not change even 1 character (existing array preserved verbatim)"
    assert len(dc["applies_to_structured"]) == len(dc["applies_to"])

    # condition 33: capability_status.defined has 14 words, all named by
    # `roles`/`requires_capability` construction above is exercised
    # separately in test_operation_catalog_register.py; here we just pin
    # the closed count again for a reader of this file alone.
    assert len(contract["capability_status"]["defined"]) == 14
