# src/r2db_api/credential_store.py -- code-comment history (change set 5)

Companion for `src/r2db_api/credential_store.py` per `docs/code-history/README.md`.

## CH-0381

- moved from: `src/r2db_api/credential_store.py` (`<module>`)
- parent commit: `3adba35`
- kind: comment

```
# Opus review minor m-5: the control plane's own last-active-control-
# credential gate (design docs/design/DESTRUCTIVE_CONFIRMATION_V1.md R-3)
# takes a real `FOR UPDATE` lock across every control-credential row for
# the duration of `control_credentials_unit_of_work` (`PostgresControl
# CredentialStore.list_all_for_update`) -- the same kind of lock-holding
# transaction `postgres.py`'s own `_set_timeouts` already bounds with a
# `SET LOCAL lock_timeout` on the DATA plane, so the control plane needs
# the identical discipline: a request that would otherwise wait forever
# behind a stuck/slow concurrent transaction must instead fail
# deterministically. Reuses `ResourceLimits`'s own default `execution_ms`
# (5000ms) for consistency with the data plane's own default budget --
# `ControlPlaneLimits` has no `execution_ms`-shaped field of its own to
# derive this from (R-7's 3 control-plane resource classes are
# applications/credentials_per_application/control_requests_per_minute,
# none of which is a lock/statement-timeout bound), so this is a fixed
# constant here rather than a configurable one, unlike the data plane's
# per-request budget.
```

## CH-0383

- moved from: `src/r2db_api/credential_store.py` (`<module>`)
- parent commit: `3adba35`
- kind: comment

```
# Phase 6 WP-2 (design D-1(c)): `_SELECT_BY_VERIFIER` (the pre-WP-2
# digest-keyed lookup) is REMOVED, not merely unused -- authentication is
# now a locator lookup (`_SELECT_BY_ID`, below) followed by `compare_
# digest`, never a `WHERE verifier = ...` scan. `_SELECT_BY_ID` was
# already this store's `assert_active`/`canonical_context`/
# `application_id_for` lookup; `authenticate` now shares it too.
```

## CH-0384

- moved from: `src/r2db_api/credential_store.py` (`_execute`)
- parent commit: `3adba35`
- kind: docstring

```
The single execution choke point for this file -- mirrors `postgres.
py::_run`'s identical role there. Typed to accept only a composed
psycopg SQL object, never `str`, so a raw string cannot reach the
database from anywhere in this module (D-4).

Phase 4 WP-2(b): `params` now also accepts a `Mapping` (psycopg3's own
`%(name)s`-style binding) -- `PostgresAuditQueryStore.query`'s own
`audit_query` UNION statement below reuses several parameters (the
visibility-lag threshold, the cursor triple, the class filter) at
multiple positions in the composed SQL text, which named binding
expresses far more directly than repeating the same positional
placeholder object many times. Every pre-existing caller in this file
still passes a `Sequence`, unaffected.
```

## CH-0386

- moved from: `src/r2db_api/credential_store.py` (`PostgresCredentialStore.count_active_for_application`)
- parent commit: `3adba35`
- kind: docstring

```
`auth.CredentialStore.count_active_for_application`'s Postgres
counterpart (R-7 `credentials_per_application`: revoked rows are
never counted).
```

## CH-0388

- moved from: `src/r2db_api/credential_store.py` (`PostgresCredentialStore.rotate`)
- parent commit: `3adba35`
- kind: docstring

```
Not part of `auth.CredentialStore`'s call surface (that class has
no rotation concept at all) -- added here because `python -m
r2db_api.ops rotate-credential` (P2-D6) needs exactly this one extra
operation, and computing/writing a verifier is already this class's
own responsibility; duplicating that SQL a second time in `ops.py`
would only risk the two copies drifting apart. P2-D6: "同一
credential_id の verifier を差し替える" -- rotation reuses the
existing `credential_id`, `role`, and `application_slug`, replacing
only `verifier` (so the old secret stops authenticating and the new
one starts, with no other lifecycle state introduced). Unchanged by
WP-2: this method still does not check `revoked` (§8 M-2's finding
about this exact method -- see `auth.CredentialStore.rotate`'s
docstring for why the new in-memory `rotate` was written to match
this, not the other way around). `work` is required (round-2
ruling (A)).

Rework (coordinator follow-up, 2026-09-04 audit finding §3-A):
returns the composed bearer (`auth.compose_bearer_locator(
credential_id, secret)`) -- `ops.py cmd_rotate_credential` now uses
this return value verbatim instead of composing it itself.
```

## CH-0390

- moved from: `src/r2db_api/credential_store.py` (`validate_control_pepper_separation`)
- parent commit: `3adba35`
- kind: docstring

```
R-2: wherever a process' configuration carries *both* the
application-plane pepper (`R2DB_CREDENTIAL_PEPPER`) and the
control-plane pepper (`R2DB_CONTROL_CREDENTIAL_PEPPER`), the two values
must differ. An operator who (by mistake, e.g. copy-paste from one
secret-manager entry to both env var names) configures them identically
would make an application credential's verifier and a control
credential's verifier collide under the same underlying secret string --
silently punching a hole through R-2's "control credential storage is
unreadable from the application plane" wall via pepper reuse rather than
any table/grant mistake.

Called from `ops.py`'s control-credential ritual/break-glass command
constructors today -- design docs/design/R2DB_CCR14_CONTROL_PLANE_V1.md
§1 R-2 calls this "共通経路" (a shared path): a future composition root
that ever constructs both an application-plane and a control-plane store
in the same process must call this too, which is why this lives here
(imported by both `ops.py` and, in the future, `main.py`/`control_main.
py`) rather than being duplicated at each call site.
```

## CH-0392

- moved from: `src/r2db_api/credential_store.py` (`PostgresControlCredentialStore.unit_of_work`)
- parent commit: `3adba35`
- kind: comment

```
# Opus review minor m-5: `SET LOCAL lock_timeout`, mirroring
# `postgres.py`'s own `_set_timeouts` (data plane) -- scoped to
# this transaction only (discarded on commit/rollback, never
# leaking onto the next transaction this pooled connection is
# reused for). Bounds the last-active-control-credential gate's
# own `FOR UPDATE` lock wait (`list_all_for_update`) so a
# concurrent lock holder that never releases cannot wedge this
# transaction open indefinitely.
```

## CH-0393

- moved from: `src/r2db_api/credential_store.py` (`PostgresControlCredentialStore.authenticate`)
- parent commit: `3adba35`
- kind: docstring

```
Phase 6 WP-2 (design D-1(c)): locator-then-digest, mirroring
`PostgresCredentialStore.authenticate`'s own rewrite above -- see
that method's docstring for the full rationale. The former inline
`WHERE verifier = {ph}` lookup is gone; this now shares `_CONTROL_
SELECT_BY_ID` with `assert_active` below.
```

## CH-0394

- moved from: `src/r2db_api/credential_store.py` (`PostgresControlCredentialStore.add`)
- parent commit: `3adba35`
- kind: docstring

```
Only reachable through `ops.py` (connected as `r2dbsvc_control`)
-- `r2dbsvc_controlplane` (0006) is never granted INSERT on this
table at all, so calling this against a control-plane-process
connection fails at the database-privilege level (R-3), independent
of this Python-level restriction. `work` is required (round-2
ruling (A) -- see `PostgresCredentialStore.add`'s docstring for the
full history).

Phase 3.5 WP-4: `role` defaults to `"control"` (every pre-WP-4 caller
-- `bootstrap_control_credential`/`reset_control_credentials` --
is unaffected); `"audit"` is the one other accepted value, used only
by `issue_audit_credential_ceremony` below. The table's own `CHECK
(role IN ('control', 'audit'))` (0006, in-place WP-4 revision) is the
authoritative enforcement; this Python-level check exists only to
surface a clean `VALIDATION_FAILED` before ever reaching SQL.
```

## CH-0395

- moved from: `src/r2db_api/credential_store.py` (`PostgresControlCredentialStore.rotate`)
- parent commit: `3adba35`
- kind: docstring

```
R-5/§2 M-2: verifier replacement + `must_rotate = false` +
`updated_at` refresh, one statement. A revoked row is refused
(`VALIDATION_FAILED`) via the same `FOR UPDATE`-then-check pattern
`set_state` above uses, rather than trusting a bare `UPDATE ...
WHERE revoked = false` to have matched zero rows for the right
reason (that would return `NOT_FOUND` for an existing-but-revoked
row, indistinguishable from "no such credential" -- a strictly
worse error for the caller than the dedicated `VALIDATION_FAILED`
this gives instead). `work` is required (round-2 ruling (A)).

Rework (coordinator follow-up, 2026-09-04 audit finding §3-A):
returns the composed bearer -- `ops.py cmd_rotate_control_
credential` now uses this return value verbatim.
```

## CH-0396

- moved from: `src/r2db_api/credential_store.py` (`PostgresControlCredentialStore.has_any`)
- parent commit: `3adba35`
- kind: docstring

```
§8 M-6: bootstrap's existence check, real-row semantics -- see
`auth.ControlCredentialStore.has_any`'s identical docstring.

`work` is a **read-only**, optional parameter (this is not one of
the state-changing methods ruling (A) requires `work` on): when
omitted, this runs as a plain standalone read on its own pooled
connection, exactly as round 1 of this WP had it. When supplied
(MA-3, round-2 review: closing the TOCTOU gap between a standalone
existence check and the subsequent `add` -- two concurrent
bootstraps could both observe "no row" before either committed),
this executes on `work.connection` instead, so the check
participates in the caller's own transaction -- and, combined with
an advisory lock taken on that same connection before this is
called (`ops.py cmd_bootstrap`/`cmd_reset`), a second concurrent
ritual invocation blocks until the first commits or rolls back, and
then sees its row.
```

## CH-0397

- moved from: `src/r2db_api/credential_store.py` (`PostgresControlCredentialStore.revoke_all`)
- parent commit: `3adba35`
- kind: docstring

```
Reset's "revoke every existing control credential" step (R-5) --
see `auth.ControlCredentialStore.revoke_all`'s identical docstring.
`work` is required (round-2 ruling (A)).
```

## CH-0399

- moved from: `src/r2db_api/credential_store.py` (`PostgresControlCredentialStore.list_all_for_update`)
- parent commit: `3adba35`
- kind: docstring

```
Row-locking counterpart to `list_all` above, used exclusively by
`ControlPlaneService.revoke_credential`'s last-active-control-
credential destructive-confirmation gate (design docs/design/
DESTRUCTIVE_CONFIRMATION_V1.md R-3, WP-0 MA-2). `FOR UPDATE` with no
`WHERE` locks every row in this table for the remainder of `work`'s
transaction -- the gate's own count of active rows must not be able
to change between this read and the state-changing `UPDATE`
(`set_state`) that follows in the SAME transaction, closing the
TOCTOU window a standalone count-then-write would leave between two
concurrent revokes each independently observing "count = 2" and
both proceeding unconfirmed. A concurrent `rotate`/`set_state`
call's own single-row `SELECT ... FOR UPDATE` (see those methods
above) blocks against this same lock too, since it necessarily
locks a row this statement has already locked.

Phase 3.5 WP-4: `role` is now selected too -- the gate's own "active"
count (`ControlPlaneService.revoke_credential`) must count only
`role="control"` rows; an `"audit"` credential existing alongside the
sole active control credential must not be allowed to mask that
control credential as "not the last one" (an audit credential cannot
perform any control-plane management operation at all, so it does
not relieve the lockout the gate exists to prevent).
```

## CH-0400

- moved from: `src/r2db_api/credential_store.py` (`PostgresApplicationRegistry.register`)
- parent commit: `3adba35`
- kind: docstring

```
Registration-only `INSERT` -- every provisioning column (`database_
name`/`runtime_role`/`developer_role`/`provisioned_at`) is omitted, so
each stays `NULL`, satisfying 0006's two-state CHECK as a "registered,
not yet provisioned" row (R-4).
```

## CH-0402

- moved from: `src/r2db_api/credential_store.py` (`PostgresControlAuditSink.borrow_connection`)
- parent commit: `3adba35`
- kind: docstring

```
Q4 phase WP-1 rework (rulings-q4-wp12-rework.md sec.1): exposes
this sink's OWN pool so `platform_declarations.check_writer_role_
timeouts` can run its dual check on a connection whose login role
actually IS the `control_audit` writer role (`r2dbsvc_
controlplane`) -- a role setting only takes effect at login time,
so no other connection would observe this role's true effective
value (design D-1(c)).
```

## CH-0403

- moved from: `src/r2db_api/credential_store.py` (`PostgresControlAuditSink.events`)
- parent commit: `3adba35`
- kind: docstring

```
Read surface for tests/tooling connected with sufficient privilege
(`r2dbsvc_control`, never the control-plane process' own `r2dbsvc_
controlplane` role, which has no SELECT on this table at all -- R-3).
Design §0: "読み取りsurface(events())はin-memory/Postgres双方に用意
(WP-5のportcontrol_audit_events()とWP-6のaudit-reportが使う)".

Round-2 review MI-8: routed through `_execute` (D-4's single
execution choke point, like every other statement in this file) and
the module's own `psycopg.Error` -> `AUTH_STATE_UNAVAILABLE` (503)
discipline (`_fetch_or_503`'s pattern) -- this method previously
called `cur.execute` directly and let a connection failure propagate
as a raw `psycopg.Error`, the one read path in this file that had not
been brought under that discipline yet.

WP-5 round-2 review NIT-4: `ORDER BY recorded_at` alone is not a
total order -- `recorded_at` is `DEFAULT now()`, a single
transaction-start timestamp, so two events inserted by the same
transaction (a state-change row + nothing else shares a
transaction today, but this is a durability property this method
should not assume stays true forever) or by two transactions that
happen to commit within the same clock tick can tie. This became
load-bearing this WP: C-15 vector 2's own prefix assertion
(`after_audit[:len(before_audit)] == before_audit`) needs a stable,
repeatable ordering across the `before`/`after` calls, not merely
"some order consistent with `recorded_at`" -- `event_id` (the
primary key, application-generated per `AuditSink.append`) is the
deterministic tiebreaker.
```

## CH-0406

- moved from: `src/r2db_api/credential_store.py` (`PostgresApplicationAuditSink.append_many`)
- parent commit: `3adba35`
- kind: docstring

```
D-4's buffer flush: every buffered `audit.AuditEvent` in
`events` is written as one multi-row `INSERT` on one connection/
transaction -- either the whole batch commits or (on failure) none
of it does, exactly like `audit.ApplicationAuditSink.append_many`'s
in-memory all-or-nothing behaviour (D-10 parity). A `psycopg.Error`
propagates to the caller unchanged; `service.py`'s buffer-flush
logic treats a failed flush as lost events (D-4: buffer content is
a best-effort channel, the overflow-alert mechanism -- not a
per-batch retry queue -- is SI-14's "explicit operational alert"
answer to that loss).
```

### correction: 2026-09-30

- reason: R-115 WP-4a -- the in-memory buffer that called `append_many` is removed; the batch is no longer a buffer flush

old:
```
every buffered `audit.AuditEvent` in `events`
```

new:
```
every `audit.AuditEvent` in `events`
```

### correction: 2026-09-30

- reason: R-115 WP-4a -- the in-memory buffer that called `append_many` is removed; no buffer-flush logic treats a failed batch as lost events any more

old:
```
A `psycopg.Error` propagates to the caller unchanged; `service.py`'s buffer-flush logic treats a failed flush as lost events (D-4: buffer content is a best-effort channel, the overflow-alert mechanism -- not a per-batch retry queue -- is SI-14's "explicit operational alert" answer to that loss).
```

new:
```
A `psycopg.Error` propagates to the caller unchanged, so a failed batch is never silently treated as recorded (SI-14); `service.py` writes each event with `append` instead.
```

## CH-0407

- moved from: `src/r2db_api/credential_store.py` (`PostgresAuditQueryStore`)
- parent commit: `3adba35`
- kind: docstring

```
Phase 4 WP-2(b) (design D-5/D-6): `audit_query`'s Postgres reader --
the dedicated, SELECT-only `r2dbsvc_auditreader` role (migration
`0007_application_audit.sql` §1.3), reading BOTH `control_audit` and
`application_audit` over one connection (D-1(b): a single platform DB
is what makes this possible without an N-database fan-out). Never
shares a pool/DSN with any writer role or with `r2dbsvc_controlplane`
(D-5's own "別 DSN" requirement -- `r2dbsvc_controlplane` receives no
grant on either audit table at all, migration 0007 §1.3 note 5).

`InMemoryAuditQueryStore` (`audit_query.py`) is this class's in-memory
pair (D-10) -- both implement the same `AuditQueryReader` call surface
and are exercised by the identical parity test
(`test_in_memory_and_postgres_audit_query_semantics_have_parity`).
```
