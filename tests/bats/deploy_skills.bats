#!/usr/bin/env bats
# Tests for bootstrap/lib/common.sh deploy_home_skills + deploy.sh skills wiring

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."

setup() {
    # Isolate the APM domain registry. Without this the suite reads the REPO's
    # live apm_domains.yml, so activating a domain there (SC-006) makes
    # deploy_home_skills stand down and every skill assertion below fails on a
    # developer machine while passing in CI. Ambient state must not decide a
    # test's outcome.
    export MANIFEST_APM_DOMAINS="$BATS_TEST_TMPDIR/no-apm-domains.yml"
    printf 'domains: []\n' > "$MANIFEST_APM_DOMAINS"

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

@test "deploy_home_skills warns on and excludes a top-level dir with no SKILL.md (rename debris)" {
    # Regression: a skill rename can leave the old-name directory behind on
    # disk (it still holds only git-ignored content, e.g. scripts/__pycache__)
    # even though git status shows nothing for it. deploy_home_skills copies
    # the filesystem, not the git tree, so this must not deploy as a phantom
    # skill.
    mkdir -p "$SANDBOX/src/real-skill" "$SANDBOX/src/orphan-skill/scripts/__pycache__"
    echo body > "$SANDBOX/src/real-skill/SKILL.md"
    echo stale > "$SANDBOX/src/orphan-skill/scripts/__pycache__/stale.pyc"

    run deploy_home_skills "$SANDBOX/src" "$SANDBOX/dest"
    assert_success
    assert_output --partial "Not deploying"
    assert_output --partial "orphan-skill"
    assert_output --partial "no SKILL.md"

    [ -d "$SANDBOX/dest/real-skill" ]        # valid skill still deployed
    [ ! -e "$SANDBOX/dest/orphan-skill" ]    # non-skill dir excluded, not deployed
    run grep -qx "orphan-skill" "$SANDBOX/dest/.deployed-skills"
    assert_failure                          # never enters the manifest
}

@test "deploy_home_skills non-skill dir guard stays quiet on a normal, fully-populated source" {
    mkdir -p "$SANDBOX/src/alpha" "$SANDBOX/src/beta"
    echo a > "$SANDBOX/src/alpha/SKILL.md"
    echo b > "$SANDBOX/src/beta/SKILL.md"

    run deploy_home_skills "$SANDBOX/src" "$SANDBOX/dest"
    assert_success
    refute_output --partial "Not deploying"
    [ -d "$SANDBOX/dest/alpha" ]
    [ -d "$SANDBOX/dest/beta" ]
}

# ── gate_graphify_skill (FR-012 disable cleanup / FR-010 collision reconcile) ──

@test "gate_graphify_skill removes the deployed skill when disabled" {
    mkdir -p "$SANDBOX/home/skills/graphify"
    echo wrapper > "$SANDBOX/home/skills/graphify/SKILL.md"
    export ENABLE_GRAPHIFY=false
    export CURSOR_TARGET_DIR="$SANDBOX/na1" GEMINI_TARGET_DIR="$SANDBOX/na2" \
        CODEX_TARGET_DIR="$SANDBOX/na3" ANTIGRAVITY_TARGET_DIR="$SANDBOX/na4"

    run gate_graphify_skill "$SANDBOX/home/skills"
    assert_success
    [ ! -e "$SANDBOX/home/skills/graphify" ]   # deployed copy removed (clean opt-out)
}

@test "gate_graphify_skill prunes an independent (non-symlink) assistant graphify dir when disabled" {
    mkdir -p "$SANDBOX/home/skills"
    mkdir -p "$SANDBOX/cursor/skills/graphify"   # real, NOT a symlink to home
    echo x > "$SANDBOX/cursor/skills/graphify/SKILL.md"
    export ENABLE_GRAPHIFY=false
    export CURSOR_TARGET_DIR="$SANDBOX/cursor" GEMINI_TARGET_DIR="$SANDBOX/na2" \
        CODEX_TARGET_DIR="$SANDBOX/na3" ANTIGRAVITY_TARGET_DIR="$SANDBOX/na4"

    run gate_graphify_skill "$SANDBOX/home/skills"
    assert_success
    [ ! -e "$SANDBOX/cursor/skills/graphify" ]
}

@test "gate_graphify_skill leaves a symlinked assistant skills dir untouched when disabled" {
    mkdir -p "$SANDBOX/home/skills" "$SANDBOX/cursor"
    ln -s "$SANDBOX/home/skills" "$SANDBOX/cursor/skills"   # symlink to home (normal case)
    export ENABLE_GRAPHIFY=false
    export CURSOR_TARGET_DIR="$SANDBOX/cursor" GEMINI_TARGET_DIR="$SANDBOX/na2" \
        CODEX_TARGET_DIR="$SANDBOX/na3" ANTIGRAVITY_TARGET_DIR="$SANDBOX/na4"

    run gate_graphify_skill "$SANDBOX/home/skills"
    assert_success
    [ -L "$SANDBOX/cursor/skills" ]   # symlink not deleted (loop continues on -L)
}

@test "gate_graphify_skill reconciles foreign 'graphify install' residue when enabled" {
    mkdir -p "$SANDBOX/home/skills/graphify/references"
    echo wrapper > "$SANDBOX/home/skills/graphify/SKILL.md"
    echo ref > "$SANDBOX/home/skills/graphify/references/update.md"
    echo "0.9.1" > "$SANDBOX/home/skills/graphify/.graphify_version"
    export ENABLE_GRAPHIFY=true

    run gate_graphify_skill "$SANDBOX/home/skills"
    assert_success
    [ -f "$SANDBOX/home/skills/graphify/SKILL.md" ]             # managed wrapper kept
    [ ! -e "$SANDBOX/home/skills/graphify/references" ]         # foreign sidecar removed
    [ ! -e "$SANDBOX/home/skills/graphify/.graphify_version" ]  # foreign marker removed
}

@test "gate_graphify_skill leaves a clean enabled deploy untouched" {
    mkdir -p "$SANDBOX/home/skills/graphify"
    echo wrapper > "$SANDBOX/home/skills/graphify/SKILL.md"
    export ENABLE_GRAPHIFY=true

    run gate_graphify_skill "$SANDBOX/home/skills"
    assert_success
    [ -f "$SANDBOX/home/skills/graphify/SKILL.md" ]   # untouched
}

@test "deploy_home_skills falls back to cp when rsync is unavailable" {
    # Minimal hosts (some slim Linux images) ship without rsync. The copy must
    # still happen via cp rather than silently no-op or hard-fail under set -e.
    mkdir -p "$SANDBOX/src/demo/sub"
    echo body > "$SANDBOX/src/demo/SKILL.md"
    echo leaf > "$SANDBOX/src/demo/sub/extra.md"

    # Restricted PATH with the coreutils the function needs, but NO rsync.
    local nobin="$SANDBOX/nobin"
    mkdir -p "$nobin"
    local t p
    for t in rm mkdir cp find wc tr mv sed sort; do
        p="$(command -v "$t")" && ln -s "$p" "$nobin/$t"
    done

    run env SRC="$SANDBOX/src" DEST="$SANDBOX/dest" NOBIN="$nobin" REPO="$REPO_ROOT" bash -c '
        export PATH="$NOBIN"
        # shellcheck disable=SC1090
        source "$REPO/bootstrap/lib/common.sh"
        command -v rsync >/dev/null 2>&1 && { echo "rsync STILL ON PATH"; exit 3; }
        deploy_home_skills "$SRC" "$DEST"
    '
    assert_success
    [ -f "$SANDBOX/dest/demo/SKILL.md" ]
    [ -f "$SANDBOX/dest/demo/sub/extra.md" ]   # nested content copied too
    assert_equal "$(cat "$SANDBOX/dest/demo/SKILL.md")" "body"
}

@test "check_rsync is a no-op success when rsync is already present" {
    # shellcheck disable=SC1090
    source "$REPO_ROOT/bootstrap/lib/install.sh"
    PLATFORM=linux PKG_MANAGER=apt
    command_exists rsync || skip "rsync not installed in this environment"
    run check_rsync
    assert_success
    assert_output --partial "rsync is installed"
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
    deploy_sync_skills() { :; }

    run deploy_configs
    assert_success

    # Real skill dirs landed (sampled), and skills is NOT a symlink.
    [ -d "$TARGET_DIR/skills/code-audit" ]
    [ ! -L "$TARGET_DIR/skills" ]
    # The compat symlink was never copied verbatim into the home dir.
    [ ! -e "$TARGET_DIR/skills/skills" ]
    # No literal tilde dir created anywhere under the sandbox.
    run find "$SANDBOX" -maxdepth 6 -name '~'
    assert_output ""
}

@test "deploy_antigravity_configs symlinks config/skills/.plans but not scripts/prompts" {
    export TARGET_DIR="$SANDBOX/home/.claude"
    export ANTIGRAVITY_TARGET_DIR="$SANDBOX/home/.antigravity"
    mkdir -p "$TARGET_DIR/skills/demo" "$TARGET_DIR/scripts" \
        "$TARGET_DIR/config" "$TARGET_DIR/prompts" "$TARGET_DIR/.plans"

    # shellcheck disable=SC1090
    source "$REPO_ROOT/bootstrap/lib/deploy.sh"

    run deploy_antigravity_configs
    assert_success

    # agy is a parallel_agent provider, not an orchestrator: no scripts/prompts.
    for link in skills config .plans; do
        [ -L "$ANTIGRAVITY_TARGET_DIR/$link" ] || { echo "missing link: $link"; false; }
    done
    [ ! -e "$ANTIGRAVITY_TARGET_DIR/scripts" ] || { echo "scripts must not be linked"; false; }
    [ ! -e "$ANTIGRAVITY_TARGET_DIR/prompts" ] || { echo "prompts must not be linked"; false; }
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

    for link in skills config .plans; do
        [ -L "$ANTIGRAVITY_TARGET_DIR/$link" ] || { echo "missing link: $link"; false; }
    done
    [ ! -e "$ANTIGRAVITY_TARGET_DIR/scripts" ] || { echo "scripts must not be linked"; false; }
    [ ! -e "$ANTIGRAVITY_TARGET_DIR/prompts" ] || { echo "prompts must not be linked"; false; }
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
