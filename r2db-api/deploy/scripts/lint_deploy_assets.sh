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

# Scratch files/dirs created by the checks below (systemd-analyze verify's
# stub unit copies, nginx -t's rendered conf/cert). Collected here rather
# than one `trap ... EXIT` per check so a later check's trap does not
# silently replace an earlier one's and skip its cleanup.
declare -a cleanup_paths=()
# shellcheck disable=SC2329 # invoked indirectly via `trap ... EXIT` below
cleanup_scratch() {
    local p
    for p in "${cleanup_paths[@]}"; do
        rm -rf "$p"
    done
}
trap cleanup_scratch EXIT

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

    # `systemd-analyze verify` stats the ExecStart= binary and the
    # EnvironmentFile= path and hard-fails ("Command ... is not executable:
    # No such file or directory") if either is absent -- both name the
    # TARGET host's illustrative install layout (/opt/r2dbsvc/..., /etc/
    # r2dbsvc/...), which does not and must not exist on whatever host runs
    # this lint (including CI). Verify a scratch COPY of each unit instead,
    # with ONLY those two paths substituted for lint-local stand-ins: the
    # ExecStart binary for a trivial executable stub, EnvironmentFile for an
    # empty file. No other directive is touched, so the hardening posture,
    # unit shape, and every other value are still exercised byte-for-byte.
    # Check 4 (ExecStart non-vacuity) below verifies the module target
    # against the ORIGINAL, unmodified unit files -- this substitution is
    # for check 1 only.
    verify_dir="$(mktemp -d)"
    cleanup_paths+=("$verify_dir")

    verify_stub_bin="${verify_dir}/uvicorn-stub"
    printf '#!/bin/sh\n' >"$verify_stub_bin"
    chmod +x "$verify_stub_bin"

    verify_env_api="${verify_dir}/api.env"
    verify_env_control="${verify_dir}/control.env"
    : >"$verify_env_api"
    : >"$verify_env_control"

    verify_unit_api="${verify_dir}/r2dbsvc-api.service"
    sed \
        -e "s#/opt/r2dbsvc/r2db-api/\.venv/bin/uvicorn#${verify_stub_bin}#" \
        -e "s#/etc/r2dbsvc/api\.env#${verify_env_api}#" \
        "${DEPLOY_DIR}/systemd/r2dbsvc-api.service" >"$verify_unit_api"

    verify_unit_control="${verify_dir}/r2dbsvc-control.service"
    sed \
        -e "s#/opt/r2dbsvc/r2db-api/\.venv/bin/uvicorn#${verify_stub_bin}#" \
        -e "s#/etc/r2dbsvc/control\.env#${verify_env_control}#" \
        "${DEPLOY_DIR}/systemd/r2dbsvc-control.service" >"$verify_unit_control"

    for unit in "$verify_unit_api" "$verify_unit_control"; do
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
    cleanup_paths+=("$nginx_tmp_conf" "$nginx_tmp_dir" "$nginx_tls_dir")

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
    #
    # `pid` and `error_log` are set explicitly to lint-local scratch paths
    # in the main context (they are not valid inside events{}/http{}):
    # nginx's own compiled-in default is `pid /run/nginx.pid;`, which a
    # non-root lint invocation cannot write to (`[emerg] open()
    # "/run/nginx.pid" failed (13: Permission denied)`), failing the
    # config test even though the config's own syntax is fine. The default
    # error_log target (typically /var/log/nginx/error.log) is equally
    # unwritable to a non-root lint; pointing it at the same scratch dir
    # avoids relying on that ambient path either.
    cat >"${nginx_tmp_dir}/nginx.conf" <<EOF
pid ${nginx_tmp_dir}/nginx.pid;
error_log ${nginx_tmp_dir}/error.log;
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
    # NOTE: shellcheck is "add it if available" per this WP's own design
    # (D-5) -- unlike nginx/systemd-analyze it is never a required check,
    # so its absence stays SKIPPED even under --require-tools. (This
    # comment deliberately does not start with the literal token sequence
    # "# shellcheck" -- shellcheck parses any comment beginning that way as
    # a directive, e.g. "# shellcheck disable=SC1234", and fails with
    # SC1072/SC1073 if what follows isn't that key=value shape. This is
    # prose, not a directive, hence the reworded lead-in.)
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
