---
name: session-checkpoint
description: Create a compact checkpoint summary of the current session so work can continue reliably when context usage is high.
---

# Checkpoint Context Command

Summarize and compress conversation history when context usage is high to prevent loss of important information.

## Arguments

- `$ARGUMENTS` — Optional threshold percentage (default: 95). Trigger checkpoint at this usage level.

---

## Task

When context usage exceeds the threshold (default 95%), create a compressed summary of the conversation that preserves:

1. Key decisions and outcomes
2. Code changes made
3. Important discoveries or blockers
4. Action items and next steps
5. User preferences established

## Instructions

### Step 1: Check Usage and Decide

Parse the most recent system warning for token usage. Use the window size the
warning actually reports as the denominator — do not hardcode it (200K on some
models, 1M on others):

```text
Token usage: X/<window>; Y remaining
```

Calculate percentage used: `(X / <window>) * 100`. If usage is below the
threshold, inform the user and exit.

### Step 2: Gather and Write the Summary

Scan the conversation for decisions, code changes, commands used, blockers,
and user preferences. Write a structured summary to the scratchpad using the
template in [references/summary-template.md](references/summary-template.md),
deriving `<window>` from the reported token warning and filling every
section from the conversation:

```bash
SUMMARY_FILE="$SCRATCHPAD/conversation_summary_$(date +%Y%m%d_%H%M%S).md"
```

### Step 3: Update Memory

Extract key learnings and update memory files:

- **Global memory** (`~/.claude/memory/MEMORY.md`): new general patterns,
  common errors and their solutions.
- **Project memory** (`~/.claude/projects/.../memory/MEMORY.md`): project-specific
  insights, recent changes, new conventions.

### Step 4: Inform User

Report usage (X/<window>, Z%), the summary path, and a quick-reference list
(files changed, commits, decisions, top 3 next steps). Conversation can
continue with preserved context in memory and summary.

---

## Automatic Trigger

This command should be **auto-invoked** when:

1. Context usage exceeds 95% of the reported window
2. Before starting any new major task
3. User explicitly runs `/session-checkpoint`

## Example Usage

```bash
# Auto-triggered at 95%
# (no user action needed)

# Manual trigger
/session-checkpoint

# Custom threshold
/session-checkpoint 90
```

---

## Notes

- Summaries are cumulative - each checkpoint builds on previous summaries
- Critical code snippets preserved in summary
- Memory files updated with learnings
- User can review summary anytime via scratchpad path
- Original conversation history remains in Claude's system (until automatic summarization)

---

## Related

- Memory system: `~/.claude/memory/MEMORY.md`
- Project memory: `~/.claude/projects/.../memory/MEMORY.md`
- Scratchpad directory: Session-specific temp storage
