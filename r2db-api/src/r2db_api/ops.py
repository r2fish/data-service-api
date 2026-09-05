"""r2db-api out-of-band control-plane CLI: ``python -m r2db_api.ops``.

R-10 (docs/design/R2DB_CCR14_CONTROL_PLANE_V1.md): the canonical in-band
management surface is `/control/v1` (`control_http.create_control_app`,
assembled by `r2db_api.control_main`, WP-4/WP-5 of this same phase -- built
and, as of WP-5's single-commit declaration flip, reachable wherever a
deployment runs `control_main` alongside this process and declares
`R2DB_CONTROL_PLANE_STATUS=enabled`, deploy/DEPLOYMENT_RUNBOOK.md). This CLI
is **not** a stand-in for that surface -- CCR-14 itself is resolved
(spec/CCR_DISPOSITION.md) -- it now has two distinct, narrower jobs (plus one
read-only diagnostic helper, R-11, documented separately below):

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

Beyond those two jobs, `audit-report` (added this WP) is a third, read-only
capability: a compromise/misuse investigation helper (R-11) that lists
durable `control_audit` events in a time window as JSON Lines -- see
`cmd_audit_report`'s own docstring and `r2db-api/docs/CONTROL_PLANE_
COMPROMISE_PLAYBOOK.md` for the recovery sequence it supports.

Q-1 WP-4 (docs/design/DESTRUCTIVE_CONFIRMATION_V1.md R-4): `reset` and
`delete-credential` -- the two genuinely destructive subcommands this
module offers (Q1-D4/WP-0 MA-1 excludes `revoke-credential`, which targets
application credentials, the same class of operation Q1-D1 already leaves
unconfirmed everywhere in this contract) -- now require a `--confirm
<phrase>` flag, following the same declare-and-echo protocol the wire
surfaces already implement (`structured.require_destructive_confirmation`/
`control_plane.py`'s revoke gate): an omitted or mismatched `--confirm`
executes nothing, prints the operation's own declaration (the confirmation
phrase to echo, plus consequence/reversible_alternative/recovery) as one
line of JSON to stderr, and exits 2; the exact same phrase echoed back on a
second invocation proceeds normally. See `_require_cli_confirmation`'s own
docstring for the mechanics and `POSTGRES_PROVISIONING_RUNBOOK.md` §12/§13
and `CONTROL_PLANE_COMPROMISE_PLAYBOOK.md` step 1 for the operator-facing
walkthrough of `reset`'s own two-step shape under this gate.

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
import json
import os
import re
import secrets
import sys
import uuid
from datetime import datetime, timezone
from typing import Any, NoReturn, Sequence

import psycopg
from psycopg import sql
from psycopg.types.json import Json

from . import platform_declarations
from .control_plane import bootstrap_control_credential, issue_audit_credential_ceremony, reset_control_credentials
from .credential_store import (
    DEFAULT_SCHEMA,
    PostgresApplicationRegistry,
    PostgresControlAuditSink,
    PostgresControlCredentialStore,
    PostgresCredentialStore,
    validate_control_pepper_separation,
)
from .errors import FoundationError, fail
from .platform_declarations import (
    MIGRATION_NUMBER,
    PEER_MODULE,
    PlatformDeclarationError,
    read_declared_role_timeouts,
    validate_audit_writer_roles_value,
    validate_coalescing_window_value,
    validate_surfaces_value,
)
from .structured import RESET_CONTROL_CREDENTIALS, delete_credential_confirmation_phrase

_CREDENTIAL_ID_PREFIX = "crd_"
# WP-5 round-2 review NIT-2: the control-credential id prefix ("ctl_") now
# has a single home -- `control_plane._new_control_credential_id()`, used
# by the shared ceremony functions this module calls (`bootstrap_control_
# credential`/`reset_control_credentials`) -- this module no longer mints
# a control credential id itself, so it no longer needs its own copy of
# that prefix constant.
_ACTOR_TYPE = "operator_cli"

# Q-1 WP-4 followup (Opus review MA-1): the exact shape both of this
# codebase's application-credential minters produce -- this module's own
# `_new_credential_id` (`issue-credential`) and the in-band `control_plane.
# _new_credential_id` (`POST /control/v1/credentials`), `_CREDENTIAL_ID_
# PREFIX` + `secrets.token_hex(8)` in both cases. `cmd_delete_credential`
# validates its own `credential_id` argument against this pattern *before*
# the confirmation gate (see that function's own comment) -- a plain,
# no-DB-access string check that rejects an unrecognized shape as
# `VALIDATION_FAILED` via the ordinary `fail()`/`main()` error path, never
# reaching `delete_credential_confirmation_phrase` with unvalidated input.
# This is the CLI's own equivalent of `validate_identifier` gating every
# data-plane phrase-construction call (`structured.py`'s own header
# comment, rule (c): a phrase never reflects unvalidated client input back
# to the client) and closes rule (d) (bounded length) the same way: a
# format-validated id is always exactly 20 characters, so no digest escape
# hatch is needed for this phrase the way `delete`/`drop_entity`/
# `drop_index` need one for a contract-unbounded identifier.
_APPLICATION_CREDENTIAL_ID_PATTERN = re.compile(r"^crd_[0-9a-f]{16}$")

# MA-3 (round-2 review): arbitrary, fixed 64-bit `pg_advisory_xact_lock` key
# for the bootstrap/reset ritual only -- see `_lock_ritual` below. Chosen
# once, must never change (changing it would silently stop serializing
# against any already-running process still using the old key -- there is
# no migration path for an advisory lock key, unlike a table/column).
_RITUAL_ADVISORY_LOCK_KEY = 1414141

# The exact column order `_write_control_audit` below inserts, matching
# `0006_control_plane_http.sql`'s `control_audit` table and contract
# `audit.fields` (`recorded_at` is the table's own `DEFAULT now()`, never
# supplied from here).
#
# Phase 3.5 WP-4 (design PHASE35_CROSS_ENTITY_AND_CONTRACT_130_V1.md §1-C/
# §4): `target_id` -- the contract's 13th, optional `audit.fields` member --
# appended last, matching `credential_store.py`'s own `_CONTROL_AUDIT_
# COLUMNS`/`_CONTROL_AUDIT_INSERT` ordering.
_CONTROL_AUDIT_INSERT = (
    "INSERT INTO {table} (event_id, event_class, occurred_at, request_id, application_id, "
    "actor_type, actor_id, role, operation, target_kind, outcome, reason_code, target_id) "
    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
)

# R-11 (`audit-report`, added this WP): the exact column order the report's
# SELECT reads and the JSON Lines output writes -- `_CONTROL_AUDIT_INSERT`'s
# own column list, above, plus `recorded_at` (0006's DB-side insertion
# timestamp, distinct from the application-side `occurred_at` this report
# filters on -- see `cmd_audit_report`'s own docstring).
_CONTROL_AUDIT_REPORT_COLUMNS = (
    "event_id", "event_class", "occurred_at", "request_id", "application_id",
    "actor_type", "actor_id", "role", "operation", "target_kind", "outcome", "reason_code",
    "target_id", "recorded_at",
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


def _applications() -> PostgresApplicationRegistry:
    """Phase 3.5 WP-4 (§4/§1-E, P35-D6): the applications-registry store for
    `freeze-issuance`/`unfreeze-issuance`. Connects with `R2DB_CONTROL_DSN`
    (`r2dbsvc_control`), same as every other write-path store this module
    constructs -- never the control-plane HTTP process' own `r2dbsvc_
    controlplane` role."""
    return PostgresApplicationRegistry(_control_dsn(), schema=_schema())


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
    #
    # Phase 6 WP-2 (design D-1(c)), corrected 2026-09-04 (coordinator
    # follow-up, audit finding §3-A): every caller now passes an ALREADY-
    # COMPOSED bearer here -- `cmd_bootstrap`/`cmd_reset`/`cmd_issue_audit_
    # credential` get one straight from `control_plane.py`'s own ceremony
    # functions (their own issuance point), and `cmd_issue_credential`/
    # `cmd_rotate_credential`/`cmd_rotate_control_credential` (which call
    # `store.add`/`.rotate` directly, bypassing those ceremonies) get one
    # from THAT call's own return value -- `add`/`rotate` are themselves
    # issuance points now (design D-1(c) "合成は store/service 層のみ"),
    # so this module composes nothing anywhere, at any call site. This
    # function itself never composes -- it would double-compose an
    # already-composed value otherwise.
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
    target_id: str | None = None,
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
                target_id,
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
# CLI declare-and-echo gate (Q-1 WP-4, docs/design/DESTRUCTIVE_CONFIRMATION_
# V1.md R-4) -- `reset` and `delete-credential` only (Q1-D4/WP-0 MA-1: this
# CLI's `revoke-credential` targets application credentials, exactly the
# operation class Q1-D1 already leaves unconfirmed -- gating it here would
# put friction on playbook step 3's own bulk-revoke incident-response flow
# for no contract-required reason). Every other subcommand's external
# behaviour is unchanged by this WP.
# ---------------------------------------------------------------------------

_RESET_CONSEQUENCE = (
    "Every existing control credential is revoked and exactly one new, "
    "must_rotate credential is issued in the same transaction; the in-band "
    "control-plane surface (/control/v1) is then usable for nothing beyond "
    "GET .../capabilities and self-rotate until that new credential "
    "completes its first rotation (POSTGRES_PROVISIONING_RUNBOOK.md §12)."
)
_RESET_REVERSIBLE_ALTERNATIVE = (
    "If the specific problem is only a disabled (not revoked) control "
    "credential, or only an uncaptured secret for one that is still "
    "enabled and not revoked, `enable-control-credential <credential_id>` "
    "or `rotate-control-credential <credential_id>` respectively recovers "
    "without revoking anything at all -- narrower than reset, but only "
    "available when credential_id is known and that credential is not "
    "already revoked (POSTGRES_PROVISIONING_RUNBOOK.md §13). Once a "
    "control credential is actually revoked, or none is known/trusted, "
    "reset is the only recovery."
)
_RESET_RECOVERY = (
    "Reset itself remains available if access is lost again for any "
    "reason -- it needs no prior credential to run and is the universal "
    "fallback for every one of §13's lockout paths. It is not meant "
    "to be re-run routinely after a prior invocation already reported "
    "success (CONTROL_PLANE_COMPROMISE_PLAYBOOK.md step 1: run once per "
    "incident, not on every retry)."
)

_DELETE_CREDENTIAL_CONSEQUENCE = (
    "The credential row, if it exists, is permanently removed; unlike "
    "revoke, no row remains afterward at all -- it disappears from "
    "list-credentials and there is nothing left to inspect or re-enable by "
    "this credential_id. (Whether it exists at all is not yet checked at "
    "the point this declaration is made -- the confirmation gate runs "
    "before that -- so this is phrased conditionally rather than asserting "
    "a row that may not be there.)"
)
_DELETE_CREDENTIAL_REVERSIBLE_ALTERNATIVE = (
    "revoke-credential <credential_id> -- terminal (no un-revoke) but the "
    "row itself stays on record and remains listable; it does not, "
    "however, clear 0005_credential_store.sql's own `credentials."
    "application_slug` foreign key (`ON DELETE RESTRICT`), which "
    "0004_deprovision_application.sql's script detects and refuses "
    "against and which only removing the row (not merely revoking it) "
    "satisfies."
)
_DELETE_CREDENTIAL_RECOVERY = None


def _require_cli_confirmation(
    confirm: str | None,
    *,
    phrase: str,
    message: str,
    consequence: str,
    reversible_alternative: str | None,
    recovery: str | None,
) -> None:
    """Contract 1.2.0 `destructive_confirmation`'s exact-match rule
    (`structured.require_destructive_confirmation`'s own HTTP-facing
    counterpart), applied to this CLI's own `--confirm <phrase>` flag: a
    valid confirmation is `confirm == phrase` as an exact string (no
    presence/truthy/prefix check) -- there is no separate `destructive`
    boolean here, since invoking `reset`/`delete-credential` at all already
    *is* the destructive intent signal a wire request's own `destructive:
    true` field stands in for.

    Checked FIRST, before any store/audit-sink construction, in both
    callers below: both phrases (`RESET_CONTROL_CREDENTIALS`, a constant;
    `DELETE_CREDENTIAL <credential_id>`, a pure function of the CLI's own
    argument) are fully computable with no database read at all, so a
    rejected confirmation leaves the platform database completely
    untouched -- not even a connection is opened -- satisfying the same
    "denial reads/writes nothing" guarantee the wire surfaces get from
    their own evaluation order (contract `destructive_confirmation.
    evaluation_order`), even though the CLI has no separate shape/auth/
    target-existence steps of its own to interleave this after.

    On denial: prints one line of problem+json-shaped JSON (`FoundationError.
    problem()`'s own shape: type/code/message/request_id/details) to
    stderr and exits 2 -- deliberately NOT routed through `main()`'s
    ordinary `FoundationError` handling (`f"error: {code}: {message}"` text,
    exit 1): this predates any store/audit construction, so there is
    nothing transactional to unwind, and R-4's own contract for this CLI is
    exit code 2 + JSON-on-stderr specifically, distinguishable at a glance
    from every other CLI failure mode (argparse usage errors; a
    `FoundationError` the ceremony/store itself raises after this gate
    passes; a raw `psycopg.Error`).

    Writes no `control_audit` event either way: a rejection changes no
    state at all (this module's own pre-existing convention, `_write_
    control_audit`'s MI-3 note -- only successful state changes are
    durably recorded by this CLI).
    """
    if confirm != phrase:
        error = FoundationError(
            "DESTRUCTIVE_CONFIRMATION_REQUIRED",
            message,
            details={
                "required_confirmation": phrase,
                "consequence": consequence,
                "reversible_alternative": reversible_alternative,
                "recovery": recovery,
            },
            status=409,
        )
        print(json.dumps(error.problem(), sort_keys=False), file=sys.stderr)
        raise SystemExit(2)


# ---------------------------------------------------------------------------
# Application-credential subcommands (pre-existing; now audited -- §8 M-10).
# ---------------------------------------------------------------------------


def cmd_issue_credential(args: argparse.Namespace) -> int:
    store = _store()
    try:
        credential_id = _new_credential_id()
        secret = _new_secret()
        with store.unit_of_work() as work:
            # Coordinator item 3 (2026-09-04 review): `store.add` is now
            # this CLI's own issuance point -- it returns the composed
            # bearer directly (design D-1(c) "合成は store/service 層の
            # み"), so this call site no longer composes it itself (see
            # `_print_issued`'s own docstring: every caller now passes an
            # already-composed value straight through).
            bearer = store.add(credential_id, args.slug, args.role, secret, work=work)
            _write_control_audit(
                work.connection,
                event_class="credential_lifecycle",
                operation="issue_credential",
                outcome="allow",
                target_kind="credential",
                application_id=args.slug,
                role=args.role,
                target_id=credential_id,
            )
    finally:
        store.close()
    _print_issued(credential_id, bearer)
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
            # Coordinator follow-up (2026-09-04 audit finding §3-A):
            # `store.rotate` is now this CLI's own re-issuance point -- it
            # returns the composed bearer directly (same discipline as
            # `store.add` in `cmd_issue_credential` above), so this call
            # site no longer composes it itself.
            bearer = store.rotate(args.credential_id, secret, work=work)
            _write_control_audit(
                work.connection,
                event_class="credential_lifecycle",
                operation="rotate_credential",
                outcome="allow",
                target_kind="credential",
                target_id=args.credential_id,
            )
    finally:
        store.close()
    _print_issued(args.credential_id, bearer)
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
                target_id=args.credential_id,
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
                target_id=args.credential_id,
            )
    finally:
        store.close()
    print(f"credential {args.credential_id} disabled")
    return 0


def cmd_delete_credential(args: argparse.Namespace) -> int:
    # Genuinely destructive and irreversible -- unlike revoke/disable
    # (soft state changes on a row that stays on record), this removes the
    # row outright. Exists specifically to satisfy `0005_credential_store.
    # sql`'s own `credentials.application_slug` foreign key (`ON DELETE
    # RESTRICT`) -- the guard `0004_deprovision_application.sql`'s script
    # detects and refuses against (`assert_no_credentials_for_deprovision`):
    # an application can never be deprovisioned while a credential row
    # (revoked or not) still references it, and revoking alone does not
    # clear that foreign key. The recommended sequence is revoke, confirm
    # nothing is relying on it, then delete -- this command performs only
    # the second half.
    #
    # Q-1 WP-4 followup (Opus review MA-1): `credential_id` is validated
    # against `_APPLICATION_CREDENTIAL_ID_PATTERN` *before* the confirmation
    # gate below, and before any database access -- an unrecognized shape is
    # `VALIDATION_FAILED` via the ordinary `fail()`/`main()` error path (see
    # that constant's own comment for why), never reaching `delete_
    # credential_confirmation_phrase` with unvalidated input.
    if not _APPLICATION_CREDENTIAL_ID_PATTERN.fullmatch(args.credential_id):
        fail("VALIDATION_FAILED", f"credential_id must match {_APPLICATION_CREDENTIAL_ID_PATTERN.pattern!r}.")
    #
    # Q-1 WP-4 (design R-4): gated by `--confirm DELETE_CREDENTIAL
    # <credential_id>` -- checked before `_store()` is even constructed (see
    # `_require_cli_confirmation`'s own docstring), so an omitted/mismatched
    # `--confirm` never touches the database at all, regardless of whether
    # this credential_id exists or is already revoked (both are the *next*
    # thing checked, inside `store.delete` itself, only once this gate has
    # already passed).
    _require_cli_confirmation(
        args.confirm,
        phrase=delete_credential_confirmation_phrase(args.credential_id),
        message="Confirmation required to permanently delete this credential row.",
        consequence=_DELETE_CREDENTIAL_CONSEQUENCE,
        reversible_alternative=_DELETE_CREDENTIAL_REVERSIBLE_ALTERNATIVE,
        recovery=_DELETE_CREDENTIAL_RECOVERY,
    )
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
                target_id=args.credential_id,
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
                target_id=args.credential_id,
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
            target_id=slug,
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


def _set_application_issuance_frozen(slug: str, frozen: bool) -> None:
    """Phase 3.5 WP-4 (design §4/§1-E, P35-D6): CLI-only, non-destructive --
    same class as `_set_application_enabled` above (no declare-and-echo
    confirmation gate; unlike `reset`/`delete-credential`, freezing/
    unfreezing issuance is fully reversible with no data loss)."""
    store = _applications()
    try:
        with store.unit_of_work() as work:
            store.set_issuance_frozen(slug, frozen, work=work)
            _write_control_audit(
                work.connection,
                event_class="application_lifecycle",
                operation="freeze_issuance" if frozen else "unfreeze_issuance",
                outcome="allow",
                target_kind="application",
                application_id=slug,
                target_id=slug,
            )
    finally:
        store.close()


def cmd_freeze_issuance(args: argparse.Namespace) -> int:
    _set_application_issuance_frozen(args.slug, True)
    print(f"credential issuance for application {args.slug} is now frozen")
    return 0


def cmd_unfreeze_issuance(args: argparse.Namespace) -> int:
    _set_application_issuance_frozen(args.slug, False)
    print(f"credential issuance for application {args.slug} is no longer frozen")
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


def _parse_report_timestamp(value: str, flag: str) -> datetime:
    """Parses `--since`/`--until` as ISO 8601 (`datetime.fromisoformat`,
    which in this project's Python floor (>=3.11) also accepts a trailing
    `Z`). A naive (no offset/timezone) value is treated as UTC -- matching
    `occurred_at`'s own storage as `timestamptz` and every other timestamp
    this module already prints/compares in UTC (`_write_control_audit`'s
    `datetime.now(timezone.utc)`) -- rather than silently adopting the
    operator's local shell timezone, which `datetime.fromisoformat` alone
    would do for a naive string once compared against an aware value.
    """
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        _die(f"{flag} must be an ISO 8601 timestamp, got {value!r}")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def cmd_audit_report(args: argparse.Namespace) -> int:
    """R-11 playbook helper (docs/design/R2DB_CCR14_CONTROL_PLANE_V1.md R-11
    "侵害/誤操作 playbook" step 2; `r2db-api/docs/CONTROL_PLANE_COMPROMISE_
    PLAYBOOK.md`): lists every durable `control_audit` row whose
    application-side event timestamp (`occurred_at` -- never `recorded_at`,
    the table's own DB-side insertion timestamp; see `0006_control_plane_
    http.sql`'s `control_audit` table comment) falls inside `[--since,
    --until]` (`--until` optional; omitting it means "no upper bound"),
    oldest first, one JSON object per line (JSON Lines) on stdout.

    Read-only: connects with `R2DB_CONTROL_DSN` (`r2dbsvc_control`, this
    schema's owner -- the same read path `credential_store.
    PostgresControlAuditSink.events()` already documents as sufficient,
    since `r2dbsvc_controlplane`, the control-plane HTTP process' own role,
    has no SELECT on this table at all -- R-3) and writes no audit event of
    its own: a read has nothing to audit, the same "list 系（読み取り）は監査
    不要" rule `cmd_list_credentials`/`cmd_list_apps` already follow.

    Ordering is `occurred_at ASC, event_id ASC` -- the identical tiebreaker
    `PostgresControlAuditSink.events()` uses (that method's own docstring,
    round-2 review NIT-4): `occurred_at`/`recorded_at` alone are not a total
    order (two rows can share a timestamp), so a second, deterministic key
    is required for a stable, repeatable "oldest first" report -- exactly
    what a playbook's "did I see every event in this window" investigation
    needs.

    Phase 3.5 WP-4 (design PHASE35_CROSS_ENTITY_AND_CONTRACT_130_V1.md
    §1-C/§4): this report's rows now include `target_id` -- the single
    target credential_id/application_id a lifecycle event acted on, when a
    single one exists (populated for every real state-changing event this
    module and `ControlPlaneService` write; `None`/absent for events with no
    single target, e.g. `bootstrap_control_credential` prior to this WP's
    own population, or a denial with no attributable target). Identifying a
    `credential_lifecycle` row's target no longer requires the timing/
    operation/`application_id` cross-reference against `list-credentials`'
    current state that earlier revisions of this docstring described as
    necessary.
    """
    since = _parse_report_timestamp(args.since, "--since")
    until = _parse_report_timestamp(args.until, "--until") if args.until else None
    if until is not None and until < since:
        _die("--until must not be before --since")

    conditions = [sql.SQL("occurred_at >= {}").format(sql.Placeholder())]
    params: list[Any] = [since]
    if until is not None:
        conditions.append(sql.SQL("occurred_at <= {}").format(sql.Placeholder()))
        params.append(until)

    statement = sql.SQL(
        "SELECT {columns} FROM {table} WHERE {where} ORDER BY occurred_at ASC, event_id ASC"
    ).format(
        columns=sql.SQL(", ").join(sql.Identifier(name) for name in _CONTROL_AUDIT_REPORT_COLUMNS),
        table=sql.Identifier(_schema(), "control_audit"),
        where=sql.SQL(" AND ").join(conditions),
    )

    dsn = _control_dsn()
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(statement, params)
            rows = cur.fetchall()

    for row in rows:
        record = dict(zip(_CONTROL_AUDIT_REPORT_COLUMNS, row))
        record["event_id"] = str(record["event_id"])
        record["occurred_at"] = record["occurred_at"].isoformat()
        record["recorded_at"] = record["recorded_at"].isoformat()
        print(json.dumps(record, sort_keys=False))
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


def cmd_reset(args: argparse.Namespace) -> int:
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

    Q-1 WP-4 (design R-4): gated by `--confirm RESET_CONTROL_CREDENTIALS`
    -- checked before `_control_store()`/`_control_audit_sink()` are even
    constructed (see `_require_cli_confirmation`'s own docstring), so an
    omitted/mismatched `--confirm` leaves the platform database completely
    untouched, no connection opened at all -- unlike `bootstrap` above,
    which stays exactly as it was (non-destructive; refusing an already-
    populated store is a `CONFLICT`, never a `destructive_confirmation`
    matter).
    """
    _require_cli_confirmation(
        args.confirm,
        phrase=RESET_CONTROL_CREDENTIALS,
        message="Confirmation required to reset all control credentials.",
        consequence=_RESET_CONSEQUENCE,
        reversible_alternative=_RESET_REVERSIBLE_ALTERNATIVE,
        recovery=_RESET_RECOVERY,
    )
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


def cmd_issue_audit_credential(_args: argparse.Namespace) -> int:
    """Phase 3.5 WP-4 (design PHASE35_CROSS_ENTITY_AND_CONTRACT_130_V1.md
    §4/§1-D, P35-D12): issues a new `role="audit"` control-table credential.
    Out-of-band ONLY -- there is no in-band issuance path for this role
    either (`CredentialIssueRequest`'s enum was never extended to accept
    it, matching the pre-existing `role="control"` rule; contract `control_
    plane.issuance`: "Audit credentials, like control credentials, are
    issued only via the out-of-band ceremony").

    Unlike `bootstrap`, this is not a once-only ritual -- any number of
    audit credentials may exist, issued at any time; there is no "first row"
    invariant to protect. It STILL takes the same `_lock_ritual` advisory
    lock `bootstrap`/`reset` use (round-2 independent review m-2): without
    it, this command's `INSERT` can interleave with a concurrent `reset`'s
    `revoke_all` -- `revoke_all` only revokes rows its own `WHERE NOT
    revoked` scan already saw, so an audit-credential row inserted mid-reset
    (after that scan, before `reset`'s transaction commits) would survive a
    reset that was supposed to wipe every control-table row. Taking the same
    lock key serializes this command against a concurrent `bootstrap`/
    `reset`/another `issue-audit-credential`, closing that window.

    `issue_audit_credential_ceremony` (`control_plane.py`) does the real
    work -- see that function's own docstring for why it issues AND rotates
    in the same transaction before ever handing back a secret (no in-band
    self-rotate exists for an audit principal, design §4 M-1): the secret
    printed below already has `must_rotate=false`.
    """
    store = _control_store()
    audit = _control_audit_sink()
    try:
        with store.unit_of_work() as work:
            _lock_ritual(work.connection)
            credential_id, secret = issue_audit_credential_ceremony(store, audit, work=work)
    finally:
        store.close()
        audit.close()
    _print_issued(credential_id, secret)
    print("must_rotate: false -- the issuance ceremony already completed rotation before this secret was printed")
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
                target_id=args.credential_id,
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
            # Coordinator follow-up (2026-09-04 audit finding §3-A): same
            # verbatim-return-value discipline as `cmd_rotate_credential`
            # above.
            bearer = store.rotate(args.credential_id, secret, work=work)
            _write_control_audit(
                work.connection,
                event_class="control_credential_lifecycle",
                operation="rotate_control_credential",
                outcome="allow",
                target_kind="control_credential",
                target_id=args.credential_id,
            )
    finally:
        store.close()
    _print_issued(args.credential_id, bearer)
    return 0


# ===========================================================================
# Q4 phase WP-1 (design docs/design/Q4_DB_SIDE_SINGLE_TRUTH_V1.md D-1/D-2,
# work order docs/work-orders/WORK_ORDER_Q4_DB_SIDE_SINGLE_TRUTH_V1.md
# WP-1 change table C; rework round, rulings-q4-wp12-rework.md sec.1,
# rulings-q4-writer-roles.md D-2(h)): declaration subcommands -- the ONLY
# way to change the declared audit writer roles' timeouts or the
# platform's `surfaces`/`audit_coalescing_window_ms` declaration, now that
# both processes reject their own former env vars outright (F-1/F-2).
# Every subcommand below connects with `R2DB_CONTROL_DSN` (`r2dbsvc_
# control`, this schema's owner -- the only role with write access to
# `platform_declarations`, migration `0008`'s own GRANTs) and writes NO
# `control_audit` event (these are provisioning-time/rare operations
# against a schema-owned table, not an authenticated-principal operation
# this schema's audit trail is designed to cover -- the same "list系
# （読み取り）は監査不要" reasoning `cmd_list_apps`/`cmd_audit_report`
# already follow extends here to the ONE write path this table has).
#
# Rework round: role names are no longer derived from `_schema()` by a
# naming-convention rewrite (`_platform_writer_roles`, removed) -- D-2(h)
# requires reading the declared `audit_writer_roles` row instead, the SAME
# row migration `0008` seeds from the very `-v api_role=.../-v
# controlplane_role=...` variables it issues `ALTER ROLE` for. URL-shape
# validation for `declare-surfaces` now calls `platform_declarations.
# validate_surfaces_value` -- the SAME function `r2db_api.main`/`r2db_api.
# control_main` call at READ time (design D-2(d): "書き込み時と読み出し時
# の両方で行い、両方が同じ Python の検証関数を通る") -- rather than keeping
# a third independent copy of the same three SHAPE checks.
#
# Q4 WP-1 does not import `r2db_api.main`/`r2db_api.control_main` here (or
# anywhere else in this file) -- both of those modules build a real ASGI
# app as an import-time side effect (`app = build_app()`/`app = build_
# control_app()`), which this CLI must never trigger merely by being
# invoked.
# ===========================================================================


def _read_audit_writer_roles(conn: "psycopg.Connection") -> tuple[str, ...]:
    """D-2(h) point 6: reads and validates the `audit_writer_roles` row
    through the SAME `validate_audit_writer_roles_value` function every
    read path uses (F-4b). Unlike `cmd_show_declarations` (which must
    degrade gracefully so an operator can SEE a broken row), this helper
    is used by `cmd_set_platform_timeouts`, which has actual work to do
    and nothing sensible to fall back to -- so it `_die`s (exit 2) on a
    missing or malformed row."""
    schema = _schema()
    with conn.cursor() as cur:
        cur.execute(sql.SQL("SELECT value FROM {table} WHERE key = 'audit_writer_roles'").format(table=_platform_declarations_table()))
        row = cur.fetchone()
    if row is None:
        _die(
            f"'audit_writer_roles' row is missing from {schema}.platform_declarations: migration {MIGRATION_NUMBER} "
            f"seeds this row in the same transaction as its own ALTER ROLE statements. Apply migration "
            f"{MIGRATION_NUMBER} to this platform database, then retry."
        )
    try:
        return validate_audit_writer_roles_value(row[0], schema=schema, ops_module=PEER_MODULE)
    except PlatformDeclarationError as exc:
        _die(str(exc))


def _platform_declarations_table() -> "sql.Composable":
    return sql.Identifier(_schema(), "platform_declarations")


def cmd_set_platform_timeouts(args: argparse.Namespace) -> int:
    """D-1 (design §3, WP-1 change table C; rework D-2(h) point 4): a
    single knob that places the SAME two ms values onto EVERY role listed
    in the declared `audit_writer_roles` row's `pg_db_role_setting` via
    `ALTER ROLE ... SET` (an assignment, not an increment -- idempotent,
    matching migration `0008`'s own idempotency). Rejects `0` and negative
    values outright (`_die`, exit 2) -- PostgreSQL reads `0` as "no limit"
    (F-10's own hazard), and an audit writer must never run unbounded. No
    per-role override is offered (design §9.2: "導出式が2roleのmaxを取る以
    上、roleごとに別値を置く利点が無い"), and no role-name ARGUMENT is
    offered either (design D-2(h) point 4: "role 名を引数で受けない") --
    the target role set comes exclusively from the declaration table."""
    if args.statement_ms <= 0:
        _die(f"--statement-ms must be a positive integer, got {args.statement_ms}")
    if args.idle_ms <= 0:
        _die(f"--idle-ms must be a positive integer, got {args.idle_ms}")
    dsn = _control_dsn()
    with psycopg.connect(dsn) as conn:
        roles = _read_audit_writer_roles(conn)
        with conn.cursor() as cur:
            for role in roles:
                cur.execute(sql.SQL("ALTER ROLE {role} SET statement_timeout = {val}").format(role=sql.Identifier(role), val=sql.Literal(f"{args.statement_ms}ms")))
                cur.execute(sql.SQL("ALTER ROLE {role} SET idle_in_transaction_session_timeout = {val}").format(role=sql.Identifier(role), val=sql.Literal(f"{args.idle_ms}ms")))
        conn.commit()
    print(f"statement_timeout={args.statement_ms}ms idle_in_transaction_session_timeout={args.idle_ms}ms set for: {', '.join(roles)}")
    print("restart both r2db_api.main and r2db_api.control_main for the new values to take effect (U-3, startup snapshot)")
    return 0


def _upsert_declaration(conn: "psycopg.Connection", *, schema: str, key: str, value: object) -> None:
    table = sql.Identifier(schema, platform_declarations.TABLE_NAME)
    statement = sql.SQL(
        "INSERT INTO {table} (key, value) VALUES (%s, %s) "
        "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()"
    ).format(table=table)
    with conn.cursor() as cur:
        cur.execute(statement, (key, Json(value)))
    conn.commit()


def cmd_declare_surfaces(args: argparse.Namespace) -> int:
    """D-2 (design §3, WP-1 change table C; amendment, q4-f3c-and-
    amendments.md): writes the SINGLE `surfaces` row both processes read
    at startup (design D-2(c): shared by BOTH, never a per-process value).
    `--control-base-url <URL>` is now OPTIONAL (omission = no `control`
    row, same as before this amendment); `--no-control` is accepted as an
    explicit, equivalent spelling of that same omission (design §3.8 F-6's
    own message text tells an operator to re-declare with `--no-control`,
    so this command must accept it) -- passing BOTH at once is a usage
    error (exit 2, now enforced by argparse's own `add_mutually_exclusive_
    group` -- G9, wp12-audit-gaps.md -- rather than a hand-rolled check
    here), but neither is REQUIRED any longer."""
    schema = _schema()
    value: dict[str, Any] = {"data": {"base_url": args.data_base_url}}
    # N-5 (monitor ruling 2026-09-05): `is not None`, never truthiness --
    # `--control-base-url ""` must reach `validate_surfaces_value` and hit
    # F-5 like every other malformed value, not be silently treated as
    # "no control" the way a falsy-but-defined value would be under a bare
    # `and` check. Mirrors MitateDB-api's own `is not None` check.
    # `--no-control` shares `--control-base-url`'s own dest and stores
    # `None`, indistinguishable at this point from plain omission (both
    # mean "no control" -- G9, mirrors MitateDB-api's identical `dest=
    # "control_base_url"` sharing).
    if args.control_base_url is not None:
        value["control"] = {"base_url": args.control_base_url}
    try:
        validate_surfaces_value(value, schema=schema, ops_module=PEER_MODULE)
    except PlatformDeclarationError as exc:
        _die(str(exc))
    with psycopg.connect(_control_dsn()) as conn:
        _upsert_declaration(conn, schema=schema, key="surfaces", value=value)
    print(f"surfaces declared: {json.dumps(value)}")
    print("restart both r2db_api.main and r2db_api.control_main for the new value to take effect (U-3, startup snapshot)")
    return 0


def cmd_declare_coalescing_window(args: argparse.Namespace) -> int:
    """D-2 (design §3, WP-1 change table C): writes the `audit_coalescing_
    window_ms` row through the SAME validation function (`validate_
    coalescing_window_value`, `r2db_api.platform_declarations`) both
    composition roots run on READ (design D-2(d): "書き込み時と読み出し時
    の両方で行い、両方が同じPythonの検証関数を通る") -- a value this command
    itself would reject can never enter the table."""
    schema = _schema()
    try:
        value = validate_coalescing_window_value(args.ms, schema=schema, ops_module=PEER_MODULE)
    except PlatformDeclarationError as exc:
        _die(str(exc))
    with psycopg.connect(_control_dsn()) as conn:
        _upsert_declaration(conn, schema=schema, key="audit_coalescing_window_ms", value=value)
    print(f"audit_coalescing_window_ms declared: {value}")
    print("restart both r2db_api.main and r2db_api.control_main for the new value to take effect (U-3, startup snapshot)")
    return 0


def cmd_show_declarations(_args: argparse.Namespace) -> int:
    """D-1/D-2 (design §3, WP-1 change table C; rework D-2(h)): a read-only
    diagnostic -- the current `platform_declarations` rows and every
    declared `audit_writer_roles` role's `pg_db_role_setting` entries.
    Deliberately does NOT run the F-3/F-4/F-8/F-4b fail-fast checks a
    composition root's own startup runs: an operator diagnosing a broken
    deployment needs to SEE a missing or malformed row printed out, not
    have this command itself refuse to run over the very condition it
    exists to surface."""
    dsn = _control_dsn()
    schema = _schema()
    print(f"{schema}.platform_declarations:")
    try:
        with psycopg.connect(dsn, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(sql.SQL("SELECT key, value, updated_at FROM {table} ORDER BY key").format(table=_platform_declarations_table()))
                rows = cur.fetchall()
    except psycopg.errors.UndefinedTable:
        rows = None
    if rows is None:
        print(f"  ({schema}.platform_declarations does not exist -- migration {MIGRATION_NUMBER} has not been applied)")
        return 0
    elif not rows:
        print("  (no rows)")
    else:
        for key, value, updated_at in rows:
            print(f"  {key} = {json.dumps(value)} (updated_at={updated_at})")

    print("writer role settings (pg_db_role_setting):")
    declared = {key: value for key, value, _updated_at in rows}
    if "audit_writer_roles" not in declared:
        print("  (no audit_writer_roles row -- apply migration 0008 with this deployment's writer role names)")
        return 0
    try:
        roles = validate_audit_writer_roles_value(declared["audit_writer_roles"], schema=schema, ops_module=PEER_MODULE)
    except PlatformDeclarationError as exc:
        print(f"  (audit_writer_roles row is invalid: {exc})")
        return 0
    with psycopg.connect(dsn) as conn:
        for role in roles:
            try:
                catalog = read_declared_role_timeouts(conn, role, ops_module=PEER_MODULE, migration=MIGRATION_NUMBER)
            except PlatformDeclarationError as exc:
                print(f"  {role}: {exc}")
                continue
            print(f"  {role}: statement_timeout={catalog.statement_ms}ms idle_in_transaction_session_timeout={catalog.idle_ms}ms")
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
        help=(
            "PERMANENTLY delete a credential row (irreversible; refused unless the credential is already revoked -- "
            "revoke first. Needed to clear the deprovisioning guard's foreign key). Requires --confirm "
            "'DELETE_CREDENTIAL <credential_id>' -- omit or get it wrong and the declaration prints to stderr as "
            "JSON and this exits 2 without touching the database"
        ),
    )
    p.add_argument("credential_id")
    p.add_argument(
        "--confirm", default=None, metavar="PHRASE",
        help="echo 'DELETE_CREDENTIAL <credential_id>' (from a prior refusal's stderr declaration) to proceed",
    )
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
        "freeze-issuance",
        help="freeze credential issuance for an application (out-of-band; issue-credential against it then refuses with FORBIDDEN)",
    )
    p.add_argument("slug")
    p.set_defaults(func=cmd_freeze_issuance)

    p = sub.add_parser(
        "unfreeze-issuance",
        help="lift a credential-issuance freeze for an application",
    )
    p.add_argument("slug")
    p.set_defaults(func=cmd_unfreeze_issuance)

    p = sub.add_parser(
        "audit-report",
        help=(
            "R-11 compromise/misuse playbook helper (see r2db-api/docs/CONTROL_PLANE_COMPROMISE_PLAYBOOK.md): "
            "list durable control_audit events with occurred_at in [--since, --until] as JSON Lines, oldest first (read-only)"
        ),
    )
    p.add_argument("--since", required=True, help="ISO 8601 timestamp (inclusive); filters on the event's occurred_at, not recorded_at")
    p.add_argument("--until", required=False, default=None, help="ISO 8601 timestamp (inclusive), optional -- omit for no upper bound")
    p.set_defaults(func=cmd_audit_report)

    p = sub.add_parser(
        "bootstrap",
        help="issue the very first control credential (refused if any control credential row already exists, including revoked ones -- use `reset` to recover)",
    )
    p.set_defaults(func=cmd_bootstrap)

    p = sub.add_parser(
        "reset",
        help=(
            "revoke every existing control credential and issue one new one, atomically -- the canonical recovery "
            "from a lost/leaked/lockout control credential. Requires --confirm RESET_CONTROL_CREDENTIALS -- omit "
            "or get it wrong and the declaration prints to stderr as JSON and this exits 2 without touching the "
            "database"
        ),
    )
    p.add_argument(
        "--confirm", default=None, metavar="PHRASE",
        help="echo RESET_CONTROL_CREDENTIALS (from a prior refusal's stderr declaration) to proceed",
    )
    p.set_defaults(func=cmd_reset)

    p = sub.add_parser(
        "issue-audit-credential",
        help=(
            "out-of-band: issue a new role=audit control-table credential (secret printed once). No in-band "
            "issuance path exists for this role either -- CredentialIssueRequest's enum was not extended. The "
            "printed secret already has must_rotate=false (the ceremony issues and rotates atomically before "
            "printing, since an audit principal has no in-band self-rotate path)"
        ),
    )
    p.set_defaults(func=cmd_issue_audit_credential)

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

    p = sub.add_parser(
        "set-platform-timeouts",
        help=(
            "Q4 D-1: set statement_timeout/idle_in_transaction_session_timeout (ALTER ROLE ... SET) on EVERY role "
            "declared in audit_writer_roles to the same two values -- rejects 0 and negative values. Restart "
            "both r2db_api.main and r2db_api.control_main afterward (startup snapshot)"
        ),
    )
    p.add_argument("--statement-ms", type=int, required=True, metavar="N")
    p.add_argument("--idle-ms", type=int, required=True, metavar="N")
    p.set_defaults(func=cmd_set_platform_timeouts)

    p = sub.add_parser(
        "declare-surfaces",
        help=(
            "Q4 D-2: declare the surfaces row both processes read at startup. --control-base-url is optional "
            "(omit for no control surface); --no-control is an equivalent, explicit way to say the same thing. "
            "Restart both r2db_api.main and r2db_api.control_main afterward"
        ),
    )
    p.add_argument("--data-base-url", required=True, metavar="URL")
    # G9 (wp12-audit-gaps.md, structural-symmetry-only ruling -- this row
    # is outside the isomorphism table): mirrors MitateDB-api's own
    # `add_mutually_exclusive_group` + `store_const` shape -- `--no-
    # control` shares `--control-base-url`'s OWN dest and argparse itself
    # rejects passing both (SystemExit(2)), rather than a hand-rolled
    # `args.no_control and args.control_base_url is not None: _die(...)`
    # check in `cmd_declare_surfaces` below. `--control-base-url ""` still
    # stores the empty string (distinct from `--no-control`'s `None`), so
    # F-5 still fires on it (N-5 below is unaffected).
    control_group = p.add_mutually_exclusive_group(required=False)
    control_group.add_argument("--control-base-url", dest="control_base_url", default=None, metavar="URL")
    control_group.add_argument("--no-control", dest="control_base_url", action="store_const", const=None)
    p.set_defaults(func=cmd_declare_surfaces)

    p = sub.add_parser(
        "declare-coalescing-window",
        help="Q4 D-2: declare audit_coalescing_window_ms (0 or a positive integer). Restart both processes afterward",
    )
    p.add_argument("--ms", type=int, required=True, metavar="N")
    p.set_defaults(func=cmd_declare_coalescing_window)

    p = sub.add_parser(
        "show-declarations",
        help="Q4 D-1/D-2: show the current platform_declarations rows and the two writer roles' pg_db_role_setting entries",
    )
    p.set_defaults(func=cmd_show_declarations)

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
