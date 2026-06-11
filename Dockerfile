# syntax=docker/dockerfile:1.7
#
# analytics-app
# Python 3.12 app managed with uv (https://docs.astral.sh/uv/guides/integration/docker/).
#
# Layer-cache strategy:
#   1. Copy lockfile + pyproject, install deps only           -> cached unless deps change
#   2. Copy source, install project itself (no deps re-fetch) -> cached unless source changes
#
# uv image already provides uv binary + python. Bookworm-slim = glibc (works with pyarrow / duckdb wheels).

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS base

ARG APP_HOME=/app
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=${APP_HOME}/.venv \
    UV_PYTHON_INSTALL_DIR=/opt/uv/python \
    PATH=${APP_HOME}/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    APP_HOME=${APP_HOME}

WORKDIR ${APP_HOME}

# ---------- deps layer (heavy, cacheable) ----------
COPY pyproject.toml uv.lock ./
# --no-install-project = install dependencies only; project itself comes after source copy
# --frozen            = respect uv.lock exactly (fails fast if lockfile drifted)
# --no-dev            = production only
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# ---------- source layer (light, changes often) ----------
COPY ingest ./ingest
COPY orchestration ./orchestration
COPY dbt ./dbt
COPY README.md ./

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen

# NOTE: running as root because named Docker volumes (duckdb-data) are created
# root-owned and the app needs to write the DuckDB file there. Switch to a
# non-root uid only after wiring up an entrypoint that chowns the volume first.
RUN mkdir -p ${APP_HOME}/duckdb ${APP_HOME}/data

# Default entry: run ingestion once, then idle so the container stays up.
# Override with `command:` in compose for the scheduler service.
CMD ["sh", "-c", "python -m ingest.run; tail -f /dev/null"]
