#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only
#
# Run the tests that don't need a UCS system, like the CI test jobs do.
# Usage: dev/test-unit.sh [objects|connector|lib|kelvin-api ...] [-- pytest args]
# The tests marked in_container need a UCS VM: see dev/agent-vm-test.py.

set -uo pipefail
cd "$(dirname "$0")/.." || exit 2
repo="$PWD"

suites=()
while [[ $# -gt 0 && "$1" != "--" ]]; do
    suites+=("$1")
    shift
done
[[ "${1:-}" == "--" ]] && shift
[[ ${#suites[@]} -eq 0 ]] && suites=(objects connector lib kelvin-api)

python="${VENV:-$repo/.venv}/bin/python"
if [[ ! -x "$python" ]] || ! "$python" -c "import pytestarch" 2>/dev/null; then
    echo "No complete virtualenv. Run: uv sync --all-packages --group dev" >&2
    echo "(building python-ldap needs libldap2-dev and libsasl2-dev)" >&2
    exit 2
fi

# The Docker image and CI copy create_ou.py from ucs-school-import into ucs-school-lib.
create_ou="ucs-school-lib/modules/ucsschool/lib/create_ou.py"
ucr_file="$(mktemp)"
cleanup() {
    rm -f "$ucr_file"
    [[ -n "${copied_create_ou:-}" ]] && rm -f "$create_ou"
}
trap cleanup EXIT
if [[ ! -e "$create_ou" ]]; then
    cp ucs-school-import/modules/ucsschool/lib/create_ou.py "$create_ou"
    copied_create_ou=1
fi

export UNIVENTION_BASECONF="$ucr_file" PYTHONDONTWRITEBYTECODE=1
failed=()
run_env=()
run() {
    local name="$1" dir="$2"
    shift 2
    echo "=== $name"
    (cd "$dir" && env "${run_env[@]}" "$python" -m pytest -q -p no:cacheprovider "$@") || failed+=("$name")
    run_env=()
}
for suite in "${suites[@]}"; do
    case "$suite" in
        objects) run objects ucsschool-objects --cov-fail-under=100 . "$@" ;;
        connector) run connector kelvin-connector --cov-fail-under=100 . "$@" ;;
        lib) run lib ucs-school-lib/modules -m "not in_container" ucsschool/lib/tests "$@" ;;
        kelvin-api)
            run_env=(LDAP_BASE=foo LDAP_HOSTDN= LDAP_SERVER_NAME= LDAP_SERVER_PORT=0)
            run kelvin-api kelvin-api -m "not in_container" tests "$@"
            ;;
        *)
            echo "Unknown suite: $suite (objects, connector, lib, kelvin-api)" >&2
            exit 2
            ;;
    esac
done

if [[ ${#failed[@]} -gt 0 ]]; then
    echo "FAILED: ${failed[*]}" >&2
    exit 1
fi
echo "All suites passed: ${suites[*]}"
