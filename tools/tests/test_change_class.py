"""tools/tests/test_change_class.py -- pytest wrapper around
tools/change_class.py's own path-classification rules (WP-4).

Deliberately NOT under `conformance-tests/` and NOT discoverable by the root
suite: `tools/` is not in pyproject.toml's `[tool.pytest.ini_options]
testpaths` (same convention as tools/tests/test_check_doc_refs.py and
tools/tests/test_rewrite_hash_refs.py -- see those files' own docstrings).

Test function names below are the literal test ids from the work order's
completion-condition table (docs/work-orders/
WORK_ORDER_DEVELOPMENT_PROCESS_HYGIENE_V1.md WP-4, "完了条件 4-1〜4-9"):
each `test_...` name IS the id the manifest names for that row, so the
manifest and this file stay in a 1:1 correspondence a reader can check by
name alone, with no renaming table in between.

Run directly:
    ./.venv/bin/python -m pytest tools/tests/test_change_class.py -q
"""
from __future__ import annotations

import importlib.util
import io
import sys
from pathlib import Path

_MODULE_PATH = Path(__file__).resolve().parents[1] / "change_class.py"
_spec = importlib.util.spec_from_file_location("change_class", _MODULE_PATH)
cc = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("change_class", cc)
_spec.loader.exec_module(cc)  # type: ignore[union-attr]


def _run(paths: list[str]) -> tuple[int, str]:
    out = io.StringIO()
    code = cc.run(paths, out=out)
    return code, out.getvalue()


def _header(output: str) -> tuple[str, str]:
    lines = output.splitlines()
    assert lines[0].startswith("class=")
    assert lines[1].startswith("conformance_required=")
    return lines[0].split("=", 1)[1], lines[1].split("=", 1)[1]


# ---------------------------------------------------------------------------
# 4-1 -- a push touching only ordinary `.md` paths (no D/C exception) is
# Class A, and conformance is NOT required.
# Mutation (manifest 4-1): drop the A rule's extension check so `.md` also
# falls to B -- turns this test's expected `class=A` into `class=B`.
# ---------------------------------------------------------------------------
def test_markdown_only_is_class_a():
    code, out = _run(["README.md", "docs/design/SOME_NOTE.md"])
    assert code == 0
    klass, conformance_required = _header(out)
    assert klass == "A", out
    assert conformance_required == "false", out


# ---------------------------------------------------------------------------
# 4-2 -- docs/security/public-repository-policy.md (the public-repository
# gate document) is Class D even though it ends in `.md`.
# Mutation (manifest 4-2): drop this path from the D pattern table -- the
# path then falls through to the `.md` extension rule and is misclassified
# A.
# ---------------------------------------------------------------------------
def test_public_repository_policy_is_class_d():
    code, out = _run(["docs/security/public-repository-policy.md"])
    assert code == 0
    klass, conformance_required = _header(out)
    assert klass == "D", out
    assert conformance_required == "true", out


# ---------------------------------------------------------------------------
# 4-3 -- CLAUDE.md is Class D (design D-4 item 1's own path list), even
# though it ends in `.md`.
# Mutation (manifest 4-3): drop "CLAUDE.md" from the D pattern table -- it
# then falls through to the `.md` extension rule and is misclassified A.
# ---------------------------------------------------------------------------
def test_claude_md_is_class_d():
    code, out = _run(["CLAUDE.md"])
    assert code == 0
    klass, conformance_required = _header(out)
    assert klass == "D", out
    assert conformance_required == "true", out


# ---------------------------------------------------------------------------
# 4-4 -- a `.md` file under spec/ is Class C, not A: the directory rule
# must be checked before the extension rule.
# Mutation (manifest 4-4): reorder the rule evaluation so the extension
# check (A) runs before the C check -- spec/*.md then becomes A.
# ---------------------------------------------------------------------------
def test_spec_markdown_is_class_c():
    code, out = _run(["spec/CCR_DISPOSITION.md"])
    assert code == 0
    klass, conformance_required = _header(out)
    assert klass == "C", out
    assert conformance_required == "true", out


# ---------------------------------------------------------------------------
# 4-5 -- a non-`.md` file under docs/ (no D/C exception applies) is Class B,
# not A -- the extension rule is an ALLOWLIST of `.md`, not a denylist of
# a handful of known-heavy extensions, and not "everything under docs/".
# Mutation (manifest 4-5): broaden the A rule to "everything under docs/"
# -- every non-D/C path under docs/ would then also be misclassified A.
# ---------------------------------------------------------------------------
def test_non_markdown_under_docs_is_class_b():
    code, out = _run(["docs/design/diagram.svg"])
    assert code == 0
    klass, conformance_required = _header(out)
    assert klass == "B", out
    assert conformance_required == "true", out


# ---------------------------------------------------------------------------
# 4-6 -- a push touching paths of several classes takes the HEAVIEST one.
# Mutation (manifest 4-6): aggregate by "the first file's class" instead of
# the heaviest -- a mixed push would then report whichever class the first
# listed path happens to carry, not the heaviest.
# ---------------------------------------------------------------------------
def test_mixed_paths_take_the_heaviest_class():
    code, out = _run(
        [
            "docs/design/SOME_NOTE.md",
            "tools/change_class.py",
            "spec/CCR_DISPOSITION.md",
            "security/SECURITY_INVARIANTS_V1.md",
        ]
    )
    assert code == 0
    klass, conformance_required = _header(out)
    assert klass == "D", out
    assert conformance_required == "true", out


# ---------------------------------------------------------------------------
# 4-7 -- an empty path list (an empty push) is "unknown", conformance
# required -- the safe-side default, not "nothing changed, therefore A".
# Mutation (manifest 4-7): make the empty-input branch print `class=A` /
# `conformance_required=false`.
# ---------------------------------------------------------------------------
def test_empty_input_is_unknown_and_requires_conformance():
    code, out = _run([])
    assert code == 0
    klass, conformance_required = _header(out)
    assert klass == "unknown", out
    assert conformance_required == "true", out


# ---------------------------------------------------------------------------
# 4-8 -- `conformance_required=false` happens ONLY when the overall class
# is A: B, C, D, and unknown are all `true`. This is a distinct condition
# from 4-1/4-7 (which each check exactly one class's own required-flag) --
# it fixes the "false" case as A-exclusive across every OTHER class in one
# assertion, so a mutation narrowing the false-case check (e.g. "false for
# A or B") cannot hide behind a single-class test passing.
# Mutation (manifest 4-8): let `conformance_required` also come out
# `false` for class B -- this test's B case then reads `false` where
# `true` is expected.
# ---------------------------------------------------------------------------
def test_only_class_a_skips_conformance():
    cases = [
        (["README.md"], "A", "false"),
        (["docs/design/diagram.svg"], "B", "true"),
        (["spec/CCR_DISPOSITION.md"], "C", "true"),
        (["CLAUDE.md"], "D", "true"),
        ([], "unknown", "true"),
    ]
    for paths, expected_class, expected_required in cases:
        code, out = _run(paths)
        assert code == 0
        klass, conformance_required = _header(out)
        assert klass == expected_class, out
        assert conformance_required == expected_required, out


# ---------------------------------------------------------------------------
# 4-9 -- lines from the 3rd line on are one `<class> <path>` entry per
# input path (blank lines dropped), stably sorted by path: passing the
# SAME set of paths in a different order produces the SAME lines from the
# 3rd line on.
# Mutation (manifest 4-9): drop the sort in the per-path listing (emit in
# input order) -- the two orderings below would then produce two
# DIFFERENT line-3-onward listings instead of the same one.
# ---------------------------------------------------------------------------
def test_output_lines_are_stably_sorted():
    order1 = ["b/two.py", "", "a/one.md"]
    order2 = ["a/one.md", "b/two.py", ""]
    code1, out1 = _run(order1)
    code2, out2 = _run(order2)
    assert code1 == 0, out1
    assert code2 == 0, out2
    lines1 = out1.splitlines()[2:]
    lines2 = out2.splitlines()[2:]
    assert lines1 == ["A a/one.md", "B b/two.py"], out1
    assert lines2 == lines1, out2


# ---------------------------------------------------------------------------
# Additional coverage (not a separate 4-1..4-9 completion condition, but
# cheap and directly exercises the module docstring's own claim that the
# `.md` extension check is exact-case): a path ending in `.MD` (uppercase)
# does not match the A rule and falls through to B.
# Mutation: fold case in the extension check (`path.endswith(".md")` ->
# `path.lower().endswith(".md")`) -- an uppercase-suffixed path would then
# also become A.
# ---------------------------------------------------------------------------
def test_uppercase_extension_is_not_class_a():
    code, out = _run(["docs/design/WEIRDLY_NAMED.MD"])
    assert code == 0
    klass, conformance_required = _header(out)
    assert klass == "B", out
    assert conformance_required == "true", out


# ---------------------------------------------------------------------------
# Additional coverage (review R-3): a path that merely CONTAINS ".md" as a
# substring, without ending in it, must not be graded as Class A -- the
# extension check is a suffix test, not a substring test. This guards
# against a backup/generated artifact of a markdown file (e.g. a `.bak` or
# `.mdx` sibling) being treated as documentation-only and silently
# skipping conformance.
# Mutation (review R-3, mutation i): change `path.endswith(".md")` to
# `".md" in path` -- both paths below would then also become Class A.
# ---------------------------------------------------------------------------
def test_md_substring_paths_are_not_class_a():
    code, out = _run(["docs/foo.md.bak", "docs/notes.mdx"])
    assert code == 0
    klass, conformance_required = _header(out)
    assert klass == "B", out
    assert conformance_required == "true", out


# ---------------------------------------------------------------------------
# Additional coverage (not a separate 4-1..4-9 completion condition, but
# cheap and directly exercises the module docstring's own claim about the
# MitateDB-api foundation.json file): a non-contract JSON file that merely
# LOOKS similar to the two packaged contract copies must stay Class B.
# ---------------------------------------------------------------------------
def test_mitatedb_foundation_json_is_not_a_contract_copy():
    code, out = _run(["MitateDB-api/contracts/foundation.json"])
    assert code == 0
    klass, _conformance_required = _header(out)
    assert klass == "B", out


# ---------------------------------------------------------------------------
# The two peer-packaged contract JSON copies (outside spec/) are Class C.
# ---------------------------------------------------------------------------
def test_packaged_contract_copies_are_class_c():
    code, out = _run(
        [
            "r2db-api/src/r2db_api/contract/data-service-api.v1.json",
            "MitateDB-api/src/mitatedb_api/contract/data-service-api.v1.json",
        ]
    )
    assert code == 0
    klass, conformance_required = _header(out)
    assert klass == "C", out
    assert conformance_required == "true", out
