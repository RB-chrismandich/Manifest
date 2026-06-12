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

@test "deploy_home_skills preserves externally-managed dest content (manifest-scoped prune)" {
    # ~/.claude/skills can hold skills from other tools/plugins; pruning is
    # scoped to the .deployed-skills manifest, so foreign entries survive.
    mkdir -p "$SANDBOX/src/keep" "$SANDBOX/dest/external"
    echo k > "$SANDBOX/src/keep/SKILL.md"
    echo e > "$SANDBOX/dest/external/SKILL.md"

    run deploy_home_skills "$SANDBOX/src" "$SANDBOX/dest"
    assert_success

    [ -d "$SANDBOX/dest/keep" ]      # source skill deployed
    [ -d "$SANDBOX/dest/external" ]  # foreign skill NOT pruned
    assert_equal "$(cat "$SANDBOX/dest/external/SKILL.md")" "e"
}

@test "deploy_home_skills prunes previously-deployed skills removed from source" {
    # FR-005a: a skill deleted from the source of truth must disappear from the
    # deploy target on the next deploy (no stale duplicates in live sessions).
    mkdir -p "$SANDBOX/src/alpha" "$SANDBOX/src/beta"
    echo a > "$SANDBOX/src/alpha/SKILL.md"
    echo b > "$SANDBOX/src/beta/SKILL.md"
    deploy_home_skills "$SANDBOX/src" "$SANDBOX/dest"
    [ -d "$SANDBOX/dest/beta" ]

    rm -rf "$SANDBOX/src/beta"                 # consolidation deletes beta
    run deploy_home_skills "$SANDBOX/src" "$SANDBOX/dest"
    assert_success

    [ -d "$SANDBOX/dest/alpha" ]               # survivor intact
    [ ! -d "$SANDBOX/dest/beta" ]              # absorbed skill pruned
}

@test "deploy_home_skills prune never touches skills it did not deploy" {
    # FR-005a safety bound: external skills (never in the manifest) survive a
    # deploy that prunes a removed source skill.
    mkdir -p "$SANDBOX/src/alpha" "$SANDBOX/src/beta"
    echo a > "$SANDBOX/src/alpha/SKILL.md"
    echo b > "$SANDBOX/src/beta/SKILL.md"
    deploy_home_skills "$SANDBOX/src" "$SANDBOX/dest"
    mkdir -p "$SANDBOX/dest/hand-added"        # external, post-deploy
    echo x > "$SANDBOX/dest/hand-added/SKILL.md"

    rm -rf "$SANDBOX/src/beta"
    run deploy_home_skills "$SANDBOX/src" "$SANDBOX/dest"
    assert_success

    [ ! -d "$SANDBOX/dest/beta" ]              # deployed+removed -> pruned
    [ -d "$SANDBOX/dest/hand-added" ]          # never deployed -> untouched
    assert_equal "$(cat "$SANDBOX/dest/hand-added/SKILL.md")" "x"
}

@test "deploy_home_skills empty source never mass-prunes previously deployed skills" {
    # Cross-verification finding: an existing-but-empty src (failed checkout,
    # wrong path) must not delete everything the manifest lists.
    mkdir -p "$SANDBOX/src/alpha"
    echo a > "$SANDBOX/src/alpha/SKILL.md"
    deploy_home_skills "$SANDBOX/src" "$SANDBOX/dest"

    rm -rf "$SANDBOX/src/alpha"                # src now exists but is empty
    run deploy_home_skills "$SANDBOX/src" "$SANDBOX/dest"
    assert_success
    [ -d "$SANDBOX/dest/alpha" ]               # NOT mass-pruned
}

@test "deploy_home_skills ignores path-traversal entries in a corrupted manifest" {
    mkdir -p "$SANDBOX/src/alpha" "$SANDBOX/outside"
    echo a > "$SANDBOX/src/alpha/SKILL.md"
    echo x > "$SANDBOX/outside/marker"
    deploy_home_skills "$SANDBOX/src" "$SANDBOX/dest"
    printf '../outside\n/etc\nalpha\n' > "$SANDBOX/dest/.deployed-skills"

    run deploy_home_skills "$SANDBOX/src" "$SANDBOX/dest"
    assert_success
    [ -f "$SANDBOX/outside/marker" ]           # traversal entry never followed
    [ -d "$SANDBOX/dest/alpha" ]               # valid, still-in-source entry kept
}

@test "deploy_home_skills double-deploy is an idempotent no-op" {
    # Constitution V: a second consecutive run changes nothing.
    mkdir -p "$SANDBOX/src/alpha"
    echo a > "$SANDBOX/src/alpha/SKILL.md"
    deploy_home_skills "$SANDBOX/src" "$SANDBOX/dest"
    local before
    before=$(find "$SANDBOX/dest" | sort)

    run deploy_home_skills "$SANDBOX/src" "$SANDBOX/dest"
    assert_success
    assert_equal "$(find "$SANDBOX/dest" | sort)" "$before"
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

@test "deploy_antigravity_configs symlinks all 5 shared assets to claude" {
    export TARGET_DIR="$SANDBOX/home/.claude"
    export ANTIGRAVITY_TARGET_DIR="$SANDBOX/home/.antigravity"
    mkdir -p "$TARGET_DIR/skills/demo" "$TARGET_DIR/scripts" \
        "$TARGET_DIR/config" "$TARGET_DIR/prompts" "$TARGET_DIR/.plans"

    # shellcheck disable=SC1090
    source "$REPO_ROOT/bootstrap/lib/deploy.sh"

    run deploy_antigravity_configs
    assert_success

    # All five shared assets are symlinked (mirrors Cursor/Gemini/Codex).
    for link in skills scripts config prompts .plans; do
        [ -L "$ANTIGRAVITY_TARGET_DIR/$link" ]
    done
    [ -d "$ANTIGRAVITY_TARGET_DIR/skills/demo" ]
}

@test "deploy_antigravity_configs is idempotent — second run leaves symlinks intact" {
    export TARGET_DIR="$SANDBOX/home/.claude"
    export ANTIGRAVITY_TARGET_DIR="$SANDBOX/home/.antigravity"
    mkdir -p "$TARGET_DIR/skills/demo" "$TARGET_DIR/scripts" \
        "$TARGET_DIR/config" "$TARGET_DIR/prompts" "$TARGET_DIR/.plans"

    # shellcheck disable=SC1090
    source "$REPO_ROOT/bootstrap/lib/deploy.sh"

    deploy_antigravity_configs          # first run
    run deploy_antigravity_configs      # second run — must not fail
    assert_success

    for link in skills scripts config prompts .plans; do
        [ -L "$ANTIGRAVITY_TARGET_DIR/$link" ]
    done
    [ -d "$ANTIGRAVITY_TARGET_DIR/skills/demo" ]
}

@test "deploy_antigravity_configs skills symlink target is resolvable" {
    export TARGET_DIR="$SANDBOX/home/.claude"
    export ANTIGRAVITY_TARGET_DIR="$SANDBOX/home/.antigravity"
    mkdir -p "$TARGET_DIR/skills/demo"

    # shellcheck disable=SC1090
    source "$REPO_ROOT/bootstrap/lib/deploy.sh"
    deploy_antigravity_configs

    local link_target
    link_target=$(readlink -f "$ANTIGRAVITY_TARGET_DIR/skills" 2>/dev/null || true)
    [ -e "$link_target" ] || (echo "Symlink target not resolvable: $link_target" && false)
    [ -d "$link_target" ]
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

# ---------------------------------------------------------------------------
# list_deployed_files — SIGPIPE-safe deployed-files listing (defensive).
# With >20 matching files, head exits early and find dies of SIGPIPE (141).
# That is fatal only under `pipefail` — bootstrap.sh currently sets only -e,
# so this hardens against the trap being armed if pipefail is ever added.
# (The silent bootstrap abort itself was _skillclaw_remove_launchd — see
# skillclaw_lib.bats.) Tests run under -euo pipefail, the strictest mode.
# ---------------------------------------------------------------------------

@test "list_deployed_files survives set -e with more than 20 files" {
    # shellcheck disable=SC1090
    source "$REPO_ROOT/bootstrap/lib/deploy.sh"
    mkdir -p "$SANDBOX/target"
    for i in $(seq 1 30); do echo x > "$SANDBOX/target/file$i.md"; done

    run bash -c "
        set -euo pipefail
        source '$REPO_ROOT/bootstrap/lib/common.sh'
        source '$REPO_ROOT/bootstrap/lib/deploy.sh'
        list_deployed_files '$SANDBOX/target'
        echo SURVIVED
    "
    assert_success
    assert_output --partial "SURVIVED"
    # Truncation to 20 entries still applies
    [ "$(echo "$output" | grep -c 'file')" -eq 20 ]
}

@test "list_deployed_files handles an empty directory" {
    # shellcheck disable=SC1090
    source "$REPO_ROOT/bootstrap/lib/deploy.sh"
    mkdir -p "$SANDBOX/empty"
    run bash -c "
        set -euo pipefail
        source '$REPO_ROOT/bootstrap/lib/common.sh'
        source '$REPO_ROOT/bootstrap/lib/deploy.sh'
        list_deployed_files '$SANDBOX/empty'
        echo SURVIVED
    "
    assert_success
    assert_output --partial "SURVIVED"
}
