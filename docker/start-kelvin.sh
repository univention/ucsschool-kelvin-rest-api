#!/usr/bin/env bash
# ENV VARS:
#
#   TRUSTED_PROXY_IPS: Optional. Comma-separated IPs/CIDRs trusted for
#   X-Forwarded-* headers. If unset, Gunicorn ignores forwarded headers.

TIMEOUT="${APPCENTER_WAIT_TIMEOUT:-60}"
elapsed=0
while [[ ! -f "/etc/machine.secret" ]]; do
    if [[ $elapsed -ge $TIMEOUT ]]; then
        echo "ERROR: timed out waiting for /etc/machine.secret after ${TIMEOUT}s"
        exit 1
    fi
    echo "waiting for /etc/machine.secret (${elapsed}s / ${TIMEOUT}s)"
    sleep 1
    ((elapsed++))
done

if [[ -z "${UCSSCHOOL_KELVIN_DB_URI}" ]]; then
    DB_URI_FILE="${UCSSCHOOL_KELVIN_DB_URI_FILE:-/etc/ucsschool/kelvin/postgresql-kelvin.uri}"
    TIMEOUT="${MIGRATE_WAIT_TIMEOUT:-120}"
    elapsed=0
    while [[ ! -f "$DB_URI_FILE" ]]; do
        if [[ $elapsed -ge $TIMEOUT ]]; then
            echo "ERROR: timed out waiting for $DB_URI_FILE after ${TIMEOUT}s"
            exit 1
        fi
        echo "waiting for $DB_URI_FILE (${elapsed}s / ${TIMEOUT}s)"
        sleep 1
        ((elapsed++))
    done
fi

if [[ "$SKIP_UCSSCHOOL_KELVIN_DB_MIGRATION" != "true" ]]; then
    echo "Migration log:"
    alembic --config pyproject.toml upgrade head
    echo "... migration done"
fi

NUM_WORKERS="${NUM_WORKERS:-$(ucr get ucsschool/kelvin/processes)}"

if [[ -z "$NUM_WORKERS" ]]; then
    NUM_WORKERS="2"
elif [[ "$NUM_WORKERS" -lt  "1" ]]; then
    NUM_WORKERS="$(nproc)"
fi

python -c "import openapi_client_udm"

if [[ $? -eq 1 ]]; then
    echo "Module openapi_client_udm is not installed. Installing..."
    MACHINE_USER="$(hostname)\$"
    MACHINE_PASSWORD=$(cat /etc/machine.secret)
    UPDATE_LOCKFILE="/tmp/update_openapi_client_lock"
    /usr/bin/flock "$UPDATE_LOCKFILE" \
        update_openapi_client \
        --generator java \
        --jar /kelvin/openapi-generator/jar/openapi-generator-cli-*.jar \
        --username "$MACHINE_USER" \
        --password "$MACHINE_PASSWORD" \
        "$DOCKER_HOST_NAME"
fi

exec gunicorn \
    --workers "$NUM_WORKERS" \
    --worker-class uvicorn.workers.UvicornWorker \
    ${TRUSTED_PROXY_IPS:+--forwarded-allow-ips="$TRUSTED_PROXY_IPS"} \
    --bind 0.0.0.0:8911 \
    ucsschool.kelvin.main:app
