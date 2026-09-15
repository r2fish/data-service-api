"""r2db-api response shapes for `DataService.query_page`/`mutate_result` (SV1).

A pure leaf: two frozen dataclasses with no logic beyond their own field
defaults, carrying no import of `.service` or anything `service.py`
assembles them from."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class QueryPage:
    """`DataService.query_page`'s own return shape, matching `spec/data-service-api.v1.json`'s `QueryResult` (CCR-13 introduced `items`/`next_page`; WP-5 adds `revisions`, index-aligned with `items`, now that `revision_preconditions` is declared `enabled`). `next_page`
    is the opaque cursor for the next page (`QueryOutcome.next_cursor`,
    `r2db_api.structured`), or `None` when this was the last page.

    History: CH-0170
    """

    items: list[dict[str, Any]]
    next_page: str | None
    revisions: list[str]
    # Contract 1.7.0: the same `request_id` this query's own audit event (`_query_outcome`'s `_event` call) carries -- generated once, in `query_page` itself, before `_query_outcome` runs, so both this field and that audit event see the identical value.
    # history: CH-0169
    request_id: str | None = None


@dataclass(frozen=True)
class MutationResult:
    """`DataService.mutate_result`'s own return shape, matching
    `spec/data-service-api.v1.json`'s `MutationResult`. Mirrors the `query`/`query_page` split: `mutate` below (in `service.py`) stays byte-for-byte backward compatible (a bare `int`, the affected count) for every existing caller (the in-process conformance adapter); this richer shape reaches only the HTTP boundary, which needs `assigned_addresses` to build the contract's own response. `entity` is
    never present on any element here (contract: only the cross-entity
    endpoint's own elements name their entity; this is the per-entity
    endpoint's shape).

    `committed`/`plan` (contract 1.7.0, D-4): before WP-2b, every caller reaching this point had necessarily committed (an atomic batch that failed partway through never returns anything, it raises), so `http.post_mutate` hardcoded `committed: True` itself and this dataclass carried no such field at all. `committed` now reports the
    real decision (`False` only for a `dry_run` that reached the "would
    succeed" decision); `plan` carries the deterministic token computed
    for it -- `DataService.mutate_result` only ever sets `plan` on a
    `dry_run` response (`None` for a real commit, D-4 (3): a real
    response's shape stays otherwise unchanged from before this version).

    `None` exactly on a `dry_run` response -- `http.post_mutate` omits the key itself then, rather than carrying an empty list, matching the contract's "does not carry" wording. A real commit always gets a list
    (possibly empty, when the batch assigned no address), unchanged from
    before this version.

    History: CH-0168
    """

    affected: int
    assigned_addresses: list[dict[str, Any]] | None
    committed: bool = True
    plan: str | None = None
    # Contract 1.7.0: `outcome.request_id` -- this execution's own value for a real commit/dry_run, or the ORIGINAL execution's own value for an idempotency replay (`MutationOutcome.request_id`'s own comment). Never regenerated here.
    # history: CH-0167
    request_id: str | None = None
