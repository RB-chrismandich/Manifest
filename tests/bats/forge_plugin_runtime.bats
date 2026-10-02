#!/usr/bin/env bats

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
BUNDLE="$REPO_ROOT/plugins/manifest-forge"

setup() {
    SANDBOX="$(mktemp -d "${BATS_TMPDIR:-/tmp}/forge-runtime.XXXXXX")"
    export HOME="$SANDBOX/home"
    export XDG_STATE_HOME="$SANDBOX/state"
    export XDG_CONFIG_HOME="$SANDBOX/config"
    export XDG_DATA_HOME="$SANDBOX/data"
    mkdir -p "$HOME" "$XDG_STATE_HOME" "$XDG_CONFIG_HOME" "$XDG_DATA_HOME" "$SANDBOX/bin"

    for command in git gh glab curl; do
        printf '#!/bin/sh\nprintf "%%s\\n" "$0 $*" >> "$FORGE_CALLS"\nexit "${FORGE_STUB_EXIT:-0}"\n' > "$SANDBOX/bin/$command"
        chmod +x "$SANDBOX/bin/$command"
    done
    ln -s "$(command -v bash)" "$SANDBOX/bin/bash"
    ln -s "$(command -v python3)" "$SANDBOX/bin/python3"
    ln -s "$(command -v dirname)" "$SANDBOX/bin/dirname"
    export FORGE_CALLS="$SANDBOX/calls"
    export PATH="$SANDBOX/bin:/usr/bin:/bin"
}

teardown() {
    [[ -n "${SANDBOX:-}" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"
    return 0
}

@test "forge commands run from their bundle under empty home and XDG roots" {
    cd "$SANDBOX"

    run "$BUNDLE/runtime/bin/tracker_ops.sh" resolve-provider
    assert_success
    assert_output "github"

    token="ghp_$(printf 'a%.0s' {1..32})"
    run "$BUNDLE/runtime/bin/audit_log.sh" append "{\"token\":\"$token\"}"
    assert_success
    [ -f "$XDG_STATE_HOME/manifest/forge/audit.jsonl" ]
    refute grep -q 'ghp_' "$XDG_STATE_HOME/manifest/forge/audit.jsonl"

    run "$BUNDLE/runtime/bin/lifecycle.sh" --help
    assert_success
    assert_output --partial "decide"
}

@test "forge runtime invokes fake external commands with argv and propagates failures" {
    mkdir -p "$SANDBOX/repo"
    cd "$SANDBOX/repo"
    export MANIFEST_GIT_PLATFORM=github

    run "$BUNDLE/runtime/bin/git_ops.sh" issue-view 42 --comments
    assert_success
    grep -q 'gh issue view 42 --comments' "$FORGE_CALLS"

    export FORGE_STUB_EXIT=23
    run "$BUNDLE/runtime/bin/git_ops.sh" issue-list
    assert_equal "$status" 23
}

@test "forge ignores hostile same-bundle command overrides" {
    printf '#!/bin/sh\ntouch "%s"\nexit 0\n' "$SANDBOX/hostile-called" > "$SANDBOX/hostile"
    chmod +x "$SANDBOX/hostile"
    export GIT_OPS_BIN="$SANDBOX/hostile"
    export MANIFEST_GIT_PLATFORM=github
    export MANIFEST_TRACKER=github
    export FORGE_STUB_EXIT=23

    run "$BUNDLE/runtime/bin/tracker_ops.sh" issue-list
    assert_equal "$status" 23
    [ ! -e "$SANDBOX/hostile-called" ]
}

@test "lifecycle rejects traversal without touching files outside XDG state" {
    printf 'sentinel\n' > "$SANDBOX/outside.json"

    run "$BUNDLE/runtime/bin/lifecycle.sh" status ../../outside --json
    assert_failure
    assert_output --partial "invalid track id"
    assert_equal "$(cat "$SANDBOX/outside.json")" "sentinel"
    [ ! -e "$XDG_STATE_HOME/manifest/outside.json" ]
}

@test "forge runtime never reads credential homes or persists credentials" {
    mkdir -p "$HOME/.config/gh" "$HOME/.config/glab-cli" "$HOME/.claude"
    printf 'DO-NOT-TOUCH' > "$HOME/.config/gh/hosts.yml"
    printf 'DO-NOT-TOUCH' > "$HOME/.config/glab-cli/config.yml"
    printf 'DO-NOT-TOUCH' > "$HOME/.claude/settings.json"

    run "$BUNDLE/runtime/bin/tracker_ops.sh" --help
    assert_success
    run "$BUNDLE/runtime/bin/pr_review.sh" --help
    assert_success

    run grep -R -n 'DO-NOT-TOUCH' "$XDG_STATE_HOME" "$XDG_CONFIG_HOME" "$XDG_DATA_HOME"
    assert_failure
    assert_equal "$(cat "$HOME/.config/gh/hosts.yml")" "DO-NOT-TOUCH"
    assert_equal "$(cat "$HOME/.config/glab-cli/config.yml")" "DO-NOT-TOUCH"
    assert_equal "$(cat "$HOME/.claude/settings.json")" "DO-NOT-TOUCH"
}
