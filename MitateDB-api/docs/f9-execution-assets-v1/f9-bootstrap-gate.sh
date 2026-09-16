#!/usr/bin/env bash
set -Eeuo pipefail

fail() { printf 'f9-bootstrap-gate.sh: result=FAIL_CLOSED reason=%s\n' "$1" >&2; exit 41; }
need() { local name="$1"; [[ -n "${!name:-}" ]] || fail "missing_${name}"; [[ "${!name}" != *$'\n'* && "${!name}" != *$'\r'* ]] || fail "newline_${name}"; }

for name in F9_EXECUTION_ENV F9_MODE F9_EXPECTED_PROJECT F9_EXPECTED_SERVICE F9_EXPECTED_DB_ID F9_EXPECTED_SCOPE F9_PROD_IDENTITY_FINGERPRINT; do need "$name"; done
[[ "$F9_EXECUTION_ENV" == cloud-environment ]] || fail local_execution_forbidden
[[ "$F9_MODE" == isolated-bootstrap ]] || fail invalid_bootstrap_mode
[[ "$F9_PROD_IDENTITY_FINGERPRINT" =~ ^[0-9a-f]{64}$ ]] || fail invalid_prod_identity_fingerprint
identity_fingerprint="$(printf '%s\0' "$F9_EXPECTED_PROJECT" "$F9_EXPECTED_SERVICE" "$F9_EXPECTED_DB_ID" "$F9_EXPECTED_SCOPE" | sha256sum | awk '{print $1}')"
[[ "$identity_fingerprint" != "$F9_PROD_IDENTITY_FINGERPRINT" ]] || fail iso_prod_identity_match
printf 'f9-bootstrap-gate.sh: mode=isolated-bootstrap identity=separate result=PASS\n'
