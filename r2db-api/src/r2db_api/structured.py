"""A small structured-operation reference engine (no database-native command path)."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
import re
from typing import Any, Callable

from .errors import fail
from .limits import ResourceLimits

IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
OPERATORS = {"eq", "ne", "lt", "lte", "gt", "gte", "in", "contains", "is_null"}


def validate_identifier(value: str) -> str:
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
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
        if not isinstance(select, list) or not select or len(select) > 100:
            fail("VALIDATION_FAILED", "A bounded non-empty projection is required.")
        for field_name in select:
            validate_identifier(field_name)
        known_fields = self.schema.get(entity, set())
        if any(field_name not in known_fields for field_name in select):
            fail("NOT_FOUND", "Field was not found.", status=404)
        for predicate in where:
            predicate.validate()
            if predicate.field not in known_fields:
                fail("NOT_FOUND", "Field was not found.", status=404)
        limits.check("query_complexity", len(where) + len(select))
        try:
            rows = [row for row in self.entities[entity] if all(_matches(row, p) for p in where)]
        except (TypeError, ValueError):
            fail("VALIDATION_FAILED", "Filter value is incompatible with the selected operator.")
        limits.check("result_items", min(len(rows), page_size))
        if deadline is not None and clock is not None:
            limits.check_deadline(deadline, clock)
        return [{field_name: row.get(field_name) for field_name in select} for row in rows[:page_size]]

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
        if not isinstance(operation, dict) or set(operation) - {"operation", "values", "where", "destructive", "confirmation", "expected_revision"}:
            fail("VALIDATION_FAILED", "Mutation shape is not supported.")
        name = operation.get("operation")
        if name not in {"insert", "update", "upsert", "delete"}:
            fail("CAPABILITY_UNSUPPORTED", "Mutation operation is not supported.")
        raw_where = operation.get("where", [])
        if not isinstance(raw_where, list):
            fail("VALIDATION_FAILED", "Mutation filter must be a list.")
        where = [parse_predicate(p) for p in raw_where]
        for p in where:
            p.validate()
            if p.field not in self.schema.get(entity, set()):
                fail("NOT_FOUND", "Field was not found.", status=404)
        values = operation.get("values", {})
        if not isinstance(values, dict):
            fail("VALIDATION_FAILED", "Mutation values must be an object.")
        if len(values) > 100:
            fail("LIMIT_EXCEEDED", "Mutation contains too many fields.", status=413)
        for key in values:
            validate_identifier(key)
            if key not in self.schema.get(entity, set()):
                fail("NOT_FOUND", "Field was not found.", status=404)
        if "destructive" in operation and not isinstance(operation["destructive"], bool):
            fail("VALIDATION_FAILED", "Destructive flag must be boolean.")
        if "expected_revision" in operation or "idempotency_key" in operation:
            fail("CAPABILITY_UNSUPPORTED", "Revision and idempotency semantics are not enabled by this foundation.")
        if name == "insert":
            self.entities[entity].append(dict(values))
            return 1
        try:
            matches = [row for row in self.entities[entity] if all(_matches(row, p) for p in where)]
        except (TypeError, ValueError):
            fail("VALIDATION_FAILED", "Filter value is incompatible with the selected operator.")
        if name in {"update", "delete", "upsert"} and not where:
            fail("VALIDATION_FAILED", "This operation requires a non-empty filter.")
        if name == "delete":
            if not operation.get("destructive") or operation.get("confirmation") != "DELETE":
                fail("DESTRUCTIVE_CONFIRMATION_REQUIRED", "Delete requires explicit destructive confirmation.", status=409)
            self.entities[entity] = [row for row in self.entities[entity] if row not in matches]
            return len(matches)
        for row in matches:
            row.update(values)
        if name == "upsert" and not matches:
            self.entities[entity].append(dict(values))
            return 1
        return len(matches)

    def apply_schema(self, operation: dict[str, Any], *, developer: bool, limits: ResourceLimits, deadline: float | None = None, clock: Callable[[], float] | None = None) -> int:
        if not developer:
            fail("FORBIDDEN", "Developer authority is required for schema operations.", status=403)
        if not isinstance(operation, dict):
            fail("VALIDATION_FAILED", "Schema operation must be an object.")
        if set(operation) - {"operation", "entity", "field", "fields", "destructive", "confirmation", "revision"}:
            fail("VALIDATION_FAILED", "Schema operation shape is not supported.")
        name = operation.get("operation")
        entity = validate_identifier(operation.get("entity", ""))
        current_objects = sum(len(fields) + 1 for fields in self.schema.values())
        if name == "create_entity":
            raw_fields = operation.get("fields", [])
            if not isinstance(raw_fields, list) or len(raw_fields) > 100:
                fail("VALIDATION_FAILED", "Schema fields must be a bounded list.")
            projected_objects = current_objects + 1 + len(raw_fields)
        elif name == "add_field":
            projected_objects = current_objects + 1
        elif name == "drop_entity":
            projected_objects = current_objects - (len(self.schema.get(entity, set())) + 1)
        else:
            projected_objects = current_objects
        limits.check("schema_objects", projected_objects)
        if deadline is not None and clock is not None:
            limits.check_deadline(deadline, clock)
        before_entities = deepcopy(self.entities)
        before_schema = deepcopy(self.schema)
        before_revision = self.schema_revision
        if name == "create_entity":
            if entity in self.entities:
                fail("CONFLICT", "Entity already exists.", status=409)
            validated_fields: list[str] = []
            for field_name in raw_fields:
                validate_identifier(field_name)
                if field_name in validated_fields:
                    fail("CONFLICT", "Field already exists.", status=409)
                validated_fields.append(field_name)
            self.entities[entity] = []
            self.schema[entity] = set()
            for field_name in validated_fields:
                self.schema[entity].add(field_name)
        elif name == "drop_entity":
            if entity not in self.entities:
                fail("NOT_FOUND", "Entity was not found.", status=404)
            if not operation.get("destructive") or operation.get("confirmation") != "DROP_ENTITY":
                fail("DESTRUCTIVE_CONFIRMATION_REQUIRED", "Drop requires explicit destructive confirmation.", status=409)
            self.entities.pop(entity, None)
            self.schema.pop(entity, None)
        elif name == "add_field":
            field_name = validate_identifier(operation.get("field", ""))
            if entity not in self.entities:
                fail("NOT_FOUND", "Entity was not found.", status=404)
            if field_name in self.schema.setdefault(entity, set()):
                fail("CONFLICT", "Field already exists.", status=409)
            self.schema[entity].add(field_name)
        else:
            fail("CAPABILITY_UNSUPPORTED", "Schema operation is not supported by this foundation.")
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
