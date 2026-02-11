---
name: antipattern-detect
description: |
  Auto-triggered skill that analyzes linting failures, test results, and code
  review feedback to detect recurring antipatterns. Stores findings in
  docs/KNOWLEDGE_BASE.md for team-wide visibility.
---

# Antipattern Detection Skill

This skill automatically activates after linting failures, test failures, or code
review feedback to identify recurring antipatterns. It documents findings in
`docs/KNOWLEDGE_BASE.md` for team reference.

## Trigger Criteria

Activate when any of the following are detected in the current session:

| Trigger | Detection Method |
|---------|-----------------|
| Lint failure | Exit code != 0 from ruff, eslint, golangci-lint, tflint |
| Test failure | Exit code != 0 from pytest, go test, vitest, terratest |
| Security finding | Any finding from bandit, gosec, npm audit, tfsec |
| Repeated pattern | Same issue type seen 3+ times across files |
| Code review feedback | Parallel agent consensus flags a recurring concern |

---

## Analysis Process

### Step 1: Collect Failure Data

Gather from the current session:

- Linter output (error codes, rule names, affected lines)
- Test output (failure messages, assertion errors)
- Security scan output (vulnerability types, severity)
- Agent review feedback (concerns raised by 2+ agents)

### Step 2: Pattern Classification

Classify each failure into an antipattern category:

| Category | Examples |
|----------|---------|
| `security` | Hardcoded secrets, SQL injection, unsafe deserialization |
| `error-handling` | Bare exceptions, silent failures, missing error boundaries |
| `performance` | N+1 queries, unbounded loops, missing pagination |
| `type-safety` | Missing type hints, `any` overuse, unchecked casts |
| `testing` | Missing edge cases, brittle assertions, test pollution |
| `architecture` | Circular imports, god classes, tight coupling |
| `naming` | Misleading names, inconsistent conventions, abbreviations |
| `duplication` | Copy-paste code, reimplemented stdlib, redundant logic |

### Step 3: Deduplication

Before adding a new antipattern, check `docs/KNOWLEDGE_BASE.md` for existing entries:

- Match by category + language + pattern description
- If a match exists, increment the `occurrences` counter and update `last_seen`
- Only create a new entry if no similar pattern is documented

### Step 4: Generate Entry

For each new antipattern, generate a documentation entry:

````markdown
### {ANTI-NNN}: {Title}

- **Category**: {category}
- **Language**: {language}
- **Severity**: {high|medium|low}
- **Occurrences**: {count}
- **First seen**: {date}
- **Last seen**: {date}

**Problem**: {1-2 sentence description of the antipattern}

**Example** (bad):
```{language}
{code example showing the antipattern}
```

**Fix** (good):

```{language}
{code example showing the correct pattern}
```

**Detection**: {How to catch this -- linter rule, test pattern, review checklist}

````

---

## Storage: docs/KNOWLEDGE_BASE.md

Maintain the knowledge base file with this structure:

```markdown
# Knowledge Base: Antipatterns & Lessons Learned

> Auto-maintained by the antipattern-detect skill. Manual edits welcome.
> Last updated: {ISO-8601}

## Table of Contents

- [Security](#security)
- [Error Handling](#error-handling)
- [Performance](#performance)
- [Type Safety](#type-safety)
- [Testing](#testing)
- [Architecture](#architecture)

## Security

### ANTI-001: Hardcoded API Keys
...

## Error Handling

### ANTI-005: Bare Exception Handlers
...
```

### ID Generation

Format: `ANTI-NNN` where NNN is a zero-padded sequential number. Find the
highest existing ID and increment.

### File Creation

If `docs/KNOWLEDGE_BASE.md` does not exist, create it with the header structure
and an empty table of contents. Create the `docs/` directory if needed.

---

## Non-Blocking Behavior

This skill follows the same non-blocking pattern as `code-quality`:

- **Never blocks** user workflow or command execution
- **Reports inline** when an antipattern is detected
- **Writes to docs/** asynchronously after primary task completes
- **Suggests fixes** but does not auto-apply changes

---

## Integration

This skill complements other skills:

| Skill | Relationship |
|-------|-------------|
| `code-quality` | Feeds security/quality findings into antipattern detection |
| `learning-loop` | Antipatterns can be promoted to knowledge base entries |
| `verify` | Lint/test failures trigger antipattern analysis |

When both `code-quality` and `antipattern-detect` trigger:

1. `code-quality` provides immediate inline feedback
2. `antipattern-detect` documents the pattern for future reference
3. Results are complementary, not duplicated

---

## Safety Checks

- Never modify source code -- only writes to `docs/KNOWLEDGE_BASE.md`
- Validate markdown structure before writing
- Back up existing `KNOWLEDGE_BASE.md` before appending (copy to `.bak`)
- Cap entries at 200 per file (suggest splitting by category if exceeded)
- Sanitize code examples to remove actual secrets or credentials
