import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from mitatedb_api import (ControlPlane, Filter, FoundationConfig,
                          MitateDataService, ProvisioningFacade, Role)
from mitatedb_api.cell import _canonical_where_json
from mitatedb_api.errors import (AuthenticationError,
                                 AuthorizationStateUnavailable,
                                 CapabilityError, ConflictError,
                                 DestructiveConfirmationRequired,
                                 NotFoundError, ResourceLimitError,
                                 ValidationError)


class FoundationTests(unittest.TestCase):
    def setUp(self):
        self.control = ControlPlane("synthetic-test-pepper-0123456789")
        self.control.provision_application("app_a")
        self.control.provision_application("app_b")
        self.dev_id, self.dev_secret = self.control.issue_credential("app_a", Role.DEVELOPER)
        self.runtime_id, self.runtime_secret = self.control.issue_credential("app_a", Role.RUNTIME)
        self.other_id, self.other_secret = self.control.issue_credential("app_b", Role.RUNTIME)
        self.other_dev_id, self.other_dev_secret = self.control.issue_credential("app_b", Role.DEVELOPER)
        self.service = MitateDataService(self.control)
        self.dev = self.service.open_session(self.dev_secret)
        self.runtime = self.service.open_session(self.runtime_secret)

    def test_developer_schema_and_runtime_crud(self):
        self.dev.create_collection("notes", {"title": "text", "rank": "integer"})
        self.runtime.insert("notes", {"title": "hello", "rank": 1})
        self.assertEqual(self.runtime.read("notes", filters=[Filter("rank", "eq", 1)])[0]["title"], "hello")
        self.assertFalse(hasattr(self.runtime, "create_collection"))

    def test_application_scope_is_server_bound(self):
        self.dev.create_collection("notes", {"title": "text"})
        self.runtime.insert("notes", {"title": "private"})
        other_dev = self.service.open_session(self.other_dev_secret)
        other_dev.create_collection("notes", {"title": "text"})
        other = self.service.open_session(self.other_secret)
        other.insert("notes", {"title": "other-private"})
        self.assertEqual(other.read("notes")[0]["title"], "other-private")
        self.assertEqual(self.runtime.read("notes")[0]["title"], "private")

    def test_no_arbitrary_sql_and_identifier_validation(self):
        self.dev.create_collection("notes", {"title": "text"})
        with self.assertRaises(ValidationError):
            self.runtime.read("notes; DROP TABLE notes", limit=1)
        with self.assertRaises(ValidationError):
            self.runtime.insert("notes", {"title); DROP TABLE notes;--": "x"})

    def test_contains_filter_is_honestly_rejected_never_executed_as_a_like_wildcard(self):
        # Contract 1.1.0 (CCR-13, §0.5 Q-2 adjudication): `contains` is a
        # contract-listed filter operator this peer declares `unsupported`
        # in its own `structured_query` capability entry (`_OPS` in cell.py
        # has no entry for it) -- it must never be silently executed with
        # SQL LIKE wildcard pass-through semantics (which would also
        # violate Q-2's "no wildcard interpretation" rule for `contains`
        # even if it were implemented). A row whose title would match a
        # naive `%<value>%` LIKE search must not silently come back; the
        # operator is refused outright instead.
        #
        # Conformance-review finding (WP-5a, C-12 reverse condition): this
        # used to assert `ValidationError` here, but `contains` is real
        # contract vocabulary this peer's own capability document declares
        # `unsupported` -- `capability_status.rules` requires
        # `CAPABILITY_UNSUPPORTED` for exactly that combination
        # ("recognized but not provided"), the same distinction `matches`
        # below already drew correctly. `cell.py::_where` previously
        # special-cased only `matches`; it now treats `contains`/`matches`/
        # `is_null` uniformly.
        self.dev.create_collection("notes", {"title": "text"})
        self.runtime.insert("notes", {"title": "50% off everything"})
        with self.assertRaises(CapabilityError):
            self.runtime.read("notes", filters=[Filter("title", "contains", "50%")])
        # No partial/silent execution: the row is untouched and still
        # readable via a supported operator.
        self.assertEqual(self.runtime.read("notes")[0]["title"], "50% off everything")

    def test_matches_filter_is_capability_unsupported_not_validation_failed(self):
        # Contract 1.1.0 (CCR-13, §0.5 Q-2 adjudication): `matches` is
        # additive vocabulary this peer does not implement, refused with
        # `CapabilityError` (-> `CAPABILITY_UNSUPPORTED`) rather than
        # `ValidationError` (-> `VALIDATION_FAILED`): a positive, honest
        # "recognized but not provided" answer, not "malformed request" --
        # the same answer `contains`/`is_null` now give (see the two
        # neighboring tests).
        self.dev.create_collection("notes", {"title": "text"})
        self.runtime.insert("notes", {"title": "hello"})
        with self.assertRaises(CapabilityError):
            self.runtime.read("notes", filters=[Filter("title", "matches", "hel%")])
        self.assertEqual(self.runtime.read("notes")[0]["title"], "hello")

    def test_is_null_filter_is_capability_unsupported_not_validation_failed(self):
        # Conformance-review finding (WP-5a, C-12 reverse condition): like
        # `contains` above, `is_null` is real contract vocabulary
        # (`allowed_query_operators`) this peer declares `unsupported` in
        # its own `structured_query` capability entry, but the pre-fix code
        # fell through to the generic "operator this peer does not
        # implement at all" branch and raised `ValidationError` instead of
        # `CapabilityError` -- disagreeing with its own declaration. Fixed
        # alongside `contains` in `cell.py::_where`.
        self.dev.create_collection("notes", {"title": "text"})
        self.runtime.insert("notes", {"title": "hello"})
        with self.assertRaises(CapabilityError):
            self.runtime.read("notes", filters=[Filter("title", "is_null", None)])
        self.assertEqual(self.runtime.read("notes")[0]["title"], "hello")

    def test_transaction_rolls_back(self):
        self.dev.create_collection("notes", {"title": "text"})
        with self.assertRaises(ValidationError):
            self.runtime.transact([
                {"type": "insert", "collection": "notes", "values": {"title": "first"}},
                {"type": "unsupported", "collection": "notes", "values": {"title": "second"}},
            ])
        self.assertEqual(self.runtime.read("notes"), [])

    def test_transact_insert_with_expected_revision_is_rejected_before_execution(self):
        # Conformance-review finding (docs/design/CONFORMANCE_ADAPTER_V1.md
        # section 12, correction B-2): `transact()`'s "insert" branch used to
        # ignore any operation-dict key it did not itself read, so an
        # `expected_revision` (a revision precondition this peer does not
        # implement) rode along on an otherwise-valid insert and the row
        # still committed -- silently dropping a real request semantic
        # instead of refusing it (contract `versioning.unknown_capability`:
        # "The service returns CAPABILITY_UNSUPPORTED without executing a
        # fallback."). This must be refused before any row is written, and
        # must not affect unrelated, well-formed inserts in the same batch.
        self.dev.create_collection("notes", {"title": "text"})
        with self.assertRaises(CapabilityError):
            self.runtime.transact([
                {"type": "insert", "collection": "notes", "values": {"title": "first"}},
                {"type": "insert", "collection": "notes", "values": {"title": "second"}, "expected_revision": "deadbeef"},
            ])
        self.assertEqual(self.runtime.read("notes"), [])

    # --- P3-D2 (design docs/design/MITATEDB_PHASE3_HTTP_PERSISTENCE_V1.md
    # R-5, WP-1.5): `transact()` update/delete atomic convergence. ---------

    def test_transact_executes_mixed_insert_update_delete_atomically(self):
        """A real mixed batch [insert, update, delete] executes as one
        atomic unit -- converging real behavior onto the existing
        `atomic_mutation.operations: ["insert", "update", "delete"]`
        declaration (unchanged by this WP). The batch-embedded delete goes
        through the identical declare-and-echo confirmation choke the
        dedicated `delete()` method uses (same fingerprinted phrase)."""
        self.dev.create_collection("widgets", {"title": "text", "rank": "integer"})
        self.runtime.insert("widgets", {"title": "keep-updated", "rank": 1})
        self.runtime.insert("widgets", {"title": "to-delete", "rank": 2})

        with self.assertRaises(DestructiveConfirmationRequired) as ctx:
            self.runtime.transact([
                {"type": "delete", "collection": "widgets", "filters": [Filter("rank", "eq", 2)]},
            ])
        phrase = ctx.exception.details["required_confirmation"]

        results = self.runtime.transact([
            {"type": "insert", "collection": "widgets", "values": {"title": "brand-new", "rank": 3}},
            {"type": "update", "collection": "widgets", "values": {"title": "renamed"}, "filters": [Filter("rank", "eq", 1)]},
            {"type": "delete", "collection": "widgets", "filters": [Filter("rank", "eq", 2)],
             "destructive": True, "confirm": phrase},
        ])
        self.assertEqual(len(results), 3)
        self.assertIn("rowid", results[0])
        self.assertEqual(results[1], {"updated": 1})
        self.assertEqual(results[2], {"deleted": 1})
        rows = {row["rank"]: row["title"] for row in self.runtime.read("widgets")}
        self.assertEqual(rows, {1: "renamed", 3: "brand-new"})

    def test_transact_mixed_batch_rolls_back_everything_when_the_delete_confirmation_is_stale(self):
        """The whole batch -- including the insert and update that would
        otherwise have succeeded -- must roll back when a LATER operation
        in the same batch (here, the delete) fails its own declare-and-
        echo check. Proves atomicity, not merely per-operation
        validation."""
        self.dev.create_collection("widgets", {"title": "text", "rank": "integer"})
        self.runtime.insert("widgets", {"title": "seed", "rank": 1})

        with self.assertRaises(DestructiveConfirmationRequired) as ctx:
            self.runtime.delete("widgets", [Filter("rank", "eq", 1)])
        stale_phrase = ctx.exception.details["required_confirmation"]
        # Invalidate that phrase (P3-D1's own schema-revision fingerprint)
        # by bumping the schema revision underneath it.
        self.dev.add_field("widgets", "extra", "text")

        with self.assertRaises(DestructiveConfirmationRequired):
            self.runtime.transact([
                {"type": "insert", "collection": "widgets", "values": {"title": "should-not-persist", "rank": 99}},
                {"type": "update", "collection": "widgets", "values": {"title": "should-not-persist-either"},
                 "filters": [Filter("rank", "eq", 1)]},
                {"type": "delete", "collection": "widgets", "filters": [Filter("rank", "eq", 1)],
                 "destructive": True, "confirm": stale_phrase},
            ])

        rows = self.runtime.read("widgets")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["title"], "seed")

    def test_transact_delete_rejects_wire_omitted_destructive_with_valid_confirmation(self):
        """The batch-embedded delete's own confirmation choke rejects the
        exact V2b-wire shape (`destructive` key genuinely absent from the
        wire, a real, currently-valid `confirm` phrase still present) the
        same way the dedicated `delete()` method does -- a missing
        `destructive` field is equivalent to `False`, never to `True`
        (contract `valid_confirmation`)."""
        self.dev.create_collection("widgets", {"title": "text", "rank": "integer"})
        self.runtime.insert("widgets", {"title": "keep-me", "rank": 1})

        with self.assertRaises(DestructiveConfirmationRequired) as ctx:
            self.runtime.transact([{"type": "delete", "collection": "widgets", "filters": [Filter("rank", "eq", 1)]}])
        phrase = ctx.exception.details["required_confirmation"]

        with self.assertRaises(DestructiveConfirmationRequired):
            self.runtime.transact([{"type": "delete", "collection": "widgets", "filters": [Filter("rank", "eq", 1)],
                                    "confirm": phrase}])
        self.assertEqual(self.runtime.read("widgets"), [{"title": "keep-me", "rank": 1}])

    def test_transact_upsert_rejected_regardless_of_other_batch_contents(self):
        """P3-D2 does not touch `upsert`: it remains refused with
        `CapabilityError` no matter what else shares the batch, and the
        whole batch (including a real insert alongside it) still rolls
        back."""
        self.dev.create_collection("widgets", {"title": "text", "rank": "integer"})
        with self.assertRaises(CapabilityError):
            self.runtime.transact([
                {"type": "insert", "collection": "widgets", "values": {"title": "should-not-persist", "rank": 1}},
                {"type": "upsert", "collection": "widgets", "values": {"title": "x", "rank": 2}},
            ])
        self.assertEqual(self.runtime.read("widgets"), [])

    def test_transact_update_rejects_extra_capability_shaped_key(self):
        """Same "capability gap, not malformed request" treatment
        `expected_revision` already gets on `insert` (the neighboring
        test above) extends to `update`: an unread extra key must not
        silently ride along with an otherwise well-formed batch update."""
        self.dev.create_collection("notes", {"title": "text"})
        self.runtime.insert("notes", {"title": "seed"})
        with self.assertRaises(CapabilityError):
            self.runtime.transact([
                {"type": "update", "collection": "notes", "values": {"title": "changed"},
                 "filters": [Filter("title", "eq", "seed")], "expected_revision": "deadbeef"},
            ])
        self.assertEqual(self.runtime.read("notes")[0]["title"], "seed")

    def test_transact_batch_delete_audit_is_deferred_past_commit_and_absent_on_rollback(self):
        """A batch-embedded delete's own `destructive_data_operation`
        audit record must never claim a write that a LATER operation in
        the same batch caused to roll back (`transact()`'s own
        `pending_audit` mechanism, P3-D2). Checked from both directions:
        a rolled-back batch records nothing, and a committed batch records
        exactly once per delete actually executed."""
        self.dev.create_collection("widgets", {"title": "text", "rank": "integer"})
        self.runtime.insert("widgets", {"title": "seed", "rank": 1})
        before = len(self.control.audit.snapshot())

        with self.assertRaises(DestructiveConfirmationRequired) as ctx:
            self.runtime.delete("widgets", [Filter("rank", "eq", 1)])
        phrase = ctx.exception.details["required_confirmation"]
        after_probe = len(self.control.audit.snapshot())
        self.assertEqual(after_probe, before, "an unconfirmed delete probe must not itself be audited")

        # A confirmed batch delete followed by a failing, unrelated
        # operation: the whole batch rolls back, so no audit record for
        # the delete may appear either.
        with self.assertRaises(ValidationError):
            self.runtime.transact([
                {"type": "delete", "collection": "widgets", "filters": [Filter("rank", "eq", 1)],
                 "destructive": True, "confirm": phrase},
                {"type": "unsupported", "collection": "widgets", "values": {}},
            ])
        after_rollback = len(self.control.audit.snapshot())
        self.assertEqual(after_rollback, before, "a rolled-back batch delete must not be audited")
        self.assertEqual(self.runtime.read("widgets")[0]["title"], "seed")

        # The same confirmed delete, alone, actually commits: exactly one
        # new `destructive_data_operation` record appears.
        result = self.runtime.transact([
            {"type": "delete", "collection": "widgets", "filters": [Filter("rank", "eq", 1)],
             "destructive": True, "confirm": phrase},
        ])
        self.assertEqual(result, [{"deleted": 1}])
        events_after_commit = self.control.audit.snapshot()[before:]
        destructive_events = [e for e in events_after_commit if e.event_type == "destructive_data_operation"]
        self.assertEqual(len(destructive_events), 1)

    def test_transact_delete_rejects_extra_capability_shaped_key(self):
        """Same treatment for `delete`: an unread extra key (here,
        `unique_key`, which this peer has no concept of at all) is a
        capability gap, checked before the confirmation phrase is even
        constructed."""
        self.dev.create_collection("notes", {"title": "text"})
        self.runtime.insert("notes", {"title": "seed"})
        with self.assertRaises(CapabilityError):
            self.runtime.transact([
                {"type": "delete", "collection": "notes", "filters": [Filter("title", "eq", "seed")],
                 "unique_key": "whatever"},
            ])
        self.assertEqual(self.runtime.read("notes")[0]["title"], "seed")

    def test_transact_batch_update_and_delete_reject_the_same_mass_operation_shapes_as_dedicated_methods(self):
        """M-1 (independent review, WP-1.5 follow-up): the batch-embedded
        `update`/`delete` branches must apply the identical mass-operation
        guards the dedicated `update()`/`delete()` methods already
        enforce -- an omitted/empty/`None` `filters` (a filter-less batch
        update/delete would otherwise mass-mutate/mass-delete every row)
        and empty `values` for `update` (a no-op that must still be
        refused as a shape defect, not silently accepted) -- rejecting
        each of the 6 shapes below with `ValidationError` before any
        write, and leaving the WHOLE BATCH's own state unchanged (nothing
        commits, the well-formed `insert` sharing the batch included).
        This is the exact guard `_validate_update`/
        `_validate_delete_confirmation` (the shared choke both dedicated
        and batch-embedded paths pass through, m-1) is responsible for."""
        self.dev.create_collection("widgets", {"title": "text"})
        self.runtime.insert("widgets", {"title": "seed"})

        bad_shapes = {
            "update: filters key omitted": {"type": "update", "collection": "widgets", "values": {"title": "x"}},
            "update: filters=[]": {"type": "update", "collection": "widgets", "values": {"title": "x"}, "filters": []},
            "update: filters=None": {"type": "update", "collection": "widgets", "values": {"title": "x"}, "filters": None},
            "update: values={}": {"type": "update", "collection": "widgets", "values": {},
                                   "filters": [Filter("title", "eq", "seed")]},
            "delete: filters key omitted": {"type": "delete", "collection": "widgets"},
            "delete: filters=[]": {"type": "delete", "collection": "widgets", "filters": []},
        }
        for label, bad_op in bad_shapes.items():
            with self.assertRaises(ValidationError, msg=label):
                self.runtime.transact([
                    {"type": "insert", "collection": "widgets", "values": {"title": "should-not-persist"}},
                    bad_op,
                ])
            self.assertEqual(self.runtime.read("widgets"), [{"title": "seed"}],
                             f"batch must not have written anything for shape {label!r}")

    def test_transact_batch_delete_accepts_an_empty_values_key(self):
        """m-4 (independent review, WP-1.5 follow-up): a batch delete
        operation-dict carrying `values: {}` must be accepted (not a
        capability-gap `CapabilityError`) -- `_TRANSACT_DELETE_KEYS`
        deliberately lists `values` for exactly this wire shape.
        Implementation-level necessity (not just contract-shape
        permissiveness, see `_TRANSACT_DELETE_KEYS`'s own module-level
        comment): `conformance_adapter_mitatedb.py::attempt_batch_with_
        addresses` always sets an `"values"` key on every batch item
        regardless of operation type, so this is a necessary condition for
        the C-06 batch-delete vector to reach this peer's real entry point
        at all -- pinned here locally too, not only via the common
        conformance suite."""
        self.dev.create_collection("widgets", {"title": "text"})
        self.runtime.insert("widgets", {"title": "keep-me"})
        with self.assertRaises(DestructiveConfirmationRequired) as ctx:
            self.runtime.transact([
                {"type": "delete", "collection": "widgets", "values": {},
                 "filters": [Filter("title", "eq", "keep-me")]},
            ])
        phrase = ctx.exception.details["required_confirmation"]
        result = self.runtime.transact([
            {"type": "delete", "collection": "widgets", "values": {},
             "filters": [Filter("title", "eq", "keep-me")], "destructive": True, "confirm": phrase},
        ])
        self.assertEqual(result, [{"deleted": 1}])
        self.assertEqual(self.runtime.read("widgets"), [])

    # --- P35 WP-2 (design docs/design/PHASE35_CROSS_ENTITY_AND_CONTRACT_
    # 130_V1.md §2): two-pass transact + batch_entities + cross-entity
    # atomicity. ---------------------------------------------------------

    def test_transact_two_pass_structure_zero_backend_calls_when_a_later_operation_fails_validation(self):
        """P35-D10 (structural, white-box): a batch whose FIRST operation
        is individually valid must never reach the backend at all -- not
        `begin()`, not `insert_in_transaction()` -- when a LATER operation
        in the same batch fails VALIDATION. This is not observable
        black-box (the net effect, "nothing persists", is identical either
        way); it is pinned here by wrapping the real SQLite backend's own
        methods and counting calls directly."""
        self.dev.create_collection("two_pass_probe", {"title": "text"})
        cell = self.control.cells["app_a"]
        backend = cell._backend
        calls = {"begin": 0, "insert_in_transaction": 0}
        real_begin = backend.begin
        real_insert = backend.insert_in_transaction

        def counting_begin():
            calls["begin"] += 1
            return real_begin()

        def counting_insert(collection, fields, params):
            calls["insert_in_transaction"] += 1
            return real_insert(collection, fields, params)

        backend.begin = counting_begin
        backend.insert_in_transaction = counting_insert
        try:
            with self.assertRaises(ValidationError):
                self.runtime.transact([
                    {"type": "insert", "collection": "two_pass_probe", "values": {"title": "would-have-executed"}},
                    {"type": "unsupported", "collection": "two_pass_probe", "values": {"title": "invalid"}},
                ])
        finally:
            backend.begin = real_begin
            backend.insert_in_transaction = real_insert
        self.assertEqual(calls["begin"], 0, "the backend transaction must never open when pass 1 fails")
        self.assertEqual(calls["insert_in_transaction"], 0, "an earlier, individually-valid op's DML must never reach the backend")
        self.assertEqual(self.runtime.read("two_pass_probe"), [])

    def test_transact_error_priority_validation_error_wins_over_an_earlier_execution_time_failure(self):
        """P35-D9: in a batch mixing an operation that would fail at
        BACKEND EXECUTION time with a LATER operation that fails
        VALIDATION, the returned error is now the validation error --
        pass 1 validates the whole batch (including the later,
        validation-failing operation) before pass 2 ever executes
        anything, so the earlier operation's own execution-time failure
        is never even reached.

        M-2 correction (independent review, WP-2 follow-up): the earlier
        claim here ("no naturally-reachable execution-time failure") was
        false -- the one known natural execution-time failure (a lone
        UTF-16 surrogate code point in a value, escaping as a raw
        `UnicodeEncodeError` on both backends) was reclassified to
        deterministic validation-time rejection by WP-2 review B-2; the
        synthesized `ConflictError` below remains the exercise vehicle
        for this test's own subject (error-type priority), now the only
        way to exercise an execution-time failure at all on either
        backend."""
        self.dev.create_collection("priority_probe", {"title": "text"})
        cell = self.control.cells["app_a"]
        backend = cell._backend
        real_insert = backend.insert_in_transaction

        def failing_insert(collection, fields, params):
            raise ConflictError("synthetic execution-time failure")

        backend.insert_in_transaction = failing_insert
        try:
            with self.assertRaises(ValidationError):
                self.runtime.transact([
                    {"type": "insert", "collection": "priority_probe", "values": {"title": "would-fail-at-execution"}},
                    {"type": "unsupported", "collection": "priority_probe", "values": {"title": "invalid"}},
                ])
        finally:
            backend.insert_in_transaction = real_insert
        self.assertEqual(self.runtime.read("priority_probe"), [])

    def test_transact_cross_entity_atomic_commit_across_two_entities(self):
        self.dev.create_collection("cross_a", {"title": "text"})
        self.dev.create_collection("cross_b", {"title": "text"})
        results = self.runtime.transact([
            {"type": "insert", "collection": "cross_a", "values": {"title": "a-row"}},
            {"type": "insert", "collection": "cross_b", "values": {"title": "b-row"}},
        ])
        self.assertEqual(len(results), 2)
        self.assertEqual(self.runtime.read("cross_a")[0]["title"], "a-row")
        self.assertEqual(self.runtime.read("cross_b")[0]["title"], "b-row")

    def test_transact_cross_entity_rollback_when_later_entity_operation_is_invalid(self):
        self.dev.create_collection("cross_c", {"title": "text"})
        self.dev.create_collection("cross_d", {"title": "text"})
        with self.assertRaises(ValidationError):
            self.runtime.transact([
                {"type": "insert", "collection": "cross_c", "values": {"title": "should-not-persist"}},
                # `filters` omitted -- a shape defect for `update`.
                {"type": "update", "collection": "cross_d", "values": {"title": "x"}},
            ])
        self.assertEqual(self.runtime.read("cross_c"), [])
        self.assertEqual(self.runtime.read("cross_d"), [])

    def test_transact_batch_entities_boundary_and_distinct_count_ignores_repeats(self):
        """P35-D2: `batch_entities` bounds DISTINCT collection names, not
        operation count -- a cheap config override (`max_batch_entities=2`)
        exercises both directions: 2 distinct entities in one batch is
        fine; a 3rd distinct entity in the same batch is refused; and many
        operations against a SINGLE entity never trips the bound at all,
        no matter how many operations share it."""
        config = FoundationConfig(max_batch_entities=2)
        control = ControlPlane("synthetic-test-pepper-0123456789", config)
        control.provision_application("entities_bound")
        dev_id, dev_secret = control.issue_credential("entities_bound", Role.DEVELOPER)
        runtime_id, runtime_secret = control.issue_credential("entities_bound", Role.RUNTIME)
        dev = MitateDataService(control).open_session(dev_secret)
        runtime = MitateDataService(control).open_session(runtime_secret)
        for name in ("ent_one", "ent_two", "ent_three"):
            dev.create_collection(name, {"title": "text"})

        # 2 distinct entities: at the declared bound, succeeds.
        result = runtime.transact([
            {"type": "insert", "collection": "ent_one", "values": {"title": "1"}},
            {"type": "insert", "collection": "ent_two", "values": {"title": "1"}},
        ])
        self.assertEqual(len(result), 2)

        # 3 distinct entities: over the declared bound, refused.
        with self.assertRaises(ResourceLimitError) as ctx:
            runtime.transact([
                {"type": "insert", "collection": "ent_one", "values": {"title": "2"}},
                {"type": "insert", "collection": "ent_two", "values": {"title": "2"}},
                {"type": "insert", "collection": "ent_three", "values": {"title": "1"}},
            ])
        self.assertEqual(ctx.exception.details, {"limit_class": "batch_entities"})
        # Nothing from the refused batch persisted (all-or-nothing, same
        # as any other transact() failure).
        self.assertEqual(len(runtime.read("ent_one")), 1)
        self.assertEqual(len(runtime.read("ent_two")), 1)
        self.assertEqual(runtime.read("ent_three"), [])

        # Many operations against a SINGLE entity: distinct count is 1,
        # never trips the batch_entities=2 bound regardless of how many
        # operations share that one entity (bounded only by batch_items,
        # independently, contract endpoints.cross_entity_mutate.semantics).
        many_same_entity = [{"type": "insert", "collection": "ent_one", "values": {"title": f"r{i}"}} for i in range(10)]
        result = runtime.transact(many_same_entity)
        self.assertEqual(len(result), 10)

    def test_transact_batch_entities_default_boundary_is_ten(self):
        """The DECLARED default (`FoundationConfig.max_batch_entities ==
        10`, unmodified config) is the one actually enforced: exactly 10
        distinct entities in one batch succeeds; an 11th distinct entity
        in the same batch is refused."""
        self.assertEqual(self.runtime.capabilities()["limits"]["batch_entities"], 10)
        names = [f"default_bound_{i}" for i in range(11)]
        for name in names:
            self.dev.create_collection(name, {"title": "text"})

        ok_ops = [{"type": "insert", "collection": n, "values": {"title": "x"}} for n in names[:10]]
        result = self.runtime.transact(ok_ops)
        self.assertEqual(len(result), 10)

        over_ops = [{"type": "insert", "collection": n, "values": {"title": "y"}} for n in names]  # 11 distinct
        with self.assertRaises(ResourceLimitError) as ctx:
            self.runtime.transact(over_ops)
        self.assertEqual(ctx.exception.details, {"limit_class": "batch_entities"})
        # The over-limit batch must not have added a second row anywhere.
        self.assertEqual(len(self.runtime.read(names[0])), 1)

    def test_transact_cross_entity_delete_wrong_entity_phrase_is_refused(self):
        """Each batch-embedded delete's own confirmation phrase is
        fingerprinted to ITS OWN collection name (`_delete_confirmation_
        phrase`) -- a phrase probed against one entity must be refused
        when echoed back for a DIFFERENT entity's delete, even within the
        same cross-entity batch."""
        self.dev.create_collection("phrase_a", {"title": "text"})
        self.dev.create_collection("phrase_b", {"title": "text"})
        self.runtime.insert("phrase_a", {"title": "keep-me"})
        self.runtime.insert("phrase_b", {"title": "keep-me"})

        with self.assertRaises(DestructiveConfirmationRequired) as ctx_a:
            self.runtime.transact([
                {"type": "delete", "collection": "phrase_a", "filters": [Filter("title", "eq", "keep-me")]},
            ])
        phrase_a = ctx_a.exception.details["required_confirmation"]
        self.assertIn("phrase_a", phrase_a)

        with self.assertRaises(DestructiveConfirmationRequired):
            self.runtime.transact([
                {"type": "delete", "collection": "phrase_b", "filters": [Filter("title", "eq", "keep-me")],
                 "destructive": True, "confirm": phrase_a},
            ])
        self.assertEqual(self.runtime.read("phrase_a")[0]["title"], "keep-me")
        self.assertEqual(self.runtime.read("phrase_b")[0]["title"], "keep-me")

        with self.assertRaises(DestructiveConfirmationRequired) as ctx_b:
            self.runtime.transact([
                {"type": "delete", "collection": "phrase_b", "filters": [Filter("title", "eq", "keep-me")]},
            ])
        phrase_b = ctx_b.exception.details["required_confirmation"]
        self.assertNotEqual(phrase_a, phrase_b)

        result = self.runtime.transact([
            {"type": "delete", "collection": "phrase_a", "filters": [Filter("title", "eq", "keep-me")],
             "destructive": True, "confirm": phrase_a},
            {"type": "delete", "collection": "phrase_b", "filters": [Filter("title", "eq", "keep-me")],
             "destructive": True, "confirm": phrase_b},
        ])
        self.assertEqual(result, [{"deleted": 1}, {"deleted": 1}])
        self.assertEqual(self.runtime.read("phrase_a"), [])
        self.assertEqual(self.runtime.read("phrase_b"), [])

    def test_transact_lone_surrogate_value_is_deterministic_validation_failure_and_earlier_entity_unchanged(self):
        """B-2 (independent review, WP-2 follow-up -- the atomicity hole,
        largest safety fix of that review): a lone UTF-16 surrogate code
        point in a LATER operation's own value (`"\\ud800"`) must be
        rejected deterministically at VALIDATION time (pass 1,
        `encode_value`, B-2(ii)) -- not escape as a raw
        `UnicodeEncodeError` during pass 2 execution, which pre-fix left
        the EARLIER, individually-valid operation's own write sitting
        uncommitted-but-visible (B-2(i)'s own atomicity hole). Both
        entities must be left completely unchanged."""
        self.dev.create_collection("surrogate_a", {"title": "text"})
        self.dev.create_collection("surrogate_b", {"title": "text"})
        with self.assertRaises(ValidationError):
            self.runtime.transact([
                {"type": "insert", "collection": "surrogate_a", "values": {"title": "should-not-persist"}},
                {"type": "insert", "collection": "surrogate_b", "values": {"title": "\ud800"}},
            ])
        self.assertEqual(self.runtime.read("surrogate_a"), [])
        self.assertEqual(self.runtime.read("surrogate_b"), [])

    def test_transact_rollback_is_unconditional_for_a_non_foundation_error_raised_mid_pass_2(self):
        """B-2(i) (independent review, WP-2 follow-up): structural pin of
        the actual fix itself, independent of B-2(ii)'s currently-known
        trigger -- ANY exception raised mid pass-2 execution (here, a
        synthesized `RuntimeError` from a wrapped `insert_in_transaction`,
        standing in for any future unclassified backend failure) must
        still trigger `self._backend.rollback()` exactly once before
        propagating, and must leave no partial effect from any EARLIER,
        individually-valid operation in the same batch."""
        self.dev.create_collection("rollback_a", {"title": "text"})
        self.dev.create_collection("rollback_b", {"title": "text"})
        cell = self.control.cells["app_a"]
        backend = cell._backend
        rollback_calls = {"count": 0}
        real_rollback = backend.rollback
        real_insert = backend.insert_in_transaction
        call_index = {"n": 0}

        def counting_rollback():
            rollback_calls["count"] += 1
            return real_rollback()

        def failing_second_insert(collection, fields, params):
            call_index["n"] += 1
            if call_index["n"] == 2:
                raise RuntimeError("synthetic non-FoundationError failure")
            return real_insert(collection, fields, params)

        backend.rollback = counting_rollback
        backend.insert_in_transaction = failing_second_insert
        try:
            with self.assertRaises(RuntimeError):
                self.runtime.transact([
                    {"type": "insert", "collection": "rollback_a", "values": {"title": "should-not-persist"}},
                    {"type": "insert", "collection": "rollback_b", "values": {"title": "would-fail-mid-execution"}},
                ])
        finally:
            backend.rollback = real_rollback
            backend.insert_in_transaction = real_insert
        self.assertEqual(rollback_calls["count"], 1, "rollback must fire exactly once for the non-FoundationError failure")
        self.assertEqual(self.runtime.read("rollback_a"), [])
        self.assertEqual(self.runtime.read("rollback_b"), [])

    def test_cross_entity_mutation_is_declared_partial(self):
        """R-5 / M-1 (independent review, WP-2 follow-up): the declaration
        flip -- `cross_entity_mutation` mirrors `atomic_mutation`'s own
        declared shape exactly, `status` included (same `operations`
        vocabulary AND the same `unsupported: ["upsert"]` truthful
        refusal, so the same `"partial"` status), no longer `unavailable`
        (§0's own "偽宣言" finding). `"enabled"` was the WP-2 review's own
        blocker-adjacent M-1 finding -- a self-contradiction against this
        peer's own declaration convention for the identical situation."""
        declared = self.runtime.capabilities()["capabilities"]["cross_entity_mutation"]
        self.assertEqual(declared, {
            "status": "partial", "operations": ["insert", "update", "delete"], "unsupported": ["upsert"],
        })

    def test_disable_revoke_and_unavailable_state_fail_closed(self):
        self.dev.create_collection("notes", {"title": "text"})
        self.runtime.insert("notes", {"title": "before-revoke"})
        self.control.revoke_credential(self.runtime_id)
        with self.assertRaises(AuthenticationError):
            self.runtime.read("notes")
        with self.assertRaises(AuthenticationError):
            self.service.open_session(self.runtime_secret)
        self.control.disable_application("app_a")
        with self.assertRaises(AuthenticationError):
            self.dev.read("notes")
        with self.assertRaises(AuthenticationError):
            self.service.open_session(self.dev_secret)
        self.control.credentials.enable_application("app_a")
        self.control.credentials.authorization_state_available = False
        with self.assertRaises(AuthorizationStateUnavailable):
            self.service.open_session(self.dev_secret)

    def test_revoke_of_unknown_credential_id_is_rejected_not_silently_ignored(self):
        # Control-plane fail-open: an operator revoking a credential id that
        # does not exist must not be told (by silence) that the revoke
        # succeeded, since no such credential was ever active in the first
        # place.
        with self.assertRaises(NotFoundError):
            self.control.revoke_credential("no-such-credential-id")
        # A real credential is unaffected by the failed call above.
        self.dev.create_collection("notes", {"title": "text"})
        self.runtime.insert("notes", {"title": "still-active"})
        self.assertEqual(self.runtime.read("notes")[0]["title"], "still-active")

    def test_batch_and_request_size_limits_and_empty_filters_shape_check(self):
        # MA-3 (independent review, docs/design/DESTRUCTIVE_CONFIRMATION_V1.md
        # §7): renamed from `test_bounded_inputs_and_explicit_destructive_
        # confirmation` -- that name overclaimed this test's own content.
        # Post Q1-D11 nothing here exercises destructive-confirmation
        # semantics at all: the `delete("notes", [], ...)` call below is
        # refused for being a shape defect (empty `filters`), a check that
        # fires before the confirmation gate ever runs (see
        # `test_delete_without_confirmation_is_gated_not_conflated_with_
        # empty_filters` below for the gate itself, isolated). This test's
        # real remaining subject is the two `ResourceLimitError` sites
        # (`batch_items`/`request_bytes`) that still exist after Q1-D11's
        # reclassification -- positive+negative boundary coverage for
        # every remaining class lives in
        # `test_every_resource_limit_error_declared_and_enforced_values_agree`
        # below; this test keeps its own narrower, override-config
        # (`max_batch_items=1`) boundary case for variety.
        config = FoundationConfig(max_batch_items=1)
        control = ControlPlane("synthetic-test-pepper-0123456789", config)
        control.provision_application("small")
        dev_id, dev_secret = control.issue_credential("small", Role.DEVELOPER)
        dev = MitateDataService(control).open_session(dev_secret)
        dev.create_collection("notes", {"title": "text"})
        with self.assertRaises(ResourceLimitError) as batch_ctx:
            dev.transact([
                {"type": "insert", "collection": "notes", "values": {"title": "a"}},
                {"type": "insert", "collection": "notes", "values": {"title": "b"}},
            ])
        self.assertEqual(batch_ctx.exception.details, {"limit_class": "batch_items"})
        # WP-5 (docs/design/DESTRUCTIVE_CONFIRMATION_V1.md R-5): empty
        # `filters` is its own shape defect (`ValidationError`, checked
        # before the confirmation gate -- see
        # `test_delete_without_confirmation_is_gated_not_conflated_with_
        # empty_filters` below for the gate itself, isolated with non-empty
        # filters so this assertion cannot be satisfied by either reason).
        with self.assertRaises(ValidationError):
            dev.delete("notes", [], destructive=True, confirm="anything")
        with self.assertRaises(ResourceLimitError) as size_ctx:
            config.validate_request_size(config.max_request_bytes + 1)
        self.assertEqual(size_ctx.exception.details, {"limit_class": "request_bytes"})

    def test_every_resource_limit_error_declared_and_enforced_values_agree(self):
        # Q1-D11 (docs/design/DESTRUCTIVE_CONFIRMATION_V1.md §7): every
        # remaining `ResourceLimitError` site's `limit_class` must name a
        # class whose `capabilities().limits` DECLARED number is the exact
        # same value this check actually ENFORCES -- not merely a
        # plausible-sounding class name.
        #
        # MA-2 (independent review): proven from BOTH directions for every
        # one of the 5 remaining classes, not just the "declared+1 fails"
        # direction this test originally carried alone. A positive-only
        # control cannot catch a peer that silently UNDER-delivers what it
        # declares (e.g. `>=` where `>` belongs, rejecting the declared
        # value itself) -- exactly the "over-claiming" failure mode MA-2
        # names. The negative control (the declared value itself succeeds)
        # closes that gap.
        config = FoundationConfig(max_batch_items=2, max_result_rows=2, max_filter_terms=2, max_schema_objects=3)
        control = ControlPlane("synthetic-test-pepper-0123456789", config)
        control.provision_application("bounds")
        dev_id, dev_secret = control.issue_credential("bounds", Role.DEVELOPER)
        runtime_id, runtime_secret = control.issue_credential("bounds", Role.RUNTIME)
        dev = MitateDataService(control).open_session(dev_secret)
        runtime = MitateDataService(control).open_session(runtime_secret)
        limits = runtime.capabilities()["limits"]
        self.assertEqual(limits["batch_items"], 2)
        self.assertEqual(limits["result_items"], 2)
        self.assertEqual(limits["query_complexity"], 2)
        self.assertEqual(limits["schema_objects"], 3)

        # schema_objects: creating exactly the declared number of
        # collections (agree, scratch_a, scratch_b = 3) must all succeed
        # (negative control); a 4th must fail (positive control).
        dev.create_collection("agree", {"title": "text"})
        dev.create_collection("scratch_a", {"title": "text"})
        dev.create_collection("scratch_b", {"title": "text"})
        runtime.insert("agree", {"title": "x"})
        runtime.insert("agree", {"title": "y"})
        with self.assertRaises(ResourceLimitError) as schema_ctx:
            dev.create_collection("scratch_c", {"title": "text"})
        self.assertEqual(schema_ctx.exception.details, {"limit_class": "schema_objects"})

        # batch_items: exactly 2 operations succeeds; 3 fails.
        result = runtime.transact([
            {"type": "insert", "collection": "scratch_a", "values": {"title": "1"}},
            {"type": "insert", "collection": "scratch_b", "values": {"title": "1"}},
        ])
        self.assertEqual(len(result), 2)
        with self.assertRaises(ResourceLimitError) as batch_ctx:
            runtime.transact([{"type": "insert", "collection": "scratch_a", "values": {"title": "z"}}] * 3)
        self.assertEqual(batch_ctx.exception.details, {"limit_class": "batch_items"})

        # result_items: requesting exactly 2 (both existing rows) succeeds;
        # requesting 3 fails.
        rows = runtime.read("agree", limit=2)
        self.assertEqual(len(rows), 2)
        with self.assertRaises(ResourceLimitError) as result_ctx:
            runtime.read("agree", limit=3)
        self.assertEqual(result_ctx.exception.details, {"limit_class": "result_items"})

        # query_complexity: exactly 2 filters succeeds (result content is
        # irrelevant -- only that no exception was raised); 3 fails.
        runtime.read("agree", filters=[Filter("title", "eq", "x"), Filter("title", "eq", "y")])
        with self.assertRaises(ResourceLimitError) as qc_ctx:
            runtime.read("agree", filters=[Filter("title", "eq", "x")] * 3)
        self.assertEqual(qc_ctx.exception.details, {"limit_class": "query_complexity"})

        # request_bytes: exactly at the declared bound succeeds; bound+1 fails.
        config.validate_request_size(config.max_request_bytes)
        with self.assertRaises(ResourceLimitError) as size_ctx:
            config.validate_request_size(config.max_request_bytes + 1)
        self.assertEqual(size_ctx.exception.details, {"limit_class": "request_bytes"})

    def test_shape_boundary_field_counts_are_validation_failed_not_limit_exceeded(self):
        # Q1-D11 (docs/design/DESTRUCTIVE_CONFIRMATION_V1.md §7): the three
        # `max_fields`-gated checks (schema-field count at definition time,
        # read-projection width, write-payload width) mirror fixed contract
        # SHAPE bounds (write-payload directly mirrors `Mutation.values.
        # maxProperties: 100`, the same property r2db-api's own Q1-D8
        # reclassified `VALIDATION_FAILED` for) -- none of them is a
        # deployment-tunable finite-resource class, so none may raise
        # `ResourceLimitError` any longer.
        config = FoundationConfig(max_fields=2)
        control = ControlPlane("synthetic-test-pepper-0123456789", config)
        control.provision_application("narrow")
        dev_id, dev_secret = control.issue_credential("narrow", Role.DEVELOPER)
        runtime_id, runtime_secret = control.issue_credential("narrow", Role.RUNTIME)
        dev = MitateDataService(control).open_session(dev_secret)
        runtime = MitateDataService(control).open_session(runtime_secret)

        with self.assertRaises(ValidationError):
            dev.create_collection("wide", {"a": "text", "b": "text", "c": "text"})
        dev.create_collection("narrow_rows", {"a": "text", "b": "text"})
        runtime.insert("narrow_rows", {"a": "1"})
        with self.assertRaises(ValidationError):
            runtime.read("narrow_rows", fields=["a", "b", "c"])
        with self.assertRaises(ValidationError):
            runtime.insert("narrow_rows", {"a": "1", "b": "2", "c": "3"})

    def test_canonical_where_json_key_sorts_each_filter_preserves_list_order_never_stringifies(self):
        # mi-5 (independent review, docs/design/DESTRUCTIVE_CONFIRMATION_V1.md
        # §7): pins the 3 properties `_canonical_where_json`'s own docstring
        # documents but had no dedicated unit test proving directly (only
        # indirectly, through delete-phrase behavior).
        a = Filter("b_field", "eq", 1)
        b = Filter("a_field", "eq", 2)

        # property 1: each Filter serializes as a key-sorted object
        # (field/operator/value, alphabetical) -- `sort_keys=True` is load-
        # bearing even though the payload dict's own construction order
        # already happens to be alphabetical (this pins the guarantee
        # against a future refactor of that construction order).
        self.assertEqual(_canonical_where_json([a]), '[{"field":"b_field","operator":"eq","value":1}]')

        # property 2: the outer list's own order is preserved, not sorted
        # -- [a, b] and [b, a] must produce different canonical strings
        # (and therefore different digests).
        ab = _canonical_where_json([a, b])
        ba = _canonical_where_json([b, a])
        self.assertNotEqual(ab, ba)
        self.assertEqual(
            ab, '[{"field":"b_field","operator":"eq","value":1},{"field":"a_field","operator":"eq","value":2}]'
        )

        # property 3: no `default=str` -- a value `json.dumps` cannot
        # serialize natively raises `TypeError` immediately rather than
        # being silently stringified into a potentially colliding string
        # (r2db-api WP-3 followup m-7's own finding, applied identically).
        class _Unserializable:
            pass

        with self.assertRaises(TypeError):
            _canonical_where_json([Filter("f", "eq", _Unserializable())])

    def test_delete_without_confirmation_is_gated_not_conflated_with_empty_filters(self):
        # WP-2 review m-6 (docs/design/DESTRUCTIVE_CONFIRMATION_V1.md §5):
        # the old combined test above conflated "empty filters"
        # (`ValidationError`) with "missing confirmation" -- both raised
        # the same exception, so it could not actually tell which check
        # fired. This isolates the confirmation gate with non-empty
        # filters, so only the gate itself can satisfy this assertion.
        self.dev.create_collection("gated", {"title": "text"})
        self.runtime.insert("gated", {"title": "keep-me"})
        with self.assertRaises(DestructiveConfirmationRequired) as ctx:
            self.runtime.delete("gated", [Filter("title", "eq", "keep-me")])
        details = ctx.exception.details
        for key in ("required_confirmation", "consequence", "reversible_alternative", "recovery"):
            self.assertIn(key, details)
        self.assertTrue(details["required_confirmation"])
        self.assertTrue(details["consequence"])
        self.assertIsNone(details["reversible_alternative"])
        self.assertIsNone(details["recovery"])
        self.assertEqual(self.runtime.read("gated")[0]["title"], "keep-me")

        phrase = details["required_confirmation"]
        affected = self.runtime.delete("gated", [Filter("title", "eq", "keep-me")], destructive=True, confirm=phrase)
        self.assertEqual(affected, {"deleted": 1})
        self.assertEqual(self.runtime.read("gated"), [])

    def test_delete_rejects_non_boolean_destructive_and_non_string_confirm(self):
        # r2db-api WP-3 followup B-1's own finding, applied identically
        # here (WP-5): a truthy-but-non-bool `destructive`, or a non-str
        # `confirm`, must be a shape defect (`ValidationError`), never
        # accepted as satisfying the gate.
        self.dev.create_collection("typed", {"title": "text"})
        self.runtime.insert("typed", {"title": "x"})
        with self.assertRaises(ValidationError):
            self.runtime.delete("typed", [Filter("title", "eq", "x")], destructive="true", confirm=None)
        with self.assertRaises(ValidationError):
            self.runtime.delete("typed", [Filter("title", "eq", "x")], destructive=True, confirm=True)
        self.assertEqual(self.runtime.read("typed")[0]["title"], "x")

    def test_add_field_is_declared_and_usable_by_developer_only(self):
        # P3-D1 (docs/design/MITATEDB_PHASE3_HTTP_PERSISTENCE_V1.md §0
        # exception, WP-1): `add_field` is now a real, developer-only
        # capability -- declaration and implementation land in this same
        # commit, on both backends. This pins the SQLite backend's own
        # (default, in-process composition) behavior.
        self.dev.create_collection("things", {"name": "text"})
        declared = self.dev.capabilities()["capabilities"]["schema_operations"]
        # Phase 9 WP-3a (design docs/design/
        # PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md D-2 (5)):
        # `alter_field` joined `operations` in this same commit as
        # `constraint_declarations` flipping to `enabled`.
        self.assertEqual(declared["operations"], ["create_entity", "add_field", "alter_field"])
        self.assertNotIn("add_field", declared["unsupported"])
        self.assertNotIn("alter_field", declared["unsupported"])
        # A runtime session has no schema-mutation surface at all,
        # `add_field` included (same authority boundary `create_collection`
        # already enforces).
        self.assertFalse(hasattr(self.runtime, "add_field"))

        self.dev.add_field("things", "score", "integer")
        self.runtime.insert("things", {"name": "a", "score": 5})
        self.assertEqual(self.runtime.read("things", filters=[Filter("score", "eq", 5)])[0]["name"], "a")

        with self.assertRaises(ConflictError):
            self.dev.add_field("things", "score", "integer")
        with self.assertRaises(NotFoundError):
            self.dev.add_field("no_such_collection", "x", "text")
        with self.assertRaises(ValidationError):
            self.dev.add_field("things", "bad type", "integer")
        with self.assertRaises(ValidationError):
            self.dev.add_field("things", "unsupported_type_field", "not_a_type")

    def test_add_field_respects_the_max_fields_shape_bound(self):
        # Q1-D11-consistent classification (cell.py::add_field's own
        # comment): the post-add field count mirrors the same fixed shape
        # bound `create_collection`'s own field-count check already
        # enforces -- `ValidationError`, not `ResourceLimitError` (keeps
        # `test_limit_class_vocabulary.py`'s own AST-scanned call-site
        # count unaffected by this WP, per P3 WP-1 round 2 instruction #7).
        config = FoundationConfig(max_fields=2)
        control = ControlPlane("synthetic-test-pepper-0123456789", config)
        control.provision_application("narrow_add_field")
        dev_id, dev_secret = control.issue_credential("narrow_add_field", Role.DEVELOPER)
        dev = MitateDataService(control).open_session(dev_secret)
        dev.create_collection("full", {"a": "text", "b": "text"})
        with self.assertRaises(ValidationError):
            dev.add_field("full", "c", "text")

    def test_create_entity_defaults_to_a_base_id_field_when_fields_omitted(self):
        # P3 WP-1 round 2 instruction #6: contract `SchemaOperationRequest.
        # fields` is optional for `create_entity`. `create_collection`
        # itself is UNCHANGED -- it keeps rejecting an empty/missing
        # `fields` outright for every existing caller.
        self.dev.create_entity("bare")
        self.runtime.insert("bare", {"id": 1})
        self.assertEqual(self.runtime.read("bare")[0]["id"], 1)
        with self.assertRaises(ValidationError):
            self.dev.create_collection("still_strict", {})
        self.assertFalse(hasattr(self.runtime, "create_entity"))

    def test_delete_confirmation_phrase_is_invalidated_by_a_subsequent_add_field(self):
        # P3 WP-1 round 2 instruction #5: `add_field` is "another schema
        # change" on an existing collection -- the delete confirmation
        # phrase must now include a schema-revision fingerprint
        # (`cell._delete_confirmation_phrase`) so a phrase obtained BEFORE
        # a schema change cannot be replayed AFTER one.
        self.dev.create_collection("gated_by_revision", {"title": "text"})
        self.runtime.insert("gated_by_revision", {"title": "keep-me"})

        with self.assertRaises(DestructiveConfirmationRequired) as ctx:
            self.runtime.delete("gated_by_revision", [Filter("title", "eq", "keep-me")])
        stale_phrase = ctx.exception.details["required_confirmation"]
        self.assertIn("@schema_revision=", stale_phrase)

        self.dev.add_field("gated_by_revision", "extra", "text")

        # The stale phrase (issued before `add_field`) must be refused --
        # NOT silently accepted -- even though its `@where=` digest still
        # matches the same filters.
        with self.assertRaises(DestructiveConfirmationRequired):
            self.runtime.delete("gated_by_revision", [Filter("title", "eq", "keep-me")],
                                destructive=True, confirm=stale_phrase)
        self.assertEqual(self.runtime.read("gated_by_revision")[0]["title"], "keep-me")

        # A freshly recomputed phrase (post-`add_field`) works and differs
        # from the stale one.
        with self.assertRaises(DestructiveConfirmationRequired) as ctx2:
            self.runtime.delete("gated_by_revision", [Filter("title", "eq", "keep-me")])
        fresh_phrase = ctx2.exception.details["required_confirmation"]
        self.assertNotEqual(fresh_phrase, stale_phrase)
        result = self.runtime.delete("gated_by_revision", [Filter("title", "eq", "keep-me")],
                                     destructive=True, confirm=fresh_phrase)
        self.assertEqual(result, {"deleted": 1})

    def test_sqlite_backend_still_round_trips_an_embedded_nul_byte(self):
        # P3 WP-1 round 2 instruction #1: PostgreSQL's own backend
        # deterministically REJECTS an embedded NUL byte
        # (`backend_postgres.PostgresBackend.encode_value`) -- the SQLite
        # backend's own pre-existing round-trip-accepts behavior for the
        # identical payload (the common conformance corpus's own
        # `nul_byte = "value\x00tail"`, conformance-tests/payloads.py)
        # must NOT change. This pins that non-change directly.
        self.dev.create_collection("nul_ok", {"value": "text"})
        self.runtime.insert("nul_ok", {"value": "value\x00tail"})
        self.assertEqual(self.runtime.read("nul_ok")[0]["value"], "value\x00tail")

    def test_null_value_can_be_written_and_filtered_on_the_sqlite_backend(self):
        # M-5 (independent review round 2): NULL is a valid value for any
        # declared field type (no `NOT NULL` constraint exists anywhere in
        # this foundation) -- pinned here on the SQLite backend as the
        # regression baseline the PostgreSQL backend's own equivalent test
        # (`tests/test_postgres.py`) is held to.
        self.dev.create_collection("nullable", {"title": "text", "rank": "integer"})
        self.runtime.insert("nullable", {"title": None, "rank": 1})
        self.assertIsNone(self.runtime.read("nullable")[0]["title"])
        # An `eq` filter against `None` must not raise (this is the actual
        # regression: pre-fix, this backend's own PostgreSQL counterpart
        # rejected `None` outright at the domain gate for ANY use,
        # including a filter value) -- ordinary SQL three-valued-logic
        # semantics apply (`title = NULL` is never true, even for a NULL
        # row, on any SQL engine including SQLite), so this correctly
        # returns no rows, not the NULL row itself (`is_null` -- a real,
        # different operator this foundation declares `unsupported` --
        # would be needed for that, and is out of this fix's scope).
        self.assertEqual(self.runtime.read("nullable", filters=[Filter("title", "eq", None)]), [])
        self.assertEqual(self.runtime.read("nullable", filters=[Filter("rank", "eq", 1)])[0]["title"], None)

    def test_sqlite_backend_rejects_out_of_range_integer_deterministically_and_transact_recovers(self):
        # M-7 (independent review round 2, defect fix -- see
        # `backend_sqlite.SQLiteBackend.encode_value`'s own comment for
        # why this is a genuine, deliberate CHANGE to this backend's
        # external behavior, not a preserved quirk): before this fix,
        # `10 ** 30` escaped as a raw `OverflowError` (not a
        # `sqlite3.Error`), which `cell.py::transact`'s own `except`
        # clause did not list -- leaving the connection's `BEGIN`
        # transaction open FOREVER and wedging every subsequent
        # `transact()` call on the SAME cell with `sqlite3.
        # OperationalError: cannot start a transaction within a
        # transaction`. This pins BOTH halves: the deterministic
        # rejection, AND that `transact()` keeps working immediately
        # afterward.
        self.dev.create_collection("oob_sqlite", {"n": "integer"})
        with self.assertRaises(ValidationError):
            self.runtime.transact([
                {"type": "insert", "collection": "oob_sqlite", "values": {"n": 10 ** 30}},
            ])
        # The connection must not be wedged: a normal transact() right
        # after must succeed (this is the exact failure mode that used to
        # repeat forever once triggered).
        result = self.runtime.transact([
            {"type": "insert", "collection": "oob_sqlite", "values": {"n": 1}},
        ])
        self.assertEqual(len(result), 1)
        self.assertEqual(self.runtime.read("oob_sqlite")[0]["n"], 1)
        # Also reachable via plain `insert()` (not just `transact()`).
        with self.assertRaises(ValidationError):
            self.runtime.insert("oob_sqlite", {"n": -(10 ** 30)})
        self.runtime.insert("oob_sqlite", {"n": 2})
        self.assertEqual(len(self.runtime.read("oob_sqlite")), 2)

    def test_provisioning_facade_rename_and_duplicate_provision_is_a_safe_conflict(self):
        # R-3/WP-0 m-8: `ControlPlane` is the backward-compatible alias of
        # the renamed `ProvisioningFacade` (`service.py`); both names must
        # refer to the exact same class. Re-provisioning an already-
        # provisioned application_id must land on this foundation's own
        # `errors.FoundationError` hierarchy (`ConflictError`), not an
        # unclassified bare `ValueError`.
        self.assertIs(ControlPlane, ProvisioningFacade)
        with self.assertRaises(ConflictError):
            self.control.provision_application("app_a")

    def test_audit_events_are_append_only_and_secret_free(self):
        self.dev.create_collection("notes", {"title": "text"})
        self.runtime.insert("notes", {"title": "synthetic-row-value"})
        events = self.control.audit.snapshot()
        self.assertGreaterEqual(len(events), 3)
        rendered = repr(events)
        self.assertNotIn(self.dev_secret, rendered)
        self.assertNotIn(self.runtime_secret, rendered)
        self.assertNotIn("synthetic-row-value", rendered)
        self.assertFalse(hasattr(self.runtime, "audit"))
        self.control.audit.record("test", detail=self.runtime_secret + " SELECT secret")
        self.assertEqual(self.control.audit.snapshot()[-1].detail, "unspecified")

    # =======================================================================
    # Phase 6 WP-3 (design docs/design/PHASE6_CONTRACT_160_CLIENT_
    # DISCOVERY_V1.md D-3): declared-type registry -- SQLite/in-process
    # parity half of `test_postgres.py`'s own identically-purposed suite.
    # Non-vacuity requirement (work order §0.1 item 1, WP-3 completion
    # condition 13/non-vacuity note): the choke point must be real here
    # too -- `backend_sqlite.SQLiteBackend.field_domains` returns all-
    # `None` domains (no live PostgreSQL-style enforcement at all), so
    # this backend's own defence-in-depth layer never runs; a mutation
    # that removed the cell-layer choke point entirely would only be
    # caught by exactly these tests.
    # =======================================================================

    def test_declared_type_registry_round_trips_every_contract_type_on_sqlite(self):
        from mitatedb_api.field_types import CONTRACT_TYPE_TO_FOUNDATION_TYPE
        contract_types = {
            "s": "string", "i": "integer", "n": "number", "b": "boolean",
            "o": "object", "arr": "array", "j": "json",
        }
        fields = {name: CONTRACT_TYPE_TO_FOUNDATION_TYPE[t] for name, t in contract_types.items()}
        self.dev.create_entity("typed_things", fields=fields, field_types=contract_types)
        values = {
            "s": "hello", "i": 42, "n": 3.5, "b": True,
            "o": {"a": 1, "b": [1, 2]}, "arr": [1, "two", {"three": 3}],
            "j": "a plain string written to a json field",
        }
        self.runtime.insert("typed_things", values)
        rows = self.runtime.read("typed_things")
        self.assertEqual(len(rows), 1)
        for key, expected in values.items():
            self.assertEqual(rows[0][key], expected, f"{key}: expected {expected!r}, got {rows[0][key]!r}")
        self.assertIs(rows[0]["b"], True)  # not 1 -- a real JSON boolean

    def test_declared_type_registry_rejects_mismatched_values_on_sqlite(self):
        from mitatedb_api.field_types import CONTRACT_TYPE_TO_FOUNDATION_TYPE
        contract_types = {
            "s": "string", "i": "integer", "n": "number", "b": "boolean",
            "o": "object", "arr": "array",
        }
        fields = {name: CONTRACT_TYPE_TO_FOUNDATION_TYPE[t] for name, t in contract_types.items()}
        self.dev.create_entity("typed_negatives", fields=fields, field_types=contract_types)
        bad_values = {"s": 123, "i": "abc", "n": "abc", "b": 7, "o": [1, 2], "arr": {"a": 1}}
        for field, bad_value in bad_values.items():
            with self.assertRaises(ValidationError):
                self.runtime.insert("typed_negatives", {field: bad_value})
        self.assertEqual(self.runtime.read("typed_negatives"), [])

    def test_declared_boolean_rejects_int_zero_and_one_on_sqlite(self):
        self.dev.create_entity("bool_strict", fields={"flag": "boolean"}, field_types={"flag": "boolean"})
        for bad in (0, 1, 7):
            with self.assertRaises(ValidationError):
                self.runtime.insert("bool_strict", {"flag": bad})
        self.runtime.insert("bool_strict", {"flag": False})
        self.assertIs(self.runtime.read("bool_strict")[0]["flag"], False)

    def test_catalog_reports_four_keys_and_undeclared_fields_default_to_json_on_sqlite(self):
        self.dev.create_entity(
            "catalog_probe", fields={"typed": "integer", "untyped": "json"}, field_types={"typed": "integer"})
        entries = self.runtime.catalog()
        entry = next(e for e in entries if e["entity"] == "catalog_probe")
        # Phase 9 WP-3a (design docs/design/
        # PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md D-2 (1)):
        # `field_constraints` joined this same-commit as `constraint_
        # declarations` flipping to `enabled` -- four keys now, not three.
        self.assertEqual(set(entry.keys()), {"entity", "fields", "field_types", "field_constraints"})
        self.assertEqual(set(entry["fields"]), {"typed", "untyped"})
        self.assertEqual(set(entry["field_types"]), set(entry["fields"]))
        self.assertEqual(set(entry["field_constraints"]), set(entry["fields"]))
        self.assertEqual(entry["field_types"]["typed"], "integer")
        self.assertEqual(entry["field_types"]["untyped"], "json")


if __name__ == "__main__":
    unittest.main()
