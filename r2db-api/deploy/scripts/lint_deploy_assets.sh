#!/usr/bin/env bash
# Deploy-asset lint -- checks the templates under r2db-api/deploy/ for
# syntactic validity without ever running an actual deployment step.
#
# Phase 7 WP-3 (r2db-api/deploy/ reproducibility). WP-2's own
# `.github/workflows/ci.yml` is not yet landed in this repository, so the
# supervisor directed that the lint body live in this script and be called
# from the CI side once that workflow exists, rather than waiting on it --
# a deviation from work order WORK_ORDER_PHASE7_EVIDENCE_AND_PUBLICATION_
# V1.md §2 WP-3's own listed deliverable 6 / completion condition 9
# ("the CI job's own step contents"), ruled by the supervisor rather than
# decided by this implementation.
#
# Four checks:
#
#   1. `systemd-analyze verify`  -- both systemd units.
#   2. `nginx -t`                -- the nginx example, against a temporary
#                                    copy with every REPLACE_ME_* port
#                                    placeholder substituted for a synthetic
#                                    value, AND `ssl_certificate`/
#                                    `ssl_certificate_key` substituted for a
#                                    freshly generated, throwaway self-signed
#                                    cert/key pair. Substitution here is not
#                                    limited to ports: the template's own
#                                    illustrative certificate paths
#                                    (/etc/letsencrypt/...) do not exist on
#                                    whatever host runs this lint, and
#                                    `nginx -t` fails closed (not merely a
#                                    warning) if the files named by
#                                    `ssl_certificate`/`ssl_certificate_key`
#                                    are absent -- so both substitutions are
#                                    required for this check to exercise the
#                                    directive shapes at all, not only the
#                                    port numbers.
#   3. `bash -n`                 -- every operator script under
#                                    deploy/scripts/, plus `shellcheck` if
#                                    it happens to be installed.
#   4. ExecStart non-vacuity     -- greps each systemd unit's own
#                                    `ExecStart=` line for the exact uvicorn
#                                    module target this WP claims it points
#                                    at, and confirms that module file
#                                    actually exists in this checkout.
#                                    `systemd-analyze verify` only checks a
#                                    unit file's own syntax; it does not
#                                    know or care whether `r2db_api.
#                                    control_main:app` names a module this
#                                    repository actually ships, so a unit
#                                    whose ExecStart silently drifted to a
#                                    renamed or deleted module would still
#                                    pass check 1. This check always runs
#                                    (no external tool dependency).
#
# --require-tools mode: without this flag, an absent `systemd-analyze` or
# `nginx` (or `openssl`, needed to generate the throwaway cert/key for check
# 2) is reported SKIPPED and does NOT make this script exit non-zero on its
# own -- a local development machine (e.g. macOS) may lack them, and their
# absence is not evidence the asset they would have checked is wrong. This
# script's own CI caller is expected to run with `--require-tools`, where
# the same absent-tool condition is instead a FAIL: a CI job that silently
# skips the one check it exists to run would report green having verified
# nothing. `bash -n` and check 4 have no absence branch either way -- they
# always run, using this script's own shell and `grep`.
#
# Exit code: 0 only if every check that actually ran (or, under
# --require-tools, every check at all) passed.

set -euo pipefail

require_tools=0
for arg in "$@"; do
    case "$arg" in
        --require-tools)
            require_tools=1
            ;;
        *)
            printf 'unknown argument: %s\n' "$arg" >&2
            exit 2
            ;;
    esac
done

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
DEPLOY_DIR="${REPO_ROOT}/r2db-api/deploy"
SRC_DIR="${REPO_ROOT}/r2db-api/src/r2db_api"

overall_status=0
declare -a results=()

record() {
    # $1 = check name, $2 = one of PASS / FAIL / "SKIPPED (tool absent)"
    results+=("$1: $2")
    if [ "$2" = "FAIL" ]; then
        overall_status=1
    fi
}

record_absent_tool() {
    # $1 = check name. Honors --require-tools: absent tool is a FAIL there,
    # a SKIPPED elsewhere.
    if [ "$require_tools" -eq 1 ]; then
        record "$1" "FAIL"
        printf '%s: required tool absent and --require-tools was given\n' "$1" >&2
    else
        record "$1" "SKIPPED (tool absent)"
    fi
}

# ---------------------------------------------------------------------------
# 1. systemd-analyze verify -- both units
# ---------------------------------------------------------------------------
if command -v systemd-analyze >/dev/null 2>&1; then
    unit_check_failed=0
    for unit in "${DEPLOY_DIR}/systemd/r2dbsvc-api.service" "${DEPLOY_DIR}/systemd/r2dbsvc-control.service"; do
        if ! systemd-analyze verify "$unit"; then
            unit_check_failed=1
        fi
    done
    if [ "$unit_check_failed" -eq 0 ]; then
        record "systemd-analyze verify" "PASS"
    else
        record "systemd-analyze verify" "FAIL"
    fi
else
    record_absent_tool "systemd-analyze verify"
fi

# ---------------------------------------------------------------------------
# 2. nginx -t -- against a temporary copy with the two REPLACE_ME_* port
#    placeholders substituted for synthetic values, and the illustrative
#    certificate/key paths substituted for a freshly generated, throwaway
#    self-signed pair (both substitutions are required for nginx to even
#    parse the file -- see the header comment above).
# ---------------------------------------------------------------------------
if command -v nginx >/dev/null 2>&1 && command -v openssl >/dev/null 2>&1; then
    nginx_tmp_conf="$(mktemp)"
    nginx_tmp_dir="$(mktemp -d)"
    nginx_tls_dir="$(mktemp -d)"
    trap 'rm -f "$nginx_tmp_conf"; rm -rf "$nginx_tmp_dir" "$nginx_tls_dir"' EXIT

    # Throwaway, synthetic-only self-signed cert/key (1-day validity) --
    # never a real certificate, never committed, generated fresh on every
    # run of this lint and discarded via the trap above. CN is the same
    # *.example.invalid synthetic hostname the template itself already
    # uses, so this substitution does not introduce a new placeholder
    # value that public_value_scan.py would need to special-case.
    openssl req -x509 -newkey rsa:2048 -nodes \
        -subj '/CN=data.example.invalid' \
        -days 1 \
        -keyout "${nginx_tls_dir}/selfsigned.key" \
        -out "${nginx_tls_dir}/selfsigned.crt" \
        >/dev/null 2>&1

    sed \
        -e 's/REPLACE_ME_INTERNAL_PORT/18081/g' \
        -e 's/REPLACE_ME_CONTROL_PORT/18082/g' \
        -e "s#/etc/letsencrypt/live/data.example.invalid/fullchain.pem#${nginx_tls_dir}/selfsigned.crt#g" \
        -e "s#/etc/letsencrypt/live/data.example.invalid/privkey.pem#${nginx_tls_dir}/selfsigned.key#g" \
        "${DEPLOY_DIR}/nginx/r2dbsvc-api-8443.conf.example" >"$nginx_tmp_conf"

    # A minimal top-level nginx.conf wrapping the rendered server block --
    # `nginx -t -c` still needs an events{} block and http{} context; the
    # server block itself is `include`d unmodified from the rendered copy
    # above so the check exercises this repository's own file byte-for-byte
    # (after substitution), not a paraphrase of it.
    cat >"${nginx_tmp_dir}/nginx.conf" <<EOF
events {}
http {
    include ${nginx_tmp_conf};
}
EOF

    if nginx -t -c "${nginx_tmp_dir}/nginx.conf"; then
        record "nginx -t" "PASS"
    else
        record "nginx -t" "FAIL"
    fi
else
    record_absent_tool "nginx -t"
fi

# ---------------------------------------------------------------------------
# 3. bash -n -- every operator script. Always runs (no absence branch: this
#    script is itself running under bash).
# ---------------------------------------------------------------------------
script_check_failed=0
for script in "${DEPLOY_DIR}"/scripts/*.sh; do
    if ! bash -n "$script"; then
        script_check_failed=1
    fi
done
if [ "$script_check_failed" -eq 0 ]; then
    record "bash -n" "PASS"
else
    record "bash -n" "FAIL"
fi

if command -v shellcheck >/dev/null 2>&1; then
    shellcheck_failed=0
    for script in "${DEPLOY_DIR}"/scripts/*.sh; do
        if ! shellcheck "$script"; then
            shellcheck_failed=1
        fi
    done
    if [ "$shellcheck_failed" -eq 0 ]; then
        record "shellcheck" "PASS"
    else
        record "shellcheck" "FAIL"
    fi
else
    # shellcheck is "add it if available" per this WP's own design (D-5) --
    # unlike nginx/systemd-analyze it is never a required check, so its
    # absence stays SKIPPED even under --require-tools.
    record "shellcheck" "SKIPPED (tool absent)"
fi

# ---------------------------------------------------------------------------
# 4. ExecStart non-vacuity -- each unit's ExecStart= must name the exact
#    uvicorn module target this WP claims it does, and that module file
#    must exist in this checkout. Always runs; no external tool.
# ---------------------------------------------------------------------------
execstart_check_failed=0

check_execstart() {
    # $1 = unit file, $2 = ERE the ExecStart line must match, $3 = module
    # file that must exist alongside it.
    local unit_path="$1" pattern="$2" module_path="$3"
    if ! grep -Eq "$pattern" "$unit_path"; then
        printf 'ExecStart non-vacuity FAILED: %s does not match %s\n' "$unit_path" "$pattern" >&2
        execstart_check_failed=1
    fi
    if [ ! -f "$module_path" ]; then
        printf 'ExecStart non-vacuity FAILED: expected module file missing: %s\n' "$module_path" >&2
        execstart_check_failed=1
    fi
}

check_execstart \
    "${DEPLOY_DIR}/systemd/r2dbsvc-control.service" \
    'ExecStart=.*uvicorn r2db_api\.control_main:app' \
    "${SRC_DIR}/control_main.py"

check_execstart \
    "${DEPLOY_DIR}/systemd/r2dbsvc-api.service" \
    'ExecStart=.*uvicorn r2db_api\.main:app' \
    "${SRC_DIR}/main.py"

if [ "$execstart_check_failed" -eq 0 ]; then
    record "ExecStart non-vacuity" "PASS"
else
    record "ExecStart non-vacuity" "FAIL"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
printf '\n-- deploy-assets lint summary --\n'
for line in "${results[@]}"; do
    printf '%s\n' "$line"
done

exit "$overall_status"
