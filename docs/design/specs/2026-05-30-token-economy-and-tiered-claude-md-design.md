# Token Economy Skill + Tiered CLAUDE.md — Design

**Date**: 2026-05-30
**Status**: Approved for planning
**Topic**: Two complementary token-reduction deliverables for the skill library —
an invokable `token-economy` session-mutator skill, and a tiered restructure of
the always-loaded `configs/claude/CLAUDE.md`.

---

## Goal

Cut token burden along its two independent vectors without degrading execution
accuracy:

- **Fixed input tax per turn** → tier `configs/claude/CLAUDE.md` (always loaded
  into every Claude turn) into a lean core + on-demand `references/`.
- **Dynamic session growth** (output verbosity + error-retry loops) → an opt-in
  `/token-economy` skill that switches the session into terse, surgical,
  clarify-first behavior. Zero always-loaded cost.

**Non-goal / guardrail:** optimization must not shift cost into error-and-retry
loops. No context starvation, no amputation of always-on guidance. A 2K-token
dependency read is cheaper than a 15K-token error-correction spiral.

## Deliverable A — `token-economy` skill (session mutator)

### Files
- Create: `.retired skill supply/skills/token-economy/SKILL.md`
- Modify: `configs/claude/config/command_config.yml` (add `tool_policies` entry)

### Behavior
Invoked as `/token-economy`. On invoke, Claude adopts the following constraints
**for the remainder of the session** (guidance, not hard enforcement):

1. **Zero filler.** No preambles ("Sure!", "Here's the…"), no post-hoc
   restating of what the code does, no closing summaries unless asked. Lead with
   the result.
2. **Surgical edits, stated by capability (not by environment name).** Phrasing
   the rule as "if you're in Claude Code… else if API…" makes the model
   self-reflect on its environment and risks misfiring in terse mode. State it
   by the capability the model actually controls — its output representation:
   > *Do not emit text-based diffs or full-file rewrites when a programmatic
   > file-editing tool is available. If text output is your only option, emit
   > the minimum line-replacement snippet required — never reprint a whole file
   > for a small change.*
3. **Clarification gate.** If an implementation detail is genuinely ambiguous,
   ask one targeted question before generating code — don't guess and produce
   throwaway output.
4. **Balanced ingestion (NOT starvation).** Read what the change actually
   depends on (types, signatures, callers). Avoid speculative whole-tree crawls
   and re-reading unchanged files. Under-reading that causes a wrong edit is the
   expensive failure mode, not an extra dependency read.

### Notes
- It is a *session mutator*: a deliberate mode switch, not always-on. This keeps
  baseline context cost at zero for normal sessions.
- Ports to Cursor/Gemini/Codex automatically (skills sync/symlink already built
  in this PR's predecessor work).
- **Persistence caveat (documented in the skill).** A skill's text enters
  context only once, at invoke. It cannot self-inject into later turns, so in a
  long session the invocation can scroll out of the active window and Claude
  reverts to default verbosity. The SKILL.md must state plainly: *re-invoke
  `/token-economy` if the session grows past ~30k tokens or you notice verbosity
  returning.* True always-on persistence would require a hook (e.g. via
  `ai-hooks-integration`) — noted as a future option, explicitly out of scope
  here (no hook enforcement).

## Deliverable B — Tiered `configs/claude/CLAUDE.md`

Split the 685-line orchestration guide into a lean-but-complete core plus
on-demand reference files. bootstrap already deploys `configs/claude/*`
(excluding skills) to `~/.claude/` via `rsync` (`deploy.sh:76`), so
`configs/claude/references/` lands at `~/.claude/references/` automatically.

### Core stays in `CLAUDE.md` (~180–220 lines — always-on guidance)
| Section | Current lines | Why it stays |
|---------|---------------|--------------|
| Title + intro | 1–5 | Orientation |
| Parallel Agent Script → Quick Usage (trimmed to **single-line** examples) | 6–55 | Core invocation, used constantly — multi-line/commented examples move to `references/parallel-agent.md` to protect the line budget |
| Proactive Decision Framework (ALWAYS / CONSIDER / SKIP) | 169–210 | Behavioral decision rules |
| Validation Criteria (Tier 1 / Tier 2 tables) | 244–265 | Decision-critical thresholds/verdicts |
| Skills (Available table, Command Usage, Auto-Triggered) | 453–517 | Skill index — always relevant |
| Plan Management (lifecycle + housekeeping) | 664–685 | Concise, behavioral |
| **NEW: Reference Index** | — | One-line pointer per reference file (see below) |

### Moves to `configs/claude/references/` (~450 lines — load on demand)
| New file | Absorbs (current sections / lines) |
|----------|-----------------------------------|
| `references/parallel-agent.md` | Options (56–80), Model Selection (81–100), Credit Exhaustion Fallback (101–112), JSON Output Schema (113–154), Environment Variables (155–168), Output Location (305–318) |
| `references/orchestration.md` | Cross-Verification Patterns (211–243), Workflow Integration (266–292), Error Handling (293–304), Orchestrated Code Review Workflow + all phases + example (319–452) |
| `references/git-platform.md` | Git Platform Detection & Operations (518–603) |
| `references/layout.md` | Configuration Files table (604–615), File Structure tree (616–663) |

### Reference Index (added to core)
A short section listing each reference file with a one-line "read this when…"
trigger, e.g.:
Use **action-verb / error-state triggers** (not bland descriptions) so the
semantic match fires a `Read` exactly when a task or failure hits:
```markdown
## Reference Index
Read on demand (NOT auto-loaded). You MUST read the reference before related tasks:
- `~/.claude/references/parallel-agent.md` — Read for flag specs, JSON schema validation, or resolving Credit Exhaustion.
- `~/.claude/references/orchestration.md`  — Read when running multi-agent validation or debugging cross-verification failures.
- `~/.claude/references/git-platform.md`   — Read when automating PRs, branch detection, or git_ops failures.
- `~/.claude/references/layout.md`          — Read when modifying config trees or mapping file locations.
```

### Mechanics & caveat
- Claude Code auto-loads `CLAUDE.md` every turn but does **not** auto-load
  `references/`. The core's Reference Index instructs Claude to `Read` the
  relevant file when a task needs that detail. Lazy by design.
- Content is **moved, not deleted** — every relocated section is reachable via a
  core pointer. Verification (below) confirms nothing is orphaned.

## Scope & Boundaries

- Restructure applies to **Claude's `CLAUDE.md` only**. `GEMINI.md` and
  `AGENTS.md` are separate always-loaded files for other tools; giving them the
  same tiering is a **follow-up**, not this PR.
- The repo-root `CLAUDE.md` and `.claude/CLAUDE.md` are out of scope (different,
  smaller files serving different purposes).
- No hook-based enforcement of the skill (guidance only).

## Risks & Mitigations
| Risk | Mitigation |
|------|------------|
| Moving sections orphans content (a pointer-less reference) | Verification step greps that every `references/*.md` is named in the core Reference Index, and that no moved `##` heading remains duplicated in core |
| Core trimmed too far, Claude loses always-on guidance | Explicit "stays in core" table above; target ~180–220 lines, not <30 |
| Skill instructs diff-output inside Claude Code (theater) | Tool-aware wording in the skill (agentic → Edit tool; chat → diffs) |
| Skill encourages context starvation → error loops | Explicit "balanced ingestion, not starvation" constraint |
| Other tools' guides drift from Claude's after restructure | Recorded as out-of-scope follow-up; `sync-configs`/`health-check` skills already surface drift |
| Split `references/*.md` lint-fail: orphaned `###` without a parent heading (MD001) or broken intra-doc links | Each reference file opens with an H1 title; promote/nest moved subheadings so heading levels increment correctly; re-point any moved relative links. Run markdownlint on the new files (the repo's markdownlint pipeline was just repaired) |
| `references/` subdir not deployed, or dest missing | `rsync -a` (deploy.sh:76) recurses and creates dest subdirs; `deploy_configs` already `mkdir -p`s the target. Verified by the sandbox e2e (success criterion 4) rather than a code change |

## Success Criteria
1. `/token-economy` skill exists in `.retired skill supply/skills/token-economy/`, has valid
   `name`/`description` frontmatter, and is listed in `command_config.yml`
   `tool_policies`.
2. `configs/claude/CLAUDE.md` is reduced to the core (~180–220 lines) with a
   Reference Index; the four `references/*.md` files exist and contain the moved
   sections verbatim.
3. Every reference file is named in the core Reference Index (no orphans); no
   moved section heading remains in core.
4. `bootstrap.sh` (sandbox `HOME`) deploys both `~/.claude/CLAUDE.md` (core) and
   `~/.claude/references/*.md`.
5. Skill syncs to targets (`.github/skills/token-economy` after `retired skill supply sync`).
6. Existing tests still pass (`bats tests/bats/`, `pytest tests/python/`); lint
   clean — **markdownlint passes on `CLAUDE.md` and every new `references/*.md`**
   (each opens with an H1, no orphaned heading-level jumps).
7. The `token-economy` SKILL.md states the surgical rule by capability and
   includes the re-invoke persistence caveat; the core Reference Index uses
   action-verb/error-state triggers.
