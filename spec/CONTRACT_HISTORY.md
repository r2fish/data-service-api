# Contract JSON provenance companion (`CONTRACT_HISTORY.md`)

This file is the provenance companion for `spec/data-service-api.v1.json`, placed per phase 8 design decision D-4 and requester ruling U-2 = (A) (`docs/design/PHASE8_EFFECTIVE_BOUNDS_AND_HYGIENE_V1.md` §3 D-4, §5 U-2). Every value in the contract JSON that carries a provenance marker (a "Since 1.x.y", "subordinate ruling N", or similar phrase identified by the scanner this file's register test embeds) gets one `## <json_path>` section below, naming: (i) that value's full text, copied verbatim (the provenance marker is embedded within it, not extracted from it), (ii) the `spec/CCR_DISPOSITION.md` subordinate ruling the marker refers to, and (iii) the contract version that introduced it.

**Update convention:** when a newly written value in the contract JSON carries a new provenance marker, add its `## <json_path>` section to this file in the same commit that adds the marker to the contract. The register test (`conformance-tests/test_contract_history_register.py`) fails the collected suite red until the two sets (scanner-found JSON paths, and this file's section headings) agree exactly, so an added marker without a matching section here cannot pass unnoticed.

**Limitations of this method (read before treating this file as "the contract's history moved out"):**

1. ~~The contract JSON's own length does not shrink by even one character.~~ **Revision note (contract 1.7.0, R-10 (B), `spec/CONTRACT_HISTORY_MANIFEST.json`):** this was true through contract 1.6.0 only. Contract 1.7.0 removes the provenance-marker prefix or embedded clause from 26 of the 29 values named in limitation 3 below (`spec/CONTRACT_HISTORY_MANIFEST.json`'s non-`unstripped` entries), which is why this companion's `## <json_path>` sections below now hold the pre-1.7.0 text (the manifest reconstructs it byte-for-byte from today's live contract value) rather than a live quote of the current contract. The remaining 3 values (`unstripped: true`) are unchanged by 1.7.0 and this companion's original limitation still applies to them unmodified: their own text still carries the marker inline, at full length, because the normative sentence and the marker are not mechanically separable in those 3 cases (`spec/CONTRACT_HISTORY_MANIFEST.json`'s `reason` field for each).
2. There is no in-band reference from inside the contract JSON to this file -- the contract JSON carries no key pointing here, by design (the contract's own additive-key discipline is preserved). The only two reachability paths are `spec/README.md` and this file's own existence under `spec/`. This is deliberately **"one hop from the `spec/` directory"**, not "one hop from the contract JSON" -- a reader who opens `spec/data-service-api.v1.json` alone, without also looking at what else lives in `spec/`, has no way to discover this file from the JSON's own content.
3. ~~This phase leaves 29 provenance-marker-carrying values inside the contract JSON body ... none of the marker text can be moved out of the contract without rewriting the normative sentence it lives in.~~ **Revision note (contract 1.7.0, R-10 (B)):** this was true through contract 1.6.0 only. Contract 1.7.0 mechanically separated the provenance-marker prefix or embedded clause from the surrounding normative sentence for 26 of these 29 values -- without rewriting a single word of the normative sentence itself (`spec/CONTRACT_HISTORY_MANIFEST.json` records, per `json_path`, exactly what was removed; applying it in reverse to today's live contract value reconstructs the original 1.6.0-and-earlier text byte-for-byte, verified by a one-time deep-equal check, docs/work-orders/WORK_ORDER_PHASE9_CONTRACT_170_V1.md §2 WP-1 (4)) -- and removed it from the contract JSON body. The remaining 3 values genuinely cannot be so separated (see limitation 1's revision note above) and stay exactly as limitation 3 originally described. The count of markers still living in the contract body is therefore 3, not 29, as of contract 1.7.0; the original count of 29 (`docs/design/PHASE8_EFFECTIVE_BOUNDS_AND_HYGIENE_V1.md` Appendix A §A.2c) was the pre-1.7.0 figure.

See `docs/design/PHASE8_EFFECTIVE_BOUNDS_AND_HYGIENE_V1.md` §3 D-4 and §5 U-2 for the full decision record, and its Appendix A for the verbatim marker inventory this file was built from. Option (B) (stripping the marker prefixes/clauses out of the contract body) was out of scope for phase 8 and was carried out in phase 9 (contract 1.7.0, `docs/design/PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md` §3 D-9) per that same ruling; see `spec/CONTRACT_HISTORY_MANIFEST.json` for the resulting strip/insert manifest.

## audit.query_cursor

**Value (verbatim; copied from the contract JSON as it read before contract 1.7.0's R-10 (B) prefix/insert removal, `spec/CONTRACT_HISTORY_MANIFEST.json` -- applying that manifest entry's `stripped_prefix`/`stripped_insert` to today's live contract value at this path reconstructs this exact quote byte-for-byte; for the 3 `unstripped: true` entries there was nothing to remove, so this quote and today's live contract value are the same string):**

> Since 1.4.0 (subordinate ruling 9, item 1, conditional): AuditQueryRequest.after is an opaque cursor, not an event_id or a numeric offset -- a client never constructs one itself, only echoes back the cursor field of the last event it received (query_event_fields_note). A cursor that fails to decode, or that no longer resolves under the request's own filters, is refused with VALIDATION_FAILED. A cursor obtained under one set of filters is valid only when reused with that same set of filters; reusing it under different filters is not defined by this version.

**Subordinate ruling:**
- 従属判断 9

**Introduced in:** contract 1.4.0

---

## audit.query_event_class_vocabulary

**Value (verbatim; copied from the contract JSON as it read before contract 1.7.0's R-10 (B) prefix/insert removal, `spec/CONTRACT_HISTORY_MANIFEST.json` -- applying that manifest entry's `stripped_prefix`/`stripped_insert` to today's live contract value at this path reconstructs this exact quote byte-for-byte; for the 3 `unstripped: true` entries there was nothing to remove, so this quote and today's live contract value are the same string):**

> Since 1.4.0 (subordinate ruling 9, item 4, conditional): event_class is a vocabulary each implementation declares for itself, at capabilities().audit_query.event_classes -- this contract does not enumerate a fixed event_class enum, and does not require an implementation's declared vocabulary to include any particular member (declare-the-hazard, matching audit.fields' own additive-vocabulary posture rather than capability_status.defined's closed status_enum).

**Subordinate ruling:**
- 従属判断 9

**Introduced in:** contract 1.4.0

---

## audit.query_event_fields_note

**Value (verbatim; copied from the contract JSON as it read before contract 1.7.0's R-10 (B) prefix/insert removal, `spec/CONTRACT_HISTORY_MANIFEST.json` -- applying that manifest entry's `stripped_prefix`/`stripped_insert` to today's live contract value at this path reconstructs this exact quote byte-for-byte; for the 3 `unstripped: true` entries there was nothing to remove, so this quote and today's live contract value are the same string):**

> Since 1.4.0 (subordinate ruling 9, items 1 and 3, conditional): each event AuditResult.events[] returns from audit_query MAY carry fields beyond audit.fields -- plane (control or application: the durable source the event was read from, never a value the original event-writer could itself set), recorded_at (when the event became durable, distinct from the emission-time occurred_at already in audit.fields), cursor (this event's own opaque position, suitable for a later after), and count (present only on an event representing more than one coalesced occurrence, absent -- never zero or one -- otherwise). AuditResult.events[] remains an open per-event shape (subordinate ruling 7(A)), so none of these are a schema-breaking addition.

**Subordinate ruling:**
- 従属判断 9

**Introduced in:** contract 1.4.0

---

## audit.query_operation_vocabulary

**Value (verbatim; copied from the contract JSON as it read before contract 1.7.0's R-10 (B) prefix/insert removal, `spec/CONTRACT_HISTORY_MANIFEST.json` -- applying that manifest entry's `stripped_prefix`/`stripped_insert` to today's live contract value at this path reconstructs this exact quote byte-for-byte; for the 3 `unstripped: true` entries there was nothing to remove, so this quote and today's live contract value are the same string):**

> Since 1.5.0 (subordinate ruling 10, item 1, conditional): operations and target_kinds are vocabularies each implementation declares for itself at capabilities().audit_query.operations / .target_kinds -- the sets of values the operation and target_kind fields of events returned by audit_query can take. As with event_classes, this contract enumerates no fixed enum and requires no particular member (declare-the-hazard). An implementation declaring 1.5.0 or higher whose audit_query is other than unavailable MUST declare both, and every event it returns MUST carry values drawn from the declared sets; the same superset relation holds for event_classes, stated here explicitly. audit_query.operations is the vocabulary of the audit row's operation field and is unrelated to capability_status.defined.atomic_mutation.operations, which enumerates the executable mutation verbs.

**Subordinate ruling:**
- 従属判断 10

**Introduced in:** contract 1.5.0

---

## audit.query_ordering

**Value (verbatim; copied from the contract JSON as it read before contract 1.7.0's R-10 (B) prefix/insert removal, `spec/CONTRACT_HISTORY_MANIFEST.json` -- applying that manifest entry's `stripped_prefix`/`stripped_insert` to today's live contract value at this path reconstructs this exact quote byte-for-byte; for the 3 `unstripped: true` entries there was nothing to remove, so this quote and today's live contract value are the same string):**

> Since 1.4.0 (subordinate ruling 9, item 2, conditional on audit_query being provided -- versioning.version_binding): AuditResult.events[] returned by audit_query is totally ordered by (recorded_at, plane, event_id). plane is included in the ordering key because an implementation may hold more than one durable event source (e.g. a control-plane source and an application-plane source) whose own event_id vocabularies are not mutually unique, so recorded_at and plane together, not event_id alone, are what make the combined order total.

**Subordinate ruling:**
- 従属判断 9

**Introduced in:** contract 1.4.0

---

## audit.query_target_kind_vocabulary

**Value (verbatim; copied from the contract JSON as it read before contract 1.7.0's R-10 (B) prefix/insert removal, `spec/CONTRACT_HISTORY_MANIFEST.json` -- applying that manifest entry's `stripped_prefix`/`stripped_insert` to today's live contract value at this path reconstructs this exact quote byte-for-byte; for the 3 `unstripped: true` entries there was nothing to remove, so this quote and today's live contract value are the same string):**

> Since 1.5.0 (subordinate ruling 10, item 1, conditional): operations and target_kinds are vocabularies each implementation declares for itself at capabilities().audit_query.operations / .target_kinds -- the sets of values the operation and target_kind fields of events returned by audit_query can take. As with event_classes, this contract enumerates no fixed enum and requires no particular member (declare-the-hazard). An implementation declaring 1.5.0 or higher whose audit_query is other than unavailable MUST declare both, and every event it returns MUST carry values drawn from the declared sets; the same superset relation holds for event_classes, stated here explicitly. audit_query.operations is the vocabulary of the audit row's operation field and is unrelated to capability_status.defined.atomic_mutation.operations, which enumerates the executable mutation verbs.

**Subordinate ruling:**
- 従属判断 10

**Introduced in:** contract 1.5.0

---

## capability_status.defined.atomic_mutation

**Value (verbatim; copied from the contract JSON as it read before contract 1.7.0's R-10 (B) prefix/insert removal, `spec/CONTRACT_HISTORY_MANIFEST.json` -- applying that manifest entry's `stripped_prefix`/`stripped_insert` to today's live contract value at this path reconstructs this exact quote byte-for-byte; for the 3 `unstripped: true` entries there was nothing to remove, so this quote and today's live contract value are the same string):**

> Single-entity atomic mutation batches. A capability entry's own operations list names the mutation vocabulary the batch execution surface executes -- not a batch-specific subset distinct from single-operation execution of that same vocabulary (CCR_DISPOSITION.md subordinate ruling 8-F). The capability entry schema (CapabilityDocument.capabilities' additionalProperties) is deliberately open, and operations is a peer-published key within that open shape, not a fixed property of the closed envelope -- a client reading only CapabilityDocument's own schema will not find operations declared there; it discovers the key by reading a real capability document.

**Subordinate ruling:**
- 従属判断 8

**Introduced in:** contract 1.3.0

---

## control_endpoints.audit_query.semantics

**Value (verbatim; copied from the contract JSON as it read before contract 1.7.0's R-10 (B) prefix/insert removal, `spec/CONTRACT_HISTORY_MANIFEST.json` -- applying that manifest entry's `stripped_prefix`/`stripped_insert` to today's live contract value at this path reconstructs this exact quote byte-for-byte; for the 3 `unstripped: true` entries there was nothing to remove, so this quote and today's live contract value are the same string):**

> Added in 1.4.0 (subordinate ruling 9, item 7): this is audit_query's canonical location, moved here from endpoints.audit_query because its only real authority (control or audit) and its only real host (the control surface, per control_plane.separability) are both control-plane-shaped, not application-shaped -- endpoints.audit_query's own path (POST /v1/audit/query) remains valid as an alias of this identical operation for one further minor version after 1.4.0 (endpoints.audit_query.deprecation_note). Application credentials are denied. Emission is a service consequence and cannot be authored by an application caller. Where audit_query is provided at all, this path and its alias resolve to the same handler and the same response; where it is unavailable, both still authenticate and authorize the caller before answering CAPABILITY_UNSUPPORTED (never a bare 404) -- see control_plane.provision and versioning.version_binding's 1.4.0 conditional-obligation list.

**Subordinate ruling:**
- 従属判断 9

**Introduced in:** contract 1.4.0

---

## control_endpoints.revoke_credential.semantics

**Value (verbatim; copied from the contract JSON as it read before contract 1.7.0's R-10 (B) prefix/insert removal, `spec/CONTRACT_HISTORY_MANIFEST.json` -- applying that manifest entry's `stripped_prefix`/`stripped_insert` to today's live contract value at this path reconstructs this exact quote byte-for-byte; for the 3 `unstripped: true` entries there was nothing to remove, so this quote and today's live contract value are the same string):**

> Terminal. A revoked credential can never be made valid again; enable does not apply. Revoking the last remaining active control credential is permitted but requires a valid confirmation per the destructive_confirmation section's definition. Every other revocation -- an application credential, or a control credential that is not the last active one -- requires no confirmation. Resolved in contract 1.2.0 (previously a pending contract decision, the destructive-confirmation semantics question).

**Subordinate ruling:**
- 従属判断 6

**Introduced in:** contract 1.2.0

---

## control_plane.authority

**Value (verbatim; copied from the contract JSON as it read before contract 1.7.0's R-10 (B) prefix/insert removal, `spec/CONTRACT_HISTORY_MANIFEST.json` -- applying that manifest entry's `stripped_prefix`/`stripped_insert` to today's live contract value at this path reconstructs this exact quote byte-for-byte; for the 3 `unstripped: true` entries there was nothing to remove, so this quote and today's live contract value are the same string):**

> Application credentials fail closed on every control endpoint; control credentials are rejected on data/schema endpoints. An audit credential is accepted only on the read-only control_capabilities, list_applications, list_credentials, and (since 1.4.0, subordinate ruling 9) audit_query endpoints; every other control endpoint fails it closed with FORBIDDEN.

**Subordinate ruling:**
- 従属判断 9

**Introduced in:** contract 1.4.0

---

## definitions.EntityDescriptor.properties.field_types.description

**Value (verbatim; copied from the contract JSON as it read before contract 1.7.0's R-10 (B) prefix/insert removal, `spec/CONTRACT_HISTORY_MANIFEST.json` -- applying that manifest entry's `stripped_prefix`/`stripped_insert` to today's live contract value at this path reconstructs this exact quote byte-for-byte; for the 3 `unstripped: true` entries there was nothing to remove, so this quote and today's live contract value are the same string):**

> Since 1.6.0 (subordinate ruling 11, item 3, conditional on application_catalog being provided -- versioning.version_binding): The field-type vocabulary gains a seventh member, json, meaning any JSON value. A field created without a declared type has type json -- this names an existing default rather than introducing a new one, and there is no "unknown" member of the vocabulary: every field carries a real type. EntityDescriptor.field_types maps every name in fields to that field's type, drawn from that same vocabulary. What a client declared -- through SchemaOperationRequest.field_types on create_entity, or field_type on add_field -- is what the catalog reports back, and a field for which no type was declared reports json. Where a schema operation later redeclares a field's type, the catalog reports the type most recently declared. The catalog reports only facts this contract's own schema operations can establish: nullability and enum membership through field_constraints, and neither default values nor a notion of required distinct from nullable: false, because no schema operation defined here establishes either; a later version that gives schema operations such a notion gives it to the catalog in that same version. object and array are narrower than json: a field declared json accepts any JSON value, including but not limited to objects and arrays, while a field declared object or array accepts only that shape -- and the catalog reports the narrower word it was declared with, never rounding it up to json. SchemaOperationRequest.field_types and EntityDescriptor.field_types share one object shape but not one coverage rule: the request's object may be partial -- any name in fields that it omits is created with type json -- while the catalog's object is always total over that entity's own fields. SchemaOperationRequest.field_types is never required: a create_entity naming only fields remains a valid request, creating json fields. A field_types naming a field the request's own fields does not name, a field_types value outside this vocabulary, or a field_types sent without fields, each fails VALIDATION_FAILED; none of the three is silently ignored. add_field continues to carry a single field_type for the single field it adds.

**Subordinate ruling:**
- 従属判断 11

**Introduced in:** contract 1.6.0

---

## definitions.Mutation.properties.values.description

**Value (verbatim; copied from the contract JSON as it read before contract 1.7.0's R-10 (B) prefix/insert removal, `spec/CONTRACT_HISTORY_MANIFEST.json` -- applying that manifest entry's `stripped_prefix`/`stripped_insert` to today's live contract value at this path reconstructs this exact quote byte-for-byte; for the 3 `unstripped: true` entries there was nothing to remove, so this quote and today's live contract value are the same string):**

> Deliberately left open (subordinate ruling 7(A)): the field-name vocabulary is entity-defined, not fixed by this contract, so an additionalProperties: false closure here would be meaningless -- there is no fixed key set to close against.

**Subordinate ruling:**
- 従属判断 7

**Introduced in:** contract 1.2.0

---

## definitions.ScopedMutation.properties.values.description

**Value (verbatim; copied from the contract JSON as it read before contract 1.7.0's R-10 (B) prefix/insert removal, `spec/CONTRACT_HISTORY_MANIFEST.json` -- applying that manifest entry's `stripped_prefix`/`stripped_insert` to today's live contract value at this path reconstructs this exact quote byte-for-byte; for the 3 `unstripped: true` entries there was nothing to remove, so this quote and today's live contract value are the same string):**

> Deliberately left open (subordinate ruling 7(A)): the field-name vocabulary is entity-defined, not fixed by this contract, so an additionalProperties: false closure here would be meaningless -- there is no fixed key set to close against.

**Subordinate ruling:**
- 従属判断 7

**Introduced in:** contract 1.2.0

---

## destructive_confirmation.phrase_construction.rules[3]

**Value (verbatim; copied from the contract JSON as it read before contract 1.7.0's R-10 (B) prefix/insert removal, `spec/CONTRACT_HISTORY_MANIFEST.json` -- applying that manifest entry's `stripped_prefix`/`stripped_insert` to today's live contract value at this path reconstructs this exact quote byte-for-byte; for the 3 `unstripped: true` entries there was nothing to remove, so this quote and today's live contract value are the same string):**

> State-fingerprinted for re-creatable targets: a target identifiable by a name that can be destroyed and later recreated (e.g. an entity or index) includes a state fingerprint in its phrase, so that either the target's re-creation under the same name, or any other schema change, invalidates any previously valid phrase for that name -- recreating the identical structure under the same name after a drop does not resurrect an old phrase's validity.

**Note:** this value carries no dedicated history marker; the scanner matched it on the normative text's "previously" (in "previously valid phrase"). The ruling attribution below was assigned from the value's content, not from a marker.

**Subordinate ruling:**
- 従属判断 6

**Introduced in:** contract 1.2.0

---

## destructive_confirmation.resolved_in

**Value (verbatim; copied from the contract JSON as it read before contract 1.7.0's R-10 (B) prefix/insert removal, `spec/CONTRACT_HISTORY_MANIFEST.json` -- applying that manifest entry's `stripped_prefix`/`stripped_insert` to today's live contract value at this path reconstructs this exact quote byte-for-byte; for the 3 `unstripped: true` entries there was nothing to remove, so this quote and today's live contract value are the same string):**

> 1.2.0. Defines the declare-and-echo confirmation semantics for every destructive operation in this contract, common across data, schema, and control-plane surfaces (CCR_DISPOSITION.md subordinate ruling 6).

**Subordinate ruling:**
- 従属判断 6

**Introduced in:** contract 1.2.0

---

## endpoints.audit_query.deprecation_note

**Value (verbatim; copied from the contract JSON as it read before contract 1.7.0's R-10 (B) prefix/insert removal, `spec/CONTRACT_HISTORY_MANIFEST.json` -- applying that manifest entry's `stripped_prefix`/`stripped_insert` to today's live contract value at this path reconstructs this exact quote byte-for-byte; for the 3 `unstripped: true` entries there was nothing to remove, so this quote and today's live contract value are the same string):**

> Since 1.4.0 (subordinate ruling 9, item 7): this entry's path is retained as an alias of control_endpoints.audit_query for one further minor version after 1.4.0, resolving to the identical operation on the control surface's own host, not this section's application surface. audit_query's canonical classification is control_endpoints.audit_query; a client should prefer POST /control/v1/audit/query going forward. This entry is not removed here (removal would be a non-additive contract change) -- it is retained, unmodified in method/request/response shape, specifically so a pre-1.4.0-shaped client is not broken by the reclassification.

**Subordinate ruling:**
- 従属判断 9

**Introduced in:** contract 1.4.0

---

## limits.audit_requests_per_minute_note

**Value (verbatim; copied from the contract JSON as it read before contract 1.7.0's R-10 (B) prefix/insert removal, `spec/CONTRACT_HISTORY_MANIFEST.json` -- applying that manifest entry's `stripped_prefix`/`stripped_insert` to today's live contract value at this path reconstructs this exact quote byte-for-byte; for the 3 `unstripped: true` entries there was nothing to remove, so this quote and today's live contract value are the same string):**

> Since 1.4.0 (subordinate ruling 9, item 8, conditional on audit_query being provided -- versioning.version_binding). A pre-authentication fixed window governing the audit_query endpoint specifically (both its canonical and alias paths, control_endpoints.audit_query/endpoints.audit_query.deprecation_note), separate from control_requests_per_minute: an implementation publishing this class enforces it as audit_query's own window and does not also charge audit_query requests against control_requests_per_minute, so that a high-frequency audit_query poller cannot exhaust the same window a break-glass control-plane operation (e.g. revoke_credential) depends on.

**Subordinate ruling:**
- 従属判断 9

**Introduced in:** contract 1.4.0

**Revision note (contract 1.12.0, subordinate ruling 17, ledger R-114):** the quote above is the 1.4.0 text and is left as it was. Contract 1.12.0 changes the live value at this path: the word "fixed" is withdrawn from its first sentence and two sentences are appended ("This contract does not define the shape of that window: ..." and "A client does not rely on where a window begins or ends."), because both peers have counted this class over a sliding window since they first implemented it and the contract's word "fixed" did not describe either peer. `spec/CONTRACT_HISTORY_MANIFEST.json`'s entry for this path gains a `rewrite` whose `from` is the whole pre-1.12.0 live value and whose `to` is the whole 1.12.0 live value, so that reverse-applying the manifest to today's live value still reconstructs the quote above byte-for-byte. The new live value carries no provenance marker of its own (the marker scanner finds 0 hits on it).

---

## schemas.AuditResult.properties.events.items.description

**Value (verbatim; copied from the contract JSON as it read before contract 1.7.0's R-10 (B) prefix/insert removal, `spec/CONTRACT_HISTORY_MANIFEST.json` -- applying that manifest entry's `stripped_prefix`/`stripped_insert` to today's live contract value at this path reconstructs this exact quote byte-for-byte; for the 3 `unstripped: true` entries there was nothing to remove, so this quote and today's live contract value are the same string):**

> Deliberately left open (subordinate ruling 7(A)): audit.fields is itself an open-ended, additive vocabulary, and a per-event shape is not one of the 11 response schemas or nested row schemas this ruling closes.

**Subordinate ruling:**
- 従属判断 7

**Introduced in:** contract 1.2.0

---

## schemas.CapabilityDocument.description

**Value (verbatim; copied from the contract JSON as it read before contract 1.7.0's R-10 (B) prefix/insert removal, `spec/CONTRACT_HISTORY_MANIFEST.json` -- applying that manifest entry's `stripped_prefix`/`stripped_insert` to today's live contract value at this path reconstructs this exact quote byte-for-byte; for the 3 `unstripped: true` entries there was nothing to remove, so this quote and today's live contract value are the same string):**

> The envelope itself is closed (additionalProperties: false at this level), but capabilities/limits/limit_enforcement below and each capability entry's own value schema deliberately keep additionalProperties open: an open key space naming deployment-declared capabilities and limit classes is an intentional, distinct mechanism, not an oversight comparable to the closed response envelopes elsewhere in this contract (subordinate ruling 7(A)).

**Subordinate ruling:**
- 従属判断 7

**Introduced in:** contract 1.2.0

---

## schemas.CapabilityDocument.properties.surfaces.description

**Value (verbatim; copied from the contract JSON as it read before contract 1.7.0's R-10 (B) prefix/insert removal, `spec/CONTRACT_HISTORY_MANIFEST.json` -- applying that manifest entry's `stripped_prefix`/`stripped_insert` to today's live contract value at this path reconstructs this exact quote byte-for-byte; for the 3 `unstripped: true` entries there was nothing to remove, so this quote and today's live contract value are the same string):**

> Since 1.6.0 (subordinate ruling 11, item 2; unconditional -- versioning.version_binding): surfaces names the absolute base URLs at which this deployment's own surfaces are reached, as declared by the deployer -- never derived, and never to be inferred by a client from the URL it happened to use. surfaces.data.base_url ends at versioning.base_path; surfaces.control.base_url ends at versioning.control_base_path. The data surface's capability document and the control surface's own capability document return the same surfaces object, so a client holding either base URL can reach the other surface, and either document, fetched again at its own declared URL, answers with the same contract_version and the same surfaces -- the rest of each document remains scoped to the credential presented. A deployment declaring control_plane as unavailable omits surfaces.control. Neither URL ends in a trailing slash, so that appending a path to it yields exactly one separator. Whether the two surfaces share a host is read from the origins (scheme, host and port -- not the path) of these two URLs -- the co-hosting versioning.control_discovery permits -- and is never assumed; where surfaces.control is absent, the surfaces are not co-hosted. Where the two surfaces run as separate processes, both are configured from the same declaration: neither can verify the other's document, so a deployment whose two documents disagree is non-conformant, and a client is given no rule for preferring one over the other.

**Subordinate ruling:**
- 従属判断 11

**Introduced in:** contract 1.6.0

---

## schemas.CredentialIssued.properties.secret.description

**Value (verbatim; copied from the contract JSON as it read before contract 1.7.0's R-10 (B) prefix/insert removal, `spec/CONTRACT_HISTORY_MANIFEST.json` -- applying that manifest entry's `stripped_prefix`/`stripped_insert` to today's live contract value at this path reconstructs this exact quote byte-for-byte; for the 3 `unstripped: true` entries there was nothing to remove, so this quote and today's live contract value are the same string):**

> Since 1.6.0 (subordinate ruling 11, item 1; unconditional -- versioning.version_binding): CredentialIssued.secret -- and the secret a rotate response returns, wherever this contract defines one -- is the complete bearer token for the surface that credential is for: a client presents that exact string, verbatim, as Authorization: Bearer <secret>; an application credential on the application surface, a control or audit credential on the control surface (security.schemes.control_credential continues to state that application credentials are not accepted there). A client MUST NOT compose it from, split it into, or derive it from any other field of the response -- credential_id is returned as its own field, for naming the credential in later control operations, and is never something a client extracts from the secret. Its internal structure is opaque; an implementation may change that structure without a contract change, and no client may depend on it. The service still stores only a verifier/digest and never returns the secret again.

**Subordinate ruling:**
- 従属判断 11

**Introduced in:** contract 1.6.0

---

## schemas.CredentialRotated.properties.secret.description

**Value (verbatim; copied from the contract JSON as it read before contract 1.7.0's R-10 (B) prefix/insert removal, `spec/CONTRACT_HISTORY_MANIFEST.json` -- applying that manifest entry's `stripped_prefix`/`stripped_insert` to today's live contract value at this path reconstructs this exact quote byte-for-byte; for the 3 `unstripped: true` entries there was nothing to remove, so this quote and today's live contract value are the same string):**

> Since 1.6.0 (subordinate ruling 11, item 1; unconditional -- versioning.version_binding): CredentialIssued.secret -- and the secret a rotate response returns, wherever this contract defines one -- is the complete bearer token for the surface that credential is for: a client presents that exact string, verbatim, as Authorization: Bearer <secret>; an application credential on the application surface, a control or audit credential on the control surface (security.schemes.control_credential continues to state that application credentials are not accepted there). A client MUST NOT compose it from, split it into, or derive it from any other field of the response -- credential_id is returned as its own field, for naming the credential in later control operations, and is never something a client extracts from the secret. Its internal structure is opaque; an implementation may change that structure without a contract change, and no client may depend on it. The service still stores only a verifier/digest and never returns the secret again.

**Subordinate ruling:**
- 従属判断 11

**Introduced in:** contract 1.6.0

---

## schemas.MutationResult.properties.assigned_addresses.items.properties.address.description

**Value (verbatim; copied from the contract JSON as it read before contract 1.7.0's R-10 (B) prefix/insert removal, `spec/CONTRACT_HISTORY_MANIFEST.json` -- applying that manifest entry's `stripped_prefix`/`stripped_insert` to today's live contract value at this path reconstructs this exact quote byte-for-byte; for the 3 `unstripped: true` entries there was nothing to remove, so this quote and today's live contract value are the same string):**

> Deliberately left open (subordinate ruling 7(A)): the address field-name vocabulary is entity-defined (EntityDescriptor.address_fields), not fixed by this contract.

**Subordinate ruling:**
- 従属判断 7

**Introduced in:** contract 1.2.0

---

## schemas.SchemaOperationRequest.properties.field_types.description

**Value (verbatim; copied from the contract JSON as it read before contract 1.7.0's R-10 (B) prefix/insert removal, `spec/CONTRACT_HISTORY_MANIFEST.json` -- applying that manifest entry's `stripped_prefix`/`stripped_insert` to today's live contract value at this path reconstructs this exact quote byte-for-byte; for the 3 `unstripped: true` entries there was nothing to remove, so this quote and today's live contract value are the same string):**

> Since 1.6.0 (subordinate ruling 11, item 3, conditional on schema_operations being provided -- versioning.version_binding): The field-type vocabulary gains a seventh member, json, meaning any JSON value. A field created without a declared type has type json -- this names an existing default rather than introducing a new one, and there is no "unknown" member of the vocabulary: every field carries a real type. EntityDescriptor.field_types maps every name in fields to that field's type, drawn from that same vocabulary. What a client declared -- through SchemaOperationRequest.field_types on create_entity, or field_type on add_field -- is what the catalog reports back, and a field for which no type was declared reports json. Where a schema operation later redeclares a field's type, the catalog reports the type most recently declared. The catalog reports only facts this contract's own schema operations can establish: nullability and enum membership through field_constraints, and neither default values nor a notion of required distinct from nullable: false, because no schema operation defined here establishes either; a later version that gives schema operations such a notion gives it to the catalog in that same version. object and array are narrower than json: a field declared json accepts any JSON value, including but not limited to objects and arrays, while a field declared object or array accepts only that shape -- and the catalog reports the narrower word it was declared with, never rounding it up to json. SchemaOperationRequest.field_types and EntityDescriptor.field_types share one object shape but not one coverage rule: the request's object may be partial -- any name in fields that it omits is created with type json -- while the catalog's object is always total over that entity's own fields. SchemaOperationRequest.field_types is never required: a create_entity naming only fields remains a valid request, creating json fields. A field_types naming a field the request's own fields does not name, a field_types value outside this vocabulary, or a field_types sent without fields, each fails VALIDATION_FAILED; none of the three is silently ignored. add_field continues to carry a single field_type for the single field it adds.

**Subordinate ruling:**
- 従属判断 11

**Introduced in:** contract 1.6.0

---

## security.schemes.application_credential.description

**Value (verbatim; copied from the contract JSON as it read before contract 1.7.0's R-10 (B) prefix/insert removal, `spec/CONTRACT_HISTORY_MANIFEST.json` -- applying that manifest entry's `stripped_prefix`/`stripped_insert` to today's live contract value at this path reconstructs this exact quote byte-for-byte; for the 3 `unstripped: true` entries there was nothing to remove, so this quote and today's live contract value are the same string):**

> Opaque credential presented over TLS. The service stores only a verifier/digest and never returns the secret. Since 1.6.0 (subordinate ruling 11, item 1; unconditional -- versioning.version_binding): CredentialIssued.secret -- and the secret a rotate response returns, wherever this contract defines one -- is the complete bearer token for the surface that credential is for: a client presents that exact string, verbatim, as Authorization: Bearer <secret>; an application credential on the application surface, a control or audit credential on the control surface (security.schemes.control_credential continues to state that application credentials are not accepted there). A client MUST NOT compose it from, split it into, or derive it from any other field of the response -- credential_id is returned as its own field, for naming the credential in later control operations, and is never something a client extracts from the secret. Its internal structure is opaque; an implementation may change that structure without a contract change, and no client may depend on it. The service still stores only a verifier/digest and never returns the secret again.

**Subordinate ruling:**
- 従属判断 11

**Introduced in:** contract 1.6.0

---

## security.schemes.control_credential.description

**Value (verbatim; copied from the contract JSON as it read before contract 1.7.0's R-10 (B) prefix/insert removal, `spec/CONTRACT_HISTORY_MANIFEST.json` -- applying that manifest entry's `stripped_prefix`/`stripped_insert` to today's live contract value at this path reconstructs this exact quote byte-for-byte; for the 3 `unstripped: true` entries there was nothing to remove, so this quote and today's live contract value are the same string):**

> A separately authenticated Control/Audit authority; application credentials are not accepted. The service stores only a verifier/digest; the secret is returned exactly once, at issue or rotate time. An authentication secret is never reused as signing-key or other cryptographic material. Since 1.6.0 (subordinate ruling 11, item 1; unconditional -- versioning.version_binding): CredentialIssued.secret -- and the secret a rotate response returns, wherever this contract defines one -- is the complete bearer token for the surface that credential is for: a client presents that exact string, verbatim, as Authorization: Bearer <secret>; an application credential on the application surface, a control or audit credential on the control surface (security.schemes.control_credential continues to state that application credentials are not accepted there). A client MUST NOT compose it from, split it into, or derive it from any other field of the response -- credential_id is returned as its own field, for naming the credential in later control operations, and is never something a client extracts from the secret. Its internal structure is opaque; an implementation may change that structure without a contract change, and no client may depend on it. The service still stores only a verifier/digest and never returns the secret again.

**Subordinate ruling:**
- 従属判断 11

**Introduced in:** contract 1.6.0

---

## structured_operations.reserved_entity_names_note

**Value (verbatim; copied from the contract JSON as it read before contract 1.7.0's R-10 (B) prefix/insert removal, `spec/CONTRACT_HISTORY_MANIFEST.json` -- applying that manifest entry's `stripped_prefix`/`stripped_insert` to today's live contract value at this path reconstructs this exact quote byte-for-byte; for the 3 `unstripped: true` entries there was nothing to remove, so this quote and today's live contract value are the same string):**

> Since 1.4.0 (subordinate ruling 9, item 6; unconditional -- versioning.version_binding). audit_events is reserved across implementations as an entity/collection name, for platform-managed audit storage an implementation may keep alongside application-declared entities in the same underlying storage. This documents an existing implementation practice (both peers already refuse this exact name defensively) rather than introducing new behavior; a client entity/schema operation naming audit_events is refused (a validation-class error; the exact contract code is implementation-defined) rather than silently colliding with platform storage. This list is additive: a future implementation-shared reserved name may be appended without removing this one.

**Subordinate ruling:**
- 従属判断 9

**Introduced in:** contract 1.4.0

---

## versioning.compatibility

**Value (verbatim; copied from the contract JSON as it read before contract 1.7.0's R-10 (B) prefix/insert removal, `spec/CONTRACT_HISTORY_MANIFEST.json` -- applying that manifest entry's `stripped_prefix`/`stripped_insert` to today's live contract value at this path reconstructs this exact quote byte-for-byte; for the 3 `unstripped: true` entries there was nothing to remove, so this quote and today's live contract value are the same string):**

> Additive fields and capabilities are allowed; removal or semantic change requires a new major version. The control surface follows the same compatibility rules. A response or request schema closure (additionalProperties: false) that narrows what the schema accepts, applied only to stop a schema from implying the existence of a field an implementation does not actually return or accept, is compatible as a minor-version change under version_binding's version-declaration discipline below -- it is not the kind of removal or semantic change that would otherwise require a new major version, because it constrains the documentation of shape rather than removing a previously-required capability or altering accepted semantics.

**Note:** this value carries no dedicated history marker; the scanner matched it on the normative text's "previously" (in "previously-required capability"). The ruling attribution below was assigned from the value's content, not from a marker.

**Subordinate ruling:**
- 従属判断 7

**Introduced in:** contract 1.2.0

---

## versioning.version_binding

**Value (verbatim; copied from the contract JSON as it read before contract 1.7.0's R-10 (B) prefix/insert removal, `spec/CONTRACT_HISTORY_MANIFEST.json` -- applying that manifest entry's `stripped_prefix`/`stripped_insert` to today's live contract value at this path reconstructs this exact quote byte-for-byte; for the 3 `unstripped: true` entries there was nothing to remove, so this quote and today's live contract value are the same string):**

> An implementation's own declared contract_version is the general rule for which version's definitions it is claiming conformance to: only an implementation declaring 1.2.0 or higher claims conformance to the obligations 1.2.0 introduced -- exhaustively: (1) the destructive_confirmation section in full, (2) errors.details_vocabulary's LIMIT_EXCEEDED.limit_class requirement, (3) subordinate ruling 7(A)'s response/request schema closures (additionalProperties: false on every schema and definition this version lists as closed), and (4) capability_status.rules' limits/limit_enforcement vocabulary-restriction rule. Only an implementation declaring 1.3.0 or higher additionally claims conformance to the obligations 1.3.0 introduced (subordinate ruling 8): audit-role acceptance on the three read-only control endpoints (control_capabilities, list_applications, list_credentials) with FORBIDDEN fail-closed on every other control endpoint; the per-application issuance-freeze FORBIDDEN refusal; and the optional target_id audit field and optional must_rotate exposure -- both are optional fields, so declaring 1.3.0 does not require emitting either one, only that their documented semantics hold whenever they are emitted. Only an implementation declaring 1.4.0 or higher additionally claims conformance to the obligations 1.4.0 introduced (subordinate ruling 9). Three of those obligations are unconditional in the same sense as every obligation enumerated above -- they bind simply by declaring 1.4.0, independent of any capability's own status: (a) audit_events is a reserved entity/collection name an implementation may refuse a client schema/collection operation against (structured_operations.reserved_entity_names_note); (b) where a control surface is provided at all (control_plane other than unavailable, the same precondition subordinate ruling 8 already carries), an audit-role credential is additionally accepted on the audit_query control endpoint alongside the three read-only endpoints ruling 8 already named, with FORBIDDEN fail-closed on every other control endpoint unchanged -- this holds whether that implementation's own audit_query capability is itself enabled or unavailable, since route registration and role authorization there precede the capability-availability check (an unavailable audit_query still answers an authorized audit-role caller with CAPABILITY_UNSUPPORTED, never FORBIDDEN or a bare 404). Added by a later revision of this document still under this same 1.4.0 label (subordinate ruling 10, item 2): this acceptance is scoped to the control surface's audit_query control endpoint (the canonical POST /control/v1/audit/query, and its alias as served on the control host -- the same host scoping endpoints.audit_query.deprecation_note already states, and this document's own 1.4.0 conditional obligation (5) below, which requires both paths to answer as the identical operation). A data-plane host is not thereby obliged to authenticate control or audit credentials merely because it declares control_plane as something other than unavailable; where such a host holds no control-credential store, it may refuse a control or audit credential presented on its own POST /v1/audit/query alias as an unknown credential (AUTH_INVALID); it is not thereby required to accept, verify, or forward it. Co-hosting both surfaces in one process remains permitted (versioning.control_discovery) and is not what this scoping addresses; and (c) audit_query's canonical classification in this document is control_endpoints (POST /control/v1/audit/query), with the pre-1.4.0 endpoints.audit_query path (POST /v1/audit/query) retained as an alias of the identical operation for one further minor version. The remaining 1.4.0 obligations are conditional, unlike every obligation enumerated above for earlier versions: they bind an implementation declaring 1.4.0 only insofar as that implementation's own capabilities() additionally declares audit_query as something other than unavailable, since whether audit_query is provided at all remains a capability-declared matter, not a version-mandated one (the same posture control_plane.provision already establishes for the control surface as a whole) -- an implementation may declare contract_version 1.4.0 while its own audit_query stays unavailable (for example, no audit datastore is configured for this deployment) and remains fully conformant to 1.4.0 throughout, without being held to, or claiming, any obligation in this conditional list while unavailable. Where an implementation does declare audit_query as enabled or partial, 1.4.0 additionally requires -- exhaustively: (1) AuditQueryRequest.after, when accepted, is treated as an opaque cursor encoding a position under the ordering in (2) rather than interpreted as an event_id or a numeric offset, and a value that fails to decode or no longer resolves under the request's own filters is answered with VALIDATION_FAILED; (2) AuditResult.events[] is returned in the total order (recorded_at, plane, event_id); (3) each returned event carries a plane field whose value is control or application; (4) event_class is a vocabulary the implementation itself declares (its own capabilities().audit_query.event_classes), not a fixed contract enum, and 1.4.0 requires no particular member of it; (5) both the canonical POST /control/v1/audit/query path and the POST /v1/audit/query alias actually answer requests as the identical operation, rather than one of the two being merely routed without a working handler behind it; and (6) where audit_requests_per_minute is published in limits/limit_enforcement, it governs the audit_query endpoint specifically, as its own declared and separately enforceable limit class, and is not satisfied by also enforcing control_requests_per_minute for audit_query requests. Only an implementation declaring 1.5.0 or higher additionally claims conformance to the obligation 1.5.0 introduces (subordinate ruling 10, item 1). Like 1.4.0's own conditional obligations, this one binds an implementation declaring 1.5.0 only insofar as that implementation's own capabilities() declares audit_query as something other than unavailable; an implementation may declare contract_version 1.5.0 while its own audit_query stays unavailable and remains fully conformant to 1.5.0 throughout, without being held to this obligation while unavailable. Since 1.5.0 (subordinate ruling 10, item 1, conditional): operations and target_kinds are vocabularies each implementation declares for itself at capabilities().audit_query.operations / .target_kinds -- the sets of values the operation and target_kind fields of events returned by audit_query can take. As with event_classes, this contract enumerates no fixed enum and requires no particular member (declare-the-hazard). An implementation declaring 1.5.0 or higher whose audit_query is other than unavailable MUST declare both, and every event it returns MUST carry values drawn from the declared sets; the same superset relation holds for event_classes, stated here explicitly. Only an implementation declaring 1.6.0 or higher additionally claims conformance to the obligations 1.6.0 introduces (subordinate ruling 11). Two of those obligations are unconditional in the same sense as every obligation enumerated above -- they bind simply by declaring 1.6.0, independent of any capability's own status: (a) its GET /v1/capabilities document carries surfaces.data.base_url, the absolute base URL of its own data surface, and -- where a control surface is provided at all (control_plane other than unavailable, the same precondition subordinate rulings 8 and 9 already carry) -- both surfaces' capability documents additionally carry surfaces.control.base_url, each document carrying the same surfaces; and (b) the secret returned by any issue or rotate path it offers, in band or out of band, is accepted verbatim as a bearer token on the surface that credential is for, with no composition, splitting, or derivation required of the client (security.schemes). The remaining 1.6.0 obligations are conditional, in the same sense 1.4.0's own conditional list is: they bind only insofar as the implementation's own capabilities() declares the named capability as something other than unavailable. Where it declares application_catalog as something other than unavailable: (1) every EntityDescriptor it returns carries field_types, total over that entity's own fields, reporting json for any field created without a declared type. Where it declares schema_operations as something other than unavailable: (2) a create_entity it executes accepts field_types and creates each field named there with the type declared there, and an add_field it executes accepts every member of the seven-member vocabulary, json included; a field_types naming a field outside the request's own fields, carrying a value outside that vocabulary, or sent without fields, is refused with VALIDATION_FAILED. 1.6.0 introduces no obligation on what a client must send: SchemaOperationRequest.field_types is optional wherever it appears, and a request valid under 1.5.0 stays valid. An implementation still declaring 1.5.0 is not held to any 1.6.0-only, 1.7.0-only, or 1.8.0-only obligation retroactively. Every obligation introduced under a given version label -- whether enumerated above or added by a later revision of this document still under that same label -- follows this same general rule. An implementation still declaring 1.1.0 remains conformant to 1.1.0 semantics and is not held to any 1.2.0-only, 1.3.0-only, 1.4.0-only, 1.5.0-only, 1.6.0-only, 1.7.0-only, or 1.8.0-only obligation retroactively, an implementation declaring 1.2.0 is not held to any 1.3.0-only, 1.4.0-only, 1.5.0-only, 1.6.0-only, 1.7.0-only, or 1.8.0-only obligation retroactively, an implementation declaring 1.3.0 is not held to any 1.4.0-only, 1.5.0-only, 1.6.0-only, 1.7.0-only, or 1.8.0-only obligation retroactively, and an implementation declaring 1.4.0 is not held to any 1.5.0-only, 1.6.0-only, 1.7.0-only, or 1.8.0-only obligation retroactively. Only an implementation declaring 1.7.0 or higher additionally claims conformance to the obligations 1.7.0 introduces (subordinate ruling 12). Two of those obligations are unconditional in the same sense as every obligation enumerated above -- they bind simply by declaring 1.7.0, independent of any capability's own status: (a) every denial it answers with VALIDATION_FAILED, IDENTIFIER_INVALID or CAPABILITY_UNSUPPORTED carries the details keys errors.details_vocabulary requires for that code, with violated_declaration drawn from the closed vocabulary named there, and carries no row value, no suggested value, no corrective action and no internal name; and (b) every successful QueryResult, MutationResult and SchemaOperationResult it returns carries request_id, the same identifier its own audit evidence for that request carries. The remaining 1.7.0 obligations are conditional, in the same sense 1.4.0's and 1.6.0's own conditional lists are: they bind only insofar as the implementation's own capabilities() declares the named capability -- or, where two are named, both of them -- as something other than unavailable. Where it declares constraint_declarations and schema_operations both as something other than unavailable: (1) a create_entity it executes accepts field_constraints, an add_field and an alter_field it executes accept enum and nullable, each field is created or altered with the constraints declared there, those constraints are enforced on every value written to that field, and an alter_field whose declared constraints existing rows would violate is refused in full with CONFLICT, changing nothing. Where it declares constraint_declarations and application_catalog both as something other than unavailable: (2) every EntityDescriptor it returns carries field_constraints, total over that entity's own fields, reporting nullable: true and no enum for a field that declares neither. Where it declares dry_run as something other than unavailable: (3) a request carrying dry_run receives the decision the identical request without it would receive -- the same code and the same details on a refusal, the same affected count on a success -- and leaves no externally visible state change, subject to the two consumptions structured_operations.dry_run.external_effects names; and a plan it returns is deterministic, and is verified by recomputation on the real request, refusing with PRECONDITION_FAILED where it no longer agrees. Where it declares idempotency as something other than unavailable: (4) an idempotency_key is recorded with a digest of the request it accompanied, in the same transaction as that request's own effects; the same key with the same digest, resent within idempotency_retention_ms, returns the original result without re-executing, including the original request_id; and the same key with a different digest is refused with CONFLICT. Where it declares request_budget as something other than unavailable: (5) a budget narrows a bound downward only, a budget above the deployed value or naming a class that does not apply to that endpoint is refused with VALIDATION_FAILED, and exceeding a narrowed bound is refused with LIMIT_EXCEEDED naming that limit class. 1.7.0 introduces no obligation on what a client must send: dry_run, plan, budget, field_constraints, enum, nullable, and SchemaOperationRequest.idempotency_key are optional wherever they appear, and a request valid under 1.6.0 stays valid. Only an implementation declaring 1.8.0 or higher additionally claims conformance to the obligations 1.8.0 introduces (subordinate ruling 13). One of those obligations is unconditional in the same sense as every obligation enumerated above -- it binds simply by declaring 1.8.0, independent of any capability's own status: every limit_enforcement value it publishes describes the whole deployment reachable at the declared surfaces base URL, never one server process, so it declares enforced for a limit class only when the bound holds across every process that may serve that base URL at the same time, and declares deployment_required when the bound is held per process and more than one process may serve that base URL. The remaining 1.8.0 obligation is conditional, in the same sense 1.4.0's, 1.6.0's and 1.7.0's own conditional lists are: it binds only insofar as the implementation's own capabilities() declares idempotency as something other than unavailable: (1) two requests carrying the same idempotency_key that arrive together are serialized so that at most one of them executes, the other being answered after the first commits as a resend -- from the record where the digests agree, with CONFLICT where they differ -- and the idempotency_entries bound is evaluated under that same serialization (structured_operations.idempotency.record). 1.8.0 introduces no obligation on what a client must send: a request valid under 1.7.0 stays valid. An implementation still declaring 1.6.0 is not held to any 1.7.0-only or 1.8.0-only obligation retroactively. An implementation still declaring 1.7.0 is not held to any 1.8.0-only obligation retroactively. Only an implementation declaring 1.9.0 or higher additionally claims conformance to the obligations 1.9.0 introduces (subordinate ruling 14). Those obligations are unconditional in the same sense as every obligation enumerated above -- they bind simply by declaring 1.9.0, independent of any capability's own status: (a) every operation common_baseline.operations names is executable -- it is not answered with CAPABILITY_UNSUPPORTED, and no capability it needs is declared unavailable; and (b) its capability document carries operation_catalog_url, and the document served at that URL is byte-identical to this contract version's own derived operation catalog. Because common_baseline names operations these capabilities govern, an implementation declaring 1.9.0 declares none of application_catalog, schema_operations, structured_query, atomic_mutation, constraint_declarations, dry_run, idempotency or request_budget as unavailable; every obligation an earlier version made conditional on exactly those capabilities therefore binds unconditionally at 1.9.0, and is not restated here. 1.9.0 introduces no obligation on what a client must send: a request valid under 1.8.0 stays valid. An implementation still declaring 1.8.0 is not held to any 1.9.0-only obligation retroactively. Only an implementation declaring 1.10.0 or higher additionally claims conformance to the obligations 1.10.0 introduces (subordinate ruling 15). Every 1.10.0 obligation is conditional, in the same sense 1.4.0's, 1.6.0's, 1.7.0's and 1.8.0's own conditional lists are: each binds only insofar as the implementation's own capabilities() declares structured_query as something other than unavailable: (1) the items a query returns are totally ordered, in the order structured_operations.paging.ordering defines -- the request's own order_by, completed by a tie-break of the implementation's own choosing, which this contract does not name -- so that two identical requests decided against unchanged stored content return the identical sequence; (2) QueryResult.next_page is non-null exactly when at least one further row follows this page's last item in that order, and null exactly when none does; (3) where it is non-null, it is a keyset cursor as structured_operations.paging.cursor defines it -- an opaque token encoding that last item's own position in that order, never an offset or a count, holding no server-side state, and a request carrying it returns the rows that follow that position; (4) a cursor is bound to the Application, the entity, the request's where and the request's order_by, and stays valid across a change of select or page.size (structured_operations.paging.binding); (5) a cursor that fails to decode, whose ordering values do not match, in number or in type, the terms of that order, or whose recorded binding names a different Application, entity, where or order_by than the request presenting it, is refused with VALIDATION_FAILED, details.violated_declaration: request_schema and details.field: page/cursor; (6) across the pages of one traversal, a row that exists throughout it and whose ordering-term values do not change during it is returned exactly once; and (7) a request that carries no page.size is answered as though it carried the page.size equal to the least of 1000 (Page.size's own maximum), the implementation's declared limits.result_items, and the request's own budget.result_items where it carries one, and its page holds at most that many items (structured_operations.paging.next_page). 1.10.0 introduces no obligation on what a client must send: page.cursor remains optional wherever it appears, and a request valid under 1.9.0 stays valid in shape. A cursor an implementation issued before its own version-flip need not remain usable across it; such a request is refused as structured_operations.paging.refusal describes, and the client restarts the traversal. An implementation still declaring 1.9.0 is not held to any 1.10.0-only obligation retroactively. Only an implementation declaring 1.11.0 or higher additionally claims conformance to the obligation 1.11.0 introduced (subordinate ruling 16), unconditional in the same sense as every unconditional obligation enumerated above: an undeclared field name, at any of the positions errors.details_vocabulary.undeclared_field names, is refused as that entry states -- VALIDATION_FAILED, violated_declaration request_schema, field naming the position -- and no other code is a conforming refusal of it. An implementation still declaring 1.10.0 is not held to any 1.11.0-only obligation retroactively. 1.12.0 introduces no obligation (subordinate ruling 17): it withdraws the word fixed from limits.audit_requests_per_minute_note, so that this contract no longer defines the shape of the audit_requests_per_minute window, and an implementation conforming to 1.11.0 conforms to 1.12.0 without a behavior change. Only an implementation declaring 1.13.0 or higher additionally claims conformance to the obligation 1.13.0 introduced (subordinate ruling 18), unconditional in the same sense as every unconditional obligation enumerated above: audit.process_loss_policy -- a service process that stops without completing a graceful shutdown loses neither the audit event of an operation whose response the service had already returned nor the count of any denial occurrence whose response the service had already returned. An implementation still declaring 1.12.0 is not held to any 1.13.0-only obligation retroactively. A peer's version-flip -- the commit that changes its own declared contract_version -- must land in the same commit as the real behavior change it claims; declaring a higher version before the corresponding behavior exists, or shipping the behavior while the declaration lags, are both non-conformant.

**Subordinate ruling(s):**
- 従属判断 7
- 従属判断 8
- 従属判断 9
- 従属判断 10
- 従属判断 11
- 従属判断 12
- 従属判断 13
- 従属判断 14
- 従属判断 15
- 従属判断 16
- 従属判断 17
- 従属判断 18

**Introduced in:** contract 1.2.0 through 1.13.0 (cumulative)

**Revision note (contract 1.8.0, subordinate ruling 13, WP-5a/5b, supervisor ruling 2026-09-08):** Contract 1.8.0 adds 3 new contract-JSON values that carry no provenance marker of their own -- `capability_status.rules`' new (5th) array element, an appended sentence on the end of `limits.profile`'s existing string, and `versioning.obligations`' 1.8.0 entry (verified: the marker scanner in `conformance-tests/test_contract_history_register.py` finds 0 hits on all 3; `spec/CONTRACT_HISTORY_MANIFEST.json` is unaffected, still exactly 29 entries, since none of the 3 was ever stripped). Re-embedding a marker there would be exactly the clutter contract 1.7.0's R-10 (B) moved OUT of the contract body in the first place, so their provenance is recorded here instead, under this existing `## versioning.version_binding` anchor -- which already carries subordinate ruling 13 in the listing above -- rather than as a separate free-standing anchor (an earlier WP-5a companion draft placed one such anchor in this file's preamble as a `### ` heading; superseded here by supervisor ruling 2026-09-08, which held that a second, unregistered heading kind would leave the register test's heading-set-equality check with an unwatched escape hatch for any anchor added the same way later, and that this section's own existing provenance already covers subordinate ruling 13). The anchor sentence those 3 values share (monitor-finalized, copied unparaphrased per `OPERATING_CONDITIONS.md` §1.5 items 35/36): "1.8.0 (subordinate ruling 13, 2026-09-08): enforcement scope defined as the deployment behind the declared surfaces base URL. Reason: r2db-api serves each base URL from one process, MitateDB-api on Cloud Run may serve it from several; the contract had not said which unit the enforcement values describe." `versioning.version_binding`'s own prose additionally gains a 4th 1.8.0 piece not listed among those 3 -- the "Only an implementation declaring 1.8.0 or higher ..." paragraph itself (placed directly after the 1.7.0 paragraph and before the retroactive-denial enumeration) -- and every "is not held to any ... obligation retroactively" clause in that enumeration is mechanically extended to add `1.8.0-only`, the same way contract 1.7.0 extended the `1.6.0-only` enumeration to add `1.7.0-only` (`git log -S"1.7.0-only" -- spec/data-service-api.v1.json`). This changes the substring the phase-9 verbatim pins (`conformance-tests/test_contract.py`'s `PIN_1_6_0_VERSION_BINDING_PARAGRAPH` and `PIN_1_7_0_RETROACTIVE_DENIAL_ROW_*`) match against; those pins were updated in the same commit to the new, longer verbatim text. This section's own quote above is the full post-1.8.0 text.

**Revision note 2 (contract 1.8.0 addendum, subordinate ruling 13 item 2, WP-5c, supervisor ruling U-9 2026-09-08):** Before 1.8.0 was published to `main`, its own text was amended once more, so 1.8.0 ships with a second obligation. The anchor sentence (monitor-finalized, copied unparaphrased per `OPERATING_CONDITIONS.md` §1.5 items 35/36): "1.8.0 addendum (subordinate ruling 13, item 2, 2026-09-08): concurrent sends of one idempotency_key are serialized so that at most one executes; the idempotency_entries bound is evaluated under that serialization. Reason: external review 2 (2026-09-08) reproduced on PostgreSQL that both peers executed the same key twice under concurrent sends; the 1.7.0 text already implied this but stated it only for sequential resends." The addendum changes 2 further contract-JSON values beyond this section's own quote above (which is the full post-addendum text of `versioning.version_binding`, its 1.8.0 paragraph rewritten to enumerate one unconditional and one conditional obligation): a sentence appended to the end of `structured_operations.idempotency.record`'s existing string, and `versioning.obligations`' 1.8.0 entry, whose `conditional` list goes from empty to one element (`idempotency_concurrent_same_key_sends_serialized`, capability `idempotency`, in the same shape 1.7.0's own conditional items carry). Like Revision note 1's 3 values, neither carries a provenance marker of its own (verified: the marker scanner above finds 0 hits on both, so this file's heading-set-equality is unaffected and no new `## ` anchor is added; `structured_operations.idempotency.record` has no anchor section in this file and does not gain one). `spec/CONTRACT_HISTORY_MANIFEST.json` is unaffected, still exactly 29 entries: nothing here was ever stripped. The version number does not move -- 1.8.0 had not yet reached `main`, so this is an amendment to an unpublished version rather than a new one.

**Revision note 3 (contract 1.9.0, subordinate ruling 14, work order `docs/work-orders/WORK_ORDER_PHASE11_MIN_COMMON_PROFILE_V1.md` WP-1, design `docs/design/PHASE11_MIN_COMMON_PROFILE_V1.md` §3 D-1/D-4/D-5, requester ruling U-1/U-4 = (α)):** Contract 1.9.0 adds new contract-JSON values that carry no provenance marker of their own -- a new top-level `common_baseline` section, `capability_status.rules`' new (6th) array element, `versioning.obligations`' 1.9.0 entry, `endpoints.operation_catalog`, `schemas.OperationCatalogDocument` and `definitions.OperationCatalogEntry` (verified: the marker scanner in `conformance-tests/test_contract_history_register.py` finds 0 hits on all of them; `spec/CONTRACT_HISTORY_MANIFEST.json` is unaffected, still exactly 29 entries, since none of them was ever stripped). Their provenance is recorded here instead, under this existing `## versioning.version_binding` anchor -- which already carries subordinate ruling 14 in the listing above -- following the same reasoning Revision note 1 gives for 1.8.0's own new values. `versioning.version_binding`'s own prose additionally gains the "Only an implementation declaring 1.9.0 or higher ..." paragraph itself (placed directly after the 1.8.0 paragraph and before the version-flip discipline sentence); the 1.8.0 paragraph itself, and every earlier retroactive-denial row, is not touched (1.8.0-and-earlier confirmed text stays unchanged, character for character). The new 1.9.0 paragraph carries its own retroactive-denial sentence at its own end -- "An implementation still declaring 1.8.0 is not held to any 1.9.0-only obligation retroactively." -- the same form each earlier version's own paragraph carries for the version it introduces, not an extension of the 1.8.0 paragraph's enumeration. This section's own quote above is the full post-1.9.0 text. Separately, `schemas.CapabilityDocument.properties.operation_catalog_url.description` is a whole-value replacement (not an appended clause) -- the requester ruling U-4 = (α) makes `operation_catalog_url` a 1.9.0-or-higher obligation, so the pin that pinned its 1.7.0-era text (`conformance-tests/test_contract.py`'s `PIN_1_7_0_CAPABILITY_DOCUMENT_OPERATION_CATALOG_URL`) moves to the new 1.9.0 text in the same commit, per the version-flip discipline this document already follows for a value a version's own ruling supersedes wholesale.

**Revision note 4 (contract 1.10.0, subordinate ruling 15, work order `docs/work-orders/WORK_ORDER_PHASE11_KEYSET_PAGING_V1.md` WP-1):** Contract 1.10.0 adds `structured_operations.paging` (6 new keys: `ordering`, `next_page`, `cursor`, `binding`, `refusal`, `traversal`) and `versioning.obligations`' 1.10.0 entry (7 conditional obligations, `unconditional: []`), none of which carries a provenance marker of its own (measured: the marker scanner above finds 0 hits on all 7 new/changed contract-JSON values -- `structured_operations.paging`'s 6 string values and the `obligations` array's 1.10.0 entry -- so this file's heading-set-equality is unaffected and no new `## ` anchor is added for any of them; the RAW contract JSON's total scanner-hit count stays exactly 3, unchanged from before 1.10.0, all 3 the same pre-existing `unstripped: true` paths this file's preamble already names). `versioning.version_binding`'s own prose additionally gains the "Only an implementation declaring 1.10.0 or higher ..." paragraph itself (placed directly after the 1.8.0-declaring retroactive-denial sentence that ends the 1.9.0 paragraph, and before the version-flip sentence); that paragraph carries its own retroactive-denial sentence ("An implementation still declaring 1.9.0 is not held to any 1.10.0-only obligation retroactively."), and, as with 1.9.0 (Revision note 3), the earlier retroactive-denial rows and the 1.9.0 paragraph's own closing sentence are left exactly as they were. This section's own quote above is the full post-1.10.0 text.

**Revision note 5 (contract 1.10.0, subordinate ruling 15, `docs/design/PHASE11_KEYSET_PAGING_V1.md` D-3 の 8, D-2b の 2):** 1.10.0 aligns both peers' `page.size` out-of-range refusal to a single form regardless of direction -- `VALIDATION_FAILED`, `violated_declaration: request_schema`, `field: page/size` -- for both `page.size` <= 0 and `page.size` > 1000. r2db-api's pre-1.10.0 refusal split this by direction and matched neither the code nor the field of this unified form for either: `page_size <= 0` was `LIMIT_EXCEEDED` (HTTP 413, `limit_class: result_items`, `r2db-api/src/r2db_api/paging.py`:44-46), and `page_size > 1000` was `VALIDATION_FAILED` but with `violated_declaration: budget` and `field: page_size` rather than `page/size` (same file, :47-48) -- not merely a different `field` value on an otherwise-matching code and declaration. 1.10.0's obligation (7) (the omitted-`page.size` default) and C-30's own `page.size` refusal observation make this unified form load-bearing for the first time. 1.10.0 also defines the default page for a request that omits `page.size`: the least of 1000 (`Page.size`'s own maximum), the implementation's declared `limits.result_items`, and the request's own `budget.result_items` where it carries one (`structured_operations.paging.next_page`, obligation (7) above) -- this replaces each peer's own prior undeclared default (r2db-api's constant 100, MitateDB-api's unbounded read truncated silently at the deployment limit), so an existing client that omits `page.size` sees a different page shape after either peer's own version-flip to 1.10.0.

**Revision note 6 (contract 1.10.0, subordinate ruling 15, `definitions.Page.cursor`, requester ruling Q-5 = (a), `docs/design/PHASE11_KEYSET_PAGING_V1.md` D-1 (D)):** `Page.cursor`'s schema loses `maxLength: 512` (now `{"type": "string"}` only) -- a keyset cursor carries the encoded ordering-key values of a row, which can exceed 512 bytes once `order_by` includes a long text field, and the cursor is a value the server issues and the client only echoes back, never one the client composes or sizes; the length of the string a request carries (including `page.cursor`) is already bound by that endpoint's own `request_bytes`, the same form `limits.enum_members` already states for another request-carried string ("the length of any single member is bounded by request_bytes on the schema operation that declares it, as every other request-carried string is"). No `## definitions.Page.cursor` heading is added here (this file has none today, and the marker scanner finds 0 hits on the new value); this note lives under this existing `## versioning.version_binding` anchor per the same convention Revision note 1 established for markerless 1.8.0 values.

**Revision note 7 (contract 1.11.0, subordinate ruling 16, work order `docs/work-orders/WORK_ORDER_R110_UNDECLARED_FIELD_REFUSAL_V1.md` WP-1):** Contract 1.11.0 adds `errors.details_vocabulary.undeclared_field` (1 new string value) and `versioning.obligations`' 1.11.0 entry (1 unconditional obligation, `conditional: []`), neither of which carries a provenance marker of its own (measured: the marker scanner above finds 0 hits on both new/changed contract-JSON values; the RAW contract JSON's total scanner-hit count stays exactly 3, unchanged from before 1.11.0, all 3 the same pre-existing `unstripped: true` paths this file's preamble already names). `versioning.version_binding`'s own prose additionally gains the "Only an implementation declaring 1.11.0 or higher ..." paragraph itself (placed directly after the 1.9.0-declaring retroactive-denial sentence that ends the 1.10.0 paragraph, and before the version-flip sentence); that paragraph carries its own retroactive-denial sentence ("An implementation still declaring 1.10.0 is not held to any 1.11.0-only obligation retroactively."), and, as with 1.9.0 and 1.10.0 (Revision notes 3 and 4), the earlier retroactive-denial rows and the 1.10.0 paragraph's own closing sentence are left exactly as they were. This section's own quote above is the full post-1.11.0 text. Unlike the contract-text-only work orders behind Revision notes 3-6, this WP lands the contract text, both peers' refusal-code alignment (`select`/`where`/`order_by`/mutation `values`) and both peers' `contract_version` flip in the same commit, since the version-flip discipline this document already states (`versioning.version_binding`'s own closing sentence) requires the declaration and the real behavior change to land together. Before this commit, r2db-api answered an undeclared field name at any of the four positions with `NOT_FOUND` and no `details` (`docs/design/R2DB_CCR13_STORAGE_V1.md`'s own correction record m-6). MitateDB-api's `select` entries already answered `VALIDATION_FAILED`/`request_schema`, but named the position by the field's own name (`select/<field name>`); this commit changes that position to the same index form (`select/<i>`) `where`/`order_by` already used there, so a client reading `details.field` off a `select` refusal sees a different string shape after this peer's own version-flip. This also closes the cross-peer code difference `conformance-tests/test_c07_atomicity_and_retry.py`'s own module docstring recorded for the mutation `values` position (measured: `NOT_FOUND` on both r2db-api plugs, `VALIDATION_FAILED` on both MitateDB-api plugs, for the identical undeclared-key probe) -- both peers now answer `VALIDATION_FAILED` there.

**Revision note 8 (contract 1.12.0, subordinate ruling 17, ledger R-114):** Contract 1.12.0 adds no obligation and no `versioning.obligations` entry (the index still ends at 1.11.0, and `version_binding` gains no "Only an implementation declaring ..." opener, so the two version-label sets stay equal). `versioning.version_binding` gains one sentence, placed directly after the 1.10.0-declaring retroactive-denial sentence that ends the 1.11.0 paragraph and before the version-flip sentence: "1.12.0 introduces no obligation (subordinate ruling 17): ...". It states what 1.12.0 changes -- `limits.audit_requests_per_minute_note` no longer defines the shape of that window (see that path's own section above) -- and that no behavior change accompanies the declaration. This section's own quote above is the full post-1.12.0 text. Both peers' declared `contract_version` moves to 1.12.0 in the same commit as the contract text.

**Revision note 9 (contract 1.13.0, subordinate ruling 18, ledger R-115):** Contract 1.13.0 adds `audit.process_loss_policy` (1 new string value) and `versioning.obligations`' 1.13.0 entry (1 unconditional obligation, `conditional: []`), neither of which carries a provenance marker of its own (measured: the marker scanner above finds 0 hits on both; the RAW contract JSON's total scanner-hit count stays exactly 3, unchanged from before 1.13.0, all 3 the same pre-existing `unstripped: true` paths this file's preamble already names), so no new `## ` anchor is added. `versioning.version_binding`'s own prose additionally gains the "Only an implementation declaring 1.13.0 or higher ..." paragraph itself (placed directly after the 1.12.0 sentence and before the version-flip sentence); that paragraph carries its own retroactive-denial sentence ("An implementation still declaring 1.12.0 is not held to any 1.13.0-only obligation retroactively."), and the 1.12.0 sentence and every earlier retroactive-denial row are left exactly as they were. This section's own quote above is the full post-1.13.0 text. `audit.sink_failure_policy` is unchanged: the 1.13.0-or-higher qualifier in `audit.process_loss_policy` is what keeps the bounded buffer that `sink_failure_policy` permits available to an implementation still declaring 1.12.0 or lower. The contract states the outcome only and names no mechanism.

---
