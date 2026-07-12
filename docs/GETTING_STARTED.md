# Getting Started

> Step-by-step guide to installing and using the Manifest parallel agent orchestration framework

**Last Updated**: 2026-06-12
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
- **Antigravity (agy)**: Independent IDE-backed agent for cross-family verification

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
9. ✅ Installs the graphify CLI and deploys the `/graphify` skill when enabled (default; `--disable-graphify` to opt out)

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

# 3. Install the cursor-agent CLI
curl https://cursor.com/install -fsS | bash
# Then authenticate: cursor-agent login  (or set CURSOR_API_KEY)

# 4. Deploy configuration
cp -r configs/claude/* ~/.claude/
cp -r configs/claude/.[!.]* ~/.claude/ 2>/dev/null || true
chmod +x ~/.claude/scripts/*.sh ~/.claude/scripts/parallel_agent.py

# 5. Configure services (see Configuration section)
```

---

## First Run

### Step 1: Verify Installation

Check that the parallel agent script is accessible:

```bash
~/.claude/scripts/parallel_agent.py --help
```

**Expected output:**

```text
Parallel Agent Orchestration

Usage:
  ./parallel_agent.py <prompt>
  ./parallel_agent.py --analyze <file>
  ./parallel_agent.py --review <file>
...
```

### Step 2: Test Agent Connectivity

Run a simple test to verify all agents are working:

```bash
~/.claude/scripts/parallel_agent.py --json "What is 2+2?"
```

**Expected output:**

```json
{
  "timestamp": "20260127_123456",
  "mode": "prompt",
  "agents": {
    "cursor": {"status": "complete", "output": "..."},
    "gemini": {"status": "complete", "output": "..."},
    "claude": {"status": "complete", "output": "..."}
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

> **No API keys required**: the Claude and Gemini agents pick an execution backend
> per run — the provider SDK when its package and API key
> (`ANTHROPIC_API_KEY` / `GOOGLE_API_KEY`) are both present, otherwise the
> logged-in `claude` / `gemini` CLI. OAuth/subscription logins work out of the box.

See [Troubleshooting](TROUBLESHOOTING.md) for solutions.

### Step 3: Test Single Agent Mode

```bash
# Test Claude CLI only
~/.claude/scripts/parallel_agent.py --claude-only "Hello"

# Test Gemini CLI only
~/.claude/scripts/parallel_agent.py --gemini-only "Hello"

# Test Cursor Agent only (if installed)
~/.claude/scripts/parallel_agent.py --cursor-only "Hello"
```

---

## Using Commands

Manifest integrates with Claude Code through slash commands.

### Available Commands

#### `/python-refactor` - Code Analysis (Always uses parallel agents)

Analyzes Python codebases for security, architecture, and code quality issues.

**Example:**

```bash
# In Claude Code
/python-refactor src/
```

**What it does:**

1. Runs all 5 agents in parallel (Cursor, Gemini, Claude, Codex, Antigravity)
2. Each agent analyzes for: security vulnerabilities, bugs, performance issues
3. Synthesizes results with consensus scoring
4. Validates against Tier 1 (security) and Tier 2 (quality) checks
5. Returns unified recommendation

#### `/docs-generate-diagrams` - Architecture Diagrams (Conditional)

Generates Mermaid diagrams for project documentation.

**Example:**

```bash
# In Claude Code
/docs-generate-diagrams docs/ARCHITECTURE.md
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

#### `/docs-improve-readme` - README Enhancement (Never uses parallel agents)

Improves README.md documentation following best practices.

**Example:**

```bash
# In Claude Code
/docs-improve-readme
```

### Command Output Formats

**Markdown (default):**

```bash
~/.claude/scripts/parallel_agent.py "Review this code"
```

**JSON (for programmatic parsing):**

```bash
~/.claude/scripts/parallel_agent.py --json "Review this code"
```

**Full output (no truncation):**

```bash
~/.claude/scripts/parallel_agent.py --json --full-output "Review this code"
```

---

## Configuration Basics

### Enable/Disable Services

Services are configured in `~/.claude/config/services.yml`:

```yaml
services:
  claude:
    enabled: true  # Enable/disable Claude CLI
  gemini:
    enabled: true  # Enable/disable Gemini CLI
  cursor:
    enabled: true  # Enable/disable Cursor Agent
  codex:
    enabled: true  # Enable/disable Codex CLI
  antigravity:
    enabled: true  # Enable/disable Antigravity CLI (agy)
  git_cli:
    github:
      enabled: auto  # auto | true | false (auto-detect if installed)
    gitlab:
      enabled: auto  # auto | true | false (auto-detect if installed)
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
~/.claude/scripts/parallel_agent.py \
  --cursor-model advanced \
  --claude-model opus \
  --review auth.py

# Quick queries (use lightweight models)
~/.claude/scripts/parallel_agent.py \
  --cursor-model mini \
  --claude-model haiku \
  "Quick question"
```

**Model tiers:**

| Tier | Cursor | Claude | Gemini | Codex | Antigravity | Use For |
|------|--------|--------|--------|-------|-------------|---------|
| Lightweight | gpt-5.1-codex-mini | claude-haiku-4-5-20251001 | - | gpt-5.4-mini | Gemini 3.5 Flash (Low) | Quick questions |
| Balanced | gpt-5.1-codex | claude-sonnet-4-6 | gemini-3-flash-preview | gpt-5.4 | Gemini 3.5 Flash (High) | Code review |
| Maximum | gpt-5.2 | claude-opus-4-8 | gemini-3-pro-preview | gpt-5.5 | Claude Opus 4.6 (Thinking) | Security analysis |
| Security | - | claude-fable-5 | - | - | - | Critical security tasks |

**See**: [Configuration Guide](CONFIGURATION.md) for all options

### Consensus Thresholds

Agents agree when consensus score ≥ threshold:

- **≥80%**: High confidence → auto-proceed with unified recommendation
- **50-79%**: Medium confidence → highlight disagreements to user
- **<50%**: Low confidence → escalate for human review

Configure in `~/.claude/config/command_config.yml`:

```yaml
# float 0.0-1.0 scale — must match command_config.yml
consensus:
  high: 0.80
  medium: 0.50
  low: 0.0
```

---

## Next Steps

### For Regular Use

1. **Integrate with Claude Code**: Commands are available as `/python-refactor`, `/docs-generate-diagrams`, etc.
2. **Review Configuration**: Read [Configuration Guide](CONFIGURATION.md) to customize behavior
3. **Learn Architecture**: View [Architecture Diagrams](ARCHITECTURE_DIAGRAMS.md) to understand data flows

### For Troubleshooting

If you encounter issues:

1. Check [Troubleshooting Guide](TROUBLESHOOTING.md)
2. Verify service configuration: `cat ~/.claude/config/services.yml`
3. Test individual agents: `~/.claude/scripts/parallel_agent.py --claude-only "test"`

### For Advanced Usage

- **Custom Skills**: Create new slash commands in `.skillshare/skills/` (exposed via `configs/claude/skills/`)
- **Validation Rules**: Customize security/quality checks in `configs/claude/config/validation_criteria.yml`
- **Model Fallbacks**: Configure credit exhaustion fallback chains
- **Environment Variables**: Override defaults with `CURSOR_MODEL_ADVANCED`, `GEMINI_INCLUDE_DIRS`, etc.
- **SkillClaw (opt-in)**: Capture agent sessions and evolve skills locally — enable with
  `./bootstrap.sh --enable-skillclaw`. See [docs/SKILLCLAW.md](SKILLCLAW.md) for details.
- **pilotfish (opt-in)**: Cost-tiered role-agents that delegate mechanical/read-only work to
  cheaper model tiers and gate results behind a verifier — enable with
  `./bootstrap.sh --enable-pilotfish` (Claude-only; does not change your main-session model).

**See**: [Configuration Guide](CONFIGURATION.md) for advanced topics

### Using Manifest with emdash

[emdash](https://github.com/generalaction/emdash) is a desktop **harness** — not a
Manifest deploy target — that launches your agent CLIs in parallel git worktrees
using your real `HOME`. A Manifest-configured agent therefore inherits the full
config (skills, subagents, hooks, MCP, guides) **transitively**, with no `~/.emdash/`
directory to deploy. Prerequisites: run `./bootstrap.sh` first (home deploy) and
install a supported agent (Claude Code is formally verified; Codex/Gemini/Cursor are
best-effort). Verify with `/env-check`'s "emdash Inheritance" section, or run the
probe directly:

```bash
configs/claude/scripts/emdash_inherit_check.sh   # verdict INHERITED = full parity
```

See [docs/EMDASH.md](EMDASH.md) for setup, the `.emdash.json` worktree pattern, and
the hook-coexistence caveat.

---

## Quick Reference

```bash
# Test all agents
~/.claude/scripts/parallel_agent.py --json "Test"

# Use specific models
~/.claude/scripts/parallel_agent.py --cursor-model advanced --claude-model opus "Task"

# Run single agent
~/.claude/scripts/parallel_agent.py --claude-only "Question"

# Analyze a file
~/.claude/scripts/parallel_agent.py --review file.py

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
