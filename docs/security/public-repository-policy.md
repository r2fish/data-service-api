# Public Repository Policy

## Purpose

data-service-api is intended for public GitHub publication and must allow an AI agent to understand the common Data Service API without exposing any real deployment credential or data.

## Public by design

Safe to publish when sanitized:
- `spec/` including OpenAPI and AI usage documentation
- `conformance-tests/`
- r2db-api and MitateDB-api source/tests
- PostgreSQL schema/migrations and security logic
- deployment/container templates
- synthetic examples and `.env.example`

Never publish:
- Runtime/Developer/Admin keys or key peppers
- PostgreSQL/Cloud SQL passwords or credential-bearing URLs
- VPS/SSH/cloud private credentials
- production `.env`
- backups, dumps, real logs or real application/user data
- operational secrets embedded in scripts or CI configuration

## Security model

The implementation may be public. Security must be provided by API authentication, Runtime/Developer privilege separation, application/database isolation, structured schema/query APIs, parameterized SQL, least-privilege database roles and external secret management—not by source secrecy.

## AI-agent rule

Treat every generated file as public. Never copy real keys, passwords, host credentials, production data or private-key material into repository content. Use placeholders, environment-variable names and synthetic fixtures.

## First-public-push gate

Before `git push` to a public remote:
1. Confirm `.gitignore`, `.env.example` and `SECURITY.md` exist.
2. Inspect tracked file names for `.env`, credentials, private keys, dumps, backups and logs.
3. Search all tracked content and Git history for secret-like values and real infrastructure credentials.
4. Review `git diff --cached` and the exact files going public.
5. Confirm both implementation examples use synthetic values.
6. Confirm conformance tests contain no real application/user data.
7. If a real secret has ever entered Git, revoke/rotate it before publication; deleting the file alone is insufficient.
8. Only then connect/push to the public GitHub repository.

## Ongoing rule

A commit is acceptable only if it could be made public immediately without granting access to any real system.
