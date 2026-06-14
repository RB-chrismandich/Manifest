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
  pr-issue-sync:
    enabled: false              # comment kept
    hook_timeout_seconds: 5
  commit-issue-sync:
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
    grep -A1 '^  pr-issue-sync:' "$ISSUE_HOOKS_CONFIG" | grep -q 'enabled: true'
    grep -A1 '^  commit-issue-sync:' "$ISSUE_HOOKS_CONFIG" | grep -q 'enabled: true'
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

# --- H5: remove cleans up both surfaces -------------------------------------

@test "remove flips enabled false and drops the settings entry" {
    bash "$INSTALL" --enable
    run bash "$INSTALL" --remove
    [ "$status" -eq 0 ]
    grep -A1 '^  pr-issue-sync:' "$ISSUE_HOOKS_CONFIG" | grep -q 'enabled: false'
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
    bash "$INSTALL" --remove
    [ ! -f "$REPO/.git/hooks/post-commit" ] || ! grep -q 'issue-support' "$REPO/.git/hooks/post-commit"
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
