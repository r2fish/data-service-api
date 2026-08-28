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
    def create_entity(self, session, entity: str, fields: Mapping[str, str]) -> None: ...

    @abstractmethod
    def insert(self, session, entity: str, values: Mapping[str, Any]) -> None: ...

    @abstractmethod
    def select_eq(
        self, session, entity: str, select: Sequence[str], field: str | None, value: Any
    ) -> list[dict]: ...

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
