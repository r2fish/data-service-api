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
from datetime import datetime, timezone
import hashlib
import hmac
import os
from typing import Any, Iterator, Sequence
import uuid

import psycopg
from psycopg import sql

from .auth import AuthContext, ControlAuthContext, _fail_identified
from .errors import FoundationError, fail
from .postgres import _RolePool, _env_int
from .structured import validate_identifier

DEFAULT_SCHEMA = "r2dbsvc_registry"

# Opus review minor m-5: the control plane's own last-active-control-
# credential gate (design docs/design/DESTRUCTIVE_CONFIRMATION_V1.md R-3)
# takes a real `FOR UPDATE` lock across every control-credential row for
# the duration of `control_credentials_unit_of_work` (`PostgresControl
# CredentialStore.list_all_for_update`) -- the same kind of lock-holding
# transaction `postgres.py`'s own `_set_timeouts` already bounds with a
# `SET LOCAL lock_timeout` on the DATA plane, so the control plane needs
# the identical discipline: a request that would otherwise wait forever
# behind a stuck/slow concurrent transaction must instead fail
# deterministically. Reuses `ResourceLimits`'s own default `execution_ms`
# (5000ms) for consistency with the data plane's own default budget --
# `ControlPlaneLimits` has no `execution_ms`-shaped field of its own to
# derive this from (R-7's 3 control-plane resource classes are
# applications/credentials_per_application/control_requests_per_minute,
# none of which is a lock/statement-timeout bound), so this is a fixed
# constant here rather than a configurable one, unlike the data plane's
# per-request budget.
_CONTROL_LOCK_TIMEOUT_MS = 5000


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

    # ---- CCR-14 WP-3 read additions (`ControlPlaneService`) ----------------

    def get_state(self, credential_id: str) -> tuple[bool, bool] | None:
        """`auth.CredentialStore.get_state`'s Postgres counterpart -- see
        that docstring for the full rationale (dual-store resolution + the
        control-plane HTTP `rotate` endpoint's own revoked-refusal check)."""
        statement = sql.SQL("SELECT enabled, revoked FROM {table} WHERE credential_id = {ph}").format(table=self._credentials_table, ph=sql.Placeholder())
        row = self._fetch_or_503(statement, [credential_id])
        return (row[0], row[1]) if row is not None else None

    def list_all(self) -> list[tuple[str, str, str, bool, bool]]:
        """`auth.CredentialStore.list_all`'s Postgres counterpart -- returns
        `(credential_id, application_id, role, enabled, revoked)` tuples,
        never `verifier` (not selected at all, so there is no column to
        forget to drop)."""
        statement = sql.SQL("SELECT credential_id, application_slug, role, enabled, revoked FROM {table} ORDER BY credential_id").format(table=self._credentials_table)
        try:
            with self._pool.connection() as conn:
                with conn.cursor() as cur:
                    _execute(cur, statement, [])
                    return cur.fetchall()
        except psycopg.Error:
            fail("AUTH_STATE_UNAVAILABLE", "Authorization state is unavailable.", status=503)
            raise  # unreachable; fail() always raises

    def count_active_for_application(self, application_id: str) -> int:
        """`auth.CredentialStore.count_active_for_application`'s Postgres
        counterpart (R-7 `credentials_per_application`: revoked rows are
        never counted)."""
        statement = sql.SQL("SELECT count(*) FROM {table} WHERE application_slug = {ph} AND NOT revoked").format(table=self._credentials_table, ph=sql.Placeholder())
        row = self._fetch_or_503(statement, [application_id])
        return int(row[0]) if row is not None else 0

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
            # Opus review minor m-5: `SET LOCAL lock_timeout`, mirroring
            # `postgres.py`'s own `_set_timeouts` (data plane) -- scoped to
            # this transaction only (discarded on commit/rollback, never
            # leaking onto the next transaction this pooled connection is
            # reused for). Bounds the last-active-control-credential gate's
            # own `FOR UPDATE` lock wait (`list_all_for_update`) so a
            # concurrent lock holder that never releases cannot wedge this
            # transaction open indefinitely.
            with conn.cursor() as cur:
                _execute(cur, sql.SQL("SET LOCAL lock_timeout = {t}").format(t=sql.Literal(f"{_CONTROL_LOCK_TIMEOUT_MS}ms")), [])
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
        statement = sql.SQL("SELECT credential_id, verifier, enabled, revoked, must_rotate, role FROM {table} WHERE verifier = {ph}").format(
            table=self._table, ph=sql.Placeholder()
        )
        row = self._fetch_or_503(statement, [computed])
        if row is None:
            fail("AUTH_INVALID", "Credential is not valid.", status=401)
        credential_id, db_verifier, enabled, revoked, must_rotate, role = row
        if not hmac.compare_digest(db_verifier, computed):
            fail("AUTH_INVALID", "Credential is not valid.", status=401)
        if revoked:
            _fail_identified("AUTH_REVOKED", "Credential is not active.", status=401, credential_id=credential_id, role=role)
        if not enabled:
            _fail_identified("AUTH_INVALID", "Credential is not active.", status=401, credential_id=credential_id, role=role)
        return ControlAuthContext(credential_id, must_rotate, role)

    def assert_active(self, context: ControlAuthContext) -> ControlAuthContext:
        if not self.available:
            fail("AUTH_STATE_UNAVAILABLE", "Authorization state is unavailable.", status=503)
        statement = sql.SQL("SELECT credential_id, enabled, revoked, must_rotate, role FROM {table} WHERE credential_id = {ph}").format(
            table=self._table, ph=sql.Placeholder()
        )
        row = self._fetch_or_503(statement, [context.credential_id])
        if row is None:
            fail("AUTH_INVALID", "Credential is not active.", status=401)
        credential_id, enabled, revoked, must_rotate, role = row
        if revoked:
            fail("AUTH_REVOKED", "Credential is not active.", status=401)
        if not enabled:
            fail("AUTH_INVALID", "Credential is not active.", status=401)
        return ControlAuthContext(credential_id, must_rotate, role)

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

    def add(self, credential_id: str, secret: str, *, role: str = "control", work: _PostgresWork) -> None:
        """Only reachable through `ops.py` (connected as `r2dbsvc_control`)
        -- `r2dbsvc_controlplane` (0006) is never granted INSERT on this
        table at all, so calling this against a control-plane-process
        connection fails at the database-privilege level (R-3), independent
        of this Python-level restriction. `work` is required (round-2
        ruling (A) -- see `PostgresCredentialStore.add`'s docstring for the
        full history).

        Phase 3.5 WP-4: `role` defaults to `"control"` (every pre-WP-4 caller
        -- `bootstrap_control_credential`/`reset_control_credentials` --
        is unaffected); `"audit"` is the one other accepted value, used only
        by `issue_audit_credential_ceremony` below. The table's own `CHECK
        (role IN ('control', 'audit'))` (0006, in-place WP-4 revision) is the
        authoritative enforcement; this Python-level check exists only to
        surface a clean `VALIDATION_FAILED` before ever reaching SQL.
        """
        if role not in {"control", "audit"}:
            fail("VALIDATION_FAILED", "Control-table credentials require control or audit role.")
        verifier = self.verifier(secret)
        statement = sql.SQL("INSERT INTO {table} (credential_id, verifier, role) VALUES ({id_ph}, {verifier_ph}, {role_ph})").format(
            table=self._table, id_ph=sql.Placeholder(), verifier_ph=sql.Placeholder(), role_ph=sql.Placeholder()
        )
        try:
            with work.connection.cursor() as cur:
                _execute(cur, statement, [credential_id, verifier, role])
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

    # ---- CCR-14 WP-3 read additions (`ControlPlaneService`) ----------------

    def get_state(self, credential_id: str) -> tuple[bool, bool] | None:
        """`auth.ControlCredentialStore.get_state`'s Postgres counterpart."""
        statement = sql.SQL("SELECT enabled, revoked FROM {table} WHERE credential_id = {ph}").format(table=self._table, ph=sql.Placeholder())
        row = self._fetch_or_503(statement, [credential_id])
        return (row[0], row[1]) if row is not None else None

    def list_all(self) -> list[tuple[str, bool, bool, bool, str]]:
        """`auth.ControlCredentialStore.list_all`'s Postgres counterpart --
        `(credential_id, enabled, revoked, must_rotate, role)` tuples.

        Phase 3.5 WP-4 (design §4/§1-B, P35-D7): `must_rotate` is now
        selected (it was deliberately omitted before this WP, §8 m-9 of the
        original design) -- `ControlPlaneService.list_credentials` exposes it
        on a control-plane credential row now that contract 1.3.0 makes the
        field optional-additive. `role` is likewise now selected so
        `list_credentials`' `role` key reads the real column instead of a
        hardcoded `"control"` literal (design §4, review m-6).
        """
        statement = sql.SQL("SELECT credential_id, enabled, revoked, must_rotate, role FROM {table} ORDER BY credential_id").format(table=self._table)
        try:
            with self._pool.connection() as conn:
                with conn.cursor() as cur:
                    _execute(cur, statement, [])
                    return cur.fetchall()
        except psycopg.Error:
            fail("AUTH_STATE_UNAVAILABLE", "Authorization state is unavailable.", status=503)
            raise  # unreachable; fail() always raises

    def list_all_for_update(self, work: _PostgresWork) -> list[tuple[str, bool, bool, str]]:
        """Row-locking counterpart to `list_all` above, used exclusively by
        `ControlPlaneService.revoke_credential`'s last-active-control-
        credential destructive-confirmation gate (design docs/design/
        DESTRUCTIVE_CONFIRMATION_V1.md R-3, WP-0 MA-2). `FOR UPDATE` with no
        `WHERE` locks every row in this table for the remainder of `work`'s
        transaction -- the gate's own count of active rows must not be able
        to change between this read and the state-changing `UPDATE`
        (`set_state`) that follows in the SAME transaction, closing the
        TOCTOU window a standalone count-then-write would leave between two
        concurrent revokes each independently observing "count = 2" and
        both proceeding unconfirmed. A concurrent `rotate`/`set_state`
        call's own single-row `SELECT ... FOR UPDATE` (see those methods
        above) blocks against this same lock too, since it necessarily
        locks a row this statement has already locked.

        Phase 3.5 WP-4: `role` is now selected too -- the gate's own "active"
        count (`ControlPlaneService.revoke_credential`) must count only
        `role="control"` rows; an `"audit"` credential existing alongside the
        sole active control credential must not be allowed to mask that
        control credential as "not the last one" (an audit credential cannot
        perform any control-plane management operation at all, so it does
        not relieve the lockout the gate exists to prevent).
        """
        statement = sql.SQL("SELECT credential_id, enabled, revoked, role FROM {table} ORDER BY credential_id FOR UPDATE").format(table=self._table)
        try:
            with work.connection.cursor() as cur:
                _execute(cur, statement, [])
                return cur.fetchall()
        except psycopg.Error:
            fail("SERVICE_UNAVAILABLE", "The database could not complete the request.", status=503)
            raise  # unreachable; fail() always raises


class PostgresApplicationRegistry:
    """CCR-14 WP-3: the Postgres-backed half of the "applications registry"
    store pair design docs/design/R2DB_CCR14_CONTROL_PLANE_V1.md §0/§3 calls
    for -- registration-only writes (R-4: this never touches the four
    provisioning columns; they stay NULL until the separate, out-of-band 0003
    provisioning flow -- `finish_provision_application` -- fills them in)
    plus the read/enable-flip surface `ControlPlaneService`'s `register_
    application`/`list_applications`/`set_application_enabled` operations
    need. There is no in-memory counterpart class: the in-memory backend
    (`control_plane.InMemoryControlBackend`) represents this same state
    directly via `DataService`'s own pre-existing `_cells`/`_disabled_apps`
    (design §0: "in-memory側はControlAuthority/DataServiceの既存状態に整合す
    る形--backend内で表現してよい") rather than duplicating a second registry.

    Deliberately stays inside the `r2dbsvc_controlplane` GRANT boundary
    (0006: SELECT/INSERT/UPDATE on `applications`, no DELETE) -- `register`
    only ever `INSERT`s a slug-only row (every provisioning column omitted,
    so they stay NULL, satisfying 0006's two-state CHECK), never anything
    that could look like a provisioning write; `set_enabled` only ever
    touches the `enabled` column. Mirrors `PostgresCredentialStore`/
    `PostgresControlCredentialStore` in every structural respect (dedicated
    `_RolePool`, D-4 SQL composition discipline, `_PostgresWork`-shaped
    `unit_of_work()`).
    """

    def __init__(
        self,
        dsn: str,
        *,
        schema: str = DEFAULT_SCHEMA,
        pool_size: int | None = None,
        connect_timeout: int | None = None,
        acquire_timeout: float | None = None,
    ) -> None:
        validate_identifier(schema)
        maxconn = pool_size if pool_size is not None else _env_int("R2DB_PLATFORM_POOL_SIZE", 4)
        pool_kwargs: dict[str, Any] = {}
        if connect_timeout is not None:
            pool_kwargs["connect_timeout"] = connect_timeout
        if acquire_timeout is not None:
            pool_kwargs["acquire_timeout"] = acquire_timeout
        self._pool = _RolePool(dsn, schema=schema, maxconn=maxconn, **pool_kwargs)
        self._schema = schema
        self._table = sql.Identifier(schema, "applications")

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

    def register(self, application_id: str, *, work: _PostgresWork) -> None:
        """Registration-only `INSERT` -- every provisioning column (`database_
        name`/`runtime_role`/`developer_role`/`provisioned_at`) is omitted, so
        each stays `NULL`, satisfying 0006's two-state CHECK as a "registered,
        not yet provisioned" row (R-4)."""
        statement = sql.SQL("INSERT INTO {table} (application_slug) VALUES ({ph})").format(table=self._table, ph=sql.Placeholder())
        try:
            with work.connection.cursor() as cur:
                _execute(cur, statement, [application_id])
        except psycopg.errors.UniqueViolation:
            fail("CONFLICT", "Application already exists.", status=409)
        except psycopg.Error:
            fail("SERVICE_UNAVAILABLE", "The database could not complete the request.", status=503)

    def set_enabled(self, application_id: str, enabled: bool, *, work: _PostgresWork) -> None:
        statement = sql.SQL(
            "UPDATE {table} SET enabled = {enabled_ph} WHERE application_slug = {id_ph} RETURNING application_slug"
        ).format(table=self._table, enabled_ph=sql.Placeholder(), id_ph=sql.Placeholder())
        try:
            with work.connection.cursor() as cur:
                _execute(cur, statement, [enabled, application_id])
                row = cur.fetchone()
                if row is None:
                    fail("NOT_FOUND", "Application was not found.", status=404)
        except psycopg.Error:
            fail("SERVICE_UNAVAILABLE", "The database could not complete the request.", status=503)

    def set_issuance_frozen(self, application_id: str, frozen: bool, *, work: _PostgresWork) -> None:
        """Phase 3.5 WP-4 (design §4/§1-E, P35-D6): CLI-only, non-destructive
        (mirrors `set_enabled` above -- no declare-and-echo confirmation
        gate, same class as disable-app). There is no in-band endpoint that
        calls this -- only `ops.py freeze-issuance`/`unfreeze-issuance`."""
        statement = sql.SQL(
            "UPDATE {table} SET issuance_frozen = {frozen_ph} WHERE application_slug = {id_ph} RETURNING application_slug"
        ).format(table=self._table, frozen_ph=sql.Placeholder(), id_ph=sql.Placeholder())
        try:
            with work.connection.cursor() as cur:
                _execute(cur, statement, [frozen, application_id])
                row = cur.fetchone()
                if row is None:
                    fail("NOT_FOUND", "Application was not found.", status=404)
        except psycopg.Error:
            fail("SERVICE_UNAVAILABLE", "The database could not complete the request.", status=503)

    def issuance_frozen(self, application_id: str) -> bool:
        """`ControlPlaneService.issue_credential`'s own read of this flag
        (design §4/§1-E): evaluated only after the `role=control` capability
        refusal and the target-existence check (contract `issue_credential.
        semantics`' own precedence sentence; C-14 vector 3 discipline).
        Returns `False` for an unknown `application_id` -- callers reach
        this only after already confirming the application exists."""
        statement = sql.SQL("SELECT issuance_frozen FROM {table} WHERE application_slug = {ph}").format(table=self._table, ph=sql.Placeholder())
        try:
            with self._pool.connection() as conn:
                with conn.cursor() as cur:
                    _execute(cur, statement, [application_id])
                    row = cur.fetchone()
                    return bool(row[0]) if row else False
        except psycopg.Error:
            fail("SERVICE_UNAVAILABLE", "The database could not complete the request.", status=503)
            raise  # unreachable; fail() always raises

    def exists(self, application_id: str) -> bool:
        statement = sql.SQL("SELECT EXISTS(SELECT 1 FROM {table} WHERE application_slug = {ph})").format(table=self._table, ph=sql.Placeholder())
        try:
            with self._pool.connection() as conn:
                with conn.cursor() as cur:
                    _execute(cur, statement, [application_id])
                    row = cur.fetchone()
                    return bool(row[0]) if row else False
        except psycopg.Error:
            fail("SERVICE_UNAVAILABLE", "The database could not complete the request.", status=503)
            raise  # unreachable; fail() always raises

    def count(self) -> int:
        statement = sql.SQL("SELECT count(*) FROM {table}").format(table=self._table)
        try:
            with self._pool.connection() as conn:
                with conn.cursor() as cur:
                    _execute(cur, statement, [])
                    row = cur.fetchone()
                    return int(row[0]) if row else 0
        except psycopg.Error:
            fail("SERVICE_UNAVAILABLE", "The database could not complete the request.", status=503)
            raise  # unreachable; fail() always raises

    def list_all(self) -> list[tuple[str, bool]]:
        statement = sql.SQL("SELECT application_slug, enabled FROM {table} ORDER BY application_slug").format(table=self._table)
        try:
            with self._pool.connection() as conn:
                with conn.cursor() as cur:
                    _execute(cur, statement, [])
                    return cur.fetchall()
        except psycopg.Error:
            fail("SERVICE_UNAVAILABLE", "The database could not complete the request.", status=503)
            raise  # unreachable; fail() always raises


# Phase 3.5 WP-4 (design PHASE35_CROSS_ENTITY_AND_CONTRACT_130_V1.md §1-C/§4,
# B-1 measure): `target_id` is the contract's 13th, optional `audit.fields`
# member -- appended at the end (matching the contract's own field-list
# order) rather than interleaved, so every existing positional reader of
# this tuple keeps working on its first 12 elements unchanged.
_CONTROL_AUDIT_COLUMNS = (
    "event_id", "event_class", "occurred_at", "request_id", "application_id",
    "actor_type", "actor_id", "role", "operation", "target_kind", "outcome", "reason_code",
    "target_id",
)
_CONTROL_AUDIT_INSERT = (
    "INSERT INTO {table} (event_id, event_class, occurred_at, request_id, application_id, "
    "actor_type, actor_id, role, operation, target_kind, outcome, reason_code, target_id) "
    "VALUES ({ph0}, {ph1}, {ph2}, {ph3}, {ph4}, {ph5}, {ph6}, {ph7}, {ph8}, {ph9}, {ph10}, {ph11}, {ph12})"
)


class PostgresControlAuditSink:
    """CCR-14 WP-3, R-6: the durable control-plane audit trail's Postgres
    half -- writes to `r2dbsvc_registry.control_audit` (0006). Lives here,
    not in `audit.py`, so that `audit.py` (imported unconditionally by
    `service.py`, and therefore the top-level `r2db_api` package) never
    gains a `psycopg` import -- see `audit.ControlAuditSink`'s docstring for
    the full rationale (mirrors the existing `CredentialStore`/
    `PostgresCredentialStore` module split).

    `append(..., work=None)`: when `work` is given (any of this file's
    `_PostgresWork` handles -- `PostgresApplicationRegistry.unit_of_work()`/
    `PostgresCredentialStore.unit_of_work()`/`PostgresControlCredentialStore.
    unit_of_work()`, whichever the caller's state change just used), the
    `INSERT` executes on `work.connection` -- the *same* connection/
    transaction the caller's state change used (R-6: "状態変更とcontrol_
    auditのINSERTを同一トランザクションでcommit"), so a failure here aborts
    that caller's whole `with store.unit_of_work()` block through the normal
    exception path, exactly like any other statement failing on that
    connection -- no special-casing needed. When `work` is omitted (the
    denial-event path, R-6: "拒否には状態変更が無いので独立トランザクション
    のINSERTで足りる"), this opens and commits its own single-statement
    transaction on its own pool.
    """

    def __init__(
        self,
        dsn: str,
        *,
        schema: str = DEFAULT_SCHEMA,
        pool_size: int | None = None,
        connect_timeout: int | None = None,
        acquire_timeout: float | None = None,
    ) -> None:
        validate_identifier(schema)
        maxconn = pool_size if pool_size is not None else _env_int("R2DB_PLATFORM_POOL_SIZE", 4)
        pool_kwargs: dict[str, Any] = {}
        if connect_timeout is not None:
            pool_kwargs["connect_timeout"] = connect_timeout
        if acquire_timeout is not None:
            pool_kwargs["acquire_timeout"] = acquire_timeout
        self._pool = _RolePool(dsn, schema=schema, maxconn=maxconn, **pool_kwargs)
        self._schema = schema
        self._table = sql.Identifier(schema, "control_audit")

    def close(self) -> None:
        self._pool.close_all()

    def append(
        self,
        *,
        event_class: str,
        request_id: str,
        application_id: str | None,
        actor_type: str,
        actor_id: str | None,
        role: str | None,
        operation: str,
        target_kind: str | None,
        outcome: str,
        reason_code: str | None = None,
        target_id: str | None = None,
        work: _PostgresWork | None = None,
    ) -> None:
        event_id = str(uuid.uuid4())
        occurred_at = datetime.now(timezone.utc)
        placeholders = {f"ph{i}": sql.Placeholder() for i in range(13)}
        statement = sql.SQL(_CONTROL_AUDIT_INSERT).format(table=self._table, **placeholders)
        params = [event_id, event_class, occurred_at, request_id, application_id, actor_type, actor_id, role, operation, target_kind, outcome, reason_code, target_id]
        if work is not None:
            # Same connection/transaction as the caller's state change --
            # deliberately no try/except here: a failure must propagate as
            # the caller's own `unit_of_work()` exception (rolling back the
            # state change too), never be swallowed or re-mapped at this
            # layer (R-6/fail-closed-by-construction).
            with work.connection.cursor() as cur:
                _execute(cur, statement, params)
            return
        # Standalone (denial-event) path: this call owns its own connection
        # and transaction. A `psycopg.Error` here propagates to the caller
        # (`ControlPlaneService._deny`), which maps it to `SERVICE_UNAVAILABLE`
        # (503) -- this method itself does not know about `FoundationError`.
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                _execute(cur, statement, params)
            conn.commit()

    def events(self) -> list[tuple[Any, ...]]:
        """Read surface for tests/tooling connected with sufficient privilege
        (`r2dbsvc_control`, never the control-plane process' own `r2dbsvc_
        controlplane` role, which has no SELECT on this table at all -- R-3).
        Design §0: "読み取りsurface(events())はin-memory/Postgres双方に用意
        (WP-5のportcontrol_audit_events()とWP-6のaudit-reportが使う)".

        Round-2 review MI-8: routed through `_execute` (D-4's single
        execution choke point, like every other statement in this file) and
        the module's own `psycopg.Error` -> `AUTH_STATE_UNAVAILABLE` (503)
        discipline (`_fetch_or_503`'s pattern) -- this method previously
        called `cur.execute` directly and let a connection failure propagate
        as a raw `psycopg.Error`, the one read path in this file that had not
        been brought under that discipline yet.

        WP-5 round-2 review NIT-4: `ORDER BY recorded_at` alone is not a
        total order -- `recorded_at` is `DEFAULT now()`, a single
        transaction-start timestamp, so two events inserted by the same
        transaction (a state-change row + nothing else shares a
        transaction today, but this is a durability property this method
        should not assume stays true forever) or by two transactions that
        happen to commit within the same clock tick can tie. This became
        load-bearing this WP: C-15 vector 2's own prefix assertion
        (`after_audit[:len(before_audit)] == before_audit`) needs a stable,
        repeatable ordering across the `before`/`after` calls, not merely
        "some order consistent with `recorded_at`" -- `event_id` (the
        primary key, application-generated per `AuditSink.append`) is the
        deterministic tiebreaker.
        """
        statement = sql.SQL("SELECT {columns} FROM {table} ORDER BY recorded_at, event_id").format(
            columns=sql.SQL(", ").join(sql.Identifier(name) for name in _CONTROL_AUDIT_COLUMNS), table=self._table
        )
        try:
            with self._pool.connection() as conn:
                with conn.cursor() as cur:
                    _execute(cur, statement, [])
                    return cur.fetchall()
        except psycopg.Error:
            fail("AUTH_STATE_UNAVAILABLE", "Authorization state is unavailable.", status=503)
            raise  # unreachable; fail() always raises


__all__ = [
    "PostgresCredentialStore",
    "PostgresControlCredentialStore",
    "PostgresApplicationRegistry",
    "PostgresControlAuditSink",
    "validate_control_pepper_separation",
    "DEFAULT_SCHEMA",
]
