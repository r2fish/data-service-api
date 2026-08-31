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
import re
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
class ControlCredentialHandle:
    """A control-plane credential handle (port v1.5, design docs/design/
    R2DB_CCR14_CONTROL_PLANE_V1.md section 4). Deliberately a distinct type
    from `CredentialHandle`, not a variant of it: a control credential
    belongs to no Application at all (the contract's `control_credential`
    scheme has no `application_id`/`role` slot the way an application
    credential's `runtime`/`developer` scheme does -- design section R-2:
    "control credential is not FK'd to any Application"). Minting a
    `ControlCredentialHandle` with a placeholder `application_id`/`role`
    just to satisfy `CredentialHandle`'s shape would let a scope-tampering
    defect hide behind a value this port itself fabricated; keeping the
    types disjoint makes such a value a type error instead of a silent
    coercion.
    """

    credential_ref: str  # opaque reference (e.g. "ctl_...")
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
    ``ConformanceDenial`` itself. Port v1.6 (design docs/design/
    DESTRUCTIVE_CONFIRMATION_V1.md R-6 item 2) adds ``details`` -- a
    *mapping* -- alongside this, additively: a structured problem+json/
    native-exception ``details`` mapping (e.g. ``required_confirmation``/
    ``consequence``/``reversible_alternative``/``recovery`` for
    ``DESTRUCTIVE_CONFIRMATION_REQUIRED``) carries genuine, code-specific
    machine-readable declarations a caller needs to act on (the
    declare-and-echo protocol below reads ``required_confirmation`` off of
    exactly this). This does not weaken the message-exclusion rationale
    above: ``details`` is never free text and is deliberately not populated
    with anything resembling a message -- each adapter wires only the
    peer's own structured details mapping (a problem+json response's
    ``details`` object, or a native exception's own ``details`` attribute),
    never a string built from interpolating request data. A denial with no
    such mapping available (most denials; most native exceptions have no
    ``details`` at all) simply carries an empty mapping, never `None` --
    callers may read ``denial.details.get(...)`` unconditionally.

    Adapters should chain the native exception using standard Python
    exception chaining: ``raise ConformanceDenial(...) from native_exc``.
    That is the single shared mechanism (`native_cause_of`, below) both the
    suite and adapters use to reach the native exception for the non-echo
    check (design section 5.2 item 6 / section 6.3), which must run
    *before* -- i.e. independently of -- any interpretation performed by
    ``classify()``.
    """

    def __init__(
        self, code: str, adapter: str, native_type: str = "", *, details: Mapping[str, Any] | None = None
    ) -> None:
        self.code = code
        self.adapter = adapter
        self.native_type = native_type
        self.details: dict[str, Any] = dict(details) if details else {}
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

    `exempt_parameters` (port v1.5 fix-round, design docs/design/
    R2DB_CCR14_CONTROL_PLANE_V1.md WP-1 independent review, major M-7):
    an optional sequence of qualified `"<callable.__qualname__>.<param>"`
    strings (the exact label `signature_forbids_parameters` itself emits
    for a violation) naming a REAL parameter on the declared `surface`
    that happens to match one of `forbidden_parameters`'s fragments by
    coincidence, but cannot actually carry the absent capability -- e.g. a
    peer's ordinary session-authentication entry point taking a parameter
    literally named `credential_id`, which identifies an *already-issued*
    application credential rather than anything control-plane-shaped. An
    exemption is not a way to make an inconvenient violation disappear:
    a consumer verifying this claim (`signature_forbids_parameters(surface,
    forbidden_parameters)`) MUST additionally assert the violations it
    finds are EXACTLY `exempt_parameters` -- no more (an unexempted, live
    violation is still a genuine claim failure) and no less (a stale or
    padded exemption naming a parameter that does not actually appear as a
    violation is itself suspicious: it either no longer applies, having
    been carried over from a prior surface, or was never a real exemption
    to begin with). The justification for each exemption belongs in the
    adapter's own source, next to the `SurfaceAbsent` call site that
    supplies it -- this constructor does not validate the justification's
    content, only that the mechanism exists for a consumer to hold the
    claim to account. Empty by default: most `SurfaceAbsent` claims need
    no exemption at all.
    """

    def __init__(
        self,
        adapter: str,
        operation: str,
        reason: str,
        *,
        surface: Sequence[Callable],
        forbidden_parameters: Sequence[str],
        exempt_parameters: Sequence[str] = (),
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
        self.exempt_parameters = tuple(exempt_parameters)
        super().__init__(f"{adapter}: {operation} has no surface on this peer: {reason}")


# Sentinel for `ConformanceAdapter.delete(..., confirmation=...)` (and every
# other destructive-operation call site that resolves this sentinel through
# an adapter's own `_resolve_confirmation`: `attempt_batch_with_addresses`'s
# `BatchOperation.confirmation`, `drop_entity`). `revoke_credential_inband`
# is deliberately NOT one of these: it passes its own `confirmation`
# parameter straight through, unresolved, exactly as its own docstring
# already states -- a caller that needs declare-and-echo for it (C-06
# vector V7) drives the real probe/echo round trip itself, directly against
# the port method, rather than asking an adapter to resolve this sentinel
# on its behalf.
#
# Peers legitimately spell their destructive-confirmation token differently.
# Before contract 1.2.0 (docs/design/DESTRUCTIVE_CONFIRMATION_V1.md), that
# meant a fixed, peer-specific literal (`r2db-api` required the literal
# "DELETE"; `MitateDB-api` used a boolean `confirm=True`). Port v1.6
# (design R-6 item 1) replaces that fixed-token resolution with
# declare-and-echo for any peer declaring `contract_version >= 1.2.0`: the
# adapter itself has no business hardcoding a phrase the contract now
# requires the *peer* to compute and declare (`phrase_construction`'s own
# "spelling is implementation-defined" rule) -- `resolve_valid_confirmation`,
# below, is the shared mechanism every adapter uses to do this (probe the
# real destructive entry point with no confirmation, read the phrase off
# the peer's own denial, echo it back). A peer still declaring `1.1.0`
# keeps receiving its legacy fixed token unchanged, so pre-1.2.0 coverage
# of this port is not disturbed.
#
# The port therefore still normalizes *intent*, not spelling, from an
# adapter call site's point of view:
#
#   confirmation=None                -> supply NO confirmation to the peer
#   confirmation=VALID_CONFIRMATION  -> supply a real, currently-valid
#                                        confirmation for this exact
#                                        request (declare-and-echo if the
#                                        peer declares >= 1.2.0; the
#                                        peer's legacy fixed token
#                                        otherwise)
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


def _walk_string_leaves(value: Any, path: str) -> list[tuple[str, str]]:
    """Recursively descend into `dict`/`list`/`tuple` structures, returning
    every `(path, string_value)` leaf found. `path` is a human-readable
    breadcrumb (`"details['x'][2]"`) for diagnostics only."""
    if isinstance(value, str):
        return [(path, value)] if value else []
    if isinstance(value, Mapping):
        leaves: list[tuple[str, str]] = []
        for key, sub in value.items():
            leaves.extend(_walk_string_leaves(sub, f"{path}[{key!r}]"))
        return leaves
    if isinstance(value, (list, tuple)):
        leaves = []
        for index, sub in enumerate(value):
            leaves.extend(_walk_string_leaves(sub, f"{path}[{index}]"))
        return leaves
    return []


def assert_no_payload_echo_in_details(details: Mapping[str, Any], payload: Any, *, context: str = "") -> None:
    """`assert_no_payload_echo`'s exact check, applied to every value of a
    `ConformanceDenial.details` mapping instead of a native exception's
    `str()` (design docs/design/DESTRUCTIVE_CONFIRMATION_V1.md R-6 item 2 /
    WP-0 MA-3 / C-06 vector V8): a destructive-confirmation denial's
    `required_confirmation`/`consequence`/`reversible_alternative`/
    `recovery` are exactly the kind of machine-readable declarations an
    adversarial target name/value could otherwise leak through verbatim
    (e.g. a `required_confirmation` phrase that echoes an unvalidated
    identifier back to the caller -- phrase_construction's own "only
    identifier-validated target names" rule exists to prevent this).

    Recurses into any `dict`/`list`/`tuple` nesting (review correction M-4:
    "details 全値" means every string leaf reachable from the mapping, not
    only its own top-level values -- a future denial that nests a per-
    operation list of consequences, for instance, must not go unchecked
    just because it is one level deeper). Only string leaves are inspected
    (a leaf can legitimately be `None`, a bool, or a number; only a string
    can contain a verbatim substring match at all). Uses the same
    length/type floor as `assert_no_payload_echo` to avoid false positives
    against short/non-string payloads.
    """
    if not isinstance(payload, str) or len(payload) < _MIN_ECHO_PAYLOAD_LEN:
        return
    for path, value in _walk_string_leaves(details, "details"):
        if payload in value:
            suffix = f" ({context})" if context else ""
            raise AssertionError(
                f"denial {path} echoed payload verbatim{suffix}: "
                f"payload={payload!r} value={value!r}"
            )


# Exactly three dot-separated non-negative integers, each with no leading
# zero (`0` itself is the one exception -- `"01"` is not a valid component).
# Deliberately narrower than full semver (no pre-release/build-metadata
# suffix, no surrounding whitespace): `contract_version` is this repository's
# own closed vocabulary (`spec/data-service-api.v1.json`'s own
# `contract_version` values are always bare `MAJOR.MINOR.PATCH`), and
# silently accepting a shape the contract itself never produces would hide
# a real declaration defect behind a permissive parse (review correction
# m-4: a raw `int()` on an unexpected shape used to raise `ValueError` with
# no explanation, which surfaced as an opaque pytest ERROR -- distinct from
# a clean, diagnosable FAILED -- in every one of C-06's 8 vector tests the
# first time this was exercised against a malformed version).
_SEMVER_RE = re.compile(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)")


def parse_semver(version: str) -> tuple[int, int, int]:
    """Parse a `MAJOR.MINOR.PATCH` string into a comparable tuple of ints
    (design docs/design/DESTRUCTIVE_CONFIRMATION_V1.md R-6 / WP-0 m-3): a
    naive string comparison would misrank e.g. "1.10.0" below "1.2.0",
    which is exactly the trap the design calls out by name for the
    contract-version branch this parses for. Raises `ValueError`, naming
    the unsupported shape explicitly, on anything that is not exactly three
    dot-separated non-negative integers with no leading zeros and no
    surrounding text -- including a pre-release/build-metadata suffix
    (`"1.2.0-rc1"`, `"1.2.0+build5"`) or incidental whitespace (`" 1.2.0"`):
    this port never guesses at a version string it cannot parse, and never
    silently truncates a suffix it does not understand.
    """
    match = _SEMVER_RE.fullmatch(version)
    if match is None:
        raise ValueError(
            f"unsupported version format: {version!r} -- expected exactly MAJOR.MINOR.PATCH "
            "(non-negative integers, no leading zeros, no pre-release/build suffix, no surrounding text)"
        )
    return tuple(int(p) for p in match.groups())  # type: ignore[return-value]


def contract_version_at_least(contract_version: str, minimum: str) -> bool:
    """`True` iff `contract_version` (a peer's own declared `capability_
    document()["contract_version"]`) is >= `minimum` under semver-tuple
    comparison (never a string comparison -- see `parse_semver`)."""
    return parse_semver(contract_version) >= parse_semver(minimum)


def resolve_valid_confirmation(
    *, contract_version: str, legacy_token: Any, probe: Callable[[], Any]
) -> Any:
    """Resolve the `VALID_CONFIRMATION` sentinel into a real confirmation
    value for the peer at hand (design docs/design/
    DESTRUCTIVE_CONFIRMATION_V1.md R-6 item 1, declare-and-echo; port v1.6).

    A peer declaring `contract_version` < 1.2.0 gets `legacy_token`
    unchanged -- its own fixed, peer-specific confirmation spelling, exactly
    as every adapter supplied before this port revision. A peer declaring
    `contract_version` >= 1.2.0 instead gets a real probe -> echo round
    trip: `probe` is called, expected to present the SAME destructive
    operation the caller is about to retry (same entity/scope), with
    `destructive=True` and NO confirmation supplied, through whatever real
    entry point a genuine client would use. The peer is expected to refuse
    it with `DESTRUCTIVE_CONFIRMATION_REQUIRED`, and the phrase this
    function returns is read directly off that denial's own
    `details["required_confirmation"]` -- never guessed, hardcoded, or
    assembled by this port itself (`phrase_construction`'s own "spelling is
    implementation-defined" rule, and Q1-D2: "句の綴りは契約で固定せず...
    クライアントは常に復唱").

    Raises `AssertionError` (a suite finding, not a harness bug) if the
    probe does not behave the way a contract_version >= 1.2.0 peer must:
    succeeding outright (SI-09 regression -- an unconfirmed destructive
    operation must never execute), denying with any code other than
    `DESTRUCTIVE_CONFIRMATION_REQUIRED`, or denying without a non-empty
    string `required_confirmation` in its details.
    """
    if not contract_version_at_least(contract_version, "1.2.0"):
        return legacy_token
    try:
        probe()
    except ConformanceDenial as denial:
        if denial.code != "DESTRUCTIVE_CONFIRMATION_REQUIRED":
            raise AssertionError(
                "declare-and-echo probe (destructive=True, no confirmation) against a peer declaring "
                f"contract_version={contract_version!r} (>= 1.2.0) expected DESTRUCTIVE_CONFIRMATION_REQUIRED, "
                f"got {denial.code!r}"
            ) from denial
        phrase = denial.details.get("required_confirmation")
        if not isinstance(phrase, str) or not phrase:
            raise AssertionError(
                f"peer declares contract_version={contract_version!r} (>= 1.2.0) but its "
                "DESTRUCTIVE_CONFIRMATION_REQUIRED denial's details carried no non-empty "
                f"required_confirmation phrase (details={denial.details!r})"
            ) from denial
        return phrase
    else:
        raise AssertionError(
            f"declare-and-echo probe (destructive=True, no confirmation) succeeded against a peer declaring "
            f"contract_version={contract_version!r} (>= 1.2.0) -- an unconfirmed destructive operation must "
            "never execute (SI-09)"
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


@dataclass(frozen=True)
class ScopedBatchOperation:
    """One element of the list `ConformanceAdapter.attempt_cross_entity_
    batch` presents as a single real atomic mutation unit scoped across
    MULTIPLE entities (port v1.7, docs/design/
    PHASE35_CROSS_ENTITY_AND_CONTRACT_130_V1.md section 3): field-for-field
    `BatchOperation` above, plus `entity` -- a cross-entity batch has no one
    shared entity for the whole call to name (unlike `attempt_batch_with_
    addresses`, whose `entity` parameter is shared by every operation in the
    list), so each operation names its own, mirroring the contract's own
    `ScopedMutation` (`Mutation` + a required `entity`, contract 1.1.0
    CCR-15, semantics clarified 1.3.0). `destructive`/`confirmation` follow
    the identical `VALID_CONFIRMATION` sentinel protocol every other
    destructive-capable operation on this port already uses -- an adapter
    presenting a batch-embedded delete's declare-and-echo probe does so
    against the SAME real cross-entity entry point this whole batch is
    presented to, never a per-entity substitute.
    """

    operation: str
    entity: str
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

    # port v1.5 (fix-round, design docs/design/R2DB_CCR14_CONTROL_PLANE_V1.md
    # WP-1 independent review, supervisor ruling on B-1/B-2): the inverse of
    # `provision_application` -- test-harness-only cleanup performed through
    # the peer's operator-privileged path, never a public API capability
    # (the contract keeps application deletion out of v1 scope entirely;
    # this is not a `revoke_credential_inband`-style in-band operation and
    # has no port v1.5 in-band counterpart). Exists so C-14 vector 5's
    # `applications` resource-bound drive can undo the permanent Applications
    # it registers to saturate the bound, instead of poisoning the
    # session-scoped adapter's registry for every later test that shares it.
    # A peer with real out-of-band deletion support (WP-5 onward) implements
    # this for real; a peer with no control plane at all raises
    # `SurfaceAbsent` the same way the other privileged setup/observation
    # operations below do (`control_credential`/`control_audit_events`).
    @abstractmethod
    def deprovision_application(self, application_id: str) -> None: ...

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

    # ------------------------------------------------------------------
    # control plane HTTP surface (port v1.5, design docs/design/
    # R2DB_CCR14_CONTROL_PLANE_V1.md section 4 "conformance -- port
    # extension and C-14/C-15 executable化")
    # ------------------------------------------------------------------
    #
    # CCR-14's contract adds an in-band `/control/v1` surface (11
    # endpoints) alongside the pre-existing out-of-band provisioning
    # primitives above (`provision_application`/`issue_credential`/
    # `revoke_credential`/`disable_application`/`enable_application`).
    # Those two groups play different roles on this port and must not be
    # confused: the group above is this adapter's own privileged,
    # out-of-band mechanism for building test preconditions -- never
    # itself the thing C-14/C-15 verify. The 13 operations below ARE the
    # thing under test: each presents a request to whatever real in-band
    # entry point a genuine application/control credential holder would
    # use, exactly as every other operation on this ABC already does for
    # its own plane (adapters observe the peer, they do not stand in for
    # it). 11 contract endpoints collapse onto 9 in-band operations here:
    # `POST .../applications/{id}/enable` and `.../disable` fold into one
    # `set_application_enabled_inband(..., enabled: bool)`, and the
    # credential pair does the same for `set_credential_enabled_inband`.
    #
    # `actor: CredentialHandle | ControlCredentialHandle` on every in-band
    # operation below is presented to the peer's real entry point exactly
    # as received -- this adapter never pre-filters by credential kind or
    # role before presenting the request. **Authorization is the peer's
    # own decision to make, not this port's.** This is what lets C-14
    # vector 1 (an application credential -- `issue_credential`'s ordinary
    # output -- handed here as `actor` against every one of these 13
    # operations) be a genuine measurement of the peer's own fail-closed
    # behavior, rather than the adapter enforcing the boundary locally and
    # reporting success regardless of what the peer itself would have
    # done.
    #
    # A denial is always `ConformanceDenial`, with `code` set by
    # `classify()` from a real native failure the peer's own real entry
    # point produced -- an adapter that raises one without ever presenting
    # the request is exactly the fabrication `SurfaceAbsent`'s own
    # docstring forbids (design principle 4), applied here to denial just
    # as it already is to absence-claims. A peer with no in-band surface
    # at all raises `SurfaceAbsent` instead (carrying `surface`/
    # `forbidden_parameters`, C-17 precedent, so the claim is
    # independently re-verifiable via `signature_forbids_parameters`
    # rather than trusted); a peer whose surface exists but whose
    # `control_plane` capability is declared `unavailable` refuses every
    # real entry point uniformly with `CAPABILITY_UNSUPPORTED` instead
    # (design section 4's two forms: (a) surface-absent, (b)
    # declared-unavailable -- see `test_c14_authority_boundary.py`'s
    # module docstring for how the condition suite dispatches between
    # them).
    #
    # A conformance build of a peer that DOES implement this surface (a
    # future work package's responsibility, not this port revision's) MUST
    # configure its SI-08 resource-boundary classes (`applications`,
    # `credentials_per_application`, `control_requests_per_minute`) small
    # enough to actually be driven past in one test run -- 200 or below is
    # recommended. A bound that is only theoretically finite (e.g. a
    # production-scale default left in place) makes C-14 vector 5
    # unexercisable in practice, which is exactly the "declared but never
    # actually driven" gap design principle 4 forbids for any boundary
    # claim.

    @abstractmethod
    def control_capabilities(self, actor: "CredentialHandle | ControlCredentialHandle") -> Mapping[str, Any]:
        """`GET /control/v1/capabilities`-equivalent: the peer's own real
        control-plane `CapabilityDocument`, exactly as `capability_document()`
        already requires for the application plane -- never a document this
        adapter assembles or invents on the peer's behalf. `actor` may be
        any credential kind; per design section 2's endpoint table this is
        the one control endpoint a `must_rotate` control credential remains
        authorized for.
        """

    @abstractmethod
    def register_application_inband(
        self, actor: "CredentialHandle | ControlCredentialHandle", application_id: str
    ) -> Mapping[str, Any]:
        """`POST /control/v1/applications`-equivalent: registers
        `application_id` as a "registered, not yet provisioned" Application
        (design section R-4) and returns the peer's real response. Never
        fabricates the registration outside the real entry point.
        """

    @abstractmethod
    def list_applications(self, actor: "CredentialHandle | ControlCredentialHandle") -> Sequence[Mapping[str, Any]]:
        """`GET /control/v1/applications`-equivalent: the peer's real
        listing (`application_id`, `enabled`) of every registered
        Application, exactly as returned -- not filtered or reshaped here.

        Response-shape normalization (design docs/design/
        R2DB_CCR14_CONTROL_PLANE_V1.md WP-1 independent review, major M-2):
        the contract's real response is an envelope object (e.g.
        `{"applications": [...]}`), not a bare array; this method unwraps
        that envelope and returns the row *sequence* itself, so every
        caller on this port works with the row list directly rather than
        re-deriving the envelope key on every call site. Row keys are the
        contract's own field names (`application_id`, `enabled`), passed
        through unmodified -- never renamed to a port-invented vocabulary.
        """

    @abstractmethod
    def set_application_enabled_inband(
        self, actor: "CredentialHandle | ControlCredentialHandle", application_id: str, enabled: bool
    ) -> Mapping[str, Any]:
        """`POST .../applications/{id}/enable`/`.../disable`-equivalent,
        collapsed onto one boolean per this group's own convention (see the
        header comment above): `enabled=True` presents the real `enable`
        request, `enabled=False` the real `disable` request -- never both,
        and never simulated locally.
        """

    @abstractmethod
    def issue_credential_inband(
        self, actor: "CredentialHandle | ControlCredentialHandle", application_id: str, role: str
    ) -> CredentialHandle:
        """`POST /control/v1/credentials`-equivalent: presents `role`
        (`"runtime"`/`"developer"`/`"control"`) to the peer's real issuance
        entry point exactly as given -- `role="control"` is deliberately
        not pre-filtered here (contract plan B reserves control-credential
        issuance to the bootstrap/reset ritual and refuses in-band
        `role="control"` with `CAPABILITY_UNSUPPORTED`; this method's job
        is only to present the request -- C-14 vector 3 is what asserts
        the peer's own refusal and its evaluation order). Returns the
        port's existing `CredentialHandle` type on a genuine
        `runtime`/`developer` success, carrying the one-time-issued real
        secret.

        Response-shape normalization (M-2, mirrors `list_credentials`
        below): the peer's real issuance response is unwrapped into this
        port's `CredentialHandle` shape by the adapter, exactly as
        `issue_credential`'s existing out-of-band counterpart already does
        -- `CredentialHandle.credential_ref` holds the same value the peer
        publishes as the contract's `credential_id`.
        """

    @abstractmethod
    def list_credentials(self, actor: "CredentialHandle | ControlCredentialHandle") -> Sequence[Mapping[str, Any]]:
        """`GET /control/v1/credentials`-equivalent: the peer's real
        combined application+control credential listing (no secrets, no
        verifiers -- design section 2's own restriction), exactly as
        returned.

        Response-shape normalization (M-2): unwraps the contract's real
        envelope (e.g. `{"credentials": [...]}`) into the row sequence,
        same as `list_applications` above. Row keys are the CONTRACT's own
        field names, passed through unmodified: `credential_id`,
        `application_id` (absent on a control-credential row), `role`,
        `enabled`, `revoked`. This port's own `CredentialHandle.
        credential_ref` / `ControlCredentialHandle.credential_ref` field
        holds the exact same value the peer publishes here as
        `credential_id` -- a caller matching a handle against a row from
        this method compares `handle.credential_ref == row["credential_id"]`,
        never `row["credential_ref"]` (that key does not exist on the
        real response; `credential_ref` is this port's own handle-field
        name, not contract vocabulary).
        """

    @abstractmethod
    def rotate_credential(self, actor: "CredentialHandle | ControlCredentialHandle", credential_ref: str) -> object:
        """`POST .../credentials/{id}/rotate`-equivalent: presents a real
        rotation request for `credential_ref` (application or control
        credential -- the peer resolves which store by trying both, design
        section 2's own "id prefix is not promoted to semantics" rule) and
        returns whatever the peer's real response carries (a fresh
        one-time secret on success). Declared `-> object` rather than a
        named port type because a rotate response's shape legitimately
        differs between an application-credential rotation and a
        control-credential rotation on the same peer, and this port does
        not need to unify them to observe rotation's own effect -- a
        caller that needs a usable handle back reads the peer's real
        response for a `secret`-shaped field (see `test_c15_..._is_not_
        permanent`'s own handling) rather than this port inventing a
        second, unified rotate-result type.
        """

    @abstractmethod
    def revoke_credential_inband(
        self,
        actor: "CredentialHandle | ControlCredentialHandle",
        credential_ref: str,
        *,
        destructive: bool | None = None,
        confirmation: str | None = None,
    ) -> Mapping[str, Any]:
        """`POST .../credentials/{id}/revoke`-equivalent. `destructive`/
        `confirmation` follow the same pass-through convention `delete`'s
        own docstring already establishes on this port (an adapter must
        not upgrade or invent confirmation state) -- design section 0.5
        notes this endpoint's confirmation *check* is presently suspended
        (contract Q-1 unresolved), so a real peer built against this
        design accepts the request whether or not these are supplied; the
        port still carries them faithfully so a future peer that does
        enforce confirmation is exercised identically without a second
        port revision.
        """

    @abstractmethod
    def set_credential_enabled_inband(
        self, actor: "CredentialHandle | ControlCredentialHandle", credential_ref: str, enabled: bool
    ) -> Mapping[str, Any]:
        """`POST .../credentials/{id}/enable`/`.../disable`-equivalent,
        collapsed the same way `set_application_enabled_inband` is.
        """

    # --- out-of-band ritual hooks (bootstrap/reset are, by contract,
    # never in-band operations at all -- see design section R-5) ---

    @abstractmethod
    def bootstrap(self) -> ControlCredentialHandle:
        """Executes the peer's real out-of-band bootstrap ritual (design
        section R-5: `python -m r2db_api.ops bootstrap` or equivalent) and
        returns the resulting control credential. No `actor` parameter --
        by contract this ritual has no in-band caller at all (plan B's own
        premise); an adapter runs the peer's real ritual mechanism (a CLI
        subprocess, a direct call into the peer's own bootstrap function --
        whichever is genuinely how an operator would invoke it), never
        fabricates a credential row itself. Raises `ConformanceDenial` on
        the peer's own real refusal (e.g. a control credential already
        exists, C-15 vector 1) or `SurfaceAbsent` where no such ritual
        mechanism exists on this peer at all yet.
        """

    @abstractmethod
    def reset(self) -> ControlCredentialHandle:
        """Executes the peer's real out-of-band reset ritual (design
        section R-5) and returns the resulting control credential. Same
        "real mechanism, no fabrication" contract as `bootstrap`.
        """

    # --- privileged setup / observation (not itself the in-band surface
    # under test -- same category as `provision_application` above) ---

    @abstractmethod
    def control_credential(self) -> ControlCredentialHandle:
        """Returns a control credential with the bootstrap/reset ritual
        already completed and any must-rotate gate (design section R-5)
        already cleared, ready to use as `actor` for any in-band operation
        -- this port's equivalent of `issue_credential`'s role for the
        application plane. Building this may require more than one real
        peer call (bootstrap, then a real rotate to clear must-rotate) --
        never a shortcut that skips a real gate the peer itself enforces.

        MUST return a handle that is genuinely valid AT CALL TIME (design
        docs/design/R2DB_CCR14_CONTROL_PLANE_V1.md WP-1 independent review,
        major M-4) -- never a memoized value from an earlier call. C-15
        deliberately revokes and resets control credentials mid-test
        (`test_c15_bootstrap_refused_while_any_control_credential_exists`,
        `test_c15_reset_revokes_every_control_credential_...`); an adapter
        that caches its first-ever `control_credential()` result and
        returns the same stale handle on every subsequent call would make
        those tests silently exercise a revoked/superseded credential
        instead of a live one, which is not conformant to this method's
        contract.
        """

    @abstractmethod
    def control_audit_events(self) -> Sequence[Mapping[str, Any]]:
        """Observes the peer's own real control-plane audit trail (design
        section R-6), exactly as recorded -- never assembled or inferred
        by this adapter from other calls' side effects. Used by C-15
        vector 4 to confirm state-change and denial events are both
        durably recorded; not itself gated behind any `actor`, since audit
        observation in a conformance build is adapter-privileged the same
        way `provision_application` is.
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
    def drop_entity(
        self,
        session,
        entity: str,
        *,
        destructive: bool,
        confirmation: str | None,
    ) -> None:
        """Present a real `drop_entity` schema operation (`SchemaOperationRequest.
        operation == "drop_entity"`) to the peer exactly as a real client
        attempting the contract's destructive schema vocabulary would (port
        v1.6, design docs/design/DESTRUCTIVE_CONFIRMATION_V1.md R-6 item 3;
        `drop_index` is deliberately left to a future port revision, Q1-D5).

        `destructive`/`confirmation` follow the EXACT same pass-through
        convention `delete`'s own docstring establishes: `destructive` MUST
        be passed through faithfully, `confirmation` follows the
        `VALID_CONFIRMATION` sentinel protocol (declare-and-echo for a peer
        declaring `contract_version >= 1.2.0`, that peer's legacy fixed
        token otherwise -- see `resolve_valid_confirmation`). An adapter
        MUST NOT upgrade a non-destructive/unconfirmed request into a
        confirmed destructive one, for the identical reason `delete`'s
        docstring already states.

        Raises `ConformanceDenial` on the peer's own real refusal, exactly
        like every other schema operation on this ABC. Raises
        `SurfaceAbsent` instead when the peer's public surface has no
        schema-operation entry point that could plausibly receive a
        destructive drop request at all -- confirmed by source inspection,
        never assumed, and carrying `surface`/`forbidden_parameters` per
        `SurfaceAbsent`'s own docstring so a consumer can verify the claim
        independently via `signature_forbids_parameters`. A peer whose real
        schema dispatcher exists but simply does not execute `drop_entity`
        (a present, real refusal) raises `ConformanceDenial` with
        `CAPABILITY_UNSUPPORTED` instead -- never `SurfaceAbsent` for that
        case, per the same "adapter は peer の不足を埋めない" discipline
        `create_unique_index`'s docstring already states.
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
    def attempt_cross_entity_batch(
        self, session, operations: Sequence[ScopedBatchOperation]
    ) -> int:
        """Present multiple mutation-vocabulary operations, each scoped to
        its OWN entity (`ScopedBatchOperation.entity`), as ONE real atomic
        unit to the peer's cross-entity entry point -- the contract's
        `cross_entity_mutate` (`POST /v1/data/mutations`-equivalent, port
        v1.7, docs/design/PHASE35_CROSS_ENTITY_AND_CONTRACT_130_V1.md
        section 3) -- and return the whole unit's `affected` count.

        Exists for C-16: `attempt_batch_with_addresses` (above) already
        proves atomic multi-OPERATION batching within one entity; this
        method is the cross-ENTITY sibling C-16 needs to observe atomicity,
        validation ordering, and the `batch_entities` bound when different
        operations in the same unit target different entities. Deliberately
        returns a bare `int`, not a tuple: unlike `attempt_batch_with_
        addresses`, no currently-registered peer that provides this
        capability also declares `row_addressability` (design M-6), so
        there is no `assigned_addresses` concept to observe here at all --
        adding a second return slot this port cannot honestly populate on
        any registered peer would be exactly the kind of adapter-fabricated
        capability design principle 4 forbids.

        Availability is governed by the peer's own declared
        `capability_document()["capabilities"]["cross_entity_mutation"]
        ["status"]`: a status of `"enabled"` or `"partial"` means this
        method presents the request for real and returns/raises whatever
        the peer's real entry point produces (a real `ConformanceDenial`
        for a genuine per-request refusal -- an unsupported operation
        member, a `batch_entities`/`batch_items` bound, a destructive
        delete's declare-and-echo gate, a validation defect on any named
        entity -- never fabricated by this adapter). Any other status (in
        practice, `"unavailable"`) means the capability is not provided at
        all; the adapter then raises `SurfaceAbsent` when no real call on
        the peer's public surface could even receive a cross-entity request
        (confirmed by source inspection, carrying `surface`/
        `forbidden_parameters` per `SurfaceAbsent`'s own docstring), or lets
        a real, present entry point's genuine `ConformanceDenial(
        CAPABILITY_UNSUPPORTED)` propagate when one exists but refuses
        uniformly (the same two-form absence structure `drop_entity`/
        `create_unique_index` already establish on this port, verified via
        `absence.py`'s shared `assert_control_operation_absent_or_
        uniformly_refused`). Every operation in the batch MUST be presented
        to the SAME real call a genuine client sending a multi-entity
        atomic unit would use -- never split into several single-entity
        calls this adapter stitches together itself, which would prove
        nothing about cross-entity atomicity at all (identical discipline
        to `attempt_batch_with_addresses`'s own docstring).
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
