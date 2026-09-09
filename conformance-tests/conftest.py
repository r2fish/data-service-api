"""Adapter discovery and the parametrized `adapter` fixture (design section
3 / section 3's `registry.json` contract).

Discovery happens once, at module-import time (i.e. during pytest
collection), by reading `registry.json`, adding each registered peer's
`conformance/` directory to `sys.path`, importing its adapter module, and
calling that module's `build_adapter()`.

If a `"required": true` adapter fails to import or build, this module
raises immediately during collection. That turns into a pytest collection
error for the whole run -- a hard FAIL, never a skip. A skip would silently
convert "this peer's conformance is unverified" into "permitted" (design
principle 4; design section 3: "skip is 'silent permission of the
unknown', which violates principle 4").
"""
from __future__ import annotations

import dataclasses
import importlib
import json
import re
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from adapter import ConformanceAdapter, ConformanceDenial, fresh_identifier, load_contract_error_codes

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = Path(__file__).parent / "registry.json"


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers", "condition(cid): common conformance condition identifier"
    )


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(config: pytest.Config, items: list) -> None:
    """Phase 6 WP-1 addendum B (docs/work-orders/WORK_ORDER_PHASE6_
    CONTRACT_160_V1.md): tags every collected item with an `xdist_group`
    marker equal to its OWN `adapter` fixture param id, so `pytest -n 5
    --dist loadgroup` schedules every test sharing one adapter param onto
    the SAME worker process -- the session-scoped `adapter` fixture (and
    each HTTP+PostgreSQL plug's own real platform database/connection
    pools) stays confined to one process exactly as in a solo run, rather
    than being torn down and rebuilt (or, worse, raced) across workers.
    An item with no `adapter` param at all (a whole-registry vacuity
    guard, e.g. `test_c19_every_control_surface_adapter_declares_1_6_0`,
    which calls `registered_adapters()` directly instead of taking the
    parametrized fixture) goes to one shared, fixed group -- these guards
    read already-built adapter state and do not themselves provision
    anything, so co-scheduling them together (never splitting one such
    guard's own single collected item across workers, which `xdist_
    group` cannot do anyway) is safe.

    Adapted from a disposable, outside-the-repository review prototype
    (supervisor experiment, 2026-09-04, `scratchpad/xdist_by_adapter.py`,
    log `scratchpad/xdist-experiment.log`: conformance suite 422 passed
    in 117.17s under this exact grouping, 0 leftover databases/roles)
    -- this hook is deliberately no more than that prototype's own
    mechanism, placed where the shared adapter/conftest machinery it
    depends on (`request.node.callspec`) already lives.

    Harmless with no `xdist` installed at all (`pytest-xdist` not on
    `sys.path`): `pytest.mark.xdist_group` is accepted by plain pytest
    like any other custom marker (unregistered markers only WARN, never
    fail collection) and is simply ignored by a sequential run -- this
    hook adds a marker, it never imports `xdist` itself.

    `@pytest.hookimpl(tryfirst=True)` is load-bearing, not decoration
    (measured empirically, WP-1 completion report): `xdist_group`'s own
    grouping is implemented by `xdist.remote.WorkerInteractor`'s OWN
    `pytest_collection_modifyitems`, which runs on each worker's own
    local collection and encodes every item's group by APPENDING
    `@<group>` to that item's nodeid (`xdist/remote.py`) -- the master's
    `LoadGroupScheduling` scheduler (`xdist/scheduler/loadgroup.py`)
    then groups purely by that nodeid SUFFIX. Without `tryfirst=True`,
    pytest's default (LIFO-by-registration) hook order let xdist's own
    hook run BEFORE this one on at least one measured run, reading NO
    `xdist_group` marker yet (this hook had not added it) and therefore
    appending no `@group` suffix at all -- `--dist loadgroup` then
    degraded silently to plain `load` (round-robin across all `-n`
    workers), scattering one adapter's own session-scoped state, real
    Postgres connections included, across every worker. `tryfirst=True`
    forces this hook first regardless of registration order, so every
    item already carries its `xdist_group` marker by the time xdist's
    own hook reads it.
    """
    for item in items:
        callspec = getattr(item, "callspec", None)
        adapter_param = callspec.params.get("adapter") if callspec is not None else None
        # Phase 10 WP-6c (design docs/design/PHASE10_DEPLOYMENT_EVIDENCE_
        # V1.md D-1 (B) 8): an item parametrized (directly, or indirectly
        # through a fixture that itself depends on `launcher_class` below,
        # e.g. `test_c26_composition_root.py`'s own module-scoped
        # `lifecycle` fixture) over `launcher_class` carries NO `adapter`
        # param at all -- without this branch it would fall into the
        # shared `registry-guards` group below and get co-scheduled (and
        # therefore serialized onto ONE worker) with every whole-registry
        # vacuity guard in the suite, even though a C-26 item starts a
        # real, separate OS process per launcher and has nothing in
        # common with those guards' read-only checks. Grouped per
        # LAUNCHER (`c26-<peer>`) instead, so the two registered launchers
        # (r2db-api/MitateDB-api) can still run on separate xdist workers
        # concurrently -- `--dist loadgroup` schedules everything sharing
        # one group onto the SAME worker, exactly like the `adapter`
        # branch below does for each adapter's own session-scoped state.
        launcher_param = callspec.params.get("launcher_class") if callspec is not None else None
        # F9 (WP-6c review 2026-09-09): `launcher_param` is checked BEFORE
        # `adapter_param` on purpose -- no currently-collected item ever
        # carries both (a `launcher_class`-parametrized item takes no
        # `adapter` fixture, and vice versa, by construction of every
        # fixture in this file today), so this ordering is unreachable
        # code today, not a live behavior choice. If a FUTURE item ever
        # parametrized over both, a real per-process composition-root
        # launcher (an expensive, foreground-blocking OS process start)
        # should take priority over the lighter, already-amortized
        # session-scoped `adapter` state for xdist-group placement -- so
        # this order (`launcher_param` first) is deliberately kept in the
        # unreachable case too, rather than swapped, and this comment
        # records that choice instead of leaving it to be re-derived.
        if launcher_param:
            group = f"c26-{launcher_param}"
        elif adapter_param:
            group = str(adapter_param)
        else:
            group = "registry-guards"
        item.add_marker(pytest.mark.xdist_group(name=group))


def _load_registry() -> list[dict]:
    import json

    data = json.loads(REGISTRY_PATH.read_text())
    return data["adapters"]


def _discover_and_build() -> list[tuple[str, ConformanceAdapter]]:
    # Phase 10 WP-3 note (design docs/design/PHASE10_DEPLOYMENT_EVIDENCE_
    # V1.md D-2 (g)): this function builds EVERY registered adapter's
    # Python OBJECT eagerly, on EVERY xdist worker, unchanged by this WP
    # -- a socket adapter's own `build_adapter()` (WP-4) must therefore
    # bind no real port and spawn no real process from inside its own
    # `__init__`. `conformance-tests/socket_harness.py`'s own
    # `RealSocketSurface` is built exactly for this: it stays inert until
    # `.data_base_url`/`.control_base_url` is first read, so a worker
    # whose own tests never touch a given socket plug (`--dist loadgroup`
    # confines each adapter's own tests to one worker) never starts that
    # plug's nginx/uvicorn at all, even though this function still
    # constructs the (otherwise-inert) adapter OBJECT for it. This
    # function itself needs no code change for that laziness to hold --
    # it never calls anything beyond `build_adapter()`.
    entries = _load_registry()
    built: list[tuple[str, ConformanceAdapter]] = []
    required_failures: list[str] = []

    for entry in entries:
        name = entry["name"]
        module_name = entry["module"]
        required = bool(entry.get("required", False))

        conformance_dir = str(ROOT / name / "conformance")
        if conformance_dir not in sys.path:
            sys.path.insert(0, conformance_dir)

        try:
            module = importlib.import_module(module_name)
            adapter_obj = module.build_adapter()
        except Exception as exc:  # noqa: BLE001 - intentionally broad: any
            # import/build failure of a required adapter must fail the
            # suite, whatever its shape.
            if required:
                required_failures.append(f"{name} ({module_name}): {exc!r}")
                continue
            # A declared-optional adapter that fails to build is skipped
            # from the parametrization; it never silently counts as passing
            # anything either, since it contributes no fixture instance.
            continue

        if not isinstance(adapter_obj, ConformanceAdapter):
            message = (
                f"{name} ({module_name}).build_adapter() did not return a "
                f"ConformanceAdapter instance (got {type(adapter_obj)!r})"
            )
            if required:
                required_failures.append(message)
                continue
            continue

        built.append((name, adapter_obj))

    if required_failures:
        # Close whatever was already built before failing. An adapter may
        # hold external resources (the HTTP+PostgreSQL plug provisions real
        # databases and cluster-global roles), and a partially-built
        # registry that raises here never reaches the `adapter` fixture's
        # teardown -- so without this, a later adapter's failure orphans an
        # earlier adapter's resources. Cleanup failures are reported, never
        # swallowed, since a silent cleanup failure is how residue
        # accumulates unnoticed.
        for _name, _adapter in built:
            try:
                _adapter.close()
            except Exception as close_error:  # noqa: BLE001
                required_failures.append(f"{_name}: close() during rollback failed: {close_error!r}")
        raise RuntimeError(
            "required conformance adapter(s) failed to import or build; "
            "the suite fails rather than skips (design section 3, principle 4):\n"
            + "\n".join(f"  - {f}" for f in required_failures)
        )

    return built


# Discovery/build happens exactly once, at collection time. A failure here
# raises out of module import, which pytest reports as a collection error
# (a hard failure) for the whole run.
_BUILT_ADAPTERS: list[tuple[str, ConformanceAdapter]] = _discover_and_build()
_ADAPTER_NAMES: list[str] = [name for name, _ in _BUILT_ADAPTERS]
_ADAPTER_BY_NAME: dict[str, ConformanceAdapter] = dict(_BUILT_ADAPTERS)


def registered_adapters() -> dict[str, ConformanceAdapter]:
    """Public accessor for the live registry built at collection time.

    A test module that needs a registry-wide check not expressed as the
    per-adapter-parametrized `adapter`/`fx` fixtures (for example, a
    vacuity guard that must hold across *all* registered adapters at once,
    rather than being asserted once per adapter) calls this instead of
    reaching into the private `_ADAPTER_BY_NAME` from outside this module.
    Returns a fresh `dict` copy each call; mutating it does not affect the
    registry.
    """
    return dict(_ADAPTER_BY_NAME)


def _close_all_adapters() -> None:
    """Closes every built adapter exactly once, tolerating a failing
    `close()` on one adapter without skipping the rest (WP-2.5c review
    item 1). Factored out of the session-end fixture below so a test can
    invoke it directly and confirm it actually visits every adapter,
    without needing a live nested pytest session to observe fixture
    teardown timing."""
    errors: list[str] = []
    for name, adapter_obj in _BUILT_ADAPTERS:
        try:
            adapter_obj.close()
        except Exception as exc:  # noqa: BLE001 - report, never swallow
            errors.append(f"{name}: close() failed: {exc!r}")
    if errors:
        raise RuntimeError(
            "adapter close() failure(s) at session teardown:\n" + "\n".join(f"  - {e}" for e in errors)
        )


@pytest.fixture(scope="session", params=_ADAPTER_NAMES, ids=_ADAPTER_NAMES)
def adapter(request: pytest.FixtureRequest) -> ConformanceAdapter:
    """The registered `ConformanceAdapter` instances, one per registry
    entry, parametrized so every dependent test runs once per adapter with
    the adapter name as the pytest test id.

    WP-2.5c review item 1 correction: this fixture no longer closes its own
    adapter in its own finalizer. A `scope="session"` fixture that also
    carries `params` is torn down per PARAM, not once for the whole
    session -- pytest's default test-item reordering groups all tests
    sharing one param value together, and finalizes that param's fixture
    instance as soon as the LAST test needing it finishes, which can be
    long before the session itself ends (whenever collection moves on to
    the next param group). The previous docstring here ("close() is
    guaranteed to run at session teardown") was therefore not accurate --
    `registered_adapters()` (used by registry-wide guards that read
    `_ADAPTER_BY_NAME` directly, bypassing this fixture, e.g. `test_c06_
    destructive_confirmation.py`'s vacuity-guard tests) could observe an
    already-`close()`'d adapter mid-session. `close()` for every adapter
    now happens exactly once, at the real end of the session, via
    `_close_all_adapters_at_session_end` below (an autouse fixture with no
    `params` of its own, so its own single finalizer runs only when the
    whole session's fixture stack unwinds)."""
    return _ADAPTER_BY_NAME[request.param]


@pytest.fixture(scope="session", autouse=True)
def _close_all_adapters_at_session_end():
    """Session-teardown-only close, unconditionally applied (WP-2.5c
    review item 1): closes every built adapter exactly once via
    `_close_all_adapters()`. Deliberately carries no `params` of its own --
    unlike the `adapter` fixture above, a plain `scope="session"` fixture
    with no parametrization has exactly one instance for the whole run, so
    its finalizer (this generator's code after `yield`) genuinely executes
    only once, after every test in the session has finished, regardless of
    which adapter param groups ran in what order."""
    yield
    _close_all_adapters()


# ---------------------------------------------------------------------------
# Phase 10 WP-6c: `composition_roots` discovery (design docs/design/
# PHASE10_DEPLOYMENT_EVIDENCE_V1.md D-1 (B), §6.1) -- the C-26 launchers,
# a SEPARATE registry section from `adapters` above. A launcher is not a
# `ConformanceAdapter` (it is never returned by any `build_adapter()`, and
# `test_c26_composition_root.py` never touches `_BUILT_ADAPTERS`), so this
# is deliberately its own small discovery function rather than a case
# folded into `_discover_and_build`.
# ---------------------------------------------------------------------------


def _load_composition_roots() -> list[dict]:
    data = json.loads(REGISTRY_PATH.read_text())
    return data.get("composition_roots", [])


def _discover_composition_roots() -> list[tuple[str, type]]:
    """Imports each registered launcher CLASS (never an instance) at
    collection time -- mirrors `_discover_and_build`'s own eager-but-inert
    construction (design D-2 (g)), but even lighter here: importing a
    module and reading one class attribute off it performs no I/O at all
    (`RealServerR2db`/`RealServerMitateDB`'s own `__init__` is pure
    attribute assignment -- provisioning a real throwaway platform and
    starting real processes only happens inside their own `start()`,
    called explicitly by `test_c26_composition_root.py`'s own fixtures).
    A missing/malformed entry (unlike a `required: true` adapter) raises
    immediately, in the same "hard collection error, never a skip" spirit
    (design principle 4) -- there is no meaningful "optional" composition
    root."""
    entries = _load_composition_roots()
    discovered: list[tuple[str, type]] = []
    for entry in entries:
        name = entry["name"]
        module_name = entry["module"]
        class_name = entry["launcher_class"]
        conformance_dir = str(ROOT / name / "conformance")
        if conformance_dir not in sys.path:
            sys.path.insert(0, conformance_dir)
        module = importlib.import_module(module_name)
        launcher_cls = getattr(module, class_name)
        discovered.append((name, launcher_cls))
    return discovered


_COMPOSITION_ROOTS: list[tuple[str, type]] = _discover_composition_roots()
_COMPOSITION_ROOT_NAMES: list[str] = [name for name, _ in _COMPOSITION_ROOTS]
_COMPOSITION_ROOT_CLASS_BY_NAME: dict[str, type] = dict(_COMPOSITION_ROOTS)


def registered_composition_roots() -> dict[str, type]:
    """Public accessor (mirrors `registered_adapters()` above) -- the
    registered launcher CLASSES, keyed by peer name. `test_c26_
    composition_root.py`'s own non-vacuity guard (design D-1 (B) 7: "`
    composition_roots` が2件以上") reads this directly, the same shape
    `test_c19_client_self_sufficiency.py`'s own registry-wide guards
    already use for `registered_adapters()`."""
    return dict(_COMPOSITION_ROOT_CLASS_BY_NAME)


@pytest.fixture(scope="session", params=_COMPOSITION_ROOT_NAMES, ids=_COMPOSITION_ROOT_NAMES)
def launcher_class(request: pytest.FixtureRequest) -> type:
    """The registered C-26 launcher CLASSES, one per `composition_roots`
    entry, parametrized so `test_c26_composition_root.py`'s own fixtures
    run once per launcher with the peer name as the pytest test id (mirrors
    the `adapter` fixture's own parametrization above). Returns the CLASS,
    never a shared instance -- every test/fixture that needs a live
    launcher constructs (and tears down) its own instance, so no C-26 test
    can observe another one's residual state."""
    return _COMPOSITION_ROOT_CLASS_BY_NAME[request.param]


@pytest.fixture()
def fx(adapter: ConformanceAdapter):
    """A fresh `Fixture` (design section 4.2) built for each test function,
    so condition tests never share application/credential state with each
    other even though the underlying `adapter` object is session-scoped."""
    return adapter.build_fixture()


@pytest.fixture()
def isolated(adapter: ConformanceAdapter):
    """A per-test, ZERO-RESIDUE application-plane context (phase 7 WP-5),
    for condition tests that need one or more throwaway applications but
    must not permanently grow the session-scoped adapter's own
    `applications` registry: yields `adapter.isolated_application_
    surface()` (port v1.11, C-05's own primitive, design D-6.1 V2) itself,
    so a test provisions whatever applications it needs directly against
    the yielded instance (`iso.provision_application(app_id)`, normally
    via `provision_pair` below) and every one of them is deprovisioned
    automatically when this fixture's own `with` block closes at the end
    of the test.

    Measured directly (WP-5, four rounds -- recorded here so the choice is
    not re-litigated): round 1, the ordinary `fx` fixture (per test, no
    teardown of its own 2 applications) permanently registered 72
    additional applications per adapter across this WP's 36 new tests,
    turning both `test_c14_authority_boundary.py::test_c14_resource_
    bounds_published_and_enforced` and `test_c15_bootstrap_reset_
    lifecycle.py::test_c15_lifecycle_changes_emit_canonical_audit_and_
    denials_are_recorded` red on all 4 adapters. Round 2, a smaller
    module/session-scoped reduction of that SAME permanent-growth pattern
    was still not enough headroom on 3 of 4 adapters. Round 3, provisioning
    directly on the shared `adapter` with an explicit `deprovision_
    application()` teardown avoided the registry-growth problem but hit a
    DIFFERENT one on `r2db-api-http`: `deprovision_application`'s own real
    `DROP DATABASE` fails with "being accessed by other users" whenever the
    per-application connection pool a prior call opened is still live --
    only `isolated_application_surface()`'s own internal exit sequence
    knows how to close that SPECIFIC pool first (`test_c05_limit_
    declaration_agreement.py`'s own module docstring documents this same
    close-then-deprovision order for HTTP plugs), so a plain external
    `deprovision_application()` call against a used, shared-adapter
    application cannot reproduce it. This fixture is round 4: genuinely
    zero-residue (the isolated surface's own internal close-then-
    deprovision handles the pool correctly), but see `provision_pair`'s
    own docstring below for the one measured side effect of the isolated
    profile's deliberately small resource bounds that callers must still
    route around (`operation_depth` in particular)."""
    with adapter.isolated_application_surface() as iso:
        yield iso


def provision_pair(iso: ConformanceAdapter, *, app_prefix: str = "wp5") -> tuple[object, object, str]:
    """Provisions one throwaway application on `iso` (the yield of the
    `isolated` fixture above) and returns `(developer_session, runtime_
    session, application_id)` -- the same shape `test_c05_limit_
    declaration_agreement.py`'s own private `_provision_pair` already
    establishes, generalized here (module-level, importable) so WP-5's
    other new condition files share one copy rather than each keeping a
    private one.

    **Depth pitfall, measured (WP-5 round 3), stated for every caller**:
    `isolated_application_surface()`'s own small profile enforces
    `operation_depth=4` on `r2db-api`/`r2db-api-http` (not on either
    MitateDB plug, which declares this class `unavailable`). A flat
    `insert`/`attempt_mutation` sits exactly at that bound; `delete`'s own
    request shape carries its filter as a `where` LIST-of-dict (one level
    deeper than `insert`'s flat `values` dict), which trips `LIMIT_
    EXCEEDED` immediately on both r2db plugs, before whatever the caller
    was actually trying to observe. A caller that needs an unconfirmed-
    destructive denial's rich `details` mapping should reach for
    `drop_entity` instead where the peer supports it (`{"operation":
    "drop_entity", "entity": ...}` is a flat, single-level dict on every
    peer) -- `test_c04_unsupported_and_safe_errors.py` documents the exact
    per-peer branch this forces (drop_entity is `SurfaceAbsent` on
    `MitateDB-api` in-process, which has no depth problem with `delete` in
    the first place, so the branch has a real answer on every peer)."""
    app_id = fresh_identifier(app_prefix)
    iso.provision_application(app_id)
    developer = iso.authenticate(iso.issue_credential(app_id, "developer"))
    runtime = iso.authenticate(iso.issue_credential(app_id, "runtime"))
    return developer, runtime, app_id


def assert_runtime_credential_denied_schema_authority(
    surface: "ConformanceAdapter", developer: Any, runtime: Any, entity: str, *, adapter_name: str,
) -> None:
    """The denial-half vector shared by `test_c01_scope_binding.py::
    test_runtime_credential_cannot_self_elevate_to_schema_authority` and
    `test_c02_runtime_privilege_negative.py::test_c02_runtime_denied_
    create_entity_but_developer_succeeds_on_the_same_request` (WP-5
    rework, review finding 10): a runtime credential's `create_entity` is
    denied with a genuine contract error code, and schema state (the
    developer's own `entities()`) is unchanged, with the probed entity
    itself absent from it.

    Factored out here, once, rather than kept as two near-identical copies
    (WP-5 禁止事項 7, "同じ assert を二重に書かない") -- the two callers'
    OWN, non-duplicated contributions stay in their own files: C-01's test
    is this vector alone (against the shared, session-scoped `adapter`/
    `fx`); C-02's test calls this, then adds its own positive control (the
    SAME request succeeding for real under the developer credential, on
    an isolated surface) that C-01 never runs.

    `surface` is deliberately typed as the general `ConformanceAdapter`
    shape rather than tied to either caller's own fixture: C-01 passes the
    shared `adapter` itself, C-02 passes an `isolated_application_
    surface()` instance -- both expose the identical `create_entity`/
    `entities` port methods this helper calls."""
    entities_before = set(surface.entities(developer))
    with pytest.raises(ConformanceDenial) as ei:
        surface.create_entity(runtime, entity, {"label": "text"})
    assert ei.value.code in load_contract_error_codes(), f"denial code {ei.value.code!r} is not a contract error code"
    entities_after = set(surface.entities(developer))
    assert entities_after == entities_before, (
        f"{adapter_name}: schema state changed despite denial of runtime schema attempt"
    )
    assert entity not in entities_after, (
        f"{adapter_name}: {entity!r} appears in the entity set despite its own create_entity being denied"
    )


# ---------------------------------------------------------------------------
# C-10's negative-content scanner (phase 7 WP-5, design docs/design/
# PHASE7_EVIDENCE_REPRODUCIBILITY_AND_PUBLICATION_V1.md D-6.7): "adapter
# boundary level" -- every public method's own return value, and every
# ConformanceDenial's own code/details, JSON-serialized and searched for
# credential-bearing/DSN-shaped/stack-trace-shaped substrings. Placed here
# (rather than in a new test-only module) so both `test_c10_no_bypass_
# material_on_the_wire.py` (the generic proxy this scanner exists for) and
# `test_c04_unsupported_and_safe_errors.py` (a narrower, single-denial
# negative-content check) share one scanning primitive instead of drifting
# apart. `adapter.py` itself is unchanged by this addition -- the port's
# own surface (and therefore its v1.11 line count) is not touched, per this
# WP's own "port を増やさない" prohibition; this lives entirely on the
# common-suite side of the port/plug split.
# ---------------------------------------------------------------------------

# Each entry is (compiled pattern, human-readable label used in the
# assertion message). Patterns are deliberately specific (a scheme://user:
# pass@host shape, a literal Python traceback header, a `File "...", line
# N` frame, a handful of unambiguous SQL-statement openers, and a short
# list of well-known PostgreSQL bypass-configuration environment variable
# names) rather than broad keyword matches, to keep false positives against
# ordinary field names/synthetic test values low while still catching the
# concrete hazards C-10/C-04 name (design D-6.7): DB credentials, private
# management authority, or bypass-enabling configuration; stack traces;
# SQL fragments.
_UNSAFE_CONTENT_PATTERNS: tuple[tuple["re.Pattern[str]", str], ...] = (
    (
        re.compile(r"[A-Za-z][A-Za-z0-9+.\-]*://[^\s'\"/@]+:[^\s'\"/@]+@[^\s'\"]+"),
        "DSN-shaped credential-bearing URL",
    ),
    # WP-5 rework (supervisor ruling 2026-09-06 item 1 / review finding 1):
    # the URL-form pattern above never matches what this build's own two
    # HTTP plugs actually produce -- `psycopg.conninfo.make_conninfo`
    # (`r2db-api/conformance/conformance_adapter_r2db_http.py::_dsn_with`,
    # `MitateDB-api/conformance/conformance_adapter_mitatedb_http.py`'s
    # identical helper) always emits libpq KEYWORD/VALUE form
    # (`dbname=... host=... user=... password=...`), never `scheme://`.
    # Measured (mutation M1 vs M2, same planted secret, two shapes): M1
    # (URL form) turned this condition red; M2 (the REAL keyword form) did
    # not -- the URL-only pattern was catching a shape neither currently-
    # registered HTTP plug ever emits. This pattern catches the bare
    # `password=<value>` token on its own (the minimal, load-bearing part
    # of that shape), independent of neighboring `dbname=`/`host=`/`user=`
    # tokens, since a peer could echo just the password fragment of a DSN
    # it built rather than the whole string.
    (re.compile(r"\bpassword\s*=\s*\S+"), "libpq keyword-form credential (password=...)"),
    (re.compile(r"Traceback \(most recent call last\)"), "Python stack trace header"),
    (re.compile(r'File "[^"]+\.py", line \d+'), "Python stack trace frame"),
    (re.compile(r"\bSELECT\b[\s\S]{0,200}\bFROM\b", re.IGNORECASE), "SQL SELECT fragment"),
    (re.compile(r"\bINSERT\s+INTO\b", re.IGNORECASE), "SQL INSERT fragment"),
    (re.compile(r"\bDROP\s+TABLE\b", re.IGNORECASE), "SQL DROP TABLE fragment"),
    (re.compile(r"\bDELETE\s+FROM\b", re.IGNORECASE), "SQL DELETE fragment"),
    (re.compile(r"\bPG(?:PASSWORD|HOST|USER|DATABASE|PORT)\b"), "PostgreSQL environment variable name"),
    (re.compile(r"\bDATABASE_URL\b"), "environment variable name"),
)


def _json_scan_text(value: Any) -> str:
    """Best-effort JSON serialization used purely for scanning (never for
    anything a test asserts equality against). `default` fires at most
    once per node `json.dumps` cannot natively encode, and returns a
    single string for that node -- it does not itself recurse any further
    (the recursion, if any, is bounded by that node's own `str()`), so this
    is safe to point at whatever a port method happens to return, including
    an opaque session handle."""

    def _default(obj: Any) -> Any:
        if isinstance(obj, (set, frozenset)):
            return sorted(obj, key=str)
        return str(obj)

    try:
        return json.dumps(value, default=_default, ensure_ascii=False)
    except (TypeError, ValueError, RecursionError):
        return str(value)


def _held_secret_literals(real_adapter: "ConformanceAdapter") -> frozenset[str]:
    """WP-5 rework (supervisor ruling 2026-09-06 item 1 / review finding
    1.2): the set of secret VALUES this specific, already-constructed plug
    instance actually holds -- design D-6.7's own "env の値" proposition,
    read directly off the real adapter's own private state rather than
    matched by shape. A pattern (`_UNSAFE_CONTENT_PATTERNS`) can only ever
    catch a hazard shaped the way the pattern author guessed; this
    catches the exact literal, however it is formatted, reordered, or
    partially echoed.

    Never adds a port method (`adapter.py` is untouched) -- this reads
    ordinary private attributes off the concrete plug object, the same
    kind of introspection `_install_residue_tracking`'s own `hasattr(self,
    "_capability_probe_session")` check already relies on elsewhere in
    this file. Degrades to an empty set for any plug (present or future)
    that carries none of these attributes, so this is additive-only: no
    plug is required to expose anything for `assert_no_unsafe_diagnostic_
    content`'s literal-scan branch to keep working.

    Two shapes of held secret, covering all 4 currently-registered plugs:

    - `real_adapter._platform` (both HTTP plugs' own bootstrap dataclass):
      every field whose name contains `dsn` is a real, per-run-generated
      libpq connection string (admin/control/api/controlplane/
      auditreader/provision/runtime/developer, depending on the plug) --
      each one already carries its own real, random `password=...`.
    - A `_pepper` attribute (bytes, HMAC key form) on whichever credential-
      store object a plug's own `_credentials`/`_control_credentials`/
      `_read_store`/`_write_store`/`_write_credentials` attribute names,
      plus any top-level `_control_app_pepper`/`_control_pepper`/
      `_control_credential_pepper` string attribute -- covers both
      in-process plugs' own hardcoded synthetic pepper constants and both
      HTTP plugs' own pepper attributes.

    Literals under 6 characters are dropped: short substrings (a bare role
    name, a single digit) would turn this into a source of false
    positives rather than a precise hazard check.
    """
    literals: set[str] = set()

    platform = getattr(real_adapter, "_platform", None)
    if platform is not None and dataclasses.is_dataclass(platform):
        for field in dataclasses.fields(platform):
            if "dsn" in field.name:
                value = getattr(platform, field.name, None)
                if isinstance(value, str) and value:
                    literals.add(value)

    for attr_name in ("_control_app_pepper", "_control_pepper", "_control_credential_pepper"):
        value = getattr(real_adapter, attr_name, None)
        if isinstance(value, str) and value:
            literals.add(value)

    for store_attr in ("_credentials", "_control_credentials", "_read_store", "_write_store", "_write_credentials"):
        store = getattr(real_adapter, store_attr, None)
        pepper = getattr(store, "_pepper", None)
        if isinstance(pepper, (bytes, bytearray)) and pepper:
            try:
                literals.add(pepper.decode())
            except UnicodeDecodeError:
                pass
        elif isinstance(pepper, str) and pepper:
            literals.add(pepper)

    return frozenset(literal for literal in literals if len(literal) >= 6)


def assert_no_unsafe_diagnostic_content(
    value: Any, *, adapter_name: str, context: str = "", secret_literals: frozenset[str] = frozenset(),
) -> None:
    """Raises `AssertionError` naming the offending pattern/text if `value`
    (JSON-serialized via `_json_scan_text`) contains a stack-trace-, SQL-,
    DSN-, or bypass-configuration-shaped substring (`_UNSAFE_CONTENT_
    PATTERNS`), OR contains any literal string in `secret_literals` (WP-5
    rework, supervisor ruling 2026-09-06 item 1.2) -- a secret VALUE this
    build's own plug is independently known to hold (`_held_secret_
    literals`), checked by plain substring containment regardless of
    surrounding shape. A clean scan -- including of an empty/trivial
    value, or when `secret_literals` is empty -- passes silently; this is
    a negative check only, never a positive non-vacuity guard on its own
    (callers supply that separately, e.g. by asserting `details` is
    non-empty before scanning it)."""
    text = _json_scan_text(value)
    for pattern, label in _UNSAFE_CONTENT_PATTERNS:
        match = pattern.search(text)
        if match:
            raise AssertionError(
                f"{adapter_name}: unsafe diagnostic content ({label}) found"
                f"{f' ({context})' if context else ''}: {match.group(0)!r} in {text[:400]!r}"
            )
    for literal in secret_literals:
        if literal in text:
            raise AssertionError(
                f"{adapter_name}: unsafe diagnostic content (a secret value this plug is known to hold) found"
                f"{f' ({context})' if context else ''}: {literal!r} in {text[:400]!r}"
            )


# Phase 9 WP-1 (design docs/design/
# PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md D-3/§6.2 C-21,
# work order §2 WP-1 実装の指示 (11), review Minor -- reviewed and carried
# forward in v1.1). The 4 keys `errors.details_vocabulary` requires on
# `VALIDATION_FAILED`/`IDENTIFIER_INVALID`/`CAPABILITY_UNSUPPORTED`.
_DETAILS_VOCABULARY_KEYS = ("field", "declared_type", "observed_type", "violated_declaration")


def assert_details_vocabulary_values_safe(details: Mapping[str, Any], *, adapter_name: str) -> None:
    """C-21's own SI-10 scan, deliberately narrower than `assert_no_unsafe_
    diagnostic_content`'s ordinary whole-`details` scan (used by C-04/C-06
    and others): this scans ONLY the values of the 4 keys `errors.details_
    vocabulary` requires (`_DETAILS_VOCABULARY_KEYS`), never the full
    `details` mapping.

    Restricted on purpose (design D-3 実装の指示, review finding 1.1 minor
    -- adjudicated as part of this same batch): `details.field` is a
    REQUEST-INTERNAL PATH the client itself chose to name -- an ordinary
    field/entity identifier the caller supplied, not server-generated
    content -- so scanning it against an adversarial-identifier corpus
    would make this check red on its own echo, not on a real hazard. C-21
    itself only ever constructs `field` from benign, `fresh_identifier`-
    generated names; presenting an adversarial identifier through this
    exact position is C-03's own territory, not C-21's -- scanning here
    only the 4 vocabulary keys keeps that boundary structural rather than
    a matter of which values a caller happens to have passed in.

    A denial's `details` mapping may carry OTHER keys this scan does not
    touch at all (for example `PRECONDITION_FAILED`'s own pre-existing
    keys, unrelated to this vocabulary) -- callers that need the broader
    scan already have `assert_no_unsafe_diagnostic_content` for that.
    """
    for key in _DETAILS_VOCABULARY_KEYS:
        if key in details:
            assert_no_unsafe_diagnostic_content(
                details[key], adapter_name=adapter_name, context=f"details.{key}",
            )


class ScanningAdapterProxy:
    """C-10's own test primitive (port unchanged; design D-6.7, phase 7
    WP-5): wraps a real `ConformanceAdapter` so every public method call
    made THROUGH this proxy has its own return value -- or, on a
    `ConformanceDenial`/`SurfaceAbsent`/`PayloadNotExpressible`/any other
    exception the call raises, its scannable text (WP-5 rework, review
    finding 6: broadened past `ConformanceDenial` alone) -- scanned by
    `assert_no_unsafe_diagnostic_content` before the result (or the
    re-raised exception) reaches the caller. A non-callable attribute
    (`name`) passes straight through, unscanned. Scans at the ADAPTER
    boundary, not the wire: this is deliberate (design D-6.7's own
    "in-process の2plug にも効く" requirement) -- an in-process plug has
    no wire to scan at all, so a wire-level check could never be applied
    uniformly to all 4 registered plugs. Never mutates or replaces the
    underlying adapter.

    Computes `_held_secret_literals(real)` exactly once, at construction
    (WP-5 rework item 1.2) -- the plug's own held secrets do not change
    across the lifetime of one instance -- and passes that same frozen set
    to every scan this proxy performs, success or failure alike. Asserts
    that set is non-empty (WP-5 rework, supervisor ruling 2026-09-06 item
    1 -- closes audit mutation A, where forcing `_held_secret_literals` to
    return an empty set made every plug pass vacuously): a plug that
    renames the attributes `_held_secret_literals` looks for degrades this
    guard to red, not to silence."""

    def __init__(self, real: "ConformanceAdapter") -> None:
        self._real = real
        self._secret_literals = _held_secret_literals(real)
        assert self._secret_literals, (
            f"{real.name}: _held_secret_literals() returned an EMPTY set for this plug "
            f"instance (WP-5 rework, supervisor ruling 2026-09-06 item 1 -- closes audit "
            f"mutation A: an empty set makes the literal-scan branch of assert_no_unsafe_"
            f"diagnostic_content a silent no-op, so a real held secret could leak through "
            f"this proxy unnoticed). This is a per-plug non-vacuity guard on the secret-"
            f"VALUE scan specifically, separate from this file's own scanned_calls >= 8 "
            f"check on call-volume non-vacuity. `_held_secret_literals` depends on a fixed "
            f"set of hardcoded attribute names (`_platform.*dsn*`, `_pepper`, `_control_*_"
            f"pepper`) -- if a peer renames the attribute it currently exposes under one of "
            f"those names, this assert is what turns that silently into a red failure here "
            f"rather than a quietly-vacuous scan."
        )
        self.scanned_calls = 0

    def __getattr__(self, item: str) -> Any:
        target = getattr(self._real, item)
        if not callable(target):
            return target

        def _wrapped(*args: Any, **kwargs: Any) -> Any:
            try:
                result = target(*args, **kwargs)
            except ConformanceDenial as denial:
                assert_no_unsafe_diagnostic_content(
                    denial.code, adapter_name=self._real.name, context=f"{item}() denial.code",
                    secret_literals=self._secret_literals,
                )
                assert_no_unsafe_diagnostic_content(
                    denial.details, adapter_name=self._real.name, context=f"{item}() denial.details",
                    secret_literals=self._secret_literals,
                )
                self.scanned_calls += 1
                raise
            except Exception as exc:  # noqa: BLE001 - always re-raised unchanged (review
                # finding 6): `SurfaceAbsent`/`PayloadNotExpressible` and any plug-internal
                # exception that escapes uninstrumented all carry a human-readable message
                # (and, for `SurfaceAbsent`, a `details` mapping) that a `ConformanceDenial`-
                # only except clause never scanned at all. Catching broadly here and
                # re-raising immediately does not change behavior for any caller -- only
                # `assert_no_unsafe_diagnostic_content` itself can turn this into a NEW
                # failure, and it raises its own `AssertionError`, which this clause does
                # not catch (a sibling `except` in the same `try` never receives an
                # exception raised inside another branch).
                assert_no_unsafe_diagnostic_content(
                    str(exc), adapter_name=self._real.name, context=f"{item}() exception message",
                    secret_literals=self._secret_literals,
                )
                assert_no_unsafe_diagnostic_content(
                    getattr(exc, "details", None), adapter_name=self._real.name, context=f"{item}() exception details",
                    secret_literals=self._secret_literals,
                )
                self.scanned_calls += 1
                raise
            assert_no_unsafe_diagnostic_content(
                result, adapter_name=self._real.name, context=f"{item}() return value",
                secret_literals=self._secret_literals,
            )
            self.scanned_calls += 1
            return result

        return _wrapped


# ---------------------------------------------------------------------------
# Application-plane residue guard (phase 7 WP-5 rework, supervisor ruling
# 2026-09-06 item 1). See `_ApplicationResidueTracker`'s own docstring for
# the diagnosed problem and the mechanism.
# ---------------------------------------------------------------------------


class _ApplicationResidueTracker:
    """A session-wide (per worker process) safety net against application-
    plane residue accumulating in the platform's shared `applications`
    registry over the course of the WHOLE conformance suite -- not only
    this WP's own 5 new files.

    Diagnosed cause (WP-5 rework round 1): the PRE-EXISTING suite's own
    `fx` fixture (`ConformanceAdapter.build_fixture()`) provisions two
    fresh Applications on the SHARED, session-scoped adapter for every
    single condition test and never deprovisions either one; several
    existing condition tests add more of the same with no cleanup at all
    (`test_c14_authority_boundary.py`'s own `disabled_app`/`saturated_app`,
    `test_c15_bootstrap_reset_lifecycle.py`'s own `new_app`, `test_c11_
    response_schema_conformance.py`'s own `fresh_app`). None of this was
    apparent until the registry's own declared `applications` bound (small
    on purpose -- SI-08 requires a conformance build to configure a bound
    small enough to actually drive over, see `test_c14_authority_boundary.
    py`'s own `_MAX_EXERCISABLE_LIMIT`) was nearly exhausted by this
    accumulation alone, at which point ANY later application-creating test
    (this WP's own 5 new files included, as a red herring measured
    directly: two content-free dummy test files reproduced the identical
    failure) tipped it over into a real `LIMIT_EXCEEDED`.

    This tracker, plus the class-level monkeypatch `_install_residue_
    tracking` below (installed once, at collection time, against every
    `_BUILT_ADAPTERS` instance), makes a teardown-based safety net apply
    RETROACTIVELY to the whole existing suite without editing any of those
    pre-existing test files: every application a TRACKED adapter instance
    (`_TRACKED_ADAPTERS` -- exactly the small, fixed set of `_BUILT_
    ADAPTERS` instances themselves, deliberately NOT whatever throwaway
    instance `isolated_application_surface()` constructs, since that C-05
    primitive already manages its own lifecycle end-to-end, measured
    WP-5 rounds 1-3) provisions via `provision_application` or `register_
    application_inband` during one test function is deprovisioned by
    `_wp5_application_residue_guard` below at that same test's own
    teardown -- unless the test already deprovisioned it itself (`record_
    removed`, fired by the identical monkeypatch on `deprovision_
    application`, drops it from the active set so teardown never double-
    deprovisions something a test's own cleanup, e.g. `test_c14_authority_
    boundary.py`'s several `finally: adapter.deprovision_application(...)`
    blocks or `test_c09_audit_evidence.py`'s own explicit cleanup, already
    removed).
    """

    def __init__(self) -> None:
        self._active: list[tuple[Any, str]] | None = None
        self._suppressed_depth = 0
        self.total_created = 0
        self.total_deprovisioned = 0

    def begin_test(self) -> None:
        self._active = []

    def enter_suppressed(self) -> None:
        """Suspends tracking for the duration of a call known, by
        construction, to provision a SESSION-scoped resource the adapter
        itself intends to cache and reuse across every later test --
        never a per-test throwaway. `capability_document()` on `MitateDB-
        api`/`MitateDB-api-http` is the concrete, measured case (WP-5
        rework, first-execution finding): it provisions one disposable
        "capability probe" application on its own FIRST-EVER call, then
        caches that same application/session on `self` and reuses it for
        every subsequent call, for the rest of the session (`MitateDB-
        api/conformance/conformance_adapter_mitatedb.py`'s own docstring:
        "provisioned ONCE and reused for every later call, not
        re-provisioned per call"). Tracking that provisioning as though
        it were an ordinary per-test resource, as the naive class-level
        patch below originally did, meant whichever test happened to run
        FIRST (and therefore triggered the one-time provisioning) had its
        own teardown deprovision the probe application/credential
        immediately afterward -- silently breaking authentication for
        every LATER test's own `capability_document()`/`_control_plane_
        status()` call for the rest of the session (measured directly:
        `MitateDB-api`'s own missing self-healing check, unlike
        `MitateDB-api-http`'s `probe_app_id not in self._cells` guard,
        turned this into a real `AuthenticationError` on nearly every
        later `test_c14`/`test_c15` test in the file). Reentrant (a
        depth counter, not a boolean) so a suppressed call that itself
        calls another suppressed method nests safely.
        """
        self._suppressed_depth += 1

    def exit_suppressed(self) -> None:
        self._suppressed_depth -= 1

    def record_created(self, adapter_obj: Any, application_id: str) -> None:
        if self._suppressed_depth > 0:
            return
        if self._active is not None:
            self._active.append((adapter_obj, application_id))
            self.total_created += 1

    def record_removed(self, adapter_obj: Any, application_id: str) -> None:
        if self._suppressed_depth > 0:
            return
        if self._active is not None:
            target = (adapter_obj, application_id)
            self._active = [pair for pair in self._active if pair != target]

    def end_test_and_sweep(self) -> None:
        pending = self._active or []
        self._active = None
        errors: list[str] = []
        for adapter_obj, application_id in pending:
            try:
                adapter_obj.deprovision_application(application_id)
            except Exception as exc:  # noqa: BLE001 - report, never swallow (matches
                # `_close_all_adapters`'s own discipline above): a residue-
                # guard sweep that silently fails to deprovision would
                # recreate exactly the accumulation problem this guard
                # exists to prevent, just less visibly.
                errors.append(
                    f"{getattr(adapter_obj, 'name', adapter_obj)!r}: "
                    f"deprovision_application({application_id!r}) failed during WP-5 "
                    f"residue-guard teardown: {exc!r}"
                )
            else:
                self.total_deprovisioned += 1
        if errors:
            raise RuntimeError(
                "WP-5 application-residue-guard teardown failed to deprovision one or more "
                "applications a test left behind:\n" + "\n".join(f"  - {e}" for e in errors)
            )


_RESIDUE_TRACKER = _ApplicationResidueTracker()

# Identity set (default, object-identity hash/eq -- none of the four
# registered adapter classes override `__eq__`/`__hash__`): exactly the
# `_BUILT_ADAPTERS` instances themselves. Checked, not assumed, inside
# every wrapper below so a throwaway instance sharing the same CLASS (the
# in-process plugs' own `isolated_application_surface()` constructs a
# wholly fresh same-class instance; the HTTP plugs' own `isolated_
# application_surface()` yields a shallow `copy.copy(self)`) is observed
# but never tracked.
_TRACKED_ADAPTERS: set = set()
_RESIDUE_PATCHED_CLASSES: set = set()


def _install_residue_tracking(adapter_obj: "ConformanceAdapter", tracker: _ApplicationResidueTracker) -> None:
    """Patches `type(adapter_obj)` -- never the instance itself -- so every
    call to `provision_application`/`register_application_inband`/
    `deprovision_application` is observed, HOWEVER it is reached
    (including from INSIDE another method of the same object, e.g.
    `build_fixture()`'s own internal `self.provision_application(app_a)`
    calls), for WHICHEVER instance of that class it is called on.

    Patching the CLASS (with the real `self` resolved dynamically at each
    call) rather than the instance itself is deliberate, not a style
    choice: `r2db-api-http`/`MitateDB-api-http`'s own `isolated_
    application_surface()` yields a SHALLOW COPY of the shared adapter
    (`copy.copy(self)`), which copies an INSTANCE-level monkeypatch's
    closure (bound to the ORIGINAL object) right along with it -- the
    isolated copy's own calls would then silently operate on the ORIGINAL
    shared adapter instead of itself, corrupting the very isolation C-05's
    primitive exists to guarantee. A class-level patch has no such
    problem: `self` is whichever object the call was actually made on,
    resolved fresh every call, so a shallow copy (or, for the two
    in-process plugs, a wholly fresh same-class instance) behaves
    correctly with no special-casing here at all. The `_TRACKED_ADAPTERS`
    identity check inside each wrapper then confines actual TRACKING (as
    opposed to behavior, which is unconditionally preserved) to the small,
    fixed set of `_BUILT_ADAPTERS` instances.
    """
    cls = type(adapter_obj)
    if cls in _RESIDUE_PATCHED_CLASSES:
        return
    _RESIDUE_PATCHED_CLASSES.add(cls)

    original_provision = cls.provision_application

    def provision_application(self, application_id, *args, **kwargs):
        result = original_provision(self, application_id, *args, **kwargs)
        if self in _TRACKED_ADAPTERS:
            tracker.record_created(self, application_id)
        return result

    cls.provision_application = provision_application

    original_deprovision = cls.deprovision_application

    def deprovision_application(self, application_id, *args, **kwargs):
        result = original_deprovision(self, application_id, *args, **kwargs)
        if self in _TRACKED_ADAPTERS:
            tracker.record_removed(self, application_id)
        return result

    cls.deprovision_application = deprovision_application

    original_register = getattr(cls, "register_application_inband", None)
    if original_register is not None:
        def register_application_inband(self, actor, application_id, *args, **kwargs):
            result = original_register(self, actor, application_id, *args, **kwargs)
            if self in _TRACKED_ADAPTERS:
                tracker.record_created(self, application_id)
            return result

        cls.register_application_inband = register_application_inband

    # `capability_document()` is exempt from tracking ONLY on the two
    # classes that actually cache their own probe application across the
    # whole session (see `_ApplicationResidueTracker.enter_suppressed`'s
    # own docstring): `MitateDB-api`/`MitateDB-api-http` provision a
    # "capability probe" application on their own first-ever call and
    # cache it (on `self._capability_probe_session`) for reuse by every
    # later call -- exactly one application for the whole run, never a
    # per-test resource, so it must never be swept.
    #
    # Corrected, WP-5 rework (measured via a raw-SQL applications count,
    # first full-suite run under `-n 5 --dist loadgroup`): this wrapper
    # ORIGINALLY suppressed tracking unconditionally on every adapter
    # class, on the mistaken assumption that `r2db-api`/`r2db-api-http`'s
    # own `capability_document()` (which provisions a genuinely FRESH,
    # never-cached probe application on EVERY call -- see that method's
    # own docstring) would call it rarely enough not to matter. Measured
    # wrong: `capability_document()` is reached indirectly, from many
    # tests, via `_declared_contract_version()`/`_resolve_confirmation()`,
    # so unconditional suppression left a real, unbounded, one-untracked-
    # application-per-call leak on r2db's own shared adapter -- a single
    # `test_c14_resource_bounds_published_and_enforced[r2db-api-http]`
    # run alone left one `cap...` application behind, and the full suite
    # left 66 on that worker. The fix: suppress ONLY when `self` actually
    # carries the caching attribute (`_capability_probe_session`, present
    # on both MitateDB classes' own `__init__`, absent on both r2db
    # classes) -- checked dynamically, at call time, so it naturally does
    # the right thing for whichever concrete class calls through this
    # class-level patch. On r2db, tracking proceeds normally, so each
    # call's own genuinely-disposable probe application is swept by
    # `_wp5_application_residue_guard` exactly like any other per-test
    # provision.
    original_capability_document = getattr(cls, "capability_document", None)
    if original_capability_document is not None:
        def capability_document(self, *args, **kwargs):
            caches_its_own_probe = hasattr(self, "_capability_probe_session")
            if caches_its_own_probe:
                tracker.enter_suppressed()
            try:
                return original_capability_document(self, *args, **kwargs)
            finally:
                if caches_its_own_probe:
                    tracker.exit_suppressed()

        cls.capability_document = capability_document


for _wp5_residue_name, _wp5_residue_adapter in _BUILT_ADAPTERS:
    _TRACKED_ADAPTERS.add(_wp5_residue_adapter)
    _install_residue_tracking(_wp5_residue_adapter, _RESIDUE_TRACKER)
del _wp5_residue_name, _wp5_residue_adapter


@contextmanager
def residue_tracking_suppressed():
    """Public helper (phase 7 WP-5 rework, first full-suite-run finding):
    for a test module that deliberately caches a provisioned application/
    `Fixture` across MULTIPLE test functions for its own module's whole
    run -- the identical shape `capability_document()`'s own internal
    per-adapter cache already needed `enter_suppressed`/`exit_suppressed`
    for (see `_ApplicationResidueTracker.enter_suppressed`'s docstring) --
    wrap the ONE-TIME provisioning call with this so `_wp5_application_
    residue_guard` never sweeps the application out from under a LATER
    test in the same module that still expects it to exist.

    The one measured, pre-existing case: `test_c06_destructive_
    confirmation.py`'s own `fx` override (`_SHARED_FIXTURE_CACHE`)
    deliberately provisions `fx.app_a`/`app_b` ONCE and reuses that same
    `Fixture` for every one of its own vector tests, by design (that
    file's own `_capability_document`'s docstring: "measured...to be the
    direct cause of a real regression" if re-provisioned per call) --
    before this helper existed, the residue guard swept those two
    applications at the FIRST test's own teardown, breaking authentication
    for every later test in the file (`FORBIDDEN`/`AUTH_INVALID` on a
    session whose own application had just been dropped out from under
    it). The unmodified, non-cached `fx` in every OTHER test file is
    untouched by this -- it is a per-file opt-in, not a global behavior
    change.
    """
    _RESIDUE_TRACKER.enter_suppressed()
    try:
        yield
    finally:
        _RESIDUE_TRACKER.exit_suppressed()


@pytest.fixture(autouse=True)
def _wp5_application_residue_guard():
    """Autouse, function-scoped (phase 7 WP-5 rework, supervisor ruling
    2026-09-06 item 1): see `_ApplicationResidueTracker`'s own docstring
    above for the mechanism and the diagnosed problem this exists to
    solve. Runs for every collected test, not only ones that use the
    `adapter`/`fx` fixtures -- a no-op sweep (empty `pending` list) for a
    test that never provisions anything through a tracked adapter, so this
    carries no real cost for e.g. `registry-guards`-group tests."""
    _RESIDUE_TRACKER.begin_test()
    yield
    _RESIDUE_TRACKER.end_test_and_sweep()


@pytest.fixture(scope="session", autouse=True)
def _wp5_residue_guard_is_not_vacuous():
    """Non-vacuity guard (supervisor ruling 2026-09-06 item 1's own
    "空振り禁止" -- teardown must be OBSERVED to actually deprovision
    something, not merely present in the source). Deliberately carries no
    `params` of its own, same discipline as `_close_all_adapters_at_
    session_end` above and for the identical reason: this must assert
    exactly once, at the true end of THIS WORKER's session, not once per
    adapter-param group.

    If this worker process provisioned ANY application through a tracked
    adapter at all (`total_created > 0` -- true for essentially every
    worker that ran even one `fx`-based test, since `build_fixture()`
    alone provisions two per test), at least one of those must have gone
    through `_wp5_application_residue_guard`'s own teardown sweep
    (`total_deprovisioned > 0`) -- otherwise the guard above is silently
    not firing (e.g. broken by a future refactor) and WP-5's own
    residue-cleanup mechanism is proving nothing. A worker that happens to
    run NO application-creating test at all (the `registry-guards` xdist
    group -- whole-registry checks, e.g. `test_c19_every_control_surface_
    adapter_declares_1_6_0`, that call `registered_adapters()` directly
    and never touch `provision_application`) trivially satisfies
    `total_created == 0` and is correctly exempted: this guard proves the
    sweep works wherever it has anything to prove it against, not that
    every worker universally exercises it.
    """
    yield
    assert _RESIDUE_TRACKER.total_created == 0 or _RESIDUE_TRACKER.total_deprovisioned > 0, (
        "WP-5 application-residue-guard: this worker's tracked adapters provisioned "
        f"{_RESIDUE_TRACKER.total_created} application(s) via provision_application()/"
        f"register_application_inband(), but the teardown sweep deprovisioned "
        f"{_RESIDUE_TRACKER.total_deprovisioned} of them -- the residue-guard fixture is not actually "
        "running (or not actually removing anything), which defeats the whole point of WP-5's own "
        "residue-cleanup mechanism"
    )
