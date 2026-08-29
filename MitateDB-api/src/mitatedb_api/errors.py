"""Safe, stable foundation errors.

These exceptions are deliberately free of SQL, connection details, and raw
storage errors. An HTTP adapter can map them to the common error contract once
that contract is extracted into ``spec/``.
"""


class FoundationError(Exception):
    """Base class for errors safe to classify at an API boundary."""


class AuthenticationError(FoundationError):
    pass


class AuthorizationError(FoundationError):
    pass


class ValidationError(FoundationError):
    pass


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
    pass


class NotFoundError(FoundationError):
    pass


class AuthorizationStateUnavailable(FoundationError):
    """Raised when authorization state cannot be safely established."""


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
