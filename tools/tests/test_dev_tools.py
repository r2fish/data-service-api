"""tools/tests/test_dev_tools.py -- tests for tools/dev/ (pt, mutate, section,
gate, finalize) and their shared helpers.

Not under `conformance-tests/` and not in pyproject.toml's `testpaths` (same
convention as tools/tests/test_change_class.py). Everything runs in
temporary directories: temporary git repositories for finalize/mutate and a
tiny throwaway pytest project for the subprocess runs.

Run directly:
    ./.venv/bin/python -m pytest tools/tests/test_dev_tools.py -q
"""
from __future__ import annotations

import contextlib
import importlib
import importlib.util
import io
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

_DEV = Path(__file__).resolve().parents[1] / "dev"
_TESTPG = Path(__file__).resolve().parents[1] / "testpg"
sys.path.insert(0, str(_DEV))
sys.path.insert(0, str(_TESTPG))


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"dev_{name}", _DEV / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


dl = importlib.import_module("_devlib")  # the same module object the scripts import
dsa_testpg = importlib.import_module("dsa_testpg")  # the same module object gate.py / pt.py / mutate.py / handover_ready.py import
pt = _load("pt")
mutate = _load("mutate")
section = _load("section")
gate = _load("gate")
finalize = _load("finalize")
fold = _load("fold")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def isolated_git(monkeypatch, tmp_path):
    """No global/system git config (signing, hooks) leaks into the temp repos."""
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "no-global-gitconfig"))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("SP", str(tmp_path / "sp"))
    for var in ("GATE_HOLD_FLAG", "GIT_AUTHOR_EMAIL", "GIT_COMMITTER_EMAIL", "GIT_AUTHOR_NAME", "GIT_COMMITTER_NAME"):
        monkeypatch.delenv(var, raising=False)


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, check=True).stdout


def _init_repo(root: Path, files: dict[str, str]) -> Path:
    root.mkdir(parents=True)
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.name", "dev")
    _git(root, "config", "user.email", "1+dev@users.noreply.github.com")
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "init")
    return root


_CALC = "def add(a, b):\n    return a + b\n\n\ndef sub(a, b):\n    return a - b\n"
_TEST_CALC = "from calc import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n"


def _calc_project(tmp_path: Path) -> Path:
    return _init_repo(tmp_path / "proj", {
        "calc.py": _CALC, "test_calc.py": _TEST_CALC, "pytest.ini": "[pytest]\npythonpath = .\n",
        "a/b.py": "B = 1\n", "a__b.py": "AB = 1\n",
    })


def _intercept_pytest(monkeypatch, fn):
    """Replace only `python -m pytest` subprocess calls (git keeps working)."""
    real = subprocess.run

    def run(cmd, *args, **kwargs):
        if isinstance(cmd, list) and cmd[1:3] == ["-m", "pytest"]:
            return fn(cmd, **kwargs)
        return real(cmd, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", run)


# ---------------------------------------------------------------------------
# _devlib
# ---------------------------------------------------------------------------

def test_journal_blocker_reports_the_unfinished_run(isolated_git, tmp_path):
    proj = _calc_project(tmp_path)
    assert dl.journal_blocker(proj) is None
    dl.journal_path(proj).write_text("{}")
    blocker = dl.journal_blocker(proj)
    assert blocker is not None and "unfinished mutation run" in blocker and "--recover" in blocker


def test_tally_line_is_the_last_stdout_line_only():
    out = "....\nFAILED t.py::a - x\n==== 1 failed, 3294 passed, 12 subtests passed, 2 warnings in 99.1s (0:01:39) ====\n\n"
    line = dl.tally_line(out)
    assert line == "1 failed, 3294 passed, 12 subtests passed, 2 warnings in 99.1s (0:01:39)"
    assert dl.parse_counts(line) == {"failed": 1, "passed": 3294, "subtests passed": 12, "warnings": 2}
    assert dl.tally_line("3 passed, 1 skipped in 1s\nsome later line\n") is None
    assert dl.failure_lines(out, 5) == ["FAILED t.py::a - x"]


def test_parse_counts_rejects_unknown_parts():
    assert dl.parse_counts("1 error in 0.1s") == {"errors": 1}
    assert dl.parse_counts("3 passed, 1 rerun in 1s") is None
    assert dl.parse_counts("no tests ran in 0.01s") is None
    assert dl.parse_counts(None) is None


def test_exit_codes_do_not_overlap_pytest():
    assert {dl.RESTORE_FAILED, dl.REFUSED, dl.PARTIAL, dl.ERROR}.isdisjoint(range(0, 6))


def test_lock_timeout_detected_requires_both_the_marker_and_nothing_collected():
    """review M-3, found running this WP's own mutation spec against
    tools/tests/test_testpg.py: the marker text ALONE is not enough -- a
    unit test that deliberately exercises the real suite lock can legitimately
    raise a real `TestPgError` whose message contains this exact wording as
    part of a NORMAL, scored test failure (pytest still reports real
    passed/failed counts), which must never be reported as an
    infrastructure refusal. Only a run that collected/ran nothing at all
    (no tally, or passed=failed=0) counts.

    mutation (`tools/dev/_devlib.py`): drop the tally-based narrowing (marker
    text alone decides) -- this test goes red on the `marker_but_real_failure`
    case below."""
    marker = "timed out after 0.3s waiting for the shared suite lock: /x/suite.lock"
    assert dl.lock_timeout_detected(f"...\n{marker}\n", None) is True
    assert dl.lock_timeout_detected(f"...\n{marker}\n", "1 error in 0.1s") is True
    assert dl.lock_timeout_detected(f"...\n{marker}\n", "1 failed in 0.1s") is False  # marker_but_real_failure
    assert dl.lock_timeout_detected(f"...\n{marker}\n", "1 passed in 0.1s") is False
    assert dl.lock_timeout_detected("no marker here\n", None) is False


# ---------------------------------------------------------------------------
# pt
# ---------------------------------------------------------------------------

def test_pt_refuses_while_mutation_journal_exists(isolated_git, tmp_path):
    proj = _calc_project(tmp_path)
    dl.journal_path(proj).write_text("{}")
    buf = io.StringIO()
    assert pt.guarded_run(proj, sys.executable, ["-q"], 0, 5, out=buf) == dl.REFUSED
    assert "unfinished mutation run" in buf.getvalue()


def test_pt_reports_tally_failures_and_exit(isolated_git, tmp_path):
    proj = _calc_project(tmp_path)
    (proj / "test_calc.py").write_text(_TEST_CALC + "\n\ndef test_bad():\n    assert add(1, 1) == 3\n")
    buf = io.StringIO()
    code = pt.guarded_run(proj, sys.executable, ["-q"], 0, 5, out=buf, guard=False)
    text = buf.getvalue()
    assert code == 1
    assert "pt: 1 failed, 1 passed" in text
    assert "FAILED test_calc.py::test_bad" in text
    assert "pt: exit=1 log=" in text


def test_pt_forwards_wait_as_the_lock_wait_env_var(isolated_git, tmp_path, monkeypatch):
    """work order §3.1 (c): pt.py's own --wait becomes the budget the pytest
    subprocess's owned-mode cluster start-up (conftest.py ->
    dsa_testpg.ensure_for_pytest()) waits for gate.py's exclusive lock,
    forwarded via DSA_TEST_PG_LOCK_WAIT -- pt.py takes no lock of its own."""
    proj = _calc_project(tmp_path)
    seen = {}
    real_run = subprocess.run

    def spy(cmd, *a, **k):
        seen["env"] = k.get("env")
        return real_run(cmd, *a, **k)

    monkeypatch.setattr(subprocess, "run", spy)
    buf = io.StringIO()
    pt.guarded_run(proj, sys.executable, ["-q"], 42.5, 5, out=buf, guard=False)
    assert seen["env"][dsa_testpg.ENV_LOCK_WAIT] == "42.5"


def test_pt_refuses_on_a_lock_timeout(isolated_git, tmp_path, monkeypatch):
    """review M-3: a lock-wait timeout inside the pytest subprocess's own
    owned-mode conftest.py (`dsa_testpg.TestPgError`, an ordinary-looking
    pytest exit 2-4) is detected from the captured output and converted to
    REFUSED(75) -- never surfaced as if the suite itself were broken."""
    proj = _calc_project(tmp_path)
    fake = subprocess.CompletedProcess(
        [], 4, stdout=(
            "ImportError while loading conftest.py\n"
            "dsa_testpg.TestPgError: timed out after 0.0s waiting for the shared suite lock: /x/suite.lock\n"
        ), stderr="")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: fake)
    buf = io.StringIO()
    code = pt.guarded_run(proj, sys.executable, ["-q"], 0, 5, out=buf, guard=False)
    assert code == dl.REFUSED
    text = buf.getvalue()
    assert "pt: REFUSED --" in text and "suite lock wait timed out" in text


# ---------------------------------------------------------------------------
# mutate
# ---------------------------------------------------------------------------

def _mutate(proj: Path, spec: dict, tmp_path: Path) -> tuple[int, str]:
    buf = io.StringIO()
    code = mutate.run(spec, proj, sys.executable, out=buf, settle=0, work=tmp_path / "work")
    return code, buf.getvalue()


def _pristine(proj: Path) -> bool:
    return ((proj / "calc.py").read_text() == _CALC and (proj / "a/b.py").read_text() == "B = 1\n"
            and (proj / "a__b.py").read_text() == "AB = 1\n")


def test_mutate_red_expected_and_restored(isolated_git, tmp_path):
    proj = _calc_project(tmp_path)
    spec = {"pytest": ["-q", "test_calc.py"], "mutations": [
        {"id": "M1", "file": "calc.py", "old": "return a + b", "new": "return a - b  # MUT1", "expect": "red"},
        {"id": "M2", "file": "calc.py", "old": "return a - b\n", "new": "return a * b  # MUT2\n", "expect": "green"},
    ]}
    code, text = _mutate(proj, spec, tmp_path)
    assert code == 0, text
    assert "M1       expect=red   got=red" in text and "M2       expect=green got=green" in text
    assert _pristine(proj)
    assert "grep counts unchanged |" in text
    assert not dl.journal_path(proj).exists()


def test_mutate_needle_is_longest_new_line_absent_from_pristine():
    edit = {"new": "    if x:  # MUT\n        return None\n"}
    assert mutate.needle(edit, "def f(x):\n        return None\n") == "    if x:  # MUT"
    assert mutate.needle({"new": "        return None"}, "        return None\n") is None


def test_mutate_reports_grep_not_applicable(isolated_git, tmp_path, monkeypatch):
    proj = _calc_project(tmp_path)
    _intercept_pytest(monkeypatch, lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, stdout="1 failed in 0s\n", stderr=""))
    spec = {"pytest": ["-q"], "mutations": [
        {"id": "M1", "file": "calc.py", "old": "def sub(a, b):\n    return a - b\n", "new": "", "expect": "red"}]}
    code, text = _mutate(proj, spec, tmp_path)
    assert code == 0 and "n/a for 1 edits" in text


def test_mutate_unmet_expectation_exits_1(isolated_git, tmp_path):
    proj = _calc_project(tmp_path)
    spec = {"pytest": ["-q"], "mutations": [
        {"id": "M1", "file": "calc.py", "old": "return a - b", "new": "return b - a  # MUT", "expect": "red"}]}
    code, text = _mutate(proj, spec, tmp_path)
    assert code == 1 and "NG" in text
    assert _pristine(proj)


def test_mutate_non_unique_old_touches_nothing(isolated_git, tmp_path):
    proj = _calc_project(tmp_path)
    spec = {"pytest": ["-q"], "mutations": [
        {"id": "M1", "file": "calc.py", "old": "return a", "new": "return 0", "expect": "red"}]}
    with pytest.raises(dl.DevError, match="occurs 2 times"):
        _mutate(proj, spec, tmp_path)
    assert _pristine(proj)
    assert not (tmp_path / "work").exists()


@pytest.mark.parametrize("signum", [signal.SIGTERM, signal.SIGHUP])
def test_mutate_signal_restores_every_file_and_ignores_a_second_signal(isolated_git, tmp_path, monkeypatch, signum):
    proj = _calc_project(tmp_path)
    spec = {"pytest": ["-q"], "mutations": [{"id": "M1", "expect": "red", "edits": [
        {"file": "a/b.py", "old": "B = 1", "new": "B = 2  # MUT"},
        {"file": "a__b.py", "old": "AB = 1", "new": "AB = 2  # MUT"}]}]}

    def killed(cmd, **kw):
        assert (proj / "a/b.py").read_text() == "B = 2  # MUT\n"
        os.kill(os.getpid(), signum)
        raise AssertionError("signal handler did not run")

    real_copy_back = mutate.copy_back
    sent = {"n": 0}

    def signal_then_copy_back(*args):
        if sent["n"] == 0:  # a second signal arrives as the restore starts
            sent["n"] += 1
            os.kill(os.getpid(), signum)
        return real_copy_back(*args)

    _intercept_pytest(monkeypatch, killed)
    monkeypatch.setattr(mutate, "copy_back", signal_then_copy_back)
    before = signal.getsignal(signum)
    with pytest.raises(KeyboardInterrupt):
        _mutate(proj, spec, tmp_path)
    assert _pristine(proj)
    assert not dl.journal_path(proj).exists()
    assert signal.getsignal(signum) == before


def test_mutate_killed_run_leaves_journal_then_recover(isolated_git, tmp_path, monkeypatch):
    proj = _calc_project(tmp_path)
    spec = {"pytest": ["-q"], "mutations": [
        {"id": "M1", "file": "calc.py", "old": "return a + b", "new": "return 0  # MUT", "expect": "red"}]}

    class Killed(BaseException):  # stands in for SIGKILL: no cleanup code runs after it
        pass

    def sigkill(cmd, **kw):
        raise Killed

    with monkeypatch.context() as mp:
        _intercept_pytest(mp, sigkill)
        mp.setattr(mutate, "copy_back", lambda *a: (_ for _ in ()).throw(Killed()))
        with pytest.raises(Killed):
            _mutate(proj, spec, tmp_path)
    assert "return 0  # MUT" in (proj / "calc.py").read_text()
    assert dl.journal_path(proj).exists()
    with pytest.raises(dl.DevError, match="unfinished mutation run"):
        _mutate(proj, spec, tmp_path)
    buf = io.StringIO()
    assert mutate.recover(proj, out=buf, settle=0) == 0, buf.getvalue()
    assert _pristine(proj) and not dl.journal_path(proj).exists()


def test_mutate_interrupted_while_pristine_removes_journal(isolated_git, tmp_path, monkeypatch):
    """The journal is written (backups taken) before the first mutation's own
    `by_file()` call, which is the first thing the per-mutation loop does --
    interrupting there simulates a KeyboardInterrupt landing while every file
    is still pristine (WP-2 §3.1 (c) dropped the old wait_clear() call this
    test used to hook for the same purpose, since mutate.py no longer waits
    for anything before editing)."""
    proj = _calc_project(tmp_path)
    spec = {"pytest": ["-q"], "mutations": [
        {"id": "M1", "file": "calc.py", "old": "return a + b", "new": "return 0  # MUT", "expect": "red"}]}
    real_by_file = mutate.by_file
    calls = {"n": 0}

    def by_file_then_interrupt(edits):
        calls["n"] += 1
        if calls["n"] == 2:  # 1 = the pristine-apply precheck (before the journal is written),
            # 2 = the per-mutation loop's own first call (files still pristine at this point)
            assert dl.journal_path(proj).exists()
            raise KeyboardInterrupt
        return real_by_file(edits)

    monkeypatch.setattr(mutate, "by_file", by_file_then_interrupt)
    with pytest.raises(KeyboardInterrupt):
        mutate.run(spec, proj, sys.executable, out=io.StringIO(), settle=0, work=tmp_path / "work")
    assert _pristine(proj) and not dl.journal_path(proj).exists()


def test_mutate_forwards_wait_as_the_lock_wait_env_var(isolated_git, tmp_path, monkeypatch):
    """work order §3.1 (c): mutate.py's own --wait is forwarded the same way
    as pt.py's, via DSA_TEST_PG_LOCK_WAIT, to each per-mutation pytest
    subprocess -- mutate.py takes no lock of its own."""
    proj = _calc_project(tmp_path)
    seen = {}

    def spy(cmd, **kw):
        seen["env"] = kw.get("env")
        return subprocess.CompletedProcess(cmd, 0, stdout="1 passed in 0s\n", stderr="")

    _intercept_pytest(monkeypatch, spy)
    spec = {"pytest": ["-q"], "mutations": [
        {"id": "M1", "file": "calc.py", "old": "return a + b", "new": "return 0  # MUT", "expect": "green"}]}
    buf = io.StringIO()
    mutate.run(spec, proj, sys.executable, out=buf, settle=0, work=tmp_path / "work", wait=17.0)
    assert seen["env"][dsa_testpg.ENV_LOCK_WAIT] == "17.0"


def test_mutate_stops_on_a_lock_timeout_without_scoring_it(isolated_git, tmp_path, monkeypatch):
    """review M-3: a lock-wait timeout must STOP the run (REFUSED), after
    restoring the mutation that hit it, rather than being scored under any
    `expect` -- in particular `expect: "error"` must not silently accept an
    infrastructure timeout (pytest exit 2-4) as its own intended outcome."""
    proj = _calc_project(tmp_path)

    def timeout_pytest(cmd, **kw):
        return subprocess.CompletedProcess(
            cmd, 4, stdout="dsa_testpg.TestPgError: timed out after 0.0s waiting for the shared suite lock: /x/suite.lock\n",
            stderr="")

    _intercept_pytest(monkeypatch, timeout_pytest)
    spec = {"pytest": ["-q"], "mutations": [
        {"id": "M1", "file": "calc.py", "old": "return a + b", "new": "return 0  # MUT", "expect": "error"}]}
    code, text = _mutate(proj, spec, tmp_path)
    assert code == dl.REFUSED
    assert "mutate: STOPPED before M1 -- exclusive suite lock wait timed out" in text
    assert "expect=error got=" not in text
    assert _pristine(proj)


def test_mutate_restore_mismatch_aborts_and_still_restores(isolated_git, tmp_path, monkeypatch):
    proj = _calc_project(tmp_path)
    spec = {"pytest": ["-q", "test_calc.py"], "mutations": [
        {"id": "M1", "file": "calc.py", "old": "return a + b", "new": "return 0  # MUT", "expect": "red"},
        {"id": "M2", "file": "calc.py", "old": "return a - b", "new": "return 0  # MUT2", "expect": "green"}]}
    real_sha = dl.sha256
    calls = {"n": 0}

    def flaky_sha(path):
        calls["n"] += 1
        return "0" * 64 if calls["n"] == 3 else real_sha(path)  # 1 = backup hash, 2-3 = first restore check

    monkeypatch.setattr(dl, "sha256", flaky_sha)
    code, text = _mutate(proj, spec, tmp_path)
    assert code == dl.RESTORE_FAILED and "restore mismatch for calc.py" in text
    assert "M2 " not in text
    assert _pristine(proj)


def test_mutate_leftover_mutation_line_fails_final_grep(isolated_git, tmp_path, monkeypatch):
    proj = _calc_project(tmp_path)

    def leaks(cmd, **kw):
        (proj / "leak.txt").write_text("return 0  # MUT\n")
        return subprocess.CompletedProcess(cmd, 1, stdout="1 failed in 0s\n", stderr="")

    _intercept_pytest(monkeypatch, leaks)
    spec = {"pytest": ["-q"], "mutations": [
        {"id": "M1", "file": "calc.py", "old": "return a + b", "new": "return 0  # MUT", "expect": "red"}]}
    code, text = _mutate(proj, spec, tmp_path)
    assert code == dl.RESTORE_FAILED and "mutation line count changed" in text


@pytest.mark.parametrize("code,expect,ok", [
    (0, "green", True), (1, "green", False), (2, "green", False),
    (1, "red", True), (0, "red", False), (2, "red", False), (5, "red", False),
    (2, "error", True), (3, "error", True), (4, "error", True), (5, "error", True),
    (0, "error", False), (1, "error", False), (6, "error", False),
])
def test_mutate_matches_pins_red_green_and_error(code, expect, ok):
    """WP-2 (docs/work-orders/WORK_ORDER_R44_TEST_PG_ISOLATION_V1.md §3.1,
    follow-up to WP-1's `M13-no-lc-all`): `expect: "error"` must accept
    every pytest exit code 2-5 (interrupted / internal error / usage error /
    no tests collected) as satisfying it, while `"red"`/`"green"` stay exact
    (1/0 only) -- a mutation that breaks the run itself before collecting
    anything (e.g. a conftest.py that can no longer start its own cluster)
    is a real, intended "red" of a different shape than a failed test, not
    a mismatch. (0, "error", False) and (1, "error", False) in particular
    pin that a genuinely green or red run must NOT satisfy `expect: "error"`.

    mutation (`tools/dev/mutate.py`): widen `_ERROR_CODES` (or `matches()`'s
    own `"error"` branch) to also accept code 1 -- this test goes red on the
    `(1, "error", False)` case, exactly the WP-2 supervisor's own example of
    a genuinely-red mutation wrongly satisfying an "error" expectation."""
    assert mutate.matches(code, expect) is ok


def test_mutate_error_expect_accepts_a_pre_collection_failure(isolated_git, tmp_path, monkeypatch):
    """End-to-end: a mutation whose pytest subprocess exits 4 (usage error --
    stands in for a conftest.py that can no longer start its own cluster,
    WP-1's `M13-no-lc-all`) satisfies `expect: "error"`, and the printed
    `got=` stays the specific `error(4)`, not a generic "error" label."""
    proj = _calc_project(tmp_path)
    _intercept_pytest(monkeypatch, lambda cmd, **kw: subprocess.CompletedProcess(cmd, 4, stdout="usage error\n", stderr=""))
    spec = {"pytest": ["-q"], "mutations": [
        {"id": "M1", "file": "calc.py", "old": "return a + b", "new": "return 0  # MUT", "expect": "error"}]}
    code, text = _mutate(proj, spec, tmp_path)
    assert code == 0, text
    assert "M1       expect=error got=error(4)" in text


# ---------------------------------------------------------------------------
# section
# ---------------------------------------------------------------------------

DOC = """# Title
intro
## 1. One
one body
### 1.1 Sub
sub body
```text
## not a heading
```
## 2. Two WP-1j
two body
### 2.1 Deep
deep
## 3. Three
"""


def test_section_prints_until_same_or_higher_level(tmp_path):
    f = tmp_path / "d.md"
    f.write_text(DOC)
    buf = io.StringIO()
    assert section.main([str(f), "^1\\. One"], out=buf) == 0
    assert buf.getvalue().splitlines() == [
        "## 1. One", "one body", "### 1.1 Sub", "sub body", "```text", "## not a heading", "```"]
    buf = io.StringIO()
    assert section.main([str(f), "WP-1j", "-n"], out=buf) == 0
    assert buf.getvalue().splitlines()[0].split() == ["10", "##", "2.", "Two", "WP-1j"]
    assert len(buf.getvalue().splitlines()) == 4


def test_section_list_and_no_match(tmp_path):
    f = tmp_path / "d.md"
    f.write_text(DOC)
    buf = io.StringIO()
    section.main([str(f), "--list", "--depth", "2"], out=buf)
    assert [l.split(None, 1)[1] for l in buf.getvalue().splitlines()] == [
        "# Title", "## 1. One", "## 2. Two WP-1j", "## 3. Three"]
    assert section.main([str(f), "nope"], out=io.StringIO()) == 1


# ---------------------------------------------------------------------------
# gate
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("tally,code,ok", [
    ("3294 passed, 12 subtests passed in 90s", 0, True),
    ("3294 passed, 1 skipped in 90s", 0, False),
    ("3294 passed, 1 xpassed in 90s", 0, False),
    ("3294 passed, 2 deselected in 90s", 0, False),
    ("3294 passed, 1 subtests skipped in 90s", 0, False),
    ("3294 passed, 1 subtests xfailed in 90s", 0, False),
    ("3294 passed, 1 rerun in 90s", 0, False),
    ("1 failed, 3293 passed in 90s", 1, False),
    ("3294 passed in 90s", 1, False),
    ("3294 passed, 1 error in 90s", 1, False),
    (None, 2, False),
])
def test_gate_judge(tally, code, ok):
    assert gate.judge(code, tally)[0] is ok


def test_gate_catalog_diff():
    before = {"pg_database": ["a", "b"], "pg_roles": ["r"]}
    assert gate.diff(before, {"pg_database": ["a", "b"], "pg_roles": ["r"]}) == []
    assert gate.diff(before, {"pg_database": ["a", "b", "c"], "pg_roles": []}) == ["pg_database +1 -0", "pg_roles +0 -1"]


_EMPTY_CATALOGS = {"pg_database": [], "pg_roles": []}


class _FakeCluster:
    """Stands in for a real `dsa_testpg.Cluster` in gate tests -- no real
    PostgreSQL, no real dsa_testpg base dir touched."""

    def env(self):
        return {
            dsa_testpg.R2DB_DSN: "host=/fake/s port=5432 dbname=postgres user=postgres",
            dsa_testpg.MITATEDB_DSN: "host=/fake/s port=5432 dbname=postgres user=postgres",
            "PGHOST": "/fake/s", "PGPORT": "5432", "PGUSER": "postgres", "PGPASSFILE": "/fake/pgpass",
        }


@contextlib.contextmanager
def _fake_cluster_cm():
    yield _FakeCluster()


@contextlib.contextmanager
def _noop_lock_cm(*a, **k):
    yield


def _patch_gate_cluster_and_lock(monkeypatch, lock=None):
    """Every gate test except test_gate_holds_the_exclusive_lock fakes BOTH
    dsa_testpg.cluster (no real PostgreSQL) and dsa_testpg.suite_lock (no
    real, machine-shared lock file) -- this is the real, shared `dsa_testpg`
    module object gate.py itself imports (same idiom already used for `dl`
    above), so the patch is undone by monkeypatch at the end of each test."""
    monkeypatch.setattr(gate.dsa_testpg, "cluster", lambda: _fake_cluster_cm())
    monkeypatch.setattr(gate.dsa_testpg, "suite_lock", lock or (lambda *a, **k: _noop_lock_cm()))


def _gate_main(tmp_path, monkeypatch, capsys, run_before, run_after,
               shared_before=None, shared_after=None, code=0, tally="3 passed in 1.00s\n"):
    """gate.main with a fake cluster/lock and the catalog snapshots and the
    suite run injected -- no real database, no real pytest."""
    monkeypatch.setenv("SP", str(tmp_path / "sp"))
    _patch_gate_cluster_and_lock(monkeypatch)
    run_snaps = iter([run_before, run_after])
    shared_snaps = iter([shared_before or _EMPTY_CATALOGS, shared_after or shared_before or _EMPTY_CATALOGS])
    monkeypatch.setattr(gate, "run_snapshot", lambda env: next(run_snaps))
    monkeypatch.setattr(gate, "shared_snapshot", lambda: (next(shared_snaps), ""))

    def fake_run_suite(cmd, cwd, env, stdout_path):
        stdout_path.write_text(f"....\n{tally}", encoding="utf-8")
        return code

    monkeypatch.setattr(gate, "run_suite", fake_run_suite)
    result = gate.main(["--python", sys.executable, "-C", str(tmp_path)])
    out = capsys.readouterr().out.splitlines()
    log_line = next(l for l in out if l.startswith("gate: pg_database/pg_roles diff"))
    log_path = Path(log_line.rsplit("log=", 1)[1])
    return result, out, log_path.read_text(encoding="utf-8")


def test_gate_names_catalog_changes_in_log_and_bounded_stdout(tmp_path, monkeypatch, capsys):
    dbs = [f"t_db_{i:02d}" for i in range(12)]
    code, out, log = _gate_main(
        tmp_path, monkeypatch, capsys,
        {"pg_database": ["postgres", *reversed(dbs)], "pg_roles": ["postgres", "t_role_b", "t_role_a"]},
        {"pg_database": ["postgres", "t_new"], "pg_roles": ["postgres"]})
    assert code == 1
    assert out[:2] == ["gate: 3 passed in 1.00s", "gate: judge=FAIL (pg_database +1 -12, pg_roles +0 -2)"]
    assert out[2:-2] == [
        "gate: pg_database added (1): t_new",
        f"gate: pg_database removed (12): {', '.join(dbs[:10])}, ... +2 more",
        "gate: pg_roles removed (2): t_role_a, t_role_b",
    ]
    assert "t_db_10" not in "\n".join(out)
    assert out[-2].startswith("gate: pg_database/pg_roles diff pg_database +1 -12, pg_roles +0 -2 | log=")
    assert out[-1] == "gate: info=shared pg_database/pg_roles diff 0"
    assert log.startswith("....\n3 passed in 1.00s\n")
    section = log.split(f"== {gate.LOG_SECTION}", 1)[1].splitlines()[1:]
    assert section == ["pg_database added (1):", "  t_new", "pg_database removed (12):", *[f"  {d}" for d in dbs],
                       "pg_roles removed (2):", "  t_role_a", "  t_role_b"]


def test_gate_no_catalog_change_prints_no_names(tmp_path, monkeypatch, capsys):
    snap = {"pg_database": ["postgres"], "pg_roles": ["postgres"]}
    code, out, log = _gate_main(tmp_path, monkeypatch, capsys, snap, dict(snap))
    assert code == 0 and len(out) == 4 and out[1] == "gate: judge=PASS"
    assert out[-1] == "gate: info=shared pg_database/pg_roles diff 0"
    assert log.split(f"== {gate.LOG_SECTION}", 1)[1].splitlines()[1:] == ["0"]


def test_gate_fails_on_run_cluster_diff(tmp_path, monkeypatch, capsys):
    """WP-2 §3.1 table row 1: the gate's OWN run cluster's own diff decides
    PASS/FAIL -- the shared cluster here is unchanged, so this proves the
    run-cluster diff alone is what fails it."""
    snap = {"pg_database": ["postgres"], "pg_roles": ["postgres"]}
    code, out, _ = _gate_main(tmp_path, monkeypatch, capsys, snap,
                              {"pg_database": ["postgres", "t_new"], "pg_roles": ["postgres"]})
    assert code == 1
    assert "judge=FAIL" in out[1] and "pg_database +1 -0" in out[1]


def test_gate_shared_cluster_diff_is_info_only(tmp_path, monkeypatch, capsys):
    """WP-2 §3.1 table row 2 (Q-3): the shared local PostgreSQL's own diff
    is printed as an `info=` line and never fails the gate -- the run
    cluster here is unchanged, so a FAIL would only be explainable by the
    shared diff wrongly being judged."""
    snap = {"pg_database": ["postgres"], "pg_roles": ["postgres"]}
    code, out, _ = _gate_main(tmp_path, monkeypatch, capsys, snap, dict(snap),
                              shared_before=snap, shared_after={"pg_database": ["postgres", "shared_new"], "pg_roles": ["postgres"]})
    assert code == 0 and out[1] == "gate: judge=PASS"
    assert out[-1] == "gate: info=shared pg_database/pg_roles diff pg_database +1 -0"


def test_gate_passes_external_env_to_pytest(tmp_path, monkeypatch, capsys):
    """WP-2 §3.1 table row 3: the suite runs with DSA_TEST_PG=external and
    the gate's own cluster's Cluster.env(). Also review B-1: DSA_TEST_PG_
    LOCK_HELD=1 is in that same env, so a genuine nested owned-mode pytest
    the suite spawns (e.g. conformance-tests/test_testpg_cluster.py's own
    nested-controller tests) knows an ancestor already holds the lock and
    must not try to acquire it again."""
    monkeypatch.setenv("SP", str(tmp_path / "sp"))
    _patch_gate_cluster_and_lock(monkeypatch)
    monkeypatch.setattr(gate, "run_snapshot", lambda env: dict(_EMPTY_CATALOGS))
    monkeypatch.setattr(gate, "shared_snapshot", lambda: (dict(_EMPTY_CATALOGS), ""))
    seen = {}

    def fake_run_suite(cmd, cwd, env, stdout_path):
        seen["env"] = env
        stdout_path.write_text("....\n3 passed in 1.00s\n", encoding="utf-8")
        return 0

    monkeypatch.setattr(gate, "run_suite", fake_run_suite)
    code = gate.main(["--python", sys.executable, "-C", str(tmp_path)])
    assert code == 0
    fake_env = _FakeCluster().env()
    assert seen["env"][dsa_testpg.ENV_MODE] == "external"
    assert seen["env"][dsa_testpg.ENV_LOCK_HELD] == "1"
    assert seen["env"][dsa_testpg.R2DB_DSN] == fake_env[dsa_testpg.R2DB_DSN]
    assert seen["env"][dsa_testpg.MITATEDB_DSN] == fake_env[dsa_testpg.MITATEDB_DSN]
    assert seen["env"]["PGPASSFILE"] == fake_env["PGPASSFILE"]


def test_gate_holds_the_exclusive_lock(tmp_path, monkeypatch, capsys):
    """WP-2 §3.1 table row 4: gate.py actually takes the REAL exclusive
    suite lock (not a fake) for the duration of its run -- proven from a
    separate process trying a shared acquisition against the SAME (tmp,
    never the machine's real per-uid) base dir while gate.main() is
    "running" (run_suite is faked to do the probe synchronously, since the
    lock is already held by the time run_suite is reached)."""
    base = tmp_path / "base"
    base.mkdir()
    monkeypatch.setattr(gate.dsa_testpg, "_base_dir", lambda *a, **k: base)
    monkeypatch.setattr(gate.dsa_testpg, "cluster", lambda: _fake_cluster_cm())
    monkeypatch.setenv("SP", str(tmp_path / "sp"))
    monkeypatch.setattr(gate, "run_snapshot", lambda env: dict(_EMPTY_CATALOGS))
    monkeypatch.setattr(gate, "shared_snapshot", lambda: (dict(_EMPTY_CATALOGS), ""))

    script = (
        "import pathlib, sys; sys.path.insert(0, %r); import dsa_testpg\n"
        "try:\n"
        "    with dsa_testpg.suite_lock(False, 0.3, base=pathlib.Path(%r)):\n"
        "        pass\n"
        "except dsa_testpg.TestPgError:\n"
        "    sys.exit(75)\n"
        "sys.exit(0)\n"
    ) % (str(_TESTPG), str(base))

    def fake_run_suite(cmd, cwd, env, stdout_path):
        probe = subprocess.run([sys.executable, "-c", script])
        assert probe.returncode == 75, "a second process's shared acquisition must time out while gate holds the exclusive lock"
        stdout_path.write_text("....\n3 passed in 1.00s\n", encoding="utf-8")
        return 0

    monkeypatch.setattr(gate, "run_suite", fake_run_suite)
    code = gate.main(["--python", sys.executable, "-C", str(tmp_path)])
    assert code == 0
    # The exclusive lock is released on the way out: a fresh shared acquisition now succeeds.
    handle = dsa_testpg._acquire_suite_lock(exclusive=False, wait=1.0, base=base)
    handle.release()
    assert not (base / dsa_testpg.GATE_INTENT_NAME).exists()


def test_gate_refused_when_the_exclusive_lock_times_out(tmp_path, monkeypatch, capsys):
    base = tmp_path / "base"
    base.mkdir()
    monkeypatch.setattr(gate.dsa_testpg, "_base_dir", lambda *a, **k: base)
    held = dsa_testpg._acquire_suite_lock(exclusive=False, wait=1.0, base=base)  # a live "other pytest run"
    try:
        code = gate.main(["--python", sys.executable, "-C", str(tmp_path), "--wait", "0.3"])
    finally:
        held.release()
    assert code == dl.REFUSED
    out = capsys.readouterr().out
    assert "REFUSED" in out


def test_gate_cluster_startup_failure_is_error_and_releases_the_lock(tmp_path, monkeypatch, capsys):
    """review MINOR-3 (test gap 8): the gate's ERROR(78) path had no test at
    all after `test_gate_removes_only_its_own_flag_on_error` was deleted
    with the hold flag. Here `dsa_testpg.cluster()` itself raises
    `TestPgError` (a real cluster start-up failure, e.g. no postgres 16
    binary) with the REAL exclusive lock held (only `_base_dir` is
    redirected to a tmp base) -- the lock must still be released and
    `gate.intent` removed on the way out, proven by a fresh acquisition
    succeeding immediately afterward."""
    base = tmp_path / "base"
    base.mkdir()
    monkeypatch.setattr(gate.dsa_testpg, "_base_dir", lambda *a, **k: base)
    monkeypatch.setenv("SP", str(tmp_path / "sp"))

    def failing_cluster():
        raise dsa_testpg.TestPgError("cluster start-up failed (simulated)")

    monkeypatch.setattr(gate.dsa_testpg, "cluster", failing_cluster)

    code = gate.main(["--python", sys.executable, "-C", str(tmp_path)])
    assert code == dl.ERROR
    assert "ERROR" in capsys.readouterr().out
    handle = dsa_testpg._acquire_suite_lock(exclusive=True, wait=1.0, base=base)
    handle.release()
    assert not (base / dsa_testpg.GATE_INTENT_NAME).exists()


def test_gate_run_snapshot_failure_is_error(tmp_path, monkeypatch, capsys):
    """review MINOR-3 (test gap 8): a `dl.DevError` from `run_snapshot`
    (e.g. `psql` failing against the gate's own run cluster) is a real
    precondition failure, not a refusal -- ERROR(78), not REFUSED(75)."""
    monkeypatch.setenv("SP", str(tmp_path / "sp"))
    _patch_gate_cluster_and_lock(monkeypatch)
    monkeypatch.setattr(gate, "shared_snapshot", lambda: (dict(_EMPTY_CATALOGS), ""))

    def failing_run_snapshot(env):
        raise dl.DevError("psql failed: simulated")

    monkeypatch.setattr(gate, "run_snapshot", failing_run_snapshot)
    code = gate.main(["--python", sys.executable, "-C", str(tmp_path)])
    assert code == dl.ERROR
    assert "ERROR" in capsys.readouterr().out


def test_shared_snapshot_never_raises_on_a_failing_read(monkeypatch):
    """review M-2: `shared_snapshot()` ITSELF (not merely a caller working
    around it) catches the psql failure and returns `(None, reason)`
    instead of letting `dl.DevError` propagate -- calls the REAL function
    (only `gate.catalog`, the thing it wraps, is faked), unlike the
    end-to-end test below which fakes `shared_snapshot` itself and so
    cannot see a regression inside its own try/except.

    mutation (`tools/dev/gate.py`): re-raise instead of returning `(None,
    str(exc))` in `shared_snapshot`'s own `except dl.DevError` -- this test
    goes red because `dl.DevError` would then propagate out uncaught."""
    monkeypatch.setattr(gate, "catalog", lambda query, env: (_ for _ in ()).throw(dl.DevError("psql failed: simulated")))
    snap, reason = gate.shared_snapshot()
    assert snap is None
    assert "psql failed: simulated" in reason


def test_gate_shared_snapshot_failure_still_yields_the_normal_pass_output(tmp_path, monkeypatch, capsys):
    """review M-2: a failing shared-cluster read must never abort the gate
    or drop the tally/judge/log -- only degrade the `info=` line."""
    monkeypatch.setenv("SP", str(tmp_path / "sp"))
    _patch_gate_cluster_and_lock(monkeypatch)
    snap = dict(_EMPTY_CATALOGS)
    monkeypatch.setattr(gate, "run_snapshot", lambda env: dict(snap))
    calls = {"n": 0}

    def flaky_shared_snapshot():
        calls["n"] += 1
        if calls["n"] == 1:
            return dict(snap), ""
        return None, "psql failed: simulated"

    monkeypatch.setattr(gate, "shared_snapshot", flaky_shared_snapshot)

    def fake_run_suite(cmd, cwd, env, stdout_path):
        stdout_path.write_text("....\n3 passed in 1.00s\n", encoding="utf-8")
        return 0

    monkeypatch.setattr(gate, "run_suite", fake_run_suite)
    code = gate.main(["--python", sys.executable, "-C", str(tmp_path)])
    out = capsys.readouterr().out.splitlines()
    assert code == 0
    assert out[:2] == ["gate: 3 passed in 1.00s", "gate: judge=PASS"]
    assert out[-1] == "gate: info=shared pg_database/pg_roles diff unavailable (psql failed: simulated)"


# ---------------------------------------------------------------------------
# finalize
# ---------------------------------------------------------------------------

def _repo_with_worktree(tmp_path: Path) -> tuple[Path, Path]:
    main_root = _init_repo(tmp_path / "main", {"docs/a.md": "a\n", "docs/old.md": "old\n", "src/x.py": "x = 1\n"})
    wt = tmp_path / "wt"
    _git(main_root, "worktree", "add", "-q", "-b", "wp", str(wt), "main")
    return main_root, wt


def _msg(tmp_path: Path, text: str) -> Path:
    p = tmp_path / "msg.txt"
    p.write_text(text)
    return p


def _finalize(wt, tmp_path, allow, msg="docs: change [skip ci]\n\nbody\n\nCo-Authored-By: A <a@example.com>\n",
              checks=(), tools_tests=False):
    buf = io.StringIO()
    code = finalize.finalize(wt, "wp", allow, _msg(tmp_path, msg), list(checks), tools_tests,
                             True, sys.executable, out=buf, repo_checks=False)
    return code, buf.getvalue()


def test_finalize_commits_allowed_paths_and_merges(isolated_git, tmp_path):
    main_root, wt = _repo_with_worktree(tmp_path)
    (wt / "docs/a.md").write_text("a2\n")
    (wt / "docs/old.md").unlink()
    (wt / "docs/new dir").mkdir()
    (wt / "docs/new dir/b c.md").write_text("b\n")
    code, text = _finalize(wt, tmp_path, ["docs/*"])
    assert code == 0, text
    subject = _git(main_root, "log", "-1", "--format=%s%n%b")
    assert subject.startswith("Merge wp: docs: change [skip ci]")
    assert "Co-Authored-By: A <a@example.com>" in subject
    assert _git(main_root, "show", "HEAD:docs/new dir/b c.md") == "b\n"
    assert "docs/old.md" not in _git(main_root, "ls-files")
    assert _git(wt, "rev-parse", "HEAD") == _git(main_root, "rev-parse", "HEAD")


def test_finalize_commits_a_staged_rename(isolated_git, tmp_path):
    # The source side of a `git mv` is a deletion that is already staged: it
    # exists neither in the working tree nor in the index, so a plain
    # `git add -- <path>` refuses it. finalize must still commit the rename
    # (docs/archive moves, docs/design/DOC_ARCHIVE_SPLIT_V1.md D-2).
    main_root, wt = _repo_with_worktree(tmp_path)
    (wt / "docs/archive").mkdir()
    _git(wt, "mv", "docs/old.md", "docs/archive/old.md")
    code, text = _finalize(wt, tmp_path, ["docs/*"])
    assert code == 0, text
    assert _git(main_root, "show", "HEAD:docs/archive/old.md") == "old\n"
    assert "docs/old.md" not in _git(main_root, "ls-files")


def test_finalize_splits_commits_with_leave(isolated_git, tmp_path):
    main_root, wt = _repo_with_worktree(tmp_path)
    main_head = _git(main_root, "rev-parse", "HEAD")
    (wt / "docs/a.md").write_text("a2\n")
    (wt / "src/x.py").write_text("x = 2\n")
    (wt / "src/new.py").write_text("y = 1\n")
    buf = io.StringIO()
    code = finalize.finalize(wt, "wp", ["docs/*"], _msg(tmp_path, "docs first\n"), [], False, False,
                             sys.executable, out=buf, repo_checks=False, leave=["src/*"])
    assert code == 0, buf.getvalue()
    assert "left uncommitted by --leave: 2 paths" in buf.getvalue()
    assert _git(wt, "show", "--name-only", "--format=", "HEAD").split() == ["docs/a.md"]
    assert sorted(_git(wt, "status", "--porcelain", "--untracked-files=all").split()) == ["??", "M", "src/new.py", "src/x.py"]
    assert _git(main_root, "rev-parse", "HEAD") == main_head
    code, text = _finalize(wt, tmp_path, ["src/*"], msg="code second\n")
    assert code == 0, text
    assert _git(main_root, "log", "-1", "--format=%s").strip() == "Merge wp: code second"
    assert "docs/a.md" in _git(main_root, "diff", "--name-only", f"{main_head.strip()}..HEAD")


def test_finalize_rejects_path_outside_allowlist(isolated_git, tmp_path):
    _, wt = _repo_with_worktree(tmp_path)
    (wt / "docs/a.md").write_text("a2\n")
    (wt / "src/x.py").write_text("x = 2\n")
    code, text = _finalize(wt, tmp_path, ["docs/*"])
    assert code == 1 and "not allowed: src/x.py" in text
    assert _git(wt, "log", "-1", "--format=%s").strip() == "init"
    assert _git(wt, "diff", "--cached", "--name-only") == ""


def test_finalize_rejects_zero_byte_md(isolated_git, tmp_path):
    _, wt = _repo_with_worktree(tmp_path)
    (wt / "docs/a.md").write_text("")
    code, text = _finalize(wt, tmp_path, ["docs/*"])
    assert code == 1 and "zero-byte .md" in text


def test_finalize_failing_check_commits_nothing(isolated_git, tmp_path):
    _, wt = _repo_with_worktree(tmp_path)
    (wt / "docs/a.md").write_text("a2\n")
    code, text = _finalize(wt, tmp_path, ["docs/*"], checks=["echo checked; exit 1"])
    assert code == 1 and "nothing committed" in text
    assert _git(wt, "log", "-1", "--format=%s").strip() == "init"


def test_finalize_requires_branch_and_noreply_identities(isolated_git, tmp_path, monkeypatch):
    _, wt = _repo_with_worktree(tmp_path)
    (wt / "docs/a.md").write_text("a2\n")
    with pytest.raises(dl.DevError, match="not 'other'"):
        finalize.finalize(wt, "other", ["docs/*"], _msg(tmp_path, "m\n"), [], False, True,
                          sys.executable, out=io.StringIO(), repo_checks=False)
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "someone@example.com")
    with pytest.raises(dl.DevError, match="GIT_COMMITTER_IDENT"):
        _finalize(wt, tmp_path, ["docs/*"])
    monkeypatch.delenv("GIT_COMMITTER_EMAIL")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "someone@example.com")
    with pytest.raises(dl.DevError, match="GIT_AUTHOR_IDENT"):
        _finalize(wt, tmp_path, ["docs/*"])


def test_finalize_refuses_with_mutation_journal(isolated_git, tmp_path):
    _, wt = _repo_with_worktree(tmp_path)
    (wt / "docs/a.md").write_text("a2\n")
    dl.journal_path(wt).write_text("{}")
    with pytest.raises(dl.DevError, match="unfinished mutation run"):
        _finalize(wt, tmp_path, ["docs/*"])


def test_finalize_rechecks_head_before_commit(isolated_git, tmp_path):
    _, wt = _repo_with_worktree(tmp_path)
    (wt / "docs/a.md").write_text("a2\n")
    moved = f"git commit -q --allow-empty -m moved"
    with pytest.raises(dl.DevError, match="moved during the checks"):
        _finalize(wt, tmp_path, ["docs/*"], checks=[moved])
    assert _git(wt, "diff", "--cached", "--name-only") == ""


def test_finalize_post_commit_refusal_is_partial(isolated_git, tmp_path, monkeypatch):
    """WP-2 §3.1 (c): the --tools-tests guard is now journal-only (the
    gate-hold flag it used to also check is gone)."""
    main_root, wt = _repo_with_worktree(tmp_path)
    main_head = _git(main_root, "rev-parse", "HEAD")
    (wt / "docs/a.md").write_text("a2\n")
    monkeypatch.setattr(dl, "journal_blocker", lambda root: "unfinished mutation run: fake")
    code, text = _finalize(wt, tmp_path, ["docs/*"], tools_tests=True)
    assert code == dl.PARTIAL and "tools/tests refused" in text and "merged=no" in text
    assert _git(wt, "log", "-1", "--format=%s").strip() == "docs: change [skip ci]"
    assert _git(main_root, "rev-parse", "HEAD") == main_head


def test_finalize_merge_conflict_is_aborted(isolated_git, tmp_path):
    main_root, wt = _repo_with_worktree(tmp_path)
    (main_root / "docs/a.md").write_text("main side\n")
    _git(main_root, "commit", "-qam", "main moves")
    main_head = _git(main_root, "rev-parse", "HEAD")
    (wt / "docs/a.md").write_text("worktree side\n")
    code, text = _finalize(wt, tmp_path, ["docs/*"])
    assert code == dl.PARTIAL and "merge failed and was aborted" in text and "merged=no" in text
    assert _git(main_root, "rev-parse", "HEAD") == main_head
    assert _git(main_root, "status", "--porcelain") == ""


# ---------------------------------------------------------------------------
# fold
# ---------------------------------------------------------------------------

def _fold_main_repo(tmp_path: Path) -> Path:
    main_root = _init_repo(tmp_path / "main", {"a.txt": "a\n"})
    _git(main_root, "config", "core.logAllRefUpdates", "true")  # deterministic reflog files
    return main_root


def _add_worktree(main_root: Path, tmp_path: Path, branch: str, base: str = "main") -> Path:
    wt = tmp_path / f"wt-{branch.replace('/', '-')}"
    _git(main_root, "worktree", "add", "-q", "-b", branch, str(wt), base)
    return wt


def _age_branch_log(main_root: Path, branch: str, hours: float) -> None:
    past = time.time() - hours * 3600
    common = Path(_git(main_root, "rev-parse", "--path-format=absolute", "--git-common-dir").strip())
    p = common / "logs" / "refs" / "heads" / branch
    if p.exists():
        os.utime(p, (past, past))


def _age_worktree(main_root: Path, wt: Path, branch: str, hours: float) -> None:
    """Backdates the 2 files fold.py's own activity check reads (R1: index
    dropped -- a `git status` read can stamp it with "now"), plus the
    branch's own reflog file: a worktree whose last activity was `hours` ago."""
    past = time.time() - hours * 3600
    git_dir = Path(_git(wt, "rev-parse", "--path-format=absolute", "--git-dir").strip())
    for rel in fold.ACTIVITY_FILES:
        p = git_dir / rel
        if p.exists():
            os.utime(p, (past, past))
    _age_branch_log(main_root, branch, hours)


def _worktrees(main_root: Path) -> str:
    return _git(main_root, "worktree", "list", "--porcelain")


def _branch_exists(main_root: Path, branch: str) -> bool:
    return _git(main_root, "branch", "--list", branch).strip() != ""


def _isolate_fold_lock(monkeypatch, tmp_path) -> Path:
    """Redirects `dsa_testpg`'s own per-uid lock base dir to a private tmp
    one (same idiom as gate.py's tests: `monkeypatch.setattr(gate.dsa_testpg,
    "_base_dir", ...)`) -- `fold.dsa_testpg` IS the same module object gate.py
    imports, so leaving this unpatched would make every --apply fold test
    take the REAL machine-wide suite lock, possibly contending with a
    concurrent gate.py/pytest run in another chat."""
    base = tmp_path / "lock-base"
    base.mkdir(exist_ok=True)
    monkeypatch.setattr(fold.dsa_testpg, "_base_dir", lambda *a, **k: base)
    return base


def _fold(root: Path, apply=False, includes=(), min_age_hours=24.0, main_branch="main", verbose=False, wait=0.0):
    buf = io.StringIO()
    code = fold.fold(root, apply, list(includes), min_age_hours, main_branch, out=buf, verbose=verbose, wait=wait)
    return code, buf.getvalue()


def test_fold_dry_run_changes_nothing(isolated_git, tmp_path):
    """mutation (`tools/dev/fold.py`): change the worktree loop's own `elif
    apply:` to `elif True:` -- this test goes red because a dry-run call
    would then actually remove a FOLD-eligible worktree/branch."""
    main_root = _fold_main_repo(tmp_path)
    wt = _add_worktree(main_root, tmp_path, "merged-clean")
    _age_worktree(main_root, wt, "merged-clean", 48)
    code, text = _fold(main_root, apply=False)
    assert code == 0, text
    assert f"fold: FOLD worktree {wt}" in text
    assert "fold: dry-run worktrees=1 branches=0 prunable=0" in text
    assert str(wt) in _worktrees(main_root)
    assert _branch_exists(main_root, "merged-clean")


def test_fold_dry_run_does_not_touch_worktree_index_mtime(isolated_git, tmp_path):
    """R1: `is_clean`/`worktree_status` reads with `--no-optional-locks` so a
    plain dry-run read never stamps the worktree's own index file with
    "now" (a real `git status` without it can do exactly that)."""
    main_root = _fold_main_repo(tmp_path)
    wt = _add_worktree(main_root, tmp_path, "index-probe")
    git_dir = Path(_git(wt, "rev-parse", "--path-format=absolute", "--git-dir").strip())
    index = git_dir / "index"
    assert index.exists()
    before = index.stat().st_mtime
    _fold(main_root, apply=False)
    assert index.stat().st_mtime == before


def test_fold_apply_removes_merged_clean_worktree_and_branch(isolated_git, tmp_path, monkeypatch):
    main_root = _fold_main_repo(tmp_path)
    wt = _add_worktree(main_root, tmp_path, "merged-clean")
    _age_worktree(main_root, wt, "merged-clean", 48)
    _isolate_fold_lock(monkeypatch, tmp_path)
    code, text = _fold(main_root, apply=True)
    assert code == 0, text
    assert f"fold: FOLD worktree {wt}" in text
    assert "fold: applied worktrees=1 branches=0 prunable=0" in text
    assert str(wt) not in _worktrees(main_root)
    assert not wt.exists()
    assert not _branch_exists(main_root, "merged-clean")


def test_fold_unmerged_worktree_stays(isolated_git, tmp_path, monkeypatch):
    """mutation (`tools/dev/fold.py`): drop the ancestor-of-main check in
    `decide_worktree` -- this test goes red because an unmerged worktree
    would then be removed under --apply."""
    main_root = _fold_main_repo(tmp_path)
    wt = _add_worktree(main_root, tmp_path, "unmerged")
    (wt / "b.txt").write_text("b\n")
    _git(wt, "add", "b.txt")
    _git(wt, "commit", "-q", "-m", "diverge")
    _age_worktree(main_root, wt, "unmerged", 48)
    _isolate_fold_lock(monkeypatch, tmp_path)
    code, text = _fold(main_root, apply=True)
    assert code == 0, text
    assert "unmerged" in text
    assert str(wt) in _worktrees(main_root)
    assert _branch_exists(main_root, "unmerged")


def test_fold_dirty_worktree_stays(isolated_git, tmp_path, monkeypatch):
    """mutation (`tools/dev/fold.py`): drop the `dirty` branch of
    `worktree_status`'s result in `decide_worktree` -- this test goes red
    because a worktree with an untracked file would then be removed."""
    main_root = _fold_main_repo(tmp_path)
    wt = _add_worktree(main_root, tmp_path, "dirty-one")
    (wt / "untracked.txt").write_text("x\n")
    _age_worktree(main_root, wt, "dirty-one", 48)
    _isolate_fold_lock(monkeypatch, tmp_path)
    code, text = _fold(main_root, apply=True)
    assert code == 0, text
    assert "dirty" in text
    assert str(wt) in _worktrees(main_root)
    assert _branch_exists(main_root, "dirty-one")


def test_fold_ignored_files_worktree_stays(isolated_git, tmp_path, monkeypatch):
    """R2: an ignored file whose own basename is not a known build artifact
    (here `.env`) must never be silently thrown away with the worktree."""
    main_root = _fold_main_repo(tmp_path)
    # .gitignore committed on main FIRST, so the new branch's tip stays
    # exactly main's tip (still trivially an ancestor) -- only the later,
    # untracked+ignored `.env` file is worktree-specific.
    (main_root / ".gitignore").write_text(".env\n")
    _git(main_root, "add", ".gitignore")
    _git(main_root, "commit", "-q", "-m", "ignore env")
    wt = _add_worktree(main_root, tmp_path, "ignored-bad")
    (wt / ".env").write_text("SECRET=x\n")
    _age_worktree(main_root, wt, "ignored-bad", 48)
    _isolate_fold_lock(monkeypatch, tmp_path)
    code, text = _fold(main_root, apply=True)
    assert code == 0, text
    assert "ignored-files" in text
    assert str(wt) in _worktrees(main_root)
    assert _branch_exists(main_root, "ignored-bad")


def test_fold_allowed_ignored_pycache_folds(isolated_git, tmp_path, monkeypatch):
    """R2: `__pycache__/*.pyc` is a known, tolerated build artifact -- its
    presence alone must not block an otherwise-eligible fold.

    mutation (`tools/dev/fold.py`): drop the `_is_allowed_ignored` allowance
    (treat every ignored path as disallowed) -- this test goes red because
    the worktree would then stay SKIP `ignored-files` instead of folding."""
    main_root = _fold_main_repo(tmp_path)
    (main_root / ".gitignore").write_text("__pycache__/\n")
    _git(main_root, "add", ".gitignore")
    _git(main_root, "commit", "-q", "-m", "ignore pycache")
    wt = _add_worktree(main_root, tmp_path, "ignored-ok")
    (wt / "__pycache__").mkdir()
    (wt / "__pycache__" / "x.pyc").write_text("x")
    _age_worktree(main_root, wt, "ignored-ok", 48)
    _isolate_fold_lock(monkeypatch, tmp_path)
    code, text = _fold(main_root, apply=True)
    assert code == 0, text
    assert f"fold: FOLD worktree {wt}" in text
    assert str(wt) not in _worktrees(main_root)


def test_fold_local_settings_copy_tolerated_only_under_dot_claude(isolated_git, tmp_path, monkeypatch):
    """The per-worktree `.claude/settings.local.json` copy, `.ruff_cache/` and
    `*.egg-info/` do not block a fold; a `settings.local.json` anywhere else
    is an unknown ignored file and does."""
    main_root = _fold_main_repo(tmp_path)
    (main_root / ".gitignore").write_text("settings.local.json\n.ruff_cache/\n*.egg-info/\n")
    _git(main_root, "add", ".gitignore")
    _git(main_root, "commit", "-q", "-m", "ignore local settings and caches")
    ok = _add_worktree(main_root, tmp_path, "settings-ok")
    (ok / ".claude").mkdir()
    (ok / ".claude" / "settings.local.json").write_text("{}")
    (ok / ".ruff_cache").mkdir()
    (ok / ".ruff_cache" / "x").write_text("x")
    (ok / "pkg.egg-info").mkdir()
    (ok / "pkg.egg-info" / "PKG-INFO").write_text("x")
    bad = _add_worktree(main_root, tmp_path, "settings-bad")
    (bad / "conf").mkdir()
    (bad / "conf" / "settings.local.json").write_text("{}")
    _age_worktree(main_root, ok, "settings-ok", 48)
    _age_worktree(main_root, bad, "settings-bad", 48)
    _isolate_fold_lock(monkeypatch, tmp_path)
    code, text = _fold(main_root, apply=True)
    assert code == 0, text
    assert str(ok) not in _worktrees(main_root)
    assert str(bad) in _worktrees(main_root)
    assert "ignored-files=1" in text


def test_fold_recent_worktree_stays(isolated_git, tmp_path, monkeypatch):
    """mutation (`tools/dev/fold.py`): drop the `is_recent` check in
    `decide_worktree` -- this test goes red because a just-created worktree
    (default --min-age-hours=24, not backdated) would then be removed."""
    main_root = _fold_main_repo(tmp_path)
    wt = _add_worktree(main_root, tmp_path, "fresh-one")
    _isolate_fold_lock(monkeypatch, tmp_path)
    code, text = _fold(main_root, apply=True)  # default min_age_hours=24, never backdated
    assert code == 0, text
    assert "recent" in text
    assert str(wt) in _worktrees(main_root)
    assert _branch_exists(main_root, "fresh-one")


def test_fold_claude_worktree_excluded_by_default_then_included(isolated_git, tmp_path, monkeypatch):
    """mutation (`tools/dev/fold.py`): empty `DEFAULT_EXCLUDES` -- this test
    goes red because the first, --include-less call would then also fold
    `claude/x`."""
    main_root = _fold_main_repo(tmp_path)
    wt = _add_worktree(main_root, tmp_path, "claude/x")
    _age_worktree(main_root, wt, "claude/x", 48)
    _isolate_fold_lock(monkeypatch, tmp_path)
    code, text = _fold(main_root, apply=True)
    assert code == 0, text
    assert "excluded" in text
    assert str(wt) in _worktrees(main_root)
    code, text = _fold(main_root, apply=True, includes=["claude/*"])
    assert code == 0, text
    assert str(wt) not in _worktrees(main_root)
    assert not _branch_exists(main_root, "claude/x")


def test_fold_current_worktree_stays(isolated_git, tmp_path, monkeypatch):
    """mutation (`tools/dev/fold.py`): drop the `current_path` check in
    `decide_worktree` -- this test goes red because the worktree `-C`
    itself points into would then be removed under --apply."""
    main_root = _fold_main_repo(tmp_path)
    wt = _add_worktree(main_root, tmp_path, "current-one")
    _age_worktree(main_root, wt, "current-one", 48)
    _isolate_fold_lock(monkeypatch, tmp_path)
    code, text = _fold(wt, apply=True)  # -C points at the worktree itself
    assert code == 0, text
    assert "current" in text
    assert str(wt) in _worktrees(main_root)
    assert _branch_exists(main_root, "current-one")


def test_fold_main_checkout_never_folds(isolated_git, tmp_path, monkeypatch):
    """mutation (`tools/dev/fold.py`): drop the `main_path` check in
    `decide_worktree` -- this test goes red because the main checkout's own
    worktree entry would then no longer be SKIPped `main-checkout`."""
    main_root = _fold_main_repo(tmp_path)
    _isolate_fold_lock(monkeypatch, tmp_path)
    code, text = _fold(main_root, apply=True)
    assert code == 0, text
    assert "main-checkout=1" in text
    assert str(main_root) in _worktrees(main_root)


def test_fold_detached_worktree_stays(isolated_git, tmp_path, monkeypatch):
    """mutation (`tools/dev/fold.py`): drop the `detached` check in
    `decide_worktree` -- this test goes red because a detached worktree
    would then be removed (`entry["branch"]` is None for it, so the removal
    step itself would also need a branch it does not have)."""
    main_root = _fold_main_repo(tmp_path)
    wt = tmp_path / "wt-detached"
    head = _git(main_root, "rev-parse", "main").strip()
    _git(main_root, "worktree", "add", "-q", "--detach", str(wt), head)
    _isolate_fold_lock(monkeypatch, tmp_path)
    code, text = _fold(main_root, apply=True)
    assert code == 0, text
    assert "detached" in text
    assert str(wt) in _worktrees(main_root)


def test_fold_worktreeless_merged_branch_removed_unmerged_stays(isolated_git, tmp_path, monkeypatch):
    main_root = _fold_main_repo(tmp_path)
    _git(main_root, "branch", "old-merged", "main")
    _age_branch_log(main_root, "old-merged", 48)
    wt = _add_worktree(main_root, tmp_path, "diverge-src")
    (wt / "c.txt").write_text("c\n")
    _git(wt, "add", "c.txt")
    _git(wt, "commit", "-q", "-m", "diverge")
    _git(main_root, "branch", "old-unmerged", "diverge-src")
    _age_branch_log(main_root, "old-unmerged", 48)
    _isolate_fold_lock(monkeypatch, tmp_path)
    code, text = _fold(main_root, apply=True)
    assert code == 0, text
    assert "fold: FOLD branch old-merged" in text
    assert not _branch_exists(main_root, "old-merged")
    assert _branch_exists(main_root, "old-unmerged")
    assert "fold: applied worktrees=0 branches=1" in text


def test_fold_branchless_dry_run_reports_without_deleting(isolated_git, tmp_path):
    """mutation (`tools/dev/fold.py`): change the branch loop's own `elif
    apply:` to `elif True:` -- this test goes red because a dry-run call
    would then actually delete a FOLD-eligible worktree-less branch."""
    main_root = _fold_main_repo(tmp_path)
    _git(main_root, "branch", "old-merged-dry", "main")
    _age_branch_log(main_root, "old-merged-dry", 48)
    code, text = _fold(main_root, apply=False)
    assert code == 0, text
    assert "fold: FOLD branch old-merged-dry" in text
    assert "fold: dry-run worktrees=0 branches=1" in text
    assert _branch_exists(main_root, "old-merged-dry")


def test_fold_branchless_no_reflog_falls_back_to_committer_date_and_stays_recent(isolated_git, tmp_path):
    """R5: a branch with no reflog file at all must fall back to its own
    tip commit's committer date, not be treated as infinitely old.

    mutation (`tools/dev/fold.py`): change `decide_branchless`'s `if mtime
    is None: mtime = committer_date(...)` fallback back to leaving `mtime`
    as `None` (the pre-R5 "missing counts as old" rule) -- this test goes
    red because the branch (committed moments ago) would then be folded
    instead of staying SKIP `recent`."""
    main_root = _fold_main_repo(tmp_path)
    _git(main_root, "config", "core.logAllRefUpdates", "false")
    _git(main_root, "branch", "no-reflog", "main")
    common = Path(_git(main_root, "rev-parse", "--path-format=absolute", "--git-common-dir").strip())
    reflog = common / "logs" / "refs" / "heads" / "no-reflog"
    assert not reflog.exists()
    code, text = _fold(main_root, apply=False)  # main's tip is fresh -> committer date is "now"
    assert code == 0, text
    assert "recent" in text
    assert _branch_exists(main_root, "no-reflog")


def test_fold_branch_delete_reconfirms_ancestry_just_before_delete(isolated_git, tmp_path, monkeypatch):
    """R6/apply_branch_delete's own re-check: a branch `decide_branchless`
    already judged FOLD (patched out below, standing in for a race where it
    was merged at enumeration time) but that has since moved to a commit no
    longer an ancestor of main must FAIL, not be deleted.

    mutation (`tools/dev/fold.py`): drop `apply_branch_delete`'s own
    `is_ancestor` re-check (delete unconditionally) -- this test goes red
    because the branch would then actually be deleted instead of FAILing."""
    main_root = _fold_main_repo(tmp_path)
    _git(main_root, "branch", "moved", "main")
    _age_branch_log(main_root, "moved", 48)
    src = _add_worktree(main_root, tmp_path, "moved-src", base="moved")
    (src / "d.txt").write_text("d\n")
    _git(src, "add", "d.txt")
    _git(src, "commit", "-q", "-m", "advance past main")
    _git(main_root, "branch", "-f", "moved", "moved-src")
    monkeypatch.setattr(fold, "decide_branchless", lambda *a, **k: ("FOLD", ""))
    _isolate_fold_lock(monkeypatch, tmp_path)
    code, text = _fold(main_root, apply=True)
    assert code == 1
    assert "fold: FAIL branch moved" in text
    assert _branch_exists(main_root, "moved")


def test_fold_mutation_journal_worktree_stays(isolated_git, tmp_path, monkeypatch):
    """mutation (`tools/dev/fold.py`): drop the `journal_blocker` check in
    `decide_worktree` -- this test goes red because a worktree with an
    unfinished mutate.py run would then be removed under --apply."""
    main_root = _fold_main_repo(tmp_path)
    wt = _add_worktree(main_root, tmp_path, "journal-one")
    _age_worktree(main_root, wt, "journal-one", 48)
    dl.journal_path(wt).write_text("{}")
    _isolate_fold_lock(monkeypatch, tmp_path)
    code, text = _fold(main_root, apply=True)
    assert code == 0, text
    assert "mutation-journal" in text
    assert str(wt) in _worktrees(main_root)
    assert _branch_exists(main_root, "journal-one")


def test_fold_locked_worktree_stays(isolated_git, tmp_path, monkeypatch):
    main_root = _fold_main_repo(tmp_path)
    wt = _add_worktree(main_root, tmp_path, "locked-one")
    _age_worktree(main_root, wt, "locked-one", 48)
    _git(main_root, "worktree", "lock", str(wt))
    _isolate_fold_lock(monkeypatch, tmp_path)
    code, text = _fold(main_root, apply=True)
    assert code == 0, text
    assert "locked" in text
    assert str(wt) in _worktrees(main_root)
    assert _branch_exists(main_root, "locked-one")


def test_fold_prunable_worktree_is_reported_and_not_pruned(isolated_git, tmp_path, monkeypatch):
    """R4: a `prunable` worktree (its directory is gone) is only reported --
    never actually pruned (a synced drive can make a directory vanish and
    reappear, so this tool never runs `git worktree prune` itself)."""
    main_root = _fold_main_repo(tmp_path)
    wt = _add_worktree(main_root, tmp_path, "gone-one")
    shutil.rmtree(wt)
    _isolate_fold_lock(monkeypatch, tmp_path)
    code, text = _fold(main_root, apply=True)
    assert code == 0, text
    assert f"fold: PRUNABLE worktree {wt}" in text
    assert "prunable=1" in text
    assert str(wt) in _worktrees(main_root)


def test_fold_refuses_when_the_exclusive_lock_times_out(isolated_git, tmp_path, monkeypatch):
    """R3: --apply runs inside the exclusive suite lock; when it cannot be
    taken within --wait, fold REFUSES (75) and changes nothing.

    mutation (`tools/dev/fold.py`): drop the `dsa_testpg.suite_lock(...)`
    wrapper around `_run` under --apply (call `_run` unconditionally) --
    this test goes red because the fold would then proceed and remove the
    worktree/branch instead of REFUSING."""
    main_root = _fold_main_repo(tmp_path)
    wt = _add_worktree(main_root, tmp_path, "locked-out")
    _age_worktree(main_root, wt, "locked-out", 48)
    base = _isolate_fold_lock(monkeypatch, tmp_path)
    held = dsa_testpg._acquire_suite_lock(exclusive=False, wait=1.0, base=base)  # a live "other pytest run"
    try:
        code, text = _fold(main_root, apply=True, wait=0.3)
    finally:
        held.release()
    assert code == dl.REFUSED
    assert "fold: REFUSED --" in text
    assert str(wt) in _worktrees(main_root)
    assert _branch_exists(main_root, "locked-out")


# ---------------------------------------------------------------------------
# turn_budget_hook
# ---------------------------------------------------------------------------

hook = _load("turn_budget_hook")
ready = _load("handover_ready")


def _rec(mid, blocks=None):
    return json.dumps({"type": "assistant", "message": {"id": mid, "content": blocks or [{"type": "text", "text": "x"}]}})


class _Hook:
    def __init__(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TURN_BUDGET_STATE_DIR", str(tmp_path / "state"))
        self.root = tmp_path / "root"
        (self.root / ".claude/worktrees/wt").mkdir(parents=True)
        self.transcript = tmp_path / "sess-1.jsonl"
        self.transcript.write_text("")

    def append(self, *lines, raw=""):
        with open(self.transcript, "a") as fh:
            fh.write("".join(l + "\n" for l in lines) + raw)

    def fire(self, threshold=3, every=2, **payload):
        body = {"session_id": "sess-1", "transcript_path": str(self.transcript), "cwd": str(self.root), **payload}
        out = io.StringIO()
        assert hook.main(["--project-root", str(self.root), "--threshold", str(threshold), "--every", str(every)],
                         stdin=io.StringIO(json.dumps(body)), out=out) == 0
        return json.loads(out.getvalue())["hookSpecificOutput"]["additionalContext"] if out.getvalue() else None


def test_hook_counts_unique_calls_and_notifies_at_threshold_then_every(tmp_path, monkeypatch):
    h = _Hook(tmp_path, monkeypatch)
    h.append(_rec("m1"), _rec("m1", [{"type": "tool_use", "name": "Bash", "input": {}}]),
             json.dumps({"type": "user", "message": {"content": "r"}}), _rec("m2"))
    assert h.fire() is None
    h.append(_rec("m3"))
    first = h.fire()
    assert first is not None and "3 回" in first and "handover_ready.py" in first
    assert h.fire() is None
    h.append(_rec("m4"))
    assert h.fire() is None
    h.append(_rec("m5"))
    assert "5 回" in h.fire()


def test_hook_waits_for_a_complete_line(tmp_path, monkeypatch):
    h = _Hook(tmp_path, monkeypatch)
    h.append(_rec("m1"), _rec("m2"), raw=_rec("m3")[:20])
    assert h.fire() is None
    h.append(raw=_rec("m3")[20:] + "\n")
    assert h.fire() is not None


def test_hook_stops_after_the_handover_chip(tmp_path, monkeypatch):
    h = _Hook(tmp_path, monkeypatch)
    plain = {"type": "tool_use", "name": "mcp__ccd_session__spawn_task", "input": {"prompt": "fix a typo"}}
    chip = {"type": "tool_use", "name": "mcp__ccd_session__spawn_task", "input": {"prompt": hook.HANDOVER_MARKER + "\n..."}}
    h.append(_rec("m1"), _rec("m2"), _rec("m3", [plain]))
    assert h.fire() is not None
    h.append(_rec("m4", [chip]), _rec("m5"), _rec("m6"), _rec("m7"))
    assert h.fire() is None


def test_hook_scope_worktree_yes_outside_or_subagent_no(tmp_path, monkeypatch):
    h = _Hook(tmp_path, monkeypatch)
    h.append(_rec("m1"), _rec("m2"), _rec("m3"))
    assert h.fire(cwd=str(tmp_path)) is None
    assert h.fire(agent_id="a1") is None
    assert h.fire(session_id="other") is None
    assert not (tmp_path / "state").exists()
    assert h.fire(cwd=str(h.root / ".claude/worktrees/wt")) is not None


def test_hook_never_fails_the_session(tmp_path):
    out = io.StringIO()
    assert hook.main(["--project-root", str(tmp_path)], stdin=io.StringIO("not json"), out=out) == 0
    assert hook.main([], stdin=io.StringIO("{}"), out=out) == 0
    assert out.getvalue() == ""


# ---------------------------------------------------------------------------
# handover_ready
# ---------------------------------------------------------------------------

def _ready_repo(tmp_path, monkeypatch):
    # WP-2 §3.1 (c): "no pytest process" + "gate-hold flag absent" collapse
    # into dsa_testpg.gate_running() -- faked here (never the real, machine-
    # shared per-uid base dir) so every handover_ready test stays hermetic.
    monkeypatch.setattr(dsa_testpg, "gate_running", lambda *a, **k: (False, ""))
    main_root, wt = _repo_with_worktree(tmp_path)
    (main_root / "docs/HANDOVER_X.md").write_text("next: WP-9\n")
    _git(main_root, "add", "docs/HANDOVER_X.md")
    _git(main_root, "commit", "-qm", "handover")
    return main_root, wt


def test_handover_ready_prints_continuation_prompt(isolated_git, tmp_path, monkeypatch):
    main_root, wt = _ready_repo(tmp_path, monkeypatch)
    buf = io.StringIO()
    code = ready.check(wt, True, [str(wt)], "docs/HANDOVER_X.md", out=buf)
    text = buf.getvalue()
    assert code == 0, text
    assert "READY" in text and "NOT READY" not in text
    prompt = text.split("----- BEGIN CONTINUATION PROMPT -----\n")[1].split("\n----- END")[0]
    assert prompt.startswith(hook.HANDOVER_MARKER) and ready.HANDOVER_MARKER == hook.HANDOVER_MARKER
    assert f"{main_root}/docs/HANDOVER_X.md" in prompt


def test_handover_not_ready_while_gate_runs(isolated_git, tmp_path, monkeypatch):
    """WP-2 §3.1 manifest row 9, named exactly as the manifest specifies
    (review MINOR-6: previously only the `gate_running` case of the
    parametrized `test_handover_ready_not_ready` below -- pulled out into
    its own function so the name matches)."""
    main_root, wt = _ready_repo(tmp_path, monkeypatch)
    monkeypatch.setattr(dsa_testpg, "gate_running", lambda *a, **k: (True, "gate intent present: /x/gate.intent"))
    buf = io.StringIO()
    assert ready.check(wt, True, [str(wt)], "docs/HANDOVER_X.md", out=buf) == 1
    text = buf.getvalue()
    assert "NG  gate not running" in text and "NOT READY" in text and "BEGIN CONTINUATION" not in text


@pytest.mark.parametrize("case,needle", [
    ("agents", "NG  no running subagents"),
    ("main_dirty", "NG  main checkout on main and clean"),
    ("journal", "NG  no unfinished mutation journal"),
    ("wt_dirty", "clean=False"),
    ("wt_unmerged", "merged=False"),
    ("handover_missing", "NG  handover committed on main"),
])
def test_handover_ready_not_ready(isolated_git, tmp_path, monkeypatch, case, needle):
    main_root, wt = _ready_repo(tmp_path, monkeypatch)
    denied, handover = True, "docs/HANDOVER_X.md"
    if case == "agents":
        denied = False
    elif case == "main_dirty":
        (main_root / "stray.txt").write_text("x")
    elif case == "journal":
        dl.journal_path(wt).write_text("{}")
    elif case == "wt_dirty":
        (wt / "stray.txt").write_text("x")
    elif case == "wt_unmerged":
        _git(wt, "commit", "-q", "--allow-empty", "-m", "unmerged")
    elif case == "handover_missing":
        handover = "docs/NOPE.md"
    buf = io.StringIO()
    assert ready.check(wt, denied, [str(wt)], handover, out=buf) == 1
    text = buf.getvalue()
    assert needle in text and "NOT READY" in text and "BEGIN CONTINUATION" not in text
