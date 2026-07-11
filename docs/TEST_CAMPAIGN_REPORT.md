# Manifest Feature-Test Campaign — Summary

**Date**: 2026-07-10
**Branch**: `main` @ `9cf4b27` (clean at campaign start)
**Plan**: `~/.claude/.plans/.archive/20260710-manifest-feature-test-campaign.md`
**Method**: Fable 5 orchestrated; all execution by **11 Sonnet 5 sub-agents** across 2 workflows
(~568k Sonnet tokens; Fable spent only on planning/synthesis)

---

## 1. Overall Verdict: ✅ APPROVED

Every Tier-1 metric is green at baseline and stayed green through the improvement pass:
**816/816 bats tests, 590/590 runnable pytest tests, full CI mirror reproduced locally with
zero failures** (shellcheck gate, yamllint, YAML parse, docs-drift gates, lint guards, smoke
Lite 7/7). The campaign applied four improvements (below) with zero regressions. The single
open item is environmental, not a code defect: the deployed `~/.claude` is one release
behind the repo (today's feature 482), with a one-command remediation left to you.

## 2. Success Metrics — Baseline vs Final

| ID | Metric | Tier | Baseline | Final | Δ |
|----|--------|------|----------|-------|---|
| M1 | bats: files / tests passed | 1 | 56/56 files, 816/816 tests (≈4 min) | unchanged¹ | — |
| M2 | pytest: passed / failed / warnings | 1 | 590 / 0 / **1 warning**, 1 skip² | 590 / 0 / **0 warnings**, 1 skip² | ✅ −1 warning |
| M3 | shellcheck (CI gate `-S warning`) | 1 | 0 errors, 0 warnings (27 info/style below gate) | unchanged | — |
| M4 | yamllint + YAML parse | 1 | 0/0; 5/5 configs parse | unchanged | — |
| M5 | Feature areas covered / gaps | 2 | 13/13 covered (100%); **7 gaps enumerated** | 13/13; gaps documented + prioritized | ✅ gaps now tracked |
| M6 | CLI `--help` contract | 2 | 14/14 pass, 0 hangs | unchanged | — |
| M7 | Docs/drift gates | 1 | drift gates green (bats) | re-verified + cursor-rules regen CLEAN | ✅ re-proven |
| M8 | Deployed-env integrity | 2 | 7/9 (skill parity 90/91; orphan `__pycache__` dir; 3 dangling links³) | 8/9 (**orphan removed**; parity 90/91 pending your redeploy) | ✅ +1 |
| M9 | Dev toolchain present | 2 | 4/6 (markdownlint, pre-commit **missing**) | **6/6** | ✅ +2 |
| — | CI-mirror steps measured locally | 2 | 15/19 (smoke Lite, markdownlint, pre-commit, bash -n unmeasured) | **19/19, all green** | ✅ +4 |

¹ No bats-covered code was modified by the improvements (only `pyproject.toml` + an empty untracked
dir); the bats-assertion lint guard re-ran clean.
² The 1 skip is a legitimate conditional: `test_mixed_ui_api_cli_dispatch` requires
Playwright+Chromium (not installed).
³ All 3 dangling symlinks live under Antigravity-IDE-owned paths outside Manifest's managed set —
not a Manifest deploy defect.

## 3. Per-Feature-Area Verdicts (13 areas)

| # | Feature area | Verdict | Evidence |
|---|--------------|---------|----------|
| FA-1 | Bootstrap & deploy | ✅ PASS | 14 bats suites green; `bash -n` 38 files; smoke deploy scenarios (antigravity reduced-set, shared-asset full-set, mcp-preserve, settings-defaults) all PASS |
| FA-2 | Parallel-agent orchestration | ✅ PASS | `test_parallel_agent.py` + `agents/` pytest green; `model_check.bats`; `--help` contract |
| FA-3 | Git/platform ops | ✅ PASS | 9 bats suites (git_ops, git_platform, label_sync, linear_ops, branch_clean, pr_review, pr_merge_loop, merge_decision, merge_gate_config) green |
| FA-4 | Skills system & doc generation | ✅ PASS | skill_naming, commands_doc_drift, context_budget, help_coverage green; cursor-rules regen drift-free; 91 skills; markdownlint 0 findings |
| FA-5 | SkillClaw | ✅ PASS | 5 pytest modules + 3 bats suites green |
| FA-6 | Issue automation & lifecycle | ✅ PASS | auto_issue_dev, issue_support, install_issue_hooks, lifecycle, loop_lock bats green |
| FA-7 | CDDL loop (feature 482) | ✅ PASS | cddl_loop.bats, deploy_cddl.bats, `tests/python/cddl/` green; smoke `cddl-loop-critical-path` PASS (repo-side; not yet deployed to home — see §5.1) |
| FA-8 | Smoke orchestrator | ✅ PASS | bats + pytest green; live Lite run 7/7 scenarios PASS |
| FA-9 | Hooks & guards | ✅ PASS | lint_on_edit, guidance_hint, version_pin, learning_capture, audit_log, gemini_hooks_merge bats green |
| FA-10 | Config integrity | ✅ PASS | yamllint 0/0; 5/5 YAML parse; knowledge_base_registry bats green |
| FA-11 | CI & repo hygiene | ✅ PASS | Full CI mirror (all 3 jobs' steps) reproduced locally green; lint guards clean; pre-commit gate now runnable locally |
| FA-12 | Deployed environment | ⚠️ PARTIAL | Structure/mirrors/CLIs healthy (all 5 assistant homes; 6/6 CLIs); **1 release behind repo** (skill parity 90/91, CDDL scripts absent from `~/.claude/scripts`) |
| FA-13 | Reconcile & verification tooling | ✅ PASS | deploy_reconcile, reconcile_deploy_report, verification_gate, spec_review, audit_log bats + `test_reconcile_policy.py` green; smoke `deploy-reconcile-preview` PASS |

## 4. Improvements Applied (baseline → final)

1. **pytest deprecation warning eliminated** — `pyproject.toml` now pins pytest-asyncio's
   future default (`asyncio_default_fixture_loop_scope = "function"`). Verified: 590 passed,
   collection count identical (591), **0 warnings** (was 1); passes the pre-commit gate with
   no autofix. *Uncommitted in the working tree for your review.*
2. **Orphan directories removed** — repo `configs/claude/scripts/orchestrator/` (untracked,
   completely empty, created today — stray scaffolding) and deployed
   `~/.claude/scripts/orchestrator/` (contained only a stale June `__pycache__` from the
   pre-`agents/` refactor layout). Matches the documented orphan-dir failure pattern that
   previously tripped the skill-naming gate. Verified deploy-safe (dir no longer exists in
   either location).
3. **Dev toolchain repaired** — `pre-commit` 4.6.0 and `markdownlint-cli2` 0.23.0 installed
   via Homebrew. The full CI mirror **and** the no-bypass pre-commit gate are now runnable
   locally (they weren't before). First measurements: markdownlint 0 findings across the 19
   CI-targeted files; pre-commit gate green on the campaign's edit.
4. **CI-mirror measurement gaps closed** — 4 CI steps never before measured in this
   environment now run and pass locally: smoke Lite tier (7/7 scenarios), both lint guards
   (`check_array_expansion.sh`, `check_bats_assertions.sh`), `bash -n` syntax sweep (38
   files), and `generate_commands_doc.py --check`.

## 5. Findings Not Fixed (Recommendations, prioritized)

1. **Redeploy your home environment** (5 min): `./bootstrap.sh --skip-install --skip-auth --force`
   — delivers feature 482 (the `spec-implement-loop` skill + CDDL scripts) shipped today in
   PR #543. The autonomous redeploy was **blocked by the safety classifier** (sub-agents may
   not rewrite the config surfaces the assistant itself loads without you explicitly asking)
   — a correct control, so this is deliberately left to you.
2. **Coverage gaps worth new tests** (from the validated feature map): standalone bats for
   `bootstrap/lib/auth.sh` + `common.sh` (currently only transitively covered); SkillClaw's
   fail-open daemon-down degrade path + `chmod 700` storage assertion; a drift meta-test
   asserting `run_pr_regression.sh` stays a superset of `ci.yml`; per-step unit assertions
   for `smoke-catalog/manifest.yaml`; direct coverage for `issue_support_hook.sh` and
   `agents/synthesis.py`.
3. **shellcheck cosmetic debt**: 26 info + 1 style findings below the CI gate — 18 are
   SC2016 in `linear_ops.sh` (almost certainly intentional GraphQL `$var` quoting; consider
   targeted `# shellcheck disable=SC2016` with rationale rather than rewrites).
4. **markdownlint version skew**: `.pre-commit-config.yaml` pins `markdownlint-cli` v0.49.0
   while CI uses `markdownlint-cli2-action` (v23 line) and brew ships cli2 0.23.0 — same
   rule set and shared `.markdownlint.jsonc`, but consider aligning on one line.
5. **Optional**: install Playwright+Chromium to un-skip `test_mixed_ui_api_cli_dispatch`
   (591/591); clean up the 3 Antigravity-IDE-owned dangling symlinks (outside Manifest's
   managed set).

## 6. Measurement Notes

- **CI parity**: every suite was invoked exactly as CI defines it (`ci.yml` consulted per
  agent): pytest via the `tests/requirements-ci.txt` pins (uv-isolated), shellcheck with
  `-S warning` over the CI file set, yamllint with the repo config, smoke via the exact
  ci.yml invocation. Baseline = the repo's own definition of green.
- **bats integrity**: 56 files split into two disjoint alphabetical halves, run serially
  within each agent with per-file TAP capture and direct exit codes (no pipe-masking).
- **Read/write discipline**: measurement agents ran strictly read-only; mutations were
  limited to the 4 improvements above + brew installs. Working-tree delta is exactly:
  `M pyproject.toml` (2 insertions). Nothing committed — say the word and I'll run the
  commit pipeline.
- **Raw logs**: scratchpad `baseline/` (TAP files, pytest/shellcheck/yamllint logs, env
  checks) and `final/` (pytest re-run, smoke, markdownlint, pre-commit, brew).
- **Budget**: baseline workflow 416,591 + improvement workflow 151,702 = **568,293 Sonnet
  tokens, 11 agents, 117 tool calls**; wall time ≈ 8 min of workflow execution.

---

## 7. Phase 2 Addendum — Recommendations Executed (same day)

Commits on `main`: `c6b706b` (pytest-asyncio pin) and `6c1c83f` (recommendations, 31 files,
+1368/−42). All three recommendation tracks from §5 completed:

| Track | Outcome |
|-------|---------|
| Coverage-gap tests | **+164 tests** (pytest 590→668 passed; bats 56→60 files): bootstrap `auth.sh`/`common.sh` (25), SkillClaw fail-open + chmod-700 (6), smoke-catalog per-step content (63), `issue_support_hook.sh` (17), `agents/synthesis.py` (21), CI-mirror drift meta-test (12) |
| shellcheck cosmetic debt | Full-severity sweep **27 → 0 findings** — targeted disables-with-rationale for intentional patterns (GraphQL `$var` quoting, profile-written export lines), one real `sed`→parameter-expansion fix |
| markdownlint version skew | pre-commit hook switched to `markdownlint-cli2` **v0.23.0** (same engine line as CI's action + brew); vendored-content excludes with documented tradeoff; **58 markdown findings fixed** in 5 first-party docs; 5 syntactically broken ai-hooks contract YAMLs repaired |

Notable: the new drift meta-test **immediately caught 4 real gaps** — `run_pr_regression.sh`
was missing CI's `bash -n` sweep, `check_bats_assertions` guard, `yaml.safe_load` parse
loop, and smoke Lite tier. All four gates were added to the mirror (now 13/13 PASS locally).
A 26-agent high-effort code review then verified 10 findings against the change set — all
fixed before commit, including two would-be CI breakers (a PATH-subtraction test that fails
on merged-/usr Linux runners; an API-key env leak in an auth test).

**SkillClaw doc correction** (found while writing fail-open tests): the daemon/proxy capture
model is retired — `.claude/CLAUDE.md`'s stale "dead daemon" phrasing updated to the current
passive-ingestion model.

**Phase-2 method**: 8 Sonnet builders + 2 Sonnet verifiers (867k tokens) + 26 review agents
(1.6M tokens, Fable-tier finders/verifiers) + inline orchestration. Grand total across the
campaign: **~3.0M sub-agent tokens, 47 agents**, with Fable context reserved for planning,
synthesis, and the inline drift/mirror fixes.
