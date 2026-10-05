"""R-39 CS-1 (work order docs/work-orders/WORK_ORDER_R39_TEST_GAPS_V1.md
C1-8a, C1-8b): `postgres_reserved_names._check_reserved_name` called
directly, for the two properties `test_postgres.py`'s
`test_postgres_backend_check_reserved_refuses_pg_prefix_and_audit_events_
exactly` does not fix -- the refusal message's wording, and that the `pg_`
prefix match is case sensitive (`startswith`).

`PG_x` and `Pg_x` are unreachable through the request path (the identifier
syntax rule rejects upper case first); this pins the leaf's own behaviour.
"""
from __future__ import annotations

import pytest

from mitatedb_api.errors import ValidationError
from mitatedb_api.postgres_reserved_names import _check_reserved_name


def test_the_refusal_message_is_reserved_followed_by_the_label() -> None:
    """C1-8a: label `collection` -> `reserved collection`; label `entity`
    -> `reserved entity` (for a `pg_` name and for `audit_events`)."""
    with pytest.raises(ValidationError) as excinfo:
        _check_reserved_name("pg_x", "collection")
    assert str(excinfo.value) == "reserved collection"
    assert excinfo.value.details == {"violated_declaration": "identifier_syntax", "field": "collection"}

    with pytest.raises(ValidationError) as excinfo:
        _check_reserved_name("audit_events", "entity")
    assert str(excinfo.value) == "reserved entity"


def test_the_pg_prefix_match_is_case_sensitive() -> None:
    """C1-8b: `PG_x`, `Pg_x` and `pg` (no underscore) are not refused,
    while the lower-case `pg_x` is."""
    assert _check_reserved_name("PG_x", "entity") is None
    assert _check_reserved_name("Pg_x", "entity") is None
    assert _check_reserved_name("pg", "entity") is None
    with pytest.raises(ValidationError):
        _check_reserved_name("pg_x", "entity")
