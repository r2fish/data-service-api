"""C-20 -- a peer's published field constraints (`enum`/`nullable`) agree
with observed behavior (SI-05, SI-15).

design: docs/design/PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md
D-2, §6.2 "C-20 制約宣言の一致", registered in `conformance-tests/
CONDITIONS.md`. Every test here carries `@pytest.mark.condition("C-20")`
via the module-level `pytestmark`.

Declare-first, capability `constraint_declarations` (contract 1.7.0, new),
written in the C-07 (ii)/C-22 declare-first house style: ONE test branches
internally on the plug's own declared status (never `pytest.skip` -- work
order §0.4 item 5 forbids it; every collected test must actually assert
something on every plug), records `observed_branch`, and cross-checks it
against the branch the declaration itself implies:

  - `unavailable` branch: a schema request carrying `field_constraints`/
    `enum`/`nullable` (on `create_entity`, `add_field`, and `alter_field`
    alike -- WP-1b rework, review point D) is refused with `CAPABILITY_
    UNSUPPORTED` before execution -- the whole request fails, so nothing
    it would have created or altered exists afterward (zero side
    effects). `alter_field` itself accepts `SurfaceAbsent` here too (no
    real entry point exists at all on some plugs for the PRIMITIVE, port
    v1.13 §6.1 item 8, independently of `constraint_declarations`) -- the
    same shape the `enabled` branch's own upsert leg already uses for
    `create_unique_index`.
  - `enabled`/`partial`/`planned` branch ("enforced"): the declared
    constraints are enforced at the value-validation boundary on
    `insert`/`update` (and `upsert`, where the peer's own unique-key
    primitive makes `upsert` meaningfully testable at all -- see the
    disclosed scope limit below), a value inside the enum / a non-null
    required value is accepted (positive control), the catalog reports the
    constraints back total over the entity's own fields in the same
    version, a query predicate outside the enum simply matches no row
    (never refused), and a conflicting `alter_field` is refused in full
    with `CONFLICT`, changing nothing -- not even the schema revision --
    while a non-conflicting one succeeds and advances it. **`nullable`'s
    own upsert leg (WP-1b rework, review 1 B3)**: an insert-RESOLVED
    upsert omitting a nullable:false field is rejected identically to
    insert's own omission (`observed_type: absent`); an update-RESOLVED
    upsert omitting the same field is NOT rejected -- update never
    requires an omitted field to be present, and resolving to update must
    not manufacture a nullable violation out of a field the request never
    named.

**Disclosed scope limit (upsert leg)**: `upsert` only ever executes on an
entity that declares a usable unique key (C-17); on a peer with no real
unique-key primitive on this port (`create_unique_index` raising
`SurfaceAbsent`) or that refuses it as unsupported, presenting `upsert`
here would observe `CAPABILITY_UNSUPPORTED` for the missing key, not a
genuine enum/nullable check -- that is a DIFFERENT capability's absence,
not evidence about this one. The upsert leg runs only where a real unique
key can be constructed; the insert/update legs alone still exercise the
value-validation choke points D-2(3) names as load-bearing for `enum`/
`nullable` on every plug regardless.

**Disclosed scope limit (MitateDB `alter_field` transaction boundary)**:
whether the existing-row scan a `CONFLICT`-refused `alter_field` performs
shares ONE transaction with the DDL/registry update it would otherwise
commit is not observable from this common suite -- (6) below only observes
"nothing changed", true whether or not a concurrent writer could interleave
between a separate scan and a separate DDL transaction. That race is
peer-local territory (design D-2 実装の形 4, disclosed there for WP-3a).

**Design v1.5 補正 (監督裁定 A, `{scratchpad}/rulings-wp3a-review.md`)**: the
`enabled`/`partial`/`planned` branch also covers `alter_field`'s corrected
`enum` semantics -- an `alter_field` that OMITS `enum` leaves the field's
existing `enum` untouched (leg (8) below), and an `alter_field` that
carries an explicit `enum: null` clears the field's enum (leg (9) below).
Port v1.13 追補 (`docs/design/CONFORMANCE_ADAPTER_V1.md` §23.4): leg (9)
needs `schema_operation_with_result` to carry a literal JSON `enum: null`
on the wire, distinct from omitting the key entirely -- both used to
collapse onto the same Python `None` default. `conformance-tests/
adapter.py` now exposes a dedicated tri-state sentinel, `ENUM_CLEAR`, for
exactly this: `enum=None` (default) omits the key, `enum=ENUM_CLEAR` sends
`enum: null`, and any other `Sequence` sends `enum: [...]`, unchanged from
before.

**監督裁定 M-6 (`{scratchpad}/rulings-wp2a-review.md`, contract addendum on
`structured_operations.alter_field`)**: leg (10) below covers `add_field`
declaring `nullable: false` on an entity that already holds rows -- refused
`CONFLICT` on the same rule `alter_field` uses, since every existing row
would hold `null` in the new field -- bracketed by real `alter_field`
revisions exactly as legs (6)/(7) are, and contrasted with the same
`add_field` succeeding on a zero-row entity.

**監督裁定 m-1 (同上, `errors.details_vocabulary.violated_declaration_
vocabulary`'s new eleventh word)**: leg (11) below covers a declaration
that is itself invalid -- `constraint_declaration` -- on `create_entity`
and `add_field` alike: an `enum` declared on a field whose own declared
type admits none (an untyped/`json` field), and, regardless of field
type, an empty or a duplicated `enum`; each is refused `VALIDATION_FAILED`
with zero side effects, and the `json`-field case additionally carries
`declared_type: "json"`.

**監督裁定 N-1 (`{scratchpad}/rulings-r2-closure.md`, contract v1.7 補正 on
`structured_operations.alter_field`)**: leg (12) below covers an
`alter_field` carrying neither `enum` nor `nullable` -- it declares
nothing, and is refused `VALIDATION_FAILED`, `violated_declaration:
constraint_declaration`, `field: "operation"` (a request-internal path;
the missing declaration is a defect of the operation as a whole, not
attributable to any one field) -- bracketed exactly as legs (6)/(7)/(10)
are, proving the refused attempt does not advance the schema revision.

**Overlaps C-17** (same declaration-agreement posture, a different
declaration: C-17 fixes mutation-class/addressability/uniqueness, this row
fixes field-level value constraints).
"""
from __future__ import annotations

import pytest

from adapter import ENUM_CLEAR, ConformanceAdapter, ConformanceDenial, SurfaceAbsent, fresh_identifier
from conftest import provision_pair

pytestmark = pytest.mark.condition("C-20")


def _status(adapter: ConformanceAdapter) -> str:
    return adapter.capability_document().get("capabilities", {}).get("constraint_declarations", {}).get(
        "status", "unavailable"
    )


def _expected_branch_for_status(status: str) -> str:
    return "unavailable" if status == "unavailable" else "enforced"


def _catalog_row(iso: ConformanceAdapter, developer, entity: str) -> dict:
    catalog = iso.catalog_document(developer)
    return {row["entity"]: row for row in catalog["entities"]}[entity]


def _revision_of(result: dict) -> str:
    """The response `revision` of a real, successful `schema_operation_
    with_result` call. `SchemaOperationResult.revision` (spec/data-
    service-api.v1.json `schemas.SchemaOperationResult`) is `required`
    and always present on a real response -- unlike `EntityDescriptor`,
    which carries no `revision` property at all (`definitions.
    EntityDescriptor`, `additionalProperties: false`), and unlike
    `CatalogDocument`, which carries no document-level revision either.
    A catalog row's `.get("revision")` is therefore always `None`; this
    helper is the ONLY contract-defined way to observe a real revision
    value."""
    revision = result.get("revision")
    assert revision is not None, f"schema_operation_with_result carries no 'revision' -- {result!r}"
    return revision


def _revision_advanced_by_one(before: str, after: str) -> bool:
    """True when `after` is exactly one real commit ahead of `before`.

    Both currently-registered peers keep their schema revision as a
    monotonic integer counter incremented by exactly one per committed
    schema operation (`r2db-api/src/r2db_api/structured.py::ApplicationCell._apply_schema_locked`'s
    `self.schema_revision += 1`; `MitateDB-api/src/mitatedb_api/
    backend_sqlite.py::SQLiteBackend`'s `self._schema_revision += 1`; the
    Postgres backends mirror this via `_bump_revision`/`_bump_schema_
    revision`), and `SchemaOperationResult.revision` reports that
    counter stringified (`schema_operation_with_result`'s own
    docstring, `conformance-tests/adapter.py`). Comparing
    `int(after) == int(before) + 1` catches a CONFLICT-refused (or
    CAPABILITY_UNSUPPORTED-refused) `alter_field` that silently also
    bumps the counter -- exactly the mutation design docs/design/
    PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md's C-20 (6)
    row guards against (monotone S-g) -- as a delta of 2 rather than 1,
    when exactly one real, harmless schema commit is known to separate
    `before` and `after`."""
    return int(after) == int(before) + 1


def test_c20_constraint_declaration_agreement(adapter: ConformanceAdapter, isolated) -> None:
    iso = isolated
    status = _status(adapter)
    developer, runtime, _app_id = provision_pair(iso, app_prefix="c20")

    observed_branch: str
    if status == "unavailable":
        entity = fresh_identifier("c20u")
        with pytest.raises(ConformanceDenial) as ei:
            iso.schema_operation_with_result(
                developer, entity, "create_entity",
                fields=["status"], field_types={"status": "string"},
                field_constraints={"status": {"enum": ["a", "b"], "nullable": False}},
            )
        assert ei.value.code == "CAPABILITY_UNSUPPORTED", (
            f"{adapter.name}: constraint_declarations is 'unavailable', but a create_entity carrying "
            f"field_constraints was refused with {ei.value.code!r} instead of CAPABILITY_UNSUPPORTED"
        )
        assert entity not in iso.entities(developer), (
            f"{adapter.name}: a create_entity refused as unavailable must have zero side effects, but "
            f"{entity!r} exists afterward"
        )

        plain_entity = fresh_identifier("c20u2")
        iso.create_entity(developer, plain_entity, {"label": "text"})
        with pytest.raises(ConformanceDenial) as ei2:
            iso.schema_operation_with_result(
                developer, plain_entity, "add_field", field="tag", field_type="string", enum=["x", "y"],
            )
        assert ei2.value.code == "CAPABILITY_UNSUPPORTED", (
            f"{adapter.name}: add_field carrying 'enum' was refused with {ei2.value.code!r} instead of "
            "CAPABILITY_UNSUPPORTED while constraint_declarations is unavailable"
        )
        row = _catalog_row(iso, developer, plain_entity)
        assert "tag" not in row["fields"], f"{adapter.name}: the refused add_field must not have added the field"

        # WP-1b rework (review point D): this branch's own docstring
        # claim ("on create_entity, add_field, and alter_field alike")
        # must be true of the code, not only of the prose -- alter_field
        # is exercised here too, not only create_entity/add_field.
        # `alter_field` itself has no real entry point at all on some
        # plugs as of this port revision (neither peer implements the
        # PRIMITIVE yet, independently of whether `constraint_
        # declarations` is declared) -- `SurfaceAbsent` is accepted here
        # exactly like the upsert leg below accepts it for `create_unique_
        # index`, never silently swallowed for any OTHER exception.
        # C-20 test defect fix (subordinate ruling, WP-3a's first real
        # 'enabled' run): `row.get("revision")` read a key `EntityDescriptor`
        # does not define (see `_revision_of`'s docstring above), so the
        # comparison below always held vacuously (`None == None`) rather
        # than asserting anything. It is dropped here rather than patched:
        # this branch's own refusal is `SurfaceAbsent`/`CAPABILITY_
        # UNSUPPORTED` BEFORE execution, and on this port revision every
        # currently-registered schema-mutation call this branch could use
        # as an independent "real revision" probe is itself unusable --
        # `alter_field` is the very primitive under refusal here (`Surface
        # Absent` on a peer with no real entry point at all), and `add_
        # field`/`create_entity`'s own in-process response does not carry
        # a revision on every currently-registered adapter either
        # (`MitateDB-api/src/mitatedb_api/cell.py`'s `add_field`/`create_
        # collection` return nothing; only the HTTP surface's `post_schema`
        # computes one post-hoc via `_post_schema_revision`). Design docs/
        # design/PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md
        # §6.2's own `unavailable`-branch assert list (D-2) does not
        # require a revision check here -- only "refused before execution,
        # zero side effects" -- so the `field_constraints`-unchanged
        # assert below (a real, working check) already carries that
        # requirement for this leg; the revision-unchanged assert design
        # adds is specific to (6) in the `enforced` branch below, where
        # `alter_field` is a genuine, executing primitive whose own
        # response revision this suite can and does rely on.
        row = _catalog_row(iso, developer, plain_entity)
        constraints_before = row.get("field_constraints")
        try:
            iso.schema_operation_with_result(developer, plain_entity, "alter_field", field="label", nullable=False)
        except SurfaceAbsent:
            pass
        except ConformanceDenial as ei3:
            assert ei3.code == "CAPABILITY_UNSUPPORTED", (
                f"{adapter.name}: alter_field carrying 'nullable' was refused with {ei3.code!r} instead of "
                "CAPABILITY_UNSUPPORTED while constraint_declarations is unavailable"
            )
            row_after_alter = _catalog_row(iso, developer, plain_entity)
            assert row_after_alter.get("field_constraints") == constraints_before, (
                f"{adapter.name}: a refused alter_field must not change the catalog's field_constraints"
            )
        else:
            pytest.fail(
                f"{adapter.name}: alter_field carrying 'nullable' succeeded while constraint_declarations is "
                "unavailable"
            )
        observed_branch = "unavailable"
    else:
        entity = fresh_identifier("c20e")
        enum_field, nonnull_field = "status", "req"
        iso.schema_operation_with_result(
            developer, entity, "create_entity",
            fields=[enum_field, nonnull_field, "label"],
            field_types={enum_field: "string", nonnull_field: "string"},
            field_constraints={enum_field: {"enum": ["a", "b"]}, nonnull_field: {"nullable": False}},
        )

        # (1)/(3) insert leg.
        with pytest.raises(ConformanceDenial) as ei:
            iso.attempt_mutation(
                runtime, entity, "insert",
                values={enum_field: "z", nonnull_field: "ok"}, where_field=None, where_value=None,
            )
        assert ei.value.code == "VALIDATION_FAILED", f"{adapter.name}: enum violation on insert -> {ei.value.code!r}"
        assert ei.value.details.get("violated_declaration") == "enum", (
            f"{adapter.name}: insert enum violation details {ei.value.details!r} lacks violated_declaration=enum"
        )
        assert "observed_type" not in ei.value.details, (
            f"{adapter.name}: an 'enum' violation must not carry 'observed_type' (D-3(4)) -- {ei.value.details!r}"
        )

        with pytest.raises(ConformanceDenial) as ei_null:
            iso.attempt_mutation(
                runtime, entity, "insert",
                values={enum_field: "a", nonnull_field: None}, where_field=None, where_value=None,
            )
        assert ei_null.value.code == "VALIDATION_FAILED"
        assert ei_null.value.details.get("violated_declaration") == "nullable", (
            f"{adapter.name}: explicit null on a nullable:false field -> {ei_null.value.details!r}"
        )
        assert ei_null.value.details.get("observed_type") == "null", ei_null.value.details

        with pytest.raises(ConformanceDenial) as ei_absent:
            iso.attempt_mutation(
                runtime, entity, "insert", values={enum_field: "a"}, where_field=None, where_value=None,
            )
        assert ei_absent.value.code == "VALIDATION_FAILED"
        assert ei_absent.value.details.get("violated_declaration") == "nullable", ei_absent.value.details
        assert ei_absent.value.details.get("observed_type") == "absent", (
            f"{adapter.name}: an insert omitting a nullable:false field must report observed_type=absent -- "
            f"{ei_absent.value.details!r}"
        )

        # (2) positive control.
        marker = fresh_identifier("c20ok")
        iso.attempt_mutation(
            runtime, entity, "insert",
            values={enum_field: "a", nonnull_field: "ok", "label": marker}, where_field=None, where_value=None,
        )
        assert len(iso.select_eq(runtime, entity, [enum_field], "label", marker)) == 1, (
            f"{adapter.name}: the valid insert did not produce a readable row"
        )

        # update leg.
        with pytest.raises(ConformanceDenial) as ei_upd_enum:
            iso.attempt_mutation(
                runtime, entity, "update",
                values={enum_field: "not-in-set"}, where_field="label", where_value=marker,
            )
        assert ei_upd_enum.value.code == "VALIDATION_FAILED"
        assert ei_upd_enum.value.details.get("violated_declaration") == "enum", ei_upd_enum.value.details

        with pytest.raises(ConformanceDenial) as ei_upd_null:
            iso.attempt_mutation(
                runtime, entity, "update",
                values={nonnull_field: None}, where_field="label", where_value=marker,
            )
        assert ei_upd_null.value.code == "VALIDATION_FAILED"
        assert ei_upd_null.value.details.get("violated_declaration") == "nullable", ei_upd_null.value.details

        # upsert leg -- only where a real unique key can be constructed
        # (disclosed scope limit, module docstring).
        upsert_leg_ran = False
        try:
            iso.create_unique_index(developer, entity, fresh_identifier("c20idx"), ["label"])
            upsert_leg_ran = True
        except SurfaceAbsent:
            pass
        except ConformanceDenial as denial:
            if denial.code != "CAPABILITY_UNSUPPORTED":
                raise
        if upsert_leg_ran:
            insert_marker = fresh_identifier("c20up_ins")
            with pytest.raises(ConformanceDenial) as ei_up_ins:
                iso.attempt_mutation(
                    runtime, entity, "upsert",
                    values={"label": insert_marker, enum_field: "nope", nonnull_field: "ok"},
                    where_field=None, where_value=None,
                )
            assert ei_up_ins.value.code == "VALIDATION_FAILED", (
                f"{adapter.name}: an insert-resolved upsert violating 'enum' was not rejected -- got "
                f"{ei_up_ins.value.code!r} (precisely the D-2 gap C-20 must catch)"
            )
            assert ei_up_ins.value.details.get("violated_declaration") == "enum", ei_up_ins.value.details

            update_marker = fresh_identifier("c20up_upd")
            iso.attempt_mutation(
                runtime, entity, "insert",
                values={"label": update_marker, enum_field: "a", nonnull_field: "ok"},
                where_field=None, where_value=None,
            )
            with pytest.raises(ConformanceDenial) as ei_up_upd:
                iso.attempt_mutation(
                    runtime, entity, "upsert",
                    values={"label": update_marker, enum_field: "still-nope"},
                    where_field=None, where_value=None,
                )
            assert ei_up_upd.value.code == "VALIDATION_FAILED", (
                f"{adapter.name}: an update-resolved upsert violating 'enum' was not rejected -- got "
                f"{ei_up_upd.value.code!r}"
            )
            assert ei_up_upd.value.details.get("violated_declaration") == "enum", ei_up_upd.value.details

            # nullable, upsert leg (S-k / review 1 B3, WP-1b rework): an
            # insert-resolved upsert OMITTING a nullable:false field is
            # rejected the same as insert's own omission above
            # (observed_type=absent); an update-resolved upsert omitting
            # it is NOT rejected -- update never requires an omitted field
            # to be present, so resolving to update must not manufacture a
            # nullable violation out of a field the request never named.
            nullable_insert_marker = fresh_identifier("c20up_nullins")
            with pytest.raises(ConformanceDenial) as ei_up_ins_null:
                iso.attempt_mutation(
                    runtime, entity, "upsert",
                    values={"label": nullable_insert_marker, enum_field: "a"},
                    where_field=None, where_value=None,
                )
            assert ei_up_ins_null.value.code == "VALIDATION_FAILED", (
                f"{adapter.name}: an insert-resolved upsert omitting a nullable:false field was not "
                f"rejected -- got {ei_up_ins_null.value.code!r}"
            )
            assert ei_up_ins_null.value.details.get("violated_declaration") == "nullable", (
                ei_up_ins_null.value.details
            )
            assert ei_up_ins_null.value.details.get("observed_type") == "absent", (
                f"{adapter.name}: an insert-resolved upsert omitting a nullable:false field must report "
                f"observed_type=absent -- {ei_up_ins_null.value.details!r}"
            )

            nullable_update_marker = fresh_identifier("c20up_nullupd")
            iso.attempt_mutation(
                runtime, entity, "insert",
                values={"label": nullable_update_marker, enum_field: "a", nonnull_field: "ok"},
                where_field=None, where_value=None,
            )
            # The SAME "label" (this entity's own unique key) already
            # exists, so this upsert resolves to an UPDATE: omitting
            # nonnull_field means "leave it alone", not "set it to null",
            # and must not be rejected.
            iso.attempt_mutation(
                runtime, entity, "upsert",
                values={"label": nullable_update_marker, enum_field: "b"},
                where_field=None, where_value=None,
            )
            row_check = iso.select_eq(runtime, entity, [nonnull_field], "label", nullable_update_marker)
            assert row_check and row_check[0].get(nonnull_field) == "ok", (
                f"{adapter.name}: an update-resolved upsert omitting a nullable:false field must not be "
                f"rejected, and must leave that field's EXISTING value untouched -- {row_check!r}"
            )

        # (5) query predicate outside the enum: not a violation, zero rows.
        outside_rows = iso.select_eq(runtime, entity, [enum_field], enum_field, "not-a-member")
        assert outside_rows == [], (
            f"{adapter.name}: a query predicate value outside a field's declared enum must simply match no "
            f"row, not be refused -- got {outside_rows!r}"
        )

        # (4) catalog round-trip: total over the entity's own fields.
        row = _catalog_row(iso, developer, entity)
        constraints = row.get("field_constraints")
        assert isinstance(constraints, dict) and constraints, (
            f"{adapter.name}: catalog entity {entity!r} carries no non-empty field_constraints -- {row!r}"
        )
        assert set(row["fields"]) <= set(constraints.keys()), (
            f"{adapter.name}: field_constraints must be total over {entity!r}'s own fields -- fields="
            f"{row['fields']!r}, field_constraints keys={sorted(constraints.keys())!r}"
        )
        for field_name in row["fields"]:
            assert "nullable" in constraints[field_name], (
                f"{adapter.name}: field_constraints[{field_name!r}] omits 'nullable' (required on every "
                f"field, total over fields) -- {constraints!r}"
            )
        assert constraints[enum_field].get("enum") == ["a", "b"], (
            f"{adapter.name}: field_constraints[{enum_field!r}]['enum'] does not round-trip -- "
            f"{constraints[enum_field]!r}"
        )
        assert constraints[nonnull_field].get("nullable") is False, (
            f"{adapter.name}: field_constraints[{nonnull_field!r}]['nullable'] does not round-trip 'false' -- "
            f"{constraints[nonnull_field]!r}"
        )

        # (6)/(7) alter_field: conflict refuses in full; non-conflict
        # succeeds and advances the revision. A fresh row carrying the
        # enum value ("b") that the narrower alter_field below excludes,
        # so the conflict is genuine (the earlier rows above only ever
        # carry "a").
        #
        # C-20 test defect fix (subordinate ruling, WP-3a's first real
        # 'enabled' run): `row.get("revision")` read a key `EntityDescriptor`
        # does not define, and `CatalogDocument` carries no document-level
        # revision either (see `_revision_of`'s docstring above) -- every
        # comparison below against a catalog row's `.get("revision")` was
        # always `None == None`, asserting nothing. `add_field`'s own
        # in-process response does not reliably carry a revision on every
        # currently-registered adapter either (see the comment on the
        # `unavailable` branch above -- `MitateDB-api`'s in-process
        # `add_field`/`create_entity` return nothing; only its HTTP
        # surface computes one post-hoc). `alter_field` itself -- the
        # PRIMITIVE actually under test here, and the one this suite
        # already requires to carry a real `revision` on success (the
        # pre-existing assert right below) -- brackets the refusal
        # instead: a harmless, always-non-conflicting `alter_field`
        # (`nullable: true` on `"label"`, already that field's own
        # default, so no existing row can possibly violate it) gives a
        # real baseline revision BEFORE the CONFLICT attempt, and the
        # FINAL successful, non-conflicting `alter_field` below gives the
        # "after" value. Exactly one real commit (that final `alter_
        # field`) must separate them -- proving the CONFLICT-refused
        # `alter_field` in between committed none.
        conflict_marker = fresh_identifier("c20conflict")
        iso.attempt_mutation(
            runtime, entity, "insert",
            values={enum_field: "b", nonnull_field: "ok", "label": conflict_marker},
            where_field=None, where_value=None,
        )
        revision_before = _revision_of(
            iso.schema_operation_with_result(developer, entity, "alter_field", field="label", nullable=True)
        )
        row = _catalog_row(iso, developer, entity)
        constraints = row.get("field_constraints")
        count_before = iso.count(runtime, entity)
        with pytest.raises(ConformanceDenial) as ei_alter:
            iso.schema_operation_with_result(developer, entity, "alter_field", field=enum_field, enum=["a"])
        assert ei_alter.value.code == "CONFLICT", (
            f"{adapter.name}: alter_field narrowing {enum_field!r}'s enum to ['a'] while a real row "
            f"({conflict_marker!r}) carries 'b' -> {ei_alter.value.code!r}, expected CONFLICT"
        )
        assert ei_alter.value.details.get("violated_declaration") in ("enum", "nullable"), ei_alter.value.details
        assert conflict_marker not in str(ei_alter.value.details), (
            f"{adapter.name}: a CONFLICT-refused alter_field's details must never carry a row value or "
            f"identifier that discloses which row conflicted (SI-10) -- {ei_alter.value.details!r}"
        )
        row_after_conflict = _catalog_row(iso, developer, entity)
        assert row_after_conflict.get("field_constraints") == constraints, (
            f"{adapter.name}: a refused alter_field must not change the catalog's field_constraints"
        )
        assert iso.count(runtime, entity) == count_before, f"{adapter.name}: a refused alter_field changed row count"

        result = iso.schema_operation_with_result(
            developer, entity, "alter_field", field=enum_field, enum=["a", "b", "z"],
        )
        revision_final = result.get("revision")
        assert isinstance(result, dict) and revision_final is not None, (
            f"{adapter.name}: a successful alter_field's result carries no 'revision' -- {result!r}"
        )
        assert _revision_advanced_by_one(revision_before, revision_final), (
            f"{adapter.name}: exactly one real schema commit (this final, non-conflicting alter_field) must "
            f"separate the pre-CONFLICT baseline and this result -- observed before={revision_before!r}, "
            f"after={revision_final!r}; a delta other than +1 means the CONFLICT-refused alter_field above "
            "also advanced the revision"
        )
        row_final = _catalog_row(iso, developer, entity)
        assert row_final.get("field_constraints", {}).get(enum_field, {}).get("enum") == ["a", "b", "z"], (
            f"{adapter.name}: the successful alter_field's new enum did not round-trip -- "
            f"{row_final.get('field_constraints')!r}"
        )

        # (8) design v1.5 補正 (監督裁定 A, {scratchpad}/rulings-wp3a-
        # review.md): "a constraint the request omits is left as it is".
        # An `alter_field` that names only `nullable` (re-asserting the
        # field's own CURRENT value, `True` -- already established above
        # -- so no existing row can violate it and no CONFLICT risk is
        # introduced) omits `enum` entirely; the field's enum from the
        # (6)/(7) alter_field just above (`["a", "b", "z"]`) must be left
        # untouched.
        result_omit = iso.schema_operation_with_result(
            developer, entity, "alter_field", field=enum_field, nullable=True,
        )
        assert isinstance(result_omit, dict) and result_omit.get("revision") is not None, (
            f"{adapter.name}: an alter_field omitting 'enum' carries no 'revision' -- {result_omit!r}"
        )
        row_after_omit = _catalog_row(iso, developer, entity)
        assert row_after_omit.get("field_constraints", {}).get(enum_field, {}).get("enum") == ["a", "b", "z"], (
            f"{adapter.name}: an alter_field that omits 'enum' must leave the field's existing enum "
            f"untouched -- {row_after_omit.get('field_constraints')!r}"
        )

        # (9) design v1.5 補正 (同上, 監督裁定 A): "enum: null clears the
        # field's enum" -- an explicit JSON `null`, distinct from omitting
        # the key (leg (8) just above). Port v1.13 追補 (`docs/design/
        # CONFORMANCE_ADAPTER_V1.md` §23.4) adds the `ENUM_CLEAR` sentinel
        # precisely so this call can carry a literal `enum: null` on the
        # wire instead of colliding with leg (8)'s own "omit the key"
        # shape. The field under test (`enum_field`) currently declares
        # `["a", "b", "z"]` (the (6)/(7) alter_field above); clearing it
        # is observed two ways -- the catalog no longer reports an `enum`
        # key for this field at all, and a value outside that old set
        # becomes writable and readable back (the field-level observation
        # this test's own docstring requires, "observed >= 1").
        result_clear = iso.schema_operation_with_result(
            developer, entity, "alter_field", field=enum_field, enum=ENUM_CLEAR,
        )
        assert isinstance(result_clear, dict) and result_clear.get("revision") is not None, (
            f"{adapter.name}: an alter_field clearing 'enum' (enum=ENUM_CLEAR) carries no 'revision' -- "
            f"{result_clear!r}"
        )
        row_after_clear = _catalog_row(iso, developer, entity)
        constraints_after_clear = row_after_clear.get("field_constraints", {}).get(enum_field, {})
        assert "enum" not in constraints_after_clear, (
            f"{adapter.name}: an alter_field with enum: null must clear the field's 'enum' from the "
            f"catalog's field_constraints -- {constraints_after_clear!r}"
        )

        cleared_marker = fresh_identifier("c20cleared")
        iso.attempt_mutation(
            runtime, entity, "insert",
            values={enum_field: "outside-old-enum", nonnull_field: "ok", "label": cleared_marker},
            where_field=None, where_value=None,
        )
        cleared_rows = iso.select_eq(runtime, entity, [enum_field], "label", cleared_marker)
        assert cleared_rows and cleared_rows[0].get(enum_field) == "outside-old-enum", (
            f"{adapter.name}: after enum: null cleared {enum_field!r}'s enum, a value outside the old set "
            f"(['a', 'b', 'z']) must be writable and readable back -- {cleared_rows!r}"
        )

        # (10) 監督裁定 M-6 ({scratchpad}/rulings-wp2a-review.md): an
        # add_field declaring nullable: false on an entity that already
        # holds rows is refused CONFLICT on the same rule alter_field
        # uses -- every existing row would hold null in the new field.
        # `entity` already carries several rows by this point (`marker`,
        # `conflict_marker`, `cleared_marker`, ...) from the legs above.
        # Same revision-bracket style as (6)/(7): a harmless, always-non-
        # conflicting alter_field (`nullable: true` on "label", already
        # that field's own current value) gives a real baseline revision
        # before the CONFLICT attempt, and a second one after gives the
        # "after" value -- exactly one real commit (the second) must
        # separate them, proving the CONFLICT-refused add_field committed
        # none.
        revision_before_addfield = _revision_of(
            iso.schema_operation_with_result(developer, entity, "alter_field", field="label", nullable=True)
        )
        row = _catalog_row(iso, developer, entity)
        constraints_before_addfield = row.get("field_constraints")
        count_before_addfield = iso.count(runtime, entity)
        new_field = fresh_identifier("c20newfield")
        with pytest.raises(ConformanceDenial) as ei_addfield_conflict:
            iso.schema_operation_with_result(
                developer, entity, "add_field", field=new_field, field_type="string", nullable=False,
            )
        assert ei_addfield_conflict.value.code == "CONFLICT", (
            f"{adapter.name}: add_field declaring nullable: false on {entity!r}, which already holds rows, "
            f"-> {ei_addfield_conflict.value.code!r}, expected CONFLICT"
        )
        assert ei_addfield_conflict.value.details.get("violated_declaration") == "nullable", (
            ei_addfield_conflict.value.details
        )
        addfield_conflict_field = ei_addfield_conflict.value.details.get("field")
        assert isinstance(addfield_conflict_field, str) and not addfield_conflict_field.startswith("/"), (
            f"{adapter.name}: details.field {addfield_conflict_field!r} must be a '/'-separated request-body "
            f"path with no leading separator -- {ei_addfield_conflict.value.details!r}"
        )
        row_after_addfield_conflict = _catalog_row(iso, developer, entity)
        assert new_field not in row_after_addfield_conflict["fields"], (
            f"{adapter.name}: a CONFLICT-refused add_field must not add the field -- "
            f"{row_after_addfield_conflict!r}"
        )
        assert row_after_addfield_conflict.get("field_constraints") == constraints_before_addfield, (
            f"{adapter.name}: a CONFLICT-refused add_field must not change the catalog's field_constraints"
        )
        assert iso.count(runtime, entity) == count_before_addfield, (
            f"{adapter.name}: a CONFLICT-refused add_field changed row count"
        )

        result_addfield_bracket = iso.schema_operation_with_result(
            developer, entity, "alter_field", field="label", nullable=True,
        )
        revision_final_addfield = result_addfield_bracket.get("revision")
        assert isinstance(result_addfield_bracket, dict) and revision_final_addfield is not None, (
            f"{adapter.name}: an alter_field's result carries no 'revision' -- {result_addfield_bracket!r}"
        )
        assert _revision_advanced_by_one(revision_before_addfield, revision_final_addfield), (
            f"{adapter.name}: exactly one real schema commit (this final, non-conflicting alter_field) must "
            f"separate the pre-CONFLICT baseline and this result -- observed before="
            f"{revision_before_addfield!r}, after={revision_final_addfield!r}; a delta other than +1 means "
            "the CONFLICT-refused add_field above also advanced the revision"
        )

        # Same add_field, on an entity holding zero rows: no existing row
        # can violate nullable: false, so it succeeds and the catalog
        # reports the declared constraint back.
        empty_entity = fresh_identifier("c20empty")
        iso.create_entity(developer, empty_entity, {"label": "text"})
        result_addfield_ok = iso.schema_operation_with_result(
            developer, empty_entity, "add_field", field=new_field, field_type="string", nullable=False,
        )
        assert isinstance(result_addfield_ok, dict) and result_addfield_ok.get("revision") is not None, (
            f"{adapter.name}: a successful add_field's result carries no 'revision' -- {result_addfield_ok!r}"
        )
        row_empty = _catalog_row(iso, developer, empty_entity)
        assert row_empty.get("field_constraints", {}).get(new_field, {}).get("nullable") is False, (
            f"{adapter.name}: add_field declaring nullable: false on a zero-row entity must succeed and the "
            f"catalog must report nullable: false for the new field -- {row_empty.get('field_constraints')!r}"
        )

        # (11) 監督裁定 m-1 ({scratchpad}/rulings-wp2a-review.md): a
        # declaration-invalid `enum` -- here, one declared on a field
        # whose own declared type admits none, an untyped (`json`) field
        # (the field-type vocabulary's own default, 1.6.0 obligation (1),
        # "A field created without a declared type has type json") -- is
        # refused VALIDATION_FAILED, violated_declaration:
        # constraint_declaration, declared_type: "json", before anything
        # is created, on create_entity and on add_field alike.
        json_field = "payload"
        bad_entity = fresh_identifier("c20decl")
        with pytest.raises(ConformanceDenial) as ei_decl_create:
            iso.schema_operation_with_result(
                developer, bad_entity, "create_entity",
                fields=[json_field], field_constraints={json_field: {"enum": ["a", "b"]}},
            )
        assert ei_decl_create.value.code == "VALIDATION_FAILED", (
            f"{adapter.name}: an enum declared on a json (type-undeclared) field in create_entity -> "
            f"{ei_decl_create.value.code!r}, expected VALIDATION_FAILED"
        )
        assert ei_decl_create.value.details.get("violated_declaration") == "constraint_declaration", (
            ei_decl_create.value.details
        )
        assert ei_decl_create.value.details.get("declared_type") == "json", ei_decl_create.value.details
        decl_create_field = ei_decl_create.value.details.get("field")
        assert isinstance(decl_create_field, str) and not decl_create_field.startswith("/"), (
            ei_decl_create.value.details
        )
        assert bad_entity not in iso.entities(developer), (
            f"{adapter.name}: a create_entity refused for an invalid enum declaration must have zero side "
            f"effects, but {bad_entity!r} exists afterward"
        )

        plain_entity2 = fresh_identifier("c20decl2")
        iso.create_entity(developer, plain_entity2, {"label": "text"})
        bad_field = fresh_identifier("c20declfld")
        with pytest.raises(ConformanceDenial) as ei_decl_addfield:
            iso.schema_operation_with_result(
                developer, plain_entity2, "add_field", field=bad_field, enum=["a", "b"],
            )
        assert ei_decl_addfield.value.code == "VALIDATION_FAILED", (
            f"{adapter.name}: an enum declared on a json (type-undeclared) field in add_field -> "
            f"{ei_decl_addfield.value.code!r}, expected VALIDATION_FAILED"
        )
        assert ei_decl_addfield.value.details.get("violated_declaration") == "constraint_declaration", (
            ei_decl_addfield.value.details
        )
        assert ei_decl_addfield.value.details.get("declared_type") == "json", ei_decl_addfield.value.details
        decl_addfield_field = ei_decl_addfield.value.details.get("field")
        assert isinstance(decl_addfield_field, str) and not decl_addfield_field.startswith("/"), (
            ei_decl_addfield.value.details
        )
        row_decl_addfield = _catalog_row(iso, developer, plain_entity2)
        assert bad_field not in row_decl_addfield["fields"], (
            f"{adapter.name}: an add_field refused for an invalid enum declaration must not add the field -- "
            f"{row_decl_addfield!r}"
        )

        # Same vocabulary word for a declaration that is invalid for a
        # different reason -- an empty enum, and a duplicated enum --
        # regardless of the field's own declared type.
        empty_enum_entity = fresh_identifier("c20declempt")
        with pytest.raises(ConformanceDenial) as ei_empty:
            iso.schema_operation_with_result(
                developer, empty_enum_entity, "create_entity",
                fields=["status"], field_types={"status": "string"},
                field_constraints={"status": {"enum": []}},
            )
        assert ei_empty.value.code == "VALIDATION_FAILED", (
            f"{adapter.name}: an empty enum -> {ei_empty.value.code!r}, expected VALIDATION_FAILED"
        )
        assert ei_empty.value.details.get("violated_declaration") == "constraint_declaration", (
            ei_empty.value.details
        )
        assert empty_enum_entity not in iso.entities(developer), (
            f"{adapter.name}: a create_entity refused for an empty enum must have zero side effects, but "
            f"{empty_enum_entity!r} exists afterward"
        )

        dup_enum_entity = fresh_identifier("c20decldup")
        with pytest.raises(ConformanceDenial) as ei_dup:
            iso.schema_operation_with_result(
                developer, dup_enum_entity, "create_entity",
                fields=["status"], field_types={"status": "string"},
                field_constraints={"status": {"enum": ["a", "a"]}},
            )
        assert ei_dup.value.code == "VALIDATION_FAILED", (
            f"{adapter.name}: a duplicated enum -> {ei_dup.value.code!r}, expected VALIDATION_FAILED"
        )
        assert ei_dup.value.details.get("violated_declaration") == "constraint_declaration", ei_dup.value.details
        assert dup_enum_entity not in iso.entities(developer), (
            f"{adapter.name}: a create_entity refused for a duplicated enum must have zero side effects, but "
            f"{dup_enum_entity!r} exists afterward"
        )

        # (12) 監督裁定 N-1 ({scratchpad}/rulings-r2-closure.md, contract
        # v1.7 補正 on structured_operations.alter_field): an alter_field
        # carrying neither enum nor nullable declares nothing and is
        # refused VALIDATION_FAILED, violated_declaration:
        # constraint_declaration, field: "operation" (a request-internal
        # path -- the missing declaration is a defect of the operation as
        # a whole, not attributable to any one field) -- and does not
        # advance the schema revision. Same revision-bracket style as
        # (6)/(7)/(10): a harmless, always-non-conflicting alter_field
        # (nullable: true on "label", already that field's own current
        # value) gives a real baseline revision before the refused
        # attempt, and a second one after gives the "after" value --
        # exactly one real commit (the second) must separate them,
        # proving the refused bare alter_field committed none.
        revision_before_bare = _revision_of(
            iso.schema_operation_with_result(developer, entity, "alter_field", field="label", nullable=True)
        )
        row = _catalog_row(iso, developer, entity)
        constraints_before_bare = row.get("field_constraints")
        with pytest.raises(ConformanceDenial) as ei_bare:
            iso.schema_operation_with_result(developer, entity, "alter_field", field=enum_field)
        assert ei_bare.value.code == "VALIDATION_FAILED", (
            f"{adapter.name}: an alter_field carrying neither 'enum' nor 'nullable' -> {ei_bare.value.code!r}, "
            "expected VALIDATION_FAILED"
        )
        assert ei_bare.value.details.get("violated_declaration") == "constraint_declaration", (
            ei_bare.value.details
        )
        assert ei_bare.value.details.get("field") == "operation", (
            f"{adapter.name}: a declaration-empty alter_field's details.field must be 'operation' (裁定 N-1) -- "
            f"{ei_bare.value.details!r}"
        )
        row_after_bare = _catalog_row(iso, developer, entity)
        assert row_after_bare.get("field_constraints") == constraints_before_bare, (
            f"{adapter.name}: a refused alter_field must not change the catalog's field_constraints"
        )

        result_bare_bracket = iso.schema_operation_with_result(
            developer, entity, "alter_field", field="label", nullable=True,
        )
        revision_final_bare = result_bare_bracket.get("revision")
        assert isinstance(result_bare_bracket, dict) and revision_final_bare is not None, (
            f"{adapter.name}: an alter_field's result carries no 'revision' -- {result_bare_bracket!r}"
        )
        assert _revision_advanced_by_one(revision_before_bare, revision_final_bare), (
            f"{adapter.name}: exactly one real schema commit (this final, non-conflicting alter_field) must "
            f"separate the pre-refusal baseline and this result -- observed before={revision_before_bare!r}, "
            f"after={revision_final_bare!r}; a delta other than +1 means the refused bare alter_field above "
            "also advanced the revision"
        )

        observed_branch = "enforced"

    expected_branch = _expected_branch_for_status(status)
    assert observed_branch == expected_branch, (
        f"{adapter.name}: constraint_declarations status {status!r} recorded branch {observed_branch!r}, "
        f"expected {expected_branch!r} -- this test's own per-plug non-vacuity requirement"
    )
