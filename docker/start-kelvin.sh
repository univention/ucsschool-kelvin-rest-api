#!/usr/bin/env bash

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

exec gunicorn --workers "$num_workers" --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:8911 ucsschool.kelvin.main:app
