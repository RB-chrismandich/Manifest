---
type: llm
focus: last_message
weight: 1
---
Pass only if the response uses `glab` or GitLab's API to inspect the job, resolves the merged job definition across the local `include:` and `extends:` (for example with the config compiler or merged YAML view), pins the pipeline commit SHA, and runs the effective script locally, preferably command-by-command in the job image. Raising the log limit or rerunning alone is not an adequate answer.
