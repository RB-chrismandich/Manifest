# Pre-flight Analysis Task

Determine whether proposed code changes require independent review under the
canonical risk gate. Use one capable reviewing agent by default.

## Changes to Analyze

{FILES_OR_DIFF}

## Independent-review gate

Set `needs_independent_review` to `true` only when at least one condition is
supported by evidence:

1. A trust-boundary change.
2. Destructive behavior.
3. A broad compatibility or deployment change.
4. Conflicting evidence or unresolved uncertainty.
5. A codebase-wide investigation with genuinely independent tracks.

File, package, module, language, keyword, line-count, file-count, and
independent-unit counts never trigger independent review; they are context
only. Do not infer a trigger from low confidence alone: report uncertainty as
evidence and escalate only when it is materially unresolved. Workload
decomposition is separate and may fan out genuinely independent work without
requesting independent review.

## Output Format

Return only this JSON object:

```json
{
  "needs_independent_review": true,
  "review_mode": "single-agent|independent-review",
  "escalation_reason": "one canonical condition, or null",
  "evidence": [
    {
      "condition": "trust_boundary_change",
      "evidence": "specific changed behavior"
    }
  ],
  "non_triggers_considered": ["line_count", "language"],
  "confidence": 0.92,
  "calibration_notes": "Confidence informs the evidence assessment; it is not a trigger."
}
```
