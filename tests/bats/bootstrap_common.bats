#!/usr/bin/env bats
# Tests for bootstrap/lib/common.sh — shared output/prompt/symlink helpers
# (currently only transitively covered via bootstrap.sh).

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

COMMON_LIB="$BATS_TEST_DIRNAME/../../bootstrap/lib/common.sh"

setup() {
    # Isolate the APM domain registry — this suite drives a writer that stands
    # down for an APM-owned domain, so without this it reads the developer's
    # live registry instead of a fixture (see apm_test_isolation_guard.bats).
    export MANIFEST_APM_DOMAINS="$BATS_TEST_TMPDIR/no-apm-domains.yml"
    printf 'domains: []\n' > "$MANIFEST_APM_DOMAINS"

    export BATS_TMPDIR="${BATS_TMPDIR:-/tmp}"
    TEST_DIR=$(mktemp -d "$BATS_TMPDIR/common_test.XXXXXX")
}

teardown() {
    rm -rf "$TEST_DIR"
}

# Source the lib inside a fresh bash with the color vars it interpolates
# defined (empty is fine — we only assert on the message text).
run_in_harness() {
    bash -c "
        set -u
        RED='' GREEN='' BLUE='' YELLOW='' CYAN='' BOLD='' NC=''
        source '$COMMON_LIB'
        $1
    "
}

@test "print_step/print_success/print_warning/print_error/print_info emit the message" {
    run run_in_harness '
        print_step "stepping"
        print_success "succeeded"
        print_warning "warned"
        print_error "errored"
        print_info "informed"
    '
    assert_success
    assert_output --partial "stepping"
    assert_output --partial "succeeded"
    assert_output --partial "warned"
    assert_output --partial "errored"
    assert_output --partial "informed"
}

@test "prompt_yes_no accepts empty input as the default (y)" {
    run bash -c "
        RED='' GREEN='' BLUE='' YELLOW='' CYAN='' BOLD='' NC=''
        source '$COMMON_LIB'
        prompt_yes_no 'Continue?' && echo YES || echo NO
    " <<< ""
    assert_success
    assert_output --partial "YES"
}

@test "prompt_yes_no rejects explicit 'n' even when default is y" {
    run bash -c "
        RED='' GREEN='' BLUE='' YELLOW='' CYAN='' BOLD='' NC=''
        source '$COMMON_LIB'
        prompt_yes_no 'Continue?' && echo YES || echo NO
    " <<< "n"
    assert_success
    assert_output --partial "NO"
}

@test "prompt_yes_no accepts 'yes' explicitly" {
    run bash -c "
        RED='' GREEN='' BLUE='' YELLOW='' CYAN='' BOLD='' NC=''
        source '$COMMON_LIB'
        prompt_yes_no 'Continue?' 'n' && echo YES || echo NO
    " <<< "yes"
    assert_success
    assert_output --partial "YES"
}

@test "command_exists is true for a command on PATH and false otherwise" {
    run run_in_harness '
        command_exists bash && echo "bash-found"
        command_exists definitely_not_a_real_command_xyz || echo "missing-not-found"
    '
    assert_success
    assert_output --partial "bash-found"
    assert_output --partial "missing-not-found"
}

@test "create_symlink skips with a warning when the target does not exist" {
    run run_in_harness "
        create_symlink '$TEST_DIR/link' '$TEST_DIR/does-not-exist' 'thing'
        echo \"exit=\$?\"
    "
    assert_success
    assert_output --partial "Symlink target not found"
    assert_output --partial "exit=0"
    [[ ! -e "$TEST_DIR/link" ]]
}

@test "create_symlink creates a symlink pointing at the target" {
    mkdir -p "$TEST_DIR/target"
    run run_in_harness "
        create_symlink '$TEST_DIR/link' '$TEST_DIR/target' 'thing'
    "
    assert_success
    [[ -L "$TEST_DIR/link" ]] || return 1
    [[ "$(readlink "$TEST_DIR/link")" == "$TEST_DIR/target" ]]
}

@test "create_symlink backs up a real (non-symlink) path instead of destroying it" {
    mkdir -p "$TEST_DIR/target"
    mkdir -p "$TEST_DIR/link"
    echo "user data" > "$TEST_DIR/link/important.txt"
    run run_in_harness "
        create_symlink '$TEST_DIR/link' '$TEST_DIR/target' 'thing'
    "
    assert_success
    assert_output --partial "backing up"
    [[ -L "$TEST_DIR/link" ]] || return 1
    backup_dir=$(find "$TEST_DIR" -maxdepth 1 -name 'link.backup.*')
    [[ -n "$backup_dir" ]] || return 1
    [[ -f "$backup_dir/important.txt" ]]
}

@test "link_shared_assets creates the expected symlinks and honors exclude list" {
    mkdir -p "$TEST_DIR/home/scripts" "$TEST_DIR/home/config" "$TEST_DIR/home/prompts" "$TEST_DIR/home/.plans" "$TEST_DIR/home/skills"
    mkdir -p "$TEST_DIR/dest"
    run run_in_harness "
        TARGET_DIR='$TEST_DIR/home'
        link_shared_assets '$TEST_DIR/dest' 'Config' true 'scripts prompts'
    "
    assert_success
    [[ ! -e "$TEST_DIR/dest/scripts" ]] || return 1
    [[ ! -e "$TEST_DIR/dest/prompts" ]] || return 1
    [[ -L "$TEST_DIR/dest/config" ]] || return 1
    [[ -L "$TEST_DIR/dest/.plans" ]] || return 1
    [[ -L "$TEST_DIR/dest/skills" ]]
}

@test "deploy_home_skills copies skill directories from source to dest" {
    mkdir -p "$TEST_DIR/src/skill-a" "$TEST_DIR/src/skill-b"
    echo "a" > "$TEST_DIR/src/skill-a/SKILL.md"
    echo "b" > "$TEST_DIR/src/skill-b/SKILL.md"
    run run_in_harness "
        deploy_home_skills '$TEST_DIR/src' '$TEST_DIR/dest'
    "
    assert_success
    [[ -f "$TEST_DIR/dest/skill-a/SKILL.md" ]] || return 1
    [[ -f "$TEST_DIR/dest/skill-b/SKILL.md" ]] || return 1
    [[ -f "$TEST_DIR/dest/.deployed-skills" ]] || return 1
    grep -q "skill-a" "$TEST_DIR/dest/.deployed-skills"
    grep -q "skill-b" "$TEST_DIR/dest/.deployed-skills"
}

@test "deploy_home_skills prunes a skill removed from source but present in the prior manifest" {
    mkdir -p "$TEST_DIR/src/skill-a"
    echo "a" > "$TEST_DIR/src/skill-a/SKILL.md"
    mkdir -p "$TEST_DIR/dest/skill-a" "$TEST_DIR/dest/skill-stale"
    printf 'skill-a\nskill-stale\n' > "$TEST_DIR/dest/.deployed-skills"

    run run_in_harness "
        deploy_home_skills '$TEST_DIR/src' '$TEST_DIR/dest'
    "
    assert_success
    assert_output --partial "Pruned removed skill: skill-stale"
    [[ -d "$TEST_DIR/dest/skill-a" ]] || return 1
    [[ ! -d "$TEST_DIR/dest/skill-stale" ]]
}

@test "deploy_home_skills refuses to mass-prune when source is empty" {
    mkdir -p "$TEST_DIR/src"
    mkdir -p "$TEST_DIR/dest/skill-stale"
    printf 'skill-stale\n' > "$TEST_DIR/dest/.deployed-skills"

    run run_in_harness "
        deploy_home_skills '$TEST_DIR/src' '$TEST_DIR/dest'
    "
    assert_success
    refute_output --partial "Pruned removed skill"
    [[ -d "$TEST_DIR/dest/skill-stale" ]]
}
