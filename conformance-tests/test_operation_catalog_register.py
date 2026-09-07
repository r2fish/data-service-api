"""Register test for `spec/OPERATION_CATALOG.json`, the R-8 derived operation
catalog (contract 1.7.0, subordinate ruling 12; design docs/design/
PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md §3 D-8; work order
docs/work-orders/WORK_ORDER_PHASE9_CONTRACT_170_V1.md §2 WP-1 (7)).

`tools/contract_catalog.py` is a pure structural projection of
`spec/data-service-api.v1.json`'s `endpoints`/`control_endpoints` sections.
This file fixes eight things (WP-1a rework adds (vii)/(viii) to the work
order's original six-item enumeration):

  (i)   Every operation's `roles` agrees with the contract's own `auth`
        string at that endpoint, under the same application/control/audit
        role-group mapping the contract itself uses.
  (ii)  Every `requires_capability` value actually names a member of
        `capability_status.defined`.
  (iii) Every `atomicity` value is one of the three fixed words: `atomic`,
        `none`, `atomic_unless_best_effort`.
  (iv)  `destructive_confirmation.applies_to_structured` is 1:1 (same
        length) with the existing `applies_to` array; every element's
        `endpoint` (where present -- the trailing `{"note": ...}` element
        names none) actually names an `endpoints`/`control_endpoints`
        entry; every element's `operation` value(s) actually appear in the
        operation enum the named endpoint's own request schema carries
        (resolved structurally: a schema's own `properties.operation.enum`
        directly, or the `enum` of the `definitions.*` a `$ref`'d array
        item type points to -- `revoke_credential`'s `CredentialRevokeRequest`
        carries no operation-shaped field at all, so only the
        endpoint-existence check applies to that element); and the
        generated catalog's own `destructive: true` record-name set equals
        the (`control.`-qualified where drawn from `control_endpoints`) set
        of endpoint names `applies_to_structured` names -- i.e.
        `tools/contract_catalog.py`'s derivation of `destructive` is
        actually 1:1 with the structured source it claims to derive it
        from.
  (v)   `versioning.obligations`' set of version labels equals the set of
        version labels `versioning.version_binding`'s own prose names via
        "Only an implementation declaring X.Y.Z ... additionally claims
        conformance".
  (vi)  For exactly the versions whose prose carries a "N of those
        obligations are unconditional" count sentence, `obligations`'
        `unconditional` list length agrees with that stated count -- and
        that set of versions has exactly 3 members (1.4.0, 1.6.0, 1.7.0);
        an empty set here would make this assertion vacuously pass, so it
        is asserted non-empty (and exactly 3) directly.
  (vii) `versioning.obligations`' 1.7.0 entry's `conditional` list is
        pinned structurally: every element's `capability` value(s) actually
        name a member of `capability_status.defined`; the list has exactly
        5 elements; and the 2 elements whose `capability` is a 2-element
        conjunction are exactly `["constraint_declarations",
        "schema_operations"]` and `["constraint_declarations",
        "application_catalog"]` (D-8 (2)'s own "capability を配列にする理由").
  (viii) The top-level `endpoint_fields_note` object exists and carries all
        3 keys (`roles`, `requires_capability`, `atomicity`), each a
        non-empty string.

Plus the byte-identical regeneration check: `spec/OPERATION_CATALOG.json`
must match a fresh run of `tools/contract_catalog.py` exactly.

No `@pytest.mark.condition(...)` marker is used anywhere in this file
(design §6.5: this is repository hygiene, an implementation-independent
requirement on the derived artifact itself, not a condition any peer
adapter is judged against -- same treatment as phase 8's own catalog-shaped
register tests).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import contract_catalog  # noqa: E402  (path insert above must run first)

CONTRACT_PATH = ROOT / "spec" / "data-service-api.v1.json"
CATALOG_PATH = ROOT / "spec" / "OPERATION_CATALOG.json"

_ROLE_GROUPS = {"application": {"runtime", "developer"}, "control": {"control"}, "audit": {"audit"}}
_ATOMICITY_VOCAB = {"atomic", "none", "atomic_unless_best_effort"}


def _contract():
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def _roles_expected_from_auth(auth: str) -> set[str]:
    expected: set[str] = set()
    for token in re.split(r"\s+or\s+", auth):
        token = token.strip()
        if token in _ROLE_GROUPS:
            expected |= _ROLE_GROUPS[token]
        elif token in {"runtime", "developer", "control", "audit"}:
            expected.add(token)
        else:
            raise AssertionError(f"unrecognized auth token {token!r} in {auth!r}")
    return expected


def _all_endpoint_entries(contract):
    """Yield (catalog_name, entry) for every endpoints.* and
    control_endpoints.* entry, using the same 'control.<name>' disambiguation
    tools/contract_catalog.py uses for the duplicate 'audit_query' name."""
    for name, entry in contract["endpoints"].items():
        yield name, entry
    for name, entry in contract["control_endpoints"].items():
        yield f"control.{name}", entry


def test_scanner_finds_at_least_one_endpoint():
    """Non-vacuity guard: there must be at least one endpoint entry, or every
    check below would vacuously pass over an empty set."""
    contract = _contract()
    entries = list(_all_endpoint_entries(contract))
    assert len(entries) >= 1
    assert len(entries) == 19, f"expected 19 endpoint entries (7 + 12), got {len(entries)}"


def test_operation_catalog_regenerates_byte_identical():
    contract = _contract()
    catalog = contract_catalog.build_catalog(contract)
    rendered = contract_catalog.render(catalog)
    on_disk = CATALOG_PATH.read_text(encoding="utf-8")
    assert rendered == on_disk, (
        f"{CATALOG_PATH} does not match a fresh run of tools/contract_catalog.py -- "
        "re-run `./.venv/bin/python tools/contract_catalog.py` and commit the result"
    )


def test_operation_catalog_roles_agree_with_contract_auth():
    """(i)."""
    contract = _contract()
    mismatched = []
    for name, entry in _all_endpoint_entries(contract):
        expected = _roles_expected_from_auth(entry["auth"])
        actual = set(entry["roles"])
        if actual != expected:
            mismatched.append((name, entry["auth"], sorted(actual), sorted(expected)))
    assert not mismatched, f"roles do not agree with auth for: {mismatched}"


def test_operation_catalog_requires_capability_values_are_defined():
    """(ii)."""
    contract = _contract()
    defined = set(contract["capability_status"]["defined"])
    assert defined, "capability_status.defined must not be empty"
    undefined = []
    for name, entry in _all_endpoint_entries(contract):
        for capability in entry["requires_capability"]:
            if capability not in defined:
                undefined.append((name, capability))
    assert not undefined, f"requires_capability names a capability not in capability_status.defined: {undefined}"
    # non-vacuity: at least one endpoint must actually name a capability, or
    # the loop above would trivially pass over nothing but empty lists.
    assert any(entry["requires_capability"] for _, entry in _all_endpoint_entries(contract))


def test_operation_catalog_atomicity_is_the_fixed_three_word_vocabulary():
    """(iii)."""
    contract = _contract()
    bad = []
    for name, entry in _all_endpoint_entries(contract):
        if entry["atomicity"] not in _ATOMICITY_VOCAB:
            bad.append((name, entry["atomicity"]))
    assert not bad, f"atomicity value(s) outside the fixed 3-word vocabulary {_ATOMICITY_VOCAB}: {bad}"
    # non-vacuity: each of the 3 words must actually be used at least once.
    used = {entry["atomicity"] for _, entry in _all_endpoint_entries(contract)}
    assert used == _ATOMICITY_VOCAB, f"expected all 3 atomicity words to be used at least once, got {used}"


def _operation_enum_for(contract, endpoint_name):
    """The set of valid `operation` values for `endpoint_name`'s
    `applies_to_structured` element(s), resolved structurally from the
    request schema the endpoint declares -- either that schema's own
    `properties.operation.enum` directly (e.g. `SchemaOperationRequest`),
    or, for a schema whose mutation vocabulary lives in an array-of-items
    shape (e.g. `MutationRequest.operations` -> each item `$ref`s
    `definitions.Mutation`, itself an object schema carrying its OWN
    `properties.operation.enum`, not a bare enum), that nested enum.
    Returns `None` when the endpoint's own request schema carries no
    operation-shaped field at all."""
    entry = contract["endpoints"].get(endpoint_name) or contract["control_endpoints"].get(endpoint_name)
    assert entry is not None, f"{endpoint_name!r} is not an endpoints/control_endpoints entry"
    request_schema_name = entry.get("request")
    if request_schema_name is None:
        return None
    props = contract["schemas"][request_schema_name]["properties"]
    operation_prop = props.get("operation")
    if operation_prop is not None and "enum" in operation_prop:
        return set(operation_prop["enum"])
    operations_prop = props.get("operations")
    if operations_prop is not None:
        ref = operations_prop.get("items", {}).get("$ref", "")
        if ref.startswith("#/definitions/"):
            definition = contract["definitions"][ref.rsplit("/", 1)[-1]]
            item_operation_prop = definition.get("properties", {}).get("operation")
            if item_operation_prop is not None and "enum" in item_operation_prop:
                return set(item_operation_prop["enum"])
    return None


def test_applies_to_structured_is_1_to_1_with_applies_to():
    """(iv)."""
    contract = _contract()
    dc = contract["destructive_confirmation"]
    assert "applies_to_structured" in dc
    assert len(dc["applies_to_structured"]) == len(dc["applies_to"]), (
        f"applies_to_structured has {len(dc['applies_to_structured'])} elements, "
        f"applies_to has {len(dc['applies_to'])} -- expected a 1:1 correspondence"
    )
    assert len(dc["applies_to"]) >= 1

    endpoint_names_named = set()
    bad_operations = []
    unresolvable_data_plane = []
    for element in dc["applies_to_structured"]:
        endpoint_name = element.get("endpoint")
        if endpoint_name is None:
            continue  # the trailing {"note": ...} element names no endpoint
        in_data_plane = endpoint_name in contract["endpoints"]
        in_control_plane = endpoint_name in contract["control_endpoints"]
        assert in_data_plane or in_control_plane, (
            f"applies_to_structured names endpoint {endpoint_name!r}, which is not an "
            f"endpoints/control_endpoints entry"
        )
        endpoint_names_named.add(endpoint_name)
        operation_value = element["operation"]
        operation_values = operation_value if isinstance(operation_value, list) else [operation_value]
        enum = _operation_enum_for(contract, endpoint_name)
        if enum is None:
            # A data-plane endpoint (`endpoints.*`) multiplexes several
            # operations through its own request schema's `operation`
            # field by construction (that IS what distinguishes a single
            # destructive operation of several non-destructive ones on the
            # same endpoint, e.g. `mutate`'s `delete` among `insert`/
            # `update`/`upsert`) -- an unresolvable enum there means
            # applies_to_structured names the wrong endpoint entirely, not
            # a legitimately schema-less one. Only a control-plane
            # endpoint (`control_endpoints.*`, one fixed action per
            # endpoint, e.g. `revoke_credential`'s `CredentialRevokeRequest`
            # carrying no `operation` field at all) may legitimately lack
            # one; that element's `operation` value then names the
            # endpoint's own fixed action and needs no enum to check
            # against.
            if in_data_plane:
                unresolvable_data_plane.append(endpoint_name)
            continue
        for op in operation_values:
            if op not in enum:
                bad_operations.append((endpoint_name, op, sorted(enum)))
    assert endpoint_names_named, "applies_to_structured names 0 endpoints"
    assert not unresolvable_data_plane, (
        f"applies_to_structured names data-plane endpoint(s) {unresolvable_data_plane} whose own request "
        f"schema carries no resolvable `operation` enum to check the named operation value(s) against"
    )
    assert not bad_operations, (
        f"applies_to_structured names operation value(s) outside the named endpoint's own "
        f"request-schema operation enum (endpoint, bad_operation, expected_enum): {bad_operations}"
    )

    catalog = contract_catalog.build_catalog(contract)
    catalog_destructive_names = {record["name"] for record in catalog["operations"] if record["destructive"]}
    expected_destructive_names = {
        name if name in contract["endpoints"] else f"control.{name}" for name in endpoint_names_named
    }
    assert catalog_destructive_names == expected_destructive_names, (
        f"tools/contract_catalog.py's generated destructive set {sorted(catalog_destructive_names)} does not "
        f"match the set derived from destructive_confirmation.applies_to_structured "
        f"{sorted(expected_destructive_names)}"
    )


_DECLARING_VERSION_RE = re.compile(
    r"[Oo]nly an implementation declaring (\d+\.\d+\.\d+) or higher (?:additionally )?claims conformance to "
    r"the obligations? \d+\.\d+\.\d+ introduce[sd]"
)
_UNCONDITIONAL_COUNT_RE = re.compile(r"(\w+) of those obligations are unconditional")
_COUNT_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9}


def _prose_version_set(version_binding: str) -> set[str]:
    return set(_DECLARING_VERSION_RE.findall(version_binding))


def _prose_unconditional_counts(version_binding: str) -> dict[str, int]:
    """{version: stated_unconditional_count} for exactly the versions whose
    paragraph contains the 'N of those obligations are unconditional'
    sentence. Each such sentence is preceded (within the same paragraph,
    i.e. since the previous 'Only an implementation declaring ...' opener or
    the start of the string) by the version label that sentence's paragraph
    is about."""
    openers = list(_DECLARING_VERSION_RE.finditer(version_binding))
    counts: dict[str, int] = {}
    for idx, m in enumerate(openers):
        start = m.start()
        end = openers[idx + 1].start() if idx + 1 < len(openers) else len(version_binding)
        paragraph = version_binding[start:end]
        count_m = _UNCONDITIONAL_COUNT_RE.search(paragraph)
        if count_m:
            word = count_m.group(1).lower()
            assert word in _COUNT_WORDS, f"unrecognized count word {word!r} for version {m.group(1)}"
            counts[m.group(1)] = _COUNT_WORDS[word]
    return counts


def test_obligations_version_set_matches_the_prose():
    """(v)."""
    contract = _contract()
    version_binding = contract["versioning"]["version_binding"]
    prose_versions = _prose_version_set(version_binding)
    assert prose_versions, "found 0 'Only an implementation declaring X.Y.Z ...' openers in version_binding"

    obligations_versions = {entry["version"] for entry in contract["versioning"]["obligations"]}
    assert obligations_versions, "versioning.obligations must not be empty"

    assert obligations_versions == prose_versions, (
        f"versioning.obligations version set {sorted(obligations_versions)} does not match "
        f"version_binding's own prose version set {sorted(prose_versions)}"
    )


def test_obligations_unconditional_counts_match_the_prose_for_versions_that_state_one():
    """(vi)."""
    contract = _contract()
    version_binding = contract["versioning"]["version_binding"]
    prose_counts = _prose_unconditional_counts(version_binding)

    assert prose_counts, "found 0 'N of those obligations are unconditional' sentences in version_binding"
    assert len(prose_counts) == 3, (
        f"expected exactly 3 versions with a stated unconditional count (1.4.0, 1.6.0, 1.7.0), "
        f"found {len(prose_counts)}: {sorted(prose_counts)}"
    )
    assert set(prose_counts) == {"1.4.0", "1.6.0", "1.7.0"}, sorted(prose_counts)

    obligations_by_version = {entry["version"]: entry for entry in contract["versioning"]["obligations"]}
    mismatched = []
    for version, stated_count in prose_counts.items():
        entry = obligations_by_version.get(version)
        assert entry is not None, f"versioning.obligations has no entry for {version!r}"
        actual_count = len(entry["unconditional"])
        if actual_count != stated_count:
            mismatched.append((version, stated_count, actual_count))
    assert not mismatched, (
        f"versioning.obligations unconditional-list length disagrees with version_binding's own stated "
        f"count for (version, stated, actual): {mismatched}"
    )


def _obligations_1_7_0_conditional(contract):
    obligations_by_version = {entry["version"]: entry for entry in contract["versioning"]["obligations"]}
    entry = obligations_by_version.get("1.7.0")
    assert entry is not None, "versioning.obligations has no 1.7.0 entry"
    return entry["conditional"]


def test_obligations_1_7_0_conditional_capabilities_are_defined():
    """(vii) (a): every 1.7.0 conditional obligation's `capability` value(s)
    actually name a member of `capability_status.defined`."""
    contract = _contract()
    defined = set(contract["capability_status"]["defined"])
    assert defined, "capability_status.defined must not be empty"
    conditional = _obligations_1_7_0_conditional(contract)
    assert conditional, "versioning.obligations 1.7.0 entry has 0 conditional obligations"

    undefined = []
    for element in conditional:
        for capability in element["capability"]:
            if capability not in defined:
                undefined.append((element["obligation"], capability))
    assert not undefined, (
        f"versioning.obligations 1.7.0 conditional entry names a capability not in "
        f"capability_status.defined: {undefined}"
    )


def test_obligations_1_7_0_conditional_has_exactly_5_elements():
    """(vii) (b)."""
    contract = _contract()
    conditional = _obligations_1_7_0_conditional(contract)
    assert len(conditional) == 5, (
        f"versioning.obligations 1.7.0 entry's conditional list has {len(conditional)} elements, expected 5"
    )


def test_obligations_1_7_0_conditional_conjunctions_are_the_2_fixed_pairs():
    """(vii) (c): the 2-element `capability` conjunctions among the 1.7.0
    conditional obligations are exactly the 2 pairs D-8 (2) fixes --
    `constraint_declarations` paired with `schema_operations` and with
    `application_catalog`."""
    contract = _contract()
    conditional = _obligations_1_7_0_conditional(contract)
    conjunctions = {tuple(element["capability"]) for element in conditional if len(element["capability"]) == 2}
    assert conjunctions == {
        ("constraint_declarations", "schema_operations"),
        ("constraint_declarations", "application_catalog"),
    }, f"1.7.0 conditional 2-capability conjunctions {conjunctions} do not match the 2 fixed pairs"


def test_endpoint_fields_note_present_and_non_empty():
    """(viii)."""
    contract = _contract()
    assert "endpoint_fields_note" in contract, "contract has no top-level endpoint_fields_note key"
    note = contract["endpoint_fields_note"]
    assert set(note.keys()) == {"roles", "requires_capability", "atomicity"}, (
        f"endpoint_fields_note has keys {sorted(note.keys())}, expected exactly "
        f"{{'roles', 'requires_capability', 'atomicity'}}"
    )
    for key, value in note.items():
        assert isinstance(value, str) and value.strip(), f"endpoint_fields_note.{key} is not a non-empty string"
