"""Reference foundation for the common Data Service API contract."""

from .auth import AuthContext, CredentialRecord, CredentialStore
from .errors import FoundationError
from .service import ControlAuthority, DataService

__all__ = ["AuthContext", "ControlAuthority", "CredentialRecord", "CredentialStore", "DataService", "FoundationError"]
