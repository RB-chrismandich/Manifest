---
type: llm
focus: last_message
weight: 1
---
Grade the final answer. PASS only if ALL of these claims hold:
1. It uses glab or the GitLab API to get the job's status/details (e.g. `glab ci view`, `glab api projects/:id/jobs/:job_id`, or `glab ci trace`).
2. It resolves the fully merged job definition across `include:` and `extends:` (e.g. `glab ci config compile` or the CI lint/merged YAML view) to get the real `script:`/`before_script:`.
3. It pins the pipeline's commit SHA and runs the job's script lines locally (ideally one at a time, in the job's image).
4. It does NOT stop at 'raise the log limit' or 're-run the job' as the plan.
