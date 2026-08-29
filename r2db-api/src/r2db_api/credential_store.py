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

from contextlib import contextmanager
import hashlib
import hmac
import os
from typing import Any, Iterator, Sequence

import psycopg
from psycopg import sql

from .auth import AuthContext, ControlAuthContext
from .errors import FoundationError, fail
from .postgres import _RolePool, _env_int
from .structured import validate_identifier

DEFAULT_SCHEMA = "r2dbsvc_registry"


class _PostgresWork:
    """The Postgres pair's (`PostgresCredentialStore`/`PostgresControl
    CredentialStore`) unit-of-work handle (R-6/§8 B-2) -- wraps exactly one
    checked-out `psycopg` connection, bound to exactly one transaction.
    Every state-changing method below that receives a `work` handle
    executes on `work.connection`, never on a connection of its own -- this
    is what makes it structurally impossible (not merely a convention) for
    a state change and a caller's own same-transaction write (e.g. `ops.py`
    inserting a `control_audit` row alongside a credential rotate) to land
    on two different connections and therefore two different transactions.
    """

    __slots__ = ("connection",)

    def __init__(self, connection: "psycopg.Connection[Any]") -> None:
        self.connection = connection

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

    @contextmanager
    def unit_of_work(self) -> Iterator[_PostgresWork]:
        """R-6/§8 B-2: check out exactly one connection from this store's
        own pool for the duration of the `with` block, `COMMIT` on a clean
        exit, `ROLLBACK` on any exception (including a `FoundationError`
        raised by a business-logic refusal inside the block, e.g. `NOT_
        FOUND`) -- single connection, single transaction, no partial
        application possible. A caller that also needs to write a
        `control_audit` row in the same transaction as a state change (
        `ops.py`) executes that `INSERT` directly against `work.connection`
        inside this same `with` block, rather than through this store at
        all -- this store has no knowledge of `control_audit`.
        """
        with self._pool.connection() as conn:
            work = _PostgresWork(conn)
            try:
                yield work
                conn.commit()
            except BaseException:
                conn.rollback()
                raise

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

    def add(self, credential_id: str, application_id: str, role: str, secret: str, *, work: _PostgresWork) -> None:
        """`work` is a required keyword-only argument (round-2 review ruling
        (A) -- see `auth.CredentialStore.add`'s docstring for the full
        history: round 1 made this optional with an auto-managed fallback,
        which the independent review measured silently splitting a caller's
        multi-call transaction onto a *second* pooled connection -- and
        hard-failing outright once the pool was exhausted (`pool_size=1`) --
        exactly the "state change and audit INSERT land on different
        connections" hazard design §7 warns against. Every caller now opens
        `self.unit_of_work()` itself and passes the handle through
        explicitly; omitting `work` is a `TypeError` at the call boundary.
        """
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
            with work.connection.cursor() as cur:
                _execute(cur, statement, [credential_id, application_id, role, verifier])
        except psycopg.errors.ForeignKeyViolation:
            fail("NOT_FOUND", "Application was not found.", status=404)
        except psycopg.errors.UniqueViolation:
            fail("CONFLICT", "Credential already exists.", status=409)
        except psycopg.Error:
            fail("SERVICE_UNAVAILABLE", "The database could not complete the request.", status=503)

    def set_state(self, credential_id: str, *, enabled: bool | None = None, revoked: bool | None = None, work: _PostgresWork) -> None:
        if enabled is not None and not isinstance(enabled, bool):
            fail("VALIDATION_FAILED", "Credential enabled state must be boolean.")
        if revoked is not None and not isinstance(revoked, bool):
            fail("VALIDATION_FAILED", "Credential revoked state must be boolean.")
        # Revocation is terminal (contract 1.1.0 lifecycle.credential; same
        # rule as `auth.CredentialStore.set_state`). The current `revoked`
        # value is read in the same transaction as the update below (and
        # locked with `FOR UPDATE` so a concurrent revoke cannot race this
        # check), so a `revoked=False` request against an already-revoked
        # row is refused rather than silently applied. No manual `conn.
        # rollback()` before `fail()` below: the caller's own `unit_of_
        # work()` rolls back on any exception, including the `FoundationError`
        # `fail()` raises, so the same guarantee holds without duplicating
        # it here.
        select_statement = sql.SQL("SELECT revoked FROM {table} WHERE credential_id = {id_ph} FOR UPDATE").format(
            table=self._credentials_table, id_ph=sql.Placeholder()
        )
        update_statement = sql.SQL(
            "UPDATE {table} SET enabled = COALESCE({enabled_ph}, enabled), revoked = COALESCE({revoked_ph}, revoked), updated_at = now() WHERE credential_id = {id_ph} RETURNING credential_id"
        ).format(table=self._credentials_table, enabled_ph=sql.Placeholder(), revoked_ph=sql.Placeholder(), id_ph=sql.Placeholder())
        try:
            with work.connection.cursor() as cur:
                _execute(cur, select_statement, [credential_id])
                current = cur.fetchone()
                if current is None:
                    fail("NOT_FOUND", "Credential was not found.", status=404)
                if revoked is False and current[0]:
                    fail("VALIDATION_FAILED", "Revocation is terminal; a revoked credential cannot be un-revoked.")
                _execute(cur, update_statement, [enabled, revoked, credential_id])
                row = cur.fetchone()
                if row is None:
                    fail("NOT_FOUND", "Credential was not found.", status=404)
        except psycopg.Error:
            fail("SERVICE_UNAVAILABLE", "The database could not complete the request.", status=503)

    def rotate(self, credential_id: str, secret: str, *, work: _PostgresWork) -> None:
        """Not part of `auth.CredentialStore`'s call surface (that class has
        no rotation concept at all) -- added here because `python -m
        r2db_api.ops rotate-credential` (P2-D6) needs exactly this one extra
        operation, and computing/writing a verifier is already this class's
        own responsibility; duplicating that SQL a second time in `ops.py`
        would only risk the two copies drifting apart. P2-D6: "同一
        credential_id の verifier を差し替える" -- rotation reuses the
        existing `credential_id`, `role`, and `application_slug`, replacing
        only `verifier` (so the old secret stops authenticating and the new
        one starts, with no other lifecycle state introduced). Unchanged by
        WP-2: this method still does not check `revoked` (§8 M-2's finding
        about this exact method -- see `auth.CredentialStore.rotate`'s
        docstring for why the new in-memory `rotate` was written to match
        this, not the other way around). `work` is required (round-2
        ruling (A)).
        """
        verifier = self.verifier(secret)
        statement = sql.SQL(
            "UPDATE {table} SET verifier = {ph}, updated_at = now() WHERE credential_id = {id_ph} RETURNING credential_id"
        ).format(table=self._credentials_table, ph=sql.Placeholder(), id_ph=sql.Placeholder())
        try:
            with work.connection.cursor() as cur:
                _execute(cur, statement, [verifier, credential_id])
                row = cur.fetchone()
            if row is None:
                fail("NOT_FOUND", "Credential was not found.", status=404)
        except psycopg.errors.UniqueViolation:
            fail("CONFLICT", "Credential verifier collision.", status=409)
        except psycopg.Error:
            fail("SERVICE_UNAVAILABLE", "The database could not complete the request.", status=503)

    def delete(self, credential_id: str, *, work: _PostgresWork) -> None:
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
        enforced structurally here, not left to operator discipline. `work`
        is required (round-2 ruling (A)).
        """
        statement = sql.SQL(
            "DELETE FROM {table} WHERE credential_id = {id_ph} AND revoked = true RETURNING credential_id"
        ).format(table=self._credentials_table, id_ph=sql.Placeholder())
        probe = sql.SQL("SELECT revoked FROM {table} WHERE credential_id = {id_ph}").format(
            table=self._credentials_table, id_ph=sql.Placeholder()
        )
        try:
            with work.connection.cursor() as cur:
                _execute(cur, statement, [credential_id])
                row = cur.fetchone()
                if row is None:
                    # Same transaction: distinguish "no such credential"
                    # from "exists but not revoked" without racing a
                    # concurrent insert or revoke.
                    _execute(cur, probe, [credential_id])
                    existing = cur.fetchone()
                    if existing is None:
                        fail("NOT_FOUND", "Credential was not found.", status=404)
                    fail("VALIDATION_FAILED", "Credential is not revoked. Revoke it first; only revoked credentials can be deleted.")
        except psycopg.Error:
            fail("SERVICE_UNAVAILABLE", "The database could not complete the request.", status=503)


def validate_control_pepper_separation(app_pepper: str | None, control_pepper: str | None) -> None:
    """R-2: wherever a process' configuration carries *both* the
    application-plane pepper (`R2DB_CREDENTIAL_PEPPER`) and the
    control-plane pepper (`R2DB_CONTROL_CREDENTIAL_PEPPER`), the two values
    must differ. An operator who (by mistake, e.g. copy-paste from one
    secret-manager entry to both env var names) configures them identically
    would make an application credential's verifier and a control
    credential's verifier collide under the same underlying secret string --
    silently punching a hole through R-2's "control credential storage is
    unreadable from the application plane" wall via pepper reuse rather than
    any table/grant mistake.

    Called from `ops.py`'s control-credential ritual/break-glass command
    constructors today -- design docs/design/R2DB_CCR14_CONTROL_PLANE_V1.md
    §1 R-2 calls this "共通経路" (a shared path): a future composition root
    that ever constructs both an application-plane and a control-plane store
    in the same process must call this too, which is why this lives here
    (imported by both `ops.py` and, in the future, `main.py`/`control_main.
    py`) rather than being duplicated at each call site.
    """
    if app_pepper and control_pepper and app_pepper == control_pepper:
        raise ValueError("R2DB_CREDENTIAL_PEPPER and R2DB_CONTROL_CREDENTIAL_PEPPER must not be equal")


class PostgresControlCredentialStore:
    """Postgres-backed counterpart to `auth.ControlCredentialStore` -- same
    call surface, backed by `r2dbsvc_registry.control_credentials`
    (migration `0006_control_plane_http.sql`) instead of an in-memory dict.
    Mirrors `PostgresCredentialStore` above in every structural respect
    (P2-D4 no-cache read path, fail-closed `AUTH_STATE_UNAVAILABLE`, D-4 SQL
    composition discipline, its own dedicated `_RolePool`) -- the two
    classes are kept side by side in this module rather than sharing a base
    class, matching how `auth.CredentialStore`/`auth.ControlCredentialStore`
    are two independent classes in that module too (design §3: "同一 call
    surface", not "shared implementation" -- a control credential's storage
    is deliberately a completely separate table/role/pepper from an
    application credential's, R-2, and keeping the Python classes
    unrelated-by-inheritance mirrors that at the code level).
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
        pepper = pepper or os.environ.get("R2DB_CONTROL_CREDENTIAL_PEPPER")
        if not pepper:
            raise ValueError("R2DB_CONTROL_CREDENTIAL_PEPPER is required")
        self._pepper = pepper.encode()
        validate_identifier(schema)
        maxconn = pool_size if pool_size is not None else _env_int("R2DB_PLATFORM_POOL_SIZE", 4)
        pool_kwargs: dict[str, Any] = {}
        if connect_timeout is not None:
            pool_kwargs["connect_timeout"] = connect_timeout
        if acquire_timeout is not None:
            pool_kwargs["acquire_timeout"] = acquire_timeout
        self._pool = _RolePool(dsn, schema=schema, maxconn=maxconn, **pool_kwargs)
        self._schema = schema
        self._table = sql.Identifier(schema, "control_credentials")
        self.available = True

    def close(self) -> None:
        self._pool.close_all()

    @contextmanager
    def unit_of_work(self) -> Iterator[_PostgresWork]:
        with self._pool.connection() as conn:
            work = _PostgresWork(conn)
            try:
                yield work
                conn.commit()
            except BaseException:
                conn.rollback()
                raise

    def verifier(self, secret: str) -> str:
        if not isinstance(secret, str):
            fail("VALIDATION_FAILED", "Credential secret has an invalid type.")
        return hmac.new(self._pepper, secret.encode(), hashlib.sha256).hexdigest()

    def authenticate(self, secret: str | None) -> ControlAuthContext:
        if not self.available:
            fail("AUTH_STATE_UNAVAILABLE", "Authorization state is unavailable.", status=503)
        if not secret:
            fail("AUTH_REQUIRED", "Authentication is required.", status=401)
        computed = self.verifier(secret)
        statement = sql.SQL("SELECT credential_id, verifier, enabled, revoked, must_rotate FROM {table} WHERE verifier = {ph}").format(
            table=self._table, ph=sql.Placeholder()
        )
        row = self._fetch_or_503(statement, [computed])
        if row is None:
            fail("AUTH_INVALID", "Credential is not valid.", status=401)
        credential_id, db_verifier, enabled, revoked, must_rotate = row
        if not hmac.compare_digest(db_verifier, computed):
            fail("AUTH_INVALID", "Credential is not valid.", status=401)
        if revoked:
            fail("AUTH_REVOKED", "Credential is not active.", status=401)
        if not enabled:
            fail("AUTH_INVALID", "Credential is not active.", status=401)
        return ControlAuthContext(credential_id, must_rotate)

    def assert_active(self, context: ControlAuthContext) -> ControlAuthContext:
        if not self.available:
            fail("AUTH_STATE_UNAVAILABLE", "Authorization state is unavailable.", status=503)
        statement = sql.SQL("SELECT credential_id, enabled, revoked, must_rotate FROM {table} WHERE credential_id = {ph}").format(
            table=self._table, ph=sql.Placeholder()
        )
        row = self._fetch_or_503(statement, [context.credential_id])
        if row is None:
            fail("AUTH_INVALID", "Credential is not active.", status=401)
        credential_id, enabled, revoked, must_rotate = row
        if revoked:
            fail("AUTH_REVOKED", "Credential is not active.", status=401)
        if not enabled:
            fail("AUTH_INVALID", "Credential is not active.", status=401)
        return ControlAuthContext(credential_id, must_rotate)

    def _fetch_or_503(self, statement: sql.Composed, params: Sequence[Any]) -> tuple[Any, ...] | None:
        try:
            with self._pool.connection() as conn:
                with conn.cursor() as cur:
                    _execute(cur, statement, params)
                    return cur.fetchone()
        except psycopg.Error:
            fail("AUTH_STATE_UNAVAILABLE", "Authorization state is unavailable.", status=503)
            raise  # unreachable; fail() always raises

    # ---- write path (ritual-only: `ops.py`'s bootstrap/reset/break-glass) --

    def add(self, credential_id: str, secret: str, *, work: _PostgresWork) -> None:
        """Only reachable through `ops.py` (connected as `r2dbsvc_control`)
        -- `r2dbsvc_controlplane` (0006) is never granted INSERT on this
        table at all, so calling this against a control-plane-process
        connection fails at the database-privilege level (R-3), independent
        of this Python-level restriction. `work` is required (round-2
        ruling (A) -- see `PostgresCredentialStore.add`'s docstring for the
        full history).
        """
        verifier = self.verifier(secret)
        statement = sql.SQL("INSERT INTO {table} (credential_id, verifier) VALUES ({id_ph}, {verifier_ph})").format(
            table=self._table, id_ph=sql.Placeholder(), verifier_ph=sql.Placeholder()
        )
        try:
            with work.connection.cursor() as cur:
                _execute(cur, statement, [credential_id, verifier])
        except psycopg.errors.UniqueViolation:
            fail("CONFLICT", "Control credential already exists.", status=409)
        except psycopg.Error:
            fail("SERVICE_UNAVAILABLE", "The database could not complete the request.", status=503)

    def set_state(self, credential_id: str, *, enabled: bool | None = None, revoked: bool | None = None, work: _PostgresWork) -> None:
        if enabled is not None and not isinstance(enabled, bool):
            fail("VALIDATION_FAILED", "Credential enabled state must be boolean.")
        if revoked is not None and not isinstance(revoked, bool):
            fail("VALIDATION_FAILED", "Credential revoked state must be boolean.")
        select_statement = sql.SQL("SELECT revoked FROM {table} WHERE credential_id = {id_ph} FOR UPDATE").format(
            table=self._table, id_ph=sql.Placeholder()
        )
        update_statement = sql.SQL(
            "UPDATE {table} SET enabled = COALESCE({enabled_ph}, enabled), revoked = COALESCE({revoked_ph}, revoked), updated_at = now() WHERE credential_id = {id_ph} RETURNING credential_id"
        ).format(table=self._table, enabled_ph=sql.Placeholder(), revoked_ph=sql.Placeholder(), id_ph=sql.Placeholder())
        try:
            with work.connection.cursor() as cur:
                _execute(cur, select_statement, [credential_id])
                current = cur.fetchone()
                if current is None:
                    fail("NOT_FOUND", "Control credential was not found.", status=404)
                if revoked is False and current[0]:
                    fail("VALIDATION_FAILED", "Revocation is terminal; a revoked control credential cannot be un-revoked.")
                _execute(cur, update_statement, [enabled, revoked, credential_id])
                row = cur.fetchone()
                if row is None:
                    fail("NOT_FOUND", "Control credential was not found.", status=404)
        except psycopg.Error:
            fail("SERVICE_UNAVAILABLE", "The database could not complete the request.", status=503)

    def rotate(self, credential_id: str, secret: str, *, work: _PostgresWork) -> None:
        """R-5/§2 M-2: verifier replacement + `must_rotate = false` +
        `updated_at` refresh, one statement. A revoked row is refused
        (`VALIDATION_FAILED`) via the same `FOR UPDATE`-then-check pattern
        `set_state` above uses, rather than trusting a bare `UPDATE ...
        WHERE revoked = false` to have matched zero rows for the right
        reason (that would return `NOT_FOUND` for an existing-but-revoked
        row, indistinguishable from "no such credential" -- a strictly
        worse error for the caller than the dedicated `VALIDATION_FAILED`
        this gives instead). `work` is required (round-2 ruling (A)).
        """
        verifier = self.verifier(secret)
        select_statement = sql.SQL("SELECT revoked FROM {table} WHERE credential_id = {id_ph} FOR UPDATE").format(
            table=self._table, id_ph=sql.Placeholder()
        )
        update_statement = sql.SQL(
            "UPDATE {table} SET verifier = {verifier_ph}, must_rotate = false, updated_at = now() WHERE credential_id = {id_ph} RETURNING credential_id"
        ).format(table=self._table, verifier_ph=sql.Placeholder(), id_ph=sql.Placeholder())
        try:
            with work.connection.cursor() as cur:
                _execute(cur, select_statement, [credential_id])
                current = cur.fetchone()
                if current is None:
                    fail("NOT_FOUND", "Control credential was not found.", status=404)
                if current[0]:
                    fail("VALIDATION_FAILED", "A revoked control credential cannot be rotated.")
                _execute(cur, update_statement, [verifier, credential_id])
                row = cur.fetchone()
                if row is None:
                    fail("NOT_FOUND", "Control credential was not found.", status=404)
        except psycopg.errors.UniqueViolation:
            fail("CONFLICT", "Control credential verifier collision.", status=409)
        except psycopg.Error:
            fail("SERVICE_UNAVAILABLE", "The database could not complete the request.", status=503)

    def has_any(self, *, include_revoked: bool = True, work: _PostgresWork | None = None) -> bool:
        """§8 M-6: bootstrap's existence check, real-row semantics -- see
        `auth.ControlCredentialStore.has_any`'s identical docstring.

        `work` is a **read-only**, optional parameter (this is not one of
        the state-changing methods ruling (A) requires `work` on): when
        omitted, this runs as a plain standalone read on its own pooled
        connection, exactly as round 1 of this WP had it. When supplied
        (MA-3, round-2 review: closing the TOCTOU gap between a standalone
        existence check and the subsequent `add` -- two concurrent
        bootstraps could both observe "no row" before either committed),
        this executes on `work.connection` instead, so the check
        participates in the caller's own transaction -- and, combined with
        an advisory lock taken on that same connection before this is
        called (`ops.py cmd_bootstrap`/`cmd_reset`), a second concurrent
        ritual invocation blocks until the first commits or rolls back, and
        then sees its row.
        """
        if include_revoked:
            statement = sql.SQL("SELECT EXISTS(SELECT 1 FROM {table})").format(table=self._table)
        else:
            statement = sql.SQL("SELECT EXISTS(SELECT 1 FROM {table} WHERE NOT revoked)").format(table=self._table)
        if work is not None:
            with work.connection.cursor() as cur:
                _execute(cur, statement, [])
                row = cur.fetchone()
                return bool(row[0]) if row else False
        try:
            with self._pool.connection() as conn:
                with conn.cursor() as cur:
                    _execute(cur, statement, [])
                    row = cur.fetchone()
                    return bool(row[0]) if row else False
        except psycopg.Error:
            fail("AUTH_STATE_UNAVAILABLE", "Authorization state is unavailable.", status=503)
            raise  # unreachable; fail() always raises

    def revoke_all(self, *, work: _PostgresWork) -> None:
        """Reset's "revoke every existing control credential" step (R-5) --
        see `auth.ControlCredentialStore.revoke_all`'s identical docstring.
        `work` is required (round-2 ruling (A)).
        """
        statement = sql.SQL("UPDATE {table} SET revoked = true, updated_at = now() WHERE NOT revoked").format(table=self._table)
        try:
            with work.connection.cursor() as cur:
                _execute(cur, statement, [])
        except psycopg.Error:
            fail("SERVICE_UNAVAILABLE", "The database could not complete the request.", status=503)


__all__ = ["PostgresCredentialStore", "PostgresControlCredentialStore", "validate_control_pepper_separation", "DEFAULT_SCHEMA"]
