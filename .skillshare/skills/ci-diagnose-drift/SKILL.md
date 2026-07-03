---
name: ci-diagnose-drift
description: Diagnose lint/format failures that only appear in CI (pass locally) by finding where CI overrides the repo's committed linter config, then verify the fix at the annotation level
---
# CI Lint Config Drift

Use when a linter (yamllint, markdownlint, eslint, ruff, etc.) flags issues in CI but passes locally, or flags at a stricter threshold than the repo's committed config declares.

1. Read the **repo's committed linter config** (`.yamllint`, `.markdownlint*`, `.eslintrc`, `pyproject.toml`, etc.) — note the actual declared thresholds (e.g. `line-length: max 150, level warning`).
2. Read **how CI invokes the linter** in the workflow file (`.github/workflows/*.yml`, `.gitlab-ci.yml`). Look for flags that override the committed config:
   - `-d relaxed` / `-d default` (yamllint presets force their own limits, ignoring `.yamllint`)
   - inline `--max-line-length`, `--config <other-file>`, `--preset`
   - a linter invoked without `-c/--config` so it never finds the repo config
3. **Confirm the mismatch is the root cause**: run the linter locally the way the *repo config* intends, and separately the way *CI* invokes it. If the repo-config run is clean (or nearly), the drift is the bug — not the flagged lines.
4. Decide the fix direction deliberately:
   - **Make CI honor the committed config** (drop the override flag / add `-c .yamllint`) — correct when the project has intentionally adopted those thresholds. Don't rewrap a dozen lines to satisfy a limit the project doesn't actually adopt.
   - **Tighten the committed config to match CI** — correct when CI's stricter limit is the intended policy and the committed config is stale.
5. Surfacing the stricter config often reveals **one or two real nits** (e.g. a comment-indentation issue) — fix those too so the chosen config passes cleanly.
6. While here, check for **deprecated CI runtimes** the same job pulls in (e.g. a marketplace action `using: node20` that the platform is removing). Bump to the latest major and verify its `action.yml` declares the current runtime before committing.
7. Push, then **verify at the annotation level, not just job status**: confirm the specific warnings/errors are gone from the run's annotations (`gh run view --log` / the checks API), not merely that the job turned green — a job can pass while still emitting the annotations you were trying to eliminate.
