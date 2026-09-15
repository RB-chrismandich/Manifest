# Dispatch reliability increment

Status: repository implementation; no real-home deployment or live model evaluation.
The [audit baseline](2026-09-08-efficiency-audit.md) records the initial findings.
This increment changes one optimization lever: omitted-worker model defaulting.
Audit/deployment changes make that lever observable and reversible.

## Runtime behavior

On Claude Code 2.1.251 and newer, bootstrap seeds the existing Sonnet alias through
`CLAUDE_CODE_SUBAGENT_MODEL` in the target `settings.json` only when no deliberate
settings/process default or force override exists. It never sets the force flag,
changes the main model/effort, or edits a frontmatter pin. The native ordering
preserves invocation and definition choices, including managed/CLI definitions.
Workflow stage choices participate in that ordering.
[Official model precedence](https://code.claude.com/docs/en/sub-agents) and
[Workflow behavior](https://code.claude.com/docs/en/workflows).

Older/unknown versions skip the new default and report `unsupported-host`.
A subsequent merge on such a host removes only a previously owned seed. A host
downgrade without running the merger remains uncovered. Model availability,
allowlist substitution, other configuration scopes and actual serving still need
host evidence; deterministic tests cannot establish them.

The Agent hook now ships with `--native-default-only`: missing defaults/force
overrides are diagnostic, not blocking. Known old Manifest registrations migrate
to that mode. The direct legacy injection CLI remains available for compatibility
but cannot guarantee managed/CLI pin precedence and is not the shipped policy.
This is a cost policy, never an authorization boundary. Existing permission and
security hooks remain in place; only the historical version-pin migration retains
its already-existing removals.

## Deployment and rollback

The Bash entry point still owns deployment. Its existing embedded Python merger
is extracted to `merge_runtime_settings.py`, using the existing private atomic
JSON writer. Source hook paths resolve relative to the target, including spaces.
User model, effort, deny rules, unrelated hooks and scalar choices survive merges.
Concurrent Manifest mergers fail immediately on lock contention; no retry loop.
Uncoordinated external editors do not share that lock; an optimistic change check
detects edits before commit but is not a global filesystem transaction.

`config/runtime_settings_merge.json` records version, source/policy/settings hashes,
timestamp, merge status and owned-default state. A prepared receipt precedes settings
commit and retains previous ownership, so interrupted writes remain recoverable.
Only a final merged receipt with a matching settings hash supports a merge claim.
The deploy stamp separately records `runtime_merge_status`; an unsuccessful merge
can no longer be mistaken for a certified runtime policy merely because a source
stamp exists. Reports still never call a successful merge proof of model serving.

After an explicitly authorized deployment, this command rolls back only the
owned default. It preserves later user replacements and every other setting:

```sh
python3 configs/claude/scripts/merge_runtime_settings.py \
  configs/claude/settings.runtime.json /absolute/target/.claude/settings.json \
  --rollback-default
```

Inspect the target and receipt before running it. Rollback is not persistent
opt-out: a later normal deployment can seed an absent default again. Source and
audit changes can be reversed through a reviewed patch; no automatic cleanup or
deletion of active work is included. No rollback has been run against the real HOME.

## Audit contract and migration

`subagent_breakdown.py --audit` JSON has `schema_version: 2`. Consumers of the old
`violations`/`exceptions` arrays must migrate to `records`, per-record `status`,
`coverage` and `incomplete_dispatches`. Exit 0 is scoped observed evidence; exit 2
means incomplete evidence or an input/output error. Historical premium requests
without intent evidence are `unattributed-premium`, not proven unauthorized use.
No model choice is interpreted as approval to perform an action.

The report separates Agent, Workflow, fork, teams, external CLI and unknown
channels. Teams/external adapters remain unsupported rather than reporting zero
as proof of absence. `--channel all` does not mean global enforcement. Native
resolution is currently unobserved (`resolved: null`); requested and served are
separate. Current agent definitions cannot change historical verdicts.

Missing sidecars/transcripts, malformed records, unknown models and missing
timestamps produce incomplete evidence. Both timestamp bounds are honored;
sidecar mtime no longer excludes a resumed transcript. Empty scopes do not report
100% pinning. `--limit` bounds detail rows (default 100, maximum 1000); totals
include the whole observed population. JSON is private and atomically written.
Descriptions, prompts, tool payloads, full paths and transcripts are not exported
by audit mode. Dispatch IDs are local path hashes; the source corpus remains the
full evidence. Existing usage breakdown reports retain their project grouping.

Usage attribution keeps request-ID streaming deduplication. Missing IDs remain
separate and carry a warning that counts may be overstated; exact identity is
unrecoverable. Malformed token/model/content shapes are skipped with bounded
diagnostics. Dollar reports label API-equivalent estimates; actual billing and
subscription quota are unknown. A thinking block does not establish difficulty.

## Verification

Baseline: 64 Bats tests and 31 Python tests passed before changes. New regression
tests were observed failing before implementation. Independent host-provided review
found downgrade, transaction and hidden-pin issues; regression tests cover the fixes.

Run from the repository; all deployment writes stay in temporary fixtures:

```sh
task_home=$(mktemp -d /private/tmp/manifest-dispatch-check.XXXXXX)
env HOME="$task_home" XDG_CONFIG_HOME="$task_home/.config" PATH="$PWD/.venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 \
  .venv/bin/python -m pytest -q -p no:cacheprovider \
  tests/python/test_subagent_audit.py tests/python/test_runtime_settings_merge.py \
  tests/python/test_dispatch_usage.py tests/python/test_measurement_reports.py
env HOME="$task_home" XDG_CONFIG_HOME="$task_home/.config" PATH="$PWD/.venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 \
  bats tests/bats/subagent_model_hook.bats tests/bats/subagent_model_plugin_layout.bats \
  tests/bats/subagent_audit.bats tests/bats/deploy_runtime_settings.bats \
  tests/bats/deploy_stamp.bats
```

Negative controls cover malformed targets, symlink targets, lock contention,
old/unknown host versions, user pins, unavailable/substituted model evidence,
missing telemetry and receipt/settings write failures. The emitted hook command
is executed from a target distinct from the temporary HOME. These tests prove
Manifest behavior, not native host inference or subscription savings.

Observed local results: **93 Python tests and 86 focused Bats tests pass**.
Ruff lint/format, ShellCheck, shfmt, Markdownlint, shell-array/Bats-assertion lint
and a redacted Gitleaks scan of the scoped files pass. Constitution checking exits
0 with advisory findings and 11 existing baselined violations; its baseline was
not changed. The optional/manual Pyright check was unavailable, not waived.

Additional `bats tests/bats/subagent_policy.bats` with the same isolated environment
passes 7 of 9 tests. The two failures concern the existing `code-audit` skill's
missing dispatch section/model prose. The skill, policy config and test are
unchanged by this increment; no guard was weakened to make them pass. An initial
run without the repository venv on PATH failed to import YAML; the rerun above
uses the existing dependency environment. This is not an all-repository green claim.

Post-deployment comparisons must use equivalent verified tasks and complete
intervals, counting failures, rework, retries, latency and all cache costs.
No representative usage or verified-task cost reduction has been measured here.
Live evaluations, deployment, pushing and global changes remain explicitly opt-in.
Skill-budget, effort, delegation-budget and compaction experiments remain
[separate proposals](2026-09-08-efficiency-audit.md#later-experiments--separate-approvals).
