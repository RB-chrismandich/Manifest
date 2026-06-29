#!/bin/bash
# Parallel Agent Orchestration Readiness Check
# Usage: ./check_status.sh [--verbose]
#
# Scope: services.yml enabled agents, CLI availability, auth, Codex session
#        storage, and Manifest state directories.  Reports whether the system
#        has enough agents ready for parallel orchestration.
#
# Also invoked by: parallel_agent.py --status
#
# For full environment audit (MCP, symlinks, config syntax, labels):
#   use the /health-check skill in Claude Code.

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    cat <<'USAGE'
Usage: check_status.sh [--verbose]

Parallel-agent orchestration readiness check: services.yml enabled agents,
CLI availability, auth, and Manifest state directories.

  --verbose   Also print CLI locations and versions

Full environment audit (MCP, symlinks, config syntax): /health-check skill.
USAGE
    exit 0
fi

VERBOSE=false
if [[ "${1:-}" == "--verbose" ]]; then
    VERBOSE=true
fi

# Detect timeout command (timeout on Linux, gtimeout on macOS via coreutils);
# a bare `timeout` made auth checks always fail on stock macOS (issue #315).
# CHECK_STATUS_NO_TIMEOUT_CMD=1 forces the pure-bash fallback below (tests use
# this to exercise the no-coreutils path deterministically on any platform).
TIMEOUT_CMD=""
if [[ "${CHECK_STATUS_NO_TIMEOUT_CMD:-}" != "1" ]]; then
    if command -v timeout &> /dev/null; then
        TIMEOUT_CMD="timeout"
    elif command -v gtimeout &> /dev/null; then
        TIMEOUT_CMD="gtimeout"
    fi
fi

# Recursively SIGKILL a process and all its descendants. A bare `kill $pid`
# leaves grandchildren orphaned (e.g. the CLI's `node` workers), and an orphan
# that still holds the script's stdout pipe blocks any caller capturing our
# output — re-introducing the very stall we are bounding. Kill children first
# so we don't reparent them to init before we can find them.
kill_tree() {
    local pid="$1" child
    for child in $(pgrep -P "$pid" 2> /dev/null); do
        kill_tree "$child"
    done
    kill -9 "$pid" 2> /dev/null
}

# Run a command bounded by 3s. Prefer timeout(1)/gtimeout(1); otherwise fall
# back to a pure-bash watchdog so a slow CLI (e.g. `gemini auth status`, ~60s)
# can't stall the readiness check on machines without GNU coreutils — without
# this the whole check took ~196s on stock macOS.
run_with_timeout() {
    local secs=3
    if [[ -n "$TIMEOUT_CMD" ]]; then
        "$TIMEOUT_CMD" "$secs" "$@"
        return $?
    fi
    "$@" &
    local cmd_pid=$!
    { sleep "$secs"; kill_tree "$cmd_pid"; } &
    local watcher_pid=$!
    wait "$cmd_pid" 2> /dev/null
    local rc=$?
    # command finished first: cancel the watchdog so it doesn't linger
    kill_tree "$watcher_pid" 2> /dev/null
    wait "$watcher_pid" 2> /dev/null
    return "$rc"
}

antigravity_enabled=""

manifest_state_root="${MANIFEST_STATE_ROOT:-$HOME/.manifest}"
manifest_tmp_dir="${MANIFEST_TMP_DIR:-$manifest_state_root/tmp}"
claude_state_dir="${CLAUDE_STATE_DIR:-$manifest_state_root/claude}"
gemini_state_dir="${GEMINI_STATE_DIR:-$manifest_state_root/gemini}"
cursor_state_dir="${CURSOR_STATE_DIR:-$manifest_state_root/cursor}"
codex_state_dir="${CODEX_STATE_DIR:-${CODEX_HOME:-$manifest_state_root/codex}}"
export CODEX_HOME="${CODEX_HOME:-$codex_state_dir}"

echo -e "${BOLD}${BLUE}═══════════════════════════════════════════════════════${NC}"
echo -e "${BOLD}${BLUE}  Parallel Agent System Health Check${NC}"
echo -e "${BOLD}${BLUE}═══════════════════════════════════════════════════════${NC}"
echo ""

# Check if services.yml exists
echo -e "${BOLD}Configuration:${NC}"
if [[ -f ~/.claude/config/services.yml ]]; then
    echo -e "  ${GREEN}✓${NC} services.yml found"

    # Parse enabled services using grep (more portable than yq)
    claude_enabled=$(grep -A1 "^  claude:" ~/.claude/config/services.yml | grep "enabled:" | awk '{print $2}')
    gemini_enabled=$(grep -A1 "^  gemini:" ~/.claude/config/services.yml | grep "enabled:" | awk '{print $2}')
    cursor_enabled=$(grep -A1 "^  cursor:" ~/.claude/config/services.yml | grep "enabled:" | awk '{print $2}')
    codex_enabled=$(grep -A1 "^  codex:" ~/.claude/config/services.yml | grep "enabled:" | awk '{print $2}')
    antigravity_enabled=$(grep -A1 "^  antigravity:" ~/.claude/config/services.yml | grep "enabled:" | awk '{print $2}')
    # graphify is a managed TOOL, not a parallel-orchestration agent (it is reported
    # separately under CLI Tools and excluded from the agent count / working_agents).
    graphify_enabled=$(grep -A1 "^  graphify:" ~/.claude/config/services.yml | grep "enabled:" | awk '{print $2}')

    enabled_count=0
    [[ "$claude_enabled" == "true" ]] && enabled_count=$((enabled_count + 1))
    [[ "$gemini_enabled" == "true" ]] && enabled_count=$((enabled_count + 1))
    [[ "$cursor_enabled" == "true" ]] && enabled_count=$((enabled_count + 1))
    [[ "$codex_enabled" == "true" ]] && enabled_count=$((enabled_count + 1))
    [[ "$antigravity_enabled" == "true" ]] && enabled_count=$((enabled_count + 1))

    echo ""
    echo -e "${BOLD}Enabled Services (${enabled_count}/5):${NC}"

    if [[ "$claude_enabled" == "true" ]]; then
        echo -e "  ${GREEN}✓${NC} Claude"
    else
        echo -e "  ${YELLOW}○${NC} Claude (disabled)"
    fi

    if [[ "$gemini_enabled" == "true" ]]; then
        echo -e "  ${GREEN}✓${NC} Gemini"
    else
        echo -e "  ${YELLOW}○${NC} Gemini (disabled)"
    fi

    if [[ "$cursor_enabled" == "true" ]]; then
        echo -e "  ${GREEN}✓${NC} Cursor"
    else
        echo -e "  ${YELLOW}○${NC} Cursor (disabled)"
    fi

    if [[ "$codex_enabled" == "true" ]]; then
        echo -e "  ${GREEN}✓${NC} Codex"
    else
        echo -e "  ${YELLOW}○${NC} Codex (disabled)"
    fi

    if [[ "$antigravity_enabled" == "true" ]]; then
        echo -e "  ${GREEN}✓${NC} Antigravity"
    else
        echo -e "  ${YELLOW}○${NC} Antigravity (disabled)"
    fi

    if [[ $enabled_count -lt 2 ]]; then
        echo ""
        echo -e "  ${YELLOW}⚠${NC}  Warning: Minimum 2 services needed for parallel orchestration"
        echo -e "  ${BLUE}→${NC} Fix: ./bootstrap.sh --reconfigure --enable-claude --enable-gemini --enable-codex"
    fi
else
    echo -e "  ${RED}✗${NC} services.yml not found"
    echo -e "  ${BLUE}→${NC} Run: ./bootstrap.sh"
fi

echo ""

# Check CLI installations
echo -e "${BOLD}CLI Tools:${NC}"

claude_installed=false
if command -v claude &> /dev/null; then
    echo -e "  ${GREEN}✓${NC} Claude CLI installed"
    claude_installed=true
    if [[ "$VERBOSE" == true ]]; then
        echo -e "    Location: $(which claude)"
        echo -e "    Version:  $(claude --version 2> /dev/null || echo 'unknown')"
    fi
else
    echo -e "  ${RED}✗${NC} Claude CLI not installed"
    echo -e "    ${BLUE}→${NC} Install: npm install -g @anthropic-ai/claude-code"
fi

gemini_installed=false
if command -v gemini &> /dev/null; then
    echo -e "  ${GREEN}✓${NC} Gemini CLI installed"
    gemini_installed=true
    if [[ "$VERBOSE" == true ]]; then
        echo -e "    Location: $(which gemini)"
        echo -e "    Version:  $(gemini --version 2> /dev/null || echo 'unknown')"
    fi
else
    echo -e "  ${RED}✗${NC} Gemini CLI not installed"
    echo -e "    ${BLUE}→${NC} Install: npm install -g @google/gemini-cli"
fi

cursor_installed=false
if command -v cursor-agent &> /dev/null; then
    echo -e "  ${GREEN}✓${NC} cursor-agent CLI available"
    cursor_installed=true
    if [[ "$VERBOSE" == true ]]; then
        echo -e "    Location: $(which cursor-agent)"
    fi
else
    echo -e "  ${YELLOW}○${NC} cursor-agent not available (optional)"
    if [[ "$VERBOSE" == true ]]; then
        echo -e "    ${BLUE}→${NC} Install: curl https://cursor.com/install -fsS | bash"
    fi
fi

codex_installed=false
if command -v codex &> /dev/null; then
    echo -e "  ${GREEN}✓${NC} Codex CLI installed"
    codex_installed=true
    if [[ "$VERBOSE" == true ]]; then
        echo -e "    Location: $(which codex)"
        echo -e "    Version:  $(codex --version 2> /dev/null || echo 'unknown')"
    fi
else
    echo -e "  ${YELLOW}○${NC} Codex CLI not installed"
    if [[ "$VERBOSE" == true ]]; then
        echo -e "    ${BLUE}→${NC} Install: npm install -g @openai/codex"
    fi
fi

antigravity_installed=false
if command -v agy &> /dev/null; then
    echo -e "  ${GREEN}✓${NC} Antigravity CLI (agy) installed"
    antigravity_installed=true
    if [[ "$VERBOSE" == true ]]; then
        echo -e "    Location: $(which agy)"
    fi
else
    echo -e "  ${YELLOW}○${NC} Antigravity CLI (agy) not installed (optional)"
    if [[ "$VERBOSE" == true ]]; then
        echo -e "    ${BLUE}→${NC} Install via the Antigravity IDE (agy install)"
    fi
fi

# Graphify is a managed knowledge-graph tool, NOT a parallel-orchestration agent,
# so it is reported here but never counted toward orchestration readiness
# (no graphify_installed flag — it must not feed working_agents; spec 364 D4).
if [[ "$graphify_enabled" == "true" ]]; then
    if command -v graphify &> /dev/null; then
        echo -e "  ${GREEN}✓${NC} Graphify CLI installed"
        if [[ "$VERBOSE" == true ]]; then
            echo -e "    Location: $(which graphify)"
            echo -e "    Version:  $(graphify --version 2> /dev/null || echo 'unknown')"
            echo -e "    Backend:  host-agent (no API key required)"
        fi
    else
        echo -e "  ${YELLOW}○${NC} Graphify CLI not installed"
        if [[ "$VERBOSE" == true ]]; then
            echo -e "    ${BLUE}→${NC} Install: ./bootstrap.sh --enable-graphify  (uv tool install graphifyy)"
        fi
    fi
else
    echo -e "  ${YELLOW}○${NC} Graphify (disabled)"
fi

echo ""

# Check authentication
echo -e "${BOLD}Authentication:${NC}"

if [[ "$claude_installed" == true ]]; then
    # Add timeout to avoid hanging
    if run_with_timeout claude auth status &> /dev/null; then
        echo -e "  ${GREEN}✓${NC} Claude authenticated"
    else
        echo -e "  ${YELLOW}?${NC} Claude authentication unknown (check timeout)"
        echo -e "    ${BLUE}→${NC} Verify: claude auth status"
    fi
fi

if [[ "$gemini_installed" == true ]]; then
    # Prefer a fast credential check: `gemini auth status` has no real auth
    # subcommand and runs as a ~60s model call, so probe it only as a last
    # resort. An API key or the OAuth creds file is an immediate signal (same
    # file-presence heuristic as the Codex check above).
    if [[ -n "$GEMINI_API_KEY" || -n "$GOOGLE_API_KEY" || -f "$HOME/.gemini/oauth_creds.json" ]]; then
        echo -e "  ${GREEN}✓${NC} Gemini authenticated"
    elif run_with_timeout gemini auth status &> /dev/null; then
        echo -e "  ${GREEN}✓${NC} Gemini authenticated"
    else
        echo -e "  ${YELLOW}?${NC} Gemini authentication unknown (check timeout)"
        echo -e "    ${BLUE}→${NC} Verify: gemini auth status"
    fi
fi

if [[ "$codex_installed" == true ]]; then
    if [[ -n "$OPENAI_API_KEY" ]] || [[ -f "$CODEX_HOME/auth.json" ]] || [[ -f "$HOME/.codex/auth.json" ]]; then
        echo -e "  ${GREEN}✓${NC} Codex authenticated"
    else
        echo -e "  ${YELLOW}?${NC} Codex authentication unknown"
        echo -e "    ${BLUE}→${NC} Verify: codex login  (or set OPENAI_API_KEY)"
    fi
fi

codex_runtime_ready=true
if [[ "$codex_installed" == true && "$codex_enabled" == "true" ]]; then
    codex_home_dir="$CODEX_HOME"
    codex_sessions_dir="$codex_home_dir/sessions"
    if [[ -d "$codex_sessions_dir" ]]; then
        if [[ -w "$codex_sessions_dir" ]]; then
            if [[ "$VERBOSE" == true ]]; then
                echo -e "  ${GREEN}✓${NC} Codex sessions writable (${codex_sessions_dir})"
            fi
        else
            echo -e "  ${YELLOW}?${NC} Codex session storage not writable"
            echo -e "    ${BLUE}→${NC} Fix permissions: $codex_sessions_dir"
            codex_runtime_ready=false
        fi
    else
        codex_sessions_parent="$(dirname "$codex_sessions_dir")"
        if [[ -d "$codex_sessions_parent" && -w "$codex_sessions_parent" ]]; then
            if [[ "$VERBOSE" == true ]]; then
                echo -e "  ${GREEN}✓${NC} Codex session parent writable (${codex_sessions_parent})"
            fi
        else
            echo -e "  ${YELLOW}?${NC} Codex session path cannot be created"
            echo -e "    ${BLUE}→${NC} Fix permissions: $codex_sessions_parent"
            codex_runtime_ready=false
        fi
    fi
fi

echo ""

echo -e "${BOLD}State Directories:${NC}"
state_ok=true
for state_dir in "$manifest_tmp_dir" "$claude_state_dir" "$gemini_state_dir" "$cursor_state_dir" "$codex_state_dir"; do
    if mkdir -p "$state_dir" 2> /dev/null && [[ -w "$state_dir" ]]; then
        if [[ "$VERBOSE" == true ]]; then
            echo -e "  ${GREEN}✓${NC} $state_dir"
        fi
    else
        echo -e "  ${YELLOW}?${NC} Not writable: $state_dir"
        state_ok=false
    fi
done
if [[ "$state_ok" == true ]]; then
    echo -e "  ${GREEN}✓${NC} Manifest state root ready: $manifest_state_root"
fi

echo ""

# Model staleness (warn-only; full detail via model_check.sh directly)
echo -e "${BOLD}Model Pins:${NC}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -x "$SCRIPT_DIR/model_check.sh" ]]; then
    stale_pins=0
    skipped_pins=0
    unsupported_pins=0
    while IFS= read -r line; do
        case "$line" in
            OK:*)          [[ "$VERBOSE" == true ]] && echo -e "  ${GREEN}✓${NC} ${line#OK: }" ;;
            STALE:*)
                stale_pins=$((stale_pins + 1))
                echo -e "  ${YELLOW}⚠${NC}  ${line#STALE: }"
                ;;
            SKIPPED:*)
                skipped_pins=$((skipped_pins + 1))
                [[ "$VERBOSE" == true ]] && echo -e "  ${YELLOW}○${NC} ${line#SKIPPED: }"
                ;;
            UNSUPPORTED:*)
                unsupported_pins=$((unsupported_pins + 1))
                [[ "$VERBOSE" == true ]] && echo -e "  ${YELLOW}○${NC} ${line#UNSUPPORTED: }"
                ;;
        esac
    done < <("$SCRIPT_DIR/model_check.sh")
    # SKIPPED must not read as green: on OAuth-only machines (no API keys)
    # claude/gemini pins go unverified and broken pins hide behind a ✓.
    # UNSUPPORTED providers (no listing command at all) are called out in the
    # green line so "verified" never overclaims what was actually checked.
    if [[ "$stale_pins" -gt 0 ]]; then
        echo -e "  ${YELLOW}⚠${NC}  $stale_pins stale model pin(s) — update model_tiers in parallel_agent.yml"
    elif [[ "$skipped_pins" -gt 0 ]]; then
        echo -e "  ${YELLOW}○${NC} $skipped_pins check(s) unverified (no API credentials — run MODEL_CHECK_PROBE=1 model_check.sh for a live CLI probe)"
    elif [[ "$unsupported_pins" -gt 0 ]]; then
        echo -e "  ${GREEN}✓${NC} Model pin check complete — all verifiable pins OK ($unsupported_pins provider(s) have no listing command)"
    else
        echo -e "  ${GREEN}✓${NC} Model pin check complete — all pins verified"
    fi
else
    echo -e "  ${YELLOW}○${NC} model_check.sh not found — skipping"
fi
echo ""

# Overall status
echo -e "${BOLD}${BLUE}═══════════════════════════════════════════════════════${NC}"
echo -e "${BOLD}Overall Status:${NC}"

working_agents=0
[[ "$claude_installed" == true && "$claude_enabled" == "true" ]] && working_agents=$((working_agents + 1))
[[ "$gemini_installed" == true && "$gemini_enabled" == "true" ]] && working_agents=$((working_agents + 1))
[[ "$cursor_installed" == true && "$cursor_enabled" == "true" ]] && working_agents=$((working_agents + 1))
[[ "$codex_installed" == true && "$codex_enabled" == "true" && "$codex_runtime_ready" == true ]] && working_agents=$((working_agents + 1))
[[ "$antigravity_installed" == true && "$antigravity_enabled" == "true" ]] && working_agents=$((working_agents + 1))

if [[ $working_agents -ge 2 ]]; then
    echo -e "  ${GREEN}✓${NC} System ready for parallel orchestration (${working_agents} agents available)"
elif [[ $working_agents -eq 1 ]]; then
    echo -e "  ${YELLOW}⚠${NC}  Limited functionality (only ${working_agents} agent available)"
    echo -e "  ${BLUE}→${NC} Enable/install at least 2 agents for full features"
else
    echo -e "  ${RED}✗${NC} System not operational (no agents available)"
    echo -e "  ${BLUE}→${NC} Run: ./bootstrap.sh"
fi

echo -e "${BOLD}${BLUE}═══════════════════════════════════════════════════════${NC}"
echo ""

# Quick test option
if [[ $working_agents -ge 1 ]]; then
    echo -e "${BOLD}Quick Test:${NC}"
    echo -e "  ~/.claude/scripts/parallel_agent.py --json 'What is 2+2?'"
    echo ""
fi

echo -e "${BOLD}Documentation:${NC}"
echo -e "  Troubleshooting: docs/TROUBLESHOOTING.md"
echo -e "  Configuration:   docs/CONFIGURATION.md"
echo -e "  Getting Started: docs/GETTING_STARTED.md"
echo ""
