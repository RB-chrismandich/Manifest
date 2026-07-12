# Cursor ↔ Claude Feature Parity — Design Spec

**Date**: 2026-07-11
**Branch**: `feat/cursor-feature-parity`
**Status**: DRAFT (reference for develop→challenge consensus)
**Author**: orchestrator (audit synthesis)

---

## 1. Goal

Bring the **Cursor** deployment configuration (`configs/cursor/` → `~/.cursor/`)
to **complete feature parity** with the **Claude** deployment
(`configs/claude/` → `~/.claude/`). Claude is the reference/source-of-truth
model; Cursor is the target that must receive the features it currently lacks.

Parity means: **every Claude capability for which Cursor has a *verified*
config-file mechanism is provisioned for Cursor and kept in sync (drift-gated).**
Capabilities that are structurally GUI-only in Cursor are documented as
intentional non-parity, not silently dropped.

## 2. Verified Cursor capability model (as of Cursor 2.x, 2026)

Confirmed against `cursor.com/docs` (hooks, subagents, rules, mcp):

| Claude feature | Cursor mechanism | Cursor reads from | Parity achievable? |
|---|---|---|---|
| MCP servers | `mcp.json` (url/stdio schema) | `~/.cursor/mcp.json`, `.cursor/mcp.json` | **Yes** |
| Lifecycle hooks | `hooks.json` (superset of Claude events; exit 2 = deny; `CLAUDE_PROJECT_DIR` alias provided) | `~/.cursor/hooks.json`, `.cursor/hooks.json` | **Yes** |
| Sub-agents | agent md + YAML frontmatter (`name`, `description`, `model`=inherit, `readonly`, `is_background`) | `~/.cursor/agents/` **and `~/.claude/agents/` natively** | **Yes** |
| Skills | `SKILL.md` folders; also reads `.claude/skills/` back-compat | `~/.cursor/skills/`, `~/.claude/skills/` | Yes (already symlinked) |
| Slash commands | `commands/*.md` (no frontmatter) | `~/.cursor/commands/*.md` | Yes (lower priority) |
| Orchestration guide | project rule / AGENTS.md | `.cursor/rules/*.mdc`, `AGENTS.md` | Yes (content parity) |
| Project rules | `.mdc` | `.cursor/rules/` (project) | Yes |
| **User-global rules on disk** | — (User Rules are GUI-stored) | **no `~/.cursor/rules/` load** | **No — structural** |
| Declarative permissions allowlist | — (hooks + GUI allowlist) | — | Partial via hooks only |
| Author-controlled memory file | — (auto-managed Memories) | — | No — structural |

## 3. Audit findings (current state)

Source-of-truth = `configs/claude/`. Cursor deploy = `deploy_cursor_configs()`
(`bootstrap/lib/deploy.sh:267-304`): copies `rules/*.mdc` + `mcp.json`, symlinks
`scripts/config/prompts/.plans/skills` → `~/.claude/*`.

1. **MCP drift** — `configs/cursor/mcp.json` is a **hand-maintained static file**
   with 3 of 9 registry servers (sentry, context7, linear). Missing: deepwiki,
   glean, google-dev-docs, atlassian, opentofu, apify. All 9 registry servers
   (`configs/claude/config/mcp_servers.yml`) are remote-`url` HTTP → all
   Cursor-eligible. The deployed `~/.cursor/mcp.json` CAN be regenerated from the
   registry (`configure_cursor_mcp_config`, `bootstrap/lib/mcp.sh:222-257`) during
   `--install-mcp`, but the **committed repo file is never regenerated** → drift.
2. **Orchestration guide content drift** — `configs/cursor/rules/orchestration.mdc`
   (hand-maintained, `<!-- Adapted from: .claude/CLAUDE.md -->`, no drift guard)
   is missing substantive `CLAUDE.md` content:
   - **Reference Index** (`CLAUDE.md:54-67`) — 5 of 7 reference docs are invisible
     to Cursor (`parallel-agent.md`, `git-platform.md`, `layout.md`,
     `sub-agent-dispatch.md`, `spec-artifact-discovery.md`).
   - Graphify managed-tool paragraph (`CLAUDE.md:125-129`).
   - `sync-skills` CLI note (`CLAUDE.md:131-132`).
   - "CONSIDER Parallel Agents For" tier (`CLAUDE.md:89-91`).
   - code-audit auto-trigger thresholds (`CLAUDE.md:134-138`).
   - `/token-conserve` re-assert note (`CLAUDE.md:18`).
   (Note: `orchestration.mdc` is *also* a superset in other areas — Model
   Selection, Cross-Verification, Available Rules table — which must be preserved,
   so full regeneration is unsafe; port the missing items + add a presence guard.)
3. **Stale rule pruning (open issue #505)** — orphan `.mdc` are never removed:
   `generate_cursor_rules.sh` is create/update-only (no prune), deploy uses
   `cp` without `--delete` (`deploy.sh:290`), and `reconcile_core.py:12-18`
   explicitly excludes `rules/*.mdc`. A renamed/removed skill leaves a dangling
   rule in both repo and `~/.cursor/rules/`.
4. **Hooks not provisioned** — Claude defines 5 hooks in
   `configs/claude/settings.local.json:37-97` (PreToolUse `guidance_hint.py`;
   PostToolUse `version_pin_hook.sh` / `spec_review.sh` / `lint_on_edit_hook.sh`;
   SessionStart `deploy_stamp_check.sh`; UserPromptSubmit echo). Cursor gets none,
   despite supporting a superset hook system.
5. **Agents not provisioned for Cursor** — 6 pilotfish role-agents
   (`configs/claude/agents/*.md`, opt-in `--enable-pilotfish`) deploy to
   `~/.claude/agents` only (spec 481 **FR-013**, decided *before* Cursor shipped
   subagents; the spec explicitly anticipates "the role/tier idea may be formalized
   for [other homes] in a later feature"). Cursor 2.x reads `~/.claude/agents/`
   natively AND `~/.cursor/agents/`, so parity is now achievable.

**In sync already (no action):** 89/89 skills↔rules, byte-identical descriptions,
CI drift gate (`ci.yml:343-356`) + bats (`generate_cursor_rules.bats`). Shared
assets symlinked. Skill bundled assets reachable via `~/.cursor/skills`.

## 4. In-scope work (parity closures)

Each workstream lists the change and **acceptance criteria** the challengers
validate against.

### WS-1 — MCP parity (generate `mcp.json` from the registry)

- **Change**: Add a generator that writes `configs/cursor/mcp.json` from
  `configs/claude/config/mcp_servers.yml` (all `url` servers, Cursor remote
  schema `{ "mcpServers": { "<name>": { "url": "<url>" } } }`). Fold invocation
  into `generate_cursor_rules.sh` (guarded on `python3`+`pyyaml`, mirroring the
  `commands-index.mdc` path) OR a dedicated `generate_cursor_mcp.py` invoked by it.
- **Gate**: extend the CI "Cursor rules up-to-date" step to also fail on
  `git status --porcelain configs/cursor/mcp.json`; add a bats test.
- **Acceptance**: regenerating leaves the tree git-clean; `mcp.json` contains all
  9 registry servers with correct URLs; deterministic/idempotent; `--dry-run`
  writes nothing; no other platform config is modified.

### WS-2 — Orchestration guide content parity

- **Change**: Port the 6 missing items (§3.2) into
  `configs/cursor/rules/orchestration.mdc`, adapted to Cursor voice, preserving
  all existing superset content. Add a bats **presence guard** asserting each
  ported section/reference token exists (so future `CLAUDE.md` edits can't
  silently desync). Must stay within the `context_budget.bats` size budget for
  `orchestration.mdc`.
- **Acceptance**: all 6 items present; existing superset content intact; size
  budget green; guard test fails if any item is removed.

### WS-3 — Stale rule pruning (closes #505)

- **Change**: (a) `generate_cursor_rules.sh` prunes orphan
  `configs/cursor/rules/*.mdc` (any `<name>.mdc` with no
  `configs/claude/skills/<name>/`, excluding `orchestration.mdc`,
  `commands-index.mdc`), with `--dry-run` reporting "would remove". (b) Cursor
  deploy prunes orphans in `~/.cursor/rules/` (manifest-tracked prune mirroring
  `deploy_home_skills` `common.sh:144-171`, or `rsync --delete` scoped to rules;
  must NOT delete user-authored files or `orchestration`/`commands-index`).
- **Acceptance**: renaming a skill removes its old rule from repo + home on
  regen/deploy; user files untouched; bats coverage for orphan removal +
  dry-run; idempotent.

### WS-4 — Hooks parity

- **Change**: Provision `configs/cursor/hooks.json` mapping Claude hooks →
  Cursor events (`preToolUse`, `postToolUse`, `afterFileEdit`, `sessionStart`,
  `beforeSubmitPrompt`), reusing the scripts already reachable via
  `~/.cursor/scripts` and the `CLAUDE_PROJECT_DIR` alias. Wire a copy step into
  `deploy_cursor_configs()`.
- **CORRECTNESS REQUIREMENT (load-bearing)**: Cursor's hook **stdin/JSON input
  contract differs from Claude's**. Before wiring any script as a Cursor hook,
  the developer MUST verify (against `cursor.com/docs/hooks`) that the script
  behaves correctly under Cursor's input, or add a thin Cursor-compatible adapter.
  A hook that only produces side effects (format/lint/notify) and ignores stdin
  is safe; a hook that parses Claude's stdin schema is NOT safe to reuse verbatim.
  Any hook that cannot be made correct is **excluded with a documented reason**
  rather than shipped broken. **No silent failures.**
- **Acceptance**: `hooks.json` is valid against the documented schema; every
  wired hook is demonstrably correct under Cursor's input contract (or excluded
  with rationale); deploy copies it under the `ENABLE_CURSOR` gate; bats validates
  schema + deploy.

### WS-5 — Agents parity

- **Change**: Provision Cursor-readable agent definitions for the 6 role-agents.
  Preferred: generate `configs/cursor/agents/*.md` with **Cursor-native
  frontmatter** (`name`, `description`, `model`, `readonly`, `is_background`;
  drop Claude-only `effort`; map model aliases to Cursor-acceptable values or
  `inherit`), deployed under the **same `--enable-pilotfish` toggle** and gate
  logic (`gate_pilotfish_agents`), with the same manifest-owned prune semantics.
  Update the FR-013 note / `README.md` / pilotfish docs to record that Cursor is
  now a provisioned target (the "later feature" FR-013 anticipated).
- **Acceptance**: with pilotfish enabled, cursor agents deploy to
  `~/.cursor/agents`; disabling prunes only manifest-owned files (user agents
  survive); frontmatter is valid Cursor schema; docs updated; bats coverage
  mirrors the Claude pilotfish gate tests.

### WS-6 — Derived files, docs, gates

- Regenerate all derived artifacts (cursor rules, `commands-index.mdc`,
  `COMMANDS.md`, `GEMINI.md`, `AGENTS.md` as applicable) and run the **real**
  pre-commit (`--from-ref origin/main`) so no derived-file/drift gate
  (`ci_mirror_drift`, `commands_doc_drift`, `context_budget`,
  `generate_cursor_rules`) is red.
- Update `config-audit` skill check #4 to flag `mcp.json` servers **missing**
  vs the registry (currently only checks the present 3 "match canonical").
- Update `.pre-commit-config.yaml` to run `generate_cursor_rules.sh --dry-run`
  (fail on drift) so cursor drift is caught locally, not just in CI.

## 5. Out of scope / intentional non-parity (documented, not dropped)

- **User-global always-on rules on disk** — Cursor User Rules are GUI-stored;
  no `~/.cursor/rules/` load. Structural. (See §6 critical flag.)
- **Declarative permissions allowlist** — Cursor has no settings-file allowlist;
  partial functional equivalent is the hook `beforeShellExecution` + `failClosed`
  (WS-4 provides the mechanism; a full permission port is not attempted here).
- **Author-controlled memory file** — Cursor Memories are auto-managed.
- **Custom modes** — GUI-only, not deployable via config.
- **UserPromptSubmit `/token-conserve` echo hook** (WS-4) — Claude's
  `UserPromptSubmit` hook stdout is injected into context; Cursor's nearest
  analog, `beforeSubmitPrompt`, takes `{prompt, attachments}` as input but its
  **output contract for injecting context back is not in the verified fact
  set** for this session (only the input shape was confirmed against
  `cursor.com/docs`). Shipping the plain `echo '...'` verbatim risks either
  silent inertness (Cursor ignores non-JSON stdout) or, worse, an unverified
  guess at the wrong JSON field. Excluded rather than shipped-broken, per the
  WS-4 correctness requirement; a follow-up should confirm the exact
  `beforeSubmitPrompt` output schema before wiring this one hook.
- **Advisory-stdout surfacing of the WIRED hints (WS-4)** — the two hooks that
  emit an advisory line to stdout, `guidance_hint.py` (`beforeShellExecution`)
  and `deploy_stamp_check.sh` (`sessionStart`), are wired because they are
  **input-correct and fail-open** (they exit 0 and never block), but whether
  Cursor actually surfaces their *non-JSON* advisory stdout to the user the way
  Claude renders PreToolUse/SessionStart output is **unverified** — the same
  output-contract gap that gated the echo exclusion above. So their advisory
  output (guidance_hint's git-command hint, deploy_stamp_check's stamp-drift
  warning) is safe regardless,
  but their user-visible *hint text* is best-effort and possibly inert pending
  that `beforeSubmitPrompt`/output-contract verification. This is a
  surfacing caveat, not a correctness risk: nothing breaks if the hint is
  swallowed.
- **`~/.cursor/CLAUDE.md` pilotfish-pointer edge (WS-5, known limitation — not
  guarded by design)** — `gate_pilotfish_agents` derives its guide path as
  `guide="$home/CLAUDE.md"`; for the Cursor home that is `~/.cursor/CLAUDE.md`,
  which the Cursor deploy never creates, so the pointer inject/remove is a pure
  no-op there (grep-guarded on a non-existent file). The only exposure: if a
  user *hand-authors* `~/.cursor/CLAUDE.md` containing a `## Reference Index` /
  `antipatterns.md` anchor, enabling pilotfish would inject a `~/.claude`-pathed
  delegation-pointer line into it (and cleanly remove it on disable — the edit
  is reversible). We **deliberately do NOT add a Cursor-specific guard** to the
  shared `gate_pilotfish_agents`/`common.sh`: that helper is Claude-critical
  machinery, and a speculative guard on it carries more regression risk than
  this narrow, self-cleaning, user-self-inflicted edge is worth (repo guardrail:
  "no speculative guards"). Documented here as a known reversible limitation
  instead.

## 6. ⚠️ CRITICAL FLAG (separate issue — NOT fixed this session)

`cursor.com/docs/rules` states User Rules are GUI-stored and documents **no
user-global `~/.cursor/rules/` on-disk load**. The repo deploys 91 `.mdc` files
to `~/.cursor/rules/`. If the Cursor **IDE** does not read that directory, the
entire home-level rules deployment may be inert (project `.cursor/rules` and
`AGENTS.md` are the documented load paths; the Cursor **CLI** behavior for
`~/.cursor/rules` is unconfirmed).

This is a potential **pre-existing architecture defect**, orthogonal to the
parity *delta*, and too large/risky to remediate in this session. **Action**:
file a dedicated issue to verify Cursor CLI vs IDE loading of `~/.cursor/rules`
and decide the delivery mechanism (project-level rules, `AGENTS.md`, or User
Rules import). Do not change the rules delivery mechanism here.

## 7. Execution model (per the session goal)

- **1 developer** (model: `sonnet`, elite process-oriented): implements each
  workstream on the shared `feat/cursor-feature-parity` worktree. Develops only.
- **2 challengers** (independent, adversarial): critique **every** change,
  validate design intent, alignment to functionality, and alignment to THIS spec.
  Challenge only — they do not edit code.
- **Consensus gate**: a workstream is done only when **both** challengers
  APPROVE. The overall goal is met only when both challengers approve the whole
  system AND all §8 gates pass. Strict role separation: developer never
  challenges; challengers never develop.

## 8. Verification gates (must all pass before "complete")

- `bash configs/claude/scripts/generate_cursor_rules.sh` → tree git-clean
  (rules + `mcp.json`).
- `bats tests/bats/` (incl. new WS tests) green.
- `pytest tests/python/` green (reconcile/config/commands-doc touched areas).
- `shellcheck` on changed shell; `yamllint` on changed YAML; JSON validates.
- Real pre-commit `--from-ref origin/main` clean (no derived-file drift).
- `context_budget.bats` green (orchestration.mdc within budget).

## 9. Risks

- **R1 (hooks stdin contract)** — reusing Claude hook scripts under Cursor's
  different input schema. Mitigation: WS-4 correctness requirement + per-hook
  verification; exclude-with-reason over ship-broken.
- **R2 (FR-013 reversal)** — provisioning cursor agents changes a shipped
  decision. Mitigation: same toggle/gate/prune semantics, docs updated, no change
  to Claude behavior.
- **R3 (drift gates)** — new generated artifacts (`mcp.json`) must be gated or
  they re-drift. Mitigation: CI + pre-commit + bats per WS.
- **R4 (rules-load flag §6)** — if `~/.cursor/rules` is inert, rules-based parity
  is moot at home scope; hooks/agents/mcp (home-read) remain valuable regardless.
  Mitigation: flagged as separate issue; parity work prioritizes home-read
  surfaces.
</content>
</invoke>
