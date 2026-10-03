# manifest-code-quality evals

Ablation suites for all 24 manifest-code-quality skills: 188 cases (167
baseline + 21 `--1N-hard-*` discrimination probes), one directory per skill
(`<skill>/<skill>--NN-<slug>/`). The headline number is Δ — the with-plugin
score minus the without-plugin score.

## Run

From `plugins/manifest-code-quality/`:

```bash
claude plugin eval . --ablation with-without \
  --judge-model opus --allow-tools Write Edit Bash
```

Every flag is required for a meaningful result:

| Flag | Why |
|------|-----|
| `--judge-model opus` | Cases pin `model: sonnet`; the judge must be a different, larger model (the runner default is Haiku). |
| `--allow-tools Write Edit Bash` | 28 cases write files or run scoped `Bash(...)` commands (e.g. `code-audit-constitution`, `project-scaffold`); without the grant they score permission failures, not the skill. |

Add `--no-publish` to keep the report local. For a suite this size, run one
skill at a time (`--case '<skill>--*'`) so a claude.ai session-limit hit zeroes
one batch instead of the whole run, and check each `aggregate-result.json` for
"session limit" errors before trusting its numbers.

## Known environment limit

The five `ai-code-audit` cases grant `Bash(git:*)`. In a macOS agent sandbox,
Apple's `/usr/bin/git` can fail through `xcrun`; if those runs show git errors,
move the repo setup into a harness-run `scaffold.sh` (`case.yaml` →
`context.scaffold_script`, run with `--scaffold`) as manifest-ops does.

## Discrimination probe: `--1N-hard-*` cases

Seven skills scored Δ≈0 in the full suite (`refactor`, `python-refactor`,
`node-refactor`, `go-refactor`, `shell-audit-pipefail`, `data-validate-live`,
`api-optimize-bulk`). Each now has three `<skill>--1N-hard-*` cases built around
a rule from its SKILL.md that a generic review tends to miss. 3-run result
on the final graders (`--ablation with-without`, sonnet agent, opus judge,
2026-10-02, $21): with 0.99 / without 0.98 / Δ +0.01 over the 21 cases. Only
`refactor--12-hard-shell-go-token-pipeline` separates the arms (with 1.00,
without 0.78, Δ +0.22); the other 20 score the same in both arms, so for these
skills the evals find no measurable lift over the base model and the cases stay
as regression tests. `python-refactor--12` scores 0.78 in both arms: one run
per arm lost a 2–1 judge vote on an answer that did refuse to fabricate check
output. Earlier measurements on pre-review graders disagree: a 3-run probe put
`node-refactor--11` at Δ +0.44 (now +0.00), and a one-run pilot put
`refactor--12` and `api-optimize-bulk--11` at Δ +0.67 (now +0.22 and +0.00).
Treat any single case's Δ as noisy until it repeats across runs.

## Baseline results

Full suite on `main` at `e8819f2e` (after #1007 fixed seven skill defects),
2026-10-02: sonnet agent, opus judge, `runs: 3`, `--ablation with-without`.
The previous run (2026-09-27, before those fixes) scored with 0.90 /
without 0.82 / Δ +0.08; the fixes lifted the with-plugin arm to 0.95, and the
former regressions (`shell-audit-errexit`, `node-refactor`, `data-wire-field`)
are now at or above zero. Overall Δ is unchanged because the without-plugin
arm also scored higher this run, so compare per-skill rows across runs, not
just the headline. Excludes the `--1N-hard-*` cases above.

| Skill | Cases | With | Without | Δ |
|---|---|---|---|---|
| `ai-code-audit` | 7 | 0.98 | 0.70 | +0.29 |
| `antipattern-detect` | 7 | 0.81 | 0.73 | +0.07 |
| `api-optimize-bulk` | 6 | 1.00 | 1.00 | +0.00 |
| `cli-audit-help` | 7 | 1.00 | 0.83 | +0.17 |
| `code-audit-constitution` | 7 | 0.84 | 0.55 | +0.30 |
| `data-design-ingestion` | 8 | 1.00 | 0.75 | +0.25 |
| `data-validate-live` | 7 | 1.00 | 1.00 | +0.00 |
| `data-wire-field` | 7 | 0.93 | 0.86 | +0.08 |
| `false-green-check-audit` | 7 | 0.93 | 0.90 | +0.02 |
| `go-refactor` | 7 | 0.92 | 0.86 | +0.06 |
| `llm-invoke-stdin` | 7 | 0.92 | 0.91 | +0.01 |
| `node-refactor` | 7 | 1.00 | 0.97 | +0.03 |
| `project-scaffold` | 7 | 0.92 | 0.82 | +0.09 |
| `project-verify` | 7 | 0.94 | 0.91 | +0.03 |
| `python-refactor` | 7 | 0.95 | 0.99 | -0.04 |
| `refactor` | 7 | 1.00 | 1.00 | +0.00 |
| `shell-audit-errexit` | 7 | 1.00 | 1.00 | +0.00 |
| `shell-audit-pipefail` | 7 | 0.94 | 0.87 | +0.06 |
| `shell-audit` | 8 | 0.95 | 0.90 | +0.05 |
| `shell-refactor` | 7 | 0.98 | 0.98 | +0.00 |
| `smoke-manage` | 7 | 0.97 | 0.76 | +0.21 |
| `terraform-refactor` | 7 | 0.90 | 0.93 | -0.02 |
| `test-pin-bug` | 6 | 1.00 | 0.78 | +0.22 |
| `test-vary-fixtures` | 6 | 0.94 | 0.85 | +0.09 |
| **Overall** | 167 | **0.95** | **0.87** | **+0.08** |
