"""r2db-api provisional control-plane CLI: ``python -m r2db_api.ops``.

*** THIS IS A PROVISIONAL, OUT-OF-BAND MANAGEMENT TOOL -- CCR-14 (control
plane endpoints) IS UNDECIDED AS OF THIS WRITING (spec/CCR_DISPOSITION.md).
IT REMAINS THE ONLY WAY TO MANAGE CREDENTIALS/APPLICATIONS UNTIL CCR-14 IS
RESOLVED. *** (design docs/design/
R2DB_CREDENTIAL_PERSISTENCE_AND_COMPOSITION_ROOT_V1.md, P2-D6.) There is
deliberately no HTTP control surface anywhere in this package (design §0):
every operation below runs out-of-band, against the platform database
directly, never through `r2db_api.http`'s application-facing routes. Once
CCR-14 is resolved, an in-band replacement (if adopted) should supersede
this CLI; nothing here should be assumed to be a permanent interface.

KNOWN GAP -- READ BEFORE RELYING ON THIS FOR PRODUCTION CHANGE CONTROL:
`r2db-api` has no durable audit sink yet (existing outstanding work,
unrelated to this change). `security/SECURITY_INVARIANTS_V1.md`'s
`audit.sink_failure_policy` requires control-plane changes to fail closed
when an audit record of them cannot be durably written. Because no durable
sink exists, every operation this CLI performs happens *without* a
canonical, persisted audit trail -- this is a real, currently-open gap,
not something this CLI silently papers over. Until a durable audit sink
lands, treat every run of this CLI as needing its own separate,
out-of-band record (e.g. your own change-management log) of who ran what,
when, and why.

Connects to the platform database as `r2dbsvc_control` (`R2DB_CONTROL_DSN`)
-- the same role `0002`/`0003`/`0004`'s provisioning scripts already run
as, and never the strictly read-only `r2dbsvc_api` role the running API
process itself uses (P2-D3: a compromised API process cannot reach this
role's privileges at all). Also requires `R2DB_CREDENTIAL_PEPPER` -- the
same pepper value the running API process is configured with -- to compute
verifiers for `issue-credential`/`rotate-credential`; a credential issued
with the wrong pepper will never authenticate.
"""
from __future__ import annotations

import argparse
import os
import secrets
import sys
from typing import NoReturn, Sequence

import psycopg
from psycopg import sql

from .credential_store import DEFAULT_SCHEMA, PostgresCredentialStore
from .errors import FoundationError

_CREDENTIAL_ID_PREFIX = "crd_"


def _schema() -> str:
    # Not part of P2-D6's documented environment contract -- added purely
    # so this repository's own tests can point this CLI at a throwaway,
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


def cmd_issue_credential(args: argparse.Namespace) -> int:
    store = _store()
    try:
        credential_id = _new_credential_id()
        secret = _new_secret()
        store.add(credential_id, args.slug, args.role, secret)
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
        store.rotate(args.credential_id, secret)
    finally:
        store.close()
    _print_issued(args.credential_id, secret)
    return 0


def cmd_revoke_credential(args: argparse.Namespace) -> int:
    store = _store()
    try:
        store.set_state(args.credential_id, revoked=True)
    finally:
        store.close()
    print(f"credential {args.credential_id} revoked")
    return 0


def cmd_disable_credential(args: argparse.Namespace) -> int:
    store = _store()
    try:
        store.set_state(args.credential_id, enabled=False)
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
        store.delete(args.credential_id)
    finally:
        store.close()
    print(f"credential {args.credential_id} deleted")
    return 0


def cmd_enable_credential(args: argparse.Namespace) -> int:
    store = _store()
    try:
        store.set_state(args.credential_id, enabled=True)
    finally:
        store.close()
    print(f"credential {args.credential_id} enabled")
    return 0


def cmd_list_credentials(_args: argparse.Namespace) -> int:
    dsn = _control_dsn()
    # Never selects `verifier` -- this command must not be able to leak the
    # one secret-derived value the platform database stores, even to an
    # operator who only asked to list credentials (P2-D1's own "verifier
    # only, never the secret" boundary extends to this listing too).
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
        print(f"{slug:<24}{str(enabled):<9}{database_name:<32}{provisioned_at}")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m r2db_api.ops",
        description=(
            "r2db-api PROVISIONAL control-plane CLI -- out-of-band credential/"
            "application management, kept only until CCR-14 (control plane "
            "endpoints) is resolved (spec/CCR_DISPOSITION.md: undecided as of "
            "this writing). No durable audit sink exists yet for the changes "
            "this CLI makes -- see this module's docstring (`pydoc r2db_api.ops`) "
            "for that gap before relying on this for production change control."
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
