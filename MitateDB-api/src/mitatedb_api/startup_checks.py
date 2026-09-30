"""``ops startup-checks``: judges, for every revision an operator declares and
one proposed ``process_ceilings`` declaration, whether that revision's own
startup checks on role connection limits (F-16) and on ``max_connections``
headroom (F-18) would pass, before the declaration is written.

The judgment is a read: the platform database is read through the same
read-only connection `ops inventory` uses (the caller opens it and passes in
what it read, this module never imports ``ops``), and a revision's source is
read from git objects only (``cat-file``, ``ls-tree``), never from a working
tree and never by fetching or checking anything out (git is run with
``GIT_NO_LAZY_FETCH=1``, so a partial clone does not fetch a missing object;
git versions before 2.44 ignore the variable, and ``GIT_NO_REPLACE_OBJECTS=1``,
so ``refs/replace`` entries of the operator's clone never substitute an
object). Nothing is written.

Input: ``--data D`` and ``--control C`` (the proposed ceilings),
``--revisions FILE`` (JSON, format ``mitatedb-startup-checks/1``: the revisions
that can start while the declaration stands, each with its plane, kinds,
40-hex ``source_ref`` and the two ``env`` values the checks read, an unset value
written ``null``), ``--repository PATH`` (a git checkout holding every
``source_ref``) and ``MITATEDB_PROVISION_DSN`` in the environment. The file
must list, per plane, every kind of revision or declare it absent
(``declared_absent``); a file that does not is rejected.

Output: one JSON object on stdout (sorted keys). ``overall`` is ``blocked`` when
any check of any revision is blocked, else ``unknown`` when any is unknown,
else ``confirmed``. ``declaration.current`` is reported, never judged: the
declared ``{"data": n, "control": n}``, ``"not-declared"`` when the declaration
table has no ``process_ceilings`` row, or ``"unreadable"`` when the read or the
value's validation fails. Exit code 0 only for ``confirmed``; 2 when a judgment was
produced but is not ``confirmed`` (a revision whose source cannot be
positively identified is ``unknown``, a failed git read included); 1 when no
judgment could be produced (a rejected input, no DSN, a read-only setting that
did not read back as ``on``, a database failure, a ``--repository`` that is not
a git checkout, an argparse usage error or an unrecognised argument), and then
stdout carries nothing. Stderr is one fixed line, except for an argparse usage
error, which prints argparse's usage line and one error line that can name the
rejected value.

Generations. The checks changed shape over the history of the code, so a
revision is judged by the formula of the generation its source belongs to.
A generation is identified from the source tree of ``source_ref``, never from
ancestry or dates. The identifying set (the fingerprint, per plane) is: the blob
ids of ``platform_declarations.py`` and ``config.py`` and of the plane's startup
module (``main.py`` for data, ``control_composition.py`` for control); the
digest of the ``DEFAULT_THREAD_LIMIT`` assignment in ``http.py`` (or nothing);
and the sorted (file, innermost enclosing ``def``, count) list of the places
in any ``.py`` under ``MitateDB-api/src`` that name either check function (a
Name, an Attribute or an import alias). A fingerprint found in
``KNOWN_FINGERPRINTS`` is that row's generation. One not found is generation G0
(neither check exists) only when the startup module exists, the list of places
that name a check function is empty and no string constant in any source file equals one of the
two check names or the two code labels; anything else is ``unknown`` with
``reason`` ``fingerprint-not-in-table``. A source file that does not parse makes
the revision ``unknown`` (``source-unparseable``).

Operational fact (a cost, not a gap): a commit that changes
``platform_declarations.py``, ``config.py``, ``main.py`` or
``control_composition.py``, or ``http.py``'s ``DEFAULT_THREAD_LIMIT``, or that
adds or removes a place naming a check function, changes the working-tree
fingerprint. The tests that compare the working tree with the current-
generation row (``test_working_tree_data_fingerprint_is_the_current_generation_row``
and ``test_working_tree_control_fingerprint_is_the_current_generation_row`` in
``MitateDB-api/tests/test_ops_startup_checks.py``) are red until the row is
updated in the same change. A commit
that changes those files without changing the formula keeps the current
generation; a commit that changes the formula adds a new generation and leaves
the existing rows as frozen generations. Rows without a representative ref are
filled in by the next change that touches this table.

Known gaps. Each item has the identifier the report carries in ``known_gaps``,
in this order.

  1. ``revision-list-is-declared`` -- not detected: a revision that can start
     but is missing from the file. why: the platform layer (Cloud Run
     revisions, traffic, tags) is not readable from here; the file's own
     per-plane coverage of kinds only rejects an undeclared kind. caught by:
     the runbook's reading of the platform layer and the coverage rule.
  2. ``image-env-and-command-are-declared`` -- not detected: an image
     ``ENV`` or a container command or args that changes what a revision
     reads. why: the image and the container spec are not readable from here;
     the operator copies the two values into ``env``. caught by: the runbook's
     source and environment confirmation.
  3. ``inputs-outside-fingerprint`` -- not detected: a change outside the
     fingerprint's files that alters a check's inputs without changing the
     fingerprint's other elements. why: the fingerprint is finite. caught by:
     review of any change that touches how the two checks are called.
  4. ``serve-apps-not-read`` -- not detected: the fact that a revision serves
     only some applications. why: the data plane is judged against every
     registered application's roles, which is at least as strict as a
     revision's own startup check. caught by: not needed for safety; the
     judgment can only be stricter than the startup check.
  5. ``no-role-of-class-is-unknown`` -- a class with no role at all (data api
     role, control controlplane role, auditreader role when the control
     revision has an audit dsn) is ``unknown`` although the startup check
     passes it. why: the tool cannot tell an unprovisioned platform from a
     revoked grant. caught by: the operator reading the ``unknown``.
  6. ``f18-judged-at-one-registration`` -- the headroom lower bound is
     computed as though at least one application is registered, with the
     zero-registration bound shown beside it. why: the first registration
     must not turn every revision into a startup failure. caught by: stricter
     than the startup check, never looser.
  7. ``window-applied-by-class`` -- the migration window (the limits the
     platform migrations put back) is applied to a role by its class, not by
     its name. why: a role with another name is judged with the migrations'
     values although the migrations name literal roles. caught by: stricter
     than the migrations, never looser.
  8. ``other-startup-checks-not-judged`` -- not detected: any startup check
     other than F-16 and F-18 (for example the worker count check). why: only
     these two are in scope. caught by: the runbook's own checks for them.
  9. ``uncommitted-checkout-not-detected`` -- not detected: a change in the
     operator's checkout that is not committed (the tool's own current-
     generation code included). why: the tool reads only the objects of
     ``source_ref``, and its own code runs from wherever it is installed.
     caught by: the runbook's rules that ``source_ref`` is taken from the
     attested image digest and that the tool is run from a checkout whose
     ``git status --porcelain`` is empty.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import subprocess
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence

from psycopg import Error as PsycopgError
from psycopg import sql

from . import config
from . import platform_declarations

FORMAT = "mitatedb-startup-checks/1"

PLANES = ("data", "control")
KINDS = ("serving", "rollback_target", "env_only_revision", "candidate", "other")

ENV_MAX_CONCURRENCY = "MITATEDB_MAX_CONCURRENCY"
ENV_THREAD_LIMIT = "MITATEDB_THREAD_LIMIT"

#: The identifiers of the report's ``known_gaps``, in the order of the
#: module docstring's Known gaps list.
KNOWN_GAPS = (
    "revision-list-is-declared",
    "image-env-and-command-are-declared",
    "inputs-outside-fingerprint",
    "serve-apps-not-read",
    "no-role-of-class-is-unknown",
    "f18-judged-at-one-registration",
    "window-applied-by-class",
    "other-startup-checks-not-judged",
    "uncommitted-checkout-not-detected",
)

CHECKS_EVALUATED = ("F-16", "F-18")

#: ``declared_absent`` vocabulary. ``data.candidate`` is not in it: a data
#: candidate must be listed.
_DECLARABLE_ABSENT = (
    "data.serving", "data.rollback_target", "data.env_only_revision", "data.other",
    "control",
    "control.serving", "control.rollback_target", "control.env_only_revision",
    "control.candidate", "control.other",
)
_CONTROL_KIND_ITEMS = (
    "control.serving", "control.rollback_target", "control.env_only_revision",
    "control.candidate", "control.other",
)
_DATA_KIND_ITEMS = ("data.serving", "data.rollback_target", "data.env_only_revision", "data.other")
_DATA_CANDIDATE_ITEM = "data.candidate"

_REVISION_KEYS = frozenset({"name", "plane", "kinds", "source_ref", "env"})
_ENV_KEYS = frozenset({ENV_MAX_CONCURRENCY, ENV_THREAD_LIMIT})
_AUDIT_DSN_KEY = "audit_dsn_configured"
_SOURCE_REF_PATTERN = re.compile(r"[0-9a-f]{40}")


class InputRejected(Exception):
    """An input the tool refuses to judge. ``rule`` is a fixed word, never
    the rejected value."""

    def __init__(self, rule: str) -> None:
        super().__init__(rule)
        self.rule = rule


@dataclass(frozen=True)
class Revision:
    name: str
    plane: str
    kinds: tuple
    source_ref: str
    max_concurrency: Optional[str]
    thread_limit: Optional[str]
    audit_dsn_configured: Optional[bool]


@dataclass(frozen=True)
class RevisionsDocument:
    revisions: tuple
    declared_absent: frozenset
    coverage: Mapping


def _reject(rule: str):
    raise InputRejected(rule)


def _parse_revision(entry: object) -> Revision:
    if not isinstance(entry, dict):
        _reject("revision-shape")
    if set(entry) - _REVISION_KEYS - {_AUDIT_DSN_KEY}:
        _reject("unknown-key")
    if _REVISION_KEYS - set(entry):
        _reject("missing-key")
    plane = entry["plane"]
    if not isinstance(plane, str) or plane not in PLANES:
        _reject("unknown-value")
    if plane == "data" and _AUDIT_DSN_KEY in entry:
        _reject("audit-dsn-on-data")
    if plane == "control" and _AUDIT_DSN_KEY not in entry:
        _reject("missing-key")
    name = entry["name"]
    if not isinstance(name, str) or not name:
        _reject("name")
    kinds = entry["kinds"]
    if not isinstance(kinds, list) or not kinds:
        _reject("kinds")
    for kind in kinds:
        if not isinstance(kind, str) or kind not in KINDS:
            _reject("unknown-value")
    if len(set(kinds)) != len(kinds):
        _reject("kinds")
    source_ref = entry["source_ref"]
    if not isinstance(source_ref, str) or not _SOURCE_REF_PATTERN.fullmatch(source_ref):
        _reject("source-ref")
    env = entry["env"]
    if not isinstance(env, dict):
        _reject("env-shape")
    if set(env) != _ENV_KEYS:
        _reject("env-keys")
    for value in env.values():
        if value is not None and not isinstance(value, str):
            _reject("env-value")
    audit = entry.get(_AUDIT_DSN_KEY)
    if plane == "control" and not isinstance(audit, bool):
        _reject("audit-dsn-type")
    return Revision(
        name=name, plane=plane, kinds=tuple(kinds), source_ref=source_ref,
        max_concurrency=env[ENV_MAX_CONCURRENCY], thread_limit=env[ENV_THREAD_LIMIT],
        audit_dsn_configured=audit if plane == "control" else None,
    )


def _coverage(declared_absent: frozenset, revisions: Sequence[Revision]) -> dict:
    listed = {f"{revision.plane}.{kind}" for revision in revisions for kind in revision.kinds}
    control_declared_absent = "control" in declared_absent
    if control_declared_absent:
        if any(revision.plane == "control" for revision in revisions):
            _reject("control-declared-absent-with-revisions")
        if any(item in declared_absent for item in _CONTROL_KIND_ITEMS):
            _reject("control-declared-absent-with-items")
    elif not any(revision.plane == "control" for revision in revisions):
        _reject("control-revisions-missing")
    if _DATA_CANDIDATE_ITEM not in listed:
        _reject("data-candidate-missing")
    coverage = {_DATA_CANDIDATE_ITEM: "listed"}
    items = _DATA_KIND_ITEMS if control_declared_absent else _DATA_KIND_ITEMS + _CONTROL_KIND_ITEMS
    for item in items:
        in_list = item in listed
        in_absent = item in declared_absent
        if in_list and in_absent:
            _reject("coverage-conflict")
        if not in_list and not in_absent:
            _reject("coverage-gap")
        coverage[item] = "listed" if in_list else "declared-absent"
    if control_declared_absent:
        coverage["control"] = "declared-absent"
        for item in _CONTROL_KIND_ITEMS:
            coverage[item] = "plane-declared-absent"
    else:
        coverage["control"] = "listed"
    return coverage


def parse_revisions_document(text: str) -> RevisionsDocument:
    """Parses and validates the revisions file. Raises `InputRejected` with
    a fixed rule word; touches nothing else."""
    try:
        raw = json.loads(text)
    except (ValueError, RecursionError):
        _reject("not-json")
    if not isinstance(raw, dict):
        _reject("format")
    if raw.get("format") != FORMAT:
        _reject("format")
    if set(raw) != {"format", "declared_absent", "revisions"}:
        _reject("unknown-key")
    declared = raw["declared_absent"]
    if not isinstance(declared, list):
        _reject("declared-absent-shape")
    for item in declared:
        if not isinstance(item, str) or item not in _DECLARABLE_ABSENT:
            _reject("unknown-value")
    entries = raw["revisions"]
    if not isinstance(entries, list):
        _reject("revisions-shape")
    if not entries:
        _reject("empty-revisions")
    revisions = tuple(_parse_revision(entry) for entry in entries)
    names = [revision.name for revision in revisions]
    if len(set(names)) != len(names):
        _reject("duplicate-name")
    declared_absent = frozenset(declared)
    return RevisionsDocument(
        revisions=revisions, declared_absent=declared_absent,
        coverage=_coverage(declared_absent, revisions),
    )


# ---------------------------------------------------------------------------
# Generation identification from git objects.
# ---------------------------------------------------------------------------

_SRC_PREFIX = "MitateDB-api/src/"
_PACKAGE_PREFIX = _SRC_PREFIX + "mitatedb_api/"
_PLATFORM_DECLARATIONS_PATH = _PACKAGE_PREFIX + "platform_declarations.py"
_CONFIG_PATH = _PACKAGE_PREFIX + "config.py"
_HTTP_PATH = _PACKAGE_PREFIX + "http.py"
_STARTUP_MODULE_PATHS = {
    "data": _PACKAGE_PREFIX + "main.py",
    "control": _PACKAGE_PREFIX + "control_composition.py",
}
_CHECK_FUNCTION_NAMES = frozenset({"check_role_connection_limits", "check_max_connections_headroom"})
_CHECK_TOKENS = _CHECK_FUNCTION_NAMES | {"F-16", "F-18"}
_GIT_TIMEOUT_SECONDS = 120


class SourceUnparseable(Exception):
    """A ``.py`` under the source tree does not parse."""


class _GitFailure(Exception):
    """A git command failed to run or exited non-zero."""


@dataclass(frozen=True)
class Fingerprint:
    platform_declarations: Optional[str]
    config: Optional[str]
    startup_module: Optional[str]
    default_thread_limit: Optional[str]
    checker_references: tuple


@dataclass(frozen=True)
class SourceTreeFingerprint:
    """What one source tree contributes to identification: the shared elements,
    the startup modules' blob ids per plane, and the facts the G0 rule reads."""
    platform_declarations: Optional[str]
    config: Optional[str]
    default_thread_limit: Optional[str]
    checker_references: tuple
    has_check_constant: bool
    startup_modules: Mapping

    def fingerprint(self, plane: str) -> Fingerprint:
        return Fingerprint(
            platform_declarations=self.platform_declarations,
            config=self.config,
            startup_module=self.startup_modules.get(plane),
            default_thread_limit=self.default_thread_limit,
            checker_references=self.checker_references,
        )


@dataclass(frozen=True)
class KnownFingerprint:
    plane: str
    generation: str
    representative_ref: Optional[str]
    fingerprint: Fingerprint


@dataclass(frozen=True)
class Identification:
    generation: Optional[str]
    reason: Optional[str]


@dataclass(frozen=True)
class _BlobAnalysis:
    references: tuple
    has_check_constant: bool
    default_thread_limit: Optional[str]


#: Analysis of a blob by its object id (content-addressed, so a result never
#: goes stale). ``None`` records a source that does not parse.
_ANALYSIS_CACHE: dict = {}


def _analyze(data: bytes) -> Optional[_BlobAnalysis]:
    try:
        text = data.decode("utf-8")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            tree = ast.parse(text)
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return None
    counts: dict = {}
    has_constant = False
    stack = [(tree, "<module>")]
    while stack:
        node, enclosing = stack.pop()
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.Name):
                referenced = child.id
            elif isinstance(child, ast.Attribute):
                referenced = child.attr
            elif isinstance(child, ast.alias):
                referenced = child.name
            else:
                referenced = None
            if referenced in _CHECK_FUNCTION_NAMES:
                counts[enclosing] = counts.get(enclosing, 0) + 1
            if isinstance(child, ast.Constant) and isinstance(child.value, str) and child.value in _CHECK_TOKENS:
                has_constant = True
            inner = child.name if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) else enclosing
            stack.append((child, inner))
    digest = None
    for statement in tree.body:
        if isinstance(statement, ast.Assign) and statement.targets:
            target = statement.targets[0]
        elif isinstance(statement, ast.AnnAssign):
            target = statement.target
        else:
            continue
        if isinstance(target, ast.Name) and target.id == "DEFAULT_THREAD_LIMIT":
            segment = ast.get_source_segment(text, statement)
            if segment is not None:
                digest = hashlib.sha256(segment.encode("utf-8")).hexdigest()
                break
    return _BlobAnalysis(
        references=tuple(sorted(counts.items())), has_check_constant=has_constant,
        default_thread_limit=digest,
    )


def compute_fingerprints(
    tree: Mapping[str, str],
    read_blobs: Callable[[Sequence[str]], Mapping[str, bytes]],
) -> SourceTreeFingerprint:
    """The fingerprint of a source tree given as ``{path: blob id}`` (paths
    from the repository root, under ``MitateDB-api/src/``). ``read_blobs``
    returns the bytes of the blob ids it is asked for. Raises
    `SourceUnparseable` when any ``.py`` does not parse."""
    python_paths = sorted(path for path in tree if path.endswith(".py"))
    missing = [tree[path] for path in python_paths if tree[path] not in _ANALYSIS_CACHE]
    if missing:
        contents = read_blobs(missing)
        for blob_id in dict.fromkeys(missing):
            _ANALYSIS_CACHE[blob_id] = _analyze(contents[blob_id])
    references = []
    has_constant = False
    for path in python_paths:
        analysis = _ANALYSIS_CACHE[tree[path]]
        if analysis is None:
            raise SourceUnparseable()
        has_constant = has_constant or analysis.has_check_constant
        shown = path[len(_PACKAGE_PREFIX):] if path.startswith(_PACKAGE_PREFIX) else path
        for enclosing, count in analysis.references:
            references.append((shown, enclosing, count))
    http_blob = tree.get(_HTTP_PATH)
    return SourceTreeFingerprint(
        platform_declarations=tree.get(_PLATFORM_DECLARATIONS_PATH),
        config=tree.get(_CONFIG_PATH),
        default_thread_limit=_ANALYSIS_CACHE[http_blob].default_thread_limit if http_blob else None,
        checker_references=tuple(sorted(references)),
        has_check_constant=has_constant,
        startup_modules={plane: tree.get(path) for plane, path in _STARTUP_MODULE_PATHS.items()},
    )


def git_blob_id(data: bytes) -> str:
    """The object id git gives a blob with this content (computed, not
    written)."""
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def working_tree_fingerprints(source_root: Path) -> SourceTreeFingerprint:
    """The fingerprint of the ``.py`` files under ``source_root`` (the
    directory that holds the ``mitatedb_api`` package), read from the file
    system and never written."""
    tree: dict = {}
    contents: dict = {}
    for path in sorted(source_root.rglob("*.py")):
        data = path.read_bytes()
        blob_id = git_blob_id(data)
        tree[_SRC_PREFIX + path.relative_to(source_root).as_posix()] = blob_id
        contents[blob_id] = data
    return compute_fingerprints(tree, lambda blob_ids: {blob_id: contents[blob_id] for blob_id in blob_ids})


def _run_git(repository: str, arguments: Sequence[str], stdin: Optional[bytes] = None) -> bytes:
    try:
        completed = subprocess.run(
            ["git", "-C", repository, *arguments], input=stdin, capture_output=True,
            timeout=_GIT_TIMEOUT_SECONDS, check=False,
            env={**os.environ, "GIT_NO_LAZY_FETCH": "1", "GIT_NO_REPLACE_OBJECTS": "1"},
        )
    except (OSError, subprocess.SubprocessError):
        raise _GitFailure() from None
    if completed.returncode != 0:
        raise _GitFailure()
    return completed.stdout


def is_git_checkout(repository: str) -> bool:
    try:
        _run_git(repository, ["rev-parse", "--git-dir"])
    except _GitFailure:
        return False
    return True


def _commit_exists(repository: str, source_ref: str) -> bool:
    answer = _run_git(
        repository, ["cat-file", "--batch-check"], stdin=f"{source_ref}^{{commit}}\n".encode("ascii"),
    ).decode("utf-8", "replace").split()
    if not answer:
        raise _GitFailure()
    return answer[-1] != "missing"


def _list_source_tree(repository: str, source_ref: str) -> dict:
    listing = _run_git(repository, ["ls-tree", "-r", "-z", "--full-tree", source_ref, "--", _SRC_PREFIX])
    tree: dict = {}
    for chunk in listing.split(b"\0"):
        if not chunk:
            continue
        meta, _, path = chunk.partition(b"\t")
        fields = meta.decode("ascii").split(" ")
        if len(fields) == 3 and fields[1] == "blob":
            tree[path.decode("utf-8", "surrogateescape")] = fields[2]
    return tree


def _read_blobs(repository: str, blob_ids: Sequence[str]) -> dict:
    unique = list(dict.fromkeys(blob_ids))
    if not unique:
        return {}
    output = _run_git(
        repository, ["cat-file", "--batch"], stdin="".join(f"{blob_id}\n" for blob_id in unique).encode("ascii"),
    )
    contents: dict = {}
    position = 0
    try:
        for blob_id in unique:
            end_of_header = output.index(b"\n", position)
            header = output[position:end_of_header].split()
            if len(header) != 3 or header[1] != b"blob":
                raise _GitFailure()
            size = int(header[2])
            start = end_of_header + 1
            contents[blob_id] = output[start:start + size]
            position = start + size + 1
    except ValueError:
        raise _GitFailure() from None
    return contents


def classify_generation(plane: str, tree_fingerprint: SourceTreeFingerprint, table: Sequence[KnownFingerprint]) -> Identification:
    """The table is read first; only when the fingerprint is not in it does
    the G0 rule apply."""
    fingerprint = tree_fingerprint.fingerprint(plane)
    for row in table:
        if row.plane == plane and row.fingerprint == fingerprint:
            return Identification(row.generation, None)
    if fingerprint.startup_module is None:
        return Identification(None, "startup-module-missing")
    if not fingerprint.checker_references and not tree_fingerprint.has_check_constant:
        return Identification("G0", None)
    return Identification(None, "fingerprint-not-in-table")


def identify_generation(
    repository: str, plane: str, source_ref: str, table: Optional[Sequence[KnownFingerprint]] = None,
) -> Identification:
    """The generation of ``source_ref`` for ``plane``, or ``unknown`` with a
    fixed reason. Reads git objects of ``repository`` only."""
    known = KNOWN_FINGERPRINTS if table is None else table
    try:
        if not _commit_exists(repository, source_ref):
            return Identification(None, "ref-not-found")
        tree = _list_source_tree(repository, source_ref)
        tree_fingerprint = compute_fingerprints(tree, lambda blob_ids: _read_blobs(repository, blob_ids))
    except SourceUnparseable:
        return Identification(None, "source-unparseable")
    except _GitFailure:
        return Identification(None, "git-failed")
    return classify_generation(plane, tree_fingerprint, known)


def first_parent_commits(repository: str, revision_range: str) -> list:
    """The commits of ``revision_range`` along first parents, oldest first."""
    return _run_git(repository, ["rev-list", "--first-parent", "--reverse", revision_range]).decode("ascii").split()


def source_tree_fingerprint_at(repository: str, source_ref: str) -> SourceTreeFingerprint:
    """The fingerprint of ``source_ref``'s source tree (raises
    `SourceUnparseable`; git failures propagate as `RuntimeError`)."""
    try:
        return compute_fingerprints(
            _list_source_tree(repository, source_ref), lambda blob_ids: _read_blobs(repository, blob_ids),
        )
    except _GitFailure:
        raise RuntimeError("git could not read the source tree") from None


# ---------------------------------------------------------------------------
# Formulas per generation.
# ---------------------------------------------------------------------------

#: The pool-size input a frozen generation reads when its env value is unset,
#: empty or not an integer (the value the configuration dataclass carried).
_FROZEN_DEFAULT_CONCURRENCY = 32
#: The thread limit the current generation applies when its env value is
#: unset (the same value ``http.DEFAULT_THREAD_LIMIT`` carries).
_CURRENT_DEFAULT_THREAD_LIMIT = 4

#: The floors of the frozen generations (G1, G2): no process multiplier.
_FROZEN_API_STORE_COUNT = 2
_FROZEN_CONTROLPLANE_FLOOR = 16
_FROZEN_AUDITREADER_FLOOR = 4

#: Which checks a generation carries.
_GENERATION_CHECKS = {
    "G0": (),
    "G1": ("f16",),
    "G2": ("f16", "f18"),
    "G3": ("f16", "f18"),
}

#: The ``CONNECTION LIMIT`` values the platform migrations 0012 and 0014 set,
#: by class of role (a class is identified by grants): (0012, 0014), ``None``
#: where the migration does not touch the class.
_MIGRATION_LIMITS = {
    "api": (68, 132),
    "controlplane": (20, 36),
    "auditreader": (None, 12),
    "application": (36, 68),
}


def _frozen_concurrency(raw: Optional[str]) -> int:
    """The frozen generations' reader: unset, empty or a non-integer text
    gives the default; ``0`` and negatives are kept."""
    if not raw:
        return _FROZEN_DEFAULT_CONCURRENCY
    try:
        return int(raw)
    except ValueError:
        return _FROZEN_DEFAULT_CONCURRENCY


def _pool_input(revision: Revision, generation: str) -> Optional[dict]:
    """The pool-size input of a revision, or a record whose ``x`` is ``None``
    when the current generation's reader refuses the value (the revision then
    fails at startup). ``None`` when the generation reads no such input."""
    if generation == "G0":
        return None
    if generation == "G3":
        declared = revision.thread_limit
        env = {ENV_THREAD_LIMIT: declared} if declared is not None else {}
        try:
            thread_limit = config.thread_limit_from_env(env, ENV_THREAD_LIMIT, _CURRENT_DEFAULT_THREAD_LIMIT)
        except ValueError:
            return {"env": ENV_THREAD_LIMIT, "declared": declared, "applied": None, "x": None}
        return {
            "env": ENV_THREAD_LIMIT, "declared": declared, "applied": thread_limit,
            "x": config.role_pool_size(thread_limit),
        }
    applied = _frozen_concurrency(revision.max_concurrency)
    return {"env": ENV_MAX_CONCURRENCY, "declared": revision.max_concurrency, "applied": applied, "x": applied}


def _role_floors(generation: str, x: int, data_processes: int, control_processes: int) -> dict:
    """The per-class floors of one generation's role connection limit check."""
    if generation == "G3":
        return {
            "api": platform_declarations._API_ROLE_STORE_COUNT * x * data_processes,
            "application": x * data_processes,
            "controlplane": platform_declarations._CONTROLPLANE_ROLE_POOL_FLOOR * control_processes,
            "auditreader": platform_declarations._AUDITREADER_ROLE_POOL_FLOOR * control_processes,
        }
    return {
        "api": _FROZEN_API_STORE_COUNT * x,
        "application": x,
        "controlplane": _FROZEN_CONTROLPLANE_FLOOR,
        "auditreader": _FROZEN_AUDITREADER_FLOOR,
    }


def _headroom_lower_bound(generation: str, x: int, data_processes: int, control_processes: int, registered: int) -> int:
    if generation == "G3":
        return platform_declarations.headroom_lower_bound(
            data_processes=data_processes, control_processes=control_processes,
            platform_pool_floor=platform_declarations._API_ROLE_STORE_COUNT * x,
            application_pair_floor=2 * x,
            control_plane_floor=platform_declarations._CONTROLPLANE_ROLE_POOL_FLOOR,
            registered_applications=registered,
        )
    platform_floor = _FROZEN_API_STORE_COUNT * x
    pair_floor = 2 * x if registered >= 1 else 0
    return data_processes * (platform_floor + pair_floor) + control_processes * _FROZEN_CONTROLPLANE_FLOOR


def _window_limit(role_class: str, current: Optional[int]) -> Optional[int]:
    """The smallest limit the role can carry while the platform migrations
    are being re-applied: ``min(current, 0012, 0014)``, with ``-1`` (no limit)
    left out of the minimum. ``None`` when nothing bounds the role."""
    candidates = []
    if current is not None and current != -1:
        candidates.append(current)
    values = _MIGRATION_LIMITS.get(role_class)
    if values is not None:
        candidates.extend(value for value in values if value is not None)
    return min(candidates) if candidates else None


# ---------------------------------------------------------------------------
# What is read from the database.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DatabaseFacts:
    api_roles: tuple
    controlplane_roles: tuple
    auditreader_roles: tuple
    application_roles: tuple
    role_limits: Mapping
    registered_applications: int
    #: (max_connections, superuser_reserved_connections, reserved_connections),
    #: or None when the database did not answer all three.
    settings: Optional[tuple]
    #: {"data": n, "control": n}, "not-declared" or "unreadable".
    declared_process_ceilings: "dict | str"


def _read_declared_process_ceilings(conn: Any, schema: str) -> "dict | str":
    """The current ``process_ceilings`` declaration, read from its one row: a
    ``{"data": n, "control": n}`` dict, ``"not-declared"`` when the table has no
    such row, ``"unreadable"`` when the read or the value's validation fails.
    Reported only, never judged; the other declaration rows are not read (they
    are absent before the first declaration)."""
    try:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("SELECT value FROM {table} WHERE key = 'process_ceilings'").format(
                    table=sql.Identifier(schema, platform_declarations.TABLE_NAME))
            )
            row = cur.fetchone()
        if row is None:
            return "not-declared"
        ceilings = platform_declarations.validate_process_ceilings_value(
            row[0], schema=schema, ops_module=platform_declarations.PEER_MODULE)
    except (PsycopgError, platform_declarations.PlatformDeclarationError):
        return "unreadable"
    return {"data": ceilings.data, "control": ceilings.control}


def read_database_facts(conn: Any, *, schema: str, role_classes: tuple) -> DatabaseFacts:
    """Reads what the judgments need, through an already-open read-only
    connection. ``role_classes`` is ``(api_roles, controlplane_roles,
    auditreader_roles)`` as the caller discovered them from grants."""
    api_roles, controlplane_roles, auditreader_roles = role_classes
    with conn.cursor() as cur:
        cur.execute(
            sql.SQL(
                "SELECT runtime_role, developer_role FROM {table} "
                "WHERE runtime_role IS NOT NULL AND developer_role IS NOT NULL ORDER BY application_id"
            ).format(table=sql.Identifier(schema, "applications"))
        )
        application_roles = tuple(sorted({role for pair in cur.fetchall() for role in pair}))
    names = sorted({*api_roles, *controlplane_roles, *auditreader_roles, *application_roles})
    with conn.cursor() as cur:
        cur.execute("SELECT rolname, rolconnlimit FROM pg_roles WHERE rolname = ANY(%s)", [names])
        role_limits = dict(cur.fetchall())
    registered = platform_declarations._count_registered_applications(conn, schema)
    try:
        settings: Optional[tuple] = platform_declarations._read_connection_headroom_settings(conn)
    except platform_declarations.PlatformDeclarationError:
        settings = None
    declared = _read_declared_process_ceilings(conn, schema)
    return DatabaseFacts(
        api_roles=tuple(api_roles), controlplane_roles=tuple(controlplane_roles),
        auditreader_roles=tuple(auditreader_roles), application_roles=application_roles,
        role_limits=role_limits, registered_applications=registered, settings=settings,
        declared_process_ceilings=declared,
    )


# ---------------------------------------------------------------------------
# Judgments.
# ---------------------------------------------------------------------------


def _worst(judgments: Sequence[str]) -> str:
    if "blocked" in judgments:
        return "blocked"
    if "unknown" in judgments:
        return "unknown"
    return "confirmed"


def _not_present(present: Optional[bool], judgment: str, reason: str) -> dict:
    return {"present": present, "judgment": judgment, "reason": reason}


def _role_connection_limit_check(
    revision: Revision, generation: str, x: int, data_processes: int, control_processes: int,
    facts: DatabaseFacts,
) -> dict:
    floors_by_class = _role_floors(generation, x, data_processes, control_processes)
    roles: dict = {}
    no_role_of_class = False

    def raise_floor(role: str, role_class: str) -> None:
        floor = floors_by_class[role_class]
        if role not in roles or floor > roles[role][1]:
            roles[role] = (role_class, floor)

    if revision.plane == "data":
        if not facts.api_roles:
            no_role_of_class = True
        for role in facts.api_roles:
            raise_floor(role, "api")
        for role in facts.application_roles:
            roles[role] = ("application", floors_by_class["application"])
    else:
        if not facts.controlplane_roles:
            no_role_of_class = True
        for role in facts.controlplane_roles:
            raise_floor(role, "controlplane")
        if revision.audit_dsn_configured:
            if not facts.auditreader_roles:
                no_role_of_class = True
            for role in facts.auditreader_roles:
                raise_floor(role, "auditreader")
    entries = []
    current_blocked = False
    window_blocked = False
    for role in sorted(roles):
        role_class, floor = roles[role]
        current = facts.role_limits.get(role)
        window = _window_limit(role_class, current) if current is not None else None
        if current is not None and current != -1 and current < floor:
            current_blocked = True
        if window is not None and window < floor:
            window_blocked = True
        entries.append({
            "role": role, "class": role_class, "floor": floor,
            "current_limit": current, "window_limit": window,
        })

    def judged(blocked: bool) -> str:
        if blocked:
            return "blocked"
        return "unknown" if no_role_of_class else "confirmed"

    current_judgment = judged(current_blocked)
    window_judgment = judged(window_blocked)
    judgment = window_judgment
    return {
        "present": True, "judgment": judgment,
        "reason": "no-role-of-class" if judgment == "unknown" else None,
        "window_judgment": window_judgment, "current_judgment": current_judgment,
        "roles": entries,
    }


def _headroom_check(
    generation: str, x: int, data_processes: int, control_processes: int, facts: DatabaseFacts,
) -> dict:
    judged_registrations = max(facts.registered_applications, 1)
    lower_bound = _headroom_lower_bound(generation, x, data_processes, control_processes, judged_registrations)
    without_registrations = _headroom_lower_bound(generation, x, data_processes, control_processes, 0)
    result = {
        "present": True, "judgment": "blocked", "reason": "headroom-settings-missing",
        "registered_applications_judged": judged_registrations,
        "lower_bound": lower_bound, "lower_bound_without_registrations": without_registrations,
        "reserved_total": None, "required": None, "max_connections": None,
    }
    if facts.settings is None:
        return result
    max_connections, superuser_reserved, reserved = facts.settings
    reserved_total = superuser_reserved + reserved
    required = lower_bound + reserved_total
    result.update({
        "judgment": "blocked" if required > max_connections else "confirmed", "reason": None,
        "reserved_total": reserved_total, "required": required, "max_connections": max_connections,
    })
    return result


def evaluate_revision(
    revision: Revision, identification: Identification, facts: DatabaseFacts,
    data_processes: int, control_processes: int,
) -> dict:
    """One revision's entry of the report."""
    base = {"name": revision.name, "plane": revision.plane}
    generation = identification.generation
    if generation is None:
        return {
            **base, "generation": None, "reason": identification.reason, "pool_input": None,
            "f16": _not_present(None, "unknown", "generation-unknown"),
            "f18": _not_present(None, "unknown", "generation-unknown"),
        }
    carried = _GENERATION_CHECKS[generation]
    pool_input = _pool_input(revision, generation)
    entry = {**base, "generation": generation, "reason": None, "pool_input": pool_input}
    for key in ("f16", "f18"):
        if key not in carried:
            entry[key] = _not_present(False, "confirmed", "check-not-in-generation")
    if pool_input is not None and pool_input["x"] is None:
        for key in carried:
            entry[key] = _not_present(True, "blocked", "startup-fails-on-env")
        return entry
    if "f16" in carried:
        entry["f16"] = _role_connection_limit_check(
            revision, generation, pool_input["x"], data_processes, control_processes, facts,
        )
    if "f18" in carried:
        entry["f18"] = _headroom_check(generation, pool_input["x"], data_processes, control_processes, facts)
    return entry


def build_report(
    document: RevisionsDocument, identifications: Mapping, facts: DatabaseFacts,
    data_processes: int, control_processes: int,
) -> dict:
    """The whole report. ``identifications`` maps a revision name to its
    `Identification`."""
    entries = [
        evaluate_revision(revision, identifications[revision.name], facts, data_processes, control_processes)
        for revision in document.revisions
    ]
    settings = facts.settings
    return {
        "overall": _worst([entry[key]["judgment"] for entry in entries for key in ("f16", "f18")]),
        "checks_evaluated": list(CHECKS_EVALUATED),
        "declaration": {
            "current": facts.declared_process_ceilings,
            "proposed": {"control": control_processes, "data": data_processes},
        },
        "database": {
            "max_connections": settings[0] if settings else None,
            "registered_applications": facts.registered_applications,
            "reserved_connections": settings[2] if settings else None,
            "superuser_reserved_connections": settings[1] if settings else None,
        },
        "coverage": dict(document.coverage),
        "known_gaps": list(KNOWN_GAPS),
        "revisions": entries,
    }


def exit_code(report: Mapping) -> int:
    """0 only for ``confirmed``; 2 for a produced judgment that is not."""
    return 0 if report["overall"] == "confirmed" else 2


def identify_revisions(repository: str, document: RevisionsDocument) -> dict:
    """Each revision's `Identification`, reading git once per (plane, ref)."""
    identified: dict = {}
    by_key: dict = {}
    for revision in document.revisions:
        key = (revision.plane, revision.source_ref)
        if key not in by_key:
            by_key[key] = identify_generation(repository, revision.plane, revision.source_ref)
        identified[revision.name] = by_key[key]
    return identified


#: The current-generation (G3) and frozen-generation (G1, G2) fingerprints share
#: two lists of places that name a check function: one call each (G1), two (G2, G3).
_REFERENCES_G1 = (
    ("control_composition.py", "<module>", 1),
    ("control_composition.py", "build_control_service", 1),
    ("main.py", "<module>", 1),
    ("main.py", "build_app", 1),
    ("ops.py", "_verify_declarations_checks", 1),
)
_REFERENCES_G2_G3 = (
    ("control_composition.py", "<module>", 2),
    ("control_composition.py", "build_control_service", 2),
    ("main.py", "<module>", 2),
    ("main.py", "build_app", 2),
    ("ops.py", "_verify_declarations_checks", 2),
)
_DEFAULT_THREAD_LIMIT_DIGEST = "cff2144aa156f1d4a9d57607862cc10d8059a67d013a563a8c10c935fc9eb160"

#: The fingerprints the tool knows, one row per (plane, fingerprint). A row's
#: representative ref is the first commit on the first-parent history of main
#: that carries the fingerprint (``None`` where not yet filled in).
KNOWN_FINGERPRINTS: tuple = (
    KnownFingerprint("data", "G1", "9361f1b1a092333821a72e2de354644f87319d45", Fingerprint(
        platform_declarations="a16796b8d3ed7a64e2c899eaf341b789c63a31c1",
        config="8762f17b094f46549fc78a6c59bec4914ba32f55",
        startup_module="200105bbfc0913b225b2455ffe22055483e04408",
        default_thread_limit=None,
        checker_references=_REFERENCES_G1,
    )),
    KnownFingerprint("control", "G1", "9361f1b1a092333821a72e2de354644f87319d45", Fingerprint(
        platform_declarations="a16796b8d3ed7a64e2c899eaf341b789c63a31c1",
        config="8762f17b094f46549fc78a6c59bec4914ba32f55",
        startup_module="348a766eb355f3ce15c315f17e5e71cdae2210a1",
        default_thread_limit=None,
        checker_references=_REFERENCES_G1,
    )),
    KnownFingerprint("data", "G1", "2152c9418591be7ba635912e160809b4bfe52cb9", Fingerprint(
        platform_declarations="83b04aaaa720283d83937fad6396e7f4ffcec4bc",
        config="8762f17b094f46549fc78a6c59bec4914ba32f55",
        startup_module="200105bbfc0913b225b2455ffe22055483e04408",
        default_thread_limit=None,
        checker_references=_REFERENCES_G1,
    )),
    KnownFingerprint("control", "G1", "2152c9418591be7ba635912e160809b4bfe52cb9", Fingerprint(
        platform_declarations="83b04aaaa720283d83937fad6396e7f4ffcec4bc",
        config="8762f17b094f46549fc78a6c59bec4914ba32f55",
        startup_module="348a766eb355f3ce15c315f17e5e71cdae2210a1",
        default_thread_limit=None,
        checker_references=_REFERENCES_G1,
    )),
    KnownFingerprint("data", "G1", "cab0ee939be1f199b4ee2a067c9350813596b7a9", Fingerprint(
        platform_declarations="fa39f9731cc6de828acb241c897ab585d7caab23",
        config="8762f17b094f46549fc78a6c59bec4914ba32f55",
        startup_module="200105bbfc0913b225b2455ffe22055483e04408",
        default_thread_limit=None,
        checker_references=_REFERENCES_G1,
    )),
    KnownFingerprint("control", "G1", "cab0ee939be1f199b4ee2a067c9350813596b7a9", Fingerprint(
        platform_declarations="fa39f9731cc6de828acb241c897ab585d7caab23",
        config="8762f17b094f46549fc78a6c59bec4914ba32f55",
        startup_module="348a766eb355f3ce15c315f17e5e71cdae2210a1",
        default_thread_limit=None,
        checker_references=_REFERENCES_G1,
    )),
    KnownFingerprint("data", "G1", "0fa46485165853ecaf31a2e946ac61610a801bc3", Fingerprint(
        platform_declarations="fa39f9731cc6de828acb241c897ab585d7caab23",
        config="3ce8f2d8d2565d101ad21aa3fe192d8014d0cc28",
        startup_module="200105bbfc0913b225b2455ffe22055483e04408",
        default_thread_limit=None,
        checker_references=_REFERENCES_G1,
    )),
    KnownFingerprint("control", "G1", "0fa46485165853ecaf31a2e946ac61610a801bc3", Fingerprint(
        platform_declarations="fa39f9731cc6de828acb241c897ab585d7caab23",
        config="3ce8f2d8d2565d101ad21aa3fe192d8014d0cc28",
        startup_module="348a766eb355f3ce15c315f17e5e71cdae2210a1",
        default_thread_limit=None,
        checker_references=_REFERENCES_G1,
    )),
    KnownFingerprint("data", "G1", "623d47c64e082392b33c58ef5d82cdafbe368be4", Fingerprint(
        platform_declarations="3b869ec02f33b8782108a32f2968d104b58253c2",
        config="3ce8f2d8d2565d101ad21aa3fe192d8014d0cc28",
        startup_module="200105bbfc0913b225b2455ffe22055483e04408",
        default_thread_limit=None,
        checker_references=_REFERENCES_G1,
    )),
    KnownFingerprint("control", "G1", "623d47c64e082392b33c58ef5d82cdafbe368be4", Fingerprint(
        platform_declarations="3b869ec02f33b8782108a32f2968d104b58253c2",
        config="3ce8f2d8d2565d101ad21aa3fe192d8014d0cc28",
        startup_module="348a766eb355f3ce15c315f17e5e71cdae2210a1",
        default_thread_limit=None,
        checker_references=_REFERENCES_G1,
    )),
    KnownFingerprint("data", "G1", "f8df32341265b3af832463308df38d025aec1552", Fingerprint(
        platform_declarations="d86d3d554ebbea9ad3f708eef2846ce5facea599",
        config="3ce8f2d8d2565d101ad21aa3fe192d8014d0cc28",
        startup_module="200105bbfc0913b225b2455ffe22055483e04408",
        default_thread_limit=None,
        checker_references=_REFERENCES_G1,
    )),
    KnownFingerprint("control", "G1", "f8df32341265b3af832463308df38d025aec1552", Fingerprint(
        platform_declarations="d86d3d554ebbea9ad3f708eef2846ce5facea599",
        config="3ce8f2d8d2565d101ad21aa3fe192d8014d0cc28",
        startup_module="348a766eb355f3ce15c315f17e5e71cdae2210a1",
        default_thread_limit=None,
        checker_references=_REFERENCES_G1,
    )),
    KnownFingerprint("data", "G1", "43c408c2d91850c1ebd695a7b4e3f718a5dd45f6", Fingerprint(
        platform_declarations="d86d3d554ebbea9ad3f708eef2846ce5facea599",
        config="3ce8f2d8d2565d101ad21aa3fe192d8014d0cc28",
        startup_module="b0efef14db4f40ffeff6b6e52635796f78b36822",
        default_thread_limit=None,
        checker_references=_REFERENCES_G1,
    )),
    KnownFingerprint("data", "G2", "da8d80786ae1786df6e2e9c503abc3439826add1", Fingerprint(
        platform_declarations="ac8bf9b56061961d907950df189b122da8946f74",
        config="3ce8f2d8d2565d101ad21aa3fe192d8014d0cc28",
        startup_module="d6bb599f8c59c73e4a3474921a75468966727d4f",
        default_thread_limit=None,
        checker_references=_REFERENCES_G2_G3,
    )),
    KnownFingerprint("control", "G2", "da8d80786ae1786df6e2e9c503abc3439826add1", Fingerprint(
        platform_declarations="ac8bf9b56061961d907950df189b122da8946f74",
        config="3ce8f2d8d2565d101ad21aa3fe192d8014d0cc28",
        startup_module="3b5a7a89e011f963a3742ce043c84b8498b11e14",
        default_thread_limit=None,
        checker_references=_REFERENCES_G2_G3,
    )),
    KnownFingerprint("data", "G2", "b283f48c78c2319de6a47316bbadf61db2b5751b", Fingerprint(
        platform_declarations="ac8bf9b56061961d907950df189b122da8946f74",
        config="295c60e25ed02b55aa18af1db366356ddf0af649",
        startup_module="d6bb599f8c59c73e4a3474921a75468966727d4f",
        default_thread_limit=None,
        checker_references=_REFERENCES_G2_G3,
    )),
    KnownFingerprint("control", "G2", "b283f48c78c2319de6a47316bbadf61db2b5751b", Fingerprint(
        platform_declarations="ac8bf9b56061961d907950df189b122da8946f74",
        config="295c60e25ed02b55aa18af1db366356ddf0af649",
        startup_module="126acf3ff29170a3c744e1112d88b9a1c0c916e5",
        default_thread_limit=None,
        checker_references=_REFERENCES_G2_G3,
    )),
    KnownFingerprint("data", "G2", "31f981d0ea12ab8a1adf5ad758c6e04deeec97c5", Fingerprint(
        platform_declarations="af8dabed6f875fc6000fd1f5226373015eab4a0b",
        config="295c60e25ed02b55aa18af1db366356ddf0af649",
        startup_module="d6bb599f8c59c73e4a3474921a75468966727d4f",
        default_thread_limit=None,
        checker_references=_REFERENCES_G2_G3,
    )),
    KnownFingerprint("control", "G2", "31f981d0ea12ab8a1adf5ad758c6e04deeec97c5", Fingerprint(
        platform_declarations="af8dabed6f875fc6000fd1f5226373015eab4a0b",
        config="295c60e25ed02b55aa18af1db366356ddf0af649",
        startup_module="126acf3ff29170a3c744e1112d88b9a1c0c916e5",
        default_thread_limit=None,
        checker_references=_REFERENCES_G2_G3,
    )),
    KnownFingerprint("data", "G2", "443a79adddd8674d9c6d700d1b2b052171721600", Fingerprint(
        platform_declarations="af8dabed6f875fc6000fd1f5226373015eab4a0b",
        config="295c60e25ed02b55aa18af1db366356ddf0af649",
        startup_module="2d3e084e21144ca6ec3c3970103e15f9e5a3b0a1",
        default_thread_limit=_DEFAULT_THREAD_LIMIT_DIGEST,
        checker_references=_REFERENCES_G2_G3,
    )),
    KnownFingerprint("control", "G2", "443a79adddd8674d9c6d700d1b2b052171721600", Fingerprint(
        platform_declarations="af8dabed6f875fc6000fd1f5226373015eab4a0b",
        config="295c60e25ed02b55aa18af1db366356ddf0af649",
        startup_module="126acf3ff29170a3c744e1112d88b9a1c0c916e5",
        default_thread_limit=_DEFAULT_THREAD_LIMIT_DIGEST,
        checker_references=_REFERENCES_G2_G3,
    )),
    KnownFingerprint("data", "G3", "41b9fa6b1a709301a424c013aeb9c446912a2a0e", Fingerprint(
        platform_declarations="1a6c6eb15ab2e1fe16a79e12ab14e74f6e59bcc7",
        config="f75dbeef3f21eac41c8d91823c452055e253ca34",
        startup_module="aeb23d8eeef36bd393b3142c08df3e8176ae81e3",
        default_thread_limit=_DEFAULT_THREAD_LIMIT_DIGEST,
        checker_references=_REFERENCES_G2_G3,
    )),
    KnownFingerprint("control", "G3", "41b9fa6b1a709301a424c013aeb9c446912a2a0e", Fingerprint(
        platform_declarations="1a6c6eb15ab2e1fe16a79e12ab14e74f6e59bcc7",
        config="f75dbeef3f21eac41c8d91823c452055e253ca34",
        startup_module="c12b93f3a8037b4c58374f5ef89949a6affe100c",
        default_thread_limit=_DEFAULT_THREAD_LIMIT_DIGEST,
        checker_references=_REFERENCES_G2_G3,
    )),
    KnownFingerprint("data", "G3", None, Fingerprint(
        platform_declarations="f0ffe6803bd560a74e2f1255c3946450a64b68bf",
        config="f75dbeef3f21eac41c8d91823c452055e253ca34",
        startup_module="07c72f2328982d5b04cfecb38295bd9a03dff376",
        default_thread_limit=_DEFAULT_THREAD_LIMIT_DIGEST,
        checker_references=_REFERENCES_G2_G3,
    )),
    KnownFingerprint("control", "G3", None, Fingerprint(
        platform_declarations="f0ffe6803bd560a74e2f1255c3946450a64b68bf",
        config="f75dbeef3f21eac41c8d91823c452055e253ca34",
        startup_module="c12b93f3a8037b4c58374f5ef89949a6affe100c",
        default_thread_limit=_DEFAULT_THREAD_LIMIT_DIGEST,
        checker_references=_REFERENCES_G2_G3,
    )),
)
