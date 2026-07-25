#!/usr/bin/env bats
# Tests for install_issue_hooks.sh and issue_support_hook.sh
# Installer safety invariants H1 (idempotent), H2 (no-clobber), H3 (opt-in gate),
# H4 (fire only on success), H5 (remove cleanup).

INSTALL="$BATS_TEST_DIRNAME/../../configs/claude/scripts/install_issue_hooks.sh"
DISPATCH="$BATS_TEST_DIRNAME/../../configs/claude/scripts/issue_support_hook.sh"

setup() {
    export BATS_TMPDIR="${BATS_TMPDIR:-/tmp}"
    TMP=$(mktemp -d "$BATS_TMPDIR/install_ih.XXXXXX")
    export ISSUE_HOOKS_SETTINGS="$TMP/settings.json"
    export ISSUE_HOOKS_CONFIG="$TMP/config.yml"
    cat >"$ISSUE_HOOKS_CONFIG" <<'EOF'
tool_policies:
  issue-sync-pr:
    enabled: false              # comment kept
    hook_timeout_seconds: 5
  issue-sync-commit:
    enabled: false
    hook_timeout_seconds: 5
    commit_hook_mode: sync
  other-skill:
    enabled: false
EOF
    REPO="$TMP/repo"; git init -q "$REPO"
    cd "$REPO" || return 1
    git config user.email t@t.t; git config user.name t
}
teardown() { [[ -n "$TMP" && -d "$TMP" ]] && rm -rf "$TMP"; }

# --- H3: opt-in runtime gate ------------------------------------------------

@test "enable flips both skills' enabled to true and preserves comments" {
    run bash "$INSTALL" --enable
    [ "$status" -eq 0 ]
    grep -A1 '^  issue-sync-pr:' "$ISSUE_HOOKS_CONFIG" | grep -q 'enabled: true'
    grep -A1 '^  issue-sync-commit:' "$ISSUE_HOOKS_CONFIG" | grep -q 'enabled: true'
    grep -q '# comment kept' "$ISSUE_HOOKS_CONFIG"
    # unrelated skill untouched
    grep -A1 '^  other-skill:' "$ISSUE_HOOKS_CONFIG" | grep -q 'enabled: false'
}

# --- H1: idempotent settings install ----------------------------------------

@test "enable is idempotent — no duplicate PostToolUse entry" {
    bash "$INSTALL" --enable
    bash "$INSTALL" --enable
    count=$(python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(sum(1 for e in d["hooks"]["PostToolUse"] for h in e["hooks"] if "issue_support_hook.sh" in h["command"]))' "$ISSUE_HOOKS_SETTINGS")
    [ "$count" -eq 1 ]
}

# Regression: the test above re-runs the SAME installer path, so the command
# strings match exactly and it passed even while this bug was live. The real
# duplicate came from installing once from a repo clone and once from the
# deployed ~/.claude/scripts copy — same hook, two absolute paths, neither
# removing the other, so it fired twice on every matching tool call.
@test "enable replaces a registration of the same hook made from another path" {
    cat > "$ISSUE_HOOKS_SETTINGS" <<'EOF'
{
  "hooks": {
    "PostToolUse": [
      {"matcher": "Bash", "hooks": [{"type": "command", "command": "/some/other/clone/configs/claude/scripts/issue_support_hook.sh", "timeout": 30}]},
      {"matcher": "Write", "hooks": [{"type": "command", "command": "/unrelated/other_hook.sh"}]}
    ]
  }
}
EOF
    run bash "$INSTALL" --enable
    [ "$status" -eq 0 ]
    count=$(python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(sum(1 for e in d["hooks"]["PostToolUse"] for h in e["hooks"] if "issue_support_hook.sh" in h["command"]))' "$ISSUE_HOOKS_SETTINGS")
    [ "$count" -eq 1 ]
    # the surviving one is the freshly-installed path, not the stale clone
    python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); assert not any("/some/other/clone/" in h["command"] for e in d["hooks"]["PostToolUse"] for h in e["hooks"])' "$ISSUE_HOOKS_SETTINGS"
    # an unrelated hook under a different matcher is untouched
    python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); assert any("other_hook.sh" in h["command"] for e in d["hooks"]["PostToolUse"] for h in e["hooks"])' "$ISSUE_HOOKS_SETTINGS"
}

# --- H5: remove cleans up both surfaces -------------------------------------

# Regression: hook commands are commonly interpreter-prefixed
# ("/usr/bin/env bash <path>", "python3 <path> --handler ...") — this repo's
# own PreToolUse entry has that shape. Keying identity on the first token only
# sees "env"/"python3", so such a registration survived --enable (duplicate)
# and --remove (orphan left behind).
@test "enable/remove match an interpreter-prefixed registration of the same hook" {
    cat > "$ISSUE_HOOKS_SETTINGS" <<'EOF'
{
  "hooks": {
    "PostToolUse": [
      {"matcher": "Bash", "hooks": [{"type": "command", "command": "/usr/bin/env bash /other/clone/issue_support_hook.sh --verbose", "timeout": 30}]},
      {"matcher": "Write", "hooks": [{"type": "command", "command": "/unrelated/other_hook.sh"}]}
    ]
  }
}
EOF
    run bash "$INSTALL" --enable
    [ "$status" -eq 0 ]
    count=$(python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(sum(1 for e in d["hooks"]["PostToolUse"] for h in e["hooks"] if "issue_support_hook.sh" in h["command"]))' "$ISSUE_HOOKS_SETTINGS")
    [ "$count" -eq 1 ]
    python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); assert not any("/other/clone/" in h["command"] for e in d["hooks"]["PostToolUse"] for h in e["hooks"])' "$ISSUE_HOOKS_SETTINGS"

    # ...and remove must not leave the interpreter-prefixed form orphaned.
    run bash "$INSTALL" --remove
    [ "$status" -eq 0 ]
    count=$(python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(sum(1 for e in d["hooks"]["PostToolUse"] for h in e["hooks"] if "issue_support_hook.sh" in h["command"]))' "$ISSUE_HOOKS_SETTINGS")
    [ "$count" -eq 0 ]
    python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); assert any("other_hook.sh" in h["command"] for e in d["hooks"]["PostToolUse"] for h in e["hooks"])' "$ISSUE_HOOKS_SETTINGS"
}

@test "remove flips enabled false and drops the settings entry" {
    bash "$INSTALL" --enable
    run bash "$INSTALL" --remove
    [ "$status" -eq 0 ]
    grep -A1 '^  issue-sync-pr:' "$ISSUE_HOOKS_CONFIG" | grep -q 'enabled: false'
    count=$(python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(sum(1 for e in d["hooks"].get("PostToolUse",[]) for h in e["hooks"] if "issue_support_hook.sh" in h["command"]))' "$ISSUE_HOOKS_SETTINGS")
    [ "$count" -eq 0 ]
}

# --- H2: native hook never clobbers a foreign post-commit -------------------

@test "native install refuses to clobber an existing foreign post-commit hook" {
    printf '#!/usr/bin/env bash\necho mine\n' > "$REPO/.git/hooks/post-commit"
    chmod +x "$REPO/.git/hooks/post-commit"
    run bash "$INSTALL" --enable --native
    [ "$status" -eq 0 ]
    grep -q 'echo mine' "$REPO/.git/hooks/post-commit"
    ! grep -q 'issue-support' "$REPO/.git/hooks/post-commit"
}

@test "native install adds a managed block when no hook exists; remove strips it" {
    bash "$INSTALL" --enable --native
    grep -q '>>> issue-support >>>' "$REPO/.git/hooks/post-commit"
    # shebang must be the first line so Git can exec the hook
    head -1 "$REPO/.git/hooks/post-commit" | grep -q '^#!'
    bash "$INSTALL" --remove
    [ ! -f "$REPO/.git/hooks/post-commit" ] || ! grep -q 'issue-support' "$REPO/.git/hooks/post-commit"
}

@test "native enable→remove→enable round-trip re-installs cleanly (bug_007)" {
    bash "$INSTALL" --enable --native
    bash "$INSTALL" --remove
    # No orphan residual must remain to trip the clobber-guard
    [ ! -f "$REPO/.git/hooks/post-commit" ]
    run bash "$INSTALL" --enable --native
    [ "$status" -eq 0 ]
    grep -q 'issue-support' "$REPO/.git/hooks/post-commit"
}

# --- bug_006: sibling hooks under the same matcher must survive --------------

@test "remove preserves a sibling hook co-located under the same Bash matcher" {
    HOOK_CANON="$(cd "$(dirname "$INSTALL")" && pwd)/issue_support_hook.sh"
    cat >"$ISSUE_HOOKS_SETTINGS" <<EOF
{"hooks":{"PostToolUse":[{"matcher":"Bash","hooks":[
  {"type":"command","command":"/usr/local/bin/audit-log.sh"},
  {"type":"command","command":"${HOOK_CANON}"}
]}]}}
EOF
    run bash "$INSTALL" --remove
    [ "$status" -eq 0 ]
    grep -q 'audit-log.sh' "$ISSUE_HOOKS_SETTINGS"
    ! grep -q 'issue_support_hook.sh' "$ISSUE_HOOKS_SETTINGS"
}

# --- H4: dispatcher fires only on success -----------------------------------

@test "dispatcher invokes engine sync-pr on a successful PR-create command" {
    REC="$TMP/engine_calls.log"
    cat >"$TMP/engine.sh" <<EOF
#!/usr/bin/env bash
echo "\$*" >> "$REC"
EOF
    chmod +x "$TMP/engine.sh"
    export ISSUE_SUPPORT_ENGINE="$TMP/engine.sh"
    printf '{"tool_input":{"command":"gh pr create --title x"},"tool_response":{}}' > "$TMP/payload.json"
    run bash "$DISPATCH" < "$TMP/payload.json"
    [ "$status" -eq 0 ]
    grep -q 'sync-pr' "$REC"
}

@test "dispatcher does NOT invoke engine when the command failed" {
    REC="$TMP/engine_calls.log"; : >"$REC"
    cat >"$TMP/engine.sh" <<EOF
#!/usr/bin/env bash
echo "\$*" >> "$REC"
EOF
    chmod +x "$TMP/engine.sh"
    export ISSUE_SUPPORT_ENGINE="$TMP/engine.sh"
    printf '{"tool_input":{"command":"git commit -m x"},"tool_response":{"is_error":true}}' | bash "$DISPATCH"
    [ ! -s "$REC" ]
}

# --- bug_005: classifier must not fire on unrelated commands ----------------

@test "dispatcher ignores commands that merely contain pr-create/commit substrings" {
    REC="$TMP/engine_calls.log"; : >"$REC"
    cat >"$TMP/engine.sh" <<EOF
#!/usr/bin/env bash
echo "\$*" >> "$REC"
EOF
    chmod +x "$TMP/engine.sh"
    export ISSUE_SUPPORT_ENGINE="$TMP/engine.sh"
    for c in "cat tests/fixtures/pr-create.json" "npm run pr-create-helper" \
             "git config commit.gpgsign true" "git log --grep=commit"; do
        printf '{"tool_input":{"command":"%s"},"tool_response":{}}' "$c" > "$TMP/p.json"
        bash "$DISPATCH" < "$TMP/p.json"
    done
    [ ! -s "$REC" ]   # none of the false-positive commands invoked the engine
}

@test "dispatcher still fires on a real git commit invocation" {
    REC="$TMP/engine_calls.log"; : >"$REC"
    cat >"$TMP/engine.sh" <<EOF
#!/usr/bin/env bash
echo "\$*" >> "$REC"
EOF
    chmod +x "$TMP/engine.sh"
    export ISSUE_SUPPORT_ENGINE="$TMP/engine.sh"
    printf '{"tool_input":{"command":"git commit -m work"},"tool_response":{}}' > "$TMP/p.json"
    bash "$DISPATCH" < "$TMP/p.json"
    grep -q 'sync-commit' "$REC"
}
