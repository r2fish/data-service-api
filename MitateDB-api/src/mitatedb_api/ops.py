"""MitateDB-api out-of-band control-plane ceremony CLI: ``python -m
mitatedb_api.ops``.

Design v1.2 R-6 ("bootstrap / reset は out-of-band CLI...CLI entry point (`ops`
module) の新設は WP-5 の flip コミットに置く", second-round M-5): WP-4 built the reusable
ceremony CORE (`control_plane.bootstrap_control_credential` /
`reset_control_credentials`) but deliberately shipped no CLI at all -- building
one earlier would have made the in-process conformance adapter's own
`bootstrap`/`reset` port operations' `SurfaceAbsent` claim an actual falsehood
("a real CLI exists, yet the adapter claims absence"). This module is the
flip's own CLI half, landing in the exact same commit as the `/control/v1`
mount (`control_main.py`) and the `control_plane` capability declaration flip
(`cell.py` reading `config.control_plane_status`).

Scope (deliberately narrower than r2db-api's sibling `r2db_api.ops`, which also
carries a large break-glass command set accumulated over several later work
packages): this WP's own instruction is exactly ``python -m mitatedb_api.ops
bootstrap`` and ``... reset`` -- the two operations contract
`control_plane.bootstrap`/`control_plane.reset` require to exist ONLY
out-of-band, with no in-band substitute of any kind (R-6: "いかなる HTTP surface
からも role=control 発行はできない"). Both subcommands call the SAME reusable ceremony
core WP-4 already built and directly tested
(`bootstrap_control_credential`/`reset_control_credentials`,
`control_plane.py`) against a real
`PostgresControlCredentialStore` -- this module supplies the store, the
audit-append wire-up, and the process/argv boundary; it invents no ceremony
logic of its own (R-6's own instruction: "儀式意味論の正本は再利用可能な product code に置き、CLI
と in-process adapter の双方が同一コアを呼ぶ").

Declare-and-echo (contract `destructive_confirmation`, design R-6): ``reset`` is
this CLI's one genuinely destructive subcommand. Unlike r2db-api's own CLI
(which re-implements a client-side confirmation gate,
``_require_cli_confirmation``, ahead of the ceremony call), this module needs
none of that: `reset_control_credentials` itself already recomputes the current
confirmation phrase and raises `errors.DestructiveConfirmationRequired` --
carrying
`details.required_confirmation`/`consequence`/`reversible_alternative`/`recovery`
-- BEFORE writing anything, whenever `destructive` is not exactly `True` or
`confirmation` does not exactly match (contract: no truthy/prefix acceptance).
Running `reset` at all already **is** the destructive intent signal a wire
request's own `destructive: true` field stands in for (same reasoning
r2db-api's own CLI docstring gives for its own subcommands), so this CLI always
passes `destructive=True` and forwards whatever `--confirm` the operator
supplied (or `None`) as `confirmation` -- the ceremony core's own gate does the
rest. On that denial, this module prints the declaration as one line of JSON to
stderr and exits 2, touching the platform database not at all beyond the read
the gate itself needed (the ceremony core's own `locked_for_update` runs inside
the SAME transaction this module opens, which is rolled back, never committed,
when the gate denies).

``bootstrap`` carries no such gate (contract: a second bootstrap while any
control-credential row exists -- including a fully revoked one -- is a
plain `CONFLICT`, never a confirmation matter; recovery from that state is
always `reset`, never a second `bootstrap`).

Ritual concurrency (mirrors r2db-api's own `ops.py::_lock_ritual`,
independently applied here for this peer's own advisory-lock key): both subcommands take a `pg_advisory_xact_lock`
before their own existence check, closing the TOCTOU gap between "no
control-credential row exists yet" and this process' own `INSERT` -- released
automatically when the surrounding transaction commits or rolls back.

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
names -- `list-applications`/`list-credentials`,
`enable-application`/`disable-application`,
`enable-credential`/`disable-credential`, `rotate-credential`,
`revoke-credential`, `audit-report`, and `deprovision`. Unlike
`bootstrap`/`reset` (which mint/replace the control credential set itself and
therefore call the ceremony CORE functions directly, with no principal to
authenticate), every one of these commands is an ordinary `/control/v1`-shaped
operation an authenticated control credential performs -- so this module builds
the SAME `ControlPlaneService` `control_main.build_control_app` mounts behind
HTTP (`control_composition.build_control_service`) and calls its public methods
directly, never re-implementing shape/authn/authz/must_rotate-gate/bounds/audit
logic a second time (R-6's own "儀式意味論の正本は再利用可能な product code に置き" principle,
extended here from the bootstrap/reset ceremony to this command family too --
unlike r2db-api's own sibling `ops.py`, which predates its own
`ControlPlaneService`-equivalent and so re-implements these operations against
raw SQL; this module deliberately does not repeat that duplication now that the
reusable service exists). This is genuinely a BREAK-GLASS path, not a second
public API: it exists for an operator who holds a live control credential's
id/secret (freshly minted by `reset`, or already on file) but cannot reach
`/control/v1` over the network (a Cloud Run outage, a locked-down environment,
or the control service deliberately stopped per the compromise playbook) while
the platform database itself is still reachable --
`MITATEDB_CONTROL_CREDENTIAL_ID`/`MITATEDB_CONTROL_CREDENTIAL_SECRET` supply
that credential exactly as an `Authorization` header would over HTTP. A
`must_rotate` credential can still do nothing here besides
self-`rotate-credential` (`ControlPlaneService._gate_must_rotate`'s own
allow-list, unchanged by this module).

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

History: CH-0408
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import NoReturn, Optional, Sequence

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.types.json import Json

from . import pg_timeouts
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
    # The secret is shown exactly once, here, and is never written
    # anywhere by this process -- copy it now, it cannot be recovered
    # later.
    #
    # Phase 6 WP-3 追補 (brief item A): every caller of this
    # function (`cmd_bootstrap`/`cmd_reset` via `_print_issued`,
    # `cmd_issue_audit_credential`, `cmd_rotate_credential`) now hands it
    # the already-COMPOSED bearer its own ceremony/service call returned
    # (`bootstrap_control_credential`/`reset_control_credentials`/`issue_audit_credential_ceremony`/`ControlPlaneService.rotate_credential`
    # all compose at their own store/service layer now, reversing this
    # function's earlier role as the single composition choke point --
    # see those functions' own docstrings). This function prints it
    # VERBATIM; no composition happens here any more. `credential_id:`
    # stays a separate line -- an operator who only needs the id (e.g. to
    # build a rotate URL) never has to parse it back out of the bearer.
    # history: CH-0411
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

    `MITATEDB_CONTROL_CREDENTIAL_SECRET` holds the operator's own saved,
    COMPOSED bearer -- the exact `secret:` value
    `bootstrap`/`reset`/`rotate-credential` printed (this module's own
    runbook, cloud-run-cloud-sql.md §7: "the operator's own live,
    already-rotated control credential", the SAME value shape a real
    `Authorization` header would carry). This CLI never splits the bearer
    itself -- exactly like `control_http.py`'s own HTTP boundary, it passes
    the presented bearer straight through to `ControlPlaneService`, which
    forwards it unchanged to
    `control_auth.ControlCredentialStore.authenticate`/`control_credential_store_postgres.PostgresControlCredentialStore.authenticate`,
    the single choke point that calls `split_bearer_locator` exactly once.
    `MITATEDB_CONTROL_CREDENTIAL_ID` is still required here (an early,
    operator-facing sanity check -- a saved secret with no matching saved
    id most likely means the operator's own record-keeping drifted) even
    though its value is no longer read: the bearer's own locator half
    already names the credential_id the store actually authenticates
    against.

    History: CH-0413
    """
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
    """`ControlPlaneService.revoke_credential`'s own built-in declare-and-echo
    gate fires only when the target is the LAST remaining active control
    credential -- an application credential's revocation is never gated
    (contract `non_destructive_requests`) and this call simply succeeds.
    `destructive=True` unconditionally: running this CLI command at all
    already is the destructive-intent signal (identical reasoning to
    `cmd_reset` above), `--confirm` supplies `confirmation` (`None` if
    omitted, which never matches a real phrase).

    History: CH-0414
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
    INSERT-only on this table and cannot read it back; a control credential
    (`MITATEDB_CONTROL_CREDENTIAL_ID`/`_SECRET`) is not needed or used here
    at all.

    History: CH-0415
    """
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


#: design D-2: the complete set of `conninfo_to_dict` keys that have a
#: known libpq (PostgreSQL 16) environment-variable form -- every psql
#: subprocess invocation below carries its connection parameters through
#: exactly these variables, never argv. A DSN key outside this table is
#: rejected outright (`_psql_connection_env` calls `_die`) rather than
#: silently dropped, which would let the connection fall back to libpq's
#: own default for that parameter unnoticed. Source: local PostgreSQL 16
#: libpq documentation, "Environment Variables" (the first, connection-
#: parameter-default group only -- the later PGDATESTYLE/PGTZ/PGGEQO/
#: PGSYSCONFDIR/PGLOCALEDIR group sets session/library behavior, not a
#: connection parameter, and `PGSERVICEFILE` has no `conninfo` keyword of
#: its own to key this table by).
_LIBPQ_ENV_VAR_FOR_CONNINFO_KEY: dict[str, str] = {
    "host": "PGHOST",
    "hostaddr": "PGHOSTADDR",
    "port": "PGPORT",
    "dbname": "PGDATABASE",
    "user": "PGUSER",
    "password": "PGPASSWORD",
    "passfile": "PGPASSFILE",
    "require_auth": "PGREQUIREAUTH",
    "channel_binding": "PGCHANNELBINDING",
    "service": "PGSERVICE",
    "options": "PGOPTIONS",
    "application_name": "PGAPPNAME",
    "sslmode": "PGSSLMODE",
    "requiressl": "PGREQUIRESSL",
    "sslcompression": "PGSSLCOMPRESSION",
    "sslcert": "PGSSLCERT",
    "sslkey": "PGSSLKEY",
    "sslcertmode": "PGSSLCERTMODE",
    "sslrootcert": "PGSSLROOTCERT",
    "sslcrl": "PGSSLCRL",
    "sslcrldir": "PGSSLCRLDIR",
    "sslsni": "PGSSLSNI",
    "requirepeer": "PGREQUIREPEER",
    "ssl_min_protocol_version": "PGSSLMINPROTOCOLVERSION",
    "ssl_max_protocol_version": "PGSSLMAXPROTOCOLVERSION",
    "gssencmode": "PGGSSENCMODE",
    "krbsrvname": "PGKRBSRVNAME",
    "gsslib": "PGGSSLIB",
    "gssdelegation": "PGGSSDELEGATION",
    "connect_timeout": "PGCONNECT_TIMEOUT",
    "client_encoding": "PGCLIENTENCODING",
    "target_session_attrs": "PGTARGETSESSIONATTRS",
    "load_balance_hosts": "PGLOADBALANCEHOSTS",
}

#: design D-2: `PGSERVICEFILE`/`PGSYSCONFDIR` configure which FILES libpq
#: reads for `service=`/system-wide settings -- connection-relevant, but
#: neither has a `conninfo` keyword of its own, so
#: `_LIBPQ_ENV_VAR_FOR_CONNINFO_KEY`'s own values alone would miss them
#: when checking for a leftover parent setting the DSN cannot override.
_LIBPQ_CONNECTION_ENV_VARS_WITHOUT_A_CONNINFO_KEY: tuple[str, ...] = ("PGSERVICEFILE", "PGSYSCONFDIR")

_PSQL_VERSION_RE = re.compile(r"PostgreSQL\)\s*(\d+)")


def _require_psql_16_or_newer() -> None:
    """design D-2: every psql subprocess invocation below calls this
    first. A psql binary older than PostgreSQL 16, one whose own
    `--version` output this module cannot parse at all, or a psql binary
    not found on `PATH` at all, ends the run via `_die` -- a fixed
    message, never the raw subprocess output."""
    try:
        result = subprocess.run(["psql", "--version"], capture_output=True, text=True)
    except OSError:
        _die("psql binary could not be started; refusing to run a psql subprocess")
    match = _PSQL_VERSION_RE.search(result.stdout)
    if match is None or int(match.group(1)) < 16:
        _die("psql binary is missing, unreadable, or older than PostgreSQL 16; refusing to run a psql subprocess")


#: A PostgreSQL GUC duration -- a positive integer optionally followed by
#: one of PostgreSQL's own `ms`/`s`/`min` unit suffixes -- never `0`
#: (which PostgreSQL itself reads as "no timeout") and never any other
#: unit PostgreSQL also accepts (`h`/`d`), so the CLI's own accepted
#: vocabulary stays a strict subset of PostgreSQL's.
_LOCK_TIMEOUT_VALUE_RE = re.compile(r"^[1-9][0-9]*(ms|s|min)?$")


def _validate_lock_timeout_value(value: str) -> str:
    """Rejects a `--lock-timeout` value that does not match `_LOCK_
    TIMEOUT_VALUE_RE` before it ever reaches a psql subprocess, via the
    same fixed-message `_die` every other usage error in this module
    already uses. The rejected value itself is never echoed back."""
    if not _LOCK_TIMEOUT_VALUE_RE.fullmatch(value):
        _die(
            "--lock-timeout value must be a positive integer optionally "
            "followed by ms, s, or min"
        )
    return value


def _psql_connection_env(dsn: str) -> dict[str, str]:
    """design D-2: builds the environment for a psql subprocess invocation
    from `dsn`'s own connection parameters -- never on argv, which is
    visible to every OTHER user on the host via `ps`/`/proc`, while these
    env vars are visible only to this process, its children, and root.
    The parent process' own `PG*` variables are stripped first, so a DSN
    that omits a parameter never inherits a stray value silently from the
    caller's own environment (e.g. an operator's own `PGPASSWORD` or
    `PGSERVICE` reaching a psql invocation the DSN never asked for). A
    `conninfo_to_dict` key outside `_LIBPQ_ENV_VAR_FOR_CONNINFO_KEY` ends
    the run the same way an existing ops configuration error does, naming
    the key (never a secret) so the operator can act on it. Beyond that,
    if the PARENT process still carries a connection-setting variable
    (this table's own values, or `_LIBPQ_CONNECTION_ENV_VARS_WITHOUT_A_
    CONNINFO_KEY`) that the DSN itself never overrides, the run ends the
    same way, naming the variable -- never its value -- rather than let
    the psql child silently inherit a setting from this process' own
    environment that the DSN never described (fail-closed: psycopg's own
    connection and psql's own connection must agree on every setting).
    Isomorphic with r2db-api's own same-named helper (`r2db_api/ops.py::
    _psql_connection_env`).
    """
    params = conninfo_to_dict(dsn)
    env = {k: v for k, v in os.environ.items() if not k.startswith("PG")}
    dsn_env_names: set[str] = set()
    for key, value in params.items():
        if value in (None, ""):
            continue
        env_name = _LIBPQ_ENV_VAR_FOR_CONNINFO_KEY.get(key)
        if env_name is None:
            _die(
                f"DSN parameter {key!r} has no known libpq (PostgreSQL 16) environment-variable "
                "form; refusing to pass it to a psql subprocess"
            )
        env[env_name] = str(value)
        dsn_env_names.add(env_name)
    leftover = sorted(
        name
        for name in (*_LIBPQ_ENV_VAR_FOR_CONNINFO_KEY.values(), *_LIBPQ_CONNECTION_ENV_VARS_WITHOUT_A_CONNINFO_KEY)
        if name not in dsn_env_names and os.environ.get(name)
    )
    if leftover:
        _die(
            "the following connection-setting environment variable(s) are set in this process' "
            f"own environment but not overridden by the DSN: {', '.join(leftover)}; add the "
            "matching DSN parameter, or unset the variable, before retrying"
        )
    return env

def _redact_connection_values(text: str, dsn: str) -> str:
    """design D-2: replaces every occurrence of a connection-parameter
    VALUE (`user`/`password`/`host`/`hostaddr`/`port`/`dbname`, as
    `conninfo_to_dict` parses `dsn`) with a fixed marker, everywhere it
    occurs in `text` (a raw exception's own `str(exc)`, or a psql
    subprocess's own captured stdout/stderr) -- never a DSN-shaped regex
    guess (design D-2: 推測のマスクはしない). `host`/`hostaddr`/`port` are
    split on `,` first (a multi-host DSN's own conninfo value for these
    three keys is comma-joined, but the raw diagnostic text names each
    host/port separately, never comma-joined, so redacting the joined
    string would silently miss every one of them). Every value is then
    escaped and joined into ONE regular expression, longest value first,
    and substituted in a single pass -- a shorter value that is a literal
    PREFIX of a longer one (e.g. a `user` value that prefixes a `password`
    value) must be matched as part of the LONGER alternative first, or a
    sequential per-value `str.replace` would consume only the shorter
    match and leave the remaining tail of the longer, more sensitive
    value exposed un-redacted. A SQL-level diagnostic (a constraint name,
    a syntax error's own quoted token) is unaffected unless it happens to
    collide with one of these values. Isomorphic with r2db-api's own
    same-named helper (`r2db_api/ops.py::_redact_connection_values`).
    """
    try:
        params = conninfo_to_dict(dsn)
    except psycopg.Error:
        return text
    values: set[str] = set()
    for key in ("user", "password", "host", "hostaddr", "port", "dbname"):
        raw = params.get(key)
        if not raw:
            continue
        raw = str(raw)
        if key in ("host", "hostaddr", "port"):
            values.update(part for part in raw.split(",") if part)
        else:
            values.add(raw)
    if not values:
        return text
    pattern = "|".join(re.escape(v) for v in sorted(values, key=len, reverse=True))
    return re.sub(pattern, "<redacted>", text)


def _with_lock_timeout_option(existing_pgoptions: "str | None", lock_timeout: str) -> str:
    """Appends a `-c lock_timeout=<value>` startup option to `existing_
    pgoptions` (the value `_psql_connection_env`'s own `options`-key
    mapping already placed there, if the DSN itself carried one) rather
    than replacing it -- a DSN-supplied `options` value keeps taking
    effect alongside the lock timeout, never silently dropped."""
    option = f"-c lock_timeout={lock_timeout}"
    if existing_pgoptions:
        return f"{existing_pgoptions} {option}"
    return option


def _run_deprovision_script(dsn: str, application_id: str, lock_timeout: str) -> None:
    script = _migrations_dir() / "0004_deprovision_application.sql"
    if not script.exists():
        _die(f"deprovision script not found at {script} (set MITATEDB_MIGRATIONS_DIR to override)")
    _require_psql_16_or_newer()
    env = _psql_connection_env(dsn)
    env["PGOPTIONS"] = _with_lock_timeout_option(env.get("PGOPTIONS"), lock_timeout)
    result = subprocess.run(
        ["psql", "-v", "ON_ERROR_STOP=1", "-v", f"app_id={application_id}", "-f", str(script)],
        capture_output=True, text=True, env=env,
    )
    if result.returncode != 0:
        _die(_redact_connection_values(f"deprovision script failed:\n{result.stdout}\n{result.stderr}", dsn))


def cmd_deprovision(args: argparse.Namespace) -> int:
    """This module's own second genuinely destructive subcommand (alongside
    `reset`) -- see this module's own docstring for why this is not a
    `ControlPlaneService` call at all, and for the fingerprinted phrase's
    own rationale. `application_id` is format-validated BEFORE any database
    access or phrase computation (mirrors r2db-api's own
    `delete-credential` fix: an unvalidated identifier must never reach a
    confirmation phrase or a shell-adjacent subprocess argument).

    History: CH-0416
    """
    application_id = args.application_id
    if not _APPLICATION_ID_PATTERN.fullmatch(application_id):
        raise ValidationError(f"application_id must match {_APPLICATION_ID_PATTERN.pattern!r}")
    lock_timeout = _validate_lock_timeout_value(args.lock_timeout)
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
    _run_deprovision_script(dsn, application_id, lock_timeout)
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
    advisory lock `bootstrap`/`reset` use (mirrors r2db-api's own lesson,
    applied here for this peer's own lock key): without it, this command's
    `INSERT` could interleave with a concurrent `reset`'s `revoke_all` --
    `revoke_all` only revokes rows its own scan already saw, so an
    audit-credential row inserted mid-reset (after that scan, before
    `reset`'s transaction commits) would survive a reset that was supposed
    to wipe every control-table row. Taking the same lock key serializes
    this command against a concurrent `bootstrap`/`reset`/another
    `issue-audit-credential`, closing that window.

    `issue_audit_credential_ceremony` (`control_plane.py`) does the real
    work -- see that function's own docstring for why it issues AND rotates
    in the same transaction before ever handing back a secret (no in-band
    self-rotate exists for an audit principal, design §4 M-1): the secret
    printed below already has `must_rotate=false`.

    History: CH-0417
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
    """the target of `set-platform-timeouts` comes from the
    `audit_writer_roles` row itself -- never a role-name argument, never a
    naming-convention derivation from `current_user`/schema. Raw read + the
    SAME `validate_audit_writer_roles_value` the read/write paths use
    (design D-2(h) 6: "行の検証は...同じ関数を通る").

    History: CH-0419
    """
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
    """`show-declarations`'s own lenient variant of `_read_audit_writer_roles`
    -- a diagnostic must still print SOMETHING for a row that is absent or
    fails validation, rather than dying (this command's own docstring:
    "does not itself enforce...validation"). Returns `None` (never a
    guessed role-name pair) when the row is absent or invalid -- D-2(h) 3's
    "role 名の導出規則はコードから撤去する" applies to a DIAGNOSTIC command exactly as much
    as to a fail-fast one: a deployment whose real writer roles are not the
    production seed names must never have this command print settings for
    roles that do not exist on it. Raises `psycopg.errors.UndefinedTable`
    (uncaught) so the caller's own existing table-not-found handling
    applies uniformly.

    History: CH-0420
    """
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
    deployment固有" value). `--control-base-url` is OPTIONAL (omitted = no
    control row declared); `--no-control` is an explicit, equivalent form
    of that same omission (correction,
    `{scratchpad}/q4-f3c-and-amendments.md`: "`--no-control` は廃止"の旧
    裁定は撤回され、「省略と等価の明示形」として受け付ける). Passing BOTH is a usage error (argparse's
    own mutually-exclusive-group behavior, exit 2) -- neither is required.
    Validated through the SAME function
    (`platform_declarations.validate_surfaces_value`) the read path uses
    (D-2(d): "書き込み時と読み出し時の両方で...同じ Python の検証関数を通る").

    History: CH-0421
    """
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


def cmd_declare_process_ceilings(args: argparse.Namespace) -> int:
    """writes the single `process_ceilings` row both processes read --
    REPLACES the entire row, same convention as `cmd_declare_surfaces`.
    Validated through the SAME function
    (`platform_declarations.validate_process_ceilings_value`) the read path
    uses (D-2(d)'s own regularity, applied to this new key).

    History: CH-0422
    """
    value = {"data": args.data, "control": args.control}
    schema = _schema()
    try:
        platform_declarations.validate_process_ceilings_value(value, schema=schema, ops_module=platform_declarations.PEER_MODULE)
    except platform_declarations.PlatformDeclarationError as exc:
        _die(str(exc))
    dsn = _provision_dsn()
    conn = psycopg.connect(dsn)
    try:
        _upsert_declaration(conn, schema=schema, key="process_ceilings", value=value)
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()
    print(f"process_ceilings declared: {json.dumps(value, sort_keys=True)}")
    print(
        "Restart both processes for this to take effect (design D-5 (ii): startup snapshot). If this "
        "platform database was provisioned before migration 0011, apply it first -- the migration → "
        "declare-process-ceilings → restart order is required (LQ4-24)."
    )
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
    # Contract 1.7.0 (work order §2 WP-2e/WP-3e F-3, `{scratchpad}/
    # rulings-r3-r7-flip.md` F-3): `check_contract_170_declarations`'s
    # own new condition -- the next unused exit code (F-12 is reserved,
    # out of scope for this command, `_verify_declarations_checks`'s own
    # docstring / the trailing disclosure line below).
    "F-14": 13,
    # Phase 10 WP-6a (design D-5(ii)): `process_ceilings` row present and
    # well-formed -- the next unused exit code.
    "F-15": 14,
    # Phase 10 WP-4f (supervisor ruling 2026-09-09): every role this
    # deployment pools connections against has a CONNECTION LIMIT of -1 or
    # at least its own real pool-composition floor -- the next unused exit
    # code.
    "F-16": 15,
    "F-17": 16,
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
    # Phase 10 WP-6a (design D-5(ii)): one combined entry -- `read_platform_
    # declarations` raises F-15 for BOTH the missing-row and the malformed-
    # value case for this key (unlike surfaces' F-3/F-5 split), and checks
    # both right after the window row-existence check above, before
    # surfaces/window VALUE validation runs.
    ("F-15", "process_ceilings row present and valid"),
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

    # Contract 1.7.0 (work order §2 WP-2e/WP-3e F-3, `{scratchpad}/
    # rulings-r3-r7-flip.md` F-3; WP-2e/WP-3e rework `{scratchpad}/
    # audit-wp2e.md` D-2, ruling L-2 = (A); closure audit M-7, `{scratchpad}
    # /audit-wp2e-2.md` R-7): the "enabled" declaration checked against the
    # actual deployed state -- the served capabilities document (its
    # `capabilities` AND `limits` blocks alike, never a second, separately
    # constructed limits object), AND (the one part that can genuinely
    # fail against a real deployment) every registered application's own
    # per-application upgrade ledger (R-2/R-5). Run unconditionally like
    # the writer-role check just above.
    try:
        applied_by_application = _applied_upgrade_numbers_by_application(conn, dsn)
        platform_declarations.check_contract_170_declarations(
            _served_capabilities_document(),
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

    # Phase 10 WP-4f (supervisor ruling 2026-09-09): every role this
    # deployment pools connections against (identified by REAL GRANTS,
    # never a schema/role-name string-rewrite convention -- see `check_
    # role_connection_limits`'s own docstring) must have a CONNECTION
    # LIMIT of -1 or at least its own real pool-composition floor.
    # `_declared_concurrency()` is peer-local -- this function's own call
    # site stays textually isomorphic across peers; see that helper's own
    # docstring for the peer-specific body it hides. Run unconditionally
    # like the writer-role/F-14 checks above.
    try:
        platform_declarations.check_role_connection_limits(
            conn, schema=schema, ops_module=platform_declarations.PEER_MODULE,
            concurrency=_declared_concurrency(),
        )
    except platform_declarations.PlatformDeclarationError as exc:
        return _verify_declarations_fail(exc)
    _verify_declarations_ok("F-16", "each role's CONNECTION LIMIT is -1 or at least its own real pool-composition floor")

    try:
        platform_declarations.check_auditreader_statement_timeout(conn, schema=schema)
    except platform_declarations.PlatformDeclarationError as exc:
        return _verify_declarations_fail(exc)
    _verify_declarations_ok("F-17", "auditreader role's statement_timeout is a positive, role-level-only value")
    return 0


def _declared_concurrency() -> int:
    """Same lenient-degrade discipline as `main._optional_int`/`config.
    FoundationConfig.max_concurrency`'s own default: an unset or
    unparsable `MITATEDB_MAX_CONCURRENCY` silently falls back to the
    dataclass default rather than raising here -- this is only a
    verification-time floor computation, not the real composition root's
    own strict parse."""
    raw = os.environ.get("MITATEDB_MAX_CONCURRENCY")
    if not raw:
        return FoundationConfig.max_concurrency
    try:
        return int(raw)
    except ValueError:
        return FoundationConfig.max_concurrency


def _served_capabilities_document() -> dict:
    """O-7 prep (版フリップ監査, ruling `{scratchpad}/rulings-r3-r7-flip.md`
    追補4): extracted out of `_verify_declarations_checks` under this SAME
    name on both peers (r2db-api's own `_served_capabilities_document`,
    `r2db_api/ops.py`), so that function's own body -- one of the
    isomorphism-pinned symbols -- calls this helper with no arguments and
    carries no peer-specific complexity of its own. This peer's own
    equivalent, unlike r2db-api's, first has to build a `FoundationConfig`
    before it can construct its own probe cell -- that peer-specific
    difference now lives entirely INSIDE this helper's own body, never
    inside `_verify_declarations_checks`'s. Previously named `_contract_
    170_capabilities_document` and taking the caller's already-resolved
    `FoundationConfig` (built from `declarations.surfaces.data_base_url`)
    as an argument (the form `_verify_declarations_checks` used before
    this rework) -- `FoundationConfig.from_env` REQUIRES a truthy
    `data_base_url` (`config.py`'s own "surfaces.data is required" raise,
    unconditional, unlike the bare dataclass constructor's own `None`-
    tolerant `__post_init__`), so this helper cannot simply omit it the
    way a first draft assumed; a fixed, synthetic placeholder URL is
    supplied here instead (`tools/public_value_scan.py`-safe: a `.invalid`
    domain, never a real deployment value) -- functionally inert either
    way, since `ApplicationCell`'s own default backend, `backend_sqlite.
    SQLiteBackend`, is a deterministic, in-memory, pure-Python object
    with no real database connection this URL could ever be dialed
    through. `FoundationConfig.from_env()` still reads every OTHER
    (limit) env var exactly as before -- only this one peer-specific
    argument is now internal to this helper rather than threaded in from
    `_verify_declarations_checks`; the isomorphism table row addition
    itself is pair-closing work, not done here (O-7's own instruction:
    "同型性表への行追加は監督の pair-closing で行う").

    The REAL `ApplicationRuntime.capabilities()` document for a throwaway,
    entirely in-memory application/credential -- never a second, hand-
    written copy of what `cell.py` is expected to declare: this exercises
    the SAME production code path a real client's `GET /v1/capabilities`
    reaches, so a future regression that stops declaring one of the
    contract 1.7.0 capabilities `enabled` is caught here too, not only by
    `mitatedb_api.cell`'s own unit tests."""
    from .cell import ApplicationCell, ApplicationRuntime, Principal
    from .auth import Role

    config = FoundationConfig.from_env(data_base_url="https://verify-declarations-probe.example.invalid/v1")
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
    dual check (F-7/F-10/F-11/F-13/F-9) unconditionally, then the
    limit-class check (F-14) unconditionally, then (Phase 10 WP-4f,
    supervisor ruling 2026-09-09) the role CONNECTION LIMIT check (F-16)
    unconditionally. The first FAIL stops the run and returns that
    F-number's own fixed exit code (`_VERIFY_DECLARATIONS_EXIT_CODES`, via
    `_verify_declarations_checks`).

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
    returns (0 through 15 alike -- F-14's own exit code (contract 1.7.0),
    F-15's own (Phase 10 WP-6a, contract 1.8.0), and F-16's own (Phase 10
    WP-4f) included), never only on the 0 path."""
    schema = _schema()
    dsn = os.environ.get(platform_declarations.PROVISION_DSN_ENV)
    if not dsn:
        print(f"error: {platform_declarations.PROVISION_DSN_ENV} is required", file=sys.stderr)
        return 1
    try:
        conn = psycopg.connect(dsn, autocommit=True)
    except psycopg.Error as exc:
        print(f"error: cannot connect to platform database ({type(exc).__name__})", file=sys.stderr)
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
    """the DEFAULT target set (`application_id is None`) is every registered
    application whose provisioning has actually completed (`database_name
    IS NOT NULL`) -- `enabled` is NOT part of this filter (design D-4(a):
    "`enabled` は対象選択に影響しない...無効化中の application の DB も一括適用の対象に含める").

    M-2(a)/(d) fix (rework): an EXPLICITLY named `--application <id>` is
    returned REGARDLESS of its own `database_name` -- mirrors r2db-api's
    own `_registry_applications_for_upgrade` (`r2db_api/ops.py`'s own
    docstring: "レジスタ済みだが未 provision の application は SKIP として報告する...operator
    が名指しした時だけ"). Before this fix the SAME `database_name IS NOT NULL`
    filter applied to both branches, so
    `--application <never-provisioned-id>` silently returned ZERO rows --
    indistinguishable from `--application <id-not-registered-at-all>` --
    and both `cmd_upgrade_applications`/`cmd_upgrade_status` then reported
    success with NO output at all, instead of `_die`ing (a
    registered-nothing id) or reporting a `database_name=None` skip row
    (design D-4(d) / D-5's own "database_nameがNULLの場合はappliedを[]とする"). `_die`s
    HERE (mirrors r2db-api's own identically-placed check in its own
    `_registry_applications_for_upgrade`) when an explicitly-named
    application matches no registry row at all, so BOTH callers get the fix
    at once.

    Returns `(application_id, database_name, developer_role)` rows, the
    latter two `None` for a registered-but-never-provisioned application
    (`database_name`, in turn, is `None` only when the row itself was
    never assigned one by `finish_provision_application` -- `developer_
    role` is `UNIQUE`, non-nullable in the schema, but is read as `NULL`
    here anyway when no row at all comes back, never dereferenced by a
    caller that already checked `database_name is None` first). Ordered
    by `application_id` for deterministic output.

    History: CH-0428
    """
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


def _run_upgrade_script(provision_dsn: str, script: Path, application_id: str, lock_timeout: str) -> tuple[bool, str]:
    """the `psql` subprocess call shape this peer newly carries
    (`MitateDB-api/src/mitatedb_api/ops.py::_run_deprovision_script`'s own
    call shape, followed here -- never `_die`, which would exit immediately
    and stop this command from reaching the REST of the applications it
    must still visit, design D-4(c)/禁止事項 16).

    Connects with the PLATFORM `provision_dsn` -- never the app-database-
    swapped `_app_dsn` (that swap is for the PYTHON-side ledger reads
    only, `_upgrade_one_application`'s own `read_applied_upgrade_numbers`
    calls). Every per-application upgrade script (`0006`/`0008`, design
    §1.5 の 5) starts by resolving `database_name` from `mitatedb_
    registry.applications` and then `\\c`-ing to it itself -- exactly the
    same shape `_run_deprovision_script` already follows for `0004`,
    which also expects to start out connected to the PLATFORM database.

    History: CH-0429
    """
    _require_psql_16_or_newer()
    env = _psql_connection_env(provision_dsn)
    env["PGOPTIONS"] = _with_lock_timeout_option(env.get("PGOPTIONS"), lock_timeout)
    result = subprocess.run(
        ["psql", "-v", "ON_ERROR_STOP=1",
         "-v", f"{platform_upgrades.UPGRADE_SCRIPT_VARIABLE}={application_id}", "-f", str(script)],
        capture_output=True, text=True, env=env,
    )
    return result.returncode == 0, _redact_connection_values(f"{result.stdout}\n{result.stderr}", provision_dsn)


def _upgrade_one_application(
    *, provision_dsn: str, provision_role: str, application_id: str, database_name: str, developer_role: str,
    migrations_by_number: dict[int, Path], script_filter: Optional[int], dry_run: bool, lock_timeout: str,
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
            cleanup_sql=cleanup_sql, failure_detail=_redact_connection_values(str(exc), app_dsn),
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
                ok, output = _run_upgrade_script(provision_dsn, script, application_id, lock_timeout)
                if ok:
                    applied_now.append(number)
                else:
                    failed.append(number)
                    # the failed psql invocation's own
                    # stdout+stderr
                    # (`_run_upgrade_script`'s own
                    # return) is the ONLY place the
                    # actual PostgreSQL error text lives
                    # -- before this fix it was bound to
                    # `_output` and dropped, leaving an
                    # operator staring at "FAILED to
                    # apply: [N]" with no way to learn
                    # WHY short of re-running the script
                    # by hand. Tail only (last ~20
                    # lines): `psql`'s own
                    # `ON_ERROR_STOP=1` failure text is
                    # short, and this application's own
                    # summary line must not be buried
                    # under an unrelated wall of output
                    # for a script that fails early with
                    # a long preamble already printed.
                    # history: CH-0431
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
    """one line per application (`applied_before` -> `applied_after` /
    `pending`), a separate `skipped` block (design D-4(d): "psql の `\\q`
    skip は exit 0 で返り成功と区別できないため、無音で成功に見える経路を出力側で閉じる"), the `REVOKE`
    cleanup line for every application that failed, and a trailing
    success/failure/skip tally.

    Counting rule (supervisor ruling U-1, 2026-09-05, 差し戻し後 delta
    監査), unified with r2db-api's own same-shaped tally: each
    application lands in EXACTLY one bucket. `failed` always
    wins first -- this INCLUDES `database_name is None` even under
    `--dry-run`, where `result.failed` itself is deliberately left empty
    (so `summarize_upgrade_run`'s own exit code stays `4`, never `3`, for a
    dry run) -- the tally line is a separate, purely descriptive surface,
    so it counts a never-provisioned application as failed regardless.
    Otherwise, an application whose own `applied_after` came back identical
    to its own `applied_before` actually applied NOTHING this run (either
    nothing was pending at all, or `--script` named a number this
    application's own ledger already recorded) -- that is "skipped"
    (未適用なし、既に記録済み), never "succeeded" (which requires having actually run
    and applied at least one upgrade). The prior form instead counted
    `succeeded` as simply "not failed" and `skipped` from `result.skipped`
    (populated ONLY by the `--script`-already-recorded path) INDEPENDENTLY
    -- a row could be counted in BOTH `succeeded` and `skipped` at once,
    and a fully-caught-up application in a bulk (non-`--script`) run was
    counted "succeeded" despite having applied nothing.

    History: CH-0432
    """
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
                # psql's own stderr tail, folded into THIS
                # application's own output block, before the
                # cleanup line (diagnosis before remedy) --
                # see `_upgrade_one_application`'s own
                # comment for why only the tail.
                # history: CH-0433
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
    """bulk-applies every pending per-application upgrade (design §8:
    `PLATFORM_UPGRADE_NUMBERS` = {6, 8, 9} -- `9` added by Phase 9 WP-3a's
    own `field_constraints` upgrade script; this function needed no change
    of its own for that addition, since it is driven entirely by
    `PLATFORM_UPGRADE_NUMBERS`/`discover_upgrade_scripts` (both data,
    `platform_upgrades.py`), never a number hardcoded here) across every
    provisioned application, or
    one (`--application`), or one SCRIPT across every application still
    missing it (`--script`, design D-4(a): only applied to a database that
    has not yet recorded it -- an already-recorded database is `skipped`,
    still counted a success). `--dry-run` applies nothing, reporting the
    same applied/pending tally `upgrade-status` reports. Requires
    `MITATEDB_PROVISION_DSN` only -- never a control credential (SI-02).

    History: CH-0434
    """
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
    lock_timeout = _validate_lock_timeout_value(args.lock_timeout)
    conn = psycopg.connect(provision_dsn)
    try:
        provision_role = conninfo_to_dict(provision_dsn).get("user") or conn.info.user
        rows = _registry_applications_for_upgrade(conn, schema=schema, application_id=args.application)
    finally:
        conn.close()

    results = []
    for application_id, database_name, developer_role in rows:
        if database_name is None:
            # a REGISTERED but never-provisioned application,
            # reachable only via an explicit `--application <id>`
            # (the default enumeration already excludes these
            # rows entirely). `pending_after` is always every
            # number this package requires (nothing could
            # possibly have been applied to a database that does
            # not exist) -- alone enough to make `--dry-run`
            # return `4` (mirrors `cmd_upgrade_status` below).
            # `failed` is populated the SAME way, but ONLY for a
            # real (non-dry-run) invocation -- D-4(e)'s own
            # exit-code table names `database_name`がNULL
            # explicitly as one of the two conditions exit code
            # `3` covers ("psql exit 3、または`database_name`がNULL");
            # this is what makes `summarize_upgrade_run` below --
            # UNMODIFIED, still the exact same pinned pure
            # function -- return `3` for this case on its own. A
            # `--dry-run` never "fails" anything (nothing is
            # attempted), so `failed` stays empty there.
            # history: CH-0435
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
            script_filter=args.script, dry_run=args.dry_run, lock_timeout=lock_timeout,
        ))
    _print_upgrade_results(results, dry_run=args.dry_run)
    return platform_upgrades.summarize_upgrade_run(results, dry_run=args.dry_run)


def cmd_upgrade_status(args: argparse.Namespace) -> int:
    """read-only equivalent of `upgrade-applications --dry-run` -- provision
    DSN only, `applied`/`pending`/`database_name` per application. Never
    touches the existing `list-applications` command (design D-5: contract
    shape `ApplicationsResult` unchanged) -- this is an entirely separate,
    peer-local-only surface.

    History: CH-0436
    """
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
            # a REGISTERED but never-provisioned application,
            # reachable only via an explicit `--application <id>`
            # (the default enumeration already excludes these
            # rows entirely) -- reported as `applied=[]`/every
            # number pending (design D-5: "台帳が無い
            # applicationはapplied=[]とする", the SAME treatment as
            # no ledger table at all), never a crash from
            # `_app_dsn(..., None)` (a `None` `dbname` is not a
            # valid connection param).
            # history: CH-0437
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


# ===========================================================================
# `inventory`: read-only Gate-0 DB-layer judgments (design docs/design/
# MITATEDB_PLATFORM_READONLY_INVENTORY_V0_1.md). Never mounted on any HTTP
# surface, never changes platform state, never takes a DSN on argv (only
# MITATEDB_PROVISION_DSN). Prints exactly one JSON object to stdout and
# nothing else; every other subcommand above is unaffected. The DB layer
# judges only the items it can read on its own; item (5) (rollback
# compatibility) and the declared-lock/maintenance-window half of item (6)
# are judged by the platform runbook's own independent-review acceptance
# record, never here -- `unjudged_items` below names the item numbers this
# subcommand has no opinion on at all.
# ===========================================================================

#: Session-level bounds every connection this subcommand opens carries, so
#: a long-held lock elsewhere in the platform (a running migration, an
#: application upgrade) cannot make a Gate-0 read hang -- exceeding either
#: one turns the item being read into `unknown` rather than blocking.
_INVENTORY_LOCK_TIMEOUT_MS = 3000
_INVENTORY_STATEMENT_TIMEOUT_MS = 5000

#: The largest number of connections `inventory`'s own single-threaded
#: run ever holds open at once (one platform connection, plus at most one
#: application connection at a time -- opened, read, and closed before the
#: next). Folded into the connection-headroom reserve below.
_INVENTORY_MAX_CONCURRENT_CONNECTIONS = 2

#: The closed judgment vocabulary every item below returns (never a fourth
#: word). `_INVENTORY_COMPARISONS` is item (1)'s own smaller, separate
#: vocabulary (a comparison result, not a state judgment). `_INVENTORY_
#: REASONS` is the closed set of fixed reason words a `blocked` judgment
#: may carry -- never the underlying exception text.
_INVENTORY_JUDGMENTS = frozenset({"confirmed", "blocked", "unknown"})
_INVENTORY_COMPARISONS = frozenset({"match", "mismatch", "unknown"})
_INVENTORY_REASONS = frozenset({"ledger-unreadable", "declaration-invalid", "statement-timeout-unbounded"})

#: Printed on stderr, at exit code 1, whenever this subcommand itself
#: fails before it can produce any item judgment at all (a missing DSN, an
#: unreadable read-only setting) -- never the underlying exception text.
_INVENTORY_TOOL_FAILURE_MESSAGE = "error: inventory could not run"

#: Column allow-lists for item (4) -- `credential_id`/`digest` never
#: appear: a caller can enumerate/re-identify a credential from its id,
#: and the digest is the one column this table stores that a read-only
#: inventory tool has no business ever projecting. Positions are fixed by
#: this tuple's own order (`_inventory_credentials` indexes rows
#: positionally rather than by re-deriving indices at read time).
_INVENTORY_CREDENTIAL_COLUMNS: tuple[str, ...] = ("role", "enabled", "revoked")
_INVENTORY_CONTROL_CREDENTIAL_COLUMNS: tuple[str, ...] = ("role", "enabled", "revoked", "must_rotate")

#: The exact top-level key set `inventory`'s own JSON output carries --
#: checked by a static test, never widened ad hoc. There is no "ready"
#: key anywhere in this shape: Gate-0's overall readiness is a
#: runbook-level judgment across BOTH the DB and platform layers, never
#: something this DB-layer-only subcommand can compute or publish on its
#: own. Item (5) has no key at all (DB layer never judges it); item (6)'s
#: own key covers only its runtime-settings half.
_INVENTORY_TOP_LEVEL_KEYS = frozenset({
    "connection", "declarations", "migrations", "credentials",
    "ddl_lock", "connection_headroom", "unjudged_items",
})

#: The fixed, pinned content of the `unjudged_items` key: the Gate-0
#: item/part pairs this DB-layer subcommand never judges at all, each
#: with the fixed reason word `runbook-acceptance` (the platform
#: runbook's own independent-review acceptance record judges them
#: instead). Item (5) is unjudged in full (`part` "all"); item (6)'s
#: declared lock-type/stop-time-limit half is unjudged too (`part`
#: "lock-and-downtime") -- item (6) still has its own `ddl_lock` key,
#: since its runtime-settings half IS judged here.
_INVENTORY_UNJUDGED_PARTS = frozenset({"all", "lock-and-downtime"})
_INVENTORY_UNJUDGED_ITEMS: tuple[dict, ...] = (
    {"item": 5, "part": "all", "reason": "runbook-acceptance"},
    {"item": 6, "part": "lock-and-downtime", "reason": "runbook-acceptance"},
)


def _inventory_positive_int(value: str) -> int:
    """`argparse` `type=` for `--concurrency`/`--data-process-ceiling`/
    `--data-process-count-total`/`--control-process-ceiling`/`--control-
    process-count-total` -- 0 and negative values are usage errors
    (argparse's own fixed, templated message via `parser.error()`),
    never silently accepted as if they meant "no input" the way omitting
    the argument entirely does. `inventory`'s own subparser remaps this
    usage error's exit code to 1, never argparse's default 2 (which this
    subcommand reserves for a completed item judgment) -- see the
    `p.error` override in `_build_parser`."""
    try:
        parsed = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"must be a positive integer, got {value!r}")
    if parsed <= 0:
        raise argparse.ArgumentTypeError(f"must be a positive integer, got {value!r}")
    return parsed


def _inventory_nonnegative_int(value: str) -> int:
    """`argparse` `type=` for `--reserved-connections` only -- unlike
    `inventory`'s other numeric arguments (which use `_inventory_
    positive_int`), `0` is a genuine value here ("no reserve"), so only
    negative values (and non-integer text) are usage errors."""
    try:
        parsed = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"must be a non-negative integer, got {value!r}")
    if parsed < 0:
        raise argparse.ArgumentTypeError(f"must be a non-negative integer, got {value!r}")
    return parsed


def _inventory_connect(dsn: str) -> "psycopg.Connection":
    """The only `psycopg.connect` call this subcommand's own code makes --
    every connection `inventory` opens, the platform connection and each
    application connection alike, goes through here, so the read-only
    setting and the two session timeouts above apply uniformly, and a
    test spying on `psycopg.connect` catches every one of them.
    `autocommit` is always on: none of `inventory`'s own reads need a
    held-open transaction, and it lets the existing `read_applied_
    upgrade_numbers` helper's own `conn.rollback()` (its `UndefinedTable`
    recovery path) run against this connection without disturbing a `SET`
    statement issued moments before -- `SET` inside an open, later-
    rolled-back transaction would itself be rolled back, silently undoing
    the timeouts this function just applied. If any of the three `SET`
    statements themselves fails, the connection is closed before the
    exception propagates -- never leaked half-configured."""
    conn = psycopg.connect(dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute("SET default_transaction_read_only = on")
            cur.execute(sql.SQL("SET lock_timeout = {}").format(sql.Literal(f"{_INVENTORY_LOCK_TIMEOUT_MS}ms")))
            cur.execute(sql.SQL("SET statement_timeout = {}").format(sql.Literal(f"{_INVENTORY_STATEMENT_TIMEOUT_MS}ms")))
    except BaseException:
        conn.close()
        raise
    return conn


def _inventory_confirmed_read_only(conn: "psycopg.Connection") -> bool:
    """Reads back `transaction_read_only` on an already-open connection --
    never assumed true merely because `_inventory_connect` just set it."""
    with conn.cursor() as cur:
        cur.execute("SHOW transaction_read_only")
        (value,) = cur.fetchone()
    return value == "on"


#: (1)'s own `comparison` -> W-2 `judgment` mapping (supervisor ruling
#: B-13): `match` is the confirmed case, `mismatch` is a real blocker
#: (design Z-26: the DB/platform pair does not agree, never merely
#: "unreadable"), `unknown` stays `unknown`.
_INVENTORY_COMPARISON_TO_JUDGMENT = {"match": "confirmed", "mismatch": "blocked", "unknown": "unknown"}


def _inventory_connection_match(dsn: str, connection_name: "Optional[str]") -> dict:
    """(1): compares the platform-layer-supplied Cloud SQL connection name
    against the unix socket directory this SAME process' own DSN names --
    never a value read from the database itself. A missing argument, or a
    DSN whose `host` is not a unix socket path (a TCP/loopback DSN),
    leaves this `unknown`; the connection target itself is never part of
    the output. Carries BOTH `comparison` (`match`/`mismatch`/`unknown`,
    Z-26's own vocabulary) and `judgment` (W-2's own closed vocabulary,
    supervisor ruling B-13) -- `_inventory_exit_code` reads `judgment`
    here exactly like every other item, never `comparison` directly."""
    comparison = _inventory_connection_comparison(dsn, connection_name)
    return {"comparison": comparison, "judgment": _INVENTORY_COMPARISON_TO_JUDGMENT[comparison]}


def _inventory_connection_comparison(dsn: str, connection_name: "Optional[str]") -> str:
    if not connection_name:
        return "unknown"
    try:
        params = conninfo_to_dict(dsn)
    except psycopg.Error:
        return "unknown"
    host = params.get("host") or ""
    if not host.startswith("/"):
        return "unknown"
    if host.rstrip("/").endswith("/" + connection_name):
        return "match"
    return "mismatch"


def _inventory_role_classes(conn: "psycopg.Connection", schema: str) -> tuple:
    """`(api_roles, control_roles, auditreader_roles)` -- the same
    table-grant discovery `platform_declarations.check_role_connection_
    limits` uses internally (never a fixed literal role name), shared by
    item (6) and item (8) so the target-role definition never drifts
    between the two. May raise `psycopg.Error`; every caller catches it."""
    api_owner = platform_declarations._table_owner(conn, schema, "application_audit")
    api_roles = [
        role for role in platform_declarations._roles_with_table_privilege(conn, schema, "application_audit", "INSERT")
        if role != api_owner
    ]
    control_owner = platform_declarations._table_owner(conn, schema, "control_audit")
    control_roles = [
        role for role in platform_declarations._roles_with_table_privilege(conn, schema, "control_audit", "INSERT")
        if role != control_owner
    ]
    reader_app = set(platform_declarations._roles_with_table_privilege(conn, schema, "application_audit", "SELECT"))
    reader_control = set(platform_declarations._roles_with_table_privilege(conn, schema, "control_audit", "SELECT"))
    auditreader_roles = sorted(role for role in (reader_app & reader_control) if role != api_owner and role != control_owner)
    return api_roles, control_roles, auditreader_roles


#: `read_platform_declarations`'s own missing-row message for `process_
#: ceilings` (the one `PlatformDeclarationError` whose code, `F-15`, is
#: shared with two DIFFERENT shape-violation messages) starts with this
#: exact prefix -- the only reliable way to tell "the row itself is
#: absent" (confirmed + remediation-required, like F-8/F-3/F-4) apart
#: from "the row exists but its value is malformed" (blocked) without a
#: second query, since both raise the identical `code="F-15"`.
_INVENTORY_F15_MISSING_MARKER = "no 'process_ceilings' row in"


def _inventory_declaration_error_is_missing(exc: "platform_declarations.PlatformDeclarationError") -> bool:
    if exc.code in ("F-8", "F-3", "F-4"):
        return True
    if exc.code == "F-15" and _INVENTORY_F15_MISSING_MARKER in str(exc):
        return True
    return False


def _inventory_declarations(conn: "psycopg.Connection", schema: str) -> dict:
    """(2): platform declarations, via the SAME read function every other
    subcommand already uses. A declaration that does not exist yet at all
    (the table, or one of its required rows, is simply absent -- F-8 / F-3
    / F-4 / F-15's own missing-row case) is a known, recoverable gap --
    confirmed with `remediation_required`. A declaration that DOES exist
    but fails its own value validation (F-5 / F-4b / F-15's own shape/value
    case -- hand-edited into a malformed shape) is `blocked` with the fixed
    reason `declaration-invalid`, never confirmed by treating a corrupt
    value as equivalent to an absent one."""
    try:
        platform_declarations.read_platform_declarations(
            conn, schema=schema, ops_module=platform_declarations.PEER_MODULE,
            migration=platform_declarations.MIGRATION_NUMBER,
        )
    except platform_declarations.PlatformDeclarationError as exc:
        if _inventory_declaration_error_is_missing(exc):
            return {"judgment": "confirmed", "remediation_required": True, "reason": None}
        return {"judgment": "blocked", "remediation_required": False, "reason": "declaration-invalid"}
    except psycopg.Error:
        return {"judgment": "unknown", "remediation_required": False, "reason": None}
    return {"judgment": "confirmed", "remediation_required": False, "reason": None}


def _inventory_migrations(conn: "psycopg.Connection", provision_dsn: str, schema: str) -> dict:
    """(3): per-application migration/upgrade ledger state. A registered
    but never-provisioned application is counted, never confirmed/blocked/
    unknown on its own. A connection failure, or any `read_applied_
    upgrade_numbers` failure OTHER than the two named below, leaves this
    item `unknown` for that application (never crashes the whole
    subcommand -- every other application is still visited).
    `InsufficientPrivilege` specifically (a pre-0008 application
    provisioned before the provision role's own `GRANT USAGE ON SCHEMA
    public` existed, roadmap R-47) is reported `blocked` with the fixed
    reason `ledger-unreadable` -- never the raw exception text -- since
    that application genuinely cannot be upgraded by the current tooling,
    not merely unreadable right now."""
    try:
        applications = _registry_applications_for_upgrade(conn, schema=schema, application_id=None)
        applications_table = sql.Identifier(schema, "applications")
        with conn.cursor() as cur:
            cur.execute(sql.SQL("SELECT count(*) FROM {table} WHERE database_name IS NULL").format(table=applications_table))
            (registered_only_count,) = cur.fetchone()
    except psycopg.Error:
        return {"judgment": "unknown", "remediation_required": False, "reason": None, "registered_only_count": 0}

    judgment = "confirmed"
    remediation_required = False
    reason = None
    for application_id, database_name, _developer_role in applications:
        app_dsn = _app_dsn(provision_dsn, database_name)
        try:
            app_conn = _inventory_connect(app_dsn)
        except psycopg.Error:
            if judgment != "blocked":
                judgment = "unknown"
            continue
        try:
            if not _inventory_confirmed_read_only(app_conn):
                if judgment != "blocked":
                    judgment = "unknown"
                continue
            try:
                applied = platform_upgrades.read_applied_upgrade_numbers(
                    app_conn, ledger_table_name=platform_upgrades.LEDGER_TABLE_NAME)
            except psycopg.errors.InsufficientPrivilege:
                judgment = "blocked"
                reason = "ledger-unreadable"
                continue
            except psycopg.Error:
                if judgment != "blocked":
                    judgment = "unknown"
                continue
        finally:
            app_conn.close()
        if applied is None:
            remediation_required = True
        elif platform_upgrades.pending_upgrade_numbers(applied, platform_upgrades.PLATFORM_UPGRADE_NUMBERS):
            remediation_required = True
    return {
        "judgment": judgment, "remediation_required": remediation_required,
        "reason": reason, "registered_only_count": registered_only_count,
    }


def _inventory_select_credential_rows(conn: "psycopg.Connection", schema: str, table_name: str, columns: "tuple[str, ...]") -> list:
    """The one query item (4) sends per table -- column list built
    entirely from `columns` (an allow-list constant), never `SELECT *`.
    Returns full rows (not merely a count) so the caller can aggregate
    per-state counts; positional, matching `columns`'s own order."""
    table = sql.Identifier(schema, table_name)
    projection = sql.SQL(", ").join(sql.Identifier(column) for column in columns)
    with conn.cursor() as cur:
        cur.execute(sql.SQL("SELECT {columns} FROM {table}").format(columns=projection, table=table))
        return cur.fetchall()


def _inventory_credentials(conn: "psycopg.Connection", schema: str) -> dict:
    """(4): credential registry, projected to non-secret columns only --
    `credential_id`/`digest` never appear in the SELECT list, regardless
    of what the connecting role could technically read. Reports the total
    row count PLUS per-state counts (`enabled`/`revoked` across both
    tables, `must_rotate` -- `control_credentials` only, the only one of
    the two tables with that column). A permission shortfall on either
    table leaves this `unknown`, never confirmed by skipping the table."""
    try:
        credential_rows = _inventory_select_credential_rows(conn, schema, "credentials", _INVENTORY_CREDENTIAL_COLUMNS)
        control_credential_rows = _inventory_select_credential_rows(
            conn, schema, "control_credentials", _INVENTORY_CONTROL_CREDENTIAL_COLUMNS)
    except psycopg.Error:
        return {
            "judgment": "unknown", "remediation_required": False,
            "total_count": 0, "enabled_count": 0, "revoked_count": 0, "must_rotate_count": 0,
        }
    # Positional indices fixed by `_INVENTORY_CREDENTIAL_COLUMNS`/
    # `_INVENTORY_CONTROL_CREDENTIAL_COLUMNS`'s own declared order above:
    # ("role", "enabled", "revoked"[, "must_rotate"]).
    enabled_count = sum(1 for row in credential_rows if row[1]) + sum(1 for row in control_credential_rows if row[1])
    revoked_count = sum(1 for row in credential_rows if row[2]) + sum(1 for row in control_credential_rows if row[2])
    must_rotate_count = sum(1 for row in control_credential_rows if row[3])
    return {
        "judgment": "confirmed", "remediation_required": False,
        "total_count": len(credential_rows) + len(control_credential_rows),
        "enabled_count": enabled_count, "revoked_count": revoked_count, "must_rotate_count": must_rotate_count,
    }


def _inventory_ddl_lock_declaration(conn: "psycopg.Connection", schema: str) -> dict:
    """(6), runtime-settings half only: reads the target
    roles' (the SAME full set item (8) discovers -- `api_roles`/`control_
    roles`/`auditreader_roles` by table grant, PLUS every provisioned
    application's own `runtime_role`/`developer_role`) `CONNECTION LIMIT`
    and `statement_timeout` declaration. `lock_timeout` is
    not part of this judgment: no role in this target set ever runs DDL
    (the role that does, the provision role, is never a member of this
    set), so a `lock_timeout` role setting here never bounded a DDL wait
    -- the DDL-wait bound is the required `--lock-timeout` argument every
    subcommand that applies a migration file (`apply-platform-migration`/
    `upgrade-applications`/`deprovision`) already carries. `CONNECTION
    LIMIT` is confirmed up to its actual VALUE, not merely its presence:
    `-1` (unlimited) is unknown here too, the SAME sentinel item (8)
    already treats specially for this identical role set; this early
    return happens before any role's `statement_timeout` value is read,
    so a `-1` CONNECTION LIMIT never mixes with a `statement_timeout`
    judgment on the same run. A role's `statement_timeout`, once
    declared (database-independently, `setdatabase = 0`), is read
    through the SAME normalization every other timeout comparison in
    this package uses (`pg_timeouts.ms_from_pg_timeout_text`) and must
    be a POSITIVE number of milliseconds -- zero (PostgreSQL's own
    "disabled" rendering) or a negative number are both `blocked` with
    the fixed reason `statement-timeout-unbounded`, never confirmed by
    treating "some value is declared" as sufficient on its own. A value
    `ms_from_pg_timeout_text` cannot parse is `blocked` for the same
    reason, its own raw text never surfacing in the output. A role
    carrying no `statement_timeout` declaration at all stays `unknown`,
    unless some OTHER role in the same target set is already `blocked` --
    `blocked` outranks `unknown` across this target set, mirroring item
    (3)'s own judgment-combining rule, but this ranking applies only
    between `statement_timeout` value judgments; it never reaches back
    to override the CONNECTION LIMIT early return above. The output
    always carries a `reason` key (`None` outside the `blocked` case),
    matching item (2)/(3)'s own shape, and `remediation_required` stays
    `False` in the `blocked` case -- a positive value the operator must
    choose, never a gap this tool can safely fill in on its own. The
    declared lock-type/stop-time-limit half of item (6) is judged by the
    platform runbook's own independent-review acceptance record instead
    (`_INVENTORY_UNJUDGED_ITEMS`'s own `{"item": 6, "part": "lock-and-
    downtime", ...}` entry), never here -- item (6) still keeps its own
    `ddl_lock` key because this runtime-settings half DOES get a real
    judgment. Item (8)'s own `--control-not-deployed` never narrows this
    item's role set: a role this item finds by grant stays subject to
    its own judgment for as long as the role itself exists."""
    try:
        api_roles, control_roles, auditreader_roles = _inventory_role_classes(conn, schema)
    except psycopg.Error:
        return {"judgment": "unknown", "remediation_required": False, "reason": None}
    try:
        with conn.cursor() as cur:
            applications_table = sql.Identifier(schema, "applications")
            cur.execute(sql.SQL(
                "SELECT runtime_role, developer_role FROM {table} "
                "WHERE runtime_role IS NOT NULL AND developer_role IS NOT NULL"
            ).format(table=applications_table))
            app_roles = cur.fetchall()
    except psycopg.Error:
        return {"judgment": "unknown", "remediation_required": False, "reason": None}
    target_roles = (
        api_roles + control_roles + auditreader_roles
        + [name for pair in app_roles for name in pair]
    )
    if not target_roles:
        return {"judgment": "unknown", "remediation_required": False, "reason": None}
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT rolname, rolconnlimit FROM pg_roles WHERE rolname = ANY(%s)", [target_roles])
            limits = dict(cur.fetchall())
        if any(limits.get(role) is None or limits.get(role) == -1 for role in target_roles):
            return {"judgment": "unknown", "remediation_required": False, "reason": None}
        judgment = "confirmed"
        for role in target_roles:
            declared_value: "Optional[str]" = None
            for setdatabase, _datname, setconfig in platform_declarations._role_setting_rows(conn, role):
                if setdatabase == 0 and setconfig:
                    for entry in setconfig:
                        key, _sep, value = entry.partition("=")
                        if key == "statement_timeout":
                            declared_value = value
            if declared_value is None:
                if judgment != "blocked":
                    judgment = "unknown"
                continue
            try:
                declared_ms = pg_timeouts.ms_from_pg_timeout_text(declared_value)
            except ValueError:
                judgment = "blocked"
                continue
            if declared_ms <= 0:
                judgment = "blocked"
    except psycopg.Error:
        return {"judgment": "unknown", "remediation_required": False, "reason": None}
    reason = "statement-timeout-unbounded" if judgment == "blocked" else None
    return {"judgment": judgment, "remediation_required": False, "reason": reason}


def _inventory_connection_headroom(conn: "psycopg.Connection", schema: str, args: argparse.Namespace) -> dict:
    """(8): connection headroom across the three platform-plane role
    classes and every provisioned application's own runtime/developer
    roles. Two DIFFERENT numbers feed this item per
    plane, never one: `--data-process-ceiling`/`--control-process-
    ceiling` (the NEW candidate revision's own declared maximum,
    compared against the `process_ceilings` declaration)
    and `--data-process-count-total`/`--control-process-count-total`
    (the actual combined process count across however many revisions are
    concurrently serving traffic, the number role-connection demand is
    computed from). Neither pair fills in for the other: a caller
    that omits one of the four leaves this `unknown`
    (`ops verify-declarations`'s own F-16 check is a DIFFERENT, single-
    process floor check and is never consulted here). `--control-not-
    deployed` is the only way Control's own process arguments may be
    absent: it declares, out loud, that no Control-plane process is
    deployed yet, so Control's own role classes (`control_roles`/
    `auditreader_roles`) are excluded from both the `-1` check and the
    demand calculation, and Control's own declared ceiling is never
    compared (a declaration is a permitted maximum, not a fact about
    what is deployed today). Role names are discovered by table
    grant (`_inventory_role_classes`), rather than assumed from a fixed
    literal name. `mitatedbsvc_auditreader` is counted only under the
    Control-plane total (measured: only `mitatedb_api.control_
    composition.build_control_service` ever pools a connection against
    it, `mitatedb_api.main.build_app` never does). This item's own output
    always carries `control_deployed`: `true` unless `--control-
    not-deployed` was given."""
    concurrency = args.concurrency
    data_process_ceiling = args.data_process_ceiling
    data_process_count_total = args.data_process_count_total
    control_not_deployed = args.control_not_deployed
    control_process_ceiling = args.control_process_ceiling
    control_process_count_total = args.control_process_count_total
    reserved_connections = args.reserved_connections
    control_deployed = not control_not_deployed

    def _result(judgment: str, *, remediation_required: bool = False) -> dict:
        return {"judgment": judgment, "remediation_required": remediation_required, "control_deployed": control_deployed}

    if concurrency is None:
        return _result("unknown")
    if data_process_ceiling is None or data_process_count_total is None:
        return _result("unknown")
    if not control_not_deployed and (control_process_ceiling is None or control_process_count_total is None):
        return _result("unknown")

    try:
        with conn.cursor() as cur:
            cur.execute("SHOW max_connections")
            (max_connections_text,) = cur.fetchone()
        max_connections = int(max_connections_text)
    except (psycopg.Error, ValueError, TypeError):
        return _result("unknown")

    try:
        api_roles, control_roles, auditreader_roles = _inventory_role_classes(conn, schema)
    except psycopg.Error:
        return _result("unknown")

    if not api_roles or (not control_not_deployed and not control_roles):
        return _result("unknown")

    try:
        with conn.cursor() as cur:
            applications_table = sql.Identifier(schema, "applications")
            cur.execute(sql.SQL(
                "SELECT runtime_role, developer_role FROM {table} "
                "WHERE runtime_role IS NOT NULL AND developer_role IS NOT NULL ORDER BY application_id"
            ).format(table=applications_table))
            app_roles = cur.fetchall()
    except psycopg.Error:
        return _result("unknown")

    # When Control is declared not-deployed, Control's own role
    # classes are excluded from both the -1 check below and demand --
    # an empty exclusion set (no such role found by grant) is not itself
    # a reason to fall back to unknown.
    excluded_roles = (set(control_roles) | set(auditreader_roles)) if control_not_deployed else set()
    role_names = sorted(
        (set(api_roles) | set(control_roles) | set(auditreader_roles) | {name for pair in app_roles for name in pair})
        - excluded_roles
    )
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT rolname, rolconnlimit FROM pg_roles WHERE rolname = ANY(%s)", [role_names])
            limits = dict(cur.fetchall())
    except psycopg.Error:
        return _result("unknown")

    if any(limits.get(name) == -1 for name in role_names):
        return _result("unknown")

    api_floor = platform_declarations._API_ROLE_STORE_COUNT * concurrency
    controlplane_floor = platform_declarations._CONTROLPLANE_ROLE_POOL_FLOOR
    auditreader_floor = platform_declarations._AUDITREADER_ROLE_POOL_FLOOR

    api_demand = data_process_count_total * api_floor
    if control_not_deployed:
        controlplane_demand = 0
        auditreader_demand = 0
    else:
        controlplane_demand = control_process_count_total * controlplane_floor
        auditreader_demand = control_process_count_total * auditreader_floor if auditreader_roles else 0

    condition_1_ok = True
    for role in api_roles:
        if limits.get(role, 0) < api_demand:
            condition_1_ok = False
    if not control_not_deployed:
        for role in control_roles:
            if limits.get(role, 0) < controlplane_demand:
                condition_1_ok = False
        for role in auditreader_roles:
            if limits.get(role, 0) < auditreader_demand:
                condition_1_ok = False
    app_role_demand = data_process_count_total * concurrency
    for runtime_role, developer_role in app_roles:
        if limits.get(runtime_role, 0) < app_role_demand or limits.get(developer_role, 0) < app_role_demand:
            condition_1_ok = False

    try:
        declarations = platform_declarations.read_platform_declarations(
            conn, schema=schema, ops_module=platform_declarations.PEER_MODULE,
            migration=platform_declarations.MIGRATION_NUMBER,
        )
    except platform_declarations.PlatformDeclarationError as exc:
        # B-14: a missing declaration means headroom genuinely cannot be
        # cross-checked against the declared process_ceilings -- unknown
        # with remediation_required, never silently skipped. A PRESENT
        # but malformed declaration is blocked, never treated as absent.
        if _inventory_declaration_error_is_missing(exc):
            return _result("unknown", remediation_required=True)
        return _result("blocked")
    except psycopg.Error:
        return _result("unknown")
    declared_process_ceilings = declarations.process_ceilings

    if declared_process_ceilings.data != data_process_ceiling:
        return _result("blocked")
    # Control's own declared ceiling is a permitted maximum, not a
    # fact about what is deployed today -- never compared when Control
    # is declared not-deployed.
    if not control_not_deployed and declared_process_ceilings.control != control_process_ceiling:
        return _result("blocked")

    if not condition_1_ok:
        return _result("blocked")

    app_shared_demand = app_role_demand if app_roles else 0
    total_demand = api_demand + controlplane_demand + auditreader_demand + app_shared_demand + _INVENTORY_MAX_CONCURRENT_CONNECTIONS

    if reserved_connections is None:
        return _result("unknown")

    if total_demand + reserved_connections > max_connections:
        return _result("blocked")

    return _result("confirmed")


def _inventory_exit_code(report: dict) -> int:
    """0 only when every DB-layer-judged item is confirmed (item (1) now
    carries its OWN `judgment`, mapped from `comparison` by
    `_INVENTORY_COMPARISON_TO_JUDGMENT`, supervisor ruling B-13 -- read
    exactly like every other item's `judgment`; `unjudged_items` is
    metadata, never itself an item); 2 whenever any judged item is
    blocked/unknown -- never 1, which `cmd_inventory` reserves for a
    failure that happens before any item judgment exists at all."""
    for key, item in report.items():
        if key == "unjudged_items":
            continue
        if item["judgment"] != "confirmed":
            return 2
    return 0


# ===========================================================================
# `apply-platform-migration` -- applies one platform migration file
# (never a per-application upgrade, never the bootstrap-only 0001/0002)
# a second (or later) time against a running cluster. Against
# production, run it only through the runbook's gated procedure
# (docs/cloud-run-cloud-sql.md section 10).
# ===========================================================================
# history: CH-0538

#: the platform migrations `apply-platform-migration` accepts --
#: every migration that neither takes a `:app_id` psql variable nor is a
#: bootstrap-only, once-ever migration (0001/0002).
_PLATFORM_MIGRATION_FILENAMES: tuple[str, ...] = (
    "0005_application_audit.sql",
    "0007_platform_declarations.sql",
    "0011_process_ceilings.sql",
    "0012_role_connection_limits.sql",
    "0013_role_statement_timeouts.sql",
    "0014_role_connection_limits_rollout.sql",
)

#: the psql `-v NAME=VALUE` variables each file above references,
#: by filename -- an argument this table does not list for a file is
#: refused, and a variable the table lists but the operator omitted is
#: refused too (`_platform_migration_variables`). Equality against each
#: file's own real `:name` references is a static test
#: (`test_ops_apply_platform_migration.py`).
_PLATFORM_MIGRATION_VARIABLE_TABLE: dict[str, tuple[str, ...]] = {
    "0005_application_audit.sql": (),
    "0007_platform_declarations.sql": ("api_role", "controlplane_role"),
    "0011_process_ceilings.sql": (),
    "0012_role_connection_limits.sql": (),
    "0013_role_statement_timeouts.sql": (),
    "0014_role_connection_limits_rollout.sql": (),
}

#: design D-2: `file -> the LATER accepted files that redefine at least
#: one of file's own targets (the same role/function's own CONNECTION
#: LIMIT, a role-level SET parameter, or a CREATE OR REPLACE FUNCTION
#: body)` -- a file with a NON-EMPTY entry here, given without every one
#: of its own listed successors later in the SAME `apply-platform-
#: migration` call, is refused (`_validate_platform_migration_run`). A
#: file absent from this table (or with an empty tuple) has no known
#: successor and may always be applied alone. This table is proved
#: equal to the "target -> defining files" map derived directly from
#: the 6 accepted migration files themselves, folded to file
#: granularity, by a static test (design
#: `docs/design/MITATEDB_PLATFORM_MIGRATION_RUN_V0_1.md` D-3,
#: `test_ops_apply_platform_migration.py`) -- this table is the side
#: that must keep matching that derivation, never the other way round.
_PLATFORM_MIGRATION_SUPERSEDED_BY: dict[str, tuple[str, ...]] = {
    "0012_role_connection_limits.sql": (
        "0013_role_statement_timeouts.sql",
        "0014_role_connection_limits_rollout.sql",
    ),
    "0013_role_statement_timeouts.sql": (
        "0014_role_connection_limits_rollout.sql",
    ),
}

#: matches a psql `:name`/`:'name'`/`:"name"` variable
#: reference, but never a `::` type cast -- the negative lookbehind/
#: lookahead on both sides of the leading colon reject a colon that is
#: itself adjacent to another colon.
_PSQL_VARIABLE_RE = re.compile(
    r"(?<!:):(?!:)(?:'([A-Za-z_][A-Za-z0-9_]*)'|\"([A-Za-z_][A-Za-z0-9_]*)\"|([A-Za-z_][A-Za-z0-9_]*))"
)


def _strip_sql_line_comments(text: str) -> str:
    """Drops everything from the first `--` onward on each
    line -- a `:name` reference inside a `--` comment is never a real
    psql variable reference."""
    return "\n".join(line[: line.find("--")] if "--" in line else line for line in text.splitlines())


def _extract_psql_variables(text: str) -> "set[str]":
    """Every psql variable `text` references, excluding
    `--` line comments and `::` type casts."""
    stripped = _strip_sql_line_comments(text)
    found: "set[str]" = set()
    for match in _PSQL_VARIABLE_RE.finditer(stripped):
        name = match.group(1) or match.group(2) or match.group(3)
        if name:
            found.add(name)
    return found


def _resolve_platform_migration_file(filename: str) -> Path:
    """`filename` must be a bare name (no path separator), a
    member of `_PLATFORM_MIGRATION_FILENAMES`, and resolve to a real
    file INSIDE `_migrations_dir()` -- both sides are resolved (symlinks
    followed) before the containment check, so a migrations directory
    that is itself a symlink still accepts a known file, while a file
    that resolves outside the directory (e.g. a symlink planted in its
    place) is refused. `_migrations_dir()` (`MITATEDB_MIGRATIONS_DIR`) is
    the operator-set trust boundary this check keeps `filename` inside
    of. The rejected value itself is never echoed back."""
    if "/" in filename or (os.sep != "/" and os.sep in filename):
        _die("apply-platform-migration: FILENAME must not contain a path separator")
    if filename not in _PLATFORM_MIGRATION_FILENAMES:
        _die("apply-platform-migration: FILENAME must be one of the known platform migration files")
    directory = _migrations_dir().resolve()
    candidate = (directory / filename).resolve()
    try:
        candidate.relative_to(directory)
    except ValueError:
        _die("apply-platform-migration: resolved migration file path is outside the migrations directory")
    if not candidate.is_file():
        _die("apply-platform-migration: migration file not found")
    return candidate


def _validate_platform_migration_run(files: "tuple[str, ...]") -> None:
    """Design D-2's 2 acceptance conditions for a RUN of FILENAMEs,
    checked once every element of `files` has already been resolved by
    `_resolve_platform_migration_file` (so each is already a known
    member of `_PLATFORM_MIGRATION_FILENAMES`) -- refuses (fixed
    message, `_die`, exit code 2) before `_platform_migration_
    variables` or any psql subprocess runs:

    1. `files` is strictly ascending in `_PLATFORM_MIGRATION_FILENAMES`
       order with no repeat.
    2. every file's own successors in `_PLATFORM_MIGRATION_SUPERSEDED_
       BY` (if any -- a file absent from that table, or mapped to an
       empty tuple, has none and always passes this condition on its
       own) are present in `files`, later than that file. The rejection
       names the FULL required run (that file plus its own successors,
       built from `_PLATFORM_MIGRATION_SUPERSEDED_BY` and
       `_PLATFORM_MIGRATION_FILENAMES`), never `files` itself -- the
       operator's own rejected values are not echoed (`ops.py`:2696's
       existing rule)."""
    positions = {name: i for i, name in enumerate(_PLATFORM_MIGRATION_FILENAMES)}
    indices = [positions[name] for name in files]
    if indices != sorted(indices) or len(set(indices)) != len(indices):
        _die("apply-platform-migration: FILENAMEs must be given in migration order, each at most once")
    given = set(files)
    for name in files:
        successors = _PLATFORM_MIGRATION_SUPERSEDED_BY.get(name, ())
        missing = [succ for succ in successors if succ not in given]
        if missing:
            required_run = (name,) + successors
            _die(
                f"apply-platform-migration: {name} is superseded by a later platform migration; "
                "apply the whole run in one call, in this order: " + " ".join(required_run)
            )


def _platform_migration_variables(files: "tuple[str, ...]", args: argparse.Namespace) -> "dict[str, str]":
    """Reconciles the operator-supplied `--api-role`/
    `--controlplane-role` values against the UNION of every file in
    `files`'s own required set (`_PLATFORM_MIGRATION_VARIABLE_TABLE`) --
    a required variable no file in `files` references, or a supplied
    variable no file in `files` references, is refused (fixed message,
    no psql subprocess started). Each file in the run is later invoked
    with only its OWN required subset (`cmd_apply_platform_migration`),
    never this whole union -- this function only checks that the union
    is exactly what the operator supplied. The union is walked in
    `files` order (already `_PLATFORM_MIGRATION_FILENAMES` order, D-2)
    and, within each file, that file's own `_PLATFORM_MIGRATION_
    VARIABLE_TABLE` tuple order -- a missing-variable message therefore
    always names the SAME variable for the SAME input, never one that
    varies run-to-run with Python's own (hash-randomized) `set`
    iteration order. An unexpected (extra) variable's own rejection
    names the ONE file it does not belong to only when `files` itself
    is one file; a run of 2+ files names no file (no single file in a
    multi-file run is the "right" one to blame for an extra variable).

    History: CH-0540
    """
    required_ordered: "list[str]" = []
    for name in files:
        for var in _PLATFORM_MIGRATION_VARIABLE_TABLE[name]:
            if var not in required_ordered:
                required_ordered.append(var)
    supplied: "dict[str, str]" = {}
    if args.api_role is not None:
        supplied["api_role"] = args.api_role
    if args.controlplane_role is not None:
        supplied["controlplane_role"] = args.controlplane_role
    missing = [name for name in required_ordered if name not in supplied]
    if missing:
        var = missing[0]
        naming_file = next(name for name in files if var in _PLATFORM_MIGRATION_VARIABLE_TABLE[name])
        _die(f"apply-platform-migration: {naming_file} requires --{var.replace('_', '-')}")
    extra = [name for name in supplied if name not in required_ordered]
    if extra:
        var = extra[0]
        if len(files) == 1:
            _die(f"apply-platform-migration: {files[0]} does not accept --{var.replace('_', '-')}")
        _die(f"apply-platform-migration: no file in this run accepts --{var.replace('_', '-')}")
    return supplied


def cmd_apply_platform_migration(args: argparse.Namespace) -> int:
    """Applies one platform migration file a second (or later) time
    against a running cluster. Against production, run it only through
    the runbook's gated procedure (docs/cloud-run-cloud-sql.md section
    10). DSN comes from `MITATEDB_PROVISION_DSN` only, never an
    argument (design Z-8/D-10).

    History: CH-0539
    """
    lock_timeout = _validate_lock_timeout_value(args.lock_timeout)
    files = tuple(args.file)
    scripts = [_resolve_platform_migration_file(name) for name in files]
    _validate_platform_migration_run(files)
    variables = _platform_migration_variables(files, args)
    dsn = _provision_dsn()
    _require_psql_16_or_newer()
    env = _psql_connection_env(dsn)
    env["PGOPTIONS"] = _with_lock_timeout_option(env.get("PGOPTIONS"), lock_timeout)
    applied: "list[str]" = []
    for name, script in zip(files, scripts):
        argv = ["psql", "-v", "ON_ERROR_STOP=1"]
        for var_name in _PLATFORM_MIGRATION_VARIABLE_TABLE[name]:
            argv += ["-v", f"{var_name}={variables[var_name]}"]
        argv += ["-f", str(script)]
        result = subprocess.run(argv, capture_output=True, text=True, env=env)
        if result.returncode != 0:
            not_run = files[len(applied) + 1:]
            message = (
                f"apply-platform-migration failed at {name}\n"
                f"applied: {' '.join(applied) if applied else '(none)'}\n"
                f"not run: {' '.join(not_run) if not_run else '(none)'}\n"
                "An applied file may still carry a value a later file in this run replaces. "
                "Re-run the whole run from its first file; every file in it is idempotent.\n"
                f"{result.stdout}\n{result.stderr}"
            )
            _die(_redact_connection_values(message, dsn))
        print(f"applied {name}")
        applied.append(name)
    return 0


def _inventory_input_reject(message: str) -> NoReturn:
    """(8)'s own input-shape rejections:
    exit code 1, never 2 (which this subcommand reserves for a completed
    item judgment) -- a fixed message, never the rejected value, and no
    database connection is opened first."""
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)


def _inventory_validate_headroom_inputs(args: argparse.Namespace) -> None:
    """Item (8)'s input-shape checks that need BOTH halves of an
    argument pair already parsed, so they cannot live in `argparse`
    `type=` alone: run before any database connection
    opens."""
    if args.control_not_deployed and args.control_process_ceiling is not None:
        _inventory_input_reject("--control-not-deployed and --control-process-ceiling are mutually exclusive")
    if args.control_not_deployed and args.control_process_count_total is not None:
        _inventory_input_reject("--control-not-deployed and --control-process-count-total are mutually exclusive")
    if (
        args.data_process_ceiling is not None and args.data_process_count_total is not None
        and args.data_process_count_total < args.data_process_ceiling
    ):
        _inventory_input_reject("--data-process-count-total must not be less than --data-process-ceiling")
    if (
        args.control_process_ceiling is not None and args.control_process_count_total is not None
        and args.control_process_count_total < args.control_process_ceiling
    ):
        _inventory_input_reject("--control-process-count-total must not be less than --control-process-ceiling")


def cmd_inventory(args: argparse.Namespace) -> int:
    """Gate-0 DB-layer read-only judgments. Prints exactly one JSON
    object to stdout; never writes a file of its own. A connection
    failure propagates to `main`'s own top-level `except psycopg.Error`
    handler (type name and fixed text only, exit 1) -- there is nothing
    item-specific to report before a connection to the platform database
    even exists. Item (8)'s own input-shape checks (`_inventory_validate_
    headroom_inputs`) run first, before that connection ever opens."""
    _inventory_validate_headroom_inputs(args)
    dsn = os.environ.get(platform_declarations.PROVISION_DSN_ENV)
    if not dsn:
        print(_INVENTORY_TOOL_FAILURE_MESSAGE, file=sys.stderr)
        return 1
    schema = _schema()
    conn = _inventory_connect(dsn)
    try:
        if not _inventory_confirmed_read_only(conn):
            print(_INVENTORY_TOOL_FAILURE_MESSAGE, file=sys.stderr)
            return 1
        report = {
            "connection": _inventory_connection_match(dsn, args.cloud_sql_connection_name),
            "declarations": _inventory_declarations(conn, schema),
            "migrations": _inventory_migrations(conn, dsn, schema),
            "credentials": _inventory_credentials(conn, schema),
            "ddl_lock": _inventory_ddl_lock_declaration(conn, schema),
            "connection_headroom": _inventory_connection_headroom(conn, schema, args),
            "unjudged_items": list(_INVENTORY_UNJUDGED_ITEMS),
        }
    finally:
        conn.close()
    print(json.dumps(report, sort_keys=True))
    return _inventory_exit_code(report)

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
    p.add_argument(
        "--lock-timeout", required=True, metavar="VALUE",
        help="lock_timeout to set on the psql session before running the deprovision script "
             "(a positive integer optionally followed by ms, s, or min; no default)",
    )
    p.set_defaults(func=cmd_deprovision)

    # ---- Q4 phase declaration-management command family -- provision
    # DSN only, no control credential needed for any of these
    # (`MITATEDB_PROVISION_DSN`, the same env var
    # `deprovision`/`audit-report` above already require).
    # history: CH-0438

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
        "declare-process-ceilings",
        help="declare the single, shared `process_ceilings` row both processes read (design D-5 (ii)) -- "
             "REPLACES the entire row. Both --data and --control are required positive integers: how many "
             "processes may serve the data / control plane's own base URL at the same time. Requires "
             "MITATEDB_PROVISION_DSN. Restart both processes afterward (startup snapshot)",
    )
    p.add_argument("--data", type=int, required=True, metavar="N")
    p.add_argument("--control", type=int, required=True, metavar="N")
    p.set_defaults(func=cmd_declare_process_ceilings)

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

    # ---- Q4 phase per-application platform-upgrade command family --
    # provision DSN only, same as the declaration family above.
    # history: CH-0439

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
    p.add_argument(
        "--lock-timeout", required=True, metavar="VALUE",
        help="lock_timeout to set on the psql session before running each per-application upgrade script "
             "(a positive integer optionally followed by ms, s, or min; no default)",
    )
    p.set_defaults(func=cmd_upgrade_applications)

    p = sub.add_parser(
        "upgrade-status",
        help="read-only per-application platform-upgrade applied/pending tally (design D-5) -- the sole "
             "peer-local visualization U-1 permits; never mounted on any HTTP surface. Does not change or "
             "replace list-applications. Requires MITATEDB_PROVISION_DSN",
    )
    p.add_argument("--application", default=None, metavar="ID", help="limit to one application id")
    p.set_defaults(func=cmd_upgrade_status)

    p = sub.add_parser(
        "apply-platform-migration",
        help="apply a RUN of one or more platform migration files, in migration order, a second (or later) "
             "time against MITATEDB_PROVISION_DSN -- restricted to the known re-appliable platform migrations ("
             + "/".join(name[:4] for name in _PLATFORM_MIGRATION_FILENAMES)
             + "; the bootstrap-only 0001/0002 are never accepted here). A file with a later file that "
             "redefines one of its own targets is refused unless every one of those later files is given "
             "too, in the same call. Against production, run it "
             "only through the runbook's gated procedure (docs/cloud-run-cloud-sql.md section 10)",
    )
    p.add_argument(
        "file", metavar="FILENAME", nargs="+",
        help="one or more of the known platform migration file names (no path), in migration order",
    )
    p.add_argument(
        "--lock-timeout", required=True, metavar="VALUE",
        help="lock_timeout to set on the psql session before applying the file (a positive integer optionally "
             "followed by ms, s, or min; no default)",
    )
    p.add_argument("--api-role", default=None, metavar="ROLE", help="0007's own :api_role psql variable")
    p.add_argument(
        "--controlplane-role", default=None, metavar="ROLE",
        help="0007's own :controlplane_role psql variable",
    )
    p.set_defaults(func=cmd_apply_platform_migration)

    p = sub.add_parser(
        "inventory",
        help="read-only Gate-0 DB-layer judgments -- never mounted on any HTTP surface, never touches "
             "platform state. Prints one JSON object to stdout. Requires MITATEDB_PROVISION_DSN (env only, "
             "never an argument)",
    )
    p.add_argument(
        "--cloud-sql-connection-name", default=None, metavar="NAME",
        help="the Cloud SQL instance connection name the platform layer read from the running revision -- "
             "omit to leave item (1) unknown",
    )
    p.add_argument(
        "--concurrency", type=_inventory_positive_int, default=None, metavar="N",
        help="the platform's declared MITATEDB_MAX_CONCURRENCY value (a positive integer) -- omit to leave "
             "item (8) unknown",
    )
    p.add_argument(
        "--data-process-ceiling", type=_inventory_positive_int, default=None, metavar="N",
        help="Data-plane process ceiling for the NEW candidate revision (a positive integer, compared "
             "against the process_ceilings declaration) -- omit to leave item (8) unknown",
    )
    p.add_argument(
        "--data-process-count-total", type=_inventory_positive_int, default=None, metavar="N",
        help="WORST-CASE Data-plane process count: the sum of the process ceilings of every revision that "
             "can serve at the same time, plus the NEW candidate's own ceiling (a positive integer, used "
             "for connection demand). Never the number of instances running at the moment of the read -- "
             "omit to leave item (8) unknown",
    )
    p.add_argument(
        "--control-process-ceiling", type=_inventory_positive_int, default=None, metavar="N",
        help="Control-plane process ceiling for the NEW candidate revision -- omit (with --control-not-"
             "deployed absent too) to leave item (8) unknown",
    )
    p.add_argument(
        "--control-process-count-total", type=_inventory_positive_int, default=None, metavar="N",
        help="WORST-CASE Control-plane process count: the sum of the process ceilings of every revision "
             "that can serve at the same time, plus the NEW candidate's own ceiling. Never the number of "
             "instances running at the moment of the read -- omit (with --control-not-deployed absent "
             "too) to leave item (8) unknown",
    )
    p.add_argument(
        "--control-not-deployed", action="store_true",
        help="declare that no Control-plane process is deployed yet -- the only way to omit both Control "
             "process arguments; excludes Control's own roles from item (8)'s -1 check, demand calculation, "
             "and declaration comparison. Mutually exclusive with --control-process-ceiling/--control-"
             "process-count-total",
    )
    p.add_argument(
        "--reserved-connections", type=_inventory_nonnegative_int, default=None, metavar="N",
        help="platform-layer connection reserve (superuser_reserved_connections plus any Cloud SQL reserve; "
             "a non-negative integer -- 0 means no reserve) -- omit to leave item (8)'s aggregate check unknown",
    )
    p.set_defaults(func=cmd_inventory)

    def _inventory_usage_error(message: str, _parser: argparse.ArgumentParser = p) -> NoReturn:
        # Every argparse usage error against `inventory`'s own
        # arguments (e.g. `--concurrency 0`) exits 1, never argparse's
        # default 2 -- this subcommand reserves 2 for a completed item
        # judgment that is blocked/unknown.
        _parser.print_usage(sys.stderr)
        _parser.exit(1, f"{_parser.prog}: error: {message}\n")

    p.error = _inventory_usage_error

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args, extra_argv = parser.parse_known_args(argv)
    if extra_argv:
        # `inventory`'s own usage-error convention (exit 1, never
        # argparse's default 2, which this subcommand reserves for a
        # completed item judgment) extends to unrecognized/extra
        # arguments too, before any database connection opens -- the
        # rejected value(s) are never echoed. Every other subcommand
        # keeps argparse's own default (exit 2) for this same case.
        if getattr(args, "command", None) == "inventory":
            print("error: unrecognized arguments", file=sys.stderr)
            raise SystemExit(1)
        parser.error(f"unrecognized arguments: {' '.join(extra_argv)}")
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
        print(f"error: database operation failed ({type(exc).__name__})", file=sys.stderr)
        return 1
    except Exception as exc:
        # design D-2: every OTHER exception reaching this top level is
        # reported the SAME way -- exception TYPE NAME plus fixed text,
        # never `str(exc)` and never a traceback (SI-10's own "raw stack
        # traces in public responses" -- this CLI's own stderr is that
        # surface for an operator running it, and for the HTTP
        # conformance adapter's own subprocess capture of it, R-8).
        # `BaseException` subclasses that are NOT `Exception` (`SystemExit`/
        # `KeyboardInterrupt`, `argparse`'s own `--help`/usage-error exit)
        # are deliberately left uncaught -- this module's own docstring
        # already names that one unreachable cell in the exit-code table.
        print(f"error: unexpected failure ({type(exc).__name__})", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
