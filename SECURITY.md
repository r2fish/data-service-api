# Security Policy

data-service-api is developed as a public repository. Its API, security model and implementation may be public; real environment access must remain private.

## Common security contract

The authoritative common security design is:

- `security/SECURITY_INVARIANTS_V1.md`
- `security/THREAT_MODEL_V1.md`
- `security/CONTROL_MAPPING.md`

The Security Invariants define required safety outcomes for both `r2db-api` and `MitateDB-api`. They are deliberately not a fixed list of allowed capabilities. New API capability may evolve when the applicable invariants remain true and can be verified.

## Never commit

- Runtime/Developer API keys, admin passwords, peppers, tokens or session secrets
- PostgreSQL passwords or real database connection URLs
- Cloud SQL credentials, service-account keys or other cloud credential files
- VPS SSH private keys, host credentials or privileged bootstrap secrets
- production `.env` files
- backups, database dumps, production logs or real application/user data

Use `.env.example`, test fixtures and clearly fake endpoints/credentials.

## Public-code principle

Security must not depend on hiding implementation details. It must depend on explicit authentication, authorization, application isolation, structured API boundaries, least privilege, containment and secret management outside Git.

The common containment objective is that one compromised Application credential or one application-facing defect must not, by itself, compromise unrelated Applications or the Control Plane.

## Before the first public push

Run `docs/security/public-repository-policy.md`. Review the complete Git history. A secret that has ever entered Git must be considered exposed and rotated/revoked before publication.
