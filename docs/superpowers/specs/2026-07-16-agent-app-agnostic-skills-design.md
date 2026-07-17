# Agent/App-Agnostic Skills — Umbrella Architecture + Phase 1 (Tracker Abstraction)

**Date**: 2026-07-16
**Status**: DRAFT (pending user review)
**Driver**: Portability — anyone should be able to adopt Manifest with their own
stack (Jira instead of Linear, Codex instead of Claude) and skills just work.

---

## 1. Problem

An audit of all 98 skills in `.skillshare/skills/` found that agent coupling is
already largely solved (~20 audit/refactor skills delegate to
`parallel_agent.py`, which abstracts five agent backends via config), but app
coupling is concentrated and structural:

- `issue-triage` is Linear-only (hardwired to `linear_ops.sh` +
  `linear_triage.yml`); no GitHub/GitLab/Jira path.
- 12 skills are GitHub-hardcoded: 8 call raw `gh api` directly
  (`pr-address-comments`, `pr-monitor`, `premise-verify`, `api-optimize-bulk`,
  `ci-audit-triggers`, `ci-harden-workflow`, `ci-reproduce-failure`,
  `reproduce-gated-ci-failure-locally`), plus `pr-clean-base`,
  `pr-reset-reapply`, `pr-merge-stacked`, `merge-stacked-pr-chain`.
- Partially-abstracted tracker skills (`issue-prioritize`, `repo-clean`,
  `pr-review`, `issue-sync-commit/pr`, `issue-dev-auto`, `issue-prep-auto`)
  each re-implement inline `case $PLATFORM` branching over GitHub/GitLab
  (sometimes Linear), duplicating logic and never reaching Jira.
- The agent roster (claude/gemini/cursor/codex/antigravity) is enumerated in
  four places (`services.yml`, `parallel_agent.yml`, `agents/config.py`,
  concrete `runners.py` subclasses); adding a vendor requires new Python.
- `skill-evolve` and `graphify` hardcode `claude -p` as their LLM backend.

The repo already contains the target pattern once: `lifecycle_providers.yml`
(consumed only by `lifecycle-run`) maps canonical statuses/tiers to
per-provider constructs for GitHub, GitLab, Linear, **and Jira** (Jira via the
pre-authenticated Atlassian MCP, zero bespoke auth). This design generalizes
that pattern.

The full per-skill inventory is in Appendix A.

## 2. Umbrella principles (apply to all four phases)

1. **Skills reference capabilities, never vendors.** A skill says "the issue
   tracker" / "the review CLI", resolved at runtime. Seams are role-named
   variables (`TRACKER_PROVIDER`, `EVOLVE_CLI`), per the pattern
   `llm-invoke-stdin` documents. Vendor names appear only in config and
   examples.
2. **Every roster is enumerated in exactly one config file.** Tracker
   providers in `tracker_providers.yml`; the agent fleet in one roster file
   (Phase 4 collapses today's four enumeration sites).
3. **Dispatchers front engines.** Skills call `tracker_ops.sh` / `git_ops.sh`
   verbs; existing wrappers (`linear_ops.sh`, gh/glab translation) become
   back-end engines that skills never invoke directly.
4. **Ordered access methods per provider: MCP → CLI → git → API.** Each
   provider entry declares its access methods as an ordered list. Resolution
   picks the first method that is (a) available in the execution context —
   hooks/scripts cannot reach MCP, so they start at CLI; (b) authenticated;
   and (c) supports the requested operation. Raw API is the last resort, must
   live inside the ops wrappers (never in a skill), and must route through the
   CLI's authenticated `api` subcommand (`gh api`/`glab api`) where one
   exists, so auth stays centralized. GitHub/GitLab currently have no MCP
   servers registered in `mcp_servers.yml`; precedence falls through to CLI
   until one is added. Linear's registered MCP moves ahead of its GraphQL
   wrapper for agent-context operations.
5. **Unverified provider paths are marked, not implied.** Each provider ships
   with a contract-test checklist; a provider added config-only is flagged
   `verified: false` until its checklist passes live. A skipped or
   unverifiable check never renders as a green pass.

## 3. Roadmap

Each phase is its own spec → plan → implement cycle. This document is the
umbrella plus the Phase 1 spec; Phases 2–4 get follow-up specs.

| Phase | Cluster | Core deliverable |
|---|---|---|
| 1 (this spec) | Tracker | `tracker_providers.yml` + `tracker_ops.sh`; migrate the issue/PM skills (7 full + 2 partial) |
| 2 | Forge/PR | Fill `git_ops.sh` gaps (`pr-close`, review-comment verbs); migrate the raw-`gh` PR skills; bot identities (Copilot/Jules/Palette/Bolt) move to a config list |
| 3 | CI | Platform detection + per-platform analysis semantics (GitHub Actions, GitLab CI) for the ci-* skills — most new logic, so it goes last |
| 4 | Agent fleet | Single agent-roster registry consumed by `env-check`/`config-audit`/`deploy-*` and `parallel_agent.py`; role-named CLI seams for `skill-evolve`/`graphify` |

**Architecture decision (chosen from three candidates):** registry as source
of truth, dispatcher as accelerator. A pure-shell dispatcher (candidate A)
would re-introduce bespoke Jira auth that the Atlassian MCP path avoids;
MCP-first-everything (candidate C) breaks hook-based skills, which run with no
agent context, and discards ~1,700 lines of working wrappers.

## 4. Phase 1 design: tracker abstraction

### 4.1 Registry — `configs/claude/config/tracker_providers.yml`

Evolves `lifecycle_providers.yml`, which is absorbed and removed (its sole
consumer, `lifecycle-run`, is re-pointed; canonical status/tier maps carry
over unchanged).

Per provider (`github`, `gitlab`, `linear`, `jira`):

- `access:` — ordered method list per Principle 4. Initial values:
  - `github: [cli, api]` (MCP prepended when a GitHub MCP server is registered)
  - `gitlab: [cli, api]`
  - `linear: [mcp, cli, api]` (`cli` = `linear_ops.sh` GraphQL engine)
  - `jira: [mcp]`
- `status_via:` — `label` (github, gitlab) vs `transition` (linear, jira),
  plus the canonical-status map (planned / in-progress / needs-review / done)
  carried over from `lifecycle_providers.yml` (key name and hyphenated status
  spelling kept verbatim for `lifecycle-run` compatibility).
- `tier_map:` — project/epic/issue/sub-issue construct names per provider.
- `mcp_tools:` — explicit MCP tool-name map where `access` includes `mcp`
  (jira today; linear once its MCP path is exercised).
- `verified:` — boolean per Principle 5, set true only after the contract
  matrix (§4.4) passes live.

**Canonical operation set** (derived from what the migrating skills actually
use — no speculative verbs): `issue-list`, `issue-view`, `issue-create`,
`issue-comment`, `issue-transition`, `issue-label`, `issue-close`,
`sub-issue-create`, `sub-issue-list`, `duplicate-mark`. Where a provider
lacks a native construct for an operation, the registry maps it to the closest
equivalent and documents the mapping (e.g. `duplicate-mark` is a native state
in Linear/Jira but maps to close-with-comment plus a `duplicate` label on
GitHub/GitLab).

**Provider detection**, in order:

1. Explicit override: `MANIFEST_TRACKER` env var, or a repo-level
   `.manifest-tracker` marker file containing the provider name.
2. Git-remote detection via existing `git_platform.sh` (github/gitlab).
3. User default: `default_provider:` key in `tracker_providers.yml` (how
   Linear/Jira users opt in globally).

A repo can host code on GitHub while tracking issues in Jira (override beats
remote detection).

### 4.2 Dispatcher — `configs/claude/scripts/tracker_ops.sh`

- Verb CLI mirroring the canonical operation set; `--provider` flag plus
  auto-detection per §4.1.
- Delegates to `git_ops.sh` (github/gitlab) and `linear_ops.sh` (linear) as
  engines. Skills stop calling `linear_ops.sh` directly.
- For an MCP-only provider reached from a shell context (e.g. Jira from a
  hook), exits with a distinct exit code and an `unsupported-in-context`
  message on stderr so hook skills fail open loudly (Principle 5). Agent
  context skills consult the registry and issue MCP tool calls instead.
- Repo conventions: `--help` (≤15 lines, exit 0, works before any
  config/dependency lookup), `err()` for error output, shellcheck-clean.

### 4.3 Skill migrations (7 full + 2 partial)

| Skill | Change |
|---|---|
| `issue-triage` | Linear-only → registry-driven; `linear_triage.yml` scoring generalizes to `tracker_triage.yml` (provider-neutral fields + per-provider overrides) |
| `issue-prioritize` | Delete inline `case $PLATFORM` block; call `tracker_ops.sh` verbs |
| `issue-sync-commit` | `issue_support.sh` re-pointed at `tracker_ops.sh`; stays fail-open |
| `issue-sync-pr` | Same as above |
| `issue-dev-auto` | Label workflow via canonical `issue-label`/`issue-transition`; drop direct `gh` calls |
| `issue-prep-auto` | Same as above |
| `lifecycle-run` | Re-pointed at renamed registry; behavior unchanged |
| `repo-clean` / `pr-review` (tracker portions only) | Issue-related steps use `tracker_ops.sh`; PR portions wait for Phase 2 |

Out of scope for Phase 1: `speckit-taskstoissues` (speckit system, GitHub-only
by design for now), all PR/forge verbs (Phase 2), CI skills (Phase 3).

### 4.4 Testing and verification

- **Contract matrix**: each canonical operation × each provider, run live
  against all four providers (GitHub, GitLab, Linear, Jira Cloud sandbox via
  Atlassian MCP — user has confirmed live access to all four). A provider's
  `verified: true` flag is set only when its column passes. The matrix is the
  acceptance checklist for implementation.
- **Unit tests**: bats coverage for dispatch, provider detection order, and
  the `unsupported-in-context` path, with stubbed `gh`/`glab` CLIs (stub with
  exit-127 shims rather than PATH subtraction, per repo lesson on merged-/usr
  CI runners).
- **Config validation**: `tracker_providers.yml` added to the yamllint set and
  the YAML syntax checks in CI.
- **Regression**: migrated skills re-verified on GitHub (the current daily
  driver) before the other providers, so no existing workflow regresses.

### 4.5 Error handling

- Unknown provider → `err()` + non-zero exit listing configured providers.
- Unauthenticated method → fall through to the next method in the `access:`
  list; if none remain, fail with a message naming the method(s) tried and the
  auth each requires. Never silently skip an operation.
- Hook contexts inherit fail-open semantics from `issue-sync-*` (a tracker
  failure never blocks a commit/PR), but the failure is logged with the
  distinct `unsupported-in-context` or auth-failure reason — never a silent
  green.

## 5. Open items deferred to later phases

- GitHub/GitLab MCP server registration (would promote MCP to the front of
  their `access:` lists) — Phase 2 decision.
- Bot identity config (Copilot/Jules/Palette/Bolt names in `pr-monitor` /
  `pr-triage-bots`) — Phase 2.
- `~/.claude/` as the hardcoded config home across ~40 skills. Functionally
  benign (symlinked into all agent homes) and invasive to change; documented
  as a known soft assumption, revisited in Phase 4.
- `ai-hooks-integration`'s independently-enumerated host list — Phase 4.

---

## Appendix A — Coupling inventory (audit of 2026-07-16, 98 skills)

### A.1 Hard-coupled to a specific agent/CLI

| Skill | Coupled to | Evidence |
|---|---|---|
| `skill-evolve` | Claude Code | Ingests `~/.claude/projects/**/*.jsonl`; evolves via `claude -p`; requires claude CLI login |
| `graphify` | Claude (default LLM backend) | Extraction through local `claude -p` (haiku), Claude Pro/Max auth |
| `env-check` | 5-agent roster (by design) | Per-agent auth checks (`claude auth status`, `gemini auth status`, `cursor --version`, …) |
| `config-audit` | 5-agent roster (by design) | Audits symlink parity across `.claude/`, `.cursor/`, `.gemini/`, `.codex/` |
| `deploy-retire-component` | Claude Code internals | `~/.claude/settings.json` `enabledPlugins`, `installed_plugins.json`, `claude plugin uninstall` |
| `deploy-reconcile` | Claude Code homes | Reconciles `~/.claude` + mirror symlinks |

### A.2 Hard-coupled to a specific app/service

| Skill | Coupled to |
|---|---|
| `issue-triage` | Linear only (`linear_ops.sh`, `linear_triage.yml`, `~/.config/linear/token`) |
| `pass-cli` | Proton Pass (`pass-cli` binary) — inherent, not a migration target |
| `pr-monitor` | GitHub + named bots (Copilot reviewer login, `@google-labs-jules` mention, `jules-trigger.yml`) |
| `pr-triage-bots` | GitHub + named bots (Jules/Palette/Bolt/Copilot author heuristics) |
| `pr-address-comments` | GitHub (`gh api …/pulls/…/comments`) |
| GitHub-only cluster | `ci-audit-triggers`, `ci-diagnose-drift`, `ci-harden-workflow`, `ci-reproduce-failure`, `reproduce-gated-ci-failure-locally`, `pr-clean-base`, `pr-reset-reapply`, `premise-verify`, `api-optimize-bulk`, `pr-merge-stacked`, `merge-stacked-pr-chain` |

### A.3 Partially abstracted

| Skill | Abstracted | Missing |
|---|---|---|
| `lifecycle-run` | GitHub/GitLab/Linear/Jira via `lifecycle_providers.yml` | The only skill using the registry |
| `issue-prioritize` | GitHub/GitLab/Linear via inline `case $PLATFORM` | Jira; branching duplicated in-skill |
| `repo-clean` | GitHub/GitLab via `git_ops.sh` | Falls back to raw `gh pr close`/`glab mr close` (git_ops lacks `pr-close`) |
| `pr-review` | GitHub/GitLab via `git_ops.sh`/`pr_review.sh` | Linear/Jira |
| `issue-dev-auto`, `issue-prep-auto` | GitHub/GitLab via `git_ops.sh` | 1–2 direct `gh` calls; no Linear/Jira |
| `issue-sync-commit`, `issue-sync-pr` | GitHub/GitLab via `issue_support.sh` | Inline platform branching; no Linear/Jira |
| `git-commit`, `ci-setup`, `plan-manage`, `shell-refactor` | Platform/agent abstractions where used | — |

### A.4 Agent-agnostic via `parallel_agent.py` (~20 skills)

`a11y-audit`, `ai-code-audit`, `code-audit`, `design-validate`, `docs-all`,
`docs-generate-diagrams`, `docs-improve`, `go-refactor`, `metrics-report`,
`node-refactor`, `python-refactor`, `shell-refactor`, `spec-audit-tasks`,
`spec-review`, `terraform-refactor`, `ux-review`, `security-refute-findings`,
`security-triage-findings`, `pr-smoke`, `ci-audit-triggers` (agent axis only).

### A.5 Fully agnostic (~42 skills)

Pure logic/shell/analysis skills with no agent or service dependency
(`branch-clean`, `data-validate-live`, `security-review-diff`,
`shell-audit-*`, `test-*`, `token-*`, etc. — full list in the audit
transcript). Many hardcode `~/.claude/` config paths only (soft assumption,
see §5).

### A.6 Existing abstraction infrastructure

- `git_platform.sh` — remote-URL platform detection (`github`|`gitlab`|`git`),
  overridable via `MANIFEST_GIT_PLATFORM`.
- `git_ops.sh` — verb dispatcher over `gh`/`glab` (issues, PRs, releases,
  labels). Gaps: no `pr-close`, no review-comment verbs, no Linear/Jira.
- `linear_ops.sh` — 1,276-line Linear GraphQL wrapper (raw curl +
  `LINEAR_API_KEY`), verb-compatible sibling of git_ops.
- `lifecycle_providers.yml` — 4-provider status/tier registry (absorbed by
  this design).
- `parallel_agent.py` + `agents/` — 5-backend agent orchestration; roster in
  config but runner classes hardcoded (Phase 4).
- `mcp_servers.yml` — 9 registered MCP servers (sentry, context7, linear,
  deepwiki, glean, google-dev-docs, atlassian, opentofu, apify), shared into
  Cursor/Gemini/Codex homes.
