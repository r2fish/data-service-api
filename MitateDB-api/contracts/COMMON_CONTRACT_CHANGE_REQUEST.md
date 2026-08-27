# Common Contract Change Request: Mitate-derived requirements

Status: **proposal for the r2db-led common-contract workstream**  
Scope: generalized requirements derived from the Mitate Repository  
Implementation status: **not yet incorporated into `spec/`**

This document is a change request, not a MitateDB-api-specific public API
contract. The common contract remains owned by `data-service-api/spec/`, and
the Mitate Repository was used as a read-only source. No endpoint names,
request shapes, or implementation-specific assumptions are fixed here.

## 1. Classification rule

Requirements are proposed for the common contract only when they describe a
platform-independent public semantic or a reusable safety outcome. A Cloud
Run, Cloud SQL, IAM, networking, secret-manager, or deployment choice remains
an implementation control and must not become a common API requirement.

The source documents describe product and architecture boundaries above the
Data Service. They therefore inform contract scope and non-responsibility,
but do not authorize the Data Service to own Agent, Solution, Capability, or
business-domain semantics.

## 2. Generalized requirements proposed for `spec/`

| ID | Proposed contract requirement | Contract area | Mitate Repository source (boundary/intent) | Common-contract/security concretization | Related SI |
|---|---|---|---|---|---|
| CCR-01 | Persistent access is performed through a versioned, structured Data Service API. The client does not need raw SQL, physical table names, database credentials, or database-specific transaction internals. | API boundary; capability discovery; versioning | **Data Service Boundary**, “Core principle”, “Mitate side must not depend on”; **Product Foundation**, §8 “Independent Data Service”; **DM-0003**, decision and consequences | `SECURITY_INVARIANTS_V1.md` SI-04/SI-05/SI-12; `MITATEDB_API_WORK_INSTRUCTION.md` §7.1 and §8 | SI-04, SI-05, SI-12 |
| CCR-02 | The public contract is business-domain-neutral and must provide reusable persistence semantics rather than Solution-specific endpoints or business workflow semantics. | Scope and non-responsibilities | **Data Service Boundary**, “Implementation boundary”; **capabilities/business-core.json**, `non_responsibilities`; **DM-0003**, consequences | `SECURITY_INVARIANTS_V1.md` SI-04/SI-05; `MITATEDB_API_WORK_INSTRUCTION.md` §4 and §8 | SI-04, SI-05 |
| CCR-03 | Structured data capability must be extensible enough for logical schema/catalog introspection, generic entities/fields/relations, keys/constraints, CRUD, query/filter/sort/projection, bounded pagination/bulk work, and (where supported) aggregation, while leaving business meaning above the Data Service. Physical table names remain an implementation detail rather than a coupling. | Data capability; schema/catalog; structured query model | **Application Primitive Boundary**, “Required abstraction level”; **Architecture Overview**, “Authoritative shape”; **Solution Boundary**, “Required dimensions”; **capabilities/README.md**, “推奨キー”; **capabilities/business-core.json**, `non_responsibilities` | `SECURITY_INVARIANTS_V1.md` SI-05/SI-08; `MITATEDB_API_WORK_INSTRUCTION.md` §7.1 and §8 (Data capability) | SI-05, SI-08 |
| CCR-04 | Structured operations must define validation, authorization, safe value handling, failure behavior, and affected scope before execution. Unsupported or unsafe input must fail closed rather than fall back to database-native execution. | Authentication/authorization; validation; error semantics | **Application Primitive Boundary**, “Why Primitives exist” and “Extension rule”; **Trust Requirements**, “Relationship to design”; **DM-0004**, decision and consequences | `SECURITY_INVARIANTS_V1.md` SI-05/SI-06/SI-10/SI-15; `MITATEDB_API_WORK_INSTRUCTION.md` §9 | SI-03, SI-05, SI-06, SI-15 |
| CCR-05 | Transaction and concurrency semantics must be explicit for each atomic operation, including rollback/integrity behavior on partial failure. Retry/race safety should use declared preconditions, idempotency, or revision semantics where applicable. | Transaction semantics; integrity; retry/concurrency | **Application Primitive Boundary**, “Why Primitives exist”; **Product Foundation**, §8 “Independent Data Service”; **DM-0003**, rationale; **capabilities/business-core.json**, `failure_behavior` | `SECURITY_INVARIANTS_V1.md` SI-11; `MITATEDB_API_WORK_INSTRUCTION.md` §7.1 and §9 | SI-11 |
| CCR-06 | Security-relevant audit semantics must be defined as a reusable persistence guarantee: the Data Service generates attributable canonical events from service-observed operations and denials, with safe failure evidence. Audit records and public security/error responses must exclude reusable secrets, raw SQL, and row values; ordinary authorized data responses may return the row values requested within their authorized scope. Application callers cannot authoritatively choose or override security-event fields. | Audit event contract | **Application Primitive Boundary**, “Why Primitives exist”; **Architecture Overview**, “Authoritative shape”; **DM-0003**, rationale and consequences | `SECURITY_INVARIANTS_V1.md` SI-10/SI-14; `MITATEDB_API_WORK_INSTRUCTION.md` §9; distinguish security-event emission from audit query authority in CCR-12 | SI-10, SI-14 |
| CCR-07 | Resource limits are part of normal capability semantics. The contract must expose or otherwise define finite bounds appropriate to request/body, batch, result, query complexity, execution time, concurrency/rate, and schema/object proliferation. | Resource-limit semantics; capability discovery | **governance/TRUST_REQUIREMENTS.md**, “Relationship to design”; **architecture/SOLUTION_BOUNDARY.md**, “Required dimensions”; **DM-0003**, rationale | `SECURITY_INVARIANTS_V1.md` SI-08; `MITATEDB_API_WORK_INSTRUCTION.md` §5.3 and §9 (finite bounds are required, exact profile is configurable) | SI-08 |
| CCR-08 | Application scope and authority are server-derived from authenticated credential context; client data cannot switch Application or elevate Runtime/Developer authority. This is an API-level semantic and does not by itself prove SI-00/SI-02/SI-07 runtime containment. | Credential semantics; Application scope; privilege separation | **Data Service Boundary**, “Mitate side must not depend on”; **Product Foundation**, §6 “Agent / Application Boundary”; **DM-0004**, consequences | `SECURITY_INVARIANTS_V1.md` SI-01/SI-06; `MITATEDB_API_WORK_INSTRUCTION.md` §9; SI-00/SI-02/SI-07 require separate platform authority evidence | SI-00, SI-01, SI-02, SI-03, SI-06, SI-07, SI-15 |
| CCR-09 | The common contract must distinguish normal data operations from structured schema/development operations and destructive effects, with explicit authority and failure semantics. It should support logical schema/catalog introspection, keys/relations/constraints, schema revision, and bounded observable jobs for long-running evolution rather than an unbounded request. | Development capability; schema evolution/jobs; destructive operations | **Application Primitive Boundary**, “Required abstraction level” (Validation/State/Transaction); **Solution Boundary**, “Out of Boundary”; **DM-0003**, review triggers; **Application Primitive Boundary**, “Why Primitives exist” | `SECURITY_INVARIANTS_V1.md` SI-03/SI-08/SI-09/SI-11; `MITATEDB_API_WORK_INSTRUCTION.md` §7.1 and §9 | SI-03, SI-08, SI-09, SI-11 |
| CCR-10 | Credential/Application/User-session revocation and disable semantics require an explicit propagation bound and fail-closed behavior when required authorization state is unavailable. | Revocation/disable semantics | **architecture/PRODUCT_FOUNDATION.md**, §4 “Trust Requirements / Lifecycle”; **governance/TRUST_REQUIREMENTS.md**, “Re-evaluation”; **DM-0004**, consequences | `SECURITY_INVARIANTS_V1.md` SI-13/SI-15; `MITATEDB_API_WORK_INSTRUCTION.md` §8 and §9 | SI-06, SI-13, SI-15 |
| CCR-11 | The common candidate should support Application-bound login/session/actor context, generic role/scope/policy enforcement, and user/session disable-revoke, without inferring authority from UI, conversation, or caller-controlled labels. Business meaning remains above the Data Service; `Person`/`Personnel` is not a Login Account. Control Plane authentication must remain separate. | Application User / Identity; policy boundary | **architecture/APPLICATION_PRIMITIVE_BOUNDARY.md**, “Required abstraction level” and “Agent isolation”; **architecture/PRODUCT_FOUNDATION.md**, §5 “Business Core” and §6 “Agent / Application Boundary”; **DM-0004**, decision and consequences | `SECURITY_INVARIANTS_V1.md` SI-01/SI-02/SI-03/SI-06/SI-13/SI-15; `MITATEDB_API_WORK_INSTRUCTION.md` §8 (Application User / Identity and Control) | SI-01, SI-02, SI-03, SI-06, SI-13, SI-15 |
| CCR-12 | Audit event emission and audit query are separate capabilities. The Data Service generates canonical security events as consequences of service-observed operations and denials; an Application caller cannot specify or override event class, actor, outcome, timestamp, target, or security detail. Querying security evidence requires separately authenticated Control/Audit authority; Application credentials must be denied. Query results and errors follow redaction and safe-error semantics. Any future Application-submitted business audit is a separate upper-layer contract and must not be mixed with Data Service security evidence. | Audit authority; audit query; error semantics | **Application Primitive Boundary**, “Why Primitives exist”; **Architecture Overview**, “Authoritative shape”; **DM-0003**, consequences | `SECURITY_INVARIANTS_V1.md` SI-02/SI-10/SI-14; `MITATEDB_API_WORK_INSTRUCTION.md` §7.3 and §9 | SI-02, SI-10, SI-14 |

These are semantic proposals only. Exact endpoint names, JSON shapes, key
formats, database topology, and deployment profile remain decisions for the
common-contract workstream and its peer conformance tests.

## 2.1 Disposition of `contracts/foundation.json`

The existing implementation-foundation artifact is split as follows. This
prevents local topology details from silently becoming public API semantics.

| Foundation section | Disposition | Follow-up |
|---|---|---|
| `public_contract` | Common-contract governance pointer | Keep ownership in `spec/`; r2db-led review promotes only validated semantics. |
| `authority_topology` | MitateDB-api implementation control and evidence plan | Keep Cloud Run/Cloud SQL workload, identity, network, and audit deployment details local; do not expose them as API behavior. |
| `credential_semantics` | Server-bound scope, role separation, secret non-disclosure, and revocation are common semantic requirements; digest/pepper mechanism is implementation-local | Add to the common machine-readable contract after peer review; retain secret-manager wiring locally. |
| `structured_operations` | Common structured-operation, validation, binding, transaction, and destructive-effect semantics | Define exact shapes only in the common contract; do not promote SQLite or PostgreSQL syntax. |
| `resource_bounds` | Finite bound requirement is common; environment variable names and selected profiles are implementation-local | Add boundary semantics to common capability discovery and keep deployment profiles local. |
| `evidence` | Local test references and production evidence gaps | Common conformance conditions belong in `conformance-tests/`; platform proof remains in `CONTROL_MAPPING.md` once deployed. |

## 3. Requirements retained as MitateDB-api platform controls

The following source requirements are valid design constraints for the
MitateDB-api implementation, but should not be copied into the common public
contract as Google-specific behavior:

| Platform control | Source document and section | Why it stays implementation-local |
|---|---|---|
| Cloud Run / Cloud SQL deployment direction | **Data Service Boundary**, “PostgreSQL direction”; **Architecture Overview**, “Deployment direction” | The common contract must work for both peer implementations; the platform may vary. |
| Separate application-facing workload from Control/Provisioning workload, or an equivalently independently verifiable authority boundary, with deny-by-default identity and network paths | **Architecture Overview**, “Authoritative shape”; **Product Foundation**, §6; **DM-0003**, consequences | This is runtime authority evidence for SI-00/SI-02/SI-07, not an API shape or a requirement for one deployment form. |
| External secret manager, Cloud IAM/service identities, private Cloud SQL connectivity, and no credential-bearing application configuration | **Data Service Boundary**, “Mitate side must not depend on”; **Product Foundation**, §8; **DM-0003**, decision | The control mechanism is platform-specific; the common semantic is credential non-disclosure and no bypass. |
| Separate Runtime and Developer database/runtime identities or an equivalent containment control | **Application Primitive Boundary**, “Why Primitives exist”; **Product Foundation**, §6; **DM-0004**, consequences | The common contract requires privilege separation, while the concrete authority topology is implementation-specific. |
| An externally governed append-only audit destination inaccessible to Application authority | **Application Primitive Boundary**, “Why Primitives exist”; **Architecture Overview**, “Authoritative shape” | The common contract defines audit guarantees; sink product, storage, retention, and tamper controls are platform evidence. |

No Mitate-specific user workflow, Typed Semantic Unit, Capability, or Business
Core meaning is promoted into the Data Service contract. Those remain above the
Data Service boundary.

## 4. High-priority semantics and next implementation completion conditions

The current local foundation does not claim to complete the following High
items. They are the next implementation work, not a reason to invent a
Mitate-specific public endpoint now.

| High item | Required semantics | Completion condition for the next implementation |
|---|---|---|
| Single-compromise containment (SI-00, with SI-02/SI-07) | A compromised Application credential or application-facing defect cannot reach another Application, Control Plane, provisioning authority, or infrastructure credentials. | Deployable authority topology with independently verifiable identity/network controls exists; negative lateral/control-plane tests pass; platform evidence shows Application authority has no privileged path. |
| Runtime/Developer authority separation (SI-03) | Runtime data operations cannot acquire schema/development authority; schema changes require separately authenticated Developer authority. | Runtime and Developer have distinct database/runtime authorities or an equivalent proven control; DDL/schema privilege tests and failure evidence pass. |
| Complete proportional resource bounds (SI-08) | Finite, deterministic bounds cover body, batch, result, complexity, execution time, concurrency, rate, and schema/object proliferation. | HTTP adapter and deployment enforce the selected profile; each bound has boundary/abuse tests, and unsupported work terminates or rejects predictably. |
| Externally governed audit integrity (SI-14) | Data Service-generated security events are canonical and attributable; Application authority cannot choose, alter, or delete evidence, and audit records/security errors exclude secrets, SQL, and row values. Ordinary authorized data responses remain allowed to return requested row values. | External append-only sink and access policy are deployed; tamper/delete attempts fail; representative auth, privilege, destructive, revoke, and control events are correlated without sensitive data. |

The local SQLite foundation and topology YAML provide preliminary API-path and
intent evidence only. They are not production proof for these items.

## 5. Requested follow-up

The r2db-api workstream should review CCR-01 through CCR-12 against the
validated r2db behavior, promote only the generalized semantics into the
common machine-readable contract, and derive implementation-independent
conformance conditions. MitateDB-api should then align its HTTP adapter and
deployment controls to that common version without introducing a divergent
public contract.
