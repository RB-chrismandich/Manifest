---
name: code-quality
description: Auto-trigger on security-sensitive code (auth, crypto, secrets, input validation), large files (>500 lines), or complex files (>10 functions/>5 classes). Gives code-quality and security feedback without blocking user flow.
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

0. **Consults knowledge base** for known issues in the detected language:

   ```bash
   ~/.claude/scripts/learning_capture.sh query --language <detected-language> --format llm
   ```

   If relevant entries exist, include them as additional check items. This is
   **non-blocking** — skip if the query fails or returns empty.

1. **Scans the file** for security patterns and complexity metrics
2. **Invokes parallel agents** for cross-verification:

   ```bash
   ~/.claude/scripts/parallel_agent.py --json --validate --analyze <file>
   ```

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
- Gemini: [Key finding]
- Cursor: [Key finding]
- Consensus: XX% (HIGH/MEDIUM/LOW)
```

## Non-Blocking Behavior

This skill provides information without interrupting user workflow:

- **Never blocks** code execution or user commands
- **Reports inline** when patterns detected
- **Suggests fixes** but doesn't auto-apply
- **Escalates only** for Critical severity findings

## Integration with Commands

This skill works alongside the `/refactor-python` command:

- **Skill**: Lightweight, auto-triggered, inline feedback
- **Command**: Comprehensive, user-invoked, full report

When both trigger:

1. Skill provides immediate feedback
2. User can invoke `/refactor-python` for detailed analysis
3. Results are complementary, not duplicated

## Configuration

Thresholds can be customized in `~/.claude/config/command_config.yml`:

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
