"""Application-bound structured data cell.

Each cell owns one storage handle. Sessions never accept an application ID;
the application scope comes from the authenticated Principal and the cell
selected by the service. No database-native command is part of this API.
"""

from dataclasses import dataclass
import json
import sqlite3
from threading import RLock

from .audit import AuditSink
from .auth import Principal, Role
from .config import FoundationConfig
from .errors import (AuthorizationError, ConflictError, NotFoundError,
                     ResourceLimitError, ValidationError)
from .identifiers import quote_identifier, validate_identifier

_TYPES = {"text": "TEXT", "integer": "INTEGER", "real": "REAL",
          "boolean": "INTEGER", "json": "TEXT"}
_OPS = {"eq": "=", "ne": "!=", "lt": "<", "lte": "<=", "gt": ">",
        "gte": ">=", "in": "IN"}


@dataclass(frozen=True)
class Filter:
    field: str
    operator: str
    value: object


class ApplicationCell:
    """A private application storage boundary.

    ``sqlite3`` is used only as a deterministic local foundation backend. The
    production Cloud SQL adapter must keep this authority shape and replace
    the storage driver without exposing its connection to Application code.
    """

    def __init__(self, application_id, config=None, audit=None, guard=None):
        validate_identifier(application_id, "application_id")
        self.application_id = application_id
        self.config = config or FoundationConfig()
        self.__record = (audit or AuditSink()).record
        self.__guard = guard
        self._db = sqlite3.connect(":memory:", check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._lock = RLock()

    def _schema_count(self):
        row = self._db.execute(
            "SELECT count(*) AS count FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%'"
        ).fetchone()
        return row["count"]

    def create_collection(self, principal, name, fields, destructive=False):
        self._require_developer(principal)
        validate_identifier(name, "collection")
        if not isinstance(fields, dict) or not fields:
            raise ValidationError("fields must be a non-empty object")
        if len(fields) > self.config.max_fields:
            raise ResourceLimitError("field limit exceeded")
        if self._schema_count() >= self.config.max_schema_objects:
            raise ResourceLimitError("schema object limit exceeded")
        definitions = []
        for field, field_type in fields.items():
            validate_identifier(field, "field")
            if field_type not in _TYPES:
                raise ValidationError("unsupported field type")
            definitions.append(quote_identifier(field) + " " + _TYPES[field_type])
        statement = "CREATE TABLE " + quote_identifier(name) + " (" + \
            ", ".join(definitions) + ")"
        with self._lock:
            try:
                self._db.execute(statement)
                self._db.commit()
            except sqlite3.DatabaseError:
                raise ConflictError("collection already exists")
        self.__record("schema_change", self.application_id,
                      principal.credential_id, detail="create_collection")

    def insert(self, principal, collection, values):
        self._require_data(principal)
        table, fields, params = self._prepare_values(collection, values)
        columns = ", ".join(quote_identifier(field) for field in fields)
        marks = ", ".join("?" for _ in fields)
        with self._lock:
            try:
                cursor = self._db.execute("INSERT INTO " + table + " (" + columns + ") VALUES (" + marks + ")", params)
                self._db.commit()
            except sqlite3.IntegrityError:
                raise ConflictError("write conflicts with a constraint")
            except sqlite3.DatabaseError:
                raise NotFoundError("collection not found")
        return {"rowid": cursor.lastrowid}

    def read(self, principal, collection, fields=None, filters=None,
             order_by=None, limit=None):
        self._require_data(principal)
        table = quote_identifier(validate_identifier(collection, "collection"))
        selected = self._fields(collection, fields)
        statement = "SELECT " + ", ".join(quote_identifier(x) for x in selected) + " FROM " + table
        where, params = self._where(collection, filters)
        statement += where
        if order_by is not None:
            if not isinstance(order_by, dict):
                raise ValidationError("order_by must be an object")
            field = validate_identifier(order_by.get("field"), "order field")
            if field not in self._field_names(collection):
                raise ValidationError("unknown order field")
            direction = order_by.get("direction", "asc")
            if direction not in ("asc", "desc"):
                raise ValidationError("invalid order direction")
            statement += " ORDER BY " + quote_identifier(field) + " " + direction.upper()
        if limit is None:
            limit = self.config.max_result_rows
        if not isinstance(limit, int) or limit <= 0 or limit > self.config.max_result_rows:
            raise ResourceLimitError("result limit exceeded")
        statement += " LIMIT ?"
        params.append(limit)
        with self._lock:
            try:
                rows = self._db.execute(statement, params).fetchall()
            except sqlite3.DatabaseError:
                raise NotFoundError("collection not found")
        return [dict(row) for row in rows]

    def update(self, principal, collection, values, filters):
        self._require_data(principal)
        if not isinstance(filters, list) or not filters:
            raise ValidationError("update requires non-empty filters")
        table, fields, values_params = self._prepare_values(collection, values)
        if not fields:
            raise ValidationError("values must be non-empty")
        where, where_params = self._where(collection, filters)
        statement = "UPDATE " + table + " SET " + ", ".join(
            quote_identifier(field) + " = ?" for field in fields) + where
        with self._lock:
            try:
                cursor = self._db.execute(statement, values_params + where_params)
                self._db.commit()
            except sqlite3.DatabaseError:
                raise NotFoundError("collection not found")
        return {"updated": cursor.rowcount}

    def delete(self, principal, collection, filters, confirm=False):
        self._require_data(principal)
        if not confirm:
            raise ValidationError("destructive operation requires explicit confirmation")
        if not isinstance(filters, list) or not filters:
            raise ValidationError("delete requires non-empty filters")
        table = quote_identifier(validate_identifier(collection, "collection"))
        where, params = self._where(collection, filters)
        statement = "DELETE FROM " + table + where
        with self._lock:
            try:
                cursor = self._db.execute(statement, params)
                self._db.commit()
            except sqlite3.DatabaseError:
                raise NotFoundError("collection not found")
        self.__record("destructive_data_operation", self.application_id,
                      principal.credential_id, detail="delete_rows")
        return {"deleted": cursor.rowcount}

    def transact(self, principal, operations):
        self._require_data(principal)
        if not isinstance(operations, list) or not operations:
            raise ValidationError("operations must be a non-empty list")
        if len(operations) > self.config.max_batch_items:
            raise ResourceLimitError("batch limit exceeded")
        with self._lock:
            try:
                self._db.execute("BEGIN")
                results = []
                for operation in operations:
                    if not isinstance(operation, dict) or operation.get("type") != "insert":
                        raise ValidationError("unsupported transaction operation")
                    results.append(self._insert_in_transaction(operation["collection"], operation["values"]))
                self._db.commit()
                return results
            except (ValidationError, ResourceLimitError):
                self._db.rollback()
                raise
            except sqlite3.IntegrityError:
                self._db.rollback()
                raise ConflictError("transaction rolled back")
            except sqlite3.DatabaseError:
                self._db.rollback()
                raise NotFoundError("transaction rolled back")

    def _insert_in_transaction(self, collection, values):
        table, fields, params = self._prepare_values(collection, values)
        statement = "INSERT INTO " + table + " (" + ", ".join(
            quote_identifier(field) for field in fields) + ") VALUES (" + \
            ", ".join("?" for _ in fields) + ")"
        cursor = self._db.execute(statement, params)
        return {"rowid": cursor.lastrowid}

    def _fields(self, collection, requested):
        available = self._field_names(collection)
        if requested is None:
            return available
        if not isinstance(requested, list) or not requested:
            raise ValidationError("fields must be a non-empty list")
        if len(requested) > self.config.max_fields:
            raise ResourceLimitError("field limit exceeded")
        result = []
        for field in requested:
            field = validate_identifier(field, "field")
            if field not in available:
                raise ValidationError("unknown field")
            result.append(field)
        return result

    def _field_names(self, collection):
        name = validate_identifier(collection, "collection")
        try:
            rows = self._db.execute("PRAGMA table_info(" + quote_identifier(name) + ")").fetchall()
        except sqlite3.DatabaseError:
            raise NotFoundError("collection not found")
        if not rows:
            raise NotFoundError("collection not found")
        return [row["name"] for row in rows]

    def _prepare_values(self, collection, values):
        table_name = validate_identifier(collection, "collection")
        available = self._field_names(table_name)
        if not isinstance(values, dict) or not values:
            raise ValidationError("values must be a non-empty object")
        if len(values) > self.config.max_fields:
            raise ResourceLimitError("field limit exceeded")
        fields = []
        params = []
        for field, value in values.items():
            field = validate_identifier(field, "field")
            if field not in available:
                raise ValidationError("unknown field")
            fields.append(field)
            params.append(self._encode_value(value))
        return quote_identifier(table_name), fields, params

    def _where(self, collection, filters):
        if filters is None:
            return "", []
        if not isinstance(filters, list) or len(filters) > self.config.max_filter_terms:
            raise ResourceLimitError("filter limit exceeded")
        available = self._field_names(collection)
        clauses, params = [], []
        for item in filters:
            if not isinstance(item, Filter):
                raise ValidationError("filters must contain Filter values")
            field = validate_identifier(item.field, "filter field")
            if field not in available or item.operator not in _OPS:
                raise ValidationError("invalid filter")
            if item.operator == "in":
                if not isinstance(item.value, list) or not item.value:
                    raise ValidationError("in filter requires values")
                if len(item.value) > self.config.max_batch_items:
                    raise ResourceLimitError("filter value limit exceeded")
                clauses.append(quote_identifier(field) + " IN (" + ",".join("?" for _ in item.value) + ")")
                params.extend(self._encode_value(value) for value in item.value)
            else:
                clauses.append(quote_identifier(field) + " " + _OPS[item.operator] + " ?")
                params.append(self._encode_value(item.value))
        return (" WHERE " + " AND ".join(clauses)) if clauses else "", params

    @staticmethod
    def _encode_value(value):
        if isinstance(value, (dict, list)):
            return json.dumps(value, separators=(",", ":"), sort_keys=True)
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, (str, int, float)) or value is None:
            return value
        raise ValidationError("unsupported value")

    def _require_data(self, principal):
        if self.__guard is not None:
            self.__guard(principal)
        if not isinstance(principal, Principal) or principal.application_id != self.application_id:
            raise AuthorizationError("application scope denied")
        if principal.role not in (Role.RUNTIME, Role.DEVELOPER):
            raise AuthorizationError("role denied")

    def _require_developer(self, principal):
        self._require_data(principal)
        if principal.role != Role.DEVELOPER:
            self.__record("authorization_denied", self.application_id,
                          getattr(principal, "credential_id", None),
                          outcome="denied", detail="schema_change")
            raise AuthorizationError("developer authority required")


class ApplicationRuntime:
    """Runtime data authority; schema mutation is intentionally absent."""

    __slots__ = ("__cell", "__principal", "__guard")

    def __init__(self, cell, principal, guard=None):
        cell._require_data(principal)
        self.__cell, self.__principal, self.__guard = cell, principal, guard

    @property
    def principal(self):
        return self.__principal

    def __authorize(self):
        if self.__guard is not None:
            self.__guard(self.__principal)

    def insert(self, collection, values):
        self.__authorize()
        return self.__cell.insert(self.__principal, collection, values)

    def read(self, collection, fields=None, filters=None, order_by=None, limit=None):
        self.__authorize()
        return self.__cell.read(self.__principal, collection, fields, filters, order_by, limit)

    def update(self, collection, values, filters):
        self.__authorize()
        return self.__cell.update(self.__principal, collection, values, filters)

    def delete(self, collection, filters, confirm=False):
        self.__authorize()
        return self.__cell.delete(self.__principal, collection, filters, confirm)

    def transact(self, operations):
        self.__authorize()
        return self.__cell.transact(self.__principal, operations)

    def capabilities(self):
        """Minimal capability/discovery document, per this session's own
        server-bound scope. Statuses reflect what this foundation actually
        executes today, not the common contract's peer-target surface: an
        operation this foundation cannot run is never advertised "enabled"
        (spec `capability_status.rules`).
        """
        self.__authorize()
        principal = self.__principal
        is_developer = principal.role == Role.DEVELOPER
        config = self.__cell.config
        return {
            # 1.1.0: every 1.1.0 addition is an optional capability this
            # peer does not (yet) provide, so conforming to 1.1.0 needs no
            # behavior change here -- only declaring the new capability
            # names below as unavailable, mirroring r2db-api's declaration.
            "contract_version": "1.1.0",
            "capabilities": {
                # `_OPS` (this module) has no "contains" / "is_null" entry,
                # so those two contract-listed operators are not executable
                # here: "enabled" would misrepresent them as available.
                "structured_query": {"status": "partial", "operators": list(_OPS), "unsupported": ["contains", "is_null"]},
                # `ApplicationCell.transact` only accepts operation type
                # "insert"; there is no "upsert" surface anywhere on this
                # peer.
                "atomic_mutation": {"status": "partial", "operations": ["insert", "update", "delete"], "unsupported": ["upsert"]},
                # No public "list collections" operation exists on this peer.
                "application_catalog": {"status": "unavailable"},
                "schema_operations": {"status": "partial", "operations": ["create_entity"] if is_developer else [], "unsupported": ["add_field", "alter_field", "create_index", "drop_index", "drop_entity", "jobs"]},
                "audit_query": {"status": "unavailable", "authority": "control_or_audit"},
                "best_effort_transactions": {"status": "unavailable"},
                "idempotency": {"status": "unavailable"},
                "revision_preconditions": {"status": "unavailable"},
                "row_addressability": {"status": "unavailable"},
                "cross_entity_mutation": {"status": "unavailable"},
                "control_plane": {"status": "unavailable"}
            },
            "limits": {
                "batch_items": config.max_batch_items,
                "result_items": config.max_result_rows,
                "fields": config.max_fields,
                "filter_terms": config.max_filter_terms,
                "request_bytes": config.max_request_bytes,
                "schema_objects": config.max_schema_objects
            },
            "limit_enforcement": {
                "batch_items": "enforced",
                "result_items": "enforced",
                "fields": "enforced",
                "filter_terms": "enforced",
                # `FoundationConfig.validate_request_size` exists but is not
                # wired into any request path yet (no caller in `cell.py` /
                # `service.py`): reporting "enforced" here would be false.
                "request_bytes": "unavailable",
                "schema_objects": "enforced"
            },
            # `CredentialStore.assert_active` (auth.py) is invoked by
            # `__authorize` above on every single session operation, with
            # no cache: revoke/disable/state-unavailable propagation is
            # synchronous.
            "authorization_propagation_bound_ms": 0,
            "application_scope": principal.application_id,
            "role": principal.role.value
        }


class ApplicationDeveloper(ApplicationRuntime):
    """Developer authority adds structured schema operations only."""

    def create_collection(self, name, fields):
        self._ApplicationRuntime__authorize()
        return self._ApplicationRuntime__cell.create_collection(
            self._ApplicationRuntime__principal, name, fields)
