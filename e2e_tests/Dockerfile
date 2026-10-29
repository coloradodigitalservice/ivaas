# python:3.14.10-slim-trixie
ARG PYTHON_IMAGE=python@sha256:3cabfd7d7aaf394e6040e79fa1eec6ca1c52b74ed9188650472695d9a9326999
# ghcr.io/astral-sh/uv:0.13.6
ARG UV_IMAGE=ghcr.io/astral-sh/uv@sha256:af22a52f5eafef3d78e551599d405c02df61919d18028f0cea8eda93bc9986d0

FROM ${UV_IMAGE} AS uv

FROM ${PYTHON_IMAGE} AS base

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
