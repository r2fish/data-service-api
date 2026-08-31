"""Bootstrap/reset ceremony core (`control_plane.bootstrap_control_credential`
/ `reset_control_credentials`) direct tests (WP-4, design v1.2 R-6).

Exercised against BOTH the in-memory `control_auth.ControlCredentialStore`
and the real-PostgreSQL `control_credential_store_postgres.
PostgresControlCredentialStore` (contract `control_plane.bootstrap`/`reset`
apply identically regardless of backend) -- no CLI entry point exists yet
(design R-6/M-5: the `ops` module is WP-5's own addition); this module
drives the ceremony CORE functions directly, exactly as a future CLI or
in-process adapter will.
"""
from __future__ import annotations

from typing import Iterator

import pytest

from .control_plane_harness import control_platform  # noqa: F401 (fixture)
from mitatedb_api.control_audit import ControlAuditSink, insert_control_audit_row
from mitatedb_api.control_auth import ControlCredentialStore, _InMemoryWork
from mitatedb_api.control_credential_store_postgres import PostgresControlCredentialStore
from mitatedb_api.control_plane import (bootstrap_control_credential, reset_control_credentials,
                                        issue_audit_credential_ceremony, _reset_confirmation_phrase)
from mitatedb_api.errors import ConflictError, DestructiveConfirmationRequired, ValidationError

_PEPPER = "ceremony-test-pepper-value-here"


class _InMemoryHarness:
    def __init__(self) -> None:
        self.store = ControlCredentialStore(_PEPPER)
        self.audit = ControlAuditSink()

    def unit_of_work(self):
        from contextlib import contextmanager

        @contextmanager
        def _cm():
            work = _InMemoryWork()
            try:
                yield work
            except BaseException:
                work.rollback()
                raise
        return _cm()

    def append_audit(self, *, work=None, **fields):
        return self.audit.append(work=work, **fields)

    def audit_events(self):
        return self.audit.snapshot()


class _PostgresHarness:
    def __init__(self, control_platform) -> None:
        self.store = PostgresControlCredentialStore(
            control_platform.controlplane_dsn, pepper=_PEPPER, schema=control_platform.registry_schema)
        self._schema = control_platform.registry_schema
        self._reader_dsn = control_platform.provision_dsn
        self._dsn = control_platform.controlplane_dsn

    def unit_of_work(self):
        import psycopg
        from contextlib import contextmanager

        @contextmanager
        def _cm():
            conn = psycopg.connect(self._dsn, connect_timeout=5)
            try:
                yield conn
                conn.commit()
            except BaseException:
                conn.rollback()
                raise
            finally:
                conn.close()
        return _cm()

    def append_audit(self, *, work, **fields):
        return insert_control_audit_row(work, self._schema, **fields)

    def audit_events(self):
        from mitatedb_api.control_audit import read_control_audit_events
        return read_control_audit_events(self._reader_dsn, self._schema)

    def clear(self) -> None:
        import psycopg
        conn = psycopg.connect(self._reader_dsn, autocommit=True)
        try:
            with conn.cursor() as cur:
                cur.execute(f"DELETE FROM {self._schema}.control_credentials")
                cur.execute(f"DELETE FROM {self._schema}.control_audit")
        finally:
            conn.close()


@pytest.fixture
def memory_harness() -> _InMemoryHarness:
    return _InMemoryHarness()


@pytest.fixture
def postgres_harness(control_platform) -> Iterator[_PostgresHarness]:
    harness = _PostgresHarness(control_platform)
    yield harness
    harness.clear()


HARNESS_NAMES = ["memory", "postgres"]


def _harness(name, memory_harness, postgres_harness):
    return memory_harness if name == "memory" else postgres_harness


@pytest.mark.parametrize("name", HARNESS_NAMES)
def test_bootstrap_issues_a_must_rotate_credential_and_records_canonical_audit(name, memory_harness, postgres_harness) -> None:
    harness = _harness(name, memory_harness, postgres_harness)
    with harness.unit_of_work() as work:
        credential_id, secret = bootstrap_control_credential(harness.store, harness.append_audit, work=work)
    principal = harness.store.authenticate(credential_id, secret)
    assert principal.must_rotate is True

    events = harness.audit_events()
    assert len(events) == 1
    event = events[0] if name == "memory" else events[0]
    operation = event.operation if name == "memory" else event["operation"]
    outcome = event.outcome if name == "memory" else event["outcome"]
    assert operation == "bootstrap_control_credential"
    assert outcome == "allow"


@pytest.mark.parametrize("name", HARNESS_NAMES)
def test_bootstrap_refuses_when_any_control_credential_row_exists_even_if_revoked(name, memory_harness, postgres_harness) -> None:
    harness = _harness(name, memory_harness, postgres_harness)
    with harness.unit_of_work() as work:
        credential_id, _secret = bootstrap_control_credential(harness.store, harness.append_audit, work=work)
    harness.store.revoke(credential_id)  # even fully revoked -- contract text is "while a control credential exists"
    with pytest.raises(ConflictError):
        with harness.unit_of_work() as work:
            bootstrap_control_credential(harness.store, harness.append_audit, work=work)


@pytest.mark.parametrize("name", HARNESS_NAMES)
def test_reset_requires_exact_declare_and_echo_confirmation(name, memory_harness, postgres_harness) -> None:
    harness = _harness(name, memory_harness, postgres_harness)
    with harness.unit_of_work() as work:
        old_id, old_secret = bootstrap_control_credential(harness.store, harness.append_audit, work=work)

    with pytest.raises(DestructiveConfirmationRequired) as excinfo:
        with harness.unit_of_work() as work:
            reset_control_credentials(harness.store, harness.append_audit, work=work, destructive=False, confirmation=None)
    details = excinfo.value.details
    for key in ("required_confirmation", "consequence", "reversible_alternative", "recovery"):
        assert key in details
    phrase = details["required_confirmation"]

    # Non-exact confirmation refused (no prefix/substring acceptance).
    with pytest.raises(DestructiveConfirmationRequired):
        with harness.unit_of_work() as work:
            reset_control_credentials(harness.store, harness.append_audit, work=work,
                                      destructive=True, confirmation=phrase[:-1])

    # The old credential must still be alive -- the denied attempts must
    # not have partially executed.
    principal = harness.store.authenticate(old_id, old_secret)
    assert principal.must_rotate is True

    with harness.unit_of_work() as work:
        new_id, new_secret = reset_control_credentials(harness.store, harness.append_audit, work=work,
                                                        destructive=True, confirmation=phrase)
    assert new_id != old_id

    with pytest.raises(Exception):
        harness.store.authenticate(old_id, old_secret)
    new_principal = harness.store.authenticate(new_id, new_secret)
    assert new_principal.must_rotate is True


@pytest.mark.parametrize("name", HARNESS_NAMES)
def test_reset_revokes_every_prior_credential_including_already_disabled_ones(name, memory_harness, postgres_harness) -> None:
    harness = _harness(name, memory_harness, postgres_harness)
    with harness.unit_of_work() as work:
        a, _secret_a = bootstrap_control_credential(harness.store, harness.append_audit, work=work)
    b, secret_b = harness.store.issue()
    harness.store.disable(b)

    # `locked_for_update` requires an open transaction on the Postgres
    # store; `list_all()` is a plain, lock-free read that suffices here for
    # phrase computation in this test (the ceremony itself takes the real
    # lock internally when it runs).
    active_ids = [row[0] for row in harness.store.list_all() if row[1] and not row[2]]
    phrase = _reset_confirmation_phrase(active_ids)

    with harness.unit_of_work() as work:
        reset_control_credentials(harness.store, harness.append_audit, work=work, destructive=True, confirmation=phrase)

    for credential_id in (a, b):
        enabled, revoked, _must_rotate = harness.store.get_state(credential_id)
        assert revoked is True


@pytest.mark.parametrize("name", HARNESS_NAMES)
def test_reset_confirmation_phrase_changes_when_active_set_changes(name, memory_harness, postgres_harness) -> None:
    harness = _harness(name, memory_harness, postgres_harness)
    with harness.unit_of_work() as work:
        credential_id, _secret = bootstrap_control_credential(harness.store, harness.append_audit, work=work)

    with pytest.raises(DestructiveConfirmationRequired) as excinfo:
        with harness.unit_of_work() as work:
            reset_control_credentials(harness.store, harness.append_audit, work=work, destructive=False, confirmation=None)
    stale_phrase = excinfo.value.details["required_confirmation"]

    # Issue a second control credential directly (bypassing the service
    # layer's own role=control in-band refusal, which is a POLICY decision
    # this store-level ceremony test is not exercising) -- the active set
    # changes, so the previously-obtained phrase must now be stale.
    harness.store.issue()

    with pytest.raises(DestructiveConfirmationRequired) as excinfo2:
        with harness.unit_of_work() as work:
            reset_control_credentials(harness.store, harness.append_audit, work=work,
                                      destructive=True, confirmation=stale_phrase)
    assert excinfo2.value.details["required_confirmation"] != stale_phrase


@pytest.mark.parametrize("name", HARNESS_NAMES)
def test_reset_rejects_non_boolean_destructive_as_a_shape_defect(name, memory_harness, postgres_harness) -> None:
    harness = _harness(name, memory_harness, postgres_harness)
    with harness.unit_of_work() as work:
        bootstrap_control_credential(harness.store, harness.append_audit, work=work)
    with pytest.raises(ValidationError):
        with harness.unit_of_work() as work:
            reset_control_credentials(harness.store, harness.append_audit, work=work,
                                      destructive="true", confirmation="whatever")


# ===========================================================================
# Phase 3.5 WP-5 (design docs/design/PHASE35_CROSS_ENTITY_AND_CONTRACT_130_
# V1.md §4/§1-D, P35-D12): out-of-band audit-credential issuance ceremony,
# and `reset`'s own role-agnostic revocation of audit rows too.
# ===========================================================================


@pytest.mark.parametrize("name", HARNESS_NAMES)
def test_issue_audit_credential_ceremony_distributes_a_must_rotate_false_audit_credential(name, memory_harness, postgres_harness) -> None:
    """Issues AND rotates in one transaction before returning a secret, so
    the returned secret's `must_rotate` is already `False` (design §4 M-1:
    no in-band self-rotate path exists for an audit principal, so the
    ceremony itself must complete the rotate half)."""
    harness = _harness(name, memory_harness, postgres_harness)
    with harness.unit_of_work() as work:
        credential_id, secret = issue_audit_credential_ceremony(harness.store, harness.append_audit, work=work)
    principal = harness.store.authenticate(credential_id, secret)
    assert principal.credential_id == credential_id
    assert principal.must_rotate is False
    assert principal.role == "audit"

    events = harness.audit_events()
    assert len(events) == 1
    event = events[0]
    operation = event.operation if name == "memory" else event["operation"]
    outcome = event.outcome if name == "memory" else event["outcome"]
    target_id = event.target_id if name == "memory" else event["target_id"]
    assert operation == "issue_audit_credential"
    assert outcome == "allow"
    assert target_id == credential_id


@pytest.mark.parametrize("name", HARNESS_NAMES)
def test_issue_audit_credential_ceremony_is_not_a_once_only_ritual(name, memory_harness, postgres_harness) -> None:
    """Unlike `bootstrap`, any number of audit credentials may be issued --
    there is no "first row" invariant to protect here, and it does not
    refuse merely because a control credential already exists."""
    harness = _harness(name, memory_harness, postgres_harness)
    with harness.unit_of_work() as work:
        bootstrap_control_credential(harness.store, harness.append_audit, work=work)
    with harness.unit_of_work() as work:
        first_id, _first_secret = issue_audit_credential_ceremony(harness.store, harness.append_audit, work=work)
    with harness.unit_of_work() as work:
        second_id, _second_secret = issue_audit_credential_ceremony(harness.store, harness.append_audit, work=work)
    assert first_id != second_id


@pytest.mark.parametrize("name", HARNESS_NAMES)
def test_reset_revokes_an_audit_credential_too(name, memory_harness, postgres_harness) -> None:
    """`reset` stays role-agnostic (design §4, P35-D5-adjacent): an
    orphan/live `role="audit"` row is revoked by `reset` exactly like every
    `role="control"` row -- the safe-side choice, no stray audit credential
    survives a reset behind an operator's back."""
    harness = _harness(name, memory_harness, postgres_harness)
    with harness.unit_of_work() as work:
        control_id, control_secret = bootstrap_control_credential(harness.store, harness.append_audit, work=work)
    with harness.unit_of_work() as work:
        audit_id, audit_secret = issue_audit_credential_ceremony(harness.store, harness.append_audit, work=work)

    active_ids = [row[0] for row in harness.store.list_all() if row[1] and not row[2]]
    phrase = _reset_confirmation_phrase(active_ids)
    with harness.unit_of_work() as work:
        new_id, new_secret = reset_control_credentials(harness.store, harness.append_audit, work=work, destructive=True, confirmation=phrase)

    # Both prior rows -- the original control credential AND the audit
    # credential -- are dead; only the freshly reset credential survives.
    with pytest.raises(Exception):
        harness.store.authenticate(audit_id, audit_secret)
    with pytest.raises(Exception):
        harness.store.authenticate(control_id, control_secret)
    new_principal = harness.store.authenticate(new_id, new_secret)
    assert new_principal.role == "control"


@pytest.mark.parametrize("name", HARNESS_NAMES)
def test_orphan_audit_row_with_no_control_row_blocks_bootstrap_but_reset_recovers(name, memory_harness, postgres_harness) -> None:
    """Review m-4: the documented recovery path -- an audit credential
    issued with NO `role="control"` row ever existing at all still blocks
    `bootstrap` (`has_any(include_revoked=True)` counts ANY control-table
    row, `role` regardless -- contract text is "while a control credential
    exists", and this table's own rows are never distinguished from an
    "audit credential" by `bootstrap`'s own existence check). `reset`
    recovers from this state exactly as it does from every other lockout --
    revoking the orphan audit row too (role-agnostic, see the sibling test
    above) and minting one fresh `role="control"` credential."""
    harness = _harness(name, memory_harness, postgres_harness)

    # No control credential is ever bootstrapped in this test at all --
    # `issue_audit_credential_ceremony` is the ONLY control-table row this
    # store ever holds before `reset` runs.
    with harness.unit_of_work() as work:
        audit_id, audit_secret = issue_audit_credential_ceremony(harness.store, harness.append_audit, work=work)

    with pytest.raises(ConflictError):
        with harness.unit_of_work() as work:
            bootstrap_control_credential(harness.store, harness.append_audit, work=work)

    # The orphan audit row is still live -- bootstrap's own refusal did not
    # touch it.
    principal = harness.store.authenticate(audit_id, audit_secret)
    assert principal.role == "audit"

    active_ids = [row[0] for row in harness.store.list_all() if row[1] and not row[2]]
    phrase = _reset_confirmation_phrase(active_ids)
    with harness.unit_of_work() as work:
        new_id, new_secret = reset_control_credentials(
            harness.store, harness.append_audit, work=work, destructive=True, confirmation=phrase)

    with pytest.raises(Exception):
        harness.store.authenticate(audit_id, audit_secret)
    new_principal = harness.store.authenticate(new_id, new_secret)
    assert new_principal.role == "control"
    assert new_principal.must_rotate is True
