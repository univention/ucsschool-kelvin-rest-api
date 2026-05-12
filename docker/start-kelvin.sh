#!/usr/bin/env bash
# ENV VARS:
#
#   TRUSTED_PROXY_IPS: Optional. Comma-separated IPs/CIDRs trusted for
#   X-Forwarded-* headers. If unset, Gunicorn ignores forwarded headers.

APPCENTER_TIMEOUT=0
while [[ ! -f "/etc/machine.secret" ]]; do
    if [[ APPCENTER_TIMEOUT -gt 60 ]]; then
        echo "ERROR: univention appcenter did not write /etc/machine.secret"
        exit 1
    fi
    # Currently the best way to wait for the appcenter to configure the container
    echo "waiting for univention appcenter to create /etc/machine.secret"
    sleep 1
    ((APPCENTER_TIMEOUT++))
done

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

if [[ "$SKIP_UCSSCHOOL_KELVIN_DB_MIGRATION" != "true" ]]; then
    echo "Migration log:"
    alembic --config pyproject.toml upgrade head
    echo "... migration done"
fi

exec gunicorn \
    --workers "$NUM_WORKERS" \
    --worker-class uvicorn.workers.UvicornWorker \
    ${TRUSTED_PROXY_IPS:+--forwarded-allow-ips="$TRUSTED_PROXY_IPS"} \
    --bind 0.0.0.0:8911 \
    ucsschool.kelvin.main:app
