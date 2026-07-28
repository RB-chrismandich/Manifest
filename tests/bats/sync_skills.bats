#!/usr/bin/env bats
# Tests for configs/claude/scripts/sync-skills.sh

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
SCRIPT="$REPO_ROOT/configs/claude/scripts/sync-skills.sh"

setup() {
    # Isolate the APM domain registry — this suite drives the LEGACY writer, which
    # correctly stands down for a domain APM owns. Without this it passes in CI
    # and fails on any machine where a domain has been activated (SC-006).
    export MANIFEST_APM_DOMAINS="$BATS_TEST_TMPDIR/no-apm-domains.yml"
    printf 'domains: []\n' > "$MANIFEST_APM_DOMAINS"

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
    mkdir -p "$MANIFEST_ROOT/.apm/skills/demo-skill"
    echo "body" > "$MANIFEST_ROOT/.apm/skills/demo-skill/SKILL.md"

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

@test "exits non-zero when .apm/skills/ is missing" {
    rm -rf "$MANIFEST_ROOT/.apm/skills"
    run bash "$SCRIPT"
    assert_failure
    assert_output --partial "skills source not found"
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

# ---------------------------------------------------------------------------
# agent_roster.yml-driven secondary targets: the secondary sync loop is
# derived from agent_roster.yml's home_dir field, not a hardcoded 4-agent
# list. Mirrors the acceptance-test pattern from
# tests/bats/check_status.bats ("6th roster-only agent...without a script
# edit") and tests/python/test_reconcile_policy.py::test_sixth_agent_extends_fleet_via_config_only
# -- a synthetic 6th agent added ONLY to a fresh, env-var-pointed roster
# fixture (never the real registry) must be picked up with zero changes to
# sync-skills.sh.
# ---------------------------------------------------------------------------

@test "6th roster-only agent is picked up by the secondary sync loop without a script edit" {
    cat > "$SANDBOX/agent_roster.yml" << 'EOF'
agents:
  claude:
    name: claude
    binary: claude
    home_dir: ~/.claude
    prompt_args: ["-p", "{prompt}"]
    model_args: ["--model", "{model}"]
    auth_check: "claude auth status"
    enabled_default: true
  gemini:
    name: gemini
    binary: gemini
    home_dir: ~/.gemini
    prompt_args: ["-p", "{prompt}"]
    model_args: ["-m", "{model}"]
    auth_check: "gemini auth status"
    enabled_default: true
  cursor:
    name: cursor
    binary: cursor-agent
    home_dir: ~/.cursor
    prompt_args: ["{prompt}"]
    model_args: ["--model", "{model}"]
    auth_check: "cursor-agent --version"
    enabled_default: true
  codex:
    name: codex
    binary: codex
    home_dir: ~/.codex
    prompt_args: ["{prompt}"]
    model_args: ["--model", "{model}"]
    auth_check: "codex login status"
    enabled_default: true
  antigravity:
    name: antigravity
    binary: agy
    home_dir: ~/.antigravity
    prompt_args: ["--print", "{prompt}"]
    model_args: ["--model", "{model}"]
    auth_check: "agy models"
    enabled_default: true
  beta:
    name: beta
    binary: beta-agent
    home_dir: ~/.beta
    prompt_args: ["{prompt}"]
    model_args: ["--model", "{model}"]
    auth_check: "beta-agent --version"
    enabled_default: true
EOF
    export MANIFEST_AGENT_ROSTER="$SANDBOX/agent_roster.yml"
    mkdir -p "$HOME/.beta/skills"
    run bash "$SCRIPT"
    assert_success
    grep -q ".beta/skills" "$RSYNC_LOG"
}

@test "awk fallback parses the 6th agent's home_dir when python3 lacks PyYAML" {
    # Restricted PATH excludes Homebrew (/usr/local/bin, /opt/homebrew/bin), so
    # this resolves to the stock /usr/bin/python3 -- which has no PyYAML on
    # macOS -- forcing the real awk fallback tier (mirrors check_status.bats's
    # setup(), and the exact scenario load_agent_roster_home_dirs's `|| true`
    # guard exists for: a failing python3 command substitution must not trip
    # `set -euo pipefail` before the fallback ever runs).
    cat > "$SANDBOX/agent_roster.yml" << 'EOF'
agents:
  claude:
    name: claude
    binary: claude
    home_dir: ~/.claude
    prompt_args: ["-p", "{prompt}"]
    model_args: ["--model", "{model}"]
    auth_check: "claude auth status"
    enabled_default: true
  beta:
    name: beta
    binary: beta-agent
    home_dir: ~/.beta
    prompt_args: ["{prompt}"]
    model_args: ["--model", "{model}"]
    auth_check: "beta-agent --version"
    enabled_default: true
EOF
    export MANIFEST_AGENT_ROSTER="$SANDBOX/agent_roster.yml"
    mkdir -p "$HOME/.beta/skills"
    PATH="$MOCK_BIN:/usr/bin:/bin" run bash "$SCRIPT"
    assert_success
    grep -q ".beta/skills" "$RSYNC_LOG"
}

@test "claude never appears in the roster-derived secondary loop (no double-sync)" {
    export MANIFEST_AGENT_ROSTER="$SANDBOX/agent_roster.yml"
    cat > "$MANIFEST_AGENT_ROSTER" << 'EOF'
agents:
  claude:
    name: claude
    binary: claude
    home_dir: ~/.claude
    prompt_args: ["-p", "{prompt}"]
    model_args: ["--model", "{model}"]
    auth_check: "claude auth status"
    enabled_default: true
EOF
    run bash "$SCRIPT"
    assert_success
    # Exactly one rsync invocation total: the primary ~/.claude/skills sync.
    # If claude leaked into the secondary loop this would be 2.
    [ "$(grep -c "rsync " "$RSYNC_LOG")" -eq 1 ]
}
