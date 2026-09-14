# Session Checkpoint — Summary Template

Fill this template when producing a checkpoint (Step 3 of the skill). `<window>`
is the total context size reported by the most recent system warning, not a
fixed constant — derive it, do not assume 200K.

## Contents

Session Overview · Key Decisions · Code Changes · Commands Executed · Blockers &
Resolutions · User Preferences · Action Items · Next Steps · Context for
Continuation · Preserved Code Snippets · Technical Context

````markdown
# Conversation Summary - [YYYY-MM-DD HH:MM]

**Context Usage**: X/<window> (Z%)
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

### Modified Files (N files)
- `path/to/file3.ext` - [what changed]

### Deleted Files (N files)
- `path/to/file5.ext` - [reason for deletion]

---

## Commands Executed

| Command | Purpose | Outcome |
|---------|---------|---------|
| `/git-commit` | Create comprehensive commit | ✅ Success (commit 03e67ee) |
| `/python-refactor` | Analyze codebase | ⚠️ Found 3 issues |

---

## Blockers & Resolutions

1. **[Blocker]**
   - Issue: [description]
   - Resolution: [how it was resolved]
   - Outcome: [result]

---

## User Preferences Noted

- Prefers [X] over [Y] for [use case]
- Coding style: [preferences noted]

---

## Action Items

### Completed
- [x] Item 1

### Pending
- [ ] Item 3

---

## Next Steps

1. [Next logical step based on conversation]
2. [Follow-up task]

---

## Context for Continuation

If conversation continues after checkpoint:
- Current working directory: `[pwd]`
- Active branch: `[git branch]`
- Recent commit: `[git log -1]`

---

## Preserved Code Snippets

### [Snippet 1 Name]
```language
[Important code snippet that should be preserved]
```

**Context**: [why this is important]

---

## Technical Context

- Platform: [macOS/Linux]
- Key dependencies: [list]
- Configuration files: [relevant configs]

````

## Durable Continuity Payload

When persistence is required, retain the summary above and derive the following
JSON payload from it. Pass the completed payload to
`session_continuity.py checkpoint --input <payload.json>`. Use concise evidence
summaries, never raw transcripts or secrets.

```json
{
  "source_session_id": "harness session identifier",
  "original_goal": "The user's original goal, preserved without narrowing it",
  "constraints": ["Immutable user, repository, and safety constraints"],
  "decisions": [{"decision": "Accepted decision", "rationale": "Evidence-backed reason"}],
  "repository": {
    "path": "/absolute/repository/path",
    "branch": "current branch",
    "head": "full HEAD commit",
    "dirty_tree": ["Exact git status --short entries"]
  },
  "completed_work": ["Concrete completed deliverable"],
  "remaining_work": ["Work still required by the original goal"],
  "verification_evidence": [{
    "command": "Exact command that ran",
    "outcome": "Exit status and concise result",
    "evidence": "Durable result or artifact preserved in this checkpoint"
  }],
  "unresolved_uncertainty": ["Fact not established from authoritative state"],
  "next_action": "Exactly one bounded action for the continuing session",
  "live_operations": [{
    "owner": "Session or actor currently responsible",
    "handle": "Durable process, job, PR, or task handle",
    "status": "Authoritatively observed current status",
    "obligation": "How continuation must monitor without restarting or duplicating"
  }],
  "continuation_goal": "Copyable goal preserving objective, constraints, state checks, remaining work, verification duties, live-operation ownership, and the one next action"
}
```

Use empty arrays when a list has no entries. Required scalar values must not be
empty. The runtime stores a SHA-256 digest in its envelope and rejects later
reads whose content no longer matches it.
