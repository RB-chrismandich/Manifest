---
type: llm
focus: last_message
weight: 1
---
Pass only if the answer gives a way to inspect the failed job's individual step status/conclusion while the workflow run is still active, such as the jobs API or `gh run view --json jobs`. It must identify the run's `headSha`, reproduce from that exact commit, map the failing step name to its workflow `run:`/`uses:` commands, and execute those commands locally. Waiting for completion or rerunning the job cannot be the primary procedure.
