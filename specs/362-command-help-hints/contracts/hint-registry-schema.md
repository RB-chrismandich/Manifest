# Contract: Hint Registry Schema (`hint_registry.yml`)

Declarative mapping of Workflow Moments → commands to surface. Read by `guidance_hint.py`.

## Schema

```yaml
moments:
  - id: pre-commit
    trigger: "PreToolUse:git-commit"
    description: "About to create a git commit"
  - id: pr-open
    trigger: "PreToolUse:pr-create"
    description: "Opening a pull/merge request"
  - id: refactor-start
    trigger: "command-invoke:refactor-*"
    description: "Invoking a language refactor command"
  - id: high-context
    trigger: "context-high"
    description: "Context usage is high"

rules:
  - moment_id: pre-commit
    command_refs: ["verify", "project-commit"]
    message: "Before committing: /verify to lint+test, or /project-commit for the full pipeline."
    priority: 10
    dedup_key: commit-guidance
    category: hint
  - moment_id: high-context
    command_refs: ["checkpoint"]
    message: "Context is high — consider /checkpoint to save progress."
    priority: 10
    dedup_key: context-guidance
    category: reminder
    rate_limit: 30m
```

## Validation contract

| Rule | Enforcement |
|------|-------------|
| `rules[].command_refs` resolve to catalog commands | dangling ref → registry validation error (fails CI) |
| `rules[].moment_id` resolves to a `moments[].id` | unknown moment → error |
| `moments[].trigger` supported by `ai-hooks-integration` | unknown trigger → error |
| `category: reminder` ⇒ `rate_limit` present | missing → error |
| dedup | rules sharing `dedup_key` collapse to one surfaced hint per moment |
| ordering | surfaced hints sorted by `priority` desc (FR-006) |

## Emission contract (`guidance_hint.py`)

- Receives the hook payload (moment), applies `GuidancePreference` gating (see data-model state transition), emits **one-shot** text, updates `last_fired`.
- Emits nothing (exit 0) when suppressed — fail-open, never blocks the underlying action.
