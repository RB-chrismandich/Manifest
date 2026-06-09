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
    cat > "$MOCK_BIN/skillclaw" << 'EOF'
#!/usr/bin/env bash
echo "skillclaw $*" >> "$SKILLCLAW_PROMOTE_LOG"
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
    chmod +x "$MOCK_BIN/git_ops.sh" "$MOCK_BIN/skillclaw" "$MOCK_BIN/git"
    export SKILLCLAW_GITOPS="$MOCK_BIN/git_ops.sh"
    export PATH="$MOCK_BIN:$PATH"
    export SKILLCLAW_PROMOTE_LOG="$SANDBOX/log"
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

@test "skill-evolve SKILL.md has valid frontmatter and points at the script" {
    local f="$REPO_ROOT/.skillshare/skills/skill-evolve/SKILL.md"
    [ -f "$f" ]
    head -1 "$f" | grep -q '^---$'
    grep -q "^name: skill-evolve$" "$f"
    grep -q "skillclaw_promote.sh" "$f"
}

@test "promote runs ingest+evolve scripts instead of the skillclaw binary" {
  run grep -E 'skillclaw_(ingest|evolve)\.py' "$REPO_ROOT/configs/claude/scripts/skillclaw_promote.sh"
  [ "$status" -eq 0 ]
  run grep -c 'skillclaw evolve --mode workflow' "$REPO_ROOT/configs/claude/scripts/skillclaw_promote.sh"
  [ "$output" -eq 0 ]
}

@test "promote warns when candidates are rejected" {
  run grep -Ei 'failed schema validation|rejected' "$REPO_ROOT/configs/claude/scripts/skillclaw_promote.sh"
  [ "$status" -eq 0 ]
}
