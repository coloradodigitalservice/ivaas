# python:3.14.7-slim-trixie
ARG PYTHON_IMAGE=python@sha256:51dafde81dbdb6ebde285137a295cf18a47ca95234fe388a343719cb97305b3d
# ghcr.io/astral-sh/uv:0.12.15
ARG UV_IMAGE=ghcr.io/astral-sh/uv@sha256:62f8c047d0a0e9ece6b53fc63df902585a67a47a7f318ddec4a37db586edc8e3

FROM ${PYTHON_IMAGE} AS base

RUN apt-get update \
  && apt-get install -y --no-install-recommends --only-upgrade \
        libpcre2-8-0=10.46-1~deb13u3 \
        libssl3t64=3.5.7-1~deb13u3 \
        openssl-provider-legacy=3.5.7-1~deb13u3 \
        openssl=3.5.7-1~deb13u3 \
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

COPY --chown=django:django income_verification /api/income_verification
COPY --chown=django:django config /api/config
COPY --chown=django:django adapter_engine /api/adapter_engine
COPY --chown=django:django manage.py /api/manage.py

USER django

EXPOSE 8000

CMD ["uvicorn", "config.asgi:application", "--host", "0.0.0.0", "--port", "8000"]
