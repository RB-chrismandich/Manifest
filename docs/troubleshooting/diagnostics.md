# Diagnostics & Getting Help

> Commands that show what is actually wrong, and where to escalate.

**Last Updated**: 2026-08-20

## Diagnostic Commands

### Quick System Health Check

Run the automated health check to see your system status:

```bash
# Quick check
~/.claude/scripts/parallel_agent.py --status

# Or directly
~/.claude/scripts/check_status.sh

# Verbose output with versions and paths
~/.claude/scripts/check_status.sh --verbose
```

This checks:

- Configuration file existence and validity
- Enabled/disabled services
- CLI tool installations
- Authentication status
- Overall system readiness

### Manual Installation Check

```bash
# Verify script exists
ls -la ~/.claude/scripts/parallel_agent.py

# Verify configuration files
ls -la ~/.claude/config/

# Check CLI installations
which claude
which gemini
which cursor-agent

# Check versions
claude --version
gemini --version
cursor-agent --version
node --version
npm --version
```

### Check Authentication

```bash
# Claude CLI
claude auth status

# Gemini CLI
gemini auth status

# Check API key environment variables (if set)
echo $ANTHROPIC_API_KEY
echo $GEMINI_API_KEY
```

### Test Individual Agents

```bash
# Test Claude CLI
~/.claude/scripts/parallel_agent.py --claude-only "What is 2+2?"

# Test Gemini CLI
~/.claude/scripts/parallel_agent.py --gemini-only "What is 2+2?"

# Test Cursor (if applicable)
~/.claude/scripts/parallel_agent.py --cursor-only "What is 2+2?"
```

### View Configuration

```bash
# Service configuration
cat ~/.claude/config/services.yml

# Command configuration
cat ~/.claude/config/command_config.yml

# Validation criteria
cat ~/.claude/config/validation_criteria.yml
```

### Check Logs

```bash
# View recent outputs
ls -lth ~/.claude/.agent_outputs/ | head -20

# View latest agent outputs
tail ~/.claude/.agent_outputs/claude_*.txt
tail ~/.claude/.agent_outputs/gemini_*.txt

# View JSON results
cat ~/.claude/.agent_outputs/results_*.json | python3 -m json.tool

# View the orchestrator log
tail ~/.claude/.agent_outputs/parallel_agent.log
```

### Test Network Connectivity

```bash
# Test Anthropic API
curl -I https://api.anthropic.com

# Test Google AI API
curl -I https://generativelanguage.googleapis.com

# Test npm registry (for installations)
curl -I https://registry.npmjs.org
```

---

## Getting More Help

### Still Having Issues?

1. **Check service status:**

   ```bash
   cat ~/.claude/config/services.yml
   claude auth status
   gemini auth status
   ```

2. **Run with verbose output:**

   ```bash
   ~/.claude/scripts/parallel_agent.py --json --full-output "Test" 2>&1 | tee debug.log
   ```

3. **Check GitHub Issues:**
   - Search existing issues: <https://github.com/ReefBytes/Manifest/issues>
   - Create new issue with debug.log

4. **Review documentation:**
   - [Getting Started](../GETTING_STARTED.md)
   - [Configuration Guide](../configuration/README.md)
   - [Architecture Diagrams](../diagrams/README.md)

---

---

[← Troubleshooting](README.md)
