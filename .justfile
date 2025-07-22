vm_conf_dir := "dev/_vm_config"

[private]
default:
  just --list

# Fetches necessary information from a UCS host, to use its UDM REST API for a local Kelvin instance
fetch-vm-data target:
    #!/usr/bin/env bash
    mkdir -p {{vm_conf_dir}}
    echo "dev" > {{vm_conf_dir}}/tokens.secret
    scp {{target}}:/etc/machine.secret {{vm_conf_dir}}/
    scp {{target}}:/etc/ldap.secret {{vm_conf_dir}}/
    scp {{target}}:/etc/ssl/certs/ca-certificates.crt {{vm_conf_dir}}/
    scp {{target}}:/etc/univention/base.conf {{vm_conf_dir}}/
    echo "LDAP_MASTER=$(ssh {{target}} ucr get ldap/master)" > {{vm_conf_dir}}/env
    echo "LDAP_BASE=$(ssh {{target}} ucr get ldap/base)" >> {{vm_conf_dir}}/env
    echo "LDAP_MASTER_PORT=$(ssh {{target}} ucr get ldap/master/port)" >> {{vm_conf_dir}}/env
    echo "LDAP_HOSTDN=$(ssh {{target}} ucr get ldap/hostdn)" >> {{vm_conf_dir}}/env
    echo "LDAP_SERVER_NAME=$(ssh {{target}} ucr get ldap/server/name)" >> {{vm_conf_dir}}/env
    echo "LDAP_SERVER_PORT=$(ssh {{target}} ucr get ldap/server/port)" >> {{vm_conf_dir}}/env
    echo "HOSTNAME=$(ssh {{target}} ucr get hostname)" >> {{vm_conf_dir}}/env
    echo "TARGET={{target}}" >> {{vm_conf_dir}}/env

# Builds the Kelvin docker image
build-docker-image:
    docker build --network host -t ucsschool-kelvin-rest-api:dev -f docker/Dockerfile .

# Starts a local instance of the Kelvin image.
# Access via http://127.0.0.1:8911/ucsschool/kelvin/v1/docs
dev-server: build-docker-image
    #!/usr/bin/env bash
    source {{vm_conf_dir}}/env
    docker run --rm --network host -ti \
      -v "$(pwd)/kelvin-api/:/kelvin/kelvin-api" \
      -v "$(pwd)/{{vm_conf_dir}}/machine.secret":/etc/machine.secret:ro \
      -v "$(pwd)/{{vm_conf_dir}}/ldap.secret":/var/lib/univention-appcenter/apps/ucsschool-kelvin-rest-api/conf/cn_admin.secret:ro \
      -v "$(pwd)/{{vm_conf_dir}}/ca-certificates.crt":/etc/ssl/certs/ca-certificates.crt:ro \
      -v "$(pwd)/{{vm_conf_dir}}/tokens.secret":/var/lib/univention-appcenter/apps/ucsschool-kelvin-rest-api/conf/tokens.secret:ro \
      -v "$(pwd)/{{vm_conf_dir}}/base.conf":/etc/univention/base.conf:ro \
      --env-file {{vm_conf_dir}}/env \
      --add-host="$LDAP_MASTER":"$TARGET" \
      --hostname "$HOSTNAME" \
      ucsschool-kelvin-rest-api:dev