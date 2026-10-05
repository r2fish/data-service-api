## CH-0543

- moved from: `src/mitatedb_api/control_plane.py` (`ControlPlaneService.control_capabilities`)
- parent commit: `0fee6e52cc81da1178f06ed88e0a12260ee705ac`
- kind: comment

```
# Phase 4 WP-3(b) (P4-D4, contract `versioning.version_binding`),
# flipped to 1.5.0 in Phase 5 WP-3 (design D-1, subordinate
# ruling 10 item 1, same commit as the `operations`/
# `target_kinds` declaration keys below -- flip and behavior
# land together, never separately): unconditional (every
# instance of this service declares 1.5.0 now, whether or not
# `audit_query` itself is `enabled` on this deployment; the
# 1.4.0/1.5.0 obligations conditional on `audit_query` being
# provided stay conditional per version_binding's own text).
# Phase 6 WP-3 (design D-1/D-2, subordinate ruling 11):
# flipped to 1.6.0 -- same commit as `surfaces` (already
# present, WP-3 D-2) and the composed-bearer issue/rotate
# responses (`control_http.py::_with_composed_secret`).
#
# Phase 9 WP-3e (design D-1 (5)/(7), F-1): flipped to 1.7.0 --
# the SAME commit as the data-plane document's own identical
# flip (`cell.py::ApplicationRuntime.capabilities`) -- C-19's
# own data/control `contract_version` agreement assert is
# what this pairing keeps green.
#
# Phase 10 WP-6b/pair-closing (design D-5 (v)): flipped again
# to 1.8.0 -- the SAME commit as the data-plane document's own
# identical flip and this host's own `process_ceilings`
# mapping (D-5 (ii)).
```

### correction: 2026-09-25

- reason: Phase 11 WP-3 (docs/design/PHASE11_MIN_COMMON_PROFILE_V1.md §7.1 訂正註「control plane の宣言版」) -- the control-plane document also flips to 1.9.0 in the same commit as the data-plane document's own identical flip (C-19's cross-plane version-match assert)

old:
```
Phase 10 WP-6b/pair-closing (design D-5 (v)): flipped again to 1.8.0 -- the SAME commit as the data-plane document's own identical flip and this host's own `process_ceilings` mapping (D-5 (ii)).
```

new:
```
Phase 10 WP-6b/pair-closing (design D-5 (v)): flipped again to 1.8.0 -- the SAME commit as the data-plane document's own identical flip and this host's own `process_ceilings` mapping (D-5 (ii)).

This control-plane document also flips to 1.9.0 in the same commit as the data-plane document's own identical flip (C-19's cross-plane version-match assert). The control surface's own `capabilities` (`control_plane`/`audit_query`) are unaffected -- 1.9.0's `common_baseline` obligation governs the data surface's application-plane operations only.
```

### correction: 2026-09-25

- reason: this control-plane document also flips to 1.10.0 in the same commit as the data-plane document's own identical flip (C-19's cross-plane version-match assert)

old:
```
This control-plane document also flips to 1.9.0 in the same commit as the data-plane document's own identical flip (C-19's cross-plane version-match assert). The control surface's own `capabilities` (`control_plane`/`audit_query`) are unaffected -- 1.9.0's `common_baseline` obligation governs the data surface's application-plane operations only.
```

new:
```
This control-plane document also flips to 1.9.0 in the same commit as the data-plane document's own identical flip (C-19's cross-plane version-match assert). The control surface's own `capabilities` (`control_plane`/`audit_query`) are unaffected -- 1.9.0's `common_baseline` obligation governs the data surface's application-plane operations only.

This control-plane document also flips to 1.10.0 in the same commit as the data-plane document's own identical flip (C-19's cross-plane version-match assert). The control surface's own `capabilities` (`control_plane`/`audit_query`) are unaffected -- 1.10.0's own obligations govern the data surface's structured-query operations only.
```

### correction: 2026-09-25

- reason: R-110 (undeclared-field refusal alignment, subordinate ruling 16) -- this control-plane document also flips to 1.11.0 in the same commit as the data-plane document's own identical flip

old:
```
This control-plane document also flips to 1.10.0 in the same commit as the data-plane document's own identical flip (C-19's cross-plane version-match assert). The control surface's own `capabilities` (`control_plane`/`audit_query`) are unaffected -- 1.10.0's own obligations govern the data surface's structured-query operations only.
```

new:
```
This control-plane document also flips to 1.10.0 in the same commit as the data-plane document's own identical flip (C-19's cross-plane version-match assert). The control surface's own `capabilities` (`control_plane`/`audit_query`) are unaffected -- 1.10.0's own obligations govern the data surface's structured-query operations only.

This control-plane document also flips to 1.11.0 in the same commit as the data-plane document's own identical flip (C-19's cross-plane version-match assert). The control surface's own `capabilities` (`control_plane`/`audit_query`) are unaffected -- 1.11.0's own obligation governs the data surface's select/where/order_by/mutation-values operations only.
```

### correction: 2026-09-30

- reason: roadmap R-114 (contract 1.12.0, subordinate ruling 17) -- this control-plane document declares 1.12.0 in the same commit as the data-plane document; no behavior change

old:
```
This control-plane document also flips to 1.11.0 in the same commit as the data-plane document's own identical flip (C-19's cross-plane version-match assert). The control surface's own `capabilities` (`control_plane`/`audit_query`) are unaffected -- 1.11.0's own obligation governs the data surface's select/where/order_by/mutation-values operations only.
```

new:
```
This control-plane document also flips to 1.11.0 in the same commit as the data-plane document's own identical flip (C-19's cross-plane version-match assert). The control surface's own `capabilities` (`control_plane`/`audit_query`) are unaffected -- 1.11.0's own obligation governs the data surface's select/where/order_by/mutation-values operations only. This control-plane document declares 1.12.0 in the same commit as the data-plane document, with no behavior change: 1.12.0 only withdraws the contract's own word for the shape of the `audit_requests_per_minute` window, which this service counts as a sliding one.
```

### correction: 2026-09-30

- reason: roadmap R-115 (contract 1.13.0, subordinate ruling 18) -- this control-plane document declares 1.13.0 in the same commit as the data-plane document

old:
```
This control-plane document also flips to 1.11.0 in the same commit as the data-plane document's own identical flip (C-19's cross-plane version-match assert). The control surface's own `capabilities` (`control_plane`/`audit_query`) are unaffected -- 1.11.0's own obligation governs the data surface's select/where/order_by/mutation-values operations only. This control-plane document declares 1.12.0 in the same commit as the data-plane document, with no behavior change: 1.12.0 only withdraws the contract's own word for the shape of the `audit_requests_per_minute` window, which this service counts as a sliding one.
```

new:
```
This control-plane document also flips to 1.11.0 in the same commit as the data-plane document's own identical flip (C-19's cross-plane version-match assert). The control surface's own `capabilities` (`control_plane`/`audit_query`) are unaffected -- 1.11.0's own obligation governs the data surface's select/where/order_by/mutation-values operations only. This control-plane document declares 1.12.0 in the same commit as the data-plane document, with no behavior change: 1.12.0 only withdraws the contract's own word for the shape of the `audit_requests_per_minute` window, which this service counts as a sliding one. This control-plane document declares 1.13.0 in the same commit as the data-plane document (C-19's cross-plane version-match assert).
```

### correction: 2026-10-01

- reason: roadmap R-108 (contract 1.14.0, subordinate ruling 19) -- this control-plane document declares 1.14.0 in the same commit as the data-plane document; no behavior change

old:
```
This control-plane document also flips to 1.11.0 in the same commit as the data-plane document's own identical flip (C-19's cross-plane version-match assert). The control surface's own `capabilities` (`control_plane`/`audit_query`) are unaffected -- 1.11.0's own obligation governs the data surface's select/where/order_by/mutation-values operations only. This control-plane document declares 1.12.0 in the same commit as the data-plane document, with no behavior change: 1.12.0 only withdraws the contract's own word for the shape of the `audit_requests_per_minute` window, which this service counts as a sliding one. This control-plane document declares 1.13.0 in the same commit as the data-plane document (C-19's cross-plane version-match assert).
```

new:
```
This control-plane document also flips to 1.11.0 in the same commit as the data-plane document's own identical flip (C-19's cross-plane version-match assert). The control surface's own `capabilities` (`control_plane`/`audit_query`) are unaffected -- 1.11.0's own obligation governs the data surface's select/where/order_by/mutation-values operations only. This control-plane document declares 1.12.0 in the same commit as the data-plane document, with no behavior change: 1.12.0 only withdraws the contract's own word for the shape of the `audit_requests_per_minute` window, which this service counts as a sliding one. This control-plane document declares 1.13.0 in the same commit as the data-plane document (C-19's cross-plane version-match assert). This control-plane document declares contract 1.14.0 in the same commit as the data-plane document, with no behavior change.
```

### correction: 2026-10-03

- reason: roadmap R-118 (contract 1.15.0, subordinate ruling 20) -- this control-plane document declares 1.15.0 in the same commit as the data-plane document; no behavior change

old:
```
This control-plane document also flips to 1.11.0 in the same commit as the data-plane document's own identical flip (C-19's cross-plane version-match assert). The control surface's own `capabilities` (`control_plane`/`audit_query`) are unaffected -- 1.11.0's own obligation governs the data surface's select/where/order_by/mutation-values operations only. This control-plane document declares 1.12.0 in the same commit as the data-plane document, with no behavior change: 1.12.0 only withdraws the contract's own word for the shape of the `audit_requests_per_minute` window, which this service counts as a sliding one. This control-plane document declares 1.13.0 in the same commit as the data-plane document (C-19's cross-plane version-match assert). This control-plane document declares contract 1.14.0 in the same commit as the data-plane document, with no behavior change.
```

new:
```
This control-plane document also flips to 1.11.0 in the same commit as the data-plane document's own identical flip (C-19's cross-plane version-match assert). The control surface's own `capabilities` (`control_plane`/`audit_query`) are unaffected -- 1.11.0's own obligation governs the data surface's select/where/order_by/mutation-values operations only. This control-plane document declares 1.12.0 in the same commit as the data-plane document, with no behavior change: 1.12.0 only withdraws the contract's own word for the shape of the `audit_requests_per_minute` window, which this service counts as a sliding one. This control-plane document declares 1.13.0 in the same commit as the data-plane document (C-19's cross-plane version-match assert). This control-plane document declares contract 1.14.0 in the same commit as the data-plane document, with no behavior change. This control-plane document declares 1.15.0 in the same commit as the data-plane document, with no behavior change: 1.15.0 only rewrites the contract's retention clause for the `endpoints.audit_query` alias; this surface keeps serving both paths unchanged.
```

### correction: 2026-10-03

- reason: roadmap R-42 (contract 1.16.0, subordinate ruling 21) -- this control-plane document declares 1.16.0 in the same commit as the data-plane document

old:
```
This control-plane document also flips to 1.11.0 in the same commit as the data-plane document's own identical flip (C-19's cross-plane version-match assert). The control surface's own `capabilities` (`control_plane`/`audit_query`) are unaffected -- 1.11.0's own obligation governs the data surface's select/where/order_by/mutation-values operations only. This control-plane document declares 1.12.0 in the same commit as the data-plane document, with no behavior change: 1.12.0 only withdraws the contract's own word for the shape of the `audit_requests_per_minute` window, which this service counts as a sliding one. This control-plane document declares 1.13.0 in the same commit as the data-plane document (C-19's cross-plane version-match assert). This control-plane document declares contract 1.14.0 in the same commit as the data-plane document, with no behavior change. This control-plane document declares 1.15.0 in the same commit as the data-plane document, with no behavior change: 1.15.0 only rewrites the contract's retention clause for the `endpoints.audit_query` alias; this surface keeps serving both paths unchanged.
```

new:
```
This control-plane document also flips to 1.11.0 in the same commit as the data-plane document's own identical flip (C-19's cross-plane version-match assert). The control surface's own `capabilities` (`control_plane`/`audit_query`) are unaffected -- 1.11.0's own obligation governs the data surface's select/where/order_by/mutation-values operations only. This control-plane document declares 1.12.0 in the same commit as the data-plane document, with no behavior change: 1.12.0 only withdraws the contract's own word for the shape of the `audit_requests_per_minute` window, which this service counts as a sliding one. This control-plane document declares 1.13.0 in the same commit as the data-plane document (C-19's cross-plane version-match assert). This control-plane document declares contract 1.14.0 in the same commit as the data-plane document, with no behavior change. This control-plane document declares 1.15.0 in the same commit as the data-plane document, with no behavior change: 1.15.0 only rewrites the contract's retention clause for the `endpoints.audit_query` alias; this surface keeps serving both paths unchanged. This control-plane document declares 1.16.0 in the same commit as the data-plane document (C-19's cross-plane version-match assert); the control surface's own `capabilities` are unaffected -- 1.16.0's obligations govern the requests `limits.execution_ms` names, none of which is a control-surface request.
```

## CH-0925

- moved from: `src/mitatedb_api/control_plane.py` (`<module>`)
- parent commit: `56f51b0`
- kind: docstring

```
`ControlPlaneService`: the control-plane semantics layer (design v1.2
R-6/R-7, WP-4).

Implements the 11 `/control/v1` operations' logic (contract `control_
endpoints`, `spec/data-service-api.v1.json`) as plain Python methods, tested
directly (WP-4's own scope: this module is never mounted behind an ASGI app
in this WP -- see `control_http.py`'s own module docstring and `main.py`,
neither of which reference this module at all yet; the flip is WP-5).

Independent implementation (R-2's closing paragraph: no code sharing
between peers; r2db-api's own `control_plane.py`/`control_main.py` were
read only as a reference for the SHAPE of problems a control plane in this
position has to solve -- the concrete architecture below is different in
several ways: MitateDB has no `ControlAuthority`/`DataService` equivalent
this layer must delegate to for its own pre-existing audit trail, so this
module's own application/credential registries are self-contained rather
than wrapping another class; the in-memory "same transaction" guarantee is
an explicit shared undo-log token (`control_auth._InMemoryWork`) rather
than a per-domain context manager; and control-plane's own writes to the
`applications`/`credentials` tables go through THIS module's own dedicated
registry classes, never through `auth.CredentialStore`/`credential_store_
postgres.PostgresCredentialStore` (the application-plane's read-only view)
-- a deliberate choice reported in the WP-4 completion notes: it keeps
every existing, already-reviewed application-plane file untouched, at the
cost of a second, control-plane-only writer for the same two tables. This
mirrors R-4's own process-role separation (`mitatedbsvc_api` only ever
reads; `mitatedbsvc_controlplane` is a completely separate role) at the
Python-class level too.

Design principle this module follows throughout (matching R-6's own
architecture note in the design document): every processing-order,
authentication/authorization, must_rotate-gate, bound, and audit decision
lives HERE, in `ControlPlaneService` -- never in a backend (`InMemory
ControlBackend`/`PostgresControlBackend` are dumb storage plumbing; they
never refuse anything ControlPlaneService did not already decide to
refuse) and never (in WP-5) in the HTTP binding layer.
```

## CH-0926

- moved from: `src/mitatedb_api/control_plane.py` (`<module>`)
- parent commit: `56f51b0`
- kind: comment

```
# Phase 4 WP-3(b) (design D-5): `audit_query`'s own default/maximum page
# size -- contract `AuditQueryRequest.limit` bounds the wire value to
# `[1, 1000]`; `_DEFAULT_AUDIT_QUERY_LIMIT` is what an omitted `limit`
# defaults to.
```

## CH-0927

- moved from: `src/mitatedb_api/control_plane.py` (`ControlPlaneLimits`)
- parent commit: `56f51b0`
- kind: docstring

```
R-6 numeric constraints (WP-0 M-5; upper bound removed Phase 5 D-3,
Q3 案A, WP-4): `applications`/`credentials_per_application`/`control_
requests_per_minute`/`audit_requests_per_minute` must each be a
positive integer -- **no upper bound is enforced here**, symmetric
with r2db-api's own `ControlPlaneLimits` (`r2db-api/src/r2db_api/
limits.py`). The accepted value is an operator responsibility, carried
through as-declared into `control_capabilities()`; removing the former
`[1, 200]` ceiling also removes the deployment-misconfiguration
guardrail it incidentally provided (`docs/design/
PHASE5_CONTRACT_150_AND_LIMIT_RANGE_V1.md` §3 D-3,
`MitateDB-api/docs/cloud-run-cloud-sql.md` §3.2c). `control_requests_
per_minute` must still exceed `applications + 2*credentials_per_
application + 67` (the headroom+margin inequality a C-14 vector-5-style
position-arithmetic test needs room to walk up to a limit without the
rate window itself becoming the first bound hit) -- this relational
check is independent of the removed ceiling and is unaffected by its
removal. `request_bytes` is a separate byte bound, checked
independently below (also positive-integer only, no upper bound),
declared for parity with R-6's "request_bytes を最初から宣言する"
instruction.
```

## CH-0928

- moved from: `src/mitatedb_api/control_plane.py` (`InMemoryCredentialRegistry.authenticate`)
- parent commit: `56f51b0`
- kind: docstring

```
Phase 4 WP-3(b) (design D-5): a READ-ONLY probe against THIS
registry's own application-credential rows -- reuses the SAME
digest `issue`/`rotate` above already compute (never a separate
auth.CredentialStore lookup, per this module's own header: control-
plane writes/reads its own dedicated registries). Returns
`(application_id, role)` when the presented bearer genuinely
authenticates a currently active (enabled, not revoked) application
credential; `None` for an unknown id, wrong secret, disabled, or
revoked credential -- never raises. Timing-safe: a digest
comparison always runs, against a real or dummy 32-byte value,
regardless of whether `credential_id` is known (mirrors `control_
auth.ControlCredentialStore.authenticate`'s identical convention).
Used only by `ControlPlaneService.audit_query`'s own "application
credentials are FORBIDDEN" probe (D-5) -- never by any other
operation, which authenticates via `_authenticate`/`control_
credential_state` instead.

Phase 6 WP-3 差し戻し 最終ラウンド (supervisor ruling 2026-09-04,
裁定 1): `secret` is the FULL presented bearer -- this method is
this registry's own single receiving boundary, splitting via
`split_bearer_locator` exactly ONCE, HERE, same one-bearer-in
contract every other store on this peer now uses. A malformed
bearer returns `None` directly, with no digest comparison at all
(mirrors `auth.CredentialStore.peek`'s identical treatment).
```

## CH-0929

- moved from: `src/mitatedb_api/control_plane.py` (`PostgresCredentialRegistry.authenticate`)
- parent commit: `56f51b0`
- kind: docstring

```
Phase 4 WP-3(b) (design D-5): the PostgreSQL twin of `InMemory
CredentialRegistry.authenticate` above -- identical contract
(`(application_id, role)` or `None`, never raises for an ordinary
auth failure, timing-safe digest comparison). A genuine store
failure (privilege/configuration defect, unreachable database)
DOES still raise -- `ControlPlaneService.audit_query` lets that
propagate exactly like every other backend call it makes (the
design exemption for store-unreachable audit-write is unrelated to
this READ probe).

Phase 6 WP-3 差し戻し 最終ラウンド (supervisor ruling 2026-09-04,
裁定 1): `secret` is the FULL presented bearer -- splits via
`split_bearer_locator` exactly ONCE, HERE, same one-bearer-in
contract every other store on this peer now uses. A malformed
bearer returns `None` directly, no lookup attempted.
```

## CH-0931

- moved from: `src/mitatedb_api/control_plane.py` (`InMemoryControlBackend.credentials_active_count_locked`)
- parent commit: `56f51b0`
- kind: comment

```
# Phase 10 WP-6b: same reasoning as `applications_count_locked`
# above -- no real lock to take for a single-process, in-memory
# backend.
```

## CH-0932

- moved from: `src/mitatedb_api/control_plane.py` (`InMemoryControlBackend.authenticate_application`)
- parent commit: `56f51b0`
- kind: docstring

```
Phase 4 WP-3(b) (design D-5): a SEPARATE probe against the
APPLICATION-credential universe (`self._credentials`, never
`self._control_credentials`) -- `audit_query`'s own authority check
needs to recognize "this credential_id/secret genuinely belongs to
a real, active application credential" BEFORE ever presenting it to
`authenticate_control`, so it can answer an identified, attributed
`FORBIDDEN` rather than let it fall through as an ordinary,
unattributed `AUTH_INVALID` against the control-credential store it
was never issued against (contract `control_endpoints.audit_query.
semantics`: "Application credentials are denied"). Returns `None`
for every failure mode -- never raises for an ordinary auth
mismatch.
```

## CH-0933

- moved from: `src/mitatedb_api/control_plane.py` (`PostgresControlBackend`)
- parent commit: `56f51b0`
- kind: comment

```
# Q4 phase (design D-1(b), work order §4 WP-2 変更対象 B): the two
# writer timeouts this connection (the ONE that writes `control_
# audit`, inside `unit_of_work` below, in the SAME transaction as
# every control-plane state change) used to carry via `SET
# SESSION` (Phase 4 D-6/N-3) are now `mitatedbsvc_controlplane`'s
# own PostgreSQL role setting (`ALTER ROLE ... SET`, migration
# `0007_platform_declarations.sql`) -- applied automatically at
# login, no client-side action needed. The control-plane
# composition root checks the declared-vs-effective value once at
# startup (`platform_declarations.check_writer_role_timeouts`)
# and derives `visibility_lag_ms` from the SAME catalog
# (`platform_declarations.derive_visibility_lag_ms`) instead of
# this constructor carrying two explicit ms parameters.
```

## CH-0934

- moved from: `src/mitatedb_api/control_plane.py` (`PostgresControlBackend.authenticate_application`)
- parent commit: `56f51b0`
- kind: docstring

```
Phase 4 WP-3(b): identical rationale to `InMemoryControlBackend.
authenticate_application` above -- `self._credentials` is the SAME
`PostgresCredentialRegistry` `issue_credential`/`rotate_credential`/
`set_credential_state` already use.
```

## CH-0935

- moved from: `src/mitatedb_api/control_plane.py` (`ControlPlaneService.__init__`)
- parent commit: `56f51b0`
- kind: comment

```
# Phase 6 WP-3 (design D-2): single source of truth for this
# control-plane process' own `CapabilityDocument.surfaces` --
# composition-root-injected (`control_composition.
# build_control_service`'s own `MITATEDB_DATA_BASE_URL`/
# `_CONTROL_BASE_URL` read), never derived here. `None` (every
# pre-1.6.0-style direct construction -- most of this
# repository's own tests) omits the key entirely.
```

## CH-0936

- moved from: `src/mitatedb_api/control_plane.py` (`ControlPlaneService.__init__`)
- parent commit: `56f51b0`
- kind: comment

```
# Phase 10 WP-6b (design D-5 (ii)): the deployer's own declared
# `process_ceilings.control` (default 1, matching every pre-
# existing direct construction of this class -- this repository's
# own tests included -- `limit_enforcement` for `control_
# requests_per_minute`/`audit_requests_per_minute` stays
# `enforced`, unchanged). `control_composition.
# build_control_service` is the one real caller that passes a
# value read from the single source `platform_declarations.
# read_platform_declarations` returns.
```

## CH-0937

- moved from: `src/mitatedb_api/control_plane.py` (`ControlPlaneService.limits`)
- parent commit: `56f51b0`
- kind: docstring

```
WP-5: a public read accessor for the composition root
(`control_main.build_control_app`) to size the ASGI request-byte
bound (`limits.request_bytes`) from the SAME `ControlPlaneLimits`
instance this service enforces everything else against -- never a
second, independently-configured copy of that number.
```

## CH-0938

- moved from: `src/mitatedb_api/control_plane.py` (`ControlPlaneService._authenticate`)
- parent commit: `56f51b0`
- kind: docstring

```
Phase 6 WP-3 差し戻し 最終ラウンド (supervisor ruling 2026-09-04,
裁定 1): `secret` is the FULL presented bearer -- this peer's own
`control_http.py` HTTP boundary passes the `Authorization: Bearer
<...>` value through UNCHANGED (no pre-split, r2db-api's own
`control_http.py::_extract_bearer` shape), and every public
operation below forwards it here unchanged too. The split into
`(credential_id, secret_part)` happens exactly once, downstream,
inside `self._backend.authenticate_control` (`control_auth.
ControlCredentialStore.authenticate` / `control_credential_store_
postgres.PostgresControlCredentialStore.authenticate`).
```

## CH-0939

- moved from: `src/mitatedb_api/control_plane.py` (`ControlPlaneService._gate_must_rotate`)
- parent commit: `56f51b0`
- kind: docstring

```
Allow-list (never a deny-list, design's own explicit warning):
only `control_capabilities` and a self-targeted `rotate_credential`
pass while `must_rotate` is true. `FORBIDDEN` (WP-0 m-4: C-15
requires this exact code, not `CAPABILITY_UNSUPPORTED`).

Phase 3.5 WP-5 (design §4 M-1): a `role="audit"` principal's own
allow-list while `must_rotate` is true is `control_capabilities`
ONLY -- self-rotate is deliberately NOT extended to it (in practice
`_authorize_role` above already forbids `rotate_credential` for an
audit principal unconditionally, but this method stays role-aware
on its own merits: `list_applications`/`list_credentials` both pass
`_authorize_role`'s allow-list, and this gate must still hold them
back while an audit credential's own `must_rotate` is true). This is
not a dead end: the out-of-band audit-credential issuance ceremony
(`issue_audit_credential_ceremony` below) issues AND rotates the
credential in the same transaction before ever printing a secret, so
a distributed audit credential's `must_rotate` is already `false` by
the time anyone can authenticate with it -- an in-band audit
principal is never actually stuck behind this gate in practice.
```

## CH-0940

- moved from: `src/mitatedb_api/control_plane.py` (`ControlPlaneService._validate_application_id`)
- parent commit: `56f51b0`
- kind: comment

```
# 追補 4 O-1: not an identifier the shared `identifiers.py`
# syntax allowlist governs (a control-plane `application_id`
# has its own, narrower pattern) -- `request_schema`, not
# `identifier_syntax`. No raw candidate value is echoed
# (SI-10): only the declared JSON type pair, mirroring
# `field_types.check_declared_value`'s own convention for a
# value that fails a declared shape.
```

## CH-0942

- moved from: `src/mitatedb_api/control_plane.py` (`ControlPlaneService.issue_credential`)
- parent commit: `56f51b0`
- kind: comment

```
# Phase 6 WP-3 追補 (supervisor ruling 2026-09-04, brief item A):
# composed HERE, at this in-band issuance point's own response --
# `control_http.py`'s HTTP boundary now uses this dict verbatim
# (its own earlier `_with_composed_secret` wrapper is removed),
# and `ops.py cmd_rotate_credential`'s CLI print path (which calls
# THIS SAME service method) receives the composed value too, no
# second composition anywhere downstream.
```

## CH-0945

- moved from: `src/mitatedb_api/control_plane.py` (`ControlPlaneService.rotate_credential`)
- parent commit: `56f51b0`
- kind: comment

```
# O-8 (版フリップ監査, ruling `{scratchpad}/rulings-r3-r7-flip.md`
# 追補4): "対象の状態が操作と矛盾する" refusal (a revoked
# credential cannot be rotated) is a resource-STATE conflict,
# not a request-shape/identifier-syntax/deployment-capability
# question the 11-word `violated_declaration_vocabulary` was
# built to describe -- ConflictError (CONFLICT, status 409),
# matching r2db-api's own same-site fix; not a forced fit into
# ValidationError's own vocabulary. `details` is optional for
# CONFLICT (O-8); `field: credential_id` is kept since one IS
# attributable.
```

## CH-0944

- moved from: `src/mitatedb_api/control_plane.py` (`reset_control_credentials`)
- parent commit: `56f51b0`
- kind: comment

```
# Phase 6 WP-3 追補 (supervisor ruling 2026-09-04, brief item A):
# `.issue()` now returns the COMPOSED bearer as its second element
# (`credential_id`, unchanged, is its first) -- captured here rather
# than discarded, so this function's own return value (below) is the
# composed bearer `ops.py`'s `_print_secret_once` now prints verbatim,
# not the pre-generated raw `secret` local. Before this fix, the
# discarded return value meant `reset`'s own CLI/HTTP callers received
# a raw secret while `bootstrap`'s identical pattern (which already
# captured `.issue()`'s return) received a composed one -- exactly
# the "in-band と帯域外の混在" this WP closes.
```
