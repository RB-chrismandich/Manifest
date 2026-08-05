# Agent/App-Agnostic Skills — Umbrella Architecture + Phase 1 (Tracker Abstraction)

**Date**: 2026-07-16
**Status**: DRAFT (pending user review)
**Driver**: Portability — anyone should be able to adopt Manifest with their own
stack (Jira instead of Linear, Codex instead of Claude) and skills just work.

---

## 1. Problem

An audit of all 98 skills in `.retired skill supply/skills/` found that agent coupling is
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

- **GitHub/GitLab MCP server registration — evaluated, deferred (Task 18,
  2026-07-17); CLI remains first.** Decision rule: adopt only if a server
  covers ≥ the `git_ops.sh` verb set (issue-view/list/create/comment/close/edit;
  pr-create/view/edit/list/review/approve/diff/checks/merge/close/comment/comments;
  pr-reopen/pr-update-branch/repo-admin-check/commit-checks/branch-protection;
  release-create/list; label-create/list/sync) with OAuth-capable auth.
  Findings (both candidates OAuth-capable, but both fail on verb coverage):
  - **GitHub official server** (`github/github-mcp-server`, README tool
    reference at commit fetched 2026-07-17): remote server supports OAuth
    (no static PAT required) via browser login. Covers issues fully
    (`issue_read`/`issue_write`/`list_issues`/`add_issue_comment`/`label_write`/
    `list_label`) and most PR ops (`create_pull_request`, `pull_request_read`
    incl. `get_diff`/`get_check_runs`/`get_status`, `update_pull_request`,
    `pull_request_review_write`, `merge_pull_request`,
    `update_pull_request_branch`). Gaps confirmed absent from the tool
    reference: no release-*create*/publish/delete tool (`releases` toolset is
    read-only — `get_latest_release`, `get_release_by_tag`, `list_releases`
    only); no branch-protection tool; no repo-admin-check equivalent (no
    permission-level/collaborator-role query, only `list_repository_collaborators`);
    no general commit-checks-by-SHA tool (`get_check_runs` is PR-scoped only,
    via `pull_request_read`). 4 of the 23 git_ops.sh verbs have no
    corresponding tool.
  - **GitLab**: no single "official first-party" server parallel to the
    GitHub one was adopted here — GitLab's own built-in MCP server
    (`https://<instance>/api/v4/mcp`, per GitLab docs
    `user/model_context_protocol/mcp_server_tools/`, fetched 2026-07-17) is
    OAuth-capable but exposes only ~20 tools skewed toward read/search
    (`create_issue`, `get_issue`, `create_merge_request`, `get_merge_request*`,
    `create_merge_request_note`, `search_labels`, pipeline read tools). It has
    no MR merge/approve/edit/close/reopen tool, no release tools at all, and
    no branch-protection tool — a larger gap than GitHub's. (Third-party
    community servers such as `zereight/gitlab-mcp` claim broader coverage
    but were out of scope: not first-party/vetted the way `atlassian` is in
    `mcp_servers.yml`, so adopting one wasn't pursued.)

  Per the decision rule, neither clears the bar — `mcp_servers.yml` and
  `tracker_providers.yml`'s `access:` lists are unchanged; `git_ops.sh`
  (CLI/API) remains the sole forge/PR-operations path. Full findings with
  sources: `.superpowers/sdd/task-18-report.md`.
- **Bot identity config — done (Task 17, 2026-07-17).** Added
  `configs/claude/config/review_bots.yml` (copilot, jules, palette, bolt);
  `pr-monitor`/`pr-triage-bots` now read it instead of hardcoding logins.
  Verified each entry against the live repo rather than guessing: copilot
  and jules have real, gh-confirmed `author_login`s; palette/bolt turned out
  to be **Jules personas with no distinct bot account** (their PRs are
  authored by the human account that invoked the session), so the registry
  correctly encodes `author_login: null` + `identified_by: title_prefix` for
  those two, and a follow-up fix pass corrected two live search-command bugs
  this surfaced (an AND-instead-of-OR title search, and a wrong `bolt-`
  vs. `bolt/` branch-prefix). Full evidence:
  `.superpowers/sdd/task-17-report.md`.
- **`~/.claude/` as the hardcoded config home — documented (Task 25,
  2026-07-17), not eliminated.** The four fleet-inspection skills
  (`env-check`, `config-audit`, `deploy-reconcile`, `deploy-retire-component`)
  now read the agent fleet from `agent_roster.yml` instead of hardcoding
  `claude`/`cursor`/`gemini`/`codex`/`antigravity` lists — antigravity in
  particular was previously missing from `config-audit`'s symlink and
  config-freshness checks entirely, and is now covered. `~/.claude/` itself
  remains the literal, unabstracted config home baked into these and ~40
  other skills' paths (`~/.claude/scripts/...`, `~/.claude/config/...`); this
  was always a documented soft assumption, not a Phase 4 deliverable to
  remove it, and it still holds. See "Two real deferred gaps" below for what
  Task 25 additionally surfaced.
- **`ai-hooks-integration`'s host list — confirmed still separately
  enumerated, by design.** This skill installs lifecycle hooks into
  Claude Code, Gemini CLI, Cursor, and OpenCode — a different axis (each
  tool's own hook/plugin mechanism) from `agent_roster.yml` (which enumerates
  backends for `parallel_agent.py`'s cross-verification). No Phase 1-4 task
  touched or was meant to touch it; the two enumerations describe genuinely
  different concepts and unifying them was never in scope. Left as-is.

### Two real deferred gaps discovered during implementation — CLOSED (Tasks A-D + goal-task-E close-out, 2026-07-17)

Both surfaced as explicit self-flagged concerns in their originating tasks'
reports, not silently dropped — and both are now substantially closed by a
follow-up goal ("the agent-fleet single source of truth", Tasks A-D plus
this close-out task, goal-task-E):

1. **`configs/claude/scripts/agents/cli.py`'s roster-awareness — CLOSED
   (Task D / goal-task-E, 2026-07-17).** `cli.py`'s provider selection,
   `--*-only`/`--no-*`/`--*-model` flags, and CLI-only rate-limiter/model
   wiring are now generated by looping over `agent_roster.yml`'s `agents:`
   map (`build_parser()`, `cli_only_provider_names()`,
   `resolve_enabled_agents()`, `resolve_cli_models()` in
   `configs/claude/scripts/agents/cli.py`) instead of being hardcoded per
   the 5 known providers. A 6th roster-only agent now gets working flags
   AND a real dispatched `CLIAgent`, with zero code change — including a
   HYPHENATED agent name (argparse mangles `--gemini-pro-only` to dest
   `gemini_pro_only`; `cli.py`'s `_dest()` helper re-derives that same
   mangling everywhere a roster name feeds a `getattr(args, ...)` lookup).
   Proven at three levels: unit
   (`tests/python/agents/test_cli.py::TestRosterDrivenSixthAgent` /
   `TestHyphenatedRosterAgentName`), cross-script integration
   (`tests/bats/agent_roster_integration.bats`: one shared
   `agent_roster.yml` fixture flows through `reconcile_core.py`,
   `check_status.sh`, `sync-skills.sh`, and `cli.py` with zero source
   edits), and a genuine live subprocess spawn (the same file's
   `--beta-only`/`--test-agent-only` tests: a real `python3
   parallel_agent.py` process, real argparse parsing, a real
   `asyncio.create_subprocess_exec` of a stub CLI — not the in-process
   `getattr()`/argparse reproduction the unit tests use).
2. **Backing scripts hardcoding the agent fleet — CLOSED (Tasks A-C /
   goal-task-E, 2026-07-17).** All four scripts named in the original
   finding now derive the fleet from `agent_roster.yml` instead of a
   hardcoded 5-agent list, each with a documented multi-tier fallback so a
   missing/unreadable registry degrades gracefully rather than to zero
   agents: `configs/claude/scripts/deploy_reconcile.sh` /
   `reconcile_core.py` (`load_fleet_tags()`, exposed via `--list-tags`),
   `configs/claude/scripts/check_status.sh` (`load_agent_roster_tsv()` +
   awk fallback, driving the Enabled Services/CLI Tools loops), and
   `configs/claude/scripts/sync-skills.sh` (`load_agent_roster_home_dirs()`
   + awk fallback, driving the secondary sync-target loop). Each has its
   own unit-level 6th-agent acceptance test
   (`tests/python/test_reconcile_policy.py::test_sixth_agent_extends_fleet_via_config_only`,
   `tests/bats/check_status.bats`, `tests/bats/sync_skills.bats`) plus the
   cross-script integration proof in
   `tests/bats/agent_roster_integration.bats` added by goal-task-E. Still
   NOT addressed (unchanged from the original finding, genuinely out of this
   goal's scope): `config-audit`'s §4 "MCP Configuration Consistency" check
   still names only `.claude`/`.cursor`/`.gemini` explicitly (no cited
   source for where codex/antigravity keep an MCP config file, so it wasn't
   guessed at).

   **Drift-guard hardening (goal-task-E, Part 2).** The original guard
   (`test_binary_matches_parallel_agent_cli_agents`) compared only `binary`
   between `agent_roster.yml` and `parallel_agent.yml`'s `cli_agents` block.
   The roster-driven scripts above each introduced their OWN hardcoded
   fallback copy of roster facts — `reconcile_core.py`'s
   `_DEFAULT_ROOT_TAGS`, `check_status.sh`'s tier-3 `ROSTER_NAMES` /
   `ROSTER_BINARIES` / `ROSTER_AUTH_CHECKS`, `sync-skills.sh`'s tier-3
   `ROSTER_NAMES` / `ROSTER_HOME_DIRS`, and `cli.py`'s `_FALLBACK_ROSTER` /
   `_MODEL_TIER_DEFAULTS` — each a fresh, independent silent-drift risk if
   `agent_roster.yml` changes without the matching fallback being updated.
   The guard now additionally covers, for the 5 known agents:
   `check_status.sh`'s fallback `binary` AND `auth_check` against the live
   registry, and `sync-skills.sh`'s fallback `home_dir` against the live
   registry (both in `tests/bats/agent_roster_drift_guard.bats`, which
   extracts the actual bash array literal out of each script's live source
   rather than re-encoding it), `reconcile_core.py`'s `_DEFAULT_ROOT_TAGS`
   name-set
   (`tests/python/test_reconcile_policy.py::test_default_root_tags_matches_real_registry_name_set`),
   and `cli.py`'s `_FALLBACK_ROSTER` / `_MODEL_TIER_DEFAULTS` name-sets
   (`tests/python/agents/test_cli.py::TestCliFallbackDriftGuard`). **What
   this does NOT eliminate**: the pattern itself of several independent
   hardcoded-default copies existing in the codebase — a fully single-sourced
   design (e.g. every fallback generated FROM `agent_roster.yml` at
   deploy/build time instead of each script carrying its own literal
   default) was out of scope for this close-out. Drift between an existing
   fallback and the registry is now test-caught, not silent — that is the
   actual guarantee delivered; a future contributor adding a brand-new
   hardcoded copy elsewhere would still need to add its own guard, same as
   today.

Both were legitimate follow-up-task candidates when originally deferred, not
gaps this program silently left unaddressed — and both are now closed to the
extent described above, with the residual scope (config-audit's MCP check,
and the drift-guard's per-copy-not-systemic coverage) called out explicitly
rather than implied to be fully resolved.

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
