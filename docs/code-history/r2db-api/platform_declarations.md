## CH-0860

- moved from: `src/r2db_api/platform_declarations.py` (`<module>`)
- parent commit: `56f51b0`
- kind: docstring

```
Q4 phase (design docs/design/Q4_DB_SIDE_SINGLE_TRUTH_V1.md D-1/D-2,
work order docs/work-orders/WORK_ORDER_Q4_DB_SIDE_SINGLE_TRUTH_V1.md WP-1;
rework round, supervisor rulings 2026-09-05 -- rulings-q4-wp12-rework.md
sec.1, rulings-q4-writer-roles.md D-2(h), q4-f3c-and-amendments.md; Agent C
isomorphism convergence pass, rulings-q4-wp12-rework.md sec.5):

Reads and validates the platform database's DB-side declarations --
`r2dbsvc_registry.platform_declarations` (`surfaces`,
`audit_coalescing_window_ms`, `audit_writer_roles`; migration `0008`;
`process_ceilings`, Phase 10 WP-6a, migration `0012`) -- and double-checks
a writer role's `pg_db_role_setting` timeout catalog entries against that
SAME connection's own effective `pg_settings` value (D-1(b)).

Reference-implementation module (supervisor ruling 2026-09-05,
`{scratchpad}/rulings-q4-wp12-rework.md` sec.1): every name, signature and
return type below is shared verbatim with MitateDB-api's own same-named
realization -- peer differences close entirely over the ARGUMENTS a
caller passes in (`schema`, `ops_module`, `migration`, `names`,
`declared_roles`), never over a literal `r2db`/`R2DB`/`mitatedb`/
`MITATEDB` string baked into a pinned function's own body. A handful of
message-building helpers below (`_f1_message`/`_f2_message`/`_f8_message`/
`_f13_message`'s own `schema` mention, `_f6_forward_message`/
`_f6_reverse_message`'s own env-var mention) instead reach for this
MODULE's own peer-local constants (`PEER_MODULE`, `MIGRATION_NUMBER`,
`MIGRATION_FILENAME`, `PROVISION_DSN_ENV`, `PEER_DIR`, `DEFAULT_SCHEMA`,
`CONTROL_PLANE_STATUS_ENV`) by bare name rather than taking them as
parameters -- those constants are peer-specific VALUES but peer-IDENTICAL
NAMES, so the referencing function body stays textually isomorphic across
peers even though it is never literally handed those values as arguments.

`current_user`-based role identification, NOT naming-convention-derived
role names (rulings-q4-writer-roles.md, rejected alternative (a)): which
role is a declared audit writer is read from this table's own
`audit_writer_roles` row (D-2(h)), never derived from `schema.removesuffix
("_registry") + "_api"` or any other string-rewrite convention -- that
convention is production-only and breaks under a throwaway-prefixed test
fixture, which is exactly why the previous (pre-rework) round of this
module was rejected.

Fail-fast only: every function here either returns a validated value or
raises `PlatformDeclarationError` -- always a STARTUP failure (composition
root), never surfaced through any HTTP response (design §3.8's own header
note, SI-10). The one cell-open-time, API-facing condition (F-12, D-3(f))
belongs to a LATER work package's own module, not this one.

Every function that touches PostgreSQL takes an already-open `conn`
(never a `dsn`) -- callers open/close their own connections. This matters
most for `check_writer_role_timeouts`: it must run on the SAME connection
the writer sink actually uses (login role = the writer role being
checked, since a role setting only takes effect at login time and `SET
ROLE` cannot substitute, design D-1(c)) -- `r2db_api.main`/
`r2db_api.control_main` borrow this connection from their own audit
sink's pool (`PostgresApplicationAuditSink.borrow_connection`/
`PostgresControlAuditSink.borrow_connection`).

Peer-local, independently maintained (no cross-peer sharing, requester
ruling 2026-09-03) -- this module's read/validate/derive/check helpers are
pinned isomorphic to MitateDB-api's own same-named realizations by
`_ISOMORPHIC_TARGETS` (`tests/test_audit_query.py`).
```

## CH-0861

- moved from: `src/r2db_api/platform_declarations.py` (`<module>`)
- parent commit: `56f51b0`
- kind: comment

```
#: This peer's own module path, named in every fail-fast message's "next
#: ops command" (design §3.8). Peer-local (no cross-peer sharing, requester
#: ruling 2026-09-03).
```

## CH-0862

- moved from: `src/r2db_api/platform_declarations.py` (`<module>`)
- parent commit: `56f51b0`
- kind: comment

```
# ---------------------------------------------------------------------------
# F-15 (Phase 10 WP-6a, design D-5(ii)): the `process_ceilings` row -- one
# combined check for "does the row exist and is it well-formed", the SAME
# treatment work order WP-6a's own §3 D-5(ii) reading calls for ("verify-
# declarations に足す番号は F-15" -- singular, unlike surfaces'
# existence/F-3 vs. shape/F-5 split). The row-existence check (inlined
# directly in `read_platform_declarations` below, as `"process_ceilings"
# not in rows` -- there is no standalone `require_process_ceilings_
# declared` function the way `require_control_surface_declared` exists for
# F-3c) and `validate_process_ceilings_value` (shape) both raise
# `code="F-15"` so `ops verify-declarations` (`_VERIFY_DECLARATIONS_EXIT_
# CODES`) needs exactly one new exit code, not two.
# ---------------------------------------------------------------------------
```

## CH-0863

- moved from: `src/r2db_api/platform_declarations.py` (`_role_setting_rows`)
- parent commit: `56f51b0`
- kind: docstring

```
Every `pg_db_role_setting` row for `role_name` that is either
database-independent (`setdatabase = 0`, the declaration itself,
design §1.5 finding 6) or scoped to THIS connection's own database
(`setdatabase = <this db's oid>`, F-11's own per-database override) --
the catalog query itself is restricted to `setdatabase IN (0, own db
oid)` (design D-1(c) amendment 2026-09-05), never every database on
the cluster. `pg_db_role_setting` is a world-readable shared catalog:
any connection can run this query regardless of its own login role.
```

## CH-0867

- moved from: `src/r2db_api/platform_declarations.py` (`<module>`)
- parent commit: `56f51b0`
- kind: comment

```
# Contract 1.7.0 (design docs/design/
# PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md D-1/D-6/D-5, work
# order §2 WP-2e F-3, `{scratchpad}/rulings-r3-r7-flip.md` F-3, WP-2e rework
# `{scratchpad}/audit-wp2e.md` D-2, ruling L-2 = (A)): a new `ops verify-
# declarations` check that the contract 1.7.0 "enabled" declaration is TRUE
# of the actual deployed state, not a second, redundant copy of `r2db_api.
# limits.ResourceLimits.__post_init__`'s own construction-time check on a
# `ResourceLimits` instance this check builds for itself.
#
# The pre-rework `check_contract_170_resource_limits` had exactly that
# flaw (audit finding D-2): it constructed its own default `ResourceLimits
# ()` and checked THAT instance, so (a) a broken default never reached this
# function at all -- `ResourceLimits.__post_init__` already raises
# `ValueError` at construction, before `_verify_declarations_checks` gets a
# chance to catch a `PlatformDeclarationError` -- and (b) a healthy default
# always passes. `PlatformDeclarationError(code="F-14")` could therefore
# never actually be raised through the real `ops verify-declarations` code
# path -- a dead check, "OK F-14" printed unconditionally with no signal
# behind it.
#
# `check_contract_170_declarations` replaces it with three checks, only the
# third of which is genuinely reachable through a real deployment's own
# state (the other two stay useful regression guards against a future code
# change, same honest scope `check_writer_role_timeouts` above documents
# for its own construction-time-only conditions):
#   (a) the SERVED capabilities document (the caller's own `capabilities()`
#       call, never rebuilt here) actually declares `constraint_
#       declarations`/`dry_run`/`idempotency`/`request_budget` `enabled`.
#   (b) M-7 (`{scratchpad}/audit-wp2e-2.md` R-7): the SAME served
#       capabilities document's own `limits` block (never a fresh
#       `ResourceLimits()` constructed here -- that residual flaw, caught
#       by the closure audit, was the same "unreachable through a real
#       deployment" bug as the pre-rework function had for (a)) carries a
#       positive `enum_members`/`idempotency_entries`/`idempotency_
#       retention_ms`.
#   (c) EVERY registered application's own per-application upgrade ledger
#       (R-2/R-5, migrations `0009`/`0010`/`0011`) already carries every
#       number this shipped version requires (`applied_upgrade_numbers_
#       by_application`, `required_upgrade_numbers` -- the caller passes
#       `r2db_api.platform_upgrades.PLATFORM_UPGRADE_NUMBERS`). This is the
#       one part of F-14 a real deployment can actually fail: an
#       application whose database has not yet run `ops upgrade-
#       applications` makes the "enabled" declaration false for that
#       application's own traffic, regardless of what the platform-wide
#       capability document says -- so this fails closed per-application,
#       not just once for the whole platform.
```

## CH-0864

- moved from: `src/r2db_api/platform_declarations.py` (`<module>`)
- parent commit: `56f51b0`
- kind: comment

```
# ---------------------------------------------------------------------------
# F-16 (Phase 10 WP-4f, supervisor ruling 2026-09-09, following the WP-4e
# conformance investigation's own finding -- see that WP's report): every
# PostgreSQL role this deployment's own processes pool connections against
# must have a `CONNECTION LIMIT` (`pg_roles.rolconnlimit`) of `-1`
# (unlimited) or at least that role's own worst-case simultaneous
# connection count ("pool 合計") -- otherwise a burst of real concurrent
# requests hits PostgreSQL's own hard `FATAL: too many connections for
# role` refusal instead of the declared 429/503 the contract promises
# (WP-4e's own measured `r2dbsvc_controlplane` finding: 4 stores x fixed
# `pool_size` 4 = 16, against a `CONNECTION LIMIT` of only 10 -- already a
# real production defect with a single control-plane process, no test
# harness involved).
#
# Role IDENTITY is read from REAL GRANTS (`information_schema.role_table_
# grants` on the fixed, migration-defined `application_audit`/
# `control_audit` table names), never from a schema/role-name string-
# rewrite convention: this module's own header already rejects that
# technique for writer-role identification (rulings-q4-writer-roles.md,
# rejected alternative (a)) precisely because it is production-only and
# breaks under a throwaway-prefixed test fixture -- the SAME reasoning
# applies here. `application_audit`/`control_audit` are schema-qualified
# object names fixed by this migration set's own DDL (never deployment-
# chosen), so querying grants on them is reading real, already-declared
# database state, not guessing a name.
#
# Runtime/developer role names, unlike the platform-plane roles above, ARE
# read directly off `<schema>.applications` -- also real stored data, not a
# derived name.
#
# Deliberately excludes `r2dbsvc_control` (short-lived, one-shot CLI/
# provisioning connections only -- no persistent pool, and no stored
# declaration this check could read to derive a floor for it, the same
# "out of scope" category as F-1/F-2/F-12, `_verify_declarations_checks`'s
# own trailing disclosure line). This is an EXPLICIT exclusion
# (`_table_owner`, below), not merely "no grants match its identity" --
# `r2dbsvc_control` is the role every migration in this set runs `CREATE
# TABLE application_audit`/`CREATE TABLE control_audit` AS (0007/0006's
# own "WHO RUNS THIS" headers), so as the OWNER of both tables it
# implicitly holds INSERT and SELECT on both without ever appearing as a
# `grantee` row -- meaning it would otherwise match all three platform-
# plane role classes below at once (measured 2026-09-10, WP-4 integration
# review M-1).
# ---------------------------------------------------------------------------
```

## CH-0865

- moved from: `src/r2db_api/platform_declarations.py` (`check_role_connection_limits`)
- parent commit: `56f51b0`
- kind: docstring

```
F-16: raises `PlatformDeclarationError(code="F-16")` for the FIRST
role (in the deterministic order built below) whose `pg_roles.
rolconnlimit` is neither `-1` nor at least its own computed floor.
`pool_size` is the caller's own declared per-role pool ceiling
(`r2db_api.limits.role_pool_size(thread_limit)`, the real per-process
simultaneous-borrow ceiling) -- this function takes it as a plain
argument rather than constructing its own default instance, so a
deployment that has genuinely raised its real pool size is checked
against ITS OWN real floor, not a silently-stale code-level default.

design D-3 (5): `role_pool_size(thread_limit)`
sizes ONE process' own pool; `pg_roles.rolconnlimit` is a
CLUSTER-WIDE cap shared by every one of `process_ceilings.<plane>`
processes that pools a connection against that role, each with its
own `pool_size`-sized pool -- this function multiplies every floor
it computes by the process count of the plane that role belongs to:
`process_ceilings.data` for the `api` class and every application's
runtime/developer role, `process_ceilings.control` for the
`controlplane` and `auditreader` classes. A caller multiplying
`pool_size` itself before calling in would count the process count
twice, since this function already multiplies by it -- every caller
passes its own plain, un-multiplied `pool_size` and the SAME
`process_ceilings` this process read from the declarations row.

Checks exactly the role classes `0013_role_connection_limits.sql`
(this peer) / the sibling peer's own same-numbered migration raises:
the platform-plane `<...>_api`/`<...>_controlplane`/`<...>_
auditreader` roles (module-level floor constants above) and every
REGISTERED application's own runtime/developer roles (floor =
`pool_size * process_ceilings.data`, one store each, Phase 10 WP-8a).
A role with no grants matching any of the three platform-plane shapes
above (identity unknown to this check) is silently skipped, never
flagged -- this check only ever verifies roles it can positively
identify, exactly like every other read in this module never guesses
at what it cannot observe.

Phase 10 WP-4g (supervisor ruling 2026-09-09): `role_classes`/
`application_slugs` let a caller narrow this check to exactly the
role(s) ITS OWN process pools connections against, instead of every
role this whole platform has -- `ops verify-declarations`'s own
aggregate call (the pre-existing, unchanged default: both `None`)
still checks everything platform-wide, but `r2db_api.main`/`r2db_api.
control_main`'s own startup fail-fast calls (added this WP) pass
these so an UNRELATED application's or the SIBLING plane's own
misconfigured role never blocks a process that never pools a
connection against it at all. `role_classes`, when given, is any
subset of `{"api", "controlplane", "auditreader"}` (`None` -- the
default -- means all three, unchanged pre-existing behavior).
`application_slugs`, when given (not `None`), restricts the runtime/
developer role check to exactly the named slugs -- an EMPTY sequence
means "check no application role at all" (`control_main`'s own case:
that process serves no application); `None` (the default) means every
registered application, unchanged pre-existing behavior.
```

## CH-0866

- moved from: `src/r2db_api/platform_declarations.py` (`check_role_connection_limits`)
- parent commit: `56f51b0`
- kind: comment

```
# M-1 (WP-4 integration review 2026-09-10): a role can legitimately
# match MORE than one platform-plane class below (a role granted
# INSERT on both audit tables, or INSERT on one and SELECT on both,
# for example) -- `max(...)` keeps the STRICTEST floor that role is
# actually subject to instead of whichever class happened to assign
# last. `_table_owner` exclusion keeps the table-owning operator role
# (`r2dbsvc_control`, never a real pooled role -- see the module
# header above) from being misidentified as matching all three via
# its implicit owner ACL.
```
