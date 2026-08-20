# Features

> What Manifest does, feature by feature.

## Features

- **Parallel Agent Orchestration**: Run 2-5 AI agents simultaneously
  (Cursor, Gemini, Claude, Codex, Antigravity, and opt-in Devin) with real-time streaming display
- **Modular `agents/` Package**: `parallel_agent.py` backed by `agents/` subpackage —
  `cli.py`, `config.py`, `orchestrator.py`, `runners.py`, `synthesis.py`, `validation.py`
- **Logging**: Structured JSON logs with correlation IDs, rotation (10MB, 5 backups), performance metrics
- **Full Validation Engine**: Tier 1 (critical: security, errors, breaking changes)
  \+ Tier 2 (quality: bugs, performance, tests)
- **Automatic Synthesis**: Disagreement resolution when consensus < 50% using Claude Sonnet
- **Streaming Responses**: Real-time Rich Live display with progressive updates (4 updates/sec)
- **Consensus Scoring**: Variance-based algorithm calculates agreement (≥80% = high confidence, <50% = escalate + synthesis)
- **Intelligent Model Selection**: Task-based routing by *tier* (security→`opus`/`advanced`,
  review→`sonnet`/`flash`, quick→`haiku`/`mini`). Each tier maps to a provider-native model
  in `model_tiers`, verified against live provider CLIs by `model_check.sh`
- **Credit Exhaustion Fallback**: Automatic detection and retry with cheaper models (opus→sonnet→haiku)
- **OAuth-Only Friendly**: Claude/Gemini agents auto-select SDK or CLI backends — no API keys
  needed when the `claude`/`gemini` CLIs are logged in (SDK + API key still preferred when present)
- **Cross-Platform**: Native support for macOS (Intel/Apple Silicon) and 5 major Linux distributions
- **Unified Label Management**: Canonical label registry with sync across GitHub, GitLab, and Linear
- **Autonomous Issue Development** (`/issue-dev-auto`): Picks the next `auto-dev`-labeled issue,
  implements it test-first, and opens a PR for review (never merges); run unattended via `/loop /issue-dev-auto`
- **Repo Hygiene Sweep** (`/repo-clean`): Review-then-confirm cleanup of open PRs and stale/merged/gone
  branches across GitHub, GitLab, and local
- **Issue-Linking Git Hooks** (`/issue-sync-pr`, `/issue-sync-commit`): Fail-open PostToolUse hooks that keep
  the linked issue's status label and back-links in sync as commits land and PRs open (installable via `install_issue_hooks.sh`)
- **Devin CLI Support** (opt-in): Adds Cognition's `devin` as a sixth panel agent
  (`--devin-only`, `--no-devin`). Its skills are **inherited, not copied** — the CLI reads
  `~/.claude/skills` and `~/.claude/CLAUDE.md` directly once bootstrap pins
  `read_config_from.claude` in `~/.config/devin/config.json`, so nothing is duplicated.
  Enable with `--enable-devin` after `devin auth login`
- **Production Templates**: Pre-configured permission templates for Django, Express, Go microservices, Python monorepos
- **SkillClaw Integration** (opt-in): Passively ingests Claude Code's own `~/.claude/projects/**/*.jsonl`
  transcripts, runs a `claude -p` map-reduce evolve pass (Max subscription, no API key), and proposes
  evolved skills via a review PR. No proxy, no daemon, no port. Enable with `--enable-skillclaw`
- **apm (Agent Package Manager)** (opt-in, under evaluation): Installs the pinned `apm` CLI, the
  candidate build/deploy layer for agent primitives (feature 522). Acquisition is **fail-closed** —
  the wheel is downloaded, checksum-verified against a recorded digest, and installed from the
  verified bytes; a mismatch, a failed download, or a missing checksum tool leaves apm uninstalled
  rather than falling back to an unverified binary. Installing it hands it no deploy domain; the
  legacy pipeline still owns everything. Enable with `--enable-apm`
- **Plugin Bundles** (spec 674): the 108 skills ship as nine Claude Code plugin
  bundles, each skill reachable as `/<bundle>:<name>`. Refresh one with
  `claude plugin update <bundle>@manifest`. Cursor, Gemini, Codex,
  Antigravity and Devin read the flat tree at `~/.manifest/skills`.
- **Proton Pass Credential Retrieval** (`/pass-cli`): Retrieve passwords, API keys, and tokens from Proton Pass
  vaults without storing PATs in files or memory
- **Pilotfish Cost-Tiered Orchestration** (opt-in): Deploys six role-agents (scout, Explore,
  mech-executor, executor, verifier, security-executor) to both the Claude home
  (`~/.claude/agents/`, bound to built-in model aliases haiku/sonnet/opus) and the Cursor home
  (`~/.cursor/agents/`, Cursor-native frontmatter with `model: inherit`), plus a verifier-gated
  delegation policy, so mechanical/read-only work runs on cheaper tiers while the frontier model
  plans and decides. Config-only; does not change your main-session model. Enable with
  `--enable-pilotfish`
- **DevPanel Critic-Gated Role Agents** (opt-in): Deploys five role-agents (developer, debugger,
  tester as primaries; spec-guard, chaos-engineer as shared adversarial validators) to the same
  Claude/Cursor agent homes as pilotfish, on disjoint filenames — both toggles may be enabled
  together. A propose → critique → refactor loop: a primary implements/diagnoses/tests, both
  validators independently gate the candidate, and the loop terminates only on dual `APPROVED`
  with zero pending changes. Config-only; does not change your main-session model. Enable with
  `--enable-devpanel`
- **Stitch Design Skills** (15 skills, vendored in `.apm/skills`; originally from
  [`google-labs-code/stitch-skills`](https://github.com/google-labs-code/stitch-skills)):
  design workflows (`generate-design`, `code-to-design`, `manage-design-system`, ...), code
  generation (`react-components`, `react-native`, `react-vite-dashboard`, `remotion`,
  `shadcn-ui`), and utilities (`stitch-loop`, `enhance-prompt`, `taste-design`, `design-md`) for
  [Google Stitch](https://stitch.withgoogle.com). Requires the Stitch MCP server — see
  [Requirements](getting-started/requirements.md)

---

---

[← Manifest README](../README.md)
