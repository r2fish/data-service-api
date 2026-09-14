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

import importlib
import importlib.util
import io
import json
import os
import signal
import subprocess
import sys
from pathlib import Path

import pytest

_DEV = Path(__file__).resolve().parents[1] / "dev"
sys.path.insert(0, str(_DEV))


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"dev_{name}", _DEV / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


dl = importlib.import_module("_devlib")  # the same module object the scripts import
pt = _load("pt")
mutate = _load("mutate")
section = _load("section")
gate = _load("gate")
finalize = _load("finalize")


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

PS_TEXT = """\
    1     0 /sbin/launchd
  100     1 /bin/zsh -c cd wt && python -m pytest -q tools/tests
  101   100 /x/.venv/bin/python -m pytest -q tools/tests
  102   101 /x/.venv/bin/python tools/dev/pt.py -- -q
  103   102 /x/.venv/bin/python -m pytest -q sub
  200     1 /x/.venv/bin/python -m pytest -q -n 5 --dist loadgroup
  201   200 /x/.venv/bin/python -c import sys;exec(eval(sys.stdin.readline()))
  300     1 grep pytest
  301     1 /bin/bash -c while ps -eo args= | grep -q '[-]m pytest'; do sleep 5; done
  400     1 /opt/homebrew/Cellar/python/Frameworks/Python.framework/Resources/Python.app/Contents/MacOS/Python -m pytest tools/tests
  500     1 /x/.venv/bin/pytest -q
  600     1 /x/.venv/bin/python -m uvicorn app:api --port 8000
"""


def test_other_pytest_counts_python_pytest_only_and_skips_own_chain():
    hits = [pid for pid, _ in dl.other_pytest(PS_TEXT, 102)]
    assert hits == [200, 400, 500]


def test_other_pytest_sees_another_process_chain():
    assert [pid for pid, _ in dl.other_pytest(PS_TEXT, 600)] == [101, 103, 200, 400, 500]


def test_current_other_pytest_reads_the_real_process_list():
    assert all(pid != os.getpid() for pid, _ in dl.current_other_pytest())


def test_current_other_pytest_refuses_incomplete_list(monkeypatch):
    fake = subprocess.CompletedProcess([], 0, stdout=b"  200   150 /x/python -m pytest\n", stderr=b"")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: fake)
    with pytest.raises(dl.DevError, match="incomplete"):
        dl.current_other_pytest()


def test_hold_flag_resolution_order(monkeypatch, tmp_path):
    monkeypatch.setenv("SP", str(tmp_path))
    monkeypatch.setenv("GATE_HOLD_FLAG", str(tmp_path / "env.flag"))
    assert dl.hold_flag("/x/explicit.flag") == Path("/x/explicit.flag")
    assert dl.hold_flag(None) == tmp_path / "env.flag"
    monkeypatch.delenv("GATE_HOLD_FLAG")
    assert dl.hold_flag(None) == tmp_path / "gate-hold.flag"
    assert dl.hold_flag("-") is None


def test_hold_flag_unknown_location_refuses(monkeypatch):
    monkeypatch.delenv("SP", raising=False)
    monkeypatch.delenv("GATE_HOLD_FLAG", raising=False)
    with pytest.raises(dl.DevError):
        dl.hold_flag(None)


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


# ---------------------------------------------------------------------------
# pt
# ---------------------------------------------------------------------------

def test_pt_refuses_when_hold_flag_present(isolated_git, tmp_path):
    proj = _calc_project(tmp_path)
    flag = tmp_path / "gate-hold.flag"
    flag.touch()
    buf = io.StringIO()
    assert pt.guarded_run(proj, sys.executable, ["-q"], flag, 0, 5, out=buf) == dl.REFUSED
    assert "gate hold flag present" in buf.getvalue()


def test_pt_refuses_while_mutation_journal_exists(isolated_git, tmp_path):
    proj = _calc_project(tmp_path)
    dl.journal_path(proj).write_text("{}")
    buf = io.StringIO()
    assert pt.guarded_run(proj, sys.executable, ["-q"], None, 0, 5, out=buf) == dl.REFUSED
    assert "unfinished mutation run" in buf.getvalue()


def test_pt_reports_tally_failures_and_exit(isolated_git, tmp_path):
    proj = _calc_project(tmp_path)
    (proj / "test_calc.py").write_text(_TEST_CALC + "\n\ndef test_bad():\n    assert add(1, 1) == 3\n")
    buf = io.StringIO()
    code = pt.guarded_run(proj, sys.executable, ["-q"], None, 0, 5, out=buf, guard=False)
    text = buf.getvalue()
    assert code == 1
    assert "pt: 1 failed, 1 passed" in text
    assert "FAILED test_calc.py::test_bad" in text
    assert "pt: exit=1 log=" in text


# ---------------------------------------------------------------------------
# mutate
# ---------------------------------------------------------------------------

def _mutate(proj: Path, spec: dict, tmp_path: Path) -> tuple[int, str]:
    buf = io.StringIO()
    code = mutate.run(spec, proj, sys.executable, None, out=buf, guard=False, settle=0, work=tmp_path / "work")
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
    proj = _calc_project(tmp_path)
    spec = {"pytest": ["-q"], "mutations": [
        {"id": "M1", "file": "calc.py", "old": "return a + b", "new": "return 0  # MUT", "expect": "red"}]}
    calls = {"n": 0}

    def wait_then_interrupt(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 2:  # 1 = before backups, 2 = before the first edit
            assert dl.journal_path(proj).exists()
            raise KeyboardInterrupt
        return []

    monkeypatch.setattr(dl, "wait_clear", wait_then_interrupt)
    with pytest.raises(KeyboardInterrupt):
        mutate.run(spec, proj, sys.executable, None, out=io.StringIO(), settle=0, work=tmp_path / "work")
    assert _pristine(proj) and not dl.journal_path(proj).exists()


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


def test_gate_rejects_hold_dash():
    assert gate.main(["--hold", "-", "--python", sys.executable]) == dl.ERROR


def test_gate_refuses_existing_flag_and_leaves_it(tmp_path, capsys):
    flag = tmp_path / "gate-hold.flag"
    flag.touch()
    assert gate.main(["--hold", str(flag), "--python", sys.executable, "-C", str(tmp_path)]) == dl.REFUSED
    assert flag.exists() and "already exists" in capsys.readouterr().out


def test_gate_removes_only_its_own_flag_on_error(tmp_path, monkeypatch):
    flag = tmp_path / "gate-hold.flag"
    monkeypatch.setattr(dl, "wait_clear", lambda *a, **k: [])
    monkeypatch.setattr(gate, "snapshot", lambda: (_ for _ in ()).throw(dl.DevError("psql failed")))
    assert gate.main(["--hold", str(flag), "--python", sys.executable, "-C", str(tmp_path)]) == dl.ERROR
    assert not flag.exists()


def test_gate_run_watched_reports_concurrent_pytest(tmp_path, monkeypatch):
    monkeypatch.setattr(dl, "current_other_pytest", lambda: [(4242, "python -m pytest")])
    code, seen = gate.run_watched([sys.executable, "-c", "import time; time.sleep(0.5)"], tmp_path,
                                  tmp_path / "out.log", poll=0.05)
    assert code == 0 and seen == ["concurrent pytest pid=4242"]


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
              checks=(), tools_tests=False, flag=None):
    buf = io.StringIO()
    code = finalize.finalize(wt, "wp", allow, _msg(tmp_path, msg), list(checks), tools_tests, flag,
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


def test_finalize_splits_commits_with_leave(isolated_git, tmp_path):
    main_root, wt = _repo_with_worktree(tmp_path)
    main_head = _git(main_root, "rev-parse", "HEAD")
    (wt / "docs/a.md").write_text("a2\n")
    (wt / "src/x.py").write_text("x = 2\n")
    (wt / "src/new.py").write_text("y = 1\n")
    buf = io.StringIO()
    code = finalize.finalize(wt, "wp", ["docs/*"], _msg(tmp_path, "docs first\n"), [], False, None, False,
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
        finalize.finalize(wt, "other", ["docs/*"], _msg(tmp_path, "m\n"), [], False, None, True,
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


def test_finalize_post_commit_refusal_is_partial(isolated_git, tmp_path):
    main_root, wt = _repo_with_worktree(tmp_path)
    main_head = _git(main_root, "rev-parse", "HEAD")
    (wt / "docs/a.md").write_text("a2\n")
    flag = tmp_path / "gate-hold.flag"
    flag.touch()
    code, text = _finalize(wt, tmp_path, ["docs/*"], tools_tests=True, flag=flag)
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
