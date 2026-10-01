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
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

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
    """port v1.10 (design docs/design/PHASE6_CONTRACT_160_CLIENT_
    DISCOVERY_V1.md section 6.1 item 1, D-1): `secret` is the COMPLETE
    bearer token for the surface this credential is for -- whatever an
    `issue`/`rotate`/`bootstrap`/`reset` call (in band or out of band)
    returned in its own `secret`-shaped field, held here VERBATIM. An
    adapter presents it to `Authorization: Bearer <secret>` with no
    transformation of any kind; it never composes it FROM `credential_ref`
    (or any other field) and never derives anything BY splitting,
    partitioning, or slicing it -- `credential_ref` is the peer's own,
    separately-returned `credential_id`, held here verbatim as well, never
    extracted from `secret`. This regulation binds every currently-
    registered adapter already (D-1's common realization is additive to
    what the port already required of a well-behaved adapter); it is
    stated here as a port-level rule, and independently re-verified by
    the static, source-level check `test_c19_client_self_sufficiency.py`
    performs across all four adapters (composition/decomposition-absence,
    `xfail(strict=True)` until WP-3 removes the one adapter's own
    remaining composition, design section 6.1 item 1 / section 6.2's own
    "adapter が bearer を組み立ても分解もしないことの静的固定").
    """

    credential_ref: str  # opaque control-plane reference to the credential (the peer's own `credential_id`, verbatim)
    application_id: str
    role: str  # "runtime" | "developer"
    secret: str  # synthetic test value only. Never a real credential. Complete bearer token, verbatim (port v1.10).


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

    port v1.10 (design section 6.1 item 1, D-1): `secret` carries the
    exact same "complete bearer token, held verbatim" meaning
    `CredentialHandle.secret`'s own docstring states above -- a control
    credential is a bearer token for the CONTROL surface rather than an
    application's data surface, never a structurally different kind of
    value. `credential_ref` is the peer's own `credential_id`, held
    verbatim, never extracted from `secret` by this adapter.
    """

    credential_ref: str  # opaque reference (e.g. "ctl_..."), the peer's own credential_id, held verbatim
    secret: str  # synthetic test value only. Never a real credential. Complete bearer token, verbatim (port v1.10).


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

    **Meaning extended for `audit_query` (port v1.8, phase 4 WP-1, design
    docs/design/PHASE4_DURABLE_AUDIT_SINK_V1.md §8.4, work order supplementary
    ruling 1 item 1):** every use of this exception above this note means
    "no Python callable on this peer's public surface could structurally
    receive this request at all", proven by source inspection, never
    assumed. `ConformanceAdapter.audit_query`/`audit_visibility_lag_ms`
    (below) ALSO raise this exception for a
    second, narrower reason: "this deployment's own capability declaration
    says it does not provide the audit surface" (undeclared, or declared
    anything other than `enabled`/`partial`) -- a claim about the peer's
    DECLARED posture, checked by this port's own dispatch before any
    request is presented (declare-first, mirroring C-14's "capability
    refusal precedes every other check"), not only about whether a Python
    callable structurally exists. As of this port revision, before any
    peer implements a real `audit_query` entry point, both readings
    coincide for every currently-registered adapter (there genuinely is no
    callable either way) -- but a future peer that implements a real
    entry point internally while leaving it declared `unavailable` (e.g.
    AUDIT DSN unset, design D-5/M-4's dual posture: the route is still
    registered and would itself answer a directly-issued request with
    `CAPABILITY_UNSUPPORTED`, never a bare 404) still raises this
    exception under the extended reading, even though a real callable now
    exists somewhere on that peer. `absence.py`'s own module docstring
    documents this same extension from the shared-assertion-helper side;
    `conftest`/test code consuming an `audit_query`-shaped `SurfaceAbsent`
    must not assume the classic "genuinely no callable anywhere" reading
    is the only one in play.
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


# Sentinel for `ConformanceAdapter.schema_operation_with_result(..., enum=
# ...)` (port v1.13 追補, contract 1.7.0's own `alter_field` correction --
# 監督裁定 A, `alter_field` の文に足された一文 "A constraint the request
# omits is left as it is; enum: null clears the field's enum, and on
# add_field enum: null means the same as omitting it."). `enum` is
# genuinely tri-state on the wire (`SchemaOperationRequest.enum: ["array",
# "null"]`, contract 1.7.0), and a bare Python `None` default parameter
# cannot distinguish "omit this key" from "send an explicit JSON `null`"
# -- both would otherwise collapse onto the same `None` value. This
# dedicated sentinel class (never a plain string, unlike `VALID_
# CONFIRMATION`/`CATALOG_SURFACE_ABSENT` above: an `enum` value is itself
# an arbitrary `Sequence[Any]`, so a string sentinel could theoretically
# collide with a legitimate declared enum member in a way `confirmation`/
# `catalog_document`'s own narrower domains cannot) makes the third state
# a value nothing else could ever equal.
#
#   enum=None         (default) -> OMIT the `enum` key entirely; on
#                                   `alter_field` this leaves the field's
#                                   existing enum untouched (leg (8),
#                                   `test_c20_constraint_declaration_
#                                   agreement.py`)
#   enum=ENUM_CLEAR              -> carry a literal JSON `enum: null` on
#                                   the wire; on `alter_field` this clears
#                                   the field's enum (leg (9), same file);
#                                   on `add_field` the contract states
#                                   this means the same as omitting it
#                                   entirely
#   enum=<a Sequence>            -> carry `enum: [...]` on the wire,
#                                   exactly as before this addendum
#
# Every adapter's `schema_operation_with_result` resolves this sentinel
# itself (mirrors `_resolve_confirmation` resolving `VALID_CONFIRMATION`):
# `enum is ENUM_CLEAR` -> `op["enum"] = None`; `enum is not None` (and not
# the sentinel) -> `op["enum"] = list(enum)`; `enum is None` -> the key is
# left out of the request body altogether. This is additive only -- every
# pre-existing call site passing a `Sequence` or omitting `enum` keeps its
# exact prior byte-for-byte request shape.
class _EnumClear:
    """Singleton sentinel type for `ENUM_CLEAR`. A dedicated class (not a
    plain string/object()) purely so `repr()` reads as intent rather than
    as a memory address or an easily-mistyped string literal."""

    def __repr__(self) -> str:  # pragma: no cover -- diagnostic only
        return "ENUM_CLEAR"


ENUM_CLEAR = _EnumClear()


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


def _origin(url: str) -> tuple[str, str | None, int | None]:
    """`(scheme, host, port)` of `url` -- design docs/design/
    PHASE6_CONTRACT_160_CLIENT_DISCOVERY_V1.md section 3 D-2's own
    definition of "origin" for co-hosting judgment: "scheme + host + port
    -- not the path". Two URLs sharing an origin under this definition may
    still differ in path (`versioning.base_path`/`control_base_path`),
    which is exactly the point: co-hosting is a PROCESS/HOST fact, not a
    path-identity fact."""
    parts = urlsplit(url)
    return (parts.scheme, parts.hostname, parts.port)


def surfaces_cohosted(document: Mapping[str, Any]) -> bool:
    """port v1.10 (design section 6.1 item 2, D-2): judges whether this
    deployment's control surface is co-hosted with its data-plane surface,
    from a 1.6.0+ peer's own DECLARED `surfaces` origins -- the port-level
    realization of "surfaces を返す peer では origin 比較を正とする" (work
    order WORK_ORDER_PHASE6_CONTRACT_160_V1.md WP-1 item 5(b)).

    Phase 6 WP-3 追補 (supervisor ruling 2026-09-04, brief item D): the
    pre-1.6.0 topology-declaration fallback (`ConformanceAdapter.control_
    surface_cohosted_with_data_plane`, this WP's own final flip target)
    is removed -- both peers now unconditionally declare 1.6.0+ `surfaces`
    (`test_c19_every_control_surface_adapter_declares_1_6_0`, un-xfailed
    in this same commit), so there is no longer any registered adapter
    for which `document` could fail to affirmatively demonstrate a 1.6.0+
    `surfaces` object. This judgment is now surfaces-derived ONLY.

    `document` is any real `CapabilityDocument` this deployment returns
    (the data-plane one and the control one are required, by 1.6.0's own
    unconditional obligation, to carry the SAME `surfaces` object -- so
    either serves this function equally; callers pass whichever they
    already have in hand). A `contract_version` below 1.6.0, or a missing/
    malformed `surfaces`/`surfaces.data.base_url`, now returns `False`
    directly rather than falling back to a since-removed adapter method --
    the SAME value that fallback always returned for every currently-
    registered adapter (its own pre-removal docstring), so this removal
    changes no adapter's observed answer (work order WP-1 completion
    condition 11's own "置換が挙動を変えないことの実測", now load-bearing
    against the fallback's own removal rather than its introduction). This
    function does not itself assert well-shapedness (that is `test_c19_
    client_self_sufficiency.py`'s own D-2 vectors' job).

    When `surfaces.control` is itself absent (a `control_plane:
    unavailable` deployment, contract-permitted to omit it) this returns
    `False` too, matching design's own "there is no co-hosting partner to
    be co-hosted WITH" reasoning (section 3 D-2).
    """
    contract_version = str(document.get("contract_version", "0.0.0"))
    surfaces = document.get("surfaces")
    if not contract_version_at_least(contract_version, "1.6.0") or not isinstance(surfaces, Mapping):
        return False
    data_surface = surfaces.get("data")
    if not isinstance(data_surface, Mapping) or not data_surface.get("base_url"):
        return False
    control_surface = surfaces.get("control")
    if not isinstance(control_surface, Mapping) or not control_surface.get("base_url"):
        return False
    return _origin(str(data_surface["base_url"])) == _origin(str(control_surface["base_url"]))


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
    # port v1.11 (design docs/design/PHASE7_EVIDENCE_REPRODUCIBILITY_AND_
    # PUBLICATION_V1.md D-6.7 C-07 (ii)): carries the contract's own
    # `idempotency_key` (`Mutation.idempotency_key`) through to whatever
    # real entry point already receives the rest of this operation --
    # never interpreted, stored, or compared by the adapter itself,
    # exactly like `expected_revision`/`unique_key` above. Exists ONLY so
    # C-07's declare-first idempotency vector can present a real,
    # key-bearing request and observe the peer's own real refusal (both
    # currently-registered peers declare `idempotency: unavailable` and
    # refuse this key with `CAPABILITY_UNSUPPORTED` before execution) --
    # the positive-side primitive (key generation/storage/replay/result
    # comparison) is deliberately NOT added here (design principle,
    # supervisor ruling S-4): nothing on either peer would exercise it
    # yet, and adding it now would grow the port's surface with no real
    # caller. `None` (the default) omits the key from the presented
    # request entirely, identical to every other optional field here.
    #
    # port v1.13 (design docs/design/
    # PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md §6.1 "port
    # docstring に書く限界" item (v), supervisor ruling S-m): this field is
    # per-ITEM, but the contract's own `idempotency_key` is a REQUEST-level
    # field with no per-operation slot on the wire -- a caller presenting a
    # batch whose operations carry anything other than "every operation the
    # same value" or "every operation none" has described a request this
    # wire shape cannot express. `fold_batch_idempotency_key` (module-level,
    # this file) is the one place that rule is enforced, raising
    # `AssertionError` on a genuine mix rather than silently resolving it;
    # every plug's `attempt_batch_with_result`/`attempt_cross_entity_
    # batch_with_result` folds through it rather than re-implementing the
    # rule per plug.
    idempotency_key: str | None = None


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
    # port v1.11 -- identical field, identical rationale, as `BatchOperation.
    # idempotency_key` above. port v1.13: folded the same way, through the
    # same `fold_batch_idempotency_key`, by `attempt_cross_entity_batch_
    # with_result`.
    idempotency_key: str | None = None


def apply_limits_override(limits: Any, overrides: Mapping[str, int] | None) -> Any:
    """Shared plumbing (not normative -- this module's own header docstring:
    everything but the ABC, value types, `Fixture`/`TamperVector`/the batch
    dataclasses, and the `MUST_COVER_*` constants is shared plumbing both
    the common suite and peer adapters may use). Returns `limits` unchanged
    when `overrides` is `None`/empty; otherwise returns `dataclasses.
    replace(limits, **overrides)` -- a shallow copy naming only the fields
    `overrides` supplies, every other field left exactly as `limits`
    already had it.

    Exists for `isolated_control_surface(limits_override=...)` (port v1.11
    addendum, supervisor ruling 2026-09-06 item 1, design docs/design/
    CONFORMANCE_ADAPTER_V1.md §21.4): both peers' own `ControlPlaneLimits`
    dataclasses (`r2db_api.limits.ControlPlaneLimits`, `mitatedb_api.
    control_plane.ControlPlaneLimits`) are frozen dataclasses sharing the
    same 3 control-plane field names (`applications`, `credentials_per_
    application`, `control_requests_per_minute`) this addendum's only
    caller ever overrides -- one shared, type-agnostic `dataclasses.
    replace` call serves every in-process plug without either peer
    importing the other's concrete limits type, and without this common-
    suite module importing either.
    """
    if not overrides:
        return limits
    return replace(limits, **dict(overrides))


def fold_batch_idempotency_key(operations: "Sequence[BatchOperation | ScopedBatchOperation]") -> str | None:
    """Shared plumbing (port v1.13, design docs/design/
    PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md §6.1 "port
    docstring に書く限界" item (v), supervisor ruling S-m). Folds the per-
    item `idempotency_key` field every `BatchOperation`/`ScopedBatchOperation`
    in `operations` carries (port v1.11) down to the single value the
    contract's own `idempotency_key` actually is: `MutationRequest.
    idempotency_key`/`ScopedMutationRequest.idempotency_key` are REQUEST-
    level fields -- there is no per-operation slot for it anywhere on the
    wire (`additionalProperties: false` on `Mutation`/`ScopedMutation`
    leaves no room for it) -- while this port's own `BatchOperation`/
    `ScopedBatchOperation` dataclasses carry it per item, purely so a
    caller building a batch from what would otherwise be several separate
    single-operation calls does not need a second, batch-specific way to
    say "this request's key is X" (each single-operation primitive already
    takes it, where it takes it at all, as a plain keyword).

    The one request-level value `operations` can honestly be sent as is
    therefore constrained to two shapes: every operation carries the exact
    same `idempotency_key` value, or none of them carries one at all. A
    caller presenting anything else -- two operations with two DIFFERENT
    non-`None` keys, or a mix of one key-bearing operation and one bare
    one, within what is meant to be a single atomic request -- has
    described a request this wire shape cannot actually express, not a
    request this function may silently resolve by picking one value and
    discarding the rest: doing so would make the suite exercise a
    different request than the one the caller thinks it built, silently.
    This function refuses that outright: it raises `AssertionError` (a
    port-usage error, caught by no `ConformanceDenial` machinery, exactly
    like a caller error anywhere else in this module) naming every distinct
    value observed, rather than folding a mixture down to "the first one"
    or "the last one" the way an unguarded `next(...)` generator expression
    would (the exact form every one of this port's own 4 concrete plugs
    used before this port revision -- each replaced with a call to this
    function so the uniform-or-absent rule is enforced once, identically,
    everywhere, rather than re-implemented per plug with a chance of
    drifting apart).

    Returns `None` when `operations` is empty or when every operation's
    `idempotency_key` is `None` (no key presented at all); otherwise
    returns that one shared value.
    """
    keys: set[str | None] = {op.idempotency_key for op in operations}
    if len(keys) > 1:
        raise AssertionError(
            "fold_batch_idempotency_key: BatchOperation.idempotency_key/"
            "ScopedBatchOperation.idempotency_key must be uniform across one request's "
            "operations -- every operation the same value, or every operation none -- "
            f"but got {sorted(repr(k) for k in keys)}. The contract's own idempotency_key "
            "is a REQUEST-level field with no per-operation slot on the wire; a caller "
            "mixing distinct values (or a value alongside an absent one) across "
            "operations of what is meant to be ONE request has described a request this "
            "wire shape cannot express, not one this function may resolve by picking one "
            "value and silently discarding the others."
        )
    if not keys:
        return None
    return next(iter(keys))


@dataclass(frozen=True)
class IsolatedControlHandle:
    """Yielded by `isolated_control_surface()` (port v1.11 addendum,
    supervisor ruling 2026-09-06 item 1, design docs/design/
    CONFORMANCE_ADAPTER_V1.md §21.4). Calling the handle itself
    (`handle(actor)`) is exactly `handle.capabilities(actor)` -- the
    ORIGINAL, sole capability this primitive offered before this addendum
    (phase 6 WP-1 addendum A), preserved unchanged so the `control_
    requests_per_minute` vector's own pre-existing call site
    (`isolated_call(actor)`) needs no edit. `register_application`/
    `list_applications` are the two additional operations the
    `applications` vector needs (supervisor ruling 2026-09-06 item 1) to
    drive registrations against the SAME isolated, small-limit surface
    without spending the shared adapter's own `control_requests_per_
    minute` window -- both dispatch against the identical fresh control-
    plane instance `capabilities`/`handle()` targets, sharing its own
    isolated rate window and its (possibly overridden) `applications`
    bound, never the shared surface's.

    Deliberately NOT `capability_document`/full `ConformanceAdapter`
    shaped, unlike `isolated_application_surface()`'s own yield: this
    primitive's own drive recipe needs only these three operations (the
    control-plane analogue of D-6.2's application-plane recipe), so this
    handle presents exactly those, not a bespoke stand-in for the whole
    port.
    """

    capabilities: Callable[["CredentialHandle | ControlCredentialHandle"], Mapping[str, Any]]
    register_application: Callable[["CredentialHandle | ControlCredentialHandle", str], Mapping[str, Any]]
    list_applications: Callable[["CredentialHandle | ControlCredentialHandle"], Sequence[Mapping[str, Any]]]

    def __call__(self, actor: "CredentialHandle | ControlCredentialHandle") -> Mapping[str, Any]:
        return self.capabilities(actor)


@dataclass(frozen=True)
class IdempotencyHold:
    """Yielded by `hold_after_idempotency_lookup()`'s own `with` block
    (port v1.15, design docs/design/PHASE10_DEPLOYMENT_EVIDENCE_V1.md §3
    D-13 "実装の形 (6d-ii) の確定" (2)). Non-normative, the same status
    `IsolatedControlHandle` above already carries for its own kind of
    yielded handle -- this port prescribes only what `wait_until_held`
    does, never this class's own shape beyond that one method.

    `wait_until_held(timeout_s=30.0) -> int`: blocks until the ONE held
    request `hold_after_idempotency_lookup` is arming has actually
    reached the stall point at the end of its own idempotency admission
    window (see that method's own docstring), then returns the REAL
    measured count of requests held there (always `1` for a correct
    realization -- this primitive holds exactly one request, never
    more) -- never a bare echo of an argument this method does not even
    take (`hold_in_flight`'s own `entered_count`/裁定 5 rationale,
    carried over unchanged: a caller must be able to tell "did this
    primitive actually hold something" without a tautological check).
    Raises `AssertionError` -- never skips, never times out silently --
    if the held request has not reached that point within `timeout_s`
    seconds (`OPERATING_CONDITIONS.md` §1.3 の 26)."""

    _wait_until_held: Callable[[float], int]

    def wait_until_held(self, timeout_s: float = 30.0) -> int:
        return self._wait_until_held(timeout_s)


@dataclass(frozen=True)
class PlanVerificationHold:
    """Yielded by `hold_after_plan_verification()`'s own `with` block
    (port v1.20, design docs/design/MITATEDB_APPLICATION_SERIALIZATION_V0_1.md
    section 9's `conformance-tests/` paragraph and section 11.1 Q-5).
    Non-normative, the same status `IdempotencyHold` above carries: this
    port prescribes only what `wait_until_held` does, never this class's
    own shape beyond that one method. It has the same shape as
    `IdempotencyHold` and is a separate type only so that neither
    primitive's yielded handle reads as the other's.

    `wait_until_held(timeout_s=30.0) -> int`: blocks until the ONE held
    schema operation `hold_after_plan_verification` is arming has actually
    reached the stall point (see that method's own docstring), then
    returns the REAL measured count of schema operations held there
    (always `1` for a correct realization -- this primitive holds exactly
    one, never more), never a bare echo of an argument. Raises
    `AssertionError` -- never skips, never times out silently -- if no
    schema operation has reached that point within `timeout_s` seconds
    (`OPERATING_CONDITIONS.md` §1.3 の 26)."""

    _wait_until_held: Callable[[float], int]

    def wait_until_held(self, timeout_s: float = 30.0) -> int:
        return self._wait_until_held(timeout_s)


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
    """Common port ABC every peer plug implements (see this module's own
    header docstring for the port's overall contract).

    port v1.13 (design docs/design/
    PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md §6.1) adds five
    methods below (`schema_operation_with_result`, `attempt_mutation_with_
    result`, `attempt_batch_with_result`, `attempt_cross_entity_batch_with_
    result`, `query_with_budget`), additive only -- no existing method's
    signature or return type changes. §6.1 requires this docstring
    (WP-1b rework, review point K: a `#` comment block is not a docstring)
    to state five limits, verbatim in substance (design's own Japanese,
    restated here in this module's own English) -- every one of the five
    new methods above is bound by all five:

    (i) `dry_run`'s "zero externally visible state change" is bounded by
        what an adapter can actually observe -- rows, catalog, schema
        revision, and (where `audit_query` is available) audit events.
        Consumption of a non-transactional address sequence is possible
        but not asserted by any of these methods (permitted, not
        required, design D-4 開示事項).
    (ii) `plan` is opaque: every method here, and every caller of them,
         treats it as a value to pass through and compare for equality
         only -- never a structure to parse or construct.
    (iii) `dry_run`/`plan`/`budget` are each exactly one value per
          request, never one per operation -- they are keyword-only
          parameters on these request-level methods, not fields on
          `BatchOperation`/`ScopedBatchOperation`.
    (iv) `budget` narrows a deployment's own declared bound DOWNWARD
         only -- no method here, and no caller, may use it to raise a
         bound above what the deployment itself declares.
    (v) `BatchOperation.idempotency_key`/`ScopedBatchOperation.
        idempotency_key` are per-ITEM fields, but the contract's own
        `idempotency_key` is a per-REQUEST field: the operations
        presented in one call to `attempt_batch_with_result`/`attempt_
        cross_entity_batch_with_result` must carry either the identical
        key on every operation, or no key on any operation at all.
        `fold_batch_idempotency_key` (module-level, above) is where that
        rule is enforced -- a genuine mixture is a port-usage error,
        raised as `AssertionError` with a reason, never silently
        resolved by picking one value. port v1.13 rework (WP-1b, review
        point H): every one of this port's own 4 concrete plugs' batch-
        shaped methods (`attempt_batch_with_addresses`/`attempt_cross_
        entity_batch` alongside the newer `_with_result` siblings) folds
        through this same function -- none re-implements the rule with an
        unguarded `next(...)` or a raw per-item value.
    """

    name: str

    # port v1.14 (design docs/design/PHASE10_DEPLOYMENT_EVIDENCE_V1.md
    # D-1 (A) 4, WP-3): which transport this plug's own client actually
    # dials through -- `"in_process"` (drives the peer's product objects
    # directly, no ASGI/HTTP boundary at all), `"asgi"` (an in-process
    # ASGI transport, `httpx.ASGITransport` -- no real socket), or
    # `"socket"` (a real loopback TCP socket, fronted by a real reverse
    # proxy -- `conformance-tests/socket_harness.py`). Deliberately a bare
    # annotation with NO default: every currently-registered adapter
    # declares its own value explicitly (one class-attribute line each,
    # e.g. `transport_kind = "in_process"`), and a future adapter that
    # forgets to declare it fails LOUDLY (`AttributeError` on first read),
    # never silently inheriting a fallback that could misclassify it (
    # `tools/perf_baseline.py`'s own `_classify_plug` reads this
    # declaration rather than guessing from the adapter's name or
    # attribute shape, design D-12; `test_c19_client_self_sufficiency.py`'s
    # real-dial branch and `test_socket_harness.py`'s own
    # `test_every_registered_adapter_declares_transport_kind` both depend
    # on this attribute never carrying a default here).
    transport_kind: str

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
    def tampered_bearer(self, handle: "CredentialHandle | ControlCredentialHandle") -> str:
        """port v1.10 追補 (supervisor ruling 2026-09-04, brief item C):
        returns a bearer string that names the SAME credential `handle`
        does (`handle.credential_ref`) but does NOT authenticate -- a
        digest mismatch on an otherwise-real, known `credential_id`, the
        common-suite's own synthetic stand-in for "an attacker who knows
        a real credential_id but not its secret" (`test_c15_bootstrap_
        reset_lifecycle.py`'s own bogus-actor vector). This is PLUG-
        SPECIFIC knowledge (this port never assumes a peer's own bearer
        SHAPE) -- both currently-registered peers happen to use the same
        `<credential_id>.<secret>` locator form, so both plugs realize
        this identically (`f"{handle.credential_ref}.{fresh_identifier(...)}"`),
        but a future peer with a different bearer shape implements this
        however its own real wire format requires; the port itself makes
        no assumption about that shape.

        The ONLY place ANY adapter composes a bearer string (D-1(d)'s
        "no composition, no decomposition" regulation binds every OTHER
        method on this port) -- `test_c19_client_self_sufficiency.py`'s
        own static fixed test (`test_c19_adapters_never_compose_or_
        decompose_the_bearer_secret`) allowlists exactly the composition
        line(s) inside each plug's own `tampered_bearer` implementation,
        by (path, lineno), with this stated reason -- never a blanket
        exemption for the whole file. A real client never constructs a
        bearer this way (or any way -- D-1(d)'s own "credential is
        Never Composed, Split, or Derived by a Client"); this exists
        purely so the common suite can construct a KNOWN-BAD credential
        without dialing into a peer's own internal store, exactly the
        same test-harness-only privilege `revoke_credential`/`control_
        credential` above already exercise."""
        ...

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

        port v1.10 (D-1): the peer's real response carries `credential_id`
        and `secret` as two SEPARATE fields; the adapter places each,
        UNCHANGED, into `CredentialHandle.credential_ref`/`.secret`
        respectively -- it never concatenates them into one string first
        and never derives one from the other. `CredentialHandle.secret`'s
        own docstring states the general "verbatim, never composed or
        split" regulation this method's return value is a first instance
        of.
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

        port v1.10 (D-1): whatever `secret`-shaped field the returned
        response carries is the fresh credential's new COMPLETE bearer
        token, to be used verbatim (`CredentialHandle.secret`'s own
        docstring) -- a caller building a fresh handle from this response
        (e.g. `ControlCredentialHandle(credential_ref=<the same
        credential_ref this call rotated>, secret=<the response's own
        secret field, read directly>)`) never re-derives `credential_ref`
        from the new secret; `credential_ref` does not change on rotation
        and the caller already has it from before this call.
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

        port v1.10 (D-1): the returned `ControlCredentialHandle.secret` is
        this fresh control credential's COMPLETE bearer token, held
        verbatim -- an adapter reads `credential_id` and `secret` as the
        two separate fields the ritual mechanism's own real output carries
        (a CLI's two separate stdout lines, or a direct function call's
        two separate return values) and places each unchanged into
        `credential_ref`/`secret` respectively, never concatenating or
        splitting either.
        """

    @abstractmethod
    def reset(self) -> ControlCredentialHandle:
        """Executes the peer's real out-of-band reset ritual (design
        section R-5) and returns the resulting control credential. Same
        "real mechanism, no fabrication" contract as `bootstrap`, including
        `bootstrap`'s own port v1.10 verbatim-secret/separate-fields
        regulation above.
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

    @abstractmethod
    def isolated_control_surface(
        self, *, limits_override: Mapping[str, int] | None = None,
    ) -> AbstractContextManager["IsolatedControlHandle"]:
        """C-14 vector 5's OWN test primitive (phase 6 WP-1 addendum A,
        supervisor ruling 2026-09-04; extended port v1.11 addendum,
        supervisor ruling 2026-09-06 item 1 -- design docs/design/
        CONFORMANCE_ADAPTER_V1.md §21.4) -- **not a contract capability**.
        A context manager that, on entry, builds a FRESH, throwaway
        control surface sharing this adapter's own real registered
        application/credential state (the SAME backend/store objects
        `control_credential()`'s own actor already authenticates against)
        but starting from its OWN, EMPTY `control_requests_per_minute`
        rate window -- and yields an `IsolatedControlHandle` presenting
        `control_capabilities`/`register_application`/`list_applications`-
        equivalent requests to THAT surface (the same real entry points/
        evaluation order every other control-plane read on this ABC
        already uses, just against a second, isolated instance of them),
        returning the peer's real response on success or raising
        `ConformanceDenial` (most commonly `LIMIT_EXCEEDED` once the
        ISOLATED surface's own declared bound is reached) exactly as the
        shared-surface equivalents do. Calling the handle itself
        (`handle(actor)`) is `handle.capabilities(actor)`'s exact
        equivalent -- the ORIGINAL, sole shape this primitive had before
        this addendum, preserved unchanged so the `control_requests_per_
        minute` vector's own call site needs no edit.

        `limits_override` (port v1.11 addendum, supervisor ruling
        2026-09-06 item 1): optional, keyword-only, `None` by default
        (every existing call site is therefore unaffected). When given, a
        mapping from a subset of this peer's OWN control-plane resource-
        class field names (at minimum `applications`, since that is the
        one class this addendum's own caller needs small -- `r2db_api.
        limits.ControlPlaneLimits`/`mitatedb_api.control_plane.
        ControlPlaneLimits` are the two concrete field-name universes) to
        the small value the ISOLATED surface's own limits profile should
        declare and enforce INSTEAD of the shared surface's own (typically
        much larger, conformance-buildable-but-expensive-to-actually-
        drive) value for that field -- every field NOT named in the
        mapping keeps the shared surface's own value, unchanged. The
        isolated surface's own `capabilities(actor)`/`handle(actor)` call
        reports the OVERRIDDEN value for an overridden field: the
        declaration and the surface under test are always the same
        instance's, exactly the same discipline `isolated_application_
        surface()`'s own `capability_document()` already follows for the
        application plane. Exists so a resource class whose declared
        bound is high enough to be expensive to drive to exhaustion (e.g.
        `applications`, in the hundreds on a real conformance build) can
        still be driven to its EXACT declared bound in a handful of calls,
        never touching the SHARED surface's own `control_requests_per_
        minute` window at all (supervisor ruling 2026-09-06 item 1 -- the
        diagnosed cause of a real, measured cross-test failure: driving
        `applications` to a three-digit bound on the shared surface alone
        consumed enough of the shared rpm window to starve unrelated
        tests sharing it within the same run).

        `register_application`/`list_applications` on the yielded handle
        dispatch against the SAME isolated instance `capabilities`/
        `handle()` targets -- so they share its rate window (never the
        shared surface's) and its (possibly overridden) `applications`
        bound -- but they still write into and read from the SAME
        underlying application registry `provision_application`/
        `register_application_inband`/`list_applications` on `self` (the
        shared surface) already observe: a caller reading `handle.
        list_applications(actor)` sees every application registered
        anywhere on this backend, isolated-surface-driven or not (the
        identical sharing `isolated_control_surface()` already documented
        for `control_credential()`'s own actor, extended here to the
        registry itself). A caller computing a headroom-style expected-
        success count against an overridden `applications` bound MUST
        therefore read the current count through THIS handle first
        (`handle.list_applications(actor)`) and subtract it from the
        override, the same position-arithmetic discipline the
        `control_requests_per_minute` vector already applies to its own
        (always-empty) isolated rate window.

        Every application `register_application` on this handle registers
        successfully is this primitive's OWN responsibility to remove: on
        `with`-block exit, it deprovisions every one of them AFTER
        releasing whatever connection pool(s) it opened (WP-5 rework,
        supervisor ruling 2026-09-06 item 2: corrected from an earlier
        "before releasing..." wording that had the order backwards --
        `close -> deprovision`, matching both HTTP plugs' own `finally`
        blocks, which close the client/connection pool first and only
        then deprovision, and matching `docs/design/CONFORMANCE_ADAPTER_
        V1.md` §21.4's own corrected description of this same order) --
        the peer's real, out-of-band `deprovision_application` path,
        exactly the way a caller of `isolated_control_surface()` before
        this addendum never needed to clean up anything at all. A caller
        must NOT also deprovision an application it registered through
        this handle -- that would be a double deprovision attempt against
        an application this primitive has already removed.

        Exists so exhausting `control_requests_per_minute` to its exact
        declared bound (the only way to observe the peer's own real
        `LIMIT_EXCEEDED` at the exact position the declared bound
        predicts) does not poison the SHARED, session-scoped adapter's
        own rate window for every later test/vector that depends on it --
        previously mitigated only by a real 60-second wait for the shared
        window to roll over (`test_c14_authority_boundary.py`'s own,
        pre-addendum-A `time.sleep(61)`), which this primitive makes
        unnecessary rather than merely faster.

        On exit, releases whatever real resources building the isolated
        surface opened (an HTTP+PostgreSQL plug's own fresh connection
        pools in particular -- mirrors `_build_control_stack()`'s own
        `stores.close()` discipline; an in-process plug's isolated
        `ControlPlaneService` needs no explicit release). Never mutates,
        rebuilds, or otherwise disturbs the adapter's own SHARED control
        surface (`control_credential()`/`control_capabilities()`'s own
        target) -- the isolated surface is additive, constructed
        alongside it, sharing only read/write access to the same
        underlying application/credential state, never replacing it.
        """

    @abstractmethod
    def isolated_application_surface(self) -> AbstractContextManager["ConformanceAdapter"]:
        """C-05's OWN test primitive (port v1.11, design docs/design/
        PHASE7_EVIDENCE_REPRODUCIBILITY_AND_PUBLICATION_V1.md D-6.1 V2) --
        the application-plane sibling of `isolated_control_surface()`
        above, but shaped differently on purpose (design review 1, B-5):
        that method yields a single callable because its own drive class
        (`control_requests_per_minute`) is the only one it ever needs to
        present; the application plane's own drive recipes (D-6.2) need
        row insertion, entity/schema-object creation, batch mutation,
        cross-entity batch mutation, and query, plus a read of the
        isolated instance's OWN `capability_document()` -- more surface
        than any single callable could honestly present. A context
        manager that, on entry, builds a FRESH, throwaway data-plane
        instance bound to its OWN, small conformance profile (its own
        `limits`/resource-class configuration, deliberately small enough
        for C-05's V2 vectors to drive every applicable class past its
        declared bound within one test) and yields a SECOND, self-similar
        object that itself conforms to this exact `ConformanceAdapter`
        ABC -- a test drives it with the SAME ordinary port operations
        (`authenticate`/`create_entity`/`insert`/`attempt_batch_with_
        addresses`/`attempt_cross_entity_batch`/`select_eq`/`attempt_
        filter`/`capability_document`/...) it already uses against the
        shared, session-scoped adapter, never a bespoke, drive-recipe-
        specific method added to this port. `capability_document()` read
        against the YIELDED instance is what C-05 V2 compares its own
        drive's observed refusal position against -- this is this
        primitive's entire reason to exist: the declaration and the
        surface under test must be the SAME instance's, never a shared
        surface's declaration compared against a different, isolated
        surface's behavior (or vice versa).

        Constructed the same way `isolated_control_surface()` is
        constructed for a peer with no real control-plane composition
        root to reuse (design D-6.5 "Q4 確定後の追補"): a direct,
        out-of-band construction of this peer's own service/foundation
        object, never the peer's real composition root
        (`main.py`'s `build_app`/`MitateDB-api`'s `build_control_
        service`) -- reaching for the composition root here would pull in
        requirements (platform-declaration reads, writer-role checks,
        deprecated-env rejection) this primitive has no need of and, for
        at least one plug, cannot even satisfy (no way to inject a small
        `limits` profile through that path at all).

        Resource-sharing shape differs by plug (D-6.5 addendum's own
        "(推測)" point -- WP-4 decided it by measurement, corrected here
        WP-4 rework 2026-09-06, 差し戻し 2 巡目, F-port-docstring: this
        paragraph previously claimed uniform "shares nothing", which was
        true for the two in-process plugs but FALSE for the two HTTP
        plugs). **In-process** (`r2db-api`, `MitateDB-api`): the isolated
        instance is built from a wholly fresh service/foundation object
        with NO reference back to the shared, session-scoped adapter at
        all -- every credential, application, and cell registry it touches
        is its own, genuinely private, from construction through exit.
        **HTTP** (`r2db-api-http`, `MitateDB-api-http`): the isolated
        instance is a SHALLOW copy (`copy.copy(self)`) of the shared
        adapter -- only the DATA-plane pieces (the `DataService`/
        `ControlAuthority` pair, the ASGI app, the httpx client, and the
        per-application cell registry) are freshly constructed and bound
        to the SMALL profile; the control-plane client/app, the credential
        stores, and the shared, already-bootstrapped PostgreSQL PLATFORM
        database are the SAME objects the shared surface already holds.
        This borrowing is deliberate, not an oversight: the isolated
        instance's own in-band `issue_credential()` is itself a real
        `/control/v1/credentials` HTTP call, and it needs the shared
        control-plane state to authenticate at all -- re-bootstrapping a
        second platform per isolated surface would add real PostgreSQL
        provisioning cost for no isolation benefit the small `limits`
        profile does not already provide (D-6.5 addendum: "この経路が要求
        するものは無し", no EXTRA platform seed is needed). One concrete
        consequence: the isolated instance's own `provision_application`
        writes into the SAME shared platform `applications` registry table
        the shared surface (and C-14's own vectors) read -- so, on exit,
        the isolated instance deprovisions every application ID it itself
        provisioned (never touching any application the shared surface
        provisioned), so this borrowing never accumulates across the many
        isolated surfaces one C-05 run opens and closes in sequence. In
        both shapes, the whole point of the SMALL profile is a low-
        cardinality surface a V2 drive can genuinely exhaust; only the
        HTTP plugs additionally share control-plane/platform state that
        this primitive's own drives never exhaust (they never touch
        `applications`/`credentials_per_application` bounds), so sharing
        it costs nothing to the positional exactness V2 depends on.

        Test code obtains its own application/credential state against
        the yielded instance the ordinary way (`provision_application`/
        `issue_credential`), exactly as it would against the shared
        adapter -- this primitive contributes only the ISOLATION and the
        SMALL profile, never a shortcut around the normal port dispatch
        it otherwise makes available.

        On exit, releases whatever real resources building the isolated
        instance opened (an HTTP+PostgreSQL plug's own fresh connection
        pool(s); an in-memory plug's own live per-cell connection(s) --
        design D-6.6/D-6.5 addendum (3)); never mutates, rebuilds, or
        otherwise disturbs the adapter's own SHARED application surface.

        Design condition 13(b) choice, stated here per that condition's own
        instruction ("どちらを採ったかを port の docstring に明記する"):
        C-05's own V2 drivers each open a FRESH instance of this primitive
        PER driven class -- no two classes' drives ever share one isolated
        instance. This is the "class ごとに新しい isolated_application_
        surface() を張る" branch, not the alternative (one shared isolated
        instance across classes, requiring a checked headroom precondition
        for every later class's drive to account for what earlier classes'
        drives already consumed of a shared rate window). The one exception
        that DOES need (and asserts) a headroom precondition is `requests_
        per_minute`'s own driver, entirely WITHIN its own single isolated
        instance: setup traffic (`create_entity`/an HTTP plug's own
        `authenticate()` round trip) against that SAME instance can consume
        part of the very rate window the drive then measures.
        """

    @abstractmethod
    def hold_in_flight(self, session, n: int) -> AbstractContextManager[int]:
        """n 個の application plane 要求を、service の in-flight 窓の内側で停止させたまま保持する。保持中に n+1 個目を出すと `LIMIT_EXCEEDED`(`concurrency`) で拒否される。解放後、保持していた n 個はすべて正常に完了する。

        Verbatim above (Phase 8 WP-1 rework 3, 裁定 1, 監督裁定 2026-09-07):
        docs/design/PHASE8_EFFECTIVE_BOUNDS_AND_HYGIENE_V1.md §3 D-2
        決定 1's own sentence, carried into this port docstring
        unparaphrased per 常設規律 4 (word-for-word from `phase8-ruling-
        verbatim.txt`'s own quoted copy of that decision -- see also
        `docs/design/CONFORMANCE_ADAPTER_V1.md` §22.1, which makes the
        same claim about this docstring and must stay true of it).

        Implementation detail this port adds beyond that sentence (the
        design text above leaves the exact stall point to the port): the
        stop point sits AFTER the concurrency counter is acquired and
        BEFORE DB execution (concurrency カウンタ取得後、DB 実行前).

        - `with` の内側では、n 個が in-flight のまま保持されている。
        - その状態で通常の port 操作を 1 つ出すと `ConformanceDenial`
          (`LIMIT_EXCEEDED` / `details.limit_class == "concurrency"`) になる。
        - `with` を抜けると保持していた n 個はすべて解放され、正常に完了する
          (例外を上げない)。抜ける時点で n 個の完了を待ち合わせる。
        - `n` は、この instance が宣言する `limits.concurrency` 以下でなければ
          ならない (呼び出し側が assert する)。
        - `as` で束縛される値 (`AbstractContextManager[int]`) は、実際に
          stall point へ到達したと実測された保持数 (`entered_count`,
          `threading.Semaphore`経由の実測値であって `n` の単なるコピーでは
          ない) を返す -- Phase 8 WP-1 rework 3 (裁定 5, 監督裁定
          2026-09-07): 呼び出し側がこの primitive を実際に何か保持したかを
          非トートロジーに確認できるようにするため。実測が `n` 未満なら
          既にこの primitive 自身が `AssertionError` を上げている (各
          realization 自身の docstring 参照) ので、正常に `yield` された
          時点でこの値は常に `n` と一致する -- それでも、呼び出し側の
          assert は `n` を折り返すのではなく、この実測値そのものを見る。

        port v1.12 (design docs/design/PHASE8_EFFECTIVE_BOUNDS_AND_HYGIENE_
        V1.md D-2, work order docs/work-orders/WORK_ORDER_PHASE8_EFFECTIVE_
        BOUNDS_V1.md §2 WP-1b): `isolated_application_surface()`'s own
        sibling primitive for the ONE application-plane resource class no
        prior port revision could drive at all -- `concurrency`. C-05's
        own `_drive_concurrency` calls this against a FRESH `isolated_
        application_surface()` instance, exactly like every other V2
        driver in that file.

        Called against the YIELDED instance of `isolated_application_
        surface()`, never against the shared, session-scoped adapter --
        the same convention every other drive-recipe method on this ABC
        already follows.

        Three points this instruction's own three bullets above leave
        undecided, disclosed here (also carried into `conformance-tests/
        CONDITIONS.md`'s own C-05 row):

        (i) The concurrency this creates is IN-PROCESS concurrency only --
            every one of the 4 registered plugs realizes this primitive
            with real OS threads calling straight into the same process's
            own service/foundation object (an HTTP plug's own `httpx.
            AsyncClient(ASGITransport(app))`, never a real socket) -- not
            concurrency across a real socket or a reverse proxy. Genuine
            wire-level concurrency is out of this primitive's scope until
            L7-2 (a future phase's own multi-plug/real-transport work).
        (ii) The in-process `MitateDB-api` plug runs at most one
             operation PER CELL at a time (its `SQLiteBackend` holds one
             `RLock` for each request scope) -- this primitive's own stop
             point sits BEFORE that lock is acquired (concurrency-
             counter-side, not lock-side), so holding N > 1 in-flight
             requests against ONE cell is still structurally possible
             (the held requests simply queue behind the lock once
             released), but the `concurrency` bound that plug declares is
             therefore a REFUSAL THRESHOLD, not a claim of N-way parallel
             EXECUTION capacity. `MitateDB-api-http` holds no such lock:
             a cell's operations run in parallel on its per-role
             connection pools.
        (iii) The scope of the counter this primitive holds open (a
              per-deployment in-flight counter; a per-credential rate
              window) is not something the common suite can observe
              directly -- the isolated surface's own application/
              credential population is deliberately small (often exactly
              one of each), so no drive here distinguishes "one counter
              shared by every application on this deployment" from "one
              counter per application" from the OUTSIDE.

        An adapter realizes the stop point by wrapping the real cell/
        backend object it already constructs out-of-band for `isolated_
        application_surface()` -- never by adding a test-only hook, delay
        endpoint, or callable to the peer's own PRODUCT code (design §4).
        See each plug's own implementation comment for exactly which
        object is wrapped and why that wrap point sits inside the
        concurrency counter's own window.
        """

    @abstractmethod
    def hold_after_idempotency_lookup(self, session, idempotency_key: str) -> AbstractContextManager["IdempotencyHold"]:
        """`session` 上で次に到着する、`idempotency_key` に一致する key を持つ要求を 1 件だけ、その要求自身の **idempotency 受理区間の末尾**で停止させたまま保持する。受理区間の末尾とは、照会が「記録なし」を返し、`idempotency_entries` の予約を取り終え、その区間が取った lock をすべて保持したまま、効果をまだ 1 件も実行していない地点である。保持中に同じ key を持つ 2 件目の要求を出すと、2 件目はその同じ lock の上で実際に待ち、先着が解放されて commit した後にはじめて答えを返す。`with` を抜けると先着は解放され、実行・記録・commit まで進む。保持するのは 1 件だけであり、`idempotency_key` に一致しない要求は素通しする。

        Verbatim above (常設規律 4, word-for-word from design docs/design/
        PHASE10_DEPLOYMENT_EVIDENCE_V1.md §3 D-13 "実装の形 (6d-ii) の
        確定" (1)'s own quoted contract text -- see also that same
        section's own claim that this docstring stays true of it, the
        same convention `hold_in_flight`'s own docstring above already
        follows for its own §22.1 citation).

        port v1.15 (design docs/design/PHASE10_DEPLOYMENT_EVIDENCE_V1.md
        D-13, work order docs/work-orders/WORK_ORDER_PHASE10_DEPLOYMENT_
        EVIDENCE_V1.md WP-6d-ii): new condition C-27's own driving
        primitive -- "同一 idempotency key 同時送信" decisively serialized
        by an adapter hook, the same "test-driving primitive, never a
        test-only hook on product code" discipline `hold_in_flight`
        above already establishes, applied to the idempotency admission
        window instead of the concurrency counter.

        Structural difference from `hold_in_flight` (design D-13 "実装の
        形 (6d-ii) の確定" (2)): this primitive never issues any request
        of its own. The held request ("A") and the second, waiting
        request ("B") are both issued by the CALLER, each from its own
        OS thread -- this method only arms the ONE stall point and
        yields the `IdempotencyHold` handle a caller uses to wait for A
        to actually reach it (`IdempotencyHold.wait_until_held`, above).
        A caller confirms B has not completed while A is held with a
        bounded wait window of its own -- the same shape both peers'
        own `tests/test_idempotency_concurrency.py::_assert_second_
        call_is_blocked` already uses.

        `with` を抜けると先着は解放され (design's own sentence above) --
        exiting the `with` block releases the ONE held request
        regardless of whether `wait_until_held` was ever called: a
        caller that never confirms the hold reached its stall point
        before exiting has simply not verified anything about non-
        vacuity, exactly as a caller of `hold_in_flight` that never
        awaits `entered_count` has not.

        `idempotency_key` に一致しない要求は素通しする (design's own
        sentence above) -- a request whose `idempotency_key` differs
        from this call's argument, or whose lookup found an EXISTING
        record (a replay or a `CONFLICT`, never a fresh admission),
        reaches its own normal outcome undisturbed; this primitive only
        ever stalls the ONE request that is both key-matching and
        genuinely fresh (design D-13 "実装の形 (6d-ii) の確定" (3): the
        stall point sits at the END of the admission window, after the
        `idempotency_entries` reservation, specifically so observation
        (iii)'s own count-bound race is not silently serialized by the
        caller's own test orchestration instead of by the real lock this
        primitive is meant to exercise).

        Called against the YIELDED instance of `isolated_application_
        surface()`, never against the shared, session-scoped adapter --
        the same convention `hold_in_flight` above already follows.

        See each plug's own implementation comment (design D-13 "実装の
        形 (6d-ii) の確定" (4)) for exactly which method(s) are wrapped,
        why the wrap point sits at the end of the admission window on
        that peer's own structure, and what a second, key-matching
        request actually waits on while this primitive holds the first.
        """

    @abstractmethod
    def hold_after_plan_verification(self, session) -> AbstractContextManager["PlanVerificationHold"]:
        """`session` 上で次に到着する、`plan` または `dry_run` を提示する schema 操作を 1 件だけ、その要求自身が plan の照合に使う現在の revision を読み終え、その読みが取った lock をすべて保持したまま、DDL をまだ 1 文も実行していない地点で停止させたまま保持する。保持中に同じ Application への 2 件目の schema 操作を出すと、2 件目は先着が解放されて commit した後にはじめて答えを返すか、または先着が `PRECONDITION_FAILED` で拒否され何も実行しない。`with` を抜けると先着は解放される。

        Verbatim above (word-for-word from the supervisor's ruling M-13
        in work order docs/work-orders/
        WORK_ORDER_R102_APPLICATION_SERIALIZATION_V1.md; the design's own section 9
        `conformance-tests/` paragraph and section 11.1 Q-5 decide only
        that the condition and the hook exist).

        port v1.20: condition C-34's own driving primitive -- a `plan`'s
        precondition under a concurrent schema operation against the same
        Application, decided deterministically by an adapter hook instead
        of a bare `time.sleep()` race. It is the same "test-driving
        primitive, never a test-only hook on product code" discipline
        `hold_in_flight` and `hold_after_idempotency_lookup` above already
        establish, applied to the window between a schema operation's
        read of the revision its `plan` is checked against and its first
        DDL statement.

        Structural difference from `hold_in_flight` (the same one
        `hold_after_idempotency_lookup` has): this primitive never issues
        any request of its own. The held schema operation ("A") and the
        second one ("B") are both issued by the CALLER, each from its own
        OS thread -- this method only arms the ONE stall point and yields
        the `PlanVerificationHold` handle a caller uses to wait for A to
        actually reach it (`PlanVerificationHold.wait_until_held`, above).
        A caller confirms B has not completed while A is held with a
        bounded wait window of its own, the same shape
        `test_c27_concurrent_same_key.py` uses. A caller that exits the
        `with` block without having called `wait_until_held` has verified
        nothing about non-vacuity.

        The arming is for the ONE next schema operation that presents a
        `plan` or `dry_run`; a schema operation presenting neither passes
        through, like every other request -- a data operation, a second
        schema operation, or one arriving after the hold was taken --
        undisturbed. A second schema operation that B issues against a
        DIFFERENT entity of the same Application is what C-34 observes,
        because the Application's revision, plan token and schema object
        count are Application-wide.

        Called against the YIELDED instance of `isolated_application_
        surface()`, never against the shared, session-scoped adapter --
        the same convention the two primitives above follow.
        """

    # ------------------------------------------------------------------
    # audit_query surface (port v1.8, phase 4 WP-1, design docs/design/
    # PHASE4_DURABLE_AUDIT_SINK_V1.md §8.3, work order docs/work-orders/
    # PHASE4_DURABLE_AUDIT_SINK_WORK_ORDER.md WP-1 supplementary ruling 1)
    # ------------------------------------------------------------------
    #
    # `audit_query` is a declare-first operation: unlike every other
    # in-band control-plane method above (which presents a request to a
    # real peer entry point and lets the peer's own authorization/
    # capability checks decide the outcome), this method reads the peer's
    # OWN `audit_query` capability declaration FIRST, before ever
    # presenting a request -- the same "capability refusal precedes every
    # other check" discipline C-14 already established for `role="control"`
    # in-band issuance (design section 8 M-1), applied here one layer
    # earlier: at the PORT's own dispatch, not inside the peer.
    #
    #   - `audit_query` undeclared, or declared anything other than
    #     `enabled`/`partial` (most commonly `unavailable`) -> raises
    #     `SurfaceAbsent`, WITHOUT presenting any request to the peer at
    #     all. AUDIT DSN unset is design D-5/M-4's own dual posture: the
    #     peer's real HTTP route is still registered and would itself
    #     answer a directly-issued request with `CAPABILITY_UNSUPPORTED`
    #     (never a bare 404) -- but this port method never reaches that
    #     route in the first place when the declaration itself already
    #     says the surface is not provided.
    #   - `audit_query` declared `enabled`/`partial` -> presents the real
    #     request with `actor` exactly as given (this method never
    #     pre-filters by credential kind, the same "authorization is the
    #     peer's own decision" convention every other in-band method above
    #     follows). Returns the peer's raw `AuditResult` document on
    #     success (`PROVIDED`), or raises `ConformanceDenial` with a code
    #     that is a genuine member of the contract's `errors.codes` on the
    #     peer's own real refusal (e.g. `FORBIDDEN` for an application
    #     credential, `VALIDATION_FAILED` for a malformed cursor). Any
    #     other outcome -- a 404, a 405, an unclassified/UNCLASSIFIED
    #     response -- is a suite failure, not a denial: see
    #     `test_c09_declared_enabled_audit_query_actually_answers`.
    #
    # `SurfaceAbsent`'s own meaning is EXTENDED by this method (design
    # section 8.4 / WP-1 supplementary ruling 1 item 1): before this port
    # revision, `SurfaceAbsent` meant only "no Python callable on this
    # peer's public surface could structurally receive this request at
    # all" (see that exception's own class docstring above). For
    # `audit_query` specifically, it ALSO covers "this deployment declares
    # it does not provide the audit surface" -- a claim about the peer's
    # own DECLARED posture, not only about the literal absence of a
    # callable, even though (as of this port revision, before any peer
    # implements a real audit_query entry point at all) both readings
    # happen to coincide for every currently-registered adapter. A future
    # peer that implements a real `audit_query` entry point internally but
    # leaves it declared `unavailable` (AUDIT DSN unset) still raises
    # `SurfaceAbsent` here, under this extended meaning, even though a
    # real callable now exists somewhere on that peer -- `absence.py`'s
    # own module docstring documents this same extension from the
    # assertion-helper side.
    @abstractmethod
    def audit_query(self, actor: "CredentialHandle | ControlCredentialHandle", request: Mapping[str, Any]) -> Mapping[str, Any]:
        """`POST /control/v1/audit/query`-equivalent (design D-5's `/v1/
        audit/query` alias also resolves to the identical operation, but
        this port method reaches it via the CONTROL base URL, never the
        data-plane one -- see the HTTP adapters' own implementations for
        the "why control host, not data-plane host" rationale design
        section 8.3 requires them to carry as a comment). `request` is a
        raw mapping matching the contract's `AuditQueryRequest` shape
        (`event_classes`/`after`/`limit`, all optional) -- never a typed
        port object, since `AuditResult`/`AuditQueryRequest` are
        deliberately observed as raw documents (mirrors `capability_
        document()`'s own "never a value the adapter invents" discipline).
        Follows this method group's own declare-first dispatch documented
        above.
        """

    # port v1.19: there is no `flush_audit_buffer`. Every event and every
    # refusal count is written before its response is returned, so a peer
    # holds nothing a test could make visible sooner; a test waits the
    # declared `audit_visibility_lag_ms` (and, for a refusal window's
    # summary event, the window's own end) and polls.
    @abstractmethod
    def audit_visibility_lag_ms(self) -> int:
        """Reads the peer's own declared `visibility_lag_ms` (design D-6:
        derived from the two durable-write connection timeouts, never a
        bare implementation-chosen constant) off its real `audit_query`
        capability declaration. Exists specifically so a test never writes
        a fixed `sleep` of its own to wait for visibility -- it waits this
        many milliseconds, read from the peer's own declaration, instead
        (design section 8.3: fixed sleeps in this suite are a structural
        source of flaky reds under real-PostgreSQL load). Follows the same
        declare-first dispatch `audit_query` documents above -- `Surface
        Absent` when the audit surface is not declared provided at all,
        since there is then no real declared lag value to read.
        """

    # ------------------------------------------------------------------
    # audit_query on the DATA-plane host (port v1.9, phase 5 WP-1, design
    # docs/design/PHASE5_CONTRACT_150_AND_LIMIT_RANGE_V1.md §6.2, work
    # order docs/work-orders/WORK_ORDER_PHASE5_CONTRACT_150_V1.md WP-1) --
    # observes contract 1.4.0's unconditional obligation (b), same-label-
    # addended by CCR_DISPOSITION.md subordinate ruling 10 item 2: a
    # control/audit credential presented on the DATA-plane host's own
    # `POST /v1/audit/query` alias is not thereby owed acceptance merely
    # because that host also declares `control_plane` as something other
    # than `unavailable`.
    # ------------------------------------------------------------------
    @abstractmethod
    def audit_query_on_data_plane_host(
        self, actor: "CredentialHandle | ControlCredentialHandle", request: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        """Presents `request` (the same raw `AuditQueryRequest`-shaped
        mapping `audit_query` above takes) to this peer's DATA-PLANE
        host's own `POST /v1/audit/query` alias -- never the control host
        `audit_query` above always reaches, the mirror image of that
        method's own "control base URL, never the data-plane one" rule.

        Reaches the alias HANDLER ITSELF where the plug can: an HTTP plug
        sends a real request to the DATA base URL (the same real ASGI app
        the data-plane's other in-band methods already use). An in-process
        plug that has no ASGI routing layer to send a request through
        instead calls the exact same product-code steps the real handler's
        own body calls, in the same order, with the same arguments,
        reaching the alias handler's own real behavior directly rather
        than approximating it. A plug that genuinely cannot reach even that
        much (a narrower observation than the real handler) presents
        `actor`'s credential at this peer's own data-plane authentication
        surface instead -- disclosed as a limit on this peer's own row in
        `conformance-tests/CONDITIONS.md`'s C-09 entry, never silently
        substituted without that disclosure.

        Returns the peer's raw `AuditResult` document (a `Mapping`) on
        success (the credential was genuinely accepted -- legitimate only
        for a deployment that co-hosts both surfaces on the data host,
        `versioning.control_discovery`'s own "convenience, not a
        requirement"), or raises `ConformanceDenial` with a genuine
        contract-code denial (most commonly `AUTH_INVALID`: this host
        holds no control-credential store) -- the same success/denial
        convention `audit_query` above already follows. Raises
        `SurfaceAbsent` (this peer declares `control_plane` `unavailable`,
        or has no data-plane `/v1/audit/query` alias at all -- both
        structural absences, never taken on the adapter's word) rather
        than presenting any request, following the same `signature_
        forbids_parameters`-verifiable convention every other `Surface
        Absent` raise site on this port already follows.
        """

    # Phase 6 WP-3 追補 (supervisor ruling 2026-09-04, brief item D): the
    # pre-1.6.0 topology-declaration method this abstract base class once
    # required here -- the fallback `surfaces_cohosted` (module-level
    # function, above) called before a peer declared a real `surfaces`
    # object -- is REMOVED, in the same commit as the last peer's 1.6.0
    # flip (design docs/design/PHASE6_CONTRACT_160_CLIENT_DISCOVERY_V1.md
    # section 6.1 item 2, D-2's own "この方式のフォールバックとしてのみ使
    # う"). Every registered adapter's own implementation (which always
    # returned `False`) is removed alongside it; `surfaces_cohosted` is
    # now surfaces-derived only (its own docstring).

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
        self, session, entity: str, select: Sequence[str], field: str | None, value: Any, *, limit: int | None = None
    ) -> list[dict]:
        """`limit` (port v1.12, L7-21, optional keyword-only, default
        `None`): the client's own requested page size -- presented to the
        peer's real page-size/`page.size` parameter verbatim, exactly as
        `values`/`where_field`/`where_value` are never interpreted by the
        adapter itself. `None` means the call carries no page-size request
        at all (byte-for-byte the pre-v1.12 behavior: whatever default
        page size the peer's own real entry point applies on its own).
        Added so `test_c05_limit_declaration_agreement.py`'s own
        `result_items` V2 drive can present a REAL, client-controlled page
        size to every plug (previously only reachable on `r2db-api`, whose
        own `query`/`query_page` already took a `page_size` keyword no
        port method exposed) -- an adapter's own capability to carry this
        field through, not a peer-name exclusion, is what a driver now
        checks (L7-21 能力判定化)."""

    @abstractmethod
    def attempt_filter(
        self,
        session,
        entity: str,
        select: Sequence[str],
        field: str,
        operator: str,
        value: Any,
        *,
        extra_predicates: Sequence[tuple[str, str, Any]] | None = None,
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

        `extra_predicates` (port v1.12, L7-21, optional keyword-only,
        default `None`): zero or more additional `(field, operator,
        value)` predicates, ANDed with the primary `(field, operator,
        value)` predicate above -- presented to the peer's real multi-
        predicate `where`/filter-list entry point verbatim (the SAME
        `QueryRequest.where` array `spec/data-service-api.v1.json`
        already declares, `maxItems: 50`), never synthesized as several
        separate single-predicate calls. `None`/empty means exactly the
        one predicate (byte-for-byte the pre-v1.12 behavior). Added so a
        `query_complexity` V2 drive can present a genuine multi-predicate
        request to a peer whose own complexity metric counts predicates
        (`MitateDB-api`'s `len(filters)`), not only one whose metric can
        be driven through `select`'s own length alone (`r2db-api`'s
        `len(where) + len(select) + order_by_count`) -- an adapter's own
        capability to carry more than one predicate through, not a
        peer-name exclusion, is what a driver now checks (L7-21 能力
        判定化).
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

    # ------------------------------------------------------------------
    # typed schema operations (port v1.10, design docs/design/
    # PHASE6_CONTRACT_160_CLIENT_DISCOVERY_V1.md section 6.1 item 3, D-3)
    # ------------------------------------------------------------------
    #
    # `create_entity`/`COMMON_FIELD_TYPES` above speak this PORT's own
    # two-member vocabulary (`"text"`/`"integer"`), deliberately distinct
    # from the CONTRACT's own seven-member `field_type` vocabulary
    # (`string`/`integer`/`number`/`boolean`/`object`/`array`/`json`,
    # `spec/data-service-api.v1.json`'s `SchemaOperationRequest.field_
    # type` enum) -- see `create_entity`'s own docstring and each plug's
    # `_PORT_FIELD_TYPE_TO_*` table. The two methods below speak the
    # CONTRACT's vocabulary directly, verbatim, with no port-level
    # translation table of their own: the common suite's D-3 round-trip
    # vector (`test_c19_client_self_sufficiency.py`) needs to know, on its
    # OWN side, exactly which contract-vocabulary word it declared for
    # each field, so it can compare that declaration against what
    # `catalog_document()` reports back -- a port-level translation table
    # would put that knowledge on the wrong side of the port/plug split
    # (design principle 1). This is the "new method(s)" resolution design
    # section 6.1 item 3 left open (work order WP-1 item 5(c)): the common
    # suite calls these two methods ITSELF with field types it already
    # knows, so no change to `Fixture` was needed for it to "know its own
    # declared types" (WP-1 completion report elaborates).
    #
    # Neither method is reachable by any currently-registered adapter as
    # of this port revision -- both are declare-first gated (>= 1.6.0) by
    # every caller in `test_c19_client_self_sufficiency.py`, and no peer
    # declares 1.6.0 yet (WP-2/WP-3). Each plug's own implementation is
    # written against the REAL eventual entry point (the same "written for
    # the real eventual shape, currently unreached" honesty
    # `docs/design/CONFORMANCE_ADAPTER_V1.md` sections 18.4/19.5 already
    # document for other declare-first methods), not a stub -- see each
    # plug's own docstring/comment for what it targets and why it may
    # currently deny with `VALIDATION_FAILED` (the peer's pre-1.6.0
    # vocabulary/keys do not yet accept these contract words) rather than
    # succeed.

    @abstractmethod
    def create_entity_with_declared_types(
        self, session, entity: str, fields: Sequence[str], field_types: Mapping[str, str] | None
    ) -> None:
        """Presents a real `create_entity` request carrying the contract's
        own `fields` (names) and, when given, `field_types` (name -> one
        of the seven contract-vocabulary words) to the peer's real
        schema-operation entry point -- the wire-shaped `SchemaOperation
        Request` itself where a plug's real surface is wire-shaped, or the
        same request DICT the wire-shaped surface would receive where a
        plug presents it directly to product code (mirrors every other
        `self._service.schema(...)`/`self._schema(...)` call already on
        this ABC's plugs). `field_types` may be partial or `None`/empty --
        the contract's own D-3(iv) rule ("the request's object may be
        partial") means any name in `fields` with no entry in `field_
        types` is created with type `json` (D-3(ii)), a rule this method
        never enforces or simulates itself: it presents the request
        exactly as given and returns whatever the peer's real response
        was (success, or `ConformanceDenial` on the peer's own real
        refusal -- most commonly `VALIDATION_FAILED` from a pre-1.6.0
        peer that does not yet accept `field_types` at all).
        """

    @abstractmethod
    def add_field_with_declared_type(self, session, entity: str, field: str, field_type: str) -> None:
        """Presents a real `add_field` request carrying the contract's own
        per-field `field_type` (one of the seven contract-vocabulary
        words, verbatim -- never translated through `COMMON_FIELD_TYPES`'
        own two-member table) to the peer's real schema-operation entry
        point, the same "real entry point, real response, no
        fabrication" contract every other schema-mutating method on this
        ABC already carries.
        """

    # ------------------------------------------------------------------
    # port v1.13 (design docs/design/
    # PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md §6.1): five
    # new methods below (`schema_operation_with_result`, `attempt_
    # mutation_with_result`, `attempt_batch_with_result`, `attempt_cross_
    # entity_batch_with_result`, `query_with_budget`), additive only --
    # no existing method's signature or return type changes. The five
    # limits §6.1 requires stating are on THIS CLASS's own docstring
    # (above `name: str`), not here -- every one of the five methods below
    # is bound by all five of them.
    # ------------------------------------------------------------------

    @abstractmethod
    def schema_operation_with_result(
        self,
        session,
        entity: str,
        operation: str,
        *,
        field: str | None = None,
        field_type: str | None = None,
        fields: Sequence[str] | None = None,
        field_types: Mapping[str, str] | None = None,
        field_constraints: Mapping[str, Mapping[str, Any]] | None = None,
        enum: Sequence[Any] | _EnumClear | None = None,
        nullable: bool | None = None,
        destructive: bool = False,
        confirmation: Any = None,
        dry_run: bool = False,
        plan: str | None = None,
        budget: Mapping[str, int] | None = None,
        idempotency_key: str | None = None,
    ) -> Mapping[str, Any]:
        """A single, general schema-operation primitive (port v1.13, design
        docs/design/PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md
        D-2/D-4/D-5/D-6/D-8, §6.1 items 1-5, 7, 8) that presents any of
        `create_entity`/`add_field`/`alter_field`/`create_index`/
        `drop_entity` to the peer's real schema entry point, carrying every
        field contract 1.7.0 newly declares on `SchemaOperationRequest`.

        This is deliberately ONE method, not five (one per operation name)
        or a family of variants bolted onto `create_entity_with_declared_
        types`/`add_field_with_declared_type`: those two pre-existing
        methods are left byte-for-byte untouched (no new keyword, same
        `None` return) so `test_c19_client_self_sufficiency.py`'s existing
        callers keep their exact pre-v1.13 behavior. This new method is
        `alter_field`'s own primitive (§6.1 item 8 -- no port method could
        express `alter_field` at all before this port revision, since
        neither peer implements it yet either), and is what every C-20/
        C-22/C-23/C-24/C-25 vector needing a schema-side observation uses,
        including `create_entity`/`add_field` ones, so the six new
        condition files speak one schema vocabulary instead of mixing this
        method with the two pre-existing ones.

        `field`/`field_type`/`fields`/`field_types` mirror the pre-existing
        per-operation shapes (`add_field`'s single `field` name + singular
        `field_type`, exactly as `add_field_with_declared_type` already
        sends; `alter_field`'s single `field` name with no `field_type`
        (D-2(5): redeclaring type is undefined in this version);
        `create_entity`'s `fields` list plus optional plural `field_types`,
        exactly as `create_entity_with_declared_types` already sends).
        `field_constraints` (D-2(1), meaningful on `create_entity` in this
        version) and `nullable` (D-2(1), `add_field`/`alter_field`'s own
        top-level constraint pair) are carried through exactly as
        `field_types` already is on `create_entity_with_declared_types` --
        never validated, simulated, or defaulted by this adapter itself.
        `enum` is tri-state (port v1.13 追補, the `ENUM_CLEAR` sentinel
        defined above this class): omitted (`None`, the default) leaves
        the `enum` key off the wire request entirely (`alter_field`: no
        change to the field's existing enum); `ENUM_CLEAR` puts a literal
        JSON `enum: null` on the wire (`alter_field`: clears the field's
        enum; `add_field`: the contract states this means the same as
        omitting it); any other `Sequence` puts `enum: [...]` on the wire,
        unchanged from pre-addendum behavior. `destructive`/`confirmation`
        follow the identical `VALID_CONFIRMATION` sentinel protocol
        `drop_entity` already uses (needed for C-23 (vii)'s
        destructive-replay vector against `drop_entity`, and for any
        future destructive schema vector).

        `dry_run`/`plan`/`budget`/`idempotency_key` are request-UNIT
        keywords -- exactly one value for this one operation (a schema
        request never batches more than one operation) -- carried through
        unedited to whatever real schema entry point already receives the
        rest of the request, never interpreted, validated, or narrowed by
        this adapter. Each keyword defaults to its own byte-compatible
        absence (`False`/`None`), identical to omitting it from the
        request entirely -- pre-v1.13 callers of the two untouched schema
        methods above are unaffected.

        Returns a `Mapping` with:
          - `revision`: `str`, the peer's real post-request schema revision
            as a string. `SchemaOperationResult.revision` is `required` and
            always present on a real response; where the underlying real
            call this plug drives returns a bare revision value (e.g. the
            pre-v1.13 `int` shape `schema()`/`schema` dispatchers already
            return on every currently-registered peer), that value is
            stringified rather than the call failing.
          - `descriptor`: `Mapping | None` (D-4(3)) -- the `EntityDescriptor`
            a dry-run or real schema operation returns, observed from the
            real response; `None` where that response structurally carries
            no such concept (every currently-registered peer, pre-D-4),
            never fabricated.
          - `plan`: `str | None`, opaque, observed the same way.
          - `request_id`: `str | None`, observed the same way.

        Raises `ConformanceDenial` on the peer's own real refusal, or
        `SurfaceAbsent` where no real entry point could carry this request
        at all, exactly like `create_entity_with_declared_types`/`drop_
        entity`.
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
    def attempt_mutation_with_result(
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
        destructive: bool = False,
        confirmation: Any = None,
        dry_run: bool = False,
        plan: str | None = None,
        budget: Mapping[str, int] | None = None,
        transaction: str | None = None,
        idempotency_key: str | None = None,
    ) -> Mapping[str, Any]:
        """`attempt_mutation`'s exact request shape, extended with the
        contract's own request-level `dry_run`/`plan`/`budget` (port v1.13,
        design docs/design/PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md
        D-4/D-6, §6.1 items 1-3), returning the full observed result as a
        `Mapping` instead of a bare `int` -- C-22/C-24/C-25 need
        `committed`/`plan`/`request_id` alongside `affected`/`assigned_
        addresses`, none of which `attempt_mutation`/`attempt_mutation_
        with_addresses` (both left byte-for-byte untouched, still returning
        their own pre-v1.13 shapes) have room to add without breaking every
        existing caller that unpacks their fixed-arity return.

        `destructive`/`confirmation` (port v1.13 追補, C-22's own
        `_confirm_probe`) follow the IDENTICAL `VALID_CONFIRMATION` sentinel
        protocol `delete`/`drop_entity`/`schema_operation_with_result`
        already establish: `destructive` MUST be passed through to the peer
        faithfully; `confirmation` is `None` (supply nothing, the default --
        byte-compatible with every pre-addendum caller that never named this
        keyword), `VALID_CONFIRMATION` (resolve to a real, currently-valid
        confirmation for this exact request via `resolve_valid_confirmation`/
        `_resolve_confirmation`), or any other string (passed straight
        through verbatim). `attempt_mutation`/`attempt_mutation_with_
        addresses` deliberately do NOT gain these two keywords -- C-12's own
        docstring already states `attempt_mutation` never exercises `delete`
        in its non-destructive context, so `delete`'s dedicated method and
        `BatchOperation.destructive`/`.confirmation` (`attempt_batch_with_
        result`'s own per-operation carrier, already declared above) remain
        the only pre-v1.13 destructive-capable entry points; this method is
        the single-operation, request-level-`dry_run`-carrying entry point
        C-22's `_confirm_probe` needs for `delete`, so it alone gets the pair
        added, exactly like `schema_operation_with_result` already carries
        them for schema operations. An adapter MUST NOT upgrade a non-
        destructive/unconfirmed request into a confirmed destructive one,
        for the identical reason `delete`'s own docstring already states.

        `dry_run`/`plan`/`budget` are request-UNIT keywords -- exactly one
        value per call, never per-operation (this method presents exactly
        one operation, like `attempt_mutation` itself) -- carried through
        unedited to whatever real entry point already receives the rest of
        this operation, never interpreted by this adapter. Each defaults to
        its own byte-compatible absence (`False`/`None`/`None`), identical
        to omitting it from the request entirely.

        `transaction` (port v1.13 追補 2, C-22 leg (10)'s own digest-scope
        proof) carries the contract's PRE-EXISTING `MutationRequest.
        transaction` key (`"atomic"`/`"best_effort"`, spec/data-service-
        api.v1.json) through unedited, exactly like `plan`/`budget` above --
        never validated or defaulted by this adapter. Defaults to `None`
        (omit the key entirely, byte-compatible with every pre-existing
        caller that never names this keyword). Chosen for C-22's plan-
        digest-scope leg specifically because, unlike `budget`
        (`request_budget`-gated) or `dry_run`/`plan` themselves,
        `transaction` is not behind any declare-first capability gate --
        every registered peer's `MutationRequest` schema carries it
        unconditionally, so a plan taken without it, re-presented WITH it
        (even the same `"atomic"` value the peer already defaults to), is
        the one always-available way to prove the plan's digest is not
        `operations`-only without depending on what any one peer declares.

        `idempotency_key` (WP-1 addendum, C-25 (4)'s own replay leg,
        `docs/design/CONFORMANCE_ADAPTER_V1.md` §23): the contract's
        REQUEST-level `MutationRequest.idempotency_key` -- this method
        presents exactly one operation per call, so it is carried through
        directly (never folded), exactly like `dry_run`/`plan`/`budget`/
        `transaction` above and like `schema_operation_with_result`'s own
        identical keyword. Each currently-registered adapter places it
        wherever its own real entry point expects a request-level
        idempotency key -- embedded on the single operation item for an
        in-process peer whose real dispatcher reads it there (the same
        position `fold_batch_idempotency_key`'s callers already use on
        that peer), or on the request body's own top-level key for a
        wire-surface peer (`extra_body`, the same mechanism `attempt_
        batch_with_addresses` already uses there) -- never interpreted,
        validated, or narrowed by this adapter itself. Defaults to `None`
        (omit the key entirely, byte-compatible with every pre-addendum
        caller that never names this keyword).

        Returns a `Mapping` with:
          - `affected`: `int`.
          - `assigned_addresses`: `list[Mapping] | None`, same observed-
            fact convention as `attempt_mutation_with_addresses`.
          - `committed`: `bool` -- `True` for a real, non-dry-run
            execution. Observed from the real result where it structurally
            carries the concept; where it does not (every currently-
            registered peer, pre-D-4), this is `not dry_run` -- a real
            request that is not a dry run always commits today, so this
            default states an existing fact rather than assuming a new
            one (mirrors the `assigned_addresses`/`revisions` "structural
            absence" convention, applied to a boolean instead of a list).
          - `plan`: `str | None`, opaque, observed.
          - `request_id`: `str | None`, observed.

        Raises `ConformanceDenial` on the peer's own real refusal, exactly
        like `attempt_mutation`.
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
    def attempt_batch_with_result(
        self,
        session,
        entity: str,
        operations: Sequence[BatchOperation],
        *,
        dry_run: bool = False,
        plan: str | None = None,
        budget: Mapping[str, int] | None = None,
    ) -> Mapping[str, Any]:
        """`attempt_batch_with_addresses`'s exact request shape, extended
        with the contract's own request-level `dry_run`/`plan`/`budget`
        (port v1.13, design docs/design/
        PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md D-4/D-6,
        §6.1 items 1-3) -- used by C-24's `batch_items` vector (the
        `budget` that narrows how many operations one request may carry)
        and by C-22's batch-shaped dry-run vectors alike, returning a
        `Mapping` (`affected`/`assigned_addresses`/`committed`/`plan`/
        `request_id`, same shape and same observed-fact conventions as
        `attempt_mutation_with_result`) rather than growing `attempt_
        batch_with_addresses`'s own fixed 2-tuple.

        `operations`' own per-item `idempotency_key` (existing since port
        v1.11) is folded to the single request-level value the contract's
        `MutationRequest.idempotency_key` actually is, via the module-level
        `fold_batch_idempotency_key` -- see that function's own docstring
        for the uniform-or-absent rule and the `AssertionError` it raises
        on a genuine mix (a port-usage error, never silently resolved by
        picking one value). `dry_run`/`plan`/`budget` are request-UNIT
        keywords exactly as on `attempt_mutation_with_result` -- one value
        for the whole batch, never per-operation; each defaults to its own
        byte-compatible absence.

        Every operation MUST be presented to the same real batch entry
        point a real client sending multiple operations at once would use,
        exactly like `attempt_batch_with_addresses` itself.
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
    def attempt_cross_entity_batch_with_result(
        self,
        session,
        operations: Sequence[ScopedBatchOperation],
        *,
        dry_run: bool = False,
        plan: str | None = None,
        budget: Mapping[str, int] | None = None,
    ) -> Mapping[str, Any]:
        """`attempt_cross_entity_batch`'s exact request shape, extended the
        same way `attempt_batch_with_result` extends `attempt_batch_with_
        addresses` (port v1.13, design D-4/D-6, §6.1 items 1-3) -- returns
        a `Mapping` with `affected`, `committed`, `plan` and `request_id`
        (deliberately no `assigned_addresses` key, mirroring `attempt_
        cross_entity_batch`'s own bare-`int` choice: no currently-
        registered peer providing this capability also declares `row_
        addressability`, design M-6). `idempotency_key` is folded across
        `operations` exactly as `attempt_batch_with_result` does, via the
        same module-level `fold_batch_idempotency_key`. `dry_run`/`plan`/
        `budget` are request-unit keywords, one value for the whole unit.

        Raises `SurfaceAbsent`/`ConformanceDenial` exactly like `attempt_
        cross_entity_batch`.
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

    @abstractmethod
    def query_with_budget(
        self,
        session,
        entity: str,
        select: Sequence[str],
        field: str | None,
        value: Any,
        *,
        budget: Mapping[str, int] | None = None,
    ) -> Mapping[str, Any]:
        """Same request shape as `query_with_revisions` (port v1.13, design
        docs/design/PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md
        D-6, §6.1 item 3), presenting the contract's own request-level
        `budget` (`QueryRequest.budget`, D-6(1)) and returning the full
        observed result as a `Mapping` rather than a bare tuple, so C-24's
        `result_items`/`execution_ms` vectors and C-25's `request_id`
        vector both use this one primitive instead of the port growing a
        fourth query method.

        `budget` is a request-UNIT keyword (there is no per-item position
        on a query request to begin with), carried through exactly as
        `field`/`value` are on `query_with_revisions`: never interpreted,
        validated, or narrowed by this adapter itself. `None` (the
        default) omits it from the presented request entirely, byte-
        identical to `query_with_revisions`'s own pre-v1.13 behavior --
        this method does not replace `query_with_revisions`, which stays
        untouched for its own existing callers.

        Returns a `Mapping` with:
          - `items`: `list[dict]`, same value `query_with_revisions`
            returns as its own first tuple element.
          - `revisions`: `list[str] | None`, same observed-fact convention
            as `query_with_revisions`.
          - `request_id`: `str | None` (C-25), observed the same way --
            `None` when the real response carries no such key/attribute at
            all, never fabricated.

        Raises `ConformanceDenial` on the peer's own real refusal (for
        example `VALIDATION_FAILED` for a `budget` naming a class that does
        not apply to `query`, or one exceeding the deployment's own
        declared value; `CAPABILITY_UNSUPPORTED` while `request_budget` is
        declared `unavailable`), exactly like every other primitive here.
        """

    @abstractmethod
    def attempt_filter_with_result(
        self,
        session,
        entity: str,
        select: Sequence[str],
        field: str,
        operator: str,
        value: Any,
        *,
        extra_predicates: Sequence[tuple[str, str, Any]] | None = None,
        order_by: Sequence[Mapping[str, Any]] | None = None,
        page_size: int | None = None,
        budget: Mapping[str, int] | None = None,
    ) -> Mapping[str, Any]:
        """`attempt_filter`'s exact request shape, extended with the
        contract's own request-level `order_by`/`page.size`/`budget` in ONE
        query request (port v1.16, design docs/design/
        PHASE11_MIN_COMMON_PROFILE_V1.md §7 段 (9) and §7.1 items 1/4, work
        order docs/work-orders/WORK_ORDER_PHASE11_MIN_COMMON_PROFILE_V1.md
        WP-2), returning the full observed result as a `Mapping` instead of
        a bare `list[dict]` -- mirrors the `attempt_mutation` -> `attempt_
        mutation_with_result` / `query_with_revisions` -> `query_with_
        budget` precedent this ABC already establishes (an additive `_with_
        result` sibling, not a change to the original method's fixed-arity
        return). `attempt_filter` itself stays byte-for-byte untouched (no
        new keyword, still a bare `list[dict]`), so every pre-v1.16 caller
        keeps its exact pre-v1.16 behavior. `select_eq`/`query_with_budget`
        are likewise untouched -- this is an ADDITION, not a replacement of
        any of the three pre-existing query methods.

        `extra_predicates` behaves exactly as it already does on `attempt_
        filter` (zero or more additional `(field, operator, value)`
        predicates, ANDed with the primary one, presented on the SAME real
        `where`/filter-list entry point).

        `order_by` (request-UNIT keyword, contract `QueryRequest.order_by`
        -- `spec/data-service-api.v1.json` `definitions.Order`, an array of
        `{field, direction}` objects where `direction` is `"asc"`/`"desc"`,
        `maxItems: 10`): carried through unedited, in that exact shape, to
        whichever real multi-term order entry point the peer already has --
        `r2db-api`'s `DataService.query_page` (`src/r2db_api/service.py`)
        already takes an `order_by` keyword of this same shape; `MitateDB-
        api`'s `session.read_with_result` (`src/mitatedb_api/cell.py`)
        already takes one too -- neither peer's backend gains a new
        keyword, only this port gains a new caller of an existing one.
        `None` (the default) omits `order_by` from the presented request
        entirely, byte-identical to every existing `attempt_filter` caller,
        none of which order.

        `page_size` (request-UNIT keyword, contract `QueryRequest.page.
        size`): the SAME real page-size parameter `select_eq`'s own
        `limit` keyword (port v1.12) already presents verbatim -- named
        `page_size` here (not `limit`) to read as the contract's own
        `page.size` at this call site. `None` omits it, exactly like
        `select_eq(..., limit=None)`.

        `budget` (request-UNIT keyword, contract `QueryRequest.budget`,
        `spec/data-service-api.v1.json`: an object with optional integer
        `result_items`/`execution_ms`/`batch_items`, each `minimum: 1`):
        the SAME keyword `query_with_budget` (port v1.13) already carries,
        in that exact shape, never interpreted, validated, or narrowed by
        this adapter itself. `None` (the default) omits it entirely.

        Returns a `Mapping` with:
          - `items`: `list[dict]`, the same value `attempt_filter` returns
            bare.
          - `request_id`: `str | None`, observed the same way `query_with_
            budget`'s own `request_id` already is -- `None` when the real
            response carries no such key/attribute at all, never
            fabricated.

        On the peer's own real refusal this raises `ConformanceDenial`
        (carrying the peer's real error body -- `code`/`details`, exactly
        like `attempt_filter`/`query_with_budget`/every other `attempt_*`
        primitive on this ABC), so a caller distinguishes a successful
        result `Mapping` from a denial by catching `ConformanceDenial`
        rather than by inspecting a field of the return value -- the SAME
        success/denial split every other `attempt_*`/`*_with_result` method
        here already uses. For example `CAPABILITY_UNSUPPORTED` for an
        `operator` outside the peer's declared `structured_query.
        operators`, or `VALIDATION_FAILED`/`LIMIT_EXCEEDED` for a `budget`
        the deployment rejects or exceeds.
        """

    @abstractmethod
    def operation_catalog_document(self, session) -> bytes:
        """Port v1.17 (design docs/design/PHASE11_MIN_COMMON_PROFILE_V1.md
        D-5, §7.1 item 2, work order docs/work-orders/
        WORK_ORDER_PHASE11_MIN_COMMON_PROFILE_V1.md WP-3): the body the
        peer itself returns for its own `operation_catalog` operation
        (contract `endpoints.operation_catalog`, `GET /v1/operation-
        catalog`), as raw BYTES -- never parsed/re-serialized by this
        adapter -- so C-29's own byte-for-byte comparison against the
        packaged derived catalog has no re-encoding step of this port's
        own to drift from either side.

        `session` is an already-authenticated application session/handle
        (runtime or developer -- the same credential `capability_
        document()` above provisions for itself; a caller here presents
        one it already holds, mirroring `attempt_filter_with_result`'s own
        `session` parameter), authenticated exactly as `GET /v1/
        capabilities` requires (design §8.2: no anonymous face).

        Realized on all SIX plugs (unlike `attempt_filter_with_result`
        above, which the two socket plugs inherit from their peer's http
        realization unchanged): C-29's stage (i) compares THIS method's
        return value against the packaged catalog on every plug, in-
        process included, since in-process plugs have no HTTP face to
        dial (design D-5's own honest limit) -- so this method is the
        ONLY way stage (i) observes an in-process plug's own served body
        at all. Stage (ii) (socket plugs only) additionally dials the
        declared `operation_catalog_url` for real and compares that
        response against this SAME method's return value.

        Raises `ConformanceDenial` on the peer's own real refusal (for
        example an invalid/expired `session`), exactly like every other
        `attempt_*`/`*_document` primitive on this port.
        """

    @abstractmethod
    def query_page(
        self,
        session,
        entity: str,
        select: Sequence[str],
        *,
        where: Sequence[tuple[str, str, Any]] | None = None,
        order_by: Sequence[tuple[str, str]] | None = None,
        page_size: int | None = None,
        cursor: str | None = None,
        budget: Mapping[str, int] | None = None,
    ) -> tuple[list[dict], str | None]:
        """port v1.18 (design docs/design/PHASE11_KEYSET_PAGING_V1.md D-4):
        an independent, additive query primitive for C-30 (keyset paging) --
        `select_eq`/`attempt_filter` carry neither `order_by` nor `cursor`,
        so this is a new abstract method rather than growing either of
        their signatures (design principle: existing ~20 callers of every
        other query method stay untouched).

        `where` is the same `(field, operator, value)` triple sequence
        `attempt_filter`'s own `extra_predicates` already carries, ANDed
        together. `order_by` is a `(field, direction)` pair sequence. Both,
        along with `select`/`page_size`/`cursor`, are presented to the
        peer's own real query entry point VERBATIM -- never interpreted,
        validated, or synthesized by this adapter itself, the same
        principle `select_eq`'s own docstring states.

        `budget` (keyword-only, port v0.4 addition to this same method,
        design D-4): carried through exactly as `query_with_budget`'s own
        `budget` is -- `None` (the default) omits it from the presented
        request entirely.

        Returns `(items, next_page)`: `next_page` is the peer's own real
        response value, returned unmodified -- this adapter neither
        interprets nor constructs a cursor. Raises `ConformanceDenial` on
        the peer's own real refusal, exactly like every other primitive
        here; this adapter never fabricates one.
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
