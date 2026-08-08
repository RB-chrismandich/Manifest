#!/usr/bin/env bats
# Tests for scripts/skillclaw_promote.sh (mocked git_ops + skillclaw + git)

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
SCRIPT="$REPO_ROOT/configs/claude/scripts/skillclaw_promote.sh"

setup() {
    export BATS_TMPDIR="${BATS_TMPDIR:-/tmp}"
    SANDBOX=$(mktemp -d "$BATS_TMPDIR/skillclaw_promote.XXXXXX")
    export SKILLCLAW_EVOLVED="$SANDBOX/evolved"
    export SKILLCLAW_COMMITTED="$SANDBOX/committed"
    export SKILLCLAW_SESSIONS="$SANDBOX/sessions"
    mkdir -p "$SKILLCLAW_EVOLVED/alpha" "$SKILLCLAW_COMMITTED" "$SKILLCLAW_SESSIONS"
    printf -- '---\nname: alpha\ndescription: d\n---\nbody\n' > "$SKILLCLAW_EVOLVED/alpha/SKILL.md"

    export MOCK_BIN="$SANDBOX/bin"; mkdir -p "$MOCK_BIN"
    cat > "$MOCK_BIN/git_ops.sh" << 'EOF'
#!/usr/bin/env bash
echo "git_ops.sh $*" >> "$SKILLCLAW_PROMOTE_LOG"
[ "$1" = "pr-create" ] && echo "https://example.test/pr/1"
exit 0
EOF
    cat > "$MOCK_BIN/git" << 'EOF'
#!/usr/bin/env bash
case "$1" in
  rev-parse) echo "abc1234" ;;
  commit) echo "git-commit" >> "$SKILLCLAW_PROMOTE_LOG" ;;
  switch|add) : ;;
  *) : ;;
esac
exit 0
EOF
    chmod +x "$MOCK_BIN/git_ops.sh" "$MOCK_BIN/git"
    export SKILLCLAW_GITOPS="$MOCK_BIN/git_ops.sh"
    export HOME="$SANDBOX/home"
    mkdir -p "$HOME"
    # shellcheck disable=SC1091
    source "$REPO_ROOT/tests/test_helper/stub_home_runtime.bash"
    stub_home_manifest_runtime "$REPO_ROOT"
    export MANIFEST="$HOME/.claude/.venv/bin/manifest"
    export PATH="$MOCK_BIN:$PATH"
    export SKILLCLAW_PROMOTE_LOG="$SANDBOX/log"
    export SKILLCLAW_AUDIT_DIR="$SANDBOX/skillclaw"
    mkdir -p "$SKILLCLAW_AUDIT_DIR"
    : > "$SKILLCLAW_PROMOTE_LOG"
}

teardown() {
    [[ -n "$SANDBOX" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"
}

@test "dry-run prints diff table and makes no PR" {
    run bash "$SCRIPT" --no-evolve
    assert_success
    assert_output --partial "alpha"
    assert_output --partial "NEW"
    run grep -c "pr-create" "$SKILLCLAW_PROMOTE_LOG"
    assert_output "0"
}

@test "--apply with no open PR creates exactly one PR" {
    export SKILLCLAW_OPEN_PR=""
    run bash "$SCRIPT" --apply --no-evolve
    assert_success
    run grep -c "pr-create" "$SKILLCLAW_PROMOTE_LOG"
    assert_output "1"
    run grep -c "git-commit" "$SKILLCLAW_PROMOTE_LOG"
    assert_output "1"
}

@test "--apply aborts when an open evolve PR already exists (Option A)" {
    export SKILLCLAW_OPEN_PR="https://example.test/pr/9"
    run bash "$SCRIPT" --apply --no-evolve
    assert_failure
    assert_output --partial "open"
    run grep -c "pr-create" "$SKILLCLAW_PROMOTE_LOG"
    assert_output "0"
}

@test "skill-evolve SKILL.md has valid frontmatter and points at its bundle-local command" {
    local f="$REPO_ROOT/.apm/skills/skill-evolve/SKILL.md"
    [ -f "$f" ]
    head -1 "$f" | grep -q '^---$'
    grep -q "^name: skill-evolve$" "$f"
    grep -q "scripts/skill_evolve.py" "$f"
}

@test "promote runs manifest skillclaw ingest/evolve/promote instead of legacy scripts" {
  run grep -E 'skillclaw_cmd (ingest|evolve|promote)' "$REPO_ROOT/configs/claude/scripts/skillclaw_promote.sh"
  [ "$status" -eq 0 ]
  run grep -cE 'skillclaw_(ingest|evolve|promote)\.py' "$REPO_ROOT/configs/claude/scripts/skillclaw_promote.sh"
  [ "$output" -eq 0 ]
}

@test "promote warns when candidates are rejected" {
  run grep -Ei 'failed schema validation|rejected' "$REPO_ROOT/configs/claude/scripts/skillclaw_promote.sh"
  [ "$status" -eq 0 ]
}

@test "promote mints a run_id and records it in promote.log" {
    run bash "$SCRIPT" --no-evolve
    assert_success
    run grep -c '"event": "run_start"' "$SKILLCLAW_AUDIT_DIR/promote.log"
    assert_output "1"
    run grep -Eq '"run_id": "[0-9]{8}T[0-9]{6}Z-[0-9]+"' "$SKILLCLAW_AUDIT_DIR/promote.log"
    assert_success
}

@test "run_start records real pipeline config (window_days/token_budget), not zeros" {
    run bash "$SCRIPT" --no-evolve
    assert_success
    run grep '"event": "run_start"' "$SKILLCLAW_AUDIT_DIR/promote.log"
    assert_output --partial '"window_days": 30'
    assert_output --partial '"token_budget": 100000'
    refute_output --partial '"window_days": 0'
}

@test "--status renders from a seeded status.json" {
    cat > "$SKILLCLAW_AUDIT_DIR/status.json" << 'EOF'
{"run_id":"20260609T230501Z-4821","state":"done","stage":"-",
 "totals":{"ingested":12,"candidates":3,"dropped":0},
 "pr_url":"https://example.test/pr/7","total_seconds":252}
EOF
    run bash "$SCRIPT" --status
    assert_success
    assert_output --partial "done"
    assert_output --partial "3 candidates"
    assert_output --partial "PR https://example.test/pr/7"
}

@test "stage transitions are logged as stage_start events" {
    run bash "$SCRIPT" --no-evolve
    assert_success
    run grep -c '"event": "stage_start"' "$SKILLCLAW_AUDIT_DIR/promote.log"
    [ "$output" -ge 1 ]
}

@test "finalization trap records run_error + failed status on mid-run interrupt" {
    # Make `git switch` fail so --apply dies after run_start/stages -> trap fires.
    cat > "$MOCK_BIN/git" << 'EOF'
#!/usr/bin/env bash
case "$1" in
  rev-parse) echo "abc1234" ;;
  switch) echo "boom" >&2; exit 1 ;;
  *) : ;;
esac
exit 0
EOF
    chmod +x "$MOCK_BIN/git"
    export SKILLCLAW_OPEN_PR=""
    run bash "$SCRIPT" --apply --no-evolve
    assert_failure
    run grep -c '"event": "run_error"' "$SKILLCLAW_AUDIT_DIR/promote.log"
    [ "$output" -ge 1 ]
    run grep -q '"state": "failed"' "$SKILLCLAW_AUDIT_DIR/status.json"
    assert_success
}

@test "unwritable audit path does not abort the run" {
    # Point the audit dir inside a regular file -> every audit call fails open.
    printf 'x' > "$SANDBOX/blocker"
    export SKILLCLAW_AUDIT_DIR="$SANDBOX/blocker/sub"
    run bash "$SCRIPT" --no-evolve
    assert_success
}

@test "classify stage logs a stage_end with seconds" {
    run bash "$SCRIPT" --no-evolve
    assert_success
    run grep -E '"stage": "classify".*"event": "stage_end"' "$SKILLCLAW_AUDIT_DIR/promote.log"
    assert_success
}

# Repo-side fail-open contract for capture (docs/SKILLCLAW.md: capture is passive,
# no daemon/socket/proxy). The equivalent decision point is here: ingest reading a
# transcript it cannot access must not abort the pipeline — it degrades to "0
# ingested, continue" rather than blocking scrub/evolve/classify.
@test "ingest failure on an unreadable transcript is fail-open: pipeline continues" {
    if [[ "$(id -u)" -eq 0 ]]; then
        skip "root ignores file permissions"
    fi
    export SKILLCLAW_TRANSCRIPTS="$SANDBOX/transcripts"
    mkdir -p "$SKILLCLAW_TRANSCRIPTS"
    local tf="$SKILLCLAW_TRANSCRIPTS/broken.jsonl"
    printf '{"type":"user","message":{"role":"user","content":"hi"}}\n' > "$tf"
    # Backdate past the 5-minute settle window so ingest actually opens the file
    # (files newer than settle_minutes are skipped, not read).
    python3 -c "import os, time; t = time.time() - 3600; os.utime('$tf', (t, t))"
    chmod 000 "$tf"
    run bash "$SCRIPT"
    chmod 644 "$tf" # restore so teardown's rm -rf can remove it
    assert_success
    assert_output --partial "ingest returned non-zero (continuing)"
    assert_output --partial "classify"
}

@test "EVOLVE_CLI seam: evolve stage invokes the stub named by EVOLVE_CLI, not a hardcoded claude" {
    # llm-invoke-stdin pattern: EVOLVE_CLI is role-named, vendor-default.
    # Pre-seed a session so evolve() actually calls the runner (an empty
    # sessions dir short-circuits before any subprocess call).
    export SKILLCLAW_TRANSCRIPTS="$SANDBOX/transcripts_empty"
    mkdir -p "$SKILLCLAW_TRANSCRIPTS"
    cat > "$SKILLCLAW_SESSIONS/preseeded.json" << 'EOF'
{"session_id": "preseeded", "turns": [{"role": "user", "blocks": [{"kind": "text", "text": "do a thing"}]}]}
EOF
    # #584 resolves EVOLVE_CLI as a *binary override* for a configured provider
    # (agents/cli_invoke.resolve_cli_route reads cli_agents from
    # ~/.claude/config/parallel_agent.yml). Provide a claude provider spec and pin
    # EVOLVE_PROVIDER so a provider resolves; EVOLVE_CLI then swaps that provider's
    # binary to our stub — proving the seam is honored/swappable, not hardcoded to
    # claude. (#584 also inserts --model <tier> before -p, hence the .*-p match.)
    mkdir -p "$HOME/.claude/config"
    cat > "$HOME/.claude/config/parallel_agent.yml" << 'EOF'
cli_agents:
  claude:
    binary: claude
    base_args: []
    model_args: ["--model", "{model}"]
    prompt_args: ["-p", "{prompt}"]
    output: stdout
model_tiers:
  claude:
    sonnet: "claude-sonnet-5"
EOF
    export EVOLVE_PROVIDER="claude"
    export EVOLVE_CLI="fake_evolve_cli"
    cat > "$MOCK_BIN/fake_evolve_cli" << 'EOF'
#!/usr/bin/env bash
echo "fake_evolve_cli $*" >> "$SKILLCLAW_PROMOTE_LOG"
cat > /dev/null
echo "NO_SKILLS"
exit 0
EOF
    chmod +x "$MOCK_BIN/fake_evolve_cli"
    run bash "$SCRIPT"
    assert_success
    run grep -Ec "fake_evolve_cli.*-p" "$SKILLCLAW_PROMOTE_LOG"
    assert_output "1"
}

@test "ingest failure still reaches and logs the classify stage in the audit log" {
    if [[ "$(id -u)" -eq 0 ]]; then
        skip "root ignores file permissions"
    fi
    export SKILLCLAW_TRANSCRIPTS="$SANDBOX/transcripts2"
    mkdir -p "$SKILLCLAW_TRANSCRIPTS"
    local tf="$SKILLCLAW_TRANSCRIPTS/broken.jsonl"
    printf '{"type":"user","message":{"role":"user","content":"hi"}}\n' > "$tf"
    python3 -c "import os, time; t = time.time() - 3600; os.utime('$tf', (t, t))"
    chmod 000 "$tf"
    run bash "$SCRIPT"
    chmod 644 "$tf"
    assert_success
    run grep -c '"stage": "classify", "event": "stage_start"' "$SKILLCLAW_AUDIT_DIR/promote.log"
    assert_output "1"
}
