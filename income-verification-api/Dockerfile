# python:3.14.7-slim-trixie
ARG PYTHON_IMAGE=python@sha256:cad9a2c871761c413caa6fdd6441c783451e740a48aaeba60ae62a8b53525ef6
# ghcr.io/astral-sh/uv:0.11.29
ARG UV_IMAGE=ghcr.io/astral-sh/uv@sha256:eb2843a1e56fd9e30c7276ce1a52cba86e64c7b385f5e3279a0e08e02dd058fc

FROM ${PYTHON_IMAGE} AS base

RUN apt-get update \
  && apt-get install -y --no-install-recommends --only-upgrade \
        base-files=13.8+deb13u7 \
        bash=5.2.37-2+b10 \
        gzip=1.13-1+deb13u1 \
        libaudit-common=1:4.0.2-2+deb13u1 \
        libaudit1=1:4.0.2-2+deb13u1 \
        libc-bin=2.41-12+deb13u4 \
        libc6=2.41-12+deb13u4 \
        libcap2=1:2.75-10+deb13u1+b3 \
        libpcre2-8-0=10.46-1~deb13u2 \
        libsqlite3-0=3.46.1-7+deb13u2 \
        perl-base=5.40.1-6+deb13u1 \
        tzdata=2026c-0+deb13u1 \
  && rm -rf /var/lib/apt/lists/*

FROM ${UV_IMAGE} AS uv

FROM base AS builder

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

# `--no-editable` copies the ivaas-core workspace member into the venv, so the
# runtime stage only needs the venv, instead of the broader source tree.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project --no-dev --no-editable

# Install adapters last, do not sync after this.
COPY custom-adapters/ custom-adapters/
RUN custom-adapters/install.sh

FROM base AS runtime

# Keeps Python from buffering stdout and stderr to avoid situations where
# the application crashes without emitting any logs due to buffering.
ENV PYTHONUNBUFFERED=1

# Prevent a uv sync after adapter install, in the event a runtime with uv were to be configured in the future
ENV UV_NO_SYNC=1

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
COPY --chown=django:django adapter_registry /api/adapter_registry
COPY --chown=django:django manage.py /api/manage.py

USER django

EXPOSE 8000

CMD ["uvicorn", "config.asgi:application", "--host", "0.0.0.0", "--port", "8000"]
