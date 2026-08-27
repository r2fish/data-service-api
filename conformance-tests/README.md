# Data Service API Conformance Tests

Implementation-independent tests for the common Data Service API contract and Security Invariants.

The same suite must be runnable against both:

- `r2db-api`
- `MitateDB-api`

## Security relationship

Security verification is derived from `security/SECURITY_INVARIANTS_V1.md`, not from whichever behavior the current implementation happens to have.

```text
Threat Model
  ↓
Security Invariant
  ↓
Conformance condition
  ↓
r2db-api / MitateDB-api evidence
```

A common invariant may be verified by API-level automated tests, controlled fault/security tests, or documented platform-control evidence when the property cannot be observed through the public API alone.

The conformance suite must not become a fixed feature allowlist. New capabilities may add new tests when needed while remaining free to use new implementation mechanisms.

## Initial extraction

Existing validated r2db-api tests are evidence candidates, not the source of truth. Their behavior should be mapped against the common invariants before reuse.

Likely reusable areas include authentication, CRUD, filtering/sorting/pagination, JSONB behavior, application isolation, SQL-injection resistance, request transaction rollback, and Runtime/Developer schema privilege separation.

Platform-specific deployment/provisioning mechanics do not belong in the common test suite, but evidence that a platform-specific control satisfies a common invariant belongs in `security/CONTROL_MAPPING.md`.
