# Contract JSON provenance companion (`CONTRACT_HISTORY.md`)

This file is the provenance companion for `spec/data-service-api.v1.json`, placed per phase 8 design decision D-4 and requester ruling U-2 = (A) (`docs/design/PHASE8_EFFECTIVE_BOUNDS_AND_HYGIENE_V1.md` §3 D-4, §5 U-2). Every value in the contract JSON that carries a provenance marker (a "Since 1.x.y", "subordinate ruling N", or similar phrase identified by the scanner this file's register test embeds) gets one `## <json_path>` section below, naming: (i) that value's full text, copied verbatim (the provenance marker is embedded within it, not extracted from it), (ii) the `spec/CCR_DISPOSITION.md` subordinate ruling the marker refers to, and (iii) the contract version that introduced it.

**Update convention:** when a newly written value in the contract JSON carries a new provenance marker, add its `## <json_path>` section to this file in the same commit that adds the marker to the contract. The register test (`conformance-tests/test_contract_history_register.py`) fails the collected suite red until the two sets (scanner-found JSON paths, and this file's section headings) agree exactly, so an added marker without a matching section here cannot pass unnoticed.

**Limitations of this method (read before treating this file as "the contract's history moved out"):**

1. The contract JSON's own length does not shrink by even one character. This companion's effect on P-7 is limited to making the primary provenance material (the subordinate ruling) reachable in one hop from the `spec/` directory -- it does not remove or shorten any text currently inside `spec/data-service-api.v1.json`.
2. There is no in-band reference from inside the contract JSON to this file -- the contract JSON carries no key pointing here, by design (the contract's own additive-key discipline is preserved). The only two reachability paths are `spec/README.md` and this file's own existence under `spec/`. This is deliberately **"one hop from the `spec/` directory"**, not "one hop from the contract JSON" -- a reader who opens `spec/data-service-api.v1.json` alone, without also looking at what else lives in `spec/`, has no way to discover this file from the JSON's own content.
3. This phase leaves 29 provenance-marker-carrying values inside the contract JSON body (`docs/design/PHASE8_EFFECTIVE_BOUNDS_AND_HYGIENE_V1.md` Appendix A §A.2c). Every one of those 29 values continues to double as current normative prose -- none of them is pure historical narrative -- so none of the marker text can be moved out of the contract without rewriting the normative sentence it lives in. This companion records where the marker points; it does not shrink the count of 29, and this count does not change as a result of this phase.

See `docs/design/PHASE8_EFFECTIVE_BOUNDS_AND_HYGIENE_V1.md` §3 D-4 and §5 U-2 for the full decision record, and its Appendix A for the verbatim marker inventory this file was built from. Option (B) (stripping the marker prefixes/clauses out of the contract body) is out of scope for this phase and is sent to phase 9 (contract 1.7.0) per that same ruling.

---

## audit.query_cursor

**Value (verbatim, full value copied from the contract JSON `spec/data-service-api.v1.json`; the history marker is embedded in it):**

> Since 1.4.0 (subordinate ruling 9, item 1, conditional): AuditQueryRequest.after is an opaque cursor, not an event_id or a numeric offset -- a client never constructs one itself, only echoes back the cursor field of the last event it received (query_event_fields_note). A cursor that fails to decode, or that no longer resolves under the request's own filters, is refused with VALIDATION_FAILED. A cursor obtained under one set of filters is valid only when reused with that same set of filters; reusing it under different filters is not defined by this version.

**Subordinate ruling:**
- 従属判断 9

**Introduced in:** contract 1.4.0

---

## audit.query_event_class_vocabulary

**Value (verbatim, full value copied from the contract JSON `spec/data-service-api.v1.json`; the history marker is embedded in it):**

> Since 1.4.0 (subordinate ruling 9, item 4, conditional): event_class is a vocabulary each implementation declares for itself, at capabilities().audit_query.event_classes -- this contract does not enumerate a fixed event_class enum, and does not require an implementation's declared vocabulary to include any particular member (declare-the-hazard, matching audit.fields' own additive-vocabulary posture rather than capability_status.defined's closed status_enum).

**Subordinate ruling:**
- 従属判断 9

**Introduced in:** contract 1.4.0

---

## audit.query_event_fields_note

**Value (verbatim, full value copied from the contract JSON `spec/data-service-api.v1.json`; the history marker is embedded in it):**

> Since 1.4.0 (subordinate ruling 9, items 1 and 3, conditional): each event AuditResult.events[] returns from audit_query MAY carry fields beyond audit.fields -- plane (control or application: the durable source the event was read from, never a value the original event-writer could itself set), recorded_at (when the event became durable, distinct from the emission-time occurred_at already in audit.fields), cursor (this event's own opaque position, suitable for a later after), and count (present only on an event representing more than one coalesced occurrence, absent -- never zero or one -- otherwise). AuditResult.events[] remains an open per-event shape (subordinate ruling 7(A)), so none of these are a schema-breaking addition.

**Subordinate ruling:**
- 従属判断 9

**Introduced in:** contract 1.4.0

---

## audit.query_operation_vocabulary

**Value (verbatim, full value copied from the contract JSON `spec/data-service-api.v1.json`; the history marker is embedded in it):**

> Since 1.5.0 (subordinate ruling 10, item 1, conditional): operations and target_kinds are vocabularies each implementation declares for itself at capabilities().audit_query.operations / .target_kinds -- the sets of values the operation and target_kind fields of events returned by audit_query can take. As with event_classes, this contract enumerates no fixed enum and requires no particular member (declare-the-hazard). An implementation declaring 1.5.0 or higher whose audit_query is other than unavailable MUST declare both, and every event it returns MUST carry values drawn from the declared sets; the same superset relation holds for event_classes, stated here explicitly. audit_query.operations is the vocabulary of the audit row's operation field and is unrelated to capability_status.defined.atomic_mutation.operations, which enumerates the executable mutation verbs.

**Subordinate ruling:**
- 従属判断 10

**Introduced in:** contract 1.5.0

---

## audit.query_ordering

**Value (verbatim, full value copied from the contract JSON `spec/data-service-api.v1.json`; the history marker is embedded in it):**

> Since 1.4.0 (subordinate ruling 9, item 2, conditional on audit_query being provided -- versioning.version_binding): AuditResult.events[] returned by audit_query is totally ordered by (recorded_at, plane, event_id). plane is included in the ordering key because an implementation may hold more than one durable event source (e.g. a control-plane source and an application-plane source) whose own event_id vocabularies are not mutually unique, so recorded_at and plane together, not event_id alone, are what make the combined order total.

**Subordinate ruling:**
- 従属判断 9

**Introduced in:** contract 1.4.0

---

## audit.query_target_kind_vocabulary

**Value (verbatim, full value copied from the contract JSON `spec/data-service-api.v1.json`; the history marker is embedded in it):**

> Since 1.5.0 (subordinate ruling 10, item 1, conditional): operations and target_kinds are vocabularies each implementation declares for itself at capabilities().audit_query.operations / .target_kinds -- the sets of values the operation and target_kind fields of events returned by audit_query can take. As with event_classes, this contract enumerates no fixed enum and requires no particular member (declare-the-hazard). An implementation declaring 1.5.0 or higher whose audit_query is other than unavailable MUST declare both, and every event it returns MUST carry values drawn from the declared sets; the same superset relation holds for event_classes, stated here explicitly. audit_query.operations is the vocabulary of the audit row's operation field and is unrelated to capability_status.defined.atomic_mutation.operations, which enumerates the executable mutation verbs.

**Subordinate ruling:**
- 従属判断 10

**Introduced in:** contract 1.5.0

---

## capability_status.defined.atomic_mutation

**Value (verbatim, full value copied from the contract JSON `spec/data-service-api.v1.json`; the history marker is embedded in it):**

> Single-entity atomic mutation batches. A capability entry's own operations list names the mutation vocabulary the batch execution surface executes -- not a batch-specific subset distinct from single-operation execution of that same vocabulary (CCR_DISPOSITION.md subordinate ruling 8-F). The capability entry schema (CapabilityDocument.capabilities' additionalProperties) is deliberately open, and operations is a peer-published key within that open shape, not a fixed property of the closed envelope -- a client reading only CapabilityDocument's own schema will not find operations declared there; it discovers the key by reading a real capability document.

**Subordinate ruling:**
- 従属判断 8

**Introduced in:** contract 1.3.0

---

## control_endpoints.audit_query.semantics

**Value (verbatim, full value copied from the contract JSON `spec/data-service-api.v1.json`; the history marker is embedded in it):**

> Added in 1.4.0 (subordinate ruling 9, item 7): this is audit_query's canonical location, moved here from endpoints.audit_query because its only real authority (control or audit) and its only real host (the control surface, per control_plane.separability) are both control-plane-shaped, not application-shaped -- endpoints.audit_query's own path (POST /v1/audit/query) remains valid as an alias of this identical operation for one further minor version after 1.4.0 (endpoints.audit_query.deprecation_note). Application credentials are denied. Emission is a service consequence and cannot be authored by an application caller. Where audit_query is provided at all, this path and its alias resolve to the same handler and the same response; where it is unavailable, both still authenticate and authorize the caller before answering CAPABILITY_UNSUPPORTED (never a bare 404) -- see control_plane.provision and versioning.version_binding's 1.4.0 conditional-obligation list.

**Subordinate ruling:**
- 従属判断 9

**Introduced in:** contract 1.4.0

---

## control_endpoints.revoke_credential.semantics

**Value (verbatim, full value copied from the contract JSON `spec/data-service-api.v1.json`; the history marker is embedded in it):**

> Terminal. A revoked credential can never be made valid again; enable does not apply. Revoking the last remaining active control credential is permitted but requires a valid confirmation per the destructive_confirmation section's definition. Every other revocation -- an application credential, or a control credential that is not the last active one -- requires no confirmation. Resolved in contract 1.2.0 (previously a pending contract decision, the destructive-confirmation semantics question).

**Subordinate ruling:**
- 従属判断 6

**Introduced in:** contract 1.2.0

---

## control_plane.authority

**Value (verbatim, full value copied from the contract JSON `spec/data-service-api.v1.json`; the history marker is embedded in it):**

> Application credentials fail closed on every control endpoint; control credentials are rejected on data/schema endpoints. An audit credential is accepted only on the read-only control_capabilities, list_applications, list_credentials, and (since 1.4.0, subordinate ruling 9) audit_query endpoints; every other control endpoint fails it closed with FORBIDDEN.

**Subordinate ruling:**
- 従属判断 9

**Introduced in:** contract 1.4.0

---

## definitions.EntityDescriptor.properties.field_types.description

**Value (verbatim, full value copied from the contract JSON `spec/data-service-api.v1.json`; the history marker is embedded in it):**

> Since 1.6.0 (subordinate ruling 11, item 3, conditional on application_catalog being provided -- versioning.version_binding): The field-type vocabulary gains a seventh member, json, meaning any JSON value. A field created without a declared type has type json -- this names an existing default rather than introducing a new one, and there is no "unknown" member of the vocabulary: every field carries a real type. EntityDescriptor.field_types maps every name in fields to that field's type, drawn from that same vocabulary. What a client declared -- through SchemaOperationRequest.field_types on create_entity, or field_type on add_field -- is what the catalog reports back, and a field for which no type was declared reports json. Where a schema operation later redeclares a field's type, the catalog reports the type most recently declared. The catalog reports only facts this contract's own schema operations can establish: it declares neither nullability, nor default values, nor whether a field is required, because no schema operation defined here establishes any of them; a later version that gives schema operations such a notion gives it to the catalog in that same version. object and array are narrower than json: a field declared json accepts any JSON value, including but not limited to objects and arrays, while a field declared object or array accepts only that shape -- and the catalog reports the narrower word it was declared with, never rounding it up to json. SchemaOperationRequest.field_types and EntityDescriptor.field_types share one object shape but not one coverage rule: the request's object may be partial -- any name in fields that it omits is created with type json -- while the catalog's object is always total over that entity's own fields. SchemaOperationRequest.field_types is never required: a create_entity naming only fields remains a valid request, creating json fields. A field_types naming a field the request's own fields does not name, a field_types value outside this vocabulary, or a field_types sent without fields, each fails VALIDATION_FAILED; none of the three is silently ignored. add_field continues to carry a single field_type for the single field it adds.

**Subordinate ruling:**
- 従属判断 11

**Introduced in:** contract 1.6.0

---

## definitions.Mutation.properties.values.description

**Value (verbatim, full value copied from the contract JSON `spec/data-service-api.v1.json`; the history marker is embedded in it):**

> Deliberately left open (subordinate ruling 7(A)): the field-name vocabulary is entity-defined, not fixed by this contract, so an additionalProperties: false closure here would be meaningless -- there is no fixed key set to close against.

**Subordinate ruling:**
- 従属判断 7

**Introduced in:** contract 1.2.0

---

## definitions.ScopedMutation.properties.values.description

**Value (verbatim, full value copied from the contract JSON `spec/data-service-api.v1.json`; the history marker is embedded in it):**

> Deliberately left open (subordinate ruling 7(A)): the field-name vocabulary is entity-defined, not fixed by this contract, so an additionalProperties: false closure here would be meaningless -- there is no fixed key set to close against.

**Subordinate ruling:**
- 従属判断 7

**Introduced in:** contract 1.2.0

---

## destructive_confirmation.phrase_construction.rules[3]

**Value (verbatim, full value copied from the contract JSON `spec/data-service-api.v1.json`; the history marker is embedded in it):**

> State-fingerprinted for re-creatable targets: a target identifiable by a name that can be destroyed and later recreated (e.g. an entity or index) includes a state fingerprint in its phrase, so that either the target's re-creation under the same name, or any other schema change, invalidates any previously valid phrase for that name -- recreating the identical structure under the same name after a drop does not resurrect an old phrase's validity.

**Note:** this value carries no dedicated history marker; the scanner matched it on the normative text's "previously" (in "previously valid phrase"). The ruling attribution below was assigned from the value's content, not from a marker.

**Subordinate ruling:**
- 従属判断 6

**Introduced in:** contract 1.2.0

---

## destructive_confirmation.resolved_in

**Value (verbatim, full value copied from the contract JSON `spec/data-service-api.v1.json`; the history marker is embedded in it):**

> 1.2.0. Defines the declare-and-echo confirmation semantics for every destructive operation in this contract, common across data, schema, and control-plane surfaces (CCR_DISPOSITION.md subordinate ruling 6).

**Subordinate ruling:**
- 従属判断 6

**Introduced in:** contract 1.2.0

---

## endpoints.audit_query.deprecation_note

**Value (verbatim, full value copied from the contract JSON `spec/data-service-api.v1.json`; the history marker is embedded in it):**

> Since 1.4.0 (subordinate ruling 9, item 7): this entry's path is retained as an alias of control_endpoints.audit_query for one further minor version after 1.4.0, resolving to the identical operation on the control surface's own host, not this section's application surface. audit_query's canonical classification is control_endpoints.audit_query; a client should prefer POST /control/v1/audit/query going forward. This entry is not removed here (removal would be a non-additive contract change) -- it is retained, unmodified in method/request/response shape, specifically so a pre-1.4.0-shaped client is not broken by the reclassification.

**Subordinate ruling:**
- 従属判断 9

**Introduced in:** contract 1.4.0

---

## limits.audit_requests_per_minute_note

**Value (verbatim, full value copied from the contract JSON `spec/data-service-api.v1.json`; the history marker is embedded in it):**

> Since 1.4.0 (subordinate ruling 9, item 8, conditional on audit_query being provided -- versioning.version_binding). A pre-authentication fixed window governing the audit_query endpoint specifically (both its canonical and alias paths, control_endpoints.audit_query/endpoints.audit_query.deprecation_note), separate from control_requests_per_minute: an implementation publishing this class enforces it as audit_query's own window and does not also charge audit_query requests against control_requests_per_minute, so that a high-frequency audit_query poller cannot exhaust the same window a break-glass control-plane operation (e.g. revoke_credential) depends on.

**Subordinate ruling:**
- 従属判断 9

**Introduced in:** contract 1.4.0

---

## schemas.AuditResult.properties.events.items.description

**Value (verbatim, full value copied from the contract JSON `spec/data-service-api.v1.json`; the history marker is embedded in it):**

> Deliberately left open (subordinate ruling 7(A)): audit.fields is itself an open-ended, additive vocabulary, and a per-event shape is not one of the 11 response schemas or nested row schemas this ruling closes.

**Subordinate ruling:**
- 従属判断 7

**Introduced in:** contract 1.2.0

---

## schemas.CapabilityDocument.description

**Value (verbatim, full value copied from the contract JSON `spec/data-service-api.v1.json`; the history marker is embedded in it):**

> The envelope itself is closed (additionalProperties: false at this level), but capabilities/limits/limit_enforcement below and each capability entry's own value schema deliberately keep additionalProperties open: an open key space naming deployment-declared capabilities and limit classes is an intentional, distinct mechanism, not an oversight comparable to the closed response envelopes elsewhere in this contract (subordinate ruling 7(A)).

**Subordinate ruling:**
- 従属判断 7

**Introduced in:** contract 1.2.0

---

## schemas.CapabilityDocument.properties.surfaces.description

**Value (verbatim, full value copied from the contract JSON `spec/data-service-api.v1.json`; the history marker is embedded in it):**

> Since 1.6.0 (subordinate ruling 11, item 2; unconditional -- versioning.version_binding): surfaces names the absolute base URLs at which this deployment's own surfaces are reached, as declared by the deployer -- never derived, and never to be inferred by a client from the URL it happened to use. surfaces.data.base_url ends at versioning.base_path; surfaces.control.base_url ends at versioning.control_base_path. The data surface's capability document and the control surface's own capability document return the same surfaces object, so a client holding either base URL can reach the other surface, and either document, fetched again at its own declared URL, answers with the same contract_version and the same surfaces -- the rest of each document remains scoped to the credential presented. A deployment declaring control_plane as unavailable omits surfaces.control. Neither URL ends in a trailing slash, so that appending a path to it yields exactly one separator. Whether the two surfaces share a host is read from the origins (scheme, host and port -- not the path) of these two URLs -- the co-hosting versioning.control_discovery permits -- and is never assumed; where surfaces.control is absent, the surfaces are not co-hosted. Where the two surfaces run as separate processes, both are configured from the same declaration: neither can verify the other's document, so a deployment whose two documents disagree is non-conformant, and a client is given no rule for preferring one over the other.

**Subordinate ruling:**
- 従属判断 11

**Introduced in:** contract 1.6.0

---

## schemas.CredentialIssued.properties.secret.description

**Value (verbatim, full value copied from the contract JSON `spec/data-service-api.v1.json`; the history marker is embedded in it):**

> Since 1.6.0 (subordinate ruling 11, item 1; unconditional -- versioning.version_binding): CredentialIssued.secret -- and the secret a rotate response returns, wherever this contract defines one -- is the complete bearer token for the surface that credential is for: a client presents that exact string, verbatim, as Authorization: Bearer <secret>; an application credential on the application surface, a control or audit credential on the control surface (security.schemes.control_credential continues to state that application credentials are not accepted there). A client MUST NOT compose it from, split it into, or derive it from any other field of the response -- credential_id is returned as its own field, for naming the credential in later control operations, and is never something a client extracts from the secret. Its internal structure is opaque; an implementation may change that structure without a contract change, and no client may depend on it. The service still stores only a verifier/digest and never returns the secret again.

**Subordinate ruling:**
- 従属判断 11

**Introduced in:** contract 1.6.0

---

## schemas.CredentialRotated.properties.secret.description

**Value (verbatim, full value copied from the contract JSON `spec/data-service-api.v1.json`; the history marker is embedded in it):**

> Since 1.6.0 (subordinate ruling 11, item 1; unconditional -- versioning.version_binding): CredentialIssued.secret -- and the secret a rotate response returns, wherever this contract defines one -- is the complete bearer token for the surface that credential is for: a client presents that exact string, verbatim, as Authorization: Bearer <secret>; an application credential on the application surface, a control or audit credential on the control surface (security.schemes.control_credential continues to state that application credentials are not accepted there). A client MUST NOT compose it from, split it into, or derive it from any other field of the response -- credential_id is returned as its own field, for naming the credential in later control operations, and is never something a client extracts from the secret. Its internal structure is opaque; an implementation may change that structure without a contract change, and no client may depend on it. The service still stores only a verifier/digest and never returns the secret again.

**Subordinate ruling:**
- 従属判断 11

**Introduced in:** contract 1.6.0

---

## schemas.MutationResult.properties.assigned_addresses.items.properties.address.description

**Value (verbatim, full value copied from the contract JSON `spec/data-service-api.v1.json`; the history marker is embedded in it):**

> Deliberately left open (subordinate ruling 7(A)): the address field-name vocabulary is entity-defined (EntityDescriptor.address_fields), not fixed by this contract.

**Subordinate ruling:**
- 従属判断 7

**Introduced in:** contract 1.2.0

---

## schemas.SchemaOperationRequest.properties.field_types.description

**Value (verbatim, full value copied from the contract JSON `spec/data-service-api.v1.json`; the history marker is embedded in it):**

> Since 1.6.0 (subordinate ruling 11, item 3, conditional on schema_operations being provided -- versioning.version_binding): The field-type vocabulary gains a seventh member, json, meaning any JSON value. A field created without a declared type has type json -- this names an existing default rather than introducing a new one, and there is no "unknown" member of the vocabulary: every field carries a real type. EntityDescriptor.field_types maps every name in fields to that field's type, drawn from that same vocabulary. What a client declared -- through SchemaOperationRequest.field_types on create_entity, or field_type on add_field -- is what the catalog reports back, and a field for which no type was declared reports json. Where a schema operation later redeclares a field's type, the catalog reports the type most recently declared. The catalog reports only facts this contract's own schema operations can establish: it declares neither nullability, nor default values, nor whether a field is required, because no schema operation defined here establishes any of them; a later version that gives schema operations such a notion gives it to the catalog in that same version. object and array are narrower than json: a field declared json accepts any JSON value, including but not limited to objects and arrays, while a field declared object or array accepts only that shape -- and the catalog reports the narrower word it was declared with, never rounding it up to json. SchemaOperationRequest.field_types and EntityDescriptor.field_types share one object shape but not one coverage rule: the request's object may be partial -- any name in fields that it omits is created with type json -- while the catalog's object is always total over that entity's own fields. SchemaOperationRequest.field_types is never required: a create_entity naming only fields remains a valid request, creating json fields. A field_types naming a field the request's own fields does not name, a field_types value outside this vocabulary, or a field_types sent without fields, each fails VALIDATION_FAILED; none of the three is silently ignored. add_field continues to carry a single field_type for the single field it adds.

**Subordinate ruling:**
- 従属判断 11

**Introduced in:** contract 1.6.0

---

## security.schemes.application_credential.description

**Value (verbatim, full value copied from the contract JSON `spec/data-service-api.v1.json`; the history marker is embedded in it):**

> Opaque credential presented over TLS. The service stores only a verifier/digest and never returns the secret. Since 1.6.0 (subordinate ruling 11, item 1; unconditional -- versioning.version_binding): CredentialIssued.secret -- and the secret a rotate response returns, wherever this contract defines one -- is the complete bearer token for the surface that credential is for: a client presents that exact string, verbatim, as Authorization: Bearer <secret>; an application credential on the application surface, a control or audit credential on the control surface (security.schemes.control_credential continues to state that application credentials are not accepted there). A client MUST NOT compose it from, split it into, or derive it from any other field of the response -- credential_id is returned as its own field, for naming the credential in later control operations, and is never something a client extracts from the secret. Its internal structure is opaque; an implementation may change that structure without a contract change, and no client may depend on it. The service still stores only a verifier/digest and never returns the secret again.

**Subordinate ruling:**
- 従属判断 11

**Introduced in:** contract 1.6.0

---

## security.schemes.control_credential.description

**Value (verbatim, full value copied from the contract JSON `spec/data-service-api.v1.json`; the history marker is embedded in it):**

> A separately authenticated Control/Audit authority; application credentials are not accepted. The service stores only a verifier/digest; the secret is returned exactly once, at issue or rotate time. An authentication secret is never reused as signing-key or other cryptographic material. Since 1.6.0 (subordinate ruling 11, item 1; unconditional -- versioning.version_binding): CredentialIssued.secret -- and the secret a rotate response returns, wherever this contract defines one -- is the complete bearer token for the surface that credential is for: a client presents that exact string, verbatim, as Authorization: Bearer <secret>; an application credential on the application surface, a control or audit credential on the control surface (security.schemes.control_credential continues to state that application credentials are not accepted there). A client MUST NOT compose it from, split it into, or derive it from any other field of the response -- credential_id is returned as its own field, for naming the credential in later control operations, and is never something a client extracts from the secret. Its internal structure is opaque; an implementation may change that structure without a contract change, and no client may depend on it. The service still stores only a verifier/digest and never returns the secret again.

**Subordinate ruling:**
- 従属判断 11

**Introduced in:** contract 1.6.0

---

## structured_operations.reserved_entity_names_note

**Value (verbatim, full value copied from the contract JSON `spec/data-service-api.v1.json`; the history marker is embedded in it):**

> Since 1.4.0 (subordinate ruling 9, item 6; unconditional -- versioning.version_binding). audit_events is reserved across implementations as an entity/collection name, for platform-managed audit storage an implementation may keep alongside application-declared entities in the same underlying storage. This documents an existing implementation practice (both peers already refuse this exact name defensively) rather than introducing new behavior; a client entity/schema operation naming audit_events is refused (a validation-class error; the exact contract code is implementation-defined) rather than silently colliding with platform storage. This list is additive: a future implementation-shared reserved name may be appended without removing this one.

**Subordinate ruling:**
- 従属判断 9

**Introduced in:** contract 1.4.0

---

## versioning.compatibility

**Value (verbatim, full value copied from the contract JSON `spec/data-service-api.v1.json`; the history marker is embedded in it):**

> Additive fields and capabilities are allowed; removal or semantic change requires a new major version. The control surface follows the same compatibility rules. A response or request schema closure (additionalProperties: false) that narrows what the schema accepts, applied only to stop a schema from implying the existence of a field an implementation does not actually return or accept, is compatible as a minor-version change under version_binding's version-declaration discipline below -- it is not the kind of removal or semantic change that would otherwise require a new major version, because it constrains the documentation of shape rather than removing a previously-required capability or altering accepted semantics.

**Note:** this value carries no dedicated history marker; the scanner matched it on the normative text's "previously" (in "previously-required capability"). The ruling attribution below was assigned from the value's content, not from a marker.

**Subordinate ruling:**
- 従属判断 7

**Introduced in:** contract 1.2.0

---

## versioning.version_binding

**Value (verbatim, full value copied from the contract JSON `spec/data-service-api.v1.json`; the history marker is embedded in it):**

> An implementation's own declared contract_version is the general rule for which version's definitions it is claiming conformance to: only an implementation declaring 1.2.0 or higher claims conformance to the obligations 1.2.0 introduced -- exhaustively: (1) the destructive_confirmation section in full, (2) errors.details_vocabulary's LIMIT_EXCEEDED.limit_class requirement, (3) subordinate ruling 7(A)'s response/request schema closures (additionalProperties: false on every schema and definition this version lists as closed), and (4) capability_status.rules' limits/limit_enforcement vocabulary-restriction rule. Only an implementation declaring 1.3.0 or higher additionally claims conformance to the obligations 1.3.0 introduced (subordinate ruling 8): audit-role acceptance on the three read-only control endpoints (control_capabilities, list_applications, list_credentials) with FORBIDDEN fail-closed on every other control endpoint; the per-application issuance-freeze FORBIDDEN refusal; and the optional target_id audit field and optional must_rotate exposure -- both are optional fields, so declaring 1.3.0 does not require emitting either one, only that their documented semantics hold whenever they are emitted. Only an implementation declaring 1.4.0 or higher additionally claims conformance to the obligations 1.4.0 introduced (subordinate ruling 9). Three of those obligations are unconditional in the same sense as every obligation enumerated above -- they bind simply by declaring 1.4.0, independent of any capability's own status: (a) audit_events is a reserved entity/collection name an implementation may refuse a client schema/collection operation against (structured_operations.reserved_entity_names_note); (b) where a control surface is provided at all (control_plane other than unavailable, the same precondition subordinate ruling 8 already carries), an audit-role credential is additionally accepted on the audit_query control endpoint alongside the three read-only endpoints ruling 8 already named, with FORBIDDEN fail-closed on every other control endpoint unchanged -- this holds whether that implementation's own audit_query capability is itself enabled or unavailable, since route registration and role authorization there precede the capability-availability check (an unavailable audit_query still answers an authorized audit-role caller with CAPABILITY_UNSUPPORTED, never FORBIDDEN or a bare 404). Added by a later revision of this document still under this same 1.4.0 label (subordinate ruling 10, item 2): this acceptance is scoped to the control surface's audit_query control endpoint (the canonical POST /control/v1/audit/query, and its alias as served on the control host -- the same host scoping endpoints.audit_query.deprecation_note already states, and this document's own 1.4.0 conditional obligation (5) below, which requires both paths to answer as the identical operation). A data-plane host is not thereby obliged to authenticate control or audit credentials merely because it declares control_plane as something other than unavailable; where such a host holds no control-credential store, it may refuse a control or audit credential presented on its own POST /v1/audit/query alias as an unknown credential (AUTH_INVALID); it is not thereby required to accept, verify, or forward it. Co-hosting both surfaces in one process remains permitted (versioning.control_discovery) and is not what this scoping addresses; and (c) audit_query's canonical classification in this document is control_endpoints (POST /control/v1/audit/query), with the pre-1.4.0 endpoints.audit_query path (POST /v1/audit/query) retained as an alias of the identical operation for one further minor version. The remaining 1.4.0 obligations are conditional, unlike every obligation enumerated above for earlier versions: they bind an implementation declaring 1.4.0 only insofar as that implementation's own capabilities() additionally declares audit_query as something other than unavailable, since whether audit_query is provided at all remains a capability-declared matter, not a version-mandated one (the same posture control_plane.provision already establishes for the control surface as a whole) -- an implementation may declare contract_version 1.4.0 while its own audit_query stays unavailable (for example, no audit datastore is configured for this deployment) and remains fully conformant to 1.4.0 throughout, without being held to, or claiming, any obligation in this conditional list while unavailable. Where an implementation does declare audit_query as enabled or partial, 1.4.0 additionally requires -- exhaustively: (1) AuditQueryRequest.after, when accepted, is treated as an opaque cursor encoding a position under the ordering in (2) rather than interpreted as an event_id or a numeric offset, and a value that fails to decode or no longer resolves under the request's own filters is answered with VALIDATION_FAILED; (2) AuditResult.events[] is returned in the total order (recorded_at, plane, event_id); (3) each returned event carries a plane field whose value is control or application; (4) event_class is a vocabulary the implementation itself declares (its own capabilities().audit_query.event_classes), not a fixed contract enum, and 1.4.0 requires no particular member of it; (5) both the canonical POST /control/v1/audit/query path and the POST /v1/audit/query alias actually answer requests as the identical operation, rather than one of the two being merely routed without a working handler behind it; and (6) where audit_requests_per_minute is published in limits/limit_enforcement, it governs the audit_query endpoint specifically, as its own declared and separately enforceable limit class, and is not satisfied by also enforcing control_requests_per_minute for audit_query requests. Only an implementation declaring 1.5.0 or higher additionally claims conformance to the obligation 1.5.0 introduces (subordinate ruling 10, item 1). Like 1.4.0's own conditional obligations, this one binds an implementation declaring 1.5.0 only insofar as that implementation's own capabilities() declares audit_query as something other than unavailable; an implementation may declare contract_version 1.5.0 while its own audit_query stays unavailable and remains fully conformant to 1.5.0 throughout, without being held to this obligation while unavailable. Since 1.5.0 (subordinate ruling 10, item 1, conditional): operations and target_kinds are vocabularies each implementation declares for itself at capabilities().audit_query.operations / .target_kinds -- the sets of values the operation and target_kind fields of events returned by audit_query can take. As with event_classes, this contract enumerates no fixed enum and requires no particular member (declare-the-hazard). An implementation declaring 1.5.0 or higher whose audit_query is other than unavailable MUST declare both, and every event it returns MUST carry values drawn from the declared sets; the same superset relation holds for event_classes, stated here explicitly. Only an implementation declaring 1.6.0 or higher additionally claims conformance to the obligations 1.6.0 introduces (subordinate ruling 11). Two of those obligations are unconditional in the same sense as every obligation enumerated above -- they bind simply by declaring 1.6.0, independent of any capability's own status: (a) its GET /v1/capabilities document carries surfaces.data.base_url, the absolute base URL of its own data surface, and -- where a control surface is provided at all (control_plane other than unavailable, the same precondition subordinate rulings 8 and 9 already carry) -- both surfaces' capability documents additionally carry surfaces.control.base_url, each document carrying the same surfaces; and (b) the secret returned by any issue or rotate path it offers, in band or out of band, is accepted verbatim as a bearer token on the surface that credential is for, with no composition, splitting, or derivation required of the client (security.schemes). The remaining 1.6.0 obligations are conditional, in the same sense 1.4.0's own conditional list is: they bind only insofar as the implementation's own capabilities() declares the named capability as something other than unavailable. Where it declares application_catalog as something other than unavailable: (1) every EntityDescriptor it returns carries field_types, total over that entity's own fields, reporting json for any field created without a declared type. Where it declares schema_operations as something other than unavailable: (2) a create_entity it executes accepts field_types and creates each field named there with the type declared there, and an add_field it executes accepts every member of the seven-member vocabulary, json included; a field_types naming a field outside the request's own fields, carrying a value outside that vocabulary, or sent without fields, is refused with VALIDATION_FAILED. 1.6.0 introduces no obligation on what a client must send: SchemaOperationRequest.field_types is optional wherever it appears, and a request valid under 1.5.0 stays valid. An implementation still declaring 1.5.0 is not held to any 1.6.0-only obligation retroactively. Every obligation introduced under a given version label -- whether enumerated above or added by a later revision of this document still under that same label -- follows this same general rule. An implementation still declaring 1.1.0 remains conformant to 1.1.0 semantics and is not held to any 1.2.0-only, 1.3.0-only, 1.4.0-only, 1.5.0-only, or 1.6.0-only obligation retroactively, an implementation declaring 1.2.0 is not held to any 1.3.0-only, 1.4.0-only, 1.5.0-only, or 1.6.0-only obligation retroactively, an implementation declaring 1.3.0 is not held to any 1.4.0-only, 1.5.0-only, or 1.6.0-only obligation retroactively, and an implementation declaring 1.4.0 is not held to any 1.5.0-only or 1.6.0-only obligation retroactively. A peer's version-flip -- the commit that changes its own declared contract_version -- must land in the same commit as the real behavior change it claims; declaring a higher version before the corresponding behavior exists, or shipping the behavior while the declaration lags, are both non-conformant.

**Subordinate ruling(s):**
- 従属判断 7
- 従属判断 8
- 従属判断 9
- 従属判断 10
- 従属判断 11

**Introduced in:** contract 1.2.0 through 1.6.0 (cumulative)

---
