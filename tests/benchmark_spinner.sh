#!/bin/bash
# Benchmark run_with_spinner overhead and verify cleanup

# Source common.sh relative to script location
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BOOTSTRAP_LIB_DIR="$SCRIPT_DIR/../bootstrap/lib"

if [[ ! -f "$BOOTSTRAP_LIB_DIR/common.sh" ]]; then
    echo "Error: common.sh not found at $BOOTSTRAP_LIB_DIR/common.sh"
    exit 1
fi

source "$BOOTSTRAP_LIB_DIR/common.sh"

echo "Benchmarking run_with_spinner..."

# Measure duration of a 2-second sleep wrapped in spinner
echo "Running spinner for 2 seconds..."
time run_with_spinner "sleep 2" "Waiting for sleep"

# Verify functionality
if run_with_spinner "true" "Quick task"; then
    echo "Quick task passed"
else
    echo "Quick task failed"
fi

if ! run_with_spinner "false" "Failing task"; then
    echo "Failing task failed correctly"
else
    echo "Failing task passed unexpectedly"
fi

# Verify cleanup (requires access to internal variables which is tricky from outside)
# But we can check if _SLEEP_PROC_PID is set and process exists
if [[ -n "$_SLEEP_PROC_PID" ]]; then
    if kill -0 "$_SLEEP_PROC_PID" 2>/dev/null; then
        echo "Sleep process $_SLEEP_PROC_PID is running (expected during execution)"
    else
        echo "Sleep process $_SLEEP_PROC_PID is NOT running (unexpected)"
    fi
else
    echo "Sleep process PID not set (maybe Bash < 4?)"
fi

echo "Exiting script. Trap should fire."
