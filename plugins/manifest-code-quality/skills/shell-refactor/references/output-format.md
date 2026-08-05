
# Shell Refactor: Output Format & Testing Reference

Extracted from the main skill to keep SKILL.md under the line cap.

## Output Format

### Shell Script Refactor Analysis Report

````markdown
# Shell Script Refactor Analysis Report

**Date:** YYYY-MM-DD
**Scripts Analyzed:** N
**Overall Score:** XX/100

---

## Executive Summary

| Category | Score | Issues | Critical |
|----------|-------|--------|----------|
| Security | XX/30 | N | Y/N |
| Error Handling | XX/20 | N | Y/N |
| Code Quality | XX/20 | N | Y/N |
| Documentation | XX/15 | N | Y/N |
| Best Practices | XX/15 | N | Y/N |

**Key Findings:**
- [1-3 sentence summary of most critical issues]

---

## Scripts Analyzed

| Script | Lines | Functions | Issues | Score |
|--------|-------|-----------|--------|-------|
| bootstrap.sh | 1000 | 15 | 12 | 75/100 |
| git_ops.sh | 1038 | 20 | 8 | 85/100 |

---

## Priority Matrix

### Immediate (Critical Risk - Any Effort)

| ID | Issue | Location | Effort | Risk |
|----|-------|----------|--------|------|
| SEC-001 | Unquoted variable expansion | `bootstrap.sh:123` | Minimal | Critical |

### Quick Wins (Low Risk + Minimal Effort)

| ID | Issue | Location | Effort | Risk |
|----|-------|----------|--------|------|
| QA-001 | Add `set -euo pipefail` | `bootstrap.sh:1` | Minimal | Low |

### Planned (Medium Risk/Effort)

[Table of medium priority items]

### Strategic (High Effort)

[Table of long-term items]

---

## Detailed Findings by Script

### bootstrap.sh

#### SEC-001: Unquoted Variable Expansion [CRITICAL]
- **Location:** Line 123
- **Risk:** Critical
- **Effort:** Minimal
- **Current Code:**
  ```bash
  cd $TARGET_DIR
  ```

- **Issue:** Unquoted variable can cause word splitting and command injection
- **Fix:**

  ```bash
  cd "$TARGET_DIR" || { echo "Failed to cd to $TARGET_DIR"; exit 1; }
  ```

- **ShellCheck:** SC2164, SC2086

#### QA-001: Declare and Assign Separately [MEDIUM]

- **Location:** Line 265
- **Risk:** Low
- **Effort:** Minimal
- **Current Code:**

  ```bash
  local var=$(command)
  ```

- **Issue:** Masks return value of command
- **Fix:**

  ```bash
  local var
  var=$(command) || { echo "Command failed"; return 1; }
  ```

- **ShellCheck:** SC2155

---

## ShellCheck Summary

### Critical Issues (Must Fix)

| Code | Count | Description |
|------|-------|-------------|
| SC2086 | 5 | Unquoted variable expansion |
| SC2046 | 2 | Word splitting in command substitution |

### High Priority

| Code | Count | Description |
|------|-------|-------------|
| SC2164 | 3 | cd without error check |
| SC2155 | 8 | Declare and assign separately |

### Medium Priority

| Code | Count | Description |
|------|-------|-------------|
| SC2034 | 1 | Variable appears unused |
| SC2129 | 5 | Consolidate redirects |

---

## Recommendations

### Immediate (This Sprint)

- [ ] Fix SEC-001: Quote all variable expansions
- [ ] Add error checking for all `cd` commands
- [ ] Add `set -euo pipefail` to all scripts

### Short Term (Next 2 Sprints)

- [ ] Separate variable declaration and assignment (SC2155)
- [ ] Add function documentation headers
- [ ] Create unit tests with BATS

### Long Term (Roadmap)

- [ ] Achieve zero ShellCheck warnings
- [ ] Add structured logging
- [ ] Implement debug mode

````

## Testing Recommendations

### Unit Testing with BATS

```bash
# Install BATS
npm install -g bats

# Create test file: tests/bootstrap.bats
@test "detect_platform identifies macOS" {
  run detect_platform
  [ "$status" -eq 0 ]
  [[ "$PLATFORM" = "macos" ]]
}
```

### Integration Testing

```bash
# Test in Docker containers
docker run --rm -v "$PWD:/work" -w /work ubuntu:22.04 ./bootstrap.sh --skip-auth
docker run --rm -v "$PWD:/work" -w /work fedora:39 ./bootstrap.sh --skip-auth
```
