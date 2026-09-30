# r2db-api deployment runbook (stage 1: parallel 8443)

Status: operator runbook for `r2db-api/deploy/`. Companion to
`docs/design/R2DB_CREDENTIAL_PERSISTENCE_AND_COMPOSITION_ROOT_V1.md` (P3-D8,
and §3 for the DB authentication posture decision this runbook presents but
does not make), `docs/work-orders/HANDOVER_20260828.md` §2.5 (deployment
policy this runbook implements), and `r2db-api/docs/
POSTGRES_PROVISIONING_RUNBOOK.md` (PostgreSQL provisioning this runbook
assumes has already run).

This document names environment-variable *names* and uses synthetic examples
(`example.invalid`, placeholder internal ports and filesystem paths) for
every target-specific value -- host, credential, DSN, certificate path, and
the internal loopback port are never real here; the real values belong only
in the 0600 `EnvironmentFile` on the deployment target, never in this
repository, per CLAUDE.md's Public Repository Security Gate. Two things this
document names are deliberately *not* placeholders, and are not covered by
that statement: the external port `8443` itself (§0 below -- a real,
deliberately fixed part of the stage-1 design, not a value standing in for
something else), and, in §4, the existing implementation's own endpoint path
names -- non-secret routing facts of the kind already on record in
`docs/work-orders/HANDOVER_20260828.md` §2.5 (§4 carries the full,
source-verified inventory, which is longer than the handover's list),
stated only to keep this document's own non-collision claim checkable in
place, not new disclosure. Path names carry no hostnames, credentials, or
data.

## 0. Scope of this stage

Stage 1 puts the new implementation (`r2db_api.main:app`, this repository's
`r2db-api`) on the same host as the currently-running, unrelated VPS
`r2db-api` deployment (`project/r2-vps/apps/r2db-api`, outside this
repository), listening on a **separate port (8443)** with **no change** to
the existing production 443 nginx server block. This is deliberate: any
mistake made while standing up the new implementation cannot surface on
production traffic, because production traffic never reaches this new code
path (§2.5 of the handover). Stage 2 (§4 below) is the later, separate step
that adds path-based routing on 443 itself and is out of scope for this
document beyond stating its plan and preconditions.

## 1. Prerequisites

Confirm all of the following before starting §2. This runbook does not
re-verify them; it assumes they are already true.

1. **PostgreSQL migrations `0001` through `0008` have been applied** against
   the target cluster, per `r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md`
   §5 (`0001_bootstrap_control_plane.sql` through
   `0004_deprovision_application.sql`), migration `0005` (the
   `r2dbsvc_registry.credentials` table and `applications.enabled` column,
   `docs/design/R2DB_CREDENTIAL_PERSISTENCE_AND_COMPOSITION_ROOT_V1.md`
   P2-D1/P2-D2), migration `0006_control_plane_http.sql` (CCR-14,
   `docs/design/R2DB_CCR14_CONTROL_PLANE_V1.md` R-2/R-3/R-4/R-6 -- the
   `applications` two-state registry, `control_credentials`, `control_audit`,
   and the `r2dbsvc_controlplane` role; see `POSTGRES_PROVISIONING_RUNBOOK.md`
   §11 -- **required even when this deployment does not run the
   control-plane HTTP process at all**, since `0006` also revises
   `begin_provision_application`/`finish_provision_application`, which
   ordinary application onboarding (`0003`) depends on), and migration
   `0007_application_audit.sql` (Phase 4, `docs/design/
   PHASE4_DURABLE_AUDIT_SINK_V1.md` D-1/D-5 -- the `application_audit` table
   and the `r2dbsvc_auditreader` role; `POSTGRES_PROVISIONING_RUNBOOK.md`
   §15 -- **also required even when `R2DB_AUDIT_DSN` is left unset**: the
   application-plane process' `application_audit` writer connection depends
   on the table existing regardless of whether `audit_query` itself is
   declared `enabled`). **Migration `0014_auditreader_statement_timeout.sql`**
   (R-56, `docs/design/R2DB_AUDIT_READER_STATEMENT_TIMEOUT_V0_1.md` D-1 --
   bounds `r2dbsvc_auditreader`'s own `statement_timeout`;
   `POSTGRES_PROVISIONING_RUNBOOK.md` §19) is additive-only and does not
   gate startup, but `ops verify-declarations` reports `FAIL F-17` until it
   is applied and the control process restarted. **Migration
   `0013_role_connection_limits.sql`** (Phase 10 WP-4f, R-66 WP-1 -- raises
   `r2dbsvc_api`/`r2dbsvc_controlplane`/every served application's own
   runtime/developer roles to their own real pool-composition floor;
   `POSTGRES_PROVISIONING_RUNBOOK.md` §4), unlike `0014`, **is required by
   BOTH processes at the default thread limit** (F-16 floors,
   `POSTGRES_PROVISIONING_RUNBOOK.md` §20): without
   it, either process REFUSES TO START (F-16, `check_role_connection_
   limits` -- the same startup fail-fast `0008`/`0012` below trigger).
   `part1_provision_host_and_db.sh` now applies `0013` itself, right after
   `0007`, but only once `part1a_check_max_connections.sh` (run right
   after `0002`) has verified this migration's own precondition --
   `max_connections` leaves enough headroom, `POSTGRES_PROVISIONING_
   RUNBOOK.md` §4; the optional `R2DBSVC_EXPECTED_PEAK_CONNECTIONS`
   overrides that check's own conservative default. And **migration
   `0008_platform_declarations_and_writer_timeouts.sql`** (Q4 phase,
   `docs/design/Q4_DB_SIDE_SINGLE_TRUTH_V1.md` D-1/D-2 --
   `r2dbsvc_registry.platform_declarations` plus the two writer roles'
   `statement_timeout`/`idle_in_transaction_session_timeout` role settings;
   `POSTGRES_PROVISIONING_RUNBOOK.md` §16 -- **required by BOTH processes
   unconditionally**: without it, either process stops at startup with F-8,
   and it takes two `-v` variables naming the writer roles). **After
   applying it, declare this deployment's own surfaces once** --
   `python -m r2db_api.ops declare-surfaces --data-base-url <URL>
   [--control-base-url <URL>]` -- since `0008` deliberately seeds no
   `surfaces` row and neither process starts without one (F-3). **Migration
   `0012_process_ceilings.sql`** (Phase 10 WP-6a, `docs/design/
   PHASE10_DEPLOYMENT_EVIDENCE_V1.md` D-5(ii)/(iii) -- widens
   `platform_declarations_key_check` to admit `process_ceilings`;
   `POSTGRES_PROVISIONING_RUNBOOK.md` §18) is likewise **required by BOTH
   processes unconditionally**, and, like `0008`/`surfaces` above, must be
   followed by declaring this deployment's own ceilings once --
   `python -m r2db_api.ops declare-process-ceilings --data <R2DB_WORKERS>
   --control 1` (`--data` equal to `api.env`'s `R2DB_WORKERS`, §8 below;
   `POSTGRES_PROVISIONING_RUNBOOK.md` §18) -- since `0012` also deliberately
   seeds no `process_ceilings` row and neither process starts without one
   (F-15). **Migration `0015_credential_request_rate.sql`**
   (`POSTGRES_PROVISIONING_RUNBOOK.md` §20 -- the credential-keyed
   `requests_per_minute` row every data-plane worker shares) is **required
   by the application-plane process**: on a platform database without its
   rate function, the application-plane process and its preflight refuse
   to start, naming the migration. **Migration
   `0016_denial_window_counter.sql`** (`POSTGRES_PROVISIONING_RUNBOOK.md`
   §21 -- the refusal-window counter every data-plane worker adds to) is
   likewise **required by the application-plane process**: without it, or
   with its function not in the state the file leaves it in, the
   application-plane process and its preflight refuse to start, naming the
   migration (F-21). `part1_provision_host_and_db.sh` applies it right
   after `0015`. **The required order for an already-provisioned host is:
   `0012` -> `ops declare-process-ceilings` -> restart both processes**
   (ledger LQ4-24; `POSTGRES_PROVISIONING_RUNBOOK.md` §18). Every
   application
   slug this deployment will serve must already be provisioned (`0003`) and
   present in `r2dbsvc_registry.applications` with `enabled = true`, **and
   its per-application platform-upgrade ledger must be current** -- run
   `python -m r2db_api.ops upgrade-status` (exit `0` = nothing pending) and,
   if anything is pending, `python -m r2db_api.ops upgrade-applications
   --lock-timeout <value>` (`--lock-timeout` is required, no default;
   `POSTGRES_PROVISIONING_RUNBOOK.md` §17). An application provisioned by
   the current `0003` is already current; one provisioned earlier is not, and
   its own cell will refuse every request with `SERVICE_UNAVAILABLE` (F-12)
   until the retrofit is applied and this process restarted. **The
   target cluster must be PostgreSQL 13 or later** (CCR-13, `docs/design/
   R2DB_CCR13_STORAGE_V1.md` §6 申し送り 4 -- every entity table's
   `_r2db_revision` column depends on the built-in `gen_random_uuid()`,
   which only exists from version 13 onward); and if any served application
   was provisioned before CCR-13's `0003` DOMAIN addition, apply that
   addition's `CREATE DOMAIN` statements to its database by hand first
   (`POSTGRES_PROVISIONING_RUNBOOK.md` §5's CCR-13 note -- not yet needed
   against this target, since no application has been provisioned here at
   all).
2. **The read-only `r2dbsvc_api` role exists** (P2-D3) with `CONNECT` on
   `r2dbsvc_platform`, `USAGE` on `r2dbsvc_registry`, and `SELECT` only on
   `applications` / `credentials`. This is the role `R2DB_PLATFORM_DSN`
   authenticates as -- never `r2dbsvc_control`. It has no grant at all on
   `control_credentials`/`control_audit` (R-2/R-3) -- a compromise of the
   process using this role cannot read a control credential's verifier or a
   single control-plane audit row.
3. **At least one credential has been issued** for each served application
   via the out-of-band CLI, `python -m r2db_api.ops issue-credential <slug>
   <runtime|developer>` (P2-D6). **CCR-14 is resolved**
   (`spec/CCR_DISPOSITION.md`) and the canonical in-band management surface
   is now `/control/v1` (`docs/design/R2DB_CCR14_CONTROL_PLANE_V1.md` R-10;
   §7 below covers deploying it). `python -m r2db_api.ops` itself is no
   longer a stand-in for that surface -- it now has two narrower, permanent
   jobs: the bootstrap/reset control-credential **ritual** (the only
   `role=control` issuance path there is, by design -- "案B",
   `spec/CCR_DISPOSITION.md`) and operator **break-glass** recovery for when
   `/control/v1` itself is unreachable (`ops.py`'s own module docstring).
   Issuing an *application* credential via `issue-credential` remains valid
   either way (break-glass, or before `/control/v1` is deployed at all) --
   the CLI connects with `R2DB_CONTROL_DSN` (the `r2dbsvc_control` role) --
   an operator-held credential, never placed in the application's own
   `EnvironmentFile` (see §6 below).
4. **Network isolation for PostgreSQL is already verified**, per
   `POSTGRES_PROVISIONING_RUNBOOK.md` §7 -- this runbook's job is standing up
   the ASGI process and nginx listener, not PostgreSQL network policy.
5. A dedicated install location for this deployment exists on the target
   host, with a virtualenv containing this package installed (`pip install
   -c constraints.txt` from a build of this repository's `r2db-api/`,
   `constraints.txt` read from the repository root of that same checkout/
   `git archive` extraction -- R-19) built with an interpreter
   satisfying this codebase's own `requires-python` (`>=3.11`,
   `r2db-api/pyproject.toml`) -- confirm with `python3 --version` on the
   target, the same caution the project's own test setup applies: system
   `python3` may be an older version not suitable here. This runbook
   deliberately does not name one specific interpreter version here: the
   version actually exercised is recorded in two other places instead, so a
   stale hardcoded number here cannot drift out of sync with either of
   them -- the CI Python matrix (`.github/workflows/ci.yml`, Phase 7 WP-2)
   states which versions this codebase's own test suite is verified
   against, and a deployment's own record (`docs/work-orders/DEPLOY_*.md`
   §7-template, Phase 7 WP-1 D-1 (iii)) states which interpreter version
   that specific target actually runs (a target's system Python may be
   newer than the floor this codebase requires -- confirm on the target
   rather than assuming a specific minor version from this document).

## 2. Stage 1 install steps

### Step 1 -- create the dedicated service account

```
sudo useradd --system --no-create-home --shell /usr/sbin/nologin r2dbsvc
```

This account must be distinct from any account the existing VPS `r2db-api`
deployment uses. If that deployment already has an account named `r2dbsvc`
(unexpected, but verify -- `id r2dbsvc` before running the command above),
stop and pick a different account name throughout this runbook and
`deploy/systemd/r2dbsvc-api.service`, the same caution
`POSTGRES_PROVISIONING_RUNBOOK.md` §1 applies to the `r2dbsvc_` PostgreSQL
object-name prefix.

### Step 2 -- place the EnvironmentFile

1. Copy `deploy/env/api.env.example` to `/etc/r2dbsvc/api.env` on the target
   host.
2. Fill in every value marked `REPLACE_WITH_...` with the real secret (from
   your secret manager) or real DSN. Do not leave any placeholder value in
   the installed copy.
3. Decide the DB authentication posture (§3 below) and use the matching DSN
   form for `R2DB_PLATFORM_DSN` and every `R2DB_APP_<SLUG>_*_DSN`.
4. Lock down ownership and mode:
   ```
   sudo mkdir -p /etc/r2dbsvc
   sudo chown root:root /etc/r2dbsvc/api.env
   sudo chmod 0600 /etc/r2dbsvc/api.env
   ```
   `systemd` reads `EnvironmentFile=` as root before the process drops
   privileges to the `r2dbsvc` account (`User=`/`Group=` in the unit), so
   the service account itself never needs read access to this file -- root
   ownership plus `0600` is the intended, sufficient protection boundary,
   matching `POSTGRES_PROVISIONING_RUNBOOK.md`'s treatment of the control
   DSN as an operator-only secret.
5. **Remove all four of `R2DB_AUDIT_STATEMENT_TIMEOUT_MS`,
   `R2DB_AUDIT_IDLE_TIMEOUT_MS`, `R2DB_DATA_BASE_URL` and
   `R2DB_CONTROL_BASE_URL` from this file** if you copied it forward from a
   pre-Q4 deployment (Q4 phase WP-1, design
   `docs/design/Q4_DB_SIDE_SINGLE_TRUTH_V1.md` D-1/D-2). **None of the four
   is read any more, and this process refuses to start while any one of them
   is defined at all, whatever its value -- an empty string included** (F-1
   for the timeouts, F-2 for the base URLs). Commenting the line out counts
   as removed; leaving it set does not, and the failure is at the NEXT
   restart, not at deploy time. The current `deploy/env/api.env.example`
   carries the removal notices in place of these variables.
6. **Declare the surfaces and the writer timeouts once, in the database
   instead** (`POSTGRES_PROVISIONING_RUNBOOK.md` §16, after migration
   `0008`):
   ```
   python -m r2db_api.ops declare-surfaces \
     --data-base-url <this deployment's data base URL, ending /v1> \
     [--control-base-url <its control base URL, ending /control/v1>]
   python -m r2db_api.ops set-platform-timeouts --statement-ms 5000 --idle-ms 5000
   python -m r2db_api.ops declare-coalescing-window --ms 60000
   ```
   (all on `R2DB_CONTROL_DSN`, the provision role -- an operator-held
   credential, never placed in either `EnvironmentFile`). This is now ONE
   declaration shared by both processes, so the two can no longer be
   configured into disagreeing about `surfaces` or about the derived
   `audit_query.visibility_lag_ms`. Pass `--control-base-url` whenever this
   deployment runs the control-plane process (§7); omit it (or pass the
   explicit `--no-control`) only when `R2DB_CONTROL_PLANE_STATUS` stays
   `unavailable` -- **omitting it also removes the control surface for the
   control-plane process, which then refuses to start (F-3c)**. Every
   declaration is read once, at startup: change it, then restart both
   processes (§7's own note on ordering when a timeout value changes).
   **What this still does not check (design §3.11 point 7, ledger LQ4-16):
   that both processes actually read the same platform database.** Diff the
   two capability documents' `surfaces` after any change
   (`docs/work-orders/DEPLOY_Q4_20260905.md` §4-1).

### Step 3 -- choose and verify the internal port

The systemd unit and nginx config both reference a placeholder,
`REPLACE_ME_INTERNAL_PORT`, that is **not** a real port number -- it is
chosen so that forgetting to replace it makes uvicorn fail to start (a
parse error on a non-numeric `--port` value) rather than silently binding
to a number that happens to look plausible.

Before choosing the real port:

1. List what is already listening on the target host:
   ```
   sudo ss -tlnp
   ```
   or, if `ss` is unavailable:
   ```
   sudo lsof -iTCP -sTCP:LISTEN -P
   ```
2. Specifically confirm the existing VPS `r2db-api` deployment's own bound
   port(s) are not the one you are about to pick -- read its actual nginx
   `proxy_pass` upstream and/or its own process manager configuration on the
   target host (this repository does not know that value; do not assume a
   number from any other document). Also confirm 8443 itself (the *public*
   nginx listener this deployment adds, §4 below) is not already bound by
   anything else.
3. Pick an unprivileged port (>1024, so no `CAP_NET_BIND_SERVICE` is ever
   needed -- the systemd unit's `CapabilityBoundingSet=` is empty and relies
   on this) not currently listed by step 1, and not equal to any port named
   in the existing deployment's configuration.
4. Substitute the chosen port for every `REPLACE_ME_INTERNAL_PORT` occurrence
   in **both** `deploy/systemd/r2dbsvc-api.service`'s `ExecStart=` line and
   `deploy/nginx/r2dbsvc-api-8443.conf.example`'s `proxy_pass` line. They
   must match exactly -- nginx proxies to the loopback port uvicorn actually
   bound.

### Step 4 -- install and start the systemd unit

```
sudo cp deploy/systemd/r2dbsvc-api.service /etc/systemd/system/r2dbsvc-api.service
# (after substituting WorkingDirectory/ExecStart paths and the port, per
# the unit file's own header comments and step 3 above)
sudo systemctl daemon-reload
sudo systemctl enable --now r2dbsvc-api.service
sudo systemctl status r2dbsvc-api.service
```

If the unit fails to start, check `journalctl -u r2dbsvc-api.service -e`
first. A failure in the unit's `ExecStartPre=` line is the preflight
(§8): it runs every startup check once, before uvicorn, and its own
traceback names the failing check. A missing/misnamed required environment variable (P2-D5: pepper,
platform DSN, `R2DB_SERVE_APPS`, or any served slug's DSN pair) fails
import with a clear exception naming the missing variable -- this is the
composition root's intended "fail loudly at startup" behavior, not a bug to
work around by relaxing a check.

### Step 5 -- add the nginx 8443 listener

```
sudo cp deploy/nginx/r2dbsvc-api-8443.conf.example /etc/nginx/sites-available/r2dbsvc-api-8443.conf
# (after substituting server_name, certificate paths, TLS policy directives,
# and the internal port, per that file's own header comments and step 3
# above)
sudo ln -s /etc/nginx/sites-available/r2dbsvc-api-8443.conf /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

(Adjust the `sites-available`/`sites-enabled` paths to whatever layout the
target host's existing nginx configuration actually uses -- some hosts
instead use a flat `conf.d/` directory. Confirm from the existing 443
configuration's own layout rather than assuming.)

### Step 6 -- verify

1. **Connectivity / auth wiring, no credential:**
   ```
   curl -sk -o /dev/null -w '%{http_code} %{content_type}\n' https://data.example.invalid:8443/v1/capabilities
   ```
   Expected: `401 application/problem+json` (not an HTML error page, and not
   a bare nginx-level error) -- this single check confirms nginx is proxying
   to the running application, the application's own auth path is reachable
   and fail-closed by default, *and* the response actually carries the
   contract's structured error media type rather than merely the right
   status code. Add `-i` (in place of `-o /dev/null`) to inspect the full
   headers/body if the status code and content type alone are inconclusive.
2. **With a real credential** (issued in Prerequisites step 3):
   ```
   curl -sk -o /dev/null -w '%{http_code} %{content_type}\n' \
     -H "Authorization: Bearer <issued secret>" \
     https://data.example.invalid:8443/v1/capabilities
   ```
   Expected: `200 application/json`, with a body matching the contract's
   `CapabilityDocument` shape (`spec/data-service-api.v1.json`'s
   `definitions.CapabilityDocument`) -- the concrete document this
   deployment actually returns is assembled at request time by
   `DataService.capabilities()` (`r2db-api/src/r2db_api/service.py`), not a
   static file; there is no `config/capabilities.json` response body in this
   implementation (`r2db-api/config/capabilities.json` is a separate,
   design-time declaration used elsewhere, not what this endpoint serves).
   Drop `-o /dev/null` to inspect the actual document.
3. Confirm the existing production 443 listener is unaffected -- a request
   against the existing implementation's own known-good endpoint on 443
   should behave exactly as it did before this deployment (this runbook does
   not name that endpoint, since it belongs to the out-of-repository
   deployment; use whatever the existing operational check for that
   deployment already is).
4. **Platform DB unavailability -- fail-closed, then automatic recovery**
   (P2-D4's `AUTH_STATE_UNAVAILABLE` guarantee, exercised against the real
   deployed process rather than only in the test suite):
   1. Stop PostgreSQL, or otherwise make `R2DB_PLATFORM_DSN` unreachable from
      this host (e.g. a firewall rule blocking the platform DB's
      port/socket -- whichever is less disruptive to anything else sharing
      that cluster).
   2. Send more requests than the platform pools can serve concurrently:
      unset, `R2DB_PLATFORM_POOL_SIZE` derives from each worker's own
      thread limit (`R2DB_THREAD_LIMIT` + 2, `role_pool_size`; 6 at the
      default thread limit of 4; both the credential-store and
      durable-audit-sink platform pools share this same value,
      `POSTGRES_PROVISIONING_RUNBOOK.md` §20). Send at least
      `R2DB_WORKERS × (R2DB_PLATFORM_POOL_SIZE + 2)` requests against
      whichever values this deployment's own `EnvironmentFile`/derived
      default actually resolves to, and no more than the declared
      `concurrency` (32 by default), so that the host-shared slots (§8)
      never answer `429` before the platform pool is reached. Every
      data-plane handler takes its slot before it authenticates (`http.py`),
      so a request beyond `concurrency` is answered `429` without reaching
      the platform pool at all. When the lower figure exceeds `concurrency`
      (at the default thread limit, `R2DB_WORKERS` of 5: 5 × 8 = 40 > 32),
      send exactly `concurrency` requests -- the upper bound wins. E.g. 8
      at one worker and the default thread limit:
      ```
      for i in $(seq 1 8); do
        curl -sk -o /dev/null -w '%{http_code} %{content_type}\n' \
          -H "Authorization: Bearer <issued secret>" \
          https://data.example.invalid:8443/v1/capabilities &
      done
      wait
      ```
      Expected: **every** response is `503`, with `application/problem+json`
      -- none may come back `401` (P2-D4: unreachable platform state must
      never be reported as an invalid credential) and none may hang past a
      reasonable client timeout (a request stuck waiting on a permanently
      unreachable connection would itself be a defect, not merely a slow
      pass). Sending more than the pool's own concurrency limit checks that
      requests queued behind exhausted connections fail closed too, not only
      the first few that reach a connection attempt directly.
   3. Restore PostgreSQL reachability (undo whatever step 1 did).
   4. Repeat step 2's request (a single request is enough this time).
      Expected: `200 application/json` again, with **no restart of the
      `r2dbsvc-api` service** -- recovery must be automatic once the
      platform DB is reachable again, matching P2-D4's "no cache" design (the
      very next request re-establishes/reuses a pool connection and
      succeeds; there is no stale "DB is down" state latched anywhere in the
      process for an operator to have to clear by hand).

## 3. DB authentication posture -- operator decision

Both postures make `PostgresCell`/`PostgresCredentialStore` behave
identically; the DSN's *shape* is a configuration property, not a code
property (P2-D5). **Ruling (2026-08-28): posture B is adopted** — the
requester delegated the choice to the design recommendation (no standing
password material on disk; OS identity is the credential). Posture A
remains documented below as the fallback: switching is a
configuration-only change (rewrite the DSNs, drop the pg_ident map), with
no code involved, and is the recorded remedy if posture B's server-side
configuration proves troublesome in practice.

### Posture A -- password DSN

The role's password is embedded in the DSN, which lives in the 0600
`EnvironmentFile`.

```
R2DB_PLATFORM_DSN=postgresql://r2dbsvc_api:REPLACE_ME@127.0.0.1:5432/r2dbsvc_platform
R2DB_APP_ALPHA_RUNTIME_DSN=postgresql://r2dbsvc_app_alpha_runtime:REPLACE_ME@127.0.0.1:5432/r2dbsvc_app_alpha
R2DB_APP_ALPHA_DEVELOPER_DSN=postgresql://r2dbsvc_app_alpha_developer:REPLACE_ME@127.0.0.1:5432/r2dbsvc_app_alpha
```

- Simple, and identical regardless of PostgreSQL version.
- The protection boundary is entirely the `EnvironmentFile`'s `root:root
  0600` mode -- there is no second layer if that mode is ever loosened.
- Every additional served application adds one more password to the file.
  Rotate via the CLI (`python -m r2db_api.ops rotate-credential` rotates
  *application* credentials against the platform DB; rotating a
  *PostgreSQL role's own* password is a separate, direct `ALTER ROLE ...
  PASSWORD ...` operation against that role, done by whoever holds
  `r2dbsvc_control`, then updating this file and restarting the unit).

### Posture B -- UNIX socket + peer authentication (no password)

The DSN carries no password at all; PostgreSQL authenticates the connecting
OS user via the UNIX socket's peer credentials.

```
R2DB_PLATFORM_DSN=postgresql://r2dbsvc_api@/r2dbsvc_platform?host=/var/run/postgresql
R2DB_APP_ALPHA_RUNTIME_DSN=postgresql://r2dbsvc_app_alpha_runtime@/r2dbsvc_app_alpha?host=/var/run/postgresql
R2DB_APP_ALPHA_DEVELOPER_DSN=postgresql://r2dbsvc_app_alpha_developer@/r2dbsvc_app_alpha?host=/var/run/postgresql
```

This requires two pieces of PostgreSQL server-side configuration, applied
by whoever holds cluster-admin access (outside this repository's migration
scripts, since they configure the server, not the database):

1. **`pg_hba.conf`** -- a `local` line selecting `peer` for the relevant
   database(s)/role(s), e.g.:
   ```
   local   r2dbsvc_platform   r2dbsvc_api          peer map=r2dbsvc_map
   local   r2dbsvc_app_alpha  r2dbsvc_app_alpha_runtime   peer map=r2dbsvc_map
   ```
   (one line per database/role pair actually served; illustrative only).
2. **`pg_ident.conf`** -- a map (`r2dbsvc_map` above) from the OS user the
   `r2dbsvc-api.service` unit runs as (`r2dbsvc`, per §2 step 1) to each
   PostgreSQL role it is allowed to connect as:
   ```
   r2dbsvc_map   r2dbsvc   r2dbsvc_api
   r2dbsvc_map   r2dbsvc   r2dbsvc_app_alpha_runtime
   r2dbsvc_map   r2dbsvc   r2dbsvc_app_alpha_developer
   ```
   Deliberately **do not** add a mapping from `r2dbsvc` to `r2dbsvc_control`
   here -- the whole point of posture B for this process is that the OS
   identity the application runs as can reach only the read-only/per-app
   roles it needs, never the control role (P2-D3's separation, enforced at
   the OS-identity layer instead of only at the password layer).

- No secret material in the `EnvironmentFile` at all for DB access (the
  pepper, `R2DB_CREDENTIAL_PEPPER`, is unrelated and still required either
  way).
- The mapping file grows with each served application/role pair, and must
  be kept in sync with `R2DB_SERVE_APPS` by hand.
- **PostgreSQL version dependency, confirm before adopting:** `pg_ident.conf`
  regex-based multi-role mapping syntax and behavior has changed across
  PostgreSQL major versions. Confirm the exact `pg_ident.conf` syntax
  supported against the target cluster's actual running version (`SELECT
  version();`) before relying on any particular mapping shape -- do not
  copy the illustrative lines above onto the target without that
  confirmation.
- The socket path (`/var/run/postgresql` above) is illustrative; confirm the
  target's actual `unix_socket_directories` setting (`SHOW
  unix_socket_directories;`).
- **Interaction with the systemd unit's `PrivateTmp=true` (`deploy/systemd/
  r2dbsvc-api.service`), check before adopting posture B:** `PrivateTmp=true`
  gives the `r2dbsvc-api` process its own private `/tmp/`, distinct from the
  host's real `/tmp/`. If the confirmed `unix_socket_directories` above
  resolves to a path under `/tmp/` (PostgreSQL's own upstream/RHEL-family
  default -- Debian/Ubuntu instead default to `/var/run/postgresql`, which is
  unaffected), every connection this process makes under posture B silently
  fails, because the socket file visible inside the process's private `/tmp/`
  is not the same object the real `postgres` server is listening on. Either
  reconfigure PostgreSQL to listen under a non-`/tmp` path (preferred), or, if
  that cannot be changed, add an explicit `BindPaths=` carve-out for the real
  socket path to the unit before installing it -- see the fuller explanation
  and example already written at `PrivateTmp=true` in `deploy/systemd/
  r2dbsvc-api.service` itself, so the two files do not drift out of sync on
  this point.

Whichever posture is adopted, use it consistently for **all** DSNs in one
deployment's `EnvironmentFile` -- mixing postures per-DSN is not prohibited
by the code, but adds operational complexity with no isolation benefit,
since both postures already satisfy the same requirement (C-3: PostgreSQL
reachable only via loopback/socket, never a public interface).

## 4. Stage 2 (443 path routing) -- plan, not yet executed

Stage 2 is **out of scope for this runbook's own steps** and is not
performed by anything in `deploy/`. It is recorded here so the plan and its
precondition are not lost between now and when it is actually carried out.

**Plan:** once stage 1 has run long enough to build operational confidence,
add path-based routing to the existing production 443 server block so that
this implementation's traffic reaches it directly on 443, then close 8443
(§5 below covers closing 8443; adding the 443 routing itself is a change
to the existing, out-of-repository 443 server block and is deliberately not
included as a `deploy/` artifact here, since this repository does not own
that file).

**Precondition, re-verified against the existing implementation's actual
source (2026-08-28; supersedes handover §2.5's shorter list):** the
existing implementation's complete top-level path namespace, enumerated
from its FastAPI routers and `main.py`, is `/`, `/health`, `/ready`,
`/v1/tables/*`, `/v1/schema/*` (specifically `/v1/schema/tables`,
`/v1/schema/tables/{table}`, `/v1/schema/tables/{table}/columns`),
`/v1/meta/*`, `/admin`, `/admin/*` (UI assets), `/admin/api/*`,
`/console/*`, `/embed/*`. No path begins with `/control` -- which is what
clears `/control/v1` as the control-plane base path (CCR-14 ruling).

This implementation's six endpoints (`/v1/capabilities`,
`/v1/data/{entity}/query`, `/v1/data/{entity}/mutations`, `/v1/catalog`,
`/v1/schema/operations`, `/v1/audit/query` --
`r2db-api/src/r2db_api/http.py`'s `_ROUTES`) share **no exact path** with
that namespace. One prefix, however, is shared: **both implementations
have routes under `/v1/schema/`.** The handover's shorter list did not
surface this. It does not affect stage 1 (separate ports), but stage 2's
path routing cannot use a bare `location /v1/schema/` prefix block --
route `/v1/schema/operations` to the new implementation with an
exact-match block (`location = /v1/schema/operations`), which nginx
always prefers over prefix matches, and leave the `/v1/schema/tables...`
prefix with the existing implementation.

Before actually performing stage 2, re-verify this inventory against the
existing implementation's *current* routes at that time (routes can
change between now and then) rather than relying solely on this runbook's
record of a past check.

## 5. Rollback

Stage 1's rollback is a single, low-risk step: remove the 8443 server
block.

```
sudo rm /etc/nginx/sites-enabled/r2dbsvc-api-8443.conf
sudo nginx -t
sudo systemctl reload nginx
```

Optionally also stop the backing process (not required for rollback of the
public surface, since nothing external reaches port `REPLACE_ME_INTERNAL_PORT`
without the 8443 listener in front of it -- it is bound to `127.0.0.1` only):

```
sudo systemctl stop r2dbsvc-api.service
```

**Why this cannot affect production 443:** the file removed above is a
server block on a different `listen` port that this deployment itself
added; it was never `include`d by, and never modified, the existing
production 443 server block (§0/§2 step 5). Removing it returns nginx's
configuration to exactly what it was before step 5 of §2 ran, with no other
edit to revert.

## 6. Secrets and DB targets must differ from the existing implementation

The internal port, `R2DB_CREDENTIAL_PEPPER`, every DSN's role/password (or
OS-identity mapping, under posture B), and every PostgreSQL database this
deployment's `EnvironmentFile` names must all be **different values** from
whatever the existing VPS `r2db-api` deployment uses for the same purposes.
This is not optional hygiene -- it is the actual isolation evidence stage 1
exists to establish (`r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md` §1:
"that absence of connection information *is* the isolation evidence").

Reusing the *same variable names* (`R2DB_PLATFORM_DSN`, etc.) as any other
deployment on the same host is fine and expected -- `systemd`'s
`EnvironmentFile=` is scoped per-unit, so two units each with their own
`EnvironmentFile=` never see each other's environment regardless of
variable-name overlap (handover §2.5: "環境変数は同名で良い"). What must
never overlap is the *value*: the same secret string or the same DSN target
used by both processes would mean a compromise of one process's environment
also compromises the other's, defeating the separation this parallel
deployment is meant to demonstrate.

## 7. Control-plane deployment (CCR-14)

Companion to `docs/design/R2DB_CCR14_CONTROL_PLANE_V1.md` (R-1/R-3/R-9/R-10)
and `r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md` §§11-14 (storage,
ritual, lockout recovery, begin-crash residue). This section is additive to
§§1-6 above -- a deployment may run the application plane alone (§§1-6,
`R2DB_CONTROL_PLANE_STATUS` left unset/`unavailable`) with no control-plane
process at all, exactly as before this section existed.

**Process.** The control-plane HTTP surface (`/control/v1`, 11 endpoints) is
a separate ASGI app, `r2db_api.control_main:app`, assembled by
`build_control_app()`. **Default deployment is a separate process, with its
own systemd unit and its own listen address**, distinct from
`r2dbsvc-api.service` (§2 above) -- R-1's own default. Co-locating both apps
behind one server process is permitted (R-1's own SI-00 boundary evidence:
distinct auth stores/DB roles/`AuthorityTopology` registration already make
that safe), but this runbook's own steps assume the separate-process
default; adapt step 3/4 below if co-locating.

**Required environment (`control_main.build_control_app`'s own contract --
see that module's docstring for the authoritative list):**

| Variable | Meaning |
|---|---|
| `R2DB_CONTROLPLANE_DSN` | The `r2dbsvc_controlplane` role's DSN against `r2dbsvc_platform` (§11 of the provisioning runbook). Never `r2dbsvc_control` -- this process must not hold provisioning authority. |
| `R2DB_CONTROL_CREDENTIAL_PEPPER` | Control-credential verifier HMAC pepper. **Must differ from `R2DB_CREDENTIAL_PEPPER`** (R-2) -- this process refuses to start if the two are equal. |
| ~~`R2DB_DATA_BASE_URL`~~ | **REMOVED (Q4 phase WP-1, design `docs/design/Q4_DB_SIDE_SINGLE_TRUTH_V1.md` D-2)** -- no longer read, and **this process refuses to start while it is defined at all** (F-2). `surfaces.data.base_url` now comes from the single `surfaces` row of `r2dbsvc_registry.platform_declarations`, shared with the application-plane process; declare it with `ops declare-surfaces` (`POSTGRES_PROVISIONING_RUNBOOK.md` §16). |
| ~~`R2DB_CONTROL_BASE_URL`~~ | **REMOVED (Q4 phase WP-1, design D-2)** -- same treatment (F-2). This process still requires a control surface unconditionally, but it now requires it in the DECLARATION: a `surfaces` row without a `control` half stops this process with F-3c, naming the `ops declare-surfaces --data-base-url <URL> --control-base-url <URL>` invocation that fixes it. |
| `R2DB_CREDENTIAL_PEPPER` | The same application-plane pepper `r2db_api.main` uses -- required here too (not merely "if configured"), because this process also issues/rotates *application* credentials in-band; see `control_main`'s own module docstring for why this departs from an earlier design-table reading. |
| `R2DB_OPERATION_CATALOG_URL` | Optional. Unset derives `surfaces.data.base_url` with its trailing contract `versioning.base_path` (`/v1`) replaced by the contract's own `endpoints.operation_catalog.path` -- reachable behind the same reverse-proxy prefix (if any) `surfaces.data.base_url` itself already carries. Set it (the SAME value on both this process and `r2db_api.main`) only for a CDN-fronted copy of the operation catalog. |
| `R2DB_CONTROL_LIMIT_APPLICATIONS` / `R2DB_CONTROL_LIMIT_CREDENTIALS_PER_APPLICATION` / `R2DB_CONTROL_LIMIT_CONTROL_REQUESTS_PER_MINUTE` | Optional, SI-08 resource bounds (R-7); default to the contract's `example_profile` values if unset. |
| `R2DB_PLATFORM_SCHEMA` / `R2DB_PLATFORM_POOL_SIZE` | Optional -- identical escape hatch/tuning knob to the application-plane process' own (§10 of the provisioning runbook); a real deployment leaves `R2DB_PLATFORM_SCHEMA` unset. |
| `R2DB_AUDIT_DSN` | Optional (Phase 4, design `PHASE4_DURABLE_AUDIT_SINK_V1.md` D-5) -- the `r2dbsvc_auditreader` role's DSN against `r2dbsvc_platform` (migration `0007_application_audit.sql`, `POSTGRES_PROVISIONING_RUNBOOK.md` §15), read-only over both `control_audit` and `application_audit`. Unset means `audit_query` (`POST /control/v1/audit/query` and its `POST /v1/audit/query` alias) stays declared `unavailable` -- the routes remain registered and still authenticate the caller, answering `CAPABILITY_UNSUPPORTED` rather than a bare 404. |
| ~~`R2DB_AUDIT_STATEMENT_TIMEOUT_MS` / `R2DB_AUDIT_IDLE_TIMEOUT_MS`~~ | **REMOVED (Q4 phase WP-1, design D-1)** -- no longer read, and **either one defined at all stops this process at startup** (F-1). Both writer roles carry the two timeouts as PostgreSQL role settings (`ALTER ROLE ... SET`, migration `0008`); this process derives `audit_query.visibility_lag_ms` from that catalog across every role in the declared `audit_writer_roles` (`max(statement + idle) + 1000` ms clock-skew margin, `11000` at the shipped defaults) **and verifies its own writer connection's effective value against it at startup** (F-9), refusing to start on a mismatch. Change both roles together with `ops set-platform-timeouts` and restart both processes -- **data-plane first when shortening, control first when lengthening** (`POSTGRES_PROVISIONING_RUNBOOK.md` §16). **It cannot effective-check `r2dbsvc_api`'s own connections** (role settings apply at login; design §3.11 point 9) -- that is the application-plane process' own startup job. |
| `R2DB_CONTROL_LIMIT_AUDIT_REQUESTS_PER_MINUTE` | Optional, default `60` (Phase 4, design D-5) -- `audit_query`'s own pre-auth rate window (both paths above), never shared with `R2DB_CONTROL_LIMIT_CONTROL_REQUESTS_PER_MINUTE`. See `POSTGRES_PROVISIONING_RUNBOOK.md` §15 for sizing guidance. |
| `R2DB_CONTROL_LIMIT_REQUEST_BYTES` | Optional, default `1048576` (Phase 4 ledger closure L4-10) -- request-body byte bound, discoverable through `GET /control/v1/capabilities`' own `limits`/`limit_enforcement` keys and enforced by the SAME `ControlPlaneLimits.request_bytes` value (`control_main.py`'s own single-source construction, R-7). Unset behaves exactly as before this variable existed. |

**None of the four request-count classes above (`applications`,
`credentials_per_application`, `control_requests_per_minute`,
`audit_requests_per_minute`) has an upper bound.** `r2db-api` has validated
only "positive integer" here from the start; `MitateDB-api` carried a
`[1, 200]` ceiling on all four until Phase 5 D-3 (Q3 案A, WP-4) removed it,
so both peers now behave identically. Whatever value you set through the
env vars above is an **operator responsibility** -- it is published
as-declared, unchanged, in `GET /control/v1/capabilities`'s own `limits`
object, and nothing in the product will refuse to start or warn you if it
is implausible. A deployment that sets `R2DB_CONTROL_LIMIT_AUDIT_REQUESTS_
PER_MINUTE` (or any of the other three) to an order of magnitude larger
than it needs removes the guardrail that a smaller ceiling used to provide
against exactly that kind of misconfiguration -- for example, an audit
consumer polling far faster than the declared `visibility_lag_ms` warrants
would no longer be capped by a code-side ceiling, only by whatever value
you chose to declare. Size these deliberately; see
`POSTGRES_PROVISIONING_RUNBOOK.md` §15 for `audit_requests_per_minute`
sizing guidance specifically.

A ready-to-copy template listing every variable above, with synthetic
placeholder values and the same style as `deploy/env/api.env.example`, is
`deploy/env/control.env.example`.

**Deployment steps (mirrors §2 above, for the second unit):**

Phase 7 WP-3 turned steps 1-2 below from prose instructions into
reproducible templates and operator scripts -- see `deploy/systemd/
r2dbsvc-control.service` (the second unit, isomorphic to `deploy/systemd/
r2dbsvc-api.service` except unit name/port/`EnvironmentFile`/`ExecStart`),
`deploy/nginx/r2dbsvc-api-8443.conf.example`'s own `location /control/v1/`
block, and `deploy/scripts/` (`part1_provision_host_and_db.sh` through
`0008`+the first application+`ops declare-surfaces`/`upgrade-applications`,
`part1b_control_credential_reset.sh` for step 4 below,
`part2_enable_units_and_nginx.sh` for installing/enabling both units and the
nginx listener together, checking both `EnvironmentFile`s carry none of the
four Q4-removed variables and that `api.env`'s `R2DB_CONTROL_PLANE_STATUS`
agrees with whether part1 declared a control surface (F-6), verifying both
fail closed with no credential, showing the platform declarations
(diagnostic only) and verifying the per-application platform-upgrade
ledger). `deploy/scripts/lint_deploy_assets.sh`
is the syntax-level check the `deploy-assets` CI job runs against all of the
above (unit files, the nginx example, and the scripts themselves) -- it
does not perform a deployment.

**Gap closed (Phase 7 WP-3 addendum, ledger LQ4-24, 2026-09-06; rework the
same day per external review).**
`deploy/scripts/part1_provision_host_and_db.sh` previously applied only
`0001`/`0002`/`0005`/`0006`/`0007` plus the first application's `0003` -- it
never applied `0008` and never ran `ops declare-surfaces`, so a host it alone
provisioned left both processes refusing to start (F-8, then F-3). The script
now also verifies, just before `0008` runs, that `R2DBSVC_API_ROLE`/
`R2DBSVC_CONTROLPLANE_ROLE` equal the literal role names `0005`/`0006`
actually create and that both are present in `pg_roles` (L-3), applies `0008`
(with those same two required variables, fail-fast on the same discipline as
`R2DBSVC_API_PASSWORD`), declares `surfaces` via `ops declare-surfaces`
(required `R2DBSVC_DATA_BASE_URL`; `R2DBSVC_CONTROL_BASE_URL` is OPTIONAL,
mirroring that subcommand's own CLI shape -- H-1 -- with `--no-control` used
when it is unset), records which of the two this run declared in a small
state file under `R2DBSVC_INSTALL_ROOT` for part2 to read back, and brings
every registered application's per-application platform-upgrade ledger
current via `ops upgrade-applications` -- all before printing "part 1
complete". `part2_enable_units_and_nginx.sh` now also refuses to install/
start either unit while its own `EnvironmentFile` still defines any of the
four Q4-removed variables (F-1/F-2's own hazard, checked regardless of
value, an empty string included) or while `api.env`'s
`R2DB_CONTROL_PLANE_STATUS` disagrees with part1's control-surface marker
(F-6, checked BEFORE either `systemctl enable --now` -- see step 3 below for
the resulting operator ordering). Both of those checks, and the placeholder/
existence checks feeding them, read the root-owned `0600` `EnvironmentFile`s
through `sudo` throughout, branching on the underlying `grep`/`test` exit
code so that a check that cannot actually run (rc >= 2: a permission or I/O
error) stops the script rather than being read as "not found" (H-2). Its
closing step then shows `ops show-declarations` purely for a human to read
(never gating anything on its exit code -- M-1) and verifies `ops
upgrade-status` (failing the script, not merely warning, if anything is
still pending) alongside the existing 401 checks (guarded against a
connection-refused target reporting a raw curl failure instead of the
intended "answered 000" diagnostic -- L-2). A host provisioned and brought
up entirely through `part1_provision_host_and_db.sh` +
`part2_enable_units_and_nginx.sh` now needs no more by-hand steps for `0008`/
`declare-surfaces`/the ledger than any other migration this runbook already
assumes scripted -- see those two scripts' own header comments for the exact
variable contract.

**Gap closed (R-66 WP-1 addendum, 2026-09-22).**
`part1_provision_host_and_db.sh` previously never applied
`0013_role_connection_limits.sql` at all -- left unapplied, a host it alone
provisioned could not start EITHER process at the default thread limit
(F-16 floors, `POSTGRES_PROVISIONING_RUNBOOK.md` §20): F-16 (`check_role_connection_limits`) is one of both
processes' own startup fail-fast checks, not merely a check `ops
verify-declarations` reports on demand. The script now also runs
`part1a_check_max_connections.sh` right after `0002` (reads `R2DBSVC_
CONTROL_DSN`, refuses before `0005` runs unless `max_connections` minus
`superuser_reserved_connections` leaves enough headroom -- see
`POSTGRES_PROVISIONING_RUNBOOK.md` §4 for the exact figure and the
optional `R2DBSVC_EXPECTED_PEAK_CONNECTIONS` override), then applies
`0013` right after `0007`, before `0014`.

1. Create a dedicated `EnvironmentFile` (e.g. `/etc/r2dbsvc/control.env`),
   root-owned, mode `0600`, containing the table above (copy
   `deploy/env/control.env.example` as a starting point) -- never the
   application plane's own `api.env`. `part1_provision_host_and_db.sh`
   provisions the database objects this file's DSNs point at; placing the
   file itself is still a manual, per-target step (this repository never
   holds a real value for it).
2. **When provisioning through `part1_provision_host_and_db.sh` +
   `part2_enable_units_and_nginx.sh`, set `R2DB_CONTROL_PLANE_STATUS=enabled`
   in the application-plane `api.env` NOW, BEFORE running
   `part2_enable_units_and_nginx.sh` in step 3 below** (supervisor ruling
   2026-09-06 H-1; this step's own number was moved ahead of the "install/
   run part2" step below in the H-1(c) rework the same day, so the numbered
   sequence itself now matches this instruction -- previously this note sat
   at a later step number than "install the second unit"/"run part2",
   which an operator working through the steps in order could read
   backwards). This script pair always stands **both** systemd units up
   together in one run, unlike a control plane added by hand to an
   already-running data plane later: part2's own F-6 preflight checks this
   variable against whether `part1_provision_host_and_db.sh` declared a
   control surface, and refuses BEFORE either `systemctl enable --now` if
   they disagree. Within one successful part2 run (step 3 below), it
   enables both systemd units FIRST and only THEN verifies each answers
   `401` with no credential -- a run that fails that verification exits
   non-zero without reverting the units it already enabled, so it is a
   part2 run actually reaching "part 2 complete" that closes the window
   between "`api.env` claims a control surface" and "part2 has verified it
   reachable", not merely starting the run.
   **Adding a control-plane process by hand to an application plane that is
   already running, without these scripts**, keeps the general rule this
   step used to state: **only after** the control-plane process is
   genuinely running and reachable, set `R2DB_CONTROL_PLANE_STATUS=enabled`
   in `api.env` and restart `r2dbsvc-api.service`. This is a deployer
   *declaration* (`r2db_api.main` cannot detect the control plane's actual
   reachability on its own -- R-9); setting it before the control-plane
   process is actually reachable creates a declaration/behavior mismatch
   (`/v1/capabilities` claiming `control_plane: enabled` with nothing
   listening). The authoritative check for "is a separated control plane
   actually reachable" is always the control plane's own
   `GET /control/v1/capabilities`, never the application plane's
   declaration.
3. Install the second systemd unit, `deploy/systemd/
   r2dbsvc-control.service`, pointing `ExecStart=` at `uvicorn r2db_api.
   control_main:app` on its own internal port, following the same
   account/port-collision checks as §2 steps 1 and 3 above -- and add the
   nginx `location /control/v1/` block from `deploy/nginx/
   r2dbsvc-api-8443.conf.example` alongside the existing `location /v1/`
   block. `part2_enable_units_and_nginx.sh` performs both halves of this
   step together (install/enable both units, install the nginx listener,
   verify both surfaces answer `401` with no credential) once the
   `EnvironmentFile`s from step 1 are in place AND `api.env` already carries
   the `R2DB_CONTROL_PLANE_STATUS` value step 2 above requires; it refuses
   to install any file that still contains an unresolved `REPLACE_ME_*`
   placeholder, and refuses outright, before enabling either unit, on a
   host that declared no control surface at all (supervisor ruling
   2026-09-06 A10) -- this script pair assumes a deployment standing up
   BOTH surfaces together; a genuinely control-less ("data-only") host
   follows this section's steps by hand instead (§2 above for the
   application plane alone), never running `part2_enable_units_and_nginx.sh`.
4. **Bootstrap the first control credential** (exactly once per platform
   database, ever -- see `POSTGRES_PROVISIONING_RUNBOOK.md` §12 for the full
   ritual and its lockout/recovery paths):
   ```
   R2DB_CONTROL_DSN=... R2DB_CONTROL_CREDENTIAL_PEPPER=... \
     python -m r2db_api.ops bootstrap
   ```
   `deploy/scripts/part1b_control_credential_reset.sh` wraps this same
   command. If bootstrap's stderr contains `error: CONFLICT:` (ops.py's
   fixed refusal text for "a control credential already exists"), the
   script does **not** fall back automatically: it stops with `exit 1`
   unless the operator has explicitly set `R2DBSVC_ALLOW_CONTROL_RESET=1`,
   since the fallback is the gated `reset` ritual (with its own
   declare-and-echo confirmation) and revokes every existing control
   credential on this platform database. Only with that variable set does
   it proceed to `reset` -- the recovery path for the "printed credential
   lost before reaching the secret manager" scenario. Any other bootstrap
   failure (a wrong/unreachable `R2DB_CONTROL_DSN`, a PostgreSQL outage,
   etc.) is not this refusal: the script prints ops's stderr verbatim and
   stops with `exit 1`, never proceeding to `reset`.
   The issued credential is `must_rotate=true` -- authorized for nothing but
   `GET /control/v1/capabilities` and rotating itself until an operator
   completes one real rotation (`POST /control/v1/credentials/{id}/rotate`,
   or the CLI break-glass `rotate-control-credential`). Do this immediately;
   until it is done, the control plane has no usable administrative
   credential for any other operation.
5. Verify, **using the credential printed by step 4**:
   ```
   curl -sk -o /dev/null -w '%{http_code} %{content_type}\n' \
     -H "Authorization: Bearer <secret from step 4>" \
     https://control.example.invalid:<internal port>/control/v1/capabilities
   ```
   Expected: `200 application/json`, `capabilities.control_plane.status ==
   "enabled"`, `capabilities.contract_version == "1.6.0"`, and the SI-08
   `limits`/`limit_enforcement` (all three classes `enforced`). When
   `R2DB_AUDIT_DSN` is wired, `capabilities.audit_query.status` is `enabled`
   and the entry carries three NON-EMPTY declared vocabularies:
   `event_classes`, and -- new in contract 1.5.0 -- `operations` (27 words on
   this peer) and `target_kinds` (5). With the DSN unset, `audit_query` is
   `unavailable` and carries none of them; that is a conformant, honest
   toggle, not a failure (`POSTGRES_PROVISIONING_RUNBOOK.md` §15). A build
   predating contract 1.5.0 declares `1.4.0` and has neither new key, which is
   conformant for THAT version -- what must never disagree is the declared
   version and the declared keys. Also new in contract 1.6.0: the response
   carries a `surfaces` object (`{"data": {"base_url": ...}, "control":
   {"base_url": ...}}`) that must be byte-identical to the SAME key in the
   application plane's own `GET /v1/capabilities` response. **Since the Q4
   phase both processes read that object from ONE declared row** (`ops
   declare-surfaces`, `POSTGRES_PROVISIONING_RUNBOOK.md` §16), so a mismatch
   no longer means "two env files disagree" -- it means **the two processes
   are not reading the same platform database**, the one thing this
   mechanism deliberately does not verify (design §3.11 point 7, ledger
   LQ4-16). **Diff the two documents anyway; that is still the only check
   for it** (`docs/work-orders/DEPLOY_Q4_20260905.md` §4-1).
   **A credential issued by a build predating this peer's own 1.6.0 flip
   will not authenticate here (or on the application plane) until it is
   rotated** -- see `POSTGRES_PROVISIONING_RUNBOOK.md` §12a for why (D-1's
   locator wire form) and the exact rotation commands. **Unlike the application plane's own `/v1/capabilities`
   check (§2 step 6), there is no no-credential variant of this check that
   returns `200`** -- `GET /control/v1/capabilities` authenticates the
   caller exactly like every other `/control/v1` endpoint (`Control
   PlaneService.capabilities` calls `self._authenticate(secret, ...)`
   unconditionally); an omitted/invalid `Authorization` header returns
   `401 AUTH_REQUIRED`, durably recorded in `control_audit` the same as any
   other authentication denial (R-6/R-11) -- it is not itself evidence that
   this deployment step succeeded. What makes `capabilities` special (R-5)
   is only that the step-4 credential, while still `must_rotate=true` at
   this point, is already authorized to call it (`capabilities` and
   self-`rotate` are the two operations a not-yet-rotated credential is
   allowed) -- no other `/control/v1` endpoint would succeed with that same
   credential yet.

**Compromise/misuse:** see `r2db-api/docs/CONTROL_PLANE_COMPROMISE_PLAYBOOK.md`
(R-11) -- `ops.py reset` (a two-step, `--confirm`-gated invocation as of
Q-1 WP-4; see that playbook's own step 1 and `POSTGRES_PROVISIONING_
RUNBOOK.md` §12) is the recovery step from a lost, leaked, or misused
control credential.

## 8. Multi-process data plane on one host

Companion to `docs/design/MULTI_PROCESS_WORKER_V0_1.md` (D-1, D-3) and
`r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md` §18 (`process_ceilings`)
and §20 (the shared rate row and the connection budget).

**One host.** Every process that serves this deployment's data base URL
runs on one host, as a worker of the one `r2dbsvc-api.service` supervisor
(`uvicorn --workers ${R2DB_WORKERS}`); the control base URL is served by
the one `r2dbsvc-control.service` process on the same host. Never run a
copy of either unit on a second host behind the same base URL: the
`concurrency` bound is held by file locks in one host's slot directory,
which another host's processes never see, and `process_ceilings` counts
processes, not hosts.

**Workers and the declaration.**

- `R2DB_WORKERS` (`api.env`) is required: a positive integer, no default.
  The unit passes it as `--workers ${R2DB_WORKERS}` on every start, so
  uvicorn never falls back to `WEB_CONCURRENCY`.
- Declare `process_ceilings.data` equal to it:
  `python -m r2db_api.ops declare-process-ceilings --data <R2DB_WORKERS> --control 1`
  (on `R2DB_CONTROL_DSN`), then stop and start both units -- both read the
  declaration once, at startup.
- The preflight and every worker refuse to start when `R2DB_WORKERS`
  exceeds `process_ceilings.data`.
- `limit_enforcement.concurrency` is `enforced` only while
  `process_ceilings.data` EQUALS `R2DB_WORKERS`. A larger declaration is
  read as "processes on another host may serve this base URL" and answers
  `deployment_required`. `requests_per_minute` is `enforced` at any
  declared ceiling: every worker counts it in the same platform-database
  row per credential (`0015`, `POSTGRES_PROVISIONING_RUNBOOK.md` §20).
- To change the worker count: re-declare `--data`, change `R2DB_WORKERS`
  in `api.env`, check the connection budget for the new count
  (`POSTGRES_PROVISIONING_RUNBOOK.md` §20), then stop and start both units.

**Control plane: one process.** `R2DB_CONTROL_WORKERS=1` in `control.env`
(required, no default) and `process_ceilings.control = 1`. The control
plane's `control_requests_per_minute`/`audit_requests_per_minute` windows
are per process, so this plane runs exactly one process; its preflight
refuses `R2DB_CONTROL_WORKERS` above `process_ceilings.control`.

**Preflight in both units.** Each unit runs `python -m r2db_api.main
--preflight` / `python -m r2db_api.control_main --preflight` as its
`ExecStartPre=`, from the same virtualenv, as the same account, with the
same `EnvironmentFile=` as its `ExecStart=`. The preflight builds the
application once -- every startup check: F-13, F-15, F-16, F-18, workers
against `process_ceilings`; on the data plane the served-application
registry and the slot directory's existence, owner, mode and a `flock`
self-check; on the control plane the pepper separation -- and exits non-zero on the first
failure, which fails the unit before uvicorn starts. uvicorn's own worker
supervisor cannot do this: it replaces a worker that failed at startup and
itself keeps running, so without the preflight a broken environment would
show up only as a restart loop in the journal. The preflight closes its own
connections before uvicorn starts, so it adds nothing to the connection
budget while the workers serve.

**Slot directory.** `r2dbsvc-api.service` carries
`RuntimeDirectory=r2dbsvc-api/slots` and `RuntimeDirectoryMode=0700`:
systemd creates `/run/r2dbsvc-api/slots`, owned by the service account,
mode `0700`, before the preflight runs, and removes it when the unit stops.
`api.env` names the same path in `R2DB_SLOT_DIR` (required, no default).
The application only checks the directory (existence, owner = its own
effective uid, mode `0700`, a working `flock`) and never creates it. Every
in-flight request holds one of `concurrency` slot files under an exclusive
`flock`, and every worker opens the same directory, so the declared
`concurrency` bounds the whole host. The directory holds three kinds of
file: `slot-<i>` (one per slot), `selfcheck` (the startup `flock`
self-check) and `scan` (held briefly while a worker looks for a free
slot). Never point `R2DB_SLOT_DIR` anywhere else, never share the
directory with another unit, and never create it by hand. The control unit
uses no slot directory.

**Signals: never SIGTTIN, never SIGHUP.** SIGTTIN makes the uvicorn
supervisor start one more worker while it runs -- beyond `R2DB_WORKERS`,
the declared `process_ceilings.data`, and the connection budget F-16/F-18
counted. SIGHUP replaces the workers one at a time, so `R2DB_WORKERS + 1`
processes run for a while, again beyond that budget. Restart a unit with
`systemctl stop` followed by `systemctl start` (`systemctl restart` does the
same: it stops before it starts); the units define no `ExecReload=`, and
neither `systemctl reload` nor `kill -HUP`/`kill -TTIN` is ever the way to
pick up a change.

**Never stop a single worker.** Do not stop one worker with SIGSTOP or by
attaching a debugger to it. A worker stopped in the middle of admitting a request holds up admission
on the whole host: while it is stopped, every request can wait up to 1 s
and then be answered `503`. To restart, use `systemctl stop` followed
by `systemctl start`.

**`verify-declarations` checks workers only by hand.** `python -m
r2db_api.ops verify-declarations` compares `R2DB_WORKERS`/
`R2DB_CONTROL_WORKERS` against `process_ceilings` (check `F-20`, exit code
`19`), but it reads both variables from its OWN shell environment, never
from the running units: export the same values `api.env`/`control.env`
carry before running it. With neither variable set it prints no `F-20`
line. It is an operator cross-check; the check that stops a service is the
preflight's.

**Connection budget.** Counted from the thread limit, never from the
declared `concurrency` (a slot holds a file lock, not a connection):
`POSTGRES_PROVISIONING_RUNBOOK.md` §20 has the per-role floors, the
cluster-wide lower bound, and the largest `R2DB_WORKERS` that `0013`'s
role limits admit (5 at the default thread limit).

**Rate row.** `requests_per_minute` is counted per credential in the
platform database (`0015`); at a window edge it may count up to one second
more than 60 s, so it may refuse slightly early and never admits more than
the declared bound (`POSTGRES_PROVISIONING_RUNBOOK.md` §20).

**Rollout overlap: what holds and what does not.** Stopping and starting
`r2dbsvc-api.service` stops every old worker before any new one starts
(`Type=simple`: stop, then start -- an inference from systemd's documented
ordering, not observed on the target), so a restart puts no old and new
process side by side. If old and new processes ever do serve the same base
URL at once:

- `requests_per_minute` holds -- one shared row per credential.
- `concurrency` holds only while both groups use the same slot directory
  on the same host; another directory or another host allows up to twice
  the declared bound.
- The control plane's two windows are per process, so two overlapping
  control processes allow up to twice each declared bound.
- The overlapping processes' connections are outside F-16/F-18 unless
  `process_ceilings` declares the overlap's own process count.

**Confirming on the target.** This repository's development machine has no
systemd, so the unit behavior below is confirmed on the deployment target
after installation:

1. `sudo systemctl start r2dbsvc-api.service`, then
   `systemctl status r2dbsvc-api.service`: the `ExecStartPre=` line reads
   `code=exited, status=0/SUCCESS` (the preflight's checks, the `flock`
   self-check included, passed), and the unit's cgroup lists
   `R2DB_WORKERS` uvicorn worker processes under the uvicorn supervisor
   (with `R2DB_WORKERS=1`, uvicorn runs a single process and no
   supervisor).
2. `sudo ls -ld /run/r2dbsvc-api/slots` shows `drwx------` owned by the
   service account.
3. With `process_ceilings.data` equal to `R2DB_WORKERS`,
   `GET /v1/capabilities` (§2 step 6) reports `limit_enforcement.
   concurrency` and `limit_enforcement.requests_per_minute` as `enforced`.
4. `sudo systemctl stop r2dbsvc-api.service`, then
   `test ! -e /run/r2dbsvc-api/slots && echo removed` prints `removed`
   (systemd removed the runtime directory with the unit). Start the unit
   again.
5. `systemctl status r2dbsvc-control.service`: its own `ExecStartPre=` line
   reads `status=0/SUCCESS`, and its cgroup lists one uvicorn process.
6. Optional, before the unit takes traffic only: set `R2DB_WORKERS` one
   above `process_ceilings.data` in `api.env` and start the unit -- it
   fails in `ExecStartPre=`, the journal naming `R2DB_WORKERS` and
   `process_ceilings.data`, and no uvicorn process starts. Restore the
   value and start again.
7. Measure how long each unit's preflight takes: in `journalctl -u
   r2dbsvc-api.service` (and `-u r2dbsvc-control.service`), the time from
   the start job to uvicorn's first line. Confirm it fits well inside the
   unit's `TimeoutStartSec=` (15 s): systemd counts `ExecStartPre=` inside
   that timeout, and a preflight that runs past it is killed and the unit
   fails its start.
