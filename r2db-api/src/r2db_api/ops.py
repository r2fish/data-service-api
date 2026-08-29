"""r2db-api out-of-band control-plane CLI: ``python -m r2db_api.ops``.

R-10 (docs/design/R2DB_CCR14_CONTROL_PLANE_V1.md): the canonical in-band
management surface is `/control/v1` (built in a later work package of this
same phase; not yet wired to any composition root as of this WP). This CLI
is **not** a stand-in for that surface any more -- CCR-14 itself is resolved
(spec/CCR_DISPOSITION.md) -- it now has two distinct, narrower jobs:

1. **The bootstrap/reset ritual.** Issuing the very first control credential
   (`bootstrap`) and revoking-all-and-reissuing (`reset`) are, by design
   (spec/CCR_DISPOSITION.md's "案B"), *only* ever available out-of-band --
   there is no HTTP endpoint anywhere, in this or any future work package,
   that can create a `role=control` credential. This module, run by an
   operator with `R2DB_CONTROL_DSN` (the `r2dbsvc_control` role), is the
   entire issuance surface.
2. **Operator break-glass.** Every subcommand this module already had before
   CCR-14 was resolved (issue/rotate/revoke/disable/enable/delete-credential,
   disable-app/enable-app) remains available: an operator with OS-level
   access to run this CLI, connected as `r2dbsvc_control`, can always recover
   the platform database's state even if the control-plane HTTP surface is
   completely down. `enable-control-credential`/`rotate-control-credential`
   (R-10, added this WP) extend that recovery path to control credentials
   themselves -- the one thing genuinely un-recoverable without this CLI is
   an *un-revoke* of a control credential, which this module deliberately
   never offers (revocation stays terminal; `reset` is the canonical
   recovery from "the only live control credential was revoked").

Every state-changing subcommand below -- both the pre-existing ones and the
new control-credential ones -- now writes a canonical event to
`r2dbsvc_registry.control_audit` in the *same transaction* as the state
change itself (R-6/§8 M-10): the two share one `unit_of_work()`-issued
connection, so a `control_audit` write failure aborts the state change too
(fail-closed by construction, not by convention).

Connects to the platform database as `r2dbsvc_control` (`R2DB_CONTROL_DSN`)
-- the same role `0002`/`0003`/`0004`'s provisioning scripts already run
as, and never the strictly read-only `r2dbsvc_api` role the running API
process itself uses (P2-D3: a compromised API process cannot reach this
role's privileges at all). Application-credential subcommands also require
`R2DB_CREDENTIAL_PEPPER` (the same pepper value the running API process is
configured with) to compute verifiers. Control-credential subcommands
(`bootstrap`/`reset`/`enable-control-credential`/`rotate-control-credential`)
require `R2DB_CONTROL_CREDENTIAL_PEPPER` instead -- a distinct value (R-2):
if both pepper env vars are set in this process' environment and are equal,
every control-credential subcommand refuses to run at all (`credential_
store.validate_control_pepper_separation`).
"""
from __future__ import annotations

import argparse
import os
import secrets
import sys
import uuid
from datetime import datetime, timezone
from typing import Any, NoReturn, Sequence

import psycopg
from psycopg import sql

from .control_plane import bootstrap_control_credential, reset_control_credentials
from .credential_store import (
    DEFAULT_SCHEMA,
    PostgresControlAuditSink,
    PostgresControlCredentialStore,
    PostgresCredentialStore,
    validate_control_pepper_separation,
)
from .errors import FoundationError, fail

_CREDENTIAL_ID_PREFIX = "crd_"
# WP-5 round-2 review NIT-2: the control-credential id prefix ("ctl_") now
# has a single home -- `control_plane._new_control_credential_id()`, used
# by the shared ceremony functions this module calls (`bootstrap_control_
# credential`/`reset_control_credentials`) -- this module no longer mints
# a control credential id itself, so it no longer needs its own copy of
# that prefix constant.
_ACTOR_TYPE = "operator_cli"

# MA-3 (round-2 review): arbitrary, fixed 64-bit `pg_advisory_xact_lock` key
# for the bootstrap/reset ritual only -- see `_lock_ritual` below. Chosen
# once, must never change (changing it would silently stop serializing
# against any already-running process still using the old key -- there is
# no migration path for an advisory lock key, unlike a table/column).
_RITUAL_ADVISORY_LOCK_KEY = 1414141

# The exact column order `_write_control_audit` below inserts, matching
# `0006_control_plane_http.sql`'s `control_audit` table and contract
# `audit.fields`' 12 named fields (`recorded_at` is the table's own
# `DEFAULT now()`, never supplied from here).
_CONTROL_AUDIT_INSERT = (
    "INSERT INTO {table} (event_id, event_class, occurred_at, request_id, application_id, "
    "actor_type, actor_id, role, operation, target_kind, outcome, reason_code) "
    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
)


def _schema() -> str:
    # Not part of the documented environment contract -- added purely so
    # this repository's own tests can point this CLI at a throwaway,
    # textually-prefixed registry schema (the same reason `r2db_api.main`
    # has an identical `R2DB_PLATFORM_SCHEMA` escape hatch; see that
    # module's docstring). A real deployment never sets this.
    return os.environ.get("R2DB_PLATFORM_SCHEMA") or DEFAULT_SCHEMA


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        _die(f"{name} is required")
    return value


def _die(message: str) -> NoReturn:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(2)


def _control_dsn() -> str:
    return _require_env("R2DB_CONTROL_DSN")


def _store() -> PostgresCredentialStore:
    # `R2DB_CONTROL_DSN` -- full DML on this schema, per this module's own
    # docstring -- is what makes `store.add`/`.set_state`/`.rotate` (write
    # operations that would fail with a permission error against the
    # read-only `r2dbsvc_api` role the running API process uses) work here.
    dsn = _control_dsn()
    pepper = _require_env("R2DB_CREDENTIAL_PEPPER")
    return PostgresCredentialStore(dsn, pepper=pepper, schema=_schema())


def _control_store() -> PostgresControlCredentialStore:
    """Constructs the control-credential store for the bootstrap/reset
    ritual and the control-credential break-glass subcommands. R-2's pepper-
    separation check runs here -- "この検査は store 構築側 ... に置く" (design
    §1 R-2) -- against whatever this *process' environment* actually holds
    for both pepper names, independent of whether the specific subcommand
    being run needs the application-plane pepper at all: an operator's
    shell/secret-manager profile realistically configures both env vars
    together, and that is exactly the context this check exists to catch.
    """
    dsn = _control_dsn()
    control_pepper = _require_env("R2DB_CONTROL_CREDENTIAL_PEPPER")
    app_pepper = os.environ.get("R2DB_CREDENTIAL_PEPPER")
    try:
        validate_control_pepper_separation(app_pepper, control_pepper)
    except ValueError as exc:
        _die(str(exc))
    return PostgresControlCredentialStore(dsn, pepper=control_pepper, schema=_schema())


def _control_audit_sink() -> PostgresControlAuditSink:
    """CCR-14 WP-5 (ceremony core extraction, work order §2): the bootstrap/
    reset ritual now writes its canonical audit event through the same
    `PostgresControlAuditSink.append(..., work=...)` call surface
    `ControlPlaneService`/the WP-5 in-process conformance adapter use,
    instead of this module's own hand-rolled `_write_control_audit` SQL --
    `bootstrap_control_credential`/`reset_control_credentials`
    (`control_plane.py`) are the single, shared product-code implementation
    of the ritual now; this module supplies the Postgres stores it needs.
    `pool_size=1` -- this sink's own connection pool is never actually used
    by the ritual's own `append(..., work=...)` call (it executes on the
    caller's already-open `work.connection`, see that method's own
    docstring), so a one-connection pool is enough to satisfy construction
    without holding idle connections a one-shot CLI invocation has no use
    for."""
    return PostgresControlAuditSink(_control_dsn(), schema=_schema(), pool_size=1)


def _new_credential_id() -> str:
    return _CREDENTIAL_ID_PREFIX + secrets.token_hex(8)


def _new_secret() -> str:
    return secrets.token_urlsafe(32)


def _print_issued(credential_id: str, secret: str) -> None:
    # The secret is shown exactly once, here, and is never written anywhere
    # by this process (P2-D1: only its verifier is ever persisted) -- copy
    # it now, it cannot be recovered later.
    print(f"credential_id: {credential_id}")
    print(f"secret: {secret}")
    print("(the secret above is shown once and is not stored anywhere -- save it now)")


def _write_control_audit(
    conn: "psycopg.Connection[Any]",
    *,
    event_class: str,
    operation: str,
    outcome: str,
    target_kind: str | None = None,
    application_id: str | None = None,
    role: str | None = None,
    reason_code: str | None = None,
) -> None:
    """Writes one canonical `control_audit` row on `conn` -- the exact same
    connection/transaction the caller's state change just executed on
    (R-6/§8 M-10). Never commits/rolls back itself: the enclosing `unit_of_
    work()` context manager (opened by the caller) owns that. `actor_type`
    is the constant `"operator_cli"` and `actor_id` is always `None` (this
    module's docstring: an out-of-band operation running under OS-level
    access, not attributable to any credential -- there is no credential
    that authenticated this process at all).

    MI-3 (round-2 review, deliberate boundary recorded here): every call
    site below passes `outcome="allow"` -- this CLI only ever durably
    records *successful* state changes, never denials/failures. A refused
    or errored CLI invocation is reported to the operator on stderr and
    `main()`'s non-zero exit code (both already operator-visible, by
    design -- this is an interactive/scripted OS-level tool, not a public
    HTTP surface an attacker could probe blindly). Durably recording
    *denial* events (authentication failures, authorization refusals,
    capability rejections) is the design's R-6/§8 B-3 obligation for the
    control-plane **HTTP** surface specifically (`ControlPlaneService`,
    WP-3) -- that surface faces untrusted network callers who could
    otherwise probe it for free with no durable trace at all, which is not
    a risk this CLI carries (it requires OS-level access and a real
    `R2DB_CONTROL_DSN`/pepper already).
    """
    statement = sql.SQL(_CONTROL_AUDIT_INSERT).format(table=sql.Identifier(_schema(), "control_audit"))
    with conn.cursor() as cur:
        cur.execute(
            statement,
            [
                str(uuid.uuid4()),
                event_class,
                datetime.now(timezone.utc),
                str(uuid.uuid4()),
                application_id,
                _ACTOR_TYPE,
                None,
                role,
                operation,
                target_kind,
                outcome,
                reason_code,
            ],
        )


def _lock_ritual(conn: "psycopg.Connection[Any]") -> None:
    """MA-3 (round-2 review): serializes concurrent `bootstrap`/`reset`
    ritual invocations against the same platform database, closing the
    TOCTOU gap between `has_any()`'s existence check and the subsequent
    `add`/`revoke_all` -- without this, two concurrent `bootstrap` calls
    could both observe "no row yet" before either commits, and both then
    issue a control credential. `pg_advisory_xact_lock` is transaction-
    scoped: called here on `work.connection`, *before* the existence check,
    so the check itself runs inside the locked section; the lock releases
    automatically when that transaction commits or rolls back (never held
    past one `bootstrap`/`reset` invocation, never leaked across calls).
    `reset` takes the same lock (same key) for the same reason, which also
    serializes `reset` against a concurrent `bootstrap` -- the two must
    never interleave on the same platform database.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT pg_advisory_xact_lock(%s)", [_RITUAL_ADVISORY_LOCK_KEY])


# ---------------------------------------------------------------------------
# Application-credential subcommands (pre-existing; now audited -- §8 M-10).
# ---------------------------------------------------------------------------


def cmd_issue_credential(args: argparse.Namespace) -> int:
    store = _store()
    try:
        credential_id = _new_credential_id()
        secret = _new_secret()
        with store.unit_of_work() as work:
            store.add(credential_id, args.slug, args.role, secret, work=work)
            _write_control_audit(
                work.connection,
                event_class="credential_lifecycle",
                operation="issue_credential",
                outcome="allow",
                target_kind="credential",
                application_id=args.slug,
                role=args.role,
            )
    finally:
        store.close()
    _print_issued(credential_id, secret)
    return 0


def cmd_rotate_credential(args: argparse.Namespace) -> int:
    # P2-D6: "同一 credential_id の verifier を差し替える" -- the id, role,
    # and application scope are unchanged; only the secret (and therefore
    # the stored verifier) is replaced, so the old secret stops
    # authenticating the moment this commits.
    store = _store()
    try:
        secret = _new_secret()
        with store.unit_of_work() as work:
            store.rotate(args.credential_id, secret, work=work)
            _write_control_audit(
                work.connection,
                event_class="credential_lifecycle",
                operation="rotate_credential",
                outcome="allow",
                target_kind="credential",
            )
    finally:
        store.close()
    _print_issued(args.credential_id, secret)
    return 0


def cmd_revoke_credential(args: argparse.Namespace) -> int:
    store = _store()
    try:
        with store.unit_of_work() as work:
            store.set_state(args.credential_id, revoked=True, work=work)
            _write_control_audit(
                work.connection,
                event_class="credential_lifecycle",
                operation="revoke_credential",
                outcome="allow",
                target_kind="credential",
            )
    finally:
        store.close()
    print(f"credential {args.credential_id} revoked")
    return 0


def cmd_disable_credential(args: argparse.Namespace) -> int:
    store = _store()
    try:
        with store.unit_of_work() as work:
            store.set_state(args.credential_id, enabled=False, work=work)
            _write_control_audit(
                work.connection,
                event_class="credential_lifecycle",
                operation="disable_credential",
                outcome="allow",
                target_kind="credential",
            )
    finally:
        store.close()
    print(f"credential {args.credential_id} disabled")
    return 0


def cmd_delete_credential(args: argparse.Namespace) -> int:
    # Genuinely destructive and irreversible -- unlike revoke/disable
    # (soft state changes on a row that stays on record), this removes the
    # row outright. Exists specifically to satisfy `0004_deprovision_
    # application.sql`'s `assert_no_credentials_for_deprovision` guard: an
    # application can never be deprovisioned while a credential row
    # (revoked or not) still references it, since that reference is a real
    # foreign key (`ON DELETE RESTRICT`), and revoking alone does not clear
    # a foreign key. The recommended sequence is revoke, confirm nothing is
    # relying on it, then delete -- this command performs only the second
    # half.
    store = _store()
    try:
        with store.unit_of_work() as work:
            store.delete(args.credential_id, work=work)
            _write_control_audit(
                work.connection,
                event_class="credential_lifecycle",
                operation="delete_credential",
                outcome="allow",
                target_kind="credential",
            )
    finally:
        store.close()
    print(f"credential {args.credential_id} deleted")
    return 0


def cmd_enable_credential(args: argparse.Namespace) -> int:
    store = _store()
    try:
        with store.unit_of_work() as work:
            store.set_state(args.credential_id, enabled=True, work=work)
            _write_control_audit(
                work.connection,
                event_class="credential_lifecycle",
                operation="enable_credential",
                outcome="allow",
                target_kind="credential",
            )
    finally:
        store.close()
    print(f"credential {args.credential_id} enabled")
    return 0


def cmd_list_credentials(_args: argparse.Namespace) -> int:
    dsn = _control_dsn()
    # Never selects `verifier` -- this command must not be able to leak the
    # one secret-derived value the platform database stores, even to an
    # operator who only asked to list credentials (P2-D1's own "verifier
    # only, never the secret" boundary extends to this listing too). A
    # read-only listing writes no audit event (§8 M-10: "list 系（読み取り）
    # は監査不要").
    statement = sql.SQL(
        "SELECT credential_id, application_slug, role, enabled, revoked, created_at FROM {table} ORDER BY created_at"
    ).format(table=sql.Identifier(_schema(), "credentials"))
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(statement)
            rows = cur.fetchall()
    print(f"{'credential_id':<24}{'application_slug':<24}{'role':<12}{'enabled':<9}{'revoked':<9}created_at")
    for credential_id, slug, role, enabled, revoked, created_at in rows:
        print(f"{credential_id:<24}{slug:<24}{role:<12}{str(enabled):<9}{str(revoked):<9}{created_at}")
    return 0


def _set_application_enabled(slug: str, enabled: bool) -> None:
    dsn = _control_dsn()
    statement = sql.SQL("UPDATE {table} SET enabled = {enabled_ph} WHERE application_slug = {slug_ph} RETURNING application_slug").format(
        table=sql.Identifier(_schema(), "applications"), enabled_ph=sql.Placeholder(), slug_ph=sql.Placeholder()
    )
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(statement, [enabled, slug])
            row = cur.fetchone()
        if row is None:
            conn.rollback()
            _die(f"application {slug!r} is not registered")
        _write_control_audit(
            conn,
            event_class="application_lifecycle",
            operation="enable_application" if enabled else "disable_application",
            outcome="allow",
            target_kind="application",
            application_id=slug,
        )
        conn.commit()


def cmd_disable_app(args: argparse.Namespace) -> int:
    _set_application_enabled(args.slug, False)
    print(f"application {args.slug} disabled")
    return 0


def cmd_enable_app(args: argparse.Namespace) -> int:
    _set_application_enabled(args.slug, True)
    print(f"application {args.slug} enabled")
    return 0


def cmd_list_apps(_args: argparse.Namespace) -> int:
    dsn = _control_dsn()
    statement = sql.SQL("SELECT application_slug, enabled, database_name, provisioned_at FROM {table} ORDER BY application_slug").format(
        table=sql.Identifier(_schema(), "applications")
    )
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(statement)
            rows = cur.fetchall()
    print(f"{'application_slug':<24}{'enabled':<9}{'database_name':<32}provisioned_at")
    for slug, enabled, database_name, provisioned_at in rows:
        print(f"{slug:<24}{str(enabled):<9}{(database_name or ''):<32}{provisioned_at if provisioned_at is not None else '(not provisioned)'}")
    return 0


# ---------------------------------------------------------------------------
# Control-credential ritual (bootstrap/reset -- R-5) and break-glass (R-10).
# ---------------------------------------------------------------------------


def cmd_bootstrap(_args: argparse.Namespace) -> int:
    """Issues the very first control credential. Refuses if *any*
    `control_credentials` row already exists -- including an entirely
    revoked one (§8 M-6: the contract's own "while a control credential
    exists" reads as row-existence, not "at least one is currently live";
    reading it the other way would open a second issuance path once every
    row happened to be revoked, defeating "issuance is bootstrap/reset
    only"). Recovery from that state is always `reset`, never a second
    `bootstrap` -- the error message below says so explicitly.

    MA-3 (round-2 review): the existence check and the issuance now run
    *inside the same* `unit_of_work()`, on `work.connection`, guarded by
    `_lock_ritual` -- closing the TOCTOU gap round 1 of this WP had (a
    standalone `has_any()` call, then a *separate* transaction for the
    `add`, with nothing serializing two concurrent `bootstrap` invocations
    against each other in between).

    CCR-14 WP-5 (§2, ceremony core extraction): the existence check, the
    issuance, and the canonical audit write are no longer hand-rolled here
    -- `bootstrap_control_credential` (`control_plane.py`) is the same
    reusable product-code ceremony the WP-5 in-process conformance adapter
    calls against its own in-memory store. This CLI's job, unchanged, is
    supplying the Postgres store/audit sink and the advisory lock
    (Postgres-only serialization, never part of the shared ceremony
    function itself); external behaviour, audit row shape, and exit codes
    are unchanged (evidenced by this file's own pre-existing green tests).
    """
    store = _control_store()
    audit = _control_audit_sink()
    try:
        with store.unit_of_work() as work:
            _lock_ritual(work.connection)
            credential_id, secret = bootstrap_control_credential(store, audit, work=work)
    finally:
        store.close()
        audit.close()
    _print_issued(credential_id, secret)
    print("must_rotate: true -- this credential must be rotated before it can do anything besides GET /control/v1/capabilities and rotate itself")
    return 0


def cmd_reset(_args: argparse.Namespace) -> int:
    """Revokes every existing control credential and issues one new one,
    atomically (R-5/design §7 "reset の原子性"): both the revoke-all and the
    new `add` run inside the same `unit_of_work()`, so there is never a
    moment where the old credentials are revoked but no new one exists yet,
    or vice versa -- a crash/fault between the two never happens because
    there is no "between": either both apply, in one transaction, or
    neither does. Touches nothing in `applications`/`credentials`/
    `control_audit` beyond the one canonical event this writes.

    MA-3 (round-2 review): takes the same `_lock_ritual` advisory lock as
    `bootstrap` (same key) -- serializing `reset` against a concurrent
    `bootstrap` (or another concurrent `reset`) on the same platform
    database, so the two rituals can never interleave.

    CCR-14 WP-5 (§2, ceremony core extraction): see `cmd_bootstrap`'s
    identical note -- `reset_control_credentials` (`control_plane.py`) is
    the shared product-code ceremony; this CLI supplies the Postgres store/
    audit sink and the advisory lock.
    """
    store = _control_store()
    audit = _control_audit_sink()
    try:
        with store.unit_of_work() as work:
            _lock_ritual(work.connection)
            credential_id, secret = reset_control_credentials(store, audit, work=work)
    finally:
        store.close()
        audit.close()
    _print_issued(credential_id, secret)
    print("must_rotate: true -- this credential must be rotated before it can do anything besides GET /control/v1/capabilities and rotate itself")
    return 0


def cmd_enable_control_credential(args: argparse.Namespace) -> int:
    """R-10 break-glass: recovers from the one lockout `reset` is heavier
    than necessary for -- the sole live control credential having been
    disabled (not revoked). Un-revoke is never offered here (`set_state`
    refuses it, matching `enable-credential`'s existing un-revoke
    refusal) -- revocation stays terminal; `reset` is the only recovery
    once a control credential is revoked.
    """
    store = _control_store()
    try:
        with store.unit_of_work() as work:
            store.set_state(args.credential_id, enabled=True, work=work)
            _write_control_audit(
                work.connection,
                event_class="control_credential_lifecycle",
                operation="enable_control_credential",
                outcome="allow",
                target_kind="control_credential",
            )
    finally:
        store.close()
    print(f"control credential {args.credential_id} enabled")
    return 0


def cmd_rotate_control_credential(args: argparse.Namespace) -> int:
    """R-10 break-glass: recovers from a lost/leaked control-credential
    secret without disturbing `credential_id` (audit continuity -- every
    prior `control_audit` row naming this id via a future `/control/v1`
    endpoint's `actor_id` still refers to the same, still-live credential).
    Sets `must_rotate = false` (R-5: "rotate 成功で must_rotate=false" --
    the same rule the in-band self-rotate endpoint will apply, WP-3),
    matching `credential_store.PostgresControlCredentialStore.rotate`'s own
    revoked-refusal (`VALIDATION_FAILED`) -- this break-glass command does
    not bypass that: a revoked control credential cannot be rotated back to
    life by any path, CLI included.
    """
    store = _control_store()
    try:
        secret = _new_secret()
        with store.unit_of_work() as work:
            store.rotate(args.credential_id, secret, work=work)
            _write_control_audit(
                work.connection,
                event_class="control_credential_lifecycle",
                operation="rotate_control_credential",
                outcome="allow",
                target_kind="control_credential",
            )
    finally:
        store.close()
    _print_issued(args.credential_id, secret)
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m r2db_api.ops",
        description=(
            "r2db-api out-of-band control-plane CLI (CCR-14 R-10) -- the "
            "bootstrap/reset control-credential ritual (no other issuance "
            "path exists) plus operator break-glass for when the canonical "
            "in-band surface, /control/v1, is unreachable. Normal, day-to-"
            "day application/credential management should use /control/v1 "
            "once it is deployed; this CLI remains the only way to bootstrap "
            "it in the first place."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("issue-credential", help="issue a new credential for an application (secret printed once)")
    p.add_argument("slug", help="application slug")
    p.add_argument("role", choices=["runtime", "developer"])
    p.set_defaults(func=cmd_issue_credential)

    p = sub.add_parser("rotate-credential", help="replace an existing credential's secret (new secret printed once)")
    p.add_argument("credential_id")
    p.set_defaults(func=cmd_rotate_credential)

    p = sub.add_parser("revoke-credential", help="permanently revoke a credential")
    p.add_argument("credential_id")
    p.set_defaults(func=cmd_revoke_credential)

    p = sub.add_parser("disable-credential", help="temporarily disable a credential")
    p.add_argument("credential_id")
    p.set_defaults(func=cmd_disable_credential)

    p = sub.add_parser("enable-credential", help="re-enable a previously disabled credential")
    p.add_argument("credential_id")
    p.set_defaults(func=cmd_enable_credential)

    p = sub.add_parser(
        "delete-credential",
        help="PERMANENTLY delete a credential row (irreversible; refused unless the credential is already revoked -- revoke first. Needed to clear the deprovisioning guard's foreign key)",
    )
    p.add_argument("credential_id")
    p.set_defaults(func=cmd_delete_credential)

    p = sub.add_parser("list-credentials", help="list credentials (never prints verifier/secret)")
    p.set_defaults(func=cmd_list_credentials)

    p = sub.add_parser("disable-app", help="disable an application -- every one of its credentials is refused (APPLICATION_DISABLED)")
    p.add_argument("slug")
    p.set_defaults(func=cmd_disable_app)

    p = sub.add_parser("enable-app", help="re-enable a previously disabled application")
    p.add_argument("slug")
    p.set_defaults(func=cmd_enable_app)

    p = sub.add_parser("list-apps", help="list registered applications")
    p.set_defaults(func=cmd_list_apps)

    p = sub.add_parser(
        "bootstrap",
        help="issue the very first control credential (refused if any control credential row already exists, including revoked ones -- use `reset` to recover)",
    )
    p.set_defaults(func=cmd_bootstrap)

    p = sub.add_parser(
        "reset",
        help="revoke every existing control credential and issue one new one, atomically -- the canonical recovery from a lost/leaked/lockout control credential",
    )
    p.set_defaults(func=cmd_reset)

    p = sub.add_parser(
        "enable-control-credential",
        help="break-glass: re-enable a disabled (not revoked) control credential",
    )
    p.add_argument("credential_id")
    p.set_defaults(func=cmd_enable_control_credential)

    p = sub.add_parser(
        "rotate-control-credential",
        help="break-glass: replace a control credential's secret in place (same credential_id; new secret printed once)",
    )
    p.add_argument("credential_id")
    p.set_defaults(func=cmd_rotate_control_credential)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except FoundationError as exc:
        print(f"error: {exc.code}: {exc.message}", file=sys.stderr)
        return 1
    except psycopg.Error as exc:
        print(f"error: database operation failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
