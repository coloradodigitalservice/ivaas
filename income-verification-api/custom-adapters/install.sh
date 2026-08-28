#!/bin/sh
# Installs any adapter wheels from the landing zone into the project venv.
# Each wheel arrives with a *-requirements.txt pinning the exact dependency
# versions it was built and tested against; those are installed first, then
# the wheels themselves with --no-deps so nothing resolves at install time.
set -eu

wheels_dir="$(dirname "$0")/wheels"
application_venv_python="$(dirname "$0")/../.venv/bin/python"

for requirements in "$wheels_dir"/*-requirements.txt; do
    [ -f "$requirements" ] || continue
    uv pip install --python "$application_venv_python" --requirements "$requirements"
done

if ls "$wheels_dir"/*.whl >/dev/null 2>&1; then
    uv pip install --python "$application_venv_python" --no-deps "$wheels_dir"/*.whl
fi
