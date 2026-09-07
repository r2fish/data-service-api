"""WP-2e rework (`{scratchpad}/audit-wp2e.md` D-1 = (A), ruling
`{scratchpad}/rulings-r3-r7-flip.md` L-1, closure-audit addendum 2 M-1/M-2):
an AST scan -- not `grep`, which the audit found misses sites (`第 15 次
§5`) -- asserting that EVERY choke-point / request-shape `fail("VALIDATION_
FAILED"|"IDENTIFIER_INVALID"|"CAPABILITY_UNSUPPORTED", ...)` call site in
the data-plane request path (`structured.py`/`service.py`/`limits.py`/
`http.py`/`postgres.py` -- the audit's own 76-site enumeration spans
exactly these files) carries a non-empty `details=` keyword built through
`errors.violation()` (D-3 (4)'s 4-key vocabulary), that call sites for
`violated_declaration in {"field_type", "nullable", "enum"}` respect the
TYPE-PAIR sub-rule (`field_type`/`nullable` require BOTH `declared_type`
and `observed_type`; `enum` requires `declared_type` and MUST NOT carry
`observed_type` -- M-2, not merely "some details present"), and that the
ONE legitimately exempt category (`postgres.py`'s backend-layer defence-
in-depth, `errors.details_vocabulary.layer_rule`) is confined to denials
that TRANSLATE a storage-layer rejection (a real backend has no in-memory
sibling denial to delegate to -- M-1) and is excluded only through an
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

#: Closure-audit M-1 (`{scratchpad}/audit-wp2e-2.md` R-2): the backend-
#: layer allowlist is confined to denials that TRANSLATE a rejection the
#: storage engine itself raised (a `psycopg` exception this handler
#: cannot attribute to one field) -- NOT to a re-implementation of a
#: shape/capability check the in-memory cell (or the shared
#: `structured.py` boundary both cells call) already performs. Every one
#: of the 5 sites the closure audit found (`postgres.py:1395/1836/1838/
#: 1842/1989`, plus the unreachable-in-practice operator fallback at
#: `2021`) was exactly that kind of re-implementation, not a storage
#: translation -- so all 6 were given the same 4-key `details=violation
#: (...)` their `structured.py` siblings already carry (or, for the two
#: unreachable defensive fallbacks with no request-internal index
#: available that deep, a best-effort non-indexed `field`) and removed
#: from this allowlist. The ONE entry that remains, `1602`
#: (`_fail_client_value`'s generic `psycopg.errors.DataError` catch), has
#: no in-memory sibling at all -- `test_backend_layer_allowlist_entries_
#: have_no_in_memory_sibling_denial` below pins that.
_BACKEND_LAYER_ALLOWLIST: frozenset[tuple[str, int]] = frozenset({
    ("postgres.py", 1621),  # _fail_client_value: generic psycopg.errors.DataError catch, cannot attribute to one field -- a storage-rejection translation with no in-memory equivalent (this WP's own I-6 pin target)
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


def _all_fail_messages(path: Path) -> set[str]:
    """The literal (string-constant, second positional argument) message
    of EVERY `fail(...)` call in `path`, any code -- used by M-1's "no
    in-memory sibling" check, which must compare a `postgres.py` denial's
    wording against the FULL in-memory vocabulary, not merely the 3
    `errors.details_vocabulary` codes (an allowlisted backend denial could
    in principle duplicate a `NOT_FOUND`/`CONFLICT` message just as much
    as a `VALIDATION_FAILED` one)."""
    tree = ast.parse(path.read_text(), filename=str(path))
    messages: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.id if isinstance(func, ast.Name) else (func.attr if isinstance(func, ast.Attribute) else None)
        if name != "fail" or len(node.args) < 2:
            continue
        second = node.args[1]
        if isinstance(second, ast.Constant) and isinstance(second.value, str):
            messages.add(second.value)
    return messages


def _fail_message_at(path: Path, lineno: int) -> str:
    """The literal message of the `fail(...)` call starting at `lineno` in
    `path` -- used to look up an allowlisted `postgres.py` site's own
    wording (see `test_allowlist_entries_match_real_bare_call_sites` for
    the analogous "does the allowlist still describe real code" check this
    mirrors)."""
    tree = ast.parse(path.read_text(), filename=str(path))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or node.lineno != lineno:
            continue
        func = node.func
        name = func.id if isinstance(func, ast.Name) else (func.attr if isinstance(func, ast.Attribute) else None)
        if name != "fail" or len(node.args) < 2:
            continue
        second = node.args[1]
        if isinstance(second, ast.Constant) and isinstance(second.value, str):
            return second.value
    raise AssertionError(f"no fail() call with a literal message found at {path}:{lineno}")


#: M-2 (`{scratchpad}/audit-wp2e-2.md` R-3/R-4): D-3 (4)'s TYPE-PAIR rule,
#: for the 2 `violated_declaration` values R-3's own "やること" names --
#: `field_type`/`nullable` require BOTH `declared_type` and `observed_
#: type`; `enum` requires `declared_type` and must NOT carry `observed_
#: type` (contract `errors.details_vocabulary.VALIDATION_FAILED.declared_
#: type`: required where `violated_declaration` is `field_type` OR
#: `nullable`; `.observed_type`: required where `field_type` OR
#: `nullable`, and explicitly NOT applicable to `enum`). `constraint_
#: declaration`/`request_schema` are deliberately NOT pinned here: a
#: `constraint_declaration` site can legitimately have no `declared_type`
#: at all when the offending declaration names a field that does not
#: exist (no type to report -- ruling m-1, `structured.py`'s existing
#: `field_constraints/<name>` site), and whether a `request_schema` site
#: is "a type violation" (needing the pair) or a shape/unknown-key
#: violation (not needing it) is not something this AST scan can decide
#: statically -- R-3's own "やること" only names `field_type`/`nullable`/
#: `enum` as the sub-rules to check here.
_TYPE_PAIR_REQUIRED: dict[str, frozenset[str]] = {
    "field_type": frozenset({"declared_type", "observed_type"}),
    "nullable": frozenset({"declared_type", "observed_type"}),
    "enum": frozenset({"declared_type"}),
}
_TYPE_PAIR_FORBIDDEN: dict[str, frozenset[str]] = {
    "field_type": frozenset(),
    "nullable": frozenset(),
    "enum": frozenset({"observed_type"}),
}


def _violated_declaration_and_present_keys(value: ast.expr) -> tuple[str | None, frozenset[str]]:
    """For a `details=` expression that already carries `violated_
    declaration` (per `_has_violated_declaration`): its literal
    `violated_declaration` value (or `None` if not a static string
    constant -- excluded from the type-pair check below rather than
    guessed at), and the set of the OTHER 3 vocabulary keys (`field`/
    `declared_type`/`observed_type`) actually present with a non-`None`
    value -- `errors.violation()` itself omits a key whose value is
    `None` (its own docstring: "omitting any key whose value is None
    rather than carrying it as an explicit null"), so a `declared_type=
    None` keyword argument is the SAME as the key being absent, both for
    the real helper and for this static check."""
    if isinstance(value, ast.Call):
        func = value.func
        name = func.id if isinstance(func, ast.Name) else (func.attr if isinstance(func, ast.Attribute) else None)
        if name != "violation":
            return None, frozenset()
        vd: str | None = None
        if value.args and isinstance(value.args[0], ast.Constant) and isinstance(value.args[0].value, str):
            vd = value.args[0].value
        present = set()
        for kw in value.keywords:
            if kw.arg in ("field", "declared_type", "observed_type") and not (isinstance(kw.value, ast.Constant) and kw.value.value is None):
                present.add(kw.arg)
            if kw.arg == "violated_declaration" and vd is None and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                vd = kw.value.value
        return vd, frozenset(present)
    if isinstance(value, ast.Dict):
        vd = None
        present = set()
        for key, val in zip(value.keys, value.values):
            if not (isinstance(key, ast.Constant) and isinstance(key.value, str)):
                continue
            if key.value == "violated_declaration" and isinstance(val, ast.Constant) and isinstance(val.value, str):
                vd = val.value
            elif key.value in ("field", "declared_type", "observed_type") and not (isinstance(val, ast.Constant) and val.value is None):
                present.add(key.value)
        return vd, frozenset(present)
    return None, frozenset()


def _type_pair_call_sites(path: Path) -> list[tuple[int, str, str, frozenset[str]]]:
    """Every vocabulary-code `fail(...)` call site in `path` whose
    `details=` carries a statically-known `violated_declaration`, as
    `(lineno, code, violated_declaration, present_type_pair_keys)`."""
    tree = ast.parse(path.read_text(), filename=str(path))
    sites: list[tuple[int, str, str, frozenset[str]]] = []
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
        if details_kw is None:
            continue
        vd, present = _violated_declaration_and_present_keys(details_kw.value)
        if vd is None:
            continue
        sites.append((node.lineno, first.value, vd, present))
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
    diff here, not just folded into an unremarkable total. Closure-audit
    R-8/M-8: re-pinned to the measured post-merge count (`limits.py`'s
    4 inline budget denials were folded into 1 `_budget_denied` helper by
    the R-5/R-6 pair-closing merge, `violated_declaration` preserved)."""
    counts = {module: len(_fail_call_sites(SRC / module)) for module in ("structured.py", "service.py", "limits.py", "http.py")}
    assert counts == {"structured.py": 93, "service.py": 10, "limits.py": 5, "http.py": 8}, counts
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


def test_backend_layer_allowlist_entries_have_no_in_memory_sibling_denial():
    """M-1 (`{scratchpad}/audit-wp2e-2.md` R-2, ruling M-1): the allowlist
    is confined to denials that TRANSLATE a storage-layer rejection -- a
    denial `ApplicationCell` (the in-memory sibling) also raises, in the
    same words, is by definition NOT a storage translation (the in-memory
    backend has no storage to translate a rejection FROM), so it cannot
    legitimately sit on this allowlist; it belongs at the choke-point/
    request-shape layer with the same 4-key `details` its sibling already
    carries (exactly what R-2 did for the 5 former allowlist entries this
    left behind). This scans `structured.py`'s FULL fail-message
    vocabulary (any code, not just the 3 in-scope ones -- see `_all_fail_
    messages`), so a match against a `NOT_FOUND`/`CONFLICT` message would
    be caught too."""
    in_memory_messages = _all_fail_messages(SRC / "structured.py")
    shared = []
    for module, lineno in sorted(_BACKEND_LAYER_ALLOWLIST):
        message = _fail_message_at(SRC / module, lineno)
        if message in in_memory_messages:
            shared.append(f"{module}:{lineno} {message!r}")
    assert shared == [], f"allowlisted backend denial(s) that duplicate an in-memory-side denial (not a storage translation -- must move off the allowlist): {shared}"


def test_type_pair_rule_is_respected_at_every_violated_declaration_site():
    """M-2 (`{scratchpad}/audit-wp2e-2.md` R-3/R-4): D-3 (4)'s type-pair
    sub-rule, checked per call site from the `violation(...)`/dict-literal
    ARGUMENTS themselves (never just "some details is present" --
    `_has_violated_declaration`'s own 0-count check above is exactly what
    let `structured.py:1508` (`nullable` with no `declared_type`) slip
    through undetected before R-4). `field_type`/`nullable` sites must
    carry BOTH `declared_type` and `observed_type`; `enum` sites must
    carry `declared_type` and must NOT carry `observed_type`."""
    violations: list[str] = []
    for module in SCANNED_MODULES:
        for lineno, code, vd, present in _type_pair_call_sites(SRC / module):
            required = _TYPE_PAIR_REQUIRED.get(vd)
            if required is None:
                continue
            forbidden = _TYPE_PAIR_FORBIDDEN[vd]
            missing = required - present
            unexpected = forbidden & present
            if missing:
                violations.append(f"{module}:{lineno} {code} violated_declaration={vd!r} missing required key(s) {sorted(missing)}")
            if unexpected:
                violations.append(f"{module}:{lineno} {code} violated_declaration={vd!r} carries forbidden key(s) {sorted(unexpected)}")
    assert violations == [], f"type-pair rule (D-3 (4)) not respected: {violations}"
