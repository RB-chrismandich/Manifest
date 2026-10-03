# manifest-forge evals

One suite, 20 skills, case dirs prefixed `<skill>-NN-…`. Each case runs with and
without the plugin; the headline number is **Δ** (with − without).

```bash
claude plugin eval . --ablation with-without --judge-model sonnet -j 8 --no-publish
claude plugin eval . --case 'pr-merge-stacked-*' --runs 1 --no-publish   # one skill
```

## Results — 2026-09-26 full run (3 runs × 2 arms, Sonnet judge, $54.03)

Overall **Δ +0.15** (with 0.91, without 0.76). `fired` = with-arm runs where the skill was invoked.

| skill | with | w/o | Δ | fired |
|---|---|---|---|---|
| issue-sync-pr | 0.89 | 0.27 | +0.63 | 7/12 |
| repo-clean | 1.00 | 0.61 | +0.39 | 6/9 |
| pr-merge-stacked | 0.97 | 0.68 | +0.29 | 10/15 |
| lifecycle-run | 0.87 | 0.60 | +0.27 | 3/12 |
| issue-sync-commit | 0.92 | 0.71 | +0.21 | 5/9 |
| issue-manage | 0.92 | 0.75 | +0.17 | 3/9 |
| pr-manage | 0.75 | 0.58 | +0.17 | 4/9 |
| issue-dev-auto | 0.87 | 0.73 | +0.13 | 3/12 |
| pr-monitor | 0.93 | 0.80 | +0.13 | 0/12 |
| branch-clean | 0.92 | 0.79 | +0.12 | 0/9 |
| git-find-artifact | 1.00 | 0.89 | +0.11 | 3/12 |
| git-commit | 0.91 | 0.86 | +0.06 | 3/12 |
| pr-address-comments | 0.91 | 0.86 | +0.06 | 0/12 |
| pr-triage-bots | 0.98 | 0.93 | +0.05 | 2/9 |
| issue-prep-auto | 0.83 | 0.79 | +0.04 | 2/9 |
| pr-clean-base | 1.00 | 0.96 | +0.04 | 0/9 |
| issue-prioritize | 0.97 | 0.97 | 0.00 | 0/9 |
| pr-review | 0.92 | 0.92 | 0.00 | 0/9 |
| pr-reset-reapply | 0.84 | 0.90 | −0.06 | 0/9 |
| issue-triage | 0.76 | 0.83 | −0.07 | 1/9 |

Positive Δ on a skill that never fired (e.g. pr-monitor, branch-clean) is run-to-run
noise, not plugin uplift; treat |Δ| < ~0.1 as zero.

**Re-measure 2026-10-01 (runs: 3, Opus judge, $46.83):** overall with 0.94 / without 0.81 (Δ +0.14, 91 cases).
New scored `skill-did-not-fire` graders: 66/66 with-arm runs pass. Lowest: issue-manage-02 0.33, lifecycle-run-02
0.33, pr-merge-stacked-02 0.56 (skill fired 0/3; the `sanity check` prompt misses the trigger), git-commit-02 0.67,
issue-dev-auto-04 0.67, pr-monitor-01 0.67. pr-merge-stacked (new oracle) 0.94 / 0.79. pr-reset-reapply-01 0.80:
the `reset` regex now accepts `rebase --onto`; `fresh-pr` fails 3/3 because answers omit that #301 is merged and a
new PR is needed (a real answer gap, not a grader conflict).

**pr-merge-stacked row is stale (2026-10-01).** Its oracle encoded the pre-2020 GitHub
behavior ("deleting a merged parent branch closes the child"). GitHub retargets the child
instead (`automatic_base_change_succeeded`/`_failed` timeline events), and GitLab retargets
up to four MRs on merge. The skill and cases 01–05 were rewritten around verifying the
retarget, rebasing after a squash merge, and recovering from a deleted *unmerged* parent
(case 03 premise changed). Scores before that date are not comparable.

## Design decisions (made under `/goal`, not individually gate-approved)

- **Answer-only cases.** The eval sandbox blocks macOS's `/usr/bin/git` stub
  (xcrun cache write denied), and there is no forge/tracker. Every case therefore
  pastes the situation (command output, PR/issue lists) and grades the advice.
  `allowed_tools: [Skill]`; prompts end with "you can't access my repo" so agents
  don't mistake the sandbox cwd for the user's repo.
- **Outcome graders** are per-criterion `llm` rubrics (Sonnet judge) plus `regex`
  where a concrete command is the outcome. `skill-fired` (`tool_used: Skill`) is
  display-only under ablation.
- Every skill has ≥1 should-NOT-fire case; each carries a scored `skill-did-not-fire`
  grader (`tool_used: Skill`, `input_match: <skill>`, `max: 0`, `arm: both`); `runs: 3`.
- **Side-channels:** answer-only, 1–5 turns, ~$0.07–0.12 per run, 180 s ceiling.

## Things I'm unsure about

- `pr-triage-bots-01/verify-613` fails in both arms. The prompt shows no diff,
  so "verify before merge" may be unreachable.
- `issue-dev-auto-03/blocked` and `git-commit-02/order` are skill-specific
  details. They are scored at 0.5 or kept deliberately, but judges vary on them.
- Router skills (`issue-manage`, `pr-manage`) name the skill in the prompt, so the
  baseline arm answers "no such skill". That's part of their Δ.
- Pure-knowledge skills (`git-find-artifact`, `pr-clean-base`, `pr-reset-reapply`,
  `branch-clean`) show Δ ≈ 0 because the base model already knows the moves.

## Follow-ups (plugin is read-only here)

- **The skills rarely trigger.** `skill-fired` is 0× on most answer-only cases, so
  descriptions under-match natural phrasing.
- **The untracked plugin `CLAUDE.md`** mandates `ctx_*` tools the plugin doesn't ship.
- **`.gitleaks.toml` needs a path allowlist** for
  `plugins/manifest-forge/evals/git-commit-01-gitleaks/prompt\.md`, which holds a
  fabricated secret. The edit was blocked in-session, so it must be applied manually.
