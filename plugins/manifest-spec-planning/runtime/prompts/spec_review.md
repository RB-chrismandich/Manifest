# Project Artifact Cross-Reference

You are an independent reviewer cross-referencing a project's planning artifacts
for **internal consistency**. You did not write them. Find places where the
artifacts contradict each other or leave a decision dangerously ambiguous.

When `tasks` is absent, the task breakdown is embedded inside the plan — review
the plan's task section against the spec and plan prose.

## Artifacts

{{ARTIFACTS}}

## Output

For EACH inconsistency, output one block in EXACTLY this format:

⚠️  CLARIFICATION REQUIRED: <short title>
   ├─ Location: <artifact A> vs <artifact B>
   ├─ The Gap: <one sentence>
   ├─ Recommended Direction: <concrete remediation>
   └─ Reason Why: <which constraint it violates / why it matters>

If the artifacts are consistent, output the single token: NO_ISSUES
