"""MitateDB-api out-of-band control-plane ceremony CLI: ``python -m
mitatedb_api.ops``.

Design v1.2 R-6 ("bootstrap / reset は out-of-band CLI...CLI entry point
(`ops` module) の新設は WP-5 の flip コミットに置く", second-round M-5): WP-4
built the reusable ceremony CORE (`control_plane.bootstrap_control_credential`
/ `reset_control_credentials`) but deliberately shipped no CLI at all --
building one earlier would have made the in-process conformance adapter's own
`bootstrap`/`reset` port operations' `SurfaceAbsent` claim (WP-3/WP-4) an
actual falsehood ("a real CLI exists, yet the adapter claims absence"). This
module is the flip's own CLI half, landing in the exact same commit as the
`/control/v1` mount (`control_main.py`) and the `control_plane` capability
declaration flip (`cell.py` reading `config.control_plane_status`).

Scope (deliberately narrower than r2db-api's sibling `r2db_api.ops`, which
also carries a large break-glass command set accumulated over several later
work packages): this WP's own instruction is exactly
``python -m mitatedb_api.ops bootstrap`` and ``... reset`` -- the two
operations contract `control_plane.bootstrap`/`control_plane.reset` require
to exist ONLY out-of-band, with no in-band substitute of any kind (R-6: "い
かなる HTTP surface からも role=control 発行はできない"). Both subcommands
call the SAME reusable ceremony core WP-4 already built and directly tested
(`bootstrap_control_credential`/`reset_control_credentials`,
`control_plane.py`) against a real `PostgresControlCredentialStore` -- this
module supplies the store, the audit-append wire-up, and the process/argv
boundary; it invents no ceremony logic of its own (R-6's own instruction:
"儀式意味論の正本は再利用可能な product code に置き、CLI と in-process
adapter の双方が同一コアを呼ぶ").

Declare-and-echo (contract `destructive_confirmation`, design R-6): ``reset``
is this CLI's one genuinely destructive subcommand. Unlike r2db-api's own
CLI (which re-implements a client-side confirmation gate,
``_require_cli_confirmation``, ahead of the ceremony call), this module needs
none of that: `reset_control_credentials` itself already recomputes the
current confirmation phrase and raises `errors.DestructiveConfirmationRequired`
-- carrying `details.required_confirmation`/`consequence`/`reversible_
alternative`/`recovery` -- BEFORE writing anything, whenever `destructive`
is not exactly `True` or `confirmation` does not exactly match (contract:
no truthy/prefix acceptance). Running `reset` at all already **is** the
destructive intent signal a wire request's own `destructive: true` field
stands in for (same reasoning r2db-api's own CLI docstring gives for its
own subcommands), so this CLI always passes `destructive=True` and forwards
whatever `--confirm` the operator supplied (or `None`) as `confirmation` --
the ceremony core's own gate does the rest. On that denial, this module
prints the declaration as one line of JSON to stderr and exits 2, touching
the platform database not at all beyond the read the gate itself needed
(the ceremony core's own `locked_for_update` runs inside the SAME
transaction this module opens, which is rolled back, never committed, when
the gate denies).

``bootstrap`` carries no such gate (contract: a second bootstrap while any
control-credential row exists -- including a fully revoked one -- is a
plain `CONFLICT`, never a confirmation matter; recovery from that state is
always `reset`, never a second `bootstrap`).

Ritual concurrency (mirrors r2db-api's own `ops.py::_lock_ritual`,
independently applied here for this peer's own advisory-lock key): both
subcommands take a `pg_advisory_xact_lock` before their own existence
check, closing the TOCTOU gap between "no control-credential row exists yet"
and this process' own `INSERT` -- released automatically when the
surrounding transaction commits or rolls back.

Connects as `mitatedbsvc_controlplane` (`MITATEDB_CONTROLPLANE_DSN`) -- the
SAME role `control_main.py`'s own composition root uses, never the
strictly-scoped `mitatedbsvc_api` role the application-plane process itself
uses (that role has no grant on `control_credentials`/`control_audit` at
all, R-4's own process-role separation). Requires
`MITATEDB_CONTROL_CREDENTIAL_PEPPER` to compute/verify control-credential
digests; `MITATEDB_CREDENTIAL_PEPPER`, if also set in this process'
environment, is checked for accidental equality with the control pepper
(R-2's pepper-separation rule, the same check `main.build_control_service`
already performs) -- application credentials are never touched by this
module at all, so that variable is otherwise unused here.

WP-6 addition (design v1.2 §3 WP-6 row: "break-glass / deprovision CLI
(WP-5 から繰延べ、監督裁定で WP-6)"): a second command family, deliberately
scoped to exactly the six operator interventions the design instruction
names -- `list-applications`/`list-credentials`, `enable-application`/
`disable-application`, `enable-credential`/`disable-credential`,
`rotate-credential`, `revoke-credential`, `audit-report`, and
`deprovision`. Unlike `bootstrap`/`reset` (which mint/replace the control
credential set itself and therefore call the ceremony CORE functions
directly, with no principal to authenticate), every one of these commands
is an ordinary `/control/v1`-shaped operation an authenticated control
credential performs -- so this module builds the SAME `ControlPlaneService`
`control_main.build_control_app` mounts behind HTTP
(`control_composition.build_control_service`) and calls its public methods
directly, never re-implementing shape/authn/authz/must_rotate-gate/bounds/
audit logic a second time (R-6's own "儀式意味論の正本は再利用可能な
product code に置き" principle, extended here from the bootstrap/reset
ceremony to this command family too -- unlike r2db-api's own sibling
`ops.py`, which predates its own `ControlPlaneService`-equivalent and so
re-implements these operations against raw SQL; this module deliberately
does not repeat that duplication now that the reusable service exists).
This is genuinely a BREAK-GLASS path, not a second public API: it exists
for an operator who holds a live control credential's id/secret (freshly
minted by `reset`, or already on file) but cannot reach `/control/v1` over
the network (a Cloud Run outage, a locked-down environment, or the control
service deliberately stopped per the compromise playbook) while the
platform database itself is still reachable -- `MITATEDB_CONTROL_
CREDENTIAL_ID`/`MITATEDB_CONTROL_CREDENTIAL_SECRET` supply that credential
exactly as an `Authorization` header would over HTTP. A `must_rotate`
credential can still do nothing here besides self-`rotate-credential`
(`ControlPlaneService._gate_must_rotate`'s own allow-list, unchanged by
this module).

`revoke-credential` reuses `ControlPlaneService.revoke_credential`'s own
built-in declare-and-echo gate (triggered only when the target is the last
remaining active control credential) exactly the way `cmd_reset` reuses
`reset_control_credentials`'s gate above -- this command always passes
`destructive=True` (running it at all is the intent signal) and forwards
`--confirm` as `confirmation`, letting the SAME `_print_denial_and_exit`
helper this module already has handle the refusal.

`deprovision` is different: it is NOT a `ControlPlaneService` operation at
all (design v1.2 R-1: deprovisioning drops a whole PostgreSQL database and
two login roles, `mitatedbsvc_provision`-only privilege no control-plane
role holds) -- it runs the existing `0004_deprovision_application.sql`
script (`migrations/`, already exercised by `tests/test_postgres.py` and
the HTTP conformance adapter's own cleanup) via `psql`, against
`MITATEDB_PROVISION_DSN`. Design v1.2 R-6 (deprovision is one of this
module's own two genuinely destructive subcommands, alongside `reset`):
"deprovision は credential 行を含む application 名前空間の終局撤去であり、
旧 guard 廃止後の唯一のインターロックとして CLI gate に載せる" -- this is
that gate, added here in WP-6 (the deprovision SQL itself shipped
guard-free back in WP-1/M-4; nothing before this WP interlocked it). The
confirmation phrase is fingerprinted on `applications.registered_at`
(contract `phrase_construction` rule (b): application_id is a name that
CAN be destroyed and recreated -- `register_application` has no defence
against reusing a just-deprovisioned application_id -- so a phrase captured
before a deprovision-then-reregister cycle must not still work afterward;
`registered_at` changes on every fresh registration, exactly like Q1-D10's
`@schema_revision` fingerprint does for `delete`). `audit-report` is also
not a `ControlPlaneService` call (it is a pure read with no operation to
authenticate as) -- it uses `control_audit.read_control_audit_events`
against `MITATEDB_PROVISION_DSN` (the control-plane role itself is
INSERT-only on `control_audit`, R-4, and cannot read this table back;
`MITATEDB_PROVISION_DSN`'s owner-role connection is the same "separate
reader" role R-8 already documents for the HTTP conformance adapter's own
`control_audit_events()` observation point).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import NoReturn, Optional, Sequence

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.types.json import Json

from . import platform_declarations
from . import platform_upgrades
from .control_audit import insert_control_audit_row, read_control_audit_events
from .control_composition import build_control_service
from .control_credential_store_postgres import DEFAULT_SCHEMA, PostgresControlCredentialStore
from .control_plane import (_APPLICATION_ID_PATTERN, PostgresApplicationRegistry,
                            bootstrap_control_credential, issue_audit_credential_ceremony,
                            reset_control_credentials)
from .config import FoundationConfig
from .credential_store_postgres import assert_pepper_separation
from .errors import (AuthenticationError, AuthorizationError, AuthorizationStateUnavailable,
                     CapabilityError, ConflictError, DestructiveConfirmationRequired,
                     FoundationError, NotFoundError, ResourceLimitError, StorageConfigurationError,
                     ValidationError)

# This repository's own copy of the package (`src/mitatedb_api/ops.py` ->
# `MitateDB-api/migrations/`) -- overridable via `MITATEDB_MIGRATIONS_DIR`
# for the same reason `_schema()` below documents an override: a
# deployment/test harness running this CLI against a throwaway,
# textually-prefixed registry (R-4's prefix-replacement convention) also
# needs a *rewritten* copy of `0004_deprovision_application.sql` (its
# `mitatedb_registry` schema reference rewritten to match), which lives
# outside this installed package entirely.
_DEFAULT_MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"

_ACTOR_TYPE = "operator_cli"

# Same classification vocabulary `conformance_adapter_mitatedb.py::_CLASSIFY_
# ORDER`/`control_http.py::_CLASSIFY_ORDER` already use, applied here so a
# caller driving this CLI as a subprocess (the HTTP conformance adapter's
# own `python -m mitatedb_api.ops bootstrap`/`reset` invocation, R-8) can
# reliably recover a contract error code from stderr -- never by pattern-
# matching this module's own free-text message, which is not a stable
# machine interface.
_CLASSIFY_ORDER: tuple[tuple[type[FoundationError], str], ...] = (
    (AuthorizationStateUnavailable, "AUTH_STATE_UNAVAILABLE"),
    (StorageConfigurationError, "SERVICE_UNAVAILABLE"),
    (AuthenticationError, "AUTH_INVALID"),
    (AuthorizationError, "FORBIDDEN"),
    (CapabilityError, "CAPABILITY_UNSUPPORTED"),
    (ValidationError, "VALIDATION_FAILED"),
    (ResourceLimitError, "LIMIT_EXCEEDED"),
    (DestructiveConfirmationRequired, "DESTRUCTIVE_CONFIRMATION_REQUIRED"),
    (ConflictError, "CONFLICT"),
    (NotFoundError, "NOT_FOUND"),
)


def _classify(exc: FoundationError) -> str:
    for exc_type, code in _CLASSIFY_ORDER:
        if isinstance(exc, exc_type):
            return code
    return "SERVICE_UNAVAILABLE"  # pragma: no cover - exhaustive by construction

# Arbitrary, fixed 64-bit `pg_advisory_xact_lock` key for the bootstrap/reset
# ritual only (mirrors r2db-api's own `ops.py::_RITUAL_ADVISORY_LOCK_KEY`,
# a DIFFERENT constant -- these two peers never share a platform database,
# so key collision between them is not a real hazard, but using a distinct
# value keeps this fact obvious on inspection). Chosen once, must never
# change: changing it would silently stop serializing against any
# already-running process still using the old key.
_RITUAL_ADVISORY_LOCK_KEY = 761761761


def _schema() -> str:
    # Not part of the documented environment contract -- exists purely so
    # this repository's own tests/conformance harness can point this CLI at
    # a throwaway, textually-prefixed registry schema (the identical escape
    # hatch `main.py`/`control_main.py` already document for the same
    # reason). A real deployment never sets this.
    return os.environ.get("MITATEDB_PLATFORM_SCHEMA") or DEFAULT_SCHEMA


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        _die(f"{name} is required")
    return value


def _die(message: str) -> NoReturn:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(2)


def _controlplane_dsn() -> str:
    return _require_env("MITATEDB_CONTROLPLANE_DSN")


def _control_pepper() -> str:
    control_pepper = _require_env("MITATEDB_CONTROL_CREDENTIAL_PEPPER")
    app_pepper = os.environ.get("MITATEDB_CREDENTIAL_PEPPER")
    try:
        assert_pepper_separation(app_pepper, control_pepper)
    except ValueError as exc:
        _die(str(exc))
    return control_pepper


def _control_store(dsn: str) -> PostgresControlCredentialStore:
    return PostgresControlCredentialStore(dsn, pepper=_control_pepper(), schema=_schema())


def _audit_append(*, work, **fields) -> str:
    return insert_control_audit_row(work, _schema(), **fields)


def _lock_ritual(conn: "psycopg.Connection") -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT pg_advisory_xact_lock(%s)", [_RITUAL_ADVISORY_LOCK_KEY])


def _print_secret_once(credential_id: str, bearer: str) -> None:
    # The secret is shown exactly once, here, and is never written anywhere
    # by this process -- copy it now, it cannot be recovered later.
    #
    # Phase 6 WP-3 追補 (supervisor ruling 2026-09-04, brief item A): every
    # caller of this function (`cmd_bootstrap`/`cmd_reset` via `_print_
    # issued`, `cmd_issue_audit_credential`, `cmd_rotate_credential`) now
    # hands it the already-COMPOSED bearer its own ceremony/service call
    # returned (`bootstrap_control_credential`/`reset_control_credentials`/
    # `issue_audit_credential_ceremony`/`ControlPlaneService.rotate_
    # credential` all compose at their own store/service layer now,
    # reversing this function's earlier WP-3 role as the single
    # composition choke point -- see those functions' own docstrings).
    # This function prints it VERBATIM; no composition happens here any
    # more. `credential_id:` stays a separate line -- an operator who
    # only needs the id (e.g. to build a rotate URL) never has to parse
    # it back out of the bearer.
    print(f"credential_id: {credential_id}")
    print(f"secret: {bearer}")
    print("(the secret above is shown once and is not stored anywhere -- save it now)")


def _print_issued(credential_id: str, secret: str) -> None:
    _print_secret_once(credential_id, secret)
    print(
        "must_rotate: true -- this credential must be rotated before it can do anything besides "
        "GET /control/v1/capabilities and rotate itself"
    )


def _print_denial_and_exit(exc: DestructiveConfirmationRequired) -> NoReturn:
    """Contract 1.2.0 `destructive_confirmation`'s own declare-and-echo
    protocol, surfaced at the CLI boundary: prints one line of problem-
    shaped JSON (type/code/message/details) to stderr and exits 2 --
    distinguishable at a glance from every other failure mode (argparse
    usage errors; a `psycopg.Error`; some other `FoundationError`, exit 1
    via `main()`'s own handling below)."""
    body = {
        "type": "DESTRUCTIVE_CONFIRMATION_REQUIRED",
        "code": "DESTRUCTIVE_CONFIRMATION_REQUIRED",
        "message": str(exc),
        "details": exc.details,
    }
    print(json.dumps(body, sort_keys=False), file=sys.stderr)
    raise SystemExit(2)


# ===========================================================================
# WP-6 break-glass command family (design v1.2 §3 WP-6 row) -- see this
# module's own docstring for why this is a distinct family from bootstrap/
# reset above (an authenticated `ControlPlaneService` call, not a ceremony-
# core call with no principal).
# ===========================================================================


def _build_service():
    """Assembles the SAME `ControlPlaneService` `control_main.build_control_
    app` mounts behind `/control/v1` -- `build_control_service` reads
    `MITATEDB_CREDENTIAL_PEPPER`/`MITATEDB_CONTROL_CREDENTIAL_PEPPER`/
    `MITATEDB_CONTROLPLANE_DSN`/`MITATEDB_PLATFORM_SCHEMA`/the four
    `MITATEDB_CONTROL_*_LIMIT` knobs from `os.environ` -- the identical
    environment contract that module's own docstring documents. A missing
    required variable (`RuntimeError`) or a pepper-separation violation
    (`ValueError`) both die loudly here, before any database connection is
    attempted, exactly like `_controlplane_dsn`/`_control_pepper` above do
    for `bootstrap`/`reset`."""
    try:
        return build_control_service(os.environ)
    except (RuntimeError, ValueError) as exc:
        _die(str(exc))


def _actor_credential() -> str:
    """The operator's own currently-live control credential -- stands in
    for the `Authorization` header a real `/control/v1` HTTP request would
    carry. Every break-glass command below authenticates through
    `ControlPlaneService` with this SAME credential; a `must_rotate`
    credential can do nothing here besides self-`rotate-credential`
    (`ControlPlaneService._gate_must_rotate`'s own allow-list -- unchanged,
    not re-implemented, by this module).

    Phase 6 WP-3 差し戻し 最終ラウンド (supervisor ruling 2026-09-04, 裁定
    1): `MITATEDB_CONTROL_CREDENTIAL_SECRET` holds the operator's own
    saved, COMPOSED bearer -- the exact `secret:` value `bootstrap`/
    `reset`/`rotate-credential` printed (this module's own runbook,
    cloud-run-cloud-sql.md §7: "the operator's own live, already-rotated
    control credential", the SAME value shape a real `Authorization`
    header would carry). This CLI never splits the bearer itself --
    exactly like `control_http.py`'s own HTTP boundary, it passes the
    presented bearer straight through to `ControlPlaneService`, which
    forwards it unchanged to `control_auth.ControlCredentialStore.
    authenticate`/`control_credential_store_postgres.
    PostgresControlCredentialStore.authenticate`, the single choke point
    that calls `split_bearer_locator` exactly once. `MITATEDB_CONTROL_
    CREDENTIAL_ID` is still required here (an early, operator-facing
    sanity check -- a saved secret with no matching saved id most likely
    means the operator's own record-keeping drifted) even though its
    value is no longer read: the bearer's own locator half already names
    the credential_id the store actually authenticates against."""
    _require_env("MITATEDB_CONTROL_CREDENTIAL_ID")
    return _require_env("MITATEDB_CONTROL_CREDENTIAL_SECRET")


def _provision_dsn() -> str:
    return _require_env("MITATEDB_PROVISION_DSN")


def _migrations_dir() -> Path:
    override = os.environ.get("MITATEDB_MIGRATIONS_DIR")
    return Path(override) if override else _DEFAULT_MIGRATIONS_DIR


def _print_json(payload) -> None:
    print(json.dumps(payload, indent=2, sort_keys=False, default=str))


def cmd_list_applications(_args: argparse.Namespace) -> int:
    service = _build_service()
    secret = _actor_credential()
    _print_json(service.list_applications(secret))
    return 0


def cmd_list_credentials(_args: argparse.Namespace) -> int:
    service = _build_service()
    secret = _actor_credential()
    _print_json(service.list_credentials(secret))
    return 0


def cmd_enable_application(args: argparse.Namespace) -> int:
    service = _build_service()
    secret = _actor_credential()
    _print_json(service.set_application_enabled(secret, args.application_id, True))
    return 0


def cmd_disable_application(args: argparse.Namespace) -> int:
    service = _build_service()
    secret = _actor_credential()
    _print_json(service.set_application_enabled(secret, args.application_id, False))
    return 0


def cmd_enable_credential(args: argparse.Namespace) -> int:
    """Works on either an application credential or a control credential
    (`ControlPlaneService.set_credential_enabled` dispatches on whichever
    table the id resolves against, `_locate_credential`) -- `enable` never
    un-revokes (SI-13, R-6's own "un-revoke はどこにも作らない"): a revoked
    row simply stays revoked, `enabled` toggling only what `revoked` has not
    already made terminal."""
    service = _build_service()
    secret = _actor_credential()
    _print_json(service.set_credential_enabled(secret, args.credential_id, True))
    return 0


def cmd_disable_credential(args: argparse.Namespace) -> int:
    service = _build_service()
    secret = _actor_credential()
    _print_json(service.set_credential_enabled(secret, args.credential_id, False))
    return 0


def cmd_rotate_credential(args: argparse.Namespace) -> int:
    """Works on either credential kind, same dispatch as enable/disable
    above. Replacing the actor's OWN credential_id here is exactly the
    self-rotate path that clears a fresh `bootstrap`/`reset` credential's
    `must_rotate` flag without needing any other operation to already be
    permitted."""
    service = _build_service()
    secret = _actor_credential()
    result = service.rotate_credential(secret, args.credential_id)
    _print_secret_once(result["credential_id"], result["secret"])
    return 0


def cmd_revoke_credential(args: argparse.Namespace) -> int:
    """`ControlPlaneService.revoke_credential`'s own built-in declare-and-
    echo gate fires only when the target is the LAST remaining active
    control credential (design R-6) -- an application credential's
    revocation is never gated (contract `non_destructive_requests`) and
    this call simply succeeds. `destructive=True` unconditionally: running
    this CLI command at all already is the destructive-intent signal
    (identical reasoning to `cmd_reset` above), `--confirm` supplies
    `confirmation` (`None` if omitted, which never matches a real phrase).
    """
    service = _build_service()
    secret = _actor_credential()
    try:
        result = service.revoke_credential(
            secret, args.credential_id, destructive=True, confirmation=args.confirm)
    except DestructiveConfirmationRequired as exc:
        _print_denial_and_exit(exc)
    _print_json(result)
    return 0


def _parse_report_timestamp(value: str, flag: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        _die(f"{flag} must be an ISO 8601 timestamp, got {value!r}")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def cmd_audit_report(args: argparse.Namespace) -> int:
    """R-9 lockout/compromise playbook helper: prints every durable
    `control_audit` row (oldest first, `read_control_audit_events`'s own
    `ORDER BY audit_seq` -- the stable monotonic ordering R-4/m-2 added
    specifically because `occurred_at` alone is not a total order) as one
    JSON object per line (JSON Lines) on stdout, optionally windowed by
    `--since`/`--until` against `occurred_at`. Read-only: writes no
    `control_audit` event of its own (a read has nothing to audit, the same
    rule this module's own `list-*` commands above follow). Requires
    `MITATEDB_PROVISION_DSN` -- `mitatedbsvc_controlplane` itself is
    INSERT-only on this table (R-4) and cannot read it back; a control
    credential (`MITATEDB_CONTROL_CREDENTIAL_ID`/`_SECRET`) is not needed
    or used here at all."""
    dsn = _provision_dsn()
    since = _parse_report_timestamp(args.since, "--since") if args.since else None
    until = _parse_report_timestamp(args.until, "--until") if args.until else None
    for event in read_control_audit_events(dsn, _schema()):
        occurred_at = event["occurred_at"]
        if since is not None and occurred_at < since:
            continue
        if until is not None and occurred_at > until:
            continue
        print(json.dumps(event, default=str, sort_keys=False))
    return 0


_DEPROVISION_CONSEQUENCE = (
    "The application's entire database (every table in it) and both its login roles are dropped, "
    "and its applications/credentials registry rows are removed permanently -- the terminal, "
    "whole-namespace removal for this application_id. Nothing about it is recoverable afterward."
)
_DEPROVISION_REVERSIBLE_ALTERNATIVE = (
    "disable-application (in-band /control/v1, or this CLI's own disable-application) refuses every "
    "credential belonging to this application without destroying anything, and is reversed by "
    "enable-application. Deprovision is for permanent removal only."
)


def _deprovision_confirmation_phrase(application_id: str, registered_at) -> str:
    """State-fingerprinted (contract `phrase_construction` rule (b):
    application_id is destroyable-and-recreatable by name -- `register_
    application` has no defence against reusing a just-deprovisioned
    application_id -- so the phrase must go stale across a deprovision-then
    -reregister cycle, mirroring Q1-D10's `@schema_revision` fingerprint for
    `delete`). `registered_at` changes on every fresh registration of the
    same application_id, which is exactly the state this needs to bind to.
    """
    canonical = registered_at.isoformat() if hasattr(registered_at, "isoformat") else str(registered_at)
    digest = hashlib.sha256(f"{application_id}:{canonical}".encode("utf-8")).hexdigest()[:16]
    return f"DEPROVISION application {application_id} @registered={digest}"


def _lookup_application_registered_at(dsn: str, application_id: str):
    statement = sql.SQL("SELECT registered_at FROM {table} WHERE application_id = {ph}").format(
        table=sql.Identifier(_schema(), "applications"), ph=sql.Placeholder())
    conn = psycopg.connect(dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(statement, [application_id])
            row = cur.fetchone()
    finally:
        conn.close()
    if row is None:
        raise NotFoundError("application was not found")
    return row[0]


def _run_deprovision_script(dsn: str, application_id: str) -> None:
    script = _migrations_dir() / "0004_deprovision_application.sql"
    if not script.exists():
        _die(f"deprovision script not found at {script} (set MITATEDB_MIGRATIONS_DIR to override)")
    result = subprocess.run(
        ["psql", dsn, "-v", "ON_ERROR_STOP=1", "-v", f"app_id={application_id}", "-f", str(script)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        _die(f"deprovision script failed:\n{result.stdout}\n{result.stderr}")


def cmd_deprovision(args: argparse.Namespace) -> int:
    """This module's own second genuinely destructive subcommand (alongside
    `reset`) -- see this module's own docstring for why this is not a
    `ControlPlaneService` call at all, and for the fingerprinted phrase's
    own rationale. `application_id` is format-validated BEFORE any database
    access or phrase computation (mirrors r2db-api's own `delete-credential`
    MA-1 fix: an unvalidated identifier must never reach a confirmation
    phrase or a shell-adjacent subprocess argument)."""
    application_id = args.application_id
    if not _APPLICATION_ID_PATTERN.fullmatch(application_id):
        raise ValidationError(f"application_id must match {_APPLICATION_ID_PATTERN.pattern!r}")
    dsn = _provision_dsn()
    registered_at = _lookup_application_registered_at(dsn, application_id)
    phrase = _deprovision_confirmation_phrase(application_id, registered_at)
    if args.confirm != phrase:
        _print_denial_and_exit(DestructiveConfirmationRequired(
            "deprovisioning this application requires the current confirmation phrase",
            details={
                "required_confirmation": phrase,
                "consequence": _DEPROVISION_CONSEQUENCE,
                "reversible_alternative": _DEPROVISION_REVERSIBLE_ALTERNATIVE,
                "recovery": None,
            },
        ))
    _run_deprovision_script(dsn, application_id)
    print(f"application {application_id} deprovisioned")
    return 0


def cmd_bootstrap(_args: argparse.Namespace) -> int:
    """Issues the very first control credential. Refuses (`CONFLICT`, via
    the shared ceremony core) if any `control_credentials` row already
    exists -- including a fully revoked one; recovery from that state is
    always `reset`, never a second `bootstrap`."""
    dsn = _controlplane_dsn()
    store = _control_store(dsn)
    conn = psycopg.connect(dsn)
    try:
        _lock_ritual(conn)
        credential_id, secret = bootstrap_control_credential(
            store, _audit_append, work=conn, actor_type=_ACTOR_TYPE,
        )
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()
    _print_issued(credential_id, secret)
    return 0


def cmd_reset(args: argparse.Namespace) -> int:
    """Revokes every existing control credential (including already-
    disabled/already-revoked rows) and issues exactly one new one,
    atomically -- the canonical recovery from a lost/leaked/lockout control
    credential. Gated by the ceremony core's own declare-and-echo check
    (`--confirm <phrase>`, echoing a prior denial's own `required_
    confirmation`) -- see this module's own docstring for why no separate
    CLI-side gate is needed."""
    dsn = _controlplane_dsn()
    store = _control_store(dsn)
    conn = psycopg.connect(dsn)
    try:
        _lock_ritual(conn)
        credential_id, secret = reset_control_credentials(
            store, _audit_append, work=conn, destructive=True, confirmation=args.confirm,
            actor_type=_ACTOR_TYPE,
        )
        conn.commit()
    except DestructiveConfirmationRequired as exc:
        conn.rollback()
        _print_denial_and_exit(exc)
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()
    _print_issued(credential_id, secret)
    return 0


# ===========================================================================
# Phase 3.5 WP-5 (design docs/design/PHASE35_CROSS_ENTITY_AND_CONTRACT_130_
# V1.md §4/§1-D/§1-E): out-of-band audit-credential issuance ceremony, and
# per-application issuance-freeze toggle -- both CLI-only, no in-band
# endpoint exists for either (P35-D6/D12).
# ===========================================================================


def cmd_issue_audit_credential(_args: argparse.Namespace) -> int:
    """Phase 3.5 WP-5 (§4/§1-D, P35-D12): issues a new `role="audit"`
    control-table credential. Out-of-band ONLY -- there is no in-band
    issuance path for this role either (`CredentialIssueRequest`'s enum was
    never extended to accept it, matching the pre-existing `role="control"`
    rule; contract `control_plane.issuance`: "Audit credentials, like
    control credentials, are issued only via the out-of-band ceremony").

    Unlike `bootstrap`, this is not a once-only ritual -- any number of
    audit credentials may exist, issued at any time; there is no "first
    row" invariant to protect. It STILL takes the SAME `_lock_ritual`
    advisory lock `bootstrap`/`reset` use (mirrors r2db-api's own review
    lesson, applied here for this peer's own lock key): without it, this
    command's `INSERT` could interleave with a concurrent `reset`'s
    `revoke_all` -- `revoke_all` only revokes rows its own scan already saw,
    so an audit-credential row inserted mid-reset (after that scan, before
    `reset`'s transaction commits) would survive a reset that was supposed
    to wipe every control-table row. Taking the same lock key serializes
    this command against a concurrent `bootstrap`/`reset`/another
    `issue-audit-credential`, closing that window.

    `issue_audit_credential_ceremony` (`control_plane.py`) does the real
    work -- see that function's own docstring for why it issues AND rotates
    in the same transaction before ever handing back a secret (no in-band
    self-rotate exists for an audit principal, design §4 M-1): the secret
    printed below already has `must_rotate=false`.
    """
    dsn = _controlplane_dsn()
    store = _control_store(dsn)
    conn = psycopg.connect(dsn)
    try:
        _lock_ritual(conn)
        credential_id, secret = issue_audit_credential_ceremony(
            store, _audit_append, work=conn, actor_type=_ACTOR_TYPE,
        )
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()
    _print_secret_once(credential_id, secret)
    print("must_rotate: false -- the issuance ceremony already completed rotation before this secret was printed")
    return 0


def _applications_registry(dsn: str) -> PostgresApplicationRegistry:
    return PostgresApplicationRegistry(dsn, schema=_schema())


def _set_issuance_frozen(application_id: str, frozen: bool, *, operation: str) -> int:
    """Phase 3.5 WP-5 (design §4/§1-E, P35-D6): CLI-only, non-destructive --
    same class as `_set_application_enabled`-style toggles (no
    declare-and-echo confirmation gate; unlike `reset`/deprovision, freezing/
    unfreezing issuance is fully reversible with no data loss). Not a
    `ControlPlaneService` operation (there is no in-band endpoint at all for
    this concept, P35-D6) -- writes directly against the control-plane DSN,
    the same shape `bootstrap`/`reset` above already use, with a manually
    appended `control_audit` row on the SAME connection/transaction.

    `application_id` is format-validated BEFORE any database access or
    audit write (mirrors `cmd_deprovision`'s own MA-1 guard, same rationale:
    an unvalidated operator-supplied string must never land in a durable
    `control_audit` row, here via `application_id`/`target_id` rather than a
    confirmation phrase or subprocess argument)."""
    if not _APPLICATION_ID_PATTERN.fullmatch(application_id):
        raise ValidationError(f"application_id must match {_APPLICATION_ID_PATTERN.pattern!r}")
    dsn = _controlplane_dsn()
    registry = _applications_registry(dsn)
    conn = psycopg.connect(dsn)
    try:
        registry.set_issuance_frozen(application_id, frozen, work=conn)
        insert_control_audit_row(
            conn, _schema(), event_class="application_lifecycle", operation=operation, outcome="allow",
            target_kind="application", application_id=application_id, actor_type=_ACTOR_TYPE,
            target_id=application_id,
        )
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()
    return 0


def cmd_freeze_issuance(args: argparse.Namespace) -> int:
    _set_issuance_frozen(args.application_id, True, operation="freeze_issuance")
    print(f"credential issuance for application {args.application_id} is now frozen")
    return 0


def cmd_unfreeze_issuance(args: argparse.Namespace) -> int:
    _set_issuance_frozen(args.application_id, False, operation="unfreeze_issuance")
    print(f"credential issuance for application {args.application_id} is no longer frozen")
    return 0


# ===========================================================================
# Q4 phase (design docs/design/Q4_DB_SIDE_SINGLE_TRUTH_V1.md D-1/D-2, work
# order docs/work-orders/WORK_ORDER_Q4_DB_SIDE_SINGLE_TRUTH_V1.md §4 WP-2
# 変更対象 C): declaration-management subcommands. All four connect with
# `MITATEDB_PROVISION_DSN` -- `mitatedbsvc_provision` (or its throwaway-
# prefixed test equivalent) is the owner of both new objects migration
# `0007_platform_declarations.sql` creates. Terminal-facing prose ("next
# ops command") is never written twice: `platform_declarations.py`'s own
# fail-fast messages already name every one of these subcommands verbatim
# (design §3.8) -- these subcommands are simply what those messages point
# an operator AT.
# ===========================================================================


def _read_audit_writer_roles(conn: "psycopg.Connection") -> tuple[str, ...]:
    """D-2(h) 4: the target of `set-platform-timeouts` comes from the
    `audit_writer_roles` row itself -- never a role-name argument, never a
    naming-convention derivation from `current_user`/schema. Raw read +
    the SAME `validate_audit_writer_roles_value` the read/write paths use
    (design D-2(h) 6: "行の検証は...同じ関数を通る")."""
    schema = _schema()
    try:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("SELECT value FROM {table} WHERE key = 'audit_writer_roles'").format(
                    table=sql.Identifier(schema, platform_declarations.TABLE_NAME)))
            row = cur.fetchone()
    except psycopg.errors.UndefinedTable:
        conn.rollback()
        _die(
            f"relation {schema}.{platform_declarations.TABLE_NAME} does not exist: apply migration "
            f"{platform_declarations.MIGRATION_NUMBER} to this platform database first."
        )
    if row is None:
        _die(
            f"no 'audit_writer_roles' row in {schema}.{platform_declarations.TABLE_NAME}: migration "
            f"{platform_declarations.MIGRATION_NUMBER} seeds this row in the same transaction as its own "
            f"ALTER ROLE statements. Apply that migration to this platform database first."
        )
    try:
        return platform_declarations.validate_audit_writer_roles_value(
            row[0], schema=schema, ops_module=platform_declarations.PEER_MODULE)
    except platform_declarations.PlatformDeclarationError as exc:
        _die(str(exc))


def _read_audit_writer_roles_lenient(conn: "psycopg.Connection") -> Optional[tuple[str, ...]]:
    """`show-declarations`'s own lenient variant of `_read_audit_writer_
    roles` -- a diagnostic must still print SOMETHING for a row that is
    absent or fails validation, rather than dying (this command's own
    docstring: "does not itself enforce...validation"). Returns `None`
    (never a guessed role-name pair) when the row is absent or invalid --
    D-2(h) 3's "role 名の導出規則はコードから撤去する" applies to a
    DIAGNOSTIC command exactly as much as to a fail-fast one: a deployment
    whose real writer roles are not the production seed names must never
    have this command print settings for roles that do not exist on it
    (monitor ruling 2026-09-05, N-6). Raises `psycopg.errors.UndefinedTable`
    (uncaught) so the caller's own existing table-not-found handling
    applies uniformly."""
    schema = _schema()
    with conn.cursor() as cur:
        cur.execute(
            sql.SQL("SELECT value FROM {table} WHERE key = 'audit_writer_roles'").format(
                table=sql.Identifier(schema, platform_declarations.TABLE_NAME)))
        row = cur.fetchone()
    if row is None:
        return None
    try:
        return platform_declarations.validate_audit_writer_roles_value(
            row[0], schema=schema, ops_module=platform_declarations.PEER_MODULE)
    except platform_declarations.PlatformDeclarationError:
        return None


def cmd_set_platform_timeouts(args: argparse.Namespace) -> int:
    """D-1(a)/D-2(h) 4: the single ALTER-ROLE knob -- one pair of values,
    EVERY role in the declared `audit_writer_roles` row, always together
    (design §3.10: "role 別の指定は設けない"). Takes no role-name
    argument -- the target comes from the declaration table itself, never
    a naming-convention derivation. Rejects 0 and negative values (F-10's
    own precondition: an audit writer must never be configured
    unbounded)."""
    if args.statement_ms <= 0:
        _die("--statement-ms must be a positive integer")
    if args.idle_ms <= 0:
        _die("--idle-ms must be a positive integer")
    dsn = _provision_dsn()
    conn = psycopg.connect(dsn)
    try:
        roles = _read_audit_writer_roles(conn)
        statement_literal = f"{args.statement_ms}ms"
        idle_literal = f"{args.idle_ms}ms"
        with conn.cursor() as cur:
            for role in roles:
                cur.execute(sql.SQL("ALTER ROLE {} SET statement_timeout = {}").format(
                    sql.Identifier(role), sql.Literal(statement_literal)))
                cur.execute(sql.SQL("ALTER ROLE {} SET idle_in_transaction_session_timeout = {}").format(
                    sql.Identifier(role), sql.Literal(idle_literal)))
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()
    print(
        f"statement_timeout = {statement_literal}, idle_in_transaction_session_timeout = {idle_literal} set on "
        f"{', '.join(roles)}. Restart both processes for this to take effect (D-1(e): startup snapshot)."
    )
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
    """D-2(c)/(d): writes the single `surfaces` row both processes read --
    this command REPLACES the entire row (design D-2: "この表には...
    deployment固有" value). `--control-base-url` is OPTIONAL (omitted =
    no control row declared); `--no-control` is an explicit, equivalent
    form of that same omission (supervisor ruling correction 2026-09-05,
    `{scratchpad}/q4-f3c-and-amendments.md`: "`--no-control` は廃止"の旧
    裁定は撤回され、「省略と等価の明示形」として受け付ける). Passing BOTH
    is a usage error (argparse's own mutually-exclusive-group behavior,
    exit 2) -- neither is required. Validated through the SAME function
    (`platform_declarations.validate_surfaces_value`) the read path uses
    (D-2(d): "書き込み時と読み出し時の両方で...同じ Python の検証関数を
    通る")."""
    value: dict = {"data": {"base_url": args.data_base_url}}
    if args.control_base_url is not None:
        value["control"] = {"base_url": args.control_base_url}
    schema = _schema()
    try:
        platform_declarations.validate_surfaces_value(value, schema=schema, ops_module=platform_declarations.PEER_MODULE)
    except platform_declarations.PlatformDeclarationError as exc:
        _die(str(exc))
    dsn = _provision_dsn()
    conn = psycopg.connect(dsn)
    try:
        _upsert_declaration(conn, schema=schema, key="surfaces", value=value)
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()
    print(f"surfaces declared: {json.dumps(value, sort_keys=True)}")
    print("Restart both processes for this to take effect (D-2(g): startup snapshot).")
    return 0


def cmd_declare_coalescing_window(args: argparse.Namespace) -> int:
    """D-2(c)/(d): writes `audit_coalescing_window_ms`. Validated through
    the SAME function the read path uses."""
    schema = _schema()
    try:
        platform_declarations.validate_coalescing_window_value(args.ms, schema=schema, ops_module=platform_declarations.PEER_MODULE)
    except platform_declarations.PlatformDeclarationError as exc:
        _die(str(exc))
    dsn = _provision_dsn()
    conn = psycopg.connect(dsn)
    try:
        _upsert_declaration(conn, schema=schema, key="audit_coalescing_window_ms", value=args.ms)
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()
    print(f"audit_coalescing_window_ms declared: {args.ms}")
    print("Restart both processes for this to take effect (D-2(g): startup snapshot).")
    return 0


def cmd_show_declarations(_args: argparse.Namespace) -> int:
    """Read-only diagnostic: the current `platform_declarations` row
    contents (raw, unvalidated -- this command's own job is to show what
    IS there, including a malformed hand-edited value, not to enforce
    F-3/F-4b/F-5 the way a composition root's own startup path does) and
    every declared writer role's `pg_db_role_setting` declarations
    (D-2(h): read from the `audit_writer_roles` row itself, never a
    naming-convention derivation -- role-name derivation is removed from
    this code path entirely, not just from the fail-fast one: when the
    row is itself absent/invalid, `role_settings` reports that fact
    instead of guessing a role-name pair that may not exist on this
    deployment, monitor ruling 2026-09-05 N-6)."""
    dsn = _provision_dsn()
    schema = _schema()
    conn = psycopg.connect(dsn)
    try:
        try:
            roles = _read_audit_writer_roles_lenient(conn)
        except psycopg.errors.UndefinedTable:
            conn.rollback()
            roles = None
        payload: dict = {"platform_declarations": None, "role_settings": {}}
        try:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL("SELECT key, value, updated_at FROM {table} ORDER BY key").format(
                        table=sql.Identifier(schema, platform_declarations.TABLE_NAME)))
                payload["platform_declarations"] = [
                    {"key": key, "value": value, "updated_at": updated_at} for key, value, updated_at in cur.fetchall()
                ]
        except psycopg.errors.UndefinedTable:
            conn.rollback()
            payload["platform_declarations"] = f"table does not exist (migration {platform_declarations.MIGRATION_NUMBER} not applied)"
        if roles is None:
            payload["role_settings"] = (
                f"(no audit_writer_roles row -- apply migration {platform_declarations.MIGRATION_NUMBER} "
                f"with this deployment's writer role names)"
            )
        else:
            for role in roles:
                rows = platform_declarations._role_setting_rows(conn, role)  # noqa: SLF001 -- ops-internal reach-in, same module family
                payload["role_settings"][role] = [
                    {"setdatabase": setdatabase, "database": datname, "setconfig": setconfig}
                    for setdatabase, datname, setconfig in rows
                ]
    finally:
        conn.close()
    _print_json(payload)
    return 0


# ===========================================================================
# Phase 8 WP-4 (design docs/design/PHASE8_EFFECTIVE_BOUNDS_AND_HYGIENE_V1.md
# D-5 decision 1/2, work order docs/work-orders/
# WORK_ORDER_PHASE8_EFFECTIVE_BOUNDS_V1.md §2 WP-4): `ops verify-
# declarations` -- a machine-checkable "is this process' declared platform
# state one it could actually start against" gate, run OUT OF BAND against
# the provision DSN, before or after a deployment. Reuses the SAME
# `platform_declarations` check functions the composition roots call at
# startup (never a second, independent copy of the checks); the only new
# code here is the exit-code table and the one-line-per-check driver.
# `_VERIFY_DECLARATIONS_EXIT_CODES`/`_VERIFY_DECLARATIONS_READ_ORDER`/
# `_verify_declarations_ok`/`_verify_declarations_fail`/`_verify_
# declarations_checks`/`cmd_verify_declarations` are ALL pinned isomorphic
# to r2db-api's own same-named realizations (`_ISOMORPHIC_TARGETS`, WP-4
# rework round 2, supervisor ruling 2026-09-06, wp4-rework-2.md #1).
# `cmd_verify_declarations` reads its own required env var's NAME through
# `platform_declarations.PROVISION_DSN_ENV` (already a peer-specific-VALUE
# constant defined once in `platform_declarations.py`, the same technique
# `PEER_MODULE`/`MIGRATION_NUMBER`/`CONTROL_PLANE_STATUS_ENV` already use
# elsewhere in this file) rather than embedding the literal env var name
# (`MITATEDB_PROVISION_DSN` here, `R2DB_CONTROL_DSN` on r2db-api) directly
# in its own body -- the function's own AST, once its per-peer docstring
# is stripped, therefore carries no peer-specific literal at all and
# normalizes byte-identical to the sibling peer's realization.
# ===========================================================================

#: Design D-5 "実装の形 (a)": the fixed F-number -> exit code table. Both
#: peers' own `platform_declarations.py` raise the SAME F-number for the
#: SAME condition, so this table is verbatim on both peers.
_VERIFY_DECLARATIONS_EXIT_CODES = {
    "F-3": 3,
    "F-3c": 4,
    "F-4": 5,
    "F-4b": 6,
    "F-5": 7,
    "F-8": 8,
    "F-6": 9,
    "F-7": 10,
    "F-10": 10,
    "F-11": 10,
    "F-13": 11,
    "F-9": 12,
    # Contract 1.7.0 (work order §2 WP-3e F-3, `{scratchpad}/
    # rulings-r3-r7-flip.md` F-3): `check_contract_170_declarations`'s
    # own new condition -- the next unused exit code (F-12 is reserved,
    # out of scope for this command, `_verify_declarations_checks`'s own
    # docstring / the trailing disclosure line below).
    "F-14": 13,
}

#: `read_platform_declarations`'s own fixed internal order (that function's
#: own docstring: table existence before row existence before value
#: validation) -- drives the OK lines printed for every condition that
#: check already passed before it either succeeded outright or raised on
#: the one that failed.
_VERIFY_DECLARATIONS_READ_ORDER = (
    ("F-8", "declaration table present"),
    ("F-3", "surfaces row present"),
    ("F-4", "audit_coalescing_window_ms row present"),
    ("F-5", "surfaces value valid"),
    ("F-4b", "audit_coalescing_window_ms / audit_writer_roles value valid"),
)


def _verify_declarations_ok(code: str, description: str) -> None:
    print(f"OK   {code}  {description}")


def _verify_declarations_fail(exc: "platform_declarations.PlatformDeclarationError") -> int:
    print(f"FAIL {exc.code}  {exc}")
    return _VERIFY_DECLARATIONS_EXIT_CODES[exc.code]


#: WP-4 rework (supervisor ruling 2026-09-06, wp4-rework-1.md #2): this was
#: previously inlined into `cmd_verify_declarations` itself, with the
#: trailing "out of scope" line printed AFTER the `try/finally` that this
#: logic lived inside -- every `return` here is a `return` out of that
#: outer `try`, so the finally ran (closing the connection) but the code
#: textually AFTER the finally block never did on any FAIL path. Splitting
#: this into its own function that only ever RETURNS a code (never prints
#: the trailing disclosure line itself) lets `cmd_verify_declarations`
#: print that line exactly once, unconditionally, for every code this
#: returns -- 0 through 13 alike.
def _verify_declarations_checks(conn: "psycopg.Connection", args: argparse.Namespace, schema: str, dsn: str) -> int:
    try:
        declarations = platform_declarations.read_platform_declarations(
            conn, schema=schema, ops_module=platform_declarations.PEER_MODULE, migration=platform_declarations.MIGRATION_NUMBER)
    except platform_declarations.PlatformDeclarationError as exc:
        for code, description in _VERIFY_DECLARATIONS_READ_ORDER:
            if code == exc.code:
                break
            _verify_declarations_ok(code, description)
        return _verify_declarations_fail(exc)
    for code, description in _VERIFY_DECLARATIONS_READ_ORDER:
        _verify_declarations_ok(code, description)

    if args.control:
        try:
            platform_declarations.require_control_surface_declared(
                declarations.surfaces, schema=schema, ops_module=platform_declarations.PEER_MODULE)
        except platform_declarations.PlatformDeclarationError as exc:
            return _verify_declarations_fail(exc)
        _verify_declarations_ok("F-3c", "surfaces.control present")

    control_plane_status = os.environ.get(platform_declarations.CONTROL_PLANE_STATUS_ENV)
    if control_plane_status is not None:
        try:
            platform_declarations.check_control_surface_consistency(
                declarations.surfaces, control_plane_status, ops_module=platform_declarations.PEER_MODULE)
        except platform_declarations.PlatformDeclarationError as exc:
            return _verify_declarations_fail(exc)
        _verify_declarations_ok("F-6", f"surfaces.control agrees with {platform_declarations.CONTROL_PLANE_STATUS_ENV}")

    try:
        platform_declarations.check_writer_role_timeouts(
            conn, declared_roles=declarations.audit_writer_roles, schema=schema,
            ops_module=platform_declarations.PEER_MODULE, migration=platform_declarations.MIGRATION_NUMBER)
    except platform_declarations.PlatformDeclarationError as exc:
        return _verify_declarations_fail(exc)
    _verify_declarations_ok("F-7/F-10/F-11/F-13/F-9", "connected role's writer timeout settings valid")

    # Contract 1.7.0 (work order §2 WP-3e F-3, `{scratchpad}/
    # rulings-r3-r7-flip.md` F-3): the "enabled" declaration checked
    # against the actual deployed state -- the served capabilities
    # document, this process' own `FoundationConfig`, AND (the one part
    # that can genuinely fail against a real deployment) every registered
    # application's own per-application upgrade ledger. Run
    # unconditionally like the writer-role check just above.
    try:
        applied_by_application = _applied_upgrade_numbers_by_application(conn, dsn)
        # `data_base_url` is no longer read from bare `environ` by
        # `FoundationConfig.from_env` (design D-2(f), `config.py`'s own
        # historical note above `from_env`'s "surfaces.data is required"
        # raise) -- the caller (normally `main.build_app`) reads it from
        # THIS SAME `declarations.surfaces` first. `declarations` is
        # already this function's own live value (`read_platform_
        # declarations` above), so `config` is built from it here too --
        # never a second, independently-drifting env read. `config` is
        # used ONLY to build the probe cell `_contract_170_capabilities_
        # document` calls its real `capabilities()` method through --
        # WP-3e rework T3 (ruling `{scratchpad}/rulings-r3-r7-flip.md`
        # L-2/M-7): `check_contract_170_declarations` itself no longer
        # takes `config` at all, and reads the `limits` block from the
        # SERVED capabilities document it returns, never from `config`
        # directly (that direct-`getattr` form was the dead-check flaw
        # this rework removes -- see `platform_declarations.py`'s own
        # comment above `check_contract_170_declarations`).
        config = FoundationConfig.from_env(data_base_url=declarations.surfaces.data_base_url)
        platform_declarations.check_contract_170_declarations(
            _contract_170_capabilities_document(config),
            applied_by_application,
            platform_upgrades.PLATFORM_UPGRADE_NUMBERS,
        )
    except platform_declarations.PlatformDeclarationError as exc:
        return _verify_declarations_fail(exc)
    _verify_declarations_ok(
        "F-14",
        "contract 1.7.0 capabilities enabled, enum_members/idempotency_entries/idempotency_retention_ms limits valid, "
        f"and every registered application has applied upgrades {sorted(platform_upgrades.PLATFORM_UPGRADE_NUMBERS)}",
    )
    return 0


def _contract_170_capabilities_document(config: "FoundationConfig") -> dict:
    """The REAL `ApplicationRuntime.capabilities()` document for a
    throwaway, entirely in-memory application/credential -- never a
    second, hand-written copy of what `cell.py` is expected to declare
    (mirrors r2db-api's own `_contract_170_capabilities_document`,
    isomorphism pinned): this exercises the SAME production code path a
    real client's `GET /v1/capabilities` reaches, so a future regression
    that stops declaring one of the contract 1.7.0 capabilities `enabled`
    is caught here too, not only by `mitatedb_api.cell`'s own unit tests.
    No network/PostgreSQL connection is involved -- `ApplicationCell`'s
    own default backend (`backend_sqlite.SQLiteBackend`) is a
    deterministic, in-memory, pure-Python object. `config` is the
    CALLER's own already-resolved `FoundationConfig` (never rebuilt
    here) -- the same instance `check_contract_170_declarations`'s own
    limit-value check inspects, so the capabilities this probe reports
    and the limits that check reads are provably the same deployment."""
    from .cell import ApplicationCell, ApplicationRuntime, Principal
    from .auth import Role

    cell = ApplicationCell("verify_declarations_probe", config)
    principal = Principal(
        application_id="verify_declarations_probe", credential_id="verify_declarations_probe", role=Role.RUNTIME,
    )
    runtime = ApplicationRuntime(cell, principal)
    return dict(runtime.capabilities())


def _applied_upgrade_numbers_by_application(
    conn: "psycopg.Connection", provision_dsn: str,
) -> dict:
    """`platform_upgrades.read_applied_upgrade_numbers` for EVERY
    registered, provisioned application (`database_name IS NOT NULL` --
    same target set `_registry_applications_for_upgrade(conn, schema=...,
    application_id=None)` already selects for `ops upgrade-applications`).
    An application with no `database_name` at all (registered but never
    provisioned) is reported with an empty-ledger sentinel (`None`,
    "every number pending") rather than skipped -- an unprovisioned
    application cannot have applied anything, so it is not silently
    exempt from F-14's own declaration. Mirrors r2db-api's own
    `_applied_upgrade_numbers_by_application`, isomorphism pinned."""
    result: dict = {}
    for application_id, database_name, _developer_role in _registry_applications_for_upgrade(
        conn, schema=_schema(), application_id=None,
    ):
        if database_name is None:
            result[application_id] = None
            continue
        app_dsn = _app_dsn(provision_dsn, database_name)
        try:
            app_conn = psycopg.connect(app_dsn)
        except psycopg.Error:
            result[application_id] = None
            continue
        try:
            result[application_id] = platform_upgrades.read_applied_upgrade_numbers(
                app_conn, ledger_table_name=platform_upgrades.LEDGER_TABLE_NAME)
        finally:
            app_conn.close()
    return result


def cmd_verify_declarations(args: argparse.Namespace) -> int:
    """R-11 WP-4 (design D-5 decision 1/2): one line per check, OK/FAIL
    prefixed, in `read_platform_declarations`'s own fixed order followed
    by F-3c (only when `--control` is given), F-6 (only when this peer's
    own `*_CONTROL_PLANE_STATUS` env var is defined), then the writer-role
    dual check (F-7/F-10/F-11/F-13/F-9) unconditionally. The first FAIL
    stops the run and returns that F-number's own fixed exit code
    (`_VERIFY_DECLARATIONS_EXIT_CODES`, via `_verify_declarations_checks`).

    Exit codes follow design D-5 実装の形 (a) literally: 1 is a USAGE
    error (this command's own required env var, `MITATEDB_PROVISION_DSN`,
    is unset -- a mistake in how the command was invoked, never a check
    result) and 2 is a real inability to connect once that DSN is known
    (host down, auth rejected, etc.) -- "検査以前の失敗" distinct from
    every F-numbered condition. This command therefore does NOT reuse the
    shared `_provision_dsn()`/`_die()` pair other subcommands call (that
    pair is SystemExit(2) for a missing env var, the opposite assignment
    from this table) -- WP-4 rework (supervisor ruling 2026-09-06,
    wp4-rework-1.md #7): those other subcommands' own `_die`=2 convention
    predates this table and is out of this WP's scope to renumber; only
    this command's own usage-error path is realigned to the table it is
    the one that has to answer to. (`argparse`'s OWN native argument
    errors -- e.g. an unrecognized flag -- still exit 2, Python's built-in
    `ArgumentParser.error()` behavior for the whole CLI; redirecting THAT
    would mean overriding `error()` on the shared parser, touching every
    subcommand, not just this one -- reported as the table's one
    unreachable cell rather than silently left inconsistent.)

    F-1/F-2 (this process' own env, not readable from a provision DSN
    connection) and F-12 (cell-open-time only, design D-5 "対象外の3条件")
    are out of this command's reach -- named, with the reason, on the last
    output line, printed for every code `_verify_declarations_checks`
    returns (0 through 13 alike), never only on the 0 path."""
    schema = _schema()
    dsn = os.environ.get(platform_declarations.PROVISION_DSN_ENV)
    if not dsn:
        print(f"error: {platform_declarations.PROVISION_DSN_ENV} is required", file=sys.stderr)
        return 1
    try:
        conn = psycopg.connect(dsn, autocommit=True)
    except psycopg.Error as exc:
        print(f"error: cannot connect to platform database: {exc}", file=sys.stderr)
        return 2
    try:
        rc = _verify_declarations_checks(conn, args, schema, dsn)
    finally:
        conn.close()
    print(
        "--   F-1/F-2/F-12  out of scope for this command: F-1/F-2 depend on this process' own environment, "
        "not the provision DSN; F-12 is checked only at cell-open time"
    )
    return rc


# ===========================================================================
# Q4 phase D-4/D-5 (design docs/design/Q4_DB_SIDE_SINGLE_TRUTH_V1.md,
# work order docs/work-orders/WORK_ORDER_Q4_DB_SIDE_SINGLE_TRUTH_V1.md §4
# WP-4 変更対象 E): `upgrade-applications` (bulk-apply, provision DSN
# only) and `upgrade-status` (read-only, same DSN). Neither takes a
# control credential -- the API process itself never holds this
# capability (SI-02: schema DDL is provision-DSN-only).
# ===========================================================================


def _app_dsn(provision_dsn: str, database_name: str) -> str:
    """Design D-4(b): "application DB への接続は...provision DSN の
    `dbname` を...差し替えて接続する" -- never a second, independently
    configured DSN. Same login identity (`mitatedbsvc_provision`) as the
    platform connection; that role's own implicit database-owner
    privilege (it `CREATE DATABASE`d every application database, `0003`'s
    own header) plus the explicit `GRANT SELECT ... TO SESSION_USER` every
    provisioning path now leaves on the ledger table (design D-3(a)) is
    what lets this connection read the ledger back at all."""
    params = conninfo_to_dict(provision_dsn)
    params["dbname"] = database_name
    return make_conninfo(**params)


def _registry_applications_for_upgrade(
    conn: "psycopg.Connection", *, schema: str, application_id: Optional[str],
) -> list[tuple[str, Optional[str], Optional[str]]]:
    """Design D-4(a): the DEFAULT target set (`application_id is None`) is
    every registered application whose provisioning has actually
    completed (`database_name IS NOT NULL`) -- `enabled` is NOT part of
    this filter (design D-4(a): "`enabled` は対象選択に影響しない...無効化
    中の application の DB も一括適用の対象に含める").

    M-2(a)/(d) fix (supervisor ruling 2026-09-05, rework): an EXPLICITLY
    named `--application <id>` is returned REGARDLESS of its own
    `database_name` -- mirrors r2db-api's own `_registry_applications_
    for_upgrade` (`r2db_api/ops.py`'s own docstring: "レジスタ済みだが未
    provision の application は SKIP として報告する...operator が名指し
    した時だけ"). Before this fix the SAME `database_name IS NOT NULL`
    filter applied to both branches, so `--application <never-
    provisioned-id>` silently returned ZERO rows -- indistinguishable
    from `--application <id-not-registered-at-all>` -- and both `cmd_
    upgrade_applications`/`cmd_upgrade_status` then reported success with
    NO output at all, instead of `_die`ing (a registered-nothing id) or
    reporting a `database_name=None` skip row (design D-4(d) / D-5's own
    "database_nameがNULLの場合はappliedを[]とする"). `_die`s HERE (mirrors
    r2db-api's own identically-placed check in its own `_registry_
    applications_for_upgrade`) when an explicitly-named application
    matches no registry row at all, so BOTH callers get the fix at once.

    Returns `(application_id, database_name, developer_role)` rows, the
    latter two `None` for a registered-but-never-provisioned application
    (`database_name`, in turn, is `None` only when the row itself was
    never assigned one by `finish_provision_application` -- `developer_
    role` is `UNIQUE`, non-nullable in the schema, but is read as `NULL`
    here anyway when no row at all comes back, never dereferenced by a
    caller that already checked `database_name is None` first). Ordered
    by `application_id` for deterministic output."""
    table = sql.Identifier(schema, "applications")
    if application_id is None:
        statement = sql.SQL(
            "SELECT application_id, database_name, developer_role FROM {table} "
            "WHERE database_name IS NOT NULL ORDER BY application_id"
        ).format(table=table)
        params: tuple = ()
    else:
        statement = sql.SQL(
            "SELECT application_id, database_name, developer_role FROM {table} "
            "WHERE application_id = %s"
        ).format(table=table)
        params = (application_id,)
    with conn.cursor() as cur:
        cur.execute(statement, params)
        rows = cur.fetchall()
    if application_id is not None and not rows:
        _die(f"application {application_id!r} is not registered")
    return rows


def _run_upgrade_script(provision_dsn: str, script: Path, application_id: str) -> tuple[bool, str]:
    """Design D-4(b): the `psql` subprocess call shape this peer newly
    carries (`MitateDB-api/src/mitatedb_api/ops.py::_run_deprovision_
    script`'s own call shape, followed here -- never `_die`, which would
    exit immediately and stop this command from reaching the REST of the
    applications it must still visit, design D-4(c)/禁止事項 16).

    Connects with the PLATFORM `provision_dsn` -- never the app-database-
    swapped `_app_dsn` (that swap is for the PYTHON-side ledger reads
    only, `_upgrade_one_application`'s own `read_applied_upgrade_numbers`
    calls). Every per-application upgrade script (`0006`/`0008`, design
    §1.5 の 5) starts by resolving `database_name` from `mitatedb_
    registry.applications` and then `\\c`-ing to it itself -- exactly the
    same shape `_run_deprovision_script` already follows for `0004`,
    which also expects to start out connected to the PLATFORM database."""
    result = subprocess.run(
        ["psql", provision_dsn, "-v", "ON_ERROR_STOP=1",
         "-v", f"{platform_upgrades.UPGRADE_SCRIPT_VARIABLE}={application_id}", "-f", str(script)],
        capture_output=True, text=True,
    )
    return result.returncode == 0, f"{result.stdout}\n{result.stderr}"


def _upgrade_one_application(
    *, provision_dsn: str, provision_role: str, application_id: str, database_name: str, developer_role: str,
    migrations_by_number: dict[int, Path], script_filter: Optional[int], dry_run: bool,
) -> platform_upgrades.ApplicationUpgradeResult:
    """Design D-4(b)/(c)/(d): one application's own full upgrade cycle --
    read the ledger, apply every pending number in ascending order (or
    only `script_filter`, if given and itself pending -- design D-4(a):
    a `script_filter` already recorded is `skipped`, still a SUCCESS, not
    an error), stopping at the first FAILURE for this DB only (never
    aborting the caller's own per-application loop, design D-4(c)). A
    `psycopg.Error` reaching this application's own database (unreachable,
    dropped, or otherwise refusing the connection) is treated as this
    application's own single failure -- every number this package still
    expects is reported `failed`, never silently excluded from the
    output (design §1.5 の 8's own "対象外の application は ops 側が
    registry の database_name で絞る" applies BEFORE this function is
    ever called; a `database_name` that IS set but no longer resolves to
    a live database is a real operational failure, not an exclusion)."""
    app_dsn = _app_dsn(provision_dsn, database_name)
    failed: list[int] = []
    skipped: list[int] = []
    applied_now: list[int] = []
    failure_detail: Optional[str] = None

    try:
        conn = psycopg.connect(app_dsn)
    except psycopg.Error as exc:
        applied_before: tuple[int, ...] = ()
        pending_full = tuple(sorted(platform_upgrades.PLATFORM_UPGRADE_NUMBERS))
        failed = list(pending_full)
        cleanup_sql = f'REVOKE "{developer_role}" FROM "{provision_role}";'
        return platform_upgrades.ApplicationUpgradeResult(
            application_id=application_id, database_name=database_name, applied_before=applied_before,
            applied_after=applied_before, pending_after=pending_full, failed=tuple(failed), skipped=(),
            cleanup_sql=cleanup_sql, failure_detail=str(exc),
        )

    try:
        applied_before_set = platform_upgrades.read_applied_upgrade_numbers(
            conn, ledger_table_name=platform_upgrades.LEDGER_TABLE_NAME)
        conn.rollback()
        applied_before = tuple(sorted(applied_before_set)) if applied_before_set is not None else ()
        pending_full = platform_upgrades.pending_upgrade_numbers(applied_before_set, platform_upgrades.PLATFORM_UPGRADE_NUMBERS)

        if not dry_run:
            if script_filter is not None:
                to_apply: tuple[int, ...] = (script_filter,) if script_filter in pending_full else ()
                if script_filter not in pending_full:
                    skipped.append(script_filter)
            else:
                to_apply = pending_full
            for number in to_apply:
                script = migrations_by_number.get(number)
                if script is None:
                    failed.append(number)
                    break
                ok, output = _run_upgrade_script(provision_dsn, script, application_id)
                if ok:
                    applied_now.append(number)
                else:
                    failed.append(number)
                    # M-3 (supervisor ruling 2026-09-05, review): the
                    # failed psql invocation's own stdout+stderr (`_run_
                    # upgrade_script`'s own return) is the ONLY place the
                    # actual PostgreSQL error text lives -- before this
                    # fix it was bound to `_output` and dropped, leaving
                    # an operator staring at "FAILED to apply: [N]" with
                    # no way to learn WHY short of re-running the script
                    # by hand. Tail only (last ~20 lines): `psql`'s own
                    # `ON_ERROR_STOP=1` failure text is short, and this
                    # application's own summary line must not be buried
                    # under an unrelated wall of output for a script that
                    # fails early with a long preamble already printed.
                    failure_detail = "\n".join(output.splitlines()[-20:])
                    break

        applied_after_set = platform_upgrades.read_applied_upgrade_numbers(
            conn, ledger_table_name=platform_upgrades.LEDGER_TABLE_NAME)
        conn.rollback()
    finally:
        conn.close()

    applied_after = tuple(sorted(applied_after_set)) if applied_after_set is not None else ()
    pending_after = platform_upgrades.pending_upgrade_numbers(applied_after_set, platform_upgrades.PLATFORM_UPGRADE_NUMBERS)
    cleanup_sql = f'REVOKE "{developer_role}" FROM "{provision_role}";' if failed else None
    return platform_upgrades.ApplicationUpgradeResult(
        application_id=application_id, database_name=database_name, applied_before=applied_before,
        applied_after=applied_after, pending_after=pending_after, failed=tuple(failed), skipped=tuple(skipped),
        cleanup_sql=cleanup_sql, failure_detail=failure_detail,
    )


def _print_upgrade_results(results: Sequence[platform_upgrades.ApplicationUpgradeResult], *, dry_run: bool) -> None:
    """Design D-4(d): one line per application (`applied_before` ->
    `applied_after` / `pending`), a separate `skipped` block (design
    D-4(d): "psql の `\\q` skip は exit 0 で返り成功と区別できないため、
    無音で成功に見える経路を出力側で閉じる"), the `REVOKE` cleanup line
    for every application that failed (design D-4(c)), and a trailing
    success/failure/skip tally.

    Counting rule (supervisor ruling U-1, 2026-09-05, 差し戻し後 delta
    監査), unified with r2db-api's own same-shaped tally: each
    application lands in EXACTLY one bucket. `failed` always wins first
    -- this INCLUDES `database_name is None` (M-1/M-2(d)) even under
    `--dry-run`, where `result.failed` itself is deliberately left empty
    (so `summarize_upgrade_run`'s own exit code stays `4`, never `3`, for
    a dry run) -- the tally line is a separate, purely descriptive
    surface, so it counts a never-provisioned application as failed
    regardless. Otherwise, an application whose own `applied_after` came
    back identical to its own `applied_before` actually applied NOTHING
    this run (either nothing was pending at all, or `--script` named a
    number this application's own ledger already recorded) -- that is
    "skipped" (未適用なし、既に記録済み), never "succeeded" (which
    requires having actually run and applied at least one upgrade). The
    prior form instead counted `succeeded` as simply "not failed" and
    `skipped` from `result.skipped` (populated ONLY by the
    `--script`-already-recorded path) INDEPENDENTLY -- a row could be
    counted in BOTH `succeeded` and `skipped` at once, and a
    fully-caught-up application in a bulk (non-`--script`) run was
    counted "succeeded" despite having applied nothing."""
    succeeded = 0
    failed_count = 0
    skipped_count = 0
    for result in results:
        print(
            f"application {result.application_id} (database {result.database_name}): "
            f"applied_before={list(result.applied_before)} applied_after={list(result.applied_after)} "
            f"pending={list(result.pending_after)}"
        )
        if result.skipped:
            print(f"  skipped (already recorded): {list(result.skipped)}")
        if result.failed:
            print(f"  FAILED to apply: {list(result.failed)}")
            if result.failure_detail is not None:
                # M-3 (supervisor ruling 2026-09-05, review): psql's own
                # stderr tail, folded into THIS application's own output
                # block, before the cleanup line (diagnosis before
                # remedy) -- see `_upgrade_one_application`'s own comment
                # for why only the tail.
                print(f"  psql stderr (tail):")
                for line in result.failure_detail.splitlines():
                    print(f"    {line}")
            if result.cleanup_sql:
                print(f"  cleanup: {result.cleanup_sql}")
        if result.failed or result.database_name is None:
            failed_count += 1
        elif result.applied_after == result.applied_before:
            skipped_count += 1
        else:
            succeeded += 1
    verb = "would apply" if dry_run else "applied"
    print(f"{succeeded} succeeded, {failed_count} failed, {skipped_count} skipped ({verb})")


def cmd_upgrade_applications(args: argparse.Namespace) -> int:
    """Design D-4: bulk-applies every pending per-application upgrade
    (design §8: `PLATFORM_UPGRADE_NUMBERS` = {6, 8, 9} -- `9` added by
    Phase 9 WP-3a's own `field_constraints` upgrade script; this
    function needed no change of its own for that addition, since it is
    driven entirely by `PLATFORM_UPGRADE_NUMBERS`/`discover_upgrade_
    scripts` (both data, `platform_upgrades.py`), never a number
    hardcoded here) across every
    provisioned application, or one (`--application`), or one SCRIPT
    across every application still missing it (`--script`, design
    D-4(a): only applied to a database that has not yet recorded it --
    an already-recorded database is `skipped`, still counted a success).
    `--dry-run` applies nothing, reporting the same applied/pending
    tally `upgrade-status` reports. Requires `MITATEDB_PROVISION_DSN`
    only -- never a control credential (SI-02)."""
    provision_dsn = _provision_dsn()
    schema = _schema()
    migrations_by_number = platform_upgrades.discover_upgrade_scripts(_migrations_dir())
    # M-2(b)/(c) fix (supervisor ruling 2026-09-05, review): an explicit
    # `--script <N>` naming a number with no corresponding file under
    # `_migrations_dir()` is a USAGE error (mirrors r2db-api's own
    # identically-placed check) -- checked HERE, before any application
    # is ever visited, never left to `_upgrade_one_application`'s own
    # per-application loop. Before this fix, `N not in migrations_by_
    # number` (true for EVERY `N` not in `PLATFORM_UPGRADE_NUMBERS`, since
    # no per-application upgrade script can be named for a number this
    # package does not know about, and also true for a number this
    # package DOES know about whose own file is simply missing from
    # `_migrations_dir()`) silently fell through to `_upgrade_one_
    # application`'s own `script_filter not in pending_full` branch,
    # which reports `skipped (already recorded)` -- a FALSE report of
    # success design D-4(a) never intended for a number outside its own
    # per-application-upgrade vocabulary entirely (the ruling's own
    # explicit prohibition: "「skipped (already recorded)」の偽報告は
    # 禁止"). `--dry-run` is exempt (it applies nothing regardless of
    # `--script`, so a missing script file changes nothing about its own
    # report -- mirrors r2db-api's own identical `not args.dry_run` guard).
    if args.script is not None and not args.dry_run and args.script not in migrations_by_number:
        _die(f"no per-application upgrade script found for upgrade number {args.script} under {_migrations_dir()}")
    conn = psycopg.connect(provision_dsn)
    try:
        provision_role = conninfo_to_dict(provision_dsn).get("user") or conn.info.user
        rows = _registry_applications_for_upgrade(conn, schema=schema, application_id=args.application)
    finally:
        conn.close()

    results = []
    for application_id, database_name, developer_role in rows:
        if database_name is None:
            # M-1/M-2(d) fix (supervisor ruling 2026-09-05): a REGISTERED
            # but never-provisioned application, reachable only via an
            # explicit `--application <id>` (the default enumeration
            # already excludes these rows entirely). `pending_after` is
            # always every number this package requires (nothing could
            # possibly have been applied to a database that does not
            # exist) -- alone enough to make `--dry-run` return `4`
            # (mirrors `cmd_upgrade_status` below). `failed` is populated
            # the SAME way, but ONLY for a real (non-dry-run) invocation
            # -- D-4(e)'s own exit-code table names `database_name`がNULL
            # explicitly as one of the two conditions exit code `3`
            # covers ("psql exit 3、または`database_name`がNULL"); this is
            # what makes `summarize_upgrade_run` below -- UNMODIFIED,
            # still the exact same pinned pure function -- return `3` for
            # this case on its own. A `--dry-run` never "fails" anything
            # (nothing is attempted), so `failed` stays empty there.
            all_numbers = tuple(sorted(platform_upgrades.PLATFORM_UPGRADE_NUMBERS))
            results.append(platform_upgrades.ApplicationUpgradeResult(
                application_id=application_id, database_name=None, applied_before=(),
                applied_after=(), pending_after=all_numbers,
                failed=() if args.dry_run else all_numbers, skipped=(), cleanup_sql=None,
            ))
            continue
        results.append(_upgrade_one_application(
            provision_dsn=provision_dsn, provision_role=provision_role, application_id=application_id,
            database_name=database_name, developer_role=developer_role, migrations_by_number=migrations_by_number,
            script_filter=args.script, dry_run=args.dry_run,
        ))
    _print_upgrade_results(results, dry_run=args.dry_run)
    return platform_upgrades.summarize_upgrade_run(results, dry_run=args.dry_run)


def cmd_upgrade_status(args: argparse.Namespace) -> int:
    """Design D-5: read-only equivalent of `upgrade-applications
    --dry-run` -- provision DSN only, `applied`/`pending`/`database_name`
    per application. Never touches the existing `list-applications`
    command (design D-5: contract shape `ApplicationsResult` unchanged) --
    this is an entirely separate, peer-local-only surface (U-1)."""
    provision_dsn = _provision_dsn()
    schema = _schema()
    conn = psycopg.connect(provision_dsn)
    try:
        rows = _registry_applications_for_upgrade(conn, schema=schema, application_id=args.application)
    finally:
        conn.close()

    results = []
    for application_id, database_name, _developer_role in rows:
        if database_name is None:
            # M-2(d) fix (supervisor ruling 2026-09-05): a REGISTERED but
            # never-provisioned application, reachable only via an
            # explicit `--application <id>` (the default enumeration
            # already excludes these rows entirely) -- reported as
            # `applied=[]`/every number pending (design D-5: "台帳が無い
            # applicationはapplied=[]とする", the SAME treatment as no
            # ledger table at all), never a crash from `_app_dsn(...,
            # None)` (a `None` `dbname` is not a valid connection param).
            results.append(platform_upgrades.ApplicationUpgradeResult(
                application_id=application_id, database_name=None, applied_before=(),
                applied_after=(), pending_after=tuple(sorted(platform_upgrades.PLATFORM_UPGRADE_NUMBERS)),
                failed=(), skipped=(), cleanup_sql=None,
            ))
            continue
        app_dsn = _app_dsn(provision_dsn, database_name)
        try:
            app_conn = psycopg.connect(app_dsn)
        except psycopg.Error:
            applied: tuple[int, ...] = ()
            pending = tuple(sorted(platform_upgrades.PLATFORM_UPGRADE_NUMBERS))
        else:
            try:
                applied_set = platform_upgrades.read_applied_upgrade_numbers(
                    app_conn, ledger_table_name=platform_upgrades.LEDGER_TABLE_NAME)
                app_conn.rollback()
            finally:
                app_conn.close()
            applied = tuple(sorted(applied_set)) if applied_set is not None else ()
            pending = platform_upgrades.pending_upgrade_numbers(applied_set, platform_upgrades.PLATFORM_UPGRADE_NUMBERS)
        results.append(platform_upgrades.ApplicationUpgradeResult(
            application_id=application_id, database_name=database_name, applied_before=applied,
            applied_after=applied, pending_after=pending, failed=(), skipped=(), cleanup_sql=None,
        ))

    for result in results:
        print(
            f"application {result.application_id} (database {result.database_name}): "
            f"applied={list(result.applied_after)} pending={list(result.pending_after)}"
        )
    return platform_upgrades.summarize_upgrade_run(results, dry_run=True)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m mitatedb_api.ops",
        description=(
            "MitateDB-api out-of-band control-plane ceremony CLI (design v1.2 R-6) -- the bootstrap/reset "
            "control-credential ritual; no other issuance path for a role=control credential exists anywhere "
            "on this peer, in-band or out."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser(
        "bootstrap",
        help="issue the very first control credential (refused with CONFLICT if any control credential row "
             "already exists, including revoked ones -- use `reset` to recover)",
    )
    p.set_defaults(func=cmd_bootstrap)

    p = sub.add_parser(
        "reset",
        help="revoke every existing control credential and issue one new one, atomically -- the canonical "
             "recovery from a lost/leaked/lockout control credential. Requires --confirm <phrase> (echoing a "
             "prior refusal's own required_confirmation) -- omit or get it wrong and the declaration prints "
             "to stderr as JSON and this exits 2 without committing anything",
    )
    p.add_argument(
        "--confirm", default=None, metavar="PHRASE",
        help="echo the required_confirmation phrase from a prior refusal's stderr declaration to proceed",
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
        "freeze-issuance",
        help="freeze credential issuance for an application (out-of-band; issue-credential against it then "
             "refuses with FORBIDDEN) -- non-destructive, no confirmation gate",
    )
    p.add_argument("application_id")
    p.set_defaults(func=cmd_freeze_issuance)

    p = sub.add_parser(
        "unfreeze-issuance",
        help="lift a credential-issuance freeze for an application",
    )
    p.add_argument("application_id")
    p.set_defaults(func=cmd_unfreeze_issuance)

    # ---- WP-6 break-glass command family ---------------------------------
    # Every subcommand below (except audit-report/deprovision, neither of
    # which is a ControlPlaneService call -- see this module's own
    # docstring) authenticates through the SAME ControlPlaneService
    # /control/v1 itself uses, via MITATEDB_CONTROL_CREDENTIAL_ID/_SECRET
    # (the operator's own live control credential).

    p = sub.add_parser("list-applications", help="list registered applications (break-glass)")
    p.set_defaults(func=cmd_list_applications)

    p = sub.add_parser(
        "list-credentials",
        help="list application AND control credentials (contract's own mixed listing) (break-glass)",
    )
    p.set_defaults(func=cmd_list_credentials)

    p = sub.add_parser("enable-application", help="re-enable a previously disabled application (break-glass)")
    p.add_argument("application_id")
    p.set_defaults(func=cmd_enable_application)

    p = sub.add_parser(
        "disable-application",
        help="disable an application -- every one of its credentials is refused, reversible with "
             "enable-application (break-glass)",
    )
    p.add_argument("application_id")
    p.set_defaults(func=cmd_disable_application)

    p = sub.add_parser(
        "enable-credential",
        help="re-enable a previously disabled credential (application or control) -- never un-revokes "
             "(break-glass)",
    )
    p.add_argument("credential_id")
    p.set_defaults(func=cmd_enable_credential)

    p = sub.add_parser(
        "disable-credential",
        help="temporarily disable a credential (application or control), reversible with enable-credential "
             "(break-glass)",
    )
    p.add_argument("credential_id")
    p.set_defaults(func=cmd_disable_credential)

    p = sub.add_parser(
        "rotate-credential",
        help="replace an existing credential's secret (application or control; new secret printed once) "
             "(break-glass)",
    )
    p.add_argument("credential_id")
    p.set_defaults(func=cmd_rotate_credential)

    p = sub.add_parser(
        "revoke-credential",
        help="permanently revoke a credential (application or control). Revoking the LAST active control "
             "credential requires --confirm <phrase> (echoing a prior refusal's own required_confirmation) "
             "(break-glass)",
    )
    p.add_argument("credential_id")
    p.add_argument(
        "--confirm", default=None, metavar="PHRASE",
        help="echo the required_confirmation phrase from a prior refusal's stderr declaration -- only "
             "consulted when the target is the last remaining active control credential",
    )
    p.set_defaults(func=cmd_revoke_credential)

    p = sub.add_parser(
        "audit-report",
        help="print durable control_audit rows as JSON Lines, oldest first (read-only; requires "
             "MITATEDB_PROVISION_DSN -- the control-plane role itself is INSERT-only and cannot read this "
             "table back) (break-glass)",
    )
    p.add_argument("--since", default=None, metavar="ISO8601", help="only rows with occurred_at >= this timestamp")
    p.add_argument("--until", default=None, metavar="ISO8601", help="only rows with occurred_at <= this timestamp")
    p.set_defaults(func=cmd_audit_report)

    p = sub.add_parser(
        "deprovision",
        help="permanently remove an application's entire database, both its login roles, and its registry "
             "rows -- the terminal, whole-namespace removal (design R-1/R-6). Requires --confirm <phrase> "
             "(echoing a prior refusal's own required_confirmation) -- omit or get it wrong and the "
             "declaration prints to stderr as JSON and this exits 2 without dropping anything. Requires "
             "MITATEDB_PROVISION_DSN (break-glass)",
    )
    p.add_argument("application_id")
    p.add_argument(
        "--confirm", default=None, metavar="PHRASE",
        help="echo the required_confirmation phrase from a prior refusal's stderr declaration to proceed",
    )
    p.set_defaults(func=cmd_deprovision)

    # ---- Q4 phase declaration-management command family (design D-1/D-2)
    # -- provision DSN only, no control credential needed for any of these
    # (`MITATEDB_PROVISION_DSN`, the same env var `deprovision`/`audit-
    # report` above already require).

    p = sub.add_parser(
        "set-platform-timeouts",
        help="set BOTH service writer roles' statement_timeout / idle_in_transaction_session_timeout as "
             "PostgreSQL role settings (design D-1(a)) -- one pair of values for both mitatedbsvc_api and "
             "mitatedbsvc_controlplane, no per-role override. Rejects 0 and negative values. Requires "
             "MITATEDB_PROVISION_DSN. Restart both processes afterward (D-1(e): startup snapshot)",
    )
    p.add_argument("--statement-ms", type=int, required=True, metavar="N")
    p.add_argument("--idle-ms", type=int, required=True, metavar="N")
    p.set_defaults(func=cmd_set_platform_timeouts)

    p = sub.add_parser(
        "declare-surfaces",
        help="declare the single, shared `surfaces` row both processes read (design D-2) -- REPLACES the "
             "entire row. --control-base-url is OPTIONAL (omit it to declare no control surface); "
             "--no-control is an explicit, equivalent form of that same omission (supervisor ruling "
             "correction 2026-09-05). Passing both is a usage error. Requires MITATEDB_PROVISION_DSN. "
             "Restart both processes afterward (D-2(g): startup snapshot)",
    )
    p.add_argument("--data-base-url", required=True, metavar="URL")
    control_group = p.add_mutually_exclusive_group(required=False)
    control_group.add_argument("--control-base-url", default=None, metavar="URL")
    control_group.add_argument("--no-control", dest="control_base_url", action="store_const", const=None)
    p.set_defaults(func=cmd_declare_surfaces)

    p = sub.add_parser(
        "declare-coalescing-window",
        help="declare `audit_coalescing_window_ms` (design D-2) -- a non-negative integer, 0 meaning no "
             "coalescing. Requires MITATEDB_PROVISION_DSN. Restart both processes afterward (D-2(g): startup "
             "snapshot)",
    )
    p.add_argument("--ms", type=int, required=True, metavar="N")
    p.set_defaults(func=cmd_declare_coalescing_window)

    p = sub.add_parser(
        "show-declarations",
        help="print the current platform_declarations row contents and both service writer roles' "
             "pg_db_role_setting declarations (read-only diagnostic; shows raw values, including a malformed "
             "hand-edited one -- does not itself enforce startup validation). Requires MITATEDB_PROVISION_DSN",
    )
    p.set_defaults(func=cmd_show_declarations)

    p = sub.add_parser(
        "verify-declarations",
        help=(
            "Phase 8 R-11: machine-checkable check of whether this process' declared platform state (as seen "
            "from the provision DSN) allows it to start -- one line per check, exit code identifies the first "
            "failing F-number (see docs/design/PHASE8_EFFECTIVE_BOUNDS_AND_HYGIENE_V1.md D-5)"
        ),
    )
    p.add_argument("--control", action="store_true", help="also check F-3c (surfaces.control must be declared for a control-plane process)")
    p.set_defaults(func=cmd_verify_declarations)

    # ---- Q4 phase per-application platform-upgrade command family
    # (design D-4/D-5) -- provision DSN only, same as the declaration
    # family above.

    p = sub.add_parser(
        "upgrade-applications",
        help="bulk-apply every pending per-application platform upgrade across every provisioned application "
             "(or one, --application), or apply one script to every database still missing it (--script, "
             "skipping databases that already recorded it). --dry-run applies nothing, reporting the same "
             "applied/pending tally as upgrade-status. Does not stop at the first failed database -- every "
             "database is visited, failures are listed with a REVOKE cleanup line. Requires "
             "MITATEDB_PROVISION_DSN",
    )
    p.add_argument("--application", default=None, metavar="ID", help="limit to one application id")
    p.add_argument("--script", type=int, default=None, metavar="NNNN", help="limit to one upgrade number")
    p.add_argument("--dry-run", action="store_true", help="report applied/pending only, apply nothing")
    p.set_defaults(func=cmd_upgrade_applications)

    p = sub.add_parser(
        "upgrade-status",
        help="read-only per-application platform-upgrade applied/pending tally (design D-5) -- the sole "
             "peer-local visualization U-1 permits; never mounted on any HTTP surface. Does not change or "
             "replace list-applications. Requires MITATEDB_PROVISION_DSN",
    )
    p.add_argument("--application", default=None, metavar="ID", help="limit to one application id")
    p.set_defaults(func=cmd_upgrade_status)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except FoundationError as exc:
        # One line of JSON on stderr, uniformly for EVERY `FoundationError`
        # (not only `DestructiveConfirmationRequired`'s own declare-and-echo
        # case above) -- a stable machine interface (`code`/`message`) a
        # subprocess caller (the HTTP conformance adapter's own `python -m
        # mitatedb_api.ops bootstrap`/`reset` invocation, R-8) can parse
        # reliably, rather than pattern-matching this module's own
        # free-text wording. Exit 1 (not 2, which this module reserves
        # exclusively for the declare-and-echo gate's own refusal).
        print(json.dumps({"code": _classify(exc), "message": str(exc)}), file=sys.stderr)
        return 1
    except psycopg.Error as exc:
        print(f"error: database operation failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
