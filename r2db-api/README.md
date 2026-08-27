# r2db-api

VPS / PostgreSQL implementation of the common `data-service-api` contract.

## Current source

The previously deployed implementation is retained separately as the
旧r2db-api実装 and is not modified by this repository work.

Migration of the previous implementation is intentionally not implicit;
production cutover remains an explicit development task.

## Contract rule

Public behavior should conform to `../spec/` and `../conformance-tests/`. VPS-specific nginx, systemd, filesystem paths, local PostgreSQL provisioning, and operational details remain implementation-local.

## Foundation

This directory contains the common-contract reference foundation, not a
production deployment. `src/r2db_api` models server-bound credentials,
application-scoped structured operations, finite limits, canonical audit
events, and the authority topology. `config/authority-topology.yaml` is a
deployment skeleton: production evidence for identity, network, database
grants, and an external append-only audit sink remains required.
The failure policy for an unavailable production audit sink is not claimed by
this foundation.

Application-facing code intentionally has no SQL/native-command execution
surface and no access to Control or Provisioning authorities.

Long-running schema evolution jobs are not implemented by this synchronous
foundation. A future job capability must define finite execution/queue bounds,
observable state transitions, cancellation, expiry, and rollback semantics
before it is advertised.
