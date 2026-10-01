"""Self-contained JSON-Schema-subset validator for the C-11 discovery/catalog
document conformance condition (design docs/design/
CONFORMANCE_CONDITIONS_V1_1.md section 3) and for the reference client
(`reference_client.py`), which validates the request and response schemas of
the data-surface operations the derived operation catalog names.

This deliberately does not depend on a general-purpose JSON Schema library
(no new dependency for the common repository) and does not attempt to
implement JSON Schema in full. It implements exactly the keyword subset the
common contract's schemas that those two users check actually use. Those are
`CapabilityDocument`, `CatalogDocument` and `EntityDescriptor` for C-11, and
for the reference client the schemas named by the catalog's entries that are
not derived from `control_endpoints` and are not an alias of one
(`test_reference_client_schemas_use_only_implemented_or_annotation_keywords`
derives that set from the catalog). The keywords are:
`type`, `required`, `properties`, `additionalProperties`, `enum`, `const`,
`pattern`, `items`, `minItems`, `maxItems`, `minimum`, `maximum`, `maxLength`,
`maxProperties`, `if`+`then` (+`else`), and same-document `$ref` (a `#/...`
JSON pointer resolved against the full contract document, never a remote
reference). `maxLength` bounds a string's length in code points and
`maxProperties` an object's number of properties; each applies only to a value
of its own type, as the draft says. Every keyword this
file implements follows the JSON Schema draft's real semantics rather than
being special-cased to this contract's current shape -- in particular, `if`
is evaluated as an ordinary schema (its own `required`/`properties` apply
exactly as they would anywhere else), so this validator does not assume the
contract always puts `required` inside `if` the way `EntityDescriptor`
currently does; a future schema that relied on `properties`-only
vacuous-truth-on-absence inside `if` would still be evaluated correctly, not
specially exempted.

This "exactly the keyword subset" claim is enforced structurally, not just
asserted in this docstring: `validate()` rejects (raises `ValueError`) any
schema-object key it encounters that is neither an implemented keyword
(`IMPLEMENTED_KEYWORDS`) nor a harmless annotation keyword this validator
deliberately ignores (`ANNOTATION_KEYWORDS`, e.g. `title`/`description` --
metadata with no bearing on conformance). A silently-ignored keyword would
be exactly the "skip converts unverified into permitted" failure mode
(design principle 4): if the contract ever added a keyword this validator
does not implement to one of the schemas either user checks, an adapter
could satisfy the letter of that keyword while this validator kept quietly
passing every instance, having never actually looked at it.
`test_schema_check.py` has two guard tests asserting that every keyword the
real contract schemas actually use is a member of
`IMPLEMENTED_KEYWORDS | ANNOTATION_KEYWORDS` -- one for the C-11 schemas
(`test_c11_schemas_use_only_implemented_or_annotation_keywords`), one for the
schemas the reference client validates
(`test_reference_client_schemas_use_only_implemented_or_annotation_keywords`)
-- so growing the contract schemas past this validator's current coverage
fails loudly, in the suite, rather than silently under-validating.
`test_unknown_schema_keyword_fails_loud` pins the rejection of a keyword
outside both sets.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

_TYPE_CHECKS = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "boolean": lambda v: isinstance(v, bool),
    # bool is a subclass of int in Python; a JSON Schema "integer"/"number"
    # must not accept True/False.
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "null": lambda v: v is None,
}

# Schema keywords this validator actually interprets and enforces.
IMPLEMENTED_KEYWORDS = frozenset({
    "type",
    "required",
    "properties",
    "additionalProperties",
    "enum",
    "const",
    "pattern",
    "items",
    "minItems",
    "maxItems",
    "minimum",
    "maximum",
    "maxLength",
    "maxProperties",
    "if",
    "then",
    "else",
    "$ref",
})

# Keywords that carry no conformance-affecting meaning -- pure documentation/
# metadata a schema author may attach to any node. Safe to ignore silently;
# everything else is either implemented or an error (see module docstring).
ANNOTATION_KEYWORDS = frozenset({
    "$id",
    "$schema",
    "$comment",
    "title",
    "description",
    "default",
    "examples",
    "readOnly",
    "writeOnly",
    "deprecated",
})

KNOWN_SCHEMA_KEYWORDS = IMPLEMENTED_KEYWORDS | ANNOTATION_KEYWORDS


class SchemaViolation:
    """One human-readable schema-conformance failure at one JSON path."""

    __slots__ = ("path", "message")

    def __init__(self, path: str, message: str) -> None:
        self.path = path
        self.message = message

    def __str__(self) -> str:
        return f"{self.path}: {self.message}"

    def __repr__(self) -> str:
        return f"SchemaViolation({self.path!r}, {self.message!r})"


def _resolve_ref(ref: str, root: Mapping) -> dict:
    if not isinstance(ref, str) or not ref.startswith("#/"):
        raise ValueError(f"schema_check only resolves same-document JSON pointer $ref values, got {ref!r}")
    node: Any = root
    for raw_part in ref[2:].split("/"):
        # RFC 6901 pointer-escape unquoting, in the order the RFC requires
        # (~1 before ~0 would corrupt a literal "~1" segment).
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if not isinstance(node, dict) or part not in node:
            raise ValueError(f"$ref {ref!r} does not resolve in the given document (failed at {part!r})")
        node = node[part]
    if not isinstance(node, dict):
        raise ValueError(f"$ref {ref!r} does not resolve to an object schema")
    return node


def _check_known_keywords(schema: Mapping, *, path: str) -> None:
    unknown = set(schema) - KNOWN_SCHEMA_KEYWORDS
    if unknown:
        raise ValueError(
            f"schema_check: unsupported/unknown schema keyword(s) {sorted(unknown)} at {path!r} -- "
            "this validator's implemented-keyword set is deliberately closed (see module docstring); "
            "extend IMPLEMENTED_KEYWORDS (or ANNOTATION_KEYWORDS, if the keyword carries no "
            "conformance-affecting meaning) explicitly rather than silently ignoring it"
        )


def validate(instance: Any, schema: Mapping, root: Mapping, *, path: str = "$") -> list[SchemaViolation]:
    """Validate `instance` against `schema`. `root` is the full contract
    document that `$ref` pointers are resolved against (design section 3:
    same-document `$ref` only -- this never fetches a remote schema).
    Returns a list of violations; an empty list means `instance` conforms.

    Raises `ValueError` (not a `SchemaViolation`) if `schema` itself uses a
    keyword this validator does not recognize -- see module docstring.
    """
    _check_known_keywords(schema, path=path)
    violations: list[SchemaViolation] = []

    if "$ref" in schema:
        resolved = _resolve_ref(schema["$ref"], root)
        violations.extend(validate(instance, resolved, root, path=path))
        # Sibling keywords alongside `$ref` are JSON-Schema-legal in the
        # draft this validator targets; none of this contract's schemas
        # currently combine them, but falling through here (rather than
        # returning immediately) keeps that combination correctly checked
        # if one is ever added, instead of silently ignoring it.

    if "const" in schema:
        if instance != schema["const"]:
            violations.append(SchemaViolation(path, f"expected const {schema['const']!r}, got {instance!r}"))

    if "enum" in schema:
        if instance not in schema["enum"]:
            violations.append(SchemaViolation(path, f"value {instance!r} is not one of {schema['enum']!r}"))

    if "type" in schema:
        expected = schema["type"]
        expected_list = expected if isinstance(expected, list) else [expected]
        unknown_types = [t for t in expected_list if t not in _TYPE_CHECKS]
        if unknown_types:
            raise ValueError(
                f"schema_check: unknown JSON Schema type name(s) {unknown_types!r} at {path!r} "
                f"(recognized: {sorted(_TYPE_CHECKS)})"
            )
        check_fns = [_TYPE_CHECKS[t] for t in expected_list]
        if not any(fn(instance) for fn in check_fns):
            violations.append(SchemaViolation(path, f"expected type {expected!r}, got {type(instance).__name__}"))
            # A value of the wrong shape entirely: `properties`/`items`/
            # `pattern` etc. below would not be meaningful against it.
            return violations

    if "pattern" in schema and isinstance(instance, str):
        if re.search(schema["pattern"], instance) is None:
            violations.append(
                SchemaViolation(path, f"value {instance!r} does not match pattern {schema['pattern']!r}")
            )

    if "maxLength" in schema and isinstance(instance, str):
        if len(instance) > schema["maxLength"]:
            violations.append(
                SchemaViolation(path, f"string of length {len(instance)} exceeds maxLength {schema['maxLength']!r}")
            )

    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            violations.append(
                SchemaViolation(path, f"value {instance!r} is less than minimum {schema['minimum']!r}")
            )
        if "maximum" in schema and instance > schema["maximum"]:
            violations.append(
                SchemaViolation(path, f"value {instance!r} exceeds maximum {schema['maximum']!r}")
            )

    if isinstance(instance, dict):
        if "maxProperties" in schema and len(instance) > schema["maxProperties"]:
            violations.append(
                SchemaViolation(
                    path, f"object with {len(instance)} properties exceeds maxProperties {schema['maxProperties']!r}"
                )
            )
        properties = schema.get("properties", {})
        for key, subschema in properties.items():
            if key in instance:
                violations.extend(validate(instance[key], subschema, root, path=f"{path}.{key}"))
        for name in schema.get("required", ()):
            if name not in instance:
                violations.append(SchemaViolation(path, f"missing required property {name!r}"))
        additional = schema.get("additionalProperties", None)
        extra_keys = [k for k in instance if k not in properties]
        if additional is False:
            if extra_keys:
                noun = "property" if len(extra_keys) == 1 else "properties"
                violations.append(SchemaViolation(path, f"unexpected {noun}: {sorted(extra_keys)}"))
        elif isinstance(additional, dict):
            for key in extra_keys:
                violations.extend(validate(instance[key], additional, root, path=f"{path}.{key}"))

    if isinstance(instance, list):
        items_schema = schema.get("items")
        if isinstance(items_schema, dict):
            for index, item in enumerate(instance):
                violations.extend(validate(item, items_schema, root, path=f"{path}[{index}]"))
        if "minItems" in schema and len(instance) < schema["minItems"]:
            violations.append(
                SchemaViolation(path, f"expected at least {schema['minItems']} items, got {len(instance)}")
            )
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            violations.append(
                SchemaViolation(path, f"expected at most {schema['maxItems']} items, got {len(instance)}")
            )

    if "if" in schema:
        # Evaluated as an ordinary schema, not special-cased: `if` "passes"
        # exactly when validating `instance` against it produces zero
        # violations, using the very same `properties`/`required` handling
        # above -- which is what gives a missing property "vacuously true"
        # treatment under `properties` while still failing `required` if
        # the `if` schema lists it there (draft semantics; see this
        # module's docstring).
        if_schema = schema["if"]
        if not validate(instance, if_schema, root, path=path):
            then_schema = schema.get("then")
            if then_schema is not None:
                violations.extend(validate(instance, then_schema, root, path=path))
        else:
            else_schema = schema.get("else")
            if else_schema is not None:
                violations.extend(validate(instance, else_schema, root, path=path))

    return violations


def assert_valid(instance: Any, schema: Mapping, root: Mapping, *, label: str = "document") -> None:
    """Raise `AssertionError` with every violation listed if `instance` does
    not conform to `schema`. A no-op if it conforms."""
    violations = validate(instance, schema, root)
    if violations:
        details = "\n".join(f"  - {v}" for v in violations)
        raise AssertionError(f"{label} does not conform to schema:\n{details}")


def used_keywords(schema: Mapping, root: Mapping, *, _seen_refs: set | None = None) -> set[str]:
    """Recursively collect every schema-keyword key appearing anywhere in
    `schema` -- and everything it structurally contains: nested
    `properties` values, `additionalProperties` when it is itself a schema,
    `items`, `if`/`then`/`else`, and (same-document) `$ref` targets.

    Used by the keyword-coverage guard test (design section 3 review
    finding 2) to confirm every keyword the real contract schemas actually
    use is one this validator implements or deliberately treats as a
    harmless annotation -- independent of, and a stronger check than,
    `validate()`'s own fail-loud behavior (which only fires when a
    non-conforming schema is actually exercised against some instance,
    whereas this walks the schema regardless of whether every branch was
    ever instantiated in a test).
    """
    if _seen_refs is None:
        _seen_refs = set()
    keywords: set[str] = set(schema.keys())
    if "$ref" in schema:
        ref = schema["$ref"]
        if ref not in _seen_refs:
            _seen_refs.add(ref)
            resolved = _resolve_ref(ref, root)
            keywords |= used_keywords(resolved, root, _seen_refs=_seen_refs)
    for subschema in schema.get("properties", {}).values():
        if isinstance(subschema, dict):
            keywords |= used_keywords(subschema, root, _seen_refs=_seen_refs)
    additional = schema.get("additionalProperties")
    if isinstance(additional, dict):
        keywords |= used_keywords(additional, root, _seen_refs=_seen_refs)
    items = schema.get("items")
    if isinstance(items, dict):
        keywords |= used_keywords(items, root, _seen_refs=_seen_refs)
    for key in ("if", "then", "else"):
        sub = schema.get(key)
        if isinstance(sub, dict):
            keywords |= used_keywords(sub, root, _seen_refs=_seen_refs)
    return keywords
