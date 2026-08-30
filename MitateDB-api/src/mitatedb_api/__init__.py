"""MitateDB-api foundation.

The package intentionally exposes a structured, application-bound data plane
without exposing a database connection or database-native command interface.
The public HTTP contract remains owned by ``data-service-api/spec``.
"""

from .auth import CredentialStore, Principal, Role
from .backend_sqlite import SQLiteBackend
from .cell import ApplicationCell, ApplicationDeveloper, ApplicationRuntime, Filter
from .config import FoundationConfig
from .service import ControlPlane, MitateDataService, ProvisioningFacade

# m-5 (independent review): `backend_postgres` imports `psycopg`
# unconditionally at module level. Importing it EAGERLY here would make
# `psycopg` a hard requirement just to `import mitatedb_api` at all --
# even for a pure-SQLite, in-process composition (the local foundation's
# own default, `architecture/DATA_SERVICE_FOUNDATION.md`) and the
# in-process conformance adapter, neither of which ever touches
# PostgreSQL. Deferred so an environment with no `psycopg` installed can
# still `import mitatedb_api` and use everything except `PostgresBackend`
# itself; `PostgresBackend` is `None` in that case (importing it directly,
# `from mitatedb_api.backend_postgres import PostgresBackend`, still
# raises the real `ImportError` for a caller who actually needs it and
# does not have `psycopg` -- this only softens the PACKAGE-level import).
try:
    from .backend_postgres import PostgresBackend
except ImportError:  # pragma: no cover - environment-dependent (no psycopg)
    PostgresBackend = None

__all__ = [
    "ApplicationCell",
    "ApplicationDeveloper",
    "ApplicationRuntime",
    # `ControlPlane` is a backward-compatible alias of `ProvisioningFacade`
    # (WP-1 R-3/WP-0 m-8 rename, `service.py`); both are exported.
    "ControlPlane",
    "CredentialStore",
    "Filter",
    "FoundationConfig",
    "MitateDataService",
    "PostgresBackend",
    "Principal",
    "ProvisioningFacade",
    "Role",
    "SQLiteBackend",
]
