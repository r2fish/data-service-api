"""R-39 change set 2 (C2-5): tests, conformance adapters and the two peers'
READMEs state where a thing lives as ``file.py::symbol``, never as a line
number. Work order: docs/work-orders/WORK_ORDER_R39_TEST_GAPS_V1.md section 9.

Why: a line number goes stale at the next edit above it (R-37 and its
follow-ups moved the numbers four times), and a stale number points at an
unrelated line instead of failing. A symbol is found by a grep and keeps
working through a move inside its file.

What is scanned (every file is read as text; nothing is imported or run):

- every ``*.py`` under ``r2db-api/tests``, ``r2db-api/conformance``,
  ``MitateDB-api/tests``, ``MitateDB-api/conformance`` and
  ``conformance-tests`` (recursive, ``__pycache__`` skipped), and
- the two peers' ``README.md`` (``r2db-api/README.md``,
  ``MitateDB-api/README.md``).

What counts as a position reference: the pattern ``_POSITION_REF``, applied
to the whole text of a file, matches any of these forms:

- a bare file name with the extension ``.py``, ``.md`` or ``.json`` (a path in
  front of the name is irrelevant, the name alone matches), an optional
  closing backtick, a colon, optional whitespace (a line break included) and
  an optional comment ``#`` prefix, then digits -- so ``file.py:12``,
  ``file.md`: 12`` and a number carried onto the next comment line match;
- a bare number alone inside backticks (colon, digits, optional ``-digits``),
  the form that inherits a path named earlier in the sentence;
- the words ``line`` or ``lines``, with or without a capital, followed by digits (``line 41``, ``Line 41``,
  ``lines 281-301``);
- any name that starts with a letter or ``_`` and may carry letters, digits, ``_``,
  ``.`` and ``-``, directly followed by a colon and digits with an optional
  ``-digits`` (``C-14:476``, ``test_c12:135-149``);
  the name need not carry an extension, so an identifier or a condition ID
  with a line range matches; a host and port is not a position, so a name
  ending in ``.invalid`` and the name ``localhost`` are left out;
- a four-digit label directly followed by a colon and digits (``0013:91``,
  a migration number with a line range);
- a tilde, a colon and digits (``~:2028``, an approximate position).

``file.py::symbol`` has two colons and never matches.

Excluded (``EXCLUDED_PATHS``, four entries, each must exist so the list
cannot go stale):

- ``conformance-tests/CONDITIONS.md``, ``conformance-tests/README.md`` and
  ``conformance-tests/CONDITIONS_HISTORY.md``: the condition table and its
  history (Class C records). They are not ``*.py`` so the scan never reads
  them; the entries are listed so the reason is written down once.
- ``conformance-tests/test_conformance_docstring_position_refs.py``: the
  R-95 check. Its fixture strings are deliberate position references, so it
  is excluded as a whole file.

``POSITION_REF_ALLOWLIST`` holds every match that stays. Each entry is
(file, verbatim match, expected count, kind, reason). Kind ``record`` is a
sentence that describes a past state (a former citation, a pre-rework
measurement, a quotation of a work order) and is kept as written; kind
``not-a-ref`` is a string that has the shape but names no repository
position (an AST-scan fixture file name, a fixture path). The scan fails on
a match that is not in the list or exceeds its count, and a second test
fails on an entry whose match is gone or whose count changed, so a fixed
line has to leave the list in the same change.

Known gaps (recorded per docs/work-orders/OPERATING_CONDITIONS.md 1.12-71:
a gap that cannot let a contract violation or a Security Invariant breach
through the completion gate is recorded here and not filed in the ledger):
    1. not detected: whether the symbol in a ``file.py::symbol`` still exists, a bare ``:NNN`` that inherits the path before it without backticks around it, an ``L<digits>`` position (it collides with the L1 vocabulary), a position written with a name that starts with a digit other than a four-digit label, a position whose name is split across a line break or closed by a backtick before the colon (other than the ``.py``/``.md``/``.json`` form, e.g. ``x.sql`:12``), a host and port written with a ``.invalid`` or ``localhost`` name (not treated as a position), and any reference in the four excluded files above.
       why: this file judges the shape of a reference, not its target, and a bare ``:NNN`` outside backticks is indistinguishable here from a ratio or an identifier, while ``L<digits>`` is also an ordinary vocabulary word; the excluded files hold the condition table and the R-95 fixtures, which cite positions on purpose.
       caught by: the reviewer's grep of each ``file.py::symbol`` against its file (the work order's per-symbol record), the reviewer's ``grep -n`` for a colon and digits, and R-95's own check of ``conformance-tests`` position references (it does follow a bare ``:NNN`` to its path).
"""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

SCAN_DIRS: tuple[str, ...] = (
    "r2db-api/tests",
    "r2db-api/conformance",
    "MitateDB-api/tests",
    "MitateDB-api/conformance",
    "conformance-tests",
)
SCAN_FILES: tuple[str, ...] = ("r2db-api/README.md", "MitateDB-api/README.md")

EXCLUDED_PATHS: tuple[str, ...] = (
    "conformance-tests/CONDITIONS.md",
    "conformance-tests/README.md",
    "conformance-tests/CONDITIONS_HISTORY.md",
    "conformance-tests/test_conformance_docstring_position_refs.py",
)

_POSITION_REF = re.compile(
    r"\b[A-Za-z_][A-Za-z0-9_]*\.(?:py|md|json)`?:\s*(?:#\s*)?[0-9]+"
    r"|`:[0-9]+(?:-[0-9]+)?`"
    r"|\b[Ll]ines? [0-9]+(?:-[0-9]+)?\b"
    r"|(?<![A-Za-z0-9_.-])(?!(?:[A-Za-z0-9_.-]*\.invalid|localhost):)[A-Za-z_][A-Za-z0-9_.-]*:[0-9]+(?:-[0-9]+)?\b"
    r"|\b[0-9]{4}:[0-9]+"
    r"|~:[0-9]+(?:-[0-9]+)?"
)

# (file, verbatim match, expected count, kind, reason)
_ALLOWLIST_ENTRIES: list[tuple[str, str, int, str, str]] = [
    # -- record: a sentence about a past state, kept as written
    ("r2db-api/tests/test_l1_details_vocabulary_ast_scan.py", "postgres.py:1395", 1, "record",
     "the 5 sites the closure audit found (audit-wp2e-2 R-2): a discovery record of the audited state; the current allowlist is pinned by the test itself"),
    ("r2db-api/tests/test_l1_details_vocabulary_ast_scan.py", "structured.py:1508", 1, "record",
     "a defect site 'before R-4' fixed since; the sentence records what the scanner would have missed then"),
    ("MitateDB-api/tests/test_l1_details_vocabulary_ast_scan.py", "structured.py:1508", 1, "record",
     "r2db-api's pre-R-4 defect named as the precedent; a record of that defect, not a location claim"),
    ("r2db-api/tests/test_idempotency_records.py", "service.py:1202", 1, "record",
     "the monitor's own self-mutation (J-1 audit N-1) as it was run then: a record of an audit action"),
    ("MitateDB-api/tests/test_threadpool_offload.py", "cell.py:774", 1, "record",
     "'Pre-implementation audit ... ALREADY thread-safe before this WP': the audit of that WP's starting state"),
    ("MitateDB-api/tests/test_threadpool_offload.py", "pool.py:78", 1, "record",
     "same sentence as the cell.py entry above: the pre-implementation audit's second finding"),
    ("MitateDB-api/tests/test_dry_run_and_plan.py", "cell.py:1784", 1, "record",
     "'reproduced against the pre-rework digest': the digest construction before WP-3b's rework, which no longer exists"),
    ("r2db-api/conformance/conformance_adapter_r2db.py", "service.py:1060", 1, "record",
     "'Pre-D-4/D-8 shape (measured ...)': the measurement that showed schema() returning a bare int before D-4/D-8"),
    ("conformance-tests/test_c05_limit_declaration_agreement.py", "cell.py:1491", 1, "record",
     "'former request_bytes case ... at the time this docstring was first written': the declaration as it stood then"),
    ("MitateDB-api/conformance/conformance_adapter_mitatedb.py", "test_c12_capability_agreement.py:95", 3, "record",
     "the WP-1a rework's AST measurement of attempt_mutation call sites ('TWELVE call sites across FOUR files'): a tally taken at that time"),
    ("MitateDB-api/conformance/conformance_adapter_mitatedb.py", "test_c05_limit_declaration_agreement.py:371", 1, "record",
     "same measurement tally"),
    ("MitateDB-api/conformance/conformance_adapter_mitatedb.py", "test_c17_declaration_agreement.py:283", 1, "record",
     "same measurement tally"),
    ("MitateDB-api/conformance/conformance_adapter_mitatedb.py", "test_c18_revision_precondition_semantics.py:81", 1, "record",
     "same measurement tally"),
    ("conformance-tests/test_control_mapping_register.py", "CONTROL_MAPPING.md:477", 1, "record",
     "'version 2.25's :477; the form 3.0 rewrite moved every line': the WP-1 measurement of the one unresolved reference at that version"),
    ("r2db-api/conformance/conformance_adapter_r2db.py", "`:758`", 1, "record",
     "this docstring's own 'former, unrelated' citations that a past rework corrected (Phase 8 WP-1 rework 3): kept as the record of what was corrected"),
    ("r2db-api/conformance/conformance_adapter_r2db.py", "`:845`", 1, "record", "same sentence as the :758 entry above"),
    ("r2db-api/conformance/conformance_adapter_r2db.py", "`:907`", 1, "record", "same sentence as the :758 entry above"),
    ("MitateDB-api/tests/test_threadpool_offload.py", "`:781`", 1, "record",
     "same sentence as the cell.py:774 entry: the pre-implementation audit's own finding"),
    ("conformance-tests/test_c05_limit_declaration_agreement.py", "`:1502`", 1, "record",
     "same sentence as the cell.py:1491 entry: the former declaration at the time the docstring was first written"),
    ("MitateDB-api/conformance/conformance_adapter_mitatedb.py", "`:125-130`", 1, "record",
     "same measurement tally as the test_c12 entries: the positive control's assertion as measured then"),
    ("conformance-tests/test_c21_denial_details_vocabulary.py", "lines 119", 1, "record",
     "review point G of WP-1b's rework ('lines 119/161 add unconditionally'): a record of the finding that replaced a structurally dead assert"),
    ("conformance-tests/test_control_mapping_register.py", "`:477`", 1, "record",
     "same sentence as the CONTROL_MAPPING.md:477 entry: version 2.25's line"),
    ("MitateDB-api/conformance/conformance_adapter_mitatedb.py", "test_c05:371", 1, "record", "same measurement tally (short form of the test_c05 entry)"),
    ("MitateDB-api/conformance/conformance_adapter_mitatedb.py", "test_c17:283", 2, "record", "same measurement tally (short form of the test_c17 entry)"),
    ("MitateDB-api/conformance/conformance_adapter_mitatedb.py", "test_c18_...py:360", 1, "record", "same measurement tally: the one delete call the tally excluded"),
    ("conformance-tests/test_c05_limit_declaration_agreement.py", "test_c05:646-659", 1, "record",
     "the V1 statistical control that WP-1a removed: named to say what is no longer there"),
    ("r2db-api/tests/test_audit_query.py", "test_control_main.py:165", 1, "record",
     "a verbatim quotation of the work order's completion condition 7 (WP-B3), quoted as written"),
    # -- not-a-ref: the shape without a repository position
    ("conformance-tests/test_control_mapping_register.py", "fixture_target.py:3", 1, "not-a-ref",
     "a fixture file the test itself writes into tmp_path for the CONTROL_MAPPING position-reference check"),
    ("conformance-tests/test_control_mapping_register.py", "`:5-9`", 1, "not-a-ref",
     "a fixture sentence the test writes into a synthetic CONTROL_MAPPING text to exercise a bare-colon extraction"),
    ("conformance-tests/test_control_mapping_register.py", "line 9", 1, "not-a-ref",
     "the expected failure message of the checker under test ('line 9 beyond EOF 5'), not a reference"),
    ("conformance-tests/test_control_mapping_register.py", "line 9999", 1, "not-a-ref",
     "the expected failure message of the checker under test ('line 9999 beyond EOF'), not a reference"),
    ("conformance-tests/test_control_mapping_register.py", "five_lines.sql:4-2", 1, "not-a-ref",
     "a fixture reference to a synthetic file the test itself writes (the reversed-range case)"),
    ("conformance-tests/test_control_mapping_register.py", "five_lines.sql:9", 1, "not-a-ref",
     "a fixture reference to a synthetic file the test itself writes (the beyond-EOF case)"),
    *[
        (peer, name, 1, "not-a-ref",
         "an AST-scan fixture file name passed to the scanner under test; no such file exists")
        for peer in ("r2db-api/tests/test_audit_query.py", "MitateDB-api/tests/test_audit_query.py")
        for name in (
            "synthetic_dict_fstring.py:2",
            "synthetic_with_as.py:4",
            "synthetic_except_as.py:5",
            "synthetic_second_binding.py:5",
            "synthetic_kw_attr.py:2",
            "synthetic_kw_sub.py:2",
        )
    ],
]

POSITION_REF_ALLOWLIST: dict[tuple[str, str], tuple[int, str, str]] = {}
_DUPLICATE_ENTRIES: list[tuple[str, str]] = []
for _file, _token, _count, _kind, _reason in _ALLOWLIST_ENTRIES:
    if (_file, _token) in POSITION_REF_ALLOWLIST:
        _DUPLICATE_ENTRIES.append((_file, _token))
    POSITION_REF_ALLOWLIST[(_file, _token)] = (_count, _kind, _reason)


def _scanned_files() -> list[Path]:
    excluded = {REPO_ROOT / rel for rel in EXCLUDED_PATHS}
    found: list[Path] = []
    for rel in SCAN_DIRS:
        for path in sorted((REPO_ROOT / rel).rglob("*.py")):
            if "__pycache__" in path.parts or path in excluded:
                continue
            found.append(path)
    for rel in SCAN_FILES:
        path = REPO_ROOT / rel
        if path not in excluded:
            found.append(path)
    return found


def _observed() -> Counter[tuple[str, str]]:
    seen: Counter[tuple[str, str]] = Counter()
    for path in _scanned_files():
        rel = path.relative_to(REPO_ROOT).as_posix()
        for match in _POSITION_REF.findall(path.read_text(encoding="utf-8")):
            seen[(rel, match)] += 1
    return seen


def test_scan_roots_exist_and_each_holds_files() -> None:
    files = _scanned_files()
    assert files, "the scan found no file at all"
    for rel in SCAN_DIRS:
        assert (REPO_ROOT / rel).is_dir(), f"scan directory is gone: {rel}"
        assert any(p.is_relative_to(REPO_ROOT / rel) for p in files), f"scan directory holds no scanned *.py: {rel}"
    for rel in SCAN_FILES:
        assert (REPO_ROOT / rel).is_file(), f"scanned README is gone: {rel}"
        assert REPO_ROOT / rel in files, f"scanned README was not read: {rel}"


def test_excluded_paths_exist_and_are_not_scanned() -> None:
    assert len(EXCLUDED_PATHS) == len(set(EXCLUDED_PATHS)) == 4
    scanned = {p.relative_to(REPO_ROOT).as_posix() for p in _scanned_files()}
    for rel in EXCLUDED_PATHS:
        assert (REPO_ROOT / rel).is_file(), f"excluded path is gone (drop it from EXCLUDED_PATHS): {rel}"
        assert rel not in scanned, f"excluded path was scanned: {rel}"


def test_position_ref_pattern_matches_the_shapes_it_is_meant_for() -> None:
    assert _POSITION_REF.findall("see `cell.py:12` and r2db-api/src/r2db_api/service.py:709-720") == ["cell.py:12", "service.py:709"]
    assert _POSITION_REF.findall("see cell.py::ApplicationCell.insert and a bare :12 and cell.py: and at 12:30, 1:1, L41, example.invalid:5432 and localhost:8080") == []
    assert _POSITION_REF.findall("see C-14:476, test_c12:135-149, 0013:91-96, ~:2028, x.txt:5, __init__:1118-1120, Line 41 and a.invalid:5432") == ["C-14:476", "test_c12:135-149", "0013:91", "~:2028", "x.txt:5", "__init__:1118-1120", "Line 41"]
    assert _POSITION_REF.findall("see `x.py`:12, `CONDITIONS.md:47`, `y.json`: 3 and z.py:\n# 355") == ["x.py`:12", "CONDITIONS.md:47", "y.json`: 3", "z.py:\n# 355"]
    assert _POSITION_REF.findall("at `:12`, `:5-9` and in lines 281-301, line 41, but not `:x`, 1:1 or underline 5") == ["`:12`", "`:5-9`", "lines 281-301", "line 41"]


def test_allowlist_is_well_formed() -> None:
    assert not _DUPLICATE_ENTRIES, f"duplicate allowlist (file, match) entries: {_DUPLICATE_ENTRIES}"
    assert POSITION_REF_ALLOWLIST, "the allowlist is empty -- an empty list would mean no sentence records a past state"
    for (file, token), (count, kind, reason) in POSITION_REF_ALLOWLIST.items():
        assert count >= 1, f"{file} {token}: count must be at least 1"
        assert kind in {"record", "not-a-ref"}, f"{file} {token}: unknown kind {kind!r}"
        assert reason.strip(), f"{file} {token}: the reason is empty"
        assert _POSITION_REF.fullmatch(token), f"{file} {token}: the entry is not a verbatim match of the pattern"


def test_no_line_number_position_ref_outside_the_allowlist() -> None:
    observed = _observed()
    assert observed, "the scan observed no match at all -- the pattern or the scan roots are broken"
    unexpected = {
        key: (n, POSITION_REF_ALLOWLIST.get(key, (0, "", ""))[0])
        for key, n in observed.items()
        if n > POSITION_REF_ALLOWLIST.get(key, (0, "", ""))[0]
    }
    assert not unexpected, (
        "line-number position references outside the allowlist (key -> (found, allowed)); "
        "write the location as `file.py::symbol`: " + repr(sorted(unexpected.items()))
    )


def test_every_allowlist_entry_still_matches_exactly() -> None:
    observed = _observed()
    stale = {
        key: (observed.get(key, 0), count)
        for key, (count, _kind, _reason) in POSITION_REF_ALLOWLIST.items()
        if observed.get(key, 0) != count
    }
    assert not stale, (
        "allowlist entries whose match is gone or whose count changed (key -> (found, expected)); "
        "remove or update the entry in the same change: " + repr(sorted(stale.items()))
    )
