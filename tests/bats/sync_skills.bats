#!/usr/bin/env bats
# Tests for configs/claude/scripts/sync-skills.sh

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
SCRIPT="$REPO_ROOT/configs/claude/scripts/sync-skills.sh"

setup() {
    export BATS_TMPDIR="${BATS_TMPDIR:-/tmp}"
    SANDBOX=$(mktemp -d "$BATS_TMPDIR/sync_skills.XXXXXX")
    MOCK_BIN="$SANDBOX/bin"
    mkdir -p "$MOCK_BIN"

    # Mock rsync: log every invocation, succeed
    cat > "$MOCK_BIN/rsync" <<'STUB'
#!/usr/bin/env bash
echo "rsync $*" >> "$RSYNC_LOG"
STUB
    chmod +x "$MOCK_BIN/rsync"
    export RSYNC_LOG="$SANDBOX/rsync.log"

    # Fake manifest root with a skills source
    export MANIFEST_ROOT="$SANDBOX/repo"
    mkdir -p "$MANIFEST_ROOT/.skillshare/skills/demo-skill"
    echo "body" > "$MANIFEST_ROOT/.skillshare/skills/demo-skill/SKILL.md"

    # Fake home with required ~/.claude/skills target
    export HOME="$SANDBOX/home"
    mkdir -p "$HOME/.claude/skills"

    export PATH="$MOCK_BIN:$PATH"
}

teardown() {
    [[ -n "$SANDBOX" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"
}

@test "exits non-zero with clear message when MANIFEST_ROOT is unset" {
    run env -u MANIFEST_ROOT bash "$SCRIPT"
    assert_failure
    assert_output --partial "MANIFEST_ROOT not set"
}

@test "exits non-zero when MANIFEST_ROOT does not exist" {
    run env MANIFEST_ROOT="/nonexistent/path" bash "$SCRIPT"
    assert_failure
    assert_output --partial "not found"
}

@test "exits non-zero when .skillshare/skills/ is missing" {
    rm -rf "$MANIFEST_ROOT/.skillshare/skills"
    run bash "$SCRIPT"
    assert_failure
    assert_output --partial "skills source not found"
}

@test "runs rsync to ~/.claude/skills/ when skillshare is absent" {
    # Use restricted PATH that excludes Homebrew (/usr/local/bin, /opt/homebrew/bin)
    # to ensure skillshare is not found and the "not installed" path is tested
    PATH="$MOCK_BIN:/usr/bin:/bin" run bash "$SCRIPT"
    assert_success
    assert_output --partial "skillshare not installed"
    grep -q ".claude/skills" "$RSYNC_LOG"
}

@test "calls skillshare sync when skillshare is on PATH" {
    export SKILLSHARE_LOG="$SANDBOX/ss.log"
    cat > "$MOCK_BIN/skillshare" <<'STUB'
#!/usr/bin/env bash
echo "skillshare $*" >> "$SKILLSHARE_LOG"
STUB
    chmod +x "$MOCK_BIN/skillshare"

    run bash "$SCRIPT"
    assert_success
    grep -q "skillshare sync" "$SKILLSHARE_LOG"
}

@test "skips IDE target when directory does not exist" {
    # ~/.cursor/skills does NOT exist under the fake HOME
    run bash "$SCRIPT"
    assert_success
    if [[ -f "$RSYNC_LOG" ]]; then
        run grep ".cursor/skills" "$RSYNC_LOG"
        assert_failure
    fi
}

@test "syncs IDE target when directory exists" {
    mkdir -p "$HOME/.cursor/skills"
    run bash "$SCRIPT"
    assert_success
    grep -q ".cursor/skills" "$RSYNC_LOG"
}

@test "never passes --delete to rsync (merge-then-manifest-prune model)" {
    run bash "$SCRIPT"
    assert_success
    if [[ -f "$RSYNC_LOG" ]]; then
        run grep -- "--delete" "$RSYNC_LOG"
        assert_failure
    fi
}

# Behavioral tests below use the REAL rsync (restricted PATH without MOCK_BIN).
REAL_PATH="/usr/bin:/bin:/usr/sbin"

@test "foreign (non-manifest) skill survives a sync" {
    mkdir -p "$HOME/.claude/skills/my-local-skill"
    echo "keep me" > "$HOME/.claude/skills/my-local-skill/SKILL.md"
    printf 'demo-skill\n' > "$HOME/.claude/skills/.deployed-skills"
    PATH="$REAL_PATH" run bash "$SCRIPT"
    assert_success
    [ -f "$HOME/.claude/skills/my-local-skill/SKILL.md" ]
    [ -f "$HOME/.claude/skills/demo-skill/SKILL.md" ]
}

@test ".deployed-skills manifest survives and is rewritten to current source" {
    printf 'demo-skill\n' > "$HOME/.claude/skills/.deployed-skills"
    PATH="$REAL_PATH" run bash "$SCRIPT"
    assert_success
    [ -f "$HOME/.claude/skills/.deployed-skills" ]
    grep -qx "demo-skill" "$HOME/.claude/skills/.deployed-skills"
}

@test "prunes a manifest-listed skill that was removed from the source" {
    # Pins the invariant the --delete replacement must preserve (deploy_home_skills parity).
    mkdir -p "$HOME/.claude/skills/old-skill"
    printf 'demo-skill\nold-skill\n' > "$HOME/.claude/skills/.deployed-skills"
    PATH="$REAL_PATH" run bash "$SCRIPT"
    assert_success
    [ ! -d "$HOME/.claude/skills/old-skill" ]
}

@test "skips a secondary home that is a symlink to the primary skills dir" {
    mkdir -p "$HOME/.cursor"
    ln -s "$HOME/.claude/skills" "$HOME/.cursor/skills"
    run bash "$SCRIPT"
    assert_success
    assert_output --partial "skipping"
    if [[ -f "$RSYNC_LOG" ]]; then
        run grep ".cursor/skills" "$RSYNC_LOG"
        assert_failure
    fi
}
