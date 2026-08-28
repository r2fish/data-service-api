"""Common conformance adapter port.

This module is the *port* half of the port/plug split described in
`docs/design/CONFORMANCE_ADAPTER_V1.md`. It is owned by the common
repository (design principle 1); each peer owns the *plug* that implements
`ConformanceAdapter` against its own runtime:

  - `r2db-api/conformance/adapter.py`      (module `conformance_adapter_r2db`)
  - `MitateDB-api/conformance/adapter.py`  (module `conformance_adapter_mitatedb`)

NORMATIVE SURFACE (design section 4): the value types (`CredentialHandle`,
`ScopeView`, `ConformanceDenial`), `Fixture`, `TamperVector`, the
`ConformanceAdapter` ABC, and the `MUST_COVER_*` constants below are
normative. Peer adapters are written against these exact names and
signatures; do not rename, reorder, or add required parameters to any of
them without a coordinated design revision.

Everything else in this file (helper functions, non-normative constants) is
shared plumbing that both the common suite and peer adapters may use, but is
not part of the frozen contract.
"""
from __future__ import annotations

import inspect
import json
import uuid
from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Contract-derived data. Never hardcode a copy of these; always read the
# contract document at runtime (design section 6.1, and CLAUDE.md's
# development-order rule that implementations follow the common contract,
# not the reverse).
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = REPO_ROOT / "spec" / "data-service-api.v1.json"


def load_contract() -> dict:
    """Load the common contract document fresh from disk on every call."""
    return json.loads(CONTRACT_PATH.read_text())


def load_contract_error_codes() -> frozenset[str]:
    """The authoritative set of common error codes, read at runtime from
    ``spec/data-service-api.v1.json``'s ``errors.codes``. ``classify()`` and
    every ``ConformanceDenial.code`` must be a member of this set (design
    section 6.1). Never maintain a hardcoded copy of this list."""
    return frozenset(load_contract()["errors"]["codes"])


# ---------------------------------------------------------------------------
# 4.1 Value types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CredentialHandle:
    credential_ref: str  # opaque control-plane reference to the credential
    application_id: str
    role: str  # "runtime" | "developer"
    secret: str  # synthetic test value only. Never a real credential.


@dataclass(frozen=True)
class ScopeView:
    application_id: str
    role: str


class ConformanceDenial(Exception):
    """Raised by adapter operations when the peer implementation denies an
    operation.

    Per design section 4.1, this exception intentionally does NOT carry the
    native exception's message text: neither as a constructor argument nor
    baked into its own ``str()``. Carrying it would let a verbatim payload
    reflection slip past assertions made directly against the
    ``ConformanceDenial`` itself.

    Adapters should chain the native exception using standard Python
    exception chaining: ``raise ConformanceDenial(...) from native_exc``.
    That is the single shared mechanism (`native_cause_of`, below) both the
    suite and adapters use to reach the native exception for the non-echo
    check (design section 5.2 item 6 / section 6.3), which must run
    *before* -- i.e. independently of -- any interpretation performed by
    ``classify()``.
    """

    def __init__(self, code: str, adapter: str, native_type: str = "") -> None:
        self.code = code
        self.adapter = adapter
        self.native_type = native_type
        super().__init__(
            f"ConformanceDenial(code={code!r}, adapter={adapter!r}, native_type={native_type!r})"
        )


class PayloadNotExpressible(Exception):
    """Raised by an identifier/value probe when a payload cannot be placed in
    that position *at the harness level* -- not because the peer rejected it.

    The motivating case is an unhashable payload (``[]``, ``{}``) in a
    position that is a Python mapping key: the request cannot even be
    constructed, so nothing about the peer's validation is being observed.

    This must never be used to excuse a peer that failed to reject a payload
    it did receive. The suite treats it as "this position could not observe
    this payload" and separately requires every payload to be denied in at
    least one position (design principle 4: uncertainty must not silently
    become permission).
    """

    def __init__(self, position: str, payload: Any, reason: str) -> None:
        self.position = position
        self.payload = payload
        self.reason = reason
        super().__init__(f"payload not expressible at position {position!r}: {reason}")


class SurfaceAbsent(Exception):
    """Raised by a port operation whose natural return type cannot double as
    a sentinel (unlike `catalog_document`, which returns
    `CATALOG_SURFACE_ABSENT`) when the peer's public surface has no real
    call that could plausibly receive the request at all.

    This is deliberately distinct from `ConformanceDenial`: a
    `ConformanceDenial` means the peer *received* the request through a
    real, present entry point and refused it (design section 4.1's own
    principle, restated in docs/design/CONFORMANCE_CONDITIONS_V1_1.md
    section 11.2 -- "an adapter denying an operation without presenting it
    to the peer at all is exactly what design principle 4 forbids"). This
    exception is for the narrower, honest case where no such entry point
    exists to present the request to in the first place -- confirmed by
    source inspection of the peer's own public methods, never assumed.
    Introduced for the port v1.2 additions
    (docs/design/CONFORMANCE_ADAPTER_V1.md section 12,
    docs/design/R2DB_CCR13_STORAGE_V1.md section 4 correction M-7):
    `create_unique_index` and `attempt_mutation`'s `expected_revision`, both
    of which return `None`/`int` and so cannot reuse `CATALOG_SURFACE_ABSENT`
    's string-sentinel approach without colliding with a genuine result.

    Unlike `PayloadNotExpressible` (a harness-level "could not observe this"
    outcome the suite accepts as a bare exception), a claim of surface
    absence is exactly the kind of claim design principle 4 ("uncertainty
    must not silently become permission") says must not be taken on its
    word: raising this exception is not itself proof of anything. Per
    design section 4.3's `structurally_absent` mechanism, this exception
    therefore MUST carry the same `surface`/`forbidden_parameters` pair a
    `structurally_absent` `TamperVector` carries, so a consumer can run
    `signature_forbids_parameters(surface, forbidden_parameters)` and
    confirm the claim independently rather than trusting the plug. A
    consumer (a future C-17/C-18 test) MUST NOT catch this exception and
    convert it to a skip or a pass without performing that check --
    swallowing it unchecked is exactly the "silent permission of the
    unknown" design principle 4 forbids, applied to this exception instead
    of to a bare `except: pass`.

    Must never be raised to excuse a peer that genuinely received and
    mishandled a request -- that is what `ConformanceDenial` and the
    suite's own assertions are for.
    """

    def __init__(
        self,
        adapter: str,
        operation: str,
        reason: str,
        *,
        surface: Sequence[Callable],
        forbidden_parameters: Sequence[str],
    ) -> None:
        if not surface:
            raise ValueError("SurfaceAbsent requires a non-empty surface to inspect")
        if not forbidden_parameters:
            raise ValueError("SurfaceAbsent requires non-empty forbidden_parameters to check for")
        self.adapter = adapter
        self.operation = operation
        self.reason = reason
        self.surface = tuple(surface)
        self.forbidden_parameters = tuple(forbidden_parameters)
        super().__init__(f"{adapter}: {operation} has no surface on this peer: {reason}")


# Sentinel for `ConformanceAdapter.delete(..., confirmation=...)`.
#
# Peers legitimately spell their destructive-confirmation token differently
# (`r2db-api` requires the literal "DELETE"; `MitateDB-api` uses a boolean
# `confirm`). The port therefore normalizes *intent*, not spelling:
#
#   confirmation=None                -> supply NO confirmation to the peer
#   confirmation=VALID_CONFIRMATION  -> supply whatever token this peer requires
#   confirmation=<any other string>  -> pass that string through verbatim
#
# `destructive` is always passed through faithfully. An adapter MUST NOT
# upgrade a non-destructive/unconfirmed request into a confirmed destructive
# one: doing so makes the port's destructive semantics decorative, hides
# whether the peer enforces SI-09, and would let a scope regression execute a
# real destructive delete during a negative test.
VALID_CONFIRMATION = "<adapter-supplies-peer-required-confirmation>"

# Returned by `classify()` when an adapter cannot map a native exception to a
# common contract code. It is deliberately NOT a member of the contract's
# `errors.codes`, so the suite's code-membership assertion fails loudly.
# An unclassifiable native failure (a raw storage-driver error, a TypeError,
# an unhandled crash) is a finding, not a denial: laundering it into
# VALIDATION_FAILED would let a peer that crashed on an injection payload
# pass the very test meant to catch that.
UNCLASSIFIED = "UNCLASSIFIED_NATIVE_FAILURE"

# Sentinel for `ConformanceAdapter.catalog_document()` (docs/design/
# CONFORMANCE_CONDITIONS_V1_1.md section 2). A peer either has a discovery
# surface that answers (returns a real document) or denies (raises
# `ConformanceDenial`), or it has no catalog operation on its public surface
# at all -- structurally, not merely "not implemented today" in a way that
# could still raise a classifiable denial. This sentinel is reserved for
# that third case. It is deliberately NOT a dict an adapter could confuse
# with a real (possibly empty) `CatalogDocument`, and deliberately NOT
# something an adapter fabricates on the peer's behalf (design principle:
# "adapter は peer の不足を埋めない") -- it is only ever returned when the
# peer genuinely has no callable to invoke for this.
CATALOG_SURFACE_ABSENT = "<peer-has-no-catalog-surface>"


def native_cause_of(denial: BaseException) -> BaseException | None:
    """Return the native exception chained onto a ``ConformanceDenial`` via
    ``raise ... from native_exc``. Used only for the non-echo inspection
    described in design sections 4.1 / 5.2 item 6 / 6.3 -- never to recover
    message text for assertions about denial semantics."""
    return denial.__cause__


_MIN_ECHO_PAYLOAD_LEN = 4


def assert_no_payload_echo(native_exc: BaseException | None, payload: Any, *, context: str = "") -> None:
    """Fail loudly if the native exception's ``str()`` contains ``payload``
    verbatim (design section 5.2 item 6 / section 6.3).

    Safe field-level diagnostics ("field 'x' failed validation") are
    contract-allowed; verbatim reflection of the attack payload is not.
    This inspects the *native* exception, independent of and prior to any
    ``classify()``-driven interpretation, per design section 4.1.
    """
    if native_exc is None:
        return
    text = str(native_exc)
    if not text:
        return
    # Only string payloads are checked, and only those long enough that a
    # substring hit means real reflection rather than coincidence. Checking
    # repr() of non-string payloads (0, 1, True) or of one-character
    # payloads ("*") produces false positives against legitimate,
    # contract-allowed field-level diagnostics.
    if not isinstance(payload, str) or len(payload) < _MIN_ECHO_PAYLOAD_LEN:
        return
    payload_str = payload
    if payload_str in text:
        suffix = f" ({context})" if context else ""
        raise AssertionError(
            f"native exception echoed payload verbatim{suffix}: "
            f"payload={payload_str!r} native_message={text!r}"
        )


def fresh_identifier(prefix: str) -> str:
    """A syntactically-safe, effectively-unique identifier for use as a
    throwaway entity/field name inside condition tests.

    Uses the lower-case ``[a-z][a-z0-9_]*`` form, which sits inside the
    intersection of both peers' identifier policies (design section 4.2 /
    discovery 2 in section 8), so it is safe regardless of which peer is
    under test.
    """
    if not prefix or not prefix[0].isalpha() or not prefix.islower():
        raise ValueError("prefix must be a lowercase identifier fragment")
    suffix = uuid.uuid4().hex[:12]
    return f"{prefix}_{suffix}"


def signature_forbids_parameters(
    callables: Sequence[Callable], forbidden_name_fragments: Sequence[str]
) -> list[str]:
    """Inspect the signatures of ``callables`` and return a list of
    human-readable violations (``"<callable>.<param>"``) for every
    parameter whose name contains one of ``forbidden_name_fragments`` as a
    case-insensitive substring. An empty return means no violation.

    Shared by the ``structurally_absent`` tamper-vector check (design
    section 4.3) and the native-command-surface check (design section 5.2
    item 2).
    """
    violations: list[str] = []
    lowered = [f.lower() for f in forbidden_name_fragments]
    for fn in callables:
        try:
            sig = inspect.signature(fn)
        except (TypeError, ValueError):
            continue
        for pname in sig.parameters:
            pname_l = pname.lower()
            if any(frag in pname_l for frag in lowered):
                label = getattr(fn, "__qualname__", repr(fn))
                violations.append(f"{label}.{pname}")
    return violations


# ---------------------------------------------------------------------------
# 4.2 Fixture
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Fixture:
    """`shared_entity`/`a_only_entity`/`b_only_entity`'s own field sets (as
    each adapter's `build_fixture()` constructs them) never include `id`, and
    common probes/tests must not introduce it as an ordinary field name
    either: `id` (and any peer's implementation-reserved name prefix, e.g.
    `r2db-api`'s `_r2db`) may be reserved by a registered peer for its own
    purposes -- `r2db-api` reserves `id` as its server-assigned address
    column (design docs/design/R2DB_CCR13_STORAGE_V1.md R-3) -- and a name
    reservable by *any one* peer is not safe for the *common* fixture/probes
    to use, even on peers that do not themselves reserve it (port v1.2
    coordinated revision, docs/design/CONFORMANCE_ADAPTER_V1.md section 12).
    The common suite's convention is `item_key` for this purpose.
    """

    adapter: "ConformanceAdapter"
    app_a: str
    app_b: str
    runtime_a: object  # session handle
    developer_a: object
    runtime_b: object
    shared_entity: str  # exists, under the same name, in both A and B
    a_only_entity: str  # exists only in A
    b_only_entity: str  # exists only in B


# ---------------------------------------------------------------------------
# 4.3 TamperVector
# ---------------------------------------------------------------------------

TAMPER_KINDS = (
    "forged_scope_object",
    "role_elevation",
    "request_field_scope",
    "cross_application_handle",
)

MUST_COVER_TAMPER_KINDS = set(TAMPER_KINDS)

TAMPER_DISPOSITIONS = frozenset({"must_deny", "must_ignore", "structurally_absent"})


@dataclass(frozen=True)
class TamperVector:
    kind: str  # member of TAMPER_KINDS
    name: str
    disposition: str  # "must_deny" | "must_ignore" | "structurally_absent"
    attempt: Callable[[], Any] | None = None
    surface: Sequence[Callable] | None = None
    forbidden_parameters: Sequence[str] = field(default_factory=tuple)


@dataclass(frozen=True)
class BatchOperation:
    """One element of the list `ConformanceAdapter.attempt_batch_with_
    addresses` presents as a single real atomic mutation unit (port v1.4,
    docs/design/CONFORMANCE_ADAPTER_V1.md section 14). Field-for-field the
    same shape `attempt_mutation`'s own keyword arguments already use, so a
    caller building a batch from what would otherwise be several separate
    `attempt_mutation` calls does not learn a second vocabulary.
    `destructive`/`confirmation` follow the same `VALID_CONFIRMATION`
    sentinel protocol as `ConformanceAdapter.delete`.
    """

    operation: str
    values: Mapping[str, Any] | None = None
    where_field: str | None = None
    where_value: Any = None
    expected_revision: str | None = None
    unique_key: str | None = None
    destructive: bool = False
    confirmation: Any = None


# ---------------------------------------------------------------------------
# 4.4 Abstract adapter
# ---------------------------------------------------------------------------

MUST_COVER_IDENTIFIER_POSITIONS = {
    "entity",
    "select_field",
    "filter_field",
    "insert_field",
    "schema_entity",
    "schema_field",
}

MUST_COVER_VALUE_POSITIONS = {"insert_value", "filter_value"}

# design section 5.2 item 2: no public operation callable may expose a
# parameter suggesting a native-command escape hatch.
NATIVE_SURFACE_FORBIDDEN_NAME_FRAGMENTS = (
    "sql",
    "query_text",
    "statement",
    "command",
    "script",
    "raw",
    "expression",
    "native",
)

# design section 6.2: the two-member common field-type vocabulary.
COMMON_FIELD_TYPES = ("text", "integer")


class ConformanceAdapter(ABC):
    name: str

    # --- control plane (outside application authority) ---
    @abstractmethod
    def provision_application(self, application_id: str) -> None: ...

    @abstractmethod
    def issue_credential(self, application_id: str, role: str) -> CredentialHandle: ...

    @abstractmethod
    def revoke_credential(self, handle: CredentialHandle) -> None: ...

    @abstractmethod
    def disable_application(self, application_id: str) -> None: ...

    @abstractmethod
    def enable_application(self, application_id: str) -> None: ...

    @abstractmethod
    def set_authorization_state_available(self, available: bool) -> None: ...

    @abstractmethod
    def propagation_bound_ms(self) -> int: ...  # finite, >= 0

    @abstractmethod
    def capability_document(self) -> Mapping[str, Any]:
        """Return the peer's capability/discovery document as a mapping.

        This is the peer's own `CapabilityDocument` (design section 7 /
        `spec/data-service-api.v1.json` `schemas.CapabilityDocument`), not a
        value invented by the adapter. It MUST include a real
        `authorization_propagation_bound_ms`, published by the peer itself,
        that agrees with `propagation_bound_ms()`.

        This method must not be permitted to return `None` or an empty
        mapping. A peer that cannot publish its propagation bound has a
        real SI-13 gap -- the suite must show that as a failure, not accept
        an escape hatch (design principle 4: uncertainty must not silently
        become permission).
        """

    # --- application plane ---
    @abstractmethod
    def authenticate(self, handle: CredentialHandle) -> object: ...  # may raise ConformanceDenial

    @abstractmethod
    def scope_of(self, session: object) -> ScopeView: ...

    @abstractmethod
    def create_entity(self, session, entity: str, fields: Mapping[str, str]) -> None:
        """Create `entity` with the given fields (`{field_name: field_type}`,
        `field_type` one of `COMMON_FIELD_TYPES`).

        A plug has an obligation to wire `field_type` through to the peer's
        own typed-column mechanism where one exists, rather than silently
        discarding the type and always falling back to an untyped/JSONB
        column (design docs/design/R2DB_CCR13_STORAGE_V1.md correction M-8:
        "型付き列が共通 suite を一度も通らない"). For `r2db-api`, the wiring
        target is `add_field` + `field_type` (`create_entity` itself has no
        per-field type slot in the common contract, so a plug maps this call
        to `create_entity` followed by one `add_field` per field -- already
        true today for the field*names* alone -- carrying `field_type` on
        each `add_field` once the peer accepts it). Activating that wiring
        is deferred to `r2db-api`'s own implementation of `add_field` +
        `field_type` (docs/design/R2DB_CCR13_STORAGE_V1.md work package
        WP-5); until then, a plug may continue to pass only field names, as
        it does today.
        """

    @abstractmethod
    def insert(self, session, entity: str, values: Mapping[str, Any]) -> None: ...

    @abstractmethod
    def select_eq(
        self, session, entity: str, select: Sequence[str], field: str | None, value: Any
    ) -> list[dict]: ...

    @abstractmethod
    def attempt_filter(
        self, session, entity: str, select: Sequence[str], field: str, operator: str, value: Any
    ) -> list[dict]:
        """`select_eq` generalized to an arbitrary predicate operator (port
        v1.3, docs/design/CONFORMANCE_ADAPTER_V1.md section 13): presents a
        single-predicate query (`{field, operator, value}`) to the peer
        exactly as a real client attempting that operator would, returning
        matching items. Unlike `select_eq`, `field`/`operator` are not
        optional -- there is always exactly one predicate.

        Used by C-12's reverse condition (an operator outside a peer's own
        declared `structured_query.operators` set must be refused with
        `CAPABILITY_UNSUPPORTED` before execution, state unchanged) and by
        C-03's `contains`/`matches` value-corpus probes (literal-vs-wildcard
        semantics, and `matches`'s pattern-grammar rejection). Every
        operator in the common contract's `allowed_query_operators` MUST be
        presented to the same real query entry point `select_eq` already
        uses -- never fabricated as a denial by the adapter itself, per the
        same principle `attempt_mutation`'s docstring states for the
        mutation vocabulary.
        """

    @abstractmethod
    def delete(
        self,
        session,
        entity: str,
        field: str,
        value: Any,
        *,
        destructive: bool,
        confirmation: str | None,
    ) -> int:
        """Delete matching rows.

        `destructive` MUST be passed through to the peer faithfully.
        `confirmation` follows the `VALID_CONFIRMATION` sentinel protocol
        documented above. An adapter that ignores these and always supplies
        its peer's native confirmation is non-conformant: it makes the
        port's destructive semantics decorative and prevents C-06 from ever
        being expressed honestly on this port.
        """

    @abstractmethod
    def count(self, session, entity: str) -> int: ...

    @abstractmethod
    def entities(self, session) -> set[str]: ...

    @abstractmethod
    def catalog_document(self, session) -> Mapping[str, Any] | str:
        """Return the peer's own `CatalogDocument` (design docs/design/
        CONFORMANCE_CONDITIONS_V1_1.md section 2), unmodified.

        This is the peer's real discovery/catalog document for `session`'s
        scope, not a value the adapter assembles from other calls. If the
        peer denies the underlying operation (e.g. the caller's
        credential/session is no longer valid, or the peer has a catalog
        endpoint that answers "unsupported"), this raises
        `ConformanceDenial` exactly like every other application-plane
        method on this ABC. If the peer has no catalog operation on its
        public surface at all -- not "denies it", structurally absent, no
        callable to invoke -- this returns `CATALOG_SURFACE_ABSENT` rather
        than fabricating a document. Adapters must not synthesize a
        `CatalogDocument`-shaped dict out of other operations' side
        channels; that would make the suite validate the adapter's
        assembly, not the peer's own declared discovery surface.
        """

    @abstractmethod
    def attempt_mutation(
        self,
        session,
        entity: str,
        operation: str,
        *,
        values: Mapping[str, Any] | None,
        where_field: str | None,
        where_value: Any,
        expected_revision: str | None = None,
        unique_key: str | None = None,
    ) -> int:
        """Present one mutation-vocabulary operation (`insert` / `update` /
        `upsert` / `delete`) to the peer exactly as a real client would, and
        return the number of rows affected.

        `values`/`where_field`/`where_value` follow the same "at most one
        equality filter" shape every other probe on this ABC already uses
        (mirrors `select_eq`/`delete`): `where_field is None` means no
        filter is supplied at all; otherwise the filter is
        `{field: where_field, operator: "eq", value: where_value}`.
        `values` is omitted (not merely empty) when `None`.

        `expected_revision` (port v1.2, docs/design/CONFORMANCE_ADAPTER_V1.md
        section 12) is the contract's revision-precondition value
        (`structured_operations.revision_preconditions`); when not `None`,
        the plug carries it through to the peer's real mutation entry point
        exactly as it does `values`/`where_field`/`where_value` -- never
        interpreted or evaluated by the adapter itself. Before reaching for
        `SurfaceAbsent`, check every entry point this peer actually has, not
        only the operation-specific dedicated methods: a generic dispatcher
        that accepts an arbitrary operation-dict shape (the same kind of
        entry point the "if a peer has more than one entry point" paragraph
        below already requires `attempt_mutation` itself to prefer for the
        base operation) may carry an extra key like `expected_revision`
        perfectly well even when no *typed* method parameter exists for it
        anywhere (correction B-2: an earlier revision of `MitateDB-api`'s
        plug declared this `SurfaceAbsent` on exactly that mistaken
        assumption, when its `transact()` dispatcher was in fact a real,
        present entry point for it -- one that, at the time, silently
        dropped the precondition and committed anyway, which was the real
        non-conformance C-18 exists to catch, not a structural absence to
        report around it). Only when no call on the peer's entire public
        surface could carry this key at all does the plug raise
        `SurfaceAbsent` (with a `surface`/`forbidden_parameters` pair
        covering every candidate entry point, per `SurfaceAbsent`'s own
        docstring) rather than fabricating either a `ConformanceDenial` or a
        silent, precondition-dropping success. `r2db-api` (both plugs)
        already has a real parameter position for this
        (`Mutation.expected_revision` in the mutation-operation shape both
        plugs already construct), which the peer itself currently refuses
        with `CAPABILITY_UNSUPPORTED` (`revision_preconditions: unavailable`
        as of docs/design/R2DB_CCR13_STORAGE_V1.md work package WP-1) -- a
        real, present denial, not a structural absence.

        `unique_key` (port v1.3, docs/design/CONFORMANCE_ADAPTER_V1.md
        section 13) is the contract's `Mutation.unique_key` (CCR-13 §0.5
        Q-1 adjudication, plan B): names, by the catalog's own key name,
        which of an entity's declared uniqueness keys `upsert` should use
        as its existence test when more than one is declared. Carried
        through exactly like `expected_revision` -- never interpreted by
        the adapter -- to whatever real entry point already receives the
        rest of the operation (for `r2db-api`, the same `unique_key`
        parameter position on the single mutation dispatcher every other
        keyword here already uses).

        This method is used by C-12 (capability declaration agreement) to
        exercise `insert`/`update`/`upsert` against the peer's own
        declared `atomic_mutation` capability; it deliberately never
        exercises `delete` in that non-destructive context (C-12 leaves
        destructive-operation conformance to C-06's own future suite), but
        `delete` is still part of this method's contract for adapters that
        can express it faithfully.

        Every operation in this vocabulary MUST be presented to some real,
        present call on the peer -- never fabricated as a denial by the
        adapter itself. If a peer has more than one entry point that could
        plausibly receive an operation name (for example, a generic
        transaction dispatcher that accepts an arbitrary operation-type
        string alongside separate, dedicated per-operation methods), the
        adapter presents it to the entry point a real client attempting
        that named operation would actually use, and returns whatever that
        peer call itself produces -- success or `ConformanceDenial` alike.
        An adapter denying an operation without presenting it to the peer
        at all is exactly what design principle 4 (`docs/design/
        CONFORMANCE_ADAPTER_V1.md` section 2) forbids: it would hide a real
        peer non-conformance (a capability the peer's own document
        declares unsupported, but which its real call surface does not
        actually refuse, or refuses with the wrong code) behind a
        passing test.
        """

    @abstractmethod
    def attempt_mutation_with_addresses(
        self,
        session,
        entity: str,
        operation: str,
        *,
        values: Mapping[str, Any] | None,
        where_field: str | None,
        where_value: Any,
        expected_revision: str | None = None,
        unique_key: str | None = None,
    ) -> tuple[int, list[Mapping[str, Any]] | None]:
        """Same request/dispatch semantics as `attempt_mutation` in every
        respect (port v1.3, docs/design/CONFORMANCE_ADAPTER_V1.md section
        13), but observes the real mutation response's addresses too,
        returning `(affected, assigned_addresses)` instead of a bare
        `int`. A second method, rather than changing `attempt_mutation`'s
        own return type, because C-12 already depends on `attempt_mutation`
        returning a plain `int` it compares with `>= 1`; this method exists
        for C-17, which needs to see the response's `assigned_addresses`
        directly (in particular, that only the *insert-resolved* half of an
        `upsert` batch ever appears there -- an update-resolved `upsert`
        must report none) rather than infer address values indirectly.

        `assigned_addresses` (index-aligned with insert/insert-resolved-
        upsert operations in the contract's `MutationResult.
        assigned_addresses`) is `None` when the peer's real mutation
        response carries no addresses concept at all (the same convention
        `query_with_revisions` uses for `revisions`) -- an *observed* fact
        about that real response, never an assumption: a plug whose peer's
        response is a dict inspects it for the real key (e.g.
        `result.get("assigned_addresses")`); only a plug whose underlying
        call's return type structurally has no such slot at all (a bare
        list/int, not a wrapping object) may report `None` on that
        structural basis alone (conformance-review correction M-1's same
        principle, applied here to addresses instead of revisions).
        """

    @abstractmethod
    def attempt_batch_with_addresses(
        self, session, entity: str, operations: Sequence[BatchOperation]
    ) -> tuple[int, list[Mapping[str, Any]] | None]:
        """Present multiple mutation-vocabulary operations as ONE real
        atomic batch to the peer -- the same real multi-operation
        dispatcher `attempt_mutation`/`attempt_mutation_with_addresses`
        already use with exactly one operation each -- and return the
        whole batch's `(affected, assigned_addresses)` (port v1.4,
        docs/design/CONFORMANCE_ADAPTER_V1.md section 14).

        Exists for C-17: `attempt_mutation_with_addresses` alone only ever
        proves the insert-only membership rule for `assigned_addresses` one
        operation at a time, which cannot catch a defect that only appears
        when operations of different kinds share one atomic unit (for
        example, a batch-level accumulation bug that attaches an address
        entry to a non-insert operation only when a real insert elsewhere
        in the same batch happens to precede it). Every operation MUST be
        presented to the same real batch entry point a real client
        sending multiple operations at once would use -- never split into
        several separate single-operation calls by the adapter itself,
        which would prove nothing about batch-level behavior at all.
        """

    @abstractmethod
    def create_unique_index(self, session, entity: str, index: str, fields: Sequence[str]) -> None:
        """Present a real `create_index` (`unique: true`) schema operation to
        the peer, exactly as a real client attempting the contract's
        `create_index` vocabulary (CCR-13, contract 1.1.0) would (port v1.2,
        docs/design/CONFORMANCE_ADAPTER_V1.md section 12). Returns normally
        on success; raises `ConformanceDenial` on the peer's own real
        refusal.

        `r2db-api` (docs/design/R2DB_CCR13_STORAGE_V1.md work package WP-3)
        now really implements `create_index`, so a well-formed request
        against a real entity with real, existing fields succeeds for real
        on this peer -- this is no longer a guaranteed-refusal probe there
        (port v1.2's original docstring text described the WP-1-era state,
        before WP-3 landed; port v1.3 corrects it). A malformed or
        conflicting request still gets a genuine `ConformanceDenial` from
        the same real, single `schema()` dispatcher every other schema
        operation goes through, exactly like `attempt_mutation`'s `upsert`
        branch -- never fabricated.

        Raises `SurfaceAbsent` instead when the peer's public surface has no
        schema-operation entry point that could plausibly receive an
        index-creation request at all -- confirmed by source inspection,
        never assumed, and never used to excuse a peer that actually
        received and mishandled the request. Per `SurfaceAbsent`'s own
        docstring, that exception must carry `surface`/`forbidden_parameters`
        naming the real callables inspected and the parameter names checked
        for, so a consumer can verify the claim independently via
        `signature_forbids_parameters` rather than trust it outright.
        """

    @abstractmethod
    def query_with_revisions(
        self, session, entity: str, select: Sequence[str], field: str | None, value: Any
    ) -> tuple[list[dict], list[str] | None]:
        """Same request shape as `select_eq`, returning `(items, revisions)`
        (port v1.2, docs/design/CONFORMANCE_ADAPTER_V1.md section 12): the
        contract's `QueryResult.revisions` (index-aligned with `items`,
        docs/design/R2DB_CCR13_STORAGE_V1.md R-4), or `None` when the peer's
        real query response carries no revisions concept at all (every
        currently-registered peer, since `revision_preconditions` is
        `unavailable` everywhere as of work package WP-1) -- never a value
        this adapter invents on the peer's behalf.

        `None` must be an *observation*, not an assumption: when the real
        call this plug drives returns a dict-shaped response, the plug
        inspects that response for a revisions-shaped key (e.g.
        `result.get("revisions")`) rather than hardcoding `None` regardless
        of what the peer actually sent back. Only when the call's own
        return type structurally has no place a revisions value could ever
        occupy at all (a bare `list[dict]`, not a wrapping object) does
        `None` stand on that structural fact alone, with no dict left
        unlooked-at (conformance-review correction M-1).
        """

    # --- attack surface declarations ---
    @abstractmethod
    def native_command_surface(self) -> None: ...  # must always return None

    @abstractmethod
    def public_operation_callables(self) -> Sequence[Callable]: ...

    @abstractmethod
    def tamper_vectors(self, fixture: Fixture) -> Sequence[TamperVector]: ...

    @abstractmethod
    def credential_reactivation_vectors(self, handle: CredentialHandle) -> Sequence[TamperVector]:
        """Declare every control-plane surface of this peer that could
        conceivably re-activate an already-*revoked* credential, as
        `TamperVector`s (design docs/design/CONFORMANCE_CONDITIONS_V1_1.md
        section 2). `handle` refers to a credential the C-13 condition test
        has already revoked by the time this is called.

        `kind` is always the fixed string `"credential_reactivation"` --
        this is deliberately not added to `TAMPER_KINDS` / not covered by
        `MUST_COVER_TAMPER_KINDS`, since it is a C-13-specific taxonomy, not
        part of C-01's scope-tampering taxonomy. `disposition` reuses the
        same three-value vocabulary as `tamper_vectors` (`TAMPER_DISPOSITIONS`),
        with the identical general meaning but interpreted against C-13's
        revoked-credential context specifically:

        - `must_deny` -- `attempt()` must raise `ConformanceDenial`: this
          control-plane call itself refuses to act on an already-revoked
          credential.
        - `must_ignore` -- `attempt()` may succeed (it legitimately changes
          some *other* piece of state, e.g. a `enabled` flag distinct from
          `revoked`), but authenticating with this credential afterward
          must still be denied -- the attempt had no reactivating effect,
          even though it did not itself raise.
        - `structurally_absent` -- there is no control-plane call on this
          peer's public surface that could reactivate a revoked credential
          at all; proven the same structural way as `tamper_vectors`'
          `structurally_absent` vectors (`surface` + `forbidden_parameters`
          inspected via `signature_forbids_parameters`), never accepted as
          a bare claim.

        At least one vector must be returned; an empty declaration is a
        suite failure (design principle 4: uncertainty must not silently
        become permission), not "not applicable".
        """

    @abstractmethod
    def identifier_positions(self, fixture: Fixture) -> Mapping[str, Callable[[Any], Any]]: ...

    @abstractmethod
    def value_positions(self, fixture: Fixture) -> Mapping[str, Callable[[Any], Any]]: ...

    # --- normalization ---
    @abstractmethod
    def classify(self, exc: BaseException) -> str:
        """Map a native peer exception to a common contract error code.

        Adapters MUST catch only their peer's own declared error base class
        when converting to `ConformanceDenial`. Any other native exception
        (a raw storage-driver error, a TypeError, an unhandled crash) MUST
        map to `UNCLASSIFIED` rather than to a plausible-looking contract
        code. A peer that crashes on an injection payload is a finding under
        SI-05 and SI-10; classifying that crash as VALIDATION_FAILED would
        turn the defect into a passing test.
        """

    # --- construction ---
    @abstractmethod
    def build_fixture(self) -> Fixture: ...

    @abstractmethod
    def close(self) -> None: ...
