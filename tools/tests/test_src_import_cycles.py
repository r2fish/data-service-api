"""R-76: import-cycle detection over both peers' `src/`.

Design: `docs/design/MODULE_REFACT_ARCHITECTURE_V1.md` §5.1's 1 ("旧 facade
と新 leaf の import / export が意図どおりであり、循環 import がない静的照
合"). Work order: `docs/work-orders/WORK_ORDER_R37_WP0_INVENTORY_V1.md`
§5.46's (2), and `docs/work-orders/WORK_ORDER_R76_SRC_IMPORT_CYCLES_V1.md`.

This file reads each peer's `src/` package with `ast` only; it never
executes an import. It builds a directed module-import graph over
`SRC_ROOTS` and asserts the graph has no nontrivial strongly connected
component.

Node set: every ``.py`` file directly under a peer's package directory,
recursive, as a package-relative dotted name (``__init__.py`` names its
own package, e.g. ``r2db_api`` for the top-level ``__init__.py`` and
``r2db_api.contract`` for ``contract/__init__.py``; every other file names
itself, e.g. ``r2db_api.audit``).

Edge set: every ``ast.Import``/``ast.ImportFrom`` node found by
``ast.walk`` over a module's whole AST, with no regard to where the
statement sits -- a module-top import, a function-body import, and an
import guarded by ``if TYPE_CHECKING:`` all count as edges exactly alike.
A relative import is resolved with its ``level`` against the importing
module's own package (an ``__init__.py``'s package is itself; any other
module's package is its parent). Both a relative ``from . import a, b``
(no explicit module) and an absolute ``from pkg import a, b`` resolve each
imported alias to a submodule of the named package first (``.a`` /
``pkg.a``); only when none of an absolute ``from``'s aliases names a real
submodule does the ``from``'s own module name become the edge target
directly (the ordinary ``from pkg.leaf import name`` case, where ``leaf``
already names the target module and ``name`` is not itself a module, and
also a bare ``from <top package> import <attribute>`` where the named
attribute is not itself a submodule -- importing it genuinely runs the
package's own ``__init__`` first, so the package is a real edge endpoint
there). A mixed ``from pkg import <submodule>, <attribute>`` only creates
the submodule edge, never an edge to ``pkg`` itself, the same treatment
Z5-20 gives the relative form. An ``import pkg.sub`` resolves by its
dotted name directly. In every case the resolved name becomes an edge
only if it names a module already in the
discovered node set for either peer -- an import of a name that isn't a
real internal module (a third-party package, the stdlib, or an attribute
rather than a submodule) is not an edge, and no import statement ever
names a package's own ``__init__`` merely because a sibling belongs to
it, so belonging to a package is never itself an edge to that package.

Scope is pinned to each peer's package directory only (never the peer's
repository directory), and the discovered module set for each peer must
equal ``PINNED_MODULES[peer]`` exactly -- a set-equality check, not a bare
count, so narrowing the scan (one fewer module) or widening it (a root
raised to the peer's repository directory, pulling in unrelated ``.py``
files) is caught the same way. Both the module count and each peer's own
edge count must be at least 1, so an empty scan -- overall or for either
peer alone -- can never pass by vacuous truth.

A cyclic edge is never silently accepted here: the assertion below allows
zero nontrivial strongly connected components, unconditionally. If a
future change needs one module to import another in a way that closes a
cycle, that requires an explicit, recorded exception added to this file's
own graph-construction rules before this test's assertion is loosened to
admit it; that exception requires a supervisor ruling recorded in the
work order before it is added. None is recorded, so today every
module-import cycle this file can see is a failure.
"""
from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# peer key -> path to that peer's package source root. Never a peer's
# repository directory (Z5-8): a peer's docs/ tree can carry unreviewed
# reference `.py` files that must not be scanned.
SRC_ROOTS: dict[str, Path] = {
    "r2db": REPO_ROOT / "r2db-api" / "src" / "r2db_api",
    "mitatedb": REPO_ROOT / "MitateDB-api" / "src" / "mitatedb_api",
}

# Every module discovered under each peer's src/, as a dotted-name list
# pinned verbatim (work order §6.1). `set(discovered) == set(pinned)` is
# asserted per peer, not a count, in `test_src_modules_match_pinned_set`. A
# change that adds a new module under either peer's src/ updates this list
# in the same change set.
PINNED_MODULES: dict[str, frozenset[str]] = {
    "r2db": frozenset(
        {
            "r2db_api",
            "r2db_api.audit",
            "r2db_api.audit_counts",
            "r2db_api.audit_hook",
            "r2db_api.audit_query",
            "r2db_api.auth",
            "r2db_api.backend",
            "r2db_api.capabilities_document",
            "r2db_api.concurrency_slots",
            "r2db_api.contract",
            "r2db_api.control_http",
            "r2db_api.control_main",
            "r2db_api.control_plane",
            "r2db_api.credential_store",
            "r2db_api.delete_confirmation",
            "r2db_api.errors",
            "r2db_api.http",
            "r2db_api.identifier_rules",
            "r2db_api.inmemory_predicate",
            "r2db_api.inmemory_sort",
            "r2db_api.limits",
            "r2db_api.main",
            "r2db_api.mutation_binding",
            "r2db_api.operation_catalog",
            "r2db_api.ops",
            "r2db_api.paging",
            "r2db_api.pg_text_format",
            "r2db_api.pg_timeouts",
            "r2db_api.platform_declarations",
            "r2db_api.platform_upgrades",
            "r2db_api.postgres",
            "r2db_api.postgres_like",
            "r2db_api.postgres_sql",
            "r2db_api.postgres_types",
            "r2db_api.psycopg_counting",
            "r2db_api.request_shape",
            "r2db_api.schema_binding",
            "r2db_api.service",
            "r2db_api.service_results",
            "r2db_api.storage_outcomes",
            "r2db_api.structured",
            "r2db_api.topology",
            "r2db_api.value_nul",
            "r2db_api.value_types",
        }
    ),
    "mitatedb": frozenset(
        {
            "mitatedb_api",
            "mitatedb_api.application_audit",
            "mitatedb_api.audit",
            "mitatedb_api.audit_dispatch",
            "mitatedb_api.audit_hook",
            "mitatedb_api.audit_query",
            "mitatedb_api.auth",
            "mitatedb_api.backend",
            "mitatedb_api.backend_postgres",
            "mitatedb_api.backend_sqlite",
            "mitatedb_api.capabilities_document",
            "mitatedb_api.cell",
            "mitatedb_api.concurrency_slots",
            "mitatedb_api.config",
            "mitatedb_api.constraint_resolution",
            "mitatedb_api.contract",
            "mitatedb_api.control_audit",
            "mitatedb_api.control_auth",
            "mitatedb_api.control_composition",
            "mitatedb_api.control_credential_store_postgres",
            "mitatedb_api.control_http",
            "mitatedb_api.control_main",
            "mitatedb_api.control_plane",
            "mitatedb_api.credential_store_postgres",
            "mitatedb_api.credential_wire",
            "mitatedb_api.delete_confirmation",
            "mitatedb_api.errors",
            "mitatedb_api.field_types",
            "mitatedb_api.http",
            "mitatedb_api.identifiers",
            "mitatedb_api.main",
            "mitatedb_api.operation_catalog",
            "mitatedb_api.ops",
            "mitatedb_api.paging",
            "mitatedb_api.pg_timeouts",
            "mitatedb_api.platform_declarations",
            "mitatedb_api.platform_upgrades",
            "mitatedb_api.pool",
            "mitatedb_api.postgres_reserved_names",
            "mitatedb_api.postgres_sql",
            "mitatedb_api.postgres_types",
            "mitatedb_api.postgres_value_domain",
            "mitatedb_api.psycopg_counting",
            "mitatedb_api.provisional_gate",
            "mitatedb_api.request_binding",
            "mitatedb_api.request_limits",
            "mitatedb_api.request_traversal",
            "mitatedb_api.request_vocabulary",
            "mitatedb_api.service",
            "mitatedb_api.surfaces",
        }
    ),
}


def _dotted_name(path: Path, src_root: Path) -> str:
    """`path`'s package-relative dotted name; `__init__.py` names its package."""
    parts = path.relative_to(src_root).with_suffix("").parts
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join((src_root.name, *parts))


def _discover_modules(src_root: Path) -> dict[str, Path]:
    """dotted name -> file path for every `.py` file under `src_root`."""
    return {_dotted_name(p, src_root): p for p in sorted(src_root.rglob("*.py"))}


def _package_attr(dotted: str, is_package: bool) -> str:
    """The dotted name a relative import in `dotted` resolves against.

    A package (`__init__.py`) resolves relative imports against itself;
    any other module resolves them against its own parent package.
    """
    if is_package or "." not in dotted:
        return dotted
    return dotted.rsplit(".", 1)[0]


def _resolve_relative_base(package_attr: str, level: int) -> str | None:
    bits = package_attr.rsplit(".", level - 1)
    if len(bits) < level:
        return None
    return bits[0]


def _module_edges(dotted: str, path: Path, module_set: frozenset[str]) -> set[tuple[str, str]]:
    """Import edges out of `dotted`, resolved per the module docstring.

    Walks the whole AST (`ast.walk`), so a function-body import or one
    guarded by `if TYPE_CHECKING:` counts exactly like a module-top
    import. A relative `from . import a, b` and an absolute `from pkg
    import a, b` are both resolved per alias to a submodule first; an
    absolute `from`'s own module name is used directly only when none of
    its aliases resolves as a submodule. No edge is added from a module
    to its own parent package merely because it belongs to that package
    -- only a name an actual import statement resolves to a module
    already in `module_set` becomes an edge.
    """
    is_package = path.name == "__init__.py"
    package_attr = _package_attr(dotted, is_package)
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    edges: set[tuple[str, str]] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in module_set:
                    edges.add((dotted, alias.name))
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = _resolve_relative_base(package_attr, node.level)
                if base is None:
                    continue
                if node.module:
                    target = f"{base}.{node.module}"
                    if target in module_set:
                        edges.add((dotted, target))
                else:
                    for alias in node.names:
                        target = f"{base}.{alias.name}"
                        if target in module_set:
                            edges.add((dotted, target))
            elif node.module and node.module in module_set:
                submodule_targets = {
                    f"{node.module}.{alias.name}"
                    for alias in node.names
                    if f"{node.module}.{alias.name}" in module_set
                }
                if submodule_targets:
                    for target in submodule_targets:
                        edges.add((dotted, target))
                else:
                    edges.add((dotted, node.module))
    return edges


def _build_graph() -> tuple[dict[str, dict[str, Path]], dict[str, set[tuple[str, str]]]]:
    """Per-peer module map, and per-peer import edges (keyed by the
    importing module's own peer)."""
    modules_by_peer = {peer: _discover_modules(root) for peer, root in SRC_ROOTS.items()}
    module_set = frozenset().union(*(frozenset(m) for m in modules_by_peer.values()))
    edges_by_peer: dict[str, set[tuple[str, str]]] = {}
    for peer, modmap in modules_by_peer.items():
        peer_edges: set[tuple[str, str]] = set()
        for dotted, path in modmap.items():
            peer_edges |= _module_edges(dotted, path, module_set)
        edges_by_peer[peer] = peer_edges
    return modules_by_peer, edges_by_peer


def _find_nontrivial_sccs(
    edges: set[tuple[str, str]]
) -> list[tuple[list[str], list[tuple[str, str]]]]:
    """Every nontrivial strongly connected component of `edges` (Tarjan).

    Returns one `(sorted module names, sorted internal edges)` pair per
    nontrivial component -- a component with 2 or more nodes, or a single
    node carrying a self-loop edge. A lone node with no self-loop is
    never returned, since that is not a cycle. Unlike reporting one path
    per DFS back edge, this always reports every module and every edge
    that actually participates in a cycle, even when several back edges
    fall inside the same component.
    """
    graph: dict[str, list[str]] = {}
    nodes: set[str] = set()
    for source, target in edges:
        graph.setdefault(source, []).append(target)
        nodes.add(source)
        nodes.add(target)

    index_counter = [0]
    index: dict[str, int] = {}
    lowlink: dict[str, int] = {}
    on_stack: dict[str, bool] = {}
    stack: list[str] = []
    components: list[list[str]] = []

    def strongconnect(v: str) -> None:
        index[v] = index_counter[0]
        lowlink[v] = index_counter[0]
        index_counter[0] += 1
        stack.append(v)
        on_stack[v] = True

        for w in sorted(graph.get(v, ())):
            if w not in index:
                strongconnect(w)
                lowlink[v] = min(lowlink[v], lowlink[w])
            elif on_stack.get(w):
                lowlink[v] = min(lowlink[v], index[w])

        if lowlink[v] == index[v]:
            component: list[str] = []
            while True:
                w = stack.pop()
                on_stack[w] = False
                component.append(w)
                if w == v:
                    break
            components.append(component)

    for node in sorted(nodes):
        if node not in index:
            strongconnect(node)

    nontrivial: list[tuple[list[str], list[tuple[str, str]]]] = []
    for component in components:
        comp_set = set(component)
        internal_edges = sorted(
            (source, target) for source, target in edges if source in comp_set and target in comp_set
        )
        if len(component) >= 2 or internal_edges:
            nontrivial.append((sorted(component), internal_edges))
    return nontrivial


def test_src_modules_match_pinned_set() -> None:
    assert set(SRC_ROOTS) == set(PINNED_MODULES) == {"r2db", "mitatedb"}

    modules_by_peer = {peer: _discover_modules(root) for peer, root in SRC_ROOTS.items()}
    mismatches: list[str] = []
    for peer, pinned in PINNED_MODULES.items():
        discovered = set(modules_by_peer[peer])
        if discovered != pinned:
            mismatches.append(
                f"{peer}: discovered {sorted(discovered)} != pinned {sorted(pinned)}"
            )
    assert not mismatches, "\n".join(mismatches)

    total_modules = sum(len(m) for m in modules_by_peer.values())
    assert total_modules >= 1, "no modules discovered under either peer's src/"


def test_src_import_graph_has_no_cycles() -> None:
    _, edges_by_peer = _build_graph()
    empty_peers = [peer for peer, peer_edges in edges_by_peer.items() if not peer_edges]
    assert not empty_peers, f"no import edges discovered under this peer's src/: {empty_peers}"

    all_edges: set[tuple[str, str]] = set()
    for peer_edges in edges_by_peer.values():
        all_edges |= peer_edges

    sccs = _find_nontrivial_sccs(all_edges)
    assert not sccs, "import cycle(s) found:\n" + "\n".join(
        f"modules={modules} edges={comp_edges}" for modules, comp_edges in sccs
    )
