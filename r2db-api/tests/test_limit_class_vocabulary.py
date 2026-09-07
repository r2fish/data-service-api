"""Static AST scan (Opus review, WP-3 follow-up, major M-1): every
`fail("LIMIT_EXCEEDED", ...)` call site anywhere in the `r2db_api` package
must declare a `limit_class` detail whose value is a member of the
contract's own `limits.classes` vocabulary (`spec/data-service-api.v1.json`,
subordinate ruling 7(B)). This is a regression guard against a *future*
`LIMIT_EXCEEDED` emission silently missing (or misspelling) this required
detail -- independent of any behavioral test exercising that specific code
path at runtime, which could stay green even if a brand-new call site never
supplied `limit_class` at all (no assertion would ever look for it there).

Design docs/design/DESTRUCTIVE_CONFIRMATION_V1.md v1.3 records this as the
disposition for review major M-1(a); M-1(b)'s own behavioral (runtime)
counterpart lives in `test_control_plane_service.py`/`test_foundation.py`
(a handful of representative call paths asserting the real response's
`limit_class`, not merely its presence-by-construction here).
"""
from __future__ import annotations

import ast
import json
from importlib import resources
from pathlib import Path

_PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "src" / "r2db_api"

# Mirrors `spec/data-service-api.v1.json`'s own `limits.classes` array
# verbatim. This test deliberately does NOT read the contract file at
# runtime (this package has no existing dependency on `spec/` at import
# time, and this is a static lint-style check, not a conformance test) --
# any future contract addition to that vocabulary must be mirrored here
# too, or a legitimate new `limit_class` value would be rejected by this
# test as if it were a typo.
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
    # Phase 4 WP-2(b) (design D-5, P4-D4 item 8, contract 1.4.0 subordinate
    # ruling 9): `audit_query`'s own separate pre-auth window.
    "audit_requests_per_minute",
    # Phase 9 WP-1 (contract 1.7.0, subordinate ruling 12, D-2 (7) = U-1
    # (β)): per-field `enum` member-count bound. Not yet enforced by this
    # foundation (WP-2a gives it real enforcement in the same commit that
    # flips `constraint_declarations` to `enabled`) -- mirrored here now so
    # this vocabulary test does not itself go stale the moment WP-1 lands.
    "enum_members",
}

# `ResourceLimits.check(self, kind: str, actual: int)` (limits.py) is the
# ONE call site in this codebase where `limit_class`'s value is not a
# string literal but the SAME `kind` parameter every caller of `.check(...)`
# passes as its own first positional argument (every real call site in this
# codebase passes a literal from `_CONTRACT_LIMIT_CLASSES` there, e.g.
# `limits.check("batch_items", len(operations))` -- not itself re-verified
# by this scanner, which only inspects `fail(...)` call sites). This is the
# one, narrow "known dynamic kind" allowance Opus review M-1 asked for:
# accepted only for this exact (class, function, parameter-name) triple,
# never as a general escape hatch for any bare name anywhere else.
_KNOWN_DYNAMIC_LIMIT_CLASS_NAMES = {("ResourceLimits", "check", "kind")}


class _LimitExceededCall:
    __slots__ = ("filename", "lineno", "class_name", "func_name", "details_node")

    def __init__(self, filename: str, lineno: int, class_name: str | None, func_name: str | None, details_node: ast.AST | None) -> None:
        self.filename = filename
        self.lineno = lineno
        self.class_name = class_name
        self.func_name = func_name
        self.details_node = details_node

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return f"{self.filename}:{self.lineno} ({self.class_name}.{self.func_name})"


class _Visitor(ast.NodeVisitor):
    def __init__(self, filename: str) -> None:
        self.filename = filename
        self.findings: list[_LimitExceededCall] = []
        self._class_stack: list[str] = []
        self._func_stack: list[str] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._class_stack.append(node.name)
        self.generic_visit(node)
        self._class_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._func_stack.append(node.name)
        self.generic_visit(node)
        self._func_stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef  # type: ignore[assignment]

    def visit_Call(self, node: ast.Call) -> None:
        self.generic_visit(node)
        func = node.func
        if not (isinstance(func, ast.Name) and func.id == "fail"):
            return
        if not node.args:
            return
        code_arg = node.args[0]
        if not (isinstance(code_arg, ast.Constant) and code_arg.value == "LIMIT_EXCEEDED"):
            return
        details_kw = next((kw for kw in node.keywords if kw.arg == "details"), None)
        self.findings.append(
            _LimitExceededCall(
                filename=self.filename,
                lineno=node.lineno,
                class_name=self._class_stack[-1] if self._class_stack else None,
                func_name=self._func_stack[-1] if self._func_stack else None,
                details_node=details_kw.value if details_kw is not None else None,
            )
        )


def _find_all_limit_exceeded_calls() -> list[_LimitExceededCall]:
    findings: list[_LimitExceededCall] = []
    for path in sorted(_PACKAGE_ROOT.glob("*.py")):
        tree = ast.parse(path.read_text(), filename=str(path))
        visitor = _Visitor(path.name)
        visitor.visit(tree)
        findings.extend(visitor.findings)
    return findings


def _dict_value_for_key(details_node: ast.AST, key: str) -> ast.AST | None:
    if not isinstance(details_node, ast.Dict):
        return None
    for key_node, value_node in zip(details_node.keys, details_node.values):
        if isinstance(key_node, ast.Constant) and key_node.value == key:
            return value_node
    return None


def test_every_limit_exceeded_call_site_declares_a_contract_limit_class() -> None:
    findings = _find_all_limit_exceeded_calls()
    # Vacuity guard (design principle 4, "skip is fail" applied to a static
    # scan too): if this ever finds zero call sites, either the scanner
    # itself is broken (wrong AST shape assumptions) or every `LIMIT_
    # EXCEEDED` emission was removed from the package -- both are findings,
    # not a silently-passing empty scan.
    assert len(findings) >= 15, (
        f"expected at least 15 LIMIT_EXCEEDED call sites (measured baseline: 19) -- found {len(findings)}, "
        "the AST scanner itself may be broken"
    )

    violations: list[str] = []
    for finding in findings:
        if finding.details_node is None:
            violations.append(f"{finding!r}: no `details=` keyword argument at all")
            continue
        value_node = _dict_value_for_key(finding.details_node, "limit_class")
        if value_node is None:
            violations.append(f"{finding!r}: details has no 'limit_class' key")
            continue
        if isinstance(value_node, ast.Constant) and isinstance(value_node.value, str):
            if value_node.value not in _CONTRACT_LIMIT_CLASSES:
                violations.append(
                    f"{finding!r}: limit_class={value_node.value!r} is not a member of "
                    f"the contract's limits.classes vocabulary"
                )
            continue
        if isinstance(value_node, ast.Name):
            triple = (finding.class_name, finding.func_name, value_node.id)
            if triple not in _KNOWN_DYNAMIC_LIMIT_CLASS_NAMES:
                violations.append(
                    f"{finding!r}: limit_class is the dynamic name {value_node.id!r}, which is not in the "
                    f"known-dynamic-kind allowlist {_KNOWN_DYNAMIC_LIMIT_CLASS_NAMES!r} -- either add it there "
                    "(after verifying every real call site passing this kind uses a contract-vocabulary "
                    "literal) or make this call site's limit_class a literal"
                )
            continue
        violations.append(f"{finding!r}: limit_class value is neither a string literal nor a known dynamic name ({ast.dump(value_node)})")

    assert not violations, "LIMIT_EXCEEDED call site(s) missing/invalid limit_class:\n" + "\n".join(violations)


def test_hand_maintained_mirror_equals_the_real_contract_limits_classes_vocabulary() -> None:
    """WP-1 review supplementary requirement (scratchpad wp2-extra-
    requirements.md item 3): `_CONTRACT_LIMIT_CLASSES` is a HAND-MAINTAINED
    mirror of the contract's own `limits.classes` array (this file's own
    header explains why it is not read live) -- a mirror with no equality
    check against its source can silently drift the moment the contract
    gains or renames a class and nobody updates this file's own literal.
    Reads the PACKAGED contract copy (`r2db_api.contract`, not `spec/`
    directly) -- the same source `test_http.py::
    test_packaged_contract_copy_is_byte_identical_to_spec_source_of_truth`
    already pins as byte-identical to `spec/`, so either source answers the
    same question here.
    """
    packaged = resources.files("r2db_api.contract").joinpath("data-service-api.v1.json").read_text()
    contract = json.loads(packaged)
    real_classes = set(contract["limits"]["classes"])
    assert _CONTRACT_LIMIT_CLASSES == real_classes, (
        f"_CONTRACT_LIMIT_CLASSES has drifted from the real contract's limits.classes: "
        f"missing={real_classes - _CONTRACT_LIMIT_CLASSES!r} extra={_CONTRACT_LIMIT_CLASSES - real_classes!r}"
    )
