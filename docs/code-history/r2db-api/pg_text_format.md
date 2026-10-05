## CH-1130

- moved from: `src/r2db_api/pg_text_format.py` (`_float8out_text`)
- parent commit: `4f80a0c`
- kind: docstring

```
PostgreSQL `double precision`'s own text-output function,
`float8out` (WP-3 confirmation review N-1) -- reproduced ONLY for a
TYPED `"number"` column's TOP-LEVEL scalar (`PostgresCell._text_
expression`'s plain `::text` cast on a real `double precision` column
invokes this natively; nothing else in this file (`structured.py`) does). An integer-
valued float drops its Python-repr trailing `.0` (`100.0` -> `"100"`).
A value already in scientific notation (`repr`'s own choice for
sufficiently large/small magnitudes, e.g. `1e+20`) never ends in `.0`
to begin with, and PostgreSQL's own `float8out` for such magnitudes
also uses scientific notation matching Python's -- so it passes
through unchanged.
```

### correction: 2026-10-06

- reason: the text form is PostgreSQL's float8out: shortest digits strictly inside the rounding interval, plain only for -4 <= e < 15, so a value at 1e15 or above (and a value whose repr digits sit on an interval end) is not what Python's repr shows, and the passes-through-unchanged claim is false

old:
```
An integer-valued float drops its Python-repr trailing `.0` (`100.0` -> `"100"`). A value already in scientific notation (`repr`'s own choice for sufficiently large/small magnitudes, e.g. `1e+20`) never ends in `.0` to begin with, and PostgreSQL's own `float8out` for such magnitudes also uses scientific notation matching Python's -- so it passes through unchanged.
```

new:
```
The digits are the shortest decimal digit string that lies strictly inside the value's rounding interval (the midpoints to the two neighbouring doubles, both ends excluded), the closest such string to the value -- PostgreSQL's own Ryu search. That is not always Python's `repr`, which accepts an end of the interval: `1e23` is `9.999999999999999e+22` here. With `e` the decimal exponent of the first digit, `-4 <= e < 15` is printed plain (an integer-valued float without a `.0`, `100.0` -> `"100"`; `repr` waits for 16, so `1e15` is `"1e+15"` here) and everything else as `d.ddde+NN` or `d.ddde-NN` (the exponent has at least two digits). `-0.0` is `"-0"` and `0.0` is `"0"`. A non-finite value is not a JSON input and keeps its `repr`.
```

## CH-1131

- moved from: `src/r2db_api/pg_text_format.py` (`_jsonb_numeric_text`)
- parent commit: `4f80a0c`
- kind: docstring

```
PostgreSQL jsonb's own numeric storage/output (WP-3 confirmation
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
`"1e+20"`).

`json.dumps(value)` reproduces the exact text psycopg's `Jsonb` adapter
sends at INSERT time (this project's own round-trip) -- confirmed
empirically to match jsonb's stored/re-emitted text byte-for-byte for
every case that does not need exponent expansion. `Decimal` expands
the scientific-notation case the same way PostgreSQL's own numeric
parser does (exact decimal arithmetic, no float re-rounding): `Decimal
(json.dumps(value))` parses the very same text, and `format(...,
"f")` renders it in fixed (non-exponential) notation.
```

### correction: 2026-10-06

- reason: jsonb's numeric has no negative zero: -0.0 is rendered 0.0 (measured against PostgreSQL 16.14 at the top level, in an array and in an object)

old:
```
never `"1e+20"`).
```

new:
```
never `"1e+20"`), and has no negative zero (`'-0.0'::jsonb` is `0.0` at the top level, in an array and in an object).
```

### correction: 2026-10-06

- reason: the zero's sign is dropped before json.dumps

old:
```
renders it in fixed (non-exponential) notation.
```

new:
```
renders it in fixed (non-exponential) notation. A zero loses its sign first (`abs`).
```
