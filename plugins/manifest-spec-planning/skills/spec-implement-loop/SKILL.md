---
name: spec-implement-loop
description: "Use once spec/plan are approved and ready to implement — critic-gated loop (CDDL): developer writes, reviewer/QA/architecture critics gate on zero findings. Never commits or pushes."
---

# Critic-Gated Implementation Loop (CDDL)

Runs a completed feature through an adversarial loop orchestrated with **native
sub-agents** (Task tool). **Do not** use `parallel_agent.py` for personas — panel
consensus is a different workflow.

## Personas (strict separation)

| Persona | Sub-agent type | Writes code? | Phase |
|---------|----------------|--------------|-------|
| **Developer** | `generalPurpose` | **Yes — only role** | 2 |
| **Developer reviewer** | `code-reviewer` (`readonly: true`) | **Never** | 2 |
| **QA / security critic** | `security-review` (`readonly: true`) | **Never** | 1 + 2 |
| **Architecture critic** | `code-architect` (`readonly: true`) | **Never** | 1 + 2 |

The orchestrator (you) **never** writes implementation code — only dispatches
sub-agents, runs verification, parses verdicts, persists run artifacts, and
stages on success.

**Completion:** phase 2 succeeds only when the developer reviewer, QA critic,
and architecture critic **each** return `approve` with **zero findings** on the
same iteration. Any findings → feed back to the developer and iterate.

## Sub-agent dispatch

> Sub-agents: **always** — one fresh sub-agent per persona per round/iteration.
> Sequential dispatch only (no parallel critics — each must see the same tree).

**Primary (Claude Code, Cursor):** native Task sub-agents per
`configs/claude/references/sub-agent-dispatch.md`.

**CLI fallback (Gemini, Codex, Antigravity):** critics and developer-reviewer via
`~/.claude/scripts/cddl_invoke.py` — see `prompts/cli-dispatch.md`. Model tiers:
`configs/claude/references/cddl-role-models.md`. The developer role still
requires a writer — run implementation in the main session when Task is absent, or
ask the operator to use Cursor / Claude Code for full separation.

Charters (deployed copies under `~/.claude/prompts/cddl/` after bootstrap):

- `developer.md` — code author
- `developer-reviewer.md` — spec/plan + quality gate
- `qa-critic.md` — security / validation / runtime safety
- `arch-critic.md` — layering / design / DRY

Dispatch templates live in this skill's `prompts/` directory. Hand sub-agents
**file paths**, not pasted artifacts.

## Session model

This skill is **long-horizon**: the CDDL loop re-runs four personas over the whole tree every round,
until the gates clear.

Before starting, check the session's model. If it is not Fable 5, **ask the user to switch**
(`/model` → Fable 5) and wait for the answer. Do not assume Fable is active, and do not silently
proceed on the default model — the choice trades ~2x the per-token cost against capability, so it
is the user's to make. Everything shorter than this runs on Opus by default
(`session_model` in `command_config.yml`; rationale in `docs/MODEL-POLICY.md`).

## Prerequisites

- Feature branch (not default); clean tree unless operator passes `--allow-dirty`
- Resolvable spec (+ optional plan): speckit feature dir or superpowers design
  doc — discovery per `configs/claude/references/spec-artifact-discovery.md`
- `uv sync --project configs/claude` (or home bootstrap) so verification tools
  exist when auto-detecting gates

## Procedure

### 0. Pre-flight (orchestrator, inline)

1. Refuse default branch and dirty tree (unless `--allow-dirty`).
2. Resolve spec + plan; write `<RUN_DIR>/context.md` (paths, layout, verify cmd,
   iteration/round limits, clarification answers).
3. Create run dir:
   `${MANIFEST_STATE_ROOT:-~/.manifest}/cddl/runs/<repo-slug>/<run-id>/`
   with `state.json` (`phase`, `iteration`, `round`, `status`).

Defaults: clarification rounds **3**, implementation iterations **10**.

### 1. Phase 1 — clarification gate (no code)

For each round until both critics `complete` or rounds exhaust:

1. Dispatch **QA critic** (`security-review`, `readonly: true`) with
   `reviewer-dispatch.md` — phase 1, artifacts = spec + plan only.
2. Dispatch **architecture critic** (`code-architect`, `readonly: true`) —
   same inputs, independent.
3. Parse last `cddl-verdict` block from each output (`prompts/verdict-format.md`).
4. If **either** has `questions` findings → write `questions.md`, relay to the
   operator, collect answers → `answers-<round>.md`, append to `context.md`,
   next round.
5. If **both** `complete` with zero findings → enter phase 2.

If rounds exhaust with open questions → **gate failure** (no code produced);
write `report.md` and stop.

### 2. Phase 2 — implement → verify → triple review

For each iteration until all three reviewers approve or iterations exhaust:

1. **Developer** (`generalPurpose`, **not** readonly) — `developer-dispatch.md`.
   Only this sub-agent may modify the repo.
2. **Verification** (orchestrator): run the verify command from context (or
   `/manifest-code-quality:project-verify`). On failure, write deficiencies to
   `iterations/<n>/verify.log`, skip critics, next iteration with verify output
   as developer feedback.
3. Generate review package: `git diff` + `git diff --cached` →
   `iterations/<n>/review-package.diff`.
4. Dispatch **developer reviewer** (`code-reviewer`, `readonly: true`).
5. Dispatch **QA critic** (`security-review`, `readonly: true`).
6. Dispatch **architecture critic** (`code-architect`, `readonly: true`).
7. Parse verdicts. If **any** persona has findings → merge into
   `iterations/<n>/findings.md` for the next developer dispatch.
8. If **all three** `approve` with **empty findings** → success (step 3).

If iterations exhaust without triple approval → **ceiling failure**; leave work
applied but **unstaged**; `report.md` lists per-persona outstanding findings.

### 3. Success disposition

- `git add --` only paths from the final approved iteration (never pre-existing
  dirt, never unrelated files).
- **Never** commit, push, or merge.
- Write `report.md`; tell the operator staged paths (`git diff --cached --name-only`).

## Operator relay (phase 1)

When critics ask questions, present them conversationally, collect answers in one
message, persist to `answers-<round>.md`, and continue — one continuous session.
Do not ask the operator to run CLI tools.

## Tunables

| Flag / env | Default | Meaning |
|------------|---------|---------|
| `--max-rounds` | 3 | Clarification rounds |
| `--max-iterations` | 10 | Implementation iterations |
| `--verify-cmd` | auto-detect | Override verification command |
| `--allow-dirty` | off | Allow dirty tree at start |
| `CDDL_INVOKE_PROVIDER` | auto | Headless critic CLI provider |
| `CDDL_INVOKE_CLI` | — | Binary override for `cddl_invoke.py` |

## Persistence

Per iteration: `developer-report.md`, `developer-reviewer.md`, `qa-critic.md`,
`arch-critic.md`, `verdicts.json` (parsed), `verify.log`, `findings.md`.

Keep everything under the run dir (manual prune: `rm -rf <run-id>`).

## What this skill does NOT do

- Use `parallel_agent.py` for personas
- Let critics or the developer reviewer write code
- Commit or push
