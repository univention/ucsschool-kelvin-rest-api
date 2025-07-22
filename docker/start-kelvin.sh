#!/usr/bin/env bash
# ENV VARS:
#
#   TRUSTED_PROXY_IPS: Optional. Comma-separated IPs/CIDRs trusted for
#   X-Forwarded-* headers. If unset, Gunicorn ignores forwarded headers.

num_workers="$(ucr get ucsschool/kelvin/processes)"
if [ "$num_workers" = "" ]; then
    num_workers="2"
elif [ "$num_workers" -lt  "1" ]; then
    num_workers="$(nproc)"
fi

while [ ! -f "/etc/machine.secret" ]; do
    echo "waiting for univention appcenter to create /etc/machine.secret"
    sleep 1
done

/usr/bin/python -c "import openapi_client_udm"

if [ $? -eq 1 ]; then
    echo "Module openapi_client_udm is not installed. Installing..."
    MACHINE_USER="$HOSTNAME\$"
    MACHINE_PASSWORD=$(cat /etc/machine.secret)
    UPDATE_LOCKFILE="/tmp/update_openapi_client_lock"
    /usr/bin/flock "$UPDATE_LOCKFILE" \
        /usr/bin/update_openapi_client \
        --generator java \
        --jar /kelvin/openapi-generator/jar/openapi-generator-cli-*.jar \
        --username "$MACHINE_USER" \
        --password "$MACHINE_PASSWORD" \
        "$DOCKER_HOST_NAME"
fi

exec gunicorn \
    --workers "$num_workers" \
    --worker-class uvicorn.workers.UvicornWorker \
    ${TRUSTED_PROXY_IPS:+--forwarded-allow-ips="$TRUSTED_PROXY_IPS"} \
    --bind 0.0.0.0:8911 \
    ucsschool.kelvin.main:app
