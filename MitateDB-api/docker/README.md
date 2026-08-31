# Data Service container/deployment assets

This folder is reserved only for Data Service-specific container/deployment support files when such files cannot live cleanly at the `data-service/` root.

It is not an additional application layer and must not contain business logic, database credentials, or Agent/Application code.

If implementation does not require a dedicated folder, this folder should be removed rather than used as a generic dumping area.

`authority-topology.yaml` is the non-secret runtime-boundary skeleton for the
Cloud Run/Cloud SQL adapter. It records intended workload separation
and deny rules, but is not platform evidence until deployed IAM, network and
secret-manager controls are configured and independently verified.

`Dockerfile` (WP-6, design v1.2 R-9) builds the one image both Cloud Run
services run: a multi-stage, non-root build with no secret baked in --
every credential/DSN/pepper is supplied at container-start time via
environment variables. `SERVICE=data`/`SERVICE=control` selects which of
`mitatedb_api.main:app`/`mitatedb_api.control_main:app` this container
serves; deployment procedure, the environment-variable contract, and the
runbook-level invariants live in `../docs/cloud-run-cloud-sql.md`, not
here.
