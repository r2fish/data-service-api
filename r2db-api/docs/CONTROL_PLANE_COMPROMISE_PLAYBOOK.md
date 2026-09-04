# r2db-api control-plane compromise/misuse playbook

Status: operator playbook, implementation-local to `r2db-api` (this
document names `r2db-api`-specific CLI operations and role/table names; a
peer implementation's own equivalent recovery lives in its own docs, not
here). Companion to `docs/design/R2DB_CCR14_CONTROL_PLANE_V1.md` R-11
("誤配・侵害への装備"), `security/CONTROL_MAPPING.md` (R-11 boundedness
statement, R-3/R-6 row references), and
`r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md` §§11-13 (control-plane
storage, the bootstrap/reset ritual, and lockout recovery -- this document
assumes that material, and does not repeat it).

## When to use this document

A control credential -- the one secret that authenticates against
`/control/v1` -- has reached, or is suspected to have reached, a party who
should not hold it: handed to a test/staging application by mistake, leaked
through a log, copied into the wrong secret store, or taken by an attacker.
This document does not attempt to distinguish "genuinely malicious" from
"an honest mistake" -- R-11's own confirmation-layer boundary
(`R2DB_CCR14_CONTROL_PLANE_V1.md` §0.5) already establishes that no in-band
mechanism, confirmation dialog included, can tell a correctly-credentialed,
correctly-sequenced *unintended* request from a *malicious* one. This
document is the layer that assumes the distinction cannot be made in time,
and bounds the damage regardless of which it turns out to be.

## Why this is a bounded, fully recoverable event

Before the recovery steps: the reason this playbook exists as a short,
mechanical procedure rather than an open-ended incident response is that
the design already constrains what a compromised control credential can do
to three properties, independent of how the recovery is carried out.
**(D-5, WP-6 review MA-4)**: this section states these properties precisely
scoped, refining wording an earlier revision of this document overclaimed --
see `security/CONTROL_MAPPING.md`'s own R-11 section for the same
correction stated once, and `docs/design/R2DB_CCR14_CONTROL_PLANE_V1.md`
§15 for the record of the review that found it.

1. **Reversibility is real but not unconditional -- `revoke` is the one
   irreversible action, and it reaches further than "just the credential
   itself."** `disable`d applications recover with `enable`; a bogus
   application registration is terminated with `disable` (v1 has no
   application-deletion path *a control credential can reach* at all --
   nothing a stolen control credential does to `applications` is
   unrecoverable). Application data is never destroyed by any
   control-plane operation, full stop. But **`revoke` on an *application*
   credential is a real, permanent, and reachable action for a compromised
   control credential to take** -- `POST /control/v1/credentials/{id}/revoke`
   accepts an application-credential id exactly as readily as a legitimate
   operator's own use of it does, and a revoked application credential
   never authenticates again. That is not a data-destroying action (no
   Application data is touched), but it is a genuine **availability harm**:
   every legitimate consumer of that credential needs a freshly issued
   replacement, redistributed to it, before it can authenticate again --
   real operational work, not a free rollback. Recovering from a
   compromise therefore is not only "revoke what the attacker issued," it
   may also be "re-issue and redistribute what the attacker revoked."
   (For the mechanics of issuing that replacement secret in its current,
   1.6.0 locator wire form, see `POSTGRES_PROVISIONING_RUNBOOK.md` §12a.)
2. **The evidence cannot be erased, including by the credential itself.**
   `control_audit` is INSERT-only from the control-plane process' own role
   (`r2dbsvc_controlplane` -- 0006's GRANT structure, R-3); a stolen control
   credential authenticates *as* that role's application-level identity,
   never as the schema owner, so it can never reach an UPDATE/DELETE on this
   table regardless of which operation it calls. Denied requests are
   durably recorded too (R-6) -- a locked-out legitimate operator's own
   failed attempts are themselves a detection signal, visible in the same
   audit trail.
3. **The credential cannot be multiplied.** Issuance of a `role=control`
   credential has exactly one path -- the out-of-band bootstrap/reset
   ritual (design "案B") -- and no in-band operation, including ones a
   stolen control credential can call, creates another one. `reset`
   revokes every live control credential and mints exactly one new one,
   atomically; an attacker cannot out-run it by having minted spares.

Put together: the residual harm from a control-credential compromise is
bounded to (a) whatever data-plane reach the *application* credentials
**issued or rotated** during the compromise window provide, until revoked
(a rotated pre-existing credential's new secret may be known to whoever
held the compromised control credential, exactly as much a reach vector as
a freshly issued one -- step 3 below treats both the same way); (b) the
**availability harm** from any application credential the compromised
control credential revoked -- recovering means re-issuing and
redistributing a replacement to every affected consumer (again, see
`POSTGRES_PROVISIONING_RUNBOOK.md` §12a for the current wire form), not
merely noting that it happened; and (c) the operational disruption of the
recovery itself (a brief window where the old control credential and any
of its in-flight operations stop working). Nothing about a compromised
control credential is a route to unbounded, undetectable, or
self-perpetuating access -- but (b) in particular is not free to recover
from, and step 3 below is where it is addressed.

## Recovery sequence

Run these in order. Steps 2-4 are idempotent to re-run if interrupted.
**Step 1's confirmed invocation (`reset --confirm ...`) is not** -- see its
own note below; run it once per incident, not on every retry. (Step 1's
first, unconfirmed/declaration invocation carries no such restriction --
see that step's own note.)

**Prerequisite, checked once at the start, not per step**: steps 1/2
authenticate to PostgreSQL as `r2dbsvc_control` (`R2DB_CONTROL_DSN`) and, for
step 1 only, additionally need `R2DB_CONTROL_CREDENTIAL_PEPPER` (the
control-plane pepper). **Step 3's `revoke-credential` additionally requires
`R2DB_CREDENTIAL_PEPPER` -- the *application-plane* pepper, the same value
`r2db_api.main` is configured with, not the control-plane pepper used in
step 1.** `PostgresCredentialStore` (the class every application-credential
subcommand uses) refuses to construct without it, even though `revoke`
itself never computes a verifier from a secret. Whoever is responding to a
control-credential compromise does not necessarily already hold this value
-- it belongs to a different plane's secret material, plausibly a different
vault entry or a different on-call rotation -- so have it ready *before*
starting step 3, not discovered mid-incident as a blocker.

### 1. Revoke every control credential and mint a fresh one

**Q-1 WP-4 (design docs/design/DESTRUCTIVE_CONFIRMATION_V1.md R-4): `reset`
is genuinely destructive (it revokes every existing control credential) and
is now gated by this contract's declare-and-echo confirmation protocol --
it is a two-step invocation, not one:**

```
# Step 1: declaration -- no --confirm, so this is refused: exit code 2 *and*
# the declaration (the exact phrase to echo, plus consequence/reversible_
# alternative/recovery) printed as one line of JSON on stderr. Nothing is
# touched at all: no credential is revoked, no new one is issued. (Exit
# code 2 alone does not mean this -- `argparse` usage errors and this
# CLI's other `_die`-based failures also exit 2; only the JSON-on-stderr
# shape identifies this specific refusal.)
R2DB_CONTROL_DSN=... R2DB_CONTROL_CREDENTIAL_PEPPER=... python -m r2db_api.ops reset

# Step 2: echo the declared phrase back verbatim -- THIS is the invocation
# that actually revokes every control credential and mints a fresh one.
R2DB_CONTROL_DSN=... R2DB_CONTROL_CREDENTIAL_PEPPER=... \
  python -m r2db_api.ops reset --confirm RESET_CONTROL_CREDENTIALS
```

**The first, unconfirmed invocation above is the declaration step, not an
attempt at the ritual itself -- `reset` has not run, and nothing has been
revoked, until step 2 succeeds.** This matters for this playbook's own
"run once per incident" rule below: the declaration step is always safe to
run, any number of times, including as a first action the instant a
compromise is suspected and before anything else in this document -- it
reads/writes nothing (`RESET_CONTROL_CREDENTIALS` is a fixed phrase needing
no database state to compute). Only step 2, the confirmed invocation, is
the one-time, non-idempotent action the note below is about.

Step 2 is the step that ends the compromised credential's ability to
authenticate, immediately -- `reset` revokes **every** existing control
credential (not only the one believed compromised; if more than one is
live, or which one leaked is not certain, this closes all of them without
needing to identify the right one first) and issues exactly one new one,
atomically, in the same transaction. The new credential is `must_rotate =
true` -- see `POSTGRES_PROVISIONING_RUNBOOK.md` §12 to complete its first
rotation before relying on it for anything beyond
`GET /control/v1/capabilities` and self-rotate.

Do this first, before investigating -- every minute the old credential
remains live is a minute it can keep issuing application credentials or
disabling applications. Investigation (steps 2-3 below) does not need the
old credential to still work; `control_audit` already has everything it
recorded.

**Step 2 (the confirmed invocation) is not idempotent -- run it once per
incident.** A confirmed `reset` that already succeeded prints a credential
you are meant to save and use; re-running the confirmed invocation again
after that success revokes *that* credential too and mints yet another new
one, discarding the secret you just captured for no reason. Re-run step 2
only if it did not complete (e.g. the connection dropped before it printed
a credential, or the process was killed before exit) -- never as a routine
"make sure" re-run after it already reported success. The declaration step
(step 1) carries no such restriction; running it again, at any time, for
any reason, is always safe.

### 2. Enumerate what happened during the compromise window

```
R2DB_CONTROL_DSN=... python -m r2db_api.ops audit-report --since <estimated-compromise-start> [--until <estimated-compromise-end-or-now>]
```

Prints one JSON object per line (JSON Lines), oldest first, for every
durable `control_audit` event whose `occurred_at` falls in that window --
every credential lifecycle change, application lifecycle change, and denied
request (including ones the compromised credential itself triggered and
ones a legitimate operator's own locked-out attempts produced) that the
control plane recorded. Read-only; this step does not require the
now-revoked credential and cannot be blocked by anything the compromised
credential did.

If the compromise start time is not known precisely, start the window
generously early (better to review a few extra, clearly-legitimate events
than to miss the actual start) -- this report is for a human to read, not
an automated all-clear signal.

### 3. Revoke every application credential issued during the window

**RESOLVED, phase 3.5 WP-1/WP-4 (dated addendum, 2026-08-31, house style --
original text below kept for record):** the contract's `audit.fields` now
carries a 13th column, `target_id`, an optional field naming the single
target credential/application a lifecycle event acted on
(`docs/design/PHASE35_CROSS_ENTITY_AND_CONTRACT_130_V1.md` §1-C/§4;
`security/CONTROL_MAPPING.md`'s SI-14 row). Step 2's `audit-report` output
now includes `target_id` on every `issue_credential`/`rotate_credential`
row, populated with the affected credential's own id
(`r2db-api/tests/test_control_plane_service.py::
test_target_id_populated_for_application_and_credential_lifecycle_events`).
The mechanical step is now:

```
jq -r 'select(.operation == "issue_credential" or .operation == "rotate_credential") | .target_id' <audit-report output>
```

to produce the exact list of credential ids to revoke directly from step
2's own report -- no cross-referencing against current state is required
for this step any longer. The `list-credentials` cross-reference below is
retained as a fallback (useful when investigating an event recorded before
this phase, or when corroborating `target_id` against current credential
state), not because it is still load-bearing for a post-phase-3.5 incident.

**Original gap description (now closed, kept verbatim for record):** a
`control_audit` row for an `issue_credential`/`rotate_credential`/etc. event
has no `target_id` field at all -- the contract's own `audit.fields` (12
named columns) has no column that names *which* credential a lifecycle
event changed (`security/CONTROL_MAPPING.md`'s SI-14 row and
`docs/design/R2DB_CCR14_CONTROL_PLANE_V1.md` §12.4 both record this as a
contract-additive candidate, not yet resolved). This means step 2's report
alone cannot mechanically produce "here is the exact list of credential ids
to revoke" -- it can only tell you *that* N credential-issuance events
happened, for which application(s) (`application_id` is present), in what
order, at what times.

Fallback cross-reference with current state (see the resolution above --
not required for a normal post-phase-3.5 incident):

```
R2DB_CONTROL_DSN=... python -m r2db_api.ops list-credentials
```

(`list-credentials` needs only `R2DB_CONTROL_DSN` -- it is a read-only
listing and computes no verifier.) For each application named in step 2's
`issue_credential`/`rotate_credential` events during the compromise window,
find its credential row(s) by `created_at`/`application_slug` proximity to
the audit event's own `occurred_at` (or, now, directly by `target_id`), then:

```
R2DB_CONTROL_DSN=... R2DB_CREDENTIAL_PEPPER=... python -m r2db_api.ops revoke-credential <credential_id>
```

(`R2DB_CREDENTIAL_PEPPER` here is the *application-plane* pepper -- see the
prerequisite note at the top of this section.)

for every one that was issued (or rotated -- a rotation during the window
means the *pre-existing* credential's secret changed to one the compromised
control credential's holder may know) inside the window. When in doubt
about whether a given application credential was touched during the
window, revoke it -- issuing a fresh one afterward for a legitimately
affected application is a normal, low-cost operation
(`issue-credential <slug> <runtime|developer>`), unlike leaving a
possibly-compromised one live.

**Also check step 2's report for `revoke_credential` events during the
window.** Unlike disabling (step 4 below), there is no un-revoke (SI-13) --
if the compromised control credential revoked an application credential
that should not have been revoked, the only recovery is issuing a fresh
one for the same application/role and redistributing it to whatever
consumer held the old one:

```
R2DB_CONTROL_DSN=... R2DB_CREDENTIAL_PEPPER=... python -m r2db_api.ops issue-credential <slug> <runtime|developer>
```

This is the availability harm noted above -- there is no shortcut around
redistributing the new secret to every legitimate consumer that needs it.

### 4. Re-enable any application disabled during the window that should not have been

Step 2's report also surfaces `disable_application`/`enable_application`
events. For any application the compromised credential disabled that was
not actually meant to be disabled:

```
R2DB_CONTROL_DSN=... python -m r2db_api.ops enable-app <slug>
```

(`enable-app` needs only `R2DB_CONTROL_DSN` -- no pepper of either kind.)

(`disable`/`enable` are fully reversible and idempotent -- there is no
harm in re-running `enable-app` on an application that was never actually
disabled, beyond a no-op.)

## Sandbox rules

- **Never let an application hold a control credential.** A control
  credential authenticates against `/control/v1`, which no application
  needs to reach at all (SI-02) -- if a test harness, a demo, or a real
  application's own configuration ever needs a secret from this platform,
  it needs an *application* credential (`issue-credential`), never a
  control credential. The single most common way a control credential
  reaches the wrong hands is a person copying it into the wrong place by
  habit (the design's own working assumption, R-11) -- there is no code
  control against that; the control is never generating that habit's
  opportunity in the first place.
- **Test and practice this playbook on a dedicated platform database**, not
  a shared or production one. Standing one up is cheap: one fresh
  `r2dbsvc_platform`-equivalent database (§1-§11 of
  `POSTGRES_PROVISIONING_RUNBOOK.md`, under a throwaway prefix) plus one
  `bootstrap` ritual run is a complete, isolated control plane to rehearse
  against -- there is no shared state to contaminate between a practice run
  and a real deployment.
- **Do not run multiple live control credentials as standing practice**
  (design R-11's own recommendation). A second "spare" control credential
  does not meaningfully speed up recovery (`reset` recovers from a single
  compromised credential exactly as fast as from one of several) and does
  strictly increase the number of secrets someone could separately
  compromise or misplace. If an operator ever needs two people to be able
  to act independently, prefer two people who both know they will use the
  *same* credential material through agreed channels, not two separately
  minted control credentials.

## What this playbook does not cover

- **A compromised `r2dbsvc_control` operating-system-level credential** (the
  role the bootstrap/reset ritual and break-glass CLI themselves connect
  as) is a materially different, larger event -- that credential can create
  new control credentials directly at the database level, bypassing the
  in-band "案B" restriction entirely, and can alter/erase `control_audit`
  itself (it is that table's schema owner). Recovering from that is a
  cluster-credential-rotation problem (rotating `r2dbsvc_control`'s own
  PostgreSQL password, per whichever DB-authentication posture
  `r2db-api/deploy/DEPLOYMENT_RUNBOOK.md` §3 documents), not something this
  document's steps address.
- **Q-1's destructive-confirmation mechanism** (the confirmation-phrase
  scheme for `revoke_credential`, `spec/CCR_DISPOSITION.md` subordinate
  ruling 6) is, as of this document, still dormant in the deployed contract
  (contract 1.1.0; see `docs/design/R2DB_CCR14_CONTROL_PLANE_V1.md` §0.5)
  -- it is not part of this recovery sequence's own steps regardless of
  when it activates, since §0.5 itself already establishes that no in-band
  confirmation mechanism defends against the scenario this playbook exists
  for (a correctly-credentialed, correctly-sequenced request from the wrong
  hands).
