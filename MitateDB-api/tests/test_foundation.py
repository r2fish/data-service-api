import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from mitatedb_api import (ControlPlane, Filter, FoundationConfig,
                          MitateDataService, Role)
from mitatedb_api.errors import (AuthenticationError,
                                 AuthorizationStateUnavailable,
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

    def test_transaction_rolls_back(self):
        self.dev.create_collection("notes", {"title": "text"})
        with self.assertRaises(ValidationError):
            self.runtime.transact([
                {"type": "insert", "collection": "notes", "values": {"title": "first"}},
                {"type": "unsupported", "collection": "notes", "values": {"title": "second"}},
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

    def test_bounded_inputs_and_explicit_destructive_confirmation(self):
        config = FoundationConfig(max_batch_items=1)
        control = ControlPlane("synthetic-test-pepper-0123456789", config)
        control.provision_application("small")
        dev_id, dev_secret = control.issue_credential("small", Role.DEVELOPER)
        dev = MitateDataService(control).open_session(dev_id, dev_secret)
        dev.create_collection("notes", {"title": "text"})
        with self.assertRaises(ResourceLimitError):
            dev.transact([
                {"type": "insert", "collection": "notes", "values": {"title": "a"}},
                {"type": "insert", "collection": "notes", "values": {"title": "b"}},
            ])
        with self.assertRaises(ValidationError):
            dev.delete("notes", [], confirm=False)
        with self.assertRaises(ResourceLimitError):
            config.validate_request_size(config.max_request_bytes + 1)

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
