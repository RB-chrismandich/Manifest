# Getting Started

> Step-by-step guide to installing and using the Manifest parallel agent orchestration framework

**Last Updated**: 2026-02-11
**Audience**: New users
**Prerequisites**: macOS 10.15+ or Linux, internet connection
**Estimated Time**: 10-15 minutes

---

## Table of Contents

1. [What is Manifest?](#what-is-manifest)
2. [Installation](#installation)
3. [First Run](#first-run)
4. [Using Commands](#using-commands)
5. [Configuration Basics](#configuration-basics)
6. [Next Steps](#next-steps)

---

## What is Manifest?

Manifest deploys a parallel LLM agent orchestration system that enables Claude Code to leverage multiple AI agents simultaneously:

- **Cursor Agent**: IDE-integrated context and code analysis
- **Gemini CLI**: Broad knowledge and creative solutions
- **Claude CLI**: Deep reasoning and security analysis
- **Codex CLI**: Terminal-based coding agent with sandbox execution

These agents run in parallel, analyze the same task from different perspectives,
and their outputs are synthesized with consensus scoring to provide higher-quality
results than any single agent.

**Key Benefits**:

- Cross-verification reduces hallucinations
- Diverse perspectives catch more edge cases
- Automatic model selection based on task complexity
- Consensus scoring (≥80% agreement = high confidence)

---

## Installation

### Option 1: Automated Bootstrap (Recommended)

The bootstrap script handles everything automatically.

```bash
# Clone the repository
git clone https://github.com/ReefBytes/Manifest.git
cd Manifest

# Run bootstrap with all services
./bootstrap.sh
```

**What happens during bootstrap:**

1. ✅ Detects your platform (macOS/Linux)
2. ✅ Installs Homebrew (macOS) or checks package manager (Linux)
3. ✅ Installs Node.js if missing
4. ✅ Installs Claude CLI via npm
5. ✅ Installs Gemini CLI via npm
6. ✅ Opens Cursor download page in browser
7. ✅ Copies configuration to `~/.claude/`
8. ✅ Guides you through authentication for each service

**Selective Installation**:

```bash
# Only install Claude and Gemini (skip Cursor)
./bootstrap.sh --disable-cursor

# Only install Claude
./bootstrap.sh --disable-gemini --disable-cursor

# Skip authentication checks (configure manually later)
./bootstrap.sh --skip-auth
```

### Option 2: Manual Installation

If you prefer manual control:

```bash
# 1. Install Node.js (if not installed)
# macOS:
brew install node

# Linux (Ubuntu/Debian):
sudo apt install nodejs npm

# 2. Install AI agent CLIs
npm install -g @anthropic-ai/claude-code
npm install -g @google/gemini-cli

# 3. Download Cursor
# Visit: https://cursor.sh

# 4. Deploy configuration
cp -r .claude/* ~/.claude/
chmod +x ~/.claude/scripts/*.sh

# 5. Configure services (see Configuration section)
```

---

## First Run

### Step 1: Verify Installation

Check that the parallel agent script is accessible:

```bash
~/.claude/scripts/parallel_agent.sh --help
```

**Expected output:**

```text
Parallel Agent Orchestration

Usage:
  ./parallel_agent.sh <prompt>
  ./parallel_agent.sh --analyze <file>
  ./parallel_agent.sh --review <file>
...
```

### Step 2: Test Agent Connectivity

Run a simple test to verify all agents are working:

```bash
~/.claude/scripts/parallel_agent.sh --json "What is 2+2?"
```

**Expected output:**

```json
{
  "timestamp": "20260127_123456",
  "mode": "prompt",
  "agents": {
    "cursor": { "status": "complete", "output": "..." },
    "gemini": { "status": "complete", "output": "..." },
    "claude": { "status": "complete", "output": "..." }
  },
  "cross_verification": {
    "consensus_score": 100,
    "confidence": "high"
  }
}
```

**If an agent fails:**

- `status: "missing"` → Agent CLI not installed
- `status: "failed"` → Authentication issue or quota exceeded

See [Troubleshooting](TROUBLESHOOTING.md) for solutions.

### Step 3: Test Single Agent Mode

```bash
# Test Claude CLI only
~/.claude/scripts/parallel_agent.sh --claude-only "Hello"

# Test Gemini CLI only
~/.claude/scripts/parallel_agent.sh --gemini-only "Hello"

# Test Cursor Agent only (if installed)
~/.claude/scripts/parallel_agent.sh --cursor-only "Hello"
```

---

## Using Commands

Manifest integrates with Claude Code through slash commands.

### Available Commands

#### `/refactor-python` - Code Analysis (Always uses parallel agents)

Analyzes Python codebases for security, architecture, and code quality issues.

**Example:**

```bash
# In Claude Code
/refactor-python src/
```

**What it does:**

1. Runs all 3 agents in parallel (Cursor, Gemini, Claude)
2. Each agent analyzes for: security vulnerabilities, bugs, performance issues
3. Synthesizes results with consensus scoring
4. Validates against Tier 1 (security) and Tier 2 (quality) checks
5. Returns unified recommendation

#### `/docs-diagrams` - Architecture Diagrams (Conditional)

Generates Mermaid diagrams for project documentation.

**Example:**

```bash
# In Claude Code
/docs-diagrams docs/ARCHITECTURE.md
```

**Triggers parallel agents when:** Analyzing 5+ unique imports/modules

#### `/docs-improve` - Documentation Analysis (Conditional)

Analyzes documentation against the Diataxis framework.

**Example:**

```bash
# In Claude Code
/docs-improve docs/
```

**Triggers parallel agents when:** Total documentation lines > 500

#### `/docs-readme` - README Enhancement (Never uses parallel agents)

Improves README.md documentation following best practices.

**Example:**

```bash
# In Claude Code
/docs-readme
```

### Command Output Formats

**Markdown (default):**

```bash
~/.claude/scripts/parallel_agent.sh "Review this code"
```

**JSON (for programmatic parsing):**

```bash
~/.claude/scripts/parallel_agent.sh --json "Review this code"
```

**Full output (no truncation):**

```bash
~/.claude/scripts/parallel_agent.sh --json --full-output "Review this code"
```

---

## Configuration Basics

### Enable/Disable Services

Services are configured in `~/.claude/config/services.yml`:

```yaml
services:
  claude:
    enabled: true # Enable/disable Claude CLI
  gemini:
    enabled: true # Enable/disable Gemini CLI
  cursor:
    enabled: true # Enable/disable Cursor Agent
  codex:
    enabled: true # Enable/disable Codex CLI
  git_cli:
    github:
      enabled: auto # auto | true | false (auto-detect if installed)
    gitlab:
      enabled: auto # auto | true | false (auto-detect if installed)
```

**Reconfigure after initial setup:**

```bash
# Disable Cursor Agent
./bootstrap.sh --reconfigure --disable-cursor

# Re-enable Gemini CLI
./bootstrap.sh --reconfigure --enable-gemini

# Enable Git CLIs explicitly
./bootstrap.sh --reconfigure --enable-gh --enable-glab
```

### Model Selection

Choose models based on task complexity:

```bash
# Security analysis (use most powerful models)
~/.claude/scripts/parallel_agent.sh \
  --cursor-model advanced \
  --claude-model opus \
  --review auth.py

# Quick queries (use lightweight models)
~/.claude/scripts/parallel_agent.sh \
  --cursor-model mini \
  --claude-model haiku \
  "Quick question"
```

**Model tiers:**

| Tier        | Cursor             | Claude | Gemini         | Codex   | Use For           |
| ----------- | ------------------ | ------ | -------------- | ------- | ----------------- |
| Lightweight | gpt-5.1-codex-mini | haiku  | -              | o4-mini | Quick questions   |
| Balanced    | gpt-5.1-codex      | sonnet | gemini-3-flash | o3      | Code review       |
| Maximum     | gpt-5.2            | opus   | gemini-3-pro   | o3-pro  | Security analysis |

**See**: [Configuration Guide](CONFIGURATION.md) for all options

### Consensus Thresholds

Agents agree when consensus score ≥ threshold:

- **≥80%**: High confidence → auto-proceed with unified recommendation
- **50-79%**: Medium confidence → highlight disagreements to user
- **<50%**: Low confidence → escalate for human review

Configure in `~/.claude/config/command_config.yml`:

```yaml
consensus:
  high: 80
  medium: 50
  low: 0
```

---

## Next Steps

### For Regular Use

1. **Integrate with Claude Code**: Commands are available as `/refactor-python`, `/docs-diagrams`, etc.
2. **Review Configuration**: Read [Configuration Guide](CONFIGURATION.md) to customize behavior
3. **Learn Architecture**: View [Architecture Diagrams](ARCHITECTURE_DIAGRAMS.md) to understand data flows

### For Troubleshooting

If you encounter issues:

1. Check [Troubleshooting Guide](TROUBLESHOOTING.md)
2. Verify service configuration: `cat ~/.claude/config/services.yml`
3. Test individual agents: `~/.claude/scripts/parallel_agent.sh --claude-only "test"`

### For Advanced Usage

- **Custom Skills**: Create new slash commands in `configs/claude/skills/`
- **Validation Rules**: Customize security/quality checks in `configs/claude/config/validation_criteria.yml`
- **Model Fallbacks**: Configure credit exhaustion fallback chains
- **Environment Variables**: Override defaults with `CURSOR_MODEL_ADVANCED`, `GEMINI_INCLUDE_DIRS`, etc.

**See**: [Configuration Guide](CONFIGURATION.md) for advanced topics

---

## Quick Reference

```bash
# Test all agents
~/.claude/scripts/parallel_agent.sh --json "Test"

# Use specific models
~/.claude/scripts/parallel_agent.sh --cursor-model advanced --claude-model opus "Task"

# Run single agent
~/.claude/scripts/parallel_agent.sh --claude-only "Question"

# Analyze a file
~/.claude/scripts/parallel_agent.sh --review file.py

# Reconfigure services
./bootstrap.sh --reconfigure --disable-cursor

# View configuration
cat ~/.claude/config/services.yml
cat ~/.claude/config/command_config.yml
```

---

## Related Documents

- [README.md](../README.md) - Project overview
- [Configuration Guide](CONFIGURATION.md) - All configuration options
- [Architecture Diagrams](ARCHITECTURE_DIAGRAMS.md) - Visual system documentation
- [Troubleshooting](TROUBLESHOOTING.md) - Common problems and solutions
- [CLAUDE.md](../CLAUDE.md) - Repository context for AI assistants
