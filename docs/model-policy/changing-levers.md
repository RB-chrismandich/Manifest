# Lever 4 — Changing a Lever

> How to move one lever at a time, and what is not yet measured.

## 4. Changing a lever: one at a time

Batched changes produce an unattributable delta, which defeats the reason the
baseline exists. For each lever:

1. **Snapshot the change point.** Run the reproduce commands with a fresh
   `--until` at the moment the change lands:

   ```bash
   D=$(date -u +%Y-%m-%dT%H:%M:%SZ)
   configs/claude/scripts/opus_attribution_report.py --until "$D" \
       --json docs/baselines/$(date -u +%F)-opus-attribution.json
   # The class x model matrix — the artifact a lever is verified against
   configs/claude/scripts/opus_attribution_report.py --until "$D" --models all \
       --json docs/baselines/$(date -u +%F)-model-class-matrix.json
   configs/claude/scripts/token_cost_report.py  --until "$D"
   configs/claude/scripts/skill_usage_report.py --until "$D"
   ```

2. **Land exactly one lever.** Nothing else in the same commit.

3. **Let traffic accumulate.** A snapshot taken immediately after a change
   measures the *old* behaviour — the corpus has not grown yet. Wait for a
   representative amount of work (rule of thumb: enough sessions that the
   affected class has ≥500 requests in the new interval).

4. **Diff the interval, not the totals.** Compare the new snapshot against the
   previous change point. Cumulative totals blend pre- and post-change traffic
   and will understate the effect.

### Change log

| Date | Lever | Snapshot | Measured effect |
|---|---|---|---|
| 2026-07-25T20:00:00Z | Baseline | `docs/baselines/2026-07-25-opus-attribution.json` | — |
| 2026-07-25T23:58:27Z | Levers 1 + 2 land | `docs/baselines/2026-07-25-changepoint-model-policy-opus-attribution.json` (Opus) · `docs/baselines/2026-07-25-changepoint-model-class-matrix.json` (all models) | pending — needs accumulated traffic |
| 2026-07-26T02:40:18Z | **Deployed to `~/.claude`** — the point measurement actually starts from | `docs/baselines/2026-07-26-postdeploy-model-class-matrix.json` | pending — measure from HERE, not from the commit |

Levers 1 and 2 landed together, which normally forfeits attribution. They stay
separable here because the attribution report splits by **class** and by
**model**: lever 1 moves the `subagent` class off Opus/Fable, lever 2 moves
main-loop Fable requests off Fable. Read them from different rows, and do not
land a third lever until both have been read.

**Measure from the deploy row, not the commit row.** Committing changed nothing
observable: until `./bootstrap.sh` copied the guide and `command_config.yml`
into `~/.claude`, every session still loaded the old policy. The interval
between the commit and the deploy is pre-change traffic wearing a post-change
date, and reading it was what made lever 1 look broken. At the deploy point the
cumulative `subagent x claude-opus-5` cell stood at 943 requests / $156.68 — all
of it inherited under the old guide, and the number a post-deploy interval must
be compared against rather than added to.

Change-point deltas from the baseline 4h earlier (measurement noise, not
effect): 48,347 requests (+1,162), Opus 17,784 (+911), `subagent` class 4,817
(+283). Fable 5 was flat at 8,452 across the interval, so its post-change
figures start clean.

---

## Not yet harvested

**Pre-pinned agent definitions.** `configs/claude/agents/` (pilotfish) and
`configs/claude/agents-devpanel/` already pin a model, so lever 1's gate does
not touch them — but 9 of 15 pin `opus`:

| Pinned `opus` | Pinned `sonnet` | Pinned `haiku` |
|---|---|---|
| dependency-guardian, executor, security-executor, verifier, chaos-engineer, debugger, developer, spec-guard, tester | mech-executor, performance-auditor | Explore, compatibility-translator, context-chronicler, scout |

Several are plausible Sonnet candidates (tester, debugger, spec-guard). That is
a capability trade on each role's charter, so it is a separate lever — audit it
on its own, and re-measure between.

**Session-level `reasoning` traffic.** `reasoning` is 49.4% of Opus requests and
60.3% of Opus spend — larger than every other class combined. It cannot be
routed per-turn (see §3), so the only lever is starting whole sessions on a
cheaper model when the work does not need a premium one. That is a scoping
change, not a routing change.

> **Read the label carefully before acting on it.** `classify()` returns
> `reasoning` for any non-sidechain request whose response carried a `thinking`
> block. Measured over the 12,339 non-sidechain Opus requests in the baseline
> window: of the 9,069 that are neither tool-only nor text-only, **8,329 (91.8%)
> carry a thinking block**. So `reasoning` is very nearly a restatement of "not
> tool-only and not text-only" — the thinking block itself adds ~8% of
> discrimination, and with `effortLevel` configured it largely reflects that
> thinking is enabled.
>
> It is *not* content-free, though: median output separates cleanly —
> `reasoning` 907 tokens vs `mixed_no_thinking` 336 vs `tool_only` 198. The
> class reliably identifies **long-output, non-mechanical turns**, which is why
> it dominates spend. What it does **not** establish is that those turns were
> *hard*, or that they needed a premium model. Treat "60.3% of spend is
> reasoning" as a statement about where output tokens go — a sound reason to
> target the class — and not as evidence that the work justified the tier. Any
> proposal to move this class needs a difficulty signal the classifier does not
> currently provide.

---

---

[← Model Policy](../MODEL-POLICY.md)
