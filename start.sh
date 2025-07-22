#!/usr/bin/env bash

target=$1
mkdir -p _config
echo "dev" > _config/tokens.secret
scp "$target":/etc/machine.secret _config/
scp "$target":/etc/ldap.secret _config/
scp "$target":/etc/ssl/certs/ca-certificates.crt _config/
scp "$target":/etc/univention/base.conf _config/
LDAP_MASTER="$(ssh "$target" ucr get ldap/master)"
LDAP_BASE="$(ssh "$target" ucr get ldap/base)"
LDAP_MASTER_PORT="$(ssh "$target" ucr get ldap/master/port)"
LDAP_HOSTDN="$(ssh "$target" ucr get ldap/hostdn)"
LDAP_SERVER_NAME="$(ssh "$target" ucr get ldap/server/name)"
LDAP_SERVER_PORT="$(ssh "$target" ucr get ldap/server/port)"
HOSTNAME="$(ssh "$target" ucr get hostname)"
echo "use 127.0.0.1; localhost doesn't work for some calls"
docker run \
    -v "$(pwd)/kelvin-api/:/kelvin/kelvin-api" \
    -v "$(pwd)/_config/machine.secret":/etc/machine.secret:ro \
    -v "$(pwd)/_config/ldap.secret":/var/lib/univention-appcenter/apps/ucsschool-kelvin-rest-api/conf/cn_admin.secret:ro \
    -v "$(pwd)/_config/ca-certificates.crt":/etc/ssl/certs/ca-certificates.crt:ro \
    -v "$(pwd)/_config/tokens.secret":/var/lib/univention-appcenter/apps/ucsschool-kelvin-rest-api/conf/tokens.secret:ro \
    -v "$(pwd)/_config/base.conf":/etc/univention/base.conf:ro \
    --add-host="$LDAP_MASTER":"$target" \
    --env LDAP_MASTER="$LDAP_MASTER" \
    --env LDAP_BASE="$LDAP_BASE" \
    --env LDAP_MASTER_PORT="$LDAP_MASTER_PORT" \
    --env LDAP_HOSTDN="$LDAP_HOSTDN" \
    --env LDAP_SERVER_NAME="$LDAP_SERVER_NAME" \
    --env LDAP_SERVER_PORT="$LDAP_SERVER_PORT" \
    --env DOCKER_HOST_NAME="$LDAP_MASTER" \
    --env SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
    --hostname "$HOSTNAME" \
    --rm --network host -ti kelvin-dev --reload
