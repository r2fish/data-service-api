"""Q4 phase (design docs/design/Q4_DB_SIDE_SINGLE_TRUTH_V1.md D-1/D-2,
work order docs/work-orders/WORK_ORDER_Q4_DB_SIDE_SINGLE_TRUTH_V1.md WP-1;
rework round, supervisor rulings 2026-09-05 -- rulings-q4-wp12-rework.md
sec.1, rulings-q4-writer-roles.md D-2(h), q4-f3c-and-amendments.md; Agent C
isomorphism convergence pass, rulings-q4-wp12-rework.md sec.5):

Reads and validates the platform database's DB-side declarations --
`r2dbsvc_registry.platform_declarations` (`surfaces`,
`audit_coalescing_window_ms`, `audit_writer_roles`; migration `0008`;
`process_ceilings`, Phase 10 WP-6a, migration `0012`) -- and double-checks
a writer role's `pg_db_role_setting` timeout catalog entries against that
SAME connection's own effective `pg_settings` value (D-1(b)).

Reference-implementation module (supervisor ruling 2026-09-05,
`{scratchpad}/rulings-q4-wp12-rework.md` sec.1): every name, signature and
return type below is shared verbatim with MitateDB-api's own same-named
realization -- peer differences close entirely over the ARGUMENTS a
caller passes in (`schema`, `ops_module`, `migration`, `names`,
`declared_roles`), never over a literal `r2db`/`R2DB`/`mitatedb`/
`MITATEDB` string baked into a pinned function's own body. A handful of
message-building helpers below (`_f1_message`/`_f2_message`/`_f8_message`/
`_f13_message`'s own `schema` mention, `_f6_forward_message`/
`_f6_reverse_message`'s own env-var mention) instead reach for this
MODULE's own peer-local constants (`PEER_MODULE`, `MIGRATION_NUMBER`,
`MIGRATION_FILENAME`, `PROVISION_DSN_ENV`, `PEER_DIR`, `DEFAULT_SCHEMA`,
`CONTROL_PLANE_STATUS_ENV`) by bare name rather than taking them as
parameters -- those constants are peer-specific VALUES but peer-IDENTICAL
NAMES, so the referencing function body stays textually isomorphic across
peers even though it is never literally handed those values as arguments.

`current_user`-based role identification, NOT naming-convention-derived
role names (rulings-q4-writer-roles.md, rejected alternative (a)): which
role is a declared audit writer is read from this table's own
`audit_writer_roles` row (D-2(h)), never derived from `schema.removesuffix
("_registry") + "_api"` or any other string-rewrite convention -- that
convention is production-only and breaks under a throwaway-prefixed test
fixture, which is exactly why the previous (pre-rework) round of this
module was rejected.

Fail-fast only: every function here either returns a validated value or
raises `PlatformDeclarationError` -- always a STARTUP failure (composition
root), never surfaced through any HTTP response (design §3.8's own header
note, SI-10). The one cell-open-time, API-facing condition (F-12, D-3(f))
belongs to a LATER work package's own module, not this one.

Every function that touches PostgreSQL takes an already-open `conn`
(never a `dsn`) -- callers open/close their own connections. This matters
most for `check_writer_role_timeouts`: it must run on the SAME connection
the writer sink actually uses (login role = the writer role being
checked, since a role setting only takes effect at login time and `SET
ROLE` cannot substitute, design D-1(c)) -- `r2db_api.main`/
`r2db_api.control_main` borrow this connection from their own audit
sink's pool (`PostgresApplicationAuditSink.borrow_connection`/
`PostgresControlAuditSink.borrow_connection`).

Peer-local, independently maintained (no cross-peer sharing, requester
ruling 2026-09-03) -- this module's read/validate/derive/check helpers are
pinned isomorphic to MitateDB-api's own same-named realizations by
`_ISOMORPHIC_TARGETS` (`tests/test_audit_query.py`).
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Optional
from urllib.parse import urlsplit

import psycopg
from psycopg import sql

from .pg_timeouts import ms_from_pg_timeout_text
from .structured import IDENTIFIER as _PG_IDENTIFIER_PATTERN
from .structured import MAX_IDENTIFIER_LENGTH as _PG_IDENTIFIER_MAX_LENGTH

#: This peer's own module path, named in every fail-fast message's "next
#: ops command" (design §3.8). Peer-local (no cross-peer sharing, requester
#: ruling 2026-09-03).
PEER_MODULE = "r2db_api"

#: Default registry schema this table lives in (D-2(a)) -- overridable by
#: this repository's own tests, which run the real migration files with
#: `r2dbsvc` textually replaced by a random throwaway prefix (the same
#: escape hatch `r2db_api.main`'s/`r2db_api.control_main`'s own
#: `R2DB_PLATFORM_SCHEMA` documents).
DEFAULT_SCHEMA = "r2dbsvc_registry"
TABLE_NAME = "platform_declarations"

#: The platform single-shot migration that creates the table, seeds the
#: two writer roles' timeout role-settings, and seeds `audit_writer_roles`
#: (design §8 migration allocation: r2db `0008`).
MIGRATION_NUMBER = "0008"
MIGRATION_FILENAME = "0008_platform_declarations_and_writer_timeouts.sql"

#: Phase 10 WP-6a (design docs/design/PHASE10_DEPLOYMENT_EVIDENCE_V1.md
#: D-5(ii), Q4 D-2(a)): the platform single-shot migration that widens
#: `platform_declarations_key_check` to admit `process_ceilings` -- a
#: SEPARATE migration from `MIGRATION_NUMBER` above (D-2(a)'s own "追加は
#: platform 単発 migration を要する" -- the key set is a closed, NAMED
#: `CHECK`, and an already-shipped migration is never edited in place).
PROCESS_CEILINGS_MIGRATION_NUMBER = "0012"
PROCESS_CEILINGS_MIGRATION_FILENAME = "0012_process_ceilings.sql"

#: The provision-DSN env var name this peer's own `ops.py` reads (named in
#: F-8's remedy text).
PROVISION_DSN_ENV = "R2DB_CONTROL_DSN"

#: `<peer>` in every fail-fast message's "next ops command" (design
#: §3.8) that names the psql invocation directly, rather than an `ops`
#: subcommand -- referenced by bare name from `_f8_message` only.
PEER_DIR = "r2db-api"

#: F-6's own env var name -- referenced by bare name from `_f6_forward_
#: message`/`_f6_reverse_message` only (Agent C isomorphism convergence,
#: rulings-q4-wp12-rework.md sec.1: the literal env var name was
#: previously baked directly into those two pinned message bodies, which
#: cannot normalize-diff empty against the sibling peer's own
#: differently-spelled literal -- this constant closes that the same way
#: `PROVISION_DSN_ENV` already does for F-8).
CONTROL_PLANE_STATUS_ENV = "R2DB_CONTROL_PLANE_STATUS"

#: The two removed env-var pairs this phase rejects outright (D-1(d)/
#: D-2(f)) -- composition roots check these against the `Mapping` they were
#: BUILT with, never `os.environ` (design D-1(d): "検査対象は composition
#: root に渡された env mapping であって os.environ ではない"). Peer-specific
#: values -- not part of the cross-peer isomorphic pin table
#: (rulings-q4-wp12-rework.md sec.1: "peer 名を含む定数は対応表に載せない").
REMOVED_TIMEOUT_ENV: tuple[str, ...] = ("R2DB_AUDIT_STATEMENT_TIMEOUT_MS", "R2DB_AUDIT_IDLE_TIMEOUT_MS")
REMOVED_SURFACE_ENV: tuple[str, ...] = ("R2DB_DATA_BASE_URL", "R2DB_CONTROL_BASE_URL")

_STATEMENT_TIMEOUT_KEY = "statement_timeout"
_IDLE_TIMEOUT_KEY = "idle_in_transaction_session_timeout"
_TIMEOUT_KEYS = (_STATEMENT_TIMEOUT_KEY, _IDLE_TIMEOUT_KEY)

#: D-1(c): the fixed clock-skew margin added on top of the writer roles'
#: summed timeouts when deriving `visibility_lag_ms`. Out-of-band from
#: `pg_db_role_setting` -- this codebase's own derivation constant, never
#: read from the catalog.
VISIBILITY_LAG_CLOCK_SKEW_MARGIN_MS = 1000


class PlatformDeclarationError(RuntimeError):
    """Every F-1..F-11/F-13/F-14 fail-fast condition this module raises. A
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
    """F-15's own validated return shape (design D-5(ii)): the deployer's
    declaration of the maximum number of processes that may serve each
    plane's declared `surfaces` base URL at the same time -- the value
    contract 1.8.0's enforcement-scope definition (`capability_status.
    rules`) is defined in terms of. Both fields are positive integers
    (`1` = the safe default every pre-Phase-10 deployment already was,
    a single process; `>= 2` means `limit_enforcement` for every
    in-memory-per-process-bound limit class reads `deployment_required`,
    never `enforced`, for that plane)."""
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
    """F-2: same step, same reasoning, the surfaces pair. `schema` is the
    caller's own resolved registry schema (design amendment 2026-09-05,
    N-7): the message must name the real schema, not this module's own
    `DEFAULT_SCHEMA`, since a deployment may override it."""
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


def _validate_base_url(field: str, raw: Any, *, suffix: str, schema: str, ops_module: str) -> str:
    """The three independent SHAPE checks a declared `surfaces.data.
    base_url`/`surfaces.control.base_url` must pass (design D-2(d)): an
    absolute URL, ending in the right suffix, with no trailing slash --
    checked as three separate conditions (design's own four malformed
    forms are independently observable this way)."""
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
    base_url` optional. This is the ONE place both `r2db_api.main` and
    `r2db_api.control_main` now call for URL-shape validation (closing
    L6-17, rulings-q4-wp12-rework.md sec.1) -- neither composition root
    keeps its own copy of this check any longer."""
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


def validate_coalescing_window_value(value: object, *, schema: str, ops_module: str) -> int:
    """F-4b(i) (design D-2(d)): the SAME function runs on the ops write
    path (`declare-coalescing-window`) and every read path -- a hand-edited
    row can never disagree with what `ops` would have accepted. Must be a
    `jsonb` number, an integer (`bool` is a Python `int` subclass, excluded
    explicitly -- a jsonb `true`/`false` must never silently read back as
    `1`/`0`), and non-negative (`0` means "no coalescing", a valid,
    documented value, design D-2(c))."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise PlatformDeclarationError(_f4b_window_message(schema, value, ops_module=ops_module), code="F-4b")
    return value


def validate_audit_writer_roles_value(value: object, *, schema: str, ops_module: str) -> tuple[str, ...]:
    """F-4b(ii) (rulings-q4-writer-roles.md D-2(h) point 6): a non-empty
    JSON array of distinct, valid PostgreSQL identifiers. Identifier
    validity reuses this package's OWN existing identifier check
    (`r2db_api.structured.IDENTIFIER`/`MAX_IDENTIFIER_LENGTH`, the same
    pattern `r2db_api.postgres` already applies to `runtime_role`/
    `developer_role`) rather than inventing a second one, and inlined
    directly here (not `structured.validate_identifier`, which raises a
    contract/HTTP-facing error via `errors.fail` -- wrong shape for a
    startup fail-fast)."""
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


# ---------------------------------------------------------------------------
# F-15 (Phase 10 WP-6a, design D-5(ii)): the `process_ceilings` row -- one
# combined check for "does the row exist and is it well-formed", the SAME
# treatment work order WP-6a's own §3 D-5(ii) reading calls for ("verify-
# declarations に足す番号は F-15" -- singular, unlike surfaces'
# existence/F-3 vs. shape/F-5 split). The row-existence check (inlined
# directly in `read_platform_declarations` below, as `"process_ceilings"
# not in rows` -- there is no standalone `require_process_ceilings_
# declared` function the way `require_control_surface_declared` exists for
# F-3c) and `validate_process_ceilings_value` (shape) both raise
# `code="F-15"` so `ops verify-declarations` (`_VERIFY_DECLARATIONS_EXIT_
# CODES`) needs exactly one new exit code, not two.
# ---------------------------------------------------------------------------


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
    (F-8) before (b) row existence (F-3 for `surfaces`, F-4 for
    `audit_coalescing_window_ms`, Phase 10 WP-6a F-15 for
    `process_ceilings` -- same "row must exist unconditionally, like
    `surfaces`" treatment, design D-5(ii)) -- a migration-not-applied
    platform database must never surface a raw psycopg 'relation does not
    exist' error. Value validation (F-5/F-4b, and F-15's own shape half)
    runs immediately after, on the SAME read (step 5). `audit_writer_
    roles`' own row is read in this SAME query too (design D-2(h)): a
    MISSING row is NOT raised here (returned as an empty tuple) -- its
    absence is exclusively the self-role inclusion check's concern (F-13,
    `check_writer_role_timeouts` below, design §3.7 step 6: "行が無い場合
    は...F-13になる"); a PRESENT but malformed value still raises F-4b
    here, immediately."""
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


def require_control_surface_declared(surfaces: Surfaces, *, schema: str, ops_module: str) -> None:
    """F-3c (control-plane composition root only): `surfaces.control` is
    unconditionally required for a control-plane process (design §3.7
    control 1-5) -- unlike the data-plane process, whose equivalent
    requirement is conditional on `R2DB_CONTROL_PLANE_STATUS` (F-6,
    `check_control_surface_consistency` below)."""
    if surfaces.control_base_url is None:
        raise PlatformDeclarationError(_f3c_message(schema, ops_module=ops_module), code="F-3c")


# ---------------------------------------------------------------------------
# F-6: `surfaces.control`'s presence must agree with the DATA-PLANE
# process' own `R2DB_CONTROL_PLANE_STATUS` -- design D-2(f), §3.8's own "F-6
# の推奨の向き" note (the forward direction's default recommendation is to
# fix `R2DB_CONTROL_PLANE_STATUS`, never `--no-control`, since the row is
# shared by both processes). Data-plane only -- the control-plane process
# has no such env var to cross-check against (it uses `require_control_
# surface_declared`/F-3c above instead).
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
    """F-6, both directions (design §3.8 F-6 note: "逆向き...も同型の1文で
    出す"). Data-plane only -- the control-plane process calls `require_
    control_surface_declared`/F-3c instead (it has no `*_CONTROL_PLANE_
    STATUS` of its own to cross-check)."""
    has_control = surfaces.control_base_url is not None
    if has_control and control_plane_status == "unavailable":
        raise PlatformDeclarationError(_f6_forward_message(ops_module=ops_module), code="F-6")
    if not has_control and control_plane_status != "unavailable":
        raise PlatformDeclarationError(_f6_reverse_message(control_plane_status, ops_module=ops_module), code="F-6")


# ---------------------------------------------------------------------------
# D-1(b): the role-setting dual check that replaces this peer's former
# per-connection `SET SESSION` audit-writer timeouts. (i) catalog
# declaration existence/validity (F-7/F-10/F-11, the F-11 scope narrowed by
# q4-f3c-and-amendments.md's "F-11 の絞り込み" amendment); (ii) THIS
# connection's own effective value, on a connection actually logged in as
# the role being checked (F-9); (iii) the self-role inclusion check (F-13,
# rulings-q4-writer-roles.md D-2(h) point 2) that gates both.
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
    """D-1(c): `max(statement_ms(role) + idle_ms(role) for role in
    audit_writer_roles) + VISIBILITY_LAG_CLOCK_SKEW_MARGIN_MS`. Pure --
    takes already-read catalogs (control-plane calls `read_declared_role_
    timeouts` once per role in `audit_writer_roles`, design D-2(h) point
    3, then this). Shipped defaults (5000/5000 for both roles) derive
    `11000` -- unchanged from the pre-Q4 constant this phase replaces."""
    return max(c.statement_ms + c.idle_ms for c in catalogs) + VISIBILITY_LAG_CLOCK_SKEW_MARGIN_MS


def check_writer_role_timeouts(
    conn: "psycopg.Connection", *, declared_roles: Sequence[str], schema: str, ops_module: str, migration: str,
) -> RoleTimeoutCatalog:
    """D-1(b) + D-2(h) 2, full dual check for the role `conn` is logged in
    as. `conn` MUST be a connection the caller's own writer sink actually
    uses to write (r2db-api: one connection borrowed from that sink's own
    pool; MitateDB-api: one connection opened via the SAME function the
    sink itself uses to open its connections) -- login role = the writer
    role being checked, since role-level settings only apply at login time
    and `SET ROLE` cannot substitute, design D-1(c): `r2db_api.main`/
    `r2db_api.control_main` each borrow one via their own
    `PostgresApplicationAuditSink.borrow_connection`/`PostgresControlAuditSink.
    borrow_connection`.

    Order (rulings-q4-writer-roles.md D-2(h) point 2, design §3.7 step 6):
    (1) `current_user` must be one of `declared_roles` -- F-13 if not
    (including when `declared_roles` is empty, i.e. the `audit_writer_
    roles` row itself is absent). (2) `read_declared_role_timeouts` for
    that role (F-7/F-10/F-11). (3) this SAME connection's own effective
    `pg_settings` value, compared ms-for-ms, never as rendered strings
    (F-9)."""
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
# order §2 WP-2e F-3, `{scratchpad}/rulings-r3-r7-flip.md` F-3, WP-2e rework
# `{scratchpad}/audit-wp2e.md` D-2, ruling L-2 = (A)): a new `ops verify-
# declarations` check that the contract 1.7.0 "enabled" declaration is TRUE
# of the actual deployed state, not a second, redundant copy of `r2db_api.
# limits.ResourceLimits.__post_init__`'s own construction-time check on a
# `ResourceLimits` instance this check builds for itself.
#
# The pre-rework `check_contract_170_resource_limits` had exactly that
# flaw (audit finding D-2): it constructed its own default `ResourceLimits
# ()` and checked THAT instance, so (a) a broken default never reached this
# function at all -- `ResourceLimits.__post_init__` already raises
# `ValueError` at construction, before `_verify_declarations_checks` gets a
# chance to catch a `PlatformDeclarationError` -- and (b) a healthy default
# always passes. `PlatformDeclarationError(code="F-14")` could therefore
# never actually be raised through the real `ops verify-declarations` code
# path -- a dead check, "OK F-14" printed unconditionally with no signal
# behind it.
#
# `check_contract_170_declarations` replaces it with three checks, only the
# third of which is genuinely reachable through a real deployment's own
# state (the other two stay useful regression guards against a future code
# change, same honest scope `check_writer_role_timeouts` above documents
# for its own construction-time-only conditions):
#   (a) the SERVED capabilities document (the caller's own `capabilities()`
#       call, never rebuilt here) actually declares `constraint_
#       declarations`/`dry_run`/`idempotency`/`request_budget` `enabled`.
#   (b) M-7 (`{scratchpad}/audit-wp2e-2.md` R-7): the SAME served
#       capabilities document's own `limits` block (never a fresh
#       `ResourceLimits()` constructed here -- that residual flaw, caught
#       by the closure audit, was the same "unreachable through a real
#       deployment" bug as the pre-rework function had for (a)) carries a
#       positive `enum_members`/`idempotency_entries`/`idempotency_
#       retention_ms`.
#   (c) EVERY registered application's own per-application upgrade ledger
#       (R-2/R-5, migrations `0009`/`0010`/`0011`) already carries every
#       number this shipped version requires (`applied_upgrade_numbers_
#       by_application`, `required_upgrade_numbers` -- the caller passes
#       `r2db_api.platform_upgrades.PLATFORM_UPGRADE_NUMBERS`). This is the
#       one part of F-14 a real deployment can actually fail: an
#       application whose database has not yet run `ops upgrade-
#       applications` makes the "enabled" declaration false for that
#       application's own traffic, regardless of what the platform-wide
#       capability document says -- so this fails closed per-application,
#       not just once for the whole platform.
def check_contract_170_declarations(
    capabilities_document: Mapping[str, Any],
    applied_upgrade_numbers_by_application: Mapping[str, Optional[frozenset[int]]],
    required_upgrade_numbers: frozenset[int],
) -> None:
    """F-14. `capabilities_document` is the value the caller's own live
    `capabilities()` call returned (or an equivalent already-served
    document) -- this function never constructs one itself, for EITHER
    half of the check. `applied_upgrade_numbers_by_application` maps every
    registered application's slug to `platform_upgrades.read_applied_
    upgrade_numbers`'s own return value for that application's database
    (`None` when that application has no ledger table at all -- read as
    "every number is pending", the same convention `platform_upgrades.
    pending_upgrade_numbers` already uses).

    WP-2e closure audit M-7 (`{scratchpad}/audit-wp2e-2.md` R-7, ruling
    `{scratchpad}/rulings-r3-r7-flip.md` addendum 2 L-2 (a)): the limit-
    class half used to take a separate, caller-constructed `ResourceLimits`
    argument and read ITS attributes -- but `ResourceLimits.__post_init__`
    already refuses to construct a value carrying a non-positive class, so
    a caller building a throwaway `ResourceLimits()` (`ops.py`'s own
    `cmd_verify_declarations`, before this fix) could never actually
    surface a broken deployment through this half of F-14 either: any
    broken value crashes the CONSTRUCTOR, before `check_contract_170_
    declarations` is even called, with an uncaught `ValueError`, not this
    function's own `PlatformDeclarationError`. This half now reads the
    SAME served `capabilities_document`'s own `limits` block (`{"limits":
    ResourceLimits.as_dict()}`, `DataService.capabilities()`'s real,
    already-served shape) that the capability half above already reads
    from -- checking the declaration the way an operator (or a client)
    actually observes it, exactly like L-2 (a)'s own wording: "capability
    document が ... limits に ... を持つこと"."""
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
#: requires `status: "enabled"` for (contract 1.7.0, D-1/D-6).
_CONTRACT_170_ENABLED_CAPABILITIES: tuple[str, ...] = ("constraint_declarations", "dry_run", "idempotency", "request_budget")

#: The `ResourceLimits` fields `check_contract_170_declarations` requires a
#: positive integer for (contract 1.7.0, D-2 (7)/D-5).
_CONTRACT_170_LIMIT_CLASSES: tuple[str, ...] = ("enum_members", "idempotency_entries", "idempotency_retention_ms")


# ---------------------------------------------------------------------------
# F-16 (Phase 10 WP-4f, supervisor ruling 2026-09-09, following the WP-4e
# conformance investigation's own finding -- see that WP's report): every
# PostgreSQL role this deployment's own processes pool connections against
# must have a `CONNECTION LIMIT` (`pg_roles.rolconnlimit`) of `-1`
# (unlimited) or at least that role's own worst-case simultaneous
# connection count ("pool 合計") -- otherwise a burst of real concurrent
# requests hits PostgreSQL's own hard `FATAL: too many connections for
# role` refusal instead of the declared 429/503 the contract promises
# (WP-4e's own measured `r2dbsvc_controlplane` finding: 4 stores x fixed
# `pool_size` 4 = 16, against a `CONNECTION LIMIT` of only 10 -- already a
# real production defect with a single control-plane process, no test
# harness involved).
#
# Role IDENTITY is read from REAL GRANTS (`information_schema.role_table_
# grants` on the fixed, migration-defined `application_audit`/
# `control_audit` table names), never from a schema/role-name string-
# rewrite convention: this module's own header already rejects that
# technique for writer-role identification (rulings-q4-writer-roles.md,
# rejected alternative (a)) precisely because it is production-only and
# breaks under a throwaway-prefixed test fixture -- the SAME reasoning
# applies here. `application_audit`/`control_audit` are schema-qualified
# object names fixed by this migration set's own DDL (never deployment-
# chosen), so querying grants on them is reading real, already-declared
# database state, not guessing a name.
#
# Runtime/developer role names, unlike the platform-plane roles above, ARE
# read directly off `<schema>.applications` -- also real stored data, not a
# derived name.
#
# Deliberately excludes `r2dbsvc_control` (short-lived, one-shot CLI/
# provisioning connections only -- no persistent pool, and no stored
# declaration this check could read to derive a floor for it, the same
# "out of scope" category as F-1/F-2/F-12, `_verify_declarations_checks`'s
# own trailing disclosure line). This is an EXPLICIT exclusion
# (`_table_owner`, below), not merely "no grants match its identity" --
# `r2dbsvc_control` is the role every migration in this set runs `CREATE
# TABLE application_audit`/`CREATE TABLE control_audit` AS (0007/0006's
# own "WHO RUNS THIS" headers), so as the OWNER of both tables it
# implicitly holds INSERT and SELECT on both without ever appearing as a
# `grantee` row -- meaning it would otherwise match all three platform-
# plane role classes below at once (measured 2026-09-10, WP-4 integration
# review M-1).
# ---------------------------------------------------------------------------

#: `r2db_api.main`'s own `credentials` + `durable_audit` stores, both
#: pool-sized to `role_pool_size(thread_limit)` (unless
#: `R2DB_PLATFORM_POOL_SIZE` overrides it) and both against
#: `r2dbsvc_api` -- identified by `INSERT` on `application_audit`.
_API_ROLE_STORE_COUNT = 2

#: `r2db_api.control_main`'s own 4 platform-plane stores (`applications`/
#: `credentials`/`control_credentials`/`audit`), each a FIXED `pool_size`
#: of 4 (WP-4e's own investigated-and-reverted default, `build_control_
#: app`'s own comment) -- NOT concurrency-derived, unlike `r2dbsvc_api`
#: above. Identified by `INSERT` on `control_audit`.
_CONTROLPLANE_ROLE_POOL_FLOOR = 16

#: `PostgresAuditQueryStore`'s own single pool, fixed `pool_size` 4
#: (`credential_store.py`'s own default). Identified by `SELECT` on BOTH
#: `application_audit` AND `control_audit` (migration 0007's own grant
#: shape -- no other role holds `SELECT` on either table).
_AUDITREADER_ROLE_POOL_FLOOR = 4


def _roles_with_table_privilege(conn: "psycopg.Connection", schema: str, table: str, privilege: str) -> list[str]:
    """Every role (`grantee`) actually granted `privilege` on `<schema>.
    <table>` -- `information_schema.role_table_grants` is a world-readable
    view (like `pg_db_role_setting`, `_role_setting_rows`'s own comment
    above): any connection can run this regardless of its own login role.
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
    role, e.g. `r2dbsvc_control`) from being misidentified as matching
    every platform-plane role class at once (M-1, WP-4 integration review
    2026-09-10). Returns `None` if the table does not exist (a caller
    scoped to `role_classes={"api"}` or similar, e.g. `r2db_api.main`'s
    own startup F-16 call, may run before `0007_application_audit.sql`
    or `0006_control_plane_http.sql` are guaranteed applied against the
    connection it happens to be given) -- exactly like `_roles_with_table_
    privilege` above, which already tolerates a missing table by simply
    returning no rows (`information_schema.role_table_grants` is a plain
    view; filtering it on a nonexistent table name errors on neither
    engine). `None` never equals a real role name, so the exclusion
    checks below simply never match in that case, the same as if this
    function were never called at all."""
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
#: any subset of this set.
_ROLE_CLASSES = frozenset({"api", "controlplane", "auditreader"})


def check_role_connection_limits(
    conn: "psycopg.Connection", *, schema: str, ops_module: str, pool_size: int,
    process_ceilings: ProcessCeilings,
    role_classes: "frozenset[str] | None" = None,
    application_slugs: "Sequence[str] | None" = None,
) -> None:
    """F-16: raises `PlatformDeclarationError(code="F-16")` for the FIRST
    role (in the deterministic order built below) whose `pg_roles.
    rolconnlimit` is neither `-1` nor at least its own computed floor.
    `pool_size` is the caller's own declared per-role pool ceiling
    (`r2db_api.limits.role_pool_size(thread_limit)`, the real per-process
    simultaneous-borrow ceiling) -- this function takes it as a plain
    argument rather than constructing its own default instance, so a
    deployment that has genuinely raised its real pool size is checked
    against ITS OWN real floor, not a silently-stale code-level default.

    design D-3 (5): `role_pool_size(thread_limit)`
    sizes ONE process' own pool; `pg_roles.rolconnlimit` is a
    CLUSTER-WIDE cap shared by every one of `process_ceilings.<plane>`
    processes that pools a connection against that role, each with its
    own `pool_size`-sized pool -- this function multiplies every floor
    it computes by the process count of the plane that role belongs to:
    `process_ceilings.data` for the `api` class and every application's
    runtime/developer role, `process_ceilings.control` for the
    `controlplane` and `auditreader` classes. A caller multiplying
    `pool_size` itself before calling in would count the process count
    twice, since this function already multiplies by it -- every caller
    passes its own plain, un-multiplied `pool_size` and the SAME
    `process_ceilings` this process read from the declarations row.

    Checks exactly the role classes `0013_role_connection_limits.sql`
    (this peer) / the sibling peer's own same-numbered migration raises:
    the platform-plane `<...>_api`/`<...>_controlplane`/`<...>_
    auditreader` roles (module-level floor constants above) and every
    REGISTERED application's own runtime/developer roles (floor =
    `pool_size * process_ceilings.data`, one store each, Phase 10 WP-8a).
    A role with no grants matching any of the three platform-plane shapes
    above (identity unknown to this check) is silently skipped, never
    flagged -- this check only ever verifies roles it can positively
    identify, exactly like every other read in this module never guesses
    at what it cannot observe.

    Phase 10 WP-4g (supervisor ruling 2026-09-09): `role_classes`/
    `application_slugs` let a caller narrow this check to exactly the
    role(s) ITS OWN process pools connections against, instead of every
    role this whole platform has -- `ops verify-declarations`'s own
    aggregate call (the pre-existing, unchanged default: both `None`)
    still checks everything platform-wide, but `r2db_api.main`/`r2db_api.
    control_main`'s own startup fail-fast calls (added this WP) pass
    these so an UNRELATED application's or the SIBLING plane's own
    misconfigured role never blocks a process that never pools a
    connection against it at all. `role_classes`, when given, is any
    subset of `{"api", "controlplane", "auditreader"}` (`None` -- the
    default -- means all three, unchanged pre-existing behavior).
    `application_slugs`, when given (not `None`), restricts the runtime/
    developer role check to exactly the named slugs -- an EMPTY sequence
    means "check no application role at all" (`control_main`'s own case:
    that process serves no application); `None` (the default) means every
    registered application, unchanged pre-existing behavior."""
    if role_classes is None:
        role_classes = _ROLE_CLASSES
    floors: dict[str, int] = {}
    # M-1 (WP-4 integration review 2026-09-10): a role can legitimately
    # match MORE than one platform-plane class below (a role granted
    # INSERT on both audit tables, or INSERT on one and SELECT on both,
    # for example) -- `max(...)` keeps the STRICTEST floor that role is
    # actually subject to instead of whichever class happened to assign
    # last. `_table_owner` exclusion keeps the table-owning operator role
    # (`r2dbsvc_control`, never a real pooled role -- see the module
    # header above) from being misidentified as matching all three via
    # its implicit owner ACL.
    application_audit_owner = _table_owner(conn, schema, "application_audit")
    control_audit_owner = _table_owner(conn, schema, "control_audit")
    if "api" in role_classes:
        for role in _roles_with_table_privilege(conn, schema, "application_audit", "INSERT"):
            if role == application_audit_owner:
                continue
            floors[role] = max(floors.get(role, 0), _API_ROLE_STORE_COUNT * pool_size * process_ceilings.data)
    if "controlplane" in role_classes:
        for role in _roles_with_table_privilege(conn, schema, "control_audit", "INSERT"):
            if role == control_audit_owner:
                continue
            floors[role] = max(floors.get(role, 0), _CONTROLPLANE_ROLE_POOL_FLOOR * process_ceilings.control)
    if "auditreader" in role_classes:
        reader_of_application_audit = set(_roles_with_table_privilege(conn, schema, "application_audit", "SELECT"))
        reader_of_control_audit = set(_roles_with_table_privilege(conn, schema, "control_audit", "SELECT"))
        for role in sorted(reader_of_application_audit & reader_of_control_audit):
            if role == application_audit_owner or role == control_audit_owner:
                continue
            floors[role] = max(floors.get(role, 0), _AUDITREADER_ROLE_POOL_FLOOR * process_ceilings.control)

    if application_slugs is None or len(application_slugs) > 0:
        applications_table = sql.Identifier(schema, "applications")
        base_statement = "SELECT runtime_role, developer_role FROM {table} WHERE runtime_role IS NOT NULL AND developer_role IS NOT NULL"
        with conn.cursor() as cur:
            if application_slugs is None:
                cur.execute(sql.SQL(base_statement + " ORDER BY application_slug").format(table=applications_table))
            else:
                cur.execute(
                    sql.SQL(base_statement + " AND application_slug = ANY(%s) ORDER BY application_slug").format(table=applications_table),
                    [list(application_slugs)],
                )
            for runtime_role, developer_role in cur.fetchall():
                floors[runtime_role] = pool_size * process_ceilings.data
                floors[developer_role] = pool_size * process_ceilings.data

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
# HEADROOM_CHECK_V1.md §1.2 D-1): F-18
# judges whether the platform this deployment DECLARES (`process_
# ceilings`) can open that many real connections against `max_connections`
# -- a cluster-wide question F-16 above never asks (F-16 judges only a
# single ROLE's own `CONNECTION LIMIT` against ITS OWN pool-composition
# floor). This is a NECESSARY condition, not a sufficient one (§1.1 (c)):
# it never counts an interactive/diagnostic `psql` session, and it
# deliberately judges the LOWER bound every `process_ceilings`-honoring
# deployment is guaranteed to open (one platform pool per data process,
# plus one runtime/developer pair per data process IF this platform has at
# least one registered application, plus one control-plane pool per
# control process), never the UPPER bound (every REGISTERED application
# times every data process, `auditreader` counted too) -- the declaration
# says nothing about which process serves which application or whether
# `auditreader`/control-plane are even deployed, so judging the upper
# bound would refuse deployments that would actually run fine (§1.1
# (c′)). All four startup call sites (`r2db_api.main.build_app`,
# `r2db_api.control_main.build_control_app`, and their MitateDB-api
# equivalents) judge the SAME deployment-wide declaration, unscoped by
# role or plane -- UNLIKE F-16's own narrowed startup calls: narrowing
# F-18 to one process' own roles would report a false green while a
# SIBLING process' own declared ceiling already exceeds headroom, since
# `max_connections` is a resource every process on the cluster shares.
# `headroom_lower_bound`/`check_max_connections_headroom`/`_f18_message`
# are pinned isomorphic to MitateDB-api's own same-named realizations
# (`_ISOMORPHIC_TARGETS`), together with the `_count_registered_
# applications`/`_read_connection_headroom_settings`/`HeadroomReport`
# helpers they call -- none of these six takes a peer-specific argument;
# `check_max_connections_headroom`'s own caller passes this peer's own
# already-declared `concurrency` the same way `check_role_connection_
# limits`'s callers already do.
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
    process_ceilings: ProcessCeilings, pool_size: int,
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
    round of reads.

    design D-3 (5): every caller passes
    `r2db_api.limits.role_pool_size(thread_limit)`; see `check_role_
    connection_limits`'s own docstring for the full rationale. Completion
    condition 71: with `process_ceilings.data` = 4, `thread_limit` = 4,
    `c` = 2 (`pool_size` = 6), the lower bound this function judges does
    not scale with the declared `concurrency` bound at all."""
    registered_applications = _count_registered_applications(conn, schema)
    platform_pool_floor = _API_ROLE_STORE_COUNT * pool_size
    application_pair_floor = 2 * pool_size
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


def _f19_message(database_name: str, *, reason: str) -> str:
    if reason == "missing":
        return (
            f"application database '{database_name}' has no matching row in pg_database -- its collation "
            f"cannot be judged. Re-provision this application with the current 0003_provision_application.sql, "
            f"or complete its deprovisioning (0004_deprovision_application.sql) instead if this row is a "
            f"deprovision left mid-way."
        )
    if reason == "collate":
        return (
            f"application database '{database_name}' was not provisioned with a codepoint-order collation. "
            f"Re-provision it with the current 0003_provision_application.sql -- an existing database's own "
            f"collation cannot be changed in place."
        )
    if reason == "ctype":
        return (
            f"application database '{database_name}' has its own ctype set to 'C', which would turn non-ASCII "
            f"case folding and pattern matching ASCII-only. Re-provision it with the current 0003_provision_"
            f"application.sql."
        )
    return (
        f"application database '{database_name}' does not use the libc locale provider, so its own LC_COLLATE "
        f"setting does not govern its string ordering. Re-provision it with the current 0003_provision_"
        f"application.sql, against a cluster initialized (initdb) with the libc locale provider -- re-running "
        f"0003 against a cluster whose own template0 already uses ICU will not fix this."
    )


def check_application_collations(conn: "psycopg.Connection", *, schema: str) -> None:
    """F-19: every REGISTERED, PROVISIONED application's own database
    (`database_name IS NOT NULL`: provisioned rows only, not the full
    `count(*)` target set `check_max_connections_headroom`'s own `_count_
    registered_applications` counts) was provisioned with a codepoint-order
    collation, matching this peer's own non-PostgreSQL backend. Raises
    `PlatformDeclarationError(code="F-19")` for the FIRST such database, in
    `database_name` order, that fails any of the following.

    `pg_database.datcollate` is not `'C'` -- the database's own string
    ordering is still locale-dependent. `pg_database.datctype` IS `'C'`
    -- the ctype must stay the cluster's own UTF-8 locale; a `'C'` ctype
    would turn non-ASCII case folding and pattern matching ASCII-only.
    On a server that can
    report it (`pg_database.datlocprovider`, PostgreSQL 15 and later
    only -- older servers have no such column and this third condition
    is skipped there), the locale provider is something other than libc
    (`'c'`): an ICU-provider database's own `LC_COLLATE` string does not
    actually govern its ordering, so the first two conditions passing
    would be a false green.

    A registered application whose own `database_name` has no matching
    `pg_database` row at all also fails -- an existing database's own
    collation cannot be judged, or fixed in place, once it no longer
    exists; re-provisioning is the only remedy either way."""
    table = sql.Identifier(schema, "applications")
    checks_provider = conn.info.server_version >= 150000
    with conn.cursor() as cur:
        cur.execute(
            sql.SQL(
                "SELECT database_name FROM {table} WHERE database_name IS NOT NULL ORDER BY database_name"
            ).format(table=table)
        )
        applications = cur.fetchall()
        for (database_name,) in applications:
            if checks_provider:
                cur.execute(
                    "SELECT datcollate, datctype, datlocprovider FROM pg_database WHERE datname = %s",
                    [database_name],
                )
            else:
                cur.execute(
                    "SELECT datcollate, datctype FROM pg_database WHERE datname = %s",
                    [database_name],
                )
            row = cur.fetchone()
            if row is None:
                raise PlatformDeclarationError(_f19_message(database_name, reason="missing"), code="F-19")
            if row[0] != "C":
                raise PlatformDeclarationError(_f19_message(database_name, reason="collate"), code="F-19")
            if row[1] == "C":
                raise PlatformDeclarationError(_f19_message(database_name, reason="ctype"), code="F-19")
            if checks_provider and row[2] != "c":
                raise PlatformDeclarationError(_f19_message(database_name, reason="provider"), code="F-19")


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
    "check_application_collations",
    "check_auditreader_statement_timeout",
    "check_contract_170_declarations",
    "check_control_surface_consistency",
    "check_max_connections_headroom",
    "check_role_connection_limits",
    "check_writer_role_timeouts",
    "derive_visibility_lag_ms",
    "headroom_lower_bound",
    "ops_module_hint",
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
