#!/usr/bin/env python3
"""check_image_pins.py -- guard against the production container image's
dependency resolution silently drifting from CI's own exact-pin record
(roadmap docs/design/ROADMAP_POST_PHASE7_V1.md section 8 R-19, design D-6).

Reads a `pip freeze` transcript (stdin, or `--freeze <file>`) taken INSIDE
a built `MitateDB-api/docker/Dockerfile` image, and compares every
`name==version` line in it against `constraints.txt` (`--constraints`,
default: the repository-root `constraints.txt`). Every image package not
in the exclusion set below must appear in `constraints.txt` under the same
(normalized) name, pinned to the exact same version -- a name present in
the image but absent from `constraints.txt`, or pinned to a different
version there, is reported as a mismatch and fails the check.

Exclusion set (script-internal constant, listed verbatim per this WP's own
manifest -- changing it is a separate, explicit commit, same discipline as
tools/check_collection_floor.py's COLLECTION_FLOOR bump and tools/
check_doc_refs.py's per-family table):

    pip, setuptools, wheel                 -- venv-native tooling, never
                                               listed in constraints.txt
                                               (constraints.txt's own header
                                               comment, step 4).
    data-service-mitatedb-foundation       -- this image's OWN distribution
                                               (`MitateDB-api/pyproject.
                                               toml`'s `[project].name`),
                                               which constraints.txt never
                                               pins (it pins the two peers'
                                               DEPENDENCIES, not the peers
                                               themselves -- constraints.
                                               txt's own header comment,
                                               step 4's "-e" removal).

A `pip freeze` line that is not a plain `name==version` pin -- editable
(`-e ...`), a direct reference (`name @ file://...` or `name @
https://...`), or any other shape `_PIN_RE` does not recognize -- is
never compared: it is counted as a SKIPPED line instead (supervisor
ruling 2026-09-08, WP-2 review round 2). This is a single, general rule
rather than a pair of shape-specific branches, because `_PIN_RE` (`^name
==version$`, no embedded whitespace) already rejects both `-e ...` and
`name @ ...` on its own -- an explicit `-e `/` @ ` pre-check would be a
no-op dead branch, not an independent guard. The image's own self-install
(an editable install, or a direct reference to the wheel/sdist built from
this checkout) is exactly the shape that ends up SKIPPED this way, which
is also why `data-service-mitatedb-foundation` still needs its own
by-name entry in the exclusion set below: a *plain* `name==version`
self-install line (e.g. after a non-editable, non-`@` install) would
otherwise parse and get compared like any other package.

`run()` always reports the SKIPPED count as `skipped lines: N` (N may be
0) alongside the OK/FAILED summary line, so a `pip freeze` transcript
that unexpectedly stops looking like plain pins (a changed install mode,
a reformatted freeze) is visible in the output rather than silently
absorbed into "fewer packages checked" with no trace.

Name comparison is normalized (PEP 503 style, restricted to what this WP's
manifest specifies): case-folded, and `_`/`-` treated as equivalent, so
`Foo_Bar` and `foo-bar` are the same package. `.` is NOT folded into `-`
here (no observed package in this project's dependency set needs it; widen
this if one ever does, in its own explicit commit).

`--require <name>` (repeatable) names a package that MUST appear in the
freeze output at all (by normalized name), regardless of whether it would
otherwise match constraints.txt -- this catches a runtime dependency that
quietly stopped being installed altogether, which a pure freeze-vs-
constraints diff cannot see (an absent package is not a "mismatch", it is
simply not in `image_pins` to compare). CI passes `--require starlette
--require psycopg --require uvicorn` (MitateDB-api/pyproject.toml's own
runtime `[project.dependencies]`).

Exit code:
    0 -- every non-excluded image package matches constraints.txt exactly,
         at least one package was actually checked, and every `--require`d
         name was present. Prints "image pins OK: N packages checked".
    1 -- any of: a mismatch (including "absent from constraints.txt"), a
         missing `--require`d name, or zero packages checked (a fully
         empty or fully-excluded freeze, which would otherwise report a
         vacuous "0 packages checked" success -- this is deliberately its
         own distinct failure message, `image pins FAILED: 0 packages
         checked (vacuous)`, so it is never mistaken for a `MISMATCH:` or
         `MISSING REQUIRED:` line).

Standard library only (tools/public_value_scan.py:1-23 convention) -- no
external dependency. Python 3.9-compatible syntax (shebang + `from
__future__ import annotations` for the `X | Y` annotations below), so it
also runs under a bare `python3` with no project venv active -- the CI job
`image-pins` (`.github/workflows/ci.yml`) invokes it exactly that way,
after `docker run --entrypoint pip <image> freeze` has already run outside
this script (this script has no docker dependency of its own and is not
itself run inside the image).
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONSTRAINTS_PATH = REPO_ROOT / "constraints.txt"

# One `name==version` requirement line, optionally trailed by whitespace.
# Deliberately does NOT match environment markers (`; python_version...`)
# or extras (`name[extra]==version`) -- neither `pip freeze` output nor
# constraints.txt ever contains those shapes for this project's own
# dependency set; a line that does not match this is simply not compared
# (comments, blank lines, `-e ...`, and `name @ ...` direct references are
# all handled explicitly below, before this regex is ever tried).
_PIN_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9_.-]*)==([A-Za-z0-9_.!+-]+)$")

# Script-internal exclusion constant (see this module's own docstring).
# Listed verbatim, not derived from pyproject.toml at runtime -- deriving
# it would make this script depend on parsing a second file's own format
# just to know what to skip in a third.
_EXCLUDED_RAW_NAMES = (
    "pip",
    "setuptools",
    "wheel",
    "data-service-mitatedb-foundation",
)


def normalize_name(name: str) -> str:
    """PEP-503-style fold, restricted to what this WP's manifest asks for:
    case-fold, and collapse runs of `-`/`_` into a single `-`. `Foo_Bar`
    and `foo-bar` normalize to the same string."""
    return re.sub(r"[-_]+", "-", name).lower()


_EXCLUDED_NORMALIZED = frozenset(normalize_name(n) for n in _EXCLUDED_RAW_NAMES)


def parse_pins(text: str) -> "tuple[dict[str, tuple[str, str]], int]":
    """Parses a `pip freeze`- or constraints.txt-shaped text into
    ({normalized_name: (raw_name, version)}, skipped_count).

    Blank lines and `#` comments are dropped silently (never counted as
    skipped -- they are not pin candidates at all, not a shape this
    script failed to recognize). Every other non-blank line is either a
    `_PIN_RE`-shaped `name==version` pin, or counted in `skipped_count`
    -- this covers `-e ...` editable lines and `name @ ...` direct
    references (both are how the image's own self-install can appear in
    `pip freeze`) without needing a dedicated pre-check for either shape:
    `_PIN_RE` has no embedded-whitespace shape in it at all, so anything
    with a space where `==` should be -- these two included -- already
    falls through to the skip path on its own.

    Later lines win on a duplicate normalized name (last-one-wins,
    matching how `pip` itself treats a repeated requirement) -- neither
    input this script actually reads is expected to contain one."""
    pins: "dict[str, tuple[str, str]]" = {}
    skipped = 0
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = _PIN_RE.match(line)
        if not match:
            skipped += 1
            continue
        raw_name, version = match.group(1), match.group(2)
        pins[normalize_name(raw_name)] = (raw_name, version)
    return pins, skipped


def compare(
    image_pins: "dict[str, tuple[str, str]]",
    constraints_pins: "dict[str, tuple[str, str]]",
) -> "tuple[list[str], int]":
    """Returns (sorted list of 'MISMATCH: ...' lines, number of packages
    actually checked -- i.e. image packages outside the exclusion set)."""
    mismatches = []
    checked = 0
    for norm_name in sorted(image_pins):
        if norm_name in _EXCLUDED_NORMALIZED:
            continue
        checked += 1
        raw_name, image_version = image_pins[norm_name]
        constraints_entry = constraints_pins.get(norm_name)
        if constraints_entry is None:
            mismatches.append(
                f"MISMATCH: {raw_name} image={image_version} constraints=absent"
            )
            continue
        _, constraints_version = constraints_entry
        if constraints_version != image_version:
            mismatches.append(
                f"MISMATCH: {raw_name} image={image_version} "
                f"constraints={constraints_version}"
            )
    return mismatches, checked


def run(
    freeze_text: str,
    constraints_text: str,
    required: "list[str] | tuple[str, ...] | None" = None,
    out=None,
) -> int:
    out = out if out is not None else sys.stdout
    required = required or ()

    image_pins, image_skipped = parse_pins(freeze_text)
    constraints_pins, _constraints_skipped = parse_pins(constraints_text)

    mismatches, checked = compare(image_pins, constraints_pins)
    missing_required = [
        name for name in required if normalize_name(name) not in image_pins
    ]

    for line in mismatches:
        print(line, file=out)
    for name in missing_required:
        print(f"MISSING REQUIRED: {name} not found in freeze output", file=out)

    if checked == 0:
        print("image pins FAILED: 0 packages checked (vacuous)", file=out)
        print(f"skipped lines: {image_skipped}", file=out)
        return 1

    if mismatches or missing_required:
        print(
            f"image pins FAILED: {len(mismatches)} mismatch(es), "
            f"{len(missing_required)} missing required package(s), "
            f"of {checked} package(s) checked",
            file=out,
        )
        print(f"skipped lines: {image_skipped}", file=out)
        return 1

    print(f"image pins OK: {checked} packages checked", file=out)
    print(f"skipped lines: {image_skipped}", file=out)
    return 0


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0] if __doc__ else None,
    )
    parser.add_argument(
        "--freeze",
        metavar="FILE",
        default=None,
        help="path to a saved `pip freeze` transcript (default: read from stdin)",
    )
    parser.add_argument(
        "--constraints",
        metavar="FILE",
        default=str(DEFAULT_CONSTRAINTS_PATH),
        help="path to the exact-pin constraints file (default: repository-root constraints.txt)",
    )
    parser.add_argument(
        "--require",
        metavar="NAME",
        action="append",
        default=[],
        help=(
            "package name that must appear in the freeze output at all "
            "(repeatable); CI passes --require starlette --require psycopg "
            "--require uvicorn"
        ),
    )
    args = parser.parse_args(argv)

    if args.freeze is None:
        freeze_text = sys.stdin.read()
    else:
        freeze_text = Path(args.freeze).read_text(encoding="utf-8")

    constraints_text = Path(args.constraints).read_text(encoding="utf-8")

    return run(freeze_text, constraints_text, required=args.require)


if __name__ == "__main__":
    sys.exit(main())
