# Model Selection Policy

> Which model runs a session, a sub-agent, and a turn — and why. Every number
> here is measured, not estimated; the derivation and the reproduce commands are
> in [docs/baselines/2026-07-25-credit-baseline.md](baselines/2026-07-25-credit-baseline.md).

**Last updated**: 2026-07-25
**Measured over**: 47,185 request-deduped API calls, $6,141.64 total spend

---

## The three levers, ranked

| Lever | Scope | Status | Value |
|---|---|---|---|
| Sub-agent model | per dispatch | **Adopted** — enforced | $845 |
| Session start model | per session | **Adopted** — ask-gated | ~$766 |
| Per-turn model routing | per turn | **Rejected on evidence** | **−$1,499** |

---

## 1. Sub-agents default to Sonnet

**Rule.** Pin an explicit model on every dispatch. Sonnet unless the task needs
more; Haiku for purely mechanical fan-out; Opus only for genuinely hard
reasoning (adversarial verification of security or correctness findings).

Never inherit the parent session's model by accident — that bills main-loop
rates for fan-out work.

**Why it is safe.** Sub-agents carry their own context and their own prompt
cache, so changing a sub-agent's model cannot invalidate the main loop's cache
prefix. This is the *only* place a model switch is cache-neutral.

**Measured.** 63.2% of sub-agent traffic already ran Sonnet. The premium
remainder cost $845 more than it needed to:

| Sub-agent traffic | Requests | Cost | On Sonnet 5 | Saving |
|---|---:|---:|---:|---:|
| Opus 4.8 | 4,534 | $503.74 | $302.24 | $201.50 |
| Fable 5 | 4,531 | $919.32 | $275.80 | **$643.52** |

Fable is the bigger half despite an almost identical request count — it bills
$10/$50 per MTok, 2x Opus. Start there.

**Enforcement — and what it does *not* prove.**

- `subagent_model` is required on every skill with `subagents: always|conditional`
  in `configs/claude/config/command_config.yml`, and the skill's
  `## Sub-agent dispatch` section must state the same model.
- Gated by `tests/bats/subagent_policy.bats` (checks T7/T8), enumerated from the
  disposition — a new dispatching skill fails until it pins a model, with no
  name list to maintain.
- **T7/T8 verify the documents, not the dispatch.** They prove
  `command_config.yml` says Sonnet; they cannot observe which model a dispatch
  actually ran on. Ad-hoc dispatches outside a skill (Explore, general-purpose,
  one-off fan-out) are not reachable by that gate at all, so the default is also
  stated in the Token Economy section of the always-loaded orchestration guides.

**Measured check (the only one that confirms behaviour).** The attribution
report splits by class *and* model, so one command reads the lever directly:

```bash
configs/claude/scripts/opus_attribution_report.py \
    --since 2026-07-25T23:58:27Z --models all | grep '^subagent'
```

**It has not yet read clean.** In the 3h58m between the baseline and the change
point — the session that landed this very policy — 283 sub-agent requests ran on
Opus 5 ($50.79), against zero Opus 5 traffic of any kind before it. The rule
above permits Opus for adversarial verification, so a non-zero cell is not by
itself a violation; what it establishes is that the cell is non-zero and the
report cannot say whether those dispatches were the permitted exception or
inherited the session model. Until a post-change interval reads premium
sub-agent cells at (or near) zero, treat lever 1 as **declared, not landed**.

Closing that last ambiguity needs the dispatch to record its own intent —
transcripts carry the model a sub-agent ran on, not the reason it was chosen.
That is a separate change; do not read the matrix as proving intent.

Full dispatch rules: [configs/claude/references/sub-agent-dispatch.md](../configs/claude/references/sub-agent-dispatch.md).

---

## 2. Sessions start on Opus; Fable is asked for, never assumed

**Rule.** Opus is the default start model. Fable 5 is for work that is
genuinely **long-horizon** — hours of autonomous iteration, not merely hard.

A skill that wants Fable **asks the user to switch and waits for the answer.**
It does not assume Fable is active, and it does not silently proceed on the
default. The switch trades ~2x per-token cost against capability; that is the
user's call, and a skill that assumes either way makes it silently.

**Measured.** Fable 5 was 39.9% of all spend on 18.1% of requests — the single
most expensive line, slightly exceeding the entire Opus family. Of that,
**$1,532.15 was main-loop traffic** (3,921 requests): a session-level model
choice, not a routing one.

| Option | Cost | Decision |
|---|---:|---|
| Leave as-is — Fable default for hard work | $1,532.15 | rejected |
| **Fable only for genuinely long-horizon work** | **~$766** | **adopted 2026-07-25** |
| Opus default, Fable opt-in per session | ~$383 | rejected: the failure mode is silent |

The third option saves most but fails silently — a hard session you did not
flag in advance runs under-powered, and you only find out from worse output.
The adopted option keeps Fable where its advantage is real and asks before
spending it.

### Where a model can be specified (verified 2026-07-25)

The session model is a settings key, not just a `/model` habit, and it cascades.
Measured on Claude Code 2.1.220 with three headless runs in one throwaway
directory, varying exactly one input per run:

| Run | Config present | Model that answered |
|---|---|---|
| A | user default only | `claude-opus-5[1m]` |
| B | `+ .claude/settings.json` → `haiku` | `claude-haiku-4-5` |
| C | `+ .claude/settings.local.json` → `sonnet` | `claude-sonnet-5` |

**Precedence: local > project > user**, and `"model"` is honoured at every
layer. That gives four specification points, narrowest first:

| Scope | Mechanism | Use for |
|---|---|---|
| Per-dispatch | `subagent_model` (T7/T8) | fan-out work; cache-neutral, no asking |
| Per-skill | `session_model` + ask-gate (T9) | a skill needing a *different* tier than the session |
| Per-project | `.claude/settings.json` `"model"` (committed) / `.local.json` (personal) | a repo whose work is consistently routine or consistently hard |
| Global | `~/.claude/settings.json` `"model"` | the fallback when nothing narrower applies |

**Prefer the narrowest scope that fits.** A per-project default beats flipping
the global one: it puts the cheaper tier where the work is routine without
relying on remembering to switch, and it leaves the hard repos untouched. It is
also the only scope that survives the thing a global default cannot — you
forgetting.

Caveat: `.claude/settings.json` is committed, so a project-scope model is a
statement about the *repo*, not about who is working in it. Anything personal
belongs in `.local.json`.

> Not yet decided: whether any project should default below Opus. See
> §"Not yet harvested" — `reasoning` is the class that would move, and the
> decision is deliberately held until lever 1 reads clean.

**Enforcement — and what it does *not* prove.** `session_model` +
`session_model_rationale` in `command_config.yml`; skills declaring
`session_model: fable` must carry a `## Session model` section instructing them
to ask. Gated by `tests/bats/subagent_policy.bats` (check T9). Currently
declared by `issue-dev-auto`, `lifecycle-run`, `spec-implement-loop`.

T9 has the same limit as T7/T8, one layer up: **it proves the SKILL.md contains
the instruction to ask, not that any session actually stopped and asked.** It is
a documentation check, and naming it one here is deliberate — lever 1 was
believed landed on exactly this kind of evidence until the class × model matrix
contradicted it. There is no transcript signal for "a skill asked and waited",
so unlike lever 1 this one has no measured counterpart today. Until it does,
lever 2's status is *declared*, and the honest confidence in it is lower than
lever 1's, not higher.

---

## 3. Do not route individual turns to a cheaper model

**This one is rejected on evidence, not preference.** It is the intuitive
optimisation and it loses money. Point people here rather than re-deriving it.

Prompt caches are model-scoped. Main-loop turns average **149,975 cache-read
tokens**, so switching model mid-conversation invalidates the prefix and forces
the next premium turn to pay a full cache **write**.

Measured on the most attractive candidate class — `tool_mechanical` turns,
10.3% of Opus requests, median output 150 tokens:

```text
saving from the downgrade      1,737 reqs   ->    $129.41
cache re-write penalty     260,507,437 tok x $6.25/MTok  =  $1,628.17
                                                    net  =  -$1,498.76
```

Net **−$1,499**, a ~12x loss. The same reasoning rejects per-turn routing of
`tool_edit`, `mixed`, and `text_response`.

**53.4% of all Opus spend is cache reads** ($1,385 of $2,595). Any proposal that
disturbs the cache prefix has to clear that bar before its savings count.

---

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

Levers 1 and 2 landed together, which normally forfeits attribution. They stay
separable here because the attribution report splits by **class** and by
**model**: lever 1 moves the `subagent` class off Opus/Fable, lever 2 moves
main-loop Fable requests off Fable. Read them from different rows, and do not
land a third lever until both have been read.

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

## Related

- [docs/baselines/2026-07-25-credit-baseline.md](baselines/2026-07-25-credit-baseline.md)
  — the measurement, with reproduce commands
- [configs/claude/references/sub-agent-dispatch.md](../configs/claude/references/sub-agent-dispatch.md)
  — dispatch mechanism selection and thresholds
- [configs/claude/references/cddl-role-models.md](../configs/claude/references/cddl-role-models.md)
  — per-role tier aliases for CDDL charters
