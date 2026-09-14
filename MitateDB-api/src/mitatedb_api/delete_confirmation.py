"""MitateDB delete-confirmation phrase construction (CE1).

This is a pure leaf: `_canonical_where_json` is a total, deterministic
JSON serialization of an already-validated `Filter` list, and
`_delete_confirmation_phrase` is a total, deterministic string
composition over its own arguments plus a sha256 digest of the former.
Neither opens a connection, reads a catalog, or consults any
request/limits/principal state; the choke point that decides whether a
`delete` may proceed at all (`ApplicationCell._validate_delete_
confirmation`, in `cell.py`) remains in its own module.
"""
from __future__ import annotations

import hashlib
import json


def _canonical_where_json(filters):
    """Canonical JSON serialization of a `delete` request's own selection
    (contract `phrase_construction` rule "scope-included"): each `Filter`
    becomes a key-sorted object; the outer list's own ORDER is preserved,
    not sorted (an intentional choice, matching r2db-api's own documented
    n-6 finding: two requests presenting the identical predicate set in a
    different order are treated as different requests, not folded onto one
    phrase -- this peer does not treat where-clause order as insignificant
    on the caller's behalf).

    Deliberately no `default=str` (r2db-api WP-3 followup m-7): every
    `Filter.value` reaching this point has already passed `_bind_filters`'s
    own `ApplicationCell._normalize_value` (dict/list/bool/str/int/float/
    None only, raising `ValidationError` for anything else) by
    construction -- `delete` below (in `cell.py`) always calls this on the caller's own,
    un-encoded `filters` argument BEFORE `_bind_filters` runs, but the same
    shape guarantee already holds because `delete` requires `filters` be a
    non-empty list of `Filter` instances first -- so a value this
    `json.dumps` cannot serialize natively would mean that invariant broke
    elsewhere; surfacing that as an immediate `TypeError` here is more
    honest than silently collapsing it into a string that could coincide
    with a different value's own string form.
    """
    payload = [{"field": f.field, "operator": f.operator, "value": f.value} for f in filters]
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _delete_confirmation_phrase(collection, filters, schema_revision):
    """`DELETE <collection> @where=<digest16> @schema_revision=<n>` --
    digest16 is the first 16 hex characters of the SHA-256 of
    `_canonical_where_json(filters)`; `schema_revision` is this
    application's current schema-revision counter (P3 WP-1 round 2
    instruction #5 -- see the module-level comment above (in `cell.py`)
    `_DELETE_CONSEQUENCE` for why this was added). `collection` must
    already be identifier-validated by the caller (contract
    `phrase_construction` rule "only identifier-validated target names")
    -- `ApplicationCell.delete` below (in `cell.py`) always calls this only after
    `ApplicationCell._identifier(collection, ...)` has succeeded.

    Length: identifiers are bounded to 63 characters
    (`identifiers._IDENTIFIER`), so `"DELETE " (7) + collection (63) +
    " @where=" (8) + digest16 (16) = 94` (the original, pre-schema-
    revision proof) `+ " @schema_revision=" (18) + digits(schema_revision)`.
    `schema_revision` is a plain, monotonically-increasing non-negative
    counter incremented once per `create_collection`/`add_field` call this
    process ever makes -- bounding its own decimal digit count to 144
    (`94 + 18 + 144 = 256`, exactly the contract `confirmation` field's own
    `maxLength`) covers every value up to `10**144`, a number of schema
    mutations no real process could ever perform (bounded, in this
    foundation, by `FoundationConfig.max_schema_objects`/`max_fields`
    per application in the first place) -- so the bounded-digest escape
    hatch contract `phrase_construction` rule "bounded" describes is never
    actually needed on this peer, exactly as the original (pre-schema-
    revision) proof already concluded. n-1 correction (independent
    review, carried forward unchanged): the `assert` below is NOT itself
    what proves this invariant -- `assert` statements are stripped
    entirely when Python runs under `-O`/`PYTHONOPTIMIZE`, so it must
    never be the only thing standing between this function and an
    over-length phrase. The real proof is the arithmetic above; the assert
    is a development-time backstop that fixes this reasoning in an
    executable form, not a substitute for it, and not load-bearing under
    `-O`.
    """
    digest = hashlib.sha256(_canonical_where_json(filters).encode("utf-8")).hexdigest()[:16]
    phrase = "DELETE " + collection + " @where=" + digest + " @schema_revision=" + str(schema_revision)
    assert len(phrase) <= 256, "delete confirmation phrase exceeds contract confirmation maxLength"
    return phrase
