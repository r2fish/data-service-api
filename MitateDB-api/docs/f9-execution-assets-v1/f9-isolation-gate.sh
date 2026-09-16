#!/usr/bin/env bash
set -Eeuo pipefail

fail() { printf 'f9-isolation-gate.sh: result=FAIL_CLOSED reason=%s\n' "$1" >&2; exit 42; }
need() { local name="$1"; [[ -n "${!name:-}" ]] || fail "missing_${name}"; [[ "${!name}" != *$'\n'* && "${!name}" != *$'\r'* ]] || fail "newline_${name}"; }

for name in F9_EXECUTION_ENV F9_MODE F9_REGION F9_SERVICE_KIND F9_EXPECTED_PROJECT F9_EXPECTED_SERVICE F9_CANDIDATE_TAG F9_CANDIDATE_REVISION F9_EXPECTED_TAGGED_URL F9_EXPECTED_STABLE_AUDIENCE F9_IMAGE_DIGEST F9_EXPECTED_SCOPE F9_EXPECTED_DB_ID F9_EXPECTED_IDENTITY_FINGERPRINT; do need "$name"; done
[[ "$F9_EXECUTION_ENV" == cloud-environment ]] || fail local_execution_forbidden
[[ "$F9_MODE" == isolated || "$F9_MODE" == production-candidate ]] || fail invalid_mode
[[ "$F9_SERVICE_KIND" == data || "$F9_SERVICE_KIND" == application ]] || fail invalid_service_kind
[[ "$F9_IMAGE_DIGEST" =~ ^sha256:[0-9a-f]{64}$ ]] || fail invalid_image_digest
[[ "$F9_EXPECTED_IDENTITY_FINGERPRINT" =~ ^[0-9a-f]{64}$ ]] || fail invalid_identity_fingerprint
if [[ "$F9_SERVICE_KIND" == data ]]; then [[ "$F9_CANDIDATE_TAG" == f9-ds-candidate ]] || fail invalid_data_candidate_tag; else [[ "$F9_CANDIDATE_TAG" == f9-app-candidate ]] || fail invalid_application_candidate_tag; fi

allowlist="F9_EXECUTION_ENV F9_EXECUTION_ASSET_ROOT F9_MODE F9_REGION F9_SERVICE_KIND F9_JOB_NAME F9_JOB_SERVICE_ACCOUNT F9_CANDIDATE_TAG F9_CANDIDATE_REVISION F9_EXPECTED_TAGGED_URL F9_EXPECTED_STABLE_AUDIENCE F9_IMAGE_DIGEST F9_EXPECTED_PROJECT F9_EXPECTED_SERVICE F9_EXPECTED_SCOPE F9_EXPECTED_DB_ID F9_EXPECTED_CREDENTIAL_SECRET_NAME F9_EXPECTED_DSN_SECRET_NAME F9_EXPECTED_APP_DS_URL F9_EXPECTED_MAX_OPERATION_DEPTH F9_EXPECTED_IDENTITY_FINGERPRINT F9_PROD_IDENTITY_FINGERPRINT F9_CREDENTIAL_SECRET_REF F9_ISO_PROBE_ENTITY F9_ISO_SECRET_FLAGS F9_PROD_SECRET_FLAGS F9_ISO_PROJECT F9_ISO_DS_SERVICE F9_ISO_DS_TAGGED_URL F9_ISO_DS_STABLE_AUDIENCE F9_ISO_APP_SERVICE F9_ISO_APP_TAGGED_URL F9_ISO_APP_STABLE_AUDIENCE F9_ISO_DB_INSTANCE F9_ISO_DB_NAME F9_ISO_APPLICATION_ID F9_ISO_CREDENTIAL_REF F9_PROD_PROJECT F9_PROD_DS_SERVICE F9_PROD_DS_TAGGED_URL F9_PROD_DS_STABLE_AUDIENCE F9_PROD_COMPAT_APP_SERVICE F9_PROD_COMPAT_APP_TAGGED_URL F9_PROD_COMPAT_APP_STABLE_AUDIENCE F9_PROD_APP_SERVICE F9_PROD_APP_TAGGED_URL F9_PROD_APP_STABLE_AUDIENCE F9_PROD_DB_INSTANCE F9_PROD_DB_NAME F9_PROD_APPLICATION_ID F9_PROD_CREDENTIAL_REF F9_OLD_APP_CREDENTIAL_REF"
while IFS='=' read -r name _; do if [[ "$name" == F9_* && " $allowlist " != *" $name "* ]]; then fail "variable_not_allowlisted_${name}"; fi; done < <(env)

candidate_host="${F9_EXPECTED_TAGGED_URL#https://}"; candidate_host="${candidate_host%%/*}"
audience_host="${F9_EXPECTED_STABLE_AUDIENCE#https://}"; audience_host="${audience_host%%/*}"
[[ -n "$candidate_host" && -n "$audience_host" && "$candidate_host" != "$audience_host" ]] || fail audience_host_not_separate
identity_fingerprint="$(printf '%s\0' "$F9_EXPECTED_PROJECT" "$F9_EXPECTED_SERVICE" "$F9_EXPECTED_DB_ID" "$F9_EXPECTED_SCOPE" | sha256sum | awk '{print $1}')"
if [[ "$F9_MODE" == isolated ]]; then
  need F9_PROD_IDENTITY_FINGERPRINT
  [[ "$F9_PROD_IDENTITY_FINGERPRINT" =~ ^[0-9a-f]{64}$ ]] || fail invalid_prod_identity_fingerprint
  [[ "$identity_fingerprint" != "$F9_PROD_IDENTITY_FINGERPRINT" ]] || fail iso_prod_identity_match
else
  [[ "$identity_fingerprint" == "$F9_EXPECTED_IDENTITY_FINGERPRINT" ]] || fail production_identity_fingerprint_mismatch
fi

service_json="$(mktemp)"; revision_json="$(mktemp)"; trap 'rm -f "$service_json" "$revision_json"' EXIT
gcloud run services describe "$F9_EXPECTED_SERVICE" --project="$F9_EXPECTED_PROJECT" --region="$F9_REGION" --format=json >"$service_json" || fail service_describe_failed
gcloud run revisions describe "$F9_CANDIDATE_REVISION" --project="$F9_EXPECTED_PROJECT" --region="$F9_REGION" --format=json >"$revision_json" || fail revision_describe_failed
stable_url="$(jq -r '.status.url // empty' "$service_json")"
[[ "$stable_url" == "$F9_EXPECTED_STABLE_AUDIENCE" ]] || fail stable_audience_mismatch
derived_tag_url="https://${F9_CANDIDATE_TAG}---${stable_url#https://}"
[[ "$derived_tag_url" == "$F9_EXPECTED_TAGGED_URL" ]] || fail tagged_url_mismatch
[[ "$(jq -r '.metadata.name // empty' "$revision_json")" == "$F9_CANDIDATE_REVISION" ]] || fail revision_name_mismatch
[[ "$(jq -r '[.status.conditions[]? | select(.type == "Ready") | .status] | last // empty' "$revision_json")" == True ]] || fail revision_not_ready
tag_count="$(jq --arg tag "$F9_CANDIDATE_TAG" --arg rev "$F9_CANDIDATE_REVISION" '[.status.traffic[]? | select(.tag == $tag and .revisionName == $rev and ((.percent // 0) | tonumber) == 0)] | length' "$service_json")"
[[ "$tag_count" == 1 ]] || fail candidate_tag_or_traffic_assertion
image="$(jq -r '.spec.containers[0].image // empty' "$revision_json")"; [[ "$image" == *"@$F9_IMAGE_DIGEST" ]] || fail image_digest_mismatch
env_value() { jq -r --arg name "$1" '[.spec.containers[0].env[]? | select(.name == $name) | .value // empty] | last // empty' "$revision_json"; }
secret_name() { jq -r --arg name "$1" '[.spec.containers[0].env[]? | select(.name == $name) | .valueFrom.secretKeyRef.name // empty] | last // empty' "$revision_json"; }
if [[ "$F9_SERVICE_KIND" == data ]]; then
  need F9_EXPECTED_DSN_SECRET_NAME
  [[ "$(env_value MITATEDB_MAX_OPERATION_DEPTH)" == "${F9_EXPECTED_MAX_OPERATION_DEPTH:-13}" ]] || fail operation_depth_env_mismatch
  [[ "$(env_value MITATEDB_SERVE_APPS)" == "$F9_EXPECTED_SCOPE" ]] || fail application_scope_mismatch
  [[ "$(secret_name MITATEDB_PLATFORM_DSN)" == "$F9_EXPECTED_DSN_SECRET_NAME" ]] || fail dsn_secret_ref_mismatch
  [[ "$(jq -r '.metadata.annotations["run.googleapis.com/cloudsql-instances"] // empty' "$service_json")" == "$F9_EXPECTED_DB_ID" ]] || fail database_identity_mismatch
else
  need F9_EXPECTED_CREDENTIAL_SECRET_NAME
  need F9_EXPECTED_APP_DS_URL
  [[ "$(env_value MITATE_STORE)" == data-service ]] || fail application_store_mismatch
  [[ "$(env_value MITATE_DATA_SERVICE_AUTH)" == google-id-token ]] || fail application_auth_mode_mismatch
  [[ "$(env_value MITATE_DATA_SERVICE_URL)" == "$F9_EXPECTED_APP_DS_URL" ]] || fail application_data_service_url_mismatch
  [[ "$(secret_name MITATE_DATA_SERVICE_RUNTIME_CREDENTIAL)" == "$F9_EXPECTED_CREDENTIAL_SECRET_NAME" ]] || fail application_credential_ref_mismatch
fi
printf 'f9-isolation-gate.sh: kind=%s mode=%s ready=Ready tag=%s traffic=0 digest=match config=match result=PASS\n' "$F9_SERVICE_KIND" "$F9_MODE" "$F9_CANDIDATE_TAG"
