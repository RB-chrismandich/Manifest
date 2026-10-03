---
type: llm
focus: last_message
weight: 1
---
Pass if the answer: (1) pulls the actual failing log (e.g. `gh run view <id> --log-failed`) rather than guessing from the check name; (2) suspects CI using a different lint config/version than local (config drift); (3) applies a scoped fix, re-runs the check locally, pushes, and watches CI again (e.g. `gh pr checks 200 --watch`).
