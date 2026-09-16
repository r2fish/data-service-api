"""R-37 WP-1-0: import-direction machinery for extracted "leaf" modules.

Design: docs/design/MODULE_REFACT_ARCHITECTURE_V1.md §3 (leaf eligibility),
§5 (verification and mutation). Work order:
docs/work-orders/WORK_ORDER_R37_WP0_INVENTORY_V1.md §5.1 (WP-1-0).

A "leaf" module's only allowed imports are the ones listed in its own
allowlist below, plus ``__future__`` (always allowed, never listed). This
file does not execute any import, and it does not detect a dynamic import
performed via ``__import__()`` or ``importlib.import_module()`` -- it
reads each module's AST and compares the *names* of its static
``import``/``from ... import`` statements to the allowlist.

Names are normalized before comparison:

- An absolute import's name is its top-level package, for both forms
  (``import psycopg.pq`` and ``from psycopg.pq import X`` both normalize
  to ``psycopg``).
- A relative import with an explicit module keeps its full dotted
  spelling, dots included (``from .errors import fail`` -> ``.errors``).
- A relative import with no module (``from . import a, b``) records one
  name per imported alias (``.a`` and ``.b``), not a bare ``.``.

An allowlist entry that is only dots (``.``, ``..``, ...) can never match
a real import name under the normalization above, so
``test_leaf_modules_import_only_their_allowlisted_modules`` treats one as
a violation in its own right.

Every ``.py`` file under either peer's ``src/<package>/`` (recursive,
including ``__init__.py`` and ``contract/__init__.py``) must appear in
exactly one of ``LEAF_MODULES`` or ``NON_LEAF_MODULES`` for its peer, and
every ``NON_LEAF_MODULES`` entry must carry a non-empty one-line reason.
This file scans all modules in two functions, not one parametrized test
per module, so registering a new leaf never grows the ``tools/tests``
node id count.

Both lists are declared as ``(path, value)`` tuple sequences
(``LEAF_MODULE_ENTRIES`` / ``NON_LEAF_MODULE_ENTRIES``) and converted to
dicts at import time via ``_entries_to_dict``; a path repeated within
either sequence is recorded as a duplicate rather than silently resolved
by last-write-wins, and ``test_every_src_module_is_classified`` fails
whenever a duplicate is present.

WP-1-0 registers only the six leaves that already existed at 2026-09-14
(work order §5.1's baseline table). Every other module in both peers'
``src/`` is classified as non-leaf; most carry the reason
"unregistered; import-shape only, eligibility not assessed (design
§3.1)" -- their own import graph happens to contain nothing outside a
plausible allowlist, but WP-1-0's scope is limited to registering the six
existing leaves, so whether any of them is actually eligible for
extraction is left to the WP that would extract it.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import TypeVar

REPO_ROOT = Path(__file__).resolve().parents[2]

# peer key -> path to that peer's package source root.
SRC_ROOTS: dict[str, Path] = {
    "r2db": REPO_ROOT / "r2db-api" / "src" / "r2db_api",
    "mitatedb": REPO_ROOT / "MitateDB-api" / "src" / "mitatedb_api",
}

_T = TypeVar("_T")


def _entries_to_dict(entries: list[tuple[str, _T]]) -> tuple[dict[str, _T], list[str]]:
    """Convert a `(path, value)` sequence to a dict, reporting duplicate paths.

    A path that appears more than once is appended to the returned
    duplicate list every time it repeats; the dict still gets a value for
    that path (last write wins) so the rest of this module can be typed
    normally, but callers must treat a non-empty duplicate list as a
    failure -- a duplicate path is how a broadened allowlist or a
    silently-dropped reason could be smuggled into either list.
    """
    result: dict[str, _T] = {}
    duplicates: list[str] = []
    for path, value in entries:
        if path in result:
            duplicates.append(path)
        result[path] = value
    return result, duplicates


# Existing leaves, as measured 2026-09-14 (work order §5.1 table). Allowlist
# values are AST import names; `__future__` is always allowed and omitted.
LEAF_MODULE_ENTRIES: dict[str, list[tuple[str, frozenset[str]]]] = {
    "r2db": [
        ("postgres_types.py", frozenset({"psycopg", "dataclasses", "typing"})),
        ("postgres_like.py", frozenset()),
        ("audit_counts.py", frozenset()),
        ("value_nul.py", frozenset({"typing"})),
        ("pg_text_format.py", frozenset({"json", "decimal", "typing"})),
        ("inmemory_sort.py", frozenset({"json", "typing"})),
        ("inmemory_predicate.py", frozenset({"re", "typing", ".errors", ".pg_text_format"})),
        ("identifier_rules.py", frozenset({"re", ".errors"})),
        ("delete_confirmation.py", frozenset({"hashlib", "json", "typing", ".errors", ".identifier_rules"})),
        ("paging.py", frozenset({"base64", "hashlib", "json", "typing", ".errors", ".identifier_rules", ".limits"})),
        ("value_types.py", frozenset({"typing", ".errors", ".value_nul"})),
        ("service_results.py", frozenset({"dataclasses", "typing"})),
        ("capabilities_document.py", frozenset({"typing"})),
        ("request_shape.py", frozenset({"typing", ".errors"})),
        ("storage_outcomes.py", frozenset({"dataclasses", "typing"})),
        ("mutation_binding.py", frozenset({"dataclasses", "typing", ".errors", ".identifier_rules"})),
        ("schema_binding.py", frozenset({"dataclasses", "typing", ".errors", ".value_types"})),
    ],
    "mitatedb": [
        ("postgres_value_domain.py", frozenset({".errors"})),
        ("request_traversal.py", frozenset({"dataclasses", "typing"})),
        ("delete_confirmation.py", frozenset({"hashlib", "json"})),
        ("request_limits.py", frozenset({".errors", ".request_traversal"})),
        ("constraint_resolution.py", frozenset({".errors", ".field_types"})),
        ("postgres_reserved_names.py", frozenset({".errors"})),
        ("provisional_gate.py", frozenset({".errors"})),
        ("postgres_types.py", frozenset({"psycopg"})),
        ("request_vocabulary.py", frozenset()),
        ("capabilities_document.py", frozenset({".backend", ".surfaces"})),
        ("request_binding.py", frozenset({"json", ".errors", ".field_types"})),
        ("postgres_sql.py", frozenset({"psycopg", ".backend"})),
    ],
}

# Every other module in both peers' src/, with a short reason it is not a
# registered leaf.
NON_LEAF_MODULE_ENTRIES: dict[str, list[tuple[str, str]]] = {
    "r2db": [
        ("__init__.py", "facade: re-exports auth/errors/service (upper layers)"),
        ("audit.py", "audit emit boundary (design §3.2)"),
        ("audit_hook.py", "pre-commit audit hook protocol, audit emit boundary (design §3.2)"),
        ("audit_query.py", "imports .service (upper layer); audit read boundary (design §3.2)"),
        ("auth.py", "authentication / credential state boundary (design §3.2)"),
        ("backend.py", "StorageBackend protocol imports .audit_hook/.limits/.structured (upper layers)"),
        ("contract/__init__.py", "unregistered; import-shape only, eligibility not assessed (design §3.1)"),
        ("control_http.py", "ASGI HTTP boundary (I/O)"),
        ("control_main.py", "composition root; imports control-plane/HTTP/credential modules (upper layers)"),
        ("control_plane.py", "control-plane authorization/session state (design §3.2)"),
        ("credential_store.py", "PostgreSQL-backed credential store; connection I/O (design §3.2)"),
        ("errors.py", "unregistered; import-shape only, eligibility not assessed (design §3.1)"),
        ("http.py", "ASGI HTTP boundary (I/O)"),
        ("limits.py", "unregistered; import-shape only, eligibility not assessed (design §3.1)"),
        ("main.py", "composition root; imports many upper-layer modules"),
        ("ops.py", "CLI: subprocess/argparse/psycopg I/O"),
        ("pg_timeouts.py", "unregistered; import-shape only, eligibility not assessed (design §3.1)"),
        ("platform_declarations.py", "reads DB-side declarations via psycopg (I/O)"),
        ("platform_upgrades.py", "executes queries against a psycopg connection; DB ledger I/O"),
        ("postgres.py", "PostgresCell: connection/cursor/lock/transaction ownership (design §3.2)"),
        ("service.py", "DataService facade; authentication/rate-limit lock (design §3.2)"),
        ("structured.py", "ApplicationCell: in-memory cell lock and transaction boundary (design §3.2)"),
        ("topology.py", "unregistered; import-shape only, eligibility not assessed (design §3.1)"),
    ],
    "mitatedb": [
        ("__init__.py", "facade: re-exports auth/backend/cell/config/service (upper layers)"),
        ("application_audit.py", "durable audit emitter; psycopg I/O (design §3.2)"),
        ("audit.py", "audit emit boundary (design §3.2)"),
        ("audit_dispatch.py", "audit dispatch/buffer/threading (design §3.2)"),
        ("audit_hook.py", "pre-commit audit hook protocol, audit emit boundary (design §3.2)"),
        ("audit_query.py", "imports .application_audit/.control_audit (upper layers); psycopg read I/O"),
        ("auth.py", "authentication / credential lifecycle boundary (design §3.2)"),
        ("backend.py", "unregistered; import-shape only, eligibility not assessed (design §3.1)"),
        ("backend_postgres.py", "PostgreSQL storage backend: connection/cursor execution (design §3.2)"),
        ("backend_sqlite.py", "SQLite storage backend: connection/cursor execution (design §3.2)"),
        ("cell.py", "ApplicationCell: in-memory cell lock and transaction boundary (design §3.2)"),
        ("config.py", "reads OS environment (os import); side effect"),
        ("contract/__init__.py", "unregistered; import-shape only, eligibility not assessed (design §3.1)"),
        ("control_audit.py", "control-plane audit evidence; psycopg I/O (design §3.2)"),
        ("control_auth.py", "control-credential store; authentication boundary (design §3.2)"),
        ("control_composition.py", "composition root; imports control-plane/credential modules (upper layers)"),
        ("control_credential_store_postgres.py", "Postgres-backed control credential store; connection I/O (design §3.2)"),
        ("control_http.py", "ASGI HTTP boundary (I/O)"),
        ("control_main.py", "composition root; imports control_composition/control_http (upper layers)"),
        ("control_plane.py", "control-plane authorization/session state (design §3.2)"),
        ("credential_store_postgres.py", "PostgreSQL-backed credential store; connection I/O (design §3.2)"),
        ("credential_wire.py", "authentication / credential-secret boundary (design §3.2)"),
        ("errors.py", "unregistered; import-shape only, eligibility not assessed (design §3.1)"),
        ("field_types.py", "unregistered; import-shape only, eligibility not assessed (design §3.1)"),
        ("http.py", "ASGI HTTP boundary (I/O)"),
        ("identifiers.py", "unregistered; import-shape only, eligibility not assessed (design §3.1)"),
        ("main.py", "composition root; imports many upper-layer modules"),
        ("ops.py", "CLI: subprocess/argparse/psycopg I/O"),
        ("pg_timeouts.py", "unregistered; import-shape only, eligibility not assessed (design §3.1)"),
        ("platform_declarations.py", "reads DB-side declarations via psycopg (I/O)"),
        ("platform_upgrades.py", "executes queries against a psycopg connection; DB ledger I/O"),
        ("pool.py", "bounded connection pool: connection ownership (design §3.2)"),
        ("service.py", "control-plane/application service composition (upper layers)"),
        ("surfaces.py", "unregistered; import-shape only, eligibility not assessed (design §3.1)"),
    ],
}

LEAF_MODULES: dict[str, dict[str, frozenset[str]]] = {}
LEAF_DUPLICATE_PATHS: dict[str, list[str]] = {}
for _peer, _entries in LEAF_MODULE_ENTRIES.items():
    LEAF_MODULES[_peer], LEAF_DUPLICATE_PATHS[_peer] = _entries_to_dict(_entries)

NON_LEAF_MODULES: dict[str, dict[str, str]] = {}
NON_LEAF_DUPLICATE_PATHS: dict[str, list[str]] = {}
for _peer, _entries in NON_LEAF_MODULE_ENTRIES.items():
    NON_LEAF_MODULES[_peer], NON_LEAF_DUPLICATE_PATHS[_peer] = _entries_to_dict(_entries)

del _peer, _entries

_DOTS_ONLY = re.compile(r"^\.+$")


def _module_import_names(path: Path) -> set[str]:
    """Normalized AST import names in `path`, `__future__` excluded.

    See the module docstring for the exact normalization rules. No import
    is executed; only the AST is read, and a dynamic import via
    ``__import__()``/``importlib.import_module()`` is invisible to this
    function by construction.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                prefix = "." * node.level
                if node.module:
                    names.add(prefix + node.module)
                else:
                    for alias in node.names:
                        names.add(prefix + alias.name)
            elif node.module:
                names.add(node.module.split(".")[0])
    names.discard("__future__")
    return names


def test_leaf_modules_import_only_their_allowlisted_modules() -> None:
    assert LEAF_MODULES, "LEAF_MODULES must not be empty"

    violations: list[str] = []
    for peer, src_root in SRC_ROOTS.items():
        for rel_path, allowed in LEAF_MODULES[peer].items():
            dots_only = sorted(entry for entry in allowed if _DOTS_ONLY.fullmatch(entry))
            if dots_only:
                violations.append(
                    f"{peer}:{rel_path}: allowlist has dots-only entries {dots_only}, "
                    "which can never match a normalized import name"
                )

            module_path = src_root / rel_path
            if not module_path.is_file():
                violations.append(f"{peer}:{rel_path}: leaf path does not exist")
                continue
            actual = _module_import_names(module_path)
            disallowed = sorted(actual - allowed)
            if disallowed:
                violations.append(
                    f"{peer}:{rel_path}: imports {disallowed} outside its allowlist "
                    f"{sorted(allowed)}"
                )
    assert not violations, "leaf module(s) import outside their allowlist:\n" + "\n".join(
        violations
    )


def test_every_src_module_is_classified() -> None:
    assert set(SRC_ROOTS) == set(LEAF_MODULES) == set(NON_LEAF_MODULES) == {"r2db", "mitatedb"}
    assert sum(len(v) for v in LEAF_MODULES.values()) >= 1, "LEAF_MODULES must not be empty"

    problems: list[str] = []
    for peer, src_root in SRC_ROOTS.items():
        if LEAF_DUPLICATE_PATHS[peer]:
            problems.append(
                f"{peer}: duplicate path(s) in LEAF_MODULE_ENTRIES: "
                f"{sorted(LEAF_DUPLICATE_PATHS[peer])}"
            )
        if NON_LEAF_DUPLICATE_PATHS[peer]:
            problems.append(
                f"{peer}: duplicate path(s) in NON_LEAF_MODULE_ENTRIES: "
                f"{sorted(NON_LEAF_DUPLICATE_PATHS[peer])}"
            )

        leaf_names = set(LEAF_MODULES[peer])
        non_leaf = NON_LEAF_MODULES[peer]
        non_leaf_names = set(non_leaf)

        overlap = leaf_names & non_leaf_names
        if overlap:
            problems.append(f"{peer}: classified as both leaf and non-leaf: {sorted(overlap)}")

        empty_reasons = sorted(name for name, reason in non_leaf.items() if not reason.strip())
        if empty_reasons:
            problems.append(f"{peer}: non-leaf module(s) with an empty reason: {empty_reasons}")

        missing_leaf_paths = sorted(
            name for name in leaf_names if not (src_root / name).is_file()
        )
        if missing_leaf_paths:
            problems.append(f"{peer}: leaf path(s) do not exist: {missing_leaf_paths}")

        actual = {str(p.relative_to(src_root)) for p in src_root.rglob("*.py")}
        assert len(actual) >= 1, f"{peer}: rglob found no modules under {src_root}"

        classified = leaf_names | non_leaf_names

        unclassified = sorted(actual - classified)
        if unclassified:
            problems.append(f"{peer}: module(s) not classified as leaf or non-leaf: {unclassified}")

        stale = sorted(classified - actual)
        if stale:
            problems.append(f"{peer}: classified module(s) missing from disk: {stale}")

    assert not problems, "\n".join(problems)
