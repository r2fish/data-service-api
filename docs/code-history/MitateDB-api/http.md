## CH-0182

- moved from: `src/mitatedb_api/http.py` (`<module>`)
- parent commit: `6e91983`
- kind: docstring

```
ASGI HTTP boundary over the MitateDB-api foundation (WP-3, docs/design/
MITATEDB_PHASE3_HTTP_PERSISTENCE_V1.md v1.2 R-5).

This module owns the HTTP surface only -- authority, structured-operation
validation, and value-domain enforcement all stay in `cell.py`/
`backend_sqlite.py`/`backend_postgres.py`/`auth.py`/
`credential_store_postgres.py` (R-3's own seam split); this file only
translates the contract's endpoint table (`spec/data-service-api.v1.json`)
onto a `HttpService` (below) and maps outcomes to
`application/problem+json`.

Independent implementation (R-2's closing paragraph: no code sharing
between peers): this is not a port of `r2db_api.http`. It follows the same
GENERAL shape (Starlette ASGI app, contract-driven top-level shape
checking, an ASGI-receive-loop byte-bound middleware) because both peers
share the same execution-environment parts by design decision (D-B), not
because either file's own code was copied.

Request shapes are not re-declared with a second (pydantic) type system:
`spec/data-service-api.v1.json` is read at import time and used as the
single source of truth for which top-level request fields are accepted.
```

## CH-0183

- moved from: `src/mitatedb_api/http.py` (`<module>`)
- parent commit: `6e91983`
- kind: comment

```
# --------------------------------------------------------------------------
# Contract as the single source of truth for request shapes (Phase 6
# WP-0, design D-4(b)).
#
# `spec/data-service-api.v1.json` in the common repository remains the
# authored source of truth (CLAUDE.md: this package must not become the
# implicit owner of the public contract). What ships inside this
# distribution is a byte-identical packaged *copy*
# (`mitatedb_api/contract/data-service-api.v1.json`, wired in as package
# data in `pyproject.toml`), loaded via `importlib.resources` so a unit
# installed or copied onto the VPS without the sibling `spec/` checkout
# still imports -- this replaces the prior repository-relative lookup
# (`Path(__file__).resolve()` walked three parent directories up to
# `"spec"`), which broke the moment this package was installed/copied
# anywhere that checkout was not a sibling three directories up (the
# known coupling design D-4(b) closes). `r2db_api.http`'s own loader took
# the identical repository-relative form as a FALLBACK behind its
# packaged copy (never this package's own primary path, which had no
# packaged copy to fall back to before this WP); the supervisor's own WP-0
# peer-symmetry ruling (2026-09-04) removed that fallback too, so both
# peers now resolve the contract exclusively through `importlib.
# resources` against their own packaged copy, no fallback on either side.
# `tests/test_http.py::test_packaged_contract_copy_is_byte_identical_to_
# spec_source_of_truth` asserts the packaged copy never silently drifts
# from `spec/`.
# --------------------------------------------------------------------------
```

## CH-0184

- moved from: `src/mitatedb_api/http.py` (`<module>`)
- parent commit: `6e91983`
- kind: comment

```
# --------------------------------------------------------------------------
# HTTP status <-> contract error code (R-5 m-12: cross-peer status
# agreement is tracked conformance evidence, contract errors.http_status_
# note). Every code this peer can actually emit is listed here, mapped to
# the SAME status r2db-api's own call sites use for that code (grep'd from
# r2db-api/src/r2db_api/*.py's own `fail(...)`/`FoundationError(...)`
# call sites -- r2db-api itself is not imported or modified, only read for
# this cross-check per the task brief). No divergence was needed: every
# code below agrees with r2db-api's own mapping. This peer simply never
# emits several contract codes at all (AUTH_REVOKED, APPLICATION_DISABLED,
# SCOPE_MISMATCH, ATOMICITY_FAILED, IDENTIFIER_INVALID -- `auth.py`/
# `credential_store_postgres.py` fold "revoked"/"disabled" into a single
# `AuthenticationError` -> AUTH_INVALID, and `identifiers.py` raises the
# same `ValidationError` -> VALIDATION_FAILED for a malformed identifier
# as for any other malformed shape); that is a pre-existing fact about
# this peer's own error vocabulary, not something WP-3 narrows, and is
# reported to the requester as a known divergence (not a status mismatch
# -- there is nothing to compare a peer never emits).
#
# Phase 9 WP-3b (design D-4/D-3 (6), 追補 2 S-h): PRECONDITION_FAILED is
# no longer in that "never emits" set -- `errors.PreconditionFailedError`
# (a stale `plan` token) is this peer's first real source of it, mapped
# to 412 -- the SAME status `r2db-api/src/r2db_api/structured.py`/
# `postgres.py` already use for their own (row-level) `PRECONDITION_
# FAILED` `fail(..., status=412)` call sites (cross-peer status
# agreement, R-5 m-12).
```

## CH-0185

- moved from: `src/mitatedb_api/http.py` (`<module>`)
- parent commit: `6e91983`
- kind: comment

```
# `errors.FoundationError` subclass -> contract code, evaluated in order
# (mirrors `conformance_adapter_mitatedb.py::_CLASSIFY_ORDER`, extended
# with `StorageConfigurationError` -- unreachable on the in-process
# adapter's own SQLite backend, real on this HTTP composition's PostgreSQL
# backend/credential store -- mapped to `SERVICE_UNAVAILABLE` per that
# class' own documented proposal, `errors.py`). Phase 4 (design PHASE4_
# DURABLE_AUDIT_SINK_V1.md D-2/D-3): `AuditSinkUnavailable` is likewise
# mapped to `SERVICE_UNAVAILABLE` -- a durable-audit-sink failure on a
# fail-closed-class operation or denial, distinct from both
# `StorageConfigurationError` (a permanent DATA-backend privilege defect)
# and `AuthorizationStateUnavailable` (the credential store's own
# unreachability). Listed explicitly here (not left to the exhaustive-by-
# construction fallback in `_classify` below) so that fallback's own
# "pragma: no cover" comment stays true.
```

## CH-0186

- moved from: `src/mitatedb_api/http.py` (`<module>`)
- parent commit: `6e91983`
- kind: comment

```
# Phase 9 WP-3b (design D-4/D-3 (6), 追補 2 S-h): a stale `plan` --
# a real, present precondition denial, checked at the
# `destructive_confirmation.evaluation_order` precondition stage
# (after confirmation validity, D-4 (2)) -- classifies before
# `ConflictError`/`NotFoundError` here, matching this table's own
# existing convention of listing the more specific denial first
# (`DestructiveConfirmationRequired` already precedes `ConflictError`
# immediately above); no ordering ambiguity arises in practice, since
# no call site ever raises more than one of these for a single
# request.
```

## CH-0187

- moved from: `src/mitatedb_api/http.py` (`<module>`)
- parent commit: `6e91983`
- kind: comment

```
# SI-10: never surface `str(exc)`/SQL/connection details/exception
# internals on the wire. Every code below gets a fixed, static,
# non-interpolated message; the only per-request data that ever
# reaches a response body is `details`, which is itself already
# constrained to the safe, structured shape `errors.
# ResourceLimitError`/`errors.DestructiveConfirmationRequired` publish
# (`limit_class` / the four declare-and-echo keys) -- never the raw
# exception message.
#
# Q4 rework (supervisor ruling 2026-09-05, H-1; design §3.8's own
# "F-12だけは...API応答として利用者に届く"): `PlatformUpgradePending`
# is the ONE exception this exemption applies to -- `isinstance`
# (never the classified `code`, which is the same `SERVICE_UNAVAILABLE`
# every OTHER `StorageConfigurationError` also classifies to) narrows
# to exactly this subclass, so this stays a one-exception carve-out,
# not a hole every current or future `StorageConfigurationError` site
# falls through. `platform_upgrades._f12_message`'s own construction
# already excludes DSN/credential/internal-hostname/declared-value
# text -- only the missing upgrade numbers and the next `ops` command
# appear -- so `str(exc)` is safe to surface verbatim here.
```

## CH-0188

- moved from: `src/mitatedb_api/http.py` (`<module>`)
- parent commit: `6e91983`
- kind: comment

```
# m-6 (independent review): drain the REST of the client's
# body before answering, discarding every remaining chunk, so
# no unread bytes are ever left on the connection. Harmless
# under `httpx.ASGITransport` (this repository's own tests,
# and both conformance adapters, drive this middleware exactly
# that way -- an in-process transport with no real socket to
# leave dangling), but load-bearing under a real ASGI server
# (uvicorn): leaving unread bytes after sending a response
# risks the server treating them as the start of the NEXT
# request on a keep-alive connection, or having to reset the
# connection outright either way. Only drains when the chunk
# that tipped the limit itself declared `more_body: true` --
# calling `receive()` again after a chunk that already
# declared the body complete is not meaningful ASGI protocol
# use and is skipped entirely.
```

## CH-0189

- moved from: `src/mitatedb_api/http.py` (`<module>`)
- parent commit: `6e91983`
- kind: docstring

```
WP-3e rework T2 (追補 L-4): does `value`'s own JSON type fail to
match `prop["type"]` (a bare string, or this contract's `[type,
"null"]` union convention -- `_schema_property_type_name`'s own
sibling reader)? A property schema naming no single JSON type at all
(a `$ref` object like `QueryRequest.page`, or an `enum`-only scalar
like `SchemaOperationRequest.operation`) never mismatches here --
this leg is deliberately confined to a JSON TYPE violation, never an
enum-membership or nested-shape one (those stay exactly where they
already lived, downstream of this shape layer).
```

## CH-0190

- moved from: `src/mitatedb_api/http.py` (`<module>`)
- parent commit: `6e91983`
- kind: docstring

```
Reject unknown top-level fields and missing required fields per
`schema`.

Phase 9 WP-3e (design D-3, V-3/V-6): every denial here is `violated_
declaration: request_schema` (`errors.details_vocabulary`) -- mirrors
r2db-api's own `http._check_object_shape` (task brief: "同型に揃え
る"). `own_path` is this VALUE's own request-internal path (`None`
for the request body itself; `"page"` for the nested `QueryRequest.
page` object; `f"operations/{i}"` for one batch item) and a child
key's own path is `own_path + "/" + key` (or the bare `key` at the
top level). `field` is carried only when the violation is
attributable to exactly ONE position (D-3 (4)): a lone unknown
field, a lone missing required field, or `value` itself failing the
object check. `declared_type`/`observed_type` are carried only for a
VALUE-type violation (`value` itself is not an object, or a required
field is entirely absent) -- never for an unknown-field denial (D-3
(4): the contract's request schema names no type for a field it
does not know).
```

## CH-0191

- moved from: `src/mitatedb_api/http.py` (`<module>`)
- parent commit: `6e91983`
- kind: comment

```
# WP-3e rework T2 (追補 L-4): the leg this function used to lack --
# a key that IS declared by `schema` and IS present in `value`, whose
# own VALUE's JSON type does not match what `schema` declares for it
# (design D-3 (2)/(4)'s own "値の型の違反のときだけ型対" rule, V-6
# applied to this shape layer, not only to `cell.py`'s downstream
# choke points). Checked in a stable (sorted) key order so a request
# violating more than one property's type still reports the SAME one
# deterministically. `missing`-before-`value` (checked above, D-2 (3)
# "検査順序は欠落検査 -> 値検査") already guarantees every key this
# loop inspects is genuinely present, never `absent`. Before this
# leg existed, a request like `{"select": "abc"}` sailed through this
# function unchecked (a known JSON type property carrying the WRONG
# JSON type is not "unknown" and not "missing") and reached a later
# choke point with no `details` at all, or -- worse, `values: "x"`,
# `dict("x")` -- an unhandled exception before any `ValidationError`
# was ever raised.
```

## CH-0192

- moved from: `src/mitatedb_api/http.py` (`<module>`)
- parent commit: `6e91983`
- kind: docstring

```
Contract 1.7.0 provisional gate (design docs/design/
PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md §3 D-1 (3); work
order docs/work-orders/WORK_ORDER_PHASE9_CONTRACT_170_V1.md §2 WP-1 (9)):
`_check_object_shape` above now accepts `dry_run`/`plan`/`budget`/
`enum`/`nullable`/`field_constraints`/`SchemaOperationRequest.
idempotency_key` (the packaged contract copy is already 1.7.0). This
peer's own `constraint_declarations` capability flipped to `enabled`
in the WP-3a commit (`enum`/`nullable`/`field_constraints` removed
from `_PROVISIONAL_UNSUPPORTED_*_FIELDS` below, same commit), and
`dry_run` flips to `enabled` in THIS commit (WP-3b: `dry_run`/`plan`
removed from `_PROVISIONAL_UNSUPPORTED_*_FIELDS` below, same commit
as `cell.py`'s own real dry_run/plan behavior, P-3) -- `budget`/
`idempotency_key` remain `unavailable` (WP-3d/WP-3c), so accepting
either of THOSE and silently ignoring it would still be a P-3
violation (declaration says `unavailable`, behavior accepts the
field).

Phase 9 WP-3e (design D-3 (5), V-7): `details` is now passed through
`CapabilityError.__init__` itself -- the attribute-assignment escape
hatch this function's own pre-WP-3e docstring described (`err.details
= {...}` after construction) is gone. Every 1.7.0 capability this
gate ever covered is `enabled` as of this WP (`_PROVISIONAL_
UNSUPPORTED_*_FIELDS` below are all empty tuples), so this function
currently has no reachable call site -- left in place, undeleted, as
the standing mechanism the next provisional capability would reuse
(mirrors `cell.py`'s identical in-process counterpart).
`_problem_for_exception` already surfaces any `getattr(exc, "details",
None)` regardless of how it was set.
```

## CH-0193

- moved from: `src/mitatedb_api/http.py` (`<module>`)
- parent commit: `6e91983`
- kind: comment

```
# Phase 9 WP-3a (design docs/design/
# PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md D-1 (4)):
# `field_constraints`/`enum`/`nullable` removed from this gate -- same
# commit as `constraint_declarations` flipping to `enabled` below
# (`cell.py::ApplicationRuntime.capabilities`) and the real enforcement
# each governs. Phase 9 WP-3b: `dry_run`/`plan` removed too -- same
# commit as `dry_run` flipping to `enabled` and `post_schema` below
# passing both through to `create_entity`/`add_field`/`alter_field` for
# real. Phase 9 WP-3c/WP-3d: `idempotency_key`/`budget` removed too --
# same reasoning as the mutation/query gates immediately above.
```

## CH-0194

- moved from: `src/mitatedb_api/http.py` (`<module>`)
- parent commit: `6e91983`
- kind: comment

```
# --------------------------------------------------------------------------
# Authentication: `Authorization: Bearer <credential_id>.<secret>`.
#
# WP-3 design decision (reported to the requester, §4 of the completion
# report -- the design document specifies "Authorization ヘッダの
# credential" but does not fix a wire encoding for THIS peer specifically):
# `auth.CredentialStore.authenticate`/`credential_store_postgres.
# PostgresCredentialStore.authenticate` both look a credential up by an
# explicit `(credential_id, secret)` PAIR (`WHERE credential_id = ...`,
# unlike r2db-api's own verifier-keyed single-secret lookup) -- there is no
# way to authenticate with `secret` alone on this peer. The bearer token
# is therefore the two values joined by a single `.`:
# `credential_id + "." + secret`. This is unambiguous: `credential_id`
# (`secrets.token_hex(12)`) and `secret` (`secrets.token_urlsafe(32)`) are
# both produced by this peer's own issuance path and neither alphabet ever
# contains `.`, so `token.split(".", 1)` always recovers the original pair
# exactly. A future in-band `/control/v1 issue_credential` (WP-4/5) would
# need to publish this SAME composite as its own `CredentialIssued.secret`
# field (the contract does not require any particular internal structure
# for that opaque string) for a real client to construct a usable bearer
# token at all.
# --------------------------------------------------------------------------
```

## CH-0195

- moved from: `src/mitatedb_api/http.py` (`<module>`)
- parent commit: `6e91983`
- kind: docstring

```
Phase 6 WP-3 差し戻し 最終ラウンド (supervisor ruling 2026-09-04,
裁定 1): kept only as a documented historical marker -- no code on
this peer constructs this exception any more. Before this round, this
HTTP boundary split a presented bearer itself and raised this class
for an unparseable shape; splitting now happens exactly once, inside
the credential store (`auth.CredentialStore.authenticate`/
`credential_store_postgres.PostgresCredentialStore.authenticate`), so
a malformed bearer reaches this boundary as an ordinary `Authentication
Error` (`AUTH_INVALID`) instead -- `_endpoint`'s own `except` clause
below still names this class for defense-in-depth, but the branch is
unreachable in practice.
```

## CH-0196

- moved from: `src/mitatedb_api/http.py` (`<module>`)
- parent commit: `6e91983`
- kind: comment

```
# --------------------------------------------------------------------------
# HttpService: the one object `create_app` needs from a composition root
# (`main.py` for a real deployment, the conformance adapter for the suite).
# Deliberately NOT `service.MitateDataService` -- that class's own
# `open_session` resolves a cell from an in-process `ControlPlane.cells`
# dict built at `provision_application` time (an in-memory SQLite
# composition, R-3's own "SQLite backend stays local-foundation-only"
# rule) has no notion of "look up this application's own PostgreSQL DSNs
# from the platform registry"; that resolution is this class' own job,
# parameterized by a `cell_factory` callable exactly like r2db-api's own
# composition root (`r2db_api.main.build_app`'s `_cell_factory`,
# independently arrived at here rather than shared code).
# --------------------------------------------------------------------------
```

## CH-0197

- moved from: `src/mitatedb_api/http.py` (`<module>`)
- parent commit: `6e91983`
- kind: docstring

```
Composition-root-agnostic session/session-authority resolution for
the HTTP surface: given a real `credential_store` (the WP-2
`PostgresCredentialStore`, in a real deployment) and a `cell_factory`
that builds a backend-bound `ApplicationCell` for a resolved
`application_id`, this class authenticates a bearer token into a real
`ApplicationRuntime`/`ApplicationDeveloper` session object -- the same
session types `cell.py` already defines, unchanged.
```

## CH-0198

- moved from: `src/mitatedb_api/http.py` (`<module>`)
- parent commit: `6e91983`
- kind: comment

```
# Phase 10 WP-8c (design D-8 (3), review F-2, supervisor ruling
# 2026-09-09 -- WP-8c review round 2): `limit_holder`/
# `max_concurrency` are the SAME `_LimitStateHolder` instance (and
# its own declared `concurrency` bound) `main.build_app` already
# constructs and injects into every `ApplicationCell` it builds
# (`main.py`'s own comment on `limit_holder`) -- given here too so
# `acquire_concurrency_slot` below can reserve a slot on that EXACT
# SAME counter, before authentication, using the deployment's own
# real declared bound (never a value re-derived or guessed here).
#
# FAIL CLOSED, not fail open: round-1 review (F-2) found this pair
# silently no-op'd `acquire_concurrency_slot` below when omitted --
# a future refactor of `main.py`'s own wiring (e.g. dropping these
# two keywords from its `HttpService(...)` call) would then have
# disabled the real deployment's own pre-authentication concurrency
# admission with NO test turning red, since every existing caller
# tolerated `None`. Round 2 (this ruling) removes that silent
# tolerance: EVERY caller of this constructor must now supply both,
# or construction itself raises immediately, loudly, before any
# request is ever served.
#
# Disclosed scope limit (report, "設計への疑義", carried forward
# from round 1): BOTH conformance HTTP adapter's own `HttpService(
# ...)` call sites (`conformance_adapter_mitatedb_http.py`,
# untouched by this WP -- design boundary "conformance adapters は
# 触らない") still omit these two keywords, so this fail-closed
# constructor now raises there too -- that harness's own fixture
# construction breaks under this change. This is a KNOWN,
# REPORTED consequence, not an oversight: fixing it means adding
# `limit_holder=`/`max_concurrency=` to those two call sites, which
# is an edit to a file this WP's own manifest explicitly places
# out of scope; the supervisor's own round-2 ruling defers that
# wiring to the integration branch that folds this WP in.
```

## CH-0199

- moved from: `src/mitatedb_api/http.py` (`_mutation_item`)
- parent commit: `6e91983`
- kind: comment

```
# Phase 4 (design docs/design/PHASE4_DURABLE_AUDIT_SINK_V1.md D-3;
# review m-1, folded into M-3, supervisor ruling 2026-09-03):
# `AUTH_REQUIRED` is in `audit_dispatch.DURABLE_DENIAL_CODES` (D-3's
# own inclusion table -- "認証系 2 コード相当"), but this peer only
# ever constructs it HERE (`_CredentialMissing`, below) -- strictly
# before any credential store is ever consulted (no bearer token
# at all was presented). Without a router here, a durable-range
# code declared in the vocabulary would have no emit site ever
# reachable in this peer's real deployment topology at all.
# `None` (the default) keeps every pre-Phase-4 caller of this
# constructor (this repository's own tests, the in-process
# conformance adapter, which has no HTTP surface at all) working
# unchanged -- a missing router simply means this ONE denial class
# stays undurable, exactly like every OTHER call site before this
# WP wired a router in.
```

## CH-0200

- moved from: `src/mitatedb_api/http.py` (`<module>`)
- parent commit: `6e91983`
- kind: docstring

```
Phase 6 WP-3 差し戻し 最終ラウンド (supervisor ruling 2026-09-04,
裁定 1): this HTTP boundary never splits the presented bearer
itself any more -- it passes `bearer_token` straight through to
`self._credentials.authenticate` (`auth.CredentialStore`/
`credential_store_postgres.PostgresCredentialStore`, whichever
this service was composed with), which is the single choke point
that calls `split_bearer_locator` exactly once. A malformed
bearer is no longer distinguished HERE at all -- it reaches the
store like any other credential and comes back as an ordinary,
unattributed `AuthenticationError` (`AUTH_INVALID`), durably
routed by the store's own pre-auth branch (mirrors r2db-api's
own `http.py::authenticate`, which never pre-splits either).
```

## CH-0201

- moved from: `src/mitatedb_api/http.py` (`<module>`)
- parent commit: `6e91983`
- kind: docstring

```
Phase 10 WP-8c (design D-8 (3), review F-2; fail-closed as of
supervisor ruling 2026-09-09, review round 2): pre-authentication
concurrency admission -- mirrors r2db `service.py::DataService.
acquire_concurrency_slot`'s own identical purpose. `http.py`'s own
route handlers below enter this BEFORE calling `_authenticate`,
and hold it for the caller's own ENTIRE request; the eventual
`ApplicationCell._limit_gate` call this request reaches (through
`ApplicationRuntime`/`ApplicationDeveloper`) recognizes the slot is
already held (`cell.py`'s own `_CONCURRENCY_RESERVED` `ContextVar`)
and does not reserve a second one.

`__init__`'s own fail-closed guard guarantees `self._limit_holder`/
`self._max_concurrency` are never `None` here -- there is no more
no-op branch to fall through to; an instance that could not be
given both never exists in the first place. `main.py`'s real
composition root wires both, so the real deployment gets the real
admission check; the conformance HTTP adapter's own `HttpService(
...)` construction (untouched by this WP) now fails at
CONSTRUCTION time instead of silently disabling this check --
`__init__`'s own comment discloses that consequence.
```

## CH-0202

- moved from: `src/mitatedb_api/http.py` (`<module>`)
- parent commit: `6e91983`
- kind: comment

```
# WP-8b (design D-8 (3)): every endpoint below delegates its own
# synchronous section (authenticate / cell call / psycopg) to `starlette.
# concurrency.run_in_threadpool` so a slow request no longer serializes the
# whole event loop behind it (D-8 (2)'s own measured trigger: a single-
# process `hold_in_flight(n>1)` could not exceed in-flight=1 before this
# WP). `run_in_threadpool` runs on anyio's default worker limiter (40
# threads unless the composition root raises `anyio.to_thread.
# current_default_thread_limiter().total_tokens`, which this WP does not
# do) -- a declared `concurrency` bound above 40 is therefore capped by
# that worker pool, not by `_LimitStateHolder.concurrency_slot`, on a
# single process (a fact only, not a change this WP makes to any limit
# declaration).
```

## CH-0203

- moved from: `src/mitatedb_api/http.py` (`<module>`)
- parent commit: `6e91983`
- kind: comment

```
# Review M-2 (major, supervisor ruling 2026-09-03, "完全案"): threads
# this same request's own `request_id` (`_request_id`, already
# generated by the byte-limiting ASGI middleware and returned as the
# `x-request-id` response header) into the credential-store
# authenticate call -- every call site below reaches `_request_id
# (request)` independently too, for its own subsequent session
# operation, so a single request's own durable rows (an `AUTH_
# INVALID`/`AUTH_REQUIRED` denial here, or an `allow` row from the
# operation that follows) all carry the identical value.
```

## CH-0204

- moved from: `src/mitatedb_api/http.py` (`<module>`)
- parent commit: `6e91983`
- kind: comment

```
# Phase 6 WP-3 (design D-3, item (i)): the contract's 7th `field_type`
# member -- physically the SAME `json` (TEXT) column `object`/`array`
# already use; the declared-type REGISTRY (`cell.py`/`backend_*.py`,
# `field_types.py`), never this map, is what recovers which of the
# three a field actually is.
```

## CH-0205

- moved from: `src/mitatedb_api/http.py` (`<module>`)
- parent commit: `6e91983`
- kind: comment

```
# `SchemaOperationRequest.operation`'s full contract enum. Only
# `create_entity`/`add_field` execute; every other member is a real,
# present denial (`CAPABILITY_UNSUPPORTED`) once this endpoint is mounted
# -- C-17's new present-denial form (design R-8 item 1), never
# `SurfaceAbsent` here (that claim belongs only to the in-process adapter,
# which genuinely has no schema-operations HTTP entry point at all).
```

## CH-0206

- moved from: `src/mitatedb_api/http.py` (`<module>`)
- parent commit: `6e91983`
- kind: comment

```
# --------------------------------------------------------------------------
# Endpoints (spec/data-service-api.v1.json -> "endpoints").
#
# Phase 10 WP-8c (design D-8 (3), review F-2): every handler below now
# enters `service.acquire_concurrency_slot()` as its OWN first statement,
# before `_authenticate` -- the data-plane evaluation order is now BYTE
# BOUND (`RequestByteBoundMiddleware`, this module's `create_app`) ->
# CONCURRENCY SLOT -> AUTHENTICATION -> body read -> rate/business
# (`ApplicationCell._limit_gate`, still entered post-authentication --
# `cell.py`'s own `_CONCURRENCY_RESERVED` `ContextVar` recognizes the slot
# is already held and does not reserve a second one). This mirrors r2db
# `http.py`'s own identical module-header comment verbatim in structure
# (independent realization, no code shared between peers -- R-2's closing
# paragraph): `concurrency` alone is credential-independent, so it alone
# can be evaluated before a credential is known at all; the rate window
# stays keyed by `credential_id` and therefore stays post-auth
# (`_LimitStateHolder.acquire_rate`).
#
# Closes review F-2's own measured gap: before this WP, an unauthenticated
# flood of invalid bearer tokens never touched `_LimitStateHolder._active`
# at all -- `_authenticate`'s own `PostgresCredentialStore` round trip
# absorbed unbounded concurrent demand, regardless of `config.
# max_concurrency`. `acquire_concurrency_slot()` is held for the caller's
# own ENTIRE request -- across both `run_in_threadpool` calls a body-
# carrying handler makes -- via a plain synchronous `with` entered on the
# event-loop thread: `starlette.concurrency.run_in_threadpool` (`anyio.
# to_thread.run_sync`) copies the CURRENT `contextvars.Context` into the
# worker thread it runs on, so a value/lock held on the event-loop thread
# still correctly spans two separate offloaded calls that may each land on
# a different physical OS thread.
# --------------------------------------------------------------------------
```

## CH-0207

- moved from: `src/mitatedb_api/http.py` (`<module>`)
- parent commit: `6e91983`
- kind: comment

```
# M-9 (design §2): application authentication ONLY. This process holds
# no control-credential store at all (R-4's own process-role
# separation), so there is structurally no way to accept a control
# credential here even as a co-hosting convenience.
#
# WP-8b (design D-8 (3)): this endpoint reads no request body, so its
# whole synchronous section -- `_authenticate` (a real
# `PostgresCredentialStore` round trip on this HTTP composition) and
# `session.capabilities` together -- is delegated to `starlette.
# concurrency.run_in_threadpool` as one unit, freeing the event-loop
# thread for other requests' own ASGI I/O while this one runs.
```

## CH-0208

- moved from: `src/mitatedb_api/http.py` (`<module>`)
- parent commit: `6e91983`
- kind: comment

```
# Phase 8 WP-1a rework 1 (裁定 1, 監督裁定 2026-09-06): `request_bytes`
# is `enforced` from `cell.py`'s own single-source declaration on BOTH
# surfaces (the in-process structural estimate `ApplicationCell.
# _limit_gate` runs is transport-independent) -- the former
# enforcement-layer override that used to flip this key from
# `unavailable` to `enforced` for the HTTP surface only is REMOVED in
# this same commit (R-3: a meaningless, redundant re-declaration of
# what the single source of truth already says, once that source
# itself says `enforced`).
#
# `operation_depth` is now the SAME -- `cell.py`'s own single-source
# declaration is `enforced` on BOTH surfaces too (see `cell.py::
# ApplicationRuntime.capabilities()`'s own `limit_enforcement.
# operation_depth` comment for why the WP-1a report's original
# "in-process has no request dict" premise was factually wrong:
# `_check_operation_depth` genuinely runs, in-process included, on
# every request shape `_limit_gate`'s own callers build -- `insert`'s
# own `{"collection": ..., "values": ...}` is a real request dict, not
# an absent one). This wire layer therefore no longer overrides
# `operation_depth` either, for the identical reason it stopped
# overriding `request_bytes` above.
```

## CH-0209

- moved from: `src/mitatedb_api/http.py` (`<module>`)
- parent commit: `6e91983`
- kind: comment

```
# WP-8b (design D-8 (3)): `_authenticate` is delegated on its OWN,
# before the body is even read -- `test_unauthenticated_malformed_
# json_body_is_auth_required_not_validation_failed` (`tests/test_http.
# py`) pins authentication strictly before shape/JSON validation;
# folding it into the tail delegation below would mean reading the
# body (on the loop) before ever authenticating, reordering that
# fail-closed guarantee. Body reading itself (`_read_json_object`,
# immediately below) stays a plain `await` on the event loop, never
# delegated.
```

## CH-0210

- moved from: `src/mitatedb_api/http.py` (`post_schema`)
- parent commit: `6e91983`
- kind: comment

```
# Phase 9 WP-3d (design D-6, B-4): `budget` now reaches `session.read`
# for real -- `ApplicationRuntime.read` (`cell.py`) is what turns it
# into `effective_limits` (`config.narrow_limits_by_budget`,
# `endpoint_kind="query"`) and validates it.
```

## CH-0211

- moved from: `src/mitatedb_api/http.py` (`<module>`)
- parent commit: `6e91983`
- kind: comment

```
# Phase 9 WP-3b rework (M-6): `values` is unconditionally present here
# (`raw.get("values") or {}`, never conditional on `"values" in raw`)
# -- this is this peer's own INTERNAL execution-item vocabulary
# (`ApplicationCell.transact`'s `_TRANSACT_*_KEYS`/`_plan_operation`
# consume it via `.get("values")` either way, so an absent key would
# have executed identically), not something the plan digest reads any
# more (WP-3b closure, H-2): `_mutation_digest_item` immediately below
# builds the digest's own per-operation object straight from `raw`,
# BEFORE this forcing, so an omitted `values` and an explicit `values:
# {}` stay two different digested requests regardless of what this
# execution item itself always carries.
```

## CH-0212

- moved from: `src/mitatedb_api/http.py` (`<module>`)
- parent commit: `6e91983`
- kind: docstring

```
Phase 9 WP-3b closure (追補 2, H-2): the plan digest's own per-
operation object -- unlike `_mutation_item` above (this peer's
INTERNAL execution vocabulary: `type`/`collection`/`filters`/
`confirm`, `values` forced present unconditionally), this is the
contract-level `Mutation`/`ScopedMutation` object AS THE CLIENT
PRESENTED IT: `raw` has already passed `_check_object_shape` against
that exact schema (`_mutation_item`'s own first line, called
immediately before or after this one at every call site), so it
carries only contract-named keys already -- a plain shallow copy, no
key renamed, no optional backfilled, no key forced present. `values`
in particular stays ABSENT here when the request omitted it (WP-3b
review A-3.3: an omitting request and a `values: {}` request must NOT
collide on one plan token -- the exact defect class M-2 already closed
for schema `field_constraints`). `where`'s own predicate objects stay
plain dicts (never converted to a `Filter` dataclass, unlike `_
mutation_item`'s `filters`) -- JSON-native by construction, so no
`default=` hook is ever needed feeding this into `cell.py::normalize_
request_for_plan` (G-4).
```

## CH-0213

- moved from: `src/mitatedb_api/http.py` (`<module>`)
- parent commit: `6e91983`
- kind: docstring

```
Phase 9 WP-3b: shared by `post_mutate`/`post_cross_entity_mutate`
-- `affected` exactly as both computed it before this WP (`zip`
truncates to `len(items)`, so this is unaffected by `cell.py::
ApplicationCell.transact`'s own dry-run envelope, appended -- when
present -- one entry PAST the last real per-item result). `committed`/
`plan` are read off that trailing envelope (a dict `transact()` itself
never returns for a real, non-dry-run request, design D-4 (4)).

Phase 9 WP-3e (design D-7 (2)/(3), Q-1/Q-2): `request_id` is this
tuple's new 4th element, read off the SAME `envelope` -- for a dry
run that is the trailing envelope `cell.py::ApplicationCell.transact`
always appends; for a real commit, `results[-1]` IS one real
operation's own per-item dict, but `cell.py`'s own commit path now
folds `request_id` into it, in place (never a new trailing entry
there, unlike the dry-run envelope -- see that method's own comment
for why: `len(results)` is load-bearing for the pre-v1.13 port).

Rework (Minor m-4, review): `committed`'s own default is `not
dry_run` -- matching the in-process port's own identical `envelope.
get("committed", not dry_run)` (`conformance/conformance_adapter_
mitatedb.py::_mutation_result_to_mapping`) -- rather than the
previous unconditional `True`. `transact()` always appends the
envelope for a dry run (so `envelope.get("committed", ...)` finds a
real `False` there in practice either way) and never for a real
call, where `results[-1]` is instead a real per-item result dict
(e.g. `{"deleted": n}`) that happens to carry no `committed` key --
this default is only ever consulted in that second case, and `dry_run`
is always `False` there too, so the two defaults agree in every
reachable case today; aligning them removes a latent trap for
whichever future change makes them diverge.
```

## CH-0214

- moved from: `src/mitatedb_api/http.py` (`post_schema`)
- parent commit: `6e91983`
- kind: comment

```
# WP-8b (design D-8 (3)): see `post_query`'s own identical comment --
# `_authenticate` is delegated on its own, before the body is read, to
# keep the fail-closed auth-before-shape/JSON-validation ordering
# intact.
```

## CH-0215

- moved from: `src/mitatedb_api/http.py` (`<module>`)
- parent commit: `6e91983`
- kind: comment

```
# `transaction_raw` (rework, G-1): the digest must commit to the
# request AS PRESENTED -- an omitted `transaction` and one explicitly
# spelling out the deployed default (`"atomic"`) are two DIFFERENT
# requests (contract `structured_operations.dry_run.plan`: "a real
# request differing from the dry run in any of them is a different
# request"), so `session.transact` below is given the RAW,
# unbackfilled value -- `None` when the client omitted the key --
# never this method's own resolved `transaction` (backfilled to
# `"atomic"` purely for THIS validation step, unchanged from before
# this rework). C-22 (10)'s own MitateDB-api-http leg is what caught
# this: presenting a dry run's plan back with `transaction: "atomic"`
# newly ADDED must be refused, and it silently was not while `session.
# transact` received the backfilled value on BOTH the dry run and the
# apply alike (both always "atomic", so nothing ever differed).
```

## CH-0216

- moved from: `src/mitatedb_api/http.py` (`<module>`)
- parent commit: `6e91983`
- kind: comment

```
# `digest_items` (WP-3b closure, H-2): the SAME `operations` list,
# built into the CONTRACT-shaped digest object instead of the
# execution item `_mutation_item` builds -- see `_mutation_digest_
# item`'s own docstring.
```

## CH-0217

- moved from: `src/mitatedb_api/http.py` (`<module>`)
- parent commit: `6e91983`
- kind: comment

```
# Phase 9 WP-3b (design D-4): `dry_run`/`plan` now reach `transact()`
# for real -- both defaulted to their own byte-compatible absence
# (`False`/`None`) above, so an unchanged (pre-WP-3b) caller's own
# request is unaffected.
```

## CH-0218

- moved from: `src/mitatedb_api/http.py` (`post_audit_query`)
- parent commit: `6e91983`
- kind: comment

```
# Phase 9 WP-3b rework (M-4/G-1): `transaction_raw` (NOT the
# backfilled `transaction` above) now reaches `session.transact`
# -- `None` when the request omitted the key, `"atomic"` only
# when the request actually named it -- so the digest commits to
# what the request presented, not this endpoint's own resolved
# default. `post_cross_entity_mutate` below has no `transaction`
# field on `ScopedMutationRequest` at all, so it never passes one.
```

## CH-0219

- moved from: `src/mitatedb_api/http.py` (`<module>`)
- parent commit: `6e91983`
- kind: comment

```
# `entity`/`digest_operations` (WP-3b closure, H-1/H-2): `entity`
# is this endpoint's own URL path segment -- `MutationRequest` has
# no `entity` property of its own (it is implicit from the path),
# so it is hoisted to the digest object's own TOP level here
# (`cell.py::ApplicationCell.transact`'s own `entity` keyword) --
# an entity substitution between a dry run and its apply must fail
# closed (H-1). `digest_operations=digest_items` supplies the
# CONTRACT-shaped per-operation objects built above, so `cell.py`
# never falls back to reconstructing them from `items`' own
# internal execution vocabulary.
```

## CH-0220

- moved from: `src/mitatedb_api/http.py` (`<module>`)
- parent commit: `6e91983`
- kind: comment

```
# Phase 9 WP-3c/WP-3d (design D-5/D-6): `idempotency_key`/`budget`
# now reach `session.transact` for real -- both are the SINGLE
# request-level `MutationRequest` values (never per-operation on
# this endpoint's own wire shape), passed straight through as
# this method's own keywords (never folded onto `items`, unlike
# the in-process port's own convention -- see `cell.py::
# ApplicationCell.transact`'s own docstring for why both entry
# points converge correctly either way).
```

## CH-0221

- moved from: `src/mitatedb_api/http.py` (`<module>`)
- parent commit: `6e91983`
- kind: docstring

```
P35 WP-2 (R-3, design docs/design/PHASE35_CROSS_ENTITY_AND_
CONTRACT_130_V1.md §2): the cross-entity counterpart of
`_mutation_item` above -- reads `entity` from EACH operation itself
(contract `ScopedMutation`, `Mutation` + a required `entity`) instead
of a single URL path segment shared by the whole request. Otherwise
identical field-by-field mapping onto `ApplicationCell.transact`'s own
operation-dict vocabulary (`_TRANSACT_INSERT_KEYS`/`_TRANSACT_UPDATE_
KEYS`/`_TRANSACT_DELETE_KEYS` in `cell.py`) -- an unsupported key
(`expected_revision`/`unique_key`) still rides along here exactly as
`_mutation_item` lets it, so `transact()`'s own single choke refuses
it with `CAPABILITY_UNSUPPORTED`, not a second copy of that refusal
at this layer.
```

## CH-0222

- moved from: `src/mitatedb_api/http.py` (`<module>`)
- parent commit: `6e91983`
- kind: comment

```
# Phase 9 WP-3b rework (M-6/G-1): same reasoning as `_mutation_item`'s
# own identical comment -- `values` always present.
```

## CH-0223

- moved from: `src/mitatedb_api/http.py` (`<module>`)
- parent commit: `6e91983`
- kind: docstring

```
P35 WP-2 (R-3/R-5): `cross_entity_mutation` is now `enabled`
(`cell.py::ApplicationRuntime.capabilities()`, same commit) -- this
endpoint dispatches for real instead of raising an unconditional
`CapabilityError`. `session.transact` is the SAME two-pass entry
point (`cell.py::ApplicationCell.transact`) the per-entity
`POST /v1/data/{entity}/mutations` endpoint already uses; the only
difference at this layer is where each operation's own `collection`
comes from (per-operation `entity`, via `_scoped_mutation_item`,
rather than one shared URL path segment).

Phase 9 WP-3c/WP-3d: `idempotency_key`/`budget` now reach `session.
transact` for real, exactly like `post_mutate` above (I-9: this
peer's own `transact()` dispatcher is shared by both endpoints, so
both honor them identically). There is no `transaction` field on
`ScopedMutationRequest` at all (unlike `MutationRequest`) -- a
cross-entity batch has no `best_effort` mode to refuse here.

Response body is `{"committed", "affected"}` ONLY -- no
`assigned_addresses` (design M-6: this peer declares
`row_addressability`/`application_catalog` unavailable, so it has no
address-field vocabulary it could honestly attach to a response;
matches `post_mutate`'s own response shape exactly).
```

## CH-0224

- moved from: `src/mitatedb_api/http.py` (`<module>`)
- parent commit: `6e91983`
- kind: comment

```
# WP-8b (design D-8 (3)): same split as `post_mutate` above --
# `_authenticate` delegated on its own before the body is read (fail-
# closed auth-before-shape ordering preserved), then the shape check
# plus the real `session.transact` call delegated together, after the
# async body read.
```

## CH-0225

- moved from: `src/mitatedb_api/http.py` (`<module>`)
- parent commit: `6e91983`
- kind: comment

```
# `digest_items` (WP-3b closure, H-1/H-2): built straight from `raw`
# per operation -- `ScopedMutation` already names `entity` as one of
# its own contract properties, so each digest item carries its own
# target entity without this endpoint needing a top-level `entity`
# keyword the way `post_mutate` above does (`_mutation_digest_item`
# is the SAME helper `post_mutate` uses -- it does no `Mutation`-vs-
# `ScopedMutation`-specific work of its own, just a shallow copy of
# whatever contract-shaped keys `raw` already carries).
```

## CH-0226

- moved from: `src/mitatedb_api/http.py` (`<module>`)
- parent commit: `6e91983`
- kind: comment

```
# Phase 6 WP-3 (design D-3): `application_catalog: enabled`
# (`cell.py`'s own declaration, same commit) -- `session.catalog()`
# returns the SAME 3-key `EntityDescriptor` shape (`entity`/`fields`/
# `field_types`) for every entity, backed by the declared-type
# registry.
#
# WP-8b (design D-8 (3)): no request body -- `_authenticate` and
# `session.catalog` are delegated together, as one unit, same shape as
# `get_capabilities` above. `session` itself is returned alongside
# `entities` (never re-authenticated on the loop) since `session.
# principal.application_id` is read below, after this call returns.
```

## CH-0227

- moved from: `src/mitatedb_api/http.py` (`<module>`)
- parent commit: `6e91983`
- kind: comment

```
# WP-8b (design D-8 (3)): `_authenticate` delegated on its own,
# before the body is read -- same fail-closed ordering rationale as
# `post_query`/`post_mutate` above.
```

## CH-0228

- moved from: `src/mitatedb_api/http.py` (`<module>`)
- parent commit: `6e91983`
- kind: comment

```
# M-3 (independent review): `SchemaOperationRequest.field_type` is
# a valid top-level property of this request shape (the contract
# gives it no per-operation `if`/`then` narrowing that would
# forbid it on `create_entity`), so `_check_object_shape` above
# accepts a request carrying it here. Silently ignoring it would
# accept a request this peer cannot honor as if it had succeeded:
# a caller naming `field_type: "integer"` alongside `fields:
# ["rank"]` would see `committed: true` yet `rank` is actually
# created as `text` (P3-D1's own untyped-equivalent mapping,
# below) -- confirmed empirically before this fix, a later insert
# of an integer value into `rank` failed with `VALIDATION_FAILED`
# despite the caller having explicitly declared its intended type
# up front and been told the operation committed. `field_type` has
# no per-field association on `create_entity` at all (only a
# single, request-level slot -- see the comment below), so there
# is no way to honor it here; refusing it explicitly, before any
# entity is created, is the same "reject an unread capability-
# shaped key before execution" discipline `cell.py`'s own
# `_TRANSACT_INSERT_KEYS` already applies to `transact()`.
```

## CH-0229

- moved from: `src/mitatedb_api/http.py` (`<module>`)
- parent commit: `6e91983`
- kind: comment

```
# P3-D1 (design §0 exception, WP-1): the contract's `fields` on
# `create_entity` is a bare array of NAMES (no per-field
# `field_type` slot on `fields` itself) -- `SchemaOperationRequest.
# field_type` (singular, scalar) is a single, request-level value
# with no per-field association, refused above; `field_types`
# (plural, this WP) is the per-field carrier instead.
```

## CH-0230

- moved from: `src/mitatedb_api/http.py` (`<module>`)
- parent commit: `6e91983`
- kind: comment

```
# Phase 9 WP-3a (design docs/design/
# PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md D-2 (1)):
# `field_constraints` is passed through verbatim -- `cell.py::
# ApplicationCell.create_collection`/`.create_entity` do the real
# validation (partial-vs-`fields` cross-check, `enum` member/type/
# limit checks) and resolution to a total map; this HTTP layer
# does not re-validate its shape beyond `_check_object_shape`'s
# own top-level key check above.
```

## CH-0231

- moved from: `src/mitatedb_api/http.py` (`<module>`)
- parent commit: `6e91983`
- kind: comment

```
# Phase 9 WP-3b (design D-4): `create_entity` now returns
# `{"revision", "descriptor", "committed"}` for real (`cell.py::
# ApplicationCell.create_collection`) -- read DIRECTLY off that
# same-transaction result rather than the separate, uncounted
# `_post_schema_revision()` readback the two branches below used
# to need (m-2/裁定 3, pre-WP-3b): a dry run rolls the write back
# before this call even returns, so a SEPARATE post-call read
# here would race a concurrent writer and could report a revision
# this dry run's own `plan` was never computed against.
# Phase 9 WP-3b rework (M-2/G-1): `field_types=` below is the RAW,
# PARTIAL declaration the caller actually presented (`field_types_
# map`, only the names `field_types_raw` itself named -- `None`
# when the request omitted `field_types` entirely), never `
# contract_field_types` (the TOTAL, `json`-backfilled map decision
# (ii) above builds so `fields`'s own foundation-type choice below
# has a value for every name). `cell.py::ApplicationCell.create_
# collection` backfills the SAME missing names to `json` on its
# own (via `FOUNDATION_TYPE_TO_CONTRACT_TYPE`, deriving it from
# the foundation type `fields` already carries for that name) --
# so the entity this call creates is byte-identical either way;
# only the `plan` DIGEST changes, from committing to the resolved
# total map (WP-3b review M-2: a request omitting `field_types`
# and one explicitly spelling out the same defaults used to
# collide on one token) to committing to what the request itself
# named.
# `operation` NOT forwarded here (WP-3b closure, H-4): `cell.py::
# ApplicationCell.create_collection`'s own keyword-only PARAMETER
# default (`operation="create_entity"`) already supplies the
# correct digest value for this branch -- this call is only ever
# reached when `schema_operation == "create_entity"` (the `if`
# above), so the two are provably always equal; a genuine
# variable forward from `schema_operation` here would itself be a
# NEW `test_audit_query.py` scanner violation (a `operation=`
# keyword call site whose value's own Name id is not literally
# "operation" is never a recognized safe forward, regardless of
# what it holds) -- the SAME shape of problem `_NON_AUDIT_
# OPERATION_LITERALS` used to work around differently, which H-4
# asks not to reintroduce.
```

## CH-0232

- moved from: `src/mitatedb_api/http.py` (`<module>`)
- parent commit: `6e91983`
- kind: comment

```
# WP-3a rework 3 (real, measured bug): `SchemaOperationRequest.
# field_type` is NOT globally `required` (only `operation`/`entity`
# are, `contract/data-service-api.v1.json`'s own `schemas.
# SchemaOperationRequest.required`), and contract `field_types`'s
# own description states the general rule this peer's
# `create_entity` branch above already honors for `fields`/`field_
# types`: "A field created without a declared type has type json
# -- this names an existing default rather than introducing a new
# one." `add_field`'s own singular `field_type` is that identical
# rule applied to the one field it adds -- an omitted `field_type`
# must default to `json`, not be refused. This peer used to refuse
# every field_type-omitting `add_field` with a bare, details-less
# `VALIDATION_FAILED` ("field and a supported field_type"), a real
# divergence from `r2db-api` (`postgres.py`'s own comment: "`add_
# field` with no `field_type` ... keep[s] the pre-CCR-13 default,
# JSONB") and from this peer's OWN in-process surface (`cell.py::
# ApplicationDeveloper.add_field`'s `field_type` keyword already
# accepts `None`-derived `"json"` via the conformance port's own
# `foundation_type = ... if field_type is not None else "json"`
# translation). A field_type that IS present and outside the
# 7-word vocabulary is still refused, unchanged.
```

## CH-0233

- moved from: `src/mitatedb_api/http.py` (`<module>`)
- parent commit: `6e91983`
- kind: comment

```
# Phase 9 WP-3a (design D-2 (1)): `enum`/`nullable` passed through
# verbatim -- `cell.py::ApplicationCell.add_field` does the real
# validation, same reasoning as `create_entity`'s own identical
# comment above.
# Phase 9 WP-3b: same reasoning as `create_entity` above -- read
# `revision`/`descriptor`/`committed`/`plan` directly off this
# same-transaction result, not a separate post-call readback.
```

## CH-0234

- moved from: `src/mitatedb_api/http.py` (`<module>`)
- parent commit: `6e91983`
- kind: comment

```
# `contract_type=field_type_raw` (WP-3b closure, H-3 (a)): the
# RAW value the request actually carried -- `None` when
# `field_type` was omitted -- NOT `field_type` (this method's
# own local, backfilled to `"json"` two lines above for
# EXECUTION purposes only). `cell.py::ApplicationCell.add_
# field`'s own digest now reads straight off this argument,
# present in the digest only when not `None`; passing the
# backfilled value here would make an omitting request and one
# explicitly spelling out `field_type: "json"` collide on one
# plan token (reproduced: `audit_probe_wp3b.py` P-B).
```

## CH-0235

- moved from: `src/mitatedb_api/http.py` (`<module>`)
- parent commit: `6e91983`
- kind: comment

```
# Phase 9 WP-3a (design D-2 (5)/(6)): present-denial (design R-8
# item 1, C-17) removed for THIS operation -- `alter_field` is now
# a real, executed request. `create_index`/`drop_index`/
# `drop_entity` still fall through to the present-denial `raise`
# below, unchanged by this WP.
```

## CH-0236

- moved from: `src/mitatedb_api/http.py` (`<module>`)
- parent commit: `6e91983`
- kind: comment

```
# Code review §2 A / 監督裁定 A (2026-09-07): `body.get("enum",
# UNCHANGED)` -- NOT a plain `body.get("enum")` -- is the one
# place on the wire this distinction can still be made: `dict.
# get(key, default)` returns `default` ONLY when `key` is absent
# from `body`, so an omitted `enum` reaches `session.alter_field`
# as the `UNCHANGED` sentinel (leaves the field's `enum` as it
# is) while a present `"enum": null` reaches it as a real `None`
# (clears it) -- the contract's own `SchemaOperationRequest.enum`
# is already `["array", "null"]` in this WP's own packaged
# contract copy, so `_check_object_shape` above lets a literal
# `"enum": null` through the shape layer, reaching this line as
# the real `None` that means "clear it".
```

## CH-0237

- moved from: `src/mitatedb_api/http.py` (`<module>`)
- parent commit: `6e91983`
- kind: comment

```
# C-17 present-denial form (design R-8 item 1): `create_index`/
# `drop_index`/`drop_entity` are all real, contract-shaped requests
# this real dispatcher receives and refuses -- never a structural
# absence on this composition, since the entry point genuinely exists
# and executes for `create_entity`/`add_field`/`alter_field` above.
```

## CH-0238

- moved from: `src/mitatedb_api/http.py` (`<module>`)
- parent commit: `6e91983`
- kind: comment

```
# `audit_query: unavailable` (cell.py's own declaration, unchanged this
# WP) -- authenticate with the same application-credential path as
# every other endpoint (fail closed on missing/invalid credentials
# first), but never execute: the contract requires control/audit
# authority for this endpoint and this process holds no control-
# credential store at all (R-4's own process-role separation).
#
# WP-8b (design D-8 (3)): `_authenticate` delegated like every other
# endpoint's own auth call -- the `raise` immediately below does no
# I/O of its own, so it stays a plain synchronous statement on the
# loop, not a second delegation.
#
# Phase 10 WP-8c: wrapped in `acquire_concurrency_slot()` like every
# other endpoint in this module, for the SAME uniform pre-
# authentication ordering (condition 5) -- even though this endpoint's
# own `_authenticate` call is the only gate it ever passes through
# (unchanged, pre-existing design: this stub never reaches `session.
# capabilities`/`.transact`/etc., so it never touches `ApplicationCell.
# _limit_gate` either, before or after this WP).
```
