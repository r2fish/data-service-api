# MitateDB-api container image (design v1.2 R-9, WP-6).
#
# One image, two entrypoints: the application-plane process
# (`mitatedb_api.main:app`, `/v1/*`) and the control-plane process
# (`mitatedb_api.control_main:app`, `/control/v1/*`) are built from the
# SAME image and selected at `docker run`/Cloud Run deploy time via the
# `SERVICE` build/run argument below -- R-6/R-9's own "同一イメージ・別
# entrypoint" default (mirrors `mitatedb_api.main`/`mitatedb_api.
# control_main` already being two separate Python modules with two
# separate `app` objects for exactly this reason: importing one must never
# require the other process' own required environment, see both modules'
# own docstrings).
#
# Independent of r2db-api's own deployment (VPS/systemd/nginx,
# `r2db-api/deploy/DEPLOYMENT_RUNBOOK.md`) -- read only as a reference for
# the SHAPE of the problem ("how does an operator run this thing"), not
# copied: r2db-api ships no Dockerfile at all (it deploys as a systemd
# unit against a long-lived VPS PostgreSQL), while this design's own R-9
# targets Cloud Run/Cloud SQL specifically, which needs a container image.
#
# No secret is ever baked into this image: every credential/DSN/pepper is
# supplied at container-start time via environment variables (Secret
# Manager references at the Cloud Run layer, `cloud-run-cloud-sql.md`).
#
# BUILD CONTEXT (2026-09-01 fix; reason updated Phase 6 WP-0 supervisor
# ruling, contract now ships as packaged data -- see the CONTRACT
# PACKAGING note below the builder stage): every `COPY` source in this
# file (`COPY MitateDB-api/pyproject.toml ./`, `COPY MitateDB-api/src
# ./src`, `COPY constraints.txt ./`) is written REPOSITORY-ROOT-relative,
# not `MitateDB-api/`-relative -- a build context scoped to `MitateDB-api/`
# alone would make all three of those `COPY` sources resolve to
# nonexistent paths (there is no `MitateDB-api/MitateDB-api/pyproject.
# toml`, nor a `MitateDB-api/constraints.txt`). Build this image from the
# REPOSITORY ROOT, naming this file explicitly, e.g.:
#   docker build -f MitateDB-api/docker/Dockerfile -t mitatedb-api:SERVICE_data .
# -- see `cloud-run-cloud-sql.md` §6's own build step for the full command
# this runbook now documents.

# ---------------------------------------------------------------------------
# Stage 1: build a wheel + resolve dependencies into an isolated venv, so
# the final stage never needs a C toolchain or pip's own build machinery
# (psycopg[binary] ships a prebuilt libpq, so no PostgreSQL client headers
# are needed even here -- this stage exists to keep the runtime stage's
# installed-package surface minimal, not to compile anything).
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS builder

WORKDIR /build

# Only the packaging manifest and this package's own source are needed to
# resolve/install dependencies + the package itself -- `migrations/` is
# deliberately NOT copied into the image (see this file's own footer note):
# provisioning SQL is operator/deploy-tooling material, run against
# Cloud SQL directly, never executed by a running application-plane/
# control-plane container. Paths are repo-root-relative (see the BUILD
# CONTEXT note above this stage).
COPY MitateDB-api/pyproject.toml ./
COPY MitateDB-api/src ./src
# `constraints.txt` is repository-root-relative like the two `COPY`s above
# (see the BUILD CONTEXT note above this stage) -- it is the same file
# CI's own `pip install -c constraints.txt ...` step resolves against
# (R-19, `tools/check_image_pins.py`).
COPY constraints.txt ./

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
# `pip install -c constraints.txt .` resolves `starlette`/`psycopg[binary]`/
# `uvicorn` from `pyproject.toml`'s own `[project.dependencies]` (WP-1),
# constrained to the exact versions pinned in `constraints.txt` -- the same
# exact-pin file CI's completion gate installs against, so this image's
# dependency resolution cannot silently drift from CI's. CI job
# `image-pins` (`.github/workflows/ci.yml`) runs `pip freeze` inside a
# built image and diffs it against `constraints.txt` with
# `tools/check_image_pins.py` to keep this true. The prior comment here
# asserted "no version drift" without anything actually checking that
# claim -- that assertion was unverified until this job existed.
RUN pip install --no-cache-dir -c constraints.txt .

# ---------------------------------------------------------------------------
# Stage 2: runtime -- the venv built above, copied onto a slim base, run as
# a non-root user.
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS runtime

# Non-root (R-9's own "非 root" instruction): a dedicated, unprivileged
# system user/group with no login shell and no home-directory writes
# expected -- all state is PostgreSQL; the only writes are stdout/stderr
# logs, which Cloud Run captures from the container's own streams
# regardless of UID, and the empty lock files in the slot directory below.
RUN groupadd --system mitatedb && useradd --system --gid mitatedb --no-create-home --shell /usr/sbin/nologin mitatedb

# Host-shared concurrency slots (`cloud-run-cloud-sql.md` §6.5): one
# directory every uvicorn worker of the data service opens, created here
# (the application only checks it -- existence, owner = its own effective
# uid, mode 0700, a working `flock` -- and never creates it), owned by the
# `USER` below, mode 0700. `MITATEDB_SLOT_DIR` names it; the control
# service uses no slot directory and ignores the variable. It holds empty
# lock files only, never persistent state.
RUN mkdir -p /var/lib/mitatedb/slots \
    && chown mitatedb:mitatedb /var/lib/mitatedb/slots \
    && chmod 0700 /var/lib/mitatedb/slots
ENV MITATEDB_SLOT_DIR=/var/lib/mitatedb/slots

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# CONTRACT PACKAGING (Phase 6 WP-0, design D-4(b)): this image no longer
# needs its own manual copy of the contract at a computed runtime-stage
# path. The prior fix here (2026-09-01, operator finding) worked around
# `http.py`'s then-repository-relative contract lookup, which broke under
# this image's own flat `pip install .` layout (no source-checkout `spec/`
# sibling exists inside the venv). That lookup is gone: `http.py` (and
# `control_http.py`, which now imports `_SCHEMAS` from it rather than
# loading a second independent copy) load the contract via `importlib.
# resources` from `mitatedb_api/contract/data-service-api.v1.json`, a
# byte-identical packaged copy wired in as package data (`pyproject.toml`'s
# own `[tool.setuptools.package-data]`, mirroring r2db-api's own
# `r2db_api/contract/*.json`). The builder stage's `pip install .` above
# already installs that packaged copy as part of the wheel -- no separate
# `COPY` of `spec/...` into the runtime stage is needed any more.
# `MitateDB-api/tests/test_http.py::test_packaged_contract_copy_is_byte_
# identical_to_spec_source_of_truth` is what keeps the packaged copy from
# silently drifting from `spec/` in this repository's own checkout.

# `SERVICE` selects which of the two ASGI apps this container runs --
# `data` (default) for `mitatedb_api.main:app`, `control` for
# `mitatedb_api.control_main:app`. A build-time `ARG` (baked into
# `ENV SERVICE`) rather than a purely run-time `docker run -e` value, so
# the SAME image can still be deployed as either Cloud Run service with a
# single `--set-env-vars SERVICE=control` override at `gcloud run deploy`
# time if an operator prefers not to build two tagged variants -- both
# paths work; `cloud-run-cloud-sql.md` documents the two-tagged-variant
# form as the default (R-9's own "2 Cloud Run service" instruction, one
# deploy per service, no shared runtime toggle to get wrong under load).
ARG SERVICE=data
ENV SERVICE=${SERVICE}

# Cloud Run injects `PORT`; uvicorn binds it below via shell expansion
# (the exec-form CMD's own `sh -c`, needed because Cloud Run's `PORT`
# value is only known at container-start time, not at build time).
ENV PORT=8080
EXPOSE 8080

USER mitatedb
WORKDIR /home/mitatedb

# No secret, DSN, or pepper is declared here -- see `cloud-run-cloud-sql.
# md` for the complete environment-variable contract each of the two
# services requires (`mitatedb_api.main`'s own module docstring for
# `SERVICE=data`, `mitatedb_api.control_composition.build_control_service`'s
# own module docstring for `SERVICE=control`). Startup fails loudly
# (`RuntimeError`, both composition roots' own documented policy) if a
# required variable is missing -- there is no partial-startup mode to mask
# a missing secret.
#
# Each branch runs the service's own preflight first (`python -m
# mitatedb_api.main --preflight` / `python -m mitatedb_api.control_main
# --preflight`: builds the application once with this container's own
# environment -- every startup check, including the workers-vs-
# `process_ceilings` check and, for `data`, the slot-directory checks --
# and exits non-zero on the first failure), joined to `exec uvicorn` with
# `&&`, so a failing preflight ends the container with that non-zero status
# and uvicorn never starts. uvicorn's own worker supervisor cannot do this:
# it replaces a worker that fails at startup and keeps running.
# `--workers` always comes from the environment -- `MITATEDB_WORKERS` for
# `data`, `MITATEDB_CONTROL_WORKERS` (always 1) for `control`, both
# required and without a default (`cloud-run-cloud-sql.md` §6.5) -- never
# a number written here.
CMD ["sh", "-c", "if [ \"$SERVICE\" = \"control\" ]; then python -m mitatedb_api.control_main --preflight && exec uvicorn mitatedb_api.control_main:app --host 0.0.0.0 --port \"$PORT\" --workers \"${MITATEDB_CONTROL_WORKERS}\"; else python -m mitatedb_api.main --preflight && exec uvicorn mitatedb_api.main:app --host 0.0.0.0 --port \"$PORT\" --workers \"${MITATEDB_WORKERS}\"; fi"]

# `migrations/` and the break-glass/ceremony CLI (`python -m mitatedb_api.
# ops ...`) are intentionally NOT this image's job to run automatically:
# `0001`-`0004` are operator/deploy-tooling SQL (each file's own "WHO RUNS
# THIS" header), and `ops.py`'s bootstrap/reset/break-glass subcommands are
# out-of-band by design (R-6: "bootstrap / reset は out-of-band CLI...
# in-band に置かない"). An operator invokes `python -m mitatedb_api.ops
# ...` ONLY from a checked-out source tree (this package installed with
# `pip install -e .`, `PYTHONPATH=MitateDB-api/src`) -- **never from inside
# a running container built from this image** (`cloud-run-cloud-sql.md` §7
# states this rule; this file is that rule's own citation). This is not
# merely a convention: `ops.py`'s own `_DEFAULT_MIGRATIONS_DIR = Path(
# __file__).resolve().parents[2] / "migrations"` has the SAME KIND of
# install-layout coupling `http.py`'s own contract lookup used to have
# before Phase 6 WP-0 moved that one onto packaged data (see the CONTRACT
# PACKAGING note above) -- `ops.py` itself is out of that WP's scope, so
# this coupling remains here unchanged: inside this image's
# `pip install .` venv layout, `parents[2]` from the installed `ops.py`
# lands at `/opt/venv/lib/python3.11`, where no `migrations/` directory
# exists at all (and none is ever copied into this image -- see this
# file's own footer note above on why). A `docker run --entrypoint python
# <image> -m mitatedb_api.ops ...` invocation of any subcommand that
# touches `_DEFAULT_MIGRATIONS_DIR` (`deprovision`, and any future
# subcommand relying on the same default) fails for exactly this reason,
# not only for the out-of-band-design reason above. `cloud-run-
# cloud-sql.md` §5/§7 documents the one correct invocation form (source
# checkout only).
