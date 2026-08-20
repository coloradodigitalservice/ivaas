# python:3.14.6-slim-trixie
ARG PYTHON_IMAGE=python@sha256:7bec7ddcddeff7975d6ba9b4be7dd6f6b2f55e7491539145e2978f7f97ce9144
# ghcr.io/astral-sh/uv:0.11.29
ARG UV_IMAGE=ghcr.io/astral-sh/uv@sha256:eb2843a1e56fd9e30c7276ce1a52cba86e64c7b385f5e3279a0e08e02dd058fc

FROM ${UV_IMAGE} AS uv
FROM ${PYTHON_IMAGE} AS builder

# Enable bytecode compilation
ENV UV_COMPILE_BYTECODE=1

# Copy from the cache instead of linking since it's a mounted volume
ENV UV_LINK_MODE=copy

# Disable python downloads
ENV UV_PYTHON_DOWNLOADS=0

WORKDIR /api

COPY --from=uv /uv /bin/

COPY pyproject.toml uv.lock .python-version ./
COPY packages/ packages/
COPY custom-adapters/ custom-adapters/

# `--no-editable` copies the ivaas-core workspace member into the venv, so the
# runtime stage only needs the venv, instead of the broader source tree.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project --no-dev --no-editable

FROM ${PYTHON_IMAGE} AS runtime

# Keeps Python from buffering stdout and stderr to avoid situations where
# the application crashes without emitting any logs due to buffering.
ENV PYTHONUNBUFFERED=1

ENV PATH="/api/.venv/bin:$PATH"

WORKDIR /api

RUN addgroup --system --gid 1001 django \
    && adduser \
        --system \
        --uid 1001 \
        --ingroup django \
        --home /home/django \
        django

COPY --from=builder \
    --chown=django:django \
    /api/.venv \
    /api/.venv

COPY --chown=django:django api /api/api
COPY --chown=django:django config /api/config
COPY --chown=django:django income_sources /api/income_sources
COPY --chown=django:django manage.py /api/manage.py

USER django

EXPOSE 8000

CMD ["uvicorn", "config.asgi:application", "--host", "0.0.0.0", "--port", "8000"]
