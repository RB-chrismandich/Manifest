#!/usr/bin/env bash
# browser_test.sh - Wrapper for browser-use E2E test execution
#
# Usage: browser_test.sh <subcommand> [options]
#
# Subcommands:
#   run <file>       Run a single YAML test file
#   run-all <dir>    Run all YAML tests in a directory
#   validate <path>  Validate YAML test files without executing
#   list <dir>       List all test files in a directory
#
# Exit codes:
#   0 - All tests passed
#   1 - One or more tests failed
#   2 - browser-use not installed (skip)
#   3 - No test files found (skip)
#   124 - Timeout

set -euo pipefail

# --- Colors -----------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
RESET='\033[0m'

# --- Defaults ---------------------------------------------------------
DEFAULT_TIMEOUT=60
DEFAULT_MAX_STEPS=15
DEFAULT_TEST_DIR="tests/browser"
SCREENSHOT_DIR="${TMPDIR:-/tmp}/browser_test_screenshots"

# --- Helper functions -------------------------------------------------

usage() {
    cat << 'USAGE'
browser_test.sh - Browser-use E2E test runner

USAGE:
  browser_test.sh <subcommand> [options]

SUBCOMMANDS:
  run <file>         Run a single YAML test file
  run-all [dir]      Run all YAML tests in a directory (default: tests/browser/)
  validate [path]    Validate YAML test files without executing
  list [dir]         List all test files in a directory

OPTIONS:
  --timeout <sec>    Timeout per test in seconds (default: 60)
  --headless         Run in headless mode (default: true)
  --no-headless      Run with visible browser
  --screenshots      Save screenshots (default: true)
  --no-screenshots   Disable screenshot capture

EXIT CODES:
  0   All tests passed
  1   One or more tests failed
  2   browser-use not installed (skip)
  3   No test files found (skip)
  124 Timeout exceeded

EXAMPLES:
  browser_test.sh run tests/browser/smoke-test.yaml
  browser_test.sh run-all tests/browser/ --timeout 120
  browser_test.sh validate tests/browser/
  browser_test.sh list
USAGE
}

error_msg() { echo -e "${RED}Error: $1${RESET}" >&2; }
success_msg() { echo -e "${GREEN}$1${RESET}"; }
warn_msg() { echo -e "${YELLOW}$1${RESET}"; }
info_msg() { echo -e "${CYAN}$1${RESET}"; }

# --- Environment checks ----------------------------------------------

check_browser_use() {
    if command -v browser-use &> /dev/null; then
        return 0
    fi

    # Check Python module as fallback
    if python3 -c "import browser_use" 2> /dev/null; then
        return 0
    fi

    error_msg "browser-use is not installed"
    echo "" >&2
    echo "Install with:" >&2
    echo "  pip install browser-use" >&2
    echo "  # or" >&2
    echo "  pipx install browser-use" >&2
    return 2
}

# --- YAML validation --------------------------------------------------

validate_yaml() {
    local file="$1"

    if [[ ! -f "$file" ]]; then
        error_msg "File not found: $file"
        return 1
    fi

    python3 - "$file" << 'PYTHON'
import sys
import yaml

filepath = sys.argv[1]

try:
    with open(filepath, "r") as f:
        data = yaml.safe_load(f)
except yaml.YAMLError as e:
    print(f"INVALID: {filepath} — YAML parse error: {e}", file=sys.stderr)
    sys.exit(1)

if not isinstance(data, dict):
    print(f"INVALID: {filepath} — Expected a YAML mapping, got {type(data).__name__}", file=sys.stderr)
    sys.exit(1)

errors = []
if "task" not in data or not data["task"]:
    errors.append("Missing required field: task")
if "judge_context" not in data:
    errors.append("Missing required field: judge_context")
elif not isinstance(data["judge_context"], list):
    errors.append("judge_context must be a list of strings")

max_steps = data.get("max_steps", 15)
if not isinstance(max_steps, int) or max_steps < 1 or max_steps > 25:
    errors.append(f"max_steps must be an integer between 1 and 25, got: {max_steps}")

if errors:
    for err in errors:
        print(f"INVALID: {filepath} — {err}", file=sys.stderr)
    sys.exit(1)

# Report valid
task_short = data["task"][:80]
criteria = len(data.get("judge_context", []))
steps = data.get("max_steps", 15)
tags = ", ".join(data.get("tags", []))
tag_str = f" [{tags}]" if tags else ""
print(f"VALID: {filepath} — \"{task_short}\" ({criteria} criteria, {steps} max steps){tag_str}")
PYTHON
}

# --- Test execution ---------------------------------------------------

run_single_test() {
    local file="$1"
    local timeout="${2:-$DEFAULT_TIMEOUT}"
    local headless="${3:-true}"

    # Validate first
    if ! validate_yaml "$file" > /dev/null 2>&1; then
        validate_yaml "$file"
        return 1
    fi

    mkdir -p "$SCREENSHOT_DIR"

    local test_name
    test_name=$(basename "$file" .yaml)
    test_name=$(basename "$test_name" .yml)

    info_msg "Running: $file (timeout: ${timeout}s)"

    # Extract task from YAML. Paths/values are passed via argv, never
    # interpolated into Python source (FR-009).
    local task
    task=$(python3 -c "
import yaml, sys
with open(sys.argv[1]) as f:
    d = yaml.safe_load(f)
print(d.get('task', ''))
" "$file")

    local max_steps
    max_steps=$(python3 -c "
import yaml, sys
with open(sys.argv[1]) as f:
    d = yaml.safe_load(f)
print(d.get('max_steps', int(sys.argv[2])))
" "$file" "$DEFAULT_MAX_STEPS")

    local start_time
    start_time=$(date +%s)

    local exit_code=0
    local output=""

    # Run browser-use with timeout
    if command -v browser-use &> /dev/null; then
        local headless_flag=""
        if [[ "$headless" == "true" ]]; then
            headless_flag="--headless"
        fi

        output=$(timeout "$timeout" browser-use run "$task" \
            --max-steps "$max_steps" \
            $headless_flag 2>&1) || exit_code=$?
    else
        # Fallback to Python API. Task text (YAML-sourced!) and settings are
        # passed via argv, never interpolated into Python source (FR-009).
        output=$(timeout "$timeout" python3 -c "
import asyncio, sys
from browser_use import Agent, Browser
from browser_use.llm import ChatBrowserUse

task, max_steps, headless = sys.argv[1], int(sys.argv[2]), sys.argv[3] == 'true'

async def main():
    browser = Browser(headless=headless)
    llm = ChatBrowserUse()
    agent = Agent(task=task, llm=llm, browser=browser, max_steps=max_steps)
    result = await agent.run()
    await browser.close()
    return result

asyncio.run(main())
" "$task" "$max_steps" "$headless" 2>&1) || exit_code=$?
    fi

    local end_time
    end_time=$(date +%s)
    local duration=$((end_time - start_time))

    # Report result
    if [[ $exit_code -eq 0 ]]; then
        success_msg "PASS: $test_name (${duration}s)"
    elif [[ $exit_code -eq 124 ]]; then
        error_msg "TIMEOUT: $test_name (exceeded ${timeout}s)"
    else
        error_msg "FAIL: $test_name (${duration}s, exit code: $exit_code)"
        if [[ -n "$output" ]]; then
            echo "  Output (last 10 lines):"
            echo "$output" | tail -10 | sed 's/^/    /'
        fi
    fi

    return $exit_code
}

# --- Subcommands ------------------------------------------------------

cmd_run() {
    local file=""
    local timeout="$DEFAULT_TIMEOUT"
    local headless="true"

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --timeout)
                timeout="$2"
                shift 2
                ;;
            --headless)
                headless="true"
                shift
                ;;
            --no-headless)
                headless="false"
                shift
                ;;
            -*)
                error_msg "Unknown option: $1"
                return 1
                ;;
            *)
                file="$1"
                shift
                ;;
        esac
    done

    if [[ -z "$file" ]]; then
        error_msg "Test file path required. Usage: browser_test.sh run <file>"
        return 1
    fi

    check_browser_use || return $?
    run_single_test "$file" "$timeout" "$headless"
}

cmd_run_all() {
    local dir="$DEFAULT_TEST_DIR"
    local timeout="$DEFAULT_TIMEOUT"
    local headless="true"

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --timeout)
                timeout="$2"
                shift 2
                ;;
            --headless)
                headless="true"
                shift
                ;;
            --no-headless)
                headless="false"
                shift
                ;;
            -*)
                error_msg "Unknown option: $1"
                return 1
                ;;
            *)
                dir="$1"
                shift
                ;;
        esac
    done

    check_browser_use || return $?

    local files=()
    while IFS= read -r f; do
        files+=("$f")
    done < <(find "$dir" -name "*.yaml" -o -name "*.yml" 2> /dev/null | sort)

    if [[ ${#files[@]} -eq 0 ]]; then
        warn_msg "No test files found in $dir"
        return 3
    fi

    info_msg "Found ${#files[@]} test file(s) in $dir"
    echo ""

    local passed=0 failed=0 skipped=0 total=${#files[@]}

    for file in ${files[@]+"${files[@]}"}; do
        if run_single_test "$file" "$timeout" "$headless"; then
            passed=$((passed + 1))
        else
            local rc=$?
            if [[ $rc -eq 2 || $rc -eq 3 ]]; then
                skipped=$((skipped + 1))
            else
                failed=$((failed + 1))
            fi
        fi
        echo ""
    done

    echo "---"
    info_msg "Results: ${passed} passed, ${failed} failed, ${skipped} skipped (${total} total)"

    if [[ $failed -gt 0 ]]; then
        return 1
    fi
    return 0
}

cmd_validate() {
    local path="${1:-$DEFAULT_TEST_DIR}"

    local files=()
    if [[ -f "$path" ]]; then
        files=("$path")
    elif [[ -d "$path" ]]; then
        while IFS= read -r f; do
            files+=("$f")
        done < <(find "$path" -name "*.yaml" -o -name "*.yml" 2> /dev/null | sort)
    else
        error_msg "Path not found: $path"
        return 1
    fi

    if [[ ${#files[@]} -eq 0 ]]; then
        warn_msg "No test files found in $path"
        return 3
    fi

    local valid=0 invalid=0

    for file in ${files[@]+"${files[@]}"}; do
        if validate_yaml "$file"; then
            valid=$((valid + 1))
        else
            invalid=$((invalid + 1))
        fi
    done

    echo ""
    info_msg "Validation: ${valid} valid, ${invalid} invalid (${#files[@]} total)"

    if [[ $invalid -gt 0 ]]; then
        return 1
    fi
    return 0
}

cmd_list() {
    local dir="${1:-$DEFAULT_TEST_DIR}"

    if [[ ! -d "$dir" ]]; then
        warn_msg "Test directory not found: $dir"
        echo ""
        echo "Create it with:"
        echo "  mkdir -p $dir"
        echo "  cp ~/.claude/skills/browser-test/templates/smoke-test.yaml $dir/"
        return 3
    fi

    local files=()
    while IFS= read -r f; do
        files+=("$f")
    done < <(find "$dir" -name "*.yaml" -o -name "*.yml" 2> /dev/null | sort)

    if [[ ${#files[@]} -eq 0 ]]; then
        warn_msg "No test files in $dir"
        return 3
    fi

    info_msg "Browser test files in $dir:"
    echo ""
    for file in ${files[@]+"${files[@]}"}; do
        validate_yaml "$file" 2> /dev/null || validate_yaml "$file" 2>&1 | head -1
    done
}

# --- Main dispatch ----------------------------------------------------

main() {
    if [[ $# -lt 1 ]]; then
        usage
        exit 1
    fi

    local subcommand="$1"
    shift

    case "$subcommand" in
        run) cmd_run "$@" ;;
        run-all) cmd_run_all "$@" ;;
        validate) cmd_validate "$@" ;;
        list) cmd_list "$@" ;;
        help | --help | -h)
            usage
            exit 0
            ;;
        *)
            error_msg "Unknown subcommand: ${subcommand}"
            echo "" >&2
            usage
            exit 1
            ;;
    esac
}

main "$@"
