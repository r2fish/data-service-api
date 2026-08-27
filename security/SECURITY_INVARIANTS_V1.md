# Data Service API Security Invariants v1

Status: **Authoritative v1 design**  
Scope: common contract for `r2db-api` and `MitateDB-api`

## 1. Purpose

These Security Invariants define the safety properties that every conforming Data Service API implementation must preserve.

They are **not a feature allowlist, architecture gate, or approval catalog**. Their role is closer to road pavement and guardrails: they make safe movement easier and predictable without deciding the destination.

A new API capability, schema operation, query form, storage strategy, authentication mechanism, or platform-specific control is allowed when it preserves these invariants. The absence of an existing implementation pattern is not, by itself, a reason to reject a valid capability.

## 2. Design rule: invariants constrain outcomes, not invention

Security Invariants specify **what must remain true**. They intentionally avoid prescribing one implementation unless the implementation detail itself is necessary to preserve a safety property.

Therefore:

- Invariants MUST NOT become a fixed catalog of permitted API operations.
- Invariants MUST NOT require every new capability to obtain a new security exception merely because it is novel.
- Invariants MUST NOT force `r2db-api` and `MitateDB-api` to use identical infrastructure controls.
- A capability MAY use a new control, data model, query mechanism, or deployment feature when the resulting behavior still satisfies the invariants.
- When an invariant cannot be evaluated for a new capability, the design must make the safety property testable; uncertainty must not silently become permission.

The intended development flow is:

```text
Capability need
  ↓
API / implementation design freedom
  ↓
Security Invariants remain true
  ↓
Conformance evidence
  ↓
usable capability
```

not:

```text
Capability need
  ↓
Is it already on an approved security list?
  ↓
blocked if new
```

## 3. Threat assumptions

The system MUST remain safe under the following assumptions:

- Public API specification and implementation source code may be known to an attacker.
- All external request data is potentially hostile, including authenticated requests.
- A valid Runtime or Developer credential may be stolen or used by a compromised application or AI agent.
- Clients may retry, replay, race, send oversized requests, probe errors, or intentionally consume resources.
- A single application-facing implementation defect may occur.
- Platform configuration may fail unless the implementation explicitly verifies required controls.

These invariants do not claim that compromise is impossible. They require compromise to be bounded, detectable where security-relevant, and prevented from automatically becoming system-wide compromise.

## 4. Top-level containment invariant

### SI-00 — Single-Compromise Containment

**Statement**  
A single compromised Application credential or a single application-facing implementation defect MUST NOT, by itself, be sufficient to compromise unrelated Applications or the Control Plane.

**Protected assets**  
Other Applications, Control Plane, administrative credentials, database administration capability.

**Required property**

```text
Application A compromise
  ≠
Application B compromise
  ≠
Control Plane compromise
```

**Implementation freedom**  
Implementations may use separate databases, roles, schemas, tenants, IAM boundaries, network boundaries, policy engines, or equivalent layered controls. The invariant requires containment, not one particular topology.

**Verification requirement**  
Conformance evidence must demonstrate that loss of one Application credential does not provide a path to another Application or the Control Plane.

---

## 5. Core invariants

### SI-01 — Application Isolation

**Statement**  
A credential scoped to one Application MUST NOT read, alter, enumerate, infer sensitive contents of, or obtain credentials for another Application.

**Must**
- Application scope is resolved server-side from authenticated identity/credential context.
- Cross-Application access is denied independently of client-supplied identifiers.
- Isolation applies to data and schema-changing capability.

**Must not**
- Trust a client-provided Application/database identifier as authority to switch scope.

**Verification**  
Cross-Application read/write/schema tests using valid credentials from another Application.

---

### SI-02 — Control Plane Isolation

**Statement**  
Application-facing Runtime and Developer APIs MUST NOT provide a route to Control Plane data or administrative capability.

**Protected assets**  
Application registry, credential registry, provisioning credentials, database administration capability, platform administration data.

**Must**
- Keep Control Plane authorization distinct from Application authorization.
- Prevent Application credentials from reaching Control Plane storage or privileged provisioning operations.

**Must not**
- Expose Control Plane credentials, internal database credentials, privileged administrative endpoints, or equivalent capability through Application APIs.

**Verification**  
Valid Runtime/Developer credentials must fail closed against Control Plane operations and identifiers.

---

### SI-03 — Runtime / Developer Privilege Separation

**Statement**  
Runtime capability MUST NOT silently acquire Developer/schema-management capability.

**Must**
- Runtime and Developer authority are distinguishable and enforceable server-side.
- Schema-changing operations require the appropriate elevated authority.

**Must not**
- Treat possession of any valid Application credential as sufficient for schema mutation.

**Implementation freedom**  
Role names and infrastructure controls may differ by implementation.

**Verification**  
Runtime credential attempts every common schema-changing class and remains unable to perform it.

---

### SI-04 — No Arbitrary Database Command Execution

**Statement**  
The public Data Service API MUST NOT accept unrestricted database-native command text as a normal execution interface.

**Examples of prohibited normal interfaces**
- arbitrary SQL execution endpoint
- arbitrary PostgreSQL command endpoint
- arbitrary database script execution

**Allowed**  
New structured operations are allowed, including powerful ones, when their semantics, inputs, authority, resource bounds, and effects are explicitly defined and validated.

**Reason**  
The invariant preserves API-level safety boundaries without freezing capability growth.

**Verification**  
No public Application API path permits a client to smuggle unrestricted database command syntax into execution.

---

### SI-05 — Validated Structured Operations

**Statement**  
Externally supplied identifiers, operators, structural definitions, and values MUST cross an explicit validation boundary before affecting database execution.

**Must**
- Validate identifiers against syntax and/or known schema as appropriate.
- Validate operation names/operators against the structured contract.
- Use parameter binding or an equivalently safe mechanism for externally supplied values wherever supported by the database interface.
- Treat validation failure as failure, not fallback to permissive execution.

**Must not**
- Concatenate untrusted values into executable database syntax without a proven safe construction boundary.

**Verification**  
Injection-oriented conformance tests cover identifiers, filters, ordering, selection, schema definitions, and request bodies where applicable.

---

### SI-06 — Server-Bound Credential Scope

**Statement**  
Credential scope MUST be bound by the server to the authenticated Application and privilege level; the client MUST NOT be able to widen it by request content.

**Must**
- Derive Application and role/authority from authenticated credential state.
- Reject disabled, expired, invalid, or unrecognized credentials.

**Must not**
- Allow request fields, headers, paths, or query parameters to upgrade privilege or switch Application unless a separately authenticated administrative contract explicitly authorizes that operation.

**Verification**  
Scope-switch and privilege-escalation attempts using manipulated request data.

---

### SI-07 — Compromised Credential Containment

**Statement**  
Possession of a valid Application credential MUST grant no more than the authority intentionally assigned to that credential.

**Required outcome**
- Stolen Runtime credential: exposure is bounded to permitted Runtime capabilities for its Application.
- Stolen Developer credential: exposure is bounded to permitted Developer capabilities for its Application.
- Neither implies access to other Applications, Control Plane, database administration, or infrastructure credentials.

**Design implication**  
Authentication success is not a trust signal for request contents.

**Verification**  
Tests assume the attacker has a fully valid credential and then attempt lateral movement and privilege expansion.

---

### SI-08 — Bounded Resource Consumption

**Statement**  
One client, credential, request, or operation MUST NOT have unbounded access to service resources merely because it is authenticated.

**Resource classes to bound where applicable**
- request body size
- batch size
- result size
- query complexity
- execution time
- concurrency
- request rate
- schema/object creation rate or count
- expensive or recursive operation depth

**Implementation freedom**  
Limits may be enforced by application code, reverse proxy, platform controls, database controls, or a combination. Exact limits may be deployment-specific when the common contract permits them.

**Must not**
- Turn every new capability into a manual security approval gate. New capabilities should define proportional bounds as part of normal design.

**Verification**  
Boundary and abuse tests confirm deterministic rejection or termination beyond supported limits.

---

### SI-09 — Controlled Destructive Operations

**Statement**  
Destructive capability MUST be explicit, attributable, and bounded so that accidental or ambiguous use is not equivalent to ordinary non-destructive use.

**Applies to**
- schema/object deletion
- bulk deletion
- irreversible migration
- destructive replacement
- equivalent future capabilities

**Must**
- Make destructive semantics explicit in the API contract.
- Require authority appropriate to the destructive effect.
- Preserve atomicity or clearly defined failure semantics.

**Does not require**
- A human approval dialog for every destructive operation.
- A fixed `confirm=true` mechanism for every future API.

Those are possible controls, not invariants.

**Verification**  
Ambiguous, incomplete, or insufficiently authorized destructive requests do not execute.

---

### SI-10 — Error and Information Non-Disclosure

**Statement**  
Public errors MUST NOT expose secrets or unnecessary internal information that materially improves an attacker’s ability to cross a security boundary.

**Must protect**
- credential material
- database passwords/connection URLs
- privileged host/network details
- raw stack traces in public responses
- internal SQL where disclosure creates unnecessary attack leverage
- existence distinctions that enable credential/Application enumeration when the distinction is not required by the public contract

**Must still provide**  
Errors useful enough for legitimate clients and AI agents to correct requests. Security does not justify opaque failure when structured safe diagnostics can be provided.

**Verification**  
Probe invalid credentials, unknown objects, malformed queries, authorization failure, database errors, and unexpected exceptions.

---

### SI-11 — Atomic Integrity

**Statement**  
Operations declared atomic by the public contract MUST either complete according to contract or leave no partial externally visible state.

**Must**
- Define transaction/rollback semantics for multi-step operations that claim atomicity.
- Return failure when integrity cannot be guaranteed.

**Does not require**  
Every future multi-request workflow to be one database transaction. Atomic scope is defined by the contract, not assumed globally.

**Verification**  
Fault injection or failing multi-item operations demonstrate rollback of the declared atomic scope.

---

### SI-12 — No Data-Service Bypass

**Statement**  
Application-facing clients MUST NOT obtain a normal path that bypasses the Data Service public contract and directly exercises database or privileged infrastructure authority.

**Must not expose through Application APIs**
- database credentials
- unrestricted database connection capability
- privileged private management endpoints
- service-account/private keys capable of bypassing the API authorization model

**Implementation freedom**  
Operational administrators may have separately governed emergency/maintenance paths; those paths are outside the Application API and must not be derivable from Application credentials.

**Verification**  
API responses, metadata, configuration exposure, and error paths are checked for bypass-enabling material.

---

### SI-13 — Revocation and Disable Effectiveness

**Statement**  
When a credential or Application is revoked/disabled according to the authoritative control state, subsequent authorization MUST cease within the explicitly documented propagation bound.

**Must**
- Define any cache/propagation delay that affects revocation.
- Fail closed after the revocation state becomes authoritative for the request path.

**Must not**
- Leave an indefinite usable session solely because a credential was previously valid.

**Verification**  
Use credential → revoke/disable → retry inside/outside defined propagation bound.

---

### SI-14 — Security-Relevant Auditability

**Statement**  
Security-relevant events MUST produce enough evidence to investigate abuse and distinguish authorized activity from denied or anomalous activity, without logging secrets.

**Minimum event classes where applicable**
- authentication/authorization denial
- credential lifecycle change
- destructive schema/data operation
- privilege-sensitive operation
- Control Plane administrative change
- security-control failure

**Must not**
- Log plaintext API keys, passwords, tokens, private keys, or equivalent reusable secrets.

**Does not require**  
Logging every successful read at unlimited granularity. Audit detail should be proportional to security value and operational cost.

**Verification**  
Representative events yield correlated evidence; secrets are absent from logs.

---

### SI-15 — Fail-Closed Authorization

**Statement**  
When the service cannot establish the required identity, scope, role, policy, or security-critical state for an operation, it MUST NOT execute that operation.

**Applies to**
- missing/invalid authentication
- unknown credential role
- unresolved Application scope
- unavailable required authorization metadata
- invalid schema metadata where safe execution depends on it

**Does not mean**  
Every infrastructure degradation must stop the entire service. Fail-closed behavior is scoped to operations whose authorization or safe target cannot be established.

**Verification**  
Missing/corrupt/unavailable authorization inputs cannot become successful execution.

---

## 6. Invariants deliberately NOT defined

To prevent the security model from becoming a road gate, v1 intentionally does **not** require:

- a fixed list of API endpoints
- a fixed table/entity model
- a fixed query language
- one physical database per Application
- one particular API-key format
- one cloud provider or network product
- one rate-limit algorithm
- human approval for every destructive operation
- identical PostgreSQL topology for both implementations
- prior enumeration of every future capability

These may be implementation controls or contract decisions, but they are not universal security invariants unless future evidence shows that a stronger invariant is required.

## 7. Conformance rule

A capability is security-conformant when:

1. its authority and affected scope are explicit,
2. all applicable invariants remain true,
3. security-relevant failure behavior is defined,
4. the applicable invariants can be verified by automated test, controlled review evidence, or platform-control evidence,
5. any platform-specific control required to uphold an invariant is documented.

A capability MUST NOT be rejected merely because no previous capability used the same mechanism.

## 8. Change rule

Changing an implementation control does not require changing this document when all invariants remain true.

Changing an invariant requires explicit review because it changes the common security contract for both `r2db-api` and `MitateDB-api`.

Adding a new invariant should require evidence that an important safety property is not adequately expressed by the existing set. The default response to a new feature is **not** to add a new invariant.

## 9. Relationship to Threat Model and controls

```text
Threat Model
  ↓ identifies safety risks
Security Invariants
  ↓ define required outcomes
Conformance Tests
  ↓ verify behavior
Implementation Controls
  ↓ realize the outcomes per platform
```

`r2db-api` and `MitateDB-api` may use different controls while conforming to the same invariants.
