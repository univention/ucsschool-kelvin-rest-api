#!/usr/bin/env bash

if [ "$LDAP_SERVER_TYPE" != "master" ]; then
    echo "Kelvin connector will only run on server type master (LDAP_SERVER_TYPE=\"$LDAP_SERVER_TYPE\")"
    sleep inf
else
    echo "Starting connector."
    /venv/bin/connector
fi
