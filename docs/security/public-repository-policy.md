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
- 本番hostname (production hostname): a real deployed hostname, FQDN, private address, or internal-only endpoint
- cloud project 識別子 (cloud project identifier): a real GCP project id or project number value
- 実credential_id (real credential_id): the leading half of a locator-form bearer -- it does not by itself break authentication, but it lets an attacker name a specific target (SI-10; see `docs/design/PHASE7_EVIDENCE_REPRODUCIBILITY_AND_PUBLICATION_V1.md` D-1)
- IAM principal・e-mail (IAM principal / e-mail): a real service-account address or a real operator-account address
- 内部トポロジ (internal topology): a real reverse-proxy destination or a real internal port assignment
- 作業機の絶対パス (working-machine absolute path): a real `/Users/…`, `/home/…`, or `C:\Users\…` path

## Placeholder convention

When a value in the categories above must be shown in shape but not in substance, use one of exactly two placeholder forms:
- `<UPPER_SNAKE>` (angle-bracket, upper-snake-case), e.g. `<GCP_PROJECT_ID>`, `<REGION>`, `<VPS_USER>`
- `REPLACE_ME_*` (upper-snake-case, `REPLACE_ME` prefix), e.g. `REPLACE_ME_CONTROL_PORT`

The only allowed synthetic domain is `*.example.invalid`. No other placeholder spelling (lowercase pseudo-values, bracket styles other than `<…>`, ad hoc "example-foo" labels, etc.) is part of this convention -- write real shapes only with one of the two forms above, and only synthetic hostnames as `*.example.invalid`.

This convention is machine-checked: `tools/public_value_scan.py`'s common exclusion recognizes exactly these two placeholder forms (and the `*.example.invalid` domain via its `*.invalid` allowance) as placeholders under this convention, and no other spelling is recognized as a placeholder by it. A spelling that is not one of these forms gets no benefit from this convention. (This is narrower than "will therefore be flagged": the scanner also carries a small number of separate, narrowly-scoped exceptions that are not part of this convention at all -- e.g. a short list of known-safe official domains, one pre-existing synthetic project label predating this convention, and a same-line/preceding-line "synthetic" annotation for credential_id examples -- each documented at its own rule's definition in `tools/public_value_scan.py`. Those do not widen this convention and do not make any other placeholder spelling recognized.)

## Deployment record template convention

A deployment record (e.g. `docs/work-orders/DEPLOY_PHASE6_20260904.md` §7) documents what was actually run against a real environment, so it is the document most at risk of carrying real values into the repository. Every such record:
- writes real values **nowhere** in the repository copy -- use the placeholder forms above for anything in the "Never publish" list;
- keeps the actual value <-> placeholder correspondence table in an operator record outside this repository, never in the committed document;
- states this rule as its own legend/blockquote at the top of its record section (see `DEPLOY_PHASE6_20260904.md` §7's legend for the form to reuse in the next such document) -- and that legend must not list `credential_id` among the things that may be written as-is: a real `credential_id` is in the "Never publish" list above, so a legend that permits writing it directly conflicts with this policy and must be corrected wherever it appears;
- and, for the declaration that a real deployment record's OWN real values were replaced with placeholders before that record entered this repository, reuses the blockquote form at `DEPLOY_PHASE6_20260904.md:3` as the template -- the next such document's opening blockquote should follow that same form (which value categories were replaced, which placeholder token stands for each, and where the real value <-> placeholder correspondence table actually lives), not restate it from scratch.

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

**When the repository has already been pushed once and a value in the "Never publish" list has entered Git history (this repository's case, per `docs/design/PHASE7_EVIDENCE_REPRODUCIBILITY_AND_PUBLICATION_V1.md` D-1), items 1-8 above are necessary but not sufficient: history itself must be rewritten before the repository may go public. The following items continue the same gate, in this order, and are equally required before switching visibility to public:**

9. Fold every linked worktree (`git worktree remove` / `git worktree prune`) -- linked worktrees such as `.claude/worktrees/*` share the main checkout's `.git/objects`, so they hold inconsistent references once history is rewritten. Do the rewrite itself on a fresh clone taken from the remote, not on a shared worktree tree.
10. Rewrite all of history with `git filter-repo --replace-text`, using the existing real-value -> placeholder correspondence table kept in the operator's own record outside this repository (this policy records only that such a table exists, never its content).
11. Apply the commit-map that `git filter-repo` emits to update every in-repository hash reference (commit SHAs quoted in `docs/`, `security/`, and `conformance-tests/CONDITIONS.md`) so those references still resolve after the rewrite.
12. Delete the same-named repository and push only the rewritten history to re-create it, across all branches and all tags: 「同名リポジトリを delete し、書換後の履歴だけを push して再作成する」。「全 branch・全 tag を push する。」(requester ruling 2026-09-05, design `PHASE7_EVIDENCE_REPRODUCIBILITY_AND_PUBLICATION_V1.md` §6 (γ) plan 1 / D-1 (iv) (4)). This is an operator action. Until this step, the rewrite exists only locally -- the real values the rewrite removes are still present on the remote. A plain force-push is not sufficient by itself: GitHub can retain the pre-rewrite commits as unreachable objects after a force-push, so the remote's object store itself must be made new by deleting and re-creating the repository -- 「remote の object store 自体を新しくする」.
13. Take a fresh clone from **the remote re-created in item 12 above** (「再作成後の remote」) and run the scanner's history mode (`tools/public_value_scan.py --history`, i.e. `git log --all -p -m`) against **that clone**, confirming zero findings across all rules. Scanning the local rewritten tree is not sufficient -- what matters is what the remote actually serves, and after item 12 that remote is the newly re-created one, not the original.
14. Re-create every clone and worktree that still points at the pre-rewrite history -- the shared checkout, `.claude/worktrees/*`, and any deployment-host clone.
15. Revoke and re-issue every live credential that could identify this repository's real deployments (the r2db control and runtime credentials). Rotation is not sufficient here because rotation preserves the credential's `id`; revoke-and-reissue is required.
16. Obtain the repository owner's explicit go-ahead before switching visibility to public, and only the repository owner performs the visibility switch itself.

Note: a plain force-push can leave the pre-rewrite commits on GitHub as unreachable objects (fetchable by exact SHA) until GitHub's own garbage collection runs. This is settled, not open: item 12 above requires deleting and re-creating the same-named repository specifically so that the remote's object store itself becomes new -- the pre-rewrite objects do not exist in it, so this residual exposure does not survive item 12 (requester ruling 2026-09-05, design §6 (γ) plan 1: 「同名リポジトリを delete し、書換後の履歴だけを push して再作成する」; 「残留対処が未確定であることを理由に公開を止める阻却事由は無くなった」).

## Ongoing rule

A commit is acceptable only if it could be made public immediately without granting access to any real system.
