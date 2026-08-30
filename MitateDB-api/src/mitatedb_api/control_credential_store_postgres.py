"""Postgres-backed twin of `control_auth.ControlCredentialStore` (design v1.2
R-4, WP-4) -- same call surface, backed by `mitatedb_registry.
control_credentials` (migration `0002_registry_and_functions.sql`) instead
of an in-memory dict.

Independently written (R-2's closing paragraph: no code sharing between
peers, and -- within this one peer -- no code sharing between this class
and `credential_store_postgres.PostgresCredentialStore` either): that
class's own row shape (`application_id`/`role`/`expires_at`) has no
analogue here; this table has no `application_id` at all and adds
`must_rotate` instead, so this is a genuinely different SQL surface, not a
parameterized reuse of the other file.

Every write method accepts an optional externally-supplied `work` -- a
`psycopg.Connection` already inside an open transaction the caller
(`control_plane.PostgresControlBackend`) owns. When `work` is given, this
store's own methods execute their statement on it and never call `conn.
commit()`/`conn.rollback()` themselves (the caller's transaction boundary
decides that, which is what lets a `control_audit` INSERT on the SAME
connection share the transaction -- R-6's same-transaction requirement).
When `work` is omitted (the default), each method opens, uses, and
commits/rolls back its own short-lived connection -- the same fail-closed,
no-pooling convention `credential_store_postgres.py` established,
preserved here so this store is independently usable (and independently
parity-tested against `control_auth.ControlCredentialStore`) without any
`ControlPlaneService` involved at all.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from typing import Optional

import psycopg
from psycopg import sql

from .control_auth import ControlPrincipal
from .errors import AuthenticationError, AuthorizationStateUnavailable, NotFoundError, StorageConfigurationError
from .identifiers import validate_identifier

DEFAULT_SCHEMA = "mitatedb_registry"
_CONTROL_CREDENTIAL_PEPPER_ENV = "MITATEDB_CONTROL_CREDENTIAL_PEPPER"

# See `control_auth._DUMMY_DIGEST`'s own docstring -- identical rationale,
# deliberately duplicated (not shared) for this store's own timing parity.
_DUMMY_DIGEST = hashlib.sha256(b"mitatedb-control-credential-store-timing-parity-dummy").digest()


def _execute(cursor, statement, params=()):
    """R-2 choke point (mirrors `backend_postgres.py`/`credential_store_
    postgres.py`'s identical role). The ONLY call to `cursor.execute` in
    this module."""
    if not isinstance(statement, (sql.SQL, sql.Composed)):
        raise TypeError(
            "control_credential_store_postgres.py only executes psycopg.sql.Composed/SQL "
            "objects, never str"
        )
    cursor.execute(statement, params)
    return cursor


class PostgresControlCredentialStore:
    def __init__(self, dsn: str, *, pepper: Optional[str] = None, schema: str = DEFAULT_SCHEMA,
                 connect_timeout: int = 5) -> None:
        pepper = pepper if pepper is not None else os.environ.get(_CONTROL_CREDENTIAL_PEPPER_ENV)
        if not isinstance(pepper, str) or len(pepper) < 16:
            raise ValueError(f"{_CONTROL_CREDENTIAL_PEPPER_ENV} must be supplied externally (>=16 characters)")
        self._pepper = pepper.encode("utf-8")
        validate_identifier(schema, "schema")
        self._dsn = dsn
        self._connect_timeout = connect_timeout
        self._table = sql.Identifier(schema, "control_credentials")

    def _digest(self, secret) -> bytes:
        if not isinstance(secret, str):
            secret = ""
        return hmac.new(self._pepper, secret.encode("utf-8"), hashlib.sha256).digest()

    def _connect(self) -> "psycopg.Connection":
        try:
            return psycopg.connect(self._dsn, connect_timeout=self._connect_timeout, autocommit=False)
        except psycopg.Error as exc:
            raise AuthorizationStateUnavailable("authorization state unavailable") from exc

    def _own_connection(self, work):
        """Returns `(conn, owns_it)` -- `owns_it=True` means this call
        opened `conn` itself and must commit/close it; `False` means `work`
        (an externally-managed connection) was supplied and this call must
        neither commit nor close it."""
        if work is not None:
            return work, False
        return self._connect(), True

    # ---- writes ---------------------------------------------------------

    def issue(self, *, must_rotate: bool = False, credential_id: Optional[str] = None,
              secret: Optional[str] = None, work=None) -> tuple[str, str]:
        credential_id = credential_id or ("ctl_" + secrets.token_hex(12))
        secret = secret or secrets.token_urlsafe(32)
        digest = self._digest(secret)
        conn, owns = self._own_connection(work)
        statement = sql.SQL(
            "INSERT INTO {table} (credential_id, digest, must_rotate) VALUES ({ph1}, {ph2}, {ph3})"
        ).format(table=self._table, ph1=sql.Placeholder(), ph2=sql.Placeholder(), ph3=sql.Placeholder())
        try:
            with conn.cursor() as cur:
                _execute(cur, statement, [credential_id, digest, must_rotate])
            if owns:
                conn.commit()
        except psycopg.errors.InsufficientPrivilege as exc:
            if owns:
                conn.rollback()
            raise StorageConfigurationError(
                "the storage backend refused this write due to a privilege/configuration defect"
            ) from exc
        except psycopg.Error as exc:
            if owns:
                conn.rollback()
            raise AuthorizationStateUnavailable("authorization state unavailable") from exc
        finally:
            if owns:
                conn.close()
        return credential_id, secret

    def _update_flag(self, credential_id: str, column: str, value, *, work) -> None:
        conn, owns = self._own_connection(work)
        statement = sql.SQL("UPDATE {table} SET {column} = {ph} WHERE credential_id = {id_ph} RETURNING credential_id").format(
            table=self._table, column=sql.Identifier(column), ph=sql.Placeholder(), id_ph=sql.Placeholder())
        try:
            with conn.cursor() as cur:
                _execute(cur, statement, [value, credential_id])
                row = cur.fetchone()
                if row is None:
                    raise NotFoundError("control credential not found")
            if owns:
                conn.commit()
        except NotFoundError:
            if owns:
                conn.rollback()
            raise
        except psycopg.errors.InsufficientPrivilege as exc:
            if owns:
                conn.rollback()
            raise StorageConfigurationError(
                "the storage backend refused this write due to a privilege/configuration defect"
            ) from exc
        except psycopg.Error as exc:
            if owns:
                conn.rollback()
            raise AuthorizationStateUnavailable("authorization state unavailable") from exc
        finally:
            if owns:
                conn.close()

    def revoke(self, credential_id: str, *, work=None) -> None:
        self._update_flag(credential_id, "revoked", True, work=work)

    def disable(self, credential_id: str, *, work=None) -> None:
        self._update_flag(credential_id, "enabled", False, work=work)

    def enable(self, credential_id: str, *, work=None) -> None:
        """See `control_auth.ControlCredentialStore.enable`'s identical
        reasoning -- no statement anywhere in this module both reads and
        writes `revoked`, so this can never resurrect a revoked row."""
        self._update_flag(credential_id, "enabled", True, work=work)

    def revoke_all(self, *, work=None) -> None:
        conn, owns = self._own_connection(work)
        statement = sql.SQL("UPDATE {table} SET revoked = TRUE").format(table=self._table)
        try:
            with conn.cursor() as cur:
                _execute(cur, statement)
            if owns:
                conn.commit()
        except psycopg.errors.InsufficientPrivilege as exc:
            if owns:
                conn.rollback()
            raise StorageConfigurationError(
                "the storage backend refused this write due to a privilege/configuration defect"
            ) from exc
        except psycopg.Error as exc:
            if owns:
                conn.rollback()
            raise AuthorizationStateUnavailable("authorization state unavailable") from exc
        finally:
            if owns:
                conn.close()

    def rotate(self, credential_id: str, *, secret: Optional[str] = None,
               clear_must_rotate: bool = True, work=None) -> str:
        secret = secret or secrets.token_urlsafe(32)
        digest = self._digest(secret)
        conn, owns = self._own_connection(work)
        if clear_must_rotate:
            statement = sql.SQL(
                "UPDATE {table} SET digest = {digest_ph}, must_rotate = FALSE "
                "WHERE credential_id = {id_ph} RETURNING credential_id"
            ).format(table=self._table, digest_ph=sql.Placeholder(), id_ph=sql.Placeholder())
        else:
            statement = sql.SQL(
                "UPDATE {table} SET digest = {digest_ph} WHERE credential_id = {id_ph} RETURNING credential_id"
            ).format(table=self._table, digest_ph=sql.Placeholder(), id_ph=sql.Placeholder())
        try:
            with conn.cursor() as cur:
                _execute(cur, statement, [digest, credential_id])
                row = cur.fetchone()
                if row is None:
                    raise NotFoundError("control credential not found")
            if owns:
                conn.commit()
        except NotFoundError:
            if owns:
                conn.rollback()
            raise
        except psycopg.errors.InsufficientPrivilege as exc:
            if owns:
                conn.rollback()
            raise StorageConfigurationError(
                "the storage backend refused this write due to a privilege/configuration defect"
            ) from exc
        except psycopg.Error as exc:
            if owns:
                conn.rollback()
            raise AuthorizationStateUnavailable("authorization state unavailable") from exc
        finally:
            if owns:
                conn.close()
        return secret

    # ---- reads ------------------------------------------------------------

    def get_state(self, credential_id: str) -> Optional[tuple[bool, bool, bool]]:
        conn = self._connect()
        try:
            statement = sql.SQL("SELECT enabled, revoked, must_rotate FROM {table} WHERE credential_id = {ph}").format(
                table=self._table, ph=sql.Placeholder())
            try:
                with conn.cursor() as cur:
                    _execute(cur, statement, [credential_id])
                    row = cur.fetchone()
            except psycopg.errors.InsufficientPrivilege as exc:
                raise StorageConfigurationError(
                    "the storage backend refused this read due to a privilege/configuration defect"
                ) from exc
            except psycopg.Error as exc:
                raise AuthorizationStateUnavailable("authorization state unavailable") from exc
        finally:
            conn.close()
        return (row[0], row[1], row[2]) if row is not None else None

    def list_all(self) -> list[tuple[str, bool, bool]]:
        conn = self._connect()
        try:
            statement = sql.SQL("SELECT credential_id, enabled, revoked FROM {table} ORDER BY issued_at").format(table=self._table)
            try:
                with conn.cursor() as cur:
                    _execute(cur, statement)
                    rows = cur.fetchall()
            except psycopg.errors.InsufficientPrivilege as exc:
                raise StorageConfigurationError(
                    "the storage backend refused this read due to a privilege/configuration defect"
                ) from exc
            except psycopg.Error as exc:
                raise AuthorizationStateUnavailable("authorization state unavailable") from exc
        finally:
            conn.close()
        return [(row[0], row[1], row[2]) for row in rows]

    def locked_for_update(self, work) -> list[tuple[str, bool, bool]]:
        """`SELECT ... FOR UPDATE` on `work` (a connection already inside
        an open transaction) -- the real PostgreSQL analogue of `control_
        auth.ControlCredentialStore.locked_for_update`'s in-memory lock,
        used by `control_plane.py`'s revoke-last-active-control-credential
        gate to make "is this the last active one" TOCTOU-safe."""
        if work is None:
            raise ValueError("locked_for_update requires an open transaction (work=...)")
        statement = sql.SQL("SELECT credential_id, enabled, revoked FROM {table} ORDER BY issued_at FOR UPDATE").format(table=self._table)
        try:
            with work.cursor() as cur:
                _execute(cur, statement)
                rows = cur.fetchall()
        except psycopg.errors.InsufficientPrivilege as exc:
            raise StorageConfigurationError(
                "the storage backend refused this read due to a privilege/configuration defect"
            ) from exc
        except psycopg.Error as exc:
            raise AuthorizationStateUnavailable("authorization state unavailable") from exc
        return [(row[0], row[1], row[2]) for row in rows]

    def has_any(self, *, include_revoked: bool = True, work=None) -> bool:
        conn, owns = self._own_connection(work)
        try:
            where = sql.SQL("") if include_revoked else sql.SQL(" WHERE NOT revoked")
            statement = sql.SQL("SELECT EXISTS(SELECT 1 FROM {table}{where})").format(table=self._table, where=where)
            try:
                with conn.cursor() as cur:
                    _execute(cur, statement)
                    row = cur.fetchone()
            except psycopg.errors.InsufficientPrivilege as exc:
                raise StorageConfigurationError(
                    "the storage backend refused this read due to a privilege/configuration defect"
                ) from exc
            except psycopg.Error as exc:
                raise AuthorizationStateUnavailable("authorization state unavailable") from exc
        finally:
            if owns:
                conn.close()
        return bool(row[0])

    def authenticate(self, credential_id, secret) -> ControlPrincipal:
        if not isinstance(credential_id, str) or not credential_id:
            raise AuthenticationError("control authentication failed")
        conn = self._connect()
        try:
            statement = sql.SQL("SELECT digest, enabled, revoked, must_rotate FROM {table} WHERE credential_id = {ph}").format(
                table=self._table, ph=sql.Placeholder())
            try:
                with conn.cursor() as cur:
                    _execute(cur, statement, [credential_id])
                    row = cur.fetchone()
            except psycopg.errors.InsufficientPrivilege as exc:
                raise StorageConfigurationError(
                    "the storage backend refused this read due to a privilege/configuration defect"
                ) from exc
            except psycopg.Error as exc:
                raise AuthorizationStateUnavailable("authorization state unavailable") from exc
        finally:
            conn.close()
        stored_digest = bytes(row[0]) if row is not None else _DUMMY_DIGEST
        digest_matches = hmac.compare_digest(stored_digest, self._digest(secret))
        if row is None or not digest_matches:
            raise AuthenticationError("control authentication failed")
        _digest, enabled, revoked, must_rotate = row
        if not enabled or revoked:
            raise AuthenticationError("control authentication failed")
        return ControlPrincipal(credential_id, must_rotate)


__all__ = ["PostgresControlCredentialStore", "DEFAULT_SCHEMA"]
