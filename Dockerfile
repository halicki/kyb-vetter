# syntax=docker/dockerfile:1.7
# One image for the MCP server (default CMD) and the worker jobs (`python -m kyb_vetter_worker ...`).
FROM ghcr.io/astral-sh/uv:python3.15-trixie-slim AS builder
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=0 UV_NO_DEV=1
# py7zr's codecs (pybcj, pyppmd, inflate64) ship no cp315 wheels yet: build them here, not at runtime.
RUN apt-get update && apt-get install -y --no-install-recommends gcc libc6-dev && rm -rf /var/lib/apt/lists/*
WORKDIR /app
# Dependency layer: only lockfile + manifests, no sources (cached until the lock changes).
COPY pyproject.toml uv.lock ./
COPY packages/core/pyproject.toml packages/core/
COPY apps/mcp/pyproject.toml apps/mcp/
COPY apps/api/pyproject.toml apps/api/
COPY apps/worker/pyproject.toml apps/worker/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-workspace --package kyb-vetter-mcp --package kyb-vetter-worker
# Sources, then install the workspace members themselves.
COPY packages/core/ packages/core/
COPY apps/mcp/ apps/mcp/
COPY apps/worker/ apps/worker/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-editable --package kyb-vetter-mcp --package kyb-vetter-worker

FROM python:3.15-slim-trixie
RUN groupadd --system app && useradd --system --gid app --home /app app \
    && apt-get update && apt-get install -y --no-install-recommends tzdata && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=builder --chown=app:app /app/.venv /app/.venv
# Alembic runs from the source tree (migrations are not a package); keep it next to the venv.
COPY --from=builder --chown=app:app /app/packages/core/alembic.ini /app/packages/core/alembic.ini
COPY --from=builder --chown=app:app /app/packages/core/alembic /app/packages/core/alembic
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PORT=8080
USER app
EXPOSE 8080
CMD ["python", "-m", "kyb_vetter_mcp", "http"]
