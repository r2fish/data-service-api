"""cs9_cli_red.py -- change set 9: CLI red signals as pytest (work order §18.3).

tools/dev/mutate.py runs `python -m pytest` with cwd = the worktree, so each
condition whose red signal is a non-zero exit of a CLI checker is wrapped here.
  * CLI exit 0                         -> test passes  (green: not triggered)
  * CLI exit 1 + the expected prefix   -> test fails   (red: the named check fired)
  * anything else (exit 1 without the prefix, other exit codes)
                                       -> pytest exit 3 (mutate.py: got=error(3), NG)
Node ids: "$SP/cs9_cli_red.py::test_cli_red[c16]" etc.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

BASE = "092e1a1"
MODULES = [
    "r2db-api/src/r2db_api/structured.py",
    "MitateDB-api/src/mitatedb_api/platform_declarations.py",
]
P = ["tools/check_comment_provenance.py", "--base", BASE, *MODULES]
R = ["tools/check_comment_provenance.py", "--register"]
D = ["tools/check_doc_refs.py"]

# case id -> (command, expected line prefix of the red signal)
CASES = {
    "c1": (P, "FAIL (§4.1 (1))"),
    "c2": (P, "FAIL (§4.1 (2))"),
    "c3a": (P, "FAIL (§4.1 (3))"),
    "c3b": (P, "FAIL (§4.1 (3))"),
    "c3c": (P, "FAIL (§4.1 (3))"),
    "c3d": (P, "FAIL (§4.1 (3))"),
    "c4": (P, "FAIL (§4.1 (3))"),   # the checker reports (4) violations under (3)
    "c5": (P, "FAIL (§4.1 (5))"),
    "c6a": (R, "FAIL (§4.2 1)"),
    "c6b": (R, "FAIL (§4.2 1)"),
    "c7": (R, "FAIL (§4.2 2)"),
    "c8": (R, "FAIL (§4.2 5)"),
    "c15": (P, "FAIL (§4.1 (2))"),
    "c16": (P, "FAIL (§4.1 (3))"),
    "c17": (P, "FAIL (§4.1 (3))"),  # the checker reports (6) violations under (3)
    "c18": (P, "FAIL (§4.1 (3))"),
    "c19a": (P, "FAIL (§9f)"),
    "c19b": (P, "FAIL (§9f)"),
    "c20": (P, "FAIL (§9f)"),
    "c21a": (P, "FAIL (§4.1 (3))"),
    "c21b": (P, "FAIL (§9e)"),
    "c21c": (P, "FAIL (§9e)"),
    "c22a": (P, "FAIL (§4.1 (2))"),
    "c22b": (P, "FAIL (§4.1 (3))"),
    "c23": (D, "check_doc_refs FAILED:"),
}


@pytest.mark.parametrize("case", sorted(CASES))
def test_cli_red(case: str) -> None:
    argv, prefix = CASES[case]
    proc = subprocess.run([sys.executable, *argv], cwd=Path.cwd(), capture_output=True, text=True)
    lines = (proc.stdout + proc.stderr).splitlines()
    if proc.returncode == 0:
        return
    hits = [line for line in lines if line.startswith(prefix)]
    if proc.returncode == 1 and hits:
        pytest.fail(f"{case}: red as expected: {hits[0]}", pytrace=False)
    tail = lines[-1] if lines else ""
    pytest.exit(f"{case}: exit {proc.returncode} without {prefix!r} (last line: {tail!r})", returncode=3)
