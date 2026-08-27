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
