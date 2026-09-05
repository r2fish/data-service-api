"""Q4 phase D-1/D-2 (docs/design/Q4_DB_SIDE_SINGLE_TRUTH_V1.md v1.3): reads
and validates `<registry>.platform_declarations` (D-2: the single source of
`surfaces` / `audit_coalescing_window_ms` / `audit_writer_roles`), and runs
the PostgreSQL role-setting dual check (D-1(b)) that REPLACES this peer's
former per-connection `SET SESSION` audit-writer timeouts -- `pg_db_role_
setting` (set once, out-of-band, by `python -m mitatedb_api.ops
set-platform-timeouts`, migration `0007_platform_declarations.sql`'s own
`ALTER ROLE ... SET` + `audit_writer_roles` seed) is now the single source
of both the two writer timeouts AND which roles are declared audit writers
(D-2(h)) -- both `main.build_app` (data-plane) and `control_composition.
build_control_service` (control-plane) check their own writer role's
declared-vs-effective value at startup rather than setting it themselves,
and first confirm their own login role is even ONE of the declared writers
(F-13).

Fail-fast only: every function here either returns a validated value or
raises `PlatformDeclarationError` -- always a STARTUP failure (composition
root), never surfaced over HTTP (design §3.8: "F-1〜F-11 と F-13 はプロセス
起動時の出力であり、API 応答や公開 endpoint には現れない"). The one
cell-open-time, API-facing condition (F-12, D-3(f)) is a LATER work
package's own `platform_upgrades` module, not this one.

Reference-implementation module (supervisor ruling 2026-09-05,
`{scratchpad}/rulings-q4-wp12-rework.md` §1): every name, signature and
return type below is shared verbatim with r2db-api's own same-named
realization -- peer differences close entirely over the ARGUMENTS a
caller passes in (`schema`, `ops_module`, `migration`, `names`,
`declared_roles`), never over a literal `mitatedb`/`MITATEDB`/`r2db`/
`R2DB` string baked into a pinned function's own body. A handful of
message-building helpers below (`_f1_message`/`_f2_message`/`_f8_message`/
`_f13_message`'s own `schema` mention) instead reach for this MODULE's own
peer-local constants (`PEER_MODULE`, `MIGRATION_NUMBER`, `MIGRATION_
FILENAME`, `PROVISION_DSN_ENV`, `PEER_DIR`, `DEFAULT_SCHEMA`) by bare
name rather than taking them as parameters -- those constants are
peer-specific VALUES but peer-IDENTICAL NAMES, so the referencing function
body stays textually isomorphic across peers even though it is never
literally handed those values as arguments. This is a deliberate,
documented implementation choice (not specified verbatim by the ruling,
which only fixes the signatures of the read/validate/derive/check
functions listed in §1) -- see this WP's own completion report for the
two points of doubt this raises.

Peer-local, independently maintained (no cross-peer sharing, requester
ruling 2026-09-03) -- this module's read/validate/derive/check helpers are
pinned isomorphic to r2db-api's own same-named realizations by
`_ISOMORPHIC_TARGETS` (`tests/test_audit_query.py`).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence
from urllib.parse import urlsplit

import psycopg
from psycopg import sql

from .identifiers import _IDENTIFIER as _PG_IDENTIFIER_PATTERN
from .pg_timeouts import ms_from_pg_timeout_text

#: Registry schema this table lives in (D-2(a)) -- the production value.
#: Composition roots pass their OWN resolved schema (possibly a
#: throwaway-prefixed test schema) explicitly to every function below;
#: this constant is consulted only by the small set of message-building
#: helpers that are not handed `schema` as a parameter (this module's own
#: docstring above explains why that is safe).
DEFAULT_SCHEMA = "mitatedb_registry"
TABLE_NAME = "platform_declarations"

#: The platform single-shot migration that creates the table and seeds
#: the two writer roles' timeout role-settings AND the `audit_writer_
#: roles` row (design §8 migration allocation, requester ruling
#: 2026-09-05: MitateDB `0007`; D-2(h) folds the role-seed into the SAME
#: migration).
MIGRATION_NUMBER = "0007"
MIGRATION_FILENAME = "0007_platform_declarations.sql"

#: `<peer>` in every fail-fast message's "next ops command" (design
#: §3.8).
PEER_MODULE = "mitatedb_api"

#: F-8's own "apply it with" psql invocation (design §3.8 F-8) -- peer-
#: specific literal strings referenced by bare name from `_f8_message`
#: only (never threaded through `read_platform_declarations`'s own fixed
#: 3-keyword-argument signature, design ruling §1).
PROVISION_DSN_ENV = "MITATEDB_PROVISION_DSN"
PEER_DIR = "MitateDB-api"

#: F-6's own env var name -- referenced by bare name from `_f6_forward_
#: message`/`_f6_reverse_message` only (Agent C isomorphism convergence,
#: rulings-q4-wp12-rework.md sec.1: the literal env var name was
#: previously baked directly into those two pinned message bodies, which
#: cannot normalize-diff empty against r2db-api's own differently-spelled
#: literal -- this constant closes that the same way `PROVISION_DSN_ENV`
#: already does for F-8).
CONTROL_PLANE_STATUS_ENV = "MITATEDB_CONTROL_PLANE_STATUS"

_STATEMENT_TIMEOUT_KEY = "statement_timeout"
_IDLE_TIMEOUT_KEY = "idle_in_transaction_session_timeout"
_TIMEOUT_KEYS = (_STATEMENT_TIMEOUT_KEY, _IDLE_TIMEOUT_KEY)

#: `identifiers._IDENTIFIER`'s own `{0,62}` already bounds total length to
#: 63 -- this constant exists only so `validate_audit_writer_roles_value`'s
#: own body reads identically to r2db-api's (that peer's identifier syntax
#: regex does not itself bound length, so it checks this separately;
#: Agent C isomorphism convergence, rulings-q4-wp12-rework.md sec.1).
_PG_IDENTIFIER_MAX_LENGTH = 63

#: D-1(c): the third term `visibility_lag_ms` sums beyond the two writer
#: connection timeouts.
VISIBILITY_LAG_CLOCK_SKEW_MARGIN_MS = 1000

#: The two removed env vars each of F-1/F-2 rejects (D-1(d)/D-2(f)) --
#: composition roots check these against the `Mapping` they were BUILT
#: with, never `os.environ`. Peer-specific literal names -- excluded from
#: the isomorphism table by design (ruling §1: "peer 名を含む定数は対応表
#: に載せない").
REMOVED_TIMEOUT_ENV: tuple[str, ...] = ("MITATEDB_AUDIT_STATEMENT_TIMEOUT_MS", "MITATEDB_AUDIT_IDLE_TIMEOUT_MS")
REMOVED_SURFACE_ENV: tuple[str, ...] = ("MITATEDB_DATA_BASE_URL", "MITATEDB_CONTROL_BASE_URL")

class PlatformDeclarationError(RuntimeError):
    """Every F-1..F-11/F-13 fail-fast condition this module raises. A
    composition-root startup failure only -- never mapped to a contract
    error code, never returned over HTTP (design §3.8's own SI-10 note)."""


@dataclass(frozen=True)
class Surfaces:
    """F-5's own validated return shape (design D-2(d))."""
    data_base_url: str
    control_base_url: Optional[str]


@dataclass(frozen=True)
class PlatformDeclarations:
    """`read_platform_declarations`'s own return shape -- the three rows
    of `<registry>.platform_declarations`, each already validated."""
    surfaces: Surfaces
    audit_coalescing_window_ms: int
    audit_writer_roles: tuple[str, ...]


@dataclass(frozen=True)
class RoleTimeoutCatalog:
    """`read_declared_role_timeouts`'s own return shape -- one writer
    role's two declared `pg_db_role_setting` timeouts, already
    ms-normalized and range-checked (F-7/F-10/F-11)."""
    role: str
    statement_ms: int
    idle_ms: int


# ---------------------------------------------------------------------------
# F-1 / F-2: removed env vars are rejected whenever DEFINED, whatever their
# value (an empty string included) -- design D-1(d)/D-2(f).
# ---------------------------------------------------------------------------


def _f1_message(var_name: str) -> str:
    return (
        f"{var_name} is no longer read (Q4 D-1): the audit writer roles carry statement_timeout / "
        f"idle_in_transaction_session_timeout as PostgreSQL role settings, applied by migration "
        f"{MIGRATION_NUMBER}. This variable is rejected whenever it is defined, whatever its value (an "
        f"empty string included). Unset this variable, then set the value with 'python -m {PEER_MODULE}.ops "
        f"set-platform-timeouts --statement-ms <N> --idle-ms <N>' and restart both processes. Note this "
        f"setting also bounds every other connection made by this role (credential store lookups and "
        f"control-plane registry operations included)."
    )


def _f2_message(var_name: str, *, schema: str) -> str:
    return (
        f"{var_name} is no longer read (Q4 D-2): surfaces are declared in {schema}.platform_declarations, "
        f"created by migration {MIGRATION_NUMBER}. This variable is rejected whenever it is defined, whatever "
        f"its value (an empty string included). Unset this variable, then declare with "
        f"'python -m {PEER_MODULE}.ops declare-surfaces --data-base-url <URL> [--control-base-url <URL>]' "
        f"and restart both processes."
    )


def reject_removed_timeout_env(env: Mapping[str, str], *, names: tuple[str, ...]) -> None:
    """F-1: called by BOTH composition roots before anything else touches
    `platform_declarations`/`pg_db_role_setting` (design §3.7 step 2).
    `names` is the peer-local `REMOVED_TIMEOUT_ENV` tuple -- checked
    against the `env` MAPPING the caller was built with, never
    `os.environ` (design D-1(d))."""
    for name in names:
        if name in env:
            raise PlatformDeclarationError(_f1_message(name))


def reject_removed_surface_env(env: Mapping[str, str], *, names: tuple[str, ...], schema: str) -> None:
    """F-2: same step, same reasoning, the surfaces pair (`REMOVED_
    SURFACE_ENV`). `schema` is the caller's own resolved registry schema
    (design amendment 2026-09-05, N-7): the message must name the real
    schema, not this module's own `DEFAULT_SCHEMA`, since a deployment
    may override it."""
    for name in names:
        if name in env:
            raise PlatformDeclarationError(_f2_message(name, schema=schema))


# ---------------------------------------------------------------------------
# D-2: `<registry>.platform_declarations` read + validate (F-3/F-3c/F-4/
# F-4b/F-5/F-8). Both write (`ops declare-*`) and read paths call the SAME
# `validate_*` functions below (design D-2(d): "検証は書き込み時と読み出し
# 時の両方で行い、両方が同じ Python の検証関数を通る").
# ---------------------------------------------------------------------------


def _f3_message(schema: str, *, ops_module: str) -> str:
    return (
        f"no 'surfaces' row in {schema}.platform_declarations: contract 1.6.0 requires surfaces.data "
        f"unconditionally. Declare it with 'python -m {ops_module}.ops declare-surfaces --data-base-url "
        f"<URL> [--control-base-url <URL>]', then restart both processes."
    )


def _f3c_message(schema: str, *, ops_module: str) -> str:
    """Control-plane-only fail-fast (monitor ruling 2026-09-05, design
    §3.8 F-3c): the `surfaces` row EXISTS but has no `surfaces.control`,
    yet this IS the control process, which always has a control surface
    of its own to declare -- a different condition from F-3 (the row
    itself is absent). Verbatim complied from `{scratchpad}/
    q4-f3c-and-amendments.md` (no paraphrase)."""
    return (
        f"'surfaces' row in {schema}.platform_declarations has no surfaces.control, but this is the "
        f"control-plane process, which always has a control surface to declare (contract 1.6.0: both "
        f"documents return the same surfaces object). Declare it with 'python -m {ops_module}.ops "
        f"declare-surfaces --data-base-url <URL> --control-base-url <URL>', then restart both processes."
    )


def _f4_message(schema: str, *, ops_module: str, migration: str) -> str:
    return (
        f"no 'audit_coalescing_window_ms' row in {schema}.platform_declarations: migration {migration} "
        f"seeds it with the shipped default (60000). Apply that migration, or set the value with "
        f"'python -m {ops_module}.ops declare-coalescing-window --ms <N>', then restart both processes."
    )


def _f4b_window_message(schema: str, value: Any, *, ops_module: str) -> str:
    return (
        f"'audit_coalescing_window_ms' in {schema}.platform_declarations must be a non-negative integer (0 "
        f"means no coalescing), got '{value}'. This table can be edited by hand, so the value is validated "
        f"on every read as well as on write. Re-set it with 'python -m {ops_module}.ops "
        f"declare-coalescing-window --ms <N>', then restart both processes."
    )


def _f4b_writer_roles_message(schema: str, value: Any, *, migration: str) -> str:
    return (
        f"'audit_writer_roles' in {schema}.platform_declarations must be a non-empty JSON array of distinct, "
        f"valid PostgreSQL identifiers, got '{value}'. This table can be edited by hand, so the value is "
        f"validated on every read. This row is written only by migration {migration}, which seeds it with "
        f"the very role names it issues ALTER ROLE for: re-apply that migration to this platform database "
        f"with this deployment's writer role names, then restart both processes."
    )


def _f5_message(field: str, suffix: str, value: Any, *, schema: str, ops_module: str) -> str:
    return (
        f"{field} in {schema}.platform_declarations must be an absolute URL ending in '{suffix}' with no "
        f"trailing slash, got '{value}'. Re-declare it with 'python -m {ops_module}.ops declare-surfaces "
        f"…'."
    )


def _f8_message(schema: str, *, migration: str) -> str:
    return (
        f"relation {schema}.platform_declarations does not exist: migration {migration} (Q4 D-2) has not "
        f"been applied to this platform database. Apply it with 'psql \"${PROVISION_DSN_ENV}\" -f "
        f"{PEER_DIR}/migrations/{MIGRATION_FILENAME}', then restart both processes."
    )


def validate_coalescing_window_value(value: object, *, schema: str, ops_module: str) -> int:
    """F-4b(i) (design D-2(d)): jsonb numeric, integer, >= 0. `bool` is a
    Python `int` subclass -- rejected explicitly, since PostgreSQL's own
    jsonb `true`/`false` must never silently read back as `1`/`0`."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise PlatformDeclarationError(_f4b_window_message(schema, value, ops_module=ops_module))
    return value


def validate_audit_writer_roles_value(value: object, *, schema: str, ops_module: str) -> tuple[str, ...]:
    """F-4b(ii) (design D-2(h) 6): non-empty JSON array of distinct,
    syntactically valid PostgreSQL identifiers. `ops_module` is accepted
    for the same three-`validate_*`-function call shape `read_platform_
    declarations` uses uniformly, even though this particular message
    never names an `ops` subcommand (this row is written only by a
    migration, never by `ops`, design D-2(h) 6). Agent C isomorphism
    convergence (rulings-q4-wp12-rework.md sec.1): inlined against this
    module's own `_PG_IDENTIFIER_PATTERN`/`_PG_IDENTIFIER_MAX_LENGTH`
    rather than calling out to `identifiers.validate_identifier` -- the
    two peers' identifier-syntax primitives differ in call shape
    (`(value, label=...)` raising `ValidationError` here vs r2db-api's
    own regex-and-length constants), and this function's own body is
    isomorphism-pinned, so it references only same-named module
    constants, never a peer-specific helper's own calling convention."""
    is_valid = (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(item, str) for item in value)
        and len(set(value)) == len(value)
        and all(_PG_IDENTIFIER_PATTERN.fullmatch(item) is not None and len(item) <= _PG_IDENTIFIER_MAX_LENGTH for item in value)
    )
    if not is_valid:
        raise PlatformDeclarationError(_f4b_writer_roles_message(schema, value, migration=MIGRATION_NUMBER))
    return tuple(value)


def _validate_base_url(field: str, raw: Any, *, suffix: str, schema: str, ops_module: str) -> str:
    """The three independent SHAPE checks a declared `surfaces.data.
    base_url`/`surfaces.control.base_url` must pass (design D-2(d)): an
    absolute URL, ending in the right suffix, with no trailing slash --
    checked as three separate conditions. Agent C isomorphism convergence
    (rulings-q4-wp12-rework.md sec.1, §12 LQ4-23): the check's own body now
    lives directly in this module (design §3.10: "URL 形式検証の本体は
    この関数に置く") rather than delegating to `surfaces.py` -- that
    module's own `validate_data_base_url`/`validate_control_base_url`
    stay in place for `config.py`/`cell.py`'s unrelated, pre-existing
    env-var-shaped re-validation, untouched by this change."""
    if not isinstance(raw, str) or not raw:
        raise PlatformDeclarationError(_f5_message(field, suffix, raw, schema=schema, ops_module=ops_module))
    parsed = urlsplit(raw)
    if not parsed.scheme or not parsed.netloc:
        raise PlatformDeclarationError(_f5_message(field, suffix, raw, schema=schema, ops_module=ops_module))
    without_trailing_slash = raw[:-1] if raw.endswith("/") else raw
    if not without_trailing_slash.endswith(suffix):
        raise PlatformDeclarationError(_f5_message(field, suffix, raw, schema=schema, ops_module=ops_module))
    # `/control/v1` itself ends with the substring `/v1` -- `surfaces.data.
    # base_url`'s own `suffix="/v1"` check alone would otherwise ACCEPT a
    # value that is actually a control-surface URL. `surfaces.control.
    # base_url`'s own check needs no symmetric guard (a bare `/v1`-ending
    # value never satisfies its own `suffix="/control/v1"` check in the
    # first place).
    if suffix == "/v1" and without_trailing_slash.endswith("/control/v1"):
        raise PlatformDeclarationError(_f5_message(field, suffix, raw, schema=schema, ops_module=ops_module))
    if raw.endswith("/"):
        raise PlatformDeclarationError(_f5_message(field, suffix, raw, schema=schema, ops_module=ops_module))
    return raw


def validate_surfaces_value(value: object, *, schema: str, ops_module: str) -> Surfaces:
    """F-5 (design D-2(d)): validates the raw `surfaces` jsonb value --
    `surfaces.data.base_url` unconditionally required, `surfaces.control.
    base_url` optional."""
    if not isinstance(value, dict) or not isinstance(value.get("data"), dict) or "base_url" not in value["data"]:
        raise PlatformDeclarationError(_f5_message("surfaces.data.base_url", "/v1", value, schema=schema, ops_module=ops_module))
    data_url = _validate_base_url("surfaces.data.base_url", value["data"]["base_url"], suffix="/v1", schema=schema, ops_module=ops_module)

    control_url: Optional[str] = None
    if "control" in value:
        control = value["control"]
        if not isinstance(control, dict) or "base_url" not in control:
            raise PlatformDeclarationError(_f5_message("surfaces.control.base_url", "/control/v1", control, schema=schema, ops_module=ops_module))
        control_url = _validate_base_url("surfaces.control.base_url", control["base_url"], suffix="/control/v1", schema=schema, ops_module=ops_module)

    return Surfaces(data_base_url=data_url, control_base_url=control_url)


def read_platform_declarations(conn: "psycopg.Connection", *, schema: str, ops_module: str, migration: str) -> PlatformDeclarations:
    """D-2, design §3.7 step 4's own required ORDER: (a) table existence
    (F-8) before (b) row existence (`surfaces` absent -> F-3,
    `audit_coalescing_window_ms` absent -> F-4) -- a migration-not-applied
    platform database must never surface a raw psycopg 'relation does not
    exist' error. `audit_writer_roles` is read in the SAME query, but its
    absence is NOT F-4 (design §3.7 step 4's own note: "行が無い場合は
    下記 6 の包含確認で F-13になる") -- an absent row comes back here as
    an empty tuple, deferred to the caller's own `check_writer_role_
    timeouts` self-role-inclusion check. Step 5's value validation
    (F-4b/F-5) runs immediately after, on the SAME read -- this function
    is the single call site both composition roots use. Takes an
    ALREADY-OPEN connection (never a DSN) -- the caller decides the
    connection's own lifetime and login identity."""
    table = sql.Identifier(schema, TABLE_NAME)
    try:
        with conn.cursor() as cur:
            cur.execute(sql.SQL("SELECT key, value FROM {table}").format(table=table))
            rows = dict(cur.fetchall())
    except psycopg.errors.UndefinedTable as exc:
        conn.rollback()
        raise PlatformDeclarationError(_f8_message(schema, migration=migration)) from exc

    if "surfaces" not in rows:
        raise PlatformDeclarationError(_f3_message(schema, ops_module=ops_module))
    if "audit_coalescing_window_ms" not in rows:
        raise PlatformDeclarationError(_f4_message(schema, ops_module=ops_module, migration=migration))

    surfaces = validate_surfaces_value(rows["surfaces"], schema=schema, ops_module=ops_module)
    window_ms = validate_coalescing_window_value(rows["audit_coalescing_window_ms"], schema=schema, ops_module=ops_module)

    writer_roles: tuple[str, ...] = ()
    if "audit_writer_roles" in rows:
        writer_roles = validate_audit_writer_roles_value(rows["audit_writer_roles"], schema=schema, ops_module=ops_module)

    return PlatformDeclarations(surfaces=surfaces, audit_coalescing_window_ms=window_ms, audit_writer_roles=writer_roles)


# ---------------------------------------------------------------------------
# F-6 / F-3c: `surfaces.control`'s presence must agree with the calling
# process' own role (data-plane: cross-checked against `*_CONTROL_PLANE_
# STATUS`, F-6; control-plane: unconditionally required, F-3c) -- design
# D-2(f), monitor ruling 2026-09-05.
# ---------------------------------------------------------------------------


def _f6_forward_message(*, ops_module: str) -> str:
    return (
        f"surfaces.control is declared but {CONTROL_PLANE_STATUS_ENV} is 'unavailable' (contract 1.6.0: a "
        "deployment declaring control_plane unavailable omits surfaces.control). The surfaces row is shared "
        "by BOTH processes: re-declaring with '--no-control' removes the control declaration for the "
        "control-plane process too, and that process will then fail to start (F-3). Unless this deployment "
        f"really offers no control surface, change {CONTROL_PLANE_STATUS_ENV} on this process instead, "
        "then restart both processes. If the deployment genuinely has no control surface, re-declare with "
        f"'python -m {ops_module}.ops declare-surfaces --data-base-url <URL> --no-control'."
    )


def _f6_reverse_message(control_plane_status: str, *, ops_module: str) -> str:
    return (
        f"surfaces.control is not declared but {CONTROL_PLANE_STATUS_ENV} is '{control_plane_status}' "
        "(contract 1.6.0: a deployment declaring control_plane other than unavailable must have a control "
        "surface). The surfaces row is shared by BOTH processes: declare a control base url with "
        f"'python -m {ops_module}.ops declare-surfaces --data-base-url <URL> --control-base-url <URL>', or "
        f"unless this deployment really offers a control surface, change {CONTROL_PLANE_STATUS_ENV} to "
        "'unavailable' on this process instead, then restart both processes."
    )


def check_control_surface_consistency(surfaces: Surfaces, control_plane_status: str, *, ops_module: str) -> None:
    """F-6, both directions (design §3.8 F-6 note). **data-plane only** --
    the control-plane process never calls this (it has its own
    unconditional F-3c check below, monitor ruling 2026-09-05: "control
    プロセスの surfaces.control 欠落は F-3 とは別の状況...control_
    composition の F-6 出力は撤去し、F-3c を出す")."""
    has_control = surfaces.control_base_url is not None
    if has_control and control_plane_status == "unavailable":
        raise PlatformDeclarationError(_f6_forward_message(ops_module=ops_module))
    if not has_control and control_plane_status != "unavailable":
        raise PlatformDeclarationError(_f6_reverse_message(control_plane_status, ops_module=ops_module))


def require_control_surface_declared(surfaces: Surfaces, *, schema: str, ops_module: str) -> None:
    """F-3c (monitor ruling 2026-09-05, design §3.8): the control-plane
    process' own unconditional check -- it ALWAYS has a control surface
    of its own to declare, so an absent `surfaces.control` is fail-fast
    regardless of any env var (there is no `*_CONTROL_PLANE_STATUS`-style
    knob on this side to consult, unlike F-6's data-plane check)."""
    if surfaces.control_base_url is None:
        raise PlatformDeclarationError(_f3c_message(schema, ops_module=ops_module))


# ---------------------------------------------------------------------------
# D-1(b): the role-setting dual check that replaces this peer's former
# per-connection `SET SESSION` audit-writer timeouts. (i) catalog
# declaration existence/validity (F-7/F-10/F-11); (ii) THIS role's own
# effective value on a connection actually logged in as it (F-9). D-2(h):
# self-role inclusion in the declared `audit_writer_roles` set (F-13) is
# checked BEFORE the dual check.
# ---------------------------------------------------------------------------


def _f7_message(role_name: str, *, ops_module: str, migration: str) -> str:
    return (
        f"role '{role_name}' has no statement_timeout / idle_in_transaction_session_timeout in "
        f"pg_db_role_setting: migration {migration} is not applied to this platform database, and an "
        f"audit writer must never run unbounded. Apply migration {migration}, or set the values with "
        f"'python -m {ops_module}.ops set-platform-timeouts --statement-ms <N> --idle-ms <N>', then restart "
        f"both processes. Note this setting also bounds every other connection made by this role "
        f"(credential store lookups and control-plane registry operations included)."
    )


def _f9_message(role_name: str, setting: str, declared_ms: int, effective_ms: int, *, ops_module: str) -> str:
    return (
        f"role '{role_name}' declares {setting} = {declared_ms} ms in pg_db_role_setting but this "
        f"connection's effective value is {effective_ms} ms (both shown in milliseconds; PostgreSQL renders "
        f"these settings in whichever unit divides evenly, so never compare the rendered strings): the "
        f"declared visibility_lag_ms would not describe the effective connection. Remove the override -- a "
        f"connection-string 'options=-c …', PGOPTIONS, or an 'ALTER ROLE … IN DATABASE … SET' row -- so the "
        f"role setting is the effective value, or change the role setting with 'python -m {ops_module}.ops "
        f"set-platform-timeouts --statement-ms <N> --idle-ms <N>', then restart both processes. Note this "
        f"setting also bounds every other connection made by this role."
    )


def _f10_message(role_name: str, setting: str, value: int, *, ops_module: str) -> str:
    return (
        f"role '{role_name}' declares {setting} = {value} in pg_db_role_setting, which PostgreSQL reads as \"no "
        f"limit\": an audit writer must never run unbounded, and the declared visibility_lag_ms would describe "
        f"a bound that does not exist. Set a positive value with 'python -m {ops_module}.ops "
        f"set-platform-timeouts --statement-ms <N> --idle-ms <N>' (the command rejects 0 and negative "
        f"values), then restart both processes."
    )


def _f11_message(role_name: str, database_name: str) -> str:
    return (
        f"role '{role_name}' has an 'ALTER ROLE … IN DATABASE …' setting row for database "
        f"'{database_name}', which takes precedence over the database-independent role setting this "
        f"deployment declares. The role setting must be a single database-independent row. Remove it with "
        f"'ALTER ROLE {role_name} IN DATABASE {database_name} RESET statement_timeout, "
        f"idle_in_transaction_session_timeout;' (issued on the provision DSN), then restart both processes."
    )


def _f13_message(current_user: str, declared_roles: Sequence[str], *, schema: str, ops_module: str, migration: str) -> str:
    declared_repr = "[" + ", ".join(f'"{role}"' for role in declared_roles) + "]" if declared_roles else "absent"
    return (
        f"current_user '{current_user}' is not declared as an audit writer role: 'audit_writer_roles' in "
        f"{schema}.platform_declarations is absent, or it does not list this role (declared: "
        f"{declared_repr}). Migration {migration} seeds that row with the very role names it issues 'ALTER "
        f"ROLE … SET statement_timeout / idle_in_transaction_session_timeout' for, in the same transaction, "
        f"so a process connecting as any other role writes audit rows whose timeouts the declared "
        f"visibility_lag_ms does not describe. Apply migration {migration} to this platform database with "
        f"this deployment's writer role names, or connect this process as one of the declared roles; then "
        f"set the timeouts with 'python -m {ops_module}.ops set-platform-timeouts --statement-ms <N> "
        f"--idle-ms <N>' (it issues ALTER ROLE for every role in 'audit_writer_roles', and takes no "
        f"role-name argument) and restart both processes."
    )


def _current_user(conn: "psycopg.Connection") -> str:
    with conn.cursor() as cur:
        cur.execute("SELECT current_user")
        return cur.fetchone()[0]


def _role_setting_rows(conn: "psycopg.Connection", role_name: str) -> list[tuple[int, Optional[str], Optional[list[str]]]]:
    """Every `pg_db_role_setting` row for `role_name` that is either
    database-independent (`setdatabase = 0`, the declaration itself,
    design §1.5 finding 6) or scoped to THIS connection's own database
    (`setdatabase = <this db's oid>`, F-11's own per-database override) --
    the catalog query itself is restricted to `setdatabase IN (0, own db
    oid)` (design D-1(c) amendment 2026-09-05), never every database on
    the cluster. `pg_db_role_setting` is a world-readable shared catalog:
    any connection can run this query regardless of its own login role."""
    statement = sql.SQL(
        "SELECT s.setdatabase, d.datname, s.setconfig FROM pg_db_role_setting s "
        "JOIN pg_roles r ON r.oid = s.setrole LEFT JOIN pg_database d ON d.oid = s.setdatabase "
        "WHERE r.rolname = %s AND s.setdatabase IN (0, (SELECT oid FROM pg_database WHERE datname = current_database()))"
    )
    with conn.cursor() as cur:
        cur.execute(statement, [role_name])
        return cur.fetchall()


def read_declared_role_timeouts(conn: "psycopg.Connection", role: str, *, ops_module: str, migration: str) -> RoleTimeoutCatalog:
    """D-1(b)(i): the catalog half of the dual check, order F-7 -> F-10 ->
    F-11 (design §3.7 data-plane step 6 / control-plane step 6). Unknown
    `setconfig` keys (e.g. `search_path`) are silently ignored. A
    per-database row (`setdatabase != 0`) is F-11 **only when its own
    `setconfig` actually mentions one of the two timeout keys** (design
    amendment 2026-09-05, F-11 の絞り込み) -- a per-database row that
    sets some unrelated GUC must never block startup."""
    rows = _role_setting_rows(conn, role)
    declared_row: Optional[list[str]] = None
    per_database_timeout_names: list[str] = []
    for setdatabase, datname, setconfig in rows:
        if setdatabase == 0:
            declared_row = setconfig
        elif setconfig and any(entry.split("=", 1)[0] in _TIMEOUT_KEYS for entry in setconfig):
            per_database_timeout_names.append(datname or str(setdatabase))

    values: dict[str, int] = {}
    for entry in declared_row or []:
        key, sep, raw_value = entry.partition("=")
        if sep and key in _TIMEOUT_KEYS:
            values[key] = ms_from_pg_timeout_text(raw_value)

    missing = [key for key in _TIMEOUT_KEYS if key not in values]
    if missing:
        raise PlatformDeclarationError(_f7_message(role, ops_module=ops_module, migration=migration))
    for key in _TIMEOUT_KEYS:
        if values[key] <= 0:
            raise PlatformDeclarationError(_f10_message(role, key, values[key], ops_module=ops_module))
    if per_database_timeout_names:
        raise PlatformDeclarationError(_f11_message(role, per_database_timeout_names[0]))
    return RoleTimeoutCatalog(role=role, statement_ms=values[_STATEMENT_TIMEOUT_KEY], idle_ms=values[_IDLE_TIMEOUT_KEY])


def read_effective_timeouts_ms(conn: "psycopg.Connection") -> tuple[int, int]:
    """D-1(b)(ii): THIS connection's own effective `(statement_timeout,
    idle_in_transaction_session_timeout)`, read from `pg_settings.setting`
    (unit = ms, a raw integer string -- never `SHOW`/`current_setting`,
    which round to whichever unit divides evenly, design D-1(b))."""
    with conn.cursor() as cur:
        cur.execute("SELECT name, setting FROM pg_settings WHERE name = ANY(%s)", [list(_TIMEOUT_KEYS)])
        effective = {name: int(setting) for name, setting in cur.fetchall()}
    return effective[_STATEMENT_TIMEOUT_KEY], effective[_IDLE_TIMEOUT_KEY]


def derive_visibility_lag_ms(catalogs: Sequence[RoleTimeoutCatalog]) -> int:
    """D-1(c): pure function -- `max(statement_ms + idle_ms) +
    VISIBILITY_LAG_CLOCK_SKEW_MARGIN_MS` over every catalog the caller
    already read (one per declared `audit_writer_roles` entry, design
    D-2(h) 3). No PostgreSQL connection, no role-name derivation of any
    kind -- the caller decides which roles to read via `read_declared_
    role_timeouts` before calling this."""
    return max(c.statement_ms + c.idle_ms for c in catalogs) + VISIBILITY_LAG_CLOCK_SKEW_MARGIN_MS


def check_writer_role_timeouts(
    conn: "psycopg.Connection", *, declared_roles: Sequence[str], schema: str, ops_module: str, migration: str,
) -> RoleTimeoutCatalog:
    """D-1(b) + D-2(h) 2, full dual check for ONE writer role -- `conn` is
    the connection the caller's OWN audit-writer sink actually uses to
    write (r2db-api: one connection borrowed from that sink's own pool;
    MitateDB-api: one connection opened via the SAME function the sink
    itself uses to open its connections) -- never a throwaway connection
    opened by SOME OTHER mechanism, since role-level settings only apply
    at login time and this check must observe the exact connection
    identity the durable sink will use.

    Order (design §3.7 step 6): (1) self-role inclusion in `declared_
    roles` (F-13, checked BEFORE the dual check below -- a role that is
    not even declared has no `visibility_lag_ms` to describe); (2) catalog
    declaration (F-7/F-10/F-11, `read_declared_role_timeouts`); (3) this
    SAME connection's own effective `pg_settings` value, compared as ms
    integers, never as rendered strings (F-9)."""
    role_name = _current_user(conn)
    if role_name not in declared_roles:
        raise PlatformDeclarationError(_f13_message(role_name, declared_roles, schema=schema, ops_module=ops_module, migration=migration))
    declared = read_declared_role_timeouts(conn, role_name, ops_module=ops_module, migration=migration)
    effective_statement_ms, effective_idle_ms = read_effective_timeouts_ms(conn)
    if effective_statement_ms != declared.statement_ms:
        raise PlatformDeclarationError(
            _f9_message(role_name, _STATEMENT_TIMEOUT_KEY, declared.statement_ms, effective_statement_ms, ops_module=ops_module))
    if effective_idle_ms != declared.idle_ms:
        raise PlatformDeclarationError(
            _f9_message(role_name, _IDLE_TIMEOUT_KEY, declared.idle_ms, effective_idle_ms, ops_module=ops_module))
    return declared


__all__ = [
    "CONTROL_PLANE_STATUS_ENV",
    "DEFAULT_SCHEMA",
    "MIGRATION_FILENAME",
    "MIGRATION_NUMBER",
    "PEER_DIR",
    "PEER_MODULE",
    "PROVISION_DSN_ENV",
    "REMOVED_SURFACE_ENV",
    "REMOVED_TIMEOUT_ENV",
    "TABLE_NAME",
    "VISIBILITY_LAG_CLOCK_SKEW_MARGIN_MS",
    "PlatformDeclarationError",
    "PlatformDeclarations",
    "RoleTimeoutCatalog",
    "Surfaces",
    "check_control_surface_consistency",
    "check_writer_role_timeouts",
    "derive_visibility_lag_ms",
    "read_declared_role_timeouts",
    "read_effective_timeouts_ms",
    "read_platform_declarations",
    "reject_removed_surface_env",
    "reject_removed_timeout_env",
    "require_control_surface_declared",
    "validate_audit_writer_roles_value",
    "validate_coalescing_window_value",
    "validate_surfaces_value",
]
