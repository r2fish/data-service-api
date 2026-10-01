# src/mitatedb_api/platform_declarations.py -- code-comment history

Companion for `src/mitatedb_api/platform_declarations.py` per `docs/code-history/README.md`.

## CH-0550

- moved from: `src/mitatedb_api/platform_declarations.py` (`check_role_connection_limits`)
- parent commit: `ddf9c73`
- kind: docstring

```
F-16: raises `PlatformDeclarationError(code="F-16")` for the FIRST
role (in the deterministic order built below) whose `pg_roles.
rolconnlimit` is neither `-1` nor at least its own computed floor.
`pool_size` is the caller's own per-process pool ceiling (`config.
role_pool_size(thread_limit)`, the real per-process simultaneous-
borrow ceiling) -- this function takes it as a plain argument rather
than reading `MITATEDB_THREAD_LIMIT` itself, so a deployment that has
genuinely raised its thread limit is checked against ITS OWN real
floor, not a silently-stale code-level default.

design docs/design/MULTI_PROCESS_WORKER_V0_1.md D-3 (5): `pool_size`
sizes ONE process' own pool; `pg_roles.rolconnlimit` is a
CLUSTER-WIDE cap shared by every one of `process_ceilings.<plane>`
processes that connects against that role -- this function
multiplies every floor it computes by the process count of the plane
that role belongs to: `process_ceilings.data` for the `api` class and
every application's runtime/developer role, `process_ceilings.
control` for the `controlplane` and `auditreader` classes. Every
caller passes its own plain, un-multiplied `pool_size` and the SAME
`process_ceilings` it read from the declarations row.

Checks exactly the role classes `0012_role_connection_limits.sql`
(this peer) raises: the platform-plane `<...>_api`/`<...>_
controlplane`/`<...>_auditreader` roles (module-level floor constants
above) and every PROVISIONED application's own runtime/developer roles
(floor = `pool_size * process_ceilings.data`, the same floor r2db-
api's sibling uses; this peer's own per-application demand is two
persistent connections per process, one per role, which this floor
covers). A role with no grants matching any of the three
platform-plane shapes above (identity unknown to this check) is
silently skipped, never flagged.

Phase 10 WP-4g (supervisor ruling 2026-09-09, peer-symmetric with
r2db-api's own same-numbered addition): `role_classes`/
`application_ids` let a caller narrow this check to exactly the
role(s) ITS OWN process pools connections against, instead of every
role this whole platform has -- `ops verify-declarations`'s own
aggregate call (the pre-existing, unchanged default: both `None`)
still checks everything platform-wide, but `mitatedb_api.main`/
`mitatedb_api.control_composition`'s own startup fail-fast calls
(added this WP) pass these so an UNRELATED application's or the
SIBLING plane's own misconfigured role never blocks a process that
never pools a connection against it at all. `role_classes`, when
given, is any subset of `{"api", "controlplane", "auditreader"}`
(`None` -- the default -- means all three, unchanged pre-existing
behavior). `application_ids`, when given (not `None`), restricts the
runtime/developer role check to exactly the named ids -- an EMPTY
sequence means "check no application role at all"
(`control_composition`'s own case: that process serves no
application); `None` (the default) means every registered
application, unchanged pre-existing behavior.
```

### correction: 2026-10-01

- reason: each served application's backend now holds one pool per role instead of two persistent connections

old:
```
this peer's own per-application demand is two persistent connections per process, one per role, which this floor covers
```

new:
```
this peer's own per-application demand is one pool per role of up to `pool_size` connections per process, which this floor covers
```
