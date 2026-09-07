"""WP-2e rework (`{scratchpad}/audit-wp2e.md` D-1 = (A), ruling
`{scratchpad}/rulings-r3-r7-flip.md` L-1): an AST scan -- not `grep`,
which the audit found misses sites (`第 15 次 §5`) -- asserting that
EVERY choke-point / request-shape `fail("VALIDATION_FAILED"|
"IDENTIFIER_INVALID"|"CAPABILITY_UNSUPPORTED", ...)` call site in the
data-plane request path (`structured.py`/`service.py`/`limits.py`/
`http.py` -- the audit's own 76-site enumeration spans exactly these 4
files) carries a non-empty `details=` keyword (D-3 (4)'s 4-key
vocabulary, built through `errors.violation()`), and that the ONE
legitimately exempt file (`postgres.py`, backend-layer defence-in-depth,
`errors.details_vocabulary.layer_rule`) is excluded only through an
allowlist this test itself verifies against real, current code -- never a
blanket file-name skip nobody checks (L-1: "allowlist は実コードとして
一致することまで assert")."""
from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "r2db_api"

#: Contract 1.7.0 `errors.details_vocabulary` applies to the DATA-plane
#: query/mutate/schema request surface (D-1/D-3) -- these are the full
#: choke-point / request-shape layer for that surface. `control_plane.py`/
#: `auth.py`/`credential_store.py`/`ops.py` also call `fail()` with these
#: 3 codes, but for the CONTROL-plane credential/application-management
#: surface, which `errors.details_vocabulary` (D-1/D-3, scoped to query/
#: mutate/schema requests) never covers -- out of this scan's scope by the
#: same boundary the audit's own 76-site count already drew, not an
#: omission. `postgres.py` is the backend storage layer UNDERNEATH the
#: data-plane surface (`layer_rule`'s defence-in-depth exemption) --
#: included in the scan below via the allowlist, never silently skipped.
SCANNED_MODULES = ("structured.py", "service.py", "limits.py", "http.py", "postgres.py")

_VOCAB_CODES = {"VALIDATION_FAILED", "IDENTIFIER_INVALID", "CAPABILITY_UNSUPPORTED"}

#: Backend-layer defence-in-depth allowlist (`errors.details_vocabulary.
#: layer_rule`) -- entries are (module, lineno) pairs, `postgres.py` only
#: (`test_backend_layer_allowlist_is_confined_to_postgres_py` below pins
#: that). Every entry here must correspond to a REAL, currently-bare (no
#: `details`, or an empty `details={}`) `fail()` call for one of the 3
#: vocabulary codes in `postgres.py` right now
#: (`test_allowlist_entries_match_real_bare_call_sites` below, checked
#: BOTH directions) -- a stale entry (the code moved, was fixed, or was
#: removed) fails that test, so this list can never silently drift from
#: the code it claims to describe, and a NEW bare site anywhere in the
#: scanned modules (`postgres.py` included) is caught by that same
#: bidirectional check even before the "0 count" test below would notice.
_BACKEND_LAYER_ALLOWLIST: frozenset[tuple[str, int]] = frozenset({
    ("postgres.py", 1395),  # "At least one mutation is required." -- PostgresCell.transact's own generic shape guard
    ("postgres.py", 1602),  # _fail_client_value: generic psycopg.errors.DataError catch, cannot attribute to one field (this WP's own I-6 pin target)
    ("postgres.py", 1836),  # "unique_key is required when an entity declares more than one uniqueness key."
    ("postgres.py", 1838),  # "Upsert does not accept a filter; ..."
    ("postgres.py", 1842),  # "Upsert values must include every uniqueness key field."
    ("postgres.py", 1989),  # "Filter value is incompatible with the selected operator."
    ("postgres.py", 2021),  # "Unsupported filter operator." (bare {"field": ...}, not the 4-key form)
})


def _has_violated_declaration(value: ast.expr) -> bool:
    """D-3 (4)'s 4-key rule turns on ONE required key, `violated_
    declaration` -- present (a) via `errors.violation(...)` (that
    function's own first parameter, always supplied whenever it is
    called with any positional/keyword argument at all -- `violation()`
    with zero arguments is not a real call site anywhere in this tree),
    or (b) via a dict literal that spells the key out directly. A dict
    literal carrying some OTHER key (the pre-rework partial forms this
    WP replaces, e.g. bare `{"field": ...}`) does NOT count -- checking
    only "non-empty" would let exactly that pre-rework partial form slip
    through undetected, defeating the point of this scan."""
    if isinstance(value, ast.Call):
        func = value.func
        name = func.id if isinstance(func, ast.Name) else (func.attr if isinstance(func, ast.Attribute) else None)
        return name == "violation" and bool(value.args or value.keywords)
    if isinstance(value, ast.Dict):
        return any(isinstance(key, ast.Constant) and key.value == "violated_declaration" for key in value.keys if key is not None)
    return False


def _fail_call_sites(path: Path) -> list[tuple[int, str, bool]]:
    """Every `fail(<CODE>, ...)` call in `path` for one of the 3
    vocabulary codes, as `(lineno, code, has_violated_declaration)`.
    AST-based (never regex/`grep`) so a multi-line call, an f-string
    message, or a code constant built via string concatenation is still
    found -- the audit's own explicit reason for rejecting a `grep`-based
    count."""
    tree = ast.parse(path.read_text(), filename=str(path))
    sites: list[tuple[int, str, bool]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.id if isinstance(func, ast.Name) else (func.attr if isinstance(func, ast.Attribute) else None)
        if name != "fail" or not node.args:
            continue
        first = node.args[0]
        if not (isinstance(first, ast.Constant) and isinstance(first.value, str) and first.value in _VOCAB_CODES):
            continue
        details_kw = next((kw for kw in node.keywords if kw.arg == "details"), None)
        has_details = details_kw is not None and _has_violated_declaration(details_kw.value)
        sites.append((node.lineno, first.value, has_details))
    return sites


def test_every_choke_point_denial_carries_details_ast_full_count():
    """L-1's own "0 件" assert, AST full-count: every in-scope site (i.e.
    every site NOT on the verified backend-layer allowlist, across all of
    `SCANNED_MODULES`) must carry non-empty `details`."""
    violations: list[str] = []
    for module in SCANNED_MODULES:
        for lineno, code, has_details in _fail_call_sites(SRC / module):
            if (module, lineno) in _BACKEND_LAYER_ALLOWLIST:
                continue
            if not has_details:
                violations.append(f"{module}:{lineno} {code}")
    assert violations == [], f"choke-point/request-shape denial(s) with no (or empty) details: {violations}"


def test_ast_full_count_matches_the_audit_site_count():
    """Non-空振り: the scan actually visits at least the 76 sites D-1
    counted (plus every VALIDATION_FAILED/IDENTIFIER_INVALID/
    CAPABILITY_UNSUPPORTED site in these 4 files that already carried
    `violated_declaration` before this rework -- the audit's own 76 was
    only the GAP count, not the total) -- a scanner that silently matched
    0 calls (e.g. because `fail` were imported under an alias, or the
    wrong AST node type were checked) would make the test above vacuously
    green. Per-module counts pinned exactly (not just a `>= 76` floor) so
    a future site quietly added to the wrong module is still visible as a
    diff here, not just folded into an unremarkable total."""
    counts = {module: len(_fail_call_sites(SRC / module)) for module in ("structured.py", "service.py", "limits.py", "http.py")}
    assert counts == {"structured.py": 92, "service.py": 10, "limits.py": 9, "http.py": 8}, counts
    assert sum(counts.values()) >= 76, counts


def test_allowlist_entries_match_real_bare_call_sites():
    """The allowlist is not a set-and-forget list: every entry must point
    at a REAL, currently-bare `fail()` call for one of the 3 vocabulary
    codes right now (checked in BOTH directions) -- if the code moves, is
    fixed, or is removed, THIS test (not just the "0 count" test above)
    goes red, forcing the allowlist to be updated rather than silently
    exempting a line that no longer needs it (or a different one that has
    drifted onto that line number). This is also what catches a brand new
    bare site added anywhere in `SCANNED_MODULES`, including a new one in
    `postgres.py` that was never added to the allowlist."""
    real_bare_sites = {
        (module, lineno)
        for module in SCANNED_MODULES
        for lineno, code, has_details in _fail_call_sites(SRC / module)
        if not has_details
    }
    missing_from_reality = sorted(_BACKEND_LAYER_ALLOWLIST - real_bare_sites)
    missing_from_allowlist = sorted(real_bare_sites - _BACKEND_LAYER_ALLOWLIST)
    assert missing_from_reality == [], f"allowlist entries with no matching real bare call site: {missing_from_reality}"
    assert missing_from_allowlist == [], f"real bare call site(s) not on the allowlist: {missing_from_allowlist}"


def test_backend_layer_allowlist_is_confined_to_postgres_py():
    """`errors.details_vocabulary.layer_rule`'s exemption is for backend-
    layer defence-in-depth ONLY -- the allowlist must never grow into one
    of the 4 choke-point / request-shape files themselves (that would
    silently reintroduce the exact D-1 gap this rework closed)."""
    assert all(module == "postgres.py" for module, _ in _BACKEND_LAYER_ALLOWLIST)
