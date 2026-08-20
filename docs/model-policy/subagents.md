# Lever 1 — Sub-agents Default to Sonnet

> Why sub-agents are pinned, how it is enforced, and the measured compliance.

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

Full dispatch rules: [configs/claude/references/sub-agent-dispatch.md](../../configs/claude/references/sub-agent-dispatch.md).

---

---

[← Model Policy](../MODEL-POLICY.md)
