"""r2db-api mutation binding: predicate parsing/validation, projection
validation, and the mutation shape/allowlist/identifier/value-bound
checks every `StorageBackend` mutation crosses before touching stored
data (ST8).

A pure leaf: no connection, global state, clock, or principal -- shape,
operator-allowlist, identifier, and value-bound checks over the request
alone, plus the shared `OPERATORS` allowlist and `Predicate.validate`
that reads it."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .errors import fail, observed_type_of, violation
from .identifier_rules import validate_identifier

OPERATORS = {"eq", "ne", "lt", "lte", "gt", "gte", "in", "contains", "matches", "is_null"}


def _mapping(value: Any, message: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        fail("VALIDATION_FAILED", message, details=violation("request_schema"))
    return value


def parse_predicate(value: Any) -> "Predicate":
    item = _mapping(value, "Filter must be an object.")
    if not {"field", "operator"}.issubset(item) or set(item) - {"field", "operator", "value"}:
        fail("VALIDATION_FAILED", "Filter shape is not supported.", details=violation("request_schema"))
    return Predicate(field=item["field"], operator=item["operator"], value=item.get("value"))


@dataclass(frozen=True)
class Predicate:
    field: str
    operator: str
    value: Any = None

    def validate(self, *, base_path: str) -> None:
        """`base_path` (WP-2e rework, ruling L-3) is THIS predicate's own
        request-internal position (e.g. `"where/2"`, or `"operations/0/
        where/1"` for a mutation's own `where` -- `validate_predicates`
        below builds it, batch index included).

        Ruling N-1 (rulings-r3-r7-flip.md 追補 3): an `identifier_syntax`
        denial's `field` must not carry the malformed identifier itself
        (it can hold SQL fragments/control characters -- SI-10), so this
        stops at `base_path` (the predicate object's own container
        position, e.g. `"where/2"`), never `f"{base_path}/field"` (which
        would still just be the literal key name "field", not the
        identifier value -- but N-1's own container-position examples
        (`where/0`) omit it, so this matches verbatim)."""
        validate_identifier(self.field, field=base_path)
        if self.operator not in OPERATORS:
            fail("VALIDATION_FAILED", "Unsupported filter operator.", details=violation("capability", field=f"{base_path}/operator"))


def validate_projection(select: Any, known_fields: set[str]) -> list[str]:
    """Bounded, non-empty, identifier-checked, catalog-checked field list."""
    if not isinstance(select, list) or not select or len(select) > 100:
        fail("VALIDATION_FAILED", "A bounded non-empty projection is required.", details=violation("request_schema", field="select"))
    for i, field_name in enumerate(select):
        # Ruling N-1: an identifier_syntax denial's `field` stops at the
        # container position ("select" -- N-1's own example), never the
        # per-index path (which is harmless on its own here, but N-1's
        # worked examples are followed verbatim across every position).
        validate_identifier(field_name, field="select")
    for i, field_name in enumerate(select):
        # Contract 1.11.0 (subordinate ruling 16): an undeclared field name
        # here is a request_schema violation naming the position -- NOT_FOUND
        # is not a conforming refusal of it at this position
        # (errors.details_vocabulary.undeclared_field).
        if field_name not in known_fields:
            fail("VALIDATION_FAILED", "Field is not declared.", details=violation("request_schema", field=f"select/{i}"))
    return select


def validate_predicates(where: list["Predicate"], known_fields: set[str], *, path_prefix: str = "where") -> list["Predicate"]:
    """Operator-allowlist- and catalog-checked predicates (already parsed).
    `path_prefix` (WP-2e rework, ruling L-3) is the request-internal path
    to THIS `where` list itself -- `"where"` for a top-level query (the
    default, both cells' own `query`), or `f"operations/{i}/where"` for
    one mutation item's own `where` (`bind_mutation` below, batch index
    included)."""
    for i, predicate in enumerate(where):
        predicate.validate(base_path=f"{path_prefix}/{i}")
        # Contract 1.11.0 (subordinate ruling 16): an undeclared field name
        # in a `where` predicate -- whether a top-level query's own `where`
        # or a mutation item's own `where` (`path_prefix` already carries
        # `operations/<i>/where` in that case) -- is a request_schema
        # violation naming `<path_prefix>/<i>/field`, not NOT_FOUND.
        if predicate.field not in known_fields:
            fail("VALIDATION_FAILED", "Field is not declared.", details=violation("request_schema", field=f"{path_prefix}/{i}/field"))
    return where


MUTATION_OPERATIONS = {"insert", "update", "upsert", "delete"}
_MUTATION_KEYS = {"operation", "values", "where", "destructive", "confirmation", "expected_revision", "idempotency_key", "unique_key"}
MAX_EXPECTED_REVISION_LENGTH = 128


@dataclass(frozen=True)
class BoundMutation:
    """A single mutation item that has crossed the shared validation
    boundary: shape, operator allowlist, identifiers, and value bounds are
    settled. `destructive`/`confirmation` are carried through unevaluated --
    see `require_destructive_confirmation` for why that check is deliberately
    left to each backend's own call site rather than folded in here.
    `expected_revision` is similarly carried through unevaluated: whether it
    can be honoured at all (a backend may not yet implement the revision
    column) and how it resolves against stored rows (R-4) is each backend's
    own execution concern.
    """

    operation: str
    where: list["Predicate"]
    values: dict[str, Any]
    destructive: bool
    confirmation: Any = None
    expected_revision: str | None = None
    # Contract 1.1.0 addendum (Q-1 adjudication, 案B, 2026-08-28): names the
    # declared uniqueness key `upsert` should use as its existence test when
    # an entity declares more than one. Only `upsert` accepts it (§0.5 Q-1 /
    # R-5); which key is actually available/selected is catalog knowledge
    # only a backend has, so -- like `expected_revision` above -- this
    # shared, catalog-agnostic function only validates its shape/placement
    # and carries it through unevaluated.
    unique_key: str | None = None


# WP-2e rework (ruling L-3): `operation_index` (REQUIRED, both call sites
# -- `ApplicationCell._apply`/`PostgresCell._apply` -- already have a
# batch index in scope) threads this mutation item's own `operations/<i>`
# position into every IDENTIFIER_INVALID/CAPABILITY_UNSUPPORTED `field`
# this function (or a function it calls) raises for a value inside this
# ONE operation -- never a bare, position-less literal.
def bind_mutation(operation: Any, known_fields: set[str], *, operation_index: int) -> BoundMutation:
    if not isinstance(operation, dict) or set(operation) - _MUTATION_KEYS:
        fail("VALIDATION_FAILED", "Mutation shape is not supported.", details=violation("request_schema"))
    name = operation.get("operation")
    if name not in MUTATION_OPERATIONS:
        fail("CAPABILITY_UNSUPPORTED", "Mutation operation is not supported.", details=violation("capability", field=f"operations/{operation_index}/operation"))
    # Contract 1.7.0 (D-5, WP-2c, ruling I-12): the present-denial that
    # used to sit here unconditionally is removed in the SAME commit as
    # `capabilities().idempotency` flipping to `enabled` -- `idempotency_
    # key` is not itself a `Mutation` (per-operation) property the common
    # contract defines (`definitions.Mutation.properties` has no such
    # key; it is `MutationRequest.properties.idempotency_key`, a REQUEST-
    # level field only `service.py`'s own `mutate_result`/`_mutate_
    # outcome` ever reads). `_MUTATION_KEYS` keeps recognizing it here
    # ONLY so this peer's own internal (non-HTTP) mutation-item shape
    # (`conformance/conformance_adapter_r2db.py`'s `_build_mutation_item`,
    # port v1.11) -- which carries a request's single, uniform key
    # duplicated onto every operation item, there being no separate top-
    # level parameter on this shape before this commit -- keeps binding
    # without error; `_mutate_outcome` below is what actually folds and
    # USES it (`_fold_operation_idempotency_keys`), not this function.
    if name == "insert" and "where" in operation:
        # WP-2 review M-4: `insert`'s `where` was previously parsed and then
        # silently never used by any backend's insert path -- the same
        # silent-ignore shape upsert's own `where` rejection closes (M-3
        # below), now closed symmetrically for insert.
        fail("VALIDATION_FAILED", "insert does not accept a filter.", details=violation("unsupported_field", field="where"))
    # Whether a `where` on `upsert` is rejected (R-5, corrigendum M-3:
    # upsert's existence test is the entity's declared uniqueness key, never
    # a client-supplied predicate) needs live catalog knowledge -- an
    # entity with zero declared uniqueness keys must still be refused with
    # CAPABILITY_UNSUPPORTED first, even if a stray `where` also came along
    # (a capability that is not available at all takes precedence over a
    # shape complaint about a request against it). That ordering can only
    # be decided once a backend has looked at the entity's own declared
    # keys, so this shared, catalog-agnostic function only parses `where`
    # here; each backend's own upsert execution path (`ApplicationCell.
    # _apply_upsert`) rejects a non-empty `where` itself, once it already
    # knows upsert is actually executable for this entity.
    raw_where = operation.get("where", [])
    if not isinstance(raw_where, list):
        fail("VALIDATION_FAILED", "Mutation filter must be a list.", details=violation("request_schema", field="where"))
    where = validate_predicates([parse_predicate(item) for item in raw_where], known_fields, path_prefix=f"operations/{operation_index}/where")
    raw_values = operation.get("values", {})
    if not isinstance(raw_values, dict):
        fail("VALIDATION_FAILED", "Mutation values must be an object.", details=violation("request_schema", field="values"))
    if len(raw_values) > 100:
        # Contract 1.2.0 (subordinate ruling 7(B), Q1-D8): this mirrors the
        # contract's own fixed `Mutation.values.maxProperties: 100` shape
        # bound, not a deployment-tunable `limits.classes` resource -- so it
        # is `VALIDATION_FAILED` (400), never `LIMIT_EXCEEDED` (which would
        # be unable to name a `limit_class` member for this, since no such
        # class exists).
        fail("VALIDATION_FAILED", "Mutation contains too many fields.", details=violation("request_schema", field="values"))
    for key in raw_values:
        # Ruling N-1 (rulings-r3-r7-flip.md 追補 3): an identifier_syntax
        # denial must not carry the malformed key itself in `field` -- it
        # was the C-03 test_identifier_positions_reject_every_payload
        # regression this ruling exists to close (an adversarial `values`
        # key echoed verbatim through this f-string). Stop at the
        # container position, `operations/<i>/values` (N-1's own example).
        validate_identifier(key, field=f"operations/{operation_index}/values")
        # Contract 1.11.0 (subordinate ruling 16): an undeclared field name
        # here is a request_schema violation naming the position, including
        # the key itself (`operations/<i>/values/<name>`, the contract's
        # own form for this position) -- the identifier check above has
        # already rejected any key outside the identifier syntax, so `key`
        # carries no adversarial content here.
        if key not in known_fields:
            fail("VALIDATION_FAILED", "Field is not declared.", details=violation("request_schema", field=f"operations/{operation_index}/values/{key}"))
    if name in {"insert", "update", "upsert"} and "id" in raw_values:
        # R-3, property 4: the row address is always server-assigned. A
        # client may read `id` (select/where/order_by) freely but can never
        # write it, on insert (it would forge an address) or update/upsert
        # (it would move an existing row's address).
        fail("VALIDATION_FAILED", "The id field is server-assigned and cannot be supplied.", details=violation("unsupported_field", field="values/id"))
    if "destructive" in operation and not isinstance(operation["destructive"], bool):
        fail("VALIDATION_FAILED", "Destructive flag must be boolean.", details=violation("request_schema", field="destructive", declared_type="boolean", observed_type=observed_type_of(operation["destructive"])))
    expected_revision: str | None = None
    if "expected_revision" in operation:
        expected_revision = operation["expected_revision"]
        if not isinstance(expected_revision, str) or len(expected_revision) > MAX_EXPECTED_REVISION_LENGTH:
            fail("VALIDATION_FAILED", "expected_revision must be a string.", details=violation("request_schema", field="expected_revision", declared_type="string", observed_type=observed_type_of(expected_revision)))
        if "\x00" in expected_revision:
            # R-7 addendum (WP-3 review blocker-2): a NUL byte here would
            # otherwise reach PostgreSQL's `uuid`/`text` comparison and be
            # rejected at execution time, not deterministically here.
            fail("VALIDATION_FAILED", "expected_revision must not contain a NUL character.", details=violation("request_schema", field="expected_revision"))
        if name == "insert":
            # R-4, contract's revision-precondition clause 6: a precondition
            # asserts an existing row's identity; insert creates one, so the
            # combination is never meaningful.
            fail("VALIDATION_FAILED", "insert does not support a revision precondition.", details=violation("unsupported_field", field="expected_revision"))
        if name == "update" and not raw_values:
            # R-4, corrigendum M-1: the empty-`values` `update` branch below
            # does not write anything, so a precondition riding along with
            # it would be silently discarded rather than evaluated -- one
            # of the "precondition asserted, then quietly ignored" gaps this
            # foundation must not have.
            fail("VALIDATION_FAILED", "A revision precondition requires values to apply.", details=violation("request_schema", field="expected_revision"))
    if name in {"update", "delete"} and not where:
        fail("VALIDATION_FAILED", "This operation requires a non-empty filter.", details=violation("request_schema", field="where"))
    unique_key: str | None = None
    if "unique_key" in operation:
        if name != "upsert":
            fail("VALIDATION_FAILED", "unique_key is only supported by upsert.", details=violation("unsupported_field", field="unique_key"))
        unique_key = validate_identifier(operation["unique_key"], field=f"operations/{operation_index}/unique_key")
    return BoundMutation(name, where, dict(raw_values), bool(operation.get("destructive")), operation.get("confirmation"), expected_revision, unique_key)
