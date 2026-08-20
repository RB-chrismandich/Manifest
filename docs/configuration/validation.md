# Validation Criteria

> Tier 1 and Tier 2 rules, weights, and verdicts.

## Validation Criteria

**File**: `~/.claude/config/validation_criteria.yml`

Defines two-tier validation system for security and quality checks.

### Tier 1: Critical (Blocking)

All Tier 1 checks must pass for approval.

```yaml
tier1:
  cross_verification:
    weight: 0.30
    description: "Multiple agents agree on key findings"
    threshold: 0.80
    enabled: true

  security:
    weight: 0.30
    description: "No security vulnerabilities introduced"
    checks:
      - id: no_hardcoded_secrets
        description: "No hardcoded secrets or credentials"
        severity: critical
      - id: input_validation
        description: "User input is validated and sanitized"
        severity: critical
      - id: no_sql_injection
        description: "Parameterized queries used for database access"
        severity: critical

  error_handling:
    weight: 0.20
    description: "Errors handled gracefully without information leakage"
    checks:
      - id: exceptions_caught
        description: "Exceptions properly caught and handled"
        severity: high

  breaking_changes:
    weight: 0.20
    description: "API and data compatibility maintained"
    checks:
      - id: api_compatibility
        description: "Public API signatures unchanged or versioned"
        severity: high
```

### Tier 2: Quality (Advisory)

Weighted score must be ≥ 0.60 for approval.

```yaml
tier2:
  bug_detection:
    weight: 0.25
    description: "No obvious bugs or logic errors"
    patterns:
      - id: null_reference
        description: "Potential null/undefined reference"
        regex: "\\.(\\w+)\\s*\\("

  performance:
    weight: 0.25
    description: "No performance anti-patterns"
    antipatterns:
      - id: quadratic_complexity
        description: "O(n^2) or worse complexity"
        indicators: ["nested loop", "forEach inside forEach"]

  maintainability:
    weight: 0.25
    description: "Code is readable and maintainable"
    thresholds:
      max_cyclomatic_complexity: 15
      max_function_length: 50
      max_file_length: 500

  test_coverage:
    weight: 0.25
    description: "Changes have corresponding tests"
    thresholds:
      minimum_coverage: 0.80
```

### Scoring

```yaml
scoring:
  tier1_pass_threshold: 1.0  # All tier1 checks must pass
  tier2_acceptable_threshold: 0.60

  verdicts:
    approved:
      tier1_passed: true
      tier2_min_score: 0.60
    needs_review:
      tier1_passed: true
      tier2_min_score: 0.0
    blocked:
      tier1_passed: false
```

**Verdict Examples:**

- Tier 1: 100% pass, Tier 2: 0.85 → **APPROVED**
- Tier 1: 100% pass, Tier 2: 0.45 → **NEEDS_REVIEW** (quality concerns)
- Tier 1: Security fail → **BLOCKED** (critical failure)

### Command-Specific Overrides

```yaml
command_overrides:
  python-refactor:
    tier1_required: true
    tier1_checks:
      - security
      - error_handling
      - breaking_changes
      - cross_verification
    tier2_required: true
    tier2_threshold: 0.80  # Higher threshold for refactoring
    consensus_threshold: 0.80

  docs-generate-diagrams:
    tier1_required: false
    tier2_required: false
    # No validation for diagram generation
```

### Customizing Validation per Command

Validation behavior is customized through the `command_overrides` section of
`validation_criteria.yml` itself — this is the mechanism the validation engine
(`agents/validation.py`) actually loads.

**File**: `~/.claude/config/validation_criteria.yml`

#### Structure

```yaml
command_overrides:
  python-refactor:
    tier1_required: true
    tier1_checks:
      - security
      - error_handling
      - breaking_changes
      - cross_verification
    tier2_required: true
    tier2_threshold: 0.80
    consensus_threshold: 0.80
    consensus_action:
      high: auto_proceed          # >=80%: Use unified recommendation
      medium: show_disagreements  # 50-79%: Highlight to user
      low: block_and_escalate     # <50%: Human review required

  docs-improve-readme:
    tier1_required: false
    tier2_required: true
    tier2_checks:
      - maintainability
    parallel_agents: false
```

When `parallel_agent.py --validate` runs with a `--command` context, the
matching override replaces the default tier requirements for that run; the
result reports `command_overrides_applied: true`.

#### How Overrides Work

1. **Base criteria loaded**: `~/.claude/config/validation_criteria.yml`
   (tier1/tier2 definitions and verdict thresholds)
2. **Command override selected**: the entry under `command_overrides:`
   matching the invoked command, if any
3. **Verdict computed**: APPROVED / NEEDS_REVIEW / BLOCKED per the
   (possibly overridden) tier requirements

> **Note**: A standalone `validation_overrides.yml` file with
> pattern-based project checks (as shipped in
> `docs/templates/validation-overrides/`) is a design sketch — no code
> loads that file today. Use `command_overrides` above for working
> customization; the templates document the checks worth adopting if the
> loader is implemented (tracked in issue #325).

---

---

[← Configuration](README.md)
