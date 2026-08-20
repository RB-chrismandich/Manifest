# Service Configuration

> Per-service toggles, SkillClaw, and native plugin reconciliation.

## Service Configuration

**File**: `~/.claude/config/services.yml`

Controls which AI agents are enabled for parallel orchestration.

### Structure

```yaml
services:
  # Claude Code CLI - Anthropic's AI assistant
  claude:
    enabled: true  # Set to false to disable
    command: claude
    description: "Deep reasoning, security analysis, complex logic"
    model_tiers:
      - haiku    # Fast, economical
      - sonnet   # Balanced (default)
      - opus     # Maximum capability

  # Gemini CLI - Google's AI assistant
  gemini:
    enabled: true
    command: gemini
    description: "Broad knowledge, creative solutions, research"
    model_tiers:
      - flash    # Fast (default)
      - pro      # Advanced

  # Cursor Agent - headless CLI for code analysis
  cursor:
    enabled: true
    command: cursor-agent
    description: "IDE-integrated context, code-specific analysis"
    model_tiers:
      - mini     # Lightweight
      - flash    # Balanced (default)
      - advanced # Maximum capability

  # Codex CLI - OpenAI terminal coding agent
  codex:
    enabled: true
    command: codex
    description: "Terminal coding assistant for codebase edits and automation"
    model_tiers:
      - mini     # Lightweight (gpt-5.6-luna)
      - flash    # Balanced (gpt-5.6-terra, default)
      - advanced # Maximum capability (gpt-5.6-sol)
      - auto     # Use Codex config default model


  # pilotfish - cost-tiered role-agents (~/.claude/agents/) + delegation policy reference.
  # Opt-in, config-only, Claude-only. Enabling deploys six role-agents (scout, Explore,
  # mech-executor, executor, verifier, security-executor) that bind to Claude Code's built-in
  # model aliases (haiku/sonnet/opus) plus a read-on-demand delegation policy; disabling removes
  # exactly those. Does not change the main-session model. Toggle: --enable-pilotfish.
  pilotfish:
    enabled: false           # opt-in; --enable-pilotfish to turn on
    description: "Cost-tiered role-agents + delegation policy, verifier-gated (opt-in, Claude-only)"

  # devpanel - critic-gated dev/debug/test role-agents (~/.claude/agents/) + delegation policy
  # reference. Opt-in, config-only, Claude-only, independent of pilotfish (own toggle/marker,
  # same target dir, disjoint filenames — both may be enabled together). Enabling deploys five
  # role-agents (developer, debugger, tester + shared validators spec-guard, chaos-engineer) in
  # a propose->critique->refactor loop; disabling removes exactly those. Toggle: --enable-devpanel.
  devpanel:
    enabled: false           # opt-in; --enable-devpanel to turn on
    description: "developer/debugger/tester + spec-guard/chaos-engineer critic loop (opt-in, Claude-only)"

  # Git CLI tools - Platform-specific Git hosting integrations
  git_cli:
    github:
      enabled: auto  # auto | true | false (default: auto-detect)
      command: gh
      description: "GitHub CLI for issue/PR management"
    gitlab:
      enabled: auto  # auto | true | false (default: auto-detect)
      command: glab
      description: "GitLab CLI for issue/MR management"
    detection:
      platform: auto  # auto | github | gitlab | git
      remote: origin  # overridable via MANIFEST_GIT_REMOTE

# Minimum agents required for parallel orchestration
minimum_agents: 2

# Fallback behavior when enabled services are unavailable
fallback:
  strategy: continue_with_available  # Options: continue_with_available, abort, warn_user
  warn_threshold: 1  # Warn if only this many agents available
```

### Enabling/Disabling Services

### Option 1: Reconfigure with bootstrap.sh

```bash
# Disable Cursor
./bootstrap.sh --reconfigure --disable-cursor

# Enable all services
./bootstrap.sh --reconfigure --enable-claude --enable-gemini --enable-cursor

# Enable Git CLIs explicitly (useful when auto-detect isn't desired)
./bootstrap.sh --reconfigure --enable-gh --enable-glab

# Disable Git CLIs
./bootstrap.sh --reconfigure --disable-gh --disable-glab

# Enable browser-use (Python E2E browser automation for smoke-manage UI steps)
./bootstrap.sh --reconfigure --enable-browser-use

```

### Option 2: Edit services.yml manually

```bash
# Edit configuration
vim ~/.claude/config/services.yml

# Change enabled: true to enabled: false
services:
  cursor:
    enabled: false  # Disabled
```

### Option 3: Override at runtime with CLI flags

```bash
# Temporarily disable Claude for this run only
~/.claude/scripts/parallel_agent.py --no-claude "Task"

# Run only Cursor Agent
~/.claude/scripts/parallel_agent.py --cursor-only "Task"
```

### Service Validation

The script validates services on startup:

1. Checks if `services.yml` exists
2. Parses enabled/disabled state for each service
3. Verifies minimum agent count (default: 2)
4. Warns if fewer agents than minimum are available

---

## SkillClaw Configuration (Optional)

**File**: `~/.claude/config/skillclaw.yml`
**Repo source**: `configs/claude/config/skillclaw.yml`

SkillClaw is an **opt-in**, proxy-free skill evolution pipeline. It passively reads
`~/.claude/projects/**/*.jsonl` transcripts (the same files Claude Code writes during
normal sessions), evolves them into skill candidates using `claude -p` (Max-backed,
no separate API key required), and opens review PRs. It is **disabled by default** and
does not intercept any agent traffic — no daemon is started, no shell wrappers are
installed, no `BASE_URL` environment variable is set.

### Enabling and Disabling

```bash
# Enable SkillClaw (creates chmod-700 storage dirs; no daemon or wrappers)
./bootstrap.sh --enable-skillclaw

# Disable SkillClaw
./bootstrap.sh --disable-skillclaw

# Reconfigure alongside other toggles
./bootstrap.sh --reconfigure --enable-skillclaw --disable-cursor
```

When enabled, `services.yml` gains a `skillclaw:` stanza set to `enabled: true`.

### What skillclaw.yml Configures

`~/.claude/config/skillclaw.yml` is the **Manifest-owned** config. It is distinct from
the vestigial upstream `~/.skillclaw/config.yaml` that older versions of the skillclaw
tool may create.

```yaml
# Storage — session and evolved-skill data (chmod 700; secrets scrubbed before evolution)
storage:
  root: ~/.skillclaw
  sessions: ~/.skillclaw/sessions
  evolved: ~/.skillclaw/skills
  rejected: ~/.skillclaw/skills/rejected
  state: ~/.skillclaw/.ingest-state.json

# Ingest — how transcripts are read from ~/.claude/projects
ingest:
  transcripts_dir: ~/.claude/projects
  window_days: 30              # only transcripts modified within the last 30 days
  settle_minutes: 5            # skip files whose mtime is <5 min old (still being written)
  max_tool_output_chars: 500   # truncate tool stdout/stderr incl. base64 blobs (noise control)

# Evolve — how ingested sessions become skill candidates
evolve:
  engine: claude-cli            # `claude -p` headless, Max-backed; no separate API key
  token_budget: 100000          # map-reduce chunk threshold; stays clear of 200k context limit
  prompt_template: ~/.claude/prompts/skillclaw_evolve.md

# Promotion — how evolved skills become PRs
promotion:
  branch_prefix: skillclaw/evolve-
  pr_base: main
  pr_labels:
    - needs-review
    - follow-up
```

### How It Works

1. **Ingest** (`skillclaw_ingest.py`) scans `~/.claude/projects/**/*.jsonl` for transcripts
   within the `window_days` window, skipping files still being written (`settle_minutes`).
   Tool output is truncated to `max_tool_output_chars` characters to reduce noise.
2. **Evolve** (`skillclaw_evolve.py`) runs `claude -p` in map-reduce mode against each
   ingested session, staying under the `token_budget` threshold to avoid the 200 k context
   limit. Candidates that pass quality checks are written to `evolved/`; rejected ones go to
   `rejected/` for inspection.
3. **Promote** (`skillclaw_promote.sh`, also `/skill-evolve`) opens one review PR per run.

### Promotion

Evolved skills are promoted via `~/.claude/scripts/skillclaw_promote.sh` (also available as
the `/skill-evolve` slash command). Dry-run is the default; pass `--apply` to open a PR.
The script opens one review PR (one commit per skill) and aborts if an open
`skillclaw/evolve-*` PR already exists — use `--force-new` to override.

**Full design doc**: [docs/SKILLCLAW.md](../SKILLCLAW.md)

---

## Native Plugin Reconciliation and ADHD Guidance

Bootstrap invokes `manifest bootstrap-sync --source <checkout> --harness codex
--non-interactive --json`. The coordinator installs and verifies the complete
local marketplace before replacing the flat Codex skill link with a system-only
directory. A failed plugin or hook verification keeps the legacy link and makes
an enabled Codex deployment fail.

Codex's initial model-visible skill metadata is separately bounded. Every
Manifest skill ships a generated `agents/openai.yaml`; only
`manifest-code-quality:antipattern-detect`, `manifest-security:code-audit`, and
`manifest-workspace:help` allow implicit invocation. The remaining skills stay
installed and are invoked explicitly as `$bundle:skill`. The qualified allowlist
is maintained in `configs/claude/config/skill_policies.yml`, and
`tools/generate_plugin_views.py --check` rejects missing, duplicate, or unknown
entries and stale generated metadata.

`manifest-i-have-adhd` mirrors commit
`2d19ad205eb1d85fc9c3968bdeba4c2116518685` of `ayghri/i-have-adhd`. Its
SessionStart launcher emits only canonical bundled guidance; session payload
values are never reflected. Say `stop adhd mode` or `normal mode` to stop the
style for the active session.

Antigravity receives the same generated Gemini extension context through its
measured Gemini-lineage import surface (`contextFileName` points to the pinned
guidance). Devin receives the generated guidance through its native Windsurf
`global_rules.md` always-on rule. Manifest writes that Devin file only when it
is absent, empty, or already byte-identical; non-empty user content is preserved
and reported as a blocking collision.

---

[← Configuration](README.md)
