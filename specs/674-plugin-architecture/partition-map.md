# Partition Map — 108 skills → 10 candidate plugins
**Produced by**: three independent classifiers (subject / user-journey / runtime-coupling lenses) reconciled by a fourth agent · **Measured**: 2026-07-30
**Status**: MAP, not a shipping plan. See [spec.md](spec.md) for what to actually ship.

> ⛔ **The 10-way split does not ship. 9 bundles do** — see [cutover-plan.md](cutover-plan.md) T3.1
> and *Explicitly dropped from scope*. Two of the ten are dissolved, both of them the ones this
> map's own agreement scores flag at **zero cross-lens agreement**:
>
> - **`manifest-data-pipelines` (0/6) — DELETED.** One lens only, six ~30-line field notes, no
>   orchestrator, invisible in a marketplace. Members scatter to their own subject-lens votes.
> - **`manifest-ci` (0/5) — DISSOLVED.** Its only cohesion was shared use of `ci_platform.sh`,
>   which is **void under the cutover**: no plugin ships `scripts/`, and bootstrap owns
>   `~/.claude/scripts/ci_platform.sh`, so all four CI skills reach it identically from any
>   bundle. The pwn-request pair (`ci-audit-triggers` + `ci-harden-workflow`) moves to
>   `manifest-security` — which is where this map's own dispute table already rated the subject
>   tiebreak `low` confidence.
> - **`manifest-runtime-ops` (0/6) — KEPT**, renamed **`manifest-ops`**, grown to 11. This
>   reverses spec.md's "never ship" line.
> - **`manifest-graphify` (1 skill) — ADDED**, so `--enable/--disable-graphify` keeps a real
>   install/uninstall target.
>
> Counts as shipped: manifest-code-quality **22** (not 19; 23 minus graphify, which leaves for its own bundle), manifest-security **10** (not 8),
> manifest-ops **11** (not 6). Sizes below are the map's, not the shipping manifest's.
> Rationale: "never ship this bundle" and "every skill must have a home" are only compatible
> under a hard cutover if the weak bundles are dissolved deliberately rather than shipping one
> whose own map calls it "the first I would delete".
**Agreement**: 69/108 skills (64%) placed identically by all three lenses. Perfect or near-perfect agreement: stitch-design (18/18), manifest-forge (18/18), manifest-docs (4/4), manifest-spec-planning (6/7), manifest-security (6/8). Zero agreement: manifest-ci (0/5), manifest-runtime-ops (0/6), manifest-data-pipelines (0/6). Partial: manifest-code-quality (8/19), manifest-workspace (9/17). CAVEAT: the coupling lens's JSON was truncated mid-assignment at `pr-triage-bots`; its remaining 89 placements were reconstructed from its plugin rationales and stated sizes (19/5/13/8/4/6/18/20/15 = 108, which reconciles exactly). Every coupling placement after pr-triage-bots is inference, not testimony, and the disputes below flag where that inference is load-bearing.

---

## `manifest-forge` — 18 skills

Everything that talks to a code forge: commits, branches, PR/MR state and review threads, plus the issue tracker (GitHub, GitLab, Linear, Jira) — triage, prioritization, labels, status sync, and autonomous issue-to-PR development.

**Cross-lens support**: All three lenses. Subject and journey both wanted to SPLIT this, but at incompatible seams (subject cuts git|issue; journey cuts plan|ship), so their splits cancel. Coupling forbids any cut: tracker_ops.sh and issue_support.sh both shell git_ops.sh through SCRIPT_DIR, so splitting duplicates ~2,400 lines. Merged by default, not by agreement — see structuralProblems.

**Hooks**: issue_support_hook.sh (PostToolUse|Bash — routes a successful PR-create or git commit to issue_support.sh sync-pr / sync-commit), native git post-commit block (# >>> issue-support >>>, project scope, installed by install_issue_hooks.sh --native)

**MCP servers**: `linear`, `atlassian`

**Shared scripts**: `git_ops.sh`, `git_platform.sh`, `tracker_ops.sh`, `tracker_registry.py`, `linear_ops.sh`, `issue_support.sh`, `label_sync.sh`, `branch_clean.sh`, `pr_review.sh`, `audit_log.sh`, `auto_issue_dev.sh`, `loop_lock.sh`, `merge_decision.sh`, `pr_merge_loop.sh`, `lifecycle.sh`, `install_issue_hooks.sh`, `learning_capture.sh (git-commit only — 1 of 3 copies)`, `manifest parallel-agent (external CLI)`

**User-invoked entry points** (13): `/git-commit`, `/pr-review`, `/pr-monitor`, `/pr-address-comments`, `/pr-merge-stacked`, `/pr-triage-bots`, `/repo-clean`, `/branch-clean`, `/issue-triage`, `/issue-prioritize`, `/issue-prep-auto`, `/issue-dev-auto`, `/lifecycle-run`

> These stay as **skills**, not `commands/*.md`. `commands/` is a legacy format;
> skills and commands load identically. See spec.md §'Commands'.

| Skill | Self-contained | Deps |
|---|:--:|---|
| `branch-clean` | ✅ | — |
| `git-commit` | — | `git_ops.sh`, `manifest parallel-agent` |
| `git-find-artifact` | ✅ | — |
| `issue-dev-auto` | — | `git_ops.sh` |
| `issue-prep-auto` | — | `git_ops.sh`, `tracker_ops.sh` |
| `issue-prioritize` | — | `linear_ops.sh`, `manifest parallel-agent`, `tracker_ops.sh` |
| `issue-sync-commit` | — | `issue_support.sh` |
| `issue-sync-pr` | — | `issue_support.sh` |
| `issue-triage` | — | `manifest parallel-agent`, `tracker_ops.sh` |
| `lifecycle-run` | — | `git_ops.sh`, `label_sync.sh`, `linear_ops.sh` |
| `pr-address-comments` | — | `git_ops.sh` |
| `pr-clean-base` | — | `git_ops.sh` |
| `pr-merge-stacked` | — | `git_ops.sh` |
| `pr-monitor` | — | `git_platform.sh` |
| `pr-reset-reapply` | — | `git_ops.sh` |
| `pr-review` | — | `git_ops.sh`, `git_platform.sh`, `manifest parallel-agent` |
| `pr-triage-bots` | — | `manifest parallel-agent` |
| `repo-clean` | — | `git_ops.sh`, `git_platform.sh`, `manifest parallel-agent` |

## `manifest-spec-planning` — 7 skills

Planning artifacts: spec.md / plan.md / tasks.md (speckit or superpowers layout) and ~/.claude/.plans entries — consistency review, task-completion audit, trade-off records, design validation, critic-gated implementation.

**Cross-lens support**: Subject and journey agree on the cluster (journey folds it into feature-lifecycle alongside issue grooming); coupling names it separately on exclusive ownership of spec_review.sh + cddl_invoke.py + prompts/cddl/. 6 of 7 unanimous.

**Agents**: `executor`, `mech-executor`, `verifier`

**Hooks**: spec_review.sh --silent (PostToolUse|Write|Edit)

**Shared scripts**: `spec_review.sh`, `cddl_invoke.py`, `prompts/cddl/`, `git_ops.sh (plan-manage — 2nd of 3 copies)`, `manifest parallel-agent (external CLI)`

**User-invoked entry points** (4): `/plan-manage`, `/spec-review`, `/spec-audit-tasks`, `/spec-implement-loop`

> These stay as **skills**, not `commands/*.md`. `commands/` is a legacy format;
> skills and commands load identically. See spec.md §'Commands'.

| Skill | Self-contained | Deps |
|---|:--:|---|
| `design-validate` | — | `manifest parallel-agent` |
| `plan-manage` | — | `git_ops.sh`, `manifest parallel-agent` |
| `premise-verify` | ✅ | — |
| `spec-audit-tasks` | — | `manifest parallel-agent` |
| `spec-decide-tradeoffs` | ✅ | — |
| `spec-implement-loop` | — | `parallel_agent.py` |
| `spec-review` | — | `manifest parallel-agent` |

## `manifest-code-quality` — 19 skills

Source code that already exists: per-language refactor roadmaps, constitution audit and remediation, AI-defect audits, codebase comprehension, project scaffolding and verification gates, and the shell/CLI/test craft lessons that fire while code is being written.

**Cross-lens support**: All three lenses name a code-quality plugin, but only 8 of 19 members are unanimous. The five <lang>-refactor skills, code-audit-constitution and the two shell-audit lessons are settled; the test-craft and verification members are contested three ways.

**Agents**: `scout`, `Explore`

**Hooks**: constitution_hook.py (PreToolUse|Read|Write|Edit — injects CON-001..013, language ceilings and live per-file measurements), lint_on_edit_hook.sh (PostToolUse|Write|Edit — shellcheck/ruff/yamllint/markdownlint dispatch, advisory)

**MCP servers**: `context7`, `deepwiki`, `opentofu`

**Shared scripts**: `constitution_check.py + constitution/ package`, `code_constitution.yml`, `constitution_baseline.json`, `learning_capture.sh (10 consumers here — 2nd of 3 copies)`, `smoke_test.py`, `git_ops.sh (shell-refactor stray — 3rd of 3 copies)`, `manifest parallel-agent (external CLI)`, `semgrep (external CLI)`

**User-invoked entry points** (11): `/python-refactor`, `/node-refactor`, `/go-refactor`, `/shell-refactor`, `/terraform-refactor`, `/code-audit-constitution`, `/ai-code-audit`, `/project-verify`, `/project-scaffold`, `/graphify`, `/smoke-manage`

> These stay as **skills**, not `commands/*.md`. `commands/` is a legacy format;
> skills and commands load identically. See spec.md §'Commands'.

| Skill | Self-contained | Deps |
|---|:--:|---|
| `ai-code-audit` | — | `manifest parallel-agent` |
| `antipattern-detect` | ✅ | — |
| `cli-audit-help` | ✅ | — |
| `code-audit-constitution` | — | `constitution_check.py`, `manifest parallel-agent` |
| `false-green-check-audit` | ✅ | — |
| `go-refactor` | — | `manifest parallel-agent` |
| `graphify` | ✅ | — |
| `llm-invoke-stdin` | ✅ | — |
| `node-refactor` | — | `manifest parallel-agent` |
| `project-scaffold` | ✅ | — |
| `project-verify` | ✅ | — |
| `python-refactor` | — | `manifest parallel-agent` |
| `shell-audit-errexit` | ✅ | — |
| `shell-audit-pipefail` | ✅ | — |
| `shell-refactor` | — | `git_ops.sh`, `manifest parallel-agent` |
| `smoke-manage` | ✅ | — |
| `terraform-refactor` | — | `manifest parallel-agent` |
| `test-pin-bug` | ✅ | — |
| `test-vary-fixtures` | ✅ | — |

## `manifest-ci` — 5 skills

> ⛔ **DISSOLVED — does not ship.** 0/5 cross-lens agreement. Its only cohesion was shared use of
> `ci_platform.sh`, which is void under the cutover (no plugin ships `scripts/`; bootstrap owns
> `~/.claude/scripts/ci_platform.sh`, reachable identically from any bundle). `ci-audit-triggers`
> + `ci-harden-workflow` → `manifest-security`; the rest follow their subject-lens votes.

CI pipelines as an artifact: scaffolding workflows, auditing attacker-influenceable triggers, hardening privileged jobs, diagnosing config drift, reproducing a failing job locally.

**Cross-lens support**: Subject (inside a larger ci-testing class) and coupling (exclusive ci_platform.sh binding four of the five) agree this is one unit. Journey shreds it across three plugins — ci-setup to deploy-ops, the two diagnostics to ship-it, the two security ones to security-review. Zero unanimous members; kept whole because ci_platform.sh binds them and journey is the outlier.

**Shared scripts**: `ci_platform.sh`, `git_platform.sh (2nd copy — stateless 63-line detector, the cheapest duplication in the corpus)`

**User-invoked entry points** (2): `/ci-setup`, `/ci-audit-triggers`

> These stay as **skills**, not `commands/*.md`. `commands/` is a legacy format;
> skills and commands load identically. See spec.md §'Commands'.

| Skill | Self-contained | Deps |
|---|:--:|---|
| `ci-audit-triggers` | — | `manifest parallel-agent` |
| `ci-diagnose-drift` | ✅ | — |
| `ci-harden-workflow` | ✅ | — |
| `ci-reproduce-failure` | ✅ | — |
| `ci-setup` | — | `git_platform.sh` |

## `manifest-security` — 8 skills

Security findings and threat surfaces: source-to-sink diff review, adversarial refutation of candidate findings, LLM/MCP/proxy sinks, and network-ACL review of exposed services.

**Cross-lens support**: All three lenses; 6 of 8 unanimous. The refutation pair (security-triage-findings / security-refute-findings) consumes a candidate-findings list that exists nowhere else in the corpus — the strongest artifact boundary in the partition.

**Agents**: `security-executor`

**Shared scripts**: `manifest parallel-agent (external CLI)`, `semgrep (external CLI)`

**User-invoked entry points** (2): `/security-review-diff`, `/mcp-audit`

> These stay as **skills**, not `commands/*.md`. `commands/` is a legacy format;
> skills and commands load identically. See spec.md §'Commands'.

| Skill | Self-contained | Deps |
|---|:--:|---|
| `code-audit` | — | `manifest parallel-agent` |
| `docker-audit-firewall` | ✅ | — |
| `llm-audit-traversal` | ✅ | — |
| `mcp-audit` | ✅ | — |
| `security-harden-proxy` | ✅ | — |
| `security-refute-findings` | — | `manifest parallel-agent` |
| `security-review-diff` | ✅ | — |
| `security-triage-findings` | — | `manifest parallel-agent` |

## `manifest-docs` — 4 skills

Read code, write the documentation tree: README, Diataxis-shaped docs/ pages, Mermaid architecture diagrams, and the one-pass refresh over all three.

**Cross-lens support**: Unanimous, 4/4 — the only plugin with zero disputed members. docs-all is literally an umbrella over the other three, and docs_lint.py (447L) is consumed by nothing outside it.

**Shared scripts**: `docs_lint.py`, `manifest parallel-agent (external CLI)`

**User-invoked entry points** (4): `/docs-all`, `/docs-improve`, `/docs-improve-readme`, `/docs-generate-diagrams`

> These stay as **skills**, not `commands/*.md`. `commands/` is a legacy format;
> skills and commands load identically. See spec.md §'Commands'.

| Skill | Self-contained | Deps |
|---|:--:|---|
| `docs-all` | — | `manifest parallel-agent` |
| `docs-generate-diagrams` | — | `manifest parallel-agent` |
| `docs-improve` | — | `manifest parallel-agent` |
| `docs-improve-readme` | ✅ | — |

## `stitch-design` — 18 skills

The Stitch design pipeline and the frontend surface on either side of it: prompt enhancement, screen generation, design systems, DESIGN.md authoring and extraction, static HTML capture, React / React Native / Vite output, walkthrough video, plus the a11y / UX / performance audits that close the loop.

**Cross-lens support**: Unanimous, 18/18 — the strongest agreement in the corpus, and all three lenses independently flagged the SAME discomfort (a11y-audit, ux-review and performance-check need no Stitch account). Named stitch- rather than manifest- because the 15 Stitch skills are vendored from an external source; a manifest- prefix would imply provenance this repo does not have.

**MCP servers**: `stitch`

**User-invoked entry points** (10): `/generate-design`, `/upload-to-stitch`, `/code-to-design`, `/extract-static-html`, `/extract-design-md`, `/react-components`, `/remotion`, `/a11y-audit`, `/ux-review`, `/performance-check`

> These stay as **skills**, not `commands/*.md`. `commands/` is a legacy format;
> skills and commands load identically. See spec.md §'Commands'.

| Skill | Self-contained | Deps |
|---|:--:|---|
| `a11y-audit` | — | `manifest parallel-agent` |
| `code-to-design` | ✅ | — |
| `design-md` | ✅ | — |
| `enhance-prompt` | ✅ | — |
| `extract-design-md` | ✅ | — |
| `extract-static-html` | ✅ | — |
| `generate-design` | ✅ | — |
| `manage-design-system` | ✅ | — |
| `performance-check` | ✅ | — |
| `react-components` | ✅ | — |
| `react-native` | ✅ | — |
| `react-vite-dashboard` | ✅ | — |
| `remotion` | ✅ | — |
| `shadcn-ui` | ✅ | — |
| `stitch-loop` | ✅ | — |
| `taste-design` | ✅ | — |
| `upload-to-stitch` | ✅ | — |
| `ux-review` | — | `manifest parallel-agent` |

## `manifest-workspace` — 17 skills

Manifest's own environment and the agent itself: deployed-home auditing and reconciliation, hook plumbing, command discovery, credential retrieval, token/metrics telemetry, session checkpointing and compaction, the knowledge base, and skill/prompt authoring.

**Cross-lens support**: All three lenses name this cluster; 9 of 17 unanimous. Journey and coupling agree the Manifest-specific environment skills (env-check, config-audit, deploy-reconcile, ai-hooks-integration) belong beside session hygiene rather than beside generic app deployment; subject files them under a broader machine-state class.

**Agents**: `compatibility-translator`, `context-chronicler`

**Hooks**: subagent_model_default.py (PreToolUse|Agent — injects model: sonnet into unpinned dispatches), block_cwd_delete.py (PreToolUse|Bash — the only blocking hook Manifest ships), guidance_hint.py (PreToolUse|Bash — hint_registry.yml routing, rate-limited), deploy_stamp_check.sh (SessionStart — deploy-freshness nudge), token-conserve UserPromptSubmit echo

**MCP servers**: `glean`

**Shared scripts**: `apm_domains_lib.sh + apm_dev_sync.sh + apm_ownership_report.sh + apm_ungate_domain.sh + apm_drift_report.sh + apm_install_verify.sh + apm_publish_gate.sh + apm_hash_lib.sh`, `deploy_reconcile.sh + reconcile_core.py`, `check_status.sh`, `command_catalog.py`, `generate_commands_doc.py + generate_cursor_rules.sh + generate_cursor_agents.py`, `skillclaw_{ingest,evolve,audit,promote,scrub}`, `deploy_stamp_check.sh`, `emdash_inherit_check.sh`, `run_pr_regression.sh (CI mirror)`, `learning_capture.sh (learning-capture — 3rd of 3 copies)`, `manifest parallel-agent (external CLI)`

**User-invoked entry points** (12): `/env-check`, `/config-audit`, `/deploy-reconcile`, `/help`, `/metrics-report`, `/token-benchmark`, `/session-checkpoint`, `/token-conserve`, `/memory-compress`, `/pr-smoke`, `/skill-evolve`, `/prompt-optimize`

> These stay as **skills**, not `commands/*.md`. `commands/` is a legacy format;
> skills and commands load identically. See spec.md §'Commands'.

| Skill | Self-contained | Deps |
|---|:--:|---|
| `ai-hooks-integration` | ✅ | — |
| `automation-rework-breakeven` | ✅ | — |
| `config-audit` | — | `parallel_agent.py` |
| `deploy-reconcile` | ✅ | — |
| `env-check` | — | `manifest parallel-agent`, `parallel_agent.py` |
| `help` | ✅ | — |
| `learning-capture` | ✅ | — |
| `memory-compress` | ✅ | — |
| `metrics-report` | — | `manifest parallel-agent` |
| `pass-cli` | ✅ | — |
| `pr-smoke` | — | `manifest parallel-agent` |
| `prompt-optimize` | ✅ | — |
| `session-checkpoint` | ✅ | — |
| `skill-evolve` | ✅ | — |
| `test-isolate-ambient` | — | `parallel_agent.py` |
| `token-benchmark` | ✅ | — |
| `token-conserve` | ✅ | — |

## `manifest-runtime-ops` — 6 skills

> ✅ **KEPT, renamed `manifest-ops`, grown to 11.** Reverses spec.md's "never ship
> `manifest-runtime-ops` (0/6 unanimous)". Zero cross-lens agreement made it unshippable as an
> *optional* bundle; under a hard cutover every skill must have a home, so the choice is not
> "ship it or not" but "which bundle absorbs these" — and no other bundle wanted them.

A deployed or about-to-be-deployed service: validating config with the app's own parser, debugging the app's own ${VAR} substitution layer, probing internal Docker networks, classifying post-deploy drift, retiring daemons/sockets/plugins, and pinning the dependency versions that define the build.

**Cross-lens support**: Subject (manifest-environment) and journey (manifest-deploy-ops) agree on every member; coupling has no signal — it scatters four of the six into its admitted 'recipes' residue and pulls version-pin into security on version_pin.sh ownership. Zero unanimous members, 2-of-3 on all six.

**Agents**: `dependency-guardian`

**Hooks**: version_pin_hook.sh (PostToolUse|Write|Edit — requirements*.txt, compose, Dockerfile only; warn-only)

**MCP servers**: `sentry`

**Shared scripts**: `version_pin.sh`, `version_pin_hook.sh`

**User-invoked entry points** (3): `/version-pin`, `/deploy-retire-component`, `/deploy-diagnose-drift`

> These stay as **skills**, not `commands/*.md`. `commands/` is a legacy format;
> skills and commands load identically. See spec.md §'Commands'.

| Skill | Self-contained | Deps |
|---|:--:|---|
| `config-debug-substitution` | ✅ | — |
| `config-validate-native` | ✅ | — |
| `deploy-diagnose-drift` | ✅ | — |
| `deploy-retire-component` | ✅ | — |
| `docker-probe-internal` | ✅ | — |
| `version-pin` | ✅ | — |

## `manifest-data-pipelines` — 6 skills

> ⛔ **DELETED — does not ship.** 0/6 cross-lens agreement; one lens only, six ~30-line field
> notes, no orchestrator, invisible in a marketplace. Members scatter to their own subject-lens
> votes. This is the bundle this map itself called "the first I would delete".

Building and operating an ingestion or API-integration job: table design for cached external records, wiring a new field through to its consumer, live-data validation, bulk-endpoint replacement of N-call loops, out-of-band cache warming, stalled-job forensics.

**Cross-lens support**: ONE lens only. Journey is the only lens that proposes this boundary; subject scatters the six across code-quality / ci-testing / environment, and coupling reports zero signal (all six land in its 'recipes' residue, which it explicitly calls a non-answer). Adopted because a coherent single-lens story beats a three-way scatter plus an admitted null — but this is the weakest plugin here and the first I would delete.

| Skill | Self-contained | Deps |
|---|:--:|---|
| `api-optimize-bulk` | ✅ | — |
| `cache-warm-oob` | ✅ | — |
| `data-design-ingestion` | ✅ | — |
| `data-validate-live` | ✅ | — |
| `data-wire-field` | ✅ | — |
| `process-diagnose-stall` | ✅ | — |

---

**Total assigned**: 108 / 108

## Disputes

| Skill | Positions | Resolution | Conf |
|---|---|---|:--:|
| `plan-manage` | subject=spec-planning (the .plans markdown files are the artifact); journey=feature-lifecycle (planning sits between specify and implement); coupling=forge (eight real git_ops.sh calls — issue-view, label-create, issue-edit) | manifest-spec-planning. 2-of-3, and a user installing a planning plugin expects it. Cost stated explicitly: it drags a second copy of git_ops.sh (560L) into the spec plugin. | medium |
| `ci-setup` | subject=ci-testing; coupling=ci (ci_platform.sh); journey=deploy-ops (standing up a pipeline is one-time delivery infrastructure) | manifest-ci. Two lenses group it with the other CI skills and it is the ci_platform.sh anchor. | high |
| `ci-diagnose-drift` | subject=ci-testing; coupling=ci; journey=ship-it (you reach for it when the PR is red but local is green) | manifest-ci. Journey's placement is about when you invoke it, not what it operates on; the file it reads is the workflow YAML. | high |
| `ci-reproduce-failure` | subject=ci-testing; coupling=ci; journey=ship-it | manifest-ci, same reasoning as ci-diagnose-drift. | high |
| `ci-audit-triggers` | subject=ci-testing but rated LOW with security named as the alt; coupling=ci (ci_platform.sh); journey=security-review (pwn-request threat modeling) | manifest-ci. Tiebreak is ci_platform.sh plus the hard constraint that it ships with ci-harden-workflow, its named remediation counterpart. Concession: the finding class is pure security and the subject lens itself calls this the place its lens produces a worse boundary than a concern-based one. | low |
| `ci-harden-workflow` | subject=ci-testing (LOW); coupling=ci; journey=security-review | manifest-ci. Moves with ci-audit-triggers by necessity. Note that branch protection, CODEOWNERS and environments are forge settings, not workflow files, so even inside manifest-ci its artifact is only partly the YAML. | low |
| `code-audit` | subject=security (LOW, alt code-quality — 'the single worst-behaved skill for this lens'); journey=security-review (auto-triggers on auth/crypto/secrets/input validation); coupling=code-quality (learning_capture.sh consumer) | manifest-security, 2-of-3. Consequence to state plainly: code-audit auto-triggers inline and is never user-invoked, so whichever plugin holds it becomes an always-on dependency for everyone who installs that plugin. | medium |
| `ai-code-audit` | subject=code-quality (alt security); journey=security-review (alt code-quality); coupling=code-quality | manifest-code-quality, 2-of-3. One of its seven passes is security; six are architecture, async/state, error handling, logic, quality and iteration. | medium |
| `docker-audit-firewall` | subject=security (network ACL boundary); coupling=security; journey=deploy-ops (fired by adding a compose ports: mapping) | manifest-security, 2-of-3. The trigger is an ops event but the work is reviewing an ACL that replaces app-layer auth. | medium |
| `version-pin` | subject=environment (LOW — edits repo files but governs the built environment; alt security); journey=deploy-ops (supply chain of a deployable); coupling=security (exclusive version_pin.sh + version_pin_hook.sh) | manifest-runtime-ops, 2-of-3. It carries its own scripts either way, so coupling does not force security. Flagged: it overlaps the dependency-guardian agent, which I placed alongside it for exactly that reason. | medium |
| `antipattern-detect` | subject=agent-workbench (its write target is knowledge_base.yml, the file learning-capture owns); journey=code-quality (triggered by lint/test/review failures); coupling=code-quality | manifest-code-quality, 2-of-3. This splits the learning_capture.sh pair across two plugins — accepted because the script is already required in both (10 code-quality consumers), so keeping the pair together would not avoid the duplication. | medium |
| `learning-capture` | subject=agent-workbench; journey=agent-ops; coupling=code-quality (it is the learning_capture.sh anchor) | manifest-workspace, 2-of-3. The store is ~/.claude/config/knowledge_base.yml — agent knowledge, not project code. | medium |
| `graphify` | subject=code-quality (GRAPH_REPORT.md is an analysis artifact like a refactor roadmap); coupling=code-quality; journey=docs (comprehension is the front door of documenting) | manifest-code-quality, 2-of-3. Journey itself concedes the user's next step — write docs or change code — is invisible at invocation time. | medium |
| `cli-audit-help` | subject=code-quality; journey=code-quality; coupling=recipes (declared no coupling signal) | manifest-code-quality. Two positive signals against one declared null. | high |
| `llm-invoke-stdin` | subject=code-quality (the invocation seam inside a script); journey=agent-ops (alt code-quality); coupling=recipes | manifest-code-quality. Journey's own alt agrees; the subject is plain script-writing craft that happens to shell out to an agent CLI. | medium |
| `project-scaffold` | subject=code-quality (alt ci-testing); journey=code-quality (alt deploy-ops); coupling=workspace | manifest-code-quality, 2-of-3. What it installs is lint config, test frameworks and quality gates. | medium |
| `project-verify` | subject=ci-testing (the pass/warn/fail report is the artifact); journey=code-quality (runs the gates project-scaffold installs); coupling=workspace | manifest-code-quality. Three-way split; resolved toward the plugin holding project-scaffold, since the two bracket the same journey. | low |
| `smoke-manage` | subject=ci-testing (owns smoke-catalog/<app>.yaml); journey=code-quality (alt ship-it); coupling=workspace (smoke_test.py) | manifest-code-quality. Three-way. The catalog is per-app and generic, which rules out workspace; test authoring beats pipeline authoring. | low |
| `test-pin-bug` | subject=ci-testing; journey=code-quality; coupling=recipes | manifest-code-quality. Assertion craft, exercised while writing code, not while operating a pipeline. | medium |
| `test-vary-fixtures` | subject=ci-testing; journey=code-quality; coupling=recipes | manifest-code-quality, same reasoning as test-pin-bug. | medium |
| `false-green-check-audit` | subject=ci-testing (alt environment); journey=code-quality (alt security-review); coupling=recipes | manifest-code-quality. Its subject is a gate's pass semantics, which applies to CI gates and health checks alike — verification craft, so it follows the test-* family. | low |
| `test-isolate-ambient` | subject=ci-testing; journey=code-quality (alt agent-ops, conceding the worked examples are all Manifest deploy/hook/installer verification); coupling=workspace | manifest-workspace. Generic in principle, Manifest-only in practice — its isolation handles are TARGET_DIR, ISSUE_HOOKS_SETTINGS and ~/.claude. | medium |
| `pr-smoke` | subject=ci-testing (despite the pr- prefix it never reads PR state); journey=ship-it (marketed as the post-PR gate); coupling=workspace (run_pr_regression.sh is Manifest's CI mirror) | manifest-workspace. Three-way, resolved on what it actually runs: the Manifest repo's own shellcheck/yamllint/bats/pytest suite plus a deployed-~/.claude smoke pass. Inert outside this repo, which is why it must not sit in a product plugin. | medium |
| `env-check` | subject=environment (installed CLIs, auth, MCP connectivity on the machine); journey=agent-ops; coupling=workspace | manifest-workspace, 2-of-3. It checks the Manifest environment specifically, not a generic deployment. | high |
| `config-audit` | subject=environment (alt agent-workbench); journey=agent-ops; coupling=workspace | manifest-workspace, 2-of-3 and subject's own alt agrees. Its targets are the Claude/Cursor/Gemini/Codex home trees. | high |
| `deploy-reconcile` | subject=environment; journey=agent-ops; coupling=workspace (deploy_reconcile.sh + reconcile_core.py) | manifest-workspace, 2-of-3. It enumerates what Manifest put into ~/.claude and its mirrors. | high |
| `ai-hooks-integration` | subject=environment (alt agent-workbench — 'the weakest boundary in this partition'); journey=agent-ops; coupling=workspace | manifest-workspace, 2-of-3. It configures the agent's own settings files across four AI tools and bundles its own scripts/, templates/ and pytest suite, so it stays plugin-portable wherever it lands. | medium |
| `pass-cli` | subject=security (the artifact is a credential; alt environment); journey=agent-ops but explicitly LOW ('it belongs to no workflow'); coupling=recipes | manifest-workspace. No lens has real grip. It is a capability every plugin may need, not a workflow member — the honest treatment is a base dependency, not a member of any single plugin. | low |
| `config-validate-native` | subject=environment; journey=deploy-ops; coupling=recipes | manifest-runtime-ops. Two positive signals agree exactly; coupling declares no signal. | high |
| `config-debug-substitution` | subject=environment; journey=deploy-ops; coupling=recipes | manifest-runtime-ops, same as config-validate-native. | high |
| `docker-probe-internal` | subject=environment; journey=deploy-ops; coupling=recipes | manifest-runtime-ops, same. | high |
| `deploy-diagnose-drift` | subject=environment; journey=deploy-ops (alt agent-ops — its canonical case is a Manifest bootstrap); coupling=workspace | manifest-runtime-ops, 2-of-3. Its stated scope is any deployed environment missing expected state; the Manifest case is the worked example, not the boundary. | medium |
| `deploy-retire-component` | subject=environment; journey=deploy-ops; coupling=workspace | manifest-runtime-ops, 2-of-3. Its subject is a launchd/systemd daemon, socket, runtime or MCP server on the host. | high |
| `api-optimize-bulk` | subject=code-quality (rewrites N-call loops at the client call sites); journey=data-pipelines; coupling=recipes | manifest-data-pipelines, adopted with the whole cluster. See structuralProblems — this plugin has no cross-lens support at all. | low |
| `cache-warm-oob` | subject=environment (a running job's cache); journey=data-pipelines; coupling=recipes | manifest-data-pipelines. Paired with api-optimize-bulk by the same batch-job trigger. | low |
| `data-design-ingestion` | subject=code-quality; journey=data-pipelines; coupling=recipes | manifest-data-pipelines. | low |
| `data-wire-field` | subject=code-quality; journey=data-pipelines; coupling=recipes | manifest-data-pipelines. | low |
| `data-validate-live` | subject=ci-testing (a test stage, not a refactor); journey=data-pipelines (alt code-quality); coupling=recipes | manifest-data-pipelines. Subject-weighting and verb-weighting genuinely disagree; the cluster keeps it. | low |
| `process-diagnose-stall` | subject=environment (a running process's resource signature); journey=data-pipelines (alt deploy-ops); coupling=recipes | manifest-data-pipelines. The closest call in the cluster — the technique is generic process forensics and it would sit equally well in manifest-runtime-ops. | low |

## Structural problems

These are the reason this map is not a shipping plan.

1. plugin.json has NO dependency field (measured 2026-07-27, specs/522). `manifest parallel-agent` is invoked by 29 of 108 skills spanning 8 of these 10 plugins. There is no way to declare it. The options are: vendor the orchestrator into 8 plugins (8 copies, guaranteed drift), or declare it an external CLI prerequisite already installed at ~/.local/bin (honest, and the only workable one — treat it like gh or docker). Neither is expressible IN the manifest, so it degrades to a README instruction that silently installs broken plugins when ignored.

2. The forge boundary is unresolvable, not merged by agreement. Subject wants to cut git|issue; journey wants to cut plan|ship. Both cuts are defensible and mutually incompatible, so the merge wins by default. It is only tolerable because coupling forbids the cut: tracker_ops.sh and issue_support.sh both shell git_ops.sh via SCRIPT_DIR, so any split duplicates ~2,400 lines and reintroduces exactly the drift feature 522 exists to remove. Result: a 19-skill plugin that a Linear-only user installs to get GitHub PR machinery they will never run.

3. git_ops.sh (560L) now crosses three plugins: manifest-forge (12 consumers), manifest-spec-planning (plan-manage, 8 call sites) and manifest-code-quality (shell-refactor, opening its result PR). Three copies, or hoist plan-manage and shell-refactor back into forge and accept two plugins no browsing user would look in.

4. learning_capture.sh (838L, 11 consumers) crosses three plugins: 10 in code-quality, learning-capture in workspace, git-commit in forge. All three copies resolve knowledge_base.yml to the same ~/.claude/config store, so state converges — but every patch must land three times, and antipattern-detect and learning-capture, which co-own that file, end up in different plugins.

5. Per-skill registries do not travel with a plugin, and this is the most expensive problem in the list. command_config.yml tool_policies has 108 name-keyed entries (allowed/forbidden tools, parallel_agents, validation_tier, subagent_model, session_model); command_categories.yml has 85 overrides; validation_criteria.yml has command_overrides; constitution_baseline.json has 13 entries keyed by .apm/skills file paths. plugin.json has no equivalent for any of it. Packaging these skills as plugins silently DROPS the subagent model pins and validation tiers — the exact cost-control layer subagent_model_default.py and docs/MODEL-POLICY.md exist to enforce, worth a measured $951.70 / 56.3% of all-time subagent spend.

6. Manifest's nine Claude hooks are user-scope entries in ~/.claude/settings.json unioned in by bootstrap, and three of them (subagent_model_default.py, block_cwd_delete.py, guidance_hint.py) are deliberately domain-free machine-wide policy. Attaching them to manifest-workspace means a user who installs only manifest-docs gets no deletion guard and no model-pin enforcement; attaching them to every plugin means N registrations of the same script. Plugin hooks are also a different mechanism from the settings.json hooks Manifest actually ships — this is a rewrite, not a repackage.

7. manifest-data-pipelines has zero cross-lens support: 0 of 6 members unanimous, subject scatters them three ways, coupling declares no signal. It exists because one lens told a coherent story. It is six ~30-line field notes with no orchestrator, no shared script and no MCP — invisible in a marketplace and invisible inside any host plugin. Deleting it and scattering the six is equally defensible and equally arbitrary.

8. Roughly 30 of the 108 skills are ≤45-line micro-lessons — captured incidents, not domain members. All three lenses admit they have no grip on these (coupling calls its 15-skill 'recipes' bucket 'the honest residue of the lens'). Their placement is driven by whichever workflow happened to produce them. No partition fixes this; a 'kind of lesson' axis would cluster them better and nobody would install it.

9. No lens applied the audience cut, and it is orthogonal to all three: about a dozen skills (pr-smoke, env-check, config-audit, deploy-reconcile, test-isolate-ambient, help, token-benchmark, metrics-report, skill-evolve, ai-hooks-integration, deploy-diagnose-drift) are about Manifest itself, not the user's product. Two of three lenses scatter some of them into product plugins where an outside user finds them inert. I pulled most into manifest-workspace; deploy-diagnose-drift and deploy-retire-component are left straddling the line.

10. manifest-ci is held together by ci_platform.sh while two of its five members (ci-audit-triggers, ci-harden-workflow) reason like security skills — placed in security by the journey lens and rated LOW by the subject lens. Whichever plugin wins, the pair must move together, and the losing plugin loses a real user expectation.

11. stitch-design is the strongest boundary (18/18 unanimous) and still ships 15 MCP-gated skills to a user who only wants a WCAG audit. All three lenses named this and all three kept the merge, because a 3-skill frontend-quality plugin is not browsable. The split is available and costs nothing structurally — it is purely a marketplace-granularity judgement.

12. Two distribution systems would both claim the skill tree. apm already owns ~/.claude/skills (SC-006, 2026-07-28) and deploys from a published tag; configs/claude/config/reconcile.yml already ignore-lists `plugins`. Shipping plugins means either apm or the marketplace owns each skill, and nothing in the repo arbitrates that today — deploy_home_skills, sync-skills and apm-dev-sync all assume a single tree at .apm/skills.

13. Skill descriptions are rivalrous: the 29,000-token frontmatter budget is a measured hard cap, and budget exhaustion drops descriptions so a name-only skill never fires (0/25 vs 38% over 3,268 sessions). Partitioning into 10 plugins does not reduce the loaded surface for a user who installs several, and per-plugin metadata adds to it. Packaging is not a fix for catalog density and may make it marginally worse.

14. The coupling lens's own output was truncated at pr-triage-bots, so 89 of its 108 placements here are reconstructed from its plugin rationales and stated sizes. The reconstruction reconciles to exactly 108, but any dispute above resolved 2-of-3 where coupling is the swing vote (notably version-pin, learning-capture, graphify, project-verify, smoke-manage) rests on inference, not on what that lens actually said.
