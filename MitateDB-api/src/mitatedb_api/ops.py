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
from typing import NoReturn, Sequence

import psycopg
from psycopg import sql

from .control_audit import insert_control_audit_row, read_control_audit_events
from .control_composition import build_control_service
from .control_credential_store_postgres import DEFAULT_SCHEMA, PostgresControlCredentialStore
from .control_plane import (_APPLICATION_ID_PATTERN, PostgresApplicationRegistry,
                            bootstrap_control_credential, issue_audit_credential_ceremony,
                            reset_control_credentials)
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
