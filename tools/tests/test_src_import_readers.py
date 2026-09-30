"""R-77: every import in both peers' `src/` has a live reader, or is on a
recorded allow list.

Design: `docs/work-orders/WORK_ORDER_R37_WP0_INVENTORY_V1.md` §5.46's (5)
("読み手検査の偽陰性(文字列注釈)の手当て") and the rulings it cites (Z5-1
(5), Z5-5, Z5-13), together with §5.45's corrigendum 4 ("読み手を失ったもの
の検査") and corrigendum 8-4 (that check's scope: the importing module
itself, plus any external file -- tests included -- that reads the module
as a facade). Work order: `docs/work-orders/WORK_ORDER_R77_SRC_IMPORT_READERS_V1.md`.
Design record for the intentional facade names this file's allow table
cites: `docs/design/MODULE_REFACT_ARCHITECTURE_V1.md` §10.19's (4).

This file reads each peer's `src/` package with `ast` only; it never
executes an import. For every ``ast.Import``/``ast.ImportFrom`` alias found
anywhere in a module's AST (``ast.walk`` over the whole tree, so a
function-body import or one guarded by ``if TYPE_CHECKING:`` counts the
same as a module-top import), the bound name (``import a.b`` binds ``a``;
``import a.b as c`` binds ``c``; ``from x import y as z`` binds ``z``;
``from x import *`` binds no name and is skipped) is checked for a reader
inside that same module:

  (a) an ``ast.Name`` (Load) occurrence anywhere in the module, including
      the leading name of an attribute reference (``a.b`` counts as a Load
      of ``a``);
  (b) a literal string element of *that module's own* ``__all__``
      assignment;
  (c) a string-literal annotation, whether the WHOLE annotation is a
      quoted string or only PART of a compound (unquoted) one carries a
      nested string constant (a function argument, a function return, or
      an ``AnnAssign``'s annotation, or a nested ``ast.Constant`` found
      anywhere inside it, e.g. the ``"Foo"`` in ``dict[str, "Foo"]``);
      each such string is parsed as an expression (``ast.parse(mode=
      "eval")``) and every ``ast.Name`` found by walking ITS OWN parsed
      tree counts too, including one nested inside a subscript or a union
      (e.g. the ``Foo`` in ``"list[Foo]"``, or the ``Sequence`` in
      ``"Sequence[str] | None"``). A string that fails to parse
      contributes no names;
  (d) the import is itself ``from __future__ import annotations`` -- a
      side-effect import that is always treated as having a reader, and
      is never a candidate for reader-zero.

An import with no reader under (a)-(d) is allowed only when it is listed,
with a reason, in ``ALLOWED_READER_ZERO_IMPORTS`` -- a fixed set of
``(peer, module, name, reason)`` rows. ``test_reader_zero_imports_match_
allow_table`` asserts the *set* of computed reader-zero imports equals the
*set* of allow-table keys exactly, both directions: an unlisted reader-zero
import fails the same as an allow-table row whose import has since gained a
real reader (a dead permission row, since the table is pinned as a row set,
not a count).

Limits (D-5; this file does not attempt more): the flow of data is never
traced -- an import used only to build a value that is itself later
ignored still counts as read. A dynamic import (``importlib``,
``__import__``) or a ``getattr`` lookup is never treated as a reader.
Scope and shadowing are not modelled either: a function-body import that
binds the same name as a module-top import of the same imported name
collapses onto one (peer, module, name) key, and a same-named local
variable or parameter ``Load`` (unrelated to the import) still counts as
that import's reader -- both are false-negative directions (an import
this file calls read might not truly be), never a false positive.
``typing.Literal[...]``'s own slice holds value strings, never a forward
reference, so none of it is ever parsed as an annotation;
``typing.Annotated[...]``'s own slice holds the real type argument first
and opaque metadata after it, so only that first element is treated as an
annotation. Both recognitions go by the bare name actually written at the
`Subscript`, so an aliased import (``from typing import Literal as L``,
then ``L[...]``) is not recognized as `Literal` either -- its value
strings are parsed as if they were forward references, a false-negative
direction (a value string might wrongly count as a reader), never a false
positive. Growing the allow table requires a reason citing either
`MODULE_REFACT_ARCHITECTURE_V1.md` §10.19's (4) record of an intentional
facade re-export, or a facade identity test's own `file:line`.

Scope is pinned to each peer's package directory only (D-1, matching
`tools/tests/test_src_import_cycles.py`'s own scope): the discovered
module set for each peer must equal ``PINNED_MODULES[peer]`` exactly, a
set-equality check rather than a bare count. The pinned list below is
copied verbatim from `test_src_import_cycles.py`'s own list rather than
imported from it (`tools/tests` files do not import each other).

Known gaps (recorded per docs/work-orders/OPERATING_CONDITIONS.md 1.12-71:
a gap that cannot let a contract violation or a Security Invariant breach
through the completion gate is recorded here and not filed in the ledger):
    1. not detected: whether a reader-zero import SHOULD exist at all --
       this file pins the allow table's row set, it cannot judge a row's
       legitimacy.
       why: a row's reason is free text; only its (peer, module, name)
       key participates in the set equality. The `"no record"` reason
       shape exists for rows pinned in `_NO_RECORD_KEYS`, which is empty
       today.
       caught by: a human ruling recorded in the ledger -- R-94 was
       exactly that ruling (both unrecorded imports deleted 2026-09-22,
       leaving the 39 rows and the empty `_NO_RECORD_KEYS` here) -- plus
       code review of any new row's reason.
    2. not detected: dataflow, a dynamic import, scope and shadowing, or
       an aliased `Literal`/`Annotated` -- see "Limits (D-5)" above.
       why: same paragraph; all of them are false-negative directions by
       construction.
       caught by: code review (accepted by D-5).
    3. not detected: any import outside the two peers' `src/` packages
       (tools/, tests/, conformance-tests/).
       why: the module set is pinned to `PINNED_MODULES` (D-1).
       caught by: accepted -- that is the designed scope.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# peer key -> path to that peer's package source root. Never a peer's
# repository directory: a peer's docs/ tree can carry unvetted reference
# `.py` files that must not be scanned.
SRC_ROOTS: dict[str, Path] = {
    "r2db": REPO_ROOT / "r2db-api" / "src" / "r2db_api",
    "mitatedb": REPO_ROOT / "MitateDB-api" / "src" / "mitatedb_api",
}

# Every module discovered under each peer's src/, as a dotted-name list
# pinned verbatim -- copied from `tools/tests/test_src_import_cycles.py`'s
# own `PINNED_MODULES` rather than imported from it (`tools/tests` files
# never import one another). `set(discovered) == set(pinned)` is asserted
# per peer in `test_src_modules_match_pinned_set`, not a count. A change
# that adds a new module under either peer's src/ updates this list in the
# same change set.
PINNED_MODULES: dict[str, frozenset[str]] = {
    "r2db": frozenset(
        {
            "r2db_api",
            "r2db_api.audit",
            "r2db_api.audit_counts",
            "r2db_api.audit_hook",
            "r2db_api.audit_query",
            "r2db_api.auth",
            "r2db_api.backend",
            "r2db_api.capabilities_document",
            "r2db_api.concurrency_slots",
            "r2db_api.contract",
            "r2db_api.control_http",
            "r2db_api.control_main",
            "r2db_api.control_plane",
            "r2db_api.credential_store",
            "r2db_api.delete_confirmation",
            "r2db_api.errors",
            "r2db_api.http",
            "r2db_api.identifier_rules",
            "r2db_api.inmemory_predicate",
            "r2db_api.inmemory_sort",
            "r2db_api.limits",
            "r2db_api.main",
            "r2db_api.mutation_binding",
            "r2db_api.operation_catalog",
            "r2db_api.ops",
            "r2db_api.paging",
            "r2db_api.pg_text_format",
            "r2db_api.pg_timeouts",
            "r2db_api.platform_declarations",
            "r2db_api.platform_upgrades",
            "r2db_api.postgres",
            "r2db_api.postgres_like",
            "r2db_api.postgres_sql",
            "r2db_api.postgres_types",
            "r2db_api.psycopg_counting",
            "r2db_api.request_shape",
            "r2db_api.schema_binding",
            "r2db_api.service",
            "r2db_api.service_results",
            "r2db_api.storage_outcomes",
            "r2db_api.structured",
            "r2db_api.topology",
            "r2db_api.value_nul",
            "r2db_api.value_types",
        }
    ),
    "mitatedb": frozenset(
        {
            "mitatedb_api",
            "mitatedb_api.application_audit",
            "mitatedb_api.audit",
            "mitatedb_api.audit_dispatch",
            "mitatedb_api.audit_hook",
            "mitatedb_api.audit_query",
            "mitatedb_api.auth",
            "mitatedb_api.backend",
            "mitatedb_api.backend_postgres",
            "mitatedb_api.backend_sqlite",
            "mitatedb_api.capabilities_document",
            "mitatedb_api.cell",
            "mitatedb_api.concurrency_slots",
            "mitatedb_api.config",
            "mitatedb_api.constraint_resolution",
            "mitatedb_api.contract",
            "mitatedb_api.control_audit",
            "mitatedb_api.control_auth",
            "mitatedb_api.control_composition",
            "mitatedb_api.control_credential_store_postgres",
            "mitatedb_api.control_http",
            "mitatedb_api.control_main",
            "mitatedb_api.control_plane",
            "mitatedb_api.credential_store_postgres",
            "mitatedb_api.credential_wire",
            "mitatedb_api.delete_confirmation",
            "mitatedb_api.errors",
            "mitatedb_api.field_types",
            "mitatedb_api.http",
            "mitatedb_api.identifiers",
            "mitatedb_api.main",
            "mitatedb_api.operation_catalog",
            "mitatedb_api.ops",
            "mitatedb_api.paging",
            "mitatedb_api.pg_timeouts",
            "mitatedb_api.platform_declarations",
            "mitatedb_api.platform_upgrades",
            "mitatedb_api.pool",
            "mitatedb_api.postgres_reserved_names",
            "mitatedb_api.postgres_sql",
            "mitatedb_api.postgres_types",
            "mitatedb_api.postgres_value_domain",
            "mitatedb_api.psycopg_counting",
            "mitatedb_api.provisional_gate",
            "mitatedb_api.request_binding",
            "mitatedb_api.request_limits",
            "mitatedb_api.request_traversal",
            "mitatedb_api.request_vocabulary",
            "mitatedb_api.service",
            "mitatedb_api.startup_checks",
            "mitatedb_api.surfaces",
        }
    ),
}

# Reader-zero imports allowed to stand, each with a reason (peer, module,
# name, reason). Pinned as a row set, not a count: `test_reader_zero_
# imports_match_allow_table` asserts this set's (peer, module, name) keys
# equal the computed reader-zero set exactly, so a row whose import gains
# a real reader (dead) fails the same as a real reader-zero import that
# isn't listed here. A reason either cites `MODULE_REFACT_ARCHITECTURE_V1.md`
# §10.19's (4) record of an intentional facade re-export, cites a facade
# identity test's own `file:line`, or -- only for a row whose key is
# pinned in _NO_RECORD_KEYS below (currently empty) -- reads "no record".
ALLOWED_READER_ZERO_IMPORTS: frozenset[tuple[str, str, str, str]] = frozenset(
    {
        (
            "r2db",
            "r2db_api.postgres",
            "_escape_like_literal",
            "facade re-export (MODULE_REFACT_ARCHITECTURE_V1.md §10.19 (4)); "
            "facade identity test r2db-api/tests/test_postgres.py:1575 "
            "test_escape_like_literal_leaf_preserves_facade_and_escape_order",
        ),
        (
            "r2db",
            "r2db_api.postgres",
            "_FIELD_TYPE_SQL",
            "facade re-export (MODULE_REFACT_ARCHITECTURE_V1.md §10.19 (4)); "
            "facade identity test r2db-api/tests/test_postgres.py:1812 "
            "test_field_type_sql_json_entry_maps_to_jsonb_without_keyerror",
        ),
        (
            "r2db",
            "r2db_api.postgres",
            "_JSONB_SQL",
            "facade re-export (MODULE_REFACT_ARCHITECTURE_V1.md §10.19 (4)); "
            "facade identity test r2db-api/tests/test_postgres.py:1812 "
            "test_field_type_sql_json_entry_maps_to_jsonb_without_keyerror",
        ),
        (
            "r2db",
            "r2db_api.postgres",
            "ConstraintPatch",
            "facade identity test r2db-api/tests/test_foundation.py:3265 "
            "test_schema_binding_leaf_preserves_structured_facade "
            "(not itself named in MODULE_REFACT_ARCHITECTURE_V1.md §10.19 (4))",
        ),
        (
            "r2db",
            "r2db_api.structured",
            "RESET_CONTROL_CREDENTIALS",
            "facade identity test r2db-api/tests/test_foundation.py:679 "
            "test_delete_confirmation_leaf_preserves_structured_facade",
        ),
        (
            "r2db",
            "r2db_api.structured",
            "_MAX_REVISION_DIGITS",
            "facade identity test r2db-api/tests/test_foundation.py:679 "
            "test_delete_confirmation_leaf_preserves_structured_facade",
        ),
        (
            "r2db",
            "r2db_api.structured",
            "_PHRASE_MAX_LENGTH",
            "facade identity test r2db-api/tests/test_foundation.py:679 "
            "test_delete_confirmation_leaf_preserves_structured_facade",
        ),
        (
            "r2db",
            "r2db_api.structured",
            "_canonical_where_json",
            "facade identity test r2db-api/tests/test_foundation.py:679 "
            "test_delete_confirmation_leaf_preserves_structured_facade",
        ),
        (
            "r2db",
            "r2db_api.structured",
            "_where_digest16",
            "facade identity test r2db-api/tests/test_foundation.py:679 "
            "test_delete_confirmation_leaf_preserves_structured_facade",
        ),
        (
            "r2db",
            "r2db_api.structured",
            "delete_credential_confirmation_phrase",
            "facade identity test r2db-api/tests/test_foundation.py:679 "
            "test_delete_confirmation_leaf_preserves_structured_facade",
        ),
        (
            "r2db",
            "r2db_api.structured",
            "revoke_last_control_credential_confirmation_phrase",
            "facade identity test r2db-api/tests/test_foundation.py:679 "
            "test_delete_confirmation_leaf_preserves_structured_facade",
        ),
        (
            "r2db",
            "r2db_api.structured",
            "IDENTIFIER",
            "facade identity test r2db-api/tests/test_foundation.py:1044 "
            "test_identifier_rules_leaf_preserves_structured_facade_and_length_bound",
        ),
        (
            "r2db",
            "r2db_api.structured",
            "_RESERVED_ENTITY_NAMES",
            "facade identity test r2db-api/tests/test_foundation.py:1044 "
            "test_identifier_rules_leaf_preserves_structured_facade_and_length_bound",
        ),
        (
            "r2db",
            "r2db_api.structured",
            "_RESERVED_PREFIX",
            "facade identity test r2db-api/tests/test_foundation.py:1044 "
            "test_identifier_rules_leaf_preserves_structured_facade_and_length_bound",
        ),
        (
            "r2db",
            "r2db_api.structured",
            "_predicate_text",
            "facade identity test r2db-api/tests/test_foundation.py:1793 "
            "test_inmemory_predicate_leaf_preserves_structured_facade_and_wildcard_escape",
        ),
        (
            "r2db",
            "r2db_api.structured",
            "_wildcard_pattern",
            "facade identity test r2db-api/tests/test_foundation.py:1793 "
            "test_inmemory_predicate_leaf_preserves_structured_facade_and_wildcard_escape",
        ),
        (
            "r2db",
            "r2db_api.structured",
            "_JSON_TYPE_RANK",
            "facade identity test r2db-api/tests/test_foundation.py:2234 "
            "test_inmemory_sort_leaf_preserves_structured_facade_and_null_rank",
        ),
        (
            "r2db",
            "r2db_api.structured",
            "_sort_key",
            "facade identity test r2db-api/tests/test_foundation.py:2234 "
            "test_inmemory_sort_leaf_preserves_structured_facade_and_null_rank",
        ),
        (
            "r2db",
            "r2db_api.structured",
            "parse_predicate",
            "facade identity test r2db-api/tests/test_foundation.py:3194 "
            "test_mutation_binding_leaf_preserves_structured_facade",
        ),
        (
            "r2db",
            "r2db_api.structured",
            "MAX_ORDER_BY_FIELDS",
            "facade identity test r2db-api/tests/test_foundation.py:2274 "
            "test_paging_leaf_preserves_structured_facade",
        ),
        (
            "r2db",
            "r2db_api.structured",
            "MAX_PAGE_SIZE",
            "facade identity test r2db-api/tests/test_foundation.py:2274 "
            "test_paging_leaf_preserves_structured_facade",
        ),
        (
            "r2db",
            "r2db_api.structured",
            "_float8out_text",
            "facade identity test r2db-api/tests/test_foundation.py:1903 "
            "test_pg_text_format_leaf_preserves_structured_facade_and_postgres_text_forms",
        ),
        (
            "r2db",
            "r2db_api.structured",
            "_jsonb_numeric_text",
            "facade identity test r2db-api/tests/test_foundation.py:1903 "
            "test_pg_text_format_leaf_preserves_structured_facade_and_postgres_text_forms",
        ),
        (
            "r2db",
            "r2db_api.structured",
            "_jsonb_scalar_text",
            "facade identity test r2db-api/tests/test_foundation.py:1903 "
            "test_pg_text_format_leaf_preserves_structured_facade_and_postgres_text_forms",
        ),
        (
            "r2db",
            "r2db_api.structured",
            "_jsonb_text",
            "facade identity test r2db-api/tests/test_foundation.py:1903 "
            "test_pg_text_format_leaf_preserves_structured_facade_and_postgres_text_forms",
        ),
        (
            "r2db",
            "r2db_api.structured",
            "_contains_nul",
            "facade identity test r2db-api/tests/test_foundation.py:1894 "
            "test_contains_nul_leaf_preserves_structured_facade_and_nested_detection",
        ),
        (
            "r2db",
            "r2db_api.structured",
            "_INT64_MAX",
            "facade identity test r2db-api/tests/test_foundation.py:2296 "
            "test_value_types_leaf_preserves_structured_facade",
        ),
        (
            "r2db",
            "r2db_api.structured",
            "_INT64_MIN",
            "facade identity test r2db-api/tests/test_foundation.py:2296 "
            "test_value_types_leaf_preserves_structured_facade",
        ),
        (
            "r2db",
            "r2db_api.structured",
            "_TEXT_ONLY_OPERATORS",
            "facade identity test r2db-api/tests/test_foundation.py:2296 "
            "test_value_types_leaf_preserves_structured_facade",
        ),
        (
            "r2db",
            "r2db_api.structured",
            "_validate_wildcard_pattern",
            "facade identity test r2db-api/tests/test_foundation.py:2296 "
            "test_value_types_leaf_preserves_structured_facade",
        ),
        (
            "mitatedb",
            "mitatedb_api.backend_postgres",
            "_INT_DOMAIN_RANGES",
            "facade re-export, marked in a comment at "
            "MitateDB-api/src/mitatedb_api/backend_postgres.py:97-98 "
            "(MODULE_REFACT_ARCHITECTURE_V1.md §10.19 (4))",
        ),
        (
            "mitatedb",
            "mitatedb_api.backend_postgres",
            "_check_domain",
            "facade re-export, marked in a comment at "
            "MitateDB-api/src/mitatedb_api/backend_postgres.py:97-98 "
            "(MODULE_REFACT_ARCHITECTURE_V1.md §10.19 (4))",
        ),
        (
            "mitatedb",
            "mitatedb_api.backend_postgres",
            "_RESERVED_EXACT",
            "facade re-export (MODULE_REFACT_ARCHITECTURE_V1.md §10.19 (4)); "
            "facade identity test MitateDB-api/tests/test_postgres.py:1661 "
            "test_postgres_reserved_names_leaf_preserves_backend_postgres_facade",
        ),
        (
            "mitatedb",
            "mitatedb_api.backend_postgres",
            "_RESERVED_PREFIX",
            "facade re-export (MODULE_REFACT_ARCHITECTURE_V1.md §10.19 (4)); "
            "facade identity test MitateDB-api/tests/test_postgres.py:1661 "
            "test_postgres_reserved_names_leaf_preserves_backend_postgres_facade",
        ),
        (
            "mitatedb",
            "mitatedb_api.cell",
            "_canonical_where_json",
            "facade identity test MitateDB-api/tests/test_foundation.py:940 "
            "test_delete_confirmation_leaf_preserves_cell_facade_and_phrase_shape",
        ),
        (
            "mitatedb",
            "mitatedb_api.cell",
            "_deny_provisional_field",
            "facade identity test MitateDB-api/tests/test_denial_details_and_request_id.py:966 "
            "test_provisional_gate_leaf_preserves_cell_facade",
        ),
        (
            "mitatedb",
            "mitatedb_api.cell",
            "_as_traversable",
            "facade identity test MitateDB-api/tests/test_application_plane_limits.py:404 "
            "test_as_traversable_leaf_preserves_cell_facade_and_dataclass_normalization",
        ),
        (
            "mitatedb",
            "mitatedb_api.main",
            "build_control_service",
            "intentional facade re-export: MitateDB-api/src/mitatedb_api/main.py:593 "
            "re-export comment; MitateDB-api/tests/test_control_main.py:6",
        ),
    }
)

# Imported names whose only reader in their own module is a string-literal
# annotation (D-2 (c)) -- the not-vacuous check for that reader kind
# (§1.5's 32). Pinned as a row set.
STRING_ANNOTATION_ONLY_READERS: frozenset[tuple[str, str, str]] = frozenset(
    {
        ("r2db", "r2db_api.postgres", "BoundMutation"),
        ("mitatedb", "mitatedb_api.audit_query", "Sequence"),
        ("mitatedb", "mitatedb_api.http", "Iterator"),
        # R-101 WP-1: `PostgresApplicationAuditSink._connect`'s own
        # `psycopg.connect(...)` call (the module's only other reader of
        # this import) was replaced with `psycopg_counting.CountingConnection.
        # connect(...)`, so `psycopg` itself is now read only inside this
        # module's own string-literal annotations (`"psycopg.Connection"`
        # on `_connect`/`_fold_closed_connection_stats`).
        ("mitatedb", "mitatedb_api.application_audit", "psycopg"),
    }
)


def _dotted_name(path: Path, src_root: Path) -> str:
    """`path`'s package-relative dotted name; `__init__.py` names its package."""
    parts = path.relative_to(src_root).with_suffix("").parts
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join((src_root.name, *parts))


def _discover_modules(src_root: Path) -> dict[str, Path]:
    """dotted name -> file path for every `.py` file under `src_root`."""
    return {_dotted_name(p, src_root): p for p in sorted(src_root.rglob("*.py"))}


def _imported_bindings(tree: ast.AST) -> list[tuple[str, bool, int]]:
    """`(bound_name, is_future_annotations_import, lineno)` for every
    import alias found anywhere in `tree` (`ast.walk`, so a function-body
    import or one guarded by `if TYPE_CHECKING:` counts the same as a
    module-top import). `from x import *` binds no name and contributes
    nothing. `lineno` is the alias's own line (Python resolves a
    multi-line `from x import (a,` `b)` to each alias's real line); it is
    used only to locate a violation in a failure message and plays no part
    in the reader determination itself.
    """
    bindings: list[tuple[str, bool, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                bindings.append((alias.asname or alias.name.split(".")[0], False, alias.lineno))
        elif isinstance(node, ast.ImportFrom):
            is_future = node.module == "__future__"
            for alias in node.names:
                if alias.name == "*":
                    continue
                bindings.append((alias.asname or alias.name, is_future, alias.lineno))
    return bindings


def _string_annotation_names(text: str) -> set[str]:
    """D-2 (c)'s core: `text` parsed as an expression, every `ast.Name`
    found by walking the parsed tree (so a name nested inside a subscript
    or a union, e.g. `Sequence` in `"Sequence[str] | None"`, counts). A
    string that fails to parse contributes no names.
    """
    try:
        parsed = ast.parse(text, mode="eval")
    except SyntaxError:
        return set()
    return {node.id for node in ast.walk(parsed) if isinstance(node, ast.Name)}


def _string_constant(node: "ast.expr | None") -> "str | None":
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _subscript_base_name(value: ast.expr) -> "str | None":
    """The bare name a `Subscript`'s own `.value` names, whether written
    unqualified (`Literal`) or qualified (`typing.Literal`)."""
    if isinstance(value, ast.Name):
        return value.id
    if isinstance(value, ast.Attribute):
        return value.attr
    return None


def _subscript_elements(node: ast.expr) -> list[ast.expr]:
    """A `Subscript`'s own slice, as a list of its elements (a `Tuple`
    slice's own `elts`, or the bare slice itself as the sole element)."""
    if isinstance(node, ast.Tuple):
        return list(node.elts)
    return [node]


def _annotation_string_names(annotation: "ast.expr | None") -> set[str]:
    """Every name read via a string-literal `ast.Constant` anywhere inside
    `annotation` (D-2 (c)) -- not only when the whole annotation is itself
    a bare string, but also a *compound* (unquoted) annotation carrying a
    nested string constant, e.g. the `Foo` in `dict[str, "Foo"]` (the
    outer `dict[str, ...]` is not itself a string, but this still finds
    the nested `"Foo"` `ast.Constant` inside its `Subscript`). Two
    exceptions descend no further: `typing.Literal[...]`'s own slice
    holds value strings, never a forward reference, so none of it is
    parsed; `typing.Annotated[...]`'s own slice holds the real type
    argument first and opaque metadata after it, so only its first
    element is parsed (as an ordinary annotation, recursively) and the
    rest is skipped."""
    if annotation is None:
        return set()
    names: set[str] = set()

    def _walk(node: ast.AST) -> None:
        if isinstance(node, ast.Subscript):
            base = _subscript_base_name(node.value)
            if base == "Literal":
                return
            if base == "Annotated":
                elements = _subscript_elements(node.slice)
                if elements:
                    _walk(elements[0])
                return
        text = _string_constant(node)
        if text is not None:
            names.update(_string_annotation_names(text))
        for child in ast.iter_child_nodes(node):
            _walk(child)

    _walk(annotation)
    return names


def _annotation_reader_names(tree: ast.AST) -> set[str]:
    """D-2 (c): names read via a string-literal annotation anywhere in
    `tree` -- a function argument, a function return, or an `AnnAssign`,
    including one nested inside a compound annotation (see
    `_annotation_string_names`).
    """
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = node.args
            candidates = [*args.posonlyargs, *args.args, *args.kwonlyargs]
            if args.vararg is not None:
                candidates.append(args.vararg)
            if args.kwarg is not None:
                candidates.append(args.kwarg)
            for arg in candidates:
                names |= _annotation_string_names(arg.annotation)
            names |= _annotation_string_names(node.returns)
        elif isinstance(node, ast.AnnAssign):
            names |= _annotation_string_names(node.annotation)
    return names


def _name_load_readers(tree: ast.AST) -> set[str]:
    """D-2 (a): every `ast.Name` (Load) occurrence anywhere in `tree`,
    including the leading name of an attribute reference (`a.b` is a Load
    of `a`)."""
    return {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
    }


def _all_literal_readers(tree: ast.AST) -> set[str]:
    """D-2 (b): the literal string elements of this module's own
    `__all__`, however it is bound -- a plain `Assign`, an annotated
    `AnnAssign` (`__all__: list[str] = [...]`), or an augmenting
    `__all__ += [...]` `AugAssign` (all three name the same list; the real
    src under scan uses only the plain form, but nothing rules the other
    two out)."""
    names: set[str] = set()
    for node in ast.walk(tree):
        value: "ast.expr | None" = None
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "__all__" for target in node.targets
        ):
            value = node.value
        elif (
            isinstance(node, (ast.AnnAssign, ast.AugAssign))
            and isinstance(node.target, ast.Name)
            and node.target.id == "__all__"
        ):
            value = node.value
        if value is None:
            continue
        if isinstance(value, (ast.List, ast.Tuple, ast.Set)):
            for elt in value.elts:
                text = _string_constant(elt)
                if text is not None:
                    names.add(text)
    return names


def _scan() -> tuple[
    dict[str, dict[str, Path]],
    set[tuple[str, str, str]],
    set[tuple[str, str, str]],
    dict[tuple[str, str, str], str],
]:
    """Discovers every module (D-1) and returns `(modules_by_peer,
    reader_zero, string_annotation_only, locations)`:

    - `modules_by_peer`: peer -> {dotted name: path}.
    - `reader_zero`: `(peer, module, name)` for every imported name with no
      reader under (a)+(b)+(c), excluding a `from __future__ import
      annotations` import itself (d).
    - `string_annotation_only`: the subset of readers whose only source is
      (c) -- absent from (a)+(b), present via (c).
    - `locations`: `(peer, module, name)` -> `"<repo-relative path>:<line>
      <name>"` for that import's own first alias occurrence -- used only
      to make a failure message locatable, never part of a determination.
    """
    modules_by_peer = {peer: _discover_modules(root) for peer, root in SRC_ROOTS.items()}
    reader_zero: set[tuple[str, str, str]] = set()
    string_annotation_only: set[tuple[str, str, str]] = set()
    locations: dict[tuple[str, str, str], str] = {}
    for peer, modmap in modules_by_peer.items():
        for dotted, path in modmap.items():
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            bindings = _imported_bindings(tree)
            if not bindings:
                continue
            readers_ab = _name_load_readers(tree) | _all_literal_readers(tree)
            readers_c = _annotation_reader_names(tree)
            rel_path = path.relative_to(REPO_ROOT)
            for name, is_future, lineno in bindings:
                if is_future:
                    continue
                key = (peer, dotted, name)
                locations.setdefault(key, f"{rel_path}:{lineno} {name}")
                if name in readers_ab:
                    continue
                if name in readers_c:
                    string_annotation_only.add(key)
                    continue
                reader_zero.add(key)
    return modules_by_peer, reader_zero, string_annotation_only, locations


def test_src_modules_match_pinned_set() -> None:
    assert set(SRC_ROOTS) == set(PINNED_MODULES) == {"r2db", "mitatedb"}

    modules_by_peer = {peer: _discover_modules(root) for peer, root in SRC_ROOTS.items()}
    mismatches: list[str] = []
    for peer, pinned in PINNED_MODULES.items():
        discovered = set(modules_by_peer[peer])
        if discovered != pinned:
            mismatches.append(f"{peer}: discovered {sorted(discovered)} != pinned {sorted(pinned)}")
    assert not mismatches, "\n".join(mismatches)

    total_modules = sum(len(m) for m in modules_by_peer.values())
    assert total_modules >= 1, "no modules discovered under either peer's src/"


def test_string_annotation_only_readers_match_pin() -> None:
    _, _, string_annotation_only, _ = _scan()
    assert string_annotation_only == set(STRING_ANNOTATION_ONLY_READERS)
    assert len(string_annotation_only) >= 1, (
        "no import is read only through a string-literal annotation -- the "
        "D-2 (c) check would be untested"
    )


_REASON_FILE_LINE_RE = re.compile(r"\.py:\d+")

# (peer, module, name) keys allowed a bare "no record" reason (no
# `MODULE_REFACT_ARCHITECTURE_V1.md` citation, no `file.py:line`) --
# pinned as a row set (currently empty) so a new row cannot quietly claim
# the same excuse without being added here first.
_NO_RECORD_KEYS: frozenset[tuple[str, str, str]] = frozenset()


def _reason_is_well_formed(key: tuple[str, str, str], reason: str) -> bool:
    """An allow-table reason must cite something checkable: `MODULE_REFACT_
    ARCHITECTURE_V1.md`'s own record, a `file.py:line` a reader can open,
    or -- only for a row whose key is pinned in `_NO_RECORD_KEYS` --
    start with `"no record"`."""
    if not reason.strip():
        return False
    if "MODULE_REFACT_ARCHITECTURE_V1.md" in reason:
        return True
    if _REASON_FILE_LINE_RE.search(reason):
        return True
    return reason.startswith("no record") and key in _NO_RECORD_KEYS


def test_reader_zero_imports_match_allow_table() -> None:
    no_record_rows = {
        (peer, module, name)
        for peer, module, name, reason in ALLOWED_READER_ZERO_IMPORTS
        if reason.startswith("no record")
    }
    assert _NO_RECORD_KEYS == no_record_rows, (
        f"_NO_RECORD_KEYS {sorted(_NO_RECORD_KEYS)} != the allow table's own "
        f"\"no record\" rows {sorted(no_record_rows)}"
    )

    malformed = sorted(
        f"{peer}/{module}/{name}: {reason!r}"
        for peer, module, name, reason in ALLOWED_READER_ZERO_IMPORTS
        if not _reason_is_well_formed((peer, module, name), reason)
    )
    assert not malformed, "allow-table rows with an unverifiable reason:\n" + "\n".join(malformed)

    _, reader_zero, _, locations = _scan()
    allowed_keys = {(peer, module, name) for peer, module, name, _reason in ALLOWED_READER_ZERO_IMPORTS}
    unlisted = sorted(locations.get(key, f"{key[0]}/{key[1]} {key[2]}") for key in reader_zero - allowed_keys)
    dead = sorted(locations.get(key, f"{key[0]}/{key[1]} {key[2]}") for key in allowed_keys - reader_zero)
    assert not unlisted and not dead, (
        f"reader-zero imports missing from the allow table: {unlisted}\n"
        f"allow-table rows whose import now has a reader (dead permission rows): {dead}"
    )
