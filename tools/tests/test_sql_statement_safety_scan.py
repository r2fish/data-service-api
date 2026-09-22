"""R-75: static scan of both peers' SQL statement construction shapes.

Design: docs/design/MODULE_REFACT_ARCHITECTURE_V1.md §3 D-4 ("client-
influenced statement が plain `str` で到達できない性質を新 module を含む
走査で確認する"). Work order: docs/work-orders/WORK_ORDER_R75_SQL_STATEMENT
_SAFETY_SCAN_V1.md §3, whose decisions are copied verbatim from
docs/work-orders/WORK_ORDER_R37_WP0_INVENTORY_V1.md §5.46 (1) and rulings
Z5-3, Z5-8..Z5-11, Z5-15..Z5-19.

Both choke points (`r2db_api.postgres._run`, `mitatedb_api.backend_postgres.
_execute`) already refuse a plain `str` at RUNTIME via `isinstance(statement,
(sql.SQL, sql.Composed))`. That guard cannot see a `sql.SQL(<f-string>)` (a
`sql.SQL` instance built from an unsafe expression) or a direct `.execute(`
call that never reaches a choke point at all. This file is a STATIC scan
that closes both gaps by looking at how the executed value is *constructed*
in the AST, never at SQL keywords (Z5-3: a keyword match would false-
positive on `r2db-api/src/r2db_api/delete_confirmation.py`'s user-typed
deletion phrases and on `MitateDB-api/src/mitatedb_api/ops.py`'s error
messages).

Two rules (Z5-16), both AST-shape checks with **no data-flow tracing**
beyond what is spelled out below -- this scan does not know what a
psycopg cursor actually executes against, only what the source text says:

- **Rule 1** (every `sql.SQL(...)` call in a scanned module, `呼出し位置を
  問わない` -- Z5-19, so a `sql.SQL(<f-string>)` nested inside another
  call's arguments, e.g. inside `.format(...)`, is scanned too): the first
  argument must be statically foldable to a string literal. Foldable means:
  a string literal; a `+` of two foldable expressions; or a bare name whose
  *every* binding is itself a foldable `name = expr` (or literal-valued
  `AnnAssign`) assignment -- ANY other kind of local binding to that name
  makes it non-foldable outright. Name resolution walks the FULL LEXICAL
  SCOPE CHAIN enclosing the `sql.SQL(...)` call -- every `FunctionDef`/
  `AsyncFunctionDef`/`Lambda`/`ClassDef` from innermost to outermost, ending
  at the module -- and uses the INNERMOST scope that binds the name AT ALL
  (a local binding, of any kind, in any enclosing scope, always shadows a
  same-named binding further out; it never skips past a binding scope to
  keep looking outward). The binding kinds that make a name non-foldable
  this way: a function/lambda parameter; a `for`/comprehension target; a
  `with ... as`/`except ... as`/`except* ... as` name; a `match` case
  capture (`MatchAs`/`MatchStar`/`MatchMapping`'s `**rest`); a walrus
  (`:=`) target; an `AugAssign` (`+=` etc.); a `nonlocal` declaration; a
  multi-target or tuple-unpacking `Assign`. A class body counts as a scope
  too (conservative: real Python skips a class body when resolving a name
  from a nested function, but treating it as a scope here can only ADD
  non-foldable outcomes, never remove one). One non-foldable binding among
  several for the same name (e.g. `q = "SELECT 1"` then later `q = f"SELECT
  {x}"`, or `q = "SELECT 1"` then `q += f"{x}"`) makes the whole name non-
  foldable. A self-referential chain (`q = "a"` then `q = q + "b"`) is also
  treated as non-foldable rather than followed forever. A `global X`
  declaration ANYWHERE in the module makes X non-foldable AT MODULE LEVEL
  unconditionally (a function elsewhere could reassign it to anything at
  runtime; `_module_level_bindings` below) -- a module-level assignment to
  a name some function also declares `global` for is not counted as that
  function's OWN local binding (the function does not own a local copy of
  it at all). Resolution is a single-hop lookup within the scope chain's
  own bindings (`関数内の全代入` / `module 内の全代入`, Z5-16) -- an
  imported name does not resolve in any scope and is therefore non-
  foldable by this narrow rule, whether or not the value it would carry at
  runtime happens to be a literal. That narrowness is deliberate (§3.3 of
  the work order limits rule 1's implementation range to "module 定数の
  解決、関数内の全代入" and forbids widening it); the 3 spots it makes
  non-foldable are recorded in `_ALLOWED_UNFOLDABLE` below rather than
  handled by extending the rule.
- **Rule 2** (every execution call -- see below): the STATEMENT argument's
  own outermost shape must not be an f-string, a `%`-format `BinOp`, a `+`
  `BinOp`, or a `.format()` call -- EXCEPT a `.format()`/`.join()` chain
  rooted in `sql.SQL(...)`/`sql.Composed(...)` (psycopg's own safe
  composition API; a bare `+` of two `sql.SQL(...)`/`sql.Composed(...)`
  values is NOT excepted when it is itself the direct statement argument --
  Z5-16 excepts only `.format()`/`.join()` -- though `_is_sql_composed_
  rooted` below does treat `+` as part of resolving whether a `.format()`/
  `.join()` call's own RECEIVER chain is SQL-rooted; a future legitimate
  direct `+` composition would need its own row in `_ALLOWED_UNFOLDABLE`,
  the same D-6 mechanism as rule 1's exceptions, not a new blanket rule-2
  exception). The statement argument is a `.execute(`/`.executemany(`
  call's own first argument, or its `query=` keyword (psycopg's own
  `Cursor.execute`/`executemany` parameter is named `query`, not
  `statement`). The 6 qualified functions instead have the signature
  `(cursor, statement, params=())` -- `cursor` comes first, so their
  statement is the SECOND positional argument (`_execution_statement_arg`
  below; matches the work order §3.5 spec example, `_execute(cursor,
  f"SELECT * FROM {table}")`), or their own `statement=` keyword. This
  looks only at the statement argument's own outer node, never at how a
  bare name it might be was built elsewhere ("データの流れは追わない") --
  a `sql.SQL(f"...")` VALUE passed as `_run(cursor, sql.SQL(q))` is rule 2
  clean (the outer shape is a `sql.SQL(...)` call) even when `q` itself is
  rule-1-unsafe; that combination is still caught, by rule 1, wherever the
  `sql.SQL(...)` call itself appears in the AST.

Every rule-1/rule-2 violation message has one shape (`_format_violation`
below): `f"{peer}:{relpath}:{lineno}: 規則{1|2} {detail}"` -- both `peer`
and `relpath` are always present, since a bare filename (`ops.py`,
`postgres_sql.py`, ...) exists in both peers and cannot disambiguate on
its own.

An "execution call" (D-5/Z5-15/Z5-17) is a `.execute(`/`.executemany(`
attribute call (any receiver -- not filtered by object shape, matching
D-2's "psycopg を import するかで絞らない"), or a bare-name call to one of
6 qualified functions, each resolved ONLY within its own defining module
(Z5-15: a same-named local closure elsewhere, e.g. `r2db_api.control_http.
_run`'s per-request closure, must never match) --
`_EXECUTION_QUALIFIED_NAMES` below. Two are the peers' own execution choke
points; four are same-named wrapper functions (Z5-17) that call `cursor.
execute` directly rather than through a choke point. This scan also pins
the SHAPE each scanned module brings `psycopg.sql` in through
(`_psycopg_sql_import_violations` below): `_is_sql_sql_call` recognizes
only the literal spelling `sql.SQL(...)` after an unaliased `from psycopg
import sql`, so a module using `from psycopg.sql import SQL`, `import
psycopg.sql`, an aliased `from psycopg import sql as X`, or a bare `import
psycopg` followed by a `psycopg.sql` attribute reference, would let a
`sql.SQL`-shaped call slip past rule 1 unrecognized -- and separately pins
that no scanned module uses `sql.SQL`/`sql.Composed` anywhere OTHER than
as a call's own callee, or the bare name `sql` anywhere OTHER than as an
attribute access's own base (`_sql_alias_violations` below, an `ast.walk`
over EVERY position, not limited to an assignment/default/keyword-
argument value, EXCEPT a type annotation or `isinstance()`'s own type-
tuple argument -- `_annotation_and_isinstance_safe_ids` -- since neither
stores a usable alias, and both are extremely common in both peers' own
choke points, e.g. `statement: sql.Composed | sql.SQL` and `isinstance
(statement, (sql.SQL, sql.Composed))`): `_H = {"s": sql.SQL}` then
`_H["s"](f"...")`, or `X = sql` then `X.SQL(f"...")`, would equally
slip past unrecognized. `getattr(psycopg, "sql")`-style dynamic
aliasing is NOT checked -- see the NOT-check list below.

Scan roots (D-2/Z5-8) are each peer's `src/<package>/` directory, never the
peer's repository root -- `MitateDB-api/docs/f9-execution-assets-v1/` holds
3 reference-only `.py` files (D-2) a `rglob` of `MitateDB-api/` would sweep
in. Module discovery uses `Path.rglob("*.py")` (`_discover_modules` below),
so a new file dropped anywhere under a scan root is visible to a plain
working-tree read, without being tracked by git first. `backend_sqlite.py`
is the only named exclusion (`_NAMED_EXCLUSIONS`): it is MitateDB's SQLite
storage backend, not PostgreSQL, and never touches `psycopg.sql` or either
choke point. The discovered SET (not merely its count) is pinned per peer
in `_EXPECTED_DISCOVERED_MODULES` -- a change that adds or removes a
module under a scan root must update that list in the same change set.
The observed `.executemany(` attribute-call count is ALSO pinned per peer
(`_EXPECTED_EXECUTEMANY_COUNTS`, currently 0 for both) -- a change that
starts using `.executemany(` must update that pin in the same change set.

This file has 2 node-id kinds (work order §3.4): the "construction-shape
test" (`test_sql_statement_construction_shapes_are_safe`, rule 1 + rule 2
together, one node id for every module in both peers -- module-level
parametrization is deliberately avoided so registering a new module never
grows the `tools/tests` node id count), and 4 "pin tests" (the discovered-
module set/named exclusion/`.executemany(` count, the psycopg.sql import
and alias shape, the explicit allow-table, and the D-7 空振り禁止
observation counts).

What this file does NOT check (an explicit, not exhaustive, list): whether
a `str` value ever reaches a psycopg cursor through some other path this
scan's shape rules do not name (data-flow tracing is explicitly out of
scope, Z5-16) -- concretely this includes a value passed through an
intermediate variable before an execution call (`stmt = f"...";
cur.execute(stmt)` is rule-2-clean, since `stmt` at the call site is a bare
`Name`, not one of the forbidden shapes), a dedented multi-line string
(`textwrap.dedent`) or a manual `str.join`, a `*args`-spread call
(`cur.execute(*args)` -- this scan only ever looks at `args[0]`/`args[1]`,
never a `Starred` spread), a call to one of the 6 D-5 functions reached
through an import from another module (e.g. `from .postgres import _run`
then calling the imported `_run` -- `_local_qualified_funcnames` only
matches a bare-name call INSIDE the function's own defining module), and a
dynamically-computed alias (`getattr(psycopg, "sql")`, `importlib.import_
module("psycopg.sql")`, ... -- `_sql_alias_violations` only recognizes a
literal `sql`/`sql.SQL`/`sql.Composed` expression, wherever it appears);
whether a `sql.Identifier`/`sql.Placeholder`/`sql.Literal` argument is
itself safe (psycopg's own API surface, not this file's concern); runtime
behavior of any kind (this file only reads source text via `ast.parse`, it
never imports or executes a scanned module).
"""
from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# D-2/Z5-8: (root, package name) per peer. The root is each peer's src/
# package directory, never the peer's repository root.
SRC_ROOTS: dict[str, tuple[Path, str]] = {
    "r2db": (REPO_ROOT / "r2db-api" / "src" / "r2db_api", "r2db_api"),
    "mitatedb": (REPO_ROOT / "MitateDB-api" / "src" / "mitatedb_api", "mitatedb_api"),
}

# D-2: the only named exclusion, with its reason. backend_sqlite.py talks
# to SQLite, not PostgreSQL, so it never touches psycopg.sql or either
# choke point this scan is about.
_NAMED_EXCLUSIONS: dict[str, dict[str, str]] = {
    "r2db": {},
    "mitatedb": {
        "backend_sqlite.py": "SQLite storage backend, not PostgreSQL -- "
        "never touches psycopg.sql or either choke point (D-2)",
    },
}
# D-2/Z5-8: the discovered SET, not just its count, is pinned per peer
# (verbatim relative paths from each peer's src root). A change that adds
# or removes a module under a scan root must update this list in the SAME
# change set.
_EXPECTED_DISCOVERED_MODULES: dict[str, frozenset[str]] = {
    "r2db": frozenset({
        "__init__.py",
        "audit.py",
        "audit_counts.py",
        "audit_hook.py",
        "audit_query.py",
        "auth.py",
        "backend.py",
        "capabilities_document.py",
        "contract/__init__.py",
        "control_http.py",
        "control_main.py",
        "control_plane.py",
        "credential_store.py",
        "delete_confirmation.py",
        "errors.py",
        "http.py",
        "identifier_rules.py",
        "inmemory_predicate.py",
        "inmemory_sort.py",
        "limits.py",
        "main.py",
        "mutation_binding.py",
        "ops.py",
        "paging.py",
        "pg_text_format.py",
        "pg_timeouts.py",
        "platform_declarations.py",
        "platform_upgrades.py",
        "postgres.py",
        "postgres_like.py",
        "postgres_sql.py",
        "postgres_types.py",
        "request_shape.py",
        "schema_binding.py",
        "service.py",
        "service_results.py",
        "storage_outcomes.py",
        "structured.py",
        "topology.py",
        "value_nul.py",
        "value_types.py",
    }),
    "mitatedb": frozenset({
        "__init__.py",
        "application_audit.py",
        "audit.py",
        "audit_dispatch.py",
        "audit_hook.py",
        "audit_query.py",
        "auth.py",
        "backend.py",
        "backend_postgres.py",
        "capabilities_document.py",
        "cell.py",
        "config.py",
        "constraint_resolution.py",
        "contract/__init__.py",
        "control_audit.py",
        "control_auth.py",
        "control_composition.py",
        "control_credential_store_postgres.py",
        "control_http.py",
        "control_main.py",
        "control_plane.py",
        "credential_store_postgres.py",
        "credential_wire.py",
        "delete_confirmation.py",
        "errors.py",
        "field_types.py",
        "http.py",
        "identifiers.py",
        "main.py",
        "ops.py",
        "pg_timeouts.py",
        "platform_declarations.py",
        "platform_upgrades.py",
        "pool.py",
        "postgres_reserved_names.py",
        "postgres_sql.py",
        "postgres_types.py",
        "postgres_value_domain.py",
        "provisional_gate.py",
        "request_binding.py",
        "request_limits.py",
        "request_traversal.py",
        "request_vocabulary.py",
        "service.py",
        "surfaces.py",
    }),
}

# D-5/Z5-15/Z5-17: the 6 execution-call targets, as dotted
# "package.module._function" strings -- the peers' 2 choke points, plus 4
# same-named wrapper functions. Each is called only by its own bare name,
# only within its own defining module (checked by hand: a WIDE `grep -n
# "\._run(\|\._execute("` across both peers' src/ -- not narrowed to a
# `self.` receiver -- found 0 hits, so no call site reaches one of these
# through an attribute/qualified reference this scan would have to
# resolve).
_EXECUTION_QUALIFIED_NAMES: tuple[str, ...] = (
    "r2db_api.postgres._run",
    "mitatedb_api.backend_postgres._execute",
    "mitatedb_api.control_plane._execute",
    "mitatedb_api.credential_store_postgres._execute",
    "mitatedb_api.control_credential_store_postgres._execute",
    "r2db_api.credential_store._execute",
)

# The pinned `.executemany(` count per peer (0 for both, measured by hand).
_EXPECTED_EXECUTEMANY_COUNTS: dict[str, int] = {"r2db": 0, "mitatedb": 0}

_PACKAGE_TO_PEER: dict[str, str] = {"r2db_api": "r2db", "mitatedb_api": "mitatedb"}


def _parse_qualified_execution_name(qualified: str) -> tuple[str, str, str]:
    """Split "pkg.module._func" into (peer, "module.py", "_func")."""
    package, module, func = qualified.split(".")
    return _PACKAGE_TO_PEER[package], f"{module}.py", func


# D-6/Z5-16: existing spots rule 1 cannot fold statically. Each row is
# (peer, relpath, lineno, old, reason): `old` is the violating `sql.SQL
# (...)` call's own EXACT source text (`ast.get_source_segment`), not just
# its line number -- postgres_sql.py:71 has TWO `sql.SQL(...)` calls on
# one line, so the line number alone cannot tell them apart, and an exact
# match (rather than a substring one) avoids one row's `old` accidentally
# covering a DIFFERENT, longer violation that happens to contain it as a
# substring. Every other candidate the work order's own §3.2 measurement
# raised (`sql.SQL(base_statement + "...")` x4 in both peers' platform_
# declarations.py, and the `sql.SQL(<module 定数>)` call sites in both
# peers' credential_store.py/ops.py/application_audit.py/audit_query.py)
# resolves under rule 1's name-resolution (a single, literal-valued
# module-level assignment) and is deliberately NOT listed here. See the
# work order (D-6) for the acceptance decision on each row below.
_ALLOWED_UNFOLDABLE: tuple[tuple[str, str, int, str, str], ...] = (
    (
        "r2db", "postgres_sql.py", 71,
        'sql.SQL("ASC" if direction == "asc" else "DESC")',
        "a ternary (ast.IfExp) between two string literals; not a "
        "literal, a `+`, or a name, so outside rule 1's narrow "
        "foldable-shape set",
    ),
    (
        "mitatedb", "postgres_sql.py", 23,
        "sql.SQL(token)",
        "`token` is a dict-comprehension for-target, not a `name = expr` "
        "assignment, so it does not resolve under rule 1's assignment-"
        "only name resolution (SQL_OPERATOR_TOKENS itself is an imported "
        "literal-valued dict in .backend, but tracing into an import is "
        "data-flow tracing, which Z5-16 excludes)",
    ),
    (
        "mitatedb", "postgres_types.py", 25,
        "sql.SQL(native)",
        "`native` is likewise a dict-comprehension for-target, not a "
        "`name = expr` assignment, even though _TYPES is this module's "
        "own literal-valued dict",
    ),
)


def _discover_modules(peer: str) -> list[Path]:
    root, _package = SRC_ROOTS[peer]
    excluded = _NAMED_EXCLUSIONS[peer]
    return sorted(p for p in root.rglob("*.py") if p.name not in excluded)


def _is_sql_sql_call(node: ast.AST) -> bool:
    """True for `sql.SQL(...)` (the exact spelling both peers import via
    `from psycopg import sql`), never `sql.Composed(...)` -- rule 1 is
    about `sql.SQL(...)`'s own argument (Z5-16); neither peer constructs a
    `sql.Composed(...)` directly with a non-trivial argument (checked by
    hand, 0 hits for `sql\\.Composed\\(` in either peer's src/)."""
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "SQL"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "sql"
    )


def _is_execution_call(node: ast.AST, local_qualified_funcnames: frozenset[str]) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Attribute) and func.attr in ("execute", "executemany"):
        return True
    if isinstance(func, ast.Name) and func.id in local_qualified_funcnames:
        return True
    return False


def _psycopg_sql_import_violations(module_path: Path) -> list[str]:
    """`_is_sql_sql_call` recognizes only the exact spelling `sql.SQL(...)`
    after an unaliased `from psycopg import sql`. Any other way of
    bringing `psycopg.sql` into scope would let a `sql.SQL`-shaped call
    slip past rule 1 unrecognized. Flags 4 forms: `from psycopg.sql import
    ...`, `import psycopg.sql`, an aliased `from psycopg import sql as X`,
    and a bare `import psycopg` followed by a `psycopg.sql` attribute
    reference."""
    tree = ast.parse(module_path.read_text(encoding="utf-8"), filename=str(module_path))
    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "psycopg.sql":
            violations.append(f"{module_path.name}:{node.lineno}: `from psycopg.sql import ...`")
        elif isinstance(node, ast.ImportFrom) and node.module == "psycopg":
            for alias in node.names:
                if alias.name == "sql" and alias.asname not in (None, "sql"):
                    violations.append(
                        f"{module_path.name}:{node.lineno}: "
                        f"`from psycopg import sql as {alias.asname}`"
                    )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "psycopg.sql":
                    violations.append(f"{module_path.name}:{node.lineno}: `import psycopg.sql`")
        elif isinstance(node, ast.Attribute) and node.attr == "sql":
            if isinstance(node.value, ast.Name) and node.value.id == "psycopg":
                violations.append(
                    f"{module_path.name}:{node.lineno}: `psycopg.sql` attribute reference"
                )
    return violations


def _build_parent_map(tree: ast.AST) -> dict[int, ast.AST]:
    """`id(child) -> parent` for every node in `tree`, needed to tell
    whether a `sql.SQL`/`sql.Composed` attribute access is a call's own
    callee, or a bare `sql` Name is an attribute access's own base --
    `ast.walk` alone carries no parent link."""
    parents: dict[int, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[id(child)] = node
    return parents


def _annotation_and_isinstance_safe_ids(tree: ast.Module) -> set[int]:
    """Node ids that may reference `sql.SQL`/`sql.Composed`/bare `sql`
    without being an aliasing risk even though they are not a call's own
    callee: a type annotation (`statement: sql.Composed | sql.SQL`,
    `-> sql.Composed`, `_X: dict[str, sql.SQL]` -- erased at runtime,
    never a stored value), or `isinstance()`'s own type-tuple argument
    (`isinstance(statement, (sql.SQL, sql.Composed))` -- immediately
    consumed by the type check, never stored as a callable alias). Both
    are extremely common, safe, real patterns in both peers' choke
    points; without this exemption `_sql_alias_violations` would flag
    every one of them."""
    safe: set[int] = set()

    def _mark(node: ast.AST) -> None:
        safe.add(id(node))
        for child in ast.walk(node):
            safe.add(id(child))

    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign) and node.annotation is not None:
            _mark(node.annotation)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.returns is not None:
                _mark(node.returns)
            all_args = (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs)
            for arg in all_args:
                if arg.annotation is not None:
                    _mark(arg.annotation)
            if node.args.vararg is not None and node.args.vararg.annotation is not None:
                _mark(node.args.vararg.annotation)
            if node.args.kwarg is not None and node.args.kwarg.annotation is not None:
                _mark(node.args.kwarg.annotation)
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "isinstance"
            and len(node.args) >= 2
        ):
            _mark(node.args[1])
    return safe


def _sql_alias_violations(module_path: Path) -> list[str]:
    """Flags any USE, anywhere in the module (any `ast.walk` position, not
    limited to an assignment/default/keyword-argument value), of the
    attribute `sql.SQL`/`sql.Composed` OTHER than as an immediately-called
    callee (`sql.SQL(...)`) or one of `_annotation_and_isinstance_safe_
    ids`'s 2 exempt contexts -- `sql.Identifier`/`sql.Literal`/`sql.
    Placeholder` are excluded from this half, since only `SQL`/`Composed`
    feed `_is_sql_sql_call` -- and any USE of the bare name `sql` OTHER
    than as an attribute access's own base (`sql.<anything>`, including
    `Identifier`/`Literal`/`Placeholder`) or one of the same 2 exempt
    contexts -- either shape lets a rebound name (`_H = {"s": sql.SQL}`
    then `_H["s"](f"...")`, or `X = sql` then `X.SQL(f"...")`) slip a
    `sql.SQL`-shaped call past `_is_sql_sql_call`'s literal-spelling
    match. Dynamic aliasing (`getattr(psycopg, "sql")`) is NOT checked --
    see the module docstring's NOT-check list."""
    tree = ast.parse(module_path.read_text(encoding="utf-8"), filename=str(module_path))
    parents = _build_parent_map(tree)
    safe_ids = _annotation_and_isinstance_safe_ids(tree)
    violations: list[str] = []
    for node in ast.walk(tree):
        if id(node) in safe_ids:
            continue
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "sql"
            and node.attr in ("SQL", "Composed")
        ):
            parent = parents.get(id(node))
            if not (isinstance(parent, ast.Call) and parent.func is node):
                violations.append(
                    f"{module_path.name}:{node.lineno}: `sql.{node.attr}` used somewhere "
                    "other than as a call's own callee (aliasing risk)"
                )
        elif isinstance(node, ast.Name) and node.id == "sql" and isinstance(node.ctx, ast.Load):
            parent = parents.get(id(node))
            if not (isinstance(parent, ast.Attribute) and parent.value is node):
                violations.append(
                    f"{module_path.name}:{node.lineno}: bare `sql` used somewhere other "
                    "than as an attribute access's own base (aliasing risk)"
                )
    return violations


def _names_in_target(target: ast.expr) -> list[str]:
    """Every plain `Name` bound by an assignment/`for`/`with`/comprehension
    TARGET expression, unwrapping `Tuple`/`List`/`Starred` (e.g. `a, *b =
    ...`); anything else (an attribute or subscript target) binds no bare
    name and is ignored here."""
    if isinstance(target, ast.Name):
        return [target.id]
    if isinstance(target, (ast.Tuple, ast.List)):
        names: list[str] = []
        for elt in target.elts:
            names.extend(_names_in_target(elt))
        return names
    if isinstance(target, ast.Starred):
        return _names_in_target(target.value)
    return []


def _names_in_match_pattern(pattern: ast.pattern) -> list[str]:
    """Every capture name a `match` case's pattern binds (`case [x] as y:`
    binds both `x` and `y`), recursing into nested sub-patterns
    (`MatchSequence`/`MatchMapping`/`MatchClass`/`MatchOr`). A bare
    wildcard (`case _:`) has `name=None` and binds nothing."""
    names: list[str] = []
    if isinstance(pattern, ast.MatchAs):
        if pattern.name:
            names.append(pattern.name)
        if pattern.pattern is not None:
            names.extend(_names_in_match_pattern(pattern.pattern))
    elif isinstance(pattern, ast.MatchStar):
        if pattern.name:
            names.append(pattern.name)
    elif isinstance(pattern, ast.MatchMapping):
        if pattern.rest:
            names.append(pattern.rest)
        for p in pattern.patterns:
            names.extend(_names_in_match_pattern(p))
    elif isinstance(pattern, ast.MatchSequence):
        for p in pattern.patterns:
            names.extend(_names_in_match_pattern(p))
    elif isinstance(pattern, ast.MatchClass):
        for p in pattern.patterns:
            names.extend(_names_in_match_pattern(p))
        for p in pattern.kwd_patterns:
            names.extend(_names_in_match_pattern(p))
    elif isinstance(pattern, ast.MatchOr):
        for p in pattern.patterns:
            names.extend(_names_in_match_pattern(p))
    return names


def _iter_scope_nodes(node: ast.AST):
    """Yield every descendant of `node` (`node` itself excluded) that is
    still in the SAME scope -- never descending into a nested `def`/
    `async def`/`class`/`lambda`, each of which starts its own scope."""
    for child in ast.iter_child_nodes(node):
        yield child
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
            continue
        yield from _iter_scope_nodes(child)


def _own_scope_declared_names(stmts: list[ast.stmt]) -> tuple[set[str], set[str]]:
    """(global_names, nonlocal_names) declared directly within `stmts`'
    own scope (never descending into a nested def/class/lambda)."""
    globals_: set[str] = set()
    nonlocals_: set[str] = set()
    root = ast.Module(body=stmts, type_ignores=[])
    for node in _iter_scope_nodes(root):
        if isinstance(node, ast.Global):
            globals_.update(node.names)
        elif isinstance(node, ast.Nonlocal):
            nonlocals_.update(node.names)
    return globals_, nonlocals_


def _param_names(func: ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda) -> tuple[str, ...]:
    a = func.args
    names = [p.arg for p in (*a.posonlyargs, *a.args, *a.kwonlyargs)]
    if a.vararg is not None:
        names.append(a.vararg.arg)
    if a.kwarg is not None:
        names.append(a.kwarg.arg)
    return tuple(names)


def _collect_bindings(
    stmts: list[ast.stmt], *, params: tuple[str, ...] = ()
) -> dict[str, list[ast.expr | None]]:
    """Every name bound within `stmts`' own scope (a function/class body or
    the module body), as a dict of value lists. A `None` entry marks an
    OPAQUE binding -- one that is not a plain `name = expr` `Assign` (or a
    literal-valued `AnnAssign`) this scan can itself inspect: a `params`
    entry, a `for`/comprehension target, a `with ... as`/`except ... as`/
    `except* ... as` name, a `match` case capture, a walrus (`:=`) target,
    an `AugAssign` (`+=` etc.), a `nonlocal` declaration, or a multi-
    target/tuple-unpacking `Assign`. `_is_foldable` treats ANY `None`
    entry as poisoning the whole name (a parameter or `for`-target sharing
    an outer scope's constant's name must never resolve to that
    constant's value -- `def f(cursor, _Q): _run(cursor, sql.SQL(_Q))`
    must be non-foldable even when a module-level `_Q = "SELECT 1"`
    exists, because `_Q` is bound locally, and a local binding is never
    skipped in favor of a same-named outer one).

    A name this scope declares `global` for is NEVER recorded as a LOCAL
    binding here (an assignment to it inside this scope writes the
    MODULE's own name, not a local one) -- `_module_level_bindings` below
    is where such a name is instead poisoned, at module level, for every
    scope. A name declared `nonlocal` IS recorded here, unconditionally
    opaque (conservative: this scan does not resolve which specific
    enclosing function actually owns it).

    Recurses into `if`/`for`/`while`/`with`/`try`/`try*`/`match` bodies
    but never into a nested `def`/`async def`/`class`/`lambda` (each
    starts its own scope). A second, expression-level pass
    (`_iter_scope_nodes`) -- still never crossing into a nested scope --
    separately finds a walrus target wherever it appears (an `if` test, a
    call argument, ...) and a comprehension target, since those are not
    visible to the statement-level walk below. A comprehension's own
    target technically opens ITS OWN, narrower scope in real Python, but
    this scan poisons the SAME name in the ENCLOSING scope instead of
    modeling that separately -- a deliberate false positive, in the safe
    direction (it can only make something non-foldable that real Python
    would still fold, never the reverse).
    """
    bindings: dict[str, list[ast.expr | None]] = {}
    global_names, nonlocal_names = _own_scope_declared_names(stmts)
    for p in params:
        bindings.setdefault(p, []).append(None)

    def _opaque_name(name: str) -> None:
        if name in global_names:
            return
        bindings.setdefault(name, []).append(None)

    def _opaque(target: ast.expr) -> None:
        for name in _names_in_target(target):
            _opaque_name(name)

    def _bind(name: str, value: ast.expr) -> None:
        if name in global_names:
            return
        bindings.setdefault(name, []).append(value)

    def _visit(body: list[ast.stmt]) -> None:
        for stmt in body:
            if isinstance(stmt, (ast.Global, ast.Nonlocal)):
                continue  # handled up front
            if isinstance(stmt, ast.Assign):
                if len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name):
                    _bind(stmt.targets[0].id, stmt.value)
                else:
                    for target in stmt.targets:
                        _opaque(target)
            elif isinstance(stmt, ast.AugAssign):
                if isinstance(stmt.target, ast.Name):
                    _opaque_name(stmt.target.id)
            elif isinstance(stmt, ast.AnnAssign):
                if isinstance(stmt.target, ast.Name) and stmt.value is not None:
                    _bind(stmt.target.id, stmt.value)
            elif isinstance(stmt, ast.If):
                _visit(stmt.body)
                _visit(stmt.orelse)
            elif isinstance(stmt, (ast.For, ast.AsyncFor)):
                _opaque(stmt.target)
                _visit(stmt.body)
                _visit(stmt.orelse)
            elif isinstance(stmt, ast.While):
                _visit(stmt.body)
                _visit(stmt.orelse)
            elif isinstance(stmt, (ast.With, ast.AsyncWith)):
                for item in stmt.items:
                    if item.optional_vars is not None:
                        _opaque(item.optional_vars)
                _visit(stmt.body)
            elif isinstance(stmt, (ast.Try, ast.TryStar)):
                _visit(stmt.body)
                for handler in stmt.handlers:
                    if handler.name:
                        _opaque_name(handler.name)
                    _visit(handler.body)
                _visit(stmt.orelse)
                _visit(stmt.finalbody)
            elif isinstance(stmt, ast.Match):
                for case in stmt.cases:
                    for name in _names_in_match_pattern(case.pattern):
                        _opaque_name(name)
                    _visit(case.body)
            # FunctionDef / AsyncFunctionDef / ClassDef / Lambda: a new
            # scope starts there; do not descend.

    _visit(stmts)

    for name in nonlocal_names:
        bindings.setdefault(name, []).append(None)

    root = ast.Module(body=stmts, type_ignores=[])
    for node in _iter_scope_nodes(root):
        if isinstance(node, ast.NamedExpr) and isinstance(node.target, ast.Name):
            _opaque_name(node.target.id)
        elif isinstance(node, ast.comprehension):
            _opaque(node.target)

    return bindings


def _function_scope_bindings(
    func: ast.FunctionDef | ast.AsyncFunctionDef,
) -> dict[str, list[ast.expr | None]]:
    """A function's own pushed scope bindings (`_collect_bindings` on its
    immediate body), PLUS: a `nonlocal X` declared ANYWHERE in this
    function's own subtree -- including inside a nested `def`/`async
    def` -- poisons X here too (the function-scope analogue of
    `_module_level_bindings`'s `global` handling). `_collect_bindings`'s
    own `nonlocal_names` handling only sees a `nonlocal` statement in the
    SAME scope; a nested function's `nonlocal X` instead reaches back
    into ITS enclosing function's namespace at runtime, so that
    enclosing function's own `X` (here) must be non-foldable too, even
    when this function's own body assigns X a literal directly."""
    bindings = _collect_bindings(func.body, params=_param_names(func))
    for node in ast.walk(func):
        if isinstance(node, ast.Nonlocal):
            for name in node.names:
                bindings.setdefault(name, []).append(None)
    return bindings


def _module_level_bindings(tree: ast.Module) -> dict[str, list[ast.expr | None]]:
    """Module-scope bindings, plus a `global` declaration's whole-module
    effect: if ANY function anywhere in this module declares `global X`,
    X is non-foldable at module level regardless of its own `Assign`
    value(s), since a function elsewhere could reassign it to anything at
    runtime."""
    bindings = _collect_bindings(tree.body)
    for node in ast.walk(tree):
        if isinstance(node, ast.Global):
            for name in node.names:
                bindings.setdefault(name, []).append(None)
    return bindings


def _is_foldable(
    node: ast.expr,
    chain: list[dict[str, list[ast.expr | None]]],
    index: int = 0,
    _visiting: frozenset[str] = frozenset(),
) -> bool:
    """Rule 1's foldability check (see the module docstring). `chain` is
    the full lexical scope chain enclosing the `sql.SQL(...)` call,
    innermost first, ending with the module's own bindings; `index` is
    where resolution starts searching (0 = from the innermost scope) --
    recursing into a NAME's own bound value re-starts the search from the
    SCOPE WHERE THAT VALUE WAS FOUND, outward (matching real lexical
    scoping: a free name inside an assigned expression resolves relative
    to where that expression is written, not relative to the ORIGINAL
    call site). `_visiting` guards a self-referential chain (`q = "a"`
    then `q = q + "b"`) -- resolving a name pushes it onto `_visiting`;
    seeing it again while still resolving it is a cycle, treated as non-
    foldable rather than recursing forever."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return True
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _is_foldable(node.left, chain, index, _visiting) and _is_foldable(
            node.right, chain, index, _visiting
        )
    if isinstance(node, ast.Name):
        if node.id in _visiting:
            return False
        for i in range(index, len(chain)):
            if node.id in chain[i]:
                values = chain[i][node.id]
                if not values:
                    return False
                nxt = _visiting | {node.id}
                return all(v is not None and _is_foldable(v, chain, i, nxt) for v in values)
        return False
    return False


def _is_sql_composed_rooted(node: ast.expr) -> bool:
    """Internal helper used ONLY to resolve whether a `.format()`/
    `.join()` call's own RECEIVER chain is `sql.SQL(...)`/`sql.Composed
    (...)`-rooted, the one shape rule 2 excepts (see the module
    docstring's rule-2 paragraph: a bare `+` is never independently
    excepted at the top level of a statement argument -- only its role
    inside resolving a `.format()`/`.join()` receiver, here)."""
    if isinstance(node, ast.Call):
        func = node.func
        if (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id == "sql"
            and func.attr in ("SQL", "Composed")
        ):
            return True
        if isinstance(func, ast.Attribute) and func.attr in ("format", "join"):
            return _is_sql_composed_rooted(func.value)
        return False
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _is_sql_composed_rooted(node.left) and _is_sql_composed_rooted(node.right)
    return False


def _classify_execution_arg(node: ast.expr) -> str | None:
    """None if `node`'s own outer shape is fine as an execution call's
    statement argument; else a short violation reason (rule 2, Z5-16).
    Looks only at the outermost node -- a bare `Name` is never inspected
    further here ("データの流れは追わない")."""
    if isinstance(node, ast.JoinedStr):
        return "f-string"
    if isinstance(node, ast.BinOp):
        if isinstance(node.op, ast.Mod):
            return "% format"
        if isinstance(node.op, ast.Add):
            return "str + concatenation"
        return None
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "format":
        if _is_sql_composed_rooted(node.func.value):
            return None
        return ".format()"
    return None


def _execution_statement_arg(node: ast.Call, is_qualified: bool) -> ast.expr | None:
    """The node holding the *statement* value for an execution call. A
    `.execute(`/`.executemany(` attribute call takes it as its own first
    argument, or its `query=` keyword (psycopg's own `Cursor.execute`/
    `executemany` parameter is named `query`, not `statement`). Each of
    the 6 qualified functions (D-5) instead has the signature `(cursor,
    statement, params=())` -- `cursor` first -- so their statement is the
    SECOND positional argument (matching the work order §3.5 spec
    example: `_execute(cursor, f"SELECT * FROM {table}")`), or their own
    `statement=` keyword. The keyword name checked therefore depends on
    `is_qualified`: `query` for a `.execute(`/`.executemany(` attribute
    call, `statement` for one of the 6 qualified functions -- never both,
    since psycopg's `query` and the 6 functions' own `statement` are
    different call shapes."""
    args = node.args[1:] if is_qualified else node.args
    if args:
        return args[0]
    keyword_name = "statement" if is_qualified else "query"
    for kw in node.keywords:
        if kw.arg == keyword_name:
            return kw.value
    return None


def _local_qualified_funcnames(peer: str, relpath: str) -> frozenset[str]:
    return frozenset(
        func
        for name in _EXECUTION_QUALIFIED_NAMES
        for (name_peer, name_module, func) in (_parse_qualified_execution_name(name),)
        if (name_peer, name_module) == (peer, relpath)
    )


def _allow_table_covers(peer: str, relpath: str, lineno: int, segment: str | None) -> bool:
    """Whether an allow-table row (D-6) covers this specific rule-1
    violation -- matched by (peer, relpath, lineno) AND the row's `old`
    text being an EXACT match of the violating call's OWN source text: a
    location match alone cannot tell apart two `sql.SQL(...)` calls
    sharing one line (postgres_sql.py:71), and an exact (rather than
    substring) match keeps one row from silently covering a different,
    longer violation that merely contains it."""
    return any(
        (a_peer, a_relpath, a_lineno) == (peer, relpath, lineno) and segment == a_old
        for a_peer, a_relpath, a_lineno, a_old, _reason in _ALLOWED_UNFOLDABLE
    )


def _format_violation(peer: str, relpath: str, lineno: int, kind: str, detail: str) -> str:
    """The one failure-message shape every rule-1/rule-2 violation report
    uses: `peer` and `relpath` disambiguate a module name that exists in
    both peers (e.g. `ops.py`), and the rule number is always spelled
    out."""
    rule_number = 1 if kind == "rule1" else 2
    return f"{peer}:{relpath}:{lineno}: 規則{rule_number} {detail}"


def _scan_module(
    peer: str,
    relpath: str,
    source: str,
    tree: ast.Module,
    module_bindings: dict[str, list[ast.expr | None]],
    local_qualified_funcnames: frozenset[str],
) -> list[tuple[int, str, str, str | None]]:
    """Every rule 1 / rule 2 violation in this module, UNFILTERED by the
    allow table (D-6) -- callers apply `_allow_table_covers` themselves
    (`test_explicit_allow_table_is_pinned` needs the raw set to pin the
    allow table against, not an already-filtered one). Each record is
    `(lineno, kind, detail, segment)`; `kind` is `"rule1"` or `"rule2"`;
    `segment` is the violating `sql.SQL(...)` call's own exact source
    text (rule 1 only -- `None` for rule 2 -- see `_allow_table_covers`).
    Builds the full lexical scope chain (`_is_foldable`'s `chain`) as it
    descends into a nested `FunctionDef`/`AsyncFunctionDef`/`Lambda`/
    `ClassDef`, pushing that scope's own bindings onto the front -- a
    function/lambda scope via `_function_scope_bindings` (which also
    poisons a name `nonlocal`-declared anywhere in ITS subtree); a
    `ClassDef`'s own bindings are visible ONLY to `sql.SQL(...)` calls
    written directly in the class body, never carried into a nested
    `def`'s own chain (`_visit`'s `check_chain`/`descend_chain` split).
    """
    violations: list[tuple[int, str, str, str | None]] = []
    Chain = list[dict[str, list[ast.expr | None]]]

    def _visit(node: ast.AST, check_chain: Chain, descend_chain: Chain) -> None:
        """`check_chain` is what `_is_foldable` resolves a `sql.SQL(...)`
        call's argument against AT THIS node; `descend_chain` is what a
        NEWLY entered function/lambda/class scope is pushed onto. The two
        differ only right after a `ClassDef`: `check_chain` gains the
        class body's own bindings (so a `sql.SQL(...)` call written
        DIRECTLY in the class body, not inside a method, sees them), but
        `descend_chain` does NOT (a class body is never part of a
        method's own free-variable resolution in real Python, so
        `descend_chain` is what a nested `def`/`class` inside this
        class body is pushed onto, skipping the class layer)."""
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                new_chain = [_function_scope_bindings(child)] + descend_chain
                _visit(child, new_chain, new_chain)
                continue
            if isinstance(child, ast.Lambda):
                lambda_bindings = {p: [None] for p in _param_names(child)}
                new_chain = [lambda_bindings] + descend_chain
                _visit(child, new_chain, new_chain)
                continue
            if isinstance(child, ast.ClassDef):
                class_bindings = _collect_bindings(child.body)
                _visit(child, [class_bindings] + descend_chain, descend_chain)
                continue
            if _is_sql_sql_call(child):
                assert isinstance(child, ast.Call)
                if child.args and not _is_foldable(child.args[0], check_chain):
                    segment = ast.get_source_segment(source, child)
                    violations.append(
                        (child.lineno, "rule1", "sql.SQL(...) の引数が静的に文字列リテラルへ畳めない", segment)
                    )
            elif _is_execution_call(child, local_qualified_funcnames):
                assert isinstance(child, ast.Call)
                is_qualified = isinstance(child.func, ast.Name)
                stmt_arg = _execution_statement_arg(child, is_qualified)
                if stmt_arg is not None:
                    reason = _classify_execution_arg(stmt_arg)
                    if reason is not None:
                        violations.append(
                            (child.lineno, "rule2", f"実行呼出しのstatement引数に{reason}を直接置いている", None)
                        )
            _visit(child, check_chain, descend_chain)

    _visit(tree, [module_bindings], [module_bindings])
    return violations


def test_scan_roots_are_pinned_to_src_and_exclude_named_modules() -> None:
    """D-2/Z5-8: scan roots are each peer's `src/<package>/`, never the
    peer's repository root, and `backend_sqlite.py` is the only named
    exclusion, with a non-empty reason. The discovered SET (not just its
    count) is pinned per peer against `_EXPECTED_DISCOVERED_MODULES`, and
    the `.executemany(` attribute-call count is pinned per peer against
    `_EXPECTED_EXECUTEMANY_COUNTS`."""
    expected_root_names = {"r2db": "r2db_api", "mitatedb": "mitatedb_api"}
    for peer, (root, _package) in SRC_ROOTS.items():
        assert root.name == expected_root_names[peer]
        assert root.parent.name == "src"

    problems: list[str] = []
    for peer, reasons in _NAMED_EXCLUSIONS.items():
        for name, reason in reasons.items():
            if not reason.strip():
                problems.append(f"{peer}: excluded module {name!r} has an empty reason")
    assert not problems, "\n".join(problems)

    for peer, (root, _package) in SRC_ROOTS.items():
        discovered = {str(p.relative_to(root)) for p in _discover_modules(peer)}
        expected = _EXPECTED_DISCOVERED_MODULES[peer]
        assert discovered == expected, (
            f"{peer}: discovered set differs from the pin -- "
            f"missing={sorted(expected - discovered)} "
            f"extra={sorted(discovered - expected)}"
        )

    assert "backend_sqlite.py" in _NAMED_EXCLUSIONS["mitatedb"]
    assert not any(p.name == "backend_sqlite.py" for p in _discover_modules("mitatedb"))

    executemany_totals: dict[str, int] = {peer: 0 for peer in SRC_ROOTS}
    for peer, (root, _package) in SRC_ROOTS.items():
        for module_path in _discover_modules(peer):
            tree = ast.parse(module_path.read_text(encoding="utf-8"), filename=str(module_path))
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "executemany"
                ):
                    executemany_totals[peer] += 1
    for peer in SRC_ROOTS:
        assert executemany_totals[peer] == _EXPECTED_EXECUTEMANY_COUNTS[peer], (
            f"{peer}: `.executemany(` count is {executemany_totals[peer]}, pinned at "
            f"{_EXPECTED_EXECUTEMANY_COUNTS[peer]} -- update the pin in the SAME change "
            "set that starts using .executemany("
        )


def test_psycopg_sql_import_shape_is_pinned() -> None:
    """Every discovered module brings `psycopg.sql` in only through the
    one spelling `_is_sql_sql_call` recognizes (`_psycopg_sql_import_
    violations`), and rebinds neither `sql` nor `sql.SQL`/`sql.Composed`
    to a new name anywhere (`_sql_alias_violations`). Measured: 0
    violations of either kind across both peers' discovered modules (21
    of them actually reference `psycopg.sql` at all, all via a plain,
    unaliased `from psycopg import sql`)."""
    violations: list[str] = []
    for peer in SRC_ROOTS:
        for module_path in _discover_modules(peer):
            violations.extend(_psycopg_sql_import_violations(module_path))
            violations.extend(_sql_alias_violations(module_path))
    assert not violations, "\n".join(violations)


def test_explicit_allow_table_is_pinned() -> None:
    """D-6/Z5-16: pins the explicit allow table against a LIVE, unfiltered
    scan, not merely a row count. Every row must (a) name an existing
    module with a non-empty reason, (b) match at least one REAL rule-1
    violation found by an unfiltered scan (no "dead" row), and (c) every
    unfiltered rule-1 violation found anywhere in either peer must be
    matched by at least one row (no violation slips through unlisted just
    because it shares a line with an allowed one -- `_allow_table_covers`
    matches by an EXACT source-text comparison, not merely by line
    number, precisely to catch that: postgres_sql.py:71 carries TWO
    `sql.SQL(...)` calls on the one line)."""
    assert len(_ALLOWED_UNFOLDABLE) == 3
    matched_counts = [0] * len(_ALLOWED_UNFOLDABLE)
    unmatched: list[str] = []

    for peer, (root, _package) in SRC_ROOTS.items():
        for module_path in _discover_modules(peer):
            relpath = str(module_path.relative_to(root))
            source = module_path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(module_path))
            module_bindings = _module_level_bindings(tree)
            local_qualified = _local_qualified_funcnames(peer, relpath)
            for lineno, kind, detail, segment in _scan_module(
                peer, relpath, source, tree, module_bindings, local_qualified
            ):
                if kind != "rule1":
                    continue
                hit = False
                for i, (a_peer, a_relpath, a_lineno, a_old, _reason) in enumerate(_ALLOWED_UNFOLDABLE):
                    if (a_peer, a_relpath, a_lineno) == (peer, relpath, lineno) and segment == a_old:
                        matched_counts[i] += 1
                        hit = True
                if not hit:
                    unmatched.append(_format_violation(peer, relpath, lineno, kind, detail))

    assert not unmatched, "rule-1 violation(s) not covered by the allow table:\n" + "\n".join(unmatched)
    dead = [
        f"{_ALLOWED_UNFOLDABLE[i][0]}:{_ALLOWED_UNFOLDABLE[i][1]}:{_ALLOWED_UNFOLDABLE[i][2]}"
        for i, count in enumerate(matched_counts) if count == 0
    ]
    assert not dead, f"allow-table row(s) matching 0 live violations (dead): {dead}"

    for peer, relpath, _lineno, _old, reason in _ALLOWED_UNFOLDABLE:
        assert peer in SRC_ROOTS
        assert reason.strip()
        module_path = SRC_ROOTS[peer][0] / relpath
        assert module_path.is_file(), f"{peer}:{relpath} does not exist"


def test_execution_and_sql_calls_are_observed_in_both_peers() -> None:
    """D-7 (空振り禁止): each of the 6 qualified execution-call targets is
    called at least once, by its own bare name, inside its own defining
    module; each peer has at least one `sql.SQL(...)` call, at least one
    execution call overall (the union of the 6 targets and a bare
    `.execute(`/`.executemany(` attribute call), and at least one bare
    `.execute(` attribute call specifically (a `.execute(`-only
    regression, e.g. breaking its own recognition, would otherwise slip
    past the union-only check since the 6 qualified targets alone already
    satisfy it). `.executemany(` has its own pinned-count check in
    `test_scan_roots_are_pinned_to_src_and_exclude_named_modules`."""
    by_qualified_name: dict[str, int] = {name: 0 for name in _EXECUTION_QUALIFIED_NAMES}
    sql_call_totals: dict[str, int] = {peer: 0 for peer in SRC_ROOTS}
    execution_call_totals: dict[str, int] = {peer: 0 for peer in SRC_ROOTS}
    execute_attr_totals: dict[str, int] = {peer: 0 for peer in SRC_ROOTS}

    for peer, (root, package) in SRC_ROOTS.items():
        for module_path in _discover_modules(peer):
            relpath = str(module_path.relative_to(root))
            local_qualified = _local_qualified_funcnames(peer, relpath)
            tree = ast.parse(module_path.read_text(encoding="utf-8"), filename=str(module_path))
            for node in ast.walk(tree):
                if _is_sql_sql_call(node):
                    sql_call_totals[peer] += 1
                elif _is_execution_call(node, local_qualified):
                    execution_call_totals[peer] += 1
                    assert isinstance(node, ast.Call)
                    if isinstance(node.func, ast.Attribute) and node.func.attr == "execute":
                        execute_attr_totals[peer] += 1
                    if isinstance(node.func, ast.Name) and node.func.id in local_qualified:
                        qualified = f"{package}.{relpath[:-3]}.{node.func.id}"
                        if qualified in by_qualified_name:
                            by_qualified_name[qualified] += 1

    zero_named = sorted(name for name, count in by_qualified_name.items() if count < 1)
    assert not zero_named, f"execution-call target(s) with 0 observed calls: {zero_named}"
    for peer in SRC_ROOTS:
        assert sql_call_totals[peer] >= 1, f"{peer}: 0 sql.SQL(...) calls observed"
        assert execution_call_totals[peer] >= 1, f"{peer}: 0 execution calls observed"
        assert execute_attr_totals[peer] >= 1, f"{peer}: 0 `.execute(` attribute calls observed"


def test_sql_statement_construction_shapes_are_safe() -> None:
    """The single construction-shape test (work order §3.4): rule 1 and
    rule 2 over every discovered module in both peers, in one node id
    regardless of how many modules exist (module-level parametrization is
    deliberately avoided)."""
    violations: list[str] = []
    for peer, (root, _package) in SRC_ROOTS.items():
        for module_path in _discover_modules(peer):
            relpath = str(module_path.relative_to(root))
            source = module_path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(module_path))
            module_bindings = _module_level_bindings(tree)
            local_qualified = _local_qualified_funcnames(peer, relpath)
            for lineno, kind, detail, segment in _scan_module(
                peer, relpath, source, tree, module_bindings, local_qualified
            ):
                if kind == "rule1" and _allow_table_covers(peer, relpath, lineno, segment):
                    continue
                violations.append(_format_violation(peer, relpath, lineno, kind, detail))
    assert not violations, "SQL statement construction violation(s):\n" + "\n".join(violations)
