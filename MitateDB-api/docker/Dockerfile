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
# BUILD CONTEXT (2026-09-01 fix, part of the same first-deployment fix as
# the runtime-stage `COPY spec/...` below): this image now needs a file
# (`spec/data-service-api.v1.json`) that lives at the common repository
# root, one level above `MitateDB-api/` -- outside a build context scoped
# to `MitateDB-api/` alone, which every `COPY` source below used to assume
# (`COPY pyproject.toml ./` only resolves because `pyproject.toml` sits at
# `MitateDB-api/pyproject.toml`). Build this image from the REPOSITORY
# ROOT, naming this file explicitly, e.g.:
#   docker build -f MitateDB-api/docker/Dockerfile -t mitatedb-api:SERVICE_data .
# every `COPY` source in this file is written relative to that root
# accordingly (`MitateDB-api/...` for this package's own files, `spec/...`
# for the common contract) -- see `cloud-run-cloud-sql.md` §6's own build
# step for the full command this runbook now documents.

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

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
# `pip install .` resolves `starlette`/`psycopg[binary]`/`uvicorn` from
# `pyproject.toml`'s own `[project.dependencies]` (WP-1) -- no separate
# requirements file, no version drift between what this image installs and
# what `pip install -e .[test]` installs locally for development.
RUN pip install --no-cache-dir .

# ---------------------------------------------------------------------------
# Stage 2: runtime -- the venv built above, copied onto a slim base, run as
# a non-root user.
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS runtime

# Non-root (R-9's own "非 root" instruction): a dedicated, unprivileged
# system user/group with no login shell and no home-directory writes
# expected -- this process never writes to its own container filesystem
# (all state is PostgreSQL; the only writes are stdout/stderr logs, which
# Cloud Run captures from the container's own streams regardless of UID).
RUN groupadd --system mitatedb && useradd --system --gid mitatedb --no-create-home --shell /usr/sbin/nologin mitatedb

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# FIRST-DEPLOYMENT FIX (2026-09-01, operator finding, "§9級" per the
# operator's own report): `http.py`'s `_CONTRACT_PATH = Path(__file__).
# resolve().parents[3] / "spec" / "data-service-api.v1.json"` is coupled to
# how many directory hops separate the installed module from the repo root
# it assumes it is still sitting inside. In a source checkout (`pip install
# -e .`) that path is `.../MitateDB-api/src/mitatedb_api/http.py`, and
# `parents[3]` from there IS the repo root (`data-service-api/`), where
# `spec/` really lives -- so local dev/test never notices this coupling.
# `pip install .` (this image's own builder stage, no `-e`) instead installs
# the package flat into the venv's site-packages, so the SAME module lands
# at `/opt/venv/lib/python3.11/site-packages/mitatedb_api/http.py` in the
# runtime image (`python:3.11-slim`, this Dockerfile's own `FROM` line is
# the actual version pin; this package's own `pyproject.toml`
# `requires-python = ">=3.11"` is only a floor, not what fixes "3.11"
# specifically here) --
# `parents[3]` from THAT path is `/opt/venv/lib` (parents[0]=`.../site-
# packages/mitatedb_api`, [1]=`.../site-packages`, [2]=`.../python3.11`,
# [3]=`/opt/venv/lib`), two hops shallower than the repo-root case above
# (the installed layout has no `src/`/`MitateDB-api/` hops to climb). So
# the runtime image needs its own copy of the contract at
# `/opt/venv/lib/spec/data-service-api.v1.json` -- confirmed working by the
# operator against the real first deployment -- computed here, not merely
# copied from that report, by walking the same four `.parents[]` hops
# against this stage's own actual installed module path. Path is
# repo-root-relative (see the BUILD CONTEXT note above the builder stage).
COPY spec/data-service-api.v1.json /opt/venv/lib/spec/data-service-api.v1.json

# ROOT FIX CANDIDATE (not this fix's scope, logged docs/design/
# PHASE35_CROSS_ENTITY_AND_CONTRACT_130_V1.md §7 ledger): this COPY still
# couples the image to the exact `parents[3]` arithmetic above. The Python
# minor version itself is NOT the fragile part -- `.../site-packages/
# mitatedb_api` is always exactly 3 `.parents[]` hops below `<venv>/lib`
# regardless of which `python3.X` directory name sits in between -- but any
# change to the INSTALL LAYOUT (a different venv path/prefix than
# `/opt/venv`, a build tool that installs into a `.dist-info`-relative
# layout instead of plain `site-packages`, etc.) still breaks it silently.
# r2db-api's own `http.py` avoids this entirely with a packaged contract
# copy loaded via `importlib.resources` (`r2db_api/contract/data-service-
# api.v1.json`, wired in as package data, `test_http.py::
# test_packaged_contract_copy_is_byte_identical_to_spec_source_of_truth`)
# with a filesystem-path fallback for editable-install dev -- the same
# shape this peer could adopt so this image no longer depends on
# filesystem layout coupling at all.

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
CMD ["sh", "-c", "if [ \"$SERVICE\" = \"control\" ]; then exec uvicorn mitatedb_api.control_main:app --host 0.0.0.0 --port \"$PORT\"; else exec uvicorn mitatedb_api.main:app --host 0.0.0.0 --port \"$PORT\"; fi"]

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
# __file__).resolve().parents[2] / "migrations"` has the SAME
# install-layout coupling this file's own runtime-stage `_CONTRACT_PATH`
# fix (above) exists to work around for `http.py` -- inside this image's
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
