# Context Monitoring Prompt

**Purpose**: Auto-trigger `/checkpoint` when <5% context remains.

## Trigger Condition

```text
if (tokens_used / 200000) >= 0.95:
    auto_invoke("/checkpoint")
```

## Auto-trigger Message

```text
⚠️ CONTEXT CHECKPOINT TRIGGERED

Usage: X/200000 (Y% used, Z% remaining)
Auto-invoking /checkpoint to preserve history...
```
