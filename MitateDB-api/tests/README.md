# Tests

Tests for the Independent Data Service repository.

Coverage should include:
- public API contract behavior
- storage-boundary validation
- PostgreSQL persistence/integrity
- transactions and rollback
- concurrency behavior
- migrations/version compatibility
- data-level audit/evidence
- rejection of invalid or unauthorized storage operations where applicable

Cross-repository compatibility with Mitate must be verified against the versioned public Data Service contract.
