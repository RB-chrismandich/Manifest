# Credit Baseline — 2026-07-25

> Re-derivable measurement baseline for credit-reduction work. Every number
> below is reproduced by re-running the scripts in the **Reproduce** section.

**Scan window**: all transcripts under `~/.claude/projects` up to
`2026-07-25T20:00:00Z` (the cutoff makes the snapshot reproducible against an
append-only corpus).

**Machine-readable snapshot**: [`2026-07-25-opus-attribution.json`](2026-07-25-opus-attribution.json)

---

## The measurement correction that gates everything

The prior baseline counted **JSONL lines**, not API requests, and was inflated
**2.24x**.

Claude Code writes each content block of one API response as its own
`assistant` line, and every sibling line repeats a `usage` object. Summing
per-line multiply-counts a single request:

| Field | Behaviour across sibling lines | Correct reducer |
|---|---|---|
| `input_tokens` | identical (per-request constant) | first |
| `cache_read_input_tokens` | identical | first |
| `cache_creation_input_tokens` | identical | first |
| `output_tokens` | **cumulative** — last block carries the running total | **max** |

Evidence (one request, two lines):

```text
requestId: req_011Cd3ZMY9DdNP1XbcYqnC3p
   blocks=['thinking']   in=2 out=5   cr=40264 cc=8921
   blocks=['tool_use']   in=2 out=123 cr=40264 cc=8921
```

`requestId` is present on 100% of usage-bearing lines, so dedup is always possible.

| Metric | Line-counted (wrong) | Request-deduped (correct) |
|---|---:|---:|
| Total API calls | 105,728 | **47,185** |
| Opus API calls | 41,527 | **16,873** |
| Output tokens (all models) | ~40.4M naive-summed 3x | 40,397,441 |

The goal's "41,330 Opus calls" is a **line count**. The real figure is
**16,873 Opus API requests**.

---

## Opus attribution (16,873 requests, 98.04% classified)

Weighted input units use Anthropic's multipliers: fresh input x1.0,
cache read x0.1, cache write x1.25.

| Class | Requests | % | Output tokens | Weighted input | Median out | p90 out |
|---|---:|---:|---:|---:|---:|---:|
| reasoning | 8,329 | 49.36 | 12,362,581 | 251,156,252 | 907 | 3,310 |
| subagent | 4,534 | 26.87 | 4,617,233 | 77,661,613 | 358 | 2,757 |
| tool_mechanical | 1,737 | 10.29 | 380,835 | 30,447,811 | 150 | 349 |
| tool_edit | 883 | 5.23 | 569,552 | 25,753,978 | 442 | 1,130 |
| mixed | 740 | 4.39 | 445,095 | 23,503,120 | 334 | 1,144 |
| other | 331 | 1.96 | 106,370 | 9,696,018 | 80 | 1,152 |
| text_response | 319 | 1.89 | 108,672 | 7,796,879 | 221 | 845 |

Classified into a non-`other` class: **16,542 / 16,873 = 98.04%** (target >=90%).

### Cost derivation

List price per MTok: Opus `$5` in / `$25` out; Sonnet 5 `$3`/`$15`;
Haiku 4.5 `$1`/`$5`. Cache read = 0.1x input rate, cache write = 1.25x.

| Class | Opus cost | on Sonnet 5 | on Haiku 4.5 | % of Opus spend |
|---|---:|---:|---:|---:|
| reasoning | $1,564.85 | $938.91 | $312.97 | 60.3% |
| subagent | $503.74 | $302.24 | $100.75 | 19.4% |
| tool_mechanical | $161.76 | $97.06 | $32.35 | 6.2% |
| tool_edit | $143.01 | $85.81 | $28.60 | 5.5% |
| mixed | $128.64 | $77.19 | $25.73 | 5.0% |
| other | $51.14 | $30.68 | $10.23 | 2.0% |
| text_response | $41.70 | $25.02 | $8.34 | 1.6% |
| **Total** | **$2,594.84** | | | 100% |

**53.4% of all Opus spend is cache reads** (2.78B tokens x $0.50/MTok = $1,385).
That single fact determines which routing levers are viable.

> **Pricing caveat: the corpus cannot see the context tier.** A session running
> `opus[1m]` records its model in the transcript as plain `claude-opus-5` — the
> `[1m]` suffix exists only in `settings.json` and in the headless `modelUsage`
> key, never in the JSONL these reports read. Every figure here therefore prices
> long-context requests at standard rates. Exposure looks bounded: main-loop
> turns average ~150K cache-read tokens and a sampled `[1m]` session averaged
> ~18K per request, both under the usual 200K long-context threshold — so if any
> premium applies it should apply rarely. But it is an unmodelled assumption in a
> document that otherwise claims list-price accuracy, and it can only shift
> figures **upward**. Separately, several still-active models
> (`claude-opus-4-5`, `claude-opus-4-1`, `claude-sonnet-4-5`, `claude-sonnet-4-0`)
> are absent from `model_pricing.py` by design — they report as `unpriced` and
> are excluded from totals rather than guessed at, so a longer scan window will
> show holes, not wrong numbers.

---

## Routing proposal

### Rejected: per-turn downgrade of mechanical tool calls

The intuitive lever — route `tool_mechanical` turns (10.3% of requests, median
output 150 tokens) to Haiku — is **net-negative by ~12x**.

Caches are model-scoped. These turns are interleaved *inside* main-loop
conversations, averaging **149,975 cache-read tokens per request**. Switching
model mid-conversation invalidates the prefix, so the next Opus turn pays a
full cache **write**:

```text
saving from the downgrade      1,737 reqs  ->    $129.41
cache re-write penalty     260,507,437 tok x $6.25/MTok  =  $1,628.17
                                                    net  =  -$1,498.76
```

Do not implement this. The same reasoning rejects per-turn routing of
`tool_edit`, `mixed`, and `text_response`.

### Adopted 2026-07-25: route remaining premium subagents to Sonnet 5

> **Declared, not yet confirmed in behaviour.** `subagent_model` is now required
> on every dispatching skill (`command_config.yml`), the dispatch prose must
> state the same model, and both are gated by `tests/bats/subagent_policy.bats`
> (T7/T8) — but those gates read the config, not the traffic. The measured check
> is the class x model matrix (see [Verifying a landed lever](#verifying-a-landed-lever));
> at the change point it still showed 283 `subagent` requests on Opus 5, so
> treat the saving below as projected until a post-change interval reads clean.
> Policy: [docs/MODEL-POLICY.md](../MODEL-POLICY.md#1-sub-agents-default-to-sonnet).

Subagents carry their **own context and own cache**, so routing them changes
nothing about the main loop's prefix. This is the only class where a model
switch is cache-neutral.

The lever is already **partly harvested** — 63.2% of subagent traffic runs on
Sonnet 5 today. What remains is the premium-model share:

| Subagent traffic | Requests | % of subagent | Current cost | On Sonnet 5 | Saving |
|---|---:|---:|---:|---:|---:|
| Sonnet 5 (already routed) | 18,109 | 63.2% | — | — | — |
| **Opus 4.8** | 4,534 | 15.8% | $503.74 | $302.24 | **$201.50** |
| **Fable 5** | 4,531 | 15.8% | $919.32 | $275.80 | **$643.52** |
| Haiku 4.5 | 768 | 2.7% | — | — | — |
| Sonnet 4.6 | 393 | 1.4% | — | — | — |

**Projected saving: $845.02 — 13.8% of total spend across all models**, at zero
cache-invalidation risk. Routing to Haiku 4.5 instead yields $1,230.38 where the
subagent's task is mechanical.

Note the Fable 5 subagent lever is **3.2x larger** than the Opus one despite an
almost identical request count: Fable 5 bills $10/$50 per MTok, 2x Opus.

### Scope correction: the goal's Opus-only framing understates the target

The goal scoped this analysis to Opus. Measured across all models, Opus is not
the dominant line:

| Model | Requests | Cost | % of total |
|---|---:|---:|---:|
| claude-fable-5 | 8,452 | $2,451.47 | **39.9%** |
| claude-opus-4-8 | 14,150 | $2,379.20 | 38.7% |
| claude-sonnet-5 | 19,918 | $1,055.29 | 17.2% |
| claude-opus-4-7 | 2,723 | $215.64 | 3.5% |
| claude-sonnet-4-6 | 792 | $32.61 | 0.5% |
| claude-haiku-4-5 | 774 | $7.43 | 0.1% |
| **Total** | **46,809** | **$6,141.64** | 100% |

**Fable 5 is 39.9% of spend on 18.1% of requests** — the single most expensive
line, slightly exceeding the entire Opus family. Any credit work that optimises
Opus while leaving Fable 5 routing untouched is addressing the smaller half of
the problem. The largest single uncosted item is Fable 5 **main-loop** traffic:
3,921 requests, $1,532.15, which is a session-level model-selection question
rather than a routing one.

### Decided 2026-07-25: Fable 5 main-loop traffic ($1,532.15)

> **Outcome: the middle option was adopted** — Fable only for genuinely
> long-horizon work, and a skill that wants it **asks the user to switch**
> rather than assuming. Encoded as `session_model` in `command_config.yml`,
> gated by `tests/bats/subagent_policy.bats` (T9). Policy:
> [docs/MODEL-POLICY.md](../MODEL-POLICY.md#2-sessions-start-on-opus-fable-is-asked-for-never-assumed).
> The options as originally costed are preserved below.

The largest single uncosted item, and the one thing here that is **not** a code
change — it is a policy choice about which model starts a session. 3,921
main-loop requests on Fable 5 at $10/$50 per MTok.

| Option | Effect | Cost if adopted |
|---|---|---|
| Leave as-is | No change; Fable stays the default for hard work | $1,532.15 |
| Fable only when the task is genuinely long-horizon; Opus otherwise | Halves the premium on routine sessions | ~$766 |
| Opus default, Fable opt-in per session | Largest saving; risks under-powering hard work | ~$766 → $383 |

**Recommendation:** the middle option. Fable's advantage is long-horizon
autonomous work; on routine sessions it bills 2x Opus for capability the task
does not use. This needs your call, not a default I pick — it trades money
against capability on work only you can judge.

### The larger structural lever

`reasoning` is 49.4% of Opus requests and **60.3% of Opus spend** — larger than
every other class combined. It cannot be routed per-turn for the cache reason
above, so the lever is **session-level**: start whole sessions on a cheaper
model when the work does not need a premium one. That is a scoping change, not
a routing change, and is out of scope for this baseline.

---

## Reproduce

```bash
# Opus attribution + cost derivation (the two tables above)
configs/claude/scripts/opus_attribution_report.py \
    --until 2026-07-25T20:00:00Z \
    --json docs/baselines/2026-07-25-opus-attribution.json

# Sub-agent traffic by model, incl. the Fable 5 row ($919.32), and the
# Fable main-loop figure ($1,532.15 = every non-subagent Fable cell)
configs/claude/scripts/opus_attribution_report.py \
    --until 2026-07-25T20:00:00Z --models all

# Per-model cost table (the scope-correction table) and skill usage
configs/claude/scripts/token_cost_report.py  --until 2026-07-25T20:00:00Z
configs/claude/scripts/skill_usage_report.py --until 2026-07-25T20:00:00Z
```

Re-running with the same `--until` reproduces the snapshot **byte-identically**
(verified), not merely within the ±2% tolerance.

Prices come from one shared table — `configs/claude/scripts/model_pricing.py`
(`--json` to dump it) — so a figure here cannot disagree with one in
`token_cost_report.py`. A model absent from that table is reported as
**unpriced** and excluded from every total; it is never silently costed at $0.
Cache writes are billed at the 5-minute-TTL rate (1.25x), so any 1h-TTL traffic
makes these figures a **floor**, not a point estimate.

### Verifying a landed lever

Cost tables justify a routing change; they do not confirm one happened. The
class x model matrix is the confirmation query — one command, no config
reading:

```bash
# Did premium sub-agent traffic actually stop after the change point?
configs/claude/scripts/opus_attribution_report.py \
    --since 2026-07-25T23:58:27Z --models all | grep '^subagent'
```

A `subagent x <premium model>` row that is still non-zero means the lever has
not landed in behaviour, whatever `command_config.yml` declares.

---

## Usage baseline (regression guard)

Top skill invocations at baseline, within the scan window. Any change to the
skill catalog must not reduce these. (The raw files-walked count is deliberately
not cited here or recorded in the snapshots — it grows with the corpus
regardless of `--until`, so quoting it would make a fixed baseline look stale.)

| Skill | Invocations |
|---|---:|
| code-review | 78 |
| issue-prep-auto | 43 |
| issue-dev-auto | 16 |
| pr-address-comments | 16 |
| superpowers:brainstorming | 13 |
| superpowers:writing-plans | 13 |
| superpowers:subagent-driven-development | 12 |
| commit-commands:commit-push-pr | 12 |
| spec-review | 11 |
| superpowers:test-driven-development | 10 |

346 Skill-tool invocations across 64 distinct skills; 521 user-typed slash
commands across 41 distinct commands.

### Deployed catalog size

107 deployed skills, 23,569 chars of name+description (~5,892 tokens). The 15
design/Stitch skills added by this deploy account for 2,658 chars (11.3%) —
tracked because catalog growth competes for the skill-listing budget, and a
skill whose description is dropped never triggers.
