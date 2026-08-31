#!/bin/sh
# Installs any adapter wheels from the landing zone into the project venv.
# Wheels install with their declared dependencies, constrained by this
# project's own lockfile (pip/uv constraints: bounds that apply only to
# packages actually being installed). Anything IVaaS also depends on stays
# at IVaaS's locked version.
# An adapter that cannot accept those versions fails the install loudly
# instead of silently changing the environment.
# All wheels install in one resolver invocation, so version conflicts
# between adapters also fail loudly.
set -eu

wheels_dir="$(dirname "$0")/wheels"
api_dir="$(dirname "$0")/.."
application_venv_python="$api_dir/.venv/bin/python"

if ls "$wheels_dir"/*.whl >/dev/null 2>&1; then
    constraints="$wheels_dir/.ivaas-constraints.txt"
    trap 'rm -f "$constraints"' EXIT
    uv export --project "$api_dir" --frozen --no-dev --no-hashes --no-emit-workspace \
        --quiet --output-file "$constraints"
    uv pip install --python "$application_venv_python" \
        --constraint "$constraints" "$wheels_dir"/*.whl
fi
