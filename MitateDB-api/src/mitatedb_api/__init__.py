"""MitateDB-api foundation.

The package intentionally exposes a structured, application-bound data plane
without exposing a database connection or database-native command interface.
The public HTTP contract remains owned by ``data-service-api/spec``.
"""

from .auth import CredentialStore, Principal, Role
from .cell import ApplicationCell, ApplicationDeveloper, ApplicationRuntime, Filter
from .config import FoundationConfig
from .service import ControlPlane, MitateDataService

__all__ = [
    "ApplicationCell",
    "ApplicationDeveloper",
    "ApplicationRuntime",
    "ControlPlane",
    "CredentialStore",
    "Filter",
    "FoundationConfig",
    "MitateDataService",
    "Principal",
    "Role",
]
