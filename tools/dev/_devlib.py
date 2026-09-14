"""_devlib.py -- shared helpers for tools/dev/ (pt, mutate, gate, finalize).

tools/dev/ turns procedures that docs/work-orders/OPERATING_CONDITIONS.md
makes agents repeat by hand into single commands, so one tool call replaces
several (see tools/dev/README.md). Standard library only.
"""
from __future__ import annotations

import hashlib
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path

HOLD_FLAG_NAME = "gate-hold.flag"
JOURNAL_NAME = "dev-mutate-journal.json"

# Exit codes kept clear of pytest's own 0-5.
RESTORE_FAILED = 70  # a mutated file could not be verified as restored
REFUSED = 75         # refused to start: hold flag, other pytest, unfinished mutation journal
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
# Gate hold flag and other pytest processes (OPERATING_CONDITIONS 1.3-20, 2-18)
# ---------------------------------------------------------------------------

def hold_flag(explicit: str | None) -> Path | None:
    """Resolve the supervisor's gate-hold flag.

    Order: --hold PATH, $GATE_HOLD_FLAG, $SP/gate-hold.flag. `--hold -` states
    that no supervisor gate exists in this session and returns None. With no
    source at all this raises: an unknown flag location must not silently
    count as "no hold" (OPERATING_CONDITIONS 1.3-26)."""
    if explicit == "-":
        return None
    if explicit:
        return Path(explicit)
    env = os.environ.get("GATE_HOLD_FLAG")
    if env:
        return Path(env)
    sp = os.environ.get("SP")
    if sp:
        return Path(sp) / HOLD_FLAG_NAME
    raise DevError("gate-hold flag location unknown: set SP or GATE_HOLD_FLAG, or pass --hold PATH (or --hold - when no supervisor gate exists)")


_PYTEST_ARGS_RE = re.compile(r"(?:^|\s)-m\s+pytest(?:\s|$)|(?:^|\s|/)(?:py\.test|pytest)(?:\s|$)")


def parse_ps(text: str) -> list[tuple[int, int, str]]:
    """Rows of `ps -eo pid=,ppid=,args=` as (pid, ppid, args)."""
    rows = []
    for line in text.splitlines():
        parts = line.strip().split(None, 2)
        if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
            rows.append((int(parts[0]), int(parts[1]), parts[2] if len(parts) == 3 else ""))
    return rows


def other_pytest(ps_text: str, self_pid: int) -> list[tuple[int, str]]:
    """pytest processes outside `self_pid`'s own chain (its ancestors and descendants).

    Only processes whose executable is python or pytest count, so a waiting
    shell or `grep pytest` never matches itself (OPERATING_CONDITIONS 2-18).
    The executable is matched on its basename, case-insensitively, so the
    truncated/capitalised `comm` of this machine does not matter."""
    rows = parse_ps(ps_text)
    parent = {pid: ppid for pid, ppid, _ in rows}
    skip = {self_pid}
    pid = self_pid
    while pid in parent and parent[pid] not in skip and parent[pid] > 0:
        pid = parent[pid]
        skip.add(pid)
    frontier = [self_pid]
    while frontier:
        children = [p for p, pp, _ in rows if pp in frontier and p not in skip]
        skip.update(children)
        frontier = children
    hits = []
    for pid, _, args in rows:
        if pid in skip or not args:
            continue
        exe = os.path.basename(args.split(None, 1)[0]).lower()
        if ("python" in exe or exe in ("pytest", "py.test")) and _PYTEST_ARGS_RE.search(args):
            hits.append((pid, args))
    return hits


def current_other_pytest() -> list[tuple[int, str]]:
    try:
        proc = subprocess.run(["ps", "-eo", "pid=,ppid=,args="], capture_output=True, check=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise DevError(f"cannot list processes: {exc}") from exc
    text = proc.stdout.decode("utf-8", errors="replace")
    if not any(pid == 1 for pid, _, _ in parse_ps(text)):
        raise DevError("process list looks incomplete (no PID 1); cannot check for other pytest")
    return other_pytest(text, os.getpid())


def blockers(flag: Path | None, root: Path | None = None) -> list[str]:
    reasons = []
    if flag is not None and flag.exists():
        reasons.append(f"gate hold flag present: {flag}")
    if root is not None and journal_path(root).exists():
        reasons.append(f"unfinished mutation run: {journal_path(root)} (run tools/dev/mutate.py --recover)")
    for pid, args in current_other_pytest():
        reasons.append(f"other pytest running: pid={pid} {args[:120]}")
    return reasons


def wait_clear(flag: Path | None, wait_seconds: float, root: Path | None = None, poll: float = 5.0) -> list[str]:
    """Blockers left after waiting up to `wait_seconds` (empty = clear)."""
    deadline = time.monotonic() + wait_seconds
    while True:
        reasons = blockers(flag, root)
        if not reasons or time.monotonic() >= deadline:
            return reasons
        time.sleep(poll)


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
