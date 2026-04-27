setup_provisioning_subscriptions() {
    local SUBSCRIPTION_NAME="${SUBSCRIPTION_NAME:-kelvin-connector}"
    local APP_PROVISIONING_CONFIG_FILE="${APP_PROVISIONING_CONFIG_FILE:-/var/lib/univention-appcenter/apps/ucsschool-kelvin-rest-api/conf/provisioning_config.json}"
    local FORCE="${FORCE:-false}"

    if [[ -d "$APP_PROVISIONING_CONFIG_FILE" ]]; then
        # docker creates a dir because the file doesn't exist yet
        rmdir "$APP_PROVISIONING_CONFIG_FILE"
    fi

    if [ "$(ucr get "server/role")" != "domaincontroller_master" ]; then
        echo "Not running on primary, skipping provisioning setup."
        return 0
    fi

    if [[ "$FORCE" != "true" ]] && [ -f "$APP_PROVISIONING_CONFIG_FILE" ]; then
        echo "$APP_PROVISIONING_CONFIG_FILE already exists, skipping provisioning setup."
        return 0
    fi

    local FQDN
    FQDN=$(ucr get ldap/master)
    local BASE_URL="https://$FQDN/univention/provisioning"
    local USERNAME="admin"
    local ADMIN_PASSWORD
    ADMIN_PASSWORD=$(python3 <<'EOF'
import json
with open("/etc/provisioning-secrets.json", "r") as f:
    print(json.load(f)["PROVISIONING_API_ADMIN_PASSWORD"])
EOF
)
    local SUBSCRIPTION_PASSWORD
    SUBSCRIPTION_PASSWORD=$(openssl rand -hex 32)
    local DATA
    # Order of realms_topics is important, this ensures we get ou's first
    DATA="$(cat <<EOF
{
  "name": "$SUBSCRIPTION_NAME",
  "realms_topics": [
    {"realm": "udm", "topic": "container/ou"},
    {"realm": "udm", "topic": "users/user"},
    {"realm": "udm", "topic": "groups/group"}
  ],
  "request_prefill": true,
  "password": "${SUBSCRIPTION_PASSWORD}"
}
EOF
)"

    curl --config <(cat <<EOF
user = "$USERNAME:$ADMIN_PASSWORD"
--silent
--fail-with-body
stderr = -
request = "DELETE"
header = "Accept: application/json"
header = "Content-Type: application/json"
url = "$BASE_URL/v1/subscriptions/$SUBSCRIPTION_NAME"
EOF
) || true  # ignore 404 when subscription doesn't exist yet

    local response_create
    response_create=$(curl --data "$DATA" \
        --config <(cat <<EOF
user = "$USERNAME:$ADMIN_PASSWORD"
--silent
--fail-with-body
stderr = -
request = "POST"
header = "Accept: application/json"
header = "Content-Type: application/json"
url = "$BASE_URL/v1/subscriptions"
EOF
))
    if [ $? -ne 0 ]; then
        echo "Error: Request to create subscription failed with: $response_create"
        return 1
    fi

    touch "$APP_PROVISIONING_CONFIG_FILE"
    chmod 640 "$APP_PROVISIONING_CONFIG_FILE"

    cat <<EOF > "$APP_PROVISIONING_CONFIG_FILE"
{
    "subscription_name": "$SUBSCRIPTION_NAME",
    "subscription_password": "$SUBSCRIPTION_PASSWORD"
}
EOF
}
