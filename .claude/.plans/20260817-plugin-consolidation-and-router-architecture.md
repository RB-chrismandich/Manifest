# Implementation Plan: Manifest Plugin Consolidation & Multi-Harness Architecture

## Summary & Consensus Goals

Consolidate fragmented domain plugins (`adversarial-design-loop` -> `stitch-design`, `manifest-docker` ->
`manifest-ops`) into clean domain bundles, maintain strict multi-harness parity, and ensure 100% test and generator
verification.

---

## Phase 1: Domain Bundle Consolidation

### 1. Merge `adversarial-design-loop` into `stitch-design`

* **Skills moved**: `design-loop`, `loop-scaffold`, `render-verify`, `review-round`, `screen-prompts`, `spec-amend` ->
  `plugins/stitch-design/skills/`.
* **Agents moved**: `design-lens-reviewer.md`, `skeptic-verifier.md` -> `plugins/stitch-design/agents/`.
* **Subagent References**: Grep and update internal invocations in `skills/review-round/SKILL.md` and references (e.g.
  change `adversarial-design-loop:design-lens-reviewer` -> `stitch-design:design-lens-reviewer` and
  `adversarial-design-loop:skeptic-verifier` -> `stitch-design:skeptic-verifier`).
* **Update `plugins/stitch-design/manifest-capabilities.yml`**:
  * Add the 6 skills to `components.skills` / discovered set.
  * Add the 2 agents to `components.agents`.
* **Update `src/manifest_agent/contracts.py`**:
  * Remove the dead `adversarial-design-loop` exclusion branch (lines 350-353).
* **Update `.claude-plugin/marketplace.json`**:
  * Remove `adversarial-design-loop` entry.
* **Remove orphan directory**: Delete `plugins/adversarial-design-loop`.

### 2. Merge `manifest-docker` into `manifest-ops`

* **Skills moved**: `docker-compose-commandments` -> `plugins/manifest-ops/skills/`.
* **Hooks moved**: `compose_commandments_hook.py` -> `plugins/manifest-ops/hooks/`.
* **Scripts/Configs moved**: `compose_check.py`, `compose_rules.py`, `compose_model.py`, `compose_commandments.yml` ->
  `plugins/manifest-ops/runtime/` and `plugins/manifest-ops/config/`.
* **Update `plugins/manifest-ops/manifest-capabilities.yml`**:
  * Add `docker-compose-commandments` skill.
  * Add `compose-commandments` hook and its runtime components with full multi-harness compatibility declarations
    (Claude/Cursor native, Codex/Gemini/Antigravity/Devin degraded).
* **Update `configs/claude/config/skill_policies.yml`**:
  * Remove `manifest-docker` from `independent_addons`.
  * Update `domain_expected_total`, `independent_addon_expected_total`, and `expected_total` integer counters
    atomically.
* **Update `.claude-plugin/marketplace.json`**:
  * Remove `manifest-docker` entry.
* **Remove orphan directory**: Delete `plugins/manifest-docker`.

### 3. Test & Fixture Updates (8-File Checklist)

Audit and update all test fixtures and assertions that check bundle counts and names:

1. `tests/python/manifest_agent/test_catalog.py`
2. `tests/python/manifest_agent/test_adapter_claude.py`
3. `tests/python/manifest_agent/_codex_adapter_test_support.py`
4. `tests/python/manifest_agent/test_manifest_release_workflow.py`
5. `tests/python/manifest_agent/test_codex_uninstall.py`
6. `tests/python/manifest_agent/test_generate_plugin_views.py`
7. `tests/python/manifest_agent/test_build_manifest_release.py`
8. `tests/python/manifest_agent/test_codex_reconcile.py`

### 4. Regenerate Views, Docs & Rules

Run all repo code and doc generators and verify clean git status:

* `python3 tools/generate_plugin_views.py` (regenerate all extension manifests)
* `python3 tools/render_plugin_capability_matrix.py` (regenerate `docs/PLUGIN_CAPABILITY_MATRIX.md`)
* `python3 configs/claude/scripts/generate_commands_doc.py` (regenerate `docs/COMMANDS.md` and injected command indexes
  in `CLAUDE.md`, `GEMINI.md`, `AGENTS.md`)
* `./configs/cursor/scripts/generate_cursor_rules.sh` (regenerate cursor rules)

---

## Phase 2: Compound Router Skills (Scoped Follow-up)

1. Add `/refactor` dispatcher in `manifest-code-quality` delegating to language sub-engines.
2. Add `/pr` router in `manifest-forge` for PR lifecycle actions.
3. Add `/issue` router in `manifest-forge` for Issue actions.
4. Add `/shell-audit` router in `manifest-code-quality`.
5. Verify `skill_reference_check.py` ratchet and `command_catalog.py` frontmatter character budgets prior to landing.

---

## Phase 1 Acceptance Criteria

* [ ] `uv run pytest tests/python/plugin_runtime/` passes 100%.
* [ ] `uv run pytest tests/python/manifest_agent/` passes 100%.
* [ ] `python3 tools/generate_plugin_views.py --check` passes with zero drift.
* [ ] No broken `subagent_type` or skill references exist across plugins.
* [ ] Claude & Antigravity reach unanimous consensus on Phase 1 delivery.
