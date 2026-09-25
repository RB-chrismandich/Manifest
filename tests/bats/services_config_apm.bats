#!/usr/bin/env bats
# Tests for APM toggle plumbing in bootstrap/lib/config.sh

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."

setup() {
    export BATS_TMPDIR="${BATS_TMPDIR:-/tmp}"
    SANDBOX=$(mktemp -d "$BATS_TMPDIR/apm_config.XXXXXX")
    export SERVICES_CONFIG="$SANDBOX/config/services.yml"
    print_step()    { :; }
    print_success() { :; }
    print_info()    { :; }
    print_warning() { :; }
    print_error()   { :; }
    # shellcheck disable=SC1090
    source "$REPO_ROOT/bootstrap/lib/config.sh"
}

teardown() {
    [[ -n "$SANDBOX" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"
}

@test "parse_services_config round-trips apm enabled: true into ENABLE_APM" {
    set_bootstrap_defaults
    export ENABLE_APM=true
    write_services_config
    set_bootstrap_defaults
    load_existing_config
    assert_equal "$ENABLE_APM" "true"
}
