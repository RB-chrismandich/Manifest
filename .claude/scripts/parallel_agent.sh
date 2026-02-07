#!/bin/bash
# Parallel Agent Orchestration Script
# Uses Cursor Agent, Gemini CLI, and Claude CLI in parallel
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

# Detect if running in a sandboxed environment (e.g., Task subagent)
# Try to use ~/.claude/.agent_outputs, fallback to /tmp if not writable
DEFAULT_OUTPUT_DIR="$PROJECT_ROOT/.agent_outputs"
if mkdir -p "$DEFAULT_OUTPUT_DIR" 2> /dev/null && [ -w "$DEFAULT_OUTPUT_DIR" ]; then
    OUTPUT_DIR="$DEFAULT_OUTPUT_DIR"
else
    # Fallback to /tmp if ~/.claude/.agent_outputs is not writable
    OUTPUT_DIR="/tmp/.claude_agent_outputs_$$"
    echo "Warning: Using fallback output directory: $OUTPUT_DIR" >&2
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

# Create output directory
mkdir -p "$OUTPUT_DIR"
chmod 700 "$OUTPUT_DIR" 2> /dev/null || true

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
    echo "  --no-claude                    Disable Claude CLI (enabled by default if available)"
    echo ""
    echo "Model Selection:"
    echo "  --cursor-model <tier>          Cursor model: mini, flash, advanced, auto (default: auto)"
    echo "  --claude-model <tier>          Claude model: haiku, sonnet, opus (default: sonnet)"
    echo "  --gemini-model <tier>          Gemini model: flash, pro (default: flash)"
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
    echo "  GEMINI_INCLUDE_DIRS            Colon-separated directories for Gemini (default: pwd:~/.claude)"
    echo "  CURSOR_MODEL_MINI              Model name for 'mini' tier (default: gpt-5.1-codex-mini)"
    echo "  CURSOR_MODEL_FLASH             Model name for 'flash' tier (default: gpt-5.1-codex)"
    echo "  CURSOR_MODEL_ADVANCED          Model name for 'advanced' tier (default: gpt-5.2)"
    echo "  GEMINI_MODEL_FLASH             Model name for 'flash' tier (default: gemini-3-flash-preview)"
    echo "  GEMINI_MODEL_PRO               Model name for 'pro' tier (default: gemini-3-pro-preview)"
    echo "  CHECK_CREDITS_PREFLIGHT        Enable pre-flight credit check (default: false)"
    echo ""
    echo "Examples:"
    echo "  $0 'Review the tuning orchestrator for bugs'"
    echo "  $0 --analyze src/tuning/orchestrator.py"
    echo "  $0 --cursor-model advanced --claude-model opus --review critical_auth.py"
    echo "  $0 --claude-only --claude-model haiku 'Quick question'"
}

# Default settings
RUN_CURSOR=true
RUN_GEMINI=true
RUN_CLAUDE=true
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
        /^[[:space:]]*enabled:[[:space:]]*true/ {
            if (section == "claude") print "RUN_CLAUDE=true;"
            if (section == "gemini") print "RUN_GEMINI=true;"
            if (section == "cursor") print "RUN_CURSOR=true;"
        }
        /^[[:space:]]*enabled:[[:space:]]*false/ {
            if (section == "claude") print "RUN_CLAUDE=false;"
            if (section == "gemini") print "RUN_GEMINI=false;"
            if (section == "cursor") print "RUN_CURSOR=false;"
        }
        /^[[:space:]]*minimum_agents:[[:space:]]*[0-9]+/ {
            if (match($0, /[0-9]+/)) {
                print "MIN_AGENTS=" substr($0, RSTART, RLENGTH) ";"
            }
        }
    ' "$SERVICES_CONFIG")

    if [[ -n "$config_settings" ]]; then
        eval "$config_settings"
    fi

    # Check minimum agents requirement
    local min_agents=${MIN_AGENTS:-2}

    local enabled_count=0
    [[ "$RUN_CLAUDE" == true ]] && enabled_count=$((enabled_count + 1))
    [[ "$RUN_GEMINI" == true ]] && enabled_count=$((enabled_count + 1))
    [[ "$RUN_CURSOR" == true ]] && enabled_count=$((enabled_count + 1))

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

# Validation results cache
CURSOR_VAL_RESULT=-1
GEMINI_VAL_RESULT=-1
CLAUDE_VAL_RESULT=-1

# Model selection defaults
CURSOR_MODEL_TIER="auto"
CURSOR_MODEL=""
CLAUDE_MODEL_TIER="sonnet"
CLAUDE_MODEL=""
GEMINI_MODEL_TIER="flash"
GEMINI_MODEL=""

# Credit exhaustion tracking
CURSOR_CREDIT_FALLBACK=false
CLAUDE_CREDIT_FALLBACK=false
CHECK_CREDITS_PREFLIGHT="${CHECK_CREDITS_PREFLIGHT:-false}"

# Model tier mappings (configurable via environment)
# Updated Jan 2026: GPT-5.x series now available in Cursor
CURSOR_MODEL_MINI="${CURSOR_MODEL_MINI:-gpt-5.1-codex-mini}"
CURSOR_MODEL_FLASH="${CURSOR_MODEL_FLASH:-gpt-5.1-codex}"
CURSOR_MODEL_ADVANCED="${CURSOR_MODEL_ADVANCED:-gpt-5.2}"

# Gemini model tier mappings (Gemini 3 series now available)
GEMINI_MODEL_FLASH="${GEMINI_MODEL_FLASH:-gemini-3-flash-preview}"
GEMINI_MODEL_PRO="${GEMINI_MODEL_PRO:-gemini-3-pro-preview}"

# Configurable directories for Gemini (colon-separated, like PATH)
GEMINI_INCLUDE_DIRS="${GEMINI_INCLUDE_DIRS:-$(pwd):$HOME/.claude}"

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
            shift
            ;;
        --gemini-only)
            RUN_CURSOR=false
            RUN_GEMINI=true
            RUN_CLAUDE=false
            shift
            ;;
        --claude-only)
            RUN_CURSOR=false
            RUN_GEMINI=false
            RUN_CLAUDE=true
            shift
            ;;
        --no-claude)
            RUN_CLAUDE=false
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
        --output)
            OUTPUT_DIR="$2"
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

    if [[ $available -eq 0 ]]; then
        echo -e "${RED}Error: No agents available${NC}"
        echo ""
        echo -e "${YELLOW}Possible fixes:${NC}"
        echo -e "  1. Enable services: ${BOLD}./bootstrap.sh --reconfigure --enable-claude --enable-gemini${NC}"
        echo -e "  2. Check config:    ${BOLD}cat ~/.claude/config/services.yml${NC}"
        echo -e "  3. Install CLIs:    ${BOLD}npm install -g @anthropic-ai/claude-code @google/gemini-cli${NC}"
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
            ;;
        review)
            if [[ ! -f "$TARGET" ]]; then
                echo -e "${RED}Error: File not found: $TARGET${NC}"
                exit 1
            fi
            CURSOR_PROMPT="Perform a detailed code review of $TARGET. Check for: bugs, security issues, performance problems, and code style."
            GEMINI_PROMPT="Code review $TARGET. Identify: potential bugs, security vulnerabilities, performance issues, and maintainability concerns."
            CLAUDE_PROMPT="Perform a comprehensive code review of $TARGET. Focus on security, correctness, performance, and maintainability. Provide actionable feedback."
            ;;
        improve)
            if [[ ! -f "$TARGET" ]]; then
                echo -e "${RED}Error: File not found: $TARGET${NC}"
                exit 1
            fi
            CURSOR_PROMPT="Review this observation YAML and suggest improvements for detection coverage and false positive reduction: $TARGET"
            GEMINI_PROMPT="Analyze this security observation YAML. Suggest improvements for: detection logic, entity mappings, and MITRE coverage. File: $TARGET"
            CLAUDE_PROMPT="Review this security observation YAML and suggest improvements for detection accuracy, coverage, and false positive reduction: $TARGET"
            ;;
        prompt | *)
            CURSOR_PROMPT="$PROMPT"
            GEMINI_PROMPT="$PROMPT"
            CLAUDE_PROMPT="$PROMPT"
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
    local output_file="$OUTPUT_DIR/cursor_${TIMESTAMP}.txt"
    local stderr_file="$OUTPUT_DIR/cursor_${TIMESTAMP}_stderr.txt"
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
    if ! run_with_retry_capture_stderr "Cursor Agent" "$output_file" "$stderr_file" \
        cursor agent --print --workspace "$PROJECT_ROOT" "${model_args[@]}" -- "$prompt"; then

        # Check for credit exhaustion
        if check_credit_exhaustion "$stderr_file" "Cursor"; then
            echo -e "${YELLOW}[Cursor Agent]${NC} Credit exhaustion detected, retrying with auto mode..."
            CURSOR_CREDIT_FALLBACK=true
            CURSOR_MODEL=""

            # Retry without model specification
            run_with_retry "Cursor Agent (fallback)" "$output_file" \
                cursor agent --print --workspace "$PROJECT_ROOT" -- "$prompt"
        fi
    fi
}

# Run Gemini CLI with model selection
run_gemini() {
    local prompt="$1"
    local output_file="$OUTPUT_DIR/gemini_${TIMESTAMP}.txt"
    local include_args=()

    # Build include-directories arguments from colon-separated list
    IFS=':' read -ra dirs <<< "$GEMINI_INCLUDE_DIRS"
    for dir in "${dirs[@]}"; do
        if [[ -d "$dir" ]]; then
            include_args+=("--include-directories" "$dir")
        fi
    done

    # Write prompt to temp file for reliable handling of special characters
    local prompt_file="$OUTPUT_DIR/gemini_prompt_${TIMESTAMP}.txt"
    printf '%s' "$prompt" > "$prompt_file"

    echo -e "${BLUE}[Gemini CLI]${NC} Starting with model: $GEMINI_MODEL..."
    # Gemini CLI: use input redirection for reliable handling (saves cat process)
    run_with_retry "Gemini CLI" "$output_file" bash -c \
        'gemini --output-format text --model "$1" "${@:2}" < "$0"' \
        "$prompt_file" "$GEMINI_MODEL" "${include_args[@]}"
}

# Run Claude CLI with model selection
run_claude() {
    local prompt="$1"
    local output_file="$OUTPUT_DIR/claude_${TIMESTAMP}.txt"
    local stderr_file="$OUTPUT_DIR/claude_${TIMESTAMP}_stderr.txt"

    # Resolve model tier
    resolve_claude_model "$CLAUDE_MODEL_TIER"

    # Write prompt to temp file for reliable handling of special characters
    local prompt_file="$OUTPUT_DIR/claude_prompt_${TIMESTAMP}.txt"
    printf '%s' "$prompt" > "$prompt_file"

    echo -e "${BLUE}[Claude CLI]${NC} Starting with model: $CLAUDE_MODEL..."

    # Claude CLI: use input redirection (saves cat process)
    if ! run_with_retry_capture_stderr "Claude CLI" "$output_file" "$stderr_file" \
        bash -c 'claude --print --output-format text --model "$1" < "$0"' \
        "$prompt_file" "$CLAUDE_MODEL"; then

        # Check for credit exhaustion
        if check_credit_exhaustion "$stderr_file" "Claude"; then
            echo -e "${YELLOW}[Claude CLI]${NC} Credit exhaustion detected, retrying with haiku..."
            CLAUDE_CREDIT_FALLBACK=true
            CLAUDE_MODEL="haiku"

            # Retry with haiku (cheapest model)
            run_with_retry "Claude CLI (fallback)" "$output_file" \
                bash -c 'claude --print --output-format text --model haiku < "$0"' \
                "$prompt_file"
        fi
    fi
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
    local json_file="$OUTPUT_DIR/results_${TIMESTAMP}.json"
    local cursor_output=""
    local gemini_output=""
    local claude_output=""
    local cursor_status="missing"
    local gemini_status="missing"
    local claude_status="missing"
    local cursor_valid=false
    local gemini_valid=false
    local claude_valid=false

    # Process Cursor output
    if [[ -f "$OUTPUT_DIR/cursor_${TIMESTAMP}.txt" ]]; then
        cursor_output=$(get_output_content "$OUTPUT_DIR/cursor_${TIMESTAMP}.txt")
        cursor_status="complete"
        if [[ "$VALIDATE" == true && "$CURSOR_VAL_RESULT" -ne -1 ]]; then
            # Accept both passed (0) and warning (2) as valid
            [[ $CURSOR_VAL_RESULT -eq 0 || $CURSOR_VAL_RESULT -eq 2 ]] && cursor_valid=true
        fi
    fi

    # Process Gemini output
    if [[ -f "$OUTPUT_DIR/gemini_${TIMESTAMP}.txt" ]]; then
        gemini_output=$(get_output_content "$OUTPUT_DIR/gemini_${TIMESTAMP}.txt")
        gemini_status="complete"
        if [[ "$VALIDATE" == true && "$GEMINI_VAL_RESULT" -ne -1 ]]; then
            [[ $GEMINI_VAL_RESULT -eq 0 || $GEMINI_VAL_RESULT -eq 2 ]] && gemini_valid=true
        fi
    fi

    # Process Claude output
    if [[ -f "$OUTPUT_DIR/claude_${TIMESTAMP}.txt" ]]; then
        claude_output=$(get_output_content "$OUTPUT_DIR/claude_${TIMESTAMP}.txt")
        claude_status="complete"
        if [[ "$VALIDATE" == true && "$CLAUDE_VAL_RESULT" -ne -1 ]]; then
            [[ $CLAUDE_VAL_RESULT -eq 0 || $CLAUDE_VAL_RESULT -eq 2 ]] && claude_valid=true
        fi
    fi

    # Count available agents for JSON
    local agent_count=0
    [[ "$cursor_status" == "complete" ]] && agent_count=$((agent_count + 1))
    [[ "$gemini_status" == "complete" ]] && agent_count=$((agent_count + 1))
    [[ "$claude_status" == "complete" ]] && agent_count=$((agent_count + 1))

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
    }
  },
  "output_files": {
    "cursor": "$OUTPUT_DIR/cursor_${TIMESTAMP}.txt",
    "gemini": "$OUTPUT_DIR/gemini_${TIMESTAMP}.txt",
    "claude": "$OUTPUT_DIR/claude_${TIMESTAMP}.txt",
    "summary": "$OUTPUT_DIR/summary_${TIMESTAMP}.md"
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

# Cross-verification: Compare agent outputs for consensus (supports 2 or 3 agents)
cross_verify() {
    local cursor_file="$OUTPUT_DIR/cursor_${TIMESTAMP}.txt"
    local gemini_file="$OUTPUT_DIR/gemini_${TIMESTAMP}.txt"
    local claude_file="$OUTPUT_DIR/claude_${TIMESTAMP}.txt"

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
    local start_time
    start_time=$(date +%s)

    # Track states locally
    local agent_states=()
    for i in "${!pids[@]}"; do agent_states[i]="running"; done

    local loop_count=0
    while $running; do
        running=false
        local status_line=""
        loop_count=$((loop_count + 1))

        # Calculate elapsed time
        local current_time
        current_time=$(date +%s)
        local elapsed=$((current_time - start_time))
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
                    wait "$pid"
                    local code=$?
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
            printf "\r${BOLD}Waiting for agents (%s):${NC}%s\033[K" "$time_str" "$status_line"
            sleep 0.1
        fi
    done

    # Final state
    local current_time
    current_time=$(date +%s)
    local elapsed=$((current_time - start_time))
    local minutes=$((elapsed / 60))
    local seconds=$((elapsed % 60))
    local time_str
    time_str=$(printf "%02d:%02d" $minutes $seconds)

    printf "\r${BOLD}Agents completed (%s):${NC}%s\033[K\n" "$time_str" "$status_line"

    # Restore cursor
    if $has_tput; then
        tput cnorm 2> /dev/null || true
    fi
}

# Combine outputs into markdown summary
create_summary() {
    local summary_file="$OUTPUT_DIR/summary_${TIMESTAMP}.md"

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

    if [[ -f "$OUTPUT_DIR/cursor_${TIMESTAMP}.txt" ]]; then
        echo "## Cursor Agent Output" >> "$summary_file"
        [[ -n "$CURSOR_MODEL" ]] && echo "**Model:** $CURSOR_MODEL" >> "$summary_file"
        [[ "$CURSOR_CREDIT_FALLBACK" == true ]] && echo "**Note:** Used fallback mode due to credit exhaustion" >> "$summary_file"
        echo '```' >> "$summary_file"
        get_output_content "$OUTPUT_DIR/cursor_${TIMESTAMP}.txt" >> "$summary_file"
        echo '```' >> "$summary_file"
        echo "" >> "$summary_file"
    fi

    if [[ -f "$OUTPUT_DIR/gemini_${TIMESTAMP}.txt" ]]; then
        echo "## Gemini CLI Output" >> "$summary_file"
        echo '```' >> "$summary_file"
        get_output_content "$OUTPUT_DIR/gemini_${TIMESTAMP}.txt" >> "$summary_file"
        echo '```' >> "$summary_file"
        echo "" >> "$summary_file"
    fi

    if [[ -f "$OUTPUT_DIR/claude_${TIMESTAMP}.txt" ]]; then
        echo "## Claude CLI Output" >> "$summary_file"
        [[ -n "$CLAUDE_MODEL" ]] && echo "**Model:** $CLAUDE_MODEL" >> "$summary_file"
        [[ "$CLAUDE_CREDIT_FALLBACK" == true ]] && echo "**Note:** Used fallback mode due to credit exhaustion" >> "$summary_file"
        echo '```' >> "$summary_file"
        get_output_content "$OUTPUT_DIR/claude_${TIMESTAMP}.txt" >> "$summary_file"
        echo '```' >> "$summary_file"
        echo "" >> "$summary_file"
    fi

    echo -e "${GREEN}Summary:${NC} $summary_file"

    # Also create JSON if requested
    if [[ "$OUTPUT_FORMAT" == "json" ]]; then
        create_json_output
    fi
}

# Main execution
main() {
    if [[ -z "$PROMPT" && -z "$TARGET" ]]; then
        usage
        exit 1
    fi

    # Validate agents are available before proceeding
    if ! validate_agents; then
        exit 2
    fi

    build_prompts

    echo -e "${GREEN}=== Parallel Agent Orchestration ===${NC}"
    echo "Mode: $MODE"
    echo "Output: $OUTPUT_DIR"
    [[ "$RUN_CURSOR" == true ]] && echo "Cursor: enabled (model: ${CURSOR_MODEL_TIER})"
    [[ "$RUN_GEMINI" == true ]] && echo "Gemini: enabled (model: ${GEMINI_MODEL_TIER})"
    [[ "$RUN_CLAUDE" == true ]] && echo "Claude: enabled (model: ${CLAUDE_MODEL_TIER})"
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

    # Monitor agents
    echo ""
    monitor_agents

    echo ""

    # Verify output files were created
    echo -e "${BLUE}=== Output File Check ===${NC}"
    local files_created=0
    if [[ "$RUN_CURSOR" == true ]]; then
        if [[ -f "$OUTPUT_DIR/cursor_${TIMESTAMP}.txt" ]]; then
            local size
            size=$(stat -f%z "$OUTPUT_DIR/cursor_${TIMESTAMP}.txt" 2> /dev/null || stat -c%s "$OUTPUT_DIR/cursor_${TIMESTAMP}.txt" 2> /dev/null || echo "0")
            echo -e "${GREEN}[Cursor]${NC} Output file created (${size} bytes)"
            files_created=$((files_created + 1))
        else
            echo -e "${RED}[Cursor]${NC} Output file NOT created: $OUTPUT_DIR/cursor_${TIMESTAMP}.txt"
        fi
    fi
    if [[ "$RUN_GEMINI" == true ]]; then
        if [[ -f "$OUTPUT_DIR/gemini_${TIMESTAMP}.txt" ]]; then
            local size
            size=$(stat -f%z "$OUTPUT_DIR/gemini_${TIMESTAMP}.txt" 2> /dev/null || stat -c%s "$OUTPUT_DIR/gemini_${TIMESTAMP}.txt" 2> /dev/null || echo "0")
            echo -e "${GREEN}[Gemini]${NC} Output file created (${size} bytes)"
            files_created=$((files_created + 1))
        else
            echo -e "${RED}[Gemini]${NC} Output file NOT created: $OUTPUT_DIR/gemini_${TIMESTAMP}.txt"
        fi
    fi
    if [[ "$RUN_CLAUDE" == true ]]; then
        if [[ -f "$OUTPUT_DIR/claude_${TIMESTAMP}.txt" ]]; then
            local size
            size=$(stat -f%z "$OUTPUT_DIR/claude_${TIMESTAMP}.txt" 2> /dev/null || stat -c%s "$OUTPUT_DIR/claude_${TIMESTAMP}.txt" 2> /dev/null || echo "0")
            echo -e "${GREEN}[Claude]${NC} Output file created (${size} bytes)"
            files_created=$((files_created + 1))
        else
            echo -e "${RED}[Claude]${NC} Output file NOT created: $OUTPUT_DIR/claude_${TIMESTAMP}.txt"
        fi
    fi

    if [[ $files_created -eq 0 ]]; then
        echo -e "${RED}ERROR: No output files were created!${NC}"
        echo -e "${YELLOW}This may indicate a permissions issue or sandbox restriction.${NC}"
        echo -e "${YELLOW}Try running with: --output /tmp/agent_outputs${NC}"
        exit 13
    fi

    echo ""

    # Run cross-verification if multiple agents were enabled
    local enabled_count=0
    [[ "$RUN_CURSOR" == true ]] && enabled_count=$((enabled_count + 1))
    [[ "$RUN_GEMINI" == true ]] && enabled_count=$((enabled_count + 1))
    [[ "$RUN_CLAUDE" == true ]] && enabled_count=$((enabled_count + 1))

    if [[ $enabled_count -ge 2 ]]; then
        cross_verify
        echo ""
    fi

    # Run validation if enabled (once)
    if [[ "$VALIDATE" == true ]]; then
        echo -e "${BLUE}=== Validation Results ===${NC}"
        if [[ "$RUN_CURSOR" == true && -f "$OUTPUT_DIR/cursor_${TIMESTAMP}.txt" ]]; then
            validate_output "$OUTPUT_DIR/cursor_${TIMESTAMP}.txt" "Cursor Agent"
            CURSOR_VAL_RESULT=$?
        fi
        if [[ "$RUN_GEMINI" == true && -f "$OUTPUT_DIR/gemini_${TIMESTAMP}.txt" ]]; then
            validate_output "$OUTPUT_DIR/gemini_${TIMESTAMP}.txt" "Gemini CLI"
            GEMINI_VAL_RESULT=$?
        fi
        if [[ "$RUN_CLAUDE" == true && -f "$OUTPUT_DIR/claude_${TIMESTAMP}.txt" ]]; then
            validate_output "$OUTPUT_DIR/claude_${TIMESTAMP}.txt" "Claude CLI"
            CLAUDE_VAL_RESULT=$?
        fi
        echo ""
    fi

    # Calculate duration
    END_TIME=$(date +%s)
    DURATION_SECONDS=$((END_TIME - START_TIME))
    DURATION_FORMATTED=$(format_duration "$DURATION_SECONDS")

    create_summary

    echo ""
    echo -e "${GREEN}Done!${NC} ($DURATION_FORMATTED) Results in: $OUTPUT_DIR"
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then main "$@"; fi
