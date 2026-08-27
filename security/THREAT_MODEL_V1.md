# Data Service API Threat Model v1

Status: **Authoritative supporting model for Security Invariants v1**

## Purpose

This Threat Model identifies the classes of hostile behavior that the common `data-service-api` security contract must tolerate. It does not prescribe platform-specific products or implementation topology.

## Security objective

The primary objective is not the impossible claim that intrusion can never occur. The objective is that compromise is difficult, bounded, does not automatically become lateral/system-wide compromise, and leaves appropriate security evidence.

The central containment objective is:

> A single compromised Application credential or a single application-facing defect must not be sufficient to compromise unrelated Applications or the Control Plane.

## Trust assumptions

The following are **not trusted** merely because they are valid participants:

- Internet clients
- AI agents
- authenticated Runtime clients
- authenticated Developer clients
- request payloads, paths, identifiers, filters, schema definitions, and query parameters
- retried/replayed/concurrent requests

The following may be trusted only through explicit platform controls and verification:

- Data Service runtime identity
- Control Plane identity
- database connection authority
- deployment configuration
- secret-management integration

## Protected assets

- Application data
- Application schema and integrity
- other Applications' data/schema
- Runtime and Developer credentials
- Control Plane data
- provisioning/database administration capability
- PostgreSQL / Cloud SQL integrity and availability
- security audit evidence
- service availability and bounded operating cost

## Primary trust boundaries

```text
Untrusted / authenticated clients
        ↓ B1
Public Data Service API
        ↓ B2
Authentication + Authorization + Scope resolution
        ↓ B3
Application-scoped execution authority
        ↓ B4
Application persistence boundary

Control Plane / Provisioning
        ↓ B5
Privileged database/platform administration
```

Application-facing authority and Control Plane authority must remain distinct.

## Threat classes

### T-01 Credential theft or replay
A valid Runtime or Developer credential is obtained and used by an attacker or compromised agent.

Required outcome: damage is limited to that credential's intended Application/role scope; revocation is effective within defined bounds.

### T-02 Privilege escalation
Runtime authority is manipulated into Developer/schema/admin capability.

Required outcome: role/authority is server-bound and escalation fails closed.

### T-03 Cross-Application lateral movement
A credential for Application A attempts to read/change/enumerate Application B.

Required outcome: isolation holds regardless of guessed IDs, table names, row IDs, or client-supplied scope fields.

### T-04 Control Plane escape
Application-facing APIs are used to reach credential registries, provisioning state, database admin authority, or management operations.

Required outcome: no such path exists through Application credentials.

### T-05 Injection / syntax smuggling
Identifiers, filters, values, schema definitions, ordering, or other structured fields attempt to introduce executable database-native syntax.

Required outcome: explicit validation and safe construction prevent unintended command execution.

### T-06 Destructive misuse
A valid credential intentionally or accidentally performs high-impact deletion/schema operations.

Required outcome: destructive semantics and authority are explicit and bounded; ambiguous destructive operations do not execute.

### T-07 Resource exhaustion / economic denial
Large bodies, batches, expensive queries, high concurrency, schema proliferation, or repeated requests exhaust CPU, memory, connections, database capacity, or cloud spend.

Required outcome: proportional resource bounds and platform/application limits constrain impact.

### T-08 Information disclosure through errors or metadata
The API leaks secrets, stack traces, connection information, internal SQL, credential existence, or sensitive topology.

Required outcome: useful but bounded diagnostics; no reusable secrets or unnecessary attacker leverage.

### T-09 Concurrency / partial failure corruption
Races, retries, or multi-item failure produce inconsistent partial state.

Required outcome: declared atomicity and integrity semantics are preserved.

### T-10 Revocation bypass
A disabled/revoked credential continues to work indefinitely because of caches, sessions, or stale authorization state.

Required outcome: revocation takes effect within documented propagation bounds.

### T-11 Public-API bypass
Application clients obtain DB credentials, private management authority, or another route around Data Service authorization.

Required outcome: Application-facing API does not provide bypass-enabling authority.

### T-12 Platform misconfiguration
Network exposure, IAM policy, database grants, secret handling, or deployment configuration undermines an invariant even when application code is correct.

Required outcome: each implementation documents and verifies platform controls required for common invariants.

### T-13 Supply-chain/runtime compromise
A dependency or runtime vulnerability provides code execution within a service component.

Required outcome: layered scope/credential/network/database controls limit lateral movement where feasible; compromise of one application-facing component is not assumed to grant Control Plane authority.

### T-14 Security evidence destruction or secret logging
Attackers evade investigation or the service logs reusable secrets while trying to improve observability.

Required outcome: security events are attributable enough for investigation; secrets are not logged.

## Out of scope for v1 common invariants

The common Threat Model does not standardize:

- physical anti-tamper protection of cloud/VPS hosts
- protection against a total compromise of the cloud provider itself
- a specific WAF, IAM product, firewall, proxy, or secret manager
- business-domain authorization inside a Solution above the Data Service contract
- guaranteed prevention of all denial-of-service traffic at Internet scale

Implementations may add stronger controls without changing the common API contract.
