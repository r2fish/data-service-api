# src/r2db_api/ops.py -- code-comment history (change set 4)

Companion for `src/r2db_api/ops.py` per `docs/code-history/README.md`.

## CH-0288

- moved from: `src/r2db_api/ops.py` (`<module>`)
- parent commit: `4d45fc6`
- kind: docstring

```
r2db-api out-of-band control-plane CLI: ``python -m r2db_api.ops``.

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
```

## CH-0289

- moved from: `src/r2db_api/ops.py` (`<module>`)
- parent commit: `4d45fc6`
- kind: comment

```
# WP-5 round-2 review NIT-2: the control-credential id prefix ("ctl_") now
# has a single home -- `control_plane._new_control_credential_id()`, used
# by the shared ceremony functions this module calls (`bootstrap_control_
# credential`/`reset_control_credentials`) -- this module no longer mints
# a control credential id itself, so it no longer needs its own copy of
# that prefix constant.
```

## CH-0290

- moved from: `src/r2db_api/ops.py` (`<module>`)
- parent commit: `4d45fc6`
- kind: comment

```
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
# comment (now in `delete_confirmation.py`), rule (c): a phrase never reflects unvalidated client input back
# to the client) and closes rule (d) (bounded length) the same way: a
# format-validated id is always exactly 20 characters, so no digest escape
# hatch is needed for this phrase the way `delete`/`drop_entity`/
# `drop_index` need one for a contract-unbounded identifier.
```

## CH-0291

- moved from: `src/r2db_api/ops.py` (`<module>`)
- parent commit: `4d45fc6`
- kind: comment

```
# MA-3 (round-2 review): arbitrary, fixed 64-bit `pg_advisory_xact_lock` key
# for the bootstrap/reset ritual only -- see `_lock_ritual` below. Chosen
# once, must never change (changing it would silently stop serializing
# against any already-running process still using the old key -- there is
# no migration path for an advisory lock key, unlike a table/column).
```

## CH-0292

- moved from: `src/r2db_api/ops.py` (`<module>`)
- parent commit: `4d45fc6`
- kind: comment

```
# Q4 WP-3 (design D-4(b), work order §4 WP-3 change table E): r2db-api had
# neither a `psql` subprocess invocation nor a migrations-directory
# resolver before this WP -- both are new here, modeled on MitateDB-api's
# own `_run_deprovision_script`/`_migrations_dir` (`MitateDB-api/src/
# mitatedb_api/ops.py:541-550`/`:373-375`) -- CALL SHAPE ONLY, never `_die`
# (D-4(b): "`_die`は使わない -- 即時exit 2では全DBを回せない").
```

### correction: 2026-09-16

- reason: R-22 change set 0i (rulings Z0i-4d, Z0i-4g) -- the raw line ranges had gone stale (at `7bc6650`, `_run_deprovision_script` starts at `MitateDB-api/src/mitatedb_api/ops.py:553` and `_migrations_dir` at `:380`), so both now name the definitions they meant, on the same path

old:
```
Q4 WP-3 (design D-4(b), work order §4 WP-3 change table E): r2db-api had neither a `psql` subprocess invocation nor a migrations-directory resolver before this WP -- both are new here, modeled on MitateDB-api's own `_run_deprovision_script`/`_migrations_dir` (`MitateDB-api/src/mitatedb_api/ops.py:541-550`/`:373-375`) -- CALL SHAPE ONLY, never `_die` (D-4(b): "`_die`は使わない -- 即時exit 2では全DBを回せない").
```

new:
```
Q4 WP-3 (design D-4(b), work order §4 WP-3 change table E): r2db-api had neither a `psql` subprocess invocation nor a migrations-directory resolver before this WP -- both are new here, modeled on MitateDB-api's own `_run_deprovision_script`/`_migrations_dir` (`MitateDB-api/src/mitatedb_api/ops.py::_run_deprovision_script`/`::_migrations_dir`) -- CALL SHAPE ONLY, never `_die` (D-4(b): "`_die`は使わない -- 即時exit 2では全DBを回せない").
```

## CH-0293

- moved from: `src/r2db_api/ops.py` (`_application_dsn`)
- parent commit: `4d45fc6`
- kind: docstring

```
Design D-4(b): `ops` only ever holds a provision DSN pointing at the
PLATFORM database -- reaching one application's own database means
swapping `dbname` in that same DSN's own connection parameters, never
a second, separately-configured credential (`psycopg.conninfo.
conninfo_to_dict`/`make_conninfo`, named explicitly by the design).
```

## CH-0294

- moved from: `src/r2db_api/ops.py` (`_control_store`)
- parent commit: `4d45fc6`
- kind: docstring

```
Constructs the control-credential store for the bootstrap/reset
ritual and the control-credential break-glass subcommands. R-2's pepper-
separation check runs here -- "この検査は store 構築側 ... に置く" (design
§1 R-2) -- against whatever this *process' environment* actually holds
for both pepper names, independent of whether the specific subcommand
being run needs the application-plane pepper at all: an operator's
shell/secret-manager profile realistically configures both env vars
together, and that is exactly the context this check exists to catch.
```

## CH-0295

- moved from: `src/r2db_api/ops.py` (`_control_audit_sink`)
- parent commit: `4d45fc6`
- kind: docstring

```
CCR-14 WP-5 (ceremony core extraction, work order §2): the bootstrap/
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
for.
```

## CH-0296

- moved from: `src/r2db_api/ops.py` (`_print_issued`)
- parent commit: `4d45fc6`
- kind: comment

```
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
```

## CH-0297

- moved from: `src/r2db_api/ops.py` (`_write_control_audit`)
- parent commit: `4d45fc6`
- kind: docstring

```
Writes one canonical `control_audit` row on `conn` -- the exact same
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
```

## CH-0298

- moved from: `src/r2db_api/ops.py` (`_lock_ritual`)
- parent commit: `4d45fc6`
- kind: docstring

```
MA-3 (round-2 review): serializes concurrent `bootstrap`/`reset`
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
```

## CH-0299

- moved from: `src/r2db_api/ops.py` (`<module>`)
- parent commit: `4d45fc6`
- kind: comment

```
# ---------------------------------------------------------------------------
# CLI declare-and-echo gate (Q-1 WP-4, docs/design/DESTRUCTIVE_CONFIRMATION_
# V1.md R-4) -- `reset` and `delete-credential` only (Q1-D4/WP-0 MA-1: this
# CLI's `revoke-credential` targets application credentials, exactly the
# operation class Q1-D1 already leaves unconfirmed -- gating it here would
# put friction on playbook step 3's own bulk-revoke incident-response flow
# for no contract-required reason). Every other subcommand's external
# behaviour is unchanged by this WP.
# ---------------------------------------------------------------------------
```

## CH-0300

- moved from: `src/r2db_api/ops.py` (`_require_cli_confirmation`)
- parent commit: `4d45fc6`
- kind: docstring

```
Contract 1.2.0 `destructive_confirmation`'s exact-match rule
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
```

## CH-0301

- moved from: `src/r2db_api/ops.py` (`<module>`)
- parent commit: `4d45fc6`
- kind: comment

```
# ---------------------------------------------------------------------------
# Application-credential subcommands (pre-existing; now audited -- §8 M-10).
# ---------------------------------------------------------------------------
```

## CH-0302

- moved from: `src/r2db_api/ops.py` (`cmd_issue_credential`)
- parent commit: `4d45fc6`
- kind: comment

```
# Coordinator item 3 (2026-09-04 review): `store.add` is now
# this CLI's own issuance point -- it returns the composed
# bearer directly (design D-1(c) "合成は store/service 層の
# み"), so this call site no longer composes it itself (see
# `_print_issued`'s own docstring: every caller now passes an
# already-composed value straight through).
```

## CH-0303

- moved from: `src/r2db_api/ops.py` (`cmd_rotate_credential`)
- parent commit: `4d45fc6`
- kind: comment

```
# Coordinator follow-up (2026-09-04 audit finding §3-A):
# `store.rotate` is now this CLI's own re-issuance point -- it
# returns the composed bearer directly (same discipline as
# `store.add` in `cmd_issue_credential` above), so this call
# site no longer composes it itself.
```

## CH-0304

- moved from: `src/r2db_api/ops.py` (`cmd_delete_credential`)
- parent commit: `4d45fc6`
- kind: comment

```
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
```

## CH-0305

- moved from: `src/r2db_api/ops.py` (`cmd_delete_credential`)
- parent commit: `4d45fc6`
- kind: comment

```
#
# Q-1 WP-4 (design R-4): gated by `--confirm DELETE_CREDENTIAL
# <credential_id>` -- checked before `_store()` is even constructed (see
# `_require_cli_confirmation`'s own docstring), so an omitted/mismatched
# `--confirm` never touches the database at all, regardless of whether
# this credential_id exists or is already revoked (both are the *next*
# thing checked, inside `store.delete` itself, only once this gate has
# already passed).
```

## CH-0306

- moved from: `src/r2db_api/ops.py` (`cmd_audit_report`)
- parent commit: `4d45fc6`
- kind: docstring

```
R-11 playbook helper (docs/design/R2DB_CCR14_CONTROL_PLANE_V1.md R-11
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
```

## CH-0307

- moved from: `src/r2db_api/ops.py` (`<module>`)
- parent commit: `4d45fc6`
- kind: comment

```
# ---------------------------------------------------------------------------
# Control-credential ritual (bootstrap/reset -- R-5) and break-glass (R-10).
# ---------------------------------------------------------------------------
```

## CH-0308

- moved from: `src/r2db_api/ops.py` (`cmd_bootstrap`)
- parent commit: `4d45fc6`
- kind: docstring

```
Issues the very first control credential. Refuses if *any*
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
```

## CH-0309

- moved from: `src/r2db_api/ops.py` (`cmd_reset`)
- parent commit: `4d45fc6`
- kind: docstring

```
Revokes every existing control credential and issues one new one,
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
```

## CH-0310

- moved from: `src/r2db_api/ops.py` (`cmd_issue_audit_credential`)
- parent commit: `4d45fc6`
- kind: docstring

```
Phase 3.5 WP-4 (design PHASE35_CROSS_ENTITY_AND_CONTRACT_130_V1.md
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
```

## CH-0311

- moved from: `src/r2db_api/ops.py` (`cmd_enable_control_credential`)
- parent commit: `4d45fc6`
- kind: docstring

```
R-10 break-glass: recovers from the one lockout `reset` is heavier
than necessary for -- the sole live control credential having been
disabled (not revoked). Un-revoke is never offered here (`set_state`
refuses it, matching `enable-credential`'s existing un-revoke
refusal) -- revocation stays terminal; `reset` is the only recovery
once a control credential is revoked.
```

## CH-0312

- moved from: `src/r2db_api/ops.py` (`cmd_rotate_control_credential`)
- parent commit: `4d45fc6`
- kind: docstring

```
R-10 break-glass: recovers from a lost/leaked control-credential
secret without disturbing `credential_id` (audit continuity -- every
prior `control_audit` row naming this id via a future `/control/v1`
endpoint's `actor_id` still refers to the same, still-live credential).
Sets `must_rotate = false` (R-5: "rotate 成功で must_rotate=false" --
the same rule the in-band self-rotate endpoint will apply, WP-3),
matching `credential_store.PostgresControlCredentialStore.rotate`'s own
revoked-refusal (`VALIDATION_FAILED`) -- this break-glass command does
not bypass that: a revoked control credential cannot be rotated back to
life by any path, CLI included.
```

## CH-0313

- moved from: `src/r2db_api/ops.py` (`cmd_rotate_control_credential`)
- parent commit: `4d45fc6`
- kind: comment

```
# Coordinator follow-up (2026-09-04 audit finding §3-A): same
# verbatim-return-value discipline as `cmd_rotate_credential`
# above.
```

## CH-0314

- moved from: `src/r2db_api/ops.py` (`<module>`)
- parent commit: `4d45fc6`
- kind: comment

```
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
```

## CH-0315

- moved from: `src/r2db_api/ops.py` (`_read_audit_writer_roles`)
- parent commit: `4d45fc6`
- kind: docstring

```
D-2(h) point 6: reads and validates the `audit_writer_roles` row
through the SAME `validate_audit_writer_roles_value` function every
read path uses (F-4b). Unlike `cmd_show_declarations` (which must
degrade gracefully so an operator can SEE a broken row), this helper
is used by `cmd_set_platform_timeouts`, which has actual work to do
and nothing sensible to fall back to -- so it `_die`s (exit 2) on a
missing or malformed row.
```

## CH-0316

- moved from: `src/r2db_api/ops.py` (`cmd_declare_surfaces`)
- parent commit: `4d45fc6`
- kind: docstring

```
D-2 (design §3, WP-1 change table C; amendment, q4-f3c-and-
amendments.md): writes the SINGLE `surfaces` row both processes read
at startup (design D-2(c): shared by BOTH, never a per-process value).
`--control-base-url <URL>` is now OPTIONAL (omission = no `control`
row, same as before this amendment); `--no-control` is accepted as an
explicit, equivalent spelling of that same omission (design §3.8 F-6's
own message text tells an operator to re-declare with `--no-control`,
so this command must accept it) -- passing BOTH at once is a usage
error (exit 2, now enforced by argparse's own `add_mutually_exclusive_
group` -- G9, wp12-audit-gaps.md -- rather than a hand-rolled check
here), but neither is REQUIRED any longer.
```

## CH-0317

- moved from: `src/r2db_api/ops.py` (`cmd_declare_surfaces`)
- parent commit: `4d45fc6`
- kind: comment

```
# N-5 (monitor ruling 2026-09-05): `is not None`, never truthiness --
# `--control-base-url ""` must reach `validate_surfaces_value` and hit
# F-5 like every other malformed value, not be silently treated as
# "no control" the way a falsy-but-defined value would be under a bare
# `and` check. Mirrors MitateDB-api's own `is not None` check.
# `--no-control` shares `--control-base-url`'s own dest and stores
# `None`, indistinguishable at this point from plain omission (both
# mean "no control" -- G9, mirrors MitateDB-api's identical `dest=
# "control_base_url"` sharing).
```

## CH-0318

- moved from: `src/r2db_api/ops.py` (`cmd_declare_coalescing_window`)
- parent commit: `4d45fc6`
- kind: docstring

```
D-2 (design §3, WP-1 change table C): writes the `audit_coalescing_
window_ms` row through the SAME validation function (`validate_
coalescing_window_value`, `r2db_api.platform_declarations`) both
composition roots run on READ (design D-2(d): "書き込み時と読み出し時
の両方で行い、両方が同じPythonの検証関数を通る") -- a value this command
itself would reject can never enter the table.
```

## CH-0319

- moved from: `src/r2db_api/ops.py` (`cmd_declare_process_ceilings`)
- parent commit: `4d45fc6`
- kind: docstring

```
Phase 10 WP-6a (design D-5(ii), Q4 D-2 mechanism): writes the
`process_ceilings` row through the SAME validation function
(`validate_process_ceilings_value`, `r2db_api.platform_declarations`)
both composition roots run on READ -- a value this command itself
would reject can never enter the table, and the table (never an env
var -- design D-5(ii) never adds a fallback) is the sole source
`limit_enforcement`'s in-memory-per-process classes are derived from.
```

## CH-0320

- moved from: `src/r2db_api/ops.py` (`<module>`)
- parent commit: `4d45fc6`
- kind: comment

```
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
# to MitateDB-api's own same-named realizations (`_ISOMORPHIC_TARGETS`,
# WP-4 rework round 2, supervisor ruling 2026-09-06, wp4-rework-2.md #1).
# `cmd_verify_declarations` reads its own required env var's NAME through
# `platform_declarations.PROVISION_DSN_ENV` (already a peer-specific-VALUE
# constant defined once in `platform_declarations.py`, the same technique
# `PEER_MODULE`/`MIGRATION_NUMBER`/`CONTROL_PLANE_STATUS_ENV` already use
# elsewhere in this file) rather than embedding the literal env var name
# (`R2DB_CONTROL_DSN` here, `MITATEDB_PROVISION_DSN` on MitateDB-api)
# directly in its own body -- the function's own AST, once its per-peer
# docstring is stripped, therefore carries no peer-specific literal at all
# and normalizes byte-identical to the sibling peer's realization.
# ===========================================================================
```

## CH-0321

- moved from: `src/r2db_api/ops.py` (`<module>`)
- parent commit: `4d45fc6`
- kind: comment

```
#: WP-4 rework (supervisor ruling 2026-09-06, wp4-rework-1.md #2): this was
#: previously inlined into `cmd_verify_declarations` itself, with the
#: trailing "out of scope" line printed AFTER the `try/finally` that this
#: logic lived inside -- every `return` here is a `return` out of that
#: outer `try`, so the finally ran (closing the connection) but the code
#: textually AFTER the finally block never did on any FAIL path. Splitting
#: this into its own function that only ever RETURNS a code (never prints
#: the trailing disclosure line itself) lets `cmd_verify_declarations`
#: print that line exactly once, unconditionally, for every code this
#: returns -- 0 through 12 alike.
```

## CH-0322

- moved from: `src/r2db_api/ops.py` (`_declared_concurrency`)
- parent commit: `4d45fc6`
- kind: docstring

```
Phase 10 WP-4f: this peer's own declared per-role pool ceiling,
consulted by `_verify_declarations_checks`'s own F-16 check.
`ResourceLimits.concurrency` is fixed on this peer -- no env var
overrides it anywhere in this peer's own composition roots -- unlike
MitateDB-api's own same-named `_declared_concurrency` (`MITATEDB_MAX_
CONCURRENCY`, deployer-configurable on that peer; see that peer's own
docstring). Named identically (peer-IDENTICAL name, peer-SPECIFIC
body) so `_verify_declarations_checks`'s own call site stays textually
isomorphic across peers.
```

## CH-0323

- moved from: `src/r2db_api/ops.py` (`_served_capabilities_document`)
- parent commit: `4d45fc6`
- kind: docstring

```
O-7 prep (版フリップ監査, ruling `{scratchpad}/rulings-r3-r7-flip.md`
追補4): extracted out of `_verify_declarations_checks` under this
SAME name on both peers, so that function's own body -- one of the
isomorphism-pinned symbols -- calls this helper with no arguments and
carries no peer-specific complexity of its own (MitateDB's own
equivalent, unlike this one, first has to build a `FoundationConfig`
from `declarations.surfaces` before it can construct its own probe
cell -- that peer-specific difference now lives entirely INSIDE this
helper's own body on each peer, never inside `_verify_declarations_
checks`'s). Previously named `_contract_170_capabilities_document`
(still the name mirrored 1:1 on MitateDB-api before this rework); the
isomorphism table row addition itself is pair-closing work, not done
here (O-7's own instruction: "同型性表への行追加は監督の pair-closing で
行う").

The REAL `DataService.capabilities()` document for a throwaway,
entirely in-memory application/credential -- never a second, hand-
written copy of what `service.py` is expected to declare (WP-2e
rework, audit-wp2e.md D-2, ruling L-2 = (A)): this exercises the SAME
production code path a real client's `GET /v1/capabilities` reaches,
so a future regression that stops declaring one of the contract 1.7.0
capabilities `enabled` is caught here too, not only by `r2db_api.
service`'s own unit tests. No network/PostgreSQL connection is
involved -- `DataService`/`CredentialStore`/`ControlAuthority` are
pure in-process objects.
```

## CH-0324

- moved from: `src/r2db_api/ops.py` (`<module>`)
- parent commit: `4d45fc6`
- kind: comment

```
# ===========================================================================
# Q4 phase WP-3 (design docs/design/Q4_DB_SIDE_SINGLE_TRUTH_V1.md D-4/D-5,
# work order docs/work-orders/WORK_ORDER_Q4_DB_SIDE_SINGLE_TRUTH_V1.md WP-3
# change table E): bulk-apply/visualize each application's own
# per-application platform-upgrade ledger. Both subcommands run entirely
# against the PROVISION DSN (`R2DB_CONTROL_DSN`) -- the running API process
# never holds this credential (SI-02) -- and neither one changes `list-
# apps`' own resource/shape (design D-5, work order constraint 17).
# ===========================================================================
```

## CH-0325

- moved from: `src/r2db_api/ops.py` (`_registry_applications_for_upgrade`)
- parent commit: `4d45fc6`
- kind: docstring

```
Design D-4(a): the default target set is EVERY registered
application with a real database (`database_name IS NOT NULL`,
`enabled` is NOT a filter here -- "`enabled`は対象選択に影響しない",
a disabled application's own DB is still brought up to date). When
`--application <id>` names one explicitly, that row is returned
regardless of its own `database_name` -- a registered-but-never-
provisioned application is reported as a SKIP (design D-4(d)'s own
"database_nameがNULL" skip reason), not a silent non-match, only when
an operator asked for it by name specifically.
```

## CH-0326

- moved from: `src/r2db_api/ops.py` (`_run_upgrade_script`)
- parent commit: `4d45fc6`
- kind: docstring

```
Call shape ONLY copied from MitateDB-api's own `_run_deprovision_
script` (design D-4(b)) -- the psql `-v` variable name is r2db's own
(`platform_upgrades.UPGRADE_SCRIPT_VARIABLE`, `app_slug`; MitateDB's
own realization uses `app_id` instead, design §3.10's own peer-pair
table). Never `_die`s on a non-zero exit -- the caller decides how one
application's own failure affects the rest of the run (D-4(c)).
```

### correction: 2026-09-22

- reason: work order `docs/work-orders/WORK_ORDER_R66_DEPLOY_0013_AND_PROVISION_ROLE_TIMEOUT_V1.md` WP-2 (design D-7) -- `_run_upgrade_script` gained a required `lock_timeout` parameter (peer-isomorphic with `MitateDB-api/src/mitatedb_api/ops.py::_run_upgrade_script`), so the docstring now names how it is applied

old:
```
Call shape ONLY copied from MitateDB-api's own `_run_deprovision_script` (design D-4(b)) -- the psql `-v` variable name is r2db's own (`platform_upgrades.UPGRADE_SCRIPT_VARIABLE`, `app_slug`; MitateDB's own realization uses `app_id` instead, design §3.10's own peer-pair table). Never `_die`s on a non-zero exit -- the caller decides how one application's own failure affects the rest of the run
```

new:
```
Call shape ONLY copied from MitateDB-api's own `_run_deprovision_script` (design D-4(b)) -- the psql `-v` variable name is r2db's own (`platform_upgrades.UPGRADE_SCRIPT_VARIABLE`, `app_slug`; MitateDB's own realization uses `app_id` instead, design §3.10's own peer-pair table). Never `_die`s on a non-zero exit -- the caller decides how one application's own failure affects the rest of the run. `lock_timeout` (design D-7) is appended to the psql session's own `PGOPTIONS` via `_with_lock_timeout_option`, on top of whatever `_psql_connection_env` already placed there from the DSN itself
```

## CH-0327

- moved from: `src/r2db_api/ops.py` (`_print_upgrade_result`)
- parent commit: `4d45fc6`
- kind: comment

```
# M-1 fix (supervisor ruling 2026-09-05): only reachable via an
# explicit `--application <id>` naming a registered-but-never-
# provisioned application (the default enumeration already
# excludes these rows entirely, design D-4(a)). Worded as a
# FAILURE, not a benign skip -- D-4(e)'s own exit-code table
# groups this with a real `psql` failure under exit code `3`
# (a real, non-dry-run invocation only; `result.failed` is left
# empty for `--dry-run`, see `cmd_upgrade_applications`).
```

## CH-0328

- moved from: `src/r2db_api/ops.py` (`_print_upgrade_result`)
- parent commit: `4d45fc6`
- kind: comment

```
# M-3 (supervisor ruling 2026-09-05, review): the failed psql
# invocation's own stderr tail, folded into THIS application's
# own output block -- printed before the `REVOKE` cleanup line
# below (diagnosis before remedy).
```

## CH-0329

- moved from: `src/r2db_api/ops.py` (`cmd_upgrade_applications`)
- parent commit: `4d45fc6`
- kind: docstring

```
Design D-4: bulk-applies every per-application upgrade script this
package knows about (`platform_upgrades.PLATFORM_UPGRADE_NUMBERS`) to
every application named (default: every registered, provisioned
application) whose own ledger is missing it -- ascending number order,
one `psql` subprocess invocation per (application, number) pair.

`--script <NNNN>` narrows to exactly ONE number: an application whose
own ledger already records it is reported `recorded, skipped` (and
counted a SUCCESS, design D-4(a): "台帳に記録済みのDBでは`recorded,
skipped`と出力し、当該DBは成功扱いとする") rather than re-run.

`--dry-run` runs nothing at all -- it reports the exact same `applied`/
`pending` set `upgrade-status` would (D-4(a)), ignoring `--script`
entirely (there is nothing to apply, so narrowing which script would
be applied has no effect on a report that applies none of them).

Never stops at the first application-level failure (D-4(c): "1つの
DBの失敗で止めず全DBを回し、失敗したDBを列挙して非0で終わる") -- a
`psql` non-zero exit for one (application, number) pair is recorded as
that application's own `failed` entry (with the D-4(c) `REVOKE`
clean-up line, since a mid-script failure leaves this run's own
temporary developer-role membership standing on the provision role --
the failed script's own `REVOKE :"developer_role" FROM CURRENT_USER`
line, positioned after `COMMIT`/the failure point, never runs), and the
loop moves on to the NEXT number/application rather than aborting.
```

## CH-0330

- moved from: `src/r2db_api/ops.py` (`cmd_upgrade_applications`)
- parent commit: `4d45fc6`
- kind: comment

```
# Design D-4(a)/(d)/(e) fix (supervisor ruling 2026-09-05,
# M-1): reachable only via an explicit `--application <id>`
# naming a registered-but-never-provisioned application.
# `pending_after` is always every number this package
# requires (nothing could possibly have been applied to a
# database that does not exist) -- this alone is what makes
# `--dry-run` return `4` here (D-5: "database_nameがNULLの
# 場合はappliedを[]とする").
#
# `failed` is populated the SAME way -- but ONLY for a real
# (non-dry-run) invocation. D-4(e)'s own exit-code table
# names `database_name`がNULL explicitly as ONE of the two
# conditions exit code `3` covers ("psql exit 3、または
# `database_name`がNULL"); populating `failed` is what makes
# `summarize_upgrade_run` below -- UNMODIFIED, still the exact
# same pinned pure function -- return `3` for this case on
# its own, with no special-casing needed at this call site
# (the prior form filtered these rows OUT before calling it,
# which is why this case silently returned `0`, review M-1).
# A `--dry-run` never "fails" anything (nothing is attempted),
# so `failed` stays empty there -- `pending_after` alone
# already drives that path's own `4`.
```

## CH-0331

- moved from: `src/r2db_api/ops.py` (`cmd_upgrade_applications`)
- parent commit: `4d45fc6`
- kind: comment

```
# M-3 (supervisor ruling 2026-09-05, review; tail source
# unified with MitateDB-api's own `_run_upgrade_script`
# by supervisor ruling U-7, 2026-09-05 差し戻し後 delta
# 監査): a failed psql invocation's own stdout+stderr is
# the ONLY place the actual PostgreSQL error text lives
# -- before this fix `_run_upgrade_script`'s own
# `CompletedProcess` was discarded except for
# `.returncode`, so an operator staring at "failed=[N]"
# had no way to learn WHY short of re-running the script
# by hand. Both streams are joined (`psql`'s own
# `ON_ERROR_STOP=1` failure text can land on either,
# depending on the failing statement) before taking the
# tail (last ~20 lines), folded into this application's
# own output block below (`_print_upgrade_result`), not
# the full capture -- an unbounded dump would risk
# burying the per-application summary line under an
# unrelated wall of output for a script that fails early
# with a long preamble already printed.
```

## CH-0332

- moved from: `src/r2db_api/ops.py` (`cmd_upgrade_applications`)
- parent commit: `4d45fc6`
- kind: comment

```
# L-... output-format unification (supervisor ruling 2026-09-05,
# 裁定 9), counting rule fixed by supervisor ruling U-1 (2026-09-05,
# 差し戻し後 delta 監査): same trailing tally SHAPE as MitateDB-api's
# own `_print_upgrade_results` ("N succeeded, N failed, N skipped
# (...)"), and the SAME counting rule -- each application lands in
# EXACTLY one bucket. `failed` always wins first -- this INCLUDES the
# `database_name is None` case above (M-1) even under `--dry-run`,
# where `result.failed` itself is deliberately left empty (so
# `summarize_upgrade_run`'s own exit code stays `4`, never `3`, for a
# dry run); the tally line is a separate, purely descriptive surface,
# so it counts a never-provisioned application as failed regardless.
# Otherwise, an application whose own `applied_after` came back
# identical to its own `applied_before` actually applied NOTHING this
# run (either nothing was pending at all, or `--script` named a
# number this application's own ledger already recorded) -- that is
# "skipped" (未適用なし、既に記録済み), never "succeeded" (which
# requires having actually run and applied at least one upgrade). The
# prior form instead used `result.skipped` (populated ONLY by the
# `--script`-already-recorded path, never by "nothing was pending to
# begin with") to decide `skipped_count`, which is why a
# fully-caught-up application in a bulk (non-`--script`) run was
# silently counted "succeeded" despite having applied nothing.
```

## CH-0333

- moved from: `src/r2db_api/ops.py` (`cmd_upgrade_applications`)
- parent commit: `4d45fc6`
- kind: comment

```
# M-1 fix: `results` is passed WHOLE -- a `database_name is None`
# row's own populated `failed` (non-dry-run only) is what makes this
# UNMODIFIED, still-pinned pure function return `3` on its own;
# filtering these rows out before this call (the prior form) is
# exactly why the condition was previously invisible to this exit
# code (review M-1).
```

## CH-0334

- moved from: `src/r2db_api/ops.py` (`cmd_upgrade_status`)
- parent commit: `4d45fc6`
- kind: docstring

```
Design D-5: `applied`/`pending`/`database_name` for every targeted
application, provision-DSN-only -- never touches `list-apps`' own
resource or shape (design D-5's own reason: this CLI cannot add a
column to a contract-shaped `ApplicationsResult` without a contract
change, U-1). An application with no ledger table at all reports
`applied=[]` (design D-5's own "台帳が無いapplicationはapplied=[]と
する").
```

## CH-0335

- moved from: `src/r2db_api/ops.py` (`_build_parser`)
- parent commit: `4d45fc6`
- kind: comment

```
# G9 (wp12-audit-gaps.md, structural-symmetry-only ruling -- this row
# is outside the isomorphism table): mirrors MitateDB-api's own
# `add_mutually_exclusive_group` + `store_const` shape -- `--no-
# control` shares `--control-base-url`'s OWN dest and argparse itself
# rejects passing both (SystemExit(2)), rather than a hand-rolled
# `args.no_control and args.control_base_url is not None: _die(...)`
# check in `cmd_declare_surfaces` below. `--control-base-url ""` still
# stores the empty string (distinct from `--no-control`'s `None`), so
# F-5 still fires on it (N-5 below is unaffected).
```
