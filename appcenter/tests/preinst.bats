#!/usr/bin/env bats

setup() {
  # Mock bin directory placed in front of PATH
  export MOCK_BIN="appcenter/tests/mocks"
  export PATH="$MOCK_BIN:$PATH"

  # Temporary log for mocked command calls
  export MOCK_CALLS="$BATS_TEST_TMPDIR/calls.log"
  : > "$MOCK_CALLS"

  # Simple store file for mocked UCR params key
  export MOCK_UCR_STORE="$BATS_TEST_TMPDIR/ucr_params.store"
  : > "$MOCK_UCR_STORE"

  export DOCKER_BIP_KEY="docker/daemon/default/opts/bip"
  export DOCKER_PARAMS_KEY="appcenter/apps/ucsschool-kelvin-rest-api/docker/params"

  # The provisioning-version check imports univention.appcenter.app.LooseVersion,
  # which only exists on a UCS docker host. Put a faithful stub on PYTHONPATH.
  export PYTHONPATH="$BATS_TEST_DIRNAME/stubs${PYTHONPATH:+:$PYTHONPATH}"

  # Controls what the mocked `univention-ldapsearch` emits (default: nothing).
  export MOCK_LDAP_OUTPUT=""

  # Source the script under test without executing side effects
  # BATS_TEST_DIRNAME points to this test file's directory
  source "$BATS_TEST_DIRNAME/../preinst"
}

# Emit an LDIF-ish block as `univention-ldapsearch -LLL ... univentionAppVersion`
# would for the given provisioning-service versions (one arg per installed
# server object).
ldap_output_for_versions() {
  local out="" v
  for v in "$@"; do
    out+="univentionAppVersion: ${v}"$'\n'
  done
  printf '%s' "$out"
}

@test "set_kelvin_docker_env_trusted_proxy_ips sets when params empty" {
  # pre conditions
  ucr set "$DOCKER_BIP_KEY=172.17.0.1/16"

  # call the SUT
  run set_kelvin_docker_env_trusted_proxy_ips
  [ "$status" -eq 0 ]

  # Verify the value was set as expected
  STORE_VAL=$(ucr get $DOCKER_PARAMS_KEY)
  [ "$STORE_VAL" = "--env TRUSTED_PROXY_IPS=172.17.0.1" ]

  # Verify calls were made to ucr get (param + bip) and ucr set
  grep -q "^ucr get appcenter/apps/ucsschool-kelvin-rest-api/docker/params$" "$MOCK_CALLS"
  grep -q "^ucr get docker/daemon/default/opts/bip$" "$MOCK_CALLS"
  grep -q "^ucr set appcenter/apps/ucsschool-kelvin-rest-api/docker/params=--env TRUSTED_PROXY_IPS=172.17.0.1$" "$MOCK_CALLS"
}

@test "set_kelvin_docker_env_trusted_proxy_ips appends when other params exist" {
  # pre conditions
  ucr set "$DOCKER_BIP_KEY=10.0.0.1/24"
  ucr set "$DOCKER_PARAMS_KEY=\"--env FOO=bar\""

  # call the SUT
  run set_kelvin_docker_env_trusted_proxy_ips
  [ "$status" -eq 0 ]

  # Existing params + space + new env
  STORE_VAL=$(ucr get $DOCKER_PARAMS_KEY)
  [ "$STORE_VAL" = "--env FOO=bar --env TRUSTED_PROXY_IPS=10.0.0.1" ]

  grep -q "^ucr set appcenter/apps/ucsschool-kelvin-rest-api/docker/params=--env FOO=bar --env TRUSTED_PROXY_IPS=10.0.0.1$" "$MOCK_CALLS"
}

@test "set_kelvin_docker_env_trusted_proxy_ips is idempotent when already present" {
  # pre conditions
  ucr set "$DOCKER_BIP_KEY=10.0.0.1/24"
  ucr set "$DOCKER_PARAMS_KEY=\"--env TRUSTED_PROXY_IPS=1.2.3.4\""

  # Clear previous call log
  : > "$MOCK_CALLS"

  # call the SUT
  run set_kelvin_docker_env_trusted_proxy_ips
  [ "$status" -eq 0 ]

  # No change expected
  STORE_VAL=$(ucr get $DOCKER_PARAMS_KEY)
  [ "$STORE_VAL" = "--env TRUSTED_PROXY_IPS=1.2.3.4" ]

  # Ensure no `ucr set` call occurred
  if grep -q "^ucr set " "$MOCK_CALLS"; then
    echo "Unexpected ucr set call found" >&2
    false
  fi
}

@test "check_provisioning_service_version: not installed -> returns 1" {
  export MOCK_LDAP_OUTPUT=""

  run check_provisioning_service_version
  [ "$status" -eq 1 ]

  # The domain-installed check must use the exact appcenter LDAP filter.
  grep -q "univentionObjectType=appcenter/app" "$MOCK_CALLS"
  grep -q "univentionAppID=provisioning-service_\*" "$MOCK_CALLS"
  grep -q "univentionAppInstalledOnServer=\*" "$MOCK_CALLS"
}

@test "check_provisioning_service_version: exactly the minimum -> returns 0" {
  export MOCK_LDAP_OUTPUT="$(ldap_output_for_versions 2.2)"

  run check_provisioning_service_version
  [ "$status" -eq 0 ]
}

@test "check_provisioning_service_version: only an older version -> returns 2" {
  export MOCK_LDAP_OUTPUT="$(ldap_output_for_versions 2.1)"

  run check_provisioning_service_version
  [ "$status" -eq 2 ]
}

@test "check_provisioning_service_version: 2.10 beats 2.2 (numeric, not lexical) -> returns 0" {
  export MOCK_LDAP_OUTPUT="$(ldap_output_for_versions 2.10)"

  run check_provisioning_service_version
  [ "$status" -eq 0 ]
}

@test "check_provisioning_service_version: newer major -> returns 0" {
  export MOCK_LDAP_OUTPUT="$(ldap_output_for_versions 3.0)"

  run check_provisioning_service_version
  [ "$status" -eq 0 ]
}

@test "check_provisioning_service_version: several servers, one recent enough -> returns 0" {
  export MOCK_LDAP_OUTPUT="$(ldap_output_for_versions 2.1 2.3)"

  run check_provisioning_service_version
  [ "$status" -eq 0 ]
}

@test "check_provisioning_service_version: several servers, all too old -> returns 2" {
  export MOCK_LDAP_OUTPUT="$(ldap_output_for_versions 2.0 2.1)"

  run check_provisioning_service_version
  [ "$status" -eq 2 ]
}

@test "check_provisioning_service_version: honours an explicit minimum argument" {
  export MOCK_LDAP_OUTPUT="$(ldap_output_for_versions 2.5)"

  run check_provisioning_service_version 3.0
  [ "$status" -eq 2 ]

  run check_provisioning_service_version 2.4
  [ "$status" -eq 0 ]
}

@test "check_provisioning_service_version: default minimum is 2.2" {
  [ "$MIN_PROVISIONING_VERSION" = "2.2" ]
}
