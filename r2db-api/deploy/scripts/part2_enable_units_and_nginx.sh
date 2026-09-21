#!/usr/bin/env bash
# r2dbsvc stage-1 install, part 2 -- check both EnvironmentFiles for the four
# removed Q4 environment variables and for a surfaces.control / R2DB_
# CONTROL_PLANE_STATUS mismatch (F-6), install/enable both systemd units
# (application plane + control plane) and the nginx 8443 listener, verify
# both surfaces answer fail-closed (401) with no credential, then show the
# Q4 platform declarations (diagnostic only) and verify the per-application
# platform-upgrade ledger this deployment depends on is actually current.
#
# Companion documents: r2db-api/deploy/DEPLOYMENT_RUNBOOK.md §2 steps 3-6
# (application plane) and §7 (control-plane addition, "mirrors §2 above,
# for the second unit"). This script is that second unit's install steps,
# made concrete -- §7 previously only described them in prose. The removed-
# variable preflight, the F-6 preflight, and the closing `ops upgrade-
# status`/`show-declarations` step are Q4 phase additions (design docs/
# design/Q4_DB_SIDE_SINGLE_TRUTH_V1.md D-1/D-2/D-3, ledger LQ4-24, r2db-api/
# docs/POSTGRES_PROVISIONING_RUNBOOK.md §16/§17): an EnvironmentFile copied
# forward from a pre-Q4 deployment makes the unit this script is about to
# start refuse at its NEXT restart (F-1/F-2), not at install time, unless
# something checks for it beforehand -- so this script now does, before
# either `systemctl enable --now` call below. Both the removed-variable and
# the F-6 checks read a root-owned, mode-`0600` `EnvironmentFile` -- every
# read of one below goes through `sudo` (supervisor ruling 2026-09-06 H-2),
# and treats a check that cannot actually run (`sudo grep`/`sudo test`
# exiting 2 or higher -- a permission or I/O error, as opposed to rc 1
# "no match"/"absent") as a reason to stop, never as a silent pass.
#
# THIS SCRIPT ASSUMES A DEPLOYMENT STANDING UP BOTH SURFACES TOGETHER
# (supervisor ruling 2026-09-06 A10): it installs, enables, and 401-verifies
# BOTH the application-plane and control-plane units unconditionally, in one
# run. `part1_provision_host_and_db.sh` (via `part1c_declare_surfaces.sh`)
# may legitimately declare NO control surface at all (`--no-control`,
# design §3.7/F-3c) for a genuinely control-less "data-only" host -- that is
# a correct, supported declaration, but this script cannot bring such a
# host up: `r2db_api.control_main` itself refuses to start once
# `surfaces.control` is undeclared, so unconditionally enabling that unit
# here would always fail this script partway through, AFTER the
# application-plane unit is already live and enabled -- a half-installed
# deployment, never a clean "no control surface" one. This script therefore
# reads part1's own control-surface marker FIRST, before installing or
# enabling either unit, and refuses outright for a data-only host (see the
# gate immediately after the required-variable checks below) rather than
# discovering the same fact partway through. A genuinely control-less
# deployment follows DEPLOYMENT_RUNBOOK.md §7's manual, by-hand procedure
# instead (install/enable the application-plane unit only; verify `401`
# against the data surface only) -- it does not run this script at all.
#
# This script is a synthetic template, written from the runbook above -- it
# was not recovered from any real host. It refuses to install a unit file
# or nginx config that still contains an unresolved REPLACE_ME_*/<UPPER_
# SNAKE> placeholder (see reject_placeholder_in_file() below) -- the same
# discipline docs/security/public-repository-policy.md's placeholder
# convention (Phase 7 WP-1) requires of every synthetic artifact in this
# repository, applied here as an operational safety net rather than only a
# publication-time scanner rule: installing a unit with a literal
# REPLACE_ME_CONTROL_PORT in its ExecStart is not merely a public-repo
# hygiene problem, it is uvicorn failing to parse `--port
# REPLACE_ME_CONTROL_PORT` and the unit failing to start (deliberately, per
# both unit files' own header comments).
#
# Usage:
#   R2DBSVC_APP_UNIT_SRC=deploy/systemd/r2dbsvc-api.service \
#   R2DBSVC_CONTROL_UNIT_SRC=deploy/systemd/r2dbsvc-control.service \
#   R2DBSVC_NGINX_CONF_SRC=deploy/nginx/r2dbsvc-api-8443.conf.example \
#   R2DBSVC_NGINX_SITES_AVAILABLE=/etc/nginx/sites-available \
#   R2DBSVC_NGINX_SITES_ENABLED=/etc/nginx/sites-enabled \
#   R2DBSVC_INTERNAL_PORT=8081 R2DBSVC_CONTROL_PORT=8082 \
#   R2DBSVC_INSTALL_ROOT=/opt/r2dbsvc/r2db-api \
#   R2DB_CONTROL_DSN=... \
#     ./part2_enable_units_and_nginx.sh
#
# Optional (default to the exact paths both units' own `EnvironmentFile=`
# name -- override only for a non-standard install layout, or to point this
# script at a scratch copy while testing it):
#   R2DBSVC_API_ENV_FILE=/etc/r2dbsvc/api.env
#   R2DBSVC_CONTROL_ENV_FILE=/etc/r2dbsvc/control.env
#
# `R2DBSVC_INSTALL_ROOT`/`R2DB_CONTROL_DSN` are new in this revision (design
# ledger LQ4-24, item 5). `R2DBSVC_INSTALL_ROOT` is now also used earlier,
# for the both-surfaces gate and F-6 preflight below (it locates the
# control-surface marker `part1c_declare_surfaces.sh` writes under it --
# `part1_provision_host_and_db.sh` calls that script as its own Step 4;
# re-running `part1c_declare_surfaces.sh` alone, standalone, is also the
# supported way to change this deployment's surfaces declaration later,
# supervisor ruling 2026-09-06 marker-stale finding). `R2DB_CONTROL_DSN`
# is used only for the closing `ops upgrade-status` check -- the SAME
# provision-DSN-only diagnostic POSTGRES_PROVISIONING_RUNBOOK.md §17 tells
# an operator to run as part of every deploy's pre-flight -- and for `ops
# show-declarations`, which this script also runs at the same point but
# purely for display (M-1 below: never as a pass/fail gate). `R2DB_
# CONTROL_DSN` is an operator-held credential -- never placed in either
# `EnvironmentFile` (DEPLOYMENT_RUNBOOK.md §2 step 6), passed to this
# script's own environment only for the duration of this one invocation.

set -euo pipefail

log() {
    printf '[part2] %s\n' "$1" >&2
}

require_var() {
    # Same placeholder discipline as part1_provision_host_and_db.sh's own
    # require_var(): fails loudly if unset, empty, or still holding an
    # unresolved placeholder token -- an operator who copy-pasted this
    # script's own usage example without substituting a real value (e.g.
    # R2DBSVC_INTERNAL_PORT left as REPLACE_ME_INTERNAL_PORT) must not be
    # allowed to proceed silently into the port substitution below.
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
    R2DBSVC_APP_UNIT_SRC \
    R2DBSVC_CONTROL_UNIT_SRC \
    R2DBSVC_NGINX_CONF_SRC \
    R2DBSVC_NGINX_SITES_AVAILABLE \
    R2DBSVC_NGINX_SITES_ENABLED \
    R2DBSVC_INTERNAL_PORT \
    R2DBSVC_CONTROL_PORT \
    R2DBSVC_INSTALL_ROOT \
    R2DB_CONTROL_DSN \
; do
    require_var "$_var"
done

# Optional overrides, defaulting to the exact paths both units' own
# `EnvironmentFile=` name (deploy/systemd/r2dbsvc-{api,control}.service) --
# see the header comment above for why these are not in the required-var
# loop.
R2DBSVC_API_ENV_FILE="${R2DBSVC_API_ENV_FILE:-/etc/r2dbsvc/api.env}"
R2DBSVC_CONTROL_ENV_FILE="${R2DBSVC_CONTROL_ENV_FILE:-/etc/r2dbsvc/control.env}"

# ---------------------------------------------------------------------------
# Both-surfaces gate (supervisor ruling 2026-09-06 A10). Read FIRST, before
# any other preflight and before installing or enabling either unit -- see
# this script's own header for why: this script assumes a deployment
# standing up BOTH the application-plane and control-plane processes
# together, and cannot cleanly bring up a host that declared no control
# surface at all (that host's `r2db_api.control_main` refuses to start no
# matter what this script does). Reads `part1c_declare_surfaces.sh`'s own
# marker -- never `ops show-declarations`'s free-text output (a diagnostic
# display, not a machine contract -- M-1 below). `sudo` throughout (H-2
# discipline): a check that cannot actually run must never be read as a
# pass.
# ---------------------------------------------------------------------------
control_surface_marker="${R2DBSVC_INSTALL_ROOT}/.r2dbsvc-control-surface-declared"
if sudo test -f "$control_surface_marker"; then
    control_surface_declared=$(sudo cat "$control_surface_marker")
else
    marker_rc=$?
    if [ "$marker_rc" -eq 1 ]; then
        log "refusing to proceed: control-surface marker ${control_surface_marker} does not exist. Run part1c_declare_surfaces.sh (ledger LQ4-24 rework) first -- an older run of part1_provision_host_and_db.sh predates this marker, or surfaces were never declared -- then re-run this script."
    else
        log "refusing to proceed: cannot determine whether control-surface marker ${control_surface_marker} exists (sudo test -f exited ${marker_rc}). Fix access to ${R2DBSVC_INSTALL_ROOT} and re-run."
    fi
    exit 1
fi

case "$control_surface_declared" in
    yes|no) ;;
    *)
        log "refusing to proceed: control-surface marker ${control_surface_marker} holds an unrecognized value '${control_surface_declared}' (expected 'yes' or 'no'). Re-run part1c_declare_surfaces.sh, or correct the file by hand, then re-run this script."
        exit 1
        ;;
esac

if [ "$control_surface_declared" = "no" ]; then
    log "refusing to proceed: this host declares NO control surface (per ${control_surface_marker}). This script assumes a control surface -- a data-only host follows DEPLOYMENT_RUNBOOK.md §7's manual procedure instead (do not bring up the control unit; verify 401 for the data surface only). Aborting before either unit is installed or enabled."
    exit 1
fi

log "control-surface marker (${control_surface_marker}) declares a control surface -- proceeding with both units."

# ---------------------------------------------------------------------------
# Removed-environment-variable preflight (Q4 phase, design docs/design/
# Q4_DB_SIDE_SINGLE_TRUTH_V1.md D-1/D-2, ledger LQ4-24). Both `r2db_api.main`
# and `r2db_api.control_main` now refuse to start -- at their NEXT restart,
# not at install time -- while ANY of the four variables below is still
# defined in their own `EnvironmentFile`, whatever its value, an empty
# string included (F-1 for the two timeouts, F-2 for the two base URLs;
# POSTGRES_PROVISIONING_RUNBOOK.md §16). Checking here, before either
# `systemctl enable --now` call below, turns a deployment mistake that would
# otherwise surface as a silent restart failure into a named, actionable
# message at install time instead -- the same "fail before any change is
# made" discipline every other preflight check in this script and in
# part1_provision_host_and_db.sh already follows. Matches on the variable
# NAME only (`^[[:space:]]*VAR=`, leading whitespace tolerated because
# systemd's own `EnvironmentFile=` parser honors an indented assignment
# line the same as an unindented one -- supervisor ruling 2026-09-06 L-1),
# never the value, because F-1/F-2 fire on presence alone -- a line
# defining the variable to an empty string must still be caught.
#
# Every read below goes through `sudo` (H-2): the file is root-owned mode
# `0600` (DEPLOYMENT_RUNBOOK.md §2 step 2), normally unreadable by the
# account running this script, and a `grep`/`test` that fails with a
# permission or I/O error (`grep` rc 2, or a `test -f` that cannot even be
# evaluated) must never be read as "not found" / "does not exist" -- both
# `sudo grep`/`sudo test` calls below branch explicitly on rc so that an
# uninspectable file stops this script instead of silently passing.
# ---------------------------------------------------------------------------
reject_removed_env_vars() {
    # $1 = human label for the log line, $2 = path to an EnvironmentFile
    # that must not define any of the four Q4-removed variables.
    local label="$1" path="$2" var found=0 rc

    if sudo test -f "$path"; then
        : # exists -- fall through to the per-variable grep below.
    else
        rc=$?
        if [ "$rc" -eq 1 ]; then
            log "refusing to proceed: ${label} EnvironmentFile ${path} does not exist. Place it first (DEPLOYMENT_RUNBOOK.md §2 step 2 / §7 step 1), then re-run this script."
        else
            log "refusing to proceed: cannot determine whether ${label} EnvironmentFile ${path} exists (sudo test -f exited ${rc} -- not the ordinary 0/1 present/absent result). This script does not treat an uninspectable path as absent. Fix access to ${path} and re-run."
        fi
        exit 1
    fi

    for var in \
        R2DB_AUDIT_STATEMENT_TIMEOUT_MS \
        R2DB_AUDIT_IDLE_TIMEOUT_MS \
        R2DB_DATA_BASE_URL \
        R2DB_CONTROL_BASE_URL \
    ; do
        if sudo grep -Eq "^[[:space:]]*${var}=" "$path"; then
            log "refusing to install/start against ${label} EnvironmentFile ${path}: it still defines ${var} (Q4 phase, design D-1/D-2). This process refuses to start while it is defined at all, whatever its value -- remove the line (declare the equivalent through 'ops set-platform-timeouts'/'ops declare-surfaces' instead, POSTGRES_PROVISIONING_RUNBOOK.md §16), then re-run this script."
            found=1
        else
            rc=$?
            if [ "$rc" -ge 2 ]; then
                log "refusing to proceed: cannot inspect ${label} EnvironmentFile ${path} for ${var} (sudo grep exited ${rc} -- a permission or I/O error, not the ordinary 0/1 match/no-match result). A check that cannot run must not be treated as a pass. Fix access to ${path} and re-run."
                exit 1
            fi
        fi
    done
    if [ "$found" -ne 0 ]; then
        exit 1
    fi
    log "${label} EnvironmentFile ${path} carries none of the four removed Q4 variables."
}

reject_removed_env_vars "application-plane" "${R2DBSVC_API_ENV_FILE}"
reject_removed_env_vars "control-plane" "${R2DBSVC_CONTROL_ENV_FILE}"

# ---------------------------------------------------------------------------
# Control-surface / R2DB_CONTROL_PLANE_STATUS consistency preflight (F-6,
# supervisor ruling 2026-09-06 H-1). By this point the both-surfaces gate
# above has already confirmed `control_surface_declared=yes` -- the ONLY
# remaining F-6 direction this script can still reach is "declared, but
# api.env claims unavailable" (the "declared=no but api.env claims a
# surface" direction is now caught by that same gate, unconditionally,
# BEFORE this section runs at all -- ruling A10; the two directions are no
# longer symmetric in this script the way `r2db_api.platform_declarations._
# f6_forward_message`/`_f6_reverse_message` are symmetric at the real
# process' own startup check, since this script refuses a data-only host
# outright rather than letting it reach its own, narrower F-6 comparison).
# A mismatch here is exactly the condition the application-plane process'
# own F-6 startup check would refuse on at its NEXT restart -- catching it
# before `systemctl enable --now` turns that into a named, actionable
# message at install time instead of a unit that enables cleanly today and
# then fails on its next restart.
# ---------------------------------------------------------------------------
normalize_env_value() {
    # $1 = the raw text following the first `=` on a matched
    # `VAR=...` EnvironmentFile line. Mirrors systemd's own EnvironmentFile
    # value parsing (systemd.exec(5)) just enough to stop this preflight's
    # own string comparison from disagreeing with what the real process
    # actually reads (supervisor ruling 2026-09-06 A7/A8): strips
    # leading/trailing whitespace around the value, then strips one layer
    # of matching `"..."`/`'...'` quoting if the (already-trimmed) value is
    # wrapped end-to-end in one style. Before this normalization, `VAR=
    # unavailable` (a space after `=`) compared as literally " unavailable"
    # -- never equal to the bare word this script checks for, so the
    # mismatch this preflight exists to catch silently passed while the
    # real process (which DOES strip that space) still refused at F-6 (A8);
    # and `VAR="unavailable"` (legitimate systemd quoting) compared as
    # literally `"unavailable"` with the quote characters included, an
    # equally wrong result in the other direction (A7).
    local v="$1"
    v="${v#"${v%%[![:space:]]*}"}"
    v="${v%"${v##*[![:space:]]}"}"
    case "$v" in
        \"*\") v="${v#\"}"; v="${v%\"}" ;;
        \'*\') v="${v#\'}"; v="${v%\'}" ;;
    esac
    printf '%s' "$v"
}

control_plane_status_from_env_file() {
    # $1 = path to the application-plane EnvironmentFile. Prints the value
    # `r2db_api.main` itself would read for R2DB_CONTROL_PLANE_STATUS,
    # including its own default (`unavailable`) when the variable is
    # absent. Uses `sudo grep` throughout (H-2 discipline, same as
    # reject_removed_env_vars() above): a check that cannot run must not be
    # silently treated as a pass, so an rc >= 2 here aborts the script
    # rather than falling through as "absent".
    local path="$1" line rc=0
    line=$(sudo grep -E "^[[:space:]]*R2DB_CONTROL_PLANE_STATUS=" "$path" | tail -n1) || rc=$?
    if [ "$rc" -ge 2 ]; then
        log "refusing to proceed: cannot inspect ${path} for R2DB_CONTROL_PLANE_STATUS (sudo grep exited ${rc} -- a permission or I/O error, not the ordinary 0/1 match/no-match result). Fix access to ${path} and re-run."
        exit 1
    fi
    if [ -z "$line" ]; then
        printf 'unavailable'
        return
    fi
    normalize_env_value "${line#*=}"
}

control_plane_status=$(control_plane_status_from_env_file "${R2DBSVC_API_ENV_FILE}")

if [ "$control_plane_status" = "unavailable" ]; then
    log "refusing to proceed: surfaces.control is declared (per ${control_surface_marker}) but R2DB_CONTROL_PLANE_STATUS is 'unavailable' in ${R2DBSVC_API_ENV_FILE} (contract 1.6.0: a deployment declaring control_plane unavailable omits surfaces.control). The surfaces row is shared by BOTH processes: re-declaring with '--no-control' removes the control declaration for the control-plane process too, and that process will then fail to start (F-3). Unless this deployment really offers no control surface, set R2DB_CONTROL_PLANE_STATUS=enabled in ${R2DBSVC_API_ENV_FILE} (DEPLOYMENT_RUNBOOK.md §7 step 2) before re-running this script; if it genuinely has no control surface, re-run part1c_declare_surfaces.sh with R2DBSVC_CONTROL_BASE_URL unset (marker-stale finding: re-declaring updates the SAME marker this gate just read, unlike a bare hand-run 'ops declare-surfaces' invocation) and follow DEPLOYMENT_RUNBOOK.md §7's manual data-only procedure instead of this script."
    exit 1
fi

log "control-surface declaration (control_surface_declared=${control_surface_declared}) agrees with R2DB_CONTROL_PLANE_STATUS (${control_plane_status}) in ${R2DBSVC_API_ENV_FILE}."

# ---------------------------------------------------------------------------
# Placeholder guard. Runs against the SOURCE files this script is about to
# install -- before substitution, every one of them legitimately still
# contains REPLACE_ME_INTERNAL_PORT / REPLACE_ME_CONTROL_PORT (that is the
# point of a template); this guard runs again AFTER substitution against
# the rendered copy this script actually installs, where none of those
# tokens may remain.
# ---------------------------------------------------------------------------
reject_placeholder_in_file() {
    # $1 = path to a rendered (post-substitution) file that must contain no
    # unresolved placeholder token.
    local path="$1"
    if grep -Eq 'REPLACE_ME[A-Z0-9_]*|<[A-Z0-9_]+>' "$path"; then
        log "refusing to install ${path}: it still contains an unresolved REPLACE_ME_*/<UPPER_SNAKE> placeholder. Substitute every real value first (ports, EnvironmentFile paths per DEPLOYMENT_RUNBOOK.md §2 step 3 / §7)."
        exit 1
    fi
}

render_port_substitution() {
    # $1 = source file, $2 = destination file. Only the two known port
    # placeholders are substituted -- this script does not attempt to
    # resolve any other placeholder (server_name, certificate paths,
    # EnvironmentFile ownership) on the operator's behalf; those are
    # filled in by hand per the runbook, exactly as before this script
    # existed.
    local src="$1" dst="$2"
    sed \
        -e "s/REPLACE_ME_INTERNAL_PORT/${R2DBSVC_INTERNAL_PORT}/g" \
        -e "s/REPLACE_ME_CONTROL_PORT/${R2DBSVC_CONTROL_PORT}/g" \
        "$src" >"$dst"
}

# ---------------------------------------------------------------------------
# Render + validate ALL THREE files first, before any `sudo cp` (or any
# other change) runs. Rendering the app unit, starting it, and only THEN
# discovering the control unit or the nginx conf still holds an unresolved
# placeholder would leave a half-installed deployment (one unit live,
# nothing else) for the operator to clean up by hand -- validating all
# three up front means this script either makes none of its changes or
# proceeds past this point with every rendered file already known-good.
# ---------------------------------------------------------------------------
app_unit_rendered=$(mktemp)
control_unit_rendered=$(mktemp)
nginx_conf_rendered=$(mktemp)
trap 'rm -f "$app_unit_rendered" "$control_unit_rendered" "$nginx_conf_rendered"' EXIT

render_port_substitution "${R2DBSVC_APP_UNIT_SRC}" "$app_unit_rendered"
render_port_substitution "${R2DBSVC_CONTROL_UNIT_SRC}" "$control_unit_rendered"
render_port_substitution "${R2DBSVC_NGINX_CONF_SRC}" "$nginx_conf_rendered"

reject_placeholder_in_file "$app_unit_rendered"
reject_placeholder_in_file "$control_unit_rendered"
reject_placeholder_in_file "$nginx_conf_rendered"

# ---------------------------------------------------------------------------
# Step 1 -- install and start the application-plane unit
# (DEPLOYMENT_RUNBOOK.md §2 steps 3-4)
# ---------------------------------------------------------------------------
log "installing r2dbsvc-api.service (port ${R2DBSVC_INTERNAL_PORT})"
sudo cp "$app_unit_rendered" /etc/systemd/system/r2dbsvc-api.service

# ---------------------------------------------------------------------------
# Step 2 -- install and start the control-plane unit
# (DEPLOYMENT_RUNBOOK.md §7 "Deployment steps", step 3 -- renumbered ahead
# of the env-var step by the H-1(c) rework, supervisor ruling 2026-09-06)
# ---------------------------------------------------------------------------
log "installing r2dbsvc-control.service (port ${R2DBSVC_CONTROL_PORT})"
sudo cp "$control_unit_rendered" /etc/systemd/system/r2dbsvc-control.service

sudo systemctl daemon-reload
sudo systemctl enable --now r2dbsvc-api.service
sudo systemctl enable --now r2dbsvc-control.service
sudo systemctl status --no-pager r2dbsvc-api.service
sudo systemctl status --no-pager r2dbsvc-control.service

# ---------------------------------------------------------------------------
# Step 3 -- nginx 8443 listener with both locations
# (DEPLOYMENT_RUNBOOK.md §2 step 5, extended per §7's own control-plane
# proxy block)
# ---------------------------------------------------------------------------
log "installing r2dbsvc-api-8443.conf"
sudo cp "$nginx_conf_rendered" "${R2DBSVC_NGINX_SITES_AVAILABLE}/r2dbsvc-api-8443.conf"
sudo ln -sf "${R2DBSVC_NGINX_SITES_AVAILABLE}/r2dbsvc-api-8443.conf" "${R2DBSVC_NGINX_SITES_ENABLED}/r2dbsvc-api-8443.conf"
sudo nginx -t
sudo systemctl reload nginx

# ---------------------------------------------------------------------------
# Step 4 -- verify both surfaces actually fail closed (401) with no
# credential (DEPLOYMENT_RUNBOOK.md §2 step 6 item 1, §7 step 5's own "no
# no-credential 200 variant" note for the control plane). This reads the
# real HTTP status code and FAILS the script if it is not exactly 401 --
# a backend that answers 200 (fail-open) or errors out entirely (503, no
# process listening) must stop this script here, not be reported as a
# successful "part 2 complete".
# ---------------------------------------------------------------------------
verify_401() {
    # $1 = human label for the log line, $2 = URL to probe. `|| true`
    # (supervisor ruling 2026-09-06 L-2) because a connection-refused (no
    # process listening) makes curl exit non-zero -- under `set -e`, an
    # unguarded `code=$(curl ...)` would abort this script right here with
    # curl's own error, never reaching the "answered ${code}" diagnostic
    # below. With `-w '%{http_code}'`, curl still writes `000` on a failed
    # connection regardless of its own exit status, so guarding the exit
    # status with `|| true` still lets the `[ "$code" != "401" ]` check
    # below catch and report it correctly.
    local label="$1" url="$2" code
    code=$(curl -sk -o /dev/null -w '%{http_code}' "$url" || true)
    if [ "$code" != "401" ]; then
        log "FAILED: ${label} (${url}) answered ${code}, expected 401. Aborting -- do not treat this deployment as verified."
        exit 1
    fi
    log "${label} (${url}) answered 401 as expected."
}

log "verifying application plane (expect 401)"
verify_401 "application plane" "http://127.0.0.1:${R2DBSVC_INTERNAL_PORT}/v1/capabilities"

log "verifying control plane (expect 401)"
verify_401 "control plane" "http://127.0.0.1:${R2DBSVC_CONTROL_PORT}/control/v1/capabilities"

# ---------------------------------------------------------------------------
# Step 5 -- show the Q4 platform declarations (diagnostic display only) and
# verify the per-application platform-upgrade ledger this deployment
# depends on (POSTGRES_PROVISIONING_RUNBOOK.md §16/§17, design D-1/D-2/D-3/
# D-5, ledger LQ4-24). Both units above are already running by this point.
#
# `ops show-declarations` is NOT a pass/fail check (supervisor ruling
# 2026-09-06 M-1): it is the same free-text diagnostic
# POSTGRES_PROVISIONING_RUNBOOK.md §16 calls "the one command to run when
# something looks inconsistent" -- its output is shown below for a human to
# read, and its own exit code is deliberately never inspected (`|| rc=$?`
# only to keep `set -e` from killing this script on it, never to gate
# anything on the result). `ops upgrade-status` is the ONLY verification
# here: a fresh check that a pending per-application upgrade is caught HERE,
# not discovered later as an F-12 SERVICE_UNAVAILABLE against a real
# request. Both commands run on `R2DB_CONTROL_DSN` (the provision role);
# neither running process holds that credential (SI-02).
# ---------------------------------------------------------------------------
OPS=("${R2DBSVC_INSTALL_ROOT}/.venv/bin/python" -m r2db_api.ops)

log "showing platform declarations (ops show-declarations; diagnostic display only -- not used for pass/fail here)"
declarations_rc=0
env R2DB_CONTROL_DSN="${R2DB_CONTROL_DSN}" "${OPS[@]}" show-declarations || declarations_rc=$?
if [ "$declarations_rc" -ne 0 ]; then
    log "note: ops show-declarations exited ${declarations_rc} -- shown above for information only. The authoritative check is ops upgrade-status below."
fi

log "checking per-application platform-upgrade ledger (ops upgrade-status)"
upgrade_status_rc=0
env R2DB_CONTROL_DSN="${R2DB_CONTROL_DSN}" "${OPS[@]}" upgrade-status || upgrade_status_rc=$?
if [ "$upgrade_status_rc" -ne 0 ]; then
    log "FAILED: ops upgrade-status exited ${upgrade_status_rc} (0 = nothing pending expected here). Do not treat this deployment as verified -- run 'python -m r2db_api.ops upgrade-applications --lock-timeout <value>' (POSTGRES_PROVISIONING_RUNBOOK.md §17), then re-run this check."
    exit 1
fi
log "ops upgrade-status: nothing pending."

# R2DB_CONTROL_PLANE_STATUS is intentionally NOT set here (supervisor
# ruling 2026-09-06 H-1): the F-6 preflight above already required it to
# agree with the declared control surface BEFORE either unit was enabled
# (DEPLOYMENT_RUNBOOK.md §7 step 2 now states this ordering), so by the
# time this script reaches "part 2 complete" api.env is already correct --
# there is no longer a step to defer until after the control plane is
# reachable.
#
# Only one closing message remains (supervisor ruling 2026-09-06 A10 --
# cleanup of the previously-unreachable "this deployment declares no
# control surface" branch here): the both-surfaces gate at the top of this
# script already exits 1, before either unit is installed or enabled,
# whenever control_surface_declared is "no" -- so by this point in the
# script it is unconditionally "yes", and a second branch for "no" here
# could never actually run.
log "part 2 complete (control-surface declaration and R2DB_CONTROL_PLANE_STATUS=enabled already agreed before this run, per the F-6 preflight above). Next: bootstrap the first control credential (part1b_control_credential_reset.sh) if not already done (DEPLOYMENT_RUNBOOK.md §7 step 4)."
