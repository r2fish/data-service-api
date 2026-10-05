"""`ControlPlaneService`: the control-plane semantics layer (design v1.2
R-6/R-7).

Implements the 11 `/control/v1` operations' logic (contract `control_
endpoints`, `spec/data-service-api.v1.json`) as plain Python methods, tested
directly (WP-4's own scope: this module is never mounted behind an ASGI app
in this WP -- see `control_http.py`'s own module docstring and `main.py`,
neither of which reference this module at all yet; the flip is WP-5).

Independent implementation (R-2's closing paragraph: no code sharing
between peers; r2db-api's own `control_plane.py`/`control_main.py` were
read only as a reference for the SHAPE of problems a control plane in this
position has to solve -- the concrete architecture below is different in
several ways: MitateDB has no `ControlAuthority`/`DataService` equivalent
this layer must delegate to for its own pre-existing audit trail, so this
module's own application/credential registries are self-contained rather
than wrapping another class; the in-memory "same transaction" guarantee is
an explicit shared undo-log token (`control_auth._InMemoryWork`) rather
than a per-domain context manager; and control-plane's own writes to the
`applications`/`credentials` tables go through THIS module's own dedicated
registry classes, never through `auth.CredentialStore`/`credential_store_
postgres.PostgresCredentialStore` (the application-plane's read-only view)
-- a deliberate choice reported in the WP-4 completion notes: it keeps
every existing, already-reviewed application-plane file untouched, at the
cost of a second, control-plane-only writer for the same two tables. This
mirrors R-4's own process-role separation (`mitatedbsvc_api` only ever
reads; `mitatedbsvc_controlplane` is a completely separate role) at the
Python-class level too.

Design principle this module follows throughout (matching R-6's own
architecture note in the design document): every processing-order,
authentication/authorization, must_rotate-gate, bound, and audit decision
lives HERE, in `ControlPlaneService` -- never in a backend (`InMemory
ControlBackend`/`PostgresControlBackend` are dumb storage plumbing; they
never refuse anything ControlPlaneService did not already decide to
refuse) and never (in WP-5) in the HTTP binding layer.

History: CH-0925
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import hmac
import json
import re
import secrets
import threading
import time
from typing import Any, Optional
import uuid

import psycopg
from psycopg import sql

from .capabilities_document import resolve_limit_enforcement
from .audit_query import (DECLARED_AUDIT_EVENT_CLASSES, DECLARED_AUDIT_OPERATIONS,
                          DECLARED_AUDIT_TARGET_KINDS, DEFAULT_COALESCING_WINDOW_MS,
                          AuditQueryReader, shape_audit_query_row, validate_audit_after,
                          validate_audit_event_classes, validate_audit_limit)
from .control_audit import ControlAuditSink, insert_control_audit_row
from .control_auth import ControlCredentialStore, ControlPrincipal, _InMemoryWork
from .credential_wire import compose_bearer_locator, split_bearer_locator
from .errors import (AuthenticationError, AuthenticationRequiredError,
                     AuthorizationError, AuthorizationStateUnavailable,
                     CapabilityError, ConflictError,
                     DestructiveConfirmationRequired, FoundationError,
                     NotFoundError, ResourceLimitError,
                     StorageConfigurationError, ValidationError, violation,
                     observed_type_of)
from .identifiers import validate_identifier
from .pool import _application_name_connect_kwargs

DEFAULT_SCHEMA = "mitatedb_registry"

# Contract `control_plane.identifiers` (spec/data-service-api.v1.json):
# deliberately narrower than `identifiers._IDENTIFIER`'s general 63-byte
# rule -- an application_id becomes platform namespace material.
_APPLICATION_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,32}$")

_ISSUABLE_ROLES = ("runtime", "developer", "control")

# Phase 3.5 WP-5 (design docs/design/PHASE35_CROSS_ENTITY_AND_CONTRACT_130_
# V1.md §1-D/§4, P35-D12): contract `control_plane.authority` -- "An audit
# credential is accepted only on the read-only control_capabilities,
# list_applications, and list_credentials endpoints; every other control
# endpoint fails it closed with FORBIDDEN." An allow-list (not a deny-list)
# -- see `ControlPlaneService._authorize_role`'s own docstring for why.
#
# Phase 4 WP-3(b) (design D-5, work order P4-D4 item 5, contract 1.4.0
# subordinate ruling 9(b)): `audit_query` joins this allow-list -- an
# `audit`-role principal may now read audit evidence too, alongside the
# three pre-existing read-only endpoints. Every other control endpoint
# remains fail-closed FORBIDDEN for this role, unchanged.
_AUDIT_ROLE_ALLOWED_OPERATIONS = frozenset({"control_capabilities", "list_applications", "list_credentials", "audit_query"})

# `audit_query`'s own default/maximum page
# size -- contract `AuditQueryRequest.limit` bounds the wire value to
# `[1, 1000]`; `_DEFAULT_AUDIT_QUERY_LIMIT` is what an omitted `limit`
# defaults to.
# history: CH-0926
_DEFAULT_AUDIT_QUERY_LIMIT = 100
_MAX_AUDIT_QUERY_LIMIT = 1000
_MAX_AUDIT_QUERY_EVENT_CLASSES = 20


def _new_request_id() -> str:
    return uuid.uuid4().hex


def _new_credential_id() -> str:
    return "crd_" + secrets.token_hex(12)


def _new_secret() -> str:
    return secrets.token_urlsafe(32)


# ===========================================================================
# Bounds (R-6: 3 finite resource classes + the request_bytes byte bound the
# control-discovery response also publishes from the very first commit that
# mounts anything, m-10 -- WP-4 never mounts an HTTP app, but the SERVICE
# layer's own `control_capabilities()` result already carries this key so
# WP-5's mount does not have to retrofit it).
# ===========================================================================


@dataclass(frozen=True)
class ControlPlaneLimits:
    """R-6 numeric constraints (upper bound removed Phase 5 D-3, Q3 案A):
    `applications`/`credentials_per_application`/`control_
    requests_per_minute`/`audit_requests_per_minute` must each be a
    positive integer -- **no upper bound is enforced here**, symmetric
    with r2db-api's own `ControlPlaneLimits` (`r2db-api/src/r2db_api/
    limits.py`). The accepted value is an operator responsibility, carried
    through as-declared into `control_capabilities()`; removing the former
    `[1, 200]` ceiling also removes the deployment-misconfiguration
    guardrail it incidentally provided (`docs/design/
    PHASE5_CONTRACT_150_AND_LIMIT_RANGE_V1.md` §3 D-3,
    `MitateDB-api/docs/cloud-run-cloud-sql.md` §3.2c). `control_requests_
    per_minute` must still exceed `applications + 2*credentials_per_
    application + 67` (the headroom+margin inequality a C-14 vector-5-style
    position-arithmetic test needs room to walk up to a limit without the
    rate window itself becoming the first bound hit) -- this relational
    check is independent of the removed ceiling and is unaffected by its
    removal. `request_bytes` is a separate byte bound, checked
    independently below (also positive-integer only, no upper bound),
    declared for parity with R-6's "request_bytes を最初から宣言する"
    instruction.

    History: CH-0927
    """

    applications: int = 100
    credentials_per_application: int = 5
    control_requests_per_minute: int = 200
    request_bytes: int = 65536
    # Phase 4 WP-3(b) (design docs/design/PHASE4_DURABLE_AUDIT_SINK_V1.md
    # D-5, work order WP-3(b) / P4-D4 item 8): `audit_query`'s own pre-auth
    # window -- a SEPARATE counter from `control_requests_per_minute`
    # above, never sharing its bucket (`ControlPlaneService.check_audit_
    # rate`/`_check_audit_rate`). Default matches `control_requests_per_
    # minute`'s own r2db-api sibling default (60).
    audit_requests_per_minute: int = 60

    def __post_init__(self) -> None:
        for name in ("applications", "credentials_per_application", "control_requests_per_minute",
                     "audit_requests_per_minute"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        if self.control_requests_per_minute <= self.applications + 2 * self.credentials_per_application + 67:
            raise ValueError(
                "control_requests_per_minute must exceed applications + 2*credentials_per_application + 67"
            )
        if not isinstance(self.request_bytes, int) or isinstance(self.request_bytes, bool) or self.request_bytes < 1:
            raise ValueError("request_bytes must be a positive integer")

    def as_dict(self) -> dict[str, int]:
        return {
            "applications": self.applications,
            "credentials_per_application": self.credentials_per_application,
            "control_requests_per_minute": self.control_requests_per_minute,
            "request_bytes": self.request_bytes,
            "audit_requests_per_minute": self.audit_requests_per_minute,
        }


# ===========================================================================
# In-memory registries (control-plane's own writer view of `applications`/
# `credentials` -- see this module's own header for why these are NOT
# `auth.CredentialStore`).
# ===========================================================================


class InMemoryApplicationRegistry:
    def __init__(self) -> None:
        self._apps: dict[str, bool] = {}
        # Phase 3.5 WP-5 (design docs/design/PHASE35_CROSS_ENTITY_AND_CONTRACT_130_
        # V1.md §4/§1-E, P35-D6): per-application issuance freeze. A separate
        # dict (not folded into `_apps`'s own bool) so an application absent
        # from it is unambiguously "not frozen" -- `register`'s own entry
        # into `_apps` needs no matching entry here at all, `.get(id, False)`
        # already defaults correctly.
        self._frozen: dict[str, bool] = {}
        self._lock = threading.RLock()

    def exists(self, application_id: str) -> bool:
        with self._lock:
            return application_id in self._apps

    def count(self) -> int:
        with self._lock:
            return len(self._apps)

    def list_all(self) -> list[tuple[str, bool]]:
        with self._lock:
            return list(self._apps.items())

    def register(self, application_id: str, *, work: Optional[_InMemoryWork] = None) -> None:
        with self._lock:
            if application_id in self._apps:
                raise ConflictError("application already exists")
            self._apps[application_id] = True
        if work is not None:
            work.on_rollback(lambda: self._apps.pop(application_id, None))

    def set_enabled(self, application_id: str, enabled: bool, *, work: Optional[_InMemoryWork] = None) -> None:
        with self._lock:
            if application_id not in self._apps:
                raise NotFoundError("application not found")
            previous = self._apps[application_id]
            self._apps[application_id] = enabled
        if work is not None:
            work.on_rollback(lambda: self._apps.__setitem__(application_id, previous))

    def issuance_frozen(self, application_id: str) -> bool:
        with self._lock:
            return self._frozen.get(application_id, False)

    def set_issuance_frozen(self, application_id: str, frozen: bool, *, work: Optional[_InMemoryWork] = None) -> None:
        """Phase 3.5 WP-5 (§4/§1-E, P35-D6): follows the SAME `work.on_
        rollback(...)` undo-log convention `set_enabled` above uses -- this
        is what structurally closes the in-memory-backend freeze-snapshot
        gap r2db-api's own WP-4 review (n-2) found in ITS in-memory backend
        (a snapshot/rollback mechanism that had to be told about every new
        piece of mutable state by hand): here, `_InMemoryWork` is a shared
        undo-log any store participates in simply by registering its own
        undo the same way every other write method in this module already
        does, so there is no separate snapshot list that could forget this
        one -- proactively unaffected by that lesson rather than needing a
        fix for it."""
        with self._lock:
            if application_id not in self._apps:
                raise NotFoundError("application not found")
            previous = self._frozen.get(application_id, False)
            self._frozen[application_id] = frozen
        if work is not None:
            work.on_rollback(lambda: self._frozen.__setitem__(application_id, previous))


@dataclass
class _AppCredential:
    credential_id: str
    application_id: str
    role: str
    digest: bytes
    enabled: bool = True
    revoked: bool = False


class InMemoryCredentialRegistry:
    """Control-plane's own in-memory writer for application credentials.
    Uses the SAME digest algorithm (HMAC-SHA256 with `MITATEDB_CREDENTIAL_
    PEPPER`) as `auth.CredentialStore`, so a credential minted here is, in
    principle, verifiable by that class too -- reconciling the two
    representations into one shared registry is a WP-5 wiring concern
    (flagged in the WP-4 completion report), out of scope here (WP-4 tests
    this store directly, with no adapter wiring)."""

    def __init__(self, pepper: str) -> None:
        if not isinstance(pepper, str) or len(pepper) < 16:
            raise ValueError("credential pepper must be supplied externally (>=16 characters)")
        self._pepper = pepper.encode("utf-8")
        self._credentials: dict[str, _AppCredential] = {}
        self._lock = threading.RLock()

    def _digest(self, secret) -> bytes:
        if not isinstance(secret, str):
            secret = ""
        return hmac.new(self._pepper, secret.encode("utf-8"), hashlib.sha256).digest()

    def get_state(self, credential_id: str) -> Optional[tuple[bool, bool]]:
        with self._lock:
            item = self._credentials.get(credential_id)
            return (item.enabled, item.revoked) if item is not None else None

    def count_active_for_application(self, application_id: str) -> int:
        with self._lock:
            return sum(1 for item in self._credentials.values()
                       if item.application_id == application_id and not item.revoked)

    def list_all(self) -> list[tuple[str, str, str, bool, bool]]:
        with self._lock:
            return [(item.credential_id, item.application_id, item.role, item.enabled, item.revoked)
                   for item in self._credentials.values()]

    def issue(self, application_id: str, role: str, *, credential_id: Optional[str] = None,
              secret: Optional[str] = None, work: Optional[_InMemoryWork] = None) -> tuple[str, str]:
        credential_id = credential_id or _new_credential_id()
        secret = secret or _new_secret()
        with self._lock:
            self._credentials[credential_id] = _AppCredential(
                credential_id=credential_id, application_id=application_id, role=role, digest=self._digest(secret))
        if work is not None:
            work.on_rollback(lambda: self._credentials.pop(credential_id, None))
        return credential_id, secret

    def rotate(self, credential_id: str, *, secret: Optional[str] = None,
               work: Optional[_InMemoryWork] = None) -> str:
        secret = secret or _new_secret()
        with self._lock:
            item = self._credentials.get(credential_id)
            if item is None:
                raise NotFoundError("credential not found")
            previous = item.digest
            item.digest = self._digest(secret)
        if work is not None:
            work.on_rollback(lambda: setattr(item, "digest", previous))
        return secret

    def set_state(self, credential_id: str, *, enabled: Optional[bool] = None, revoked: Optional[bool] = None,
                  work: Optional[_InMemoryWork] = None) -> None:
        with self._lock:
            item = self._credentials.get(credential_id)
            if item is None:
                raise NotFoundError("credential not found")
            previous_enabled, previous_revoked = item.enabled, item.revoked
            if enabled is not None:
                item.enabled = enabled
            if revoked is not None:
                item.revoked = revoked
        if work is not None:
            def _undo() -> None:
                item.enabled = previous_enabled
                item.revoked = previous_revoked
            work.on_rollback(_undo)

    def authenticate(self, secret: str) -> Optional[tuple[str, str, str]]:
        """Phase 4 WP-3(b) (design D-5): a READ-ONLY probe against THIS
        registry's own application-credential rows -- reuses the SAME
        digest `issue`/`rotate` above already compute (never a separate
        auth.CredentialStore lookup, per this module's own header: control-
        plane writes/reads its own dedicated registries). Returns
        `(application_id, role)` when the presented bearer genuinely
        authenticates a currently active (enabled, not revoked) application
        credential; `None` for an unknown id, wrong secret, disabled, or
        revoked credential -- never raises. Timing-safe: a digest
        comparison always runs, against a real or dummy 32-byte value,
        regardless of whether `credential_id` is known (mirrors `control_
        auth.ControlCredentialStore.authenticate`'s identical convention).
        Used only by `ControlPlaneService.audit_query`'s own "application
        credentials are FORBIDDEN" probe (D-5) -- never by any other
        operation, which authenticates via `_authenticate`/`control_
        credential_state` instead.

        Phase 6 WP-3 差し戻し 最終ラウンド (裁定 1): `secret` is the FULL
        presented bearer -- this method is
        this registry's own single receiving boundary, splitting via
        `split_bearer_locator` exactly ONCE, HERE, same one-bearer-in
        contract every other store on this peer now uses. A malformed
        bearer returns `None` directly, with no digest comparison at all
        (mirrors `auth.CredentialStore.peek`'s identical treatment).

        History: CH-0928
        """
        locator = split_bearer_locator(secret)
        if locator is None:
            return None
        credential_id, secret_part = locator
        with self._lock:
            item = self._credentials.get(credential_id)
            stored_digest = item.digest if item is not None else _APP_CREDENTIAL_DUMMY_DIGEST
            digest_matches = hmac.compare_digest(stored_digest, self._digest(secret_part))
            if item is None or not digest_matches or not item.enabled or item.revoked:
                return None
            return item.credential_id, item.application_id, item.role


# WP-3(b) (mirrors `control_auth._DUMMY_DIGEST`'s own rationale, applied to
# this registry's own credential kind): a fixed-length, never-matching
# stand-in digest so `InMemoryCredentialRegistry.authenticate` above always
# performs a real `hmac.compare_digest` call, whether or not `credential_id`
# is present.
_APP_CREDENTIAL_DUMMY_DIGEST = hashlib.sha256(b"mitatedb-control-plane-app-credential-probe-timing-parity-dummy").digest()


# ===========================================================================
# PostgreSQL registries -- direct SQL against `applications`/`credentials`
# (migration 0002), using the `mitatedbsvc_controlplane` role. NEVER shares
# code with `credential_store_postgres.py` (see this module's own header).
# ===========================================================================


def _execute(cursor, statement, params=()):
    """R-2 choke point. The ONLY call to `cursor.execute` in this module."""
    if not isinstance(statement, (sql.SQL, sql.Composed)):
        raise TypeError("control_plane.py only executes psycopg.sql.Composed/SQL objects, never str")
    cursor.execute(statement, params)
    return cursor


_BOUND_ADVISORY_LOCK_STATEMENT = sql.SQL("SELECT pg_advisory_xact_lock(hashtext(%s))")


def _take_bound_advisory_lock(cursor: "psycopg.Cursor[Any]", *, schema: str, table: str) -> None:
    """Phase 10 WP-6b (design docs/design/PHASE10_DEPLOYMENT_EVIDENCE_V1.md
    D-5(ii) addendum (2); supervisor ruling `scratchpad/phase10/wp6-
    rulings.md` #1, closing review finding F1): the lock every region-(iii)
    process-ceiling bound (`applications`, `credentials_per_application`)
    takes immediately before its own count, in the SAME transaction that
    then performs the INSERT -- `PostgresApplicationRegistry.count_locked`
    and `PostgresCredentialRegistry.count_active_for_application_locked`
    below are this function's only two callers.

    This is `pg_advisory_xact_lock(hashtext(<key>))`, NOT `LOCK TABLE ...
    IN SHARE MODE` (the form the design addendum names and forbids
    explicitly; this peer's own pre-review-round-3 form was `SHARE ROW
    EXCLUSIVE MODE`, which serializes correctly but is not the prescribed
    idiom and was asymmetric with r2db): SHARE conflicts with
    the ROW EXCLUSIVE the following INSERT needs, but SHARE never
    conflicts with a concurrent SHARE, so two concurrent callers could
    both acquire SHARE, both read a count one under the limit, and only
    THEN each block on the other's INSERT -- a genuine deadlock, not
    merely the widened TOCTOU window the pre-WP-6b code had.
    `pg_advisory_xact_lock` is exclusive against itself instead: a second
    caller taking the SAME key blocks until the first caller's
    transaction commits or rolls back, so by the time it proceeds, its
    own count is guaranteed to already reflect the first caller's INSERT
    (or its absence, if the first rolled back) -- closing the TOCTOU
    window without ever letting two holders past the count at once.

    The key is a per-table *constant* -- `hashtext('<schema>.<table>')`,
    one fixed 32-bit int per table -- never a per-row/per-key value.
    Scoped per table, not one shared key for every bound, so concurrent
    `applications` and `credentials_per_application` traffic never
    contend with each other, only with itself."""
    _execute(cursor, _BOUND_ADVISORY_LOCK_STATEMENT, [f"{schema}.{table}"])


class _PostgresRegistryBase:
    def __init__(self, dsn: str, *, schema: str = DEFAULT_SCHEMA, connect_timeout: int = 5) -> None:
        validate_identifier(schema, "schema")
        self._dsn = dsn
        self._schema = schema
        self._connect_timeout = connect_timeout

    def _connect(self) -> "psycopg.Connection":
        try:
            return psycopg.connect(self._dsn, connect_timeout=self._connect_timeout, autocommit=False, **_application_name_connect_kwargs())
        except psycopg.Error as exc:
            raise AuthorizationStateUnavailable("authorization state unavailable") from exc

    def _own_connection(self, work):
        if work is not None:
            return work, False
        return self._connect(), True


class PostgresApplicationRegistry(_PostgresRegistryBase):
    def __init__(self, dsn: str, *, schema: str = DEFAULT_SCHEMA, connect_timeout: int = 5) -> None:
        super().__init__(dsn, schema=schema, connect_timeout=connect_timeout)
        self._table = sql.Identifier(schema, "applications")

    def exists(self, application_id: str) -> bool:
        conn = self._connect()
        try:
            statement = sql.SQL("SELECT 1 FROM {table} WHERE application_id = {ph}").format(
                table=self._table, ph=sql.Placeholder())
            try:
                with conn.cursor() as cur:
                    _execute(cur, statement, [application_id])
                    row = cur.fetchone()
            except psycopg.errors.InsufficientPrivilege as exc:
                raise StorageConfigurationError("privilege/configuration defect") from exc
            except psycopg.Error as exc:
                raise AuthorizationStateUnavailable("authorization state unavailable") from exc
        finally:
            conn.close()
        return row is not None

    def count(self) -> int:
        conn = self._connect()
        try:
            statement = sql.SQL("SELECT count(*) FROM {table}").format(table=self._table)
            try:
                with conn.cursor() as cur:
                    _execute(cur, statement)
                    row = cur.fetchone()
            except psycopg.errors.InsufficientPrivilege as exc:
                raise StorageConfigurationError("privilege/configuration defect") from exc
            except psycopg.Error as exc:
                raise AuthorizationStateUnavailable("authorization state unavailable") from exc
        finally:
            conn.close()
        return int(row[0])

    def count_locked(self, work: Any) -> int:
        """Phase 10 WP-6b (design docs/design/PHASE10_DEPLOYMENT_EVIDENCE_
        V1.md D-5(ii) addendum (2)): the row-locking counterpart to
        `count` above, used exclusively by `ControlPlaneService.register_
        application`'s own `applications` limit gate. Takes `_take_bound_
        advisory_lock` (a table-scoped constant-key `pg_advisory_xact_
        lock` -- see that function's own docstring for the full
        rationale; `LOCK TABLE ... IN SHARE ROW EXCLUSIVE MODE`, this
        method's pre-review-round-3 form, self-conflicts and therefore
        serializes writers correctly -- it was replaced for symmetry with
        r2db and with the design's prescribed idiom, not because it
        deadlocked) on `work`'s own connection (never a separate,
        already-committed connection the way the pre-WP-6b `applications_
        count()`-then-later-INSERT call sequence used), BEFORE the count:
        a second concurrent `register_application` call's own `count_
        locked` -- which takes the SAME key -- blocks until THIS
        transaction commits or rolls back, at which point its count is
        guaranteed to already reflect this call's INSERT (or its
        absence) -- closing the TOCTOU window a standalone count, read on
        a connection distinct from the one that later performs the
        INSERT, would otherwise leave open (two concurrent calls could
        each observe a count one under the limit and both proceed,
        overshooting it)."""
        try:
            with work.cursor() as cur:
                _take_bound_advisory_lock(cur, schema=self._schema, table="applications")
                _execute(cur, sql.SQL("SELECT count(*) FROM {table}").format(table=self._table))
                row = cur.fetchone()
        except psycopg.errors.InsufficientPrivilege as exc:
            raise StorageConfigurationError("privilege/configuration defect") from exc
        except psycopg.Error as exc:
            raise AuthorizationStateUnavailable("authorization state unavailable") from exc
        return int(row[0]) if row else 0

    def list_all(self) -> list[tuple[str, bool]]:
        conn = self._connect()
        try:
            statement = sql.SQL("SELECT application_id, enabled FROM {table} ORDER BY registered_at").format(table=self._table)
            try:
                with conn.cursor() as cur:
                    _execute(cur, statement)
                    rows = cur.fetchall()
            except psycopg.errors.InsufficientPrivilege as exc:
                raise StorageConfigurationError("privilege/configuration defect") from exc
            except psycopg.Error as exc:
                raise AuthorizationStateUnavailable("authorization state unavailable") from exc
        finally:
            conn.close()
        return [(row[0], row[1]) for row in rows]

    def register(self, application_id: str, *, work=None) -> None:
        conn, owns = self._own_connection(work)
        statement = sql.SQL("INSERT INTO {table} (application_id) VALUES ({ph})").format(
            table=self._table, ph=sql.Placeholder())
        try:
            with conn.cursor() as cur:
                _execute(cur, statement, [application_id])
            if owns:
                conn.commit()
        except psycopg.errors.UniqueViolation as exc:
            if owns:
                conn.rollback()
            raise ConflictError("application already exists") from exc
        except psycopg.errors.InsufficientPrivilege as exc:
            if owns:
                conn.rollback()
            raise StorageConfigurationError("privilege/configuration defect") from exc
        except psycopg.Error as exc:
            if owns:
                conn.rollback()
            raise AuthorizationStateUnavailable("authorization state unavailable") from exc
        finally:
            if owns:
                conn.close()

    def set_enabled(self, application_id: str, enabled: bool, *, work=None) -> None:
        conn, owns = self._own_connection(work)
        statement = sql.SQL(
            "UPDATE {table} SET enabled = {ph} WHERE application_id = {id_ph} RETURNING application_id"
        ).format(table=self._table, ph=sql.Placeholder(), id_ph=sql.Placeholder())
        try:
            with conn.cursor() as cur:
                _execute(cur, statement, [enabled, application_id])
                row = cur.fetchone()
                if row is None:
                    raise NotFoundError("application not found")
            if owns:
                conn.commit()
        except NotFoundError:
            if owns:
                conn.rollback()
            raise
        except psycopg.errors.InsufficientPrivilege as exc:
            if owns:
                conn.rollback()
            raise StorageConfigurationError("privilege/configuration defect") from exc
        except psycopg.Error as exc:
            if owns:
                conn.rollback()
            raise AuthorizationStateUnavailable("authorization state unavailable") from exc
        finally:
            if owns:
                conn.close()

    def issuance_frozen(self, application_id: str) -> bool:
        """Phase 3.5 WP-5 (design §4/§1-E, P35-D6): `ControlPlaneService.
        issue_credential`'s own read of this flag, evaluated only after the
        `role=control` capability refusal and the target-existence check
        (contract `issue_credential.semantics`'s own precedence sentence).
        Returns `False` for an unknown `application_id` -- callers reach
        this only after already confirming the application exists."""
        conn = self._connect()
        try:
            statement = sql.SQL("SELECT issuance_frozen FROM {table} WHERE application_id = {ph}").format(
                table=self._table, ph=sql.Placeholder())
            try:
                with conn.cursor() as cur:
                    _execute(cur, statement, [application_id])
                    row = cur.fetchone()
            except psycopg.errors.InsufficientPrivilege as exc:
                raise StorageConfigurationError("privilege/configuration defect") from exc
            except psycopg.Error as exc:
                raise AuthorizationStateUnavailable("authorization state unavailable") from exc
        finally:
            conn.close()
        return bool(row[0]) if row is not None else False

    def set_issuance_frozen(self, application_id: str, frozen: bool, *, work=None) -> None:
        """Phase 3.5 WP-5 (§4/§1-E, P35-D6): CLI-only, non-destructive
        (mirrors `set_enabled` above -- no declare-and-echo confirmation
        gate, same class as disable-application). No in-band endpoint
        calls this -- only `ops.py freeze-issuance`/`unfreeze-issuance`."""
        conn, owns = self._own_connection(work)
        statement = sql.SQL(
            "UPDATE {table} SET issuance_frozen = {ph} WHERE application_id = {id_ph} RETURNING application_id"
        ).format(table=self._table, ph=sql.Placeholder(), id_ph=sql.Placeholder())
        try:
            with conn.cursor() as cur:
                _execute(cur, statement, [frozen, application_id])
                row = cur.fetchone()
                if row is None:
                    raise NotFoundError("application not found")
            if owns:
                conn.commit()
        except NotFoundError:
            if owns:
                conn.rollback()
            raise
        except psycopg.errors.InsufficientPrivilege as exc:
            if owns:
                conn.rollback()
            raise StorageConfigurationError("privilege/configuration defect") from exc
        except psycopg.Error as exc:
            if owns:
                conn.rollback()
            raise AuthorizationStateUnavailable("authorization state unavailable") from exc
        finally:
            if owns:
                conn.close()


class PostgresCredentialRegistry(_PostgresRegistryBase):
    def __init__(self, dsn: str, *, pepper: str, schema: str = DEFAULT_SCHEMA, connect_timeout: int = 5) -> None:
        super().__init__(dsn, schema=schema, connect_timeout=connect_timeout)
        if not isinstance(pepper, str) or len(pepper) < 16:
            raise ValueError("credential pepper must be supplied externally (>=16 characters)")
        self._pepper = pepper.encode("utf-8")
        self._table = sql.Identifier(schema, "credentials")

    def _digest(self, secret) -> bytes:
        if not isinstance(secret, str):
            secret = ""
        return hmac.new(self._pepper, secret.encode("utf-8"), hashlib.sha256).digest()

    def get_state(self, credential_id: str) -> Optional[tuple[bool, bool]]:
        conn = self._connect()
        try:
            statement = sql.SQL("SELECT enabled, revoked FROM {table} WHERE credential_id = {ph}").format(
                table=self._table, ph=sql.Placeholder())
            try:
                with conn.cursor() as cur:
                    _execute(cur, statement, [credential_id])
                    row = cur.fetchone()
            except psycopg.errors.InsufficientPrivilege as exc:
                raise StorageConfigurationError("privilege/configuration defect") from exc
            except psycopg.Error as exc:
                raise AuthorizationStateUnavailable("authorization state unavailable") from exc
        finally:
            conn.close()
        return (row[0], row[1]) if row is not None else None

    def count_active_for_application(self, application_id: str) -> int:
        conn = self._connect()
        try:
            statement = sql.SQL(
                "SELECT count(*) FROM {table} WHERE application_id = {ph} AND NOT revoked"
            ).format(table=self._table, ph=sql.Placeholder())
            try:
                with conn.cursor() as cur:
                    _execute(cur, statement, [application_id])
                    row = cur.fetchone()
            except psycopg.errors.InsufficientPrivilege as exc:
                raise StorageConfigurationError("privilege/configuration defect") from exc
            except psycopg.Error as exc:
                raise AuthorizationStateUnavailable("authorization state unavailable") from exc
        finally:
            conn.close()
        return int(row[0])

    def count_active_for_application_locked(self, application_id: str, work: Any) -> int:
        """Phase 10 WP-6b (design docs/design/PHASE10_DEPLOYMENT_EVIDENCE_
        V1.md D-5(ii) addendum (2)): the row-locking counterpart to
        `count_active_for_application` above, used exclusively by
        `ControlPlaneService.issue_credential`'s own `credentials_per_
        application` limit gate. Takes `_take_bound_advisory_lock` (a
        table-scoped constant-key `pg_advisory_xact_lock` -- see that
        function's own docstring for the full rationale, including why
        `LOCK TABLE ... IN SHARE ROW EXCLUSIVE MODE`, this method's
        pre-review-round-3 form, self-conflicts and serializes writers
        correctly; it was replaced for symmetry with r2db and the design's
        prescribed idiom) on
        `work`'s own connection, BEFORE the count: a second concurrent
        `issue_credential` call's own `count_active_for_application_
        locked` -- which takes the SAME key -- blocks until THIS
        transaction commits or rolls back, at which point its count is
        guaranteed to already reflect this call's INSERT (or its
        absence)."""
        try:
            with work.cursor() as cur:
                _take_bound_advisory_lock(cur, schema=self._schema, table="credentials")
                _execute(
                    cur,
                    sql.SQL("SELECT count(*) FROM {table} WHERE application_id = {ph} AND NOT revoked").format(
                        table=self._table, ph=sql.Placeholder()),
                    [application_id],
                )
                row = cur.fetchone()
        except psycopg.errors.InsufficientPrivilege as exc:
            raise StorageConfigurationError("privilege/configuration defect") from exc
        except psycopg.Error as exc:
            raise AuthorizationStateUnavailable("authorization state unavailable") from exc
        return int(row[0]) if row else 0

    def list_all(self) -> list[tuple[str, str, str, bool, bool]]:
        conn = self._connect()
        try:
            statement = sql.SQL(
                "SELECT credential_id, application_id, role, enabled, revoked FROM {table} ORDER BY issued_at"
            ).format(table=self._table)
            try:
                with conn.cursor() as cur:
                    _execute(cur, statement)
                    rows = cur.fetchall()
            except psycopg.errors.InsufficientPrivilege as exc:
                raise StorageConfigurationError("privilege/configuration defect") from exc
            except psycopg.Error as exc:
                raise AuthorizationStateUnavailable("authorization state unavailable") from exc
        finally:
            conn.close()
        return [tuple(row) for row in rows]

    def issue(self, application_id: str, role: str, *, credential_id: Optional[str] = None,
              secret: Optional[str] = None, work=None) -> tuple[str, str]:
        credential_id = credential_id or _new_credential_id()
        secret = secret or _new_secret()
        digest = self._digest(secret)
        conn, owns = self._own_connection(work)
        statement = sql.SQL(
            "INSERT INTO {table} (credential_id, application_id, role, digest) "
            "VALUES ({id_ph}, {app_ph}, {role_ph}, {digest_ph})"
        ).format(table=self._table, id_ph=sql.Placeholder(), app_ph=sql.Placeholder(),
                  role_ph=sql.Placeholder(), digest_ph=sql.Placeholder())
        try:
            with conn.cursor() as cur:
                _execute(cur, statement, [credential_id, application_id, role, digest])
            if owns:
                conn.commit()
        except psycopg.errors.ForeignKeyViolation as exc:
            if owns:
                conn.rollback()
            raise NotFoundError("unknown application") from exc
        except psycopg.errors.InsufficientPrivilege as exc:
            if owns:
                conn.rollback()
            raise StorageConfigurationError("privilege/configuration defect") from exc
        except psycopg.Error as exc:
            if owns:
                conn.rollback()
            raise AuthorizationStateUnavailable("authorization state unavailable") from exc
        finally:
            if owns:
                conn.close()
        return credential_id, secret

    def rotate(self, credential_id: str, *, secret: Optional[str] = None, work=None) -> str:
        secret = secret or _new_secret()
        digest = self._digest(secret)
        conn, owns = self._own_connection(work)
        statement = sql.SQL(
            "UPDATE {table} SET digest = {digest_ph} WHERE credential_id = {id_ph} RETURNING credential_id"
        ).format(table=self._table, digest_ph=sql.Placeholder(), id_ph=sql.Placeholder())
        try:
            with conn.cursor() as cur:
                _execute(cur, statement, [digest, credential_id])
                row = cur.fetchone()
                if row is None:
                    raise NotFoundError("credential not found")
            if owns:
                conn.commit()
        except NotFoundError:
            if owns:
                conn.rollback()
            raise
        except psycopg.errors.InsufficientPrivilege as exc:
            if owns:
                conn.rollback()
            raise StorageConfigurationError("privilege/configuration defect") from exc
        except psycopg.Error as exc:
            if owns:
                conn.rollback()
            raise AuthorizationStateUnavailable("authorization state unavailable") from exc
        finally:
            if owns:
                conn.close()
        return secret

    def set_state(self, credential_id: str, *, enabled: Optional[bool] = None, revoked: Optional[bool] = None,
                  work=None) -> None:
        assignments = []
        params: list[Any] = []
        if enabled is not None:
            assignments.append(sql.SQL("enabled = {}").format(sql.Placeholder()))
            params.append(enabled)
        if revoked is not None:
            assignments.append(sql.SQL("revoked = {}").format(sql.Placeholder()))
            params.append(revoked)
        if not assignments:
            return
        params.append(credential_id)
        conn, owns = self._own_connection(work)
        statement = sql.SQL("UPDATE {table} SET {assignments} WHERE credential_id = {id_ph} RETURNING credential_id").format(
            table=self._table, assignments=sql.SQL(", ").join(assignments), id_ph=sql.Placeholder())
        try:
            with conn.cursor() as cur:
                _execute(cur, statement, params)
                row = cur.fetchone()
                if row is None:
                    raise NotFoundError("credential not found")
            if owns:
                conn.commit()
        except NotFoundError:
            if owns:
                conn.rollback()
            raise
        except psycopg.errors.InsufficientPrivilege as exc:
            if owns:
                conn.rollback()
            raise StorageConfigurationError("privilege/configuration defect") from exc
        except psycopg.Error as exc:
            if owns:
                conn.rollback()
            raise AuthorizationStateUnavailable("authorization state unavailable") from exc
        finally:
            if owns:
                conn.close()

    def authenticate(self, secret: str) -> Optional[tuple[str, str, str]]:
        """Phase 4 WP-3(b) (design D-5): the PostgreSQL twin of `InMemory
        CredentialRegistry.authenticate` above -- identical contract
        (`(application_id, role)` or `None`, never raises for an ordinary
        auth failure, timing-safe digest comparison). A genuine store
        failure (privilege/configuration defect, unreachable database)
        DOES still raise -- `ControlPlaneService.audit_query` lets that
        propagate exactly like every other backend call it makes (the
        design exemption for store-unreachable audit-write is unrelated to
        this READ probe).

        Phase 6 WP-3 差し戻し 最終ラウンド (裁定 1): `secret` is the FULL
        presented bearer -- splits via
        `split_bearer_locator` exactly ONCE, HERE, same one-bearer-in
        contract every other store on this peer now uses. A malformed
        bearer returns `None` directly, no lookup attempted.

        History: CH-0929
        """
        locator = split_bearer_locator(secret)
        if locator is None:
            return None
        credential_id, secret_part = locator
        conn = self._connect()
        try:
            statement = sql.SQL(
                "SELECT digest, application_id, role, enabled, revoked FROM {table} WHERE credential_id = {ph}"
            ).format(table=self._table, ph=sql.Placeholder())
            try:
                with conn.cursor() as cur:
                    _execute(cur, statement, [credential_id])
                    row = cur.fetchone()
            except psycopg.errors.InsufficientPrivilege as exc:
                raise StorageConfigurationError("privilege/configuration defect") from exc
            except psycopg.Error as exc:
                raise AuthorizationStateUnavailable("authorization state unavailable") from exc
        finally:
            conn.close()
        stored_digest = bytes(row[0]) if row is not None else _APP_CREDENTIAL_DUMMY_DIGEST
        digest_matches = hmac.compare_digest(stored_digest, self._digest(secret_part))
        if row is None or not digest_matches or not row[3] or row[4]:
            return None
        return credential_id, row[1], row[2]


# ===========================================================================
# Backends: dumb storage plumbing `ControlPlaneService` drives. Each bundles
# an application registry + credential registry + control-credential store
# + audit sink/inserter, plus one `unit_of_work()` spanning all four (the
# R-6 same-transaction guarantee).
# ===========================================================================


class InMemoryControlBackend:
    def __init__(self, *, app_pepper: str, control_pepper: str) -> None:
        self._applications = InMemoryApplicationRegistry()
        self._credentials = InMemoryCredentialRegistry(app_pepper)
        self._control_credentials = ControlCredentialStore(control_pepper)
        self._audit = ControlAuditSink()
        self._lock = threading.RLock()

    @property
    def control_credential_store(self) -> ControlCredentialStore:
        return self._control_credentials

    @property
    def audit_sink(self) -> ControlAuditSink:
        return self._audit

    @contextmanager
    def unit_of_work(self):
        with self._lock:
            work = _InMemoryWork()
            try:
                yield work
            except BaseException:
                work.rollback()
                raise

    def application_exists(self, application_id: str) -> bool:
        return self._applications.exists(application_id)

    def applications_count(self) -> int:
        return self._applications.count()

    def applications_count_locked(self, work: Any) -> int:
        # Phase 10 WP-6b (design D-5 (ii) region (iii)): this backend has
        # no real store/lock to take -- `unit_of_work()` above already
        # holds `self._lock` (a process-wide `threading.RLock`) for the
        # WHOLE `with` block a caller opens it in, so the TOCTOU window a
        # real, multi-process PostgreSQL deployment needs a table-scoped
        # advisory lock to close (`PostgresControlBackend.applications_
        # count_locked` below) does not exist here at all; `work` is
        # accepted only to satisfy the shared call surface `Control
        # PlaneService.register_application` uses against both backends.
        del work
        return self.applications_count()

    def list_applications(self):
        return self._applications.list_all()

    def register_application(self, application_id: str, *, work) -> None:
        self._applications.register(application_id, work=work)

    def set_application_enabled(self, application_id: str, enabled: bool, *, work) -> None:
        self._applications.set_enabled(application_id, enabled, work=work)

    def application_issuance_frozen(self, application_id: str) -> bool:
        return self._applications.issuance_frozen(application_id)

    def set_application_issuance_frozen(self, application_id: str, frozen: bool, *, work) -> None:
        self._applications.set_issuance_frozen(application_id, frozen, work=work)

    def credential_state(self, credential_id: str):
        return self._credentials.get_state(credential_id)

    def credentials_active_count(self, application_id: str) -> int:
        return self._credentials.count_active_for_application(application_id)

    def credentials_active_count_locked(self, application_id: str, work: Any) -> int:
        # same reasoning as `applications_count_locked`
        # above -- no real lock to take for a single-process, in-memory
        # backend.
        # history: CH-0931
        del work
        return self.credentials_active_count(application_id)

    def list_credentials(self):
        return self._credentials.list_all()

    def issue_credential(self, application_id: str, role: str, *, credential_id: str, secret: str, work) -> None:
        self._credentials.issue(application_id, role, credential_id=credential_id, secret=secret, work=work)

    def rotate_credential(self, credential_id: str, secret: str, *, work) -> None:
        self._credentials.rotate(credential_id, secret=secret, work=work)

    def set_credential_state(self, credential_id: str, *, enabled=None, revoked=None, work) -> None:
        self._credentials.set_state(credential_id, enabled=enabled, revoked=revoked, work=work)

    def control_credential_state(self, credential_id: str):
        return self._control_credentials.get_state(credential_id)

    def list_control_credentials(self):
        return self._control_credentials.list_all()

    def control_credentials_locked(self, work):
        return self._control_credentials.locked_for_update(work)

    def rotate_control_credential(self, credential_id: str, secret: str, *, work) -> None:
        self._control_credentials.rotate(credential_id, secret=secret, work=work)

    def set_control_credential_state(self, credential_id: str, *, enabled=None, revoked=None, work) -> None:
        if enabled is not None:
            (self._control_credentials.enable if enabled else self._control_credentials.disable)(credential_id, work=work)
        if revoked:
            self._control_credentials.revoke(credential_id, work=work)

    def authenticate_control(self, secret) -> ControlPrincipal:
        return self._control_credentials.authenticate(secret)

    def authenticate_application(self, secret) -> Optional[tuple[str, str, str]]:
        """a SEPARATE probe against the
        APPLICATION-credential universe (`self._credentials`, never
        `self._control_credentials`) -- `audit_query`'s own authority check
        needs to recognize "this credential_id/secret genuinely belongs to
        a real, active application credential" BEFORE ever presenting it to
        `authenticate_control`, so it can answer an identified, attributed
        `FORBIDDEN` rather than let it fall through as an ordinary,
        unattributed `AUTH_INVALID` against the control-credential store it
        was never issued against (contract `control_endpoints.audit_query.
        semantics`: "Application credentials are denied"). Returns `None`
        for every failure mode -- never raises for an ordinary auth
        mismatch.

        History: CH-0932
        """
        return self._credentials.authenticate(secret)

    def append_audit(self, *, work=None, **fields):
        return self._audit.append(work=work, **fields)


class PostgresControlBackend:
    def __init__(self, *, applications: PostgresApplicationRegistry, credentials: PostgresCredentialRegistry,
                 control_credentials, audit_schema: str, dsn: str, connect_timeout: int = 5) -> None:
        self._applications = applications
        self._credentials = credentials
        self._control_credentials = control_credentials
        self._audit_schema = audit_schema
        self._dsn = dsn
        self._connect_timeout = connect_timeout
        # Q4 phase (design D-1(b), work order §4 WP-2 変更対象 B): the two
        # writer timeouts this connection (the ONE that writes `control_
        # audit`, inside `unit_of_work` below, in the SAME transaction as
        # every control-plane state change) used to carry via `SET
        # SESSION` are now `mitatedbsvc_controlplane`'s
        # own PostgreSQL role setting (`ALTER ROLE ... SET`, migration
        # `0007_platform_declarations.sql`) -- applied automatically at
        # login, no client-side action needed. The control-plane
        # composition root checks the declared-vs-effective value once at
        # startup (`platform_declarations.check_writer_role_timeouts`)
        # and derives `visibility_lag_ms` from the SAME catalog
        # (`platform_declarations.derive_visibility_lag_ms`) instead of
        # this constructor carrying two explicit ms parameters.
        # history: CH-0933

    @property
    def control_credential_store(self):
        return self._control_credentials

    @contextmanager
    def unit_of_work(self):
        try:
            conn = psycopg.connect(self._dsn, connect_timeout=self._connect_timeout, autocommit=False, **_application_name_connect_kwargs())
        except psycopg.Error as exc:
            raise AuthorizationStateUnavailable("authorization state unavailable") from exc
        try:
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def application_exists(self, application_id: str) -> bool:
        return self._applications.exists(application_id)

    def applications_count(self) -> int:
        return self._applications.count()

    def applications_count_locked(self, work: Any) -> int:
        """Phase 10 WP-6b (design D-5 (ii)/(iii)): forwards to
        `PostgresApplicationRegistry.count_locked` -- see that method's
        own docstring for the full rationale (table-scoped constant-key
        `pg_advisory_xact_lock`, closes the phantom-write window an
        unlocked `applications_count() >= limit` pre-check cannot)."""
        return self._applications.count_locked(work)

    def list_applications(self):
        return self._applications.list_all()

    def register_application(self, application_id: str, *, work) -> None:
        self._applications.register(application_id, work=work)

    def set_application_enabled(self, application_id: str, enabled: bool, *, work) -> None:
        self._applications.set_enabled(application_id, enabled, work=work)

    def application_issuance_frozen(self, application_id: str) -> bool:
        return self._applications.issuance_frozen(application_id)

    def set_application_issuance_frozen(self, application_id: str, frozen: bool, *, work) -> None:
        self._applications.set_issuance_frozen(application_id, frozen, work=work)

    def credential_state(self, credential_id: str):
        return self._credentials.get_state(credential_id)

    def credentials_active_count(self, application_id: str) -> int:
        return self._credentials.count_active_for_application(application_id)

    def credentials_active_count_locked(self, application_id: str, work: Any) -> int:
        """The `credentials_per_application` counterpart of
        `applications_count_locked` above."""
        return self._credentials.count_active_for_application_locked(application_id, work)

    def list_credentials(self):
        return self._credentials.list_all()

    def issue_credential(self, application_id: str, role: str, *, credential_id: str, secret: str, work) -> None:
        self._credentials.issue(application_id, role, credential_id=credential_id, secret=secret, work=work)

    def rotate_credential(self, credential_id: str, secret: str, *, work) -> None:
        self._credentials.rotate(credential_id, secret=secret, work=work)

    def set_credential_state(self, credential_id: str, *, enabled=None, revoked=None, work) -> None:
        self._credentials.set_state(credential_id, enabled=enabled, revoked=revoked, work=work)

    def control_credential_state(self, credential_id: str):
        return self._control_credentials.get_state(credential_id)

    def list_control_credentials(self):
        return self._control_credentials.list_all()

    def control_credentials_locked(self, work):
        return self._control_credentials.locked_for_update(work)

    def rotate_control_credential(self, credential_id: str, secret: str, *, work) -> None:
        self._control_credentials.rotate(credential_id, secret=secret, work=work)

    def set_control_credential_state(self, credential_id: str, *, enabled=None, revoked=None, work) -> None:
        if enabled is not None:
            (self._control_credentials.enable if enabled else self._control_credentials.disable)(credential_id, work=work)
        if revoked:
            self._control_credentials.revoke(credential_id, work=work)

    def authenticate_control(self, secret) -> ControlPrincipal:
        return self._control_credentials.authenticate(secret)

    def authenticate_application(self, secret) -> Optional[tuple[str, str, str]]:
        """identical rationale to `InMemoryControlBackend.
        authenticate_application` above -- `self._credentials` is the SAME
        `PostgresCredentialRegistry` `issue_credential`/`rotate_credential`/
        `set_credential_state` already use.

        History: CH-0934
        """
        return self._credentials.authenticate(secret)

    def append_audit(self, *, work, **fields):
        return insert_control_audit_row(work, self._audit_schema, **fields)


# ===========================================================================
# Declare-and-echo phrases + declarations (contract 1.2.0 `destructive_
# confirmation`).
# ===========================================================================


def _revoke_last_control_credential_phrase(credential_id: str) -> str:
    return f"REVOKE control_credential {credential_id} @last_active=true"


def _reset_confirmation_phrase(active_credential_ids: list[str]) -> str:
    """State-fingerprinted (phrase_construction rule): the digest reflects
    exactly which control credentials are currently active, so any change
    to that set (another concurrent revoke/rotate/issue -- though nothing
    in this codebase issues a control credential in-band, R-6's own
    `deny_role_control`) invalidates a previously-obtained phrase."""
    canonical = json.dumps(sorted(active_credential_ids), separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
    return f"RESET control_credentials @active={digest}"


# Phase 3.5 WP-5 (design docs/design/PHASE35_CROSS_ENTITY_AND_CONTRACT_130_
# V1.md §4/§1-D, WP-4 m-1 symmetry): narrowed to MANAGEMENT credentials --
# an active `role="audit"` credential, if any, is untouched by this specific
# revoke and remains usable for the 3 read-only operations it was ever
# allowed (`_AUDIT_ROLE_ALLOWED_OPERATIONS`). The original wording ("every
# in-band control-plane credential becomes unusable") was true before this
# WP (every row in `control_credentials` WAS a control credential) but is no
# longer -- the actual consequence of losing the last CONTROL credential is
# that no in-band MANAGEMENT operation remains possible, not that every row
# is unusable.
_REVOKE_LAST_CONSEQUENCE = (
    "The last remaining active control credential is revoked; every in-band control-plane "
    "MANAGEMENT credential becomes unusable until the out-of-band reset ceremony runs (an "
    "audit credential, if any, remains usable but is read-only and cannot manage credentials)."
)
_REVOKE_LAST_REVERSIBLE_ALTERNATIVE = (
    "disable_credential reverses (this specific revoke is terminal, a disable is not) -- but "
    "re-enabling the last disabled control credential still requires its own out-of-band "
    "break-glass step, so disabling only defers needing one, it does not avoid it."
)
_REVOKE_LAST_RECOVERY = "The out-of-band operator reset ceremony issues a fresh control credential."

_RESET_CONSEQUENCE = (
    "Every existing control-table credential -- control OR audit, including any already-disabled "
    "or already-revoked row -- is revoked; exactly one new must-rotate control credential is "
    "issued in its place (an audit credential is not reissued automatically -- use "
    "issue-audit-credential again if one is still needed)."
)


# ===========================================================================
# ControlPlaneService
# ===========================================================================


class ControlPlaneService:
    """Evaluation order (design R-6, fixed at every one of the 9 methods
    below): rate-limit (pre-authentication) -> authenticate -> audit-role
    authorization gate (Phase 3.5 WP-5, §1-D/§4) -> must_rotate gate
    (authorization) -> [role=control capability denial, issue_credential
    only] -> shape validation of the remaining request fields ->
    target-existence resolution -> [issuance-freeze denial, issue_credential
    only, §1-E] -> bounds -> [destructive-confirmation gate, revoke_
    credential's last-active-control-credential case only] -> execute +
    same-transaction audit.
    """

    def __init__(self, backend, *, limits: Optional[ControlPlaneLimits] = None, clock=None,
                 audit_reader: Optional[AuditQueryReader] = None, audit_visibility_lag_ms: int = 0,
                 audit_event_classes: "frozenset[str]" = DECLARED_AUDIT_EVENT_CLASSES,
                 audit_operations: "frozenset[str]" = DECLARED_AUDIT_OPERATIONS,
                 audit_target_kinds: "frozenset[str]" = DECLARED_AUDIT_TARGET_KINDS,
                 audit_default_limit: int = _DEFAULT_AUDIT_QUERY_LIMIT,
                 audit_max_limit: int = _MAX_AUDIT_QUERY_LIMIT,
                 audit_coalescing_window_ms: int = DEFAULT_COALESCING_WINDOW_MS,
                 surfaces: Optional[dict] = None, process_ceiling: int = 1,
                 operation_catalog_url: Optional[str] = None) -> None:
        self._backend = backend
        # single source of truth for this
        # control-plane process' own `CapabilityDocument.surfaces` --
        # composition-root-injected (`control_composition.
        # build_control_service`'s own `MITATEDB_DATA_BASE_URL`/
        # `_CONTROL_BASE_URL` read), never derived here. `None` (every
        # pre-1.6.0-style direct construction -- most of this
        # repository's own tests) omits the key entirely.
        # history: CH-0935
        self._surfaces = surfaces
        # The control surface's own `CapabilityDocument` carries the SAME
        # `operation_catalog_url` value the data surface's own document
        # carries -- constructor-injected, same echo-only discipline as
        # `surfaces` immediately above. `control_composition.
        # build_control_service` reads `MITATEDB_OPERATION_CATALOG_URL`
        # (the same env var `main.py` reads).
        self._operation_catalog_url = operation_catalog_url
        self._limits = limits or ControlPlaneLimits()
        self._clock = clock or time.monotonic
        self._rate_lock = threading.Lock()
        self._rate_window: list[float] = []
        # Phase 4 WP-3(b) (design D-5/D-6): `audit_query`'s own state.
        # `audit_reader is None` is this instance's true, complete posture
        # for "AUDIT DSN not configured" (D-5 M-4) -- `control_capabilities`
        # below declares `audit_query: {"status": "unavailable"}` exactly
        # when this holds, and `audit_query()` refuses with `CAPABILITY_
        # UNSUPPORTED` (never a bare 404/AttributeError) on that same
        # condition. A SEPARATE pre-auth rate window from `_rate_window`
        # above (`_audit_rate_window`) -- `audit_query`'s own window must
        # never share a counter with `control_requests_per_minute` (design
        # M-8 / P4-D4 item 8): a high-frequency audit poller must never be
        # able to exhaust the window a break-glass `revoke_credential`
        # depends on.
        self._audit_reader = audit_reader
        self._audit_visibility_lag_ms = audit_visibility_lag_ms
        self._audit_event_classes = frozenset(audit_event_classes)
        self._audit_operations = frozenset(audit_operations)
        self._audit_target_kinds = frozenset(audit_target_kinds)
        self._audit_default_limit = audit_default_limit
        self._audit_max_limit = audit_max_limit
        self._audit_coalescing_window_ms = audit_coalescing_window_ms
        self._audit_rate_lock = threading.Lock()
        self._audit_rate_window: list[float] = []
        # the deployer's own declared
        # `process_ceilings.control` (default 1, matching every pre-
        # existing direct construction of this class -- this repository's
        # own tests included -- `limit_enforcement` for `control_
        # requests_per_minute`/`audit_requests_per_minute` stays
        # `enforced`, unchanged). `control_composition.
        # build_control_service` is the one real caller that passes a
        # value read from the single source `platform_declarations.
        # read_platform_declarations` returns.
        # history: CH-0936
        self._process_ceiling = process_ceiling

    @property
    def limits(self) -> ControlPlaneLimits:
        """a public read accessor for the composition root
        (`control_main.build_control_app`) to size the ASGI request-byte
        bound (`limits.request_bytes`) from the SAME `ControlPlaneLimits`
        instance this service enforces everything else against -- never a
        second, independently-configured copy of that number.

        History: CH-0937
        """
        return self._limits

    # ---- shared machinery -------------------------------------------------

    def check_rate(self) -> None:
        """Public wrapper around `_check_rate` (charges exactly one token,
        or raises `LIMIT_EXCEEDED`). Exists so an HTTP binding layer
        (`control_http.py`) can charge the rate window BEFORE it does
        anything else -- including reading/shape-checking a request body --
        for the endpoints whose request fields are extracted from the body
        before the corresponding service method is even called (`register_
        application`/`issue_credential`/`revoke_credential`). A caller that
        calls `check_rate()` itself must then pass `rate_precharged=True` to
        the operation method it goes on to call, or the window is charged
        twice for one logical request."""
        self._check_rate()

    def _check_rate(self) -> None:
        """R-6 rate-limit, pre-authentication (design's own exemption (i):
        never durably audited -- the actor is not yet known and auditing an
        unauthenticated flood would itself be an amplification vector)."""
        now = self._clock()
        with self._rate_lock:
            self._rate_window[:] = [stamp for stamp in self._rate_window if now - stamp < 60]
            if len(self._rate_window) >= self._limits.control_requests_per_minute:
                raise ResourceLimitError(
                    "control-plane request rate limit exceeded", limit_class="control_requests_per_minute")
            self._rate_window.append(now)

    def check_audit_rate(self) -> None:
        """Phase 4 WP-3(b) (design D-5, `check_rate`'s own public-wrapper
        precedent above): lets `control_http.py` charge `audit_query`'s own
        window before it even reads a request body, for the SAME reason
        `check_rate` documents. A caller that calls this itself and then
        `audit_query(..., rate_precharged=True)` must not also call `check_
        rate()` for the same request -- `audit_query` never touches
        `control_requests_per_minute` at all, by design (M-8 / P4-D4 item 8)."""
        self._check_audit_rate()

    def _check_audit_rate(self) -> None:
        """`audit_requests_per_minute` -- a SEPARATE global window from
        `_check_rate`'s `control_requests_per_minute` above (own lock, own
        list, own limit field), reusing the identical sliding-window
        mechanism (never a new one -- work order §6 item 5: no new
        constraint/enforcement mechanisms). Pre-auth, exactly like `_check_
        rate` (this window governs BOTH `/control/v1/audit/query` and its
        `/v1/audit/query` alias, before either path even extracts a bearer
        token) -- and, identically, never durably audited (rate-limit
        refusals carry no attributable actor yet)."""
        now = self._clock()
        with self._audit_rate_lock:
            self._audit_rate_window[:] = [stamp for stamp in self._audit_rate_window if now - stamp < 60]
            if len(self._audit_rate_window) >= self._limits.audit_requests_per_minute:
                raise ResourceLimitError(
                    "audit query request rate limit exceeded", limit_class="audit_requests_per_minute")
            self._audit_rate_window.append(now)

    def _deny_audit(self, *, event_class: str, operation: str, target_kind: Optional[str] = None,
                     request_id: Optional[str], actor_id: Optional[str] = None, actor_type: Optional[str] = None,
                     role: Optional[str] = None, application_id: Optional[str] = None, reason_code: str,
                     target_id: Optional[str] = None) -> None:
        """R-6: every denial (except the two exemptions -- rate-limit
        pre-auth, and `AUTH_STATE_UNAVAILABLE`, neither of which calls this)
        is durably recorded in its OWN transaction before the denial itself
        is raised by the caller. If the durable write itself fails, the
        failure is re-raised as a safe `FoundationError` (never a raw
        exception) so SI-10 holds even when a test injects an audit fault
        here.

        Phase 3.5 WP-5 (§1-C/§4): `target_id` -- the single target
        credential_id/application_id this denial concerns, when the caller
        supplied one."""
        try:
            with self._backend.unit_of_work() as work:
                self._backend.append_audit(
                    work=work, event_class=event_class, request_id=request_id, application_id=application_id,
                    actor_type=actor_type, actor_id=actor_id, role=role, operation=operation,
                    target_kind=target_kind, outcome="deny", reason_code=reason_code, target_id=target_id,
                )
        except FoundationError:
            raise
        except Exception as exc:
            raise StorageConfigurationError("the denial could not be durably recorded") from exc

    def _authenticate(self, secret: Optional[str], *, request_id: str) -> ControlPrincipal:
        """`secret` is the FULL presented bearer -- this peer's own
        `control_http.py` HTTP boundary passes the `Authorization: Bearer
        <...>` value through UNCHANGED (no pre-split, r2db-api's own
        `control_http.py::_extract_bearer` shape), and every public
        operation below forwards it here unchanged too. The split into
        `(credential_id, secret_part)` happens exactly once, downstream,
        inside `self._backend.authenticate_control` (`control_auth.
        ControlCredentialStore.authenticate` / `control_credential_store_
        postgres.PostgresControlCredentialStore.authenticate`).

        History: CH-0938
        """
        if secret is None:
            self._deny_audit(event_class="authentication_denial", operation="control_authenticate",
                             target_kind="control_credential", request_id=request_id, reason_code="AUTH_REQUIRED")
            raise AuthenticationRequiredError("authentication is required")
        try:
            return self._backend.authenticate_control(secret)
        except AuthorizationStateUnavailable:
            # Design exemption (ii): the store itself is unreachable, so a
            # durable audit write is also impossible -- never attempted.
            raise
        except AuthenticationError:
            self._deny_audit(event_class="authentication_denial", operation="control_authenticate",
                             target_kind="control_credential", request_id=request_id, reason_code="AUTH_INVALID")
            raise

    def _authorize_role(self, principal: ControlPrincipal, *, operation: str, request_id: str,
                        target_id: Optional[str] = None) -> None:
        """Phase 3.5 WP-5 (design docs/design/PHASE35_CROSS_ENTITY_AND_CONTRACT_130_
        V1.md §1-D/§4, P35-D12): contract `control_plane.authority` -- an
        `audit`-role principal is accepted ONLY on the 3 read-only control
        endpoints (`_AUDIT_ROLE_ALLOWED_OPERATIONS` below); every other
        control endpoint fails it closed with `FORBIDDEN`, durably audited
        (same discipline as `_gate_must_rotate` below, and deliberately
        checked as a SEPARATE, orthogonal gate from it: this is a
        role-authorization question, not a rotate-pending question -- a
        `role="control"` principal is never affected by this method at all,
        `must_rotate` or not).

        Two different dimensions here, not one: the OPERATION check is a
        genuine allow-list (`_AUDIT_ROLE_ALLOWED_OPERATIONS`), for the same
        reason `_gate_must_rotate`'s own allow-list is one -- a deny-list of
        operations would silently fail open the moment a new control
        endpoint is added and nobody remembers to list it. The ROLE check
        (`principal.role == "audit"` below) is, accurately, a deny-list: it
        gates only the one specific role value `"audit"`, and any OTHER
        role value would pass through this method entirely unrestricted.
        That is safe only because `control_credentials.role` carries a
        database `CHECK (role IN ('control', 'audit'))` (migration 0002) --
        no third role value can ever be stored, so "any other role" can only
        ever mean `"control"` in practice, which is exactly the role this
        method is meant to leave unrestricted. This role-dimension deny-list
        is backstopped by that constraint, not by anything in this method
        itself.

        Called at every one of the 9 public operations below, BEFORE
        `_gate_must_rotate` -- both gates ultimately agree that a
        rotate-pending audit principal may reach only `control_capabilities`
        (see `_gate_must_rotate`'s own docstring), but this one runs first
        so a non-rotate-pending audit principal calling a write endpoint
        gets the role-authorization denial, not a confusing must_rotate one.
        """
        if principal.role == "audit" and operation not in _AUDIT_ROLE_ALLOWED_OPERATIONS:
            self._deny_audit(event_class="authorization_denial", operation=operation, target_kind="control_credential",
                             request_id=request_id, actor_id=principal.credential_id, actor_type="control_credential",
                             role=principal.role, reason_code="FORBIDDEN", target_id=target_id)
            raise AuthorizationError(
                "this audit credential is not authorized for this operation; audit credentials are accepted "
                "only on the read-only control_capabilities, list_applications, list_credentials, and "
                "audit_query endpoints"
            )

    def _gate_must_rotate(self, principal: ControlPrincipal, *, operation: str, request_id: str,
                          self_rotate: bool = False) -> None:
        """Allow-list (never a deny-list, design's own explicit warning):
        only `control_capabilities` and a self-targeted `rotate_credential`
        pass while `must_rotate` is true. `FORBIDDEN` (WP-0 m-4: C-15
        requires this exact code, not `CAPABILITY_UNSUPPORTED`).

        a `role="audit"` principal's own
        allow-list while `must_rotate` is true is `control_capabilities`
        ONLY -- self-rotate is deliberately NOT extended to it (in practice
        `_authorize_role` above already forbids `rotate_credential` for an
        audit principal unconditionally, but this method stays role-aware
        on its own merits: `list_applications`/`list_credentials` both pass
        `_authorize_role`'s allow-list, and this gate must still hold them
        back while an audit credential's own `must_rotate` is true). This is
        not a dead end: the out-of-band audit-credential issuance ceremony
        (`issue_audit_credential_ceremony` below) issues AND rotates the
        credential in the same transaction before ever printing a secret, so
        a distributed audit credential's `must_rotate` is already `false` by
        the time anyone can authenticate with it -- an in-band audit
        principal is never actually stuck behind this gate in practice.

        History: CH-0939
        """
        if not principal.must_rotate:
            return
        if operation == "control_capabilities":
            return
        if principal.role == "control" and operation == "rotate_credential" and self_rotate:
            return
        self._deny_audit(event_class="authorization_denial", operation=operation, target_kind="control_credential",
                         request_id=request_id, actor_id=principal.credential_id, actor_type="control_credential",
                         role=principal.role, reason_code="FORBIDDEN")
        raise AuthorizationError("this control credential must be rotated before performing this operation")

    def _deny_role_control(self, principal: ControlPrincipal, application_id: Any, *, request_id: str) -> None:
        self._deny_audit(event_class="capability_denial", operation="issue_credential", target_kind="credential",
                         request_id=request_id, actor_id=principal.credential_id, actor_type="control_credential",
                         role=principal.role, application_id=application_id if isinstance(application_id, str) else None,
                         reason_code="CAPABILITY_UNSUPPORTED")
        raise CapabilityError(
            "issuing a role=control credential in-band is not supported; control credentials are "
            "created only by the operator bootstrap/reset ceremony",
            details=violation("capability", field="role"),
        )

    def _deny_issuance_frozen(self, principal: ControlPrincipal, application_id: str, *, request_id: str) -> None:
        """Phase 3.5 WP-5 (design §4/§1-E, P35-D6/D13): `FORBIDDEN` -- the
        contract's own chosen code for this refusal (no existing
        application-disabled issuance refusal exists to match, so the
        design stage fixed this one directly; `CONFLICT` was rejected as
        easily confused with the two-state application registry).
        Fail-closed, durably audited, same `_deny_audit` machinery as every
        other refusal here."""
        self._deny_audit(event_class="authorization_denial", operation="issue_credential", target_kind="credential",
                         request_id=request_id, actor_id=principal.credential_id, actor_type="control_credential",
                         role=principal.role, application_id=application_id, reason_code="FORBIDDEN")
        raise AuthorizationError(
            "credential issuance for this application is frozen (an out-of-band deployer operation); "
            "only an operator can lift the freeze"
        )

    def _validate_application_id(self, application_id: Any) -> None:
        if not isinstance(application_id, str) or not _APPLICATION_ID_PATTERN.fullmatch(application_id):
            # not an identifier the shared `identifiers.py`
            # syntax allowlist governs (a control-plane `application_id`
            # has its own, narrower pattern) -- `request_schema`, not
            # `identifier_syntax`. No raw candidate value is echoed
            # (SI-10): only the declared JSON type pair, mirroring
            # `field_types.check_declared_value`'s own convention for a
            # value that fails a declared shape.
            # history: CH-0940
            raise ValidationError(
                "application_id must match ^[a-z][a-z0-9_]{0,32}$",
                details=violation(
                    "request_schema", field="application_id", declared_type="string",
                    observed_type=observed_type_of(application_id),
                ),
            )

    def _locate_credential(self, credential_id: Any) -> tuple[Optional[str], Optional[tuple]]:
        if not isinstance(credential_id, str):
            return None, None
        state = self._backend.credential_state(credential_id)
        if state is not None:
            return "application", state
        state = self._backend.control_credential_state(credential_id)
        if state is not None:
            return "control", state
        return None, None

    # ---- public operations --------------------------------------------------

    def control_capabilities(self, secret, *, request_id: Optional[str] = None, rate_precharged: bool = False) -> dict:
        request_id = request_id or _new_request_id()
        if not rate_precharged:
            self._check_rate()
        principal = self._authenticate(secret, request_id=request_id)
        self._authorize_role(principal, operation="control_capabilities", request_id=request_id)
        self._gate_must_rotate(principal, operation="control_capabilities", request_id=request_id)
        limits = self._limits.as_dict()
        limit_enforcement = {name: "enforced" for name in limits}
        # R-7: the HTTP-layer enforcement fact (`control_http.py`, WP-5
        # mount) is added on top of this service-layer default -- this
        # process alone cannot enforce a byte bound with no HTTP boundary.
        limit_enforcement["request_bytes"] = "unavailable"
        # Phase 10 WP-6b (design D-5 (ii)): region (ii) of the 3-region
        # map -- `control_requests_per_minute`/`audit_requests_per_minute`
        # are bound in this process' own in-memory sliding window
        # (`_check_rate`/`_check_audit_rate` above, process-wide state,
        # never per-application/per-request), so the `enforced` default
        # above only describes the whole deployment while exactly one
        # process may serve this base URL -- it degrades to `deployment_
        # required` once the deployer declares more than one may.
        # `applications`/`credentials_per_application` (region (iii),
        # DB-side-bound) are UNAFFECTED -- they stay `enforced` above
        # regardless of ceiling (see `applications_count_locked`/
        # `credentials_active_count_locked` below for what makes that
        # claim hold under concurrency).

        # design D-3 (4): routed through the SAME 2-strategy helper the
        # data plane's own `capabilities_document.py` uses --
        # `configured=False` unconditionally (control's 2 region-(ii)
        # classes stay in-process), so this reduces to the single-process
        # `ceiling <= 1` rule.
        for name in ("control_requests_per_minute", "audit_requests_per_minute"):
            limit_enforcement[name] = resolve_limit_enforcement(configured=False, ceiling=self._process_ceiling)
        return {
            # Phase 4 WP-3(b) (P4-D4, contract `versioning.version_binding`),
            # flipped to 1.5.0 in Phase 5 WP-3 (design D-1, subordinate
            # ruling 10 item 1, same commit as the `operations`/
            # `target_kinds` declaration keys below -- flip and behavior
            # land together, never separately): unconditional (every
            # instance of this service declares 1.5.0 now, whether or not
            # `audit_query` itself is `enabled` on this deployment; the
            # 1.4.0/1.5.0 obligations conditional on `audit_query` being
            # provided stay conditional per version_binding's own text).
            # Phase 6 WP-3 (design D-1/D-2, subordinate ruling 11):
            # flipped to 1.6.0 -- same commit as `surfaces` (already
            # present, WP-3 D-2) and the composed-bearer issue/rotate
            # responses (`control_http.py::_with_composed_secret`).
            #
            # Phase 9 WP-3e (design D-1 (5)/(7), F-1): flipped to 1.7.0 --
            # the SAME commit as the data-plane document's own identical
            # flip (`cell.py::ApplicationRuntime.capabilities`) -- C-19's
            # own data/control `contract_version` agreement assert is
            # what this pairing keeps green.
            #
            # Phase 10 WP-6b/pair-closing (design D-5 (v)): flipped again
            # to 1.8.0 -- the SAME commit as the data-plane document's own
            # identical flip and this host's own `process_ceilings`
            # mapping (D-5 (ii)).
            #
            # This control-plane document also flips to 1.9.0 in the same commit as the data-plane document's own identical flip (C-19's cross-plane version-match assert). The control surface's own `capabilities` (`control_plane`/`audit_query`) are unaffected -- 1.9.0's `common_baseline` obligation governs the data surface's application-plane operations only.
            #
            # This control-plane document also flips to 1.10.0 in the same commit as the data-plane document's own identical flip (C-19's cross-plane version-match assert). The control surface's own `capabilities` (`control_plane`/`audit_query`) are unaffected -- 1.10.0's own obligations govern the data surface's structured-query operations only.
            #
            # This control-plane document also flips to 1.11.0 in the same commit as the data-plane document's own identical flip (C-19's cross-plane version-match assert). The control surface's own `capabilities` (`control_plane`/`audit_query`) are unaffected -- 1.11.0's own obligation governs the data surface's select/where/order_by/mutation-values operations only. This control-plane document declares 1.12.0 in the same commit as the data-plane document, with no behavior change: 1.12.0 only withdraws the contract's own word for the shape of the `audit_requests_per_minute` window, which this service counts as a sliding one. This control-plane document declares 1.13.0 in the same commit as the data-plane document (C-19's cross-plane version-match assert). This control-plane document declares contract 1.14.0 in the same commit as the data-plane document, with no behavior change. This control-plane document declares 1.15.0 in the same commit as the data-plane document, with no behavior change: 1.15.0 only rewrites the contract's retention clause for the `endpoints.audit_query` alias; this surface keeps serving both paths unchanged. This control-plane document declares 1.16.0 in the same commit as the data-plane document (C-19's cross-plane version-match assert); the control surface's own `capabilities` are unaffected -- 1.16.0's obligations govern the requests `limits.execution_ms` names, none of which is a control-surface request.
            # history: CH-0543
            "contract_version": "1.16.0",
            "capabilities": {
                "control_plane": {"status": "enabled"},
                "audit_query": self._audit_capability_declaration(),
            },
            **({"surfaces": self._surfaces} if self._surfaces is not None else {}),
            **({"operation_catalog_url": self._operation_catalog_url} if self._operation_catalog_url is not None else {}),
            "limits": limits,
            "limit_enforcement": limit_enforcement,
            "authorization_propagation_bound_ms": 0,
            # Phase 3.5 WP-5 (design §4, review m-6): the real, authenticated
            # principal's own role -- never a hardcoded `"control"` literal
            # (a `role="audit"` principal reaches this same method).
            "role": principal.role,
        }

    def _audit_capability_declaration(self) -> dict:
        """Phase 4 WP-3(b) (design D-5's own JSON shape, mirroring r2db-
        api's identical declaration). `status`'s vocabulary is the
        contract's own `capability_status.status_enum` (4 values) -- never
        the word `"available"`, which is not a member. AUDIT DSN
        unconfigured (`self._audit_reader is None`) keeps the declaration
        at exactly `{"status": "unavailable"}` (D-5 M-4) -- every other key
        below is published only once there is a real reader to back it."""
        if self._audit_reader is None:
            return {"status": "unavailable"}
        return {
            "status": "enabled",
            "authority": "control_or_audit",
            "event_classes": sorted(self._audit_event_classes),
            # Phase 5 WP-3 (design D-1, contract 1.5.0 subordinate ruling 10
            # item 1, conditional on `audit_query` being provided): the
            # `operation`/`target_kind` vocabulary this reader can ever
            # surface -- same declare-the-hazard posture as `event_classes`
            # above, not the `capability_status.defined.atomic_mutation.
            # operations` execution vocabulary (contract's own disambiguation
            # note).
            "operations": sorted(self._audit_operations),
            "target_kinds": sorted(self._audit_target_kinds),
            "default_limit": self._audit_default_limit,
            "max_limit": self._audit_max_limit,
            # D-6 point 3: a DERIVED value (composition root's own two
            # writer-connection timeouts + 1s clock-skew margin), never a
            # bare constant this class invents on its own.
            "visibility_lag_ms": self._audit_visibility_lag_ms,
            "coalescing_window_ms": self._audit_coalescing_window_ms,
            "completeness_note": (
                "A page shorter than limit does not mean the log is exhausted -- rows within "
                "visibility_lag_ms of the current time are not yet returned. Keep polling with the "
                "cursor of the last event received (the opaque per-event 'cursor' field, passed back "
                "as the next request's 'after') until a page comes back empty."
            ),
            "outcome_note": (
                "outcome=allow means the operation was authorized and submitted; a later outcome=error "
                "row sharing the same request_id means the service did not see it commit: either it did "
                "not commit, or the connection was lost during the commit itself and its outcome is "
                "unknown. An allow row with no "
                "corresponding error row usually means the operation committed, but -- if the process "
                "was lost between recording allow and committing, or if the error row itself could not "
                "be recorded -- can also mean it did not; the audit trail alone cannot distinguish the "
                "two in those cases."
            ),
            # Contract `audit.query_event_fields_note` verbatim ("present
            # only on an event representing more than one coalesced
            # occurrence, absent -- never zero or one -- otherwise").
            "count_note": (
                "count is the number of occurrences the ONE row represents; a row representing exactly "
                "one occurrence never carries it (never 0, never 1) -- absence means one occurrence, "
                "same as an ordinary uncoalesced event."
            ),
            # D-6: this implementation's cursor is a pure KEYSET position
            # (`(recorded_at, plane, event_id)`, opaque-encoded) -- it
            # always resolves to a real position in the total order
            # regardless of which `event_classes` filter accompanies it, so
            # a cursor obtained under one filter is accepted under a
            # DIFFERENT filter too.
            "cursor_note": (
                "cursor is a filter-independent position token (a keyset position in the total order, "
                "opaque-encoded) -- it always resolves, and may be reused as 'after' under a different "
                "event_classes filter than the one that produced it."
            ),
        }

    def register_application(self, secret, application_id, *, request_id: Optional[str] = None, rate_precharged: bool = False) -> dict:
        request_id = request_id or _new_request_id()
        if not rate_precharged:
            self._check_rate()
        principal = self._authenticate(secret, request_id=request_id)
        self._authorize_role(principal, operation="register_application", request_id=request_id)
        self._gate_must_rotate(principal, operation="register_application", request_id=request_id)
        self._validate_application_id(application_id)

        # Phase 10 WP-6b (design D-5 (ii)/(iii)): the capacity check now
        # runs INSIDE the SAME transaction that performs the write, via
        # `applications_count_locked` -- for `PostgresControlBackend` that
        # takes a table-scoped constant-key `pg_advisory_xact_lock` first
        # (`control_plane._take_bound_advisory_lock`), which blocks a
        # concurrent registration's own `applications_count_locked` (same
        # key) until THIS transaction commits or rolls back. Before this
        # WP, the count ran on its own, already-committed connection,
        # entirely outside this transaction -- two concurrent `register_
        # application` calls could each observe a count one under the
        # limit and both proceed, overshooting it (the TOCTOU window
        # design D-5(ii) requires closed, not weakened).
        # `InMemoryControlBackend.applications_count_locked` is a plain
        # forward to `applications_count` because that backend's own
        # `unit_of_work()` already holds a process-wide lock for this
        # whole block.
        with self._backend.unit_of_work() as work:
            if self._backend.application_exists(application_id):
                raise ConflictError("application already exists")
            if self._backend.applications_count_locked(work) >= self._limits.applications:
                raise ResourceLimitError("application registration limit exceeded", limit_class="applications")
            self._backend.register_application(application_id, work=work)
            self._backend.append_audit(
                work=work, event_class="application_lifecycle", request_id=request_id, application_id=application_id,
                actor_type="control_credential", actor_id=principal.credential_id, role=principal.role,
                operation="register_application", target_kind="application", outcome="allow", reason_code=None,
                target_id=application_id,
            )
        return {"application_id": application_id, "enabled": True}

    def list_applications(self, secret, *, request_id: Optional[str] = None, rate_precharged: bool = False) -> dict:
        request_id = request_id or _new_request_id()
        if not rate_precharged:
            self._check_rate()
        principal = self._authenticate(secret, request_id=request_id)
        self._authorize_role(principal, operation="list_applications", request_id=request_id)
        self._gate_must_rotate(principal, operation="list_applications", request_id=request_id)
        return {"applications": [{"application_id": aid, "enabled": enabled}
                                  for aid, enabled in self._backend.list_applications()]}

    def set_application_enabled(self, secret, application_id, enabled, *,
                                 request_id: Optional[str] = None, rate_precharged: bool = False) -> dict:
        request_id = request_id or _new_request_id()
        if not rate_precharged:
            self._check_rate()
        principal = self._authenticate(secret, request_id=request_id)
        if not isinstance(enabled, bool):
            raise ValidationError(
                "enabled must be a boolean",
                details=violation("request_schema", field="enabled", declared_type="boolean", observed_type=observed_type_of(enabled)),
            )
        operation = "enable_application" if enabled else "disable_application"
        self._authorize_role(principal, operation=operation, request_id=request_id,
                             target_id=application_id if isinstance(application_id, str) else None)
        self._gate_must_rotate(principal, operation=operation, request_id=request_id)
        if not self._backend.application_exists(application_id):
            raise NotFoundError("application was not found")

        with self._backend.unit_of_work() as work:
            self._backend.set_application_enabled(application_id, enabled, work=work)
            self._backend.append_audit(
                work=work, event_class="application_lifecycle", request_id=request_id, application_id=application_id,
                actor_type="control_credential", actor_id=principal.credential_id, role=principal.role,
                operation=operation, target_kind="application", outcome="allow", reason_code=None,
                target_id=application_id,
            )
        return {"application_id": application_id, "enabled": enabled}

    def issue_credential(self, secret, application_id, role, *, request_id: Optional[str] = None, rate_precharged: bool = False) -> dict:
        request_id = request_id or _new_request_id()
        if not rate_precharged:
            self._check_rate()
        principal = self._authenticate(secret, request_id=request_id)
        self._authorize_role(principal, operation="issue_credential", request_id=request_id)
        self._gate_must_rotate(principal, operation="issue_credential", request_id=request_id)
        if role not in _ISSUABLE_ROLES:
            # 追補 4 O-1: an accepted-value-set violation, not a JSON-
            # type mismatch (`role` may well already be a string) --
            # `declared_type`/`observed_type` omitted (V-2: "形の違反な
            # ら不要").
            raise ValidationError(
                "role must be one of runtime, developer, control",
                details=violation("request_schema", field="role"),
            )
        self._validate_application_id(application_id)
        # Capability denial BEFORE target resolution/freeze/limit (C-14
        # vector 3; Phase 3.5 §1-E/M-8 extends the same precedence to the
        # freeze refusal below): must refuse `role=control` even when the
        # named application does not exist, is disabled, is frozen, or is
        # already at its credential limit -- none of those questions are
        # reached.
        if role == "control":
            self._deny_role_control(principal, application_id, request_id=request_id)
        if not self._backend.application_exists(application_id):
            raise NotFoundError("application was not found")
        # Phase 3.5 WP-5 (§4/§1-E, P35-D6/D13): per-application issuance
        # freeze -- an out-of-band (CLI-only) deployer operation.
        # `FORBIDDEN`/fail-closed/durably audited, evaluated after target
        # resolution (a freeze on a nonexistent application is meaningless)
        # but before the credentials_per_application limit check (grouped
        # with "application existence/state" resolution, contract `issue_
        # credential.semantics`'s own precedence sentence).
        if self._backend.application_issuance_frozen(application_id):
            self._deny_issuance_frozen(principal, application_id, request_id=request_id)

        new_credential_id = _new_credential_id()
        new_secret = _new_secret()
        # Phase 10 WP-6b (design D-5 (ii)/(iii)): the capacity check now
        # runs INSIDE the SAME transaction that performs the write, via
        # `credentials_active_count_locked` -- see `register_application`'s
        # own identical-shaped comment above for the phantom-write window
        # this closes (here: `credentials_active_count() >= limit`).
        with self._backend.unit_of_work() as work:
            if self._backend.credentials_active_count_locked(application_id, work) >= self._limits.credentials_per_application:
                raise ResourceLimitError(
                    "credentials-per-application limit exceeded", limit_class="credentials_per_application")
            self._backend.issue_credential(application_id, role, credential_id=new_credential_id, secret=new_secret, work=work)
            self._backend.append_audit(
                work=work, event_class="credential_lifecycle", request_id=request_id, application_id=application_id,
                actor_type="control_credential", actor_id=principal.credential_id, role=principal.role,
                operation="issue_credential", target_kind="credential", outcome="allow", reason_code=None,
                target_id=new_credential_id,
            )
        # Phase 6 WP-3 追補 (brief item A):
        # composed HERE, at this in-band issuance point's own response --
        # `control_http.py`'s HTTP boundary now uses this dict verbatim
        # (its own earlier `_with_composed_secret` wrapper is removed),
        # and `ops.py cmd_rotate_credential`'s CLI print path (which calls
        # THIS SAME service method) receives the composed value too, no
        # second composition anywhere downstream.
        # history: CH-0942
        return {"credential_id": new_credential_id, "application_id": application_id, "role": role,
                "secret": compose_bearer_locator(new_credential_id, new_secret)}

    def list_credentials(self, secret, *, request_id: Optional[str] = None, rate_precharged: bool = False) -> dict:
        request_id = request_id or _new_request_id()
        if not rate_precharged:
            self._check_rate()
        principal = self._authenticate(secret, request_id=request_id)
        self._authorize_role(principal, operation="list_credentials", request_id=request_id)
        self._gate_must_rotate(principal, operation="list_credentials", request_id=request_id)
        rows: list[dict] = []
        for cid, app_id, role, enabled, revoked in self._backend.list_credentials():
            # Application-credential rows never carry `must_rotate` at all
            # (P35-D7, contract `CredentialsResult.credentials[].must_
            # rotate` description) -- the concept does not exist for them.
            rows.append({"credential_id": cid, "application_id": app_id, "role": role, "enabled": enabled, "revoked": revoked})
        for cid, enabled, revoked, must_rotate, ctl_role in self._backend.list_control_credentials():
            # No `application_id` key at all (design §2, unchanged for
            # `role="audit"` rows too -- neither kind belongs to an
            # Application). Phase 3.5 WP-5 (§4/§1-B, P35-D7 reversal of the
            # original §8 m-9 omission): `must_rotate` is now exposed here
            # with its real value for every control-table row (control OR
            # audit) -- the store has the value and contract 1.3.0 makes the
            # field optional-additive, so there is no longer a reason to
            # withhold it. This does widen who can observe a not-yet-
            # rotated credential's existence (an `audit`-role principal can
            # now read this same listing), but no secret/verifier is ever
            # included, and this is documented, intended operational
            # visibility (CONTROL_MAPPING.md SI-10/SI-02). `role` reads the
            # real column instead of a hardcoded `"control"` literal.
            rows.append({"credential_id": cid, "role": ctl_role, "enabled": enabled, "revoked": revoked, "must_rotate": must_rotate})
        return {"credentials": rows}

    def rotate_credential(self, secret, target_credential_id, *, request_id: Optional[str] = None, rate_precharged: bool = False) -> dict:
        request_id = request_id or _new_request_id()
        if not rate_precharged:
            self._check_rate()
        principal = self._authenticate(secret, request_id=request_id)
        self_rotate = isinstance(target_credential_id, str) and target_credential_id == principal.credential_id
        self._authorize_role(principal, operation="rotate_credential", request_id=request_id,
                             target_id=target_credential_id if isinstance(target_credential_id, str) else None)
        self._gate_must_rotate(principal, operation="rotate_credential", request_id=request_id, self_rotate=self_rotate)
        kind, state = self._locate_credential(target_credential_id)
        if kind is None:
            raise NotFoundError("credential was not found")
        if state[1]:  # revoked
            # O-8 (版フリップ監査, ruling
            # 追補4): "対象の状態が操作と矛盾する" refusal (a revoked
            # credential cannot be rotated) is a resource-STATE conflict,
            # not a request-shape/identifier-syntax/deployment-capability
            # question the 11-word `violated_declaration_vocabulary` was
            # built to describe -- ConflictError (CONFLICT, status 409),
            # matching r2db-api's own same-site fix; not a forced fit into
            # ValidationError's own vocabulary. `details` is optional for
            # CONFLICT (O-8); `field: credential_id` is kept since one IS
            # attributable.
            # history: CH-0945
            raise ConflictError("a revoked credential cannot be rotated", details={"field": "credential_id"})
        new_secret = _new_secret()

        if kind == "application":
            with self._backend.unit_of_work() as work:
                self._backend.rotate_credential(target_credential_id, new_secret, work=work)
                self._backend.append_audit(
                    work=work, event_class="credential_lifecycle", request_id=request_id,
                    actor_type="control_credential", actor_id=principal.credential_id, role=principal.role,
                    operation="rotate_credential", target_kind="credential", outcome="allow", reason_code=None,
                    target_id=target_credential_id,
                )
            # Phase 6 WP-3 追補 (brief item A): composed HERE, same
            # single-point discipline `issue_credential` above follows.
            return {"credential_id": target_credential_id, "secret": compose_bearer_locator(target_credential_id, new_secret)}

        with self._backend.unit_of_work() as work:
            self._backend.rotate_control_credential(target_credential_id, new_secret, work=work)
            self._backend.append_audit(
                work=work, event_class="control_credential_lifecycle", request_id=request_id,
                actor_type="control_credential", actor_id=principal.credential_id, role=principal.role,
                operation="rotate_credential", target_kind="control_credential", outcome="allow", reason_code=None,
                target_id=target_credential_id,
            )
        return {"credential_id": target_credential_id, "secret": compose_bearer_locator(target_credential_id, new_secret)}

    def revoke_credential(self, secret, target_credential_id, *, destructive=None, confirmation=None,
                          request_id: Optional[str] = None, rate_precharged: bool = False) -> dict:
        request_id = request_id or _new_request_id()
        if not rate_precharged:
            self._check_rate()
        principal = self._authenticate(secret, request_id=request_id)
        self._authorize_role(principal, operation="revoke_credential", request_id=request_id,
                             target_id=target_credential_id if isinstance(target_credential_id, str) else None)
        self._gate_must_rotate(principal, operation="revoke_credential", request_id=request_id)
        # Shape-validate `destructive`/`confirmation` unconditionally
        # (contract: these fields are ordinary, schema-validated optional
        # fields regardless of whether this particular revoke ever meets
        # the gate condition below).
        if destructive is not None and not isinstance(destructive, bool):
            raise ValidationError(
                "destructive must be a boolean",
                details=violation("request_schema", field="destructive", declared_type="boolean", observed_type=observed_type_of(destructive)),
            )
        if confirmation is not None and not isinstance(confirmation, str):
            raise ValidationError(
                "confirmation must be a string",
                details=violation("request_schema", field="confirmation", declared_type="string", observed_type=observed_type_of(confirmation)),
            )
        kind, state = self._locate_credential(target_credential_id)
        if kind is None:
            raise NotFoundError("credential was not found")

        if kind == "application":
            # Contract `non_destructive_requests`: an application
            # credential's revocation is never gated.
            with self._backend.unit_of_work() as work:
                self._backend.set_credential_state(target_credential_id, revoked=True, work=work)
                self._backend.append_audit(
                    work=work, event_class="credential_lifecycle", request_id=request_id,
                    actor_type="control_credential", actor_id=principal.credential_id, role=principal.role,
                    operation="revoke_credential", target_kind="credential", outcome="allow", reason_code=None,
                    target_id=target_credential_id,
                )
            return {"credential_id": target_credential_id, "enabled": state[0], "revoked": True}

        with self._backend.unit_of_work() as work:
            rows = self._backend.control_credentials_locked(work)
            matching = next((row for row in rows if row[0] == target_credential_id), None)
            if matching is None:
                raise NotFoundError("credential was not found")
            _cid, enabled_now, revoked_now, _matching_role = matching
            # Phase 3.5 WP-5: filtered to `role == "control"` rows only --
            # the destructive-confirmation gate exists to protect the LAST
            # remaining active CONTROL credential (the only kind that can
            # perform any control-plane management operation at all). An
            # `"audit"` row existing alongside the sole active control
            # credential must not be able to mask it as "not the last one":
            # revoking that control credential would still leave zero
            # credentials capable of management, even though an audit
            # credential remains active. Symmetrically, revoking an audit
            # credential itself never trips this gate at all (it is
            # excluded from `active_ids`, so `active_ids[0] ==
            # target_credential_id` can never hold for one) -- an ordinary,
            # unconfirmed revoke, exactly like an application credential's.
            active_ids = [row[0] for row in rows if row[1] and not row[2] and row[3] == "control"]
            if len(active_ids) == 1 and active_ids[0] == target_credential_id:
                phrase = _revoke_last_control_credential_phrase(target_credential_id)
                if destructive is not True or confirmation != phrase:
                    self._deny_audit(
                        event_class="control_credential_lifecycle", operation="revoke_credential",
                        target_kind="control_credential", request_id=request_id, actor_id=principal.credential_id,
                        actor_type="control_credential", role=principal.role,
                        reason_code="DESTRUCTIVE_CONFIRMATION_REQUIRED", target_id=target_credential_id,
                    )
                    raise DestructiveConfirmationRequired(
                        "revoking the last remaining active control credential requires the current "
                        "confirmation phrase",
                        details={
                            "required_confirmation": phrase,
                            "consequence": _REVOKE_LAST_CONSEQUENCE,
                            "reversible_alternative": _REVOKE_LAST_REVERSIBLE_ALTERNATIVE,
                            "recovery": _REVOKE_LAST_RECOVERY,
                            "audited": True,
                        },
                    )
            self._backend.set_control_credential_state(target_credential_id, revoked=True, work=work)
            self._backend.append_audit(
                work=work, event_class="control_credential_lifecycle", request_id=request_id,
                actor_type="control_credential", actor_id=principal.credential_id, role=principal.role,
                operation="revoke_credential", target_kind="control_credential", outcome="allow", reason_code=None,
                target_id=target_credential_id,
            )
        return {"credential_id": target_credential_id, "enabled": enabled_now, "revoked": True}

    def set_credential_enabled(self, secret, target_credential_id, enabled, *,
                               request_id: Optional[str] = None, rate_precharged: bool = False) -> dict:
        request_id = request_id or _new_request_id()
        if not rate_precharged:
            self._check_rate()
        principal = self._authenticate(secret, request_id=request_id)
        if not isinstance(enabled, bool):
            raise ValidationError(
                "enabled must be a boolean",
                details=violation("request_schema", field="enabled", declared_type="boolean", observed_type=observed_type_of(enabled)),
            )
        operation = "enable_credential" if enabled else "disable_credential"
        self._authorize_role(principal, operation=operation, request_id=request_id,
                             target_id=target_credential_id if isinstance(target_credential_id, str) else None)
        self._gate_must_rotate(principal, operation=operation, request_id=request_id)
        kind, state = self._locate_credential(target_credential_id)
        if kind is None:
            raise NotFoundError("credential was not found")

        if kind == "application":
            with self._backend.unit_of_work() as work:
                self._backend.set_credential_state(target_credential_id, enabled=enabled, work=work)
                self._backend.append_audit(
                    work=work, event_class="credential_lifecycle", request_id=request_id,
                    actor_type="control_credential", actor_id=principal.credential_id, role=principal.role,
                    operation=operation, target_kind="credential", outcome="allow", reason_code=None,
                    target_id=target_credential_id,
                )
            return {"credential_id": target_credential_id, "enabled": enabled, "revoked": state[1]}

        with self._backend.unit_of_work() as work:
            self._backend.set_control_credential_state(target_credential_id, enabled=enabled, work=work)
            self._backend.append_audit(
                work=work, event_class="control_credential_lifecycle", request_id=request_id,
                actor_type="control_credential", actor_id=principal.credential_id, role=principal.role,
                operation=operation, target_kind="control_credential", outcome="allow", reason_code=None,
                target_id=target_credential_id,
            )
        return {"credential_id": target_credential_id, "enabled": enabled, "revoked": state[1]}

    def audit_query(self, secret, request: Any, *, request_id: Optional[str] = None,
                     rate_precharged: bool = False) -> dict:
        """Phase 4 WP-3(b) (design D-5/D-6). Processing order: `audit_
        requests_per_minute` (its OWN window, never `control_requests_per_
        minute`) -> application-credential probe (identified FORBIDDEN,
        BEFORE the control-credential store ever sees this bearer -- see
        `_deny_application_credential_on_audit_query`'s own docstring for
        why the ordering matters) -> ordinary control/audit authentication
        -> role authorization (`_AUDIT_ROLE_ALLOWED_OPERATIONS` now
        includes `audit_query`) -> must_rotate gate -> `CAPABILITY_
        UNSUPPORTED` when no reader is configured (D-5 M-4: the route
        answers this AFTER authenticating, never a bare 404) -> request
        shape/semantic validation -> the real read."""
        request_id = request_id or _new_request_id()
        if not rate_precharged:
            self._check_audit_rate()
        # D-5's own authority-separation requirement: probe the
        # APPLICATION-credential universe first. If this bearer genuinely
        # authenticates there, deny it here -- attributed, `FORBIDDEN` --
        # without ever presenting it to `self._authenticate` below (which
        # would otherwise durably record an unattributed `AUTH_INVALID`
        # denial for a credential that, in fact, belongs to a real
        # application credential, a confusing and duplicative record for
        # one request).
        if secret is not None:
            app_match = self._backend.authenticate_application(secret)
            if app_match is not None:
                self._deny_application_credential_on_audit_query(app_match, request_id=request_id)
        principal = self._authenticate(secret, request_id=request_id)
        self._authorize_role(principal, operation="audit_query", request_id=request_id)
        self._gate_must_rotate(principal, operation="audit_query", request_id=request_id)
        if self._audit_reader is None:
            self._deny_audit_capability_unsupported(principal, request_id=request_id)
        if not isinstance(request, dict):
            raise ValidationError(
                "AuditQueryRequest must be an object",
                details=violation("request_schema", declared_type="object", observed_type=observed_type_of(request)),
            )
        event_classes = validate_audit_event_classes(request.get("event_classes"), max_classes=_MAX_AUDIT_QUERY_EVENT_CLASSES)
        after = validate_audit_after(request.get("after"))
        limit = validate_audit_limit(request.get("limit"), default=self._audit_default_limit, maximum=self._audit_max_limit)
        rows = self._audit_reader.query(event_classes=event_classes, after=after, limit=limit,
                                        visibility_lag_ms=self._audit_visibility_lag_ms)
        return {"events": [shape_audit_query_row(row) for row in rows]}

    def _deny_application_credential_on_audit_query(self, app_match: tuple, *,
                                                     request_id: str) -> None:
        """Contract `control_endpoints.audit_query.semantics`: "Application
        credentials are denied." Always attributed (`app_match` -- a
        `(credential_id, application_id, role)` triple -- names a real,
        currently-active application credential this call already
        confirmed) -- see `audit_query`'s own docstring for why this must
        run BEFORE `self._authenticate` ever sees the same bearer."""
        credential_id, application_id, role = app_match
        self._deny_audit(
            event_class="authorization_denial", operation="audit_query", target_kind="credential",
            request_id=request_id, actor_id=credential_id, actor_type="application_credential", role=role,
            application_id=application_id, reason_code="FORBIDDEN",
        )
        raise AuthorizationError(
            "application credentials are denied on audit_query; audit evidence requires control or audit authority"
        )

    def _deny_audit_capability_unsupported(self, principal: ControlPrincipal, *, request_id: str) -> None:
        """D-5 M-4: AUDIT DSN not configured -- the route is always
        registered and always authenticates first (never a bare 404), and
        this refusal is durably recorded like every other control-plane
        capability denial (mirrors `_deny_role_control`'s identical
        `CAPABILITY_UNSUPPORTED` precedent)."""
        self._deny_audit(
            event_class="capability_denial", operation="audit_query", target_kind="control_credential",
            request_id=request_id, actor_id=principal.credential_id, actor_type="control_credential",
            role=principal.role, reason_code="CAPABILITY_UNSUPPORTED",
        )
        raise CapabilityError(
            "audit evidence query is not available on this deployment",
            details=violation("capability"),
        )


# ===========================================================================
# Ceremony core (design R-6: reusable product functions -- a future WP-5
# CLI entry point and, separately, an in-process adapter both call this SAME
# code; WP-4 builds no CLI at all, this module is imported and driven only
# by direct tests).
# ===========================================================================


def bootstrap_control_credential(control_credentials, audit_append, *, work, credential_id: Optional[str] = None,
                                  secret: Optional[str] = None, request_id: Optional[str] = None,
                                  actor_type: str = "operator_cli") -> tuple[str, str]:
    """Contract `control_plane.bootstrap`: refuses (`CONFLICT`) when ANY
    control-credential row exists, including a fully-revoked one ("while a
    control credential exists", not "while an unrevoked one exists").
    Issues one must_rotate credential and appends the canonical audit event
    inside the SAME `work` the caller already opened."""
    if control_credentials.has_any(include_revoked=True, work=work):
        raise ConflictError("a control credential already exists; bootstrap runs at most once -- use reset to recover")
    credential_id, secret = control_credentials.issue(
        must_rotate=True, credential_id=credential_id, secret=secret, work=work)
    audit_append(
        work=work, event_class="control_credential_lifecycle", request_id=request_id, application_id=None,
        actor_type=actor_type, actor_id=None, role=None, operation="bootstrap_control_credential",
        target_kind="control_credential", outcome="allow", reason_code=None, target_id=credential_id,
    )
    return credential_id, secret


def reset_control_credentials(control_credentials, audit_append, *, work, destructive, confirmation,
                              credential_id: Optional[str] = None, secret: Optional[str] = None,
                              request_id: Optional[str] = None, actor_type: str = "operator_cli") -> tuple[str, str]:
    """Contract `control_plane.reset`: revokes EVERY existing control
    credential (including already-disabled/already-revoked rows) and mints
    exactly one new must_rotate credential, atomically (`work`). Design R-6:
    reset is one of the CLI's own irreversible subcommands and is therefore
    gated by declare-and-echo -- the required phrase is a digest over the
    currently-active credential id set (`_reset_confirmation_phrase`), so a
    denial's own `required_confirmation` goes stale the moment that set
    changes again."""
    if not isinstance(destructive, bool):
        raise ValidationError(
            "destructive must be a boolean",
            details=violation("request_schema", field="destructive", declared_type="boolean", observed_type=observed_type_of(destructive)),
        )
    if confirmation is not None and not isinstance(confirmation, str):
        raise ValidationError(
            "confirmation must be a string",
            details=violation("request_schema", field="confirmation", declared_type="string", observed_type=observed_type_of(confirmation)),
        )
    rows = control_credentials.locked_for_update(work)
    active_ids = [row[0] for row in rows if row[1] and not row[2]]
    phrase = _reset_confirmation_phrase(active_ids)
    if destructive is not True or confirmation != phrase:
        raise DestructiveConfirmationRequired(
            "reset requires the current confirmation phrase",
            details={
                "required_confirmation": phrase,
                "consequence": _RESET_CONSEQUENCE,
                "reversible_alternative": None,
                "recovery": None,
            },
        )
    credential_id = credential_id or ("ctl_" + secrets.token_hex(12))
    secret = secret or _new_secret()
    control_credentials.revoke_all(work=work)
    # Phase 6 WP-3 追補 (brief item A):
    # `.issue()` now returns the COMPOSED bearer as its second element
    # (`credential_id`, unchanged, is its first) -- captured here rather
    # than discarded, so this function's own return value (below) is the
    # composed bearer `ops.py`'s `_print_secret_once` now prints verbatim,
    # not the pre-generated raw `secret` local. Before this fix, the
    # discarded return value meant `reset`'s own CLI/HTTP callers received
    # a raw secret while `bootstrap`'s identical pattern (which already
    # captured `.issue()`'s return) received a composed one -- exactly
    # the "in-band と帯域外の混在" this WP closes.
    # history: CH-0944
    credential_id, bearer = control_credentials.issue(must_rotate=True, credential_id=credential_id, secret=secret, work=work)
    audit_append(
        work=work, event_class="control_credential_lifecycle", request_id=request_id, application_id=None,
        actor_type=actor_type, actor_id=None, role=None, operation="reset_control_credentials",
        target_kind="control_credential", outcome="allow", reason_code=None, target_id=credential_id,
    )
    return credential_id, bearer


def issue_audit_credential_ceremony(
    control_credentials, audit_append, *, work,
    credential_id: Optional[str] = None, request_id: Optional[str] = None,
    actor_type: str = "operator_cli",
) -> tuple[str, str]:
    """Phase 3.5 WP-5 out-of-band audit-credential issuance ceremony (design
    docs/design/PHASE35_CROSS_ENTITY_AND_CONTRACT_130_V1.md §4/§1-D,
    P35-D12/M-1). Same extraction rationale as `bootstrap_control_
    credential`/`reset_control_credentials` above (reusable product code,
    not hand-rolled per caller -- `ops.py cmd_issue_audit_credential` is
    this WP's own only caller today).

    Unlike bootstrap/reset, this ceremony issues AND rotates the credential
    in the SAME transaction, before a secret is ever handed back to the
    caller: an `audit`-role principal has no in-band self-rotate path at all
    (`ControlPlaneService._gate_must_rotate`'s own allow-list for
    `role="audit"` while `must_rotate` is true is `control_capabilities`
    ONLY -- design's own explicit decision not to extend self-rotate to it,
    since the whole point of completing the rotation here is that no
    in-band path should ever need to). Issuing with `must_rotate=true` and
    leaving it to the operator to somehow clear it out-of-band-again would
    be a dead end; this ceremony closes that gap structurally by never
    printing a secret whose `must_rotate` is still true. The intermediate
    `issue()`-time secret is generated, used once to satisfy `issue`'s own
    required `secret` return value, and immediately discarded -- only the
    final, post-`rotate()` secret is ever returned (and therefore ever
    printed by `ops.py`).

    Returns `(credential_id, secret)` -- `secret` is the one that actually
    authenticates (post-rotation); `must_rotate` is `false` for it already.
    """
    credential_id, _issuance_secret = control_credentials.issue(
        must_rotate=True, role="audit", credential_id=credential_id, work=work)
    distributed_secret = control_credentials.rotate(credential_id, work=work)
    audit_append(
        work=work, event_class="control_credential_lifecycle", request_id=request_id, application_id=None,
        actor_type=actor_type, actor_id=None, role=None, operation="issue_audit_credential",
        target_kind="control_credential", outcome="allow", reason_code=None, target_id=credential_id,
    )
    return credential_id, distributed_secret


__all__ = [
    "ControlPlaneLimits",
    "ControlPlaneService",
    "InMemoryApplicationRegistry",
    "InMemoryCredentialRegistry",
    "InMemoryControlBackend",
    "PostgresApplicationRegistry",
    "PostgresCredentialRegistry",
    "PostgresControlBackend",
    "bootstrap_control_credential",
    "reset_control_credentials",
    "issue_audit_credential_ceremony",
    # WP-6 (design v1.2 R-6 identifiers rule): exported so `ops.py`'s own
    # break-glass `deprovision` subcommand validates an operator-supplied
    # application_id against the SAME compiled pattern `register_
    # application`/`issue_credential` already enforce, rather than
    # maintaining a second, possibly-drifting copy of this contract regex.
    "_APPLICATION_ID_PATTERN",
]
