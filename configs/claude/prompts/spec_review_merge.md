<!-- configs/claude/prompts/spec_review_merge.md -->
# Merge Reviewer Findings

Several independent reviewers each cross-referenced a project's planning artifacts
for internal consistency. Their raw findings are below. Merge them into ONE list:

- Combine findings that describe the same gap into a single block (keep the
  clearest wording and the most concrete recommendation).
- Drop exact or near-duplicate findings.
- Do not invent new findings that no reviewer raised.

## Reviewer findings

{{REVIEWS}}

## Output

For EACH distinct inconsistency, output one block in EXACTLY this format:

⚠️  CLARIFICATION REQUIRED: <short title>
   ├─ Location: <artifact A> vs <artifact B>
   ├─ The Gap: <one sentence>
   ├─ Recommended Direction: <concrete remediation>
   └─ Reason Why: <which constraint it violates / why it matters>

If the reviewers found no real inconsistencies, output the single token: NO_ISSUES
