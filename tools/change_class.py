#!/usr/bin/env python3
"""change_class.py -- classify a set of changed paths into the change class
(A/B/C/D) defined by docs/design/ROADMAP_POST_PHASE7_V1.md section 9 item 8,
so CI can decide from the *path set alone* whether the conformance gate is
required for a given push.

Design: docs/design/DEVELOPMENT_PROCESS_HYGIENE_V1.md D-4. Work order:
docs/work-orders/WORK_ORDER_DEVELOPMENT_PROCESS_HYGIENE_V1.md WP-4.

Input: one path per line on stdin, or paths as positional arguments (e.g.
`git diff --name-only --no-renames origin/main...HEAD | ./.venv/bin/python tools/change_class.py`
(three dots: only the changes since the merge base, so commits merged into
main by other work in the meantime do not pull the class upward),
or `... | xargs ...` style argv usage). Paths are repo-root-relative, exactly
as `git diff --name-only` prints them. Blank lines are ignored. CI calls
`git diff` with `--no-renames`: git's default (`diff.renames=true`) prints
only a rename's DESTINATION path, so a rename would otherwise classify only
the new location and never the old one; `--no-renames` makes a rename
report as a delete-plus-add, so both the source and destination paths reach
this script and are each classified on their own merits (e.g. moving a
`security/` file out of `security/` must not be graded solely by its new,
possibly lighter-weight, location). Local invocations should use
`--no-renames` for the same reason.

Path rules (heaviest evaluated first; the FIRST rule a path matches decides
that path's class -- design D-4 item 1):

    D  `security/` (any depth under it), `CLAUDE.md`,
       `docs/security/public-repository-policy.md`, `tools/public_value_scan.py`
    C  `spec/` (any depth), `conformance-tests/` (any depth), and the
       contract JSON's two PACKAGED COPIES (see below) -- the spec/ original
       is already covered by the `spec/` rule above.
    A  none of the above, AND the path ends in `.md` (exact, case-sensitive:
       this repository's own `.md` files are all lowercase-suffixed; a path
       ending in anything else, including `.MD`, is never A on this rule).
    B  everything else.

The push's overall class is the heaviest class among all of its changed
paths (design D-4 item 1, "各ファイルの最重クラス"). `conformance_required`
is false ONLY when the overall class is A -- true for B, C, D, and for the
"unknown" class an empty input set produces (an empty push is treated as
unknown/conformance-required, the safe-side default: design D-4 item 1,
"安全側の原則: 判定できないときは全部回す").

Disclosed limitation (design D-4 item 1's own disclosure, and roadmap
section 9 item 8's C/D rows): some C/D triggers are CONTENT-level, not
path-level -- an isomorphic helper's own body registered in
`_ISOMORPHIC_TARGETS` (C), a change to the `_ISOMORPHIC_TARGETS` set itself
(D), or a changed catalog declaration value (C). A path-only classifier
cannot see inside a diff's content, so it cannot detect these. This
classification is therefore a FLOOR, not a ceiling: it never replaces the
human classification recorded in a work order's own Change Set Manifest.
The only thing CI itself consumes from this script is whether the class is
A or not (`conformance_required`) -- CI never runs the conformance gate
based on a machine-derived B/C/D distinction, precisely because that
distinction can be wrong in the C/D direction on content grounds this
script cannot see.

Contract JSON packaged-copy paths (script-internal constants, exactly like
tools/check_doc_refs.py's own family/canonical-file table and
tools/check_collection_floor.py's COLLECTION_FLOOR discipline -- changing
these paths is a separate, explicit commit): confirmed via `git ls-files`
against this repository's actual tracked tree. There are three on-disk
copies of the contract JSON: `spec/data-service-api.v1.json` (the `spec/`
original, already Class C via the `spec/` directory rule) and two
peer-packaged copies, listed explicitly below because they live OUTSIDE
`spec/`:

    r2db-api/src/r2db_api/contract/data-service-api.v1.json
    MitateDB-api/src/mitatedb_api/contract/data-service-api.v1.json

`MitateDB-api/contracts/foundation.json` is a DIFFERENT file (MitateDB's
own foundation/catalog document, not a copy of the data-service-api
contract) and is deliberately NOT in this list -- it falls through to
Class B like any other peer-code file.

Output (to stdout):
    line 1: `class=<A|B|C|D|unknown>`
    line 2: `conformance_required=<true|false>`
    then one `<class> <path>` line per input path, sorted by path (stable
    sort -- ties, i.e. a duplicated input path, keep their original input
    order).

Exit code: always 0. This script only classifies; it never encounters an
"input error" (per-tools/ convention, a non-zero exit is reserved for an
actual input error, and every line of text this script can receive on
stdin/argv is a valid, classifiable path).

Standard library only (tools/public_value_scan.py convention) -- no
external dependency.

Known gaps (recorded per docs/work-orders/OPERATING_CONDITIONS.md 1.12-71:
a gap that cannot let a contract violation or a Security Invariant breach
through the completion gate is recorded here and not filed in the ledger):
    1. not detected: a changed path the caller never hands in -- an
       untracked, an unstaged or an otherwise filtered-out path is never
       classified at all.
       why: the only input is stdin/argv, so the class is computed over
       exactly the path set given (CI gives it `git diff --name-only
       --no-renames origin/main...HEAD`). Reproduced 2026-09-23 for the
       ledger's own R-100: `echo 'MitateDB-api/docs/cloud-run-cloud-
       sql.md' | tools/change_class.py` does print `class=A` and `A
       MitateDB-api/docs/cloud-run-cloud-sql.md`, so the path rules
       above have no blind spot there -- that path had simply never
       reached the tool.
       caught by: tools/dev/finalize.py's own --allow allowlist, which
       matches EVERY changed path, tracked and untracked alike (`git
       status --porcelain --untracked-files=all`), and the supervisor's
       own `git status --short` before a class is declared.
    2. not detected: a C/D trigger that lives in a diff's CONTENT rather
       than in a path -- see "Disclosed limitation" above.
       why: same paragraph: a path-only classifier cannot look inside a
       diff.
       caught by: the human classification recorded in the work order's
       own Change Set Manifest; CI consumes only `conformance_required`.
"""
from __future__ import annotations

import sys

# ---------------------------------------------------------------------------
# Class D (heaviest). Evaluated first, exactly as roadmap section 9 item 8's
# table and design D-4 item 1 both fix.
# ---------------------------------------------------------------------------
_D_DIR_PREFIXES: tuple[str, ...] = ("security/",)
_D_EXACT_FILES: tuple[str, ...] = (
    "CLAUDE.md",
    "docs/security/public-repository-policy.md",
    "tools/public_value_scan.py",
)

# ---------------------------------------------------------------------------
# Class C. Evaluated second (after D, before the A extension rule) -- a path
# under spec/ or conformance-tests/ is C even though it also ends in `.md`.
# ---------------------------------------------------------------------------
_C_DIR_PREFIXES: tuple[str, ...] = ("spec/", "conformance-tests/")
_C_EXACT_FILES: tuple[str, ...] = (
    "r2db-api/src/r2db_api/contract/data-service-api.v1.json",
    "MitateDB-api/src/mitatedb_api/contract/data-service-api.v1.json",
)

# Class weight for "heaviest wins" (design D-4 item 1). "unknown" never
# appears in a per-path classification (only as the whole-push result for
# an empty input set), so it carries no weight here.
_CLASS_WEIGHT: dict[str, int] = {"A": 0, "B": 1, "C": 2, "D": 3}


def classify_path(path: str) -> str:
    """Classifies a single repo-root-relative path into "A"/"B"/"C"/"D",
    per the module docstring's path rules. D is checked before C, and C
    before the A extension rule -- a path matching more than one rule
    always takes the heaviest one that matches (design D-4 item 1)."""
    if path in _D_EXACT_FILES or any(path.startswith(prefix) for prefix in _D_DIR_PREFIXES):
        return "D"
    if path in _C_EXACT_FILES or any(path.startswith(prefix) for prefix in _C_DIR_PREFIXES):
        return "C"
    if path.endswith(".md"):
        return "A"
    return "B"


def heaviest(classes: list[str]) -> str:
    """The heaviest class among a non-empty list of per-path classes.
    Callers must never pass an empty list -- the empty-input case is
    handled separately in `run` as "unknown", not as a degenerate
    `heaviest([])` call."""
    return max(classes, key=lambda c: _CLASS_WEIGHT[c])


def classify_paths(paths: list[str]) -> list[tuple[str, str]]:
    """Returns (class, path) for every path, in the SAME order as `paths`
    (callers that need output sorted by path do that sort themselves)."""
    return [(classify_path(p), p) for p in paths]


def run(paths: list[str], out=None) -> int:
    out = sys.stdout if out is None else out

    # Blank lines (a trailing newline from stdin, or an empty argv element)
    # never count as a "path" -- they carry no class-determining content
    # and must not be reported in the per-path listing.
    cleaned = [p for p in paths if p]

    if not cleaned:
        # Safe-side default (design D-4 item 1): an empty change set gives
        # no evidence at all, so it is treated as unconditionally requiring
        # the conformance gate, exactly like an undiffable push.
        print("class=unknown", file=out)
        print("conformance_required=true", file=out)
        return 0

    classified = classify_paths(cleaned)
    overall = heaviest([c for c, _ in classified])
    conformance_required = "false" if overall == "A" else "true"

    print(f"class={overall}", file=out)
    print(f"conformance_required={conformance_required}", file=out)
    for c, p in sorted(classified, key=lambda entry: entry[1]):
        print(f"{c} {p}", file=out)
    return 0


def _read_paths_from_stdin() -> list[str]:
    return [line.rstrip("\n").rstrip("\r").strip() for line in sys.stdin]


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    paths = list(argv) if argv else _read_paths_from_stdin()
    return run(paths)


if __name__ == "__main__":
    sys.exit(main())
