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
    """Raised for an operation that is part of the common contract's own
    mutation vocabulary (``structured_operations.allowed_mutations``:
    insert/update/upsert/delete) but which this peer implementation does
    not itself execute through the entry point the caller used -- e.g.
    ``upsert`` (no peer implementation at all) or ``update``/``delete``
    presented to ``ApplicationCell.transact`` (this peer provides those
    only through their own dedicated ``update``/``delete`` methods, not
    through ``transact``). This is distinct from :class:`ValidationError`,
    which is for a request outside the contract's vocabulary entirely (an
    unrecognized operation name, a malformed shape). An HTTP adapter or
    conformance plug maps this to the common contract's
    ``CAPABILITY_UNSUPPORTED`` error code.
    """
