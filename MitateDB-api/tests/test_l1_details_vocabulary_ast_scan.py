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

`config.py` (also named in the WP-3e T1 work order as a file to inspect
for a data-plane choke point) is DELIBERATELY not a member of
`SCANNED_MODULES` below -- see that module's own boundary comment (in
`test_config_budget_denial_helper_carries_the_4_key_form` below) for why
every OTHER `ValidationError`/`CapabilityError` site in it turned out to
belong to a surface `errors.details_vocabulary` never covers (deployment-
time `FoundationConfig` construction), except its own ONE genuine choke-
point site (`_budget_denied`, D-6's `request_budget` gate), verified
directly there rather than folded into the whole-file scan below.

追補 4 O-1 (版フリップ監査 §14 疑義 1/§16, `{scratchpad}/rulings-r3-r7-
flip.md`, 2026-09-08): `control_plane.py`/`control_http.py`/`audit_
query.py` WERE excluded from `SCANNED_MODULES` by an earlier draft of
this scan on the theory that `errors.details_vocabulary` applies only to
the query/mutate/schema DATA-plane request surface -- the audit found
this reading too narrow: contract `versioning.version_binding`'s 1.7.0
unconditional obligation (a) says "**every** denial it answers with
VALIDATION_FAILED ... or CAPABILITY_UNSUPPORTED", with no plane-scoped
carve-out, and these three modules' own `VALIDATION_FAILED`/
`CAPABILITY_UNSUPPORTED` denials (credential/application-management
request-shape checks, the audit-evidence-query capability gate) reach a
real client (an operator/control-credential holder) as problem+json
exactly like a data-plane denial does. They are now full `SCANNED_
MODULES` members -- `ops.py`/`control_auth.py`/`control_credential_
store_postgres.py` stay OUT of scope (not named by O-1's own "12 + 4 +
3" count, and their own `ValidationError`/`CapabilityError` sites are
either deployment-time or duplicate a control_plane.py-level check
already covered here)."""
from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "mitatedb_api"

#: Contract 1.7.0 `errors.details_vocabulary` applies to EVERY
#: `VALIDATION_FAILED`/`IDENTIFIER_INVALID`/`CAPABILITY_UNSUPPORTED`
#: denial this peer answers with, data-plane (D-1/D-3) AND control-plane
#: (追補 4 O-1) alike -- these 11 files are the full choke-point/request-
#: shape layer for both surfaces, plus the two data-plane backend
#: realizations. `config.py`/`ops.py`/`control_auth.py`/`control_
#: credential_store_postgres.py` also raise `ValidationError`/
#: `CapabilityError` (see `{scratchpad}/wp3e-sites.md`'s own 147-site
#: enumeration), but for deployment-time configuration or a surface O-1
#: does not name -- out of this scan's scope (every site in those files
#: was read while drafting this scan/O-1's own fix; `config.py`'s own
#: ONE exception is verified separately, see above).
#: R-37 WP-1 leaf extraction (2026-09-14): `postgres_value_domain.py`
#: holds `_check_domain`, extracted from `backend_postgres.py` -- it
#: carries 4 `ValidationError` call sites (all already 4-key, moved
#: verbatim) and must stay in `SCANNED_MODULES` so a future edit to that
#: leaf is still covered by this scan (this was the exact gap the
#: R-37 WP-1 fix closed: the leaf was extracted without being added
#: here).
#: R-37 WP-1d (2026-09-14): `request_limits.py` holds `_measure_request_
#: bytes`/`_check_operation_depth`, extracted from `cell.py` -- it
#: carries the 2 `ValidationError` call sites those functions moved with
#: (both already 4-key, moved verbatim) and must stay in `SCANNED_
#: MODULES` for the same reason `postgres_value_domain.py` does above.
#: R-37 WP-1j (2026-09-15): `constraint_resolution.py` holds
#: `_validate_enum_declaration_with_path`/`_resolve_field_constraints`,
#: extracted from `cell.py` -- it carries the 3 `ValidationError` call
#: sites those functions moved with (all already 4-key, moved verbatim;
#: a 4th moved denial, a bare `ResourceLimitError`, is outside this
#: scan's `_VOCAB_CLASSES`) and must stay in `SCANNED_MODULES` for the
#: same reason `postgres_value_domain.py` does above.
#: R-37 WP-1l (2026-09-15): `postgres_reserved_names.py` holds
#: `_check_reserved_name`, extracted from `backend_postgres.py` -- it
#: carries the 1 `ValidationError` call site that function moved with
#: (already 4-key, moved verbatim) and must stay in `SCANNED_MODULES`
#: for the same reason `postgres_value_domain.py` does above.
SCANNED_MODULES = (
    "cell.py", "http.py", "field_types.py", "identifiers.py", "backend_postgres.py", "backend_sqlite.py",
    "postgres_value_domain.py", "request_limits.py", "constraint_resolution.py", "postgres_reserved_names.py",
    "control_plane.py", "control_http.py", "audit_query.py",
)

_VOCAB_CLASSES = {"ValidationError", "CapabilityError"}

#: M-1 (`{scratchpad}/rulings-r3-r7-flip.md` addendum 2) / 追補 4 O-2
#: (版フリップ監査 §5/§15, 2026-09-08): the backend-layer allowlist is
#: confined to denials that TRANSLATE a rejection the storage engine
#: itself raised, with NO controlled input a probe can construct to
#: reach it deliberately (a generic `except psycopg.Error`/`except
#: sqlite3.DatabaseError` final backstop, reached only by a genuinely
#: unanticipated driver-level rejection) -- NOT to a re-implementation of
#: a shape/capability/value-domain check the in-memory `ApplicationCell`
#: (or a module it calls into, `field_types.py`/`identifiers.py`) already
#: performs, or that a NORMAL client request can reach on purpose. THREE
#: categories in each backend module were moved OFF this allowlist onto
#: the 4-key form instead: the shared `check_reserved` identifier choke
#: point and the `invalid order direction` `KeyError` backstop (this WP's
#: own earlier fix -- `identifiers.py`'s own module docstring names
#: `check_reserved` as the backend-specific SECOND HALF of `cell.
#: ApplicationCell._identifier`, always applied together with
#: `identifiers.validate_identifier`; `invalid order direction` is the
#: exact literal denial `cell.ApplicationCell._bind_order_by` already
#: carries -- `test_backend_layer_allowlist_entries_have_no_in_memory_
#: sibling_denial` below is what caught this pair), and the PostgreSQL
#: text-encoding / physical value-domain checks (追補 4 O-2, this WP's own
#: closure fix: embedded NUL, lone UTF-16 surrogate, the physical
#: isinstance re-check in `_check_domain`/`backend_sqlite.encode_value`,
#: and the 32/64-bit integer RANGE bound). The 版フリップ監査 (§5) found
#: these last six/two sites reachable from an ORDINARY client request
#: (an insert/filter naming an out-of-range integer or a lone-surrogate/
#: NUL string) while still returning an EMPTY `details` -- contract
#: `versioning.version_binding`'s 1.7.0 unconditional obligation (a)
#: ("every denial ... carries the details keys ... requires for that
#: code") does not carve out an exception for "no in-memory sibling
#: exists to duplicate the wording of"; `errors.details_vocabulary.
#: layer_rule`'s own defence-in-depth exemption is for a denial a client
#: request cannot normally trigger at all, not for one it can. What
#: remains allowlisted is ONLY the generic driver-exception translation
#: backstop (`"storage backend rejected the request"`) -- no controlled
#: input reaches it on purpose, so `test_backend_layer_allowlist_entries_
#: have_no_in_memory_sibling_denial` below judges it by ABSENCE of a
#: reproducible client-reachable input (the probe-based sibling test,
#: `test_backend_value_domain_denials_reachable_from_a_normal_client_
#: request_carry_the_4_key_form` in `tests/test_denial_details_and_
#: request_id.py`/`tests/test_postgres.py`, is what now carries the
#: allowlist's OWN evidentiary weight for the entries this WP moved off
#: -- see those tests' own docstrings), never by comparing message text
#: alone (追補 4 O-2's own stated correction: "「同文言か」ではなく「同じ
#: 入力で in-memory 側が denial を出すか」で判定する" -- a differently-
#: worded denial for an input the in-memory layer WOULD also refuse is
#: still not a storage translation; this test's own scan below (both
#: message-text AND, for the remaining generic-translation entries, "no
#: real input this allowlist entry's own site can be driven by that the
#: in-memory layer would treat differently") is the surviving check for
#: what remains).
#: WP-6d (`{scratchpad}/review2/frame.md` F-①, ruling U-7) line-number
#: shift: `idempotency_begin`/`idempotency_reserve` (2 bare sites) REPLACE
#: the pre-WP-6d `idempotency_get`/`idempotency_reap_expired`/
#: `idempotency_count` (3 bare sites) -- one fewer generic-driver-
#: exception-translation site overall (21 -> 20), and every entry from
#: `schema_count` onward shifted +22 lines (the new `_IDEMPOTENCY_KEY_
#: LOCK_NAMESPACE`/`_IDEMPOTENCY_COUNT_ADVISORY_LOCK_KEY` module-level
#: constants + their comments, inserted above `schema_count`). Recomputed
#: from the real file via `_fail_call_sites`, not hand-counted.
#: `phase10-r35` merge (WP-6d line-number shift, 2026-09-08): the two
#: `LOCK TABLE ... IN SHARE MODE` -> `... IN SHARE ROW EXCLUSIVE MODE`
#: comment rewrites (`alter_field_constraints`, `add_field`) inserted
#: +16 lines then +17 more lines (net +33 for everything after the
#: second rewrite, +16 only for the three sites between the two
#: rewrites) -- NOT a uniform offset, so every entry below is
#: re-verified against the current file via `_fail_call_sites`, not
#: hand-shifted. Entry count unchanged (20): no site was added or
#: removed, only comment/lock-clause text.
#: R-37 WP-1 leaf extraction (2026-09-14): `_check_domain` (4
#: `ValidationError` sites, all already 4-key -- not on this allowlist)
#: moved to `postgres_value_domain.py`, which leaves a facade re-export
#: import in `backend_postgres.py` for `_INT_DOMAIN_RANGES`/
#: `_check_domain`. Net effect on every entry at or before the
#: `encode_value` docstring comment block (`schema_count` through the
#: site just above that comment): UP by 49 lines. Every entry AFTER that
#: comment block (including the two WP-6d-i idempotency sites): UP by
#: 48 lines -- one less, because the R-37 WP-1 corrective change's
#: verbatim-restoration bracket fix to that comment block (`_check_
#: domain` now in `postgres_value_domain.py`) added back 1 line the
#: pre-fix extraction had saved. Reviewer-fix follow-up (2026-09-14):
#: the `_INT_DOMAIN_RANGES` facade-compat comment above the `postgres_
#: value_domain` import (this file's own review item 3) shrank by 1
#: line (a factual correction to what it claimed, not a rewording for
#: its own sake), shifting EVERY entry below DOWN by 1 line again (564
#: -> 563, ..., 1987 -> 1986). Re-verified
#: against the current file via `_fail_call_sites`, not hand-shifted.
#: Entry count and site identity unchanged (20).
#: R-37 WP-1l (2026-09-15): `check_reserved`'s own reserved-name check
#: (`_RESERVED_EXACT`/`_RESERVED_PREFIX` + the `if`/`raise` body, not on
#: this allowlist -- its denial carries `details`) moved to `postgres_
#: reserved_names.py`, leaving a facade re-export import plus a 1-line
#: delegation in `backend_postgres.py`. Net effect: every entry below
#: shifted UP by 14 lines (563 -> 549, ..., 1986 -> 1972). Re-verified
#: against the current file via `_fail_call_sites`, not hand-shifted.
#: Entry count and site identity unchanged (20).
_BACKEND_LAYER_ALLOWLIST: frozenset[tuple[str, int]] = frozenset({
    # Code-review fix F1/F2/F6 (Opus review 2, WP-6d rework): every line
    # number below shifted when `idempotency_begin`/`idempotency_reserve`
    # gained a `conn.commit()` (F1), a `SET LOCAL lock_timeout` + a new
    # `except (QueryCanceled, LockNotAvailable):` clause (F2), and longer
    # docstrings threading `conn` through explicitly instead of resolving
    # `for_developer` internally (F6) -- re-verified against the current
    # file, not merely offset by a constant (the two idempotency sites
    # near the bottom moved by MORE than every site above them, since the
    # added code sits between them and the earlier sites).
    ("backend_postgres.py", 549),   # schema_count: except psycopg.Error -- generic driver-exception translation
    ("backend_postgres.py", 606),   # generic driver-exception translation
    ("backend_postgres.py", 655),   # generic driver-exception translation
    ("backend_postgres.py", 682),   # generic driver-exception translation
    ("backend_postgres.py", 739),   # generic driver-exception translation
    ("backend_postgres.py", 791),   # generic driver-exception translation
    ("backend_postgres.py", 816),   # generic driver-exception translation
    ("backend_postgres.py", 994),   # generic driver-exception translation
    ("backend_postgres.py", 1011),  # generic driver-exception translation
    ("backend_postgres.py", 1142),  # generic driver-exception translation
    ("backend_postgres.py", 1300),  # generic driver-exception translation
    ("backend_postgres.py", 1387),  # generic driver-exception translation
    ("backend_postgres.py", 1439),  # generic driver-exception translation
    ("backend_postgres.py", 1472),  # generic driver-exception translation
    ("backend_postgres.py", 1498),  # generic driver-exception translation
    ("backend_postgres.py", 1565),  # generic driver-exception translation
    ("backend_postgres.py", 1593),  # generic driver-exception translation
    ("backend_postgres.py", 1634),  # generic driver-exception translation
    ("backend_postgres.py", 1903),  # idempotency_begin: except psycopg.Error -- generic driver-exception translation
    ("backend_postgres.py", 1972),  # idempotency_reserve: except psycopg.Error -- generic driver-exception translation
})

#: 追補 4 O-1 left `control_plane.py`'s own ONE remaining bare site --
#: `rotate_credential`'s "a revoked credential cannot be rotated" -- as a
#: disclosed, narrowly-confined allowlist entry, with the supervisor-level
#: decision (reclassify to `ConflictError`, or extend the vocabulary)
#: explicitly left open. O-8 (版フリップ監査, ruling `{scratchpad}/
#: rulings-r3-r7-flip.md` 追補4, pair-closing) resolves it: a STATE
#: precondition on an already-existing resource (the named credential is
#: revoked) is a resource-state CONFLICT, the same kind of fact
#: `ConflictError` ("application already exists", this same module, 4
#: other sites) already exists to carry -- not a declaration violation
#: the closed 11-word `violated_declaration` vocabulary has a word for,
#: and not `ValidationError`. The site now raises `ConflictError`
#: (`control_plane.py`), which is outside `_VOCAB_CLASSES` entirely (this
#: scan only tracks `ValidationError`/`CapabilityError`) -- so this
#: allowlist is now EMPTY, not populated with a rewritten entry: there is
#: no remaining bare `ValidationError`/`CapabilityError` site in
#: `control_plane.py` this scan's own 11-word vocabulary fails to cover.
#: `test_control_plane_service.py::test_rotate_credential_refuses_a_
#: revoked_credential`/`test_enable_credential_never_resurrects_a_
#: revoked_credential` now pin `ConflictError` (updated in the same
#: pair-closing commit).
_CONTROL_PLANE_NO_VOCABULARY_ALLOWLIST: frozenset[tuple[str, int]] = frozenset()


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


#: The two allowlists combined -- every legitimately-bare site across
#: `SCANNED_MODULES`, for whichever of two DISTINCT reasons (backend-
#: layer defence-in-depth with a real storage-only condition, or a
#: control-plane state-conflict the closed vocabulary has no word for).
_ALL_ALLOWLISTS = _BACKEND_LAYER_ALLOWLIST | _CONTROL_PLANE_NO_VOCABULARY_ALLOWLIST


def test_every_choke_point_denial_carries_details_ast_full_count():
    """L-1's own "0 件" assert, AST full-count: every in-scope site
    (i.e. every site NOT on one of the two verified allowlists, across
    all of `SCANNED_MODULES`) must carry non-empty `details`."""
    violations: list[str] = []
    for module in SCANNED_MODULES:
        for lineno, cls, has_details in _fail_call_sites(SRC / module):
            if (module, lineno) in _ALL_ALLOWLISTS:
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
        # R-37 WP-1d (2026-09-14): -2 -- `_measure_request_bytes`'s and
        # `_check_operation_depth`'s own bare-cycle `ValidationError`
        # sites (both already 4-key) moved verbatim to `request_
        # limits.py` (49 -> 47); see that module's own count below.
        # R-37 WP-1j (2026-09-15): -3 -- `_validate_enum_declaration_
        # with_path`'s and `_resolve_field_constraints`'s own 3
        # `ValidationError` sites (all already 4-key) moved verbatim to
        # `constraint_resolution.py` (47 -> 44); see that module's own
        # count below.
        "cell.py": 44,
        # WP-3e rework T2 (追補 L-4): +1 -- `_check_object_shape`'s own
        # new "present but wrong type" leg (a genuine new choke-point
        # call site, not a relabeling of an existing one).
        "http.py": 27,
        "field_types.py": 4,
        "identifiers.py": 1,
        # WP-6d (ruling U-7): -1 -- `idempotency_begin`/`idempotency_
        # reserve` (2 bare `ValidationError` sites) replace the pre-WP-6d
        # `idempotency_get`/`idempotency_reap_expired`/`idempotency_count`
        # (3 bare sites); `idempotency_unlock` (new) raises nothing.
        # R-37 WP-1 leaf extraction (2026-09-14): -4 -- `_check_domain`'s
        # 4 `ValidationError` sites (all already 4-key) moved verbatim to
        # `postgres_value_domain.py` (28 -> 24); see that module's own
        # count below.
        # R-37 WP-1l (2026-09-15): -1 -- `check_reserved`'s own
        # `ValidationError` site (already 4-key) moved verbatim to
        # `postgres_reserved_names.py` (24 -> 23); see that module's own
        # count below.
        "backend_postgres.py": 23,
        "backend_sqlite.py": 4,
        # R-37 WP-1 leaf extraction (2026-09-14): the 4 sites `_check_
        # domain` carried in `backend_postgres.py` before the move,
        # unchanged in wording or `details=` shape.
        "postgres_value_domain.py": 4,
        # R-37 WP-1l (2026-09-15): the 1 `ValidationError` site
        # `check_reserved` carried in `backend_postgres.py` before the
        # move, unchanged in wording or `details=` shape.
        "postgres_reserved_names.py": 1,
        # R-37 WP-1d (2026-09-14): the 2 sites `_measure_request_bytes`/
        # `_check_operation_depth` carried in `cell.py` before the move,
        # unchanged in wording or `details=` shape.
        "request_limits.py": 2,
        # R-37 WP-1j (2026-09-15): the 3 `ValidationError` sites
        # `_validate_enum_declaration_with_path`/`_resolve_field_
        # constraints` carried in `cell.py` before the move, unchanged in
        # wording or `details=` shape. A 4th moved denial (a bare
        # `ResourceLimitError` in `_resolve_field_constraints`) is
        # outside `_VOCAB_CLASSES` and not counted here.
        "constraint_resolution.py": 3,
        # 追補 4 O-1: the 3 control-plane modules this WP newly scans --
        # "12 + 4 + 3" is the AUDIT's own bare-site count (before this
        # WP's fix); the total CALL-SITE count (bare + already-had-
        # details) is 12 / 4 / 4 (`control_http.py`'s own "missing
        # required fields, no sole attributable key" leg is a genuine
        # 4th call site, mirroring `http.py`'s own analogous split).
        # O-8 pair-closing: `rotate_credential`'s "a revoked credential
        # cannot be rotated" site now raises `ConflictError`, outside
        # `_VOCAB_CLASSES` -- `control_plane.py` drops from 12 to 11
        # `ValidationError`/`CapabilityError` call sites.
        "control_plane.py": 11,
        "control_http.py": 4,
        "audit_query.py": 4,
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
    in `backend_postgres.py`/`backend_sqlite.py`/`control_plane.py` that
    was never added to either allowlist."""
    real_bare_sites = {
        (module, lineno)
        for module in SCANNED_MODULES
        for lineno, cls, has_details in _fail_call_sites(SRC / module)
        if not has_details
    }
    missing_from_reality = sorted(_ALL_ALLOWLISTS - real_bare_sites)
    missing_from_allowlist = sorted(real_bare_sites - _ALL_ALLOWLISTS)
    assert missing_from_reality == [], f"allowlist entries with no matching real bare call site: {missing_from_reality}"
    assert missing_from_allowlist == [], f"real bare call site(s) not on the allowlist: {missing_from_allowlist}"


def test_backend_layer_allowlist_is_confined_to_backend_modules():
    """`errors.details_vocabulary.layer_rule`'s exemption is for backend-
    layer defence-in-depth ONLY -- this allowlist must never grow into one
    of the choke-point / request-shape files themselves (that would
    silently reintroduce the exact L-1 gap this rework closed)."""
    assert all(module in ("backend_postgres.py", "backend_sqlite.py") for module, _ in _BACKEND_LAYER_ALLOWLIST)


def test_control_plane_allowlist_is_confined_to_control_plane_py_and_one_entry():
    """The no-vocabulary-fit allowlist (追補 4 O-1) is deliberately tiny
    and named-module-confined -- unlike the backend allowlist, growth here
    should be rare and each addition individually justified in prose (a
    site genuinely outside the closed 11-word vocabulary), never used as
    a general escape hatch for "did not get around to it yet". O-8
    pair-closing resolved the one entry O-1 left open (`rotate_
    credential`'s revoked-credential refusal now raises `ConflictError`,
    outside this scan's `_VOCAB_CLASSES` entirely) -- the allowlist is
    now empty, kept as a named, typed constant (not deleted outright) so
    a future genuinely-no-vocabulary-fit site has an established place to
    be added, individually justified, the same way this one was."""
    assert _CONTROL_PLANE_NO_VOCABULARY_ALLOWLIST == frozenset()


def test_control_plane_allowlist_entry_matches_a_real_bare_site():
    """Mirrors `test_allowlist_entries_match_real_bare_call_sites` above,
    scoped to the (now empty) control-plane allowlist -- if a new bare
    `ValidationError`/`CapabilityError` site appears in `control_plane.py`
    that this scan's own 4-key check does not already cover, this goes
    red rather than silently letting it slip through unaccounted for."""
    real_bare_sites = {
        (module, lineno)
        for module in ("control_plane.py",)
        for lineno, cls, has_details in _fail_call_sites(SRC / module)
        if not has_details
    }
    assert real_bare_sites == _CONTROL_PLANE_NO_VOCABULARY_ALLOWLIST, real_bare_sites


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
    for module in ("cell.py", "field_types.py", "http.py", "identifiers.py", "request_limits.py", "constraint_resolution.py"):
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


#: R-37 WP-1 fix (2026-09-14, corrective revision per reviewer ruling):
#: guard against the exact gap this WP found -- `postgres_value_domain.
#: py` was extracted from `backend_postgres.py` without being added to
#: `SCANNED_MODULES`, so its `ValidationError` denials silently dropped
#: out of scan coverage. `config.py`/`control_auth.py`/`control_
#: credential_store_postgres.py`/`ops.py` are the ONLY modules under
#: `src/mitatedb_api` (recursively) that carry a vocabulary-class denial
#: site while staying out of `SCANNED_MODULES` -- this file's own
#: top-level module docstring already discloses them as a deliberate
#: scope limit (deployment-time configuration or a surface O-1 does not
#: name); `config.py`'s own one genuine choke-point site is separately
#: verified by `test_config_budget_denial_helper_carries_the_4_key_form`
#: above. Each entry's value below is that disclosure, quoted short, not
#: a fresh justification invented here. Any OTHER module with such a
#: site is a real coverage gap, not a disclosed one. Adding, removing,
#: or renaming an entry here is a `SCANNED_MODULES`-boundary change and
#: requires the same supervisor ruling any other change to that boundary
#: would -- this set is not a general escape hatch. LIMITATION (this
#: scan's own coverage boundary, not something this guard can close): a
#: vocabulary-class denial newly added INSIDE an already-excluded module
#: is invisible to this whole file -- excluding a module means its
#: future edits are not audited here at all, only that its CURRENT
#: exclusion is not silently stale or silently overlapping `SCANNED_
#: MODULES`.
_DELIBERATELY_UNSCANNED_MODULES: dict[str, str] = {
    "config.py": "module docstring above: deployment-time FoundationConfig construction, not a client-request choke point (its own _budget_denied exception is verified separately)",
    "control_auth.py": "module docstring above: not named by O-1's own 12+4+3 count",
    "control_credential_store_postgres.py": "module docstring above: not named by O-1's own 12+4+3 count",
    "ops.py": "module docstring above: not named by O-1's own 12+4+3 count",
}


def test_every_module_with_a_vocabulary_denial_is_accounted_for():
    """Regression guard for scan-coverage gaps: walks every `*.py`
    under `src/mitatedb_api`, RECURSIVELY (a nested package such as
    `contract/` can carry its own denial site just as easily as a
    top-level module can), and asserts that any module carrying >= 1
    site this scanner's own `_fail_call_sites` counts is either a
    `SCANNED_MODULES` member or a key of the explicit, reasoned
    exclusion set above. Keys are POSIX relative paths from
    `src/mitatedb_api` -- identical to the plain filename for every
    current top-level entry, but able to name a nested file (e.g.
    `contract/__init__.py`) without inventing a different key shape for
    that case. Non-空振り: also asserts at least one module was actually
    found carrying a denial, so a scanner that silently matched nothing
    anywhere would not pass this test vacuously."""
    modules_with_denials: list[str] = []
    unaccounted: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        rel = path.relative_to(SRC).as_posix()
        if _fail_call_sites(path):
            modules_with_denials.append(rel)
            if rel not in SCANNED_MODULES and rel not in _DELIBERATELY_UNSCANNED_MODULES:
                unaccounted.append(rel)
    assert modules_with_denials, "no module under src/mitatedb_api carries a vocabulary-class denial call site -- the scanner is not visiting real code"
    assert unaccounted == [], f"module(s) with a vocabulary-class denial call site but not in SCANNED_MODULES or the explicit exclusion set: {unaccounted}"


def test_deliberately_unscanned_modules_do_not_overlap_scanned_modules():
    """A module must never sit on BOTH `SCANNED_MODULES` and this
    exclusion set at once -- that would mean an incomplete edit (an
    exclusion entry added without removing the module from `SCANNED_
    MODULES`, or vice versa) left the two boundaries contradicting each
    other, silently obscuring which one actually governs that module."""
    overlap = sorted(set(_DELIBERATELY_UNSCANNED_MODULES) & set(SCANNED_MODULES))
    assert overlap == [], f"module(s) listed as both scanned and deliberately excluded: {overlap}"


def test_deliberately_unscanned_modules_each_carry_a_real_denial():
    """Guard against exclusion-set staleness: every excluded module must
    actually contain >= 1 vocabulary-class denial site right now,
    checked against the same live scanner the rest of this file uses --
    a module that no longer does should be REMOVED from the exclusion
    set (there is nothing left to disclose an exception for), not left
    there as unexplained dead weight that could later hide a real gap."""
    for rel, reason in sorted(_DELIBERATELY_UNSCANNED_MODULES.items()):
        assert reason, f"{rel} has no reason recorded in _DELIBERATELY_UNSCANNED_MODULES"
        sites = _fail_call_sites(SRC / rel)
        assert sites, f"{rel} is on the exclusion set but carries no vocabulary-class denial site -- remove it"


# 追補 4 O-1 (版フリップ監査 §14 疑義 1/§16, 2026-09-08): the test that
# used to stand here, `test_control_plane_module_has_no_data_plane_
# choke_point_site`, asserted the OPPOSITE of what this file now enforces
# -- that every `control_plane.py` `ValidationError`/`CapabilityError`
# site was legitimately exempt from `errors.details_vocabulary` because
# the module sat entirely outside its scope (a "data 面のみ" reading of
# D-1/D-3 the audit found too narrow; see the module docstring above and
# `versioning.version_binding`'s own unconditional (a) obligation, which
# names no plane-scoped carve-out). `control_plane.py` is now a full
# `SCANNED_MODULES` member instead -- `test_every_choke_point_denial_
# carries_details_ast_full_count`/`test_ast_full_count_matches_a_non_
# trivial_floor`/`test_allowlist_entries_match_real_bare_call_sites`
# above already cover it (its 12-site count, its one remaining allowlisted
# site, and the 4-key requirement on the other 11), making a THIRD,
# narrower test asserting the module's old exempt status both redundant
# and actively wrong to keep.
