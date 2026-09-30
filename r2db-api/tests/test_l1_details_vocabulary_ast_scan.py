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

#: Contract 1.7.0 `errors.details_vocabulary`'s unconditional obligation
#: (a) (`versioning.version_binding`'s own 1.7.0 paragraph) covers "every
#: denial" this peer answers with VALIDATION_FAILED/IDENTIFIER_INVALID/
#: CAPABILITY_UNSUPPORTED -- not only the data-plane query/mutate/schema
#: request surface. WP-2e rework closure audit (版フリップ監査, ruling
#: `{scratchpad}/rulings-r3-r7-flip.md` 追補4 O-1): the CONTROL-plane
#: credential/application-management surface (`control_plane.py`'s own
#: `fail()`/`_deny(code=..., extra_details=...)` call sites, plus
#: `control_http.py`/`audit_query.py`, which call neither directly but
#: are scanned too so a future direct call site there is not silently
#: missed) is now in scope -- the earlier "out of this scan's scope by
#: the same boundary the audit's own 76-site count already drew" posture
#: this comment previously stated was itself the D-1 gap O-1 closes.
#: `auth.py`/`credential_store.py`/`ops.py` (also named in the pre-O-1
#: version of this comment) remain OUT of scope -- O-1's own audit did
#: not enumerate them, and this WP does not extend the scan there
#: (disclosed as unaddressed, not silently included by inference).
#: `postgres.py` is the backend storage layer UNDERNEATH the data-plane
#: surface (`layer_rule`'s defence-in-depth exemption) -- included in
#: the scan below via the allowlist, never silently skipped.
#: R-37 WP-1e (2026-09-14): `inmemory_predicate.py` holds `_wildcard_
#: pattern`, extracted from `structured.py` -- it carries the 1 `fail(
#: "VALIDATION_FAILED", ...)` call site that function moved with (already
#: 4-key, moved verbatim) and must stay in `SCANNED_MODULES` for the same
#: reason `postgres_value_domain.py`/`request_limits.py` do on the
#: MitateDB side (this was the exact gap the R-37 WP-1 fix closed: a leaf
#: extracted without being added here).
#: R-37 WP-1f (2026-09-14): `identifier_rules.py` holds `validate_
#: identifier`/`_reject_reserved_field`/`_reject_reserved_prefix`/
#: `_reject_reserved_entity_name`, extracted from `structured.py` -- it
#: carries the 4 `fail("IDENTIFIER_INVALID", ...)` call sites those
#: functions moved with (already 4-key, moved verbatim) and must stay in
#: `SCANNED_MODULES` for the same reason as `inmemory_predicate.py` above.
#: R-37 WP-1h (2026-09-14): `paging.py` holds `validate_page_size`/
#: `_resolve_order_by`/`_shape_hash`/`_encode_cursor`/`_decode_cursor`,
#: extracted from `structured.py` -- it carries the 10 `fail("VALIDATION_
#: FAILED", ...)` call sites those functions moved with (already 4-key,
#: moved verbatim; the `_resolve_order_by` `fail("NOT_FOUND", ...)` site
#: and `validate_page_size`'s own `fail("LIMIT_EXCEEDED", ...)` site are
#: not vocabulary codes and are not counted here) and must stay in
#: `SCANNED_MODULES` for the same reason as `identifier_rules.py` above.
#: Phase 11 keyset paging WP-5 (design docs/design/
#: PHASE11_KEYSET_PAGING_V1.md D-3): `_shape_hash`/`_encode_cursor`/
#: `_decode_cursor` are replaced by `canonical_page_binding`/`encode_page_
#: cursor`/`decode_page_cursor` (the D-6 codec/binding trio) plus the new
#: r2db-only wrapper `decode_and_check_page_cursor`; `validate_page_size`'s
#: own `LIMIT_EXCEEDED`/`VALIDATION_FAILED` split collapses to one
#: `VALIDATION_FAILED` site (D-3 (8)). `paging.py`'s own vocabulary count is
#: now 6: `validate_page_size` (1), `_resolve_order_by` (4, unchanged), and
#: `decode_and_check_page_cursor` (1, a single site covering decode/
#: binding/count/type failure alike -- D-1 (5) collapses all four into one
#: refusal). `encode_page_cursor`/`decode_page_cursor`/`canonical_page_
#: binding` raise no `fail(...)` of their own (`decode_page_cursor` raises
#: `ValueError`, per D-6 (b)) and add 0.
#: R-37 WP-1i (2026-09-14): `value_types.py` holds `_check_type`/
#: `_declared_type_label`/`_validate_wildcard_pattern`/`_validate_
#: predicate_types` (plus the `_TEXT_ONLY_OPERATORS` set only the last of
#: those reads), extracted from `structured.py` -- it carries the 11
#: `fail("VALIDATION_FAILED", ...)` call sites those functions moved with
#: (already 4-key, moved verbatim) and must stay in `SCANNED_MODULES` for
#: the same reason as `paging.py` above.
#: R-37 WP-3c (2026-09-15): `request_shape.py` holds `_check_query_
#: request_shape`/`_check_mutation_request_shape`, extracted from
#: `service.py` -- it carries the 6 `fail(...)` call sites (4
#: `VALIDATION_FAILED` from the query-shape checks, 1 `CAPABILITY_
#: UNSUPPORTED` and 1 `VALIDATION_FAILED` from the mutation-shape checks)
#: those functions moved with (already 4-key, moved verbatim) and must
#: stay in `SCANNED_MODULES` for the same reason as `value_types.py`
#: above.
#: R-37 WP-4c (2026-09-16): `postgres_sql.py` holds `_predicate_sql`
#: (plus `_select_statement`/`_order_by_sql`/`_bind_value`/`_append_
#: revision_predicate`/`_where_clause`/`_text_expression`, none of which
#: carry a vocabulary `fail(...)` site), extracted from `postgres.py` --
#: it carries the 2 `fail("VALIDATION_FAILED", ...)` call sites
#: `_predicate_sql` moved with (already 4-key, moved verbatim) and must
#: stay in `SCANNED_MODULES` for the same reason as `schema_binding.py`
#: above. Unlike those leaves, `postgres.py` itself is not a member of
#: the `counts` dict's own module tuple (Z4-6: the backend layer was
#: never pinned there), so there is no matching subtraction to record.
SCANNED_MODULES = ("structured.py", "service.py", "limits.py", "http.py", "postgres.py", "control_plane.py", "control_http.py", "audit_query.py", "inmemory_predicate.py", "identifier_rules.py", "paging.py", "value_types.py", "request_shape.py", "mutation_binding.py", "schema_binding.py", "postgres_sql.py")

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
#: R-78 (2026-09-23, work order docs/work-orders/
#: WORK_ORDER_R78_POOL_WAIT_MEASUREMENT_V1.md D-1): `_RolePool.__init__`
#: gained six acquisition-statistics fields, `_acquire` gained calls into
#: three new `_record_acquire`/`_record_wait`/`_record_release` methods
#: (inserted directly above `_liveness_check`), and `SharedPoolManager`
#: gained a `stats()` method -- all inserted ABOVE `_fail_client_value`'s
#: own single `fail()` call, pushing it (and nothing else vocabulary-
#: relevant) down by 64 lines. Re-verified against the current file via
#: `_fail_call_sites`, not hand-shifted. Entry count and site identity
#: unchanged (1) -- R-78 calls no `fail()`/`violation()`/`_VOCAB_CLASSES`
#: site of its own; only the line number of this one pre-existing generic
#: `except psycopg.errors.DataError` backstop moves.
_BACKEND_LAYER_ALLOWLIST: frozenset[tuple[str, int]] = frozenset({
    # WP-6d (ruling U-7, `{scratchpad}/review2/frame.md` F-①): line shift
    # only (1621 -> 1732) -- the new `_idempotency_key_lock`/`_idempotency_
    # reserve_lock` methods and their module-level lock constants, inserted
    # earlier in this same file, push every later line down; `_fail_client_
    # value`'s own single `fail()` call is otherwise unchanged. Code-review
    # fix F7 (Opus review 2): another line shift only (1732 -> 1744) --
    # correcting `_IDEMPOTENCY_KEY_LOCK_NAMESPACE`'s own false collision
    # rationale lengthened that comment block by 12 lines; the call site
    # itself is still otherwise unchanged.
    # Phase 10 WP-6a merge with main (2026-09-09): line shift only (1744 ->
    # 1752) -- WP-6a's own doc comment in _idempotency_reserve (the LOCK
    # TABLE it once carried was removed; WP-6d-i owns that lock) lengthens the
    # file by 8 lines above this call site.
    # R-37 WP-1 leaf extraction (2026-09-14): line shift only (1752 -> 1706)
    # -- `_column_type_sql`/`_FIELD_TYPE_SQL`/`_JSONB_SQL` moved to
    # `postgres_types.py` and `_escape_like_literal` moved to
    # `postgres_like.py`, each leaving a facade re-export import in place of
    # the removed body; `_fail_client_value`'s own single `fail()` call is
    # otherwise unchanged.
    # R-37 WP-4b (2026-09-16): line shift only (1523 -> 1472) -- `_DOMAIN_TO_
    # DECLARED`/`_SQL_TYPE_TO_DECLARED`/`_TableInfo` moved to
    # `postgres_types.py`, leaving a facade re-export import in place of the
    # removed body; `_fail_client_value`'s own single `fail()` call is
    # otherwise unchanged.
    # R-37 WP-4c (2026-09-16): line shift only (1472 -> 1439) -- `_COMPARISON_
    # OPERATORS`/`_select_statement`/`_order_by_sql`/`_bind_value`/`_append_
    # revision_predicate`/`_where_clause`/`_text_expression`/`_predicate_sql`
    # moved to `postgres_sql.py`, leaving a delegation attribute (or, for
    # `_COMPARISON_OPERATORS`, nothing -- it had no external reader) in place
    # of each removed body, and a facade-compat import of `_escape_like_
    # literal` (still read by `test_postgres.py`'s own facade test) net +7
    # lines above; `_fail_client_value`'s own single `fail()` call is
    # otherwise unchanged.
    # R-62 WP-1 (2026-09-21): line shift only (1439 -> 1451) -- `catalog` now
    # threads `limits` through `_set_timeouts`/the mapped-exception handlers
    # inside its own transaction (parity with `query`/`transact`/`apply_
    # schema`), lengthening the file by 12 lines above this call site;
    # `_fail_client_value`'s own single `fail()` call is otherwise unchanged.
    # R-78 WP-1 (2026-09-23): line shift only (1451 -> 1515) -- see this
    # frozenset's own `#:` header above for the detailed accounting.
    # R-79 WP-1 (2026-09-23): line shift only (1515 -> 1659, then 1659 ->
    # 1658 after a rework pass removed the probe's own internal `try`/
    # `except` -- WO §2.2 completion condition 15's own
    # `finally`-based connection return only exercises meaningfully when
    # the probe itself is allowed to raise, so the catch moved to the
    # caller) -- `postgres.py` gained a `CountingConnection` import, the
    # module-level `pg_prepared_statements` probe helpers, and `_RolePool.
    # prepared_stats`/`SharedPoolManager.prepared_stats` (WO §2.1 D-1/D-2),
    # all above this call site; `_fail_client_value`'s own single `fail()`
    # call is otherwise unchanged.
#: R-79 WP-1 supervisor rework (2026-09-23): the CH-ID-less comment block
#: in front of `_RolePool._connect`'s `CountingConnection.connect` call
#: was removed (comment provenance §4.1 (2)), shortening the file by 6
#: lines -- the `postgres.py` site below shifted UP by 6. Re-verified via
#: `_fail_call_sites`.
#: R-79 WP-1 rework (2026-09-23, 指摘 3): 1652 -> 1584 -- the `pg_
#: prepared_statements` probe helpers (then locally named with a leading
#: underscore, now the shared, public `prepared_stats_skeleton`/`probe_
#: prepared_statements`) moved out of this file entirely, into
#: `psycopg_counting.py` (shared with MitateDB-api, no longer duplicated
#: per peer); only a `CountingConnection`/`prepared_stats_skeleton`/
#: `probe_prepared_statements` import line remains here. Re-verified via
#: `_fail_call_sites`.
#: R-79 WP-1 final rework (2026-09-23): the `_RolePool.prepared_stats`
#: docstring gained the harness-only calling condition (8 lines), so the
#: `postgres.py` site below shifted DOWN by 8. Re-verified via
#: `_fail_call_sites`.
#: R-79 WP-3 (2026-09-23): line shift only (1592 -> 1604) -- `_liveness_
#: check` grew a non-IDLE pre-check and a replacement explanatory comment
#: for its own `autocommit`-based ping, net +12 lines above this call site.
#: Phase 11 keyset paging WP-5 (2026-09-25): line shift only (1604 -> 1626)
#: -- `PostgresCell.query` gained the keyset binding/decode/predicate lines
#: (design D-3), net +22 lines above this call site; `_fail_client_value`'s
#: own single `fail()` call is otherwise unchanged. Re-verified via
#: `_fail_call_sites`.
#: Review corrections 2026-09-25 (task A, comment provenance CH-0024
#: correction): line shift only (1626 -> 1627) -- a `# history: CH-0024`
#: reference line was added above this call site's own scope; `_fail_
#: client_value`'s own single `fail()` call is otherwise unchanged.
#: Re-verified via `_fail_call_sites`.
#: R-101 WP-1 (2026-09-26): line shift only (1627 -> 1694) -- `_RolePool`
#: gained platform DB-time accounting (`_connect_wall_ms`/`_sessions`/
#: `_closed_db_wall_ms`/`_closed_txn_count` in `__init__`, connect timing
#: in `_connect`, `_fold_closed_connection_stats`, and the read-only
#: `platform_stats` method), all inserted ABOVE `_fail_client_value`'s own
#: single `fail()` call, pushing it down by 67 lines. Re-verified against
#: the current file via `_fail_call_sites`. Entry count and site identity
#: unchanged (1) -- this WP calls no `fail()`/`violation()`/`_VOCAB_
#: CLASSES` site of its own; only the line number of this one pre-existing
#: generic `except psycopg.errors.DataError` backstop moves.
#: R-101 WP-1 差し戻し 1 (2026-09-26): line shift only (1694 -> 1703) --
#: `_RolePool` gained a `_closed_db_calls` counter (`__init__`), folded in
#: by `_fold_closed_connection_stats` and read back by `platform_stats`
#: (`db_calls=` on the `DBTIME scope=platform` line, no longer a fixed
#: `0`), all inserted ABOVE `_fail_client_value`'s own single `fail()`
#: call, pushing it down by 9 lines. Re-verified against the current file
#: via `_fail_call_sites`. Entry count and site identity unchanged (1).
#: R-101 WP-1 差し戻し 2 (2026-09-26): line shift only (1703 -> 1733) --
#: `_RolePool.connection()` now folds an already-`.closed` dequeued
#: connection's own stats before replacing it, and tracks that connection
#: (`already_folded_conn`) so the `finally` block does not fold the same
#: connection's stats a second time when its own replacement `_connect()`
#: call raises, all inserted ABOVE `_fail_client_value`'s own single
#: `fail()` call, pushing it down by 30 lines. Re-verified against the
#: current file via `_fail_call_sites`. Entry count and site identity
#: unchanged (1).
#: R-101 WP-1 差し戻し 2 comment fix (2026-09-26): line shift only (1733
#: -> 1734) -- a one-line net growth in the comments above `_RolePool.
#: connection()` and its own `_stats_lock` accounting note, still ABOVE
#: `_fail_client_value`'s own single `fail()` call. Re-verified against
#: the current file via `_fail_call_sites`. Entry count and site identity
#: unchanged (1).
#: R-113 WP-2 (2026-09-28): line shift only (1734 -> 1779) -- a new
#: module-level `application_name` toggle (`_connection_application_
#: name`/`set_connection_application_name`/`_application_name_connect_
#: kwargs`) and its own `**_application_name_connect_kwargs()` spread in
#: `_RolePool._connect`, all inserted ABOVE `_fail_client_value`'s own
#: single `fail()` call, pushing it down by 45 lines. Re-verified against
#: the current file via `_fail_call_sites`. Entry count and site identity
#: unchanged (1).
#: R-115 WP-4a (2026-09-30): line shift only (1779 -> 1785) -- `PostgresCell.
#: transact` moved its audit pre-commit call after the idempotency record
#: write and gained an `error`-row call in each of its two 413 branches, net
#: +6 lines ABOVE `_fail_client_value`'s own single `fail()` call.
#: Re-verified against the current file via `_fail_call_sites`. Entry count
#: and site identity unchanged (1).
#: R-115 WP-4b (2026-09-30): line shift only (1785 -> 1791) -- `PostgresCell.
#: transact` writes the `error` row in its `UniqueViolation` and `DataError`
#: branches too, net +6 lines ABOVE `_fail_client_value`'s own single `fail()`
#: call. Re-verified against the current file via `_fail_call_sites`. Entry
#: count and site identity unchanged (1).
    ("postgres.py", 1791),  # _fail_client_value: generic psycopg.errors.DataError catch, cannot attribute to one field -- a storage-rejection translation with no in-memory equivalent (this WP's own I-6 pin target)
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
    count.

    O-1 (版フリップ監査, ruling `{scratchpad}/rulings-r3-r7-flip.md` 追補4):
    also matches `self._deny(code=<CODE literal>, ..., extra_details=...)`
    -- `control_plane.py`'s own R-6/R-11 durable-denial helper, which
    raises through `fail(code, message, ..., details=details)` internally
    but with `code`/`details` both DYNAMIC (a local variable, never a
    literal at that inner call site) -- the bare `fail`-name match above
    can never see a `_deny`-mediated denial at all, which would silently
    exempt every one of `_deny`'s own callers from this scan. `code=`/
    `extra_details=` are matched the same way `fail`'s own first
    positional arg / `details=` keyword are: a literal string in
    `_VOCAB_CODES`, and `_has_violated_declaration` run over whatever
    `extra_details` is (a `violation(...)` call, or a dict literal that
    spells `violated_declaration` out directly -- `_deny` itself merges
    `extra_details` into its own `{"audited": ..., "attribution": ...}`
    base dict via `dict.update`, so a caller's own `extra_details` value
    is exactly the fragment this scan needs to inspect, never the whole
    merged dict `_deny` builds at runtime, which this static scan never
    sees)."""
    tree = ast.parse(path.read_text(), filename=str(path))
    sites: list[tuple[int, str, bool]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.id if isinstance(func, ast.Name) else (func.attr if isinstance(func, ast.Attribute) else None)
        if name == "fail" and node.args:
            first = node.args[0]
            if not (isinstance(first, ast.Constant) and isinstance(first.value, str) and first.value in _VOCAB_CODES):
                continue
            details_kw = next((kw for kw in node.keywords if kw.arg == "details"), None)
            has_details = details_kw is not None and _has_violated_declaration(details_kw.value)
            sites.append((node.lineno, first.value, has_details))
        elif name == "_deny":
            code_kw = next((kw for kw in node.keywords if kw.arg == "code"), None)
            if code_kw is None or not (isinstance(code_kw.value, ast.Constant) and isinstance(code_kw.value.value, str) and code_kw.value.value in _VOCAB_CODES):
                continue
            extra_kw = next((kw for kw in node.keywords if kw.arg == "extra_details"), None)
            has_details = extra_kw is not None and _has_violated_declaration(extra_kw.value)
            sites.append((node.lineno, code_kw.value.value, has_details))
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
    CAPABILITY_UNSUPPORTED site in these 8 files that already carried
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
    counts = {module: len(_fail_call_sites(SRC / module)) for module in ("structured.py", "service.py", "limits.py", "http.py", "inmemory_predicate.py", "identifier_rules.py", "paging.py", "value_types.py", "request_shape.py", "mutation_binding.py", "schema_binding.py", "postgres_sql.py")}
    assert counts == {
        # R-37 WP-1e (2026-09-14): -1 -- `_wildcard_pattern`'s own bare
        # trailing-backslash `fail("VALIDATION_FAILED", ...)` site
        # (already 4-key) moved verbatim to `inmemory_predicate.py`
        # (93 -> 92); see that module's own count below.
        # R-37 WP-1f (2026-09-14): -4 -- `validate_identifier`/
        # `_reject_reserved_field`/`_reject_reserved_prefix`/`_reject_
        # reserved_entity_name`'s own `fail("IDENTIFIER_INVALID", ...)`
        # sites (already 4-key) moved verbatim to `identifier_rules.py`
        # (92 -> 88); see that module's own count below.
        # R-37 WP-1h (2026-09-14): -10 -- `validate_page_size`/
        # `_resolve_order_by`/`_decode_cursor`'s own `fail("VALIDATION_
        # FAILED", ...)` sites (already 4-key) moved verbatim to
        # `paging.py` (88 -> 78); see that module's own count below.
        # R-37 WP-1i (2026-09-14): -11 -- `_check_type`/`_validate_
        # wildcard_pattern`/`_validate_predicate_types`'s own `fail(
        # "VALIDATION_FAILED", ...)` sites (already 4-key) moved verbatim
        # to `value_types.py` (78 -> 67); see that module's own count
        # below.
        # R-37 WP-3c (2026-09-15): -6 -- `_query_outcome`'s 4 `fail(
        # "VALIDATION_FAILED", ...)` request-shape sites and `_mutate_
        # outcome`'s `fail("CAPABILITY_UNSUPPORTED", ...)`/`fail(
        # "VALIDATION_FAILED", ...)` sites (already 4-key) moved verbatim
        # to `request_shape.py` (10 -> 4); see that module's own count
        # below.
        # R-37 WP-3f (2026-09-15): -18 -- `Predicate.validate`'s/
        # `bind_mutation`'s own `fail("VALIDATION_FAILED", ...)`/`fail(
        # "CAPABILITY_UNSUPPORTED", ...)` sites (already 4-key) moved
        # verbatim to `mutation_binding.py` (67 -> 49); see that module's
        # own count below.
        # R-37 WP-3g (2026-09-15): -1 -- `_fail_constraint_declaration`'s
        # own `fail("VALIDATION_FAILED", ...)` site (already 4-key) moved
        # verbatim to `schema_binding.py` (49 -> 48); see that module's
        # own count below.
        "structured.py": 48, "service.py": 4, "limits.py": 5, "http.py": 8,
        # R-37 WP-1e (2026-09-14): the 1 site `_wildcard_pattern` carried
        # in `structured.py` before the move, unchanged in wording or
        # `details=` shape.
        "inmemory_predicate.py": 1,
        # R-37 WP-1f (2026-09-14): the 4 sites `validate_identifier`/
        # `_reject_reserved_field`/`_reject_reserved_prefix`/`_reject_
        # reserved_entity_name` carried in `structured.py` before the
        # move, unchanged in wording or `details=` shape.
        "identifier_rules.py": 4,
        # R-37 WP-1h (2026-09-14): the 10 `fail("VALIDATION_FAILED", ...)`
        # sites `validate_page_size`/`_resolve_order_by`/`_decode_cursor`
        # carried in `structured.py` before the move, unchanged in
        # wording or `details=` shape (the module's own `LIMIT_EXCEEDED`
        # and `NOT_FOUND` sites are not vocabulary codes and are not
        # counted here).
        # Phase 11 keyset paging WP-5 (design D-3): -4 -- `validate_page_
        # size`'s own `LIMIT_EXCEEDED`/`VALIDATION_FAILED` split collapses
        # to 1 `VALIDATION_FAILED` site (-0 net from that function, since
        # only the `VALIDATION_FAILED` leg was ever counted); `_shape_
        # hash`/`_encode_cursor`/`_decode_cursor`'s 5 sites (all inside the
        # old `_decode_cursor`) are replaced by the new codec (`encode_
        # page_cursor`/`decode_page_cursor`/`canonical_page_binding`, 0
        # `fail(...)` sites of their own -- `decode_page_cursor` raises
        # `ValueError`, D-6 (b)) plus 1 new site in the r2db-only wrapper
        # `decode_and_check_page_cursor` (a single site covering decode/
        # binding/count/type failure alike, D-1 (5)); `_resolve_order_by`
        # is unchanged (4 sites). Net: 1 (`validate_page_size`) + 4
        # (`_resolve_order_by`) + 1 (`decode_and_check_page_cursor`) = 6
        # (10 -> 6).
        # Contract 1.11.0 (subordinate ruling 16): +1 -- `_resolve_order_by`'s
        # undeclared-field site converts from `NOT_FOUND` (not a vocabulary
        # code, uncounted) to `VALIDATION_FAILED`/`request_schema` (6 -> 7).
        "paging.py": 7,
        # R-37 WP-1i (2026-09-14): the 11 `fail("VALIDATION_FAILED", ...)`
        # sites `_check_type`/`_validate_wildcard_pattern`/`_validate_
        # predicate_types` carried in `structured.py` before the move,
        # unchanged in wording or `details=` shape.
        # Review corrections 2026-09-25 (task C, design PHASE11_
        # KEYSET_PAGING_V1 D-3 (4a)): +2 -- `_check_type`'s own "number"
        # (finite float64) and "string" (no lone UTF-16 surrogate) domain
        # checks, the shared choke point `where` and `page/cursor` both
        # pass through (11 -> 13).
        "value_types.py": 13,
        # R-37 WP-3c (2026-09-15): the 6 sites `_check_query_request_
        # shape`/`_check_mutation_request_shape` carried in `service.py`
        # before the move, unchanged in wording or `details=` shape.
        "request_shape.py": 6,
        # R-37 WP-3f (2026-09-15): the 18 `fail("VALIDATION_FAILED", ...)`/
        # `fail("CAPABILITY_UNSUPPORTED", ...)` sites `Predicate.validate`/
        # `bind_mutation` carried in `structured.py` before the move,
        # unchanged in wording or `details=` shape.
        # Contract 1.11.0 (subordinate ruling 16): +3 -- `validate_
        # projection`'s select, `validate_predicates`'s where (shared by
        # both a top-level query's own where and a mutation item's where)
        # and `bind_mutation`'s values-key undeclared-field sites convert
        # from `NOT_FOUND` (not a vocabulary code, uncounted) to
        # `VALIDATION_FAILED`/`request_schema` (18 -> 21).
        "mutation_binding.py": 21,
        # R-37 WP-3g (2026-09-15): the 1 `fail("VALIDATION_FAILED", ...)`
        # site `_fail_constraint_declaration` carried in `structured.py`
        # before the move, unchanged in wording or `details=` shape.
        "schema_binding.py": 1,
        # R-37 WP-4c (2026-09-16): the 2 `fail("VALIDATION_FAILED", ...)`
        # sites `_predicate_sql` carried in `postgres.py` before the move
        # ("Filter value is incompatible with the selected operator."/
        # "Unsupported filter operator."), unchanged in wording or
        # `details=` shape. `postgres.py` itself is not in this dict (Z4-6
        # asymmetry: it was never a member of this tuple, so there is
        # nothing to subtract).
        "postgres_sql.py": 2,
    }, counts
    assert sum(counts.values()) >= 76, counts


def test_control_plane_scan_is_not_vacuous():
    """O-1's own non-空振り pin, mirroring the data-plane pin just above:
    `control_plane.py` carries 11 direct `fail(...)` sites (all 11 now
    4-key, per this scan's own 0-count test -- O-8 pair-closing dropped
    the count from 12: `rotate_credential`'s revoked-credential refusal
    now raises `fail("CONFLICT", ...)`, a code outside `_VOCAB_CODES`
    entirely, not a `VALIDATION_FAILED` this scan tracks) PLUS 2 `_deny(
    code=...)` sites (`_deny_audit_capability_unsupported`/`_deny_role_
    control`, both CAPABILITY_UNSUPPORTED) that the bare `fail`-name
    match alone would never see -- 13 total. `control_http.py`/`audit_
    query.py` genuinely carry 0 (neither calls `fail`/`_deny` with a
    literal vocabulary code at all -- `control_http.py` delegates its own
    request-shape checks to `http.py`'s shared `_check_object_shape`,
    already counted in that file's own pin above; `audit_query.py`'s
    `decode_cursor` raises a bare `ValueError` that `control_plane.py`'s
    own `_validate_audit_after` translates, already counted there) --
    pinned at 0 rather than omitted, so a scanner that silently matched
    nothing at all in `control_plane.py` either (a real bug: `fail`/
    `_deny` typo'd, or the wrong node type checked) would NOT be
    indistinguishable from the genuine 0 these two files have;
    `control_plane.py`'s own non-zero 13 is what proves the scanner
    actually visited real code."""
    counts = {module: len(_fail_call_sites(SRC / module)) for module in ("control_plane.py", "control_http.py", "audit_query.py")}
    assert counts == {"control_plane.py": 13, "control_http.py": 0, "audit_query.py": 0}, counts


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
    left behind). This scans `structured.py`'s and its extracted leaves'
    (`inmemory_predicate.py`, R-37 WP-1e; `identifier_rules.py`, R-37
    WP-1f; `paging.py`, R-37 WP-1h; `value_types.py`, R-37 WP-1i;
    `request_shape.py`, R-37 WP-3c; `mutation_binding.py`, R-37 WP-3f;
    `schema_binding.py`, R-37 WP-3g) FULL fail-message vocabulary (any
    code, not just the 3 in-scope ones
    -- see `_all_fail_messages`), so a match against a `NOT_FOUND`/
    `CONFLICT` message would be caught too."""
    in_memory_messages: set[str] = set()
    for module in ("structured.py", "inmemory_predicate.py", "identifier_rules.py", "paging.py", "value_types.py", "request_shape.py", "mutation_binding.py", "schema_binding.py"):
        in_memory_messages |= _all_fail_messages(SRC / module)
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


#: R-37 WP-1 fix (2026-09-14, corrective revision per reviewer ruling):
#: guard against the exact gap this WP found -- `postgres_value_domain.
#: py` was extracted as a `SCANNED_MODULES` sibling leaf on the MitateDB
#: side without being added to that peer's `SCANNED_MODULES`, so its
#: `ValidationError` denials silently dropped out of scan coverage.
#: `auth.py`/`credential_store.py`/`ops.py` are the ONLY r2db modules
#: under `src/r2db_api` (recursively -- `contract/` included) that carry
#: a vocabulary-code `fail(...)`/`_deny(code=...)` site while staying
#: out of `SCANNED_MODULES` -- the comment directly above `SCANNED_
#: MODULES` (not this file's own top-level module docstring, which never
#: names these three) already discloses them as an unaddressed,
#: deliberate scope limit (O-1's own audit did not enumerate them, and
#: no WP has extended the scan there). Each entry's value below is that
#: disclosure, quoted short, not a fresh justification invented here.
#: Any OTHER module with such a site is a real coverage gap, not a
#: disclosed one. Adding, removing, or renaming an entry here is a
#: `SCANNED_MODULES`-boundary change and requires the same supervisor
#: ruling any other change to that boundary would -- this set is not a
#: general escape hatch. LIMITATION (this scan's own coverage boundary,
#: not something this guard can close): a vocabulary-code denial newly
#: added INSIDE an already-excluded module is invisible to this whole
#: file -- excluding a module means its future edits are not audited
#: here at all, only that its CURRENT exclusion is not silently stale or
#: silently overlapping `SCANNED_MODULES`.
_DELIBERATELY_UNSCANNED_MODULES: dict[str, str] = {
    "auth.py": "SCANNED_MODULES comment above: O-1's own audit did not enumerate it, and no WP has extended the scan there",
    "credential_store.py": "SCANNED_MODULES comment above: O-1's own audit did not enumerate it, and no WP has extended the scan there",
    "ops.py": "SCANNED_MODULES comment above: O-1's own audit did not enumerate it, and no WP has extended the scan there",
}


def test_every_module_with_a_vocabulary_denial_is_accounted_for():
    """Regression guard for scan-coverage gaps: walks every `*.py` under
    `src/r2db_api`, RECURSIVELY (a nested package such as `contract/`
    can carry its own denial site just as easily as a top-level module
    can), and asserts that any module carrying >= 1 site this scanner's
    own `_fail_call_sites` counts is either a `SCANNED_MODULES` member or
    a key of the explicit, reasoned exclusion set above. Keys are POSIX
    relative paths from `src/r2db_api` -- identical to the plain
    filename for every current top-level entry, but able to name a
    nested file (e.g. `contract/__init__.py`) without inventing a
    different key shape for that case. Non-空振り: also asserts at least
    one module was actually found carrying a denial, so a scanner that
    silently matched nothing anywhere would not pass this test
    vacuously."""
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
    assert modules_with_denials, "no module under src/r2db_api carries a vocabulary-code denial call site -- the scanner is not visiting real code"
    assert unaccounted == [], f"module(s) with a vocabulary-code denial call site but not in SCANNED_MODULES or the explicit exclusion set: {unaccounted}"


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
    actually contain >= 1 vocabulary-code denial site right now, checked
    against the same live scanner the rest of this file uses -- a module
    that no longer does should be REMOVED from the exclusion set (there
    is nothing left to disclose an exception for), not left there as
    unexplained dead weight that could later hide a real gap."""
    for rel, reason in sorted(_DELIBERATELY_UNSCANNED_MODULES.items()):
        assert reason, f"{rel} has no reason recorded in _DELIBERATELY_UNSCANNED_MODULES"
        sites = _fail_call_sites(SRC / rel)
        assert sites, f"{rel} is on the exclusion set but carries no vocabulary-code denial site -- remove it"
