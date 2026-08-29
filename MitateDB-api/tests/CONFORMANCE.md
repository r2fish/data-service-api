# MitateDB-api foundation conformance

`test_foundation.py` is the first executable implementation of invariant-derived
conditions. It deliberately exercises the authority and structured-operation
boundary rather than inventing HTTP endpoint names before the common contract
in `spec/` is extracted.

| Condition | Evidence | Invariants |
|---|---|---|
| Application scope is server-bound and cells cannot be crossed | `test_application_scope_is_server_bound` | SI-01, SI-06 (local API-path evidence only) |
| Runtime cannot perform schema mutation | `test_developer_schema_and_runtime_crud` | SI-03 |
| Native command/injection-shaped identifiers are rejected | `test_no_arbitrary_sql_and_identifier_validation` | SI-04, SI-05 |
| Atomic transaction rolls back on a rejected operation | `test_transaction_rolls_back` | SI-11 |
| Revocation, disable, and unavailable auth state fail closed | `test_disable_revoke_and_unavailable_state_fail_closed` | SI-13, SI-15 |
| Batch and destructive-operation bounds are deterministic | `test_bounded_inputs_and_explicit_destructive_confirmation` | SI-08, SI-09 |
| `delete` denies without a valid declare-and-echo confirmation, and the same phrase executes it (contract 1.2.0 `destructive_confirmation`) | `test_delete_without_confirmation_is_gated_not_conflated_with_empty_filters` | SI-09 |
| `delete` rejects a non-boolean `destructive`/non-string `confirm` as a shape defect, never as a truthy confirmation | `test_delete_rejects_non_boolean_destructive_and_non_string_confirm` | SI-09 |

Cloud Run/Cloud SQL identity, network, secret-manager, and externally governed
append-only audit controls remain deployment evidence and must be added to
`security/CONTROL_MAPPING.md` only after they exist in the deployment
configuration.
