# data-service-api security design

The common security model is defined by:

1. `SECURITY_INVARIANTS_V1.md` — authoritative required safety outcomes
2. `THREAT_MODEL_V1.md` — hostile conditions and risks the invariants address
3. `CONTROL_MAPPING.md` — platform-specific implementation/evidence mapping

Core rule:

> Security Invariants are pavement and guardrails, not a capability allowlist or development gate.

New Data Service capabilities remain designable when the invariants remain true and their security properties are verifiable.
