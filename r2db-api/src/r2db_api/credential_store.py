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
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import os
from typing import Any, Iterator, Mapping, Sequence
import uuid

import psycopg
from psycopg import sql

from .auth import AuthContext, ControlAuthContext, _DUMMY_VERIFIER, _fail_identified, compose_bearer_locator, split_bearer_locator
from .errors import FoundationError, fail
from .postgres import _RolePool, _env_int
from .structured import validate_identifier

DEFAULT_SCHEMA = "r2dbsvc_registry"

# Phase 4 (design D-6/N-3; WP-2(a) fix round 2 review N-6): the two
# writer-connection SESSION-level timeout defaults, shared by BOTH
# composition roots (`r2db_api.main.build_app` / `r2db_api.control_main.
# build_control_app`) as ONE definition -- a WP-2(b) `visibility_lag_ms`
# declaration is derived from these two values under the assumption that
# BOTH processes' writer connections carry the identical policy; two
# independently-maintained literals (one per composition root) could
# silently drift apart with no test catching it. Both composition roots
# import these names directly rather than defining their own.
DEFAULT_AUDIT_STATEMENT_TIMEOUT_MS = 5000
DEFAULT_AUDIT_IDLE_TIMEOUT_MS = 5000

# the control plane's own last-active-control-credential gate (design
# docs/design/DESTRUCTIVE_CONFIRMATION_V1.md R-3) takes a real `FOR UPDATE`
# lock across every control-credential row for the duration of
# `control_credentials_unit_of_work`
# (`PostgresControlCredentialStore.list_all_for_update`) -- the same kind of
# lock-holding transaction `postgres.py`'s own `_set_timeouts` already bounds
# with a `SET LOCAL lock_timeout` on the DATA plane, so the control plane
# needs the identical discipline: a request that would otherwise wait forever
# behind a stuck/slow concurrent transaction must instead fail
# deterministically. Reuses `ResourceLimits`'s own default `execution_ms`
# (5000ms) for consistency with the data plane's own default budget --
# `ControlPlaneLimits` has no `execution_ms`-shaped field of its own to
# derive this from (R-7's 3 control-plane resource classes are
# applications/credentials_per_application/control_requests_per_minute, none
# of which is a lock/statement-timeout bound), so this is a fixed constant
# here rather than a configurable one, unlike the data plane's per-request
# budget.
# history: CH-0381
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
# `_SELECT_BY_VERIFIER` (the digest-keyed lookup) is REMOVED, not merely
# unused -- authentication is now a locator lookup (`_SELECT_BY_ID`, below)
# followed by `compare_digest`, never a `WHERE verifier = ...` scan.
# `_SELECT_BY_ID` was already this store's
# `assert_active`/`canonical_context`/`application_id_for` lookup;
# `authenticate` now shares it too.
# history: CH-0383
_SELECT_BY_ID = "SELECT {columns}, a.enabled FROM {credentials} c JOIN {applications} a ON a.application_slug = c.application_slug WHERE c.credential_id = {ph}"

# Phase 6 WP-2 (design D-1(c), r2db decision (c)'s own "control 側にも
# `_SELECT_BY_ID` 相当を新設する" item): the control-credential table's own
# named credential_id-keyed lookup, used by BOTH `PostgresControlCredential
# Store.authenticate` (below, replacing its former inline `WHERE verifier =
# {ph}` text) and `.assert_active` (already credential_id-keyed before this
# WP) -- the same "one named constant, not an inline literal repeated at
# each call site" discipline `_SELECT_BY_ID` above already follows for the
# application-credential table.
_CONTROL_SELECT_BY_ID = "SELECT credential_id, verifier, enabled, revoked, must_rotate, role FROM {table} WHERE credential_id = {ph}"


def _execute(cursor: "psycopg.Cursor[Any]", statement: sql.Composed | sql.SQL, params: Sequence[Any] | Mapping[str, Any] = ()) -> None:
    """The single execution choke point for this file -- mirrors
    `postgres.py::_run`'s identical role there. Typed to accept only a
    composed psycopg SQL object, never `str`, so a raw string cannot reach
    the database from anywhere in this module.

    `params` now also accepts a `Mapping` (psycopg3's own `%(name)s`-style
    binding) -- `PostgresAuditQueryStore.query`'s own `audit_query` UNION
    statement below reuses several parameters (the visibility-lag
    threshold, the cursor triple, the class filter) at multiple positions
    in the composed SQL text, which named binding expresses far more
    directly than repeating the same positional placeholder object many
    times. Every pre-existing caller in this file still passes a
    `Sequence`, unaffected.

    History: CH-0384
    """
    if not isinstance(statement, (sql.Composed, sql.SQL)):
        raise TypeError("credential_store.py only executes psycopg.sql.Composed/SQL objects, never str")
    cursor.execute(statement, params if isinstance(params, Mapping) else list(params))


_BOUND_ADVISORY_LOCK_STATEMENT = sql.SQL("SELECT pg_advisory_xact_lock(hashtext(%s))")


def _take_bound_advisory_lock(cursor: "psycopg.Cursor[Any]", *, schema: str, table: str) -> None:
    """Phase 10 WP-6a (design docs/design/PHASE10_DEPLOYMENT_EVIDENCE_V1.md
    D-5(ii) addendum (2); supervisor ruling `scratchpad/phase10/wp6-
    rulings.md` #1, closing review finding F1): the lock every region-(iii)
    process-ceiling bound (`applications`, `credentials_per_application`)
    takes immediately before its own count, in the SAME transaction that
    then performs the INSERT -- `PostgresApplicationRegistry.count_locked`
    and `PostgresCredentialStore.count_active_for_application_locked`
    below are this function's only two callers.

    This is `pg_advisory_xact_lock(hashtext(<key>))`, NOT `LOCK TABLE ...
    IN SHARE MODE` (this function's own pre-review-round-3 form, which the
    design addendum names and forbids explicitly): SHARE conflicts with
    the ROW EXCLUSIVE the following INSERT needs, but SHARE never
    conflicts with a concurrent SHARE, so two concurrent callers could
    both acquire SHARE, both read a count one under the limit, and only
    THEN each block on the other's INSERT -- a genuine deadlock, not
    merely the widened TOCTOU window the pre-WP-6a code had (reproduced
    against a real PostgreSQL 16 running this exact idiom, barrier-
    synchronized: `{1: 'DeadlockDetected', 2: 'OK'}`).
    `pg_advisory_xact_lock` is exclusive against itself instead: a second
    caller taking the SAME key blocks until the first caller's
    transaction commits or rolls back, so by the time it proceeds, its
    own count is guaranteed to already reflect the first caller's INSERT
    (or its absence, if the first rolled back) -- closing the TOCTOU
    window without ever letting two holders past the count at once.
    (Phase 9 R-2's own `LOCK TABLE ... IN SHARE ROW EXCLUSIVE MODE` (SHARE
    MODE until Phase 10 R-35), `postgres.py`'s
    `add_field`/`alter_field`, is NOT a precedent for this idiom -- it
    guards a read-then-DDL existence scan against a *concurrent schema
    change*, not a count-then-INSERT bound; citing it as this idiom's
    precedent, as an earlier version of this WP's own report did, was an
    error. The actual precedent the design addendum points to is `ops.
    py`'s `_RITUAL_ADVISORY_LOCK_KEY`/`_lock_ritual` -- a `pg_advisory_
    xact_lock` on a fixed key, confirmed here to hold the same "exclusive
    against itself, transaction-scoped, never leaked past one
    transaction" contract this function relies on, and NOT the mistaken
    "SHARE blocks a second SHARE" reasoning this function's own docstring
    used to (incorrectly) claim.)

    The key is a per-table *constant* -- `hashtext('<schema>.<table>')`,
    the same string-keyed idiom this repository already uses for
    `pg_advisory_lock(hashtext(%s))` in `conformance_adapter_r2db_http.
    py`'s own prefix guard, here transaction-scoped instead of session-
    scoped -- one fixed 32-bit int per table, in the same class as `ops.
    py`'s own `_RITUAL_ADVISORY_LOCK_KEY`, never a per-row/per-key value
    (unlike WP-6d-i's idempotency-key lock). Scoped per table, not one
    shared key for every bound, so concurrent `applications` and
    `credentials_per_application` traffic never contend with each other,
    only with itself."""
    _execute(cursor, _BOUND_ADVISORY_LOCK_STATEMENT, [f"{schema}.{table}"])


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
        validate_identifier(schema, field="schema")
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

    # ---- region (ii), wired `requests_per_minute` (design D-3 (1)) ------

    def record_rate_and_check(self, credential_id: str, limit: int) -> bool:
        """(design docs/design/MULTI_PROCESS_WORKER_V0_1.md D-3 (1)):
        one round trip against migration `0015`'s
        own `credential_request_rate_admit` function, on THIS store's
        OWN pool (the same `r2dbsvc_api` pool `authenticate`/`assert_
        active` already read from, toggled to autocommit for this one
        statement -- see below) -- never the credentials table itself,
        and never a second, dedicated pool. Called from `service.py`'s `_acquire_
        rate` AFTER the caller's own authentication borrow has already
        returned its connection -- this
        method's own borrow-execute-return is a single, separate unit of
        work, never nested inside another.

        Returns `True` when the request is admitted (this credential's
        own `requests_per_minute` window, shared by every worker process
        this deployment runs, was strictly under `limit` before this
        call), `False` when it is not -- the caller (`service.py`) maps
        `False` to the SAME `LIMIT_EXCEEDED`/`requests_per_minute` denial
        the pre-existing in-memory window already raised. A PostgreSQL
        failure raises `FoundationError(SERVICE_UNAVAILABLE, 503)`
        instead of returning either boolean:
        fail-closed, never silently admitted nor silently denied, mirroring
        every other write in this class (`add`/`set_state`/`rotate`).
        """
        statement = sql.SQL("SELECT {schema}.credential_request_rate_admit(%s, %s)").format(
            schema=sql.Identifier(self._schema)
        )
        try:
            with self._pool.connection() as conn:
                # `_RolePool._connect` opens every connection with
                # `autocommit=False` (this pool's own general-purpose
                # default -- every OTHER write in this class runs inside
                # an explicit `unit_of_work()`/`conn.commit()` instead).
                # This call is the one exception (design D-3 (1): the
                # rate count is one statement):
                # toggled to `True` for the duration of this ONE
                # statement, exactly like `_RolePool._liveness_check`'s
                # own temporary toggle, and restored to `False` in
                # `finally` before the connection is ever returned to the
                # pool -- so the rate statement commits immediately, on
                # its own, never joining any other caller's transaction.
                conn.autocommit = True
                try:
                    with conn.cursor() as cur:
                        _execute(cur, statement, [credential_id, limit])
                        (admitted,) = cur.fetchone()
                finally:
                    conn.autocommit = False
        except psycopg.Error:
            fail("SERVICE_UNAVAILABLE", "The database could not complete the request.", status=503)
            raise  # unreachable; fail() always raises
        return bool(admitted)

    # ---- shared verifier computation (identical to `auth.CredentialStore`) --

    def verifier(self, secret: str) -> str:
        if not isinstance(secret, str):
            fail("VALIDATION_FAILED", "Credential secret has an invalid type.")
        return hmac.new(self._pepper, secret.encode(), hashlib.sha256).hexdigest()

    # ---- read path (P2-D4: every call below queries PostgreSQL fresh) -----

    def authenticate(self, secret: str | None) -> AuthContext:
        """Phase 6 WP-2 (design D-1(c), L6-1 (i)/(iv)): `secret` is the
        presented bearer's locator form `<credential_id>.<secret_part>`
        (`auth.split_bearer_locator`). Authentication is now a `credential_
        id`-keyed row lookup (`_SELECT_BY_ID` -- the SAME statement `assert_
        active`/`canonical_context`/`application_id_for` already use, not a
        digest-keyed `WHERE verifier = ...` scan), followed by `hmac.
        compare_digest` against the row's stored `verifier`. Unlike the pre-
        WP-2 form, that `compare_digest` call is now THE authoritative
        check -- a `credential_id` alone identifies no secret at all (it is
        non-secret, R-2's own reasoning: it appears in `list_credentials`
        responses), so nothing above this comparison has verified anything
        about the presented secret; skipping it would authenticate on the
        locator's id half alone. `verifier`'s own `UNIQUE` constraint
        (`0005_credential_store.sql`) is unrelated to this lookup path now
        -- it remains a structural guarantee that no two credentials can
        ever collide on the same verifier, not an index this method
        queries by.
        """
        if not self.available:
            fail("AUTH_STATE_UNAVAILABLE", "Authorization state is unavailable.", status=503)
        if not secret:
            fail("AUTH_REQUIRED", "Authentication is required.", status=401)
        locator = split_bearer_locator(secret)
        if locator is None:
            # SI-15 fail-closed: malformed locator, no lookup attempted.
            fail("AUTH_INVALID", "Credential is not valid.", status=401)
        credential_id, secret_part = locator
        computed = self.verifier(secret_part)
        statement = sql.SQL(_SELECT_BY_ID).format(
            columns=sql.SQL(_COLUMNS), credentials=self._credentials_table, applications=self._applications_table, ph=sql.Placeholder()
        )
        row = self._fetch_or_503(statement, [credential_id])
        # Coordinator item 7(i): `compare_digest` runs UNCONDITIONALLY --
        # against the real `db_verifier` when a row was found, against the
        # fixed-shape `auth._DUMMY_VERIFIER` otherwise -- so a `credential_
        # id` this table does not have costs the same one comparison a
        # real-but-mismatched one does (no timing oracle for row
        # existence, mirrors `auth.CredentialStore.authenticate`'s own
        # identical rework).
        db_verifier = row[3] if row is not None else _DUMMY_VERIFIER
        digest_matches = hmac.compare_digest(db_verifier, computed)
        if row is None or not digest_matches:
            # Design implementation constraint 2: an unknown locator and a
            # known locator with a digest mismatch (below) are both a bare,
            # uniform AUTH_INVALID -- SI-10 gives no signal distinguishing
            # them. Constraint 3: the client-declared `credential_id` is
            # never attached to this denial.
            fail("AUTH_INVALID", "Credential is not valid.", status=401)
        row_credential_id, application_id, role, _db_verifier, enabled, revoked, app_enabled = row
        # Design implementation constraint 1: `compare_digest` (above) runs
        # -- and must succeed -- BEFORE `revoked`/`enabled`/`app_enabled`
        # below, exactly as the pre-WP-2 ordering already was.
        if revoked:
            fail("AUTH_REVOKED", "Credential is not active.", status=401)
        if not enabled:
            fail("AUTH_INVALID", "Credential is not active.", status=401)
        if not app_enabled:
            fail("APPLICATION_DISABLED", "Application is disabled.", status=403)
        return AuthContext(row_credential_id, application_id, role)

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
        counterpart (`credentials_per_application`: revoked rows are
        never counted).

        History: CH-0386
        """
        statement = sql.SQL("SELECT count(*) FROM {table} WHERE application_slug = {ph} AND NOT revoked").format(table=self._credentials_table, ph=sql.Placeholder())
        row = self._fetch_or_503(statement, [application_id])
        return int(row[0]) if row is not None else 0

    def count_active_for_application_locked(self, application_id: str, work: _PostgresWork) -> int:
        """Phase 10 WP-6a (design docs/design/PHASE10_DEPLOYMENT_EVIDENCE_
        V1.md D-5(ii) addendum (2)): the row-locking counterpart to
        `count_active_for_application` above, used exclusively by
        `ControlPlaneService.issue_credential`'s own `credentials_per_
        application` limit gate. Takes `_take_bound_advisory_lock` (a
        table-scoped constant-key `pg_advisory_xact_lock` -- see that
        function's own docstring for the full rationale, including why
        `LOCK TABLE ... IN SHARE MODE`, this method's pre-review-round-3
        form, deadlocks instead of merely widening the TOCTOU window) on
        `work`'s own connection, BEFORE the count: a second concurrent
        `issue_credential` call's own `count_active_for_application_
        locked` -- which takes the SAME key -- blocks until THIS
        transaction commits or rolls back, at which point its count is
        guaranteed to already reflect this call's INSERT (or its
        absence)."""
        try:
            with work.connection.cursor() as cur:
                _take_bound_advisory_lock(cur, schema=self._schema, table="credentials")
                _execute(
                    cur,
                    sql.SQL("SELECT count(*) FROM {table} WHERE application_slug = {ph} AND NOT revoked").format(table=self._credentials_table, ph=sql.Placeholder()),
                    [application_id],
                )
                row = cur.fetchone()
                return int(row[0]) if row else 0
        except psycopg.Error:
            fail("SERVICE_UNAVAILABLE", "The database could not complete the request.", status=503)
            raise  # unreachable; fail() always raises

    # ---- write path (P2-D6: reused directly by `python -m r2db_api.ops`) --

    def add(self, credential_id: str, application_id: str, role: str, secret: str, *, work: _PostgresWork) -> str:
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

        Rework (coordinator item 3): returns the composed bearer
        (`auth.compose_bearer_locator(credential_id, secret)`) -- same
        "issuance point returns the ready-to-present bearer, never the
        caller" discipline as `auth.CredentialStore.add`'s own identical
        rework; see that docstring for the full rationale.
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
        return compose_bearer_locator(credential_id, secret)

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

    def rotate(self, credential_id: str, secret: str, *, work: _PostgresWork) -> str:
        """Not part of `auth.CredentialStore`'s call surface (that class
        has no rotation concept at all) -- added here because
        `python -m r2db_api.ops rotate-credential` (P2-D6) needs
        exactly this one extra operation, and computing/writing a
        verifier is already this class's own responsibility;
        duplicating that SQL a second time in `ops.py` would only risk
        the two copies drifting apart. P2-D6: "同一 credential_id の
        verifier を差し替える" -- rotation reuses the existing
        `credential_id`, `role`, and `application_slug`, replacing only
        `verifier` (so the old secret stops authenticating and the new
        one starts, with no other lifecycle state introduced). this
        method still does not check `revoked` (§8 M-2's finding about
        this exact method -- see `auth.CredentialStore.rotate`'s
        docstring for why the new in-memory `rotate` was written to
        match this, not the other way around). `work` is required
        (round-2 ruling (A)).

        Rework (coordinator follow-up audit finding §3-A): returns the
        composed bearer (`auth.compose_bearer_locator(credential_id,
        secret)`) -- `ops.py cmd_rotate_credential` now uses this
        return value verbatim instead of composing it itself.

        History: CH-0388
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
        return compose_bearer_locator(credential_id, secret)

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
    """wherever a process' configuration carries *both* the application-plane
    pepper (`R2DB_CREDENTIAL_PEPPER`) and the control-plane pepper
    (`R2DB_CONTROL_CREDENTIAL_PEPPER`), the two values must differ. An
    operator who (by mistake, e.g. copy-paste from one secret-manager entry
    to both env var names) configures them identically would make an
    application credential's verifier and a control credential's verifier
    collide under the same underlying secret string -- silently punching a
    hole through R-2's "control credential storage is unreadable from the
    application plane" wall via pepper reuse rather than any table/grant
    mistake.

    Called from `ops.py`'s control-credential ritual/break-glass command
    constructors today -- design docs/design/R2DB_CCR14_CONTROL_PLANE_V1.md
    §1 R-2 calls this "共通経路" (a shared path): a future composition root
    that ever constructs both an application-plane and a control-plane
    store in the same process must call this too, which is why this lives
    here (imported by both `ops.py` and, in the future, `main.py`/`control_main.
    py`) rather than being duplicated at each call site.

    History: CH-0390
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
        validate_identifier(schema, field="schema")
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
            # `SET LOCAL lock_timeout`, mirroring `postgres.py`'s
            # own `_set_timeouts` (data plane) -- scoped to this
            # transaction only (discarded on commit/rollback,
            # never leaking onto the next transaction this pooled
            # connection is reused for). Bounds the
            # last-active-control-credential gate's own
            # `FOR UPDATE` lock wait (`list_all_for_update`) so a
            # concurrent lock holder that never releases cannot
            # wedge this transaction open indefinitely.
            # history: CH-0392
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
        """locator-then-digest, mirroring
        `PostgresCredentialStore.authenticate`'s own rewrite above --
        see that method's docstring for the full rationale. The former
        inline `WHERE verifier = {ph}` lookup is gone; this now shares
        `_CONTROL_SELECT_BY_ID` with `assert_active` below.

        History: CH-0393
        """
        if not self.available:
            fail("AUTH_STATE_UNAVAILABLE", "Authorization state is unavailable.", status=503)
        if not secret:
            fail("AUTH_REQUIRED", "Authentication is required.", status=401)
        locator = split_bearer_locator(secret)
        if locator is None:
            fail("AUTH_INVALID", "Credential is not valid.", status=401)
        credential_id, secret_part = locator
        computed = self.verifier(secret_part)
        statement = sql.SQL(_CONTROL_SELECT_BY_ID).format(table=self._table, ph=sql.Placeholder())
        row = self._fetch_or_503(statement, [credential_id])
        # Coordinator item 7(i): unconditional compare_digest -- see
        # `PostgresCredentialStore.authenticate`'s identical comment above.
        db_verifier = row[1] if row is not None else _DUMMY_VERIFIER
        digest_matches = hmac.compare_digest(db_verifier, computed)
        if row is None or not digest_matches:
            fail("AUTH_INVALID", "Credential is not valid.", status=401)
        row_credential_id, _db_verifier, enabled, revoked, must_rotate, role = row
        if revoked:
            _fail_identified("AUTH_REVOKED", "Credential is not active.", status=401, credential_id=row_credential_id, role=role)
        if not enabled:
            _fail_identified("AUTH_INVALID", "Credential is not active.", status=401, credential_id=row_credential_id, role=role)
        return ControlAuthContext(row_credential_id, must_rotate, role)

    def assert_active(self, context: ControlAuthContext) -> ControlAuthContext:
        if not self.available:
            fail("AUTH_STATE_UNAVAILABLE", "Authorization state is unavailable.", status=503)
        statement = sql.SQL(_CONTROL_SELECT_BY_ID).format(table=self._table, ph=sql.Placeholder())
        row = self._fetch_or_503(statement, [context.credential_id])
        if row is None:
            fail("AUTH_INVALID", "Credential is not active.", status=401)
        credential_id, _verifier, enabled, revoked, must_rotate, role = row
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
        """Only reachable through `ops.py` (connected as
        `r2dbsvc_control`) -- `r2dbsvc_controlplane` (0006) is never
        granted INSERT on this table at all, so calling this against a
        control-plane-process connection fails at the
        database-privilege level, independent of this Python-level
        restriction. `work` is required (round-2 ruling (A) -- see
        `PostgresCredentialStore.add`'s docstring for the full
        history).

        `role` defaults to `"control"` (every pre-WP-4 caller --
        `bootstrap_control_credential`/`reset_control_credentials` --
        is unaffected); `"audit"` is the one other accepted value, used
        only by `issue_audit_credential_ceremony` below. The table's
        own `CHECK (role IN ('control', 'audit'))` (0006, in-place
        revision) is the authoritative enforcement; this Python-level
        check exists only to surface a clean `VALIDATION_FAILED` before
        ever reaching SQL.

        History: CH-0394
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

    def rotate(self, credential_id: str, secret: str, *, work: _PostgresWork) -> str:
        """R-5/§2 M-2: verifier replacement + `must_rotate = false` +
        `updated_at` refresh, one statement. A revoked row is refused
        (`VALIDATION_FAILED`) via the same `FOR UPDATE`-then-check pattern
        `set_state` above uses, rather than trusting a bare `UPDATE ...
        WHERE revoked = false` to have matched zero rows for the right
        reason (that would return `NOT_FOUND` for an existing-but-revoked
        row, indistinguishable from "no such credential" -- a strictly
        worse error for the caller than the dedicated `VALIDATION_FAILED`
        this gives instead). `work` is required (round-2 ruling (A)).

        Rework (coordinator follow-up audit finding §3-A): returns the
        composed bearer -- `ops.py cmd_rotate_control_credential` now
        uses this return value verbatim.

        History: CH-0395
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
        return compose_bearer_locator(credential_id, secret)

    def has_any(self, *, include_revoked: bool = True, work: _PostgresWork | None = None) -> bool:
        """bootstrap's existence check, real-row semantics -- see
        `auth.ControlCredentialStore.has_any`'s identical docstring.

        `work` is a **read-only**, optional parameter (this is not one
        of the state-changing methods ruling (A) requires `work` on):
        when omitted, this runs as a plain standalone read on its own
        pooled connection, exactly as round 1 of this WP had it. When supplied
        (MA-3, round-2 review: closing the TOCTOU gap between a standalone
        existence check and the subsequent `add` -- two concurrent
        bootstraps could both observe "no row" before either committed),
        this executes on `work.connection` instead, so the check
        participates in the caller's own transaction -- and, combined with
        an advisory lock taken on that same connection before this is
        called (`ops.py cmd_bootstrap`/`cmd_reset`), a second concurrent
        ritual invocation blocks until the first commits or rolls back, and
        then sees its row.

        History: CH-0396
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
        """Reset's "revoke every existing control credential" step -- see
        `auth.ControlCredentialStore.revoke_all`'s identical docstring.
        `work` is required (round-2 ruling (A)).

        History: CH-0397
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
        """Row-locking counterpart to `list_all` above, used exclusively
        by `ControlPlaneService.revoke_credential`'s
        last-active-control-credential destructive-confirmation gate
        (design docs/design/DESTRUCTIVE_CONFIRMATION_V1.md R-3, WP-0 MA-2).
        `FOR UPDATE` with no `WHERE` locks every row in this table for
        the remainder of `work`'s transaction -- the gate's own count
        of active rows must not be able to change between this read and
        the state-changing `UPDATE` (`set_state`) that follows in the
        SAME transaction, closing the TOCTOU window a standalone
        count-then-write would leave between two concurrent revokes
        each independently observing "count = 2" and both proceeding
        unconfirmed. A concurrent `rotate`/`set_state` call's own
        single-row `SELECT ... FOR UPDATE` (see those methods above)
        blocks against this same lock too, since it necessarily locks a
        row this statement has already locked.

        `role` is now selected too -- the gate's own "active" count
        (`ControlPlaneService.revoke_credential`) must count only
        `role="control"` rows; an `"audit"` credential existing
        alongside the sole active control credential must not be
        allowed to mask that control credential as "not the last one"
        (an audit credential cannot perform any control-plane
        management operation at all, so it does not relieve the lockout
        the gate exists to prevent).

        History: CH-0399
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
        validate_identifier(schema, field="schema")
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
        """Registration-only `INSERT` -- every provisioning column
        (`database_name`/`runtime_role`/`developer_role`/`provisioned_at`)
        is omitted, so each stays `NULL`, satisfying 0006's two-state
        CHECK as a "registered, not yet provisioned" row.

        History: CH-0400
        """
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

    def count_locked(self, work: _PostgresWork) -> int:
        """Phase 10 WP-6a (design docs/design/PHASE10_DEPLOYMENT_EVIDENCE_
        V1.md D-5(ii) addendum (2)): the row-locking counterpart to `count`
        above, used exclusively by `ControlPlaneService.register_
        application`'s own `applications` limit gate. Takes `_take_bound_
        advisory_lock` (a table-scoped constant-key `pg_advisory_xact_
        lock` -- see that function's own docstring for the full
        rationale, including why `LOCK TABLE ... IN SHARE MODE`, this
        method's pre-review-round-3 form, deadlocks instead of merely
        widening the TOCTOU window) on `work`'s own connection (never a
        separate, already-committed connection the way the pre-WP-6a
        `applications_count()`-then-later-INSERT call sequence used),
        BEFORE the count: a second concurrent `register_application`
        call's own `count_locked` -- which takes the SAME key -- blocks
        until THIS transaction commits or rolls back, at which point its
        count is guaranteed to already reflect this call's INSERT (or its
        absence) -- closing the TOCTOU window a standalone count, read on
        a connection distinct from the one that later performs the
        INSERT, would otherwise leave open (two concurrent calls could
        each observe a count one under the limit and both proceed,
        overshooting it)."""
        try:
            with work.connection.cursor() as cur:
                _take_bound_advisory_lock(cur, schema=self._schema, table="applications")
                _execute(cur, sql.SQL("SELECT count(*) FROM {table}").format(table=self._table), [])
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
        validate_identifier(schema, field="schema")
        maxconn = pool_size if pool_size is not None else _env_int("R2DB_PLATFORM_POOL_SIZE", 4)
        pool_kwargs: dict[str, Any] = {}
        if connect_timeout is not None:
            pool_kwargs["connect_timeout"] = connect_timeout
        if acquire_timeout is not None:
            pool_kwargs["acquire_timeout"] = acquire_timeout
        # Q4 phase WP-1 (design docs/design/Q4_DB_SIDE_SINGLE_TRUTH_V1.md
        # D-1(b)): this class no longer sets `statement_timeout`/
        # `idle_in_transaction_session_timeout` itself -- the connection
        # that writes `control_audit` (`r2dbsvc_controlplane`) now carries
        # both as a PostgreSQL role setting applied by migration `0008`
        # (`ALTER ROLE ... SET`), the single source of truth `visibility_
        # lag_ms` is derived from. `r2db_api.control_main.build_control_app`
        # double-checks this connection's actual effective value against
        # that role setting SYNCHRONOUSLY at startup (`effective_timeouts_
        # ms` below, `r2db_api.platform_declarations.check_writer_role_
        # timeouts`) rather than this class setting anything itself.
        self._pool = _RolePool(dsn, schema=schema, maxconn=maxconn, **pool_kwargs)
        self._schema = schema
        self._table = sql.Identifier(schema, "control_audit")

    def close(self) -> None:
        self._pool.close_all()

    def borrow_connection(self):
        """Q4 phase WP-1 rework (rulings-q4-wp12-rework.md sec.1): exposes
        this sink's OWN pool so
        `platform_declarations.check_writer_role_timeouts` can run its
        dual check on a connection whose login role actually IS the
        `control_audit` writer role (`r2dbsvc_controlplane`) -- a role
        setting only takes effect at login time, so no other connection
        would observe this role's true effective value.

        History: CH-0402
        """
        return self._pool.connection()

    def effective_timeouts_ms(self) -> dict[str, int]:
        """Q4 phase WP-1 (design D-1(b)(ii)): borrows one connection from
        this sink's OWN pool (login role = the actual `control_audit`
        writer role, `r2dbsvc_controlplane`) and reads back `statement_
        timeout`/`idle_in_transaction_session_timeout` from `pg_settings`
        -- the ms-integer effective value PostgreSQL is actually enforcing
        on THIS connection, as opposed to what `pg_db_role_setting` merely
        declares (`r2db_api.platform_declarations.read_declared_role_
        timeouts`). `pg_settings.setting` for these two GUCs is already a
        bare ms integer (never unit-suffixed), so no text parsing is
        needed -- see `r2db_api.platform_declarations.read_effective_
        timeouts_ms`'s own docstring."""
        from .platform_declarations import read_effective_timeouts_ms

        with self._pool.connection() as conn:
            statement_ms, idle_ms = read_effective_timeouts_ms(conn)
        return {"statement_timeout": statement_ms, "idle_in_transaction_session_timeout": idle_ms}

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

        routed through `_execute` (D-4's single execution choke point,
        like every other statement in this file) and the module's own
        `psycopg.Error` -> `AUTH_STATE_UNAVAILABLE` (503) discipline
        (`_fetch_or_503`'s pattern) -- this method previously called
        `cur.execute` directly and let a connection failure propagate
        as a raw `psycopg.Error`, the one read path in this file that
        had not been brought under that discipline yet.

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

        History: CH-0403
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


# Phase 4 (design PHASE4_DURABLE_AUDIT_SINK_V1.md D-1/§6.1): the same 13
# contract `audit.fields` columns `_CONTROL_AUDIT_INSERT` writes, plus the
# 14th column `count` (D-3's coalesced-denial summary row / D-4's
# buffer-overflow alert row -- every other event leaves it `NULL`).
# `audit_seq`/`recorded_at` are never named here -- both are server-side
# defaults (`bigserial`/`DEFAULT clock_timestamp()`, migration `0007_
# application_audit.sql`), exactly like `control_audit.recorded_at` is
# never named in `_CONTROL_AUDIT_INSERT` above.
_APPLICATION_AUDIT_COLUMNS = _CONTROL_AUDIT_COLUMNS + ("count",)
_APPLICATION_AUDIT_INSERT = (
    "INSERT INTO {table} (event_id, event_class, occurred_at, request_id, application_id, "
    "actor_type, actor_id, role, operation, target_kind, outcome, reason_code, target_id, count) "
    "VALUES ({ph0}, {ph1}, {ph2}, {ph3}, {ph4}, {ph5}, {ph6}, {ph7}, {ph8}, {ph9}, {ph10}, {ph11}, {ph12}, {ph13})"
)


class PostgresApplicationAuditSink:
    """Phase 4 (design PHASE4_DURABLE_AUDIT_SINK_V1.md D-1/D-10): the
    durable application-plane audit trail's Postgres half -- writes to
    `r2dbsvc_registry.application_audit` (migration `0007_application_
    audit.sql`), the `application_audit` counterpart to `PostgresControl
    AuditSink` above. Lives here (not in `audit.py`) for the identical
    reason `PostgresControlAuditSink` does -- see that class's own
    docstring; `audit.py`'s `ApplicationAuditSink` is this class's
    in-memory pair (D-10 parity).

    Unlike `PostgresControlAuditSink.append`, this class's `append` never
    accepts a `work` handle -- there is no cross-database unit-of-work to
    join (design §1.3/D-1: application data lives in a *different*
    database entirely, one per application; `application_audit` lives in
    the platform database alongside `control_audit`). Every call -- the
    D-2 pre-commit fail-closed write, the D-3 coalesced-denial first-
    occurrence write, the D-2 commit-failure `error` row, the D-4 buffer
    flush -- opens (and commits, or rolls back on failure) its own single
    connection/transaction from this sink's own pool, which is exactly
    what makes D-4's "buffer flush never shares a transaction with a
    fail-closed write" requirement automatic rather than something a
    caller has to arrange: two calls to this class are, structurally,
    always two different connections (or the same pooled connection reused
    only after the first call's transaction has already ended).
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
        validate_identifier(schema, field="schema")
        maxconn = pool_size if pool_size is not None else _env_int("R2DB_PLATFORM_POOL_SIZE", 4)
        pool_kwargs: dict[str, Any] = {}
        if connect_timeout is not None:
            pool_kwargs["connect_timeout"] = connect_timeout
        if acquire_timeout is not None:
            pool_kwargs["acquire_timeout"] = acquire_timeout
        # Q4 phase WP-1 (design D-1(b)): see `PostgresControlAuditSink.
        # __init__`'s identical comment -- this class no longer sets
        # `statement_timeout`/`idle_in_transaction_session_timeout` itself;
        # `r2dbsvc_api` (the `application_audit` writer role) carries both
        # as a PostgreSQL role setting applied by migration `0008`,
        # double-checked at startup by `r2db_api.main.build_app`
        # (`effective_timeouts_ms` below).
        self._pool = _RolePool(dsn, schema=schema, maxconn=maxconn, **pool_kwargs)
        self._schema = schema
        self._table = sql.Identifier(schema, "application_audit")

    def close(self) -> None:
        self._pool.close_all()

    def borrow_connection(self):
        """Q4 phase WP-1 rework (rulings-q4-wp12-rework.md sec.1): exposes
        this sink's OWN pool so `platform_declarations.check_writer_role_
        timeouts` can run its dual check on a connection whose login role
        actually IS the `application_audit` writer role (`r2dbsvc_api`) --
        see `PostgresControlAuditSink.borrow_connection`'s identical
        docstring."""
        return self._pool.connection()

    def effective_timeouts_ms(self) -> dict[str, int]:
        """Q4 phase WP-1 (design D-1(b)(ii)): see `PostgresControlAuditSink.
        effective_timeouts_ms`'s identical docstring -- this sink's own
        pool connection logs in as `r2dbsvc_api`, the `application_audit`
        writer role."""
        from .platform_declarations import read_effective_timeouts_ms

        with self._pool.connection() as conn:
            statement_ms, idle_ms = read_effective_timeouts_ms(conn)
        return {"statement_timeout": statement_ms, "idle_in_transaction_session_timeout": idle_ms}

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
        count: int | None = None,
    ) -> None:
        """Synchronous durable INSERT + commit, on this sink's own
        connection/transaction (never a caller-supplied `work` -- see this
        class's own docstring). A `psycopg.Error` here propagates to the
        caller unchanged (never mapped to `FoundationError` at this layer,
        matching `PostgresControlAuditSink.append`'s identical denial-path
        behaviour) -- `service.py`'s pre-commit-hook/denial/alert closures
        are the layer that decides how a failure here becomes `SERVICE_
        UNAVAILABLE`.
        """
        event_id = str(uuid.uuid4())
        occurred_at = datetime.now(timezone.utc)
        placeholders = {f"ph{i}": sql.Placeholder() for i in range(14)}
        statement = sql.SQL(_APPLICATION_AUDIT_INSERT).format(table=self._table, **placeholders)
        params = [event_id, event_class, occurred_at, request_id, application_id, actor_type, actor_id, role, operation, target_kind, outcome, reason_code, target_id, count]
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                _execute(cur, statement, params)
            conn.commit()

    def append_many(self, events: "list[Any]") -> None:
        """every buffered `audit.AuditEvent` in `events` is written as one
        multi-row `INSERT` on one connection/transaction -- either the
        whole batch commits or (on failure) none of it does, exactly
        like `audit.ApplicationAuditSink.append_many`'s in-memory
        all-or-nothing behaviour (D-10 parity). A `psycopg.Error` propagates
        to the caller unchanged; `service.py`'s buffer-flush logic
        treats a failed flush as lost events (D-4: buffer content is a
        best-effort channel, the overflow-alert mechanism -- not a
        per-batch retry queue -- is SI-14's "explicit operational
        alert" answer to that loss).

        History: CH-0406
        """
        if not events:
            return
        placeholders = {f"ph{i}": sql.Placeholder() for i in range(14)}
        row_sql = sql.SQL("({})").format(sql.SQL(", ").join(placeholders[f"ph{i}"] for i in range(14)))
        statement = sql.SQL(
            "INSERT INTO {table} (event_id, event_class, occurred_at, request_id, application_id, "
            "actor_type, actor_id, role, operation, target_kind, outcome, reason_code, target_id, count) VALUES {rows}"
        ).format(table=self._table, rows=sql.SQL(", ").join(row_sql for _ in events))
        params: list[Any] = []
        for event in events:
            # `AuditEvent.occurred_at` is an ISO-8601 `str` (`audit.py`'s
            # `.isoformat()` construction, matching every JSON-serializing
            # reader of this dataclass) -- parsed back to a `datetime` here
            # so psycopg adapts it as `timestamptz`, not `text` (a bare
            # `str` parameter has no implicit cast to `timestamptz` in
            # PostgreSQL; `PostgresControlAuditSink.append`/this class's
            # own `append` above never hit this because they construct
            # `occurred_at` as a `datetime` directly, never round-tripping
            # through `AuditEvent`).
            occurred_at = datetime.fromisoformat(event.occurred_at) if isinstance(event.occurred_at, str) else event.occurred_at
            params.extend(
                [
                    event.event_id, event.event_class, occurred_at, event.request_id, event.application_id,
                    event.actor_type, event.actor_id, event.role, event.operation, event.target_kind,
                    event.outcome, event.reason_code, event.target_id, event.count,
                ]
            )
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                _execute(cur, statement, params)
            conn.commit()

    def events(self) -> list[tuple[Any, ...]]:
        """Read surface for tests/tooling connected with sufficient
        privilege (`r2dbsvc_control`, or the dedicated `r2dbsvc_
        auditreader` role -- never the data-plane process' own `r2dbsvc_
        api` role, which has no SELECT on this table at all -- D-1/§6.1).
        Mirrors `PostgresControlAuditSink.events`'s identical ordering
        rationale (`recorded_at, event_id` is not a total order on its own
        -- `audit_query`'s own richer `(recorded_at, plane, event_id)`
        total order, D-6, is WP-2(b)'s concern; this method exists for
        this repository's own tests, not for `audit_query`).
        """
        statement = sql.SQL("SELECT {columns} FROM {table} ORDER BY recorded_at, event_id").format(
            columns=sql.SQL(", ").join(sql.Identifier(name) for name in _APPLICATION_AUDIT_COLUMNS), table=self._table
        )
        try:
            with self._pool.connection() as conn:
                with conn.cursor() as cur:
                    _execute(cur, statement, [])
                    return cur.fetchall()
        except psycopg.Error:
            fail("SERVICE_UNAVAILABLE", "The database could not complete the request.", status=503)
            raise  # unreachable; fail() always raises


# Phase 4 WP-2(b) (design D-5/D-6): the `audit_query` UNION -- shared column
# list (both tables carry the identical 13 contract `audit.fields` columns
# plus `recorded_at`; only `application_audit` has `count`, so the
# `control_audit` half selects a literal `NULL::integer`). `event_id` is
# cast to `text` in both halves (r2db's `event_id` columns are `uuid`,
# D-6's cursor triple is compared/encoded as plain strings, and MitateDB's
# own `event_id` is natively `text` -- casting here keeps this reader's own
# row shape peer-shape-agnostic beyond this one file). `ROW(...) > ROW(...)`
# is PostgreSQL's native lexicographic tuple comparison -- it expresses
# exclusive keyset paging against the full `(recorded_at, plane, event_id)`
# order directly, without hand-splitting the boundary cases a manual
# per-column `OR` chain would need (the `plane` literal differs -- `'control'`
# sorts below `'application'`... no: `'application' < 'control'` -- for each
# half, so a manual split would need to special-case which half is "before"
# vs "at or after" the cursor's own plane; `ROW()` comparison does not need
# that case analysis at all). Each half repeats the SAME named parameters
# (`%(...)s`) rather than one shared filter fragment interpolated twice,
# because `sql.SQL(...).format()`'s own `{...}` templating and psycopg's
# `%(...)s` execute-time binding are two independent substitution passes
# (see `_execute`'s own Phase-4 comment) -- reusing one named parameter at
# several `%(...)s` occurrences is exactly what psycopg's mapping-style
# binding is for.
_AUDIT_QUERY_UNION_SQL = """
WITH filtered AS (
    SELECT event_id::text AS event_id, event_class, occurred_at, request_id, application_id,
           actor_type, actor_id, role, operation, target_kind, outcome, reason_code, target_id,
           NULL::integer AS count, recorded_at, 'control'::text AS plane
    FROM {control_table}
    WHERE recorded_at < %(threshold)s
      AND (%(classes)s::text[] IS NULL OR event_class = ANY(%(classes)s::text[]))
      AND (
        %(after_recorded_at)s::timestamptz IS NULL
        OR ROW(recorded_at, 'control'::text, event_id::text)
           > ROW(%(after_recorded_at)s::timestamptz, %(after_plane)s::text, %(after_event_id)s::text)
      )
    UNION ALL
    SELECT event_id::text AS event_id, event_class, occurred_at, request_id, application_id,
           actor_type, actor_id, role, operation, target_kind, outcome, reason_code, target_id,
           count, recorded_at, 'application'::text AS plane
    FROM {application_table}
    WHERE recorded_at < %(threshold)s
      AND (%(classes)s::text[] IS NULL OR event_class = ANY(%(classes)s::text[]))
      AND (
        %(after_recorded_at)s::timestamptz IS NULL
        OR ROW(recorded_at, 'application'::text, event_id::text)
           > ROW(%(after_recorded_at)s::timestamptz, %(after_plane)s::text, %(after_event_id)s::text)
      )
)
SELECT event_id, event_class, occurred_at, request_id, application_id, actor_type, actor_id, role,
       operation, target_kind, outcome, reason_code, target_id, count, recorded_at, plane
FROM filtered
ORDER BY recorded_at, plane, event_id
LIMIT %(row_limit)s
"""

_AUDIT_QUERY_ROW_COLUMNS = (
    "event_id", "event_class", "occurred_at", "request_id", "application_id", "actor_type", "actor_id",
    "role", "operation", "target_kind", "outcome", "reason_code", "target_id", "count", "recorded_at", "plane",
)


class PostgresAuditQueryStore:
    """`audit_query`'s Postgres reader -- the dedicated, SELECT-only
    `r2dbsvc_auditreader` role (migration `0007_application_audit.sql`
    §1.3), reading BOTH `control_audit` and `application_audit` over one
    connection (D-1(b): a single platform DB is what makes this possible
    without an N-database fan-out). Never shares a pool/DSN with any writer
    role or with `r2dbsvc_controlplane` (D-5's own "別 DSN" requirement --
    `r2dbsvc_controlplane` receives no grant on either audit table at all,
    migration 0007 §1.3 note 5).

    `InMemoryAuditQueryStore` (`audit_query.py`) is this class's in-memory pair -- both
    implement the same `AuditQueryReader` call surface and are exercised by
    the identical parity test
    (`test_in_memory_and_postgres_audit_query_semantics_have_parity`).

    History: CH-0407
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
        validate_identifier(schema, field="schema")
        maxconn = pool_size if pool_size is not None else _env_int("R2DB_PLATFORM_POOL_SIZE", 4)
        pool_kwargs: dict[str, Any] = {}
        if connect_timeout is not None:
            pool_kwargs["connect_timeout"] = connect_timeout
        if acquire_timeout is not None:
            pool_kwargs["acquire_timeout"] = acquire_timeout
        self._pool = _RolePool(dsn, schema=schema, maxconn=maxconn, **pool_kwargs)
        self._control_table = sql.Identifier(schema, "control_audit")
        self._application_table = sql.Identifier(schema, "application_audit")

    def close(self) -> None:
        self._pool.close_all()

    def query(
        self,
        *,
        event_classes: "Sequence[str] | None",
        after: "tuple[datetime, str, str] | None",
        limit: int,
        visibility_lag_ms: int,
    ) -> list[dict[str, Any]]:
        threshold = datetime.now(timezone.utc) - timedelta(milliseconds=visibility_lag_ms)
        params: dict[str, Any] = {
            "threshold": threshold,
            "classes": list(event_classes) if event_classes is not None else None,
            "after_recorded_at": after[0] if after is not None else None,
            "after_plane": after[1] if after is not None else None,
            "after_event_id": after[2] if after is not None else None,
            "row_limit": limit,
        }
        statement = sql.SQL(_AUDIT_QUERY_UNION_SQL).format(control_table=self._control_table, application_table=self._application_table)
        try:
            with self._pool.connection() as conn:
                with conn.cursor() as cur:
                    _execute(cur, statement, params)
                    raw_rows = cur.fetchall()
        except psycopg.Error:
            fail("SERVICE_UNAVAILABLE", "The database could not complete the request.", status=503)
            raise  # unreachable; fail() always raises
        rows: list[dict[str, Any]] = []
        for raw in raw_rows:
            row = dict(zip(_AUDIT_QUERY_ROW_COLUMNS, raw))
            rec = row["recorded_at"]
            row["recorded_at"] = rec if rec.tzinfo is not None else rec.replace(tzinfo=timezone.utc)
            occurred = row["occurred_at"]
            row["occurred_at"] = occurred.isoformat() if hasattr(occurred, "isoformat") else occurred
            rows.append(row)
        return rows


__all__ = [
    "PostgresCredentialStore",
    "PostgresControlCredentialStore",
    "PostgresApplicationRegistry",
    "PostgresControlAuditSink",
    "PostgresApplicationAuditSink",
    "PostgresAuditQueryStore",
    "validate_control_pepper_separation",
    "DEFAULT_SCHEMA",
    "DEFAULT_AUDIT_STATEMENT_TIMEOUT_MS",
    "DEFAULT_AUDIT_IDLE_TIMEOUT_MS",
]
