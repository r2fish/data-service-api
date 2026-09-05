#!/usr/bin/env bash
# r2dbsvc stage-1 install, part 1b -- control-credential bootstrap/reset
# ritual (the only way a role=control credential is ever created or
# recovered, design "案B" -- no /control/v1 endpoint can do this).
#
# Companion documents: r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md §12
# (bootstrap/reset, the exact CLI shapes this script wraps) and §13
# (lockout paths). Recovery scenario this script targets is recorded in
# docs/work-orders/DEPLOY_PHASE6_20260904.md §8 item 10: an operator lost
# the printed bootstrap credential before it reached the secret manager,
# and recovered with `ops.py reset --confirm RESET_CONTROL_CREDENTIALS`.
# This script automates that same two attempts -- bootstrap first (the
# platform database's first-ever control credential), falling back to the
# gated reset ritual ONLY if bootstrap's own stderr shows it refused with
# `error: CONFLICT:` (control_plane.py's `fail("CONFLICT", ...)` at its
# bootstrap-ceremony gate, surfaced by ops.py's `main()` as `error:
# CONFLICT: <message>` on exit 1 -- see both call sites below for exactly
# what that looks like). Any OTHER non-zero exit from bootstrap (a
# `psycopg.Error`, a missing/invalid env var, or anything else ops.py's own
# `main()` reports) is NOT a signal to fall back to reset -- this script
# prints that stderr verbatim and stops, rather than requiring the operator
# to know in advance which of the two rituals applies to this platform
# database. Falling back to reset is also gated behind an explicit operator
# opt-in (`R2DBSVC_ALLOW_CONTROL_RESET=1`, checked below) even once a
# genuine CONFLICT is confirmed: reset revokes every existing control
# credential on this platform database, and a script that ran it
# automatically the instant bootstrap merely exited non-zero would turn any
# unrelated bootstrap failure mode into a destructive action this operator
# never asked for.
#
# This script is a synthetic template, written from the runbook above -- it
# was not recovered from any real host. Never place a real DSN, pepper, or
# issued secret inside this file itself (CLAUDE.md's Public Repository
# Security Gate); the credential this script prints is exactly as
# ONE-TIME-VISIBLE as `python -m r2db_api.ops` itself makes it -- pipe this
# script's own stdout straight into your secret manager's own input, or
# redirect it to a 0600 file you `shred -u` immediately after transcribing
# it, and never leave it in shell history (POSTGRES_PROVISIONING_RUNBOOK.md
# §12's own non-permanence note).
#
# Usage:
#   R2DBSVC_INSTALL_ROOT=/opt/r2dbsvc/r2db-api \
#   R2DB_CONTROL_DSN=... \
#   R2DB_CONTROL_CREDENTIAL_PEPPER=... \
#   R2DB_CREDENTIAL_PEPPER=... \
#     ./part1b_control_credential_reset.sh
#
# R2DBSVC_ALLOW_CONTROL_RESET=1 must ALSO be set (in addition to the four
# variables above) before this script will run the reset ritual after a
# confirmed CONFLICT -- it is deliberately not part of the required-variable
# loop below, since bootstrap succeeding (no existing control credential)
# never needs it at all; see the reset branch further down.

set -euo pipefail

log() {
    printf '[part1b] %s\n' "$1" >&2
}

require_var() {
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
    R2DB_CONTROL_DSN \
    R2DB_CONTROL_CREDENTIAL_PEPPER \
    R2DB_CREDENTIAL_PEPPER \
; do
    require_var "$_var"
done

# R-2 (POSTGRES_PROVISIONING_RUNBOOK.md §12): both rituals refuse to run at
# all if the two pepper values are equal. Checking it here, before invoking
# either subcommand, turns that refusal into a named, actionable message
# instead of whatever exit path the CLI itself takes for it.
if [ "${R2DB_CONTROL_CREDENTIAL_PEPPER}" = "${R2DB_CREDENTIAL_PEPPER}" ]; then
    log "R2DB_CONTROL_CREDENTIAL_PEPPER must differ from R2DB_CREDENTIAL_PEPPER (R-2). Aborting before any change is made."
    exit 1
fi

OPS=("${R2DBSVC_INSTALL_ROOT}/.venv/bin/python" -m r2db_api.ops)

# Bootstrap's own stdout (the one-time-visible issued credential, on
# success) must still reach this script's own stdout uncaptured -- fd 3
# below is this script's original stdout, saved so the command
# substitution can capture ONLY stderr into $bootstrap_stderr while stdout
# passes through live.
log "attempting bootstrap (only succeeds if no control_credentials row exists yet)"
exec 3>&1
bootstrap_rc=0
bootstrap_stderr=$(env \
    R2DB_CONTROL_DSN="${R2DB_CONTROL_DSN}" \
    R2DB_CONTROL_CREDENTIAL_PEPPER="${R2DB_CONTROL_CREDENTIAL_PEPPER}" \
    "${OPS[@]}" bootstrap 2>&1 1>&3) || bootstrap_rc=$?
exec 3>&-

if [ "$bootstrap_rc" -eq 0 ]; then
    log "bootstrap succeeded -- this was the platform database's first-ever control credential. Store the printed credential_id/secret in your secret manager now; it will not be shown again."
    exit 0
fi

# ops.py's `main()` prints exactly `error: CONFLICT: <message>` to stderr
# and exits 1 for this specific refusal (control_plane.py's
# `bootstrap_control_credential()` calling `fail("CONFLICT", "a control
# credential already exists; bootstrap runs at most once -- use `reset` to
# recover", status=409)`, caught by ops.py's own `except FoundationError`
# arm). ANY other failure -- a `psycopg.Error` (`error: database operation
# failed: ...`), a missing/invalid env var caught before the DB call, or any
# other `FoundationError` code -- is NOT this refusal, and must not fall
# through to reset.
case "$bootstrap_stderr" in
    *'error: CONFLICT:'*)
        log "bootstrap refused with CONFLICT (ops printed: ${bootstrap_stderr}) -- a control credential already exists on this platform database."
        ;;
    *)
        log "bootstrap failed for a reason other than CONFLICT; NOT falling back to reset. ops's own stderr was:"
        printf '%s\n' "$bootstrap_stderr" >&2
        exit 1
        ;;
esac

# Reset is destructive (it revokes every existing control credential on this
# platform database, atomically reissuing exactly one) -- confirming a
# genuine CONFLICT above is not by itself enough to run it. An operator who
# only wants to know whether this platform database already has a control
# credential (e.g. re-running this script against the wrong target by
# mistake) must not have this script silently revoke it for them.
if [ "${R2DBSVC_ALLOW_CONTROL_RESET:-}" != "1" ]; then
    log "a control credential already exists on this platform database. Running reset revokes ALL existing control credentials and issues exactly one new one. To proceed, set R2DBSVC_ALLOW_CONTROL_RESET=1 and re-run this script."
    exit 1
fi

log "R2DBSVC_ALLOW_CONTROL_RESET=1 -- proceeding to the reset ritual (POSTGRES_PROVISIONING_RUNBOOK.md §12)."

# Step 1: declaration only. This first invocation is refused (exit code 2)
# and touches nothing -- it exists so an operator who does not already know
# the fixed confirmation phrase gets it from the CLI itself rather than
# from a hardcoded copy in this script (structured.RESET_CONTROL_
# CREDENTIALS's own docstring explains why the phrase is a fixed constant
# here, unlike a re-creatable named target).
set +e
declaration=$(env \
    R2DB_CONTROL_DSN="${R2DB_CONTROL_DSN}" \
    R2DB_CONTROL_CREDENTIAL_PEPPER="${R2DB_CONTROL_CREDENTIAL_PEPPER}" \
    "${OPS[@]}" reset 2>&1 1>/dev/null)
declaration_rc=$?
set -e

# ops.py's `_require_cli_confirmation()` raises `SystemExit(2)` directly
# (bypassing `main()`'s ordinary `FoundationError` -> exit-1 handling) for
# exactly the "declaration only, nothing touched yet" refusal this step
# relies on. Any other exit code here means the declaration step did NOT
# behave as this script assumes (e.g. a DB/env error before the
# confirmation gate, or ops's own contract changing underneath this
# script) -- proceeding to hardcode the confirmation phrase below would be
# wrong in that case, so this must stop rather than fall through.
if [ "$declaration_rc" -ne 2 ]; then
    log "declaration step exited $declaration_rc, expected 2 (ops.py's fixed exit code for the confirmation-required refusal); NOT proceeding to confirm. ops's own output was:"
    printf '%s\n' "$declaration" >&2
    exit 1
fi

log "declaration step output (JSON, no state changed yet): ${declaration}"

# The declared phrase is a fixed constant in this implementation
# (RESET_CONTROL_CREDENTIALS, per POSTGRES_PROVISIONING_RUNBOOK.md §12) --
# used literally here rather than parsed out of the JSON above, since this
# script's own dependency footprint is deliberately zero (no JSON parser).
# If a future revision of the ritual changes this phrase, the declaration
# step's own stderr output above is the authoritative source to update this
# script from.
log "confirming reset with the declared phrase RESET_CONTROL_CREDENTIALS -- this REVOKES every existing control credential and issues exactly one new one, atomically."
env \
    R2DB_CONTROL_DSN="${R2DB_CONTROL_DSN}" \
    R2DB_CONTROL_CREDENTIAL_PEPPER="${R2DB_CONTROL_CREDENTIAL_PEPPER}" \
    "${OPS[@]}" reset --confirm RESET_CONTROL_CREDENTIALS

log "reset complete. Store the printed credential_id/secret in your secret manager now; it will not be shown again. The credential is must_rotate=true -- complete a real rotation before relying on it for anything beyond GET /control/v1/capabilities and self-rotate."
