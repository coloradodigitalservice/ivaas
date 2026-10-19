# python:3.14.7-slim-trixie
ARG PYTHON_IMAGE=python@sha256:51dafde81dbdb6ebde285137a295cf18a47ca95234fe388a343719cb97305b3d
# ghcr.io/astral-sh/uv:0.12.15
ARG UV_IMAGE=ghcr.io/astral-sh/uv@sha256:62f8c047d0a0e9ece6b53fc63df902585a67a47a7f318ddec4a37db586edc8e3

FROM ${UV_IMAGE} AS uv

FROM ${PYTHON_IMAGE} AS base

# Match the application image's base-system security fixes.
RUN apt-get update \
  && apt-get install -y --no-install-recommends --only-upgrade \
        libpcre2-8-0=10.46-1~deb13u3 \
        libssl3t64=3.5.7-1~deb13u3 \
        openssl-provider-legacy=3.5.7-1~deb13u3 \
        openssl=3.5.7-1~deb13u3 \
  && rm -rf /var/lib/apt/lists/*

FROM base AS builder

COPY --from=uv /uv /bin/uv
ENV UV_PYTHON_DOWNLOADS=0 UV_LINK_MODE=copy
WORKDIR /smoke
COPY income-verification-api/pyproject.toml income-verification-api/uv.lock income-verification-api/.python-version ./
# Frozen uses the existing lock without needing application or workspace source.
RUN uv sync --frozen --only-group test --no-editable

FROM base AS runtime

ENV PATH="/smoke/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTEST_DISABLE_PLUGIN_AUTOLOAD=1

WORKDIR /smoke
COPY --from=builder /smoke/.venv /smoke/.venv
COPY smoke_tests/test_api.py smoke_tests/conftest.py smoke_tests/smoke_client.py smoke_tests/pytest.ini ./smoke_tests/
RUN mkdir /results && chown 1001:1001 /results
USER 1001:1001

ENTRYPOINT ["python", "-m", "pytest", "-c", "smoke_tests/pytest.ini", "smoke_tests/test_api.py", "-p", "no:cacheprovider"]
CMD ["--junitxml=/results/smoke-results.xml"]
