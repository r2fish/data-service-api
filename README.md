# data-service-api

Platform-independent PostgreSQL REST Data Service API project.

The repository exists to make the same core Data Service API usable by AI agents across different deployment platforms. An AI agent should be able to operate either implementation from the common API specification plus a base URL and API key.

## Relation to the Mitate product

This Data Service is also the persistence layer of the Mitate product, which is made of four repositories: `Mitate` (product source of truth and the Agent–Application API contract), `mitate-agent`, `mitate-application`, and this one. `mitate-application` integrates only through the public common API in `spec/`; it never imports either implementation or depends on SQL, physical tables, migrations or database credentials.

That rule sets the direction of dependency. It does not put this repository outside the product: when Mitate is read, evaluated or audited as a product, this repository is in scope, and the persistence-safety claims are verified here (`security/`, `spec/`, `conformance-tests/`). The table that maps the product's claims to their evidence is in the `Mitate` repository's `README.md`.

The common contract is owned by neither Mitate nor either implementation, and the Data Service stays usable without Mitate.

## Repository model

```text
data-service-api/
├─ spec/                # authoritative common API specification
├─ security/            # common Threat Model / Security Invariants / control mapping
├─ conformance-tests/   # implementation-independent contract tests
├─ r2db-api/            # VPS / PostgreSQL implementation
└─ MitateDB-api/        # Google Cloud / Cloud SQL for PostgreSQL implementation
```

## Core rule

`r2db-api` and `MitateDB-api` are peer implementations of the same common API contract. Neither implementation owns the contract.

Platform-specific deployment, provisioning, connection management, and operations may differ. Public API semantics, security guarantees, error contracts, and conformance requirements should remain common unless an explicit versioned contract decision says otherwise.

## Primary product goal

API specification first: given the common specification, base URL, and authorized API key, an AI agent should be able to discover and safely use the Data Service without implementation-specific knowledge.

## Common security design

`security/SECURITY_INVARIANTS_V1.md` is the authoritative common safety contract for both implementations. `security/THREAT_MODEL_V1.md` defines the hostile conditions the invariants address, and `security/CONTROL_MAPPING.md` records how each implementation realizes them.

Security Invariants are intentionally **pavement and guardrails, not a capability allowlist or development gate**. They define outcomes that must remain true while leaving API capability, architecture and platform controls free to evolve. A new capability is not rejected merely because it has no previous implementation pattern; it must preserve the applicable invariants and make its security properties verifiable.

Because this API's integrators are assumed to be AI agents, refusals on the control plane carry **truthful deterrence declarations** — true, fixed statements (durable attributed audit, no in-band path to mint control credentials) written to be read by the caller's own AI and to make it warn its human. See `docs/security/TRUTHFUL_DETERRENCE_DECLARATIONS.md`.

## Public repository security

This repository is intentionally public-by-design. Implementation details may be visible; access to real systems must never depend on source secrecy.

- See `SECURITY.md`.
- Complete `docs/security/public-repository-policy.md` before the first public push.
- Real API keys, passwords, PostgreSQL/Cloud SQL credentials, service-account keys, SSH keys, production `.env`, backups, dumps, logs and real application/user data are prohibited from Git.
- `.env.example` contains placeholders only. Runtime secrets belong outside Git.
