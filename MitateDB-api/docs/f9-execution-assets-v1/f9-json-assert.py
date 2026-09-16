#!/usr/bin/env python3
"""Validate only the public JSON fields required by an F9 capability check."""
from __future__ import annotations

import argparse
import json
import sys


def fail(reason: str) -> None:
    raise SystemExit(f"f9-json-assert.py: result=FAIL_CLOSED reason={reason}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--minimum-operation-depth", type=int, required=True)
    args = parser.parse_args()
    try:
        payload = json.load(sys.stdin)
        limits = payload["limits"]
        enforcement = payload["limit_enforcement"]
        operation_depth = limits["operation_depth"]
        operation_enforcement = enforcement["operation_depth"]
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        fail("capability_json_shape")
    if not isinstance(operation_depth, int) or isinstance(operation_depth, bool):
        fail("operation_depth_not_integer")
    if operation_depth < args.minimum_operation_depth:
        fail("operation_depth_below_minimum")
    if operation_enforcement != "enforced":
        fail("operation_depth_not_enforced")
    print(f"capabilities: operation_depth>={args.minimum_operation_depth} limit_enforcement=operation_depth:enforced json=PASS")
    return 0


if __name__ == "__main__":
    main()
