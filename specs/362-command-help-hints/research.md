# Phase 0 Research: Command Discovery & Workflow Guidance

**Feature**: 362-command-help-hints | **Date**: 2026-06-21

All clarifications were resolved in `/speckit-clarify` (see spec Clarifications 2026-06-21).
This document records the remaining design decisions needed before Phase 1, each with
rationale and rejected alternatives. No open `NEEDS CLARIFICATION` items remain.

---

## D1 — Curated category taxonomy

**Decision**: A fixed set of 8 categories, defined in `command_categories.yml`:
`git-pr`, `docs`, `security`, `planning`, `skills`, `ci-cd`, `infra`, `meta`. Plus the
implicit `uncategorized` bucket for unmapped commands. Each command maps to exactly one.

**Precedence (resolves the "single source" constraint)**: `command_categories.yml` defines
only the **valid taxonomy** (keys, labels, order) plus an explicit `overrides:` map.
Assignment authority order: (1) a per-skill `category:` in `SKILL.md` frontmatter is
authoritative; (2) the `overrides:` map in the taxonomy file wins **only** for commands it
explicitly names (the escape hatch for skills not yet carrying frontmatter); (3) otherwise
→ `uncategorized`. The taxonomy file is therefore not a competing *assignment* source — it
bounds valid values and holds explicit, auditable exceptions.

**Rationale**: These clusters already emerge from the existing skill library (e.g.
`docs-*`, `refactor-*`, `ci-*`, `speckit-*`, `pr-*`, security audits) and from how
`docs/COMMANDS.md` groups today. Eight is small enough to scan, broad enough to home all
~84 commands. Mapping lives in config (not skill names), so re-categorizing is a config
edit, not a rename.

**Alternatives rejected**:
- *Freeform per-skill categories* — drift into near-duplicates (`git` vs `git-ops` vs `PR`); unstable grouping.
- *Derive from directory/name only* — many skills lack a categorizable prefix; misclassifies the long tail.

## D2 — `when-to-use` derivation (no new field)

**Decision**: Derive the "when to use" cue from the existing description convention.
Most `SKILL.md` descriptions already begin with or contain "Use when …"; parse that
clause. Fallback chain: (1) explicit "Use when …" sentence → (2) first sentence of
`description` → (3) `name` humanized. Never invent text not present in the source.

**Rationale**: Honors the source-of-truth assumption (FR-003) with zero schema change.
Inspection of the skill library shows the "Use when…" convention is already dominant.

**Alternatives rejected**:
- *New `when_to_use` frontmatter field* — redundant with description; adds a field to maintain across 84 files and 5 platforms.

## D3 — Catalog generation + drift detection

**Decision**: `command_catalog.py` parses every `.skillshare/skills/*/SKILL.md` frontmatter
(walking with symlink-following per repo convention) into an in-memory catalog;
`generate_commands_doc.py` renders it to `docs/COMMANDS.md`. A `--check` mode regenerates
in memory and diffs against the committed file, exiting non-zero on drift (mirrors
`version_pin.sh --check`). Wired into CI (a `bats` test) and optionally a save-hook.

**Injection bounding (FR-009/SC-006)**: always-loaded targets (`GEMINI.md`, `AGENTS.md`,
Cursor rule) receive only a **compact index** — category headers + `` `/name` `` links, no
descriptions — under a hard line cap with a "Run /help for full details" fallback. Full
text lives only in the on-demand `/help` surface and `docs/COMMANDS.md` (not always-loaded).
A `bats` test asserts the injected block stays under the `context_budget` threshold as the
catalog grows.

**Rationale**: Generation-from-source is the only way to satisfy FR-004 / SC-002 (zero
drift). Reuses the established `generate_cursor_rules.sh` + `version-pin --check` patterns
already trusted in this repo, so reviewers recognize the shape.

**Alternatives rejected**:
- *Hand-maintained `COMMANDS.md`* — guaranteed drift; violates FR-004.
- *Runtime-only catalog (no committed doc)* — loses out-of-session browsing/linking (rejected by clarify Q5).

## D4 — Cross-platform hint delivery (parity in v1)

**Decision**: Deliver event-driven, one-shot hints through the existing
`ai-hooks-integration` plumbing, which already abstracts lifecycle hooks across Claude
Code, Gemini CLI, Cursor, and OpenCode. Map Workflow Moments to hook events:
pre-commit / PR-open → `PreToolUse` (Bash matcher on `git commit` / `gh pr|glab mr`);
high-context → session/compaction signal; refactor-start → `PreToolUse` matching invocation of a `/refactor-*` command (NOT the discovery command).
`guidance_hint.py` is the single handler each platform's hook calls; per-platform reach
for the **discovery list** uses each adapter's native convention (Claude skill, Cursor
`.mdc` via `generate_cursor_rules.sh`, Gemini/Codex guide injection, Antigravity symlinks).

**Rationale**: Reuses a purpose-built cross-tool hook layer (FR-011 parity) instead of
inventing five bespoke integrations; one handler keeps behavior identical across platforms.

**Alternatives rejected**:
- *Per-platform bespoke hooks* — five code paths to keep in sync; high parity-drift risk.
- *Always-loaded hint text in guides* — violates FR-009 (per-turn context cost).

## D5 — Guidance preferences + rate-limit state

**Decision**: Two layers. **Shipped defaults** in committed `configs/claude/config/guidance.yml`
(all enabled). **User overrides** in a gitignored `~/.claude/config/guidance_local.yml`,
created on first toggle. Effective prefs = defaults ← local (local wins). So a single
opt-out toggle (SC-004) writes only the machine-local file and never dirties the tracked
tree. Ephemeral rate-limit state (last-fired timestamps per moment) lives in a small
uncommitted state file under the agent home (e.g. `~/.claude/state/guidance/`), never in
the repo.

**Rationale**: Separates declarative config (committed, deployed) from runtime state
(machine-local), consistent with how the repo treats `services.yml` vs runtime caches.
Per-category granularity satisfies clarify Q4 / FR-007.

**Alternatives rejected**:
- *Single global flag only* — too blunt (rejected by clarify Q4).
- *State committed to repo* — churns git, leaks machine specifics.

## D6 — Availability resolution

**Decision**: A command is "available" iff (a) its owning service is enabled in
`services.yml` AND (b) it is deployed to the active platform per the existing per-platform
deployment mapping. The catalog annotates each entry with an availability status; the
discovery surface marks unavailable commands rather than recommending them (FR-008).

**Rationale**: Both signals already exist; no new metadata (per clarify + spec assumption).

**Alternatives rejected**:
- *New per-skill `platforms`/`availability` frontmatter* — contradicts "no new availability field" assumption.

## D7 — Discovery command + search ranking

**Decision**: New skill `/help` (interactive). Inputs: optional free-text query and/or
`--category`. Search ranks by weighted match over `name` (highest), `category`, then
`description`/`when-to-use` text; ties broken alphabetically. Empty query → full grouped
listing. No match → explicit "no command matches" message (edge case in spec).

**Rationale**: Skill-First (Constitution IV); simple deterministic ranking is testable
(SC-001/SC-003) and needs no model call, keeping it fast and offline-capable.

**Alternatives rejected**:
- *Embedding/semantic search* — adds a runtime dependency and nondeterminism; overkill for ~84 entries.
- *Bake discovery into `parallel_agent.py`* — violates Skill-First.

---

## Resolved unknowns summary

| Technical Context item | Resolution |
|------------------------|------------|
| Category taxonomy | D1 — fixed 8-category set in config |
| `when-to-use` source | D2 — derived from description convention |
| Drift-free doc generation | D3 — generator + `--check`, CI-enforced |
| 5-platform hint parity | D4 — `ai-hooks-integration` + single handler |
| Preferences & rate-limit | D5 — `guidance.yml` + machine-local state |
| Availability source | D6 — `services.yml` + deployment mapping |
| Discovery form & search | D7 — `/help` skill, deterministic ranking |

No `NEEDS CLARIFICATION` remain → ready for Phase 1.
