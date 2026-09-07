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
existing `enum` untouched (leg (8) below). **Disclosed scope limit (`enum:
null` leg NOT added)**: `alter_field enum: null` clearing the field's enum
is the OTHER half of that same correction, and is NOT tested here --
`conformance-tests/adapter.py`'s `schema_operation_with_result(..., enum:
Sequence[Any] | None = None)` collapses "omit the key" and "send an
explicit JSON null" onto the same Python `None`, so this port cannot
currently make that call carry a literal `enum: null` on the wire without
a tri-state sentinel addition (out of this WP's file scope). See the
comment at leg (9) below for the full disclosure.

**Overlaps C-17** (same declaration-agreement posture, a different
declaration: C-17 fixes mutation-class/addressability/uniqueness, this row
fixes field-level value constraints).
"""
from __future__ import annotations

import pytest

from adapter import ConformanceAdapter, ConformanceDenial, SurfaceAbsent, fresh_identifier
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
    schema operation (`r2db-api/src/r2db_api/structured.py:1583`
    `self.schema_revision += 1`; `MitateDB-api/src/mitatedb_api/
    backend_sqlite.py:207`/`:250` `self._schema_revision += 1`; the
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

        # (9) design v1.5 補正 (同上): "enum: null clears the field's
        # enum" -- an explicit JSON `null`, distinct from omitting the
        # key (leg (8) just above). NOT ADDED HERE (disclosed scope
        # limit, see this module's docstring): `conformance-tests/
        # adapter.py`'s `schema_operation_with_result(..., enum: Sequence
        # [Any] | None = None)` collapses "omit the key" and "send an
        # explicit null" onto the same Python `None` -- its body
        # construction is `if enum is not None: body["enum"] = list(
        # enum)`, so there is no way to make this call carry a literal
        # `enum: null` on the wire without adding a tri-state sentinel to
        # the port (the same shape `VALID_CONFIRMATION` already uses for
        # `confirmation`). That port change is out of this WP's file
        # scope (`conformance-tests/adapter.py` is not one of the files
        # this WP may touch); adding a leg that calls `enum=None` here
        # would be indistinguishable from leg (8) and would silently
        # assert nothing new (C-20's own non-vacuity requirement, this
        # module's docstring). Left as an explicit gap for the supervisor
        # to close (a small port addition, or an explicit scope grant),
        # not silently worked around.
        observed_branch = "enforced"

    expected_branch = _expected_branch_for_status(status)
    assert observed_branch == expected_branch, (
        f"{adapter.name}: constraint_declarations status {status!r} recorded branch {observed_branch!r}, "
        f"expected {expected_branch!r} -- this test's own per-plug non-vacuity requirement"
    )
