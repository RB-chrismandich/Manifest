# Pre-flight Analysis Task

Determine whether proposed code changes require parallel multi-agent review.
Evaluate the change scope, sensitivity, and risk to produce a structured decision.

## Changes to Analyze

{FILES_OR_DIFF}

## Chain-of-Thought Reasoning

Think step by step through each trigger criterion below. For each criterion:

1. **Examine**: Scan the changed code for relevant patterns
2. **Evaluate**: Determine whether the criterion applies and at what severity
3. **Evidence**: Quote the specific line, function, or pattern that triggered (or cleared) the criterion
4. **Conclude**: State your determination with a brief rationale

Do not skip steps. If you are uncertain about a criterion, say so explicitly
rather than defaulting to "not triggered" -- uncertainty should bias toward
triggering review.

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

### Step 5: Language-Specific Triggers

Apply additional trigger criteria based on the languages detected in the change.
Only evaluate sections relevant to the languages present.

#### Go

- **Unsafe operations**: `unsafe.Pointer`, `reflect.SliceHeader`, `//go:linkname`, `//go:nosplit`
- **CGo boundary**: `import "C"`, `C.` calls, manual memory management across FFI boundary
- **Concurrency hazards**: goroutine spawning (`go func`), channel operations without
  context/cancellation, missing `sync.Mutex` around shared state, `sync/atomic` usage
- **Error swallowing**: unchecked `err` returns, `_ = someFunc()` discarding errors

#### Node.js / JavaScript / TypeScript

- **Code injection**: `eval()`, `new Function()`, `vm.runInContext()`, `child_process.exec()`
  with string interpolation
- **Prototype pollution**: direct assignment to `__proto__`, `Object.assign` with untrusted
  input, deep merge of user-controlled objects
- **Dependency surface**: >5 new dependencies added, dependencies without lockfile pinning,
  install scripts (`preinstall`, `postinstall`) in new packages
- **Deserialization**: `JSON.parse` of untrusted input without schema validation,
  `require()` with dynamic paths

#### Terraform / OpenTofu / IaC

- **State manipulation**: `terraform state mv`, `terraform import`, `terraform state rm`,
  manual `.tfstate` edits
- **Provider credentials**: hardcoded `access_key`, `secret_key`, `token` in provider blocks;
  credentials outside of variables/secrets managers
- **Module sources**: modules sourced from `git::`, `http://`, or unversioned registries;
  missing `version` constraint on registry modules
- **Destructive operations**: `force_destroy = true`, `prevent_destroy = false`,
  `create_before_destroy = false` on stateful resources
- **IAM / permissions**: `iam:*`, overly broad `Action` or `Resource` wildcards in policies

#### Python

- **Code injection**: `exec()`, `eval()`, `compile()` with user input, `subprocess.shell=True`
- **Deserialization**: `pickle.load()`, `yaml.load()` without `Loader=SafeLoader`,
  `marshal.loads()` from untrusted sources
- **SQL injection**: string formatting in SQL queries (`f"SELECT ... {user_input}"`)

#### Rust

- **Unsafe blocks**: `unsafe { }`, `#[no_mangle]`, FFI declarations, raw pointer dereferencing
- **Concurrency**: `Arc<Mutex<>>` without deadlock analysis, `std::thread::spawn` with
  shared mutable state

> If the language is not listed above, apply general security heuristics from Steps 1-4.
> Language-specific triggers carry the same weight as security triggers in the Decision Matrix.

## Confidence Calibration

Rate your confidence in the pre-flight decision on a 0.0-1.0 scale:

- **0.90-1.00**: Clear trigger or clear non-trigger; no ambiguity
- **0.70-0.89**: Likely trigger/non-trigger but some edge cases
- **0.50-0.69**: Uncertain; could go either way depending on context
- **Below 0.50**: Insufficient information to decide; default to triggering review

When confidence is below 0.70, default to triggering parallel review (false positives
are cheaper than missed security issues).

### Calibration Notes

Include a brief `calibration_notes` field in your output explaining what factors
raised or lowered your confidence. Common factors:

- **Raises confidence**: Small diff, single-purpose change, well-tested area, no external inputs
- **Lowers confidence**: Unfamiliar codebase patterns, indirect data flow, generated code,
  missing test context, changes touching multiple subsystems
- **Automatic low confidence**: If the diff is truncated or incomplete, set confidence <= 0.60
  and note that full context was not available

## Output Format

Return ONLY the following JSON object. Do not include commentary outside the JSON block.

```json
{
  "needs_parallel_review": true,
  "reason": "Short explanation of why review is or isn't needed",
  "triggered_criteria": [
    {
      "criterion": "security_sensitivity",
      "step": 1,
      "evidence": "Line 42: jwt.verify(token, secret) — authentication logic",
      "severity": "high"
    },
    {
      "criterion": "language_specific",
      "step": 5,
      "language": "go",
      "evidence": "Line 78: go func() without context.Context propagation",
      "severity": "medium"
    }
  ],
  "non_triggered_criteria": [
    {
      "criterion": "critical_logic",
      "step": 4,
      "reason": "No payment or PII handling detected"
    }
  ],
  "confidence": 0.92,
  "calibration_notes": "High confidence: small, focused auth change with clear trigger pattern. No ambiguous data flows.",
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
| Any security criterion (Step 1) | Any | REVIEW (use security model tier) |
| Any language-specific trigger (Step 5) | Any | REVIEW (use security model tier) |
| Architectural + >200 lines | >= 0.70 | REVIEW (use review model tier) |
| Critical logic only | >= 0.70 | REVIEW (use analyze model tier) |
| Scope only (>200 lines) | >= 0.70 | REVIEW (use review model tier) |
| None triggered | >= 0.80 | SKIP review |
| None triggered | < 0.80 | REVIEW (insufficient confidence to skip) |
