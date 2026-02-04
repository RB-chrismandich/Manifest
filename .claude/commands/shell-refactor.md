---
description: Analyze Bash/Shell scripts for security, quality, and best practices
allowed-tools: Read, Glob, Grep, Bash
argument-hint: [script-path]
---

# Shell Script Refactor Analysis

Analyze Bash/Shell scripts against security best practices, ShellCheck standards, and enterprise shell scripting guidelines. Generate a comprehensive refactoring report with prioritized recommendations.

## Parallel Agent Integration

This command ALWAYS uses parallel agents (security-critical).
Executes: `~/.claude/scripts/parallel_agent.sh --json --full-output --validate`

Consensus scoring:
- ≥80%: Auto-proceed with unified recommendation
- 50-79%: Highlight disagreements to user
- <50%: Escalate for human review

## Task

You are a Senior DevOps/Infrastructure Engineer analyzing production shell scripts. Your goals are to:

1. Run ShellCheck analysis for security and quality issues
2. Identify security vulnerabilities (command injection, unquoted variables, dangerous commands)
3. Find code quality and maintainability issues
4. Rate each finding by **effort** (Minimal/Medium/High) and **risk** (Low/Medium/High/Critical)
5. Generate an actionable improvement roadmap with priority matrix
6. Check for proper error handling and logging

---

## Instructions

### Step 1: Identify Shell Scripts

Find all shell scripts in the repository:
```bash
find . -name "*.sh" -type f
find . -type f -exec grep -l "^#!/bin/bash\|^#!/bin/sh" {} \;
```

### Step 2: Run ShellCheck Analysis

For each script, run ShellCheck:
```bash
shellcheck --severity=info script.sh
```

**Key ShellCheck Codes to Prioritize:**

| Code | Severity | Issue |
|------|----------|-------|
| SC2086 | Critical | Unquoted variable expansion (injection risk) |
| SC2046 | Critical | Quote word splitting in `$(cmd)` |
| SC2162 | High | Read without -r (backslash handling) |
| SC2164 | High | `cd` without checking if it succeeded |
| SC2155 | Medium | Declare and assign separately |
| SC2034 | Low | Variable appears unused |

### Step 3: Security Pattern Analysis

Scan for dangerous patterns:

#### Command Injection Risks

```bash
# Bad: Unquoted variables in commands
grep -rn 'eval' *.sh
grep -rn '\$(' *.sh | grep -v '"\$('  # Unquoted command substitution
grep -rn '\${[^}]*}' *.sh | grep -v '"\${'  # Unquoted variable expansion
```

#### Dangerous Commands

```bash
grep -rn 'rm -rf' *.sh
grep -rn 'curl.*|.*bash' *.sh
grep -rn 'wget.*|.*sh' *.sh
grep -rn '^[[:space:]]*eval ' *.sh
```

#### Insufficient Error Handling

```bash
grep -rn '^[[:space:]]*cd ' *.sh | grep -v '&&\|||'  # cd without error check
grep -n 'set -e' *.sh  # Check if scripts fail on error
```

### Step 4: Code Quality Analysis

#### Long Functions

```bash
# Functions longer than 50 lines
awk '/^[a-zA-Z_][a-zA-Z0-9_]*\(\)/ {start=NR; fname=$1} /^}/ && start {len=NR-start; if(len>50) print FILENAME":"start" "fname" ("len" lines)"}' script.sh
```

#### Global Variables

```bash
# Find all global variables (SCREAMING_SNAKE_CASE)
grep -n '^[A-Z_][A-Z0-9_]*=' script.sh
```

#### Magic Values

```bash
# Hardcoded paths, IPs, URLs
grep -nE '/(usr|etc|var|tmp|home)/[^"]*[^[:space:]]' script.sh
grep -nE '[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}' script.sh
grep -nE 'https?://[^"[:space:]]+' script.sh
```

### Step 5: Documentation Analysis

Check for:
- Shebang line (#!/bin/bash)
- Script-level comments explaining purpose
- Function documentation
- Usage/help function
- Example invocations

### Step 6: Best Practices

#### Recommended Patterns

```bash
# Should use:
set -euo pipefail  # Fail on errors, undefined vars, pipe failures
readonly VAR="value"  # Immutable variables
local var="value"  # Function-scoped variables
[[ ... ]]  # Modern test syntax instead of [ ... ]
"${var}"  # Always quote variables
```

---

## Effort Classification

| Level | Time | Scope | Examples |
|-------|------|-------|----------|
| **Minimal** | <30 min | Single-line fixes | Quote variable, add `readonly`, fix shebang |
| **Medium** | 1-4 hours | Function refactor | Add error handling, break up long function |
| **High** | 1-2 days | Architectural | Rewrite with proper structure, add tests |

## Risk Classification

| Level | Impact | Testing Required | Examples |
|-------|--------|------------------|----------|
| **Low** | No behavior change | None | Add comments, rename variables |
| **Medium** | Internal changes | Manual testing | Add error checks, refactor helpers |
| **High** | Logic changes | Integration tests | Fix command injection, change flow |
| **Critical** | Security/Breaking | Full regression | Fix injection, remove dangerous commands |

---

## Output Format

### Shell Script Refactor Analysis Report

```markdown
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
| parallel_agent.sh | 1038 | 20 | 8 | 85/100 |

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
```

---

## Analysis Principles

- **Be specific**: Every finding must have exact file:line location
- **Be actionable**: Every finding must have a concrete fix
- **Prioritize security**: Command injection and unsafe operations come first
- **Run ShellCheck**: Always include actual ShellCheck output
- **Show examples**: Include before/after code snippets

---

## Common Patterns to Check

### Security

```bash
# Bad: Unquoted expansion
rm -rf $dir/*

# Good: Quoted
rm -rf "${dir:?}/"*  # :? fails if unset
```

### Error Handling

```bash
# Bad: No error check
cd /some/path
do_something

# Good: Check or fail
cd /some/path || exit 1
do_something
```

### Variable Quoting

```bash
# Bad: Unquoted
if [ $var = "value" ]; then

# Good: Quoted
if [[ "$var" = "value" ]]; then
```

### Command Substitution

```bash
# Bad: Unquoted
files=$(ls *.txt)

# Good: Array
files=(*.txt)
```

---

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

---

## Related Tools

- **ShellCheck**: Static analysis (already installed)
- **shfmt**: Shell script formatter
- **bashate**: OpenStack style checker
- **bats**: Bash Automated Testing System
- **shellharden**: Automatic script hardening
