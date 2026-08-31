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
from pathlib import Path

_PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "src" / "mitatedb_api"

# Mirrors `spec/data-service-api.v1.json`'s own `limits.classes` array
# verbatim (this package has no runtime dependency on `spec/`, so this is a
# static, hand-mirrored copy -- any future contract addition to that
# vocabulary must be mirrored here too, or a legitimate new `limit_class`
# value would be rejected by this test as if it were a typo).
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
}


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
    assert len(findings) == 11, (
        f"expected exactly 11 ResourceLimitError(...) call sites (Q1-D11 count, design v1.5 §7: cell.py x5, "
        f"config.py x1 -- down from WP-5's original 9 after Q1-D11 reclassified 3 shape-boundary checks in "
        f"cell.py to ValidationError -- plus WP-3's own http.py x1, the ASGI request-byte-bound middleware's "
        f"real `request_bytes` enforcement, design v1.2 R-5 -- plus WP-4's own control_plane.py x3 (design v1.2 "
        f"R-6's three finite resource classes: `control_requests_per_minute`'s rate-limiter, `applications`'s "
        f"registration bound, `credentials_per_application`'s issuance bound) -- plus P35 WP-2's own cell.py x1 "
        f"(design docs/design/PHASE35_CROSS_ENTITY_AND_CONTRACT_130_V1.md §2 R-2, `ApplicationCell.transact`'s "
        f"new `batch_entities` distinct-collection-count bound)), found {len(findings)}: "
        f"{findings!r} -- if a new call site was added or removed intentionally, update this count in the same commit"
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
