# Quickstart: Multi-Agent Delegation Plugin

**Feature**: `675-multi-agent-delegation` — validates the plan end to end once
implemented. Commands assume Claude Code with the `manifest` marketplace
configured (any fresh workspace: standard marketplace flow only, SC-005).

## 1. Install

```bash
claude plugin install manifest-delegate@manifest
```

## 2. Check readiness (US2)

```
/manifest-delegate:delegate-setup
```

Expected: one row per backend (codex, claude, antigravity) with
ready/not_installed/not_authenticated/disabled state, version, and an exact
fix for anything unready — completes in under 30s, no interactive prompts.

## 3. Delegate a task (US1)

```
/manifest-delegate:delegate use codex to explain the failing test in tests/python/test_x.py
/manifest-delegate:delegate --backend claude same task
/manifest-delegate:delegate --backend agy same task
```

Expected: each ready backend returns the same envelope shape (backend/model
attribution, outcome, attempted, changes, follow-ups). With no backend named,
the configured default (factory: codex) is used and stated. Delegations are
read-only unless you say to write (`--write`).

Background + job management (FR-014):

```
/manifest-delegate:delegate --background <task>     # returns a job id
/manifest-delegate:delegate status                  # job table
/manifest-delegate:delegate result <job-id>
/manifest-delegate:delegate cancel <job-id>
```

Follow-up on the same backend conversation (FR-015):

```
/manifest-delegate:delegate --resume-last apply the top recommendation
```

## 4. Second opinion (US3)

```
/manifest-delegate:delegate --second-opinion --of <job-id> --backend claude
```

Expected: second backend receives the shared context; both findings shown,
clearly attributed. Naming the same backend warns and offers the others.

## 4b. Standalone review / adversarial review (SC-002 parity)

```
/manifest-delegate:delegate review --backend claude --scope working-tree
/manifest-delegate:delegate review --adversarial --backend codex focus: rollback safety
```

Expected: read-only review of local git state on the chosen backend
(foreground or `--background`), findings severity-first in the normalized
envelope, never auto-applied.

## 5. Finish-time review gate (US4 — off by default)

```
/manifest-delegate:delegate-setup --enable-review-gate --gate-backend codex
```

Complete a small code change; on completion the gate pauses **once** (≤ its
budget, default 600s), presents findings, and you decide — it never loops and
never applies fixes. Unready gate backend ⇒ completion proceeds with a note.
Disable again: `--disable-review-gate`.

## 6. Configure (FR-013 / SC-007)

Edit `~/.claude/config/delegation.json` (the canonical file setup creates):

```json
{
  "default_backend": "claude",
  "backends": {
    "antigravity": { "enabled": false },
    "codex": { "model": "advanced", "budget_seconds": 900 }
  }
}
```

Next invocation honors it — no reinstall. A hand-authored `delegation.yml`
(same schema) is honored when PyYAML is importable, and setup updates it in
place only in that case — otherwise setup writes `delegation.json`, which
takes precedence, and reports the unreadable `.yml`. Delete the file
to return to factory defaults. A malformed or unreadable file is reported and
factory defaults apply.
A workspace `services.yml` disable always outranks a user enable, and the
readiness report names the blocking layer.

## 7. Migrate off the baseline codex plugin (SC-006)

Follow `plugins/manifest-delegate/MIGRATION.md` (all 13 baseline entry points
mapped, e.g. `/codex:rescue` → `/manifest-delegate:delegate --backend codex`,
`/codex:transfer` → `... transfer --backend codex`). Disable the baseline's
review gate before enabling the new one, then:

```bash
claude plugin uninstall codex
```

Expected: every baseline capability remains reachable through
`manifest-delegate` (SC-002 traceability table in MIGRATION.md).

## Verification hooks (Constitution VI)

Smoke tests cover: delegate-per-backend (mocked CLIs), readiness with one
unready backend, background status/result/cancel, gate on/off. Fault-injection
suite asserts SC-004 (every failure explicit, attributed, actionable).
