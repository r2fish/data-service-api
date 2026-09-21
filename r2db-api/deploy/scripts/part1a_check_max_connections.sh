#!/usr/bin/env bash
# r2dbsvc stage-1 install, part 1a -- verify `max_connections` (minus
# `superuser_reserved_connections`) leaves this deployment enough headroom
# BEFORE `0013_role_connection_limits.sql` is applied (design D-2, work
# order docs/work-orders/WORK_ORDER_R66_DEPLOY_0013_AND_PROVISION_ROLE_
# TIMEOUT_V1.md §1.4).
#
# WHY A SEPARATE SCRIPT (design D-2's own "置き場" rationale): a pytest run
# can start THIS script directly, with a stub `psql` placed on `PATH`, to
# exercise its refusal/pass logic without any of the `sudo useradd`/`sudo
# mkdir`/venv-creation steps `part1_provision_host_and_db.sh` itself does
# before Step 3 -- there is no way to drive that script all the way to its
# own migration steps from a test at all. This script has no such
# dependency: it only ever reads `SHOW max_connections`/`SHOW superuser_
# reserved_connections` and counts `r2dbsvc_registry.applications` rows,
# over the SAME `R2DBSVC_CONTROL_DSN` `part1_provision_host_and_db.sh`
# already validates and passes through.
#
# WHERE THIS RUNS (design D-2's own "位置"): called from
# `part1_provision_host_and_db.sh` right after `0002_provisioning_
# functions.sql` (the first point `r2dbsvc_control` and the not-yet-
# populated `r2dbsvc_registry.applications` table both exist) and before
# `0005_credential_store.sql` -- a host that refuses here has applied only
# `0001`/`0002`, both idempotent, so re-running the whole script later is
# safe; nothing past `0005` is ever applied to a host this check rejects.
#
# WHAT "required" MEANS (design D-2's own "必要数の既定"): `98 + 72 x (N +
# 1)`, N = the number of ALREADY-PROVISIONED applications in
# `r2dbsvc_registry.applications` (`runtime_role IS NOT NULL AND
# developer_role IS NOT NULL` -- a row `register_application` creates but
# `begin_provision_application`/`finish_provision_application` has not yet
# finished provisioning still has both columns NULL, `0006_control_plane_
# http.sql`'s own `DROP NOT NULL`). `98` = platform baseline (`r2dbsvc_api`
# 68 + `r2dbsvc_controlplane` 20 + `r2dbsvc_control` 5 + `r2dbsvc_
# auditreader` 5, `0013_role_connection_limits.sql`'s/`0001`'s/`0007`'s own
# `CONNECTION LIMIT` literals). `72` = one application's own runtime (36) +
# developer (36) roles, same migration. `+ 1` accounts for the application
# THIS run of `part1_provision_host_and_db.sh` itself is about to
# provision (`0003`, later in that script) -- `r2db-api/tests/
# test_deploy_script_migrations.py` recomputes both `98` and `72` from the
# same migration files and pins them against the two literals below.
#
# `98 + 72 x (N + 1)` is a CONSERVATIVE STAND-IN (runbook §4's own "One
# formula, not three"), never the real PostgreSQL requirement itself --
# an operator who has derived the real figure from that section's own
# formula sets `R2DBSVC_EXPECTED_PEAK_CONNECTIONS` (a positive integer) to
# use it instead of this script's own default (design D-2's own "運用者の
# 導出値"). `ResourceLimits.concurrency` is fixed on this peer -- no env
# var overrides it anywhere in this peer's own composition roots
# (`r2db_api.ops`'s own module-level fact, quoted verbatim in the work
# order) -- so `R2DB_PLATFORM_POOL_SIZE` is the only knob this peer
# actually exposes for lowering real peak demand below this script's own
# conservative default.
#
# This script is a synthetic template, written from the runbook and the
# work order above -- it was not recovered from any real host. Every
# path, port, and account name it references is illustrative or a named
# environment variable; substitute real values only via the environment
# when actually running this script on a target host. Never place a real
# secret, DSN, or hostname inside this file itself (CLAUDE.md's Public
# Repository Security Gate).
#
# Usage:
#   R2DBSVC_CONTROL_DSN=... \
#   [R2DBSVC_EXPECTED_PEAK_CONNECTIONS=<positive integer>] \
#     ./part1a_check_max_connections.sh
#
# `R2DBSVC_EXPECTED_PEAK_CONNECTIONS` is OPTIONAL, exactly like
# `R2DBSVC_CONTROL_BASE_URL` in `part1_provision_host_and_db.sh`/
# `part1c_declare_surfaces.sh`: unset means "use this script's own
# conservative default", a valid and expected choice, not an operator
# oversight.

set -euo pipefail

log() {
    printf '[part1a] %s\n' "$1" >&2
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

require_var R2DBSVC_CONTROL_DSN

is_positive_integer() {
    # Design D-2's own refusal set for R2DBSVC_EXPECTED_PEAK_CONNECTIONS:
    # empty, zero, negative, non-numeric are all rejected -- including an
    # EXPLICITLY EMPTY value (code review 1 高2: reachable only because the
    # caller below tests `${R2DBSVC_EXPECTED_PEAK_CONNECTIONS+x}`, not
    # `${R2DBSVC_EXPECTED_PEAK_CONNECTIONS:-}` -- the former is true the
    # moment the variable is SET, even to "", while the latter is
    # indistinguishable from unset in that same case; only the former lets
    # an explicitly-empty override actually reach this function instead of
    # silently taking the default-required path below). `$((10#$1))`
    # forces base-10 arithmetic so a value like "008" is never misread as
    # an invalid octal literal by plain bash arithmetic.
    local value="$1"
    case "$value" in
        ''|*[!0-9]*)
            return 1
            ;;
    esac
    [ "$((10#$value))" -gt 0 ]
}

# Platform baseline (design D-2): r2dbsvc_api 68 (0013_role_connection_
# limits.sql:108) + r2dbsvc_controlplane 20 (0013:109) + r2dbsvc_control 5
# (0001_bootstrap_control_plane.sql:96) + r2dbsvc_auditreader 5
# (0007_application_audit.sql:194) = 98. Per-application baseline: runtime
# 36 + developer 36 (0013:131-132/181/185) = 72.
PLATFORM_BASELINE_CONNECTIONS=98
PER_APPLICATION_CONNECTIONS=72

max_connections=$(psql "${R2DBSVC_CONTROL_DSN}" -tAc "SHOW max_connections")
superuser_reserved_connections=$(psql "${R2DBSVC_CONTROL_DSN}" -tAc "SHOW superuser_reserved_connections")

# `r2dbsvc_registry.applications` does not exist yet on a platform database
# this script has never touched at all (this check runs right after
# `0002`, which is the migration that creates it -- but a re-run against
# an already-provisioned platform database always finds it present).
# `to_regclass` returns SQL NULL (an empty string over `-tAc`) rather than
# erroring when the relation is absent, the same pattern `0013_role_
# connection_limits.sql`'s own per-application loop and this repository's
# own static tests already rely on.
applications_regclass=$(psql "${R2DBSVC_CONTROL_DSN}" -tAc "SELECT to_regclass('r2dbsvc_registry.applications')")
if [ -z "$applications_regclass" ]; then
    provisioned_applications=0
else
    provisioned_applications=$(psql "${R2DBSVC_CONTROL_DSN}" -tAc \
        "SELECT count(*) FROM r2dbsvc_registry.applications WHERE runtime_role IS NOT NULL AND developer_role IS NOT NULL")
fi

if [ -n "${R2DBSVC_EXPECTED_PEAK_CONNECTIONS+x}" ]; then
    if ! is_positive_integer "${R2DBSVC_EXPECTED_PEAK_CONNECTIONS}"; then
        log "refusing to proceed: R2DBSVC_EXPECTED_PEAK_CONNECTIONS (${R2DBSVC_EXPECTED_PEAK_CONNECTIONS}) must be a positive integer (max_connections read as ${max_connections}, superuser_reserved_connections read as ${superuser_reserved_connections}, already-provisioned applications N=${provisioned_applications}). See r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md §4 for how to derive a real value, or unset R2DBSVC_EXPECTED_PEAK_CONNECTIONS to use this script's own conservative default. Aborting before 0005 runs."
        exit 1
    fi
    required_connections=$((10#${R2DBSVC_EXPECTED_PEAK_CONNECTIONS}))
else
    required_connections=$((PLATFORM_BASELINE_CONNECTIONS + PER_APPLICATION_CONNECTIONS * (provisioned_applications + 1)))
fi

available_connections=$((max_connections - superuser_reserved_connections))

if [ "$available_connections" -lt "$required_connections" ]; then
    log "refusing to proceed: max_connections (${max_connections}) minus superuser_reserved_connections (${superuser_reserved_connections}) = ${available_connections}, below the required ${required_connections} connections (platform baseline ${PLATFORM_BASELINE_CONNECTIONS} + per-application ${PER_APPLICATION_CONNECTIONS} x (already-provisioned applications N=${provisioned_applications} + 1 this run)). See r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md §4 to derive this deployment's real peak connection demand, or set R2DBSVC_EXPECTED_PEAK_CONNECTIONS to override this conservative default. Aborting before 0005 runs."
    exit 1
fi

log "max_connections (${max_connections}) minus superuser_reserved_connections (${superuser_reserved_connections}) = ${available_connections}, at least the required ${required_connections} (N=${provisioned_applications} already-provisioned applications). Proceeding."
