#!/usr/bin/env bats

bats_require_minimum_version 1.5.0
load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
HEALTH="$REPO_ROOT/plugins/manifest-workspace/skills/env-check/scripts/mcp_health.py"
HOOK="$REPO_ROOT/configs/claude/scripts/mcp_health_check.sh"
STATUS_SCRIPT="$REPO_ROOT/configs/claude/scripts/check_status.sh"
EXTENSION="$REPO_ROOT/configs/omp/extensions/manifest-health.ts"

setup() {
    SANDBOX="$(mktemp -d "${BATS_TMPDIR:-/tmp}/mcp_health.XXXXXX")"
    export HOME="$SANDBOX/home"
    export XDG_STATE_HOME="$SANDBOX/state"
    export XDG_DATA_HOME="$SANDBOX/data"
    export MCP_HEALTH_STATE_DIR="$SANDBOX/health"
    export MOCK_BIN="$SANDBOX/bin"
    mkdir -p "$HOME/.claude" "$MOCK_BIN" "$MCP_HEALTH_STATE_DIR"

    PYTHON_BIN="$(command -v python3)"
    export PYTHON_BIN
    ORIGINAL_PATH="$PATH"
    export PATH="$MOCK_BIN:/usr/bin:/bin"
    unset CLAUDECODE PI_CODING_AGENT_DIR OMP_AGENT_DIR
    unset MANIFEST_MCP_HEALTH_HELPER MANIFEST_HEALTH_PYTHON
    unset MANIFEST_MCP_HEALTH_OUTER_TIMEOUT_SECONDS

    write_claude_config
}

teardown() {
    export PATH="$ORIGINAL_PATH"
    if [[ -n "${SANDBOX:-}" && -d "$SANDBOX" ]]; then
        chmod -R u+w "$SANDBOX" 2>/dev/null || true
        rm -rf "$SANDBOX"
    fi
}

write_claude_config() {
    cat > "$HOME/.claude.json" <<'JSON'
{
  "mcpServers": {
    "context7": {
      "type": "http",
      "url": "https://configuration-secret.invalid/mcp"
    }
  }
}
JSON
}

write_claude() {
    cat > "$MOCK_BIN/claude"
    chmod +x "$MOCK_BIN/claude"
}

run_health() {
    run "$PYTHON_BIN" "$HEALTH" --json --probe --harness claude \
        --timeout-seconds 2 --state-dir "$MCP_HEALTH_STATE_DIR"
}

run_health_while_lock_held() {
    run "$PYTHON_BIN" - "$HEALTH" "$MCP_HEALTH_STATE_DIR" "$PYTHON_BIN" "$@" <<'PY'
import fcntl
import os
from pathlib import Path
import subprocess
import sys

health = sys.argv[1]
state_dir = Path(sys.argv[2])
python = sys.argv[3]
state_dir.mkdir(parents=True, exist_ok=True)
lock_path = state_dir / "mcp-claude.lock"
descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
try:
    fcntl.flock(descriptor, fcntl.LOCK_EX)
    result = subprocess.run(
        [python, health, *sys.argv[4:]],
        text=True,
        capture_output=True,
        check=False,
        timeout=5,
    )
finally:
    os.close(descriptor)
sys.stdout.write(result.stdout)
sys.stderr.write(result.stderr)
raise SystemExit(result.returncode)
PY
}

@test "verified Claude health is cached privately without raw endpoint output" {
    write_claude <<'SH'
#!/bin/sh
printf '%s\n' 'Checking MCP server health…'
printf '%s\n' 'context7: https://runtime-secret.invalid/mcp (HTTP) - ✔ Connected'
SH

    run_health

    assert_success
    assert_output --partial '"status": "ok"'
    assert_output --partial '"reason_code": "connected"'
    refute_output --partial 'runtime-secret'
    refute_output --partial 'configuration-secret'

    run "$PYTHON_BIN" -c 'import json,stat,sys; p=sys.argv[1]; d=json.load(open(p)); print(oct(stat.S_IMODE(__import__("os").stat(p).st_mode)), d["status"], "secret" in json.dumps(d).lower())' \
        "$MCP_HEALTH_STATE_DIR/mcp-claude.json"
    assert_success
    assert_output '0o600 ok False'
}

@test "authentication failure is degraded and raw CLI detail is not relayed" {
    write_claude <<'SH'
#!/bin/sh
printf '%s\n' 'context7: https://do-not-relay.invalid/mcp (HTTP) - ✘ Failed to connect — Authentication required: bearer-secret-marker'
SH

    run_health

    assert_failure 1
    assert_output --partial '"status": "degraded"'
    assert_output --partial '"reason_code": "auth_required"'
    refute_output --partial 'bearer-secret-marker'
    refute_output --partial 'do-not-relay'
}

@test "a sleeping CLI process group times out and its grandchild is terminated" {
    export MCP_GRANDCHILD_PID_FILE="$SANDBOX/grandchild.pid"
    write_claude <<'SH'
#!/bin/sh
sleep 30 &
printf '%s\n' "$!" > "$MCP_GRANDCHILD_PID_FILE"
wait
SH

    started="$SECONDS"
    run "$PYTHON_BIN" "$HEALTH" --json --probe --harness claude \
        --timeout-seconds 1 --state-dir "$MCP_HEALTH_STATE_DIR"
    elapsed=$((SECONDS - started))

    assert_failure 1
    assert_output --partial '"reason_code": "timeout"'
    [[ "$elapsed" -lt 5 ]] || return 1
    grandchild_pid="$(cat "$MCP_GRANDCHILD_PID_FILE")"
    for _ in 1 2 3 4 5; do
        kill -0 "$grandchild_pid" 2>/dev/null || break
        sleep 0.1
    done
    ! kill -0 "$grandchild_pid" 2>/dev/null
}

@test "oversized native output is rejected as unparseable" {
    write_claude <<'SH'
#!/bin/sh
dd if=/dev/zero bs=1048577 count=1 2>/dev/null | tr '\000' X
SH

    run_health

    assert_failure 1
    assert_output --partial '"reason_code": "unparseable"'
    [[ "${#output}" -lt 8192 ]]
}

@test "name-only and unrecognized Claude output cannot produce a green result" {
    write_claude <<'SH'
#!/bin/sh
printf '%s\n' 'context7: secret-output-marker'
SH

    run_health

    assert_failure 1
    assert_output --partial '"reason_code": "unparseable"'
    refute_output --partial 'secret-output-marker'
}

@test "invalid UTF-8 anywhere in Claude output cannot certify health" {
    write_claude <<'SH'
#!/bin/sh
printf '\377\n'
printf '%s\n' 'context7: https://example.invalid/mcp (HTTP) - ✔ Connected'
SH

    run_health

    assert_failure 1
    assert_output --partial '"reason_code": "unparseable"'
}

@test "an enabled plugin with no installed inventory is degraded" {
    cat > "$HOME/.claude/settings.json" <<'JSON'
{"enabledPlugins":{"fixture@marketplace":true}}
JSON
    write_claude <<'SH'
#!/bin/sh
printf '%s\n' 'context7: https://example.invalid/mcp (HTTP) - ✔ Connected'
SH

    run_health

    assert_failure 1
    assert_output --partial '"name": "__configuration__"'
    assert_output --partial '"reason_code": "unavailable"'
}

@test "plugin MCP names follow each harness native namespace" {
    plugin_root="$SANDBOX/plugin"
    mkdir -p "$plugin_root" "$HOME/.claude/plugins"
    cat > "$HOME/.claude/settings.json" <<'JSON'
{"enabledPlugins":{"fixture@marketplace":true}}
JSON
    printf '{"plugins":{"fixture@marketplace":[{"installPath":"%s"}]}}\n' \
        "$plugin_root" > "$HOME/.claude/plugins/installed_plugins.json"
    cat > "$plugin_root/.mcp.json" <<'JSON'
{"mcpServers":{"docs":{"command":"never-run"}}}
JSON
    write_claude <<'SH'
#!/bin/sh
printf '%s\n' 'context7: https://example.invalid/mcp (HTTP) - ✔ Connected'
printf '%s\n' 'plugin:fixture:docs: never-run - ✔ Connected'
SH

    run_health
    assert_success
    assert_output --partial '"name": "plugin:fixture:docs"'

    run "$PYTHON_BIN" "$HEALTH" --json --probe --harness omp \
        --inventory-observed --observed-server context7 \
        --observed-server fixture:docs --timeout-seconds 2 \
        --state-dir "$MCP_HEALTH_STATE_DIR"
    assert_success
    assert_output --partial '"name": "fixture:docs"'
    refute_output --partial '"name": "plugin:fixture:docs"'
}

@test "non-finite timeouts are usage errors" {
    run "$PYTHON_BIN" "$HEALTH" --json --probe --harness claude \
        --timeout-seconds nan --state-dir "$MCP_HEALTH_STATE_DIR"

    assert_failure 2
}

@test "missing Claude binary is unavailable rather than healthy" {
    run_health

    assert_failure 1
    assert_output --partial '"reason_code": "unavailable"'
}

@test "non-probe mode reuses fresh evidence without launching Claude" {
    write_claude <<'SH'
#!/bin/sh
printf '%s\n' 'context7: https://example.invalid/mcp (HTTP) - ✔ Connected'
SH
    run_health
    assert_success
    rm "$MOCK_BIN/claude"

    run "$PYTHON_BIN" "$HEALTH" --json --harness claude \
        --state-dir "$MCP_HEALTH_STATE_DIR"

    assert_success
    assert_output --partial '"status": "ok"'
}

@test "a contending probe without fresh evidence reports probe_in_progress" {
    run_health_while_lock_held --json --probe --harness claude \
        --timeout-seconds 2 --state-dir "$MCP_HEALTH_STATE_DIR"

    assert_failure 1
    assert_output --partial '"reason_code": "probe_in_progress"'
}

@test "a contending probe reuses fresh evidence without launching Claude" {
    write_claude <<'SH'
#!/bin/sh
printf '%s\n' 'context7: https://example.invalid/mcp (HTTP) - ✔ Connected'
SH
    run_health
    assert_success
    rm "$MOCK_BIN/claude"

    run_health_while_lock_held --json --probe --harness claude \
        --timeout-seconds 2 --state-dir "$MCP_HEALTH_STATE_DIR"

    assert_success
    assert_output --partial '"status": "ok"'
}

@test "stale cached evidence is degraded and not silently refreshed" {
    write_claude <<'SH'
#!/bin/sh
printf '%s\n' 'context7: https://example.invalid/mcp (HTTP) - ✔ Connected'
SH
    run_health
    assert_success
    "$PYTHON_BIN" -c 'import json,sys; p=sys.argv[1]; d=json.load(open(p)); d["observed_at"]="2000-01-01T00:00:00Z"; json.dump(d,open(p,"w"))' \
        "$MCP_HEALTH_STATE_DIR/mcp-claude.json"
    rm "$MOCK_BIN/claude"

    run "$PYTHON_BIN" "$HEALTH" --json --harness claude \
        --state-dir "$MCP_HEALTH_STATE_DIR"

    assert_failure 1
    assert_output --partial '"reason_code": "not_probed"'
}

@test "OMP inventory verifies imported servers and treats explicit disables as non-errors" {
    mkdir -p "$HOME/.omp/agent"
    cat > "$HOME/.omp/agent/mcp.json" <<'JSON'
{
  "mcpServers": {
    "optional-local": {"enabled": false, "command": "never-run"}
  },
  "disabledServers": ["disabled-plugin:server"]
}
JSON

    run "$PYTHON_BIN" "$HEALTH" --json --probe --harness omp \
        --inventory-observed --observed-server context7 \
        --timeout-seconds 2 --state-dir "$MCP_HEALTH_STATE_DIR"

    assert_success
    assert_output --partial '"name": "context7"'
    assert_output --partial '"name": "optional-local"'
    assert_output --partial '"status": "disabled"'
    assert_output --partial '"name": "disabled-plugin:server"'
}

@test "missing OMP tool inventory is degraded instead of empty-and-healthy" {
    run "$PYTHON_BIN" "$HEALTH" --json --probe --harness omp \
        --timeout-seconds 2 --state-dir "$MCP_HEALTH_STATE_DIR"

    assert_failure 1
    assert_output --partial '"name": "__inventory__"'
    assert_output --partial '"reason_code": "unavailable"'
}

@test "Claude startup hook warns on degraded health but always permits startup" {
    write_claude <<'SH'
#!/bin/sh
printf '%s\n' 'context7: https://secret-hook-output.invalid/mcp (HTTP) - ✘ Failed to connect — Authentication required'
SH

    run env MANIFEST_MCP_HEALTH_HELPER="$HEALTH" \
        MANIFEST_HEALTH_PYTHON="$PYTHON_BIN" \
        MANIFEST_MCP_HEALTH_OUTER_TIMEOUT_SECONDS=4 \
        sh "$HOOK"

    assert_success
    assert_output --partial 'MCP health: degraded (auth_required)'
    refute_output --partial 'secret-hook-output'
}

@test "Claude startup hook bounds a broken helper and reports a sanitized warning" {
    cat > "$SANDBOX/sleeping_helper.py" <<'PY'
import time
time.sleep(30)
PY

    started="$SECONDS"
    run env MANIFEST_MCP_HEALTH_HELPER="$SANDBOX/sleeping_helper.py" \
        MANIFEST_HEALTH_PYTHON="$PYTHON_BIN" \
        MANIFEST_MCP_HEALTH_OUTER_TIMEOUT_SECONDS=1 \
        sh "$HOOK"
    elapsed=$((SECONDS - started))

    assert_success
    assert_output 'MCP health: degraded (outer_timeout)'
    [[ "$elapsed" -lt 5 ]]
}

@test "Claude startup hook exposes missing runtime paths without blocking startup" {
    run env MANIFEST_MCP_HEALTH_HELPER="$SANDBOX/missing-helper.py" \
        MANIFEST_HEALTH_PYTHON="$PYTHON_BIN" sh "$HOOK"
    assert_success
    assert_output 'MCP health: degraded (helper_unavailable)'

    run env MANIFEST_MCP_HEALTH_HELPER="$HEALTH" \
        MANIFEST_HEALTH_PYTHON="$SANDBOX/missing-python" sh "$HOOK"
    assert_success
    assert_output 'MCP health: degraded (python_unavailable)'
}

@test "check_status reuses cached MCP health through the shared helper" {
    mkdir -p "$HOME/.claude/config"
    cat > "$HOME/.claude/config/services.yml" <<'YAML'
services:
  claude:
    enabled: false
  gemini:
    enabled: false
  cursor:
    enabled: false
  codex:
    enabled: false
  antigravity:
    enabled: false
  devin:
    enabled: false
YAML
    export MCP_STATUS_ARG_LOG="$SANDBOX/status-health-args.log"
    cat > "$SANDBOX/status_health.py" <<'PY'
import os
import sys

with open(os.environ["MCP_STATUS_ARG_LOG"], "a", encoding="utf-8") as handle:
    handle.write(" ".join(sys.argv[1:]) + "\n")
print("MCP health: degraded (timeout)")
raise SystemExit(1)
PY

    run env MANIFEST_MCP_HEALTH_HELPER="$SANDBOX/status_health.py" \
        MANIFEST_HEALTH_PYTHON="$PYTHON_BIN" bash "$STATUS_SCRIPT"

    assert_success
    assert_output --partial 'MCP Health:'
    assert_output --partial 'MCP health: degraded (timeout)'
    run cat "$MCP_STATUS_ARG_LOG"
    assert_line --index 0 '--harness claude'
    assert_line --index 1 '--harness omp'
    refute_output --partial '--probe'
}

@test "OMP extension passes inventory argv, stays headless-safe, and warns only on degradation" {
    command -v bun >/dev/null || skip "bun is required for the extension contract test"
    : > "$SANDBOX/helper.py"
    export EXTENSION_ARG_LOG="$SANDBOX/extension-args.log"
    cat > "$SANDBOX/fake-python" <<'SH'
#!/bin/sh
printf '%s\n' "$*" > "$EXTENSION_ARG_LOG"
if [ "${EXTENSION_RESULT:-ok}" = degraded ]; then
    printf '%s\n' '{"schema_version":1,"observed_at":"2026-01-01T00:00:00Z","harness":"omp","status":"degraded","servers":[{"name":"context7","status":"degraded","reason_code":"connection_failed"}]}'
    exit 1
fi
printf '%s\n' '{"schema_version":1,"observed_at":"2026-01-01T00:00:00Z","harness":"omp","status":"ok","servers":[{"name":"context7","status":"healthy","reason_code":"connected"}]}'
exit 0
SH
    chmod +x "$SANDBOX/fake-python"
    cat > "$SANDBOX/extension_harness.ts" <<'TS'
let startHandler: ((event: unknown, ctx: unknown) => Promise<void>) | undefined;
const notifications: unknown[] = [];
const pi = {
  on(name: string, handler: typeof startHandler) {
    if (name === "session_start") startHandler = handler;
  },
  getAllTools() {
    return [{ name: "docs", mcpServerName: "context7" }, { name: "read" }];
  },
};
const extension = await import(process.argv[2]);
extension.default(pi);
if (!startHandler) throw new Error("session_start handler was not registered");
const hasUI = process.env.EXTENSION_HAS_UI !== "false";
await startHandler({}, {
  hasUI,
  ui: { notify(message: string, level: string) { notifications.push([message, level]); } },
});
console.log(JSON.stringify(notifications));
TS

    run env MANIFEST_MCP_HEALTH_HELPER="$SANDBOX/helper.py" \
        MANIFEST_HEALTH_PYTHON="$SANDBOX/fake-python" \
        bun "$SANDBOX/extension_harness.ts" "$EXTENSION"

    assert_success
    assert_output '[]'
    run cat "$EXTENSION_ARG_LOG"
    assert_output --partial '--inventory-observed'
    assert_output --partial '--observed-server context7'

    run env MANIFEST_MCP_HEALTH_HELPER="$SANDBOX/helper.py" \
        MANIFEST_HEALTH_PYTHON="$SANDBOX/fake-python" \
        EXTENSION_RESULT=degraded \
        bun "$SANDBOX/extension_harness.ts" "$EXTENSION"
    assert_success
    assert_output '[["MCP health: degraded (connection_failed)","warning"]]'

    run env MANIFEST_MCP_HEALTH_HELPER="$SANDBOX/helper.py" \
        MANIFEST_HEALTH_PYTHON="$SANDBOX/fake-python" \
        EXTENSION_RESULT=degraded EXTENSION_HAS_UI=false \
        bun "$SANDBOX/extension_harness.ts" "$EXTENSION"
    assert_success
    assert_output '[]'
}

@test "runtime settings register the MCP check as a separate SessionStart hook once" {
    run "$PYTHON_BIN" - "$REPO_ROOT/configs/claude/settings.runtime.json" <<'PY'
import json
import sys

settings = json.load(open(sys.argv[1], encoding="utf-8"))
entries = settings["hooks"]["SessionStart"]
commands = [
    hook["command"]
    for entry in entries
    for hook in entry.get("hooks", [])
]
assert commands.count("~/.claude/scripts/mcp_health_check.sh") == 1, commands
mcp_entry = [
    entry
    for entry in entries
    if any(
        hook.get("command") == "~/.claude/scripts/mcp_health_check.sh"
        for hook in entry.get("hooks", [])
    )
]
assert len(mcp_entry) == 1, entries
assert len(mcp_entry[0]["hooks"]) == 1, mcp_entry
print("wired")
PY

    assert_success
    assert_output "wired"
}
