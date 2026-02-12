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

## Language-Specific Validation

Apply these additional checks based on the detected language(s) in the changeset.

### Python

- [ ] Type hints present on function signatures (pyright/mypy compatible)
- [ ] No bare `except:` — use specific exception types
- [ ] No `eval()`, `exec()`, or `pickle.loads()` on untrusted input
- [ ] `yaml.safe_load()` used instead of `yaml.load()`
- [ ] f-strings not used in SQL queries (parameterized queries required)
- [ ] Async functions use `await` properly (no blocking calls in async context)

### Go

- [ ] Errors checked — no `_ :=` ignoring error returns
- [ ] No bare returns from error checks — always return the error or wrap it
- [ ] No goroutine leaks — goroutines have cancellation via context or done channels
- [ ] Goroutine lifecycle managed — use `sync.WaitGroup`, `errgroup`, or explicit shutdown signals
- [ ] Race conditions — shared state protected by mutex or channels
- [ ] `defer` used for resource cleanup (file handles, locks, connections)
- [ ] Input validation on exported functions
- [ ] `context.Context` propagated through call chains (first parameter by convention)
- [ ] `context.Context` not stored in structs — pass explicitly to functions
- [ ] `go vet` compliance — no composite literal issues, printf format mismatches, or unreachable code
- [ ] `go vet` shadow check — no unintended variable shadowing in nested scopes

### Node.js / TypeScript

- [ ] TypeScript strict mode enabled (`strict: true` in tsconfig)
- [ ] No `any` type — use specific types or `unknown` with type guards
- [ ] Async/await used instead of raw callbacks (no callback hell)
- [ ] Async/await error handling — all `await` calls wrapped in try/catch or `.catch()`
- [ ] No unhandled promise rejections — reject handlers or global handlers configured
- [ ] No prototype pollution vectors (`Object.assign` on user input, `__proto__` access)
- [ ] No `Object.assign({}, userInput)` or spread of untrusted objects without sanitization
- [ ] Dependencies audited — no known vulnerabilities (`npm audit`)
- [ ] No `require()` of user-controlled paths (path traversal risk)
- [ ] Event listeners cleaned up to prevent memory leaks
- [ ] Stream backpressure handled — no unbounded memory growth on writable streams

### Terraform

- [ ] No hardcoded secrets in `.tf` files or `terraform.tfvars`
- [ ] No hardcoded provider credentials — use environment variables, IAM roles, or vault
- [ ] IAM policies follow least privilege (no `*` actions or resources)
- [ ] Security groups do not allow `0.0.0.0/0` ingress on sensitive ports
- [ ] `sensitive = true` set on outputs containing secrets
- [ ] Remote state backend configured with encryption and locking
- [ ] State file not stored in version control — `.gitignore` includes `*.tfstate`
- [ ] Provider and module versions pinned with constraints
- [ ] Module sources pinned to specific versions or commit SHAs (no floating `ref=main`)
- [ ] Variable validation blocks present for variables with constrained values
- [ ] `validation { condition = ... }` used on input variables where applicable

### Shell / Bash

- [ ] Variables quoted to prevent word splitting: `"$var"` not `$var`
- [ ] No `eval` on user-supplied input
- [ ] `set -euo pipefail` at script top (or equivalent error handling)
- [ ] Temporary files created with `mktemp` (not predictable paths)
- [ ] No command injection via unvalidated input to `$()` or backticks

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
