# Validation Task

Validate the proposed code changes against tiered criteria.

## Code to Validate

{CODE_OR_DIFF}

## Tier 1 Criteria (Critical - All must pass)

These are blocking criteria. Any failure requires resolution before proceeding.

| Criterion | Weight | Description |
|-----------|--------|-------------|
| Cross-Verification | 0.30 | Changes align with multi-agent consensus (if applicable) |
| Security | 0.30 | No injection, XSS, auth bypass, or exposed secrets |
| Error Handling | 0.20 | Graceful failures, no silent errors, safe error messages |
| Breaking Changes | 0.20 | API compatibility maintained, migrations provided |

### Security Checklist

- [ ] No hardcoded secrets, API keys, or credentials
- [ ] Input validation present for user-supplied data
- [ ] No SQL injection vulnerabilities (parameterized queries used)
- [ ] No command injection (user input not passed to shell)
- [ ] No XSS vulnerabilities (output properly escaped)
- [ ] Authentication/authorization checks in place
- [ ] Sensitive data not logged or exposed in errors

### Error Handling Checklist

- [ ] Exceptions properly caught and handled
- [ ] No silent failures that hide problems
- [ ] Error messages don't leak internal details
- [ ] Resources properly cleaned up on failure

### Breaking Changes Checklist

- [ ] Public API signatures unchanged (or properly versioned)
- [ ] Database migrations provided for schema changes
- [ ] Deprecation warnings added for removed features
- [ ] Backwards compatibility maintained where expected

## Tier 2 Criteria (Quality)

These are quality criteria. Issues should be noted but are not blocking.

| Criterion | Weight | Description |
|-----------|--------|-------------|
| Bug Detection | 0.25 | No logic errors, null refs, off-by-one, race conditions |
| Performance | 0.25 | No O(n^2), memory leaks, N+1 queries, blocking I/O |
| Maintainability | 0.25 | Clear naming, reasonable complexity, good structure |
| Test Coverage | 0.25 | Changes have corresponding tests |

## Output Format

```json
{
  "tier1": {
    "passed": true,
    "score": 0.95,
    "checks": {
      "cross_verification": {"passed": true, "notes": "Aligned with agent consensus"},
      "security": {"passed": true, "notes": "No vulnerabilities detected"},
      "error_handling": {"passed": true, "notes": "Proper exception handling"},
      "breaking_changes": {"passed": true, "notes": "No breaking changes"}
    },
    "failures": [],
    "blockers": []
  },
  "tier2": {
    "score": 0.80,
    "checks": {
      "bug_detection": {"score": 0.90, "concerns": []},
      "performance": {"score": 0.85, "concerns": ["Consider caching for repeated lookups"]},
      "maintainability": {"score": 0.75, "concerns": ["Function X is complex, consider splitting"]},
      "test_coverage": {"score": 0.70, "concerns": ["Missing tests for edge case Y"]}
    },
    "concerns": ["List of all quality concerns"]
  },
  "overall_verdict": "APPROVED",
  "summary": "Code passes all critical checks. Minor quality improvements suggested.",
  "recommendations": [
    "Consider adding test for edge case Y",
    "Function X could be simplified"
  ]
}
```

## Verdict Guide

- **APPROVED**: All Tier 1 checks pass, Tier 2 score >= 0.60
- **NEEDS_REVIEW**: All Tier 1 checks pass, Tier 2 score < 0.60
- **BLOCKED**: Any Tier 1 check fails
