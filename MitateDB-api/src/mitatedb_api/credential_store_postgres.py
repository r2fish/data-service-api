"""`PostgresCredentialStore`: WP-2 (design v1.2 R-4/§3, "credential store
の二重実装") -- the same application-credential call surface as
`mitatedb_api.auth.CredentialStore` (`issue`/`revoke`/`disable`/`enable`/
`authenticate`/`assert_active`/`get_state`, plus `disable_application`/
`enable_application` for the application-level toggle the same store also
observes), backed by `mitatedb_registry.credentials`/`applications`
(migration `0002_registry_and_functions.sql`) instead of an in-memory dict.

This is a genuinely independent implementation, not a port of either
`auth.CredentialStore` or r2db-api's own `credential_store.py` (design R-2's
own closing paragraph, restated by WP-2's own instruction: "実装コードの複
製禁止 (二重独立実装の原則)"). Concretely, this file differs from both in
several structural respects:

- **Lookup key.** `auth.CredentialStore.authenticate` takes an explicit
  `(credential_id, secret)` pair and looks the row up BY `credential_id`
  (a plain dict key) -- this store does the identical thing, `SELECT ...
  WHERE credential_id = %s`, then compares the stored digest with
  `hmac.compare_digest`. r2db-api's own `PostgresCredentialStore` instead
  looks a credential up BY its computed verifier (`secret` alone, no
  caller-supplied id) -- a different lookup shape entirely, not merely a
  different SQL string for the same shape. This store's own shape was
  chosen to match `auth.CredentialStore`'s OWN existing call surface (the
  "同一 call surface" WP-2 actually requires is between this store and
  `auth.CredentialStore`, not between this store and r2db's).
- **No pooling, one connection per call.** Every method below opens a
  fresh `psycopg.connect(...)`, does its work, and closes it -- there is no
  persistent connection and no connection pool anywhere in this file. This
  is deliberate, not merely simple: WP-2 instruction #5 requires "DB 不達
  fail-closed" to be observable by pointing this store at an unreachable
  DSN and calling `authenticate`/`assert_active` -- with a fresh connection
  attempt on every call, ANY point of unreachability (never-up, or torn
  down between two calls) surfaces identically as a failed `psycopg.
  connect()`, with no separate "was the pool ever primed" state to reason
  about. This also keeps this store honest with the "no cache, ever"
  principle r2db-api's own module docstring names explicitly: every call
  reads PostgreSQL fresh, with nothing in this process remembering the
  previous answer.
- **Fail-closed, never fail-open.** A PostgreSQL connection failure OR a
  query failure while reading credential/application state is mapped to
  `errors.AuthorizationStateUnavailable` (this foundation's own existing
  fail-closed exception, `errors.py` -- the same one `auth.CredentialStore.
  authenticate`/`assert_active` already raise when their own `
  authorization_state_available` flag is `False`), never silently treated
  as "credential invalid" and never allowed to escape as a raw `psycopg.
  Error`. Every read path below funnels through exactly one `try/except
  psycopg.Error` each, so this is a structural property of the file, not a
  convention repeated ad hoc per method.
- **SQL composition discipline (R-2, this repository's own choke-point
  convention -- see `backend_postgres.py`'s identical `_execute`).** Every
  statement in this file is built with `psycopg.sql.SQL`/`sql.Identifier`/
  `sql.Placeholder` and passed through the single `_execute` choke point,
  which raises `TypeError` on anything that is not already a composed
  `psycopg.sql.SQL`/`Composed` object -- never an f-string or `%`-formatted
  plain string reaches `cursor.execute` from anywhere in this module.
  `schema`/table/column names below are fixed, code-authored literals
  (never client/request input); `schema` itself is validated with the
  same shared identifier allowlist `backend_postgres.py`/`cell.py` already
  use (`identifiers.validate_identifier`) purely so this repository's own
  tests can point this class at a throwaway-prefixed schema name (R-4/R-8
  "prefix 置換方式") -- it is never derived from client/request input.

Two configurations this class is actually used in, mirroring R-4's own
process-role separation (this WP wires neither into a running composition
root yet -- WP-3/WP-4 do that; this WP's own tests construct both
configurations directly):

1. **Read path -- the application-plane process** (future `mitatedb_api.
   main`, WP-3): constructed with a DSN authenticating as `mitatedbsvc_api`
   (migration 0002: `SELECT`-only on `applications`/`credentials`). Only
   `authenticate`/`assert_active`/`get_state` are ever exercised in this
   configuration; `issue`/`disable`/`enable`/`revoke`/`disable_application`/
   `enable_application` would fail at the database privilege level if ever
   called here (`InsufficientPrivilege`, not a special case this class
   handles -- it simply attempts the `INSERT`/`UPDATE` and lets PostgreSQL's
   own grant boundary refuse it, then maps that failure through the same
   generic `except psycopg.Error` every write method already has).
2. **Write path -- provisioning/control-plane tooling** (WP-2 instruction
   #2: "発行/失効は control plane の仕事 -- 本 WP では store の書込系は
   provisioning/テスト経路から使う形でよい"): constructed with a DSN
   authenticating as `mitatedbsvc_controlplane` (migration 0002: `SELECT`,
   `INSERT`, `UPDATE` on both tables). `tests/test_postgres.py` (the
   `_PostgresCredentialHarness`/parity tests and the dedicated grant-
   boundary tests below it) is the only caller today; a future WP-4
   `ControlPlaneService` is the eventual production caller, reusing these
   same methods rather than hand-rolling a second copy of this SQL
   (mirroring r2db-api's own `ops.py` reuse of its `credential_store.py`,
   independently arrived at here).

WP-2 review M-1 (blocker-adjacent finding): a bare `except psycopg.Error`
would fold PostgreSQL's own `InsufficientPrivilege` -- a PERMANENT grant/
role misconfiguration, e.g. this exact reader-configuration-1-calling-a-
write-method case, or a provisioning defect -- into the same fail-closed
bucket as a TRANSIENT unreachability (`errors.AuthorizationStateUnavailable`).
Every method below therefore catches `psycopg.errors.InsufficientPrivilege`
FIRST, before its own final `except psycopg.Error` backstop, and raises
`errors.StorageConfigurationError` instead -- see that class's own
docstring (`errors.py`) for why the two must never be the same class and
for this file's own proposed future HTTP mapping.

`schema` defaults to the real production schema name (`mitatedb_registry`,
matching `migrations/0002_registry_and_functions.sql`); it is a constructor
parameter purely so this repository's own tests -- which run the real
migration files with `mitatedb`/`mitatedb_registry` textually replaced by a
random throwaway prefix (R-4/R-8, `tests/test_postgres.py`'s own established
convention) -- can point this class at their own rewritten schema name.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import hmac
import os
import secrets
from typing import Optional

import psycopg
from psycopg import sql

from .auth import Principal, Role
from .errors import (AuthenticationError, AuthorizationStateUnavailable,
                     NotFoundError, StorageConfigurationError)
from .identifiers import validate_identifier
from .pool import BoundedConnectionPool

DEFAULT_SCHEMA = "mitatedb_registry"

_CREDENTIAL_PEPPER_ENV = "MITATEDB_CREDENTIAL_PEPPER"
_CONTROL_CREDENTIAL_PEPPER_ENV = "MITATEDB_CONTROL_CREDENTIAL_PEPPER"

# WP-2 review m-4: a fixed-length (32 bytes, matching this module's own
# `_digest`'s SHA-256 output), never-matching stand-in digest -- `authenticate`
# below always performs an `hmac.compare_digest` call against SOME 32-byte
# value, whether or not `credential_id` was actually found, so an unknown
# `credential_id` does not take a measurably cheaper code path than a known
# one that fails on the secret comparison. This value has no security
# property of its own (it is not derived from any pepper or secret) -- its
# only job is to keep the comparison's *shape* identical across both cases.
_DUMMY_DIGEST = hashlib.sha256(b"mitatedb-credential-store-timing-parity-dummy").digest()


def assert_pepper_separation(app_pepper: Optional[str], control_pepper: Optional[str]) -> None:
    """WP-2 instruction #4: detects the two peppers (`MITATEDB_CREDENTIAL_
    PEPPER` for application credentials, `MITATEDB_CONTROL_CREDENTIAL_
    PEPPER` for the future control-credential store, design v1.2 R-4)
    being configured identically. An operator who copy-pastes the same
    secret-manager value into both env var names would make an application
    credential's digest and a control credential's digest collide under
    the same underlying secret string -- silently punching a hole through
    R-4's "面別ストア分離" (credentials/control_credentials are separate
    tables reachable by separate process roles) via pepper reuse rather
    than any table/grant mistake.

    Deliberately a bare function, not a method on either store class: WP-2
    instruction #4 asks only for the DETECTION function plus its own unit
    test here -- "呼び出しは将来の composition root" (a future WP-3/WP-4
    process that constructs both an application-plane and a control-plane
    credential store in the same process is the actual caller; no such
    composition root exists yet in this WP). Raises `ValueError` (a
    configuration error, not a request-time `errors.FoundationError`) so a
    composition root can call this once at startup and let the process
    fail to start outright, mirroring how `auth.CredentialStore.__init__`
    already raises `ValueError` for a missing/too-short pepper rather than
    a `FoundationError`.

    A `None`/empty value on either side is not itself flagged here (each
    store's OWN constructor already fails closed on that independently --
    see `PostgresCredentialStore.__init__` below and `auth.CredentialStore.
    __init__`); this function's only job is the CROSS-check between two
    otherwise-independently-valid values.
    """
    if app_pepper and control_pepper and app_pepper == control_pepper:
        raise ValueError(
            f"{_CREDENTIAL_PEPPER_ENV} and {_CONTROL_CREDENTIAL_PEPPER_ENV} must not be equal"
        )


def _role_or_state_unavailable(value):
    """WP-2 review m-5: `Role(value)` raises a bare `ValueError` for any
    string outside `Role`'s own two members -- a plain Python `ValueError`
    is not an `errors.FoundationError` and would otherwise escape this
    module's entire safe-classification boundary if it reached a caller
    unwrapped. The `credentials.role` column is guarded today by a
    database `CHECK (role IN ('runtime', 'developer'))` (migration 0002),
    so this branch is not reachable through this module's own `issue()`
    -- but the contract's own `role` enum already names FOUR members
    (`runtime`/`developer`/`control`/`audit`, spec/data-service-api.v1.
    json `CapabilityDocument.role`), and a future widening of this table's
    own CHECK constraint (WP-4, if application credentials ever need a
    third role) or an out-of-band data corruption is exactly the kind of
    "this store's own data no longer matches what this code assumes"
    condition `errors.AuthorizationStateUnavailable` exists for: this is
    a loss of STORE STATE INTEGRITY, not a bad credential, so it must
    never be swallowed into a plain `AuthenticationError` (which would
    disguise a genuine store-integrity fault as an ordinary "wrong
    secret" outcome an operator has no reason to investigate further).
    """
    try:
        return Role(value)
    except ValueError as exc:
        raise AuthorizationStateUnavailable(
            "credential store returned a role value outside the known vocabulary "
            "(store state integrity violation)"
        ) from exc


def _execute(cursor, statement, params=()):
    """R-2 choke point (mirrors `backend_postgres.py`'s identical role
    there). The ONLY call to `cursor.execute` in this module."""
    if not isinstance(statement, (sql.SQL, sql.Composed)):
        raise TypeError(
            "credential_store_postgres.py only executes psycopg.sql.Composed/SQL "
            "objects, never str"
        )
    cursor.execute(statement, params)
    return cursor


class PostgresCredentialStore:
    """Same application-credential call surface as `auth.CredentialStore`,
    backed by PostgreSQL instead of an in-memory dict. See this module's
    own top-of-file docstring for the structural differences from both
    `auth.CredentialStore` and r2db-api's peer implementation.
    """

    def __init__(self, dsn: str, *, pepper: Optional[str] = None,
                 schema: str = DEFAULT_SCHEMA, connect_timeout: int = 5,
                 pool: Optional[BoundedConnectionPool] = None) -> None:
        pepper = pepper if pepper is not None else os.environ.get(_CREDENTIAL_PEPPER_ENV)
        # Fail-closed store construction (WP-2 instruction #4): an
        # application-plane process that somehow started without a real
        # pepper configured must never come up able to "authenticate"
        # anything -- refusing to even construct is `auth.CredentialStore.
        # __init__`'s own existing rule, applied identically here.
        if not isinstance(pepper, str) or len(pepper) < 16:
            raise ValueError(f"{_CREDENTIAL_PEPPER_ENV} must be supplied externally (>=16 characters)")
        self._pepper = pepper.encode("utf-8")
        validate_identifier(schema, "schema")
        self._dsn = dsn
        self._connect_timeout = connect_timeout
        self._credentials_table = sql.Identifier(schema, "credentials")
        self._applications_table = sql.Identifier(schema, "applications")
        # WP-3 (design v1.2 R-8 ledger / WP-2 review N-1): an optional
        # bounded pool (`pool.BoundedConnectionPool`) replacing the
        # per-call `psycopg.connect()`/`close()` WP-2 deliberately chose.
        # `None` (the default) preserves WP-2's exact original behavior --
        # every existing caller of this class (WP-2's own tests) is
        # unaffected. The HTTP composition root (`mitatedb_api.main`) is
        # the one caller that supplies a real pool, since it is the one
        # process that calls `assert_active`/`authenticate` once per
        # incoming HTTP request against `mitatedbsvc_api`'s own bounded
        # `CONNECTION LIMIT`.
        self._pool = pool

    def _digest(self, secret) -> bytes:
        if not isinstance(secret, str):
            secret = ""
        return hmac.new(self._pepper, secret.encode("utf-8"), hashlib.sha256).digest()

    def _connect(self) -> "psycopg.Connection":
        """Every method below calls this exactly once, fresh -- see this
        module's own top-of-file docstring ("no pooling, one connection
        per call") for why. `psycopg.Error` here (the platform database
        unreachable, refused, or the connect timing out) is exactly the
        "DB 不達" case WP-2 instruction #5 requires to fail closed as
        `AuthorizationStateUnavailable`, never surfaced as a raw driver
        exception and never silently treated as an authentication failure.
        """
        try:
            return psycopg.connect(self._dsn, connect_timeout=self._connect_timeout, autocommit=False)
        except psycopg.Error as exc:
            raise AuthorizationStateUnavailable("authorization state unavailable") from exc

    @contextmanager
    def _borrow_connection(self):
        """The single choke point every method below acquires a connection
        through (WP-3 pool wiring). Mechanically replaces the WP-2 shape
        `conn = self._connect(); try: ...; finally: conn.close()` with
        `with self._borrow_connection() as conn: ...` -- every method
        body's own indentation and internal try/except is otherwise
        unchanged, since this context manager's `no pool` branch is
        exactly the WP-2 behavior it replaces.

        Pool branch: a connection that raises `psycopg.Error` while
        checked out is discarded (closed, never returned to the idle
        pool) rather than assumed healthy. A connection that returns
        normally -- including via a NON-`psycopg.Error` exception such as
        `errors.NotFoundError` raised between a statement and this store's
        own `conn.commit()`/`conn.rollback()` call (e.g. `revoke()`'s
        `if row is None: raise NotFoundError(...)`, reached before that
        method's own `conn.commit()`) -- still gets a defensive
        `conn.rollback()` here before being released back to the pool.
        Without this, a pooled connection could go idle mid-transaction
        (harmless under WP-2's per-call-connect model, where the very next
        line was always `conn.close()` regardless) and hand the NEXT
        caller a connection with a dangling, uncommitted transaction still
        open on it. `rollback()` with no transaction in progress is a
        no-op, so this is safe to call unconditionally on every healthy
        return, whether or not the method already rolled back itself.
        """
        if self._pool is not None:
            conn = self._pool.acquire()
            healthy = True
            try:
                yield conn
            except psycopg.Error:
                healthy = False
                raise
            finally:
                if healthy:
                    try:
                        conn.rollback()
                    except psycopg.Error:
                        healthy = False
                if healthy:
                    self._pool.release(conn)
                else:
                    self._pool.discard(conn)
        else:
            conn = self._connect()
            try:
                yield conn
            finally:
                conn.close()

    def close(self) -> None:
        """Release every pooled connection this store holds (WP-3). A
        no-op when constructed without a pool (`pool=None`, the WP-2
        default) -- there is nothing this store itself owns to release in
        that configuration, since every connection was already closed
        immediately after its own single call."""
        if self._pool is not None:
            self._pool.closeall()

    # ---- read path ----------------------------------------------------

    def authenticate(self, credential_id, secret) -> Principal:
        """Same shape as `auth.CredentialStore.authenticate`: looks up BY
        `credential_id`, then compares digests with `hmac.compare_digest`
        (never a bare `==`, matching the in-memory store's own choice --
        this is not a lookup-by-index shortcut like r2db's own verifier-
        keyed lookup, so the constant-time comparison is load-bearing
        here, exactly as it is in `auth.CredentialStore`).
        """
        if not isinstance(credential_id, str) or not credential_id:
            raise AuthenticationError("authentication failed")
        with self._borrow_connection() as conn:
            statement = sql.SQL(
                "SELECT c.digest, c.role, c.application_id, c.enabled, c.revoked, "
                "c.expires_at, a.enabled FROM {credentials} c "
                "JOIN {applications} a ON a.application_id = c.application_id "
                "WHERE c.credential_id = {ph}"
            ).format(credentials=self._credentials_table, applications=self._applications_table,
                      ph=sql.Placeholder())
            try:
                with conn.cursor() as cur:
                    _execute(cur, statement, [credential_id])
                    row = cur.fetchone()
            except psycopg.errors.InsufficientPrivilege as exc:
                raise StorageConfigurationError(
                    "the storage backend refused this read due to a privilege/configuration defect"
                ) from exc
            except psycopg.Error as exc:
                raise AuthorizationStateUnavailable("authorization state unavailable") from exc
        # WP-2 review m-4: compute a real `hmac.compare_digest` call
        # against a fixed-shape 32-byte value UNCONDITIONALLY, whether or
        # not `row` was found -- an unknown `credential_id` must not
        # return via a measurably cheaper path than a known one that only
        # fails the secret comparison (see `_DUMMY_DIGEST`'s own docstring).
        stored_digest = bytes(row[0]) if row is not None else _DUMMY_DIGEST
        digest_matches = hmac.compare_digest(stored_digest, self._digest(secret))
        if row is None or not digest_matches:
            raise AuthenticationError("authentication failed")
        _digest, role, application_id, enabled, revoked, expires_at, app_enabled = row
        # WP-2 (design v1.2 R-4): `enabled` and `revoked` are checked
        # independently, mirroring `auth.CredentialStore.authenticate`'s
        # identical two-condition check -- `revoked` is terminal and is
        # never reversed by a later `enable()` call (see `enable`'s own
        # docstring below), so this gate must hold even once `enabled` has
        # been flipped back to `True`.
        valid = enabled and not revoked
        valid = valid and bool(app_enabled)
        valid = valid and (expires_at is None or expires_at > datetime.now(timezone.utc))
        if not valid:
            raise AuthenticationError("authentication failed")
        return Principal(application_id, credential_id, _role_or_state_unavailable(role))

    def assert_active(self, principal: Principal) -> None:
        """Same re-check role as `auth.CredentialStore.assert_active`:
        re-validates an already-open session's credential/application/role
        on every call, so a session cannot outlive a revoke/disable that
        happened after it opened. Read-only (a single `SELECT`) -- the
        application-plane process role (`mitatedbsvc_api`) only ever needs
        `SELECT` for this, matching migration 0002's own grants.
        """
        credential_id = getattr(principal, "credential_id", None)
        if not isinstance(credential_id, str) or not credential_id:
            raise AuthenticationError("authentication failed")
        with self._borrow_connection() as conn:
            statement = sql.SQL(
                "SELECT c.application_id, c.role, c.enabled, c.revoked, c.expires_at, a.enabled "
                "FROM {credentials} c JOIN {applications} a ON a.application_id = c.application_id "
                "WHERE c.credential_id = {ph}"
            ).format(credentials=self._credentials_table, applications=self._applications_table,
                      ph=sql.Placeholder())
            try:
                with conn.cursor() as cur:
                    _execute(cur, statement, [credential_id])
                    row = cur.fetchone()
            except psycopg.errors.InsufficientPrivilege as exc:
                raise StorageConfigurationError(
                    "the storage backend refused this read due to a privilege/configuration defect"
                ) from exc
            except psycopg.Error as exc:
                raise AuthorizationStateUnavailable("authorization state unavailable") from exc
        if row is None:
            raise AuthenticationError("authentication failed")
        application_id, role, enabled, revoked, expires_at, app_enabled = row
        if application_id != getattr(principal, "application_id", None):
            raise AuthenticationError("authentication failed")
        if _role_or_state_unavailable(role) != getattr(principal, "role", None):
            raise AuthenticationError("authentication failed")
        if not enabled or revoked:
            raise AuthenticationError("authentication failed")
        if not app_enabled:
            raise AuthenticationError("authentication failed")
        if expires_at is not None and expires_at <= datetime.now(timezone.utc):
            raise AuthenticationError("authentication failed")

    def get_state(self, credential_id):
        """`(enabled, revoked)` for `credential_id`, or `None` if it does
        not exist -- same read-only, parity-test-facing role as `auth.
        CredentialStore.get_state`."""
        with self._borrow_connection() as conn:
            statement = sql.SQL("SELECT enabled, revoked FROM {table} WHERE credential_id = {ph}").format(
                table=self._credentials_table, ph=sql.Placeholder()
            )
            try:
                with conn.cursor() as cur:
                    _execute(cur, statement, [credential_id])
                    row = cur.fetchone()
            except psycopg.errors.InsufficientPrivilege as exc:
                raise StorageConfigurationError(
                    "the storage backend refused this read due to a privilege/configuration defect"
                ) from exc
            except psycopg.Error as exc:
                raise AuthorizationStateUnavailable("authorization state unavailable") from exc
        return (row[0], row[1]) if row is not None else None

    # ---- write path (provisioning/control-plane tooling only) ---------

    def issue(self, application_id, role, expires_at=None):
        if not isinstance(role, Role):
            role = Role(role)
        if expires_at is not None and (not isinstance(expires_at, datetime) or expires_at.tzinfo is None):
            raise ValueError("expiry must be timezone-aware")
        credential_id = secrets.token_hex(12)
        secret = secrets.token_urlsafe(32)
        digest = self._digest(secret)
        with self._borrow_connection() as conn:
            statement = sql.SQL(
                "INSERT INTO {table} (credential_id, application_id, role, digest, expires_at) "
                "VALUES ({id_ph}, {app_ph}, {role_ph}, {digest_ph}, {expires_ph})"
            ).format(table=self._credentials_table, id_ph=sql.Placeholder(), app_ph=sql.Placeholder(),
                      role_ph=sql.Placeholder(), digest_ph=sql.Placeholder(), expires_ph=sql.Placeholder())
            try:
                with conn.cursor() as cur:
                    _execute(cur, statement, [credential_id, application_id, role.value, digest, expires_at])
                conn.commit()
            except psycopg.errors.ForeignKeyViolation:
                conn.rollback()
                raise AuthenticationError("unknown application")
            except psycopg.errors.InsufficientPrivilege as exc:
                conn.rollback()
                raise StorageConfigurationError(
                    "the storage backend refused this write due to a privilege/configuration defect"
                ) from exc
            except psycopg.Error as exc:
                conn.rollback()
                raise AuthorizationStateUnavailable("authorization state unavailable") from exc
        # Same contract as `auth.CredentialStore.issue`: the secret is
        # returned once and never stored or returned again (only its
        # digest is durable, in the `digest` column above).
        return credential_id, secret

    def revoke(self, credential_id):
        """Sets `revoked` only -- never `enabled` -- same reasoning as
        `auth.CredentialStore.revoke`'s identical rewrite this WP. No SQL
        statement anywhere in this module ever sets `revoked` back to
        `FALSE` (there is no un-revoke path to accidentally trigger)."""
        with self._borrow_connection() as conn:
            statement = sql.SQL(
                "UPDATE {table} SET revoked = TRUE WHERE credential_id = {ph} RETURNING credential_id"
            ).format(table=self._credentials_table, ph=sql.Placeholder())
            try:
                with conn.cursor() as cur:
                    _execute(cur, statement, [credential_id])
                    row = cur.fetchone()
                    if row is None:
                        # Fail closed rather than silently accepting an
                        # unknown id, mirroring `auth.CredentialStore.
                        # revoke`'s identical reasoning.
                        raise NotFoundError("credential not found")
                conn.commit()
            except psycopg.errors.InsufficientPrivilege as exc:
                conn.rollback()
                raise StorageConfigurationError(
                    "the storage backend refused this write due to a privilege/configuration defect"
                ) from exc
            except psycopg.Error as exc:
                conn.rollback()
                raise AuthorizationStateUnavailable("authorization state unavailable") from exc

    def disable(self, credential_id):
        """Reversible operational state -- touches `enabled` only, never
        `revoked`. Fails closed on an unknown credential id, mirroring
        `revoke`."""
        with self._borrow_connection() as conn:
            statement = sql.SQL(
                "UPDATE {table} SET enabled = FALSE WHERE credential_id = {ph} RETURNING credential_id"
            ).format(table=self._credentials_table, ph=sql.Placeholder())
            try:
                with conn.cursor() as cur:
                    _execute(cur, statement, [credential_id])
                    row = cur.fetchone()
                    if row is None:
                        raise NotFoundError("credential not found")
                conn.commit()
            except psycopg.errors.InsufficientPrivilege as exc:
                conn.rollback()
                raise StorageConfigurationError(
                    "the storage backend refused this write due to a privilege/configuration defect"
                ) from exc
            except psycopg.Error as exc:
                conn.rollback()
                raise AuthorizationStateUnavailable("authorization state unavailable") from exc

    def enable(self, credential_id):
        """Reverses `disable` only (contract `enable_credential.
        semantics`). Sets `enabled = TRUE` unconditionally -- including
        when `revoked` is already `TRUE` -- and never touches `revoked` in
        the same statement or any other: there is no SQL text anywhere in
        this class that both reads `revoked` and writes `revoked`, so
        `enable` cannot resurrect a revoked credential even by an
        accidental future edit that tried to make it conditional on the
        current `revoked` value. `authenticate`/`assert_active` above gate
        on `not revoked` independently, so a previously-revoked credential
        still cannot authenticate after this call.

        Fails closed on an unknown credential id, mirroring `disable`.
        """
        with self._borrow_connection() as conn:
            statement = sql.SQL(
                "UPDATE {table} SET enabled = TRUE WHERE credential_id = {ph} RETURNING credential_id"
            ).format(table=self._credentials_table, ph=sql.Placeholder())
            try:
                with conn.cursor() as cur:
                    _execute(cur, statement, [credential_id])
                    row = cur.fetchone()
                    if row is None:
                        raise NotFoundError("credential not found")
                conn.commit()
            except psycopg.errors.InsufficientPrivilege as exc:
                conn.rollback()
                raise StorageConfigurationError(
                    "the storage backend refused this write due to a privilege/configuration defect"
                ) from exc
            except psycopg.Error as exc:
                conn.rollback()
                raise AuthorizationStateUnavailable("authorization state unavailable") from exc

    def disable_application(self, application_id) -> bool:
        """Application-level toggle this same store also observes (via
        the `a.enabled` join column `authenticate`/`assert_active` read
        above) -- WP-2 instruction #2's own "store の書込系は provisioning/
        テスト経路から使う形でよい" applies here too; a future WP-4
        `ControlPlaneService.disable_application` is the eventual
        production caller.

        WP-2 review m-1: returns `True` if `application_id` matched a row
        (`RETURNING application_id`), `False` if it did not -- never
        raises for an unknown application id (still not fail-closed for
        THIS specific method, matching `auth.CredentialStore.
        disable_application`'s own identical, non-fail-closed choice,
        unlike this module's own credential-level methods above) but no
        longer silent about the outcome either: the boolean return lets a
        WP-4 caller decide for itself whether "no such application" is
        worth surfacing, rather than this method deciding that for every
        caller by staying silent.
        """
        with self._borrow_connection() as conn:
            statement = sql.SQL(
                "UPDATE {table} SET enabled = FALSE WHERE application_id = {ph} RETURNING application_id"
            ).format(table=self._applications_table, ph=sql.Placeholder())
            try:
                with conn.cursor() as cur:
                    _execute(cur, statement, [application_id])
                    row = cur.fetchone()
                conn.commit()
                return row is not None
            except psycopg.errors.InsufficientPrivilege as exc:
                conn.rollback()
                raise StorageConfigurationError(
                    "the storage backend refused this write due to a privilege/configuration defect"
                ) from exc
            except psycopg.Error as exc:
                conn.rollback()
                raise AuthorizationStateUnavailable("authorization state unavailable") from exc

    def enable_application(self, application_id) -> bool:
        """See `disable_application` above -- identical reasoning, opposite
        value, same `bool` return (WP-2 review m-1)."""
        with self._borrow_connection() as conn:
            statement = sql.SQL(
                "UPDATE {table} SET enabled = TRUE WHERE application_id = {ph} RETURNING application_id"
            ).format(table=self._applications_table, ph=sql.Placeholder())
            try:
                with conn.cursor() as cur:
                    _execute(cur, statement, [application_id])
                    row = cur.fetchone()
                conn.commit()
                return row is not None
            except psycopg.errors.InsufficientPrivilege as exc:
                conn.rollback()
                raise StorageConfigurationError(
                    "the storage backend refused this write due to a privilege/configuration defect"
                ) from exc
            except psycopg.Error as exc:
                conn.rollback()
                raise AuthorizationStateUnavailable("authorization state unavailable") from exc


__all__ = ["PostgresCredentialStore", "assert_pepper_separation", "DEFAULT_SCHEMA"]
