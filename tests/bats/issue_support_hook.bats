#!/usr/bin/env bats
# Direct unit coverage for configs/claude/scripts/issue_support_hook.sh
# (previously exercised only indirectly via install_issue_hooks.bats).
#
# Covers: fail-open behavior when the engine / classify path errors, the
# dedup/skip logic (never double-invoke, forward-only classification), and
# the argument/env contract (--help, -h, ISSUE_SUPPORT_ENGINE override,
# stdin payload shape).

DISPATCH="$BATS_TEST_DIRNAME/../../configs/claude/scripts/issue_support_hook.sh"

setup() {
    export BATS_TMPDIR="${BATS_TMPDIR:-/tmp}"
    TMP=$(mktemp -d "$BATS_TMPDIR/issue_support_hook.XXXXXX")
    REC="$TMP/engine_calls.log"
    : >"$REC"
    cat >"$TMP/engine.sh" <<EOF
#!/usr/bin/env bash
echo "\$*" >> "$REC"
exit "\${ENGINE_RC:-0}"
EOF
    chmod +x "$TMP/engine.sh"
    export ISSUE_SUPPORT_ENGINE="$TMP/engine.sh"
}

teardown() { [[ -n "$TMP" && -d "$TMP" ]] && rm -rf "$TMP"; }

# --- argument/env contract ---------------------------------------------------

@test "--help prints usage and exits 0 without reading stdin" {
    run bash "$DISPATCH" --help
    [ "$status" -eq 0 ]
    [[ "$output" == *"issue_support_hook.sh"* ]] || return 1
    [ ! -s "$REC" ]
}

@test "-h prints usage and exits 0" {
    run bash "$DISPATCH" -h
    [ "$status" -eq 0 ]
    [[ "$output" == *"Usage"* ]]
}

@test "unset ISSUE_SUPPORT_ENGINE falls back to the sibling issue_support.sh path without erroring on a non-matching command" {
    unset ISSUE_SUPPORT_ENGINE
    printf '{"tool_input":{"command":"ls -la"},"tool_response":{}}' > "$TMP/p.json"
    run bash "$DISPATCH" < "$TMP/p.json"
    [ "$status" -eq 0 ]
}

@test "ISSUE_SUPPORT_ENGINE override is honored over the default sibling script" {
    printf '{"tool_input":{"command":"gh pr create -t x"},"tool_response":{}}' > "$TMP/p.json"
    run bash "$DISPATCH" < "$TMP/p.json"
    [ "$status" -eq 0 ]
    grep -q 'sync-pr' "$REC" || return 1
    # exactly one line — the override engine, not any other resolution path
    [ "$(wc -l < "$REC" | tr -d ' ')" -eq 1 ]
}

@test "missing tool_response key defaults ok=1 (still invokes engine on match)" {
    printf '{"tool_input":{"command":"git commit -m x"}}' > "$TMP/p.json"
    run bash "$DISPATCH" < "$TMP/p.json"
    [ "$status" -eq 0 ]
    grep -q 'sync-commit HEAD' "$REC"
}

# --- fail-open behavior -------------------------------------------------------

@test "fail-open: invalid JSON on stdin exits 0 and never invokes the engine" {
    printf 'not json at all {{{' > "$TMP/p.json"
    run bash "$DISPATCH" < "$TMP/p.json"
    [ "$status" -eq 0 ]
    [ ! -s "$REC" ]
}

@test "fail-open: empty stdin exits 0 and never invokes the engine" {
    run bash "$DISPATCH" < /dev/null
    [ "$status" -eq 0 ]
    [ ! -s "$REC" ]
}

@test "fail-open: engine binary exits non-zero (simulated git_ops/network failure) — hook still exits 0" {
    export ENGINE_RC=1
    printf '{"tool_input":{"command":"gh pr create -t x"},"tool_response":{}}' > "$TMP/p.json"
    run bash "$DISPATCH" < "$TMP/p.json"
    [ "$status" -eq 0 ]
    # the engine was still attempted (and recorded its call) despite failing
    grep -q 'sync-pr' "$REC"
}

@test "fail-open: engine binary missing/unresolvable — hook still exits 0" {
    export ISSUE_SUPPORT_ENGINE="$TMP/does-not-exist.sh"
    printf '{"tool_input":{"command":"git commit -m x"},"tool_response":{}}' > "$TMP/p.json"
    run bash "$DISPATCH" < "$TMP/p.json"
    [ "$status" -eq 0 ]
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
    [ ! -s "$REC" ]
}

@test "underlying command marked is_error:true never invokes the engine (H4)" {
    printf '{"tool_input":{"command":"gh pr create -t x"},"tool_response":{"is_error":true}}' > "$TMP/p.json"
    run bash "$DISPATCH" < "$TMP/p.json"
    [ "$status" -eq 0 ]
    [ ! -s "$REC" ]
}

@test "underlying command marked error:<truthy> never invokes the engine" {
    printf '{"tool_input":{"command":"git commit -m x"},"tool_response":{"error":"boom"}}' > "$TMP/p.json"
    run bash "$DISPATCH" < "$TMP/p.json"
    [ "$status" -eq 0 ]
    [ ! -s "$REC" ]
}

# --- dedup/skip logic ---------------------------------------------------------

@test "dedup: a single matching command invokes the engine exactly once" {
    printf '{"tool_input":{"command":"gh pr create -t x"},"tool_response":{}}' > "$TMP/p.json"
    run bash "$DISPATCH" < "$TMP/p.json"
    [ "$status" -eq 0 ]
    [ "$(wc -l < "$REC" | tr -d ' ')" -eq 1 ]
}

@test "dedup: a command matching neither class invokes the engine zero times" {
    printf '{"tool_input":{"command":"echo hello world"},"tool_response":{}}' > "$TMP/p.json"
    run bash "$DISPATCH" < "$TMP/p.json"
    [ "$status" -eq 0 ]
    [ ! -s "$REC" ]
}

@test "dedup: classification is mutually exclusive — a commit-shaped command never also fires sync-pr" {
    printf '{"tool_input":{"command":"git commit -m \\"pr-create rollout\\""},"tool_response":{}}' > "$TMP/p.json"
    run bash "$DISPATCH" < "$TMP/p.json"
    [ "$status" -eq 0 ]
    grep -q 'sync-commit' "$REC" || return 1
    ! grep -q 'sync-pr' "$REC"
}

@test "dedup: two independent hook invocations each record their own single call (no cross-run merging)" {
    printf '{"tool_input":{"command":"gh pr create -t x"},"tool_response":{}}' > "$TMP/p1.json"
    printf '{"tool_input":{"command":"git commit -m x"},"tool_response":{}}' > "$TMP/p2.json"
    bash "$DISPATCH" < "$TMP/p1.json"
    bash "$DISPATCH" < "$TMP/p2.json"
    [ "$(wc -l < "$REC" | tr -d ' ')" -eq 2 ]
    grep -q 'sync-pr' "$REC" || return 1
    grep -q 'sync-commit HEAD' "$REC"
}

@test "glab mr-create is classified as pr and git_ops.sh mr-create is also recognized" {
    printf '{"tool_input":{"command":"glab mr create --title x"},"tool_response":{}}' > "$TMP/p.json"
    run bash "$DISPATCH" < "$TMP/p.json"
    [ "$status" -eq 0 ]
    grep -q 'sync-pr' "$REC" || return 1

    : >"$REC"
    printf '{"tool_input":{"command":"scripts/git_ops.sh mr-create"},"tool_response":{}}' > "$TMP/p2.json"
    run bash "$DISPATCH" < "$TMP/p2.json"
    [ "$status" -eq 0 ]
    grep -q 'sync-pr' "$REC"
}
