# manifest-code-quality evals

Ablation suites for all 24 manifest-code-quality skills: 167 cases, one
directory per skill (`<skill>/<skill>--NN-<slug>/`). The headline number is
Δ — the with-plugin score minus the without-plugin score.

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
