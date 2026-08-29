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

1. **PostgreSQL migrations `0001` through `0006` have been applied** against
   the target cluster, per `r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md`
   §5 (`0001_bootstrap_control_plane.sql` through
   `0004_deprovision_application.sql`), migration `0005` (the
   `r2dbsvc_registry.credentials` table and `applications.enabled` column,
   `docs/design/R2DB_CREDENTIAL_PERSISTENCE_AND_COMPOSITION_ROOT_V1.md`
   P2-D1/P2-D2), and migration `0006_control_plane_http.sql` (CCR-14,
   `docs/design/R2DB_CCR14_CONTROL_PLANE_V1.md` R-2/R-3/R-4/R-6 -- the
   `applications` two-state registry, `control_credentials`, `control_audit`,
   and the `r2dbsvc_controlplane` role; see `POSTGRES_PROVISIONING_RUNBOOK.md`
   §11 -- **required even when this deployment does not run the
   control-plane HTTP process at all**, since `0006` also revises
   `begin_provision_application`/`finish_provision_application`, which
   ordinary application onboarding (`0003`) depends on). Every application
   slug this deployment will serve must already be provisioned (`0003`) and
   present in `r2dbsvc_registry.applications` with `enabled = true`. **The
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
   host, with a Python 3.11 virtualenv containing this package installed
   (`pip install` from a build of this repository's `r2db-api/`, matching
   the `requires-python` this codebase targets -- confirm with `python3
   --version` on the target, the same caution the project's own test setup
   applies: system `python3` may be an older version not suitable here).

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
first. A missing/misnamed required environment variable (P2-D5: pepper,
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
   2. Send more requests than the platform pool can serve concurrently: with
      `R2DB_PLATFORM_POOL_SIZE` at its default of `4` (or whatever value
      this deployment's `EnvironmentFile` actually sets), send at least
      `R2DB_PLATFORM_POOL_SIZE + 2` requests, e.g.:
      ```
      for i in $(seq 1 6); do
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
| `R2DB_CREDENTIAL_PEPPER` | The same application-plane pepper `r2db_api.main` uses -- required here too (not merely "if configured"), because this process also issues/rotates *application* credentials in-band; see `control_main`'s own module docstring for why this departs from an earlier design-table reading. |
| `R2DB_CONTROL_LIMIT_APPLICATIONS` / `R2DB_CONTROL_LIMIT_CREDENTIALS_PER_APPLICATION` / `R2DB_CONTROL_LIMIT_CONTROL_REQUESTS_PER_MINUTE` | Optional, SI-08 resource bounds (R-7); default to the contract's `example_profile` values if unset. |
| `R2DB_PLATFORM_SCHEMA` / `R2DB_PLATFORM_POOL_SIZE` | Optional -- identical escape hatch/tuning knob to the application-plane process' own (§10 of the provisioning runbook); a real deployment leaves `R2DB_PLATFORM_SCHEMA` unset. |

**Deployment steps (mirrors §2 above, for the second unit):**

1. Create a dedicated `EnvironmentFile` (e.g. `/etc/r2dbsvc/control.env`),
   root-owned, mode `0600`, containing the table above -- never the
   application plane's own `api.env`.
2. Install a second systemd unit pointing `ExecStart=` at
   `uvicorn r2db_api.control_main:app` on its own internal port, following
   the same account/port-collision checks as §2 steps 1 and 3 above.
3. **Only after** the control-plane process is genuinely running and
   reachable, set `R2DB_CONTROL_PLANE_STATUS=enabled` in the
   **application-plane** process' own `api.env` and restart
   `r2dbsvc-api.service`. This is a deployer *declaration*
   (`r2db_api.main` cannot detect the control plane's actual reachability on
   its own -- R-9); setting it before the control-plane process is actually
   reachable creates a declaration/behavior mismatch (`/v1/capabilities`
   claiming `control_plane: enabled` with nothing listening). The
   authoritative check for "is a separated control plane actually
   reachable" is always the control plane's own `GET /control/v1/capabilities`,
   never the application plane's declaration.
4. **Bootstrap the first control credential** (exactly once per platform
   database, ever -- see `POSTGRES_PROVISIONING_RUNBOOK.md` §12 for the full
   ritual and its lockout/recovery paths):
   ```
   R2DB_CONTROL_DSN=... R2DB_CONTROL_CREDENTIAL_PEPPER=... \
     python -m r2db_api.ops bootstrap
   ```
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
   "enabled"`, and the SI-08 `limits`/`limit_enforcement` (all three classes
   `enforced`). **Unlike the application plane's own `/v1/capabilities`
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
(R-11) -- `ops.py reset` is the single recovery step from a lost, leaked, or
misused control credential.
