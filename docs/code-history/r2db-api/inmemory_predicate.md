## CH-1132

- moved from: `src/r2db_api/inmemory_predicate.py` (`_predicate_text`)
- parent commit: `4f80a0c`
- kind: docstring

```
The text representation `contains`/`matches` compare a non-string
row value against (WP-3 review D-1~D-4: "型付き非文字列列にも text
表現で適用可") -- matching `PostgresCell._text_expression`'s own text
form (a typed column's `::text` cast, or an untyped JSONB scalar's
`#>> '{}'` unwrap) as closely as Python's/PostgreSQL's differing native
formatting allows.

`field_type` (WP-3 confirmation review N-1 correction: this parameter
did not exist in the first pass, which applied `float8out`-style
formatting unconditionally -- correct for a typed `"number"` column,
but WRONG for an untyped one, where jsonb's own numeric storage rules
apply instead and disagree with `float8out` on both trailing zeros and
scientific-notation expansion) decides which rule a TOP-LEVEL float
uses: `float8out` only when this field is itself a typed `"number"`
column (matching `PostgresCell._text_expression`'s plain `::text`
cast); jsonb's own numeric rules for everything else, including an
untyped top-level column. A top-level dict/list (`_jsonb_text`) and any
NESTED position inside one always use jsonb's own rules regardless of
`field_type` -- nesting only exists inside jsonb storage, which has no
"typed number" concept at all beneath its own root.
```

### correction: 2026-10-06

- reason: a JSON integer in a typed number column is a double precision value, so its text is float8out's (10**15 is 1e+15), not the integer's own digits

old:
```
decides which rule a TOP-LEVEL float uses:
```

new:
```
decides which rule a TOP-LEVEL float or int uses:
```

### correction: 2026-10-06

- reason: same: the typed-column rule covers an int; an untyped int keeps its own digits

old:
```
including an untyped top-level column.
```

new:
```
including an untyped top-level column. An int in a typed `"number"` column is a `double precision` value like any float there, so it takes `float8out` too (`10**15` is `"1e+15"`); an untyped int keeps its own digits.
```
