# Common conformance conditions (v1 foundation)

These conditions are implementation-independent. An adapter may expose an
equivalent operation; endpoint names and storage topology are not tested here.

| ID | Condition | Invariants | Evidence | Status |
|---|---|---|---|---|
| C-00 | A credential for Application A has no path to B or control/provisioning authority. | SI-00, SI-02, SI-07 | platform topology evidence plus negative adapter test | not yet executable (common suite) -- peer-local evidence only: `r2db-api/tests/test_topology.py` (`test_topology_has_all_planes_and_denies_application_escape`, `test_deployment_skeleton_declares_denied_privileged_egress`); `MitateDB-api` topology/control-plane evidence is TBD per `security/CONTROL_MAPPING.md` |
| C-01 | Application and role come only from authenticated credential state; request scope/role fields cannot alter them. | SI-01, SI-06 | scope-tampering test | executable (three adapters) -- `conformance-tests/test_c01_scope_binding.py`, `@pytest.mark.condition("C-01")`; runs against `r2db-api` (in-process), `r2db-api-http` (real HTTP boundary + PostgreSQL), and `MitateDB-api` |
| C-02 | Runtime cannot execute schema/development or control operations. | SI-02, SI-03 | privilege-negative test | not yet executable (common suite) -- peer-local evidence only, both peers: `r2db-api/tests/test_foundation.py::test_runtime_developer_separation_and_structured_validation`; `MitateDB-api/tests/test_foundation.py::FoundationTests::test_developer_schema_and_runtime_crud` |
| C-03 | SQL/native command text and syntax-smuggling identifiers are rejected; supported values cross a binding boundary. | SI-04, SI-05 | structured input/injection test | executable (three adapters) -- `conformance-tests/test_c03_structured_injection.py`, `@pytest.mark.condition("C-03")`; runs against `r2db-api` (in-process), `r2db-api-http` (real HTTP boundary + PostgreSQL), and `MitateDB-api` |
| C-04 | Unsupported operations fail before execution and public errors are safe, structured diagnostics. | SI-05, SI-10, SI-15 | error probe | not yet executable (common suite) -- peer-local evidence only: `r2db-api/tests/test_foundation.py::test_malformed_inputs_fail_with_safe_foundation_errors`; `MitateDB-api` SI-10 (error/information non-disclosure) evidence is TBD per `security/CONTROL_MAPPING.md`, so peer coverage here is partial |
| C-05 | All applicable resource classes have finite, discoverable bounds and over-bound requests terminate deterministically. | SI-08 | boundary test | not yet executable (common suite) -- peer-local evidence only, both peers, and MitateDB-api's execution-time/concurrency/rate bounds remain unimplemented per `security/CONTROL_MAPPING.md` |
| C-06 | Destructive operations require explicit semantics and authority; ambiguous requests do not execute. | SI-09 | destructive-negative test | not yet executable (common suite) -- peer-local evidence only, both peers; the `VALID_CONFIRMATION` sentinel protocol (design section 10.1) exists on the port for this condition but no common `test_c06_*` suite has been written yet |
| C-07 | Atomic operations commit wholly or roll back; retries use declared idempotency/preconditions. | SI-11 | fault/rollback test | not yet executable (common suite) -- peer-local evidence only, both peers: `r2db-api/tests/test_foundation.py::test_atomic_rollback_and_explicit_destructive_operation`; `MitateDB-api/tests/test_foundation.py::FoundationTests::test_transaction_rolls_back` |
| C-08 | Revoked/disabled credentials, applications, and sessions stop authorizing within the published finite bound; unavailable state fails closed. | SI-13, SI-15 | revoke/retry test | executable (three adapters) -- `conformance-tests/test_c08_revocation_boundary.py`, `@pytest.mark.condition("C-08")`; runs against `r2db-api` (in-process), `r2db-api-http` (real HTTP boundary + PostgreSQL), and `MitateDB-api` |
| C-09 | Security events are attributable and immutable to application callers; secrets, SQL, and row values are absent. Audit query requires control/audit authority. | SI-10, SI-14 | audit event test and platform sink evidence | not yet executable (common suite) -- peer-local evidence only, both peers (preliminary for `MitateDB-api`); no external append-only audit sink is implemented or evidenced for either peer per `security/CONTROL_MAPPING.md` |
| C-10 | Application clients cannot obtain DB credentials, private management authority, or bypass-enabling configuration. | SI-12 | response/configuration review | not yet executable (common suite) -- document-level evidence only (response/configuration review); `r2db-api` additionally has partial peer-local evidence (structured-package/topology review, contract smoke test), `MitateDB-api` evidence is TBD per `security/CONTROL_MAPPING.md` |
| C-11 | A peer's published discovery/catalog documents conform to the contract's schema (`CapabilityDocument` / `CatalogDocument` + `EntityDescriptor`), and every declared capability name is a member of `capability_status.defined`. | SI-08, SI-15 | document schema/vocabulary conformance test | executable (three adapters) -- `conformance-tests/test_c11_document_conformance.py`, `@pytest.mark.condition("C-11")`; runs against `r2db-api` (in-process), `r2db-api-http` (real HTTP boundary + PostgreSQL), and `MitateDB-api`. Validated with a self-contained schema-subset checker, `conformance-tests/schema_check.py` (unit-tested in `conformance-tests/test_schema_check.py`) |
| C-12 | Capability declarations agree with observed behavior: a declared operation executes (positive control); an undeclared operation is refused with `CAPABILITY_UNSUPPORTED` before execution and leaves state unchanged. | SI-15, SI-05 | capability/behavior agreement test | executable (three adapters) -- `conformance-tests/test_c12_capability_agreement.py`, `@pytest.mark.condition("C-12")`; runs against `r2db-api`, `r2db-api-http`, and `MitateDB-api`; exercises `insert`/`update`/`upsert` (`delete` is left to C-06's future destructive-operation suite) and the `application_catalog` declaration against `catalog_document()` |
| C-13 | Credential revocation is terminal: after revoke, no control-plane surface on the peer can re-activate that credential, and `authenticate` remains refused. | SI-13 | revocation-terminality test | executable (three adapters) -- `conformance-tests/test_c13_revocation_terminality.py`, `@pytest.mark.condition("C-13")`; runs against `r2db-api`, `r2db-api-http`, and `MitateDB-api`, exercising every vector `credential_reactivation_vectors()` declares |
| C-14 | Control-plane authority boundary: an application credential is fail-closed against every control endpoint; a control credential is refused on data/schema endpoints; an in-band `role=control` issuance request is refused with `CAPABILITY_UNSUPPORTED` (plan B). | SI-00, SI-02, SI-03 | privilege-boundary test | not yet executable (common suite) -- neither peer implements a control-plane surface yet (`r2db-api`'s `python -m r2db_api.ops` remains an out-of-band CLI, not an in-band endpoint; `MitateDB-api` has no control-plane HTTP surface at all). To be made executable once a `/control/v1`-equivalent surface exists on a peer |
| C-15 | Bootstrap/reset lifecycle: bootstrap cannot re-run while a control credential already exists; reset revokes every existing control credential; the first-issued credential is non-permanent. | SI-13, SI-14 | lifecycle test | not yet executable (common suite) -- same gap as C-14: no peer implements the control-plane lifecycle surface these clauses govern yet |
| C-16 | Cross-entity atomicity: one atomic mutation unit is scoped to a single request, every named entity's validation precedes any entity's execution, and `batch_entities` has a finite, discoverable bound. | SI-08, SI-11 | cross-entity atomicity test | not yet executable (common suite) -- `cross_entity_mutation` is `unavailable` on both peers (no executable `POST /v1/data/mutations` path exists yet). One vector of this condition is already effectively enforced on `r2db-api`'s HTTP surface today: a per-entity mutation request's body cannot smuggle its own `entity` field past the entity the URL path already names -- this is exercised as a C-01 `tamper_vectors()` vector on the `r2db-api-http` plug only (`http_smuggled_entity_field_in_mutation_operation_body`, kind `request_field_scope`, disposition `must_deny`), not yet as its own C-16 test, and not (yet) evidenced for `MitateDB-api` |

"executable (three adapters)" means: the ID is asserted via
`@pytest.mark.condition(...)` on tests in `conformance-tests/`, those tests
are parametrized over every registered adapter in `registry.json`, and
`test_conditions_register.py` verifies the marker/row correspondence in
both directions. Three adapters are currently registered, covering two
peers: `r2db-api` (in-process, driving `DataService` directly over an
in-memory cell), `r2db-api-http` (the same peer's real ASGI HTTP boundary
in front of `PostgresCell` against a real local PostgreSQL server), and
`MitateDB-api`. `r2db-api` registering two adapters is deliberate, not
redundant: the same condition IDs re-run unchanged against a materially
different deployed shape of the same peer (see
`conformance-tests/README.md`, "Adding a new peer"). Every other status
here is an honest statement that the condition currently has, at most,
document-level narrative or a peer-local test suite that runs against one
implementation's own harness -- not a common-suite test runnable against
every adapter through the port defined in
`docs/design/CONFORMANCE_ADAPTER_V1.md`. Peer-local evidence is real
evidence (see `security/CONTROL_MAPPING.md`), but it does not by itself
establish that every adapter satisfies the condition the same way, which is
what "executable" certifies here.

## Taxonomies used by the executable conditions

The six conditions marked `executable (three adapters)` above are built on
shared taxonomies defined normatively in `conformance-tests/adapter.py`
(design `docs/design/CONFORMANCE_ADAPTER_V1.md` sections 4.3 and 4.4, and
`docs/design/CONFORMANCE_CONDITIONS_V1_1.md` section 2 for the C-13
addition below). This is what "executable" actually covers for C-01, C-03,
and C-13: coverage of these taxonomies, not just "some test ran and
passed."

### Tamper-vector taxonomy (design section 4.3)

Every `TamperVector` an adapter declares has a `kind` (one of
`forged_scope_object`, `role_elevation`, `request_field_scope`,
`cross_application_handle`) and a `disposition`:

- `must_deny` -- attempting the vector must raise `ConformanceDenial`.
- `must_ignore` -- the attempt may succeed, but the server-bound scope and
  the state of the application it targeted must be unchanged afterward.
- `structurally_absent` -- the claim is that the attack surface does not
  exist on the public API at all. The suite does not accept this claim on
  its word: it inspects the signatures of the declared `surface` callables
  and fails if any `forbidden_parameters` name appears as a parameter.

An adapter must declare at least one vector per `kind` (`MUST_COVER_TAMPER_KINDS`);
C-01 fails an adapter that omits a kind rather than treating the omission
as "not applicable."

### Identifier/value position taxonomy (design section 4.4)

C-03 requires adapters to expose two disjoint sets of probes, each a
callable that places one payload at one syntactic position of a request:

- Identifier positions (`MUST_COVER_IDENTIFIER_POSITIONS`: `entity`,
  `select_field`, `filter_field`, `insert_field`, `schema_entity`,
  `schema_field`) -- every payload in the identifier corpus must be denied
  at every covered position. A payload that cannot even be constructed at a
  given position (for example, an unhashable payload used as a mapping
  key) may raise `PayloadNotExpressible` there instead; the suite still
  requires that payload to have been denied in at least one other position,
  so a per-position exemption can never become a whole-corpus blind spot
  (design section 10.3).
- Value positions (`MUST_COVER_VALUE_POSITIONS`: `insert_value`,
  `filter_value`) -- every payload in the value corpus must either round-trip
  byte-equal through storage/comparison or be denied as a classified
  `ConformanceDenial`. Silent mutation, truncation, or normalization is a
  failure; so is an unclassified native crash (`adapter.UNCLASSIFIED`,
  design section 10.2), which the suite's contract-code membership check
  surfaces rather than silently treating as a pass.

### Credential-reactivation taxonomy (design CONFORMANCE_CONDITIONS_V1_1
section 2)

C-13 requires adapters to declare every control-plane surface of the peer
that could conceivably re-activate an already-revoked credential, as
`TamperVector`s with the fixed `kind` `"credential_reactivation"` --
deliberately not a member of `TAMPER_KINDS` and not covered by
`MUST_COVER_TAMPER_KINDS` (this is a C-13-specific taxonomy, not part of
C-01's scope-tampering one). The three-value `disposition` vocabulary is
the same as `tamper_vectors`, reinterpreted for C-13's revoked-credential
context: `must_deny` (the reactivation call itself is refused),
`must_ignore` (the call may succeed, but authenticating with the
credential afterward is still refused), and `structurally_absent` (no such
call exists at all, proven the same structural, signature-inspection way
as C-01's `structurally_absent` vectors, never accepted as a bare claim).
An adapter must declare at least one vector; an empty declaration is a
suite failure.
