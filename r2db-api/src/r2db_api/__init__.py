"""Reference foundation for the common Data Service API contract."""

from .auth import AuthContext, CredentialRecord, CredentialStore
from .errors import FoundationError
from .service import ControlAuthority, DataService

# `PostgresCredentialStore` (`r2db_api.credential_store`) is deliberately
# not re-exported here, mirroring `r2db_api.postgres.PostgresCell`'s own
# precedent: this top-level package stays importable without `psycopg`
# installed at all (a pure in-memory consumer of `CredentialStore`/
# `DataService`/`ApplicationCell` has no PostgreSQL dependency). Anything
# that needs the PostgreSQL-backed store imports it explicitly from
# `r2db_api.credential_store`, exactly as PostgreSQL-backed callers already
# import `PostgresCell` from `r2db_api.postgres` rather than from here.
__all__ = ["AuthContext", "ControlAuthority", "CredentialRecord", "CredentialStore", "DataService", "FoundationError"]
