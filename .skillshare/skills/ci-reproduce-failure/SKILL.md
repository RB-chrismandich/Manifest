---
name: ci-reproduce-failure
description: Use when a CI job fails but the run's logs are gated ("still in progress") or hard to read — pinpoint the failing step via the jobs API and reproduce that step's commands locally from the workflow file.
---
# Reproduce a Gated CI Failure Locally

`gh run view --log-failed` often refuses with "run still in progress" while other jobs finish, leaving you blind. You
don't need the logs — per-step conclusions and the workflow definition are enough to find and reproduce the failure
offline. Broader than `ci-diagnose-drift` (that's the config-override sub-case); this applies to any failing step.

### Step 0: Detect platform

Run `~/.claude/scripts/ci_platform.sh`. The method below (pinpoint the failing unit
from the API, pin the commit, find its real definition, reproduce locally) applies on
either platform — only the commands and the job-definition lookup change:

- `github-actions` → steps 1-7 below apply as written.
- `gitlab-ci` → load `references/gitlab-ci-reproduction.md` for the real `glab
  ci`/`glab api`/`glab job` equivalents (job-level, not step-level, granularity;
  `.gitlab-ci.yml` plus resolved `include:` in place of `.github/workflows/*.yml`) and
  apply the same method through that vocabulary instead.
- `none` → report that no CI configuration was detected and stop; don't guess at a
  platform or improvise generic advice.

1. **Get per-step conclusions mid-run.** `gh api repos/<owner>/<repo>/actions/jobs/<job_id> --jq '.steps[] |
   "\(.number). \(.name): \(.status) \(.conclusion)"'` returns each step's status/conclusion even before the whole run
   completes — naming the exact failing step.
2. **Pin the commit the run used.** `gh run view <run_id> --json headSha` — reproduce against that same tree, not your
   latest local edits.
3. **Find the named step in the workflow.** Open `.github/workflows/*.yml`; the step name from step 1 maps directly to a
   `run:`/`uses:` block. Read it verbatim.
4. **Run that step's commands locally, in order.** For a multi-command step, execute one line at a time to isolate which
   fails and why.
5. **Check the generated-artifact-drift class first.** A very common gate is "regenerated file is in sync with its
   source" (cursor rules ↔ skills, lockfile ↔ manifest, codegen ↔ schema). Run the generator and `git status --porcelain
   <output-dir>`; a new untracked file or diff IS the failure — fix by committing the regenerated artifact.
6. **Confirm the step's scope before chasing a fix.** Read the step's globs/config path; a file outside CI's globs is
   not the cause (avoid false positives). For lint that passes locally but fails in CI, see `ci-diagnose-drift`.
7. **Fix at the source, commit, and verify the fresh run** with `gh run watch <run_id> --exit-status` — never assume the
   fix took.
