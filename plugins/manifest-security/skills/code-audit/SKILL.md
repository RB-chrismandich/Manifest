---
name: code-audit
description: Auto-trigger on security-sensitive code (auth, crypto, secrets, input validation), large files (>500 lines), or complex files (>10 functions/>5 classes). Gives code-audit and security feedback without blocking user flow.
---

# Code Quality Analysis Skill

This skill automatically activates when Claude detects code patterns that warrant proactive security or quality review.

## Trigger Criteria

### Security Patterns (Immediate Trigger)

Activate when code contains any of these patterns:

**Authentication/Authorization**:

- `auth`, `login`, `logout`, `session`
- `jwt`, `oauth`, `token`, `bearer`
- `authenticate`, `authorize`, `permission`

**Cryptography**:

- `crypto`, `encrypt`, `decrypt`
- `hash`, `digest`, `hmac`
- `salt`, `iv`, `nonce`
- `private_key`, `public_key`, `certificate`

**Secrets Handling**:

- `secret`, `password`, `credential`
- `api_key`, `access_key`, `token`
- `connection_string`, `database_url`

**Input Validation**:

- `sanitize`, `validate`, `escape`
- `filter`, `whitelist`, `blacklist`
- `regex`, `pattern`, `input`

### Complexity Patterns (Immediate Trigger)

Activate when file metrics exceed thresholds:

| Metric | Threshold | Rationale |
|--------|-----------|-----------|
| File lines | >500 | God class indicator |
| Function count | >10 | Single responsibility violation |
| Class count | >5 | Module doing too much |
| Cyclomatic complexity | >15 | Hard to test/maintain |

## Behavior

When triggered, this skill:

0. **Loads local doctrine and known issues.** Read
   `../../runtime/references/code-constitution.md` and
   `../../runtime/references/antipatterns.md`, then consult the mutable knowledge
   base for the detected language:

   ```bash
   manifest-workspace:learning-capture query --language <detected-language> --format llm
   ```

   If relevant entries exist, include them as additional check items. This is
   **non-blocking** — skip if the query fails or returns empty.

1. **Scans the file** for security patterns and complexity metrics
2. **Invokes parallel agents** for cross-verification:

   ```bash
   manifest-workspace:parallel-agent --json --validate --analyze <file>
   ```

   **Sub-agent dispatch**: pin this fan-out call to Sonnet explicitly
   (`subagent_model: sonnet` per `command_config.yml`) — never inherit the
   session's model, which can silently bill premium rates for a routine
   verification pass.

3. **Reports findings inline** without blocking user workflow
4. **Escalates critical issues** that require immediate attention

## Analysis Scope

### Security Checks

| Check | Severity | Pattern |
|-------|----------|---------|
| Hardcoded secrets | Critical | `password =`, `secret =`, `api_key =` |
| SQL injection | Critical | f-strings in SQL queries |
| Command injection | Critical | User input in `subprocess`, `os.system` |
| Unsafe deserialization | Critical | `pickle.load`, `yaml.load` (not safe_load) |
| Bare exceptions | High | `except:` without specific exception |
| Empty catch blocks | High | `catch {}` or `catch (e) {}` with no handling |
| Missing input validation | High | External data used without validation |

### Quality Checks

| Check | Severity | Pattern |
|-------|----------|---------|
| God class | Medium | File >500 lines |
| Long function | Medium | Function >100 lines |
| Too many parameters | Low | Function with >5 parameters |
| Missing type hints | Low | Function without return type |
| Magic numbers | Low | Unexplained numeric literals |

### Registry Anti-Patterns (advisory)

On trigger, additionally consult the antipattern entries returned by the
bundle-local `manifest-workspace:learning-capture query` call above. Every entry carrying
exactly one guardrail-category tag (`arch`, `async-state`, `error-handling`,
`security`, `dependency`, `iteration`) — including
`provenance: session-capture` entries added after this skill shipped — defines
a `detection_cue` and a `prevention_rule`.

- Match the code being written/reviewed against the entries' detection cues
  (use the cue for the file's language when the cue is a per-language map).
- For each match, report inline: entry ID, title, severity, and the entry's
  `prevention_rule` as the suggested fix.
- These findings are **advisory and non-blocking** (spec 457 FR-011): they
  never gate or interrupt the workflow. Blocking remains exclusive to the
  Tier 1 validation gates (`validation_criteria.yml`).
- Full per-entry detail: `../../runtime/references/antipatterns.md`. For a
  systematic whole-codebase review, suggest `manifest-code-quality:ai-code-audit` instead of
  expanding inline feedback.

### Optional Semgrep pass

Semgrep is optional. Run it only when the user selected the `semgrep`
capability or the requested audit mode explicitly requires Semgrep. Its absence
must not fail the default inline audit. If a selected or explicitly requested
Semgrep mode lacks the executable, fail that mode with an actionable capability
message instead of silently claiming the scan ran.

## Output Format

When triggered, report findings in this format:

```markdown
## Code Quality Analysis

**File**: `path/to/file.py`
**Triggered by**: [Security pattern | Complexity threshold]

### Findings

| Severity | Issue | Location | Recommendation |
|----------|-------|----------|----------------|
| Critical | Hardcoded API key | Line 45 | Move to environment variable |
| High | Bare exception | Line 112 | Catch specific exception |
| Medium | Long function | Lines 200-350 | Extract helper methods |

### Summary
- Critical: X issues (must fix before merge)
- High: X issues (should fix soon)
- Medium: X issues (refactor when possible)

### Parallel Agent Consensus
- Agent A: [Key finding]
- Agent B: [Key finding]
- Consensus: XX% (HIGH/MEDIUM/LOW)
```

## Non-Blocking Behavior

This skill provides information without interrupting user workflow:

- **Never blocks** code execution or user commands
- **Reports inline** when patterns detected
- **Suggests fixes** but doesn't auto-apply
- **Escalates only** for Critical severity findings

## Integration with Commands

This skill works alongside `manifest-code-quality:python-refactor`:

- **Skill**: Lightweight, auto-triggered, inline feedback
- **Command**: Comprehensive, user-invoked, full report

When both trigger:

1. Skill provides immediate feedback
2. User can invoke `manifest-code-quality:python-refactor` for detailed analysis
3. Results are complementary, not duplicated

## Configuration

Use these bundle-owned defaults unless the user supplies explicit thresholds for
the current invocation:

```yaml
thresholds:
  skill_file_lines: 500
  skill_function_count: 10
  skill_class_count: 5
  skill_cyclomatic_complexity: 15

security_patterns:
  - auth|login|session|jwt
  - crypto|encrypt|hash|secret
  - api_key|password|token|credential
```

## Prioritization

When multiple issues found, prioritize by:

1. **Security** - Always first
2. **Correctness** - Bugs and logic errors
3. **Performance** - Efficiency issues
4. **Maintainability** - Code quality
5. **Style** - Formatting and conventions
