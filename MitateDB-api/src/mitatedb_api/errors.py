"""Safe, stable foundation errors.

These exceptions are deliberately free of SQL, connection details, and raw
storage errors. An HTTP adapter can map them to the common error contract once
that contract is extracted into ``spec/``.
"""


class FoundationError(Exception):
    """Base class for errors safe to classify at an API boundary."""


class AuthenticationError(FoundationError):
    pass


class AuthenticationRequiredError(AuthenticationError):
    """WP-4 control-plane addition: raised when NO credential was presented
    at all (contract ``AUTH_REQUIRED``), distinct from the base class' own
    ``AUTH_INVALID`` meaning (a credential WAS presented but is wrong,
    disabled, or revoked). A subclass of ``AuthenticationError`` (not a
    sibling) so any existing ``isinstance(exc, AuthenticationError)`` check
    elsewhere in this codebase still matches it -- classification order
    matters wherever both are checked (``control_http.py``'s own
    ``_CLASSIFY_ORDER`` checks this subclass first).

    The application-plane HTTP layer (``http.py``) handles this same
    missing-vs-invalid distinction structurally instead, with a local
    ``_CredentialMissing`` exception raised *before* any session-layer
    ``authenticate()`` call -- that layer never needs this class. The
    control plane's own ``ControlPlaneService`` (``control_plane.py``)
    accepts ``secret: Optional[str]`` directly on every public method and
    is exercised by WP-4's own direct tests with no HTTP layer mounted at
    all, so the missing-credential distinction has to live inside the
    service layer itself here, not only at an HTTP adaptation boundary.
    """


class AuthorizationError(FoundationError):
    pass


class ValidationError(FoundationError):
    """Phase 9 WP-3a (design docs/design/
    PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md D-3 (5)):
    `details` is OPTIONAL here (`None` by default) -- this WP gives the
    D-3 `details` shape only to the denials it newly introduces (an
    `enum`/`nullable` violation at the value-validation choke point, an
    `alter_field` naming `field_type`, an unrecognized `field_constraints`
    entry key, a `field_constraints` sent without `fields`, a non-boolean
    `nullable` on `field_constraints` or `alter_field`, and an
    `alter_field`/`add_field` naming a field the entity does not have),
    never retrofitting it onto any of this class's other pre-existing
    call sites (that full rollout is WP-3e's own, separate task, D-3
    実装の形 3). `getattr(exc, "details",
    None)` (`http.py::_problem_for_exception`'s existing convention)
    already tolerates an instance with no `details` attribute at all --
    passing `details=None` here deliberately leaves that attribute UNSET
    (not set to `{}`), so an untouched call site's own error shape is
    byte-for-byte unchanged by this addition."""

    def __init__(self, message, *, details=None):
        super().__init__(message)
        if details is not None:
            self.details = dict(details)


class ResourceLimitError(FoundationError):
    """Raised when a finite, deployment-configurable resource bound
    (``FoundationConfig``) is exceeded. ``details['limit_class']`` names the
    common contract's own ``limits.classes`` member this exceeded bound
    belongs to (contract ``errors.details_vocabulary.LIMIT_EXCEEDED.
    limit_class``, WP-5 Q1-D7(B)) -- every call site is required to pass one
    (no default: a missing classification here would silently reintroduce
    the pre-WP-5 vocabulary gap this attribute exists to close).
    """

    def __init__(self, message, *, limit_class):
        super().__init__(message)
        self.details = {"limit_class": limit_class}


class DestructiveConfirmationRequired(FoundationError):
    """Raised when a destructive operation (contract ``destructive_
    confirmation``: currently ``delete`` on this peer) is attempted without
    a valid confirmation echo -- ``destructive`` was not exactly ``True``,
    or ``confirm`` did not exactly match the server's own currently
    recomputed ``required_confirmation`` phrase for this exact request
    (contract ``valid_confirmation``: no truthy/partial/prefix acceptance).

    ``details`` carries the contract's four required declaration keys
    (``required_confirmation``/``consequence``/``reversible_alternative``/
    ``recovery``, contract ``destructive_confirmation.denial.details_
    keys``) so an HTTP adapter or conformance plug can surface them
    verbatim on the denial -- exactly the same ``getattr(exc, "details",
    None)`` convention ``conformance_adapter_mitatedb.py::_deny`` already
    uses for every other ``FoundationError`` subclass.
    """

    def __init__(self, message, *, details):
        super().__init__(message)
        self.details = dict(details)


class ConflictError(FoundationError):
    """Phase 9 WP-3a (design D-3 (5)/(6)): same optional `details` as
    `ValidationError` above, for exactly one new caller -- a rejected
    `alter_field` whose declared constraints an existing row would
    violate (`backend.StorageBackend.alter_field_constraints`), which
    carries `{"field": ..., "violated_declaration": "enum"|"nullable"}`
    (never a row value or a row count, SI-10). Every pre-existing
    `ConflictError` call site (a unique-index/row-write conflict) keeps
    raising with no `details` at all."""

    def __init__(self, message, *, details=None):
        super().__init__(message)
        if details is not None:
            self.details = dict(details)


class NotFoundError(FoundationError):
    pass


class PreconditionFailedError(FoundationError):
    """Phase 9 WP-3b (design docs/design/
    PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md D-4/D-3 (6),
    追補 2 S-h): raised when a caller-presented `plan` token
    (`structured_operations.dry_run.plan`) no longer matches this same
    request re-digested against the current schema state -- the first
    time this peer raises the common contract's `PRECONDITION_FAILED`
    code at all (`http.py`'s own pre-WP-3b comment: "this peer simply
    never emits ... PRECONDITION_FAILED"; `revision_preconditions`,
    the row-level precondition, stays `unavailable` and unrelated --
    L9-2b, design table L9-2 split).

    `details` carries `{"violated_declaration": "plan"}` (`errors.
    details_vocabulary.violated_declaration_vocabulary`'s own `plan`
    member) -- always present, since a plan mismatch is the ONLY
    reason this class is ever raised; not one of D-3 (4)'s three
    4-key-mandatory codes (`VALIDATION_FAILED`/`IDENTIFIER_INVALID`/
    `CAPABILITY_UNSUPPORTED`), so `field`/`declared_type`/`observed_
    type` are never required here and never supplied."""

    def __init__(self, message, *, details=None):
        super().__init__(message)
        self.details = dict(details) if details is not None else {"violated_declaration": "plan"}


class AuthorizationStateUnavailable(FoundationError):
    """Raised when authorization state cannot be safely established."""


class StorageConfigurationError(FoundationError):
    """WP-2 review M-1 (design docs/design/MITATEDB_PHASE3_HTTP_PERSISTENCE_
    V1.md v1.2 R-4/R-6): raised when a storage backend refuses an operation
    because of a PERMANENT privilege/grant misconfiguration (PostgreSQL
    ``InsufficientPrivilege`` -- a role missing a GRANT it should have,
    e.g. a provisioning defect or a manual grant regression) rather than a
    TRANSIENT unavailability (the platform database unreachable, a
    connection timing out, a deadlock).

    Deliberately a distinct class from :class:`AuthorizationStateUnavailable`
    and never mapped to that class's own future contract code
    (``AUTH_STATE_UNAVAILABLE``): R-6's own audit-write exemption (ii) --
    "the two exceptions [to durably auditing every denial] are ... `AUTH_
    STATE_UNAVAILABLE` (store itself is unreachable and audit write is
    also impossible)" -- is reserved for genuine store unreachability, not
    for a role that IS reachable but was granted the wrong privileges. A
    catch-all ``except psycopg.Error`` that folded ``InsufficientPrivilege``
    into ``AuthorizationStateUnavailable`` would silently manufacture a
    false instance of that exemption for a case R-6 never intended to
    cover -- a permanent misconfiguration that keeps failing on every
    retry, not a transient condition auditing may legitimately be unable
    to observe.

    Proposed future HTTP mapping (no composition root exists yet in this
    WP to wire it): the common contract's own ``SERVICE_UNAVAILABLE``
    code (spec/data-service-api.v1.json ``errors.codes``) -- the generic
    "the backend rejected this request for a reason outside the caller's
    control" bucket this repository's own sibling peer (r2db-api's
    ``credential_store.py``) already uses for an unclassified backend
    write failure -- rather than ``AUTH_STATE_UNAVAILABLE``, whose own
    contract meaning ("authorization state cannot be safely established
    right now") implies a condition a retry might resolve; a privilege
    misconfiguration will not resolve itself on retry and should alert an
    operator differently than a transient outage would. This mapping
    decision belongs to the WP-3/WP-4 composition root/HTTP adapter, not
    this class -- reported here as the proposal WP-2's review asked for.
    """


class PlatformUpgradePending(StorageConfigurationError):
    """Q4 rework (supervisor ruling 2026-09-05, H-1; design docs/design/
    Q4_DB_SIDE_SINGLE_TRUTH_V1.md D-3(f)/§3.8 F-12): raised (by `backend_
    postgres.py`'s own `_guard_pending_platform_upgrades`) instead of the
    bare `StorageConfigurationError` above for exactly one condition --
    an application's own per-application platform-upgrade ledger is
    missing an entry this package requires.

    A DISTINCT subclass, not a bare `StorageConfigurationError`, because
    F-12 is design §3.8's own explicitly named exception to SI-10's
    general "never surface `str(exc)` on the wire" discipline (`http.py::
    _problem_for_exception`'s own docstring/comment): "F-12だけは起動時
    ではなくcell open時であり、API応答として利用者に届く...F-12の
    メッセージは未適用の番号とopsコマンド名を示す". Every OTHER
    `StorageConfigurationError` site in this peer (the missing-`0006`
    reads in `field_domains`/`field_types`/`all_field_types`) keeps the
    generic, fixed `_problem_for_exception` message -- `isinstance`
    narrows to exactly this one subclass, so a future `Storage
    ConfigurationError` raise elsewhere does not silently start leaking
    its own message onto the wire by inheriting this behavior unasked.
    `platform_upgrades._f12_message`'s own construction already excludes
    DSN/credential/internal-hostname/declared-value text (only the
    missing upgrade numbers and the next `ops` command appear), so this
    message is safe to surface verbatim.
    """


class AuditSinkUnavailable(FoundationError):
    """Phase 4 (design docs/design/PHASE4_DURABLE_AUDIT_SINK_V1.md D-2/D-3,
    work order WP-3(a)): raised when the durable application-plane audit
    sink (`application_audit.PostgresApplicationAuditSink` in production,
    `application_audit.ApplicationAuditSink` for the in-memory/test
    configuration) could not durably record a fail-closed-class event --
    a pre-commit write ahead of a schema change or a confirmed-destructive
    delete, a coalesced denial's first-occurrence write, or the
    commit-failure `outcome="error"` row D-2 requires. The operation or
    denial this event would have accompanied is refused rather than
    proceeding (or being reported as denied) un-audited -- fail-closed by
    construction, mirroring r2db-api's own `fail("SERVICE_UNAVAILABLE",
    ...)` call sites for the identical failure class.

    Deliberately a distinct class from :class:`StorageConfigurationError`
    (reserved for a PERMANENT PostgreSQL privilege/grant misconfiguration
    on the DATA backend, not the audit sink) and from
    :class:`AuthorizationStateUnavailable` (the credential-store's own
    "cannot safely establish authorization state" condition) -- this is
    the generic "a dependency this request needed is not answering right
    now" bucket, specific to the audit-sink dependency Phase 4 introduces.
    Maps to the common contract's `SERVICE_UNAVAILABLE` code
    (`http.py::_CLASSIFY_ORDER`).
    """


class CapabilityError(FoundationError):
    """Raised for a name that is part of the common contract's own
    vocabulary -- a mutation operation (``structured_operations.
    allowed_mutations``: insert/update/upsert/delete) or a query filter
    operator (``allowed_query_operators``, e.g. ``matches``, CCR-13 §0.5
    Q-2) -- but which this peer implementation does not itself execute
    through the entry point the caller used. Examples: ``upsert`` (no peer
    implementation at all), ``update``/``delete`` presented to
    ``ApplicationCell.transact`` (this peer provides those only through
    their own dedicated ``update``/``delete`` methods, not through
    ``transact``), or a ``matches`` filter (this peer's filter grammar has
    an acceptance surface for it -- an operator name, checked before the
    supported-operator allowlist -- but no execution path). This is
    distinct from :class:`ValidationError`, which is for a request outside
    the contract's vocabulary entirely (an unrecognized operation/operator
    name, a malformed shape). An HTTP adapter or conformance plug maps this
    to the common contract's ``CAPABILITY_UNSUPPORTED`` error code.
    """
