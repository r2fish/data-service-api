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
        self.dev = self.service.open_session(self.dev_id, self.dev_secret)
        self.runtime = self.service.open_session(self.runtime_id, self.runtime_secret)

    def test_developer_schema_and_runtime_crud(self):
        self.dev.create_collection("notes", {"title": "text", "rank": "integer"})
        self.runtime.insert("notes", {"title": "hello", "rank": 1})
        self.assertEqual(self.runtime.read("notes", filters=[Filter("rank", "eq", 1)])[0]["title"], "hello")
        self.assertFalse(hasattr(self.runtime, "create_collection"))

    def test_application_scope_is_server_bound(self):
        self.dev.create_collection("notes", {"title": "text"})
        self.runtime.insert("notes", {"title": "private"})
        other_dev = self.service.open_session(self.other_dev_id, self.other_dev_secret)
        other_dev.create_collection("notes", {"title": "text"})
        other = self.service.open_session(self.other_id, self.other_secret)
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

    def test_disable_revoke_and_unavailable_state_fail_closed(self):
        self.dev.create_collection("notes", {"title": "text"})
        self.runtime.insert("notes", {"title": "before-revoke"})
        self.control.revoke_credential(self.runtime_id)
        with self.assertRaises(AuthenticationError):
            self.runtime.read("notes")
        with self.assertRaises(AuthenticationError):
            self.service.open_session(self.runtime_id, self.runtime_secret)
        self.control.disable_application("app_a")
        with self.assertRaises(AuthenticationError):
            self.dev.read("notes")
        with self.assertRaises(AuthenticationError):
            self.service.open_session(self.dev_id, self.dev_secret)
        self.control.credentials.enable_application("app_a")
        self.control.credentials.authorization_state_available = False
        with self.assertRaises(AuthorizationStateUnavailable):
            self.service.open_session(self.dev_id, self.dev_secret)

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
        dev = MitateDataService(control).open_session(dev_id, dev_secret)
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
        dev = MitateDataService(control).open_session(dev_id, dev_secret)
        runtime = MitateDataService(control).open_session(runtime_id, runtime_secret)
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
        dev = MitateDataService(control).open_session(dev_id, dev_secret)
        runtime = MitateDataService(control).open_session(runtime_id, runtime_secret)

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
        self.assertEqual(declared["operations"], ["create_entity", "add_field"])
        self.assertNotIn("add_field", declared["unsupported"])
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
        dev = MitateDataService(control).open_session(dev_id, dev_secret)
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


if __name__ == "__main__":
    unittest.main()
