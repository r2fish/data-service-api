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

#: Phase 10 WP-6b (design D-5 (ii)): the platform single-shot migration
#: that widens `platform_declarations.key`'s own CHECK constraint to
#: accept `'process_ceilings'` -- referenced by `_f15_missing_message`
#: only (the row-missing F-15 message names the migration that made this
#: KEY legal, not `MIGRATION_NUMBER` = 0007, which never mentions this
#: key at all).
PROCESS_CEILINGS_MIGRATION_NUMBER = "0011"
PROCESS_CEILINGS_MIGRATION_FILENAME = "0011_process_ceilings.sql"

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
    error code, never returned over HTTP (design §3.8's own SI-10 note).

    Phase 8 WP-4 (design PHASE8_EFFECTIVE_BOUNDS_AND_HYGIENE_V1.md D-5
    decision 2): `code` is the structured F-number attribute `ops
    verify-declarations` maps to its own fixed exit code table -- added so
    that command never has to prefix-match this exception's own message
    text. The message text itself is UNCHANGED by this addition (every
    `_fN_message`/`_fNx_message` builder above is untouched; only the
    `raise PlatformDeclarationError(...)` call sites below now also pass
    `code=`)."""

    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Surfaces:
    """F-5's own validated return shape (design D-2(d))."""
    data_base_url: str
    control_base_url: Optional[str]


@dataclass(frozen=True)
class ProcessCeilings:
    """F-15's own validated return shape (design D-5 (ii)): how many
    processes may serve each plane's declared base URL at the same time.
    The SAME shape `Surfaces` uses (`{"data": ..., "control": ...}`,
    design U-5: "新しい形を発明しない") -- unlike `Surfaces.control_base_url`,
    `control` here is never optional: this deployment's process topology
    for the control plane is a fact of the deployment, not conditioned on
    whether a control SURFACE is declared."""
    data: int
    control: int


@dataclass(frozen=True)
class PlatformDeclarations:
    """`read_platform_declarations`'s own return shape -- the four rows
    of `<registry>.platform_declarations`, each already validated."""
    surfaces: Surfaces
    audit_coalescing_window_ms: int
    audit_writer_roles: tuple[str, ...]
    process_ceilings: ProcessCeilings


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
            raise PlatformDeclarationError(_f1_message(name), code="F-1")


def reject_removed_surface_env(env: Mapping[str, str], *, names: tuple[str, ...], schema: str) -> None:
    """F-2: same step, same reasoning, the surfaces pair (`REMOVED_
    SURFACE_ENV`). `schema` is the caller's own resolved registry schema
    (design amendment 2026-09-05, N-7): the message must name the real
    schema, not this module's own `DEFAULT_SCHEMA`, since a deployment
    may override it."""
    for name in names:
        if name in env:
            raise PlatformDeclarationError(_f2_message(name, schema=schema), code="F-2")


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
        raise PlatformDeclarationError(_f4b_window_message(schema, value, ops_module=ops_module), code="F-4b")
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
        raise PlatformDeclarationError(_f4b_writer_roles_message(schema, value, migration=MIGRATION_NUMBER), code="F-4b")
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
        raise PlatformDeclarationError(_f5_message(field, suffix, raw, schema=schema, ops_module=ops_module), code="F-5")
    parsed = urlsplit(raw)
    if not parsed.scheme or not parsed.netloc:
        raise PlatformDeclarationError(_f5_message(field, suffix, raw, schema=schema, ops_module=ops_module), code="F-5")
    without_trailing_slash = raw[:-1] if raw.endswith("/") else raw
    if not without_trailing_slash.endswith(suffix):
        raise PlatformDeclarationError(_f5_message(field, suffix, raw, schema=schema, ops_module=ops_module), code="F-5")
    # `/control/v1` itself ends with the substring `/v1` -- `surfaces.data.
    # base_url`'s own `suffix="/v1"` check alone would otherwise ACCEPT a
    # value that is actually a control-surface URL. `surfaces.control.
    # base_url`'s own check needs no symmetric guard (a bare `/v1`-ending
    # value never satisfies its own `suffix="/control/v1"` check in the
    # first place).
    if suffix == "/v1" and without_trailing_slash.endswith("/control/v1"):
        raise PlatformDeclarationError(_f5_message(field, suffix, raw, schema=schema, ops_module=ops_module), code="F-5")
    if raw.endswith("/"):
        raise PlatformDeclarationError(_f5_message(field, suffix, raw, schema=schema, ops_module=ops_module), code="F-5")
    return raw


def validate_surfaces_value(value: object, *, schema: str, ops_module: str) -> Surfaces:
    """F-5 (design D-2(d)): validates the raw `surfaces` jsonb value --
    `surfaces.data.base_url` unconditionally required, `surfaces.control.
    base_url` optional."""
    if not isinstance(value, dict) or not isinstance(value.get("data"), dict) or "base_url" not in value["data"]:
        raise PlatformDeclarationError(_f5_message("surfaces.data.base_url", "/v1", value, schema=schema, ops_module=ops_module), code="F-5")
    data_url = _validate_base_url("surfaces.data.base_url", value["data"]["base_url"], suffix="/v1", schema=schema, ops_module=ops_module)

    control_url: Optional[str] = None
    if "control" in value:
        control = value["control"]
        if not isinstance(control, dict) or "base_url" not in control:
            raise PlatformDeclarationError(_f5_message("surfaces.control.base_url", "/control/v1", control, schema=schema, ops_module=ops_module), code="F-5")
        control_url = _validate_base_url("surfaces.control.base_url", control["base_url"], suffix="/control/v1", schema=schema, ops_module=ops_module)

    return Surfaces(data_base_url=data_url, control_base_url=control_url)


def _f15_missing_message(schema: str, *, ops_module: str) -> str:
    return (
        f"no 'process_ceilings' row in {schema}.platform_declarations: contract 1.8.0 defines the scope of "
        f"every limit_enforcement value in terms of it unconditionally. Declare it with 'python -m "
        f"{ops_module}.ops declare-process-ceilings --data <N> --control <N>' (requires migration "
        f"{PROCESS_CEILINGS_MIGRATION_NUMBER} applied to this platform database), then restart both processes."
    )


def _f15_shape_message(schema: str, value: Any, *, ops_module: str) -> str:
    return (
        f"'process_ceilings' in {schema}.platform_declarations must be a JSON object with exactly the two "
        f"keys 'data' and 'control', each a positive integer (the maximum number of processes that may "
        f"serve that plane's declared surfaces base URL at the same time), got '{value}'. This table can be "
        f"edited by hand, so the value is validated on every read as well as on write. Re-declare it with "
        f"'python -m {ops_module}.ops declare-process-ceilings --data <N> --control <N>', then restart both "
        f"processes."
    )


def _f15_value_message(schema: str, value: Any, *, ops_module: str) -> str:
    return (
        f"'process_ceilings' in {schema}.platform_declarations has the right keys but 'data' and 'control' "
        f"must both be a positive integer (the maximum number of processes that may serve that plane's "
        f"declared surfaces base URL at the same time), got '{value}'. This table can be edited by hand, so "
        f"the value is validated on every read as well as on write. Re-declare it with 'python -m "
        f"{ops_module}.ops declare-process-ceilings --data <N> --control <N>', then restart both processes."
    )


def validate_process_ceilings_value(value: object, *, schema: str, ops_module: str) -> ProcessCeilings:
    """F-15's shape half (design D-5(ii)): `{"data": <int >= 1>, "control":
    <int >= 1>}` -- exactly those two keys (no extra, none missing), each a
    positive integer (`bool` is a Python `int` subclass, excluded
    explicitly, same discipline as `validate_coalescing_window_value`). The
    SAME function runs on the ops write path (`declare-process-ceilings`)
    and every read path (Q4 D-2(d): "書き込み時と読み出し時の両方で行い、
    両方が同じ Python の検証関数を通る").

    Two SEPARATE checks, deliberately not folded into one `all(...)` (peer-
    parity note, supervisor ruling `scratchpad/phase10/wp6-rulings.md` #4:
    r2db's 2-stage form -- shape, then value -- is the form both peers
    converge to): stage 1 rejects the wrong CONTAINER shape (not a dict, or
    the wrong key set) with `_f15_shape_message`; stage 2, reached only
    once stage 1 has already confirmed both keys are present, rejects a
    present-but-out-of-range VALUE (wrong type, `bool`, non-positive) with
    the separate `_f15_value_message` -- a distinct message per failure
    kind, even though both stages raise the SAME `code="F-15"` (design
    D-5(ii): existence and shape are one combined check, not two exit
    codes; see this function's own callers in `read_platform_declarations`
    below)."""
    if not isinstance(value, dict) or set(value.keys()) != {"data", "control"}:
        raise PlatformDeclarationError(_f15_shape_message(schema, value, ops_module=ops_module), code="F-15")
    data_value = value["data"]
    control_value = value["control"]
    is_valid = (
        not isinstance(data_value, bool) and isinstance(data_value, int) and data_value >= 1
        and not isinstance(control_value, bool) and isinstance(control_value, int) and control_value >= 1
    )
    if not is_valid:
        raise PlatformDeclarationError(_f15_value_message(schema, value, ops_module=ops_module), code="F-15")
    return ProcessCeilings(data=data_value, control=control_value)


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
        raise PlatformDeclarationError(_f8_message(schema, migration=migration), code="F-8") from exc

    if "surfaces" not in rows:
        raise PlatformDeclarationError(_f3_message(schema, ops_module=ops_module), code="F-3")
    if "audit_coalescing_window_ms" not in rows:
        raise PlatformDeclarationError(_f4_message(schema, ops_module=ops_module, migration=migration), code="F-4")
    if "process_ceilings" not in rows:
        raise PlatformDeclarationError(_f15_missing_message(schema, ops_module=ops_module), code="F-15")
    # Existence and shape are both raised as F-15 (design D-5(ii): one
    # combined check, unlike surfaces' F-3/F-5 split) -- validated here, in
    # one contiguous step right after the existence check above and BEFORE
    # surfaces'/the window's own value validation below, so `ops verify-
    # declarations`' own fixed read order (`_VERIFY_DECLARATIONS_READ_
    # ORDER`) never has to represent this row's two sub-checks at two
    # different list positions.
    process_ceilings = validate_process_ceilings_value(rows["process_ceilings"], schema=schema, ops_module=ops_module)

    surfaces = validate_surfaces_value(rows["surfaces"], schema=schema, ops_module=ops_module)
    window_ms = validate_coalescing_window_value(rows["audit_coalescing_window_ms"], schema=schema, ops_module=ops_module)

    writer_roles: tuple[str, ...] = ()
    if "audit_writer_roles" in rows:
        writer_roles = validate_audit_writer_roles_value(rows["audit_writer_roles"], schema=schema, ops_module=ops_module)

    return PlatformDeclarations(
        surfaces=surfaces, audit_coalescing_window_ms=window_ms, audit_writer_roles=writer_roles,
        process_ceilings=process_ceilings,
    )


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
        raise PlatformDeclarationError(_f6_forward_message(ops_module=ops_module), code="F-6")
    if not has_control and control_plane_status != "unavailable":
        raise PlatformDeclarationError(_f6_reverse_message(control_plane_status, ops_module=ops_module), code="F-6")


def require_control_surface_declared(surfaces: Surfaces, *, schema: str, ops_module: str) -> None:
    """F-3c (monitor ruling 2026-09-05, design §3.8): the control-plane
    process' own unconditional check -- it ALWAYS has a control surface
    of its own to declare, so an absent `surfaces.control` is fail-fast
    regardless of any env var (there is no `*_CONTROL_PLANE_STATUS`-style
    knob on this side to consult, unlike F-6's data-plane check)."""
    if surfaces.control_base_url is None:
        raise PlatformDeclarationError(_f3c_message(schema, ops_module=ops_module), code="F-3c")


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
        raise PlatformDeclarationError(_f7_message(role, ops_module=ops_module, migration=migration), code="F-7")
    for key in _TIMEOUT_KEYS:
        if values[key] <= 0:
            raise PlatformDeclarationError(_f10_message(role, key, values[key], ops_module=ops_module), code="F-10")
    if per_database_timeout_names:
        raise PlatformDeclarationError(_f11_message(role, per_database_timeout_names[0]), code="F-11")
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
        raise PlatformDeclarationError(_f13_message(role_name, declared_roles, schema=schema, ops_module=ops_module, migration=migration), code="F-13")
    declared = read_declared_role_timeouts(conn, role_name, ops_module=ops_module, migration=migration)
    effective_statement_ms, effective_idle_ms = read_effective_timeouts_ms(conn)
    if effective_statement_ms != declared.statement_ms:
        raise PlatformDeclarationError(_f9_message(role_name, _STATEMENT_TIMEOUT_KEY, declared.statement_ms, effective_statement_ms, ops_module=ops_module), code="F-9")
    if effective_idle_ms != declared.idle_ms:
        raise PlatformDeclarationError(_f9_message(role_name, _IDLE_TIMEOUT_KEY, declared.idle_ms, effective_idle_ms, ops_module=ops_module), code="F-9")
    return declared


# Contract 1.7.0 (design docs/design/
# PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md D-1/D-6/D-5, work
# order §2 WP-3e F-3, `{scratchpad}/rulings-r3-r7-flip.md` F-3; WP-3e
# rework T3, `{scratchpad}/rulings-r3-r7-flip.md` L-2/M-7): pinned
# isomorphic to r2db-api's own `check_contract_170_declarations` (same
# name, same signature SHAPE, same 3-part check, `_ISOMORPHIC_TARGETS` --
# task brief: "F-14 (check_contract_170_resource_limits / ops_module_hint)
# と exit code の表"). Never a second, redundant construction of a fresh
# `FoundationConfig()`/capabilities document for itself (the SAME flaw
# r2db-api's own pre-rework version had, audit finding D-2/L-2 -- a broken
# default would raise at construction, before this function is ever
# reached, and a healthy default always passes, making the check dead):
# `capabilities_document` is the CALLER's own already-live value, for
# BOTH halves of the check below -- no separate `config`/`ResourceLimits`
# argument at all (T3 rework: the PRE-rework version of this function took
# a `config: FoundationConfig` argument and read `getattr(config, attr_
# name)` directly -- the exact "on-the-spot construction" flaw this rework
# removes, since the caller built that `config` fresh, at check time, via
# `FoundationConfig.from_env(...)`; a broken value there raises at
# `FoundationConfig.__post_init__`, before this function is ever reached).
#   (a) the served capabilities document actually declares `constraint_
#       declarations`/`dry_run`/`idempotency`/`request_budget` `enabled`.
#   (b) the SAME served document's own `limits` block (never a separately
#       constructed `FoundationConfig`/`ResourceLimits`) carries a
#       positive `enum_members`/`idempotency_entries`/`idempotency_
#       retention_ms` -- this peer's own `__build_capabilities_document`
#       (`cell.py`) (body now in `capabilities_document.py`) already normalizes every limit key to the contract's
#       own vocabulary name there (`"enum_members": config.max_enum_
#       members`, this peer's own `max_*` naming convention resolved at
#       DOCUMENT-BUILD time, not read here), so this function needs no
#       peer-specific attribute-name mapping of its own -- `_CONTRACT_170_
#       LIMIT_CLASSES` below is the bare vocabulary tuple, byte-identical
#       to r2db-api's own same-named constant.
#   (c) EVERY registered application's own per-application upgrade ledger
#       (migrations `0009`/`0010`, `platform_upgrades.PLATFORM_UPGRADE_
#       NUMBERS`) already carries every number this shipped version
#       requires -- the one part of F-14 a real deployment can actually
#       fail (an application whose database has not yet run `ops
#       upgrade-applications` makes the "enabled" declaration false for
#       that application's own traffic).
def check_contract_170_declarations(
    capabilities_document: Mapping[str, Any],
    applied_upgrade_numbers_by_application: Mapping[str, Optional[frozenset[int]]],
    required_upgrade_numbers: frozenset[int],
) -> None:
    """F-14. `capabilities_document` is the value the caller's own live
    `ApplicationRuntime.capabilities()` call returned (or an equivalent
    already-served document) -- this function never constructs one
    itself, for EITHER half of the check. `applied_upgrade_numbers_by_
    application` maps every registered application's slug to `platform_
    upgrades.read_applied_upgrade_numbers`'s own return value for that
    application's database (`None` when that application has no ledger
    table at all -- read as "every number is pending", the same
    convention `platform_upgrades.pending_upgrade_numbers` already
    uses).

    O-7 prep (版フリップ監査, ruling `{scratchpad}/rulings-r3-r7-flip.md`
    追補4): the signature above is bare (not string-quoted) annotations,
    matching r2db-api's own same-named function's real, current form --
    both modules carry `from __future__ import annotations`, so quoting
    was never semantically necessary; a prior draft quoted these three
    for reasons unrelated to runtime behavior, which only produced a
    normalize-diff against the sibling (r2db 形を基準にし, O-7's own
    instruction). The docstring text differs (peer-specific -- `_normalize`
    strips docstrings before comparing, so this paragraph itself is not
    part of what must match)."""
    capabilities = capabilities_document.get("capabilities", capabilities_document)
    for name in _CONTRACT_170_ENABLED_CAPABILITIES:
        entry = capabilities.get(name) if isinstance(capabilities, Mapping) else None
        status = entry.get("status") if isinstance(entry, Mapping) else None
        if status != "enabled":
            raise PlatformDeclarationError(
                f"{ops_module_hint()}.capabilities().{name}.status must be 'enabled'; got {status!r}.",
                code="F-14",
            )
    limits = capabilities_document.get("limits")
    for name in _CONTRACT_170_LIMIT_CLASSES:
        value = limits.get(name) if isinstance(limits, Mapping) else None
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise PlatformDeclarationError(
                f"{ops_module_hint()}.capabilities().limits.{name} must be a positive integer; got {value!r}.",
                code="F-14",
            )
    missing = {
        application_id: tuple(sorted(required_upgrade_numbers - (applied or frozenset())))
        for application_id, applied in applied_upgrade_numbers_by_application.items()
        if required_upgrade_numbers - (applied or frozenset())
    }
    if missing:
        detail = "; ".join(f"{app}: pending={list(nums)}" for app, nums in sorted(missing.items()))
        raise PlatformDeclarationError(
            f"{ops_module_hint()}: the following application(s) have not applied every contract 1.7.0 "
            f"per-application upgrade {sorted(required_upgrade_numbers)} -- {detail}. Run "
            f"'python -m {ops_module_hint()}.ops upgrade-applications' before declaring this capability enabled.",
            code="F-14",
        )


#: The `capabilities()` document keys `check_contract_170_declarations`
#: requires `status: "enabled"` for (contract 1.7.0, D-1/D-6). Byte-
#: identical to r2db-api's own same-named constant -- no peer-specific
#: value here.
_CONTRACT_170_ENABLED_CAPABILITIES: tuple = ("constraint_declarations", "dry_run", "idempotency", "request_budget")

#: The `capabilities()` document's own `limits` block keys `check_
#: contract_170_declarations` requires a positive integer for (contract
#: 1.7.0, D-2 (7)/D-5). Byte-identical to r2db-api's own same-named
#: `_CONTRACT_170_LIMIT_CLASSES` -- no peer-specific value here either:
#: this peer's `FoundationConfig` attribute names (`max_enum_members`
#: etc., `config.py`) differ from these contract-vocabulary names, but
#: that rename already happens once, at DOCUMENT-BUILD time, inside
#: `cell.py`'s own `__build_capabilities_document` (body now in `capabilities_document.py`) (`"enum_members":
#: config.max_enum_members`) -- never here. WP-3e rework T3 (ruling
#: `{scratchpad}/rulings-r3-r7-flip.md` L-2/M-7) removed this module's
#: former `_CONTRACT_170_LIMIT_ATTRIBUTES` (a `contract name -> Foundation
#: Config attribute name` mapping `check_contract_170_declarations` used
#: to read a freshly-built `FoundationConfig` through, `getattr(config,
#: attr_name)`) for exactly that reason: once the check reads the SERVED
#: document instead, a peer-specific attribute-name mapping constant has
#: no remaining job to do inside this pinned function. A future limit
#: class whose contract name and this peer's own `FoundationConfig` field
#: name genuinely diverge (unlike the three above) would need a mapping
#: constant again -- if so, keep it OUTSIDE this function's own body (a
#: module-level constant `cell.py`'s document-builder (body now in `capabilities_document.py`) reads from), never
#: inlined into `check_contract_170_declarations` itself, so this
#: function's own body stays textually isomorphic to r2db-api's.
_CONTRACT_170_LIMIT_CLASSES: tuple = ("enum_members", "idempotency_entries", "idempotency_retention_ms")


# ---------------------------------------------------------------------------
# F-16 (Phase 10 WP-4f, supervisor ruling 2026-09-09; peer-symmetric with
# r2db-api's own same-numbered check -- see that peer's own module for the
# full WP-4e finding this responds to): every PostgreSQL role this
# deployment's own processes pool connections against must have a
# `CONNECTION LIMIT` (`pg_roles.rolconnlimit`) of `-1` (unlimited) or at
# least that role's own worst-case simultaneous connection count ("pool
# 合計") -- otherwise a burst of real concurrent requests hits PostgreSQL's
# own hard `FATAL: too many connections for role` refusal instead of the
# declared 429/503 the contract promises.
#
# Role IDENTITY is read from REAL GRANTS (`information_schema.role_table_
# grants` on the fixed, migration-defined `application_audit`/
# `control_audit` table names), never from a schema/role-name string-
# rewrite convention -- this module's own header already avoids that
# technique for writer-role identification (D-2(h): `audit_writer_roles`
# is read from the declaration row, never derived); the SAME reasoning
# applies here. Runtime/developer role names ARE read directly off
# `<schema>.applications` -- also real stored data, not a derived name.
#
# Deliberately excludes `mitatedbsvc_provision` (short-lived, one-shot
# CLI/provisioning connections only -- no persistent pool, and no stored
# declaration this check could read to derive a floor for it, the same
# "out of scope" category as F-1/F-2/F-12). This is an EXPLICIT exclusion
# (`_table_owner`, below), not merely "no grants match its identity" --
# `mitatedbsvc_provision` is the role every migration in this set runs
# `CREATE TABLE application_audit`/`CREATE TABLE control_audit` AS
# (0005/0002's own "WHO RUNS THIS" headers), so as the OWNER of both
# tables it implicitly holds INSERT and SELECT on both without ever
# appearing as a `grantee` row -- meaning it would otherwise match all
# three platform-plane role classes below at once (measured 2026-09-10,
# WP-4 integration review M-1, peer-symmetric with r2db-api's own
# `r2dbsvc_control`).
# ---------------------------------------------------------------------------

#: `mitatedb_api.main`'s own platform pool (`PostgresCredentialStore`'s
#: `BoundedConnectionPool`, pool-sized to the declared `max_concurrency`
#: ceiling, Phase 10 WP-4e) PLUS `PostgresApplicationAuditSink`'s own
#: per-write transient connections against the SAME role (worst case, one
#: per in-flight request, also bounded by `max_concurrency`) -- both
#: against `mitatedbsvc_api`. Identified by `INSERT` on `application_audit`.
_API_ROLE_STORE_COUNT = 2

#: `mitatedb_api.control_composition`'s own 4 platform-plane stores
#: (`applications`/`credentials_registry`/`control_credentials`/`audit`),
#: peer-symmetric worst case with r2db-api's own measured 16 (4 stores x
#: 4) -- this peer's own stores open one connection per call rather than a
#: persistent multi-connection pool, so the floor here is the SAME
#: worst-case bound applied conservatively, not a literal `pool_size`
#: read off this peer's own code. Identified by `INSERT` on `control_
#: audit`.
_CONTROLPLANE_ROLE_POOL_FLOOR = 16

#: `PostgresAuditQueryStore`'s own reader -- one connection per call
#: (this module's own header), peer-symmetric floor with r2db-api's own
#: fixed `pool_size` 4. Identified by `SELECT` on BOTH `application_audit`
#: AND `control_audit` (migration 0005's own grant shape -- no other role
#: holds `SELECT` on either table).
_AUDITREADER_ROLE_POOL_FLOOR = 4


def _roles_with_table_privilege(conn: "psycopg.Connection", schema: str, table: str, privilege: str) -> list[str]:
    """Every role (`grantee`) actually granted `privilege` on `<schema>.
    <table>` -- `information_schema.role_table_grants` is a world-readable
    view: any connection can run this regardless of its own login role.
    Ordered by `grantee` so callers get deterministic iteration order."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT grantee FROM information_schema.role_table_grants "
            "WHERE table_schema = %s AND table_name = %s AND privilege_type = %s ORDER BY grantee",
            [schema, table, privilege],
        )
        return [row[0] for row in cur.fetchall()]


def _table_owner(conn: "psycopg.Connection", schema: str, table: str) -> "str | None":
    """The role that owns `<schema>.<table>` (`pg_tables.tableowner`) --
    that role implicitly holds every privilege on the table (INSERT,
    SELECT, ...) without ever appearing as a `grantee` row for a real
    GRANT, which is exactly the shape `_roles_with_table_privilege` above
    reads. Used below to keep that owner (the migration-running operator
    role, e.g. `mitatedbsvc_provision`) from being misidentified as
    matching every platform-plane role class at once (M-1, WP-4
    integration review 2026-09-10, peer-symmetric with r2db-api's own
    `_table_owner`). Returns `None` if the table does not exist (a caller
    scoped to `role_classes={"api"}` or similar, e.g. `mitatedb_api.main`'s
    own startup F-16 call, may run before `0005_application_audit.sql` is
    guaranteed applied against the connection it happens to be given) --
    exactly like `_roles_with_table_privilege` above, which already
    tolerates a missing table by simply returning no rows. `None` never
    equals a real role name, so the exclusion checks below simply never
    match in that case, the same as if this function were never called at
    all."""
    with conn.cursor() as cur:
        cur.execute("SELECT tableowner FROM pg_tables WHERE schemaname = %s AND tablename = %s", [schema, table])
        row = cur.fetchone()
        return row[0] if row is not None else None


def _f16_message(role: str, current_limit: int, required_floor: int, *, ops_module: str) -> str:
    return (
        f"role '{role}' has CONNECTION LIMIT {current_limit}, below its own real pool-composition floor "
        f"{required_floor} -- a burst of real concurrent requests can hit PostgreSQL's own hard 'too many "
        f"connections for role' refusal instead of the declared 429/503 the contract promises. Raise it with "
        f"'ALTER ROLE {role} CONNECTION LIMIT {required_floor};' on the provision DSN for a throwaway/test "
        f"platform, or a new migration for an already-shipped deployment (never edit a shipped migration file) "
        f"-- see {ops_module}'s own provisioning runbook."
    )


#: The three platform-plane role classes `check_role_connection_limits`
#: knows how to identify -- a caller narrowing `role_classes` below passes
#: any subset of this set. Peer-symmetric with r2db-api's own `_ROLE_
#: CLASSES`.
_ROLE_CLASSES = frozenset({"api", "controlplane", "auditreader"})


def check_role_connection_limits(
    conn: "psycopg.Connection", *, schema: str, ops_module: str, concurrency: int,
    role_classes: "frozenset[str] | None" = None,
    application_ids: "Sequence[str] | None" = None,
) -> None:
    """F-16: raises `PlatformDeclarationError(code="F-16")` for the FIRST
    role (in the deterministic order built below) whose `pg_roles.
    rolconnlimit` is neither `-1` nor at least its own computed floor.
    `concurrency` is the caller's own declared per-role pool ceiling
    (`config.FoundationConfig.max_concurrency`) -- this function takes it
    as a plain argument rather than reading `MITATEDB_MAX_CONCURRENCY`
    itself, so a deployment that has genuinely raised its declared
    concurrency is checked against ITS OWN real floor, not a silently-stale
    code-level default.

    Checks exactly the role classes `0012_role_connection_limits.sql`
    (this peer) raises: the platform-plane `<...>_api`/`<...>_
    controlplane`/`<...>_auditreader` roles (module-level floor constants
    above) and every PROVISIONED application's own runtime/developer roles
    (floor = `concurrency`, Phase 10 WP-4f peer-symmetric with r2db-api's
    own WP-8a). A role with no grants matching any of the three
    platform-plane shapes above (identity unknown to this check) is
    silently skipped, never flagged.

    Phase 10 WP-4g (supervisor ruling 2026-09-09, peer-symmetric with
    r2db-api's own same-numbered addition): `role_classes`/
    `application_ids` let a caller narrow this check to exactly the
    role(s) ITS OWN process pools connections against, instead of every
    role this whole platform has -- `ops verify-declarations`'s own
    aggregate call (the pre-existing, unchanged default: both `None`)
    still checks everything platform-wide, but `mitatedb_api.main`/
    `mitatedb_api.control_composition`'s own startup fail-fast calls
    (added this WP) pass these so an UNRELATED application's or the
    SIBLING plane's own misconfigured role never blocks a process that
    never pools a connection against it at all. `role_classes`, when
    given, is any subset of `{"api", "controlplane", "auditreader"}`
    (`None` -- the default -- means all three, unchanged pre-existing
    behavior). `application_ids`, when given (not `None`), restricts the
    runtime/developer role check to exactly the named ids -- an EMPTY
    sequence means "check no application role at all"
    (`control_composition`'s own case: that process serves no
    application); `None` (the default) means every registered
    application, unchanged pre-existing behavior."""
    if role_classes is None:
        role_classes = _ROLE_CLASSES
    floors: dict = {}
    # M-1 (WP-4 integration review 2026-09-10): a role can legitimately
    # match MORE than one platform-plane class below -- `max(...)` keeps
    # the STRICTEST floor that role is actually subject to instead of
    # whichever class happened to assign last. `_table_owner` exclusion
    # keeps the table-owning operator role (`mitatedbsvc_provision`, never
    # a real pooled role -- see the module header above) from being
    # misidentified as matching all three via its implicit owner ACL.
    application_audit_owner = _table_owner(conn, schema, "application_audit")
    control_audit_owner = _table_owner(conn, schema, "control_audit")
    if "api" in role_classes:
        for role in _roles_with_table_privilege(conn, schema, "application_audit", "INSERT"):
            if role == application_audit_owner:
                continue
            floors[role] = max(floors.get(role, 0), _API_ROLE_STORE_COUNT * concurrency)
    if "controlplane" in role_classes:
        for role in _roles_with_table_privilege(conn, schema, "control_audit", "INSERT"):
            if role == control_audit_owner:
                continue
            floors[role] = max(floors.get(role, 0), _CONTROLPLANE_ROLE_POOL_FLOOR)
    if "auditreader" in role_classes:
        reader_of_application_audit = set(_roles_with_table_privilege(conn, schema, "application_audit", "SELECT"))
        reader_of_control_audit = set(_roles_with_table_privilege(conn, schema, "control_audit", "SELECT"))
        for role in sorted(reader_of_application_audit & reader_of_control_audit):
            if role == application_audit_owner or role == control_audit_owner:
                continue
            floors[role] = max(floors.get(role, 0), _AUDITREADER_ROLE_POOL_FLOOR)

    # Two-state registry (0002's own header): a registered-but-never-
    # provisioned row has `runtime_role`/`developer_role` still NULL --
    # excluded here the same way `0012_role_connection_limits.sql`'s own
    # migration-time loop excludes it.
    if application_ids is None or len(application_ids) > 0:
        applications_table = sql.Identifier(schema, "applications")
        base_statement = "SELECT runtime_role, developer_role FROM {table} WHERE runtime_role IS NOT NULL AND developer_role IS NOT NULL"
        with conn.cursor() as cur:
            if application_ids is None:
                cur.execute(sql.SQL(base_statement + " ORDER BY application_id").format(table=applications_table))
            else:
                cur.execute(
                    sql.SQL(base_statement + " AND application_id = ANY(%s) ORDER BY application_id").format(table=applications_table),
                    [list(application_ids)],
                )
            for runtime_role, developer_role in cur.fetchall():
                floors[runtime_role] = concurrency
                floors[developer_role] = concurrency

    if not floors:
        return
    role_names = sorted(floors)
    with conn.cursor() as cur:
        cur.execute("SELECT rolname, rolconnlimit FROM pg_roles WHERE rolname = ANY(%s)", [role_names])
        current_limits = dict(cur.fetchall())
    for role in role_names:
        current = current_limits.get(role)
        if current is None or current == -1:
            continue
        required = floors[role]
        if current < required:
            raise PlatformDeclarationError(_f16_message(role, current, required, ops_module=ops_module), code="F-16")


def _f17_message(role: str, *, database_name: "str | None" = None) -> str:
    if database_name is not None:
        return (
            f"role '{role}' has an 'ALTER ROLE … IN DATABASE …' statement_timeout override for database "
            f"'{database_name}', which takes precedence over the role-level declaration this deployment "
            f"relies on. Remove it with 'ALTER ROLE {role} IN DATABASE {database_name} RESET "
            f"statement_timeout;' (issued on the provision DSN), then restart the process that holds this "
            f"role's own connection pool."
        )
    return (
        f"role '{role}' has no positive statement_timeout declared in pg_db_role_setting: an audit reader "
        f"must never run unbounded. Set one with 'ALTER ROLE {role} SET statement_timeout = ...;' (issued "
        f"on the provision DSN), then restart the process that holds this role's own connection pool."
    )


def check_auditreader_statement_timeout(conn: "psycopg.Connection", *, schema: str) -> None:
    """F-17: raises `PlatformDeclarationError(code="F-17")` for the FIRST
    audit-reader role, in sorted name order, that fails either condition
    below. An audit reader is identified by what it can do, not by its
    name: a role holding `SELECT` on BOTH `application_audit` and
    `control_audit` in `schema`, other than the role that owns either
    table. Finding no such role is not a failure -- a deployment without
    an audit reader passes.

    Two conditions fail a reader role. Its role-level row in
    `pg_db_role_setting` (`setdatabase = 0`) carries no
    `statement_timeout`, or one that is zero, negative, or not parseable
    as a PostgreSQL duration. Or a per-database row for the database this
    connection is in sets the same key, whatever its value: that row
    takes precedence over the role-level one, so the declaration would
    not be what a session gets. For one role the first condition is
    reported before the second, and the second names the overriding
    database. Per-database rows for OTHER databases are not read
    (`_role_setting_rows`).

    This judges the DECLARATION, not the value in effect inside a running
    process: a role setting is copied into a session at login, so a
    connection opened before the setting was made keeps its old value
    until it is closed, and a pooled connection can outlive the change
    for as long as the process that holds it runs. `ops
    verify-declarations` is the only caller; no process runs this at
    startup."""
    application_audit_owner = _table_owner(conn, schema, "application_audit")
    control_audit_owner = _table_owner(conn, schema, "control_audit")
    reader_of_application_audit = set(_roles_with_table_privilege(conn, schema, "application_audit", "SELECT"))
    reader_of_control_audit = set(_roles_with_table_privilege(conn, schema, "control_audit", "SELECT"))
    for role in sorted(reader_of_application_audit & reader_of_control_audit):
        if role in (application_audit_owner, control_audit_owner):
            continue
        rows = _role_setting_rows(conn, role)
        declared_row: Optional[list[str]] = None
        per_database_names: list[str] = []
        for setdatabase, datname, setconfig in rows:
            if setdatabase == 0:
                declared_row = setconfig
            elif setconfig and any(entry.split("=", 1)[0] == _STATEMENT_TIMEOUT_KEY for entry in setconfig):
                per_database_names.append(datname or str(setdatabase))
        declared_ms: Optional[int] = None
        for entry in declared_row or []:
            key, sep, raw_value = entry.partition("=")
            if sep and key == _STATEMENT_TIMEOUT_KEY:
                try:
                    declared_ms = ms_from_pg_timeout_text(raw_value)
                except ValueError:
                    declared_ms = None
        if declared_ms is None or declared_ms <= 0:
            raise PlatformDeclarationError(_f17_message(role), code="F-17")
        if per_database_names:
            raise PlatformDeclarationError(_f17_message(role, database_name=per_database_names[0]), code="F-17")


# ---------------------------------------------------------------------------
# F-18 (R-91, work order docs/work-orders/WORK_ORDER_R91_MAX_CONNECTIONS_
# HEADROOM_CHECK_V1.md §1.2 D-1, peer-symmetric with r2db-api's own
# same-numbered addition): F-18 judges
# whether the platform this deployment DECLARES (`process_ceilings`) can
# open that many real connections against `max_connections` -- a
# cluster-wide question F-16 above never asks (F-16 judges only a single
# ROLE's own `CONNECTION LIMIT` against ITS OWN pool-composition floor).
# This is a NECESSARY condition, not a sufficient one (§1.1 (c)): it
# never counts an interactive/diagnostic `psql` session, and it
# deliberately judges the LOWER bound every `process_ceilings`-honoring
# deployment is guaranteed to open (one platform pool per data process,
# plus one runtime/developer pair per data process IF this platform has at
# least one registered application, plus one control-plane pool per
# control process), never the UPPER bound (every REGISTERED application
# times every data process, `auditreader` counted too) -- the declaration
# says nothing about which process serves which application or whether
# `auditreader`/control-plane are even deployed, so judging the upper
# bound would refuse deployments that would actually run fine (§1.1
# (c′)). All four startup call sites (`mitatedb_api.main.build_app`,
# `mitatedb_api.control_composition.build_control_service`, and their
# r2db-api equivalents) judge the SAME deployment-wide declaration,
# unscoped by role or plane -- UNLIKE F-16's own narrowed startup calls:
# narrowing F-18 to one process' own roles would report a false green
# while a SIBLING process' own declared ceiling already exceeds headroom,
# since `max_connections` is a resource every process on the cluster
# shares. `headroom_lower_bound`/`check_max_connections_headroom`/
# `_f18_message` are pinned isomorphic to r2db-api's own same-named
# realizations (`_ISOMORPHIC_TARGETS`), together with the `_count_
# registered_applications`/`_read_connection_headroom_settings`/
# `HeadroomReport` helpers they call -- none of these six takes a
# peer-specific argument; `check_max_connections_headroom`'s own caller
# passes this peer's own already-declared `concurrency` the same way
# `check_role_connection_limits`'s callers already do.
# ---------------------------------------------------------------------------


def headroom_lower_bound(
    *,
    data_processes: int,
    control_processes: int,
    platform_pool_floor: int,
    application_pair_floor: int,
    control_plane_floor: int,
    registered_applications: int,
) -> int:
    """The connection count every deployment honoring `process_ceilings`
    (`data_processes`/`control_processes`) is GUARANTEED to open, given
    this platform's own registered-application count: each data process
    always opens its own platform pool (`platform_pool_floor`); it also
    opens exactly ONE runtime/developer pair's worth (`application_pair_
    floor`) if this platform has at least one registered application --
    never scaled by HOW MANY applications are registered (a single
    process serves whichever applications it is actually given, not
    every one on the platform; the count that WOULD scale with
    registration is the upper bound, computed by this module's own
    caller, never here). Each control process always opens its own
    control-plane pool (`control_plane_floor`) -- `auditreader` is never
    added here: whether this deployment even runs a control process
    with an `auditreader` pool configured is not something `process_
    ceilings` declares (§1.1 (c′) (iii))."""
    application_floor = platform_pool_floor + (application_pair_floor if registered_applications >= 1 else 0)
    return data_processes * application_floor + control_processes * control_plane_floor


def _count_registered_applications(conn: "psycopg.Connection", schema: str) -> int:
    """The number of rows in `<schema>.applications` -- read unconditionally
    (never filtered by `runtime_role`/`developer_role` being set, unlike
    `check_role_connection_limits`'s own read of this table): a
    REGISTERED-only row (no roles provisioned yet) still means "this
    platform has at least one application", which is all `headroom_lower_
    bound` above needs to know."""
    with conn.cursor() as cur:
        cur.execute(sql.SQL("SELECT count(*) FROM {table}").format(table=sql.Identifier(schema, "applications")))
        (count,) = cur.fetchone()
    return count


_HEADROOM_SETTING_NAMES = ("max_connections", "superuser_reserved_connections", "reserved_connections")


def _read_connection_headroom_settings(conn: "psycopg.Connection") -> "tuple[int, int, int]":
    """`max_connections`/`superuser_reserved_connections`/`reserved_
    connections` (PG16), read directly off `pg_settings` -- a
    world-readable view (§1.3 (7): measured readable by a non-superuser
    `SET ROLE` session), so this never needs a superuser connection.
    Returns `(max_connections, superuser_reserved_connections, reserved_
    connections)`. Raises `PlatformDeclarationError(code="F-18")`, naming
    every missing name, if `pg_settings` answers fewer than all three rows
    -- never a bare `KeyError` a caller would have to translate itself."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT name, setting FROM pg_settings WHERE name = ANY(%s)",
            [list(_HEADROOM_SETTING_NAMES)],
        )
        settings = dict(cur.fetchall())
    missing = [name for name in _HEADROOM_SETTING_NAMES if name not in settings]
    if missing:
        raise PlatformDeclarationError(
            f"pg_settings did not answer {', '.join(missing)} -- F-18 cannot judge connection headroom without "
            f"all three of {', '.join(_HEADROOM_SETTING_NAMES)}.",
            code="F-18",
        )
    return (
        int(settings["max_connections"]),
        int(settings["superuser_reserved_connections"]),
        int(settings["reserved_connections"]),
    )


@dataclass(frozen=True)
class HeadroomReport:
    """`check_max_connections_headroom`'s own return shape (success only --
    a FAILING judgment raises instead, `_f18_message` below): the numbers
    `ops verify-declarations`'s own OK line reports (completion condition
    4)."""
    lower_bound: int
    upper_bound: int
    superuser_reserved_connections: int
    reserved_connections: int
    max_connections: int


def _f18_message(
    *,
    lower_bound: int,
    upper_bound: int,
    superuser_reserved_connections: int,
    reserved_connections: int,
    max_connections: int,
    ops_module: str,
) -> str:
    """The FAIL text `check_max_connections_headroom` raises with, naming
    every number its own judgment reads: the algorithm this judges is
    `lower_bound + superuser_reserved_connections + reserved_connections
    <= max_connections` (§1.2 D-1) -- `upper_bound` is named too, but only
    disclosed, never part of that judgment (§1.1 (c′))."""
    shortfall = lower_bound + superuser_reserved_connections + reserved_connections - max_connections
    return (
        f"declared process_ceilings' own connection lower bound {lower_bound} (upper bound {upper_bound}) plus "
        f"superuser_reserved_connections {superuser_reserved_connections} and reserved_connections "
        f"{reserved_connections} exceeds max_connections {max_connections} by {shortfall} -- raise max_connections, "
        f"or lower the declared process_ceilings -- see {ops_module}'s own provisioning runbook."
    )


def check_max_connections_headroom(
    conn: "psycopg.Connection", *, schema: str, ops_module: str,
    process_ceilings: ProcessCeilings, concurrency: int,
) -> HeadroomReport:
    """F-18: raises `PlatformDeclarationError(code="F-18")` when the LOWER
    bound of the connections `process_ceilings` guarantees this deployment
    opens (`headroom_lower_bound`, above) plus `superuser_reserved_
    connections` plus `reserved_connections` exceeds `max_connections`
    (all three read live off `pg_settings`, never a caller-supplied
    value). Equal is allowed (`<=`, not `<`). On success, returns a
    `HeadroomReport` carrying the lower bound, the UPPER bound (every
    REGISTERED application times every data process, `auditreader`'s own
    floor added to the control side too -- reported only, never judged,
    §1.1 (c′)), both reserved-connection settings, and `max_connections`
    itself, so the caller can print all four numbers without a second
    round of reads."""
    registered_applications = _count_registered_applications(conn, schema)
    platform_pool_floor = _API_ROLE_STORE_COUNT * concurrency
    application_pair_floor = 2 * concurrency
    control_plane_floor = _CONTROLPLANE_ROLE_POOL_FLOOR
    auditreader_floor = _AUDITREADER_ROLE_POOL_FLOOR
    lower_bound = headroom_lower_bound(
        data_processes=process_ceilings.data,
        control_processes=process_ceilings.control,
        platform_pool_floor=platform_pool_floor,
        application_pair_floor=application_pair_floor,
        control_plane_floor=control_plane_floor,
        registered_applications=registered_applications,
    )
    upper_bound = (
        process_ceilings.data * (platform_pool_floor + application_pair_floor * registered_applications)
        + process_ceilings.control * (control_plane_floor + auditreader_floor)
    )
    max_connections, superuser_reserved_connections, reserved_connections = _read_connection_headroom_settings(conn)
    if lower_bound + superuser_reserved_connections + reserved_connections > max_connections:
        raise PlatformDeclarationError(
            _f18_message(
                lower_bound=lower_bound,
                upper_bound=upper_bound,
                superuser_reserved_connections=superuser_reserved_connections,
                reserved_connections=reserved_connections,
                max_connections=max_connections,
                ops_module=ops_module,
            ),
            code="F-18",
        )
    return HeadroomReport(
        lower_bound=lower_bound,
        upper_bound=upper_bound,
        superuser_reserved_connections=superuser_reserved_connections,
        reserved_connections=reserved_connections,
        max_connections=max_connections,
    )


def ops_module_hint() -> str:
    """`PEER_MODULE`, named through a function (not referenced directly by
    `check_contract_170_declarations`'s own f-strings) so this check's
    error-message wording stays isomorphic across peers the same way the
    `_fN_message` builders above do (peer-IDENTICAL name, peer-SPECIFIC
    value read from this module's own `PEER_MODULE` constant)."""
    return PEER_MODULE


__all__ = [
    "CONTROL_PLANE_STATUS_ENV",
    "DEFAULT_SCHEMA",
    "MIGRATION_FILENAME",
    "MIGRATION_NUMBER",
    "PEER_DIR",
    "PEER_MODULE",
    "PROCESS_CEILINGS_MIGRATION_FILENAME",
    "PROCESS_CEILINGS_MIGRATION_NUMBER",
    "PROVISION_DSN_ENV",
    "REMOVED_SURFACE_ENV",
    "REMOVED_TIMEOUT_ENV",
    "TABLE_NAME",
    "VISIBILITY_LAG_CLOCK_SKEW_MARGIN_MS",
    "HeadroomReport",
    "PlatformDeclarationError",
    "PlatformDeclarations",
    "ProcessCeilings",
    "RoleTimeoutCatalog",
    "Surfaces",
    "check_auditreader_statement_timeout",
    "check_control_surface_consistency",
    "check_max_connections_headroom",
    "check_role_connection_limits",
    "check_writer_role_timeouts",
    "derive_visibility_lag_ms",
    "headroom_lower_bound",
    "read_declared_role_timeouts",
    "read_effective_timeouts_ms",
    "read_platform_declarations",
    "reject_removed_surface_env",
    "reject_removed_timeout_env",
    "require_control_surface_declared",
    "validate_audit_writer_roles_value",
    "validate_coalescing_window_value",
    "validate_process_ceilings_value",
    "validate_surfaces_value",
]
