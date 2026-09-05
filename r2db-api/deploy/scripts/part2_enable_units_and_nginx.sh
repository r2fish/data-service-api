#!/usr/bin/env bash
# r2dbsvc stage-1 install, part 2 -- install/enable both systemd units
# (application plane + control plane) and the nginx 8443 listener, then
# verify both surfaces answer fail-closed (401) with no credential.
#
# Companion documents: r2db-api/deploy/DEPLOYMENT_RUNBOOK.md §2 steps 3-6
# (application plane) and §7 (control-plane addition, "mirrors §2 above,
# for the second unit"). This script is that second unit's install steps,
# made concrete -- §7 previously only described them in prose.
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
#     ./part2_enable_units_and_nginx.sh

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
; do
    require_var "$_var"
done

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
# (DEPLOYMENT_RUNBOOK.md §7 "Deployment steps", step 2)
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
    # $1 = human label for the log line, $2 = URL to probe.
    local label="$1" url="$2" code
    code=$(curl -sk -o /dev/null -w '%{http_code}' "$url")
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

log "part 2 complete. Next: bootstrap the first control credential (part1b_control_credential_reset.sh) if not already done, then set R2DB_CONTROL_PLANE_STATUS=enabled in api.env and restart r2dbsvc-api.service (DEPLOYMENT_RUNBOOK.md §7 step 3)."
