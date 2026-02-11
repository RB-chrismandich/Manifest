# Pre-flight Analysis Task

Determine whether proposed code changes require parallel multi-agent review.
Evaluate the change scope, sensitivity, and risk to produce a structured decision.

## Changes to Analyze

{FILES_OR_DIFF}

## Chain-of-Thought Reasoning

Think step by step through each trigger criterion below. For each criterion,
explicitly state whether it applies, why or why not, and cite specific evidence
from the files or diff.

### Step 1: Security Sensitivity

Check for any of these patterns in the changed code:

- **Authentication/authorization**: login, session, JWT, OAuth, RBAC, middleware guards
- **Cryptographic operations**: hashing, encryption, key generation, signing
- **Secrets handling**: API keys, tokens, credentials, environment variables
- **Input validation/sanitization**: user input parsing, form validation, query parameters
- **Network security**: CORS, CSP, TLS configuration, firewall rules

Evidence format: Quote the specific line or pattern that triggered this criterion.

### Step 2: Architectural Impact

Check for structural changes:

- **New services or modules**: new entry points, new packages, new API routes
- **API changes**: modified endpoints, changed request/response schemas, new public interfaces
- **Schema modifications**: database migrations, model changes, state shape changes
- **Integration patterns**: new external service calls, webhook handlers, message queue consumers
- **Configuration changes**: environment config, infrastructure-as-code, CI/CD pipelines

### Step 3: Change Scope

Assess the magnitude of changes:

- **Line count**: >200 lines modified triggers review
- **File count**: >5 files changed triggers review
- **Cross-cutting changes**: modifications spanning multiple packages or layers

### Step 4: Critical Logic

Check for business-critical operations:

- **Payment processing**: billing, subscriptions, transactions, financial calculations
- **User data handling**: PII, GDPR-relevant operations, data export/deletion
- **Compliance-related**: audit logging, access control, data retention policies
- **State mutations**: operations that are hard to reverse (deletes, migrations, deployments)

## Confidence Calibration

Rate your confidence in the pre-flight decision:

- **0.90-1.00**: Clear trigger or clear non-trigger; no ambiguity
- **0.70-0.89**: Likely trigger/non-trigger but some edge cases
- **0.50-0.69**: Uncertain; could go either way depending on context
- **Below 0.50**: Insufficient information to decide; default to triggering review

When confidence is below 0.70, default to triggering parallel review (false positives
are cheaper than missed security issues).

## Output Format

```json
{
  "needs_parallel_review": true,
  "reason": "Short explanation of why review is or isn't needed",
  "triggered_criteria": [
    {
      "criterion": "security_sensitivity",
      "evidence": "Line 42: jwt.verify(token, secret) — authentication logic",
      "severity": "high"
    }
  ],
  "non_triggered_criteria": [
    {
      "criterion": "critical_logic",
      "reason": "No payment or PII handling detected"
    }
  ],
  "confidence": 0.92,
  "recommended_model_tier": "security|review|analyze|quick",
  "scope_summary": {
    "files_changed": 3,
    "lines_added": 120,
    "lines_removed": 45,
    "languages": ["python", "yaml"]
  }
}
```

## Decision Matrix

| Criteria Triggered | Confidence | Decision |
|--------------------|------------|----------|
| Any security criterion | Any | REVIEW (use security model tier) |
| Architectural + >200 lines | >= 0.70 | REVIEW (use review model tier) |
| Critical logic only | >= 0.70 | REVIEW (use analyze model tier) |
| Scope only (>200 lines) | >= 0.70 | REVIEW (use review model tier) |
| None triggered | >= 0.80 | SKIP review |
| None triggered | < 0.80 | REVIEW (insufficient confidence to skip) |
