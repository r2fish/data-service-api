#!/usr/bin/env bash
# r2dbsvc stage-1 install, part 1c -- declare this deployment's `surfaces`
# row (`ops declare-surfaces`) and record which control-surface choice was
# made, in exactly ONE place (supervisor ruling 2026-09-06, marker-stale
# finding, ledger LQ4-24 final rework).
#
# Extracted out of `part1_provision_host_and_db.sh`'s own former Step 4 --
# this script's body is that step, unchanged in substance. Before this
# extraction, the ONLY way to (re-)declare `surfaces` and keep
# `part2_enable_units_and_nginx.sh`'s own control-surface marker in sync was
# to re-run the WHOLE of `part1_provision_host_and_db.sh` (re-applying every
# migration `0001`-`0008`+`0003` along the way) -- or to bypass this script
# family entirely and hand-run `python -m r2db_api.ops declare-surfaces`
# directly, which changes the declared `surfaces` row but does NOT touch
# the marker `part2_enable_units_and_nginx.sh` reads, leaving it stale.
# `part2_enable_units_and_nginx.sh`'s own F-6 rejection message used to
# recommend exactly that hand-run command as the fix for a declared-control-
# but-api.env-says-unavailable mismatch -- an operator following that advice
# literally would silence today's rejection by changing the DATABASE row,
# then hit the SAME rejection again next run, because the marker on disk
# never moved. Re-running THIS script alone, standalone, is now the one
# correct way to change or re-affirm this deployment's surfaces declaration
# after initial provisioning -- it is idempotent (`ops declare-surfaces`
# itself replaces the row, design D-2(c)) and touches nothing else.
#
# `part1_provision_host_and_db.sh` calls this script as its own Step 4
# during a fresh provision (no separate invocation needed there) --
# `part2_enable_units_and_nginx.sh`'s own F-6 rejection message now says to
# re-run THIS script, never to hand-run `ops declare-surfaces` directly.
#
# This script is a synthetic template, written from the runbook and the
# LQ4-24 rework above -- it was not recovered from any real host. Every
# path, port, and account name it references is illustrative or a named
# environment variable; substitute real values only via the environment
# when actually running this script on a target host. Never place a real
# secret, DSN, or hostname inside this file itself (CLAUDE.md's Public
# Repository Security Gate).
#
# Usage:
#   R2DBSVC_INSTALL_ROOT=/opt/r2dbsvc/r2db-api \
#   R2DBSVC_CONTROL_DSN=... \
#   R2DBSVC_DATA_BASE_URL=https://data.example.invalid/v1 \
#   [R2DBSVC_CONTROL_BASE_URL=https://control.example.invalid/control/v1] \
#     ./part1c_declare_surfaces.sh
#
# `R2DBSVC_CONTROL_BASE_URL` is OPTIONAL (supervisor ruling 2026-09-06 H-1),
# exactly as in `part1_provision_host_and_db.sh`: set it to declare a
# control surface (`--control-base-url`); leave it unset to declare none
# (`--no-control`, the explicit spelling of that same omission,
# POSTGRES_PROVISIONING_RUNBOOK.md §16). See
# `part1_provision_host_and_db.sh`'s own header (the paragraph beginning
# "THIS SCRIPT PAIR ... ASSUMES A DEPLOYMENT STANDING UP BOTH SURFACES
# TOGETHER") for what each choice means downstream:
# `part2_enable_units_and_nginx.sh` assumes BOTH surfaces (supervisor ruling
# 2026-09-06 A10) and refuses outright, before enabling any unit, when this
# script's own marker says no control surface was declared -- a deployment
# that genuinely offers no control surface follows
# DEPLOYMENT_RUNBOOK.md §7's manual procedure instead of
# `part2_enable_units_and_nginx.sh`.

set -euo pipefail

log() {
    printf '[part1c] %s\n' "$1" >&2
}

require_var() {
    # Same placeholder discipline as part1_provision_host_and_db.sh's own
    # require_var(): fails loudly if unset, empty, or still holding an
    # unresolved placeholder token.
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
    R2DBSVC_INSTALL_ROOT \
    R2DBSVC_CONTROL_DSN \
    R2DBSVC_DATA_BASE_URL \
; do
    require_var "$_var"
done

# `R2DBSVC_CONTROL_BASE_URL` is deliberately OUTSIDE the required-variable
# loop above (supervisor ruling 2026-09-06 H-1) -- unset is a valid,
# meaningful choice (declare no control surface), not an operator oversight.
# Still validated for the placeholder-token hazard require_var() guards
# against, but only when it is actually set.
if [ -n "${R2DBSVC_CONTROL_BASE_URL:-}" ]; then
    require_var R2DBSVC_CONTROL_BASE_URL
fi

OPS=("${R2DBSVC_INSTALL_ROOT}/.venv/bin/python" -m r2db_api.ops)

if [ -n "${R2DBSVC_CONTROL_BASE_URL:-}" ]; then
    log "declaring surfaces (ops declare-surfaces --data-base-url ... --control-base-url ...)"
    env R2DB_CONTROL_DSN="${R2DBSVC_CONTROL_DSN}" \
        "${OPS[@]}" declare-surfaces \
        --data-base-url "${R2DBSVC_DATA_BASE_URL}" \
        --control-base-url "${R2DBSVC_CONTROL_BASE_URL}"
    control_surface_declared=yes
else
    log "declaring surfaces (ops declare-surfaces --data-base-url ... --no-control: R2DBSVC_CONTROL_BASE_URL is not set)"
    env R2DB_CONTROL_DSN="${R2DBSVC_CONTROL_DSN}" \
        "${OPS[@]}" declare-surfaces \
        --data-base-url "${R2DBSVC_DATA_BASE_URL}" \
        --no-control
    control_surface_declared=no
fi

# Written via `sudo tee` because `R2DBSVC_INSTALL_ROOT` is chowned to
# `R2DBSVC_OS_USER` by `part1_provision_host_and_db.sh` (its own Step 1),
# not to whichever account runs this script.
control_surface_marker="${R2DBSVC_INSTALL_ROOT}/.r2dbsvc-control-surface-declared"
printf '%s\n' "$control_surface_declared" | sudo tee "$control_surface_marker" >/dev/null
log "recorded control-surface-declared=${control_surface_declared} in ${control_surface_marker} for part2_enable_units_and_nginx.sh's both-surfaces gate and F-6 preflight"
