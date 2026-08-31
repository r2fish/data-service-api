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
# control-plane container.
COPY pyproject.toml ./
COPY src ./src

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
# ...` from a checked-out source tree (this package installed with
# `pip install -e .`, `PYTHONPATH` pointed at `src/`) or from a one-off
# `docker run --entrypoint python <image> -m mitatedb_api.ops ...`
# invocation with the relevant DSN/pepper env vars supplied -- never as
# this image's own default `CMD`. `cloud-run-cloud-sql.md` §5 documents
# both invocation forms.
