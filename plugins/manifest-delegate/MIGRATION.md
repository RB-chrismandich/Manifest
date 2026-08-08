# Migrating from `openai/codex-plugin-cc`

`manifest-delegate` supersedes the externally installed `openai/codex-plugin-cc`
(baseline v1.0.6). This table maps every baseline entry point to its
replacement in this plugin, with the test(s) that cover it.

## Traceability table

| # | Baseline entry point | Replacement | Covering test(s) |
|---|----------------------|-------------|-------------------|
| 1 | `/codex:rescue` command → `codex-rescue` agent | `delegate` skill → `delegate.py task` (fg default `--wait`, `--background`, `--resume`/`--resume-last`/`--fresh`, `--backend`, `--model`); forwarder is `agents/delegate-runner.md` | `test_delegate_dispatcher.py::test_resume_last_reuses_backend_and_session`-equivalent flows in `test_delegate_jobs.py::test_resume_last_reuses_backend_and_session`, `test_resume_null_backend_falls_back_fresh`, `test_delegate_dispatcher.py::test_background_reuses_job_records` |
| 2 | `/codex:setup` command | `delegate-setup` skill → `delegate.py setup [--backend] [--json]` (per-backend ready/not_installed/not_authenticated/disabled/retired + `--enable/--disable-review-gate`, `--gate-backend`) | `test_delegate_dispatcher.py::test_ready_state_has_identity`, `test_not_installed_when_version_binary_missing`, `test_not_authenticated_when_auth_probe_fails`, `test_disabled_workspace_outranks_user_enable`, `test_disabled_user`, `test_retired_backend_reports_retired`, `test_cmd_setup_runs_backends_in_parallel`, `test_cmd_setup_unknown_backend_exits_2` |
| 3 | `/codex:review` command | `delegate` skill → `delegate.py review [--base REF] [--scope auto\|working-tree\|branch]` (always read-only) | `test_delegate_dispatcher.py::test_working_tree_scope_captures_uncommitted_changes`, `test_branch_scope_uses_base_ref`, `test_auto_scope_falls_back_to_working_tree`, `test_review_forces_read_only_args` |
| 4 | `/codex:adversarial-review` command | `delegate.py review --adversarial [FOCUS...]` (JSON-schema envelope, severity-first findings) | `test_delegate_dispatcher.py::test_adversarial_switches_prompt_with_focus`, `test_findings_presented_severity_first_in_envelope`, `test_valid_envelope_satisfies_schema_required_fields` |
| 5 | `/codex:status` command | `delegate.py status [JOB_ID\|--all] [--wait [--timeout N]]` | `test_delegate_jobs.py::test_background_spawn_status_result`, `test_delegate_dispatcher.py::test_reap_marks_dead_worker_as_failed`, `test_reap_noop_on_terminal_job` |
| 6 | `/codex:result` command | `delegate.py result JOB_ID` | `test_delegate_jobs.py::test_background_spawn_status_result`, `test_result_on_active_job_exit_1` |
| 7 | `/codex:cancel` command | `delegate.py cancel JOB_ID` | `test_delegate_jobs.py::test_cancel_active_job`, `test_cancel_already_terminal_is_noop_exit_0`; unconditional-cancel semantics change is D-noted below |
| 8 | `/codex:transfer` command | `delegate.py transfer --backend NAME [--source TRANSCRIPT]` (per-backend declared `transfer` contract in `config/backends.json`, `null` = unsupported) | `test_delegate_dispatcher.py::test_unknown_backend_exits_2` (transfer suite), `test_backend_without_transfer_support_offers_task`, `test_source_outside_transcript_roots_rejected`, `test_missing_source_and_env_exits_2`, `test_app_server_import_success_returns_resume_command`, `test_resolves_under_allowed_root`, `test_rejects_path_outside_roots` |
| 9 | Stop hook (900s, review gate) | `plugins/manifest-delegate/hooks/hooks.json` Stop entry → `delegate.py gate` (per T034; default OFF, toggled via `delegate.py setup --enable/--disable-review-gate --gate-backend`) | `delegate.py gate` dispatch itself: `test_delegate_dispatcher.py::test_gate_budget_capped_and_reported`; hook wiring content-audited by `tests/bats/delegate_plugin.bats`: `"hooks.json is valid JSON"`, `"hooks.json declares exactly Stop, SessionStart, SessionEnd"`, `"hooks.json timeouts are 900/5/5 for Stop/SessionStart/SessionEnd"`, `"hooks.json commands use \${CLAUDE_PLUGIN_ROOT}, never an absolute path"`, `"hooks.json referenced scripts exist and are executable"`, `"stop hook subprocess call to delegate.py gate outlasts the backend budget cap"`, `"stop_gate_hook.py fails open (exit 0) when transcript_path is missing"` |
| 10 | SessionStart/End hooks (5s, env capture + cleanup) | `plugins/manifest-delegate/scripts/session_hook.py` (SessionStart: capture session id + transcript path; SessionEnd: orphan-job + reap cleanup) per T033 | Job-reap logic: `test_delegate_dispatcher.py::test_reap_marks_dead_worker_as_failed`, `test_reap_noop_on_terminal_job`; hook wiring content-audited by `tests/bats/delegate_plugin.bats`: `"hooks.json is valid JSON"`, `"hooks.json timeouts are 900/5/5 for Stop/SessionStart/SessionEnd"`, `"hooks.json referenced scripts exist and are executable"`, `"stop_gate_hook.py and session_hook.py are --help compliant"`, `"SessionStart/SessionEnd hooks respond exit 0 to a minimal payload (no gate subcommand invoked)"` |
| 11 | `codex-cli-runtime` internal skill | `skills/delegate/references/prompting-codex.md` (+ `prompting-claude.md`, `prompting-agy.md` for the other backends) | Referenced from `skills/delegate/SKILL.md` "Before composing a delegation prompt"; no dedicated unit test (reference doc, not executable) — covered structurally by skill-catalog/budget gates, not `test_delegate_*` |
| 12 | `codex-result-handling` internal skill | `skills/delegate/references/result-envelope.md` (envelope schema + non-autonomy presentation rules, backend-agnostic) | `test_delegate_dispatcher.py::test_extracts_last_fenced_json_block`, `test_no_fenced_block_is_failure_never_fabricated`, `test_empty_output_is_failure`, `test_malformed_json_block_is_failure`, `test_missing_required_fields_is_failure`, `test_failure_outcome_without_error_gets_synthesized`, `test_valid_envelope_satisfies_schema_required_fields` |
| 13 | `gpt-5-4-prompting` skill (+3 refs) | Folded into `skills/delegate/references/prompting-codex.md` (backend-scoped, not a standalone skill — one skill, one dispatcher, per research.md D-decisions) | Same reference-doc caveat as row 11: no dedicated unit test; block-structured contract conventions are prose guidance consumed by the agent, not executable code |

## Uninstalling the baseline

```bash
claude plugin uninstall codex
```

This removes `openai/codex-plugin-cc` (marketplace id `openai-codex`) and its
Stop/SessionStart/SessionEnd hooks, job state under
`${CLAUDE_PLUGIN_DATA}/state/`, and the detached broker process. It does not
touch `manifest-delegate` state (separate plugin data directory).

## Gate exclusivity (D7)

Only one Stop-time review gate may be active per workspace. Before enabling
`manifest-delegate`'s gate (`delegate.py setup --enable-review-gate`),
disable the baseline's equivalent gate first:

```bash
claude codex setup --disable-review-gate   # baseline, if still installed
delegate.py setup --enable-review-gate --gate-backend <id>   # manifest-delegate
```

Running both simultaneously produces two competing Stop-hook verdicts on the
same session; there is no merge or precedence rule between the two plugins.
Uninstalling the baseline (above) also removes its gate, which is the
cleaner path once migration is complete.

## Read-only-by-default posture change (D8)

The baseline's `/codex:rescue` is **write-capable by default** — it can edit
files unless explicitly scoped otherwise. `manifest-delegate` inverts this:
every backend defaults to **read-only** for `task`, `review`, and
second-opinion calls; write access requires an explicit `--write` scope. This
is a deliberate posture change, not a parity gap — a delegated agent that can
silently write to the workspace is the incident class D8 exists to close.
Callers relying on the baseline's implicit-write behavior must add `--write`
explicitly after migrating.

## `--effort` disposition (SC-002 settled)

The baseline's `/codex:rescue --effort` (low/medium/high reasoning effort) is
**deliberately not carried forward as a dispatcher flag**. Effort selection
folds into `--model` tier selection instead (`config/backends.json` model
tiers per backend) — there is no `--effort` flag on `delegate.py`, and this is
not a missing feature. This row's SC-002 traceability is settled by this
paragraph, not by a table row, since there is no baseline entry point # for
it (it was a flag on row 1, not a standalone entry point).

## Principle VII activation note

If `manifest-delegate` is ever published to a marketplace external to this
repo, Principle VII (constitution: external-distribution obligations) applies
and must be re-evaluated at that time — it is inactive while the plugin is
repo-local.
