# data-service-api Agent Guide

## Purpose

This repository owns the common Data Service API contract and its two peer implementations: `r2db-api` and `MitateDB-api`.

## Source of truth

1. `spec/` — common public API contract and semantics
2. `security/SECURITY_INVARIANTS_V1.md` — authoritative common safety outcomes
3. `security/THREAT_MODEL_V1.md` — common hostile conditions and protected boundaries
4. `conformance-tests/` — implementation-independent behavioral/security requirements
5. `security/CONTROL_MAPPING.md` — implementation-specific control/evidence mapping
6. implementation-local architecture/docs — platform-specific realization only
7. `docs/security/public-repository-policy.md` — public repository publication gate

## Security Invariants are not a feature gate

Treat Security Invariants as pavement and guardrails, not a capability allowlist.

- They define what must remain true, not which future capabilities are permitted.
- Do not reject a valid new capability merely because no existing endpoint, primitive, control, or implementation pattern matches it.
- Do not add a new invariant for every new feature. Add one only when an important common safety property is not represented by the existing set.
- Platform-specific controls may differ between `r2db-api` and `MitateDB-api` when they provide the same required safety outcome.
- If a new capability cannot yet demonstrate an applicable invariant, make the security property testable and resolve the gap; do not silently permit uncertainty and do not turn novelty itself into a blocker.

## Boundaries

- Do not make `r2db-api` or `MitateDB-api` the implicit owner of the public contract.
- Do not introduce implementation-specific public API behavior without deciding whether it belongs in the common contract.
- Do not expose arbitrary SQL as the normal public API.
- Preserve the common Security Invariants unless an explicit versioned security-contract decision supersedes them.
- Platform-specific PostgreSQL provisioning and deployment belong inside the corresponding implementation.
- Existing VPS `project/r2-vps/apps/r2db-api` remains the current r2db-api source until an explicit migration is performed.

## Public Repository Security Gate

Treat every file as public from creation time.

- Never commit real Runtime/Developer/Admin API keys, passwords, tokens, peppers, cookies, SSH/private keys, service-account keys, PostgreSQL/Cloud SQL credentials, or credential-bearing URLs.
- Never commit production `.env`, backups, database dumps, production logs, real application/user data, or personal information.
- Use environment-variable names, secret-manager references, fake domains and synthetic fixtures only.
- `.gitignore` reduces accidental tracking but is not the security boundary. Inspect tracked content and Git history before first public push.
- If a real secret has ever entered Git, rotate/revoke it before publication; deleting the current file is insufficient.
- Complete `docs/security/public-repository-policy.md` before connecting/pushing to a public GitHub remote.

Security must depend on explicit authentication, authorization, application isolation, structured API boundaries, safe database construction, least privilege and external secret management—not on source-code secrecy.

## Development order

Common capability/requirement → applicable Security Invariants → common API contract → conformance evidence → implementation(s) → implementation-specific tests/controls.

## Working procedure

- Read `docs/work-orders/OPERATING_CONDITIONS.md` at session start; it is the source for how work is run here (worktrees, gates, commits, roles).
- Use `tools/dev/` (`pt.py`, `mutate.py`, `gate.py`, `finalize.py`, `section.py`; see `tools/dev/README.md`) instead of repeating those procedures by hand. Commit through `finalize.py`, which runs the identity, empty-`.md`, doc-reference and public-value checks.
- On a fresh clone run `.venv/bin/pre-commit install` once, so a hand-made commit also runs the public-value and doc-reference scans. `.git/hooks` is shared by every worktree.
