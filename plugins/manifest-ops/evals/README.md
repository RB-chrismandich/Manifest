# manifest-ops evals

Ablation suite for all 12 manifest-ops skills: 84 cases, 7 per skill
(5 should-fire, 2 should-not-fire). The headline number is Δ — the
with-plugin score minus the without-plugin score.

## Run

From `plugins/manifest-ops/`:

```bash
claude plugin eval . --ablation with-without --scaffold \
  --judge-model opus --allow-tools Write Edit Bash
```

Every flag is required for a meaningful result:

| Flag | Why |
|------|-----|
| `--scaffold` | 15 cases (`cis-*`, `cdd-0*`, `crf-0*`) build their repo in `scaffold.sh`. Without it their prompts describe a checkout that does not exist. |
| `--allow-tools Write Edit Bash` | File-writing cases (`cis-*`, `dcc-0[124]`, `vp-0[1-4]`) cannot create the graded files otherwise. |
| `--judge-model opus` | Cases run on `sonnet`; the judge must be a different, larger model. |

Add `--no-publish` to keep the report local. One full run (3 runs × 2 arms)
cost about $75 in the 2026-09 pilot.

## Layout

Each case directory holds `prompt.md` (frontmatter + prompt) and `graders/`.
Scaffolded cases add `case.yaml` pointing at `scaffold.sh`, which runs as the
operator before the agent starts; files it writes count as pre-existing, not
agent-created. `cis-02-pnpm-next/fixtures/pnpm-lock.yaml` is a real lockfile
generated from that case's `package.json`.

Case prefixes map to skills: `cwo` cache-warm-oob, `cdd` ci-diagnose-drift,
`crf` ci-reproduce-failure, `cis` ci-setup, `cds` config-debug-substitution,
`cvn` config-validate-native, `ddd` deploy-diagnose-drift, `drc`
deploy-retire-component, `dcc` docker-compose-commandments, `dpi`
docker-probe-internal, `pds` process-diagnose-stall, `vp` version-pin.
