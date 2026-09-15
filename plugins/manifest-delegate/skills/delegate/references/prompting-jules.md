# Jules remote tasks

Jules works on an authorized GitHub repository in the cloud. Supply a complete
task with acceptance criteria and repository-relative paths. Local edits,
untracked files, home configuration, and current-branch context are not uploaded.
Never include credentials in the prompt.

Use `task --backend jules --remote-write --repo OWNER/REPO
--remote-base provider-selected --task-file TASK.md`. The explicit base choice
acknowledges that Jules CLI 0.1.42 has no branch-selection flag. If the task needs
a specific branch or local-only changes, use the Jules UI to select the branch;
do not imply that the CLI selected it. The repository must already appear in
`jules remote list --repo`. `--write` alone does not authorize remote work.

Submission returns a local job ID and a cloud session link when recognized.
It does not mean the coding task completed. `--background` and `--wait` both
wait only for submission (at most 120 seconds); cloud observation uses
`status JOB_ID --wait --timeout 600` separately. Unknown submissions are retained
and never retried automatically. Inspect Jules before starting another task.

Jules chooses its own model. Model chains, automatic fallback, resume, remote
cancellation, read-only reviews, second opinions, and review gates are unsupported.
Use the session link to give feedback, approve a plan, or stop cloud work.
Stopping the local command does not stop the cloud task.

`pull JOB_ID` saves a completed task's patch for inspection. After reviewing it,
`apply JOB_ID` applies that saved patch only in a clean matching repository.
Neither operation pushes or merges. Missing or truncated table rows are reported
as unavailable status, never inferred as completion. CLI output is not a stable
JSON API, so a new output format may require updating the parser.

Authentication: `jules login` uses the vendor's browser flow. Manifest reuses its
stored login and never copies tokens or falls back to an API key. Verify access
with two separate `jules remote list --repo` invocations. Empty output cannot
establish repository access. Long-term refresh remains subject to the provider.

For issue-driven work, authorize the Jules GitHub App and apply the `jules` label
(case insensitive) to a GitHub issue. Do not also submit that issue through the
CLI: those are two independent task triggers. PR monitoring observes Jules
feedback when present; it does not label linked issues automatically.

Sources: [CLI](https://jules.google/docs/cli/reference),
[issue labels](https://jules.google/docs/running-tasks/).
