#!/usr/bin/env bash

# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

setup_provisioning_subscriptions() {
    local subscription_name="${SUBSCRIPTION_NAME:-kelvin-connector}"
    local app_provisioning_config_file="${APP_PROVISIONING_CONFIG_FILE:-/var/lib/univention-appcenter/apps/ucsschool-kelvin-rest-api/conf/provisioning/provisioning_config.json}"
    local force="${FORCE:-false}"

    mkdir --parent "$(dirname "$app_provisioning_config_file")"

    if [[ "$(ucr get "server/role")" != "domaincontroller_master" ]]; then
        echo "Not running on primary, skipping provisioning setup."
        return 0
    fi

    if [[ "$force" != "true" ]] && [[ -f "$app_provisioning_config_file" ]]; then
        echo "$app_provisioning_config_file already exists, skipping provisioning setup."
        return 0
    fi

    local fqdn
    fqdn=$(ucr get ldap/master)
    local base_url="https://$fqdn/univention/provisioning"
    local username="admin"
    local admin_password
    admin_password=$(python3 <<'EOF'
import json
with open("/etc/provisioning-secrets.json", "r") as f:
    print(json.load(f)["PROVISIONING_API_ADMIN_PASSWORD"])
EOF
)
    local subscription_password
    subscription_password=$(openssl rand -hex 32)
    local data
    # Order of realms_topics is important, this ensures we get ou's first
    data="$(cat <<EOF
{
  "name": "$subscription_name",
  "realms_topics": [
    {"realm": "udm", "topic": "container/ou"},
    {"realm": "udm", "topic": "groups/group"},
    {"realm": "udm", "topic": "users/user"}
  ],
  "request_prefill": true,
  "password": "${subscription_password}"
}
EOF
)"

    curl --config <(cat <<EOF
user = "$username:$admin_password"
--silent
--fail-with-body
stderr = -
request = "DELETE"
header = "Accept: application/json"
header = "Content-Type: application/json"
url = "$base_url/v1/subscriptions/$subscription_name"
EOF
) || true  # ignore 404 when subscription doesn't exist yet

    local response_create
    response_create=$(curl --data "$data" \
        --config <(cat <<EOF
user = "$username:$admin_password"
--silent
--fail-with-body
stderr = -
request = "POST"
header = "Accept: application/json"
header = "Content-Type: application/json"
url = "$base_url/v1/subscriptions"
EOF
))
    if [[ $? -ne 0 ]]; then
        echo "Error: Request to create subscription failed with: $response_create"
        return 1
    fi

    touch "$app_provisioning_config_file"
    chmod 640 "$app_provisioning_config_file"

    cat <<EOF > "$app_provisioning_config_file"
{
    "subscription_name": "$subscription_name",
    "subscription_password": "$subscription_password"
}
EOF
}

# The connector container (compose service "provisioning") reads
# PROVISIONING_PASSWORD and DATABASE_URL from this env file. The App Center
# starts the containers before configure_host writes the Kelvin DB credentials
# and before the join script creates the subscription, so the preinst creates
# the file empty and this fills it and recreates the container.
write_connector_env() {
    local env_file="${CONNECTOR_ENV_FILE:-/var/lib/univention-appcenter/apps/ucsschool-kelvin-rest-api/conf/provisioning/connector.env}"
    local app_provisioning_config_file="${APP_PROVISIONING_CONFIG_FILE:-/var/lib/univention-appcenter/apps/ucsschool-kelvin-rest-api/conf/provisioning/provisioning_config.json}"
    local kelvin_config_dir="${KELVIN_CONFIG_DIR:-/etc/ucsschool/kelvin}"
    local compose_dir="${COMPOSE_DIR:-/var/lib/univention-appcenter/apps/$APP_ID/compose}"

    if [[ "$(ucr get "server/role")" != "domaincontroller_master" ]]; then
        echo "Not running on primary, skipping the connector configuration."
        return 0
    fi

    local content
    # The values are written unquoted: the password is hex and the URL is
    # percent-encoded, so neither contains a quote, '$', '#' or whitespace.
    content="$(python3 - "$app_provisioning_config_file" "$kelvin_config_dir" <<'PYEOF'
import json
import sys
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

config_file, kelvin_config_dir = sys.argv[1:]
with open(config_file) as config:
    subscription_password = json.load(config)["subscription_password"]

def read(name):
    with open(f"{kelvin_config_dir}/postgresql-kelvin.{name}") as kelvin_db_file:
        return kelvin_db_file.read().strip()

uri = urlsplit(read("uri"))
# The CCF keeps its tables in the schema "ccf" of the Kelvin DB.
query = urlencode(parse_qsl(uri.query) + [("options", "-csearch_path=ccf")])
netloc = f"{quote(read('username'), safe='')}:{quote(read('secret'), safe='')}@{uri.netloc}"
print(f"PROVISIONING_PASSWORD={subscription_password}")
print(f"DATABASE_URL={urlunsplit(('postgres', netloc, uri.path, query, ''))}")
PYEOF
)" || return 1

    (umask 077 && printf '%s\n' "$content" > "$env_file") || return 1

    # Only the connector: the env file is read when a container is created.
    (cd "$compose_dir" \
        && docker-compose -p "$APP_ID" up -d --no-build --no-deps --force-recreate provisioning)
}
