#!/usr/bin/env python3
"""deploy_smoke.py -- data-service-api deployment smoke test (Phase 8 WP-4,
design docs/design/PHASE8_EFFECTIVE_BOUNDS_AND_HYGIENE_V1.md D-5 decision
3, work order docs/work-orders/WORK_ORDER_PHASE8_EFFECTIVE_BOUNDS_V1.md §2
WP-4 実装の指示 (b)).

Three stages, run against a REAL, already-deployed HTTP surface (never a
conformance plug -- this tool is an operational aid, not part of the
`conformance-tests/` suite; L7-2's own real-socket plug is a later phase's
item):

  1. GET  /v1/capabilities  -- 200, and `contract_version` is readable.
  2. GET  /v1/catalog       -- 200, and at least one entity is readable.
  3. POST /v1/data/{entity}/query -- 200, one bounded query against the
                                stage-2 entity (`--entity` overrides the
                                default, "the catalog's first entity").
                                If the catalog is empty, or the picked
                                entity has no field to select, stage 3
                                cannot be performed at all -- an empty
                                application is not, by itself, a broken
                                deployment, but this tool does NOT treat
                                "could not check" the same as "checked and
                                it passed": by default it exits 4 ("stage
                                3 not performed") and prints "stage3
                                skipped: empty catalog"; pass
                                --allow-empty-catalog to make that same
                                situation exit 0 instead (WP-4 rework,
                                supervisor ruling 2026-09-06, wp4-rework-
                                1.md #5 -- a restore-verification runbook
                                that only checks "exit 0" cannot otherwise
                                tell an empty/misrouted restore target
                                apart from one that was actually queried).

Standard library only (`urllib`) -- both peers share the same contract, so
one tool serves both, and this is an operational aid, never product code
(design D-5: "両 peer 共通のツールでよい...製品コードではない").

Secret handling (SI-10): `--api-key-env`/`--base-url-env` take ENVIRONMENT
VARIABLE NAMES, never values, as ARGUMENTS -- this tool never accepts a
base URL or an API key as a literal argument. The API key VALUE is never
printed by this tool, in any message, on any path. The base URL VALUE, by
contrast, DOES appear on stderr on a stage failure -- every stage's own
error message embeds the full request URL it tried (e.g. a connection
failure prints "GET https://<the base URL>/v1/... -> could not connect:
..."); a base URL is not itself SI-10's protected secret (SI-10 protects
passwords/credential-bearing connection URLs, not a bare service origin),
but an earlier draft of this docstring claimed NO message ever includes
more than the env var NAME, which measured behavior contradicts (WP-4
rework, supervisor ruling 2026-09-06, wp4-rework-1.md #6) -- corrected
here rather than changed to suppress the URL, since the URL is useful for
diagnosing which stage failed against which target.

Exit codes (WP-4 rework round 2, supervisor ruling 2026-09-06, wp4-
rework-2.md #3: "段3失敗" and "段3未実施(空catalog)" previously shared exit
code 4 -- indistinguishable by exit code alone, only by stderr text; now
split):

| exit | condition                                                          |
|------|---------------------------------------------------------------------|
|  0   | all three stages passed, OR stage 3's skip was allowed via          |
|      | `--allow-empty-catalog`                                             |
|  1   | stage 1 (capabilities) failed                                       |
|  2   | stage 2 (catalog) failed                                             |
|  3   | stage 3 (query) failed OUTRIGHT (a real request was made and it     |
|      | did not pass)                                                        |
|  4   | stage 3 was NOT PERFORMED at all -- empty catalog, or the picked    |
|      | entity has no queryable field -- and `--allow-empty-catalog` was    |
|      | not given (unchanged from the prior round)                          |
|  5   | usage error -- missing/unset env var, bad arguments (never a check  |
|      | result; argparse's own native argument errors, e.g. an unrecognized |
|      | flag, still exit 2 via Python's own `ArgumentParser.error()`, a     |
|      | different code path than this table)                                |
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any


class SmokeStageError(RuntimeError):
    """One stage's own failure -- carries no secret, only what the stage
    itself observed (status code / a parse complaint), so `main` can print
    it directly."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuses to follow a redirect: contract `versioning.url_composition`
    says a client follows no redirect in answer to a request that carries a
    credential, at any URL this rule forms, and the default opener would
    send this tool's bearer to the `Location` of a 3xx. With `redirect_request` returning `None` the 3xx
    surfaces as an `HTTPError` carrying its own status, and nothing is sent
    to the `Location`. `_request` reports such a 3xx as its own status with
    its body uninterpreted; the stage that asked treats any status but 200
    as its failure, and neither the `Location` value nor the credential
    appears in any message."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401, ARG002
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


def _request(method: str, url: str, *, api_key: str, body: dict[str, Any] | None = None) -> tuple[int, Any]:
    data = None
    headers = {"Authorization": f"Bearer {api_key}"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with _OPENER.open(req, timeout=15) as resp:
            status = resp.status
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        status = exc.code
        raw = exc.read()
    except urllib.error.URLError as exc:
        # Connection-level failure (refused/unreachable/DNS/timeout) --
        # never a raw traceback: every stage's own failure surfaces as one
        # SmokeStageError line, same as an unexpected status code does.
        raise SmokeStageError(f"{method} {url} -> could not connect: {exc.reason}") from None
    if 300 <= status < 400:
        return status, None
    try:
        parsed = json.loads(raw) if raw else None
    except json.JSONDecodeError as exc:
        raise SmokeStageError(f"{method} {url} -> {status}, but the response body did not parse as JSON: {exc}") from None
    return status, parsed


def _stage_capabilities(base_url: str, api_key: str) -> str:
    status, document = _request("GET", f"{base_url}/v1/capabilities", api_key=api_key)
    if status != 200:
        raise SmokeStageError(f"GET /v1/capabilities -> {status} (expected 200)")
    if not isinstance(document, dict) or "contract_version" not in document:
        raise SmokeStageError("GET /v1/capabilities -> 200, but the response has no readable contract_version")
    contract_version = document["contract_version"]
    print(f"stage1 capabilities  {status} contract_version={contract_version}")
    return contract_version


def _stage_catalog(base_url: str, api_key: str, entity_override: str | None) -> tuple[str, str] | None:
    """Returns `(entity, field)` for stage 3 to query, or `None` if stage
    3 CANNOT be performed at all (a legitimately empty catalog, or the
    picked entity has no fields to select). `None` is not itself a pass/
    fail verdict -- `main` decides the exit code for it (design D-5 /
    WP-4 rework #5: "could not check" is not silently the same as
    "checked and it passed")."""
    status, document = _request("GET", f"{base_url}/v1/catalog", api_key=api_key)
    if status != 200:
        raise SmokeStageError(f"GET /v1/catalog -> {status} (expected 200)")
    if not isinstance(document, dict) or not isinstance(document.get("entities"), list):
        raise SmokeStageError("GET /v1/catalog -> 200, but the response has no readable entities array")
    entities = document["entities"]
    print(f"stage2 catalog       {status} entities={len(entities)}")

    if entity_override is not None:
        picked = next((e for e in entities if isinstance(e, dict) and e.get("entity") == entity_override), None)
        if picked is None:
            raise SmokeStageError(f"GET /v1/catalog -> 200, but --entity {entity_override!r} is not in the catalog")
    elif entities:
        picked = entities[0]
        if not isinstance(picked, dict) or not picked.get("entity"):
            raise SmokeStageError("GET /v1/catalog -> 200, but the first entity has no readable name")
    else:
        return None

    fields = picked.get("fields") or []
    if not fields:
        return None
    return picked["entity"], fields[0]


def _stage_query(base_url: str, api_key: str, entity: str, field: str) -> None:
    status, document = _request("POST", f"{base_url}/v1/data/{entity}/query", api_key=api_key, body={"select": [field]})
    if status != 200:
        raise SmokeStageError(f"POST /v1/data/{entity}/query -> {status} (expected 200)")
    items = document.get("items") if isinstance(document, dict) else None
    row_count = len(items) if isinstance(items, list) else "?"
    print(f"stage3 query         {status} rows={row_count}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="deploy_smoke.py",
        description="Three-stage deployment smoke test (capabilities -> catalog -> one query). Secrets are read "
                     "from the environment ONLY -- pass environment variable NAMES, never values.\n"
                     "Exit codes: 0=all stages passed (or empty catalog allowed); 1=stage 1 (capabilities) "
                     "failed; 2=stage 2 (catalog) failed; 3=stage 3 (query) failed outright; 4=stage 3 not "
                     "performed (empty catalog / no queryable field), --allow-empty-catalog not given; "
                     "5=usage error (missing/unset env var, bad arguments).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--base-url-env", required=True, metavar="NAME", help="name of the env var holding the base URL (e.g. R2DB_SMOKE_BASE_URL)")
    parser.add_argument("--api-key-env", required=True, metavar="NAME", help="name of the env var holding the bearer API key")
    parser.add_argument("--entity", default=None, metavar="NAME", help="entity to query in stage 3 (default: the catalog's first entity)")
    # WP-4 rework (supervisor ruling 2026-09-06, wp4-rework-1.md #5): an
    # empty catalog (or a catalog whose picked entity has no field to
    # select) means stage 3 could not be PERFORMED, not that it passed --
    # default behavior is exit 4 ("stage 3 not performed"); this flag is
    # the explicit, named opt-in that turns that same situation into exit
    # 0, for a caller that already knows the target application is
    # legitimately empty.
    parser.add_argument(
        "--allow-empty-catalog", action="store_true",
        help="treat an empty catalog (or an entity with no queryable field) as exit 0 instead of exit 4",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    base_url = os.environ.get(args.base_url_env)
    if not base_url:
        print(f"error: {args.base_url_env} is not set (or empty) -- pass an env var NAME holding the base URL, never a literal URL", file=sys.stderr)
        return 5
    api_key = os.environ.get(args.api_key_env)
    if not api_key:
        print(f"error: {args.api_key_env} is not set (or empty) -- pass an env var NAME holding the API key, never a literal secret", file=sys.stderr)
        return 5
    base_url = base_url.rstrip("/")

    try:
        _stage_capabilities(base_url, api_key)
    except SmokeStageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    try:
        picked = _stage_catalog(base_url, api_key, args.entity)
    except SmokeStageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if picked is None:
        if args.allow_empty_catalog:
            print("stage3 skipped: empty catalog (--allow-empty-catalog given)")
            return 0
        print("stage3 skipped: empty catalog", file=sys.stderr)
        return 4
    entity, field = picked

    try:
        _stage_query(base_url, api_key, entity, field)
    except SmokeStageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
