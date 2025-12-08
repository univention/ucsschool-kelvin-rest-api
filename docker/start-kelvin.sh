#!/bin/sh

# for auto-reload during development run:
# export DEV=1

if [ "$DEV" = 1 ]; then
    RELOAD="--reload"
else
    RELOAD=""
fi

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

exec /usr/bin/gunicorn \
    --workers "$num_workers" \
    --worker-class uvicorn.workers.UvicornWorker \
    $RELOAD \
    --bind 0.0.0.0:8911 \
    ucsschool.kelvin.main:app
