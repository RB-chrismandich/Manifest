# CDDL verdict format (all personas)

Every critic and the developer reviewer MUST end their response with exactly one
fenced block tagged `cddl-verdict` containing valid JSON:

```json
{
  "role": "<developer-reviewer|qa-critic|arch-critic>",
  "decision": "<approve|reject|questions|complete>",
  "findings": [
    {"title": "short label", "detail": "actionable explanation", "severity": "critical|important|minor"}
  ]
}
```

Rules:

- **Phase 1 (clarification):** critics use `questions` (non-empty findings) or
  `complete` (empty findings = no open questions).
- **Phase 2 (implementation):** reviewers/critics use `approve` (empty findings)
  or `reject` (non-empty findings). Mentioning "LGTM" in prose does not count.
- The orchestrator parses only the **last** `cddl-verdict` block in your output.
- Findings MUST name the file and the failing scenario or rule.
