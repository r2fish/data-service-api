"""`PostgresCredentialStore`: the same call surface as `r2db_api.auth.
CredentialStore`, backed by `r2dbsvc_registry.credentials`/`applications`
(migration `0005_credential_store.sql`) instead of an in-memory dict.

Design this file is written to satisfy (docs/design/
R2DB_CREDENTIAL_PERSISTENCE_AND_COMPOSITION_ROOT_V1.md, P2-D1/P2-D3/P2-D4):

- **Persistence.** `r2db_api.auth.CredentialStore` loses every credential
  and every application `enabled`/disabled flag on process restart -- this
  class reads and writes the same shape from/to PostgreSQL instead, so a
  restarted process (or a second process entirely) sees exactly the state
  the last write left behind.
- **No cache, ever (P2-D4).** `authenticate`/`assert_active` query
  PostgreSQL fresh on every single call -- there is no in-process cache of
  credential state anywhere in this file. This is what keeps
  `authorization_propagation_bound_ms: 0` (`DataService.capabilities`)
  true for the PostgreSQL-backed deployment exactly as it was for the
  in-memory one: a revoke/disable/state-unavailable change committed by
  `python -m r2db_api.ops` is visible to the *next* request this store
  handles, with no cache entry anywhere to expire or invalidate. Adding a
  cache here would require also changing that advertised bound -- so this
  file deliberately never adds one.
- **Fail-closed, never fail-open (P2-D4).** A PostgreSQL error while
  *reading* credential state (the platform database unreachable, the
  connection pool exhausted and unable to open a new one, a query timing
  out) is deliberately mapped to `AUTH_STATE_UNAVAILABLE` (503) here, never
  to `AUTH_INVALID` (401): "we could not verify this" and "this is invalid"
  are different claims, and only the caller's `available` flag or an actual
  negative lookup result may produce the latter. Every read path below
  funnels PostgreSQL exceptions through exactly one `except psycopg.Error`
  clause each, so this is a structural property of the file, not a
  convention repeated ad hoc per method.
- **SQL composition discipline (D-4, `r2db_api.postgres`'s own header).**
  Every statement in this file is built with `psycopg.sql.SQL`/`sql.
  Identifier`/`sql.Placeholder` and passed through `cursor.execute(...)`
  with a bound parameter list -- never an f-string or `%`-formatted plain
  string. `schema`/table/column names below are fixed, code-authored
  literals (never client/request input), matching `_load_catalog`'s own use
  of plain `sql.SQL(...)` text for statically-known identifiers in
  `postgres.py`.

Two configurations this class is actually used in (docs/design's P2-D3):

1. **Read path -- the running API process** (`r2db_api.main`): constructed
   with `R2DB_PLATFORM_DSN`, which authenticates as the strictly read-only
   `r2dbsvc_api` role (0005: `SELECT` only on `applications`/`credentials`).
   Only `authenticate`/`assert_active`/`canonical_context`/
   `application_id_for`/`verifier`/`available` are ever exercised in this
   configuration; `add`/`set_state`/`rotate` would fail at the database
   privilege level if ever called here (by design -- see 0005's header).
2. **Write path -- `python -m r2db_api.ops`** (P2-D6): constructed with
   `R2DB_CONTROL_DSN`, which authenticates as `r2dbsvc_control` (full DML on
   this schema, the same role 0002/0003/0004 already run as). The CLI reuses
   `add`/`set_state`/`rotate`/`verifier` directly instead of hand-rolling a
   second copy of this same SQL.

`schema` defaults to the literal production schema name
(`r2dbsvc_registry`, matching `0005_credential_store.sql`); it exists as a
constructor parameter (mirroring `PostgresCell`'s own `schema` parameter)
solely so this repository's own tests and the conformance adapter -- which
run the real migration files with `r2dbsvc` textually replaced by a
random throwaway prefix, to avoid colliding with anything else in a shared
local cluster -- can point this class at their own rewritten schema name.
It is never derived from client/request input.
"""
from __future__ import annotations

import hashlib
import hmac
import os
from typing import Any, Sequence

import psycopg
from psycopg import sql

from .auth import AuthContext
from .errors import FoundationError, fail
from .postgres import _RolePool, _env_int
from .structured import validate_identifier

DEFAULT_SCHEMA = "r2dbsvc_registry"

# The exact column order every `SELECT` below returns, so the small local
# tuple-unpacking helpers that follow stay in one place instead of being
# repeated (and risking drifting out of sync) at every call site.
_COLUMNS = "c.credential_id, c.application_slug, c.role, c.verifier, c.enabled, c.revoked"
_SELECT_BY_VERIFIER = "SELECT {columns}, a.enabled FROM {credentials} c JOIN {applications} a ON a.application_slug = c.application_slug WHERE c.verifier = {ph}"
_SELECT_BY_ID = "SELECT {columns}, a.enabled FROM {credentials} c JOIN {applications} a ON a.application_slug = c.application_slug WHERE c.credential_id = {ph}"


def _execute(cursor: "psycopg.Cursor[Any]", statement: sql.Composed | sql.SQL, params: Sequence[Any] = ()) -> None:
    """The single execution choke point for this file -- mirrors `postgres.
    py::_run`'s identical role there. Typed to accept only a composed
    psycopg SQL object, never `str`, so a raw string cannot reach the
    database from anywhere in this module (D-4).
    """
    if not isinstance(statement, (sql.Composed, sql.SQL)):
        raise TypeError("credential_store.py only executes psycopg.sql.Composed/SQL objects, never str")
    cursor.execute(statement, list(params))


class PostgresCredentialStore:
    """Same call surface as `r2db_api.auth.CredentialStore`
    (`authenticate`/`assert_active`/`canonical_context`/
    `application_id_for`/`add`/`set_state`/`verifier`/`available`), backed
    by PostgreSQL instead of an in-memory dict. `rotate` is one addition
    beyond that literal surface -- see its own docstring for why.
    """

    def __init__(
        self,
        dsn: str,
        *,
        pepper: str | None = None,
        schema: str = DEFAULT_SCHEMA,
        pool_size: int | None = None,
        connect_timeout: int | None = None,
        acquire_timeout: float | None = None,
    ) -> None:
        pepper = pepper or os.environ.get("R2DB_CREDENTIAL_PEPPER")
        if not pepper:
            raise ValueError("R2DB_CREDENTIAL_PEPPER is required")
        self._pepper = pepper.encode()
        validate_identifier(schema)
        # P2-D4's own dedicated pool: deliberately *not* registered with
        # `postgres.SharedPoolManager` (whose key space is `(application_id,
        # role)`, `application_id` constrained to
        # `r2db_api.structured.validate_identifier`'s syntax -- this store
        # is not an application and must not be made to look like one in
        # that cache). `_RolePool` already is exactly "a small pool fixed to
        # one dsn/schema", which is exactly what this store needs, so it is
        # reused directly here rather than re-implemented -- including its
        # bounded connect/acquire timeouts (`_RolePool`'s own module-level
        # defaults apply unless overridden below), which is what keeps a
        # platform database outage from turning into an indefinite hang on
        # every request's authentication path rather than a prompt
        # `AUTH_STATE_UNAVAILABLE` (503) -- see `_RolePool._acquire`'s own
        # comment for the bug this fixes.
        maxconn = pool_size if pool_size is not None else _env_int("R2DB_PLATFORM_POOL_SIZE", 4)
        pool_kwargs: dict[str, Any] = {}
        if connect_timeout is not None:
            pool_kwargs["connect_timeout"] = connect_timeout
        if acquire_timeout is not None:
            pool_kwargs["acquire_timeout"] = acquire_timeout
        self._pool = _RolePool(dsn, schema=schema, maxconn=maxconn, **pool_kwargs)
        self._schema = schema
        self._credentials_table = sql.Identifier(schema, "credentials")
        self._applications_table = sql.Identifier(schema, "applications")
        self.available = True

    def close(self) -> None:
        """Release every connection this store's own pool holds -- called
        from the composition root's ASGI shutdown lifespan
        (`r2db_api.main`) and from this repository's test/adapter teardown,
        mirroring `PostgresCell.close()`'s equivalent role for application
        pools.
        """
        self._pool.close_all()

    # ---- shared verifier computation (identical to `auth.CredentialStore`) --

    def verifier(self, secret: str) -> str:
        if not isinstance(secret, str):
            fail("VALIDATION_FAILED", "Credential secret has an invalid type.")
        return hmac.new(self._pepper, secret.encode(), hashlib.sha256).hexdigest()

    # ---- read path (P2-D4: every call below queries PostgreSQL fresh) -----

    def authenticate(self, secret: str | None) -> AuthContext:
        if not self.available:
            fail("AUTH_STATE_UNAVAILABLE", "Authorization state is unavailable.", status=503)
        if not secret:
            fail("AUTH_REQUIRED", "Authentication is required.", status=401)
        computed = self.verifier(secret)
        statement = sql.SQL(_SELECT_BY_VERIFIER).format(
            columns=sql.SQL(_COLUMNS), credentials=self._credentials_table, applications=self._applications_table, ph=sql.Placeholder()
        )
        row = self._fetch_or_503(statement, [computed])
        if row is None:
            fail("AUTH_INVALID", "Credential is not valid.", status=401)
        credential_id, application_id, role, db_verifier, enabled, revoked, app_enabled = row
        # The lookup above is already an exact-equality index match on
        # `verifier` (the row could not have been found otherwise) -- this
        # `compare_digest` is deliberate defence-in-depth, not the
        # authoritative check, kept for structural symmetry with
        # `auth.CredentialStore.authenticate`'s identical final comparison
        # (P2-D4).
        if not hmac.compare_digest(db_verifier, computed):
            fail("AUTH_INVALID", "Credential is not valid.", status=401)
        if revoked:
            fail("AUTH_REVOKED", "Credential is not active.", status=401)
        if not enabled:
            fail("AUTH_INVALID", "Credential is not active.", status=401)
        if not app_enabled:
            fail("APPLICATION_DISABLED", "Application is disabled.", status=403)
        return AuthContext(credential_id, application_id, role)

    def assert_active(self, context: AuthContext) -> AuthContext:
        if not self.available:
            fail("AUTH_STATE_UNAVAILABLE", "Authorization state is unavailable.", status=503)
        statement = sql.SQL(_SELECT_BY_ID).format(
            columns=sql.SQL(_COLUMNS), credentials=self._credentials_table, applications=self._applications_table, ph=sql.Placeholder()
        )
        row = self._fetch_or_503(statement, [context.credential_id])
        if row is None:
            fail("AUTH_INVALID", "Credential is not active.", status=401)
        credential_id, application_id, role, _verifier, enabled, revoked, app_enabled = row
        if revoked:
            fail("AUTH_REVOKED", "Credential is not active.", status=401)
        if not enabled:
            fail("AUTH_INVALID", "Credential is not active.", status=401)
        if application_id != context.application_id or role != context.role:
            fail("SCOPE_MISMATCH", "Credential scope is not valid for this request.", status=403)
        if not app_enabled:
            fail("APPLICATION_DISABLED", "Application is disabled.", status=403)
        return AuthContext(credential_id, application_id, role)

    def canonical_context(self, context: AuthContext) -> AuthContext | None:
        """Audit-trail attribution only (`DataService._event`'s caller),
        never an authorization gate -- unlike `authenticate`/`assert_active`
        above, a PostgreSQL error here must not turn an already-authorized,
        in-flight request into a 503: it degrades to `None` (the same
        "could not attribute this" outcome `auth.CredentialStore.
        canonical_context` already produces for an unknown `credential_id`),
        not a raised `FoundationError`.
        """
        credential_id = getattr(context, "credential_id", "")
        if not credential_id:
            return None
        statement = sql.SQL(_SELECT_BY_ID).format(
            columns=sql.SQL(_COLUMNS), credentials=self._credentials_table, applications=self._applications_table, ph=sql.Placeholder()
        )
        try:
            row = self._fetch_or_503(statement, [credential_id])
        except FoundationError:
            return None
        if row is None:
            return None
        _credential_id, application_id, role, *_rest = row
        return AuthContext(credential_id, application_id, role)

    def application_id_for(self, credential_id: str) -> str | None:
        """Same audit-attribution-only reasoning as `canonical_context`
        above: used by `ControlAuthority._control_event` to attribute a
        control-plane event whose target is a credential id, not an
        application id already known to be live. Degrades to `None` on a
        PostgreSQL error rather than raising.
        """
        statement = sql.SQL(_SELECT_BY_ID).format(
            columns=sql.SQL(_COLUMNS), credentials=self._credentials_table, applications=self._applications_table, ph=sql.Placeholder()
        )
        try:
            row = self._fetch_or_503(statement, [credential_id])
        except FoundationError:
            return None
        return row[1] if row is not None else None

    def _fetch_or_503(self, statement: sql.Composed, params: Sequence[Any]) -> tuple[Any, ...] | None:
        try:
            with self._pool.connection() as conn:
                with conn.cursor() as cur:
                    _execute(cur, statement, params)
                    return cur.fetchone()
        except psycopg.Error:
            fail("AUTH_STATE_UNAVAILABLE", "Authorization state is unavailable.", status=503)
            raise  # unreachable; fail() always raises

    # ---- write path (P2-D6: reused directly by `python -m r2db_api.ops`) --

    def add(self, credential_id: str, application_id: str, role: str, secret: str) -> None:
        if role not in {"runtime", "developer"}:
            fail("VALIDATION_FAILED", "Application credentials require runtime or developer role.")
        verifier = self.verifier(secret)
        statement = sql.SQL(
            "INSERT INTO {table} (credential_id, application_slug, role, verifier) VALUES ({id_ph}, {app_ph}, {role_ph}, {verifier_ph})"
        ).format(
            table=self._credentials_table,
            id_ph=sql.Placeholder(),
            app_ph=sql.Placeholder(),
            role_ph=sql.Placeholder(),
            verifier_ph=sql.Placeholder(),
        )
        try:
            with self._pool.connection() as conn:
                with conn.cursor() as cur:
                    _execute(cur, statement, [credential_id, application_id, role, verifier])
                conn.commit()
        except psycopg.errors.ForeignKeyViolation:
            fail("NOT_FOUND", "Application was not found.", status=404)
        except psycopg.errors.UniqueViolation:
            fail("CONFLICT", "Credential already exists.", status=409)
        except psycopg.Error:
            fail("SERVICE_UNAVAILABLE", "The database could not complete the request.", status=503)

    def set_state(self, credential_id: str, *, enabled: bool | None = None, revoked: bool | None = None) -> None:
        if enabled is not None and not isinstance(enabled, bool):
            fail("VALIDATION_FAILED", "Credential enabled state must be boolean.")
        if revoked is not None and not isinstance(revoked, bool):
            fail("VALIDATION_FAILED", "Credential revoked state must be boolean.")
        # Revocation is terminal (contract 1.1.0 lifecycle.credential; same
        # rule as `auth.CredentialStore.set_state`). The current `revoked`
        # value is read in the same transaction as the update below (and
        # locked with `FOR UPDATE` so a concurrent revoke cannot race this
        # check), so a `revoked=False` request against an already-revoked
        # row is refused rather than silently applied.
        select_statement = sql.SQL("SELECT revoked FROM {table} WHERE credential_id = {id_ph} FOR UPDATE").format(
            table=self._credentials_table, id_ph=sql.Placeholder()
        )
        update_statement = sql.SQL(
            "UPDATE {table} SET enabled = COALESCE({enabled_ph}, enabled), revoked = COALESCE({revoked_ph}, revoked), updated_at = now() WHERE credential_id = {id_ph} RETURNING credential_id"
        ).format(table=self._credentials_table, enabled_ph=sql.Placeholder(), revoked_ph=sql.Placeholder(), id_ph=sql.Placeholder())
        try:
            with self._pool.connection() as conn:
                with conn.cursor() as cur:
                    _execute(cur, select_statement, [credential_id])
                    current = cur.fetchone()
                    if current is None:
                        conn.rollback()
                        fail("NOT_FOUND", "Credential was not found.", status=404)
                    if revoked is False and current[0]:
                        conn.rollback()
                        fail("VALIDATION_FAILED", "Revocation is terminal; a revoked credential cannot be un-revoked.")
                    _execute(cur, update_statement, [enabled, revoked, credential_id])
                    row = cur.fetchone()
                    if row is None:
                        conn.rollback()
                        fail("NOT_FOUND", "Credential was not found.", status=404)
                conn.commit()
        except psycopg.Error:
            fail("SERVICE_UNAVAILABLE", "The database could not complete the request.", status=503)

    def rotate(self, credential_id: str, secret: str) -> None:
        """Not part of `auth.CredentialStore`'s call surface (that class has
        no rotation concept at all) -- added here because `python -m
        r2db_api.ops rotate-credential` (P2-D6) needs exactly this one extra
        operation, and computing/writing a verifier is already this class's
        own responsibility; duplicating that SQL a second time in `ops.py`
        would only risk the two copies drifting apart. P2-D6: "同一
        credential_id の verifier を差し替える" -- rotation reuses the
        existing `credential_id`, `role`, and `application_slug`, replacing
        only `verifier` (so the old secret stops authenticating and the new
        one starts, with no other lifecycle state introduced).
        """
        verifier = self.verifier(secret)
        statement = sql.SQL(
            "UPDATE {table} SET verifier = {ph}, updated_at = now() WHERE credential_id = {id_ph} RETURNING credential_id"
        ).format(table=self._credentials_table, ph=sql.Placeholder(), id_ph=sql.Placeholder())
        try:
            with self._pool.connection() as conn:
                with conn.cursor() as cur:
                    _execute(cur, statement, [verifier, credential_id])
                    row = cur.fetchone()
                if row is None:
                    fail("NOT_FOUND", "Credential was not found.", status=404)
                conn.commit()
        except psycopg.errors.UniqueViolation:
            fail("CONFLICT", "Credential verifier collision.", status=409)
        except psycopg.Error:
            fail("SERVICE_UNAVAILABLE", "The database could not complete the request.", status=503)

    def delete(self, credential_id: str) -> None:
        """Not part of `auth.CredentialStore`'s call surface either, and
        distinct in kind from `set_state(revoked=True)`: revoking preserves
        the row (P2-D1's own reasoning -- the verifier stays on record,
        `enabled`/`revoked` are the only things that change), this actually
        removes it. Added specifically so `0004_deprovision_application.
        sql`'s `assert_no_credentials_for_deprovision` guard (review-
        reported gap) has a real, supported way to be satisfied: that
        guard's `ON DELETE RESTRICT` foreign key means an application can
        never be deprovisioned while any credential row still references
        it, revoked or not -- only removing the row clears it. `python -m
        r2db_api.ops delete-credential` is the only caller; this is a
        genuinely destructive, irreversible operation (unlike every other
        write this class performs), so it is deliberately not exposed as
        part of the ordinary lifecycle vocabulary (`add`/`set_state`/
        `rotate`) and carries no soft-delete/undo path.

        Only a *revoked* credential can be deleted. A live credential must
        go through `revoke` first: deleting it directly would cut an
        application's access with no revocation ever having been recorded
        -- the removal would masquerade as the credential never having
        existed, exactly the audit-linkage failure the `ON DELETE RESTRICT`
        design is there to prevent. The two-step (revoke, then delete) is
        enforced structurally here, not left to operator discipline.
        """
        statement = sql.SQL(
            "DELETE FROM {table} WHERE credential_id = {id_ph} AND revoked = true RETURNING credential_id"
        ).format(table=self._credentials_table, id_ph=sql.Placeholder())
        probe = sql.SQL("SELECT revoked FROM {table} WHERE credential_id = {id_ph}").format(
            table=self._credentials_table, id_ph=sql.Placeholder()
        )
        try:
            with self._pool.connection() as conn:
                with conn.cursor() as cur:
                    _execute(cur, statement, [credential_id])
                    row = cur.fetchone()
                    if row is None:
                        # Same transaction: distinguish "no such credential"
                        # from "exists but not revoked" without racing a
                        # concurrent insert or revoke.
                        _execute(cur, probe, [credential_id])
                        existing = cur.fetchone()
                        conn.rollback()
                        if existing is None:
                            fail("NOT_FOUND", "Credential was not found.", status=404)
                        fail("VALIDATION_FAILED", "Credential is not revoked. Revoke it first; only revoked credentials can be deleted.")
                conn.commit()
        except psycopg.Error:
            fail("SERVICE_UNAVAILABLE", "The database could not complete the request.", status=503)


__all__ = ["PostgresCredentialStore", "DEFAULT_SCHEMA"]
