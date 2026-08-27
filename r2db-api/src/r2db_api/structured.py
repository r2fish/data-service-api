"""A small structured-operation reference engine (no database-native command path)."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
import re
from typing import Any, Callable

from .errors import fail
from .limits import ResourceLimits

IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
# PostgreSQL's own identifier limit, and the bound MitateDB-api already
# enforces (`^[a-z][a-z0-9_]{0,62}$`). This is a structural syntax policy on
# identifiers, not a deployment-tunable resource class from the contract's
# `limits.classes`, so it lives here as a constant rather than in
# ResourceLimits; the contract permits a stricter per-implementation
# identifier policy.
MAX_IDENTIFIER_LENGTH = 63
OPERATORS = {"eq", "ne", "lt", "lte", "gt", "gte", "in", "contains", "is_null"}


def validate_identifier(value: str) -> str:
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value) or len(value) > MAX_IDENTIFIER_LENGTH:
        fail("IDENTIFIER_INVALID", "Identifier has an unsupported format.", details={"field": "identifier"})
    return value


def _mapping(value: Any, message: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        fail("VALIDATION_FAILED", message)
    return value


def parse_predicate(value: Any) -> "Predicate":
    item = _mapping(value, "Filter must be an object.")
    if not {"field", "operator"}.issubset(item) or set(item) - {"field", "operator", "value"}:
        fail("VALIDATION_FAILED", "Filter shape is not supported.")
    return Predicate(field=item["field"], operator=item["operator"], value=item.get("value"))


@dataclass(frozen=True)
class Predicate:
    field: str
    operator: str
    value: Any = None

    def validate(self) -> None:
        validate_identifier(self.field)
        if self.operator not in OPERATORS:
            fail("VALIDATION_FAILED", "Unsupported filter operator.", details={"field": self.field})


# --- Shared validation/planning boundary (design D-1) -----------------------
#
# Everything below this point is the boundary every `StorageBackend` MUST
# cross before touching stored data: identifier syntax, the operator/
# operation allowlists, mutation/schema shape checks, and destructive
# confirmation. `ApplicationCell` (below) and `PostgresCell`
# (`r2db_api.postgres`) both call these same functions -- neither backend
# reimplements this logic privately. A backend still performs its own
# catalog-existence checks (NOT_FOUND/CONFLICT against its real stored
# entities/fields) and its own execution, because those are inherently
# backend-specific; but "is this identifier/operator/shape/confirmation
# valid at all" is decided exactly once, here, for every backend.


def validate_projection(select: Any, known_fields: set[str]) -> list[str]:
    """Bounded, non-empty, identifier-checked, catalog-checked field list."""
    if not isinstance(select, list) or not select or len(select) > 100:
        fail("VALIDATION_FAILED", "A bounded non-empty projection is required.")
    for field_name in select:
        validate_identifier(field_name)
    if any(field_name not in known_fields for field_name in select):
        fail("NOT_FOUND", "Field was not found.", status=404)
    return select


def validate_predicates(where: list["Predicate"], known_fields: set[str]) -> list["Predicate"]:
    """Operator-allowlist- and catalog-checked predicates (already parsed)."""
    for predicate in where:
        predicate.validate()
        if predicate.field not in known_fields:
            fail("NOT_FOUND", "Field was not found.", status=404)
    return where


MUTATION_OPERATIONS = {"insert", "update", "upsert", "delete"}
_MUTATION_KEYS = {"operation", "values", "where", "destructive", "confirmation", "expected_revision"}


@dataclass(frozen=True)
class BoundMutation:
    """A single mutation item that has crossed the shared validation
    boundary: shape, operator allowlist, identifiers, and value bounds are
    settled. `destructive`/`confirmation` are carried through unevaluated --
    see `require_destructive_confirmation` for why that check is deliberately
    left to each backend's own call site rather than folded in here.
    """

    operation: str
    where: list["Predicate"]
    values: dict[str, Any]
    destructive: bool
    confirmation: Any = None


def bind_mutation(operation: Any, known_fields: set[str]) -> BoundMutation:
    if not isinstance(operation, dict) or set(operation) - _MUTATION_KEYS:
        fail("VALIDATION_FAILED", "Mutation shape is not supported.")
    name = operation.get("operation")
    if name not in MUTATION_OPERATIONS:
        fail("CAPABILITY_UNSUPPORTED", "Mutation operation is not supported.")
    raw_where = operation.get("where", [])
    if not isinstance(raw_where, list):
        fail("VALIDATION_FAILED", "Mutation filter must be a list.")
    where = validate_predicates([parse_predicate(item) for item in raw_where], known_fields)
    raw_values = operation.get("values", {})
    if not isinstance(raw_values, dict):
        fail("VALIDATION_FAILED", "Mutation values must be an object.")
    if len(raw_values) > 100:
        fail("LIMIT_EXCEEDED", "Mutation contains too many fields.", status=413)
    for key in raw_values:
        validate_identifier(key)
        if key not in known_fields:
            fail("NOT_FOUND", "Field was not found.", status=404)
    if "destructive" in operation and not isinstance(operation["destructive"], bool):
        fail("VALIDATION_FAILED", "Destructive flag must be boolean.")
    if "expected_revision" in operation or "idempotency_key" in operation:
        fail("CAPABILITY_UNSUPPORTED", "Revision and idempotency semantics are not enabled by this foundation.")
    if name in {"update", "delete", "upsert"} and not where:
        fail("VALIDATION_FAILED", "This operation requires a non-empty filter.")
    return BoundMutation(name, where, dict(raw_values), bool(operation.get("destructive")), operation.get("confirmation"))


def require_destructive_confirmation(destructive: bool, confirmation: Any, expected: str, message: str) -> None:
    """Shared SI-09 gate for every destructive operation (`delete`,
    `drop_entity`). Deliberately NOT called from inside `bind_mutation`/
    `bind_schema_operation`: each backend calls it at the point in its own
    execution where it is about to destroy rows/objects, which for
    `ApplicationCell` is after existence/match computation (matching this
    foundation's pre-existing, tested error precedence) and may differ for
    another backend's own execution order. The confirmation *logic* --
    "must be explicitly `destructive: true` with the exact expected token"
    -- is the one thing every backend shares.
    """
    if not destructive or confirmation != expected:
        fail("DESTRUCTIVE_CONFIRMATION_REQUIRED", message, status=409)


SCHEMA_OPERATIONS = {"create_entity", "add_field", "drop_entity"}
_SCHEMA_KEYS = {"operation", "entity", "field", "fields", "destructive", "confirmation", "revision"}


@dataclass(frozen=True)
class BoundSchemaOperation:
    operation: str
    entity: str
    field: str | None
    fields: tuple[str, ...]
    destructive: bool
    confirmation: Any = None


def bind_schema_operation(operation: Any, *, developer: bool) -> BoundSchemaOperation:
    if not developer:
        fail("FORBIDDEN", "Developer authority is required for schema operations.", status=403)
    if not isinstance(operation, dict):
        fail("VALIDATION_FAILED", "Schema operation must be an object.")
    if set(operation) - _SCHEMA_KEYS:
        fail("VALIDATION_FAILED", "Schema operation shape is not supported.")
    name = operation.get("operation")
    entity = validate_identifier(operation.get("entity", ""))
    fields: tuple[str, ...] = ()
    field_name = None
    if name == "create_entity":
        raw_fields = operation.get("fields", [])
        if not isinstance(raw_fields, list) or len(raw_fields) > 100:
            fail("VALIDATION_FAILED", "Schema fields must be a bounded list.")
        validated: list[str] = []
        for candidate in raw_fields:
            validate_identifier(candidate)
            if candidate in validated:
                fail("CONFLICT", "Field already exists.", status=409)
            validated.append(candidate)
        fields = tuple(validated)
    elif name == "add_field":
        field_name = validate_identifier(operation.get("field", ""))
    elif name != "drop_entity":
        fail("CAPABILITY_UNSUPPORTED", "Schema operation is not supported by this foundation.")
    return BoundSchemaOperation(name, entity, field_name, fields, bool(operation.get("destructive")), operation.get("confirmation"))


@dataclass
class ApplicationCell:
    application_id: str
    entities: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    schema: dict[str, set[str]] = field(default_factory=dict)
    schema_revision: int = 0

    def __post_init__(self) -> None:
        for entity, rows in list(self.entities.items()):
            validate_identifier(entity)
            if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
                fail("VALIDATION_FAILED", "Entity rows must be a list of objects.")
            fields = set().union(*(row.keys() for row in rows)) if rows else set()
            for name in fields:
                validate_identifier(name)
            declared = self.schema.setdefault(entity, set())
            declared.update(fields)

    def query(self, entity: str, *, select: list[str], where: list[Predicate], page_size: int, limits: ResourceLimits, deadline: float | None = None, clock: Callable[[], float] | None = None) -> list[dict[str, Any]]:
        if deadline is not None and clock is not None:
            limits.check_deadline(deadline, clock)
        validate_identifier(entity)
        if page_size <= 0:
            fail("LIMIT_EXCEEDED", "Page size must be positive.", status=413, details={"resource": "result_items", "limit": limits.result_items})
        if entity not in self.entities:
            fail("NOT_FOUND", "Entity was not found.", status=404)
        known_fields = self.schema.get(entity, set())
        validate_projection(select, known_fields)
        validate_predicates(where, known_fields)
        limits.check("query_complexity", len(where) + len(select))
        try:
            rows = [row for row in self.entities[entity] if all(_matches(row, p) for p in where)]
        except (TypeError, ValueError):
            fail("VALIDATION_FAILED", "Filter value is incompatible with the selected operator.")
        limits.check("result_items", min(len(rows), page_size))
        if deadline is not None and clock is not None:
            limits.check_deadline(deadline, clock)
        return [{field_name: row.get(field_name) for field_name in select} for row in rows[:page_size]]

    def catalog(self) -> list[dict[str, Any]]:
        return [{"entity": name, "fields": sorted(self.schema.get(name, set()))} for name in sorted(self.entities)]

    def transact(self, entity: str, operations: list[dict[str, Any]], limits: ResourceLimits, *, deadline: float | None = None, clock: Callable[[], float] | None = None) -> int:
        if deadline is not None and clock is not None:
            limits.check_deadline(deadline, clock)
        validate_identifier(entity)
        if not operations:
            fail("VALIDATION_FAILED", "At least one mutation is required.")
        limits.check("batch_items", len(operations))
        if entity not in self.entities:
            fail("NOT_FOUND", "Entity was not found.", status=404)
        before = deepcopy(self.entities[entity])
        try:
            affected = 0
            for operation in operations:
                affected += self._apply(entity, operation)
                limits.check("result_items", affected)
            if deadline is not None and clock is not None:
                limits.check_deadline(deadline, clock)
            return affected
        except Exception:
            self.entities[entity] = before
            raise

    def _apply(self, entity: str, operation: dict[str, Any]) -> int:
        known_fields = self.schema.get(entity, set())
        bound = bind_mutation(operation, known_fields)
        if bound.operation == "insert":
            self.entities[entity].append(dict(bound.values))
            return 1
        try:
            matches = [row for row in self.entities[entity] if all(_matches(row, p) for p in bound.where)]
        except (TypeError, ValueError):
            fail("VALIDATION_FAILED", "Filter value is incompatible with the selected operator.")
        if bound.operation == "delete":
            require_destructive_confirmation(bound.destructive, bound.confirmation, "DELETE", "Delete requires explicit destructive confirmation.")
            self.entities[entity] = [row for row in self.entities[entity] if row not in matches]
            return len(matches)
        for row in matches:
            row.update(bound.values)
        if bound.operation == "upsert" and not matches:
            self.entities[entity].append(dict(bound.values))
            return 1
        return len(matches)

    def apply_schema(self, operation: dict[str, Any], *, developer: bool, limits: ResourceLimits, deadline: float | None = None, clock: Callable[[], float] | None = None) -> int:
        bound = bind_schema_operation(operation, developer=developer)
        current_objects = sum(len(fields) + 1 for fields in self.schema.values())
        if bound.operation == "create_entity":
            projected_objects = current_objects + 1 + len(bound.fields)
        elif bound.operation == "add_field":
            projected_objects = current_objects + 1
        else:  # drop_entity
            projected_objects = current_objects - (len(self.schema.get(bound.entity, set())) + 1)
        limits.check("schema_objects", projected_objects)
        if deadline is not None and clock is not None:
            limits.check_deadline(deadline, clock)
        before_entities = deepcopy(self.entities)
        before_schema = deepcopy(self.schema)
        before_revision = self.schema_revision
        if bound.operation == "create_entity":
            if bound.entity in self.entities:
                fail("CONFLICT", "Entity already exists.", status=409)
            self.entities[bound.entity] = []
            self.schema[bound.entity] = set(bound.fields)
        elif bound.operation == "drop_entity":
            if bound.entity not in self.entities:
                fail("NOT_FOUND", "Entity was not found.", status=404)
            require_destructive_confirmation(bound.destructive, bound.confirmation, "DROP_ENTITY", "Drop requires explicit destructive confirmation.")
            self.entities.pop(bound.entity, None)
            self.schema.pop(bound.entity, None)
        else:  # add_field
            if bound.entity not in self.entities:
                fail("NOT_FOUND", "Entity was not found.", status=404)
            if bound.field in self.schema.setdefault(bound.entity, set()):
                fail("CONFLICT", "Field already exists.", status=409)
            self.schema[bound.entity].add(bound.field)
        if deadline is not None and clock is not None:
            try:
                limits.check_deadline(deadline, clock)
            except Exception:
                self.entities = before_entities
                self.schema = before_schema
                self.schema_revision = before_revision
                raise
        self.schema_revision += 1
        return self.schema_revision


def _matches(row: dict[str, Any], predicate: Predicate) -> bool:
    actual = row.get(predicate.field)
    expected = predicate.value
    if predicate.operator == "eq":
        return actual == expected
    if predicate.operator == "ne":
        return actual != expected
    if predicate.operator == "lt":
        return actual < expected
    if predicate.operator == "lte":
        return actual <= expected
    if predicate.operator == "gt":
        return actual > expected
    if predicate.operator == "gte":
        return actual >= expected
    if predicate.operator == "in":
        return actual in expected
    if predicate.operator == "contains":
        return expected in actual
    return actual is None  # is_null
