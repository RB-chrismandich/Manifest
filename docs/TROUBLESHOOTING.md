# Troubleshooting Guide

> Common problems and solutions for the Manifest parallel agent orchestration
framework

**Last Updated**: 2026-01-27
**Audience**: All users
**Quick Help**: Most issues are fixed by checking service configuration and
verifying CLI installations

---

## Table of Contents

1. [Installation Issues](#installation-issues)
2. [Agent Execution Issues](#agent-execution-issues)
3. [Authentication Issues](#authentication-issues)
4. [Configuration Issues](#configuration-issues)
5. [Performance Issues](#performance-issues)
6. [Output Issues](#output-issues)
7. [Diagnostic Commands](#diagnostic-commands)

---

## Installation Issues

### Bootstrap Fails with "Permission denied"

**Symptom:**

```bash
./bootstrap.sh
-bash: ./bootstrap.sh: Permission denied
```

**Solution:**

```bash
chmod +x bootstrap.sh
./bootstrap.sh
```

**Cause:** Script not marked as executable

---

### Homebrew Installation Fails (macOS)

**Symptom:**

```text
Error: Homebrew installation failed
```

**Solution:**

```bash
# Install Homebrew manually
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Re-run bootstrap
./bootstrap.sh --skip-install
```

**Alternative:** Use `--skip-install` flag and install dependencies manually

---

### npm Install Fails

**Symptom:**

```text
npm ERR! code EACCES
npm ERR! syscall access
npm ERR! path /usr/local/lib/node_modules
```

**Solution:**

```bash
# Option 1: Use sudo (not recommended)
sudo npm install -g @anthropic-ai/claude-code
sudo npm install -g @google/gemini-cli

# Option 2: Fix npm permissions (recommended)
mkdir ~/.npm-global
npm config set prefix '~/.npm-global'
echo 'export PATH=~/.npm-global/bin:$PATH' >> ~/.bashrc
source ~/.bashrc

# Retry installation
npm install -g @anthropic-ai/claude-code
npm install -g @google/gemini-cli
```

---

### Node.js Not Found (Linux)

**Symptom:**

```text
Error: Node.js not found
```

**Solution:**

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install nodejs npm

# RHEL/Fedora
sudo dnf install nodejs npm

# Arch
sudo pacman -S nodejs npm

# Verify installation
node --version
npm --version
```

---

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
which cursor

# If missing, install
npm install -g @anthropic-ai/claude-code
npm install -g @google/gemini-cli

# Verify installation
claude --version
gemini --version
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

1. **Authentication failure** → See [Authentication
Issues](#authentication-issues)

2. **Quota exceeded** → Wait or use cheaper models
3. **Timeout** → Increase timeout with `--timeout 900`

**Solution:**

```bash
# Check authentication
claude auth status
gemini auth status

# Try with longer timeout
~/.claude/scripts/parallel_agent.sh --timeout 900 "Task"

# Try with cheaper models
~/.claude/scripts/parallel_agent.sh \
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
~/.claude/scripts/parallel_agent.sh --status
~/.claude/scripts/parallel_agent.sh --codex-only --codex-model advanced "Quick test"
```

**Tradeoff:** This avoids permission issues but uses a separate Codex
state/config history path.

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
~/.claude/scripts/parallel_agent.sh --status

# 2. Check service configuration
cat ~/.claude/config/services.yml

# 3. Reconfigure to enable services
./bootstrap.sh --reconfigure --enable-claude --enable-gemini

# 4. Or edit services.yml directly
vim ~/.claude/config/services.yml
# Change enabled: false → enabled: true

# 5. Verify the fix
~/.claude/scripts/parallel_agent.sh --json 'Hello from all agents'
```

---

### Parallel Agents Not Running

**Symptom:** Only one agent runs when you expect multiple

**Cause:** Command-line flag overriding configuration

**Solution:**

```bash
# Check for --*-only flags
# BAD: Only runs Claude
~/.claude/scripts/parallel_agent.sh --claude-only "Task"

# GOOD: Runs all enabled agents
~/.claude/scripts/parallel_agent.sh "Task"

# Check services.yml for disabled agents
cat ~/.claude/config/services.yml
```

---

## Authentication Issues

### Claude CLI: "Not authenticated"

**Symptom:**

```text
Error: You are not authenticated. Run 'claude auth login'
```

**Solution:**

```bash
# Log in to Claude CLI
claude auth login

# Follow prompts to enter API key

# Verify authentication
claude auth status
```

**Get API Key:**

1. Visit: <https://console.anthropic.com/account/keys>
2. Create new API key
3. Copy key for `claude auth login`

---

### Gemini CLI: "Authentication failed"

**Symptom:**

```text
Error: Invalid API key
```

**Solution:**

```bash
# Authenticate with Gemini CLI
gemini auth login

# Verify authentication
gemini auth status
```

**Get API Key:**

1. Visit: <https://makersuite.google.com/app/apikey>
2. Create new API key
3. Copy key for `gemini auth login`

---

### Cursor: "Command not found"

**Symptom:**

```bash
cursor: command not found
```

**Solution:**

Cursor is a desktop application, not a CLI tool. The Manifest integration
expects Cursor
to be installed but doesn't directly invoke it via command line in the current
implementation.

**Workaround:**

```bash
# Disable Cursor in configuration
./bootstrap.sh --reconfigure --disable-cursor

# Or use --no-cursor flag
~/.claude/scripts/parallel_agent.sh --no-claude "Task"
```

**Note:** Cursor integration may be implemented differently in your environment.
Check your specific Cursor setup for command-line access.

---

## Configuration Issues

### services.yml Not Found

**Symptom:**

```text
Warning: No services config, use defaults (all enabled)
```

**Solution:**

```bash
# Deploy configuration
cp -r .claude/* ~/.claude/

# Or re-run bootstrap
./bootstrap.sh --force
```

---

### Invalid YAML Syntax

**Symptom:**

```text
Error: YAML parsing failed
```

**Solution:**

```bash
# Validate YAML syntax
python3 -c "import yaml; yaml.safe_load(open('~/.claude/config/services.yml'))"

# Common issues:
# - Incorrect indentation (must use spaces, not tabs)
# - Missing colons
# - Unquoted strings with special characters

# Restore from backup
cp .claude/config/services.yml ~/.claude/config/services.yml
```

---

### Configuration Not Updating

**Symptom:** Changes to `services.yml` don't take effect

**Cause:** Configuration is cached or CLI flags override

**Solution:**

```bash
# Restart shell to clear any environment variables
exit
# (Open new terminal)

# Verify configuration is correct
cat ~/.claude/config/services.yml

# Run without CLI flag overrides
~/.claude/scripts/parallel_agent.sh "Task"
```

---

## Performance Issues

### Agents Timeout

**Symptom:**

```text
Error: Agent timed out after 600 seconds
```

**Solution:**

```bash
# Increase timeout (up to 10 minutes recommended)
~/.claude/scripts/parallel_agent.sh --timeout 900 "Task"

# Use lighter models for faster response
~/.claude/scripts/parallel_agent.sh \
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
~/.claude/scripts/parallel_agent.sh \
  --cursor-model flash \
  --claude-model sonnet \
  "Task"

# Or use single agent for quick tasks
~/.claude/scripts/parallel_agent.sh --claude-only "Quick question"
```

---

### High API Costs

**Symptom:** Unexpected high costs from API usage

**Solution:**

```bash
# Use lightweight models by default
export CURSOR_MODEL_FLASH="gpt-5.1-codex-mini"  # Instead of gpt-5.1-codex
export CLAUDE_MODEL_TIER="haiku"                 # Instead of sonnet

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
~/.claude/scripts/parallel_agent.sh --json "Task" | jq .

# Check output files directly
cat ~/.manifest/orchestration/outputs/results_*.json

# Validate JSON
~/.claude/scripts/parallel_agent.sh --json "Task" | python3 -m json.tool
```

---

### Output Truncated

**Symptom:** Agent responses cut off mid-sentence

**Solution:**

```bash
# Use --full-output to disable truncation
~/.claude/scripts/parallel_agent.sh --json --full-output "Task"

# Check output files for complete responses
cat ~/.manifest/claude/outputs/claude_*.txt
cat ~/.manifest/gemini/outputs/gemini_*.txt
```

---

### No Output Files Generated

**Symptom:** Expected files in `~/.manifest/orchestration/outputs/` don't exist

**Cause:** Output directory not created or permissions issue

**Solution:**

```bash
# Create output directory
mkdir -p ~/.manifest/orchestration/outputs

# Fix permissions
chmod 700 ~/.manifest/orchestration/outputs

# Specify custom output directory
~/.claude/scripts/parallel_agent.sh --output ~/.manifest/orchestration/outputs "Task"
```

---

## Diagnostic Commands

### Quick System Health Check

Run the automated health check to see your system status:

```bash
# Quick check
~/.claude/scripts/parallel_agent.sh --status

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
ls -la ~/.claude/scripts/parallel_agent.sh

# Verify configuration files
ls -la ~/.claude/config/

# Check CLI installations
which claude
which gemini
which cursor

# Check versions
claude --version
gemini --version
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
~/.claude/scripts/parallel_agent.sh --claude-only "What is 2+2?"

# Test Gemini CLI
~/.claude/scripts/parallel_agent.sh --gemini-only "What is 2+2?"

# Test Cursor (if applicable)
~/.claude/scripts/parallel_agent.sh --cursor-only "What is 2+2?"
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
ls -lth ~/.manifest/orchestration/outputs/ | head -20

# View latest agent outputs
tail ~/.manifest/claude/outputs/claude_*.txt
tail ~/.manifest/gemini/outputs/gemini_*.txt

# View JSON results
cat ~/.manifest/orchestration/outputs/results_*.json | python3 -m json.tool
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
   ~/.claude/scripts/parallel_agent.sh --json --full-output "Test" 2>&1 | tee debug.log
   ```

3. **Check GitHub Issues:**
   - Search existing issues: <https://github.com/ReefBytes/Manifest/issues>
   - Create new issue with debug.log

4. **Review documentation:**
   - [Getting Started](GETTING_STARTED.md)
   - [Configuration Guide](CONFIGURATION.md)
   - [Architecture Diagrams](ARCHITECTURE_DIAGRAMS.md)

---

## Related Documents

- [Getting Started](GETTING_STARTED.md) - Installation guide
- [Configuration Guide](CONFIGURATION.md) - All configuration options
- [README.md](../README.md) - Project overview
- [CLAUDE.md](../CLAUDE.md) - Repository context
