# Data Service Foundation

## Purpose

Provide a business-domain-neutral persistence safety boundary for Mitate while keeping PostgreSQL implementation details outside the Agent/Application product repository.

## Architecture

```text
Mitate
  ↓ versioned public API
mitate-data-service
  ↓
Cloud SQL for PostgreSQL
```

## Owns

- persistence API implementation
- PostgreSQL connectivity
- physical schema and migrations
- transaction/concurrency guarantees
- storage-boundary integrity
- data-level audit/evidence
- deployment/runtime configuration

## Does not own

- user conversation
- Solution/Capability design
- Typed Semantic Unit semantics
- Application Primitive semantics
- business workflows or business-specific endpoints

## Safety rule

Mitate must never need raw SQL, table names, DB credentials, migrations or private persistence types to use this service.
