# Generic CLI Agent Refactor, Model Refresh, and Antigravity Parallel Agent

**Date**: 2026-06-11
**Status**: Approved
**Scope**: Refactor CLI-based runners in `parallel_agent.py` into one data-driven
`CLIAgent`, add Antigravity (`agy`) as the 5th parallel agent, refresh all model
tier pins, govern the spec reviewer's model from the same registry, and add a
model staleness check to health-check.

**Related**: [2026-06-01-antigravity-support-design.md](2026-06-01-antigravity-support-design.md)
(Antigravity as IDE platform target — symlink hub, bootstrap toggle). This spec
builds on it: the same `antigravity` service toggle now also gates `agy` agent
participation.

---

## Problem

1. **Stale model pins.** `model_tiers` in `configs/claude/config/parallel_agent.yml`
   (and the duplicated defaults in `configs/claude/scripts/agents/config.py`) have
   drifted: `claude-opus-4-6` (current: Opus 4.8, plus the new Fable 5 tier),
   `gemini-3-*-preview` (current: Gemini 3.5 Flash / 3.1 Pro), o3-era Codex pins.
   Nothing detects this drift; agents silently run on outdated or soon-to-be-retired
   models.
2. **No Antigravity agent.** The `agy` CLI is installed and already used by
   `spec_review.sh`, but is not part of the parallel consensus pool.
3. **Boilerplate runners.** `CursorAgent` and `CodexAgent` are near-identical
   subprocess wrappers; adding each new CLI provider costs a new Python class.
4. **Ungoverned spec reviewer.** `spec_review.sh` invokes `agy -p` with no
   `--model`, riding agy's session default — outside any model governance.

## Approach (chosen)

A **generic, YAML-driven `CLIAgent`** replaces the per-provider CLI runner classes.
Adding a CLI provider becomes a configuration change. Antigravity is the proving
case: it ships as config only, zero new runner code beyond the generic class.

Alternatives considered:

- *Dedicated `AntigravityAgent` class* (mirror of `CodexAgent`): lowest-risk but
  perpetuates the boilerplate pattern. Rejected in favor of the refactor.
- *agy as orchestration-level wrapper script only*: would not participate in
  consensus scoring. Rejected — full 5th agent was the requirement.

### Known limitation: consensus diversity

agy's catalog (per `agy models`) contains only Gemini, Claude, and GPT-OSS
families — all but GPT-OSS already in the pool via direct API. Adding agy
increases *run independence* (different harness/system prompts) but not *model
diversity*; same-family agents correlate and can inflate consensus scores. This
is documented in the orchestration guide as a known correlation, not solved.
GPT-OSS 120B is not treated as a peer-tier mitigation.

---

## Components

### 1. `CLIAgent` (`configs/claude/scripts/agents/runners.py`)

One class, N provider definitions. `ClaudeAgent` and `GeminiAgent` (API-based)
are unchanged. `CursorAgent` and `CodexAgent` are **removed**; call sites in
`orchestrator.py` / `cli.py` construct `CLIAgent(provider, ...)`.

Provider definitions live in a new `cli_agents:` block in `parallel_agent.yml`,
with matching hardcoded fallback defaults in `agents/config.py` (same pattern as
`model_tiers` — the two must never disagree):

```yaml
cli_agents:
  cursor:
    binary: cursor
    base_args: []
    model_args: ["--model", "{model}"]
    output: stdout
  codex:
    binary: codex
    base_args: ["exec", "--full-auto", "--color", "never",
                "--output-last-message", "{output_file}"]
    model_args: ["--model", "{model}"]
    output: file_then_stdout
  antigravity:
    binary: agy
    base_args: []
    model_args: ["--model", "{model}"]
    prompt_args: ["--print", "{prompt}"]
    output: stdout
```

Behaviors:

- **Command assembly**: `[binary] + base_args + (model_args if model else []) + prompt_args`.
  The optional model group is dropped *atomically* (structural grouping — no
  flag/value pair scanning, no dangling `--model`). A tier of `auto`/unresolved
  yields no model args (preserves Codex `auto` behavior).
- **Prompt placement is data too**: `prompt_args` (default `["{prompt}"]`, a
  trailing positional) covers CLIs whose prompt is a flag value — agy's
  `--print` is a Go flag that *takes the prompt as its argument*, so antigravity
  uses `prompt_args: ["--print", "{prompt}"]` (live-verified; a positional
  prompt after `--print` is silently swallowed by Go flag parsing). The prompt
  content itself is never template-substituted.
- **Exec-style execution**: args remain a list passed to
  `asyncio.create_subprocess_exec` — never a shell string. Preserves existing
  command-injection protection.
- **Output strategies**: explicit mapping `{"stdout": ..., "file_then_stdout": ...}`.
  `file_then_stdout` reproduces Codex's exact priority (output file > stdout >
  stderr-on-nonzero-exit). `{output_file}` in `base_args` triggers
  `NamedTemporaryFile` creation before exec and `os.unlink` in a `finally`.
- **Availability check**: `shutil.which(binary)` → `status: missing` result
  (existing pattern).
- **Inherited from `BaseAgent` unchanged**: rate limiting, timeout, credit
  exhaustion detection, fallback chain walking, tier resolution via
  `model_tiers.<provider>.<tier>`.

New CLI flags (existing convention): `--antigravity-only`,
`--antigravity-model <tier>`. New config entries: `rate_limits.antigravity`,
`credit_fallback.antigravity`, `model_tiers.antigravity`, and an `antigravity`
service entry in `services.yml` (the existing toggle extends from IDE symlinks
to agent participation).

Risk accepted: refactoring two working runners carries regression risk in
Codex's output-file handling. Mitigation: port Codex runner tests *first*, keep
its output priority as a named strategy, verify behavior parity before removing
the old classes.

### 2. Model refresh (`parallel_agent.yml` + `agents/config.py` defaults)

Pins stay pinned (reproducibility); this change refreshes them with live
verification at implementation time (provider docs/model-list endpoints, plus
each CLI's own listing — `agy models` already confirmed its catalog).

| Provider | Tier | Current (stale) | Proposed |
|----------|------|-----------------|----------|
| claude | haiku | `claude-haiku-4-5-20251001` | unchanged (still latest haiku) |
| claude | sonnet | `claude-sonnet-4-5-20250929` | `claude-sonnet-4-6` |
| claude | opus | `claude-opus-4-6` | `claude-opus-4-8` |
| claude | **fable** (new) | — | `claude-fable-5` (new top tier) |
| gemini | flash | `gemini-3-flash-preview` | Gemini 3.5 Flash GA ID (verify slug) |
| gemini | pro | `gemini-3-pro-preview` | Gemini 3.1 Pro GA ID (verify slug) |
| cursor | mini/flash/advanced | gpt-5.1 era | verify against current Cursor docs |
| codex | mini/flash/advanced | o4-mini / o3 / o3-pro | verify against current Codex docs |
| antigravity (new) | mini | — | Gemini 3.5 Flash (Low) — slug via `agy models` |
| antigravity (new) | flash | — | Gemini 3.5 Flash (High) — slug via `agy models` |
| antigravity (new) | advanced | — | Claude Opus 4.6 (Thinking) — slug via `agy models` |

Antigravity tier keys follow the `mini/flash/advanced` convention shared by the
other CLI agents (cursor, codex), so intent-level flags stay semantically
uniform across the CLI pool. (`claude`/`gemini` API agents keep their
provider-native keys — `haiku/sonnet/opus/fable`, `flash/pro` — as today.)

**Catalog constraint (accepted)**: antigravity pins are bounded by agy's served
catalog, which may lag the direct API — e.g. agy's ceiling is Opus 4.6 while the
direct Claude agent runs Opus 4.8/Fable 5. This version skew within the pool is
accepted, documented in the orchestration guide alongside the diversity caveat,
and detected over time by the staleness check (for antigravity, `agy models` is
the ground truth, not Anthropic's API).

Lockstep updates: `credit_fallback.claude` → `[fable, opus, sonnet, haiku]`;
`credit_fallback.antigravity` → `[advanced, flash, mini]`; `agents/config.py`
fallback defaults synced to the YAML; doc examples refreshed; and
`task_model_defaults` in `command_config.yml` updated so the new top tier is
actually auto-selected — security-critical and architecture task types move
from `opus` to `fable` (with the credit-fallback chain degrading through opus →
sonnet → haiku). Without this, `fable` would exist as a tier key reachable only
via explicit `--claude-model fable` and never be chosen by the orchestrator.

Antigravity's default tier is a Gemini model — overlap with the Gemini API agent
is the documented diversity caveat above.

### 3. Spec reviewer alignment (`configs/claude/scripts/spec_review.sh`)

- New `SPEC_REVIEW_MODEL` env seam, mirroring the existing `SPEC_REVIEW_CLI` seam.
- Default resolution: `model_tiers.antigravity.advanced` from
  `~/.claude/config/parallel_agent.yml`, read via a small python3/yq fallback.
- Fail-open: if the config is unreadable or the key is absent, omit `--model`
  and ride agy's default (preserves the script's fail-open philosophy — a broken
  config must never block a save hook).
- When resolved, `run_reviewer` passes `--model "$SPEC_REVIEW_MODEL"`.

Result: one registry governs both the parallel pool and the spec reviewer.

### 4. Model staleness check (`configs/claude/scripts/check_status.sh` + `/health-check`)

New warn-only check, surfaced through the existing health-check report:

- **CLI agents** (cursor, codex, antigravity): run the CLI's model-list command
  where one exists (`agy models` confirmed; cursor/codex equivalents verified at
  implementation; if a CLI has no listing command, report `UNSUPPORTED`). Flag
  any configured tier ID absent from the listing.
- **API agents** (claude, gemini): query the provider's models endpoint
  (Anthropic `GET /v1/models`; Gemini list-models) only when credentials are
  already present; otherwise `SKIPPED (no credentials)` — health check must not
  demand new auth.
- Report lines: `OK` / `STALE: model_tiers.claude.opus = claude-opus-4-6 not in
  provider listing` / `SKIPPED` / `UNSUPPORTED`.
- Never blocks; exit code unaffected by staleness findings.

### 5. Bootstrap (`bootstrap/lib/`)

- agy CLI availability + auth detection added under the existing `antigravity`
  toggle (`install.sh` / `auth.sh` / summary in `deploy.sh`).
- Per the 2026-06-01 design, config deployment stays unconditional; the toggle
  gates reporting and now also agent participation via `services.yml`.

### 6. Tests and docs

- **pytest** (`tests/python/`, extending `test_parallel_agent.py` coverage):
  `CLIAgent` arg assembly (model group present/dropped, `{output_file}`
  substitution), output strategies (file > stdout > stderr priority parity with
  old `CodexAgent`), missing binary, tier resolution, config-default sync test
  (YAML defaults == `config.py` defaults for `cli_agents`/`model_tiers`).
- **bats** (`tests/bats/`): `spec_review.sh` model seam (env override, config
  resolution, fail-open on missing config); staleness check report formats.
- **Docs**: both CLAUDE.md orchestration guides, `references/parallel-agent.md`
  (flags, 5-agent table), AGENTS.md, README agent table (4 → 5), CLAUDE.md
  example commands with refreshed tier names.

---

## Data flow

```
parallel_agent.yml ──┐
                     ├─→ Config ─→ CLIAgent(provider) ─→ subprocess exec ─→ consensus pool
config.py defaults ──┘                │
                                      └─ model_tiers.<provider>.<tier> ─┐
                                                                        ├─→ one registry
spec_review.sh ── SPEC_REVIEW_MODEL ── model_tiers.antigravity.advanced ┘
check_status.sh ── compares model_tiers.* against live provider listings (warn-only)
```

## Error handling

- Missing CLI binary → `status: missing` (agent excluded from consensus, run
  continues) — existing behavior, now uniform across all CLI providers.
- Credit exhaustion → existing `BaseAgent` fallback chain, now including
  `credit_fallback.antigravity`.
- Unreadable `cli_agents` config for a provider → that agent reports
  `status: failed` with a config error; other agents unaffected.
- Spec reviewer: all model-resolution failures degrade to "no `--model` flag"
  (fail-open), never a blocked review.
- Staleness check: network/auth failures degrade to `SKIPPED`, never fail the
  health check.

## Out of scope

- Weighting consensus scores by model-family correlation (documented only).
- Dynamic/alias model resolution (e.g. `latest`) — pins stay explicit.
- Refactoring `ClaudeAgent`/`GeminiAgent` (API runners are genuinely distinct).
- Antigravity IDE deployment mechanics (covered by 2026-06-01 design).

## Build sequence

1. Port existing Cursor/Codex runner tests to characterize current behavior.
2. Introduce `CLIAgent` + `cli_agents` config (cursor, codex) — tests green.
3. Remove `CursorAgent`/`CodexAgent`; update `orchestrator.py`/`cli.py` call sites.
4. Add antigravity provider config, tiers, rate limits, fallback chain, flags,
   `services.yml` entry, bootstrap detection.
5. Model refresh across `parallel_agent.yml` + `config.py` +
   `command_config.yml` `task_model_defaults` + docs (live-verify each slug).
6. `SPEC_REVIEW_MODEL` seam in `spec_review.sh` + bats tests.
7. Staleness check in `check_status.sh` + health-check report wiring.
8. Docs pass (orchestration guides, references, README, AGENTS.md).
