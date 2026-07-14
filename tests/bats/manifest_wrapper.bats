#!/usr/bin/env bats
# Tests for configs/claude/scripts/manifest-cli.sh (deployed as ~/.local/bin/manifest)

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
WRAPPER="$REPO_ROOT/configs/claude/scripts/manifest-cli.sh"

setup() {
    export BATS_TMPDIR="${BATS_TMPDIR:-/tmp}"
    SANDBOX=$(mktemp -d "$BATS_TMPDIR/manifest_wrapper.XXXXXX")
    export HOME="$SANDBOX/home"
    mkdir -p "$HOME/.claude"
}

teardown() {
    [[ -n "$SANDBOX" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"
}

@test "exits 1 with home runtime message when venv manifest is missing" {
    # Restrict PATH so uv resolution falls through to ~/.local/bin/uv stub.
    MOCK_BIN="$SANDBOX/bin"
    mkdir -p "$MOCK_BIN" "$HOME/.local/bin"
    cat > "$HOME/.local/bin/uv" <<'STUB'
#!/usr/bin/env bash
exit 0
STUB
    chmod +x "$HOME/.local/bin/uv"

    run env HOME="$HOME" PATH="$MOCK_BIN:/usr/bin:/bin" bash "$WRAPPER" --help 2>&1
    assert_failure
    assert_output --partial "home runtime not installed"
}
