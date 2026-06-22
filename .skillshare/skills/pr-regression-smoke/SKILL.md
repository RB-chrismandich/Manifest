---
name: pr-regression-smoke
description: |
  Full Manifest regression (CI mirror: shellcheck, yamllint, markdownlint, bats
  + pytest) plus a deployed-env smoke pass (bootstrap re-deploy, env health,
  orchestration round-trip), as a post-PR gate. Use right after a PR opens or
  merges — "regression test the PR", "did the merge break anything", "verify main
  is still green". Whole-repo verdict; prefer over verify (one lang) or health-check.
---

# PR Regression + Smoke

Confirm a pull request introduced no regressions by running the **entire** repo
test suite the way CI does, then exercising the **deployed** environment so you
catch breakage that unit tests can't see (a broken `bootstrap.sh`, a dangling
symlink, an orchestrator that no longer responds).

This skill works on whatever is currently checked out, so it fits both moments a
PR creates risk: right after the branch is pushed (a pre-merge gate) and right
after it merges to `main` (a post-merge regression check). It does not inspect
GitHub state or know about PR numbers — it validates the code in front of it.

## When to reach for this vs. neighbors

- **`verify`** runs a *single project's* lint/test/security for one language. Use
  it for a quick quality pass on a subdirectory. This skill is the whole-repo,
  CI-equivalent gate plus a smoke pass — heavier and PR-scoped.
- **`health-check`** validates only the deployed environment (configs, symlinks,
  auth). That is a *subset* of this skill's smoke phase.
- Reach for **this** skill when someone wants one verdict answering "is it safe
  to merge / did the merge break anything?"

## How to run it

The deterministic work lives in a bundled runner so the verdict is reproducible
and the exit code can gate a merge or feed a hook. From the repo root:

```bash
.skillshare/skills/pr-regression-smoke/scripts/run_pr_regression.sh
```

Useful flags (the script self-documents via `--help`):

| Flag | Use when |
|------|----------|
| `--quick` | Fast feedback loop: lint + bats only, skips pytest and smoke |
| `--skip-deploy` | You don't want the smoke pass to re-run `bootstrap.sh` against `~/` |
| `--skip-orchestration` | Offline / no API credits — avoids the live agent round-trip |
| `--skip-smoke` | Regression suite only |
| `--skip-regression` | Smoke pass only |

The runner exits **0 (PASS)** when every gate is clean, **1 (WARN)** when only
non-blocking smoke checks degraded (e.g. an unauthenticated agent), and
**2 (FAIL)** when a real regression gate failed. Surface that exit code — it is
the gating signal.

## What it checks

**Regression (mirrors `.github/workflows/ci.yml` — keep them in lockstep):**

- `shellcheck -S warning` over `configs/claude/scripts/*.sh` and `bootstrap.sh` + `bootstrap/lib/*.sh`
- `tests/lint/check_array_expansion.sh`
- `yamllint configs/claude/config/*.yml`
- `markdownlint-cli2` over `AGENTS.md CLAUDE.md README.md docs/*.md`
- generated-artifact drift: `generate_commands_doc.py --check` (docs/COMMANDS.md + GEMINI.md/AGENTS.md command index) and a `generate_cursor_rules.sh` regenerate-and-clean-tree check — adding a skill that forgets these is the classic way a green local run still red-CIs
- `bats tests/bats/` (full suite)
- `pytest tests/python/` (full suite)

**Smoke (deployed environment — what unit tests can't see):**

- `bootstrap.sh --skip-install --skip-auth --force` — the deploy path still works *(hard gate: a broken deploy is a regression)*
- `check_status.sh` — symlinks, config syntax, auth, orchestration readiness *(soft: disabled/unauth agents are normal)*
- `parallel_agent.py --claude-only` round-trip — an agent actually responds end-to-end *(soft)*

## Reporting back to the user

After the run, relay the runner's markdown table and verdict verbatim, then add a
one-line recommendation tied to the exit code:

- **PASS** → "Safe to merge / merge confirmed clean."
- **WARN** → name which smoke check degraded and whether it's environmental
  (e.g. "orchestration warned — this machine isn't authenticated, not a code
  issue") so the user can judge it.
- **FAIL** → lead with the failing gate(s) and the captured tail output; do not
  bury it under the passing rows.

If a gate **fails**, don't stop at reporting — offer to drive `systematic-debugging`
on the first failure, since a red regression suite is exactly what it's for.

## Keeping the mirror honest

The regression list above must track `ci.yml`. If a PR changes CI (adds a lint, a
new test path, bumps a tool), update the runner's `run_regression()` to match in
the same change — a gate that has silently drifted from CI gives false confidence.
When CI and this skill disagree, CI is the source of truth.
