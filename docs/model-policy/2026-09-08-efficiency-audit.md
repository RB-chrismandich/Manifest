# Efficiency audit — approval checkpoint

Historical approval checkpoint: inspection and baseline preceded approval.
The user subsequently approved the first increment; see
[implementation, verification and rollback](dispatch-reliability.md).
The evidence below describes the pre-change baseline, not current source.
Broader efficiency experiments remain separate. No measured savings are claimed.

## Checkout and boundaries

Checkout: `/Users/charlemagne/agentic-workstreams/internal/Manifest`.
Branch: `feat/risk-based-review-escalation`.
Revision: `a3ede138db5ad6a9926e562c237e8ecfe1252d23`.
There were 88 changed/untracked status entries before this audit artifact.
These include delegation, review policy, and session-continuity work; preserve them.
Repository AGENTS.md and the brainstorming lifecycle were inspected. Implementation
requires approval of a concrete design. No bootstrap, deployment, global setting
change, paid model call, MCP installation, push, or transcript export occurred.

Installed versions observed: Claude Code `2.1.263`, Codex CLI `0.153.4`;
Gemini CLI package metadata says `0.29.6`. Antigravity is installed but its version
was not established; `cursor-agent` was not found on PATH. This is not a complete
supported-version matrix.

Read-only deployed-state sample: Claude user settings contain one Agent default
hook, `skillListingBudgetFraction=0.05`, and session model `opus`; the two subagent
model/force environment keys are absent from that file. Other configuration
scopes and process environment were not proven absent. The deployed hook matches
repository source SHA-256 `8bfc4f5b08f84c84fd8cc457eb1ffee3b63767fd8ac2bd1fc69e2bf2cdd4a763`.
The deploy stamp records revision `c03aac5027025d2cf39bf3da5f998b78c6e89b19`,
`dirty=false`, and `2026-08-05T04:52:52Z`. Neither the stamp nor matching source
proves the hook executed in a particular session.

## Evidence table

Paths below are relative to the repository root; function names identify the
relevant implementation without depending on changing line numbers.

| Behavior | Declared policy | Implementation | Deployment destination | Behavioral test | Telemetry coverage | Gap |
|---|---|---|---|---|---|---|
| Agent defaults and explicit exceptions | `docs/model-policy/subagents.md` | `configs/claude/scripts/subagent_model_default.py`: `decide`, `declared_model` preserve explicit/frontmatter pins and skip forks | `~/.claude/scripts/`; Agent matcher in `~/.claude/settings.json` | `tests/bats/subagent_model_hook.bats`, `subagent_model_plugin_layout.bats`: 34 pass | Sidecar request versus transcript served model | Silent malformed-input skips; current filesystem pin resolution is not historical evidence; managed/CLI definitions and alternate config roots need reconciliation |
| Workflow, forks, teams, external CLI | `subagents.md`, `cross-harness.md`, `configs/claude/references/sub-agent-dispatch.md` | Agent hook excludes Workflow; `subagent_breakdown.py` distinguishes Workflow by path and forks by type; `plugins/manifest-delegate/manifest_delegate/` already provides external execution and recovery | Claude hook only; delegate plugin runtime separately | `tests/bats/subagent_audit.bats`: 17 pass | Agent/Workflow split in text; forks listed when premium | JSON omits other-channel coverage; no explicit teams/external/unknown coverage states; Workflow default currently unenforced by this hook |
| Deployment reliability | `subagents.md` requires correct file/scope | `bootstrap/lib/deploy.sh`: `merge_claude_runtime_settings`, `write_deploy_stamp` | User `settings.json`; MCP separately in `.claude.json` | `tests/bats/deploy_runtime_settings.bats`: 13 pass | Source revision/tree hashes, dirty flag, timestamp | Hook path expands against HOME rather than target; test checks repo basename, not executable at emitted path; warning-only merge can precede stamp; no effective policy hash or transactional rollback in this function |
| Usage and cost attribution | `MODEL-POLICY.md`, `changing-levers.md` | `token_cost_report.py`, `opus_attribution_report.py`, `subagent_breakdown.py`, shared `model_pricing.py` | Local scripts and reports | `tests/python/test_measurement_reports.py`: 31 pass | Input/cache-write/cache-read/output; request dedup; per-model estimates | Missing-ID collapse in breakdown/attribution; malformed shapes insufficiently checked; no verified-task denominator; historical estimates called spend/savings; audit exports free-text description |
| Context, skills, continuation | `command_config.yml`, dispatch reference, session-checkpoint skill | `skill_usage_report.py`, `tests/token_benchmark/`, existing checkpoint work | Harness guides, plugin skills, shared mirror; MCP registry ships Context7 | Measurement suite covers skill report; new workflow/continuity tests already exist in user WIP and were not run here | Skill invocation counts; benchmark records; continuity work in progress | Listings/preloads versus invocation not measured; cross-host tool-search and compaction support not fully verified; aggregate budgets cannot be inferred from individual timeouts |

## Priority findings

1. **Audit completeness:** an empty existing root returns exit 0, `0/0 (100.0%)`
   pinned, and `OK`. Missing/unreadable transcripts and malformed sidecars can
   disappear from the population. Unknown served models are printed but do not
   prevent the final OK. These are observation gaps, not evidence of compliance.
2. **Historical attribution:** `collect_dispatches` resolves old agent names
   against current definitions and folds that into `requested`. A definition
   changed after execution can change the verdict. Requested, resolved, and
   served need separate fields with provenance; absent evidence stays unknown.
3. **Deployment proof:** execute the emitted hook from a temporary deployment
   target. The existing test named “the deployed hook command points at a real
   script” checks repository source instead. Merge warnings must be visible in
   deployment evidence; a source stamp alone cannot certify an effective merge.
4. **Counting and disclosure:** a synthetic two-record missing-ID probe in
   `subagent_breakdown.fold` produces one request and 10 input tokens from records
   containing 10 and 20. `opus_attribution_report.fold_file` has the same None-key
   pattern by inspection. Audit descriptions are unbounded in JSON and may carry
   task text. Bounded, allowlisted output should preserve diagnostics without it.
5. **Policy drift:** `sessions.md` both retires and later describes the Fable
   ask-gate as current. Runtime JSON comments say permissions/listing settings
   remain inert although the keys are present in that runtime source. References
   to `settings.hooks.json` and `deploy_runtime_hooks.bats` have moved to
   `settings.runtime.json` and `deploy_runtime_settings.bats` respectively.

## Current official documentation versus historical evidence

Claude's current docs place invocation model before frontmatter, then the
subagent environment default, then session model. They date the precedence
change to `2.1.251`; older versions put the environment override first. The
installed `2.1.263` is newer, but this audit did not make a live dispatch.
The force option overrides deliberate pins and is unsuitable for this task.
[Official subagent documentation](https://code.claude.com/docs/en/sub-agents).

Workflow agents use the same model order, with a stage model acting as the
invocation choice. A version-gated, non-forcing environment default is therefore
a supported candidate for omitted-model Workflow dispatches. Arbitrary script
rewriting is unnecessary. Host substitution can still change the served model.
The Workflow size guideline is advice, not a cap.
[Official Workflow documentation](https://code.claude.com/docs/en/workflows).

Claude tool search depends on model/provider support and deployment settings;
Azure-hosted Foundry rejects it, and proxies can disable it. Treat support as
a host/provider capability, not a shared global flag.
[Official MCP documentation](https://code.claude.com/docs/en/mcp).
The current settings page did not expose `skillListingBudgetFraction` in the
retrieved text; that absence does not establish removal.
[Official settings documentation](https://code.claude.com/docs/en/settings).

The current [Codex subagent documentation](https://developers.openai.com/codex/subagents)
and [Gemini MCP documentation](https://geminicli.com/docs/tools/mcp-server/) were
located, but exact installed-version contracts were not established here.
No Claude setting or model alias should be copied into those hosts on that basis.
This session's host-provided tool schema remains authoritative for its execution.

## Baseline commands and observed results

Run from the checkout. Existing dependencies only; no model invocation:

```sh
task_home=$(mktemp -d /private/tmp/manifest-efficiency-baseline.XXXXXX)
env HOME="$task_home" XDG_CONFIG_HOME="$task_home/.config" \
  PYTHONDONTWRITEBYTECODE=1 bats \
  tests/bats/subagent_model_hook.bats \
  tests/bats/subagent_model_plugin_layout.bats \
  tests/bats/subagent_audit.bats \
  tests/bats/deploy_runtime_settings.bats
env HOME="$task_home" XDG_CONFIG_HOME="$task_home/.config" \
  PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider \
  tests/python/test_measurement_reports.py
```

Observed: **64 Bats passes; 31 Python passes**. The initial system `python3`
pytest invocation could not import `pygments`; the existing repository virtual
environment ran the suite successfully. No dependencies were installed.
These are baseline tests, not verification of a new implementation.

Additional read-only probes: empty-root audit returned the false assurance
described above; in-memory missing-ID fold returned one request instead of two.
Neither probe used real transcripts or paid execution.

Static context inventory: AGENTS.md 26,503 bytes, Claude guide 6,654 bytes,
Gemini guide 25,773 bytes; 122 repository plugin SKILL.md files. These are source
bytes/file counts, not runtime tokens, listing size, or savings. Startup context
and task-time growth still need separate measurements.

## Later experiments — separate approvals

| Experiment | Fixed controls | Evidence required |
|---|---|---|
| Opt-in delegation profile | Main model/effort and required independent review | Start with two workers, no recursive fan-out/teams/swarm; explicit turn/retry/dispatch/time budgets; test exhaustion checkpoints and document resume/external escapes |
| Skill listing/context | Keep 0.05 until measured; preserve discovery capability | Startup instructions/listing/preloads/MCP metadata versus task-time tool definitions/results/history/hook context; compare discovery failures and rework; consolidate duplicate skills reversibly |
| Effort | Main model, task class, tools and context configuration | Equivalent verified tasks, failures, retries, latency and all cache costs; no automatic effort lowering |
| Compaction/memory | Native supported mechanism; existing checkpoint implementation | Separate model window from compaction window; preserve decisions/constraints/approvals; continuation must revalidate stale evidence; no universal percentage or destructive cleanup |

Post-deployment task outcomes, actual billing, subscription quota, and savings
are **unknown**. Historical API-equivalent counterfactuals are estimates, not
observed reductions. Representative host/model evaluations and deployment need
separate explicit authorization. Do not add a second telemetry or agent system.
