#!/usr/bin/env bash
set -Eeuo pipefail

fail() {
  printf 'f9-auth-curl.sh: result=FAIL_CLOSED reason=%s\n' "$1" >&2
  exit 43
}

[[ "${F9_EXECUTION_ENV:-}" == cloud-environment ]] || fail local_auth_forbidden
[[ -n "${F9_STABLE_AUDIENCE:-}" ]] || fail missing_stable_audience
[[ -n "${F9_CREDENTIAL_SECRET_REF:-}" ]] || fail missing_credential_reference
[[ "$F9_STABLE_AUDIENCE" != "${F9_TARGET_URL:-}" ]] || fail audience_equals_target
[[ "$F9_CREDENTIAL_SECRET_REF" =~ ^projects/[a-z0-9-]+/secrets/[a-zA-Z0-9_-]+/versions/[0-9]+$ ]] || fail invalid_secret_reference

method=GET
path=/v1/capabilities
body_file=
status_file=
target_url="${F9_TARGET_URL:-}"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --url) target_url="${2:-}"; shift 2 ;;
    --method) method="${2:-}"; shift 2 ;;
    --path) path="${2:-}"; shift 2 ;;
    --body-file) body_file="${2:-}"; shift 2 ;;
    --status-file) status_file="${2:-}"; shift 2 ;;
    *) fail unknown_argument ;;
  esac
done
[[ "$target_url" == https://* ]] || fail invalid_target_url
[[ "$target_url" != "$F9_STABLE_AUDIENCE" ]] || fail target_is_stable_url
[[ "$path" == /* ]] || fail invalid_path
target_host="${target_url#https://}"
target_host="${target_host%%/*}"
audience_host="${F9_STABLE_AUDIENCE#https://}"
audience_host="${audience_host%%/*}"
[[ -n "$target_host" && -n "$audience_host" && "$target_host" != "$audience_host" ]] || fail audience_host_not_separate

id_token="$(gcloud auth print-identity-token --audiences="$F9_STABLE_AUDIENCE")" || fail iam_token_unavailable
secret_resource="${F9_CREDENTIAL_SECRET_REF%/versions/*}"
secret_version="${F9_CREDENTIAL_SECRET_REF##*/versions/}"
credential="$(gcloud secrets versions access "$secret_version" --secret="$secret_resource")" || fail credential_reference_unavailable
[[ -n "$id_token" && -n "$credential" ]] || fail empty_auth_material

response_file="$(mktemp)"
curl_config="$(mktemp)"
chmod 600 "$curl_config"
trap 'rm -f "$response_file" "$curl_config"' EXIT
printf '%s\n' "silent" "show-error" "request = $method" "output = $response_file" "write-out = %{http_code}" \
  "header = Authorization: Bearer $credential" \
  "header = X-Serverless-Authorization: Bearer $id_token" >"$curl_config"
if [[ -n "$body_file" ]]; then
  [[ -f "$body_file" ]] || fail body_file_missing
  printf '%s\n' "header = Content-Type: application/json" "data-binary = @$body_file" >>"$curl_config"
fi
printf 'url = %s\n' "${target_url}${path}" >>"$curl_config"
status="$(curl --config "$curl_config")" || fail request_failed
[[ "$status" =~ ^[0-9]{3}$ ]] || fail invalid_http_status
if [[ -n "$status_file" ]]; then
  printf '%s\n' "$status" >"$status_file"
fi
cat "$response_file"
