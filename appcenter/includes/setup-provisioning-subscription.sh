#!/usr/bin/env bash

setup_provisioning_subscriptions() {
    local subscription_name="${SUBSCRIPTION_NAME:-kelvin-connector}"
    local app_provisioning_config_file="${APP_PROVISIONING_CONFIG_FILE:-/var/lib/univention-appcenter/apps/ucsschool-kelvin-rest-api/conf/provisioning/provisioning_config.json}"
    local force="${FORCE:-false}"

    mkdir --parent "$(dirname "$app_provisioning_config_file")"

    if [ "$(ucr get "server/role")" != "domaincontroller_master" ]; then
        echo "Not running on primary, skipping provisioning setup."
        return 0
    fi

    if [[ "$force" != "true" ]] && [ -f "$app_provisioning_config_file" ]; then
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
    {"realm": "udm", "topic": "users/user"},
    {"realm": "udm", "topic": "groups/group"}
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
