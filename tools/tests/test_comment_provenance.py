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
