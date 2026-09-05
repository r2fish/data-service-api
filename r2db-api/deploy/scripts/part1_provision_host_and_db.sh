#!/usr/bin/env bash
# r2dbsvc stage-1 install, part 1 -- OS account, install directory, venv, the
# PostgreSQL migrations through the credential store / control-plane storage
# / audit sink / Q4 platform declarations (0001, 0002, 0005, 0006, 0007,
# 0008) plus one application's onboarding (0003), then the two Q4 `ops`
# steps every fresh host needs before either process will start: declaring
# `surfaces` (0008 deliberately seeds no `surfaces` row, design D-2(c)) and
# bringing every registered application's per-application platform-upgrade
# ledger current (`ops upgrade-applications`, D-4 -- a no-op for THIS
# script's own application, whose ledger the revised `0003` already seeds,
# but idempotent and cheap to run every time regardless, and the one step
# that also retrofits any other application already registered against this
# platform database from an earlier run).
#
# Companion documents: r2db-api/deploy/DEPLOYMENT_RUNBOOK.md §§1-2 (host
# steps) and §7 (control-plane addition), r2db-api/docs/
# POSTGRES_PROVISIONING_RUNBOOK.md §5/§9/§11 (migration order and psql
# invocation shapes), §16 (`0008`, `ops declare-surfaces`/`set-platform-
# timeouts`/`declare-coalescing-window`/`show-declarations`) and §17 (`ops
# upgrade-applications`/`upgrade-status`), docs/design/
# Q4_DB_SIDE_SINGLE_TRUTH_V1.md D-1/D-2/D-3/D-4 (ledger LQ4-24 -- this
# script previously stopped at `0007`+`0003` and never applied `0008` or
# declared surfaces at all, so a host it alone provisioned left both
# processes refusing to start, F-8 then F-3; DEPLOYMENT_RUNBOOK.md §7's own
# "Gap to close by hand" note tracked this until this revision), and
# docs/work-orders/DEPLOY_PHASE6_20260904.md §8 item 10 -- the real-
# deployment incident this script's fail-fast check for
# `R2DBSVC_API_PASSWORD` exists to prevent: migration `0005` was run there
# without that variable set, and failed partway through, requiring a second,
# corrective pass. This script checks every required variable BEFORE running
# anything, so the equivalent failure here happens before any `psql`/`ops`
# invocation, not partway through one. The two new required role-name
# variables below (`R2DBSVC_API_ROLE`/`R2DBSVC_CONTROLPLANE_ROLE`) follow
# that SAME fail-fast discipline for `0008`'s own required psql variables
# (design D-2(h): "migration は psql 変数で role 名を受ける") -- this script
# does not hardcode the production role names itself, exactly as the
# product code deliberately does not (design D-2(h) point 1's own "却下した
# 2 案" -- naming-convention derivation is rejected for the SAME reason a
# script-level hardcoded default would be). Because this script itself
# always runs `0005`/`0006` unmodified, and those two migrations are NOT
# parameterized on role name (they hardcode the literal
# `r2dbsvc_api`/`r2dbsvc_controlplane` unconditionally), this script DOES
# additionally verify -- as a self-consistency check just before `0008`
# runs, never as a hardcoded default fed to `0008` itself -- that these two
# variables equal those exact literals and that both names are already
# present in `pg_roles` (review LQ4-24 rework, supervisor ruling
# 2026-09-06 L-3): a typo in either variable would otherwise only surface
# as `0008`'s own `ALTER ROLE` failing (or, worse, silently succeeding
# against an unrelated existing role of that name).
#
# Rework (review LQ4-24, supervisor ruling 2026-09-06): H-1 makes
# `R2DBSVC_CONTROL_BASE_URL` OPTIONAL again (mirroring `ops declare-
# surfaces`'s own CLI shape) and has this script record which choice it
# made in a small state file `part2_enable_units_and_nginx.sh` reads back
# (see the `R2DBSVC_CONTROL_BASE_URL` paragraph below); L-3 adds the
# role-name/`pg_roles` check described above, just before `0008`.
#
# This script is a synthetic template, written from the runbook and the
# incident record above -- it was not recovered from any real host. Every
# path, port, and account name it references is illustrative or a named
# environment variable; substitute real values only via the environment
# when actually running this script on a target host. Never place a real
# secret, DSN, or hostname inside this file itself (CLAUDE.md's Public
# Repository Security Gate).
#
# Usage (every variable below must be exported or set inline; none has a
# baked-in default, by design -- see require_var()):
#   R2DBSVC_OS_USER=r2dbsvc \
#   R2DBSVC_INSTALL_ROOT=/opt/r2dbsvc/r2db-api \
#   R2DBSVC_PYTHON_BIN=<an interpreter satisfying this project's requires-python;
#     the version itself is authoritative in the runbook and the CI matrix, not here> \
#   R2DBSVC_MIGRATIONS_DIR=/opt/r2dbsvc/r2db-api/migrations \
#   R2DBSVC_BOOTSTRAP_ADMIN_DSN=... R2DBSVC_CONTROL_PASSWORD=... \
#   R2DBSVC_CONTROL_DSN=... \
#   R2DBSVC_API_PASSWORD=... \
#   R2DBSVC_CONTROLPLANE_PASSWORD=... \
#   R2DBSVC_AUDITREADER_PASSWORD=... \
#   R2DBSVC_API_ROLE=r2dbsvc_api R2DBSVC_CONTROLPLANE_ROLE=r2dbsvc_controlplane \
#   R2DBSVC_DATA_BASE_URL=https://data.example.invalid/v1 \
#   [R2DBSVC_CONTROL_BASE_URL=https://control.example.invalid/control/v1] \
#   R2DB_APP_SLUG=sandbox R2DB_APP_RUNTIME_PASSWORD=... R2DB_APP_DEVELOPER_PASSWORD=... \
#     ./part1_provision_host_and_db.sh
#
# `R2DBSVC_API_ROLE`/`R2DBSVC_CONTROLPLANE_ROLE` name the two service writer
# roles `0008` both issues `ALTER ROLE ... SET` for and seeds into the new
# `audit_writer_roles` declaration row (production values are the two shown
# above; this repository's own tests pass throwaway-prefixed names through
# the same migration variables instead -- design D-2(h)).
# `R2DBSVC_DATA_BASE_URL` is this deployment's own `surfaces.data.base_url`
# (design D-2(c)) and is always required. `R2DBSVC_CONTROL_BASE_URL` is this
# deployment's own `surfaces.control.base_url` and is OPTIONAL, mirroring
# `ops declare-surfaces`'s own CLI shape exactly (supervisor ruling
# 2026-09-06 H-1, reversing this script's previous "both required" stance):
# set it to declare a control surface below (`--control-base-url`); leave it
# unset to declare none (`--no-control`, POSTGRES_PROVISIONING_RUNBOOK.md
# §16's own "explicit spelling of that same omission"). Either way this
# script records WHICH of the two it did, in a small state file under
# `R2DBSVC_INSTALL_ROOT` -- Step 4 below now delegates both that `ops
# declare-surfaces` call and the marker write to a separate script,
# `part1c_declare_surfaces.sh` (supervisor ruling 2026-09-06, marker-stale
# finding: the ONE place both now happen, so an operator changing this
# deployment's surfaces declaration LATER re-runs that script alone) --
# never by re-parsing `ops show-declarations`'s own free-text diagnostic
# output (M-1: that command is a display, never a machine contract).
#
# THIS SCRIPT PAIR (this script + `part1c_declare_surfaces.sh` +
# `part1b_control_credential_reset.sh` + `part2_enable_units_and_nginx.sh`)
# ASSUMES A DEPLOYMENT STANDING UP BOTH SURFACES TOGETHER (supervisor ruling
# 2026-09-06 A10): `part2_enable_units_and_nginx.sh` reads this script's
# marker FIRST, before installing or enabling anything, and refuses
# outright -- before either unit exists on disk -- on a host this script
# declared NO control surface for; it does NOT unconditionally install and
# start both systemd units regardless of the choice made here. Concretely:
#   - `R2DBSVC_CONTROL_BASE_URL` set (a control surface declared): part2
#     proceeds to install/enable/verify BOTH units, and separately still
#     requires `api.env`'s own `R2DB_CONTROL_PLANE_STATUS` to AGREE (F-6,
#     next bullet) before enabling either one.
#   - `R2DBSVC_CONTROL_BASE_URL` unset (no control surface declared): part2
#     refuses immediately with a named message, before touching either
#     unit -- a deployment that genuinely never runs the control-plane
#     process does not run `part2_enable_units_and_nginx.sh` at all;
#     DEPLOYMENT_RUNBOOK.md §7's own manual, by-hand procedure is how such
#     a deployment installs/enables the application-plane unit alone (never
#     re-declare with `--control-base-url` here just to get past part2's
#     refusal).
#   - separately, the application-plane unit's own startup check (F-6)
#     requires `surfaces.control`'s declared state to AGREE with ITS OWN
#     `R2DB_CONTROL_PLANE_STATUS` -- when a control surface WAS declared
#     (the first bullet above), `part2_enable_units_and_nginx.sh` checks
#     this script's marker against that variable's value in `api.env`
#     before either unit is enabled (the SAME wording
#     `r2db_api.platform_declarations._f6_forward_message` raises at
#     startup), and refuses BEFORE `systemctl enable --now` on a mismatch.
#     Concretely: set `R2DBSVC_CONTROL_BASE_URL` here only if `api.env`
#     will already have `R2DB_CONTROL_PLANE_STATUS=enabled` set BEFORE
#     part2 runs (DEPLOYMENT_RUNBOOK.md §7 step 2 states this ordering --
#     reversed from the pre-WP-3 prose, and renumbered ahead of the
#     "install the unit"/"run part2" step by the H-1(c) rework the same
#     day -- precisely because this script pair always stands both
#     processes up together, unlike a control plane bolted on to an
#     already-running data plane later by hand); leave it unset, and leave
#     `R2DB_CONTROL_PLANE_STATUS` unset (or `unavailable`) in `api.env`,
#     when this deployment has none.

set -euo pipefail

log() {
    printf '[part1] %s\n' "$1" >&2
}

# ---------------------------------------------------------------------------
# Fail-fast checks. Every variable this script needs is validated here,
# before the first useradd/mkdir/psql runs -- an operator who forgets one
# (as happened with R2DBSVC_API_PASSWORD in the real deployment, DEPLOY_
# PHASE6_20260904.md §8 item 10) gets one clear message naming the missing
# variable, not a migration failing halfway through with the earlier
# statements already committed.
# ---------------------------------------------------------------------------

require_var() {
    # $1 = variable name. Fails loudly if unset, empty, or still holding an
    # unresolved placeholder token -- an operator who copy-pasted this
    # script's own usage example without substituting a real value must not
    # be allowed to proceed silently.
    local name="$1"
    local value="${!name:-}"
    if [ -z "$value" ]; then
        log "required variable ${name} is not set. Aborting before any change is made."
        exit 1
    fi
    case "$value" in
        REPLACE_ME*|'<'*'>')
            log "required variable ${name} still holds an unresolved placeholder (${value}). Aborting before any change is made."
            exit 1
            ;;
    esac
}

for _var in \
    R2DBSVC_OS_USER \
    R2DBSVC_INSTALL_ROOT \
    R2DBSVC_PYTHON_BIN \
    R2DBSVC_MIGRATIONS_DIR \
    R2DBSVC_BOOTSTRAP_ADMIN_DSN \
    R2DBSVC_CONTROL_PASSWORD \
    R2DBSVC_CONTROL_DSN \
    R2DBSVC_API_PASSWORD \
    R2DBSVC_CONTROLPLANE_PASSWORD \
    R2DBSVC_AUDITREADER_PASSWORD \
    R2DBSVC_API_ROLE \
    R2DBSVC_CONTROLPLANE_ROLE \
    R2DBSVC_DATA_BASE_URL \
    R2DB_APP_SLUG \
    R2DB_APP_RUNTIME_PASSWORD \
    R2DB_APP_DEVELOPER_PASSWORD \
; do
    require_var "$_var"
done

# Named explicitly (not merely covered by the loop above) because this is
# the exact variable the real-deployment incident (DEPLOY_PHASE6_20260904.md
# §8 item 10) was missing when migration 0005 was first attempted there.
# Keeping a second, named check here documents the lesson in the script
# itself, even though require_var() above already enforces it.
require_var R2DBSVC_API_PASSWORD

# `R2DBSVC_CONTROL_BASE_URL` is deliberately OUTSIDE the required-variable
# loop above (supervisor ruling 2026-09-06 H-1) -- unset is a valid,
# meaningful choice (declare no control surface), not an operator oversight.
# Still validated for the placeholder-token hazard require_var() guards
# against, but only when it is actually set.
if [ -n "${R2DBSVC_CONTROL_BASE_URL:-}" ]; then
    require_var R2DBSVC_CONTROL_BASE_URL
fi

# ---------------------------------------------------------------------------
# Step 1 -- dedicated, non-login OS service account
# (DEPLOYMENT_RUNBOOK.md §2 step 1)
# ---------------------------------------------------------------------------
if id "${R2DBSVC_OS_USER}" >/dev/null 2>&1; then
    log "OS account ${R2DBSVC_OS_USER} already exists -- not re-created (verify it is not shared with the existing VPS r2db-api deployment, per the runbook's own caution)."
else
    log "creating OS account ${R2DBSVC_OS_USER}"
    sudo useradd --system --no-create-home --shell /usr/sbin/nologin "${R2DBSVC_OS_USER}"
fi

# ---------------------------------------------------------------------------
# Step 2 -- install directory and venv (DEPLOYMENT_RUNBOOK.md §1 item 5).
# This script assumes a checkout of this repository's r2db-api/ already
# exists at R2DBSVC_INSTALL_ROOT (e.g. via `git archive` piped in, or a
# release tarball) -- it does not fetch source itself, matching this WP's
# own "do not recover assets from a real host" discipline in the opposite
# direction: this script also never assumes a specific fetch mechanism.
# ---------------------------------------------------------------------------
log "creating install root ${R2DBSVC_INSTALL_ROOT} (if absent) and its venv"
sudo mkdir -p "${R2DBSVC_INSTALL_ROOT}"
sudo chown "${R2DBSVC_OS_USER}:${R2DBSVC_OS_USER}" "${R2DBSVC_INSTALL_ROOT}"

if [ ! -x "${R2DBSVC_INSTALL_ROOT}/.venv/bin/python" ]; then
    log "creating venv at ${R2DBSVC_INSTALL_ROOT}/.venv with ${R2DBSVC_PYTHON_BIN}"
    sudo -u "${R2DBSVC_OS_USER}" "${R2DBSVC_PYTHON_BIN}" -m venv "${R2DBSVC_INSTALL_ROOT}/.venv"
else
    log "venv already present at ${R2DBSVC_INSTALL_ROOT}/.venv -- not re-created"
fi

log "installing r2db-api into the venv (matching this codebase's requires-python >=3.11 -- see pyproject.toml; the exact interpreter version is an operator/CI choice, not asserted by this script, per DEPLOYMENT_RUNBOOK.md's own :105 note)"
sudo -u "${R2DBSVC_OS_USER}" "${R2DBSVC_INSTALL_ROOT}/.venv/bin/pip" install "${R2DBSVC_INSTALL_ROOT}"

# ---------------------------------------------------------------------------
# Step 3 -- PostgreSQL migrations (POSTGRES_PROVISIONING_RUNBOOK.md §5/§9/
# §11/§16/§17). Order: 0001 (cluster-admin bootstrap) -> 0002 (provisioning
# functions) -> 0005 (credential store + api_password) -> 0006
# (control-plane storage) -> 0007 (audit sink) -> 0008 (Q4 platform
# declarations + writer-role timeouts) -> 0003 (this deployment's first
# application). 0005/0006/0007/0008 are platform-wide bootstrap and are
# independent of any one application (§5/§9/§16's own note); 0003 is placed
# last here so an operator who only wants the platform-wide objects can stop
# before it. `0004` (deprovision) is intentionally never invoked by this
# script -- it is an operator-run teardown path, not part of onboarding.
# `0009` (the per-application platform-upgrade ledger retrofit, §17) is
# likewise never run directly here: the revised `0003` above already seeds
# this deployment's first application with the ledger pre-populated, and the
# general retrofit path for any OTHER already-registered application is
# `ops upgrade-applications` below, not a hand-picked `psql -f 0009_....sql`
# invocation (design D-3(b), D-4).
# ---------------------------------------------------------------------------

log "0001_bootstrap_control_plane.sql (cluster admin)"
psql "${R2DBSVC_BOOTSTRAP_ADMIN_DSN}" \
    -v control_password="${R2DBSVC_CONTROL_PASSWORD}" \
    -f "${R2DBSVC_MIGRATIONS_DIR}/0001_bootstrap_control_plane.sql"

log "0002_provisioning_functions.sql (r2dbsvc_control)"
psql "${R2DBSVC_CONTROL_DSN}" \
    -f "${R2DBSVC_MIGRATIONS_DIR}/0002_provisioning_functions.sql"

log "0005_credential_store.sql (r2dbsvc_control, api_password)"
psql "${R2DBSVC_CONTROL_DSN}" \
    -v api_password="${R2DBSVC_API_PASSWORD}" \
    -f "${R2DBSVC_MIGRATIONS_DIR}/0005_credential_store.sql"

log "0006_control_plane_http.sql (r2dbsvc_control, controlplane_password)"
psql "${R2DBSVC_CONTROL_DSN}" \
    -v controlplane_password="${R2DBSVC_CONTROLPLANE_PASSWORD}" \
    -f "${R2DBSVC_MIGRATIONS_DIR}/0006_control_plane_http.sql"

log "0007_application_audit.sql (r2dbsvc_control, auditreader_password)"
psql "${R2DBSVC_CONTROL_DSN}" \
    -v auditreader_password="${R2DBSVC_AUDITREADER_PASSWORD}" \
    -f "${R2DBSVC_MIGRATIONS_DIR}/0007_application_audit.sql"

# ---------------------------------------------------------------------------
# Role-name / pg_roles consistency check (supervisor ruling 2026-09-06
# L-3), run after 0005/0006 -- which create these two roles under FIXED,
# literal names, `r2dbsvc_api`/`r2dbsvc_controlplane`, neither migration
# parameterized on role name -- and before 0008, which IS parameterized
# (design D-2(h)) and would otherwise accept R2DBSVC_API_ROLE/
# R2DBSVC_CONTROLPLANE_ROLE as free variables with no validation at all.
# This is a self-consistency check specific to THIS script (which always
# runs 0005/0006 unmodified, so their two role names are deterministic),
# never a hardcoded default fed into 0008 or ops.py itself -- those stay
# name-agnostic for the throwaway names this repository's own tests pass
# through the same variables.
# ---------------------------------------------------------------------------
if [ "${R2DBSVC_API_ROLE}" != "r2dbsvc_api" ]; then
    log "refusing to proceed: R2DBSVC_API_ROLE (${R2DBSVC_API_ROLE}) does not match the literal role name 0005_credential_store.sql creates (r2dbsvc_api). Aborting before 0008 runs."
    exit 1
fi
if [ "${R2DBSVC_CONTROLPLANE_ROLE}" != "r2dbsvc_controlplane" ]; then
    log "refusing to proceed: R2DBSVC_CONTROLPLANE_ROLE (${R2DBSVC_CONTROLPLANE_ROLE}) does not match the literal role name 0006_control_plane_http.sql creates (r2dbsvc_controlplane). Aborting before 0008 runs."
    exit 1
fi

log "verifying r2dbsvc_api/r2dbsvc_controlplane are present in pg_roles before 0008 runs"
present_roles=$(psql "${R2DBSVC_CONTROL_DSN}" -tAc \
    "SELECT rolname FROM pg_roles WHERE rolname IN ('r2dbsvc_api', 'r2dbsvc_controlplane') ORDER BY rolname")
missing_roles=""
case "$present_roles" in *r2dbsvc_api*) ;; *) missing_roles="${missing_roles}r2dbsvc_api " ;; esac
case "$present_roles" in *r2dbsvc_controlplane*) ;; *) missing_roles="${missing_roles}r2dbsvc_controlplane " ;; esac
if [ -n "$missing_roles" ]; then
    log "refusing to proceed: pg_roles is missing: ${missing_roles}(expected 0005/0006 to have created them already, run against ${R2DBSVC_CONTROL_DSN}). Aborting before 0008 runs."
    exit 1
fi

log "0008_platform_declarations_and_writer_timeouts.sql (r2dbsvc_control, api_role=${R2DBSVC_API_ROLE} controlplane_role=${R2DBSVC_CONTROLPLANE_ROLE})"
psql "${R2DBSVC_CONTROL_DSN}" \
    -v api_role="${R2DBSVC_API_ROLE}" \
    -v controlplane_role="${R2DBSVC_CONTROLPLANE_ROLE}" \
    -f "${R2DBSVC_MIGRATIONS_DIR}/0008_platform_declarations_and_writer_timeouts.sql"

log "0003_provision_application.sql (r2dbsvc_control, application ${R2DB_APP_SLUG})"
psql "${R2DBSVC_CONTROL_DSN}" \
    -v app_slug="${R2DB_APP_SLUG}" \
    -v runtime_password="${R2DB_APP_RUNTIME_PASSWORD}" \
    -v developer_password="${R2DB_APP_DEVELOPER_PASSWORD}" \
    -f "${R2DBSVC_MIGRATIONS_DIR}/0003_provision_application.sql"

# ---------------------------------------------------------------------------
# Step 4 -- Q4 platform declarations this deployment must make before either
# process will start (POSTGRES_PROVISIONING_RUNBOOK.md §16/§9.1 steps 1-2).
# `0008` above deliberately seeds NO `surfaces` row (design D-2(c): it is
# deployment-specific) -- both `r2db_api.main` and `r2db_api.control_main`
# refuse to start on this platform database until it is declared (F-3).
# `audit_coalescing_window_ms` and the two writer-role timeouts, by
# contrast, ARE seeded by `0008` at the shipped defaults (behavior-
# preserving) -- `ops set-platform-timeouts`/`ops declare-coalescing-window`
# are therefore NOT run here; an operator who wants a non-default value
# runs them by hand, per POSTGRES_PROVISIONING_RUNBOOK.md §16/§9.2, after
# this script completes.
#
# `R2DBSVC_CONTROL_BASE_URL` is optional (H-1 above): declare with
# `--control-base-url` when set, `--no-control` (the explicit spelling of
# the same omission, POSTGRES_PROVISIONING_RUNBOOK.md §16) when not. Both
# the `ops declare-surfaces` call itself and recording which one this run
# did, in a small state file under `R2DBSVC_INSTALL_ROOT`, now live in
# `part1c_declare_surfaces.sh` (supervisor ruling 2026-09-06, marker-stale
# finding), called below -- never duplicated inline here, so there is
# exactly ONE place both happen and an operator changing this deployment's
# surfaces declaration LATER re-runs that script alone, never this whole
# script again (which would also re-run every migration above). See that
# script's own header for the exact contract; it reads
# `R2DBSVC_INSTALL_ROOT`/`R2DBSVC_CONTROL_DSN`/`R2DBSVC_DATA_BASE_URL`/
# `R2DBSVC_CONTROL_BASE_URL` directly out of THIS script's own environment
# (all four are already validated above), no explicit `env` prefix needed.
# `part2_enable_units_and_nginx.sh`'s own both-surfaces gate and F-6
# preflight read the marker it writes (never `ops show-declarations`'s
# free-text output, M-1) before either systemd unit is enabled.
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
"${SCRIPT_DIR}/part1c_declare_surfaces.sh"

control_surface_marker="${R2DBSVC_INSTALL_ROOT}/.r2dbsvc-control-surface-declared"
control_surface_declared=$(sudo cat "$control_surface_marker")

# ---------------------------------------------------------------------------
# Step 5 -- bring every registered application's per-application platform-
# upgrade ledger current (POSTGRES_PROVISIONING_RUNBOOK.md §17, design D-4).
# The application provisioned by step 3 above already carries the ledger
# (the revised `0003` seeds it directly), so this is a no-op for that one
# application -- it is still run unconditionally because it is idempotent
# and is also what retrofits any OTHER application already registered
# against this platform database from an earlier run of this script (or
# from before this WP existed at all). `R2DB_MIGRATIONS_DIR` must be passed
# explicitly here: `ops`'s own default migrations-directory resolution
# assumes an editable/source checkout layout and does not find the
# migrations directory once this package is `pip install`ed into a venv
# (step 2 above) -- see `r2db_api.ops._migrations_dir`'s own `R2DB_
# MIGRATIONS_DIR` override.
# ---------------------------------------------------------------------------
OPS=("${R2DBSVC_INSTALL_ROOT}/.venv/bin/python" -m r2db_api.ops)

log "bringing every registered application's per-application platform-upgrade ledger current (ops upgrade-applications)"
env R2DB_CONTROL_DSN="${R2DBSVC_CONTROL_DSN}" R2DB_MIGRATIONS_DIR="${R2DBSVC_MIGRATIONS_DIR}" \
    "${OPS[@]}" upgrade-applications

log "part 1 complete. Record every generated password above in your secret manager now -- none of it is stored in recoverable form anywhere (POSTGRES_PROVISIONING_RUNBOOK.md §5)."
if [ "$control_surface_declared" = "yes" ]; then
    log "Next: place /etc/r2dbsvc/{api,control}.env (deploy/env/*.example are the templates -- neither may still define R2DB_AUDIT_STATEMENT_TIMEOUT_MS / R2DB_AUDIT_IDLE_TIMEOUT_MS / R2DB_DATA_BASE_URL / R2DB_CONTROL_BASE_URL, POSTGRES_PROVISIONING_RUNBOOK.md §16). Because this run declared a control surface, set R2DB_CONTROL_PLANE_STATUS=enabled in api.env BEFORE running part2_enable_units_and_nginx.sh (DEPLOYMENT_RUNBOOK.md §7 step 2) -- part2 now checks this and refuses (F-6) on a mismatch."
else
    log "Next: this run declared NO control surface. part2_enable_units_and_nginx.sh assumes BOTH surfaces are being stood up together (supervisor ruling 2026-09-06 A10) and refuses outright, before touching either unit, on a data-only host like this one -- do NOT run it. Place /etc/r2dbsvc/api.env (deploy/env/api.env.example is the template -- it may not still define R2DB_AUDIT_STATEMENT_TIMEOUT_MS / R2DB_AUDIT_IDLE_TIMEOUT_MS / R2DB_DATA_BASE_URL / R2DB_CONTROL_BASE_URL, POSTGRES_PROVISIONING_RUNBOOK.md §16), leave R2DB_CONTROL_PLANE_STATUS unset (or 'unavailable') in it, then follow DEPLOYMENT_RUNBOOK.md §7's manual, by-hand procedure to install/enable the application-plane unit alone."
fi
