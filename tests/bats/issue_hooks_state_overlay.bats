#!/usr/bin/env bats
# T051/FR-034: installer-written state lives in a file no package owns.
#
# Before this, `install_issue_hooks.sh --enable` edited the DEPLOYED
# command_config.yml — a build output. Any deploy is free to overwrite a build
# output, which is exactly why preserve_issue_sync_gates() had to exist: a
# carry-across hook compensating for state stored in the wrong place. Under
# FR-034's build-output semantics the fix is to stop writing there, not to carry
# the write across more robustly.
#
# What must hold:
#   - --enable/--disable write ~/.manifest/issue_hooks.yml, not the package file
#   - the package file is left byte-identical
#   - the reader prefers the overlay but falls through for keys it lacks, so
#     existing opt-ins recorded the old way keep working
#   - "present but false" is distinguishable from "absent", or a hook could
#     never be turned OFF once the package config said true

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
INSTALLER="$REPO_ROOT/configs/claude/scripts/install_issue_hooks.sh"
SUPPORT="$REPO_ROOT/configs/claude/scripts/issue_support.sh"

setup() {
    export BATS_TMPDIR="${BATS_TMPDIR:-/tmp}"
    SANDBOX="$(mktemp -d "$BATS_TMPDIR/issue_overlay.XXXXXX")"

    export HOME="$SANDBOX/home"
    mkdir -p "$HOME/.claude"
    export ISSUE_HOOKS_STATE="$HOME/.manifest/issue_hooks.yml"
    export ISSUE_HOOKS_SETTINGS="$HOME/.claude/settings.json"
    echo '{}' > "$ISSUE_HOOKS_SETTINGS"

    # A package config with both hooks disabled — the shipped default.
    PKG_CONFIG="$SANDBOX/command_config.yml"
    cat > "$PKG_CONFIG" << 'YML'
tool_policies:
  issue-sync-pr:
    enabled: false
    hook_timeout_seconds: 5
  issue-sync-commit:
    enabled: false
YML
    cp "$PKG_CONFIG" "$SANDBOX/command_config.yml.orig"
    export ISSUE_HOOKS_CONFIG="$PKG_CONFIG"
    export ISSUE_SUPPORT_CONFIG="$PKG_CONFIG"
}

teardown() {
    [[ -n "$SANDBOX" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"
}

# Read one policy value through the REAL resolver.
#
# issue_support.sh dispatches its CLI at the bottom of the file, so sourcing it
# runs `usage` and exits — the same reason bootstrap_reconfigure.bats extracts
# run_reconfigure with awk instead of sourcing bootstrap.sh. Extract the two
# resolver functions and exercise those, so the test covers the shipped code
# rather than a re-implementation of it.
read_cfg() {
    local harness="$SANDBOX/resolver.sh"
    {
        echo 'CONFIG_FILE="$1"; ISSUE_HOOKS_STATE="$2"'
        awk '/^overlay_has\(\) \{/,/^\}/' "$SUPPORT"
        awk '/^cfg_get\(\) \{/,/^\}/' "$SUPPORT"
        echo 'cfg_get "$3" "$4" "$5"'
    } > "$harness"
    bash "$harness" "$PKG_CONFIG" "$ISSUE_HOOKS_STATE" "$1" "$2" "$3"
}

# --- the writer stops touching the package file ------------------------------

@test "--enable writes the user-scope overlay" {
    run "$INSTALLER" --enable
    assert_success
    [ -f "$ISSUE_HOOKS_STATE" ]
    run cat "$ISSUE_HOOKS_STATE"
    assert_output --partial "issue-sync-pr"
}

@test "--enable leaves the deployed package config byte-identical" {
    # The property that retires preserve_issue_sync_gates().
    run "$INSTALLER" --enable
    assert_success
    run diff "$PKG_CONFIG" "$SANDBOX/command_config.yml.orig"
    assert_success
}

@test "the overlay is created outside any package-owned directory" {
    run "$INSTALLER" --enable
    assert_success
    # `|| return 1` is required: a bare non-final [[ ]] silently passes on
    # macOS Bash 3.2, so this assertion would never have been able to fail.
    [[ "$ISSUE_HOOKS_STATE" == "$HOME/.manifest/"* ]] || return 1
    [ ! -e "$HOME/.claude/config/issue_hooks.yml" ]
}

# --- the reader resolves overlay-first, package-second ------------------------

@test "with no overlay, the package config still decides" {
    run read_cfg issue-sync-pr enabled false
    assert_output "false"
}

@test "the overlay overrides the package config" {
    run "$INSTALLER" --enable
    assert_success
    run read_cfg issue-sync-pr enabled false
    assert_output "true"
}

@test "a key the overlay lacks falls through to the package config" {
    # The overlay only carries what the user set. Without fall-through, enabling
    # a hook would blank every other policy value for that skill.
    run "$INSTALLER" --enable
    assert_success
    run read_cfg issue-sync-pr hook_timeout_seconds 99
    assert_output "5"
}

@test "an overlay 'false' beats a package 'true' — absent is not the same as false" {
    # If the reader treated a falsy overlay value as "absent", a hook enabled in
    # the package config could never be turned off by the user.
    cat > "$PKG_CONFIG" << 'YML'
tool_policies:
  issue-sync-pr:
    enabled: true
YML
    mkdir -p "$(dirname "$ISSUE_HOOKS_STATE")"
    cat > "$ISSUE_HOOKS_STATE" << 'YML'
tool_policies:
  issue-sync-pr:
    enabled: false
YML
    run read_cfg issue-sync-pr enabled true
    assert_output "false"
}

@test "an unreadable overlay is not silently overwritten" {
    # It holds the user's other opt-ins; clobbering it on a parse error would
    # discard them without a word.
    mkdir -p "$(dirname "$ISSUE_HOOKS_STATE")"
    printf 'tool_policies: [this: is: not: valid\n' > "$ISSUE_HOOKS_STATE"
    run "$INSTALLER" --enable
    assert_failure
    run cat "$ISSUE_HOOKS_STATE"
    assert_output --partial "not: valid"
}

@test "a missing overlay falls back rather than erroring" {
    rm -rf "$HOME/.manifest"
    run read_cfg issue-sync-commit enabled false
    assert_output "false"
}
