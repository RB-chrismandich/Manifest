#!/usr/bin/env bats
# T4.5 (spec 674) — verify_plugin_cache_after_restore's three outcomes.
#
# The function shipped with no coverage, and its interesting behaviour is the
# distinction between "checked, all resolve" and "could not check". Both print
# nothing about missing bundles, both return 0, and only one of them is fine.

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."

setup() {
    SANDBOX="$(mktemp -d "${BATS_TMPDIR:-/tmp}/pcr.XXXXXX")"
    mkdir -p "$SANDBOX/target/plugins"
    STATE="$SANDBOX/target/plugins/installed_plugins.json"
}

teardown() {
    [[ -n "${SANDBOX:-}" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"
    return 0
}

# The function lives in deploy.sh, which needs the print_* family and
# command_exists. Stub them so the assertion is about THIS function.
run_verify() {
    run bash -c "
        print_warning() { echo \"WARN: \$*\"; }
        print_info() { :; }; print_error() { echo \"ERR: \$*\"; }; print_success() { :; }
        command_exists() { command -v \"\$1\" >/dev/null 2>&1; }
        SCRIPT_DIR='$REPO_ROOT'
        source '$REPO_ROOT/bootstrap/lib/deploy.sh' 2>/dev/null || true
        verify_plugin_cache_after_restore '$SANDBOX/target'"
}

@test "a bundle whose install path is gone is named, with the command to restore it" {
    printf '{"plugins":{"manifest-docs@manifest":[{"installPath":"%s/gone"}]}}\n' \
        "$SANDBOX" > "$STATE"
    run_verify
    assert_output --partial "no longer resolve"
    assert_output --partial "manifest-docs@manifest"
    assert_output --partial "claude plugin install"
    [ "$status" -eq 0 ]
}

@test "a bundle that still resolves produces no warning" {
    mkdir -p "$SANDBOX/here"
    printf '{"plugins":{"manifest-docs@manifest":[{"installPath":"%s/here"}]}}\n' \
        "$SANDBOX" > "$STATE"
    run_verify
    refute_output --partial "no longer resolve"
    [ "$status" -eq 0 ]
}

@test "an unreadable state file is reported as UNKNOWN, not as clean" {
    # The bug this closes: the helper returned an empty list on malformed JSON
    # and the caller's `|| true` collapsed exit 3 into exit 0, so a corrupt
    # plugins state after a restore printed exactly what a healthy one printed.
    printf '{not json\n' > "$STATE"
    run_verify
    assert_output --partial "UNKNOWN"
    [ "$status" -eq 0 ]
}

@test "the check never fails the deploy, whatever it finds" {
    # It runs after the user's live directory has already been moved into a
    # backup. Aborting there is the worst possible moment to stop.
    printf '{not json\n' > "$STATE"
    run_verify
    [ "$status" -eq 0 ]
    printf '{"plugins":{"x@m":[{"installPath":"%s/gone"}]}}\n' "$SANDBOX" > "$STATE"
    run_verify
    [ "$status" -eq 0 ]
}

@test "an absent state file is a no-op, not an UNKNOWN" {
    # A machine with no plugins installed is not a machine whose plugin state
    # could not be read. Reporting UNKNOWN there would be noise on every deploy.
    rm -f "$STATE"
    run_verify
    refute_output --partial "UNKNOWN"
    [ "$status" -eq 0 ]
}
