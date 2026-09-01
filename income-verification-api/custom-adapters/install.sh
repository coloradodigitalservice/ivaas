#!/bin/sh
# Installs any adapter wheels from the landing zone into the project venv.
set -eu

wheels_dir="$(dirname "$0")/wheels"
application_venv_python="$(dirname "$0")/../.venv/bin/python"

if ls "$wheels_dir"/*.whl >/dev/null 2>&1; then
    uv pip install --python "$application_venv_python" --no-deps "$wheels_dir"/*.whl
fi
