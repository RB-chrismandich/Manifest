# Changelog

> Version history for the Manifest parallel agent orchestration framework

**Last Updated**: 2026-07-13

All notable changes are documented here in reverse chronological order.

---

## [Unreleased]

### Doc Concision Contract (docs-* skills)

- **`configs/claude/scripts/docs_lint.py`** — per-type line caps for a docs set,
  read from `configs/claude/config/doc_limits.yml`. Exit 1 when a doc is over
  cap; fluff phrases are advisory only (a wording blocklist that fails a build
  is one people route around). `wc -l` parity, code blocks included.
- **Caps**: hub 120, root README 200, tutorial/how-to 200, explanation 250,
  reference 400, diagram page 300 (max 4 diagrams). Generated files, vendored
  trees, and dated records (specs, plans, reports, ADRs) are exempt — rewriting
  a record to fit a cap falsifies it. In-file `<!-- doc-type: -->` and
  `<!-- doc-limit: N — why -->` overrides; a limit override without a rationale
  is a hard failure, same contract as help-coverage exemptions.
- **`configs/claude/references/doc-concision.md`** — the fan-out rule (split by
  subject into a hub plus sub-pages, never `-part-2`; caps apply recursively),
  the fluff list, and the rewrite order (cut before you split). Indexed in the
  Claude and Cursor Reference Indexes.
- **All four docs-* skills** now measure before and after and report a
  line-count delta instead of asserting improvement. `docs-improve` trades its
  100-point health score for the linter's numbers; `docs-generate-diagrams`
  moves Mermaid syntax traps to a loaded-on-demand reference. Skill bodies:
  616 → 359 lines.
- **Policy follows the code**: the three skills that run the linter have `Bash`
  un-forbidden (scoped to `docs_lint.py`), and `docs-improve` moves
  `subagents: never` → `conditional` because its unit of work is now an
  independently-capped topic directory, not one holistic score.
- **Edit-time enforcement, not CI.** `lint_on_edit_hook.sh` now runs the cap
  check on `.md` writes, so a doc that crosses its cap says so in-session where
  the fix is one edit — rather than at merge time, when it is already written
  and reviewed. Opt-in per repo (only fires where a `doc_limits.yml` or
  `.doc-limits.yml` is present, so unrelated projects are never nagged),
  reports only when over cap, advisory as ever. `docs_lint.py` is deliberately
  NOT wired into CI: the changed-file gate would fail unrelated PRs on the 10
  pre-existing over-cap docs.
- **Tests**: `tests/bats/docs_lint.bats` (19 cases) pins classification, cap
  arithmetic, override rationale enforcement, exempt handling, and the
  `**`-vs-`*` glob distinction that `fnmatch` would collapse.
  `lint_on_edit_hook.bats` gains 6 covering opt-in, silence-when-clean,
  per-type classification, `.mdc` exclusion, and non-mutation.

### Model-Routing Verification (class x model matrix)

- **`opus_attribution_report.py` is no longer Opus-only.** A hardcoded
  `if "opus" not in model: continue` meant no committed script could reproduce the
  baseline's own headline row (Fable 5 sub-agents: 4,531 requests, $919.32) — that
  figure came from ad-hoc analysis that was not kept, while the Reproduce section
  claimed otherwise. The filter is now `--models` (default `opus`, `all` to widen),
  and the report emits a **class x model matrix** with per-cell cost.
- **`--since <change-point> --models all` is the lever-verification query.**
  `subagent_policy.bats` T7/T8 prove `command_config.yml` *says* Sonnet; nothing
  proved a dispatch *ran* Sonnet. One command now answers it. First reading:
  283 sub-agent requests on Opus 5 in the change-point interval, so lever 1 is
  marked **declared, not landed** in `docs/MODEL-POLICY.md`.
- **Shared price table** `configs/claude/scripts/model_pricing.py` (`--json` to
  dump), used by both cost-reporting CLIs so their figures cannot diverge. An
  unknown model is reported **unpriced** and excluded from totals — never costed
  at $0. `token_cost_report.py` gained the per-model cost table that reproduces
  the baseline's $6,141.64 scope-correction figures.
- **Tests**: 7 new cases in `tests/python/test_measurement_reports.py` covering
  matrix cost math, unpriced-not-zero, `--models` filtering, and the
  cell-goes-to-zero verification query.

### Credit Measurement Baseline

- **Three measurement CLIs** in `configs/claude/scripts/` — `token_cost_report.py`,
  `skill_usage_report.py`, `opus_attribution_report.py`. All take `--since`/`--until`
  so a committed snapshot is reproducible against an append-only transcript corpus.
- **Corrected a 2.24x measurement error.** Prior credit figures counted JSONL *lines*,
  not API requests: Claude Code writes each content block of one response as its own
  `assistant` line and every sibling repeats the same `usage` object. Deduping by
  `requestId` (first value for input/cache fields, **max** for the cumulative
  `output_tokens`) puts the real total at 47,185 requests, not 105,728 — and Opus at
  16,873, not 41,527.
- **Dated baseline** in `docs/baselines/` with the Opus task-class attribution
  (98.04% classified) and a costed routing proposal. Headline findings: cache reads
  are 53% of Opus spend; per-turn model downgrades are net-**negative** (-$1,499)
  because caches are model-scoped; sub-agents are the only cache-neutral lever
  ($845, 13.8% of spend); Fable 5 is 39.9% of total spend on 18% of requests.
- **Sub-agent model-selection rule** documented in
  `configs/claude/references/sub-agent-dispatch.md`, including why the intuitive
  per-turn downgrade is rejected on evidence.

### Fixed

- **Duplicate PostToolUse hook.** `install_issue_hooks.sh` deduped by exact command
  string, so installing once from a repo clone and once from the deployed
  `~/.claude/scripts` copy registered the same hook twice and it fired twice on every
  matching tool call. Matching is now by script name.
- **Stale-clone drift was undetectable.** `deploy_stamp_check.sh` compared the clone
  against the deploy stamp, so a clone many commits *behind* its remote (stamp
  matching HEAD exactly) never warned. It now also checks the already-fetched
  remote-tracking ref — no `git fetch`, preserving the fail-open SessionStart design.
- **Git-invisible directories could deploy as skills.** A directory under
  `.skillshare/skills/` containing only ignored files (e.g. `__pycache__` left by a
  rename) is reported by git as ignored, never untracked, but `deploy_home_skills`
  rsyncs the filesystem. Directories without a `SKILL.md` are now warned about and
  excluded.
- **Five CLI defects** in the new measurement scripts, all found by probing and now
  covered by regression tests: an unparseable `--until` was silently ignored (leaving
  the scan unbounded at exit 0), a nonexistent `--root` returned a clean zero at exit 0,
  an empty result set raised a `ZeroDivisionError` traceback, an unwritable `--json`
  path raised a raw `FileNotFoundError`, and unbounded scan counters made committed
  snapshots drift on every regeneration.

### Added

- Exit-code and empty-result conventions for new Python CLI entry points in
  `docs/CODING_STANDARDS.md`; `--help` coverage for Python entry points in
  `tests/bats/help_coverage.bats`.

### Agent Frameworks Expansion

- **New Role-Agents** — Added 4 new high-precision role-agents with detailed operational
  execution rules, prompts, and validation criteria:
  - `context-chronicler`: Memory optimization utility with a strict JSON state checkpoint schema.
  - `compatibility-translator`: Cross-platform configuration sync engine (Cursor `.mdc`,
    Antigravity `agy`, Claude Code).
  - `performance-auditor`: Continuous CDDL critic verifying Big-O complexity, batching
    efficiency, and resource leak prevention.
  - `dependency-guardian`: Supply-chain security audit tool detecting typosquatting and
    restrictive licenses.
- **Auto-Sync & Parity** — Registered roles in the bootstrap configuration arrays, documented
  them in delegation policies, and regenerated all matching Cursor configurations automatically.

### specs/482 — Critic-Driven Development Loop (CDDL)

- **`/spec-implement-loop`** — sub-agent CDDL: developer writes; developer reviewer,
  QA critic, and architecture critic review until each approves with zero findings.
  Role prompts at `configs/claude/prompts/cddl/`.
- **CDDL sunset** — removed `manifest cddl` and the `cddl/` Python package; `cddl_loop.py`
  is a deprecation stub pointing at `/spec-implement-loop`.
- **Agent-agnostic synthesis** — low-consensus merge in `parallel-agent` uses any
  configured `cli_agents` provider (`synthesis.provider` / `SYNTH_PROVIDER` /
  `SYNTH_CLI`); default order prefers antigravity → cursor → gemini → codex → claude.
- **Cross-platform parity seams** — shared `agents/cli_invoke.py` for synthesis,
  `cddl_invoke.py` (CDDL critics on Gemini/Codex/Agy), and SkillClaw evolve
  (`EVOLVE_CLI` / `EVOLVE_PROVIDER`); `anthropic` moved to optional `uv --group claude`;
  Gemini hooks aligned with version-pin / spec-review / lint-on-edit; `/pr-smoke`
  orchestration probe tries the first available provider.
- **Shared infra** — `spec_review.sh` `discover_artifacts` now handles FILE
  targets (paired within their own layout tree); `audit_log.sh` gains a generic
  `AUDIT_LOG_FILE` env; deploy-reconcile now covers the `prompts/` namespace.

### specs/457 — Proactive Code Guardrails

- **Guardrail registry** — `knowledge_base.yml` seeded with 33 curated
  anti-pattern entries across 6 categories (`arch`, `async-state`,
  `error-handling`, `security`, `dependency`, `iteration`), each with severity,
  per-language detection cues, and a positive prevention rule; schema pinned by
  `knowledge_base_registry.bats`.
- **Write-time prevention** — "Proactive Coding Guardrails (always on)" digest
  in all deployed guides (budget-checked) with full detail in
  `references/antipatterns.md`; `code-quality` now flags registry anti-patterns
  inline as non-blocking advisory feedback.
- **`/ai-code-audit`** — dedicated seven-pass audit skill (inventory →
  architecture → async/state → security → logic → quality → iterative
  regression) with evidence-traced findings, adversarial cross-verification of
  critical/high candidates, and APPROVED/NEEDS_REVIEW/BLOCKED verdicts; smoke
  harness at `tests/fixtures/audit-seeded/`.
- **Capture loop** — `learning_capture.sh add` accepts `--severity`,
  `--detection-cue`, `--prevention-rule`, `--provenance`;
  `antipattern-detect`/`learning-loop` captures become active in guidance and
  audits in one step.

---

## [2026-06]

### specs/368 — Deploy Reconciliation Review (shipped 2026-06-30, PR #443)

- **`/deploy-reconcile`** — compares what Manifest deployed into the assistant
  homes (`~/.claude` + mirrors) against what the project would deploy, listing
  orphaned deployed items KEEP/REMOVE (`deploy_reconcile.sh` + `reconcile_core.py`,
  realpath-deduped `skills/` + `config/` namespaces).
- Preview by default; removal is opt-in and recoverable (timestamped backup,
  never a hard delete).

### specs/367 — Sub-Agent Dispatch Guidance (shipped 2026-06-30, PR #441)

- **One documented home for dispatch rules** — `references/sub-agent-dispatch.md`
  (native Task sub-agents vs `parallel_agent.py`, the ≥3-independent-units
  threshold, no recursion, cross-platform fallback); skills link there instead of
  restating the rules.
- Every skill carries a `subagents: always|conditional|never` disposition in
  `command_config.yml` `tool_policies`, enforced by `subagent_policy.bats`.

### specs/365 — Codified State-Gated Dev Lifecycle (shipped 2026-06-30, PR #432)

- **`/lifecycle`** drives a feature/issue through the codified
  specify→…→verify phases with hard phase-gating; entry is a ticket URL/issue
  key, and the Verify gate requires a smoke test.

### specs/366 — Coding Standards & No-Bypass CI Gate (shipped 2026-06-29, PR #440)

- **`docs/CODING_STANDARDS.md`** — per-language standards with explicit
  enforcement layers; `lint_on_edit_hook.sh` gives edit-time lint feedback.
- **Changed-file pre-commit gate in CI** — the full hook suite runs on every
  file a PR touches, with no bypass path.

### specs/364 — Graphify Integration (shipped 2026-06-29, PR #433)

- **`/graphify`** maps a codebase, docs set, or GitHub repo into a queryable
  knowledge graph (`graph.html`, `GRAPH_REPORT.md`, `graph.json`); the
  `graphify` CLI is installed by bootstrap behind
  `--enable-graphify`/`--disable-graphify` (default: enabled).
- Managed *tool*, not an orchestration agent — never part of
  `parallel_agent.py` consensus.

### specs/363 — Smoke-Test Orchestrator (shipped 2026-06-28, PR #431)

- **smoke-orchestrator skill + `smoke_test.py`** — catalog-driven smoke tests
  (`smoke-catalog/`) with `append`/`run`/`list`/`prune`; UI steps run via
  `mode: agent` (browser-use).
- **`/browser-test` deprecated** — superseded by the orchestrator, with a
  documented migration path.

### specs/362 — Command Discovery & Workflow Guidance (shipped 2026-06-22, PR #396)

- **`/help` command discovery** — a read-only skill that lists and searches every
  command by category with a one-line description + when-to-use cue, marking
  commands unavailable in the current environment. Ranked, deterministic, offline.
- **Generated, drift-free `docs/COMMANDS.md`** — `command_catalog.py` builds a
  machine catalog from `SKILL.md` frontmatter (the single source of truth);
  `generate_commands_doc.py` renders it and `--check` fails CI on drift (FR-004).
- **Curated category taxonomy** (`command_categories.yml`) — 8 categories assigned
  via frontmatter > overrides map > `uncategorized` (no mass SKILL.md rename).
- **Event-driven, one-shot workflow hints** (`guidance_hint.py` +
  `hint_registry.yml`) at recognized moments (pre-commit, PR-open, refactor-start,
  high-context), deduped + priority-ordered, fail-open, never added to
  always-loaded context. Delivered via Claude Code + Gemini hooks; Codex/Antigravity
  use a documented standing-line fallback in `AGENTS.md`.
- **Tunable best-practice reminders** — `guidance.yml` shipped defaults (all on) ←
  gitignored `~/.claude/config/guidance_local.yml` override (local wins); global +
  per-category opt-out, verbosity, and rate-limiting. A single opt-out never dirties
  the tracked tree (SC-004).
- **Cross-platform parity** — compact, description-less command index injected into
  `GEMINI.md`/`AGENTS.md` (budget-bounded, drift-checked) and a Cursor
  `commands-index.mdc` rule; full descriptions stay in `/help` and `docs/COMMANDS.md`.

### specs/003 — Skill Library Consolidation & Repo Health (shipped 2026-06-11, PRs #289 #291 #293 #294 #296)

- **Skill library consolidated 81 → 69** (specs/003) — six duplicate clusters
  resolved (five merged, one cross-anchored): `address-pr-comments` (absorbs 2), `session-memory-compress`
  (absorbs 1), `live-data-validation` (absorbs 3, mode subsections), new
  `verify-premise` (absorbs 5), new `retire-component-cleanup` (absorbs 3);
  `reset-reapply-clean-pr`/`clean-pr-from-stale-base` gain mutual decision
  anchors. Evolve's `{{LIBRARY}}` prompt now carries `name — description`
  lines so duplicates are suppressed at the source.
- **Prune-on-deploy** — `deploy_home_skills` prunes previously-deployed skills
  removed from the source of truth via a `.deployed-skills` manifest; skills
  added by other tools are never touched (does NOT reintroduce the PR #255
  blind `--delete` data-loss bug).
- **Docs accuracy** — command tables unified to canonical `docs/COMMANDS.md`
  (33 rows mirrored byte-identically in CLAUDE.md, AGENTS.md,
  configs/claude/CLAUDE.md); skill counts corrected to 69.
- **Tests & CI (US4)** — behavioral bats suites for learning_capture,
  check_status, generate_cursor_rules, browser_test (+ browser-use
  bootstrap toggle); CI pins matching pre-commit + dependency caching;
  cursor-rules drift check now catches untracked files.
- **Hygiene (US5)** — specs/002 marked Delivered; canonical `err()`
  convention swept across configs/claude/scripts/; `--help` on all
  user-facing scripts (+ help_coverage.bats); records/ and
  package-lock.json untracked and gitignored.

### Added

- **SkillClaw promote audit log + live status/ETA** (PR #284) — new `skillclaw_audit.py`
  writes an append-only `~/.skillclaw/promote.log` (JSONL history, self-trimmed to
  ~50 runs) and a live `status.json` snapshot. `skillclaw_promote.sh --status`
  reports where a run is and a rough ETA; the evolve stage prints per-chunk
  progress. Fail-open: audit I/O never blocks a promote run.
- **45 SkillClaw-evolved skills** (PR #285) — promoted via the proxy-free
  evolve pipeline, one commit per skill.
- **spec-review reviewer: Gemini → agy (Antigravity)** (PR #282) — seam renamed
  to `SPEC_REVIEW_CLI`, default reviewer `agy`.

### Fixed

- **label_sync.sh Bash 3.2 `set -u` crash** — empty `team_args[@]` expansion
  guarded; sync no longer aborts after the first label.
- **SkillClaw promote review fixes** (PRs #284/#285) — truthful `run_start`
  config, dropped-candidate reasons, evolve `stage_start` on empty sessions,
  ingest count in `stage_end`, `trim()` clamp.

## [2026-05]

### Added

- **`agents/` package** (PR #260) — `parallel_agent.py` modularized into a proper Python package:
  `agents/cli.py`, `config.py`, `orchestrator.py`, `runners.py`, `synthesis.py`, `validation.py`
- **`sync-skills` CLI command** (PR #258) — native binary at `~/.local/bin/sync-skills` for daily
  skill development; deploys `.skillshare/skills/` to all home targets with `MANIFEST_ROOT` support
- **CI drift guard** (PR #259) — detects stale cursor rules and config drift in CI
- **speckit integration** — spec/plan/task workflow tooling initialized

### Changed

- **Skillshare centralization** (PR #255) — `.skillshare/skills/` is now the source of truth;
  `configs/claude/skills/` is a compatibility symlink; bootstrap uses additive rsync (no `--delete`)
- **CLAUDE.md tiered** (PR #255) — core guide + reference index pattern adopted

### Removed

- **`parallel_agent.sh`** (PR #257) — retired in favor of `parallel_agent.py`; all 56+ call sites
  updated; -1939 lines

### Fixed

- **rsync `--delete` data-loss bug** (PR #255) — removed `--delete` from skill deploy to prevent
  wiping home skills on bootstrap

---

## [2026-02]

### Added

- **Codex CLI support** — fourth agent alongside Cursor, Gemini, Claude
- **Python parallel agent** (PR #49) — feature parity with shell script: async orchestration,
  structured JSON logging, Tier 1/2 validation engine, consensus scoring, Rich streaming display
- **`browser-test` skill** — AI-powered E2E testing via browser-use YAML prompts
- **GitLab CI** and multi-language prompt templates

### Fixed

- Command injection in `CursorAgent` (CWE-78)
- `git_ops.sh` GitLab flag translation for `pr-create`
- MCP re-registration guard (skip when already configured)

---

## [2026-01]

### Added

- Unified label management across GitHub, GitLab, and Linear (`labels.yml`, `label_sync.sh`)
- `issue-prioritize` and `issue-triage` commands with Linear integration
- Bootstrap modularization (`bootstrap/lib/`) with hookable module system
- Production-grade permission templates (Django, Express, Go microservices, Python monorepo)
- `docs/` documentation hub with Getting Started, Configuration, Troubleshooting, Architecture

### Changed

- Deployment configs moved to `configs/` to prevent session config override

---

## Related Documents

- [README.md](README.md) — Project overview
- [docs/README.md](docs/README.md) — Documentation hub
