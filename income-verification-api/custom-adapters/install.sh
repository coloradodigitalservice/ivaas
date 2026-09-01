#!/bin/sh
# Installs any adapter wheels from the landing zone into the project venv.
# Wheels install with their declared dependencies. Packages IVaaS locks
# are constrained to its locked versions; dependencies only adapters
# use resolve at install time within the ranges the wheels declare.
set -eu

wheels_dir="$(dirname "$0")/wheels"
api_dir="$(dirname "$0")/.."
application_venv_python="$api_dir/.venv/bin/python"

if ls "$wheels_dir"/*.whl >/dev/null 2>&1; then
    constraints_txt_temp="$wheels_dir/.ivaas-constraints_txt_temp.txt"
    trap 'rm -f "$constraints_txt_temp"' EXIT
    # Export IVaaS constraints_txt_temp for adapters to build against
    # --frozen: Use the lockfile exactly as it is on disc
    # --no-dev: dev dependencies not relevant for adapter wheel installation
    # --no-hashes: omit integrity hashes; versions stay exact pins (constraints install nothing, so hashes add nothing)
    # --no-emit-workspace: leave out workspace packages like ivaas-core, already installed in the venv
    # --quiet, --output-file: write constraints to the temporary file
    uv export --project "$api_dir" --frozen --no-dev --no-hashes --no-emit-workspace \
        --quiet --output-file "$constraints_txt_temp"
    # Install adapter wheels with their dependencies from the wheels landing zone
    # --constraint: use the constraints file to install wheels, failing where constraints conflict
    uv pip install --python "$application_venv_python" \
        --constraint "$constraints_txt_temp" "$wheels_dir"/*.whl
fi
