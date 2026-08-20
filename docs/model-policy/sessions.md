# Levers 2 & 3 — Sessions and Turns

> Why sessions start on Opus and why individual turns are not downgraded.

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

---

[← Model Policy](../MODEL-POLICY.md)
