#!/usr/bin/env bats
# Tests for configs/cursor/hooks.json (spec 2026-07-11 cursor-feature-parity
# WS-4): schema validity, that every wired command references a real script,
# that each wired hook script is demonstrably correct under Cursor's stdin/
# JSON input contract (as opposed to Claude's), and that deploy_cursor_configs
# copies the file under the ENABLE_CURSOR toggle.

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$(cd "$BATS_TEST_DIRNAME/../.." && pwd)"
HOOKS_JSON="$REPO_ROOT/configs/cursor/hooks.json"

teardown() {
    if [[ -n "${SANDBOX:-}" && -d "$SANDBOX" ]]; then
        rm -rf "$SANDBOX"
    fi
}

# ── Schema validity (real repo file) ────────────────────────────────────────

@test "hooks.json is valid JSON" {
    run python3 -c "import json; json.load(open('$HOOKS_JSON'))"
    assert_success
}

@test "hooks.json declares version: 1 (required top-level field)" {
    run python3 -c "
import json
d = json.load(open('$HOOKS_JSON'))
assert d.get('version') == 1, f\"version={d.get('version')!r}\"
print('ok')
"
    assert_success
    assert_output --partial "ok"
}

@test "every hook entry has command + type:command (required fields)" {
    run python3 -c "
import json
d = json.load(open('$HOOKS_JSON'))
for event, entries in d.get('hooks', {}).items():
    for e in entries:
        assert isinstance(e.get('command'), str) and e['command'], f\"{event}: missing command\"
        assert e.get('type') == 'command', f\"{event}: type={e.get('type')!r}\"
print('ok')
"
    assert_success
    assert_output --partial "ok"
}

@test "every wired command references a script that exists in configs/claude/scripts" {
    run python3 -c "
import json, os
d = json.load(open('$HOOKS_JSON'))
scripts_dir = '$REPO_ROOT/configs/claude/scripts'
missing = []
for event, entries in d.get('hooks', {}).items():
    for e in entries:
        token = e['command'].split()[0]
        name = token.rsplit('/', 1)[-1]
        if not os.path.isfile(os.path.join(scripts_dir, name)):
            missing.append(f'{event}:{name}')
assert not missing, f'missing scripts: {missing}'
print('ok')
"
    assert_success
    assert_output --partial "ok"
}

@test "only documented Cursor hook events are used" {
    run python3 -c "
import json
d = json.load(open('$HOOKS_JSON'))
allowed = {'preToolUse', 'postToolUse', 'afterFileEdit', 'sessionStart', 'beforeSubmitPrompt', 'beforeShellExecution'}
used = set(d.get('hooks', {}))
assert used <= allowed, f'unknown events: {used - allowed}'
print('ok')
"
    assert_success
    assert_output --partial "ok"
}

@test "UserPromptSubmit's token-conserve echo has no beforeSubmitPrompt entry (excluded, unverified output contract)" {
    run python3 -c "
import json
d = json.load(open('$HOOKS_JSON'))
for e in d.get('hooks', {}).get('beforeSubmitPrompt', []):
    assert 'token-conserve' not in e.get('command', ''), 'plain echo shipped verbatim — see design spec section 5'
print('ok')
"
    assert_success
    assert_output --partial "ok"
}

# ── Correctness under Cursor's verified input contract ──────────────────────
# Each wired script is exercised with the field SHAPE Cursor actually sends
# (no tool_input wrapper; the field is top-level), proving the fallback
# extraction path — not just Claude's shape — is genuinely exercised. Payloads
# are written to a file and fed via stdin redirection to avoid fragile nested
# shell-quoting of embedded JSON.

@test "version_pin_hook.sh: Cursor afterFileEdit payload (top-level file_path, no tool_input) is honored" {
    tmpfile="$BATS_TEST_TMPDIR/requirements.txt"
    printf 'requests\n' > "$tmpfile"
    payload_file="$BATS_TEST_TMPDIR/payload.json"
    python3 -c "import json,sys; json.dump({'file_path': sys.argv[1], 'edits': [{'old_string':'a','new_string':'b'}]}, open(sys.argv[2], 'w'))" \
        "$tmpfile" "$payload_file"

    run "$REPO_ROOT/configs/claude/scripts/version_pin_hook.sh" < "$payload_file"
    assert_success
    # version_pin.sh --check always prints a Summary line once it actually
    # runs on the resolved file — this only appears if the top-level
    # file_path fallback resolved the path (the tool_input-first branch is
    # empty/absent under Cursor's shape).
    assert_output --partial "Summary:"
}

@test "version_pin_hook.sh: Cursor payload for a non-pinned filename is a silent no-op (exit 0)" {
    tmpfile="$BATS_TEST_TMPDIR/notes.txt"
    printf 'irrelevant\n' > "$tmpfile"
    payload_file="$BATS_TEST_TMPDIR/payload.json"
    python3 -c "import json,sys; json.dump({'file_path': sys.argv[1]}, open(sys.argv[2], 'w'))" \
        "$tmpfile" "$payload_file"

    run "$REPO_ROOT/configs/claude/scripts/version_pin_hook.sh" < "$payload_file"
    assert_success
    assert_output ""
}

@test "lint_on_edit_hook.sh: Cursor afterFileEdit payload (top-level file_path) is honored" {
    command -v shellcheck > /dev/null 2>&1 || skip "shellcheck not installed"
    tmpfile="$BATS_TEST_TMPDIR/bad.sh"
    printf '#!/usr/bin/env bash\necho $UNQUOTED\n' > "$tmpfile"
    payload_file="$BATS_TEST_TMPDIR/payload.json"
    python3 -c "import json,sys; json.dump({'file_path': sys.argv[1], 'edits': []}, open(sys.argv[2], 'w'))" \
        "$tmpfile" "$payload_file"

    run "$REPO_ROOT/configs/claude/scripts/lint_on_edit_hook.sh" < "$payload_file"
    assert_success
    # Only reachable if $FILE resolved via the top-level fallback (tool_input
    # is absent under Cursor's afterFileEdit shape) and shellcheck then ran.
    assert_output --partial "lint-on-edit:"
}

@test "guidance_hint.py: Cursor beforeShellExecution payload (top-level command, no tool_input) is honored" {
    SANDBOX="$BATS_TEST_TMPDIR/home"
    mkdir -p "$SANDBOX"
    payload_file="$BATS_TEST_TMPDIR/payload.json"
    printf '{"command":"git commit -m wip","cwd":"/tmp","sandbox":{}}' > "$payload_file"

    export HOME="$SANDBOX"
    run python3 "$REPO_ROOT/configs/claude/scripts/guidance_hint.py" < "$payload_file"
    assert_success
    assert_output --partial "/project-verify"
}

@test "guidance_hint.py: an unrelated Cursor beforeShellExecution command is silent (exit 0)" {
    SANDBOX="$BATS_TEST_TMPDIR/home2"
    mkdir -p "$SANDBOX"
    payload_file="$BATS_TEST_TMPDIR/payload.json"
    printf '{"command":"ls -la","cwd":"/tmp","sandbox":{}}' > "$payload_file"

    export HOME="$SANDBOX"
    run python3 "$REPO_ROOT/configs/claude/scripts/guidance_hint.py" < "$payload_file"
    assert_success
    assert_output ""
}

@test "deploy_stamp_check.sh: ignores a Cursor sessionStart payload on stdin and exits 0" {
    SANDBOX="$BATS_TEST_TMPDIR/no-stamp-home"
    mkdir -p "$SANDBOX"
    payload_file="$BATS_TEST_TMPDIR/payload.json"
    printf '{"session_id":"abc123","is_background_agent":false}' > "$payload_file"

    export HOME="$SANDBOX"
    run "$REPO_ROOT/configs/claude/scripts/deploy_stamp_check.sh" < "$payload_file"
    assert_success
}

@test "spec_review.sh --silent: ignores Cursor stdin shape, safe no-op with <2 artifacts" {
    workdir="$BATS_TEST_TMPDIR/spec-review-empty"
    mkdir -p "$workdir"
    payload_file="$BATS_TEST_TMPDIR/payload.json"
    printf '{"file_path":"/tmp/x","edits":[]}' > "$payload_file"

    run bash -c "cd '$workdir' && '$REPO_ROOT/configs/claude/scripts/spec_review.sh' --silent < '$payload_file'"
    assert_success
}

@test "hooks.json spec_review entry passes \$CLAUDE_PROJECT_DIR as the positional ROOT (FIX 1)" {
    # Reliability guard: without an explicit ROOT the hook discovers artifacts
    # from cwd '.', so a Cursor invocation from a non-root cwd would silently
    # find nothing. The wired command must pass $CLAUDE_PROJECT_DIR as ROOT.
    run python3 -c "
import json
d = json.load(open('$HOOKS_JSON'))
cmds = [e['command'] for e in d['hooks']['afterFileEdit'] if 'spec_review' in e['command']]
assert len(cmds) == 1, cmds
c = cmds[0]
assert '--silent' in c and 'CLAUDE_PROJECT_DIR' in c, c
# ROOT must come AFTER --silent (positional), not be a flag value.
assert c.index('--silent') < c.index('CLAUDE_PROJECT_DIR'), c
print('ok')
"
    assert_success
    assert_output --partial "ok"
}

@test "spec_review.sh --silent ROOT honors ROOT over cwd (proves the FIX 1 arg is load-bearing)" {
    # Artifacts live under ROOT; cwd is an unrelated empty dir. If the hook
    # keyed on cwd it would find <2 artifacts and no-op (no feedback.md). Passing
    # ROOT explicitly (as the hook now does with $CLAUDE_PROJECT_DIR) must make
    # discovery succeed and write feedback — the reliability property FIX 1 adds.
    root="$BATS_TEST_TMPDIR/proj-root"
    empty_cwd="$BATS_TEST_TMPDIR/elsewhere"
    mkdir -p "$root/specs/001" "$empty_cwd"
    printf 'spec body\n' > "$root/specs/001/spec.md"
    printf 'plan body\n' > "$root/specs/001/plan.md"

    # Stub reviewer CLI (consumes stdin, emits a finding), mirroring spec_review.bats.
    stub="$BATS_TEST_TMPDIR/agy"
    cat > "$stub" << 'STUB'
#!/usr/bin/env bash
cat >/dev/null
printf 'CLARIFICATION REQUIRED: fixture finding\n'
STUB
    chmod +x "$stub"

    state="$BATS_TEST_TMPDIR/state"
    run bash -c "cd '$empty_cwd' && \
        SPEC_REVIEW_CLI='$stub' SPEC_REVIEW_NO_DETACH=1 SPEC_REVIEW_STATE='$state' \
        SPEC_REVIEW_TEMPLATE='$REPO_ROOT/configs/claude/prompts/spec_review.md' \
        '$REPO_ROOT/configs/claude/scripts/spec_review.sh' --silent '$root'"
    assert_success
    [ -f "$state/feedback.md" ]   # discovery keyed on ROOT, not the empty cwd

    # Control: same run WITHOUT the ROOT arg (cwd-only) finds nothing -> no feedback.
    state2="$BATS_TEST_TMPDIR/state2"
    run bash -c "cd '$empty_cwd' && \
        SPEC_REVIEW_CLI='$stub' SPEC_REVIEW_NO_DETACH=1 SPEC_REVIEW_STATE='$state2' \
        SPEC_REVIEW_TEMPLATE='$REPO_ROOT/configs/claude/prompts/spec_review.md' \
        '$REPO_ROOT/configs/claude/scripts/spec_review.sh' --silent"
    assert_success
    [ ! -f "$state2/feedback.md" ]
}

# ── Deploy wiring (ENABLE_CURSOR gate) ──────────────────────────────────────

setup_deploy_sandbox() {
    export BATS_TMPDIR="${BATS_TMPDIR:-/tmp}"
    SANDBOX=$(mktemp -d "$BATS_TMPDIR/deploy_cursor_hooks.XXXXXX")

    # shellcheck disable=SC1090
    source "$REPO_ROOT/bootstrap/lib/common.sh"
    # shellcheck disable=SC1090
    source "$REPO_ROOT/bootstrap/lib/deploy.sh"

    export SCRIPT_DIR="$SANDBOX/repo"
    mkdir -p "$SCRIPT_DIR/configs/cursor/rules"
    printf '{"version":1,"hooks":{"sessionStart":[{"command":"~/.cursor/scripts/deploy_stamp_check.sh","type":"command"}]}}' \
        > "$SCRIPT_DIR/configs/cursor/hooks.json"

    export TARGET_DIR="$SANDBOX/home/.claude" # unused directly; link_shared_assets no-ops on missing targets
    export CURSOR_TARGET_DIR="$SANDBOX/home/.cursor"
    export ENABLE_CURSOR=true
    export ENABLE_PILOTFISH=false
}

@test "deploy_cursor_configs copies hooks.json to CURSOR_TARGET_DIR/hooks.json" {
    setup_deploy_sandbox
    run deploy_cursor_configs
    assert_success
    [ -f "$CURSOR_TARGET_DIR/hooks.json" ]
    run cat "$CURSOR_TARGET_DIR/hooks.json"
    assert_output --partial "deploy_stamp_check.sh"
}

@test "ENABLE_CURSOR=false: deploy_cursor_configs never writes hooks.json" {
    setup_deploy_sandbox
    export ENABLE_CURSOR=false
    run deploy_cursor_configs
    assert_success
    [ ! -e "$CURSOR_TARGET_DIR/hooks.json" ]
}

@test "missing configs/cursor/hooks.json source: deploy_cursor_configs still succeeds (no hooks.json written)" {
    setup_deploy_sandbox
    rm -f "$SCRIPT_DIR/configs/cursor/hooks.json"
    run deploy_cursor_configs
    assert_success
    [ ! -e "$CURSOR_TARGET_DIR/hooks.json" ]
}
