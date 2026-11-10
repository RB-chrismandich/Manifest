#!/usr/bin/env bats
# Gemini CLI support was removed. Bootstrap cleans up only what it provably
# deployed for the Gemini CLI into ~/.gemini, and the Antigravity path now owns
# agy's ~/.gemini/config link and ~/.gemini/GEMINI.md guide. Every test runs
# against a fake $HOME.

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."

setup() {
    SANDBOX=$(mktemp -d "${BATS_TMPDIR:-/tmp}/retired_gemini.XXXXXX")
    export HOME="$SANDBOX/home"
    export SCRIPT_DIR="$REPO_ROOT"
    export TARGET_DIR="$HOME/.claude"
    export MANIFEST_STATE_DIR="$HOME/.manifest"
    export MANIFEST_SKILLS_DIR="$MANIFEST_STATE_DIR/skills"
    export AGY_GEMINI_HOME="$HOME/.gemini"
    export ANTIGRAVITY_TARGET_DIR="$HOME/.antigravity"
    export RED='' GREEN='' BLUE='' YELLOW='' CYAN='' BOLD='' NC=''
    mkdir -p "$TARGET_DIR"/scripts "$TARGET_DIR"/config "$TARGET_DIR"/prompts \
        "$TARGET_DIR"/.plans "$MANIFEST_SKILLS_DIR" "$AGY_GEMINI_HOME"
    # shellcheck disable=SC1090
    source "$REPO_ROOT/bootstrap/lib/common.sh"
    # shellcheck disable=SC1090
    source "$REPO_ROOT/bootstrap/lib/deploy.sh"
}

teardown() {
    [[ -n "${SANDBOX:-}" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"
    return 0
}

# A ~/.gemini exactly as an earlier bootstrap left it, plus agy and user state.
seed_legacy_gemini_home() {
    ln -s "$TARGET_DIR/scripts" "$AGY_GEMINI_HOME/scripts"
    ln -s "$TARGET_DIR/prompts" "$AGY_GEMINI_HOME/prompts"
    ln -s "$TARGET_DIR/.plans" "$AGY_GEMINI_HOME/.plans"
    ln -s "$MANIFEST_SKILLS_DIR" "$AGY_GEMINI_HOME/skills"
    ln -s "$TARGET_DIR/config" "$AGY_GEMINI_HOME/config"
    echo "# guide" > "$AGY_GEMINI_HOME/GEMINI.md"
    echo '{"mcpServers": {}}' > "$AGY_GEMINI_HOME/settings.json"
    echo '{"token": "x"}' > "$AGY_GEMINI_HOME/oauth_creds.json"
    mkdir -p "$AGY_GEMINI_HOME/antigravity-cli"
    echo '{}' > "$AGY_GEMINI_HOME/antigravity-cli/settings.json"
}

# One historical Manifest command file, byte-identical to what was shipped.
shipped_command() {
    local name digest
    read -r digest name < <(grep -v '^#' "$REPO_ROOT/bootstrap/data/retired_gemini_commands.sha256" | head -1)
    git -C "$REPO_ROOT" log --all --format=%H -- "configs/gemini/commands/$name" |
        while read -r commit; do
            git -C "$REPO_ROOT" show "$commit:configs/gemini/commands/$name" 2> /dev/null > "$1/$name" || continue
            if [[ "$(_retired_gemini_sha256 "$1/$name")" == "$digest" ]]; then
                echo "$name"
                return 0
            fi
        done
}

@test "retire removes Manifest's Gemini CLI symlinks into ~/.claude and ~/.manifest" {
    seed_legacy_gemini_home

    run retire_gemini_cli_deployment
    assert_success

    for name in scripts prompts .plans skills; do
        [ ! -e "$AGY_GEMINI_HOME/$name" ] && [ ! -L "$AGY_GEMINI_HOME/$name" ] ||
            { echo "retired link survived: $name"; false; }
    done
}

@test "retire never touches agy config, GEMINI.md, settings, credentials, or antigravity state" {
    seed_legacy_gemini_home

    run retire_gemini_cli_deployment
    assert_success

    [ -L "$AGY_GEMINI_HOME/config" ]
    [ -f "$AGY_GEMINI_HOME/GEMINI.md" ]
    [ -f "$AGY_GEMINI_HOME/settings.json" ]
    [ -f "$AGY_GEMINI_HOME/oauth_creds.json" ]
    [ -f "$AGY_GEMINI_HOME/antigravity-cli/settings.json" ]
}

@test "retire keeps a foreign symlink and a real directory under a retired name" {
    mkdir -p "$SANDBOX/elsewhere" "$AGY_GEMINI_HOME/scripts"
    echo mine > "$AGY_GEMINI_HOME/scripts/user.sh"
    ln -s "$SANDBOX/elsewhere" "$AGY_GEMINI_HOME/skills"

    run retire_gemini_cli_deployment
    assert_success

    [ -f "$AGY_GEMINI_HOME/scripts/user.sh" ]
    [ -L "$AGY_GEMINI_HOME/skills" ]
    assert_equal "$(readlink "$AGY_GEMINI_HOME/skills")" "$SANDBOX/elsewhere"
}

@test "retire removes only byte-identical shipped command files" {
    mkdir -p "$AGY_GEMINI_HOME/commands"
    local shipped
    shipped="$(shipped_command "$AGY_GEMINI_HOME/commands")"
    [ -n "$shipped" ] || skip "historical command blob unavailable in this clone"
    echo 'prompt = "mine"' > "$AGY_GEMINI_HOME/commands/my-own.toml"
    printf 'edited\n' > "$AGY_GEMINI_HOME/commands/checkpoint.toml"

    run retire_gemini_cli_deployment
    assert_success

    [ ! -e "$AGY_GEMINI_HOME/commands/$shipped" ]
    [ -f "$AGY_GEMINI_HOME/commands/my-own.toml" ]
    [ -f "$AGY_GEMINI_HOME/commands/checkpoint.toml" ]
}

@test "retire drops the commands directory once it holds only shipped files" {
    mkdir -p "$AGY_GEMINI_HOME/commands"
    local shipped
    shipped="$(shipped_command "$AGY_GEMINI_HOME/commands")"
    [ -n "$shipped" ] || skip "historical command blob unavailable in this clone"

    run retire_gemini_cli_deployment
    assert_success

    [ ! -e "$AGY_GEMINI_HOME/commands" ]
}

@test "retire is a no-op without a ~/.gemini directory" {
    rm -rf "$AGY_GEMINI_HOME"

    run retire_gemini_cli_deployment
    assert_success
    assert_output ""
    [ ! -e "$AGY_GEMINI_HOME" ]
}

@test "deploy_antigravity_configs owns agy's ~/.gemini/config link and GEMINI.md guide" {
    export ENABLE_ANTIGRAVITY=true

    run deploy_antigravity_configs
    assert_success

    [ -L "$AGY_GEMINI_HOME/config" ]
    assert_equal "$(readlink "$AGY_GEMINI_HOME/config")" "$TARGET_DIR/config"
    cmp -s "$REPO_ROOT/configs/antigravity/GEMINI.md" "$AGY_GEMINI_HOME/GEMINI.md"
    head -1 "$AGY_GEMINI_HOME/GEMINI.md" | grep -q "Antigravity Orchestration Guide"
}

@test "deploy_antigravity_configs keeps agy's own real ~/.gemini/config directory" {
    export ENABLE_ANTIGRAVITY=true
    mkdir -p "$AGY_GEMINI_HOME/config/plugins/manifest-docs"

    run deploy_antigravity_configs
    assert_success

    [ ! -L "$AGY_GEMINI_HOME/config" ]
    [ -d "$AGY_GEMINI_HOME/config/plugins/manifest-docs" ]
}

@test "claude+antigravity-only deploy_configs gives agy its config link and guide" {
    export MANIFEST_APM_DOMAINS="$SANDBOX/no-apm-domains.yml"
    printf 'domains: []\n' > "$MANIFEST_APM_DOMAINS"
    export CURSOR_TARGET_DIR="$HOME/.cursor" CODEX_TARGET_DIR="$HOME/.codex"
    export MANIFEST_OUTPUT_DIR="$MANIFEST_STATE_DIR/outputs" FORCE=true
    export ENABLE_CLAUDE=true ENABLE_CURSOR=false ENABLE_CODEX=false \
        ENABLE_ANTIGRAVITY=true ENABLE_DEVIN=false
    seed_legacy_gemini_home
    rm "$AGY_GEMINI_HOME/config" "$AGY_GEMINI_HOME/GEMINI.md"
    write_services_config() { :; }
    deploy_sync_skills() { :; }
    register_manifest_marketplace() { :; }
    sync_all_native_harnesses() { :; }

    deploy_configs > /dev/null

    [ -L "$AGY_GEMINI_HOME/config" ]
    cmp -s "$REPO_ROOT/configs/antigravity/GEMINI.md" "$AGY_GEMINI_HOME/GEMINI.md"
    [ ! -L "$AGY_GEMINI_HOME/scripts" ]
    [ ! -L "$AGY_GEMINI_HOME/skills" ]
    [ -f "$AGY_GEMINI_HOME/oauth_creds.json" ]
}
