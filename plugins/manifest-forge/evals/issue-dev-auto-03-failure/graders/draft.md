---
type: llm
focus: last_message
weight: 1
---
Pass if the answer opens a DRAFT PR/MR (e.g. `--draft`) for the WIP, and the PR body it proposes does not use a closing keyword for #57 (using `Refs #57`, or warning the user not to use `Closes #57`, is correct and should pass).
