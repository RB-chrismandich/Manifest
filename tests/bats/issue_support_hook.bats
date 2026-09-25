#!/usr/bin/env bats
# Direct unit coverage for plugins/manifest-forge/runtime/bin/issue_support_hook.sh
# (previously exercised only indirectly via install_issue_hooks.bats).
#
# Covers: fail-open behavior when the engine / classify path errors, the
# dedup/skip logic (never double-invoke, forward-only classification), and
# the argument/env contract (--help, -h, stdin payload shape).
#
# Forge contract: the dispatcher invokes the sibling issue_support.sh — the
# ISSUE_SUPPORT_ENGINE override seam no longer exists. The engine is observed
# through a stubbed native CLI (gh/glab -> forge-cli -> $CALL_LOG) and gated by
# the user-scope issue_hooks.json overlay (enabled: true) — the same model as
# install_issue_hooks.bats.

DISPATCH="$BATS_TEST_DIRNAME/../../plugins/manifest-forge/runtime/bin/issue_support_hook.sh"

setup() {
    export BATS_TMPDIR="${BATS_TMPDIR:-/tmp}"
    TMP=$(mktemp -d "$BATS_TMPDIR/issue_support_hook.XXXXXX")
    # Both engine opt-in layers are pointed at TMP so the developer's real
    # ~/.config/manifest/forge is never read. The overlay enables both policies.
    export ISSUE_HOOKS_STATE="$TMP/issue_hooks.json"
    export ISSUE_SUPPORT_CONFIG="$TMP/issue_support.json"
    export XDG_STATE_HOME="$TMP/xdg-state"
    cat >"$ISSUE_HOOKS_STATE" <<'STATE'
{"tool_policies": {
  "issue-sync-pr": {"enabled": true, "hook_timeout_seconds": 5},
  "issue-sync-commit": {"enabled": true, "hook_timeout_seconds": 5, "commit_hook_mode": "sync"}
}}
STATE
    # Native CLI stub: logs every call so engine invocation is observable.
    mkdir -p "$TMP/bin"
    cat >"$TMP/bin/forge-cli" <<'STUB'
#!/usr/bin/env bash
echo "forge-cli $*" >> "${CALL_LOG:-/dev/null}"
exit "${NATIVE_CLI_RC:-0}"
STUB
    chmod +x "$TMP/bin/forge-cli"
    ln -sf forge-cli "$TMP/bin/gh"
    ln -sf forge-cli "$TMP/bin/glab"
    export PATH="$TMP/bin:$PATH"
    export CALL_LOG="$TMP/calls.log"
    : >"$CALL_LOG"
    # Pin provider detection: the repo has no remote, so without this the
    # registry default decides. github keeps platform assertions deterministic.
    export MANIFEST_TRACKER=github
    REPO="$TMP/repo"; git init -q "$REPO"
    cd "$REPO" || return 1
    git config user.email t@t.t; git config user.name t
}

teardown() { [[ -n "$TMP" && -d "$TMP" ]] && rm -rf "$TMP"; }

# --- argument/env contract ---------------------------------------------------

@test "--help prints usage and exits 0 without touching the engine" {
    run bash "$DISPATCH" --help
    [ "$status" -eq 0 ]
    [[ "$output" == *"issue_support_hook.sh"* ]] || return 1
    [ ! -s "$CALL_LOG" ]
}

@test "-h prints usage and exits 0" {
    run bash "$DISPATCH" -h
    [ "$status" -eq 0 ]
    [[ "$output" == *"Usage"* ]]
}

@test "ISSUE_SUPPORT_ENGINE is no longer honored — the sibling engine always runs" {
    # The forge dispatcher hard-codes ENGINE=<sibling>/issue_support.sh. A
    # planted override must be ignored: the real engine runs (observed via the
    # gh stub), the planted file is never executed.
    cat >"$TMP/evil.sh" <<'EOF'
#!/usr/bin/env bash
echo INJECTED > "$EVIL_MARKER"
EOF
    chmod +x "$TMP/evil.sh"
    export ISSUE_SUPPORT_ENGINE="$TMP/evil.sh"
    export EVIL_MARKER="$TMP/evil.marker"
    printf '{"tool_input":{"command":"gh pr create -t x"},"tool_response":{}}' > "$TMP/p.json"
    run bash "$DISPATCH" < "$TMP/p.json"
    [ "$status" -eq 0 ]
    [ ! -e "$EVIL_MARKER" ]
    grep -q 'pr view' "$CALL_LOG"
}

@test "missing tool_response key defaults ok=1 (still invokes engine on match)" {
    printf '{"tool_input":{"command":"git commit -m x"}}' > "$TMP/p.json"
    run bash "$DISPATCH" < "$TMP/p.json"
    [ "$status" -eq 0 ]
    grep -q 'issue list --search' "$CALL_LOG"
}

# --- fail-open behavior -------------------------------------------------------

@test "fail-open: invalid JSON on stdin exits 0 and never invokes the engine" {
    printf 'not json at all {{{' > "$TMP/p.json"
    run bash "$DISPATCH" < "$TMP/p.json"
    [ "$status" -eq 0 ]
    [ ! -s "$CALL_LOG" ]
}

@test "fail-open: empty stdin exits 0 and never invokes the engine" {
    run bash "$DISPATCH" < /dev/null
    [ "$status" -eq 0 ]
    [ ! -s "$CALL_LOG" ]
}

@test "fail-open: engine work errors (simulated native CLI failure) — hook still exits 0" {
    export NATIVE_CLI_RC=1
    printf '{"tool_input":{"command":"gh pr create -t x"},"tool_response":{}}' > "$TMP/p.json"
    run bash "$DISPATCH" < "$TMP/p.json"
    [ "$status" -eq 0 ]
    # the engine was still attempted despite the native failure
    [ -s "$CALL_LOG" ]
}

@test "fail-open: python3 classify path unavailable falls back to none/0 and exits 0" {
    STUBDIR="$TMP/nopy"
    mkdir -p "$STUBDIR"
    # Shadow python3 with a command-not-found stub (exit 127) instead of
    # subtracting PATH dirs: on merged-/usr Linux (ubuntu-latest CI) /bin is a
    # symlink to /usr/bin, so a "$STUBDIR:/bin" PATH still finds real python3.
    # Shadowing is deterministic on every platform and keeps bash/cat working.
    printf '#!/usr/bin/env bash\nexit 127\n' > "$STUBDIR/python3"
    chmod +x "$STUBDIR/python3"
    printf '{"tool_input":{"command":"git commit -m x"},"tool_response":{}}' > "$TMP/p.json"
    run env PATH="$STUBDIR:$PATH" bash "$DISPATCH" < "$TMP/p.json"
    [ "$status" -eq 0 ]
    [ ! -s "$CALL_LOG" ]
}

@test "underlying command marked is_error:true never invokes the engine (H4)" {
    printf '{"tool_input":{"command":"gh pr create -t x"},"tool_response":{"is_error":true}}' > "$TMP/p.json"
    run bash "$DISPATCH" < "$TMP/p.json"
    [ "$status" -eq 0 ]
    [ ! -s "$CALL_LOG" ]
}

@test "underlying command marked error:<truthy> never invokes the engine" {
    printf '{"tool_input":{"command":"git commit -m x"},"tool_response":{"error":"boom"}}' > "$TMP/p.json"
    run bash "$DISPATCH" < "$TMP/p.json"
    [ "$status" -eq 0 ]
    [ ! -s "$CALL_LOG" ]
}

# --- dedup/skip logic ---------------------------------------------------------

@test "dedup: a single matching command invokes the engine exactly once" {
    printf '{"tool_input":{"command":"gh pr create -t x"},"tool_response":{}}' > "$TMP/p.json"
    run bash "$DISPATCH" < "$TMP/p.json"
    [ "$status" -eq 0 ]
    # sync-pr with no number resolves the branch PR via exactly one `pr view`.
    [ "$(wc -l < "$CALL_LOG" | tr -d ' ')" -eq 1 ]
    grep -q 'pr view' "$CALL_LOG"
}

@test "dedup: a command matching neither class invokes the engine zero times" {
    printf '{"tool_input":{"command":"echo hello world"},"tool_response":{}}' > "$TMP/p.json"
    run bash "$DISPATCH" < "$TMP/p.json"
    [ "$status" -eq 0 ]
    [ ! -s "$CALL_LOG" ]
}

@test "dedup: classification is mutually exclusive — a commit-shaped command never also fires sync-pr" {
    printf '{"tool_input":{"command":"git commit -m \\"pr-create rollout\\""},"tool_response":{}}' > "$TMP/p.json"
    run bash "$DISPATCH" < "$TMP/p.json"
    [ "$status" -eq 0 ]
    grep -q 'issue list --search' "$CALL_LOG" || return 1
    ! grep -q 'pr view' "$CALL_LOG"
}

@test "dedup: two independent hook invocations each record their own single call (no cross-run merging)" {
    printf '{"tool_input":{"command":"gh pr create -t x"},"tool_response":{}}' > "$TMP/p1.json"
    printf '{"tool_input":{"command":"git commit -m x"},"tool_response":{}}' > "$TMP/p2.json"
    bash "$DISPATCH" < "$TMP/p1.json"
    bash "$DISPATCH" < "$TMP/p2.json"
    [ "$(grep -c 'pr view' "$CALL_LOG")" -eq 1 ]
    [ "$(grep -c 'issue list --search' "$CALL_LOG")" -eq 1 ]
}

@test "glab mr-create is classified as pr" {
    export MANIFEST_TRACKER=gitlab
    printf '{"tool_input":{"command":"glab mr create --title x"},"tool_response":{}}' > "$TMP/p.json"
    run bash "$DISPATCH" < "$TMP/p.json"
    [ "$status" -eq 0 ]
    grep -q 'mr view' "$CALL_LOG"
}
