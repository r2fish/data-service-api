# r2db-api

VPS / PostgreSQL implementation of the common `data-service-api` contract.

## Current source

The current implemented source remains under:

`project/r2-vps/apps/r2db-api`

It is not moved automatically by the repository-layout change. Migration into this directory must preserve the working VPS implementation and be performed as an explicit development task.

## Contract rule

Public behavior should conform to `../spec/` and `../conformance-tests/`. VPS-specific nginx, systemd, filesystem paths, local PostgreSQL provisioning, and operational details remain implementation-local.
