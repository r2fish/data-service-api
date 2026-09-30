"""Phase 9 WP-3c (design docs/design/
PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md D-5, 追補 2
S-a/S-b/S-f; 監督裁定集約 {scratchpad}/rulings-r5-r6.md I-1..I-13): local,
peer-side pinning for `idempotency` -- record read/write position, digest
rule, CONFLICT/LIMIT_EXCEEDED shape, Application scope, dry_run non-
participation, schema-operation coverage, and the plan-digest inclusion
rule (I-13). The conformance suite's own `test_c23_idempotency_semantics.
py` is the cross-peer evidence; this file pins peer-local mechanics
(record-count observation, retention-window manipulation) that suite
cannot reach without a real clock wait.
"""
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from mitatedb_api import ControlPlane, FoundationConfig, MitateDataService, Role
from mitatedb_api.cell import compute_plan_token, idempotency_digest, normalize_request_for_idempotency
from mitatedb_api.errors import ConflictError, PreconditionFailedError, ResourceLimitError, ValidationError


class IdempotencyRecordsTests(unittest.TestCase):
    def setUp(self):
        self.control = ControlPlane("synthetic-test-pepper-0123456789")
        self.control.provision_application("app_a")
        self.dev_id, self.dev_secret = self.control.issue_credential("app_a", Role.DEVELOPER)
        self.runtime_id, self.runtime_secret = self.control.issue_credential("app_a", Role.RUNTIME)
        self.other_runtime_id, self.other_runtime_secret = self.control.issue_credential("app_a", Role.RUNTIME)
        self.service = MitateDataService(self.control)
        self.dev = self.service.open_session(self.dev_secret)
        self.runtime = self.service.open_session(self.runtime_secret)
        self.dev.create_collection("notes", {"title": "text"})

    # -- I-3/I-8: same key + same body replays the original result -------

    def test_same_key_same_body_replays_and_writes_one_row(self):
        key = "idem-key-1"
        first = self.runtime.transact(
            [{"type": "insert", "collection": "notes", "values": {"title": "a"}, "idempotency_key": key}])
        second = self.runtime.transact(
            [{"type": "insert", "collection": "notes", "values": {"title": "a"}, "idempotency_key": key}])
        self.assertEqual(first, second)
        self.assertEqual(len(self.runtime.read("notes")), 1)

    # -- I-4: same key, different body -> CONFLICT ------------------------

    def test_same_key_different_body_is_conflict(self):
        key = "idem-key-2"
        self.runtime.transact(
            [{"type": "insert", "collection": "notes", "values": {"title": "a"}, "idempotency_key": key}])
        with self.assertRaises(ConflictError) as ctx:
            self.runtime.transact(
                [{"type": "insert", "collection": "notes", "values": {"title": "b"}, "idempotency_key": key}])
        self.assertEqual(ctx.exception.details["violated_declaration"], "idempotency_key")
        self.assertEqual(ctx.exception.details["field"], "idempotency_key")
        # The CONFLICT-refused body must not have been written.
        self.assertEqual(len(self.runtime.read("notes")), 1)

    # -- I-1: a failed attempt leaves no record ---------------------------

    def test_failed_attempt_leaves_no_record_and_resend_executes(self):
        key = "idem-key-3"
        with self.assertRaises(ValidationError):
            self.runtime.transact([
                {"type": "insert", "collection": "notes", "values": {"title": "ok"}, "idempotency_key": key},
                {"type": "insert", "collection": "notes", "values": {"no_such_field": "x"}, "idempotency_key": key},
            ])
        self.assertEqual(self.runtime.read("notes"), [])
        retried = self.runtime.transact(
            [{"type": "insert", "collection": "notes", "values": {"title": "ok"}, "idempotency_key": key}])
        self.assertEqual(len(retried), 1)
        self.assertEqual(len(self.runtime.read("notes")), 1)

    # -- I-1: a failure AFTER `begin()` (validation/target-existence/
    # confirmation already passed, a real backend write already applied)
    # leaves no record either -- the test above only reaches a PASS-1
    # (`_plan_operation`) validation failure, which never calls `begin()`
    # at all (`transact`'s own two-pass docstring), so it cannot by
    # itself distinguish "record written in the SAME transaction as the
    # data" from "record written independently" -- this one can, using
    # the ONE other documented failure mode that reaches past `begin()`:
    # a destructive delete's own pre-commit audit hook raising
    # `AuditSinkUnavailable` (`cell.py`'s own "the idempotency record is
    # written as the LAST thing before this backend's own commit"
    # comment, `transact`).

    def test_execution_time_failure_after_begin_leaves_no_record(self):
        from mitatedb_api import Filter
        from mitatedb_api.application_audit import ApplicationAuditSink
        from mitatedb_api.audit_dispatch import AuditRouter
        from mitatedb_api.auth import Principal
        from mitatedb_api.cell import (ApplicationCell, ApplicationDeveloper, ApplicationRuntime,
                                       _delete_confirmation_phrase)
        from mitatedb_api.errors import AuditSinkUnavailable

        sink = ApplicationAuditSink()
        router = AuditRouter(sink)
        cell = ApplicationCell("app_audit_i1", FoundationConfig(), audit_router=router)
        dev = ApplicationDeveloper(
            cell, Principal(application_id="app_audit_i1", credential_id="devone", role=Role.DEVELOPER))
        runtime = ApplicationRuntime(
            cell, Principal(application_id="app_audit_i1", credential_id="rtone", role=Role.RUNTIME))
        dev.create_collection("things", {"id": "integer"})
        runtime.transact([{"type": "insert", "collection": "things", "values": {"id": 1}}])

        sink.inject_fault(RuntimeError("sink down"))
        revision = cell._backend.schema_revision()
        phrase = _delete_confirmation_phrase("things", [Filter("id", "eq", 1)], revision)
        key = "idem-audit-fail"
        delete_op = {"type": "delete", "collection": "things", "destructive": True, "confirm": phrase,
                     "filters": [Filter("id", "eq", 1)], "idempotency_key": key}
        with self.assertRaises(AuditSinkUnavailable):
            runtime.transact([delete_op])
        # A read writes its own event before it answers, so the sink is
        # healthy again before the row count is read back.
        sink.inject_fault(None)
        # The backend write (`delete_in_transaction`) already ran, on the
        # SAME connection/transaction the failed pre-commit hook aborted
        # -- rolled back together, so the row is still there...
        self.assertEqual(len(runtime.read("things")), 1)
        # ...and so is the key: a retry is a FRESH request, not a CONFLICT
        # (which is what a leaked, independently-durable record from the
        # failed attempt would have produced here, since a delete's own
        # confirmation phrase is revision-bound and this retry reuses the
        # unchanged `revision`/`phrase` -- same digest as the failed
        # attempt).
        sink.inject_fault(None)
        retried = runtime.transact([delete_op])
        self.assertEqual(len(retried), 1)
        self.assertEqual(len(runtime.read("things")), 0)

    # -- I-5: Application scope, not credential scope ---------------------

    def test_key_scope_is_application_not_credential(self):
        other_runtime = self.service.open_session(self.other_runtime_secret)
        key = "idem-key-4"
        first = self.runtime.transact(
            [{"type": "insert", "collection": "notes", "values": {"title": "cross"}, "idempotency_key": key}])
        second = other_runtime.transact(
            [{"type": "insert", "collection": "notes", "values": {"title": "cross"}, "idempotency_key": key}])
        self.assertEqual(first, second)
        self.assertEqual(len(self.runtime.read("notes")), 1)

    # -- I-6: capacity is checked at the lookup stage, before execution ---

    def test_capacity_refuses_before_execution_and_writes_nothing(self):
        control = ControlPlane("synthetic-test-pepper-0123456789", config=FoundationConfig(idempotency_entries=1))
        control.provision_application("app_cap")
        _dev_id, dev_secret = control.issue_credential("app_cap", Role.DEVELOPER)
        _rt_id, rt_secret = control.issue_credential("app_cap", Role.RUNTIME)
        service = MitateDataService(control)
        dev = service.open_session(dev_secret)
        runtime = service.open_session(rt_secret)
        dev.create_collection("notes", {"title": "text"})
        runtime.transact(
            [{"type": "insert", "collection": "notes", "values": {"title": "a"}, "idempotency_key": "cap-1"}])
        with self.assertRaises(ResourceLimitError) as ctx:
            runtime.transact(
                [{"type": "insert", "collection": "notes", "values": {"title": "b"}, "idempotency_key": "cap-2"}])
        self.assertEqual(ctx.exception.details["limit_class"], "idempotency_entries")
        # The refused request must not have executed.
        self.assertEqual(len(runtime.read("notes")), 1)

    def test_capacity_refusal_never_attempts_the_backend_write(self):
        """I-6 (満杯 = 照会段で実行前, "実行してから rollback しない"): the
        test above alone cannot distinguish "refused before ANY backend
        write is attempted" from "refused after a write, then correctly
        rolled back" -- both leave the SAME final row count. This one
        counts the actual `insert_in_transaction` calls (the same
        wrap-and-count technique `test_foundation.py`'s own two-pass
        pinning test uses) to confirm the refusal happens strictly at the
        lookup stage, with zero backend write attempts."""
        control = ControlPlane("synthetic-test-pepper-0123456789", config=FoundationConfig(idempotency_entries=1))
        control.provision_application("app_cap2")
        _dev_id, dev_secret = control.issue_credential("app_cap2", Role.DEVELOPER)
        _rt_id, rt_secret = control.issue_credential("app_cap2", Role.RUNTIME)
        service = MitateDataService(control)
        dev = service.open_session(dev_secret)
        runtime = service.open_session(rt_secret)
        dev.create_collection("notes", {"title": "text"})
        runtime.transact(
            [{"type": "insert", "collection": "notes", "values": {"title": "a"}, "idempotency_key": "cap2-1"}])

        cell = control.cells["app_cap2"]
        backend = cell._backend
        calls = {"insert_in_transaction": 0}
        real_insert = backend.insert_in_transaction

        def counting_insert(collection, fields, params):
            calls["insert_in_transaction"] += 1
            return real_insert(collection, fields, params)

        backend.insert_in_transaction = counting_insert
        try:
            with self.assertRaises(ResourceLimitError) as ctx:
                runtime.transact(
                    [{"type": "insert", "collection": "notes", "values": {"title": "b"}, "idempotency_key": "cap2-2"}])
            self.assertEqual(ctx.exception.details["limit_class"], "idempotency_entries")
        finally:
            backend.insert_in_transaction = real_insert
        self.assertEqual(calls["insert_in_transaction"], 0)

    # -- I-7: dry_run never records or consults an idempotency record -----

    def test_dry_run_does_not_record_or_consult(self):
        key = "idem-key-dry"
        self.runtime.transact(
            [{"type": "insert", "collection": "notes", "values": {"title": "dry"}, "idempotency_key": key}],
            dry_run=True)
        # A dry run rolled back -- nothing written, and the SAME key is
        # still usable for a REAL, different-shaped request afterward
        # (proving the dry run never recorded it).
        self.assertEqual(self.runtime.read("notes"), [])
        real = self.runtime.transact(
            [{"type": "insert", "collection": "notes", "values": {"title": "real"}, "idempotency_key": key}])
        self.assertEqual(len(real), 1)
        self.assertEqual(len(self.runtime.read("notes")), 1)

    # -- I-9: SchemaOperationRequest (add_field) idempotency --------------

    def test_schema_add_field_replays_and_conflicts(self):
        key = "idem-schema-1"
        first = self.dev.add_field("notes", "rank", "integer", idempotency_key=key)
        second = self.dev.add_field("notes", "rank", "integer", idempotency_key=key)
        self.assertEqual(first["revision"], second["revision"])
        self.assertEqual(first["descriptor"], second["descriptor"])
        with self.assertRaises(ConflictError) as ctx:
            self.dev.add_field("notes", "other", "text", idempotency_key=key)
        self.assertEqual(ctx.exception.details["violated_declaration"], "idempotency_key")
        # Only ONE add_field actually landed (a second add_field of the
        # SAME field name would have raised ConflictError for a real,
        # different reason -- confirmed here by reading the catalog).
        notes_types = self._field_types("notes")
        self.assertIn("rank", notes_types)
        self.assertNotIn("other", notes_types)

    def _field_types(self, entity):
        return next(e for e in self.dev.catalog() if e["entity"] == entity)["field_types"]

    def test_schema_create_entity_replays(self):
        key = "idem-schema-2"
        first = self.dev.create_entity("widgets", {"label": "text"}, idempotency_key=key)
        second = self.dev.create_entity("widgets", {"label": "text"}, idempotency_key=key)
        self.assertEqual(first, second)

    def test_schema_failed_attempt_leaves_no_record(self):
        key = "idem-schema-fail"
        with self.assertRaises(ValidationError):
            self.dev.add_field("notes", "bad", "not-a-real-type", idempotency_key=key)
        # The field was never created.
        self.assertNotIn("bad", self._field_types("notes"))
        retried = self.dev.add_field("notes", "bad", "text", idempotency_key=key)
        self.assertIsNotNone(retried["revision"])
        self.assertIn("bad", self._field_types("notes"))

    # -- I-11: the key is never written to an audit row --------------------

    def test_key_never_reaches_audit_row(self):
        from mitatedb_api.audit import AuditSink

        class _Capturing(AuditSink):
            def __init__(self):
                self.rows = []

            def record(self, event, application_id, credential_id, detail=None):
                self.rows.append((event, application_id, credential_id, detail))

        sink = _Capturing()
        control = ControlPlane("synthetic-test-pepper-0123456789", audit=sink)
        control.provision_application("app_audit")
        _dev_id, dev_secret = control.issue_credential("app_audit", Role.DEVELOPER)
        _rt_id, rt_secret = control.issue_credential("app_audit", Role.RUNTIME)
        service = MitateDataService(control)
        dev = service.open_session(dev_secret)
        runtime = service.open_session(rt_secret)
        dev.create_collection("notes", {"title": "text"})
        secret_key = "SUPER-SECRET-IDEMPOTENCY-KEY"
        runtime.transact(
            [{"type": "insert", "collection": "notes", "values": {"title": "a"}, "idempotency_key": secret_key}])
        for _event, _app, _cred, detail in sink.rows:
            self.assertNotEqual(detail, secret_key)
            self.assertNotIn(secret_key, str(detail))

    # -- I-3: the lookup runs before target-existence/confirmation are
    # (re-)evaluated -- a replay must answer from the record even when
    # the ORIGINAL confirmation phrase is no longer valid against the
    # CURRENT schema revision. `test_same_key_same_body_replays_and_
    # writes_one_row` above cannot distinguish "answered from the record,
    # unconditionally" from "answered because confirmation happened to
    # still be valid too" -- this test forces the two apart by bumping
    # the schema revision (an unrelated `add_field`) between the first,
    # confirmed delete and the identical resend, so a resend that
    # RE-EVALUATES confirmation (instead of answering from the record
    # first, I-3) would recompute a DIFFERENT `required_confirmation`
    # phrase than the stale one this resend still carries, and be
    # refused `DESTRUCTIVE_CONFIRMATION_REQUIRED`.

    def test_replay_of_a_confirmed_delete_bypasses_reconfirmation(self):
        from mitatedb_api import Filter
        from mitatedb_api.cell import _delete_confirmation_phrase

        self.dev.create_collection("widgets", {"id": "integer"})
        self.runtime.transact([{"type": "insert", "collection": "widgets", "values": {"id": 1}}])
        revision = self.runtime.schema_revision()
        phrase = _delete_confirmation_phrase("widgets", [Filter("id", "eq", 1)], revision)
        key = "idem-delete-reconfirm"
        delete_op = {"type": "delete", "collection": "widgets", "destructive": True, "confirm": phrase,
                     "filters": [Filter("id", "eq", 1)], "idempotency_key": key}
        first = self.runtime.transact([delete_op])
        self.assertEqual(len(self.runtime.read("widgets")), 0)
        # An unrelated schema change bumps the revision -- the ORIGINAL
        # `phrase` above is now stale: a FRESH (non-replay) delete built
        # against it would be refused `DESTRUCTIVE_CONFIRMATION_REQUIRED`.
        self.dev.add_field("widgets", "note", "text")
        self.assertNotEqual(self.runtime.schema_revision(), revision)
        # The identical resend -- SAME stale `confirm`, SAME key -- must
        # still succeed, replaying the original result, because the
        # idempotency lookup answers it before confirmation is ever
        # re-evaluated against the now-different revision.
        second = self.runtime.transact([delete_op])
        self.assertEqual(first, second)

    # -- F-② (外部レビュー 2, scratchpad/review2/frame.md, 監督裁定 U-11):
    # `budget` is part of what a resend must match (契約 1.7.0
    # `idempotency.record`, "every other field, including budget,
    # transaction and confirmation, is part of what a resend must
    # match") -- an omitted `budget` and a present-but-empty `budget: {}`
    # are two DIFFERENT requests, exactly like r2db's own `plan_request`
    # (`if budget is not None:`, `r2db-api/src/r2db_api/service.py:1237`).
    # Before this fix, `cell.py::transact`'s own `digest_request`
    # construction used `if budget:` (truthy), which drops an empty-but-
    # PRESENT `budget: {}` from the digest exactly as if it had been
    # omitted -- a resend adding `budget: {}` to an omitted-budget
    # original was wrongly answered as a REPLAY instead of refused
    # CONFLICT.

    def test_omitted_budget_then_resend_with_empty_budget_is_conflict_not_replay(self):
        key = "idem-budget-shape-1"
        first = self.runtime.transact(
            [{"type": "insert", "collection": "notes", "values": {"title": "no-budget"}, "idempotency_key": key}])
        with self.assertRaises(ConflictError) as ctx:
            self.runtime.transact(
                [{"type": "insert", "collection": "notes", "values": {"title": "no-budget"}, "idempotency_key": key}],
                budget={})
        self.assertEqual(ctx.exception.details["violated_declaration"], "idempotency_key")
        self.assertEqual(ctx.exception.details["field"], "idempotency_key")
        # The CONFLICT-refused resend must not have executed a second time.
        self.assertEqual(len(self.runtime.read("notes")), 1)
        self.assertEqual(len(first), 1)

    def test_plan_digest_differs_between_omitted_and_empty_budget(self):
        body = [{"type": "insert", "collection": "notes", "values": {"title": "budget-plan"}}]
        plan_omitted = self.runtime.transact(body, dry_run=True)[-1]["plan"]
        plan_empty = self.runtime.transact(body, dry_run=True, budget={})[-1]["plan"]
        self.assertNotEqual(
            plan_omitted, plan_empty,
            "an omitted budget and an empty-but-present budget: {} must produce different plan digests",
        )

    # -- F-② extended to the three schema-operation digest sites
    # (`create_collection`/`create_entity`, `add_field`, `alter_field`):
    # each receives `budget` for limit narrowing (see `_gate(...,
    # budget=...)`) but, before this fix, never folded it into its OWN
    # `digest_request` -- only the HTTP layer's `digest_extra` carried it
    # (`http.py`'s schema-operation dispatch, ~:1260). A direct,
    # in-process caller (bypassing HTTP, exactly like every other test in
    # this class) proves the cell-level digest itself now covers
    # `budget`, not merely that HTTP happens to inject it separately.

    def test_schema_create_entity_omitted_budget_then_resend_with_empty_budget_is_conflict(self):
        key = "idem-schema-budget-shape-1"
        first = self.dev.create_entity("budget_shape_widgets", {"label": "text"}, idempotency_key=key)
        with self.assertRaises(ConflictError) as ctx:
            self.dev.create_entity("budget_shape_widgets", {"label": "text"}, idempotency_key=key, budget={})
        self.assertEqual(ctx.exception.details["violated_declaration"], "idempotency_key")
        # The CONFLICT-refused resend must not have executed a second
        # time (a second real create_entity of the SAME name would raise
        # ConflictError for a different reason -- confirmed by revision).
        self.assertIsNotNone(first["revision"])
        self.assertEqual(
            len([e for e in self.dev.catalog() if e["entity"] == "budget_shape_widgets"]), 1,
        )

    def test_schema_create_entity_plan_digest_differs_between_omitted_and_empty_budget(self):
        plan_omitted = self.dev.create_entity("budget_shape_plan_widgets", {"label": "text"}, dry_run=True)["plan"]
        plan_empty = self.dev.create_entity(
            "budget_shape_plan_widgets", {"label": "text"}, dry_run=True, budget={})["plan"]
        self.assertNotEqual(
            plan_omitted, plan_empty,
            "an omitted budget and an empty-but-present budget: {} must produce different plan digests",
        )

    def test_schema_add_field_omitted_budget_then_resend_with_empty_budget_is_conflict(self):
        key = "idem-schema-budget-shape-2"
        first = self.dev.add_field("notes", "budget_shape_field", "integer", idempotency_key=key)
        with self.assertRaises(ConflictError) as ctx:
            self.dev.add_field("notes", "budget_shape_field", "integer", idempotency_key=key, budget={})
        self.assertEqual(ctx.exception.details["violated_declaration"], "idempotency_key")
        self.assertIsNotNone(first["revision"])
        self.assertIn("budget_shape_field", self._field_types("notes"))

    def test_schema_alter_field_omitted_budget_then_resend_with_empty_budget_is_conflict(self):
        key = "idem-schema-budget-shape-3"
        first = self.dev.alter_field("notes", "title", nullable=True, idempotency_key=key)
        with self.assertRaises(ConflictError) as ctx:
            self.dev.alter_field("notes", "title", nullable=True, idempotency_key=key, budget={})
        self.assertEqual(ctx.exception.details["violated_declaration"], "idempotency_key")
        self.assertIsNotNone(first["revision"])

    # -- J-1/I-13: the plan-digest inclusion rule, through the REAL entry
    # point -- `test_idempotency_key_is_part_of_the_plan_digest`
    # (`IdempotencyDigestTests` below) only proves the digest RULE in
    # isolation (a hand-built dict passed straight to `compute_plan_
    # token`); it never exercises `ApplicationCell.transact`'s/`create_
    # collection`'s own real wiring. WP-3cd audit (§11 必須 1, N-1):
    # deleting the `if idempotency_key is not None: digest_request
    # ["idempotency_key"] = idempotency_key` line inside `transact` left
    # EVERY existing test green (`MitateDB-api/tests` and conformance
    # alike) -- these two tests close that gap by driving the same real
    # entry points production traffic uses.

    def test_plan_digest_wiring_through_real_transact_path(self):
        body = [{"type": "insert", "collection": "notes", "values": {"title": "j1"}}]
        plan_without_key = self.runtime.transact(body, dry_run=True)[-1]["plan"]
        plan_with_key = self.runtime.transact(body, dry_run=True, idempotency_key="j1-key")[-1]["plan"]
        self.assertNotEqual(plan_without_key, plan_with_key)
        # A plan taken from a KEYED dry run, presented to a KEYLESS apply
        # of the identical body, must be refused PRECONDITION_FAILED --
        # proving `idempotency_key` really is part of what the token
        # commits to (not merely that the two tokens above happen to
        # differ for some OTHER reason).
        with self.assertRaises(PreconditionFailedError) as ctx:
            self.runtime.transact(body, plan=plan_with_key)
        self.assertEqual(ctx.exception.details["violated_declaration"], "plan")
        self.assertEqual(self.runtime.read("notes"), [])

    def test_schema_plan_digest_wiring_through_real_create_entity_path(self):
        plan_without_key = self.dev.create_entity("j1_widgets", {"label": "text"}, dry_run=True)["plan"]
        plan_with_key = self.dev.create_entity(
            "j1_widgets", {"label": "text"}, dry_run=True, idempotency_key="j1-schema-key")["plan"]
        self.assertNotEqual(plan_without_key, plan_with_key)
        with self.assertRaises(PreconditionFailedError) as ctx:
            self.dev.create_entity("j1_widgets", {"label": "text"}, plan=plan_with_key)
        self.assertEqual(ctx.exception.details["violated_declaration"], "plan")
        self.assertNotIn("j1_widgets", [e["entity"] for e in self.dev.catalog()])

    # -- J-4/SI-14: a replay earns its own durable audit row ---------------

    def test_replayed_destructive_delete_writes_exactly_one_audit_row(self):
        """WP-3cd audit §11 必須 2 (N-5; 監督裁定集約 rulings-r5-r6.md J-4/
        SI-14): before this fix, `cell.py`'s 4 replay branches `return
        replay` immediately, reaching neither the pre-commit audit hook
        nor `self.__record(...)` -- a confirmed destructive delete's own
        resend returned `committed: true` while leaving zero durable
        evidence this Application was touched. Drives the real
        `ApplicationCell.transact` idempotency-replay path with a fresh,
        private `AuditRouter` and counts durable rows before/after,
        mirroring r2db-api's own equivalent test one-for-one."""
        from mitatedb_api import Filter
        from mitatedb_api.application_audit import ApplicationAuditSink
        from mitatedb_api.audit_dispatch import AuditRouter
        from mitatedb_api.auth import Principal
        from mitatedb_api.cell import (ApplicationCell, ApplicationDeveloper, ApplicationRuntime,
                                       _delete_confirmation_phrase)

        sink = ApplicationAuditSink()
        router = AuditRouter(sink)
        cell = ApplicationCell("app_j4", FoundationConfig(), audit_router=router)
        dev = ApplicationDeveloper(
            cell, Principal(application_id="app_j4", credential_id="devj4", role=Role.DEVELOPER))
        runtime = ApplicationRuntime(
            cell, Principal(application_id="app_j4", credential_id="rtj4", role=Role.RUNTIME))
        dev.create_collection("widgets", {"id": "integer"})
        runtime.transact([{"type": "insert", "collection": "widgets", "values": {"id": 1}}])
        revision = runtime.schema_revision()
        phrase = _delete_confirmation_phrase("widgets", [Filter("id", "eq", 1)], revision)
        key = "idem-j4-replay"
        delete_op = {"type": "delete", "collection": "widgets", "destructive": True, "confirm": phrase,
                     "filters": [Filter("id", "eq", 1)], "idempotency_key": key}

        first = runtime.transact([delete_op], request_id="rid-original")
        before = len(sink.events())

        second = runtime.transact([delete_op], request_id="rid-replay")
        after = sink.events()
        self.assertEqual(len(after), before + 1, "the destructive replay must add EXACTLY one durable audit row")
        self.assertEqual(first, second)

        new_rows = [e for e in after if e.request_id == "rid-replay"]
        self.assertEqual(len(new_rows), 1)
        row = new_rows[0]
        self.assertEqual(row.outcome, "replayed")
        self.assertEqual(row.operation, "transact")
        # I-11: the key never appears in the durable row, in any field.
        self.assertNotIn(key, repr(row))

    def test_replayed_schema_operation_writes_exactly_one_audit_row(self):
        """J-4/SI-14, schema side: `create_collection`'s own replay
        branch."""
        from mitatedb_api.application_audit import ApplicationAuditSink
        from mitatedb_api.audit_dispatch import AuditRouter
        from mitatedb_api.auth import Principal
        from mitatedb_api.cell import ApplicationCell, ApplicationDeveloper, ApplicationRuntime

        sink = ApplicationAuditSink()
        router = AuditRouter(sink)
        cell = ApplicationCell("app_j4s", FoundationConfig(), audit_router=router)
        dev = ApplicationDeveloper(
            cell, Principal(application_id="app_j4s", credential_id="devj4s", role=Role.DEVELOPER))
        key = "idem-j4-schema-replay"

        first = dev.create_entity("widgets", {"label": "text"}, idempotency_key=key, request_id="rid-s-original")
        before = len(sink.events())

        second = dev.create_entity("widgets", {"label": "text"}, idempotency_key=key, request_id="rid-s-replay")
        after = sink.events()
        self.assertEqual(len(after), before + 1, "the schema replay must add EXACTLY one durable audit row")
        self.assertEqual(first, second)

        new_rows = [e for e in after if e.request_id == "rid-s-replay"]
        self.assertEqual(len(new_rows), 1)
        row = new_rows[0]
        self.assertEqual(row.outcome, "replayed")
        self.assertEqual(row.operation, "create_collection")
        self.assertNotIn(key, repr(row))

    # -- K-4 (WP-3cd audit §11 推奨 5/6/7): 3 "空振り" mutations the audit
    # measured as all-green -- each of the 3 tests below is designed to
    # go red under exactly the mutation its own docstring names.

    def test_record_write_failure_leaves_no_committed_data(self):
        """K-4 item 1 (推奨 5, I-1/SI-11): proves the idempotency record
        write and the batch's own data commit are the SAME atomic unit --
        a failure of the RECORD write itself must leave NO committed data
        behind, exactly as it would if the record write happens strictly
        BEFORE `self._backend.commit()` (the real, current code order --
        `cell.py::transact`'s own "the idempotency record is written as
        the LAST thing before this backend's own commit" comment). If the
        record write were instead moved to a SEPARATE step AFTER `commit
        ()` (the audit's own "記録を commit 後の別 tx に移す" mutation),
        this SAME injected fault would fire AFTER the insert had already
        durably committed, and `runtime.read(...)` below would see the
        row despite the raised exception -- `self._backend.rollback()` on
        an already-committed SQLite connection is a no-op, it does not
        retroactively undo a commit that already happened."""
        control = ControlPlane("synthetic-test-pepper-0123456789")
        control.provision_application("app_k4a")
        _dev_id, dev_secret = control.issue_credential("app_k4a", Role.DEVELOPER)
        _rt_id, rt_secret = control.issue_credential("app_k4a", Role.RUNTIME)
        service = MitateDataService(control)
        dev = service.open_session(dev_secret)
        runtime = service.open_session(rt_secret)
        dev.create_collection("notes", {"title": "text"})

        cell = control.cells["app_k4a"]
        backend = cell._backend
        real_record = backend.record_idempotency

        def failing_record(*args, **kwargs):
            raise RuntimeError("simulated record-write failure")

        backend.record_idempotency = failing_record
        try:
            with self.assertRaises(RuntimeError):
                runtime.transact(
                    [{"type": "insert", "collection": "notes", "values": {"title": "k4a"},
                      "idempotency_key": "k4a-key"}])
        finally:
            backend.record_idempotency = real_record
        self.assertEqual(runtime.read("notes"), [])

    def test_expired_records_are_reaped_before_capacity_is_checked(self):
        """K-4 item 2 (推奨 6, I-6): proves `_idempotency_check` reclaims
        elapsed records BEFORE testing capacity -- with `idempotency_
        entries=1`/`idempotency_retention_ms=1`, a SECOND, DIFFERENT key
        presented after the first key's record has elapsed must succeed
        (the reap frees the sole slot), not raise LIMIT_EXCEEDED. If
        `self._backend.idempotency_reap_expired(...)` were skipped (the
        audit's own "retention 回収を除く" mutation, a bare `pass`), the
        elapsed-but-still-PRESENT record would still count against
        capacity and this would raise instead."""
        control = ControlPlane(
            "synthetic-test-pepper-0123456789",
            config=FoundationConfig(idempotency_entries=1, idempotency_retention_ms=1))
        control.provision_application("app_k4b")
        _dev_id, dev_secret = control.issue_credential("app_k4b", Role.DEVELOPER)
        _rt_id, rt_secret = control.issue_credential("app_k4b", Role.RUNTIME)
        service = MitateDataService(control)
        dev = service.open_session(dev_secret)
        runtime = service.open_session(rt_secret)
        dev.create_collection("notes", {"title": "text"})

        runtime.transact(
            [{"type": "insert", "collection": "notes", "values": {"title": "a"}, "idempotency_key": "k4b-1"}])
        time.sleep(0.05)  # comfortably past the 1ms retention window
        result = runtime.transact(
            [{"type": "insert", "collection": "notes", "values": {"title": "b"}, "idempotency_key": "k4b-2"}])
        self.assertEqual(len(result), 1)
        self.assertEqual(len(runtime.read("notes")), 2)

    # -- K-5 (N-8): the in-memory backend's own transact exception path
    # discards a pending idempotency record too --------------------------

    def test_transact_commit_failure_after_record_write_discards_the_pending_record(self):
        """K-5 (監督裁定集約 rulings-r5-r6.md, N-8): `backend_sqlite.
        SQLiteBackend`'s 3 DDL methods (`create_collection`/`add_field`/
        `alter_field_constraints`) each pop their own tentative `self.
        _idempotency` entry in their own `except Exception:` block, but
        `cell.py::transact`'s `except Exception:` had no equivalent --
        `record_idempotency` writes to that SAME private, NON-
        transactional dict, so a `self._backend.commit()` failure
        IMMEDIATELY AFTER a successful `record_idempotency` left a
        phantom, durable-looking record behind for data that `self.
        rollback()` actually discarded. Left unfixed, a resend under the
        SAME key would be wrongly answered from that phantom record
        (I-3/I-8's own "resend answers from the record") instead of
        executing fresh -- observably, `runtime.read("notes")` would stay
        empty forever, even after a resend that reports `committed` (via
        replay)."""
        control = ControlPlane("synthetic-test-pepper-0123456789")
        control.provision_application("app_k5")
        _dev_id, dev_secret = control.issue_credential("app_k5", Role.DEVELOPER)
        _rt_id, rt_secret = control.issue_credential("app_k5", Role.RUNTIME)
        service = MitateDataService(control)
        dev = service.open_session(dev_secret)
        runtime = service.open_session(rt_secret)
        dev.create_collection("notes", {"title": "text"})

        cell = control.cells["app_k5"]
        backend = cell._backend
        real_commit = backend.commit

        def failing_commit():
            raise RuntimeError("simulated commit failure")

        backend.commit = failing_commit
        try:
            from mitatedb_api.errors import AuditSinkUnavailable
            # the batch's `allow` row is already durable when the commit
            # fails, so the failure surfaces as the audit sink's own (the
            # `error` row is written for the same request)
            with self.assertRaises(AuditSinkUnavailable):
                runtime.transact(
                    [{"type": "insert", "collection": "notes", "values": {"title": "k5"},
                      "idempotency_key": "k5-key"}])
        finally:
            backend.commit = real_commit
        self.assertEqual(runtime.read("notes"), [])

        # The key must be usable again -- a retry under the SAME key must
        # execute FRESH (a real second attempt), not be answered from a
        # leaked phantom record.
        retried = runtime.transact(
            [{"type": "insert", "collection": "notes", "values": {"title": "k5"}, "idempotency_key": "k5-key"}])
        self.assertEqual(len(retried), 1)
        self.assertEqual(len(runtime.read("notes")), 1)


def test_declared_audit_outcomes_include_replayed():
    """J-4 (WP-2cd/WP-3cd audit N-5): the peer-local `outcome` vocabulary
    pin (`application_audit.py`'s `DECLARED_AUDIT_OUTCOMES`) includes
    `"replayed"` -- fixed against every real `outcome=`/`"outcome":`
    literal the DURABLE application-audit trail's own dispatch module
    (`audit_dispatch.py` -- the ONLY module that ever calls `Application
    AuditSink.append`, through `.write_event`/`.write_replayed_fail_closed_
    event`) constructs, using the SAME generalized AST scanner `test_
    audit_query.py`'s own `DECLARED_AUDIT_OPERATIONS`/`_TARGET_KINDS`/
    `_EVENT_CLASSES` tests use -- restricted to THIS one file, not
    `src/mitatedb_api/` as a whole, because `audit.py`'s unrelated,
    pre-existing 6-field `AuditSink.record` (a DIFFERENT, non-durable
    sink -- see `application_audit.py`'s own module docstring, "A
    *separate* sink... not a replacement for either") happens to share
    the SAME `outcome` parameter name with its OWN, disjoint vocabulary
    (`"denied"`/its own `"success"` default), which would otherwise
    collide with this vocabulary under an unrestricted, whole-tree scan.
    A future new `outcome=` word added to `audit_dispatch.py` itself and
    left undeclared here is still caught, not silently permitted."""
    from mitatedb_api.application_audit import DECLARED_AUDIT_OUTCOMES

    from .test_audit_query import _SRC_DIR, _field_literal_union, _literal_leaves, _scan_file_field_sites

    assert "replayed" in DECLARED_AUDIT_OUTCOMES
    dispatch_file = [_SRC_DIR / "audit_dispatch.py"]
    emitted = _field_literal_union(dispatch_file, "outcome")
    assert emitted, "the AST scanner found zero outcome literals -- it is itself broken"
    # a denial's row takes its `outcome` from a dict literal (`route_denial`'s
    # `fields`), which the keyword/assignment union above does not read
    _keyword_sites, dict_sites, _assignment_sites = _scan_file_field_sites(dispatch_file[0], "outcome")
    for _lineno, _kind, value, _ok in dict_sites:
        emitted |= _literal_leaves(value)
    assert emitted == DECLARED_AUDIT_OUTCOMES, (
        f"emittable-vs-declared mismatch: emitted but not declared: {emitted - DECLARED_AUDIT_OUTCOMES!r}; "
        f"declared but never actually emitted: {DECLARED_AUDIT_OUTCOMES - emitted!r}"
    )


class IdempotencyDigestTests(unittest.TestCase):
    """I-2/I-13: the digest rule itself, independent of any storage
    backend."""

    def test_excludes_plan_dry_run_and_idempotency_key_only(self):
        request = {
            "operations": [{"type": "insert"}], "budget": {"execution_ms": 10}, "transaction": "atomic",
            "idempotency_key": "k1", "plan": "stale-token", "dry_run": True,
        }
        normalized = normalize_request_for_idempotency(request)
        self.assertNotIn(b"idempotency_key", normalized)
        self.assertNotIn(b"plan", normalized)
        self.assertNotIn(b"dry_run", normalized)
        self.assertIn(b"budget", normalized)
        self.assertIn(b"transaction", normalized)

    def test_differs_only_by_body_not_by_key(self):
        base = {"operations": [{"type": "insert", "values": {"title": "a"}}]}
        same_body_different_key_a = dict(base, idempotency_key="k1")
        same_body_different_key_b = dict(base, idempotency_key="k2")
        self.assertEqual(
            idempotency_digest(same_body_different_key_a), idempotency_digest(same_body_different_key_b),
            "the idempotency digest must not depend on the key's own value",
        )
        different_body = dict(base, idempotency_key="k1")
        different_body["operations"] = [{"type": "insert", "values": {"title": "b"}}]
        self.assertNotEqual(idempotency_digest(same_body_different_key_a), idempotency_digest(different_body))

    def test_idempotency_key_is_part_of_the_plan_digest(self):
        """I-13: `idempotency_key`, when present, changes the plan token --
        `normalize_request_for_plan` excludes only `plan`/`dry_run`."""
        without_key = {"operations": [{"type": "insert", "values": {"title": "a"}}]}
        with_key = dict(without_key, idempotency_key="k1")
        self.assertNotEqual(
            compute_plan_token(without_key, 0), compute_plan_token(with_key, 0),
            "an idempotency_key must change the plan token (I-13)",
        )


if __name__ == "__main__":
    unittest.main()
