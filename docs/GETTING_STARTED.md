# Getting Started

> Step-by-step guide to installing and using Manifest's OMP-native workflow configuration

**Last Updated**: 2026-09-12
**Audience**: New users
**Prerequisites**: macOS 10.15+ or Linux, internet connection
**Estimated Time**: 10-15 minutes

---

## What is Manifest?

Manifest deploys shared AI coding guides, skills, prompts, and scripts for
Claude Code, Cursor, Gemini CLI, Codex CLI, Antigravity, and opt-in Devin.

Interactive sub-agent work uses OMP-native `task` batches: submit all ready,
independent units in one call (at most 32 per wave), assign each child one unit,
and have the parent validate and aggregate evidence. Use `hub` only to
coordinate or wait. If OMP is unavailable, work inline and report `DEGRADED`;
do not fall back to provider CLI fan-out.

Retained noninteractive tools such as CDDL, delegation, and SkillClaw use
`model_policy.yml` to resolve a single provider CLI, model tier, and bounded
fallback.

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
chmod +x ~/.claude/scripts/*.sh

# 5. Configure services (see Configuration section)
```

---

## First Run

### Step 1: Verify Installation

Confirm the installed command surface:

```bash
~/.local/bin/manifest --help
```

### Step 2: Start a Coding Session

Open a supported coding harness and invoke a skill. For independent work,
follow the OMP dispatch guidance in the installed orchestration guide: use one
`task` batch for all ready units, validate worker evidence in the parent, and
keep shared mutations sequential.

For a retained noninteractive integration, configure the relevant provider CLI
and `~/.claude/config/model_policy.yml`; see
[Model Policy](MODEL-POLICY.md) for its scope.

---

## Continue

| Page | Lesson |
|------|--------|
| [Using Commands](getting-started/using-commands.md) | Invoking skills once the first run works |
| [Configuration Basics](getting-started/configuration.md) | The few settings worth changing early |
| [Next Steps](getting-started/next-steps.md) | Where to go from here |
| [Quick Reference](getting-started/quick-reference.md) | Every command from this tutorial |
