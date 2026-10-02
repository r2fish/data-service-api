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

### correction: 2026-09-30

- reason: R-115 WP-4a -- ordinary data-operation events are written synchronously before the response and the in-memory buffer is removed; the `allow` bullet no longer describes a buffer

old:
```
`outcome == "allow"`: buffer-class
```

new:
```
`outcome == "allow"` (`data_operation` only) or `"replayed"` (any class): written synchronously to the durable sink before the caller's response is returned
```

### correction: 2026-09-30

- reason: R-115 WP-4a -- ordinary data-operation events are written synchronously before the response and the in-memory buffer is removed; a replay of any class is durable, and a sink failure is fail-closed

old:
```
`query`/`catalog` always reach here (they never pass through the confirmation choke), and `mutate` reaches here only when its batch did NOT (`already_durable=False`).
```

new:
```
`query`/`catalog`, a `mutate` whose backend did not already record it (`already_durable=False`), and every replay. A sink failure raises `SERVICE_UNAVAILABLE` (fail-closed), so a response is only ever returned for an operation whose event is durable.
```

### correction: 2026-09-30

- reason: R-115 WP-4a -- ordinary data-operation events are written synchronously before the response and the in-memory buffer is removed; no buffered record exists any more

old:
```
without any durable/buffered record at all;
```

new:
```
without any durable record at all;
```

### correction: 2026-09-30

- reason: R-115 WP-4b -- an `allow` of any class but `authentication` is written by `_event` unless the backend hook already recorded it; a schema operation no longer passes a constant for "already recorded"

old:
```
`outcome == "allow"` (`data_operation` only) or `"replayed"` (any class)
```

new:
```
`outcome == "allow"` (any class but `authentication`) or `"replayed"` (any class)
```

### correction: 2026-09-30

- reason: R-115 WP-5a -- the process-local coalescing router is removed; a fail-closed-class refusal is counted in the platform database's refusal window before its response is returned

old:
```
goes through the coalescing denial router (which may itself raise `SERVICE_UNAVAILABLE`).
```

new:
```
is counted in the durable refusal window before its response is returned (a count that cannot be recorded raises `SERVICE_UNAVAILABLE`).
```

### correction: 2026-10-01

- reason: R-115 -- the coalescing denial router and its first-insert write are gone; a refusal is counted in the platform database's refusal window before its response

old:
```
a coalesced-denial first-insert failure) -- routing it through `_route_denial` again would be a second (or third) durable write
```

new:
```
a refusal-window count that could not be recorded) -- counting it in the refusal window again would be a second (or third) durable write
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

### correction: 2026-09-30

- reason: R-115 WP-4a -- ordinary data-operation events are written synchronously before the response and the in-memory buffer is removed; a catalog read's event is written before its result is returned

old:
```
`catalog` never passes through the confirmation choke -- always buffer-class.
```

new:
```
`catalog` writes its event synchronously, before the result is returned.
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

### correction: 2026-09-16

- reason: R-22 change set 0i (ruling Z0i-4d) -- `tests/test_constraints_declaration.py` never reads `.revision` off this method's result (only off `cell.apply_schema`); `tests/test_foundation.py` is the direct caller that does

old:
```
Every pre-1.7.0 direct caller of this method (`tests/test_foundation.py`, `tests/test_constraints_declaration.py`) reads `.revision` off the result; the in-process conformance adapter's own `hasattr(result, "revision")` branch already handles a non-`int` result unchanged (it never assumed `int`).
```

new:
```
Every pre-1.7.0 direct caller of this method (`tests/test_foundation.py`; `tests/test_constraints_declaration.py` reads `.revision` only off `cell.apply_schema`) reads `.revision` off the result; the in-process conformance adapter's own `hasattr(result, "revision")` branch already handles a non-`int` result unchanged (it never assumed `int`).
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

### correction: 2026-09-30

- reason: R-115 WP-4a -- ordinary data-operation events are written synchronously before the response and the in-memory buffer is removed; no buffer-class event exists

old:
```
(buffer-class OR the legacy in-memory sink `_event` itself unconditionally appends to)
```

new:
```
(durable OR the legacy in-memory sink `_event` itself unconditionally appends to)
```

### correction: 2026-09-30

- reason: R-115 WP-4a -- ordinary data-operation events are written synchronously before the response and the in-memory buffer is removed; the already-durable signal is the hook's own `fired` flag, and `_event` writes the row itself when the backend did not

old:
```
`outcome.destructive` reports whether the backend's pre-commit hook already durably recorded this batch -- `already_durable` tells `_event` to skip the buffer-class enqueue in that case (at most one durable row per operation).
```

new:
```
`hook.fired` reports whether the backend's pre-commit hook already durably recorded this batch -- `already_durable` tells `_event` to skip its own synchronous write in that case (at most one durable row per operation); a backend that never called the hook leaves the row to `_event`, which writes it before the response.
```

### correction: 2026-09-30

- reason: R-115 WP-4a -- ordinary data-operation events are written synchronously before the response and the in-memory buffer is removed; a fresh commit's hook is no longer destructive-only

old:
```
THIS event the way a genuinely destructive fresh commit's hook already wrote one for its own.
```

new:
```
THIS event the way a fresh commit's hook already wrote one for its own.
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

### correction: 2026-09-30

- reason: R-115 WP-4a -- ordinary data-operation events are written synchronously before the response and the in-memory buffer is removed; the backend calls the hook for every real batch

old:
```
the hook is only ever USED by the backend when this batch turns out to pass through the confirmation choke (a confirmed `delete`) -- building it unconditionally here is cheap (no I/O happens until/unless `pre_commit()` is actually called) and keeps this call site identical regardless of what the batch turns out to contain, matching `schema`'s own unconditional hook below.
```

new:
```
the backend calls the hook as the last statement of every real (non-`dry_run`) batch, so the `allow` row is durable before the data commit -- the same path `schema`'s own hook below takes.
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

### correction: 2026-09-15

- reason: R-37 WP-3c -- the `_mutate_outcome` request-shape checks moved to `request_shape.py`; the pointer gets a 40c position bracket

old:
```
`transaction` is never a contract-level *default* -- `None` here means the caller's own request object never carried the key at all (both `http.post_mutate` and the in-process port omit the kwarg rather than resolving it to `"atomic"` before this call). `resolved_transaction` is used for every behavioural decision (the capability gate below); the RAW `transaction` value (still `None` when omitted) is what `plan_request` below reflects, so a request that carried `transaction: "atomic"` explicitly digests differently from one that omitted the key entirely, even though both behave identically otherwise.
```

new:
```
`transaction` is never a contract-level *default* -- `None` here means the caller's own request object never carried the key at all (both `http.post_mutate` and the in-process port omit the kwarg rather than resolving it to `"atomic"` before this call). `resolved_transaction` is used for every behavioural decision (the capability gate below); the RAW `transaction` value (still `None` when omitted) is what `plan_request` below (in `service.py`) reflects, so a request that carried `transaction: "atomic"` explicitly digests differently from one that omitted the key entirely, even though both behave identically otherwise.
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

### correction: 2026-09-30

- reason: R-115 WP-4a -- ordinary data-operation events are written synchronously before the response and the in-memory buffer is removed; a query's event is written before its result is returned

old:
```
`query` never passes through the confirmation choke -- always buffer-class.
```

new:
```
`query` writes its event synchronously, before the result is returned.
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

### correction: 2026-09-25

- reason: keyset paging work order WORK_ORDER_PHASE11_KEYSET_PAGING_V1 §4 WP-5 (design PHASE11_KEYSET_PAGING_V1 D-1 (2a), D-3 (9)) -- a second paragraph documents the new `page_size=None` default resolution (least of the contract maximum, declared `limits.result_items`, and the request's own `budget.result_items`). The `WP-4` pointer on the first paragraph's `(CCR-13 WP-4)` was already dropped at this change set's own base (§4.1 (6) label stripping, untracked before this correction)

old:
```
which `http.post_query` uses.
```

new:
```
which `http.post_query` uses.

Keyset paging (design D-1 (2a), D-3 (9)): `page_size` of `None` (the default, and what a request that omits `page.size` resolves to) is answered as though it carried the least of the contract maximum, this deployment's own declared `limits.result_items`, and the request's own `budget.result_items` where it carries one -- resolved once, in `_query_outcome` below, after `budget` has already narrowed the effective limits.
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

### correction: 2026-09-15

- reason: R-37 WP-3b -- capability-document assembly moved to `capabilities_document.py`; the pointer gets a 40c position bracket

old:
```
`surfaces` is an optional key -- present only when this instance was constructed with one (`__init__`'s own comment on `self._surfaces`). Never a `"surfaces": None` entry.
```

new:
```
`surfaces` is an optional key -- present only when this instance was constructed with one (`__init__`'s own comment on `self._surfaces`) (in `service.py`). Never a `"surfaces": None` entry.
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

### correction: 2026-09-28

- reason: design docs/design/MULTI_PROCESS_WORKER_V0_1.md D-3 (4) -- region (ii) (`requests_per_minute`/`concurrency`) no longer follows a single `process_ceiling`-only rule; `capabilities_document.resolve_limit_enforcement` reads `enforced` unconditionally once each class' own shared mechanism is configured across every worker, and falls back to the single-process rule only when it is not.

old:
```
Region (ii) (`requests_per_minute`/`concurrency` -- bound by in-memory, per-process state, `self._rate_windows`/`self._active`) reads `enforced` only while `process_ceiling == 1` and `deployment_required` once it is `>= 2` (contract 1.8.0's own enforcement-scope definition: a per-process bound is `enforced` for the whole deployment only while exactly one process may serve this plane's base URL).
```

new:
```
Region (ii) (`requests_per_minute`/`concurrency`, each resolved by `capabilities_document.resolve_limit_enforcement`) reads `enforced` unconditionally once its own mechanism is configured across every worker this supervisor runs (the PostgreSQL-backed rate row for `requests_per_minute`; the host-shared slot directory, with this supervisor's workers at the declared ceiling, for `concurrency`) -- otherwise it keeps contract 1.8.0's own single-process enforcement-scope rule, `enforced` only while `process_ceiling == 1`.
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

### correction: 2026-09-15

- reason: R-22 fact-fix commit 1715e18 -- the three capabilities are now `enabled`, not `unavailable`, and the schema fields they reference are declared below this comment, not above

old:
```
Contract 1.7.0 (subordinate ruling 12, D-1 (3)): three new capabilities, honestly declared `unavailable` until each one's own capability WP flips it, in the SAME commit as the provisional gate that rejects every field it governs (`schema`/`mutate_result`/`_query_outcome` above, `http.py`'s `post_mutate`/`post_query`) -- P-3 (宣言と挙動は同一コミット).
```

new:
```
Contract 1.7.0 (subordinate ruling 12): each of the three capabilities below is declared `enabled` in the same commit that removes the provisional gate rejecting every field it governs (`schema`/`mutate_result`/`_query_outcome` below, `http.py`'s `post_mutate`/`post_query`) -- P-3 (宣言と挙動は同一コミット).
```

### correction: 2026-09-15

- reason: R-37 WP-3b -- capability-document assembly moved to `capabilities_document.py`; the pointer gets a 40c position bracket

old:
```
Contract 1.7.0 (subordinate ruling 12): each of the three capabilities below is declared `enabled` in the same commit that removes the provisional gate rejecting every field it governs (`schema`/`mutate_result`/`_query_outcome` below, `http.py`'s `post_mutate`/`post_query`) -- P-3 (宣言と挙動は同一コミット).
```

new:
```
Contract 1.7.0 (subordinate ruling 12): each of the three capabilities below is declared `enabled` in the same commit that removes the provisional gate rejecting every field it governs (`schema`/`mutate_result`/`_query_outcome` below, `http.py`'s `post_mutate`/`post_query`) (in `service.py`) -- P-3 (宣言と挙動は同一コミット).
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

### correction: 2026-09-15

- reason: R-37 WP-3b -- capability-document assembly moved to `capabilities_document.py`; the pointer gets a 40c position bracket

old:
```
reflects this instance's own constructor-injected deployer declaration -- never hardcoded (see __init__'s comment on this field).
```

new:
```
reflects this instance's own constructor-injected deployer declaration -- never hardcoded (see __init__'s comment on this field) (in `service.py`).
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

### correction: 2026-09-25

- reason: Phase 11 WP-3 (docs/design/PHASE11_MIN_COMMON_PROFILE_V1.md D-4/D-5) -- this host also declares contract 1.9.0 in the same commit as `common_baseline`'s operations all being genuinely executable and `operation_catalog_url` actually serving the byte-identical derived catalog

old:
```
Phase 10 WP-6a/pair-closing (design D-5 (v)): flipped again to 1.8.0 in the SAME commit as this host's own `process_ceilings` mapping (D-5 (ii)) -- the version's one unconditional obligation, `limit_enforcement_scoped_to_deployment_behind_base_url` -- never ahead of the behavior it declares.
```

new:
```
Phase 10 WP-6a/pair-closing: flipped again to 1.8.0 in the SAME commit as this host's own `process_ceilings` mapping -- the version's one unconditional obligation, `limit_enforcement_scoped_to_deployment_behind_base_url` -- never ahead of the behavior it declares.

This host also declares contract 1.9.0 in the same commit as `common_baseline`'s operations all being genuinely executable (no status below moves) and `operation_catalog_url` (below) actually serving the byte-identical derived catalog (`http.py::get_operation_catalog`) -- the version's two unconditional obligations, never ahead of the behavior they declare. `control_plane.py`'s own control-plane document flips in the same commit too (C-19's cross-plane version match).
```

### correction: 2026-09-25

- reason: this host also declares contract 1.10.0 in the same commit as its own keyset paging behavior (query results totally ordered, a stateless page.cursor with next_page, cursor binding, and a page.size default)

old:
```
This host also declares contract 1.9.0 in the same commit as `common_baseline`'s operations all being genuinely executable (no status below moves) and `operation_catalog_url` (below) actually serving the byte-identical derived catalog (`http.py::get_operation_catalog`) -- the version's two unconditional obligations, never ahead of the behavior they declare. `control_plane.py`'s own control-plane document flips in the same commit too (C-19's cross-plane version match).
```

new:
```
This host also declares contract 1.9.0 in the same commit as `common_baseline`'s operations all being genuinely executable (no status below moves) and `operation_catalog_url` (below) actually serving the byte-identical derived catalog (`http.py::get_operation_catalog`) -- the version's two unconditional obligations, never ahead of the behavior they declare. `control_plane.py`'s own control-plane document flips in the same commit too (C-19's cross-plane version match).

This host also declares contract 1.10.0 in the same commit as its own keyset paging behavior -- query results totally ordered, a stateless page.cursor with next_page, cursor binding, and a page.size default -- 1.10.0's own conditional obligations, bound while structured_query stays enabled here, never ahead of the behavior they declare.
```

### correction: 2026-09-25

- reason: R-110 (undeclared-field refusal alignment, subordinate ruling 16) -- this host also declares contract 1.11.0 in the same commit as its own undeclared-field refusal alignment across select/where/order_by/mutation-values

old:
```
This host also declares contract 1.10.0 in the same commit as its own keyset paging behavior -- query results totally ordered, a stateless page.cursor with next_page, cursor binding, and a page.size default -- 1.10.0's own conditional obligations, bound while structured_query stays enabled here, never ahead of the behavior they declare.
```

new:
```
This host also declares contract 1.10.0 in the same commit as its own keyset paging behavior -- query results totally ordered, a stateless page.cursor with next_page, cursor binding, and a page.size default -- 1.10.0's own conditional obligations, bound while structured_query stays enabled here, never ahead of the behavior they declare.

This host also declares contract 1.11.0 in the same commit as its own undeclared-field refusal alignment -- a select entry, a where predicate's field, an order_by entry's field, or a mutation's values key that names a field this entity does not declare is refused with VALIDATION_FAILED, violated_declaration request_schema and field naming the position -- 1.11.0's own unconditional obligation, never ahead of the behavior it declares.
```

### correction: 2026-09-30

- reason: roadmap R-114 (contract 1.12.0, subordinate ruling 17) -- this host declares 1.12.0 in the same commit as the contract text; no behavior change

old:
```
This host also declares contract 1.11.0 in the same commit as its own undeclared-field refusal alignment -- a select entry, a where predicate's field, an order_by entry's field, or a mutation's values key that names a field this entity does not declare is refused with VALIDATION_FAILED, violated_declaration request_schema and field naming the position -- 1.11.0's own unconditional obligation, never ahead of the behavior it declares.
```

new:
```
This host also declares contract 1.11.0 in the same commit as its own undeclared-field refusal alignment -- a select entry, a where predicate's field, an order_by entry's field, or a mutation's values key that names a field this entity does not declare is refused with VALIDATION_FAILED, violated_declaration request_schema and field naming the position -- 1.11.0's own unconditional obligation, never ahead of the behavior it declares. This host declares contract 1.12.0 with no behavior change: 1.12.0 only withdraws the contract's own word for the shape of the `audit_requests_per_minute` window.
```

### correction: 2026-09-30

- reason: roadmap R-115 (contract 1.13.0, subordinate ruling 18) -- this host declares 1.13.0 in the same commit as its own audit durability behavior

old:
```
This host also declares contract 1.11.0 in the same commit as its own undeclared-field refusal alignment -- a select entry, a where predicate's field, an order_by entry's field, or a mutation's values key that names a field this entity does not declare is refused with VALIDATION_FAILED, violated_declaration request_schema and field naming the position -- 1.11.0's own unconditional obligation, never ahead of the behavior it declares. This host declares contract 1.12.0 with no behavior change: 1.12.0 only withdraws the contract's own word for the shape of the `audit_requests_per_minute` window.
```

new:
```
This host also declares contract 1.11.0 in the same commit as its own undeclared-field refusal alignment -- a select entry, a where predicate's field, an order_by entry's field, or a mutation's values key that names a field this entity does not declare is refused with VALIDATION_FAILED, violated_declaration request_schema and field naming the position -- 1.11.0's own unconditional obligation, never ahead of the behavior it declares. This host declares contract 1.12.0 with no behavior change: 1.12.0 only withdraws the contract's own word for the shape of the `audit_requests_per_minute` window. This host also declares contract 1.13.0 in the same commit as its own audit durability behavior -- a service process that stops without completing a graceful shutdown loses neither the audit event of an operation whose response was already returned nor the count of any denial occurrence whose response was already returned -- 1.13.0's own unconditional obligation, never ahead of the behavior it declares.
```

### correction: 2026-10-01

- reason: roadmap R-108 (contract 1.14.0, subordinate ruling 19) -- this host declares 1.14.0 in the same commit as the contract text; no behavior change

old:
```
This host also declares contract 1.11.0 in the same commit as its own undeclared-field refusal alignment -- a select entry, a where predicate's field, an order_by entry's field, or a mutation's values key that names a field this entity does not declare is refused with VALIDATION_FAILED, violated_declaration request_schema and field naming the position -- 1.11.0's own unconditional obligation, never ahead of the behavior it declares. This host declares contract 1.12.0 with no behavior change: 1.12.0 only withdraws the contract's own word for the shape of the `audit_requests_per_minute` window. This host also declares contract 1.13.0 in the same commit as its own audit durability behavior -- a service process that stops without completing a graceful shutdown loses neither the audit event of an operation whose response was already returned nor the count of any denial occurrence whose response was already returned -- 1.13.0's own unconditional obligation, never ahead of the behavior it declares.
```

new:
```
This host also declares contract 1.11.0 in the same commit as its own undeclared-field refusal alignment -- a select entry, a where predicate's field, an order_by entry's field, or a mutation's values key that names a field this entity does not declare is refused with VALIDATION_FAILED, violated_declaration request_schema and field naming the position -- 1.11.0's own unconditional obligation, never ahead of the behavior it declares. This host declares contract 1.12.0 with no behavior change: 1.12.0 only withdraws the contract's own word for the shape of the `audit_requests_per_minute` window. This host also declares contract 1.13.0 in the same commit as its own audit durability behavior -- a service process that stops without completing a graceful shutdown loses neither the audit event of an operation whose response was already returned nor the count of any denial occurrence whose response was already returned -- 1.13.0's own unconditional obligation, never ahead of the behavior it declares. This host declares contract 1.14.0 with no behavior change: 1.14.0 states how a client forms a request and reads a response, and this host's responses already carry what its obligations (a) and (b) name; obligation (c) applies only where a deployment declares an operation_catalog_url other than the derived one.
```

### correction: 2026-10-03

- reason: roadmap R-118 (contract 1.15.0, subordinate ruling 20) -- this host declares 1.15.0 in the same commit as the contract text; no behavior change

old:
```
This host also declares contract 1.11.0 in the same commit as its own undeclared-field refusal alignment -- a select entry, a where predicate's field, an order_by entry's field, or a mutation's values key that names a field this entity does not declare is refused with VALIDATION_FAILED, violated_declaration request_schema and field naming the position -- 1.11.0's own unconditional obligation, never ahead of the behavior it declares. This host declares contract 1.12.0 with no behavior change: 1.12.0 only withdraws the contract's own word for the shape of the `audit_requests_per_minute` window. This host also declares contract 1.13.0 in the same commit as its own audit durability behavior -- a service process that stops without completing a graceful shutdown loses neither the audit event of an operation whose response was already returned nor the count of any denial occurrence whose response was already returned -- 1.13.0's own unconditional obligation, never ahead of the behavior it declares. This host declares contract 1.14.0 with no behavior change: 1.14.0 states how a client forms a request and reads a response, and this host's responses already carry what its obligations (a) and (b) name; obligation (c) applies only where a deployment declares an operation_catalog_url other than the derived one.
```

new:
```
This host also declares contract 1.11.0 in the same commit as its own undeclared-field refusal alignment -- a select entry, a where predicate's field, an order_by entry's field, or a mutation's values key that names a field this entity does not declare is refused with VALIDATION_FAILED, violated_declaration request_schema and field naming the position -- 1.11.0's own unconditional obligation, never ahead of the behavior it declares. This host declares contract 1.12.0 with no behavior change: 1.12.0 only withdraws the contract's own word for the shape of the `audit_requests_per_minute` window. This host also declares contract 1.13.0 in the same commit as its own audit durability behavior -- a service process that stops without completing a graceful shutdown loses neither the audit event of an operation whose response was already returned nor the count of any denial occurrence whose response was already returned -- 1.13.0's own unconditional obligation, never ahead of the behavior it declares. This host declares contract 1.14.0 with no behavior change: 1.14.0 states how a client forms a request and reads a response, and this host's responses already carry what its obligations (a) and (b) name; obligation (c) applies only where a deployment declares an operation_catalog_url other than the derived one. This host declares contract 1.15.0 with no behavior change: 1.15.0 only rewrites the contract's retention clause for the `endpoints.audit_query` alias, which this host keeps serving unchanged on its control surface (`control_http.py`).
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

### correction: 2026-09-15

- reason: R-37 WP-3b -- capability-document assembly moved to `capabilities_document.py`; the pointer gets a 40c position bracket

old:
```
CCR-13 WP-5b: the WP-2-through-WP-5 provisional gate (design R2DB_CCR13_STORAGE_V1.md §3) is removed in this same commit (see `query`/`mutate`/`schema`/`catalog` below) -- this declaration update is what makes that removal honest rather than a new C-12 "declared unavailable, executes anyway" gap.
```

new:
```
CCR-13 WP-5b: the WP-2-through-WP-5 provisional gate (design R2DB_CCR13_STORAGE_V1.md §3) is removed in this same commit (see `query`/`mutate`/`schema`/`catalog` below) (in `service.py`) -- this declaration update is what makes that removal honest rather than a new C-12 "declared unavailable, executes anyway" gap.
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

### correction: 2026-09-30

- reason: R-115 WP-4a -- ordinary data-operation events are written synchronously before the response and the in-memory buffer is removed; the hook fires for every real `transact` batch, not only a confirmed delete

old:
```
supplies none of it, only the fail-closed/buffer-class decision (D-2's normative rule: the confirmation choke for `transact`, unconditional for `apply_schema`).
```

new:
```
supplies none of it, only the moment (every real batch for `transact`, unconditional for `apply_schema`).
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

### correction: 2026-09-15

- reason: R-37 WP-3a -- `MutationResult` moved to `service_results.py`; the pointer gets a 40c position bracket

old:
```
Mirrors the `query`/`query_page` split (WP-4): `mutate` below stays byte-for-byte backward compatible (a bare `int`, the affected count) for every existing caller (`tests/test_foundation.py`, the in-process conformance adapter); this richer shape reaches only the HTTP boundary, which needs `assigned_addresses` to build the contract's own response.
```

new:
```
Mirrors the `query`/`query_page` split (WP-4): `mutate` below (in `service.py`) stays byte-for-byte backward compatible (a bare `int`, the affected count) for every existing caller (`tests/test_foundation.py`, the in-process conformance adapter); this richer shape reaches only the HTTP boundary, which needs `assigned_addresses` to build the contract's own response.
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

### correction: 2026-09-15

- reason: R-37 WP-3b -- capability-document assembly moved to `capabilities_document.py`; the pointer gets a 40c position bracket

old:
```
Phase 10 WP-6a (design D-5(ii), contract 1.8.0): this plane's own region (ii) -- limit classes bound by in-memory, per-process state (`self._rate_windows`/`self._active`, both below), the only classes whose `limit_enforcement` mapping actually depends on `process_ceiling`.
```

new:
```
Phase 10 WP-6a (design D-5(ii), contract 1.8.0): this plane's own region (ii) -- limit classes bound by in-memory, per-process state (`self._rate_windows`/`self._active`, both below) (in `service.py`), the only classes whose `limit_enforcement` mapping actually depends on `process_ceiling`.
```

### correction: 2026-09-28

- reason: design docs/design/MULTI_PROCESS_WORKER_V0_1.md D-3 (4) -- `_IN_MEMORY_PROCESS_WIDE_LIMIT_CLASSES` (the frozenset this comment described) is deleted; `capabilities_document.resolve_limit_enforcement` now decides region (ii) enforcement per class from how each is wired, not from a fixed in-memory-only set, so the note is reduced to what region (ii) still names, moved beside that function.

old:
```
Phase 10 WP-6a (design D-5(ii), contract 1.8.0): this plane's own region (ii) -- limit classes bound by in-memory, per-process state (`self._rate_windows`/`self._active`, both below) (in `service.py`), the only classes whose `limit_enforcement` mapping actually depends on `process_ceiling`.
```

new:
```
design D-5(ii), contract 1.8.0: region (ii) is `requests_per_minute`/`concurrency` -- the two `ResourceLimits` classes `resolve_limit_enforcement` below governs (both admitted by `DataService` in `service.py`), the only ones whose `limit_enforcement` mapping depends on how each is wired rather than on `process_ceiling` alone.
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

### correction: 2026-10-01

- reason: R-115 -- the coalescing denial router and its first-insert write are gone; a refusal is counted in the platform database's refusal window before its response, and the marker keeps a failed count from being counted again

old:
```
a coalesced-denial first-insert failure). `_event`'s own deny-dispatch checks this marker and skips routing such a denial through `_route_denial` again
```

new:
```
a refusal-window count that could not be recorded). `_event`'s own deny-dispatch checks this marker and skips counting such a denial in the refusal window again
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

### correction: 2026-09-30

- reason: R-115 WP-4b -- ordinary data-operation events are written synchronously before the response and the in-memory buffer is removed; no buffered record exists any more

old:
```
Every other reason_code -- D-3's originally-named 4 non-durable codes (`VALIDATION_FAILED`/`LIMIT_EXCEEDED`/`CAPABILITY_UNSUPPORTED`/`NOT_FOUND`) AND everything else this facade can raise (`CONFLICT`, `PRECONDITION_FAILED`, `SERVICE_UNAVAILABLE`, `AUTH_STATE_UNAVAILABLE`, ...) -- is out of scope for durable/buffered recording (review N-2: buffering them would just let the flow problem D-3 exists to bound come back through the buffer instead).
```

new:
```
Every other reason_code -- D-3's originally-named 4 non-durable codes (`VALIDATION_FAILED`/`LIMIT_EXCEEDED`/`CAPABILITY_UNSUPPORTED`/`NOT_FOUND`) AND everything else this facade can raise (`CONFLICT`, `PRECONDITION_FAILED`, `SERVICE_UNAVAILABLE`, `AUTH_STATE_UNAVAILABLE`, ...) -- is out of scope for durable recording (N-2: recording them would just let the flow problem exists to bound come back).
```

