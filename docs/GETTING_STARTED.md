# Getting Started

> Step-by-step guide to installing and using the Manifest parallel agent orchestration framework

**Last Updated**: 2026-06-12
**Audience**: New users
**Prerequisites**: macOS 10.15+ or Linux, internet connection
**Estimated Time**: 10-15 minutes

---

## What is Manifest?

Manifest deploys a parallel LLM agent orchestration system that enables Claude Code to leverage multiple AI agents simultaneously:

- **Cursor Agent**: IDE-integrated context and code analysis
- **Gemini CLI**: Broad knowledge and creative solutions
- **Claude CLI**: Deep reasoning and security analysis
- **Codex CLI**: Terminal-based coding agent with sandbox execution
- **Antigravity (agy)**: Independent IDE-backed agent for cross-family verification
- **Devin CLI** *(opt-in)*: Cognition's terminal agent, off by default — enable with
  `./bootstrap.sh --enable-devin` after `devin auth login`

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

See [Troubleshooting](troubleshooting/README.md) for solutions.

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

## Continue

| Page | Lesson |
|------|--------|
| [Using Commands](getting-started/using-commands.md) | Invoking skills once the first run works |
| [Configuration Basics](getting-started/configuration.md) | The few settings worth changing early |
| [Next Steps](getting-started/next-steps.md) | Where to go from here |
| [Quick Reference](getting-started/quick-reference.md) | Every command from this tutorial |
