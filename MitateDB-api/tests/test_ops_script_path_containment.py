"""Every path `ops` hands to `psql -f` is resolved and contained.

`ops deprovision` (the `0004` script) and `ops upgrade-applications` (each
discovered per-application upgrade script) pass a file from the migrations
directory to `psql -f`; a file that resolves outside `_migrations_dir()`
(e.g. a symlink planted in its place) must end the run with a fixed message
-- the refused path is never echoed, no `psql` subprocess starts, and
`upgrade-applications` refuses before it visits any application. A
migrations directory that is itself a symlink still works, and `psql` then
receives the resolved path.

No database is needed: `subprocess.run` and the registry lookup are
replaced, and `psycopg.connect` is replaced by a failure.
"""
from __future__ import annotations

import ast
import subprocess
from pathlib import Path

import pytest

import mitatedb_api.ops as ops

_DSN = "postgresql://ops@example.invalid:5432/platform"
_DEPROVISION_SCRIPT = "0004_deprovision_application.sql"
_OUTSIDE_MESSAGE = "error: deprovision: resolved migration file path is outside the migrations directory\n"
_UPGRADE_OUTSIDE_MESSAGE = "error: upgrade-applications: resolved migration file path is outside the migrations directory\n"


@pytest.fixture
def ops_env(monkeypatch, tmp_path):
    for name in (*ops._LIBPQ_ENV_VAR_FOR_CONNINFO_KEY.values(), *ops._LIBPQ_CONNECTION_ENV_VARS_WITHOUT_A_CONNINFO_KEY):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("MITATEDB_PROVISION_DSN", _DSN)
    monkeypatch.setattr(ops, "_lookup_application_registered_at", lambda dsn, application_id: "stamp")
    calls: list[list[str]] = []

    def _fake_run(argv, **kwargs):
        if argv[:2] == ["psql", "--version"]:
            return subprocess.CompletedProcess(argv, 0, stdout="psql (PostgreSQL) 16.4", stderr="")
        calls.append(list(argv))
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    def _no_connection(*args, **kwargs):
        pytest.fail("an application was visited: psycopg.connect was called")

    monkeypatch.setattr(subprocess, "run", _fake_run)
    monkeypatch.setattr(ops.psycopg, "connect", _no_connection)
    outside = tmp_path / "outside"
    outside.mkdir()
    return calls, outside


def _deprovision(monkeypatch, migrations_dir: Path) -> None:
    monkeypatch.setenv("MITATEDB_MIGRATIONS_DIR", str(migrations_dir))
    phrase = ops._deprovision_confirmation_phrase("dpapp", "stamp")
    ops.main(["deprovision", "dpapp", "--confirm", phrase, "--lock-timeout", "5000ms"])


def test_deprovision_refuses_a_script_symlinked_outside_the_migrations_directory(monkeypatch, capsys, tmp_path, ops_env):
    calls, outside = ops_env
    target = outside / "evil.sql"
    target.write_text("-- not a real migration\n")
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    (migrations / _DEPROVISION_SCRIPT).symlink_to(target)
    with pytest.raises(SystemExit) as excinfo:
        _deprovision(monkeypatch, migrations)
    captured = capsys.readouterr()
    assert excinfo.value.code == 2
    assert captured.err == _OUTSIDE_MESSAGE
    assert str(target) not in captured.err and str(target) not in captured.out
    assert calls == []


def test_deprovision_through_a_symlinked_migrations_directory_passes_the_resolved_path_to_psql(monkeypatch, tmp_path, ops_env):
    calls, _ = ops_env
    real = tmp_path / "real_migrations"
    real.mkdir()
    (real / _DEPROVISION_SCRIPT).write_text("-- synthetic\n")
    link = tmp_path / "migrations_link"
    link.symlink_to(real)
    _deprovision(monkeypatch, link)
    assert len(calls) == 1
    argv = calls[0]
    assert argv[0] == "psql"
    assert argv[argv.index("-f") + 1] == str((real / _DEPROVISION_SCRIPT).resolve())
    assert argv[argv.index("-f") + 1] != str(link / _DEPROVISION_SCRIPT)


def test_upgrade_applications_refuses_a_script_symlinked_outside_before_visiting_any_application(
    monkeypatch, capsys, tmp_path, ops_env,
):
    calls, outside = ops_env
    target = outside / "evil_upgrade.sql"
    target.write_text("-- not a real upgrade\n")
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    (migrations / "0009_synthetic_upgrade.sql").symlink_to(target)
    monkeypatch.setenv("MITATEDB_MIGRATIONS_DIR", str(migrations))
    with pytest.raises(SystemExit) as excinfo:
        ops.main(["upgrade-applications", "--lock-timeout", "5000ms"])
    captured = capsys.readouterr()
    assert excinfo.value.code == 2
    assert captured.err == _UPGRADE_OUTSIDE_MESSAGE
    assert str(target) not in captured.err and str(target) not in captured.out
    assert calls == []


# ===========================================================================
# every psql `-f` launch takes its file from a containment helper
# ===========================================================================

_CONTAINMENT_HELPERS = frozenset({"_resolve_contained_migration_path", "_resolve_platform_migration_file"})
_EXPECTED_PSQL_FILE_LAUNCHERS = frozenset({"_run_deprovision_script", "_run_upgrade_script", "cmd_apply_platform_migration"})


def _own_nodes(function: ast.AST):
    """The nodes of `function`'s own body, not those of a nested function,
    lambda or class."""
    stack = list(ast.iter_child_nodes(function))
    while stack:
        node = stack.pop()
        yield node
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
            stack.extend(ast.iter_child_nodes(node))


def _names_in(expression: "ast.AST | None") -> "set[str]":
    if expression is None:
        return set()
    return {node.id for node in ast.walk(expression) if isinstance(node, ast.Name)}


def _calls_helper(expression: "ast.AST | None") -> bool:
    return expression is not None and any(
        isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _CONTAINMENT_HELPERS
        for node in ast.walk(expression)
    )


def _bindings(function: ast.AST) -> "dict[str, list[ast.AST | None]]":
    """Every expression each local name is bound from inside `function`
    (`None` for a binding whose source is not an expression, e.g. a
    `with ... as` or `except ... as` name)."""
    found: "dict[str, list[ast.AST | None]]" = {}

    def bind(target: ast.AST, source: "ast.AST | None") -> None:
        for name in _names_in(target):
            found.setdefault(name, []).append(source)

    for node in _own_nodes(function):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                bind(target, node.value)
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
            bind(node.target, node.value)
        elif isinstance(node, (ast.For, ast.AsyncFor)):
            bind(node.target, node.iter)
        elif isinstance(node, ast.NamedExpr):
            bind(node.target, node.value)
        elif isinstance(node, ast.withitem) and node.optional_vars is not None:
            bind(node.optional_vars, None)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            found.setdefault(node.name, []).append(None)
    return found


def _psql_file_arguments(function: ast.AST) -> "list[ast.expr] | None":
    """Every expression right after a `"-f"` / `"--file"` element in a list
    or tuple literal of a function that calls anything on `subprocess`;
    `None` when the function makes no such call or names no such element.
    An option with no following element yields the option constant itself,
    which is never an accepted shape."""
    launches = False
    arguments: "list[ast.expr]" = []
    for node in _own_nodes(function):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
            if node.func.value.id == "subprocess":
                launches = True
        if isinstance(node, (ast.List, ast.Tuple)):
            for index, element in enumerate(node.elts):
                if isinstance(element, ast.Constant) and element.value in ("-f", "--file"):
                    arguments.append(node.elts[index + 1] if index + 1 < len(node.elts) else element)
    return arguments if launches and arguments else None


def _subprocess_import_forms() -> "list[str]":
    """How `ops` brings `subprocess` in: one entry per import statement
    that names it, `import subprocess` spelled exactly that way when it
    carries no alias."""
    source_path = Path(ops.__file__)
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    forms: "list[str]" = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "subprocess" or alias.name.startswith("subprocess."):
                    forms.append(f"import {alias.name}" + (f" as {alias.asname}" if alias.asname else ""))
        elif isinstance(node, ast.ImportFrom) and node.module is not None and node.module.split(".")[0] == "subprocess":
            forms.append(f"from {node.module} import ...")
    return forms


def _psql_file_launchers_and_their_provenance() -> "tuple[dict[str, bool], set[str]]":
    """`({launching function: its -f file comes from a containment helper},
    launching functions)`. The file argument must be `str(<name>)`, and
    `<name>` must be derived: bound only from expressions that call a
    containment helper or use an already-derived name, or (for a parameter)
    passed a derived expression at EVERY call site in the module."""
    source_path = Path(ops.__file__)
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    functions = {node.name: node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    bindings = {name: _bindings(function) for name, function in functions.items()}
    parameters = {
        name: [argument.arg for argument in (*function.args.posonlyargs, *function.args.args, *function.args.kwonlyargs)]
        for name, function in functions.items()
    }
    call_sites: "dict[str, list[tuple[str, ast.Call]]]" = {name: [] for name in functions}
    for caller, function in [*functions.items(), ("<module>", tree)]:
        for node in _own_nodes(function):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in functions:
                call_sites[node.func.id].append((caller, node))
    derived: "dict[str, set[str]]" = {name: set() for name in functions}
    derived["<module>"] = set()
    changed = True
    while changed:
        changed = False
        for name in functions:
            candidates = set(bindings[name]) | set(parameters[name])
            for local in candidates:
                if local in derived[name]:
                    continue
                sources = bindings[name].get(local, [])
                if local in parameters[name]:
                    index = parameters[name].index(local)
                    sites = call_sites[name]
                    passed = []
                    for caller, call in sites:
                        by_keyword = [keyword.value for keyword in call.keywords if keyword.arg == local]
                        if by_keyword:
                            passed.append((caller, by_keyword[0]))
                        elif index < len(call.args):
                            passed.append((caller, call.args[index]))
                        else:
                            passed.append((caller, None))
                    if not sites or any(
                        expression is None or not (_calls_helper(expression) or _names_in(expression) & derived[caller])
                        for caller, expression in passed
                    ):
                        continue
                if all(
                    source is not None and (_calls_helper(source) or _names_in(source) & derived[name])
                    for source in sources
                ):
                    derived[name].add(local)
                    changed = True
    result: "dict[str, bool]" = {}
    for name, function in functions.items():
        arguments = _psql_file_arguments(function)
        if arguments is None:
            continue
        result[name] = all(
            isinstance(argument, ast.Call) and isinstance(argument.func, ast.Name) and argument.func.id == "str"
            and len(argument.args) == 1 and isinstance(argument.args[0], ast.Name)
            and argument.args[0].id in derived[name]
            for argument in arguments
        )
    return result, set(result)


def test_every_psql_file_launch_takes_its_file_from_a_containment_helper():
    """Each function of `ops` that starts a `psql` subprocess with `-f FILE`
    (there are three today) passes `str(<name>)` whose `<name>` comes from
    `_resolve_contained_migration_path` /
    `_resolve_platform_migration_file` -- directly, or through parameters
    that every call site fills from such a value. A launch is any call on
    `subprocess` in a function whose list or tuple literals carry `-f` or
    `--file`, and every such option in that function must be derived; `ops`
    imports `subprocess` only as `import subprocess`, so no launch hides
    behind another name. Derived from `ops`' own AST; the launching set is
    pinned so the scan cannot go empty. Not seen: an argv assembled without
    a literal `-f` / `--file` element, and a dynamic import."""
    assert _subprocess_import_forms() == ["import subprocess"]
    provenance, launchers = _psql_file_launchers_and_their_provenance()
    assert launchers == _EXPECTED_PSQL_FILE_LAUNCHERS
    assert provenance == {name: True for name in _EXPECTED_PSQL_FILE_LAUNCHERS}
