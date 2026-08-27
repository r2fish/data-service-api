# Security Invariant Control Mapping

Status: **Implementation mapping template**

This document maps common Security Invariants to platform-specific controls. It is intentionally not the source of truth for the invariants themselves.

| Invariant | r2db-api control/evidence | MitateDB-api control/evidence | Common conformance evidence |
|---|---|---|---|
| SI-00 Single-Compromise Containment | TBD during r2db-api audit | TBD during implementation | lateral/control-plane tests |
| SI-01 Application Isolation | TBD during r2db-api audit | TBD | cross-Application tests |
| SI-02 Control Plane Isolation | TBD during r2db-api audit | TBD | control-plane denial tests |
| SI-03 Runtime/Developer Separation | TBD during r2db-api audit | TBD | privilege tests |
| SI-04 No Arbitrary DB Commands | TBD during r2db-api audit | TBD | contract/API surface review |
| SI-05 Validated Structured Operations | TBD during r2db-api audit | TBD | injection tests |
| SI-06 Server-Bound Credential Scope | TBD during r2db-api audit | TBD | scope tampering tests |
| SI-07 Compromised Credential Containment | TBD during r2db-api audit | TBD | stolen-credential scenario tests |
| SI-08 Bounded Resource Consumption | TBD during r2db-api audit | TBD | resource boundary tests |
| SI-09 Controlled Destructive Operations | TBD during r2db-api audit | TBD | destructive misuse tests |
| SI-10 Error/Information Non-Disclosure | TBD during r2db-api audit | TBD | error probing tests |
| SI-11 Atomic Integrity | TBD during r2db-api audit | TBD | rollback/fault tests |
| SI-12 No Data-Service Bypass | TBD during r2db-api audit | TBD | exposure/config review |
| SI-13 Revocation/Disable Effectiveness | TBD during r2db-api audit | TBD | revoke/retry tests |
| SI-14 Security-Relevant Auditability | TBD during r2db-api audit | TBD | audit evidence tests |
| SI-15 Fail-Closed Authorization | TBD during r2db-api audit | TBD | unavailable/invalid auth-state tests |

## Rule

A blank/TBD mapping is not permission to weaken an invariant. It means the implementation has not yet demonstrated how it satisfies the common requirement.

Conversely, a new implementation control does not require a new invariant if it preserves the existing security outcomes.
