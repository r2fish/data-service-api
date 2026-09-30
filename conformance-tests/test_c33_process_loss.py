"""C-33 -- a service process that stops without a graceful shutdown loses
neither the audit event of an operation whose response it had already
returned nor the count of a denial occurrence whose response it had already
returned (contract `audit.process_loss_policy`, declared from 1.13.0).

Drives every launcher registered in `conformance-tests/registry.json`'s own
`composition_roots` section (`conftest.py`'s `launcher_class` fixture, shared
with `test_c26_composition_root.py` and `test_c32_shared_limits.py`). Each
launcher is started for this file alone -- a SIGKILL of every worker breaks
the deployment for whatever else it was serving -- with `workers = 2`, a
coalescing window of a few seconds (`start(coalescing_window_ms=...)`, the
real `ops declare-coalescing-window`) and short audit writer timeouts
(`start(audit_writer_timeouts_ms=...)`, the real `ops set-platform-
timeouts`, which is what the served `visibility_lag_ms` derives from), so
the whole drive stays within seconds.

The drive (`process_loss_drive`, one per launcher):

  1. issues a credential fresh for this drive and sends `M` refusals under
     it (the same destructive delete without its confirmation phrase, so
     every refusal is `DESTRUCTIVE_CONFIRMATION_REQUIRED` with the same audit
     key), then `N` successful queries under it, with `N + M` inside the
     declared `requests_per_minute`; the successes go last so that the
     shortest time separates the last event from the kill;
  2. right after the last response, SIGKILLs every worker
     (`launcher.kill_workers`) and waits for the supervisor to replace them;
  3. reads the control plane's `audit_query` under a fresh `role=audit`
     credential, narrowing to this drive's `actor_id` on the client side,
     and polls until the evidence is complete or a bound derived from the
     declared window plus the declared `visibility_lag_ms` plus a margin
     runs out. There is no fixed sleep between the kill and the read.

The observations are separate tests on purpose, so one run shows each of
them on its own:

  - the drive's preconditions (`M` is at least `workers + 1` and some worker
    handled two refusals; every request got the answer the drive counts on;
    the kill followed the last response by well under the period of the
    periodic flush an implementation may still run) and the kill itself
    (every worker killed, gone, replaced, and a replacement serving) are
    green whatever the implementation does with audit evidence;
  - the two tests on the evidence (every returned success has its event,
    with the `request_id` the response carried; the refusal count read back
    totals `M`) are the condition.

`M >= workers + 1` and the access-log check ("one worker handled two or
more refusals") are what make the refusal test bite: an implementation that
records the first refusal a worker sees synchronously and keeps every later
one in that worker's memory loses at least one count only when some worker
saw two.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from typing import Any

import pytest

import socket_harness as sh

pytestmark = pytest.mark.condition("C-33")

#: Kept short and specific so it can never collide with a name any OTHER
#: test file's own probe entities use.
_PROBE_ENTITY = "process_loss_probe"

_WORKERS = 2
#: The coalescing window the launcher declares (ms), and the audit writer
#: `(statement, idle)` timeouts (ms) the served `visibility_lag_ms` derives
#: from.
_WINDOW_MS = 3000
_WRITER_TIMEOUTS_MS = (1000, 2000)

#: `N` successes and `M` refusals of the drive. `M` must be at least
#: `workers + 1` so that some worker handles two refusals.
_SUCCESSES = 6
_DENIALS = 6

#: Longest allowed gap between the last response and the SIGKILL. The
#: periodic flush an implementation may run has a 2 s period; a gap this
#: small keeps that flush from rescuing evidence the kill was meant to take.
_MAX_LAST_RESPONSE_TO_KILL_S = 1.0

#: Poll bound: window + `visibility_lag_ms` + this margin. The interval is
#: at least `60 / audit_requests_per_minute` seconds (both peers declare 60).
_POLL_MARGIN_S = 5.0
_POLL_INTERVAL_S = 1.2

#: How long a replacement worker may take to answer its first request.
_SERVE_DEADLINE_S = 30.0

#: A destructive delete presented without its confirmation phrase: refused
#: before execution and recorded as a durable authorization/confirmation
#: denial attributed to the presenting credential.
_DENIAL_CODE = "DESTRUCTIVE_CONFIRMATION_REQUIRED"
_DENIED_BODY = {
    "operations": [{
        "operation": "delete", "where": [{"field": "value", "operator": "eq", "value": "x"}], "destructive": True,
    }],
}
_QUERY_BODY = {"select": ["value"], "page": {"size": 1}}


def _request(method: str, url: str, bearer: str, body: "dict[str, Any] | None" = None, *, timeout: float = 30.0) -> "tuple[int, dict[str, Any]]":
    """Returns `(status, decoded_json)` for a success or an HTTP error
    response; never raises for a 4xx/5xx (the drive counts both)."""
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(
        url, method=method, data=data,
        headers={"authorization": f"Bearer {bearer}", "content-type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            return response.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        return exc.code, (json.loads(raw) if raw else {})


def _parent_pid(pid: int) -> int:
    result = subprocess.run(["ps", "-o", "ppid=", "-p", str(pid)], stdout=subprocess.PIPE, text=True)
    return int(result.stdout.strip())


def _served_by(launcher: Any, pids: "list[int]", *, deadline_s: float = _SERVE_DEADLINE_S) -> "set[int]":
    """Sends concurrent batches of authenticated reads until at least one
    of `pids` shows up as the responding worker in the pid-tagged access
    log (lines this call itself appended), or `deadline_s` passes. Returns
    the set of responding pids seen from `pids`."""
    since = launcher.access_log_line_count()
    deadline = time.monotonic() + deadline_s
    url = f"{launcher.data_base_url}/capabilities"
    while True:
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda _i: _request("GET", url, launcher.runtime_bearer), range(8)))
        seen = set(launcher.access_log_pids_for_status(200, since=since)) & set(pids)
        if seen or time.monotonic() >= deadline:
            return seen


def _audit_events_for(launcher: Any, audit_bearer: str, actor_id: str, page_limit: int) -> "list[dict[str, Any]]":
    """Every event `audit_query` currently returns whose `actor_id` is
    `actor_id` (the read is unfiltered; the narrowing is the client's)."""
    url = f"{launcher.control_base_url}/audit/query"
    events: "list[dict[str, Any]]" = []
    after = None
    while True:
        request_body: "dict[str, Any]" = {"limit": page_limit}
        if after is not None:
            request_body["after"] = after
        status, body = _request("POST", url, audit_bearer, request_body)
        if status == 429 or body.get("code") == "LIMIT_EXCEEDED":
            return events
        assert status == 200, f"audit_query answered {status}: {body!r}"
        page = body.get("events", [])
        events.extend(event for event in page if event.get("actor_id") == actor_id)
        if len(page) < page_limit:
            return events
        after = page[-1].get("cursor")


def _denial_total(events: "list[dict[str, Any]]") -> int:
    """Sum of the occurrences the refusal events represent (`count` absent
    means one)."""
    return sum(
        event.get("count", 1) for event in events
        if event.get("outcome") == "deny" and event.get("reason_code") == _DENIAL_CODE
    )


@pytest.fixture(scope="module")
def process_loss_deployment(launcher_class: type) -> SimpleNamespace:
    """One launcher per peer, started for this file alone: workers=2,
    the short window and short audit writer timeouts, one probe entity and
    one `role=audit` control credential."""
    launcher = launcher_class()
    launcher.start(
        ceilings={"data": _WORKERS, "control": _WORKERS}, workers=_WORKERS,
        coalescing_window_ms=_WINDOW_MS, audit_writer_timeouts_ms=_WRITER_TIMEOUTS_MS,
    )
    try:
        launcher.create_probe_entity(_PROBE_ENTITY, ["value"])
        audit_bearer = launcher.issue_audit_credential()
        _status, data_document = _request("GET", f"{launcher.data_base_url}/capabilities", launcher.runtime_bearer)
        yield SimpleNamespace(launcher=launcher, audit_bearer=audit_bearer, data_document=data_document)
    finally:
        launcher.stop()


def _served_audit_capability(deployment: SimpleNamespace) -> "dict[str, Any]":
    launcher = deployment.launcher
    status, document = _request("GET", f"{launcher.control_base_url}/capabilities", deployment.audit_bearer)
    assert status == 200, f"control capabilities answered {status}: {document!r}"
    return document["capabilities"]["audit_query"]


@pytest.fixture(scope="module")
def process_loss_drive(process_loss_deployment: SimpleNamespace) -> SimpleNamespace:
    """The drive described in the module docstring. Records what happened;
    asserts nothing -- each observation is its own test."""
    deployment = process_loss_deployment
    launcher = deployment.launcher
    audit_capability = _served_audit_capability(deployment)
    actor_id, bearer = launcher.issue_runtime_credential_with_id()
    workers_before = launcher.worker_pids()
    since = launcher.access_log_line_count()

    query_url = f"{launcher.data_base_url}/data/{_PROBE_ENTITY}/query"
    denial_url = f"{launcher.data_base_url}/data/{_PROBE_ENTITY}/mutations"
    denials = [_request("POST", denial_url, bearer, _DENIED_BODY) for _ in range(_DENIALS)]
    successes = [_request("POST", query_url, bearer, _QUERY_BODY) for _ in range(_SUCCESSES)]
    last_response_at = time.monotonic()

    denial_statuses = {status for status, _body in denials}
    denial_pids = [
        pid for status in denial_statuses for pid in launcher.access_log_pids_for_status(status, since=since)
    ]
    kill_started_at = time.monotonic()
    replacements = launcher.kill_workers(workers_before)
    kill_returned_at = time.monotonic()

    sent_request_ids = [body.get("request_id") for status, body in successes if status == 200]
    poll_bound_s = (
        launcher.coalescing_window_ms() / 1000.0 + audit_capability["visibility_lag_ms"] / 1000.0 + _POLL_MARGIN_S
    )
    page_limit = min(1000, audit_capability.get("max_limit", 1000))
    poll_started_at = time.monotonic()
    polls = 0
    events: "list[dict[str, Any]]" = []
    while True:
        polls += 1
        events = _audit_events_for(launcher, deployment.audit_bearer, actor_id, page_limit)
        seen_ids = {event.get("request_id") for event in events}
        complete = set(sent_request_ids) <= seen_ids and _denial_total(events) >= len(denials)
        if complete or time.monotonic() - poll_started_at >= poll_bound_s:
            break
        time.sleep(_POLL_INTERVAL_S)

    return SimpleNamespace(
        launcher=launcher, actor_id=actor_id,
        requests_per_minute=deployment.data_document["limits"]["requests_per_minute"],
        successes=successes, denials=denials, denial_statuses=denial_statuses, denial_pids=denial_pids,
        workers_before=workers_before, replacements=replacements,
        response_to_kill_s=kill_started_at - last_response_at,
        kill_and_replace_s=kill_returned_at - kill_started_at,
        sent_request_ids=sent_request_ids, events=events, polls=polls,
        poll_bound_s=poll_bound_s, poll_elapsed_s=time.monotonic() - poll_started_at,
    )


# ---------------------------------------------------------------------------
# launcher helpers
# ---------------------------------------------------------------------------


def test_c33_worker_pid_list_holds_exactly_the_workers(process_loss_deployment: SimpleNamespace) -> None:
    """`worker_pids()` returns the `workers` data-plane worker processes
    and nothing else of the process group: each is a `multiprocessing`
    spawn child of the supervisor, the supervisor (the group leader, and
    the parent of every one of them) is not among them, and the pids that
    answer requests are among them."""
    launcher = process_loss_deployment.launcher
    workers = launcher.worker_pids()
    assert len(workers) == _WORKERS, f"worker_pids() returned {workers!r}, expected {_WORKERS} pids"
    supervisors = {_parent_pid(pid) for pid in workers}
    assert len(supervisors) == 1, f"workers {workers!r} have more than one parent: {supervisors!r}"
    (supervisor,) = supervisors
    assert supervisor not in workers, f"the supervisor {supervisor} is listed as a worker: {workers!r}"
    assert all(os.getpgid(pid) == supervisor for pid in workers), f"workers {workers!r} are not in the supervisor's group"
    for pid in workers:
        command = sh._process_cmdline(pid)
        assert "multiprocessing.spawn" in command, f"pid {pid} is not a spawned worker: {command!r}"
    since = launcher.access_log_line_count()
    url = f"{launcher.data_base_url}/capabilities"
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda _i: _request("GET", url, launcher.runtime_bearer), range(8)))
    served = set(launcher.access_log_pids_for_status(200, since=since))
    assert served, "no request was logged (空振り -- nothing was exercised)"
    assert served <= set(workers), f"pids {sorted(served - set(workers))!r} answered requests but are not in worker_pids() {workers!r}"


def test_c33_kill_helper_returns_only_after_the_supervisor_replaced_the_worker(process_loss_deployment: SimpleNamespace) -> None:
    """After `kill_workers([pid])` returns, the killed pid no longer
    exists, the supervisor has started a replacement (a new pid, so the
    worker count is back to `workers`), and a replacement answers
    requests."""
    launcher = process_loss_deployment.launcher
    before = launcher.worker_pids()
    assert len(before) == _WORKERS, f"expected {_WORKERS} workers before the kill, found {before!r}"
    victim = before[0]
    replacements = launcher.kill_workers([victim])
    with pytest.raises(ProcessLookupError):
        os.kill(victim, 0)
    assert len(replacements) == 1 and replacements[0] not in before, (
        f"kill_workers([{victim}]) returned {replacements!r}, expected one new pid (workers were {before!r})"
    )
    after = launcher.worker_pids()
    assert sorted(after) == sorted(set(before[1:]) | set(replacements)), f"workers after the kill: {after!r}"
    served = _served_by(launcher, replacements)
    assert served, f"the replacement {replacements!r} never answered a request within {_SERVE_DEADLINE_S}s"


def test_c33_short_window_start_serves_the_window_it_was_given(process_loss_deployment: SimpleNamespace) -> None:
    """The coalescing window served in the control plane's own
    `audit_query` capability is the value `start()` was given, and the
    launcher reports the same value."""
    served = _served_audit_capability(process_loss_deployment)["coalescing_window_ms"]
    assert served == _WINDOW_MS, f"served coalescing_window_ms was {served!r}, start() was given {_WINDOW_MS}"
    assert process_loss_deployment.launcher.coalescing_window_ms() == _WINDOW_MS


# ---------------------------------------------------------------------------
# the drive's preconditions and the kill
# ---------------------------------------------------------------------------


def test_c33_drive_stays_inside_the_rate_bound_and_one_worker_handles_two_refusals(process_loss_drive: SimpleNamespace) -> None:
    """The drive is the drive the module docstring describes: `N + M` is
    inside `requests_per_minute`; `M >= workers + 1` and the access log
    shows a worker that handled two or more refusals; every success is a
    200 with its own `request_id` and every refusal the one denial (the
    contract fixes no status for it, so the access-log lines are read at the
    status the responses carried); the
    kill followed the last response by less than
    `_MAX_LAST_RESPONSE_TO_KILL_S`."""
    drive = process_loss_drive
    workers = len(drive.workers_before)
    assert workers == _WORKERS, f"expected {_WORKERS} workers before the drive, found {drive.workers_before!r}"
    assert len(drive.successes) + len(drive.denials) <= drive.requests_per_minute, (
        f"{len(drive.successes)} + {len(drive.denials)} requests exceed requests_per_minute {drive.requests_per_minute}"
    )
    assert len(drive.denials) >= workers + 1, (
        f"{len(drive.denials)} refusals cannot put two on one of {workers} workers (need at least {workers + 1})"
    )
    assert [status for status, _body in drive.successes] == [200] * len(drive.successes), drive.successes
    assert len(drive.sent_request_ids) == len(drive.successes)
    assert all(drive.sent_request_ids), f"a success carried no request_id: {drive.successes!r}"
    assert len(set(drive.sent_request_ids)) == len(drive.sent_request_ids), "two successes carried the same request_id"
    assert [body.get("code") for _status, body in drive.denials] == [_DENIAL_CODE] * len(drive.denials), drive.denials
    assert len(drive.denial_statuses) == 1, f"the refusals carried more than one status: {drive.denial_statuses!r}"
    assert len(drive.denial_pids) == len(drive.denials), (
        f"the access log holds {len(drive.denial_pids)} refusal lines for {len(drive.denials)} refusals (空振り)"
    )
    per_worker = Counter(drive.denial_pids)
    assert max(per_worker.values()) >= 2, f"no worker handled two refusals: {dict(per_worker)!r}"
    assert set(per_worker) <= set(drive.workers_before), (
        f"refusals were answered by {sorted(set(per_worker) - set(drive.workers_before))!r}, not among the workers {drive.workers_before!r}"
    )
    assert drive.response_to_kill_s < _MAX_LAST_RESPONSE_TO_KILL_S, (
        f"the kill followed the last response by {drive.response_to_kill_s:.2f}s, "
        f"limit {_MAX_LAST_RESPONSE_TO_KILL_S}s"
    )


def test_c33_every_worker_is_killed_and_replaced(process_loss_drive: SimpleNamespace) -> None:
    """The SIGKILL took every worker that was serving the drive (`kill_
    workers` was handed exactly `workers_before`), each is gone, the
    supervisor started as many replacements, and a replacement answers
    requests."""
    drive = process_loss_drive
    launcher = drive.launcher
    assert len(drive.workers_before) == _WORKERS
    for pid in drive.workers_before:
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)
    assert len(drive.replacements) == _WORKERS, f"replacements {drive.replacements!r} for workers {drive.workers_before!r}"
    assert not set(drive.replacements) & set(drive.workers_before)
    served = _served_by(launcher, drive.replacements)
    assert served, f"no replacement of {drive.replacements!r} answered a request within {_SERVE_DEADLINE_S}s"


# ---------------------------------------------------------------------------
# the condition: evidence read back after the kill
# ---------------------------------------------------------------------------


def test_c33_returned_successes_keep_their_audit_event_after_the_kill(process_loss_drive: SimpleNamespace) -> None:
    """Every success the service returned before the kill has an event in
    `audit_query` whose `request_id` is the one the response carried
    (events narrowed to this drive's `actor_id`)."""
    drive = process_loss_drive
    assert drive.sent_request_ids, "the drive sent no successful request (空振り)"
    assert drive.events, (
        f"audit_query returned no event for actor {drive.actor_id!r} within {drive.poll_bound_s:.1f}s "
        f"({drive.polls} polls): the read path observed nothing (空振り)"
    )
    seen = {event.get("request_id") for event in drive.events}
    missing = [request_id for request_id in drive.sent_request_ids if request_id not in seen]
    assert not missing, (
        f"{len(missing)} of {len(drive.sent_request_ids)} returned successes have no audit event after "
        f"{drive.poll_elapsed_s:.1f}s ({drive.polls} polls, bound {drive.poll_bound_s:.1f}s): request_id {missing!r}; "
        f"{len(drive.events)} events were returned for the actor"
    )


def test_c33_denial_count_total_survives_the_kill(process_loss_drive: SimpleNamespace) -> None:
    """The refusal events `audit_query` returns for this drive's `actor_id`
    total `M` occurrences (an event without `count` stands for one)."""
    drive = process_loss_drive
    assert drive.denials, "the drive sent no refusal (空振り)"
    assert drive.events, (
        f"audit_query returned no event for actor {drive.actor_id!r} within {drive.poll_bound_s:.1f}s "
        f"({drive.polls} polls): the read path observed nothing (空振り)"
    )
    total = _denial_total(drive.events)
    assert total == len(drive.denials), (
        f"refusal events total {total} occurrences, expected {len(drive.denials)} (after {drive.poll_elapsed_s:.1f}s, "
        f"{drive.polls} polls, bound {drive.poll_bound_s:.1f}s): "
        f"{[(e.get('event_class'), e.get('count', 1)) for e in drive.events if e.get('reason_code') == _DENIAL_CODE]!r}"
    )
