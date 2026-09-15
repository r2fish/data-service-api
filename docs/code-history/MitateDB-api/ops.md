# src/mitatedb_api/ops.py -- code-comment history (change set 5)

Companion for `src/mitatedb_api/ops.py` per `docs/code-history/README.md`.

## CH-0408

- moved from: `src/mitatedb_api/ops.py` (`<module>`)
- parent commit: `3adba35`
- kind: docstring

```
MitateDB-api out-of-band control-plane ceremony CLI: ``python -m
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
```

## CH-0411

- moved from: `src/mitatedb_api/ops.py` (`_print_secret_once`)
- parent commit: `3adba35`
- kind: comment

```
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
```

## CH-0413

- moved from: `src/mitatedb_api/ops.py` (`_actor_credential`)
- parent commit: `3adba35`
- kind: docstring

```
The operator's own currently-live control credential -- stands in
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
the credential_id the store actually authenticates against.
```

## CH-0414

- moved from: `src/mitatedb_api/ops.py` (`cmd_revoke_credential`)
- parent commit: `3adba35`
- kind: docstring

```
`ControlPlaneService.revoke_credential`'s own built-in declare-and-
echo gate fires only when the target is the LAST remaining active
control credential (design R-6) -- an application credential's
revocation is never gated (contract `non_destructive_requests`) and
this call simply succeeds. `destructive=True` unconditionally: running
this CLI command at all already is the destructive-intent signal
(identical reasoning to `cmd_reset` above), `--confirm` supplies
`confirmation` (`None` if omitted, which never matches a real phrase).
```

## CH-0415

- moved from: `src/mitatedb_api/ops.py` (`cmd_audit_report`)
- parent commit: `3adba35`
- kind: docstring

```
R-9 lockout/compromise playbook helper: prints every durable
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
or used here at all.
```

## CH-0416

- moved from: `src/mitatedb_api/ops.py` (`cmd_deprovision`)
- parent commit: `3adba35`
- kind: docstring

```
This module's own second genuinely destructive subcommand (alongside
`reset`) -- see this module's own docstring for why this is not a
`ControlPlaneService` call at all, and for the fingerprinted phrase's
own rationale. `application_id` is format-validated BEFORE any database
access or phrase computation (mirrors r2db-api's own `delete-credential`
MA-1 fix: an unvalidated identifier must never reach a confirmation
phrase or a shell-adjacent subprocess argument).
```

## CH-0417

- moved from: `src/mitatedb_api/ops.py` (`cmd_issue_audit_credential`)
- parent commit: `3adba35`
- kind: docstring

```
Phase 3.5 WP-5 (§4/§1-D, P35-D12): issues a new `role="audit"`
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
```

## CH-0419

- moved from: `src/mitatedb_api/ops.py` (`_read_audit_writer_roles`)
- parent commit: `3adba35`
- kind: docstring

```
D-2(h) 4: the target of `set-platform-timeouts` comes from the
`audit_writer_roles` row itself -- never a role-name argument, never a
naming-convention derivation from `current_user`/schema. Raw read +
the SAME `validate_audit_writer_roles_value` the read/write paths use
(design D-2(h) 6: "行の検証は...同じ関数を通る").
```

## CH-0420

- moved from: `src/mitatedb_api/ops.py` (`_read_audit_writer_roles_lenient`)
- parent commit: `3adba35`
- kind: docstring

```
`show-declarations`'s own lenient variant of `_read_audit_writer_
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
applies uniformly.
```

## CH-0421

- moved from: `src/mitatedb_api/ops.py` (`cmd_declare_surfaces`)
- parent commit: `3adba35`
- kind: docstring

```
D-2(c)/(d): writes the single `surfaces` row both processes read --
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
通る").
```

## CH-0422

- moved from: `src/mitatedb_api/ops.py` (`cmd_declare_process_ceilings`)
- parent commit: `3adba35`
- kind: docstring

```
Phase 10 WP-6b (design D-5 (ii)): writes the single `process_
ceilings` row both processes read -- REPLACES the entire row, same
convention as `cmd_declare_surfaces`. Validated through the SAME
function (`platform_declarations.validate_process_ceilings_value`)
the read path uses (D-2(d)'s own regularity, applied to this new
key).
```

## CH-0428

- moved from: `src/mitatedb_api/ops.py` (`_registry_applications_for_upgrade`)
- parent commit: `3adba35`
- kind: docstring

```
Design D-4(a): the DEFAULT target set (`application_id is None`) is
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
by `application_id` for deterministic output.
```

## CH-0429

- moved from: `src/mitatedb_api/ops.py` (`_run_upgrade_script`)
- parent commit: `3adba35`
- kind: docstring

```
Design D-4(b): the `psql` subprocess call shape this peer newly
carries (`MitateDB-api/src/mitatedb_api/ops.py::_run_deprovision_
script`'s own call shape, followed here -- never `_die`, which would
exit immediately and stop this command from reaching the REST of the
applications it must still visit, design D-4(c)/禁止事項 16).

Connects with the PLATFORM `provision_dsn` -- never the app-database-
swapped `_app_dsn` (that swap is for the PYTHON-side ledger reads
only, `_upgrade_one_application`'s own `read_applied_upgrade_numbers`
calls). Every per-application upgrade script (`0006`/`0008`, design
§1.5 の 5) starts by resolving `database_name` from `mitatedb_
registry.applications` and then `\c`-ing to it itself -- exactly the
same shape `_run_deprovision_script` already follows for `0004`,
which also expects to start out connected to the PLATFORM database.
```

## CH-0431

- moved from: `src/mitatedb_api/ops.py` (`_upgrade_one_application`)
- parent commit: `3adba35`
- kind: comment

```
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
```

## CH-0432

- moved from: `src/mitatedb_api/ops.py` (`_print_upgrade_results`)
- parent commit: `3adba35`
- kind: docstring

```
Design D-4(d): one line per application (`applied_before` ->
`applied_after` / `pending`), a separate `skipped` block (design
D-4(d): "psql の `\q` skip は exit 0 で返り成功と区別できないため、
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
counted "succeeded" despite having applied nothing.
```

## CH-0433

- moved from: `src/mitatedb_api/ops.py` (`_print_upgrade_results`)
- parent commit: `3adba35`
- kind: comment

```
# M-3 (supervisor ruling 2026-09-05, review): psql's own
# stderr tail, folded into THIS application's own output
# block, before the cleanup line (diagnosis before
# remedy) -- see `_upgrade_one_application`'s own comment
# for why only the tail.
```

## CH-0434

- moved from: `src/mitatedb_api/ops.py` (`cmd_upgrade_applications`)
- parent commit: `3adba35`
- kind: docstring

```
Design D-4: bulk-applies every pending per-application upgrade
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
only -- never a control credential (SI-02).
```

## CH-0435

- moved from: `src/mitatedb_api/ops.py` (`cmd_upgrade_applications`)
- parent commit: `3adba35`
- kind: comment

```
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
```

## CH-0436

- moved from: `src/mitatedb_api/ops.py` (`cmd_upgrade_status`)
- parent commit: `3adba35`
- kind: docstring

```
Design D-5: read-only equivalent of `upgrade-applications
--dry-run` -- provision DSN only, `applied`/`pending`/`database_name`
per application. Never touches the existing `list-applications`
command (design D-5: contract shape `ApplicationsResult` unchanged) --
this is an entirely separate, peer-local-only surface (U-1).
```

## CH-0437

- moved from: `src/mitatedb_api/ops.py` (`cmd_upgrade_status`)
- parent commit: `3adba35`
- kind: comment

```
# M-2(d) fix (supervisor ruling 2026-09-05): a REGISTERED but
# never-provisioned application, reachable only via an
# explicit `--application <id>` (the default enumeration
# already excludes these rows entirely) -- reported as
# `applied=[]`/every number pending (design D-5: "台帳が無い
# applicationはapplied=[]とする", the SAME treatment as no
# ledger table at all), never a crash from `_app_dsn(...,
# None)` (a `None` `dbname` is not a valid connection param).
```

## CH-0438

- moved from: `src/mitatedb_api/ops.py` (`_build_parser`)
- parent commit: `3adba35`
- kind: comment

```
# ---- Q4 phase declaration-management command family (design D-1/D-2)
# -- provision DSN only, no control credential needed for any of these
# (`MITATEDB_PROVISION_DSN`, the same env var `deprovision`/`audit-
# report` above already require).
```

## CH-0439

- moved from: `src/mitatedb_api/ops.py` (`_build_parser`)
- parent commit: `3adba35`
- kind: comment

```
# ---- Q4 phase per-application platform-upgrade command family
# (design D-4/D-5) -- provision DSN only, same as the declaration
# family above.
```
