#!/usr/bin/env bash
# ENV VARS:
#
#   TRUSTED_PROXY_IPS: Optional. Comma-separated IPs/CIDRs trusted for
#   X-Forwarded-* headers. If unset, Gunicorn ignores forwarded headers.

num_workers="$(python -c "from ucsschool.lib.models.utils import ucr; print(ucr.get('ucsschool/kelvin/processes', 2))")"

if [ "$num_workers" = "" ]; then
    num_workers="2"
elif [ "$num_workers" -lt  "1" ]; then
    num_workers="$(nproc)"
fi

while [ ! -f "/etc/machine.secret" ]; do
    echo "waiting for univention appcenter to create /etc/machine.secret"
    sleep 1
done

exec gunicorn \
    --workers "$num_workers" \
    --worker-class uvicorn.workers.UvicornWorker \
    ${TRUSTED_PROXY_IPS:+--forwarded-allow-ips="$TRUSTED_PROXY_IPS"} \
    --bind 0.0.0.0:8911 \
    ucsschool.kelvin.main:app
