"""Phase 6 WP-3 追補 (isomorphism table extension, supervisor ruling
2026-09-04): NEW file, same name as r2db-api's own `tests/test_control_
plane_store.py`. This peer's credential/control-credential store tests
already live spread across `tests/test_control_credentials.py`, `tests/
test_control_plane_postgres.py`, `tests/test_postgres.py`, and others --
this file does not attempt to consolidate them. It exists solely to hold
`test_authenticate_methods_use_the_shared_dummy_verifier_for_
unconditional_compare_digest`, the structural (white-box) timing-oracle
pin r2db-api registered under coordinator item 7(i) (2026-09-04 review),
under the SAME file name and SAME function name r2db-api uses -- this
peer's own realization of contract 1.6.0 subordinate ruling 11 item 1's
shared bearer-locator obligation (`credential_wire.compose_bearer_
locator`/`split_bearer_locator`) carries the identical timing-oracle
hazard r2db-api's own WP-2 rework closed (coordinator item 7(i)/m-4): an
unknown `credential_id` must not return via a measurably cheaper path
than a known one whose secret merely fails to match (SI-10). This test
is pinned isomorphic to r2db-api's own copy
(`tests/test_audit_query.py::_ISOMORPHIC_TARGETS`, the `tests/test_
control_plane_store.py` row) -- see this module's own `_TIMING_PIN_
TARGETS` comment for why the {filename: {class names}} map is kept
OUTSIDE the pinned function body.
"""
from __future__ import annotations

from pathlib import Path


# ---------------------------------------------------------------------------
# Phase 6 WP-3 追補 (isomorphism table extension, supervisor ruling
# 2026-09-04): `test_authenticate_methods_use_the_shared_dummy_verifier_
# for_unconditional_compare_digest` below is a row in `tests/test_audit_
# query.py::_ISOMORPHIC_TARGETS` (pinned isomorphic to r2db-api's own
# same-named test in its own `tests/test_control_plane_store.py`). The
# two peers' `authenticate` implementations live under DIFFERENT file/
# class names -- r2db-api's own 4 live across 2 files (`auth.py`'s 2
# in-memory classes, `credential_store.py`'s 2 Postgres classes), this
# peer's own 4 live across 4 files (one class per file: `auth.py`'s
# `CredentialStore`, `control_auth.py`'s `ControlCredentialStore`,
# `credential_store_postgres.py`'s `PostgresCredentialStore`, `control_
# credential_store_postgres.py`'s `PostgresControlCredentialStore`) -- a
# real per-peer module-layout difference, not a naming accident, and NOT
# something package-name substitution alone can normalize away. This
# {filename: {class names}} map is therefore kept HERE, at module level,
# OUTSIDE the pinned function body, so the function itself stays byte-
# identical (after normalization) across both peers; only this table
# differs per peer.
# ---------------------------------------------------------------------------
_TIMING_PIN_TARGETS: dict[str, set[str]] = {
    "auth.py": {"CredentialStore"},
    "control_auth.py": {"ControlCredentialStore"},
    "credential_store_postgres.py": {"PostgresCredentialStore"},
    "control_credential_store_postgres.py": {"PostgresControlCredentialStore"},
}


def test_authenticate_methods_use_the_shared_dummy_verifier_for_unconditional_compare_digest() -> None:
    """Coordinator item 7(i) (reviewer O3): a structural pin for a property
    a functional-outcome test cannot express without flaky timing
    measurement -- all 4 `authenticate` implementations (`auth.py`'s two
    in-memory stores, `credential_store.py`'s two Postgres stores) must
    reference `_DUMMY_VERIFIER` so `compare_digest` runs unconditionally
    (same cost whether or not the presented `credential_id` names a real
    row), closing the "does this credential_id exist" timing oracle. This
    is a source-text pin, not a timing measurement -- a real timing attack
    test would be flaky by nature and is out of this WP's scope; this pin
    at least prevents a future edit from silently reintroducing the
    short-circuit form without touching this text."""
    # Supervisor rework (2026-09-04, audit of the WP-2 rework, item 7(i)):
    # the previous form of this pin only counted occurrences of the
    # `_DUMMY_VERIFIER` token per file (>= 2), which stayed green even when
    # both use sites in a file were reverted to the short-circuit form
    # (definition + comment still made the count) -- measured by the
    # auditor. This form reads the AST of each of the four
    # `authenticate` methods and requires, per method, at least one
    # `hmac.compare_digest(...)` call that is NOT nested inside any `if`
    # whose test mentions the looked-up row (`record` / `row`) -- i.e. the
    # digest comparison must be reached unconditionally, whether or not
    # the presented locator named a real row. Reverting any ONE of the
    # four methods to `if record is None: fail(...)` before the
    # comparison turns this red (measured, one method at a time).
    import ast

    src_root = Path(__file__).resolve().parents[1] / "src" / "mitatedb_api"
    targets = _TIMING_PIN_TARGETS
    row_names = {"record", "row"}

    def _mentions_row(node: ast.AST) -> bool:
        return any(isinstance(n, ast.Name) and n.id in row_names for n in ast.walk(node))

    def _unconditional_compare_digest(fn: ast.FunctionDef) -> bool:
        # Walk with an explicit parent chain so each Call knows the `if`
        # tests it sits under.
        found = False

        def visit(node: ast.AST, guarding: list[ast.If]) -> None:
            nonlocal found
            if isinstance(node, ast.Call):
                f = node.func
                is_cd = (isinstance(f, ast.Attribute) and f.attr == "compare_digest") or (isinstance(f, ast.Name) and f.id == "compare_digest")
                if is_cd and not any(_mentions_row(g.test) for g in guarding):
                    found = True
            for child in ast.iter_child_nodes(node):
                if isinstance(node, ast.If) and child in node.body + node.orelse:
                    visit(child, guarding + [node])
                else:
                    visit(child, guarding)

        visit(fn, [])
        if not found:
            return False
        # Ordering: an early `if record is None: fail(...)` BEFORE the
        # comparison is the same timing oracle in a different syntactic
        # coat (the digest is never computed for an unknown locator), so
        # no `if` whose test mentions the row may precede the first
        # compare_digest call in source order.
        first_cd = min(
            n.lineno for n in ast.walk(fn)
            if isinstance(n, ast.Call) and (
                (isinstance(n.func, ast.Attribute) and n.func.attr == "compare_digest")
                or (isinstance(n.func, ast.Name) and n.func.id == "compare_digest")
            )
        )
        early_row_ifs = [n for n in ast.walk(fn) if isinstance(n, ast.If) and n.lineno < first_cd and _mentions_row(n.test)]
        return not early_row_ifs

    checked: list[str] = []
    for filename, class_names in targets.items():
        tree = ast.parse((src_root / filename).read_text())
        for cls in [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name in class_names]:
            fns = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "authenticate"]
            assert len(fns) == 1, f"{filename}::{cls.name} must define exactly one authenticate()"
            assert _unconditional_compare_digest(fns[0]), (
                f"{filename}::{cls.name}.authenticate() must call hmac.compare_digest unconditionally "
                f"(not only inside an `if` that depends on whether the locator named a row)"
            )
            checked.append(f"{filename}::{cls.name}")
    assert len(checked) == 4, checked
