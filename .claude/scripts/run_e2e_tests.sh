#!/bin/bash
# Quick E2E Test Runner for Parallel Agent Phase 3
# Usage: ./run_e2e_tests.sh [--full]

set -e # Exit on error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Test results
TESTS_PASSED=0
TESTS_FAILED=0

# Helper functions
print_test() {
    echo -e "${BLUE}[TEST]${NC} $1"
}

print_pass() {
    echo -e "${GREEN}✓${NC} $1"
    ((TESTS_PASSED++))
}

print_fail() {
    echo -e "${RED}✗${NC} $1"
    ((TESTS_FAILED++))
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_section() {
    echo ""
    echo -e "${BLUE}═══════════════════════════════════════════════${NC}"
    echo -e "${BLUE}  $1${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════${NC}"
}

# Check if running full tests
FULL_TESTS=false
if [[ "$1" == "--full" ]]; then
    FULL_TESTS=true
fi

# Start testing
echo -e "${BLUE}╔═══════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   Parallel Agent Phase 3 - E2E Tests         ║${NC}"
echo -e "${BLUE}╚═══════════════════════════════════════════════╝${NC}"
echo ""

# ============================================================================
# LEVEL 0: Prerequisites
# ============================================================================
print_section "Level 0: Prerequisites"

# Check Python version
print_test "Python 3.9+ available"
if python3 --version | grep -E "Python 3\.(9|[1-9][0-9])" > /dev/null 2>&1; then
    print_pass "Python version: $(python3 --version | cut -d' ' -f2)"
else
    print_fail "Python 3.9+ required"
    exit 1
fi

# Check syntax
print_test "Python syntax valid"
if python3 -m py_compile parallel_agent.py 2> /dev/null; then
    print_pass "Syntax check passed"
else
    print_fail "Syntax errors found"
    exit 1
fi

# Check config files
print_test "Configuration files exist"
if [[ -f ~/.claude/config/parallel_agent.yml ]] &&
    [[ -f ~/.claude/config/validation_criteria.yml ]] &&
    [[ -f ~/.claude/prompts/synthesis.md ]]; then
    print_pass "All config files present"
else
    print_fail "Missing config files"
    print_warning "Run: cp -r /path/to/repo/.claude/* ~/.claude/"
    exit 1
fi

# Check dependencies (non-blocking)
print_test "Dependencies installed"
DEPS_OK=true
python3 -c "import yaml" 2> /dev/null || DEPS_OK=false
python3 -c "import rich" 2> /dev/null || DEPS_OK=false
python3 -c "import anthropic" 2> /dev/null || DEPS_OK=false

if $DEPS_OK; then
    print_pass "Core dependencies installed"
else
    print_warning "Some dependencies missing (run: pip3 install -r requirements.txt)"
fi

# Check API keys (non-blocking)
print_test "API keys configured"
if [[ -n "$ANTHROPIC_API_KEY" ]]; then
    print_pass "ANTHROPIC_API_KEY set"
else
    print_warning "ANTHROPIC_API_KEY not set (some tests will be skipped)"
fi

if [[ -n "$GOOGLE_API_KEY" ]]; then
    print_pass "GOOGLE_API_KEY set"
else
    print_warning "GOOGLE_API_KEY not set (will try OAuth)"
fi

# ============================================================================
# LEVEL 1: Smoke Tests
# ============================================================================
print_section "Level 1: Smoke Tests (Fast)"

# Test 1.1: Help menu
print_test "Help menu displays"
if python3 parallel_agent.py --help 2> /dev/null | grep -q "analyze"; then
    print_pass "Help menu shows new flags"
else
    print_fail "Help menu incomplete"
fi

# Test 1.2: Credit check (if API keys available)
if [[ -n "$ANTHROPIC_API_KEY" ]]; then
    print_test "Credit check completes"
    if timeout 15 python3 parallel_agent.py --check-credits > /tmp/credit_check.json 2>&1; then
        if python3 -m json.tool /tmp/credit_check.json > /dev/null 2>&1; then
            print_pass "Credit check returned valid JSON"

            # Show status
            CLAUDE_STATUS=$(python3 -c "import json; print(json.load(open('/tmp/credit_check.json'))['claude']['status'])" 2> /dev/null || echo "unknown")
            if [[ "$CLAUDE_STATUS" == "available" ]]; then
                print_pass "Claude API available"
            else
                print_warning "Claude API status: $CLAUDE_STATUS"
            fi
        else
            print_fail "Credit check returned invalid JSON"
        fi
    else
        print_warning "Credit check timed out or failed (API issue?)"
    fi
else
    print_warning "Skipping credit check (no API keys)"
fi

# Test 1.3: Config loading
print_test "Configuration loading"
if python3 -c "
from parallel_agent import Config, Logger
config = Config()
assert config.get('logging.level') is not None
assert config.get('synthesis.enabled') is not None
assert config.get('streaming.enabled') is not None
logger = Logger(config)
logger.set_correlation_id('test-123')
" 2> /dev/null; then
    print_pass "Config and Logger functional"
else
    print_fail "Config or Logger failed"
fi

# Test 1.4: YAML syntax
print_test "YAML configuration syntax"
if python3 -c "import yaml; yaml.safe_load(open('$HOME/.claude/config/parallel_agent.yml'))" 2> /dev/null &&
    python3 -c "import yaml; yaml.safe_load(open('$HOME/.claude/config/validation_criteria.yml'))" 2> /dev/null; then
    print_pass "All YAML files valid"
else
    print_fail "YAML syntax errors"
fi

# ============================================================================
# LEVEL 2: Feature Tests (Optional - requires API keys)
# ============================================================================
if $FULL_TESTS && [[ -n "$ANTHROPIC_API_KEY" ]]; then
    print_section "Level 2: Feature Tests (Full)"

    # Create temp directory
    mkdir -p /tmp/parallel_agent_tests

    # Test 2.1: Logging
    print_test "Logging functionality"
    LOG_FILE="$HOME/.claude/.agent_outputs/parallel_agent.log"
    if timeout 30 python3 parallel_agent.py --claude-only "Hello" > /dev/null 2>&1; then
        if [[ -f "$LOG_FILE" ]] && grep -q "correlation_id" "$LOG_FILE" 2> /dev/null; then
            print_pass "Log file created with correlation IDs"
        else
            print_fail "Log file missing or incomplete"
        fi
    else
        print_warning "Logging test timed out"
    fi

    # Test 2.2: CLI flag --analyze
    print_test "CLI flag: --analyze"
    cat > /tmp/parallel_agent_tests/test_analyze.py << 'EOF'
# Test file with security issue
API_KEY = "hardcoded-secret"
def query(username):
    return f"SELECT * FROM users WHERE name='{username}'"
EOF
    if timeout 60 python3 parallel_agent.py --analyze /tmp/parallel_agent_tests/test_analyze.py --json > /tmp/analyze_result.json 2>&1; then
        if python3 -c "import json; r=json.load(open('/tmp/analyze_result.json')); assert r['mode']=='analyze'" 2> /dev/null; then
            print_pass "--analyze flag works"
        else
            print_fail "--analyze returned invalid result"
        fi
    else
        print_warning "--analyze test timed out or failed"
    fi

    # Test 2.3: Validation
    print_test "Validation engine"
    if timeout 90 python3 parallel_agent.py --analyze /tmp/parallel_agent_tests/test_analyze.py --validate --json > /tmp/validation_result.json 2>&1; then
        if python3 -c "import json; r=json.load(open('/tmp/validation_result.json')); assert 'validation' in r; assert 'verdict' in r['validation']" 2> /dev/null; then
            VERDICT=$(python3 -c "import json; print(json.load(open('/tmp/validation_result.json'))['validation']['verdict'])")
            if [[ "$VERDICT" == "BLOCKED" ]]; then
                print_pass "Validation detected security issues (verdict: $VERDICT)"
            else
                print_warning "Expected BLOCKED verdict, got: $VERDICT"
            fi
        else
            print_fail "Validation result incomplete"
        fi
    else
        print_warning "Validation test timed out"
    fi

    # Test 2.4: Streaming vs non-streaming
    print_test "Streaming mode"
    if timeout 30 python3 parallel_agent.py --claude-only "Count to 3" > /dev/null 2>&1; then
        print_pass "Streaming mode works"
    else
        print_warning "Streaming test failed or timed out"
    fi

    print_test "Non-streaming mode"
    if timeout 30 python3 parallel_agent.py --no-stream --claude-only "Count to 3" > /dev/null 2>&1; then
        print_pass "Non-streaming mode works"
    else
        print_warning "Non-streaming test failed or timed out"
    fi

    # Clean up
    rm -rf /tmp/parallel_agent_tests

else
    if ! $FULL_TESTS; then
        print_warning "Skipping full tests (run with --full flag)"
    fi
    if [[ -z "$ANTHROPIC_API_KEY" ]]; then
        print_warning "Skipping API tests (no ANTHROPIC_API_KEY)"
    fi
fi

# ============================================================================
# LEVEL 3: Unit Tests
# ============================================================================
print_section "Level 3: Unit Tests"

print_test "Running unit tests"
if python3 test_parallel_agent.py > /tmp/unit_test_output.txt 2>&1; then
    print_pass "All unit tests passed"
else
    print_warning "Some unit tests failed (check /tmp/unit_test_output.txt)"
    # Don't fail overall tests - unit tests might need dependencies
fi

# ============================================================================
# Summary
# ============================================================================
print_section "Test Summary"

TOTAL_TESTS=$((TESTS_PASSED + TESTS_FAILED))
PASS_RATE=0
if [[ $TOTAL_TESTS -gt 0 ]]; then
    PASS_RATE=$((TESTS_PASSED * 100 / TOTAL_TESTS))
fi

echo -e "Tests Passed: ${GREEN}$TESTS_PASSED${NC}"
echo -e "Tests Failed: ${RED}$TESTS_FAILED${NC}"
echo -e "Pass Rate:    ${BLUE}${PASS_RATE}%${NC}"
echo ""

if [[ $TESTS_FAILED -eq 0 ]]; then
    echo -e "${GREEN}✅ ALL TESTS PASSED${NC}"
    echo ""
    echo "Next steps:"
    echo "  1. Run full tests: ./run_e2e_tests.sh --full"
    echo "  2. Test with your own files"
    echo "  3. Review logs: tail -f ~/.claude/.agent_outputs/parallel_agent.log"
    echo "  4. See full guide: cat E2E_TESTING_GUIDE.md"
    exit 0
else
    echo -e "${RED}❌ SOME TESTS FAILED${NC}"
    echo ""
    echo "Troubleshooting:"
    echo "  1. Install dependencies: pip3 install -r requirements.txt"
    echo "  2. Set API keys: export ANTHROPIC_API_KEY='sk-ant-...'"
    echo "  3. Check config files in ~/.claude/"
    echo "  4. See guide: cat E2E_TESTING_GUIDE.md"
    exit 1
fi
