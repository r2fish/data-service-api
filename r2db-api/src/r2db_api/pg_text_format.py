"""PostgreSQL text-output reproduction for jsonb and `double precision` (ST1).

This is a pure leaf: every function is a total, deterministic string
transform of an already-typed Python value. It opens no connection, reads
no catalog, and consults no request/limits/principal state; the choke
points that decide *which* of these functions applies to a given column
(`PostgresCell._text_expression`, `inmemory_predicate._predicate_text`)
remain in their own modules.
"""
from __future__ import annotations

import json
import math
from decimal import Decimal
from typing import Any


def _float8out_text(value: float) -> str:
    """PostgreSQL `double precision`'s own text-output function,
    `float8out` (WP-3 confirmation review N-1) -- reproduced ONLY for a
    TYPED `"number"` column's TOP-LEVEL scalar (`PostgresCell._text_
    expression`'s plain `::text` cast on a real `double precision` column
    invokes this natively; nothing else in this file (`structured.py`) does).
    The digits are the shortest decimal digit string that lies strictly
    inside the value's rounding interval (the midpoints to the two
    neighbouring doubles, both ends excluded), the closest such string to
    the value -- PostgreSQL's own Ryu search. That is not always Python's
    `repr`, which accepts an end of the interval: `1e23` is
    `9.999999999999999e+22` here. With `e` the decimal exponent of the
    first digit, `-4 <= e < 15` is printed plain (an integer-valued float
    without a `.0`, `100.0` -> `"100"`; `repr` waits for 16, so `1e15` is
    `"1e+15"` here) and everything else as `d.ddde+NN` or `d.ddde-NN` (the
    exponent has at least two digits). `-0.0` is `"-0"` and `0.0` is `"0"`.
    A non-finite value is not a JSON input and keeps its `repr`.

    History: CH-1130
    """
    if value == 0:
        return "-0" if math.copysign(1.0, value) < 0 else "0"
    if not math.isfinite(value):
        return repr(value)
    digits, exponent = _shortest_digits(abs(value))
    sign = "-" if value < 0 else ""
    if -4 <= exponent < 15:
        if exponent < 0:
            return sign + "0." + "0" * (-exponent - 1) + digits
        integer = digits[: exponent + 1].ljust(exponent + 1, "0")
        fraction = digits[exponent + 1 :]
        return sign + integer + ("." + fraction if fraction else "")
    mantissa = digits[0] + ("." + digits[1:] if len(digits) > 1 else "")
    return f"{sign}{mantissa}e{'-' if exponent < 0 else '+'}{abs(exponent):02d}"


_EXACT_INTEGER_LIMIT = 2.0**53


def _shortest_digits(value: float) -> tuple[str, int]:
    """`(digits, exponent)` of a finite positive double: `digits` is the
    shortest digit string (no trailing zeros) strictly inside the value's
    rounding interval, `exponent` the decimal exponent of its first digit.

    Python's `repr` digits are the shortest and closest ones among the
    decimals that read back as the value (the closed interval for an even
    significand, the open one for an odd one), so whenever they lie
    strictly inside the open interval they are also the answer here:
    nothing shorter or closer can be strictly inside without being inside
    the closed interval too.

    Below `_EXACT_INTEGER_LIMIT` (2**53) they always do, with no
    comparison: for `x` in `[2**m, 2**(m+1))` an interval end is an odd
    multiple of `2**(m-53)` (`2**(m-54)` for the lower end at a power of
    two, `2**-1075` below the normal range; both need even more digits),
    which needs more than 17 significant digits for `m <= 51`; for
    `m = 52` an end has 17 digits but `x` itself is an integer of 16
    digits, a shorter candidate strictly inside.

    From 2**53 on one exact comparison decides, and only when the `repr`
    digits sit exactly on an interval end does the search run: for
    `n = 1..17` the `n`-digit decimal nearest the value is the candidate
    and the first one strictly inside is returned. Seventeen digits always
    fit; if none did, the `repr` digits would be returned. The interval is
    asymmetric only around a power of two, which never reaches the search
    (the C-3 corpus compares every power of two with a real server).

    The comparisons are exact integer ones: the value and its two
    neighbours are scaled to a common power-of-two denominator `scale`
    (twice the largest of theirs), so the interval ends -- the midpoints
    to the neighbours, with the top of the largest double mirroring the
    gap below it -- are the integers `low` and `high` over `scale`.
    """
    repr_digits, repr_exponent = _repr_digits(value)
    if value < _EXACT_INTEGER_LIMIT:
        return repr_digits, repr_exponent
    exact_scaled, denominator = value.as_integer_ratio()
    below, below_denominator = math.nextafter(value, 0.0).as_integer_ratio()
    above = math.nextafter(value, math.inf)
    above_numerator, above_denominator = above.as_integer_ratio() if above != math.inf else (0, 1)
    common = max(denominator, below_denominator, above_denominator)
    scale = 2 * common
    exact_scaled *= common // denominator
    below *= common // below_denominator
    above_numerator *= common // above_denominator
    low = exact_scaled + below
    high = exact_scaled + above_numerator if above != math.inf else 3 * exact_scaled - below

    def compare(count: int, exponent: int, bound: int) -> int:
        """-1, 0 or 1: `count * 10**exponent` against `bound / scale`."""
        if exponent >= 0:
            left, right = count * 10**exponent * scale, bound
        else:
            left, right = count * scale, bound * 10**-exponent
        return (left > right) - (left < right)

    repr_power = repr_exponent - len(repr_digits) + 1
    if compare(int(repr_digits), repr_power, low) > 0 and compare(int(repr_digits), repr_power, high) < 0:
        return repr_digits, repr_exponent
    for places in range(1, 18):
        mantissa, _, exponent = ("%.*e" % (places - 1, value)).partition("e")
        count = int(mantissa.replace(".", ""))
        power = int(exponent) - (places - 1)
        if compare(count, power, low) > 0 and compare(count, power, high) < 0:
            text = str(count)
            return text.rstrip("0"), power + len(text) - 1
    return repr_digits, repr_exponent


def _repr_digits(value: float) -> tuple[str, int]:
    """The same pair read off Python's `repr` of a positive double (no
    trailing zeros)."""
    mantissa, _, exponent = repr(value).partition("e")
    whole, _, fraction = mantissa.partition(".")
    digits = whole + fraction
    significant = digits.lstrip("0")
    leading_zeros = len(digits) - len(significant)
    return significant.rstrip("0"), int(exponent or 0) + len(whole) - 1 - leading_zeros


def _jsonb_numeric_text(value: float) -> str:
    """PostgreSQL jsonb's own numeric storage/output (WP-3 confirmation
    review N-1) -- used for every OTHER float position: an UNTYPED top-
    level column, or ANY nested position inside a dict/list, regardless of
    the enclosing field's own declared type (jsonb storage is jsonb either
    way, whether the column is bare or one of this backend's `_r2db_json_
    object`/`_r2db_json_array` DOMAINs over it). Confirmed empirically
    against a real server: jsonb preserves a number's original literal
    text almost verbatim, INCLUDING trailing zeros (`'100.0'::jsonb #>>
    '{}'` stays `"100.0"`, never drops the `.0` the way `float8out` does),
    but always EXPANDS scientific notation to full plain-decimal digits
    (`'1e+20'::jsonb #>> '{}'` -> `"100000000000000000000"`, never
    `"1e+20"`), and has no negative zero (`'-0.0'::jsonb` is `0.0` at the
    top level, in an array and in an object).

    `json.dumps(value)` reproduces the exact text psycopg's `Jsonb` adapter
    sends at INSERT time (this project's own round-trip) -- confirmed
    empirically to match jsonb's stored/re-emitted text byte-for-byte for
    every case that does not need exponent expansion. `Decimal` expands
    the scientific-notation case the same way PostgreSQL's own numeric
    parser does (exact decimal arithmetic, no float re-rounding): `Decimal
    (json.dumps(value))` parses the very same text, and `format(...,
    "f")` renders it in fixed (non-exponential) notation. A zero loses its
    sign first (`abs`).

    History: CH-1131
    """
    if value == 0:
        value = abs(value)
    text = json.dumps(value)
    if "e" in text or "E" in text:
        return format(Decimal(text), "f")
    return text


def _jsonb_scalar_text(value: Any) -> str:
    """A JSON scalar's PostgreSQL `jsonb` text-output form for a NESTED
    position (inside a dict/list), or for an untyped, non-float, top-level
    scalar: `boolean` is the lowercase `true`/`false` literal; `float` uses
    `_jsonb_numeric_text` above (jsonb's own numeric rules, never
    `float8out` -- a nested float is never affected by the enclosing
    field's own declared type, since nesting only exists inside jsonb
    storage to begin with).
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return _jsonb_numeric_text(value)
    if value is None:
        return "null"
    return str(value)  # pragma: no cover - value is always JSON-shaped


def _jsonb_text(value: Any) -> str:
    """PostgreSQL's own `jsonb` text-output rendering for a dict/list value
    (WP-3 review N-1/N-2), used both directly (`_predicate_text`, below (in
    `inmemory_predicate.py`)) and recursively for a nested dict/list. Object
    key order is PostgreSQL's own storage order -- *not* the order the keys
    were written in JSON source, and not Python's default string sort either:
    `(byte length, byte value)`, ascending (confirmed empirically against a
    real server). Nested strings are quoted (`json.dumps`, `ensure_ascii=
    False` to keep non-ASCII characters literal like PostgreSQL's own jsonb
    text output does, rather than Python's default `\\uXXXX` escaping);
    nested scalars reuse `_jsonb_scalar_text` above (never `_float8out_
    text`: nesting only exists inside jsonb storage, so a nested float is
    always jsonb's own numeric rules, independent of whatever the
    enclosing top-level field's own declared type is).
    """
    if isinstance(value, dict):
        keys = sorted(value.keys(), key=lambda k: (len(k.encode("utf-8")), k.encode("utf-8")))
        parts = [f"{json.dumps(key, ensure_ascii=False)}: {_jsonb_text(value[key])}" for key in keys]
        return "{" + ", ".join(parts) + "}"
    if isinstance(value, list):
        return "[" + ", ".join(_jsonb_text(item) for item in value) + "]"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    return _jsonb_scalar_text(value)
