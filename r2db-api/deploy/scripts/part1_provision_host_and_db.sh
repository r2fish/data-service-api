#!/usr/bin/env bash
# r2dbsvc stage-1 install, part 1 -- OS account, install directory, venv, and
# the PostgreSQL migrations through the credential store / control-plane
# storage / audit sink (0001, 0002, 0005, 0006, 0007) plus one application's
# onboarding (0003).
#
# Companion documents: r2db-api/deploy/DEPLOYMENT_RUNBOOK.md §§1-2 (host
# steps) and §7 (control-plane addition), r2db-api/docs/
# POSTGRES_PROVISIONING_RUNBOOK.md §5/§9/§11 (migration order and psql
# invocation shapes), and docs/work-orders/DEPLOY_PHASE6_20260904.md §8
# item 10 -- the real-deployment incident this script's fail-fast check
# for `R2DBSVC_API_PASSWORD` exists to prevent: migration `0005` was run
# there without that variable set, and failed partway through, requiring a
# second, corrective pass. This script checks every required variable
# BEFORE running anything, so the equivalent failure here happens before
# any `psql` invocation, not partway through one.
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
#   R2DB_APP_SLUG=sandbox R2DB_APP_RUNTIME_PASSWORD=... R2DB_APP_DEVELOPER_PASSWORD=... \
#     ./part1_provision_host_and_db.sh

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
# §11). Order: 0001 (cluster-admin bootstrap) -> 0002 (provisioning
# functions) -> 0005 (credential store + api_password) -> 0006
# (control-plane storage) -> 0007 (audit sink) -> 0003 (this deployment's
# first application). 0005/0006/0007 are control-plane bootstrap and are
# independent of any one application (§5/§9's own note); 0003 is placed
# last here so an operator who only wants the control-plane objects can
# stop before it.
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

log "0003_provision_application.sql (r2dbsvc_control, application ${R2DB_APP_SLUG})"
psql "${R2DBSVC_CONTROL_DSN}" \
    -v app_slug="${R2DB_APP_SLUG}" \
    -v runtime_password="${R2DB_APP_RUNTIME_PASSWORD}" \
    -v developer_password="${R2DB_APP_DEVELOPER_PASSWORD}" \
    -f "${R2DBSVC_MIGRATIONS_DIR}/0003_provision_application.sql"

log "part 1 complete. Record every generated password above in your secret manager now -- none of it is stored in recoverable form anywhere (POSTGRES_PROVISIONING_RUNBOOK.md §5)."
log "Next: place /etc/r2dbsvc/{api,control}.env (deploy/env/*.example are the templates) and run part2_enable_units_and_nginx.sh."
