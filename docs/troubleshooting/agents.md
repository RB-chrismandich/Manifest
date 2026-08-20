# Agent Execution Problems

> Agents that hang, fail, or return nothing.

**Last Updated**: 2026-08-20

## Agent Execution Issues

### Agent Status: "missing"

**Symptom:**

```json
{
  "agents": {
    "claude": {"status": "missing"}
  }
}
```

**Solution:**

```bash
# Check if CLI is installed
which claude
which gemini
which cursor-agent

# If missing, install
npm install -g @anthropic-ai/claude-code
npm install -g @google/gemini-cli
curl https://cursor.com/install -fsS | bash

# Verify installation
claude --version
gemini --version
cursor-agent --version
```

---

### Agent Status: "failed"

**Symptom:**

```json
{
  "agents": {
    "claude": {"status": "failed", "output": "Error: ..."}
  }
}
```

**Causes:**

1. **Authentication failure** → See [Authentication Issues](authentication.md)
2. **Quota exceeded** → Wait or use cheaper models
3. **Timeout** → Increase timeout with `--timeout 900`

**Solution:**

```bash
# Check authentication
claude auth status
gemini auth status

# Try with longer timeout
~/.claude/scripts/parallel_agent.py --timeout 900 "Task"

# Try with cheaper models
~/.claude/scripts/parallel_agent.py \
  --claude-model haiku \
  --cursor-model mini \
  "Task"
```

---

### Codex: Session Storage Not Writable

**Symptom:**

```text
Warning: Codex runtime unavailable, disabling Codex agent
Reason: Session directory is not writable: /Users/<user>/.manifest/codex/sessions
```

**Why this happens:**

Codex CLI requires writable session storage even in non-interactive `exec` mode.

**Preferred fix (repair ~/.manifest permissions):**

```bash
sudo chown -R "$(whoami)" ~/.manifest
chmod -R u+rwX ~/.manifest
```

**Engineering workaround (use a custom Codex state path):**

```bash
# 1) Create a writable Manifest state directory
mkdir -p ~/.manifest/custom-codex-state

# 2) Point Codex state to it
export CODEX_HOME="$HOME/.manifest/custom-codex-state"

# 3) Re-run status or orchestration
~/.claude/scripts/parallel_agent.py --status
~/.claude/scripts/parallel_agent.py --codex-only --codex-model advanced "Quick test"
```

**Tradeoff:** This avoids permission issues but uses a separate Codex state/config history path.

---

### All Agents Disabled

**Symptom:**

```text
Warning: Only 0 services enabled (minimum: 2)
Error: No agents available to run
```

**Solution:**

```bash
# 1. Check system status (recommended)
~/.claude/scripts/parallel_agent.py --status

# 2. Check service configuration
cat ~/.claude/config/services.yml

# 3. Reconfigure to enable services
./bootstrap.sh --reconfigure --enable-claude --enable-gemini

# 4. Or edit services.yml directly
vim ~/.claude/config/services.yml
# Change enabled: false → enabled: true

# 5. Verify the fix
~/.claude/scripts/parallel_agent.py --json 'Hello from all agents'
```

---

### Parallel Agents Not Running

**Symptom:** Only one agent runs when you expect multiple

**Cause:** Command-line flag overriding configuration

**Solution:**

```bash
# Check for --*-only flags
# BAD: Only runs Claude
~/.claude/scripts/parallel_agent.py --claude-only "Task"

# GOOD: Runs all enabled agents
~/.claude/scripts/parallel_agent.py "Task"

# Check services.yml for disabled agents
cat ~/.claude/config/services.yml
```

---

---

[← Troubleshooting](README.md)
