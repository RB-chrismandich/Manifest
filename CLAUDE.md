# CLAUDE.md

> Repository context and guidance for Claude Code when working with this codebase

**Last Updated**: 2026-07-30
**Audience**: AI assistants (Claude Code), contributors
**Purpose**: Provide Claude Code with repository structure, deployment process, and testing guidelines

---

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## MCP Default Policy

Default MCP/tool routing is defined once in the deployed orchestration guide —
see [configs/claude/CLAUDE.md](configs/claude/CLAUDE.md) ("Default MCP/tool
routing"), which is also the authority on which servers are actually registered
versus opt-in. Only Context7 ships registered (#646); do not assume the rest are
available. The full catalog is `configs/claude/config/mcp_servers.yml`.

## Repository Purpose

This repository manages AI coding workflow configuration for deployment to
supported native-host surfaces. It contains current-host orchestration guides,
skills, and retained single-provider scripts shared by supported harnesses.

## Repository Structure

```text
configs/                             # Deployment source configs (deployed to ~/ via bootstrap.sh)
├── claude/                          # → ~/.claude/ (primary configuration)
│   ├── prompts/                     # Skill and single-provider prompt templates
│   ├── config/                      # YAML configuration files
│   │   ├── mcp_servers.yml          # Default MCP server registry (OAuth-capable)
│   │   └── model_policy.yml         # Single-provider CLI model tiers and fallback
│   ├── .plans/                      # Plan management (template, archive, abandoned)
│   ├── settings.local.json          # Default permissions and MCP server config
│   └── scripts/manifest_cli/        # Manifest CLI router (smoke, skill-run, ...)
├── cursor/                          # → ~/.cursor/ (Cursor IDE configuration)
│   ├── rules/                       # Cursor rules (.mdc) adapted from commands/skills
│   ├── mcp.json                     # Cursor MCP server defaults
│   └── (symlinks to ../claude/)     # scripts, config, prompts, .plans (skills via rules/)
├── gemini/                          # → ~/.gemini/ (Gemini CLI configuration)
│   ├── GEMINI.md                    # Orchestration guide for Gemini
│   ├── settings.json                # Gemini settings (includes MCP server defaults)
│   └── (symlinks to ../claude/)     # scripts, config, prompts, .plans
├── codex/                           # → ~/.codex/ (Codex CLI configuration)
│   ├── AGENTS.md -> ../../AGENTS.md # Codex guide
│   └── (symlinks to ../claude/)     # scripts, config, prompts, .plans
    └── (symlinks to ../claude/)     # config, skills, .plans (no provider orchestration)

.claude/                             # Repo-specific config only (does NOT override active sessions)
├── CLAUDE.md                        # Developer guide for working in this repo
├── skills/                          # speckit-* project-scoped skills (loaded in this repo's sessions)
└── settings.local.json              # Repo-relevant permissions only (no MCP servers)

.claude-plugin/marketplace.json      # this repo IS the "manifest" plugin marketplace
plugins/                             # ten plugin bundles, 114 skills (installed via marketplace, NOT bootstrap)
bootstrap.sh                         # macOS/Linux bootstrap script
bootstrap/                           # Modular bootstrap libraries + hookable modules
├── lib/                             # Shared bootstrap logic split by concern
│   ├── common.sh                    # Shared output/prompts/symlink helpers
│   ├── modules.sh                   # Hook registry + module loader
│   ├── platform.sh                  # Platform detection + timeout/browser helpers
│   ├── config.sh                    # Argument parsing + services config helpers
│   ├── install.sh                   # CLI install routines
│   ├── auth.sh                      # Authentication + state setup routines
│   ├── deploy.sh                    # Deploy/verify/summary routines
│   └── mcp.sh                       # MCP configuration/install routines
└── modules/README.md                # How to add custom bootstrap extensions
AGENTS.md                            # AI agent instructions (Cursor, Claude, Gemini, Codex, Antigravity)
```

## Bootstrap (macOS / Linux)

The `bootstrap.sh` script automates installation, deployment, and authentication.

**Supported platforms:**

- macOS (Intel and Apple Silicon)
- Linux (Debian/Ubuntu, RHEL/Fedora, Arch, openSUSE)

### Quick Start

```bash
# Full setup with all services
./bootstrap.sh

# Setup with specific services disabled
./bootstrap.sh --disable-cursor
./bootstrap.sh --disable-gemini --disable-cursor

# Skip interactive prompts
./bootstrap.sh --skip-auth --force

# Configure MCP servers (interactive per-server selection)
./bootstrap.sh --install-mcp
```

Service toggles (`--enable-*/--disable-*` for claude, gemini, cursor, codex,
antigravity, devin, skillclaw, apm, browser-use, smoke, gh, glab), other flags (`--skip-install`,
`--skip-auth`, `--force`, `--reconfigure`, `--install-mcp`), and the full step
list are documented in [README.md](README.md) and `./bootstrap.sh --help`.

The script installs Homebrew/Node.js and enabled CLIs as needed, deploys
`configs/` to `~/`, writes toggles to `~/.claude/config/services.yml`, and
checks authentication.

## Manual Deployment

Per-platform manual copy/symlink steps (Claude, Cursor, Gemini, Codex,
Antigravity) and required CLI installs are in
[docs/GETTING_STARTED.md](docs/GETTING_STARTED.md).

## Key Files

| File | Purpose |
|------|---------|
| `configs/claude/CLAUDE.md` | Main current-host native orchestration guide |
| `configs/cursor/rules/orchestration.mdc` | Cursor always-on guidance |
| `configs/gemini/GEMINI.md` | Gemini CLI guide |
| `configs/codex/AGENTS.md` | Codex CLI guide |
| `configs/claude/config/model_policy.yml` | Model tiers and CLI fallback for retained single-provider tools |
| `configs/claude/scripts/git_platform.sh` | Platform detection script (github, gitlab, git) |
| `configs/claude/scripts/linear_ops.sh` | Linear API wrapper for issue management (GraphQL) |
| `configs/claude/config/tracker_providers.yml` | Issue-tracker provider registry — access precedence, phase-to-status mapping, per-provider config |
| `configs/claude/scripts/tracker_registry.py` | Read-only resolver CLI for `tracker_providers.yml` (status/access/default-provider/mcp-tool lookups) |
| `configs/claude/scripts/tracker_ops.sh` | Provider-agnostic issue verb dispatcher (github/gitlab/linear; jira exit 3) — resolve-provider, issue-list/view/create/comment/transition/label/close, duplicate-mark |
| `configs/claude/config/command_config.yml` | Thresholds, tool policies, model selection, error recovery |
| `configs/claude/config/code_constitution.yml` | Code Constitution: 12 pre-write articles + per-language ceilings |
| `configs/claude/scripts/constitution_check.py` | Constitution checker (ratcheted); hook `constitution_hook.py` |
| `configs/claude/config/tracker_triage.yml` | Provider-neutral triage scoring, duplicate detection, staleness thresholds (replaced `linear_triage.yml`, deleted 2026-07-29) |
| `configs/claude/config/validation_criteria.yml` | Tier 1 (critical) and Tier 2 (quality) validation rules |
| `configs/claude/config/labels.yml` | Canonical label registry for GitHub, GitLab, and Linear |
| `configs/claude/scripts/label_sync.sh` | Label sync script — reads registry, provisions labels across platforms |
| `AGENTS.md` | AI agent instructions for all platforms (Cursor, Claude, Gemini, Codex) |

## Available Commands

Skills (70+, invoked as `/skill-name`) live in `.apm/skills/` — each
directory's `SKILL.md` frontmatter is the authoritative name and description,
and Claude Code auto-loads every description at session start, so no table is
duplicated here. Per-skill native dispatch policy lives in
`configs/claude/config/command_config.yml` under `tool_policies`. See
[`docs/COMMANDS.md`](docs/COMMANDS.md) for the human-readable command reference.

**CLI tools** (installed to `~/.local/bin/`): `sync-skills` — sync
`.apm/skills/` to all home targets. Skills ship as plugin bundles: refresh
with `claude plugin update <bundle>@manifest`.

## Testing Changes

Confirm the Manifest CLI surface:

```bash
PYTHONPATH=configs/claude/scripts python3 -m manifest_cli --help
```

Validate YAML syntax:

```bash
python3 -c "import yaml; yaml.safe_load(open('configs/claude/config/command_config.yml'))"
python3 -c "import yaml; yaml.safe_load(open('configs/claude/config/model_policy.yml'))"
python3 -c "import yaml; yaml.safe_load(open('configs/claude/config/validation_criteria.yml'))"
```

## Label Management

**Labels**: managed centrally in `configs/claude/config/labels.yml` (12 active
labels incl. the auto-dev lifecycle set), synced across GitHub, GitLab and
Linear by `label_sync.sh`; the full registry table lives in
[docs/commands/builtin.md](docs/commands/builtin.md#label-management).

```bash
configs/claude/scripts/label_sync.sh             # sync to current platform
configs/claude/scripts/label_sync.sh --dry-run  # preview
```

## Adding New Skills

Create `plugins/<bundle>/skills/<name>/SKILL.md` (source of truth; `.apm/skills`
is the generated mirror), give it a bundle in `skill_policies.yml` + the bundle's
`plugin.json`, and add `tool_policies` in `command_config.yml` — then **run the
generators**, or CI fails: `docs/COMMANDS.md`, the `GEMINI.md`/`AGENTS.md` index
(`--inject-guides` — a *different* file set), and `configs/cursor/rules/`. Traps:
[docs/SKILL-NAMING.md](docs/SKILL-NAMING.md#lifecycle-adding-renaming-retiring).

Skills are invoked as `/my-skill` in Claude Code.

## Plan Management

Implementation plans are tracked in `configs/claude/.plans/` as date-prefixed markdown files
(`YYYYMMDD-description.md`). Plans follow a lifecycle:
CREATE -> ACTIVE -> COMPLETED (`.archive/`) or ABANDONED (`.abandoned/`).
See `configs/claude/.plans/README.md` for naming conventions and rules.
Use `/plan-manage` to create plans, review stale plans, or archive/abandon
completed work. Independent plan-review units use the current host's native
mechanism; the parent compares their evidence directly.

## Configuration Reference

**Native dispatch:** OMP uses `task` batches and `hub`; Claude Code uses
discovered native Agents and background collection. The parent validates and
aggregates evidence. The shared
[`sub-agent-dispatch` contract](configs/claude/references/sub-agent-dispatch.md)
defines child limits, the runner exception, and `DEGRADED` behavior.

**Validation tiers** (in `validation_criteria.yml`):

- Tier 1 (blocking): Security, error handling, breaking changes
- Tier 2 (advisory): Bug detection, performance, maintainability, test coverage

**Single-provider model policy** (in `model_policy.yml`): model tiers, provider
order, CLI-agent invocation shapes, and bounded fallback for noninteractive
tools. It is not an interactive sub-agent dispatcher.

---

## Related Documents

- [README.md](README.md) - Project overview and quick start
- [docs/README.md](docs/README.md) - Documentation hub: it indexes GETTING_STARTED,
  CONFIGURATION, diagrams/ and TROUBLESHOOTING
- [configs/claude/.plans/README.md](configs/claude/.plans/README.md) - Plan management quick reference
- [configs/claude/CLAUDE.md](configs/claude/CLAUDE.md) - Orchestration guide (deployed to ~/.claude/)
- [docs/CODING_STANDARDS.md](docs/CODING_STANDARDS.md) - Per-language coding standards and enforcement layers
- [docs/MODEL-POLICY.md](docs/MODEL-POLICY.md) - Which model runs a session/sub-agent/turn, measured

<!-- SPECKIT START -->
## Active Spec Kit Feature

- **`675-multi-agent-delegation`** — Implementation in progress via CDDL;
  `plugins/manifest-delegate` bundle landed, remaining: verification gates.
  [plan.md](specs/675-multi-agent-delegation/plan.md) (+ research, data-model,
  contracts/, quickstart).
- `674-plugin-architecture` — complete ([record](specs/674-plugin-architecture/cutover-plan.md)).
<!-- SPECKIT END -->
