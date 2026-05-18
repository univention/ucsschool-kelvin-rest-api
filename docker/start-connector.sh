#!/usr/bin/env bash

if [ "$LDAP_SERVER_TYPE" != "master" ]; then
    echo "Kelvin connector will only run on server type master (LDAP_SERVER_TYPE=\"$LDAP_SERVER_TYPE\")"
    sleep inf
else
    APP_PROVISIONING_CONFIG_FILE="/var/lib/univention-appcenter/apps/ucsschool-kelvin-rest-api/conf/provisioning/provisioning_config.json"
    TIMEOUT="${APPCENTER_WAIT_TIMEOUT:-120}"
    elapsed=0
    while [[ ! -f "$APP_PROVISIONING_CONFIG_FILE" ]]; do
        if [[ $elapsed -ge $TIMEOUT ]]; then
            echo "ERROR: timed out waiting for $APP_PROVISIONING_CONFIG_FILE after ${TIMEOUT}s"
            exit 1
        fi
        echo "waiting for $APP_PROVISIONING_CONFIG_FILE (${elapsed}s / ${TIMEOUT}s)"
        sleep 1
        ((elapsed++))
    done

    KELVIN_HEALTH_URL="${KELVIN_HEALTH_URL:-http://api:8911/health}"
    TIMEOUT="${KELVIN_WAIT_TIMEOUT:-120}"
    elapsed=0
    while ! python3 -c "import urllib.request, sys; urllib.request.urlopen(sys.argv[1])" "$KELVIN_HEALTH_URL" > /dev/null 2>&1; do
        if [[ $elapsed -ge $TIMEOUT ]]; then
            echo "ERROR: timed out waiting for $KELVIN_HEALTH_URL after ${TIMEOUT}s"
            exit 1
        fi
        echo "waiting for $KELVIN_HEALTH_URL (${elapsed}s / ${TIMEOUT}s)"
        sleep 1
        ((elapsed++))
    done

    echo "Starting connector."
    /venv/bin/connector
fi
