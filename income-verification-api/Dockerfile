ARG PYTHON_VERSION=3.14.6
ARG UV_VERSION=0.11.29

FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv
FROM python:${PYTHON_VERSION}-slim-trixie AS builder

# Enable bytecode compilation
ENV UV_COMPILE_BYTECODE=1

# Copy from the cache instead of linking since it's a mounted volume
ENV UV_LINK_MODE=copy

# Disable python downloads
ENV UV_PYTHON_DOWNLOADS=0

WORKDIR /api

COPY --from=uv /uv /bin/

COPY pyproject.toml uv.lock .python-version ./

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project --no-dev

FROM python:${PYTHON_VERSION}-slim-trixie AS runtime

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
COPY --chown=django:django manage.py /api/manage.py

USER django

EXPOSE 8000

CMD ["uvicorn", "config.asgi:application", "--host", "0.0.0.0", "--port", "8000"]
