# manifest-delegate eval suites

Two suites, one per skill. Headline number is Δ (with-plugin − without-plugin), per suite.

```bash
# delegate-setup
claude plugin eval . --ablation with-without --case 'setup-*'    --judge-model sonnet --allow-tools Bash       --no-publish
# delegate
claude plugin eval . --ablation with-without --case 'delegate-*' --judge-model sonnet --allow-tools Bash Write --no-publish
```

`Bash`/`Write` are operator grants (`--allow-tools`); neither skill declares `allowed-tools`.
`tool_used: Skill` graders are display-only trigger checks (excluded from score in both arms).

## Sandbox constraint (read first)

In the eval sandbox `HOME` is a temp dir, so `delegate.py` always exits 2 with
`Manifest root runtime is missing manifest-model-policy; re-run ./bootstrap.sh`.
No case can observe a successful backend dispatch. Live cases therefore grade
correct command composition + honest reporting of the failure; all other cases
paste a report/envelope into the prompt so they are deterministic.

## delegate-setup

| case | shape | tools | graders |
|---|---|---|---|
| setup-01-all-backends | live probe, all backends | +Bash | regex: names all six · llm(trace): states/fixes grounded in probe output, probe failure reported honestly |
| setup-02-cursor-disabled-user | pasted row, `disabled_user` | read-only | llm: user `delegation.json` is sufficient, no workspace/admin needed · regex(0.5): `delegation.(json\|yml)` |
| setup-03-jules-exit-zero | "probe is wrong?" | read-only | llm: exit 0 ≠ auth, needs positive repo listing, `jules login` + GitHub App · regex(0.5): `jules login` |
| setup-04-disabled-despite-user | `disabled_workspace` vs user config | read-only | llm: workspace outranks user, edit `services.yml` · regex(0.5): `services.yml` |
| setup-05-ready-vs-runner | `ready` ≠ runner works | read-only | llm: names runner discovery / model as separate prereqs |
| setup-06-neg-python-env | NOT fire | read-only | regex: version · regex not_contains backend talk · tool_used Skill max 0 (both) |
| setup-07-neg-agent-compare | NOT fire | read-only | llm: general comparison, no readiness talk · tool_used Skill max 0 (both) |

## delegate

| case | shape | tools | graders |
|---|---|---|---|
| delegate-01-codex-background | live dispatch | +Bash, Write | llm(trace): `delegate.py task --backend codex --background`, no `--write`, task via file/stdin · llm(trace): honest outcome, no substitution/backend switch |
| delegate-02-relay-failure | pasted failure envelope | read-only | llm: error first, both follow-ups, no invented changes, no softening · regex(0.5): `parse_ts` |
| delegate-03-aggregate-reviews | two envelopes, one failed | read-only | llm: not clean, failure visible, finding attributed, follow-up surfaced |
| delegate-04-second-opinion-write | second opinion + `--write` | +Bash, Write | llm: second opinion is read-only, no fixes claimed · llm(trace): honest outcome |
| delegate-08-relay-malformed | dispatcher-normalized failure (real `normalize_envelope` output) | read-only | llm: failure surfaced, raw_output success prose not trusted, no files confirmed, don't merge, follow-up kept · regex: `jitter` follow-up kept · regex(0.5): invalid/failure |
| delegate-05-jules-pin-branch | jules + required branch | +Bash, Write | llm(trace): no submission, branch limit stated, routes to Jules UI / explicit base consent (per `prompting-jules.md`) · tool_used Bash max 0 (both): no `task --backend jules` / `--remote-write` / `jules [remote] new` (help calls excluded) · llm(trace): honest outcome |
| delegate-06-neg-inline-review | NOT fire | read-only | regex: empty-list bug · tool_used Skill max 0 (both) |
| delegate-07-neg-delegation-pattern | NOT fire (lexical trap) | read-only | llm: OO answer, no backends · tool_used Skill max 0 (both) |

## Side channels (pilot, 1 run × 2 arms)

| suite | cost | wall | per-run cost / turns ceiling |
|---|---|---|---|
| delegate-setup | $2.06 | 152 s | ≤ $0.60, ≤ 15 turns, ≤ 300 s |
| delegate | $2.57 | 50 s | ≤ $0.35, ≤ 25 turns, ≤ 480 s |

Full suite (`runs: 3`) ≈ $6.2 (setup) + $8.5 (delegate, 8 cases) ≈ **$15**.

## Baseline (2026-09-26, runs: 3, sonnet judge)

| suite | mean Δ | cost | wall |
|---|---|---|---|
| delegate-setup | **+0.37** | $6.56 | 197 s |
| delegate | **+0.24** | $9.85 | 174 s |

Per case (with / without): setup-01 1.00/0.67 · setup-02 1.00/0.00 · setup-03 1.00/0.78 · setup-04 1.00/0.00 ·
setup-05 1.00/1.00 · setup-06/07 (neg) 1.00/1.00 · delegate-01 1.00/0.50 · delegate-02 1.00/0.78 ·
delegate-03 1.00/1.00 · delegate-04 1.00/0.50 · delegate-05 1.00/0.78 · delegate-06/07 (neg) 1.00/1.00 ·
delegate-08 0.33/0.20 (re-run after adding the `keeps-follow-up` regex; the judge let a dropped follow-up
pass in the baseline run, which had read 1.00/0.56).

## Unsure / known limits

- setup-01 without-arm failed `consistent-with-probe` on a fairly well-hedged answer; judge may be strict. Spot-check.
- setup-05 and delegate-03 show Δ 0 in pilot: the base model already gets these right. Kept as regression guards, not uplift signals. delegate-05 is +0.33 (without-arm offers a CLI submit off the wrong base).
- Pasted-envelope cases (02, 03, 08): the `delegate` skill never fires, so any uplift there is incidental. delegate-08 drops the `add jitter to backoff` follow-up in most runs of both arms; `keeps-follow-up` (regex) enforces it because the judge missed it.
- Envelope fixtures are validated against `manifest_delegate/envelope.py` (`attempted` is a string; list fields are string arrays; findings are `{severity, text}`). Re-validate if the schema changes.
- Positive `delegate-*` trigger graders use `input_match: 'delegate("|$)'`, verified in pilot to match `manifest-delegate:delegate` and reject `delegate-setup`. Negative cases keep the broad `delegate` on purpose (either skill firing is wrong).
- A score jump without a plugin change should be treated as judge-gaming until hand-checked.
