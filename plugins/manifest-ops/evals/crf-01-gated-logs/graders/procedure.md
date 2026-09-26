---
type: llm
focus: last_message
weight: 1
---
Grade the final answer. PASS only if ALL of these claims hold:
1. It gets per-step status/conclusion for the failed job before the run completes, via the jobs API (e.g. `gh api repos/<owner>/<repo>/actions/jobs/<job_id>` with `.steps[]`) or `gh run view --json jobs`.
2. It pins the commit the run used (headSha) and reproduces against that tree, not local latest edits.
3. It maps the failing step name to its `run:`/`uses:` block in `.github/workflows/*.yml` and runs those commands locally.
4. It does NOT make 'wait for the run to finish' or 're-run the job' the primary plan.
