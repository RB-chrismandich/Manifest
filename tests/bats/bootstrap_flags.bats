#!/usr/bin/env bats
# Tests for bootstrap.sh CLI flags: --update-config non-interactive dispatch
# and --enable-apm no-op help wording.

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."

setup() {
    export MANIFEST_APM_DOMAINS="$BATS_TEST_TMPDIR/no-apm-domains.yml"
    printf 'domains: []\n' > "$MANIFEST_APM_DOMAINS"

    export BATS_TMPDIR="${BATS_TMPDIR:-/tmp}"
    SANDBOX=$(mktemp -d "$BATS_TMPDIR/bootstrap_flags.XXXXXX")
    export HOME="$SANDBOX/home"
    export XDG_CONFIG_HOME="$SANDBOX/xdg/config"
    export XDG_DATA_HOME="$SANDBOX/xdg/data"
    export XDG_STATE_HOME="$SANDBOX/xdg/state"
    export MANIFEST_STATE_ROOT="$HOME/.manifest"
    FAKE_BIN="$SANDBOX/bin"
    mkdir -p "$HOME" "$XDG_CONFIG_HOME" "$XDG_DATA_HOME" "$XDG_STATE_HOME" "$FAKE_BIN"
    # Block any unintended network download (e.g. verified uv release fetch).
    make_stub curl 1
    if [[ -x "$REPO_ROOT/.venv/bin/python3" ]]; then
        ln -s "$REPO_ROOT/.venv/bin/python3" "$FAKE_BIN/python3"
    fi
}

teardown() {
    [[ -n "$SANDBOX" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"
}

make_stub() {
    local name="$1"
    local exit_code="${2:-0}"
    cat > "$FAKE_BIN/$name" << EOF
#!/bin/bash
exit $exit_code
EOF
    chmod +x "$FAKE_BIN/$name"
}

_uv_release_target_for_tests() {
    case "$(uname -s)-$(uname -m)" in
        Darwin-arm64) echo "aarch64-apple-darwin" ;;
        Darwin-x86_64) echo "x86_64-apple-darwin" ;;
        Linux-x86_64) echo "x86_64-unknown-linux-gnu" ;;
        Linux-aarch64 | Linux-arm64) echo "aarch64-unknown-linux-gnu" ;;
        *) echo "" ;;
    esac
}

# check_uv() always fetches the pinned release archive via curl. The suite-wide
# curl stub blocks network, so tests that run full bootstrap must wire a local
# archive copy through a curl shim (see bootstrap_verified_uv.bats).
install_offline_verified_uv_curl_stub() {
    local target archive cache_dir system_curl
    target="$(_uv_release_target_for_tests)"
    [[ -n "$target" ]] || skip "unsupported platform for verified uv bootstrap test"
    archive="uv-${target}.tar.gz"
    cache_dir="$SANDBOX/verified-uv"
    mkdir -p "$cache_dir"
    system_curl="$(command -v curl)"
    [[ -x "$system_curl" && "$system_curl" != "$FAKE_BIN/curl" ]] || skip "system curl required to seed verified uv fixture"
    "$system_curl" -fsSL \
        -o "$cache_dir/$archive" \
        "https://github.com/astral-sh/uv/releases/download/0.12.6/$archive" \
        || skip "could not download verified uv fixture for $target"
    cat > "$FAKE_BIN/curl" <<EOF
#!/bin/bash
out=""
while [[ \$# -gt 0 ]]; do
    case "\$1" in
        -o) out="\$2"; shift 2 ;;
        *) shift ;;
    esac
done
if [[ -n "\$out" ]]; then
    cp "$cache_dir/$archive" "\$out"
    exit 0
fi
exit 1
EOF
    chmod +x "$FAKE_BIN/curl"
}

seed_existing_claude_home() {
    mkdir -p "$HOME/.claude/plugins/cache/mkt/remember/0.7.3" \
             "$HOME/.claude/projects" "$HOME/.claude/config"
    echo '{"plugins":{"remember":1}}' > "$HOME/.claude/plugins/installed_plugins.json"
    echo 'session-data'               > "$HOME/.claude/projects/abc.jsonl"
    echo '{"permissions":{}}'         > "$HOME/.claude/settings.json"
    echo 'STALE-CLAUDE-MD'            > "$HOME/.claude/CLAUDE.md"
    echo 'STALE-LABELS'               > "$HOME/.claude/config/labels.yml"
    echo 'keepme'                     > "$HOME/.claude/my_personal_note.md"
}

@test "bootstrap.sh --help documents --update-config and clarifies --enable-apm as a no-op" {
    run env -i PATH=/usr/bin:/bin HOME="$HOME" bash "$REPO_ROOT/bootstrap.sh" --help
    assert_success
    assert_output --partial "--update-config"
    assert_output --partial "--enable-apm"

    local apm_line
    apm_line="$(printf '%s\n' "$output" | grep -- '--enable-apm' | tr '[:upper:]' '[:lower:]')"
    [[ "$apm_line" == *"no-op"* ]]
}

@test "bootstrap.sh --help documents --enable-gemini/--disable-gemini as no-ops" {
    run env -i PATH=/usr/bin:/bin HOME="$HOME" bash "$REPO_ROOT/bootstrap.sh" --help
    assert_success

    local flag line
    for flag in --enable-gemini --disable-gemini; do
        line="$(printf '%s\n' "$output" | grep -- "$flag" | tr '[:upper:]' '[:lower:]')"
        [[ "$line" == *"no-op"* && "$line" == *"removed"* ]] || {
            echo "$flag not documented as a removed no-op: $line"
            false
        }
    done
}

@test "--enable-gemini/--disable-gemini parse as notice-only no-ops" {
    run bash -c "
        RED='' GREEN='' BLUE='' YELLOW='' CYAN='' BOLD='' NC=''
        source '$REPO_ROOT/bootstrap/lib/common.sh'
        source '$REPO_ROOT/bootstrap/lib/config.sh'
        set_bootstrap_defaults
        parse_bootstrap_args --enable-gemini --disable-cursor --disable-gemini
        echo \"cursor=\$ENABLE_CURSOR gemini=\${ENABLE_GEMINI-unset}\"
    "
    assert_success
    assert_output --partial "--enable-gemini ignored: Gemini CLI support was removed"
    assert_output --partial "--disable-gemini ignored: Gemini CLI support was removed"
    assert_output --partial "cursor=false gemini=unset"
}

@test "bootstrap.sh rejects combining --force and --update-config" {
    run env -i PATH=/usr/bin:/bin HOME="$HOME" bash "$REPO_ROOT/bootstrap.sh" --force --update-config
    assert_failure
    assert_output --partial "--force"
    assert_output --partial "--update-config"
}

@test "bootstrap.sh --update-config dispatches option 4 non-interactively and preserves runtime state" {
    seed_existing_claude_home
    install_offline_verified_uv_curl_stub
    make_stub claude 0

    run env PATH="$FAKE_BIN:/usr/bin:/bin" \
        HOME="$HOME" \
        XDG_CONFIG_HOME="$XDG_CONFIG_HOME" \
        XDG_DATA_HOME="$XDG_DATA_HOME" \
        XDG_STATE_HOME="$XDG_STATE_HOME" \
        MANIFEST_STATE_ROOT="$MANIFEST_STATE_ROOT" \
        MANIFEST_APM_DOMAINS="$MANIFEST_APM_DOMAINS" \
        SHELL=/bin/zsh \
        bash "$REPO_ROOT/bootstrap.sh" \
            --update-config \
            --skip-install \
            --skip-auth \
            --disable-cursor \
            --disable-gemini \
            --disable-codex \
            --disable-antigravity < /dev/null
    assert_success
    assert_output --partial "Configuration updated (runtime state kept)"

    run cmp -s "$HOME/.claude/CLAUDE.md" "$REPO_ROOT/configs/claude/CLAUDE.md"
    assert_success
    run cmp -s "$HOME/.claude/config/labels.yml" "$REPO_ROOT/configs/claude/config/labels.yml"
    assert_success
    assert_equal "$(cat "$HOME/.claude/projects/abc.jsonl")" "session-data"
    assert_equal "$(cat "$HOME/.claude/my_personal_note.md")" "keepme"

    run bash -c "ls -d '$HOME'/.claude.backup.* 2>/dev/null | wc -l | tr -d ' '"
    assert_output "0"
}
