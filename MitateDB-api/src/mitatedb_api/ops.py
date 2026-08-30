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
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import NoReturn, Sequence

import psycopg

from .control_audit import insert_control_audit_row
from .control_credential_store_postgres import DEFAULT_SCHEMA, PostgresControlCredentialStore
from .control_plane import bootstrap_control_credential, reset_control_credentials
from .credential_store_postgres import assert_pepper_separation
from .errors import (AuthenticationError, AuthorizationError, AuthorizationStateUnavailable,
                     CapabilityError, ConflictError, DestructiveConfirmationRequired,
                     FoundationError, NotFoundError, ResourceLimitError, StorageConfigurationError,
                     ValidationError)

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


def _print_issued(credential_id: str, secret: str) -> None:
    # The secret is shown exactly once, here, and is never written anywhere
    # by this process -- copy it now, it cannot be recovered later.
    print(f"credential_id: {credential_id}")
    print(f"secret: {secret}")
    print("(the secret above is shown once and is not stored anywhere -- save it now)")
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
