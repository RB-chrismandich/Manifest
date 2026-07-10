# Contract: Critic Verdict Format (`cddl-verdict`)

**Feature**: `482-critic-dev-loop` | Enforces spec FR-003, FR-005, FR-006

Every critic invocation MUST end its output with exactly one fenced block:

````text
```cddl-verdict
{ ...single JSON object... }
```
````

## JSON schema

```json
{
  "role":     "qa_critic | arch_critic",          // must equal the invoked role
  "decision": "approve | reject | questions | complete",
  "findings": [                                    // required non-empty for reject/questions
    { "title": "...", "detail": "...", "severity": "high|medium|low" }
  ]
}
```

Phase-appropriate decisions (anything else = non-approval):

| Phase | Allowed decisions |
|---|---|
| 1 (clarification) | `complete` (gate signal, FR-003) or `questions` (findings = the questions) |
| 2 (implementation) | `approve` or `reject` (findings = deficiencies, FR-007) |

## Parsing rules (fail-closed, FR-006)

1. Scan the raw output for fenced ` ```cddl-verdict ` blocks; take the **last** one
   (tolerates preamble/reasoning noise, mirrors the repo's tolerant-parser precedent).
2. Strict `json.loads` — no repair, no partial extraction.
3. Validate: single object; `role` equals the invoked role; `decision` in the
   phase-appropriate set; `findings` is a list, non-empty when `decision` ∈
   {`reject`, `questions`}.
4. **Any** failure (no block, >0 parse errors, wrong role, bad decision, empty
   required findings) ⇒ `parsed_ok=false` ⇒ treated as **non-approval**; the
   invocation gets exactly one retry (same prompt + a parse-failure notice); a second
   failure aborts the run (exit 7).
5. A mention of `cddl-verdict`, `approve`, `LGTM`, or any signal token in prose
   (including inside other fenced blocks that lack the `cddl-verdict` info-string)
   has no effect — only rule 1–3 output counts (spec edge case: verdict spoofing).

## Test fixtures required (D13)

- Happy: single well-formed block per decision type.
- Spoof: rejection prose quoting `"decision": "approve"` and an ` ```cddl-verdict ` example
  inside a ` ```markdown ` fence → must parse the real (last `cddl-verdict`) block only;
  a quoted token with NO real block → non-approval.
- Malformed: truncated JSON, duplicate blocks (last wins), wrong `role`,
  `approve` during phase 1, empty findings on `reject`, no block at all.
