# r2db-api/service.py -- code-comment history (change set 2)

Companion for `r2db-api/src/r2db_api/service.py` per `docs/code-history/README.md`.

## CH-0103

- moved from: `src/r2db_api/service.py` (`ControlAuthority.issue_credential`)
- parent commit: `3a4c018`
- kind: docstring

```
`work` is keyword-only, defaulting to `None` -- see `set_credential_
state`'s docstring immediately above for the full CCR-14 WP-3
rationale; identical reasoning applies here.

Rework (coordinator item 3, 2026-09-04 review): returns the
composed bearer `self._service._credentials.add(...)` itself now
returns (design D-1(c) "合成は store/service 層のみ" principle) --
this out-of-band lifecycle-authority entry point is an issuance
point (the conformance in-process plug's own privileged-setup
`issue_credential` calls this directly, `ops.py` does not use this
method at all -- see that module's own `cmd_issue_credential`,
which calls the store's `add` directly and gets the same composed
return value there). Every pre-WP-2 caller that ignored the
previous `None` return is unaffected (Python permits discarding a
return value freely) -- `test_control_authority_work_parameter_
defaults_preserve_existing_callers` pins this explicitly.
```

## CH-0104

- moved from: `src/r2db_api/service.py` (`ControlAuthority.set_credential_state`)
- parent commit: `3a4c018`
- kind: comment

```
# R-6/§8 B-2: chase `CredentialStore`/`PostgresCredentialStore`'s
# new `unit_of_work()`-required call form -- semantics are
# unchanged (this still commits/reverts exactly one call's
# worth of state, same as before WP-2; `ControlAuthority`'s own
# audit trail stays on the existing in-memory `AuditSink` below,
# not on the new `control_audit` table, which only `ops.py`'s
# ritual/CLI-path writes to in this work package).
```

## CH-0105

- moved from: `src/r2db_api/service.py` (`ControlAuthority.set_credential_state`)
- parent commit: `3a4c018`
- kind: docstring

```
`work` is keyword-only and defaults to `None` (CCR-14 WP-3): when
omitted, this method self-manages exactly as before -- opens its own
`unit_of_work()`, commits/reverts exactly one call's worth of state,
and every pre-WP-3 caller (this repository's own tests, the
in-process conformance adapter) keeps working unchanged. When a
caller supplies its own already-open `work` handle (`ControlPlane
Service`'s in-memory backend, WP-3: it needs the credential-state
change and its own `control_audit` sink append to land in the *same*
transaction, R-6), this method uses that handle directly instead of
opening a second one -- never both. `work`'s type is deliberately
untyped (`Any`) rather than importing `auth._InMemoryWork`/
`credential_store._PostgresWork` here: this module stays agnostic to
which store implementation (in-memory or PostgreSQL) it is holding,
exactly as it already is everywhere else (`self._service._credentials`
is never type-narrowed in this class).
```

## CH-0106

- moved from: `src/r2db_api/service.py` (`DataService.flush_audit_buffer`)
- parent commit: `3a4c018`
- kind: docstring

```
Phase 4 (design D-4/§7.3/§7.4): synchronously drains the
bounded buffer (writing it as one batch), retries the sticky
overflow-alert row if one is pending and due, and sweeps
denial-coalescing windows (writing their repeat-count summary row,
D-3). Called on demand by this repository's own tests and by a
composition root's periodic timer alike -- there is nothing
time-sensitive about calling this more or less often beyond how
promptly buffered/coalesced evidence becomes durable (D-4's own
"periodic or threshold" flush-trigger latitude).

`force_expire_denial_windows=True` (WP-2(a) fix round 2, review
N-4): flushes EVERY currently-open denial-coalescing window,
expired or not, instead of only expired ones -- used exactly once,
by a composition root's graceful-shutdown path. Without this, a
window still short of its own `window_s` at the moment the process
stops loses its accumulated repeat count entirely (D-3 only
sanctions losing counts to an actual crash, not to an orderly
stop); the default (periodic timer, explicit test calls) stays
`False` -- an in-progress window still has a legitimate future to
expire into naturally and must not be cut short just because
something else happened to call this method.
```

## CH-0107

- moved from: `src/r2db_api/service.py` (`DataService._make_audit_hook`)
- parent commit: `3a4c018`
- kind: docstring

```
Phase 4 (design D-2): builds the `ApplicationAuditHook` passed
to `StorageBackend.transact`/`apply_schema` as `audit_hook` --
every field the durable row needs is already resolved here (this
is `DataService`'s own job; the backend has no identity/request
context of its own beyond what it is given).
```

## CH-0108

- moved from: `src/r2db_api/service.py` (`DataService._denial_event`)
- parent commit: `3a4c018`
- kind: docstring

```
The shared fail-closed/coalesced-denial dispatch (design D-3),
used both by `_event`'s own deny branch and by `authenticate`'s
except clause (which has no `canonical`/`AuthContext` to route
through `_event` at all -- authentication itself is what failed).
`details` mirrors `_event`'s own audit-sink-origin short-circuit.
```

## CH-0109

- moved from: `src/r2db_api/service.py` (`DataService._event`)
- parent commit: `3a4c018`
- kind: docstring

```
The single dispatch point every public method above calls,
both on success (`outcome="allow"`) and on denial
(`outcome="deny"`). Always appends to the pre-existing legacy
in-memory `self._audit` first, unconditionally (D-10: this sink's
behaviour is completely unaffected by anything below) -- then
applies Phase 4's durable-recording dispatch (design D-2/D-3/D-4):

- `already_durable=True` (only ever passed by `mutate`/`schema`
  above, when the backend's own pre-commit hook already durably
  recorded this exact event): return immediately. D-10's "at most
  one durable row per operation" rule.
- `outcome == "deny"`: `details["origin"] == "audit_sink"` (D-2)
  means this denial's `SERVICE_UNAVAILABLE` was produced by the
  audit pipeline itself already failing to record this very
  operation (a pre-commit sink failure, a commit-failure error-row
  write, a coalesced-denial first-insert failure) -- routing it
  through `_route_denial` again would be a second (or third)
  durable write for what is still logically one operation, so this
  returns without doing anything further. Otherwise, any reason
  code outside D-3's durable-code inclusion list (`_DURABLE_
  DENIAL_CODES`, J-2 -- not merely the 4 originally named) returns
  without any durable/buffered
  record at all; every other reason code is fail-closed-class and
  goes through the coalescing denial router (which may itself
  raise `SERVICE_UNAVAILABLE`).
- `outcome == "allow"`: buffer-class (D-4) -- `query`/`catalog`
  always reach here (they never pass through the confirmation
  choke), and `mutate` reaches here only when its batch did NOT
  (`already_durable=False`).
```

## CH-0110

- moved from: `src/r2db_api/service.py` (`DataService.acquire_concurrency_slot`)
- parent commit: `3a4c018`
- kind: docstring

```
Phase 10 WP-8c (design D-8 (3), review F-2): pre-authentication
concurrency admission for the HTTP surface -- mirrors
`ControlPlaneService.check_rate()`'s own pre-auth admission shape
on the control plane (`control_http.py`'s module header: "charged
before anything else, including authentication"), applied here to
`concurrency` rather than `requests_per_minute` (this class alone
is credential-independent, so it alone can be evaluated before a
credential is known at all -- see `_slot`'s own docstring).

`http.py` enters this BEFORE calling `_authenticate`, and holds it
for the caller's own ENTIRE request -- authentication, body
parsing, and the eventual `DataService` business call, which
itself passes `concurrency_precharged=True` into `_slot` so the
SAME single reservation is never taken twice for one request
(`_slot`'s own docstring). This closes review F-2's own measured
gap: before this WP, an unauthenticated flood (invalid bearer
tokens) never touched `self._active` at all -- `_authenticate`
occupied a worker thread and the platform credential pool for
every concurrently in-flight request, up to anyio's own
thread-limiter ceiling (40), regardless of `limits.concurrency`
(32). With this reservation taken first, at most `limits.
concurrency` requests -- authenticated or not -- are ever
in-flight at once, so demand on `_authenticate`'s own platform
pool is bounded by the SAME declared class a caller's own
`capabilities()` document already advertises as `concurrency`.

A refusal here raises `fail()` directly, exactly like `_slot`'s
own concurrency branch did before this WP -- no `_event`/durable-
audit call runs between this raise and the ASGI layer's own
`except FoundationError` (`http.py::_endpoint`), so this denial is
never durably audited, the same "rate-class pre-auth denial is
never durably audited" rule `_acquire_rate`'s own denial already
followed (there is no `context`/`canonical` to attribute it to
yet in any case).

Deliberately its OWN copy of the check-then-increment block
`_slot` above also carries (not a shared helper the two call into)
-- `tests/test_threadpool_offload.py::test_slot_check_then_
increment_is_lexically_inside_the_active_lock` pins that exact
block LEXICALLY INSIDE `_slot` itself (an AST scan, WP-8a review
F-4), so factoring it out into a shared private method would have
turned that pre-existing, unrelated test red as a side effect of
this WP -- an acceptable small duplication (four lines) rather
than disturbing a pinned mutation-test shape this WP does not own.
```

## CH-0111

- moved from: `src/r2db_api/service.py` (`DataService._slot`)
- parent commit: `3a4c018`
- kind: docstring

```
Phase 10 WP-8c (design D-8 (3), review F-2): `concurrency_
precharged` mirrors `ControlPlaneService.check_rate()`'s own
`rate_precharged` parameter (`control_plane.py::check_rate`'s
docstring) -- an HTTP caller that already reserved this SAME
deployment's own concurrency slot BEFORE authentication (via
`acquire_concurrency_slot()` below, called from `http.py` ahead of
`_authenticate`) passes `concurrency_precharged=True` into the
eventual `DataService` call so this method does not reserve a
SECOND slot for the identical logical request -- otherwise every
HTTP request would cost 2 units of `limits.concurrency` instead of
1, halving the deployment's own real capacity relative to its
declaration (completion condition 3). Every OTHER caller (this
repository's own tests, the in-process conformance adapter, which
call a `DataService` method directly with no pre-auth reservation
of their own) keeps the default `False` -- unchanged from before
this WP: `_check`/`_acquire_rate` run exactly as before, and the
concurrency slot is still acquired HERE, inside this method, in
exactly the same relative position (after `_check`/`_acquire_rate`,
around the caller's own business logic) `hold_in_flight`'s own
stall point already depends on (`conformance-tests/adapter.py`'s
`hold_in_flight` docstring: "AFTER the concurrency counter is
acquired and BEFORE DB execution").

`_check`/`_acquire_rate` stay POST-authentication in every case:
`_acquire_rate` is keyed by `context.credential_id` (`_acquire_
rate`'s own signature), which does not exist before authentication
resolves one -- only the credential-independent concurrency bound
can be, and now is, taken before authentication.
```

## CH-0112

- moved from: `src/r2db_api/service.py` (`DataService.deny_unsupported`)
- parent commit: `3a4c018`
- kind: comment

```
# D-3 (4): the request AS A WHOLE is what is unsupported
# here (this foundation has no execution path for the
# endpoint at all) -- `field` is omitted, matching
# `errors.details_vocabulary.CAPABILITY_UNSUPPORTED`'s own
# "omitted where the request as a whole is what is
# unsupported" clause.
```

## CH-0113

- moved from: `src/r2db_api/service.py` (`DataService.deny_unsupported`)
- parent commit: `3a4c018`
- kind: docstring

```
Refuse a capability this foundation does not implement, while
still passing through `_slot`'s rate/concurrency accounting and
emitting a denial audit event -- exactly like every other
application-plane method below, instead of being a bare pre-`_slot`
`fail()` call that an unauthenticated-looking credential could
spend for free (review R12).

`http.py`'s `post_audit_query`/`post_cross_entity_mutate` stub
handlers use this for the two contract endpoints this foundation
declares `unavailable`/has no execution path for at all
(`audit_query`, `cross_entity_mutation`); this always raises
`CAPABILITY_UNSUPPORTED`, it never returns.

Phase 4 (design D-3): this denial's `reason_code` is always
`CAPABILITY_UNSUPPORTED` -- not in D-3's durable-code inclusion list, so
`_event`'s deny dispatch never routes it through the durable/
coalesced path (unchanged from pre-Phase-4 behaviour: this method
never wrote a durable row before this WP either).
```

## CH-0114

- moved from: `src/r2db_api/service.py` (`DataService.catalog`)
- parent commit: `3a4c018`
- kind: comment

```
# Phase 4 (design D-2 §7.3): `catalog` never passes through
# the confirmation choke -- always buffer-class.
```

## CH-0115

- moved from: `src/r2db_api/service.py` (`DataService.schema`)
- parent commit: `3a4c018`
- kind: comment

```
# Phase 4 (design D-2, item 2): unconditionally fail-closed
# -- every schema operation, not only a confirmed destructive
# one (unlike `mutate` above). Extended by D-4 (4)/U-2 = (A)
# (WP-2b): a `dry_run` never gets a hook AT ALL -- not
# merely one that is never called -- so no audit line can
# ever be written for it, by construction.
```

## CH-0116

- moved from: `src/r2db_api/service.py` (`DataService.schema`)
- parent commit: `3a4c018`
- kind: comment

```
# Contract 1.7.0 (D-4 (7)/S-a, WP-2b): the contract-level
# request object a `plan` commits to -- `operation` itself
# already IS that object (`SchemaOperationRequest`'s own
# flat shape), minus `plan`/`dry_run` (S-a's exclusion
# pair, applied again defensively inside `normalize_
# request_for_plan`). Ruling I-13: `idempotency_key`, when
# present, stays IN this object (only `plan`/`dry_run` are
# excluded here) -- `idempotency_digest` below applies its
# own, separate 3-key exclusion.
```

## CH-0117

- moved from: `src/r2db_api/service.py` (`DataService.schema`)
- parent commit: `3a4c018`
- kind: comment

```
# Contract 1.7.0 (D-6, addendum 2 S-l, ruling B-2/B-3,
# WP-2d): see `_query_outcome`'s identical comment.
```

## CH-0118

- moved from: `src/r2db_api/service.py` (`DataService.schema`)
- parent commit: `3a4c018`
- kind: comment

```
# Authority is checked before touching request content at
# all, so a non-developer credential gets FORBIDDEN/403 for
# any schema operation, before any shape/capability
# question is even considered. Unaffected by `dry_run`
# (D-4 (2): a dry run walks the SAME gates a real request
# does, no early-out).
```

## CH-0119

- moved from: `src/r2db_api/service.py` (`DataService.schema`)
- parent commit: `3a4c018`
- kind: comment

```
# Contract 1.7.0 (D-4, WP-2b): `SchemaOperationRequest` is the
# single flat operation object itself (no separate `operations`
# wrapper the way `MutationRequest` has) -- `dry_run`/`plan` are
# simply keys already present on `operation`, read here (before
# `_slot`) so the audit-hook/dispatch decisions below can already
# act on them.
```

## CH-0120

- moved from: `src/r2db_api/service.py` (`DataService.schema`)
- parent commit: `3a4c018`
- kind: docstring

```
Always returns `SchemaOutcome` (`.committed`/`.revision`/
`.descriptor`/`.plan`, contract 1.7.0, D-4, WP-2b) -- a pure
passthrough of `ApplicationCell.apply_schema`/`PostgresCell.
apply_schema`'s own return, which review round F-8
(`{scratchpad}/rulings-r4.md`) unified to one shape regardless of
whether `operation` carries `dry_run`/`plan`. Every pre-1.7.0
direct caller of this method (`tests/test_foundation.py`,
`tests/test_constraints_declaration.py`) reads `.revision` off
the result; the in-process conformance adapter's own `hasattr(
result, "revision")` branch already handles a non-`int` result
unchanged (it never assumed `int`).

`budget`/`idempotency_key` (contract 1.7.0, D-6/D-5, WP-2d/WP-2c):
both real as of this commit -- the provisional gate that used to
reject either field outright (`_PROVISIONAL_UNSUPPORTED_SCHEMA_
FIELDS`) is removed in this same commit as `capabilities().
request_budget`/`.idempotency` both flipping to `enabled` (P-3).
```

## CH-0121

- moved from: `src/r2db_api/service.py` (`DataService._mutate_outcome`)
- parent commit: `3a4c018`
- kind: comment

```
# D-4 (4)/U-2 = (A): a dry_run that reached this point
# reached the "would succeed" decision -- no audit event
# (buffer-class OR the legacy in-memory sink `_event`
# itself unconditionally appends to) is written for it.
# D-10: `outcome.destructive` reports whether the backend's
# pre-commit hook already durably recorded this batch --
# `already_durable` tells `_event` to skip the buffer-class
# enqueue in that case (at most one durable row per
# operation). Contract 1.7.0 (D-5 (1)(v), ruling I-11/J-4,
# WP-2c/WP-2cd): `outcome.replayed` -- a resend answered
# from an idempotency record still earns its OWN audit line
# (SI-14, WP-2cd audit N-5: a destructive resend must never
# return `committed: true` while leaving zero evidence of
# its own that this Application was touched at time T) --
# `outcome="replayed"`, never `"allow"`, keeps a resend
# distinguishable from a genuine new execution in the audit
# trail itself; it carries THIS resend's own `request_id`
# (never the original), and, like every event this method
# emits, never the `idempotency_key` value (I-11). Always
# `already_durable=False`: a replay never invokes the
# pre-commit hook (nothing below the idempotency lookup
# executed), so no durable row has already been written for
# THIS event the way a genuinely destructive fresh commit's
# hook already wrote one for its own.
```

## CH-0122

- moved from: `src/r2db_api/service.py` (`DataService._mutate_outcome`)
- parent commit: `3a4c018`
- kind: comment

```
# Phase 4 (design D-2/D-10), extended by D-4 (4)/U-2 = (A)
# (WP-2b): the hook is only ever USED by the backend when
# this batch turns out to pass through the confirmation
# choke (a confirmed `delete`) -- building it unconditionally
# here is cheap (no I/O happens until/unless `pre_commit()`
# is actually called) and keeps this call site identical
# regardless of what the batch turns out to contain,
# matching `schema`'s own unconditional hook below. A
# `dry_run`, though, never gets one AT ALL -- not merely
# one that is never called -- so no audit line can ever be
# written for it, by construction (U-2 = (A): "監査行を一切
# 書かない", not "書くが呼ばない").
```

## CH-0123

- moved from: `src/r2db_api/service.py` (`DataService._mutate_outcome`)
- parent commit: `3a4c018`
- kind: comment

```
# Ruling I-13 (`{scratchpad}/rulings-wp2a-review.md` audit
# N-3): `idempotency_key` is INCLUDED in the plan digest
# (only `plan`/`dry_run` are excluded there, `normalize_
# request_for_plan`'s own 2-key exclusion) even though it
# is excluded from its OWN digest (`normalize_request_for_
# idempotency`'s 3-key exclusion, `idempotency_digest`
# below) -- a `plan` token captured with one key (or none)
# must not verify against a request presenting a different
# one.
```

## CH-0124

- moved from: `src/r2db_api/service.py` (`DataService._mutate_outcome`)
- parent commit: `3a4c018`
- kind: comment

```
# Contract 1.7.0 (D-4 (7)/S-a, WP-2b): the contract-level
# request object a `plan` commits to -- `operations`/
# `transaction`/`budget`, plus this request's own target
# `entity` (H-1, `{scratchpad}/rulings-r4.md` addendum 2:
# "computed from the request itself" includes the request's
# URL path segment, not only its body -- `MutationRequest`
# itself has no `entity` property, but the plan digest is
# not scoped to `MutationRequest` alone). Placed at the
# object's own top level so a plan captured for one entity's
# dry_run, presented against a DIFFERENT entity's apply
# (identical `operations`/`transaction`/`budget`, identical
# schema_revision), fails PRECONDITION_FAILED fail-closed,
# rather than being silently honored. `dry_run`/`plan`
# themselves are excluded (S-a's own exclusion pair, applied
# again defensively inside `normalize_request_for_plan`).
# G-1: `transaction` is included only when the caller's own
# request object actually carried the key (see above) --
# never the resolved/defaulted value.
```

## CH-0125

- moved from: `src/r2db_api/service.py` (`DataService._mutate_outcome`)
- parent commit: `3a4c018`
- kind: comment

```
# Contract 1.7.0 (D-6, addendum 2 S-l, ruling B-2/B-3,
# WP-2d): see `_query_outcome`'s identical comment -- the
# SAME single point (`narrow_limits_by_budget`) every
# endpoint uses, checked here at request-shape time,
# before target-existence.
```

## CH-0126

- moved from: `src/r2db_api/service.py` (`DataService._mutate_outcome`)
- parent commit: `3a4c018`
- kind: comment

```
# G-1 (`{scratchpad}/rulings-r4.md` addendum): `transaction`
# is never a contract-level *default* -- `None` here means
# the caller's own request object never carried the key at
# all (both `http.post_mutate` and the in-process port omit
# the kwarg rather than resolving it to `"atomic"` before
# this call). `resolved_transaction` is used for every
# behavioural decision (the capability gate below); the
# RAW `transaction` value (still `None` when omitted) is
# what `plan_request` below reflects, so a request that
# carried `transaction: "atomic"` explicitly digests
# differently from one that omitted the key entirely, even
# though both behave identically otherwise.
```

## CH-0127

- moved from: `src/r2db_api/service.py` (`DataService.mutate_result`)
- parent commit: `3a4c018`
- kind: comment

```
# D-4 (3)/A-9: a dry-run mutation result never carries
# `assigned_addresses` -- the addresses a real execution would
# assign are not settled (an insert may still have tentatively
# consumed real id-sequence values, F-15, but this response
# never reports them). Review round F-6: `None`, not `[]` --
# `http.post_mutate` omits the key itself on `None`, matching
# the contract's "does not carry" wording.
```

## CH-0128

- moved from: `src/r2db_api/service.py` (`DataService.mutate_result`)
- parent commit: `3a4c018`
- kind: comment

```
# Contract 1.7.0 (D-7 (3), WP-2e): `outcome.request_id` -- THIS
# execution's own value for a real commit/dry_run, or the
# ORIGINAL execution's own value for an idempotency replay
# (`MutationOutcome.request_id`'s own comment) -- never the
# resend's own `rid` (which `_mutate_outcome` below already
# used for the resend's own, separate audit event).
```

## CH-0129

- moved from: `src/r2db_api/service.py` (`DataService.mutate_result`)
- parent commit: `3a4c018`
- kind: docstring

```
The HTTP-facing shape (`{affected, assigned_addresses}`,
`spec/data-service-api.v1.json`'s `MutationResult`) -- used by
`http.post_mutate` instead of `mutate` above, mirroring the
`query`/`query_page` split (WP-4/WP-5).

`dry_run`/`plan` (contract 1.7.0, D-4, WP-2b): real, given full
effect below -- `capabilities().dry_run` is `enabled` as of this
commit. `budget` (contract 1.7.0, D-6, WP-2d) and `idempotency_
key` (contract 1.7.0, D-5, WP-2c) are likewise real as of this
commit -- `capabilities().request_budget`/`.idempotency` are both
`enabled`; `_mutate_outcome` below validates/narrows `budget` and
consults/records `idempotency_key` at exactly the request stages
`narrow_limits_by_budget`'s/`transact`'s own comments describe.
```

## CH-0130

- moved from: `src/r2db_api/service.py` (`DataService.mutate`)
- parent commit: `3a4c018`
- kind: docstring

```
Plain affected-count form, unchanged in shape since before
CCR-13 (every existing caller -- `tests/test_foundation.py`, the
in-process conformance adapter -- keeps working against exactly
this return type). `mutate_result` below is the richer shape
`http.post_mutate` uses.
```

## CH-0131

- moved from: `src/r2db_api/service.py` (`DataService._query_outcome`)
- parent commit: `3a4c018`
- kind: comment

```
# Phase 4 (design D-2 §7.3): `query` never passes through
# the confirmation choke -- always buffer-class.
```

## CH-0132

- moved from: `src/r2db_api/service.py` (`DataService._query_outcome`)
- parent commit: `3a4c018`
- kind: comment

```
# Contract 1.7.0 (D-6, addendum 2 S-l, ruling B-2/B-3,
# WP-2d): `request_budget` is `enabled` -- `budget` validity
# (applicable class / integer >= 1 / not above the deployed
# bound) is checked here, at request-shape time, before
# target existence -- the SAME single point every endpoint
# uses (`limits.narrow_limits_by_budget`) to turn `budget`
# into the "effective limits" every existing check point
# below reads, without any of them being rewritten.
```

## CH-0133

- moved from: `src/r2db_api/service.py` (`DataService.query_page`)
- parent commit: `3a4c018`
- kind: comment

```
# Contract 1.7.0 (D-7, WP-2e): resolved HERE, once, so the SAME
# value both reaches `QueryPage.request_id` below and is the one
# `_query_outcome` uses for its own audit event -- the generation
# point for the request/response pair a caller sees, never
# re-derived a second time for the response body (Q-1: "HTTP 層は
# 再生成しない" generalizes to "no layer re-derives it").
```

## CH-0134

- moved from: `src/r2db_api/service.py` (`DataService.query_page`)
- parent commit: `3a4c018`
- kind: docstring

```
The HTTP-facing shape (`{items, next_page, revisions}`,
`spec/data-service-api.v1.json`'s `QueryResult`) -- used by `http.
post_query` instead of `query` above, since building a real
`next_page`/`revisions` needs `QueryOutcome.next_cursor`/
`.revisions`, which the plain-list `query()` deliberately does not
expose (kept byte-for-byte backward compatible with every pre-
CCR-13 caller). `revisions` is always index-aligned with `items`:
`revision_preconditions` is declared `enabled`, and every entity
both cells provision is `mutable`, so a query response always
carries revisions (R-4).

`budget` (contract 1.7.0, `QueryRequest.budget`, WP-2d): real,
given full effect by `_query_outcome` below via `limits.
narrow_limits_by_budget` -- `capabilities().request_budget` is
`enabled` as of this commit. `result_items`/`execution_ms` are the
two classes a query's own `budget` may narrow (D-6 (2)); an
applicable-but-invalid or inapplicable `budget` is refused
`VALIDATION_FAILED` before target existence.
```

## CH-0135

- moved from: `src/r2db_api/service.py` (`DataService.query`)
- parent commit: `3a4c018`
- kind: docstring

```
Plain-item-list form, unchanged in shape since before CCR-13
(every existing caller -- `tests/test_foundation.py`, the in-process
conformance adapter -- keeps working against exactly this return
type). `order_by`/`cursor` (CCR-13 WP-4) are accepted here too (so
this method alone is enough to exercise/test them against the
facade), but the pagination continuation itself only reaches a
caller through `query_page` below, which `http.post_query` uses.
```

## CH-0136

- moved from: `src/r2db_api/service.py` (`DataService.capabilities`)
- parent commit: `3a4c018`
- kind: comment

```
# Phase 6 WP-2 (design D-2): `surfaces` is an optional key --
# present only when this instance was constructed with one
# (`__init__`'s own comment on `self._surfaces`). Never a
# `"surfaces": None` entry.
```

## CH-0137

- moved from: `src/r2db_api/service.py` (`DataService.capabilities`)
- parent commit: `3a4c018`
- kind: comment

```
# Ruling J-3 (WP-2cd audit N-3): `idempotency_retention_ms`
# joins `execution_ms` in the `reference_wall_clock` set --
# both are wall-clock DURATIONS a deployment cannot drive to
# a deterministic N/N+1 boundary within a bounded test run
# (unlike every COUNT-valued class here, `idempotency_
# entries` included, which genuinely IS `enforced`: a
# record's own retention window is checked lazily, against
# real elapsed time, not a request-counted budget).
# Phase 10 WP-6a (design D-5(ii), contract 1.8.0): three
# regions, not two. Region (i) (request-scoped: every class
# below not named in the other two sets) is unaffected by
# `process_ceiling` -- unchanged from before this WP.
# Region (ii) (`requests_per_minute`/`concurrency` --
# bound by in-memory, per-process state, `self._rate_
# windows`/`self._active`) reads `enforced` only while
# `process_ceiling == 1` and `deployment_required` once it
# is `>= 2` (contract 1.8.0's own enforcement-scope
# definition: a per-process bound is `enforced` for the
# whole deployment only while exactly one process may
# serve this plane's base URL). Region (iii)
# (`idempotency_entries` -- bound in PostgreSQL,
# `postgres.py`'s own `_idempotency_reserve`) stays
# `enforced` regardless of `process_ceiling` -- this class
# does not resolve within one request. Its own count lock
# is WP-6d-i's scope (supervisory ruling 2026-09-08), not
# this WP's.
```

## CH-0138

- moved from: `src/r2db_api/service.py` (`DataService.capabilities`)
- parent commit: `3a4c018`
- kind: comment

```
# WP-2b: `dry_run` is `enabled` -- `dry_run`/`plan` are
# no longer in `_PROVISIONAL_UNSUPPORTED_SCHEMA_FIELDS`
# (schema side) and `mutate_result`/`_mutate_outcome`
# (mutation side) no longer refuse them outright, in
# this same commit as `structured.py`/`postgres.py`'s
# own real dry_run/plan enforcement (D-4). WP-2d
# (`request_budget`) flips its own entry the same way,
# in its own commit.
```

## CH-0139

- moved from: `src/r2db_api/service.py` (`DataService.capabilities`)
- parent commit: `3a4c018`
- kind: comment

```
# Contract 1.7.0 (subordinate ruling 12, D-1 (3)): three
# new capabilities, honestly declared `unavailable`
# until each one's own capability WP flips it, in the
# SAME commit as the provisional gate that rejects
# every field it governs (`schema`/`mutate_result`/
# `_query_outcome` above, `http.py`'s `post_mutate`/
# `post_query`) -- P-3 (宣言と挙動は同一コミット).
#
# WP-2a: `constraint_declarations` is `enabled` --
# `field_constraints`/`enum`/`nullable`/`alter_field`
# are no longer in `_PROVISIONAL_UNSUPPORTED_SCHEMA_
# FIELDS` (removed in this same commit) and are now
# enforced (`structured.py`/`postgres.py`).
```

## CH-0140

- moved from: `src/r2db_api/service.py` (`DataService.capabilities`)
- parent commit: `3a4c018`
- kind: comment

```
# R-9: reflects this instance's own constructor-injected
# deployer declaration -- never hardcoded (see __init__'s
# comment on this field).
```

## CH-0141

- moved from: `src/r2db_api/service.py` (`DataService.capabilities`)
- parent commit: `3a4c018`
- kind: comment

```
# `cross_entity_mutation` needs the new `POST /v1/data/
# mutations` endpoint (stubbed in `http.py` as
# CAPABILITY_UNSUPPORTED, not executable), so it stays
# `unavailable` here: it has no executable operation at
# all. (`control_plane`, immediately below, is NOT in
# the same position any more: CCR-14 shipped the
# `/control/v1` surface as a separate process, and its
# status is the deployer's own R-9 declaration -- the
# pre-CCR-14 wording that once grouped the two as "both
# remain unavailable" was corrected 2026-09-05.)
```

## CH-0142

- moved from: `src/r2db_api/service.py` (`DataService.capabilities`)
- parent commit: `3a4c018`
- kind: comment

```
# Phase 4 WP-2(b) (P4-D4, contract `versioning.
# version_binding`), flipped to 1.5.0 in phase 5 WP-2,
# flipped to 1.6.0 in phase 6 WP-2 (design docs/design/
# PHASE6_CONTRACT_160_CLIENT_DISCOVERY_V1.md, subordinate
# ruling 11): unconditional -- every deployment of this
# data-plane host declares 1.6.0 now, whether or not
# the CONTROL host alongside it has AUDIT DSN configured
# (`audit_query` stays `unavailable` right below,
# unchanged: this host never provides it, D-5's own
# "declaration = real behavior" rule). This same commit
# ships every 1.6.0 behavioral obligation this host owns
# (locator-form credentials, `surfaces`, `field_types`) --
# the flip is never ahead of the behavior it declares.
#
# Flipped to 1.7.0 in phase 9 WP-2e (design docs/design/
# PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md
# D-1 (5)): the SAME commit as this host's own R-3
# (`errors.details_vocabulary` 4-key details) and R-7
# (`request_id` on every successful result) implementation
# -- the two 1.7.0 UNCONDITIONAL obligations -- never ahead
# of the behavior it declares (D-1 (7)'s xfail(strict=True)
# version gate is exactly what would catch that ordering
# mistake).
#
# Phase 10 WP-6a/pair-closing (design D-5 (v)): flipped
# again to 1.8.0 in the SAME commit as this host's own
# `process_ceilings` mapping (D-5 (ii)) -- the version's
# one unconditional obligation, `limit_enforcement_scoped_
# to_deployment_behind_base_url` -- never ahead of the
# behavior it declares.
```

## CH-0143

- moved from: `src/r2db_api/service.py` (`DataService.capabilities`)
- parent commit: `3a4c018`
- kind: comment

```
# CCR-13 WP-5b: the WP-2-through-WP-5 provisional gate (design
# R2DB_CCR13_STORAGE_V1.md §3) is removed in this same commit
# (see `query`/`mutate`/`schema`/`catalog` below) -- this
# declaration update is what makes that removal honest rather
# than a new C-12 "declared unavailable, executes anyway" gap.
# Contract 1.7.0 (D-2 (5), WP-2a): `alter_field` joins the
# developer-only schema-operation set -- `R-2` constraint
# declarations are enforced now (see `constraint_declarations`
# below), so it is no longer accurate to list it under
# `unsupported`.
```

## CH-0144

- moved from: `src/r2db_api/service.py` (`DataService.authenticate`)
- parent commit: `3a4c018`
- kind: comment

```
# Phase 4 (design D-2/D-3): the legacy in-memory `self._audit`
# append is unchanged (pre-Phase-4 behaviour, this repository's
# own tests read it back via `ControlAuthority.audit_events()`)
# -- `_denial_event` below ADDS the durable/coalesced dispatch
# every other public method's `except FoundationError` reaches
# through `_event`'s own deny branch; this call site cannot use
# `_event` itself because authentication has not yet resolved a
# `canonical`/`AuthContext` to build one from.
```

## CH-0145

- moved from: `src/r2db_api/service.py` (`DataService.__init__`)
- parent commit: `3a4c018`
- kind: comment

```
# Phase 4 (design PHASE4_DURABLE_AUDIT_SINK_V1.md D-1/D-10): the
# durable-designated sink -- `ApplicationAuditSink` (in-memory,
# fault-injectable) by default, or a caller-supplied
# `PostgresApplicationAuditSink` (`credential_store.py`, wired by
# `main.py`'s composition root). `self._audit` above is untouched
# and stays the sole recorder for D-3's non-durable denial classes
# (everything outside `_DURABLE_DENIAL_CODES`'s inclusion list,
# J-2 -- D-10's own instruction) -- this is a SEPARATE sink, not a
# replacement.
```

## CH-0146

- moved from: `src/r2db_api/service.py` (`DataService.__init__`)
- parent commit: `3a4c018`
- kind: comment

```
# Phase 10 WP-6a (design D-5(ii), contract 1.8.0): the deployer's
# own declared ceiling on how many processes may serve THIS
# plane's `surfaces` base URL at the same time -- constructor-
# injected, same "deployer-declared, not derived" discipline as
# `control_plane_status`/`surfaces` above. `main.py` (the real
# composition root) is the one caller that resolves this from the
# DB-side `process_ceilings` declaration (`platform_declarations.
# read_platform_declarations(...).process_ceilings.data`) at
# startup; every other caller (this repository's own unit tests,
# the in-process conformance adapter) keeps the default `1` --
# the single-process assumption every pre-Phase-10 caller already
# made implicitly, so this default changes no existing behavior.
# Validated here (not only at `main.py`'s own read/validate
# boundary via `platform_declarations.validate_process_ceilings_
# value`) so any other direct caller gets the same fail-loud guard
# against a non-positive value, rather than silently publishing a
# nonsensical `limit_enforcement` mapping.
```

## CH-0147

- moved from: `src/r2db_api/service.py` (`DataService.__init__`)
- parent commit: `3a4c018`
- kind: comment

```
# Phase 6 WP-2 (design D-2): `surfaces` is constructor-injected,
# same "deployer-declared, not derived" discipline as `control_
# plane_status` immediately above -- `main.py` (the real
# composition root) is the one caller that validates the two
# `R2DB_*_BASE_URL` environment variables' SHAPE at startup and
# assembles this dict from them; this class only ever echoes
# whatever it was given, verbatim, in `capabilities()` below. `None`
# (the default -- every pre-WP-2 caller, including this
# repository's own unit tests that construct `DataService` directly
# without opting in) omits the `surfaces` key from the response
# entirely, never a `"surfaces": None` value (contract `Capability
# Document.surfaces` is an optional key, not a nullable one).
```

## CH-0148

- moved from: `src/r2db_api/service.py` (`DataService.__init__`)
- parent commit: `3a4c018`
- kind: comment

```
# R-9 (CCR-14 WP-5, design docs/design/R2DB_CCR14_CONTROL_PLANE_V1.md
# §1: "capability 申告は環境変数由来で composition root 注入"):
# whether this application-plane process' own `capabilities()`
# declares `control_plane: enabled` is a *deployer* fact this class
# cannot know on its own (a separated `/control/v1` deployment, the
# default, means the application-plane process has no idea whether a
# control-plane process is running anywhere at all) -- it is
# constructor-injected, defaulting to the safe, honest `unavailable`
# so nothing short of an explicit composition-root decision
# (`main.py`, reading `R2DB_CONTROL_PLANE_STATUS`) ever declares
# `enabled`. Validated here too (not only at `main.py`'s env-parsing
# boundary) so any other caller constructing a `DataService` directly
# (this repository's own tests, the WP-5 in-process conformance
# adapter) gets the same fail-loud guard against a typo'd status
# string, rather than silently publishing an invalid capability
# value.
```

## CH-0149

- moved from: `src/r2db_api/service.py` (`_DenialCoalescer._flush_keys`)
- parent commit: `3a4c018`
- kind: comment

```
# Review D-1: never silently drop this repeat count
# -- put it back where a future attempt (this same
# sweep's own next pass, a later explicit/periodic
# flush, or the next `route()` call for this key)
# will retry it. Safe specifically because this
# happens under THIS key's own lock (no concurrent
# `route()`/sweep call for the SAME key can be
# touching `self._windows[key]` right now).
```

## CH-0150

- moved from: `src/r2db_api/service.py` (`_DenialCoalescer.flush_all`)
- parent commit: `3a4c018`
- kind: docstring

```
WP-2(a) fix round 2, review N-4: force EVERY currently-open
window to be flushed, expired or not -- used only at graceful
shutdown. Once this process is about to stop, there is no "wait
for the window to naturally expire" future left; treating every
window as due now is what keeps a shutdown from silently
discarding an in-progress window's accumulated repeat count (D-3
only ever sanctions losing counts to an actual crash, never to an
orderly stop).
```

## CH-0151

- moved from: `src/r2db_api/service.py` (`_DenialCoalescer._note_aggregate_write_result`)
- parent commit: `3a4c018`
- kind: docstring

```
Review D-1: fixed-message `logging.error`, only on a failing<->
healthy state TRANSITION (N-2's own established discipline) -- not
once per attempt, which would reproduce the exact logging-DoS risk
N-2 already closed for the buffer-overflow alert path.
```

## CH-0152

- moved from: `src/r2db_api/service.py` (`_DenialCoalescer._requeue_failed_aggregate`)
- parent commit: `3a4c018`
- kind: docstring

```
WP-2(a) fix round 3, review D-1: called only while holding this
KEY's OWN `key_lock` (both call sites below), right after its
aggregate-row write attempt raised -- puts `state["repeat_count"]`
back where a future flush (periodic, explicit, shutdown, or the
very next `route()` call for this same key) will retry it, instead
of discarding it. Two cases, both safe specifically BECAUSE the
caller holds this key's lock (no concurrent `route()`/sweep call
for the SAME key can be observing or mutating `self._windows[key]`
at this exact moment -- see class docstring):

- A fresh window has already been opened for this key by a
  concurrent `route()` call in the meantime (its own first-
  occurrence row is already durable) -- merge the failed repeat
  count into it rather than overwriting.
- No window exists for this key right now -- re-register one
  carrying just the failed repeat count, with the SAME (already
  past) `window_start` it had, so it reads as immediately "due"
  again for both a future sweep and the next `route()` call for
  this key (which flushes an expired window inline before opening
  a fresh one, the same code path that calls this method).
```

## CH-0153

- moved from: `src/r2db_api/service.py` (`_DenialCoalescer._release_key_lock_ref`)
- parent commit: `3a4c018`
- kind: docstring

```
Review D-2: only prunes `self._key_locks[key]` when this is the
LAST outstanding reference (refcount reaches 0) AND no window
remains for the key -- see class docstring for why both conditions
are required for this to be safe.
```

## CH-0154

- moved from: `src/r2db_api/service.py` (`_DenialCoalescer.__init__`)
- parent commit: `3a4c018`
- kind: comment

```
# Review D-1: tracks whether the MOST RECENT aggregate-row write
# attempt (from any key) failed -- a single, process-wide flag,
# deliberately mirroring `_AuditBuffer`'s own N-2 state-transition
# logging discipline (log only on failing<->healthy transitions,
# never once per attempt).
```

## CH-0155

- moved from: `src/r2db_api/service.py` (`_DenialCoalescer`)
- parent commit: `3a4c018`
- kind: docstring

```
Phase 4 (design D-3/P4-D3): the coalescing state for fail-closed-
class denials. Process-local (review N-4: a shared store is never
consulted, so the same key can legitimately produce one row per
process/instance, not one row per deployment).

Keyed by `(application_id, actor_id or "unknown", operation,
reason_code)`, window `W` seconds: the first occurrence of a new key
writes a durable row synchronously (fail-closed -- `route()` raises
`SERVICE_UNAVAILABLE` if that write fails); every occurrence after that,
within the same window, only increments an in-memory counter. When the
window is later found expired (lazily, on the next `route()` call for
THAT key, or explicitly via `flush_expired()`/`flush_all()`), a second
row -- carrying the repeat count in `count` -- is written for that key,
if there were any repeats at all; zero-repeat windows are simply
dropped with no second write.

WP-2(a) review B-2 (fail-closed correctness): a same-key concurrent
`route()` call must never observe "a window already exists" (and take
the fast `repeat_count += 1` path) before the FIRST occurrence's own
durable INSERT has actually resolved -- otherwise a fail-closed denial
flood racing a sink outage could return an ordinary-looking denial
response, never even attempting its own durable write, while the
window's supposed first row was never actually recorded (§9.2 property
1's fail-closed guarantee would then hold only single-threaded).

WP-2(a) fix round 2, supervisor ruling on review m-2: PER-KEY locking,
not a single process-wide lock held across I/O. `self._lock` (process-
wide) protects ONLY `self._windows`/`self._key_locks`/`self._key_lock_
refcount` dict structure -- it is acquired only for brief, non-blocking
dict reads/writes, NEVER across a durable INSERT. Each coalescing key
gets its own `threading.Lock` (`self._key_locks`, created on first use),
held across that ONE key's own first-occurrence INSERT (and its own
expired-window aggregate flush, if one is due) -- this is what still
gives B-2 its correctness guarantee (a same-key concurrent caller
blocks on that key's own lock until the in-flight attempt resolves)
WITHOUT serializing unrelated keys against each other. The periodic
sweep (`flush_expired()`/`flush_all()`) collects expired keys/state
under the process lock and performs each one's INSERT under that SAME
key's own per-key lock (never the process lock) -- this is what lets a
concurrent `route()` call for that key correctly serialize against the
sweep too (WP-2(a) fix round 3, review D-1 -- see `_requeue_failed_
aggregate`'s own docstring for why this matters).

WP-2(a) fix round 3, review D-1 (major): a failed aggregate-row write
(the repeat-count summary row for an expired window) must never
silently discard that repeat count -- see `_requeue_failed_aggregate`.
A round-2 revision deleted the due window from `self._windows` before
attempting its write and simply dropped it on failure (`except:
continue`/`pass`), reasoning that re-inserting after releasing the
process lock would race a concurrent `route()` for the same key; that
race is real, but per-key locking (already required for B-2/m-2) is
exactly what closes it -- the requeue now happens under the SAME key's
lock the write attempt itself ran under, so no concurrent `route()`
call for that key can be in flight at that moment.

Review D-2 (minor): `self._key_locks` entries are pruned via reference
counting (`_acquire_key_lock`/`_release_key_lock_ref`) once a key has
no outstanding lock user AND no window left for it -- never while a
lock might still be in use (which would let a fresh `route()` call
silently start using a NEW, different `Lock` object for the same key,
defeating serialization entirely).
```

## CH-0156

- moved from: `src/r2db_api/service.py` (`_AuditBuffer._retry_alert`)
- parent commit: `3a4c018`
- kind: comment

```
# N-2: the backoff is keyed to whether the BUFFER FLUSH is
# currently failing, not to whether this alert row's own
# INSERT just succeeded. If the flush is still failing (more
# evictions can still be coming), keep backing off -- exactly
# like an alert-write failure would -- so a healthy alert path
# cannot be used to re-trigger a fresh attempt every single
# `_alert_min_interval_s` for as long as the underlying sink
# stays broken. Only reset to the floor once the flush itself
# is observed healthy.
```

## CH-0157

- moved from: `src/r2db_api/service.py` (`_AuditBuffer._retry_alert`)
- parent commit: `3a4c018`
- kind: comment

```
# §7.4/review m-4: this branch is only ever reached once the
# backoff interval has already elapsed (the early return above
# enforces that), so logging unconditionally here already
# matches "first attempt, then once per backoff interval" --
# no separate first-attempt bookkeeping is needed.
```

## CH-0158

- moved from: `src/r2db_api/service.py` (`_AuditBuffer.flush`)
- parent commit: `3a4c018`
- kind: comment

```
# P4-D15 (WP-B2): `_flush_currently_failing` clears
# unconditionally on ANY successful `append_many` --
# not gated on `self._events` being empty. Under
# sustained push load the buffer is rarely empty even
# once the sink has genuinely recovered (M-2's
# threshold flush keeps refilling it), so the prior
# "only when empty" gate left the flag -- and the
# alert backoff it feeds, see `_retry_alert` below --
# stuck at the sink-broken state long after recovery.
#
# Completion-order semantics absorb the WP-3(a) review
# m-1 race this replaces: a DIFFERENT, still-failing
# concurrent flush (disjoint batch, per the B-2 swap
# above) sets this back to True in its own failure
# branch whenever IT completes -- whichever flush
# completes LAST wins, exactly as with any other
# unsynchronized shared-state update. A brief window
# where this reads False while that concurrent failure
# is still in flight does not weaken the alert-rate
# guarantee: `_retry_alert`'s own `alert_min_interval_s`
# floor on `alert_next_retry_at` still bounds attempts
# to at most one per flush interval regardless of how
# many times this flag flips in between (§7.4's "at
# most 1 alert row per flush interval" is enforced by
# that floor, not by this flag).
#
# Accepted tradeoff (P4-D15): if the sink is FLAPPING
# (success and failure completing alternately), the
# backoff resets to the floor on every success, so the
# observed alert-row rate can rise from "stuck at the
# 60s backoff cap" up to "one per alert_min_interval_s"
# (2.0s by default). This is intentional -- evidence
# (`count`) reaches the durable table sooner from a
# partially-working sink, and the declared bound itself
# (at most 1 row per flush interval) still holds; only
# the realized rate moves toward that bound instead of
# sitting far under it.
```

## CH-0159

- moved from: `src/r2db_api/service.py` (`_AuditBuffer.flush`)
- parent commit: `3a4c018`
- kind: comment

```
# B-1: re-impose the capacity bound `push()` could not
# enforce while this batch was held outside
# `self._events` -- drop the oldest overflow, exactly
# the FIFO discipline `push()`'s own eviction branch
# uses, and count ONLY this genuine, irrevocable loss
# (the rest is still a retained retry, not a drop).
```

## CH-0160

- moved from: `src/r2db_api/service.py` (`_AuditBuffer.flush`)
- parent commit: `3a4c018`
- kind: comment

```
# N-1/N-2: put the un-written batch back rather than
# discarding it -- it is retried by the next flush, not
# counted in `_dropped_total` (nothing has actually been
# lost) and nothing new to alert or log about on this
# path alone. Prepended ahead of anything a concurrent
# `push()` added to `self._events` while this I/O was in
# flight, so flush order still matches arrival order.
```

## CH-0161

- moved from: `src/r2db_api/service.py` (`_AuditBuffer.flush`)
- parent commit: `3a4c018`
- kind: docstring

```
D-4/§7.3: called on demand (tests, the adapter privilege hook),
periodically (composition root), and now also from `push()` at the
threshold (M-2). Writes the current buffer contents as one batch,
then attempts the sticky overflow-alert retry -- always in that
order, always on a connection/transaction of its own. A failed
batch write leaves the events in place for the next attempt
(retained, not counted as dropped -- N-1) rather than discarding
them or alerting on its own.

WP-3(a) review B-2 (reentrancy): the periodic-flush thread
(composition root) and a request-path threshold flush (`push()`,
M-2 above) can call this method concurrently on the SAME buffer.
`pending` is therefore SWAPPED OUT of `self._events` under a
single lock acquisition (not merely copied) -- this, not a
separate "flush in progress" flag, is what makes two concurrent
`flush()` calls durably write disjoint (usually one full, one
empty) sets of events instead of both durably writing the SAME
events (the double-row bug this review found, reproduced verbatim
by `test_concurrent_periodic_and_threshold_flush_never_double_
writes_pending_events`). A concurrent call that finds `self.
_events` already emptied by the swap simply has nothing to flush
and returns without ever touching the sink -- it is not blocked or
serialized behind the in-flight I/O, so this stays lock-free
across the network round trip exactly as before.

A failed `append_many` puts `pending` BACK -- prepended, so it
precedes (in flush order) anything pushed while this I/O was in
flight -- preserving N-1's retain discipline (retained events are
never counted as dropped) and `_dropped_total`'s accuracy (a
retained batch is not itself a loss) exactly as the prior
read-then-delete version did.

WP-3(a) review B-1 (blocker, on the B-2 fix above): while this
method holds `pending` outside `self._events`, `push()` sees an
empty (or merely in-flight-refilled) buffer and does not evict --
capacity is enforced only against whatever is currently sitting in
`self._events`. A naive unconditional `pending + self._events`
restore on failure can therefore exceed `_capacity` (up to
`len(pending)` extra), and because the surviving overflow is never
itself re-evicted by a later `push()` (each `push()` only ever
evicts ONE item, the one IT just added), a sink outage would let
the buffer grow WITHOUT BOUND across repeated failed flushes --
breaking D-4's "bounded in-memory buffer" and D-1 review M-5's
capacity-side availability argument, and doing so *silently*: no
`push()` eviction fires during this growth, so `_dropped_total`
never increments and the overflow alert (D-4) never appears even
though evidence is unboundedly accumulating in memory. So the
restore truncates back down to `_capacity`, dropping from the
FRONT (oldest first, matching `push()`'s own `pop(0)` FIFO
discipline) -- and, exactly like a genuine `push()`-path eviction,
counts only what was ACTUALLY, irrevocably discarded here (never
the merely-retried remainder) in `_dropped_total`, sets
`_alert_pending`, and logs the same fixed overflow message.
```

## CH-0162

- moved from: `src/r2db_api/service.py` (`_AuditBuffer.push`)
- parent commit: `3a4c018`
- kind: comment

```
# M-2: threshold flush -- see class docstring. Outside the lock
# (already released above), on the calling thread.
```

## CH-0163

- moved from: `src/r2db_api/service.py` (`_AuditBuffer.__init__`)
- parent commit: `3a4c018`
- kind: comment

```
# N-2: tracks whether the most recent `flush()` attempt's own
# `append_many` succeeded or failed -- independent of the alert
# row's own write outcome, and read by `_retry_alert` to decide
# whether the backoff may reset.
```

## CH-0164

- moved from: `src/r2db_api/service.py` (`_AuditBuffer`)
- parent commit: `3a4c018`
- kind: docstring

```
Phase 4 (design D-4/§7.3/§7.4): the bounded in-memory buffer for
ordinary (buffer-class) data-operation success events, plus the
overflow-alert sticky-retry state. Owns its own lock; the durable I/O
`flush()` performs happens on the calling thread using `sink.append`/
`append_many`, each of which opens its own connection/transaction (D-1's
`PostgresApplicationAuditSink` docstring) -- this is what makes "a
flush never shares a transaction with a fail-closed write" (D-4)
automatic rather than something this class has to arrange.

Process-local (review N-4): capacity is per-process, not per-deployment
-- a multi-instance deployment's real bound is `capacity * <max
instances>`, which is runbook (§9.3), not code, territory.

WP-2(a) review M-2: §7.3 names TWO flush triggers, "periodic" and
"threshold" -- a prior revision implemented only the periodic one (the
composition root's background timer). `push()` now also triggers a
flush, synchronously, in the caller's own thread, the moment the buffer
reaches `_FLUSH_THRESHOLD_FRACTION` of capacity -- "その場で" (right
there), the simpler of the two options §7.3's own review text
sanctioned. Under a healthy sink this keeps the buffer far below
capacity, so overflow becomes a genuine signal that the sink cannot
keep up, not an artifact of the periodic timer's own interval.

`flush()` does not unconditionally empty `self._events` before
attempting the write -- a FAILED `append_many` leaves those events in
place (retried by the next flush) instead of discarding them outright,
so a transient I/O failure does not permanently destroy buffered
evidence a later retry might still durably record.

WP-2(a) fix round 2 review (N-1/N-2): a RETAINED event is, by
definition, NOT lost -- it is still sitting in `self._events`, waiting
for the next flush attempt. Counting it in `_dropped_total` (a prior
revision did, via `+= len(pending)` on every failed `append_many`) both
mislabels "not yet flushed" as "dropped" (N-1: the same event, retried
and failing repeatedly, gets counted again and again) AND -- combined
with a failed flush marking the alert pending -- lets a single
threshold-triggered flush failure emit its own alert-row *attempt* on
every subsequent buffer-class request (N-2: a `push()` on every
request, no bound on request rate). `_dropped_total` now increments
ONLY where an event is actually, irrevocably discarded: `push()`'s own
eviction branch (capacity reached, oldest event evicted to make room).
A failed `append_many` retains its batch and adjusts NEITHER
`_dropped_total` NOR `_alert_pending` on its own -- there is nothing
new to alert about merely because a retry is still pending, and the
ALREADY-pending alert (if any, from a genuine eviction) is independently
rate-limited below regardless of how often `flush()` itself is retried.

Alert-row EMISSION RATE is bounded independently of eviction/flush-retry
rate (N-2): `_alert_min_interval_s` (constructor parameter, matching the
composition root's own periodic-flush interval, default 2.0s) is a
hard floor under `_alert_backoff_s` -- no two alert attempts are ever
less than `_alert_min_interval_s` apart, "1 alert row attempt per flush
interval per process" even while eviction is ongoing. The backoff is
keyed to whether the underlying buffer FLUSH is currently succeeding
(`_flush_currently_failing`, updated by every `flush()` call), not to
whether the alert row's own INSERT succeeded: an alert row can itself
write successfully while the buffer flush keeps failing (evidence keeps
being evicted) -- in that case the backoff still grows, so a healthy
alert-write path does not let a broken buffer-flush path re-trigger a
fresh alert attempt every `_alert_min_interval_s` forever at the
fastest allowed rate; it backs off further, same as an outright alert
failure. The backoff only resets to the floor once the buffer flush
itself is observed healthy again.
```

## CH-0165

- moved from: `src/r2db_api/service.py` (`_PreCommitHook.commit_failed`)
- parent commit: `3a4c018`
- kind: comment

```
# D-2's error-row rule: best-effort from the response's point of
# view (the caller fails SERVICE_UNAVAILABLE regardless of whether
# this succeeds -- the data commit already failed either way) --
# any exception here is swallowed, never re-raised, so a backend's
# own `except psycopg.Error` clause always reaches its own `fail()`
# call next, not this method's failure.
```

## CH-0166

- moved from: `src/r2db_api/service.py` (`_PreCommitHook`)
- parent commit: `3a4c018`
- kind: docstring

```
Phase 4 (design D-2/D-10): the concrete `ApplicationAuditHook`
`DataService` builds per fail-closed-class request and hands to
`StorageBackend.transact`/`apply_schema` as `audit_hook`. Every field
the durable row needs (`event_class`/`request_id`/`application_id`/
`actor_type`/`actor_id`/`role`/`operation`/`target_kind`/`target_id`)
is already bound here at construction time -- the backend itself
supplies none of it, only the fail-closed/buffer-class decision (D-2's
normative rule: the confirmation choke for `transact`, unconditional
for `apply_schema`).
```

## CH-0167

- moved from: `src/r2db_api/service.py` (`MutationResult`)
- parent commit: `3a4c018`
- kind: comment

```
# Contract 1.7.0 (D-7, WP-2e): `outcome.request_id` -- this execution's
# own value for a real commit/dry_run, or the ORIGINAL execution's own
# value for an idempotency replay (`MutationOutcome.request_id`'s own
# comment). Never regenerated here.
```

## CH-0168

- moved from: `src/r2db_api/service.py` (`MutationResult`)
- parent commit: `3a4c018`
- kind: docstring

```
`DataService.mutate_result`'s own return shape, matching
`spec/data-service-api.v1.json`'s `MutationResult`. Mirrors the
`query`/`query_page` split (WP-4): `mutate` below stays byte-for-byte
backward compatible (a bare `int`, the affected count) for every
existing caller (`tests/test_foundation.py`, the in-process conformance
adapter); this richer shape reaches only the HTTP boundary, which needs
`assigned_addresses` to build the contract's own response. `entity` is
never present on any element here (contract: only the cross-entity
endpoint's own elements name their entity; this is the per-entity
endpoint's shape).

`committed`/`plan` (contract 1.7.0, D-4, WP-2b): before WP-2b, every
caller reaching this point had necessarily committed (an atomic batch
that failed partway through never returns anything, it raises), so
`http.post_mutate` hardcoded `committed: True` itself and this
dataclass carried no such field at all. `committed` now reports the
real decision (`False` only for a `dry_run` that reached the "would
succeed" decision); `plan` carries the deterministic token computed
for it -- `DataService.mutate_result` only ever sets `plan` on a
`dry_run` response (`None` for a real commit, D-4 (3): a real
response's shape stays otherwise unchanged from before this version).

`assigned_addresses` (review round F-6, `{scratchpad}/rulings-r4.md`):
`None` exactly on a `dry_run` response -- `http.post_mutate` omits the
key itself then, rather than carrying an empty list, matching the
contract's "does not carry" wording. A real commit always gets a list
(possibly empty, when the batch assigned no address), unchanged from
before this version.
```

## CH-0169

- moved from: `src/r2db_api/service.py` (`QueryPage`)
- parent commit: `3a4c018`
- kind: comment

```
# Contract 1.7.0 (D-7, WP-2e): the same `request_id` this query's own
# audit event (`_query_outcome`'s `_event` call) carries -- generated
# once, in `query_page` itself, before `_query_outcome` runs, so both
# this field and that audit event see the identical value.
```

## CH-0170

- moved from: `src/r2db_api/service.py` (`QueryPage`)
- parent commit: `3a4c018`
- kind: docstring

```
`DataService.query_page`'s own return shape, matching
`spec/data-service-api.v1.json`'s `QueryResult` (CCR-13 WP-4 introduced
`items`/`next_page`; WP-5 adds `revisions`, index-aligned with `items`,
now that `revision_preconditions` is declared `enabled`). `next_page`
is the opaque cursor for the next page (`QueryOutcome.next_cursor`,
`r2db_api.structured`), or `None` when this was the last page.
```

## CH-0171

- moved from: `src/r2db_api/service.py` (`<module>`)
- parent commit: `3a4c018`
- kind: comment

```
# Default cell factory (design D-1 step 2): builds the existing in-memory
# `ApplicationCell`, unchanged, so every caller that does not pass
# `cell_factory` gets exactly today's behavior. A deployment that wants
# `PostgresCell` (or any other `StorageBackend`) instead passes its own
# factory -- `DataService` itself never imports `postgres.py` or references
# PostgreSQL, keeping this module backend-agnostic (D-1: "in-memory backend
# and PostgreSQL backend pass through the same validation boundary" without
# either backend leaking into this facade).
```

## CH-0172

- moved from: `src/r2db_api/service.py` (`<module>`)
- parent commit: `3a4c018`
- kind: comment

```
# Phase 4 (design §7.4, review m-4): exponential backoff for the sticky
# overflow-alert retry, capped at 60s -- an unbounded equal-interval retry
# against a durably-failing sink would itself become a logging DoS (the
# same flow problem D-3 bounds for denials, recurring on the alert path).
# The FLOOR for this backoff is `_DEFAULT_AUDIT_FLUSH_INTERVAL_S`
# (`_AuditBuffer`'s own `alert_min_interval_s`, WP-2(a) fix round 2 review
# N-2), not a separate, smaller initial value -- no alert attempt is ever
# spaced closer together than the composition root's own flush cadence.
```

## CH-0173

- moved from: `src/r2db_api/service.py` (`<module>`)
- parent commit: `3a4c018`
- kind: comment

```
# Phase 4 (WP-2(a) fix round 3, review D-1): fixed, no-interpolation log
# messages for the denial-coalescer's own aggregate (repeat-count summary)
# row write path -- mirrors `_ALERT_WRITE_FAILED_LOG_MESSAGE`/`_ALERT_
# WRITE_RECOVERED_LOG_MESSAGE`'s identical state-transition-only discipline
# (N-2), applied to `_DenialCoalescer._note_aggregate_write_result`.
```

## CH-0174

- moved from: `src/r2db_api/service.py` (`<module>`)
- parent commit: `3a4c018`
- kind: comment

```
# Phase 10 WP-6a (design D-5(ii), contract 1.8.0): this plane's own region
# (ii) -- limit classes bound by in-memory, per-process state (`self.
# _rate_windows`/`self._active`, both below), the only classes whose
# `limit_enforcement` mapping actually depends on `process_ceiling`. Every
# other `ResourceLimits` class is either region (i) (request-scoped,
# unaffected regardless of process count) or region (iii)
# (`idempotency_entries`, bound in PostgreSQL -- `enforced` regardless of
# `process_ceiling`, design D-5(ii); the count lock itself is WP-6d-i's
# scope, supervisory ruling 2026-09-08, not this WP's).
```

## CH-0175

- moved from: `src/r2db_api/service.py` (`<module>`)
- parent commit: `3a4c018`
- kind: comment

```
# Phase 4 (design D-4): the bounded buffer's default capacity (implementation
# discretion per the design -- "既定 1000、実装裁量で設定可").
```

## CH-0176

- moved from: `src/r2db_api/service.py` (`<module>`)
- parent commit: `3a4c018`
- kind: comment

```
# Phase 4 (design D-3): the coalescing window (D-3/P4-D3, confirmed value).
```

## CH-0177

- moved from: `src/r2db_api/service.py` (`<module>`)
- parent commit: `3a4c018`
- kind: comment

```
# Phase 4 (design D-2/D-10): a `FoundationError.details` marker this
# module's own audit-hook/denial-routing code sets on a `SERVICE_UNAVAILABLE`
# it raises BECAUSE the durable audit pipeline itself just failed (a
# pre-commit sink failure, a post-commit `error`-row write, a coalesced-
# denial first-insert failure). `_event`'s own deny-dispatch checks this
# marker and skips routing such a denial through `_route_denial` again --
# without it, the generic `except FoundationError` handler every public
# method already has would treat this SERVICE_UNAVAILABLE as a brand-new
# denial needing its own durable write, producing a second (or third)
# durable row for what D-10 requires stays at most one (+ the D-2 error-row
# exception).
```

## CH-0178

- moved from: `src/r2db_api/service.py` (`<module>`)
- parent commit: `3a4c018`
- kind: comment

```
# Phase 4 (design PHASE4_DURABLE_AUDIT_SINK_V1.md D-3; WP-2(a) review J-2,
# supervisor ruling 2026-09-02): an INCLUSION set -- only a denial whose
# reason_code is one of these 6 (D-3's own range table, SI-14's minimal
# event class: authentication/authorization denial) is fail-closed/
# coalesced-durable. Every other reason_code -- D-3's originally-named 4
# non-durable codes (`VALIDATION_FAILED`/`LIMIT_EXCEEDED`/`CAPABILITY_
# UNSUPPORTED`/`NOT_FOUND`) AND everything else this facade can raise
# (`CONFLICT`, `PRECONDITION_FAILED`, `SERVICE_UNAVAILABLE`, `AUTH_STATE_
# UNAVAILABLE`, ...) -- is out of scope for durable/buffered recording
# (review N-2: buffering them would just let the flow problem D-3 exists to
# bound come back through the buffer instead). An exclusion-list reading
# (only the named 4 are non-durable, everything else durable) was this
# module's first implementation; the review's B-1 finding showed it lets a
# `SERVICE_UNAVAILABLE` produced by the audit pipeline's OWN failure re-enter
# as a "new" denial, writing a THIRD durable row for one operation (D-10's
# own prohibited case (ii)) -- switching to inclusion closes that path
# structurally (`SERVICE_UNAVAILABLE` was never in D-3's fail-closed list to
# begin with). `test_durable_denial_codes_match_the_design_d3_table`
# (`tests/test_application_audit.py`) fixes this set against D-3's table by
# name.
```

## CH-0179

- moved from: `src/r2db_api/service.py` (`<module>`)
- parent commit: `3a4c018`
- kind: comment

```
# `_coalesced_count`'s own comment (Phase 4 WP-2(b) review B-1) moved with
# it to `audit_counts.py` when that helper was extracted.
```
