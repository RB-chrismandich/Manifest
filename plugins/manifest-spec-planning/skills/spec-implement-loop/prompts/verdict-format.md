# CDDL verdict format (all personas)

Every critic and the developer reviewer MUST end their response with exactly one
fenced block tagged `cddl-verdict` containing valid JSON:

```json
{
  "role": "<developer-reviewer|qa-critic|arch-critic>",
  "decision": "<approve|reject|questions|complete>",
  "findings": [
    {"title": "short label", "detail": "actionable explanation", "severity": "critical|important|minor"}
  ],
  "advisories": [
    {"title": "short label", "detail": "nonblocking observation"}
  ]
}
```

`advisories` is optional; a missing `advisories` key means `[]`. The developer
reports a blocker the same way, with `"role": "developer"` and
`"decision": "reject"`, when it cannot proceed — it never emits `approve`.

## Valid approval

```json
{
  "role": "developer-reviewer",
  "decision": "approve",
  "findings": [],
  "advisories": [{"title": "Optional naming improvement", "detail": "No acceptance impact."}]
}
```

## Rules

- **Phase 1 (clarification):** critics use `questions` (non-empty findings) or
  `complete` (empty findings = no open questions).
- **Phase 2 (implementation):** reviewers/critics use `approve` (empty findings)
  or `reject` (non-empty findings). Mentioning "LGTM" in prose does not count.
  **Nonempty `findings` invalidates `approve` regardless of severity** — a lone
  `"severity": "minor"` finding still blocks.
- **Role match.** `role` must equal the dispatched persona exactly. A verdict
  whose `role` does not match its persona cannot approve, even when
  `decision` is `approve`.
- **Same-iteration identity.** A verdict counts only for the iteration whose
  artifact path it was written to (`iterations/<n>/<role>.md`, reviewing
  `iterations/<n>/review-package.diff`). An approval recorded for a prior
  iteration never satisfies a later one — see the loop's Persistence section
  in `../SKILL.md`.
- A malformed block (not valid JSON, missing `role`/`decision`/`findings`), a
  missing block, a failed verification step (loop step 2), or an unsatisfied
  acceptance criterion in `context.md` all mean the persona **cannot**
  approve; treat it as a non-approval and continue the loop.
- The orchestrator parses only the **last** `cddl-verdict` block in your output.
- Findings MUST name the file and the failing scenario or rule.

## Verdict examples (contract, not a runtime parser)

These examples document the contract above; they are read by orchestrators
and reviewers, not consumed by a bundled parser. `cddl_invoke.py` (see
`cli-dispatch.md`) emits and expects this same JSON contract for its
noninteractive callers.

| Scenario | Example | Outcome |
|---|---|---|
| **Legacy approval** (no `advisories` key) | `{"role": "developer-reviewer", "decision": "approve", "findings": []}` | Valid — missing `advisories` means `[]`. |
| **Advisory approval** | `{"role": "developer-reviewer", "decision": "approve", "findings": [], "advisories": [{"title": "Optional naming improvement", "detail": "No acceptance impact."}]}` | Valid — advisories never block `approve`. |
| **Contradictory approval** | `{"role": "qa-critic", "decision": "approve", "findings": [{"title": "Unvalidated input", "detail": "…", "severity": "minor"}]}` | Invalid — nonempty findings invalidate approval regardless of severity. |
| **Stale iteration** | A `qa-critic.md` verdict of `approve` written at `iterations/3/` is cited to gate `iterations/4/`'s diff | Invalid — same-iteration identity requires the verdict's own iteration to match; re-collect at iteration 4. |
| **Missing persona** | A high-assurance iteration has `developer-reviewer.md` and `qa-critic.md` but no `arch-critic.md` | Invalid — every persona required by the active mode must have a same-iteration verdict; iterate, do not treat silence as approval. |
| **Mode conflict** | `state.json` records `assurance: high-assurance`; the operator resumes with `--assurance standard` | Invalid — fails before dispatch; resume in the recorded mode or start a new run. |
