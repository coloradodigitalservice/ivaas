#!/bin/sh
# Installs any adapter wheels from the landing zone into the project venv.
# Wheels install with their declared dependencies. Packages IVaaS locks
# are constrained to its locked versions; dependencies only adapters
# use resolve at install time within the ranges the wheels declare,
# bounded by the shared constraints.txt file.
set -eu

wheels_dir="$(dirname "$0")/wheels"
api_dir="$(dirname "$0")/.."
application_venv_python="$api_dir/.venv/bin/python"
constraints_txt="$(dirname "$0")/constraints.txt"

if ls "$wheels_dir"/*.whl >/dev/null 2>&1; then
    ivaas_constraints_temp_txt="$wheels_dir/.ivaas-constraints-temp.txt"
    trap 'rm -f "$ivaas_constraints_temp_txt"' EXIT
    # Export IVaaS's locked versions as constraints for adapters to install against
    # --locked: fail if uv.lock does not match pyproject.toml, instead of exporting stale pins
    # --no-dev: dev dependencies not relevant for adapter wheel installation
    # --no-hashes: omit integrity hashes; versions stay exact pins (constraints install nothing, so hashes add nothing)
    # --no-emit-workspace: leave out workspace packages like ivaas-core, already installed in the venv
    # --quiet, --output-file: write constraints to the temporary file
    uv export --project "$api_dir" --locked --no-dev --no-hashes --no-emit-workspace \
        --quiet --output-file "$ivaas_constraints_temp_txt"
    # Install adapter wheels with their dependencies from the wheels landing zone
    # --constraint: all constraints files apply together; the install fails where any conflict
    uv pip install --python "$application_venv_python" \
        --constraint "$ivaas_constraints_temp_txt" \
        --constraint "$constraints_txt" \
        "$wheels_dir"/*.whl
    # Audit the whole venv: fail if any package is left with unsatisfied declared dependencies
    uv pip check --python "$application_venv_python"
fi
