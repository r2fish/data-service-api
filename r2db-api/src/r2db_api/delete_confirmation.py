"""r2db destructive-confirmation phrase construction and gate (ST5, design
docs/design/DESTRUCTIVE_CONFIRMATION_V1.md R-2 item 1, contract 1.2.0
`destructive_confirmation.phrase_construction`).

This is a pure leaf: every phrase function is a total, deterministic string
composition over its own arguments (plus, for `delete_confirmation_phrase`,
a SHA-256 digest of `_canonical_where_json`'s own deterministic JSON
serialization of an already-validated predicate list), and
`require_destructive_confirmation` is a total, deterministic comparison of
its own arguments. None of them opens a connection, reads a catalog, or
consults any request/limits/principal state; the choke points that decide
*when* to call `require_destructive_confirmation` at all -- each backend's
own `delete`/`drop_entity`/`drop_index` call site (`ApplicationCell`,
`r2db_api.postgres.PostgresCell`), the control plane's own credential gate
(`control_plane.py`), and the ceremony CLI's own gated subcommands
(`ops.py`) -- remain in their own modules.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from .errors import fail
from .identifier_rules import MAX_IDENTIFIER_LENGTH


# --- destructive confirmation phrase construction (design docs/design/
# DESTRUCTIVE_CONFIRMATION_V1.md R-2 item 1, contract 1.2.0
# `destructive_confirmation.phrase_construction`) --------------------------
#
# One shared definition for every one of this codebase's three surfaces
# (data/schema plane here (in `structured.py`), control plane in `control_plane.py`, and the
# ceremony CLI's own `ops.py` in a later work package) -- none of them
# re-derives its own spelling. Every phrase is: (a) deterministic given only
# the operation/target/consequence class (never request_id, timestamps, or
# the request's own destructive/confirmation fields), (b) scope-included
# (`delete`'s own selection/where predicate is part of the derivation), (c)
# state-fingerprinted for a re-creatable target (`drop_entity`/`drop_index`
# carry the application's current `schema_revision`, so re-creating the same
# name -- or any other schema change -- invalidates a stale phrase), (d)
# built only from already identifier-validated target names (never an
# unvalidated client-supplied string reflected back), and (e) bounded well
# within `confirmation`'s contract maxLength (256).

# r2db's own identifier limit (`MAX_IDENTIFIER_LENGTH` above (in
# `identifier_rules.py`)), not a contract figure -- used only to assert the
# worst-case phrase length stays bounded.
_PHRASE_MAX_LENGTH = 256
# int64 (`_INT64_MAX` below in this same module (in `structured.py`)) has at most 19 decimal
# digits; `schema_revision` is a monotonic counter starting at 0 and is
# always representable in that range for the lifetime of any real
# deployment, so 20 digits (one more than the true worst case) is a safe,
# round upper bound for the length assertions below.
_MAX_REVISION_DIGITS = 20


def _canonical_where_json(where: "list[Predicate]") -> str:
    """Key-order-fixed JSON serialization of a bound (identifier- and
    operator-validated) predicate list, the input to `_where_digest16`
    below. Defined for an empty list too (a `delete` with no `where` selects
    every row -- design R-2 item 1's own "where 空にも digest は定まる").

    Opus review minor m-7: deliberately NO `default=str` fallback. Every
    `predicate.value` reaching this function today is JSON-native (str/
    int/float/bool/None/list/dict, from `parse_predicate`'s own JSON-body
    parsing) and serializes exactly here without one. A `default=str`
    escape hatch would silently coerce any FUTURE non-JSON-native value
    (e.g. a `Decimal`, `datetime`, or `bytes` a later `bind_mutation` change
    might admit) into whatever `str(value)` happens to produce -- and two
    genuinely different values whose `str()` forms coincide (a real
    possibility across types, e.g. `Decimal("1")` and the string `"1"`)
    would then silently collide onto the identical digest, silently merging
    two different scopes' phrases into one. Without the fallback, such a
    value raises `TypeError` here immediately and loudly instead -- a
    finding for whoever introduces it to fix at the type's own admission
    point, not a probability-dependent security gap in this hash.
    """
    payload = [{"field": p.field, "operator": p.operator, "value": p.value} for p in where]
    return json.dumps(payload, sort_keys=True, ensure_ascii=True)


def _where_digest16(where: "list[Predicate]") -> str:
    """SHA-256, first 16 hex characters, of `_canonical_where_json`'s
    output -- the delete phrase's own state-fingerprint-free scope digest
    (design Q1-D9/WP-0 MA-4: a probed narrow selection must never validate a
    broader one, since the digest changes whenever the selection does)."""
    blob = _canonical_where_json(where).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


def delete_confirmation_phrase(entity: str, where: "list[Predicate]", schema_revision: int) -> str:
    """`DELETE <entity> @where=<digest16> @schema_revision=<n>` -- `entity`
    must already be identifier-validated by the caller (every caller of
    this function is downstream of `validate_identifier(entity)` in
    `transact()`).

    Monitor decision Q1-D10 (Opus review minor m-2, measured): the
    `schema_revision` fingerprint was originally omitted here on the
    reasoning that "a row is not a target identifiable by a re-creatable
    name, so it needs no state fingerprint" -- but the where-digest alone
    is a pure function of the (field, operator, value) tuples in the
    caller's own selection, independent of whether `entity` currently
    declares those fields at all. A probed phrase for `delete ... where
    id=5` against `widgets`, followed by `drop_entity widgets` + `create_
    entity widgets` (a genuinely different entity, same name, contract
    `phrase_construction` rule (b): "対象の再作成...により旧句が無効になる
    こと"), would otherwise still validate an echo of the OLD phrase
    against the NEW entity's identical-looking delete request -- the old
    phrase never actually became invalid, contradicting rule (b)'s literal
    text even though delete's own target (a row set) is not itself a
    re-created name. Including `schema_revision` closes this: any schema
    change to the Application (including this exact drop-then-recreate)
    invalidates every previously-issued delete phrase for every entity, not
    only the recreated one -- broader invalidation than strictly necessary,
    but safe (Q1-D3's own precedent: over-invalidating a stale phrase is
    the safe direction, under-invalidating is not) and now uniform across
    all three phrase-construction functions in this module.
    """
    # Worst-case length check, symmetric with `drop_index_confirmation_
    # phrase`'s own: `"DELETE "` (7) + entity (<= MAX_IDENTIFIER_LENGTH) +
    # `" @where="` (8) + 16-hex digest (16) + `" @schema_revision="` (18) +
    # up to `_MAX_REVISION_DIGITS` digits = 7 + 63 + 8 + 16 + 18 + 20 = 132,
    # comfortably within 256.
    worst_case = 7 + MAX_IDENTIFIER_LENGTH + 8 + 16 + 18 + _MAX_REVISION_DIGITS
    assert worst_case <= _PHRASE_MAX_LENGTH, "delete_confirmation_phrase's own worst-case bound no longer fits confirmation's maxLength"
    phrase = f"DELETE {entity} @where={_where_digest16(where)} @schema_revision={schema_revision}"
    assert len(phrase) <= _PHRASE_MAX_LENGTH, "delete_confirmation_phrase exceeded the contract's confirmation maxLength"
    return phrase


def drop_entity_confirmation_phrase(entity: str, schema_revision: int) -> str:
    """`DROP_ENTITY <entity> @schema_revision=<n>` -- `n` is the
    Application's current schema_revision (monotonic, bumped by every
    schema operation on either backend), so re-creating an entity under the
    same name -- which necessarily bumps the revision again -- invalidates
    any phrase computed before the drop."""
    phrase = f"DROP_ENTITY {entity} @schema_revision={schema_revision}"
    assert len(phrase) <= _PHRASE_MAX_LENGTH, "drop_entity_confirmation_phrase exceeded the contract's confirmation maxLength"
    return phrase


def drop_index_confirmation_phrase(entity: str, index: str, schema_revision: int) -> str:
    """`DROP_INDEX <entity>.<index> @schema_revision=<n>` -- the index name
    is scoped by entity in the phrase (design R-2 item 1: index names live
    in an entity-scoped namespace, `indexes[entity][index]`/the physical
    `<table>__<index>` name), not because the phrase needs to be invertible,
    only because two different entities' indexes of the same local name
    must never collide onto the same phrase.

    Worst-case length check (design R-2 item 1; nit n-1 corrected the
    arithmetic below -- the trailing segment is 18 characters, not 19, so
    the true worst case is 176, not 177; the assert itself was always
    conservative/safe either way, this corrects what the number MEANS):
    `"DROP_INDEX "` (11) + entity (<= MAX_IDENTIFIER_LENGTH) + `"."` (1) +
    index (<= MAX_IDENTIFIER_LENGTH) + `" @schema_revision="` (18) + up to
    `_MAX_REVISION_DIGITS` digits = 11 + 63 + 1 + 63 + 18 + 20 = 176,
    comfortably within the contract's 256 maxLength -- asserted here as a
    standing regression guard, not merely documented.
    """
    worst_case = 11 + MAX_IDENTIFIER_LENGTH + 1 + MAX_IDENTIFIER_LENGTH + 18 + _MAX_REVISION_DIGITS
    assert worst_case <= _PHRASE_MAX_LENGTH, "drop_index_confirmation_phrase's own worst-case bound no longer fits confirmation's maxLength"
    phrase = f"DROP_INDEX {entity}.{index} @schema_revision={schema_revision}"
    assert len(phrase) <= _PHRASE_MAX_LENGTH, "drop_index_confirmation_phrase exceeded the contract's confirmation maxLength"
    return phrase


def revoke_last_control_credential_confirmation_phrase(credential_id: str) -> str:
    """`REVOKE_LAST_CONTROL_CREDENTIAL <credential_id>` -- the control
    plane's own destructive-confirmation phrase (design R-3), sharing this
    module's phrase-construction definitions even though the gate itself
    lives in `control_plane.py`, not here. No state fingerprint is needed:
    `credential_id` is itself a random, never-reused value (`control_plane.
    _new_control_credential_id`), so it already serves as its own fingerprint --
    a revoked id can never legitimately reappear as a *different* live
    credential the way an entity/index name can be re-created under the
    same name.
    """
    phrase = f"REVOKE_LAST_CONTROL_CREDENTIAL {credential_id}"
    assert len(phrase) <= _PHRASE_MAX_LENGTH, "revoke_last_control_credential_confirmation_phrase exceeded the contract's confirmation maxLength"
    return phrase


# Q-1 WP-4 (docs/design/DESTRUCTIVE_CONFIRMATION_V1.md R-4): the ceremony
# CLI's (`ops.py`) own two gated subcommands, `reset` and `delete-credential`
# (Q1-D4/WP-0 MA-1 excludes `revoke-credential` -- it targets application
# credentials, the same operation class Q1-D1 already leaves unconfirmed).
# Both phrases live here, alongside the other three, so `ops.py` never
# re-derives its own spelling -- the same "one shared definition, three
# surfaces" discipline this module's header comment already documents for
# data/schema plane + control plane + CLI.

RESET_CONTROL_CREDENTIALS = "RESET_CONTROL_CREDENTIALS"
"""`ops.py cmd_reset`'s destructive-confirmation phrase -- a fixed constant,
not a function, and carrying no per-request state fingerprint at all.
Unlike `delete`/`drop_entity`/`drop_index` (a target identifiable by a name
that can be re-created) or `REVOKE_LAST_CONTROL_CREDENTIAL <credential_id>`
(a specific row, itself a never-reused fingerprint), `reset`'s own target is
"every row in the control_credentials store" -- there is no narrower name
for that target to be re-created under, and its consequence class (revoke
every existing row, mint exactly one new must_rotate row) is identical no
matter how many rows currently exist or what state they are in. A state
fingerprint exists to invalidate a stale phrase once ITS OWN target's state
changes (Q1-D3/contract `phrase_construction` rule (c)) -- but there is no
state `reset`'s own scope could change in without also changing what
running `reset` again would itself just do (revoke whatever is currently
there) to something functionally equivalent, so a computed fingerprint would
never actually distinguish one call from the next. This matches contract
`phrase_construction`'s own "deterministic given only operation, target, and
consequence class" rule: for `reset`, that triple never varies, so neither
does the phrase."""


def delete_credential_confirmation_phrase(credential_id: str) -> str:
    """`DELETE_CREDENTIAL <credential_id>` -- `ops.py cmd_delete_credential`'s
    destructive-confirmation phrase. `credential_id` is itself a random,
    never-reused value, minted by either of this codebase's two application-
    credential issuance paths -- the CLI's own `ops._new_credential_id`
    (`issue-credential`) and the in-band `control_plane._new_credential_id`
    (`POST /control/v1/credentials`) -- both producing the identical `crd_` +
    16 lowercase hex format (`_CREDENTIAL_ID_PREFIX`/`secrets.token_hex(8)`).
    Exactly the same reasoning `revoke_last_control_credential_confirmation_
    phrase` above already documents for `ctl_` ids: a deleted row's id can
    never legitimately reappear naming a *different*, later row, so the id
    already serves as its own fingerprint with no separate state fingerprint
    needed.

    Q-1 WP-4 followup (Opus review MA-1): this function itself performs no
    validation -- `ops.cmd_delete_credential` validates `credential_id`
    against `^crd_[0-9a-f]{16}$` (`ops._APPLICATION_CREDENTIAL_ID_PATTERN`,
    matching both minters above) *before* ever calling this function, the
    same way every caller of `delete_confirmation_phrase`/`drop_entity_
    confirmation_phrase`/`drop_index_confirmation_phrase` is downstream of
    `validate_identifier` first. This is what makes contract
    `phrase_construction` rules (c) (a phrase never reflects an unvalidated
    client-supplied string back to the client) and (d) (bounded length) hold
    for the CLI's own phrase, not merely for the data/schema plane's: a
    format-validated `credential_id` is always exactly 20 characters, so the
    `assert` below is unreachable in practice given that upstream check (no
    digest escape hatch is needed here, unlike the where/entity digests
    `delete`/`drop_entity`/`drop_index` fall back to for a contract identifier
    length this format check does not itself bound)."""
    phrase = f"DELETE_CREDENTIAL {credential_id}"
    assert len(phrase) <= _PHRASE_MAX_LENGTH, "delete_credential_confirmation_phrase exceeded the contract's confirmation maxLength"
    return phrase


def require_destructive_confirmation(
    destructive: bool,
    confirmation: Any,
    phrase: str,
    message: str,
    *,
    consequence: str,
    reversible_alternative: str | None,
    recovery: str | None,
) -> None:
    """Shared SI-09 gate for every destructive operation (`delete`,
    `drop_entity`, `drop_index`). Deliberately NOT called from inside
    `bind_mutation`/`bind_schema_operation`: each backend calls it at the
    point in its own execution where it is about to destroy rows/objects,
    which for `ApplicationCell` is after existence/match computation
    (matching this foundation's pre-existing, tested error precedence) and
    strictly before any revision-precondition evaluation (R-4, corrigendum
    m-5: failure-before-execution means an unconfirmed destructive
    operation is refused before a precondition is even looked at).

    Contract 1.2.0 (`destructive_confirmation.valid_confirmation`/`denial`):
    `phrase` is this exact request's own, freshly (re)computed
    `required_confirmation` (one of the `*_confirmation_phrase` functions
    above) -- a valid confirmation is `destructive is True` AND
    `confirmation` equal to `phrase` as an exact Unicode code point sequence
    (no normalization). On denial, `details` carries all four contract-
    required keys (`required_confirmation`/`consequence`/
    `reversible_alternative`/`recovery`); `reversible_alternative`/`recovery`
    are `None` exactly when the caller declares no such path genuinely
    exists (never fabricated -- Q1-D6/design R-2 item 2).
    """
    if not destructive or confirmation != phrase:
        fail(
            "DESTRUCTIVE_CONFIRMATION_REQUIRED",
            message,
            status=409,
            details={
                "required_confirmation": phrase,
                "consequence": consequence,
                "reversible_alternative": reversible_alternative,
                "recovery": recovery,
            },
        )
