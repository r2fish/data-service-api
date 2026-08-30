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

import importlib
import sys
from pathlib import Path

import pytest

from adapter import ConformanceAdapter

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = Path(__file__).parent / "registry.json"


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers", "condition(cid): common conformance condition identifier"
    )


def _load_registry() -> list[dict]:
    import json

    data = json.loads(REGISTRY_PATH.read_text())
    return data["adapters"]


def _discover_and_build() -> list[tuple[str, ConformanceAdapter]]:
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


@pytest.fixture()
def fx(adapter: ConformanceAdapter):
    """A fresh `Fixture` (design section 4.2) built for each test function,
    so condition tests never share application/credential state with each
    other even though the underlying `adapter` object is session-scoped."""
    return adapter.build_fixture()
