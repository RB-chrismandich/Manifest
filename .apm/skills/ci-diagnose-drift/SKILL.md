---
name: ci-diagnose-drift
description: Diagnose lint/format failures that only appear in CI (pass locally) by finding where CI overrides the repo's committed linter config, then verify the fix at the annotation level
---
# CI Lint Config Drift

Use when a linter (yamllint, markdownlint, eslint, ruff, etc.) flags issues in CI but passes locally, or flags at a
stricter threshold than the repo's committed config declares.

### Step 0: Detect platform

Run `~/.claude/scripts/ci_platform.sh`. The diagnosis method below (compare the
repo's committed linter config against how CI actually invokes the linter, confirm
the mismatch is the root cause, fix in the deliberate direction, verify at the
annotation level) applies on either platform — only where CI's overrides live
changes:

- `github-actions` → the workflow-file override sources in step 2 below apply as
  written.
- `gitlab-ci` → in addition to reading `.gitlab-ci.yml` itself, resolve its
  `include:` directives first — the job that runs the linter may be defined in an
  included file, not the top-level `.gitlab-ci.yml` (`glab ci config compile` prints
  the fully merged, include-resolved config; see
  `~/.claude/skills/ci-reproduce-failure/references/gitlab-ci-reproduction.md` for
  the command). Then check the GitLab-specific override locations in step 2 below.
- `none` → report that no CI configuration was detected and stop; don't guess at a
  platform.

1. Read the **repo's committed linter config** (`.yamllint`, `.markdownlint*`, `.eslintrc`, `pyproject.toml`, etc.) —
   note the actual declared thresholds (e.g. `line-length: max 150, level warning`).
2. Read **how CI invokes the linter** in the workflow file (`.github/workflows/*.yml`, `.gitlab-ci.yml` — resolved via
   `glab ci config compile` on GitLab, see Step 0). Look for flags that override the committed config:
   - `-d relaxed` / `-d default` (yamllint presets force their own limits, ignoring `.yamllint`)
   - inline `--max-line-length`, `--config <other-file>`, `--preset`
   - a linter invoked without `-c/--config` so it never finds the repo config
   - **GitLab-specific override locations** (no GitHub Actions analog — GitHub's per-step `run:` blocks don't have
     a separate global-override layer of this kind):
     - a job-level or top-level `variables:` block setting a linter env var (e.g. `RUFF_CONFIG`,
       `ESLINT_CONFIG`) or passing extra CLI flags through a variable the `script:` line interpolates
     - `before_script:`/`after_script:` (job-level or global, in the top-level file or an included one) —
       these commonly install a *different* linter config, `cd` into a subdirectory before invoking the
       linter (changing which config file it auto-discovers), or append override flags before the job's own
       `script:` runs
     - **instance/group-level enforced pipeline configuration** — GitLab's Ultimate tier lets a group admin
       apply a compliance framework whose *pipeline execution policy* (the current mechanism; the older
       "compliance pipelines" feature is deprecated since GitLab 17.3, removal targeted for GitLab 19.0)
       injects additional CI/CD configuration into every scoped project's pipeline **without it appearing in
       that project's own `.gitlab-ci.yml`**. If the override isn't in the repo's config or any `include:` you
       can resolve, this is the next place to check — ask a group Owner/Maintainer to check
       `Group > Secure > Policies` (or the deprecated `Group > Settings > Compliance > Frameworks`) rather than
       assuming the drift is unexplained. There is no exact GitHub Actions equivalent: GitHub's closest
       feature (org-level required workflows) runs as visible, separate check runs rather than being merged
       invisibly into the repo's own pipeline, so don't force the GitHub mental model onto this case.
3. **Confirm the mismatch is the root cause**: run the linter locally the way the *repo config* intends, and separately
   the way *CI* invokes it. If the repo-config run is clean (or nearly), the drift is the bug — not the flagged lines.
4. Decide the fix direction deliberately:
   - **Make CI honor the committed config** (drop the override flag / add `-c .yamllint`) — correct when the project has
     intentionally adopted those thresholds. Don't rewrap a dozen lines to satisfy a limit the project doesn't actually
     adopt.
   - **Tighten the committed config to match CI** — correct when CI's stricter limit is the intended policy and the
     committed config is stale.
5. Surfacing the stricter config often reveals **one or two real nits** (e.g. a comment-indentation issue) — fix those
   too so the chosen config passes cleanly.
6. While here, check for **deprecated CI runtimes** the same job pulls in (e.g. a marketplace action `using: node20`
   that the platform is removing). Bump to the latest major and verify its `action.yml` declares the current runtime
   before committing.
7. Push, then **verify at the annotation level, not just job status**: confirm the specific warnings/errors are gone
   from the run's annotations (`gh run view --log` / the checks API), not merely that the job turned green — a job can
   pass while still emitting the annotations you were trying to eliminate.
