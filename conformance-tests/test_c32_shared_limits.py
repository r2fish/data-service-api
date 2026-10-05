"""新条件 (a)/(b) -- `concurrency`/`requests_per_minute` が 2 worker をまた
いで宣言値ちょうどで効くこと (design docs/design/MULTI_PROCESS_WORKER_V0_1.md
D-4, 裁定 12/14/23/32)。

Drives every launcher registered in `conformance-tests/registry.json`'s own
`composition_roots` section (`conftest.py`'s `launcher_class` fixture,
shared with `test_c26_composition_root.py`) through a workers=2 startup
form (ceiling=2), creates one real probe entity via the launcher's own
developer credential, then:

  新条件 (a) `concurrency`: holds the probe entity's own table under the
  launcher's own privileged `LOCK TABLE ... IN ACCESS EXCLUSIVE MODE`,
  sends `L_c + 2` new connections concurrently against that entity (under
  a runtime credential issued fresh for this one observation, shared with
  no other request), and asserts exactly `L_c` stay in flight while the
  lock holds (the other 2 refused with `LIMIT_EXCEEDED`, `details.limit_
  class: concurrency`, observed before the lock releases), and that the
  in-flight requests' own PostgreSQL sessions -- waiting on that same lock
  -- carry 2 or more distinct worker pids (parsed out of `application_
  name`).

  新条件 (b) `requests_per_minute`: sends `2 * L_r` new connections (under
  a SEPARATE runtime credential, fresh for this observation and shared
  with no other request in this file), in waves never exceeding `L_c`
  concurrently outstanding, and asserts exactly `L_r` receive `200`,
  exactly `L_r` receive `LIMIT_EXCEEDED` with `details.limit_class:
  requests_per_minute`, and the `200` responses' own worker pid (read
  back from the data plane's pid-tagged access log, scoped to the lines
  this drive itself appended) take 2 or more distinct values.

Design 裁定12: a peer may honestly declare `concurrency`/`requests_per_
minute` as `enforced` OR `deployment_required` at ceiling >= 2 -- only a
peer declaring `enforced` is held to (a)/(b) above; one declaring
`deployment_required` stays conformant without them. Each (a)/(b) test
below therefore reads the served declaration first and cross-checks it
(`test_c26_composition_root.cross_check_limit_enforcement_declaration`,
mirroring `test_c30_keyset_paging.py`'s own `observed_branch` cross-check
shape) against whether THIS launcher actually configured the wiring
design 裁定27 requires (`RealServer*.data_multi_process_mapping_
configured()`) before deciding whether to drive the body at all -- never
driven unconditionally, and never skipped without that check (`OPERATING_
CONDITIONS.md` §1.5 の 32: a `deployment_required` branch records why it
did not drive the body, it does not silently vanish).

`errors.details_vocabulary` (contract) never fixes an HTTP status for
`LIMIT_EXCEEDED`; a denial is identified by its own `code`/`details.
limit_class` fields, never a bare status code (one registered peer answers
`413` for this same denial, another `429`).
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from typing import Any

import pytest

from test_c26_composition_root import configured_for_limit_class, cross_check_limit_enforcement_declaration

pytestmark = pytest.mark.condition("C-32")

#: Kept short and specific so it can never collide with a name any OTHER
#: test file's own probe entities use on a shared throwaway platform.
_PROBE_ENTITY = "multi_process_shared_limit_probe"

_FORM_LABEL = "ceiling=2/workers=2"


def _waiter_application_name_re(peer_token: str) -> "re.Pattern[str]":
    """Review finding N1 (measured): a fixed, lowercase-only pattern
    (`^[a-z0-9]+:data:\\d+$`) rejects the ACTUAL `application_name` shape
    the work order's own completion conditions 68/126 require WP-2/WP-3
    to produce -- `r2db-api:data:<pid>` and `MitateDB-api:data:<pid>`
    (`WORK_ORDER_R113_MULTI_PROCESS_WORKER_V1.md`, completion conditions 68/126) -- both carry
    a `-` and MitateDB's own carries uppercase letters, so `assert not
    unmatched` would stay red forever even after WP-2/WP-3 land the real
    tagging. Built from `launcher.name` (the SAME per-peer token already
    used by `conformance-tests/registry.json` and every `RealServer*`
    class's own `name` class attribute -- `real_server_r2db.py::RealServerR2db.name`,
    `real_server_mitatedb.py::RealServerMitateDB.name`) instead of a generic charset, so it
    matches ONLY that one launcher's own documented token, exactly,
    followed by `:data:<pid>` -- never a different peer's name, a
    substring of it, or a name with a different case."""
    return re.compile(rf"^{re.escape(peer_token)}:data:(?P<pid>\d+)$")


def _get_json(url: str, bearer: str, *, timeout: float = 30.0) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"authorization": f"Bearer {bearer}"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read()
    return json.loads(raw) if raw else {}


def _post(url: str, bearer: str, body: dict[str, Any], *, timeout: float) -> "tuple[int, dict[str, Any]]":
    """Posts `body` and returns `(status_code, decoded_json)` on EITHER a
    success or an HTTP error response (never raises for a 4xx/5xx -- the
    tests below need to count both outcomes). The decoded body is what the
    tests below classify a denial BY (`code`/`details.limit_class`), never
    the bare status code, which the contract does not fix."""
    data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        url, method="POST", data=data,
        headers={"authorization": f"Bearer {bearer}", "content-type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            return response.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        return exc.code, (json.loads(raw) if raw else {})


def _is_limit_exceeded(body: dict[str, Any], limit_class: str) -> bool:
    return body.get("code") == "LIMIT_EXCEEDED" and body.get("details", {}).get("limit_class") == limit_class


@pytest.fixture(scope="module")
def shared_limit_deployment(launcher_class: type) -> SimpleNamespace:
    """One launcher, started ceiling=2/workers=2 (裁定 35's 3rd form: the
    one where both new conditions are actually driven), with one real
    probe entity created through the developer credential. `concurrency_
    configured`/`rate_configured` are the TWO separate accessor readings
    design D-3 (4)/裁定18/27 require (`concurrency`'s own mapping depends
    on workers vs. ceiling; `requests_per_minute`'s own mapping depends
    only on whether the PostgreSQL-backed rate-row strategy is wired) --
    see `test_c26_composition_root.configured_for_limit_class`'s own
    docstring; both are constant for this fixture's own single, fixed
    ceiling=2/workers=2 form, so no snapshot timing concern applies here
    the way it does for `test_c26_composition_root.py`'s own 3-form
    fixture. Read-only setup calls (`create_probe_entity`, this one `GET
    /capabilities`) use the launcher's own default `runtime_bearer` --
    every request-rate-scoped observation below issues and uses its OWN,
    separate credential instead (`issue_runtime_credential()`), so none of
    them ever shares a `requests_per_minute` window with this setup call,
    with each other, or with a peer test module driven on the SAME xdist
    worker."""
    launcher = launcher_class()
    launcher.start(ceilings={"data": 2, "control": 2}, workers=2)
    try:
        launcher.create_probe_entity(_PROBE_ENTITY, ["value"])
        doc = _get_json(f"{launcher.data_base_url}/capabilities", launcher.runtime_bearer)
        concurrency_configured = configured_for_limit_class(launcher, "concurrency")
        rate_configured = configured_for_limit_class(launcher, "requests_per_minute")
        yield SimpleNamespace(
            launcher=launcher, doc=doc,
            concurrency_configured=concurrency_configured, rate_configured=rate_configured,
        )
    finally:
        launcher.stop()


def _query_url(launcher: Any) -> str:
    return f"{launcher.data_base_url}/data/{_PROBE_ENTITY}/query"


# ---------------------------------------------------------------------------
# 新条件 (a): concurrency
# ---------------------------------------------------------------------------


def test_c32_concurrency_in_flight_count_matches_declared_bound(shared_limit_deployment: SimpleNamespace) -> None:
    """`L_c + 2` concurrent new connections against the locked probe
    entity, under a credential issued fresh for this one observation --
    exactly `L_c` stay in flight (blocked on the launcher's own held lock)
    while 2 are refused (`LIMIT_EXCEEDED`, `details.limit_class:
    concurrency`) BEFORE the lock releases, never waiting on it at all.
    Design 裁定12: only driven when the served document declares
    `concurrency` `enforced`, cross-checked first against whether this
    launcher actually configured the wiring 裁定27 requires -- a peer
    honestly declaring `deployment_required` is not held to this body at
    all, and this test records that branch and passes without driving it."""
    ns = shared_limit_deployment
    value = ns.doc["limit_enforcement"]["concurrency"]
    enforced = cross_check_limit_enforcement_declaration(
        value, configured=ns.concurrency_configured, limit_class="concurrency", form_label=_FORM_LABEL,
    )
    if not enforced:
        # Declared `deployment_required` (裁定12): the new condition does
        # not bind for this peer at this ceiling. Nothing further to
        # drive or assert -- recorded above, passes here.
        return

    launcher = ns.launcher
    l_c = ns.doc["limits"]["concurrency"]
    assert l_c > 0, f"declared concurrency was {l_c!r}, expected a positive int"
    total = l_c + 2
    bearer = launcher.issue_runtime_credential()

    hold = launcher.hold_entity_storage_lock(_PROBE_ENTITY, bearer=bearer)
    try:
        results: "list[tuple[int, dict[str, Any]] | None]" = [None] * total

        def _fire(i: int) -> None:
            results[i] = _post(
                _query_url(launcher), bearer,
                {"select": ["value"], "page": {"size": 1}},
                timeout=hold.hold_s + 15.0,
            )

        with ThreadPoolExecutor(max_workers=total) as pool:
            futures = [pool.submit(_fire, i) for i in range(total)]
            # Give every immediately-refused request time to land while
            # the lock is STILL held -- this is the moment "how many are
            # genuinely in flight" is observable at all, and the moment a
            # denial's own body must be read to count as "before release".
            time.sleep(min(hold.hold_s * 0.6, 3.0))
            done_before_release = [i for i, f in enumerate(futures) if f.done()]
            in_flight = total - len(done_before_release)
            for f in futures:
                f.result(timeout=hold.hold_s + 30.0)
    finally:
        hold.release_now()

    denied_concurrency_before_release = sum(
        1 for i in done_before_release
        if results[i] is not None and _is_limit_exceeded(results[i][1], "concurrency")
    )
    assert in_flight == l_c, (
        f"in-flight count while the lock was held was {in_flight}, expected exactly the declared "
        f"concurrency bound {l_c} (sent {total} = L_c + 2; "
        f"{len(done_before_release)} returned before the lock released)"
    )
    assert denied_concurrency_before_release == 2, (
        f"LIMIT_EXCEEDED/concurrency count observed BEFORE the lock released was "
        f"{denied_concurrency_before_release}, expected exactly 2 (sent L_c + 2 = {total}); "
        f"bodies returned before release: {[results[i][1] for i in done_before_release]!r}"
    )


def test_c32_concurrency_lock_waiters_span_2_or_more_workers(shared_limit_deployment: SimpleNamespace) -> None:
    """While `L_c + 2` requests are in flight against the locked probe
    entity, the PostgreSQL sessions actually WAITING on that lock
    (`pg_locks`/`pg_stat_activity`) carry an `application_name` shaped
    `"<peer>:data:<pid>"`, and those pids take 2 or more distinct values
    -- i.e. genuinely spread across both data-plane workers, never all
    funneled through one. Design 裁定12: same declaration/wiring
    cross-check and branch as `test_c32_concurrency_in_flight_count_
    matches_declared_bound` above."""
    ns = shared_limit_deployment
    value = ns.doc["limit_enforcement"]["concurrency"]
    enforced = cross_check_limit_enforcement_declaration(
        value, configured=ns.concurrency_configured, limit_class="concurrency", form_label=_FORM_LABEL,
    )
    if not enforced:
        return

    launcher = ns.launcher
    l_c = ns.doc["limits"]["concurrency"]
    total = l_c + 2
    bearer = launcher.issue_runtime_credential()

    hold = launcher.hold_entity_storage_lock(_PROBE_ENTITY, bearer=bearer)
    try:
        with ThreadPoolExecutor(max_workers=total) as pool:
            futures = [
                pool.submit(_post, _query_url(launcher), bearer,
                            {"select": ["value"], "page": {"size": 1}}, timeout=hold.hold_s + 15.0)
                for _ in range(total)
            ]
            time.sleep(min(hold.hold_s * 0.6, 3.0))
            waiter_names = launcher.lock_waiter_application_names(_PROBE_ENTITY)
            hold.release_now()
            for f in futures:
                f.result(timeout=hold.hold_s + 30.0)
    finally:
        hold.release_now()

    assert waiter_names, "lock_waiter_application_names observed 0 waiting sessions (空振り -- nothing was exercised)"
    name_re = _waiter_application_name_re(launcher.name)
    unmatched = [name for name in waiter_names if name_re.match(name) is None]
    assert not unmatched, (
        f"lock-waiting session(s) carried an application_name not shaped "
        f"'{launcher.name}:data:<pid>': {sorted(set(unmatched))!r} (full list: {waiter_names!r})"
    )
    waiter_pids = {int(name_re.match(name).group("pid")) for name in waiter_names}
    assert len(waiter_pids) >= 2, (
        f"lock-waiting sessions' own worker pids were {sorted(waiter_pids)!r} (only {len(waiter_pids)} distinct) "
        f"-- expected 2 or more (spread across >= 2 workers)"
    )


# ---------------------------------------------------------------------------
# 新条件 (b): requests_per_minute
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def rate_probe_results(shared_limit_deployment: SimpleNamespace) -> SimpleNamespace:
    """Sends `2 * L_r` new connections against the (unlocked) probe
    entity, under a credential issued fresh for THIS one observation
    (shared with no other request in this file), in waves never exceeding
    `L_c` concurrently outstanding (a bounded `ThreadPoolExecutor`), and
    records each one's own decoded body -- and, for a `200`, the
    responding worker's own pid (pid-tagged access log, scoped via
    `since=` to the lines THIS drive itself appends). Shared by all 3
    completion-condition tests below so the (expensive: up to 2 * 600 =
    1200 real HTTP round trips) drive itself only happens once.

    Design 裁定12: `declared` is the RAW served value, read here but never
    asserted on -- the actual declaration/wiring cross-check (and the
    decision whether the new condition binds at all) is each dependent
    test's OWN job (`cross_check_limit_enforcement_declaration`), so a
    genuine mismatch is reported against the specific completion condition
    it belongs to, not smuggled into this shared fixture's own setup. When
    `declared` is not `enforced`, the (expensive) drive itself is skipped
    -- a peer honestly declaring `deployment_required` owes nothing here
    (裁定12), so there is nothing to spend 1200 real round trips proving."""
    launcher = shared_limit_deployment.launcher
    l_c = shared_limit_deployment.doc["limits"]["concurrency"]
    l_r = shared_limit_deployment.doc["limits"]["requests_per_minute"]
    declared = shared_limit_deployment.doc["limit_enforcement"]["requests_per_minute"]
    if declared != "enforced":
        return SimpleNamespace(
            declared=declared, l_c=l_c, l_r=l_r, total=0, outcomes=[],
            ok_count=0, denied_rate_count=0, other_count=0, ok_pids=[],
        )

    total = 2 * l_r
    bearer = launcher.issue_runtime_credential()
    since = launcher.access_log_line_count()

    outcomes: "list[tuple[int, dict[str, Any]] | None]" = [None] * total

    def _fire(i: int) -> None:
        outcomes[i] = _post(
            _query_url(launcher), bearer,
            {"select": ["value"], "page": {"size": 1}}, timeout=30.0,
        )

    with ThreadPoolExecutor(max_workers=max(1, l_c)) as pool:
        list(pool.map(_fire, range(total)))

    ok_count = sum(1 for status, _body in outcomes if status == 200)
    denied_rate_count = sum(1 for _status, body in outcomes if _is_limit_exceeded(body, "requests_per_minute"))
    other_count = total - ok_count - denied_rate_count
    ok_pids = launcher.access_log_pids_for_status(200, since=since)
    return SimpleNamespace(
        declared=declared, l_c=l_c, l_r=l_r, total=total, outcomes=outcomes,
        ok_count=ok_count, denied_rate_count=denied_rate_count, other_count=other_count,
        ok_pids=ok_pids,
    )


def test_c32_requests_per_minute_200_count_matches_declared_bound(
    shared_limit_deployment: SimpleNamespace, rate_probe_results: SimpleNamespace,
) -> None:
    """`2 * L_r` new connections -- exactly `L_r` receive `200`. Design
    裁定12: only driven/asserted when the served document declares
    `requests_per_minute` `enforced`, cross-checked against this
    launcher's own configured wiring first."""
    enforced = cross_check_limit_enforcement_declaration(
        rate_probe_results.declared, configured=shared_limit_deployment.rate_configured,
        limit_class="requests_per_minute", form_label=_FORM_LABEL,
    )
    if not enforced:
        return
    ns = rate_probe_results
    assert ns.ok_count == ns.l_r, (
        f"200 count was {ns.ok_count}, expected exactly the declared requests_per_minute bound "
        f"{ns.l_r} (sent 2 * L_r = {ns.total}; other={ns.other_count})"
    )


def test_c32_requests_per_minute_429_count_matches_declared_bound(
    shared_limit_deployment: SimpleNamespace, rate_probe_results: SimpleNamespace,
) -> None:
    """The remaining `L_r` receive `LIMIT_EXCEEDED` with `details.limit_
    class: requests_per_minute` (never `concurrency` -- this drive never
    exceeds the declared concurrency bound at once), and no OTHER outcome
    occurs at all. Design 裁定12: same declaration/wiring cross-check and
    branch as the `200` count above."""
    enforced = cross_check_limit_enforcement_declaration(
        rate_probe_results.declared, configured=shared_limit_deployment.rate_configured,
        limit_class="requests_per_minute", form_label=_FORM_LABEL,
    )
    if not enforced:
        return
    ns = rate_probe_results
    assert ns.denied_rate_count == ns.l_r, (
        f"LIMIT_EXCEEDED/requests_per_minute count was {ns.denied_rate_count}, expected exactly the declared "
        f"requests_per_minute bound {ns.l_r} (sent 2 * L_r = {ns.total}; 200={ns.ok_count} other={ns.other_count})"
    )
    assert ns.other_count == 0, (
        f"{ns.other_count} response(s) were neither 200 nor LIMIT_EXCEEDED/requests_per_minute: "
        f"{[body for status, body in ns.outcomes if not (status == 200 or _is_limit_exceeded(body, 'requests_per_minute'))]!r}"
    )


def test_c32_requests_per_minute_200_pids_span_2_or_more_workers(
    shared_limit_deployment: SimpleNamespace, rate_probe_results: SimpleNamespace,
) -> None:
    """The `200` responses' own worker pid (pid-tagged access log, scoped
    to THIS drive's own lines) take 2 or more distinct values -- spread
    across both workers, not funneled through one. Not itself named by
    design 裁定12's own branch text, but gated the SAME way for
    consistency: `rate_probe_results` never drives the underlying traffic
    at all when the new condition does not bind, so there is nothing this
    leg could observe in that branch either."""
    enforced = cross_check_limit_enforcement_declaration(
        rate_probe_results.declared, configured=shared_limit_deployment.rate_configured,
        limit_class="requests_per_minute", form_label=_FORM_LABEL,
    )
    if not enforced:
        return
    ns = rate_probe_results
    assert ns.ok_pids, "access_log_pids_for_status(200, since=...) observed 0 pids (空振り -- nothing was exercised)"
    assert len(set(ns.ok_pids)) >= 2, (
        f"200 responses' own worker pids were {sorted(set(ns.ok_pids))!r} (only {len(set(ns.ok_pids))} distinct) "
        f"-- expected 2 or more (spread across >= 2 workers)"
    )
