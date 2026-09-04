"""`credential_wire.split_bearer_locator`/`compose_bearer_locator` --
direct, dedicated unit tests (WP-3 差し戻し 最終ラウンド, supervisor ruling
2026-09-04, 裁定 3, review F4).

No test anywhere in this peer's own suite pinned `split_bearer_locator`'s
own NUL-byte rejection directly before this file -- the property was only
ever exercised indirectly, deep inside a store's own `authenticate()` (this
file closes that gap at the function's own level, fast and PostgreSQL-
independent; `test_postgres.py`'s own
`test_postgres_credential_store_rejects_a_nul_bearing_locator_before_any_
lookup` exercises the SAME property against a real PostgreSQL connection
directly, and `test_application_audit.py`'s own
`test_http_service_durably_audits_a_nul_locator_as_auth_invalid_not_503`
(data plane) / `test_control_main.py`'s own
`test_control_http_durably_audits_a_nul_locator_as_auth_invalid_not_503`
(control plane) exercise it over real HTTP + real PostgreSQL together,
including the durable `authentication_denied`/`authentication_denial`
audit row, per this WP's own 裁定 3)."""
from __future__ import annotations

import pytest

from mitatedb_api.credential_wire import compose_bearer_locator, split_bearer_locator


def test_split_bearer_locator_rejects_a_nul_byte_in_the_credential_id_half() -> None:
    assert split_bearer_locator("crd_\x00nulid.secret") is None


def test_split_bearer_locator_rejects_a_nul_byte_in_the_secret_half() -> None:
    assert split_bearer_locator("crd_nulid.sec\x00ret") is None


def test_split_bearer_locator_rejects_a_nul_byte_in_both_halves() -> None:
    assert split_bearer_locator("crd_\x00nulid.sec\x00ret") is None


def test_split_bearer_locator_accepts_a_well_formed_locator_with_no_nul() -> None:
    assert split_bearer_locator("crd_realid.realsecret") == ("crd_realid", "realsecret")


def test_split_bearer_locator_round_trips_through_compose() -> None:
    bearer = compose_bearer_locator("crd_realid", "realsecret")
    assert split_bearer_locator(bearer) == ("crd_realid", "realsecret")


@pytest.mark.parametrize("malformed", [None, "", "no-dot-at-all", ".", "noid.", ".nosecret"])
def test_split_bearer_locator_rejects_every_other_malformed_shape(malformed) -> None:
    """Not a NUL case -- pins the pre-existing 3 malformed forms
    (absent/no separator/empty half) alongside the NUL case above, in one
    file, so a future regression to any of the 4 forms this function's own
    docstring enumerates is caught here directly, not only indirectly
    through a store's own tests."""
    assert split_bearer_locator(malformed) is None
