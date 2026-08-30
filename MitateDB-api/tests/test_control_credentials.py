"""Parity tests: `control_auth.ControlCredentialStore` (in-memory) vs
`control_credential_store_postgres.PostgresControlCredentialStore`
(WP-4, design v1.2 R-4 item 1: "control credential store 二重実装 + parity").

Parity basis is CONTRACT behaviour (mirroring WP-2's own precedent for the
application-credential store pair), not any one implementation's internal
detail: enabled/revoked independent booleans, revoke is terminal (no
un-revoke path), `enable` reverses `disable` only, `must_rotate` starts
`True` only when the caller asks for it (the bootstrap/reset ceremony's own
choice, not this store's default), and a rotated credential's own digest
changes while its `credential_id` does not.
"""
from __future__ import annotations

import secrets
from typing import Iterator

import pytest

from .control_plane_harness import control_platform  # noqa: F401 (fixture)
from mitatedb_api.control_auth import ControlCredentialStore
from mitatedb_api.control_credential_store_postgres import PostgresControlCredentialStore
from mitatedb_api.errors import AuthenticationError, NotFoundError

_PEPPER = "control-credential-parity-pepper-value"


def _memory_store() -> ControlCredentialStore:
    return ControlCredentialStore(_PEPPER)


@pytest.fixture
def pg_store(control_platform) -> Iterator[PostgresControlCredentialStore]:
    store = PostgresControlCredentialStore(control_platform.controlplane_dsn, pepper=_PEPPER,
                                           schema=control_platform.registry_schema)
    yield store
    # Clean the table between tests sharing the module-scoped platform.
    import psycopg
    conn = psycopg.connect(control_platform.provision_dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute(f"DELETE FROM {control_platform.registry_schema}.control_credentials")
    finally:
        conn.close()


PARAM_STORES = ["memory", "postgres"]


def _make(kind, pg_store):
    return _memory_store() if kind == "memory" else pg_store


@pytest.mark.parametrize("kind", PARAM_STORES)
def test_issue_then_authenticate_succeeds(kind, pg_store) -> None:
    store = _make(kind, pg_store)
    credential_id, secret = store.issue()
    principal = store.authenticate(credential_id, secret)
    assert principal.credential_id == credential_id
    assert principal.must_rotate is False


@pytest.mark.parametrize("kind", PARAM_STORES)
def test_issue_with_must_rotate_true_is_reported_on_authenticate(kind, pg_store) -> None:
    store = _make(kind, pg_store)
    credential_id, secret = store.issue(must_rotate=True)
    principal = store.authenticate(credential_id, secret)
    assert principal.must_rotate is True


@pytest.mark.parametrize("kind", PARAM_STORES)
def test_wrong_secret_is_rejected(kind, pg_store) -> None:
    store = _make(kind, pg_store)
    credential_id, _secret = store.issue()
    with pytest.raises(AuthenticationError):
        store.authenticate(credential_id, "definitely-wrong")


@pytest.mark.parametrize("kind", PARAM_STORES)
def test_unknown_credential_id_is_rejected(kind, pg_store) -> None:
    store = _make(kind, pg_store)
    with pytest.raises(AuthenticationError):
        store.authenticate("no-such-id", "whatever")


@pytest.mark.parametrize("kind", PARAM_STORES)
def test_revoke_is_terminal_enable_cannot_resurrect_it(kind, pg_store) -> None:
    store = _make(kind, pg_store)
    credential_id, secret = store.issue()
    store.revoke(credential_id)
    with pytest.raises(AuthenticationError):
        store.authenticate(credential_id, secret)
    store.enable(credential_id)
    with pytest.raises(AuthenticationError):
        store.authenticate(credential_id, secret)
    enabled, revoked, _must_rotate = store.get_state(credential_id)
    assert revoked is True
    assert enabled is True  # enable() still flips the flag itself...
    # ...but authenticate/revoked-gate still refuses it (the actual invariant).


@pytest.mark.parametrize("kind", PARAM_STORES)
def test_disable_then_enable_restores_authentication(kind, pg_store) -> None:
    store = _make(kind, pg_store)
    credential_id, secret = store.issue()
    store.disable(credential_id)
    with pytest.raises(AuthenticationError):
        store.authenticate(credential_id, secret)
    store.enable(credential_id)
    principal = store.authenticate(credential_id, secret)
    assert principal.credential_id == credential_id


@pytest.mark.parametrize("kind", PARAM_STORES)
def test_rotate_changes_digest_and_clears_must_rotate(kind, pg_store) -> None:
    store = _make(kind, pg_store)
    credential_id, _old_secret = store.issue(must_rotate=True)
    new_secret = store.rotate(credential_id)
    principal = store.authenticate(credential_id, new_secret)
    assert principal.must_rotate is False
    with pytest.raises(AuthenticationError):
        store.authenticate(credential_id, _old_secret)


@pytest.mark.parametrize("kind", PARAM_STORES)
def test_revoke_unknown_id_fails_closed(kind, pg_store) -> None:
    store = _make(kind, pg_store)
    with pytest.raises(NotFoundError):
        store.revoke("no-such-id")


@pytest.mark.parametrize("kind", PARAM_STORES)
def test_has_any_excludes_nothing_when_include_revoked_true(kind, pg_store) -> None:
    store = _make(kind, pg_store)
    assert store.has_any(include_revoked=True) is False
    credential_id, _secret = store.issue()
    store.revoke(credential_id)
    assert store.has_any(include_revoked=True) is True
    assert store.has_any(include_revoked=False) is False


@pytest.mark.parametrize("kind", PARAM_STORES)
def test_revoke_all_revokes_every_row_including_already_disabled(kind, pg_store) -> None:
    store = _make(kind, pg_store)
    a, secret_a = store.issue()
    b, secret_b = store.issue()
    store.disable(b)
    store.revoke_all()
    with pytest.raises(AuthenticationError):
        store.authenticate(a, secret_a)
    with pytest.raises(AuthenticationError):
        store.authenticate(b, secret_b)
    for credential_id in (a, b):
        _enabled, revoked, _must_rotate = store.get_state(credential_id)
        assert revoked is True


@pytest.mark.parametrize("kind", PARAM_STORES)
def test_list_all_reports_every_row_without_must_rotate(kind, pg_store) -> None:
    store = _make(kind, pg_store)
    a, _ = store.issue()
    b, _ = store.issue(must_rotate=True)
    rows = {row[0]: row for row in store.list_all()}
    assert set(rows) == {a, b}
    for credential_id, enabled, revoked in rows.values():
        assert isinstance(enabled, bool) and isinstance(revoked, bool)


# --------------------------------------------------------------------------
# Reviewer m-3: pepper-length fail-closed construction. The application
# credential stores (`auth.CredentialStore`/`credential_store_postgres.
# PostgresCredentialStore`) already have an equivalent test; the control
# credential store pair had the identical `len(pepper) < 16` guard in its
# own `__init__` but no test exercising it -- a mutation loosening that
# bound (e.g. `< 16` -> `< 1`) passed every other control-plane test
# unnoticed. `PostgresControlCredentialStore.__init__` validates the pepper
# BEFORE opening any connection, so this needs no real PostgreSQL server at
# all -- a placeholder DSN is never actually connected to.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("bad_pepper", ["", "short", "x" * 15, None, 12345])
def test_in_memory_control_store_rejects_a_pepper_shorter_than_16_characters(bad_pepper) -> None:
    with pytest.raises(ValueError):
        ControlCredentialStore(bad_pepper)


def test_in_memory_control_store_accepts_a_pepper_of_exactly_16_characters() -> None:
    ControlCredentialStore("x" * 16)  # must not raise


@pytest.mark.parametrize("bad_pepper", ["", "short", "x" * 15, None, 12345])
def test_postgres_control_store_rejects_a_pepper_shorter_than_16_characters(bad_pepper) -> None:
    with pytest.raises(ValueError):
        PostgresControlCredentialStore("dbname=unused-placeholder-never-connected", pepper=bad_pepper)


def test_postgres_control_store_accepts_a_pepper_of_exactly_16_characters() -> None:
    PostgresControlCredentialStore("dbname=unused-placeholder-never-connected", pepper="x" * 16)  # must not raise
