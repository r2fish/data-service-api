#!/usr/bin/env python3
"""Synthetic dry-run operation-depth probe for the isolated Data Service."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from collections.abc import Mapping, Sequence


def depth(value: object) -> int:
    if isinstance(value, Mapping):
        children = value.values()
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        children = value
    else:
        return 0
    return 1 + max((depth(child) for child in children), default=0)


def fail(reason: str) -> None:
    raise SystemExit(f"f9-depth-probe.py: result=FAIL_CLOSED reason={reason}")


def call_json(auth_curl: str, base_url: str, path: str, body: dict[str, object] | None = None) -> tuple[int, object]:
    with tempfile.TemporaryDirectory() as work:
        body_path = os.path.join(work, "request.json")
        status_path = os.path.join(work, "status")
        command = [auth_curl, "--url", base_url, "--method", "GET" if body is None else "POST", "--path", path, "--status-file", status_path]
        if body is not None:
            with open(body_path, "w", encoding="utf-8") as handle:
                json.dump(body, handle, separators=(",", ":"))
            command.extend(("--body-file", body_path))
        response = subprocess.run(command, check=False, capture_output=True, text=True)
        if response.returncode != 0 or not os.path.exists(status_path):
            fail("read_only_invariant_request_failed")
        with open(status_path, encoding="utf-8") as handle:
            status = int(handle.read().strip())
        try:
            payload = json.loads(response.stdout)
        except json.JSONDecodeError:
            fail("read_only_invariant_json_shape")
        return status, payload


def invariant_snapshot(auth_curl: str, base_url: str, entity: str) -> tuple[int, int, object]:
    audit_status, audit = call_json(auth_curl, base_url, "/v1/data/audit_log/query", {"page": {"size": 500}})
    entity_status, rows = call_json(auth_curl, base_url, f"/v1/data/{entity}/query", {"page": {"size": 500}})
    capability_status, capabilities = call_json(auth_curl, base_url, "/v1/capabilities")
    if audit_status != 200 or entity_status != 200 or capability_status != 200:
        fail("read_only_invariant_status")
    if not isinstance(audit, dict) or not isinstance(rows, dict) or not isinstance(capabilities, dict):
        fail("read_only_invariant_object_shape")
    audit_items = audit.get("items")
    row_items = rows.get("items")
    if not isinstance(audit_items, list) or not isinstance(row_items, list):
        fail("read_only_invariant_items_shape")
    public_capability = {"contract_version": capabilities.get("contract_version"), "capabilities": capabilities.get("capabilities"), "limits": capabilities.get("limits"), "limit_enforcement": capabilities.get("limit_enforcement")}
    return len(audit_items), len(row_items), public_capability


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--auth-mode", required=True)
    parser.add_argument("--auth-curl", required=True)
    parser.add_argument("--depth", type=int, choices=(13, 14), required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.auth_mode != "cloud-environment" or not args.dry_run:
        fail("cloud_environment_and_dry_run_required")
    entity = os.environ.get("F9_ISO_PROBE_ENTITY")
    if not entity or any(char in entity for char in "\n\r"):
        fail("missing_probe_entity")

    values: dict[str, object] = {"label": "f9-synthetic-depth-probe", "probe_padding": {}}
    body: dict[str, object] = {
        "operations": [{"operation": "insert", "entity": entity, "values": values}],
        "dry_run": True,
    }
    padding = values["probe_padding"]
    assert isinstance(padding, dict)
    while depth(body) < args.depth:
        child: dict[str, object] = {}
        padding["x"] = child
        padding = child
    if depth(body) != args.depth:
        fail("probe_depth_construction")

    before_audit, before_rows, before_capability = invariant_snapshot(args.auth_curl, args.base_url, entity)

    with tempfile.TemporaryDirectory() as work:
        body_path = os.path.join(work, "body.json")
        status_path = os.path.join(work, "status")
        with open(body_path, "w", encoding="utf-8") as handle:
            json.dump(body, handle, separators=(",", ":"))
        command = [args.auth_curl, "--url", args.base_url, "--method", "POST", "--path", "/v1/data/mutations", "--body-file", body_path, "--status-file", status_path]
        response = subprocess.run(command, check=False, capture_output=True, text=True)
        if response.returncode != 0 or not os.path.exists(status_path):
            fail("authenticated_request_failed")
        with open(status_path, encoding="utf-8") as handle:
            status = int(handle.read().strip())
        try:
            payload = json.loads(response.stdout)
        except json.JSONDecodeError:
            payload = {}

    after_audit, after_rows, after_capability = invariant_snapshot(args.auth_curl, args.base_url, entity)
    if (before_audit, before_rows, before_capability) != (after_audit, after_rows, after_capability):
        fail("dry_run_changed_schema_or_audit_invariants")
    print("dry-run invariants: audit_rows=same entity_rows=same capabilities=same")

    if args.depth == 13:
        if status != 200 or payload.get("committed") is not False:
            fail("depth_13_not_accepted_without_commit")
        print("depth=13 status=accepted committed=false")
    else:
        details = payload.get("details") if isinstance(payload, dict) else None
        code = payload.get("code") if isinstance(payload, dict) else None
        if code is None and isinstance(payload, dict):
            code = payload.get("error_code")
        limit_class = details.get("limit_class") if isinstance(details, dict) else None
        if status != 413 or code != "LIMIT_EXCEEDED" or limit_class != "operation_depth":
            fail("depth_14_not_rejected_as_operation_depth")
        print("depth=14 status=413 code=LIMIT_EXCEEDED limit_class=operation_depth")
    return 0


if __name__ == "__main__":
    main()
