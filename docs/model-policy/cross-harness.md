# Cross-Harness Skill Model Policy

> How model tiers map across Claude, Cursor, Codex, and Antigravity.

## Cross-Harness Skill Model Policy

Skills may declare portable, ordered tiers without embedding provider model IDs:

```yaml
models:
  codex: [advanced, flash, auto]
  gemini: [pro, flash, auto]
  antigravity: [advanced, flash, auto]
  cursor: [advanced, flash, auto]
model_fallback:
  mode: confirm
```

`agy` is accepted on input and normalized to `antigravity`. Chains contain one
to four unique tiers; `auto`, when supported, is final. Concrete IDs remain in
`configs/claude/config/parallel_agent.yml`.

Precedence is explicit CLI/session choice, skill frontmatter, then the global
`confirm` default. `--model` replaces the chain unless `--model-chain` supplies
subsequent fallbacks. Authentication, configuration, safety, malformed output,
task errors, unknown evidence, and truncated evidence never trigger fallback.
Model unavailability, rate limits, transient provider failures, capacity,
quota, and billing failures are eligible.

Non-interactive and JSON execution never prompts. Confirm mode returns a
recovery command; auto mode advances. Provider evidence is retained only while
classifying a bounded attempt. Durable summaries are allowlisted, redacted,
and size bounded; task text is never stored in job state.

Confirm-mode recovery is versioned and identity-bound. Approval requires the
printed job version, `recovery_id`, and a freshly resubmitted task through stdin
or `--task-file`. Reject/cancel validates only the job version and recovery
identity, then terminates as `fallback_rejected` without resolving a backend or
reading task/payload input. The background ownership protocol is durable:
`spawned -> worker_owned -> backend_started -> terminal`; an unprovable loss at
or after ownership becomes non-resumable `dispatch_unknown`, never an automatic
retry.

Second-opinion dispatch is also a fresh attempt. It accepts only bounded
`title`/`detail`/`severity` findings tied to the source job's current attempt,
plus freshly resubmitted task text. It excludes prior prompt summaries, raw
provider output/errors, session references, full envelopes, and attempt history.

Use an explicit model-aware entry point when policy must apply:

```bash
printf '%s' 'the task' | manifest skill-run path/to/SKILL.md --harness codex
```

Ordinary native skill invocation retains the harness default.

---

[← Model Policy](../MODEL-POLICY.md)
