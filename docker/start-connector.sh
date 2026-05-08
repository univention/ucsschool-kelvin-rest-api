#!/usr/bin/env bash

if [ "$LDAP_SERVER_TYPE" != "master" ]; then
    echo "Kelvin connector will only run on server type master (LDAP_SERVER_TYPE=\"$LDAP_SERVER_TYPE\")"
    sleep inf
else
    APPCENTER_TIMEOUT=0
    APP_PROVISIONING_CONFIG_FILE="/var/lib/univention-appcenter/apps/ucsschool-kelvin-rest-api/conf/provisioning_config.json"
    while [[ ! -f "$APP_PROVISIONING_CONFIG_FILE" ]]; do
        if [[ APPCENTER_TIMEOUT -gt 60 ]]; then
            echo "ERROR: joinscript did not write $APP_PROVISIONING_CONFIG_FILE"
            exit 1
        fi
        # Currently the best way to wait for the appcenter to configure the container
        echo "waiting for joinscript to create $APP_PROVISIONING_CONFIG_FILE"
        sleep 1
        ((APPCENTER_TIMEOUT++))
    done
    echo "Starting connector."
    /venv/bin/connector
fi
