# Quick Start: Testing Parallel Agent Phase 3

**Goal**: Get you testing in < 5 minutes

---

## 🚀 Fastest Path (30 seconds)

```bash
cd /Users/charlemagne/.claude/scripts

# Run automated tests
./run_e2e_tests.sh
```

**What it does**: Runs smoke tests (syntax, config, help menu) - no API calls needed

**Expected output**:

```text
═══════════════════════════════════════════════
  Level 0: Prerequisites
═══════════════════════════════════════════════
✓ Python version: 3.11.7
✓ Syntax check passed
✓ All config files present
✓ Core dependencies installed
⚠ ANTHROPIC_API_KEY not set (some tests will be skipped)

═══════════════════════════════════════════════
  Level 1: Smoke Tests (Fast)
═══════════════════════════════════════════════
✓ Help menu shows new flags
✓ Config and Logger functional
✓ All YAML files valid

═══════════════════════════════════════════════
  Test Summary
═══════════════════════════════════════════════
Tests Passed: 8
Tests Failed: 0
Pass Rate:    100%

✅ ALL TESTS PASSED
```

---

## 🔧 Setup (2 minutes)

### 1. Install Dependencies

```bash
cd /Users/charlemagne/.claude/scripts
pip3 install -r requirements.txt
```

### 2. Set API Keys

```bash
# Claude (required for most tests)
export ANTHROPIC_API_KEY="sk-ant-..."

# Gemini (optional - will use OAuth if not set)
export GOOGLE_API_KEY="..."
# OR: gemini auth login
```

### 3. Verify Setup

```bash
# Quick check
python3 parallel_agent.py --check-credits
```

**Expected**:

```json
{
  "claude": {"status": "available"},
  "gemini": {"status": "available"},
  "cursor": {"status": "assumed_available"}
}
```

---

## ✅ Full Test Suite (5 minutes)

```bash
# Run ALL tests (includes API calls)
./run_e2e_tests.sh --full
```

**What it tests**:

- ✓ Prerequisites (syntax, config, dependencies)
- ✓ Smoke tests (help, credit check, config loading)
- ✓ Feature tests (logging, CLI flags, validation, streaming)
- ✓ Unit tests (Logger, ValidationEngine, SynthesisEngine)

**Expected duration**: 3-5 minutes (with API calls)

---

## 🎯 Manual Tests (10 minutes)

### Test 1: Basic Execution

```bash
python3 parallel_agent.py "What is 2+2?" --timeout 30
```

**Expected**: Live streaming display with agent responses

---

### Test 2: Analysis with Validation

```bash
# Create test file
cat > /tmp/test_file.py << 'EOF'
API_KEY = "hardcoded-secret"
def unsafe_query(user_input):
    return f"SELECT * FROM users WHERE name='{user_input}'"
EOF

# Analyze it
python3 parallel_agent.py --analyze /tmp/test_file.py --validate --json
```

**Expected**:

- Verdict: `BLOCKED`
- Tier 1 failures: hardcoded secret, SQL injection
- Full validation report in JSON

---

### Test 3: Synthesis Triggering

```bash
# Ask controversial question (low consensus expected)
python3 parallel_agent.py --json \
  "Should we use tabs or spaces for indentation? Give a STRONG opinion." \
  --timeout 60
```

**Expected**:

- Consensus score < 50%
- Synthesis triggered
- `unified_recommendation` in output

---

### Test 4: Streaming Display

```bash
# Watch live streaming
python3 parallel_agent.py "Explain async/await in Python" --timeout 60
```

**Expected**: Real-time Rich panel with agent outputs

**Compare with non-streaming**:

```bash
python3 parallel_agent.py --no-stream "Same question" --timeout 60
```

---

### Test 5: Logging

```bash
# Generate logs
python3 parallel_agent.py "Test logging" --timeout 30

# View logs
tail -20 ~/.claude/.agent_outputs/parallel_agent.log
```

**Expected**: JSON-formatted logs with correlation IDs

---

## 📊 Check Your Results

### View Validation Output

```bash
# Run test with validation
python3 parallel_agent.py --analyze /tmp/test_file.py --validate --json > /tmp/result.json

# Pretty print
cat /tmp/result.json | python3 -m json.tool | less
```

### View Logs

```bash
# Tail logs in real-time
tail -f ~/.claude/.agent_outputs/parallel_agent.log

# Search logs by correlation ID
grep "20260210_143022_12345" ~/.claude/.agent_outputs/parallel_agent.log
```

### Check Output Files

```bash
# List recent outputs
ls -lt ~/.claude/.agent_outputs/ | head -10

# View summary
cat ~/.claude/.agent_outputs/summary_*.md | tail -50
```

---

## 🐛 Troubleshooting

### Issue: "Missing dependencies"

```bash
pip3 install -r requirements.txt
```

### Issue: "ANTHROPIC_API_KEY not set"

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
# Add to ~/.bashrc or ~/.zshrc to persist
```

### Issue: "Gemini OAuth not configured"

```bash
# Option 1: API key
export GOOGLE_API_KEY="..."

# Option 2: OAuth
gemini auth login
# OR
gcloud auth application-default login
```

### Issue: Tests timeout

```bash
# Increase timeout
python3 parallel_agent.py --timeout 300 "Your prompt"
```

### Issue: "Can't import parallel_agent"

```bash
# Make sure you're in the scripts directory
cd /Users/charlemagne/.claude/scripts
python3 parallel_agent.py --help
```

---

## 📈 Success Metrics

**Basic Success** (smoke tests):

- ✓ Syntax valid
- ✓ Config loads
- ✓ Help menu shows all flags

**Full Success** (with API):

- ✓ Credit check passes
- ✓ Logging works
- ✓ Validation detects issues
- ✓ Streaming displays
- ✓ Synthesis triggers on disagreement

---

## 📚 Next Steps

### 1. Read Full Guide

```bash
cat E2E_TESTING_GUIDE.md
```

Comprehensive guide with:

- All test levels (smoke, feature, integration, performance)
- Expected outputs for each test
- Troubleshooting for every issue
- Test result tracker checklist

### 2. Test Your Own Files

```bash
# Analyze your code
python3 parallel_agent.py --analyze /path/to/your/file.py --validate --json

# Review your code
python3 parallel_agent.py --review /path/to/your/file.py --timeout 300
```

### 3. Customize Configuration

```bash
# Edit config
vim ~/.claude/config/parallel_agent.yml

# Adjust thresholds
# - synthesis.threshold (default: 0.50)
# - validation thresholds (in validation_criteria.yml)
# - streaming.refresh_rate (default: 4)
```

### 4. Review Implementation

```bash
# See what was implemented
cat PYTHON_PHASE3_COMPLETE.md

# Check code
vim parallel_agent.py
```

---

## 🎉 Quick Wins

**1-Minute Test**:

```bash
./run_e2e_tests.sh
```

**5-Minute Test**:

```bash
./run_e2e_tests.sh --full
```

**10-Minute Test**:

```bash
# Manual feature tests
python3 parallel_agent.py --check-credits
python3 parallel_agent.py --analyze /tmp/test.py --validate --json
python3 parallel_agent.py "Test synthesis" --json
tail ~/.claude/.agent_outputs/parallel_agent.log
```

---

## 📞 Support

**Documentation**:

- Quick Start: `TESTING_QUICK_START.md` (this file)
- Full Guide: `E2E_TESTING_GUIDE.md`
- Implementation: `PYTHON_PHASE3_COMPLETE.md`

**Test Scripts**:

- Automated: `./run_e2e_tests.sh`
- Unit tests: `python3 test_parallel_agent.py`

**Logs**:

- Runtime: `~/.claude/.agent_outputs/parallel_agent.log`
- Outputs: `~/.claude/.agent_outputs/`

---

## ✨ Summary

**Fastest path to testing**:

1. `cd /Users/charlemagne/.claude/scripts`
2. `./run_e2e_tests.sh`
3. See results in < 30 seconds

**With API keys**:

1. `export ANTHROPIC_API_KEY="sk-ant-..."`
2. `./run_e2e_tests.sh --full`
3. Complete test suite in 3-5 minutes

**Manual testing**:

1. Follow examples above
2. Test each feature individually
3. See `E2E_TESTING_GUIDE.md` for comprehensive tests

**Status**: ✅ Ready to test! All Phase 3 features implemented and functional.
