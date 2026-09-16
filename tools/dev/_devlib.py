"""_devlib.py -- shared helpers for tools/dev/ (pt, mutate, gate, finalize).

tools/dev/ turns procedures that docs/work-orders/OPERATING_CONDITIONS.md
makes agents repeat by hand into single commands, so one tool call replaces
several (see tools/dev/README.md). Standard library only.

WP-2 (docs/work-orders/WORK_ORDER_R44_TEST_PG_ISOLATION_V1.md §3.1 (c)):
`hold_flag()` / `blockers()` / `wait_clear()` / `other_pytest()` /
`current_other_pytest()` / `parse_ps()` and the gate-hold flag file they
served are removed. PostgreSQL exclusivity is now a real flock
(`tools/testpg/dsa_testpg.py`'s own `suite_lock()`), taken by gate.py /
perf_baseline.py directly and by every owned-mode pytest run via its own
conftest.py -- never re-derived here by scanning `ps`. Only the mutation-
journal check survives, renamed `journal_blocker()`.
"""
from __future__ import annotations

import hashlib
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path

JOURNAL_NAME = "dev-mutate-journal.json"

# Exit codes kept clear of pytest's own 0-5.
RESTORE_FAILED = 70  # a mutated file could not be verified as restored
REFUSED = 75         # refused to start: unfinished mutation journal, or (gate.py/perf_baseline.py)
                     # the exclusive suite lock timed out (dsa_testpg.TestPgError)
PARTIAL = 76         # finalize: committed, but not (fully) merged
ERROR = 78           # precondition / usage error


class DevError(Exception):
    """A precondition failed; the message is printed and the tool exits ERROR."""


# ---------------------------------------------------------------------------
# Repository layout
# ---------------------------------------------------------------------------

def git(cwd: Path, *args: str, check: bool = True) -> str:
    proc = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise DevError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout


def worktree_root(start: Path) -> Path:
    return Path(git(start, "rev-parse", "--show-toplevel").strip())


def main_checkout(start: Path) -> Path:
    """Root of the main checkout that owns `start` (a linked worktree or the
    main tree itself): the parent of git's common dir."""
    common = git(start, "rev-parse", "--path-format=absolute", "--git-common-dir").strip()
    return Path(common).parent


def venv_python(start: Path) -> str:
    """The shared `.venv` interpreter of the main checkout (worktrees have none)."""
    path = main_checkout(start) / ".venv" / "bin" / "python"
    if not path.exists():
        raise DevError("no shared interpreter at <main checkout>/.venv/bin/python (pass --python)")
    return str(path)


def journal_path(start: Path) -> Path:
    """Per-worktree record of a mutation run in progress (inside the git dir, never tracked)."""
    return Path(git(start, "rev-parse", "--path-format=absolute", "--git-path", JOURNAL_NAME).strip())


def log_dir() -> Path:
    """Default place for full logs: the session scratchpad ($SP) when set."""
    sp = os.environ.get("SP")
    if sp:
        path = Path(sp) / "dev-logs"
        path.mkdir(parents=True, exist_ok=True)
        return path
    return Path(tempfile.mkdtemp(prefix="dev-logs-"))


def stamp() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


# ---------------------------------------------------------------------------
# Mutation journal (OPERATING_CONDITIONS 1.4-28..31)
# ---------------------------------------------------------------------------

def journal_blocker(root: Path) -> str | None:
    """The one blocker `blockers()` used to check besides the gate-hold flag
    and the `ps` poll (WP-2 §3.1 (c) keeps only this part): an unfinished
    `mutate.py` run left a journal in this worktree's git dir. None when
    clear."""
    path = journal_path(root)
    if path.exists():
        return f"unfinished mutation run: {path} (run tools/dev/mutate.py --recover)"
    return None


# ---------------------------------------------------------------------------
# Suite-lock timeout detection (review M-3, WP-2 §3.1 (a)/(c)): pt.py and
# mutate.py both launch a pytest subprocess whose OWN owned-mode conftest.py
# may block waiting for gate.py's exclusive suite lock, then fail at
# collection time with `dsa_testpg.TestPgError` when that wait times out --
# an ordinary pytest usage/collection error (exit 2-4) indistinguishable
# from a real breakage by exit code alone. Detected here by the launcher's
# own, fixed error text (never a DSN or password -- `tools/testpg/
# dsa_testpg.py`'s own module docstring) rather than re-deriving the
# condition from `dsa_testpg.gate_running()`, which only reports "right
# now", not "at the moment this subprocess's own conftest.py actually
# tried" -- a real race window a pre-check cannot close.
#
# The marker text alone is NOT enough (found the hard way, running this
# tool's own WP-2 mutation spec against tools/tests/test_testpg.py: a
# mutation of `_acquire_suite_lock` legitimately made a unit test's OWN
# `_real_acquire_suite_lock(...)` call raise a real `TestPgError` whose
# message happens to contain "waiting for the shared suite lock" -- that is
# the mutation's own INTENDED, scored "red", not an infrastructure timeout,
# and pytest reported it as an ordinary test FAILURE with a normal tally
# line). So this also requires that NOTHING was actually collected/run
# (work order review M-3's own wording): either no parseable tally line at
# all (pytest aborted before it could even report one -- the real shape of
# a conftest.py import-time TestPgError), or a tally whose `passed`/`failed`
# are both zero (only `errors`/`no tests ran`). A run that did complete and
# report real passed/failed counts is never treated as a lock timeout, no
# matter what text appears inside an assertion message.
# ---------------------------------------------------------------------------

_LOCK_TIMEOUT_MARKERS = (
    "waiting for gate intent to clear",
    "waiting for the exclusive suite lock",
    "waiting for the shared suite lock",
)


def lock_timeout_detected(output: str, tally: str | None) -> bool:
    """True when `output` (a pytest subprocess's combined stdout+stderr)
    contains `dsa_testpg.TestPgError`'s own suite-lock-timeout message AND
    `tally` (its own `tally_line(output)`) shows nothing was actually
    collected/run -- see this section's own module comment for why both
    conditions are required."""
    if not any(marker in output for marker in _LOCK_TIMEOUT_MARKERS):
        return False
    counts = parse_counts(tally)
    if counts is None:
        return True
    return not counts.get("passed") and not counts.get("failed")


# ---------------------------------------------------------------------------
# pytest output
# ---------------------------------------------------------------------------

_TALLY_HINT_RE = re.compile(r"\b\d+ (?:passed|failed|errors?|skipped|xfailed|xpassed|deselected)\b|no tests ran")
_COUNT_RE = re.compile(
    r"(\d+) (subtests passed|subtests failed|subtests skipped|subtests xfailed|subtests xpassed"
    r"|passed|failed|skipped|xfailed|xpassed|errors?|deselected|warnings?)"
)


def tally_line(stdout: str) -> str | None:
    """pytest's summary: the last non-empty line of stdout, undecorated, or None
    when that line is not a summary (a stray later line must not stand in for it)."""
    lines = [l for l in stdout.splitlines() if l.strip()]
    if not lines:
        return None
    line = lines[-1].strip().strip("=").strip()
    return line if _TALLY_HINT_RE.search(line) and " in " in line else None


def parse_counts(line: str | None) -> dict[str, int] | None:
    """Counts of a summary line; None if any part is not a known count."""
    if not line or " in " not in line:
        return None
    body = line.rpartition(" in ")[0]
    counts: dict[str, int] = {}
    for part in body.split(", "):
        m = _COUNT_RE.fullmatch(part.strip())
        if not m:
            return None
        key = {"error": "errors", "warning": "warnings"}.get(m.group(2), m.group(2))
        counts[key] = counts.get(key, 0) + int(m.group(1))
    return counts


def failure_lines(output: str, limit: int) -> list[str]:
    lines = [l for l in output.splitlines() if l.startswith(("FAILED ", "ERROR "))]
    return lines[:limit]


# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------

def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
