# Security Invariant Control Mapping

Status: **Implementation mapping template**

Version: **2.17** (2026-09-21; R-70 -- SI-09's MitateDB-api `platform upgrade` named block, one Control claim corrected in place, no claim moved between blocks: the Platform-upgrade runbook claim said the remediation stage is gated `instead` by the isolated proof, the independent audit and the requester's approval, which could be read as those three conditions applying to the remediation stage only -- weaker than the runbook (`MitateDB-api/docs/cloud-run-cloud-sql.md` section 10), which requires all three before anything in stage 2 or stage 4 runs against production; the claim now says the three conditions come before both state-changing stages and that Gate-0 ready, which gates the candidate stage, does not gate the remediation stage. No new invariant or control. The superseded line verbatim in `CONTROL_MAPPING_HISTORY.md`'s SI-09 section. -- docs/design/ROADMAP_POST_PHASE7_V1.md R-70)

This document maps common Security Invariants to platform-specific controls. It is intentionally not the source of truth for the invariants themselves.

Each claim is one bullet under its invariant, subsection (r2db-api / MitateDB-api / Common), block (the subsection's default block, or a named one written `### <subsection> -- <topic>`) and axis (Control / Evidence / Status); `- —` marks an axis with no claim.

**Update convention** (phase 7 WP-7 (i), requester ruling 4 --
`docs/design/PHASE7_EVIDENCE_REPRODUCIBILITY_AND_PUBLICATION_V1.md` §5):
「訂正は現行行を書き換え、旧文は履歴へ移す」-- a correction rewrites the
current claim below in place, and the superseded text it replaces is moved,
verbatim and unedited, into the per-ID companion file
`CONTROL_MAPPING_HISTORY.md` (headings there are the bare ID only, e.g.
`## SI-14`, so a section's own `[history](CONTROL_MAPPING_HISTORY.md#si-14)`
link resolves to a real GitHub anchor). Each section keeps only today's control
and its evidence -- test names, `file:line`, and any disclosed scope limits
-- plus that one link; it is not a place to re-accumulate the next
correction's own narrative. This file holds no `|`-started table
(`conformance-tests/test_control_mapping_register.py` parses on that
assumption); do not add one, and keep every claim as one bullet on one
line (no embedded newline inside a claim).

**Length cap measurement** (差し戻し rework round 3, 監督裁定 2026-09-06 item
C-1/B-2; re-measured 2026-09-21, R-70): this file's longest block is
SI-09's MitateDB-api `platform upgrade` block, 12,681 characters (2,519 left under the cap).
`conformance-tests/test_control_mapping_register.py`'s `MAX_BLOCK_LENGTH = 15200`
is the 2026-09-06 measurement of SI-14's r2db-api subsection (15,065 characters, the figure
that file's own comment records) plus a 135-char margin, unchanged, set independently
of `conformance-tests/CONDITIONS.md`'s own cap (per C-1: a shared cap left that
file's own guard nearly inert; design section 13/WP-8 keeps its own copy). A block is one subsection's default block or one of its named blocks, that block's claims joined by single spaces. Each physical line is also capped at `MAX_LINE_LENGTH = 1400`. 【訂正註 2026-09-21 (R-65)】 Until version 2.16 this paragraph carried a dated measurement that no later split had updated; the text replaced here read, verbatim apart from line breaks: "re-measured 2026-09-10, WP-9): this file's longest (SI, subsection) block is still SI-14's r2db-api block, now 15,122 characters (15,065 on 2026-09-06, the figure `conformance-tests/test_control_mapping_register.py`'s own comment records). Its `MAX_BLOCK_LENGTH = 15200` is that 2026-09-06 measurement plus a 135-char margin, unchanged (78 left today), set independently".

**Blocks per subsection** (R-50, requester ruling 2026-09-18 --
`docs/design/CONTROL_MAPPING_MULTI_BLOCK_V0_1.md`): a subsection may hold more
than one block. Each `### ` heading inside an invariant section is either that
subsection's default block (`### MitateDB-api`) or one of its named blocks
(`### MitateDB-api -- ops inventory`; the topic is English and unique within
the subsection). The default block is mandatory, appears exactly once and comes
first; a subsection may add at most 3 named blocks (`MAX_NAMED_SUBBLOCKS = 3`
in `conformance-tests/test_control_mapping_register.py`, raised only by a
supervisor ruling). A subsection's blocks stand together, the subsection order
(r2db-api, MitateDB-api, Common) is unchanged, and every block holds the same 3
axes in the same order (`- —` for an axis with no claim). Moving claims between
blocks of the SAME subsection changes no character of any claim, so it is not a
correction and moves nothing into `CONTROL_MAPPING_HISTORY.md`. Other documents
point at a named block as `SI-08 / MitateDB-api / ops inventory / Evidence`,
and at a default block as `SI-08 / MitateDB-api / Evidence`. Re-measured
2026-09-19 (version 2.11, after R-59 split SI-09's `MitateDB-api`
subsection): the longest block is `SI-14`'s `r2db-api` `default block`
again, unchanged at the `12,624` characters version 2.8 measured after
the first split and the SI-09 -> SI-08 move (`2,576` left), ahead of
`SI-08`'s `MitateDB-api` `default block` at `11,858` (`3,342` left);
SI-09's `MitateDB-api` `platform upgrade` block is `9,616` characters
and its `default block` is `4,612` (`10,588` left, against the `14,229`
and `971` version 2.10 measured), and the 15,122-character figure above
describes the file before the first split. Re-measured 2026-09-20 (version
2.12, after R-56 added claims to both of SI-08's own default blocks):
the longest block is now `SI-08`'s `MitateDB-api` `default block` at
`13,023` characters (`2,177` left), ahead of `SI-08`'s `r2db-api`
`default block` at `12,928` (`2,272` left) and `SI-14`'s `r2db-api`
`default block`, unchanged at `12,624`; `SI-08`'s `MitateDB-api`
subsection already carries one named block (`ops inventory`, `8,349`),
leaving 2 of `MAX_NAMED_SUBBLOCKS`' 3 named slots free there and 3 free
in `SI-08`'s `r2db-api` subsection, should either default block need a
split later. Re-measured 2026-09-20 (version 2.13, after R-57 WP-1's own
run-acceptance additions to SI-09's `MitateDB-api` `platform upgrade`
block, plus this same WP-3's rework of its runbook-acceptance Evidence
and Status claims): that block is now `12,200` characters (`3,000` left,
against the `9,616` version 2.11 measured, `11,945` before the rework);
SI-08's `MitateDB-api` `ops inventory` named block, touched only by a
test-name correction, is now `8,335` (`14` fewer than the `8,349`
version 2.12 measured, the length of the old test name minus the new
one); the longest block stays `SI-08`'s `MitateDB-api` `default block`
at `13,023`, unchanged this change set. Re-measured 2026-09-20 (version
2.14, after R-60/R-61 corrected two Control claims in SI-09's
`MitateDB-api` `platform upgrade` block in place and moved nothing):
that block is now `12,516` characters (`2,684` left, against the
`12,200` version 2.13 measured); the longest block stays `SI-08`'s
`MitateDB-api` `default block` at `13,023`, unchanged this change set.
Re-measured 2026-09-21 (version 2.15, after R-62 corrected one Control
claim in `SI-08`'s `r2db-api` `default block` in place, split it into
two claims and moved nothing): that block is now `14,105` characters
(`1,095` left, against the `12,928` version 2.12 measured) and is the
longest block, ahead of `SI-08`'s `MitateDB-api` `default block` at
`13,023`, unchanged this change set; splitting `SI-08`'s default
blocks is ledger item R-65.
Re-measured 2026-09-21 (version 2.16, after R-65 split both of `SI-08`'s
default blocks): `SI-08`'s `r2db-api` `default block` is now `7,682` and its
`capacity and concurrency` block `6,422`; `SI-08`'s `MitateDB-api`
`default block` is `5,555`, its `ops inventory` block `8,335` and its
`capacity and concurrency` block `7,467`; the longest block is `SI-14`'s
`r2db-api` `default block` again, unchanged at `12,624` (`2,576` left).
Re-measured 2026-09-21 (version 2.17, after R-70 corrected one Control
claim in `SI-09`'s `MitateDB-api` `platform upgrade` block in place and
moved nothing): that block is now `12,681` characters (`2,519` left; version
2.16 left that block at `12,533` characters) and is the longest block, ahead of
`SI-14`'s `r2db-api` `default block` at `12,624`, unchanged this change set.

**【訂正 2026-09-18 (R-50, version 2.7)】** The two sentences rewritten in place
above each described a block as one whole subsection, which is false once a
subsection holds several blocks. The superseded text is kept here verbatim --
not in `CONTROL_MAPPING_HISTORY.md`, whose headings are bare invariant IDs and
hold no place for this preamble: (1) "Each claim is one bullet under its
invariant, subsection (r2db-api / MitateDB-api / Common) and axis (Control /
Evidence / Status); `- —` marks an axis with no claim." (2) "A block is one
subsection's claims (r2db-api, MitateDB-api or Common) joined by single
spaces."

## SI-00 Single-Compromise Containment

[history](CONTROL_MAPPING_HISTORY.md#si-00)

### r2db-api

#### Control

- `authority-topology.yaml` provides a deny-by-default plane skeleton, verified by negative reachability tests (`test_topology.py`).
- Per-application database isolation is structural, PostgreSQL-enforced (migrations 0001-0004): `0003_provision_application.sql` creates each application's DB from `template0`, `REVOKE CONNECT ... FROM PUBLIC`, grants `CONNECT` only to that application's 2 dedicated roles -- crossing is impossible without FDW/dblink, not merely grant discipline;
- RLS is retained as defence-in-depth (SI-01/02/03) -- `test_cross_database_connect_is_refused_at_the_database_level`.
- CCR-14 adds a co-located control-plane HTTP process with 3 checked isolation points: (a) structurally separate credential stores/tables, distinct HMAC peppers required to differ at startup -- `test_cross_store_leakage_secret_added_to_one_store_never_authenticates_the_other`, `test_validate_control_pepper_separation_rejects_equal_peppers`;
- (b) distinct login roles -- `r2dbsvc_api` has no grant on `control_credentials`/`control_audit` and only `INSERT` on `application_audit` (no SELECT/UPDATE/DELETE);
- a third SELECT-only `r2dbsvc_auditreader` role reads both audit tables -- `test_controlplane_role_grants_match_the_design`, `test_auditreader_role_can_select_both_audit_tables_and_nothing_else`;
- (c) `AuthorityTopology` registers the control-plane HTTP process as its own node with a structural unreachability check -- `test_control_plane_http_reaches_only_control_and_audit`.
- A data-plane host declaring `control_plane: enabled` with no control-credential store fails `AUTH_INVALID` for any control/audit credential on its `/v1/audit/query` alias -- separation working as designed (contract's `audit_query` obligation binds the control surface's own endpoint, not this alias; also recorded on SI-14).
- **Realization**: the data-plane composition root neither constructs nor imports the control-credential store, pinned by an AST-based check (parses `main.py`'s `Import`/`ImportFrom`/`Name`/`Attribute` nodes, not substring match) -- `test_data_plane_composition_root_does_not_import_the_control_credential_store`;
- resulting wire behavior is exactly what the contract permits: `AUTH_INVALID` because no verifier exists at all, never `CAPABILITY_UNSUPPORTED`/`FORBIDDEN`/5xx (all non-conforming).
- **Deprovision in front of live connections (R-54, design `docs/design/DEPROVISION_FORCED_DROP_V0_1.md` v1.0 D-1/D-2R)**: `0004_deprovision_application.sql` closes out an application's own live backends while taking no cluster-wide privilege at all -- no `GRANT` of a predefined role (`pg_signal_backend`, `pg_read_all_stats` or any other) appears anywhere in this peer's migration set, in which `pg_signal_backend` occurs only inside comments and `pg_read_all_stats` does not occur at all; the executing role `r2dbsvc_control` is `NOSUPERUSER` (`0001_bootstrap_control_plane.sql`); and no operator grant is a precondition of the script.
- The whole authority its new stages use is a temporary `GRANT <role> TO CURRENT_USER WITH INHERIT TRUE, SET FALSE` (`r2db-api/migrations/0004_deprovision_application.sql`:140-150) over that one application's own two roles, which `r2dbsvc_control` created itself during `0003` and therefore already holds ADMIN OPTION on -- `r2db-api/tests/test_postgres.py::test_deprovision_succeeds_in_a_single_pass_with_a_live_runtime_role_connection` (a runtime-role connection held open across one un-retried run), `::test_0004_temporary_grant_uses_inherit_true_set_false`.
- That grant is reached only through a pre-check (`0004`:102-113) that refuses the whole run, before anything at all is changed, when that database holds a connection under any role other than the application's own runtime/developer role and the executing role; background workers (`usesysid IS NULL`) are deliberately not counted, and the refusal message names no role. Reading `pg_stat_activity`'s own `usename`/`usesysid` for this needs no `pg_read_all_stats` membership (design H-2) -- `::test_deprovision_pre_check_stops_and_changes_nothing_for_an_unrelated_connected_role` holds an unrelated LOGIN role's connection open and asserts the database, its `datallowconn`, the executing role's own `inherit_option = true` membership count and the registry row are all exactly as they were.
- A failure leaves a bounded residue, not a wider authority (design §4.1): a run stopping at or after `ALTER DATABASE ... WITH ALLOW_CONNECTIONS false` (`0004`:164-168) leaves that one database non-connectable with the temporary membership still standing -- availability lost for that application, not privilege gained, because the membership covers only that application's own two roles, carries `SET FALSE` (no `SET ROLE`), and sits on a role that already holds ADMIN OPTION over them, so `r2dbsvc_control` undoes it alone with `REVOKE <role> FROM CURRENT_USER` and needs no other role to do so; re-running `0004` clears both and completes -- `::test_deprovision_completes_on_rerun_after_the_database_was_already_dropped`, with the operator's own recovery written out in `r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md` §5 and §14.

#### Evidence

- —

#### Status

- **Acceptance boundary**: r2db Stage 1, contract 1.6.0, was installed on the VPS on 2026-09-05 -- migrations 0001, 0002, 0005, 0006, 0007 and 0003 were applied in that order (0004 is the deprovision script and is never applied at install), `pg_hba`/`pg_ident` posture B was configured, and external reachability on port 8443 was verified (`docs/work-orders/DEPLOY_PHASE6_20260904.md` §8, items 9-12);
- no later contract version has been deployed to that VPS since, and no production credential-store/role/grant listing beyond the runbook's own steps is recorded -- this row's own containment checks (a)-(c) remain unexercised against that instance.
- **R-54 evidence boundary**: the four deprovision claims above were measured only against throwaway local PostgreSQL 16 clusters, by the 6 tests this change set adds to `r2db-api/tests/test_postgres.py` (:377, :398, :424, :469, :530, :546), each pinned by a mutation of its own stage (design §6.1's one-condition-one-test rule; 6 mutations on this peer, all red);
- production evidence is `absent` -- `0004` is still never applied at install (this block's own acceptance boundary above), nothing was applied to the VPS for R-54, and whether `ALTER DATABASE ... WITH ALLOW_CONNECTIONS false` and `GRANT ... WITH INHERIT TRUE, SET FALSE` behave the same on a managed platform is unexercised; the place that reading is to be taken is `MitateDB-api/docs/cloud-run-cloud-sql.md` §9 item 3 (design §7).

### MitateDB-api

#### Control

- Control-plane/data-plane separation (design R-4/R-6): (a) structurally separate credential tables (`credentials` vs. `control_credentials`), distinct HMAC peppers required to differ at startup -- `test_pepper_separation_detects_the_two_env_vars_configured_identically`.
- (b) two disjoint least-privilege PostgreSQL roles, verified with bare `psycopg` connections -- `test_application_plane_role_has_no_privilege_on_control_credentials`.
- `mitatedbsvc_api` additionally holds only `INSERT` on `application_audit` (no SELECT/UPDATE/DELETE);
- `mitatedbsvc_controlplane` gets nothing on it;
- a third SELECT-only reader role `mitatedbsvc_auditreader` reads both audit tables -- `test_auditreader_role_can_select_both_audit_tables_and_nothing_else`.
- Contract 1.4.0's `audit_query` obligation binds the control surface's own endpoint, not the data host's alias (this peer's data service declares `control_plane` enabled while holding no control-credential store, so that alias answers `AUTH_INVALID`; also on SI-00's r2db column).
- (c) `mitatedbsvc_provision` (CREATEDB/CREATEROLE) is held only by operator/deploy tooling and the out-of-band CLI, never by either process.
- **Realization**: structurally identical to r2db-api -- the data-plane composition root neither imports the control-credential store, pinned by an AST check on identifiers, not string literals -- `test_data_plane_composition_root_does_not_import_the_control_credential_store`.
- **Deprovision in front of live connections (R-54, design `docs/design/DEPROVISION_FORCED_DROP_V0_1.md` v1.0 D-1/D-2R)**: this peer reaches the same safety outcome as the r2db-api block above, with `mitatedbsvc_provision` (`NOSUPERUSER`, `0001_bootstrap_platform.sql`) as the executing role -- no `GRANT` of a predefined role appears anywhere in this peer's migration set either (`pg_signal_backend` occurs in it only inside comments), and the only added authority is the temporary `GRANT <role> TO CURRENT_USER WITH INHERIT TRUE, SET FALSE` over that application's own two roles (`MitateDB-api/migrations/0004_deprovision_application.sql`:134-144), roles `mitatedbsvc_provision` created itself during `0003` -- `MitateDB-api/tests/test_postgres.py::test_deprovision_succeeds_in_a_single_pass_with_a_live_runtime_role_connection`, `::test_0004_temporary_grant_uses_inherit_true_set_false`.
- The per-membership `INHERIT TRUE` is what makes that grant effective at all here: `mitatedbsvc_provision` is `NOINHERIT`, so a membership granted without it confers nothing on the role -- which is equally why the `GRANT pg_signal_backend TO mitatedbsvc_provision` applied at the 2026-09-01 deployment changed nothing (design M-3) and why the runbook's §9 item 3 no longer asks for it; `SET FALSE` withholds `SET ROLE`, which this path never needs.
- The same pre-check stands ahead of that grant (`0004`:96-107, inside the `\if :{?database_name}` branch, so a registration-only registry row is untouched by it): a connection under any role other than this application's own runtime/developer role and the executing role stops the run before anything is changed, background workers (`usesysid IS NULL`) are not counted, and the refusal message names no role -- `::test_deprovision_pre_check_stops_and_changes_nothing_for_an_unrelated_connected_role`.
- The residue a failure leaves is the same bounded one (design §4.1): stopping at or after `ALTER DATABASE ... WITH ALLOW_CONNECTIONS false` (`0004`:158-162) leaves that database non-connectable with the self-grant standing, removable by `mitatedbsvc_provision` alone (`REVOKE <role> FROM CURRENT_USER`, since it holds ADMIN OPTION over the roles it granted) and cleared by re-running `0004` -- `::test_deprovision_completes_on_rerun_after_the_database_was_already_dropped`. On this peer that residue additionally degrades fleet reads while it stands: `ops verify-declarations` reads that one application as having every upgrade pending and fails, `ops inventory` judges it `unknown`, and `ops upgrade-applications` fails on its row (design F-3, read from `MitateDB-api/src/mitatedb_api/ops.py`, with no test of its own) -- a disclosed availability/diagnosis cost, not a privilege change.

#### Evidence

- —

#### Status

- MitateDB has no Python topology-declaration class equivalent to r2db's `AuthorityTopology`;
- `docker/authority-topology.yaml` is a non-secret intent skeleton only, not evidence.
- **Deployment precondition (R-1, cloudsqlsuperuser bypass)**: every application-facing role must be created only via migration SQL's `CREATE ROLE` (never Cloud SQL's Users API, which grants `cloudsqlsuperuser` membership and bypasses `REVOKE CONNECT ... FROM PUBLIC`) -- the fail-closed backstop is verified locally by `test_provisioning_guard_detects_an_unexpected_group_membership`;
- runbook/real-Cloud-SQL verification is `docs/cloud-run-cloud-sql.md` §3.3/§9.
- **Acceptance boundary**: local-cluster evidence only -- on the one real Cloud SQL deployment, role/database DDL and `log_statement=none` have passed, but the deprovision path and the cloudsqlsuperuser probe remain unexercised, production evidence stays open.
- That AST check does not cover this peer's data-plane env still naming the control-credential pepper -- a separate, still-open asymmetry (ledger item L4-13, still open).
- **R-54 evidence boundary**: the four deprovision claims above were measured only against throwaway local PostgreSQL 16 clusters, by the 6 tests this change set adds to `MitateDB-api/tests/test_postgres.py` (:1939, :1960, :1987, :2031, :2091, :2107), each pinned by a mutation of its own stage (design §6.1; 6 mutations on this peer, all red);
- Cloud SQL evidence stays `absent` -- the deprovision path is still unexercised there (this block's own acceptance boundary above), `MitateDB-api/docs/cloud-run-cloud-sql.md` §9 item 3 is now the place that reading is to be taken and asks for a deprovision run against an application holding a live connection instead of the superseded `pg_signal_backend` grant, and whether Cloud SQL's own management connections (a `cloudsqladmin`-owned session) would themselves trip the pre-check is `absent` too -- no control anywhere in this repository depends on `cloudsqladmin`; every occurrence of the name is prose recording this same evidence gap.

### Common

#### Control

- —

#### Evidence

- lateral/control-plane tests;
- CCR-14's control-plane authority boundary is additionally covered by `conformance-tests/test_c14_authority_boundary.py` (condition C-14, SI-00/SI-02/SI-03/SI-08) -- all four adapters (`r2db-api`, `r2db-api-http`, `MitateDB-api`, `MitateDB-api-http`) currently take the PROVIDED branch: each declares a real control-plane surface as `enabled`, checked for real fail-closed behavior in both directions.
- The data-host side of obligation (b) is exercised in the common suite by `conformance-tests/test_c09_audit_evidence.py::test_c09_data_plane_host_audit_query_alias_rejects_control_credential_unless_cohosted` (unconditional, all four plugs, conformance port v1.9).
- Co-hosting is judged by `adapter.surfaces_cohosted(document)` (`conformance-tests/adapter.py`), a plain module-level port helper that derives the answer purely from a 1.6.0+ peer's own declared `surfaces.data.base_url`/`surfaces.control.base_url` origins, never from an adapter's own self-report;
- `conformance-tests/test_c09_audit_evidence.py::test_surfaces_cohosted_resolves_true_only_for_matching_origins_and_false_otherwise` exercises `surfaces_cohosted`'s own `True` branch directly against synthetic `CapabilityDocument` fixtures, independent of whether any real deployment ever co-hosts.

#### Status

- All four registered plugs currently resolve `False` there (no currently-registered deployment co-hosts both surfaces on the same origin), so the `provided` branch of `test_c09_data_plane_host_audit_query_alias_rejects_control_credential_unless_cohosted` remains unreached by any registered plug -- this residual limit is restated, not closed, in the C-09 row of `conformance-tests/CONDITIONS.md`.

## SI-01 Application Isolation

[history](CONTROL_MAPPING_HISTORY.md#si-01)

### r2db-api

#### Control

- `r2db-api/src/r2db_api/service.py` resolves cell from `AuthContext.application_id`;
- `r2db-api/src/r2db_api/postgres.py`'s `PostgresCell` additionally confines each application to its own PostgreSQL database (architecture §8 "D-3 改訂", database-per-application: the database name is assigned by the control plane, never derived from client input, and the cell only ever connects over that application's own `runtime`/`developer` DSNs) and verifies every identifier against that database's live `information_schema` catalog (`_load_catalog`) before composing SQL, so a request cannot reach another application's tables even if an identifier happens to collide by name;

#### Evidence

- `r2db-api/tests/test_foundation.py::test_server_bound_scope_and_isolation`;
- exercised against a real local PostgreSQL 16 cluster by `r2db-api/tests/test_postgres.py`, including `test_cross_database_connect_is_refused_at_the_database_level` (application A's roles cannot even open a raw connection to application B's database) and `test_pool_never_leaks_role_or_schema_across_applications`.

#### Status

- This is local/test-cluster evidence;
- r2db Stage 1, contract 1.6.0, was installed on the VPS on 2026-09-05 with migrations 0001, 0002, 0005, 0006, 0007 and 0003 applied in that order (0004 is the deprovision script and is never applied at install) (`docs/work-orders/DEPLOY_PHASE6_20260904.md` §8, items 9-12), so the same database-per-application `REVOKE CONNECT ... FROM PUBLIC` grant now exists there for the one provisioned application (`sandbox`);
- cross-application connect-refusal itself has not been re-exercised against that instance (only one application is provisioned there), so production database-grant isolation is configured but not yet verified.

### MitateDB-api

#### Control

- `MitateDB-api/src/mitatedb_api/service.py` resolves the cell only from authenticated Principal (`MitateDB-api/tests/test_foundation.py::test_application_scope_is_server_bound`, SQLite backend).
- Database-per-application (design R-1): `MitateDB-api/src/mitatedb_api/backend_postgres.py` confines each application to its own PostgreSQL database, named/allocated by the control plane and never derived from client input;
- `MitateDB-api/migrations/0003_provision_application.sql` issues `REVOKE CONNECT ON DATABASE ... FROM PUBLIC` and grants `CONNECT` only to that application's own `runtime`/`developer` roles, `0004_deprovision_application.sql` reverses it.

#### Evidence

- Verified against a real local PostgreSQL 16 cluster by `MitateDB-api/tests/test_postgres.py::test_cross_database_connect_is_refused_at_the_database_level` (application A's roles cannot open even a raw connection to application B's database).

#### Status

- **Deployment precondition (cloudsqlsuperuser bypass, shared with the SI-00 row above)**: this isolation is a PostgreSQL `CONNECT`-grant boundary, which a Cloud-SQL-Users-API-created role bypasses entirely (Cloud SQL's own `cloudsqlsuperuser` membership) -- `cloud-run-cloud-sql.md` §3.3 states this as a hard runbook rule, and the fail-closed backstop is `MitateDB-api/tests/test_postgres.py::test_provisioning_guard_detects_an_unexpected_group_membership`.
- Local/test-cluster evidence only -- Cloud SQL production database-grant isolation is `absent` until `cloud-run-cloud-sql.md` §9 is run once;
- on the one real deployment made so far, the DDL itself passed but the cross-database-connect-refused behavior has not been re-exercised against that instance and deprovision remains unexercised, so this isolation stays open, not confirmed, in production.

### Common

#### Control

- —

#### Evidence

- `conformance-tests/test_c01_scope_binding.py::test_positive_control_scope_is_bound_and_legitimate_access_succeeds`, `::test_cross_application_entity_is_unreachable`, `::test_cross_application_denial_does_not_disclose_existence` (four adapters -- `r2db-api`, `r2db-api-http`, `MitateDB-api`, `MitateDB-api-http` -- condition C-01).

#### Status

- —

## SI-02 Control Plane Isolation

[history](CONTROL_MAPPING_HISTORY.md#si-02)

### r2db-api

#### Control

- `AuthorityTopology` denies application/developer reachability to control/provisioning (`test_topology.py`).
- `0001_bootstrap_control_plane.sql` creates provisioning authority (`r2dbsvc_control`) as a distinct `NOSUPERUSER`/`NOINHERIT` role only an operator holds a credential for (it deliberately carries `CREATEDB`/`CREATEROLE` for database-per-application provisioning, §5.3 C-2 -- exactly why the API process never holds it);
- `PostgresCell` never embeds a control-plane DSN, only ever opens connections as an application's already-provisioned `runtime`/`developer` role.
- CCR-14's `/control/v1` surface shares SI-00's 3 isolation points identically;
- Within the control plane, `role="control"` is separated from `role="audit"` (read-only) structurally, fail-closed by enumeration: every one of the 8 remaining operations refuses an `audit` principal with `FORBIDDEN` -- `test_audit_role_forbidden_fail_closed_on_every_other_control_endpoint`, with a real-wire-route-table completeness guarantee via `test_audit_role_http_authorization_matrix_all_13_endpoints`.
- The per-application platform-upgrade bulk apply (`upgrade-applications`/`upgrade-status`) and the 4 declaration subcommands are one more operation inside this row's provisioning boundary, not a new route out of an app-facing API: they reach each application's database only as `r2dbsvc_control` over `R2DB_CONTROL_DSN`;
- no API process holds that DSN -- `test_upgrade_applications_exit_codes`, `test_set_platform_timeouts_places_the_same_two_values_on_both_writer_roles`.

#### Evidence

- SI-02's own concern (an app-facing API must not route to control-plane data/capability) is additionally C-14's own vectors 1/2 (app credential fail-closed on every control endpoint, control credential fail-closed on every data endpoint), a structural consequence of the separate-store design: an application credential's verifier does not exist in `control_credentials` at all, so cross-plane authentication fails at lookup, not a secondary authorization check that could be misconfigured away.

#### Status

- **Acceptance boundary**: r2db Stage 1, contract 1.6.0, was installed on the VPS on 2026-09-05 -- provisioning (migrations 0001, 0002, 0005, 0006, 0007 and 0003, applied in that order; 0004 is the deprovision script and is never applied at install) has run, `pg_hba`/`pg_ident` posture B was configured, and external reachability on port 8443 was verified (`docs/work-orders/DEPLOY_PHASE6_20260904.md` §8, items 9-12);
- socket-binding/credential-file-access evidence beyond the runbook's own steps is not separately recorded, and no later contract version has been deployed there since.

### MitateDB-api

#### Control

- The same separate-store design recorded on SI-00 (distinct `credentials`/`control_credentials` tables and roles, distinct peppers) means an application credential's verifier does not exist in `control_credentials` and vice versa -- cross-plane authentication fails at the lookup itself (`ControlPlaneService._locate_credential`), never a secondary check that could be misconfigured away.
- `ControlPlaneService`'s own fixed evaluation order (rate-limit -> authenticate -> must_rotate -> role=control capability denial -> shape -> target-existence -> bounds -> destructive-confirmation -> execute+audit) guarantees an unauthenticated/wrong-plane request never reaches target resolution;
- `issue_credential` refuses `role="control"` unconditionally, before resolving whether the named application even exists -- `test_issue_credential_role_shape_is_validated_before_capability_check`, and against real PostgreSQL, `test_role_control_refused_before_target_resolution_against_real_postgres`.
- Two Cloud Run services by default put this isolation at the network layer too (separate IAM invoker bindings) on top of credential-store separation;
- The `audit` role is narrowed symmetrically with r2db's own bundle -- `test_audit_role_forbidden_fail_closed_on_every_other_control_endpoint`, and against real PostgreSQL `test_audit_role_accepted_on_read_endpoints_and_forbidden_on_a_write_endpoint_against_real_postgres`.
- `upgrade-applications`/`upgrade-status` and the 4 declaration subcommands all require `MITATEDB_PROVISION_DSN`;
- the Cloud Run services' own environments never carry it, so the control service cannot invoke this path either.
- `list-applications` is unchanged;
- per-application upgrade state is deliberately not published on any HTTP surface (requester ruling U-1, design §5).

#### Evidence

- Evidence: `test_upgrade_applications_usage_error_without_provision_dsn`, `test_all_four_subcommands_require_provision_dsn`.

#### Status

- **acceptance boundary**: production network/IAM evidence for that split is absent until deployed, local/test-cluster evidence only.

### Common

#### Control

- —

#### Evidence

- control-plane denial tests;
- CCR-14's cross-plane fail-closed boundary is additionally covered by `conformance-tests/test_c14_authority_boundary.py` (condition C-14) -- see the SI-00 row above for the adapter-state detail (all four adapters currently take the provided branch).

#### Status

- —

## SI-03 Runtime/Developer Separation

[history](CONTROL_MAPPING_HISTORY.md#si-03)

### r2db-api

#### Control

- `ApplicationCell.apply_schema` requires developer context;
- schema catalog rejects unknown runtime entity/fields;
- topology has distinct data/development planes;
- `r2db-api/src/r2db_api/postgres.py`'s `PostgresCell.apply_schema` checks the same `developer: bool` flag and additionally executes every schema-changing statement only over the `developer_dsn` connection pool -- the DML-only `runtime` role has no `CREATE` grant on the schema at all (`migrations/0003_provision_application.sql`'s `REVOKE ALL ON SCHEMA public FROM PUBLIC`, `USAGE`-only grant to the runtime role, and `ALTER DEFAULT PRIVILEGES`), a second, DB-enforced layer under the application-level check.

#### Evidence

- `test_runtime_developer_separation_and_structured_validation`, `test_runtime_unknown_entity_and_failed_mutation_leave_no_ghost`;
- Exercised locally by `r2db-api/tests/test_postgres.py`;

#### Status

- the distinct production Runtime/Developer DB authority itself was realized on the VPS by the same 2026-09-05 Stage 1 install (migrations 0001, 0002, 0005, 0006, 0007 and 0003, applied in that order -- 0004 is the deprovision script and is never applied at install; `docs/work-orders/DEPLOY_PHASE6_20260904.md` §8, items 9-12), though the runtime-role-has-no-CREATE-grant behavior has not been separately re-exercised against that instance.

### MitateDB-api

#### Control

- Preliminary local API method/role-check evidence: `ApplicationRuntime` has no schema mutation method and `ApplicationCell._require_developer`;

#### Evidence

- `test_developer_schema_and_runtime_crud`;

#### Status

- distinct production Runtime/Developer DB authority TBD.

### Common

#### Control

- —

#### Evidence

- privilege tests;
- the `role=control` in-band issuance refusal (a third, non-runtime/developer role never silently granted) is additionally covered by `conformance-tests/test_c14_authority_boundary.py` (condition C-14) -- see the SI-00 row above for the adapter-state detail.

#### Status

- —

## SI-04 No Arbitrary DB Commands

[history](CONTROL_MAPPING_HISTORY.md#si-04)

### r2db-api

#### Control

- `structured.py` exposes only enumerated operations and no native command API;
- `r2db-api/src/r2db_api/postgres.py`'s `_run` is the single execution choke point every statement passes through and is typed to accept only `psycopg.sql.Composed`/`psycopg.sql.SQL`, raising `TypeError` on any `str` -- no method on `PostgresCell`, public or private, can pass a raw command string to PostgreSQL.

#### Evidence

- `test_runtime_developer_separation_and_structured_validation`;
- contract surface review;
- Exercised against a real PostgreSQL cluster by `r2db-api/tests/test_postgres.py` and the `r2db-api-http` conformance adapter.

#### Status

- —

### MitateDB-api

#### Control

- Structured-only methods in `MitateDB-api/src/mitatedb_api/cell.py`;
- no command-text execution method;

#### Evidence

- `test_no_arbitrary_sql_and_identifier_validation`.

#### Status

- —

### Common

#### Control

- —

#### Evidence

- `conformance-tests/test_c03_structured_injection.py::test_no_native_command_surface_is_exposed` (four adapters -- `r2db-api`, `r2db-api-http`, `MitateDB-api`, `MitateDB-api-http` -- condition C-03).

#### Status

- —

## SI-05 Validated Structured Operations

[history](CONTROL_MAPPING_HISTORY.md#si-05)

### r2db-api

#### Control

- `validate_identifier`, operator allowlist, typed mutation shape, and service tests in `r2db-api/src/r2db_api/structured.py`;
- `r2db-api/src/r2db_api/postgres.py` composes identifiers only via `psycopg.sql.Identifier`, after both the shared `structured.py` syntax allowlist and a second check against the schema's live `information_schema` catalog (`_load_catalog`), and binds every value as a server-side parameter (`psycopg.sql.Placeholder`/`Jsonb`) rather than string interpolation;
- CCR-13 (`docs/design/R2DB_CCR13_STORAGE_V1.md` R-7) extends validation from identifiers/shapes to value domains -- typed-column values (`bigint`/`double precision`/`boolean`/`text`) are checked against the declared type and bound natively, with a shared range/NUL-byte check ahead of execution so a value PostgreSQL would reject at runtime fails deterministically instead.

#### Evidence

- `r2db-api/tests/test_postgres.py` covers this for query/mutation paths and the DDL paths (`create_entity`/`add_field`), where the catalog cannot reject an identifier that does not exist yet.

#### Status

- Exercised against a real local PostgreSQL 16 cluster only -- no production evidence.

### MitateDB-api

#### Control

- `identifiers.py` validation, quoted identifiers and bound values in `cell.py`;

#### Evidence

- `test_no_arbitrary_sql_and_identifier_validation`.

#### Status

- —

### Common

#### Control

- —

#### Evidence

- `conformance-tests/test_c03_structured_injection.py::test_identifier_positions_reject_every_payload`, `::test_value_positions_round_trip_or_deny`, `::test_structural_integrity_across_corpus` (four adapters -- `r2db-api`, `r2db-api-http`, `MitateDB-api`, `MitateDB-api-http` -- condition C-03);
- CCR-13 declaration/behavior agreement is additionally covered by `test_c12_capability_agreement.py` (condition C-12) and `test_c17_declaration_agreement.py` (condition C-17), both executable on all four adapters.
- The branch is narrow by construction -- `transport_kind == "socket"` only, only for wire-carried positions, and only for `httpx.LocalProtocolError` (or an `UNCLASSIFIED` non-problem+json failure), never for an unreachable peer -- and body-carried positions still demand a genuine contract-coded denial on every plug -- `conformance-tests/test_c03_structured_injection.py::test_c03_wire_rejection_never_applies_to_a_body_carried_position`, `::test_c03_wire_rejection_never_applies_to_a_reachability_failure`.

#### Status

- **Phase 10 socket plugs -- disclosed**: C-03's corpus now also runs on the two real-socket plugs, where a URL-path-carried identifier payload can be refused by the client's own HTTP/1.1 layer (h11) before any byte reaches the peer;
- the suite counts that wire refusal as a rejection, so for the `entity` position on a socket plug the denial is not always the peer's own validation.

## SI-06 Server-Bound Credential Scope

[history](CONTROL_MAPPING_HISTORY.md#si-06)

### r2db-api

#### Control

- `CredentialStore.authenticate/assert_active` derives immutable `AuthContext` -- `test_server_bound_scope_and_isolation`.
- **CCR-14 extends server-bound scope to the control credential type**: `ControlCredentialStore`/`PostgresControlCredentialStore` derive an immutable `ControlAuthContext` (`credential_id`/`must_rotate`) from stored verifier state alone, never a client-supplied field, rejecting disabled/revoked/must-rotate-exceeded state like the application-plane store;
- the secret is bound server-side to its own dedicated HMAC pepper (required to differ from the application pepper) and exposed only as an opaque handle, never a raw secret past authentication -- `test_control_credential_parity_add_authenticate_rotate_must_rotate_both_impls`, `test_control_authenticate_fails_closed_when_platform_db_unreachable`.
- **`must_rotate` exposure**: `list_credentials` rows for a control-table credential carry their real `must_rotate` value (application rows never carry the key -- the concept does not exist for them) -- `test_issued_secret_appears_only_in_the_response`.
- **`audit` role**: a second, weaker, distributable control-credential scope (`control_credentials.role` CHECK constraint) narrowed to the 3 read-only endpoints;
- issuance is ceremony-only (out-of-band CLI, single tx = issue+rotate, distributed already `must_rotate=false`), never in-band;
- fail-closed on the other 8 write operations, durably audited -- `test_audit_role_forbidden_fail_closed_on_every_other_control_endpoint`, `test_audit_role_http_authorization_matrix_all_11_endpoints` (derives its own enumeration from the real wire route table).
- **Revoke-gate role filter**: the "sole remaining control credential" gate (SI-09) filters to `role=="control"` rows only, so an `audit` row can neither mask nor be mistaken for the last administrative credential;
- revoking an `audit` credential itself is never gated -- `test_revoke_gate_active_audit_credential_does_not_mask_last_active_control_credential`.
- **Per-application issuance freeze**: `applications.issuance_frozen`, CLI-only, non-destructive;
- `issue_credential` against a frozen application refused `FORBIDDEN` (evaluated after the `role=control` capability refusal, per the fixed evaluation order) -- `test_issuance_freeze_forbids_then_unfreeze_allows_again`, `test_issuance_freeze_precedence_role_control_refused_before_freeze_check`.

#### Evidence

- —

#### Status

- —

### MitateDB-api

#### Control

- `CredentialStore.authenticate` derives Application/role from stored credential state -- `test_application_scope_is_server_bound`.
- **Control credential**: `control_auth.ControlCredentialStore`/`PostgresControlCredentialStore` (same call-surface-parity convention as the application-credential pair) derive an immutable `ControlPrincipal` (`credential_id`/`must_rotate`) from stored verifier state alone, bound to its own dedicated pepper (required to differ from the application pepper);
- **`must_rotate` exposure**: `list_credentials` merges application and control rows so a control-table credential's real `must_rotate` value is exposed, symmetric with r2db -- `test_list_credentials_merges_application_and_control_rows`.
- **`audit` role**: ceremony-only issuance (single tx = issue+rotate), fail-closed with durable audit on the 8 write endpoints, allowed on exactly the 3 read endpoints -- `test_audit_role_forbidden_fail_closed_on_every_other_control_endpoint`, and against real PostgreSQL `test_audit_role_accepted_on_read_endpoints_and_forbidden_on_a_write_endpoint_against_real_postgres`.
- **Revoke-gate role filter and issuance freeze**, applied from the start on this peer, symmetric with r2db's own bundle -- `test_revoke_gate_active_audit_credential_does_not_mask_last_active_control_credential`, `test_issuance_freeze_precedence_role_control_refused_before_freeze_check`;

#### Evidence

- parity verified across both implementations -- `test_issue_then_authenticate_succeeds`, `test_revoke_is_terminal_enable_cannot_resurrect_it`.
- also verified via the CLI (`test_ops.py::test_cli_freeze_issuance_then_unfreeze_round_trips`) and, uniquely on this peer, an in-memory rollback path -- `test_in_memory_issuance_freeze_rolls_back_with_its_own_unit_of_work`.

#### Status

- —

### Common

#### Control

- Both peers' bearer is the locator form `<credential_id>.<secret_part>` (an opaque complete bearer at the contract level);
- authentication looks up the row by the locator's `credential_id` and then compares the verifier with `hmac.compare_digest` -- **the verifier is never used as a lookup key** (r2db's `_SELECT_BY_VERIFIER` has been removed; `auth.split_bearer_locator` / MitateDB's `credential_wire.split_bearer_locator` split the bearer exactly once, inside the store).
- A malformed bearer (no `.`, an empty half, or a NUL) fails closed before any lookup (`AUTH_INVALID` uniformly, SI-10) and is durably audited as `authentication_denied` with an unknown actor (SI-14).
- An unknown credential id still runs `compare_digest` against a dummy verifier so no timing difference leaks (pinned on both peers by `test_authenticate_methods_use_the_shared_dummy_verifier_for_unconditional_compare_digest`).

#### Evidence

- `conformance-tests/test_c01_scope_binding.py::test_must_deny_vectors_are_denied_with_contract_codes`, `::test_must_ignore_vectors_leave_scope_and_other_app_unchanged`, `::test_structurally_absent_vectors_have_no_forbidden_parameters`, `::test_runtime_credential_cannot_self_elevate_to_schema_authority` (four adapters -- `r2db-api`, `r2db-api-http`, `MitateDB-api`, `MitateDB-api-http` -- condition C-01).

#### Status

- —

## SI-07 Compromised Credential Containment

[history](CONTROL_MAPPING_HISTORY.md#si-07)

### r2db-api

#### Control

- Topology deny rules plus per-credential role/scope records;

#### Evidence

- negative topology and isolation tests;

#### Status

- production containment evidence not yet present.

### MitateDB-api

#### Control

- **Control-credential-scoped compromise containment** (application-credential compromise containment is the SI-13/SI-06 rows above): a compromised control credential is bounded to (i) application credentials it issued/rotated during the compromise window, (ii) an availability harm from any application credential it revoked (ungated -- `ControlPlaneService.revoke_credential` applies no confirmation to an application-credential target, `MitateDB-api/tests/test_control_plane_service.py::test_revoke_application_credential_is_never_gated`), and never reaches Application data or the `mitatedbsvc_provision` provisioning/deprovisioning surface (a wholly separate DSN no control credential or control-plane process holds).
- `role=control` issuance has exactly one path, the out-of-band `bootstrap`/`reset` ceremony -- no in-band operation reaches it (`_deny_role_control`, evaluated before target resolution, `MitateDB-api/tests/test_control_plane_service.py::test_issue_credential_role_shape_is_validated_before_capability_check`);
- `reset` revokes every existing control credential unconditionally and mints exactly one new one atomically, verified against real PostgreSQL by `MitateDB-api/tests/test_ops.py::test_reset_with_the_echoed_phrase_revokes_everything_and_mints_one_new_credential`.
- Full recovery procedure: `MitateDB-api/docs/CONTROL_PLANE_COMPROMISE_PLAYBOOK.md`.
- **`audit`-credential compromise** is a strictly narrower containment class: bounded to read-only disclosure of `list_applications`/`list_credentials`/`control_capabilities` (see the SI-06/SI-10 rows for the exact exposure and the SI-02 row for the authority-class distinction) -- an `audit` credential cannot issue, rotate, revoke, register, enable, or disable anything (fail-closed on all 8 write endpoints, `test_audit_role_forbidden_fail_closed_on_every_other_control_endpoint`), so its compromise carries none of the (i)/(ii) harms above;
- `reset`'s unconditional revoke-all also covers every live `audit` row, same ceremony, same test.

#### Evidence

- —

#### Status

- —

### Common

#### Control

- —

#### Evidence

- stolen-credential scenario tests

#### Status

- —

## SI-08 Bounded Resource Consumption

[history](CONTROL_MAPPING_HISTORY.md#si-08)

### r2db-api

#### Control

- finite `ResourceLimits` across required classes;
- atomic credential-rate window, iterative request/depth checks, structured batch/result/schema checks, wall-clock deadline -- `test_every_advertised_resource_limit_has_a_deterministic_boundary`, `test_rate_limit_is_atomic_for_concurrent_requests`.
- `RequestByteBoundMiddleware` enforces the byte bound in the ASGI receive loop, measured from actual bytes received (not `Content-Length`), before Starlette's parser runs -- the real request path, unexercised on the VPS under real traffic;
- `postgres.py` also maps `execution_ms` onto PostgreSQL's own `statement_timeout`/`lock_timeout` (`SET LOCAL`, per-transaction), a real second enforcement layer.
- **CCR-14 adds 3 control-plane resource classes**: `applications`, `credentials_per_application` (revoked rows never count), `control_requests_per_minute` (single global sliding 60s window, not per-credential) -- enforced by `ControlPlaneService`, published `enforced`.
- The rate check runs before authentication and before any durable audit write -- a flood cannot generate unbounded audit rows, and is the one denial category never durably audited (SI-14) -- `test_applications_limit_at_exact_bound`, `test_rate_limit_precedes_authentication_and_is_not_audited`.
- `request_bytes` declaration is two-layer: the service layer alone declares `unavailable` (no HTTP boundary there), `control_http.py` overrides to `enforced` once the real middleware mounts, both reading the SAME limits source -- `test_l4_request_bytes_single_source_mutating_limit_changes_both_bound_and_discovery`.
- **`audit_requests_per_minute`**: a 5th control-plane class, default 60, env-overridable, `enforced`;
- accepted range is any positive integer, no upper bound (checks only `> 0`, matching MitateDB);
- a separate counter, not a renamed view of `control_requests_per_minute` -- `audit_query` (canonical path + `/v1/audit/query` alias) consumes only this window, so polling for evidence cannot exhaust the window `revoke_credential` depends on;
- checked pre-auth like the control window, so an unauthenticated flood cannot generate audit rows.
- Overage is `LIMIT_EXCEEDED` with `limit_class=="audit_requests_per_minute"` -- `test_audit_query_over_its_own_window_is_limit_exceeded_with_limit_class_audit_requests_per_minute`.
- **The audit reader's own statement bound (R-56, design `docs/design/R2DB_AUDIT_READER_STATEMENT_TIMEOUT_V0_1.md` D-1/D-4)**: `0014_auditreader_statement_timeout.sql` runs `ALTER ROLE r2dbsvc_auditreader SET statement_timeout = '5000ms'`, which bounds what a connection made with the audit reader's own DSN may run -- an operator's interactive `psql` session as much as `control_main`'s pooled ones -- but a role setting is copied into a session at login, so it reaches connections OPENED AFTER the file is applied: a connection `_RolePool` (`r2db-api/src/r2db_api/postgres.py`) is already holding keeps the value it logged in with, and the control process is restarted once `0014` has been applied (`r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md` section 19 carries that order -- apply, restart the control process, then `ops verify-declarations`);
- a statement cut off at that bound arrives as `QueryCanceled`, and `PostgresAuditQueryStore.query`'s own `except psycopg.Error` (`r2db-api/src/r2db_api/credential_store.py`) answers 503 `SERVICE_UNAVAILABLE` without the backend's own message and hands the connection back to the pool; `ops verify-declarations`'s F-17 (exit code 16) reads the role-level `statement_timeout` of the roles it identifies by their real SELECT grants on both audit tables and requires a positive value with no per-database row overriding that same key -- **F-17 judges the DECLARATION, not the effective value inside a running process**, which is what the Evidence tests below read on a reader connection opened for that purpose;
- **disclosed difference between the peers**: MitateDB-api's `0013_role_statement_timeouts.sql` puts a role-level `statement_timeout` on its application runtime/developer roles as well, while r2db-api leaves those two roles without a role-level timeout and relies on the per-transaction `SET LOCAL` `_set_timeouts` issues (`r2db-api/src/r2db_api/postgres.py:2294-2308`), which sets `statement_timeout` and `lock_timeout` alike (MitateDB-api's role-level setting is `statement_timeout` only); on MitateDB-api the developer connection its catalog path reads through carries that role-level value -- `MitateDB-api/tests/test_application_audit.py::test_developer_connection_used_by_the_catalog_path_carries_the_role_level_statement_timeout`.
- all four client-reachable operations of `PostgresCell` -- `query`, `transact`, `apply_schema` and `catalog` (`:803-819`) -- issue that call inside their own transaction; `catalog` takes its bound from the `ResourceLimits` it is passed (`DataService.catalog` passes its own), falls back to the default `ResourceLimits()` when called without one, so the bound never depends on the caller, and maps a cancelled statement or a lock timeout to the same `LIMIT_EXCEEDED` the other three return -- `r2db-api/tests/test_postgres.py::test_catalog_wires_statement_and_lock_timeout_to_the_passed_resource_limits`, `::test_catalog_without_an_explicit_limits_argument_uses_default_resource_limits`, `::test_catalog_set_local_timeouts_do_not_leak_to_the_next_transaction`, `::test_catalog_maps_timeout_and_lock_conflicts_to_limit_exceeded`, `r2db-api/tests/test_foundation.py::test_data_service_catalog_passes_only_its_own_limits_to_the_cell`, `::test_data_service_catalog_denial_is_audited_with_the_limit_exceeded_reason`.

#### Evidence

- **R-56, measured on throwaway PostgreSQL clusters**: the effective value a reader connection opened after `0014` carries, the 503 a statement over that ROLE-level bound produces on a pooled reader connection (the scenario shortens the role's own declared value with `ALTER ROLE ... SET` and restores it from `pg_roles.rolconfig`, rather than overriding it per connection), and `0014`'s own re-application -- `r2db-api/tests/test_auditreader_statement_timeout.py::test_reader_connection_effective_statement_timeout_is_5000ms_after_0014` (reads `pg_settings.setting`, the raw ms integer), `::test_slow_audit_query_is_canceled_returns_503_without_backend_detail_and_frees_the_connection`, `::test_0014_reapplication_is_idempotent`; F-17's own red and green are `r2db-api/tests/test_ops_verify_declarations.py::test_verify_declarations_f17_passes_after_migration_0014`, `::test_verify_declarations_f17_fails_when_declared_timeout_is_zero`, `::test_verify_declarations_f17_fails_when_declared_timeout_is_reset`, `::test_verify_declarations_f17_fails_when_a_per_database_override_exists`, `::test_verify_declarations_f17_passes_when_auditreader_role_is_absent`, `::test_f17_the_schema_owning_role_is_never_flagged_despite_an_explicit_select_grant`.

#### Status

- **Not bound by this window**: the application plane's durable denial writes are on a different plane/host, bounded by D-3 coalescing + row-length CHECKs -- deliberately no data-plane pre-auth window.
- **Production evidence for `0014` is `absent`** (R-56): the measurements recorded above were taken on throwaway PostgreSQL clusters started by the test suite, and the VPS deployment was left as it stands, with `0014` unapplied.
- On that deployment `ops verify-declarations` answers `FAIL F-17` (exit code 16) while `0014` is unapplied, and **that is the intended signal, not a regression**: the check states in machine-readable form a gap that predates it (an audit reader whose statements carry no bound of their own), and applying `0014` then restarting the control process clears it (`r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md` section 19).

### r2db-api -- capacity and concurrency

#### Control

- **Phase 10 (WP-4/WP-6/WP-8, 2026-09-10) -- declared process ceilings, DB-side count bounds, derived connection capacity, pre-authentication concurrency**: (a) `process_ceilings` (`{"data": N, "control": M}`) is a platform-declaration row read at startup from the declaration table alone (no env fallback), and it is what decides `limit_enforcement`: ceiling 1 publishes the per-process in-memory classes (`requests_per_minute`/`concurrency` on the data plane, `control_requests_per_minute`/`audit_requests_per_minute` on the control plane) as `enforced`, ceiling >= 2 publishes exactly those as `deployment_required` -- an in-process counter is not a deployment-wide bound once more than one process serves the same base URL;
- request-scoped classes (`request_bytes`, `batch_items`, `result_items`, `query_complexity`, `schema_objects`, `operation_depth`, `enum_members`) and DB-side-bound classes stay `enforced` at every ceiling, `execution_ms` stays `reference_wall_clock`, and each plane reads its OWN key -- `r2db-api/tests/test_process_ceilings_declaration.py::test_ceiling_one_maps_in_memory_classes_to_enforced`, `::test_ceiling_two_maps_in_memory_classes_to_deployment_required`, `::test_control_plane_ceiling_mapping_reads_control_not_data_through_build_control_app`, `::test_declaration_table_is_the_only_source_no_env_fallback`;
- a missing or malformed row stops startup and `ops verify-declarations` reports F-15 with exit code 14 -- `::test_missing_row_fails_fast_through_build_app`, `::test_verify_declarations_f15_when_process_ceilings_row_is_absent`, `::test_verify_declarations_exit_code_table_maps_f15_to_14`.
- (b) `applications` and `credentials_per_application` are bounded in the DATABASE rather than in the process: `_take_bound_advisory_lock` (`r2db-api/src/r2db_api/credential_store.py`) takes `pg_advisory_xact_lock(hashtext('<schema>.<table>'))` in the same transaction as the count-then-insert, so two concurrent writers cannot both pass a bound -- `::test_db_side_bounds_hold_under_concurrent_writers_applications`, `::test_db_side_bounds_hold_under_concurrent_writers_credentials_per_application`, and the barrier-synchronized two-writer forms `::test_applications_bound_holds_under_barrier_synchronized_concurrent_registration`, `::test_credentials_per_application_bound_holds_under_barrier_synchronized_concurrent_issuance`.
- (c) Connection capacity is derived from the declared `concurrency`, not fixed: `role_pool_size(limits) == limits.concurrency` (`r2db-api/src/r2db_api/limits.py`) sizes every served application's runtime/developer pool and both platform pools (credential store + durable audit sink) -- `r2db-api/tests/test_threadpool_offload.py::test_role_pool_size_derives_from_declared_concurrency`, `::test_main_composition_root_wires_pool_size_from_role_pool_size`, `::test_role_pool_sized_to_declared_concurrency_avoids_premature_503`, `r2db-api/tests/test_credential_persistence.py::test_platform_pool_sized_to_declared_concurrency_avoids_premature_503`;
- `r2db-api/migrations/0013_role_connection_limits.sql` raises each role's PostgreSQL `CONNECTION LIMIT` to its own pool composition plus a 4-connection operator margin, and F-16 (`check_role_connection_limits`, roles identified by their REAL grants and never by name, floor = the maximum over every matching role class, the schema owner excluded, register-only applications with NULL role names skipped) fails `ops verify-declarations` with exit code 15 and stops each composition root at startup when its own role is below that floor -- `r2db-api/tests/test_ops_verify_declarations.py::test_verify_declarations_f16_passes_after_migration_0013`, `::test_verify_declarations_f16_fails_when_a_role_connection_limit_is_lowered_below_its_pool_composition_floor`, `::test_f16_floor_for_a_role_matching_multiple_classes_is_the_max_not_the_last_assigned`, `::test_f16_the_schema_owning_role_is_never_flagged_even_though_it_matches_every_class`, `::test_0013_migration_tolerates_a_registered_only_application_and_still_raises_a_provisioned_applications_role_limits`, `r2db-api/tests/test_credential_persistence.py::test_build_app_fails_fast_when_its_own_api_role_connection_limit_is_lowered_below_the_pool_composition_floor`, `r2db-api/tests/test_surfaces_env.py::test_build_control_app_fails_fast_when_its_own_controlplane_role_connection_limit_is_lowered_below_the_pool_composition_floor`.
- (d) On the HTTP plane the deployment-wide `concurrency` slot is taken BEFORE authentication, so an unauthenticated flood is bounded before it reaches the credential store;
- this surface's order is BYTE BOUND -> CONCURRENCY SLOT -> AUTHENTICATION -> body -> rate/business (the per-credential `requests_per_minute` window stays reachable only after authentication succeeds, so a both-exhausted request is denied `concurrency` here -- the opposite of the cell-level order, an explicit HTTP-plane ruling, not an implementation accident), and the slot is held across authentication and dispatch and released on every exit path -- `r2db-api/tests/test_preauth_concurrency_bound.py::test_unauthenticated_flood_is_bounded_by_concurrency`, `::test_http_plane_denies_concurrency_before_requests_per_minute`, `::test_concurrency_hold_spans_the_gap_between_authentication_and_dispatch`, `::test_slot_is_released_after_a_401_ending_request`, `::test_slot_is_released_after_a_validation_failed_ending_request`, `::test_concurrency_slot_is_acquired_exactly_once_per_handler`.
- (e) Async handlers delegate their synchronous section to the threadpool, so more than one request is genuinely in flight and these bounds are exercised under real parallelism;
- the limiter state and the pools are lock-guarded, pinned lexically (source shape) rather than by a race -- `r2db-api/tests/test_threadpool_offload.py::test_sync_section_runs_off_the_event_loop`, `::test_control_sync_section_runs_off_the_event_loop`, `::test_body_read_stays_on_the_loop`, `::test_limiter_state_is_thread_safe`, `::test_pool_acquire_is_thread_safe`, `::test_slot_check_then_increment_is_lexically_inside_the_active_lock`, `::test_rate_window_check_then_append_is_lexically_inside_the_rate_lock`, `::test_role_pool_reservation_is_lexically_inside_the_pool_lock`, `::test_authenticate_delegation_pinned_for_every_body_first_handler`, `::test_service_call_delegation_pinned_for_query_mutate_cross_entity_schema`, `::test_control_service_call_delegation_pinned_for_rotate_and_issue_credential`.

#### Evidence

- —

#### Status

- —

### MitateDB-api

#### Control

- Local bounds for batch/result/fields/filters/schema/request-size in `FoundationConfig`/`MITATEDB_*` config -- `test_batch_and_request_size_limits_and_empty_filters_shape_check`.
- **`request_bytes`**: ASGI receive-loop middleware measures actual received bytes (never `Content-Length`), rejects before Starlette's parser runs, sized from the SAME `FoundationConfig.max_request_bytes` the declaration publishes -- `test_byte_bound_is_measured_from_actual_received_bytes_not_content_length_header`, `test_request_over_byte_limit_is_limit_exceeded_before_parsing`.
- **Control-plane's own 3 classes plus its own `request_bytes` bound** (`applications`/`credentials_per_application`/`control_requests_per_minute`): all enforced by `ControlPlaneService`, published `enforced`;
- `credentials_per_application` excludes revoked rows -- `test_register_application_enforces_the_applications_bound`, `test_rate_limit_denial_is_never_durably_audited` (matching r2db's identical pre-auth/never-audited rule).
- **Application-plane resource bounds** (Phase 8 WP-1a, rework 1, 2026-09-06): `requests_per_minute` and `concurrency` are `enforced` -- `_LimitStateHolder.acquire_rate`/`.concurrency_slot` (`cell.py:744`, `:775-782`, `:785-794`), declared in `__build_capabilities_document`'s `limit_enforcement` dict (`cell.py:3811`, `:4051`, `:4055`);
- `execution_ms` is declared `reference_wall_clock`, not `enforced` (`cell.py:4044`) -- a wall-clock deadline (`time.monotonic() + max_execution_ms`) handed to the backend, `backend_postgres.py` converts it into a real `SET LOCAL statement_timeout`/`lock_timeout` (`backend_postgres.py:1658-1661`), matching r2db-api's own identical declaration.
- **`batch_entities`**: a 4th enforced class bounding distinct entity names a `cross_entity_mutation` unit may name (repeats don't count twice; `batch_items` is the separate total-operation-count bound);
- default 10, counted before any operation executes, `enforced` -- `test_transact_batch_entities_boundary_and_distinct_count_ignores_repeats`, real-HTTP `test_cross_entity_mutation_batch_entities_boundary`;
- **`audit_requests_per_minute`**: same default 60, same separate-counter/pre-auth/never-shared-with-`control_requests_per_minute` properties and `LIMIT_EXCEEDED`/`limit_class` shape as r2db's own entry -- `test_audit_query_over_its_own_window_is_limit_exceeded_with_limit_class_audit_requests_per_minute`.
- **Symmetric with r2db**: all 4 control-plane request-count classes accept any positive integer with no upper bound;
- **F-17 runs on this peer too (R-56)**: the same `ops verify-declarations` check r2db-api's own SI-08 row describes (role-level `statement_timeout` positive for the roles identified by their real SELECT grants on both audit tables, no per-database row overriding that key, exit code 16) is judged here against the reader bound `0013_role_statement_timeouts.sql` already declares, so R-56 adds no migration to this peer; `_f17_message` and `check_auditreader_statement_timeout` are rows of `_ISOMORPHIC_TARGETS`, which holds the two peers' wording and judgment together -- `MitateDB-api/tests/test_ops_verify_declarations.py::test_verify_declarations_f17_passes_from_migration_0013`, `::test_verify_declarations_f17_fails_when_declared_timeout_is_zero`, `::test_verify_declarations_f17_fails_when_declared_timeout_is_reset`, `::test_verify_declarations_f17_fails_when_a_per_database_override_exists`, `::test_verify_declarations_f17_passes_when_auditreader_role_is_absent`, `::test_f17_the_schema_owning_role_is_never_flagged_despite_an_explicit_select_grant`, `MitateDB-api/tests/test_audit_query.py::test_isomorphic_target_table_is_pinned_to_its_current_140_rows`.
- The per-application-upgrade/deprovision psql invocations (`_run_upgrade_script`/`_run_deprovision_script`) require a `--lock-timeout` value with no default, set on the psql session via `PGOPTIONS`'s own `-c lock_timeout=<value>` (appended to, never overwriting, the DSN's own `options` value if any) so each of these two psql invocations' own catalog-lock wait has an upper bound rather than none -- the CLI rejects both a missing value and one that is not a positive integer optionally followed by `ms`/`s`/`min`, before any psql subprocess starts.

#### Evidence

- common-suite coverage is C-16's own V3 (see SI-11 row).
- `MitateDB-api/tests/test_platform_migration_reapply.py::test_run_upgrade_script_passes_lock_timeout_via_pgoptions`, `::test_run_deprovision_script_passes_lock_timeout_via_pgoptions`, `::test_run_upgrade_script_keeps_the_dsns_own_pgoptions_alongside_lock_timeout`, `::test_upgrade_applications_without_lock_timeout_is_a_usage_error`, `::test_deprovision_without_lock_timeout_is_a_usage_error`, `::test_upgrade_applications_rejects_a_malformed_lock_timeout_value`, `::test_deprovision_rejects_a_malformed_lock_timeout_value`, `::test_deprovision_accepts_a_well_formed_lock_timeout_value`.

#### Status

- the contract declares no range -- an operator responsibility, published as-declared -- removing the ceiling also removes the deployment-misconfiguration guardrail it incidentally provided (nothing stops an operator from declaring an implausibly large value), a deliberate trade recorded in `MitateDB-api/docs/cloud-run-cloud-sql.md` §3.2c / `r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md` §15 -- `test_limits_reject_out_of_range_values`.
- **Deployment caveat**: like `control_requests_per_minute`, this is an in-process counter, inheriting the `--max-instances=1` requirement on the control service.
- The application plane's own durable-denial writes are NOT governed by this window (SI-14 point 6).

### MitateDB-api -- ops inventory

#### Control

- **`ops inventory` (Gate-0 DB-layer read-only judgments, R-45 WP-B/WP-E)**: item (8) sums connection demand across `mitatedbsvc_api`/`mitatedbsvc_controlplane`/`mitatedbsvc_auditreader` (table-grant discovery, never a literal name) plus every application's own runtime/developer role; application-role demand scales with the Data TOTAL, never `concurrency` alone; `--control-not-deployed` zeroes Control's own demand/role checks;
- measured: only `control_composition.build_control_service` ever pools a connection against `mitatedbsvc_auditreader` (conditionally on `MITATEDB_AUDIT_DSN`), `main.build_app` never does -- its demand is counted only under the Control process count;
- each plane's own CEILING (vs. declared `process_ceilings`) and TOTAL (actual count, feeds demand) are SEPARATE positive-integer arguments, plus `concurrency`/`--reserved-connections` (0 = no reserve) -- omitting any leaves (8) unknown; `--control-not-deployed` substitutes Control's pair;
- `CONNECTION LIMIT = -1` is unknown, but only for a role INSIDE this item's own target role set -- an unrelated role (e.g. the provision role) carrying `-1` never rounds (8) to unknown;
- a declaration read that finds the row absent is unknown + remediation-required; a row that fails validation is blocked; a plain connection failure is unknown; a declared/actual CEILING mismatch on EITHER plane is blocked (never compared for Control once `--control-not-deployed` is given);
- item (6)'s runtime-settings half confirms once `statement_timeout` (0013, `setdatabase = 0`) is POSITIVE, plus a real non-`-1` `CONNECTION LIMIT` on every item (8) target role; 0/negative/unparseable blocks (`statement-timeout-unbounded`), absent is unknown (`lock_timeout` unjudged, no DDL role here); lock-type/downtime, and item (5) in full, are `unjudged_items` (closed `part` vocabulary, reason `runbook-acceptance`).
- **Rollout arithmetic against the ceilings 0014 sets**: at `concurrency=32` with a process TOTAL of 2 on each plane (a candidate revision beside the revision it replaces; the declared ceilings stay 1, since the TOTAL is a count of processes and not a declaration), condition 1 holds for every role class and (8) is confirmed, while a TOTAL of 3 blocks on `mitatedbsvc_api` (demand 3 x 2 x 32 = 192 against its own ceiling of 132).
- A stray single-file re-application after 0014 is not reverted by any migration, and (8) catches only some of them: a stray `0012` is caught (it lowers every role 0012 itself names -- `mitatedbsvc_api`, `mitatedbsvc_controlplane` and every application's own runtime/developer role -- back to 68/20/36, while `mitatedbsvc_auditreader` keeps 0014's own 12, since 0012 never alters it), a stray `0013` is caught once an application is provisioned after it (that application's roles are created at 36), and a stray `0013` with NO application provisioned afterwards is NOT caught -- every existing role still carries 0014's own ceiling, so (8) reads confirmed while the provisioning function is silently back at 36 for the next application; that gap is a disclosed limit pinned by a test that turns red if the detection ever improves, and `MitateDB-api/docs/cloud-run-cloud-sql.md` section 10 carries it together with the rule that a re-application runs `0012` -> `0013` -> `0014` in that order.

#### Evidence

- Evidence for the `ops inventory` claims above is `MitateDB-api/tests/test_ops_inventory.py`; every name below (`::name` form) is in that ONE file.
- role-set discovery and application-role scaling: `test_inventory_connection_headroom_data_process_count_overflow_is_blocked`, `::test_inventory_connection_headroom_app_role_demand_scales_with_data_process_count`, `::test_inventory_connection_headroom_app_role_overflow_with_named_values`, `::test_inventory_connection_headroom_shared_application_role_budget_counts_once`.
- auditreader pooled by Control only: `::test_inventory_connection_headroom_auditreader_counted_under_control_only`, `::test_only_control_composition_pools_a_connection_against_mitatedbsvc_auditreader`.
- CLI arguments and their own fail-closed paths: `::test_inventory_connection_headroom_concurrency_missing_is_unknown`, `::test_inventory_connection_headroom_process_count_missing_is_unknown`, `::test_inventory_connection_headroom_reserved_connections_missing_is_unknown`, `::test_inventory_connection_headroom_max_connections_unreadable_is_unknown`.
- `-1` scoped to the target role set only: `::test_inventory_connection_headroom_minus_one_connection_limit_is_unknown`, `::test_inventory_connection_headroom_minus_one_on_an_unrelated_role_is_not_unknown`.
- declaration missing/invalid/connection-failure, ceiling mismatch, ceiling-vs-total, `--control-not-deployed`: `::test_inventory_connection_headroom_declaration_missing_is_unknown_with_remediation`, `::test_inventory_connection_headroom_declaration_shape_violation_is_blocked`, `::test_inventory_connection_headroom_declaration_connection_failure_is_unknown`, `::test_inventory_connection_headroom_declared_and_actual_process_counts_disagree_is_blocked`, `::test_inventory_connection_headroom_control_process_count_mismatch_is_blocked`, `::test_inventory_connection_headroom_total_may_exceed_ceiling_without_a_declaration_mismatch`, `::test_inventory_connection_headroom_control_not_deployed_computes_with_control_zeroed`.
- the pinned reserve constant and its own real measurement: `::test_inventory_connection_headroom_max_concurrent_connections_constant_is_pinned`, `::test_inventory_connection_headroom_aggregate_overflow_is_blocked`, `::test_inventory_connection_headroom_spy_measured_concurrency_stays_at_or_below_the_constant`.
- item (6)'s runtime-settings half and its own role set: `::test_inventory_ddl_lock_is_confirmed_without_lock_timeout_declared`, `::test_inventory_ddl_lock_is_unknown_when_statement_timeout_not_declared`, `::test_inventory_ddl_lock_target_roles_include_auditreader`, `::test_inventory_ddl_lock_target_roles_include_application_roles`, `::test_inventory_ddl_lock_minus_one_connection_limit_is_unknown`, `::test_inventory_ddl_lock_ignores_a_per_database_scoped_setting`.
- `ops inventory` item (6) reads the value 0013 sets: `MitateDB-api/tests/test_ops_inventory.py::test_inventory_ddl_lock_is_confirmed_by_default_bootstrap_alone`, `::test_inventory_ddl_lock_confirmed_after_0013_is_applied`, `::test_inventory_ddl_lock_is_blocked_when_statement_timeout_is_zero`, `::test_inventory_ddl_lock_is_blocked_when_statement_timeout_is_negative`, `::test_inventory_ddl_lock_is_blocked_when_statement_timeout_is_unparseable`, `::test_inventory_ddl_lock_is_blocked_when_only_the_application_runtime_role_is_unbounded`, `::test_inventory_ddl_lock_is_blocked_when_only_the_application_developer_role_is_unbounded`, `::test_inventory_ddl_lock_blocked_outranks_unknown_when_mixed_with_an_undeclared_role`, `::test_inventory_ddl_lock_minus_one_and_zero_statement_timeout_mixture_is_unknown`, `::test_inventory_exit_code_is_2_when_ddl_lock_is_blocked`, `::test_inventory_ddl_lock_key_set_is_the_same_on_the_psycopg_error_path`.
- the CLI/key-set/`unjudged_items` static pins: `::test_inventory_numeric_arguments_reject_zero_and_negative`, `::test_inventory_reserved_connections_accepts_zero_but_rejects_negative`, `::test_inventory_top_level_and_item_keys_are_pinned`, `::test_inventory_unjudged_parts_vocabulary_is_pinned`, `::test_inventory_exit_code_is_0_when_every_judged_item_is_confirmed`.
- the rollout arithmetic and the three stray-re-application states: `MitateDB-api/tests/test_ops_inventory.py::test_inventory_connection_headroom_rollout_two_processes_confirmed_three_processes_blocked`, `::test_inventory_connection_headroom_catches_0012_reapplied_alone_after_0014`, `::test_inventory_connection_headroom_catches_0013_reapplied_alone_after_0014_when_a_new_application_exists`, and the disclosed gap `::test_inventory_connection_headroom_misses_0013_reapplied_alone_after_0014_with_no_new_application`.

#### Status

- **Disclosed scope limit of item (8)'s second condition**: raising a `CONNECTION LIMIT` adds no capacity, so condition 2 (total demand + reserved <= `max_connections`) is untouched by 0014; the total it computes adds every application's own role demand once rather than once per registered application, so it is not the physical worst case; and what an operator does when a cluster's `max_connections` does not cover the rollout total is not decided yet.

### MitateDB-api -- capacity and concurrency

#### Control

- **Phase 10 (WP-4/WP-6/WP-8, 2026-09-10), peer-symmetric with r2db-api's own entry**: (a) the same `process_ceilings` declaration row and the same `limit_enforcement` mapping (ceiling 1 -> `enforced`, ceiling >= 2 -> `deployment_required`, per plane, request-scoped and DB-side-bound classes unaffected), read from the declaration table alone -- `MitateDB-api/tests/test_process_ceilings_declaration.py::test_ceiling_one_maps_data_plane_in_memory_classes_to_enforced`, `::test_ceiling_two_maps_data_plane_in_memory_classes_to_deployment_required`, `::test_ceiling_one_maps_control_plane_in_memory_classes_to_enforced`, `::test_ceiling_two_maps_control_plane_in_memory_classes_to_deployment_required`, `::test_region_i_classes_are_unaffected_by_ceiling`, `::test_declaration_table_is_the_only_source`, and through a real composition root with an asymmetric declaration `::test_ceiling_asymmetric_declaration_maps_through_a_real_composition_root_data_plane`;
- a missing row fails startup fast on both planes and F-15 exits 14 -- `::test_missing_row_fails_fast_at_startup_data_plane`, `::test_missing_row_fails_fast_at_startup_control_plane`, `::test_verify_declarations_f15_exit_code`.
- (b) `applications`/`credentials_per_application` are bounded in the database by the same-named `_take_bound_advisory_lock` helper (`MitateDB-api/src/mitatedb_api/control_plane.py`, same `pg_advisory_xact_lock(hashtext('<schema>.<table>'))` derivation, pinned textually isomorphic to r2db-api's own by `_ISOMORPHIC_TARGETS`) -- `::test_db_side_bounds_hold_under_concurrent_writers_applications`, `::test_db_side_bounds_hold_under_concurrent_writers_credentials_per_application`, `::test_db_side_lock_holds_under_barrier_synchronized_two_writers_applications`, `::test_db_side_lock_holds_under_barrier_synchronized_two_writers_credentials_per_application`.
- (c) `role_pool_size(config) == config.max_concurrency` (`MitateDB-api/src/mitatedb_api/config.py`) is the platform pool's default in `main.build_app`;
- this peer's per-application `PostgresBackend` pools nothing, so it has no per-application counterpart -- `MitateDB-api/tests/test_threadpool_offload.py::test_platform_pool_sized_to_declared_concurrency_avoids_premature_503`;
- `MitateDB-api/migrations/0012_role_connection_limits.sql` and F-16 are the same control as r2db-api's own `0013_role_connection_limits.sql` (a role's ceiling is that role's own pool composition plus one 4-connection operator margin, F-16's floor is that role's own SINGLE-process pool on both peers, exit code 15, startup fail-fast) -- `MitateDB-api/tests/test_ops_verify_declarations.py::test_verify_declarations_f16_passes_after_migration_0012`, `::test_verify_declarations_f16_fails_when_a_role_connection_limit_is_lowered_below_its_pool_composition_floor`, `::test_f16_floor_for_a_role_matching_multiple_classes_is_the_max_not_the_last_assigned`, `::test_f16_the_schema_owning_role_is_never_flagged_even_though_it_matches_every_class`, `::test_0012_migration_tolerates_a_registered_only_application_and_still_raises_a_provisioned_applications_role_limits`, `MitateDB-api/tests/test_application_audit.py::test_build_app_fails_fast_when_its_own_api_role_connection_limit_is_lowered_below_the_pool_composition_floor`, `MitateDB-api/tests/test_control_main.py::test_build_control_app_fails_fast_when_its_own_controlplane_role_connection_limit_is_lowered_below_the_pool_composition_floor`.
- **`0014_role_connection_limits_rollout.sql`**: the two peers' CEILINGS are no longer the same arithmetic -- a rollout window on this peer runs two revisions of the same service side by side, so each ceiling becomes `2 x (that role's own one-process pool) + 4`: `mitatedbsvc_api` 68 -> 132, `mitatedbsvc_controlplane` 20 -> 36, every application's own runtime/developer role 36 -> 68, and `mitatedbsvc_auditreader` 5 -> 12 (the one role 0012 deliberately left alone, since 5 covered a single process's own 4). Whether r2db-api's own deployment ever runs two processes of the same plane side by side is NOT verified, so this is a still-unverified asymmetry between the peers rather than an accepted one (ledger item R-52, still open);
- the operator margin stays ONE 4, not a doubled one, and F-16's floor is deliberately not doubled with the ceiling -- F-16 judges only the pool held by the process it runs in, which is why a ceiling lowered back to a single process's demand still passes it (that is exactly what `MitateDB-api/tests/test_ops_verify_declarations.py::test_verify_declarations_f16_passes_after_migration_0012` fixes) and is read only by `ops inventory` item (8) -- `MitateDB-api/tests/test_ops_apply_platform_migration.py::test_apply_platform_migration_0014_sets_role_connection_limits_for_every_role_class`, `::test_apply_platform_migration_0014_new_application_connection_limit_is_68`, `::test_apply_platform_migration_0014_duplicate_object_fallback_connection_limit_is_68`.
- (d) The same pre-authentication `concurrency` slot and the same HTTP-plane order (byte bound -> concurrency slot -> authentication -> body -> rate/business).
- `HttpService` is fail-closed here: its constructor raises unless BOTH the shared `_LimitStateHolder` and the declared `max_concurrency` are supplied (`MitateDB-api/src/mitatedb_api/http.py`; the former no-op branch is removed, so a miswired composition cannot serve unbounded), and the composition root's own wiring is pinned by `MitateDB-api/tests/test_main.py::test_build_app_wires_the_preauth_concurrency_slot`.
- One holder is shared by every application in the process, so the bound is deployment-wide, not per-application -- `MitateDB-api/tests/test_application_plane_limits.py::test_limit_holder_is_shared_across_applications_in_one_process`, `MitateDB-api/tests/test_preauth_concurrency_bound.py::test_unauthenticated_flood_is_bounded_by_concurrency`, `::test_http_plane_denies_concurrency_before_requests_per_minute`, `::test_concurrency_hold_spans_the_gap_between_authentication_and_dispatch`, `::test_slot_is_released_after_a_401_ending_request`, `::test_slot_is_released_after_a_validation_failed_ending_request`, `::test_concurrency_slot_is_acquired_exactly_once_per_handler`.
- (e) Handlers delegate the synchronous section to the threadpool, and `ApplicationCell._lock` now covers the WHOLE lookup -> pass-1 -> pass-2 sequence inside that slot (the separate `_idempotency_lock_scope` helper is gone: the outer cell lock is the in-process serializer, `_idempotency_pg_scope` the cross-process one).
- That lock is per `ApplicationCell`, so requests against the SAME application serialize while different applications hold different locks -- `MitateDB-api/tests/test_threadpool_offload.py::test_pass1_and_pass2_serialize_through_cell_lock_no_developer_connection_race`, `::test_sync_section_runs_off_the_event_loop`, `::test_post_query_sync_section_runs_off_the_event_loop`, `::test_post_mutate_sync_section_runs_off_the_event_loop`, `::test_post_cross_entity_mutate_sync_section_runs_off_the_event_loop`, `::test_control_post_issue_credential_sync_section_runs_off_the_event_loop`, `::test_body_read_stays_on_the_loop`, `::test_limiter_state_is_thread_safe`, `::test_pool_acquire_is_thread_safe`, `::test_concurrency_slot_check_then_increment_is_inside_the_active_lock`, and the concurrent same-key idempotency forms `MitateDB-api/tests/test_idempotency_concurrency.py::test_memory_same_key_same_digest_concurrent_executes_exactly_once`, `::test_postgres_same_key_same_digest_concurrent_executes_exactly_once`.

#### Evidence

- —

#### Status

- —

### Common

#### Control

- —

#### Evidence

- resource boundary tests;
- the three control-plane SI-08 classes' publish-and-enforce agreement is additionally covered by `conformance-tests/test_c14_authority_boundary.py`'s vector 5 (condition C-14) -- see the SI-00 row above for the adapter-state detail.
- `batch_entities`' publish-and-enforce agreement is additionally covered by `conformance-tests/test_c16_cross_entity_atomicity.py` (condition C-16, executable on all four adapters -- see the SI-11 row below).
- **Phase 10 (2026-09-10)**: two real-socket plugs (`r2db-api-socket`/`MitateDB-api-socket`: a separate uvicorn process behind a real nginx) join the registry, so C-05's V2 vector is driven over a real wire as well as in process -- `conformance-tests/test_c05_limit_declaration_agreement.py::test_c05_v2_declaration_and_position_agree` drives `concurrency` through the port's own `hold_in_flight` on every registered plug, and what decides whether a plug's own readiness probe already consumed a unit of the bound is `adapter.transport_kind`, never the adapter's name -- `::test_c05_l7_21_v2_drivers_do_not_gate_drive_or_not_on_peer_name`, `::test_c05_all_plug_names_match_the_registry`, `conformance-tests/test_socket_harness.py::test_every_registered_adapter_declares_transport_kind`.
- The declared `process_ceilings` value is additionally observed against a REAL deployment by condition C-26: a restart between ceiling 1 and ceiling 2, started from each peer's own documented composition root, exhibits the `limit_enforcement` mapping those ceilings imply on both planes -- `conformance-tests/test_c26_composition_root.py::test_c26_ceiling_maps_to_limit_enforcement`, with `::test_c26_missing_declaration_fails_fast` (F-15) and `::test_c26_role_connection_limit_below_pool_floor_fails_fast` (F-16) as the two fail-fast halves.

#### Status

- **Disclosed limits, carried from the C-05 and C-26 rows of `conformance-tests/CONDITIONS.md`**: this suite still cannot distinguish a deployment-wide counter from a credential-scoped one;
- `execution_ms`/`idempotency_retention_ms` are never driven;
- and C-26 starts exactly ONE process per declared base URL, so agreement between a declared ceiling and a deployment's real process count rests on runbook discipline and the post-deployment check, not on this evidence.

## SI-09 Controlled Destructive Operations

[history](CONTROL_MAPPING_HISTORY.md#si-09)

### r2db-api

#### Control

- `structured.py` requires operation-specific confirmation for delete/drop, including `drop_index` (CCR-13 R-5: dropping a declared unique index is effectively irreversible once duplicate data has entered, treated as schema deletion like `drop_entity`);
- the check runs before any revision-precondition evaluation on `update`/`delete` (R-4, failure-before-execution) -- `test_atomic_rollback_and_explicit_destructive_operation`, `test_drop_index_requires_destructive_confirmation`.
- Phrase construction for all 4 gated surfaces (`delete`/`drop_entity`/`drop_index`, `revoke_credential`'s last-control-credential gate, and the ritual CLI's `reset`/`delete-credential`) is defined exactly once in the shared module `structured.py`, imported by both `control_plane.py` and `ops.py` rather than reimplemented -- fixed by an object-identity assertion, `test_cli_phrases_share_the_structured_module_with_data_and_control_plane_phrases`.
- All 6 data/schema call sites declare the same 4 machine-readable keys via `require_destructive_confirmation`'s `details` synthesis.
- The control-plane gate (`ControlPlaneService.revoke_credential`) determines "sole remaining enabled control credential" and performs the state change together, inside the SAME transaction (row-locked scan) -- closing the TOCTOU window a judgment made outside the open transaction would leave open -- `test_revoke_credential_gate_judgment_is_made_inside_the_open_transaction`, `test_control_credentials_locked_scan_serializes_against_a_concurrent_scan`.
- The out-of-band ritual CLI gates on the identical declare-and-echo protocol before any store/DSN is constructed, so a wrong `--confirm` never touches the database -- `test_cli_reset_without_confirm_declares_and_touches_nothing`, `test_cli_delete_credential_without_confirm_declares_and_touches_nothing`.
- `destructive`/`confirm(ation)` are type-checked (non-`bool`/non-`str` refused `VALIDATION_FAILED` before the confirmation check itself, never truthy-accepted) at all 4 gated surfaces, including over the real HTTP wire -- `test_delete_rejects_truthy_non_boolean_destructive_before_confirmation`, `test_revoke_last_control_credential_with_wire_truthy_non_boolean_destructive_is_validation_failed`.

#### Evidence

- —

#### Status

- —

### MitateDB-api

#### Control

- `delete` implements contract 1.2.0 declare-and-echo (`ApplicationCell.delete`; peer declares `contract_version=1.3.0`, unaffected by the later additive flip) -- a valid confirmation requires `destructive is True` AND `confirm` to exactly equal the server's recomputed `DELETE <collection> @where=<digest16>` phrase (SHA-256 of the canonically-serialized filter list, no state fingerprint needed since this peer has no drop/recreate path for a collection);
- a non-bool `destructive`/non-str `confirm` is refused as a shape defect, never truthy-accepted (`DestructiveConfirmationRequired` carries the contract's 4 keys, `reversible_alternative`/`recovery` both null -- no durable audit or soft-delete, mirrors r2db) -- `test_delete_without_confirmation_is_gated_not_conflated_with_empty_filters`, `test_delete_rejects_non_boolean_destructive_and_non_string_confirm`;
- `add_field`/schema-revision fingerprint: the `delete` phrase carries an `@schema_revision=<n>` fingerprint alongside `@where=<digest16>` (same reasoning as r2db -- once a second schema-changing operation exists, drop-then-recreate-under-the-same-name could leave a stale phrase valid) -- `test_canonical_where_json_key_sorts_each_filter_preserves_list_order_never_stringifies`.
- Control-plane `revoke_credential` last-active gate: gated exactly like r2db's -- target-set scan and state change happen inside the SAME transaction, closing the TOCTOU window -- `test_revoke_credential_confirmation_denial_is_durably_audited`, real-PostgreSQL `test_revoke_last_active_control_credential_gate_against_real_postgres`.
- Break-glass CLI: `revoke-credential` reuses this SAME gate rather than reimplementing it;
- `deprovision <application_id>` is this peer's own second genuinely destructive CLI subcommand (provisioning-level, against `MITATEDB_PROVISION_DSN`), gated by a NEW phrase fingerprinted on `applications.registered_at` (phrase must go stale across a deprovision-then-reregister cycle) -- `test_deprovision_without_confirm_declares_the_phrase_and_touches_nothing`, `test_deprovision_with_the_echoed_phrase_removes_the_registration`.
- **`ops inventory` (R-45 WP-B) never mutates platform state**: every connection it opens (the single factory `_inventory_connect`, never a bare `psycopg.connect` elsewhere in its own code) sets `default_transaction_read_only = on` immediately after connecting and reads the setting back rather than trusting it was applied -- read-only is a TOOL-SIDE property, not a privilege boundary (the connecting role can still write on a DIFFERENT connection);
- item (3)'s per-application ledger read survives `read_applied_upgrade_numbers`'s own `UndefinedTable`/`conn.rollback()` recovery path without losing its read-only setting or its two session timeouts (`autocommit=True`, never an open transaction a rollback could unwind);
- each connection also carries a fixed `lock_timeout`/`statement_timeout` (3000ms/5000ms) so a read cannot queue behind, or itself prolong, a concurrent migration/upgrade -- exceeding either leaves that item unknown, never confirmed;
- `cmd_inventory`'s own read-only readback (not merely `_inventory_connect`'s own internal `SET`) genuinely gates the whole run (a false readback fails the subcommand closed, never proceeds to build a report); item (3)'s own per-application connections are read-only the same way the platform connection is, confirmed by the SAME readback on each one;
- if any of `_inventory_connect`'s own three `SET` statements fails, the connection is closed before the exception propagates -- never leaked half-configured.

#### Evidence

- `test_c06_destructive_confirmation.py` exercises the full strict-branch vector set (V1-V5/V8; V6/V7 use the shared absence mechanism -- no `drop_entity`/control-plane surface here).
- `MitateDB-api/tests/test_ops_inventory.py::test_inventory_connections_reject_writes_outside_an_explicit_transaction`, `::test_inventory_application_connections_also_reject_writes`, `::test_inventory_application_connections_confirm_read_only`, `::test_inventory_confirms_read_only_by_reading_it_back`, `::test_inventory_ledger_absent_read_only_survives_the_internal_rollback`, `::test_inventory_all_opened_connections_go_through_the_factory`, `::test_inventory_never_calls_psycopg_connect_outside_its_own_factory`, `::test_inventory_connect_closes_the_connection_when_a_set_statement_fails`, `::test_inventory_tool_failure_when_read_only_cannot_be_confirmed`.
- `MitateDB-api/tests/test_ops_inventory.py::test_inventory_session_timeouts_are_actually_set`, `::test_inventory_session_timeout_constants_are_pinned`, `::test_inventory_credentials_lock_timeout_exceeded_is_unknown`.

#### Status

- —

### MitateDB-api -- platform upgrade

#### Control

- **`apply-platform-migration` (R-45 WP-E; R-57 WP-1 accepts a run of one or more FILENAMEs)**: applies each of one or more platform migration files, in the fixed pinned order (0005/0007/0011/0012/0013/0014 only, never the bootstrap-only 0001/0002), against `MITATEDB_PROVISION_DSN`; each FILENAME is a bare name (no path separator), matched against that pinned enumeration, and resolved (both the migrations directory and the candidate file, symlinks followed) to confirm it stays inside the migrations directory before any psql subprocess starts -- a rejected value is never echoed;
- a run is refused (no psql subprocess started) unless every given FILENAME is strictly ascending in that pinned order with no repeat, and, for every file with a later-accepted file that redefines one of its own targets (a role/function's own `CONNECTION LIMIT`, a role-level `SET` parameter, or a `CREATE OR REPLACE FUNCTION` body -- the target-level map design D-3 derives statically from the 6 files themselves and proves equal, folded to file granularity, to the constant this check reads), every one of those later files is present too, later in the same call -- the rejection names the required run, never the operator's own given values -- `MitateDB-api/tests/test_ops_apply_platform_migration.py::test_apply_platform_migration_out_of_order_run_is_rejected`, `::test_apply_platform_migration_duplicate_filename_in_run_is_rejected`, `::test_apply_platform_migration_solo_0012_is_rejected_with_the_confirmed_closure_message`, `::test_apply_platform_migration_0012_0014_without_0013_is_rejected`, `::test_platform_migration_target_map_contains_the_4_known_targets`, `::test_platform_migration_superseded_by_equals_the_target_map_folded_to_file_level`;
- only the FILENAMEs the operator explicitly listed are ever started -- an omitted successor is never added automatically -- and each accepted file still runs through its own separate psql invocation, in the given order, so a mid-run psql failure stops before any later file starts and reports which files applied, which did not run, and that the whole run must be re-run from its first file, never the failed file alone -- `::test_apply_platform_migration_run_never_starts_a_file_the_operator_did_not_list`, `::test_apply_platform_migration_never_starts_a_files_own_successor_the_operator_omitted`, `::test_apply_platform_migration_run_stops_at_the_failing_file_with_the_confirmed_t3_message`, `::test_apply_platform_migration_run_of_0012_0013_0014_leaves_the_newest_values` (real PostgreSQL), `::test_apply_platform_migration_run_reversed_order_leaves_the_oldest_values` (real PostgreSQL);
- DSN is environment-only (no CLI argument, design Z-8/D-10), `ON_ERROR_STOP=1`, a required no-default `--lock-timeout` reaching psql via `PGOPTIONS` (`_with_lock_timeout_option`, the SAME helper `upgrade-applications`/`deprovision` use), and psql's own captured output is redacted before any failure message reaches stderr;
- per-file psql variables (0007's own `:api_role`/`:controlplane_role`) are a static table matched against each file's own real `:name` references (excluding `--` comments and `::` casts); a table entry the operator omits, or an argument the table does not list, is refused before any subprocess starts;
- the AST-derived set of subcommands that flow a migration file through psql (`apply-platform-migration`/`upgrade-applications`/`deprovision`) is exactly the set whose own `--lock-timeout` is a required, no-default argument -- `set-platform-timeouts`/`declare-*` (psycopg-only configuration writes) are never in it;
- against production, `apply-platform-migration` is run only through the runbook's gated procedure (`MitateDB-api/docs/cloud-run-cloud-sql.md` section 10), whose stage 2 preconditions this block's own Platform-upgrade runbook claim below states rather than this claim restating a subset of them -- the subcommand's own help text, section-heading comment and docstring name that same section too, pinned by `MitateDB-api/tests/test_ops_help_text.py`; every test targets a throwaway PostgreSQL cluster only (`MITATEDB_TEST_ADMIN_DSN`).
- **`0013_role_statement_timeouts.sql` (R-45 WP-F)**: sets a role-level `statement_timeout` on `mitatedbsvc_auditreader` and on every application's own runtime/developer role, both retroactively (already-provisioned roles, inside one transaction -- a permission failure partway rolls back the whole file, no half-applied state) and going forward (`begin_provision_application`'s own `CREATE OR REPLACE`, both the `CREATE ROLE` branch and its `duplicate_object` fallback);
- a registry row naming a role `pg_roles` no longer carries is skipped rather than aborting the migration; must run after 0012 (both `CREATE OR REPLACE` the identical function -- 0012 alone afterward drops the setting for FUTURE applications only, and, now that `0014_role_connection_limits_rollout.sql` replaces that same function last, a stray 0012 additionally lowers every EXISTING role's own `CONNECTION LIMIT` back to 0012's own values; either stray is corrected by re-applying the set in its own order and ending at `apply-platform-migration 0014`, never by 0013 alone, which would leave the next application's roles at 36); applying 0013 requires ADMIN OPTION on `mitatedbsvc_auditreader` (PostgreSQL 16's own CREATEROLE rule), refused rather than bypassed when absent.
- **`0014_role_connection_limits_rollout.sql`**: applies the raised ceilings `SI-08`'s `MitateDB-api` `capacity and concurrency` block states, retroactively (already-provisioned runtime/developer roles, a registry row whose role `pg_roles` no longer carries skipped rather than aborting the file) and going forward (`begin_provision_application`'s own `CREATE OR REPLACE`, both the `CREATE ROLE` branch and its `duplicate_object` fallback), the WHOLE file inside one transaction so a permission failure partway leaves nothing changed rather than a half-applied state;
- it is the third and last file to replace that function, so it runs after 0012 and 0013 and its own replacement keeps 0013's `statement_timeout` lines unchanged; its header overwrites, rather than erases, 0012's own statement that `mitatedbsvc_auditreader` is deliberately left untouched (true for one process, not for two); ADMIN OPTION on every role it alters is required exactly as 0013 requires it, refused rather than bypassed -- `MitateDB-api/tests/test_ops_apply_platform_migration.py::test_apply_platform_migration_0014_preserves_0013_statement_timeout_on_provisioned_roles`, `::test_apply_platform_migration_0014_is_transactional_and_rolls_back_on_permission_failure`, `::test_apply_platform_migration_0014_survives_a_registry_role_dropped_before_it_runs`, `::test_apply_platform_migration_accepts_0014_via_the_subcommand`.
- **Platform-upgrade runbook (R-45 WP-D)**: `MitateDB-api/docs/cloud-run-cloud-sql.md` section 10 is the operator procedure for the Gate-0 read and the platform upgrade, in four stages -- first read, platform remediation, second read, candidate -- of which only the remediation and the candidate stage change production state (a read performs no DDL, no DML, no declaration replacement, no restart, no traffic change, no API enablement); Gate-0 is ready only when all 10 items are confirmed AND section 10.8's acceptance records name the current versions (`ops inventory`'s own exit status 0 never makes it ready), and what ready gates is exactly the candidate deploy and the traffic switch onto it; against production, the isolated proof, the independent audit and the requester's approval all come before anything in either state-changing stage runs -- the candidate stage, which ready gates as well, and the remediation stage, which ready does not gate -- including the remediation stage's own single move of traffic percentages, onto the env-only revision that runs the same image digest as the revision it replaces, and the removal of a tag that keeps a Data revision out of the concurrency agreement (no percentage moves, but it is the same traffic projection and carries the same three conditions);
- before that stage changes anything, item (8)'s connection-demand arithmetic is computed on paper from the inputs the second read will pass and the limits in force at that read (0012's own value for a role it names, the catalog value for every other role), and a role whose `CONNECTION LIMIT` sits below its own demand is reported and stopped on rather than remediated here (raising such a limit takes a new platform migration, since 0012 sets fixed values and never touches the auditreader's or the provision role's own limit);
- an `unknown` that survives the second read stops the procedure and is never carried forward as a warning; item (5) and item (6)'s lock/downtime half are judged by that independent-review acceptance record, matching `inventory`'s own `unjudged_items`/`runbook-acceptance`; platform migrations are applied only as one numbered set (0005/0007/0011/0012/0013/0014) through `apply-platform-migration` with its required `--lock-timeout`, never one file out of order (0012, 0013 and 0014 all `CREATE OR REPLACE` the same function, in that order; 0013 and 0014 both name the role 0005 creates), re-applying 0007/0012 is idempotent but not value-neutral (the runbook records the writer-role timeouts, the `audit_writer_roles` row and the current `CONNECTION LIMIT`s first, and restores the two timeouts and that row -- the `CONNECTION LIMIT`s are recorded only, never restored, since 0012 sets each role it names to its own value, raising a lower limit and lowering a higher one, and 0014 sets its own four values the same way), and section 10.10 states the ADMIN OPTION prerequisite the `ALTER ROLE` statements in 0007/0012/0013/0014 share together with the single explicit `GRANT` that repairs a cluster lacking it.

#### Evidence

- `MitateDB-api/tests/test_ops_apply_platform_migration.py` (75 tests: filename validation, the psql-variable table (quoted-form-only reference, no bare `:name`), DSN-via-environment, redaction, drift-then-restore for 5 of the 6 accepted files (0005/0007/0011/0012/0013), 0013's and 0014's own retroactive/forward-provisioning/transactional/skip-missing-role/permission-failure coverage, 0014's own preservation of the setting 0013 adds, the AST-derived DDL-flowing-subcommand and psql-file-launching-function sets, and, since R-57 WP-1, a run of 1+ FILENAMEs' own order/duplicate/closure acceptance, the target-level map D-3 derives, explicit-files-only and mid-run-stop rejection, and real-PostgreSQL run-ordering coverage) and `MitateDB-api/tests/test_platform_migration_reapply.py::test_0007_0011_0012_reapplication_is_idempotent_from_every_starting_prefix` (also covers 0005/0013/0014; re-application routed through `apply-platform-migration` with drift-then-restore, replacing the earlier bare-psql re-application).
- Runbook acceptance for the section 10.6 table (version 4), the section 10.7 table (version 4) and the section 10.10 procedure (version 7): the acceptance record in `MitateDB-api/docs/cloud-run-cloud-sql.md` section 10.8 (conclusion, version reviewed, where the review is recorded, date accepted). Sections 10.6 and 10.10 moved to versions 4 and 7 in this change set -- following `apply-platform-migration` accepting a run of FILENAMEs and refusing a solo `0012`/`0013` application that has a later file redefining its own targets -- and were accepted at those versions by an independent review of 2026-09-20; section 10.7 is unchanged at version 4, since this change set touches only prose outside its own table (the `apply-platform-migration` line under "How the table's values are passed"), never one of the table's own rows. This claim carries no mutation of its own -- it is an audit correspondence, and its verbatim collation record is `docs/work-orders/WORK_ORDER_R57_PLATFORM_MIGRATION_RUN_V1.md` section 5 for sections 10.6 and 10.10, and `docs/work-orders/WORK_ORDER_R54_DEPROVISION_LIVE_CONNECTIONS_V1.md` section 5 for section 10.7's own version 4, each named by the matching row of section 10.8.

#### Status

- Section 10's three reviewed subjects stand at these versions -- the 10.6 table at 4, the 10.7 table at 4, the 10.10 procedure at 7 -- and each stays a draft until section 10.8's own row names that same version for it; section 10.8 is the single place that state is read from, and a row naming an earlier version counts as no record at all. As of this version of this file, nothing in section 10 has been run against production, and neither `0014_role_connection_limits_rollout.sql`, the `0004` stages R-54 adds, nor the run/closure behavior R-57 adds has been applied to production either -- every value and every judgment above was measured on a throwaway test cluster.

### Common

#### Control

- —

#### Evidence

- destructive misuse tests;
- CCR-13's destructive-confirmation-before-precondition ordering is additionally covered by `conformance-tests/test_c18_revision_precondition_semantics.py` (condition C-18, executable on all four adapters).
- Q-1's declare-and-echo protocol itself (contract 1.2.0) has its own dedicated common suite, `conformance-tests/test_c06_destructive_confirmation.py` (condition C-06, executable four adapters -- `r2db-api`, `r2db-api-http`, `MitateDB-api`, `MitateDB-api-http`): all four registered adapters declare `contract_version >= 1.2.0` and take the strict branch (vectors V1-V8: unconfirmed-denial, full-match adversarial checks, phrase determinism, probe-then-echo, state-fingerprint invalidation, the in-band last-control-credential revoke gate, and payload-echo absence) for real;

#### Status

- the baseline (<1.2.0) branch is retained, deliberately unremoved, as a disclosed and currently-unexercised acceptance floor for any future <1.2.0 peer (`conformance-tests/CONDITIONS.md` C-06 row).

## SI-10 Error/Information Non-Disclosure

[history](CONTROL_MAPPING_HISTORY.md#si-10)

### r2db-api

#### Control

- `FoundationError` emits a safe problem shape;
- no internal exception is serialized;
- `r2db-api/src/r2db_api/http.py` renders every `FoundationError` as `application/problem+json` and collapses any uncaught exception (Starlette routing, or a `PostgresCell`/psycopg failure) to a generic `SERVICE_UNAVAILABLE` with a static message, deliberately discarding the real exception rather than interpolating or logging it at this layer (`_generic_service_unavailable`);
- `r2db-api/src/r2db_api/postgres.py` itself maps `psycopg.Error` to that same generic denial rather than letting a driver error/message reach the caller.
- Under the Q4 design (`docs/design/Q4_DB_SIDE_SINGLE_TRUTH_V1.md` §3.8), exactly one fail-fast message reaches a client and it carries no configuration state: F-1..F-11/F-3c/F-13 are startup-time output only (they may quote a declared value, a role name, or a DSN env-var NAME, so they are never copied onto a readiness/health surface), while F-12 alone is raised at cell-open time and becomes an API response -- `PostgresCell.verify_platform_upgrades_applied` re-raises `platform_upgrades.PlatformUpgradeError` as a `FoundationError("SERVICE_UNAVAILABLE", str(exc))`, and `platform_upgrades._f12_message` is built from the missing upgrade numbers, the application id, and the `ops upgrade-applications` command only -- no DSN, credential, internal hostname, or declared value.
- The out-of-band `ops` CLI's `cmd_verify_declarations` and top-level `main()` never print a raw exception string on a connection/database failure -- only the caught exception's own type name plus a fixed message.
- `cmd_upgrade_applications`'s own `failure_detail` has every DSN element (`user`/`password`/`host`/`hostaddr`/`port`/`dbname`, `host`/`hostaddr`/`port` split on `,` first for a multi-host DSN) redacted via `_redact_connection_values` -- one regular expression, longest value first, in a single pass, so a shorter value that is a literal prefix of a longer one cannot leave the longer value's own tail exposed. Every psql subprocess invocation passes its connection parameters through libpq's own environment variables via `_psql_connection_env`, never on argv; the child's environment is built by first stripping every parent `PG*` variable, then setting only the 33 libpq (PostgreSQL 16) keys with a documented environment-variable form (local `libpq-envars` documentation, "Environment Variables", connection-parameter group) -- a DSN key outside that set ends the run via `_die`, naming the key but never its value.
- Fail-closed on a connection-setting variable the parent process still carries but the DSN itself never overrides (the allow-list's own values, plus `PGSERVICEFILE`/`PGSYSCONFDIR`): `_die` names the variable, never its value, rather than let the psql child silently inherit a setting from this process' own environment. Every psql subprocess invocation is preceded by `_require_psql_16_or_newer`, which reads `psql --version` and `_die`s (fixed text) if the binary cannot be started at all, the major version is below 16, or the output cannot be parsed.

#### Evidence

- malformed/deep/cyclic input tests verify structured safe failures;
- audit tests check secret absence.
- Exercised locally by `r2db-api/tests/test_http.py` and `test_postgres.py`;
- Evidence: `r2db-api/tests/test_platform_upgrade_ledger_scan.py::test_f12_message_matches_design_section_3_8_verbatim`, `r2db-api/tests/test_postgres.py::test_verify_platform_upgrades_applied_raises_service_unavailable_when_a_number_is_missing`, `::test_verify_platform_upgrades_applied_raises_when_the_ledger_table_is_entirely_absent`, `r2db-api/tests/test_application_audit.py::test_build_app_h1_logs_the_f12_message_verbatim_at_cell_open_time`.
- Evidence: `r2db-api/tests/test_ops_verify_declarations.py::test_verify_declarations_connect_failure_never_prints_the_raw_exception_text`, `::test_main_psycopg_error_handler_never_prints_the_raw_exception_text`, `::test_main_catches_non_psycopg_exceptions_without_a_traceback`; `r2db-api/tests/test_ops_upgrade.py::test_run_upgrade_script_passes_connection_params_via_env_never_argv`, `::test_cmd_upgrade_applications_redacts_connection_values_from_a_failed_psql_output`, `::test_redact_connection_values_leaves_unrelated_text_untouched`, `::test_redact_connection_values_handles_prefix_overlap_and_multi_host_dsn`, `::test_psql_connection_env_rejects_a_dsn_key_with_no_libpq_env_var_form`, `::test_psql_connection_env_accepts_new_allow_listed_keys`.
- Evidence: `r2db-api/tests/test_ops_upgrade.py::test_psql_connection_env_strips_parent_pg_star_vars`, `::test_psql_connection_env_rejects_a_parent_connection_var_the_dsn_does_not_override`, `::test_psql_connection_env_accepts_when_dsn_overrides_the_parent_connection_var`, `::test_psql_connection_env_rejects_a_parent_pgservicefile_the_dsn_can_never_override`, `::test_psql_connection_env_rejects_a_parent_pgsysconfdir_the_dsn_can_never_override`, `::test_require_psql_16_or_newer_rejects_an_older_or_unparseable_version`, `::test_require_psql_16_or_newer_rejects_unparseable_output`, `::test_require_psql_16_or_newer_accepts_16`, `::test_require_psql_16_or_newer_rejects_when_the_binary_is_not_found`, `::test_run_upgrade_script_calls_the_psql_version_gate_first`.

#### Status

- production log/observability handling of the discarded exception is not yet defined or evidenced.

### MitateDB-api

#### Control

- Application-plane HTTP: `http.py` renders every `FoundationError` as `application/problem+json` and collapses any uncaught exception (routing, a `backend_postgres`/psycopg failure) to a generic `SERVICE_UNAVAILABLE` with a static message, discarding the real exception rather than logging/interpolating it here -- `test_problem_response_never_leaks_the_underlying_exception_message`, `test_authorization_state_unavailable_is_reported`.
- Control-plane HTTP: `control_http.py` reuses the same generic-collapse pattern with its own error-classification table, exercised end-to-end including a dedicated negative test that injects a raw `RuntimeError` (secret-shaped marker) into the authentication path and asserts the marker is absent from the entire response body -- `test_control_problem_response_never_leaks_the_underlying_exception_message`.
- **Intended operational visibility, not a disclosure gap**: `list_credentials` is readable by the strictly weaker `audit` role (SI-02/SI-06), so a distributable, ceremony-issued `audit` credential can enumerate `must_rotate`/`enabled`/`revoked` state for every control credential, not only its own -- deliberate, not a regression: `CredentialsResult`'s "never returns secrets or verifiers" applies identically regardless of role (same schema-exactness assertions as SI-12), and the point of a weaker distributable role is observing rotation/enable/revoke state without being able to change anything (SI-02's fail-closed enumeration keeps it read-only).
- Under Q4, this peer narrows the same carve-out by TYPE, not by code: the problem-body builder replaces every other error's message with a fixed generic string;
- the sole exception is `isinstance(exc, PlatformUpgradePending)` (a dedicated subclass, not the classified `SERVICE_UNAVAILABLE` code every other storage-configuration failure maps to), so the carve-out cannot silently widen to a future error site.
- The surfaced text is the same fixed F-12 message (missing upgrade numbers + the `ops upgrade-applications` command, nothing else) -- `test_f12_message_matches_design_section_3_8_verbatim`, `test_build_app_h1_serves_every_application_and_refuses_only_the_one_with_a_pending_upgrade`.
- The out-of-band `ops` CLI's `cmd_verify_declarations` and top-level `main()` never print a raw exception string on a connection/database failure -- only the caught exception's own type name plus a fixed message.
- `_upgrade_one_application`'s own `failure_detail` and `_run_deprovision_script`'s own `_die` message (this peer's only psql-based deprovision path) have every DSN element (`user`/`password`/`host`/`hostaddr`/`port`/`dbname`, `host`/`hostaddr`/`port` split on `,` first for a multi-host DSN) redacted via `_redact_connection_values` -- one regular expression, longest value first, in a single pass, so a shorter value that is a literal prefix of a longer one cannot leave the longer value's own tail exposed. Every psql subprocess invocation passes its connection parameters through libpq's own environment variables via `_psql_connection_env`, never on argv; the child's environment is built by first stripping every parent `PG*` variable, then setting only the 33 libpq (PostgreSQL 16) keys with a documented environment-variable form (local `libpq-envars` documentation, "Environment Variables", connection-parameter group) -- a DSN key outside that set ends the run via `_die`, naming the key but never its value.
- Fail-closed on a connection-setting variable the parent process still carries but the DSN itself never overrides (the allow-list's own values, plus `PGSERVICEFILE`/`PGSYSCONFDIR`): `_die` names the variable, never its value, rather than let the psql child silently inherit a setting from this process' own environment. Every psql subprocess invocation is preceded by `_require_psql_16_or_newer`, which reads `psql --version` and `_die`s (fixed text) if the binary cannot be started at all, the major version is below 16, or the output cannot be parsed.
- **`ops inventory` (R-45 WP-B)** never formats an exception's own text into its output at all -- every item's own failure path returns a fixed judgment word (`confirmed`/`blocked`/`unknown`), a fixed reason word (`ledger-unreadable`/`declaration-invalid`, closed vocabulary) or `match`/`mismatch`/`unknown` for item (1), never `str(exc)`; a connection failure before any item can be read propagates uncaught to `main`'s own existing top-level handler (type name and fixed text only, unchanged by this WP);
- item (2)'s own declaration read distinguishes an ABSENT declaration (table/row missing -- confirmed + remediation-required) from a PRESENT but hand-corrupted one (fails its own value validation -- blocked with the fixed reason `declaration-invalid`), never treating a corrupt value as equivalent to an absent one;
- item (4)'s credential-registry projection is an explicit column allow-list (`role`/`enabled`/`revoked`[/`must_rotate`]) -- `credential_id`/`digest` are never in the SELECT list regardless of what the connecting role can technically read (read-only is not a privilege boundary here, SI-09 above), and item (4) reports per-state counts (`enabled`/`revoked`/`must_rotate`) rather than a total alone;
- item (1) never emits the Cloud SQL connection name or the DSN's own unix-socket path, only the `match`/`mismatch`/`unknown` comparison result; item (1) also carries its own `judgment` (`match`->`confirmed`, `mismatch`->`blocked`, `unknown`->`unknown`), and `_inventory_exit_code` reads every item's `judgment` uniformly, item (1) included; the JSON output's top-level and per-item key sets are pinned (no `ready` key, no key for item (5): Gate-0's overall readiness AND item (5)/item (6)'s own declared half are runbook-level judgments this DB-layer-only subcommand never publishes -- named instead in the pinned `unjudged_items` list), and the judgment/comparison/reason/part vocabularies are all closed;
- `--concurrency`/`--data-process-count`/`--control-process-count` accept only a positive integer (0 refused); `--reserved-connections` accepts a non-negative integer (0 = no reserve, only negative refused) -- both forms are a usage error (argparse's own fixed, templated message) before any connection opens.

#### Evidence

- `MitateDB-api/tests/test_ops_inventory.py::test_inventory_success_route_never_leaks_user_or_password`, `::test_inventory_success_route_never_leaks_dbname`, `::test_inventory_connect_failure_host_never_leaks`, `::test_inventory_connect_failure_role_never_leaks`, `::test_inventory_connect_failure_database_never_leaks`, `::test_inventory_dsn_parse_failure_never_leaks`, `::test_inventory_post_connect_psycopg_exception_never_leaks`, `::test_inventory_non_psycopg_exception_is_caught_at_the_top_level_without_a_traceback`.
- `MitateDB-api/tests/test_ops_inventory.py::test_inventory_credentials_column_allowlist_excludes_secrets`, `::test_inventory_credentials_cursor_description_matches_the_allowlist`, `::test_inventory_credentials_query_never_selects_star_or_secret_columns`, `::test_inventory_credentials_permission_error_is_unknown`, `::test_inventory_credentials_per_state_counts`, `::test_inventory_credentials_never_output_credential_id_or_digest`.
- `MitateDB-api/tests/test_ops_inventory.py::test_inventory_declarations_missing_row_is_confirmed_with_remediation`, `::test_inventory_declarations_shape_violation_is_blocked`, `::test_inventory_declarations_connection_failure_is_unknown`, `::test_inventory_declarations_f15_missing_only_is_confirmed_with_remediation`, `::test_inventory_reason_vocabulary_is_pinned`, `::test_inventory_numeric_arguments_reject_zero_and_negative`.
- `MitateDB-api/tests/test_ops_inventory.py::test_inventory_connection_comparison_reports_a_mismatch`, `::test_inventory_connection_comparison_matches_the_real_socket_path`, `::test_inventory_connection_comparison_tcp_dsn_is_unknown`, `::test_inventory_connection_output_never_includes_the_socket_path_or_name`, `::test_inventory_does_not_accept_a_dsn_argument`, `::test_inventory_writes_nothing_but_stdout`, `::test_inventory_never_calls_psycopg_connect_outside_its_own_factory`.
- `MitateDB-api/tests/test_ops_inventory.py::test_inventory_top_level_and_item_keys_are_pinned`, `::test_inventory_judgment_vocabulary_is_closed`, `::test_inventory_never_reports_an_overall_ready_key`, `::test_inventory_exit_code_is_2_when_any_item_is_not_confirmed`, `::test_inventory_exit_code_is_0_when_every_judged_item_is_confirmed`, `::test_inventory_connection_judgment_drives_the_exit_code`, `::test_inventory_tool_failure_exit_code_is_1_with_fixed_text_only`, `::test_inventory_reports_every_db_layer_item_with_a_judgment`, `::test_inventory_migrations_r47_pre_fix_application_is_blocked_with_a_fixed_reason`.
- Evidence: `MitateDB-api/tests/test_ops_verify_declarations.py::test_verify_declarations_connect_failure_never_prints_the_raw_exception_text`, `::test_main_psycopg_error_handler_never_prints_the_raw_exception_text`, `::test_main_catches_non_psycopg_exceptions_without_a_traceback`; `MitateDB-api/tests/test_ops_upgrade.py::test_run_upgrade_script_passes_connection_params_via_env_never_argv`, `::test_run_deprovision_script_passes_connection_params_via_env_never_argv`, `::test_run_upgrade_script_redacts_connection_values_from_a_failed_psql_output`, `::test_run_deprovision_script_redacts_connection_values_before_dying`, `::test_redact_connection_values_leaves_unrelated_text_untouched`, `::test_upgrade_one_application_redacts_connection_values_on_connect_failure`, `::test_redact_connection_values_handles_prefix_overlap_and_multi_host_dsn`.
- Evidence: `MitateDB-api/tests/test_ops_upgrade.py::test_psql_connection_env_rejects_a_dsn_key_with_no_libpq_env_var_form`, `::test_psql_connection_env_accepts_new_allow_listed_keys`, `::test_psql_connection_env_strips_parent_pg_star_vars`, `::test_psql_connection_env_rejects_a_parent_connection_var_the_dsn_does_not_override`, `::test_psql_connection_env_accepts_when_dsn_overrides_the_parent_connection_var`, `::test_require_psql_16_or_newer_rejects_an_older_or_unparseable_version`, `::test_require_psql_16_or_newer_rejects_unparseable_output`, `::test_require_psql_16_or_newer_accepts_16`, `::test_require_psql_16_or_newer_rejects_when_the_binary_is_not_found`, `::test_psql_connection_env_rejects_a_parent_pgservicefile_the_dsn_can_never_override`, `::test_psql_connection_env_rejects_a_parent_pgsysconfdir_the_dsn_can_never_override`, `::test_run_upgrade_script_calls_the_psql_version_gate_first`, `::test_run_deprovision_script_calls_the_psql_version_gate_first`.

#### Status

- **Disclosed gap**: production log/observability handling of the discarded exception is not yet defined or evidenced for either plane.

### Common

#### Control

- —

#### Evidence

- error probing tests

#### Status

- —

## SI-11 Atomic Integrity

[history](CONTROL_MAPPING_HISTORY.md#si-11)

### r2db-api

#### Control

- `ApplicationCell.transact` snapshots and restores on failure;
- `r2db-api/src/r2db_api/postgres.py`'s `PostgresCell.transact` maps one HTTP request to one real PostgreSQL transaction (design D-5): every operation in a batch runs inside a single `conn.transaction()` block, and any exception -- including a `FoundationError` raised by a later operation in the batch -- rolls back the whole batch via PostgreSQL itself rather than an in-memory snapshot/restore;
- CCR-13 (`docs/design/R2DB_CCR13_STORAGE_V1.md` R-4) additionally makes an `expected_revision` precondition part of the same atomic unit -- the predicate and the revision comparison are combined into one `WHERE` clause of the single `UPDATE`/`DELETE` statement (`_r2db_revision::text = $expected`), never a separate read followed by a conditional write, so the compare-and-swap cannot race with a concurrent mutation of the same row.

#### Evidence

- `test_atomic_rollback_and_explicit_destructive_operation`;
- Exercised against a real local PostgreSQL 16 cluster by `r2db-api/tests/test_postgres.py`;

#### Status

- no production evidence.
- r2db's own `cross_entity_mutation` remains `unavailable` (P35-D1, `docs/design/PHASE35_CROSS_ENTITY_AND_CONTRACT_130_V1.md` §0) -- no cross-entity atomic unit exists on this peer to evidence.

### MitateDB-api

#### Control

- `ApplicationCell.transact` uses one local transaction with rollback on rejected operation -- `test_transaction_rolls_back`.
- Cross-entity atomic unit (design §2 R-1): `transact()` is a two-pass choke -- pass 1 (`_plan_operation`, side-effect-free) validates the WHOLE unit before pass 2 executes any of it, so a later operation's validation failure voids every earlier operation's effect too;
- shared by both single-entity and cross-entity call paths (no second implementation) -- `test_transact_two_pass_structure_zero_backend_calls_when_a_later_operation_fails_validation` (wrapped backend proving zero execution calls when a later op fails).
- Rollback on a pass-2 failure is unconditional regardless of exception type, with deterministic pre-execution rejection of lone UTF-16 surrogates in `encode_value` (both backends, same treatment as pre-existing NUL-byte rejection) -- `test_transact_lone_surrogate_value_is_deterministic_validation_failure_and_earlier_entity_unchanged`, `test_transact_rollback_is_unconditional_for_a_non_foundation_error_raised_mid_pass_2`.

#### Evidence

- The PostgreSQL-specific validate/execute pass-boundary window (pass 1 runs outside `self._lock`; a schema change could land between passes) is exercised by wrapping `begin()` and dropping the target table mid-window -- `test_transact_pass_boundary_schema_change_window_yields_not_found_and_sibling_entity_unchanged` (affected entity surfaces `NotFoundError`, a sibling entity in the same batch is left unchanged).
- Common-suite coverage: `test_c16_v1_two_entity_insert_commits_as_one_unit` (positive), `test_c16_v2_invalid_operation_on_one_entity_voids_the_whole_unit` (atomicity) -- MitateDB pair takes PROVIDED, r2db pair takes the documented ABSENT branch (SI-11's r2db-api cell above).

#### Status

- —

### Common

#### Control

- —

#### Evidence

- rollback/fault tests;
- CCR-13's revision-precondition atomicity/semantics are additionally covered by `conformance-tests/test_c18_revision_precondition_semantics.py` (condition C-18, executable on all four adapters).
- Cross-entity atomic-unit agreement (declared vs. observed, both entities voided together on a mixed-validity unit) is additionally covered by `conformance-tests/test_c16_cross_entity_atomicity.py` (condition C-16, executable on all four adapters -- vectors V1/V2 for the two PROVIDED MitateDB adapters, V5's evidence-form check for the two ABSENT r2db adapters)

#### Status

- —

## SI-12 No Data-Service Bypass

[history](CONTROL_MAPPING_HISTORY.md#si-12)

### r2db-api

#### Control

- Structured package has no credential/connection/native-command response;
- topology denies privileged egress;
- Under the Q4 design (`docs/design/Q4_DB_SIDE_SINGLE_TRUTH_V1.md` D-2/D-3, §3.9, requester ruling U-2), two new bookkeeping tables exist, neither reachable from an application-facing API: (a) `r2dbsvc_registry.platform_declarations` (migration `0008`) lives in the platform database, which no application `runtime`/`developer` role ever connects to;
- both platform process roles (`r2dbsvc_api`, `r2dbsvc_controlplane`) hold `SELECT` only and every write goes through the provision DSN (`ops`/migration).
- (b) `public._r2db_platform_upgrades` (revised `0003` template, retrofit script `0009`) lives inside each application's own database, is OWNED by that application's developer role -- the same scope `_r2db_schema_revision` already has, closed inside that one database -- and grants the `runtime` role `SELECT` only (requester ruling U-2), which is what the cell-open completeness check reads;
- the provision role holds `SELECT` plus schema `USAGE` so `upgrade-status` can report without assuming the developer role.
- Reading one bookkeeping row is not the exercise of a privilege SI-12 forbids (no DB credential, no unbounded connection, no privileged private endpoint, no key that bypasses authorization), and the table name is unreachable through the API at all: `structured.py`'s `_reject_reserved_prefix` refuses any `_`-prefixed identifier.

#### Evidence

- contract smoke test.
- Evidence: `r2db-api/tests/test_postgres.py::test_runtime_role_can_select_but_not_write_the_ledger`, `::test_provision_role_can_read_the_ledger_after_the_script_ends`, `::test_ledger_table_has_no_row_level_security`, `::test_template_seeds_the_ledger_with_the_current_platform_upgrade_numbers`, `::test_0009_upgrades_a_legacy_application_to_match_a_freshly_provisioned_ledger`, `::test_backend_excludes_the_ledger_from_catalog_and_schema_objects_accounting`, `::test_missing_rls_view_stays_empty_on_both_a_new_and_an_upgraded_application`, `r2db-api/tests/test_ops_declarations.py::test_migration_0008_grants_select_to_both_writer_roles_and_nothing_to_public`, `::test_migration_0008_seeds_window_default_but_not_surfaces`, `::test_migration_0008_key_check_constraint_is_named`.

#### Status

- Stated limit (design §3.9): the ledger is an operational record, not tamper-proof evidence -- inside the threat model's own "one application-facing defect" case its rows are as reachable as any other bookkeeping row in that same database.

### MitateDB-api

#### Control

- `cell.py`/`backend.py`/`backend_postgres.py`/`backend_sqlite.py` expose only the structured operation set (query/insert/update/delete/create_entity/add_field) -- no method returns a raw connection, DSN, or credential/verifier value, and the single execution choke point (`_execute`, R-2) is typed to reject any `str` statement with `TypeError` -- `test_no_arbitrary_sql_and_identifier_validation`, real-PostgreSQL coverage in `test_postgres.py` (shared with SI-04/SI-05).
- `/control/v1`'s own responses likewise never echo a DSN, pepper, or another credential's secret -- `list_credentials`/`list_applications` return only `credential_id`/`application_id`/`role`/`enabled`/`revoked` (schema-exact per `test_control_capabilities_result_matches_schema_exactly_and_declares_request_bytes`).
- Under Q4 (design D-2/D-3 §3.9, ruling U-2), this peer is isomorphic: `platform_declarations` (migration 0007) sits in the platform database with `SELECT` for both service roles and writes only through `MITATEDB_PROVISION_DSN`;
- `_mdb_platform_upgrades` (revised 0003, retrofit 0008) sits in each application database, owned by that application's developer role, `SELECT`-only for the runtime role, excluded from `schema_count()`'s accounting and never listed as an entity.
- `_`-prefixed identifiers are unreachable through the API here too.

#### Evidence

- —

#### Status

- Same stated limit: an operational record, not tamper-proof evidence -- `test_runtime_role_has_select_only_on_the_ledger`, `test_0007_grants_select_to_both_roles_and_nothing_to_public`.

### Common

#### Control

- —

#### Evidence

- exposure/config review

#### Status

- —

## SI-13 Revocation/Disable Effectiveness

[history](CONTROL_MAPPING_HISTORY.md#si-13)

### r2db-api

#### Control

- `CredentialStore.assert_active` re-checks each operation and `DataService` checks application state;
- CCR-14 extends immediate revoke/disable effectiveness to control credentials (`docs/design/R2DB_CCR14_CONTROL_PLANE_V1.md` R-2/R-5/R-10/R-13): the same request-time, no-cache credential lookup the application plane uses -- the row is resolved by the locator's `credential_id` and `compare_digest` against the stored verifier is the authoritative check (Phase 6 D-1, contract 1.6.0; the verifier is never the lookup key) (`authorization_propagation_bound_ms: 0`) applies to `ControlCredentialStore`/`PostgresControlCredentialStore` -- a revoked or disabled control credential stops authenticating on its very next request, verified end-to-end by `r2db-api/tests/test_control_plane_store.py::test_reset_revokes_all_and_issues_one_new_credential_atomically_and_touches_nothing_else` (old secret `AUTH_REVOKED` immediately after `reset`, new secret live, Application data/application credentials untouched).
- Deliberate, permanent design choice, not a gap: an *un-revoke* of a control credential is never offered by any code path (`set_state(revoked=False)` is refused with `VALIDATION_FAILED` by both store implementations, matching the pre-existing application-credential un-revoke refusal) -- reversing a revocation would make a durably-recorded revocation event false, which SI-13 itself would then have to call a propagation failure;
- the canonical recovery from a revoked control credential is always the out-of-band `reset` ritual, never an un-revoke, verified by `r2db-api/tests/test_control_plane_store.py::test_control_credential_parity_un_revoke_refused_both_impls`, `::test_break_glass_never_offers_un_revoke`.
- The first-issued credential's own non-permanence (contract `bootstrap[5]`, "expires or requires rotation") is satisfied by a `must_rotate` gate rather than a time-based expiry -- the credential authorizes nothing but `GET /control/v1/capabilities` and self-rotate until one real rotation completes, verified by `r2db-api/tests/test_control_plane_store.py::test_control_credential_locked_by_must_rotate_still_authenticates_and_rotate_clears_it`.

#### Evidence

- `test_revoke_disable_and_unavailable_state_fail_closed`;

#### Status

- propagation bound remains deployment evidence.

### MitateDB-api

#### Control

- `CredentialStore.assert_active` re-checks revocation/application state on every session operation;
- Control credential: the same request-time, no-cache credential lookup (row resolved by the locator's `credential_id`, `compare_digest` against the stored verifier as the authoritative check; Phase 6 D-1) applies to `control_auth.ControlCredentialStore`/`control_credential_store_postgres.PostgresControlCredentialStore` (`authorization_propagation_bound_ms: 0`, `ControlPlaneService.control_capabilities`, schema-checked by `test_control_plane_service.py::test_control_capabilities_result_matches_schema_exactly_and_declares_request_bytes`) -- a revoked or disabled control credential stops authenticating on its very next call, verified by `MitateDB-api/tests/test_control_credentials.py::test_revoke_is_terminal_enable_cannot_resurrect_it`, `::test_disable_then_enable_restores_authentication`, and end-to-end (real reset ceremony) by `MitateDB-api/tests/test_ops.py::test_reset_with_the_echoed_phrase_revokes_everything_and_mints_one_new_credential`.
- Un-revoke is refused, not merely absent: both `set_credential_state`/`set_control_credential_state` call paths only ever set `revoked=True`, never `False` -- `ControlPlaneService` has no method parameter that could request it, and the C-13 conformance vector (below) exercises the real `enable(True)`-after-`revoke` sequence as a `must_deny` case, not a `structurally_absent` one.

#### Evidence

- `test_disable_revoke_and_unavailable_state_fail_closed`.

#### Status

- Production propagation bound (network/co-location latency beyond the in-process guarantee above) remains deployment evidence for both credential kinds.

### Common

#### Control

- —

#### Evidence

- `conformance-tests/test_c08_revocation_boundary.py::test_revoked_credential_stops_existing_session_and_reauth`, `::test_disable_propagates_contains_and_enable_is_selective`, `::test_double_revoke_and_double_disable_do_not_loosen_denial`, `::test_propagation_bound_is_finite_and_non_negative` (four adapters -- `r2db-api`, `r2db-api-http`, `MitateDB-api`, `MitateDB-api-http` -- condition C-08);
- the bootstrap/reset lifecycle's own revocation-effectiveness/non-permanence properties are additionally covered by `conformance-tests/test_c15_bootstrap_reset_lifecycle.py` (condition C-15) -- all four adapters take the PROVIDED branch

#### Status

- —

## SI-14 Security-Relevant Auditability

[history](CONTROL_MAPPING_HISTORY.md#si-14)

### r2db-api

#### Control

- `ControlAuthority` emits canonical lifecycle/control-failure events including denied audit deletion;
- application facade exposes no audit accessor;
- `AuditSink` immutable snapshots and forbidden-field guard;
- `r2dbsvc_registry.control_audit` (`0006_control_plane_http.sql`) is a real, durable PostgreSQL table carrying the contract `audit.fields`' 13 named columns plus `recorded_at`.
- State-changing control-plane operations write their audit row in the same transaction as the state change (`unit_of_work()`), so a durable-write failure aborts the state change too -- fail-closed by construction -- verified by `r2db-api/tests/test_control_plane_service.py::test_each_state_change_adds_exactly_one_audit_row`, `::test_state_change_sink_fault_injection_aborts_the_state_change`.
- `target_id` (the contract's 13th `audit.fields` member) names the single target credential/application a lifecycle event acted on, populated at every emission site (`control_plane.py`, `ops.py`, the bootstrap/reset ritual) -- verified by `r2db-api/tests/test_control_plane_service.py::test_issued_secret_appears_only_in_the_response`, `::test_target_id_populated_for_application_and_credential_lifecycle_events`, and for the CLI emission path by `r2db-api/tests/test_control_plane_store.py::test_cli_freeze_issuance_writes_control_audit_row`.
- The compromise-window playbook reads `target_id` directly off `issue_credential`/`rotate_credential` audit rows.
- Denial events are durably recorded too (contract `audit.sink_failure_policy` lists authentication/authorization denial first, ahead of state changes), including `AUTH_REQUIRED` (no credential presented at all) so even the cheapest probe leaves a trace -- `r2db-api/tests/test_control_plane_service.py::test_authentication_denials_are_durably_audited_with_truthful_attribution`, `::test_denial_audit_insert_failure_becomes_503_for_every_denial_kind` (1 more attribution pin: companion history).
- **Runtime role holds no privilege beyond insert**: `GRANT INSERT`-only on `control_audit` holds from the control-plane process' own role (`r2dbsvc_controlplane`);
- the schema owner (`r2dbsvc_control`) retains ordinary owner privilege -- `r2db-api/tests/test_control_plane_store.py::test_controlplane_role_grants_match_the_design` (INSERT only, never SELECT/UPDATE/DELETE its own writes back).
- The out-of-band CLI (`python -m r2db_api.ops`) writes to the same table, same-transaction-as-state-change, for every state-changing subcommand (`r2db-api/tests/test_control_plane_store.py::test_cli_issue_credential_writes_control_audit_row_with_no_secret_anywhere`, `::test_cli_revoke_credential_writes_control_audit_row`; 1 more subcommand pin: companion history);
- CLI denials are reported via stderr/exit code rather than durably audited (an OS-access-gated tool, not the public surface's untraceable-probe risk).
- `r2dbsvc_registry.application_audit` (`migrations/0007_application_audit.sql`) carries the same 13 contract `audit.fields` columns `control_audit` does, plus `recorded_at timestamptz NOT NULL DEFAULT clock_timestamp()`, `audit_seq bigserial`, per-column `length` CHECKs, and a `count` column (a coalesced-denial summary row or buffer-overflow alert row sets it; never `0`/`1`) -- `r2db-api/tests/test_application_audit.py::test_coalesced_summary_row_with_exactly_one_repeat_writes_no_literal_count_of_one`, `::test_buffer_overflow_alert_row_with_exactly_one_drop_writes_no_literal_count_of_one`.
- **Fail-closed by construction**: the durable row is INSERTed/committed on a separate platform connection before the data transaction commits;
- a sink failure rolls the data transaction back, answers `SERVICE_UNAVAILABLE` -- `::test_destructive_mutate_is_service_unavailable_when_the_durable_sink_fails`, `::test_schema_operation_is_service_unavailable_when_the_durable_sink_fails`.
- `outcome="allow"` means "authorized and submitted", not "committed": a clean commit failure writes a second `outcome="error"` row for the SAME `request_id` (`::test_failed_data_commit_writes_an_error_row_for_the_same_request_id`), that error row is itself fail-closed;
- a simulated process loss deliberately leaves the `allow` row standing alone, per spec (`::test_simulated_process_loss_leaves_the_allow_row_alone`).
- **Append-only by grant**: `r2dbsvc_api` gains INSERT (plus sequence USAGE) on `application_audit` and nothing else;
- `r2dbsvc_auditreader` holds SELECT-only on BOTH audit tables;
- `r2dbsvc_controlplane` has no privilege on `application_audit` at all -- verified over bare `psycopg` connections by `::test_api_role_cannot_select_update_or_delete_application_audit`, `::test_auditreader_role_can_select_both_audit_tables_and_nothing_else` (1 more grant pin: companion history).
- **Which denials are durable**: an inclusion list of exactly six reason codes -- `AUTH_REQUIRED`, `AUTH_INVALID`, `AUTH_REVOKED`, `FORBIDDEN`, `APPLICATION_DISABLED`, `DESTRUCTIVE_CONFIRMATION_REQUIRED` (`_DURABLE_DENIAL_CODES`, `src/r2db_api/service.py`);
- every other reason code is non-durable and does not enter the bounded buffer -- `r2db-api/tests/test_application_audit.py::test_validation_failed_denials_add_no_durable_row_and_no_buffer_entry`, `::test_capability_unsupported_and_not_found_denials_add_no_durable_row`.
- **Coalescing**: the key is `(application_id, actor_id or "unknown", operation, reason_code)` over a 60s window;
- the first occurrence is a synchronous INSERT+commit;
- repeats are counted in memory and flushed at window end as one aggregate row -- ceiling of two rows per key per window per process -- both the coalescing counters and the bounded buffer below are process-local, so a deployment's real ceiling is `2 x <windows> x M` and `<buffer capacity> x M` for M = the deployment's maximum instance count;
- **Bounded buffer for ordinary successes**: capacity 1000 by default (`R2DB_AUDIT_BUFFER_CAPACITY`), flushed on threshold and periodically, on a separate connection so a buffer failure never blocks a fail-closed operation;
- overflow emits a fixed `logging.error` plus a durable `security_control_failure` row, rate-limited to one per flush interval (3 buffer-bound/overflow/rate-limit pins: companion history).
- The `failing` flag means the result of the LAST COMPLETED flush attempt -- clears on success regardless of remaining backlog;
- concurrent flushes resolve by completion order (2 `failing`-flag pins: companion history).
- One data operation adds at most one durable row (`::test_each_data_operation_adds_exactly_one_application_audit_row`);
- dispatch between fail-closed and buffered classes is by request structure at the destructive-confirmation choke, never by `event_class` (`::test_dispatch_point_is_the_destructive_confirmation_choke`).
- The `request_id` the HTTP layer returns is the one written to the durable row (`::test_failed_data_commit_writes_an_error_row_for_the_same_request_id`).
- A denial row's `application_id` comes from the authenticated `AuthContext`, never a client-declared value;
- an unauthenticated denial carries `application_id = NULL`, keyed on `actor_id or "unknown"`.
- **Declared `event_class`/`operation`/`target_kind` vocabulary is exactly the emitted one**, machine-guaranteed by a single AST scanner over the whole package, no hand-maintained list: each `<field>=` keyword argument must be a string constant, an `IfExp` of constants, or a genuinely-bound forward parameter -- no smuggling via a dict literal, subscript/attribute assignment, or passthrough of a client-supplied dict;
- every function taking the field declares it keyword-only.
- With the literal set thereby completely enumerable, the scanner pins `U == D ∪ N` and `D ∩ N == ∅` per field, where `N` is an explicitly-named, runtime-measured non-durable exclusion set.
- Peer numbers: `event_class` (legacy in-memory-sink-only classes only: `authentication`/`control_failure`/`control_state`, reached only through `ControlAuthority._control_event`);
- `operation` U 31 = D 27 + N 4 (`delete_audit`/`set_authorization_state_available`/`set_credential_state`, plus `control_capabilities` (its 2 emit sites can never reach a deny branch) -- `r2db-api/tests/test_audit_query.py::test_control_capabilities_operation_has_no_reachable_deny_branch`);
- `target_kind` U 6 = D 5 + N 1 (`application_or_credential`).
- Contract 1.4.0 obligation (b)'s scope is settled by contract text (same-label addendum): a data-plane host need not authenticate control/audit credentials merely by declaring `control_plane` other than `unavailable`;
- Why this peer's data-plane host holds no control-credential store at all belongs to SI-00, not this row.

#### Evidence

- `test_control_lifecycle_and_failures_are_canonical_audit_events`, `test_audit_is_append_only_and_secret_free`.
- (i)/(ii): `r2db-api/tests/test_control_plane_service.py::test_rate_limit_precedes_authentication_and_is_not_audited`;
- (iii): `r2db-api/tests/test_preauth_concurrency_bound.py::test_preauth_concurrency_denial_is_never_durably_audited`.
- Non-durability is measured, not assumed: `r2db-api/tests/test_audit_query.py::test_operation_and_target_kind_non_durable_exclusions_never_reach_the_durable_tables` drives each excluded word through its real path and asserts no durable row appears.
- `::test_declared_event_classes_cover_every_emittable_class`, `::test_every_field_keyword_argument_is_a_string_literal_ifexp_or_forward` (7 more AST-scanner structural pins: companion history).
- `::test_peer_local_helpers_are_isomorphic_to_the_sibling_peer` reads the sibling peer's test file by path (never imports it), asserting the loaded path is the sibling's.

#### Status

- **Disclosed limit -- three denial categories are exempted from durable audit**: (i) `control_requests_per_minute` rate-limit refusals -- runs before authentication (no `credential_id` yet) and before any durable write, so a flood cannot generate unbounded audit rows;
- (ii) `AUTH_STATE_UNAVAILABLE` (the credential store itself is unreachable) -- a service-health outcome where the audit attempt would itself fail, compounding one outage into a second 503 for no benefit;
- the HTTP response is already fail-closed regardless;
- (iii) phase 10's pre-authentication `concurrency` refusals on the application HTTP plane -- the slot is taken before `_authenticate`, so the denial has no authenticated actor to attribute and writes no durable row (SI-08).
- These codes are out of scope because they sit outside SI-14's own minimal event class (authentication/authorization denial, credential/Application lifecycle change, destructive or privilege-sensitive operation, control-plane administrative change, security-control failure), not because they are uninteresting -- and this rests on the same ground as, but does not resolve or excuse, the control plane's own two exemptions above (pre-auth rate refusal, `AUTH_STATE_UNAVAILABLE`): the two lines differ in content;
- neither settles the other.
- folding M into the capacity thresholds is runbook work (`POSTGRES_PROVISIONING_RUNBOOK.md` §15) -- `r2db-api/tests/test_application_audit.py::test_repeated_invalid_secret_adds_exactly_one_coalesced_row_with_count_n`, `::test_different_denial_keys_do_not_coalesce_together` (1 more concurrency pin: companion history).
- **Disclosed limit**: `AUTH_REQUIRED` durability is a genuinely new unauthenticated-write path;
- bounded only by coalescing and length CHECKs, not any rate window (`audit_requests_per_minute` governs `audit_query` on the control host only).
- operational instruction `POSTGRES_PROVISIONING_RUNBOOK.md` §16.
- **Two limits disclosed, not overstated**: (i) that both processes point at the SAME platform database is itself unverified -- neither knows the other's DSN, so a stale platform DSN on the control process reproduces the old drift;
- detection stays at post-deploy comparison of the two capability documents;
- (ii) a process can effective-check only its OWN role, only at startup -- role settings apply at login, so the control process cannot check `r2dbsvc_api` (that peer's own job), and pool connections opened after startup are not re-checked;
- changing the declaration means `ops` plus a restart of BOTH processes.
- deliberately peer-local (the port carries no method for it).
- **Disclosed limit**: the equality check cannot see a SHRINKING declaration (moving a durable word from `D` into `N` in the same step keeps `U == D ∪ N` true);
- the only detector is a per-field snapshot test pinning `DECLARED_AUDIT_OPERATIONS`/`DECLARED_AUDIT_TARGET_KINDS`/`DECLARED_AUDIT_EVENT_CLASSES` against a fixture `frozenset` -- `r2db-api/tests/test_audit_query.py::test_declared_audit_event_classes_change_only_deliberately`, `::test_declared_audit_operations_change_only_deliberately` (1 more snapshot pin: companion history).

### r2db-api -- audit query

#### Control

- `POST /control/v1/audit/query` and the `POST /v1/audit/query` alias resolve to ONE handler on the control app;
- the reader is `r2dbsvc_auditreader` (SELECT-only) over the UNION of `control_audit` and `application_audit`;
- `plane` derives from the source table, never writer-settable;
- total order is `(recorded_at, plane, event_id)`;
- `after` is an opaque keyset cursor, `VALIDATION_FAILED` when undecodable;
- rows newer than `visibility_lag_ms` are withheld -- `r2db-api/tests/test_audit_query.py::test_control_host_serves_both_audit_query_paths_with_one_handler`, `::test_cursor_paging_covers_every_row_without_duplicates_under_concurrent_writes` (3 more endpoint-behavior pins: companion history).
- The data-plane host's own `/v1/audit/query` is unchanged and still answers `CAPABILITY_UNSUPPORTED` (`::test_data_plane_host_audit_query_still_refuses_with_capability_unsupported`).
- `visibility_lag_ms` (`statement_timeout + idle_in_transaction_session_timeout + 1000ms`, `11000ms` at shipped defaults) is derived by both processes from ONE shared ground -- the platform catalog (`pg_db_role_setting`) -- each process checks at startup that its own effective value agrees with it (declared writer, both settings present, neither zero/negative, no per-database override, writer connection matches catalog);
- any failure stops that process before it declares or serves anything -- `r2db-api/tests/test_audit_query.py::test_declared_visibility_lag_ms_is_derived_from_the_two_timeouts`, `r2db-api/tests/test_ops_declarations.py::test_derive_visibility_lag_ms_default_is_11000` (5 more startup-guard message pins: companion history);
- `capabilities().audit_query.operations` (27 members) and `.target_kinds` (5 members) are published `sorted()` off declared constants -- the same declare-the-hazard posture `event_class` has, with no enum in the contract;
- the data-plane host declares `audit_query` `unavailable` and carries neither key (`r2db-api/tests/test_audit_query.py::test_data_plane_capabilities_declares_contract_version_1_5_0_and_audit_query_unavailable`).

#### Evidence

- The same measurement technique (reading the two `SHOW` timeouts off the sink's own writer connection) also covers the HTTP conformance adapters' `PostgresApplicationAuditSink` writer connection -- `r2db-api/tests/test_conformance_adapter_r2db_http_audit_writer_timeouts.py::test_http_conformance_adapter_audit_writer_connection_has_no_explicit_session_override`, `MitateDB-api/tests/test_conformance_adapter_mitatedb_http_audit_writer_timeouts.py::test_http_conformance_adapter_audit_writer_connection_has_statement_and_idle_timeouts_set`;
- the control-credential-against-data-host case is now a common, unconditional vector (this row's Common evidence cell).

#### Status

- —

### MitateDB-api

#### Control

- **Application-plane audit, pre-durable-sink foundation**: `AuditSink` uses immutable snapshots + detail/event allowlists;
- This 6-field in-memory sink is no longer the only record -- see the durable-sink paragraph below.
- `mitatedb_registry.control_audit` (migration `0002`) is a real, durable PostgreSQL table carrying the contract `audit.fields`' 13 named columns plus a monotonic `audit_seq` bigserial (`recorded_at` alone is not a total order under concurrent same-timestamp writes, needed for C-15's prefix-strict comparison).
- State-changing operations write their audit row in the SAME transaction as the state change (`unit_of_work()`), so a durable-write failure aborts the state change too -- `MitateDB-api/tests/test_control_plane_service.py::test_audit_write_fault_rolls_back_an_accompanying_application_registration`, `::test_audit_write_fault_rolls_back_an_accompanying_credential_revoke` (1 more rollback pin: companion history).
- `target_id` (the contract's 13th `audit.fields` member) names the single target credential/application a lifecycle event acted on -- `::test_target_id_populated_for_application_and_credential_lifecycle_events`, `::test_target_id_populated_for_control_credential_lifecycle_events` (1 more emission-site pin: companion history).
- Denials are durably recorded too, with the same three exemptions r2db documents (rate-limit pre-authentication, `AUTH_STATE_UNAVAILABLE`, and phase 10's pre-authentication `concurrency` refusal on the application HTTP plane, taken before `_authenticate` and therefore carrying no authenticated actor) -- `::test_rate_limit_denial_is_never_durably_audited`, `::test_auth_state_unavailable_is_never_durably_audited` (2 more denial-kind pins: companion history), and `MitateDB-api/tests/test_preauth_concurrency_bound.py::test_preauth_concurrency_denial_is_never_durably_audited`.
- **Runtime role holds no privilege beyond insert**: `mitatedbsvc_controlplane` has `INSERT`-only privilege on `control_audit` (no `SELECT`/`UPDATE`/`DELETE` for that role) -- bare-connection verified: `MitateDB-api/tests/test_control_plane_postgres.py::test_control_plane_role_cannot_select_its_own_audit_table`, `::test_control_plane_role_can_insert_into_its_own_audit_table`;
- the schema owner (`mitatedbsvc_provision`) is a separate reader role required to read this table back (used by the HTTP conformance adapter and the break-glass `audit-report` CLI subcommand).
- The out-of-band ritual CLI (`ops.py`) writes to the same table for `bootstrap`/`reset`;
- the break-glass command family's state-changing subcommands write through the SAME `ControlPlaneService` methods, therefore the same same-transaction audit guarantee, never a second CLI-specific path.
- `mitatedb_registry.application_audit` (`migrations/0005_application_audit.sql`, `event_id text` PRIMARY KEY) carries the identical 13 contract columns + `count` + `audit_seq` + `recorded_at DEFAULT clock_timestamp()` + the same length CHECKs;
- `mitatedbsvc_api` INSERT-only, `mitatedbsvc_auditreader` SELECT-only on both audit tables, `mitatedbsvc_controlplane` nothing -- `MitateDB-api/tests/test_application_audit.py::test_api_role_cannot_select_update_or_delete_application_audit`, `::test_auditreader_role_can_select_both_audit_tables_and_nothing_else` (2 more grant pins: companion history).
- Same 6-code inclusion list, key, 60s window, and 2-rows-per-key-per-window-per-process ceiling as r2db: `::test_durable_denial_codes_match_the_design_d3_table`, `::test_repeated_invalid_secret_adds_exactly_one_coalesced_row_with_count_n` (2 more coalescing pins: companion history).
- Same bounded buffer + rate-limited overflow alert: `::test_buffer_does_not_grow_past_its_configured_bound`, `::test_buffer_overflow_emits_logging_error_and_exactly_one_security_control_failure_row` (2 more buffer pins: companion history).
- **MitateDB-specific**: the legacy 6-field in-memory sink's rounding (out-of-vocabulary values silently mapped to `"unclassified"`/`"unspecified"`) never reaches the durable path -- a separate 13-column emitter is used there -- `::test_durable_path_never_passes_through_the_six_field_rounding_sink`, `::test_declared_event_class_values_are_disjoint_from_the_six_field_sink_rounding_fallbacks`.
- **`commit()` runs inside `try`**: `backend_postgres`'s `create_collection`/`add_field`/`delete` commit inside the classified block (both backends; SQLite's DDL runs under an explicit pseudo-transaction) so a commit raise is never left unclassified -- `::test_backend_commit_failure_is_classified_and_produces_an_error_row`, `::test_in_memory_and_postgres_backends_have_pre_commit_hook_parity`.
- query/insert/update successes are emitted/buffered like r2db's own -- `::test_query_insert_and_update_success_events_are_durably_recorded`, `::test_each_data_operation_adds_exactly_one_application_audit_row` (1 more dispatch pin: companion history).
- `request_id` is threaded from HTTP through auth/cell/backends so the wire id matches the durable row's id -- `::test_http_response_request_id_matches_the_durable_audit_row`.
- A `FORBIDDEN` row's `application_id` is the TARGET cell's own id (victim side), never caller-declared -- `::test_application_scope_denied_is_durably_recorded`, `::test_role_denied_is_durably_recorded` (1 more denial-kind pin: companion history).
- `audit_query` is served on the control host at both paths with one handler, reader `mitatedbsvc_auditreader`, `plane` from the source table, `(recorded_at, plane, event_id)` order, opaque cursor, derived `visibility_lag_ms` -- `MitateDB-api/tests/test_audit_query.py::test_control_host_serves_both_audit_query_paths_with_one_handler`, `::test_cursor_paging_covers_every_row_without_duplicates_under_concurrent_writes` (3 more endpoint-behavior pins: companion history).
- The two-process `visibility_lag_ms` premise is grounded the same way as r2db's cell: one shared catalog (`pg_db_role_setting`) grounds both the declaration and the effective value, the same startup double-check, the same removed/rejected env vars.
- Both `operation` and `target_kind` are declared, alongside `event_class`, by the same single AST scanner r2db's cell describes, no hand-maintained list.
- `capabilities().audit_query.operations` (29 members) and `.target_kinds` (5 members) are published `sorted()`, each the union of the control half and the application half -- a mutation in either half turns the same equality check red.
- Peer numbers: `operation` U 30 = D 29 + N 1 (`control_capabilities`, excluded for the same structurally-unreachable-deny-branch reason as r2db's literal -- `::test_control_capabilities_operation_has_no_reachable_deny_branch`);
- `target_kind` U = D = 5, N = ∅;
- `event_class` N = ∅.
- This peer's exclusion list has 1 definition.
- Contract 1.4.0 obligation (b) is settled by contract text, as in r2db's cell;
- see SI-00 for this peer's realization (no control-credential store on the data-plane composition root).

#### Evidence

- representative test: `test_audit_events_are_append_only_and_secret_free`.
- Field-set match is fixed by `::test_control_audit_fields_matches_the_contract_audit_fields_exactly`.
- `test_application_plane_role_has_no_privilege_on_control_audit` remains green unchanged.
- Fail-closed by construction: `::test_destructive_delete_is_service_unavailable_when_the_durable_sink_fails_sqlite`/`_postgres`, `::test_schema_operation_is_service_unavailable_when_the_durable_sink_fails_sqlite`/`_postgres`, with the `error`-row rule at `::test_failed_data_commit_writes_an_error_row_for_the_same_request_id`, `::test_simulated_process_loss_leaves_the_allow_row_alone`.
- Derivation pinned by `::test_declared_visibility_lag_ms_is_derived_from_the_two_timeouts`;
- catalog-grounded checks by `MitateDB-api/tests/test_platform_declarations.py::test_f7_missing_declaration` (4 more startup-guard pins: companion history);
- real writer connections by `test_application_audit.py::test_application_audit_writer_connection_reflects_the_api_roles_own_setting`, `::test_control_audit_writer_connection_reflects_the_controlplane_roles_own_setting`;
- removed env vars by `test_main.py::test_build_app_rejects_every_removed_env_var_through_the_real_composition_root`;
- `auth.py`'s and `credential_store_postgres.py`'s `operation="authenticate"`/`"assert_active"` and `target_kind="credential"` sites are measured to reach the durable tables (`::test_authenticate_and_assert_active_denials_are_durable_not_excluded`, and against real PostgreSQL `::test_postgres_authenticate_and_assert_active_denials_are_durable_not_excluded`), so they are `D`, not `N`.

#### Status

- **Two limits, identical to r2db's cell**: (i) both processes reading the same platform database is itself unverified;
- (ii) a process can effective-check only its own role, only at startup.
- operational instruction `MitateDB-api/docs/cloud-run-cloud-sql.md` §3.2b.
- **Disclosed limit, identical to r2db's cell**: the equality check cannot see a shrinking declaration;
- the only detector is a per-field snapshot test.

### Common

#### Control

- —

#### Evidence

- audit evidence tests;
- CCR-14's control-plane durable-audit and non-permanence properties are additionally covered by `conformance-tests/test_c15_bootstrap_reset_lifecycle.py` (condition C-15) -- all four adapters take the PROVIDED branch.
- The application-plane durable sink and `audit_query` are additionally covered by `conformance-tests/test_c09_audit_evidence.py` (condition C-09) and by `AuditResult` reverse-validation in `conformance-tests/test_c11_response_schema_conformance.py` (condition C-11) -- all four registered adapters take the PROVIDED branch, and the whole-registry vacuity guard `test_c09_every_control_surface_adapter_takes_the_provided_branch` is green with no `xfail`, requiring EVERY registered adapter with a control surface to have taken it (see the C-09 row of `conformance-tests/CONDITIONS.md`).
- The declared-vocabulary property is checked from the common side too, by three isomorphic declaration-agreement vectors in `conformance-tests/test_c09_audit_evidence.py` -- `::test_c09_declaration_agreement_event_class`, `::test_c09_declaration_agreement_operation`, `::test_c09_declaration_agreement_target_kind` -- each of which raises a known durable event, polls within the declared visibility lag and asserts a NON-EMPTY observation before checking that every returned value is drawn from the declaration, plus `::test_c09_every_control_surface_adapter_declares_1_5_0` as the whole-registry vacuity guard.
- Contract 1.4.0 obligation (b)'s scope is exercised unconditionally by `::test_c09_data_plane_host_audit_query_alias_rejects_control_credential_unless_cohosted` on all four plugs, over conformance port v1.9 (co-hosting judged by `adapter.surfaces_cohosted(document)`, derived from a peer's own declared `surfaces` origins).
- **Phase 10 (2026-09-10)**: C-25's leg (3) -- a mutation's own `request_id` is the one its own audit event carries -- is now driven from the plug's own CONTROL-plane discovery (`control_capabilities()`), not the data-plane document every plug declares `audit_query: unavailable` on by product-code constant, which is what made the leg vacuously undriven before;
- the status is read off the SAME isolated surface the mutation was made through, asserted to agree with the session adapter's own reading, with an in-test whole-registry guard requiring at least one registered plug to declare `audit_query` enabled/partial -- `conformance-tests/test_c25_result_request_id.py::test_c25_result_request_id`, parametrized once per registered plug (six since the two socket plugs landed).
- Condition C-26 adds real-startup evidence: each peer's documented composition root runs as real OS processes in front of a real nginx and is observed to serve exactly the surfaces it declared, on both planes, to a brand-new client;
- a root with no declaration row fails fast instead of starting on a default;
- and shutdown leaves no process, no bound port, no temporary directory and no throwaway database or role behind -- `conformance-tests/test_c26_composition_root.py::test_c26_declared_surfaces_are_served`, `::test_c26_deploy_smoke_is_green`, `::test_c26_missing_declaration_fails_fast`, `::test_c26_no_residue_after_shutdown`, `::test_c26_start_failure_leaves_no_residue`, with the registry non-vacuity guards `::test_c26_composition_roots_registry_has_at_least_two` and `::test_c26_items_are_grouped_per_launcher`.

#### Status

- **Disclosed limit**: the common side only checks "returned ⊆ declared" -- the reverse half (a word declared but never returned) stays outside the common suite and is carried by each peer's own cell alone.
- **Disclosed limit**: the `provided` branch's own real-world co-hosted case remains unexercised by any currently-registered deployment (no registered plug currently co-hosts both surfaces on the same origin) -- restated in the C-09 row.

## SI-15 Fail-Closed Authorization

[history](CONTROL_MAPPING_HISTORY.md#si-15)

### r2db-api

#### Control

- `CredentialStore` rejects unavailable/unknown/disabled/revoked state;
- `DataService._check`;
- CCR-13's declaration-completeness guard is the same fail-closed shape applied to capability declarations rather than credential state: `PostgresCell._load_catalog` (`docs/design/R2DB_CCR13_STORAGE_V1.md` R-1) fails the whole call closed with `SERVICE_UNAVAILABLE` if even one entity lacks the `id`/`_r2db_revision` columns a `mutable`/`revision_preconditions: enabled` declaration requires, rather than silently publishing a false declaration for it.
- `audit`-role denial: an `audit` credential attempting any of the 8 write control operations is refused `FORBIDDEN` and the denial is durably audited in the same assertion, not merely fail-closed with no trace -- `r2db-api/tests/test_control_plane_service.py::test_audit_role_forbidden_fail_closed_on_every_other_control_endpoint` asserts both `exc.value.code == "FORBIDDEN"` and `exc.value.details.get("audited") is True` (plus a durable audit-row-count increment) for every one of the 8, parametrized over both the in-memory and real-PostgreSQL backends -- the PostgreSQL parametrization is this row's own durable read-back evidence for r2db.

#### Evidence

- `test_revoke_disable_and_unavailable_state_fail_closed`;

#### Status

- —

### MitateDB-api

#### Control

- `CredentialStore` rejects unavailable auth state and missing/disabled credentials;
- `audit`-role denial: same fail-closed-with-durable-trace property, `MitateDB-api/tests/test_control_plane_service.py::test_audit_role_forbidden_fail_closed_on_every_other_control_endpoint` (asserts a durable audit-row-count increment plus `reason_code == "FORBIDDEN"` for every one of the 8 write operations), with dedicated real-PostgreSQL durable read-back evidence (a genuine post-commit SELECT, not an in-process snapshot) by `MitateDB-api/tests/test_control_plane_postgres.py::test_audit_role_accepted_on_read_endpoints_and_forbidden_on_a_write_endpoint_against_real_postgres`.

#### Evidence

- `test_disable_revoke_and_unavailable_state_fail_closed`.

#### Status

- —

### Common

#### Control

- —

#### Evidence

- `conformance-tests/test_c08_revocation_boundary.py::test_authorization_state_unavailable_fails_closed_then_recovers`, `::test_disable_propagates_contains_and_enable_is_selective` (four adapters -- `r2db-api`, `r2db-api-http`, `MitateDB-api`, `MitateDB-api-http` -- condition C-08);
- an undeclared capability executing anyway (the reverse fail-closed direction) is additionally covered by `test_c12_capability_agreement.py` (condition C-12) and `test_c17_declaration_agreement.py` (condition C-17), both executable on all four adapters

#### Status

- —

## CCR-14 control-plane compromise boundedness (R-11)

This is a cross-cutting statement about `r2db-api`'s control-plane design
(`docs/design/R2DB_CCR14_CONTROL_PLANE_V1.md` R-11), not a new invariant --
it follows from SI-13's revocation effectiveness, SI-14's auditability, and
R-2/R-3/R-6's storage design already recorded above, restated together
because R-11 reasons about them jointly (a "what can go wrong, and how far"
statement, distinct from any single invariant's own per-property claim).

**Control-credential compromise is a bounded, recoverable event -- bounded
specifically to the control credential itself and to Application
*credentials*, not to Application data, which a compromised control
credential can never destroy.** The residual harm from a stolen or misused
control credential is bounded to (1) whatever data-plane reach the
*application* credentials it **issued or rotated** during the compromise
window provide, until those are individually revoked -- `rotate` on a
pre-existing credential changes its secret to one the compromised control
credential's holder may now know, exactly as much a residual-reach vector
as a freshly `issue`d one, and the recovery procedure below treats both the
same way; (2) an **availability harm from `revoke` itself**: a compromised
control credential can irreversibly `revoke` any number of legitimate
application credentials, and recovering from that is not free -- every
consumer of a revoked credential needs a freshly issued replacement
credential redistributed to it before it can authenticate again, which is
real operational work, not merely "note it happened and move on"; and (3)
the operational disruption of the recovery itself. It is not a route to
unbounded, undetectable, or self-perpetuating access, because three
properties hold simultaneously and by construction (D-5, WP-6 review MA-4
-- refining the design's own R-11 "可逆性の全数" wording, which this row
does not restate verbatim; see `docs/design/R2DB_CCR14_CONTROL_PLANE_V1.md`
§15 for the correction record):

- **Reversibility, precisely scoped.** Every reachable operation
  *except `revoke`* is reversible (`disable`/`enable` round-trips for both
  applications and credentials; a wrongly issued application credential is
  individually revocable to stop it, which is the intended, not merely
  tolerated, response). `revoke`'s own irreversibility is scoped to
  credential rows -- **it destroys no Application data, and it destroys no
  control credential state beyond the row `revoke` targeted** -- but it is
  not scoped to zero real-world effect: a control credential can revoke any
  number of application credentials it can see, and every one of those
  revocations is permanent and requires a freshly issued replacement to be
  redistributed to whatever consumer held the old one. This is the one
  place "bounded" means "the blast radius has a known shape and a known
  recovery cost," not "costs nothing to recover from."
- **Evidence cannot be erased.** `control_audit` is append-only from the
  control-plane process' own role (SI-14 above, R-3) -- a control
  credential, which authenticates only as that role's application-level
  identity, can never reach the schema-owner privilege that could alter or
  delete it. Denied requests are durably recorded too (SI-14 above), so a
  locked-out legitimate operator's own failed attempts are themselves a
  detection signal.
- **Non-persistence.** `role=control` issuance has exactly one path -- the
  out-of-band bootstrap/reset ritual ("案B") -- with no in-band operation,
  including ones a stolen control credential can call, able to create
  another one; `reset` revokes every live control credential and mints
  exactly one new one, atomically, so an attacker cannot out-run recovery
  by having minted spares.

**Recovery procedure**: `r2db-api/docs/CONTROL_PLANE_COMPROMISE_PLAYBOOK.md`
-- reset, then `ops.py audit-report --since <window start>` to enumerate
what happened during the compromise window, then revoke every application
credential issued/rotated in that window (identified directly from each
`issue_credential`/`rotate_credential` audit row's own `target_id` field,
closed phase 3.5 WP-1/WP-4 -- the former `list-credentials`
timestamp-proximity cross-reference the playbook used while this was an
open gap is no longer needed for this step, though the playbook keeps it
documented as a fallback; see the SI-14 row above), then re-enable any
application wrongly disabled.

## Rule

A blank/TBD mapping is not permission to weaken an invariant. It means the implementation has not yet demonstrated how it satisfies the common requirement.

Conversely, a new implementation control does not require a new invariant if it preserves the existing security outcomes.
