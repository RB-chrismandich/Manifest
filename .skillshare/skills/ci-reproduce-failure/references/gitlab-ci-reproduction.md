# GitLab CI Reproduction Commands (for the gated-failure method)

This reference translates the GitHub `gh run`/`gh api` vocabulary in
`ci-reproduce-failure/SKILL.md` (and its duplicate,
`reproduce-gated-ci-failure-locally/SKILL.md`) into GitLab CI's real `glab ci`/`glab
api`/`glab job` equivalents. The **method** (pinpoint the failing unit → pin the commit
→ find its real definition → reproduce locally → check generated-artifact drift first →
confirm scope → fix and verify) is unchanged — only the commands and one structural
detail (job-definition lookup) differ. Load this instead of, not in addition to, the
GitHub-specific numbered steps when `ci_platform.sh` reports `gitlab-ci`.

**Read this first — GitHub's "step" has no exact GitLab analog.** GitHub Actions
exposes per-**step** conclusions inside a job (`gh api .../jobs/<job_id>` returns a
`steps[]` array with one entry per `run:`/`uses:` block). GitLab's CI/CD Jobs API
reports status at the **job** level only — a job's `script:` lines are not individually
queryable as separate steps. When a GitLab job fails, "which command inside the job
failed" is not something you fetch from the API before reading the log; you get it by
reading the job's log (`glab ci trace`) or by re-running the job's `script:` lines
locally one at a time, same as step 4 of the GitHub method.

## Mapping table

| GitHub Actions command | GitLab CLI (`glab`) equivalent | Confidence / caveat |
|---|---|---|
| `gh api repos/<o>/<r>/actions/jobs/<job_id> --jq '.steps[]...'` (per-step conclusions) | `glab ci get -p <pipeline-id> --with-job-details --status=failed` — lists the pipeline's jobs and their status; `-d`/`--with-job-details` adds job-level detail. No step-level breakdown exists (see note above). | High that job-level (not step-level) listing is what's available via `glab ci get`; verified flag names against GitLab CLI docs. |
| listing failed runs across the project | `glab ci list --status=failed` (also accepts `-s failed`) | High — flag verified directly against GitLab CLI docs. |
| `gh run view <run_id> --json headSha` (pin the commit) | `glab ci get -p <pipeline-id>` includes commit/ref info in its text/JSON output; for the exact `sha` field with certainty use the raw API: `glab api "projects/:id/pipelines/<pipeline-id>" --jq '.sha'` | Medium on the exact field path through `glab ci get`'s JSON shape (not live-tested); high on the `glab api` fallback since it hits GitLab's documented Pipelines API directly. |
| `gh run view --log-failed` (gated logs) / reading a step's log | `glab ci trace <job-id>` (or `glab ci trace <job-name>`, or bare `glab ci trace` for interactive job selection) — streams the job's log to the terminal in real time. Get the job ID from `glab ci get`/`glab ci list` first. | High — command and flags verified against GitLab CLI docs. |
| downloading run artifacts (`gh api .../actions/runs/<run_id>/artifacts`) | `glab job artifact <ref> <job-name> [--path <dir>]` — **note the command group is `glab job`, not `glab ci`**; there is no `glab ci artifact`. | High — verified directly; this is an easy one to get wrong by guessing `glab ci artifact`. |
| `gh run watch <run_id> --exit-status` (verify the fix) | `glab ci status --live` or `--wait` for the *current branch's* pipeline; to watch/verify a specific (non-current) pipeline, `glab ci view -p <pipeline-id> -w` opens it (interactive/browser), or poll `glab ci get -p <pipeline-id> --status=<state>` | Medium — `glab ci status` did not show a documented `-p/--pipeline-id` flag in the fetched reference, so it appears branch-scoped only; prefer `glab ci get -p <id>` or `glab ci view -p <id>` when you need a specific, non-current pipeline. Re-verify against `glab ci status --help` if precision matters. |

## Job-definition lookup: `.gitlab-ci.yml` + `include:` resolution

GitHub's workflow file is usually self-contained: the step name from the jobs API
maps directly to a `run:`/`uses:` block inside the one `.github/workflows/*.yml` file
that fired the run. GitLab's `.gitlab-ci.yml` is frequently **not** self-contained —
teams factor job definitions out via `include:`, and `include:` supports four
different sources in the same file:

- `local:` — another file in the same repo
- `project:` — a file from a different GitLab project
- `remote:` — a raw URL outside GitLab
- `template:` — a GitLab-maintained CI/CD template, or a CI/CD Component from the
  Components catalog

The failing job's real `script:`/`variables:`/`extends:` definition may live in any
of these, not in the top-level `.gitlab-ci.yml` you'd naively open. Don't assume the
job is "missing" from the file you can see — resolve includes first:

```
glab ci config compile              # current directory's .gitlab-ci.yml
glab ci config compile path/to/.gitlab-ci.yml
```

`glab ci config compile` prints the **fully merged, include-resolved** pipeline
definition — the actual job body GitLab will run (or ran), with every `include:`
expanded inline. Read the failing job's block from that output, not from the
unresolved source file, before reproducing its commands locally. (`glab ci lint
[path] --dry-run` is a related check — it validates the config and can simulate
pipeline creation — but `config compile` is the one that shows you the resolved job
body to copy commands from.)

## Sources

- [glab ci get](https://docs.gitlab.com/cli/ci/get/)
- [glab ci list](https://docs.gitlab.com/cli/ci/list/)
- [glab ci trace](https://docs.gitlab.com/cli/ci/trace/)
- [glab ci status](https://docs.gitlab.com/cli/ci/status/)
- [glab ci view](https://gitlab.com/gitlab-org/cli/-/raw/main/docs/source/ci/view.md)
- [glab ci config / config compile](https://docs.gitlab.com/cli/ci/config/)
- [glab ci lint](https://docs.gitlab.com/cli/ci/lint/)
- [glab job artifact](https://docs.gitlab.com/cli/job/artifact/)
- [glab api](https://docs.gitlab.com/cli/api/)
- [Use CI/CD configuration from other files (`include:`)](https://docs.gitlab.com/ci/yaml/includes/)
