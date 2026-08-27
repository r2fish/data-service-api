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

The three conditions marked `executable (three adapters)` above are built on
two shared taxonomies defined normatively in `conformance-tests/adapter.py`
(design `docs/design/CONFORMANCE_ADAPTER_V1.md` sections 4.3 and 4.4). This
is what "executable" actually covers for C-01 and C-03: coverage of these
taxonomies, not just "some test ran and passed."

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
