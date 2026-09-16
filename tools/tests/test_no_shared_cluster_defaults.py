"""tools/tests/test_no_shared_cluster_defaults.py -- re-check that no
tracked .py silently falls back to a shared local PostgreSQL cluster
(work order docs/work-orders/WORK_ORDER_R44_TEST_PG_ISOLATION_V1.md §4.2
(d), design docs/design/TEST_POSTGRES_ISOLATION_V0_1.md v0.2 D-4, §2 目標
1・5).

WP-3 (a) deleted the shared-cluster default `ADMIN_DSN_DEFAULT =
"host=/tmp port=5432 dbname=postgres"` from the 23 tracked .py files that
used to carry it, and made every reader of `ADMIN_DSN_ENV` raise when the
environment variable is unset or empty. This file is the re-introduction
guard (D-4's own "既定値のリテラルが再び入らないことの検査"), in two
independent parts:

(d-1) Body inspection (R-2, the most important addition here): a bare
"no literal, no name" scan would stay green even if a future edit wrote
`os.environ.get(ADMIN_DSN_ENV, "")` -- `psycopg.connect("")` still falls
back to the shared cluster via libpq's own defaults, silently, past every
other check in this repository. `test_admin_dsn_env_definitions_are_
pinned_to_23_files` and `test_every_admin_dsn_reader_raises_when_the_
environment_variable_is_unset` read the AST of every module-level
`ADMIN_DSN_ENV` definition's own reader function(s) directly, not a
string search (§1.7 の 52 -- a check must read the property a function
actually depends on).

(d-2)/(d-3) Literal scan: three literal shapes that reach a shared
PostgreSQL cluster by accident (`host=/tmp` -- W44-3-8: any port, not
only `5432`, except the repository's own established "port=1" deliberate-
unreachable-value convention, R-18; a `postgresql://` URL with an empty/
`localhost`/`127.0.0.1` host; a conninfo string with `dbname=` but no
`host=` key and no URL host, which reaches the shared cluster through
libpq's own defaults) plus the bare name `ADMIN_DSN_DEFAULT` being
redefined at module level (R-13), scanned across every git-tracked `*.py`
file with a reasoned, count-pinned allowlist (R-3/R-9).

(d-5) 限界: this is a static, AST-level scan over string constants. Every
constant's own literal text is checked for the two self-contained
signatures (`host=/tmp`, a loose `postgresql://`), including an
f-string's own implicit-concatenation fragments -- an adjacent plain
literal next to an f-string is one `JoinedStr` in Python's own grammar,
and skipping every fragment inside it would have missed a real DSN
literal reintroduced into one such message (the WP-3 mutation for
completion condition 1 targets exactly this shape). The third signature
(`dbname=` present, no `host=` anywhere) is NOT self-contained -- reading
it off one fragment alone produced a false positive against legitimate
code that assembles a DSN across SEVERAL f-string pieces (a real `host=`
variable in one piece, a `dbname=...` literal in the next, e.g.
tools/testpg/dsa_testpg.py's own `Cluster.env()`) -- so it is only ever
checked against a complete, non-fragment constant. String concatenation
built through anything other than adjacent literals (e.g. `+`), and
libpq's out-of-order key spelling (`port=5432 host=/tmp`), still close
over this static walk. The primary guarantee against a re-introduced
default is (d-1) -- every one of the 23 readers raising on empty -- not
this scan, which is secondary (D-4's "再導入されない検査" is not read
here as an all-quantified claim).

(d-6) 範囲と前提: the scan covers git-tracked `*.py` files only. `.md`
prose and `MitateDB-api/migrations/0001_bootstrap_platform.sql` (a
migration file, its own comments are checksum-pinned history) are out of
scope by design (design §5 「触らないもの」). This file itself requires
no PostgreSQL connection -- like every other file under `tools/tests`, it
sits below `tools/tests/pytest.ini`'s own root, which keeps the
repository-root `conftest.py` (and its throwaway-cluster startup) from
ever being imported here (design D-1, WP-1 §2.3).

Run directly:
    ./.venv/bin/python -m pytest tools/tests/test_no_shared_cluster_defaults.py -q
"""
from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]

# (d-4) allowlist: reasoned, count-pinned exceptions to the literal scan.
# `None` marks the one self-referential entry (this file's own scanning
# literals) whose count is deliberately NOT pinned (a self-referential
# expected count would defeat itself -- supervisor ruling 2026-09-16).
_ALLOWLIST: dict[str, int | None] = {
    # docstring prose describing the shared cluster this repository still
    # reads for local development outside pytest -- not a connection
    # default (design §4.2 (d-4) table).
    "tools/dev/gate.py": 2,
    "tools/testpg/dsa_testpg.py": 1,
    # WP-1's own "a connection that writes no host reaches the run's own
    # cluster" proof (design §3.1: relies on `PGHOST`, never on a literal
    # default) -- two independent embedded scripts, `_SETTINGS_SCRIPT` and
    # `_WRONG_PASSWORD_SCRIPT`.
    "conformance-tests/test_testpg_cluster.py": 2,
    # design §3.1's own "current is: does not connect" placeholder --
    # `PostgresControlCredentialStore` construction-argument tests that
    # never reach the network (R-9 の 3).
    "MitateDB-api/tests/test_control_credentials.py": 2,
    "tools/tests/test_no_shared_cluster_defaults.py": None,
}

_ADMIN_DSN_DEFAULT_DEF_RE = re.compile(r"^ADMIN_DSN_DEFAULT\s*[:=]", re.MULTILINE)

# host=/tmp, any port -- except this repository's own established
# deliberate-unreachable-value convention, exactly `port=1` (R-18's seven
# pre-existing files, and WP-3 (b) 3's three new MitateDB-api/tests/
# test_postgres.py replacements): those are not a shared-cluster risk,
# they are constructed specifically NOT to connect.
_HOST_TMP_RE = re.compile(r"host=/tmp(?!\s+port=1\b)")
_LOOSE_URL_RE = re.compile(r"postgresql://(?:[^@/\s'\"]*@)?(|localhost|127\.0\.0\.1)(?::\d+)?/")
_DBNAME_RE = re.compile(r"(?:^|[\s'\"])dbname=[^\s'\"]")
_HOST_KEY_RE = re.compile(r"(?:^|[\s'\"])host=")


def _tracked_py_files() -> list[Path]:
    """Every git-tracked `*.py` file, repo-wide (design (d-6): not a fixed
    directory list). NUL-separated (`-z`) so a path is never split on
    embedded whitespace -- same technique as tools/check_doc_refs.py's own
    `iter_tracked_markdown_files`."""
    proc = subprocess.run(
        ["git", "ls-files", "-z", "--", "*.py"],
        cwd=_REPO_ROOT,
        capture_output=True,
        timeout=30,
    )
    if proc.returncode != 0:
        pytest.fail(f"git ls-files failed: {proc.stderr.decode('utf-8', errors='replace')}")
    names = proc.stdout.decode("utf-8", errors="strict").split("\0")
    return sorted(_REPO_ROOT / name for name in names if name)


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _defines_admin_dsn_env_at_module_level(tree: ast.Module) -> bool:
    """True when `ADMIN_DSN_ENV` is assigned at module top level (not
    inside a class or function) -- completion condition 5."""
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "ADMIN_DSN_ENV":
                    return True
    return False


def _direct_body_nodes(func: ast.AST):
    """Yields every node inside `func`, never descending into a NESTED
    function/lambda definition -- so a helper reading `ADMIN_DSN_ENV` is
    never misattributed to an unrelated enclosing function."""
    stack = list(ast.iter_child_nodes(func))
    while stack:
        node = stack.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue
        yield node
        stack.extend(ast.iter_child_nodes(node))


def _reads_admin_dsn_env(func: ast.FunctionDef) -> bool:
    """True for the function that actually FETCHES `ADMIN_DSN_ENV` from
    the environment -- named `_admin_dsn`/`admin_dsn` in every one of the
    23 files (work order §4.2 (a)'s own 3-way reader enumeration) and
    referencing the name in its own body. Narrower than "any function
    mentioning the name" on purpose: several of these files also build a
    `pytest.fail`/exception MESSAGE elsewhere that interpolates
    `{ADMIN_DSN_ENV}` for a human to read (e.g. `_require_admin_
    connection`'s own failure text) -- that is a downstream consumer of
    the already-fetched DSN, not itself a reader with a fall-back-default
    risk to guard, and a name-unscoped scan misattributed the missing
    falsy-check+raise to those functions instead."""
    if func.name not in ("_admin_dsn", "admin_dsn"):
        return False
    return any(
        isinstance(n, ast.Name) and n.id == "ADMIN_DSN_ENV" and isinstance(n.ctx, ast.Load)
        for n in _direct_body_nodes(func)
    )


def _has_falsy_check_and_raise(func: ast.FunctionDef) -> bool:
    """Completion condition 6: an `if not <name>:` (a real falsiness
    check, read via its AST shape -- `ast.UnaryOp`/`ast.Not` -- not a
    string search) whose own body (direct or nested) contains a `raise`."""
    for node in _direct_body_nodes(func):
        if not (isinstance(node, ast.If) and isinstance(node.test, ast.UnaryOp) and isinstance(node.test.op, ast.Not)):
            continue
        if any(isinstance(n, ast.Raise) for n in ast.walk(node)):
            return True
    return False


def _admin_dsn_env_reader_functions(tree: ast.Module) -> list[ast.FunctionDef]:
    return [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and _reads_admin_dsn_env(n)]


class _StringConstantCollector(ast.NodeVisitor):
    """Collects every string constant, tagging each as a `fragment` (one
    piece of an f-string's own implicit-concatenation sequence, e.g. a
    plain literal adjacent to an f-string -- Python's grammar merges the
    WHOLE adjacent sequence into one `JoinedStr`, even the plain pieces)
    or not. `host=/tmp`/`postgresql://` (categories 1/2) are self-
    contained signatures -- true wherever they appear, fragment or not,
    since no sibling fragment can make `host=/tmp` not be `host=/tmp`.
    The `dbname=`-without-`host=` shape (category 3) is NOT self-
    contained -- reading it off one fragment alone produced a false
    positive on code that builds a real, non-default DSN across several
    f-string pieces (`host=` from a real variable in one piece, a
    `dbname=...` literal in the NEXT, so the second piece alone looks
    host-less even though the assembled string is not). Category 3 is
    therefore only ever checked against a non-fragment constant."""

    def __init__(self) -> None:
        self.found: list[tuple[ast.Constant, bool]] = []

    def visit_JoinedStr(self, node: ast.JoinedStr) -> None:  # noqa: N802 (ast visitor naming)
        for value in node.values:
            if isinstance(value, ast.FormattedValue):
                self.visit(value.value)
            elif isinstance(value, ast.Constant) and isinstance(value.value, str):
                self.found.append((value, True))

    def visit_Constant(self, node: ast.Constant) -> None:  # noqa: N802 (ast visitor naming)
        if isinstance(node.value, str):
            self.found.append((node, False))


def _string_constants(tree: ast.Module) -> list[tuple[ast.Constant, bool]]:
    collector = _StringConstantCollector()
    collector.visit(tree)
    return collector.found


def _classify_literal(value: str, *, is_fragment: bool) -> str | None:
    if _HOST_TMP_RE.search(value):
        return "host_tmp"
    if _LOOSE_URL_RE.search(value):
        return "loose_url"
    if is_fragment:
        return None
    if _DBNAME_RE.search(value) and not _HOST_KEY_RE.search(value) and "://" not in value:
        return "dbname_without_host"
    return None


def _literal_hits_by_file() -> dict[str, list[ast.Constant]]:
    hits: dict[str, list[ast.Constant]] = {}
    for path in _tracked_py_files():
        matches = [n for n, frag in _string_constants(_parse(path)) if _classify_literal(n.value, is_fragment=frag)]
        if matches:
            hits[str(path.relative_to(_REPO_ROOT))] = matches
    return hits


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------


def test_scan_covers_at_least_one_file() -> None:
    """Completion condition 4 (§1.5 の 32, 空振り禁止): the tracked-`.py`
    iteration this whole file depends on must never be silently empty."""
    files = _tracked_py_files()
    assert len(files) >= 1, "git ls-files -- '*.py' returned no files"


def test_admin_dsn_env_definitions_are_pinned_to_23_files() -> None:
    """Completion condition 5 (R-2): exactly 23 tracked .py files define
    `ADMIN_DSN_ENV` at module level (work order §4.2 (a))."""
    files = [p for p in _tracked_py_files() if _defines_admin_dsn_env_at_module_level(_parse(p))]
    assert len(files) == 23, sorted(str(p.relative_to(_REPO_ROOT)) for p in files)


def test_every_admin_dsn_reader_raises_when_the_environment_variable_is_unset() -> None:
    """Completion condition 6 (R-2): every one of the 23 files' own
    `ADMIN_DSN_ENV` reader function(s) has a falsy check + `raise` (AST,
    not string search -- §1.7 の 52)."""
    files = [p for p in _tracked_py_files() if _defines_admin_dsn_env_at_module_level(_parse(p))]
    assert files, "expected at least one ADMIN_DSN_ENV definition to check"

    offenders: list[str] = []
    reader_count = 0
    for path in files:
        tree = _parse(path)
        readers = _admin_dsn_env_reader_functions(tree)
        reader_count += len(readers)
        if not readers or not all(_has_falsy_check_and_raise(fn) for fn in readers):
            offenders.append(str(path.relative_to(_REPO_ROOT)))
    assert reader_count >= 1, "expected at least one ADMIN_DSN_ENV reader function to check"
    assert not offenders, f"ADMIN_DSN_ENV reader(s) without a falsy-check+raise: {offenders}"


def test_no_tracked_py_defines_admin_dsn_default() -> None:
    """Completion condition 2 (R-13): the bare name `ADMIN_DSN_DEFAULT` is
    never DEFINED again (`^ADMIN_DSN_DEFAULT\\s*[:=]`, column 0 -- narrow
    on purpose so the surviving provenance comments that still mention the
    name in prose, e.g. tests/test_audit_query.py's dated removal note,
    never trip this)."""
    files = _tracked_py_files()
    assert len(files) >= 1
    offenders = [
        str(p.relative_to(_REPO_ROOT))
        for p in files
        if _ADMIN_DSN_DEFAULT_DEF_RE.search(p.read_text(encoding="utf-8"))
    ]
    assert not offenders, f"ADMIN_DSN_DEFAULT redefined in: {offenders}"


def test_no_tracked_py_carries_a_shared_cluster_dsn_literal() -> None:
    """Completion conditions 1 and 28: no tracked .py outside the (d-4)
    allowlist carries a literal that would reach a shared PostgreSQL
    cluster by accident."""
    hits = _literal_hits_by_file()
    offenders = {path: len(nodes) for path, nodes in hits.items() if path not in _ALLOWLIST}
    assert not offenders, f"shared-cluster-reaching literal(s) outside the allowlist: {offenders}"


def test_allowlist_entries_still_carry_their_expected_counts() -> None:
    """Completion condition 3 (R-3): every count-pinned allowlist entry
    still carries exactly its expected number of matches -- catches a
    silently-thinned allowlist item (e.g. one of gate.py's own two
    docstring mentions removed) that a bare "the file is still in the
    allowlist" check would miss."""
    pinned = {path: count for path, count in _ALLOWLIST.items() if count is not None}
    assert pinned, "expected at least one count-pinned allowlist entry"

    hits = _literal_hits_by_file()
    mismatches = {
        path: (expected, len(hits.get(path, [])))
        for path, expected in pinned.items()
        if len(hits.get(path, [])) != expected
    }
    assert not mismatches, f"allowlist entries with a stale expected count (expected, actual): {mismatches}"
