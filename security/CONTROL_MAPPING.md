# Security Invariant Control Mapping

Status: **Implementation mapping template**

Version: **3.15** (2026-10-01; R-102 acceptance -- SI-09 MitateDB-api -- platform upgrade: section 10.8 records 10.10 accepted at version 12 on the requester's confirmation of 2026-10-01, so Gate-0 readiness again rests on the 10 items alone.)
Version: **3.14** (2026-10-01; R-102 -- SI-01 MitateDB-api, SI-08 MitateDB-api and its capacity and concurrency block, SI-08 r2db-api -- capacity and concurrency, SI-09 r2db-api, SI-09 MitateDB-api -- platform upgrade, SI-10 MitateDB-api, SI-11 r2db-api, SI-11 MitateDB-api, SI-11 Common: per-role pools, a request scope and transaction-scoped advisory locks replace the cell lock; runbook section 10.10 version 12 is not yet accepted.)


This document maps common Security Invariants to platform-specific controls. It is intentionally not the source of truth for the invariants themselves.

Each claim is one bullet under its invariant, subsection (r2db-api / MitateDB-api / Common), block (the subsection's default block, or a named one written `### <subsection> -- <topic>`) and axis (Control / Evidence / Status); `- —` marks an axis with no claim.

**Claim form** (form 3.0, requester ruling 2026-09-23 --
`docs/design/CONTROL_MAPPING_FORM_V3_V0_1.md` §2): a Control claim names its
subject (a noun phrase of at most six words, preceded by an existing `F-NN` /
`C-NN` / `CCR-NN` id when one exists), states in one sentence what it bounds,
and cites at least one enforcement location as a `path` or `path:line` that
`conformance-tests/test_control_mapping_register.py` resolves (a function or
class name alone is not a location); an Evidence claim states what was
observed and cites at least one test name or `file:line`; a Status claim
states a disclosed limit or a difference between the peers. A limit belongs on
the Status axis, not inside a Control claim, and a generic Evidence sentence
with no citation is not a claim. Each claim is one physical line of at most
250 (Control) / 300 (Evidence) / 300 (Status) characters counting its leading
`- ` (`MAX_CLAIM_LENGTH` in that test file); the cap is per claim, not per
block, so no block length is measured or recorded here.

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
**Since form 3.0 (2026-09-23)** `docs/design/CONTROL_MAPPING_FORM_V3_V0_1.md`
§3 overrides the convention above in two cases: a wording correction or a
reference update (a test name, a `file:line`) is left to git history and moves
nothing into the companion file; a withdrawn control, a weakened limit, and an
Evidence claim that loses its citation and falls to Status still move there
verbatim. Prose that claimed no control, evidence or limit was deleted in the
3.0 migration without being moved; the full text of version 2.25 is at commit
`94febb3`.

**Blocks per subsection** (R-50, requester ruling 2026-09-18 --
`docs/design/CONTROL_MAPPING_MULTI_BLOCK_V0_1.md`): a subsection may hold more
than one block. Each `### ` heading inside an invariant section is either that
subsection's default block (`### MitateDB-api`) or one of its named blocks
(`### MitateDB-api -- ops inventory`; the topic is English and unique within
the subsection). The default block is mandatory, appears exactly once and comes
first. Since form 3.0 the five named blocks that exist stay as they are and no
new named block is added (`docs/design/CONTROL_MAPPING_FORM_V3_V0_1.md` §2.1;
other documents point at these headings, so their text does not change). A
subsection's blocks stand together, the subsection order (r2db-api,
MitateDB-api, Common) is unchanged, and every block holds the same 3 axes in
the same order (`- —` for an axis with no claim). Moving claims between blocks
of the SAME subsection changes no character of any claim, so it is not a
correction and moves nothing into `CONTROL_MAPPING_HISTORY.md`. Other documents
point at a named block as `SI-08 / MitateDB-api / ops inventory / Evidence`,
and at a default block as `SI-08 / MitateDB-api / Evidence`.

**【訂正 2026-09-18 (R-50, version 2.7)】** The two sentences rewritten in place
above each described a block as one whole subsection, which is false once a
subsection holds several blocks. The superseded text is kept here verbatim --
not in `CONTROL_MAPPING_HISTORY.md`, whose headings are bare invariant IDs and
hold no place for this preamble: (1) "Each claim is one bullet under its
invariant, subsection (r2db-api / MitateDB-api / Common) and axis (Control /
Evidence / Status); `- —` marks an axis with no claim." (2) "A block is one
subsection's claims (r2db-api, MitateDB-api or Common) joined by single
spaces." (Form 3.0 removed the rewritten form of sentence (2) together with the length-cap paragraph it lived in; sentence (1)'s rewritten form is the third paragraph above.)

## SI-00 Single-Compromise Containment

[history](CONTROL_MAPPING_HISTORY.md#si-00)

### r2db-api

#### Control

- `authority-topology.yaml` bounds plane reachability to a deny-by-default skeleton -- `r2db-api/config/authority-topology.yaml`, `r2db-api/src/r2db_api/topology.py:34`.
- Per-application database isolation is structural and PostgreSQL-enforced (migrations 0001-0004): `0003_provision_application.sql` creates each application's DB from `template0` -- `r2db-api/migrations/0003_provision_application.sql`.
- That script issues `REVOKE CONNECT ... FROM PUBLIC` and grants `CONNECT` only to that application's 2 dedicated roles -- `r2db-api/migrations/0003_provision_application.sql`.
- That boundary is crossable only through FDW/dblink, which no application role is granted -- not merely grant discipline -- `r2db-api/migrations/0003_provision_application.sql`.
- RLS on `public._r2db_schema_revision` is retained as defence-in-depth under that boundary (SI-01/02/03) -- `r2db-api/migrations/0003_provision_application.sql:224-225`.
- CCR-14 control-plane HTTP process is co-located with 3 checked isolation points; (a) its credential store and audit sink are structurally separate tables -- `r2db-api/migrations/0006_control_plane_http.sql:388`, `:430`.
- Control-pepper separation refuses startup when the control and application HMAC peppers are equal -- `r2db-api/src/r2db_api/credential_store.py:748`, `r2db-api/src/r2db_api/control_main.py:349`.
- (b) `r2dbsvc_api` has no grant on `control_credentials`/`control_audit` and only `INSERT` on `application_audit` (no SELECT/UPDATE/DELETE) -- `r2db-api/migrations/0007_application_audit.sql:179`.
- A third SELECT-only `r2dbsvc_auditreader` role reads both audit tables and nothing else -- `r2db-api/migrations/0007_application_audit.sql:207-208`.
- (c) `AuthorityTopology` registers the control-plane HTTP process as its own node with a structural unreachability check -- `r2db-api/src/r2db_api/topology.py:52-70`.
- The `/v1/audit/query` alias fails `AUTH_INVALID` for any control/audit credential on a data-plane host that declares `control_plane: enabled` with no control-credential store -- `r2db-api/src/r2db_api/http.py:766`.
- `/control/v1/audit/query` is the endpoint the contract's `audit_query` obligation binds, not that data-host alias (also recorded on SI-14) -- `r2db-api/src/r2db_api/control_http.py:462`.
- **Realization**: the data-plane composition root neither constructs nor imports the control-credential store -- `r2db-api/src/r2db_api/main.py`.
- That alias answers `AUTH_INVALID` because no verifier exists at all, never `CAPABILITY_UNSUPPORTED`/`FORBIDDEN`/5xx (all non-conforming) -- `r2db-api/src/r2db_api/http.py:718`.
- `0004_deprovision_application.sql` closes out an application's own live backends while taking no cluster-wide privilege at all (R-54, design `docs/design/DEPROVISION_FORCED_DROP_V0_1.md` v1.0 D-1/D-2R).
- No `GRANT` of a predefined role (`pg_signal_backend`, `pg_read_all_stats` or any other) appears anywhere in this peer's migration set -- `0004_deprovision_application.sql`.
- This peer's migration set names `pg_signal_backend` only inside comments and never names `pg_read_all_stats` -- `r2db-api/migrations/0004_deprovision_application.sql`.
- The executing role `r2dbsvc_control` is `NOSUPERUSER`, and no operator grant is a precondition of the script -- `0001_bootstrap_control_plane.sql`.
- The whole authority the new stages use is a temporary `GRANT <role> TO CURRENT_USER WITH INHERIT TRUE, SET FALSE` over that one application's own two roles -- `r2db-api/migrations/0004_deprovision_application.sql`:142-152.
- `r2dbsvc_control` created those two roles itself during `0003` and therefore already holds ADMIN OPTION on them -- `r2db-api/migrations/0004_deprovision_application.sql`.
- That grant is reached only through a pre-check that refuses the run, before anything is changed, when the database holds a connection under any role other than the application's own runtime/developer role and the executing role -- `0004`:104-115.
- Background workers (`usesysid IS NULL`) are deliberately not counted by that pre-check, and the refusal message names no role -- `0004`:104-115.
- That pre-check reads `pg_stat_activity`'s own `usename`/`usesysid`, which needs no `pg_read_all_stats` membership (design H-2) -- `r2db-api/migrations/0004_deprovision_application.sql`.
- A failed run leaves a bounded residue, not a wider authority (design §4.1): stopping at or after `ALTER DATABASE ... WITH ALLOW_CONNECTIONS false` leaves that database non-connectable with the temporary membership standing -- `0004`:166-170.
- That residue is availability lost for one application, not privilege gained: the membership covers only that application's own two roles and carries `SET FALSE` (no `SET ROLE`) -- `r2db-api/migrations/0004_deprovision_application.sql`.
- `r2dbsvc_control` undoes the membership alone with `REVOKE <role> FROM CURRENT_USER` and needs no other role to do so; re-running `0004` clears both and completes -- `r2db-api/migrations/0004_deprovision_application.sql`.

#### Evidence

- negative plane reachability against the topology declaration, and the cross-database and cross-store negatives -- `test_topology.py`, `test_cross_database_connect_is_refused_at_the_database_level`, `test_cross_store_leakage_secret_added_to_one_store_never_authenticates_the_other`.
- pepper separation at startup, and the control-plane role's grants -- `test_validate_control_pepper_separation_rejects_equal_peppers`, `test_controlplane_role_grants_match_the_design`.
- `r2dbsvc_auditreader` selects both audit tables and nothing else -- `test_auditreader_role_can_select_both_audit_tables_and_nothing_else`.
- `test_control_plane_http_reaches_only_control_and_audit`.
- the composition-root check is AST-based, parsing `main.py`'s `Import`/`ImportFrom`/`Name`/`Attribute` nodes rather than matching substrings -- `test_data_plane_composition_root_does_not_import_the_control_credential_store`.
- the deprovision path -- `r2db-api/tests/test_postgres.py::test_deprovision_succeeds_in_a_single_pass_with_a_live_runtime_role_connection`, `::test_0004_temporary_grant_uses_inherit_true_set_false`.
- an unrelated LOGIN role's open connection leaves the database, its `datallowconn`, the executing role's `inherit_option = true` membership count and the registry row intact -- `r2db-api/tests/test_postgres.py::test_deprovision_pre_check_stops_and_changes_nothing_for_an_unrelated_connected_role`.
- a re-run after the drop completes -- `r2db-api/tests/test_postgres.py::test_deprovision_completes_on_rerun_after_the_database_was_already_dropped`; the operator's own recovery from that residue is `r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md` §5 and §14, which no test exercises.

#### Status

- **Acceptance boundary**: r2db Stage 1, contract 1.6.0, was installed on the VPS on 2026-09-05 -- migrations 0001, 0002, 0005, 0006, 0007 and 0003 were applied in that order (0004 is the deprovision script and is never applied at install);
- `pg_hba`/`pg_ident` posture B was configured and external reachability on port 8443 was verified (`docs/work-orders/DEPLOY_PHASE6_20260904.md` §8, items 9-12);
- no later contract version has been deployed to that VPS since, and no production credential-store/role/grant listing beyond the runbook's own steps is recorded -- this row's own containment checks (a)-(c) remain unexercised against that instance.
- **R-54 evidence boundary**: the four deprovision claims above were measured only against throwaway local PostgreSQL 16 clusters, by the 6 tests this change set adds to `r2db-api/tests/test_postgres.py` (:377, :398, :424, :469, :530, :546);
- each of those 6 tests is pinned by a mutation of its own stage (design §6.1's one-condition-one-test rule; 6 mutations on this peer, all red);
- production evidence is `absent` -- `0004` is still never applied at install (this block's own acceptance boundary above), and nothing was applied to the VPS for R-54;
- whether `ALTER DATABASE ... WITH ALLOW_CONNECTIONS false` and `GRANT ... WITH INHERIT TRUE, SET FALSE` behave the same on a managed platform is unexercised; the place that reading is to be taken is `MitateDB-api/docs/cloud-run-cloud-sql.md` §9 item 3 (design §7).

### MitateDB-api

#### Control

- Control-plane/data-plane separation (design R-4/R-6) keeps (a) structurally separate credential tables, `credentials` vs. `control_credentials` -- `MitateDB-api/migrations/0002_registry_and_functions.sql:127`, `:169`.
- The control HMAC pepper is required to differ from the application pepper at startup -- `MitateDB-api/src/mitatedb_api/credential_store_postgres.py:149`, `MitateDB-api/src/mitatedb_api/control_composition.py:144`.
- (b) two disjoint least-privilege PostgreSQL roles bound each plane's own grants -- `MitateDB-api/migrations/0002_registry_and_functions.sql`.
- `mitatedbsvc_api` additionally holds only `INSERT` on `application_audit` (no SELECT/UPDATE/DELETE) -- `MitateDB-api/migrations/0005_application_audit.sql:225`.
- `mitatedbsvc_controlplane` gets nothing on `application_audit` -- `MitateDB-api/migrations/0005_application_audit.sql:262`.
- A third SELECT-only reader role `mitatedbsvc_auditreader` reads both audit tables -- `MitateDB-api/migrations/0005_application_audit.sql:265-266`.
- `/control/v1/audit/query` is the endpoint contract 1.4.0's `audit_query` obligation binds, not the data host's alias (also on SI-00's r2db column) -- `MitateDB-api/src/mitatedb_api/control_http.py:509`.
- This peer's data service declares `control_plane` enabled while holding no control-credential store, so that alias answers `AUTH_INVALID` -- `MitateDB-api/src/mitatedb_api/http.py:1300`.
- (c) `mitatedbsvc_provision` (CREATEDB/CREATEROLE) is held only by operator/deploy tooling and the out-of-band CLI, never by either process -- `MitateDB-api/migrations/0001_bootstrap_platform.sql:134`.
- **Realization**: structurally identical to r2db-api -- the data-plane composition root neither imports nor constructs the control-credential store -- `MitateDB-api/src/mitatedb_api/main.py`.
- This peer's `0004_deprovision_application.sql` reaches the same safety outcome, with `mitatedbsvc_provision` (`NOSUPERUSER`, `0001_bootstrap_platform.sql`) executing (design `docs/design/DEPROVISION_FORCED_DROP_V0_1.md` D-1/D-2R, R-54).
- No `GRANT` of a predefined role appears anywhere in this peer's migration set either, and `pg_signal_backend` occurs in it only inside comments -- `MitateDB-api/migrations/0004_deprovision_application.sql`.
- The only added authority is the temporary `GRANT <role> TO CURRENT_USER WITH INHERIT TRUE, SET FALSE` over that application's own two roles -- `MitateDB-api/migrations/0004_deprovision_application.sql`:134-144.
- `mitatedbsvc_provision` created those two roles itself during `0003` -- `MitateDB-api/migrations/0004_deprovision_application.sql`.
- The per-membership `INHERIT TRUE` is what makes that grant effective at all here: `mitatedbsvc_provision` is `NOINHERIT`, so a membership granted without it confers nothing on the role -- `MitateDB-api/migrations/0004_deprovision_application.sql`.
- `SET FALSE` withholds `SET ROLE`, which this path never needs -- `MitateDB-api/migrations/0004_deprovision_application.sql`.
- The same pre-check stands ahead of that grant, inside the `\if :{?database_name}` branch, so a registration-only registry row is untouched by it -- `0004`:96-107.
- That pre-check stops the run before anything is changed if any role other than this application's own runtime/developer role and the executing role holds a connection -- `0004`:96-107.
- Background workers (`usesysid IS NULL`) are not counted by that pre-check, and the refusal message names no role -- `0004`:96-107.
- The residue a failure leaves is the same bounded one (design §4.1): stopping at or after `ALTER DATABASE ... WITH ALLOW_CONNECTIONS false` leaves that database non-connectable with the self-grant standing -- `0004`:158-162.
- That self-grant is removable by `mitatedbsvc_provision` alone (`REVOKE <role> FROM CURRENT_USER`, since it holds ADMIN OPTION over the roles it granted) and is cleared by re-running `0004` -- `0004`:158-162.

#### Evidence

- the two pepper env vars configured identically -- `test_pepper_separation_detects_the_two_env_vars_configured_identically`.
- the application-plane role has no privilege on `control_credentials`, read with bare `psycopg` connections -- `test_application_plane_role_has_no_privilege_on_control_credentials`.
- `mitatedbsvc_auditreader` selects both audit tables and nothing else -- `test_auditreader_role_can_select_both_audit_tables_and_nothing_else`.
- an AST check on identifiers, not string literals, over the data-plane composition root -- `test_data_plane_composition_root_does_not_import_the_control_credential_store`.
- the deprovision path -- `MitateDB-api/tests/test_postgres.py::test_deprovision_succeeds_in_a_single_pass_with_a_live_runtime_role_connection`, `::test_0004_temporary_grant_uses_inherit_true_set_false`.
- its pre-check, and a re-run after the drop -- `MitateDB-api/tests/test_postgres.py::test_deprovision_pre_check_stops_and_changes_nothing_for_an_unrelated_connected_role`, `::test_deprovision_completes_on_rerun_after_the_database_was_already_dropped`.

#### Status

- MitateDB has no Python topology-declaration class equivalent to r2db's `AuthorityTopology`;
- `docker/authority-topology.yaml` is a non-secret intent skeleton only, not evidence.
- **Deployment precondition (R-1, cloudsqlsuperuser bypass)**: every application-facing role must be created only via migration SQL's `CREATE ROLE`, never Cloud SQL's Users API, which grants `cloudsqlsuperuser` membership and bypasses `REVOKE CONNECT ... FROM PUBLIC`;
- the fail-closed backstop is verified locally by `test_provisioning_guard_detects_an_unexpected_group_membership`, and runbook/real-Cloud-SQL verification is `docs/cloud-run-cloud-sql.md` §3.3/§9.
- **Acceptance boundary**: local-cluster evidence only -- on the one real Cloud SQL deployment, role/database DDL and `log_statement=none` have passed, but the deprovision path and the cloudsqlsuperuser probe remain unexercised, production evidence stays open.
- That AST check does not cover this peer's data-plane env still naming the control-credential pepper -- a separate, still-open asymmetry (ledger item L4-13, still open).
- The `GRANT pg_signal_backend TO mitatedbsvc_provision` applied at the 2026-09-01 deployment changed nothing, because the grantee is `NOINHERIT` (design M-3), and the runbook's §9 item 3 no longer asks for it.
- **Disclosed availability/diagnosis cost**: while that residue stands, `ops verify-declarations` reads the application as having every upgrade pending and fails, and `ops inventory` judges it `unknown`.
- `ops upgrade-applications` fails on that row too (design F-3, read from `MitateDB-api/src/mitatedb_api/ops.py`, with no test of its own) -- a disclosed availability and diagnosis cost, not a privilege change.
- **R-54 evidence boundary**: the four deprovision claims above were measured only against throwaway local PostgreSQL 16 clusters, by the 6 tests this change set adds to `MitateDB-api/tests/test_postgres.py` (:1916, :1937, :1964, :2008, :2068, :2084);
- each of those 6 tests is pinned by a mutation of its own stage (design §6.1; 6 mutations on this peer, all red);
- Cloud SQL evidence stays `absent` -- the deprovision path is still unexercised there (this block's own acceptance boundary above);
- `MitateDB-api/docs/cloud-run-cloud-sql.md` §9 item 3 is now the place that reading is to be taken, and asks for a deprovision run against an application holding a live connection instead of the superseded `pg_signal_backend` grant;
- whether Cloud SQL's own management connections (a `cloudsqladmin`-owned session) would themselves trip the pre-check is `absent` too -- no control anywhere in this repository depends on `cloudsqladmin`; every occurrence of the name is prose recording this same evidence gap.

### Common

#### Control

- —

#### Evidence

- CCR-14's control-plane authority boundary, condition C-14, on SI-00/SI-02/SI-03/SI-08 -- `conformance-tests/test_c14_authority_boundary.py`.
- all four adapters take that check's PROVIDED branch: each declares a real control-plane surface as `enabled`, checked fail-closed in both directions -- `conformance-tests/test_c14_authority_boundary.py`.
- the data-host side of obligation (b), unconditional, all four plugs, conformance port v1.9 -- `conformance-tests/test_c09_audit_evidence.py::test_c09_data_plane_host_audit_query_alias_rejects_control_credential_unless_cohosted`.
- co-hosting is judged by `adapter.surfaces_cohosted(document)`, a module-level port helper deriving it from a 1.6.0+ peer's own declared `surfaces.data.base_url`/`surfaces.control.base_url` origins, never from an adapter self-report -- `conformance-tests/adapter.py`.
- that helper's own `True` branch runs against synthetic `CapabilityDocument` fixtures, independent of whether any real deployment co-hosts -- `conformance-tests/test_c09_audit_evidence.py::test_surfaces_cohosted_resolves_true_only_for_matching_origins_and_false_otherwise`.

#### Status

- **No cited evidence for the lateral/control-plane path**: no test is named for that part of this block's controls; version 2.25's uncited wording is in the history file.
- All four registered plugs currently resolve `False` there (no currently-registered deployment co-hosts both surfaces on the same origin), so the `provided` branch of `test_c09_data_plane_host_audit_query_alias_rejects_control_credential_unless_cohosted` remains unreached by any registered plug;
- that residual limit is restated, not closed, in the C-09 row of `conformance-tests/CONDITIONS.md`.

## SI-01 Application Isolation

[history](CONTROL_MAPPING_HISTORY.md#si-01)

### r2db-api

#### Control

- Cell resolution reads `AuthContext.application_id` alone, never a client-supplied value -- `r2db-api/src/r2db_api/service.py`:314.
- `PostgresCell` confines each application to its own PostgreSQL database, whose name the control plane assigns and never derives from client input (architecture §8 "D-3 改訂", database-per-application) -- `r2db-api/src/r2db_api/postgres.py`:982.
- `PostgresCell` only ever connects over that application's own `runtime`/`developer` DSNs -- `r2db-api/src/r2db_api/postgres.py`:1006-1010.
- `PostgresCell` verifies every identifier against that database's live `information_schema` catalog (`_load_catalog`) before composing SQL, so a name collision reaches no other application's tables -- `r2db-api/src/r2db_api/postgres.py`:1128.

#### Evidence

- server-bound scope, and pool isolation -- `r2db-api/tests/test_foundation.py::test_server_bound_scope_and_isolation`, `test_pool_never_leaks_role_or_schema_across_applications`.
- against a real local PostgreSQL 16 cluster -- `r2db-api/tests/test_postgres.py`, including `test_cross_database_connect_is_refused_at_the_database_level`.

#### Status

- This is local/test-cluster evidence;
- r2db Stage 1, contract 1.6.0, was installed on the VPS on 2026-09-05 with migrations 0001, 0002, 0005, 0006, 0007 and 0003 applied in that order (0004 is the deprovision script and is never applied at install) (`docs/work-orders/DEPLOY_PHASE6_20260904.md` §8, items 9-12);
- the same database-per-application `REVOKE CONNECT ... FROM PUBLIC` grant now exists there for the one provisioned application (`sandbox`);
- cross-application connect-refusal itself has not been re-exercised against that instance (only one application is provisioned there), so production database-grant isolation is configured but not yet verified.

### MitateDB-api

#### Control

- Cell resolution reads the authenticated Principal alone -- `MitateDB-api/src/mitatedb_api/service.py`:98.
- `PostgresBackend` confines each application to its own PostgreSQL database, named and allocated by the control plane and never derived from client input (design R-1) -- `MitateDB-api/src/mitatedb_api/backend_postgres.py`:326.
- `MitateDB-api/migrations/0003_provision_application.sql` issues `REVOKE CONNECT ON DATABASE ... FROM PUBLIC` and grants `CONNECT` only to that application's own `runtime`/`developer` roles.
- `0004_deprovision_application.sql` reverses that grant -- `MitateDB-api/migrations/0004_deprovision_application.sql`.
- each served application's `PostgresBackend` builds and owns its own runtime and developer pool; no process-wide registry hands out a pool by key -- `MitateDB-api/src/mitatedb_api/backend_postgres.py:331`, `:332`.
- the process-wide weak set of live pools is read only by the idle sweep, which closes stale idle connections and never looks a pool up -- `MitateDB-api/src/mitatedb_api/pool.py:87`, `:438`.

#### Evidence

- the cell is resolved only from the authenticated Principal, on the SQLite backend -- `MitateDB-api/tests/test_foundation.py::test_application_scope_is_server_bound`.
- against a real local PostgreSQL 16 cluster -- `MitateDB-api/tests/test_postgres.py::test_cross_database_connect_is_refused_at_the_database_level`.
- one served application's backend holds two role pools of `role_pool_size(thread_limit)` connections -- `MitateDB-api/tests/test_main.py::test_build_app_sizes_each_applications_role_pools_from_the_thread_limit`.
- the http adapter builds the same two pools -- `MitateDB-api/tests/test_r78_pool_wait_stats.py::test_http_adapter_builds_each_applications_role_pools_like_the_composition_root`.

#### Status

- **Deployment precondition (cloudsqlsuperuser bypass, shared with the SI-00 row above)**: this isolation is a PostgreSQL `CONNECT`-grant boundary, which a Cloud-SQL-Users-API-created role bypasses entirely (Cloud SQL's own `cloudsqlsuperuser` membership);
- `cloud-run-cloud-sql.md` §3.3 states this as a hard runbook rule, and the fail-closed backstop is `MitateDB-api/tests/test_postgres.py::test_provisioning_guard_detects_an_unexpected_group_membership`.
- Local/test-cluster evidence only -- Cloud SQL production database-grant isolation is `absent` until `cloud-run-cloud-sql.md` §9 is run once;
- on the one real deployment made so far, the DDL itself passed but the cross-database-connect-refused behavior has not been re-exercised against that instance and deprovision remains unexercised, so this isolation stays open, not confirmed, in production.
- **Per-application pool ownership holds by construction**: that each application's pools belong to that application's backend is structure only; no dedicated test drives one application's request toward another application's pool (the tests above observe the pools' size, not their ownership).

### Common

#### Control

- C-30 query cursor binding -- a cursor whose recorded Application, entity, where or order_by differs from the request presenting it is refused before execution (`r2db-api/src/r2db_api/paging.py`, `MitateDB-api/src/mitatedb_api/paging.py`).

#### Evidence

- condition C-01 on all four adapters -- `conformance-tests/test_c01_scope_binding.py::test_positive_control_scope_is_bound_and_legitimate_access_succeeds`, `::test_cross_application_entity_is_unreachable`, `::test_cross_application_denial_does_not_disclose_existence`.
- A cursor issued for one Application or entity is refused for another with no existence signal, and one reused under a different where or order_by is refused: `test_c30_keyset_paging.py::test_c30_cross_application_cursor_is_refused`, `::test_c30_cursor_binding`.

#### Status

- —

## SI-02 Control Plane Isolation

[history](CONTROL_MAPPING_HISTORY.md#si-02)

### r2db-api

#### Control

- `AuthorityTopology` denies application/developer reachability to control/provisioning -- `r2db-api/src/r2db_api/topology.py:46-48`.
- `0001_bootstrap_control_plane.sql` creates the provisioning authority `r2dbsvc_control` as a distinct `NOSUPERUSER`/`NOINHERIT` role only an operator holds a credential for -- `0001_bootstrap_control_plane.sql`.
- That role deliberately carries `CREATEDB`/`CREATEROLE` for database-per-application provisioning (§5.3 C-2) -- exactly why the API process never holds it -- `r2db-api/migrations/0001_bootstrap_control_plane.sql`.
- `PostgresCell` never embeds a control-plane DSN, and only ever opens connections as an application's already-provisioned `runtime`/`developer` role -- `r2db-api/src/r2db_api/postgres.py:958`.
- CCR-14's `/control/v1` surface carries the same 3 isolation points as SI-00's block: separate stores, distinct login roles, its own topology node -- `r2db-api/src/r2db_api/control_http.py:446-463`.
- Within the control plane, `role="control"` is separated from `role="audit"` (read-only) structurally -- `r2db-api/src/r2db_api/control_plane.py:132`.
- That separation is fail-closed by enumeration: every one of the 8 remaining operations refuses an `audit` principal with `FORBIDDEN` -- `r2db-api/src/r2db_api/control_plane.py:1272`.
- The per-application platform-upgrade bulk apply (`upgrade-applications`/`upgrade-status`) and the 4 declaration subcommands reach each application's database only as `r2dbsvc_control` over `R2DB_CONTROL_DSN` -- `r2db-api/src/r2db_api/ops.py:130`.
- No API process holds `R2DB_CONTROL_DSN` -- `r2db-api/src/r2db_api/main.py`.
- C-14 separate credential stores fail cross-plane authentication at the lookup: an application verifier is absent from `control_credentials`, so no secondary check can be misconfigured away -- `r2db-api/src/r2db_api/credential_store.py:869`.

#### Evidence

- negative reachability against the topology declaration -- `test_topology.py`.
- the second matrix is derived from the real wire route table -- `test_audit_role_forbidden_fail_closed_on_every_other_control_endpoint`, `test_audit_role_http_authorization_matrix_all_13_endpoints`.
- the bulk apply, and the platform timeouts -- `test_upgrade_applications_exit_codes`, `test_set_platform_timeouts_places_the_same_two_values_on_both_writer_roles`.

#### Status

- **Acceptance boundary**: r2db Stage 1, contract 1.6.0, was installed on the VPS on 2026-09-05 -- provisioning (migrations 0001, 0002, 0005, 0006, 0007 and 0003, applied in that order; 0004 is the deprovision script and is never applied at install) has run;
- `pg_hba`/`pg_ident` posture B was configured, and external reachability on port 8443 was verified (`docs/work-orders/DEPLOY_PHASE6_20260904.md` §8, items 9-12);
- socket-binding/credential-file-access evidence beyond the runbook's own steps is not separately recorded, and no later contract version has been deployed there since.

### MitateDB-api

#### Control

- Separate credential stores (`credentials` vs. `control_credentials`, distinct roles and peppers) keep an application verifier out of `control_credentials`, and vice versa -- `MitateDB-api/migrations/0002_registry_and_functions.sql:169`.
- Cross-plane authentication therefore fails at the lookup itself (`ControlPlaneService._locate_credential`), never at a secondary check that could be misconfigured away -- `MitateDB-api/src/mitatedb_api/control_plane.py:1538`.
- `ControlPlaneService` fixes the order: rate-limit -> authenticate -> must_rotate -> role=control denial -> shape -> target-existence -> bounds -> destructive-confirmation -> execute+audit -- `MitateDB-api/src/mitatedb_api/control_plane.py:1227`.
- That order guarantees an unauthenticated/wrong-plane request never reaches target resolution -- `MitateDB-api/src/mitatedb_api/control_plane.py:1777`.
- `issue_credential` refuses `role="control"` unconditionally, before resolving whether the named application even exists -- `MitateDB-api/src/mitatedb_api/control_plane.py:1800-1801`.
- The `audit` role is narrowed symmetrically with r2db's own bundle -- `MitateDB-api/src/mitatedb_api/control_plane.py:94`, `:1452`.
- `upgrade-applications`/`upgrade-status` and the 4 declaration subcommands all require `MITATEDB_PROVISION_DSN` -- `MitateDB-api/src/mitatedb_api/ops.py:381`.
- `list-applications` requires no provisioning DSN and reaches no application database -- `MitateDB-api/src/mitatedb_api/ops.py`:392.
- Per-application upgrade state is deliberately not published on any HTTP surface (requester ruling U-1, design §5) -- `MitateDB-api/src/mitatedb_api/control_http.py`.

#### Evidence

- `role` shape and `role=control` -- `test_issue_credential_role_shape_is_validated_before_capability_check`, `test_role_control_refused_before_target_resolution_against_real_postgres`.
- an `audit` principal on the control endpoints -- `test_audit_role_forbidden_fail_closed_on_every_other_control_endpoint`, `test_audit_role_accepted_on_read_endpoints_and_forbidden_on_a_write_endpoint_against_real_postgres`.
- the provisioning DSN, on the bulk apply and on the declaration subcommands -- `test_upgrade_applications_usage_error_without_provision_dsn`, `test_all_four_subcommands_require_provision_dsn`.

#### Status

- **acceptance boundary**: production network/IAM evidence for that split is absent until deployed, local/test-cluster evidence only.
- **Network-layer isolation is a deployment default, not enforced code**: two Cloud Run services with separate IAM invoker bindings add it on top of credential-store separation only while that default deployment holds -- `MitateDB-api/docs/cloud-run-cloud-sql.md:1187`.
- **The control service's inability to invoke this path is a deployment assumption**: it holds only while the Cloud Run services' environments carry no such variable; no code or test pins that -- `MitateDB-api/docs/cloud-run-cloud-sql.md:1141`.

### Common

#### Control

- —

#### Evidence

- CCR-14's cross-plane fail-closed boundary, condition C-14; the adapter state is in the SI-00 row above -- `conformance-tests/test_c14_authority_boundary.py`.

#### Status

- **No cited evidence for cross-plane denial**: no test is named for this block's control-plane denial controls; version 2.25's uncited wording is in the history file.

## SI-03 Runtime/Developer Separation

[history](CONTROL_MAPPING_HISTORY.md#si-03)

### r2db-api

#### Control

- `ApplicationCell.apply_schema` requires developer context -- `r2db-api/src/r2db_api/backend.py:125-129`, `r2db-api/src/r2db_api/structured.py:178-179`.
- The schema catalog rejects unknown runtime entity/fields -- `r2db-api/src/r2db_api/structured.py:884`.
- The topology has distinct data and development planes -- `r2db-api/src/r2db_api/topology.py:27-28`.
- `PostgresCell.apply_schema` checks the same `developer: bool` flag and executes every schema-changing statement only over the `developer_dsn` connection pool -- `r2db-api/src/r2db_api/postgres.py`:2081-2115.
- The DML-only `runtime` role has no `CREATE` grant on the schema at all: `REVOKE ALL ON SCHEMA public FROM PUBLIC`, a `USAGE`-only grant to it, and `ALTER DEFAULT PRIVILEGES` -- `migrations/0003_provision_application.sql`.
- Those grants are a second, DB-enforced layer under the application-level `developer: bool` check -- `migrations/0003_provision_application.sql`.

#### Evidence

- `test_runtime_developer_separation_and_structured_validation`, `test_runtime_unknown_entity_and_failed_mutation_leave_no_ghost`, exercised locally by `r2db-api/tests/test_postgres.py`.

#### Status

- the distinct production Runtime/Developer DB authority itself was realized on the VPS by the same 2026-09-05 Stage 1 install (`docs/work-orders/DEPLOY_PHASE6_20260904.md` §8, items 9-12);
- that install applied migrations 0001, 0002, 0005, 0006, 0007 and 0003 in that order -- 0004 is the deprovision script and is never applied at install;
- the runtime-role-has-no-CREATE-grant behavior has not been separately re-exercised against that instance.

### MitateDB-api

#### Control

- `ApplicationRuntime` has no schema-mutation method -- `MitateDB-api/src/mitatedb_api/cell.py`:3590.
- `ApplicationCell._require_developer` gates every schema-changing call -- `MitateDB-api/src/mitatedb_api/cell.py`:3570.

#### Evidence

- `test_developer_schema_and_runtime_crud`.

#### Status

- The API method/role-check evidence above is preliminary and local only.
- distinct production Runtime/Developer DB authority TBD.

### Common

#### Control

- —

#### Evidence

- the in-band `role=control` issuance refusal (a third, non-runtime/developer role never silently granted), condition C-14; the adapter state is in the SI-00 row above -- `conformance-tests/test_c14_authority_boundary.py`.

#### Status

- **No cited evidence for the privilege separation**: no test is named for this block's runtime/developer privilege controls; version 2.25's uncited wording is in the history file.
- A page cursor carries no authority: it encodes only ordering values of rows the client already received, and never role, credential or scope.

## SI-04 No Arbitrary DB Commands

[history](CONTROL_MAPPING_HISTORY.md#si-04)

### r2db-api

#### Control

- `structured.py` exposes only enumerated operations and no native command API -- `r2db-api/src/r2db_api/structured.py`.
- `_run` is the single execution choke point every statement passes through, typed to accept only `psycopg.sql.Composed`/`psycopg.sql.SQL` and raising `TypeError` on any `str` -- `r2db-api/src/r2db_api/postgres.py`:234-240.
- `PostgresCell` has no method, public or private, that can pass a raw command string to PostgreSQL -- `r2db-api/src/r2db_api/postgres.py`:234.

#### Evidence

- `test_runtime_developer_separation_and_structured_validation`, against a real PostgreSQL cluster by `r2db-api/tests/test_postgres.py` and the `r2db-api-http` conformance adapter.

#### Status

- **No cited evidence from the contract surface review**: no test and no file record that review; version 2.25's uncited wording is in the history file.

### MitateDB-api

#### Control

- `ApplicationCell` exposes structured-only methods -- `MitateDB-api/src/mitatedb_api/cell.py`:508.
- No command-text execution method exists on the PostgreSQL backend; only `Composed` objects reach the database -- `MitateDB-api/src/mitatedb_api/backend_postgres.py:295`.

#### Evidence

- `test_no_arbitrary_sql_and_identifier_validation`.

#### Status

- —

### Common

#### Control

- —

#### Evidence

- four adapters, condition C-03 -- `conformance-tests/test_c03_structured_injection.py::test_no_native_command_surface_is_exposed`.

#### Status

- —

## SI-05 Validated Structured Operations

[history](CONTROL_MAPPING_HISTORY.md#si-05)

### r2db-api

#### Control

- `validate_identifier` and the operator allowlist bound every structured request, together with the typed mutation shape and the service checks -- `r2db-api/src/r2db_api/structured.py`, `r2db-api/src/r2db_api/identifier_rules.py:50`.
- `r2db-api/src/r2db_api/postgres.py` composes identifiers only via `psycopg.sql.Identifier` -- `r2db-api/src/r2db_api/postgres.py`:1897.
- That composition runs after both the shared `structured.py` syntax allowlist and a second check against the schema's live `information_schema` catalog (`_load_catalog`) -- `r2db-api/src/r2db_api/postgres.py`:1128.
- `PostgresCell` binds every value as a server-side parameter (`psycopg.sql.Placeholder`/`Jsonb`) rather than string interpolation -- `r2db-api/src/r2db_api/postgres.py`:1904.
- CCR-13 (`docs/design/R2DB_CCR13_STORAGE_V1.md` R-7) extends validation from identifiers/shapes to value domains -- `r2db-api/src/r2db_api/value_types.py:69`.
- Typed-column values (`bigint`/`double precision`/`boolean`/`text`) are checked against the declared type and bound natively -- `r2db-api/src/r2db_api/value_types.py:69`.
- A shared range/NUL-byte check runs ahead of execution, so a value PostgreSQL would reject at runtime fails deterministically instead -- `r2db-api/src/r2db_api/value_nul.py:7`.

#### Evidence

- the query/mutation paths and the DDL paths (`create_entity`/`add_field`), where the catalog cannot reject an identifier that does not exist yet -- `r2db-api/tests/test_postgres.py`.

#### Status

- Exercised against a real local PostgreSQL 16 cluster only -- no production evidence.

### MitateDB-api

#### Control

- `identifiers.py` validation, quoted identifiers and bound values in `cell.py` -- `MitateDB-api/src/mitatedb_api/identifiers.py:22`, `:75`.

#### Evidence

- `test_no_arbitrary_sql_and_identifier_validation`.

#### Status

- —

### Common

#### Control

- —

#### Evidence

- four adapters, condition C-03 -- `conformance-tests/test_c03_structured_injection.py::test_identifier_positions_reject_every_payload`, `::test_value_positions_round_trip_or_deny`, `::test_structural_integrity_across_corpus`.
- CCR-13 declaration/behavior agreement, conditions C-12 and C-17, on all four adapters -- `test_c12_capability_agreement.py`, `test_c17_declaration_agreement.py`.
- the socket-plug branch is narrow by construction: `transport_kind == "socket"` only, wire-carried positions only, and only for `httpx.LocalProtocolError` or an `UNCLASSIFIED` non-problem+json failure, never an unreachable peer -- `conformance-tests/test_c03_structured_injection.py`.
- body-carried positions still demand a genuine contract-coded denial on every plug -- `conformance-tests/test_c03_structured_injection.py::test_c03_wire_rejection_never_applies_to_a_body_carried_position`, `::test_c03_wire_rejection_never_applies_to_a_reachability_failure`.
- C-28, on all six adapters: in a baseline-only turn, an out-of-enum value and a null in a `nullable: false` field are each refused as `VALIDATION_FAILED` naming that declaration -- `conformance-tests/test_c28_baseline_turn.py::test_c28_baseline_turn`.

#### Status

- **Phase 10 socket plugs -- disclosed**: C-03's corpus now also runs on the two real-socket plugs, where a URL-path-carried identifier payload can be refused by the client's own HTTP/1.1 layer (h11) before any byte reaches the peer;
- the suite counts that wire refusal as a rejection, so for the `entity` position on a socket plug the denial is not always the peer's own validation.

## SI-06 Server-Bound Credential Scope

[history](CONTROL_MAPPING_HISTORY.md#si-06)

### r2db-api

#### Control

- `CredentialStore.authenticate`/`assert_active` derive an immutable `AuthContext` from stored state alone -- `r2db-api/src/r2db_api/auth.py:321`, `:370`.
- CCR-14 `ControlCredentialStore`/`PostgresControlCredentialStore` derive an immutable `ControlAuthContext` (`credential_id`/`must_rotate`) from stored verifier state alone -- `r2db-api/src/r2db_api/auth.py:590`.
- That derivation never reads a client-supplied field -- `r2db-api/src/r2db_api/credential_store.py:878`.
- That control store rejects disabled/revoked/must-rotate-exceeded state like the application-plane store -- `r2db-api/src/r2db_api/auth.py:620`.
- The control secret is bound server-side to its own dedicated HMAC pepper, required to differ from the application pepper -- `r2db-api/src/r2db_api/credential_store.py:748`.
- The control secret is exposed only as an opaque handle, never a raw secret past authentication -- `r2db-api/src/r2db_api/control_plane.py:875`.
- **`must_rotate` exposure**: `list_credentials` rows for a control-table credential carry their real `must_rotate` value -- `r2db-api/src/r2db_api/control_plane.py:495`.
- Application rows never carry that key: the concept does not exist for them -- `r2db-api/src/r2db_api/control_plane.py:367`.
- **`audit` role**: the `control_credentials.role` CHECK constraint defines a second, weaker, distributable control-credential scope narrowed to the 3 read-only endpoints -- `r2db-api/migrations/0006_control_plane_http.sql:376-388`.
- Issuance of that role is ceremony-only (out-of-band CLI, single tx = issue+rotate, distributed already `must_rotate=false`), never in-band -- `r2db-api/src/r2db_api/ops.py:130`.
- An `audit` principal is fail-closed on the other 8 write operations and durably audited -- `r2db-api/src/r2db_api/control_plane.py:132`, `:1272`.
- **Revoke-gate role filter**: the "sole remaining control credential" gate (SI-09) filters to `role=="control"` rows only, so an `audit` row neither masks nor is mistaken for the last one -- `r2db-api/src/r2db_api/control_plane.py:966`.
- Revoking an `audit` credential itself is never gated -- `r2db-api/src/r2db_api/control_plane.py:929`.
- **Per-application issuance freeze**: `applications.issuance_frozen` is CLI-only and non-destructive -- `r2db-api/src/r2db_api/control_plane.py:414-417`.
- `issue_credential` against a frozen application is refused `FORBIDDEN`, evaluated after the `role=control` capability refusal, per the fixed evaluation order -- `r2db-api/src/r2db_api/control_plane.py:830-842`.

#### Evidence

- server-bound scope, and the issued secret -- `test_server_bound_scope_and_isolation`, `test_issued_secret_appears_only_in_the_response`.
- the control-credential store -- `test_control_credential_parity_add_authenticate_rotate_must_rotate_both_impls`, `test_control_authenticate_fails_closed_when_platform_db_unreachable`.
- the second matrix is derived from the real wire route table -- `test_audit_role_forbidden_fail_closed_on_every_other_control_endpoint`, `test_audit_role_http_authorization_matrix_all_13_endpoints`.
- the revoke gate -- `test_revoke_gate_active_audit_credential_does_not_mask_last_active_control_credential`.
- the issuance freeze, and its precedence -- `test_issuance_freeze_forbids_then_unfreeze_allows_again`, `test_issuance_freeze_precedence_role_control_refused_before_freeze_check`.

#### Status

- —

### MitateDB-api

#### Control

- `CredentialStore.authenticate` derives Application/role from stored credential state -- `MitateDB-api/src/mitatedb_api/auth.py:388`.
- **Control credential**: `control_auth.ControlCredentialStore`/`PostgresControlCredentialStore` derive an immutable `ControlPrincipal` (`credential_id`/`must_rotate`) from stored verifier state -- `MitateDB-api/src/mitatedb_api/control_auth.py:302`.
- That control store is bound to its own dedicated pepper, required to differ from the application pepper -- `MitateDB-api/src/mitatedb_api/control_auth.py:110-113`, `MitateDB-api/src/mitatedb_api/credential_store_postgres.py:149`.
- **`must_rotate` exposure**: `list_credentials` merges application and control rows so a control-table credential's real `must_rotate` value is exposed, symmetric with r2db -- `MitateDB-api/src/mitatedb_api/control_plane.py:1124`.
- **`audit` role**: issuance is ceremony-only (single tx = issue+rotate) -- `MitateDB-api/src/mitatedb_api/ops.py:802`.
- An `audit` principal is fail-closed with durable audit on the 8 write endpoints and allowed on exactly the 3 read endpoints -- `MitateDB-api/src/mitatedb_api/control_plane.py:94`, `:1452`.
- **Revoke-gate role filter and issuance freeze** apply from the start on this peer, symmetric with r2db's own bundle -- `MitateDB-api/src/mitatedb_api/control_plane.py:1967`, `:605`.

#### Evidence

- parity across both implementations -- `test_issue_then_authenticate_succeeds`, `test_revoke_is_terminal_enable_cannot_resurrect_it`.
- the freeze through the CLI, and, uniquely on this peer, an in-memory rollback path -- `test_ops.py::test_cli_freeze_issuance_then_unfreeze_round_trips`, `test_in_memory_issuance_freeze_rolls_back_with_its_own_unit_of_work`.
- server-bound scope, and `list_credentials` -- `test_application_scope_is_server_bound`, `test_list_credentials_merges_application_and_control_rows`.
- an `audit` principal on the control endpoints -- `test_audit_role_forbidden_fail_closed_on_every_other_control_endpoint`, `test_audit_role_accepted_on_read_endpoints_and_forbidden_on_a_write_endpoint_against_real_postgres`.
- the revoke gate, and the freeze's precedence -- `test_revoke_gate_active_audit_credential_does_not_mask_last_active_control_credential`, `test_issuance_freeze_precedence_role_control_refused_before_freeze_check`.

#### Status

- —

### Common

#### Control

- Both peers' bearer is the locator form `<credential_id>.<secret_part>`, an opaque complete bearer at the contract level -- `r2db-api/src/r2db_api/auth.py:27`, `MitateDB-api/src/mitatedb_api/credential_wire.py:92`.
- Authentication looks up the row by the locator's `credential_id` and then compares the verifier with `hmac.compare_digest` -- **the verifier is never used as a lookup key** -- `r2db-api/src/r2db_api/auth.py:355`.
- `auth.split_bearer_locator` / MitateDB's `credential_wire.split_bearer_locator` split the bearer exactly once, inside the store -- `r2db-api/src/r2db_api/auth.py:27`, `MitateDB-api/src/mitatedb_api/credential_wire.py:92`.
- A malformed bearer (no `.`, an empty half, or a NUL) fails closed before any lookup, `AUTH_INVALID` uniformly (SI-10) -- `MitateDB-api/src/mitatedb_api/credential_wire.py:92`.
- That denial is durably audited as `authentication_denied` with an unknown actor (SI-14) -- `r2db-api/src/r2db_api/service.py`:219.
- An unknown credential id still runs `compare_digest` against a dummy verifier so no timing difference leaks -- `r2db-api/src/r2db_api/auth.py:24`, `MitateDB-api/src/mitatedb_api/auth.py:36`.

#### Evidence

- the shared dummy verifier on both peers -- `test_authenticate_methods_use_the_shared_dummy_verifier_for_unconditional_compare_digest`.
- condition C-01 on all four adapters -- `conformance-tests/test_c01_scope_binding.py::test_must_deny_vectors_are_denied_with_contract_codes`, `::test_must_ignore_vectors_leave_scope_and_other_app_unchanged`.
- same four adapters -- `conformance-tests/test_c01_scope_binding.py::test_structurally_absent_vectors_have_no_forbidden_parameters`, `::test_runtime_credential_cannot_self_elevate_to_schema_authority`.

#### Status

- —

## SI-07 Compromised Credential Containment

[history](CONTROL_MAPPING_HISTORY.md#si-07)

### r2db-api

#### Control

- Topology deny rules bound where a stolen credential can reach -- `r2db-api/src/r2db_api/topology.py:46-48`.
- Per-credential role/scope records bound what it can do once it arrives -- `r2db-api/src/r2db_api/auth.py:143`.

#### Evidence

- —

#### Status

- **No cited evidence for topology/isolation containment**: no test is named for this block's controls; version 2.25's uncited wording is in the history file.
- production containment evidence not yet present.

### MitateDB-api

#### Control

- **Control-credential-scoped compromise containment**: a compromised control credential is bounded to (i) application credentials it issued or rotated during the compromise window -- `MitateDB-api/src/mitatedb_api/control_plane.py:1777`.
- `ControlPlaneService.revoke_credential` applies no confirmation to an application-credential target, so (ii) the availability harm from any application credential it revoked is ungated -- `MitateDB-api/src/mitatedb_api/control_plane.py:1921`.
- A compromised control credential never reaches Application data or the `mitatedbsvc_provision` provisioning/deprovisioning surface, a wholly separate DSN no control-plane process holds -- `MitateDB-api/src/mitatedb_api/ops.py:381`.
- `role=control` issuance has exactly one path, the out-of-band `bootstrap`/`reset` ceremony -- no in-band operation reaches it (`_deny_role_control`, evaluated before target resolution) -- `MitateDB-api/src/mitatedb_api/control_plane.py:1494`.
- `reset` revokes every existing control credential unconditionally and mints exactly one new one atomically -- `MitateDB-api/src/mitatedb_api/ops.py:825` (procedure: `MitateDB-api/docs/CONTROL_PLANE_COMPROMISE_PLAYBOOK.md`).
- **`audit`-credential compromise** is a strictly narrower class, bounded to read-only disclosure of `list_applications`/`list_credentials`/`control_capabilities` (exposure on SI-06/SI-10) -- `MitateDB-api/src/mitatedb_api/control_plane.py:94`.
- An `audit` credential cannot issue, rotate, revoke, register, enable, or disable anything (fail-closed on all 8 write endpoints), so its compromise carries none of the (i)/(ii) harms above -- `MitateDB-api/src/mitatedb_api/control_plane.py:1452`.
- `reset`'s unconditional revoke-all also covers every live `audit` row, same ceremony -- `MitateDB-api/src/mitatedb_api/ops.py:825`.

#### Evidence

- control-plane service gates -- `MitateDB-api/tests/test_control_plane_service.py::test_revoke_application_credential_is_never_gated`, `::test_issue_credential_role_shape_is_validated_before_capability_check`.
- against real PostgreSQL; the same test covers the `audit` rows -- `MitateDB-api/tests/test_ops.py::test_reset_with_the_echoed_phrase_revokes_everything_and_mints_one_new_credential`.
- `test_audit_role_forbidden_fail_closed_on_every_other_control_endpoint`.

#### Status

- —

### Common

#### Control

- —

#### Evidence

- —

#### Status

- **No cited evidence for stolen-credential scenarios**: no test is named for this block's containment controls; version 2.25's uncited wording is in the history file.

## SI-08 Bounded Resource Consumption

[history](CONTROL_MAPPING_HISTORY.md#si-08)

### r2db-api

#### Control

- `ResourceLimits` declares a finite bound for every required class -- atomic credential-rate window, iterative request/depth checks, structured batch/result/schema checks, wall-clock deadline -- `r2db-api/src/r2db_api/limits.py:11`.
- the served data plane counts `requests_per_minute` in `0015`'s row under its row lock; the in-memory window runs only where no rate row is wired -- `r2db-api/src/r2db_api/service.py:656`, `r2db-api/src/r2db_api/main.py:693`.
- `RequestByteBoundMiddleware` bounds `request_bytes` in the ASGI receive loop from bytes actually received, not `Content-Length`, before Starlette parses -- `r2db-api/src/r2db_api/http.py:247`.
- `postgres.py`'s `_set_timeouts` maps `execution_ms` onto PostgreSQL's own `statement_timeout`/`lock_timeout` (`SET LOCAL`, per transaction), a real second enforcement layer -- `r2db-api/src/r2db_api/postgres.py:2656`.
- both peers' `SET LOCAL` sets `statement_timeout` and `lock_timeout` alike, and r2db-api's application runtime/developer roles rely on that per-transaction call alone -- `r2db-api/src/r2db_api/postgres.py:2656-2670`.
- **CCR-14** `ControlPlaneService` bounds the control-plane classes `applications` and `credentials_per_application`, where revoked rows never count, and publishes both `enforced` -- `r2db-api/src/r2db_api/control_plane.py:766`.
- `control_requests_per_minute` is a third control-plane class, one global sliding 60s window rather than a per-credential one, published `enforced` -- `r2db-api/src/r2db_api/control_plane.py:1409`.
- `_check_rate` runs before authentication and before any durable audit write, so a flood cannot generate unbounded audit rows -- `r2db-api/src/r2db_api/control_plane.py:1409`.
- `request_bytes` is declared in two layers: the service layer alone declares `unavailable`, `control_http.py` overrides it to `enforced` once the middleware mounts, both reading the SAME limits source -- `r2db-api/src/r2db_api/control_http.py:231`.
- **`audit_requests_per_minute`** is a 5th control-plane class, default 60, env-overridable, published `enforced` -- `r2db-api/src/r2db_api/limits.py:398`.
- `ControlPlaneLimits.__post_init__` accepts any positive integer for a control-plane class and sets no upper bound, matching MitateDB-api -- `r2db-api/src/r2db_api/limits.py:400`.
- `audit_query` (canonical path plus the `/v1/audit/query` alias) consumes only that window, a separate counter and never a renamed view of `control_requests_per_minute` -- `r2db-api/src/r2db_api/control_http.py:463`.
- `_check_audit_rate` is charged pre-auth like the control window, so an unauthenticated flood adds no audit rows and polling for evidence cannot exhaust the window `revoke_credential` depends on -- `r2db-api/src/r2db_api/control_plane.py:1432`.
- the audit window's overage is `LIMIT_EXCEEDED` with `limit_class=="audit_requests_per_minute"` -- `r2db-api/src/r2db_api/control_plane.py:1444`.
- **F-17** `0014_auditreader_statement_timeout.sql` runs `ALTER ROLE r2dbsvc_auditreader SET statement_timeout = '5000ms'` (R-56, design `docs/design/R2DB_AUDIT_READER_STATEMENT_TIMEOUT_V0_1.md` D-1/D-4).
- that role setting bounds what a connection made with the audit reader's own DSN may run -- an operator's interactive `psql` session as much as `control_main`'s pooled ones -- `r2db-api/migrations/0014_auditreader_statement_timeout.sql`.
- a role setting is copied into a session at login, so it reaches connections OPENED AFTER the file is applied: a connection `_RolePool` is already holding keeps its login value -- `r2db-api/src/r2db_api/postgres.py`.
- `PostgresAuditQueryStore.query`'s own `except psycopg.Error` answers a `QueryCanceled` with 503 `SERVICE_UNAVAILABLE`, without the backend's own message, and hands the connection back to the pool -- `r2db-api/src/r2db_api/credential_store.py`.
- **F-17** in `ops verify-declarations` (exit code 16) requires a positive role-level `statement_timeout` with no per-database row overriding that same key -- `r2db-api/src/r2db_api/platform_declarations.py:1168`.
- **F-17** identifies its target roles by their real SELECT grants on both audit tables, never by name -- `r2db-api/src/r2db_api/platform_declarations.py:1152`.
- `PostgresCell`'s four client-reachable operations -- `query`, `transact`, `apply_schema` and `catalog` -- issue that call inside their own transaction -- `r2db-api/src/r2db_api/postgres.py` `:1110-1126`.
- `catalog` takes its bound from the `ResourceLimits` it is passed and falls back to the default `ResourceLimits()` when called without one, so the bound never depends on the caller -- `r2db-api/src/r2db_api/postgres.py` `:1110-1126`.
- `catalog` maps a cancelled statement or a lock timeout to the same `LIMIT_EXCEEDED` the other three operations return -- `r2db-api/src/r2db_api/postgres.py` `:1110-1126`.
- `ops upgrade-applications` requires `--lock-timeout` with no default, `--dry-run` included -- `r2db-api/src/r2db_api/ops.py:2412`.
- `_validate_lock_timeout_value` validates that value before any connection is opened -- a positive integer with an optional `ms`/`s`/`min`, so `0` is refused and the refused value is never echoed -- `r2db-api/src/r2db_api/ops.py:1501`.
- `_run_upgrade_script` hands the value to each `psql` child as `-c lock_timeout=<value>` appended to `PGOPTIONS`, alongside any `options` the DSN itself carried -- `r2db-api/src/r2db_api/ops.py:1617`.
- those three helpers are same-named copies of MitateDB-api's own, held identical by the isomorphism table -- `r2db-api/src/r2db_api/ops.py:1617`.
- all three subcommands that apply a migration file against a running cluster -- `apply-platform-migration`, `upgrade-applications`, `deprovision` -- require `--lock-timeout` with no default (R-90) -- `r2db-api/src/r2db_api/ops.py:2368`.
- the set of subcommand handlers reaching a psql/migrations-directory sink equals the set whose own `--lock-timeout` is required with no default -- `r2db-api/src/r2db_api/ops.py:2395`.

#### Evidence

- limit bounds -- `test_every_advertised_resource_limit_has_a_deterministic_boundary`, `test_rate_limit_is_atomic_for_concurrent_requests`, `test_applications_limit_at_exact_bound`, `test_rate_limit_precedes_authentication_and_is_not_audited`.
- limit bounds -- `test_l4_request_bytes_single_source_mutating_limit_changes_both_bound_and_discovery`, `test_audit_query_over_its_own_window_is_limit_exceeded_with_limit_class_audit_requests_per_minute`.
- `0014` reader `statement_timeout`, read from `pg_settings.setting` as the raw ms integer -- `r2db-api/tests/test_auditreader_statement_timeout.py::test_reader_connection_effective_statement_timeout_is_5000ms_after_0014`, `::test_0014_reapplication_is_idempotent`.
- the ROLE-level bound, shortened with `ALTER ROLE ... SET` -- `r2db-api/tests/test_auditreader_statement_timeout.py::test_slow_audit_query_is_canceled_returns_503_without_backend_detail_and_frees_the_connection`.
- F-17 -- `r2db-api/tests/test_ops_verify_declarations.py::test_verify_declarations_f17_passes_after_migration_0014`, `::test_verify_declarations_f17_fails_when_declared_timeout_is_zero`, `::test_verify_declarations_f17_fails_when_declared_timeout_is_reset`.
- F-17 -- `r2db-api/tests/test_ops_verify_declarations.py::test_verify_declarations_f17_fails_when_a_per_database_override_exists`, `::test_verify_declarations_f17_passes_when_auditreader_role_is_absent`, `::test_f17_the_schema_owning_role_is_never_flagged_despite_an_explicit_select_grant`.
- peer: the MitateDB catalog path issues no `SET LOCAL` -- `MitateDB-api/tests/test_application_audit.py::test_developer_connection_used_by_the_catalog_path_carries_the_role_level_statement_timeout`.
- `catalog` limits -- `r2db-api/tests/test_postgres.py::test_catalog_wires_statement_and_lock_timeout_to_the_passed_resource_limits`, `::test_catalog_without_an_explicit_limits_argument_uses_default_resource_limits`, `::test_catalog_set_local_timeouts_do_not_leak_to_the_next_transaction`.
- `catalog` limits -- `r2db-api/tests/test_postgres.py::test_catalog_maps_timeout_and_lock_conflicts_to_limit_exceeded`, `r2db-api/tests/test_foundation.py::test_data_service_catalog_passes_only_its_own_limits_to_the_cell`.
- `catalog` limits -- `r2db-api/tests/test_foundation.py::test_data_service_catalog_denial_is_audited_with_the_limit_exceeded_reason`.
- `--lock-timeout` -- `r2db-api/tests/test_ops_upgrade.py::test_upgrade_applications_without_lock_timeout_is_a_usage_error`, `::test_upgrade_applications_without_lock_timeout_is_a_usage_error_with_dry_run`, `::test_upgrade_applications_rejects_an_ill_formed_lock_timeout_through_the_cli`.
- `--lock-timeout` -- `r2db-api/tests/test_ops_upgrade.py::test_validate_lock_timeout_value_accepts_well_formed_values`, `::test_validate_lock_timeout_value_rejects_ill_formed_values`, `::test_upgrade_applications_cli_lock_timeout_value_reaches_pgoptions`.
- `--lock-timeout` -- `r2db-api/tests/test_ops_upgrade.py::test_run_upgrade_script_keeps_the_dsns_own_pgoptions_alongside_lock_timeout`.
- the DDL-flowing set, from the AST -- `r2db-api/tests/test_ops_apply_platform_migration.py::test_ddl_flowing_subcommands_match_the_required_lock_timeout_set`.

#### Status

- **`RequestByteBoundMiddleware` unexercised in production**: the VPS has never run this middleware under real traffic; every measurement is from the test suite.
- **Not bound by this window**: the application plane's durable denial writes are on a different plane/host, bounded by D-3 coalescing + row-length CHECKs -- deliberately no data-plane pre-auth window.
- **Rate-limit denials are not durably audited**: the rate-limit denial is the one denial category never durably audited (SI-14) -- `r2db-api/src/r2db_api/control_plane.py:1397`.
- **F-17 judges the DECLARATION, not the effective value inside a running process**: what a reader connection actually carries is read only by the Evidence tests above, never by the check itself.
- **Disclosed difference between the peers**: MitateDB-api's `0013_role_statement_timeouts.sql` puts a role-level `statement_timeout` on its application runtime/developer roles as well, while r2db-api leaves those two roles without one.
- **Only the lock WAIT is bounded on the provisioning path**: once a lock is granted, how long the statement holds it is deliberately left unbounded; the ground for accepting that is that no client can reach that role, not that `lock_timeout` would bound it.
- **`r2dbsvc_control` carries no role-level `statement_timeout`** (decision R-66): it applies the migration files and the per-application upgrade scripts, whose DDL may legitimately run long -- `docs/design/Q4_DB_SIDE_SINGLE_TRUTH_V1.md`.
- a role setting cannot be scoped to one file, so a bound on that role would cut a migration off part-way and leave it half applied -- `docs/design/Q4_DB_SIDE_SINGLE_TRUTH_V1.md`.
- **Deliberately accepted gap (R-90)**: the initial deployment script `r2db-api/deploy/scripts/part1_provision_host_and_db.sh` still applies the platform migrations and `0003` with no `lock_timeout` -- a host being provisioned has no other session to wait behind (design D-4).
- **Production evidence for `0014` is `absent`** (R-56): the measurements recorded above were taken on throwaway PostgreSQL clusters started by the test suite, and the VPS deployment was left as it stands, with `0014` unapplied.
- On that deployment `ops verify-declarations` answers `FAIL F-17` (exit code 16) while `0014` is unapplied, and **that is the intended signal, not a regression**: the check states in machine-readable form a gap that predates it (an audit reader whose statements carry no bound of their own).
- Applying `0014` and then restarting the control process clears that signal -- `r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md` section 19.
- **A pooled connection outliving `0014` is prevented only by procedure**: the runbook restarts the control process after applying `0014`; nothing in code enforces the restart -- `r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md` section 19.

### r2db-api -- capacity and concurrency

#### Control

- `process_ceilings` (`{"data": N, "control": M}`) is a platform-declaration row read at startup from the declaration table alone, with no env fallback -- `r2db-api/src/r2db_api/platform_declarations.py:499`.
- `resolve_limit_enforcement` reads a class `enforced` at every ceiling once its cross-process mechanism is configured, and otherwise `enforced` only at ceiling 1 and `deployment_required` above -- `r2db-api/src/r2db_api/capabilities_document.py:19`.
- data-plane `requests_per_minute` is configured whenever the PostgreSQL rate row is wired, so it reads `enforced` at every ceiling -- `r2db-api/src/r2db_api/capabilities_document.py:175`.
- data-plane `concurrency` is configured only when the slot directory is wired and `process_ceilings.data` is at most `R2DB_WORKERS` -- `r2db-api/src/r2db_api/main.py:502`.
- `control_requests_per_minute`/`audit_requests_per_minute` stay in-process windows and are never configured, so they keep the single-process rule -- `r2db-api/src/r2db_api/control_plane.py:635`.
- request-scoped classes (`request_bytes`, `batch_items`, `result_items`, `query_complexity`, `schema_objects`, `operation_depth`, `enum_members`) stay `enforced` at every ceiling -- `r2db-api/src/r2db_api/capabilities_document.py:172`.
- DB-side-bound classes stay `enforced` at every ceiling, `execution_ms` stays `reference_wall_clock`, and each plane reads its OWN key -- `r2db-api/src/r2db_api/capabilities_document.py:172`.
- **F-15** a missing or malformed `process_ceilings` row stops startup, and `ops verify-declarations` reports it with exit code 14 -- `r2db-api/src/r2db_api/platform_declarations.py:465`.
- `build_app` and `build_control_app` refuse to start when `R2DB_WORKERS`/`R2DB_CONTROL_WORKERS` exceeds its plane's `process_ceilings` value -- `r2db-api/src/r2db_api/main.py:488`, `r2db-api/src/r2db_api/control_main.py:573`.
- **F-20** `ops verify-declarations` reports `R2DB_WORKERS`/`R2DB_CONTROL_WORKERS` above `process_ceilings` with exit code 19 -- `r2db-api/src/r2db_api/ops.py:1204`.
- the `ExecStartPre=` preflight runs `build_app` once and exits non-zero on any startup check, before uvicorn starts a worker -- `r2db-api/src/r2db_api/main.py:769`, `r2db-api/deploy/systemd/r2dbsvc-api.service:69`.
- `_take_bound_advisory_lock` takes `pg_advisory_xact_lock(hashtext('<schema>.<table>'))` in the same transaction as the count-then-insert -- `r2db-api/src/r2db_api/credential_store.py`.
- `applications` and `credentials_per_application` are therefore bounded in the DATABASE rather than in the process, so two concurrent writers cannot both pass a bound -- `r2db-api/src/r2db_api/credential_store.py`.
- `role_pool_size(thread_limit)`, the thread limit plus 2, sizes every served application's runtime/developer pool and both platform pools, never the declared `concurrency` -- `r2db-api/src/r2db_api/limits.py:159`.
- `r2db-api/migrations/0013_role_connection_limits.sql` raises each role's PostgreSQL `CONNECTION LIMIT` to its own pool composition plus a 4-connection operator margin.
- **F-16** `check_role_connection_limits` identifies roles by their REAL grants and never by name, and takes the floor as the maximum over every matching role class -- `r2db-api/src/r2db_api/platform_declarations.py:1031`.
- **F-16** excludes the schema owner and skips register-only applications whose role names are NULL -- `r2db-api/src/r2db_api/platform_declarations.py:1031`.
- **F-16** fails `ops verify-declarations` with exit code 15 and stops each composition root at startup when its own role sits below that floor -- `r2db-api/src/r2db_api/platform_declarations.py:1031`.
- **F-16** multiplies each floor by its own plane's `process_ceilings` value (`data` for the api and application roles, `control` for the controlplane and auditreader roles) -- `r2db-api/src/r2db_api/platform_declarations.py:1108`.
- **F-18** `headroom_lower_bound` (`r2db-api/src/r2db_api/platform_declarations.py:1260`, `check_max_connections_headroom` `:1369`, `_f18_message` `:1346`) judges from declared values alone whether this deployment stays at or under `max_connections`.
- the judged count is one platform pool per data process, one runtime/developer pair per data process once an application is registered, and one control-plane pool per control process -- `r2db-api/src/r2db_api/platform_declarations.py:1260`.
- `superuser_reserved_connections` and `reserved_connections` are added to that count before it is compared with `max_connections` -- `r2db-api/src/r2db_api/platform_declarations.py:1260`.
- **F-18** is pinned in `_ISOMORPHIC_TARGETS` together with `_count_registered_applications`, `_read_connection_headroom_settings` and `HeadroomReport` -- `r2db-api/src/r2db_api/platform_declarations.py:1260`.
- `ops verify-declarations` exits 17 on that shortfall, and both composition roots refuse to start on the same unscoped judgment -- `r2db-api/src/r2db_api/ops.py:1021`.
- the data plane's startup also requires `credential_request_rate_admit(text, integer)` to exist and be EXECUTE-able by its own role, naming `0015` otherwise -- `r2db-api/src/r2db_api/platform_declarations.py:1515`.
- the deployment-wide `concurrency` slot is taken BEFORE authentication on the HTTP plane, so an unauthenticated flood is bounded before it reaches the credential store -- `r2db-api/src/r2db_api/http.py:492`.
- this surface's order is BYTE BOUND -> CONCURRENCY SLOT -> AUTHENTICATION -> body -> rate/business -- `r2db-api/src/r2db_api/http.py:456`.
- the per-credential `requests_per_minute` window stays reachable only after authentication succeeds, so a both-exhausted request is denied `concurrency` here, an explicit HTTP-plane ruling -- `r2db-api/src/r2db_api/http.py:456`.
- `acquire_concurrency_slot` holds the slot across authentication and dispatch and releases it on every exit path -- `r2db-api/src/r2db_api/service.py:587`.
- async handlers delegate their synchronous section to the threadpool, so more than one request is genuinely in flight and these bounds are exercised under real parallelism -- `r2db-api/src/r2db_api/http.py:492`.
- the limiter state and the pools are lock-guarded, pinned lexically by source shape rather than by a race -- `r2db-api/src/r2db_api/service.py:587`.
- `HostSharedConcurrencySlots` bounds `concurrency` across every worker on the host: a request `flock`s one of L `slot-<i>` files without waiting, scanning them under the exclusive `scan` lock -- `r2db-api/src/r2db_api/concurrency_slots.py:296`.
- each request opens and closes its own slot fd, so a killed worker's slot returns via the kernel; an unexpected errno or a `scan` wait over 1 s is a 503 -- `r2db-api/src/r2db_api/concurrency_slots.py:256`, `r2db-api/src/r2db_api/service.py:625`.
- `build_app` refuses to start unless `R2DB_SLOT_DIR` is an existing directory owned by this process, mode 0700, whose `selfcheck` file refuses a second `flock` -- `r2db-api/src/r2db_api/main.py:400`, `r2db-api/src/r2db_api/concurrency_slots.py:177`.
- `credential_request_rate_admit` keeps one `credential_request_rate` row per credential, a 61-second ring on the database clock, and admits only while its total is under the limit -- `r2db-api/migrations/0015_credential_request_rate.sql:128`.
- `record_rate_and_check` runs it after authentication has returned its connection, as one autocommit statement on the api role's pool, and answers 503 on a PostgreSQL failure -- `r2db-api/src/r2db_api/credential_store.py:320`.
- `r2dbsvc_api` holds only SELECT/INSERT/UPDATE on that table and EXECUTE on the function, and a deleted credential takes its row by `ON DELETE CASCADE` -- `r2db-api/migrations/0015_credential_request_rate.sql:75`, `:82`, `:186`.
- `part1_provision_host_and_db.sh` runs `0013_role_connection_limits.sql` right after `0007` -- `r2db-api/deploy/scripts/part1_provision_host_and_db.sh`.
- every platform migration file is either run by that script or in a reasoned exclusion set equal to the per-application upgrade numbers plus `0004` -- `r2db-api/deploy/scripts/part1_provision_host_and_db.sh`.
- `part1a_check_max_connections.sh` runs before `0005`, reads `max_connections` and `superuser_reserved_connections` over the control DSN, and refuses to proceed unless their difference covers the declared demand.
- the covered figure is `98 + 72 x (provisioned applications + 1)`, the sum of the `CONNECTION LIMIT`s this deployment holds once `0013` is applied -- `r2db-api/deploy/scripts/part1a_check_max_connections.sh`.
- `R2DBSVC_EXPECTED_PEAK_CONNECTIONS` replaces that default with the operator's own positive integer, and an empty or malformed value is refused, never defaulted -- `part1a_check_max_connections.sh`.
- `apply_schema` checks `schema_objects` against the catalog it loads under the application-wide schema lock, so two concurrent creates cannot both pass the bound -- `r2db-api/src/r2db_api/postgres.py:2200`, `:2157`.

#### Evidence

- `process_ceilings`, F-15 -- `r2db-api/tests/test_process_ceilings_declaration.py::test_ceiling_one_maps_in_memory_classes_to_enforced`, `::test_ceiling_two_maps_in_memory_classes_to_deployment_required`, `::test_control_plane_ceiling_mapping_reads_control_not_data_through_build_control_app`.
- `process_ceilings`, F-15 -- `r2db-api/tests/test_process_ceilings_declaration.py::test_declaration_table_is_the_only_source_no_env_fallback`, `::test_missing_row_fails_fast_through_build_app`, `::test_verify_declarations_f15_when_process_ceilings_row_is_absent`.
- `process_ceilings`, F-15 -- `r2db-api/tests/test_process_ceilings_declaration.py::test_verify_declarations_exit_code_table_maps_f15_to_14`.
- DB-side bounds -- `r2db-api/tests/test_process_ceilings_declaration.py::test_db_side_bounds_hold_under_concurrent_writers_applications`, `::test_db_side_bounds_hold_under_concurrent_writers_credentials_per_application`.
- DB-side bounds -- `r2db-api/tests/test_process_ceilings_declaration.py::test_applications_bound_holds_under_barrier_synchronized_concurrent_registration`, `::test_credentials_per_application_bound_holds_under_barrier_synchronized_concurrent_issuance`.
- pool sizing -- `r2db-api/tests/test_threadpool_offload.py::test_role_pool_size_derives_from_thread_limit`, `::test_main_composition_root_wires_pool_size_from_role_pool_size`, `::test_role_pool_sized_to_thread_limit_avoids_premature_503`.
- pool sizing -- `r2db-api/tests/test_credential_persistence.py::test_platform_pool_sized_to_thread_limit_avoids_premature_503`.
- F-16 and F-18 -- `r2db-api/tests/test_ops_verify_declarations.py::test_verify_declarations_f16_passes_after_migration_0013`, `::test_verify_declarations_f16_fails_when_a_role_connection_limit_is_lowered_below_its_pool_composition_floor`.
- F-16 and F-18 -- `r2db-api/tests/test_ops_verify_declarations.py::test_f16_floor_for_a_role_matching_multiple_classes_is_the_max_not_the_last_assigned`, `::test_f16_the_schema_owning_role_is_never_flagged_even_though_it_matches_every_class`.
- F-16 and F-18 -- `r2db-api/tests/test_ops_verify_declarations.py::test_0013_migration_tolerates_a_registered_only_application_and_still_raises_a_provisioned_applications_role_limits`, `::test_verify_declarations_f18_fails_when_the_declared_lower_bound_exceeds_max_connections`.
- F-16 and F-18 -- `r2db-api/tests/test_ops_verify_declarations.py::test_verify_declarations_f18_passes_when_the_declared_lower_bound_fits`.
- composition roots -- `r2db-api/tests/test_credential_persistence.py::test_build_app_fails_fast_when_its_own_api_role_connection_limit_is_lowered_below_the_pool_composition_floor`.
- composition roots -- `r2db-api/tests/test_surfaces_env.py::test_build_control_app_fails_fast_when_its_own_controlplane_role_connection_limit_is_lowered_below_the_pool_composition_floor`.
- at the default thread limit 4 and `process_ceilings.data` 1 the api role's floor is 12, so the 10 `0005` creates is refused -- `r2db-api/tests/test_credential_persistence.py::test_build_app_fails_fast_when_its_own_api_role_connection_limit_is_lowered_below_the_pool_composition_floor`.
- F-16 scaled by `process_ceilings.data`: at `data` 3 `build_app` refuses an api role limit of 20, naming floor 36 -- `r2db-api/tests/test_r113_multi_process_wiring.py::test_f16_startup_floor_scales_with_process_ceilings_data_times_pool_composition`.
- F-16 scaled by `process_ceilings.control`: the controlplane role's limit 20 clears floor 16 at `control` 1 and fails floor 32 at `control` 2 -- `r2db-api/tests/test_ops_verify_declarations.py::test_f16_controlplane_floor_scales_with_process_ceilings_control`.
- `ops verify-declarations` passes the declared `control` 2 into F-16 and fails the auditreader role at floor 8 -- `r2db-api/tests/test_ops_verify_declarations.py::test_f16_aggregate_ops_call_scales_controlplane_floor_by_declared_process_ceilings`.
- a host deployed by the script alone, before `0013` joined it, could start neither process -- `r2db-api/tests/test_surfaces_env.py::test_build_control_app_fails_fast_when_its_own_controlplane_role_connection_limit_is_lowered_below_the_pool_composition_floor`.
- the pre-auth slot -- `r2db-api/tests/test_preauth_concurrency_bound.py::test_unauthenticated_flood_is_bounded_by_concurrency`, `::test_http_plane_denies_concurrency_before_requests_per_minute`, `::test_concurrency_hold_spans_the_gap_between_authentication_and_dispatch`.
- the pre-auth slot -- `r2db-api/tests/test_preauth_concurrency_bound.py::test_slot_is_released_after_a_401_ending_request`, `::test_slot_is_released_after_a_validation_failed_ending_request`, `::test_concurrency_slot_is_acquired_exactly_once_per_handler`.
- offload and locking -- `r2db-api/tests/test_threadpool_offload.py::test_sync_section_runs_off_the_event_loop`, `::test_control_sync_section_runs_off_the_event_loop`, `::test_body_read_stays_on_the_loop`, `::test_limiter_state_is_thread_safe`, `::test_pool_acquire_is_thread_safe`.
- offload and locking -- `r2db-api/tests/test_threadpool_offload.py::test_slot_check_then_increment_is_lexically_inside_the_active_lock`, `::test_rate_window_check_then_append_is_lexically_inside_the_rate_lock`, `::test_role_pool_reservation_is_lexically_inside_the_pool_lock`.
- offload and locking -- `r2db-api/tests/test_threadpool_offload.py::test_authenticate_delegation_pinned_for_every_body_first_handler`, `::test_service_call_delegation_pinned_for_query_mutate_cross_entity_schema`, `::test_control_service_call_delegation_pinned_for_rotate_and_issue_credential`.
- the deploy script -- `r2db-api/tests/test_deploy_script_migrations.py::test_every_platform_migration_appears_in_the_scripts_invocation_list`, `::test_excluded_migration_set_matches_platform_upgrade_numbers_plus_deprovision`, `::test_invocation_order_matches_runbook_section_5`.
- the deploy script -- `r2db-api/tests/test_deploy_script_max_connections.py::test_insufficient_headroom_is_refused_and_names_every_required_value`, `::test_sufficient_headroom_passes`, `::test_script_is_executable`, `::test_expected_peak_connections_rejects_non_positive_integers`.
- the deploy script -- `r2db-api/tests/test_deploy_script_max_connections.py::test_expected_peak_connections_replaces_the_default_not_added_to_it`.
- the literals 98 and 72 recompute from the migration `CONNECTION LIMIT`s -- `r2db-api/tests/test_deploy_script_migrations.py::test_part1a_literals_98_and_72_recompute_from_migration_connection_limits`.
- `part1a_check_max_connections.sh` is called right after `0002` and before `0005` -- `r2db-api/tests/test_deploy_script_migrations.py::test_part1a_is_called_right_after_0002_and_before_0005`.
- the mapping helper -- `r2db-api/tests/test_r113_multi_process_wiring.py::test_resolve_limit_enforcement_configured_is_always_enforced_regardless_of_ceiling`, `::test_resolve_limit_enforcement_unconfigured_follows_the_legacy_ceiling_rule`.
- the served mapping -- `r2db-api/tests/test_r113_multi_process_wiring.py::test_build_capabilities_document_concurrency_mapping_enforced_only_at_ceiling_le_workers`, `::test_build_capabilities_document_rate_mapping_ignores_ceiling_when_wired`.
- the served mapping -- `r2db-api/tests/test_r113_multi_process_wiring.py::test_build_app_concurrency_configured_reflects_workers_vs_ceiling`, `::test_control_plane_mapping_goes_through_the_same_helper_unconfigured`.
- workers against the ceiling -- `r2db-api/tests/test_r113_multi_process_wiring.py::test_build_app_fails_when_workers_exceeds_declared_data_ceiling`, `::test_build_control_app_fails_when_workers_exceeds_declared_control_ceiling`.
- workers against the ceiling -- `r2db-api/tests/test_r113_multi_process_wiring.py::test_data_workers_env_rejects_unset_empty_zero_negative_non_numeric`, `::test_verify_declarations_reports_workers_exceeding_ceiling_with_a_dedicated_exit_code`.
- the preflight -- `r2db-api/tests/test_r113_multi_process_wiring.py::test_data_preflight_exits_0_on_a_sound_env`, `::test_data_preflight_exits_nonzero_with_f15_when_process_ceilings_missing`, `::test_preflight_entry_reuses_the_module_app_never_calling_build_app_twice`.
- the unit's preflight and workers -- `r2db-api/tests/test_deploy_systemd_workers_static.py::test_systemd_api_unit_runs_the_data_plane_preflight_before_uvicorn`, `::test_systemd_api_unit_passes_workers_from_env_without_a_literal_count`.
- the rate function check -- `r2db-api/tests/test_r113_multi_process_wiring.py::test_build_app_and_preflight_fail_naming_the_rate_migration_when_the_rate_function_is_missing`.
- the rate function check -- `r2db-api/tests/test_r113_multi_process_wiring.py::test_build_app_fails_naming_the_rate_migration_when_the_data_plane_role_may_not_execute_the_rate_function`.
- the host-shared slots -- `r2db-api/tests/test_r113_multi_process_wiring.py::test_two_threads_l_c_1_second_is_refused`, `::test_full_slots_refuse_immediately_never_blocking`, `::test_one_http_request_holds_exactly_one_slot`, `::test_slot_released_even_when_the_body_raises`.
- the `scan` lock -- `r2db-api/tests/test_r113_multi_process_wiring.py::test_scan_serialises_another_process_behind_a_paused_scan`, `::test_scan_serialises_a_same_process_thread_behind_a_paused_scan`.
- release by the kernel -- `r2db-api/tests/test_r113_multi_process_wiring.py::test_slot_is_reacquirable_after_a_holding_child_process_is_sigkilled_and_after_a_plain_close`, `::test_scan_lock_held_by_a_sigkilled_child_process_is_released_by_the_kernel`.
- slot failures answer 503 -- `r2db-api/tests/test_r113_multi_process_wiring.py::test_flock_unexpected_errno_maps_to_backend_error_not_admitted_or_denied`, `::test_slot_backend_error_maps_to_service_unavailable_through_data_service`.
- slot failures answer 503 -- `r2db-api/tests/test_r113_multi_process_wiring.py::test_scan_held_past_its_deadline_raises_backend_error_and_the_caller_answers_503`.
- the slot directory -- `r2db-api/tests/test_r113_multi_process_wiring.py::test_slot_dir_env_missing_raises_naming_the_variable`, `::test_slot_dir_wrong_owner_raises`, `::test_slot_dir_wrong_mode_raises`, `::test_selfcheck_detects_a_faked_flock_that_never_excludes`.
- the rate row -- `r2db-api/tests/test_r113_multi_process_wiring.py::test_pg_rate_admits_up_to_limit_then_denies`, `::test_rate_ring_full_count_60_seconds_ago_still_denies`, `::test_rate_ring_base_s_never_rewinds_after_a_lock_wait`.
- the rate row -- `r2db-api/tests/test_r113_multi_process_wiring.py::test_pg_rate_concurrent_first_admissions_for_a_new_credential_never_race`, `::test_pg_rate_db_failure_maps_to_service_unavailable_503`.
- the rate row after authentication -- `r2db-api/tests/test_r113_multi_process_wiring.py::test_rate_call_is_lexically_outside_the_authentication_borrow`, `::test_denied_authentication_never_writes_a_rate_row`.
- the rate row's grants and reclaim -- `r2db-api/tests/test_r113_multi_process_wiring.py::test_0015_api_role_has_select_insert_update_only_no_delete_or_truncate`, `::test_0015_rate_row_cascades_on_credential_delete`.
- one real request holds one slot and writes one rate row -- `r2db-api/tests/test_r113_multi_process_wiring.py::test_real_http_request_holds_the_shared_slot_and_writes_a_rate_row`.
- pool sizing from the thread limit -- `r2db-api/tests/test_r113_multi_process_wiring.py::test_role_pool_size_is_thread_limit_plus_two`, `::test_build_app_sizes_platform_and_application_pools_from_r2db_thread_limit`.
- the `schema_objects` window, two cells on one application -- `r2db-api/tests/test_r102_schema_windows.py::test_schema_objects_window_concurrent_create_entity_cannot_exceed_schema_objects`.

#### Status

- **F-18 is a necessary condition only**: it never counts an interactive or diagnostic `psql` session, nor its own connection, and it prints the upper bound (every registered application times every data process) for disclosure only, never as the judged quantity.
- **F-18 and F-16 do not track a pool-size override**: the floors they read are the declared ones, so a deployment that sets `R2DB_PLATFORM_POOL_SIZE` is judged against a figure its processes do not use.
- **F-16 itself still does not read `max_connections`**: the cluster-wide headroom question is answered only by the deployment script's own check and by F-18's declared-value judgment.
- **Disclosed limit of the deployment-script evidence (R-66)**: no test runs `part1_provision_host_and_db.sh` end to end, since it needs root and a host to provision; the tests above read its invocation lines statically.
- `part1a_check_max_connections.sh` is exercised only against a stub `psql`, and the script as changed has not been run against the VPS.
- **The systemd unit's evidence is static**: the tests above read `r2dbsvc-api.service` as text and none starts it, so the preflight-then-uvicorn order and the slot directory it creates are unobserved until the unit runs on the VPS, which the unit as changed has not.
- **Production evidence for `0015` is `absent`**: the VPS deployment has no `0015`, and a build carrying the rate-function check refuses to start there until `0015` is applied -- `r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md` section 20.
- **The 98/72 figure is a conservative stand-in for real demand**, not a PostgreSQL requirement, and it holds only until an operator derives the real figure.
- **`concurrency` is shared within one host only**: the slot directory is host-local, so `enforced` holds only while every process serving the base URL is a worker on that host, a runbook rule no check reads -- `r2db-api/deploy/DEPLOYMENT_RUNBOOK.md:889`.
- **A worker stopped while holding `scan` holds up the whole host**: every acquisition waits up to 1 s and answers 503; the runbook forbids stopping a single worker -- `r2db-api/deploy/DEPLOYMENT_RUNBOOK.md:966`.
- **The rate ring may refuse slightly early**: at a window edge it counts up to one second more than 60 s, and never admits more than the declared `requests_per_minute` -- `r2db-api/deploy/DEPLOYMENT_RUNBOOK.md:987`.
- **A database clock that steps back stretches the rate window by that step**: the ring's base second never moves back, so no count ages out until the clock passes it again (stricter, never looser); read from the function, not tested -- `r2db-api/migrations/0015_credential_request_rate.sql:165`.
- **A database clock that steps forward ages counts out early**: the ring reads the database's wall clock, so a forward step admits up to twice the declared `requests_per_minute` in 60 real seconds; read from the function, not tested -- `r2db-api/migrations/0015_credential_request_rate.sql`.
- **A restart is assumed never to overlap**: stop-then-start is inferred from systemd's documented ordering, not observed on the host; old and new workers serving at once from different slot directories admit up to twice the declared `concurrency` -- `r2db-api/deploy/DEPLOYMENT_RUNBOOK.md:992`.
- **SIGHUP or SIGTTIN runs more data workers than declared**: the uvicorn supervisor then runs `R2DB_WORKERS + 1` or more, beyond `process_ceilings.data` and the F-16/F-18 budget; no check sees it and only the runbook forbids it -- `r2db-api/deploy/DEPLOYMENT_RUNBOOK.md:956`.
- **F-20 reads the workers from the operator's own shell**, never from the running units, so it is a hand cross-check; the preflight's check is the one that stops a service -- `r2db-api/deploy/DEPLOYMENT_RUNBOOK.md:972`.

### MitateDB-api

#### Control

- `FoundationConfig` carries the local bounds for batch, result, fields, filters, schema and request size, overridable through the `MITATEDB_*` names -- `MitateDB-api/src/mitatedb_api/config.py:14`.
- **`request_bytes`**: an ASGI receive-loop middleware measures actual received bytes, never `Content-Length`, and rejects before Starlette's parser runs -- `MitateDB-api/src/mitatedb_api/http.py:198`.
- that middleware is sized from the SAME `FoundationConfig.max_request_bytes` the declaration publishes -- `MitateDB-api/src/mitatedb_api/config.py:36`.
- **Control-plane's own 3 classes** (`applications`/`credentials_per_application`/`control_requests_per_minute`) are enforced by `ControlPlaneService`, published `enforced` -- `MitateDB-api/src/mitatedb_api/control_plane.py:1728`.
- the control plane carries its own `request_bytes` bound as well, published `enforced` -- `MitateDB-api/src/mitatedb_api/control_plane.py:153`.
- `credentials_per_application` excludes revoked rows, matching r2db-api's identical pre-auth and never-audited rule -- `MitateDB-api/src/mitatedb_api/control_plane.py:1119`.
- **Application-plane resource bounds**: `_LimitStateHolder.acquire_rate`/`.concurrency_slot` bound `requests_per_minute` and `concurrency`, through the PostgreSQL rate row and the host-shared slots once wired (`cell.py:320`, `:393`, `:412`).
- those two classes are declared in `build_capabilities_document`'s `limit_enforcement` dict through `resolve_limit_enforcement` (`capabilities_document.py:60`, dict at `:308`; entries `:354`, `:361`).
- `execution_ms` is declared `reference_wall_clock`, not `enforced` (`capabilities_document.py:338`) -- a wall-clock deadline (`time.monotonic() + max_execution_ms`) handed to the backend.
- `backend_postgres.py` converts that deadline into a real `SET LOCAL statement_timeout`/`lock_timeout` (`backend_postgres.py:1687-1696`), matching r2db-api's own identical declaration.
- **`batch_entities`** is a 4th enforced class bounding the distinct entity names a `cross_entity_mutation` unit may name; repeats do not count twice -- `MitateDB-api/src/mitatedb_api/config.py:32`.
- `batch_items` stays the separate total-operation-count bound -- `MitateDB-api/src/mitatedb_api/config.py:22`.
- `batch_entities` defaults to 10 and is counted before any operation executes, published `enforced` -- `MitateDB-api/src/mitatedb_api/config.py:32`.
- **`audit_requests_per_minute`**: this class carries the same default 60 and separate-counter, pre-auth, never-shared-with-`control_requests_per_minute` properties as r2db-api's own entry -- `MitateDB-api/src/mitatedb_api/control_plane.py:160`.
- its overage carries the same `LIMIT_EXCEEDED`/`limit_class` shape -- `MitateDB-api/src/mitatedb_api/control_plane.py:1345`.
- **Symmetric with r2db-api**: all 4 control-plane request-count classes accept any positive integer with no upper bound -- `MitateDB-api/src/mitatedb_api/control_plane.py:164`.
- **F-17** is judged here against the reader bound `0013_role_statement_timeouts.sql` already declares, so R-56 adds no migration to this peer -- `MitateDB-api/src/mitatedb_api/platform_declarations.py:1145`.
- `_f17_message` and `check_auditreader_statement_timeout` are rows of `_ISOMORPHIC_TARGETS`, which holds the two peers' wording and judgment together -- `MitateDB-api/src/mitatedb_api/platform_declarations.py:1145`.
- `_run_upgrade_script` and `_run_deprovision_script` require a `--lock-timeout` value with no default, set on the psql session through `PGOPTIONS`'s own `-c lock_timeout=<value>` -- `MitateDB-api/src/mitatedb_api/ops.py:1773`.
- that option is appended to, never overwriting, the DSN's own `options` value, so each invocation's catalog-lock wait has an upper bound -- `MitateDB-api/src/mitatedb_api/ops.py:750`.
- the CLI rejects both a missing value and one that is not a positive integer optionally followed by `ms`/`s`/`min`, before any psql subprocess starts -- `MitateDB-api/src/mitatedb_api/ops.py:638`.
- **Developer-connection catalog reads**: `backend_postgres.py` runs 8 of them -- `schema_count`, `field_domains`, `field_types`, `all_field_types`, `field_constraints`, `field_types_and_constraints`, `all_field_constraints`, `schema_revision`.
- each of those reads maps a `statement_timeout`/`lock_timeout` cancel to `LIMIT_EXCEEDED` (`limit_class` `execution_ms`) -- `MitateDB-api/src/mitatedb_api/backend_postgres.py:640-641`.
- that mapping is not the `VALIDATION_FAILED` the catch-all backstop gives an unclassified `psycopg.Error`, so a client is not told to reshape a request that was cut off for time -- `MitateDB-api/src/mitatedb_api/backend_postgres.py:640-641`.
- each of the 8 reads runs on the request scope's developer connection inside its transaction, committing nothing and setting no timeout of its own -- `MitateDB-api/src/mitatedb_api/backend_postgres.py:634`.
- a scope that ends without an exception COMMITs a read-only transaction it still has open (a rollback discards psycopg's prepared statements), one that ends with an exception rolls back -- `MitateDB-api/src/mitatedb_api/backend_postgres.py:508`.
- `request_scope` sets `statement_timeout`/`lock_timeout` by `SET LOCAL` on each connection it borrows, from the request's deadline, or the constructed value for a scope without one -- `MitateDB-api/src/mitatedb_api/backend_postgres.py:467`.
- after a lock wait the scope sets them again from what remains of the deadline, and a wait that used the whole budget is `LIMIT_EXCEEDED` (`execution_ms`) -- `MitateDB-api/src/mitatedb_api/backend_postgres.py:532`, `:555`.
- `main.py` passes `config.max_execution_ms` (`MITATEDB_MAX_EXECUTION_MS`), the number the capabilities document declares as `execution_ms`; a bare construction uses the default 5000 -- `MitateDB-api/src/mitatedb_api/main.py:264`.
- that bound applies to each statement and is what remains of the request's deadline when it is set, so a request-level `budget` narrows it -- `MitateDB-api/src/mitatedb_api/backend_postgres.py:1681`.
- the role-level `statement_timeout` of `0013_role_statement_timeouts.sql` (5000ms) remains in force only for a developer-connection statement outside a request scope -- `MitateDB-api/migrations/0013_role_statement_timeouts.sql`.
- `0007_platform_declarations.sql` and `0013_role_statement_timeouts.sql` put the role-level bound on the api, controlplane, auditreader, runtime and developer roles and leave that one out -- `MitateDB-api/migrations/0007_platform_declarations.sql`.
- the per-invocation `--lock-timeout` bounds the WAIT for a lock on this path, since a role setting is copied into every session at login and would cut a migration off part-way -- `MitateDB-api/src/mitatedb_api/ops.py:638`.

#### Evidence

- limit bounds -- `test_batch_and_request_size_limits_and_empty_filters_shape_check`, `test_byte_bound_is_measured_from_actual_received_bytes_not_content_length_header`, `test_request_over_byte_limit_is_limit_exceeded_before_parsing`, `test_register_application_enforces_the_applications_bound`.
- limit bounds -- `test_rate_limit_denial_is_never_durably_audited`, `test_transact_batch_entities_boundary_and_distinct_count_ignores_repeats`, `test_audit_query_over_its_own_window_is_limit_exceeded_with_limit_class_audit_requests_per_minute`.
- the same `batch_entities` boundary holds over real HTTP -- `test_cross_entity_mutation_batch_entities_boundary`.
- F-17 -- `MitateDB-api/tests/test_ops_verify_declarations.py::test_verify_declarations_f17_passes_from_migration_0013`, `::test_verify_declarations_f17_fails_when_declared_timeout_is_zero`, `::test_verify_declarations_f17_fails_when_declared_timeout_is_reset`.
- F-17 -- `MitateDB-api/tests/test_ops_verify_declarations.py::test_verify_declarations_f17_fails_when_a_per_database_override_exists`, `::test_verify_declarations_f17_passes_when_auditreader_role_is_absent`, `::test_f17_the_schema_owning_role_is_never_flagged_despite_an_explicit_select_grant`.
- the isomorphic target -- `MitateDB-api/tests/test_audit_query.py::test_isomorphic_target_table_is_pinned_to_its_current_205_rows`.
- catalog-read timeouts -- `MitateDB-api/tests/test_r71_catalog_read_cancel_mapping.py::test_catalog_read_cancel_synthetic_injection_maps_to_resource_limit_error`, `::test_get_catalog_returns_limit_exceeded_not_validation_failed_when_the_read_is_canceled`.
- catalog-read timeouts -- `MitateDB-api/tests/test_r87_catalog_read_execution_ms.py::test_blocked_catalog_read_is_bounded_by_the_constructed_value_not_the_role_value`.
- the scope's timeouts and the reads inside it -- `MitateDB-api/tests/test_r102_request_scope.py::test_catalog_reads_run_inside_the_scope_transaction_without_committing_or_setting_timeouts`, `::test_the_scope_sets_its_timeouts_from_the_deadline_not_the_constructed_value`.
- timeouts after a lock wait -- `MitateDB-api/tests/test_r102_request_scope.py::test_a_lock_wait_shortens_the_timeouts_of_the_statements_that_follow`, `::test_an_uncontended_request_sets_its_timeouts_once_per_connection`.
- read-only transactions end in a COMMIT, so prepared statements survive on the pooled connections -- `MitateDB-api/tests/test_r102_request_scope.py::test_read_only_transactions_end_in_a_commit_so_prepared_statements_survive`.
- catalog-read timeouts -- `MitateDB-api/tests/test_r87_catalog_read_execution_ms.py::test_bare_construction_uses_the_foundation_config_default_execution_ms`, `::test_build_app_passes_the_declared_execution_ms_to_the_constructed_backend`.
- the developer connection -- `MitateDB-api/tests/test_application_audit.py::test_developer_connection_used_by_the_catalog_path_carries_the_role_level_statement_timeout`.
- the DDL-flowing set -- `MitateDB-api/tests/test_ops_apply_platform_migration.py::test_ddl_flowing_subcommands_match_the_required_lock_timeout_set`.
- common-suite coverage of `batch_entities` is C-16's own V3 vector (see the SI-11 row) -- `conformance-tests/test_c16_cross_entity_atomicity.py::test_c16_v3_batch_entities_bound_is_discoverable_and_enforced`.
- `lock_timeout` in ops -- `MitateDB-api/tests/test_platform_migration_reapply.py::test_run_upgrade_script_passes_lock_timeout_via_pgoptions`, `::test_run_deprovision_script_passes_lock_timeout_via_pgoptions`, `::test_run_upgrade_script_keeps_the_dsns_own_pgoptions_alongside_lock_timeout`.
- `lock_timeout` in ops -- `MitateDB-api/tests/test_platform_migration_reapply.py::test_upgrade_applications_without_lock_timeout_is_a_usage_error`, `::test_deprovision_without_lock_timeout_is_a_usage_error`, `::test_upgrade_applications_rejects_a_malformed_lock_timeout_value`.
- `lock_timeout` in ops -- `MitateDB-api/tests/test_platform_migration_reapply.py::test_deprovision_rejects_a_malformed_lock_timeout_value`, `::test_deprovision_accepts_a_well_formed_lock_timeout_value`.

#### Status

- the contract declares no range for a control-plane class -- an operator responsibility, published as-declared -- `test_limits_reject_out_of_range_values`.
- **Removing the ceiling removed the misconfiguration guardrail it incidentally provided**: nothing stops an operator declaring an implausibly large value, a deliberate trade recorded in `MitateDB-api/docs/cloud-run-cloud-sql.md` §3.2c and `r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md` §15.
- **Deployment caveat**: like `control_requests_per_minute`, this is an in-process counter, inheriting the `--max-instances=1` requirement on the control service.
- The application plane's own durable-denial writes are NOT governed by this window (SI-14 point 6).
- **`field_constraints` has no caller in `src/` today**, so one of the 8 developer-connection catalog reads is covered only by the tests above.
- **This peer does not durably audit a `LIMIT_EXCEEDED` denial**, unlike r2db-api's own data plane.
- **A deployment declaring `execution_ms` above 5000 also raises the catalog-read bound above 5000**, since inside those 8 transactions the constructed value wins over the role-level one.
- **Only the lock WAIT is bounded on the provisioning path**: once a lock is granted, how long the statement holds it is deliberately left unbounded, and the ground for accepting that is that no client can reach that role.
- **`mitatedbsvc_provision` carries no role-level `statement_timeout`** (decision R-66): it applies the migration files and the per-application scripts, whose DDL may legitimately run long -- `MitateDB-api/src/mitatedb_api/ops.py:1773`.

### MitateDB-api -- ops inventory

#### Control

- **`ops inventory` item (8)** sums connection demand across `mitatedbsvc_api`, `mitatedbsvc_controlplane` and `mitatedbsvc_auditreader`, discovered by table grant and never by a literal name -- `MitateDB-api/src/mitatedb_api/ops.py:2562`.
- item (8) counts Data demand per revision basis: old-basis processes at `--concurrency`, the rest of the total at `role_pool_size(--thread-limit)`, F-16's own function and floor constants -- `MitateDB-api/src/mitatedb_api/ops.py:2643`.
- condition 2 counts the application roles as the larger of that floor and 2 x K x (old-basis + new-basis processes x `role_pool_size(--thread-limit)`), K = registered applications with roles -- `MitateDB-api/src/mitatedb_api/ops.py:2762`.
- `--control-not-deployed` zeroes Control's own demand and role checks -- `MitateDB-api/src/mitatedb_api/ops.py:2562`.
- only `control_composition.build_control_service` pools a connection against `mitatedbsvc_auditreader`, on `MITATEDB_AUDIT_DSN`, so that demand counts only under the Control process count -- `MitateDB-api/src/mitatedb_api/ops.py:2562`.
- `main.build_app` never pools such a connection -- `MitateDB-api/src/mitatedb_api/main.py:264`.
- each plane's own CEILING (against the declared `process_ceilings`) and TOTAL (the actual count, which feeds demand) are SEPARATE positive-integer arguments -- `MitateDB-api/src/mitatedb_api/ops.py:3051`.
- each ceiling and total, `--thread-limit`, `--data-process-count-old-basis` and `--reserved-connections` are required, `--concurrency` only with old-basis processes; one omitted leaves item (8) unknown -- `MitateDB-api/src/mitatedb_api/ops.py:2632`.
- `--control-not-deployed` stands in for Control's own ceiling and total -- `MitateDB-api/src/mitatedb_api/ops.py:2632`.
- an old-basis count above the total, a new-basis count below `--data-process-ceiling`, or `--concurrency` with an old-basis count of 0 is refused, exit code 1, before any connection -- `MitateDB-api/src/mitatedb_api/ops.py:3051`.
- `CONNECTION LIMIT = -1` is unknown, but only for a role INSIDE item (8)'s own target role set, so an unrelated role carrying `-1` never rounds the item to unknown -- `MitateDB-api/src/mitatedb_api/ops.py:2298`.
- a declaration read that finds the row absent is unknown and remediation-required, a row that fails validation is blocked, and a plain connection failure is unknown -- `MitateDB-api/src/mitatedb_api/ops.py:2338`.
- a declared/actual CEILING mismatch on EITHER plane is blocked, and Control is never compared once `--control-not-deployed` is given -- `MitateDB-api/src/mitatedb_api/ops.py:2562`.
- item (6)'s runtime-settings half confirms once `statement_timeout` (`0013`, `setdatabase = 0`) is POSITIVE, plus a real non-`-1` `CONNECTION LIMIT` on every item (8) target role -- `MitateDB-api/src/mitatedb_api/ops.py:2465`.
- a zero, negative or unparseable value blocks with `statement-timeout-unbounded`, an absent one is unknown, and `lock_timeout` is unjudged since no DDL role is in that set -- `MitateDB-api/src/mitatedb_api/ops.py:2465`.
- lock-type/downtime, and item (5) in full, are `unjudged_items` under a closed `part` vocabulary with the reason `runbook-acceptance` -- `MitateDB-api/src/mitatedb_api/ops.py:2187`.
- **Rollout arithmetic against the ceilings `0014` sets**: one old-basis process at `concurrency` 32 plus W new-basis ones at thread limit 4 need 64 + 12W on `mitatedbsvc_api`, confirmed through W = 5 -- `MitateDB-api/src/mitatedb_api/ops.py:2700`.
- W = 6 blocks on `mitatedbsvc_api`, whose demand of 136 exceeds its own ceiling of 132 -- `MitateDB-api/src/mitatedb_api/ops.py:2700`.
- the declared ceilings stay 1 in that window, since a TOTAL is a count of processes and not a declaration -- `MitateDB-api/src/mitatedb_api/ops.py:2562`.
- a stray `0012` is caught when re-applied alone after `0014`, because it lowers every role it names back to 68/20/36 while `mitatedbsvc_auditreader` keeps `0014`'s own 12 -- `MitateDB-api/migrations/0012_role_connection_limits.sql`.
- a stray `0013` is caught once an application is provisioned after it, since that application's roles are created at 36 -- `MitateDB-api/migrations/0013_role_statement_timeouts.sql`.
- a re-application runs `0012` -> `0013` -> `0014` in that order -- `MitateDB-api/docs/cloud-run-cloud-sql.md` section 10.

#### Evidence

- connection headroom, all of it in `MitateDB-api/tests/test_ops_inventory.py` -- `MitateDB-api/tests/test_ops_inventory.py::test_inventory_connection_headroom_data_process_count_overflow_is_blocked`, `::test_inventory_connection_headroom_app_role_demand_scales_with_data_process_count`.
- the `ops inventory` items -- `MitateDB-api/tests/test_ops_inventory.py::test_inventory_connection_headroom_app_role_overflow_with_named_values`, `::test_inventory_connection_headroom_shared_application_role_budget_counts_once`.
- the `ops inventory` items -- `MitateDB-api/tests/test_ops_inventory.py::test_inventory_connection_headroom_auditreader_counted_under_control_only`, `::test_only_control_composition_pools_a_connection_against_mitatedbsvc_auditreader`.
- the `ops inventory` items -- `MitateDB-api/tests/test_ops_inventory.py::test_inventory_connection_headroom_concurrency_missing_is_unknown`, `::test_inventory_connection_headroom_process_count_missing_is_unknown`, `::test_inventory_connection_headroom_reserved_connections_missing_is_unknown`.
- the `ops inventory` items -- `MitateDB-api/tests/test_ops_inventory.py::test_inventory_connection_headroom_max_connections_unreadable_is_unknown`, `::test_inventory_connection_headroom_minus_one_connection_limit_is_unknown`.
- the `ops inventory` items -- `MitateDB-api/tests/test_ops_inventory.py::test_inventory_connection_headroom_minus_one_on_an_unrelated_role_is_not_unknown`, `::test_inventory_connection_headroom_declaration_missing_is_unknown_with_remediation`.
- the `ops inventory` items -- `MitateDB-api/tests/test_ops_inventory.py::test_inventory_connection_headroom_declaration_shape_violation_is_blocked`, `::test_inventory_connection_headroom_declaration_connection_failure_is_unknown`.
- the `ops inventory` items -- `MitateDB-api/tests/test_ops_inventory.py::test_inventory_connection_headroom_declared_and_actual_process_counts_disagree_is_blocked`, `::test_inventory_connection_headroom_control_process_count_mismatch_is_blocked`.
- the `ops inventory` items -- `MitateDB-api/tests/test_ops_inventory.py::test_inventory_connection_headroom_total_may_exceed_ceiling_without_a_declaration_mismatch`, `::test_inventory_connection_headroom_control_not_deployed_computes_with_control_zeroed`.
- the `ops inventory` items -- `MitateDB-api/tests/test_ops_inventory.py::test_inventory_connection_headroom_max_concurrent_connections_constant_is_pinned`, `::test_inventory_connection_headroom_aggregate_overflow_is_blocked`.
- the `ops inventory` items -- `MitateDB-api/tests/test_ops_inventory.py::test_inventory_connection_headroom_spy_measured_concurrency_stays_at_or_below_the_constant`, `::test_inventory_connection_headroom_rollout_two_processes_confirmed_three_processes_blocked`.
- the `ops inventory` items -- `MitateDB-api/tests/test_ops_inventory.py::test_inventory_connection_headroom_catches_0012_reapplied_alone_after_0014`, `::test_inventory_connection_headroom_catches_0013_reapplied_alone_after_0014_when_a_new_application_exists`.
- the `ops inventory` items -- `MitateDB-api/tests/test_ops_inventory.py::test_inventory_ddl_lock_is_confirmed_without_lock_timeout_declared`, `::test_inventory_ddl_lock_is_unknown_when_statement_timeout_not_declared`, `::test_inventory_ddl_lock_target_roles_include_auditreader`.
- the `ops inventory` items -- `MitateDB-api/tests/test_ops_inventory.py::test_inventory_ddl_lock_target_roles_include_application_roles`, `::test_inventory_ddl_lock_minus_one_connection_limit_is_unknown`, `::test_inventory_ddl_lock_ignores_a_per_database_scoped_setting`.
- the `ops inventory` items -- `MitateDB-api/tests/test_ops_inventory.py::test_inventory_ddl_lock_is_confirmed_by_default_bootstrap_alone`, `::test_inventory_ddl_lock_confirmed_after_0013_is_applied`, `::test_inventory_ddl_lock_is_blocked_when_statement_timeout_is_zero`.
- the `ops inventory` items -- `MitateDB-api/tests/test_ops_inventory.py::test_inventory_ddl_lock_is_blocked_when_statement_timeout_is_negative`, `::test_inventory_ddl_lock_is_blocked_when_statement_timeout_is_unparseable`.
- the `ops inventory` items -- `MitateDB-api/tests/test_ops_inventory.py::test_inventory_ddl_lock_is_blocked_when_only_the_application_runtime_role_is_unbounded`, `::test_inventory_ddl_lock_is_blocked_when_only_the_application_developer_role_is_unbounded`.
- the `ops inventory` items -- `MitateDB-api/tests/test_ops_inventory.py::test_inventory_ddl_lock_blocked_outranks_unknown_when_mixed_with_an_undeclared_role`, `::test_inventory_ddl_lock_minus_one_and_zero_statement_timeout_mixture_is_unknown`.
- the `ops inventory` items -- `MitateDB-api/tests/test_ops_inventory.py::test_inventory_exit_code_is_2_when_ddl_lock_is_blocked`, `::test_inventory_ddl_lock_key_set_is_the_same_on_the_psycopg_error_path`, `::test_inventory_numeric_arguments_reject_zero_and_negative`.
- the `ops inventory` items -- `MitateDB-api/tests/test_ops_inventory.py::test_inventory_reserved_connections_accepts_zero_but_rejects_negative`, `::test_inventory_top_level_and_item_keys_are_pinned`, `::test_inventory_unjudged_parts_vocabulary_is_pinned`.
- the `ops inventory` items -- `MitateDB-api/tests/test_ops_inventory.py::test_inventory_exit_code_is_0_when_every_judged_item_is_confirmed`.
- the disclosed gap below is pinned by a test that turns red if detection ever improves -- `MitateDB-api/tests/test_ops_inventory.py::test_inventory_connection_headroom_misses_0013_reapplied_alone_after_0014_with_no_new_application`.
- per-basis inputs -- `MitateDB-api/tests/test_ops_inventory.py::test_inventory_connection_headroom_old_basis_missing_is_unknown`, `::test_inventory_connection_headroom_thread_limit_missing_is_unknown`, `::test_inventory_connection_headroom_old_basis_zero_without_concurrency_is_judged`.
- refused input shapes -- `MitateDB-api/tests/test_ops_inventory.py::test_inventory_old_basis_exceeding_total_is_rejected_with_exit_code_1`, `::test_inventory_new_basis_count_below_ceiling_is_rejected_with_exit_code_1`.
- refused input shapes -- `MitateDB-api/tests/test_ops_inventory.py::test_inventory_old_basis_zero_with_concurrency_is_rejected_with_exit_code_1`, `::test_inventory_old_basis_shape_checks_run_before_any_connection`.
- the F-16 minimum, per role class -- `MitateDB-api/tests/test_ops_inventory.py::test_inventory_connection_headroom_matches_f16_minimum_limit_for_api`, `::test_inventory_connection_headroom_matches_f16_minimum_limit_for_application`.
- the F-16 minimum, per role class -- `MitateDB-api/tests/test_ops_inventory.py::test_inventory_connection_headroom_matches_f16_minimum_limit_for_controlplane`, `::test_inventory_connection_headroom_matches_f16_minimum_limit_for_auditreader`.
- a floor constant moves both sides -- `MitateDB-api/tests/test_ops_inventory.py::test_inventory_connection_headroom_pool_size_headroom_constant_moves_both`, `::test_inventory_connection_headroom_api_role_store_count_constant_moves_both`.
- a floor constant moves both sides -- `MitateDB-api/tests/test_ops_inventory.py::test_inventory_connection_headroom_controlplane_floor_constant_moves_both`, `::test_inventory_connection_headroom_auditreader_floor_constant_moves_both`.
- mixed bases -- `MitateDB-api/tests/test_ops_inventory.py::test_inventory_connection_headroom_mixed_basis_condition1_boundary_for_api`, `::test_inventory_connection_headroom_mixed_basis_condition1_boundary_for_application`.
- condition 2's application term -- `MitateDB-api/tests/test_ops_inventory.py::test_inventory_connection_headroom_aggregate_application_term_uses_the_per_role_floor_when_larger`.
- condition 2's application term -- `MitateDB-api/tests/test_ops_inventory.py::test_inventory_connection_headroom_aggregate_application_term_uses_the_registration_count_when_larger`.
- condition 2's application term -- `MitateDB-api/tests/test_ops_inventory.py::test_inventory_connection_headroom_aggregate_application_term_registration_count_wins_with_an_old_basis_process`.

#### Status

- **Disclosed detection gap**: a stray `0013` re-applied after `0014` with NO application provisioned afterwards is NOT caught -- every existing role still carries `0014`'s ceiling, so item (8) reads confirmed while the provisioning function is silently back at 36.
- **A stray single-file re-application is not reverted by any migration**, and `MitateDB-api/docs/cloud-run-cloud-sql.md` section 10 carries that gap together with the re-application order.
- **Disclosed scope limit of item (8)'s second condition**: raising a `CONNECTION LIMIT` adds no capacity, so condition 2 (total demand + reserved <= `max_connections`) is untouched by `0014`.
- **`ops inventory` cannot check the declared old-basis process count**: a wrong, too-small declaration undercounts demand -- `MitateDB-api/docs/cloud-run-cloud-sql.md:2611`.
- **The F-16 agreement holds for equal inputs only**: that the thread limit and process counts an operator declares match what each composition root passes F-16 rests on the runbook, not a test -- `docs/design/MITATEDB_INVENTORY_DEMAND_BASIS_V0_1.md` section 10.1.
- What an operator does when a cluster's `max_connections` does not cover the rollout total is not decided yet.

### MitateDB-api -- capacity and concurrency

#### Control

- `process_ceilings` is the same declaration row as r2db-api's own, read from the declaration table alone -- `MitateDB-api/src/mitatedb_api/platform_declarations.py:474`.
- `resolve_limit_enforcement` gives the same per-plane mapping as r2db-api's own, with request-scoped and DB-side-bound classes unaffected -- `MitateDB-api/src/mitatedb_api/capabilities_document.py:33`.
- data-plane `requests_per_minute` reads `enforced` at every ceiling once the PostgreSQL rate row is wired -- `MitateDB-api/src/mitatedb_api/capabilities_document.py:361`.
- data-plane `concurrency` is configured only when the slot directory is wired and `process_ceilings.data` is at most `MITATEDB_WORKERS` -- `MitateDB-api/src/mitatedb_api/main.py:399`.
- `control_requests_per_minute`/`audit_requests_per_minute` stay in-process windows and keep the single-process rule -- `MitateDB-api/src/mitatedb_api/control_plane.py:1584`.
- **F-15** a missing row fails startup fast on both planes and `ops verify-declarations` exits 14 -- `MitateDB-api/src/mitatedb_api/platform_declarations.py:440`.
- `build_app` refuses to start when `MITATEDB_WORKERS` exceeds `process_ceilings.data` -- `MitateDB-api/src/mitatedb_api/main.py:386`.
- `build_control_service` refuses to start when `MITATEDB_CONTROL_WORKERS` exceeds `process_ceilings.control` -- `MitateDB-api/src/mitatedb_api/control_composition.py:173`.
- **F-20** `ops verify-declarations` reports `MITATEDB_WORKERS`/`MITATEDB_CONTROL_WORKERS` above `process_ceilings` with exit code 19 -- `MitateDB-api/src/mitatedb_api/ops.py:1472`.
- the image's CMD runs `python -m mitatedb_api.main --preflight`, which builds the app once and exits non-zero on any startup check, before `exec uvicorn` -- `MitateDB-api/docker/Dockerfile:171`, `MitateDB-api/src/mitatedb_api/main.py:696`.
- the same-named `_take_bound_advisory_lock` helper bounds `applications` and `credentials_per_application` in the database, by the same `pg_advisory_xact_lock` derivation -- `MitateDB-api/src/mitatedb_api/control_plane.py`.
- that helper is pinned textually isomorphic to r2db-api's own by `_ISOMORPHIC_TARGETS` -- `MitateDB-api/src/mitatedb_api/control_plane.py:409`.
- `role_pool_size(thread_limit)`, the thread limit plus 2, is the platform pool's default in `main.build_app`, never the declared `max_concurrency` -- `MitateDB-api/src/mitatedb_api/config.py:335`.
- each served application's `PostgresBackend` holds a runtime and a developer pool of `role_pool_size(thread_limit)` connections, opened lazily -- `MitateDB-api/src/mitatedb_api/backend_postgres.py:331`, `MitateDB-api/src/mitatedb_api/main.py:553`.
- any pool's acquire closes every pool's connections idle for more than 300 s, at most once a second per process -- `MitateDB-api/src/mitatedb_api/pool.py:78`, `MitateDB-api/src/mitatedb_api/pool.py:423`.
- `MitateDB-api/migrations/0012_role_connection_limits.sql` sets each role's ceiling to that role's own pool composition plus one 4-connection operator margin, the same control as r2db-api's own `0013_role_connection_limits.sql`.
- **F-16** takes each role's per-process pool times its own plane's `process_ceilings` value as that role's floor on both peers, with exit code 15 and startup fail-fast -- `MitateDB-api/src/mitatedb_api/platform_declarations.py:1005`.
- **F-18** `headroom_lower_bound` (`MitateDB-api/src/mitatedb_api/platform_declarations.py:1239`, `check_max_connections_headroom` `:1348`, `_f18_message` `:1325`) judges the same necessary condition from declared values alone.
- **F-18** is pinned in `_ISOMORPHIC_TARGETS` with the same three helpers as r2db-api's own row -- `MitateDB-api/src/mitatedb_api/platform_declarations.py:1239`.
- `ops verify-declarations` exits 17 on that shortfall, and both composition roots refuse to start on the same unscoped judgment -- `MitateDB-api/src/mitatedb_api/ops.py:1290`.
- that judgment takes no operator-supplied process count or reserved-connection value, unlike `ops inventory` item (8) (`MitateDB-api/src/mitatedb_api/ops.py:2562`), and reads the process count off `process_ceilings`.
- it counts only ONE registered application's runtime/developer pair toward the judged lower bound, the full registered-application count feeding only the disclosed upper bound -- `MitateDB-api/src/mitatedb_api/platform_declarations.py:1239`.
- the data plane's startup also requires `credential_request_rate_admit(text, integer)` to exist and be EXECUTE-able by its own role, naming `0016` otherwise -- `MitateDB-api/src/mitatedb_api/platform_declarations.py:1493`.
- **`0014_role_connection_limits_rollout.sql`** raises each ceiling to `2 x (that role's own one-process pool) + 4`, for a rollout window running two revisions side by side.
- the resulting ceilings are `mitatedbsvc_api` 132, `mitatedbsvc_controlplane` 36, each application's runtime/developer role 68, `mitatedbsvc_auditreader` 12 -- `MitateDB-api/migrations/0014_role_connection_limits_rollout.sql`.
- `mitatedbsvc_auditreader` is the one role `0012` deliberately left alone, since 5 covered a single process's own 4 -- `MitateDB-api/migrations/0012_role_connection_limits.sql`.
- the operator margin stays ONE 4, not a doubled one -- `MitateDB-api/migrations/0014_role_connection_limits_rollout.sql`.
- **F-16** scales its floor by the declared `process_ceilings` alone, never by the two-revision overlap `0014` provisions for -- `MitateDB-api/src/mitatedb_api/platform_declarations.py:1005`.
- the doubled `CONNECTION LIMIT` itself is read only by `ops inventory` item (8) -- `MitateDB-api/src/mitatedb_api/ops.py:2562`.
- **F-18** reads the declared `process_ceilings` and the same per-process floors, never a role's `CONNECTION LIMIT` -- `MitateDB-api/src/mitatedb_api/platform_declarations.py:1239`.
- the same pre-authentication `concurrency` slot holds here, in the same HTTP-plane order (byte bound -> concurrency slot -> authentication -> body -> rate/business) -- `MitateDB-api/src/mitatedb_api/http.py:547`.
- `HttpService` is fail-closed: its constructor raises unless BOTH the shared `_LimitStateHolder` and the declared `max_concurrency` are supplied, the former no-op branch being removed -- `MitateDB-api/src/mitatedb_api/http.py`.
- one holder is shared by every application in the process, so the bound is deployment-wide rather than per-application -- `MitateDB-api/src/mitatedb_api/cell.py:364`.
- handlers delegate the synchronous section to the threadpool, and each request opens a request scope that borrows its own connections, developer before runtime, before any lock -- `MitateDB-api/src/mitatedb_api/backend_postgres.py:467`.
- one request is one transaction on its scope's main connection, and the idempotency per-key and count locks are `pg_advisory_xact_lock`s inside it -- `MitateDB-api/src/mitatedb_api/backend_postgres.py:1766`, `:1803`.
- a schema operation takes the application-wide `pg_advisory_xact_lock(761761763)`, then its entity's exclusive entity lock, before its first catalog read -- `MitateDB-api/src/mitatedb_api/cell.py:1241`.
- a data write takes each entity it touches as a shared entity lock, sorted, in one statement before pass 1; a query takes neither lock -- `MitateDB-api/src/mitatedb_api/backend_postgres.py:609`, `MitateDB-api/src/mitatedb_api/cell.py:2749`.
- a pool or lock wait past the deadline is `LIMIT_EXCEEDED` (`execution_ms`), and a 40P01/40001 or an unreachable database is `SERVICE_UNAVAILABLE` -- `MitateDB-api/src/mitatedb_api/backend_postgres.py:452`, `:271`.
- the in-process SQLite backend holds one `RLock` for the whole request scope, so one request per cell runs at a time there -- `MitateDB-api/src/mitatedb_api/backend_sqlite.py:126`.
- the same `HostSharedConcurrencySlots` as r2db-api's own, held identical by `_ISOMORPHIC_TARGETS`, bounds `concurrency` across the instance's workers, scanning under the `scan` lock -- `MitateDB-api/src/mitatedb_api/concurrency_slots.py:296`.
- `build_app` refuses to start unless `MITATEDB_SLOT_DIR` is an existing mode-0700 directory owned by this process -- `MitateDB-api/src/mitatedb_api/main.py:311`, `MitateDB-api/src/mitatedb_api/concurrency_slots.py:177`.
- it also refuses to start unless that directory's `selfcheck` file refuses a second `flock` from the same process -- `MitateDB-api/src/mitatedb_api/concurrency_slots.py:200`.
- `credential_request_rate_admit` keeps one `credential_request_rate` row per credential, a 61-second ring on the database clock, admitting only while its total is under the limit -- `MitateDB-api/migrations/0016_credential_request_rate.sql:112`.
- `record_rate_and_check` runs it from the cell's limit gate after authentication, as one autocommit statement on the platform pool, and fails closed with 503 -- `MitateDB-api/src/mitatedb_api/credential_store_postgres.py:618`.
- `mitatedbsvc_api` holds only SELECT/INSERT/UPDATE on that table and EXECUTE on the function, and a deleted credential takes its row by `ON DELETE CASCADE` -- `MitateDB-api/migrations/0016_credential_request_rate.sql:74`, `:82`, `:170`.

#### Evidence

- `process_ceilings`, F-15 -- `MitateDB-api/tests/test_process_ceilings_declaration.py::test_ceiling_one_maps_data_plane_in_memory_classes_to_enforced`, `::test_ceiling_two_maps_data_plane_in_memory_classes_to_deployment_required`.
- `process_ceilings`, F-15 -- `MitateDB-api/tests/test_process_ceilings_declaration.py::test_ceiling_one_maps_control_plane_in_memory_classes_to_enforced`, `::test_ceiling_two_maps_control_plane_in_memory_classes_to_deployment_required`, `::test_region_i_classes_are_unaffected_by_ceiling`.
- `process_ceilings`, F-15 -- `MitateDB-api/tests/test_process_ceilings_declaration.py::test_declaration_table_is_the_only_source`, `::test_ceiling_asymmetric_declaration_maps_through_a_real_composition_root_data_plane`, `::test_missing_row_fails_fast_at_startup_data_plane`.
- `process_ceilings`, F-15 -- `MitateDB-api/tests/test_process_ceilings_declaration.py::test_missing_row_fails_fast_at_startup_control_plane`, `::test_verify_declarations_f15_exit_code`.
- DB-side bounds -- `MitateDB-api/tests/test_process_ceilings_declaration.py::test_db_side_bounds_hold_under_concurrent_writers_applications`, `::test_db_side_bounds_hold_under_concurrent_writers_credentials_per_application`.
- DB-side bounds -- `MitateDB-api/tests/test_process_ceilings_declaration.py::test_db_side_lock_holds_under_barrier_synchronized_two_writers_applications`, `::test_db_side_lock_holds_under_barrier_synchronized_two_writers_credentials_per_application`.
- the platform pool -- `MitateDB-api/tests/test_threadpool_offload.py::test_platform_pool_sized_to_thread_limit_avoids_premature_503`.
- F-16 and F-18 -- `MitateDB-api/tests/test_ops_verify_declarations.py::test_verify_declarations_f16_passes_after_migration_0012`, `::test_verify_declarations_f16_fails_when_a_role_connection_limit_is_lowered_below_its_pool_composition_floor`.
- F-16 and F-18 -- `MitateDB-api/tests/test_ops_verify_declarations.py::test_f16_floor_for_a_role_matching_multiple_classes_is_the_max_not_the_last_assigned`, `::test_f16_the_schema_owning_role_is_never_flagged_even_though_it_matches_every_class`.
- F-16 and F-18 -- `MitateDB-api/tests/test_ops_verify_declarations.py::test_0012_migration_tolerates_a_registered_only_application_and_still_raises_a_provisioned_applications_role_limits`, `::test_verify_declarations_f18_fails_when_the_declared_lower_bound_exceeds_max_connections`.
- F-16 and F-18 -- `MitateDB-api/tests/test_ops_verify_declarations.py::test_verify_declarations_f18_passes_when_the_declared_lower_bound_fits`.
- a ceiling lowered back to a single process's demand still passes F-16 -- `MitateDB-api/tests/test_ops_verify_declarations.py::test_verify_declarations_f16_passes_after_migration_0012`.
- composition roots -- `MitateDB-api/tests/test_application_audit.py::test_build_app_fails_fast_when_its_own_api_role_connection_limit_is_lowered_below_the_pool_composition_floor`.
- composition roots -- `MitateDB-api/tests/test_control_main.py::test_build_control_app_fails_fast_when_its_own_controlplane_role_connection_limit_is_lowered_below_the_pool_composition_floor`.
- `0014` role limits -- `MitateDB-api/tests/test_ops_apply_platform_migration.py::test_apply_platform_migration_0014_sets_role_connection_limits_for_every_role_class`, `::test_apply_platform_migration_0014_new_application_connection_limit_is_68`.
- `0014` role limits -- `MitateDB-api/tests/test_ops_apply_platform_migration.py::test_apply_platform_migration_0014_duplicate_object_fallback_connection_limit_is_68`.
- the pre-auth slot -- `MitateDB-api/tests/test_main.py::test_build_app_wires_the_preauth_concurrency_slot`, `MitateDB-api/tests/test_application_plane_limits.py::test_limit_holder_is_shared_across_applications_in_one_process`.
- the pre-auth slot -- `MitateDB-api/tests/test_preauth_concurrency_bound.py::test_unauthenticated_flood_is_bounded_by_concurrency`, `::test_http_plane_denies_concurrency_before_requests_per_minute`, `::test_concurrency_hold_spans_the_gap_between_authentication_and_dispatch`.
- the pre-auth slot -- `MitateDB-api/tests/test_preauth_concurrency_bound.py::test_slot_is_released_after_a_401_ending_request`, `::test_slot_is_released_after_a_validation_failed_ending_request`, `::test_concurrency_slot_is_acquired_exactly_once_per_handler`.
- offload and locking -- `MitateDB-api/tests/test_threadpool_offload.py::test_concurrent_requests_on_one_application_never_touch_each_others_transaction`, `::test_sync_section_runs_off_the_event_loop`, `::test_post_query_sync_section_runs_off_the_event_loop`.
- offload and locking -- `MitateDB-api/tests/test_threadpool_offload.py::test_post_mutate_sync_section_runs_off_the_event_loop`, `::test_post_cross_entity_mutate_sync_section_runs_off_the_event_loop`, `::test_control_post_issue_credential_sync_section_runs_off_the_event_loop`.
- offload and locking -- `MitateDB-api/tests/test_threadpool_offload.py::test_body_read_stays_on_the_loop`, `::test_limiter_state_is_thread_safe`, `::test_pool_acquire_is_thread_safe`, `::test_concurrency_slot_check_then_increment_is_inside_the_active_lock`.
- a same-key concurrent pair -- `MitateDB-api/tests/test_idempotency_concurrency.py::test_memory_same_key_same_digest_concurrent_executes_exactly_once`, `::test_postgres_same_key_same_digest_concurrent_executes_exactly_once`.
- the request scope -- `MitateDB-api/tests/test_r102_request_scope.py::test_two_requests_of_one_application_are_in_pass_2_at_the_same_time`, `::test_constructing_a_postgres_backend_opens_no_connection`, `::test_the_schema_and_entity_lock_keys_are_the_documented_values_and_distinct`.
- the lock order -- `MitateDB-api/tests/test_r102_request_scope.py::test_keyed_create_collection_and_keyed_add_field_do_not_deadlock`, `::test_a_schema_operation_on_one_entity_does_not_hold_up_data_writes_to_another`, `::test_a_query_is_not_held_by_a_schema_operations_locks`.
- the lock order -- `MitateDB-api/tests/test_r102_request_scope.py::test_a_batch_takes_its_entity_locks_in_one_sorted_deduplicated_statement`, `::test_a_write_and_a_schema_operation_on_one_entity_with_pools_of_one_do_not_wait_in_a_ring`.
- waits and failures -- `MitateDB-api/tests/test_r102_request_scope.py::test_a_write_waiting_for_an_entity_lock_is_cut_by_the_deadline`, `::test_a_pool_wait_that_outlasts_the_deadline_is_limit_exceeded_execution_ms`, `::test_a_database_that_cannot_be_reached_is_service_unavailable`.
- waits and failures -- `MitateDB-api/tests/test_r102_request_scope.py::test_a_deadlock_between_two_batches_is_service_unavailable_not_a_client_error`, `::test_a_serialization_failure_is_service_unavailable_not_a_client_error`, `::test_a_connection_lost_while_taking_a_lock_is_service_unavailable`.
- two cells on one application -- `MitateDB-api/tests/test_r102_cross_cell_windows.py::test_window1_plan_is_checked_against_the_revision_inside_the_ddl_serialization`, `::test_window2_concurrent_alter_field_calls_do_not_lose_each_others_update`.
- two cells on one application -- `MitateDB-api/tests/test_r102_cross_cell_windows.py::test_window3_data_write_validated_before_an_alter_is_not_committed_against_the_new_constraint`, `::test_window4_concurrent_create_collection_cannot_exceed_max_schema_objects`.
- no advisory lock outlives its request -- `MitateDB-api/tests/test_idempotency_concurrency.py::test_postgres_returned_connections_hold_no_advisory_lock_after_any_keyed_request`.
- the role pools -- `MitateDB-api/tests/test_main.py::test_build_app_sizes_each_applications_role_pools_from_the_thread_limit`, `MitateDB-api/tests/test_r102_pool.py::test_release_rolls_back_so_the_next_borrower_gets_a_clean_connection`.
- the idle sweep -- `MitateDB-api/tests/test_r102_pool.py::test_another_pools_acquire_closes_stale_idle_connections_and_spares_in_use_ones`, `::test_the_idle_sweep_runs_at_most_once_per_second_in_the_process`.
- a schema operation waiting for the audit pool -- `MitateDB-api/tests/test_application_audit.py::test_a_schema_operation_waiting_for_the_audit_pool_is_refused_in_bounded_time_and_leaves_no_lock`.
- the mapping -- `MitateDB-api/tests/test_r113_multi_process_wiring.py::test_resolve_limit_enforcement_configured_is_always_enforced_regardless_of_ceiling`, `::test_resolve_limit_enforcement_unconfigured_follows_the_single_process_rule`.
- the mapping on three startup forms -- `MitateDB-api/tests/test_r113_multi_process_wiring.py::test_build_app_concurrency_mapping_follows_workers_vs_ceiling_on_all_three_forms`.
- workers against the ceiling -- `MitateDB-api/tests/test_r113_multi_process_wiring.py::test_build_app_fails_when_workers_exceeds_declared_data_ceiling`, `::test_build_control_app_fails_when_workers_exceeds_declared_control_ceiling`.
- workers against the ceiling -- `MitateDB-api/tests/test_r113_multi_process_wiring.py::test_data_workers_env_rejects_unset_empty_zero_negative_non_numeric`, `::test_verify_declarations_reports_workers_exceeding_ceiling_with_a_dedicated_exit_code`.
- the preflight -- `MitateDB-api/tests/test_r113_multi_process_wiring.py::test_data_preflight_exits_0_on_a_sound_env`, `::test_data_preflight_exits_nonzero_with_f15_when_process_ceilings_missing`.
- the image's preflight -- `MitateDB-api/tests/test_docker_workers_static.py::test_docker_cmd_data_branch_runs_the_data_plane_preflight_before_uvicorn`, `::test_docker_cmd_data_branch_never_reaches_uvicorn_after_a_failed_preflight`.
- the rate function check -- `MitateDB-api/tests/test_r113_multi_process_wiring.py::test_build_app_and_preflight_fail_naming_the_rate_migration_when_the_rate_function_is_missing`.
- the rate function check -- `MitateDB-api/tests/test_r113_multi_process_wiring.py::test_build_app_fails_naming_the_rate_migration_when_the_data_plane_role_may_not_execute_the_rate_function`.
- the host-shared slots -- `MitateDB-api/tests/test_r113_multi_process_wiring.py::test_two_threads_l_c_1_second_is_refused`, `::test_full_slots_refuse_immediately_never_blocking`, `::test_one_request_holds_exactly_one_slot_through_the_reserved_marker`.
- the `scan` lock -- `MitateDB-api/tests/test_r113_multi_process_wiring.py::test_scan_serialises_another_process_behind_a_paused_scan`, `::test_scan_serialises_a_same_process_thread_behind_a_paused_scan`.
- release by the kernel -- `MitateDB-api/tests/test_r113_multi_process_wiring.py::test_slot_is_reacquirable_after_a_holding_child_process_is_sigkilled_and_after_a_plain_close`, `::test_scan_lock_held_by_a_sigkilled_child_process_is_released_by_the_kernel`.
- slot failures answer 503 -- `MitateDB-api/tests/test_r113_multi_process_wiring.py::test_flock_unexpected_errno_maps_to_backend_error_not_admitted_or_denied`, `::test_slot_backend_error_maps_to_503_through_the_limit_state_holder`.
- slot failures answer 503 -- `MitateDB-api/tests/test_r113_multi_process_wiring.py::test_scan_held_past_its_deadline_raises_backend_error_and_the_caller_answers_503`.
- the slot directory -- `MitateDB-api/tests/test_r113_multi_process_wiring.py::test_slot_dir_env_missing_raises_naming_the_variable`, `::test_slot_dir_wrong_owner_raises`, `::test_slot_dir_wrong_mode_raises`, `::test_selfcheck_detects_a_faked_flock_that_never_excludes`.
- the rate row -- `MitateDB-api/tests/test_r113_multi_process_wiring.py::test_pg_rate_admits_up_to_limit_then_denies`, `::test_rate_ring_full_count_60_seconds_ago_still_denies`, `::test_rate_ring_base_s_never_rewinds_after_a_lock_wait`.
- the rate row -- `MitateDB-api/tests/test_r113_multi_process_wiring.py::test_pg_rate_concurrent_first_admissions_for_a_new_credential_never_race`, `::test_pg_rate_db_failure_maps_to_503`.
- the rate row after authentication -- `MitateDB-api/tests/test_r113_multi_process_wiring.py::test_rate_call_is_lexically_outside_every_with_block_in_the_limit_gate`, `::test_denied_authentication_never_writes_a_rate_row`.
- the rate row's grants and reclaim -- `MitateDB-api/tests/test_r113_multi_process_wiring.py::test_0016_api_role_has_select_insert_update_only_no_delete_or_truncate`, `::test_0016_rate_row_cascades_on_credential_delete`.
- one real request holds one slot and writes one rate row -- `MitateDB-api/tests/test_r113_multi_process_wiring.py::test_real_http_request_holds_the_shared_slot_and_writes_a_rate_row`.
- pool sizing from the thread limit -- `MitateDB-api/tests/test_r113_multi_process_wiring.py::test_role_pool_size_is_thread_limit_plus_two`, `::test_build_app_sizes_the_platform_pool_from_mitatedb_thread_limit`, `::test_platform_pool_default_does_not_follow_mitatedb_max_concurrency`.
- F-16 scaled by `process_ceilings.data` -- `MitateDB-api/tests/test_r113_multi_process_wiring.py::test_f16_startup_floor_scales_with_process_ceilings_data`.
- F-16 scaled by `process_ceilings.control`: the controlplane role's limit 20 clears floor 16 at `control` 1 and fails floor 32 at `control` 2 -- `MitateDB-api/tests/test_ops_verify_declarations.py::test_f16_controlplane_floor_scales_with_process_ceilings_control`.
- `ops verify-declarations` passes the declared `control` 2 into F-16 and fails the auditreader role at floor 8 -- `MitateDB-api/tests/test_ops_verify_declarations.py::test_f16_aggregate_ops_call_scales_controlplane_floor_by_declared_process_ceilings`.

#### Status

- **The two peers' CEILINGS are no longer the same arithmetic**: whether r2db-api's own deployment ever runs an old and a new revision of the same plane side by side is NOT verified, so this is a still-unverified asymmetry rather than an accepted one (ledger item R-52, still open).
- **F-18's floors do not track this peer's `MITATEDB_PLATFORM_POOL_SIZE` override**, exactly as F-16's do not.
- **The control plane's startup judgment reads the thread limit from its own process environment** (`MITATEDB_THREAD_LIMIT`, as its F-16 call does), so a control deployment whose value differs from the data plane's judges a different floor for the application pair.
- If the open rollout-overlap question (R-52) is resolved by declaring the overlap's own process count in `process_ceilings`, that count is exactly what this lower bound already counts.
- **`concurrency` is shared within one instance only**: `enforced` holds only while `--max-instances=1` keeps every data worker on that instance, which neither composition root can read -- `MitateDB-api/docs/cloud-run-cloud-sql.md:1399`.
- **During a rollout overlap the slots are not shared**: an old and a new revision on two instances may hold up to twice the declared `concurrency`, while `requests_per_minute` still holds -- `MitateDB-api/docs/cloud-run-cloud-sql.md:1792`.
- **A worker stopped while holding `scan` holds up the whole instance**: every acquisition waits up to 1 s and answers 503; the runbook forbids stopping a single worker -- `MitateDB-api/docs/cloud-run-cloud-sql.md:1706`.
- **The rate ring may refuse slightly early**: at a window edge it counts up to one second more than 60 s, and never admits more than the declared `requests_per_minute` -- `MitateDB-api/docs/cloud-run-cloud-sql.md:1784`.
- **A database clock that steps back stretches the rate window by that step**: the ring's base second never moves back, so no count ages out until the clock passes it again (stricter, never looser); read from the function, not tested -- `MitateDB-api/migrations/0016_credential_request_rate.sql:149`.
- **A database clock that steps forward ages counts out early**: the ring reads the database's wall clock, so a forward step admits up to twice the declared `requests_per_minute` in 60 real seconds; read from the function, not tested -- `MitateDB-api/migrations/0016_credential_request_rate.sql`.
- **SIGHUP or SIGTTIN runs more data workers than declared**: the uvicorn supervisor then runs `MITATEDB_WORKERS + 1` or more, beyond `process_ceilings.data` and the F-16/F-18 budget; no check sees it and only the runbook forbids it -- `MitateDB-api/docs/cloud-run-cloud-sql.md:1698`.
- **The image's evidence is static**: the tests above read the Dockerfile as text; the development machine has no container runtime, so the preflight-then-uvicorn order is confirmed only on a deployed revision -- `MitateDB-api/docs/cloud-run-cloud-sql.md:1810`.
- **F-20 reads the workers from the operator's own shell**, never from the running revision, so it is a hand cross-check; the preflight's check is the one that stops a revision -- `MitateDB-api/src/mitatedb_api/ops.py:1472`.
- **A new `process_ceilings` changes which running revisions can start**: section 10.10.1 step 6 judges F-16 / F-18 for every listed revision with `ops startup-checks` -- `MitateDB-api/docs/cloud-run-cloud-sql.md:3785`, `MitateDB-api/src/mitatedb_api/startup_checks.py:913`.
- **A keyed write holding the idempotency count lock while it waits for an entity lock** holds up other keys' keyed writes until the schema operation on that entity ends -- `docs/design/MITATEDB_APPLICATION_SERIALIZATION_V0_1.md` section 10.
- **A process that receives no request closes no idle connection**: the idle sweep runs only inside an acquire -- `MitateDB-api/src/mitatedb_api/pool.py:423`.

### Common

#### Control

- C-30 stateless paging -- a traversal's whole position lives in the token the client echoes back; the service keeps no cursor table, timer or ceiling (`r2db-api/src/r2db_api/paging.py`, `MitateDB-api/src/mitatedb_api/paging.py`).

#### Evidence

- A cursor is honored in a second session under a different credential, and two identical requests return the identical token: `test_c30_keyset_paging.py::test_c30_cursor_is_stateless`, `::test_c30_cursor_is_deterministic`.
- the three control-plane SI-08 classes agree under C-14's vector 5 -- `conformance-tests/test_c14_authority_boundary.py` (see the SI-00 row above for the adapter-state detail).
- `batch_entities` agrees under C-16, on all four adapters -- `conformance-tests/test_c16_cross_entity_atomicity.py` (see the SI-11 row below).
- two real-socket plugs (`r2db-api-socket`/`MitateDB-api-socket`, a uvicorn process behind a real nginx) drive C-05's V2 vector over a real wire -- `conformance-tests/test_c05_limit_declaration_agreement.py::test_c05_v2_declaration_and_position_agree`.
- that vector drives `concurrency` through the port's own `hold_in_flight` on every registered plug -- `conformance-tests/test_c05_limit_declaration_agreement.py::test_c05_v2_declaration_and_position_agree`.
- whether a plug's readiness probe already consumed a unit of the bound is judged by `adapter.transport_kind`, never by name -- `conformance-tests/test_c05_limit_declaration_agreement.py::test_c05_l7_21_v2_drivers_do_not_gate_drive_or_not_on_peer_name`.
- plug names and declared `transport_kind` -- `conformance-tests/test_c05_limit_declaration_agreement.py::test_c05_all_plug_names_match_the_registry`, `conformance-tests/test_socket_harness.py::test_every_registered_adapter_declares_transport_kind`.
- a restart between ceiling 1 and ceiling 2, from each peer's own documented composition root, on both planes (C-26) -- `conformance-tests/test_c26_composition_root.py::test_c26_ceiling_maps_to_limit_enforcement`.
- F-15 and F-16 in that real deployment -- `conformance-tests/test_c26_composition_root.py::test_c26_missing_declaration_fails_fast`, `::test_c26_role_connection_limit_below_pool_floor_fails_fast`.
- the three startup forms (C-26 (4)) -- `conformance-tests/test_c26_composition_root.py::test_c26_ceiling1_workers1_all_classes_enforced`, `::test_c26_ceiling2_workers2_concurrency_declaration_matches_wiring`, `::test_c26_ceiling2_workers1_concurrency_deployment_required`.
- the three startup forms (C-26 (4)) -- `conformance-tests/test_c26_composition_root.py::test_c26_ceiling2_requests_per_minute_declaration_matches_wiring_both_worker_forms`, `::test_c26_control_ceiling2_deployment_required`.
- the preflight and the `workers >= 2` form -- `conformance-tests/test_c26_composition_root.py::test_c26_preflight_precedes_data_uvicorn_start`, `::test_c26_preflight_precedes_data_uvicorn_start_with_workers_2`, `::test_c26_missing_declaration_fails_fast_multi_worker`.
- one slot directory per launcher instance, removed on stop -- `conformance-tests/test_c26_composition_root.py::test_c26_slot_directory_is_per_instance_and_removed_on_stop`.
- `concurrency` across two workers (C-32) -- `conformance-tests/test_c32_shared_limits.py::test_c32_concurrency_in_flight_count_matches_declared_bound`, `::test_c32_concurrency_lock_waiters_span_2_or_more_workers`.
- `requests_per_minute` across two workers (C-32) -- `conformance-tests/test_c32_shared_limits.py::test_c32_requests_per_minute_200_count_matches_declared_bound`, `::test_c32_requests_per_minute_429_count_matches_declared_bound`.
- `requests_per_minute` across two workers (C-32) -- `conformance-tests/test_c32_shared_limits.py::test_c32_requests_per_minute_200_pids_span_2_or_more_workers`.

#### Status

- Statelessness itself is not observable from the port: no registered plug spans more than one process, so a server-side cursor table keyed by a deterministic token would pass both tests above; it is enforced by both peers' paging module holding no state.
- **No cited evidence for the common SI-08 resource bounds**: no test is named for this block's blanket resource-boundary claim beyond C-05, C-14, C-16, C-26 and C-32; version 2.25's uncited wording is in the history file.
- **Disclosed limits, carried from the C-05 and C-26 rows of `conformance-tests/CONDITIONS.md`**: this suite still cannot distinguish a deployment-wide counter from a credential-scoped one.
- `execution_ms` and `idempotency_retention_ms` are never driven by this suite.
- C-26 and C-32 start each declared base URL on one host; every preflight and worker checks workers against the declared ceiling, but no check reads how many hosts serve that URL, which rests on the one-host runbook rule and the post-deployment check.

## SI-09 Controlled Destructive Operations

[history](CONTROL_MAPPING_HISTORY.md#si-09)

### r2db-api

#### Control

- `structured.py` requires operation-specific confirmation for delete and drop, `drop_index` included -- `r2db-api/src/r2db_api/structured.py:1783`.
- **CCR-13** treats dropping a declared unique index as schema deletion like `drop_entity`, since it is effectively irreversible once duplicate data has entered (R-5) -- `r2db-api/src/r2db_api/structured.py:568`.
- the check runs before any revision-precondition evaluation on `update`/`delete`, failure before execution (R-4) -- `r2db-api/src/r2db_api/structured.py:1800`.
- `structured.py` defines phrase construction exactly once for 4 of the 5 gated surfaces, imported by both `control_plane.py` and `ops.py` rather than reimplemented -- `r2db-api/src/r2db_api/structured.py:22`.
- the 4 surfaces sharing that module are `delete`/`drop_entity`/`drop_index`, `revoke_credential`'s last-control-credential gate, and the ritual CLI's `reset`/`delete-credential` -- `r2db-api/src/r2db_api/structured.py:1772`.
- the 5th gated surface, the ritual CLI's `deprovision`, keeps its own phrase (`_deprovision_confirmation_phrase`, `ops.py`) beside its caller -- `r2db-api/src/r2db_api/ops.py:2056`.
- `_deprovision_confirmation_phrase`'s material (`r2dbsvc_registry.applications.provisioned_at`) is a registry value `structured.py`'s own cell-layer phrase functions never read -- `r2db-api/src/r2db_api/ops.py:2056`.
- `_deprovision_confirmation_phrase` is held isomorphic to MitateDB-api's own same-named function by `_ISOMORPHIC_TARGETS` -- `r2db-api/src/r2db_api/ops.py:2056`.
- all 6 data/schema call sites declare the same 4 machine-readable keys through `require_destructive_confirmation`'s `details` synthesis -- `r2db-api/src/r2db_api/delete_confirmation.py:248`.
- `ControlPlaneService.revoke_credential` determines the sole-remaining-enabled-control-credential judgment and performs the state change together, inside the SAME transaction under a row-locked scan -- `r2db-api/src/r2db_api/control_plane.py:929`.
- that same-transaction ordering closes the TOCTOU window a judgment made outside the open transaction would leave open -- `control_plane.py`.
- the ritual CLI's `reset` and `delete-credential` gate on the identical declare-and-echo protocol before any store or DSN is constructed, so a wrong `--confirm` never touches the database -- `r2db-api/src/r2db_api/ops.py:327`.
- `deprovision`'s registry read sits at contract `destructive_confirmation`'s own `evaluation_order` position for target-existence, before precondition evaluation -- `r2db-api/src/r2db_api/ops.py:2113`.
- `destructive`/`confirm(ation)` are type-checked at all 4 gated surfaces, including over the real HTTP wire -- `r2db-api/src/r2db_api/delete_confirmation.py:248`.
- a non-`bool` or non-`str` value there is refused `VALIDATION_FAILED` before the confirmation check itself, never truthy-accepted -- `r2db-api/src/r2db_api/delete_confirmation.py:248`.
- **`apply-platform-migration`** applies a RUN of one or more of the 6 known re-appliable platform migrations (0008/0012/0013/0014/0015/0016), in ascending order, against `R2DB_CONTROL_DSN` -- `r2db-api/src/r2db_api/ops.py:1812`, `:2004`.
- that enumeration never includes the bootstrap-only `0001`/`0002` or the password-carrying `0005`/`0006`/`0007` -- `r2db-api/src/r2db_api/ops.py:1858`.
- `apply-platform-migration` refuses a FILENAME outside the enumeration, carrying a path separator, or resolving outside the migrations directory with symlinks followed, before any psql subprocess starts -- `r2db-api/src/r2db_api/ops.py:2004`.
- the rejected filename value is never echoed -- `r2db-api/src/r2db_api/ops.py:2004`.
- a run is refused, with no psql subprocess started, unless every FILENAME is strictly ascending with no repeat -- `r2db-api/src/r2db_api/ops.py:1946`.
- `0008`'s own required successor `0012` must be present later in the same call, the only closure entry of `_PLATFORM_MIGRATION_SUPERSEDED_BY` -- `r2db-api/src/r2db_api/ops.py:1858`.
- that map is derived statically from the 6 accepted files' own targets, whose one redefinition is `0012` re-adding `0008`'s `platform_declarations_key_check` constraint, and proved equal to it -- `r2db-api/src/r2db_api/ops.py:1858`.
- the DSN is environment-only (`R2DB_CONTROL_DSN`, no CLI argument) -- `r2db-api/src/r2db_api/ops.py:2004`.
- a required no-default `--lock-timeout` reaches psql via `PGOPTIONS` without discarding a DSN-supplied `options` value -- `r2db-api/src/r2db_api/ops.py:2368`.
- a failed file's own output is redacted before reaching stderr, and that file is excluded from both `applied` and `not run` -- `r2db-api/src/r2db_api/ops.py:2004`.
- **`deprovision`** permanently removes an application's database, both its login roles and its registry row via `0004_deprovision_application.sql`, gated by `_require_cli_confirmation` -- `r2db-api/src/r2db_api/ops.py:2113`.
- `deprovision`'s gate is the SAME declare-and-echo `--confirm` protocol as `reset`/`delete-credential` -- `r2db-api/src/r2db_api/ops.py:327`.
- the slug's format is validated before any database access, and an unregistered or never-provisioned slug is refused before any phrase is computed -- `r2db-api/src/r2db_api/ops.py:2113`.
- a mismatched `--confirm` is a JSON denial that writes nothing and starts no psql subprocess -- `r2db-api/src/r2db_api/ops.py:2113`.
- the confirmation phrase is fingerprinted on `r2dbsvc_registry.applications.provisioned_at`, peer-isomorphic to MitateDB-api's own phrase fingerprinted on `registered_at` -- `r2db-api/src/r2db_api/ops.py:2056`.
- deprovisioning a slug and re-provisioning it changes `provisioned_at`, so a stale echoed phrase is refused -- `r2db-api/src/r2db_api/ops.py:2056`.
- the AST-derived set of subcommands that flow a migration file through psql is exactly the set whose own `--lock-timeout` is required with no default -- `r2db-api/src/r2db_api/ops.py:2395`.
- `apply_schema` reads the revision a drop confirmation phrase binds under the application-wide schema lock, so a concurrent schema operation cannot advance it between the check and the drop -- `r2db-api/src/r2db_api/postgres.py:2234`, `:2157`.

#### Evidence

- atomic rollback, `drop_index` -- `test_atomic_rollback_and_explicit_destructive_operation`, `test_drop_index_requires_destructive_confirmation`.
- the CLI, data-plane and control-plane phrases share `structured.py`, fixed by an object-identity assertion -- `test_cli_phrases_share_the_structured_module_with_data_and_control_plane_phrases`.
- the `revoke_credential` gate judgment inside the open transaction, and the locked scan -- `test_revoke_credential_gate_judgment_is_made_inside_the_open_transaction`, `test_control_credentials_locked_scan_serializes_against_a_concurrent_scan`.
- confirmation gates -- `test_cli_reset_without_confirm_declares_and_touches_nothing`, `test_cli_delete_credential_without_confirm_declares_and_touches_nothing`.
- a confirm mismatch -- `r2db-api/tests/test_ops_apply_platform_migration.py::test_deprovision_confirm_mismatch_is_a_json_denial_and_touches_nothing`.
- no psql subprocess starts and the registry is untouched -- `r2db-api/tests/test_ops_apply_platform_migration.py::test_deprovision_confirm_mismatch_is_a_json_denial_and_touches_nothing`.
- non-boolean `destructive` -- `test_delete_rejects_truthy_non_boolean_destructive_before_confirmation`, `test_revoke_last_control_credential_with_wire_truthy_non_boolean_destructive_is_validation_failed`.
- the platform-migration CLI -- `r2db-api/tests/test_ops_apply_platform_migration.py::test_apply_platform_migration_rejects_unknown_filename_before_any_psql`, `::test_apply_platform_migration_rejects_path_separator_in_filename`.
- the platform-migration CLI -- `r2db-api/tests/test_ops_apply_platform_migration.py::test_apply_platform_migration_rejects_symlink_escaping_migrations_dir`, `::test_apply_platform_migration_rejects_missing_file`, `::test_apply_platform_migration_rejects_out_of_order_run`.
- the platform-migration CLI -- `r2db-api/tests/test_ops_apply_platform_migration.py::test_apply_platform_migration_rejects_duplicate_filename_in_run`, `::test_apply_platform_migration_solo_0008_is_rejected_with_the_full_required_run`.
- the platform-migration CLI -- `r2db-api/tests/test_ops_apply_platform_migration.py::test_platform_migration_superseded_by_equals_the_target_map_folded_to_file_level`, `::test_apply_platform_migration_pgoptions_carries_lock_timeout_and_preserves_dsn_options`.
- the platform-migration CLI -- `r2db-api/tests/test_ops_apply_platform_migration.py::test_apply_platform_migration_failure_output_names_applied_and_not_run_and_redacts`, `::test_apply_platform_migration_parser_has_no_dsn_argument`, `::test_apply_platform_migration_requires_r2db_control_dsn_env`.
- the platform-migration CLI -- `r2db-api/tests/test_ops_apply_platform_migration.py::test_apply_platform_migration_lock_timeout_is_required_with_no_default`, `::test_deprovision_rejects_malformed_slug_before_any_db_access`, `::test_deprovision_rejects_unregistered_slug`.
- the platform-migration CLI -- `r2db-api/tests/test_ops_apply_platform_migration.py::test_deprovision_confirmation_phrase_changes_across_reprovision`, `::test_ddl_flowing_subcommands_are_exactly_apply_platform_migration_upgrade_applications_deprovision`.
- the platform-migration CLI -- `r2db-api/tests/test_ops_apply_platform_migration.py::test_psql_file_launching_functions_are_exactly_the_3_expected`, `::test_ddl_flowing_subcommands_match_the_required_lock_timeout_set`.
- `0015` is in the accepted set and takes no psql variable -- `r2db-api/tests/test_r113_multi_process_wiring.py::test_ops_accepts_0015_as_a_known_platform_migration`.
- the drop confirmation window, two cells on one application -- `r2db-api/tests/test_r102_schema_windows.py::test_confirmation_window_drop_entity_confirmation_is_checked_against_the_revision_inside_the_ddl_serialization`.

#### Status

- **`deprovision`'s gate is not read-free**: unlike `reset`/`delete-credential`, a wrong `--confirm` still reads the registry for the phrase's own material, though it writes nothing there and starts no psql subprocess.

### MitateDB-api

#### Control

- `ApplicationCell.delete` implements contract 1.2.0 declare-and-echo, the peer declaring `contract_version=1.3.0` and unaffected by the later additive flip -- `MitateDB-api/src/mitatedb_api/cell.py:2363`.
- a valid confirmation requires `destructive is True` AND `confirm` to equal exactly the server's recomputed `DELETE <collection> @where=<digest16>` phrase -- `MitateDB-api/src/mitatedb_api/cell.py:2363`.
- the `@where=<digest16>` digest is the SHA-256 of the canonically-serialized filter list, no state fingerprint being needed since this peer has no drop/recreate path -- `MitateDB-api/src/mitatedb_api/cell.py:2363`.
- a non-bool `destructive` or non-str `confirm` is refused as a shape defect, never truthy-accepted -- `MitateDB-api/src/mitatedb_api/cell.py:2363`.
- `DestructiveConfirmationRequired` carries the contract's 4 keys with `reversible_alternative`/`recovery` both null, mirroring r2db-api -- `MitateDB-api/src/mitatedb_api/errors.py`.
- the `delete` phrase carries an `@schema_revision=<n>` fingerprint alongside `@where=<digest16>`, so a drop-then-recreate under the same name cannot leave a stale phrase valid -- `MitateDB-api/src/mitatedb_api/cell.py:2363`.
- the control-plane `revoke_credential` last-active gate performs its target-set scan and state change inside the SAME transaction, closing the TOCTOU window exactly as r2db-api's does -- `MitateDB-api/src/mitatedb_api/control_plane.py:1921`.
- the break-glass CLI's `revoke-credential` reuses that SAME gate rather than reimplementing it -- `MitateDB-api/src/mitatedb_api/ops.py:454`.
- `deprovision <application_id>` is this peer's own second genuinely destructive CLI subcommand, provisioning-level, against `MITATEDB_PROVISION_DSN` -- `MitateDB-api/src/mitatedb_api/ops.py:769`.
- `deprovision`'s phrase is fingerprinted on `applications.registered_at`, so it goes stale across a deprovision-then-reregister cycle -- `MitateDB-api/src/mitatedb_api/ops.py:528`.
- **`ops inventory` never mutates platform state**: every connection it opens comes from the single factory `_inventory_connect`, never a bare `psycopg.connect` elsewhere in its own code -- `MitateDB-api/src/mitatedb_api/ops.py:2226`.
- `_inventory_connect` sets `default_transaction_read_only = on` immediately after connecting and reads the setting back rather than trusting it was applied -- `MitateDB-api/src/mitatedb_api/ops.py:2226`.
- item (3)'s per-application ledger read survives `read_applied_upgrade_numbers`'s own `UndefinedTable`/`conn.rollback()` recovery path without losing its read-only setting or its two session timeouts -- `MitateDB-api/src/mitatedb_api/ops.py:2253`.
- item (3)'s ledger read runs with `autocommit=True`, never inside an open transaction a rollback could unwind -- `MitateDB-api/src/mitatedb_api/ops.py:2226`.
- each connection also carries a fixed `lock_timeout`/`statement_timeout` of 3000ms/5000ms, so a read cannot queue behind, or itself prolong, a concurrent migration or upgrade -- `MitateDB-api/src/mitatedb_api/ops.py:2226`.
- a read that exceeds either timeout leaves its own item unknown, never confirmed -- `MitateDB-api/src/mitatedb_api/ops.py:2465`.
- `cmd_inventory`'s own read-only readback gates the whole run: a false readback fails the subcommand closed and never proceeds to build a report -- `MitateDB-api/src/mitatedb_api/ops.py:3093`.
- item (3)'s own per-application connections are read-only the same way the platform connection is, confirmed by the SAME readback on each one -- `MitateDB-api/src/mitatedb_api/ops.py:2253`.
- if any of `_inventory_connect`'s own three `SET` statements fails, the connection is closed before the exception propagates, never leaked half-configured -- `MitateDB-api/src/mitatedb_api/ops.py:2226`.

#### Evidence

- the full strict-branch vector set (V1-V5 and V8) is exercised here; V6 and V7 use the shared absence mechanism, since this peer has no `drop_entity` or control-plane surface -- `test_c06_destructive_confirmation.py`.
- `delete` gating, `where` -- `test_delete_without_confirmation_is_gated_not_conflated_with_empty_filters`, `test_delete_rejects_non_boolean_destructive_and_non_string_confirm`, `test_canonical_where_json_key_sorts_each_filter_preserves_list_order_never_stringifies`.
- credential and `deprovision` -- `test_revoke_credential_confirmation_denial_is_durably_audited`, `test_revoke_last_active_control_credential_gate_against_real_postgres`, `test_deprovision_without_confirm_declares_the_phrase_and_touches_nothing`.
- credential and `deprovision` -- `test_deprovision_with_the_echoed_phrase_removes_the_registration`.
- read-only connections -- `MitateDB-api/tests/test_ops_inventory.py::test_inventory_connections_reject_writes_outside_an_explicit_transaction`, `::test_inventory_application_connections_also_reject_writes`, `::test_inventory_application_connections_confirm_read_only`.
- read-only connections -- `MitateDB-api/tests/test_ops_inventory.py::test_inventory_confirms_read_only_by_reading_it_back`, `::test_inventory_ledger_absent_read_only_survives_the_internal_rollback`, `::test_inventory_all_opened_connections_go_through_the_factory`.
- read-only connections -- `MitateDB-api/tests/test_ops_inventory.py::test_inventory_never_calls_psycopg_connect_outside_its_own_factory`, `::test_inventory_connect_closes_the_connection_when_a_set_statement_fails`, `::test_inventory_tool_failure_when_read_only_cannot_be_confirmed`.
- session timeouts -- `MitateDB-api/tests/test_ops_inventory.py::test_inventory_session_timeouts_are_actually_set`, `::test_inventory_session_timeout_constants_are_pinned`, `::test_inventory_credentials_lock_timeout_exceeded_is_unknown`.

#### Status

- **`ops inventory`'s read-only setting is a TOOL-SIDE property, not a privilege boundary**: the connecting role can still write on a DIFFERENT connection.

### MitateDB-api -- platform upgrade

#### Control

- **`apply-platform-migration`** applies one or more platform migration files in the fixed pinned order (0005/0007/0011/0012/0013/0014/0016/0017 only) against `MITATEDB_PROVISION_DSN` -- `MitateDB-api/src/mitatedb_api/ops.py:2804`, `:3001`.
- that enumeration never includes the bootstrap-only 0001/0002 or a file taking `:app_id` -- `MitateDB-api/src/mitatedb_api/ops.py:2804`.
- each FILENAME is a bare name with no path separator, matched against that pinned enumeration -- `MitateDB-api/src/mitatedb_api/ops.py:3001`.
- `apply-platform-migration` resolves both the migrations directory and the candidate file with symlinks followed, to confirm the file stays inside that directory before any psql subprocess starts -- `MitateDB-api/src/mitatedb_api/ops.py:3001`.
- a rejected filename value is never echoed -- `MitateDB-api/src/mitatedb_api/ops.py:3001`.
- a run is refused, with no psql subprocess started, unless every given FILENAME is strictly ascending in that pinned order with no repeat -- `MitateDB-api/src/mitatedb_api/ops.py:2941`.
- for every file that has a later-accepted file redefining one of its own targets, every one of those later files must be present too, later in the same call -- `MitateDB-api/src/mitatedb_api/ops.py:2846`.
- a target is a role or function's own `CONNECTION LIMIT`, a role-level `SET` parameter, or a `CREATE OR REPLACE FUNCTION` body -- `MitateDB-api/src/mitatedb_api/ops.py:2846`.
- the target-level map is derived statically from the 8 accepted files themselves and proved equal, folded to file granularity, to the constant this check reads -- `MitateDB-api/src/mitatedb_api/ops.py:2846`.
- the rejection names the required run, never the operator's own given values -- `MitateDB-api/src/mitatedb_api/ops.py:2945`.
- only the FILENAMEs the operator explicitly listed are ever started, an omitted successor never being added automatically -- `MitateDB-api/src/mitatedb_api/ops.py:3001`.
- each accepted file runs through its own separate psql invocation, in the given order, so a mid-run psql failure stops before any later file starts -- `MitateDB-api/src/mitatedb_api/ops.py:3021`.
- that failure reports which files applied, which did not run, and that the whole run must be re-run from its first file, never the failed file alone -- `MitateDB-api/src/mitatedb_api/ops.py:3021`.
- the DSN is environment-only, with no CLI argument (design Z-8/D-10), and psql runs under `ON_ERROR_STOP=1` -- `MitateDB-api/src/mitatedb_api/ops.py:3021`.
- a required no-default `--lock-timeout` reaches psql via `PGOPTIONS` through `_with_lock_timeout_option`, the SAME helper `upgrade-applications`/`deprovision` use -- `MitateDB-api/src/mitatedb_api/ops.py:742`.
- psql's own captured output is redacted before any failure message reaches stderr -- `MitateDB-api/src/mitatedb_api/ops.py:3021`.
- per-file psql variables (`0007`'s own `:api_role`/`:controlplane_role`) are a static table matched against each file's own real references, excluding comments and casts -- `MitateDB-api/src/mitatedb_api/ops.py:3001`.
- `apply-platform-migration` refuses a table entry the operator omits, or an argument the table does not list, before any subprocess starts -- `MitateDB-api/src/mitatedb_api/ops.py:3001`.
- the AST-derived set of subcommands that flow a migration file through psql is exactly the set whose own `--lock-timeout` is required with no default -- `MitateDB-api/src/mitatedb_api/ops.py:3001`.
- `set-platform-timeouts` and the `declare-*` subcommands, which are psycopg-only configuration writes, are never in that set -- `MitateDB-api/src/mitatedb_api/ops.py:3001`.
- against production, `apply-platform-migration` is run only through the runbook's gated procedure, whose stage 2 preconditions the Platform-upgrade runbook claims below state -- `MitateDB-api/docs/cloud-run-cloud-sql.md` section 10.
- the subcommand names that same section in its own help text, section-heading comment and docstring -- `MitateDB-api/src/mitatedb_api/ops.py:3001`.
- **`0013_role_statement_timeouts.sql`** sets a role-level `statement_timeout` on `mitatedbsvc_auditreader` and on every application's own runtime/developer role -- `MitateDB-api/migrations/0013_role_statement_timeouts.sql`.
- it does so retroactively for already-provisioned roles, inside one transaction, so a permission failure partway rolls the whole file back with no half-applied state -- `MitateDB-api/migrations/0013_role_statement_timeouts.sql`.
- it does so going forward through `begin_provision_application`'s own `CREATE OR REPLACE`, in both the `CREATE ROLE` branch and its `duplicate_object` fallback -- `MitateDB-api/migrations/0013_role_statement_timeouts.sql`.
- `0013_role_statement_timeouts.sql` skips a registry row naming a role `pg_roles` no longer carries, rather than aborting the migration -- `MitateDB-api/migrations/0013_role_statement_timeouts.sql`.
- `0013` must run after `0012`, since both `CREATE OR REPLACE` the identical function -- `MitateDB-api/migrations/0012_role_connection_limits.sql`.
- applying `0013` requires ADMIN OPTION on `mitatedbsvc_auditreader` under PostgreSQL 16's own CREATEROLE rule, refused rather than bypassed when absent -- `MitateDB-api/migrations/0013_role_statement_timeouts.sql`.
- **`0014_role_connection_limits_rollout.sql`** applies the raised ceilings SI-08's `capacity and concurrency` block states, retroactively for already-provisioned runtime/developer roles.
- `0014_role_connection_limits_rollout.sql` likewise skips a registry row whose role `pg_roles` no longer carries, rather than aborting the file -- `MitateDB-api/migrations/0014_role_connection_limits_rollout.sql`.
- it applies going forward through the same `CREATE OR REPLACE`, in both the `CREATE ROLE` branch and its `duplicate_object` fallback -- `MitateDB-api/migrations/0014_role_connection_limits_rollout.sql`.
- the WHOLE file runs inside one transaction, so a permission failure partway leaves nothing changed rather than a half-applied state -- `MitateDB-api/migrations/0014_role_connection_limits_rollout.sql`.
- `0014` is the third and last file to replace that function, running after `0012` and `0013`, and its replacement keeps `0013`'s `statement_timeout` lines unchanged -- `MitateDB-api/migrations/0014_role_connection_limits_rollout.sql`.
- `0014`'s header overwrites, rather than erases, `0012`'s own statement that `mitatedbsvc_auditreader` is deliberately left untouched -- `MitateDB-api/migrations/0014_role_connection_limits_rollout.sql`.
- `0014` requires ADMIN OPTION on every role it alters, exactly as `0013` requires it, refused rather than bypassed -- `MitateDB-api/migrations/0014_role_connection_limits_rollout.sql`.
- **Platform-upgrade runbook** section 10 is the operator procedure for the Gate-0 read and the platform upgrade, in four stages: first read, platform remediation, second read, candidate -- `MitateDB-api/docs/cloud-run-cloud-sql.md` section 10.
- only the remediation and candidate stages change production state; a read performs no DDL, no DML, no declaration replacement, no restart, no traffic change and no API enablement -- `MitateDB-api/docs/cloud-run-cloud-sql.md` section 10.
- Gate-0 is ready only when all 10 items are confirmed AND section 10.8's acceptance records name the current versions; `ops inventory`'s own exit status 0 never makes it ready -- `MitateDB-api/docs/cloud-run-cloud-sql.md:3090`.
- what ready gates is exactly the candidate deploy and the traffic switch onto it -- `MitateDB-api/docs/cloud-run-cloud-sql.md` section 10.
- Section 10.2 orders the isolated proof, the independent audit and the requester's approval before anything in either state-changing stage runs -- `MitateDB-api/docs/cloud-run-cloud-sql.md` section 10.2.
- the remediation stage, which ready does not gate, carries the same three conditions for its own single move of traffic percentages onto the env-only revision running the same image digest -- `MitateDB-api/docs/cloud-run-cloud-sql.md` section 10.2.
- removing a tag that keeps a Data revision out of the concurrency agreement moves no percentages but is the same traffic projection, under those same three conditions -- `MitateDB-api/docs/cloud-run-cloud-sql.md` section 10.2.
- before the remediation stage changes anything, item (8)'s connection-demand arithmetic is computed on paper from the inputs the second read will pass and the limits in force at that read -- `MitateDB-api/docs/cloud-run-cloud-sql.md` section 10.
- those limits are `0012`'s own value for a role it names and the catalog value for every other role -- `MitateDB-api/docs/cloud-run-cloud-sql.md` section 10.
- a role whose `CONNECTION LIMIT` sits below its own demand is reported and stopped on rather than remediated there, since raising such a limit takes a new platform migration -- `MitateDB-api/docs/cloud-run-cloud-sql.md` section 10.
- an `unknown` that survives the second read stops the procedure and is never carried forward as a warning -- `MitateDB-api/docs/cloud-run-cloud-sql.md` section 10.
- That acceptance record judges item (5) and item (6)'s lock/downtime half, matching `inventory`'s own `unjudged_items`/`runbook-acceptance` -- `MitateDB-api/docs/cloud-run-cloud-sql.md:3044`.
- platform migrations run only in numbered-set order through `apply-platform-migration` with its required `--lock-timeout`: `0005`, `0007`, `0011` one run each, then `0012`/`0013`/`0014` as one run -- `MitateDB-api/docs/cloud-run-cloud-sql.md:3431`.
- `0016` then runs alone at step 7a, and `0017` alone at step 7b, through the same subcommand -- `MitateDB-api/docs/cloud-run-cloud-sql.md:4342`, `:4350`.
- `0012`, `0013` and `0014` all `CREATE OR REPLACE` the same function in that order, and `0013` and `0014` both name the role `0005` creates -- `MitateDB-api/migrations/0014_role_connection_limits_rollout.sql`.
- re-applying `0007`/`0012` is idempotent but not value-neutral, so the runbook records the writer-role timeouts, the `audit_writer_roles` row and the current `CONNECTION LIMIT`s first -- `MitateDB-api/docs/cloud-run-cloud-sql.md` section 10.
- it restores the two timeouts and that row, while the `CONNECTION LIMIT`s are recorded only and never restored, since `0012` sets each role it names to its own value -- `MitateDB-api/docs/cloud-run-cloud-sql.md` section 10.
- Section 10.10 requires the ADMIN OPTION prerequisite the `ALTER ROLE` statements in `0007`/`0012`/`0013`/`0014` share, and names the single `GRANT` that repairs a cluster lacking it -- `MitateDB-api/docs/cloud-run-cloud-sql.md`.

#### Evidence

- filename validation, the psql-variable table (quoted-form-only reference, no bare name), DSN-via-environment and redaction are covered by the 75 tests of `MitateDB-api/tests/test_ops_apply_platform_migration.py`.
- drift-then-restore holds for 5 of the 8 accepted files (0005/0007/0011/0012/0013) -- `MitateDB-api/tests/test_ops_apply_platform_migration.py::test_apply_platform_migration_0005_restores_a_manually_drifted_public_grant`.
- drift-then-restore -- `MitateDB-api/tests/test_ops_apply_platform_migration.py::test_apply_platform_migration_0007_restores_a_manually_drifted_role_setting`.
- drift-then-restore -- `MitateDB-api/tests/test_ops_apply_platform_migration.py::test_apply_platform_migration_0011_restores_a_manually_drifted_constraint`, `::test_apply_platform_migration_0012_restores_a_manually_drifted_function_body`.
- drift-then-restore -- `MitateDB-api/tests/test_ops_apply_platform_migration.py::test_apply_platform_migration_0013_restores_manually_drifted_settings_and_function_body`.
- the accepted set -- `MitateDB-api/tests/test_ops_apply_platform_migration.py::test_apply_platform_migration_accepted_filenames_are_pinned_and_exist_without_app_id`.
- `0016` in the accepted set, as a platform migration and never an upgrade script -- `MitateDB-api/tests/test_r113_multi_process_wiring.py::test_ops_accepts_0016_as_a_known_platform_migration`, `::test_0016_is_a_platform_single_shot_migration_never_an_upgrade_script`.
- `0016` runs alone, outside the `0012`/`0013`/`0014` run -- `MitateDB-api/tests/test_platform_migration_reapply.py::test_reapply_platform_migration_solo_and_run_groups_partition_the_real_constant`.
- the migration run -- `MitateDB-api/tests/test_ops_apply_platform_migration.py::test_apply_platform_migration_out_of_order_run_is_rejected`, `::test_apply_platform_migration_duplicate_filename_in_run_is_rejected`.
- the migration run -- `MitateDB-api/tests/test_ops_apply_platform_migration.py::test_apply_platform_migration_solo_0012_is_rejected_with_the_confirmed_closure_message`, `::test_apply_platform_migration_0012_0014_without_0013_is_rejected`.
- the migration run -- `MitateDB-api/tests/test_ops_apply_platform_migration.py::test_platform_migration_target_map_contains_the_4_known_targets`, `::test_platform_migration_superseded_by_equals_the_target_map_folded_to_file_level`.
- the migration run -- `MitateDB-api/tests/test_ops_apply_platform_migration.py::test_apply_platform_migration_run_never_starts_a_file_the_operator_did_not_list`, `::test_apply_platform_migration_never_starts_a_files_own_successor_the_operator_omitted`.
- the migration run -- `MitateDB-api/tests/test_ops_apply_platform_migration.py::test_apply_platform_migration_run_stops_at_the_failing_file_with_the_confirmed_t3_message`, `::test_apply_platform_migration_0014_preserves_0013_statement_timeout_on_provisioned_roles`.
- the migration run -- `MitateDB-api/tests/test_ops_apply_platform_migration.py::test_apply_platform_migration_accepts_0014_via_the_subcommand`, `::test_apply_platform_migration_0014_is_transactional_and_rolls_back_on_permission_failure`.
- the migration run -- `MitateDB-api/tests/test_ops_apply_platform_migration.py::test_apply_platform_migration_0014_survives_a_registry_role_dropped_before_it_runs`.
- run order, on real PostgreSQL -- `MitateDB-api/tests/test_ops_apply_platform_migration.py::test_apply_platform_migration_run_of_0012_0013_0014_leaves_the_newest_values`, `::test_apply_platform_migration_run_reversed_order_leaves_the_oldest_values`.
- the help text, section-heading comment and docstring name the same runbook section -- `MitateDB-api/tests/test_ops_help_text.py`.
- re-application with drift-then-restore is idempotent from every starting prefix, also covering 0005/0013/0014, with `0016` re-applied undrifted -- `MitateDB-api/tests/test_platform_migration_reapply.py::test_0007_0011_0012_reapplication_is_idempotent_from_every_starting_prefix`.

#### Status

- **Production evidence is `absent`**: section 10 has never been run against production, and neither `0014_role_connection_limits_rollout.sql`, `0016`, `0017`, the `0004` stages R-54 adds, nor the run/closure behavior R-57 adds is applied there; every value above was measured on a throwaway cluster.
- **`0014`'s header is true for one process, not for two**: it overwrites `0012`'s own statement that `mitatedbsvc_auditreader` is deliberately left untouched, rather than erasing it -- `MitateDB-api/migrations/0014_role_connection_limits_rollout.sql`.
- **Each reviewed subject stays a draft until section 10.8's own row names that same version for it**: section 10.8 is the single place that state is read from, and a row naming an earlier version counts as no record at all.
- **Section 10.8 names 10.6 / 10.7 / 10.10 accepted at versions 7 / 7 / 12** (requester, 2026-10-01; design `docs/design/MITATEDB_APPLICATION_SERIALIZATION_V0_1.md` section 11.2), so Gate-0 readiness rests on the 10 items alone -- `MitateDB-api/docs/cloud-run-cloud-sql.md:3051-3053`.
- **Every `apply-platform-migration` test targets a throwaway PostgreSQL cluster only** (`MITATEDB_TEST_ADMIN_DSN`).
- **A stray `0012` applied alone after `0013`** drops the setting for FUTURE applications only, and, now that `0014_role_connection_limits_rollout.sql` replaces that same function last, additionally lowers every EXISTING role's `CONNECTION LIMIT` back to `0012`'s values.
- **Either stray is corrected only by re-applying the set in its own order, ending at `apply-platform-migration 0014`** -- never by `0013` alone, which would leave the next application's roles at 36.

### Common

#### Control

- —

#### Evidence

- CCR-13's destructive-confirmation-before-precondition ordering is additionally covered by C-18, on all four adapters -- `conformance-tests/test_c18_revision_precondition_semantics.py`.
- Q-1's declare-and-echo protocol (contract 1.2.0) has its own condition C-06, executable on `r2db-api`, `r2db-api-http`, `MitateDB-api` and `MitateDB-api-http` -- `conformance-tests/test_c06_destructive_confirmation.py`.
- the C-06 vectors -- `conformance-tests/test_c06_destructive_confirmation.py::test_c06_v1_unconfirmed_destructive_delete_denied`, `::test_c06_v3_confirmation_exact_match_required`, `::test_c06_v4_phrase_is_deterministic_and_requester_independent`, `::test_c06_v5_echo_executes`.
- the C-06 vectors -- `conformance-tests/test_c06_destructive_confirmation.py::test_c06_v6_drop_entity_fingerprint_invalidation`, `::test_c06_v7_control_credential_gate`, `::test_c06_v8_no_payload_echo_in_declarations`.
- C-28, on all six adapters: the turn's predicate `delete` is refused unconfirmed, executes once the client presents the declared phrase, and removes exactly the matched row (exact-match enforcement itself is C-06's) -- `conformance-tests/test_c28_baseline_turn.py::test_c28_baseline_turn`.

#### Status

- **No cited evidence for the common destructive-misuse coverage beyond C-06 and C-18**: no test is named for this block's blanket destructive-misuse claim; version 2.25's uncited wording is in the history file.
- the baseline (<1.2.0) branch is retained, deliberately unremoved, as a disclosed and currently-unexercised acceptance floor for any future <1.2.0 peer (`conformance-tests/CONDITIONS.md` C-06 row).

## SI-10 Error/Information Non-Disclosure

[history](CONTROL_MAPPING_HISTORY.md#si-10)

### r2db-api

#### Control

- `FoundationError` emits a safe problem shape, and no internal exception is serialized -- `r2db-api/src/r2db_api/errors.py`.
- `r2db-api/src/r2db_api/http.py` renders every `FoundationError` as `application/problem+json`.
- `_generic_service_unavailable` collapses any uncaught exception, from Starlette routing or a `PostgresCell`/psycopg failure, to a generic `SERVICE_UNAVAILABLE` with a static message -- `r2db-api/src/r2db_api/http.py:348`.
- that collapse deliberately discards the real exception rather than interpolating or logging it at this layer -- `r2db-api/src/r2db_api/http.py:348`.
- `r2db-api/src/r2db_api/postgres.py` itself maps `psycopg.Error` to that same generic denial rather than letting a driver error or message reach the caller.
- exactly one fail-fast message reaches a client under the Q4 design, and it carries no configuration state -- `docs/design/Q4_DB_SIDE_SINGLE_TRUTH_V1.md` §3.8, `r2db-api/src/r2db_api/postgres.py:1026`.
- F-1..F-11/F-3c/F-13 are startup-time output only, so they are never copied onto a readiness or health surface, though they may quote a declared value, a role name or a DSN env-var NAME -- `r2db-api/src/r2db_api/platform_declarations.py`.
- **F-12** alone is raised at cell-open time and becomes an API response, `PostgresCell.verify_platform_upgrades_applied` re-raising `platform_upgrades.PlatformUpgradeError` as a `FoundationError` -- `r2db-api/src/r2db_api/postgres.py:1026`.
- `platform_upgrades._f12_message` is built from the missing upgrade numbers, the application id and the `ops upgrade-applications` command only -- no DSN, credential or hostname -- `r2db-api/src/r2db_api/platform_upgrades.py:167`.
- the out-of-band `ops` CLI's `cmd_verify_declarations` never prints a raw exception string on a connection or database failure, only the caught exception's own type name plus a fixed message -- `r2db-api/src/r2db_api/ops.py:1317`.
- the CLI's top-level `main()` applies the same rule -- `r2db-api/src/r2db_api/ops.py:2428`.
- `cmd_upgrade_applications`'s own `failure_detail` has every DSN element redacted via `_redact_connection_values` -- `r2db-api/src/r2db_api/ops.py:1659`.
- the redacted elements are `user`/`password`/`host`/`hostaddr`/`port`/`dbname`, with `host`/`hostaddr`/`port` split on `,` first for a multi-host DSN -- `r2db-api/src/r2db_api/ops.py:1563`.
- that redaction is one regular expression, longest value first, in a single pass, so a shorter value that is a literal prefix of a longer one cannot leave the longer value's own tail exposed -- `r2db-api/src/r2db_api/ops.py:1563`.
- every psql subprocess invocation passes its connection parameters through libpq's own environment variables via `_psql_connection_env`, never on argv -- `r2db-api/src/r2db_api/ops.py:1514`.
- the child's environment is built by first stripping every parent `PG*` variable, then setting only the 33 libpq (PostgreSQL 16) keys with a documented environment-variable form -- `r2db-api/src/r2db_api/ops.py:1514`.
- a DSN key outside that set ends the run via `_die`, naming the key but never its value -- `r2db-api/src/r2db_api/ops.py:1514`.
- the run is fail-closed on a connection-setting variable the parent process still carries but the DSN itself never overrides, including `PGSERVICEFILE`/`PGSYSCONFDIR` -- `r2db-api/src/r2db_api/ops.py:1514`.
- `_die` names that variable, never its value, rather than let the psql child silently inherit a setting from this process' own environment -- `r2db-api/src/r2db_api/ops.py:1514`.
- `_require_psql_16_or_newer` precedes every psql invocation, reading `psql --version` and `_die`ing with fixed text on an unstartable binary, a major version below 16, or unparseable output -- `r2db-api/src/r2db_api/ops.py:1478`.

#### Evidence

- malformed, deep and cyclic input produce structured safe failures -- `r2db-api/tests/test_http.py`.
- audit records carry no secret -- `r2db-api/tests/test_http.py`.
- the generic collapse and the `psycopg.Error` mapping -- `test_postgres.py`.
- F-12, the ledger scan -- `r2db-api/tests/test_platform_upgrade_ledger_scan.py::test_f12_message_matches_design_section_3_8_verbatim`, `r2db-api/tests/test_application_audit.py::test_build_app_h1_logs_the_f12_message_verbatim_at_cell_open_time`.
- F-12, the ledger scan -- `r2db-api/tests/test_postgres.py::test_verify_platform_upgrades_applied_raises_service_unavailable_when_a_number_is_missing`, `::test_verify_platform_upgrades_applied_raises_when_the_ledger_table_is_entirely_absent`.
- no raw exception text -- `r2db-api/tests/test_ops_verify_declarations.py::test_verify_declarations_connect_failure_never_prints_the_raw_exception_text`, `::test_main_psycopg_error_handler_never_prints_the_raw_exception_text`, `::test_main_catches_non_psycopg_exceptions_without_a_traceback`.
- the psql invocation -- `r2db-api/tests/test_ops_upgrade.py::test_run_upgrade_script_passes_connection_params_via_env_never_argv`, `::test_cmd_upgrade_applications_redacts_connection_values_from_a_failed_psql_output`, `::test_redact_connection_values_leaves_unrelated_text_untouched`.
- the psql invocation -- `r2db-api/tests/test_ops_upgrade.py::test_redact_connection_values_handles_prefix_overlap_and_multi_host_dsn`, `::test_psql_connection_env_rejects_a_dsn_key_with_no_libpq_env_var_form`, `::test_psql_connection_env_accepts_new_allow_listed_keys`.
- the psql invocation -- `r2db-api/tests/test_ops_upgrade.py::test_psql_connection_env_strips_parent_pg_star_vars`, `::test_psql_connection_env_rejects_a_parent_connection_var_the_dsn_does_not_override`, `::test_psql_connection_env_accepts_when_dsn_overrides_the_parent_connection_var`.
- the psql invocation -- `r2db-api/tests/test_ops_upgrade.py::test_psql_connection_env_rejects_a_parent_pgservicefile_the_dsn_can_never_override`, `::test_psql_connection_env_rejects_a_parent_pgsysconfdir_the_dsn_can_never_override`.
- the psql invocation -- `r2db-api/tests/test_ops_upgrade.py::test_require_psql_16_or_newer_rejects_an_older_or_unparseable_version`, `::test_require_psql_16_or_newer_rejects_unparseable_output`, `::test_require_psql_16_or_newer_accepts_16`.
- the psql invocation -- `r2db-api/tests/test_ops_upgrade.py::test_require_psql_16_or_newer_rejects_when_the_binary_is_not_found`, `::test_run_upgrade_script_calls_the_psql_version_gate_first`.

#### Status

- production log/observability handling of the discarded exception is not yet defined or evidenced.

### MitateDB-api

#### Control

- `http.py` renders every application-plane `FoundationError` as `application/problem+json` -- `MitateDB-api/src/mitatedb_api/http.py:122`.
- `_generic_service_unavailable` collapses any uncaught exception, from routing or a `backend_postgres`/psycopg failure, to a generic `SERVICE_UNAVAILABLE` with a static message -- `MitateDB-api/src/mitatedb_api/http.py:147`.
- that collapse discards the real exception rather than logging or interpolating it here -- `MitateDB-api/src/mitatedb_api/http.py:147`.
- `control_http.py` reuses the same generic-collapse pattern with its own error-classification table -- `MitateDB-api/src/mitatedb_api/control_http.py:151`.
- the problem-body builder replaces every other error's message with a fixed generic string, narrowing the Q4 carve-out by TYPE rather than by code -- `MitateDB-api/src/mitatedb_api/http.py:122`.
- the sole exception is `isinstance(exc, PlatformUpgradePending)`, a dedicated subclass rather than the classified `SERVICE_UNAVAILABLE` code every other storage-configuration failure maps to -- `MitateDB-api/src/mitatedb_api/errors.py:222`.
- that subclass keeps the carve-out from silently widening to a future error site -- `MitateDB-api/src/mitatedb_api/errors.py:222`.
- the surfaced text is the same fixed **F-12** message -- the missing upgrade numbers plus the `ops upgrade-applications` command, nothing else -- `MitateDB-api/src/mitatedb_api/platform_upgrades.py`.
- the out-of-band `ops` CLI's `cmd_verify_declarations` never prints a raw exception string on a connection or database failure, only the type name plus a fixed message -- `MitateDB-api/src/mitatedb_api/ops.py:1624`.
- the CLI's top-level `main()` applies the same rule -- `MitateDB-api/src/mitatedb_api/ops.py:3583`.
- `_upgrade_one_application` and `_run_deprovision_script` redact every DSN element from their own `failure_detail` and `_die` message via `_redact_connection_values` -- `MitateDB-api/src/mitatedb_api/ops.py:1802`.
- the redacted elements are `user`/`password`/`host`/`hostaddr`/`port`/`dbname`, with `host`/`hostaddr`/`port` split on `,` first for a multi-host DSN -- `MitateDB-api/src/mitatedb_api/ops.py:700`.
- that redaction is one regular expression, longest value first, in a single pass, so a shorter value that is a literal prefix of a longer one cannot leave the longer value's tail exposed -- `MitateDB-api/src/mitatedb_api/ops.py:700`.
- every psql subprocess invocation passes its connection parameters through libpq's own environment variables via `_psql_connection_env`, never on argv -- `MitateDB-api/src/mitatedb_api/ops.py:651`.
- the child's environment is built by first stripping every parent `PG*` variable, then setting only the 33 libpq (PostgreSQL 16) keys with a documented environment-variable form -- `MitateDB-api/src/mitatedb_api/ops.py:651`.
- a DSN key outside that set ends the run via `_die`, naming the key but never its value -- `MitateDB-api/src/mitatedb_api/ops.py:651`.
- the run is fail-closed on a connection-setting variable the parent still carries but the DSN never overrides, including `PGSERVICEFILE`/`PGSYSCONFDIR` -- `MitateDB-api/src/mitatedb_api/ops.py:651`.
- `_die` names that variable, never its value, rather than let the psql child silently inherit a setting from this process' own environment -- `MitateDB-api/src/mitatedb_api/ops.py:651`.
- `_require_psql_16_or_newer` precedes every psql subprocess invocation and `_die`s with fixed text on an unstartable binary, a major version below 16, or unparseable output -- `MitateDB-api/src/mitatedb_api/ops.py:615`.
- **`ops inventory`** never formats an exception's own text into its output: every failure path returns a fixed judgment word, a closed-vocabulary reason word, or `match`/`mismatch`, never `str(exc)` -- `MitateDB-api/src/mitatedb_api/ops.py:3093`.
- a connection failure before any item can be read propagates uncaught to `main`'s own top-level handler, which prints a type name and fixed text only -- `MitateDB-api/src/mitatedb_api/ops.py:3583`.
- item (2)'s declaration read distinguishes an ABSENT declaration (confirmed plus remediation-required) from a PRESENT but hand-corrupted one (blocked with the fixed reason `declaration-invalid`) -- `MitateDB-api/src/mitatedb_api/ops.py:2338`.
- it never treats a corrupt value as equivalent to an absent one -- `MitateDB-api/src/mitatedb_api/ops.py:2338`.
- item (4)'s credential-registry projection is an explicit column allow-list (`role`/`enabled`/`revoked`/`must_rotate`), so `credential_id` and `digest` are never in the SELECT list -- `MitateDB-api/src/mitatedb_api/ops.py:2435`.
- item (4) reports per-state counts (`enabled`/`revoked`/`must_rotate`) rather than a total alone -- `MitateDB-api/src/mitatedb_api/ops.py:2435`.
- item (1) emits only the `match`/`mismatch`/`unknown` comparison result, never the Cloud SQL connection name or the DSN's own unix-socket path -- `MitateDB-api/src/mitatedb_api/ops.py:2283`.
- item (1) carries its own `judgment` (`match` to `confirmed`, `mismatch` to `blocked`, `unknown` to `unknown`), and `_inventory_exit_code` reads every item's `judgment` uniformly -- `MitateDB-api/src/mitatedb_api/ops.py:2776`.
- `_INVENTORY_TOP_LEVEL_KEYS` pins the JSON output's top-level and per-item key sets, with no `ready` key and no key for item (5) -- `MitateDB-api/src/mitatedb_api/ops.py:2174`.
- the pinned `unjudged_items` list names Gate-0's overall readiness and item (5)/item (6)'s own declared half as runbook-level judgments this DB-layer subcommand never publishes -- `MitateDB-api/src/mitatedb_api/ops.py:2187`.
- `ops inventory` closes the judgment, comparison, reason and part vocabularies alike -- `MitateDB-api/src/mitatedb_api/ops.py:2174`.
- `--concurrency`, `--thread-limit` and the process ceiling and total arguments accept only a positive integer, 0 refused -- `MitateDB-api/src/mitatedb_api/ops.py:2192`.
- `--reserved-connections` and `--data-process-count-old-basis` accept a non-negative integer, 0 meaning no reserve or no old-basis process, only a negative value refused -- `MitateDB-api/src/mitatedb_api/ops.py:2211`.
- both forms are a usage error, in argparse's own fixed templated message, before any connection opens -- `MitateDB-api/src/mitatedb_api/ops.py:3051`.

#### Evidence

- problem responses -- `test_problem_response_never_leaks_the_underlying_exception_message`, `test_authorization_state_unavailable_is_reported`.
- the control-plane problem response, exercised end to end with a raw `RuntimeError` carrying a secret-shaped marker injected into the authentication path -- `test_control_problem_response_never_leaks_the_underlying_exception_message`.
- F-12 -- `test_f12_message_matches_design_section_3_8_verbatim`, `test_build_app_h1_serves_every_application_and_refuses_only_the_one_with_a_pending_upgrade`.
- `ops inventory` output -- `MitateDB-api/tests/test_ops_inventory.py::test_inventory_success_route_never_leaks_user_or_password`, `::test_inventory_success_route_never_leaks_dbname`, `::test_inventory_connect_failure_host_never_leaks`, `::test_inventory_connect_failure_role_never_leaks`.
- `ops inventory` output -- `MitateDB-api/tests/test_ops_inventory.py::test_inventory_connect_failure_database_never_leaks`, `::test_inventory_dsn_parse_failure_never_leaks`, `::test_inventory_post_connect_psycopg_exception_never_leaks`.
- `ops inventory` output -- `MitateDB-api/tests/test_ops_inventory.py::test_inventory_non_psycopg_exception_is_caught_at_the_top_level_without_a_traceback`, `::test_inventory_credentials_column_allowlist_excludes_secrets`, `::test_inventory_credentials_cursor_description_matches_the_allowlist`.
- `ops inventory` output -- `MitateDB-api/tests/test_ops_inventory.py::test_inventory_credentials_query_never_selects_star_or_secret_columns`, `::test_inventory_credentials_permission_error_is_unknown`, `::test_inventory_credentials_per_state_counts`.
- `ops inventory` output -- `MitateDB-api/tests/test_ops_inventory.py::test_inventory_credentials_never_output_credential_id_or_digest`, `::test_inventory_declarations_missing_row_is_confirmed_with_remediation`, `::test_inventory_declarations_shape_violation_is_blocked`.
- `ops inventory` output -- `MitateDB-api/tests/test_ops_inventory.py::test_inventory_declarations_connection_failure_is_unknown`, `::test_inventory_declarations_f15_missing_only_is_confirmed_with_remediation`, `::test_inventory_reason_vocabulary_is_pinned`.
- `ops inventory` output -- `MitateDB-api/tests/test_ops_inventory.py::test_inventory_numeric_arguments_reject_zero_and_negative`, `::test_inventory_connection_comparison_reports_a_mismatch`, `::test_inventory_connection_comparison_matches_the_real_socket_path`.
- `ops inventory` output -- `MitateDB-api/tests/test_ops_inventory.py::test_inventory_connection_comparison_tcp_dsn_is_unknown`, `::test_inventory_connection_output_never_includes_the_socket_path_or_name`, `::test_inventory_does_not_accept_a_dsn_argument`.
- `ops inventory` output -- `MitateDB-api/tests/test_ops_inventory.py::test_inventory_writes_nothing_but_stdout`, `::test_inventory_never_calls_psycopg_connect_outside_its_own_factory`, `::test_inventory_top_level_and_item_keys_are_pinned`, `::test_inventory_judgment_vocabulary_is_closed`.
- `ops inventory` output -- `MitateDB-api/tests/test_ops_inventory.py::test_inventory_never_reports_an_overall_ready_key`, `::test_inventory_exit_code_is_2_when_any_item_is_not_confirmed`, `::test_inventory_exit_code_is_0_when_every_judged_item_is_confirmed`.
- `ops inventory` output -- `MitateDB-api/tests/test_ops_inventory.py::test_inventory_connection_judgment_drives_the_exit_code`, `::test_inventory_tool_failure_exit_code_is_1_with_fixed_text_only`, `::test_inventory_reports_every_db_layer_item_with_a_judgment`.
- `ops inventory` output -- `MitateDB-api/tests/test_ops_inventory.py::test_inventory_migrations_r47_pre_fix_application_is_blocked_with_a_fixed_reason`.
- `ops inventory` output -- `MitateDB-api/tests/test_ops_inventory.py::test_inventory_old_basis_accepts_zero_but_rejects_negative`.
- no raw exception text -- `MitateDB-api/tests/test_ops_verify_declarations.py::test_verify_declarations_connect_failure_never_prints_the_raw_exception_text`, `::test_main_psycopg_error_handler_never_prints_the_raw_exception_text`, `::test_main_catches_non_psycopg_exceptions_without_a_traceback`.
- the psql invocation -- `MitateDB-api/tests/test_ops_upgrade.py::test_run_upgrade_script_passes_connection_params_via_env_never_argv`, `::test_run_deprovision_script_passes_connection_params_via_env_never_argv`, `::test_run_upgrade_script_redacts_connection_values_from_a_failed_psql_output`.
- the psql invocation -- `MitateDB-api/tests/test_ops_upgrade.py::test_run_deprovision_script_redacts_connection_values_before_dying`, `::test_redact_connection_values_leaves_unrelated_text_untouched`, `::test_upgrade_one_application_redacts_connection_values_on_connect_failure`.
- the psql invocation -- `MitateDB-api/tests/test_ops_upgrade.py::test_redact_connection_values_handles_prefix_overlap_and_multi_host_dsn`, `::test_psql_connection_env_rejects_a_dsn_key_with_no_libpq_env_var_form`, `::test_psql_connection_env_accepts_new_allow_listed_keys`.
- the psql invocation -- `MitateDB-api/tests/test_ops_upgrade.py::test_psql_connection_env_strips_parent_pg_star_vars`, `::test_psql_connection_env_rejects_a_parent_connection_var_the_dsn_does_not_override`, `::test_psql_connection_env_accepts_when_dsn_overrides_the_parent_connection_var`.
- the psql invocation -- `MitateDB-api/tests/test_ops_upgrade.py::test_psql_connection_env_rejects_a_parent_pgservicefile_the_dsn_can_never_override`, `::test_psql_connection_env_rejects_a_parent_pgsysconfdir_the_dsn_can_never_override`.
- the psql invocation -- `MitateDB-api/tests/test_ops_upgrade.py::test_require_psql_16_or_newer_rejects_an_older_or_unparseable_version`, `::test_require_psql_16_or_newer_rejects_unparseable_output`, `::test_require_psql_16_or_newer_accepts_16`.
- the psql invocation -- `MitateDB-api/tests/test_ops_upgrade.py::test_require_psql_16_or_newer_rejects_when_the_binary_is_not_found`, `::test_run_upgrade_script_calls_the_psql_version_gate_first`, `::test_run_deprovision_script_calls_the_psql_version_gate_first`.

#### Status

- **Disclosed gap**: production log/observability handling of the discarded exception is not yet defined or evidenced for either plane.
- **Intended operational visibility, not a disclosure gap**: `list_credentials` is readable by the strictly weaker `audit` role (SI-02/SI-06), so a distributable, ceremony-issued `audit` credential can enumerate `must_rotate`/`enabled`/`revoked` state for every control credential, not only its own.
- That is deliberate: `CredentialsResult` never returns secrets or verifiers regardless of role, and the point of a weaker distributable role is observing rotation state without being able to change anything.
- **A refusing cell refuses at its scope's entry**: with an upgrade pending, a defect checked inside the scope (identifiers, vocabulary, declarations) answers 503, not `VALIDATION_FAILED`; HTTP body-shape checks still answer 400 -- `MitateDB-api/src/mitatedb_api/backend_postgres.py:481-482`.

### Common

#### Control

- C-30 cursor refusal details -- an unusable cursor is refused with only request_schema/page/cursor, whether malformed, foreign, or bound to a stale where/order_by (`r2db-api/src/r2db_api/paging.py`, `MitateDB-api/src/mitatedb_api/cell.py:2188`).

#### Evidence

- C-28, on all six adapters: an enum refusal names the request-body position, never the rejected value or a declared member, with details keys inside the contract vocabulary -- `conformance-tests/test_c28_baseline_turn.py::test_c28_baseline_turn`.
- C-29: each plug serves a catalog byte-identical to the packaged one; socket plugs serve it at the declared URL -- `conformance-tests/test_c29_operation_catalog_url.py::test_c29_served_body_matches_the_packaged_catalog`, `::test_c29_operation_catalog_url_is_really_dialable_on_socket_plugs`.
- An undecodable cursor and one bound to a different Application, entity, where or order_by all produce the identical 2-key denial: `test_c30_keyset_paging.py::test_c30_cursor_refusal_details`.
- r2db pins a wrong-count/wrong-type cursor token as the same denial: `r2db-api/tests/test_foundation.py::test_cursor_rejects_a_tampered_token_with_the_wrong_value_count_or_type`.
- MitateDB pins the same: `MitateDB-api/tests/test_http.py::test_tampered_page_cursor_count_and_type_and_domain_mismatches_are_validation_failed`.
- C-31 (select/where), on all six adapters: an undeclared field name is refused as request_schema naming the position -- `conformance-tests/test_c31_undeclared_field_refusal.py::test_c31_select_names_the_undeclared_entrys_index`, `::test_c31_where_names_the_undeclared_predicates_field`.
- C-31 (order_by/values), on all six adapters: an undeclared field name is refused as request_schema naming the position -- `conformance-tests/test_c31_undeclared_field_refusal.py::test_c31_order_by_names_the_undeclared_entrys_field`, `::test_c31_values_names_the_undeclared_keys_own_name`.

#### Status

- **No cited evidence for the common error-probing coverage**: no test is named for this block's blanket error-probing claim; version 2.25's uncited wording is in the history file.
- The count/type-mismatch causes above are not driven through the port (a cursor is contractually opaque, so the conformance suite cannot manufacture a tampered token); the port-only causes are malformed, cross-Application, cross-entity and where/order_by mismatch.
- A page cursor is a recoverable encoding of a row's ordering values, so, as audit.forbidden_fields excludes row_value, no audit event field carries it; both peers' event field sets are fixed, so no further check is added.

## SI-11 Atomic Integrity

[history](CONTROL_MAPPING_HISTORY.md#si-11)

### r2db-api

#### Control

- `ApplicationCell.transact` snapshots and restores on failure -- `r2db-api/src/r2db_api/structured.py:997`.
- `r2db-api/src/r2db_api/postgres.py`'s `PostgresCell.transact` maps one HTTP request to one real PostgreSQL transaction (design D-5).
- every operation in a batch runs inside a single `conn.transaction()` block -- `r2db-api/src/r2db_api/postgres.py:1586`.
- `PostgresCell.transact` rolls the whole batch back via PostgreSQL itself on any exception, including a `FoundationError` raised by a later operation in the batch, rather than an in-memory snapshot -- `r2db-api/src/r2db_api/postgres.py:1586`.
- **CCR-13** additionally makes an `expected_revision` precondition part of the same atomic unit (`docs/design/R2DB_CCR13_STORAGE_V1.md` R-4) -- `r2db-api/src/r2db_api/postgres_sql.py:138`.
- the predicate and the revision comparison are folded into one `WHERE` clause of the single `UPDATE`/`DELETE` statement (`_r2db_revision::text = $expected`) -- `r2db-api/src/r2db_api/postgres_sql.py:138`.
- that is never a separate read followed by a conditional write, so the compare-and-swap cannot race with a concurrent mutation of the same row -- `r2db-api/src/r2db_api/postgres_sql.py:138`.
- `PostgresCell.apply_schema` takes the application-wide `pg_advisory_xact_lock(761761763)` before `_load_catalog`, so a `plan` is checked against the revision read under that lock -- `r2db-api/src/r2db_api/postgres.py:2157`, `:2166`.
- its lock order is per-key -> lookup -> schema lock -> count lock -> `_load_catalog`, and a replay answers from its record before the schema lock -- `r2db-api/src/r2db_api/postgres.py:1405`.

#### Evidence

- atomic rollback with the explicit destructive operation -- `test_atomic_rollback_and_explicit_destructive_operation`.
- the transaction mapping is exercised against a real local PostgreSQL 16 cluster -- `r2db-api/tests/test_postgres.py`.
- the `plan` window, two cells on one application -- `r2db-api/tests/test_r102_schema_windows.py::test_plan_window_plan_is_checked_against_the_revision_inside_the_ddl_serialization`.
- the schema lock -- `r2db-api/tests/test_schema_serialization_lock.py::test_a_dry_run_reads_the_revision_under_the_schema_lock`, `::test_replay_of_a_recorded_schema_operation_answers_while_another_schema_operation_holds_the_lock`.
- the schema lock -- `r2db-api/tests/test_schema_serialization_lock.py::test_a_keyed_schema_operation_waiting_for_the_schema_lock_does_not_block_a_keyed_data_operation`, `::test_the_advisory_lock_ids_of_the_four_serialization_points_are_distinct`.

#### Status

- no production evidence.
- r2db's own `cross_entity_mutation` remains `unavailable` (P35-D1, `docs/design/PHASE35_CROSS_ENTITY_AND_CONTRACT_130_V1.md` §0) -- no cross-entity atomic unit exists on this peer to evidence.
- **r2db's DML validation and an `alter_field` commit are not serialized**: a data write validated against the registry can commit after a concurrent `alter_field` changed the constraint, leaving a row against the declaration (structural, not reproduced; ledger item R-120, still open).

### MitateDB-api

#### Control

- `ApplicationCell.transact` uses one local transaction with rollback on a rejected operation -- `MitateDB-api/src/mitatedb_api/cell.py:2580`.
- `transact()` is a two-pass choke for the cross-entity atomic unit (design §2 R-1): pass 1 (`_plan_operation`, side-effect-free) validates the WHOLE unit before pass 2 executes any of it -- `MitateDB-api/src/mitatedb_api/cell.py:2403`.
- a later operation's validation failure therefore voids every earlier operation's effect too -- `MitateDB-api/src/mitatedb_api/cell.py:2403`.
- that choke is shared by both the single-entity and the cross-entity call path, with no second implementation -- `MitateDB-api/src/mitatedb_api/cell.py:2580`.
- rollback on a pass-2 failure is unconditional regardless of exception type -- `MitateDB-api/src/mitatedb_api/cell.py:2580`.
- `encode_value` rejects lone UTF-16 surrogates deterministically before execution on both backends, the same treatment as the pre-existing NUL-byte rejection -- `MitateDB-api/src/mitatedb_api/backend_postgres.py:1421`.
- pass 1 and pass 2 of one batch run under the shared entity locks of every entity it names, so an API schema operation on those entities waits for the batch -- `MitateDB-api/src/mitatedb_api/cell.py:2749`.

#### Evidence

- rollback and two passes -- `test_transaction_rolls_back`, `test_transact_two_pass_structure_zero_backend_calls_when_a_later_operation_fails_validation`.
- a lone surrogate value, and an unconditional rollback for a non-`FoundationError` raised mid-pass-2 -- `test_transact_lone_surrogate_value_is_deterministic_validation_failure_and_earlier_entity_unchanged`, `test_transact_rollback_is_unconditional_for_a_non_foundation_error_raised_mid_pass_2`.
- a table dropped at the pass 1 / pass 2 boundary (`begin()`) from a separate connection that takes no advisory lock -- `test_transact_pass_boundary_schema_change_window_yields_not_found_and_sibling_entity_unchanged`.
- the C-16 unit -- `test_c16_v1_two_entity_insert_commits_as_one_unit`, `test_c16_v2_invalid_operation_on_one_entity_voids_the_whole_unit`.
- an `alter_field` from another cell waits for a batch validated against the old constraint -- `MitateDB-api/tests/test_r102_cross_cell_windows.py::test_window3_data_write_validated_before_an_alter_is_not_committed_against_the_new_constraint`.

#### Status

- **Disclosed PostgreSQL-specific window**: a schema change made outside the API, on a connection that takes no advisory lock, can still land between the two passes; the Evidence above drives exactly that window.
- the MitateDB pair takes the C-16 PROVIDED branch while the r2db pair takes the documented ABSENT branch (SI-11's r2db-api cell above).

### Common

#### Control

- C-34 plan precondition -- a schema operation presenting a `plan` reads the revision it checks and runs its DDL under one application-wide lock (`r2db-api/src/r2db_api/postgres.py:2157`, `MitateDB-api/src/mitatedb_api/cell.py:1241`).

#### Evidence

- CCR-13's revision-precondition atomicity and semantics are additionally covered by C-18, on all four adapters -- `conformance-tests/test_c18_revision_precondition_semantics.py`.
- cross-entity atomic-unit agreement, declared against observed, with both entities voided together on a mixed-validity unit, is additionally covered by C-16 -- `conformance-tests/test_c16_cross_entity_atomicity.py`.
- V1 and V2 drive the two PROVIDED MitateDB adapters and V5's evidence-form check the two ABSENT r2db adapters -- `conformance-tests/test_c16_cross_entity_atomicity.py::test_c16_v5_unavailable_peers_take_their_declared_evidence_form`.
- C-28, on all six adapters: a dry run under the real send's idempotency key leaves no row, the real send presenting that plan commits one row, and a same-key resend adds none -- `conformance-tests/test_c28_baseline_turn.py::test_c28_baseline_turn`.
- C-34, on all six adapters: with a `plan`-presenting schema operation held after its revision read, a second one on another entity answers only after the first commits -- `conformance-tests/test_c34_concurrent_plan_precondition.py::test_c34_concurrent_schema_operation_keeps_plan_precondition`.

#### Status

- **No cited evidence for the common rollback/fault coverage beyond C-16 and C-18**: no test is named for this block's blanket rollback/fault claim; version 2.25's uncited wording is in the history file.

## SI-12 No Data-Service Bypass

[history](CONTROL_MAPPING_HISTORY.md#si-12)

### r2db-api

#### Control

- the structured package has no credential, connection or native-command response -- `r2db-api/src/r2db_api/structured.py`.
- topology denies privileged egress -- `r2db-api/src/r2db_api/topology.py`.
- two Q4 bookkeeping tables exist, neither reachable from an application-facing API (`docs/design/Q4_DB_SIDE_SINGLE_TRUTH_V1.md` D-2/D-3, §3.9, requester ruling U-2) -- `r2db-api/migrations/0008_platform_declarations_and_writer_timeouts.sql`.
- `r2dbsvc_registry.platform_declarations` (migration `0008`) lives in the platform database, which no application `runtime`/`developer` role ever connects to -- `r2db-api/migrations/0008_platform_declarations_and_writer_timeouts.sql`.
- both platform process roles (`r2dbsvc_api`, `r2dbsvc_controlplane`) hold `SELECT` only on it, and every write goes through the provision DSN -- `r2db-api/migrations/0008_platform_declarations_and_writer_timeouts.sql`.
- `public._r2db_platform_upgrades` (revised `0003` template, retrofit script `0009`) lives inside each application's own database and is OWNED by that application's developer role -- `r2db-api/migrations/0009_platform_upgrades_ledger_upgrade.sql`.
- that is the same scope `_r2db_schema_revision` already has, closed inside that one database -- `r2db-api/migrations/0003_provision_application.sql`.
- the `runtime` role is granted `SELECT` only on that table (requester ruling U-2), which is what the cell-open completeness check reads -- `r2db-api/migrations/0009_platform_upgrades_ledger_upgrade.sql`.
- the provision role holds `SELECT` plus schema `USAGE`, so `upgrade-status` can report without assuming the developer role -- `r2db-api/migrations/0009_platform_upgrades_ledger_upgrade.sql`.
- `structured.py`'s `_reject_reserved_prefix` refuses any `_`-prefixed identifier, so the table name is unreachable through the API at all -- `r2db-api/src/r2db_api/structured.py`.
- the bookkeeping row exposes no DB credential, no unbounded connection, no privileged private endpoint and no key that bypasses authorization -- `r2db-api/src/r2db_api/structured.py`.

#### Evidence

- the upgrade ledger -- `r2db-api/tests/test_postgres.py::test_runtime_role_can_select_but_not_write_the_ledger`, `::test_provision_role_can_read_the_ledger_after_the_script_ends`, `::test_ledger_table_has_no_row_level_security`.
- the upgrade ledger -- `r2db-api/tests/test_postgres.py::test_template_seeds_the_ledger_with_the_current_platform_upgrade_numbers`, `::test_0009_upgrades_a_legacy_application_to_match_a_freshly_provisioned_ledger`, `::test_backend_excludes_the_ledger_from_catalog_and_schema_objects_accounting`.
- the upgrade ledger -- `r2db-api/tests/test_postgres.py::test_missing_rls_view_stays_empty_on_both_a_new_and_an_upgraded_application`.
- migration `0008` -- `r2db-api/tests/test_ops_declarations.py::test_migration_0008_grants_select_to_both_writer_roles_and_nothing_to_public`, `::test_migration_0008_seeds_window_default_but_not_surfaces`, `::test_migration_0008_key_check_constraint_is_named`.

#### Status

- **No cited evidence for the contract smoke test**: no test is named for this block's blanket contract-smoke claim; version 2.25's uncited wording is in the history file.
- Stated limit (design §3.9): the ledger is an operational record, not tamper-proof evidence -- inside the threat model's own "one application-facing defect" case its rows are as reachable as any other bookkeeping row in that same database.

### MitateDB-api

#### Control

- `cell.py`, `backend.py`, `backend_postgres.py` and `backend_sqlite.py` expose only the structured operation set, and no method returns a raw connection, DSN, or credential/verifier value -- `MitateDB-api/src/mitatedb_api/cell.py`.
- the single execution choke point `_execute` (R-2) is typed to reject any `str` statement with `TypeError` -- `MitateDB-api/src/mitatedb_api/backend_postgres.py:295`.
- `/control/v1`'s own responses never echo a DSN, pepper, or another credential's secret -- `MitateDB-api/src/mitatedb_api/control_http.py:139`.
- `list_credentials`/`list_applications` return only `credential_id`/`application_id`/`role`/`enabled`/`revoked` -- `MitateDB-api/src/mitatedb_api/control_plane.py:990`.
- `platform_declarations` (migration `0007`) sits in the platform database with `SELECT` for both service roles and writes only through `MITATEDB_PROVISION_DSN` -- `MitateDB-api/migrations/0007_platform_declarations.sql`.
- `_mdb_platform_upgrades` (revised `0003`, retrofit `0008`) sits in each application database, owned by that application's developer role and `SELECT`-only for the runtime role -- `MitateDB-api/migrations/0008_platform_upgrades_upgrade.sql`.
- that table is excluded from `schema_count()`'s accounting and never listed as an entity -- `MitateDB-api/src/mitatedb_api/backend_postgres.py`.
- `_`-prefixed identifiers are unreachable through the API here too -- `MitateDB-api/src/mitatedb_api/identifiers.py`.

#### Evidence

- no arbitrary SQL, real-PostgreSQL coverage shared with SI-04/SI-05 -- `test_no_arbitrary_sql_and_identifier_validation`, `test_postgres.py`.
- control capabilities -- `test_control_capabilities_result_matches_schema_exactly_and_declares_request_bytes`.
- ledger privileges -- `test_runtime_role_has_select_only_on_the_ledger`, `test_0007_grants_select_to_both_roles_and_nothing_to_public`.

#### Status

- Same stated limit as r2db-api: the ledger is an operational record, not tamper-proof evidence.

### Common

#### Control

- —

#### Evidence

- —

#### Status

- **No cited evidence for the common exposure/config review**: no test is named for this block's blanket exposure/config-review claim; version 2.25's uncited wording is in the history file.

## SI-13 Revocation/Disable Effectiveness

[history](CONTROL_MAPPING_HISTORY.md#si-13)

### r2db-api

#### Control

- `CredentialStore.assert_active` re-checks each operation -- `r2db-api/src/r2db_api/credential_store.py:443`.
- `DataService` checks application state on the same path -- `r2db-api/src/r2db_api/service.py`.
- **CCR-14** extends immediate revoke/disable effectiveness to control credentials (`docs/design/R2DB_CCR14_CONTROL_PLANE_V1.md` R-2/R-5/R-10/R-13) -- `r2db-api/src/r2db_api/credential_store.py:878`.
- `ControlCredentialStore`/`PostgresControlCredentialStore` use the same request-time, no-cache credential lookup the application plane uses -- `r2db-api/src/r2db_api/credential_store.py:880`.
- the row is resolved by the locator's `credential_id`, `compare_digest` against the stored verifier being the authoritative check and the verifier never the lookup key -- `r2db-api/src/r2db_api/credential_store.py:880`.
- a revoked or disabled control credential therefore stops authenticating on its very next request, with `authorization_propagation_bound_ms: 0` -- `r2db-api/src/r2db_api/control_plane.py:663`.
- an un-revoke of a control credential is never offered by any code path: `set_state(revoked=False)` is refused with `VALIDATION_FAILED` by both store implementations -- `r2db-api/src/r2db_api/credential_store.py:941`.
- that matches the pre-existing application-credential un-revoke refusal -- `r2db-api/src/r2db_api/credential_store.py:622`.
- the out-of-band `reset` ritual is the canonical recovery from a revoked control credential, never an un-revoke -- `r2db-api/src/r2db_api/ops.py:705`.
- the first-issued credential's own non-permanence (contract `bootstrap[5]`, "expires or requires rotation") is satisfied by a `must_rotate` gate rather than a time-based expiry -- `r2db-api/src/r2db_api/control_plane.py:1300`.
- that credential authorizes nothing but `GET /control/v1/capabilities` and self-rotate until one real rotation completes -- `r2db-api/src/r2db_api/control_plane.py:1310`.

#### Evidence

- fail-closed states -- `test_revoke_disable_and_unavailable_state_fail_closed`.
- `reset` is atomic: the old secret is `AUTH_REVOKED` at once, the new one live, Application data untouched -- `r2db-api/tests/test_control_plane_store.py::test_reset_revokes_all_and_issues_one_new_credential_atomically_and_touches_nothing_else`.
- un-revoke -- `r2db-api/tests/test_control_plane_store.py::test_control_credential_parity_un_revoke_refused_both_impls`, `::test_break_glass_never_offers_un_revoke`.
- a `must_rotate` lock -- `r2db-api/tests/test_control_plane_store.py::test_control_credential_locked_by_must_rotate_still_authenticates_and_rotate_clears_it`.

#### Status

- propagation bound remains deployment evidence.
- **Reversing a revocation is a permanent design refusal, not a gap**: it would make a durably-recorded revocation event false, which SI-13 itself would then have to call a propagation failure.

### MitateDB-api

#### Control

- `CredentialStore.assert_active` re-checks revocation and application state on every session operation -- `MitateDB-api/src/mitatedb_api/credential_store_postgres.py:548`.
- the same request-time, no-cache credential lookup applies to `control_auth.ControlCredentialStore` and `control_credential_store_postgres.PostgresControlCredentialStore` -- `MitateDB-api/src/mitatedb_api/control_auth.py`.
- the row is resolved by the locator's `credential_id`, with `compare_digest` against the stored verifier as the authoritative check (Phase 6 D-1) -- `MitateDB-api/src/mitatedb_api/control_credential_store_postgres.py`.
- `ControlPlaneService.control_capabilities` publishes `authorization_propagation_bound_ms: 0` -- `MitateDB-api/src/mitatedb_api/control_plane.py:1626`.
- a revoked or disabled control credential therefore stops authenticating on its very next call -- `MitateDB-api/src/mitatedb_api/control_auth.py`.
- un-revoke is refused, not merely absent: both `set_credential_state` and `set_control_credential_state` only ever set `revoked=True`, never `False` -- `MitateDB-api/src/mitatedb_api/control_plane.py:999`.
- `ControlPlaneService` has no method parameter that could request it -- `MitateDB-api/src/mitatedb_api/control_plane.py:1014`.

#### Evidence

- fail-closed states -- `test_disable_revoke_and_unavailable_state_fail_closed`.
- control capabilities -- `test_control_plane_service.py::test_control_capabilities_result_matches_schema_exactly_and_declares_request_bytes`.
- terminality -- `MitateDB-api/tests/test_control_credentials.py::test_revoke_is_terminal_enable_cannot_resurrect_it`, `::test_disable_then_enable_restores_authentication`.
- a real reset ceremony -- `MitateDB-api/tests/test_ops.py::test_reset_with_the_echoed_phrase_revokes_everything_and_mints_one_new_credential`.
- C-13 exercises the real `enable(True)`-after-`revoke` sequence as a `must_deny` case, not a `structurally_absent` one -- `conformance-tests/test_c13_revocation_terminality.py::test_revoked_credential_stays_revoked_across_every_reactivation_vector`.

#### Status

- Production propagation bound, meaning network and co-location latency beyond the in-process guarantee above, remains deployment evidence for both credential kinds.

### Common

#### Control

- —

#### Evidence

- the C-08 vectors -- `conformance-tests/test_c08_revocation_boundary.py::test_revoked_credential_stops_existing_session_and_reauth`, `::test_disable_propagates_contains_and_enable_is_selective`, `::test_double_revoke_and_double_disable_do_not_loosen_denial`.
- the C-08 vectors -- `conformance-tests/test_c08_revocation_boundary.py::test_propagation_bound_is_finite_and_non_negative`.
- the four adapters are `r2db-api`, `r2db-api-http`, `MitateDB-api`, `MitateDB-api-http` -- `conformance-tests/test_c08_revocation_boundary.py`.
- the bootstrap/reset lifecycle's own revocation-effectiveness and non-permanence properties are additionally covered by C-15, all four adapters taking the PROVIDED branch -- `conformance-tests/test_c15_bootstrap_reset_lifecycle.py`.

#### Status

- —

## SI-14 Security-Relevant Auditability

[history](CONTROL_MAPPING_HISTORY.md#si-14)

### r2db-api

#### Control

- `ControlAuthority` emits canonical lifecycle and control-failure events, denied audit deletion included -- `r2db-api/src/r2db_api/service.py:855`.
- the application facade exposes no audit accessor -- `r2db-api/src/r2db_api/service.py`.
- `AuditSink` keeps immutable snapshots behind a forbidden-field guard -- `r2db-api/src/r2db_api/audit.py:67`.
- `r2dbsvc_registry.control_audit` (`0006_control_plane_http.sql`) is a real, durable PostgreSQL table carrying the contract `audit.fields`' 13 named columns plus `recorded_at`.
- state-changing control-plane operations write their audit row in the same transaction as the state change through `unit_of_work()`, so a durable-write failure aborts the state change too -- `control_plane.py`.
- `target_id`, the contract's 13th `audit.fields` member, names the single target credential or application a lifecycle event acted on -- `r2db-api/src/r2db_api/control_plane.py:752`.
- `target_id` is populated at every emission site, the service layer, `ops.py` and the bootstrap/reset ritual alike, and the compromise-window playbook reads it directly off `issue_credential`/`rotate_credential` rows.
- denial events are durably recorded too, contract `audit.sink_failure_policy` listing authentication and authorization denial ahead of state changes -- `r2db-api/src/r2db_api/service.py:695`.
- `AUTH_REQUIRED`, a request with no credential presented at all, is included, so even the cheapest probe leaves a trace -- `r2db-api/src/r2db_api/service.py:49`.
- **The runtime role holds no privilege beyond insert**: `GRANT INSERT`-only on `control_audit` holds for the control-plane process' own role `r2dbsvc_controlplane` -- `r2db-api/migrations/0006_control_plane_http.sql`.
- the schema owner `r2dbsvc_control` retains ordinary owner privilege, so the control-plane role never reads its own writes back -- `r2db-api/migrations/0006_control_plane_http.sql`.
- the out-of-band CLI `python -m r2db_api.ops` writes to the same table, in the same transaction as the state change, for every state-changing subcommand -- `r2db-api/src/r2db_api/ops.py:327`.
- `r2dbsvc_registry.application_audit` (`migrations/0007_application_audit.sql`) carries the same 13 contract `audit.fields` columns `control_audit` does.
- it adds `recorded_at timestamptz NOT NULL DEFAULT clock_timestamp()`, `audit_seq bigserial`, per-column `length` CHECKs and a `count` column -- `r2db-api/migrations/0007_application_audit.sql`.
- `count` is carried only by a closed refusal window's summary event, as that window's repeats when two or more, and is never `0` or `1` -- `r2db-api/src/r2db_api/credential_store.py:1798`.
- **Fail-closed by construction**: the durable row is INSERTed and committed on a separate platform connection before the data transaction commits -- `r2db-api/src/r2db_api/credential_store.py:1635`.
- a sink failure rolls the data transaction back and answers `SERVICE_UNAVAILABLE` -- `r2db-api/src/r2db_api/service.py:99`.
- `outcome="allow"` means authorized and submitted, not committed: a clean commit failure writes a second `outcome="error"` row for the SAME `request_id` -- `r2db-api/src/r2db_api/service.py:101`, `:115`.
- that error row is itself fail-closed -- `r2db-api/src/r2db_api/service.py:678`.
- **Append-only by grant**: `r2dbsvc_api` gains INSERT plus sequence USAGE on `application_audit` and nothing else -- `r2db-api/migrations/0007_application_audit.sql`.
- `r2dbsvc_auditreader` holds SELECT-only on BOTH audit tables -- `r2db-api/migrations/0007_application_audit.sql`.
- `r2dbsvc_controlplane` has no privilege on `application_audit` at all -- `r2db-api/migrations/0007_application_audit.sql`.
- **Which denials are durable**: `_DURABLE_DENIAL_CODES` lists six reason codes -- `AUTH_REQUIRED`, `AUTH_INVALID`, `AUTH_REVOKED`, `FORBIDDEN`, `APPLICATION_DISABLED`, `DESTRUCTIVE_CONFIRMATION_REQUIRED` (`src/r2db_api/service.py`).
- every other reason code writes no durable row and adds no count -- `r2db-api/src/r2db_api/service.py:733`.
- **Refusal window**: a durable-code refusal is counted before its response by `denial_window_record`, keyed by window length, application, actor or "unknown", operation and reason code -- `r2db-api/migrations/0016_denial_window_counter.sql:178`.
- the window is aligned to the clock; its first refusal writes its own audit row and the counter row in one autocommit statement -- `r2db-api/migrations/0016_denial_window_counter.sql:189`, `r2db-api/src/r2db_api/credential_store.py:1637`.
- a later refusal of that window only adds 1 to `occurrences`: one counter row per key, window and window length for the whole deployment -- `r2db-api/migrations/0016_denial_window_counter.sql:194`.
- a count that cannot be recorded answers `SERVICE_UNAVAILABLE`, for every refusal of the window, not only the first -- `r2db-api/src/r2db_api/service.py:741`.
- **The runtime role cannot lower a count**: `r2dbsvc_api` holds EXECUTE on the function and nothing on the counter table, PUBLIC's EXECUTE is revoked, `r2dbsvc_auditreader` holds SELECT -- `r2db-api/migrations/0016_denial_window_counter.sql:230`.
- the function is SECURITY DEFINER with a pinned `search_path`, and it and the table are owned by the schema's owner role whoever applies the migration -- `r2db-api/migrations/0016_denial_window_counter.sql:159`, `:221`.
- **F-21** checks SECURITY DEFINER, the pinned `search_path`, PUBLIC's EXECUTE and the function's and table's owner -- `r2db-api/src/r2db_api/platform_declarations.py:1584`.
- F-21 runs in `build_app` and in `ops verify-declarations`, exit code 20 -- `r2db-api/src/r2db_api/main.py:611`, `r2db-api/src/r2db_api/ops.py:1233`.
- **F-21** also names a runtime role holding a direct privilege on the counter table, a writer or connecting role without EXECUTE, and an audit reader without SELECT -- `r2db-api/src/r2db_api/platform_declarations.py:1584`.
- the in-process plug counts refusals in its own clock-aligned table with the same meaning -- `r2db-api/src/r2db_api/audit.py:241`.
- **Every data-operation event is durable before its response**: `query`, `catalog`, a `mutate` its backend did not record and every replay are written synchronously -- `r2db-api/src/r2db_api/service.py:711`.
- one data operation adds at most one durable row -- `r2db-api/src/r2db_api/service.py:690`.
- the `request_id` the HTTP layer returns is the one written to the durable row -- `r2db-api/src/r2db_api/http.py`.
- a denial row's `application_id` comes from the authenticated `AuthContext`, never a client-declared value -- `r2db-api/src/r2db_api/service.py:695`.
- an unauthenticated denial carries `application_id = NULL` and is keyed on `actor_id or "unknown"` -- `r2db-api/src/r2db_api/service.py:695`.
- **The declared `event_class`/`operation`/`target_kind` vocabulary is exactly the emitted one**, machine-guaranteed by a single AST scanner over the whole package with no hand-maintained list -- `r2db-api/src/r2db_api/audit_query.py:52`.
- each `<field>=` keyword argument must be a string constant, an `IfExp` of constants, or a genuinely-bound forward parameter -- `r2db-api/src/r2db_api/audit_query.py:52`.
- that forbids smuggling via a dict literal, a subscript or attribute assignment, or passthrough of a client-supplied dict -- `r2db-api/src/r2db_api/audit_query.py:52`.
- every function taking one of those fields declares it keyword-only -- `r2db-api/src/r2db_api/audit_query.py:52`.
- with the literal set thereby enumerable, the scanner pins `U == D union N` and `D intersect N == empty` per field, `N` being an explicitly-named, runtime-measured non-durable exclusion set -- `r2db-api/src/r2db_api/audit_query.py:118`.
- `event_class`'s own `N` holds only the legacy in-memory-sink classes `authentication`/`control_failure`/`control_state`, reached only through `ControlAuthority._control_event` -- `r2db-api/src/r2db_api/service.py:870`.
- `operation` stands at U 31 = D 27 + N 4, the excluded words being `delete_audit`, `set_authorization_state_available`, `set_credential_state` and `control_capabilities` -- `r2db-api/src/r2db_api/audit_query.py:118`.
- `control_capabilities` is excluded because its 2 emit sites can never reach a deny branch -- `r2db-api/src/r2db_api/audit_query.py:118`.
- `target_kind` stands at U 6 = D 5 + N 1, the excluded word being `application_or_credential` -- `r2db-api/src/r2db_api/audit_query.py:155`.
- contract 1.4.0 obligation (b)'s scope is settled by contract text: a data-plane host need not authenticate control or audit credentials merely by declaring `control_plane` other than `unavailable` -- `spec/data-service-api.v1.json`.

#### Evidence

- control audit events -- `test_control_lifecycle_and_failures_are_canonical_audit_events`, `test_audit_is_append_only_and_secret_free`.
- control-plane audit rows -- `r2db-api/tests/test_control_plane_service.py::test_each_state_change_adds_exactly_one_audit_row`, `::test_state_change_sink_fault_injection_aborts_the_state_change`, `::test_target_id_populated_for_application_and_credential_lifecycle_events`.
- control-plane audit rows -- `r2db-api/tests/test_control_plane_service.py::test_issued_secret_appears_only_in_the_response`, `::test_authentication_denials_are_durably_audited_with_truthful_attribution`, `::test_denial_audit_insert_failure_becomes_503_for_every_denial_kind`.
- control-plane audit rows -- `r2db-api/tests/test_control_plane_service.py::test_rate_limit_precedes_authentication_and_is_not_audited`, `r2db-api/tests/test_control_plane_store.py::test_cli_freeze_issuance_writes_control_audit_row`.
- control-plane audit rows -- `r2db-api/tests/test_control_plane_store.py::test_cli_issue_credential_writes_control_audit_row_with_no_secret_anywhere`, `::test_cli_revoke_credential_writes_control_audit_row`.
- control-plane audit rows -- `r2db-api/tests/test_preauth_concurrency_bound.py::test_preauth_concurrency_denial_is_never_durably_audited`.
- the controlplane role: INSERT only, never SELECT, UPDATE or DELETE of its own writes -- `r2db-api/tests/test_control_plane_store.py::test_controlplane_role_grants_match_the_design`.
- durable audit -- `r2db-api/tests/test_application_audit.py::test_a_window_with_one_repeat_has_a_summary_without_a_count_and_a_lone_refusal_has_none`, `::test_coalesced_count_leaf_semantics`.
- durable audit -- `r2db-api/tests/test_application_audit.py::test_destructive_mutate_is_service_unavailable_when_the_durable_sink_fails`, `::test_schema_operation_is_service_unavailable_when_the_durable_sink_fails`, `::test_validation_failed_denials_add_no_durable_row`.
- durable audit -- `r2db-api/tests/test_application_audit.py::test_capability_unsupported_and_not_found_denials_add_no_durable_row`, `::test_each_data_operation_adds_exactly_one_application_audit_row`.
- durable audit -- `r2db-api/tests/test_application_audit.py::test_repeated_invalid_secret_counts_n_repeats_once_in_the_windows_summary`, `::test_different_denial_keys_do_not_share_a_window`.
- events before the response -- `r2db-api/tests/test_application_audit.py::test_query_event_is_durable_before_the_result_is_returned`, `::test_catalog_event_is_durable_before_the_result_is_returned`, `::test_mutate_replay_event_is_durable_before_the_result_is_returned`.
- events before the response -- `r2db-api/tests/test_application_audit.py::test_a_sink_failure_makes_an_ordinary_operation_service_unavailable_and_keeps_no_event`, `::test_non_destructive_mutate_allow_row_is_committed_before_the_data_commit`.
- no process-local audit state -- `r2db-api/tests/test_credential_persistence.py::test_build_app_starts_no_background_audit_thread_and_reads_no_flush_interval`, `r2db-api/tests/test_application_audit.py::test_the_service_keeps_no_denial_window_of_its_own`.
- refusal window, in-process plug -- `r2db-api/tests/test_application_audit.py::test_every_refusal_of_a_window_is_fail_closed_not_only_the_first`, `::test_the_window_follows_the_clock_so_refusals_across_a_boundary_are_two_first_rows`.
- counter grants -- `r2db-api/tests/test_denial_window_counter.py::test_runtime_role_has_execute_on_the_function_and_no_privilege_on_the_counter_table`, `::test_function_is_security_definer_with_a_pinned_search_path`.
- counter grants -- `r2db-api/tests/test_denial_window_counter.py::test_public_holds_no_execute_on_the_function_and_another_role_cannot_call_it`, `::test_migration_run_by_another_role_leaves_the_function_and_table_owned_by_the_schema_owner`.
- counting -- `r2db-api/tests/test_denial_window_counter.py::test_concurrent_first_refusals_of_one_key_leave_one_counter_row_and_one_first_row`, `::test_the_first_refusal_writes_both_rows_in_one_statement_and_commits_before_returning`.
- counting -- `r2db-api/tests/test_denial_window_counter.py::test_a_count_that_cannot_be_added_is_an_error_not_a_silent_loss`, `::test_two_window_lengths_never_share_a_counter_row`, `::test_the_count_of_a_closed_window_is_the_repeats_and_the_total_is_n`.
- counting -- `r2db-api/tests/test_denial_window_counter.py::test_a_service_over_the_postgres_sink_counts_refusals_and_a_failed_count_is_a_503`.
- F-21 -- `r2db-api/tests/test_denial_window_counter.py::test_the_check_names_each_lost_property`, `::test_the_check_names_a_direct_privilege_a_runtime_role_holds_on_the_counter_table`, `::test_build_app_refuses_to_start_when_the_refusal_window_function_is_unsafe_or_missing`.
- F-21 -- `r2db-api/tests/test_ops_verify_declarations.py::test_verify_declarations_f21_when_the_refusal_window_function_is_not_safe_to_run_as_its_owner`.
- the `error` row is itself fail-closed -- `r2db-api/tests/test_application_audit.py::test_failed_data_commit_writes_an_error_row_for_the_same_request_id`.
- the returned `request_id` is the one on the durable row -- `r2db-api/tests/test_application_audit.py::test_failed_data_commit_writes_an_error_row_for_the_same_request_id`.
- a process loss, per spec -- `r2db-api/tests/test_application_audit.py::test_simulated_process_loss_leaves_the_allow_row_alone`.
- role privileges, over a bare `psycopg` connection -- `r2db-api/tests/test_application_audit.py::test_api_role_cannot_select_update_or_delete_application_audit`, `::test_auditreader_role_can_select_both_audit_tables_and_nothing_else`.
- `control_capabilities` -- `r2db-api/tests/test_audit_query.py::test_control_capabilities_operation_has_no_reachable_deny_branch`.
- non-durability is measured, not assumed: each excluded word is driven through its real path -- `r2db-api/tests/test_audit_query.py::test_operation_and_target_kind_non_durable_exclusions_never_reach_the_durable_tables`, `::test_declared_event_classes_cover_every_emittable_class`.
- field keyword arguments; the peer-local helpers are read by path, never imported, the loaded path asserted to be the sibling's -- `r2db-api/tests/test_audit_query.py::test_every_field_keyword_argument_is_a_string_literal_ifexp_or_forward`.
- field keyword arguments; the peer-local helpers are read by path, never imported, the loaded path asserted to be the sibling's -- `r2db-api/tests/test_audit_query.py::test_peer_local_helpers_are_isomorphic_to_the_sibling_peer`.
- declared vocabularies -- `r2db-api/tests/test_audit_query.py::test_declared_audit_event_classes_change_only_deliberately`, `::test_declared_audit_operations_change_only_deliberately`.

#### Status

- **Disclosed limit -- three denial categories are exempted from durable audit**: (i) `control_requests_per_minute` rate-limit refusals run before authentication, with no `credential_id` yet, and before any durable write, so a flood cannot generate unbounded audit rows.
- (ii) `AUTH_STATE_UNAVAILABLE`, where the credential store itself is unreachable, is a service-health outcome whose audit attempt would itself fail, compounding one outage into a second 503 for no benefit.
- the HTTP response is already fail-closed regardless.
- (iii) phase 10's pre-authentication `concurrency` refusals on the application HTTP plane take the slot before `_authenticate`, so the denial has no authenticated actor to attribute and writes no durable row (SI-08).
- These codes are out of scope because they sit outside SI-14's own minimal event class, not because they are uninteresting.
- That minimal event class is authentication/authorization denial, credential/Application lifecycle change, destructive or privilege-sensitive operation, control-plane administrative change, and security-control failure.
- That ground is the same as, but does not resolve or excuse, the control plane's own two exemptions above; the two lines differ in content and neither settles the other.
- **Refusal counts are deployment-wide**: one counter row per key, window and window length plus the window's first audit row, whatever the process count; the counter table's retention and vacuum are runbook work (`POSTGRES_PROVISIONING_RUNBOOK.md` §15).
- **Every data operation and every durable-code refusal costs one platform-database write before its response**, unauthenticated refusals included, and a write that fails answers `SERVICE_UNAVAILABLE` instead of being buffered.
- **In-flight requests are outside `audit.process_loss_policy`**: a request not yet answered when its process stopped may leave an `allow` row with no data commit, read as the declared `outcome_note` states.
- **Disclosed limit**: `AUTH_REQUIRED` durability is a genuinely new unauthenticated-write path, bounded only by coalescing and length CHECKs, not by any rate window.
- `audit_requests_per_minute` governs `audit_query` on the control host only; the operational instruction is `POSTGRES_PROVISIONING_RUNBOOK.md` §16.
- **Two limits disclosed, not overstated**: (i) that both processes point at the SAME platform database is itself unverified, since neither knows the other's DSN, so a stale platform DSN on the control process reproduces the old drift.
- detection stays at post-deploy comparison of the two capability documents, deliberately peer-local since the port carries no method for it.
- (ii) a process can effective-check only its OWN role, only at startup: role settings apply at login, so the control process cannot check `r2dbsvc_api`, and pool connections opened after startup are not re-checked.
- changing the declaration means `ops` plus a restart of BOTH processes.
- **Disclosed limit**: the equality check cannot see a SHRINKING declaration, since moving a durable word from `D` into `N` in the same step keeps `U == D union N` true.
- the only detector is a per-field snapshot test pinning `DECLARED_AUDIT_OPERATIONS`/`DECLARED_AUDIT_TARGET_KINDS`/`DECLARED_AUDIT_EVENT_CLASSES` against a fixture `frozenset`.
- **CLI denials are reported via stderr and an exit code rather than durably audited**: an OS-access-gated tool does not carry the public surface's untraceable-probe risk.

### r2db-api -- audit query

#### Control

- `POST /control/v1/audit/query` and the `POST /v1/audit/query` alias resolve to ONE handler on the control app -- `r2db-api/src/r2db_api/control_http.py:462`.
- the reader is `r2dbsvc_auditreader`, SELECT-only, over the UNION of `control_audit`, `application_audit` and the closed windows of `denial_window_counter` -- `r2db-api/src/r2db_api/audit_query.py:247`.
- a closed window with two or more refusals is one summary event: `recorded_at` is the window end and `event_id` the id stored when the window opened -- `r2db-api/src/r2db_api/credential_store.py:1796`.
- `plane` derives from the source table and is never writer-settable -- `r2db-api/src/r2db_api/audit_query.py:247`.
- the total order is `(recorded_at, plane, event_id)` -- `r2db-api/src/r2db_api/audit_query.py:247`.
- `after` is an opaque keyset cursor, answered `VALIDATION_FAILED` when undecodable -- `r2db-api/src/r2db_api/audit_query.py:247`.
- rows newer than `visibility_lag_ms` are withheld -- `r2db-api/src/r2db_api/audit_query.py:247`.
- the data-plane host's own `/v1/audit/query` is unchanged and still answers `CAPABILITY_UNSUPPORTED` -- `r2db-api/src/r2db_api/http.py`.
- `visibility_lag_ms` is `statement_timeout + idle_in_transaction_session_timeout + 1000ms`, `11000ms` at shipped defaults -- `r2db-api/src/r2db_api/platform_declarations.py:748`.
- both processes derive it from ONE shared ground, the platform catalog `pg_db_role_setting` -- `r2db-api/src/r2db_api/platform_declarations.py:748`.
- each process checks at startup that its own effective value agrees: declared writer, both settings present, neither zero nor negative, no per-database override -- `r2db-api/src/r2db_api/platform_declarations.py:748`.
- that check also requires the writer connection to match the catalog -- `r2db-api/src/r2db_api/platform_declarations.py:748`.
- any such failure stops that process before it declares or serves anything -- `r2db-api/src/r2db_api/platform_declarations.py:748`.
- `capabilities().audit_query.operations` (27 members) and `.target_kinds` (5 members) are published `sorted()` off declared constants, with no enum in the contract -- `r2db-api/src/r2db_api/audit_query.py:118`.
- that is the same declare-the-hazard posture `event_class` has -- `r2db-api/src/r2db_api/audit_query.py:52`.
- the data-plane host declares `audit_query` `unavailable` and carries neither key -- `r2db-api/src/r2db_api/capabilities_document.py:172`.

#### Evidence

- audit-query hosting -- `r2db-api/tests/test_audit_query.py::test_control_host_serves_both_audit_query_paths_with_one_handler`, `::test_cursor_paging_covers_every_row_without_duplicates_under_concurrent_writes`, `::test_data_plane_host_audit_query_still_refuses_with_capability_unsupported`.
- `visibility_lag_ms` -- `r2db-api/tests/test_audit_query.py::test_declared_visibility_lag_ms_is_derived_from_the_two_timeouts`, `r2db-api/tests/test_ops_declarations.py::test_derive_visibility_lag_ms_default_is_11000`.
- the derivation and the two host declarations are all pinned in `r2db-api/tests/test_audit_query.py` -- `r2db-api/tests/test_audit_query.py::test_data_plane_capabilities_declares_contract_version_1_5_0_and_audit_query_unavailable`.
- adapter audit writers -- `r2db-api/tests/test_conformance_adapter_r2db_http_audit_writer_timeouts.py::test_http_conformance_adapter_audit_writer_connection_has_no_explicit_session_override`.
- adapter audit writers -- `MitateDB-api/tests/test_conformance_adapter_mitatedb_http_audit_writer_timeouts.py::test_http_conformance_adapter_audit_writer_connection_has_statement_and_idle_timeouts_set`.
- the control-credential-against-data-host case is a common, unconditional vector -- `conformance-tests/test_c09_audit_evidence.py::test_c09_data_plane_host_audit_query_alias_rejects_control_credential_unless_cohosted`.
- summary events -- `r2db-api/tests/test_denial_window_counter.py::test_audit_query_returns_only_closed_windows_as_application_plane_events_ending_at_the_window_end`, `::test_a_closed_windows_summary_event_keeps_the_same_event_id_across_reads`.
- summary events -- `r2db-api/tests/test_denial_window_counter.py::test_a_walk_through_the_cursor_returns_every_summary_event_exactly_once`, `::test_the_event_class_filter_applies_to_summary_events`.

#### Status

- —

### MitateDB-api

#### Control

- **Application-plane audit, pre-durable-sink foundation**: `AuditSink` uses immutable snapshots plus detail and event allowlists -- `MitateDB-api/src/mitatedb_api/audit.py:47`.
- `mitatedb_registry.control_audit` (migration `0002`) is a real, durable PostgreSQL table carrying the contract `audit.fields`' 13 named columns plus a monotonic `audit_seq` bigserial -- `MitateDB-api/migrations/0002_registry_and_functions.sql`.
- `recorded_at` alone is not a total order under concurrent same-timestamp writes, which C-15's prefix-strict comparison needs -- `MitateDB-api/migrations/0002_registry_and_functions.sql`.
- state-changing operations write their audit row in the SAME transaction as the state change through `unit_of_work()`, so a durable-write failure aborts the state change too -- `MitateDB-api/src/mitatedb_api/control_plane.py:1725`.
- `target_id`, the contract's 13th `audit.fields` member, names the single target credential or application a lifecycle event acted on -- `MitateDB-api/src/mitatedb_api/control_plane.py:1735`.
- denials are durably recorded too, with the same three exemptions r2db-api documents: pre-auth rate-limit refusal, `AUTH_STATE_UNAVAILABLE`, and the pre-auth `concurrency` refusal -- `MitateDB-api/src/mitatedb_api/control_plane.py:1379`.
- that third refusal is taken before `_authenticate` and therefore carries no authenticated actor -- `MitateDB-api/src/mitatedb_api/http.py:547`.
- **The runtime role holds no privilege beyond insert**: `mitatedbsvc_controlplane` has `INSERT`-only privilege on `control_audit`, with no `SELECT`, `UPDATE` or `DELETE` -- `MitateDB-api/migrations/0002_registry_and_functions.sql`.
- the schema owner `mitatedbsvc_provision` is a separate reader role required to read that table back, used by the HTTP conformance adapter and the break-glass `audit-report` subcommand -- `MitateDB-api/src/mitatedb_api/ops.py:454`.
- the out-of-band ritual CLI (`ops.py`) writes to the same table for `bootstrap` and `reset`.
- the break-glass family's state-changing subcommands write through the SAME `ControlPlaneService` methods, so the same-transaction guarantee holds and no second CLI path exists -- `MitateDB-api/src/mitatedb_api/ops.py:454`.
- `mitatedb_registry.application_audit` (`migrations/0005_application_audit.sql`, `event_id text` PRIMARY KEY) carries the identical 13 contract columns plus `count`, `audit_seq`, `recorded_at DEFAULT clock_timestamp()` and the same length CHECKs.
- `mitatedbsvc_api` is INSERT-only, `mitatedbsvc_auditreader` SELECT-only on both audit tables, and `mitatedbsvc_controlplane` has nothing -- `MitateDB-api/migrations/0005_application_audit.sql`.
- a durable-code refusal is counted before its response through the same function, key and 60s default window as r2db-api -- `MitateDB-api/src/mitatedb_api/audit_dispatch.py:168`, `MitateDB-api/src/mitatedb_api/application_audit.py:584`.
- a count that cannot be recorded raises `AuditSinkUnavailable`, answered `SERVICE_UNAVAILABLE` -- `MitateDB-api/src/mitatedb_api/audit_dispatch.py:192`.
- `0017` gives the function and counter table the same SECURITY DEFINER, pinned `search_path`, owner and grants as r2db-api's migration -- `MitateDB-api/migrations/0017_denial_window_counter.sql:164`, `:228`, `:237`.
- **F-21** runs the same check at startup and in `ops verify-declarations` (exit code 20) -- `MitateDB-api/src/mitatedb_api/platform_declarations.py:1562`, `MitateDB-api/src/mitatedb_api/main.py:465`, `MitateDB-api/src/mitatedb_api/ops.py:1502`.
- `audit_query` returns a closed window with two or more refusals as one summary event, as r2db-api does -- `MitateDB-api/src/mitatedb_api/audit_query.py:362`.
- the in-process plug counts refusals in its own clock-aligned table with the same meaning -- `MitateDB-api/src/mitatedb_api/application_audit.py:288`.
- a runtime credential's schema operation refused by the HTTP layer is counted in the refusal window too -- `MitateDB-api/src/mitatedb_api/http.py:1038`.
- **MitateDB-specific**: the legacy 6-field in-memory sink's rounding, which silently maps out-of-vocabulary values to `"unclassified"`/`"unspecified"`, never reaches the durable path -- `MitateDB-api/src/mitatedb_api/audit.py:48`.
- a separate 13-column emitter is used on the durable path instead -- `MitateDB-api/src/mitatedb_api/audit_dispatch.py`.
- **`commit()` runs inside `try`**: `backend_postgres`'s `create_collection`/`add_field`/`delete` commit inside the classified block, so a commit raise is never left unclassified -- `MitateDB-api/src/mitatedb_api/backend_postgres.py:295`.
- that holds on both backends, SQLite's DDL running under an explicit pseudo-transaction -- `MitateDB-api/src/mitatedb_api/backend_sqlite.py`.
- query, insert and update successes are written durably before the response, like r2db-api's own -- `MitateDB-api/src/mitatedb_api/audit_dispatch.py:196`, `MitateDB-api/src/mitatedb_api/cell.py:791`, `:2581`.
- `request_id` is threaded from HTTP through auth, cell and backends, so the wire id matches the durable row's id -- `MitateDB-api/src/mitatedb_api/http.py:559`.
- a `FORBIDDEN` row's `application_id` is the TARGET cell's own id, the victim side, never caller-declared -- `MitateDB-api/src/mitatedb_api/cell.py:3554`.
- `audit_query` is served on the control host at both paths with one handler, reader `mitatedbsvc_auditreader`, `plane` from the source table -- `MitateDB-api/src/mitatedb_api/control_http.py:432`.
- its order is `(recorded_at, plane, event_id)`, its cursor opaque and its `visibility_lag_ms` derived -- `MitateDB-api/src/mitatedb_api/audit_query.py:379`, `:191`, `MitateDB-api/src/mitatedb_api/platform_declarations.py:719`.
- the two-process `visibility_lag_ms` premise is grounded the same way as r2db-api's cell: one shared catalog (`pg_db_role_setting`) grounds both the declaration and the effective value -- `MitateDB-api/src/mitatedb_api/platform_declarations.py`.
- `build_app` applies the same startup double-check and the same removed or rejected env vars -- `MitateDB-api/src/mitatedb_api/main.py:264`.
- both `operation` and `target_kind` are declared, alongside `event_class`, by the same single AST scanner r2db-api's cell describes, with no hand-maintained list -- `MitateDB-api/src/mitatedb_api/audit_query.py:137`.
- `capabilities().audit_query.operations` (29 members) and `.target_kinds` (5 members) are published `sorted()`, each the union of the control half and the application half -- `MitateDB-api/src/mitatedb_api/audit_query.py:137`.
- a mutation in either half turns the same equality check red -- `MitateDB-api/src/mitatedb_api/audit_query.py:137`.
- `operation` stands at U 30 = D 29 + N 1, the excluded word being `control_capabilities`, for the same structurally-unreachable-deny-branch reason as r2db-api's literal -- `MitateDB-api/src/mitatedb_api/audit_query.py:137`.
- `target_kind` stands at U = D = 5 with N empty -- `MitateDB-api/src/mitatedb_api/audit_query.py:139`.
- `event_class`'s own N is empty, and this peer's exclusion list has 1 definition -- `MitateDB-api/src/mitatedb_api/audit_query.py:137`.
- contract 1.4.0 obligation (b) is settled by contract text, as in r2db-api's cell -- `spec/data-service-api.v1.json`.

#### Evidence

- audit events and fields -- `test_audit_events_are_append_only_and_secret_free`, `test_control_audit_fields_matches_the_contract_audit_fields_exactly`, `test_application_plane_role_has_no_privilege_on_control_audit`.
- write faults, `target_id` -- `MitateDB-api/tests/test_control_plane_service.py::test_audit_write_fault_rolls_back_an_accompanying_application_registration`, `::test_audit_write_fault_rolls_back_an_accompanying_credential_revoke`.
- write faults, `target_id` -- `MitateDB-api/tests/test_control_plane_service.py::test_target_id_populated_for_application_and_credential_lifecycle_events`, `::test_target_id_populated_for_control_credential_lifecycle_events`.
- non-durable denials -- `MitateDB-api/tests/test_control_plane_service.py::test_rate_limit_denial_is_never_durably_audited`, `::test_auth_state_unavailable_is_never_durably_audited`, `MitateDB-api/tests/test_preauth_concurrency_bound.py::test_preauth_concurrency_denial_is_never_durably_audited`.
- durable audit -- `MitateDB-api/tests/test_control_plane_postgres.py::test_control_plane_role_cannot_select_its_own_audit_table`, `::test_control_plane_role_can_insert_into_its_own_audit_table`.
- durable audit -- `MitateDB-api/tests/test_application_audit.py::test_api_role_cannot_select_update_or_delete_application_audit`, `::test_auditreader_role_can_select_both_audit_tables_and_nothing_else`, `::test_durable_denial_codes_match_the_design_d3_table`.
- durable audit -- `MitateDB-api/tests/test_application_audit.py::test_repeated_invalid_secret_counts_n_repeats_once_in_the_windows_summary`, `::test_the_router_keeps_no_denial_window_of_its_own`, `::test_every_refusal_of_a_window_is_fail_closed_not_only_the_first`.
- events before the response -- `MitateDB-api/tests/test_application_audit.py::test_query_event_is_durable_before_the_rows_are_returned`, `::test_a_write_records_its_allow_row_before_the_data_commit`, `::test_a_failed_event_write_fails_the_operation_closed_and_keeps_no_event`.
- events before the response -- `MitateDB-api/tests/test_application_audit.py::test_replay_of_a_non_destructive_batch_writes_its_event_before_answering`, `MitateDB-api/tests/test_main.py::test_build_app_starts_no_background_audit_thread_and_reads_no_flush_interval`.
- counter grants and counting -- `MitateDB-api/tests/test_denial_window_counter.py::test_runtime_role_has_execute_on_the_function_and_no_privilege_on_the_counter_table`, `::test_function_is_security_definer_with_a_pinned_search_path`.
- counter grants and counting -- `MitateDB-api/tests/test_denial_window_counter.py::test_concurrent_first_refusals_of_one_key_leave_one_counter_row_and_one_first_row`, `::test_a_router_over_the_postgres_sink_counts_refusals_and_a_failed_count_is_a_503`.
- F-21 and summary events -- `MitateDB-api/tests/test_denial_window_counter.py::test_the_check_names_each_lost_property`, `MitateDB-api/tests/test_ops_verify_declarations.py::test_verify_declarations_f21_when_the_refusal_window_function_or_its_grants_are_not_safe`.
- F-21 and summary events -- `MitateDB-api/tests/test_denial_window_counter.py::test_audit_query_returns_only_closed_windows_as_application_plane_events_ending_at_the_window_end`, `::test_the_count_of_a_closed_window_is_the_repeats_and_the_total_is_n`.
- schema-operation refusals -- `MitateDB-api/tests/test_http.py::test_runtime_credential_forbidden_from_schema_operations_is_counted_in_the_durable_refusal_window`.
- durable audit -- `MitateDB-api/tests/test_application_audit.py::test_durable_path_never_passes_through_the_six_field_rounding_sink`, `::test_declared_event_class_values_are_disjoint_from_the_six_field_sink_rounding_fallbacks`.
- durable audit -- `MitateDB-api/tests/test_application_audit.py::test_backend_commit_failure_is_classified_and_produces_an_error_row`, `::test_in_memory_and_postgres_backends_have_pre_commit_hook_parity`, `::test_query_insert_and_update_success_events_are_durably_recorded`.
- durable audit -- `MitateDB-api/tests/test_application_audit.py::test_each_data_operation_adds_exactly_one_application_audit_row`, `::test_http_response_request_id_matches_the_durable_audit_row`, `::test_application_scope_denied_is_durably_recorded`, `::test_role_denied_is_durably_recorded`.
- durable audit -- `MitateDB-api/tests/test_application_audit.py::test_destructive_delete_is_service_unavailable_when_the_durable_sink_fails_sqlite`, `::test_destructive_delete_is_service_unavailable_when_the_durable_sink_fails_postgres`.
- durable audit -- `MitateDB-api/tests/test_application_audit.py::test_schema_operation_is_service_unavailable_when_the_durable_sink_fails_sqlite`, `::test_schema_operation_is_service_unavailable_when_the_durable_sink_fails_postgres`.
- audit-query hosting -- `MitateDB-api/tests/test_audit_query.py::test_control_host_serves_both_audit_query_paths_with_one_handler`, `::test_cursor_paging_covers_every_row_without_duplicates_under_concurrent_writes`, `::test_control_capabilities_operation_has_no_reachable_deny_branch`.
- a failed data commit, a simulated process loss, and `visibility_lag_ms` -- `MitateDB-api/tests/test_application_audit.py::test_failed_data_commit_writes_an_error_row_for_the_same_request_id`, `::test_simulated_process_loss_leaves_the_allow_row_alone`.
- a failed data commit, a simulated process loss, and `visibility_lag_ms` -- `MitateDB-api/tests/test_audit_query.py::test_declared_visibility_lag_ms_is_derived_from_the_two_timeouts`.
- the catalog-grounded startup check -- `MitateDB-api/tests/test_platform_declarations.py::test_f7_missing_declaration`.
- audit writer connections -- `test_application_audit.py::test_application_audit_writer_connection_reflects_the_api_roles_own_setting`, `MitateDB-api/tests/test_application_audit.py::test_control_audit_writer_connection_reflects_the_controlplane_roles_own_setting`.
- removed env vars -- `test_main.py::test_build_app_rejects_every_removed_env_var_through_the_real_composition_root`.
- the `"authenticate"`/`"assert_active"` and `target_kind="credential"` sites in `auth.py` and `credential_store_postgres.py` are measured to reach the durable tables: `D`, not `N` -- `MitateDB-api/tests/test_audit_query.py::test_authenticate_and_assert_active_denials_are_durable_not_excluded`.
- the same against real PostgreSQL -- `MitateDB-api/tests/test_audit_query.py::test_postgres_authenticate_and_assert_active_denials_are_durable_not_excluded`.

#### Status

- **Two limits, identical to r2db-api's cell**: (i) both processes reading the same platform database is itself unverified.
- (ii) a process can effective-check only its own role, only at startup; the operational instruction is `MitateDB-api/docs/cloud-run-cloud-sql.md` §3.2b.
- **Disclosed limit, identical to r2db-api's cell**: the equality check cannot see a shrinking declaration, and the only detector is a per-field snapshot test.
- **Refusal counts, write cost and in-flight requests, identical to r2db-api's cell**: counts are deployment-wide, every data operation and durable-code refusal costs one platform-database write before its response, and an unanswered request is outside `audit.process_loss_policy`.

### Common

#### Control

- —

#### Evidence

- **CCR-14**'s control-plane durable-audit and non-permanence properties are additionally covered by C-15, all four adapters taking the PROVIDED branch -- `conformance-tests/test_c15_bootstrap_reset_lifecycle.py`.
- the application-plane durable sink and `audit_query` are additionally covered by C-09 -- `conformance-tests/test_c09_audit_evidence.py`.
- the three declaration-agreement vectors below all live in `conformance-tests/test_c09_audit_evidence.py`, whose whole-registry guards are green.
- `AuditResult` reverse-validation is covered by C-11 -- `conformance-tests/test_c11_response_schema_conformance.py`.
- all four registered adapters take the C-09 PROVIDED branch, with no `xfail` -- `conformance-tests/test_c09_audit_evidence.py::test_c09_every_control_surface_adapter_takes_the_provided_branch`.
- that guard requires EVERY registered adapter with a control surface to have taken it (see the C-09 row of `conformance-tests/CONDITIONS.md`).
- declaration agreement -- `conformance-tests/test_c09_audit_evidence.py::test_c09_declaration_agreement_event_class`, `::test_c09_declaration_agreement_operation`, `::test_c09_declaration_agreement_target_kind`.
- each of those raises a known durable event, polls within the declared visibility lag, asserts a NON-EMPTY observation, and only then checks the declaration -- `conformance-tests/test_c09_audit_evidence.py::test_c09_declaration_agreement_event_class`.
- the whole-registry vacuity guard for that trio requires every control-surface adapter to declare 1.5.0 -- `conformance-tests/test_c09_audit_evidence.py::test_c09_every_control_surface_adapter_declares_1_5_0`.
- contract 1.4.0 obligation (b)'s scope is exercised unconditionally on all four plugs over conformance port v1.9 -- `conformance-tests/test_c09_audit_evidence.py::test_c09_data_plane_host_audit_query_alias_rejects_control_credential_unless_cohosted`.
- co-hosting is judged by `adapter.surfaces_cohosted(document)`, derived from a peer's own declared `surfaces` origins -- `conformance-tests/test_c09_audit_evidence.py::test_c09_data_plane_host_audit_query_alias_rejects_control_credential_unless_cohosted`.
- **C-25**'s leg (3), a mutation's own `request_id` on its own audit event, is driven from the plug's own CONTROL-plane discovery (`control_capabilities()`) -- `conformance-tests/test_c25_result_request_id.py::test_c25_result_request_id`.
- that leg is no longer read off the data-plane document, where every plug declares `audit_query: unavailable` by product-code constant, which left it vacuously undriven -- `conformance-tests/test_c25_result_request_id.py::test_c25_result_request_id`.
- the status is read off the SAME isolated surface the mutation was made through and agrees with the session adapter's own reading -- `conformance-tests/test_c25_result_request_id.py::test_c25_result_request_id`.
- an in-test whole-registry guard requires at least one plug to declare `audit_query` enabled or partial, parametrized once per registered plug, six since the two socket plugs landed -- `conformance-tests/test_c25_result_request_id.py::test_c25_result_request_id`.
- each peer's documented composition root runs as real OS processes in front of a real nginx and serves exactly the surfaces it declared, on both planes (C-26) -- `conformance-tests/test_c26_composition_root.py::test_c26_declared_surfaces_are_served`.
- the deploy smoke on that real startup; a root with no declaration row fails fast instead of starting on a default -- `conformance-tests/test_c26_composition_root.py::test_c26_deploy_smoke_is_green`, `::test_c26_missing_declaration_fails_fast`.
- shutdown and a start failure leave no process, no bound port, no temporary directory and no throwaway database or role behind -- `conformance-tests/test_c26_composition_root.py::test_c26_no_residue_after_shutdown`, `::test_c26_start_failure_leaves_no_residue`.
- the composition-roots registry -- `conformance-tests/test_c26_composition_root.py::test_c26_composition_roots_registry_has_at_least_two`, `::test_c26_items_are_grouped_per_launcher`.
- C-28, on all six adapters: the turn's real send carries a `request_id`, and a same-key, same-body resend returns that same `request_id` -- `conformance-tests/test_c28_baseline_turn.py::test_c28_baseline_turn`.
- C-33, on both composition roots: after every worker of a `workers = 2` root is SIGKILLed, every returned success keeps its audit event -- `conformance-tests/test_c33_process_loss.py::test_c33_returned_successes_keep_their_audit_event_after_the_kill`.
- C-33: the denial events still total every denial the service returned -- `conformance-tests/test_c33_process_loss.py::test_c33_denial_count_total_survives_the_kill`.

#### Status

- **No cited evidence for the common audit-evidence coverage beyond C-09, C-11, C-15, C-25 and C-26**: no test is named for this block's blanket audit-evidence claim; version 2.25's uncited wording is in the history file.
- **Disclosed limit**: the common side only checks that returned is a subset of declared -- the reverse half, a word declared but never returned, stays outside the common suite and is carried by each peer's own cell alone.
- **Disclosed limit**: the `provided` branch's own real-world co-hosted case remains unexercised by any currently-registered deployment, since no registered plug currently co-hosts both surfaces on the same origin -- restated in the C-09 row.

## SI-15 Fail-Closed Authorization

[history](CONTROL_MAPPING_HISTORY.md#si-15)

### r2db-api

#### Control

- `CredentialStore` rejects an unavailable, unknown, disabled or revoked state -- `r2db-api/src/r2db_api/credential_store.py:443`.
- `DataService._check` applies the same rejection on every operation -- `r2db-api/src/r2db_api/service.py:638`.
- **CCR-13**'s declaration-completeness guard is the same fail-closed shape applied to capability declarations rather than credential state (`docs/design/R2DB_CCR13_STORAGE_V1.md` R-1) -- `r2db-api/src/r2db_api/postgres.py:1128`.
- `PostgresCell._load_catalog` fails the whole call closed with `SERVICE_UNAVAILABLE` if one entity lacks the `id`/`_r2db_revision` columns its declaration requires -- `r2db-api/src/r2db_api/postgres.py:1128`.
- that is instead of silently publishing a false declaration for that entity -- `r2db-api/src/r2db_api/postgres.py:1128`.
- `_authorize_role` refuses `FORBIDDEN` to an `audit` credential attempting any of the 8 write control operations -- `r2db-api/src/r2db_api/control_plane.py:1272`.
- the same assertion durably audits that denial, rather than merely failing closed with no trace -- `r2db-api/src/r2db_api/control_plane.py:1272`.
- `_AUDIT_ROLE_ALLOWED_OPERATIONS` is the read-only allow-list that refusal is judged against -- `r2db-api/src/r2db_api/control_plane.py:132`.

#### Evidence

- fail-closed states -- `test_revoke_disable_and_unavailable_state_fail_closed`.
- all 8 write control endpoints refuse an `audit` credential with `details["audited"] is True` -- `r2db-api/tests/test_control_plane_service.py::test_audit_role_forbidden_fail_closed_on_every_other_control_endpoint`.
- that vector asserts a durable audit-row-count increment too, over the in-memory and the real-PostgreSQL backend alike -- `r2db-api/tests/test_control_plane_service.py::test_audit_role_forbidden_fail_closed_on_every_other_control_endpoint`.

#### Status

- —

### MitateDB-api

#### Control

- `CredentialStore` rejects an unavailable auth state and a missing or disabled credential -- `MitateDB-api/src/mitatedb_api/auth.py:388`.
- `_authorize_role` refuses an `audit` credential attempting any of the 8 write control operations, with the same fail-closed-with-durable-trace property -- `MitateDB-api/src/mitatedb_api/control_plane.py:1416`.
- `_AUDIT_ROLE_ALLOWED_OPERATIONS` is the read-only allow-list that refusal is judged against -- `MitateDB-api/src/mitatedb_api/control_plane.py:94`.

#### Evidence

- fail-closed states -- `test_disable_revoke_and_unavailable_state_fail_closed`.
- all 8 write operations yield `FORBIDDEN` plus a durable audit-row-count increment -- `MitateDB-api/tests/test_control_plane_service.py::test_audit_role_forbidden_fail_closed_on_every_other_control_endpoint`.
- a genuine post-commit SELECT, not an in-process snapshot -- `MitateDB-api/tests/test_control_plane_postgres.py::test_audit_role_accepted_on_read_endpoints_and_forbidden_on_a_write_endpoint_against_real_postgres`.

#### Status

- —

### Common

#### Control

- —

#### Evidence

- C-08 -- `conformance-tests/test_c08_revocation_boundary.py::test_authorization_state_unavailable_fails_closed_then_recovers`, `::test_disable_propagates_contains_and_enable_is_selective`.
- the four adapters are `r2db-api`, `r2db-api-http`, `MitateDB-api`, `MitateDB-api-http` -- `conformance-tests/test_c08_revocation_boundary.py`.
- an undeclared capability executing anyway, the reverse fail-closed direction, is additionally covered by C-12 and C-17, both on all four adapters -- `test_c12_capability_agreement.py`, `test_c17_declaration_agreement.py`.

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
