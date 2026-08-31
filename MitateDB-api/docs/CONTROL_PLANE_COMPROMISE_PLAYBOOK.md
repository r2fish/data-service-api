# MitateDB-api control-plane compromise/lockout playbook

Status: operator playbook, implementation-local to `MitateDB-api` (this
document names `MitateDB-api`-specific CLI subcommands, table/role names,
and environment variables; r2db-api's own equivalent recovery material
lives in `r2db-api/docs/CONTROL_PLANE_COMPROMISE_PLAYBOOK.md` -- read here
only for the *shape* of the problem, never copied: the two peers'
independent control-plane implementations, design R-2's own "no code
sharing between peers" principle, mean the mechanics below genuinely
differ in several places, noted as they come up). Companion to
`docs/design/MITATEDB_PHASE3_HTTP_PERSISTENCE_V1.md` R-6/R-9,
`security/CONTROL_MAPPING.md` (evidence for the properties this document
claims), and `cloud-run-cloud-sql.md` (this same directory) §7-8, which
this document assumes and does not repeat.

## When to use this document

A **control credential** -- the secret that authenticates against
`/control/v1` (over HTTP) or the break-glass CLI's own `MITATEDB_CONTROL_
CREDENTIAL_ID`/`_SECRET` (§7 of `cloud-run-cloud-sql.md`) -- has reached, or
is suspected to have reached, a party who should not hold it: logged
somewhere it should not have been, handed to the wrong environment, or
taken by an attacker. This document does not attempt to distinguish
"genuinely malicious" from "an honest mistake" (the confirmation layer
below cannot make that distinction either, by construction) -- it bounds
the damage regardless of which it turns out to be, and gives the recovery
sequence.

This document is specifically about a **control credential**
(`control_credentials` table). Two adjacent, more severe incident classes
are named in §5 but are NOT this document's main subject, because
recovering from them requires a different secret entirely:

- The **control-plane pepper** (`MITATEDB_CONTROL_CREDENTIAL_PEPPER`) or
  the **`mitatedbsvc_controlplane` DSN itself** leaking is an
  infrastructure-secret incident, not a credential-row incident -- see §5.
- The **`mitatedbsvc_provision` DSN** (`MITATEDB_PROVISION_DSN`) leaking is
  categorically worse (that role can `CREATE`/`DROP DATABASE`/`ROLE`) and
  is out of this document's scope entirely -- see §5.

## Why this is a bounded, recoverable event

1. **Reversibility is real but not unconditional.** `disable_application`
   immediately denies every credential belonging to that application
   (`auth.CredentialStore.authenticate`'s own `self._applications.get(item.
   application_id, False)` check) with no data destroyed, and is undone by
   `enable_application`. `disable_credential`/`enable_credential` are the
   same, scoped to one credential. **`revoke_credential` on an
   *application* credential is real, permanent, and -- this is the
   important asymmetry from a compromised control credential's point of
   view -- entirely UNGATED**: `ControlPlaneService.revoke_credential`
   applies contract `non_destructive_requests` to an application-credential
   target (no `destructive`/`confirmation` check of any kind), so a
   compromised control credential can revoke every application credential
   it can see, one call each, with no confirmation step slowing it down at
   all. That is not a data-destroying action (Application data is never
   touched by any control-plane operation), but it is a genuine
   **availability harm**: every legitimate consumer of a revoked
   credential needs a freshly issued replacement before it authenticates
   again -- real operational work, addressed in step 5 below, not a free
   rollback.
2. **The control credential itself cannot be multiplied.** Issuing a
   `role=control` credential has exactly one path -- the out-of-band
   `bootstrap`/`reset` ceremony (`python -m mitatedb_api.ops`) -- and no
   in-band operation reaches it: `ControlPlaneService.issue_credential`
   refuses `role="control"` unconditionally
   (`_deny_role_control`/`CAPABILITY_UNSUPPORTED`, evaluated *before*
   target-application resolution so the refusal is uniform regardless of
   which application_id is named -- design R-6's own evaluation-order
   fixture, C-14 vector 3). A stolen control credential cannot mint itself
   a spare to survive `reset`.
3. **`reset` reaches every control credential unconditionally, including
   ones the attacker does not know about.** `reset_control_credentials`
   revokes **every** `control_credentials` row -- enabled, disabled, or
   already revoked -- and mints exactly one new must-rotate credential,
   atomically, in one transaction. Running it does not require knowing
   which credential is compromised, or even how many control credentials
   currently exist.
4. **The evidence cannot be erased, including by the credential itself.**
   `control_audit` is INSERT-only from `mitatedbsvc_controlplane`'s own
   grant (migration `0002`: `GRANT INSERT ON mitatedb_registry.
   control_audit TO mitatedbsvc_controlplane` -- no `UPDATE`/`DELETE`, no
   `SELECT` even) -- a stolen control credential authenticates as an
   application-level principal inside that role's connection, never as the
   schema owner, so it can never reach an `UPDATE`/`DELETE` on this table
   regardless of which `/control/v1` operation it calls. Denials are
   durably recorded too (`ControlPlaneService._deny_audit`, every
   authentication/authorization/capability denial except the two named
   exemptions -- the rate-limit pre-authentication stage, and `AUTH_STATE_
   UNAVAILABLE` itself, neither of which has a known actor or a reachable
   store to write to) -- a locked-out legitimate operator's own failed
   attempts are themselves a detection signal, visible in the same trail
   `audit-report` reads (§4 below).
5. **A compromised control credential never reaches application data, and
   never reaches the deprovisioning/provisioning surface.** Every `/control
   /v1` operation and every break-glass CLI subcommand this document's
   recovery steps use operates only on the `applications`/`credentials`/
   `control_credentials`/`control_audit` registry tables (`mitatedbsvc_
   controlplane`'s own grants, migration `0002`) -- none of them can
   `CREATE`/`DROP DATABASE` or `CREATE`/`DROP ROLE` (that needs
   `mitatedbsvc_provision`, a wholly separate DSN no control credential or
   control-plane process ever holds, design R-4's process-role
   separation). `deprovision` (the CLI's own genuinely destructive,
   declare-and-echo-gated subcommand) is reachable ONLY with `MITATEDB_
   PROVISION_DSN` -- a control credential alone cannot invoke it.

Put together: the residual harm from a control-credential compromise is
bounded to (a) whatever data-plane reach the application credentials
**issued or rotated during the compromise window** provide, until revoked
(a rotated pre-existing credential's new secret is exactly as much a reach
vector as a freshly issued one); (b) the **availability harm** from every
application credential the compromised control credential revoked --
recovering means reissuing and redistributing a replacement to every
affected consumer, not merely noting that it happened; and (c) the
operational disruption of the recovery itself. Nothing about a compromised
control credential reaches Application data, or is a route to unbounded,
undetectable, or self-perpetuating access.

## Recovery sequence

Run in order. Steps 2-5 read `control_audit` to scope steps 3/6/7 --
do not skip straight to `reset` without first widening your read of what
happened, if the audit trail is still reachable (it is, unless the whole
Cloud SQL instance itself is also down, a different incident class
entirely).

**Prerequisite, checked once, not per step**: every step below connects
directly to Cloud SQL (through the Cloud SQL Auth Proxy, `cloud-run-
cloud-sql.md` §7) -- never through the control Cloud Run service's own
HTTP surface, whether or not that service is still running. This is
deliberate: a suspected-compromised environment is exactly when you should
not trust the network path an attacker might also have reached.

### Step 1 -- stop the network path (optional, but usually first)

If the compromise looks actively in-progress over HTTP, stop or undeploy
the control Cloud Run service immediately:

```sh
gcloud run services update-traffic mitatedb-ctrl --project=example-project --region=us-central1 --to-revisions=REVISION=0
```

**This alone revokes nothing** -- the break-glass CLI (§7 of
`cloud-run-cloud-sql.md`) still reaches every control credential directly
through Cloud SQL, which is exactly why steps 2+ below do not depend on
the control service being up at all. Per `cloud-run-cloud-sql.md`
invariant 3, flip the data service's own `MITATEDB_CONTROL_PLANE_STATUS`
to `unavailable` in the SAME change if you are leaving the control service
down for more than a brief window -- otherwise the data service's own
`GET /v1/capabilities` keeps asserting a control plane that is not actually
reachable.

### Step 2 -- read the audit trail before it might change further

```sh
export MITATEDB_PROVISION_DSN="host=127.0.0.1 port=5432 dbname=mitatedb_platform user=mitatedbsvc_provision password=..."
python -m mitatedb_api.ops audit-report --since 2026-08-01T00:00:00Z > /tmp/mitatedb-incident-audit.jsonl
```

Save this file somewhere outside the incident's own blast radius before
proceeding -- it is the only record of what happened before `reset` (step
3) changes `control_credentials`' own state. Note every row where
`operation` is `issue_credential`, `rotate_credential`, or
`revoke_credential`, and every row where `outcome` is `deny` with an
`actor_type`/`actor_id` you do not recognize (a legitimate operator's own
locked-out attempts will also show up here -- do not treat every denial as
proof of an attacker, but do not discard any of them either).

### Step 3 -- reset every control credential

```sh
export MITATEDB_CONTROLPLANE_DSN="host=127.0.0.1 port=5432 dbname=mitatedb_platform user=mitatedbsvc_controlplane password=..."
export MITATEDB_CREDENTIAL_PEPPER="..." MITATEDB_CONTROL_CREDENTIAL_PEPPER="..."
python -m mitatedb_api.ops reset   # step 1 of 2: declares the required phrase, touches nothing
python -m mitatedb_api.ops reset --confirm '<the printed required_confirmation phrase>'
```

This is idempotent to re-run in the sense that a second `reset` still
succeeds (it revokes whatever is currently active and mints a new one
again) -- but each invocation's own declare-and-echo phrase is a fresh
digest over the currently-active credential id set (`_reset_confirmation_
phrase`), so a phrase captured from one `reset` attempt does not carry over
to a later one. Save the newly printed `credential_id`/`secret` (shown
exactly once) somewhere durable immediately.

### Step 4 -- self-rotate the new credential before using it further

The credential `reset` just minted is `must_rotate: true` -- it can do
nothing besides `control_capabilities` and self-`rotate-credential` until
rotated:

```sh
export MITATEDB_CONTROL_CREDENTIAL_ID='<credential_id from step 3>'
export MITATEDB_CONTROL_CREDENTIAL_SECRET='<secret from step 3>'
python -m mitatedb_api.ops rotate-credential "$MITATEDB_CONTROL_CREDENTIAL_ID"
```

Update `MITATEDB_CONTROL_CREDENTIAL_ID`/`_SECRET` to the freshly rotated
secret from this step's own output before continuing.

### Step 5 -- reissue and redistribute what the attacker revoked

For every `revoke_credential` row in step 2's own audit export whose
target you do not recognize as your own legitimate action, that
credential is gone permanently (`SI-13`, un-revoke does not exist
anywhere in this codebase) -- issue a fresh one and redistribute it to
that credential's own legitimate consumer:

```sh
python -m mitatedb_api.ops list-applications   # confirm the application_id is still the one you expect
```

then issue the replacement in-band (`/control/v1 issue_credential`, once
the control service is redeployed/confirmed healthy again) rather than
through the break-glass CLI (WP-6's own break-glass scope is deliberately
the six operations named in the design's §3 WP-6 row -- `issue_credential`
stays an ordinary in-band operation, not a break-glass one).

### Step 6 -- revoke and reissue anything the attacker itself issued or rotated

Every `issue_credential`/`rotate_credential` row in step 2's own export
attributable to the compromise window is a reach vector that survives
step 3 (resetting the CONTROL credential does not touch APPLICATION
credentials at all) -- revoke each one and issue/redistribute a clean
replacement the same way as step 5:

```sh
python -m mitatedb_api.ops revoke-credential <credential_id>
```

(No `--confirm` needed -- an application credential's revocation is never
gated, per this document's own §"Why this is bounded" point 1.)

### Step 7 -- restore the control service

Redeploy/resume traffic to the control Cloud Run service if you stopped it
in step 1, and flip `MITATEDB_CONTROL_PLANE_STATUS` back to `enabled` on
the data service in the same change (`cloud-run-cloud-sql.md` invariant 3,
reversed). Confirm `GET /v1/capabilities` on the data service and `POST
/control/v1/capabilities` on the control service both report the state you
expect before considering the incident closed.

## §5 -- the two more severe incident classes this document does not cover

- **Control-plane pepper or `mitatedbsvc_controlplane` DSN leaked**
  (infrastructure secret, not a credential row): `reset` alone does not
  help here -- a party holding the DSN can connect to `mitatedb_platform`
  directly and, while it still cannot bypass `control_audit`'s own
  INSERT-only grant or reach `mitatedbsvc_provision`'s own DDL privileges,
  it CAN read `control_credentials`' digests (though not recover a secret
  from a digest) and read/write `applications`/`credentials` directly,
  bypassing `ControlPlaneService` entirely -- including its audit trail.
  Rotate the leaked secret in Secret Manager, redeploy the control service
  with the new DSN/pepper, then run this document's own recovery sequence
  above as a precaution (you cannot fully trust `control_audit`'s
  completeness for the window the DSN was exposed, since a direct
  connection could have written to `applications`/`credentials` without
  going through `ControlPlaneService`'s own audit-append step at all).
- **`mitatedbsvc_provision` DSN leaked**: categorically worse (that role
  can `CREATE`/`DROP DATABASE`/`ROLE` -- the provisioning/deprovisioning
  surface itself). Rotate it immediately (`ALTER ROLE mitatedbsvc_provision
  PASSWORD ...` as the Cloud SQL bootstrap superuser-equivalent, `cloud-
  run-cloud-sql.md` §3.1) and treat every database/role on the instance as
  needing an integrity review -- this is outside what any CLI subcommand
  in this codebase can remediate on its own.
