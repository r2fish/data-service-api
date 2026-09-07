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
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from mitatedb_api import ControlPlane, FoundationConfig, MitateDataService, Role
from mitatedb_api.cell import compute_plan_token, idempotency_digest, normalize_request_for_idempotency
from mitatedb_api.errors import ConflictError, ResourceLimitError, ValidationError


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
