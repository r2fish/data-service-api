## CH-0542

- moved from: `src/mitatedb_api/capabilities_document.py` (`build_capabilities_document`)
- parent commit: `0fee6e52cc81da1178f06ed88e0a12260ee705ac`
- kind: comment

```
# Phase 4 WP-3(b) (P4-D4, contract `versioning.version_
# binding`), flipped to 1.5.0 in Phase 5 WP-3 (design D-1,
# subordinate ruling 10 item 1): unconditional -- every
# deployment of this data-plane host declares 1.5.0 now,
# whether or not the CONTROL host alongside it has AUDIT DSN
# configured (`audit_query` stays `unavailable` right below,
# unchanged: this host never provides it, D-5's own
# "declaration = real behavior" rule -- design docs/design/
# PHASE4_DURABLE_AUDIT_SINK_V1.md §7.5 "data-plane ホスト
# (不変)"). `operations`/`target_kinds` are NOT declared here
# -- this host's own `audit_query` stays `unavailable`, and
# declaring a vocabulary for a surface this host never
# provides would contradict declare-the-hazard (design D-1).
# Phase 6 WP-3 (design D-1/D-2/D-3, subordinate ruling 11):
# flipped to 1.6.0 -- same commit as `surfaces` (already
# present, WP-3 D-2), the declared-type registry, and this
# capability's own flip immediately below (declaration and
# real behaviour land together, unconditionally -- every
# deployment of this data-plane host declares 1.6.0 now).
#
# Phase 9 WP-3e (design D-1 (5)/(7), F-1): flipped to 1.7.0 --
# SAME commit as this WP's own R-3 (`errors.details_
# vocabulary`'s 4-key form on every VALIDATION_FAILED/
# CAPABILITY_UNSUPPORTED this peer emits) and R-7
# (`request_id` on every successful `QueryResult`/
# `MutationResult`/`SchemaOperationResult`) implementation --
# the two 1.7.0 UNCONDITIONAL obligations (`versioning.
# version_binding`'s own "(a)"/"(b)" pair). D-1 (7): a peer
# must never flip its own declared `contract_version` ahead
# of the real behavior it claims -- C-21/C-25's own version-
# gated `xfail(strict=True)` is the machine-enforced form of
# that rule (this WP's own report measures both sides of it:
# the pre-flip state with R-3/R-7 behavior already wired in
# but this literal still `1.6.0`, C-21/C-25 XPASS(strict) RED
# on this peer's 2 plugs; this flip landing in the SAME
# commit as R-3/R-7 is what makes that measurement moot in
# the delivered state).
#
# Flipped again to 1.8.0 in phase 10 WP-6b/pair-closing (design
# D-5 (v)): the SAME commit as this host's own `process_
# ceilings` mapping (D-5 (ii)) -- never ahead of the behavior
# it declares.
```

### correction: 2026-09-25

- reason: Phase 11 WP-3 (docs/design/PHASE11_MIN_COMMON_PROFILE_V1.md D-4/D-5) -- this host also declares contract 1.9.0 in the same commit as `common_baseline`'s operations all being genuinely executable and `operation_catalog_url` actually serving the byte-identical derived catalog

old:
```
Flipped again to 1.8.0 in phase 10 WP-6b/pair-closing (design D-5 (v)): the SAME commit as this host's own `process_ceilings` mapping (D-5 (ii)) -- never ahead of the behavior it declares.
```

new:
```
Flipped again to 1.8.0 in phase 10 WP-6b/pair-closing (design D-5 (v)): the SAME commit as this host's own `process_ceilings` mapping (D-5 (ii)) -- never ahead of the behavior it declares.

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

This host also declares contract 1.10.0 in the same commit as its own keyset paging behavior -- query results totally ordered, a stateless page.cursor with next_page, cursor binding, and a page.size default -- 1.10.0's own conditional obligations, bound while structured_query stays declared other than unavailable (partial) here, never ahead of the behavior they declare.
```

### correction: 2026-09-25

- reason: R-110 (undeclared-field refusal alignment, subordinate ruling 16, acceptance audit observation O4) -- this host also declares contract 1.11.0 in the same commit as its own undeclared-field refusal alignment across all five positions the contract names (the values position names itself by key, not by index; the mutation where predicate field is the fifth position)

old:
```
This host also declares contract 1.10.0 in the same commit as its own keyset paging behavior -- query results totally ordered, a stateless page.cursor with next_page, cursor binding, and a page.size default -- 1.10.0's own conditional obligations, bound while structured_query stays declared other than unavailable (partial) here, never ahead of the behavior they declare.
```

new:
```
This host also declares contract 1.10.0 in the same commit as its own keyset paging behavior -- query results totally ordered, a stateless page.cursor with next_page, cursor binding, and a page.size default -- 1.10.0's own conditional obligations, bound while structured_query stays declared other than unavailable (partial) here, never ahead of the behavior they declare.

This host also declares contract 1.11.0 in the same commit as its own undeclared-field refusal alignment across all five positions the contract names -- a select entry names its own index (select/<i>), matching where/order_by/mutation-where, and a mutation's values key names itself (operations/<i>/values/<name>) -- each refused with VALIDATION_FAILED, violated_declaration request_schema and field naming the position -- 1.11.0's own unconditional obligation, never ahead of the behavior it declares.
```

### correction: 2026-09-30

- reason: roadmap R-114 (contract 1.12.0, subordinate ruling 17) -- this host declares 1.12.0 in the same commit as the contract text; no behavior change

old:
```
This host also declares contract 1.11.0 in the same commit as its own undeclared-field refusal alignment across all five positions the contract names -- a select entry names its own index (select/<i>), matching where/order_by/mutation-where, and a mutation's values key names itself (operations/<i>/values/<name>) -- each refused with VALIDATION_FAILED, violated_declaration request_schema and field naming the position -- 1.11.0's own unconditional obligation, never ahead of the behavior it declares.
```

new:
```
This host also declares contract 1.11.0 in the same commit as its own undeclared-field refusal alignment across all five positions the contract names -- a select entry names its own index (select/<i>), matching where/order_by/mutation-where, and a mutation's values key names itself (operations/<i>/values/<name>) -- each refused with VALIDATION_FAILED, violated_declaration request_schema and field naming the position -- 1.11.0's own unconditional obligation, never ahead of the behavior it declares. This host declares contract 1.12.0 with no behavior change: 1.12.0 only withdraws the contract's own word for the shape of the `audit_requests_per_minute` window.
```

### correction: 2026-09-30

- reason: roadmap R-115 (contract 1.13.0, subordinate ruling 18) -- this host declares 1.13.0 in the same commit as its own audit durability behavior

old:
```
This host also declares contract 1.11.0 in the same commit as its own undeclared-field refusal alignment across all five positions the contract names -- a select entry names its own index (select/<i>), matching where/order_by/mutation-where, and a mutation's values key names itself (operations/<i>/values/<name>) -- each refused with VALIDATION_FAILED, violated_declaration request_schema and field naming the position -- 1.11.0's own unconditional obligation, never ahead of the behavior it declares. This host declares contract 1.12.0 with no behavior change: 1.12.0 only withdraws the contract's own word for the shape of the `audit_requests_per_minute` window.
```

new:
```
This host also declares contract 1.11.0 in the same commit as its own undeclared-field refusal alignment across all five positions the contract names -- a select entry names its own index (select/<i>), matching where/order_by/mutation-where, and a mutation's values key names itself (operations/<i>/values/<name>) -- each refused with VALIDATION_FAILED, violated_declaration request_schema and field naming the position -- 1.11.0's own unconditional obligation, never ahead of the behavior it declares. This host declares contract 1.12.0 with no behavior change: 1.12.0 only withdraws the contract's own word for the shape of the `audit_requests_per_minute` window. This host also declares contract 1.13.0 in the same commit as its own audit durability behavior -- a service process that stops without completing a graceful shutdown loses neither the audit event of an operation whose response was already returned nor the count of any denial occurrence whose response was already returned -- 1.13.0's own unconditional obligation, never ahead of the behavior it declares.
```

### correction: 2026-10-01

- reason: roadmap R-108 (contract 1.14.0, subordinate ruling 19) -- this host declares 1.14.0 in the same commit as the contract text; no behavior change

old:
```
This host also declares contract 1.11.0 in the same commit as its own undeclared-field refusal alignment across all five positions the contract names -- a select entry names its own index (select/<i>), matching where/order_by/mutation-where, and a mutation's values key names itself (operations/<i>/values/<name>) -- each refused with VALIDATION_FAILED, violated_declaration request_schema and field naming the position -- 1.11.0's own unconditional obligation, never ahead of the behavior it declares. This host declares contract 1.12.0 with no behavior change: 1.12.0 only withdraws the contract's own word for the shape of the `audit_requests_per_minute` window. This host also declares contract 1.13.0 in the same commit as its own audit durability behavior -- a service process that stops without completing a graceful shutdown loses neither the audit event of an operation whose response was already returned nor the count of any denial occurrence whose response was already returned -- 1.13.0's own unconditional obligation, never ahead of the behavior it declares.
```

new:
```
This host also declares contract 1.11.0 in the same commit as its own undeclared-field refusal alignment across all five positions the contract names -- a select entry names its own index (select/<i>), matching where/order_by/mutation-where, and a mutation's values key names itself (operations/<i>/values/<name>) -- each refused with VALIDATION_FAILED, violated_declaration request_schema and field naming the position -- 1.11.0's own unconditional obligation, never ahead of the behavior it declares. This host declares contract 1.12.0 with no behavior change: 1.12.0 only withdraws the contract's own word for the shape of the `audit_requests_per_minute` window. This host also declares contract 1.13.0 in the same commit as its own audit durability behavior -- a service process that stops without completing a graceful shutdown loses neither the audit event of an operation whose response was already returned nor the count of any denial occurrence whose response was already returned -- 1.13.0's own unconditional obligation, never ahead of the behavior it declares. This host declares contract 1.14.0 with no behavior change: 1.14.0 states how a client forms a request and reads a response, and this host's responses already carry what its obligations (a) and (b) name; obligation (c) applies only where a deployment declares an operation_catalog_url other than the derived one.
```

### correction: 2026-10-03

- reason: roadmap R-118 (contract 1.15.0, subordinate ruling 20) -- this host declares 1.15.0 in the same commit as the contract text; no behavior change

old:
```
This host also declares contract 1.11.0 in the same commit as its own undeclared-field refusal alignment across all five positions the contract names -- a select entry names its own index (select/<i>), matching where/order_by/mutation-where, and a mutation's values key names itself (operations/<i>/values/<name>) -- each refused with VALIDATION_FAILED, violated_declaration request_schema and field naming the position -- 1.11.0's own unconditional obligation, never ahead of the behavior it declares. This host declares contract 1.12.0 with no behavior change: 1.12.0 only withdraws the contract's own word for the shape of the `audit_requests_per_minute` window. This host also declares contract 1.13.0 in the same commit as its own audit durability behavior -- a service process that stops without completing a graceful shutdown loses neither the audit event of an operation whose response was already returned nor the count of any denial occurrence whose response was already returned -- 1.13.0's own unconditional obligation, never ahead of the behavior it declares. This host declares contract 1.14.0 with no behavior change: 1.14.0 states how a client forms a request and reads a response, and this host's responses already carry what its obligations (a) and (b) name; obligation (c) applies only where a deployment declares an operation_catalog_url other than the derived one.
```

new:
```
This host also declares contract 1.11.0 in the same commit as its own undeclared-field refusal alignment across all five positions the contract names -- a select entry names its own index (select/<i>), matching where/order_by/mutation-where, and a mutation's values key names itself (operations/<i>/values/<name>) -- each refused with VALIDATION_FAILED, violated_declaration request_schema and field naming the position -- 1.11.0's own unconditional obligation, never ahead of the behavior it declares. This host declares contract 1.12.0 with no behavior change: 1.12.0 only withdraws the contract's own word for the shape of the `audit_requests_per_minute` window. This host also declares contract 1.13.0 in the same commit as its own audit durability behavior -- a service process that stops without completing a graceful shutdown loses neither the audit event of an operation whose response was already returned nor the count of any denial occurrence whose response was already returned -- 1.13.0's own unconditional obligation, never ahead of the behavior it declares. This host declares contract 1.14.0 with no behavior change: 1.14.0 states how a client forms a request and reads a response, and this host's responses already carry what its obligations (a) and (b) name; obligation (c) applies only where a deployment declares an operation_catalog_url other than the derived one. This host declares contract 1.15.0 with no behavior change: 1.15.0 only rewrites the contract's retention clause for the `endpoints.audit_query` alias, which this host keeps serving unchanged on its control surface (`control_http.py`).
```
