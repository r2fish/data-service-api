"""Bearer-token composition (Phase 6 WP-3, design docs/design/
PHASE6_CONTRACT_160_CLIENT_DISCOVERY_V1.md D-1(d)).

Contract 1.6.0 (subordinate ruling 11, item 1): `CredentialIssued.secret`
-- and the `secret` a rotate response returns, on the application and
control surfaces alike -- IS the complete bearer token. A client presents
that exact string, verbatim, as `Authorization: Bearer <secret>`, and must
never compose it, split it into parts, or derive it from any other field
of the response. This peer's own common realization of that opaque string
(a repository-design choice, never written into the contract itself, D-1
decision (b)) is a single "<credential_id>.<secret_part>" token. Phase 6
WP-3 差し戻し 最終ラウンド (supervisor ruling 2026-09-04, 裁定 1) retired
the two HTTP-layer helpers this paragraph originally named here
(`http.py`'s own `_split_bearer`, `control_http.py`'s own `_bearer_pair`)
-- neither `http.py` nor `control_http.py` splits a presented bearer any
more; each passes it straight through, UNSPLIT, to the store/registry
layer below, which is now the ONLY place `split_bearer_locator` (below)
is ever called (see this module's own "receiving boundaries" paragraph
further down for the current, complete list).

Phase 6 WP-3 追補, round 2 (supervisor ruling 2026-09-04): `compose_
bearer_locator`/`split_bearer_locator` are now the SAME name and SAME
signature as r2db-api's own `r2db_api.auth.compose_bearer_locator`/
`split_bearer_locator` (that peer's own WP-2 realization of this
identical D-1(c)/D-1(d) obligation) -- a coordinator ruling that
supersedes this module's earlier, differently-shaped `compose_bearer`/
`split_bearer`(credential_id-scoped)/`recover_secret_part`(fallback-on-
mismatch) trio. `split_bearer_locator` returns `None` for ANY malformed
shape (no `.`, an empty half, or a NUL byte in either half) rather than
raising, and NEVER silently treats an unsplittable value as "already
raw" -- the earlier `recover_secret_part` fallback was a prohibited
two-form-acceptance compatibility shim (a store must accept ONE bearer
shape, not silently tolerate both a composed and a not-yet-composed
secret through the same call surface). Every caller now splits ONCE, at
its own single receiving boundary, and passes the recovered
`(credential_id, secret)` pair (or the `secret` part alone, when
`credential_id` is already known from elsewhere) downstream -- never a
raw, unsplit token.

This module holds the ONE place every real issuance point composes that
token, so the composition itself never has to be re-derived (or, worse,
re-implemented) by a caller. It is intentionally tiny: `compose_bearer_
locator` is used at every point that mints a brand-new secret and must
hand back a ready-to-use bearer -- store/service-layer issuance ONLY
(`credential_store_postgres.PostgresCredentialStore.issue`, `auth.
CredentialStore.issue`/`.rotate`, `control_auth.ControlCredentialStore.
issue`/`.rotate`, `control_credential_store_postgres.
PostgresControlCredentialStore.issue`/`.rotate`, `control_plane.
ControlPlaneService.issue_credential`/`.rotate_credential`'s own response
dicts -- NEVER `control_http.py`'s HTTP response bodies nor `ops.py::
_print_secret_once`, which use the already-composed value verbatim).

Phase 6 WP-3 差し戻し 最終ラウンド (supervisor ruling 2026-09-04, 裁定 1):
`split_bearer_locator` is used at SIX real receiving boundaries -- the
four credential stores' own `authenticate` methods (`auth.
CredentialStore.authenticate`/`.peek`, `credential_store_postgres.
PostgresCredentialStore.authenticate`, `control_auth.
ControlCredentialStore.authenticate`, `control_credential_store_postgres.
PostgresControlCredentialStore.authenticate`), PLUS `control_plane.py`'s
own two independent registries (`InMemoryCredentialRegistry.
authenticate`, `PostgresCredentialRegistry.authenticate` -- this peer's
own control-plane registries, which keep their own separate `authenticate`
implementation and do not share code with `credential_store_postgres.py`,
per this repository's own documented peer-internal split), each splitting
the FULL presented bearer exactly once, internally -- SEVEN call sites in
total (`auth.py` alone accounts for two: `authenticate` and `peek`).
Every caller of those six boundaries (`http.py::HttpService.
authenticate`, `service.MitateDataService.open_session`, `control_http.
py`'s own control-plane handlers via `control_plane.ControlPlaneService`,
`ops.py`'s CLI, the in-process conformance adapter) passes the bearer
straight through, UNSPLIT -- never by a conformance adapter, which must
never split a bearer it did not itself compose (D-1(d), the static "no
composition, no decomposition" fixture this same WP registers; port
v1.10's own designated exception is `tampered_bearer`, brief item C).
"""
from __future__ import annotations


def compose_bearer_locator(credential_id: str, secret: str) -> str:
    """`<credential_id>.<secret>` -- see this module's own docstring.
    Same name/signature/contract as r2db-api's own `auth.compose_bearer_
    locator`: raises `ValueError` if `.` appears in either half (never a
    silent, ambiguous join) -- `credential_id` (`crd_`/`ctl_` + hex) and
    `secret` (`secrets.token_urlsafe(32)`, base64url alphabet) never
    contain `.` themselves, so this is a real precondition check, not a
    defensive no-op."""
    if "." in credential_id or "." in secret:
        raise ValueError("compose_bearer_locator: credential_id/secret must not contain '.'")
    return f"{credential_id}.{secret}"


def split_bearer_locator(token: str | None) -> tuple[str, str] | None:
    """Splits a presented bearer token into its `(credential_id,
    secret_part)` locator pair -- same name/signature/contract as
    r2db-api's own `auth.split_bearer_locator`. Returns `None` for any
    malformed shape -- no token at all, no `.` separator, an empty
    locator half, or a NUL (U+0000) byte in either half -- so every
    caller can fail closed WITHOUT ever looking anything up: a malformed
    token names no row to query in the first place. Never used by an
    issuance path (see `compose_bearer_locator` above, its inverse) --
    only by a receiving boundary, and only ONCE per presented token
    (never re-split downstream)."""
    if not token or "." not in token:
        return None
    credential_id, _, secret = token.partition(".")
    if not credential_id or not secret:
        return None
    if "\x00" in credential_id or "\x00" in secret:
        return None
    return credential_id, secret
