#!/usr/bin/env bats
# Tests for install_issue_hooks.sh and issue_support_hook.sh
# Installer safety invariants H1 (idempotent), H2 (no-clobber), H3 (opt-in gate),
# H4 (fire only on success), H5 (remove cleanup).

INSTALL="$BATS_TEST_DIRNAME/../../plugins/manifest-forge/runtime/bin/install_issue_hooks.sh"
DISPATCH="$BATS_TEST_DIRNAME/../../plugins/manifest-forge/runtime/bin/issue_support_hook.sh"

setup() {
    export BATS_TMPDIR="${BATS_TMPDIR:-/tmp}"
    TMP=$(mktemp -d "$BATS_TMPDIR/install_ih.XXXXXX")
    export ISSUE_HOOKS_SETTINGS="$TMP/settings.json"
    # Isolate the user-scope opt-in overlay (T051). This suite RUNS the real
    # installer, so without this it writes into the developer's actual
    # ~/.config/manifest/forge/ — observed, not hypothetical.
    export ISSUE_HOOKS_STATE="$TMP/issue_hooks.json"
    # The forge reader's package-layer config is a JSON document; nothing writes
    # to it — it is the fixture the fall-through test diffs for byte-identity.
    export ISSUE_HOOKS_CONFIG="$TMP/issue_support.json"
    export ISSUE_SUPPORT_CONFIG="$ISSUE_HOOKS_CONFIG"
    cat >"$ISSUE_HOOKS_CONFIG" <<'CFGJSON'
{"tool_policies": {
  "issue-sync-pr": {"enabled": false, "hook_timeout_seconds": 5},
  "issue-sync-commit": {"enabled": false, "hook_timeout_seconds": 5, "commit_hook_mode": "sync"},
  "other-skill": {"enabled": false}
}}
CFGJSON
    # Native CLI stub so the real dispatcher->engine chain can be observed
    # without touching a tracker (the ISSUE_SUPPORT_ENGINE seam is gone).
    mkdir -p "$TMP/bin"
    cat >"$TMP/bin/forge-cli" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail
echo "forge-cli $*" >> "${CALL_LOG:-/dev/null}"
case "${1:-} ${2:-}" in
  "issue list") printf '%s' "${ISSUE_LIST_OUT:-}" ;;
  "issue view") [[ -f "${FIXTURE_DIR:-/nonexistent}/issue-${3:-}.json" ]] && cat "${FIXTURE_DIR}/issue-${3:-}.json" || true ;;
  "pr view") [[ -f "${FIXTURE_DIR:-/nonexistent}/pr.json" ]] && cat "${FIXTURE_DIR}/pr.json" || true ;;
esac
exit "${NATIVE_CLI_RC:-0}"
STUB
    chmod +x "$TMP/bin/forge-cli"
    ln -sf forge-cli "$TMP/bin/gh"
    ln -sf forge-cli "$TMP/bin/glab"
    export PATH="$TMP/bin:$PATH"
    export CALL_LOG="$TMP/calls.log"
    REPO="$TMP/repo"; git init -q "$REPO"
    cd "$REPO" || return 1
    git config user.email t@t.t; git config user.name t
}
teardown() { [[ -n "$TMP" && -d "$TMP" ]] && rm -rf "$TMP"; }

# --- H3: opt-in runtime gate ------------------------------------------------

@test "enable records both skills in the user-scope overlay" {
    # Contract CHANGED by T051/FR-034. This test previously asserted the
    # installer flipped `enabled: true` inside the deployed command_config.yml.
    # That made a user opt-in a piece of state stored in a build output, which
    # any deploy is free to overwrite — the sole reason
    # preserve_issue_sync_gates() existed. The installer now writes a file no
    # package owns, and the assertion moved with it.
    run bash "$INSTALL" --enable
    [ "$status" -eq 0 ]
    python3 - "$ISSUE_HOOKS_STATE" <<'STATEPY'
import json, sys
pol = json.load(open(sys.argv[1]))["tool_policies"]
assert pol["issue-sync-pr"]["enabled"] is True
assert pol["issue-sync-commit"]["enabled"] is True
STATEPY
}

@test "enable leaves the package-owned config untouched, comments and all" {
    # The other half of the same contract. The installer now has no code path to
    # command_config.yml at all, so this passes trivially today — it is kept as a
    # regression guard against the write being reintroduced, which is exactly how
    # the original defect arrived.
    cp "$ISSUE_HOOKS_CONFIG" "$TMP/config.before"
    run bash "$INSTALL" --enable
    [ "$status" -eq 0 ]
    diff "$ISSUE_HOOKS_CONFIG" "$TMP/config.before"
    python3 - "$ISSUE_HOOKS_CONFIG" <<'CFGPY'
import json, sys
pol = json.load(open(sys.argv[1]))["tool_policies"]
assert pol["other-skill"]["enabled"] is False
CFGPY
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
      {"matcher": "Bash", "hooks": [{"type": "command", "command": "/some/other/clone/plugins/manifest-forge/runtime/bin/issue_support_hook.sh", "timeout": 30}]},
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
    python3 - "$ISSUE_HOOKS_STATE" <<'RMPY'
import json, sys
pol = json.load(open(sys.argv[1]))["tool_policies"]
assert pol["issue-sync-pr"]["enabled"] is False
RMPY
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
    # Enabled in the state file so the real engine proceeds past its gate.
    bash "$INSTALL" --enable
    printf '{"tool_input":{"command":"gh pr create --title x"},"tool_response":{}}' > "$TMP/payload.json"
    run bash "$DISPATCH" < "$TMP/payload.json"
    [ "$status" -eq 0 ]
    # The real engine ran: sync-pr resolves the current branch's PR via gh pr view.
    grep -q 'forge-cli pr view' "$CALL_LOG"
}

@test "dispatcher does NOT invoke engine when the command failed" {
    bash "$INSTALL" --enable
    : >"$CALL_LOG"
    printf '{"tool_input":{"command":"git commit -m x"},"tool_response":{"is_error":true}}' | bash "$DISPATCH"
    [ ! -s "$CALL_LOG" ]
}

# --- bug_005: classifier must not fire on unrelated commands ----------------

@test "dispatcher ignores commands that merely contain pr-create/commit substrings" {
    bash "$INSTALL" --enable
    : >"$CALL_LOG"
    for c in "cat tests/fixtures/pr-create.json" "npm run pr-create-helper" \
             "git config commit.gpgsign true" "git log --grep=commit"; do
        printf '{"tool_input":{"command":"%s"},"tool_response":{}}' "$c" > "$TMP/p.json"
        bash "$DISPATCH" < "$TMP/p.json"
    done
    [ ! -s "$CALL_LOG" ]   # none of the false-positive commands invoked the engine
}

@test "dispatcher still fires on a real git commit invocation" {
    # Enabled in the state file so the real engine proceeds past its gate.
    bash "$INSTALL" --enable
    printf '{"tool_input":{"command":"git commit -m work"},"tool_response":{}}' > "$TMP/p.json"
    bash "$DISPATCH" < "$TMP/p.json"
    # No linked issue on this branch -> sync-commit reaches the create-flow,
    # which searches for an existing issue via gh issue list --search.
    grep -q 'forge-cli issue list --search' "$CALL_LOG"
}
