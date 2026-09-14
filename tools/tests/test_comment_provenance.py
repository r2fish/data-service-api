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


def test_q4_real_repo_postgres_unchanged_is_green():
    # Real-repository check (read-only, per the file docstring's stated
    # exception for `test_repository_register_passes`): the actual,
    # already-migrated r2db `postgres.py` at main `5d12799`, left
    # UNCHANGED, must pass `--base 5d12799` cleanly. Before the v0.7
    # ruling this was blocked by several blocks (e.g. CH-0028) where
    # change set 1 stopped at a partial, rule-3-eligible-but-not-swept
    # reduction; the permissive derivation check now accepts those too.
    out = io.StringIO()
    code = cp.run_base(
        REAL_REPO_ROOT, "5d12799", ["r2db-api/src/r2db_api/postgres.py"], out=out, err=out
    )
    output = out.getvalue()
    assert code == 0, output


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


def test_v072_ambiguous_basename_filename_removable_is_green(tmp_path):
    # `README.md` exists at TWO different paths -- ambiguous, so it stays
    # a removable history token rather than becoming a provenance tag.
    repo, rev = _real_paths_scenario(
        tmp_path, "Note (README.md, D-3): body.", "Note: body.",
        extra_files=[("a/README.md", "stub\n"), ("b/README.md", "stub\n")],
    )
    code, output = _run_base(repo, rev, "r2db-api/src/r2db_api/mod.py")
    assert code == 0, output


def test_v072_unique_basename_matches_real_repo_control_mapping(tmp_path):
    # Confirms the real repository actually has exactly one
    # `CONTROL_MAPPING.md` (under security/) -- the precondition the
    # first fixture above relies on, pinned directly against HEAD's tree.
    real_paths = cp._tree_paths(REAL_REPO_ROOT, "HEAD")
    matches = [p for p in real_paths if p.rpartition("/")[2] == "CONTROL_MAPPING.md"]
    assert matches == ["security/CONTROL_MAPPING.md"], matches


def test_v072_mutation_basename_uniqueness_removed_would_break_control_mapping():
    # White-box companion to the "basename uniqueness check removed"
    # mutation: directly pins that a basename match alone (without
    # requiring exactly one) is not what makes CONTROL_MAPPING.md real.
    real_paths = frozenset({"security/CONTROL_MAPPING.md"})
    assert cp._is_real_filename_candidate("CONTROL_MAPPING.md", real_paths) is True
    ambiguous = frozenset({"a/README.md", "b/README.md"})
    assert cp._is_real_filename_candidate("README.md", ambiguous) is False


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
