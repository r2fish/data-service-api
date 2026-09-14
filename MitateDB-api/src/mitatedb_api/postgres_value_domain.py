"""Pure domain checks for values sent to the PostgreSQL backend."""
from __future__ import annotations

from .errors import ValidationError, observed_type_of, violation


_INT_DOMAIN_RANGES = {
    "int32": (-2147483648, 2147483647),
    "int64": (-9223372036854775808, 9223372036854775807),
}


def _validate_value_domain(value, domain=None, *, field=None, declared_type=None):
    """B-1 value-domain gate (independent review, both rounds). A pure,
    connection-independent function (m-8, round 2: "layer (i) 単体テスト
    は接続不要であるべき") -- `PostgresBackend.encode_value` is a thin
    wrapper that just calls this; `tests/test_postgres.py` also calls it
    directly, with no live server involved, to pin the mechanism itself
    independent of any integration-level round trip (round 2's own
    finding: 3 of the reviewer's 4 mutations survived because the only
    tests exercising this logic went through the FULL insert/read/update/
    delete path, where the layer (ii) backstop produces the identical
    `ValidationError` a layer (i) bypass would have -- masking the
    regression at the black-box level).

    `domain`: one of `field_domains`'s own `"text"`/`"int32"`/`"int64"`/
    `"float"` category strings, or `None` when the caller has no column
    context -- `None` skips domain validation entirely, matching this
    function's own pre-B-1 behavior for that case (shape-checked-but-not-
    domain-checked), never silently WIDENING what a real column call site
    accepts.

    `field`/`declared_type` (追補 4 O-2, `{scratchpad}/rulings-r3-r7-flip.
    md`): this gate reaches every value a NORMAL client request writes or
    filters on (`cell.py::_prepare_values`/`_bind_filters`, the ONLY
    callers of `PostgresBackend.encode_value`, always pass both) -- it is
    the choke-point layer's own PostgreSQL realization of the same D-3 (4)
    4-key `errors.details_vocabulary` rule `field_types.check_declared_
    value` applies in-memory, not backend-layer defence-in-depth (there is
    no in-memory equivalent value-domain check to duplicate wording
    against here in the first place -- the NUL/lone-surrogate/int-range
    conditions below are genuinely PostgreSQL-storage-only, but a client
    request reaches them directly all the same, so the DENIAL it receives
    must still carry the 4-key form). `field` is the caller's own
    request-internal path (never composed here -- this function has no
    path context of its own, exactly `field_types.check_declared_value`'s
    own precedent); `declared_type` is the contract vocabulary word
    (`CONTRACT_TYPES`) the caller already resolved. Both default to
    `None` so this function's own direct callers in `tests/test_postgres.
    py` (mechanism-level unit tests, no request context at all) keep
    working unchanged.
    """
    # M-5 (independent review round 2, regression from B-1's own first
    # round): SQL `NULL` is a valid value for ANY column regardless of its
    # declared type (this foundation defines no `NOT NULL` constraint
    # anywhere, `migrations/0003_provision_application.sql`) -- domain
    # validation must never apply to it. The pre-fix `_check_domain`
    # rejected `None` unconditionally (every domain branch's own
    # `isinstance` check is `False` for `None`, falling through to "value
    # does not match the declared field type"), which made writing OR
    # filtering on `NULL` impossible on this backend even though SQLite
    # (no domain concept at all) and the schema itself both allow it --
    # checked FIRST, before anything else in this function, so nothing
    # below ever sees `None`.
    if value is None:
        return None
    # Deterministic, pre-execution rejection (independent-review
    # finding, WP-1 P3 round 2 instruction #1): PostgreSQL's `text`
    # storage cannot represent an embedded NUL (U+0000) codepoint at
    # all -- the common conformance corpus (`conformance-tests/
    # payloads.py`'s `nul_byte = "value\x00tail"`) presents exactly
    # this as a real value-position payload. The SQLite backend's own
    # round-trip-accepts behavior for the identical payload is
    # UNCHANGED (`backend_sqlite.py` has no equivalent check) -- a
    # genuine, backend-specific value domain difference, not a bug.
    #
    # A dict/list value has already become a JSON string by this
    # point (`cell.ApplicationCell._normalize_value`), and `json.
    # dumps` always escapes a NUL codepoint as the 6-character
    # backslash-u-0000 sequence in its OWN output text -- never a raw
    # NUL byte -- so nothing further is needed for the dict/list case;
    # only a value that is ALREADY a plain `str` at this point can
    # carry a literal NUL through to a bind parameter.
    if isinstance(value, str) and "\x00" in value:
        raise ValidationError(
            "value contains an embedded NUL character, which PostgreSQL text storage cannot represent",
            details=violation("field_type", field=field, declared_type=declared_type, observed_type=observed_type_of(value)),
        )
    # Independent review B-2(ii) (WP-2 follow-up, same precedent as the
    # NUL check immediately above): a Python `str` may contain a LONE
    # UTF-16 surrogate code point (U+D800-U+DFFF) that is not part of a
    # valid surrogate pair -- CPython's own `str` type allows constructing
    # one (a literal `"\ud800"`, `surrogateescape`-decoded bytes, ...)
    # even though no real Unicode text ever legitimately contains one.
    # Measured directly (WP-2 review): binding such a value as a psycopg
    # parameter raises a raw `UnicodeEncodeError` at the driver's own
    # UTF-8 encoding step -- neither a `psycopg.Error` subclass NOR any
    # `errors.FoundationError` this module's own layer (ii) backstop (in `backend_postgres.py`)
    # (`except psycopg.Error`, this module's per-DML-method final clause) (in `backend_postgres.py`)
    # ever catches, since the encoding happens before psycopg even issues
    # a wire message PostgreSQL could reject. Rejected here, deterministically,
    # at validation time -- the same treatment the embedded-NUL case
    # above already gets, and for the identical reason (`cell.
    # ApplicationCell._normalize_value` already turned any dict/list
    # value into JSON text via `json.dumps`, which always escapes a lone
    # surrogate as the 6-character `\ud800`-style sequence in its OWN
    # output text, never a raw surrogate code point -- so only a value
    # that is ALREADY a plain `str` at this point can carry one through
    # to a bind parameter, exactly as for NUL).
    if isinstance(value, str) and any(0xD800 <= ord(ch) <= 0xDFFF for ch in value):
        raise ValidationError(
            "value contains a lone UTF-16 surrogate code point, which cannot be encoded as UTF-8",
            details=violation("field_type", field=field, declared_type=declared_type, observed_type=observed_type_of(value)),
        )
    # See this module's own `_TYPES` comment (in `postgres_types.py`): `boolean` fields are
    # physically `INTEGER` columns on this backend (as on SQLite's),
    # so a Python `bool` is converted here too -- keeping both
    # backends' own observable value representation identical. This
    # runs BEFORE the domain check below so an `int32`/`int64` domain
    # check sees a plain `int`, never a `bool` (`isinstance(True,
    # int)` is `True` in Python, which would otherwise let a stray
    # `bool` slip through an `int` domain check unconverted).
    if isinstance(value, bool):
        value = int(value)
    if domain is not None:
        value = _check_domain(value, domain, field=field, declared_type=declared_type)
    return value


def _check_domain(value, domain, *, field=None, declared_type=None):
    """B-1 (i): the actual value-domain gate, a pure function (m-8).
    Runs BEFORE any statement reaches PostgreSQL, so a type-mismatched
    value never gets the chance to raise `InvalidTextRepresentation`/
    `NumericValueOutOfRange`/etc. at the driver level. Every rejection
    message here starts with "value" and says "does not match"/"is out of
    range" -- deliberately worded differently from the layer (ii)
    backstop's own generic "storage backend rejected the request" (every
    DML/DDL method's final `except psycopg.Error` branch, in `backend_
    postgres.py`), so a test can tell WHICH layer actually caught a given
    case (m-8 (ii)).

    `field`/`declared_type`: same 追補 4 O-2 threading as `_validate_value_
    domain` above (this is that function's own
    callee, `field`/`declared_type` pass straight through unchanged)."""
    if domain in ("string", "object", "array", "json"):
        # See `_TEXT_DOMAIN_BY_DECLARED_TYPE`'s own comment (in
        # `postgres_types.py`): the real object-vs-array-vs-json shape
        # check already ran at the cell layer (design G3) -- by this
        # point every one of these four declared types is physically a
        # plain `str` (JSON text for the three non-`string` members).
        if not isinstance(value, str):
            raise ValidationError(
                "value does not match the declared field type",
                details=violation("field_type", field=field, declared_type=declared_type, observed_type=observed_type_of(value)),
            )
        return value
    if domain in _INT_DOMAIN_RANGES:
        if not isinstance(value, int):
            raise ValidationError(
                "value does not match the declared field type",
                details=violation("field_type", field=field, declared_type=declared_type, observed_type=observed_type_of(value)),
            )
        low, high = _INT_DOMAIN_RANGES[domain]
        if not (low <= value <= high):
            raise ValidationError(
                "value is out of range for the declared field type",
                details=violation("field_type", field=field, declared_type=declared_type, observed_type=observed_type_of(value)),
            )
        return value
    if domain == "float":
        if not isinstance(value, (int, float)):
            raise ValidationError(
                "value does not match the declared field type",
                details=violation("field_type", field=field, declared_type=declared_type, observed_type=observed_type_of(value)),
            )
        return float(value)
    return value
