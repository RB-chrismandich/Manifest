---
name: shell-refactor
description: Perform security and quality analysis for Bash/Shell scripts and produce a prioritized refactor plan with risk and effort guidance.
---

# Shell Script Refactor Analysis

Analyze Bash/Shell scripts against security best practices, ShellCheck standards, and
enterprise shell scripting guidelines. Generate a comprehensive refactoring report
with prioritized recommendations.

## Parallel Agent Integration

This command ALWAYS uses parallel agents (security-critical).
Executes: `[[skill:parallel-agent]] --json --full-output --validate`

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

### Step 0: Consult Knowledge Base

Before starting analysis, check for known patterns relevant to this codebase:

```bash
[[skill:learning-capture]] query --language bash --format llm
```

If the knowledge base contains relevant antipatterns or insights for Bash/Shell:

- Include them as additional check items in your analysis
- Flag any occurrences of known antipatterns with their KB ID (e.g., ANTI-001)
- Note if a known antipattern has been resolved

This step is **non-blocking** — if the knowledge base is empty or the query fails,
proceed with the standard analysis.

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

Produce a report with: Executive Summary (score by category), Scripts
Analyzed table, Priority Matrix (Immediate/Quick Wins/Planned/Strategic),
Detailed Findings by script (location, risk, effort, current code, fix,
ShellCheck code), ShellCheck Summary by severity, and Recommendations
(Immediate/Short Term/Long Term).

Full populated template: [references/output-format.md](references/output-format.md)

## Analysis Principles

- **Be specific**: Every finding must have exact file:line location
- **Be actionable**: Every finding must have a concrete fix
- **Prioritize security**: Command injection and unsafe operations come first
- **Run ShellCheck**: Always include actual ShellCheck output
- **Show examples**: Include before/after code snippets

---

## Related Tools

- **ShellCheck**: Static analysis (already installed)
- **shfmt**: Shell script formatter
- **bashate**: OpenStack style checker
- **bats**: Bash Automated Testing System
- **shellharden**: Automatic script hardening

---

## Learning Capture (Optional)

After completing the analysis, capture the most significant findings:

1. For each critical or high-severity finding:
   - Run:

     ```bash
     [[skill:learning-capture]] add \
       --category antipattern --language bash \
       --title "<finding title>" \
       --description "<finding description and recommended fix>" \
       --source shell-refactor --confidence high
     ```

2. For any new tool recommendations discovered:
   - Run:

     ```bash
     [[skill:learning-capture]] add \
       --category tool_discovery --language bash \
       --title "<tool recommendation>" \
       --description "<why this tool is better>" \
       --source shell-refactor --confidence medium
     ```

3. This step is **non-blocking** -- failures in learning capture should not affect the analysis output.

## Sub-agent dispatch

When ≥3 independent scripts exist, dispatch one sub-agent per script to analyze it, then merge findings; below
that, analyze inline. Use native Task sub-agents on Claude, or `[[skill:parallel-agent]]` /
inline on other assistants. Dispatched sub-agents execute their task directly and do not re-dispatch.

Dispatch on **Sonnet** (`subagent_model: sonnet`) — pass the model
explicitly; inheriting the session's model bills premium rates for fan-out work.
