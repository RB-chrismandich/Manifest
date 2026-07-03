#!/usr/bin/env bats
# write_deploy_stamp(): records deploy-source tree hashes so the SessionStart
# checker can detect a clone that advanced past the last deploy.

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."

setup() {
    TMP="$(mktemp -d)"
    CLONE="$TMP/clone"
    TGT="$TMP/target"
    mkdir -p "$CLONE/configs/claude" "$CLONE/.skillshare/skills/demo" "$TGT/config"
    echo "orchestration guide" > "$CLONE/configs/claude/CLAUDE.md"
    echo "demo skill" > "$CLONE/.skillshare/skills/demo/SKILL.md"
    git -C "$CLONE" init -q
    git -C "$CLONE" config user.email t@t.test
    git -C "$CLONE" config user.name test
    git -C "$CLONE" add -A
    git -C "$CLONE" commit -qm init

    print_info() { echo "INFO: $*"; }
    print_success() { echo "OK: $*"; }
    export -f print_info print_success 2>/dev/null || true
    # shellcheck disable=SC1091
    source "$REPO_ROOT/bootstrap/lib/deploy.sh" 2>/dev/null || true
}

teardown() { rm -rf "$TMP"; }

stamp_val() { grep "^$1=" "$TGT/config/deploy_stamp" | cut -d= -f2-; }

@test "writes a stamp with all six keys and correct tree hashes" {
    run write_deploy_stamp "$CLONE" "$TGT"
    assert_success
    [ -f "$TGT/config/deploy_stamp" ]
    assert_equal "$(stamp_val tree_configs)" "$(git -C "$CLONE" rev-parse HEAD:configs)"
    assert_equal "$(stamp_val tree_skills)" "$(git -C "$CLONE" rev-parse HEAD:.skillshare/skills)"
    assert_equal "$(stamp_val head_sha)" "$(git -C "$CLONE" rev-parse HEAD)"
    assert_equal "$(stamp_val dirty)" "false"
    assert_equal "$(stamp_val clone_path)" "$CLONE"
    [ -n "$(stamp_val deployed_at)" ]
}

@test "uncommitted change under configs marks dirty=true" {
    echo "edit" >> "$CLONE/configs/claude/CLAUDE.md"
    write_deploy_stamp "$CLONE" "$TGT"
    assert_equal "$(stamp_val dirty)" "true"
}

@test "uncommitted change OUTSIDE deploy sources keeps dirty=false" {
    mkdir -p "$CLONE/tests"
    echo "wip" > "$CLONE/tests/wip.txt"
    write_deploy_stamp "$CLONE" "$TGT"
    assert_equal "$(stamp_val dirty)" "false"
}

@test "non-git source dir writes no stamp and still returns 0" {
    local NONGIT="$TMP/nongit" TGT2="$TMP/t2"
    mkdir -p "$NONGIT/configs" "$TGT2/config"
    run write_deploy_stamp "$NONGIT" "$TGT2"
    assert_success
    [ ! -f "$TGT2/config/deploy_stamp" ]
}

# --- checker: deploy_stamp_check.sh ---

CHECK="$BATS_TEST_DIRNAME/../../configs/claude/scripts/deploy_stamp_check.sh"

# Build a fake HOME whose deploy_stamp points at $CLONE, deployed at its
# current (clean) HEAD. $1 overrides the dirty field (default false).
write_fake_stamp() {
    local dirty="${1:-false}"
    mkdir -p "$FHOME/.claude/config"
    cat > "$FHOME/.claude/config/deploy_stamp" << EOF
tree_configs=$(git -C "$CLONE" rev-parse HEAD:configs)
tree_skills=$(git -C "$CLONE" rev-parse HEAD:.skillshare/skills)
head_sha=$(git -C "$CLONE" rev-parse HEAD)
dirty=$dirty
clone_path=$CLONE
deployed_at=2026-07-03T00:00:00Z
EOF
}

# Advance the clone so its source trees differ from the stamp.
advance_clone() {
    echo "new content" >> "$CLONE/configs/claude/CLAUDE.md"
    git -C "$CLONE" add -A
    git -C "$CLONE" commit -qm advance
}

setup_checker() {
    FHOME="$TMP/home"; mkdir -p "$FHOME/.manifest"
    # origin/HEAD so the default-branch resolver finds 'main' (or the init branch)
    DEF_BRANCH="$(git -C "$CLONE" rev-parse --abbrev-ref HEAD)"
    git -C "$CLONE" symbolic-ref "refs/remotes/origin/HEAD" "refs/remotes/origin/$DEF_BRANCH" 2>/dev/null || true
}

@test "checker: silent when no stamp file" {
    setup_checker
    run env HOME="$FHOME" MANIFEST_STATE_ROOT="$FHOME/.manifest" bash "$CHECK"
    assert_success
    assert_output ""
}

@test "checker: silent when clone_path does not exist" {
    setup_checker
    mkdir -p "$FHOME/.claude/config"
    cat > "$FHOME/.claude/config/deploy_stamp" << EOF
tree_configs=x
tree_skills=y
head_sha=z
dirty=false
clone_path=$TMP/gone
deployed_at=2026-07-03T00:00:00Z
EOF
    run env HOME="$FHOME" bash "$CHECK"
    assert_success
    assert_output ""
}

@test "checker: silent on a feature branch even when hashes differ" {
    setup_checker
    write_fake_stamp
    advance_clone
    git -C "$CLONE" checkout -q -b feature/x
    run env HOME="$FHOME" MANIFEST_STATE_ROOT="$FHOME/.manifest" bash "$CHECK"
    assert_success
    assert_output ""
}

@test "checker: silent when configs dirty on main" {
    setup_checker
    write_fake_stamp
    advance_clone
    echo "uncommitted" >> "$CLONE/configs/claude/CLAUDE.md"   # dirty source
    run env HOME="$FHOME" MANIFEST_STATE_ROOT="$FHOME/.manifest" bash "$CHECK"
    assert_success
    assert_output ""
}

@test "checker: silent when hashes match and stamp clean" {
    setup_checker
    write_fake_stamp false
    run env HOME="$FHOME" MANIFEST_STATE_ROOT="$FHOME/.manifest" bash "$CHECK"
    assert_success
    assert_output ""
}

@test "checker: nudges once on clean-main drift, then dedupes" {
    setup_checker
    write_fake_stamp
    advance_clone
    run env HOME="$FHOME" MANIFEST_STATE_ROOT="$FHOME/.manifest" bash "$CHECK"
    assert_success
    assert_output --partial "Manifest deploy is stale"
    # second run: same hash → silent
    run env HOME="$FHOME" MANIFEST_STATE_ROOT="$FHOME/.manifest" bash "$CHECK"
    assert_success
    assert_output ""
}

@test "checker: re-nudges after a new commit past a warned drift" {
    setup_checker
    write_fake_stamp
    advance_clone
    env HOME="$FHOME" MANIFEST_STATE_ROOT="$FHOME/.manifest" bash "$CHECK" >/dev/null
    advance_clone   # new hash
    run env HOME="$FHOME" MANIFEST_STATE_ROOT="$FHOME/.manifest" bash "$CHECK"
    assert_success
    assert_output --partial "Manifest deploy is stale"
}

@test "checker: dirty=true stamp with matching hashes still nudges" {
    setup_checker
    write_fake_stamp true   # deployed from a dirty tree — stamp untrusted
    run env HOME="$FHOME" MANIFEST_STATE_ROOT="$FHOME/.manifest" bash "$CHECK"
    assert_success
    assert_output --partial "Manifest deploy is stale"
}

@test "checker: --help exits 0 with usage in a clean env" {
    run env HOME="$TMP/empty" bash "$CHECK" --help
    assert_success
    assert_output --partial "Usage"
}

@test "wiring: repo settings.local.json registers the SessionStart hook" {
    run python3 -c "
import json
d = json.load(open('$REPO_ROOT/configs/claude/settings.local.json'))
cmds = [h['command'] for m in d['hooks']['SessionStart'] for h in m['hooks']]
assert any(c.endswith('deploy_stamp_check.sh') for c in cmds), cmds
allow = d['permissions']['allow']
assert any('deploy_stamp_check.sh' in a for a in allow), 'missing allow entry'
print('wired')"
    assert_success
    assert_output --partial "wired"
}

@test "wiring: both deploy paths call write_deploy_stamp" {
    run grep -c 'write_deploy_stamp "\$SCRIPT_DIR" "\$TARGET_DIR"' "$REPO_ROOT/bootstrap/lib/deploy.sh"
    assert_output "2"
}
