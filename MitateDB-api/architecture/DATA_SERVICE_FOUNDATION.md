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

## Executable foundation (0.1)

The initial implementation keeps the common public contract in `../../spec/`
and provides only a contract-independent foundation under `src/mitatedb_api/`:

- `ControlPlane` owns application provisioning and credential lifecycle.
- `ApplicationCell` is an application-bound storage handle. An application
  session is opened from authenticated credential state; request data cannot
  select another cell.
- `ApplicationRuntime` exposes structured data operations only. Its interface
  does not contain schema mutation or database-native command execution.
- `ApplicationDeveloper` adds structured schema creation, while retaining the
  same application-bound cell.
- `AuditSink` exposes immutable snapshots from the session boundary and accepts
  allowlisted event classifications rather than secrets, SQL, or row values.

The local backend is SQLite solely for deterministic foundation tests. It is
not the production persistence topology. The Cloud Run/Cloud SQL adapter must
preserve these authority boundaries and provide the platform evidence listed
in `contracts/foundation.json` before production use.

Finite local bounds are defined by `FoundationConfig` and may be supplied by
the non-secret `MITATEDB_*` environment variables in `config/foundation.env.example`.
The machine-readable implementation foundation and its evidence scope are in
`contracts/foundation.json`; it intentionally does not invent public endpoint
semantics before the common contract is established.
