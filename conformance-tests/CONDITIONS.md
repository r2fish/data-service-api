# Common conformance conditions (v1 foundation)

These conditions are implementation-independent. An adapter may expose an
equivalent operation; endpoint names and storage topology are not tested here.

| ID | Condition | Invariants | Evidence |
|---|---|---|---|
| C-00 | A credential for Application A has no path to B or control/provisioning authority. | SI-00, SI-02, SI-07 | platform topology evidence plus negative adapter test |
| C-01 | Application and role come only from authenticated credential state; request scope/role fields cannot alter them. | SI-01, SI-06 | scope-tampering test |
| C-02 | Runtime cannot execute schema/development or control operations. | SI-02, SI-03 | privilege-negative test |
| C-03 | SQL/native command text and syntax-smuggling identifiers are rejected; supported values cross a binding boundary. | SI-04, SI-05 | structured input/injection test |
| C-04 | Unsupported operations fail before execution and public errors are safe, structured diagnostics. | SI-05, SI-10, SI-15 | error probe |
| C-05 | All applicable resource classes have finite, discoverable bounds and over-bound requests terminate deterministically. | SI-08 | boundary test |
| C-06 | Destructive operations require explicit semantics and authority; ambiguous requests do not execute. | SI-09 | destructive-negative test |
| C-07 | Atomic operations commit wholly or roll back; retries use declared idempotency/preconditions. | SI-11 | fault/rollback test |
| C-08 | Revoked/disabled credentials, applications, and sessions stop authorizing within the published finite bound; unavailable state fails closed. | SI-13, SI-15 | revoke/retry test |
| C-09 | Security events are attributable and immutable to application callers; secrets, SQL, and row values are absent. Audit query requires control/audit authority. | SI-10, SI-14 | audit event test and platform sink evidence |
| C-10 | Application clients cannot obtain DB credentials, private management authority, or bypass-enabling configuration. | SI-12 | response/configuration review |

The initial executable suite checks contract shape and the reference
authority skeleton. Peer adapters can run the same condition identifiers with
their own harnesses.
