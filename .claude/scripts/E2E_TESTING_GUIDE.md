# End-to-End Testing Guide for Parallel Agent (Phase 3)

**Purpose**: Comprehensive testing strategy to verify all Phase 3 features work correctly

**Prerequisites**: API keys, dependencies installed, configuration files present

---

## 📋 Pre-Testing Checklist

### 1. Environment Setup

```bash
# Navigate to scripts directory
cd /Users/charlemagne/.claude/scripts

# Check Python version (3.9+ required)
python3 --version

# Verify configuration files exist
ls -la ~/.claude/config/parallel_agent.yml
ls -la ~/.claude/config/validation_criteria.yml
ls -la ~/.claude/prompts/synthesis.md

# Check API keys (don't print actual keys)
echo "Claude API key set: $([ -n "$ANTHROPIC_API_KEY" ] && echo 'YES' || echo 'NO')"
echo "Gemini API key set: $([ -n "$GOOGLE_API_KEY" ] && echo 'YES' || echo 'NO (using OAuth)')"
```

### 2. Install Dependencies

```bash
# Install all dependencies
pip3 install -r requirements.txt

# Verify critical packages
python3 -c "import anthropic; print('✓ anthropic:', anthropic.__version__)"
python3 -c "from google import genai; print('✓ google-generativeai installed')" 2>/dev/null || echo "⚠ google-generativeai not installed"
python3 -c "import yaml; print('✓ yaml:', yaml.__version__)"
python3 -c "import rich; print('✓ rich:', rich.__version__)"
```

### 3. Syntax Validation

```bash
# Check Python syntax
python3 -m py_compile parallel_agent.py && echo "✓ Syntax valid"

# Check YAML syntax
python3 -c "import yaml; yaml.safe_load(open('/Users/charlemagne/.claude/config/parallel_agent.yml'))" && echo "✓ Config YAML valid"
python3 -c "import yaml; yaml.safe_load(open('/Users/charlemagne/.claude/config/validation_criteria.yml'))" && echo "✓ Validation YAML valid"
```

---

## 🧪 Test Suite

### Level 1: Smoke Tests (5-10 minutes)

**Goal**: Verify basic functionality without expensive API calls

#### Test 1.1: Help Menu

```bash
python3 parallel_agent.py --help
```

**Expected**: Usage instructions with all flags displayed

**Verify**:

- ✓ New flags present: `--analyze`, `--improve`, `--check-credits`, `--output`, `--full-output`, `--no-stream`, `--synthesize`, `--no-claude`

---

#### Test 1.2: Credit Check (No Expensive Calls)

```bash
python3 parallel_agent.py --check-credits
```

**Expected**: JSON output with status for each agent

**Success Output**:

```json
{
  "claude": {"status": "available"},
  "gemini": {"status": "available"},
  "cursor": {"status": "assumed_available"}
}
```

**Possible Outputs**:

- `available` - API key valid, quota available
- `quota_exceeded` - Rate limit or quota exhausted
- `no_api_key` - API key not set
- `not_installed` - SDK not installed
- `error` - Other error

**Verify**:

- ✓ All agents checked
- ✓ JSON format valid
- ✓ No crashes

---

#### Test 1.3: Configuration Loading

```bash
# Test config is loaded correctly
python3 -c "
from parallel_agent import Config, Logger
config = Config()
print('✓ Config loaded')
print('✓ Logging config:', config.get('logging.level'))
print('✓ Synthesis config:', config.get('synthesis.enabled'))
print('✓ Streaming config:', config.get('streaming.enabled'))
logger = Logger(config)
print('✓ Logger created')
logger.set_correlation_id('test-123')
logger.info('Test log entry')
print('✓ Logger functional')
"
```

**Expected**:

```
✓ Config loaded
✓ Logging config: INFO
✓ Synthesis config: True
✓ Streaming config: True
✓ Logger created
✓ Logger functional
```

**Verify**:

- ✓ Config loads without errors
- ✓ Logger creates log file
- ✓ Check log file: `tail ~/.claude/.agent_outputs/parallel_agent.log`

---

### Level 2: Feature Tests (15-20 minutes)

**Goal**: Test each Phase 3 feature individually

#### Test 2.1: Logging

```bash
# Run with logging enabled (default)
python3 parallel_agent.py --claude-only --timeout 30 "Say hello" --json > /tmp/test_output.json

# Check log file was created and has entries
tail -5 ~/.claude/.agent_outputs/parallel_agent.log
```

**Expected**:

```json
{"timestamp": "2026-02-10 14:30:22", "level": "INFO", "correlation_id": "20260210_143022_12345", "message": "Starting orchestration: mode=prompt, agents=1"}
{"timestamp": "2026-02-10 14:30:22", "level": "INFO", "correlation_id": "20260210_143022_12345", "message": "[claude] Starting execution with model claude-sonnet-4-5-20250929"}
{"timestamp": "2026-02-10 14:30:25", "level": "INFO", "correlation_id": "20260210_143022_12345", "message": "[claude] Completed in 3.21s"}
{"timestamp": "2026-02-10 14:30:25", "level": "INFO", "correlation_id": "20260210_143022_12345", "message": "Consensus score: 0%"}
{"timestamp": "2026-02-10 14:30:25", "level": "INFO", "correlation_id": "20260210_143022_12345", "message": "Total duration: 3.45s"}
```

**Verify**:

- ✓ Log file exists at `~/.claude/.agent_outputs/parallel_agent.log`
- ✓ Correlation IDs present (format: `YYYYMMDD_HHMMSS_PID`)
- ✓ Timestamps present
- ✓ Agent names in log messages
- ✓ Performance metrics logged (duration, consensus)

---

#### Test 2.2: CLI Flag Parity

**Test --analyze flag**:

```bash
# Create a test file with a security issue
cat > /tmp/test_security.py << 'EOF'
# Test file with security issue
API_KEY = "hardcoded-secret-123"

def login(username, password):
    query = f"SELECT * FROM users WHERE username='{username}'"
    # SQL injection vulnerability
    return query
EOF

# Analyze it
python3 parallel_agent.py --analyze /tmp/test_security.py --json --timeout 60 > /tmp/analyze_result.json

# Check result
cat /tmp/analyze_result.json | python3 -m json.tool | head -30
```

**Expected**:

- ✓ Mode: "analyze"
- ✓ Timeout: 900s (auto-adjusted from 60s default)
- ✓ Agents run analysis
- ✓ Potential security issues flagged

**Test --improve flag**:

```bash
# Create a test YAML observation file
cat > /tmp/test_observation.yml << 'EOF'
observation:
  title: "Test Observation"
  description: "This needs improvement"
  notes: "some notes here"
EOF

# Improve it
python3 parallel_agent.py --improve /tmp/test_observation.yml --json --timeout 60 > /tmp/improve_result.json

# Check result
cat /tmp/improve_result.json | python3 -m json.tool | grep -A5 '"mode"'
```

**Expected**:

- ✓ Mode: "improve"
- ✓ Timeout: 300s (auto-adjusted)
- ✓ Agents provide suggestions

**Test --output flag**:

```bash
# Custom output directory
mkdir -p /tmp/custom_agent_output

python3 parallel_agent.py --claude-only --output /tmp/custom_agent_output "Test output" --timeout 30

# Verify files created in custom directory
ls -la /tmp/custom_agent_output/
```

**Expected**:

- ✓ Files created in `/tmp/custom_agent_output/`
- ✓ Format: `claude_YYYYMMDD_HHMMSS.txt`, `results_*.json`, `summary_*.md`

**Test --no-stream flag**:

```bash
# Disable streaming
python3 parallel_agent.py --no-stream --claude-only "Test no streaming" --timeout 30
```

**Expected**:

- ✓ No live Rich display
- ✓ Spinner/progress indicator instead
- ✓ Same final output

**Test --no-claude flag**:

```bash
# Run without Claude agent
python3 parallel_agent.py --no-claude "Test without Claude" --timeout 30 --json
```

**Expected**:

- ✓ Only Gemini and Cursor agents run
- ✓ No Claude in results

---

#### Test 2.3: Validation (Tier 1 + Tier 2)

```bash
# Create a file with multiple issues
cat > /tmp/test_validation.py << 'EOF'
import os

# Hardcoded secret (Tier 1: Security)
API_KEY = "sk-secret-key-123"

# SQL injection (Tier 1: Security)
def get_user(username):
    query = f"SELECT * FROM users WHERE name='{username}'"
    return query

# Silent failure (Tier 1: Error Handling)
def risky_operation():
    try:
        dangerous_call()
    except:
        pass  # Silent failure

# O(n²) complexity (Tier 2: Performance)
def find_duplicates(arr):
    for i in arr:
        for j in arr:
            if i == j:
                print("duplicate")

# No tests (Tier 2: Test Coverage)
# Missing test file
EOF

# Analyze with validation
python3 parallel_agent.py --analyze /tmp/test_validation.py --validate --json --timeout 120 > /tmp/validation_result.json

# Check validation results
cat /tmp/validation_result.json | python3 -m json.tool | grep -A20 '"validation"'
```

**Expected Output Structure**:

```json
{
  "validation": {
    "tier1": {
      "passed": false,
      "score": 0.4,
      "checks": {
        "cross_verification": {"passed": true, "score": 0.85},
        "security": {"passed": false, "issues": ["[claude] Potential hardcoded secret detected"]},
        "error_handling": {"passed": false, "issues": ["[claude] Potential silent failure detected"]},
        "breaking_changes": {"passed": true}
      },
      "failures": [
        "[claude] Potential hardcoded secret detected",
        "[claude] Potential silent failure detected"
      ]
    },
    "tier2": {
      "score": 0.55,
      "checks": {
        "bug_detection": {"score": 1.0, "concerns": []},
        "performance": {"score": 0.75, "concerns": ["[claude] Quadratic or worse complexity detected"]},
        "maintainability": {"score": 0.8, "concerns": []},
        "test_coverage": {"score": 0.7, "concerns": ["[claude] Missing test coverage noted"]}
      },
      "concerns": [...]
    },
    "verdict": "BLOCKED",
    "command_overrides_applied": false
  }
}
```

**Verify**:

- ✓ Tier 1 checks run (cross_verification, security, error_handling, breaking_changes)
- ✓ Tier 2 checks run (bug_detection, performance, maintainability, test_coverage)
- ✓ Verdict is one of: APPROVED, NEEDS_REVIEW, BLOCKED
- ✓ BLOCKED if Tier 1 failed (hardcoded secret + silent failure)
- ✓ Tier 2 score between 0.0 and 1.0
- ✓ Issues and concerns listed

**Test Verdict Thresholds**:

```bash
# Create a clean file (should get APPROVED)
cat > /tmp/test_clean.py << 'EOF'
import os

def get_user_safely(user_id):
    """Safely get user by ID using parameterized query"""
    # Using proper parameterization (no SQL injection)
    query = "SELECT * FROM users WHERE id = ?"
    return execute_query(query, (user_id,))

def safe_operation():
    """Operation with proper error handling"""
    try:
        result = risky_call()
        return result
    except ValueError as e:
        logging.error(f"Operation failed: {e}")
        raise

# Tests exist for this module
# See: test_clean.py
EOF

python3 parallel_agent.py --analyze /tmp/test_clean.py --validate --json --timeout 120 > /tmp/clean_result.json

# Check verdict
cat /tmp/clean_result.json | python3 -m json.tool | grep '"verdict"'
```

**Expected**:

- ✓ Verdict: "APPROVED" (Tier 1 passed, Tier 2 >= 0.60)
- ✓ Or "NEEDS_REVIEW" (Tier 1 passed, Tier 2 < 0.60)

---

#### Test 2.4: Synthesis Agent

**Goal**: Test synthesis triggers when consensus < 50%

```bash
# Use a prompt that's likely to generate disagreement
python3 parallel_agent.py \
  --json \
  --timeout 120 \
  "Should we use microservices or monolith architecture for a new startup? Provide a strong opinion." \
  > /tmp/synthesis_result.json

# Check if synthesis was triggered
cat /tmp/synthesis_result.json | python3 -m json.tool | grep -A30 '"synthesis"'
```

**Expected (if consensus < 50%)**:

```json
{
  "cross_verification": {
    "consensus_score": 35,
    "confidence": "low",
    "agent_count": 3,
    "synthesis": {
      "triggered": true,
      "consensus_score": 0.35,
      "disagreements": [
        {
          "topic": "Architecture choice",
          "gemini_position": "Use microservices",
          "cursor_position": "Use monolith",
          "claude_position": "Use monolith",
          "resolution": "Start with monolith, prepare for microservices",
          "preferred_agent": "neither",
          "rationale": "Context-dependent"
        }
      ],
      "agreements": ["Both agree scalability is important"],
      "unified_recommendation": "Start with a well-structured monolith...",
      "caveats": ["Depends on team size", "Depends on deployment frequency"],
      "confidence": 0.75
    }
  }
}
```

**Verify**:

- ✓ `triggered: true` when consensus < 50%
- ✓ `disagreements` array populated
- ✓ `unified_recommendation` present
- ✓ `confidence` score between 0.0 and 1.0
- ✓ Synthesis uses Claude Sonnet (check model in result)

**Test Synthesis Skip (High Consensus)**:

```bash
# Use a prompt with clear answer (high consensus expected)
python3 parallel_agent.py \
  --json \
  --timeout 60 \
  "What is 2 + 2?" \
  > /tmp/no_synthesis_result.json

# Check synthesis was NOT triggered
cat /tmp/no_synthesis_result.json | python3 -m json.tool | grep '"synthesis"'
```

**Expected**:

- ✓ No `synthesis` key (or `synthesis: null`)
- ✓ Consensus score >= 50%

---

#### Test 2.5: Streaming Responses

**Test Streaming Enabled (Default)**:

```bash
# Run with streaming (watch the live display)
python3 parallel_agent.py "Explain async/await in Python in 3 sentences" --timeout 60
```

**Expected**:

- ✓ Live Rich panel displayed during execution
- ✓ Real-time updates as agents respond
- ✓ Format: `🔄 Agent: partial output...`
- ✓ Final output after completion

**Visual Verification**:

```
┌─ Parallel Agent Execution ─────────────────────┐
│                                                 │
│ 🔄 Claude:                                      │
│ Async/await in Python allows you to write...   │
│                                                 │
│ 🔄 Gemini:                                      │
│ The async/await syntax provides...             │
│                                                 │
│ ⏳ Cursor:                                      │
│ Waiting for response...                        │
│                                                 │
└─────────────────────────────────────────────────┘
```

**Test Streaming Disabled**:

```bash
# Disable streaming
python3 parallel_agent.py --no-stream "Same question" --timeout 60
```

**Expected**:

- ✓ No live panel
- ✓ Spinner/progress indicator instead
- ✓ `Running 3 agents...` message
- ✓ Same final output

---

#### Test 2.6: Package Migration (Gemini)

**Test Legacy Package (google-generativeai)**:

```bash
# Check which package is being used
python3 -c "
from parallel_agent import HAS_GENAI_NEW, HAS_GENAI, genai
print('New package (google.genai):', HAS_GENAI_NEW)
print('Has Gemini SDK:', HAS_GENAI)
print('Using package:', genai.__name__ if genai else 'None')
"
```

**Expected**:

- ✓ Shows which package is active
- ✓ Works with both old and new package

**Test Gemini Agent Creation**:

```bash
python3 -c "
from parallel_agent import Config, GeminiAgent, RateLimiter

config = Config()
limiter = RateLimiter(**config.get('rate_limits.gemini', {}))

try:
    agent = GeminiAgent('flash', 60, limiter, config)
    print('✓ Gemini agent created successfully')
    print('✓ Model:', agent.model_name)
    print('✓ Client type:', type(agent.client).__name__)
except Exception as e:
    print('✗ Gemini agent creation failed:', e)
"
```

**Expected**:

- ✓ Agent created successfully
- ✓ Model resolved correctly
- ✓ Client created (with OAuth or API key)

---

### Level 3: Integration Tests (20-30 minutes)

**Goal**: Test complete workflows with all features enabled

#### Test 3.1: Full Analysis Pipeline

```bash
# Create a realistic test file
cat > /tmp/integration_test.py << 'EOF'
"""
E-commerce checkout module
"""
import os
import sqlite3

class CheckoutService:
    def __init__(self):
        self.db = sqlite3.connect('checkout.db')
        # Potential issue: hardcoded in example (should be env var)
        self.payment_api_key = os.getenv('PAYMENT_API_KEY', 'default-key-123')

    def process_payment(self, user_id, amount):
        """Process payment for user"""
        # Potential SQL injection if user_id not validated
        cursor = self.db.cursor()
        cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")
        user = cursor.fetchone()

        if not user:
            return None

        # Call payment API
        try:
            response = self._call_payment_api(amount)
            return response
        except Exception:
            # Silent failure - should log
            pass

        return None

    def _call_payment_api(self, amount):
        """Call external payment API"""
        # Implementation here
        pass

# TODO: Add tests
EOF

# Run FULL pipeline: analyze + validate + synthesis + streaming + logging
python3 parallel_agent.py \
  --analyze /tmp/integration_test.py \
  --validate \
  --json \
  --full-output \
  --timeout 180 \
  > /tmp/integration_result.json

# Verify output
cat /tmp/integration_result.json | python3 -m json.tool > /tmp/integration_result_pretty.json
```

**Verify Complete Output**:

```bash
# Check all sections exist
python3 << 'EOF'
import json

with open('/tmp/integration_result_pretty.json') as f:
    result = json.load(f)

# Check timestamp
assert 'timestamp' in result
print('✓ Timestamp:', result['timestamp'])

# Check mode
assert result['mode'] == 'analyze'
print('✓ Mode:', result['mode'])

# Check agents ran
assert 'agents' in result
assert len(result['agents']) > 0
print('✓ Agents:', list(result['agents'].keys()))

# Check consensus
assert 'cross_verification' in result
consensus = result['cross_verification']
print('✓ Consensus:', f"{consensus['consensus_score']}% ({consensus['confidence']})")

# Check synthesis (if triggered)
if 'synthesis' in consensus:
    print('✓ Synthesis triggered:', consensus['synthesis'].get('triggered'))
else:
    print('✓ Synthesis: Not triggered (consensus >= 50%)')

# Check validation
assert 'validation' in result
validation = result['validation']
print('✓ Validation verdict:', validation['verdict'])
print('  - Tier 1 passed:', validation['tier1']['passed'])
print('  - Tier 2 score:', validation['tier2']['score'])

# Check output files
assert 'output_files' in result
files = result['output_files']
print('✓ Output files created:', len(files))
for agent, path in files.items():
    print(f'  - {agent}: {path}')

print('\n✅ All integration test checks passed!')
EOF
```

**Expected Issues Detected**:

- 🚨 **Tier 1 Security**: Hardcoded secret fallback (`default-key-123`)
- 🚨 **Tier 1 Security**: SQL injection vulnerability (f-string query)
- 🚨 **Tier 1 Error Handling**: Silent failure (bare except pass)
- ⚠️  **Tier 2 Test Coverage**: Missing tests
- ✓ **Tier 2 Maintainability**: Generally good structure

**Expected Verdict**: `BLOCKED` (Tier 1 failures)

---

#### Test 3.2: End-to-End with All Agents

```bash
# Test with all agents (Claude, Gemini, Cursor)
python3 parallel_agent.py \
  --review /tmp/integration_test.py \
  --validate \
  --json \
  --timeout 300 \
  --claude-model sonnet \
  --gemini-model flash \
  > /tmp/all_agents_result.json

# Check all agents completed
python3 << 'EOF'
import json

with open('/tmp/all_agents_result.json') as f:
    result = json.load(f)

agents = result['agents']
print('Agent Results:')
for agent_name, agent_result in agents.items():
    status = agent_result['status']
    duration = agent_result.get('duration_seconds', 0)
    icon = '✓' if status == 'complete' else '✗'
    print(f'{icon} {agent_name.title()}: {status} ({duration:.2f}s)')

    if agent_result.get('credit_fallback'):
        print(f'  ⚠ Credit fallback used')

# Check consensus calculation
consensus = result['cross_verification']
print(f'\nConsensus: {consensus["consensus_score"]}% ({consensus["confidence"]})')
print(f'Agents contributing: {consensus["agent_count"]}')

# Check performance metrics in log file
print('\n✓ Check log file for performance metrics:')
print('  tail -20 ~/.claude/.agent_outputs/parallel_agent.log')
EOF
```

**Expected**:

- ✓ All 3 agents complete (or graceful degradation if one fails)
- ✓ Consensus calculated across all outputs
- ✓ Performance metrics logged for each agent
- ✓ Total duration logged

---

#### Test 3.3: Error Handling & Fallbacks

**Test Credit Fallback**:

```bash
# Simulate credit exhaustion (use test mode if available)
# Or use a model tier that might hit limits

# This would require actually exhausting credits, which we don't want to do
# Instead, check the fallback logic manually:

# Check fallback chains are configured
python3 -c "
from parallel_agent import Config
config = Config()
print('Claude fallback chain:', config.get('credit_fallback.claude'))
print('Gemini fallback chain:', config.get('credit_fallback.gemini'))
print('Cursor fallback chain:', config.get('credit_fallback.cursor'))
"
```

**Expected**:

```
Claude fallback chain: ['opus', 'sonnet', 'haiku']
Gemini fallback chain: ['pro', 'flash']
Cursor fallback chain: ['advanced', 'flash', 'mini']
```

**Test Timeout Handling**:

```bash
# Use very short timeout to trigger timeout
python3 parallel_agent.py --timeout 1 "Write a long essay" --json 2>/dev/null
```

**Expected**:

- ✓ Agents timeout after 1 second
- ✓ Status: "failed"
- ✓ Error: "timeout after 1s"
- ✓ No crashes

**Test Missing Agent**:

```bash
# Run with only Claude (if Gemini/Cursor not available)
python3 parallel_agent.py --claude-only "Test single agent" --timeout 30
```

**Expected**:

- ✓ Works with single agent
- ✓ Consensus score: 0% (only 1 agent)
- ✓ No synthesis (need multiple agents)

---

### Level 4: Performance Tests (10-15 minutes)

**Goal**: Verify performance overhead is acceptable

#### Test 4.1: Baseline Performance

```bash
# Run without streaming, logging minimal
time python3 parallel_agent.py --no-stream --claude-only "Hello" --timeout 30 > /dev/null
```

**Expected**:

- ✓ Completes in reasonable time (< 10s for simple prompt)
- ✓ Most time is API call, not overhead

#### Test 4.2: Streaming Overhead

```bash
# Compare streaming vs non-streaming
echo "Testing non-streaming..."
time python3 parallel_agent.py --no-stream --claude-only "Count to 10" --timeout 30 > /dev/null 2>&1

echo "Testing streaming..."
time python3 parallel_agent.py --claude-only "Count to 10" --timeout 30 > /dev/null 2>&1
```

**Expected**:

- ✓ Streaming overhead < 5%
- ✓ Both complete successfully

#### Test 4.3: Validation Performance

```bash
# Compare with and without validation
echo "Testing without validation..."
time python3 parallel_agent.py --claude-only "Test" --timeout 30 > /dev/null 2>&1

echo "Testing with validation..."
time python3 parallel_agent.py --validate --claude-only "Test" --timeout 30 > /dev/null 2>&1
```

**Expected**:

- ✓ Validation overhead < 1s
- ✓ Mostly heuristic checks (fast)

#### Test 4.4: Log File Size

```bash
# Check log file growth
ls -lh ~/.claude/.agent_outputs/parallel_agent.log

# Run multiple times
for i in {1..10}; do
  python3 parallel_agent.py --claude-only "Test $i" --timeout 20 > /dev/null 2>&1
done

# Check log file size again
ls -lh ~/.claude/.agent_outputs/parallel_agent.log

# Verify rotation works (if > 10MB)
ls -lh ~/.claude/.agent_outputs/parallel_agent.log*
```

**Expected**:

- ✓ Log file grows reasonably (few KB per run)
- ✓ Rotation kicks in at 10MB
- ✓ Up to 5 backup files (parallel_agent.log.1, .2, .3, .4, .5)

---

## 📊 Test Results Tracker

Use this checklist to track test results:

### ✅ Smoke Tests

- [ ] Help menu displays all flags
- [ ] Credit check completes without errors
- [ ] Configuration loads successfully
- [ ] Logger creates log file

### ✅ Feature Tests

- [ ] Logging: Structured JSON logs with correlation IDs
- [ ] CLI flags: --analyze, --improve, --check-credits, --output work
- [ ] Validation: Tier 1 + Tier 2 checks run, verdicts correct
- [ ] Synthesis: Triggers when consensus < 50%, returns JSON
- [ ] Streaming: Live display works, --no-stream fallback works
- [ ] Package: Works with google-generativeai (legacy)

### ✅ Integration Tests

- [ ] Full pipeline: analyze + validate + streaming + logging
- [ ] All agents: Claude + Gemini + Cursor work together
- [ ] Error handling: Timeouts, fallbacks, missing agents

### ✅ Performance Tests

- [ ] Baseline performance acceptable (< 10s for simple prompt)
- [ ] Streaming overhead < 5%
- [ ] Validation overhead < 1s
- [ ] Log rotation works at 10MB

---

## 🐛 Common Issues & Troubleshooting

### Issue: "Missing dependencies"

**Solution**:

```bash
pip3 install -r requirements.txt
```

### Issue: "ANTHROPIC_API_KEY not set"

**Solution**:

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

### Issue: "Gemini OAuth not configured"

**Solution**:

```bash
# Option 1: Use API key
export GOOGLE_API_KEY="..."

# Option 2: Use OAuth
gemini auth login
# OR
gcloud auth application-default login
```

### Issue: Validation always returns BLOCKED

**Cause**: Test file has actual security issues (hardcoded secrets, SQL injection)

**Solution**: Use clean test file or expect BLOCKED verdict

### Issue: Synthesis never triggers

**Cause**: Consensus score >= 50% (agents agree)

**Solution**: Use controversial prompt or mock low consensus

### Issue: Streaming doesn't show

**Cause**: Running in non-TTY environment or Rich not installed

**Solution**: Use `--no-stream` flag or install Rich

### Issue: Log file not created

**Cause**: Directory doesn't exist or permissions issue

**Solution**:

```bash
mkdir -p ~/.claude/.agent_outputs
chmod 700 ~/.claude/.agent_outputs
```

---

## 🎯 Success Criteria

**All tests pass when**:

- ✅ All smoke tests complete without errors
- ✅ Each Phase 3 feature works independently
- ✅ Full pipeline integration test succeeds
- ✅ Error handling gracefully degrades
- ✅ Performance overhead < 5%
- ✅ Log file rotation works
- ✅ All verdicts (APPROVED/NEEDS_REVIEW/BLOCKED) can be triggered

**Ready for production when**:

- ✅ All test levels pass (smoke, feature, integration, performance)
- ✅ API keys configured and working
- ✅ All agents can run (or gracefully degrade)
- ✅ Logging captures all events
- ✅ Validation catches real issues
- ✅ Synthesis resolves disagreements

---

## 📝 Next Steps

After completing E2E tests:

1. **Document any issues found** in GitHub issues
2. **Update configuration** based on test results
3. **Adjust thresholds** if validation too strict/lenient
4. **Performance tune** if overhead > 5%
5. **Deploy to production** if all tests pass

**Test Report Template**:

```
# E2E Test Report

Date: YYYY-MM-DD
Tester: [Name]
Environment: [macOS/Linux]
Python Version: [3.x.x]

## Results
- Smoke Tests: PASS/FAIL
- Feature Tests: PASS/FAIL
- Integration Tests: PASS/FAIL
- Performance Tests: PASS/FAIL

## Issues Found
1. [Issue description]
2. [Issue description]

## Recommendations
- [Recommendation 1]
- [Recommendation 2]

Status: ✅ READY FOR PRODUCTION / ⚠️ NEEDS FIXES
```
