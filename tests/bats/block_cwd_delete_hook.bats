#!/usr/bin/env bats
# PreToolUse hook: refuse to delete a directory a live session is running in
# (block_cwd_delete.py).
#
# Incident 2026-07-28T06:06Z: a session in repo A ran a `git worktree remove`
# sweep whose KEEP guard protected only its OWN cwd. The list included the live
# cwd of a session in repo B. Eight minutes later every hook in that session
# failed with `ENOENT ... posix_spawn '/bin/sh'` — Claude Code spawns hooks with
# cwd set to the session directory, and a missing child cwd is reported against
# the binary, so the error names a shell that is present and healthy.
#
# The hookify rule that already covered this was project-scoped (hookify globs
# .claude/hookify.*.local.md relative to cwd), so it was not armed in repo A,
# and its guidance only told the operator to check `pwd -P` — which cannot see a
# sibling session. Both halves are gated here: the targets come from OTHER
# sessions' transcripts, and the removal is recognized inside a shell loop where
# the path never appears next to the `git worktree remove` verb.

bats_require_minimum_version 1.5.0

setup() {
    load '../test_helper/bats-support/load'
    load '../test_helper/bats-assert/load'
    HOOK="$(cd "$(dirname "$BATS_TEST_FILENAME")/../../configs/claude/scripts" && pwd)/block_cwd_delete.py"

    SESSIONS="$BATS_TEST_TMPDIR/projects"
    mkdir -p "$SESSIONS"
    export CLAUDE_SESSIONS_DIR="$SESSIONS"

    # A live session in an unrelated repo, plus the directory it runs in.
    VICTIM="$BATS_TEST_TMPDIR/worktrees/other-repo/emdash/fancy-comics"
    mkdir -p "$VICTIM"
    live_session victim "$VICTIM"

    # The session running the sweep.
    ACTOR="$BATS_TEST_TMPDIR/worktrees/other-repo/emdash/beige-emus"
    mkdir -p "$ACTOR"
}

# Record a session transcript whose last entry reports `cwd`. age_min ages the
# file so the staleness window can be exercised.
live_session() {
    local name="$1" cwd="$2" age_min="${3:-0}"
    mkdir -p "$SESSIONS/$name"
    local f="$SESSIONS/$name/$name.jsonl"
    printf '{"type":"user","cwd":%s}\n' "\"$cwd\"" >"$f"
    if [ "$age_min" -gt 0 ]; then
        touch -t "$(python3 - "$age_min" <<'EOF'
import sys, time
print(time.strftime("%Y%m%d%H%M.%S", time.localtime(time.time() - int(sys.argv[1]) * 60)))
EOF
        )" "$f"
    fi
}

# Run the hook with a Bash payload; stdout is the decision (empty = allow).
decide() {
    local command="$1" cwd="${2:-$ACTOR}"
    python3 - "$command" "$cwd" <<'EOF' | python3 "$HOOK"
import json, sys
print(json.dumps({"tool_name": "Bash",
                  "cwd": sys.argv[2],
                  "tool_input": {"command": sys.argv[1]}}))
EOF
}

# "deny" or "" — the permission decision the hook returned.
verdict() {
    decide "$@" | python3 -c 'import json,sys
raw = sys.stdin.read().strip()
print(json.loads(raw)["hookSpecificOutput"]["permissionDecision"] if raw else "")'
}

@test "--help exits 0 and prints Usage" {
    run python3 "$HOOK" --help
    assert_success
    assert_output --partial "Usage"
}

@test "a command that deletes nothing is not inspected" {
    assert_equal "$(verdict 'git worktree list')" ""
}

@test "git worktree remove of another live session's cwd is denied" {
    assert_equal "$(verdict "git worktree remove $VICTIM")" "deny"
}

@test "the sweep loop is caught even though the path never touches the verb" {
    # The 2026-07-28 command shape: targets live in the `for` list, so verb-
    # adjacent argument parsing sees only "$wt" and would wave this through.
    local cmd="for wt in $ACTOR $VICTIM; do git worktree remove \"\$wt\"; done"
    assert_equal "$(verdict "$cmd")" "deny"
}

@test "rm -rf of a live session's cwd is denied" {
    assert_equal "$(verdict "rm -rf $VICTIM")" "deny"
}

@test "deleting an ancestor of a live session's cwd is denied" {
    assert_equal "$(verdict "rm -rf $BATS_TEST_TMPDIR/worktrees/other-repo")" "deny"
}

@test "the session's own cwd is protected even with no transcript" {
    rm -rf "${SESSIONS:?}"/*
    assert_equal "$(verdict "git worktree remove $ACTOR" "$ACTOR")" "deny"
}

@test "the denial names the path and the session that holds it" {
    output="$(decide "git worktree remove $VICTIM")"
    assert [ -n "$output" ]
    reason="$(printf '%s' "$output" | python3 -c 'import json,sys
print(json.load(sys.stdin)["hookSpecificOutput"]["permissionDecisionReason"])')"
    assert [ -n "$reason" ]
    printf '%s' "$reason" | grep -q "fancy-comics"
    printf '%s' "$reason" | grep -q "cwd-verified"
}

@test "an unrelated directory under the cwd is left alone" {
    assert_equal "$(verdict "rm -rf $ACTOR/node_modules")" ""
}

@test "a path in a non-deleting clause is not a deletion target" {
    # Regression, self-inflicted while verifying this hook: `cd $HOME && …` in a
    # command that mentions rm elsewhere is not a request to delete $HOME. The
    # loose whole-command scan that catches sweep loops must therefore demand an
    # EXACT live cwd; only a literal argument to the delete verb itself is
    # strong enough evidence to act on containment.
    local home_ish="$BATS_TEST_TMPDIR/worktrees"
    assert_equal "$(verdict "cd $home_ish && rm -rf \$SOME_VAR")" ""
}

@test "a literal ancestor argument to rm is still caught" {
    assert_equal "$(verdict "cd / && rm -rf $BATS_TEST_TMPDIR/worktrees/other-repo")" "deny"
}

# --------------------------------------------------------------------------- #
# `cd <exact live cwd>` must not be read as a deletion target.
#
# Restricting the loose scan to equality implemented the docstring's rule only
# for ANCESTORS: an exact `cd <live cwd>` still matched, and agent shells prefix
# nearly every command with `cd <repo>`. So any command that merely MENTIONED a
# deletion verb — in a grep pattern, a comment, an echo string — was denied.
# All four of these were observed denying real read-only work.
# --------------------------------------------------------------------------- #

@test "cd to the exact cwd is not a deletion target: verb inside a grep pattern" {
    assert_equal "$(verdict "cd $ACTOR
grep -rnE 'rm -rf|rmtree' --include='*.sh' src lib | head")" ""
}

@test "cd to the exact cwd is not a deletion target: verb only in a comment" {
    assert_equal "$(verdict "cd $ACTOR && ls   # not going to rmdir anything")" ""
}

@test "cd to the exact cwd is not a deletion target: verb only inside echo" {
    assert_equal "$(verdict "cd $ACTOR && echo 'run rmdir later'")" ""
}

@test "cd to the exact cwd then deleting a temp dir is allowed" {
    # The shape that kept firing during real work: cd into the repo, then clean
    # up a mktemp dir. The rm target is a $-token the hook cannot resolve, so the
    # only cwd-equal token was the cd argument.
    assert_equal "$(verdict "cd $ACTOR
T=\$(mktemp -d); rm -rf \"\$T\"")" ""
}

@test "cd to another session's cwd is still not a deletion target" {
    # Same rule, victim-side: mentioning a path is not requesting its deletion.
    assert_equal "$(verdict "cd $VICTIM && grep -r rmdir .")" ""
}

@test "cd does not launder a real deletion in a later clause" {
    # The cd argument is exempt; the rm argument is not.
    assert_equal "$(verdict "cd $ACTOR && rm -rf $VICTIM")" "deny"
}

@test "rm -rf . is caught when the cwd is a live session dir" {
    # Previously a hole: "." was discarded as non-path-shaped, so deleting the
    # cwd via a relative target slipped through both passes entirely.
    assert_equal "$(verdict 'rm -rf .')" "deny"
}

@test "rm -rf .. is caught when it resolves onto a live session dir" {
    local child="$VICTIM/subdir"
    mkdir -p "$child"
    assert_equal "$(verdict 'rm -rf ..' "$child")" "deny"
}

@test "a bare . elsewhere in a deleting command is not itself a target" {
    # `.` counts only as a deletion-verb argument. As a bare mention it would
    # match every cwd and deny everything.
    assert_equal "$(verdict "grep -r rmdir . && rm -rf $ACTOR/build")" ""
}

@test "a relative target that is not a session cwd is left alone" {
    assert_equal "$(verdict 'rm -rf build/artifacts')" ""
}

@test "a session idle past the window no longer holds its directory" {
    rm -rf "${SESSIONS:?}"/*
    live_session stale "$VICTIM" 600
    BLOCK_CWD_DELETE_WINDOW_MIN=60
    export BLOCK_CWD_DELETE_WINDOW_MIN
    assert_equal "$(verdict "rm -rf $VICTIM")" ""
}

@test "the cwd-verified marker is an explicit override" {
    assert_equal "$(verdict "git worktree remove $VICTIM  # cwd-verified")" ""
}

@test "a malformed payload fails open and silent" {
    run --separate-stderr bash -c "printf 'not json' | python3 '$HOOK'"
    assert_success
    assert_output ""
}

@test "wiring: repo settings.runtime.json registers the PreToolUse:Bash hook" {
    # settings.runtime.json, not settings.local.json: the latter is inert at
    # user scope (measured), so a guard registered there would never fire —
    # and a guard that never fires is worse than none, because it reads as
    # coverage.
    local repo_root
    repo_root="$(cd "$(dirname "$BATS_TEST_FILENAME")/../.." && pwd)"
    run python3 -c "
import json
d = json.load(open('$repo_root/configs/claude/settings.runtime.json'))
cmds = [h['command']
        for m in d['hooks']['PreToolUse'] if m.get('matcher') == 'Bash'
        for h in m['hooks']]
assert any(c.endswith('block_cwd_delete.py') for c in cmds), cmds
allow = d['permissions']['allow']
assert any('block_cwd_delete.py' in a for a in allow), 'missing allow entry'
print('wired')"
    assert_success
    assert_output --partial "wired"
}

@test "an unreadable sessions directory fails open" {
    export CLAUDE_SESSIONS_DIR="$BATS_TEST_TMPDIR/does-not-exist"
    # The victim is unknown without transcripts, so only the caller's own cwd
    # is defended — the hook must still not error.
    assert_equal "$(verdict "rm -rf $VICTIM")" ""
}
