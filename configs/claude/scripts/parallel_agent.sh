#!/bin/bash
# ┌──────────────────────────────────────────────────────────────────────┐
# │  DEPRECATED: This shell script is superseded by parallel_agent.py   │
# │  Use instead:                                                       │
# │    python3 ~/.claude/scripts/parallel_agent.py [args...]            │
# │                                                                     │
# │  The Python implementation has full feature parity plus:            │
# │  - Async execution with streaming output                           │
# │  - Codex agent support (--codex-only, --codex-model, --no-codex)   │
# │  - services.yml integration                                        │
# │  - Synthesis engine for low-consensus results                      │
# │  - Rate limiting and structured logging                            │
# │                                                                     │
# │  This script will be removed in a future release.                  │
# └──────────────────────────────────────────────────────────────────────┘
#
# Parallel Agent Orchestration Script (DEPRECATED)
# Uses Cursor Agent, Gemini CLI, Claude CLI, and Codex CLI in parallel
#
# Usage:
#   ./scripts/parallel_agent.sh "Your task description"
#   ./scripts/parallel_agent.sh --analyze "path/to/file.py"
#   ./scripts/parallel_agent.sh --cursor-model advanced --claude-model opus --review file.py

set -e

# Security: Ensure all created files are only readable by the owner
umask 0077

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Manifest state directories
MANIFEST_STATE_ROOT="${MANIFEST_STATE_ROOT:-$HOME/.manifest}"
ORCHESTRATION_STATE_DIR="${ORCHESTRATION_STATE_DIR:-$MANIFEST_STATE_ROOT/orchestration}"
MANIFEST_TMP_DIR="${MANIFEST_TMP_DIR:-$MANIFEST_STATE_ROOT/tmp}"
CURSOR_STATE_DIR="${CURSOR_STATE_DIR:-$MANIFEST_STATE_ROOT/cursor}"
GEMINI_STATE_DIR="${GEMINI_STATE_DIR:-$MANIFEST_STATE_ROOT/gemini}"
CLAUDE_STATE_DIR="${CLAUDE_STATE_DIR:-$MANIFEST_STATE_ROOT/claude}"
CODEX_STATE_DIR="${CODEX_STATE_DIR:-${CODEX_HOME:-$MANIFEST_STATE_ROOT/codex}}"
DEFAULT_OUTPUT_DIR="$ORCHESTRATION_STATE_DIR/outputs"
STATE_PATH_FALLBACK=false
STATE_PATH_FALLBACK_REASON=""

# Prefer ~/.manifest state paths. Fallback to project-local output dir if unavailable.
if mkdir -p "$DEFAULT_OUTPUT_DIR" "$MANIFEST_TMP_DIR" "$CURSOR_STATE_DIR" "$GEMINI_STATE_DIR" "$CLAUDE_STATE_DIR" "$CODEX_STATE_DIR" 2> /dev/null &&
    [[ -w "$DEFAULT_OUTPUT_DIR" && -w "$MANIFEST_TMP_DIR" ]]; then
    OUTPUT_DIR="$DEFAULT_OUTPUT_DIR"
else
    OUTPUT_DIR="$PROJECT_ROOT/.agent_outputs"
    mkdir -p "$OUTPUT_DIR" 2> /dev/null || true
    STATE_PATH_FALLBACK=true
    STATE_PATH_FALLBACK_REASON="$HOME/.manifest state path is not writable"
fi

# Route temp files/directories to ~/.manifest/tmp when possible.
# If state root is unavailable, keep temp artifacts under the fallback output dir.
if [[ "$STATE_PATH_FALLBACK" == false && -d "$MANIFEST_TMP_DIR" && -w "$MANIFEST_TMP_DIR" ]]; then
    export TMPDIR="$MANIFEST_TMP_DIR"
else
    TMP_FALLBACK_DIR="$OUTPUT_DIR/tmp"
    mkdir -p "$TMP_FALLBACK_DIR" 2> /dev/null || true
    if [[ -d "$TMP_FALLBACK_DIR" && -w "$TMP_FALLBACK_DIR" ]]; then
        export TMPDIR="$TMP_FALLBACK_DIR"
    fi
fi

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
START_TIME=$(date +%s)

# macOS compatibility: use gtimeout if available, otherwise no timeout
TIMEOUT_CMD=""
if command -v gtimeout &> /dev/null; then
    TIMEOUT_CMD="gtimeout"
elif command -v timeout &> /dev/null; then
    TIMEOUT_CMD="timeout"
fi

# Wrapper function for timeout
run_with_timeout() {
    local seconds="$1"
    shift
    if [[ -n "$TIMEOUT_CMD" ]]; then
        $TIMEOUT_CMD "$seconds" "$@"
    else
        "$@"
    fi
}

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# Global array to track background process IDs
pids=()

# Cleanup function to restore cursor and kill background processes
cleanup() {
    local exit_code=$?

    # Restore cursor
    if command -v tput &> /dev/null; then
        tput cnorm 2> /dev/null || true
    fi

    # Kill background processes if they exist
    if [[ -n "${pids[*]}" ]]; then
        for pid in "${pids[@]}"; do
            if kill -0 "$pid" 2> /dev/null; then
                kill "$pid" 2> /dev/null || true
            fi
        done
    fi

    exit "$exit_code"
}

# Trap exit to ensure cleanup
trap cleanup EXIT

# Draw a progress bar
draw_bar() {
    local percentage="$1"
    local width=20
    local filled=$((percentage * width / 100))
    local empty=$((width - filled))

    # Optimized: Use printf for string generation instead of loops
    printf -v filled_str "%${filled}s" ""
    filled_str="${filled_str// /█}"
    printf -v empty_str "%${empty}s" ""
    empty_str="${empty_str// /·}"

    echo "[$filled_str$empty_str]"
}

# Format duration in human readable format
format_duration() {
    local seconds=$1
    if [[ $seconds -lt 60 ]]; then
        echo "${seconds}s"
    else
        local minutes=$((seconds / 60))
        local rem_seconds=$((seconds % 60))
        echo "${minutes}m ${rem_seconds}s"
    fi
}

usage() {
    echo "Parallel Agent Orchestration"
    echo ""
    echo "Usage:"
    echo "  $0 <prompt>                    Run all agents with a prompt"
    echo "  $0 --analyze <file>            Analyze a specific file"
    echo "  $0 --review <file>             Code review a file"
    echo "  $0 --improve <observation>     Improve an observation YAML"
    echo "  $0 --status                    Check system health and configuration"
    echo ""
    echo "Agent Selection:"
    echo "  --cursor-only                  Only run Cursor Agent"
    echo "  --gemini-only                  Only run Gemini CLI"
    echo "  --claude-only                  Only run Claude CLI"
    echo "  --codex-only                   Only run Codex CLI"
    echo "  --no-claude                    Disable Claude CLI (enabled by default if available)"
    echo "  --no-codex                     Disable Codex CLI (enabled by default if available)"
    echo ""
    echo "Model Selection:"
    echo "  --cursor-model <tier>          Cursor model: mini, flash, advanced, auto (default: auto)"
    echo "  --claude-model <tier>          Claude model: haiku, sonnet, opus (default: sonnet)"
    echo "  --gemini-model <tier>          Gemini model: flash, pro (default: flash)"
    echo "  --codex-model <tier|model>     Codex model: mini, flash, advanced, auto, or explicit model name"
    echo ""
    echo "Options:"
    echo "  --output <dir>                 Custom output directory"
    echo "  --timeout <sec>                Timeout per agent (default: 600)"
    echo "  --json                         Output results in JSON format"
    echo "  --full-output                  Include full agent outputs (no truncation)"
    echo "  --validate                     Check outputs against success criteria"
    echo "  --check-credits                Run pre-flight credit check"
    echo ""
    echo "Environment Variables:"
    echo "  GEMINI_INCLUDE_DIRS            Colon-separated directories for Gemini (default: pwd:~/.claude:~/.gemini)"
    echo "  CURSOR_MODEL_MINI              Model name for 'mini' tier (default: gpt-5.1-codex-mini)"
    echo "  CURSOR_MODEL_FLASH             Model name for 'flash' tier (default: gpt-5.1-codex)"
    echo "  CURSOR_MODEL_ADVANCED          Model name for 'advanced' tier (default: gpt-5.2)"
    echo "  GEMINI_MODEL_FLASH             Model name for 'flash' tier (default: gemini-3-flash-preview)"
    echo "  GEMINI_MODEL_PRO               Model name for 'pro' tier (default: gemini-3-pro-preview)"
    echo "  CODEX_MODEL_TIER               Codex model tier: mini, flash, advanced, auto (default: auto)"
    echo "  CODEX_MODEL                    Codex model override (tier or explicit model; takes precedence)"
    echo "  CODEX_MODEL_MINI               Model name for 'mini' tier (default: gpt-5.1-codex-mini)"
    echo "  CODEX_MODEL_FLASH              Model name for 'flash' tier (default: gpt-5.1-codex)"
    echo "  CODEX_MODEL_ADVANCED           Model name for 'advanced' tier (default: gpt-5.2)"
    echo "  MANIFEST_STATE_ROOT            Root state directory (default: ~/.manifest)"
    echo "  MANIFEST_TMP_DIR               Temp directory for orchestration (default: ~/.manifest/tmp)"
    echo "  CODEX_HOME                     Codex state directory (default: ~/.manifest/codex)"
    echo "  CHECK_CREDITS_PREFLIGHT        Enable pre-flight credit check (default: false)"
    echo ""
    echo "Examples:"
    echo "  $0 'Review the tuning orchestrator for bugs'"
    echo "  $0 --analyze src/tuning/orchestrator.py"
    echo "  $0 --cursor-model advanced --claude-model opus --review critical_auth.py"
    echo "  $0 --claude-only --claude-model haiku 'Quick question'"
    echo "  $0 --codex-only --codex-model advanced 'Review this file'"
    echo "  $0 --codex-only --codex-model gpt-5.3-codex 'Review this file'"
}

# Default settings
RUN_CURSOR=true
RUN_GEMINI=true
RUN_CLAUDE=true
RUN_CODEX=true
TIMEOUT=600 # 10 minutes - complex analyses need time

# Service configuration file
SERVICES_CONFIG="$PROJECT_ROOT/config/services.yml"

# Load service configuration from services.yml
load_services_config() {
    if [[ ! -f "$SERVICES_CONFIG" ]]; then
        # No services config, use defaults (all enabled)
        return 0
    fi

    # Parse YAML using awk (portable, no external dependencies)
    # Reads services.yml once and sets variables
    # Use process substitution to avoid subshell variable loss
    local config_settings
    config_settings=$(awk '
        BEGIN { section="" }
        /^[[:space:]]*claude:/ { section="claude" }
        /^[[:space:]]*gemini:/ { section="gemini" }
        /^[[:space:]]*cursor:/ { section="cursor" }
        /^[[:space:]]*codex:/ { section="codex" }
        /^[[:space:]]*enabled:[[:space:]]*true/ {
            if (section == "claude") print "RUN_CLAUDE=true;"
            if (section == "gemini") print "RUN_GEMINI=true;"
            if (section == "cursor") print "RUN_CURSOR=true;"
            if (section == "codex") print "RUN_CODEX=true;"
        }
        /^[[:space:]]*enabled:[[:space:]]*false/ {
            if (section == "claude") print "RUN_CLAUDE=false;"
            if (section == "gemini") print "RUN_GEMINI=false;"
            if (section == "cursor") print "RUN_CURSOR=false;"
            if (section == "codex") print "RUN_CODEX=false;"
        }
        /^[[:space:]]*minimum_agents:[[:space:]]*[0-9]+/ {
            if (match($0, /[0-9]+/)) {
                print "MIN_AGENTS=" substr($0, RSTART, RLENGTH) ";"
            }
        }
    ' "$SERVICES_CONFIG")

    if [[ -n "$config_settings" ]]; then
        while read -r line; do
            case "$line" in
                RUN_CLAUDE=*) RUN_CLAUDE="${line#RUN_CLAUDE=}"; RUN_CLAUDE="${RUN_CLAUDE%;}" ;;
                RUN_GEMINI=*) RUN_GEMINI="${line#RUN_GEMINI=}"; RUN_GEMINI="${RUN_GEMINI%;}" ;;
                RUN_CURSOR=*) RUN_CURSOR="${line#RUN_CURSOR=}"; RUN_CURSOR="${RUN_CURSOR%;}" ;;
                RUN_CODEX=*) RUN_CODEX="${line#RUN_CODEX=}"; RUN_CODEX="${RUN_CODEX%;}" ;;
                MIN_AGENTS=*) MIN_AGENTS="${line#MIN_AGENTS=}"; MIN_AGENTS="${MIN_AGENTS%;}" ;;
            esac
        done <<< "$config_settings"
    fi

    # Check minimum agents requirement
    local min_agents=${MIN_AGENTS:-2}

    local enabled_count=0
    [[ "$RUN_CLAUDE" == true ]] && enabled_count=$((enabled_count + 1))
    [[ "$RUN_GEMINI" == true ]] && enabled_count=$((enabled_count + 1))
    [[ "$RUN_CURSOR" == true ]] && enabled_count=$((enabled_count + 1))
    [[ "$RUN_CODEX" == true ]] && enabled_count=$((enabled_count + 1))

    if [[ $enabled_count -lt $min_agents ]]; then
        echo -e "${YELLOW}Warning: Only $enabled_count services enabled (minimum: $min_agents)${NC}"
        echo -e "${YELLOW}Parallel agent features may be limited${NC}"
    fi
}

# Load services configuration (can be overridden by command-line args)
load_services_config
PROMPT=""
MODE="prompt"
TARGET=""
OUTPUT_FORMAT="markdown"
FULL_OUTPUT=false
VALIDATE=false
RETRY_COUNT=1
RETRY_DELAY=5
CONSENSUS_SCORE=0
CROSS_VERIFY_RAN=false
CUSTOM_OUTPUT_DIR=false

# Validation results cache
CURSOR_VAL_RESULT=-1
GEMINI_VAL_RESULT=-1
CLAUDE_VAL_RESULT=-1
CODEX_VAL_RESULT=-1

# Model selection defaults
CURSOR_MODEL_TIER="auto"
CURSOR_MODEL=""
CLAUDE_MODEL_TIER="sonnet"
CLAUDE_MODEL=""
GEMINI_MODEL_TIER="flash"
GEMINI_MODEL=""
CODEX_MODEL_SELECTION="${CODEX_MODEL:-${CODEX_MODEL_TIER:-auto}}"
CODEX_MODEL_TIER="auto"
CODEX_MODEL=""

# Codex runtime prerequisites
if [[ -n "${CODEX_HOME:-}" ]]; then
    CODEX_HOME_DIR="$CODEX_HOME"
elif [[ "$STATE_PATH_FALLBACK" == true ]]; then
    CODEX_HOME_DIR="$OUTPUT_DIR/codex"
else
    CODEX_HOME_DIR="$CODEX_STATE_DIR"
fi
CODEX_SESSIONS_DIR="$CODEX_HOME_DIR/sessions"
CODEX_RUNTIME_BLOCKED_REASON=""
# Use ~/.manifest/codex by default so Codex session state is co-located with Manifest state.
export CODEX_HOME="$CODEX_HOME_DIR"

# Per-run file paths (initialized after argument parsing)
CURSOR_OUTPUT_FILE=""
CURSOR_STDERR_FILE=""
GEMINI_OUTPUT_FILE=""
GEMINI_PROMPT_FILE=""
CLAUDE_OUTPUT_FILE=""
CLAUDE_STDERR_FILE=""
CLAUDE_PROMPT_FILE=""
CODEX_OUTPUT_FILE=""
CODEX_STDOUT_FILE=""
CODEX_STDERR_FILE=""
CODEX_LAST_MESSAGE_FILE=""
SUMMARY_FILE=""
JSON_FILE=""

# Credit exhaustion tracking
CURSOR_CREDIT_FALLBACK=false
CLAUDE_CREDIT_FALLBACK=false
CODEX_CREDIT_FALLBACK=false
CHECK_CREDITS_PREFLIGHT="${CHECK_CREDITS_PREFLIGHT:-false}"

# Model tier mappings (configurable via environment)
# Updated Jan 2026: GPT-5.x series now available in Cursor
CURSOR_MODEL_MINI="${CURSOR_MODEL_MINI:-gpt-5.1-codex-mini}"
CURSOR_MODEL_FLASH="${CURSOR_MODEL_FLASH:-gpt-5.1-codex}"
CURSOR_MODEL_ADVANCED="${CURSOR_MODEL_ADVANCED:-gpt-5.2}"

# Gemini model tier mappings (Gemini 3 series now available)
GEMINI_MODEL_FLASH="${GEMINI_MODEL_FLASH:-gemini-3-flash-preview}"
GEMINI_MODEL_PRO="${GEMINI_MODEL_PRO:-gemini-3-pro-preview}"

# Codex model tier mappings
CODEX_MODEL_MINI="${CODEX_MODEL_MINI:-gpt-5.1-codex-mini}"
CODEX_MODEL_FLASH="${CODEX_MODEL_FLASH:-gpt-5.1-codex}"
CODEX_MODEL_ADVANCED="${CODEX_MODEL_ADVANCED:-gpt-5.2}"

# Configurable directories for Gemini (colon-separated, like PATH)
GEMINI_INCLUDE_DIRS="${GEMINI_INCLUDE_DIRS:-$(pwd):$HOME/.claude:$HOME/.gemini}"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --help | -h)
            usage
            exit 0
            ;;
        --status)
            # Run the status check script
            STATUS_SCRIPT="$(dirname "$0")/check_status.sh"
            if [[ -f "$STATUS_SCRIPT" ]]; then
                "$STATUS_SCRIPT" "$@"
            else
                echo -e "${RED}Error: Status check script not found${NC}"
                echo -e "${YELLOW}Expected: $STATUS_SCRIPT${NC}"
                exit 1
            fi
            exit 0
            ;;
        --analyze)
            if [[ -z "$2" || "$2" == --* ]]; then
                echo -e "${RED}Error: --analyze requires a file path argument${NC}"
                exit 1
            fi
            MODE="analyze"
            TARGET="$2"
            shift 2
            ;;
        --review)
            if [[ -z "$2" || "$2" == --* ]]; then
                echo -e "${RED}Error: --review requires a file path argument${NC}"
                exit 1
            fi
            MODE="review"
            TARGET="$2"
            shift 2
            ;;
        --improve)
            if [[ -z "$2" || "$2" == --* ]]; then
                echo -e "${RED}Error: --improve requires a file path argument${NC}"
                exit 1
            fi
            MODE="improve"
            TARGET="$2"
            shift 2
            ;;
        --cursor-only)
            RUN_CURSOR=true
            RUN_GEMINI=false
            RUN_CLAUDE=false
            RUN_CODEX=false
            shift
            ;;
        --gemini-only)
            RUN_CURSOR=false
            RUN_GEMINI=true
            RUN_CLAUDE=false
            RUN_CODEX=false
            shift
            ;;
        --claude-only)
            RUN_CURSOR=false
            RUN_GEMINI=false
            RUN_CLAUDE=true
            RUN_CODEX=false
            shift
            ;;
        --codex-only)
            RUN_CURSOR=false
            RUN_GEMINI=false
            RUN_CLAUDE=false
            RUN_CODEX=true
            shift
            ;;
        --no-claude)
            RUN_CLAUDE=false
            shift
            ;;
        --no-codex)
            RUN_CODEX=false
            shift
            ;;
        --cursor-model)
            if [[ -z "$2" || "$2" == --* ]]; then
                echo -e "${RED}Error: --cursor-model requires a model tier (mini, flash, advanced, auto)${NC}"
                exit 1
            fi
            CURSOR_MODEL_TIER="$2"
            shift 2
            ;;
        --claude-model)
            if [[ -z "$2" || "$2" == --* ]]; then
                echo -e "${RED}Error: --claude-model requires a model tier (haiku, sonnet, opus)${NC}"
                exit 1
            fi
            CLAUDE_MODEL_TIER="$2"
            shift 2
            ;;
        --gemini-model)
            if [[ -z "$2" || "$2" == --* ]]; then
                echo -e "${RED}Error: --gemini-model requires a model tier (flash, pro)${NC}"
                exit 1
            fi
            GEMINI_MODEL_TIER="$2"
            shift 2
            ;;
        --codex-model)
            if [[ -z "$2" || "$2" == --* ]]; then
                echo -e "${RED}Error: --codex-model requires a tier/model (mini, flash, advanced, auto, or gpt-5.3-codex)${NC}"
                exit 1
            fi
            CODEX_MODEL_SELECTION="$2"
            shift 2
            ;;
        --output)
            OUTPUT_DIR="$2"
            CUSTOM_OUTPUT_DIR=true
            mkdir -p "$OUTPUT_DIR"
            shift 2
            ;;
        --timeout)
            TIMEOUT="$2"
            shift 2
            ;;
        --json)
            OUTPUT_FORMAT="json"
            shift
            ;;
        --full-output)
            FULL_OUTPUT=true
            shift
            ;;
        --validate)
            VALIDATE=true
            shift
            ;;
        --check-credits)
            CHECK_CREDITS_PREFLIGHT=true
            shift
            ;;
        *)
            if [[ -z "$PROMPT" ]]; then
                PROMPT="$1"
            else
                PROMPT="$PROMPT $1"
            fi
            shift
            ;;
    esac
done

# Initialize output/temp paths for this run.
initialize_output_paths() {
    local cursor_output_dir="$CURSOR_STATE_DIR/outputs"
    local gemini_output_dir="$GEMINI_STATE_DIR/outputs"
    local claude_output_dir="$CLAUDE_STATE_DIR/outputs"
    local codex_output_dir="$CODEX_STATE_DIR/outputs"
    local cursor_tmp_dir="$CURSOR_STATE_DIR/tmp"
    local gemini_tmp_dir="$GEMINI_STATE_DIR/tmp"
    local claude_tmp_dir="$CLAUDE_STATE_DIR/tmp"
    local codex_tmp_dir="$CODEX_STATE_DIR/tmp"

    if [[ "$STATE_PATH_FALLBACK" == true || "$CUSTOM_OUTPUT_DIR" == true ]]; then
        cursor_output_dir="$OUTPUT_DIR"
        gemini_output_dir="$OUTPUT_DIR"
        claude_output_dir="$OUTPUT_DIR"
        codex_output_dir="$OUTPUT_DIR"
    fi

    if [[ "$STATE_PATH_FALLBACK" == true ]]; then
        cursor_tmp_dir="$OUTPUT_DIR/tmp"
        gemini_tmp_dir="$OUTPUT_DIR/tmp"
        claude_tmp_dir="$OUTPUT_DIR/tmp"
        codex_tmp_dir="$OUTPUT_DIR/tmp"
    fi

    mkdir -p "$OUTPUT_DIR" \
        "$MANIFEST_TMP_DIR" \
        "$cursor_output_dir" "$gemini_output_dir" "$claude_output_dir" "$codex_output_dir" \
        "$cursor_tmp_dir" "$gemini_tmp_dir" "$claude_tmp_dir" "$codex_tmp_dir" \
        2> /dev/null || true

    chmod 700 "$OUTPUT_DIR" "$MANIFEST_TMP_DIR" \
        "$cursor_output_dir" "$gemini_output_dir" "$claude_output_dir" "$codex_output_dir" \
        "$cursor_tmp_dir" "$gemini_tmp_dir" "$claude_tmp_dir" "$codex_tmp_dir" \
        2> /dev/null || true

    CURSOR_OUTPUT_FILE="$cursor_output_dir/cursor_${TIMESTAMP}.txt"
    CURSOR_STDERR_FILE="$cursor_output_dir/cursor_${TIMESTAMP}_stderr.txt"

    GEMINI_OUTPUT_FILE="$gemini_output_dir/gemini_${TIMESTAMP}.txt"
    GEMINI_PROMPT_FILE="$gemini_tmp_dir/gemini_prompt_${TIMESTAMP}.txt"

    CLAUDE_OUTPUT_FILE="$claude_output_dir/claude_${TIMESTAMP}.txt"
    CLAUDE_STDERR_FILE="$claude_output_dir/claude_${TIMESTAMP}_stderr.txt"
    CLAUDE_PROMPT_FILE="$claude_tmp_dir/claude_prompt_${TIMESTAMP}.txt"

    CODEX_OUTPUT_FILE="$codex_output_dir/codex_${TIMESTAMP}.txt"
    CODEX_STDOUT_FILE="$codex_output_dir/codex_${TIMESTAMP}_stdout.txt"
    CODEX_STDERR_FILE="$codex_output_dir/codex_${TIMESTAMP}_stderr.txt"
    CODEX_LAST_MESSAGE_FILE="$codex_tmp_dir/codex_${TIMESTAMP}_last_message.txt"

    SUMMARY_FILE="$OUTPUT_DIR/summary_${TIMESTAMP}.md"
    JSON_FILE="$OUTPUT_DIR/results_${TIMESTAMP}.json"
}

# Resolve Cursor model tier to actual model name
resolve_cursor_model() {
    local tier="$1"
    case "$tier" in
        mini)
            CURSOR_MODEL="$CURSOR_MODEL_MINI"
            ;;
        flash)
            CURSOR_MODEL="$CURSOR_MODEL_FLASH"
            ;;
        advanced)
            CURSOR_MODEL="$CURSOR_MODEL_ADVANCED"
            ;;
        auto | "")
            CURSOR_MODEL=""
            ;;
        *)
            echo -e "${YELLOW}Warning: Unknown Cursor model tier '$tier', using auto${NC}"
            CURSOR_MODEL=""
            ;;
    esac
}

# Resolve Claude model tier to actual model name
resolve_claude_model() {
    local tier="$1"
    case "$tier" in
        haiku)
            CLAUDE_MODEL="haiku"
            ;;
        sonnet)
            CLAUDE_MODEL="sonnet"
            ;;
        opus)
            CLAUDE_MODEL="opus"
            ;;
        *)
            echo -e "${YELLOW}Warning: Unknown Claude model tier '$tier', using sonnet${NC}"
            CLAUDE_MODEL="sonnet"
            ;;
    esac
}

# Resolve Gemini model tier to actual model name
resolve_gemini_model() {
    local tier="$1"
    case "$tier" in
        flash)
            GEMINI_MODEL="$GEMINI_MODEL_FLASH"
            ;;
        pro)
            GEMINI_MODEL="$GEMINI_MODEL_PRO"
            ;;
        *)
            echo -e "${YELLOW}Warning: Unknown Gemini model tier '$tier', using flash${NC}"
            GEMINI_MODEL="$GEMINI_MODEL_FLASH"
            ;;
    esac
}

# Resolve Codex model tier to actual model name.
# Unknown values are treated as explicit model names for backwards compatibility.
resolve_codex_model() {
    local selection="$1"
    case "$selection" in
        mini)
            CODEX_MODEL="$CODEX_MODEL_MINI"
            CODEX_MODEL_TIER="mini"
            ;;
        flash)
            CODEX_MODEL="$CODEX_MODEL_FLASH"
            CODEX_MODEL_TIER="flash"
            ;;
        advanced)
            CODEX_MODEL="$CODEX_MODEL_ADVANCED"
            CODEX_MODEL_TIER="advanced"
            ;;
        auto | default | "")
            CODEX_MODEL=""
            CODEX_MODEL_TIER="auto"
            ;;
        *)
            CODEX_MODEL="$selection"
            CODEX_MODEL_TIER="custom"
            ;;
    esac
}

# Codex requires writable session storage even in non-interactive exec mode.
check_codex_runtime_access() {
    local sessions_dir="$CODEX_SESSIONS_DIR"
    local probe_file="$sessions_dir/.manifest_codex_probe_$$"

    if [[ ! -d "$sessions_dir" ]]; then
        if ! mkdir -p "$sessions_dir" 2> /dev/null; then
            CODEX_RUNTIME_BLOCKED_REASON="Cannot create session directory: $sessions_dir"
            return 1
        fi
    fi

    if [[ ! -w "$sessions_dir" ]]; then
        CODEX_RUNTIME_BLOCKED_REASON="Session directory is not writable: $sessions_dir"
        return 1
    fi

    if ! : > "$probe_file" 2> /dev/null; then
        CODEX_RUNTIME_BLOCKED_REASON="Unable to write session probe in: $sessions_dir"
        return 1
    fi

    rm -f "$probe_file" 2> /dev/null || true
    CODEX_RUNTIME_BLOCKED_REASON=""
    return 0
}

# Validate agent availability before launch
validate_agents() {
    local available=0

    if [[ "$RUN_CURSOR" == true ]]; then
        if ! command -v cursor &> /dev/null; then
            echo -e "${RED}Error: cursor command not found${NC}"
            echo "Install Cursor: https://www.cursor.com/downloads"
            RUN_CURSOR=false
        else
            available=$((available + 1))
        fi
    fi

    if [[ "$RUN_GEMINI" == true ]]; then
        if ! command -v gemini &> /dev/null; then
            echo -e "${RED}Error: gemini command not found${NC}"
            echo "Install: pip install google-generativeai && gemini configure"
            RUN_GEMINI=false
        else
            available=$((available + 1))
        fi
    fi

    if [[ "$RUN_CLAUDE" == true ]]; then
        if ! command -v claude &> /dev/null; then
            echo -e "${YELLOW}Warning: claude CLI not found, disabling Claude agent${NC}"
            echo "Install: https://docs.anthropic.com/en/docs/claude-cli"
            RUN_CLAUDE=false
        else
            available=$((available + 1))
        fi
    fi

    if [[ "$RUN_CODEX" == true ]]; then
        if ! command -v codex &> /dev/null; then
            echo -e "${YELLOW}Warning: codex CLI not found, disabling Codex agent${NC}"
            echo "Install: https://github.com/openai/codex"
            RUN_CODEX=false
        elif ! check_codex_runtime_access; then
            echo -e "${YELLOW}Warning: Codex runtime unavailable, disabling Codex agent${NC}"
            echo -e "${YELLOW}Reason:${NC} $CODEX_RUNTIME_BLOCKED_REASON"
            echo -e "${YELLOW}Fix:${NC} Ensure this path is writable: $CODEX_SESSIONS_DIR"
            RUN_CODEX=false
        else
            available=$((available + 1))
        fi
    fi

    if [[ $available -eq 0 ]]; then
        echo -e "${RED}Error: No agents available${NC}"
        echo ""
        echo -e "${YELLOW}Possible fixes:${NC}"
        echo -e "  1. Enable services: ${BOLD}./bootstrap.sh --reconfigure --enable-claude --enable-gemini --enable-codex${NC}"
        echo -e "  2. Check config:    ${BOLD}cat ~/.claude/config/services.yml${NC}"
        echo -e "  3. Install CLIs:    ${BOLD}npm install -g @anthropic-ai/claude-code @google/gemini-cli @openai/codex${NC}"
        echo ""
        echo -e "${BLUE}Troubleshooting:${NC} https://github.com/ReefBytes/Manifest/blob/main/docs/TROUBLESHOOTING.md#all-agents-disabled"
        return 1
    fi

    return 0
}

# Build prompts based on mode
build_prompts() {
    case $MODE in
        analyze)
            if [[ ! -f "$TARGET" ]]; then
                echo -e "${RED}Error: File not found: $TARGET${NC}"
                exit 1
            fi
            CURSOR_PROMPT="Analyze this file for bugs, improvements, and security issues: $TARGET"
            GEMINI_PROMPT="Review $TARGET for code quality, potential bugs, and suggest improvements. Focus on: error handling, edge cases, performance."
            CLAUDE_PROMPT="Analyze this file for security vulnerabilities, bugs, and code quality issues. Provide specific line-by-line recommendations: $TARGET"
            CODEX_PROMPT="Analyze this file for bugs, security issues, and maintainability concerns. Provide actionable recommendations: $TARGET"
            ;;
        review)
            if [[ ! -f "$TARGET" ]]; then
                echo -e "${RED}Error: File not found: $TARGET${NC}"
                exit 1
            fi
            CURSOR_PROMPT="Perform a detailed code review of $TARGET. Check for: bugs, security issues, performance problems, and code style."
            GEMINI_PROMPT="Code review $TARGET. Identify: potential bugs, security vulnerabilities, performance issues, and maintainability concerns."
            CLAUDE_PROMPT="Perform a comprehensive code review of $TARGET. Focus on security, correctness, performance, and maintainability. Provide actionable feedback."
            CODEX_PROMPT="Perform a thorough code review of $TARGET focusing on correctness, security, and maintainability. Provide concrete fixes."
            ;;
        improve)
            if [[ ! -f "$TARGET" ]]; then
                echo -e "${RED}Error: File not found: $TARGET${NC}"
                exit 1
            fi
            CURSOR_PROMPT="Review this observation YAML and suggest improvements for detection coverage and false positive reduction: $TARGET"
            GEMINI_PROMPT="Analyze this security observation YAML. Suggest improvements for: detection logic, entity mappings, and MITRE coverage. File: $TARGET"
            CLAUDE_PROMPT="Review this security observation YAML and suggest improvements for detection accuracy, coverage, and false positive reduction: $TARGET"
            CODEX_PROMPT="Review this security observation YAML and suggest specific improvements for coverage, precision, and maintainability: $TARGET"
            ;;
        prompt | *)
            CURSOR_PROMPT="$PROMPT"
            GEMINI_PROMPT="$PROMPT"
            CLAUDE_PROMPT="$PROMPT"
            CODEX_PROMPT="$PROMPT"
            ;;
    esac
}

# Run agent with retry logic
run_with_retry() {
    local agent_name="$1"
    local output_file="$2"
    shift 2
    local cmd=("$@")

    for ((attempt = 0; attempt <= RETRY_COUNT; attempt++)); do
        if [[ $attempt -gt 0 ]]; then
            echo -e "${YELLOW}[$agent_name]${NC} Retrying (attempt $attempt/$RETRY_COUNT)..."
            sleep $RETRY_DELAY
        fi

        if run_with_timeout "$TIMEOUT" "${cmd[@]}" > "$output_file" 2>&1; then
            echo -e "${GREEN}[$agent_name]${NC} Complete -> $output_file"
            return 0
        fi
    done

    echo -e "${YELLOW}[$agent_name]${NC} Failed after $RETRY_COUNT retries, continuing with partial results..."
    return 1
}

# Run agent with retry logic, capturing stderr separately for credit detection
run_with_retry_capture_stderr() {
    local agent_name="$1"
    local output_file="$2"
    local stderr_file="$3"
    shift 3
    local cmd=("$@")

    for ((attempt = 0; attempt <= RETRY_COUNT; attempt++)); do
        if [[ $attempt -gt 0 ]]; then
            echo -e "${YELLOW}[$agent_name]${NC} Retrying (attempt $attempt/$RETRY_COUNT)..."
            sleep $RETRY_DELAY
        fi

        if run_with_timeout "$TIMEOUT" "${cmd[@]}" > "$output_file" 2> "$stderr_file"; then
            echo -e "${GREEN}[$agent_name]${NC} Complete -> $output_file"
            return 0
        fi
    done

    echo -e "${YELLOW}[$agent_name]${NC} Failed after $RETRY_COUNT retries, continuing with partial results..."
    return 1
}

# Check stderr for credit/quota exhaustion patterns
check_credit_exhaustion() {
    local stderr_file="$1"
    local agent_name="$2"

    if [[ ! -f "$stderr_file" ]]; then
        return 1
    fi

    # Patterns indicating credit/quota issues
    if grep -qiE "credit|quota|rate.limit|exceeded|insufficient|billing|subscription|limit.reached|usage.limit" "$stderr_file" 2> /dev/null; then
        echo -e "${YELLOW}[$agent_name]${NC} Credit/quota exhaustion detected"
        return 0
    fi

    return 1
}

# Run Cursor Agent with optional model selection
run_cursor() {
    local prompt="$1"
    local model_args=()

    # Resolve model tier to actual model name
    resolve_cursor_model "$CURSOR_MODEL_TIER"

    if [[ -n "$CURSOR_MODEL" ]]; then
        model_args=("--model" "$CURSOR_MODEL")
        echo -e "${BLUE}[Cursor Agent]${NC} Starting with model: $CURSOR_MODEL..."
    else
        echo -e "${BLUE}[Cursor Agent]${NC} Starting (auto model selection)..."
    fi

    # Run with stderr capture for credit detection
    if ! run_with_retry_capture_stderr "Cursor Agent" "$CURSOR_OUTPUT_FILE" "$CURSOR_STDERR_FILE" \
        cursor agent --print --workspace "$PROJECT_ROOT" "${model_args[@]}" -- "$prompt"; then

        # Check for credit exhaustion
        if check_credit_exhaustion "$CURSOR_STDERR_FILE" "Cursor"; then
            echo -e "${YELLOW}[Cursor Agent]${NC} Credit exhaustion detected, retrying with auto mode..."
            CURSOR_CREDIT_FALLBACK=true
            CURSOR_MODEL=""

            # Retry without model specification
            run_with_retry "Cursor Agent (fallback)" "$CURSOR_OUTPUT_FILE" \
                cursor agent --print --workspace "$PROJECT_ROOT" -- "$prompt"
        fi
    fi
}

# Run Gemini CLI with model selection
run_gemini() {
    local prompt="$1"
    local include_args=()

    # Build include-directories arguments from colon-separated list
    IFS=':' read -ra dirs <<< "$GEMINI_INCLUDE_DIRS"
    for dir in "${dirs[@]}"; do
        if [[ -d "$dir" ]]; then
            include_args+=("--include-directories" "$dir")
        fi
    done

    # Write prompt to temp file for reliable handling of special characters
    printf '%s' "$prompt" > "$GEMINI_PROMPT_FILE"

    echo -e "${BLUE}[Gemini CLI]${NC} Starting with model: $GEMINI_MODEL..."
    # Gemini CLI: use -p flag for non-interactive (headless) mode.
    # Run from a temp directory to avoid loading project-level .gemini/ settings
    # (e.g., GEMINI.md orchestration guide) which can cause Gemini to
    # "investigate the environment" instead of answering the prompt.
    run_with_retry "Gemini CLI" "$GEMINI_OUTPUT_FILE" bash -c \
        'cd "$(mktemp -d)" && gemini --output-format text --model "$1" -p "" "${@:2}" < "$0"' \
        "$GEMINI_PROMPT_FILE" "$GEMINI_MODEL" "${include_args[@]}"
}

# Run Claude CLI with model selection
run_claude() {
    local prompt="$1"

    # Resolve model tier
    resolve_claude_model "$CLAUDE_MODEL_TIER"

    # Write prompt to temp file for reliable handling of special characters
    printf '%s' "$prompt" > "$CLAUDE_PROMPT_FILE"

    echo -e "${BLUE}[Claude CLI]${NC} Starting with model: $CLAUDE_MODEL..."

    # Claude CLI: use input redirection (saves cat process)
    if ! run_with_retry_capture_stderr "Claude CLI" "$CLAUDE_OUTPUT_FILE" "$CLAUDE_STDERR_FILE" \
        bash -c 'claude --print --output-format text --model "$1" --append-system-prompt "$2" < "$0"' \
        "$CLAUDE_PROMPT_FILE" "$CLAUDE_MODEL" \
        "You are a code analysis agent in a parallel orchestration system. Rules: Do NOT use emojis. Do NOT claim to have read files or performed actions you did not actually perform. Keep responses concise and technical. Report only findings from actual analysis of the provided content."; then

        # Check for credit exhaustion
        if check_credit_exhaustion "$CLAUDE_STDERR_FILE" "Claude"; then
            echo -e "${YELLOW}[Claude CLI]${NC} Credit exhaustion detected, retrying with haiku..."
            CLAUDE_CREDIT_FALLBACK=true
            CLAUDE_MODEL="haiku"

            # Retry with haiku (cheapest model)
            run_with_retry "Claude CLI (fallback)" "$CLAUDE_OUTPUT_FILE" \
                bash -c 'claude --print --output-format text --model haiku --append-system-prompt "$1" < "$0"' \
                "$CLAUDE_PROMPT_FILE" \
                "You are a code analysis agent in a parallel orchestration system. Rules: Do NOT use emojis. Do NOT claim to have read files or performed actions you did not actually perform. Keep responses concise and technical. Report only findings from actual analysis of the provided content."
        fi
    fi
}

# Run Codex CLI with optional model override
run_codex() {
    local prompt="$1"
    local model_args=()

    if [[ -n "$CODEX_MODEL" ]]; then
        model_args=("--model" "$CODEX_MODEL")
        if [[ "$CODEX_MODEL_TIER" == "custom" ]]; then
            echo -e "${BLUE}[Codex CLI]${NC} Starting with explicit model: $CODEX_MODEL..."
        else
            echo -e "${BLUE}[Codex CLI]${NC} Starting with tier '$CODEX_MODEL_TIER' -> $CODEX_MODEL..."
        fi
    else
        echo -e "${BLUE}[Codex CLI]${NC} Starting with default model from Codex config (tier: auto)..."
    fi

    # Codex CLI: use exec mode and write final assistant response to an explicit file.
    if run_with_retry_capture_stderr "Codex CLI" "$CODEX_STDOUT_FILE" "$CODEX_STDERR_FILE" \
        codex --sandbox read-only --ask-for-approval never exec --color never \
        --output-last-message "$CODEX_LAST_MESSAGE_FILE" "${model_args[@]}" "$prompt"; then

        if [[ -s "$CODEX_LAST_MESSAGE_FILE" ]]; then
            mv "$CODEX_LAST_MESSAGE_FILE" "$CODEX_OUTPUT_FILE"
        elif [[ -s "$CODEX_STDOUT_FILE" ]]; then
            mv "$CODEX_STDOUT_FILE" "$CODEX_OUTPUT_FILE"
        else
            echo "Codex completed with no output." > "$CODEX_OUTPUT_FILE"
        fi
        return 0
    fi

    # Retry once without explicit model if quota/model-specific limits are detected.
    if check_credit_exhaustion "$CODEX_STDERR_FILE" "Codex" && [[ -n "$CODEX_MODEL" ]]; then
        echo -e "${YELLOW}[Codex CLI]${NC} Credit exhaustion detected, retrying with default model..."
        CODEX_CREDIT_FALLBACK=true
        CODEX_MODEL=""
        CODEX_MODEL_TIER="auto"
        CODEX_MODEL_SELECTION="auto"

        if run_with_retry_capture_stderr "Codex CLI (fallback)" "$CODEX_STDOUT_FILE" "$CODEX_STDERR_FILE" \
            codex --sandbox read-only --ask-for-approval never exec --color never \
            --output-last-message "$CODEX_LAST_MESSAGE_FILE" "$prompt"; then

            if [[ -s "$CODEX_LAST_MESSAGE_FILE" ]]; then
                mv "$CODEX_LAST_MESSAGE_FILE" "$CODEX_OUTPUT_FILE"
            elif [[ -s "$CODEX_STDOUT_FILE" ]]; then
                mv "$CODEX_STDOUT_FILE" "$CODEX_OUTPUT_FILE"
            else
                echo "Codex fallback completed with no output." > "$CODEX_OUTPUT_FILE"
            fi
            return 0
        fi
    fi

    # Preserve diagnostics for downstream summary/validation steps.
    if [[ -s "$CODEX_LAST_MESSAGE_FILE" ]]; then
        mv "$CODEX_LAST_MESSAGE_FILE" "$CODEX_OUTPUT_FILE"
    elif [[ -s "$CODEX_STDOUT_FILE" ]]; then
        mv "$CODEX_STDOUT_FILE" "$CODEX_OUTPUT_FILE"
    else
        {
            echo "Codex execution failed."
            [[ -f "$CODEX_STDERR_FILE" ]] && cat "$CODEX_STDERR_FILE"
        } > "$CODEX_OUTPUT_FILE"
    fi

    return 1
}

# Pre-flight credit check (optional)
preflight_credit_check() {
    if [[ "$CHECK_CREDITS_PREFLIGHT" != true ]]; then
        return 0
    fi

    echo -e "${BLUE}=== Pre-flight Credit Check ===${NC}"

    local test_prompt="Echo: test"
    local test_output
    test_output=$(mktemp)
    local test_stderr
    test_stderr=$(mktemp)

    # Check Cursor credits if using a specific model
    if [[ "$RUN_CURSOR" == true ]]; then
        resolve_cursor_model "$CURSOR_MODEL_TIER"
        if [[ -n "$CURSOR_MODEL" ]]; then
            if ! run_with_timeout 15 cursor agent --print --model "$CURSOR_MODEL" -- "$test_prompt" \
                > "$test_output" 2> "$test_stderr"; then
                if check_credit_exhaustion "$test_stderr" "Cursor"; then
                    echo -e "${YELLOW}[Pre-flight]${NC} Cursor credits exhausted for $CURSOR_MODEL, will use auto mode"
                    CURSOR_MODEL=""
                    CURSOR_MODEL_TIER="auto"
                    CURSOR_CREDIT_FALLBACK=true
                fi
            fi
            rm -f "$test_output" "$test_stderr"
        fi
    fi

    # Check Claude credits
    if [[ "$RUN_CLAUDE" == true ]]; then
        resolve_claude_model "$CLAUDE_MODEL_TIER"
        if ! run_with_timeout 15 claude --print --output-format text --model "$CLAUDE_MODEL" -- "$test_prompt" \
            > "$test_output" 2> "$test_stderr"; then
            if check_credit_exhaustion "$test_stderr" "Claude"; then
                echo -e "${YELLOW}[Pre-flight]${NC} Claude credits exhausted for $CLAUDE_MODEL, will use haiku"
                CLAUDE_MODEL="haiku"
                CLAUDE_MODEL_TIER="haiku"
                CLAUDE_CREDIT_FALLBACK=true
            fi
        fi
        rm -f "$test_output" "$test_stderr"
    fi

    # Check Codex credits only when a concrete model is selected
    if [[ "$RUN_CODEX" == true && -n "$CODEX_MODEL" ]]; then
        if ! run_with_timeout 20 codex --sandbox read-only --ask-for-approval never exec --color never \
            --model "$CODEX_MODEL" --output-last-message "$test_output" "$test_prompt" \
            > /dev/null 2> "$test_stderr"; then
            if check_credit_exhaustion "$test_stderr" "Codex"; then
                echo -e "${YELLOW}[Pre-flight]${NC} Codex credits exhausted for $CODEX_MODEL, will use default model"
                CODEX_MODEL=""
                CODEX_MODEL_TIER="auto"
                CODEX_MODEL_SELECTION="auto"
                CODEX_CREDIT_FALLBACK=true
            fi
        fi
        rm -f "$test_output" "$test_stderr"
    fi

    echo ""
}

# Validate output against success criteria
validate_output() {
    local output_file="$1"
    local agent_name="$2"

    # Check if file exists and is non-empty
    if [[ ! -s "$output_file" ]]; then
        echo -e "${RED}[$agent_name]${NC} Validation FAILED: Empty output"
        return 1
    fi

    # Check for critical error keywords
    if grep -qi "error:\|exception:\|fatal:\|panic:" "$output_file"; then
        echo -e "${YELLOW}[$agent_name]${NC} Validation WARNING: Output contains error messages"
        return 2
    fi

    echo -e "${GREEN}[$agent_name]${NC} Validation PASSED"
    return 0
}

# Get output content (full or truncated)
get_output_content() {
    local file="$1"
    if [[ "$FULL_OUTPUT" == true ]]; then
        cat "$file"
    else
        head -100 "$file"
    fi
}

# Escape string for JSON - with fallback chain
# Optimized: Detects tool once to avoid repeated command -v checks
if command -v jq &> /dev/null; then
    json_escape() {
        printf '%s' "$1" | jq -Rs '.'
    }
elif command -v python3 &> /dev/null; then
    json_escape() {
        printf '%s' "$1" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))'
    }
elif command -v python &> /dev/null; then
    json_escape() {
        printf '%s' "$1" | python -c 'import json,sys; print(json.dumps(sys.stdin.read()))'
    }
else
    json_escape() {
        echo -e "${YELLOW}Warning: Neither jq nor python available for JSON escaping${NC}" >&2
        printf '"%s"' "$(printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g' | tr '\n' ' ')"
    }
fi

# Create JSON output
create_json_output() {
    local json_file="$JSON_FILE"
    local cursor_output=""
    local gemini_output=""
    local claude_output=""
    local codex_output=""
    local cursor_status="missing"
    local gemini_status="missing"
    local claude_status="missing"
    local codex_status="missing"
    local cursor_valid=false
    local gemini_valid=false
    local claude_valid=false
    local codex_valid=false

    # Process Cursor output
    if [[ -f "$CURSOR_OUTPUT_FILE" ]]; then
        cursor_output=$(get_output_content "$CURSOR_OUTPUT_FILE")
        cursor_status="complete"
        if [[ "$VALIDATE" == true && "$CURSOR_VAL_RESULT" -ne -1 ]]; then
            # Accept both passed (0) and warning (2) as valid
            [[ $CURSOR_VAL_RESULT -eq 0 || $CURSOR_VAL_RESULT -eq 2 ]] && cursor_valid=true
        fi
    fi

    # Process Gemini output
    if [[ -f "$GEMINI_OUTPUT_FILE" ]]; then
        gemini_output=$(get_output_content "$GEMINI_OUTPUT_FILE")
        gemini_status="complete"
        if [[ "$VALIDATE" == true && "$GEMINI_VAL_RESULT" -ne -1 ]]; then
            [[ $GEMINI_VAL_RESULT -eq 0 || $GEMINI_VAL_RESULT -eq 2 ]] && gemini_valid=true
        fi
    fi

    # Process Claude output
    if [[ -f "$CLAUDE_OUTPUT_FILE" ]]; then
        claude_output=$(get_output_content "$CLAUDE_OUTPUT_FILE")
        claude_status="complete"
        if [[ "$VALIDATE" == true && "$CLAUDE_VAL_RESULT" -ne -1 ]]; then
            [[ $CLAUDE_VAL_RESULT -eq 0 || $CLAUDE_VAL_RESULT -eq 2 ]] && claude_valid=true
        fi
    fi

    # Process Codex output
    if [[ -f "$CODEX_OUTPUT_FILE" ]]; then
        codex_output=$(get_output_content "$CODEX_OUTPUT_FILE")
        if grep -q "^Codex execution failed\." "$CODEX_OUTPUT_FILE" 2> /dev/null; then
            codex_status="failed"
        else
            codex_status="complete"
        fi
        if [[ "$VALIDATE" == true && "$CODEX_VAL_RESULT" -ne -1 ]]; then
            [[ $CODEX_VAL_RESULT -eq 0 || $CODEX_VAL_RESULT -eq 2 ]] && codex_valid=true
        fi
    fi

    # Count available agents for JSON
    local agent_count=0
    [[ "$cursor_status" == "complete" ]] && agent_count=$((agent_count + 1))
    [[ "$gemini_status" == "complete" ]] && agent_count=$((agent_count + 1))
    [[ "$claude_status" == "complete" ]] && agent_count=$((agent_count + 1))
    [[ "$codex_status" == "complete" ]] && agent_count=$((agent_count + 1))

    cat > "$json_file" << EOF
{
  "timestamp": "$TIMESTAMP",
  "duration_seconds": ${DURATION_SECONDS:-0},
  "duration_formatted": "${DURATION_FORMATTED:-0s}",
  "mode": "$MODE",
  "prompt": $(json_escape "${PROMPT:-$TARGET}"),
  "agents": {
    "cursor": {
      "status": "$cursor_status",
      "validated": $cursor_valid,
      "model": $(json_escape "${CURSOR_MODEL:-auto}"),
      "credit_fallback": $CURSOR_CREDIT_FALLBACK,
      "output": $(json_escape "$cursor_output")
    },
    "gemini": {
      "status": "$gemini_status",
      "validated": $gemini_valid,
      "model": $(json_escape "${GEMINI_MODEL:-$GEMINI_MODEL_FLASH}"),
      "output": $(json_escape "$gemini_output")
    },
    "claude": {
      "status": "$claude_status",
      "validated": $claude_valid,
      "model": $(json_escape "${CLAUDE_MODEL:-sonnet}"),
      "credit_fallback": $CLAUDE_CREDIT_FALLBACK,
      "output": $(json_escape "$claude_output")
    },
    "codex": {
      "status": "$codex_status",
      "validated": $codex_valid,
      "model_tier": $(json_escape "$CODEX_MODEL_TIER"),
      "model": $(json_escape "${CODEX_MODEL:-default}"),
      "credit_fallback": $CODEX_CREDIT_FALLBACK,
      "output": $(json_escape "$codex_output")
    }
  },
  "output_files": {
    "cursor": "$CURSOR_OUTPUT_FILE",
    "gemini": "$GEMINI_OUTPUT_FILE",
    "claude": "$CLAUDE_OUTPUT_FILE",
    "codex": "$CODEX_OUTPUT_FILE",
    "summary": "$SUMMARY_FILE"
  },
  "cross_verification": {
    "consensus_score": $CONSENSUS_SCORE,
    "confidence": "$(if [[ $CONSENSUS_SCORE -ge 80 ]]; then echo "high"; elif [[ $CONSENSUS_SCORE -ge 50 ]]; then echo "medium"; else echo "low"; fi)",
    "agent_count": $agent_count
  }
}
EOF

    echo -e "${GREEN}JSON:${NC} $json_file"
}

# Cross-verification: Compare agent outputs for consensus (supports 2+ agents)
cross_verify() {
    local cursor_file="$CURSOR_OUTPUT_FILE"
    local gemini_file="$GEMINI_OUTPUT_FILE"
    local claude_file="$CLAUDE_OUTPUT_FILE"
    local codex_file="$CODEX_OUTPUT_FILE"

    local available_outputs=()
    local agent_names=()

    if [[ -f "$cursor_file" ]]; then
        available_outputs+=("$cursor_file")
        agent_names+=("Cursor")
    fi
    if [[ -f "$gemini_file" ]]; then
        available_outputs+=("$gemini_file")
        agent_names+=("Gemini")
    fi
    if [[ -f "$claude_file" ]]; then
        available_outputs+=("$claude_file")
        agent_names+=("Claude")
    fi
    if [[ -f "$codex_file" ]]; then
        if grep -q "^Codex execution failed\." "$codex_file" 2> /dev/null; then
            echo -e "${YELLOW}Cross-verification: Skipping Codex output due to execution failure${NC}"
        else
            available_outputs+=("$codex_file")
            agent_names+=("Codex")
        fi
    fi

    local output_count=${#available_outputs[@]}

    if [[ $output_count -lt 2 ]]; then
        echo -e "${YELLOW}Cross-verification skipped: Need at least 2 agent outputs${NC}"
        return 1
    fi

    echo -e "${BLUE}=== Cross-Verification Analysis ($output_count agents) ===${NC}"

    local total_issues=0
    local total_warnings=0
    declare -a issues_arr=()
    declare -a warnings_arr=()

    # Collect metrics from each output
    for i in "${!available_outputs[@]}"; do
        local file="${available_outputs[$i]}"
        local name="${agent_names[$i]}"

        # Optimization: Use awk to count both metrics in a single pass
        # This replaces 2 grep processes and 2 tr processes per agent (4 forks) with 1 awk process
        local counts
        counts=$(awk '
            BEGIN { issues=0; warnings=0 }
            {
                line = tolower($0)
                if (line ~ /bug|error|issue|vulnerability|security|fix/) issues++
                if (line ~ /warning|caution|consider|potential|might/) warnings++
            }
            END { print issues, warnings }
        ' "$file" 2> /dev/null || echo "0 0")

        read -r issues warnings <<< "$counts"

        echo "$name: $issues issues, $warnings warnings"

        total_issues=$((total_issues + issues))
        total_warnings=$((total_warnings + warnings))
        issues_arr+=("$issues")
        warnings_arr+=("$warnings")
    done

    # Calculate variance-based consensus
    local total_findings=$((total_issues + total_warnings))
    local avg_issues=$((total_issues / output_count))
    local avg_warnings=$((total_warnings / output_count))

    # Calculate total deviation from averages
    local total_deviation=0
    for i in "${!available_outputs[@]}"; do
        local issues="${issues_arr[$i]}"
        local warnings="${warnings_arr[$i]}"

        local issue_dev=$((issues > avg_issues ? issues - avg_issues : avg_issues - issues))
        local warn_dev=$((warnings > avg_warnings ? warnings - avg_warnings : avg_warnings - warnings))
        total_deviation=$((total_deviation + issue_dev + warn_dev))
    done

    local consensus_score=100
    if [[ $total_findings -gt 0 ]]; then
        consensus_score=$(((total_findings - total_deviation) * 100 / total_findings))
        # Clamp to valid range [0, 100]
        if [[ $consensus_score -lt 0 ]]; then
            consensus_score=0
        elif [[ $consensus_score -gt 100 ]]; then
            consensus_score=100
        fi
    fi

    echo ""

    local bar
    bar=$(draw_bar $consensus_score)

    if [[ $consensus_score -ge 80 ]]; then
        echo -e "${GREEN}Consensus: HIGH ${bar} ${consensus_score}%${NC} - Agents largely agree"
    elif [[ $consensus_score -ge 50 ]]; then
        echo -e "${YELLOW}Consensus: MEDIUM ${bar} ${consensus_score}%${NC} - Some disagreement, review carefully"
    else
        echo -e "${RED}Consensus: LOW ${bar} ${consensus_score}%${NC} - Agents disagree significantly"
    fi

    # Store consensus score for JSON output
    CONSENSUS_SCORE=$consensus_score
    CROSS_VERIFY_RAN=true
    return 0
}

# Monitor agents and show status
monitor_agents() {
    # Check dependencies once to avoid repeated calls in the loop
    # Optimized for performance (avoiding repeated PATH lookups and shell overhead in the loop)
    local has_tput=false
    if command -v tput &> /dev/null; then
        has_tput=true
    fi

    local has_ps=false
    if command -v ps &> /dev/null; then
        has_ps=true
    fi

    # Hide cursor
    if $has_tput; then
        tput civis 2> /dev/null || true
    fi

    local running=true
    # Braille spinner for smoother animation
    local spinner=('⠋' '⠙' '⠹' '⠸' '⠼' '⠴' '⠦' '⠧' '⠇' '⠏')
    local spin_idx=0
    local start_seconds=$SECONDS

    # Track states locally
    local agent_states=()
    for i in "${!pids[@]}"; do agent_states[i]="running"; done

    local loop_count=0
    while $running; do
        running=false
        local status_line=""
        loop_count=$((loop_count + 1))

        # Calculate elapsed time
        local elapsed=$((SECONDS - start_seconds))
        local minutes=$((elapsed / 60))
        local seconds=$((elapsed % 60))
        local time_str
        time_str=$(printf "%02d:%02d" $minutes $seconds)

        # Advance spinner
        local spin_char="${spinner[$spin_idx]}"
        spin_idx=$(((spin_idx + 1) % ${#spinner[@]}))

        for i in "${!pids[@]}"; do
            local pid=${pids[$i]}
            local name=${agent_names[$i]}
            local state=${agent_states[$i]}

            local name_color="${NC}"
            if [[ "$name" == "Cursor" ]]; then name_color="${CYAN}"; fi
            if [[ "$name" == "Gemini" ]]; then name_color="${BLUE}"; fi
            if [[ "$name" == "Claude" ]]; then name_color="${MAGENTA}"; fi
            if [[ "$name" == "Codex" ]]; then name_color="${YELLOW}"; fi
            local display_name="${name_color}${name}${NC}"

            if [[ "$state" == "running" ]]; then
                local is_alive=false
                if kill -0 "$pid" 2> /dev/null; then
                    is_alive=true
                    # Check for zombie state
                    # Optimization: On Linux, read /proc directly to avoid 'ps' fork overhead
                    if [[ -r "/proc/$pid/stat" ]]; then
                        local stat_line
                        read -r stat_line < "/proc/$pid/stat" 2> /dev/null || true
                        # The command name (comm) is in parens and can contain spaces/parens.
                        # Everything after the last ')' starts with space then state.
                        local stat_rest="${stat_line##*)}"
                        local state_char="${stat_rest:1:1}"
                        if [[ "$state_char" == "Z" ]]; then
                            is_alive=false
                        fi
                    elif $has_ps; then
                        # Fallback (e.g. macOS): throttle ps to every 10th iteration (~1s)
                        if ((loop_count % 10 == 0)); then
                            local ps_state
                            ps_state=$(ps -o state= -p "$pid" 2> /dev/null || true)
                            if [[ "$ps_state" == *"Z"* ]]; then
                                is_alive=false
                            fi
                        fi
                    fi
                fi

                if $is_alive; then
                    status_line="$status_line $display_name [${CYAN}${spin_char}${NC}]"
                    running=true
                else
                    # Process finished
                    local code=0
                    set +e
                    wait "$pid"
                    code=$?
                    set -e
                    if [[ $code -eq 0 ]]; then
                        agent_states[$i]="${GREEN}✔${NC}"
                    else
                        agent_states[$i]="${RED}✘${NC}"
                    fi
                    status_line="$status_line $display_name [${agent_states[$i]}]"
                fi
            else
                status_line="$status_line $display_name [$state]"
            fi
        done

        if $running; then
            # \r to start, \033[K to clear line
            printf "\r${BOLD}Waiting for agents (%s):${NC}%b\033[K" "$time_str" "$status_line"
            sleep 0.1
        fi
    done

    # Final state
    local elapsed=$((SECONDS - start_seconds))
    local minutes=$((elapsed / 60))
    local seconds=$((elapsed % 60))
    local time_str
    time_str=$(printf "%02d:%02d" $minutes $seconds)

    printf "\r${BOLD}Agents completed (%s):${NC}%b\033[K\n" "$time_str" "$status_line"

    # Restore cursor
    if $has_tput; then
        tput cnorm 2> /dev/null || true
    fi
}

# Combine outputs into markdown summary
create_summary() {
    local summary_file="$SUMMARY_FILE"

    echo "# Parallel Agent Results - $TIMESTAMP" > "$summary_file"
    echo "" >> "$summary_file"
    echo "**Mode:** $MODE" >> "$summary_file"
    echo "**Duration:** $DURATION_FORMATTED" >> "$summary_file"
    echo "**Prompt/Target:** ${PROMPT:-$TARGET}" >> "$summary_file"

    if [[ "$CROSS_VERIFY_RAN" == true ]]; then
        local bar
        bar=$(draw_bar $CONSENSUS_SCORE)
        echo "**Consensus:** $CONSENSUS_SCORE% \`$bar\`" >> "$summary_file"
    fi

    echo "" >> "$summary_file"

    if [[ -f "$CURSOR_OUTPUT_FILE" ]]; then
        echo "## Cursor Agent Output" >> "$summary_file"
        [[ -n "$CURSOR_MODEL" ]] && echo "**Model:** $CURSOR_MODEL" >> "$summary_file"
        [[ "$CURSOR_CREDIT_FALLBACK" == true ]] && echo "**Note:** Used fallback mode due to credit exhaustion" >> "$summary_file"
        echo '```' >> "$summary_file"
        get_output_content "$CURSOR_OUTPUT_FILE" >> "$summary_file"
        echo '```' >> "$summary_file"
        echo "" >> "$summary_file"
    fi

    if [[ -f "$GEMINI_OUTPUT_FILE" ]]; then
        echo "## Gemini CLI Output" >> "$summary_file"
        echo '```' >> "$summary_file"
        get_output_content "$GEMINI_OUTPUT_FILE" >> "$summary_file"
        echo '```' >> "$summary_file"
        echo "" >> "$summary_file"
    fi

    if [[ -f "$CLAUDE_OUTPUT_FILE" ]]; then
        echo "## Claude CLI Output" >> "$summary_file"
        [[ -n "$CLAUDE_MODEL" ]] && echo "**Model:** $CLAUDE_MODEL" >> "$summary_file"
        [[ "$CLAUDE_CREDIT_FALLBACK" == true ]] && echo "**Note:** Used fallback mode due to credit exhaustion" >> "$summary_file"
        echo '```' >> "$summary_file"
        get_output_content "$CLAUDE_OUTPUT_FILE" >> "$summary_file"
        echo '```' >> "$summary_file"
        echo "" >> "$summary_file"
    fi

    if [[ -f "$CODEX_OUTPUT_FILE" ]]; then
        echo "## Codex CLI Output" >> "$summary_file"
        [[ -n "$CODEX_MODEL" ]] && echo "**Model:** $CODEX_MODEL (tier: $CODEX_MODEL_TIER)" >> "$summary_file"
        [[ "$CODEX_CREDIT_FALLBACK" == true ]] && echo "**Note:** Used default model due to credit exhaustion" >> "$summary_file"
        echo '```' >> "$summary_file"
        get_output_content "$CODEX_OUTPUT_FILE" >> "$summary_file"
        echo '```' >> "$summary_file"
        echo "" >> "$summary_file"
    fi

    echo -e "${GREEN}Summary:${NC} $summary_file"

    # Also create JSON if requested
    if [[ "$OUTPUT_FORMAT" == "json" ]]; then
        create_json_output
    fi
}

# Print results table
print_results_table() {
    echo -e "${BLUE}=== Execution Summary ===${NC}"
    echo ""
    if [[ "$MODE" == "analyze" || "$MODE" == "review" ]]; then
        echo "Task: $MODE $TARGET"
        echo ""
    fi

    # Table Header
    # Agent (10) | Status (10) | Model (20) | Validation (10)
    printf "${BOLD}%-10s | %-10s | %-20s" "Agent" "Status" "Model"
    if [[ "$VALIDATE" == true ]]; then
        printf " | %-10s" "Validation"
    fi
    printf "${NC}\n"

    printf "%s\n" "-----------|------------|----------------------$(if [[ "$VALIDATE" == true ]]; then echo "-|------------"; fi)"

    # Cursor Row
    if [[ "$RUN_CURSOR" == true ]]; then
        local status="SKIPPED"
        local model="${CURSOR_MODEL:-auto}"
        local val_status=""
        local color="${NC}"

        if [[ -f "$CURSOR_OUTPUT_FILE" ]]; then
            status="COMPLETE"
            color="${GREEN}"
        else
            status="FAILED"
            color="${RED}"
        fi

        if [[ "$CURSOR_CREDIT_FALLBACK" == true ]]; then
            model="$model (fallback)"
        fi

        printf "%-10s | ${color}%-10s${NC} | %-20s" "Cursor" "$status" "$model"

        if [[ "$VALIDATE" == true ]]; then
            if [[ "$CURSOR_VAL_RESULT" -eq 0 ]]; then
                val_status="${GREEN}PASSED${NC}"
            elif [[ "$CURSOR_VAL_RESULT" -eq 2 ]]; then
                val_status="${YELLOW}WARNING${NC}"
            elif [[ "$CURSOR_VAL_RESULT" -eq 1 ]]; then
                val_status="${RED}FAILED${NC}"
            else
                val_status="${NC}N/A${NC}"
            fi
            printf " | %-10b" "$val_status"
        fi
        printf "\n"
    fi

    # Gemini Row
    if [[ "$RUN_GEMINI" == true ]]; then
        local status="SKIPPED"
        local model="${GEMINI_MODEL:-flash}"
        local val_status=""
        local color="${NC}"

        if [[ -f "$GEMINI_OUTPUT_FILE" ]]; then
            status="COMPLETE"
            color="${GREEN}"
        else
            status="FAILED"
            color="${RED}"
        fi

        printf "%-10s | ${color}%-10s${NC} | %-20s" "Gemini" "$status" "$model"

        if [[ "$VALIDATE" == true ]]; then
            if [[ "$GEMINI_VAL_RESULT" -eq 0 ]]; then
                val_status="${GREEN}PASSED${NC}"
            elif [[ "$GEMINI_VAL_RESULT" -eq 2 ]]; then
                val_status="${YELLOW}WARNING${NC}"
            elif [[ "$GEMINI_VAL_RESULT" -eq 1 ]]; then
                val_status="${RED}FAILED${NC}"
            else
                val_status="${NC}N/A${NC}"
            fi
            printf " | %-10b" "$val_status"
        fi
        printf "\n"
    fi

    # Claude Row
    if [[ "$RUN_CLAUDE" == true ]]; then
        local status="SKIPPED"
        local model="${CLAUDE_MODEL:-sonnet}"
        local val_status=""
        local color="${NC}"

        if [[ -f "$CLAUDE_OUTPUT_FILE" ]]; then
            status="COMPLETE"
            color="${GREEN}"
        else
            status="FAILED"
            color="${RED}"
        fi

        if [[ "$CLAUDE_CREDIT_FALLBACK" == true ]]; then
            model="$model (fallback)"
        fi

        printf "%-10s | ${color}%-10s${NC} | %-20s" "Claude" "$status" "$model"

        if [[ "$VALIDATE" == true ]]; then
            if [[ "$CLAUDE_VAL_RESULT" -eq 0 ]]; then
                val_status="${GREEN}PASSED${NC}"
            elif [[ "$CLAUDE_VAL_RESULT" -eq 2 ]]; then
                val_status="${YELLOW}WARNING${NC}"
            elif [[ "$CLAUDE_VAL_RESULT" -eq 1 ]]; then
                val_status="${RED}FAILED${NC}"
            else
                val_status="${NC}N/A${NC}"
            fi
            printf " | %-10b" "$val_status"
        fi
        printf "\n"
    fi

    # Codex Row
    if [[ "$RUN_CODEX" == true ]]; then
        local status="SKIPPED"
        local model="${CODEX_MODEL:-default}"
        local val_status=""
        local color="${NC}"

        if [[ -f "$CODEX_OUTPUT_FILE" ]]; then
            if grep -q "^Codex execution failed\." "$CODEX_OUTPUT_FILE" 2> /dev/null; then
                status="FAILED"
                color="${RED}"
            else
                status="COMPLETE"
                color="${GREEN}"
            fi
        else
            status="FAILED"
            color="${RED}"
        fi

        if [[ -n "$CODEX_MODEL" && "$CODEX_MODEL_TIER" != "custom" ]]; then
            model="$model ($CODEX_MODEL_TIER)"
        fi

        if [[ "$CODEX_CREDIT_FALLBACK" == true ]]; then
            model="$model (fallback)"
        fi

        printf "%-10s | ${color}%-10s${NC} | %-20s" "Codex" "$status" "$model"

        if [[ "$VALIDATE" == true ]]; then
            if [[ "$CODEX_VAL_RESULT" -eq 0 ]]; then
                val_status="${GREEN}PASSED${NC}"
            elif [[ "$CODEX_VAL_RESULT" -eq 2 ]]; then
                val_status="${YELLOW}WARNING${NC}"
            elif [[ "$CODEX_VAL_RESULT" -eq 1 ]]; then
                val_status="${RED}FAILED${NC}"
            else
                val_status="${NC}N/A${NC}"
            fi
            printf " | %-10b" "$val_status"
        fi
        printf "\n"
    fi

    echo ""

    if [[ "$CROSS_VERIFY_RAN" == true ]]; then
        local bar
        bar=$(draw_bar $CONSENSUS_SCORE)
        local score_color="${NC}"
        if [[ $CONSENSUS_SCORE -ge 80 ]]; then
            score_color="${GREEN}"
        elif [[ $CONSENSUS_SCORE -ge 50 ]]; then
            score_color="${YELLOW}"
        else score_color="${RED}"; fi

        echo -e "Consensus: ${score_color}${CONSENSUS_SCORE}%${NC} $bar"
    fi

    echo "Duration : $DURATION_FORMATTED"
    echo "Results  : $OUTPUT_DIR"
    echo ""
}

# Main execution
main() {
    if [[ -z "$PROMPT" && -z "$TARGET" ]]; then
        usage
        exit 1
    fi

    # Resolve model selection early so status/pre-flight use canonical values.
    resolve_codex_model "$CODEX_MODEL_SELECTION"

    # Prepare per-agent output and temp paths.
    initialize_output_paths

    # Validate agents are available before proceeding
    if ! validate_agents; then
        exit 2
    fi

    build_prompts

    echo -e "${GREEN}=== Parallel Agent Orchestration ===${NC}"
    echo "Mode: $MODE"
    echo "Output: $OUTPUT_DIR"
    echo "State: $MANIFEST_STATE_ROOT"
    if [[ "$STATE_PATH_FALLBACK" == true ]]; then
        echo -e "${YELLOW}Warning:${NC} $STATE_PATH_FALLBACK_REASON"
    fi
    [[ "$RUN_CURSOR" == true ]] && echo "Cursor: enabled (model: ${CURSOR_MODEL_TIER})"
    [[ "$RUN_GEMINI" == true ]] && echo "Gemini: enabled (model: ${GEMINI_MODEL_TIER})"
    [[ "$RUN_CLAUDE" == true ]] && echo "Claude: enabled (model: ${CLAUDE_MODEL_TIER})"
    [[ "$RUN_CODEX" == true ]] && echo "Codex: enabled (model: ${CODEX_MODEL:-default}, tier: ${CODEX_MODEL_TIER})"
    [[ "$OUTPUT_FORMAT" == "json" ]] && echo "Format: JSON"
    [[ "$FULL_OUTPUT" == true ]] && echo "Full output: enabled"
    [[ "$VALIDATE" == true ]] && echo "Validation: enabled"
    echo ""

    # Pre-flight credit check if enabled
    preflight_credit_check

    # Resolve models in parent process so variables are available for JSON output
    if [[ "$RUN_CURSOR" == true ]]; then
        resolve_cursor_model "$CURSOR_MODEL_TIER"
    fi
    if [[ "$RUN_GEMINI" == true ]]; then
        resolve_gemini_model "$GEMINI_MODEL_TIER"
    fi
    if [[ "$RUN_CLAUDE" == true ]]; then
        resolve_claude_model "$CLAUDE_MODEL_TIER"
    fi
    if [[ "$RUN_CODEX" == true ]]; then
        resolve_codex_model "$CODEX_MODEL_SELECTION"
    fi

    # Run agents in parallel using background processes
    # pids array is defined globally for cleanup trap
    pids=()
    agent_names=()

    if [[ "$RUN_CURSOR" == true && -n "$CURSOR_PROMPT" ]]; then
        run_cursor "$CURSOR_PROMPT" > /dev/null &
        pids+=($!)
        agent_names+=("Cursor")
    fi

    if [[ "$RUN_GEMINI" == true && -n "$GEMINI_PROMPT" ]]; then
        run_gemini "$GEMINI_PROMPT" > /dev/null &
        pids+=($!)
        agent_names+=("Gemini")
    fi

    if [[ "$RUN_CLAUDE" == true && -n "$CLAUDE_PROMPT" ]]; then
        run_claude "$CLAUDE_PROMPT" > /dev/null &
        pids+=($!)
        agent_names+=("Claude")
    fi

    if [[ "$RUN_CODEX" == true && -n "$CODEX_PROMPT" ]]; then
        run_codex "$CODEX_PROMPT" > /dev/null &
        pids+=($!)
        agent_names+=("Codex")
    fi

    # Monitor agents
    echo ""
    monitor_agents

    echo ""

    # Verify output files were created
    echo -e "${BLUE}=== Output File Check ===${NC}"
    local files_created=0
    if [[ "$RUN_CURSOR" == true ]]; then
        if [[ -f "$CURSOR_OUTPUT_FILE" ]]; then
            local size
            size=$(stat -f%z "$CURSOR_OUTPUT_FILE" 2> /dev/null || stat -c%s "$CURSOR_OUTPUT_FILE" 2> /dev/null || echo "0")
            echo -e "${GREEN}[Cursor]${NC} Output file created (${size} bytes)"
            files_created=$((files_created + 1))
        else
            echo -e "${RED}[Cursor]${NC} Output file NOT created: $CURSOR_OUTPUT_FILE"
        fi
    fi
    if [[ "$RUN_GEMINI" == true ]]; then
        if [[ -f "$GEMINI_OUTPUT_FILE" ]]; then
            local size
            size=$(stat -f%z "$GEMINI_OUTPUT_FILE" 2> /dev/null || stat -c%s "$GEMINI_OUTPUT_FILE" 2> /dev/null || echo "0")
            echo -e "${GREEN}[Gemini]${NC} Output file created (${size} bytes)"
            files_created=$((files_created + 1))
        else
            echo -e "${RED}[Gemini]${NC} Output file NOT created: $GEMINI_OUTPUT_FILE"
        fi
    fi
    if [[ "$RUN_CLAUDE" == true ]]; then
        if [[ -f "$CLAUDE_OUTPUT_FILE" ]]; then
            local size
            size=$(stat -f%z "$CLAUDE_OUTPUT_FILE" 2> /dev/null || stat -c%s "$CLAUDE_OUTPUT_FILE" 2> /dev/null || echo "0")
            echo -e "${GREEN}[Claude]${NC} Output file created (${size} bytes)"
            files_created=$((files_created + 1))
        else
            echo -e "${RED}[Claude]${NC} Output file NOT created: $CLAUDE_OUTPUT_FILE"
        fi
    fi
    if [[ "$RUN_CODEX" == true ]]; then
        if [[ -f "$CODEX_OUTPUT_FILE" ]]; then
            local size
            size=$(stat -f%z "$CODEX_OUTPUT_FILE" 2> /dev/null || stat -c%s "$CODEX_OUTPUT_FILE" 2> /dev/null || echo "0")
            if grep -q "^Codex execution failed\." "$CODEX_OUTPUT_FILE" 2> /dev/null; then
                echo -e "${YELLOW}[Codex]${NC} Output file created but execution failed (${size} bytes)"
            else
                echo -e "${GREEN}[Codex]${NC} Output file created (${size} bytes)"
            fi
            files_created=$((files_created + 1))
        else
            echo -e "${RED}[Codex]${NC} Output file NOT created: $CODEX_OUTPUT_FILE"
        fi
    fi

    if [[ $files_created -eq 0 ]]; then
        echo -e "${RED}ERROR: No output files were created!${NC}"
        echo -e "${YELLOW}This may indicate a permissions issue or sandbox restriction.${NC}"
        echo -e "${YELLOW}Try running with: --output $MANIFEST_STATE_ROOT/orchestration/outputs${NC}"
        exit 13
    fi

    echo ""

    # Run cross-verification if multiple agents were enabled
    local enabled_count=0
    [[ "$RUN_CURSOR" == true ]] && enabled_count=$((enabled_count + 1))
    [[ "$RUN_GEMINI" == true ]] && enabled_count=$((enabled_count + 1))
    [[ "$RUN_CLAUDE" == true ]] && enabled_count=$((enabled_count + 1))
    [[ "$RUN_CODEX" == true ]] && enabled_count=$((enabled_count + 1))

    if [[ $enabled_count -ge 2 ]]; then
        cross_verify
        echo ""
    fi

    # Run validation if enabled (once)
    if [[ "$VALIDATE" == true ]]; then
        echo -e "${BLUE}=== Validation Results ===${NC}"
        if [[ "$RUN_CURSOR" == true && -f "$CURSOR_OUTPUT_FILE" ]]; then
            validate_output "$CURSOR_OUTPUT_FILE" "Cursor Agent"
            CURSOR_VAL_RESULT=$?
        fi
        if [[ "$RUN_GEMINI" == true && -f "$GEMINI_OUTPUT_FILE" ]]; then
            validate_output "$GEMINI_OUTPUT_FILE" "Gemini CLI"
            GEMINI_VAL_RESULT=$?
        fi
        if [[ "$RUN_CLAUDE" == true && -f "$CLAUDE_OUTPUT_FILE" ]]; then
            validate_output "$CLAUDE_OUTPUT_FILE" "Claude CLI"
            CLAUDE_VAL_RESULT=$?
        fi
        if [[ "$RUN_CODEX" == true && -f "$CODEX_OUTPUT_FILE" ]]; then
            validate_output "$CODEX_OUTPUT_FILE" "Codex CLI"
            CODEX_VAL_RESULT=$?
        fi
        echo ""
    fi

    # Calculate duration
    END_TIME=$(date +%s)
    DURATION_SECONDS=$((END_TIME - START_TIME))
    DURATION_FORMATTED=$(format_duration "$DURATION_SECONDS")

    create_summary

    print_results_table
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then main "$@"; fi
