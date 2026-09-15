"""r2db-api schema binding: the field-type/index/constraint vocabulary and
the bound-operation shape `bind_schema_operation` (`structured.py`) composes
its result from (ST9 minus `bind_schema_operation` itself).

A pure leaf: every name here is a literal, a shape-checked dataclass, or a
total, deterministic check over already-passed arguments (an `enum`
declaration and a field's own declared type) -- no connection, catalog,
clock, or global state. The choke point that decides WHEN these run and what
a request does with the result (`bind_schema_operation`, in `structured.py`)
remains in its own module (W3-9: its body calls the registered helper
`validate_enum_declaration`, which stays in `structured.py` per WF-1, so
moving the body here would make this leaf import `structured`, a cycle
design D-1 forbids)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .errors import fail
from .value_types import _declared_type_label

# Phase 6 WP-2 (design docs/design/PHASE6_CONTRACT_160_CLIENT_DISCOVERY_
# V1.md D-3(i)): the contract's field-type vocabulary gains a 7th member,
# `json` (any JSON value) -- the honest name for what an untyped field
# already was (`_check_type` below (in `value_types.py`), `field_type is None`: JSONB-equivalent,
# any JSON value accepted). `json` is a real, declarable word in THIS set
# (accepted by `add_field`'s `field_type` and `create_entity`'s new
# `field_types`, below (in `structured.py`)) -- it is translated to the pre-existing internal
# `None` representation at bind time (see `bind_schema_operation` below (in `structured.py`)),
# never stored as the literal string "json", so every existing `field_type
# is None` code path (this file's own `_check_type` (in `value_types.py`) NUL-check inclusion,
# `postgres.py`'s own JSONB-default DDL) keeps working unchanged for a
# field whose type was explicitly declared `json`.
FIELD_TYPES = {"string", "integer", "number", "boolean", "object", "array", "json"}
MAX_INDEX_FIELDS = 16

# Contract 1.7.0 (D-2, WP-2a): `SCHEMA_OPERATIONS` below is a dead constant
# (no reference anywhere in this repository, work order §2 WP-2a's own
# "実装の指示", 監査照合項目 2) -- the real dispatch/rejection points are
# `bind_schema_operation`'s own `if`/`elif` chain below (in `structured.py`) and `service.py`'s
# `schema_ops`/`unsupported` literals. Left in place unmodified (never
# referenced, so leaving it stale changes nothing observable) rather than
# "fixed" to look complete -- updating it would not satisfy any completion
# condition, only look like it did.
SCHEMA_OPERATIONS = {"create_entity", "add_field", "drop_entity", "create_index", "drop_index"}
# Contract 1.7.0 (D-4, WP-2b): `dry_run`/`plan` join this allowlist --
# `SchemaOperationRequest` is the single flat operation object itself (no
# separate wrapper level unlike `MutationRequest`'s `operations` array), so
# these two request-level fields arrive as ordinary keys on `operation`
# here (in `structured.py`). Contract 1.7.0 (D-5/D-6, WP-2c/WP-2d): `idempotency_key`/`budget`
# join this allowlist too, in their own commits -- `service.py`'s own
# `schema()` reads both directly off `operation` (`operation.get("budget")`/
# `operation.get("idempotency_key")`) BEFORE this function (in `structured.py`) ever runs, but
# the SAME `operation` dict, budget/key still attached, is what `apply_
# schema` then passes to THIS function (in `structured.py`) -- omitting them here would reject
# every schema request that carries either with a generic "shape is not
# supported" `VALIDATION_FAILED`, never reaching the real `budget`/
# `idempotency_key` handling at all. Mirrors WP-2a's identical addition of
# `field_constraints`/`enum`/`nullable` to this same set in its own commit.
_SCHEMA_KEYS = {"operation", "entity", "field", "fields", "field_types", "destructive", "confirmation", "revision", "index", "unique", "field_type", "field_constraints", "enum", "nullable", "dry_run", "plan", "budget", "idempotency_key"}


@dataclass(frozen=True)
class FieldConstraints:
    """Contract 1.7.0 (D-2, R-2): one field's `enum`/`nullable` declaration,
    the choke point's (`_check_type` below (in `value_types.py`)) own value-validation vocabulary
    -- mirrors `field_type`'s own shape (a small, frozen value carried
    alongside a field name), never the raw request JSON.

    `enum`: the closed set of accepted non-null values, already validated
    (non-empty, distinct, each a member of the field's own declared type,
    `validate_enum_declaration` below (in `structured.py`)) -- `None` means no `enum` is
    declared (any value of the field's own type is accepted, contract
    default).
    `nullable`: whether the field accepts a JSON `null` -- defaults to
    `True` (D-2 (2): "既存挙動を宣言化する", the pre-1.7.0 default every
    field, declared or not, already had).
    """

    enum: tuple[Any, ...] | None = None
    nullable: bool = True

    @property
    def is_declared(self) -> bool:
        """`True` iff this instance carries something other than the
        version-wide default (no `enum`, `nullable: true`) -- used to
        decide whether the side-table/in-memory registry needs a row for
        this field at all (WP-2a: a field nobody ever declared a
        constraint on never touches the registry, contract `field_
        constraints` description's own "省略 = 制約なし")."""
        return self.enum is not None or not self.nullable


@dataclass(frozen=True)
class ConstraintPatch:
    """`alter_field`'s own request-side `enum`/`nullable` PATCH (D-2 (5);
    monitor ruling A, rulings-wp3a-review.md, applied to r2db by ruling
    B-2, rulings-wp2a-review.md) -- deliberately distinct from
    `FieldConstraints` above (the COMPOSED, effective state a field ends
    up with). `alter_field` redeclares one field WHOLESALE per the
    contract text, but "wholesale" means "the request's own explicit
    keys replace what they name", never "every key not sent is cleared" --
    the previous (pre-rework) implementation's bug was collapsing this
    into a single `FieldConstraints` at BIND time, before the field's
    EXISTING declared constraints are even known (only `apply_schema`,
    both backends, knows them) -- silently dropping an omitted `nullable`
    back to `true` and an omitted `enum` to "none" instead of leaving
    them alone.

    Three-valued per key, ruling A verbatim: "alter_field で enum 省略 =
    変更なし、enum: null = 解除、nullable 省略 = 変更なし."

    `enum_omitted=True` (the request carried no `enum` key at all): leave
    the field's existing `enum` exactly as it is. `enum_omitted=False,
    enum_clear=True` (`enum: null`): clear it (no `enum` after this
    operation). `enum_omitted=False, enum_clear=False`: the request gave
    an explicit list, in `enum_raw` -- already SHAPE-checked at bind time
    (a non-empty list, no `None` member, no duplicate) but NOT YET
    validated against the field's declared type (`validate_enum_
    declaration`, deferred to `apply_schema`, addendum R-b/R-c, D-2 (3):
    only there is the field's EXISTING declared type known).

    `nullable_omitted=True` (the request carried no `nullable` key at
    all): leave the field's existing `nullable` exactly as it is.
    `nullable_omitted=False`: `nullable` is the request's own explicit
    boolean.
    """

    enum_omitted: bool = True
    enum_clear: bool = False
    enum_raw: tuple[Any, ...] | None = None
    nullable_omitted: bool = True
    nullable: bool = True


#: Contract 1.7.0 (D-2 (2), monitor ruling B-1 rulings-wp2a-review.md):
#: an `enum` is declarable ONLY on a field of one of these 4 scalar
#: types -- `None` (untyped/JSONB-equivalent), `"json"`, `"object"` and
#: `"array"` are ALL rejected outright, never accepted-with-inference.
#: Mirrors MitateDB's own `field_types._ENUM_ELIGIBLE_TYPES` verbatim
#: (m-3: same name, r2db keeps its own leading-underscore module-private
#: convention since this constant, unlike the two functions below (in `structured.py`), was
#: never named in the isomorphism pairing).
_ENUM_ELIGIBLE_TYPES = ("string", "integer", "number", "boolean")


class _ConstraintDeclarationError(Exception):
    """Internal-only signal `validate_enum_declaration` below (in `structured.py`) raises when
    an `enum` declaration is itself invalid -- never surfaced outside this
    module. Every one of that function's 3 call sites (`create_entity`'s
    `field_constraints` loop, `add_field`, and `alter_field`'s composition
    in `apply_schema`, both backends) catches this and calls `fail()`
    itself, attaching the `details` (`field` as a request-internal PATH,
    D-3 (2); `violated_declaration: "constraint_declaration"`, monitor
    ruling m-1; `declared_type`) that only the CALL SITE -- never this
    shared validator -- knows how to compose (m-3's own locked, minimal
    2-argument signature carries no field/path at all, mirroring
    MitateDB's `field_types.validate_enum_declaration`, which similarly
    raises with no `details` of its own attached inside the function)."""


def _fail_constraint_declaration(request_path: str, declared_type: str | None, exc: "_ConstraintDeclarationError") -> None:
    """Shared `fail()` wrapper every `validate_enum_declaration` call site
    below (in `structured.py`) uses (monitor ruling m-1, rulings-wp2a-review.md): `field` is
    the request-internal PATH the offending declaration sits at (D-3 (2)),
    `violated_declaration` is the new 11th vocabulary word this ruling
    adds, and `declared_type` is the field's own declared type (`"json"`
    for an untyped field -- `_declared_type_label` below (in `value_types.py`)) -- never
    `observed_type` (a declaration defect is not a value defect)."""
    fail(
        "VALIDATION_FAILED",
        str(exc),
        details={"field": request_path, "violated_declaration": "constraint_declaration", "declared_type": _declared_type_label(declared_type)},
    )


@dataclass(frozen=True)
class BoundSchemaOperation:
    operation: str
    entity: str
    field: str | None
    fields: tuple[str, ...]
    destructive: bool
    confirmation: Any = None
    field_type: str | None = None
    index: str | None = None
    index_fields: tuple[str, ...] = ()
    unique: bool = False
    # Phase 6 WP-2 (design D-3(iv)): `create_entity`'s own optional,
    # per-field type declarations (`SchemaOperationRequest.field_types`) --
    # a `{field_name: declared_type}` map, ALREADY translated (`json` ->
    # `None`, see `bind_schema_operation` below (in `structured.py`)) to this file's own internal
    # vocabulary. Only ever populated for `create_entity`; empty (never
    # `None`) for every other operation, so a caller never needs an
    # `is None` check before `.get(...)`-ing it.
    field_types: dict[str, str | None] = field(default_factory=dict)
    # Contract 1.7.0 (D-2, WP-2a): `create_entity`'s own optional, per-field
    # constraint declarations (`SchemaOperationRequest.field_constraints`)
    # -- a `{field_name: FieldConstraints}` map, populated ONLY for the
    # fields the request itself named a spec for (D-2 (1): "省略 = 制約
    # なし" -- a name absent from this map carries the version-wide
    # default, never an explicit `FieldConstraints()` entry). Only ever
    # populated for `create_entity`; empty for every other operation.
    field_constraints: dict[str, "FieldConstraints"] = field(default_factory=dict)
    # Contract 1.7.0 (D-2, WP-2a): `add_field`'s own single-field
    # constraint declaration (the request's own top-level `enum`/
    # `nullable`) -- `None` when the request carried neither key (no
    # declaration at all, not even the default made explicit). Only ever
    # populated for `add_field`; `None` for every other operation
    # (`alter_field`'s own single-field declaration is `constraint_patch`
    # below, never this -- ruling B-2/A: `add_field` creates a brand new
    # field, so there is no EXISTING declared state to compose against,
    # unlike `alter_field`).
    constraints: "FieldConstraints | None" = None
    # Contract 1.7.0 (D-2 (5), WP-2a; monitor ruling A/B-2): `alter_field`'s
    # own single-field enum/nullable PATCH -- see `ConstraintPatch`'s own
    # docstring for the three-valued (omitted/clear/value) semantics this
    # carries instead of a collapsed `FieldConstraints`. Only ever
    # populated for `alter_field`; `None` for every other operation.
    # `apply_schema` (both backends) composes this against the field's
    # EXISTING declared constraints -- the first place they are known.
    constraint_patch: "ConstraintPatch | None" = None
