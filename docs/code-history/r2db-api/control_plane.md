## CH-0239

- moved from: `src/r2db_api/control_plane.py` (`<module>`)
- parent commit: `6e91983`
- kind: docstring

```
`ControlPlaneService` (CCR-14 WP-3): the control-plane semantics layer.

Design this file is written against: docs/design/R2DB_CCR14_CONTROL_PLANE_V1.md
v1.5, §2 (endpoint/service mapping and the common processing order), §3
(service-layer composition), R-5 (must_rotate gate)/R-6 (durable audit)/R-7
(limits)/R-9 (capability discovery)/R-11 (deterrence declarations), §5's
WP-3 row, §7 (risk/review focus), and §10/§11 (WP-1/WP-2 supervisor
decisions this WP inherits: required `work` on every store's state-changing
method, the `applications` two-state registry, `ControlCredentialStore`'s
own revoked-refusing `rotate`).

Architecture (§0/§3, a bound supervisor decision): `ControlPlaneService` is a
*shared semantics layer* -- processing order, authentication, the
must_rotate gate, `role=control` issuance refusal, R-7 limits, R-6 audit
(including the same-transaction guarantee and durable denial recording), and
the R-11 deterrence declarations all live *here*, never in a backend and
never (in a later WP) in the HTTP binding layer. This mirrors the exact
"拒否の所在" lesson design §3/§7 calls out from an earlier phase (a prior
B-1 defect: a refusal implemented in the bind layer instead of the service
layer silently stopped applying through a second, in-process call path).

Two backend implementations share one call surface (`ControlBackend`,
below), the same pairing convention CCR-13 established for storage cells:

- `InMemoryControlBackend` wraps `ControlAuthority` (+ the in-memory
  `CredentialStore`/`ControlCredentialStore`). Every operation `Control
  Authority` already implements (register/enable/disable application,
  issue/set-state credential) is delegated to it, not reimplemented here --
  this is what keeps `ControlAuthority`'s own semantics (and its own,
  pre-existing in-memory audit trail, used by the in-process conformance
  adapter and this repository's own tests) authoritative for both callers
  instead of forking into two implementations of "register an application".
  Operations `ControlAuthority` has no concept of at all (list, rotate,
  control-credential lifecycle) talk to the in-memory stores directly.
- `PostgresControlBackend` talks to the WP-2 Postgres store trio directly
  (`PostgresCredentialStore`/`PostgresControlCredentialStore`/the new
  `PostgresApplicationRegistry`) -- there is no `DataService`/`ControlAuthority`
  in a real WP-4+ deployment of this surface at all (it is a *separate*
  process from the application-plane API, R-1/R-3), so direct-to-store is
  the only option, not a shortcut.

Both backends are deliberately dumb: everything a backend method raises
(`NOT_FOUND`/`CONFLICT`/`VALIDATION_FAILED` from the underlying stores) is
allowed to surface through unchanged; `ControlPlaneService` never asks a
backend "is this allowed" -- it decides that itself, then tells the backend
what to persist.

Single-commit rule (design §5, still binding for this WP): `control_plane`
stays declared `unavailable` in every public capability document this
codebase already emits (`DataService.capabilities`, `config/capabilities.
json`) -- neither of those files is touched here. This module connects to no
HTTP surface, ASGI app, or composition root; `control_http.py`/`control_main.
py` do not exist yet (WP-4). Constructing a `ControlPlaneService` is, as of
this WP, something only this module's own tests do.
```

## CH-0240

- moved from: `src/r2db_api/control_plane.py` (`<module>`)
- parent commit: `6e91983`
- kind: comment

```
# Contract 1.2.0 `destructive_confirmation` (design docs/design/
# DESTRUCTIVE_CONFIRMATION_V1.md R-3): the last-active-control-credential
# revoke gate's own four declarations. Fixed, verbatim text -- like R-11's
# declarations above, these are conformance-testable literals, never
# regenerated per call. `reversible_alternative` is truthful about a real
# limitation (WP-0 m-7, precision corrected by Opus review minor m-6):
# `disable_credential` genuinely reverses this specific revoke (a disable,
# not a revoke), but re-enabling the LAST disabled control credential is
# itself gated behind its OWN separate out-of-band break-glass procedure
# (`enable-control-credential`) -- distinct from `recovery`'s own `reset`
# ceremony below, not "the same" one (an earlier revision of this text
# conflated the two, which is not truthful: `reset` mints a fresh
# credential and revokes every prior one, while `enable-control-credential`
# re-enables the SAME still-existing, merely-disabled row -- two different
# procedures, not one). Either way, the "alternative" does not actually
# avoid needing an out-of-band step, it only defers which one. `recovery`
# matches `r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md` §12/§13 (WP-0
# m-2: that runbook, not DEPLOYMENT_RUNBOOK).
```

## CH-0241

- moved from: `src/r2db_api/control_plane.py` (`<module>`)
- parent commit: `6e91983`
- kind: comment

```
# R-6 (design §4): exactly the denial codes design's own enumeration names
# as requiring durable audit (authentication failure, the must_rotate gate,
# and the `role=control` capability refusal). `AUTH_STATE_UNAVAILABLE` is
# deliberately excluded -- it is a service-health outcome (the store itself
# is unreachable/unavailable), not an adversarial denial, and attempting a
# durable write in that same moment is likely to fail too, compounding the
# outage into a second 503 for no benefit. Round-2 review MA-1 (supervisor
# ruling): `AUTH_REQUIRED` (no secret presented at all) is INCLUDED here --
# it is the cheapest possible probe against this surface, and the rate
# limiter already runs before this check (design §4's own "監査増幅の防止"
# reasoning already covers it), so there is no audit-amplification concern
# left to justify excluding it; leaving it out created exactly the asymmetry
# R-11 exists to close (a garbage-secret probe left a trace, a no-header
# probe left none).
```

## CH-0242

- moved from: `src/r2db_api/control_plane.py` (`ControlBackend`)
- parent commit: `6e91983`
- kind: comment

```
# Phase 4 WP-2(b) (design D-5): `audit_query`'s own default/maximum page
# size -- contract `AuditQueryRequest.limit` bounds the wire value to
# `[1, 1000]`; `_DEFAULT_AUDIT_QUERY_LIMIT` is what an omitted `limit`
# defaults to.
```

## CH-0243

- moved from: `src/r2db_api/control_plane.py` (`<module>`)
- parent commit: `6e91983`
- kind: comment

```
# Phase 10 WP-6a (design D-5(ii), contract 1.8.0): this plane's own region
# (ii) -- `ControlPlaneLimits` classes bound by in-memory, per-process
# state (`self._rate_window`/`self._audit_rate_window`), the only classes
# whose `limit_enforcement` mapping depends on `process_ceiling`. Every
# other `ControlPlaneLimits` class is either region (i) (`request_bytes`,
# request-scoped) or region (iii) (`applications`/`credentials_per_
# application`, bound in PostgreSQL under a same-transaction lock --
# `enforced` regardless of `process_ceiling`).
```

## CH-0244

- moved from: `src/r2db_api/control_plane.py` (`<module>`)
- parent commit: `6e91983`
- kind: comment

```
# Phase 4 WP-2(b) (design D-5): a SEPARATE probe against the
# APPLICATION-credential universe (`credentials`, never `control_
# credentials`) -- `audit_query`'s own authority check needs to
# recognize "this secret genuinely belongs to a real, active
# application credential" BEFORE ever presenting it to `authenticate`
# above, so it can answer an identified, attributed `FORBIDDEN` rather
# than let it fall through as an ordinary, unattributed `AUTH_INVALID`
# against the control-credential store it was never issued against
# (contract `control_endpoints.audit_query.semantics`: "Application
# credentials are denied"). Returns `None` for every failure mode
# (missing/unknown/revoked/disabled secret) -- never raises -- so the
# caller can use it as a pure probe without a `try/except` at every
# call site.
```

## CH-0245

- moved from: `src/r2db_api/control_plane.py` (`<module>`)
- parent commit: `6e91983`
- kind: comment

```
# -- issuance freeze (Phase 3.5 WP-4, §4/§1-E, P35-D6) --
```

## CH-0246

- moved from: `src/r2db_api/control_plane.py` (`<module>`)
- parent commit: `6e91983`
- kind: docstring

```
`ControlBackend`'s in-memory implementation. Wraps a `ControlAuthority`
(whose `DataService`/`CredentialStore` must themselves be the in-memory
implementations -- this backend never checks that, matching how
`ControlAuthority` itself is backend-agnostic; a caller that hands this
class a Postgres-backed `ControlAuthority` gets undefined behaviour, not
a defended error) plus a standalone in-memory `ControlCredentialStore`
(control credentials have no relationship to `ControlAuthority` at all --
design R-2: a control credential belongs to no Application, and
`ControlAuthority`'s pre-existing surface has no concept of one).

There is no separate in-memory "applications registry" store class: this
backend reads/restores `ControlAuthority`'s own `DataService`'s `_cells`/
`_disabled_apps` directly (design §0: "in-memory側はControlAuthority/
DataServiceの既存状態に整合する形--backend内で表現してよい"). Every
*mutation* still goes through `ControlAuthority.register_application`/
`.set_application_enabled` -- never a direct dict write -- so `Control
Authority`'s own pre-existing in-memory audit trail observes every
control-plane application change too (this is what the WP-3 work
order's test item 9, "ControlAuthority委譲", checks for).
```

## CH-0247

- moved from: `src/r2db_api/control_plane.py` (`<module>`)
- parent commit: `6e91983`
- kind: comment

```
# `ControlAuthority` has no public accessor for the `CredentialStore`
# it holds (by design -- it is the trusted lifecycle authority, not
# a data-access facade); reaching `._service._credentials` directly
# mirrors `ControlAuthority._control_event`'s own established
# precedent of reading `self._service`'s private state from inside
# this package (service.py is not modified to add a new public
# accessor here -- the WP-3 work order scopes service.py's only
# change to the `work=` keyword argument addition).
```

## CH-0248

- moved from: `src/r2db_api/control_plane.py` (`InMemoryControlBackend.control_credentials_locked`)
- parent commit: `6e91983`
- kind: comment

```
# Phase 3.5 WP-4 (round-2 independent review n-2): `_frozen_
# applications` (§4/§1-E) is this block's own state too --
# `set_application_issuance_frozen` is a state-changing method
# reachable through this same `work` handle, so it needs the same
# snapshot/rollback coverage as `_cells`/`_disabled_apps` above, or a
# fault injected after a freeze/unfreeze call inside this block would
# leave the frozen-set change applied despite the block rolling back
# everything else.
```

## CH-0249

- moved from: `src/r2db_api/control_plane.py` (`<module>`)
- parent commit: `6e91983`
- kind: docstring

```
Round-2 review MI-1: `issue_credential`/`set_credential_state`
(`ControlPlaneService` -> `ControlAuthority`, below) also write to
`ControlAuthority`'s own secondary in-memory audit trail -- same
rollback-consistency concern as `applications_unit_of_work` above,
same fix. `self._credentials.unit_of_work()` (WP-2, `auth.
CredentialStore`) already owns snapshot/restore of `_records` itself
on any exception; this wraps that with the *additional* secondary-
trail truncation, rather than duplicating the store's own rollback
logic here.
```

## CH-0250

- moved from: `src/r2db_api/control_plane.py` (`<module>`)
- parent commit: `6e91983`
- kind: comment

```
# ---- issuance freeze (Phase 3.5 WP-4) -------------------------------
```

## CH-0251

- moved from: `src/r2db_api/control_plane.py` (`ControlPlaneService`)
- parent commit: `6e91983`
- kind: docstring

```
`ControlBackend`'s Postgres implementation -- talks to the WP-2 store
trio directly, no `DataService`/`ControlAuthority` involved at all (a
real deployment of this surface is a separate process, R-1/R-3, which
never constructs an application-plane `DataService`).
```

## CH-0252

- moved from: `src/r2db_api/control_plane.py` (`<module>`)
- parent commit: `6e91983`
- kind: comment

```
# ---- issuance freeze (Phase 3.5 WP-4) -------------------------------
```

## CH-0253

- moved from: `src/r2db_api/control_plane.py` (`<module>`)
- parent commit: `6e91983`
- kind: docstring

```
CCR-14 control-plane facade (WP-3). Constructed with a `ControlBackend`
(either implementation above), a durable audit sink (`ControlAuditSink`/
`PostgresControlAuditSink`), an optional `ControlPlaneLimits` profile
(defaults to the contract's own `example_profile` values), and an
optional monotonic clock callable (rate-limiter testability, mirroring
`DataService`'s own `clock` parameter).

See this module's header for the architecture this class embodies: every
processing-order/authorization/limit/audit/deterrence judgment lives
here; backends are dumb storage plumbing.

CCR-14 WP-4 round-2 (independent review MAJOR-1): every one of the 9
public operation methods below accepts a keyword-only `rate_precharged:
bool = False`. `False` (the default -- what every direct in-process
caller, including the WP-5 in-process conformance adapter, keeps using)
means the method charges the R-7 rate window itself, exactly as before
this fix. `True` means the caller already charged it via `check_rate()`
(see that method's own docstring) and this call must not charge it
again -- `control_http.py` is the one caller that does this, because it
has to charge the window before it can even read a request body.
```

## CH-0254

- moved from: `src/r2db_api/control_plane.py` (`<module>`)
- parent commit: `6e91983`
- kind: comment

```
# Phase 6 WP-2 (design D-2): same constructor-injected, echo-only
# discipline as `DataService.__init__`'s own `surfaces` parameter --
# see that class's comment. `control_main.py` (the real composition
# root) assembles this from the same two `R2DB_*_BASE_URL`
# environment variables `main.py` reads.
```

## CH-0255

- moved from: `src/r2db_api/control_plane.py` (`<module>`)
- parent commit: `6e91983`
- kind: comment

```
# Phase 10 WP-6a (design D-5(ii), contract 1.8.0): this plane's own
# declared process ceiling -- see `DataService.__init__`'s
# identical parameter/validation for the full rationale.
# `control_main.py` resolves this from `declarations.
# process_ceilings.control` (never `.data`, the data-plane's own).
# Default `1` preserves every pre-Phase-10 caller's behavior
# unchanged (this repository's own tests, the in-process
# conformance adapter).
```

## CH-0256

- moved from: `src/r2db_api/control_plane.py` (`<module>`)
- parent commit: `6e91983`
- kind: comment

```
# Phase 4 WP-2(b) (design D-5/D-6): `audit_query`'s own state.
# `audit_reader is None` is this instance's true, complete posture
# for "AUDIT DSN not configured" (D-5 M-4) -- `capabilities()`
# below declares `audit_query: {"status": "unavailable"}` exactly
# when this holds, and `audit_query()` refuses with `CAPABILITY_
# UNSUPPORTED` (never a bare 404/`AttributeError`) on that same
# condition. A SEPARATE pre-auth rate window from `_rate_window`
# above (`_audit_rate_window`) -- `audit_query`'s own window must
# never share a counter with `control_requests_per_minute`
# (design M-8 / P4-D4 item 8): a high-frequency audit poller must
# never be able to exhaust the window a break-glass `revoke_
# credential` depends on.
```

## CH-0257

- moved from: `src/r2db_api/control_plane.py` (`<module>`)
- parent commit: `6e91983`
- kind: comment

```
# Phase 10 WP-6a (design D-5(ii), contract 1.8.0): region (ii)
# (`control_requests_per_minute`/`audit_requests_per_minute` --
# bound by in-memory, per-process state, `self._rate_window`/
# `self._audit_rate_window`) reads `enforced` only while `self.
# _process_ceiling == 1`, `deployment_required` once `>= 2`.
# Region (iii) (`applications`/`credentials_per_application` --
# bound in PostgreSQL, under a same-transaction, table-scoped
# constant-key `pg_advisory_xact_lock`, `register_application`/
# `issue_credential` below) stays `enforced` regardless of
# `process_ceiling` -- the lock makes the bound hold across every
# process. `request_bytes`
# (region (i), request-scoped) is untouched here, overridden to
# `"unavailable"` below exactly as before this WP.
```

## CH-0258

- moved from: `src/r2db_api/control_plane.py` (`<module>`)
- parent commit: `6e91983`
- kind: comment

```
# Phase 3.5 WP-4 (§4 "L4", MitateDB-parity two-layer form, review
# M-3): this service alone cannot enforce a byte bound -- there is no
# HTTP boundary at this layer -- so the service-layer default is
# `"unavailable"`; `control_http.py`'s own handler overrides this one
# key to `"enforced"` once the real `RequestByteBoundMiddleware` is
# actually mounted in front of it (same single-source instance, see
# the `limits` property above).
```

## CH-0259

- moved from: `src/r2db_api/control_plane.py` (`<module>`)
- parent commit: `6e91983`
- kind: comment

```
# Phase 4 WP-2(b) (design D-5, contract 1.4.0 subordinate ruling 9):
# `audit_requests_per_minute` is a pre-auth fixed window that always
# exists once this process is running (the route is always
# registered, D-5 M-4) -- "enforced" regardless of whether
# `audit_query` itself is `enabled`, exactly like every other
# `ControlPlaneLimits` field the generic comprehension above already
# marks "enforced".
```

## CH-0260

- moved from: `src/r2db_api/control_plane.py` (`<module>`)
- parent commit: `6e91983`
- kind: comment

```
# Phase 4 WP-2(b) (P4-D4, contract 1.4.0 `versioning.
# version_binding`), flipped to 1.5.0 in phase 5 WP-3, flipped
# to 1.6.0 in phase 6 WP-2 (design docs/design/
# PHASE6_CONTRACT_160_CLIENT_DISCOVERY_V1.md, subordinate
# ruling 11): the flip lands in the SAME commit as the real
# `audit_query`/locator-credential/`surfaces` behavior --
# unconditional (every instance of this service declares 1.6.0
# now, whether or not `audit_query` itself is `enabled` on this
# deployment; the 1.4.0 obligations that are conditional on
# `audit_query` being provided stay conditional per version_
# binding's own text).
#
# Flipped to 1.7.0 in phase 9 WP-2e (design docs/design/
# PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md D-1
# (5)): the SAME commit as `service.py`'s own data-plane flip
# (C-19's control-plane/data-plane match assert) -- never ahead
# of the R-3/R-7 behavior this data-plane host now implements.
#
# Flipped again to 1.8.0 in phase 10 WP-6a/pair-closing (design
# D-5 (v)): the SAME commit as `service.py`'s own data-plane
# flip and this host's own `process_ceilings` mapping (D-5
# (ii)) -- never ahead of the behavior it declares.
```

## CH-0261

- moved from: `src/r2db_api/control_plane.py` (`<module>`)
- parent commit: `6e91983`
- kind: comment

```
# Phase 6 WP-2 (design D-2): optional key, present only when this
# instance was constructed with one (`__init__`'s own comment on
# `self._surfaces`). A live control-plane process' own control
# surface is, by definition, provided (this method answering at all
# means so) -- the composition root only ever constructs this class
# with both `surfaces.data`/`surfaces.control` present together.
```

## CH-0262

- moved from: `src/r2db_api/control_plane.py` (`<module>`)
- parent commit: `6e91983`
- kind: docstring

```
Phase 4 WP-2(b) (design D-5's own JSON shape). `status`'s
vocabulary is the contract's own `capability_status.status_enum` (4
values) -- never the word `"available"`, which is not a member.
AUDIT DSN unconfigured (`self._audit_reader is None`) keeps the
declaration at exactly `{"status": "unavailable"}` (D-5 M-4) --
every other key below is published only once there is a real
reader to back it, so a client never reads a `visibility_lag_ms`/
`event_classes` for a capability that cannot actually answer a
request.
```

## CH-0263

- moved from: `src/r2db_api/control_plane.py` (`ControlPlaneService.rotate_credential`)
- parent commit: `6e91983`
- kind: comment

```
# WP-2(b) review B-1 (supervisor ruling): the durable `count`
# column's real semantics, matching contract `audit.
# query_event_fields_note` verbatim ("present only on an event
# representing more than one coalesced occurrence, absent --
# never zero or one -- otherwise"). A denial-coalescing window
# or a buffer-overflow drop that ends up representing exactly
# one occurrence is written as an ordinary row with count
# absent, not count=1 -- a consumer must never read "count is
# present" as "this row alone represents 2+ occurrences" being
# the ONLY way to represent 2+; it is, but the converse
# (absent implies exactly 1) is what this note pins down.
```

## CH-0264

- moved from: `src/r2db_api/control_plane.py` (`<module>`)
- parent commit: `6e91983`
- kind: comment

```
# Phase 10 WP-6a (design D-5(ii) addendum (2)): the limit check
# now runs INSIDE this same transaction, via `applications_
# count_locked` -- for `PostgresControlBackend` that takes a
# table-scoped constant-key `pg_advisory_xact_lock` first
# (`credential_store._take_bound_advisory_lock`), which blocks
# a concurrent registration's own `count_locked` (same key)
# until THIS transaction commits or rolls back. Before this
# WP, the count above ran on its own, already-
# committed connection, entirely outside this transaction --
# two concurrent `register_application` calls could each
# observe a count one under the limit and both proceed,
# overshooting it (the TOCTOU window design D-5(ii) requires
# closed, not weakened).
```

## CH-0265

- moved from: `src/r2db_api/control_plane.py` (`<module>`)
- parent commit: `6e91983`
- kind: comment

```
# Nit (round-2 review): `enabled`'s own bool-ness must be checked
# *before* it is used to pick an `operation` name at all -- unlike
# every other operation's shape validation (which the canonical (3)
# gate -> (4) validate order defers past the gate on purpose), this
# one specific field is an input to the gate call itself (which
# `operation` name to check), so there is no way to gate first
# without first deciding what a non-bool `enabled` even means for
# audit/gate purposes. Both `enable_application`/`disable_
# application` are refused identically under must_rotate regardless,
# so this ordering has no observable effect on gate outcomes -- it
# only avoids deriving an operation name from a value that was never
# validated as meaningful in the first place.
```

## CH-0266

- moved from: `src/r2db_api/control_plane.py` (`<module>`)
- parent commit: `6e91983`
- kind: comment

```
# O-1 (`{scratchpad}/rulings-r3-r7-flip.md` 追補4): contract
# 1.7.0's `errors.details_vocabulary` unconditional obligation
# (a) covers "every denial", not only the data-plane query/
# mutate/schema surface -- this control-plane request field
# gets the same 4-key `violation(...)` shape a data-plane
# `bind_mutation`'s own `destructive` boolean-shape check
# (structured.py) already carries.
```

## CH-0267

- moved from: `src/r2db_api/control_plane.py` (`<module>`)
- parent commit: `6e91983`
- kind: comment

```
# Phase 6 WP-2 (design D-1(c), item 1): the STORE receives the
# raw, freshly-generated `secret_value` (its own verifier is
# computed from exactly that value) -- only the RESPONSE's
# `secret` is the composed bearer (`compose_bearer_locator`).
# `credential_id` stays a separate response field, unchanged.
```

## CH-0268

- moved from: `src/r2db_api/control_plane.py` (`<module>`)
- parent commit: `6e91983`
- kind: comment

```
# No `application_id` key at all (design §2: "control行はapplication_id無し",
# unchanged for `role="audit"` rows too -- neither kind belongs
# to an Application). Phase 3.5 WP-4 (§4/§1-B, P35-D7 reversal of
# the original §8 m-9 omission): `must_rotate` is now exposed
# here with its real value for every control-table row (control
# OR audit) -- the store has the value and contract 1.3.0 makes
# the field optional-additive, so there is no longer a reason to
# withhold it (m-4: this does widen who can observe a not-yet-
# rotated credential's existence -- an `audit`-role principal can
# now read this same listing -- but no secret/verifier is ever
# included, and this is documented, intended operational
# visibility, not a leak; see CONTROL_MAPPING.md SI-10/SI-02).
# `role` reads the real column (design §4 review m-6) instead of
# a hardcoded `"control"` literal.
```

## CH-0269

- moved from: `src/r2db_api/control_plane.py` (`<module>`)
- parent commit: `6e91983`
- kind: comment

```
# O-8 (版フリップ監査, ruling `{scratchpad}/rulings-r3-r7-flip.md`
# 追補4): "対象の状態が操作と矛盾する" refusal (a revoked
# credential cannot be rotated) is a resource-STATE conflict,
# not a request-shape/identifier-syntax/deployment-capability
# question the 11-word `violated_declaration_vocabulary` was
# built to describe -- CONFLICT (status 409), the code this
# module already uses for every other "target state
# contradicts the requested operation" refusal (already-
# revoked/already-exists/concurrently-modified above), not a
# forced fit into VALIDATION_FAILED's own vocabulary. `details`
# is optional for CONFLICT (O-8); `field: credential_id` is
# kept here since one IS attributable.
```

## CH-0270

- moved from: `src/r2db_api/control_plane.py` (`<module>`)
- parent commit: `6e91983`
- kind: comment

```
# Phase 6 WP-2 (design D-1(c), item 1): same raw-to-store/composed-
# in-response split as `issue_credential` above, for both the
# application and control branches below.
```

## CH-0271

- moved from: `src/r2db_api/control_plane.py` (`<module>`)
- parent commit: `6e91983`
- kind: docstring

```
Contract 1.2.0 `destructive_confirmation` (design docs/design/
DESTRUCTIVE_CONFIRMATION_V1.md R-3): revoking an application
credential, or a control credential that is not the last remaining
active one, is never gated -- `destructive`/`confirmation` are not
even inspected on those paths (contract `non_destructive_requests`),
exactly as before this WP. Revoking the LAST remaining active
(enabled and not revoked) control credential requires a valid
confirmation; the judgment "is this the last active one" is made
inside the SAME `control_credentials_unit_of_work` transaction as
the state change itself, under a lock (`control_credentials_
locked`), so two concurrent revoke attempts against two different
credentials can never both observe "not last" and both proceed
unconfirmed (WP-0 MA-2's TOCTOU concern). Processing order:
authenticate -> must_rotate gate -> [confirmation gate, control
credentials only] -> execute (design R-3's own ordering).
```

## CH-0272

- moved from: `src/r2db_api/control_plane.py` (`<module>`)
- parent commit: `6e91983`
- kind: comment

```
# Review blocker B-1: shape validation of the request's own
# `destructive`/`confirmation` fields (contract `CredentialRevoke
# Request.destructive: {"type": "boolean"}` / `.confirmation:
# {"type": "string", ...}`) -- applied unconditionally, regardless
# of whether this particular revoke ever meets the gate condition
# below. This is the same "request schema enforce" `bind_mutation`
# already applies to every data-plane mutation's own `destructive`
# field (structured.py); it is not part of the destructive-
# confirmation *semantics* the contract's own `non_destructive_
# requests` clause says a non-gated revoke never inspects -- a
# non-boolean truthy `destructive` (e.g. the string `"false"`,
# which a loose `bool(...)` cast would silently coerce to `True`)
# must be rejected as a shape defect before that semantic question
# is even reached, exactly per contract `evaluation_order` (shape
# validation precedes confirmation evaluation).
```

## CH-0273

- moved from: `src/r2db_api/control_plane.py` (`<module>`)
- parent commit: `6e91983`
- kind: docstring

```
Phase 4 WP-2(b) (design D-5/D-6). Processing order: `audit_
requests_per_minute` (its OWN window, never `control_requests_
per_minute`) -> application-credential probe (identified FORBIDDEN,
BEFORE the control-credential store ever sees this secret -- see
`_deny_application_credential_on_audit_query`'s own docstring for
why the ordering matters) -> ordinary control/audit authentication
-> role authorization (`_AUDIT_ROLE_ALLOWED_OPERATIONS` now
includes `audit_query`) -> must_rotate gate -> `CAPABILITY_
UNSUPPORTED` when no reader is configured (D-5 M-4: the route
answers this AFTER authenticating, never a bare 404) -> request
shape/semantic validation -> the real read.
```

## CH-0274

- moved from: `src/r2db_api/control_plane.py` (`<module>`)
- parent commit: `6e91983`
- kind: docstring

```
Turns one reader row (`AuditQueryReader.query`'s own dict shape
-- 13 contract `audit.fields` + `count` + `recorded_at` + `plane`)
into one `AuditResult.events[]` element: adds the opaque `cursor`
(D-6), formats `recorded_at` as ISO-8601, and omits every optional
field that is `None` (mirrors `audit.AuditEvent.as_dict()`'s own
None-filtering convention -- `events[]` is contract-open, but a
`null`-valued key is still needless noise no existing reader emits
elsewhere in this codebase).
```

## CH-0275

- moved from: `src/r2db_api/control_plane.py` (`reset_control_credentials`)
- parent commit: `6e91983`
- kind: comment

```
# Round-2 review MI-6 (supervisor ruling): `role` always names the
# ACTOR's role, never the target's -- every control-plane operation
# is performed by a control credential (`role="control"` -- and,
# since Phase 3.5 WP-4, possibly `role="audit"` for a read-only
# operation, though every *state-changing* call site this method
# actually serves is itself unreachable for an audit principal, see
# `_authorize_role` below; `actor.role` is still read here rather
# than re-hardcoding `"control"`, for correctness independent of
# that other gate ever changing). Earlier code passed the *issued*
# credential's role (`runtime`/`developer`) through here for
# `issue_credential`'s own audit row, conflating actor and target --
# fixed by dropping the caller-supplied override entirely; there is
# no longer a `role` parameter to misuse.
#
# Phase 3.5 WP-4 (§1-C/§4): `target_id` -- the single target
# credential_id/application_id this state change acted on, when the
# caller supplied one (every real call site above does).
```

## CH-0276

- moved from: `src/r2db_api/control_plane.py` (`<module>`)
- parent commit: `6e91983`
- kind: comment

```
# Round-2 review MA-2: the store identifies a real credential
# before refusing it for AUTH_REVOKED and for a matching-but-
# disabled AUTH_INVALID (`auth._fail_identified` -- see its
# docstring); an AUTH_INVALID/AUTH_REQUIRED with no match at
# all carries no such attribute. `getattr(..., None)` treats
# both "attribute absent" and "attribute None" as unattributed
# -- `_deny` picks the truthful declaration form either way.
```

## CH-0277

- moved from: `src/r2db_api/control_plane.py` (`<module>`)
- parent commit: `6e91983`
- kind: comment

```
# Phase 3.5 WP-4 (design §4 review m-6): the identified
# credential's REAL role (`auth._fail_identified`'s own new
# `identified_role` attribute), never a hardcoded `"control"`
# -- an audit credential that is revoked/disabled must be
# attributed as `role="audit"` in its own denial row, not
# misreported as a control credential.
```

## CH-0278

- moved from: `src/r2db_api/control_plane.py` (`<module>`)
- parent commit: `6e91983`
- kind: docstring

```
R-5/§7: allow-list gate -- only `control_capabilities` and a
self-targeted `rotate_credential` (`role="control"` only) pass while
`must_rotate` is true; every other operation is `FORBIDDEN`.
Deliberately an allow-list, not a deny-list (design's own explicit
warning: a deny-list silently fails open the moment a new operation
is added and nobody remembers to list it).

Phase 3.5 WP-4 (design §4 M-1): a `role="audit"` principal's own
allow-list while `must_rotate` is true is `control_capabilities`
ONLY -- self-rotate is deliberately NOT extended to it. This is not
a dead end: the out-of-band audit-credential issuance ceremony
(`issue_audit_credential_ceremony` below) issues AND rotates the
credential in the same transaction before ever printing a secret, so
a distributed audit credential's `must_rotate` is already `false` by
the time anyone can authenticate with it -- an in-band audit
principal is never actually stuck behind this gate in practice.
```

## CH-0279

- moved from: `src/r2db_api/control_plane.py` (`<module>`)
- parent commit: `6e91983`
- kind: docstring

```
R-6/R-11: writes one durable denial event in its own, independent
transaction, then raises the original denial with an R-11
declaration attached. "No state change to share one with" (design
§4) describes the ordinary call sites (`_authenticate`/`_gate_must_
rotate`/`_deny_role_control`), which run before any state-changing
`unit_of_work` is even opened. The last-active-control-credential
revoke gate (design R-3, WP-3) calls `_deny` from a different
position -- from INSIDE an already-open `control_credentials_unit_
of_work` transaction (`revoke_credential`'s own `_body`) -- but the
"independent transaction" property still holds in practice: `self.
_audit` (`ControlAuditSink`/`PostgresControlAuditSink`) is backed by
its own, separate connection/pool from the one `control_credentials_
unit_of_work` holds open (see `PostgresControlAuditSink.__init__`'s
own dedicated `_RolePool`), so the audit row this call writes
commits independently of, and is never rolled back by, the
enclosing `_body`'s own transaction aborting after `_deny` raises
(which it always does -- `_deny` never returns normally). Durably
recorded audit evidence for a denial made from inside an open
transaction survives that transaction's own rollback for the same
reason two ordinary, unrelated database connections' commits are
independent of each other.

If the durable write itself fails, the *whole response* becomes
`SERVICE_UNAVAILABLE` (503) instead -- the original denial code/
message/declaration are discarded, not merely supplemented, which
is what keeps "audited: true" truthful by construction (a response
can never claim durable attribution for an event that was not, in
fact, durably recorded).

Round-2 review MA-2: the declaration text itself must be truthful
about *attribution*, not just about durability -- the attributed
form ("...attributed to the credential that made it...") is only
used when `actor_id` identifies a real credential (the audit row
this call is about to write actually names one); every other denial
gets the plain "recorded" form, which claims durability but no
attribution. Both forms are still `details["attribution"]` -- the
key name is unchanged, only its value differs by case.
```

## CH-0280

- moved from: `src/r2db_api/control_plane.py` (`<module>`)
- parent commit: `6e91983`
- kind: docstring

```
CCR-14 WP-4 round-2 (independent review MAJOR-1): public wrapper
around `_check_rate` below, charging exactly one token against the
R-7 `control_requests_per_minute` window (or raising `LIMIT_EXCEEDED`/
429, same as every internal call site).

Exists so an HTTP binding layer (`control_http.py`) can charge the
window *before* it does anything else -- including reading/parsing a
request body -- for the 3 endpoints whose request schema is read off
the body before the corresponding service method is called at all
(design §12.5: those methods take already-extracted arguments, so
the HTTP layer must shape-check the body first; see `control_http.
py`'s own module docstring for why that ordering is otherwise
correct). Without a way to charge the window ahead of that shape
check, a malformed/unauthenticated body flood against `register_
application`/`issue_credential`/`revoke_credential` never touched
`_check_rate` at all -- an unbounded, unauthenticated path under a
`limit_enforcement: "enforced"` capability declaration (round-2
review MAJOR-1, measured).

A caller that calls `check_rate()` itself and then calls one of the
9 operation methods below **must** pass `rate_precharged=True` to
that call -- otherwise the window is charged twice for one logical
request. Every operation method's own default (`rate_precharged=
False`) keeps every *other* caller (this repository's own tests,
the in-process conformance adapter WP-5 will wire up) fully charged
exactly as before this fix: the in-process path calls a method
directly, once, with no separate `check_rate()` call, so the
internal `_check_rate()` below still runs and still charges one
token per call, unchanged.
```

## CH-0281

- moved from: `src/r2db_api/control_plane.py` (`<module>`)
- parent commit: `6e91983`
- kind: docstring

```
R-7 `control_requests_per_minute` -- a single, global window
(never keyed per-credential/actor, unlike the data plane's
`DataService._acquire_rate`): this check runs *before*
authentication (design §4/R-6's own "監査増幅の防止" -- an
unauthenticated caller must not be able to generate unbounded durable
audit rows), so there is no `credential_id` to key on yet even in
principle. Rate-limit refusals are deliberately never durably
audited at all (design §4: "拒否には状態変更が無い...rate limit超過
は監査しない(認証前・実行者不明。監査増幅DoSの防止)") -- this is the
one denial category with no R-11 `audited: true` declaration.

Round-2 review MI-7 (supervisor ruling): this is a *sliding* window
(every call re-filters to "within the last 60s of `self._clock()`"),
not the fixed/bucketed window design §1 R-7 says merely "suffices"
(固定窓で足りる) -- a fixed window is a permissive floor, not a
ceiling, and the sliding form is strictly stricter (no boundary
double-burst at a bucket edge) while staying bounded (this list can
never hold more than `control_requests_per_minute` entries, by the
`fail()` below). Kept deliberately rather than downgraded to match
the design's minimum; noted here so a future reader does not "fix"
this back down to a fixed window under the mistaken impression the
design requires it.
```

## CH-0282

- moved from: `src/r2db_api/control_plane.py` (`<module>`)
- parent commit: `6e91983`
- kind: docstring

```
Phase 4 WP-2(b) (design D-5, `check_rate`'s own public-wrapper
precedent above): lets `control_http.py` charge `audit_query`'s own
window before it even reads a request body, for the SAME
`rate_precharged=True` reason `check_rate` documents. A caller that
calls this itself and then `audit_query(..., rate_precharged=True)`
must not also call `check_rate()` for the same request -- `audit_
query` never touches `control_requests_per_minute` at all, by
design (M-8 / P4-D4 item 8).
```

## CH-0283

- moved from: `src/r2db_api/control_plane.py` (`<module>`)
- parent commit: `6e91983`
- kind: docstring

```
`audit_requests_per_minute` -- a SEPARATE global window from
`_check_rate`'s `control_requests_per_minute` above (own lock, own
list, own limit field), reusing the identical sliding-window
mechanism (never a new one -- work order §6 item 5: "制約・制限の
追加で問題を回避しない...新機構を発明しない"). Pre-auth, exactly
like `_check_rate` (this window governs BOTH `/control/v1/audit/
query` and its `/v1/audit/query` alias, before either path even
extracts a bearer token) -- and, identically, never durably
audited (rate-limit refusals carry no attributable actor yet; the
same "監査増幅の防止" reasoning `_check_rate` documents applies
unchanged to this second window).
```

## CH-0284

- moved from: `src/r2db_api/control_plane.py` (`<module>`)
- parent commit: `6e91983`
- kind: comment

```
# ===========================================================================
# Ceremony core (CCR-14 WP-5, design §5 WP-5 row / §2 item 2 of the work
# order): the bootstrap/reset ritual's actual decision logic (existence
# check, atomic revoke-all+add, same-transaction canonical audit), extracted
# out of `ops.py` into real, reusable product code. Two callers share this
# exact code, never two independent reimplementations of "what does
# bootstrap/reset mean": `ops.py cmd_bootstrap`/`cmd_reset` (Postgres store,
# wrapped in `_lock_ritual`'s advisory lock -- the Postgres-only
# serialization guard the work order requires) and the WP-5 in-process
# conformance adapter (in-memory store, no lock -- a single adapter instance
# has no concurrent daemons to serialize against, design §5 item 2: "advisory
# lock は Postgres 経路のみ").
#
# `control_credentials`/`audit` are duck-typed against the exact call
# surfaces `ControlCredentialStore`/`PostgresControlCredentialStore`
# (`has_any`/`add`/`revoke_all`) and `ControlAuditSink`/
# `PostgresControlAuditSink` (`append(..., work=...)`) already share --
# these two functions work unmodified against either backend pairing, same
# as `ControlBackend`/`ControlPlaneService` above never branch on which
# concrete store they were given.
# ===========================================================================
```

## CH-0285

- moved from: `src/r2db_api/control_plane.py` (`<module>`)
- parent commit: `6e91983`
- kind: docstring

```
R-5 bootstrap ceremony core. Refuses (`CONFLICT`) when *any*
control-credential row exists, including a fully-revoked one (§8 M-6:
the contract's own text is "while a control credential exists", not
"while an unrevoked one exists"). Issues one credential and writes the
canonical `bootstrap_control_credential` audit event inside the same
`work` transaction the caller already opened -- a fault in `audit.
append` therefore aborts the issuance too (fail-closed by construction,
R-6's "同一トランザクション" guarantee), through the caller's own
enclosing `unit_of_work()` rollback, not through any handling here.

Returns `(credential_id, secret)`. `credential_id`/`secret` may be
supplied by the caller (parity/replay tests) -- when supplied, `secret`
is the RAW value the store is asked to record (matching this function's
pre-WP-2 contract for those callers); by default both are freshly
generated. Phase 6 WP-2 (design D-1(c), r2db decision (c): "control
credential = bootstrap / reset / rotate" among this repository's own
issuance points that must return a composed bearer): the STORE always
receives the raw secret (its own verifier is computed from exactly that
value); the RETURNED `secret` is the composed bearer
(`compose_bearer_locator`) -- this is this ceremony's own issuance
point, so composition happens here, once, rather than at each of this
function's two callers (`ops.py cmd_bootstrap`'s `_print_issued`, and
the in-process conformance adapter's `bootstrap()`).
```

## CH-0286

- moved from: `src/r2db_api/control_plane.py` (`<module>`)
- parent commit: `6e91983`
- kind: comment

```
# Phase 6 WP-2 (design D-1(c)): same raw-to-store/composed-in-response
# split as `bootstrap_control_credential` above.
```

## CH-0287

- moved from: `src/r2db_api/control_plane.py` (`<module>`)
- parent commit: `6e91983`
- kind: docstring

```
Phase 3.5 WP-4 out-of-band audit-credential issuance ceremony (design
PHASE35_CROSS_ENTITY_AND_CONTRACT_130_V1.md §4/§1-D, P35-D12/M-1). Same
extraction rationale as `bootstrap_control_credential`/`reset_control_
credentials` above (reusable product code, not hand-rolled per caller --
`ops.py cmd_issue_audit_credential` is this WP's own only caller today).

Unlike bootstrap/reset, this ceremony issues AND rotates the credential
in the SAME transaction, before a secret is ever handed back to the
caller: an `audit`-role principal has no in-band self-rotate path at all
(`ControlPlaneService._gate_must_rotate`'s own allow-list for `role=
"audit"` while `must_rotate` is true is `control_capabilities` ONLY --
design's own explicit decision not to extend self-rotate to it, since
the whole point of completing the rotation here is that no in-band path
should ever need to). Issuing with `must_rotate=true` and leaving it to
the operator to somehow clear it out-of-band-again would be a dead end;
this ceremony closes that gap structurally by never printing a secret
whose `must_rotate` is still true. The intermediate `add()`-time secret
is generated, used once to satisfy `add`'s own required `secret`
parameter, and immediately discarded -- only the final, post-`rotate()`
secret is ever returned (and therefore ever printed by `ops.py`).

Returns `(credential_id, secret)` -- `secret` is the one that actually
authenticates (post-rotation); `must_rotate` is `false` for it already.
Phase 6 WP-2 (design D-1(c)): `secret` is the composed bearer
(`compose_bearer_locator`) -- the store itself still receives/rotates
on the raw `distributed_secret`.
```
