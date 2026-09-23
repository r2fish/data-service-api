"""tools/tests/test_comment_provenance.py -- self-test for
tools/check_comment_provenance.py (change set 0 of the code-comment-history
移動 effort; design docs/design/CODE_COMMENT_PROVENANCE_V1.md v0.4, work
order docs/work-orders/WORK_ORDER_CODE_COMMENT_PROVENANCE_CS1.md §1;
revised after the change-set-0 code-review monitor ruling 2026-09-14).

Deliberately NOT under `conformance-tests/` and NOT discoverable by the root
suite: `tools/` is not in pyproject.toml's `[tool.pytest.ini_options]
testpaths` (same convention as tools/tests/test_check_doc_refs.py).

Every scenario builds its own synthetic git repository under `tmp_path`
(git init, an old-version commit, then the new version written into the
working tree) and calls this file's `run_base` / `run_register` directly --
never `git checkout`, never touching the real repository except in
`test_repository_register_passes`, which runs `--register` against the
real repo read-only.

Run directly:
    ./.venv/bin/python -m pytest tools/tests/test_comment_provenance.py -q
"""
from __future__ import annotations

import ast
import importlib.util
import io
import subprocess
import sys
from pathlib import Path

import pytest

_MODULE_PATH = Path(__file__).resolve().parents[1] / "check_comment_provenance.py"
_spec = importlib.util.spec_from_file_location("check_comment_provenance", _MODULE_PATH)
cp = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("check_comment_provenance", cp)
_spec.loader.exec_module(cp)  # type: ignore[union-attr]

REAL_REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Synthetic-repository helpers.
# ---------------------------------------------------------------------------
def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "r2db-api" / "src" / "r2db_api").mkdir(parents=True)
    (repo / "MitateDB-api" / "src" / "mitatedb_api").mkdir(parents=True)
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "test")
    return repo


def _commit_all(repo: Path, msg: str) -> str:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", msg)
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()


def _write(repo: Path, rel: str, content: str) -> Path:
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def _run_base(repo: Path, rev: str, rel_path: str) -> tuple[int, str]:
    out = io.StringIO()
    code = cp.run_base(repo, rev, [rel_path], out=out, err=out)
    return code, out.getvalue()


def _run_register(repo: Path) -> tuple[int, str]:
    out = io.StringIO()
    code = cp.run_register(repo, out=out, err=out)
    return code, out.getvalue()


def _companion_section(ch_id: str, block_text: str, *, moved_from: str = "`mod.py` (`f`)",
                        parent_commit: str = "0123abc", kind: str = "comment") -> str:
    return (
        f"## {ch_id}\n\n"
        f"- moved from: {moved_from}\n"
        f"- parent commit: `{parent_commit}`\n"
        f"- kind: {kind}\n\n"
        f"```\n{block_text}\n```\n\n"
    )


# ===========================================================================
# --base : design §4.1 (1)-(5)
# ===========================================================================

# --- (1) code unchanged --------------------------------------------------

def test_code_line_change_is_red(tmp_path):
    repo = _init_repo(tmp_path)
    old = "def f():\n    # A short comment (SI-08).\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    new = "def f():\n    # A short comment (SI-08).\n    return 2\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", new)

    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (1)" in output


def test_line_shift_only_is_green(tmp_path):
    repo = _init_repo(tmp_path)
    old = "def f():\n    # A short comment (SI-08).\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    new = "\n\ndef f():\n    # A short comment (SI-08).\n\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", new)

    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 0, output
    assert "comment provenance OK" in output


# --- (2) moved block byte-identical to companion -------------------------

def test_companion_sentence_deleted_is_red(tmp_path):
    repo = _init_repo(tmp_path)
    old_block = "# First sentence here. Second sentence here."
    old = f"{old_block}\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    new = "# history: CH-0001\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", new)
    # Companion is missing "Second sentence here." -- an accidental edit.
    _write(
        repo, "docs/code-history/r2db-api/mod.md",
        _companion_section("CH-0001", "# First sentence here."),
    )

    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (2)" in output


def test_changed_block_without_id_is_red(tmp_path):
    repo = _init_repo(tmp_path)
    old = "# An old note (WP-9).\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    # Silently edited, with no CH-ID reference registering the change.
    new = "# A different note.\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", new)

    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (2)" in output


# --- (3) retained text is a sentence-order-preserving reduction ----------

def _setup_retained_reduction(tmp_path, retained_new_block: str):
    """Old block: 3 sentences. Sentence C always moves out to the
    companion (byte-identical, satisfying check (2)); the first two
    sentences are retained (verbatim or mutated, per `retained_new_block`)
    plus a trailing `# history: CH-0001` marker."""
    repo = _init_repo(tmp_path)
    old_block_lines = [
        "# Sentence A stays here.",
        "# Sentence B stays here too.",
        "# Sentence C moves away for history.",
    ]
    old = "\n".join(old_block_lines) + "\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    new = f"{retained_new_block}\n# history: CH-0001\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", new)
    companion_block = "\n".join(old_block_lines)
    _write(
        repo, "docs/code-history/r2db-api/mod.md",
        _companion_section("CH-0001", companion_block),
    )
    return repo, rev


def test_sentence_deletion_is_green(tmp_path):
    repo, rev = _setup_retained_reduction(
        tmp_path,
        "# Sentence A stays here.\n# Sentence B stays here too.",
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 0, output


def test_negation_dropped_is_red(tmp_path):
    repo = _init_repo(tmp_path)
    old_block_lines = [
        "# Sentence A must never regress here.",
        "# Sentence B stays here too.",
        "# Sentence C moves away for history.",
    ]
    old = "\n".join(old_block_lines) + "\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    new = (
        "# Sentence A must regress here.\n"  # negation dropped
        "# Sentence B stays here too.\n"
        "# history: CH-0001\ndef f():\n    return 1\n"
    )
    _write(repo, "r2db-api/src/r2db_api/mod.py", new)
    _write(
        repo, "docs/code-history/r2db-api/mod.md",
        _companion_section("CH-0001", "\n".join(old_block_lines)),
    )

    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (3)" in output


def test_sentence_reorder_is_red(tmp_path):
    repo, rev = _setup_retained_reduction(
        tmp_path,
        "# Sentence B stays here too.\n# Sentence A stays here.",
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (3)" in output


def test_word_added_is_red(tmp_path):
    # The added word is a PREFIX ("Well, ") so the original sentence stays
    # a contiguous substring of the new one -- this is what a substring-
    # match bug (row 7's mutation) would wrongly treat as unchanged; the
    # correct exact-match check must still reject it.
    repo, rev = _setup_retained_reduction(
        tmp_path,
        "# Well, Sentence A stays here.\n# Sentence B stays here too.",
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (3)" in output


def test_wrapped_line_deleted_is_red(tmp_path):
    repo = _init_repo(tmp_path)
    old_block_lines = [
        "# This sentence wraps across two physical",
        "# lines here.",
        "# This other sentence moves away.",
    ]
    old = "\n".join(old_block_lines) + "\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    # Second physical line of the wrapped sentence is deleted.
    new = "# This sentence wraps across two physical\n# history: CH-0001\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", new)
    _write(
        repo, "docs/code-history/r2db-api/mod.md",
        _companion_section("CH-0001", "\n".join(old_block_lines)),
    )

    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (3)" in output


# --- (4) parenthetical token removal --------------------------------------

def test_current_ref_removed_in_parens_is_red(tmp_path):
    repo = _init_repo(tmp_path)
    old_block_lines = [
        "# Use the connection pool (SI-08/R-5).",
        "# This sentence moves away.",
    ]
    old = "\n".join(old_block_lines) + "\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    # Wrongly removed the provenance-tagged SI-08 instead of the bare R-5.
    new = "# Use the connection pool (R-5).\n# history: CH-0001\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", new)
    _write(
        repo, "docs/code-history/r2db-api/mod.md",
        _companion_section("CH-0001", "\n".join(old_block_lines)),
    )

    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (3)" in output


def test_history_only_parens_removed_is_green(tmp_path):
    # Both words in the parens ("WP-12", "review") are single-word §4.1(5)
    # history tokens -- the whole parenthetical may be dropped.
    repo = _init_repo(tmp_path)
    old_block_lines = [
        "# Use the connection pool (WP-12, review).",
        "# This sentence moves away.",
    ]
    old = "\n".join(old_block_lines) + "\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    new = "# Use the connection pool.\n# history: CH-0001\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", new)
    _write(
        repo, "docs/code-history/r2db-api/mod.md",
        _companion_section("CH-0001", "\n".join(old_block_lines)),
    )

    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 0, output


def test_slash_separated_paren_correct_removal_is_green(tmp_path):
    # Fixture 7: (SI-08/R-5) -> (SI-08) is the CORRECT removal (only the
    # bare, untagged R-5 goes; the protected SI-08 stays) -- green.
    repo = _init_repo(tmp_path)
    old_block_lines = [
        "# Use the connection pool (SI-08/R-5).",
        "# This sentence moves away.",
    ]
    old = "\n".join(old_block_lines) + "\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    new = "# Use the connection pool (SI-08).\n# history: CH-0001\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", new)
    _write(
        repo, "docs/code-history/r2db-api/mod.md",
        _companion_section("CH-0001", "\n".join(old_block_lines)),
    )

    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 0, output


# --- (5) no history token in an added line --------------------------------

def test_added_history_token_is_red(tmp_path):
    repo = _init_repo(tmp_path)
    old = "# Keep this as is.\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    # Blank line keeps the addition a distinct block from the unchanged
    # one, isolating this test to the (5) added-history-token concern.
    new = "# Keep this as is.\n\n# Added during WP-9 work.\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", new)

    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (5)" in output


def test_round_trip_is_not_a_history_token(tmp_path):
    # "round trip" must survive here even though it is literally present in
    # an ADDED/changed line -- this is a legitimate (4) paren removal
    # (WP-12 dropped), not a rogue history-token addition, and the
    # resulting line happens to contain the word "round" followed by a
    # non-digit word ("trip"), which \bround \d+\b must not match.
    repo = _init_repo(tmp_path)
    old_block_lines = [
        "# This performs a round trip (WP-12) to the database.",
        "# This sentence moves away.",
    ]
    old = "\n".join(old_block_lines) + "\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    new = "# This performs a round trip to the database.\n# history: CH-0001\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", new)
    _write(
        repo, "docs/code-history/r2db-api/mod.md",
        _companion_section("CH-0001", "\n".join(old_block_lines)),
    )

    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 0, output


# ===========================================================================
# --register : design §4.2, items 1-6
# ===========================================================================

def test_register_unresolved_id_is_red(tmp_path):
    repo = _init_repo(tmp_path)
    _write(repo, "r2db-api/src/r2db_api/mod.py", "# history: CH-0001\ndef f():\n    return 1\n")
    code, output = _run_register(repo)
    assert code == 1
    assert "§4.2 1" in output
    assert "CH-0001" in output


def test_register_orphan_section_is_red(tmp_path):
    repo = _init_repo(tmp_path)
    _write(repo, "r2db-api/src/r2db_api/mod.py", "def f():\n    return 1\n")
    _write(
        repo, "docs/code-history/r2db-api/mod.md",
        _companion_section("CH-0002", "# Some moved comment."),
    )
    code, output = _run_register(repo)
    assert code == 1
    assert "§4.2 1" in output
    assert "orphan" in output


def test_register_duplicate_across_peers_is_red(tmp_path):
    repo = _init_repo(tmp_path)
    _write(repo, "r2db-api/src/r2db_api/mod.py", "# history: CH-0003\ndef f():\n    return 1\n")
    _write(repo, "MitateDB-api/src/mitatedb_api/mod.py", "# history: CH-0003\ndef g():\n    return 2\n")
    _write(
        repo, "docs/code-history/r2db-api/mod.md",
        _companion_section("CH-0003", "# Some moved comment."),
    )
    _write(
        repo, "docs/code-history/MitateDB-api/mod.md",
        _companion_section("CH-0003", "# Some other moved comment."),
    )
    code, output = _run_register(repo)
    assert code == 1
    assert "§4.2 2" in output


def test_register_missing_required_line_is_red(tmp_path):
    repo = _init_repo(tmp_path)
    _write(repo, "r2db-api/src/r2db_api/mod.py", "# history: CH-0004\ndef f():\n    return 1\n")
    section = (
        "## CH-0004\n\n"
        "- moved from: `mod.py` (`f`)\n"
        "- parent commit: `0123abc`\n\n"  # "kind:" line missing
        "```\n# Some moved comment.\n```\n\n"
    )
    _write(repo, "docs/code-history/r2db-api/mod.md", section)
    code, output = _run_register(repo)
    assert code == 1
    assert "§4.2 3" in output


def test_register_bad_reference_format_is_red(tmp_path):
    repo = _init_repo(tmp_path)
    # Wrong case ("History" vs the canonical lower-case "history") -- a
    # regression that makes the reference-line regex case-INsensitive
    # would wrongly accept this as canonical.
    _write(
        repo, "r2db-api/src/r2db_api/mod.py",
        "# History: CH-0005\ndef f():\n    return 1\n",
    )
    _write(
        repo, "docs/code-history/r2db-api/mod.md",
        _companion_section("CH-0005", "# Some moved comment."),
    )
    code, output = _run_register(repo)
    assert code == 1
    assert "§4.2 4" in output


def test_register_new_doc_access_is_red(tmp_path):
    repo = _init_repo(tmp_path)
    _write(
        repo, "r2db-api/src/r2db_api/mod.py",
        "import inspect\n\n\ndef f():\n    return inspect.getsource(f)\n",
    )
    code, output = _run_register(repo)
    assert code == 1
    assert "§4.2 5" in output


def test_min_ch_ids_counts_across_peers(tmp_path, monkeypatch):
    repo = _init_repo(tmp_path)
    _write(repo, "r2db-api/src/r2db_api/mod.py", "# history: CH-0006\ndef f():\n    return 1\n")
    _write(repo, "MitateDB-api/src/mitatedb_api/mod.py", "# history: CH-0007\ndef g():\n    return 2\n")
    _write(
        repo, "docs/code-history/r2db-api/mod.md",
        _companion_section("CH-0006", "# Some moved comment."),
    )
    _write(
        repo, "docs/code-history/MitateDB-api/mod.md",
        _companion_section("CH-0007", "# Some other moved comment."),
    )
    # Each peer has only 1 id on its own; the combined total is 2. A buggy
    # "count per peer" implementation would fail this (1 < 2 per peer);
    # the correct combined-count implementation passes.
    monkeypatch.setattr(cp, "MIN_CH_IDS", 2)
    code, output = _run_register(repo)
    assert code == 0, output


def test_repository_register_passes():
    out = io.StringIO()
    code = cp.run_register(REAL_REPO_ROOT, out=out, err=out)
    output = out.getvalue()
    assert code == 0, output
    assert "comment provenance register OK" in output
    scanned = int(output.split("register OK: ")[1].split(" files scanned")[0])
    assert scanned >= 1


# ===========================================================================
# Code-review fixtures (monitor ruling 2026-09-14, change-set-0 re-review).
# Numbered per the reviewer's own list; S-numbers refer to the reviewer's
# probe script (scratchpad rev-ccp0/probe.py).
# ===========================================================================

# --- 1: retained text detached from its marker by a blank line (S1) ------

def test_retained_text_detached_from_marker_is_red(tmp_path):
    repo = _init_repo(tmp_path)
    old_block_lines = ["# A is true.", "# B moves (WP-3)."]
    old = "\n".join(old_block_lines) + "\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    # The rewritten text sits in its OWN block (blank-line separated) from
    # the reference line -- the reference alone claims the whole original
    # block moved, but the rewritten text is unaccounted for.
    new = "# A is FALSE, do anything.\n\n# history: CH-0001\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", new)
    _write(
        repo, "docs/code-history/r2db-api/mod.md",
        _companion_section("CH-0001", "\n".join(old_block_lines)),
    )

    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (2)" in output


# --- 2: a brand-new, unrelated comment block is added (S2) ---------------

def test_new_unrelated_block_added_is_red(tmp_path):
    repo = _init_repo(tmp_path)
    old = "# Keep.\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    new = "# Keep.\n\n# Safe to call without the lock.\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", new)

    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (2)" in output


# --- 3: negation word blocks whole-parens removal (S3) --------------------

def test_negation_word_blocks_paren_removal_is_red(tmp_path):
    repo = _init_repo(tmp_path)
    old_block_lines = ["# Retry (never before review).", "# Moved."]
    old = "\n".join(old_block_lines) + "\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    # Only "review" is removable; "never before" must stay -- deleting the
    # whole parenthetical is invalid.
    new = "# Retry.\n# history: CH-0001\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", new)
    _write(
        repo, "docs/code-history/r2db-api/mod.md",
        _companion_section("CH-0001", "\n".join(old_block_lines)),
    )

    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (3)" in output


# --- 4: space-separated paren words (S4) ----------------------------------

def test_space_separated_paren_partial_removal_is_green(tmp_path):
    repo = _init_repo(tmp_path)
    old_block_lines = ["# Pool (see SI-08 WP-3).", "# Moved."]
    old = "\n".join(old_block_lines) + "\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    new = "# Pool (see SI-08).\n# history: CH-0001\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", new)
    _write(
        repo, "docs/code-history/r2db-api/mod.md",
        _companion_section("CH-0001", "\n".join(old_block_lines)),
    )

    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 0, output


def test_space_separated_paren_full_removal_is_red(tmp_path):
    repo = _init_repo(tmp_path)
    old_block_lines = ["# Pool (see SI-08 WP-3).", "# Moved."]
    old = "\n".join(old_block_lines) + "\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    # Whole parens removed -- "see" and "SI-08" are not removable.
    new = "# Pool.\n# history: CH-0001\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", new)
    _write(
        repo, "docs/code-history/r2db-api/mod.md",
        _companion_section("CH-0001", "\n".join(old_block_lines)),
    )

    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (3)" in output


# --- 5: filename-tagged parens protect co-located bare IDs (S5) ----------

def test_filename_tagged_paren_removal_is_red(tmp_path):
    repo = _init_repo(tmp_path)
    old_block_lines = ["# Store (`docs/design/X_V1.md` R-2).", "# Moved."]
    old = "\n".join(old_block_lines) + "\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    # design §9 rule 2 (0c): a filename is only a provenance tag if it
    # REALLY EXISTS in the basis revision's tree -- commit a stub so this
    # fixture still exercises the "real filename" branch, not the "fake
    # filename becomes a removable history token" branch.
    _write(repo, "docs/design/X_V1.md", "stub\n")
    rev = _commit_all(repo, "old")
    # R-2 is a bare ID, but the same parens names a design file, so it may
    # not be removed -- this edit (dropping R-2, keeping the file name) is
    # invalid.
    new = "# Store (`docs/design/X_V1.md`).\n# history: CH-0001\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", new)
    _write(
        repo, "docs/code-history/r2db-api/mod.md",
        _companion_section("CH-0001", "\n".join(old_block_lines)),
    )

    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (3)" in output


# --- 6: comma-separated parens, partial removal (S6) ----------------------

def test_comma_separated_paren_partial_removal_is_green(tmp_path):
    repo = _init_repo(tmp_path)
    old_block_lines = ["# Pool (SI-08, C-05, WP-3).", "# Moved."]
    old = "\n".join(old_block_lines) + "\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    new = "# Pool (SI-08, C-05).\n# history: CH-0001\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", new)
    _write(
        repo, "docs/code-history/r2db-api/mod.md",
        _companion_section("CH-0001", "\n".join(old_block_lines)),
    )

    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 0, output


# --- 8: a history token glued directly onto Japanese text (S7, re.ASCII) -

def test_japanese_adjacent_history_token_is_red(tmp_path):
    repo = _init_repo(tmp_path)
    old = "# Keep.\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    # No space/punctuation between the Japanese text and "WP-3" -- default
    # Unicode \b would see no boundary there (Kanji counts as \w).
    new = "# Keep.\n\n# 作業WP-3で追加。\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", new)

    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (5)" in output


# --- 9: a Japanese `。` splits a sentence with no trailing space (S8) -----

def test_japanese_period_sentence_deletion_is_green(tmp_path):
    repo = _init_repo(tmp_path)
    old_block_lines = ["# 文Aは正しい。文Bは移す。"]
    old = "\n".join(old_block_lines) + "\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    new = "# 文Aは正しい。\n# history: CH-0001\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", new)
    _write(
        repo, "docs/code-history/r2db-api/mod.md",
        _companion_section("CH-0001", "\n".join(old_block_lines)),
    )

    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 0, output


# --- extra: history token added inside a trailing/inline comment ---------

def test_trailing_comment_history_token_is_red(tmp_path):
    repo = _init_repo(tmp_path)
    old = "def f():\n    x = 1\n    return x\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    new = "def f():\n    x = 1  # added during WP-9 work\n    return x\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", new)

    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (5)" in output


# --- 10: docstring `History:` marker resolution (S9/S9b) -----------------

def test_docstring_history_unresolved_is_red(tmp_path):
    repo = _init_repo(tmp_path)
    _write(
        repo, "r2db-api/src/r2db_api/mod.py",
        'def f():\n    """Do it.\n\n    History: CH-0009\n    """\n    return 1\n',
    )
    code, output = _run_register(repo)
    assert code == 1
    assert "§4.2 1" in output
    assert "CH-0009" in output


def test_docstring_history_with_companion_is_green(tmp_path):
    repo = _init_repo(tmp_path)
    _write(
        repo, "r2db-api/src/r2db_api/mod.py",
        'def f():\n    """Do it.\n\n    History: CH-0009\n    """\n    return 1\n',
    )
    _write(
        repo, "docs/code-history/r2db-api/mod.md",
        _companion_section("CH-0009", "Do it.\n\nMoved.", kind="docstring"),
    )
    code, output = _run_register(repo)
    assert code == 0, output


# --- 11: the six §4.2-3 / §4.2-1 register cases ---------------------------

def test_register_same_id_in_two_files_same_peer_is_red(tmp_path):
    repo = _init_repo(tmp_path)
    _write(repo, "r2db-api/src/r2db_api/a.py", "# history: CH-0020\ndef f():\n    return 1\n")
    _write(repo, "r2db-api/src/r2db_api/b.py", "# history: CH-0020\ndef g():\n    return 2\n")
    _write(
        repo, "docs/code-history/r2db-api/mod.md",
        _companion_section("CH-0020", "# x"),
    )
    code, output = _run_register(repo)
    assert code == 1
    assert "§4.2 3" in output
    assert "CH-0020" in output


def test_register_same_id_twice_in_one_file_is_red(tmp_path):
    repo = _init_repo(tmp_path)
    _write(
        repo, "r2db-api/src/r2db_api/mod.py",
        "# history: CH-0021\ndef f():\n    return 1\n\n\n# history: CH-0021\ndef g():\n    return 2\n",
    )
    _write(
        repo, "docs/code-history/r2db-api/mod.md",
        _companion_section("CH-0021", "# x"),
    )
    code, output = _run_register(repo)
    assert code == 1
    assert "§4.2 3" in output
    assert "CH-0021" in output


def test_register_same_id_both_peers_without_pair_is_red(tmp_path):
    repo = _init_repo(tmp_path)
    _write(repo, "r2db-api/src/r2db_api/mod.py", "# history: CH-0022\ndef f():\n    return 1\n")
    _write(repo, "MitateDB-api/src/mitatedb_api/mod.py", "# history: CH-0022\ndef g():\n    return 2\n")
    _write(
        repo, "docs/code-history/r2db-api/mod.md",
        _companion_section("CH-0022", "# x"),
    )
    _write(
        repo, "docs/code-history/MitateDB-api/mod.md",
        _companion_section("CH-0022", "# y"),
    )
    code, output = _run_register(repo)
    assert code == 1
    assert "pair.md" in output
    assert "CH-0022" in output


def test_register_pair_both_sides_once_is_green(tmp_path):
    repo = _init_repo(tmp_path)
    _write(repo, "r2db-api/src/r2db_api/mod.py", "# history: CH-0023\ndef f():\n    return 1\n")
    _write(repo, "MitateDB-api/src/mitatedb_api/mod.py", "# history: CH-0023\ndef g():\n    return 2\n")
    _write(
        repo, "docs/code-history/pair.md",
        _companion_section("CH-0023", "# x"),
    )
    code, output = _run_register(repo)
    assert code == 0, output


def test_register_pair_one_side_only_is_red(tmp_path):
    repo = _init_repo(tmp_path)
    _write(repo, "r2db-api/src/r2db_api/mod.py", "# history: CH-0024\ndef f():\n    return 1\n")
    _write(
        repo, "docs/code-history/pair.md",
        _companion_section("CH-0024", "# x"),
    )
    code, output = _run_register(repo)
    assert code == 1
    assert "pair.md" in output
    assert "CH-0024" in output


def test_register_section_empty_or_no_fence_is_red(tmp_path):
    repo = _init_repo(tmp_path)
    _write(repo, "r2db-api/src/r2db_api/mod.py", "# history: CH-0025\ndef f():\n    return 1\n")
    # Required lines present, but no fenced block at all.
    section = (
        "## CH-0025\n\n"
        "- moved from: `mod.py` (`f`)\n"
        "- parent commit: `0123abc`\n"
        "- kind: comment\n"
    )
    _write(repo, "docs/code-history/r2db-api/mod.md", section)
    code, output = _run_register(repo)
    assert code == 1
    assert "§4.2 3" in output
    assert "CH-0025" in output


# --- 12: pair.md orphan (S11) ---------------------------------------------

def test_register_pair_orphan_is_red(tmp_path):
    repo = _init_repo(tmp_path)
    _write(repo, "r2db-api/src/r2db_api/mod.py", "def f():\n    return 1\n")
    _write(
        repo, "docs/code-history/pair.md",
        _companion_section("CH-0026", "# x"),
    )
    code, output = _run_register(repo)
    assert code == 1
    assert "pair.md" in output
    assert "orphan" in output


# --- 13: MIN_CH_IDS threshold not met (combined) --------------------------

def test_min_ch_ids_threshold_not_met_is_red(tmp_path, monkeypatch):
    repo = _init_repo(tmp_path)
    _write(repo, "r2db-api/src/r2db_api/mod.py", "# history: CH-0027\ndef f():\n    return 1\n")
    _write(repo, "MitateDB-api/src/mitatedb_api/mod.py", "# history: CH-0028\ndef g():\n    return 2\n")
    _write(
        repo, "docs/code-history/r2db-api/mod.md",
        _companion_section("CH-0027", "# x"),
    )
    _write(
        repo, "docs/code-history/MitateDB-api/mod.md",
        _companion_section("CH-0028", "# y"),
    )
    monkeypatch.setattr(cp, "MIN_CH_IDS", 3)
    code, output = _run_register(repo)
    assert code == 1
    assert "§4.2 6" in output


# --- 14: `from inspect import getsource` (S13) -----------------------------

def test_register_new_doc_access_via_import_is_red(tmp_path):
    repo = _init_repo(tmp_path)
    _write(
        repo, "r2db-api/src/r2db_api/mod.py",
        "from inspect import getsource\n\n\ndef f():\n    return getsource(f)\n",
    )
    code, output = _run_register(repo)
    assert code == 1
    assert "§4.2 5" in output


# --- extra: a 5-or-more-digit CH-ID is a format violation -----------------

def test_register_five_digit_ch_id_is_red(tmp_path):
    repo = _init_repo(tmp_path)
    _write(repo, "r2db-api/src/r2db_api/mod.py", "# history: CH-00015\ndef f():\n    return 1\n")
    code, output = _run_register(repo)
    assert code == 1
    assert "§4.2 4" in output


# ===========================================================================
# Code-review fixtures, round 3 (monitor ruling 2026-09-14, 2nd re-review).
# ===========================================================================

# --- 1: a filename-tagged paren protects EVERY bare ID in it, not just the
#        one immediately next to the file name (S5, probe2.py P1) --------

def test_filename_tagged_paren_protects_every_id_is_red(tmp_path):
    repo = _init_repo(tmp_path)
    old_block_lines = ["# Store (`docs/design/X_V1.md` R-1/R-2).", "# Moved."]
    old = "\n".join(old_block_lines) + "\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    _write(repo, "docs/design/X_V1.md", "stub\n")  # design §9 rule 2: must be real
    rev = _commit_all(repo, "old")
    # R-2 is not adjacent to the file name, but the whole parens is
    # file-tagged, so it may not be removed either.
    new = "# Store (`docs/design/X_V1.md` R-1).\n# history: CH-0001\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", new)
    _write(
        repo, "docs/code-history/r2db-api/mod.md",
        _companion_section("CH-0001", "\n".join(old_block_lines)),
    )

    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (3)" in output


# --- 2: `f.__doc__` -------------------------------------------------------

def test_register_doc_dunder_attribute_is_red(tmp_path):
    repo = _init_repo(tmp_path)
    _write(
        repo, "r2db-api/src/r2db_api/mod.py",
        "def f():\n    return f.__doc__\n",
    )
    code, output = _run_register(repo)
    assert code == 1
    assert "§4.2 5" in output


# --- 3: getattr(f, "__doc__") and an aliased bare import call ------------

def test_register_getattr_doc_is_red(tmp_path):
    repo = _init_repo(tmp_path)
    _write(
        repo, "r2db-api/src/r2db_api/mod.py",
        'def f():\n    return getattr(f, "__doc__")\n',
    )
    code, output = _run_register(repo)
    assert code == 1
    assert "§4.2 5" in output


def test_register_aliased_import_call_is_red(tmp_path):
    repo = _init_repo(tmp_path)
    _write(
        repo, "r2db-api/src/r2db_api/mod.py",
        "from inspect import getsource as gs\n\n\ndef f():\n    return gs(f)\n",
    )
    code, output = _run_register(repo)
    assert code == 1
    assert "§4.2 5" in output


# --- 4: a docstring containing ``` in a 4-backtick-fenced companion ------

def test_docstring_with_backticks_in_long_fence_is_green(tmp_path):
    repo = _init_repo(tmp_path)
    old = (
        'def f():\n'
        '    """Run.\n\n'
        '    ```\n'
        '    x = 1\n'
        '    ```\n\n'
        '    Moved part.\n'
        '    """\n'
        '    return 1\n'
    )
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    new = 'def f():\n    """Run.\n\n    History: CH-0001\n    """\n    return 1\n'
    _write(repo, "r2db-api/src/r2db_api/mod.py", new)
    doc_value = cp.inspect.cleandoc(
        'Run.\n\n    ```\n    x = 1\n    ```\n\n    Moved part.'
    )
    companion = (
        "## CH-0001\n\n"
        "- moved from: `mod.py` (`f`)\n"
        "- parent commit: `0123abc`\n"
        "- kind: docstring\n\n"
        f"````\n{doc_value}\n````\n\n"
    )
    _write(repo, "docs/code-history/r2db-api/mod.md", companion)

    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 0, output


# --- 5: r2db references an ID whose companion lives only in MitateDB ----

def test_register_r2db_reference_not_resolved_by_mitatedb_companion_is_red(tmp_path):
    repo = _init_repo(tmp_path)
    _write(repo, "r2db-api/src/r2db_api/mod.py", "# history: CH-0030\ndef f():\n    return 1\n")
    _write(
        repo, "docs/code-history/MitateDB-api/mod.md",
        _companion_section("CH-0030", "# x"),
    )
    code, output = _run_register(repo)
    assert code == 1
    assert "r2db-api: CH-0030" in output
    assert "has no companion section" in output


# --- P3: no-CH-ID blocks are compared ORDERED, per enclosing scope -------

def test_block_swap_within_scope_is_red(tmp_path):
    repo = _init_repo(tmp_path)
    old = "# Block X.\ndef f():\n    return 1\n\n\n# Block Y.\ndef g():\n    return 2\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    # Both blocks are individually unchanged text, but swapped in place --
    # a multiset comparison would wrongly call this green.
    new = "# Block Y.\ndef f():\n    return 1\n\n\n# Block X.\ndef g():\n    return 2\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", new)

    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (2)" in output


def test_duplicate_identical_block_deleted_without_id_is_red(tmp_path):
    # Regression (formerly probe S15): a duplicate identical block silently
    # dropped, with no CH-ID, must stay red under the ordered comparison.
    repo = _init_repo(tmp_path)
    old = "def f():\n    # Lock first.\n    a = 1\n    # Lock first.\n    return a\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    new = "def f():\n    a = 1\n    # Lock first.\n    return a\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", new)

    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (2)" in output


# --- P4: a Japanese closing bracket right after 。 stays attached --------

def test_japanese_closing_bracket_sentence_split_is_green(tmp_path):
    repo = _init_repo(tmp_path)
    old_block_lines = ["# 「これは正しい。」次は移す。"]
    old = "\n".join(old_block_lines) + "\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    new = "# 「これは正しい。」\n# history: CH-0001\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", new)
    _write(
        repo, "docs/code-history/r2db-api/mod.md",
        _companion_section("CH-0001", "\n".join(old_block_lines)),
    )

    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 0, output


# --- token grammar: `_WP-3` and inflected "review" forms ------------------

def test_underscore_prefixed_wp_token_is_red(tmp_path):
    repo = _init_repo(tmp_path)
    old = "# Keep.\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    new = "# Keep.\n\n# see _WP-3 for context.\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", new)

    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (5)" in output


def test_review_inflected_form_is_red(tmp_path):
    repo = _init_repo(tmp_path)
    old = "# Keep.\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    new = "# Keep.\n\n# Per the reviews, this changed.\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", new)

    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (5)" in output


# ===========================================================================
# Code-review fixtures, round 4 (monitor ruling 2026-09-14, final/small).
# ===========================================================================

# --- 1 (P3a): identical block in f and g; g's copy moves via CH-ID ------

def test_p3a_shared_block_moved_from_g_via_id_is_green(tmp_path):
    repo = _init_repo(tmp_path)
    old = (
        "def f():\n"
        "    # Lock note.\n"
        "    return 1\n"
        "\n\n"
        "def g():\n"
        "    # Lock note.\n"
        "    return 2\n"
    )
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    new = (
        "def f():\n"
        "    # Lock note.\n"
        "    return 1\n"
        "\n\n"
        "def g():\n"
        "    # history: CH-0001\n"
        "    return 2\n"
    )
    _write(repo, "r2db-api/src/r2db_api/mod.py", new)
    _write(
        repo, "docs/code-history/r2db-api/mod.md",
        _companion_section("CH-0001", "# Lock note."),
    )

    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 0, output


# --- 2 (P3b): same scope, block moved to precede a DIFFERENT statement --

def test_p3b_block_moved_to_different_statement_is_red(tmp_path):
    repo = _init_repo(tmp_path)
    old = (
        "def f():\n"
        "    # Note.\n"
        "    a = 1\n"
        "    b = 2\n"
        "    return a + b\n"
    )
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    new = (
        "def f():\n"
        "    a = 1\n"
        "    # Note.\n"
        "    b = 2\n"
        "    return a + b\n"
    )
    _write(repo, "r2db-api/src/r2db_api/mod.py", new)

    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (2)" in output


# --- 3: an extension-less path word (`docs/R-5`) is still a path -------

def test_extensionless_path_paren_removal_is_red(tmp_path):
    repo = _init_repo(tmp_path)
    old_block_lines = ["# Store (docs/R-5).", "# Moved."]
    old = "\n".join(old_block_lines) + "\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    new = "# Store (docs).\n# history: CH-0001\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", new)
    _write(
        repo, "docs/code-history/r2db-api/mod.md",
        _companion_section("CH-0001", "\n".join(old_block_lines)),
    )

    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (3)" in output


# --- 4 (Y1): the sole block in f moves to g, with no CH-ID --------------

def test_y1_sole_block_moved_between_scopes_is_red(tmp_path):
    repo = _init_repo(tmp_path)
    old = "def f():\n    # Only note.\n    return 1\n\n\ndef g():\n    return 2\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    new = "def f():\n    return 1\n\n\ndef g():\n    # Only note.\n    return 2\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", new)

    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (2)" in output


# --- 5: a line-shift right before a block, and a decorator/def gap ------

def test_line_shift_and_decorator_gap_block_are_green(tmp_path):
    repo = _init_repo(tmp_path)
    old = (
        "@deco\n"
        "# Note between decorator and def.\n"
        "def f():\n"
        "    # Keep this comment.\n"
        "    return 1\n"
    )
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    # A blank line is added directly above "# Keep this comment." (a pure
    # line-shift of that one block); the decorator/def-gap block is left
    # untouched.
    new = (
        "@deco\n"
        "# Note between decorator and def.\n"
        "def f():\n"
        "\n"
        "    # Keep this comment.\n"
        "    return 1\n"
    )
    _write(repo, "r2db-api/src/r2db_api/mod.py", new)

    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 0, output


# ===========================================================================
# Code-review fixtures, round 5 (monitor ruling 2026-09-14, final/small).
# ===========================================================================

def test_reference_in_wrong_scope_is_red(tmp_path):
    # f's sole block is claimed as "moved" by a `# history:` reference
    # placed in g instead of f -- there is no cross-scope fallback, so
    # this must be red even though the companion byte-matches f's block.
    repo = _init_repo(tmp_path)
    old = "def f():\n    # Only note.\n    return 1\n\n\ndef g():\n    return 2\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    new = "def f():\n    return 1\n\n\ndef g():\n    # history: CH-0001\n    return 2\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", new)
    _write(
        repo, "docs/code-history/r2db-api/mod.md",
        _companion_section("CH-0001", "# Only note."),
    )

    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (2)" in output


# ===========================================================================
# Change set 0b: §4.1 (6), leading history-label removal (design v0.5).
# ===========================================================================

def _label_scenario(tmp_path, old_first_sentence: str, new_first_sentence: str):
    """Old block: `old_first_sentence` plus a second sentence that always
    moves away (justifying the CH-ID + companion, byte-identical to the
    full original block). New block retains `new_first_sentence` plus the
    `# history: CH-0001` marker."""
    repo = _init_repo(tmp_path)
    old_block_lines = [f"# {old_first_sentence}", "# Moved."]
    old = "\n".join(old_block_lines) + "\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    new = f"# {new_first_sentence}\n# history: CH-0001\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", new)
    _write(
        repo, "docs/code-history/r2db-api/mod.md",
        _companion_section("CH-0001", "\n".join(old_block_lines)),
    )
    return repo, rev


# --- green ------------------------------------------------------------

def test_label_removal_basic_is_green(tmp_path):
    repo, rev = _label_scenario(tmp_path, "Ruling U-7 (WP-6d): reason.", "reason.")
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 0, output


def test_label_removal_with_branch_number_is_green(tmp_path):
    # Without merging "WP-6d" with its branch number "(ii)", "ii" would
    # stand alone as a 4th content word (Ruling, ii), pushing content
    # words to 2 -- still under the limit here, so the exact-count
    # white-box test below is what actually pins the merge's necessity.
    repo, rev = _label_scenario(tmp_path, "Ruling U-7 (WP-6d (ii)): reason.", "reason.")
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 0, output


def test_label_word_tokens_merges_history_token_branch():
    # White-box (0b review round 4 supervisor ruling): the branch-number
    # merge applies to a §4.1 (5) history token too, not only a bare ID.
    # "Ruling U-7 (WP-6d (ii))" must count as exactly 3 words / 1 content
    # word (Ruling); without the WP- merge, "ii" stands alone as a 2nd
    # content word and the total climbs to 4.
    tokens = cp._label_word_tokens("Ruling U-7 (WP-6d (ii))", frozenset())
    assert len(tokens) == 3
    assert sum(1 for _t, is_content in tokens if is_content) == 1


def test_label_removal_content_words_exactly_three_is_green(tmp_path):
    repo, rev = _label_scenario(tmp_path, "Pool lock order (WP-3): reason.", "reason.")
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 0, output


def test_label_removal_twelve_words_is_green(tmp_path):
    label = " ".join(f"WP-{i}" for i in range(1, 12)) + " x"
    repo, rev = _label_scenario(tmp_path, f"{label}: reason.", "reason.")
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 0, output


def test_label_removal_combined_with_paren_removal_is_green(tmp_path):
    # (6) removes the leading label, then (4) removes the now-fully-
    # removable trailing "(R-2)" (a lone unprotected bare ID).
    repo, rev = _label_scenario(tmp_path, "Ruling X (WP-3): reason (R-2).", "reason.")
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 0, output


def test_label_removal_japanese_is_green(tmp_path):
    repo, rev = _label_scenario(
        tmp_path,
        "監督裁定 (WP-6d): 現在も成り立つ理由のみ残す。",
        "現在も成り立つ理由のみ残す。",
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 0, output


# --- red ----------------------------------------------------------------

def test_label_removal_too_many_content_words_is_red(tmp_path):
    repo, rev = _label_scenario(
        tmp_path, "Because the pool is shared (WP-3): reason.", "reason."
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (3)" in output


def test_label_removal_separator_mid_sentence_is_red(tmp_path):
    repo, rev = _label_scenario(
        tmp_path, "The lock is taken before the read per WP-3: reason.", "reason."
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (3)" in output


def test_label_removal_then_word_change_is_red(tmp_path):
    repo, rev = _label_scenario(
        tmp_path, "Ruling U-7 (WP-6d): reason is clear.", "reason is different."
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (3)" in output


def test_label_removal_thirteen_words_is_red(tmp_path):
    # 13 words (>12), but content words = 1 (<=3) -- isolates the word-
    # count condition from the content-word condition, so this fixture
    # specifically pins the 12-word limit.
    label = " ".join(f"WP-{i}" for i in range(1, 13)) + " x"
    repo, rev = _label_scenario(tmp_path, f"{label}: reason.", "reason.")
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (3)" in output


def test_label_removal_content_words_exactly_four_is_red(tmp_path):
    repo, rev = _label_scenario(tmp_path, "Pool lock order rule (WP-3): reason.", "reason.")
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (3)" in output


def test_label_removal_japanese_twenty_five_chars_is_red(tmp_path):
    repo, rev = _label_scenario(
        tmp_path, "経" * 25 + " (WP-3)：本文です。", "本文です。"
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (3)" in output


def test_label_removal_japanese_over_word_limit_is_red(tmp_path):
    # The 12-word limit applies EVEN when the label contains Japanese and
    # would otherwise pass the (separate) 24-character check.
    label = " ".join(f"WP-{i}" for i in range(1, 13)) + " 経"
    repo, rev = _label_scenario(tmp_path, f"{label}：本文です。", "本文です。")
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (3)" in output


def test_label_removal_japanese_thirty_char_paren_is_red(tmp_path):
    # The parenthetical's CONTENT counts toward the 24-char limit (only
    # the bracket characters themselves are excluded) -- this 30+
    # character note pushes the label over the limit.
    repo, rev = _label_scenario(
        tmp_path,
        "WP-3 (この規則は現在も有効な安全上の理由を説明する長い注記です)：本文です。",
        "本文です。",
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (3)" in output


def test_label_removal_separator_inside_code_span_is_red(tmp_path):
    # The ": " inside the backtick span is not a valid separator; the
    # actual (invalid) edit below assumes it was.
    repo, rev = _label_scenario(
        tmp_path, "WP-3 `x: y` more: body stays.", "y` more: body stays."
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (3)" in output


def test_label_removal_invariant_branch_protected_is_red(tmp_path):
    # SI-08 is protected -- it may never merge with a following branch
    # number, and (being the only marker) this label has no qualifying
    # unprotected marker either.
    repo, rev = _label_scenario(tmp_path, "Invariant SI-08 (2): body.", "body.")
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (3)" in output


def test_label_word_tokens_does_not_merge_protected_id_branch():
    # White-box: rule (c)'s hard exclusion (any protected reference
    # disqualifies the whole label outright) makes it impossible to
    # observe the branch-merge restriction end-to-end through
    # `_run_base` -- a label with a protected ID is always rejected
    # regardless of how it tokenizes. So this pins the tokenizer directly:
    # SI-08 (protected) must NOT merge with a following "(2)" branch the
    # way an unprotected ID would.
    tokens = cp._label_word_tokens("Invariant SI-08 (2) rule", frozenset())
    content_words = [t for t, is_content in tokens if is_content]
    assert "SI-08" in content_words


def test_label_removal_roadmap_tagged_id_is_red(tmp_path):
    repo, rev = _label_scenario(tmp_path, "roadmap R-22: body.", "body.")
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (3)" in output


def test_label_has_provenance_marker_ignores_tagged_bare_id():
    # White-box: same reasoning as above -- rule (c) ALSO independently
    # rejects "roadmap R-22" (a provenance-tagged bare ID is itself a
    # "protected reference" per the supervisor ruling), so condition (1)'s
    # own tag-check can't be isolated end-to-end either.
    assert cp._label_has_provenance_marker("roadmap R-22", frozenset()) is False


def test_label_removal_negation_word_is_red(tmp_path):
    repo, rev = _label_scenario(tmp_path, "Never (WP-3): retry.", "retry.")
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (3)" in output


def test_label_removal_protected_plus_token_is_red(tmp_path):
    # SI-08 (a protected reference) co-occurs with WP-3 (a real token) --
    # the protected reference still disqualifies the whole label.
    repo, rev = _label_scenario(tmp_path, "SI-08 WP-3: body.", "body.")
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (3)" in output


# ===========================================================================
# Change set 0b, review round 3 (monitor ruling, final/small): (a) revert
# _FILENAME_EXT_RE + versioned-document-name provenance tag, applied to
# both (4) and (6); (b)/(c) e2e fixtures.
# ===========================================================================

def test_label_removal_japanese_forbidden_word_is_red(tmp_path):
    repo, rev = _label_scenario(tmp_path, "これは禁止 (WP-3)：本文。", "本文。")
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (3)" in output


def test_label_removal_english_no_is_red(tmp_path):
    repo, rev = _label_scenario(tmp_path, "No retry (WP-3): body.", "body.")
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (3)" in output


def test_label_removal_extensionless_path_word_is_red(tmp_path):
    repo, rev = _label_scenario(tmp_path, "(docs/x R-2, WP-3): body.", "body.")
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (3)" in output


def test_label_removal_roadmap_tagged_id_with_token_is_red(tmp_path):
    # Unlike the plain "roadmap R-22: body." case, WP-3 alone would
    # satisfy condition (1) -- the roadmap tag must still block R-22 and
    # disqualify the whole label via the protected-reference rule.
    repo, rev = _label_scenario(tmp_path, "roadmap R-22 (WP-3): body.", "body.")
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (3)" in output


def test_label_removal_contract_version_tagged_is_red(tmp_path):
    # "Contract 1.7.0" is a versioned document name -- D-2 is tagged by
    # it and may not be removed, even with the branch number merged.
    repo, rev = _label_scenario(
        tmp_path, "Contract 1.7.0 (D-2 (4), WP-2a): body.", "body."
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (3)" in output


def test_label_removal_design_version_tagged_is_red(tmp_path):
    repo, rev = _label_scenario(tmp_path, "design v1.2 R-4 (WP-1): body.", "body.")
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (3)" in output


def test_label_removal_design_version_tagged_no_dot_is_red(tmp_path):
    # Same as above but with a dot-less version ("v12"), so the (reverted,
    # wide) _FILENAME_EXT_RE has no "." to coincidentally latch onto --
    # this isolates the versioned-document-name check specifically.
    repo, rev = _label_scenario(tmp_path, "design v12 R-4 (WP-1): body.", "body.")
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (3)" in output


def test_label_removal_lowercased_remainder_is_red(tmp_path):
    # §8.3 (3): the remainder must stay byte-for-byte -- no reshaping.
    repo, rev = _label_scenario(tmp_path, "Ruling U-7 (WP-6d): Reason stays.", "reason stays.")
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (3)" in output


def test_label_removal_separator_kept_is_red(tmp_path):
    # §8.3 (4): only the label itself may be removed, not the separator.
    repo, rev = _label_scenario(
        tmp_path, "Ruling U-7 (WP-6d): reason stays.", ": reason stays."
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (3)" in output


def test_label_removal_extra_word_deleted_is_red(tmp_path):
    # §8.3 (5): the remainder itself must not lose an extra word.
    repo, rev = _label_scenario(
        tmp_path, "Ruling U-7 (WP-6d): the reason stays clear.", "the reason stays."
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (3)" in output


def test_label_removal_no_provenance_marker_is_red(tmp_path):
    repo, rev = _label_scenario(tmp_path, "Note carefully: reason.", "reason.")
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (3)" in output


def test_label_removal_no_real_separator_is_red(tmp_path):
    # No `: ` / `：` / ` -- ` / ` — ` anywhere -- the whole sentence must
    # stay verbatim; a single hyphen is NOT a recognized separator.
    repo, rev = _label_scenario(
        tmp_path,
        "WP-4 forever - stays the same reasoning.",
        "stays the same reasoning.",
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (3)" in output


# ===========================================================================
# Change set 0c: design §9 (v0.6) rule-hole fixes, §9.1 fixtures.
# ===========================================================================

# --- rule 1: multi-word history tokens ------------------------------------

def test_0c_rule1_multiword_token_full_removal_is_green(tmp_path):
    repo, rev = _label_scenario(
        tmp_path, "Note (Phase 10, WP-6d-i review): body.", "Note: body."
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 0, output


def test_0c_rule1_lowercase_monitor_ruling_is_green(tmp_path):
    repo, rev = _label_scenario(
        tmp_path, "Note (monitor ruling, WP-2): body.", "Note: body."
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 0, output


# --- rule 2: real-filename-only provenance --------------------------------

def _real_paths_scenario(tmp_path, old_first_sentence: str, new_first_sentence: str, extra_files=()):
    """Like `_label_scenario`, but commits `extra_files` ({rel: content})
    into the basis commit first, so `_tree_paths` sees them as real."""
    repo = _init_repo(tmp_path)
    for rel, content in extra_files:
        _write(repo, rel, content)
    old_block_lines = [f"# {old_first_sentence}", "# Moved."]
    old = "\n".join(old_block_lines) + "\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    new = f"# {new_first_sentence}\n# history: CH-0001\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", new)
    _write(
        repo, "docs/code-history/r2db-api/mod.md",
        _companion_section("CH-0001", "\n".join(old_block_lines)),
    )
    return repo, rev


def test_0c_rule2_fake_scratchpad_path_paren_is_green(tmp_path):
    repo, rev = _real_paths_scenario(
        tmp_path, "Note (D-3, {scratchpad}/review2/frame.md): body.", "Note: body."
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 0, output


def test_0c_rule2_fake_backtick_path_leaves_non_id_residue_is_green(tmp_path):
    repo, rev = _real_paths_scenario(
        tmp_path,
        "Store (`{scratchpad}/review2/frame.md` F-①, WP-6d): body.",
        "Store (F-①): body.",
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 0, output


def test_0c_rule2_wrapped_backtick_path_is_green(tmp_path):
    # A physical line-wrap inside the backtick span joins to one space
    # (via `_flatten_comment`) well before this check runs; that space is
    # stripped again when checking tree-membership, so the whole span is
    # treated as ONE word either way -- a non-real path, hence removable.
    repo = _init_repo(tmp_path)
    old_block_lines = [
        "# Note (D-3, `{scratchpad}/rulings-r3-",
        "# r7-flip.md`): body.",
        "# Moved.",
    ]
    old = "\n".join(old_block_lines) + "\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    new = "# Note: body.\n# history: CH-0001\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", new)
    _write(
        repo, "docs/code-history/r2db-api/mod.md",
        _companion_section("CH-0001", "\n".join(old_block_lines)),
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 0, output


def test_0c_rule2_unprefixed_working_note_name_is_green(tmp_path):
    # No `{scratchpad}/` prefix at all, and this name was never committed
    # -- design §9 rule 2's other example of "not real".
    repo, rev = _real_paths_scenario(
        tmp_path, "Note (D-3, rulings-r5-r6.md): body.", "Note: body."
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 0, output


def test_0c_rule2_real_file_stays_protective_is_red(tmp_path):
    # Regression: a filename that DOES exist in the basis tree must still
    # protect its co-located ID (§9 rule 2 only removes protection from
    # FAKE filenames, never from real ones).
    repo, rev = _real_paths_scenario(
        tmp_path,
        "Store (`docs/design/Y_V1.md` R-9): body.",
        "Store: body.",
        extra_files=[("docs/design/Y_V1.md", "stub\n")],
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (3)" in output


def test_0c_rule2_read_write_paren_unchanged_is_red(tmp_path):
    # Fixture 5: "(read/write, R-5)" is unaffected by rule 2/4 -- attempting
    # any removal here is invalid.
    repo, rev = _real_paths_scenario(
        tmp_path, "Note (read/write, R-5): body.", "Note: body."
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (3)" in output


# --- rule 3: kind-word-only residue after (4) reduction --------------------

def test_0c_rule3_kind_word_residue_removed_is_green(tmp_path):
    repo, rev = _label_scenario(
        tmp_path, "Note (design D-4, WP-2): body.", "Note: body."
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 0, output


def test_0c_rule3_original_kind_word_only_paren_stays_is_red(tmp_path):
    # A parens that held ONLY a kind word from the start is never touched.
    repo, rev = _label_scenario(
        tmp_path, "Note (design): body.", "Note: body."
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (3)" in output


def test_0c_rule3_versioned_doc_blocks_rule3_is_green(tmp_path):
    # Only WP-2 goes; rule 3 must NOT sweep away "(design v1.2)" since a
    # versioned document name remains.
    repo, rev = _label_scenario(
        tmp_path, "Note (design v1.2, WP-2): body.", "Note (design v1.2): body."
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 0, output


# --- rule 4: `/`-joined ID splitting ---------------------------------------

def test_0c_rule4_slash_joined_ids_removed_is_green(tmp_path):
    repo, rev = _label_scenario(tmp_path, "Note (M-3/D): body.", "Note: body.")
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 0, output


def test_0c_rule4_protected_slash_id_partial_removal_is_green(tmp_path):
    # SI-08 stays protected; R-5 alone is still an ordinary removable bare
    # ID (rule 4 just declines to treat the PAIR as a slash-ID shortcut).
    repo, rev = _label_scenario(
        tmp_path, "Note (SI-08/R-5): body.", "Note (SI-08): body."
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 0, output


# --- rule 5: slash-ID + branch-number combination, contract clause --------

def test_0c_rule5_slash_and_branch_combo_is_green(tmp_path):
    repo, rev = _label_scenario(tmp_path, "Note (I-6/D-5 (5)): body.", "Note: body.")
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 0, output


def test_0c_rule5_contract_clause_with_provenance_unchanged_is_red(tmp_path):
    repo, rev = _label_scenario(
        tmp_path, "Note (contract 1.7.0 D-5): body.", "Note: body."
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (3)" in output


# --- items 9-11: label negation, added-line tokens, round exclusion -------

def test_0c_negation_monitor_ruling_label_is_red(tmp_path):
    repo, rev = _label_scenario(
        tmp_path, "Never (Monitor ruling M-4): retry.", "retry."
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (3)" in output


def test_0c_added_line_requester_ruling_is_red(tmp_path):
    repo = _init_repo(tmp_path)
    old = "# Keep.\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    new = "# Keep.\n\n# Per the Requester ruling, this changed.\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", new)
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (5)" in output


def test_0c_round_unit_exclusion_paren_removal_is_red(tmp_path):
    repo, rev = _label_scenario(
        tmp_path, "Note (round 2 decimal places): body.", "Note: body."
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (3)" in output


def test_0c_round_unit_exclusion_label_removal_is_red(tmp_path):
    repo, rev = _label_scenario(
        tmp_path, "Round 2 digits: body stays put here now.", "body stays put here now."
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (3)" in output


def test_0c_round_unit_exclusion_added_line_is_green(tmp_path):
    # A trailing/inline comment (design v0.4 ruling: excluded from block
    # extraction, but the (5) added-history-token scan still reads it) --
    # isolates this fixture to the (5) concern alone.
    repo = _init_repo(tmp_path)
    old = "def f():\n    x = 1\n    return x\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    new = "def f():\n    x = 1  # uses round 2 decimal places for the total\n    return x\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", new)
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 0, output


# ===========================================================================
# Q-4 supervisor ruling (0c): re-edit of an already-CH-ID'd block. No new
# id is allocated; the existing companion section is not rewritten (D-1).
# Containment is derivability via (3)(4)(6)+§9, not a byte/sentence-exact
# match (fixed per the reviewer report on q4repo/rev-cs2, postgres.py
# CH-0001 false-red).
# ===========================================================================

def test_q4_reedit_further_label_and_paren_removal_is_green(tmp_path):
    # Companion (v0.5-era first move) holds the full original text. The
    # basis block already reduced it once (label removed by an earlier
    # change set) and keeps CH-0001; this diff reduces it a second time
    # (the now-lone bare id "(R-2)" is removed by (4)) -- same CH-0001,
    # no new id, companion untouched.
    repo = _init_repo(tmp_path)
    old = "# body (R-2).\n# history: CH-0001\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    new = "# body.\n# history: CH-0001\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", new)
    _write(
        repo, "docs/code-history/r2db-api/mod.md",
        _companion_section("CH-0001", "# Note (WP-3): body (R-2).\n# Moved."),
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 0, output


def test_q4_reedit_sentence_not_in_companion_is_red(tmp_path):
    # The basis block carries a sentence the companion section does not
    # contain (in any derivable form) -- e.g. added after the companion
    # snapshot was taken, then deleted here. Must be red, not silently
    # accepted as a "further reduction".
    repo = _init_repo(tmp_path)
    old = "# body (R-2). Extra note.\n# history: CH-0001\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    new = "# body. Extra note.\n# history: CH-0001\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", new)
    _write(
        repo, "docs/code-history/r2db-api/mod.md",
        _companion_section("CH-0001", "# Note (WP-3): body (R-2).\n# Moved."),
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "not derivable from the existing companion section" in output


def test_q4_reedit_id_swapped_to_different_section_is_red(tmp_path):
    # The basis block's own CH-0001 marker is replaced by a different,
    # also-existing section's id (CH-0002) instead of being reused. The
    # basis block's own CH-0001 reference then goes unmatched.
    repo = _init_repo(tmp_path)
    old = "# body.\n# history: CH-0001\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    new = "# body.\n# history: CH-0002\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", new)
    _write(
        repo, "docs/code-history/r2db-api/mod.md",
        _companion_section("CH-0001", "# body.") + _companion_section("CH-0002", "# body."),
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "was not matched by any new block" in output


# ===========================================================================
# v0.7 supervisor ruling (0c follow-up): §4.1 (3)/(4)/(6) and §9 rules 1-4
# are each a PERMISSION, not an obligation. The derivation check accepts
# ANY subset of the allowed operations, not only the maximal reduction --
# e.g. change set 1 leaving a lone kind word like "(ruling)" behind
# instead of also sweeping it per §9 rule 3 is just as valid as sweeping
# it. Q-4 (CH-0001) itself is unchanged by this ruling.
# ===========================================================================

def test_v07_partial_rule3_reduction_is_green(tmp_path):
    # A human editor may remove the bare id from a parenthetical via (4)
    # and STOP there, leaving the lone kind word "ruling" unswept -- §9
    # rule 3's sweep is a permission, not an obligation.
    repo, rev = _label_scenario(
        tmp_path, "Note (ruling I-7/D-4): body.", "Note (ruling): body."
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 0, output


def test_v07_maximal_rule3_reduction_still_green(tmp_path):
    # The maximal reduction (rule 3's sweep actually applied) must remain
    # an equally valid, reachable outcome.
    repo, rev = _label_scenario(
        tmp_path, "Note (ruling I-7/D-4): body.", "Note: body."
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 0, output


# Retired (R-37 WP-3f, ruling W3-18): the fixed-anchor re-edit branch can never
# stay derivable once a migrated CH block gains a position parenthetical; see test_0f.


def test_v07_rule3_broadened_would_break_real_repo_is_red_when_mandatory():
    # White-box companion to the mutation "revert rule 3 to mandatory":
    # isolates the exact real-repo sentence pair (CH-0028) so the
    # regression is visible without needing the whole real file. Directly
    # exercises `_is_allowed_reduction`, not an e2e `_run_base` scenario.
    old_full = "A `dry_run` never consults or writes a record (ruling I-7/D-4)."
    retained = "A `dry_run` never consults or writes a record (ruling)."
    ok, _reason = cp._is_allowed_reduction("comment", old_full, retained, frozenset())
    assert ok is True


# --- fixtures isolating the 4 mutations the first 0c mutation run missed ---
# (note: the "rule1_broadened" mutation -- removing the round-unit
# negative lookahead -- is caught by the EXISTING
# test_0c_round_unit_exclusion_added_line_is_green fixture above; the
# paren-removal fixture doesn't catch it because leftover "decimal"/
# "places" words mask the regression there.)

def test_0c_rule2_dotted_backtick_identifier_not_a_filename_is_red(tmp_path):
    # A backtick-quoted, dotted CODE identifier that is neither a real
    # path nor ends in a KNOWN extension must never be treated as a
    # (fake, hence removable) filename candidate -- this is the exact
    # real-world corruption `_FILENAME_EXT_RE`'s narrowing fixed
    # (`` `information_schema.columns.domain_name` ``-shaped content).
    repo, rev = _label_scenario(
        tmp_path,
        "Body text stays (`schema.columns.name`) as is.",
        "Body text stays as is.",
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (3)" in output


def test_0c_rule4_readwrite_id_stays_protected_is_red(tmp_path):
    # "(read/write, R-5)" as a whole is already covered by
    # test_0c_rule2_read_write_paren_unchanged_is_red (full removal
    # attempt). This isolates the PARTIAL leak an over-broadened
    # `_SUBSCRIPT_RE` introduces: "read/write" no longer registers as
    # path-like, so it stops protecting the co-located bare id "R-5" --
    # removing R-5 ALONE while leaving "read/write" untouched must still
    # be rejected.
    repo, rev = _real_paths_scenario(
        tmp_path, "Note (read/write, R-5): body.", "Note (read/write): body."
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (3)" in output


def test_0c_history_token_branch_merge_crosses_content_word_limit_is_green(tmp_path):
    # Unlike test_label_removal_with_branch_number_is_green (content-word
    # count stays under the limit with or without the merge), this label
    # is built so the branch-number merge is NECESSARY for it to qualify
    # at all: merged, content words are "Ruling"/"Pool"/"Lock" (3, at the
    # limit); without the merge, "WP-6d-i" and "(ii)" would be counted as
    # separate tokens and "ii" would stand alone as a 4th content word,
    # crossing the <=3 limit and disqualifying the whole label.
    repo, rev = _label_scenario(
        tmp_path, "Ruling Pool Lock U-7 (WP-6d-i (ii)): reason.", "reason."
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 0, output


# ===========================================================================
# v0.7 supervisor ruling, second follow-up: (1) an unprefixed (basename-
# only) filename is STILL a provenance tag if its basename matches
# EXACTLY ONE path in the tree; 0 or >=2 matches keep it a removable
# history token. (2) `_is_allowed_reduction` judges each independent SITE
# (each parenthetical; the leading label) on its own via a single left-
# to-right scan, not by enumerating subsets -- so there is no length cap.
# ===========================================================================

def test_v072_unique_basename_filename_protects_is_red(tmp_path):
    # `CONTROL_MAPPING.md` has no path separator but its basename matches
    # exactly one real path (`security/CONTROL_MAPPING.md`) -- it counts
    # as a provenance tag, so SI-10 stays protected too.
    repo, rev = _real_paths_scenario(
        tmp_path, "Note (CONTROL_MAPPING.md, SI-10): body.", "Note: body.",
        extra_files=[("security/CONTROL_MAPPING.md", "stub\n")],
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (3)" in output


def test_v072_unique_basename_filename_alone_protects_is_red(tmp_path):
    # Isolates the basename-uniqueness check itself from SI-10's OWN,
    # independent protected-prefix protection (the fixture above keeps
    # its outcome even if the filename check is removed entirely, since
    # SI-10 alone already blocks full removal) -- here nothing BUT the
    # unique-basename match protects the parenthetical.
    repo, rev = _real_paths_scenario(
        tmp_path, "Note (CONTROL_MAPPING.md): body.", "Note: body.",
        extra_files=[("security/CONTROL_MAPPING.md", "stub\n")],
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (3)" in output


def test_v072_nonexistent_basename_filename_removable_is_green(tmp_path):
    # No file anywhere in the tree has this basename -- 0 matches, stays
    # a removable history token (unchanged from the original §9 rule 2).
    repo, rev = _label_scenario(
        tmp_path, "Note (D-3, rulings-r5-r6.md): body.", "Note: body."
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 0, output


def test_0i_rule3_ambiguous_basename_is_real_is_red(tmp_path):
    # design 9.2 rule 3 (Z0i-2 (A), change set 0i, monitor ruling):
    # `README.md` exists at TWO different paths -- under 0c/pre-0i this
    # stayed a removable history token (ambiguous); under 0i, a basename
    # match count of >=1 (not ==1) is enough to make it real, so it now
    # protects its co-located ID instead. Replaces (old name recorded in
    # the work order 15.4) `test_v072_ambiguous_basename_filename_removable_is_green`,
    # whose expectation this inverts.
    repo, rev = _real_paths_scenario(
        tmp_path, "Note (README.md, D-3): body.", "Note: body.",
        extra_files=[("a/README.md", "stub\n"), ("b/README.md", "stub\n")],
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (3)" in output


def test_v072_unique_basename_matches_real_repo_control_mapping(tmp_path):
    # Confirms the real repository actually has exactly one
    # `CONTROL_MAPPING.md` (under security/) -- the precondition the
    # first fixture above relies on, pinned directly against HEAD's tree.
    real_paths = cp._tree_paths(REAL_REPO_ROOT, "HEAD")
    matches = [p for p in real_paths if p.rpartition("/")[2] == "CONTROL_MAPPING.md"]
    assert matches == ["security/CONTROL_MAPPING.md"], matches


def test_v072_unique_basename_is_real():
    # F8 (code review, nit): renamed from
    # test_v072_mutation_basename_uniqueness_removed_would_break_control_mapping
    # (work order §15.4) -- since the `== 1` assert this pinned was
    # removed (Z0i-2 (A)), the old name described a mutation that no
    # longer exists. White-box companion pinning the unique-basename-
    # real precondition test_v072_unique_basename_matches_real_repo_
    # control_mapping relies on. (The ambiguous-README.md half of the
    # original assertion moved to test_0i_rule3_ambiguous_basename_is_
    # real_is_red, since >=2 matches is now REAL, the opposite of what
    # this pinned.)
    real_paths = frozenset({"security/CONTROL_MAPPING.md"})
    assert cp._is_real_filename_candidate("CONTROL_MAPPING.md", real_paths) is True


def test_v072_long_sentence_partial_reduction_of_one_of_three_parens_is_green(tmp_path):
    # 30+ words, 3 independent parenthetical sites, one per physical line
    # (so only the MIDDLE line's own diff is scanned by §4.1 (5) -- the
    # untouched "(WP-3)" line must not itself trip an added-token false
    # positive) -- only the middle parenthetical is PARTIALLY reduced
    # (its 3 words are "design"/D-4/WP-2; only WP-2 is removed, "design
    # D-4" stays -- a genuine partial retention inside a >2-word paren,
    # not one of the 2 "extremes" a length-capped check could still
    # coincidentally accept); the other two parens stay untouched. The
    # first (subset-enumeration) form of the permissive check capped
    # parenthetical size and would have rejected this once the sentence
    # grew long enough to matter; the per-site linear scan has no cap.
    repo = _init_repo(tmp_path)
    old_block_lines = [
        "# Alpha bravo charlie delta echo (SI-08) foxtrot golf hotel india juliet",
        "# kilo lima (design D-4, WP-2) mike november oscar papa quebec romeo",
        "# sierra tango uniform (WP-3) victor whiskey xray yankee zulu end.",
        "# Moved.",
    ]
    old = "\n".join(old_block_lines) + "\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    new = (
        "# Alpha bravo charlie delta echo (SI-08) foxtrot golf hotel india juliet\n"
        "# kilo lima (design D-4) mike november oscar papa quebec romeo\n"
        "# sierra tango uniform (WP-3) victor whiskey xray yankee zulu end.\n"
        "# history: CH-0001\ndef f():\n    return 1\n"
    )
    _write(repo, "r2db-api/src/r2db_api/mod.py", new)
    _write(
        repo, "docs/code-history/r2db-api/mod.md",
        _companion_section("CH-0001", "\n".join(old_block_lines)),
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 0, output


def test_v072_long_sentence_one_word_substitution_in_paren_is_red(tmp_path):
    # Same 3-line sentence, but the middle parenthetical's content is
    # CHANGED (WP-2 -> WP-9) rather than reduced by an allowed operation
    # -- must be rejected, not silently accepted as "close enough".
    repo = _init_repo(tmp_path)
    old_block_lines = [
        "# Alpha bravo charlie delta echo (SI-08) foxtrot golf hotel india juliet",
        "# kilo lima (design D-4, WP-2) mike november oscar papa quebec romeo",
        "# sierra tango uniform (WP-3) victor whiskey xray yankee zulu end.",
        "# Moved.",
    ]
    old = "\n".join(old_block_lines) + "\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    new = (
        "# Alpha bravo charlie delta echo (SI-08) foxtrot golf hotel india juliet\n"
        "# kilo lima (design D-4, WP-9) mike november oscar papa quebec romeo\n"
        "# sierra tango uniform (WP-3) victor whiskey xray yankee zulu end.\n"
        "# history: CH-0001\ndef f():\n    return 1\n"
    )
    _write(repo, "r2db-api/src/r2db_api/mod.py", new)
    _write(
        repo, "docs/code-history/r2db-api/mod.md",
        _companion_section("CH-0001", "\n".join(old_block_lines)),
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (3)" in output


# ===========================================================================
# 0c review round: (1) versioned-doc dot false positive when locating a
# parenthetical's end anchor, (2) separator-aware paren matching, (3)
# supervisor ruling narrowing §4.1 (5) to a token-level diff against the
# basis. Cross-checked against the reviewer's own probe9.py/probe10.py
# (scratchpad rev-ccp0/) -- every one of their ~40 labeled cases agrees
# with this implementation.
# ===========================================================================

def test_review_t9_versioned_doc_dot_anchor_is_green(tmp_path):
    # `end = target.find(next_txt, pos)` used to stop at the FIRST "."
    # inside "1.7.0" itself (next_txt here is just "."), truncating the
    # candidate span before the real closing paren -- try every
    # occurrence, not just the first.
    repo, rev = _label_scenario(
        tmp_path, "Pool (contract 1.7.0 D-5, WP-2c).", "Pool (contract 1.7.0 D-5)."
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 0, output


def test_review_design_v1_2_dot_anchor_is_green(tmp_path):
    repo, rev = _label_scenario(
        tmp_path, "Note (design v1.2 R-4, WP-4).", "Note (design v1.2 R-4)."
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 0, output


def test_review_t1_separator_comma_to_space_is_red(tmp_path):
    repo, rev = _label_scenario(tmp_path, "Pool (SI-08, C-05) stays.", "Pool (SI-08 C-05) stays.")
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (3)" in output


def test_review_t2_separator_comma_to_slash_is_red(tmp_path):
    repo, rev = _label_scenario(tmp_path, "Pool (SI-08, C-05) stays.", "Pool (SI-08/C-05) stays.")
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (3)" in output


def test_review_t3_dangling_separator_is_red(tmp_path):
    repo, rev = _label_scenario(tmp_path, "Pool (R-5, SI-08) stays.", "Pool (, SI-08) stays.")
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (3)" in output


def test_review_t4_dangling_slash_separator_is_red(tmp_path):
    repo, rev = _label_scenario(tmp_path, "Pool (M-3/D) stays.", "Pool (/D) stays.")
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (3)" in output


def test_review_middle_word_removal_keeps_correct_separator_is_green(tmp_path):
    # Removing the MIDDLE word "WP-3" must reconnect SI-08 and C-05 with
    # their OWN original mutual separator (", "), not lose track of it.
    repo, rev = _label_scenario(
        tmp_path, "Pool (SI-08, WP-3, C-05) stays.", "Pool (SI-08, C-05) stays."
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 0, output


def test_review_n4_partial_keeps_existing_token_is_green(tmp_path):
    # supervisor ruling: (5) flags only a history token ABSENT from the
    # basis -- "round 2" already existed in the basis paren, so keeping
    # it while removing WP-3/R-5 is not itself an added-token violation.
    repo, rev = _label_scenario(
        tmp_path, "Pool (WP-3, round 2, R-5) stays.", "Pool (round 2) stays."
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 0, output


def test_review_added_line_new_token_not_in_basis_is_red(tmp_path):
    repo = _init_repo(tmp_path)
    old = "def f():\n    x = 1  # note (WP-3) here\n    return x\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    new = "def f():\n    x = 1  # note (WP-3, WP-9) here\n    return x\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", new)
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (5)" in output


def test_check_no_added_history_tokens_basis_diff_direct():
    # White-box: same N4/WP-9 pair, calling the (5) checker directly.
    old_n4 = "x = 1  # note (WP-3, round 2, R-5) here\n"
    new_n4 = "x = 1  # note (round 2) here\n"
    assert cp.check_no_added_history_tokens(old_n4, new_n4) == []

    old_wp9 = "x = 1  # note (WP-3) here\n"
    new_wp9 = "x = 1  # note (WP-3, WP-9) here\n"
    hits = cp.check_no_added_history_tokens(old_wp9, new_wp9)
    assert len(hits) == 1 and "WP-" in hits[0][2]


# ===========================================================================
# reviewer-planned mutations (0c review round item 4).
# ===========================================================================

def test_review_q4_scope_mismatch_rejected_is_red(tmp_path):
    # Q-4's reedit_candidates lookup must stay scoped to the SAME scope as
    # the referencing new block. g() wrongly claims f()'s already-migrated
    # CH-0001 -- without the scope check this cross-scope reuse would be
    # silently accepted using f's basis block as g's "reedit" predecessor.
    repo = _init_repo(tmp_path)
    old = (
        "def f():\n    # body (R-2).\n    # history: CH-0001\n    return 1\n\n\n"
        "def g():\n    return 2\n"
    )
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    new = (
        "def f():\n    return 1\n\n\n"
        "def g():\n    # body.\n    # history: CH-0001\n    return 2\n"
    )
    _write(repo, "r2db-api/src/r2db_api/mod.py", new)
    _write(
        repo, "docs/code-history/r2db-api/mod.md",
        _companion_section("CH-0001", "Note (WP-3): body (R-2)."),
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (2)" in output


def test_review_tree_paths_uses_base_rev_not_head_is_red(tmp_path):
    # `_tree_paths` for `--base <rev>` must use the BASIS revision's tree,
    # never HEAD's -- a file added AFTER the basis commit must not count
    # as "real" when judging the basis's own comment content.
    repo = _init_repo(tmp_path)
    old_lines = ["# Note (D-3, notes_added_later.md): body.", "# Moved."]
    _write(repo, "r2db-api/src/r2db_api/mod.py", "\n".join(old_lines) + "\ndef f():\n    return 1\n")
    rev = _commit_all(repo, "old")
    # AFTER the basis commit, a file with this exact basename appears --
    # if `_tree_paths` used HEAD instead of `rev`, it would wrongly treat
    # the basis's filename mention as real (protecting it, and D-3).
    _write(repo, "notes_added_later.md", "stub\n")
    new = "# Note: body.\n# history: CH-0001\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", new)
    _write(
        repo, "docs/code-history/r2db-api/mod.md",
        _companion_section("CH-0001", "\n".join(old_lines)),
    )
    _commit_all(repo, "add notes file (after basis)")
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 0, output


def test_review_backtick_stripped_before_tree_check_is_red(tmp_path):
    # `_clean_filename_candidate` must strip the surrounding backticks
    # before the tree-membership check -- a real file referenced WITHOUT
    # backticks in the comment must still be recognized (and protect its
    # co-located id), not be treated as fake merely because the raw
    # candidate text (with backticks) never appears verbatim in the tree.
    repo, rev = _real_paths_scenario(
        tmp_path, "Store (`docs/design/X_V1.md` R-9): body.", "Store: body.",
        extra_files=[("docs/design/X_V1.md", "stub\n")],
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (3)" in output


def test_review_slash_path_basename_match_not_real_is_green(tmp_path):
    # A candidate WITH a path separator ("x/CONTROL_MAPPING.md") must
    # never fall through to the basename-uniqueness check -- only an
    # EXACT full-path match counts as real for a "/"-containing
    # candidate, even when its basename uniquely matches a real file
    # elsewhere in the tree (`security/CONTROL_MAPPING.md`). So the fake
    # path is a removable history token, and the co-located bare id R-9
    # (no other provenance tag) is independently removable too.
    repo, rev = _real_paths_scenario(
        tmp_path, "Note (x/CONTROL_MAPPING.md, R-9): body.", "Note: body.",
        extra_files=[("security/CONTROL_MAPPING.md", "stub\n")],
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 0, output


# ===========================================================================
# Change set 0d (supervisor ruling): design §4.1 (3) whole-sentence
# deletion may never drop a sentence carrying a protected reference
# (SI-/C-/CCR- id, `spec §`, a versioned document name, or a real path in
# the basis tree). Mechanically stripping a history token from WITHIN a
# KEPT sentence via (4)/(6) is unaffected. HTTP status codes and error-
# code vocabulary are deliberately NOT protected by this tool. Cross-
# checked against the reviewer's probe12.py (scratchpad rev-ccp0/).
# ===========================================================================

def test_0d_delete_sentence_with_si_id_is_red(tmp_path):
    repo = _init_repo(tmp_path)
    old = "# Status 409 maps to CONFLICT (SI-08).\n# The body is JSON.\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    new = "# The body is JSON.\n# history: CH-0001\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", new)
    _write(
        repo, "docs/code-history/r2db-api/mod.md",
        _companion_section("CH-0001", "# Status 409 maps to CONFLICT (SI-08).\n# The body is JSON."),
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (3)" in output


def test_0d_delete_sentence_with_spec_section_is_red(tmp_path):
    repo = _init_repo(tmp_path)
    old = "# Error codes follow spec §7.3 exactly.\n# The body is JSON.\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    new = "# The body is JSON.\n# history: CH-0001\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", new)
    _write(
        repo, "docs/code-history/r2db-api/mod.md",
        _companion_section("CH-0001", "# Error codes follow spec §7.3 exactly.\n# The body is JSON."),
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (3)" in output


def test_0d_delete_negation_sentence_with_c_id_is_red(tmp_path):
    repo = _init_repo(tmp_path)
    old = "# Never retry a 503 here (C-12).\n# The body is JSON.\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    new = "# The body is JSON.\n# history: CH-0001\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", new)
    _write(
        repo, "docs/code-history/r2db-api/mod.md",
        _companion_section("CH-0001", "# Never retry a 503 here (C-12).\n# The body is JSON."),
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (3)" in output


def test_0d_delete_sentence_with_real_path_is_red(tmp_path):
    repo = _init_repo(tmp_path)
    _write(repo, "docs/design/X_V1.md", "stub\n")
    old = "# See `docs/design/X_V1.md` for details.\n# The body is JSON.\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    new = "# The body is JSON.\n# history: CH-0001\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", new)
    _write(
        repo, "docs/code-history/r2db-api/mod.md",
        _companion_section("CH-0001", "# See `docs/design/X_V1.md` for details.\n# The body is JSON."),
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (3)" in output


def test_0d_delete_sentence_with_versioned_doc_is_red(tmp_path):
    repo = _init_repo(tmp_path)
    old = "# Contract 1.7.0 governs this.\n# The body is JSON.\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    new = "# The body is JSON.\n# history: CH-0001\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", new)
    _write(
        repo, "docs/code-history/r2db-api/mod.md",
        _companion_section("CH-0001", "# Contract 1.7.0 governs this.\n# The body is JSON."),
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (3)" in output


def test_0d_paren_only_wp3_removal_kept_sentence_is_green(tmp_path):
    repo, rev = _label_scenario(tmp_path, "Rules (SI-08, WP-3) apply.", "Rules (SI-08) apply.")
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 0, output


def test_0d_delete_plain_history_sentence_is_green(tmp_path):
    repo = _init_repo(tmp_path)
    old = "# Phase 4 (design D-4) notes this.\n# The body is JSON.\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    new = "# The body is JSON.\n# history: CH-0001\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", new)
    _write(
        repo, "docs/code-history/r2db-api/mod.md",
        _companion_section("CH-0001", "# Phase 4 (design D-4) notes this.\n# The body is JSON."),
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 0, output


def test_0d_delete_http_status_only_sentence_is_green(tmp_path):
    # HTTP status codes and error-code vocabulary are NOT protected by
    # this tool (left to audit/conformance review).
    repo = _init_repo(tmp_path)
    old = "# Status 409 maps to CONFLICT.\n# The body is JSON.\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    new = "# The body is JSON.\n# history: CH-0001\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", new)
    _write(
        repo, "docs/code-history/r2db-api/mod.md",
        _companion_section("CH-0001", "# Status 409 maps to CONFLICT.\n# The body is JSON."),
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 0, output


# ===========================================================================
# Change set 0d code review round: (1) whole-block-moved-away must also
# check EVERY sentence for a protected reference, even when nothing at
# all is retained in code; (2) a trailing (tail-of-block) whole-sentence
# deletion needs its own fixture; (3) a line-wrap that splits an ID
# (`SI-` / `08`) must rejoin without a space before judgment, narrowly
# scoped to an ID-shaped split (not ordinary hyphenated English prose
# wraps -- confirmed against the real r2db `postgres.py` corpus).
# Cross-checked against the reviewer's probe13.py (scratchpad rev-ccp0/).
# ===========================================================================

def test_0d_whole_block_moved_with_protected_ref_is_red(tmp_path):
    # First-move (case A): nothing kept in code at all (`nb.retained_text`
    # empty) -- but the companion text being moved away still carries
    # SI-08, which must never fully disappear from the source silently.
    repo = _init_repo(tmp_path)
    old = "# Guarded by SI-08.\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    new = "# history: CH-0001\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", new)
    _write(
        repo, "docs/code-history/r2db-api/mod.md",
        _companion_section("CH-0001", "# Guarded by SI-08."),
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (3)" in output


def test_0d_whole_docstring_block_moved_with_protected_ref_is_red(tmp_path):
    repo = _init_repo(tmp_path)
    old = 'def f():\n    """Guarded by SI-08."""\n    return 1\n'
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    new = 'def f():\n    """History: CH-0001"""\n    return 1\n'
    _write(repo, "r2db-api/src/r2db_api/mod.py", new)
    _write(
        repo, "docs/code-history/r2db-api/mod.md",
        _companion_section("CH-0001", "Guarded by SI-08.", kind="docstring"),
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (3)" in output


def test_0d_whole_block_moved_without_protected_ref_is_green(tmp_path):
    repo = _init_repo(tmp_path)
    old = "# Phase 4 (design D-4) notes this.\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    new = "# history: CH-0001\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", new)
    _write(
        repo, "docs/code-history/r2db-api/mod.md",
        _companion_section("CH-0001", "# Phase 4 (design D-4) notes this."),
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 0, output


def test_0d_delete_trailing_protected_sentence_is_red(tmp_path):
    # Keep the FIRST sentence, delete a protected-reference sentence at
    # the TAIL of the block (old_sentences[j:], not a mid-block gap).
    repo = _init_repo(tmp_path)
    old = "# The body is JSON. Guarded by SI-08.\n# Moved.\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    new = "# The body is JSON.\n# history: CH-0001\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", new)
    _write(
        repo, "docs/code-history/r2db-api/mod.md",
        _companion_section("CH-0001", "# The body is JSON. Guarded by SI-08.\n# Moved."),
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (3)" in output


def test_0d_hyphen_wrapped_id_sentence_deleted_is_red(tmp_path):
    # "SI-" at the end of one comment line, "08" at the start of the
    # next -- must rejoin as "SI-08" BEFORE judgment, so the whole
    # sentence carrying it cannot be deleted.
    repo = _init_repo(tmp_path)
    old = (
        "# Status 409 maps to CONFLICT per SI-\n"
        "# 08 here.\n"
        "# The body is JSON.\n"
        "# Moved.\n"
        "def f():\n    return 1\n"
    )
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    new = "# The body is JSON.\n# history: CH-0001\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", new)
    _write(
        repo, "docs/code-history/r2db-api/mod.md",
        _companion_section(
            "CH-0001",
            "# Status 409 maps to CONFLICT per SI-\n# 08 here.\n# The body is JSON.\n# Moved.",
        ),
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (3)" in output


def test_join_wrapped_lines_hyphenated_compound_joins_with_zero_space():
    # change set 0e (supervisor ruling, corrects this test's own change-
    # set-0d-era assumption): a real-corpus check during the change-set-3
    # re-review found `postgres.py` ITSELF already carrying the broken
    # "confirmed- destructive" / "table- level" forms of this exact
    # split -- the old assumption that ordinary hyphenated English
    # compounds deliberately keep their space when wrapped was wrong;
    # both an ID-shaped split and an ordinary hyphenated compound now
    # join with zero space, uniformly (rule (b), §9e).
    assert cp._flatten_comment("# confirmed-\n# destructive") == "confirmed-destructive"
    assert cp._flatten_comment("# SI-\n# 08") == "SI-08"


def test_join_wrapped_lines_multiword_backtick_fragment_keeps_space():
    # change set 0e: a multi-word SQL/expression fragment quoted whole in
    # backticks, wrapped mid-phrase with NO `_`/`-`/`.` boundary marker at
    # the line break, keeps its space -- bare backtick-openness alone is
    # deliberately NOT a join trigger (real-corpus pin: `postgres.py`
    # CH-0045's own "`<predicate> AND\n_r2db_revision::text = $expected`"
    # and CH-0069's own "`SHARE\nMODE`" wraps).
    assert (
        cp._flatten_comment("# `<predicate> AND\n# _r2db_revision::text = $x`")
        == "`<predicate> AND _r2db_revision::text = $x`"
    )
    assert cp._flatten_comment("# `SHARE\n# MODE`") == "`SHARE MODE`"


def test_join_wrapped_lines_dot_inside_backtick_joins_with_zero_space():
    # change set 0e, predicate B rule 3 (supervisor ruling 2026-09-15
    # final unification): a `.` wrapped INSIDE a backtick span is always
    # attribute/method/path access, never a sentence-ending period --
    # joins with zero space regardless of whether the following word is
    # a file extension (contrast rule 4, the outside-backtick case,
    # which IS scoped to extensions only). ONE predicate now serves
    # detection, normalization, and a fresh join alike -- no more
    # narrow/broad split (that split itself caused false greens on
    # `` `conn. transaction()` ``/`self. _rate_windows`, since the
    # broader normalization silently absorbed the mismatch detection's
    # narrower rule was supposed to catch).
    assert cp._flatten_comment("# `table_info.\n# constraints`") == "`table_info.constraints`"
    assert cp._flatten_comment("# `conn.\n# transaction():`") == "`conn.transaction():`"
    assert cp._flatten("comment", "# `table_info.\n# constraints`") == "`table_info.constraints`"
    assert cp._flatten("comment", "# `conn.\n# transaction():`") == "`conn.transaction():`"


def test_0d_q4_reedit_to_empty_with_protected_ref_is_red(tmp_path):
    # Q-4 reedit path specifically (basis already carries CH-0001 with
    # SOME retained text) reduced all the way down to NOTHING but the
    # marker -- distinct from the first-move (case A) fixture above,
    # which never allocates a CH-ID in the basis at all.
    repo = _init_repo(tmp_path)
    old = "# Guarded by SI-08.\n# history: CH-0001\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    new = "# history: CH-0001\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", new)
    _write(
        repo, "docs/code-history/r2db-api/mod.md",
        _companion_section("CH-0001", "Guarded by SI-08."),
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (3)" in output


def test_0d_bare_real_path_mention_not_citation_shaped_is_red(tmp_path):
    # Supervisor ruling: a real-path mention protects a whole sentence
    # from deletion regardless of whether it's citation-shaped (e.g. in
    # parens alongside an id) -- an ordinary prose mention of where code
    # moved to is still a live signpost for the reader.
    repo = _init_repo(tmp_path)
    _write(repo, "r2db-api/src/r2db_api/audit_counts.py", "stub\n")
    old = "# The helper moved to `audit_counts.py`.\n# The body is JSON.\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    new = "# The body is JSON.\n# history: CH-0001\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", new)
    _write(
        repo, "docs/code-history/r2db-api/mod.md",
        _companion_section(
            "CH-0001", "# The helper moved to `audit_counts.py`.\n# The body is JSON."
        ),
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (3)" in output


# ===========================================================================
# change set 0e: broken line-wrap join detection (supervisor ruling,
# 2026-09-15, corrects change set 0d review round item 3)
# ===========================================================================

def test_0e_backtick_path_py_extension_zero_space_join():
    assert (
        cp._flatten_comment("# see `spec/data-service-api.v1.\n# json` for the schema.")
        == "see `spec/data-service-api.v1.json` for the schema."
    )


def test_0e_underscore_identifier_zero_space_join():
    assert cp._flatten_comment("# calls `violated_\n# declaration` here.") == "calls `violated_declaration` here."
    assert (
        cp._flatten_comment("# refuses `CAPABILITY_\n# UNSUPPORTED` outright.")
        == "refuses `CAPABILITY_UNSUPPORTED` outright."
    )


def test_0e_hyphen_compound_zero_space_join():
    assert (
        cp._flatten_comment("# the row is already-\n# committed here.") == "the row is already-committed here."
    )


def test_0e_dot_py_extension_outside_backtick_zero_space_join():
    assert cp._flatten_comment("# see control_main.\n# py for wiring.") == "see control_main.py for wiring."


def test_0e_sentence_end_period_before_capitalized_word_keeps_space():
    # No false red: an ordinary sentence boundary (period, then a new
    # sentence starting with a capitalized word that is NOT a known file
    # extension) must NOT be treated as a join-sensitive boundary.
    assert cp._flatten_comment("# End of sentence.\n# Next sentence starts here.") == (
        "End of sentence. Next sentence starts here."
    )


def test_0e_double_hyphen_em_dash_newline_keeps_space():
    # No false red: `--` (the em-dash-like separator used throughout this
    # codebase's comments) is explicitly excluded from the hyphen rule.
    assert cp._flatten_comment("# first clause --\n# second clause.") == "first clause -- second clause."


def test_0e_find_broken_line_wrap_joins_detects_broken_form():
    basis = "# see `spec/data-service-api.v1.\n# json` for the schema."
    broken_new = "# see `spec/data-service-api.v1. json` for the schema.\n# history: CH-0001"
    fixed_new = "# see `spec/data-service-api.v1.json` for the schema.\n# history: CH-0001"
    hits = cp.find_broken_line_wrap_joins("comment", basis, broken_new)
    assert hits == [("`spec/data-service-api.v1.json`", "`spec/data-service-api.v1. json`")]
    assert cp.find_broken_line_wrap_joins("comment", basis, fixed_new) == []


def test_0e_run_base_flags_broken_join_as_red(tmp_path):
    repo = _init_repo(tmp_path)
    old = (
        "# see `spec/data-service-api.v1.\n"
        "# json` for the schema. The body is JSON.\n"
        "def f():\n    return 1\n"
    )
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    broken = (
        "# see `spec/data-service-api.v1. json` for the schema. The body is JSON.\n"
        "# history: CH-0001\n"
        "def f():\n    return 1\n"
    )
    _write(repo, "r2db-api/src/r2db_api/mod.py", broken)
    _write(
        repo, "docs/code-history/r2db-api/mod.md",
        _companion_section(
            "CH-0001",
            "# see `spec/data-service-api.v1.\n# json` for the schema. The body is JSON.",
        ),
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§9e" in output
    assert "`spec/data-service-api.v1. json`" in output


def test_0e_run_base_green_when_join_fixed(tmp_path):
    repo = _init_repo(tmp_path)
    old = (
        "# see `spec/data-service-api.v1.\n"
        "# json` for the schema. The body is JSON.\n"
        "def f():\n    return 1\n"
    )
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    fixed = (
        "# see `spec/data-service-api.v1.json` for the schema. The body is JSON.\n"
        "# history: CH-0001\n"
        "def f():\n    return 1\n"
    )
    _write(repo, "r2db-api/src/r2db_api/mod.py", fixed)
    _write(
        repo, "docs/code-history/r2db-api/mod.md",
        _companion_section(
            "CH-0001",
            "# see `spec/data-service-api.v1.\n# json` for the schema. The body is JSON.",
        ),
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 0, output


def _check_rev_pair(repo_root, rel_path, old_source, new_source, real_paths, identifier_set, out, rev):
    """change set 0f (supervisor ruling 2026-09-15, fixing this test's
    own working-tree dependency): the SAME per-file checks `run_base`
    runs, but taking `old_source`/`new_source` directly instead of
    reading the working tree -- lets a test compare two REVISIONS (or a
    revision against itself) without ever touching the local worktree's
    own uncommitted state.

    `rev` (design docs/design/CODE_COMMENT_PROVENANCE_V1.md §9.3 rule 6):
    the companion AND its correction records are read from THIS rev too
    (never the working tree), so a "rev vs itself" comparison is built
    from one shared snapshot throughout -- an uncommitted, working-tree-
    only correction record must never perturb it."""
    had_failure = False
    try:
        old_sig = cp.ast_signature(old_source)
        new_sig = cp.ast_signature(new_source)
    except SyntaxError as exc:
        print(f"FAIL (§4.1 (1)) {rel_path}: could not parse ({exc})", file=out)
        return 1
    if old_sig != new_sig:
        print(f"FAIL (§4.1 (1)) {rel_path}: code changed (AST differs, docstrings excluded)", file=out)
        had_failure = True
    for lineno, line_text, pat in cp.check_no_added_history_tokens(old_source, new_source):
        print(f"FAIL (§4.1 (5)) {rel_path}:{lineno} added line carries a history token ({pat}): {line_text.strip()!r}", file=out)
        had_failure = True
    peer = Path(rel_path).parts[0]
    companion_lookup = cp._load_companion_lookup(repo_root, peer, rev=rev)
    corrections_lookup, corrections_errors = cp._load_corrections_lookup(repo_root, peer, rev=rev)
    for corr_err in corrections_errors:
        print(f"FAIL (§9f) {corr_err}", file=out)
        had_failure = True
    new_blocks = cp.extract_all_blocks(new_source)
    old_blocks = cp.extract_all_blocks(old_source)
    for msg in cp.check_provenance_semantics(
        rel_path, old_source, new_source, old_blocks, new_blocks, companion_lookup, real_paths, identifier_set,
        corrections_lookup,
    ):
        print(msg, file=out)
        had_failure = True
    for nb in new_blocks:
        if nb.history_id is None:
            continue
        basis_text = companion_lookup.get(nb.history_id)
        if basis_text is None:
            continue
        for correct, broken in cp.find_broken_line_wrap_joins(nb.kind, basis_text, nb.dedented, identifier_set):
            print(f"FAIL (§9e) {rel_path} broken line-wrap join: {broken!r} should be {correct!r} (zero space)", file=out)
            had_failure = True
        if (
            nb.kind == "comment"
            and nb.retained_text
            and cp._is_colon_style_block(basis_text)
            and not cp._is_colon_style_block(nb.retained_text)
        ):
            print(
                f"FAIL (§9f) {rel_path} {nb.history_id}: '#:' Sphinx-style comment marker lost "
                "(basis used '#:' lines, new block does not)",
                file=out,
            )
            had_failure = True
    return 1 if had_failure else 0


def test_0f_both_peers_all_src_rev_vs_itself_is_green():
    # Regression safety, rewritten to be independent of the local
    # worktree's own uncommitted state (supervisor ruling 2026-09-15):
    # the previous version of this test compared the WORKING TREE
    # against HEAD, so it went red the instant ANY tracked .py file
    # under either peer's src/ had an uncommitted comment edit -- R-37
    # WP-1m hit exactly this in a different worktree (an unrelated
    # parenthetical edit looked like "an unregistered change" under
    # 40c). A checker must never depend on what else happens to be
    # sitting, uncommitted, in the same shared checkout. Instead this
    # compares HEAD's own blob against ITSELF (via `git show`, never
    # the working tree) for every tracked .py file in both peers' src/
    # -- content is byte-identical by construction, so nothing DIFFERS
    # for the AST/added-token/derivability checks to flag. §9e
    # (`find_broken_line_wrap_joins`) does not compare old vs new for
    # equality -- it asks "does this content still contain a broken
    # join relative to ITS OWN companion" -- so it is NOT automatically
    # green just because both sides are the same rev: it can genuinely,
    # correctly go red if HEAD's own committed blob still contains a
    # broken join relative to its companion's canonical text (design
    # ruling 2026-09-15 (c): no per-file exception list -- a red here
    # correctly catches real, still-uncommitted breakage left in HEAD,
    # and clears on its own the moment that breakage is committed, with
    # nothing to remove by hand).
    real_paths = cp._tree_paths(REAL_REPO_ROOT, "HEAD")
    identifier_set = cp._tracked_identifier_set(REAL_REPO_ROOT, "HEAD")
    r2db_src = REAL_REPO_ROOT / "r2db-api" / "src" / "r2db_api"
    mitatedb_src = REAL_REPO_ROOT / "MitateDB-api" / "src" / "mitatedb_api"
    rel_paths = [
        str(p.relative_to(REAL_REPO_ROOT))
        for base in (r2db_src, mitatedb_src)
        for p in sorted(base.glob("*.py"))
    ]
    out = io.StringIO()
    had_failure = False
    for rel_path in rel_paths:
        blob = subprocess.run(
            ["git", "show", f"HEAD:{rel_path}"], cwd=REAL_REPO_ROOT, capture_output=True, timeout=30
        )
        assert blob.returncode == 0, blob.stderr.decode()
        source = blob.stdout.decode("utf-8")
        code = _check_rev_pair(REAL_REPO_ROOT, rel_path, source, source, real_paths, identifier_set, out, rev="HEAD")
        if code != 0:
            had_failure = True
    output = out.getvalue()
    assert not had_failure, output


def test_0f_rev_pair_check_is_red_when_working_tree_has_uncommitted_comment_edit(tmp_path):
    # Mutation for the rewritten test above: swapping the comparison
    # target back to the WORKING TREE (the exact bug being fixed) must
    # go red for a fixture with an uncommitted, unregistered comment
    # edit -- confirming this failure mode is real and that the new
    # rev-vs-itself test correctly avoids it.
    repo = _init_repo(tmp_path)
    _write(repo, "r2db-api/src/r2db_api/mod.py", "# a plain comment.\ndef f():\n    return 1\n")
    rev = _commit_all(repo, "old")
    # An uncommitted, unrelated comment tweak -- never registered/moved,
    # exactly like R-37 WP-1m's parenthetical edit.
    _write(repo, "r2db-api/src/r2db_api/mod.py", "# a plain comment (tweaked).\ndef f():\n    return 1\n")
    # Old-style check: working tree vs HEAD -- goes red.
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1, output
    # New-style check: rev vs itself -- stays green regardless of the
    # uncommitted working-tree edit, since it never reads the worktree.
    real_paths = cp._tree_paths(repo, rev)
    identifier_set = cp._tracked_identifier_set(repo, rev)
    blob = subprocess.run(
        ["git", "show", f"{rev}:r2db-api/src/r2db_api/mod.py"], cwd=repo, capture_output=True, timeout=30
    )
    source = blob.stdout.decode("utf-8")
    out2 = io.StringIO()
    code2 = _check_rev_pair(repo, "r2db-api/src/r2db_api/mod.py", source, source, real_paths, identifier_set, out2, rev=rev)
    assert code2 == 0, out2.getvalue()


def test_0e_camelcase_split_inside_backtick_zero_space_join():
    # supervisor ruling 2026-09-15 (predicate B rule 5): a lowercase-
    # then-uppercase boundary INSIDE a backtick span joins with zero
    # space ONLY when the joined identifier is a member of the tracked
    # identifier set -- "ControlAuthority" is a real class in this
    # codebase's own corpus, so the fixture below supplies it explicitly.
    identifier_set = frozenset({"ControlAuthority"})
    assert (
        cp._flatten_comment("# see `Control\n# Authority`'s own gate.", identifier_set)
        == "see `ControlAuthority`'s own gate."
    )


def test_0e_identifier_set_guard_f1_f7_red_fixtures():
    # F1-F7 (reviewer fixtures, $SP/rev-ccp0/probe16.py): each of these
    # must compare/join as the CORRECT (fixed) form -- i.e. predicate B
    # is true at the boundary and a lingering broken (spaced) form is
    # what `find_broken_line_wrap_joins` must flag red.
    identifier_set = frozenset({"ApplicationCell", "ControlAuthority"})
    # F1: `conn. transaction()` -> `conn.transaction()` (rule 3, dot
    # inside backtick, regardless of extension).
    assert cp._flatten_comment("# `conn.\n# transaction()`") == "`conn.transaction()`"
    # F2: `table_info. constraints` -> `table_info.constraints` (rule 3).
    assert cp._flatten_comment("# `table_info.\n# constraints`") == "`table_info.constraints`"
    # F3: `SchemaOperationRequest. idempotency_key` -> zero space (rule 3).
    assert (
        cp._flatten_comment("# `SchemaOperationRequest.\n# idempotency_key`")
        == "`SchemaOperationRequest.idempotency_key`"
    )
    # F4: `self. _rate_windows` -> `self._rate_windows` (rule 3: `.`
    # inside backtick followed by a word character, `_` included).
    assert cp._flatten_comment("# `self.\n# _rate_windows`") == "`self._rate_windows`"
    # F5: `id ASC` stays TWO words -- "idASC" is not a real tracked
    # identifier, so rule 5 does not fire and the space is REQUIRED
    # (over-joining this into one token is what must go red elsewhere).
    assert cp._flatten_comment("# `id\n# ASC`", identifier_set) == "`id ASC`"
    assert "idASC" not in identifier_set
    # F6: `exceptFoundationError` is not a real tracked identifier either
    # -- "except"/"FoundationError" stays two words WITH a required space.
    assert cp._flatten_comment("# `except\n# FoundationError`", identifier_set) == "`except FoundationError`"
    assert "exceptFoundationError" not in identifier_set
    # F7: `Control Authority` -> `ControlAuthority` (rule 5, WITH the
    # identifier in the set this time).
    assert (
        cp._flatten_comment("# `Control\n# Authority` type", identifier_set) == "`ControlAuthority` type"
    )


def test_0e_all_caps_and_lowercase_pairs_inside_backtick_keep_space():
    # No false red: an ALL-CAPS pair or two lowercase words inside
    # backticks is not a case CHANGE at all, so it stays a real word
    # boundary regardless of the identifier set.
    identifier_set = frozenset({"ShareMode", "FooBar"})
    assert (
        cp._flatten_comment("# `SHARE\n# MODE` is not self-conflicting.", identifier_set)
        == "`SHARE MODE` is not self-conflicting."
    )
    assert cp._flatten_comment("# `foo\n# bar` is a stub.", identifier_set) == "`foo bar` is a stub."


def test_0e_is_none_and_except_foundationerror_join_with_space_stays_green():
    # No false red (the coordinator's own repro): a lowercase-to-
    # uppercase boundary that does NOT form a real tracked identifier
    # once joined stays a required space -- joining WITH a space is the
    # correct, green form.
    identifier_set = frozenset({"ApplicationCell"})
    assert cp._flatten_comment("# `is\n# None`", identifier_set) == "`is None`"
    assert cp._flatten_comment("# `except\n# FoundationError`", identifier_set) == "`except FoundationError`"


def test_0e_sentence_end_dot_next_and_double_hyphen_stay_green_outside_backtick():
    assert cp._flatten_comment("# End of sentence.\n# Next sentence.") == "End of sentence. Next sentence."
    assert cp._flatten_comment("# first clause --\n# second clause.") == "first clause -- second clause."


def test_0e_run_base_flags_camelcase_split_as_red(tmp_path):
    repo = _init_repo(tmp_path)
    old = "# see `Control\n# Authority`'s own gate. The body is JSON.\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    # "ControlAuthority" must be a real identifier somewhere in the
    # BASIS tree for rule 5 to fire -- give it a real occurrence.
    _write(repo, "r2db-api/src/r2db_api/other.py", "class ControlAuthority:\n    pass\n")
    rev = _commit_all(repo, "old")
    broken = (
        "# see `Control Authority`'s own gate. The body is JSON.\n"
        "# history: CH-0001\n"
        "def f():\n    return 1\n"
    )
    _write(repo, "r2db-api/src/r2db_api/mod.py", broken)
    _write(
        repo, "docs/code-history/r2db-api/mod.md",
        _companion_section("CH-0001", "# see `Control\n# Authority`'s own gate. The body is JSON."),
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§9e" in output
    assert "`Control Authority`" in output


def test_0e_run_base_green_when_camelcase_fixed(tmp_path):
    repo = _init_repo(tmp_path)
    old = "# see `Control\n# Authority`'s own gate. The body is JSON.\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    _write(repo, "r2db-api/src/r2db_api/other.py", "class ControlAuthority:\n    pass\n")
    rev = _commit_all(repo, "old")
    fixed = (
        "# see `ControlAuthority`'s own gate. The body is JSON.\n"
        "# history: CH-0001\n"
        "def f():\n    return 1\n"
    )
    _write(repo, "r2db-api/src/r2db_api/mod.py", fixed)
    _write(
        repo, "docs/code-history/r2db-api/mod.md",
        _companion_section("CH-0001", "# see `Control\n# Authority`'s own gate. The body is JSON."),
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 0, output


def test_0e_run_base_red_when_over_joined_id_asc(tmp_path):
    # The over-join direction: the basis genuinely has TWO words ("id
    # ASC", never wrapped -- both on the same original line), and new
    # code wrongly mashes them into "idASC". Since "idASC" is not a real
    # tracked identifier, predicate B's rule 5 does not license this
    # join, so the two texts must NOT compare equal.
    repo = _init_repo(tmp_path)
    old = "# order by `id ASC`. The body is JSON.\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    over_joined = "# order by `idASC`. The body is JSON.\n# history: CH-0001\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", over_joined)
    _write(
        repo, "docs/code-history/r2db-api/mod.md",
        _companion_section("CH-0001", "# order by `id ASC`. The body is JSON."),
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1, output


def test_0e_identifier_set_is_read_from_base_rev_is_green(tmp_path):
    # change set 0i (Z0i-5, monitor ruling): renamed from
    # test_0e_mutation_identifier_set_from_head_instead_of_base_is_red
    # (work order 15.4) -- the back half, which hand-built a stand-in
    # for the (mis-scoped) identifier set and called
    # `_is_allowed_reduction` directly to prove the MUTATED behavior
    # would be red, is replaced by the `mutate.py` mutation
    # "b27-identifier-set-head" against the real checker code (design
    # 10.2's own "no hand-copied mutation evidence" lesson). What
    # remains here is the real-code fixture: a renamed identifier that
    # existed at the basis but not at HEAD must still license the join
    # when checking that basis.
    #
    # x1 (reviewer fixture): predicate B rule 5 must build the
    # identifier set from the BASIS revision's own tree, never HEAD/the
    # working tree -- an identifier that existed at the basis but was
    # since renamed away must still license the join when checking
    # THAT basis (using HEAD's set instead would silently drop it).
    repo = _init_repo(tmp_path)
    _write(repo, "r2db-api/src/r2db_api/widget.py", "class OldWidget:\n    pass\n")
    old = "# see `Old\n# Widget` handle requests. The body is JSON.\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")  # this becomes the --base revision
    # Advance past `rev`: rename OldWidget away, so by the time HEAD is
    # read, this identifier no longer exists anywhere in the tree.
    _write(repo, "r2db-api/src/r2db_api/widget.py", "class NewWidget:\n    pass\n")
    _commit_all(repo, "renamed")
    fixed = (
        "# see `OldWidget` handle requests. The body is JSON.\n"
        "# history: CH-0001\n"
        "def f():\n    return 1\n"
    )
    _write(repo, "r2db-api/src/r2db_api/mod.py", fixed)
    _write(
        repo, "docs/code-history/r2db-api/mod.md",
        _companion_section("CH-0001", "# see `Old\n# Widget` handle requests. The body is JSON."),
    )
    # correct: identifier set built from the BASIS rev (`rev`) -- green.
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 0, output


def test_0e_identifier_set_includes_docs_is_green(tmp_path):
    # change set 0i (Z0i-5, monitor ruling): renamed from
    # test_0e_mutation_identifier_set_excluding_docs_is_red (work order
    # 15.4) -- the back half (a hand-built stand-in for the docs-
    # excluding identifier set, via a local `git grep` call) is
    # replaced by the `mutate.py` mutation "b28-identifier-set-no-docs"
    # against the real checker code.
    #
    # x2 (reviewer fixture): predicate B rule 5's identifier set must
    # scan `docs` too, not just `src`/`spec` -- an identifier documented
    # only in a design doc (never mentioned in any tracked source file)
    # must still license the join.
    repo = _init_repo(tmp_path)
    (repo / "docs" / "design").mkdir(parents=True, exist_ok=True)
    _write(repo, "docs/design/SOME_DESIGN.md", "`DocsOnlyWidget` is described here.\n")
    old = "# see `Docs\n# OnlyWidget` here. The body is JSON.\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    fixed = (
        "# see `DocsOnlyWidget` here. The body is JSON.\n"
        "# history: CH-0001\n"
        "def f():\n    return 1\n"
    )
    _write(repo, "r2db-api/src/r2db_api/mod.py", fixed)
    _write(
        repo, "docs/code-history/r2db-api/mod.md",
        _companion_section("CH-0001", "# see `Docs\n# OnlyWidget` here. The body is JSON."),
    )
    # correct: identifier set includes docs -- green.
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 0, output


# ===========================================================================
# change set 0f: predicate B rules 6-8 (supervisor ruling 2026-09-15,
# read-only survey found 71 remaining reflow-damage cases B still missed)
# ===========================================================================

def test_0f_rule6_slash_boundary_red_and_green():
    # Red (broken): a naive single-space join after `/`.
    assert cp._flatten_comment("# see `cell.py`/\n# `backend_sqlite.py` here.") == (
        "see `cell.py`/`backend_sqlite.py` here."
    )
    assert cp._flatten_comment("# calls `POST /v1/data/\n# mutations` endpoint.") == (
        "calls `POST /v1/data/mutations` endpoint."
    )


def test_0f_rule7_paren_bracket_equals_inside_backtick_red_and_green():
    assert cp._flatten_comment("# uses `HttpService(\n# ...)` call sites.") == "uses `HttpService(...)` call sites."
    assert cp._flatten_comment('# an allow-list for `role=\n# "audit"` while.') == (
        'an allow-list for `role="audit"` while.'
    )
    # Green: an ordinary SPACED assignment `a = b` keeps its space -- the
    # character right before `=` is a space, not a word char or bracket.
    assert cp._flatten_comment("# note that a =\n# b holds here.") == "note that a = b holds here."


def test_0f_rule8_opening_backtick_immediately_wrapped_red_and_green():
    assert cp._flatten_comment("# never `\n# contract_field_types` entirely.") == (
        "never `contract_field_types` entirely."
    )


def test_0f_exclusions_stay_green():
    # Closing backtick followed by ordinary English: not a trigger.
    assert cp._flatten_comment("# `ConflictError`\n# immediately above.") == "`ConflictError` immediately above."
    # Quote mark followed by English: not a trigger.
    assert cp._flatten_comment('# the "local-foundation-only"\n# rule has no notion.') == (
        'the "local-foundation-only" rule has no notion.'
    )
    # `*` (markdown emphasis) followed by English: not a trigger.
    assert cp._flatten_comment("# it is *separate*\n# process from the app.") == "it is *separate* process from the app."
    # An `=`-rule separator line: the char before the LAST `=` is another
    # `=`, not a word char or bracket, so rule 7 does not fire.
    assert cp._flatten_comment("# ========\n# ==== Ceremony core") == "======== ==== Ceremony core"
    # A `<->` arrow: `-` is preceded by `<`, not a word char, so rule 2
    # (unchanged, pre-existing) does not fire either.
    assert cp._flatten_comment("# only on a failing<->\n# healthy state.") == "only on a failing<-> healthy state."


def test_0f_run_base_flags_slash_boundary_as_red(tmp_path):
    repo = _init_repo(tmp_path)
    old = "# see `cell.py`/\n# `backend_sqlite.py` here. The body is JSON.\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    broken = (
        "# see `cell.py`/ `backend_sqlite.py` here. The body is JSON.\n"
        "# history: CH-0001\n"
        "def f():\n    return 1\n"
    )
    _write(repo, "r2db-api/src/r2db_api/mod.py", broken)
    _write(
        repo, "docs/code-history/r2db-api/mod.md",
        _companion_section("CH-0001", "# see `cell.py`/\n# `backend_sqlite.py` here. The body is JSON."),
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§9e" in output


def test_0f_run_base_green_when_slash_boundary_fixed(tmp_path):
    repo = _init_repo(tmp_path)
    old = "# see `cell.py`/\n# `backend_sqlite.py` here. The body is JSON.\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    fixed = (
        "# see `cell.py`/`backend_sqlite.py` here. The body is JSON.\n"
        "# history: CH-0001\n"
        "def f():\n    return 1\n"
    )
    _write(repo, "r2db-api/src/r2db_api/mod.py", fixed)
    _write(
        repo, "docs/code-history/r2db-api/mod.md",
        _companion_section("CH-0001", "# see `cell.py`/\n# `backend_sqlite.py` here. The body is JSON."),
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 0, output


# ===========================================================================
# change set 0f, review round 2 (supervisor ruling 2026-09-15): 3 further
# fixes -- Item 1 [major] a real-path-detection bug in
# `_FILENAME_CANDIDATE_RE`/`_filename_candidates` present since 4bc9535,
# Item 2 [minor] rule 6's `/`-boundary needs a not-preceded-by-space
# guard, Item 3 [minor] a fixture pinning rule 7's existing prev-char
# guard (the reviewer's own mutation "y2" found it incorrectly green).
# ===========================================================================

def test_0f_item1_real_path_between_backtick_spans_is_protected():
    """Item 1: the OLD `_FILENAME_CANDIDATE_RE.finditer`-based candidate
    extraction matched a literal backtick ... backtick pair without
    tracking which backtick OPENS a span and which CLOSES one, so a bare
    (non-backtick) real path sandwiched between two backtick spans was
    swallowed whole into one bogus, non-real "candidate" running from
    the first span's closing backtick to the second span's opening
    backtick -- and was therefore never recognized as a real, protected
    path reference. Fixed by pairing backticks front-to-back first, then
    finding path candidates separately inside each paired span and in
    the residue outside every span (`_filename_span_matches`)."""
    sentence = (
        "Counterpart to `a` below (design docs/design/X_V1.md R-2): "
        "a plain `SELECT` here."
    )
    real_paths = frozenset({"docs/design/X_V1.md"})
    assert cp._filename_candidates(sentence) == ["docs/design/X_V1.md"]
    assert cp._has_real_filename_reference(sentence, real_paths) is True
    assert cp._sentence_has_protected_reference(sentence, real_paths) is True
    # Deleting the whole sentence must not be an allowed reduction.
    ok, reason = cp._is_allowed_reduction("comment", sentence, "", real_paths, frozenset())
    assert ok is False, reason


def test_0f_item1_ch0080_postgres_reference_now_protected():
    """The coordinator flagged that the CH-0080 sentence restored in
    postgres.py:2432 (`docs/design/DESTRUCTIVE_CONFIRMATION_V1.md`) may
    also not have been recognized as protected under the buggy regex,
    since it too sits directly after other prose with no backtick
    wrapping. Pin that it IS recognized once real, with the fix."""
    real_paths = frozenset({"docs/design/DESTRUCTIVE_CONFIRMATION_V1.md"})
    sentence = (
        "See design docs/design/DESTRUCTIVE_CONFIRMATION_V1.md R-2 item 1 m-1."
    )
    assert cp._has_real_filename_reference(sentence, real_paths) is True
    assert cp._sentence_has_protected_reference(sentence, real_paths) is True


def test_0f_item2_rule6_slash_boundary_requires_no_space_before_slash():
    """Item 2: a genuinely SPACED path-like expression `a / b` (a real
    space before the `/`) must join WITH a space when wrapped right
    after the `/`, not zero-space -- only a `/` sitting directly
    against the preceding text (no space before it) is a real path
    separator."""
    identifier_set = frozenset()
    # Green: spaced `a / b` keeps its space.
    assert cp._is_join_sensitive_boundary("a /", "b holds here.", identifier_set) is False
    assert cp._flatten_comment("# note that a /\n# b holds here.") == "note that a / b holds here."
    # Still red/joining: a real zero-space path split (unaffected regression check).
    assert cp._is_join_sensitive_boundary("`cell.py`/", "`backend_sqlite.py`", identifier_set) is True


def test_0f_item3_rule7_prev_char_guard_pinned_by_fixture():
    """Item 3: pin rule 7's existing "the character immediately before
    `(`/`[`/`=` must be a word character or `(`/`[`" guard with a
    dedicated fixture -- the reviewer's own mutation "y2" (removing/
    weakening exactly this guard) was found to incorrectly stay GREEN.
    A genuinely SPACED `a = b` expression, wrapped right after `=`,
    must stay spaced (the space before `=` means this is an ordinary
    assignment, not a call/subscript/kwarg opening)."""
    identifier_set = frozenset()
    assert cp._is_join_sensitive_boundary("`a =", "b`", identifier_set) is False
    assert cp._flatten_comment("# note that a =\n# b holds here.") == "note that a = b holds here."


# ===========================================================================
# Change set 0g: append-only companion correction records (design
# docs/design/CODE_COMMENT_PROVENANCE_V1.md v0.11 §9, supervisor ruling
# 2026-09-15). A companion's original fenced block is never edited; a
# `### correction: <date>` entry is appended under the same CH-ID heading
# instead (see `cp.Correction`/`cp._parse_corrections` for the exact
# format). `_apply_corrections` splices the correction's `old` sentence
# out and its `new` sentence in, against the FLATTENED basis text, before
# any derivability/0d check runs.
# ===========================================================================

def _correction_block(date: str, reason: str, old: str, new: str) -> str:
    return (
        f"### correction: {date}\n\n"
        f"- reason: {reason}\n\n"
        f"old:\n```\n{old}\n```\n\n"
        f"new:\n```\n{new}\n```\n\n"
    )


def _correction_scenario(tmp_path, companion_lines, correction_blocks, current_block_lines, extra_committed_files=None):
    """Shared setup: the committed revision AND the working tree carry the
    SAME (already-corrected-in-code) block, referencing CH-0001 (a Q-4
    re-edit of an already-migrated block) -- exactly the shape of the real
    CH-0239/CH-0139 regression (`test_0f_both_peers_all_src_rev_vs_itself_
    is_green`). The companion's own recorded text (`companion_lines`)
    still holds the ORIGINAL (pre-fix) wording; `correction_blocks` (zero
    or more, from `_correction_block`) are appended after the companion's
    unedited fenced block to bridge the two. `extra_committed_files`
    ({rel_path: content}) are written and committed alongside the source
    file -- needed so a real-path fixture's referenced file actually
    exists in the BASIS revision's tree (`_tree_paths`)."""
    repo = _init_repo(tmp_path)
    for rel_path, content in (extra_committed_files or {}).items():
        _write(repo, rel_path, content)
    src = "\n".join(current_block_lines + ["# history: CH-0001"]) + "\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", src)
    section = _companion_section("CH-0001", "\n".join(companion_lines))
    section += "".join(correction_blocks)
    # design §9.3 rule 1 (work order R-68 WP-1): the companion AND its
    # correction records are committed in THIS SAME revision, matching
    # this helper's own documented shape ("the committed revision AND
    # the working tree carry the SAME... block") -- a re-edit's stage-A
    # basis now reads its correction records from the BASIS revision,
    # never the working tree, so leaving them uncommitted would starve
    # every scenario built by this helper of its own correction record.
    _write(repo, "docs/code-history/r2db-api/mod.md", section)
    rev = _commit_all(repo, "old")
    return repo, rev


_SI08_COMPANION = ["# Guarded by SI-08.", "# The old widget does not exist yet."]
_SI08_CURRENT = ["# Guarded by SI-08.", "# The new widget exists now."]
_SI08_CORRECTION = _correction_block(
    "2026-09-10", "the widget shipped", "The old widget does not exist yet.", "The new widget exists now.",
)


def test_0g_correction_bridges_rewritten_protected_sentence_is_green(tmp_path):
    repo, rev = _correction_scenario(tmp_path, _SI08_COMPANION, [_SI08_CORRECTION], _SI08_CURRENT)
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 0, output


# --- (a): removing the correction entry is red ----------------------------

def test_0g_missing_correction_entry_is_red(tmp_path):
    repo, rev = _correction_scenario(tmp_path, _SI08_COMPANION, [], _SI08_CURRENT)
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (2)" in output


# --- (b): an old sentence that does not occur is red -----------------------

def test_0g_correction_old_sentence_not_found_is_red(tmp_path):
    bad_correction = _correction_block(
        "2026-09-10", "the widget shipped",
        "The odl widget does not exist yet.",  # typo -- never occurs in the basis
        "The new widget exists now.",
    )
    repo, rev = _correction_scenario(tmp_path, _SI08_COMPANION, [bad_correction], _SI08_CURRENT)
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§9f" in output
    assert "occurs 0 time" in output


# --- (c): an old sentence occurring twice is red ----------------------------

def test_0g_correction_old_sentence_ambiguous_is_red(tmp_path):
    companion_lines = [
        "# The old widget does not exist yet.",
        "# The old widget does not exist yet.",
    ]
    correction = _correction_block(
        "2026-09-10", "the widget shipped",
        "The old widget does not exist yet.", "The new widget exists now.",
    )
    repo, rev = _correction_scenario(
        tmp_path, companion_lines, [correction], ["# The new widget exists now."],
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§9f" in output
    assert "occurs 2 time" in output


# --- (d): two chained corrections, order matters ---------------------------

_CHAIN_COMPANION = ["# Step one happens then step two happens."]
_CHAIN_CURRENT = ["# Phase one runs then phase two runs."]
_CHAIN_CORRECTION_1 = _correction_block(
    "2026-09-10", "phase 1 renamed",
    "Step one happens then step two happens.", "Phase one runs then step two happens.",
)
_CHAIN_CORRECTION_2 = _correction_block(
    "2026-09-15", "phase 2 renamed",
    "Phase one runs then step two happens.", "Phase one runs then phase two runs.",
)


def test_0g_chained_corrections_in_file_order_is_green(tmp_path):
    repo, rev = _correction_scenario(
        tmp_path, _CHAIN_COMPANION, [_CHAIN_CORRECTION_1, _CHAIN_CORRECTION_2], _CHAIN_CURRENT,
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 0, output


def test_0g_chained_corrections_out_of_file_order_is_red(tmp_path):
    # The SAME two corrections, written in the WRONG (swapped) order --
    # correction 2's own `old` text does not exist until correction 1 has
    # already been applied, so applying strictly in file order (never by
    # date, never by any other reordering) must catch this as red.
    repo, rev = _correction_scenario(
        tmp_path, _CHAIN_COMPANION, [_CHAIN_CORRECTION_2, _CHAIN_CORRECTION_1], _CHAIN_CURRENT,
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§9f" in output
    assert "occurs 0 time" in output


# --- (e): a malformed correction entry is red under --register -------------

def test_0g_malformed_correction_entry_register_is_red(tmp_path):
    repo = _init_repo(tmp_path)
    _write(
        repo, "r2db-api/src/r2db_api/mod.py",
        "# history: CH-0001\ndef f():\n    return 1\n",
    )
    section = _companion_section("CH-0001", "# Some moved comment.")
    # Missing the required '- reason:' line.
    section += (
        "### correction: 2026-09-10\n\n"
        "old:\n```\nSome moved comment.\n```\n\n"
        "new:\n```\nSome other comment.\n```\n\n"
    )
    _write(repo, "docs/code-history/r2db-api/mod.md", section)
    code, output = _run_register(repo)
    assert code == 1
    assert "§9f" in output
    assert "reason" in output


# --- (f): a correction does not relax 0d elsewhere --------------------------

def test_0g_correction_present_but_other_protected_sentence_deleted_is_red(tmp_path):
    companion_lines = [
        "# Guarded by SI-08.",
        "# The old widget does not exist yet.",
        "# See C-05 for details.",
    ]
    # The correction only bridges the middle sentence; the code below
    # drops the THIRD sentence entirely -- still protected (C-05), so
    # this must stay red regardless of the (valid, present) correction.
    repo, rev = _correction_scenario(
        tmp_path, companion_lines, [_SI08_CORRECTION], _SI08_CURRENT,
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (2)" in output
    assert "cannot delete a whole sentence carrying a protected reference" in output
    assert "See C-05 for details." in output


# ===========================================================================
# Change set 0g review round (supervisor ruling 2026-09-15, "hole" fix): a
# correction record must never let a protected reference in its `old`
# sentence silently disappear from `new` -- that would be a 0d bypass (a
# sentence 0d would never let vanish outright could otherwise be
# "corrected" into one that no longer carries what made it protected).
# Adding a protected reference is fine; only DROPPING one already present
# is red (§9f). A real path that changed is deliberately NOT an exception.
# ===========================================================================

def test_0g_correction_dropping_protected_id_is_red(tmp_path):
    bad_correction = _correction_block(
        "2026-09-10", "widget shipped (drops SI-08 too)",
        "Guarded by SI-08, the old widget does not exist yet.",
        "The new widget exists now.",  # SI-08 silently dropped
    )
    repo, rev = _correction_scenario(
        tmp_path,
        ["# Guarded by SI-08, the old widget does not exist yet."],
        [bad_correction],
        ["# The new widget exists now."],
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§9f" in output
    assert "SI-08" in output
    assert "dropped" in output


def test_0g_correction_dropping_real_path_is_red(tmp_path):
    bad_correction = _correction_block(
        "2026-09-10", "path reference reworded away (drops the real path)",
        "See `docs/design/X_V1.md` for the old rule.",
        "See the updated rule.",  # the real path reference vanished
    )
    repo, rev = _correction_scenario(
        tmp_path,
        ["# See `docs/design/X_V1.md` for the old rule."],
        [bad_correction],
        ["# See the updated rule."],
        extra_committed_files={"docs/design/X_V1.md": "stub\n"},
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§9f" in output
    assert "docs/design/X_V1.md" in output
    assert "dropped" in output


def test_0g_correction_adding_protected_reference_is_green(tmp_path):
    # Adding a protected reference that was not there before is allowed --
    # only DROPPING one already present in `old` is restricted.
    good_correction = _correction_block(
        "2026-09-10", "now cites SI-08 for clarity",
        "The widget behaves the old way.",
        "The widget behaves the old way, per SI-08.",
    )
    repo, rev = _correction_scenario(
        tmp_path,
        ["# The widget behaves the old way."],
        [good_correction],
        ["# The widget behaves the old way, per SI-08."],
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 0, output


def test_0g_real_ch0239_and_ch0139_corrections_stay_green():
    # The two real corrections (control_plane.py CH-0239, service.py
    # CH-0139) must still pass the new protection-preservation check --
    # covered end-to-end by test_0f_both_peers_all_src_rev_vs_itself_is_
    # green already, but pinned here directly against the real companion
    # records so a future edit to either correction entry is caught even
    # if the broader rev-vs-itself sweep is ever narrowed.
    real_paths = cp._tree_paths(REAL_REPO_ROOT, "HEAD")
    lookup = cp._load_corrections_lookup(REAL_REPO_ROOT, "r2db-api")
    corrections_by_id, format_errors = lookup
    assert format_errors == []
    for ch_id in ("CH-0239", "CH-0139"):
        for corr in corrections_by_id.get(ch_id, []):
            err = cp._correction_relaxes_protection(corr.old, corr.new, real_paths)
            assert err is None, f"{ch_id}: {err}"


# ===========================================================================
# Change set 0g review round 2 (supervisor ruling 2026-09-15): flattening
# stripped only the leading `#`, so a Sphinx-style `#:`-prefixed comment
# line kept its own leading `:` as if it were CONTENT. Change set 4's
# `ops.py` CH-0321 one-line compaction hit exactly this -- a stray ": "
# landed mid-sentence -- and went undetected because the SAME (buggy)
# stripping corrupted the companion's own basis text identically, so both
# sides matched each other. `_comment_line_groups` now strips `#:` as its
# own two-character marker; `_is_colon_style_block` additionally flags a
# basis-was-`#:`-but-new-is-not style regression even when content still
# happens to match.
# ===========================================================================

_COLON_COMPANION = ["#: Note continues across two lines here.", "#: Second part stays intact too."]


def test_0g_colon_prefix_stray_residue_one_liner_is_red(tmp_path):
    # Naive one-line compaction: drops the `#:` marker in favor of plain
    # `#` and bakes a stray ": " into the middle of the sentence -- the
    # exact shape of the real change-set-4 `ops.py` CH-0321 bug.
    repo = _init_repo(tmp_path)
    old = "\n".join(_COLON_COMPANION) + "\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    new = (
        "# Note continues across two lines here. : Second part stays intact too.\n"
        "# history: CH-0001\ndef f():\n    return 1\n"
    )
    _write(repo, "r2db-api/src/r2db_api/mod.py", new)
    _write(
        repo, "docs/code-history/r2db-api/mod.md",
        _companion_section("CH-0001", "\n".join(_COLON_COMPANION)),
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§9f" in output
    assert "Sphinx-style" in output


def test_0g_colon_prefix_correct_one_liner_keeps_marker_is_green(tmp_path):
    # A CORRECT compaction: still one line, but keeps the `#:` marker and
    # introduces no stray residue -- content and style both preserved.
    repo = _init_repo(tmp_path)
    old = "\n".join(_COLON_COMPANION) + "\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    new = (
        "#: Note continues across two lines here. Second part stays intact too.\n"
        "# history: CH-0001\ndef f():\n    return 1\n"
    )
    _write(repo, "r2db-api/src/r2db_api/mod.py", new)
    _write(
        repo, "docs/code-history/r2db-api/mod.md",
        _companion_section("CH-0001", "\n".join(_COLON_COMPANION)),
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 0, output


def test_0g_plain_hash_block_unaffected_by_colon_style_check(tmp_path):
    # An ordinary `#` block (never `#:`) compacted the same way must be
    # completely unaffected by the new style check -- `_is_colon_style_
    # block` on the basis is False, so it never even looks at the new
    # side.
    repo, rev = _setup_retained_reduction(
        tmp_path, "# Sentence A stays here.\n# Sentence B stays here too.",
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 0, output
    assert "§9f" not in output


def test_0g_is_colon_style_block_unit():
    assert cp._is_colon_style_block("#: a\n#: b") is True
    assert cp._is_colon_style_block("#: a\n# b") is False
    assert cp._is_colon_style_block("# a\n# b") is False
    assert cp._is_colon_style_block("") is False


def test_0g_flatten_strips_colon_marker_not_content():
    # The flatten fix itself: `#:` is a two-character marker, stripped
    # whole (plus one following space) -- a bare `#:` occurring MID-LINE
    # (not as the line's own leading marker) is untouched.
    assert cp._flatten_comment("#: Note here.\n#: continues.") == "Note here. continues."
    assert cp._flatten_comment("# See ratio 3:1 here.") == "See ratio 3:1 here."


# ---------------------------------------------------------------------------
# change set 0h: `split_sentences` did not restore an `_ABBREVIATIONS`
# placeholder (`...`) hidden INSIDE a backtick span -- e.g. change set 5's
# `credential_store.py` module docstring, `` passed through `cursor.
# execute(...)` `` -- because abbreviation-hiding ran BEFORE backtick-span
# hiding: the backtick-span regex then captured the ALREADY-hidden `\x00A3
# \x00` token as part of the span's own "original" text, and `restore()`'s
# single left-to-right pass over `placeholders` (A-tokens inserted first,
# so restored first) had already finished restoring lone A-tokens by the
# time the B-token substitution reintroduced one, hidden inside the
# now-restored backtick span. Minimal repro (found working on change set
# 5's real `credential_store.py`, 2026-09-15):
#   input:    "Every statement is passed through `cursor.execute(...)`
#              with a bound list."
#   expected: [the same string, unsplit -- one sentence]
#   actual (before this fix): the returned sentence contained the literal
#              placeholder text "\x00A3\x00" in place of "...".
# Fix: hide backtick spans FIRST, abbreviations SECOND, so an
# abbreviation-shaped substring inside a span is never separately
# substituted at all (it is already opaque) -- `restore()`'s insertion
# order therefore restores the (untouched) span before any lone
# abbreviation outside it, and neither pass can leave a placeholder behind
# inside the other's restored text.
# ---------------------------------------------------------------------------


def test_0h_ellipsis_inside_backtick_span_survives_split_sentences():
    text = "Every statement is passed through `cursor.execute(...)` with a bound list."
    assert cp.split_sentences(text) == [text]


def test_0h_various_abbreviations_inside_backtick_span_survive_split_sentences():
    for abbr in ("...", "e.g.", "i.e.", "vs."):
        text = f"See the `example({abbr})` call for the exact shape. Next sentence."
        result = cp.split_sentences(text)
        assert "\x00" not in "".join(result), (abbr, result)
        assert result[0] == f"See the `example({abbr})` call for the exact shape."
        assert result[1] == "Next sentence."


def test_0h_abbreviation_outside_backtick_span_still_protected():
    # The fix must not regress the ORIGINAL purpose of abbreviation-hiding:
    # a bare "e.g." outside any backtick span must still not split the
    # sentence on its own internal period.
    text = "This covers common cases, e.g. a plain one. The next sentence."
    result = cp.split_sentences(text)
    assert result == [
        "This covers common cases, e.g. a plain one.",
        "The next sentence.",
    ]


# ===========================================================================
# change set 0h, predicate B condition 9 (design v0.14 §9): a line-wrap
# boundary where BOTH sides are CJK characters (Han, Hiragana, Katakana, or
# CJK punctuation) must join with ZERO space, never the single space rules
# 1-8 (all English-oriented) leave in place by default. Found in change set
# 5's `ops.py` ("い かなる", "無効化 中", etc. -- Japanese prose carries no
# spaces between words at all, so any such stray space is itself the
# corruption).
# ===========================================================================


def test_0h_rule9_cjk_boundary_red_and_green():
    # Red (broken): a naive single-space join between two CJK characters,
    # both outside and inside a backtick span.
    assert cp._flatten_comment("# い\n# かなる HTTP surface からも発行できない。") == (
        "いかなる HTTP surface からも発行できない。"
    )
    assert cp._flatten_comment("# 無効化\n# 中の application も対象に含める。") == (
        "無効化中の application も対象に含める。"
    )
    assert cp._flatten_comment("# `psql の実行結果は監査\n# 不要`とする。") == (
        "`psql の実行結果は監査不要`とする。"
    )
    # Green: an ASCII word immediately next to CJK text is NOT a trigger --
    # only a CJK-CJK boundary joins with zero space; a CJK/ASCII boundary
    # keeps its space exactly as rules 1-8 already require.
    assert cp._flatten_comment("# 対象は application\n# のみとする。") == (
        "対象は application のみとする。"
    )
    assert cp._flatten_comment("# こちらは英語の control_plane\n# モジュールが担当する。") == (
        "こちらは英語の control_plane モジュールが担当する。"
    )
    # Green: a correctly-joined (already zero-space, never wrapped) CJK
    # phrase on one physical line is left untouched.
    assert cp._flatten_comment("# いかなる HTTP surface からも発行できない。") == (
        "いかなる HTTP surface からも発行できない。"
    )


def test_0h_run_base_flags_cjk_boundary_as_red(tmp_path):
    repo = _init_repo(tmp_path)
    old = "# い\n# かなる HTTP surface からも発行できない。The body is JSON.\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    broken = (
        "# い かなる HTTP surface からも発行できない。The body is JSON.\n"
        "# history: CH-0001\n"
        "def f():\n    return 1\n"
    )
    _write(repo, "r2db-api/src/r2db_api/mod.py", broken)
    _write(
        repo, "docs/code-history/r2db-api/mod.md",
        _companion_section("CH-0001", "# い\n# かなる HTTP surface からも発行できない。The body is JSON."),
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§9e" in output


def test_0h_run_base_green_when_cjk_boundary_fixed(tmp_path):
    repo = _init_repo(tmp_path)
    old = "# い\n# かなる HTTP surface からも発行できない。The body is JSON.\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    fixed = (
        "# いかなる HTTP surface からも発行できない。The body is JSON.\n"
        "# history: CH-0001\n"
        "def f():\n    return 1\n"
    )
    _write(repo, "r2db-api/src/r2db_api/mod.py", fixed)
    _write(
        repo, "docs/code-history/r2db-api/mod.md",
        _companion_section("CH-0001", "# い\n# かなる HTTP surface からも発行できない。The body is JSON."),
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 0, output


# ===========================================================================
# change set 5 (independent review): fixtures for the charset A2 extended
# (々/〇, fullwidth punctuation, CJK Ext-A, halfwidth Katakana) and the
# 、/。/（ punctuation boundary specifically, plus the A1 short-context
# fix in `find_broken_line_wrap_joins` (real code, not a local copy).
# ===========================================================================


def test_0h_punctuation_boundary_toten_kuten_open_paren_red_and_green():
    # 、(toten) and 。(kuten) and （(fullwidth open paren) each join with
    # zero space against an adjacent CJK character across a line wrap --
    # the same condition-9 rule pinned above for `。`/Han, exercised here
    # for `、` and `（` specifically (design v0.14 §9, A2 charset review).
    assert cp._flatten_comment("# 対象は権限\n# 、権限失効の両方とする。") == (
        "対象は権限、権限失効の両方とする。"
    )
    assert cp._flatten_comment("# 対象は権限、\n# 権限失効の両方とする。") == (
        "対象は権限、権限失効の両方とする。"
    )
    assert cp._flatten_comment("# 引数は必須\n# （キーワード専用）とする。") == (
        "引数は必須（キーワード専用）とする。"
    )
    # Green: an ASCII word adjacent to `、`/`。` keeps its required space.
    assert cp._flatten_comment("# 対象は application\n# 、権限失効とする。") == (
        "対象は application 、権限失効とする。"
    )


def test_0h_katakana_boundary_fullwidth_and_halfwidth_red_and_green():
    # Fullwidth Katakana (already in range before change set 5) and
    # halfwidth Katakana (change set 5, A2) both join with zero space
    # against an adjacent CJK character across a line wrap.
    assert cp._flatten_comment("# ダウン\n# ロードは対象外とする。") == (
        "ダウンロードは対象外とする。"
    )
    assert cp._flatten_comment("# ﾀﾝｰ\n# ﾆﾟｸﾝは半角カナである。") == (
        "ﾀﾝｰﾆﾟｸﾝは半角カナである。"
    )
    # Green: an ASCII word adjacent to Katakana keeps its required space.
    assert cp._flatten_comment("# ダウンロード module\n# は対象外とする。") == (
        "ダウンロード module は対象外とする。"
    )


def test_0h_extended_charset_iteration_mark_and_ext_a_red():
    # 々 (iteration mark) and a CJK Unified Ideographs Extension A
    # character (change set 5, A2) both join with zero space against an
    # adjacent CJK character across a line wrap.
    assert cp._is_cjk_char("々") is True
    assert cp._is_cjk_char("〇") is True  # 〇 ideographic zero
    assert cp._is_cjk_char("㐀") is True  # CJK Ext-A, first code point
    assert cp._is_cjk_char("䶿") is True  # CJK Ext-A, last code point
    assert cp._flatten_comment("# 日々\n# の運用は対象外とする。") == (
        "日々の運用は対象外とする。"
    )
    # Fullwidth alphanumerics are deliberately NOT CJK (A2 scope limit).
    assert cp._is_cjk_char("Ａ") is False  # fullwidth "A"
    assert cp._is_cjk_char("１") is False  # fullwidth "1"


def test_0h_find_broken_line_wrap_joins_short_context_survives_unrelated_run_space():
    # change set 5 fix (independent review finding, r2db `control_plane.py`
    # CH-0281 shape): the basis wraps between two CJK characters -- a
    # genuine condition-9 boundary (超過/は) -- inside a `\\S+`-delimited
    # run that ALSO contains a SECOND, unrelated space later in the SAME
    # run (after `。`, mid-line in the basis, nothing to do with this
    # boundary). A full-token `\\S+` context spanning the WHOLE run fails
    # to find the boundary's own broken join as a literal substring once
    # that unrelated space exists in `new_dedented`; the short single-
    # character CJK context this fix uses must still catch it.
    basis = "rate limit超過\nは監査しない(認証前・実行者不明。監査増幅DoSの防止)\")"
    broken_new = "rate limit超過 は監査しない(認証前・実行者不明。 監査増幅DoSの防止)\")"
    hits = cp.find_broken_line_wrap_joins("docstring", basis, broken_new)
    assert ("過は", "過 は") in hits


def test_0h_find_broken_line_wrap_joins_short_context_ascii_unaffected():
    # The short-context change is scoped to a pure condition-9 (CJK/CJK)
    # boundary only -- an ordinary ASCII word-boundary break (rule 1,
    # underscore-joined identifier) still uses the full `\\S+` token
    # context exactly as before, unaffected by this fix.
    basis = "the `foo_\nbar` helper stays intact"
    broken_new = "the `foo_ bar` helper stays intact"
    hits = cp.find_broken_line_wrap_joins("comment", basis, broken_new)
    assert ("`foo_bar`", "`foo_ bar`") in hits


def test_0h_fullwidth_punctuation_added_in_a2_line_wrap_boundary_hit():
    # change set 5, second send-back C2 (independent review item 6): the
    # fullwidth punctuation `！？：；［］〈〉《》` added to `_CJK_PUNCTUATION`
    # in A2 is covered by `_is_cjk_char` (test_0h_extended_charset_...) and
    # by `_flatten_comment` for `、`/`。`/`（` specifically, but nothing
    # exercised it through `find_broken_line_wrap_joins` -- the actual
    # detector a mutation against `_CJK_PUNCTUATION` must turn red. The
    # basis wraps between `！` and a Han character; a broken rejoin that
    # inserts a single space there must be caught.
    basis = "重要度は高！\n重大事項である。"
    broken_new = "重要度は高！ 重大事項である。"
    hits = cp.find_broken_line_wrap_joins("comment", basis, broken_new)
    assert len(hits) >= 1
    assert ("！重", "！ 重") in hits


# ===========================================================================
# change set 0i (design docs/design/CODE_COMMENT_PROVENANCE_V1.md §9.2 v0.18,
# work order docs/work-orders/WORK_ORDER_CODE_COMMENT_PROVENANCE_CS1.md §15,
# monitor ruling): protected-reference extension -- rule 1 (F-ID, with the
# "review F-n"/"review round F-n"/"review (F-n)" exclusion), rule 2 (real
# path, suffix match at a "/" boundary, ::qualname/:line stripped first),
# rule 3 (basename real with >=1 match), rule 4 (a paren enclosing another
# in the same sentence extends its own tag inward), and M3 (the label
# exclusion also calls the sentence-level protected-reference check).
# ===========================================================================

# --- rule 1: F-ID ------------------------------------------------------

def test_0i_rule1_fid_sentence_whole_deletion_is_red():
    sentence = "Status F-2 applies here."
    ok, reason = cp._is_allowed_reduction("comment", sentence, "", frozenset(), frozenset())
    assert ok is False, reason


def test_0i_rule1_cjk_adjacent_fid_sentence_whole_deletion_is_red():
    # M2: protected-ID extraction uses ASCII word boundaries, so an ID
    # glued directly onto Japanese text with no separating space or
    # punctuation is still caught -- Python's default Unicode `\\b`
    # treats Hiragana as a word character and would see no boundary
    # between "2" and "だ" here, missing the ID entirely.
    sentence = "F-12だけは特別な扱いを受ける。"
    assert cp._sentence_has_protected_reference(sentence, frozenset()) is True
    ok, reason = cp._is_allowed_reduction("comment", sentence, "", frozenset(), frozenset())
    assert ok is False, reason


def test_0i_rule1_fid_in_parens_not_removable_is_red(tmp_path):
    repo, rev = _label_scenario(tmp_path, "Note (F-2): body.", "Note: body.")
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (3)" in output


def test_0i_rule1_fid_label_not_removable_is_red(tmp_path):
    repo, rev = _label_scenario(tmp_path, "Ruling F-2 (WP-6d): reason.", "reason.")
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (3)" in output


def test_0i_rule1_review_fid_is_history_token_is_green(tmp_path):
    # paren: "review F-2" is a removable history token, not a protected ID.
    repo, rev = _label_scenario(tmp_path, "Note (review F-2): body.", "Note: body.")
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 0, output
    # whole-sentence deletion: a sentence naming only "review round F-5"
    # (no other protected reference) may be deleted outright.
    assert cp._sentence_has_protected_reference("Per review round F-5 this changed.", frozenset()) is False
    # the parenthesized form "review (F-2)" is the same one token.
    assert cp._sentence_has_protected_reference("See review (F-2) below.", frozenset()) is False


def test_0i_rule1_review_fid_standalone_paren_is_green():
    # Z0i-1 (B), real-corpus form (MitateDB `http.py` CH-0198): "review"
    # sits in plain sentence prose immediately before a TOP-LEVEL paren
    # whose own entire content is just the F-ID ("round-1 review (F-2)
    # found ..."). `_REVIEW_FID_TOKEN_RE`'s premerge never spans across
    # that paren boundary (it only ever sees one paren's own inner text,
    # or a plain flat run with none), so this needs `_sentence_reachable`
    # to separately recognize "review"/"review round" immediately before
    # a paren as licensing that whole paren's removal too.
    old = "FAIL CLOSED, not fail open: round-1 review (F-2) found this pair."
    new = "FAIL CLOSED, not fail open: round-1 review found this pair."
    ok, reason = cp._is_allowed_reduction("comment", old, new, frozenset(), frozenset())
    assert ok is True, reason


def test_0i_rule1_review_paren_holes_closed_is_red():
    # F2/F3 (code review): the review-flag must come from the ONE
    # shared `_REVIEW_FID_TOKEN_RE` pattern (M1), not a separate, wider
    # grammar -- these four synthetic forms are NOT the ruled
    # "review (F-n)" form (Z0i-1 (B), whole paren content is only the
    # F-ID) and must stay protected.
    real_paths = frozenset({"docs/design/X_V1.md"})

    def refused(old, new):
        ok, reason = cp._is_allowed_reduction("comment", old, new, real_paths, frozenset())
        assert ok is False, (old, new, reason)

    # zero-space "review(F-2)": never matched by the token pattern at
    # all (it requires a literal space), so it must not be reachable
    # via any review-flag path either.
    refused("The review(F-2) found this.", "The review found this.")
    # paren holds MORE than just the F-ID -- dropping F-5 alone.
    refused("The review (D-3, F-5) found this.", "The review (D-3) found this.")
    # paren already carries its OWN provenance tag (a real path) --
    # the review flag must never bypass that tag.
    refused(
        "The review (docs/design/X_V1.md, F-4) found this.",
        "The review (docs/design/X_V1.md) found this.",
    )
    # paren holds "see" plus the F-ID -- not a sole-content match.
    refused("Per review (see F-12) the code is fixed.", "Per review (see) the code is fixed.")


def test_0i_rule1_unhyphenated_and_circled_forms_unchanged_is_green():
    # "F6" (no hyphen) and "F-①" (circled digit, not an ASCII digit) are
    # not ID-shaped -- unprotected before 0i, still unprotected after
    # (9.2's known constraint (b) is about un-indicated REVIEW pointers,
    # not these never-ID-shaped forms).
    assert cp._sentence_has_protected_reference("Code-review fix F6 landed.", frozenset()) is False
    assert cp._sentence_has_protected_reference("See F-① for detail.", frozenset()) is False


def test_0i_rule1_correction_cannot_drop_fid_is_red():
    # 0g's own "correction must not drop a protected reference" check
    # (design 9.2's fourth "使う箇所"), now extended to F-IDs.
    err = cp._correction_relaxes_protection("Bug F-2 occurs here.", "Bug occurs here.", frozenset())
    assert err is not None
    assert "F-2" in err


def test_0i_rule1_correction_substring_id_overlap_is_red():
    # F4 (code review): the old check compared "i not in new" as a
    # SUBSTRING test, so a correction turning F-1 into F-12 (F-1 is a
    # character subsequence -- in fact a literal substring -- of F-12)
    # silently passed. Must compare the SETS of extracted protected IDs.
    err = cp._correction_relaxes_protection("Code F-1 applies.", "Code F-12 applies.", frozenset())
    assert err is not None
    assert "F-1" in err


# --- rule 2: real path (suffix match, location-suffix stripped) --------

def test_0i_rule2_peer_relative_path_is_real_is_red(tmp_path):
    repo, rev = _real_paths_scenario(
        tmp_path, "Store (r2db_api/ops.py, D-3): body.", "Store: body.",
        extra_files=[("r2db-api/src/r2db_api/ops.py", "# stub\n")],
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (3)" in output


def test_0i_rule2_segment_boundary_required_is_green(tmp_path):
    # M5: a suffix that cuts through the MIDDLE of a path segment
    # ("rity/CONTROL_MAPPING.md" out of "security/CONTROL_MAPPING.md")
    # is never real -- stays a removable history token.
    repo, rev = _real_paths_scenario(
        tmp_path, "Note (D-3, rity/CONTROL_MAPPING.md): body.", "Note: body.",
        extra_files=[("security/CONTROL_MAPPING.md", "stub\n")],
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 0, output


def test_0i_rule2_location_suffix_stripped_is_real_is_red(tmp_path):
    # Z0i-3 (A): a trailing "::qualname" is stripped before the real-path
    # check, so a candidate naming a specific symbol inside a real file
    # is matched against that file, not rejected for the suffix.
    repo, rev = _real_paths_scenario(
        tmp_path, "Store (`r2db_api/service.py::Cls::meth`, D-3): body.", "Store: body.",
        extra_files=[("r2db-api/src/r2db_api/service.py", "# stub\n")],
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (3)" in output


def test_0i_rule2_dotted_qualname_and_call_suffix_stripped_is_real_is_red(tmp_path):
    # F1 (code review, major): the real-corpus DOMINANT form is a
    # DOTTED Python qualname (e.g. `cell.py::ApplicationCell.transact`),
    # and a call-suffix form (`::entities()`) also occurs -- the
    # stripper must handle both, not just an undotted `::ident::ident`
    # chain.
    repo, rev = _real_paths_scenario(
        tmp_path, "Store (`r2db_api/service.py::Cls.meth`, D-3): body.", "Store: body.",
        extra_files=[("r2db-api/src/r2db_api/service.py", "# stub\n")],
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (3)" in output
    assert cp._is_real_filename_candidate(
        "`r2db_api/limits.py::entities()`",
        frozenset({"r2db-api/src/r2db_api/limits.py"}),
    ) is True


def test_0i_rule2_peer_relative_sentence_whole_deletion_is_red():
    real_paths = frozenset({"MitateDB-api/migrations/0003_provision_application.sql"})
    sentence = "See migrations/0003_provision_application.sql for the schema."
    assert cp._sentence_has_protected_reference(sentence, real_paths) is True
    ok, reason = cp._is_allowed_reduction("comment", sentence, "", real_paths, frozenset())
    assert ok is False, reason


def test_0i_z0i4f_correction_swaps_location_suffix_only_is_green():
    # Z0i-4f: `_correction_relaxes_protection`'s lost-path comparison
    # must strip the location suffix the same way the real-path decision
    # already does (Z0i-3, `_is_real_filename_candidate`). A correction
    # that only replaces a `:line-line` range with a `::qualname` on the
    # SAME real path is not a relaxation -- the restorer's CH-0292
    # correction (`ops.py:541-550` -> `ops.py::_run_deprovision_script`)
    # is exactly this shape.
    real_paths = frozenset({"MitateDB-api/src/mitatedb_api/ops.py"})
    err = cp._correction_relaxes_protection(
        "See `MitateDB-api/src/mitatedb_api/ops.py:10-20` for detail.",
        "See `MitateDB-api/src/mitatedb_api/ops.py::func` for detail.",
        real_paths,
    )
    assert err is None


def test_0i_z0i4f_correction_drops_real_path_is_red():
    # A correction that drops the real path itself (not merely its
    # location suffix) must still be refused.
    real_paths = frozenset({"MitateDB-api/src/mitatedb_api/ops.py"})
    err = cp._correction_relaxes_protection(
        "See `MitateDB-api/src/mitatedb_api/ops.py:10-20` for detail.",
        "See the updated rule.",
        real_paths,
    )
    assert err is not None
    assert "MitateDB-api/src/mitatedb_api/ops.py" in err


# (rule 3's test, test_0i_rule3_ambiguous_basename_is_real_is_red, lives
# in place of the replaced test_v072_ambiguous_basename_filename_removable_
# is_green above, among the other real-path fixtures.)

# --- rule 4: nested (enclosing) parens ----------------------------------

def test_0i_rule4_id_branch_in_tagged_paren_not_removable_is_red(tmp_path):
    # Only D-5(ii) is removed here (its own preceding separator with
    # it); "design" and "contract 1.8.0" both stay -- "design" alone is
    # never independently removable (rule 3's kind-word sweep only
    # clears a parenthetical down to "", never down to a partial kind-
    # word residue), so this is the only candidate that isolates rule
    # 4's own tag-dependent judgment on D-5(ii).
    repo, rev = _label_scenario(
        tmp_path, "Note (design D-5(ii), contract 1.8.0): body.", "Note (design, contract 1.8.0): body."
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (3)" in output


def test_0i_rule4_enclosing_paren_tag_protects_inner_bare_id_is_red(tmp_path):
    repo, rev = _real_paths_scenario(
        tmp_path,
        "Note (see docs/design/X_V1.md §3 (D-4, WP-2)): body.",
        "Note (see docs/design/X_V1.md §3 (WP-2)): body.",
        extra_files=[("docs/design/X_V1.md", "stub\n")],
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (3)" in output


def test_0i_rule4_history_token_branch_in_tagged_paren_removable_is_green(tmp_path):
    repo, rev = _real_paths_scenario(
        tmp_path,
        "Note (see docs/design/X_V1.md §3 (D-4, WP-6d (ii))): body.",
        "Note (see docs/design/X_V1.md §3 (D-4)): body.",
        extra_files=[("docs/design/X_V1.md", "stub\n")],
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 0, output


# --- M3: label exclusion 2 also calls the sentence-level check ---------

def test_0i_label_with_real_path_not_removable_is_red(tmp_path):
    # A history token alone ("phase 3") makes this a candidate label,
    # and it carries no ID at all, so pre-M3 `_label_has_protected_
    # reference` never looked at the real path in it (its own ID-only
    # check found nothing) -- M3 makes it also call the sentence-level
    # protected-reference check, which does see the real path.
    repo, rev = _real_paths_scenario(
        tmp_path,
        "Per docs/design/X_V1.md phase 3: reason.",
        "reason.",
        extra_files=[("docs/design/X_V1.md", "stub\n")],
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (3)" in output


def test_0i_label_m3_without_protected_reference_stays_removable_is_green(tmp_path):
    # F9: M3's own GREEN side -- the ADDED sentence-level check
    # (_sentence_has_protected_reference) finds nothing here (no ID, no
    # real path), so a label carrying only a plain history token still
    # qualifies for removal exactly as before M3.
    repo, rev = _label_scenario(tmp_path, "Per phase 3: reason.", "reason.")
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 0, output


# ===========================================================================
# R-63 WP-1 (docs/work-orders/WORK_ORDER_R63_PROVENANCE_NEW_SYMBOL_BLOCKS_V1.md
# §2.2): §4.1 (2)'s CH-ID-less column opens for blocks attached to a symbol
# absent from the base rev (D-1, J-1, J-2), while an addition to an EXISTING
# target stays red (D-2) and (5)'s history-token scan still reaches a new
# symbol's own block (condition (b)). Each scenario asserts, per §2.2's own
# observation rule, the presence/absence of the literal "§4.1 (2)" line --
# not the overall exit code, since (1) (a real code change) legitimately
# still fires whenever a brand-new statement is added.
# ===========================================================================

def test_r63_new_function_with_docstring_is_green(tmp_path):
    repo = _init_repo(tmp_path)
    old = "def alpha():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    new = old + '\n\ndef beta():\n    """Computes beta."""\n    return 2\n'
    _write(repo, "r2db-api/src/r2db_api/mod.py", new)

    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert "§4.1 (2)" not in output, output


def test_r63_new_module_constant_with_comment_is_green(tmp_path):
    repo = _init_repo(tmp_path)
    old = "LIMIT = 3\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    new = "LIMIT = 3\n\n# New ceiling for the cache.\nMAX = 5\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", new)

    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert "§4.1 (2)" not in output, output


def test_r63_new_function_docstring_history_token_is_red(tmp_path):
    # condition (b): a new symbol's own block is still subject to (5)'s
    # history-token scan even though it is exempt from (2).
    repo = _init_repo(tmp_path)
    old = "def alpha():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    new = old + '\n\ndef beta():\n    """Computes beta (WP-1).\n    """\n    return 2\n'
    _write(repo, "r2db-api/src/r2db_api/mod.py", new)

    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert "§4.1 (5)" in output, output
    assert "§4.1 (2)" not in output, output


def test_r63_moved_block_into_new_function_is_red_at_old_key(tmp_path):
    # D-1(c): a "new symbol" disguise must not hide an existing block's
    # move -- the OLD side of its key still reports the loss (old 1, new
    # 0), even though the destination (a brand-new function) is itself
    # exempt from (2).
    repo = _init_repo(tmp_path)
    old = "def alpha(x):\n    # Guard against negative input.\n    return x + 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    new = (
        "def beta(y):\n    # Guard against negative input.\n    return y\n"
        "\n\ndef alpha(x):\n    return x + 1\n"
    )
    _write(repo, "r2db-api/src/r2db_api/mod.py", new)

    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert "§4.1 (2)" in output, output
    assert "(old 1, new 0)" in output, output


def test_r63_new_block_before_existing_statement_is_red(tmp_path):
    # D-2: the target statement ("import os") already exists in the base
    # rev, so a CH-ID-less block placed in front of it is never exempt.
    repo = _init_repo(tmp_path)
    old = "import os\n\nLIMIT = 3\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    new = "import os\n\n# Read the ceiling from the environment when set.\nLIMIT = 3\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", new)

    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert "§4.1 (2)" in output, output


def test_r63_insert_statement_before_existing_block_is_green(tmp_path):
    # §1.2 (i): a new, unrelated statement inserted ahead of an unchanged
    # existing block must not move that block's own key.
    repo = _init_repo(tmp_path)
    old = "# Ceiling for the queue.\nLIMIT = 3\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    new = "T = 5\n\n# Ceiling for the queue.\nLIMIT = 3\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", new)

    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert "§4.1 (2)" not in output, output


def test_r63_value_only_change_of_commented_constant_is_green(tmp_path):
    # J-1: an `Assign` token is the TARGET only, never the value, so a
    # value-only edit still aligns to the same statement and keeps its
    # block attached ((1) still separately reports the value change).
    repo = _init_repo(tmp_path)
    old = "# Ceiling for the queue.\nLIMIT = 3\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    new = "# Ceiling for the queue.\nLIMIT = 4\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", new)

    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert "§4.1 (2)" not in output, output


def test_r63_new_function_after_scope_final_block_is_green(tmp_path):
    # §1.2 (iv): an unchanged scope-final block, still last in its own key
    # group, is unaffected by a brand-new function appended after it.
    repo = _init_repo(tmp_path)
    old = "LIMIT = 3\n\n# Trailing note about the module.\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    new = old + "\n\ndef beta(y):\n    return y - 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", new)

    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert "§4.1 (2)" not in output, output


def test_r63_block_moved_between_identical_siblings_is_red(tmp_path):
    # J-1 (ii): two structurally identical statements (`pass`, `pass`) are
    # still distinguished by their OWN position in the old body, so moving
    # a block from before the first to before the second is still red.
    repo = _init_repo(tmp_path)
    old = "def f():\n    # Note.\n    pass\n    pass\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    new = "def f():\n    pass\n    # Note.\n    pass\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", new)

    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert "§4.1 (2)" in output, output


# ===========================================================================
# R-63 WP-1, code review round 1 (差し戻し、監督裁定 2026-09-20): 4 items.
# ===========================================================================

_PROPSRC = (
    "class C:\n"
    "    @property\n"
    "    def value(self):\n"
    '        """Returns the cached value."""\n'
    "        return self._v\n"
    "\n"
    "    @value.setter\n"
    "    def value(self, v):\n"
    '        """Stores a new value."""\n'
    "        self._v = v\n"
)

_GETTER_ONLY = (
    "class C:\n"
    "    @property\n"
    "    def value(self):\n"
    '        """Returns the cached value."""\n'
    "        return self._v\n"
)


def test_r63_review1_property_setter_unchanged_is_green(tmp_path):
    # 重大 1: same-named sibling scopes (`@property`/`@x.setter`) must not
    # collide in the J-1 alignment cache -- an untouched pair is fully
    # green, not a false (2) red from one sibling's blocks being aligned
    # against the OTHER sibling's body.
    repo = _init_repo(tmp_path)
    _write(repo, "r2db-api/src/r2db_api/mod.py", _PROPSRC)
    rev = _commit_all(repo, "old")
    _write(repo, "r2db-api/src/r2db_api/mod.py", _PROPSRC)

    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert "§4.1 (2)" not in output, output


def test_r63_review1_new_setter_sibling_getter_unaffected_is_green(tmp_path):
    # 重大 1: adding a same-named sibling (a `@x.setter` where only the
    # `@property` existed before) is D-1's "new symbol" -- its own
    # docstring is green, AND the pre-existing getter's docstring is not
    # dragged along into a spurious mismatch by the collision.
    repo = _init_repo(tmp_path)
    _write(repo, "r2db-api/src/r2db_api/mod.py", _GETTER_ONLY)
    rev = _commit_all(repo, "old")
    _write(repo, "r2db-api/src/r2db_api/mod.py", _PROPSRC)

    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert "§4.1 (2)" not in output, output


def test_r63_review1_docstring_edit_inside_if_body_is_red_once(tmp_path):
    # 重大 2: a `def` nested inside a NON-scope compound statement
    # (`if True:`) is not itself a J-1 "scope", so its docstring text
    # lives inside the `if` statement's own `ast.dump` token. Without
    # recursively stripping docstrings from that token (the same
    # `_strip_docstrings_for_ast` (1) uses), the edit wrongly perturbs the
    # `if` statement's alignment and doubles an unrelated trailing
    # module-level comment's own error count (1 -> 2).
    repo = _init_repo(tmp_path)
    old = (
        "# Module note about the fallback.\n"
        "if True:\n"
        "    def helper():\n"
        '        """Does the work."""\n'
        "        return 1\n"
    )
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    new = old.replace("Does the work.", "Does the work well.")
    _write(repo, "r2db-api/src/r2db_api/mod.py", new)

    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert output.count("§4.1 (2)") == 1, output


def test_r63_review1_ast_equal_diffs_align_by_identity(tmp_path):
    # 中 (完了条件 10 の強化): for several AST-equal (per (1)) diffs -- a
    # pure line-shift, a comment reworded with code unchanged, and a
    # docstring reworded with code unchanged -- the module scope's J-1
    # alignment must be the IDENTITY map (every old index corresponds to
    # itself), which is exactly what a plain structural INDEX key would
    # already give: nothing about (2)'s verdict changes for a pure
    # code-invariant diff.
    pairs = [
        ("X = 1\nY = 2\n", "\n\nX = 1\n\nY = 2\n"),
        ("# Note A.\nX = 1\n\nY = 2\n", "# Note A changed.\nX = 1\n\nY = 2\n"),
        (
            'def f():\n    """Doc f."""\n    return 1\n\n\ndef g():\n    return 2\n',
            'def f():\n    """Doc f v2."""\n    return 1\n\n\ndef g():\n    return 2\n',
        ),
    ]
    assert len(pairs) >= 2
    for old_src, new_src in pairs:
        assert cp.ast_signature(old_src) == cp.ast_signature(new_src)
        old_body = ast.parse(old_src).body
        new_body = ast.parse(new_src).body
        mapping = cp._align_scope_bodies(old_body, new_body)
        assert len(old_body) == len(new_body)
        assert mapping == {i: i for i in range(len(old_body))}, mapping


def test_r63_review1_duplicated_block_before_new_function_is_green(tmp_path):
    # 低 (逐語コピー): duplicating an EXISTING block so a copy also sits in
    # front of a brand-new function is allowed -- 原本が残る限り許す -- as
    # long as the original's own key still holds it (checked here: it
    # does, the original stays attached to the pre-existing statement).
    repo = _init_repo(tmp_path)
    old = "# Guard the queue.\nX = 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    new = "# Guard the queue.\ndef newf():\n    pass\n\n\n# Guard the queue.\nX = 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", new)

    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert "§4.1 (2)" not in output, output


def test_r63_review1_non_leading_bare_string_is_content_sensitive():
    # 低 (docstring の範囲): `_token_for_stmt`'s `is_first` restriction must
    # match design §4.1 (1)'s own docstring shape exactly (`body[0]`
    # only) -- a bare string Expr statement NOT at that position is an
    # ordinary, content-sensitive statement: editing its text must NOT
    # align to its old self (index 1), unlike its unaffected neighbours
    # (index 0 and index 2, which do align).
    old_body = ast.parse('def f():\n    x = 1\n    "note"\n    y = 2\n').body[0].body
    new_body = ast.parse('def f():\n    x = 1\n    "note changed"\n    y = 2\n').body[0].body
    mapping = cp._align_scope_bodies(old_body, new_body)
    assert mapping.get(0) == 0
    assert 1 not in mapping, mapping
    assert mapping.get(2) == 2


# ===========================================================================
# Change set 0j: a re-edited block's companion correction record may now be
# recorded in the SAME changeset as the reword (design
# docs/design/CODE_COMMENT_PROVENANCE_V1.md §9.3, work order
# docs/work-orders/WORK_ORDER_R68_PROVENANCE_SAME_CHANGESET_REWORD_V1.md
# WP-1). `_same_changeset_scenario` commits a revision whose SOURCE and
# companion still reflect the state BEFORE the reword (plus any correction
# entries already committed in an earlier changeset -- `base_correction_
# blocks`), then leaves the WORKING TREE with the reworded source and the
# companion carrying the full correction list (`all_correction_blocks`,
# base entries first, any new ones appended after).
# ===========================================================================

def _same_changeset_scenario(
    tmp_path, old_src, new_src, companion_lines, base_correction_blocks, all_correction_blocks,
    *, kind="comment", rel_path="r2db-api/src/r2db_api/mod.py",
    companion_rel_path="docs/code-history/r2db-api/mod.md",
    base_has_companion_file=True, base_section_present=True, working_companion_lines=None,
):
    repo = _init_repo(tmp_path)
    _write(repo, rel_path, old_src)
    if base_has_companion_file:
        if base_section_present:
            base_section = _companion_section("CH-0001", "\n".join(companion_lines), kind=kind)
            base_section += "".join(base_correction_blocks)
        else:
            # completion condition 5's second shape: the basis rev's
            # companion FILE exists, but carries only a DIFFERENT CH-ID's
            # section -- CH-0001's own section is absent from the file,
            # distinct from the file itself being absent
            # (`base_has_companion_file=False`).
            base_section = _companion_section("CH-9999", "# Unrelated section.")
        _write(repo, companion_rel_path, base_section)
    rev = _commit_all(repo, "old")
    _write(repo, rel_path, new_src)
    working_lines = companion_lines if working_companion_lines is None else working_companion_lines
    full_section = _companion_section("CH-0001", "\n".join(working_lines), kind=kind)
    full_section += "".join(all_correction_blocks)
    _write(repo, companion_rel_path, full_section)
    return repo, rev


_0J_WRAPPED_OLD = [
    "# The widget behaves the old way across multiple",
    "# lines for backward compatibility.",
]
_0J_WRAPPED_NEW = [
    "# The widget behaves the new way across multiple",
    "# lines for backward compatibility.",
]
_0J_WRAPPED_CORRECTION = _correction_block(
    "2026-09-20", "behavior changed",
    "The widget behaves the old way across multiple lines for backward compatibility.",
    "The widget behaves the new way across multiple lines for backward compatibility.",
)


def test_0j_comment_reword_with_same_changeset_correction_is_green(tmp_path):
    # Completion condition 1 (wrapped basis block, R1-2): the basis
    # revision carries no correction for CH-0001 at all (base = 0
    # entries); the working tree reword and its correction record are
    # recorded together.
    old_src = "\n".join(_0J_WRAPPED_OLD) + "\n# history: CH-0001\ndef f():\n    return 1\n"
    new_src = "\n".join(_0J_WRAPPED_NEW) + "\n# history: CH-0001\ndef f():\n    return 1\n"
    repo, rev = _same_changeset_scenario(
        tmp_path, old_src, new_src, _0J_WRAPPED_OLD, [], [_0J_WRAPPED_CORRECTION],
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 0, output


def test_0j_docstring_reword_with_same_changeset_correction_is_green(tmp_path):
    # Completion condition 2 (wrapped basis block, R1-2): same shape, a
    # docstring block instead of a comment.
    companion_lines = [
        "The widget stores state using the old on-disk format",
        "across process restarts.",
    ]
    old_src = (
        'def f():\n    """The widget stores state using the old on-disk format\n'
        '    across process restarts.\n\n    History: CH-0001\n    """\n    return 1\n'
    )
    new_src = (
        'def f():\n    """The widget stores state using the new on-disk format\n'
        '    across process restarts.\n\n    History: CH-0001\n    """\n    return 1\n'
    )
    correction = _correction_block(
        "2026-09-20", "format changed",
        "The widget stores state using the old on-disk format across process restarts.",
        "The widget stores state using the new on-disk format across process restarts.",
    )
    repo, rev = _same_changeset_scenario(
        tmp_path, old_src, new_src, companion_lines, [], [correction], kind="docstring",
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 0, output


def test_0j_two_pending_corrections_chain_is_green(tmp_path):
    # Completion condition 3: two pending corrections, the second
    # chaining on the first's own `new` text.
    companion_lines = ["# Step one runs first then step two runs second."]
    old_src = "\n".join(companion_lines) + "\n# history: CH-0001\ndef f():\n    return 1\n"
    new_src = "# Phase one runs first then phase two runs second.\n# history: CH-0001\ndef f():\n    return 1\n"
    corr1 = _correction_block(
        "2026-09-20", "step one renamed",
        "Step one runs first then step two runs second.",
        "Phase one runs first then step two runs second.",
    )
    corr2 = _correction_block(
        "2026-09-20", "step two renamed",
        "Phase one runs first then step two runs second.",
        "Phase one runs first then phase two runs second.",
    )
    repo, rev = _same_changeset_scenario(
        tmp_path, old_src, new_src, companion_lines, [], [corr1, corr2],
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 0, output


def test_0j_pending_old_absent_from_basis_block_is_noop_green(tmp_path):
    # Completion condition 4: an earlier (uncorrelated) reduction already
    # deleted the sentence a pending correction still names -- 0
    # occurrences applies no change rather than erroring.
    companion_lines = [
        "# Kept sentence stays here.",
        "# Removed sentence was deleted earlier.",
    ]
    old_src = "# Kept sentence stays here.\n# history: CH-0001\ndef f():\n    return 1\n"
    new_src = old_src  # the block itself is untouched in this changeset
    correction = _correction_block(
        "2026-09-20", "stale, sentence already gone",
        "Removed sentence was deleted earlier.", "Replacement text should not appear.",
    )
    repo, rev = _same_changeset_scenario(
        tmp_path, old_src, new_src, companion_lines, [], [correction],
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 0, output


def test_0j_no_basis_companion_section_treats_all_as_pending_is_green(tmp_path):
    # Completion condition 5 (F-1): the basis revision has no companion
    # file for CH-0001 at all -- base corrections are 0, every working-
    # tree correction is pending.
    companion_lines = ["# Plain content stays as is."]
    old_src = "\n".join(companion_lines) + "\n# history: CH-0001\ndef f():\n    return 1\n"
    new_src = "# Plain content now stays updated.\n# history: CH-0001\ndef f():\n    return 1\n"
    correction = _correction_block(
        "2026-09-20", "content updated",
        "Plain content stays as is.", "Plain content now stays updated.",
    )
    repo, rev = _same_changeset_scenario(
        tmp_path, old_src, new_src, companion_lines, [], [correction], base_has_companion_file=False,
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 0, output


def test_0j_no_basis_section_in_present_companion_file_treats_all_as_pending_is_green(tmp_path):
    # Completion condition 5's second shape (F-1): the basis revision's
    # companion FILE exists (unlike the fixture above) but carries only
    # a DIFFERENT CH-ID's section -- CH-0001's own section is absent
    # from the file, not the file itself.
    companion_lines = ["# Plain content stays as is."]
    old_src = "\n".join(companion_lines) + "\n# history: CH-0001\ndef f():\n    return 1\n"
    new_src = "# Plain content now stays updated.\n# history: CH-0001\ndef f():\n    return 1\n"
    correction = _correction_block(
        "2026-09-20", "content updated",
        "Plain content stays as is.", "Plain content now stays updated.",
    )
    repo, rev = _same_changeset_scenario(
        tmp_path, old_src, new_src, companion_lines, [], [correction], base_section_present=False,
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 0, output


def test_0j_reword_without_any_correction_record_is_red(tmp_path):
    # Completion condition 6, condition (a): a plain reword with no
    # correction record at all must stay red exactly as before.
    companion_lines = ["# Value uses the legacy format."]
    old_src = "\n".join(companion_lines) + "\n# history: CH-0001\ndef f():\n    return 1\n"
    new_src = "# Value uses the updated format.\n# history: CH-0001\ndef f():\n    return 1\n"
    repo, rev = _same_changeset_scenario(tmp_path, old_src, new_src, companion_lines, [], [])
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (3)" in output


def test_0j_basis_correction_new_rewritten_in_working_tree_is_red(tmp_path):
    # Completion condition 7, condition (b): a correction already
    # committed at the basis rev is edited (its `new` text changed) in
    # the working tree -- the prefix check must catch this positionally.
    companion_lines = ["# The widget used old behavior."]
    old_src = "# The widget used behavior X.\n# history: CH-0001\ndef f():\n    return 1\n"
    new_src = old_src
    base_corr = _correction_block(
        "2026-09-10", "reworded", "The widget used old behavior.", "The widget used behavior X.",
    )
    working_corr = _correction_block(
        "2026-09-10", "reworded", "The widget used old behavior.", "The widget used behavior Y.",
    )
    repo, rev = _same_changeset_scenario(
        tmp_path, old_src, new_src, companion_lines, [base_corr], [working_corr],
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§9.3 (2)" in output


def test_0j_basis_correction_deleted_in_working_tree_is_red(tmp_path):
    # Completion condition 8, condition (b): the basis rev has TWO
    # committed corrections; the working tree drops the second one --
    # the list got shorter, which is never a valid prefix relationship.
    companion_lines = ["# Sentence one original."]
    old_src = "# Sentence one fixed twice.\n# history: CH-0001\ndef f():\n    return 1\n"
    new_src = old_src
    corr1 = _correction_block(
        "2026-09-10", "first fix", "Sentence one original.", "Sentence one fixed.",
    )
    corr2 = _correction_block(
        "2026-09-11", "second fix", "Sentence one fixed.", "Sentence one fixed twice.",
    )
    repo, rev = _same_changeset_scenario(
        tmp_path, old_src, new_src, companion_lines, [corr1, corr2], [corr1],
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§9.3 (2)" in output


def test_0j_pending_correction_drops_protected_reference_is_red(tmp_path):
    # Completion condition 9, condition (c): a pending correction's `new`
    # silently drops the `old` sentence's protected reference (SI-08).
    companion_lines = ["# The body is plain here (SI-08)."]
    old_src = "\n".join(companion_lines) + "\n# history: CH-0001\ndef f():\n    return 1\n"
    new_src = "# The body is plain here now.\n# history: CH-0001\ndef f():\n    return 1\n"
    correction = _correction_block(
        "2026-09-20", "drops SI-08",
        "The body is plain here (SI-08).", "The body is plain here now.",
    )
    repo, rev = _same_changeset_scenario(
        tmp_path, old_src, new_src, companion_lines, [], [correction],
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§9f" in output
    assert "SI-08" in output
    assert "dropped" in output


def test_0j_pending_old_occurs_twice_is_red(tmp_path):
    # Completion condition 10 (R1-10): the pending `old` sentence occurs
    # TWICE in the basis block's own text. The new block below replaces
    # only the FIRST occurrence -- if the ambiguity check were bypassed,
    # this exact reduction would otherwise pass -- so a red here must be
    # attributable ONLY to the 2-occurrence ambiguity, never to the
    # unchanged full-chain check (F-4): a committed base correction
    # turns an unrelated placeholder sentence into the target wording
    # (so the full chain sees it exactly once against the companion's
    # own pristine text), while a SEPARATE, already-allowed bare-id
    # parenthetical removal turns the companion's second, still-
    # DIFFERENT sentence into the SAME wording only in the basis
    # block's own (committed) text -- the two occurrences the pending
    # correction ambiguously matches exist ONLY there.
    companion_lines = ["# Some placeholder text. Repeat sentence (R-9) stays."]
    old_src = "# Repeat sentence stays. Repeat sentence stays.\n# history: CH-0001\ndef f():\n    return 1\n"
    new_src = "# Fixed sentence now. Repeat sentence stays.\n# history: CH-0001\ndef f():\n    return 1\n"
    base_correction = _correction_block(
        "2026-09-10", "placeholder replaced",
        "Some placeholder text.", "Repeat sentence stays.",
    )
    pending_correction = _correction_block(
        "2026-09-20", "one occurrence fixed",
        "Repeat sentence stays.", "Fixed sentence now.",
    )
    repo, rev = _same_changeset_scenario(
        tmp_path, old_src, new_src, companion_lines, [base_correction],
        [base_correction, pending_correction],
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§9f" in output
    assert "occurs 2 time" in output


def test_0j_unrecorded_sentence_added_alongside_reword_is_red(tmp_path):
    # Completion condition 11, condition (a): an unrecorded sentence is
    # smuggled in alongside an otherwise-valid, correction-backed reword.
    companion_lines = ["# The cache refreshes every five minutes."]
    old_src = "\n".join(companion_lines) + "\n# history: CH-0001\ndef f():\n    return 1\n"
    new_src = (
        "# The cache refreshes every ten minutes. This extra sentence was never recorded.\n"
        "# history: CH-0001\ndef f():\n    return 1\n"
    )
    correction = _correction_block(
        "2026-09-20", "interval changed",
        "The cache refreshes every five minutes.", "The cache refreshes every ten minutes.",
    )
    repo, rev = _same_changeset_scenario(
        tmp_path, old_src, new_src, companion_lines, [], [correction],
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (3)" in output


def test_0j_pending_old_absent_from_companion_original_is_red(tmp_path):
    # Completion condition 12 (F-4, unchanged existing check): an earlier
    # ALLOWED reduction (a bare-id parenthetical removal, unrelated to
    # any correction) already changed the basis block's own wording, so
    # the pending correction's `old` -- written against the basis
    # block's CURRENT form -- occurs once there but never in the
    # companion's own pristine original.
    companion_lines = ["# The cache uses LRU eviction (R-5)."]
    old_src = "# The cache uses LRU eviction.\n# history: CH-0001\ndef f():\n    return 1\n"
    new_src = "# The cache uses LRU eviction now.\n# history: CH-0001\ndef f():\n    return 1\n"
    correction = _correction_block(
        "2026-09-20", "reworded",
        "The cache uses LRU eviction.", "The cache uses LRU eviction now.",
    )
    repo, rev = _same_changeset_scenario(
        tmp_path, old_src, new_src, companion_lines, [], [correction],
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§9f" in output
    assert "occurs 0 time" in output


def test_0j_whole_block_move_with_pending_added_protected_ref_is_red(tmp_path):
    # Completion condition 13 (F-4's last sentence): the block is moved
    # away entirely (nothing retained); the pending correction ADDS a
    # protected reference (SI-08) that was not present before -- the
    # whole-move protected-reference check runs against the text AFTER
    # the pending correction is applied.
    companion_lines = ["# The helper runs synchronously."]
    old_src = "\n".join(companion_lines) + "\n# history: CH-0001\ndef f():\n    return 1\n"
    new_src = "# history: CH-0001\ndef f():\n    return 1\n"
    correction = _correction_block(
        "2026-09-20", "clarified with SI-08",
        "The helper runs synchronously.", "The helper runs synchronously per SI-08.",
    )
    repo, rev = _same_changeset_scenario(
        tmp_path, old_src, new_src, companion_lines, [], [correction],
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (3)" in output
    assert "SI-08" in output


def test_0j_rev_pair_check_ignores_uncommitted_pending_correction_is_green(tmp_path):
    # Completion condition 14 (J-1): the rev-vs-itself guard must read
    # the companion AND its correction records from the SAME rev the
    # source comes from -- an uncommitted correction record added to the
    # working tree's companion file (a same-changeset reword still in
    # progress) must never perturb a "rev vs itself" comparison, which
    # never even looks at the working tree.
    repo = _init_repo(tmp_path)
    src = "# The body is JSON.\n# history: CH-0001\ndef f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", src)
    _write(
        repo, "docs/code-history/r2db-api/mod.md",
        _companion_section("CH-0001", "# The body is JSON."),
    )
    rev = _commit_all(repo, "old")
    # Uncommitted, working-tree-only pending correction -- never
    # committed at `rev`.
    pending_correction = _correction_block(
        "2026-09-20", "reworded", "The body is JSON.", "The body uses JSON.",
    )
    section = _companion_section("CH-0001", "# The body is JSON.") + pending_correction
    _write(repo, "docs/code-history/r2db-api/mod.md", section)

    real_paths = cp._tree_paths(repo, rev)
    identifier_set = cp._tracked_identifier_set(repo, rev)
    out = io.StringIO()
    code = _check_rev_pair(repo, "r2db-api/src/r2db_api/mod.py", src, src, real_paths, identifier_set, out, rev=rev)
    assert code == 0, out.getvalue()


def test_0j_working_tree_rewrite_of_companion_original_is_red(tmp_path):
    # Completion condition 15 (R1-1): the companion's ORIGINAL fenced
    # block (never the append-only correction mechanism) is rewritten
    # directly in the working tree, bypassing the record -- since it is
    # always read from the working tree, this must still be caught.
    companion_lines = ["# The helper validates input strictly."]
    old_src = "\n".join(companion_lines) + "\n# history: CH-0001\ndef f():\n    return 1\n"
    new_src = old_src  # the code itself never changed
    working_companion_lines = ["# The helper validates input loosely."]
    repo, rev = _same_changeset_scenario(
        tmp_path, old_src, new_src, companion_lines, [], [],
        working_companion_lines=working_companion_lines,
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (2)" in output


def test_0j_pending_revives_previously_deleted_sentence_is_red(tmp_path):
    # Completion condition 16 (F-3): a sentence an earlier changeset
    # deleted is reintroduced into the code, "backed" by a pending
    # correction whose `old` text does not occur in the basis block's
    # own (already-reduced) text -- the stage-B basis is the basis
    # block's OWN body, never the receptacle's fully-corrected text, so
    # the revived sentence has no counterpart and is rejected as an
    # unaccounted-for addition.
    companion_lines = ["# Kept sentence stays. Removed sentence was cut earlier."]
    old_src = "# Kept sentence stays.\n# history: CH-0001\ndef f():\n    return 1\n"
    new_src = "# Kept sentence stays. Removed sentence is back again.\n# history: CH-0001\ndef f():\n    return 1\n"
    correction = _correction_block(
        "2026-09-20", "revival attempt",
        "Removed sentence was cut earlier.", "Removed sentence is back again.",
    )
    repo, rev = _same_changeset_scenario(
        tmp_path, old_src, new_src, companion_lines, [], [correction],
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (3)" in output


def test_0j_pair_md_basis_correction_rewritten_is_red(tmp_path):
    # Completion condition 17 (R1-4): the same basis-side prefix check
    # (F-2) applies to a CH-ID whose companion section lives in
    # `pair.md`, not a peer-specific file -- the basis-side enumeration
    # must find it there too.
    companion_lines = ["# Shared behavior stays old."]
    old_src = "# Shared behavior stays new.\n# history: CH-0001\ndef f():\n    return 1\n"
    new_src = old_src
    base_corr = _correction_block(
        "2026-09-10", "reworded", "Shared behavior stays old.", "Shared behavior stays new.",
    )
    working_corr = _correction_block(
        "2026-09-10", "reworded", "Shared behavior stays old.", "Shared behavior stays different.",
    )
    repo, rev = _same_changeset_scenario(
        tmp_path, old_src, new_src, companion_lines, [base_corr], [working_corr],
        companion_rel_path="docs/code-history/pair.md",
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§9.3 (2)" in output


def test_0j_unreadable_basis_companion_path_is_fail(tmp_path, monkeypatch):
    # Completion condition 25: a companion path the basis revision's OWN
    # tree lists (so `_companion_rel_paths` enumerates it) but whose
    # content `git show` then fails to read must be reported, never
    # silently folded into "0 corrections" -- that would push every
    # correction the unreadable file carries into `pending`, disabling
    # the append-only prefix check (design §9.3 rule 2) for every CH-ID
    # it covers. `git show` is monkeypatched to fail for exactly this
    # one path; the source file's own read is untouched.
    repo = _init_repo(tmp_path)
    _write(repo, "r2db-api/src/r2db_api/mod.py", "# body.\n# history: CH-0001\ndef f():\n    return 1\n")
    _write(repo, "docs/code-history/r2db-api/mod.md", _companion_section("CH-0001", "# body."))
    rev = _commit_all(repo, "old")

    real_git_show = cp._git_show
    unreadable_rel_path = "docs/code-history/r2db-api/mod.md"

    def flaky_git_show(repo_root, git_rev, rel_path):
        if rel_path == unreadable_rel_path:
            return None
        return real_git_show(repo_root, git_rev, rel_path)

    monkeypatch.setattr(cp, "_git_show", flaky_git_show)
    corrections_lookup, errors = cp._load_corrections_lookup(repo, "r2db-api", rev=rev)
    assert corrections_lookup == {}
    # This function's own errors carry no `FAIL (§9f) ` label --
    # `run_base`, the only caller that ever prints them, adds it once
    # itself.
    assert any(unreadable_rel_path in e and "could not be read" in e for e in errors), errors


def test_0j_unreadable_basis_rev_is_fail(tmp_path):
    # Completion condition 25's second shape: `rev` itself does not
    # resolve at all, so `_companion_rel_paths` would otherwise
    # enumerate zero paths (nothing to iterate, nothing to report) --
    # `_rev_tree_readable` is checked first so this is still a FAIL, not
    # a silent "0 corrections" indistinguishable from a legitimate rev
    # whose tree simply has no companion files yet.
    repo = _init_repo(tmp_path)
    _write(repo, "r2db-api/src/r2db_api/mod.py", "# body.\ndef f():\n    return 1\n")
    _commit_all(repo, "old")
    corrections_lookup, errors = cp._load_corrections_lookup(repo, "r2db-api", rev="not-a-real-rev")
    assert corrections_lookup == {}
    assert any("not-a-real-rev" in e and "could not be read" in e for e in errors), errors


def test_0j_ls_tree_failure_on_resolvable_rev_is_fail(tmp_path, monkeypatch):
    # A rev that resolves fine (`_rev_tree_readable` succeeds) but whose
    # own companion-tree enumeration (`git ls-tree`, via
    # `_tree_paths_or_none`) then fails outright must also be a hard
    # FAIL, never silently read as an empty (0-corrections) tree --
    # `_tree_paths` itself keeps its documented fail-toward-empty
    # contract for every OTHER caller; only the basis-record enumeration
    # in `_load_corrections_lookup` is hardened this way.
    repo = _init_repo(tmp_path)
    _write(repo, "r2db-api/src/r2db_api/mod.py", "# body.\ndef f():\n    return 1\n")
    rev = _commit_all(repo, "old")

    def failing_tree_paths_or_none(repo_root, git_rev):
        return None

    monkeypatch.setattr(cp, "_tree_paths_or_none", failing_tree_paths_or_none)
    corrections_lookup, errors = cp._load_corrections_lookup(repo, "r2db-api", rev=rev)
    assert corrections_lookup == {}
    assert any("could not be enumerated" in e for e in errors), errors


_0K_R5_COMPANION = ["# The cache uses LRU eviction (R-5)."]
_0K_R5_OLD_SRC = "# The cache uses LRU eviction.\n# history: CH-0001\ndef f():\n    return 1\n"
_0K_R5_CORRECTION = _correction_block(
    "2026-09-21", "eviction policy changed",
    "The cache uses LRU eviction (R-5).", "The cache now uses LFU eviction (R-5).",
)


def test_0k_pending_old_matches_reduced_basis_sentence_is_replaced_green(tmp_path):
    # Fixture 17 (design §9.4): the receiving end's original sentence
    # carries a bare-id parenthetical (R-5) that an earlier, uncorrelated
    # §4.1 (4) reduction already dropped from the basis block before this
    # changeset's pending correction ever ran. The correction's `old` is
    # written against the receiving end's own (unreduced) wording, so it
    # occurs 0 times verbatim in the basis block; exactly one basis
    # sentence is a reduction of it, and that sentence is the one that
    # gets replaced.
    new_src = "# The cache now uses LFU eviction (R-5).\n# history: CH-0001\ndef f():\n    return 1\n"
    repo, rev = _same_changeset_scenario(
        tmp_path, _0K_R5_OLD_SRC, new_src, _0K_R5_COMPANION, [], [_0K_R5_CORRECTION],
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 0, output


def test_0k_pending_replacement_then_reduced_again_is_green(tmp_path):
    # Fixture 18: same basis and correction as above, but the working
    # tree's new block goes on to drop the same bare-id parenthetical
    # from the correction's own `new` text -- stage B must accept a
    # reduction of `new` the same way it accepts a reduction of any
    # other sentence.
    new_src = "# The cache now uses LFU eviction.\n# history: CH-0001\ndef f():\n    return 1\n"
    repo, rev = _same_changeset_scenario(
        tmp_path, _0K_R5_OLD_SRC, new_src, _0K_R5_COMPANION, [], [_0K_R5_CORRECTION],
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 0, output


def test_0k_pending_old_reduced_sentence_ambiguous_is_red(tmp_path):
    # Fixture 19: the basis block's own text carries the same reduced
    # wording twice -- each one independently a reduction of a DIFFERENT
    # bare-id sentence on the receiving end (R-5 / R-7), so the pending
    # correction's `old` (written against just the R-5 sentence) still
    # occurs exactly once against the receiving end for the full-chain
    # check. The reduced-sentence search cannot tell which of the two
    # identical basis sentences the correction meant.
    companion = [
        "# The cache uses LRU eviction (R-5).",
        "# The cache uses LRU eviction (R-7).",
    ]
    old_src = (
        "# The cache uses LRU eviction. The cache uses LRU eviction.\n"
        "# history: CH-0001\ndef f():\n    return 1\n"
    )
    new_src = old_src
    repo, rev = _same_changeset_scenario(
        tmp_path, old_src, new_src, companion, [], [_0K_R5_CORRECTION],
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§9.4" in output
    assert "ambiguous" in output
    assert output.count("The cache uses LRU eviction.") >= 2


def test_0k_pending_reduced_sentence_left_stale_is_red(tmp_path):
    # Fixture 20: same basis and correction as fixture 17, but the new
    # block keeps the basis's own (stale) wording instead of picking up
    # the correction's `new` text -- stage B's basis now carries the
    # corrected sentence, and the stale wording is no longer reachable
    # from it.
    repo, rev = _same_changeset_scenario(
        tmp_path, _0K_R5_OLD_SRC, _0K_R5_OLD_SRC, _0K_R5_COMPANION, [], [_0K_R5_CORRECTION],
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§4.1 (3)" in output
    assert "no order-preserving match" in output


def test_0k_pending_old_written_in_reduced_form_is_red(tmp_path):
    # Fixture 21: writing the correction's `old` against the basis
    # block's own reduced wording, instead of the receiving end's
    # original, still fails the full-chain check exactly as before --
    # the reduced-sentence search only widens what stage B accepts,
    # never what the full-correction chain against the companion's
    # pristine text accepts.
    correction = _correction_block(
        "2026-09-21", "eviction policy changed",
        "The cache uses LRU eviction.", "The cache now uses LFU eviction.",
    )
    new_src = "# The cache now uses LFU eviction.\n# history: CH-0001\ndef f():\n    return 1\n"
    repo, rev = _same_changeset_scenario(
        tmp_path, _0K_R5_OLD_SRC, new_src, _0K_R5_COMPANION, [], [correction],
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§9f" in output
    assert "occurs 0 time" in output


def test_0k_pending_reduction_occurs_twice_in_basis_is_red(tmp_path):
    # Fixture 22 (design §9.4 rule 1's uniqueness clause): the basis
    # block's own text is "Rule 4: The connection is closed. The
    # connection is closed." -- two sentences, the SECOND of which is
    # the only one reachable from the pending correction's `old` (the
    # first carries an unrelated leading label the correction's `old`
    # never mentions). Naming exactly one reachable sentence is not
    # enough: that sentence's own literal text also occurs a second
    # time, as the tail end of the FIRST (longer) sentence, so a
    # position-blind `str.replace(..., 1)` would silently rewrite the
    # wrong occurrence -- the first sentence's own tail, not the second
    # sentence the correction actually names.
    companion = [
        "# Rule 4: The connection is closed.",
        "# The connection is closed (R-5).",
    ]
    old_src = (
        "# Rule 4: The connection is closed. The connection is closed.\n"
        "# history: CH-0001\ndef f():\n    return 1\n"
    )
    new_src = (
        "# Rule 4: The connection is closed. The socket is now closed (R-5).\n"
        "# history: CH-0001\ndef f():\n    return 1\n"
    )
    correction = _correction_block(
        "2026-09-21", "connection wording updated",
        "The connection is closed (R-5).", "The socket is now closed (R-5).",
    )
    repo, rev = _same_changeset_scenario(
        tmp_path, old_src, new_src, companion, [], [correction],
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 1
    assert "§9.4" in output
    assert "ambiguous" in output
    assert "occurs 2 time" in output


def test_0k_pending_old_reaches_basis_only_via_label_strip_is_green(tmp_path):
    # Fixture 22': the receiving end's original sentence carries BOTH a
    # §4.1 (6) leading label ("Ruling U-7: ", an unprotected bare id) and
    # a bare-id parenthetical (R-5); the basis block has already dropped
    # both, keeping only the bare sentence. The pending correction's
    # `old` is written in the receiving end's full (labelled, bracketed)
    # form, so it is unreachable from the basis sentence directly -- only
    # stripping the label first (design §9.4 rule 1's `or` clause) makes
    # the remaining bracketed sentence reduce to the basis sentence.
    companion = ["# Ruling U-7: The cache uses LRU eviction (R-5)."]
    old_src = "# The cache uses LRU eviction.\n# history: CH-0001\ndef f():\n    return 1\n"
    new_src = (
        "# Ruling U-7: The cache now uses LFU eviction (R-5).\n"
        "# history: CH-0001\ndef f():\n    return 1\n"
    )
    correction = _correction_block(
        "2026-09-21", "eviction policy changed",
        "Ruling U-7: The cache uses LRU eviction (R-5).",
        "Ruling U-7: The cache now uses LFU eviction (R-5).",
    )
    repo, rev = _same_changeset_scenario(
        tmp_path, old_src, new_src, companion, [], [correction],
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 0, output



# ===========================================================================
# R-89 (docs/work-orders/WORK_ORDER_R89_PROVENANCE_PLAIN_BLOCK_KEY_V1.md;
# design docs/design/CODE_COMMENT_PROVENANCE_V1.md §4.1 (2) v0.26):
# a CH-ID-less block's own text is unchanged, but the statement it
# immediately precedes was rewritten (not merely line-shifted) -- the
# `replace`-pair byte-identity gate (`_replace_pairs`, `_plain_block_keys`)
# keeps the block's old key when it is the SAME statement, rewritten, and
# the block's own dedented text already sat at that exact old key.
# ===========================================================================

def test_r89_try_except_added_after_unchanged_docstring_is_green(tmp_path):
    # D-4 (i): the docstring block itself is byte-identical; only the
    # `try` statement immediately after it gains an `except` clause. The
    # block's own text never moved and never changed -- this must stay
    # green even though the `try` statement's own `ast.dump` differs.
    repo = _init_repo(tmp_path)
    old = (
        'def f():\n    """Returns the rows."""\n'
        "    try:\n        return g()\n    finally:\n        h()\n"
    )
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    new = (
        'def f():\n    """Returns the rows."""\n'
        "    try:\n        return g()\n    except KeyError:\n        raise\n"
        "    finally:\n        h()\n"
    )
    _write(repo, "r2db-api/src/r2db_api/mod.py", new)

    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert "§4.1 (2)" not in output, output


def test_r89_edited_block_before_rewritten_statement_stays_red(tmp_path):
    # D-4 (ii), D-1's own byte-identity gate: same shape as the green case
    # above, but the docstring's OWN text is also edited by one word.
    # Rewriting the following statement must NOT excuse the block's own,
    # separate, unaccounted-for edit -- the exact `(old 1, new 0)` count
    # is asserted verbatim (守る条件 (c): no smuggling a different block's
    # text past the old block's key just because the next statement was
    # also rewritten).
    repo = _init_repo(tmp_path)
    old = (
        'def f():\n    """Returns the rows."""\n'
        "    try:\n        return g()\n    finally:\n        h()\n"
    )
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    new = (
        'def f():\n    """Returns the row."""\n'
        "    try:\n        return g()\n    except KeyError:\n        raise\n"
        "    finally:\n        h()\n"
    )
    _write(repo, "r2db-api/src/r2db_api/mod.py", new)

    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert "§4.1 (2)" in output, output
    assert "(old 1, new 0)" in output, output


def test_r89_replace_1to2_block_before_first_is_green(tmp_path):
    # D-4 (iv), `replace` region old-len 1 -> new-len 2: the block stays
    # attached to the FIRST new statement (old i-th <-> new i-th pairing,
    # k=0 only) -- unchanged text, same relative position, green.
    repo = _init_repo(tmp_path)
    old = "def f():\n    # Note.\n    print(1)\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    new = "def f():\n    # Note.\n    print(11)\n    print(2)\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", new)

    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert "§4.1 (2)" not in output, output


def test_r89_replace_1to2_block_before_second_is_red(tmp_path):
    # D-4 (iv): the SAME region, but the block now precedes the SECOND
    # new statement -- outside the `min(1, 2)` = 1 paired position, so it
    # is an unaccounted-for move.
    repo = _init_repo(tmp_path)
    old = "def f():\n    # Note.\n    print(1)\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    new = "def f():\n    print(11)\n    # Note.\n    print(2)\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", new)

    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert "§4.1 (2)" in output, output


def test_r89_replace_2to1_block_on_surviving_stmt_is_green(tmp_path):
    # D-4 (v), `replace` region old-len 2 -> new-len 1: the block precedes
    # the position that survives (paired old i=0 <-> new i=0) -- green.
    repo = _init_repo(tmp_path)
    old = "def f():\n    # Note.\n    print(1)\n    print(2)\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    new = "def f():\n    # Note.\n    print(11)\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", new)

    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert "§4.1 (2)" not in output, output


def test_r89_replace_2to1_block_on_vanishing_stmt_is_red(tmp_path):
    # D-4 (v): the block was attached to the SECOND old statement (the
    # one with no counterpart once the pair collapses to one). It stays
    # in the file, immediately before the sole remaining statement (the
    # only place left to put it) -- but the byte-identity gate requires
    # an OLD block to have sat AT THE PAIRED old index (`stmt#0`, the
    # FIRST/surviving one), not merely somewhere in the same replace
    # region, so this still loses its key and stays red.
    repo = _init_repo(tmp_path)
    old = "def f():\n    print(1)\n    # Note.\n    print(2)\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    new = "def f():\n    # Note.\n    print(11)\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", new)

    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert "§4.1 (2)" in output, output


def test_r89_new_docstring_on_existing_function_stays_red(tmp_path):
    # D-2 (ii), D-4 (ix): R-67's own case (RM:511) -- a function that
    # already existed in the base rev gains its FIRST docstring. This is
    # the intentionally-kept-red "old 0, new 1" case (out of scope for
    # this work order); it must not be swept up by the `replace`-pair
    # gate above.
    repo = _init_repo(tmp_path)
    old = "def f():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    new = 'def f():\n    """Returns one."""\n    return 1\n'
    _write(repo, "r2db-api/src/r2db_api/mod.py", new)

    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert "§4.1 (2)" in output, output
    assert "(old 0, new 1)" in output, output


def test_r89_new_block_before_rewritten_statement_is_green(tmp_path):
    # D-4 (vi), S10: a block that did NOT exist in the base rev at all is
    # placed immediately before a statement that was itself rewritten (a
    # `replace` pair, not merely line-shifted) -- still green, exactly
    # like any other brand-new block whose anchor has no OLD counterpart.
    repo = _init_repo(tmp_path)
    old = "def f():\n    print(1)\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    new = "def f():\n    # Brand new note.\n    print(2)\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", new)

    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert "§4.1 (2)" not in output, output


def test_r89_renamed_function_preceding_block_stays_red(tmp_path):
    # D-4 (vii), D-1's node-type/name condition, S12: a `def` renamed
    # (same kind, DIFFERENT name) must NOT pair with its old self --
    # renaming is not "the same statement, rewritten" for this rule, so
    # the untouched preceding comment still loses its key.
    repo = _init_repo(tmp_path)
    old = "# Guard the queue.\ndef alpha():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    new = "# Guard the queue.\ndef beta():\n    return 1\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", new)

    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert "§4.1 (2)" in output, output


def test_r89_different_call_same_kind_preceding_block_is_green(tmp_path):
    # D-4 (viii), D-2 (vi) known limitation, S19: substituting a DIFFERENT
    # statement of the SAME AST kind (a call to a different function) at
    # the block's anchor position is indistinguishable, by this rule
    # alone, from an in-place rewrite -- the block stays paired to its
    # old key even though what it precedes now says something else.
    repo = _init_repo(tmp_path)
    old = "def f():\n    # Note.\n    b()\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    new = "def f():\n    # Note.\n    d()\n"
    _write(repo, "r2db-api/src/r2db_api/mod.py", new)

    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert "§4.1 (2)" not in output, output


def test_r89_moved_across_same_named_sibling_scopes_stays_red(tmp_path):
    # R-89: the byte-identity gate must
    # match by INTERNAL scope identity (`_internal_scope_and_anchor_for_
    # block`), not the plain DISPLAY name -- a block moved from a
    # `@property` getter's body to its `@x.setter` sibling's body, with
    # BOTH bodies' own following statements independently rewritten (so
    # both land in a `replace` pair), must still lose its key: the getter
    # and setter share the same plain name ("value") but are DIFFERENT
    # internal (`#k`-disambiguated) scopes.
    repo = _init_repo(tmp_path)
    old = (
        "class C:\n"
        "    @property\n"
        "    def value(self):\n"
        "        # Note.\n"
        "        print(1)\n"
        "\n"
        "    @value.setter\n"
        "    def value(self, v):\n"
        "        print(2)\n"
    )
    _write(repo, "r2db-api/src/r2db_api/mod.py", old)
    rev = _commit_all(repo, "old")
    new = (
        "class C:\n"
        "    @property\n"
        "    def value(self):\n"
        "        print(11)\n"
        "\n"
        "    @value.setter\n"
        "    def value(self, v):\n"
        "        # Note.\n"
        "        print(22)\n"
    )
    _write(repo, "r2db-api/src/r2db_api/mod.py", new)

    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert "§4.1 (2)" in output, output


def test_r89_real_commit_0d0f8c9_reproduction(tmp_path):
    # D-5: the actual R-71 regression (commit `0d0f8c9`,
    # `MitateDB-api/src/mitatedb_api/backend_postgres.py`) reproduced in a
    # throwaway repo. Fails outright (never skips) if the real repository
    # does not have this commit. Before this fix the "sequence of
    # CH-ID-less blocks changed" line appeared twice, for
    # `PostgresBackend.all_field_constraints` and
    # `PostgresBackend.all_field_types`; after it, zero.
    sha = "0d0f8c9"
    rel = "MitateDB-api/src/mitatedb_api/backend_postgres.py"
    check = subprocess.run(
        ["git", "cat-file", "-e", sha], cwd=REAL_REPO_ROOT, capture_output=True
    )
    assert check.returncode == 0, f"real commit {sha} not found in {REAL_REPO_ROOT}"

    def _blob(rev: str) -> str:
        r = subprocess.run(
            ["git", "show", f"{rev}:{rel}"], cwd=REAL_REPO_ROOT, capture_output=True
        )
        assert r.returncode == 0, r.stderr
        return r.stdout.decode()

    old = _blob(f"{sha}~1")
    new = _blob(sha)

    repo = _init_repo(tmp_path)
    _write(repo, rel, old)
    rev = _commit_all(repo, "old")
    _write(repo, rel, new)

    code, output = _run_base(repo, rev, rel)
    seq_lines = [
        line for line in output.splitlines()
        if "§4.1 (2)" in line and "the sequence of CH-ID-less blocks changed" in line
    ]
    assert seq_lines == [], seq_lines
    # R-89: a positive observation, so a run that
    # silently produced NO output at all (e.g. a crash swallowed upstream)
    # could not pass this assertion by vacuously satisfying it. This
    # throwaway single-file repo lacks the OTHER files this commit's
    # CH-ID companions live in, so `run_base` still fails overall (exit
    # 1) on 12 unrelated `§4.1 (2)` lines (companion-section-not-found /
    # unmatched-own-reference, for CH-0525/0526/0528/0529/0530/0537) --
    # this fix narrows the "sequence changed" count, it does not silence
    # the check.
    assert code == 1, (code, output)
    all_two_lines = [line for line in output.splitlines() if "§4.1 (2)" in line]
    assert len(all_two_lines) == 12, all_two_lines


# ---------------------------------------------------------------------------
# WORK_ORDER_DOC_ARCHIVE_SPLIT_V1.md WP-1, completion condition (4):
# `_companion_files`'s enumeration of a peer's companions never includes a
# duplicate placed under docs/archive/docs/code-history/<peer>/ -- the
# `peer_dir` it globs is `docs/code-history/<peer>/` itself (non-recursive),
# not `docs/` at large, so a path outside that one directory is invisible
# regardless of the recursion depth `docs/archive/...` happens to sit at
# (design docs/design/DOC_ARCHIVE_SPLIT_V1.md D-3 (ii)). This is 4a of the
# 2-way split (監督裁定, 設計レビュー指摘) -- the GLOB-based enumeration
# (`_companion_files`, used by the working-tree path); 4b below covers the
# TREE-based enumeration (`_companion_rel_paths_from_tree`, used by the
# rev-based `--base` path).
# Mutation (WP-1 manifest entry 4a, same entry/2 edits): widen `peer_dir`
# to `repo_root / "docs"` and change `.glob("*.md")` to `.rglob("*.md")`
# -- both edits together make the archive duplicate below reappear in the
# enumeration.
# ---------------------------------------------------------------------------
def test_4a_archive_companion_duplicate_not_enumerated_via_glob(tmp_path):
    repo = tmp_path / "repo"
    _write(repo, "docs/code-history/r2db-api/mod.md", "## CH-0001\n")
    _write(
        repo,
        "docs/archive/docs/code-history/r2db-api/x.md",
        "## CH-0002\n",
    )

    files = cp._companion_files(repo, "r2db-api")
    rels = sorted(str(p.relative_to(repo)) for p in files)

    assert rels != [], "companion enumeration must not be empty (空振り禁止)"
    assert "docs/code-history/r2db-api/mod.md" in rels, rels
    assert "docs/archive/docs/code-history/r2db-api/x.md" not in rels, rels


# ---------------------------------------------------------------------------
# WORK_ORDER_DOC_ARCHIVE_SPLIT_V1.md WP-1, completion condition 4b (2-way
# split, 監督裁定, 設計レビュー指摘): the TREE-based companion enumeration
# (`_companion_rel_paths_from_tree`, used by the rev-based `--base` path --
# tools/check_comment_provenance.py:2005-2018) also never returns a
# docs/archive/ duplicate: its prefix check (`p.startswith(peer_prefix)`)
# already excludes any path not starting exactly with
# `docs/code-history/<peer>/`, so `docs/archive/docs/code-history/
# r2db-api/x.md` never qualifies regardless of the `"/" not in
# p[len(peer_prefix):]` non-recursion guard.
# Mutation (WP-1 manifest entry 4b): loosen the exact-prefix check to a
# bare containment test (`peer_prefix in p`) and drop the non-recursion
# guard in the same edit -- the archive duplicate then reappears in the
# enumeration alongside the real companion.
# ---------------------------------------------------------------------------
def test_4b_archive_companion_duplicate_excluded_from_tree_enumeration():
    tree_paths = frozenset(
        {
            "docs/archive/docs/code-history/r2db-api/x.md",
            "docs/code-history/r2db-api/y.md",
        }
    )

    rel_paths = cp._companion_rel_paths_from_tree("r2db-api", tree_paths)

    assert rel_paths != [], "companion enumeration must not be empty (空振り禁止)"
    assert rel_paths == ["docs/code-history/r2db-api/y.md"], rel_paths
