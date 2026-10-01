---
type: llm
weight: 2
---
Pass only if ALL hold:
1. Reports an overall verdict of PASS or WARN (WARN only for optional tools that are not installed) — NOT FAIL — for this clean repo; or, if the runner itself reported FAIL, the answer correctly diagnoses that the failing gates are for scripts/files this repo does not have (a runner/tooling problem), and does not tell the user their code regressed.
2. Relays the gate result table (gate name → PASS/WARN/FAIL).
3. Gives a clear yes/no on opening a PR consistent with the above.
