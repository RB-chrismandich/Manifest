#!/usr/bin/env bats
# Tests for bootstrap/lib/common.sh deploy_home_skills + deploy.sh skills wiring

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."

setup() {
    export BATS_TMPDIR="${BATS_TMPDIR:-/tmp}"
    SANDBOX=$(mktemp -d "$BATS_TMPDIR/deploy_skills.XXXXXX")
    # Source the helpers under test
    # shellcheck disable=SC1090
    source "$REPO_ROOT/bootstrap/lib/common.sh"
}

teardown() {
    [[ -n "$SANDBOX" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"
}

@test "deploy_home_skills copies real directories from physical source" {
    mkdir -p "$SANDBOX/src/demo-skill"
    echo "body" > "$SANDBOX/src/demo-skill/SKILL.md"

    run deploy_home_skills "$SANDBOX/src" "$SANDBOX/dest"
    assert_success

    [ -d "$SANDBOX/dest/demo-skill" ]
    [ ! -L "$SANDBOX/dest" ]
    assert_equal "$(cat "$SANDBOX/dest/demo-skill/SKILL.md")" "body"
}

@test "deploy_home_skills preserves externally-managed dest content (no --delete)" {
    # ~/.claude/skills can hold skills from other tools/plugins; deploy must be
    # additive and NOT prune dest entries that are absent from the source.
    mkdir -p "$SANDBOX/src/keep" "$SANDBOX/dest/external"
    echo k > "$SANDBOX/src/keep/SKILL.md"
    echo e > "$SANDBOX/dest/external/SKILL.md"

    run deploy_home_skills "$SANDBOX/src" "$SANDBOX/dest"
    assert_success

    [ -d "$SANDBOX/dest/keep" ]      # source skill deployed
    [ -d "$SANDBOX/dest/external" ]  # foreign skill NOT pruned
    assert_equal "$(cat "$SANDBOX/dest/external/SKILL.md")" "e"
}

@test "deploy_home_skills converts a stray symlink dest into a real dir" {
    mkdir -p "$SANDBOX/src/demo" "$SANDBOX/elsewhere"
    echo d > "$SANDBOX/src/demo/SKILL.md"
    ln -s "$SANDBOX/elsewhere" "$SANDBOX/dest"   # dest starts as a symlink

    run deploy_home_skills "$SANDBOX/src" "$SANDBOX/dest"
    assert_success

    [ ! -L "$SANDBOX/dest" ]              # symlink replaced by a real dir
    [ -d "$SANDBOX/dest/demo" ]           # content deployed into the real dir
    [ ! -e "$SANDBOX/elsewhere/demo" ]    # did NOT write through into old target
}

@test "deploy_home_skills fails clearly when source missing" {
    run deploy_home_skills "$SANDBOX/nonexistent" "$SANDBOX/dest"
    assert_failure
    assert_output --partial "not found"
}

@test "deploy_configs (fresh) puts real skill dirs in TARGET and no '~' junk" {
    # Arrange an isolated TARGET and stub the heavy secondary deploys.
    export SCRIPT_DIR="$REPO_ROOT"
    export TARGET_DIR="$SANDBOX/home/.claude"
    export CURSOR_TARGET_DIR="$SANDBOX/home/.cursor"
    export GEMINI_TARGET_DIR="$SANDBOX/home/.gemini"
    export CODEX_TARGET_DIR="$SANDBOX/home/.codex"
    export ANTIGRAVITY_TARGET_DIR="$SANDBOX/home/.antigravity"
    export MANIFEST_OUTPUT_DIR="$SANDBOX/home/.manifest/outputs"
    export FORCE=true

    # shellcheck disable=SC1090
    source "$REPO_ROOT/bootstrap/lib/deploy.sh"

    # Isolate: stub secondary routines that need network/CLIs/other configs.
    write_services_config() { :; }
    deploy_cursor_configs() { :; }
    deploy_gemini_configs() { :; }
    deploy_codex_configs() { :; }
    deploy_antigravity_configs() { :; }
    sync_skillshare_targets() { :; }
    deploy_sync_skills() { :; }

    run deploy_configs
    assert_success

    # Real skill dirs landed (sampled), and skills is NOT a symlink.
    [ -d "$TARGET_DIR/skills/code-quality" ]
    [ ! -L "$TARGET_DIR/skills" ]
    # The compat symlink was never copied verbatim into the home dir.
    [ ! -e "$TARGET_DIR/skills/skills" ]
    # No literal tilde dir created anywhere under the sandbox.
    run find "$SANDBOX" -maxdepth 6 -name '~'
    assert_output ""
}

@test "deploy_antigravity_configs symlinks ~/.antigravity/skills to claude skills" {
    export TARGET_DIR="$SANDBOX/home/.claude"
    export ANTIGRAVITY_TARGET_DIR="$SANDBOX/home/.antigravity"
    mkdir -p "$TARGET_DIR/skills/demo"

    # shellcheck disable=SC1090
    source "$REPO_ROOT/bootstrap/lib/deploy.sh"

    run deploy_antigravity_configs
    assert_success

    [ -L "$ANTIGRAVITY_TARGET_DIR/skills" ]
    [ -d "$ANTIGRAVITY_TARGET_DIR/skills/demo" ]
}

@test "sync_skillshare_targets runs skillshare sync when present" {
    export SCRIPT_DIR="$SANDBOX/repo"
    mkdir -p "$SCRIPT_DIR/.skillshare"
    echo "targets: []" > "$SCRIPT_DIR/.skillshare/config.yaml"

    # Stub skillshare on PATH that records invocation.
    MOCK_BIN="$SANDBOX/bin"; mkdir -p "$MOCK_BIN"
    cat > "$MOCK_BIN/skillshare" <<'STUB'
#!/usr/bin/env bash
echo "skillshare $*" >> "$SKILLSHARE_LOG"
STUB
    chmod +x "$MOCK_BIN/skillshare"
    export PATH="$MOCK_BIN:$PATH"
    export SKILLSHARE_LOG="$SANDBOX/ss.log"

    # shellcheck disable=SC1090
    source "$REPO_ROOT/bootstrap/lib/deploy.sh"

    run sync_skillshare_targets
    assert_success
    assert_output --partial "Syncing"
    grep -q "skillshare sync" "$SKILLSHARE_LOG"
}

@test "sync_skillshare_targets is a no-op (success) when skillshare absent" {
    export SCRIPT_DIR="$SANDBOX/repo"
    mkdir -p "$SCRIPT_DIR/.skillshare"
    echo "targets: []" > "$SCRIPT_DIR/.skillshare/config.yaml"

    # shellcheck disable=SC1090
    source "$REPO_ROOT/bootstrap/lib/deploy.sh"

    # Minimal PATH that keeps coreutils but excludes Homebrew (where skillshare
    # lives), so `command -v skillshare` finds nothing. Scoped to `run`.
    PATH="/usr/bin:/bin" run sync_skillshare_targets
    assert_success
    assert_output --partial "skipping"
}

# ── configure_shell_profile_state — MANIFEST_ROOT ───────────────────────────

@test "configure_shell_profile_state writes MANIFEST_ROOT to shell profile" {
    local fake_home="$SANDBOX/home"
    mkdir -p "$fake_home"
    export HOME="$fake_home"
    export SHELL="/bin/bash"
    export PLATFORM="linux"
    export SCRIPT_DIR="/fake/manifest/path"

    print_step()    { :; }
    print_success() { :; }
    print_info()    { :; }
    print_warning() { :; }
    print_error()   { :; }

    # shellcheck disable=SC1090
    source "$REPO_ROOT/bootstrap/lib/auth.sh"
    configure_shell_profile_state

    grep -q 'export MANIFEST_ROOT="/fake/manifest/path"' "$fake_home/.bashrc"
}

@test "configure_shell_profile_state updates MANIFEST_ROOT on re-run with no duplicate lines" {
    local fake_home="$SANDBOX/home"
    mkdir -p "$fake_home"
    echo 'export MANIFEST_ROOT="/old/path"' > "$fake_home/.bashrc"
    export HOME="$fake_home"
    export SHELL="/bin/bash"
    export PLATFORM="linux"
    export SCRIPT_DIR="/new/path"

    print_step()    { :; }
    print_success() { :; }
    print_info()    { :; }
    print_warning() { :; }
    print_error()   { :; }

    # shellcheck disable=SC1090
    source "$REPO_ROOT/bootstrap/lib/auth.sh"
    configure_shell_profile_state

    run grep -c 'export MANIFEST_ROOT=' "$fake_home/.bashrc"
    assert_output "1"
    grep -q '/new/path' "$fake_home/.bashrc"
}

# ── deploy_sync_skills ───────────────────────────────────────────────────────

@test "deploy_sync_skills copies script to ~/.local/bin/sync-skills and makes it executable" {
    local fake_home="$SANDBOX/home"
    export HOME="$fake_home"
    mkdir -p "$fake_home"
    local fake_profile="$SANDBOX/profile"
    touch "$fake_profile"
    export SHELL_PROFILE_FILE="$fake_profile"
    export SCRIPT_DIR="$REPO_ROOT"

    print_step()    { :; }
    print_success() { :; }
    print_info()    { :; }

    # shellcheck disable=SC1090
    source "$REPO_ROOT/bootstrap/lib/deploy.sh"

    run deploy_sync_skills
    assert_success

    [ -f "$fake_home/.local/bin/sync-skills" ]
    [ -x "$fake_home/.local/bin/sync-skills" ]
}

@test "deploy_sync_skills adds ~/.local/bin to PATH in shell profile" {
    local fake_home="$SANDBOX/home"
    export HOME="$fake_home"
    mkdir -p "$fake_home"
    local fake_profile="$SANDBOX/profile"
    touch "$fake_profile"
    export SHELL_PROFILE_FILE="$fake_profile"
    export SCRIPT_DIR="$REPO_ROOT"

    print_step()    { :; }
    print_success() { :; }
    print_info()    { :; }

    # shellcheck disable=SC1090
    source "$REPO_ROOT/bootstrap/lib/deploy.sh"

    run deploy_sync_skills
    assert_success

    grep -q ".local/bin" "$fake_profile"
}

@test "deploy_sync_skills PATH entry is idempotent on re-run" {
    local fake_home="$SANDBOX/home"
    export HOME="$fake_home"
    mkdir -p "$fake_home"
    local fake_profile="$SANDBOX/profile"
    touch "$fake_profile"
    export SHELL_PROFILE_FILE="$fake_profile"
    export SCRIPT_DIR="$REPO_ROOT"

    print_step()    { :; }
    print_success() { :; }
    print_info()    { :; }

    # shellcheck disable=SC1090
    source "$REPO_ROOT/bootstrap/lib/deploy.sh"

    deploy_sync_skills
    deploy_sync_skills  # second run — must not duplicate the PATH line

    run grep -c 'export PATH="$HOME/.local/bin:$PATH"' "$fake_profile"
    assert_output "1"
}
