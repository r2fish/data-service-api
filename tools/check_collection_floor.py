#!/usr/bin/env python3
"""check_collection_floor.py -- guard against a silent drop in the total
number of tests the root pytest session collects (R-9, evidence-loss
detection).

Design: docs/design/PHASE8_EFFECTIVE_BOUNDS_AND_HYGIENE_V1.md D-3. Work
order: docs/work-orders/WORK_ORDER_PHASE8_EFFECTIVE_BOUNDS_V1.md WP-2.

Runs `<this interpreter> -m pytest --collect-only -q` from the repository
root, reads the trailing "<N> test(s) collected" summary line, and compares
it against the decimal integer stored in conformance-tests/COLLECTION_FLOOR
(or an explicit path passed as the sole positional argument).

Exit code:
    0 -- measured collected count >= floor, AND `--collect-only` exited
         cleanly (exit code 0) with no collection error reported on its
         own summary line (an increase in the count is always fine).
    1 -- any of: measured collected count < floor; the floor file could
         not be read/parsed; the "<N> test(s) collected" line could not
         be found in pytest's own output; OR `--collect-only` exited with
         a non-zero return code, or its summary line itself reports an
         error (e.g. "2274 tests collected, 1 error in 0.21s"). This last
         case matters even when the measured count is still >= floor: a
         collection error can hide an entire broken test package (e.g. a
         broken conftest.py) behind a summary line that still reports a
         plausible-looking count for the tests collection *did* manage to
         reach before failing. Partial collection is never evidence of
         the floor being met, so it is never reported as a pass -- an
         unreadable or partial result must never be reported as "clean".

Standard library only (tools/public_value_scan.py:1-23 convention) -- no
external dependency.

The floor itself is not bumped by this script. It only compares; raising
COLLECTION_FLOOR after a legitimate increase is a separate, explicit commit
(see conformance-tests/README.md's COLLECTION_FLOOR section) made at a
phase's completion gate, not something this tool does on its own.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FLOOR_PATH = REPO_ROOT / "conformance-tests" / "COLLECTION_FLOOR"

# pytest -q --collect-only's own summary line, e.g. "2274 tests collected
# in 1.19s" (or "1 test collected in 0.01s" for the singular), possibly
# followed by an error clause, e.g. "2274 tests collected, 1 error in
# 0.21s". Matched via re.search, which returns the FIRST occurrence in the
# combined stdout/stderr, not literally the last line of it -- in practice
# this project's `--collect-only` output contains exactly one such line,
# so "first" and pytest's own trailing summary line coincide.
#
# When some items are deselected (e.g. a `-k`/`-m` filter is in effect),
# pytest instead prints "<selected>/<total> tests collected (<n>
# deselected) in 0.01s". This regex's digit group captures <total> (the
# number immediately preceding "tests collected"), not <selected> -- and
# that is what this tool wants: COLLECTION_FLOOR is a floor on the size of
# the *collected* session (how many tests exist), not on how many a given
# filter happens to select. Neither this project's addopts nor its CI
# invocation of `--collect-only` ever pass `-k`/`-m`, so this path is
# currently untested in practice; if a `-k`/`-m` filter is ever added to
# this project's `--collect-only` invocation, re-verify this assumption
# against that pytest version's exact wording before relying on it.
_COLLECTED_RE = re.compile(r"(\d+)\s+tests?\s+collected\b")


def _read_floor(floor_path: Path) -> int:
    if not floor_path.is_file():
        print(f"ERROR: floor file not found: {floor_path}", file=sys.stderr)
        sys.exit(1)
    text = floor_path.read_text().strip()
    if not re.fullmatch(r"\d+", text):
        print(
            f"ERROR: {floor_path} must contain exactly one decimal integer "
            f"and nothing else; got {text!r}",
            file=sys.stderr,
        )
        sys.exit(1)
    return int(text)


def _measure_collected() -> tuple[int, str, int]:
    """Returns (measured_count, summary_line, returncode). `summary_line`
    is the single output line the count was read from -- callers must
    inspect it (and `returncode`) for a reported collection error before
    trusting `measured_count`, since a partial/errored collection can
    still print a plausible-looking "<N> tests collected" count for
    whatever it reached before failing."""
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    output = proc.stdout + "\n" + proc.stderr
    match = _COLLECTED_RE.search(output)
    if match is None:
        # Fail loud, never silently report a clean result when the count
        # itself could not be read -- an unreadable count is not evidence
        # that nothing regressed.
        print(
            "ERROR: could not find a '<N> test(s) collected' line in "
            f"`{sys.executable} -m pytest --collect-only -q` output "
            f"(exit code {proc.returncode}). Last 20 lines of combined "
            "output:",
            file=sys.stderr,
        )
        for line in output.splitlines()[-20:]:
            print(line, file=sys.stderr)
        sys.exit(1)
    line_start = output.rfind("\n", 0, match.start()) + 1
    line_end = output.find("\n", match.end())
    if line_end == -1:
        line_end = len(output)
    summary_line = output[line_start:line_end]
    return int(match.group(1)), summary_line, proc.returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "floor_file",
        nargs="?",
        type=Path,
        default=DEFAULT_FLOOR_PATH,
        help="Path to the COLLECTION_FLOOR file (default: conformance-tests/COLLECTION_FLOOR)",
    )
    args = parser.parse_args(argv)

    floor = _read_floor(args.floor_file)
    measured, summary_line, returncode = _measure_collected()
    diff = measured - floor

    # Partial collection is never evidence of the floor being met, even
    # when the count it did reach is >= floor: a broken conftest.py (or
    # any other collection error) can hide an entire missing test package
    # behind a summary line that still reports a plausible-looking count.
    if returncode != 0 or "error" in summary_line.lower():
        print(
            "COLLECTION_FLOOR check FAILED: "
            f"`{sys.executable} -m pytest --collect-only -q` reported a "
            f"collection error (exit code {returncode}); summary line: "
            f"{summary_line.strip()!r}. A partial collection is not "
            "evidence of the floor being met, regardless of the count it "
            "reports -- refusing to report a clean result.",
            file=sys.stderr,
        )
        return 1

    if measured < floor:
        print(
            f"COLLECTION_FLOOR check FAILED: measured={measured} floor={floor} diff={diff}",
            file=sys.stderr,
        )
        return 1

    print(f"COLLECTION_FLOOR check OK: measured={measured} floor={floor} diff={diff}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
