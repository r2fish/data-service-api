"""Phase 8 WP-4 (design docs/design/PHASE8_EFFECTIVE_BOUNDS_AND_HYGIENE_V1.md
D-5 decision 5, 実装の形 (c), work order docs/work-orders/
WORK_ORDER_PHASE8_EFFECTIVE_BOUNDS_V1.md §2 WP-4 実装の指示 (c)): a static
regex scan proving the exact ONE proposition the design states -- "配備ス
クリプトと両 peer の ops.py が、secret を子プロセスの argv に載せない"
(`ps` から見える形で secret が渡っていないこと。環境変数経由で渡すことは
違反ではない).

The regex, `SECRET_WORD`, `COMMENT`, and `ENV_ASSIGN` below are copied
VERBATIM from design §3 D-5 実装の形 (c) -- not paraphrased, not
re-derived (常設規律 4).

Scope of what a GREEN run here means (design's own disclosure, repeated
here per §2 WP-4 実装の指示 (c)): this rule's green means only that these
THREE PATTERNS are absent from the current tree -- (i) false positives: a
`--password` flag immediately followed by a positional argument (e.g.
`createuser --password <role>`) is indistinguishable from one followed by
a value, and gets flagged anyway; (ii) false negatives: command
substitution, variable/array expansion, and an argument split across
multiple lines are none of them detectable by a line-level regex. This is
NOT a proof that no secret ever reaches an argv anywhere in this
repository -- only that these three literal shapes do not appear in the
scanned files today."""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

#: design §3 D-5 実装の形 (c), verbatim.
SECRET_WORD = r"(?:password|passwd|pepper|secret|token|api_key|key)"

RULE = re.compile(
    r"(?:^|[\s;|&])-v[\s=][A-Za-z0-9_]*" + SECRET_WORD + r"\s*="   # (a) psql -v <...secret...>=
    r"|--password(?:=\S|[ \t]+[^-\s])"                              # (b) 値を伴う --password のみ
    r"|://[^/\s]*:[^@/\s]+@",                                       # (c) URL の userinfo
    re.IGNORECASE,
)
COMMENT = re.compile(r"^\s*#")
ENV_ASSIGN = re.compile(r"^\s*(?:export\s+)?[A-Za-z_][A-Za-z0-9_]*=")


def _scan_targets() -> list[Path]:
    """design's own scope: every file under `r2db-api/deploy/scripts/`,
    plus both peers' own `ops.py` -- 7 files on the current tree (5
    deploy scripts + 2 `ops.py`, both counted in the design's own
    prototype run)."""
    targets = sorted((REPO_ROOT / "r2db-api" / "deploy" / "scripts").glob("*"))
    targets = [p for p in targets if p.is_file()]
    targets.append(REPO_ROOT / "r2db-api" / "src" / "r2db_api" / "ops.py")
    targets.append(REPO_ROOT / "MitateDB-api" / "src" / "mitatedb_api" / "ops.py")
    return targets


def scan_file(path: Path) -> list[tuple[int, str]]:
    """Returns `(line_number, line_text)` for every line the rule flags --
    comment lines and lines that are themselves a plain env-var assignment
    (`export X=...`/`X=...`) are excluded from the scan (design's own
    "行頭の env 代入とコメント行は走査対象から除外する")."""
    hits: list[tuple[int, str]] = []
    for lineno, line in enumerate(path.read_text().splitlines(), start=1):
        if COMMENT.match(line) or ENV_ASSIGN.match(line):
            continue
        if RULE.search(line):
            hits.append((lineno, line))
    return hits


def test_deploy_secret_argv_scan_flags_zero_hits() -> None:
    """完了条件 4: flagged 0 件。非空振り: 走査対象ファイルが 1 件以上ある
    ことをまず assert する (`files scanned` が 0 のまま「hits 0 で緑」にな
    る形にしない)."""
    targets = _scan_targets()
    assert len(targets) >= 1, "no files scanned -- a vacuous run, not a real check"
    for path in targets:
        assert path.exists(), f"scan target does not exist: {path}"

    all_hits: list[str] = []
    for path in targets:
        for lineno, line in scan_file(path):
            all_hits.append(f"{path.relative_to(REPO_ROOT)}:{lineno}: {line}")

    print(f"files scanned: {len(targets)} hits: {len(all_hits)}")
    for hit in all_hits:
        print(hit)

    assert not all_hits, f"secret(s) found in argv position (flagged {len(all_hits)}): {all_hits!r}"


# ===========================================================================
# WP-4 rework (supervisor ruling 2026-09-06, wp4-rework-1.md #3): the
# review found two gaps a bare "flagged 0" assert cannot catch on its own
# -- (a) the rule TEXT itself silently narrowing (e.g. "pepper" dropped
# from SECRET_WORD would still show "flagged 0" if no pepper-carrying line
# exists in the tree today), and (b) the DEPLOY-SCRIPT side of the scan
# going empty (e.g. `r2db-api/deploy/scripts/` renamed) while the existing
# `len(targets) >= 1` assert stays satisfied by the two unconditionally-
# appended `ops.py` files alone.
# ===========================================================================


def test_secret_word_and_rule_pattern_are_the_design_verbatim_text() -> None:
    """完了条件 4 (WP-4 rework #3(a)): `SECRET_WORD` and the FULLY DERIVED
    `RULE.pattern` (built FROM `SECRET_WORD` at import time, so a mutation
    to either one moves `RULE.pattern`) are pinned against a SEPARATELY
    spelled-out copy of design §3 D-5 実装の形 (c)'s own verbatim text --
    not derived from the module's own `SECRET_WORD` here, so a narrowing
    mutation (e.g. dropping "pepper") cannot pass by accidentally
    reproducing itself on both sides of the comparison."""
    assert SECRET_WORD == r"(?:password|passwd|pepper|secret|token|api_key|key)"
    assert RULE.pattern == (
        r"(?:^|[\s;|&])-v[\s=][A-Za-z0-9_]*(?:password|passwd|pepper|secret|token|api_key|key)\s*="
        r"|--password(?:=\S|[ \t]+[^-\s])"
        r"|://[^/\s]*:[^@/\s]+@"
    )


def test_rule_detects_each_secret_word_category_and_excludes_env_assign_comment_and_valueless_password(
    tmp_path: Path,
) -> None:
    """完了条件 4 (WP-4 rework #3(a)): one synthetic line per category,
    each asserted individually -- pepper / password / api_key / token /
    URL userinfo / valued `--password` must all be DETECTED; an `export
    X=`/`X=` env assignment, a comment, and a valueless `--password`
    (prompt-forcing flag, never carries the secret on argv) must all be
    EXCLUDED. Dropping "pepper" from `SECRET_WORD` turns only the pepper
    line's own assertion red, nothing else."""
    fixture_lines: list[tuple[str, bool, str]] = [
        ('    -v control_password="${SOME_PASSWORD}" \\', True, "psql -v <...password...>= (rule branch a)"),
        ('    -v pepper="${SOME_PEPPER}" \\', True, "psql -v <...pepper...>= (rule branch a)"),
        ('    -v api_key="${SOME_API_KEY}" \\', True, "psql -v <...api_key...>= (rule branch a)"),
        ('    -v session_token="${SOME_TOKEN}" \\', True, "psql -v <...token...>= (rule branch a)"),
        ('psql "postgresql://someuser:s3cr3t@db.example.invalid/somedb"', True, "URL userinfo (rule branch c)"),
        ("createuser --password=hunter2 someuser", True, "valued --password=<val> (rule branch b)"),
        ("createuser --password hunter2", True, "valued --password <val> (rule branch b)"),
        ('export SOME_SVC_CONTROL_PASSWORD="${1}"', False, "excluded: export env assignment"),
        ('SOME_SVC_CONTROL_PASSWORD="${1}"', False, "excluded: bare env assignment"),
        ('# -v control_password="${SOME_PASSWORD}" \\', False, "excluded: comment line"),
        ("psql --password -U someuser", False, "excluded: valueless --password (prompt flag, no secret on argv)"),
    ]
    fixture_path = tmp_path / "argv_secret_fixture.txt"
    fixture_path.write_text("\n".join(line for line, _, _ in fixture_lines) + "\n")

    hit_linenos = {lineno for lineno, _ in scan_file(fixture_path)}
    for lineno, (line, expect_detect, label) in enumerate(fixture_lines, start=1):
        detected = lineno in hit_linenos
        assert detected == expect_detect, f"line {lineno} ({label!r} -- {line!r}): expected detected={expect_detect}, got {detected}"


def test_scan_targets_include_the_deploy_scripts_directory_with_at_least_one_shell_script() -> None:
    """完了条件 4 非空振り (WP-4 rework #3(b)): the pre-existing `len(
    targets) >= 1` assert in `test_deploy_secret_argv_scan_flags_zero_hits`
    is trivially satisfied by the two unconditionally-appended `ops.py`
    files alone, even if `r2db-api/deploy/scripts/` were renamed or
    emptied out from under it. This test pins the deploy-script side
    specifically -- renaming the directory turns it red."""
    deploy_dir = REPO_ROOT / "r2db-api" / "deploy" / "scripts"
    assert deploy_dir.is_dir(), f"deploy scripts directory not found: {deploy_dir}"
    shell_scripts = sorted(deploy_dir.glob("*.sh"))
    assert len(shell_scripts) >= 1, "no .sh files under r2db-api/deploy/scripts -- the scan would silently skip the deploy-script side"
    targets = _scan_targets()
    for script in shell_scripts:
        assert script in targets, f"{script} is not among the scan targets"
