"""Unit tests for `schema_check.py` itself (design docs/design/
CONFORMANCE_CONDITIONS_V1_1.md section 3: "検証器自身の単体テストを書く").

These are suite self-tests, not condition tests: they carry no
`@pytest.mark.condition(...)` marker, and `test_conditions_register.py`
does not expect one here.

The R1-type four cases below exercise `EntityDescriptor`'s real `if`/`then`
clause straight from `spec/data-service-api.v1.json` (the same defect shape
a missing-validator let through before this file existed): no
`mutation_class` declared, `mutation_class: append_only`, a complete
`mutation_class: mutable` declaration, and an incomplete one.
"""
from __future__ import annotations

import json

import pytest

from adapter import REPO_ROOT, load_contract
from schema_check import ANNOTATION_KEYWORDS, IMPLEMENTED_KEYWORDS, assert_valid, used_keywords, validate


def _contract():
    return load_contract()


def _entity_descriptor():
    contract = _contract()
    return contract["definitions"]["EntityDescriptor"], contract


# --- R1 four cases, against the real EntityDescriptor schema ---------------


def test_r1_no_mutation_class_declared_is_valid():
    schema, contract = _entity_descriptor()
    instance = {"entity": "notes", "fields": ["id", "body"]}
    assert validate(instance, schema, contract) == []


def test_r1_append_only_without_address_fields_is_valid():
    schema, contract = _entity_descriptor()
    instance = {"entity": "notes", "fields": ["id", "body"], "mutation_class": "append_only"}
    assert validate(instance, schema, contract) == []


def test_r1_mutable_with_full_addressability_declaration_is_valid():
    schema, contract = _entity_descriptor()
    instance = {
        "entity": "notes",
        "fields": ["id", "body"],
        "mutation_class": "mutable",
        "address_fields": ["id"],
        "address_reuse": "never",
    }
    assert validate(instance, schema, contract) == []


def test_r1_mutable_without_address_fields_is_invalid():
    # This is exactly the defect shape (R1) the contract review flagged:
    # `mutation_class: mutable` advertised without the addressability
    # declaration the `if`/`then` clause requires alongside it.
    schema, contract = _entity_descriptor()
    instance = {"entity": "notes", "fields": ["id", "body"], "mutation_class": "mutable"}
    violations = validate(instance, schema, contract)
    assert violations, "an incomplete mutable declaration must be rejected"
    joined = "\n".join(str(v) for v in violations)
    assert "address_fields" in joined or "address_reuse" in joined


# --- keyword-level checks, independent of the real contract -----------------


def test_type_mismatch_is_reported_and_short_circuits_structural_checks():
    schema = {"type": "object", "required": ["x"]}
    violations = validate("not an object", schema, {})
    assert len(violations) == 1
    assert "type" in violations[0].message


def test_required_missing_property_is_reported():
    schema = {"type": "object", "required": ["a", "b"]}
    violations = validate({"a": 1}, schema, {})
    assert any("b" in v.message for v in violations)


def test_additional_properties_false_rejects_unknown_keys():
    schema = {"type": "object", "properties": {"a": {"type": "string"}}, "additionalProperties": False}
    assert validate({"a": "x"}, schema, {}) == []
    violations = validate({"a": "x", "z": 1}, schema, {})
    assert any("z" in v.message for v in violations)


def test_additional_properties_schema_validates_extra_values():
    schema = {"type": "object", "additionalProperties": {"type": "integer", "minimum": 0}}
    assert validate({"a": 1}, schema, {}) == []
    violations = validate({"a": "not an int"}, schema, {})
    assert violations
    # "minimum" is implemented (see test_minimum_and_maximum below), so a
    # negative value under this same additionalProperties schema is also
    # rejected -- not just a type mismatch.
    assert validate({"a": -1}, schema, {})


def test_enum_and_const():
    assert validate("enabled", {"enum": ["enabled", "partial"]}, {}) == []
    assert validate("bogus", {"enum": ["enabled", "partial"]}, {})
    assert validate("fixed", {"const": "fixed"}, {}) == []
    assert validate("other", {"const": "fixed"}, {})


def test_pattern():
    schema = {"type": "string", "pattern": "^[a-z_][a-z0-9_]*$"}
    assert validate("valid_name", schema, {}) == []
    assert validate("Not Valid", schema, {})


def test_minimum_and_maximum():
    schema = {"type": "integer", "minimum": 1, "maximum": 10}
    assert validate(5, schema, {}) == []
    assert validate(1, schema, {}) == []
    assert validate(10, schema, {}) == []
    assert validate(0, schema, {})
    assert validate(11, schema, {})


def test_max_length_accepts_a_string_at_the_bound_and_rejects_one_past_it():
    schema = {"type": "string", "maxLength": 3}
    assert validate("abc", schema, {}) == []
    assert validate("", schema, {}) == []
    violations = validate("abcd", schema, {})
    assert violations and "maxLength" in violations[0].message
    # The bound counts code points, as JSON Schema does, and says nothing of a
    # value that is not a string.
    assert validate("\u00e9\U0001F600\u00e9", schema, {}) == []
    assert validate(12345, {"maxLength": 3}, {}) == []

    contract = _contract()
    request = contract["schemas"]["MutationRequest"]
    base = {"operations": [{"operation": "insert", "values": {"a": 1}}]}
    assert validate({**base, "idempotency_key": "k" * 128}, request, contract) == []
    over = validate({**base, "idempotency_key": "k" * 129}, request, contract)
    assert over and "maxLength" in over[0].message and over[0].path == "$.idempotency_key"


def test_max_properties_accepts_an_object_at_the_bound_and_rejects_one_past_it():
    schema = {"type": "object", "maxProperties": 2}
    assert validate({}, schema, {}) == []
    assert validate({"a": 1, "b": 2}, schema, {}) == []
    violations = validate({"a": 1, "b": 2, "c": 3}, schema, {})
    assert violations and "maxProperties" in violations[0].message
    assert validate([1, 2, 3], {"maxProperties": 2}, {}) == []

    contract = _contract()
    request = contract["schemas"]["MutationRequest"]

    def with_values(count):
        return {"operations": [{"operation": "insert", "values": {f"f{i}": i for i in range(count)}}]}

    assert validate(with_values(100), request, contract) == []
    over = validate(with_values(101), request, contract)
    assert over and "maxProperties" in over[0].message and over[0].path == "$.operations[0].values"


def test_unknown_schema_keyword_fails_loud():
    schema = {"type": "string", "totallyMadeUpKeyword": True}
    with pytest.raises(ValueError):
        validate("x", schema, {})


def test_unknown_type_name_fails_loud():
    schema = {"type": "frobnicate"}
    with pytest.raises(ValueError):
        validate("x", schema, {})


def test_annotation_keywords_are_ignored_not_flagged():
    schema = {
        "type": "string",
        "title": "Name",
        "description": "A human-readable label.",
        "$comment": "internal note",
        "examples": ["a", "b"],
    }
    assert validate("x", schema, {}) == []


def test_items_min_max_items():
    schema = {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 2}
    assert validate(["a"], schema, {}) == []
    assert validate([], schema, {})
    assert validate(["a", "b", "c"], schema, {})
    assert validate([1], schema, {})  # item type mismatch


def test_ref_resolves_within_same_document():
    root = {
        "definitions": {"Thing": {"type": "object", "required": ["name"]}},
        "schemas": {"Holder": {"type": "object", "properties": {"thing": {"$ref": "#/definitions/Thing"}}}},
    }
    schema = root["schemas"]["Holder"]
    assert validate({"thing": {"name": "x"}}, schema, root) == []
    violations = validate({"thing": {}}, schema, root)
    assert any("name" in v.message for v in violations)


def test_assert_valid_raises_with_details_and_is_silent_when_valid():
    schema = {"type": "object", "required": ["a"]}
    assert_valid({"a": 1}, schema, {}, label="ok")
    try:
        assert_valid({}, schema, {}, label="broken")
    except AssertionError as exc:
        assert "broken" in str(exc)
        assert "a" in str(exc)
    else:
        raise AssertionError("assert_valid should have raised")


# --- against the real contract's other C-11-relevant schemas ---------------


def test_capability_document_schema_from_real_contract():
    contract = _contract()
    schema = contract["schemas"]["CapabilityDocument"]
    valid_document = {
        "contract_version": "1.1.0",
        "capabilities": {"structured_query": {"status": "enabled"}},
        "limits": {"batch_items": 100},
        "limit_enforcement": {"batch_items": "enforced"},
        "authorization_propagation_bound_ms": 0,
    }
    assert validate(valid_document, schema, contract) == []

    missing_required = dict(valid_document)
    del missing_required["authorization_propagation_bound_ms"]
    assert validate(missing_required, schema, contract)

    unknown_top_level_field = dict(valid_document, made_up_field="x")
    assert validate(unknown_top_level_field, schema, contract)


def test_capability_document_schema_rejects_a_zero_limit_value():
    # design section 3 review finding 2: CapabilityDocument.limits'
    # additionalProperties schema declares "minimum": 1; a peer publishing
    # a zero-valued limit is a real conformance defect (a limit of 0 is not
    # a finite, meaningful bound) that C-11 must catch via this validator,
    # not silently accept because "minimum" went unimplemented.
    contract = _contract()
    schema = contract["schemas"]["CapabilityDocument"]
    document = {
        "contract_version": "1.1.0",
        "capabilities": {"structured_query": {"status": "enabled"}},
        "limits": {"batch_items": 0},
        "limit_enforcement": {"batch_items": "enforced"},
        "authorization_propagation_bound_ms": 0,
    }
    violations = validate(document, schema, contract)
    assert violations, "a limits value of 0 must be rejected (CapabilityDocument.limits.additionalProperties.minimum: 1)"
    assert any("minimum" in v.message for v in violations)


# --- keyword-coverage guard (design section 3 review finding 2) -----------


def test_c11_schemas_use_only_implemented_or_annotation_keywords():
    """Every schema keyword actually used anywhere inside the three
    schemas C-11 validates against (`CapabilityDocument`, `CatalogDocument`
    -- which transitively pulls in `EntityDescriptor` via `$ref`) must be a
    member of `IMPLEMENTED_KEYWORDS | ANNOTATION_KEYWORDS`. This is a
    schema-shape check independent of any single instance: it walks the
    schema trees directly, so it catches a keyword the contract added that
    no test happened to exercise, not just one that showed up in an
    instance under test.
    """
    contract = _contract()
    used: set[str] = set()
    for name in ("CapabilityDocument", "CatalogDocument"):
        used |= used_keywords(contract["schemas"][name], contract)
    known = IMPLEMENTED_KEYWORDS | ANNOTATION_KEYWORDS
    unknown = used - known
    assert not unknown, (
        f"contract schema(s) use keyword(s) schema_check.py does not recognize: {sorted(unknown)} -- "
        "extend IMPLEMENTED_KEYWORDS (or ANNOTATION_KEYWORDS) in schema_check.py"
    )


def test_reference_client_schemas_use_only_implemented_or_annotation_keywords():
    """The same guard for the request and response schemas that the
    operations of the data surface name in the derived operation catalog -- the
    ones a client validates against. An entry derived from `control_endpoints`
    (its name carries the `control.` prefix) or an alias of one (its name is
    also a key of `control_endpoints`) names schemas the client never uses.
    """
    contract = _contract()
    catalog = json.loads((REPO_ROOT / "spec" / "OPERATION_CATALOG.json").read_text())
    names: set[str] = set()
    for entry in catalog["operations"]:
        if entry["name"].startswith("control.") or entry["name"] in contract["control_endpoints"]:
            continue
        names |= {entry[key] for key in ("request_schema", "response_schema") if entry[key] is not None}
    assert names, "no data-surface schema was found to check"
    used: set[str] = set()
    for name in sorted(names):
        used |= used_keywords(contract["schemas"][name], contract)
    unknown = used - (IMPLEMENTED_KEYWORDS | ANNOTATION_KEYWORDS)
    assert not unknown, (
        f"schema(s) the reference client validates use keyword(s) schema_check.py does not recognize: {sorted(unknown)} -- "
        "extend IMPLEMENTED_KEYWORDS (or ANNOTATION_KEYWORDS) in schema_check.py"
    )


def test_catalog_document_schema_from_real_contract():
    contract = _contract()
    schema = contract["schemas"]["CatalogDocument"]
    valid_document = {
        "application_scope": "app_a",
        "entities": [{"entity": "notes", "fields": ["id", "body"]}],
    }
    assert validate(valid_document, schema, contract) == []

    invalid_entity_descriptor = {
        "application_scope": "app_a",
        "entities": [{"entity": "notes", "fields": ["id"], "mutation_class": "mutable"}],
    }
    violations = validate(invalid_entity_descriptor, schema, contract)
    assert violations, "an entity with an incomplete mutable declaration must be rejected via $ref"


# --- Phase 6 WP-1 review fix F2 (test): CapabilityDocument.surfaces STRUCTURE,
# and EntityDescriptor/SchemaOperationRequest.field_types VOCABULARY, against
# the real contract's own schemas. Review mutation alpha (dropping the nested
# `required: ["base_url"]` from surfaces.data / surfaces.control in spec plus
# both packaged copies simultaneously) went undetected by this file, by
# test_contract.py, and by test_c11_document_conformance.py alike (52 passed)
# before this fix -- these tests close that gap at the schema_check.py /
# real-contract level, independent of any adapter ever emitting a `surfaces`
# key (peers have not flipped to 1.6.0 yet). ---------------------------------


def test_capability_document_schema_accepts_a_valid_surfaces_document():
    contract = _contract()
    schema = contract["schemas"]["CapabilityDocument"]
    document = {
        "contract_version": "1.6.0",
        "capabilities": {"structured_query": {"status": "enabled"}},
        "limits": {"batch_items": 100},
        "limit_enforcement": {"batch_items": "enforced"},
        "authorization_propagation_bound_ms": 0,
        "surfaces": {
            "data": {"base_url": "https://data.conformance.invalid/v1"},
            "control": {"base_url": "https://control.conformance.invalid/control/v1"},
        },
    }
    assert validate(document, schema, contract) == []

    # A control_plane: unavailable deployment omits ONLY surfaces.control
    # (confirmed prose (2)); surfaces.data alone remains valid.
    data_only_document = dict(document, surfaces={"data": {"base_url": "https://data.conformance.invalid/v1"}})
    assert validate(data_only_document, schema, contract) == []


def test_capability_document_schema_rejects_surfaces_missing_data():
    # Supervisor ruling F2: surfaces.required == ["data"] -- surfaces.data.
    # base_url is version_binding's own UNCONDITIONAL 1.6.0 obligation
    # wherever `surfaces` itself is present at all.
    contract = _contract()
    schema = contract["schemas"]["CapabilityDocument"]
    document = {
        "contract_version": "1.6.0",
        "capabilities": {"structured_query": {"status": "enabled"}},
        "limits": {"batch_items": 100},
        "limit_enforcement": {"batch_items": "enforced"},
        "authorization_propagation_bound_ms": 0,
        "surfaces": {},
    }
    violations = validate(document, schema, contract)
    assert violations, "an empty surfaces object (missing the required 'data' key) must be rejected"


def test_capability_document_schema_rejects_surfaces_data_missing_base_url():
    contract = _contract()
    schema = contract["schemas"]["CapabilityDocument"]
    document = {
        "contract_version": "1.6.0",
        "capabilities": {"structured_query": {"status": "enabled"}},
        "limits": {"batch_items": 100},
        "limit_enforcement": {"batch_items": "enforced"},
        "authorization_propagation_bound_ms": 0,
        "surfaces": {"data": {}},
    }
    violations = validate(document, schema, contract)
    assert violations, "surfaces.data without base_url (its own required property) must be rejected"


def test_capability_document_schema_rejects_surfaces_control_base_url_non_string():
    contract = _contract()
    schema = contract["schemas"]["CapabilityDocument"]
    document = {
        "contract_version": "1.6.0",
        "capabilities": {"structured_query": {"status": "enabled"}},
        "limits": {"batch_items": 100},
        "limit_enforcement": {"batch_items": "enforced"},
        "authorization_propagation_bound_ms": 0,
        "surfaces": {
            "data": {"base_url": "https://data.conformance.invalid/v1"},
            "control": {"base_url": 12345},
        },
    }
    violations = validate(document, schema, contract)
    assert violations, "surfaces.control.base_url must be rejected when it is not a string"


def test_entity_descriptor_field_types_rejects_a_value_outside_the_seven_word_vocabulary():
    schema, contract = _entity_descriptor()
    valid_instance = {
        "entity": "notes",
        "fields": ["id", "body"],
        "field_types": {"id": "integer", "body": "json"},
    }
    assert validate(valid_instance, schema, contract) == []

    invalid_instance = {
        "entity": "notes",
        "fields": ["id", "body"],
        "field_types": {"id": "integer", "body": "unknown"},
    }
    violations = validate(invalid_instance, schema, contract)
    assert violations, "EntityDescriptor.field_types must reject a value outside the 7-word type vocabulary"


def test_schema_operation_request_field_types_rejects_a_value_outside_the_seven_word_vocabulary():
    contract = _contract()
    schema = contract["schemas"]["SchemaOperationRequest"]
    valid_instance = {
        "operation": "create_entity",
        "entity": "notes",
        "fields": ["id", "body"],
        "field_types": {"body": "json"},
    }
    assert validate(valid_instance, schema, contract) == []

    invalid_instance = {
        "operation": "create_entity",
        "entity": "notes",
        "fields": ["id", "body"],
        "field_types": {"body": "unknown"},
    }
    violations = validate(invalid_instance, schema, contract)
    assert violations, "SchemaOperationRequest.field_types must reject a value outside the 7-word type vocabulary"
