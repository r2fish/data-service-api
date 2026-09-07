"""WP-3e rework T1 (`{scratchpad}/rulings-r3-r7-flip.md` addendum L-1,
addendum 2 M-1/M-2 -- verbatim rulings; mirrors r2db-api's own
`tests/test_l1_details_vocabulary_ast_scan.py`, `{scratchpad}/wp3e-
sites.md`'s own 147-site enumeration): an AST scan -- not `grep`, which
misses multi-line calls -- asserting that EVERY choke-point / request-
shape `ValidationError(...)`/`CapabilityError(...)` call site in the
data-plane request path (`cell.py`/`http.py`/`field_types.py`/
`identifiers.py`/`backend_postgres.py`/`backend_sqlite.py`) carries a
non-empty `details=` keyword built through `errors.violation()` (or the
equivalent literal dict, for the few pre-existing sites that still spell
it out directly) -- D-3 (4)'s 4-key vocabulary -- that call sites for
`violated_declaration in {"field_type", "nullable", "enum"}` respect the
TYPE-PAIR sub-rule (M-2: `field_type`/`nullable` require BOTH `declared_
type` and `observed_type`; `enum` requires `declared_type` and MUST NOT
carry `observed_type`), and that the ONLY legitimately exempt category
(`backend_postgres.py`/`backend_sqlite.py`'s own backend-layer defence-
in-depth, `errors.details_vocabulary.layer_rule`) is confined to denials
that TRANSLATE a storage-layer rejection with no in-memory sibling (M-1:
a check the in-memory `ApplicationCell` also performs, in the same
words, is NOT defence-in-depth -- it is the choke-point layer's own
Postgres/SQLite realization of that same check, and must carry the same
4-key `details` its in-memory sibling does) -- confined through an
allowlist this test itself verifies against real, current code, never a
blanket file-name skip nobody checks.

`config.py`/`control_plane.py` (also named in the WP-3e T1 work order as
files to inspect for a data-plane choke point) are DELIBERATELY not
members of `SCANNED_MODULES` below -- see each module's own boundary
comment for why every `ValidationError`/`CapabilityError` site AST-
visited while drafting this scan turned out to belong to a surface
`errors.details_vocabulary` never covers (deployment-time `FoundationConfig`
construction, or the control-plane credential/application-management
API), except `config.py`'s own ONE genuine choke-point site
(`_budget_denied`, D-6's `request_budget` gate), which
`test_config_budget_denial_helper_carries_the_4_key_form` below verifies
directly rather than folding into the whole-file scan.
"""
from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "mitatedb_api"

#: Contract 1.7.0 `errors.details_vocabulary` applies to the DATA-plane
#: query/mutate/schema request surface (D-1/D-3) -- these 6 files are the
#: full choke-point / request-shape layer for that surface plus its two
#: backend realizations. `config.py`/`control_plane.py`/`audit_query.py`/
#: `ops.py`/`control_auth.py`/`control_http.py`/`control_credential_
#: store_postgres.py` also raise `ValidationError`/`CapabilityError` (see
#: `{scratchpad}/wp3e-sites.md`'s own 147-site enumeration), but for the
#: CONTROL-plane credential/application-management surface or deployment-
#: time configuration -- out of this scan's scope by the same boundary
#: r2db-api's own analogous scan draws around `control_plane.py`/
#: `auth.py`/`credential_store.py`/`ops.py`, not an omission (every site
#: in those files was read while drafting this scan; none of them is a
#: request-shape check for a query/mutate/schema request).
SCANNED_MODULES = ("cell.py", "http.py", "field_types.py", "identifiers.py", "backend_postgres.py", "backend_sqlite.py")

_VOCAB_CLASSES = {"ValidationError", "CapabilityError"}

#: M-1 (`{scratchpad}/rulings-r3-r7-flip.md` addendum 2): the backend-
#: layer allowlist is confined to denials that TRANSLATE a rejection the
#: storage engine (or the physical value-domain encoding step) itself
#: raised -- NOT to a re-implementation of a shape/capability check the
#: in-memory `ApplicationCell` (or a module it calls into, `field_types.
#: py`/`identifiers.py`) already performs. Two categories in each
#: backend module ARE exactly that kind of re-implementation and were
#: moved OFF this allowlist onto the 4-key form instead (this WP's own
#: fix): the shared `check_reserved` identifier choke point (`identifiers.
#: py`'s own module docstring names this as the backend-specific SECOND
#: HALF of `cell.ApplicationCell._identifier`, always applied together
#: with `identifiers.validate_identifier` -- not a redundant backstop for
#: a check the cell layer already performs itself, since this backend IS
#: the one place that reserved-name knowledge lives), and the `invalid
#: order direction` `KeyError` backstop in each backend's own ORDER BY
#: composition (the exact literal denial `cell.ApplicationCell._bind_
#: order_by` already carries -- `test_backend_layer_allowlist_entries_
#: have_no_in_memory_sibling_denial` below is what caught this pair, and
#: is what would catch a future one). What remains allowlisted is
#: genuinely storage/physical-encoding-only: driver-exception translation
#: (`"storage backend rejected the request"`, every `except psycopg.
#: Error`/`except sqlite3.DatabaseError` final backstop), PostgreSQL text-
#: encoding domain checks with no in-memory equivalent at all (embedded
#: NUL / lone UTF-16 surrogate -- `cell.ApplicationCell._normalize_value`
#: only checks PYTHON type, never byte-level text encodability), and the
#: physical value-domain re-check in `_check_domain`/`backend_sqlite.
#: encode_value` (a defensively worded, differently-phrased echo of
#: `field_types.check_declared_value`'s own type check -- DIFFERENT
#: literal wording, confirmed by `test_backend_layer_allowlist_entries_
#: have_no_in_memory_sibling_denial` finding no shared message -- plus a
#: genuine storage-only 32/64-bit integer RANGE bound the in-memory side
#: never checks at all).
_BACKEND_LAYER_ALLOWLIST: frozenset[tuple[str, int]] = frozenset({
    ("backend_postgres.py", 257),   # _validate_value_domain: embedded NUL, PostgreSQL text storage only, no in-memory equivalent
    ("backend_postgres.py", 282),   # _validate_value_domain: lone UTF-16 surrogate, encoding-only, no in-memory equivalent
    ("backend_postgres.py", 317),   # _check_domain: text-domain physical isinstance re-check, differently worded from field_types.check_declared_value
    ("backend_postgres.py", 321),   # _check_domain: int-domain physical isinstance re-check, differently worded
    ("backend_postgres.py", 324),   # _check_domain: int32/int64 RANGE bound -- genuine storage-only domain, no in-memory equivalent at all
    ("backend_postgres.py", 328),   # _check_domain: float-domain physical isinstance re-check, differently worded
    ("backend_postgres.py", 539),   # schema_count: except psycopg.Error -- generic driver-exception translation
    ("backend_postgres.py", 596),   # generic driver-exception translation
    ("backend_postgres.py", 645),   # generic driver-exception translation
    ("backend_postgres.py", 672),   # generic driver-exception translation
    ("backend_postgres.py", 729),   # generic driver-exception translation
    ("backend_postgres.py", 781),   # generic driver-exception translation
    ("backend_postgres.py", 806),   # generic driver-exception translation
    ("backend_postgres.py", 968),   # generic driver-exception translation
    ("backend_postgres.py", 985),   # generic driver-exception translation
    ("backend_postgres.py", 1116),  # generic driver-exception translation
    ("backend_postgres.py", 1257),  # generic driver-exception translation
    ("backend_postgres.py", 1343),  # generic driver-exception translation
    ("backend_postgres.py", 1395),  # generic driver-exception translation
    ("backend_postgres.py", 1428),  # generic driver-exception translation
    ("backend_postgres.py", 1454),  # generic driver-exception translation
    ("backend_postgres.py", 1521),  # generic driver-exception translation
    ("backend_postgres.py", 1549),  # generic driver-exception translation
    ("backend_postgres.py", 1590),  # generic driver-exception translation
    ("backend_postgres.py", 1685),  # generic driver-exception translation
    ("backend_postgres.py", 1701),  # generic driver-exception translation
    ("backend_postgres.py", 1713),  # generic driver-exception translation
    ("backend_sqlite.py", 660),     # encode_value: out of range for 64-bit integer storage -- genuine storage-only domain, no in-memory equivalent
    ("backend_sqlite.py", 682),     # encode_value: lone UTF-16 surrogate, encoding-only, no in-memory equivalent
})


def _call_target_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _has_violated_declaration(value: ast.expr) -> bool:
    """D-3 (4)'s 4-key rule turns on ONE required key, `violated_
    declaration` -- present (a) via `errors.violation(...)` (that
    function's own first parameter, always supplied whenever it is
    called with any positional/keyword argument at all), or (b) via a
    dict literal that spells the key out directly (the few pre-existing
    sites, e.g. `cell.py`'s `filters_path`/`field_constraints` branches,
    that still build the dict by hand rather than through the helper). A
    dict literal carrying some OTHER key but not this one does NOT
    count -- checking only "non-empty" would let a pre-rework partial
    form slip through undetected."""
    if isinstance(value, ast.Call):
        name = _call_target_name(value.func)
        return name == "violation" and bool(value.args or value.keywords)
    if isinstance(value, ast.Dict):
        return any(isinstance(key, ast.Constant) and key.value == "violated_declaration" for key in value.keys if key is not None)
    return False


def _fail_call_sites(path: Path) -> list[tuple[int, str, bool]]:
    """Every `ValidationError(...)`/`CapabilityError(...)` call in
    `path`, as `(lineno, class_name, has_violated_declaration)`. AST-
    based (never regex/`grep`) so a multi-line call or an f-string
    message is still found."""
    tree = ast.parse(path.read_text(), filename=str(path))
    sites: list[tuple[int, str, bool]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _call_target_name(node.func)
        if name not in _VOCAB_CLASSES:
            continue
        details_kw = next((kw for kw in node.keywords if kw.arg == "details"), None)
        has_details = details_kw is not None and _has_violated_declaration(details_kw.value)
        sites.append((node.lineno, name, has_details))
    return sites


def _all_denial_messages(path: Path) -> set[str]:
    """The literal (string-constant, first positional argument) message
    of EVERY `ValidationError`/`CapabilityError`/`ConflictError`/
    `ResourceLimitError`/`NotFoundError` raise in `path` -- used by
    M-1's "no in-memory sibling" check, which must compare a backend
    denial's wording against the FULL in-memory vocabulary, not merely
    the 2 classes this scan otherwise tracks (an allowlisted backend
    denial could in principle duplicate a `NotFoundError`/`ConflictError`
    message just as much as a `ValidationError` one). An f-string message
    (`ast.JoinedStr`, e.g. `field_types.check_declared_value`'s own
    interpolated denials) is deliberately NOT reduced to a comparable
    literal here -- it is a DIFFERENT message from any fixed string by
    construction, exactly the "confirmed no shared message" case several
    allowlist entries above rely on."""
    tree = ast.parse(path.read_text(), filename=str(path))
    messages: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        name = _call_target_name(node.func)
        if name not in {"ValidationError", "CapabilityError", "ConflictError", "ResourceLimitError", "NotFoundError", "PreconditionFailedError"}:
            continue
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            messages.add(first.value)
    return messages


def _message_at(path: Path, lineno: int) -> str:
    tree = ast.parse(path.read_text(), filename=str(path))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or node.lineno != lineno or not node.args:
            continue
        name = _call_target_name(node.func)
        if name not in _VOCAB_CLASSES:
            continue
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            return first.value
    raise AssertionError(f"no ValidationError/CapabilityError call with a literal message found at {path}:{lineno}")


#: M-2 (`{scratchpad}/rulings-r3-r7-flip.md` addendum 2): D-3 (4)'s
#: TYPE-PAIR rule -- `field_type`/`nullable` require BOTH `declared_type`
#: and `observed_type`; `enum` requires `declared_type` and must NOT
#: carry `observed_type` (contract `errors.details_vocabulary.
#: VALIDATION_FAILED.declared_type`/`.observed_type`). `constraint_
#: declaration`/`request_schema` are deliberately NOT pinned here: a
#: `constraint_declaration` site can legitimately carry no `declared_
#: type` at all (the offending declaration names a field that does not
#: exist -- ruling m-1), and whether a `request_schema` site needs the
#: pair is not something this scan can decide statically.
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
    declaration`: its literal value (or `None` if not a static string
    constant -- excluded from the type-pair check rather than guessed
    at), and the set of the other 3 vocabulary keys actually present
    with a non-`None` value (`errors.violation()` itself omits a key
    whose value is `None` -- its own docstring -- so a `declared_type=
    None` keyword is the SAME as the key being absent here too)."""
    if isinstance(value, ast.Call):
        name = _call_target_name(value.func)
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
    """Every `ValidationError`/`CapabilityError` call site in `path`
    whose `details=` carries a statically-known `violated_declaration`,
    as `(lineno, class_name, violated_declaration, present_type_pair_keys)`."""
    tree = ast.parse(path.read_text(), filename=str(path))
    sites: list[tuple[int, str, str, frozenset[str]]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _call_target_name(node.func)
        if name not in _VOCAB_CLASSES:
            continue
        details_kw = next((kw for kw in node.keywords if kw.arg == "details"), None)
        if details_kw is None:
            continue
        vd, present = _violated_declaration_and_present_keys(details_kw.value)
        if vd is None:
            continue
        sites.append((node.lineno, name, vd, present))
    return sites


def test_every_choke_point_denial_carries_details_ast_full_count():
    """L-1's own "0 件" assert, AST full-count: every in-scope site
    (i.e. every site NOT on the verified backend-layer allowlist, across
    all of `SCANNED_MODULES`) must carry non-empty `details`."""
    violations: list[str] = []
    for module in SCANNED_MODULES:
        for lineno, cls, has_details in _fail_call_sites(SRC / module):
            if (module, lineno) in _BACKEND_LAYER_ALLOWLIST:
                continue
            if not has_details:
                violations.append(f"{module}:{lineno} {cls}")
    assert violations == [], f"choke-point/request-shape denial(s) with no (or empty) details: {violations}"


def test_ast_full_count_matches_a_non_trivial_floor():
    """Non-空振り: the scan actually visits real call sites in every
    scanned module (a scanner that silently matched 0 calls anywhere,
    e.g. because the wrong AST node type were checked, would make the
    test above vacuously green). Per-module counts pinned exactly (not
    just a floor) so a future site quietly added to the wrong module is
    still visible as a diff here, not folded into an unremarkable total
    -- measured directly against this WP's own post-fix tree."""
    counts = {module: len(_fail_call_sites(SRC / module)) for module in SCANNED_MODULES}
    assert counts == {
        "cell.py": 49,
        "http.py": 26,
        "field_types.py": 4,
        "identifiers.py": 1,
        "backend_postgres.py": 29,
        "backend_sqlite.py": 4,
    }, counts
    assert sum(counts.values()) >= 76, counts


def test_allowlist_entries_match_real_bare_call_sites():
    """The allowlist is not set-and-forget: every entry must point at a
    REAL, currently-bare `ValidationError`/`CapabilityError` call right
    now (checked in BOTH directions) -- if the code moves, is fixed, or
    is removed, THIS test (not just the "0 count" test above) goes red,
    forcing the allowlist to be updated rather than silently exempting a
    line that no longer needs it. This is also what catches a brand new
    bare site added anywhere in `SCANNED_MODULES`, including a new one
    in `backend_postgres.py`/`backend_sqlite.py` that was never added to
    the allowlist."""
    real_bare_sites = {
        (module, lineno)
        for module in SCANNED_MODULES
        for lineno, cls, has_details in _fail_call_sites(SRC / module)
        if not has_details
    }
    missing_from_reality = sorted(_BACKEND_LAYER_ALLOWLIST - real_bare_sites)
    missing_from_allowlist = sorted(real_bare_sites - _BACKEND_LAYER_ALLOWLIST)
    assert missing_from_reality == [], f"allowlist entries with no matching real bare call site: {missing_from_reality}"
    assert missing_from_allowlist == [], f"real bare call site(s) not on the allowlist: {missing_from_allowlist}"


def test_backend_layer_allowlist_is_confined_to_backend_modules():
    """`errors.details_vocabulary.layer_rule`'s exemption is for backend-
    layer defence-in-depth ONLY -- the allowlist must never grow into one
    of the 4 choke-point / request-shape files themselves (that would
    silently reintroduce the exact L-1 gap this rework closed)."""
    assert all(module in ("backend_postgres.py", "backend_sqlite.py") for module, _ in _BACKEND_LAYER_ALLOWLIST)


def test_backend_layer_allowlist_entries_have_no_in_memory_sibling_denial():
    """M-1 (`{scratchpad}/rulings-r3-r7-flip.md` addendum 2): the
    allowlist is confined to denials that TRANSLATE a storage-layer
    rejection -- a denial `cell.py`/`field_types.py`/`http.py`/
    `identifiers.py` (the in-memory choke-point layer) also raises, in
    the same words, is by definition NOT a storage translation, so it
    cannot legitimately sit on this allowlist; it belongs at the choke-
    point/request-shape layer with the same 4-key `details` its sibling
    already carries (exactly what this WP did for `check_reserved`/
    `invalid order direction`, the 4 former allowlist entries this test
    would otherwise have caught). Scans the FULL in-memory denial
    vocabulary (any of `ValidationError`/`CapabilityError`/`ConflictError`/
    `ResourceLimitError`/`NotFoundError`/`PreconditionFailedError`, not
    just the 2 in-scope classes), so a match against a differently-coded
    denial would be caught too."""
    in_memory_messages: set[str] = set()
    for module in ("cell.py", "field_types.py", "http.py", "identifiers.py"):
        in_memory_messages |= _all_denial_messages(SRC / module)
    shared = []
    for module, lineno in sorted(_BACKEND_LAYER_ALLOWLIST):
        message = _message_at(SRC / module, lineno)
        if message in in_memory_messages:
            shared.append(f"{module}:{lineno} {message!r}")
    assert shared == [], f"allowlisted backend denial(s) that duplicate an in-memory-side denial (not a storage translation -- must move off the allowlist): {shared}"


def test_type_pair_rule_is_respected_at_every_violated_declaration_site():
    """M-2 (`{scratchpad}/rulings-r3-r7-flip.md` addendum 2): D-3 (4)'s
    type-pair sub-rule, checked per call site from the `violation(...)`/
    dict-literal ARGUMENTS themselves (never just "some details is
    present" -- `_has_violated_declaration`'s own 0-count check above is
    exactly what would let a `nullable` site with no `declared_type`
    slip through undetected, r2db-api's own `structured.py:1508`
    precedent). `field_type`/`nullable` sites must carry BOTH `declared_
    type` and `observed_type`; `enum` sites must carry `declared_type`
    and must NOT carry `observed_type`."""
    violations: list[str] = []
    for module in SCANNED_MODULES:
        for lineno, cls, vd, present in _type_pair_call_sites(SRC / module):
            required = _TYPE_PAIR_REQUIRED.get(vd)
            if required is None:
                continue
            forbidden = _TYPE_PAIR_FORBIDDEN[vd]
            missing = required - present
            unexpected = forbidden & present
            if missing:
                violations.append(f"{module}:{lineno} {cls} violated_declaration={vd!r} missing required key(s) {sorted(missing)}")
            if unexpected:
                violations.append(f"{module}:{lineno} {cls} violated_declaration={vd!r} carries forbidden key(s) {sorted(unexpected)}")
    assert violations == [], f"type-pair rule (D-3 (4)) not respected: {violations}"


def test_config_budget_denial_helper_carries_the_4_key_form():
    """`config.py` is not a `SCANNED_MODULES` member (see this file's own
    module docstring) -- the overwhelming majority of its `ValidationError`
    call sites are deployment-time `FoundationConfig`/`values`-construction
    checks (`control_plane_status`, `data_base_url`/`control_base_url`,
    env-var resource limits, `surfaces.data` presence), never reached
    while handling one client request, so `errors.details_vocabulary`
    (scoped to query/mutate/schema REQUEST denials, D-1/D-3) does not
    apply to them. The ONE exception is `_budget_denied` (D-6's
    `request_budget` choke point, called from `narrow_limits_by_budget`
    at the SAME validation stage `cell.ApplicationCell._limit_gate`
    checks everything else) -- verified directly here rather than by
    adding `config.py` to the whole-file scan above (which would then
    need its own allowlist for the 6 legitimately out-of-scope
    deployment sites, duplicating the reasoning this test states once)."""
    path = SRC / "config.py"
    tree = ast.parse(path.read_text(), filename=str(path))
    budget_denied_def = next(
        (node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == "_budget_denied"),
        None,
    )
    assert budget_denied_def is not None, "config.py must still define _budget_denied"
    raises = [n for n in ast.walk(budget_denied_def) if isinstance(n, ast.Raise)]
    assert len(raises) == 1
    call = raises[0].exc
    assert isinstance(call, ast.Call) and _call_target_name(call.func) == "ValidationError"
    details_kw = next((kw for kw in call.keywords if kw.arg == "details"), None)
    assert details_kw is not None
    assert isinstance(details_kw.value, ast.Dict)
    keys = {k.value for k in details_kw.value.keys if isinstance(k, ast.Constant)}
    assert "violated_declaration" in keys and "field" in keys


def test_control_plane_module_has_no_data_plane_choke_point_site():
    """The WP-3e T1 work order names `control_plane.py`'s "data 面" as a
    file to inspect for a query/mutate/schema request choke point.
    Reading every `ValidationError`/`CapabilityError` site in that module
    (credential issuance/rotation/revocation, application enable/disable,
    audit-query gating, `application_id`/`destructive`/`confirmation`
    shape checks on control-plane requests) found none: every one of
    them is part of the control-plane credential/application-management
    surface `errors.details_vocabulary` (D-1/D-3, scoped to query/
    mutate/schema requests) never covers -- confirmed here, not merely
    asserted in prose, so a future data-plane site accidentally added to
    this module would need to either carry `details` in `cell.py`/
    `http.py` style or this test itself would need deliberate revision,
    never a silent gap."""
    path = SRC / "control_plane.py"
    sites = _fail_call_sites(path)
    assert sites, "control_plane.py should still contain ValidationError/CapabilityError sites (sanity: scan is not vacuous)"
    # None of these are asserted to carry `details` -- this module is
    # entirely out of `errors.details_vocabulary`'s scope, confirmed by
    # inspection (see module docstring above) rather than by this loop,
    # which only pins the count so a file-shape change is visible here.
    assert len(sites) == 12, len(sites)
