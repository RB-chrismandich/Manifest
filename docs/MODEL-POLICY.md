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
  one-off fan-out) are not reachable by that gate at all.
- **The mechanism is a hook, not a sentence.** A prose default was already
  loaded in every session — including every session that inherited; measured pin
  compliance under prose alone was 7.3%. `subagent_model_default.py` runs as a
  `PreToolUse` hook on the `Agent` tool and returns
  `hookSpecificOutput.updatedInput` with `model: sonnet` when, and only when,
  the dispatch named none. It deliberately does not touch an explicit `model`
  (layer 1), an agent whose frontmatter sets `model:` (layer 2 — a call-site
  model outranks frontmatter, so injecting would silently revoke the Opus
  permission this policy grants), or `fork` (which ignores `model` by design, so
  injecting would record a requested model that never served and corrupt the
  audit).
- **Deployment caveat — hooks must land in `settings.json`.** Measured
  2026-07-26 on Claude Code 2.1.220 by controlled A/B (same hook, same absolute
  command, only the file differing): a hook in `~/.claude/settings.local.json`
  fired **zero** times, the same hook in `~/.claude/settings.json` fired on
  every dispatch. An absolute path in `settings.local.json` also never fired, so
  tilde expansion is not the cause — `settings.local.json` is a *project*-scope
  file and a copy at `~/.claude/` is inert. This hook is therefore shipped in
  `configs/claude/settings.hooks.json` and merged into `~/.claude/settings.json`
  by `merge_claude_runtime_hooks`. Every other hook Manifest ships is still
  registered in `configs/claude/settings.local.json` and inherits the same
  defect; see the open item at the end of this section.

**Measured check (the only one that confirms behaviour).** The attribution
report splits by class *and* model, so one command reads the lever directly:

```bash
# --since is the DEPLOY point, not the commit point: until bootstrap.sh copied
# the guide into ~/.claude, every session still loaded the old policy.
configs/claude/scripts/opus_attribution_report.py \
    --since 2026-07-26T02:40:18Z --models all | grep '^subagent'
```

**Deployed 2026-07-26T02:40:18Z; measurement starts there.** Earlier readings
of this query looked alarming — 283 sub-agent requests on Opus 5, then 555, then
943 — and every one of them was measured against a `--since` that predated the
deploy. The policy existed only in the repo until `./bootstrap.sh` copied it into
`~/.claude`, so that traffic ran under the *old* guide. It is the comparison
baseline, not evidence of failure.

The rule above permits Opus for adversarial verification, so a non-zero premium
cell is not by itself a violation.

**Correction (2026-07-26): a permitted exception and an inherited default ARE
distinguishable.** This document previously said they were not, and that the
dispatch would have to "record its own intent" before they could be told apart.
It already does. Every dispatch writes an `agent-<id>.meta.json` sidecar beside
its transcript: `meta.model` records the model *requested*, the transcript
records the model that *served*. So

| requested | served | reading |
|---|---|---|
| `opus` | claude-opus-5 | permitted exception — deliberate |
| frontmatter `model:` | claude-opus-5 | permitted exception — deliberate (layer 2; not in `meta.model`, resolved from the agent definition) |
| *absent* | claude-opus-5 | **inherited default — a violation** |

Measured over the full corpus: only 6 dispatches ever explicitly requested
`opus`. Essentially all premium sub-agent spend was inherited, not chosen. The
claim that intent was unrecoverable was wrong, and it mattered — it is the
reason this lever sat on a documentation check while 11,000 inherited premium
requests accumulated under a policy that was already written down.

**Behavioural gate (item 2 of this change).** The sidecars make the check
executable, so it is no longer a matter of reading a matrix:

```bash
# Defaults --since to deployed_at in ~/.claude/config/deploy_stamp.
configs/claude/scripts/subagent_breakdown.py --audit
```

Exit 1 with a per-dispatch list on any inherited premium dispatch; exit 0 when
clean. It shares `declared_model()` with the hook, so the audit cannot flag the
frontmatter-pinned agents the hook is required to leave alone.

**Lever-1 verdict: split — landed inside Manifest, not globally.** The
post-deploy read is clean for Manifest-repo sessions (sub-agents 100% Sonnet,
zero Opus). It is *not* clean everywhere: the post-deploy Opus-5 sub-agent
traffic came from sessions in repos Manifest's configuration never reaches. The
lever is landed where Manifest's config applies and undetermined outside it —
recorded as a split verdict rather than a single pass/fail, because averaging
the two would hide both facts.

**Two channels, one of them still open.** The `Agent` PreToolUse hook
(`configs/claude/scripts/subagent_model_default.py`) fills in an omitted model
on Agent-tool dispatches. Workflow-tool agents (`agent()` inside a Workflow
script) do **not** pass through it — they are governed by the script's own
`model` option or `CLAUDE_CODE_SUBAGENT_MODEL`. That is the largest single
premium block measured ($919.32, workflow-subagent x Fable 5). `--audit` scopes
its exit code with `--channel` and always reports the other channel's count, so
a clean agent-tool result can never be read as "sub-agent spend is under
control".

**Resolved — every Claude hook now ships in `settings.hooks.json`.** The A/B
above was run for one hook; a second A/B on a different event
(`PostToolUse:Write`, same probe, zero fires from `settings.local.json` and a
fire from `settings.json`) established the defect as a property of the **file**,
not of the hook or the event. So `guidance_hint.py`, `version_pin_hook.sh`,
`spec_review.sh`, `lint_on_edit_hook.sh` and the
`SessionStart`/`UserPromptSubmit` entries had all been inert on every deployed
machine, and all of them were migrated.

Because none had ever executed in production, each was probed with a
representative payload before being activated: all exit 0 (non-blocking),
`guidance_hint`/`version_pin`/`spec_review` stay silent on ordinary edits,
`lint_on_edit` emits advisory output only on a genuine lint error, and all three
`PostToolUse` hooks chained on a single edit cost ~240ms. Gated by
`tests/bats/deploy_runtime_hooks.bats`, which fails if a hook is ever added back
to the inert file.

**Resolved — but each key needed a *different* destination.** The rest of
`settings.local.json` (`permissions`, `mcpServers`,
`skillListingBudgetFraction`) was equally unread. The obvious fix — move it all
next to the hooks in `settings.json` — is **wrong for `mcpServers`**: probing
that key into each file showed `settings.json` does not read it either, so the
migration would have looked complete and changed nothing.

| Key | Destination that works | How it gets there |
|---|---|---|
| `hooks`, `permissions`, scalar defaults | `~/.claude/settings.json` | `settings.runtime.json` → `merge_claude_runtime_settings` |
| `mcpServers` | **`~/.claude.json` only** | `config/mcp_user_servers.json` → `claude mcp add --scope user` |

`settings.local.json` is now an empty stub kept only as a path other code still
references. The MCP step also rescues any server a user had added to that inert
file. It is guarded to no-op when `TARGET_DIR` is outside `$HOME`, because it is
the one deploy step that writes outside the target tree and would otherwise let
a sandboxed test edit a developer's real config.

**Caveat, stated rather than glossed:** permission *enforcement* was not
successfully verified. The obvious probe — a rule present vs absent under
`claude -p` — is useless, because headless mode ran the command with **no rule
anywhere**, so the control could not fail. The permissions destination is
therefore inferred from the file-level result, not measured. The `mcpServers`
and `hooks` destinations *were* measured directly.

Full dispatch rules: [configs/claude/references/sub-agent-dispatch.md](../configs/claude/references/sub-agent-dispatch.md).

---

## 2. Sessions start on Opus (1M context); there is no tier above it

**Rule.** Opus is the default start model and, since the Fable tier was retired
on **2026-08-17**, also the top tier. Both `sonnet` and `opus` now pin their
1M-context variants (`claude-sonnet-5[1m]`, `claude-opus-5[1m]`).

Because no costlier Claude tier remains, the ask-before-switching rule this
section used to carry has no referent and was removed along with the tier: the
three skills that declared `session_model: fable` now run on the default, and
`tests/bats/subagent_policy.bats` no longer enforces a switch prompt.

The history below is kept as the measured record that motivated the original
split — it describes spend under the retired tier, not current behaviour.

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

## Related

- [docs/baselines/2026-07-25-credit-baseline.md](baselines/2026-07-25-credit-baseline.md)
  — the measurement, with reproduce commands
- [configs/claude/references/sub-agent-dispatch.md](../configs/claude/references/sub-agent-dispatch.md)
  — dispatch mechanism selection and thresholds
- [configs/claude/references/cddl-role-models.md](../configs/claude/references/cddl-role-models.md)
  — per-role tier aliases for CDDL charters

## Cross-Harness Skill Model Policy

Skills may declare portable, ordered tiers without embedding provider model IDs:

```yaml
models:
  codex: [advanced, flash, auto]
  gemini: [pro, flash, auto]
  antigravity: [advanced, flash, auto]
  cursor: [advanced, flash, auto]
model_fallback:
  mode: confirm
```

`agy` is accepted on input and normalized to `antigravity`. Chains contain one
to four unique tiers; `auto`, when supported, is final. Concrete IDs remain in
`configs/claude/config/parallel_agent.yml`.

Precedence is explicit CLI/session choice, skill frontmatter, then the global
`confirm` default. `--model` replaces the chain unless `--model-chain` supplies
subsequent fallbacks. Authentication, configuration, safety, malformed output,
task errors, unknown evidence, and truncated evidence never trigger fallback.
Model unavailability, rate limits, transient provider failures, capacity,
quota, and billing failures are eligible.

Non-interactive and JSON execution never prompts. Confirm mode returns a
recovery command; auto mode advances. Provider evidence is retained only while
classifying a bounded attempt. Durable summaries are allowlisted, redacted,
and size bounded; task text is never stored in job state.

Confirm-mode recovery is versioned and identity-bound. Approval requires the
printed job version, `recovery_id`, and a freshly resubmitted task through stdin
or `--task-file`. Reject/cancel validates only the job version and recovery
identity, then terminates as `fallback_rejected` without resolving a backend or
reading task/payload input. The background ownership protocol is durable:
`spawned -> worker_owned -> backend_started -> terminal`; an unprovable loss at
or after ownership becomes non-resumable `dispatch_unknown`, never an automatic
retry.

Second-opinion dispatch is also a fresh attempt. It accepts only bounded
`title`/`detail`/`severity` findings tied to the source job's current attempt,
plus freshly resubmitted task text. It excludes prior prompt summaries, raw
provider output/errors, session references, full envelopes, and attempt history.

Use an explicit model-aware entry point when policy must apply:

```bash
printf '%s' 'the task' | manifest skill-run path/to/SKILL.md --harness codex
```

Ordinary native skill invocation retains the harness default.
