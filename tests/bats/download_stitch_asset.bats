#!/usr/bin/env bats

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'
bats_require_minimum_version 1.5.0

setup() {
    SANDBOX=$(mktemp -d "${BATS_TMPDIR:-/tmp}/stitch_download.XXXXXX")
    SCRIPT="$BATS_TEST_DIRNAME/../../plugins/stitch-design/skills/remotion/scripts/download-stitch-asset.sh"
    export HOME="$SANDBOX/home" CURL_HOME="$SANDBOX/home"
    export STITCH_TEST_ARGS="$SANDBOX/args"
    mkdir -p "$HOME" "$SANDBOX/bin"
    cp "$BATS_TEST_DIRNAME/../fixtures/stitch/download_curl.sh" "$SANDBOX/bin/curl"
    URL='https://synthetic-user:synthetic-pass@example.invalid/asset?X-Goog-Signature=synthetic-capability#synthetic-fragment'
    OUTPUT="$SANDBOX/nested/screen image.png"
}

teardown() {
    if [[ -n "${SERVER_PID:-}" ]]; then
        kill "$SERVER_PID" 2>/dev/null || true
        wait "$SERVER_PID" 2>/dev/null || true
    fi
    rm -rf "$SANDBOX"
}

assert_no_capability() {
    local marker
    for marker in "$URL" synthetic-user synthetic-pass synthetic-capability synthetic-fragment redirect-capability redirect-fragment; do
        [[ "$output" != *"$marker"* ]] || { echo "stdout leaked synthetic capability"; return 1; }
        [[ "$stderr" != *"$marker"* ]] || { echo "stderr leaked synthetic capability"; return 1; }
    done
}

@test "signed asset success keeps bytes and suppresses URL diagnostics in both streams" {
    run --separate-stderr env PATH="$SANDBOX/bin:/usr/bin:/bin" /bin/bash "$SCRIPT" "$URL" "$OUTPUT"
    assert_success
    assert_no_capability
    assert_equal "$(cat "$OUTPUT")" "synthetic asset bytes"
    assert_output --partial "$OUTPUT"
}

@test "failed asset download suppresses capability-bearing curl errors" {
    export STITCH_TEST_EXIT=22
    run --separate-stderr env PATH="$SANDBOX/bin:/usr/bin:/bin" /bin/bash "$SCRIPT" "$URL" "$OUTPUT"
    assert_failure 1
    assert_no_capability
    [ ! -e "$OUTPUT" ]
}


@test "inherited xtrace never sees the signed URL assignment or curl arguments" {
    run --separate-stderr env PATH="$SANDBOX/bin:/usr/bin:/bin" /bin/bash -x "$SCRIPT" "$URL" "$OUTPUT"
    assert_success
    assert_no_capability
    [ -f "$OUTPUT" ]
}

@test "curl receives the complete URL with config disabled as its first option" {
    run --separate-stderr env PATH="$SANDBOX/bin:/usr/bin:/bin" /bin/bash "$SCRIPT" "$URL" "$OUTPUT"
    assert_success
    assert_equal "$(head -n 1 "$STITCH_TEST_ARGS")" "-q"
    assert_equal "$(tail -n 1 "$STITCH_TEST_ARGS")" "$URL"
    run grep -Fx -- "$OUTPUT" "$STITCH_TEST_ARGS"
    assert_success
}

@test "real curl parser failure does not echo a malformed signed URL" {
    URL='https://synthetic-user:synthetic-pass@example.invalid/a[bad]?signature=synthetic-capability#synthetic-fragment'
    run --separate-stderr env PATH=/usr/bin:/bin /bin/bash "$SCRIPT" "$URL" "$OUTPUT"
    assert_failure 1
    assert_output --partial "curl exit 3"
    assert_no_capability
    [ ! -e "$OUTPUT" ]
}

start_server() {
    python3 "$BATS_TEST_DIRNAME/../fixtures/stitch/download_server.py" "$SANDBOX/port" > "$SANDBOX/server.log" 2>&1 &
    SERVER_PID=$!
    local attempt
    for attempt in $(seq 1 100); do
        [[ -s "$SANDBOX/port" ]] && break
        sleep 0.01
    done
    [ -s "$SANDBOX/port" ]
    URL="http://synthetic-user:synthetic-pass@127.0.0.1:$(cat "$SANDBOX/port")/$1?signature=synthetic-capability#synthetic-fragment"
}

@test "real local redirect succeeds without ambient curl trace or write-out leakage" {
    start_server redirect
    printf 'verbose\nwrite-out = "%%{url_effective}\n"\ntrace-ascii = "%s"\n' "$SANDBOX/curl-trace" > "$HOME/.curlrc"
    run --separate-stderr env PATH=/usr/bin:/bin /bin/bash "$SCRIPT" "$URL" "$OUTPUT"
    assert_success
    assert_no_capability
    assert_equal "$(cat "$OUTPUT")" "local asset bytes"
    assert_output --partial "File size: 17 bytes"
    [ ! -e "$SANDBOX/curl-trace" ]
}

@test "real local HTTP failure reports status and removes the output" {
    start_server error
    run --separate-stderr env PATH=/usr/bin:/bin /bin/bash "$SCRIPT" "$URL" "$OUTPUT"
    assert_failure 1
    assert_output --partial "curl exit 22"
    assert_no_capability
    [ ! -e "$OUTPUT" ]
}

@test "usage failure does not print a supplied capability argument" {
    run --separate-stderr /bin/bash "$SCRIPT" "$URL"
    assert_failure 1
    assert_output --partial "Usage:"
    assert_no_capability
}
