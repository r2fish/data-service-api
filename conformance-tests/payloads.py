"""Shared injection payload corpus for the C-03 structured-injection
condition (design section 6.2).

Categorized dicts are kept alongside the flat lists so a failure report can
name which category tripped, without any test file needing its own copy of
the corpus.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Identifier-position corpus. Every one of these is, by construction, not a
# valid common-contract identifier (`^[A-Za-z_][A-Za-z0-9_]*$`); every
# identifier position must reject every one of them.
# ---------------------------------------------------------------------------

IDENTIFIER_PAYLOAD_CATEGORIES: dict[str, str] = {
    "statement_terminator": "users;",
    "comment_dash": "users--",
    "comment_block": "users/*comment*/",
    "quote_escape_single": "users'",
    "quote_escape_double": 'users"',
    "tautology": "' OR '1'='1",
    "identifier_quote_backtick": "`users`",
    "identifier_quote_bracket": "[users]",
    "embedded_newline": "users\nname",
    "embedded_nul": "users\x00name",
    "embedded_whitespace": "users name",
    "qualified_name": "a.b",
    "wildcard": "*",
    "empty_string": "",
    "starts_with_digit": "1users",
    "long_string": "a" * 300,
    "non_ascii": "usérs",
    "fullwidth": "ユーザー",  # full-width (zenkaku) katakana, not half-width
}

IDENTIFIER_PAYLOADS: list[str] = list(IDENTIFIER_PAYLOAD_CATEGORIES.values())

# design section 6.2: non-string values presented where an identifier is
# expected.
NON_STRING_IDENTIFIERS: list[object] = [None, 0, 1, True, [], {}, 1.5]

# ---------------------------------------------------------------------------
# Value-position corpus. These are *not* required to be rejected outright:
# design section 5.2 item 4 requires either a byte-equivalent round trip or a
# classified ConformanceDenial. Silent mutation/truncation/normalization is
# the failure mode under test.
# ---------------------------------------------------------------------------

VALUE_PAYLOAD_CATEGORIES: dict[str, str] = {
    "statement_fragment": "'; DROP TABLE users; --",
    "format_placeholder_percent_s": "%s",
    "format_placeholder_question": "?",
    "format_placeholder_dollar_1": "$1",
    "template_expression": "{{7*7}}",
    "nul_byte": "value\x00tail",
    "embedded_newline": "line one\nline two",
    "non_ascii": "ünïcödé—テスト",
}

VALUE_PAYLOADS: list[str] = list(VALUE_PAYLOAD_CATEGORIES.values())
