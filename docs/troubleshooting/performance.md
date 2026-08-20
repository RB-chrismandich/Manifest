# Performance & Output Problems

> Slow runs and malformed or missing output.

## Performance Issues

### Agents Timeout

**Symptom:**

```text
Error: Agent timed out after 600 seconds
```

**Solution:**

```bash
# Increase timeout (up to 10 minutes recommended)
~/.claude/scripts/parallel_agent.py --timeout 900 "Task"

# Use lighter models for faster response
~/.claude/scripts/parallel_agent.py \
  --cursor-model mini \
  --claude-model haiku \
  "Task"
```

---

### Slow Consensus Scoring

**Symptom:** Long wait time for results

**Cause:** Multiple agents running heavy models

**Solution:**

```bash
# Use balanced models
~/.claude/scripts/parallel_agent.py \
  --cursor-model flash \
  --claude-model sonnet \
  "Task"

# Or use single agent for quick tasks
~/.claude/scripts/parallel_agent.py --claude-only "Quick question"
```

---

### High API Costs

**Symptom:** Unexpected high costs from API usage

**Solution:**

```bash
# Use lightweight models by default
export CURSOR_MODEL_FLASH="gpt-5.1-codex-mini"  # Instead of gpt-5.1-codex

# Or pass a lighter Claude tier per run
~/.claude/scripts/parallel_agent.py --claude-model haiku "Task"

# Configure in command_config.yml
vim ~/.claude/config/command_config.yml
# Change task_model_defaults to use cheaper models

# Disable expensive agents
./bootstrap.sh --reconfigure --disable-cursor
```

---

## Output Issues

### JSON Output Malformed

**Symptom:** `jq` fails to parse output

**Cause:** Agent output contains non-JSON text

**Solution:**

```bash
# Use --json flag explicitly
~/.claude/scripts/parallel_agent.py --json "Task" | jq .

# Check output files directly
cat ~/.claude/.agent_outputs/results_*.json

# Validate JSON
~/.claude/scripts/parallel_agent.py --json "Task" | python3 -m json.tool
```

---

### Output Truncated

**Symptom:** Agent responses cut off mid-sentence

**Solution:**

```bash
# Use --full-output to disable truncation
~/.claude/scripts/parallel_agent.py --json --full-output "Task"

# Check output files for complete responses
cat ~/.claude/.agent_outputs/claude_*.txt
cat ~/.claude/.agent_outputs/gemini_*.txt
```

---

### No Output Files Generated

**Symptom:** Expected files in `~/.claude/.agent_outputs/` don't exist

**Cause:** Output directory not created or permissions issue. On permission
errors (e.g. sandboxed runs) the script falls back to
`/tmp/.claude_agent_outputs_<pid>` — check there too.

**Solution:**

```bash
# Create output directory
mkdir -p ~/.claude/.agent_outputs

# Fix permissions
chmod 700 ~/.claude/.agent_outputs

# Specify custom output directory
~/.claude/scripts/parallel_agent.py --output /tmp/agent_outputs "Task"
```

---

---

[← Troubleshooting](README.md)
