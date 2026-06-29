---
description: "Task list for graphify integration"
---

# Tasks: Graphify Integration

**Input**: Design documents from `specs/364-graphify-integration/`

**Prerequisites**: plan.md, spec.md, research.md (D1–D6), data-model.md, contracts/

**Tests**: Included — Constitution Development Workflow requires `bats`/`pytest` to pass, and the spec defines verifiable acceptance/health states.

**Organization**: Grouped by user story (US1 P1 → US2 P2 → US3 P3). MVP = US1.

## Path Conventions

Configuration/deployment repo (no `src/`). Edits land in `bootstrap/`, `bootstrap/lib/`, `.skillshare/skills/`, `configs/claude/`, `docs/`, `tests/`. All paths repo-relative to `/Users/chrismandich/Documents/GitHub/Manifest/.claude/worktrees/graphify/`.

---

## Phase 1: Setup

**Purpose**: Confirm grounding before editing.

- [ ] T001 Re-read research.md decisions D1–D6 and confirm the integration anchors are still valid against current `bootstrap/lib/config.sh` line numbers (they drift); note any offsets before editing.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The default-enabled `graphify` service toggle plumbing. Blocks US1 (install gate reads `ENABLE_GRAPHIFY`) and US3 (health reads `services.yml`). All edits in `bootstrap/lib/config.sh` are sequential (same file).

- [ ] T002 In `bootstrap/lib/config.sh` `set_bootstrap_defaults()`, add `ENABLE_GRAPHIFY=true` (after `ENABLE_ANTIGRAVITY=true`) and `GRAPHIFY_SET=false` (after `ANTIGRAVITY_SET=false`). Default-ON, mirroring core assistants — NOT the browser-use/skillclaw opt-in pattern.
- [ ] T003 In `bootstrap/lib/config.sh` `print_bootstrap_help()`, add `--enable-graphify` (default: enabled) and `--disable-graphify` lines under Service Toggles, after antigravity.
- [ ] T004 In `bootstrap/lib/config.sh` `parse_bootstrap_args()`, add `--enable-graphify` and `--disable-graphify` case blocks (set `ENABLE_GRAPHIFY` + `GRAPHIFY_SET=true`), after the antigravity cases.
- [ ] T005 In `bootstrap/lib/config.sh` `parse_services_config()` awk block, initialize `FILE_GRAPHIFY=""`, add `/^[[:space:]]*graphify:/ { section="graphify" }`, emit `FILE_GRAPHIFY=true|false` in the enabled true/false branches, and add `FILE_GRAPHIFY` to the `FILE_*` export case.
- [ ] T006 In `bootstrap/lib/config.sh` `load_existing_config()`, add the `GRAPHIFY_SET=false && -n "$FILE_GRAPHIFY"` guard that applies `ENABLE_GRAPHIFY=$FILE_GRAPHIFY` (after the antigravity block).
- [ ] T007 In `bootstrap/lib/config.sh` `write_services_config()` heredoc, add the `graphify:` block using `enabled: $ENABLE_GRAPHIFY` (NO `:-false` fallback — default-on), with `command: graphify` and a description. Per contracts/services-yml.md.
- [ ] T008 [P] In `bootstrap.sh`, add graphify to the help comment (Service Toggles), the main enabled-services display (~L204-212), and the `--reconfigure` old→new display (~L126-151), mirroring antigravity.
- [ ] T009 [P] In `configs/claude/config/services.yml` (vestigial parity copy), add the `graphify:` entry matching the heredoc so the committed file stays representative.

**Checkpoint**: `./bootstrap.sh --help` shows the flags; a dry `write_services_config` emits `graphify: enabled: true`.

---

## Phase 3: User Story 1 — Installed & available across assistants (Priority: P1) 🎯 MVP

**Goal**: A standard bootstrap installs the graphify CLI and deploys the `/graphify` skill to every enabled assistant.

**Independent Test**: Run `./bootstrap.sh` on a clean machine → `command -v graphify` works and `~/.claude/skills/graphify/SKILL.md` exists, symlinked into enabled assistants.

- [ ] T010 [US1] Add `check_uv()` to `bootstrap/lib/install.sh` (after `install_smoke_deps`): existence-guarded (`command_exists uv` → return), else install `uv` via brew (macOS) / apt|dnf|yum|pacman (Linux); warn-and-return non-fatally if no supported manager. Mirror Principle V comment style.
- [ ] T011 [US1] Add `install_graphify()` to `bootstrap/lib/install.sh` (mirror `install_browser_use` L742-777 / `install_smoke_deps` L779-828): early-return when `ENABLE_GRAPHIFY=false`; call `check_uv`; existence-guard with `uv tool list | grep -q graphifyy`; else `uv tool install graphifyy`; warn-and-continue on failure (never abort bootstrap).
- [ ] T012 [US1] In `bootstrap.sh` main, call `install_graphify` after `install_smoke_deps` (~L256), inside the same install phase.
- [ ] T013 [US1] Create `.skillshare/skills/graphify/SKILL.md` — thin wrapper per contracts/graphify-skill.md: frontmatter `name: graphify` + one-line description; body = preflight `command -v graphify` (clear "not installed" + install hint, no crash), shell the CLI on the path/URL arg (default `.`), report `graphify-out/` outputs, read-only. Match existing skill prose/`err()` conventions.
- [ ] T014 [US1] Collision guard (FR-010) in `bootstrap/lib/deploy.sh` graphify deploy path — MUST land in the MVP since it fires on the *first* deploy: before deploying, if a pre-existing `~/.claude/skills/graphify` is present that Manifest did not place (e.g. a prior upstream `graphify install`), surface a warning and skip rather than silently clobber it. Same-name duplicates *within* the source tree are already surfaced by `command_catalog.py`'s `CatalogError` — reference that as the in-catalog mechanism. Add a bats case asserting the warn-and-skip path.
- [ ] T015 [P] [US1] Verify `.skillshare/.gitignore` does not exclude `skills/graphify/`; if skillshare-managed markers would ignore it, place a keep-entry OUTSIDE the BEGIN/END markers so the skill stays committed.
- [ ] T016 [P] [US1] Add bats coverage in `tests/bats/bootstrap_services.bats`: `write_services_config` emits `graphify: enabled: true` by default, and `enabled: false` when `ENABLE_GRAPHIFY=false`.

**Checkpoint**: US1 independently testable — graphify CLI + skill present after bootstrap, collision-safe.

---

## Phase 4: User Story 2 — Operators can opt out (Priority: P2)

**Goal**: `--disable-graphify` cleanly removes graphify from the environment and the choice persists.

**Independent Test**: `./bootstrap.sh --disable-graphify` → no install/deploy, no uv, no creds; flag-less re-run stays disabled.

- [ ] T017 [US2] Make graphify skill deployment service-toggle-aware in `bootstrap/lib/deploy.sh` (FR-012/SC-002). `deploy_home_skills()` copies the whole `.skillshare/skills/` tree unconditionally — so the vendored graphify skill would otherwise deploy even when disabled (like `browser-test` regardless of browser-use). When `ENABLE_GRAPHIFY=false`: skip deploying `.skillshare/skills/graphify` AND actively remove a previously-deployed `~/.claude/skills/graphify`, leaving the `.skillshare/skills/graphify` SOURCE intact in the repo. **Cleanup scope**: research confirms every assistant's `skills/` dir is a symlink to `~/.claude/skills` (`link_shared_assets` with `include_skills=true`), so removing the central `~/.claude/skills/graphify` clears all targets; the task MUST also assert no assistant holds an *independent* (non-symlink) `graphify` skill dir and prune it if a future target does (FR-012, "Disable after enable" edge case). Keep `install_graphify` early-returning when disabled. **Add a bats case** (mirroring T014's test-first posture): deploy graphify, then re-run with `ENABLE_GRAPHIFY=false`, and assert `~/.claude/skills/graphify` is removed with no dangling graphify symlinks across assistant targets, while `.skillshare/skills/graphify` stays intact.
- [ ] T018 [US2] Add bats persistence coverage in `tests/bats/bootstrap_services.bats`: with a pre-existing `services.yml` `graphify: enabled: false` and no flag, `load_existing_config` keeps `ENABLE_GRAPHIFY=false` (GRAPHIFY_SET guard); with `--enable-graphify` it flips to true regardless of file.
- [ ] T019 [P] [US2] Add `tests/python/agents/test_config.py` cases: `ServiceConfig` reports graphify enabled-by-default when file missing, and `False` when `services.yml` sets `graphify: enabled: false`. NO source edit to `agents/config.py` needed — `is_enabled()` returns `True` for unrecognized services (config.py:223) and parses YAML dynamically; graphify is intentionally NOT added to the agent-defaults dict (config.py:209–215) so it is never counted as a consensus agent (D4). The tests pin this behavior.

**Checkpoint**: US2 independently testable — opt-out and persistence verified.

---

## Phase 5: User Story 3 — Verify & discover through the system (Priority: P3)

**Goal**: Health-check reports graphify status; docs describe it like every other capability.

**Independent Test**: `check_status.sh` reports graphify enabled + installed/not-installed; docs mention enable/disable/invoke/troubleshoot.

- [ ] T020 [US3] In `configs/claude/scripts/check_status.sh`, add graphify to services.yml parsing + enabled-count + display (~L110-155), and add CLI detection (`command -v graphify`, version in verbose, install hint when missing) in the CLI section (~L169-238). Backend/auth: report host-agent as "no key required" (auth N/A). Detecting an enriched-backend "unauthenticated" state is OUT OF SCOPE (SC-004 deferral — optional backends are out of baseline scope, D1); do not add a credential probe here. Per contracts/health-check.md. Keep reporting non-fatal.
- [ ] T021 [P] [US3] In `.skillshare/skills/health-check/SKILL.md`, add graphify to the CLI Tool Availability list so the `/health-check` skill documents it.
- [ ] T022 [P] [US3] Add bats coverage in `tests/bats/check_status.bats`: extend `write_services_yml` fixture with a graphify arg; assert "Graphify CLI installed" with a mock binary and "not installed" without; update the enabled-services count test for the new service.
- [ ] T023 [P] [US3] Update docs: `README.md` (features/services), `docs/GETTING_STARTED.md` (agents list + install steps), `docs/CONFIGURATION.md` (graphify services.yml block), `docs/COMMANDS.md` (`/graphify` command), root `CLAUDE.md` (services + `--enable/--disable-graphify` flags), `AGENTS.md` (services + flags). Each: what it is, enable/disable, invoke, troubleshoot.
- [ ] T024 [P] [US3] In `configs/claude/CLAUDE.md`, note graphify as a managed capability and explicitly that it is a tool/skill, NOT a parallel-consensus agent (D4) — so it is not added to `parallel_agent.py`/`cli.py` agent gating.

**Checkpoint**: US3 independently testable — verifiable + discoverable.

---

## Phase 6: Polish & Cross-Cutting

- [ ] T025 Run the CI mirror: `shellcheck bootstrap.sh bootstrap/lib/*.sh configs/claude/scripts/check_status.sh`, `yamllint configs/claude/config/services.yml`, `markdownlint` on changed docs, `bats tests/bats/`, `pytest tests/python/`. Fix all findings.
- [ ] T026 Execute quickstart.md sections 2–8 manually (default-on, idempotency, opt-out, health-check, skill-absent message, failure isolation, docs) and confirm each acceptance/SC. **Partial-enable** edge case: verify it is observable through the system's *existing* mechanisms — the `/health-check` (`check_status.sh`) graphify line and the `sync-configs` skill's symlink-integrity report surface graphify's presence/absence per assistant (a missing/unwritable target shows up as a skipped/broken symlink). No bespoke per-target reporting is added; confirm these two surfaces correctly reflect a deliberately-broken target.
- [ ] T027 Constitution Principle II gate: run `parallel_agent.py --review` (and/or `/spec-review`) on the diff for cross-verification (change >200 lines + architectural); record the consensus verdict in the PR description per Principle III thresholds.
- [ ] T028 Verify `configs/claude/skills` is still a symlink to `../../.skillshare/skills` (not replaced by a real dir) and that no graphify edit broke the symlink invariant.

---

## Dependencies & Execution Order

- **Setup (T001)** → **Foundational (T002–T009)** must complete before user stories.
- **Foundational** blocks: US1 install gate (T011 reads `ENABLE_GRAPHIFY`), US3 health (T020 reads `services.yml`).
- **US1 (T010–T016)** = MVP; deliverable on its own and collision-safe (T014).
- **US2 (T017–T019)** depends on Foundational toggle plumbing; its deploy-gate (T017) shares `deploy.sh` with the US1 collision guard (T014) but is a separate behavior.
- **US3 (T020–T024)** depends on Foundational; independent of US1/US2 deliverables.
- **Polish (T025–T028)** last.

## Parallel Opportunities

- Foundational: T008 (bootstrap.sh) and T009 (vestigial services.yml) are `[P]` vs the config.sh chain T002–T007 (different files) — but logically land after the vars exist.
- US1: T015, T016 `[P]` (different files from the install.sh / deploy.sh edits).
- US2: T019 `[P]` (python tests, separate from bats).
- US3: T021, T022, T023, T024 all `[P]` (distinct files: health-check skill, bats, docs set, configs/claude/CLAUDE.md).

## Implementation Strategy

**MVP first**: Foundational + US1 → graphify installs and the `/graphify` skill deploys everywhere, collision-safe. Then layer US2 (opt-out) and US3 (verify + docs). Each story is an independently testable increment.

**Single PR / no partial merge**: "MVP first" is the build/validate *order within this feature branch* — all phases (US1–US3 + Polish) land together before merge; "ship/validate" denotes an internal checkpoint, not a production release. This keeps every invariant true at the merge boundary: the disable deploy-gate (T017, FR-012/SC-002) ships in the same PR, and FR-002 ("no deploy to disabled assistants") is already satisfied during the MVP by the pre-existing per-assistant `ENABLE_*` guards in `deploy.sh` (independent of graphify).
