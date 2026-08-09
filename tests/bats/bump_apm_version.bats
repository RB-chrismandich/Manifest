#!/usr/bin/env bats
# Coverage for configs/claude/scripts/bump_apm_version.sh: patch/minor/major
# increment correctness and loud failure on malformed input.

setup() {
    load '../test_helper/bats-support/load'
    load '../test_helper/bats-assert/load'
    SCRIPT="${BATS_TEST_DIRNAME}/../../configs/claude/scripts/bump_apm_version.sh"
    TMPDIR_TEST="$(mktemp -d)"
    APM_FILE="${TMPDIR_TEST}/apm.yml"
}

teardown() {
    rm -rf "${TMPDIR_TEST}"
}

write_apm() {
    cat > "$APM_FILE" <<EOF
name: manifest-skills
version: $1
description: test
EOF
}

@test "bump_apm_version.sh --help exits 0" {
    run "$SCRIPT" --help
    assert_success
    assert_output --partial "Usage:"
}

@test "defaults to patch bump" {
    write_apm "1.2.3"
    run "$SCRIPT" --file "$APM_FILE"
    assert_success
    assert_output "1.2.4"
    run grep '^version: ' "$APM_FILE"
    assert_output "version: 1.2.4"
}

@test "minor bump resets patch" {
    write_apm "1.2.3"
    run "$SCRIPT" minor --file "$APM_FILE"
    assert_success
    assert_output "1.3.0"
}

@test "major bump resets minor and patch" {
    write_apm "1.2.3"
    run "$SCRIPT" major --file "$APM_FILE"
    assert_success
    assert_output "2.0.0"
}

@test "--print does not mutate the file" {
    write_apm "0.1.0"
    run "$SCRIPT" --print --file "$APM_FILE"
    assert_success
    assert_output "0.1.1"
    run grep '^version: ' "$APM_FILE"
    assert_output "version: 0.1.0"
}

@test "preserves surrounding file content" {
    write_apm "1.0.0"
    run "$SCRIPT" --file "$APM_FILE"
    assert_success
    run cat "$APM_FILE"
    assert_line "name: manifest-skills"
    assert_line "version: 1.0.1"
    assert_line "description: test"
}

@test "fails loudly when version line is missing" {
    cat > "$APM_FILE" <<EOF
name: manifest-skills
description: test
EOF
    run "$SCRIPT" --file "$APM_FILE"
    assert_failure
    assert_output --partial "no top-level 'version:' line found"
}

@test "fails loudly on unparseable version" {
    write_apm "not-a-semver"
    run "$SCRIPT" --file "$APM_FILE"
    assert_failure
    assert_output --partial "unparseable version"
}

@test "fails on missing file" {
    run "$SCRIPT" --file "${TMPDIR_TEST}/does-not-exist.yml"
    assert_failure
    assert_output --partial "no such file"
}

@test "rejects unrecognized argument" {
    write_apm "1.0.0"
    run "$SCRIPT" --file "$APM_FILE" --bogus
    assert_failure
    assert_output --partial "unrecognized argument"
}
