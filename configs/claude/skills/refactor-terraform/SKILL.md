---
name: refactor-terraform
description: |
  Perform security, modularity, and quality analysis for Terraform/OpenTofu IaC codebases
  and return a prioritized, actionable refactoring roadmap.
---

# Terraform IaC Refactor Analysis

Analyze Terraform/OpenTofu infrastructure-as-code against security best practices,
module composition patterns, and state management standards. Generate a comprehensive
refactoring report with prioritized recommendations.

## Parallel Agent Integration

This command ALWAYS uses parallel agents (security-critical).
Executes: `~/.claude/scripts/parallel_agent.sh --json --full-output --validate --analyze`

## Task

You are a Senior Infrastructure/Platform Engineer analyzing production Terraform code.
Your goals:

1. Assess IaC against security standards (tfsec, checkov, Sentinel patterns)
2. Identify misconfigurations, drift risks, and blast radius issues
3. Find modularity and composition improvements
4. Rate each finding by **effort** and **risk**
5. Generate an actionable improvement roadmap

---

## Instructions

### Step 0: Consult Knowledge Base

Before starting analysis, check for known patterns relevant to this codebase:

```bash
~/.claude/scripts/learning_capture.sh query --language terraform --format llm
```

If the knowledge base contains relevant antipatterns or insights for Terraform/OpenTofu:

- Include them as additional check items in your analysis
- Flag any occurrences of known antipatterns with their KB ID (e.g., ANTI-001)
- Note if a known antipattern has been resolved

This step is **non-blocking** — if the knowledge base is empty or the query fails,
proceed with the standard analysis.

### Step 1: Read Project Standards

- Read README.md, CLAUDE.md for project context
- Check for existing tooling: .terraform-version, .tflint.hcl, .checkov.yaml
- Inspect provider versions and required_providers blocks
- Check backend configuration (state storage, locking)

### Step 2: Architecture Analysis

- Map module structure (root vs child modules)
- Check for module composition (DRY principles)
- Identify monolithic configurations (>500 lines per file)
- Verify proper use of workspaces vs separate state files
- Check for hardcoded values that should be variables

### Step 3: Security Analysis (CRITICAL)

**Access Control**:

- Overly permissive IAM policies (`*` actions or resources)
- Missing least-privilege boundaries
- Public access to storage buckets, databases, or APIs
- Missing encryption at rest and in transit

**Network Security**:

- Security groups with `0.0.0.0/0` ingress
- Missing VPC flow logs
- Public subnets for private resources
- Missing WAF or DDoS protection

**Secrets Management**:

- Hardcoded secrets in `.tf` files or `terraform.tfvars`
- Missing integration with secret managers (Vault, AWS SSM, etc.)
- Secrets in state file (sensitive = true missing)

**State Security**:

- Local state files (should be remote with locking)
- State file without encryption
- Missing state file access controls

### Step 4: Module Quality

- Input validation with `validation` blocks
- Proper use of `locals` for computed values
- Output descriptions and documentation
- Version constraints on modules and providers
- Consistent file structure: main.tf, variables.tf, outputs.tf, versions.tf

### Step 5: Drift and Lifecycle

- Resources with `ignore_changes` lifecycle rules (intentional or hiding drift?)
- Missing `prevent_destroy` on critical resources
- Proper tagging strategy (cost allocation, ownership, environment)
- Resource naming conventions

### Step 6: Testing

- Terratest or tftest integration tests
- `terraform validate` and `terraform plan` in CI
- Policy-as-code (OPA/Sentinel/Checkov)

---

## Effort Classification

| Level | Time | Scope | Examples |
|-------|------|-------|----------|
| **Minimal** | <1 hour | Single resource | Add tags, fix variable description, add sensitive flag |
| **Medium** | 2-8 hours | Module refactor | Extract module, add validation, fix IAM policy |
| **High** | 1-3 days | Architectural | State migration, module restructure, add testing |

## Risk Classification

| Level | Impact | Testing Required | Examples |
|-------|--------|------------------|----------|
| **Low** | No infra change | `terraform plan` | Add descriptions, tags, locals |
| **Medium** | Non-destructive change | Plan review | Add variables, outputs, lifecycle rules |
| **High** | Resource modification | Staging first | Change IAM, security groups, encryption |
| **Critical** | Destructive/Security | Full DR test | State migration, access control, secrets |

---

## Output Format

```markdown
# Terraform Refactor Analysis Report

**Date:** YYYY-MM-DD
**Terraform Version:** X.X
**Providers:** N
**Modules:** N
**Overall Score:** XX/100

## Executive Summary

| Category | Score | Issues | Critical |
|----------|-------|--------|----------|
| Security | XX/30 | N | Y/N |
| Module Quality | XX/20 | N | Y/N |
| State Management | XX/15 | N | Y/N |
| Code Quality | XX/15 | N | Y/N |
| Testing | XX/10 | N | Y/N |
| Documentation | XX/10 | N | Y/N |

## Priority Matrix
[Immediate / Quick Wins / Planned / Strategic]

## Detailed Findings
[Per finding with blast radius assessment]

## Recommendations
[Immediate / Short Term / Long Term]
```

---

## Configuration Templates

### .tflint.hcl

```hcl
config {
  call_module_type = "all"
}

plugin "terraform" {
  enabled = true
  preset  = "recommended"
}

plugin "aws" {
  enabled = true
  version = "0.35.0"
  source  = "github.com/terraform-linters/tflint-ruleset-aws"
}
```

---

## Analysis Principles

- **Assess blast radius**: Every finding should note what breaks if changed
- **Be specific**: Include resource addresses (module.x.resource.y)
- **Security first**: IAM and network misconfigurations are production incidents
- **State is sacred**: State migrations require extreme care
- **Plan before apply**: Every recommendation should be verifiable with `terraform plan`

---

## Learning Capture (Optional)

After completing the analysis, capture the most significant findings:

1. For each critical or high-severity finding:
   - Run:

     ```bash
     ~/.claude/scripts/learning_capture.sh add \
       --category antipattern --language terraform \
       --title "<finding title>" \
       --description "<finding description and recommended fix>" \
       --source refactor-terraform --confidence high
     ```

2. For any new tool recommendations discovered:
   - Run:

     ```bash
     ~/.claude/scripts/learning_capture.sh add \
       --category tool_discovery --language terraform \
       --title "<tool recommendation>" \
       --description "<why this tool is better>" \
       --source refactor-terraform --confidence medium
     ```

3. This step is **non-blocking** -- failures in learning capture should not affect the analysis output.
