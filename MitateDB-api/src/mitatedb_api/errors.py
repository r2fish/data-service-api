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
    pass


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
