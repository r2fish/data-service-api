#!/usr/bin/env bash
set -Eeuo pipefail

fail() {
  printf 'f9-job-entrypoint.sh: result=FAIL_CLOSED reason=%s\n' "$1" >&2
  exit 44
}

command_name="${1:-}"
set_candidate_auth_env() {
  : "${F9_EXPECTED_TAGGED_URL:?F9_EXPECTED_TAGGED_URL is required}"
  : "${F9_EXPECTED_STABLE_AUDIENCE:?F9_EXPECTED_STABLE_AUDIENCE is required}"
  : "${F9_CREDENTIAL_SECRET_REF:?F9_CREDENTIAL_SECRET_REF is required}"
  export F9_CANDIDATE_URL="$F9_EXPECTED_TAGGED_URL"
  export F9_TARGET_URL="$F9_EXPECTED_TAGGED_URL"
  export F9_STABLE_AUDIENCE="$F9_EXPECTED_STABLE_AUDIENCE"
}
case "$command_name" in
  gate)
    exec /opt/f9/f9-isolation-gate.sh
    ;;
  bootstrap-gate)
    exec /opt/f9/f9-bootstrap-gate.sh
    ;;
  capabilities)
    set_candidate_auth_env
    /opt/f9/f9-auth-curl.sh --url "$F9_CANDIDATE_URL" --path /v1/capabilities \
      | python3 /opt/f9/f9-json-assert.py --minimum-operation-depth 13
    ;;
  depth-13|depth-14)
    depth_value="${command_name#depth-}"
    [[ "$F9_MODE" == isolated ]] || fail production_depth_probe_forbidden
    set_candidate_auth_env
    exec python3 /opt/f9/f9-depth-probe.py --base-url "$F9_CANDIDATE_URL" \
      --auth-mode cloud-environment --auth-curl /opt/f9/f9-auth-curl.sh \
      --depth "$depth_value" --dry-run
    ;;
  conformance-inprocess)
    [[ "${F9_MODE:-}" == isolated ]] || fail production_conformance_forbidden
    cd /opt/mitate-application
    exec env MITATE_STORE=data-service MITATE_DATA_SERVICE_AUTH=google-id-token \
      CONFORMANCE_FIXTURES_DIR=/opt/fixtures npm run conformance -- --md
    ;;
  conformance-http)
    [[ "${F9_MODE:-}" == isolated ]] || fail production_conformance_forbidden
    cd /opt/mitate-application
    exec env MITATE_STORE=data-service MITATE_DATA_SERVICE_AUTH=google-id-token \
      CONFORMANCE_FIXTURES_DIR=/opt/fixtures npm run conformance -- --http --md
    ;;
  app-readonly)
    : "${MITATE_STORE:?MITATE_STORE is required}"
    : "${MITATE_DATA_SERVICE_URL:?MITATE_DATA_SERVICE_URL is required}"
    : "${MITATE_DATA_SERVICE_RUNTIME_CREDENTIAL:?runtime credential secret mapping is required}"
    : "${MITATE_DATA_SERVICE_AUTH:?MITATE_DATA_SERVICE_AUTH is required}"
    cd /opt/mitate-application
    node dist/http/serve.js >/tmp/f9-application-startup.log 2>&1 &
    pid=$!
    trap 'kill "$pid" 2>/dev/null || true' EXIT
    for attempt in $(seq 1 30); do
      if curl --silent --show-error --fail http://127.0.0.1:"${PORT:-8080}"/health >/dev/null; then
        printf 'application-readonly=PASS data-service-url-host=%s\n' "${MITATE_DATA_SERVICE_URL#https://}" | cut -d/ -f1
        exit 0
      fi
      kill -0 "$pid" 2>/dev/null || fail application_startup_failed
      sleep 1
    done
    fail application_readiness_timeout
    ;;
  *)
    fail "unknown_command_${command_name:-missing}"
    ;;
esac
