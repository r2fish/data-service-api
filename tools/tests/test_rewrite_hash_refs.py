"""tools/tests/test_rewrite_hash_refs.py -- pytest wrapper around
tools/rewrite_hash_refs.py's own scenarios (WP-9).

Deliberately NOT under `conformance-tests/` and NOT discoverable by the root
suite: `tools/` is not in pyproject.toml's `[tool.pytest.ini_options]
testpaths`, and adding it there is an undesigned extension outside WP-9's
scope (常設規律 5 -- design-outside extensions get raised before
implementation, not slipped into a shared config). This file exists so the
same scenarios can also be run the ordinary pytest way (`pytest
tools/tests/test_rewrite_hash_refs.py`) during manual/CI-adjacent
verification; the gate-safe, always-available check is the script's own
`--self-test` (see rewrite_hash_refs.py's module docstring and WP-9 report).

Run directly:
    ./.venv/bin/python -m pytest tools/tests/test_rewrite_hash_refs.py -q
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_MODULE_PATH = Path(__file__).resolve().parents[1] / "rewrite_hash_refs.py"
_spec = importlib.util.spec_from_file_location("rewrite_hash_refs", _MODULE_PATH)
rhr = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("rewrite_hash_refs", rhr)
_spec.loader.exec_module(rhr)  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Shared synthetic commit-map. Every short prefix mixes a digit and a
# letter -- an all-letter run ("aaaaaaa") is excluded from candidacy
# entirely (has_digit_and_alpha) and would never reach classify_token.
# ---------------------------------------------------------------------------
OLD_A = "aa11111" + "a" * 33
NEW_A = "bb22222" + "c" * 33
OLD_B = "aa11111" + "b" * 33  # shares the 7-char prefix "aa11111" with A
NEW_B = "cc33333" + "d" * 33
OLD_C = "de1adb0" + "c" * 33  # unique 8-char prefix "de1adb0" among A/B/C
NEW_C = "fe2edf0" + "e" * 33


@pytest.fixture()
def commit_map(tmp_path: Path) -> list[tuple[str, str]]:
    p = tmp_path / "commit-map.txt"
    p.write_text(f"old new\n{OLD_A} {NEW_A}\n{OLD_B} {NEW_B}\n{OLD_C} {NEW_C}\n", encoding="utf-8")
    return rhr.parse_commit_map(str(p))


def test_commit_map_parses_three_pairs(commit_map):
    assert len(commit_map) == 3


def test_unique_prefix_is_replaced(commit_map):
    findings: list = []
    new_text, changed = rhr.process_text(
        "doc.md", "see commit de1adb0 for details\n", commit_map, [], False, apply=True, findings=findings
    )
    replaced = [f for f in findings if f.verdict == "replaced"]
    assert len(replaced) == 1
    assert replaced[0].token == "de1adb0"
    assert "fe2edf0" in new_text
    assert "de1adb0" not in new_text
    assert changed is True


def test_non_unique_prefix_is_ambiguous_and_untouched(commit_map):
    """Mutation 1 target: if classify_token's uniqueness check is removed
    (picks the first front-match unconditionally), this goes red -- the
    non-unique short hash would be silently 'replaced' instead of flagged
    ambiguous, and the source text would change."""
    findings: list = []
    new_text, changed = rhr.process_text(
        "doc.md", "see commit aa11111 for details\n", commit_map, [], False, apply=True, findings=findings
    )
    ambiguous = [f for f in findings if f.verdict == "ambiguous"]
    assert len(ambiguous) == 1
    assert ambiguous[0].token == "aa11111"
    assert changed is False
    assert "aa11111" in new_text


def test_token_absent_from_commit_map_is_unmatched(commit_map):
    findings: list = []
    rhr.process_text(
        "doc.md", "random token 0123abc appears here\n", commit_map, [], False, apply=False, findings=findings
    )
    unmatched = [f for f in findings if f.verdict == "unmatched"]
    assert len(unmatched) == 1
    assert unmatched[0].token == "0123abc"


def test_uuid_fragment_is_allowed(commit_map):
    findings: list = []
    rhr.process_text(
        "doc.md",
        "uuid 1a2b3c4d-5e6f-7a8b-9c0d-1e2f3a4b5c6d here\n",
        commit_map, [], False, apply=False, findings=findings,
    )
    allowed = {f.token: f.reason for f in findings if f.verdict == "allowed"}
    assert allowed.get("1a2b3c4d") == "uuid_fragment"
    assert allowed.get("1e2f3a4b5c6d") == "uuid_fragment"
    assert {f.verdict for f in findings} == {"allowed"}


def test_hyphenated_credential_id_hex_suffix_is_allowed(commit_map):
    findings: list = []
    rhr.process_text(
        "doc.md", "id crd-0123456789fedcba too\n", commit_map, [], False, apply=False, findings=findings
    )
    assert len(findings) == 1
    assert findings[0].verdict == "allowed"
    assert findings[0].reason == "credential_id_prefix"


def test_user_allow_pattern_short_circuits_lookup(commit_map):
    patterns = rhr.compile_user_allow_patterns(["feedbee1"], None)
    findings: list = []
    rhr.process_text(
        "doc.md", "synthetic id feedbee1 must not resolve\n", commit_map, patterns, False, apply=False, findings=findings
    )
    assert len(findings) == 1
    assert findings[0].verdict == "allowed"
    assert findings[0].reason.startswith("allow:")


def _residual_tokens(text: str, commit_map) -> list[str]:
    out = []
    for raw_line in text.splitlines(keepends=True):
        for m in rhr.HEX_TOKEN_RE.finditer(raw_line):
            tok = m.group(0)
            if not rhr.has_digit_and_alpha(tok):
                continue
            if rhr.default_allow_reason(raw_line, m.start(), m.end(), tok):
                continue
            if rhr.residual_matches(tok, commit_map) > 0:
                out.append(tok)
    return out


def test_verify_detects_residual_old_sha(commit_map):
    """Mutation 2 target: if residual_matches is neutralized (always
    returns 0), this goes red -- an un-rewritten old-sha reference would be
    reported as clean."""
    assert "de1adb0" in _residual_tokens("still references de1adb0, unfortunately\n", commit_map)


def test_verify_reports_zero_residual_for_rewritten_document(commit_map):
    assert _residual_tokens("now references fe2edf0, all good\n", commit_map) == []


@pytest.mark.parametrize(
    "token,expected",
    [("1234567", False), ("abcdefg", False), ("a1b2c3d", True)],
)
def test_candidate_requires_digit_and_alpha(token, expected):
    assert rhr.has_digit_and_alpha(token) is expected


def test_long_hex_digest_allow_reason_direct():
    """HEX_TOKEN_RE's own \\b anchors mean it can never itself extract a
    >40-char contiguous lowercase-hex run as a <=40-char token (both ends of
    such a run would need a genuine word/non-word transition, which a
    homogeneous hex run does not have in its interior). Exercised directly
    against a synthetic 64-char digest line to prove the function's own
    logic rather than relying on an unreachable path."""
    digest = ("e3b0c44298fc1c14" * 4)[:64]
    line = f"sha256:{digest}\n"
    start = line.index(digest)
    end = start + 40
    assert rhr.default_allow_reason(line, start, end, digest[:40]) == "long_hex_digest"


def test_self_test_entry_point_passes():
    assert rhr.self_test() == 0
