# Truthful Deterrence Declarations (真実性抑止宣言)

- Status: implemented on the r2db-api control plane (design `docs/design/R2DB_CCR14_CONTROL_PLANE_V1.md` R-11/§2, adopted v1.3, implemented WP-3). This document names the pattern and is its first-class description; the design document remains the normative source for r2db-api.
- Preservation: this mechanism and its records were explicitly ordered preserved by the requester (see `docs/work-orders/CCR14_DESIGN_PHASE_RECORD_20260829.md`). Do not remove it, or this document, in refactoring.

## The pattern in one paragraph

An API cannot judge intent: a hostile request and a legitimate one are byte-identical. What an API *can* do is attach **true statements** to its refusals — statements chosen so that the AI agent reading them is prompted to warn the human it works for. This repository's client integrators are assumed to be AI agents ("declarations are reliably read" — the same premise that drives its declare-the-hazard contract design). That premise cuts both ways: a careless integrator's agent reads the declaration and asks its operator "is this intended?"; an attacker driving the API through an AI agent finds that the agent balks or warns. The safety filter we cannot put in our API fires **inside the caller's own tooling**.

## The declarations (verbatim, conformance-testable literals)

Control-plane refusals carry `details.audited: true` plus one of two attribution declarations — the attributed form is used **only** when the denial's durable audit row actually names a credential (truthfulness by construction; an unattributed denial must not claim attribution):

> "This request is durably recorded; not even a control credential can erase that record."

> "This request is durably recorded and attributed to the credential that made it; not even a control credential can erase that record."

A `role=control` in-band issuance refusal additionally carries the futility declaration:

> "No in-band path exists to create a control credential; issuance is limited to the operator bootstrap/reset ceremony, with no exceptions."

Every statement is true and enforced elsewhere: denial events are durably recorded before the refusal is returned (if the durable write fails, the whole response degrades to 503 rather than claim a record that does not exist), the audit table accepts only INSERT from the control-plane role, and control-credential creation is closed in-band at the HTTP, service, and database-GRANT layers.

A sibling set of steering declarations belongs to the destructive-confirmation protocol (ruled 2026-08-29, `spec/CCR_DISPOSITION.md` dependent judgment 6; contract 1.2.0, **landed**: r2db-api's data/schema plane and control plane both effectivized this WP, `docs/design/DESTRUCTIVE_CONFIRMATION_V1.md` R-2/R-3): a destructive refusal declares the canonical confirmation phrase (`required_confirmation`, freshly recomputed per request — never a stored token) together with the `consequence`, the **reversible alternative** (`reversible_alternative`, `null` when none genuinely exists — e.g. `delete`/`drop_entity`), and the **recovery path** (`recovery`, e.g. `create_index` fully restores a dropped index; the out-of-band reset ceremony recovers a revoked last control credential) — steering a faithfully compliant agent toward the reversible action. The last-active-control-credential revoke gate's own denial additionally carries `audited: true`/`attribution` (this document's own R-11 declarations, above) on the same `details` mapping, since that denial goes through the identical durably-recorded `_deny` path.

## Where it fires — and where it cannot

1. **Trial calls during development** (primary): an agent building against this API tests its code, receives a refusal, and reads the declaration in the response.
2. **Reading the documentation**: this document and the design records make the declared facts discoverable before any code is written.
3. **Operations**: a refusal surfacing in logs or in an operating agent's context triggers the same reading.

Not covered: clients that discard error bodies, and clients not driven by an AI at all. This is why deterrence is a **bonus layer that safety never depends on**. The load-bearing defenses are structural: no in-band persistence path for control credentials, unerasable attributed audit, full reversibility of everything except revocation (which destroys only credentials, never data), and operator reset as bounded recovery.

## Calibrated expectation (set by the requester, 2026-08-29)

The intended effect is deliberately modest: **the caller-side agent raises a warning or asks for confirmation**. That is enough to make a careless human careful, and to make the system look tedious and unrewarding to a hostile one. No stronger claim is made.

## Hard constraints

- **Truth only.** Bluffing, honeypots, fake successes, and capability claims the implementation does not enforce are forbidden — this repository's conformance regime tests that declared behavior *is* actual behavior, and a false deterrence declaration would break that covenant at its root.
- **No internal disclosure** (SI-10): the declarations are fixed literals that reveal no architecture beyond what the refusal itself implies.
- **Fixed wording**: the strings are verbatim literals asserted by tests. Changing them is a supervised change, not copy-editing.

## Open verification candidate

The calibrated expectation is empirically testable: present the real refusal payload, with and without the declarations, to a range of AI models in an "you are the integrating agent — proceed?" scenario, and compare warning rates. Recorded as a future-work candidate; not yet performed.
