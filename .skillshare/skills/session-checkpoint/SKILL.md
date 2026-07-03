---
name: session-checkpoint
description: |
  Create a compact checkpoint summary of the current session so work can continue
  reliably when context usage is high.
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

### Step 1: Check Current Context Usage

Parse the most recent system warning for token usage:

```text
Token usage: X/200000; Y remaining
```text

Calculate percentage used: `(X / 200000) * 100`

If usage < threshold, inform user and exit.

### Step 2: Analyze Conversation History

Scan the conversation for:

- **Decisions**: User choices, architectural decisions, approach selections
- **Code Changes**: Files created, modified, or deleted
- **Commands Used**: Skills/commands invoked and their results
- **Blockers**: Issues encountered and how they were resolved
- **Preferences**: User-stated preferences for tools, patterns, approaches

### Step 3: Create Compact Summary

Generate a structured summary in the scratchpad directory:

```markdown
# Conversation Summary - [YYYY-MM-DD HH:MM]

**Context Usage**: X/200000 (Z%)
**Trigger Threshold**: 95%

---

## Session Overview

**Started**: [timestamp from first message]
**Duration**: [approximate]
**Primary Goal**: [main task user requested]

---

## Key Decisions

1. **[Decision 1]**
   - Context: [why decision was needed]
   - Choice: [what was decided]
   - Rationale: [reasoning]

2. **[Decision 2]**
   - ...

---

## Code Changes

### Created Files (N files)
- `path/to/file1.ext` - [brief description]
- `path/to/file2.ext` - [brief description]

### Modified Files (N files)
- `path/to/file3.ext` - [what changed]
- `path/to/file4.ext` - [what changed]

### Deleted Files (N files)
- `path/to/file5.ext` - [reason for deletion]

---

## Commands Executed

| Command | Purpose | Outcome |
|---------|---------|---------|
| `/project-commit` | Create comprehensive commit | ✅ Success (commit 03e67ee) |
| `/refactor-python` | Analyze codebase | ⚠️ Found 3 issues |

---

## Blockers & Resolutions

1. **[Blocker]**
   - Issue: [description]
   - Resolution: [how it was resolved]
   - Outcome: [result]

---

## User Preferences Noted

- Prefers [X] over [Y] for [use case]
- Uses [tool/pattern] for [scenario]
- Coding style: [preferences noted]

---

## Action Items

### Completed
- [x] Item 1
- [x] Item 2

### Pending
- [ ] Item 3
- [ ] Item 4

---

## Next Steps

1. [Next logical step based on conversation]
2. [Follow-up task]
3. [Recommendation for user]

---

## Context for Continuation

If conversation continues after checkpoint:
- Current working directory: `[pwd]`
- Active branch: `[git branch]`
- Recent commit: `[git log -1]`
- Open files: [list if relevant]

---

## Preserved Code Snippets

### [Snippet 1 Name]
```language
[Important code snippet that should be preserved]
```text

**Context**: [why this is important]

---

## Technical Context

- Platform: [macOS/Linux]
- Key dependencies: [list]
- Configuration files: [relevant configs]

---

_

```text

### Step 4: Save Summary

Save to scratchpad:
```bash
SUMMARY_FILE="$SCRATCHPAD/conversation_summary_$(date +%Y%m%d_%H%M%S).md"
# Write summary content
echo "✅ Summary saved to: $SUMMARY_FILE"
```text

### Step 5: Update Memory

Extract key learnings and update memory files:

**Global memory** (`~/.claude/memory/MEMORY.md`):

- Add any new general patterns discovered
- Note common errors encountered and solutions

**Project memory** (`~/.claude/projects/.../memory/MEMORY.md`):

- Add project-specific insights
- Update recent changes section
- Note new patterns or conventions

### Step 6: Inform User

Present summary to user:

```markdown
## 🗜️ Context Compacted

**Usage**: 192,000/200,000 (96%)
**Summary saved**: [path]

### Quick Reference
- **Files changed**: [count]
- **Commits**: [count]
- **Decisions**: [count]
- **Next steps**: [list top 3]

To review full summary:
```bash
cat [summary_path]
```text

Conversation can continue with preserved context in memory and summary.

```text

---

## Automatic Trigger

This command should be **auto-invoked** when:
1. Context usage > 95% (190,000/200,000 tokens)
2. Before starting any new major task
3. User explicitly runs `/checkpoint`

## Example Usage

```bash
# Auto-triggered at 95%
# (no user action needed)

# Manual trigger
/checkpoint

# Custom threshold
/checkpoint 90
```text

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
