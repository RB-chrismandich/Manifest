# Model Selection

> Pins, tiers, and fallback order.

**Last Updated**: 2026-08-20

## Model Selection

### Model Tiers

Every pin below carries its verification status as of **2026-07-29**. VERIFIED
means a real one-shot call through that provider's own CLI answered; UNVERIFIED
means the pin is retained so tier lookups resolve, but nothing has confirmed it.
The distinction is load-bearing — pins transcribed from documentation are what
produced this repo's 404ing Gemini tiers. Re-check with `model_check.sh`
(`MODEL_CHECK_PROBE=1` on machines with no API key).

#### Cursor Models — VERIFIED

| Tier | Model Name | Use Case | Cost |
|------|------------|----------|------|
| `mini` | cursor-grok-4.5-low | Quick queries | Lowest |
| `flash` | cursor-grok-4.5-medium | Code review (default) | Medium |
| `advanced` | cursor-grok-4.5-high | Security analysis | Highest |
| `auto` | (Cursor decides) | Let Cursor optimize | Variable |

One effort ladder from a single family, so the tiers genuinely differ — all three
previously read `auto`, which made the tier abstraction inert. `auto` and
`composer-2.5` also verified and remain valid alternates. Cursor's newer premium
ladder (`claude-opus-5-thinking-*`, `gpt-5.6-sol-*`,
`kimi-k3-high`) is **not** pinned: every one returned an account usage-limit
`ActionRequiredError` (resets **2026-08-12**), making them unverifiable rather
than broken. Re-probe after that date and promote `advanced` if they answer.

#### Claude Models — VERIFIED

| Tier | Model Name | Use Case | Cost |
|------|------------|----------|------|
| `haiku` | claude-haiku-4-5 | Quick queries | Lowest |
| `sonnet` | claude-sonnet-5 | Code review (default) | Medium |
| `opus` | claude-opus-5 | Security analysis | Higher |

Full IDs, not the `opus`/`sonnet`/`haiku` aliases (which also work): an
alias is a moving target the provider can remap, so pinning one would let a tier
change model without a diff in this repo.

#### Gemini Models — UNVERIFIED

| Tier | Model Name | Use Case | Cost |
|------|------------|----------|------|
| `flash` | gemini-3-flash-preview | General use (default) | Lower |
| `pro` | gemini-3-pro-preview | Complex analysis | Higher |

**The `gemini` CLI is non-functional on a free-tier account.** Every invocation
fails at the eligibility layer — before model selection — with
`IneligibleTierError`: *"no longer supported for Gemini Code Assist for
individuals … migrate to the Antigravity suite"*. With no `GOOGLE_API_KEY` /
`GEMINI_API_KEY` set, the REST models endpoint cannot confirm these IDs either,
so both pins are unproven. Google's own stated remedy is the Antigravity table
below, which serves Gemini models and *is* verified.

#### Codex Models — VERIFIED (2026-08-02)

| Tier | Model Name | Use Case | Cost |
|------|------------|----------|------|
| `mini` | gpt-5.6-luna | Quick queries | Lowest |
| `flash` | gpt-5.6-terra | Code review (default) | Medium |
| `advanced` | gpt-5.6-sol | Security analysis | Highest |

VERIFIED 2026-08-02: all three pins answered a live
`codex exec --skip-git-repo-check --model <id>` probe on a ChatGPT login.
The CLI still exposes no model-listing command (no `models`, `models list`,
`--list-models`), so `model_check.sh` has no listing source — re-verify with
`MODEL_CHECK_PROBE=1 model_check.sh`. gpt-5.4* retire from ChatGPT-login
Codex on 2026-08-31.

#### Antigravity Models — VERIFIED

| Tier | Model Name | Use Case | Cost |
|------|------------|----------|------|
| `mini` | gemini-3.6-flash-low | Quick queries | Lowest |
| `flash` | gemini-3.6-flash-high | General use (default) | Medium |
| `advanced` | claude-opus-4-6-thinking | Complex analysis | Highest |

**Note**: these are slugs, not display labels. `agy models` emitted labels like
`Gemini 3.5 Flash (Low)` under agy 1.1.1 and emits slugs under 1.1.8. agy still
*accepts* the old labels, so the previous pins were never broken at runtime —
they had merely stopped matching the catalog, which made `model_check.sh` score
them STALE for a cosmetic reason. `mini`/`flash` keep the prior low/high effort
split, moved up to the 3.6 flash family now that it exists. Antigravity's
catalog is managed by the `agy` CLI and may lag the direct API (its top Claude
entry is Opus 4.6, where the Claude table above is on Opus 5). Run `agy models`
for the live list, which `model_check.sh` validates.

#### Devin Models

Devin has **no tier table on purpose**. `devin models list` is login-gated, so the
account's real catalog cannot be enumerated from this repo, and pinning names read
off a docs page is how a stale pin turns into a runtime 404. Consequences:

- `--devin-model` defaults to `auto`, which sends no `--model` flag at all and lets
  the account default stand.
- Any other value is passed through verbatim, so you can name a real model
  (`--devin-model opus`) once `devin models list` shows you what your account has.
- `credit_fallback.devin` is empty: there is no known cheaper tier to fall back to.

**Skills, rules, and MCP servers are inherited, not copied.** `devin` reads
`~/.claude/skills` and `~/.claude/CLAUDE.md` directly when
`~/.config/devin/config.json` sets `read_config_from.claude: true` (bootstrap pins
it). Copying the skills into `~/.config/devin/skills` would register each one twice
— `/devin:<name>` beside `/claude:<name>` — so `agent_roster.yml` marks devin
`skills_sync: false`. MCP servers arrive the same way: `devin mcp list` showed 11
servers on a Manifest-configured home and 3 with `read_config_from.cursor: false`,
the missing 8 being exactly what `--install-mcp` wrote to `~/.cursor/mcp.json`.
Verify the whole inheritance chain with:

```bash
devin skills list | grep -c '~/.claude/skills'   # expect your skill count
devin rules list                                 # expect a CLAUDE entry
devin mcp list                                   # expect your registry
```

**Known interaction:** `devin rules list` reports a YAML parse error for each
generated Cursor rule (`~/.cursor/rules/*.mdc`), because `generate_cursor_rules.sh`
emits `globs:` as a string and Devin's parser requires a sequence. Those rules are
per-skill duplicates of skills Devin already loads from `~/.claude/skills`, so the
errors are noise, not lost capability; the fix (emit a YAML list) is deferred
because Cursor's own tolerance for the list form is unverified.

### Selecting Models

**Via CLI flags:**

```bash
# Use advanced models for security-critical code
~/.claude/scripts/parallel_agent.py \
  --cursor-model advanced \
  --claude-model opus \
  --review auth.py

# Use lightweight models for quick questions
~/.claude/scripts/parallel_agent.py \
  --cursor-model mini \
  --claude-model haiku \
  "What is this function doing?"
```

**Via environment variables:**

```bash
export CURSOR_MODEL_ADVANCED="gpt-5.2"
export CURSOR_MODEL_FLASH="gpt-5.1-codex"
export CURSOR_MODEL_MINI="gpt-5.1-codex-mini"

~/.claude/scripts/parallel_agent.py --cursor-model advanced "Task"
```

**Via command_config.yml** (see task_model_defaults above)

---

---

[← Configuration](README.md)
