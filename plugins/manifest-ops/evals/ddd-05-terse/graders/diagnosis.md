---
type: llm
focus: last_message
weight: 1
---
Grade the final answer. PASS only if ALL of these claims hold:
1. It points at the difference between the deployer's fresh-install and existing-install code paths (e.g. preserve-on-existing / skip-if-exists logic) as the likely cause.
2. It recommends reading both branches of the deployer and comparing against the source definition/docs to classify the gap.
3. It does NOT stop at 'just relink the missing four'; any backfill is paired with fixing the deployer.
