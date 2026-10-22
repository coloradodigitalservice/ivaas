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
WORKDIR /e2e
COPY income-verification-api/pyproject.toml income-verification-api/uv.lock income-verification-api/.python-version ./
# Frozen uses the existing lock without needing application or workspace source.
RUN uv sync --frozen --only-group test --no-editable

FROM base AS runtime

ENV PATH="/e2e/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTEST_DISABLE_PLUGIN_AUTOLOAD=1

WORKDIR /e2e
COPY --from=builder /e2e/.venv /e2e/.venv
COPY e2e_tests/test_api.py e2e_tests/conftest.py e2e_tests/e2e_test_client.py e2e_tests/pytest.ini ./e2e_tests/
RUN mkdir /results && chown 1001:1001 /results
USER 1001:1001

ENTRYPOINT ["python", "-m", "pytest", "-c", "e2e_tests/pytest.ini", "e2e_tests/test_api.py", "-p", "no:cacheprovider"]
CMD ["--junitxml=/results/e2e-results.xml"]
