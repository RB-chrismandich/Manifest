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

### Step 1: Trust-boundary change

Determine whether changed behavior crosses authentication, authorization,
cryptographic, secret-handling, validation, privilege, network, or another
trust boundary. Evidence must describe the changed behavior and boundary, not
an identifier or keyword.

### Step 2: Destructive behavior

Determine whether the change deletes, migrates, deploys, irreversibly mutates,
or otherwise causes hard-to-reverse data or infrastructure effects.

### Step 3: Broad compatibility or deployment change

Determine whether a public compatibility, platform, deployment, or operational
change has broad impact. File, line, package, module, or language counts do
not establish this condition.

### Step 4: Conflicting evidence or unresolved uncertainty

Determine whether available evidence conflicts or a material uncertainty cannot
be resolved through a single capable review.

### Step 5: Genuinely independent codebase-wide tracks

Determine whether a codebase-wide investigation with genuinely independent
tracks exists. File, package, module, language, keyword, and independent-unit
counts never trigger independent review.

## Confidence Calibration

Rate confidence in the evidence assessment on a 0.0-1.0 scale. Low confidence
does not independently trigger review. It triggers independent review only when
the missing or conflicting evidence is material and remains unresolved after one
capable review; record that fourth risk condition explicitly.

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
  "reason": "Changed authorization behavior crosses a trust boundary",
  "triggered_criteria": [
    {
      "criterion": "trust_boundary_change",
      "step": 1,
      "evidence": "The changed authorization decision grants a new caller role access",
      "severity": "high"
    }
  ],
  "non_triggered_criteria": [
    {
      "criterion": "destructive_behavior",
      "step": 2,
      "reason": "No irreversible data or infrastructure operation changed"
    }
  ],
  "confidence": 0.92,
  "calibration_notes": "The authorization behavior and its affected caller role are explicit.",
  "scope_summary": {
    "files_changed": 3,
    "lines_added": 120,
    "lines_removed": 45,
    "languages": ["python", "yaml"]
  }
}
```

## Decision Matrix

| Criteria Triggered | Decision |
|--------------------|----------|
| Any of Steps 1-5 | REVIEW; record the concrete condition and evidence |
| None, confidence >= 0.70 with complete context | Single-agent inline review |
| None, confidence < 0.70 or incomplete context | REVIEW for conflicting evidence or unresolved uncertainty; record the missing context |
