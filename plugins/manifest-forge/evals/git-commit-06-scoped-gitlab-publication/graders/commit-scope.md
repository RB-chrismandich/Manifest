---
type: llm
focus: last_message
weight: 1
---
Pass only if the answer says the failed commit prohibits any push or MR lookup/create; does not stage or discard unrelated staged/unstaged files; continues only after diagnosing/fixing the hook and safely staging the task-owned path/hunks; identifies the task diff as non-empty and intended; and verifies the resulting commit SHA/diff before further publication. It must not use `gh` for this GitLab repository.
