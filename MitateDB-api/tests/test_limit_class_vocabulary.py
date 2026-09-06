"""Static AST scan (WP-5, mirrors r2db-api's own `test_limit_class_
vocabulary.py`, design docs/design/DESTRUCTIVE_CONFIRMATION_V1.md R-5):
every `ResourceLimitError(...)` call site anywhere in the `mitatedb_api`
package must pass a `limit_class` keyword whose value is a member of the
contract's own `limits.classes` vocabulary (`spec/data-service-api.v1.json`,
subordinate ruling 7(B)).

Unlike r2db-api's own scan, this one does not need to check for
`limit_class`'s bare *presence* -- `errors.ResourceLimitError.__init__`
declares it a required keyword-only parameter with no default, so Python
itself already refuses any call site omitting it (a `TypeError` at raise
time, not merely an untested gap). What Python's own type system cannot
enforce is that the *value* supplied is a genuine member of the contract's
15-class vocabulary rather than a typo or an invented word -- that is what
this scan is for, applied independently of whether any behavioral test
happens to exercise that exact call site at runtime.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

_PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "src" / "mitatedb_api"
_CONTRACT_PATH = Path(__file__).resolve().parents[2] / "spec" / "data-service-api.v1.json"

# Mirrors `spec/data-service-api.v1.json`'s own `limits.classes` array
# verbatim (this package has no runtime dependency on `spec/`, so this is a
# static, hand-mirrored copy -- any future contract addition to that
# vocabulary must be mirrored here too, or a legitimate new `limit_class`
# value would be rejected by this test as if it were a typo). Phase 4
# WP-3(b) (scratchpad/wp2-extra-requirements.md item 4: "手写しミラーの
# drift を構造的に防ぐ"): `test_hand_maintained_mirror_equals_the_real_
# contract_limits_classes_vocabulary` below fixes this set against the
# REAL, packaged contract file directly (an equality test, not a one-way
# membership check), so a future contract addition/removal that this
# mirror is not updated to match is caught here rather than silently
# under- or over-accepting.
_CONTRACT_LIMIT_CLASSES = {
    "request_bytes",
    "batch_items",
    "batch_entities",
    "result_items",
    "query_complexity",
    "execution_ms",
    "concurrency",
    "requests_per_minute",
    "schema_objects",
    "operation_depth",
    "idempotency_entries",
    "idempotency_retention_ms",
    "applications",
    "credentials_per_application",
    "control_requests_per_minute",
    # Phase 4 WP-3(b) (design D-5, P4-D4 item 8): `audit_query`'s own
    # dedicated pre-auth window (`ControlPlaneService.check_audit_rate`/
    # `_check_audit_rate`).
    "audit_requests_per_minute",
}


def test_hand_maintained_mirror_equals_the_real_contract_limits_classes_vocabulary() -> None:
    contract = json.loads(_CONTRACT_PATH.read_text())
    real = set(contract["limits"]["classes"])
    assert _CONTRACT_LIMIT_CLASSES == real, (
        f"_CONTRACT_LIMIT_CLASSES has drifted from spec/data-service-api.v1.json's own limits.classes: "
        f"missing={real - _CONTRACT_LIMIT_CLASSES!r} extra={_CONTRACT_LIMIT_CLASSES - real!r}"
    )


class _Finding:
    __slots__ = ("filename", "lineno", "limit_class_node")

    def __init__(self, filename: str, lineno: int, limit_class_node: ast.AST | None) -> None:
        self.filename = filename
        self.lineno = lineno
        self.limit_class_node = limit_class_node

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return f"{self.filename}:{self.lineno}"


class _Visitor(ast.NodeVisitor):
    def __init__(self, filename: str) -> None:
        self.filename = filename
        self.findings: list[_Finding] = []

    def visit_Call(self, node: ast.Call) -> None:
        self.generic_visit(node)
        func = node.func
        name = func.id if isinstance(func, ast.Name) else (func.attr if isinstance(func, ast.Attribute) else None)
        if name != "ResourceLimitError":
            return
        limit_class_kw = next((kw for kw in node.keywords if kw.arg == "limit_class"), None)
        self.findings.append(
            _Finding(filename=self.filename, lineno=node.lineno, limit_class_node=limit_class_kw.value if limit_class_kw is not None else None)
        )


def _find_all_resource_limit_error_calls() -> list[_Finding]:
    findings: list[_Finding] = []
    for path in sorted(_PACKAGE_ROOT.glob("*.py")):
        tree = ast.parse(path.read_text(), filename=str(path))
        visitor = _Visitor(path.name)
        visitor.visit(tree)
        findings.extend(visitor.findings)
    return findings


def test_every_resource_limit_error_call_site_declares_a_contract_limit_class() -> None:
    findings = _find_all_resource_limit_error_calls()
    # Vacuity guard (design principle 4, "skip is fail" applied to a static
    # scan too): if this ever finds zero call sites, either the scanner
    # itself is broken (wrong AST shape assumptions -- e.g. `cell.py`
    # renaming the exception class) or every `ResourceLimitError` call site
    # was removed, either of which this test must notice rather than
    # vacuously pass.
    assert findings, "found zero ResourceLimitError(...) call sites in mitatedb_api -- scanner or package changed"
    assert len(findings) == 28, (
        f"expected exactly 28 ResourceLimitError(...) call sites (pre-Phase-8 count was 12: Q1-D11's cell.py x5 + "
        f"config.py x1 + WP-3's http.py x1 + WP-4's control_plane.py x3 + P35 WP-2's cell.py x1 + Phase 4 "
        f"WP-3(b)'s control_plane.py x1 -- see git history for that count's own full breakdown) -- Phase 8 WP-1a "
        f"(design docs/design/PHASE8_EFFECTIVE_BOUNDS_AND_HYGIENE_V1.md D-1, L7-1) adds 13 new call sites for the "
        f"4 previously-`unavailable` application-plane classes this WP wires up real enforcement for: cell.py x6 "
        f"(`_measure_request_bytes` x3 -- container-count/dict/list early-reject and total-overflow -- `_check_"
        f"operation_depth` x1, `_LimitStateHolder.acquire_rate` x1 `requests_per_minute`, `_LimitStateHolder."
        f"concurrency_slot` x1 `concurrency`), backend_sqlite.py x1 (`_check_deadline`'s app-side `execution_ms` "
        f"wall-clock check), backend_postgres.py x6 (`insert`/`read`/`update`/`delete`/`create_collection`/"
        f"`add_field`, each mapping a real `QueryCanceled`/`LockNotAvailable` to `execution_ms`). "
        f"12 + 13 = 25 -- plus WP-1a REWORK 1's own 3 more (裁定 2, 監督裁定 2026-09-06): backend_postgres.py x3 "
        f"(`insert_in_transaction`/`update_in_transaction`/`delete_in_transaction`, the SAME `QueryCanceled`/"
        f"`LockNotAvailable` -> `execution_ms` mapping the 6 standalone methods above already had, previously "
        f"missing from the transact-batch path every HTTP mutation actually uses). 25 + 3 = 28, "
        f"found {len(findings)}: {findings!r} -- if a new call site was added or removed "
        f"intentionally, update this count in the same commit"
    )

    violations = []
    for finding in findings:
        node = finding.limit_class_node
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
            violations.append(f"{finding!r}: limit_class is not a string literal ({ast.dump(node) if node is not None else None!r})")
            continue
        if node.value not in _CONTRACT_LIMIT_CLASSES:
            violations.append(f"{finding!r}: limit_class={node.value!r} is not a member of limits.classes")
    assert not violations, "ResourceLimitError call site(s) with a non-contract limit_class:\n" + "\n".join(violations)
