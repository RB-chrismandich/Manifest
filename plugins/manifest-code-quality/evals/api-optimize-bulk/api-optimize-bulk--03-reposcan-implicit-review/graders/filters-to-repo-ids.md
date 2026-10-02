---
type: llm
weight: 0.5
---
Score 1 if the answer notes that the org-wide result should be filtered in-process down to the `repo_ids` the caller actually cares about (rather than assuming every org repo is wanted), or otherwise addresses matching the bulk result back to the original `repo_ids` set. Score 0 if this is not mentioned at all.
