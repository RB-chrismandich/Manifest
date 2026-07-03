#!/usr/bin/env bats
# merge_gemini_hooks(): repo hooks must reach EXISTING ~/.gemini/settings.json
# installs (the preserve-only branch silently skipped them, so hooks shipped
# in configs/gemini/settings.json never propagated to bootstrapped machines).

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."

setup() {
    TMPDIR_T="$(mktemp -d)"
    SRC="$TMPDIR_T/src.json"
    TGT="$TMPDIR_T/tgt.json"

    # Minimal stubs for the helpers merge_gemini_hooks uses
    command_exists() { command -v "$1" > /dev/null 2>&1; }
    print_info() { echo "INFO: $*"; }
    print_success() { echo "OK: $*"; }
    print_warning() { echo "WARN: $*"; }
    export -f command_exists print_info print_success print_warning 2> /dev/null || true

    # shellcheck disable=SC1091
    source "$REPO_ROOT/bootstrap/lib/deploy.sh" 2> /dev/null || true

    cat > "$SRC" <<'EOF'
{
  "hooks": {
    "BeforeAgent": [
      { "hooks": [ { "name": "token-economy-reminder", "type": "command",
          "command": "echo reminder", "timeout": 5000 } ] }
    ]
  }
}
EOF
}

teardown() {
    rm -rf "$TMPDIR_T"
}

@test "adds repo hook to existing settings.json and preserves user keys" {
    cat > "$TGT" <<'EOF'
{ "mcpServers": { "user-server": { "url": "https://example.test" } } }
EOF
    run merge_gemini_hooks "$SRC" "$TGT"
    assert_success
    assert_output --partial "Merged repo hooks"

    run python3 -c "
import json
d = json.load(open('$TGT'))
assert d['mcpServers']['user-server']['url'] == 'https://example.test'
assert d['hooks']['BeforeAgent'][0]['hooks'][0]['name'] == 'token-economy-reminder'
print('merged-and-preserved')"
    assert_output --partial "merged-and-preserved"
}

@test "second run is idempotent (no duplicate hook entries)" {
    cat > "$TGT" <<'EOF'
{}
EOF
    run merge_gemini_hooks "$SRC" "$TGT"
    assert_success
    run merge_gemini_hooks "$SRC" "$TGT"
    assert_success
    assert_output --partial "already has repo hooks"

    run python3 -c "
import json
d = json.load(open('$TGT'))
assert len(d['hooks']['BeforeAgent']) == 1, d
print('no-duplicates')"
    assert_output --partial "no-duplicates"
}

@test "malformed existing settings.json fails open (file untouched, warning)" {
    echo '{ not json' > "$TGT"
    local before
    before=$(cat "$TGT")
    run merge_gemini_hooks "$SRC" "$TGT"
    assert_success
    assert_output --partial "WARN"
    assert_equal "$(cat "$TGT")" "$before"
}

@test "repo settings.json source contains the BeforeAgent reminder hook" {
    run python3 -c "
import json
d = json.load(open('$REPO_ROOT/configs/gemini/settings.json'))
entries = d['hooks']['BeforeAgent']
assert any('token-conserve' in json.dumps(e) for e in entries)
print('source-hook-present')"
    assert_output --partial "source-hook-present"
}
