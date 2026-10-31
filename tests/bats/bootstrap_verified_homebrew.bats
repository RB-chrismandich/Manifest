#!/usr/bin/env bats

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

setup() {
    SANDBOX=$(mktemp -d "${BATS_TMPDIR:-/tmp}/manifest_brew_test.XXXXXX")
    export INSTALL_LIB="$BATS_TEST_DIRNAME/../../bootstrap/lib/install.sh"
    export BREW_TEST_FIXTURE="$SANDBOX/fixture.sh"
    export BREW_TEST_MARKER="$SANDBOX/executed"
    export BREW_TEST_PATH="$SANDBOX/installer-path"
    export BREW_TEST_CURL_LOG="$SANDBOX/curl.log"
    export TMPDIR="$SANDBOX/tmp"
    mkdir -p "$SANDBOX/bin" "$TMPDIR"
    cp "$BATS_TEST_DIRNAME/../fixtures/bootstrap/homebrew_installer.sh" "$BREW_TEST_FIXTURE"
    cp "$BATS_TEST_DIRNAME/../fixtures/bootstrap/homebrew_curl.sh" "$SANDBOX/bin/curl"
    chmod +x "$SANDBOX/bin/curl"
    export BREW_TEST_SHA
    BREW_TEST_SHA=$(shasum -a 256 "$BREW_TEST_FIXTURE" | awk '{print $1}')
}

teardown() { rm -rf "$SANDBOX"; }

run_brew() {
    run env PATH="$SANDBOX/bin:/usr/bin:/bin" /bin/bash -c '
        set -eu
        source "$INSTALL_LIB"
        PLATFORM="${BREW_TEST_PLATFORM:-macos}"; PKG_MANAGER=dnf
        print_step() { :; }; print_warning() { echo "$*"; }; print_error() { echo "$*"; }
        print_info() { :; }; print_success() { echo "SUCCESS: $*"; }
        prompt_yes_no() { [[ "${BREW_TEST_CONSENT:-yes}" == yes ]]; }
        command_exists() {
            if [[ "$1" == brew ]]; then [[ "${BREW_TEST_PRESENT:-no}" == yes ]];
            elif [[ "${BREW_TEST_SHASUM:-no}" == yes && "$1" == sha256sum ]]; then return 1;
            elif [[ "${BREW_TEST_NO_HASH:-no}" == yes && ( "$1" == shasum || "$1" == sha256sum ) ]]; then return 1;
            else command -v "$1" >/dev/null 2>&1; fi
        }
        brew() { printf "%s\n" "$*" > "$BREW_TEST_MARKER"; }
        _homebrew_installer_sha256() { printf "%s\n" "$BREW_TEST_SHA"; }
        if [[ "${BREW_TEST_DIRECT:-no}" == yes ]]; then
            install_package_manager
        else
            if install_package_manager; then exit 0; else exit $?; fi
        fi
    '
}

@test "Homebrew rejects changed bytes before any installer execution" {
    export BREW_TEST_SHA=0000000000000000000000000000000000000000000000000000000000000000
    run_brew
    assert_failure
    [ ! -e "$BREW_TEST_MARKER" ]
    refute_output --partial "SUCCESS: Homebrew installed"
}

@test "Homebrew rejects partial download even when curl emits a valid script" {
    export BREW_TEST_CURL_EXIT=22
    run_brew
    assert_failure
    [ ! -e "$BREW_TEST_MARKER" ]
    refute_output --partial "SUCCESS: Homebrew installed"
}

@test "verified Homebrew fixture executes privately and cleans its downloaded file" {
    run_brew
    assert_success
    [ -f "$BREW_TEST_MARKER" ]
    assert_equal "$(cat "$BREW_TEST_MARKER")" "synthetic installer"
    run cat "$BREW_TEST_PATH"
    assert_output --partial "$TMPDIR/manifest-homebrew."
    assert_equal "$(ls -A "$TMPDIR")" ""
    run cat "$BREW_TEST_CURL_LOG"
    assert_output --partial "https://raw.githubusercontent.com/Homebrew/install/df3c2556141c012eaba0453ede7a1bd4f05b824c/install.sh"
    refute_output --partial "/HEAD/"
    assert_output --partial "=https"
}

@test "Homebrew checksum verification supports the macOS shasum fallback" {
    export BREW_TEST_SHASUM=yes
    run_brew
    assert_success
    [ -f "$BREW_TEST_MARKER" ]
    assert_equal "$(ls -A "$TMPDIR")" ""
}

@test "Homebrew refuses without a checksum tool before downloading" {
    export BREW_TEST_NO_HASH=yes
    run_brew
    assert_failure
    [ ! -e "$BREW_TEST_CURL_LOG" ]
    [ ! -e "$BREW_TEST_MARKER" ]
    assert_equal "$(ls -A "$TMPDIR")" ""
}

@test "checksum command failure cannot pass using plausible digest stdout" {
    printf '#!/bin/bash\nprintf "%%s  file\\n" "$BREW_TEST_SHA"\nexit 17\n' > "$SANDBOX/bin/sha256sum"
    chmod +x "$SANDBOX/bin/sha256sum"
    run_brew
    assert_failure
    [ ! -e "$BREW_TEST_MARKER" ]
    assert_equal "$(ls -A "$TMPDIR")" ""
}

@test "failed verified installer stops before success and cleans staging" {
    export BREW_TEST_INSTALL_EXIT=19
    run_brew
    assert_failure
    [ -f "$BREW_TEST_MARKER" ]
    refute_output --partial "SUCCESS: Homebrew installed"
    assert_equal "$(ls -A "$TMPDIR")" ""
}

@test "download failure also propagates with direct errexit caller" {
    export BREW_TEST_DIRECT=yes BREW_TEST_CURL_EXIT=22
    run_brew
    assert_failure
    [ ! -e "$BREW_TEST_MARKER" ]
    assert_equal "$(ls -A "$TMPDIR")" ""
}

@test "declining Homebrew keeps consent behavior and makes no download" {
    export BREW_TEST_CONSENT=no
    run_brew
    assert_success
    [ ! -e "$BREW_TEST_CURL_LOG" ]
    [ ! -e "$BREW_TEST_MARKER" ]
}

@test "existing Homebrew still updates without downloading installer" {
    export BREW_TEST_PRESENT=yes
    run_brew
    assert_success
    assert_equal "$(cat "$BREW_TEST_MARKER")" "update --quiet"
    [ ! -e "$BREW_TEST_CURL_LOG" ]
}

@test "Linux package manager path never invokes Homebrew downloader" {
    export BREW_TEST_PLATFORM=linux
    run_brew
    assert_success
    [ ! -e "$BREW_TEST_CURL_LOG" ]
    [ ! -e "$BREW_TEST_MARKER" ]
}

@test "committed Homebrew digest is anchored in sourced helper rather than environment" {
    run /bin/bash -c 'source "$INSTALL_LIB"; _homebrew_installer_sha256'
    assert_success
    assert_output '151a786c066af55f61bd32bd4804470fdb2b872e6a42a8ef1335c29760e37404'
}
