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

  # Source the script under test without executing side effects
  # BATS_TEST_DIRNAME points to this test file's directory
  source "$BATS_TEST_DIRNAME/../preinst"
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
