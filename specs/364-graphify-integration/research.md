# Phase 0 Research: Graphify Integration

**Feature**: 364-graphify-integration | **Date**: 2026-06-28

Consolidated findings from parallel research (graphify externals + Manifest integration points). Each decision resolves a Technical Context unknown.

---

## D1 — Graphify packaging, CLI, and prerequisites

**Decision**: Install the CLI with `uv tool install graphifyy` (note the **double-y** PyPI package name; the command/skill trigger is single-y `graphify`). Require Python ≥ 3.10 and `uv`. Default to the local/host-agent path — no API keys, no optional extras — for the baseline integration.

**Rationale**: Confirmed from upstream source (`pyproject.toml`, `graphify/__main__.py`, `graphify/skill.md` via `gh api`):
- PyPI package `graphifyy` v0.9.1, MIT license, `requires-python >= 3.10`.
- Core code extraction is deterministic tree-sitter AST parsing — **no LLM/credentials** required.
- The **default backend is "host-agent"**: when invoked inside an AI assistant, graphify uses the running session as the LLM for non-code semantic extraction. No API key needed for the common case.
- `tree-sitter` + 30+ grammars install automatically as hard deps. Optional extras (`[video]`, `[pdf]`, `[mcp]`, `[neo4j]`, `[gemini]`, `[svg]`, …) are out of baseline scope.

**Alternatives considered**: `pipx install graphifyy` and `pip install graphifyy` work but diverge from the documented `uv tool` path; `uv` also gives isolated, idempotent tool management. Optional backends (Gemini via `GEMINI_API_KEY`, OpenAI, Anthropic headless) are deferred — reused opportunistically when the user already has them configured (D5), never required.

**Unconfirmed**: `ffmpeg` as a hard video prereq is unverified in upstream source; video/audio is out of baseline scope so this does not block.

---

## D2 — CLI install mechanism in bootstrap

**Decision**: Add a `check_uv()` helper and an `install_graphify()` function to `bootstrap/lib/install.sh`, mirroring `install_browser_use()` (lines 742–777) and `install_smoke_deps()` (lines 779–828). Call `install_graphify` from `bootstrap.sh` main (~line 256, after `install_smoke_deps`). Both functions are existence-guarded (Constitution Principle V).

**Rationale**: `uv` is not currently used anywhere in the repo (grep found only a recommendation in `language_profiles.yml`), so it is a genuinely new prerequisite that bootstrap must provision — consistent with how bootstrap already auto-installs Homebrew and Node.js. `install_graphify()` early-returns when `ENABLE_GRAPHIFY=false`, ensures `uv` (installing via brew/apt/dnf/pacman if missing), then `uv tool install graphifyy` **only if `uv tool list` doesn't already list it** — making re-runs no-ops.

**Alternatives considered**: `pip --break-system-packages` (fragile on externally-managed Python); installing `uv` via the upstream curl installer (less consistent with Manifest's package-manager approach). Rejected in favor of package-manager `uv` + `uv tool`.

---

## D3 — Service toggle, ENABLED BY DEFAULT

**Decision**: Wire `graphify` as a **default-enabled** service (opt out via `--disable-graphify`, opt back in via `--enable-graphify`), following the core-assistant pattern (claude/gemini/cursor/codex/antigravity), **not** the opt-in pattern (browser-use/skillclaw). In the `write_services_config()` heredoc use `enabled: $ENABLE_GRAPHIFY` (no `:-false` fallback).

**Rationale**: Per clarification, graphify is enabled by default. The heredoc in `bootstrap/lib/config.sh` (lines 364–481) is the **source of truth** for `~/.claude/config/services.yml`; the committed `configs/claude/config/services.yml` is vestigial/regenerated (known repo gotcha). Default-on services use `enabled: $ENABLE_X`; default-off use `${ENABLE_X:-false}`. The `GRAPHIFY_SET` guard ensures an explicit CLI flag always wins over the persisted file value.

**Touch points** (from research, exact anchors in plan.md): `set_bootstrap_defaults` (`ENABLE_GRAPHIFY=true`, `GRAPHIFY_SET=false`), `print_bootstrap_help`, `parse_bootstrap_args` (two cases), `parse_services_config` (awk section + `FILE_GRAPHIFY` init + case export), `load_existing_config` (SET guard), `write_services_config` (heredoc), `bootstrap.sh` main + reconfigure display.

**Alternatives considered**: Opt-in default (rejected per clarification).

---

## D4 — Graphify is a managed tool, NOT a consensus agent

**Decision**: Do **not** wire graphify into the parallel-agent execution path (`configs/claude/scripts/agents/cli.py` agent gating, `parallel_agent.py`, or `minimum_agents`). The services.yml entry gates **install + skill deployment + health-check reporting only**.

**Rationale**: Graphify is a code-indexing/knowledge-graph tool, not a reasoning LLM agent. Adding it to `cli.py`'s `is_enabled()` agent dict would make `parallel_agent.py` attempt to run it as a review agent and could distort consensus scoring (Constitution Principles II/III). Keeping it out preserves the agent-orchestration contract. `ServiceConfig` already defaults unknown services to enabled, so no runtime gating change is required for graphify; the toggle is consumed by bootstrap (install) and `check_status.sh` (health).

**Alternatives considered**: Full ServiceConfig/cli.py registration (rejected — conflates a tool with an agent).

---

## D5 — Skill delivery: vendored thin wrapper via the source of truth

**Decision**: Author a concise, Manifest-native `/graphify` skill at `.retired skill supply/skills/graphify/SKILL.md` (a thin wrapper that shells the `graphify` CLI and reports if it is not installed). Deploy it through the existing `deploy_home_skills()` pipeline. Do **not** run graphify's own `graphify install`.

**Rationale**: `.retired skill supply/skills/` is the single source of truth; `deploy_home_skills()` copies it to `~/.claude/skills/` and the other assistants' `skills/` dirs symlink back, so one vendored skill reaches Claude/Cursor/Gemini/Codex/Antigravity automatically, and disabled assistants are skipped by their `ENABLE_*` guards. Graphify's own installer would instead write per-assistant skill copies AND patch each assistant's `CLAUDE.md`/`GEMINI.md`/`AGENTS.md` with always-on blocks — bypassing the source of truth, duplicating deployment, and violating Configuration-as-Code (Principle I). Upstream's real `skill.md` is 678 lines + a `references/` sidecar; a thin wrapper matching Manifest skill conventions is lighter to maintain and avoids dragging the sidecar into the repo.

**Collision safety**: `command_catalog.py` raises `CatalogError` on duplicate frontmatter `name`; `name: graphify` is currently unused in `.retired skill supply/skills/`, and the deliberate avoidance of `graphify install` prevents a second `~/.claude/skills/graphify` from appearing (FR-010).

**Disabled-state deployment (consistency fix)**: `deploy_home_skills()` copies the *entire* `.retired skill supply/skills/` tree unconditionally — it is not service-toggle-aware (precedent: the `browser-test` skill deploys even when browser-use is disabled). A vendored graphify skill would therefore deploy even under `--disable-graphify`, contradicting SC-002/FR-012. Because graphify is enabled-by-default the common path is unaffected, but to honor the clean opt-out we add a small deploy-time gate in `bootstrap/lib/deploy.sh` that prunes `~/.claude/skills/graphify` when `ENABLE_GRAPHIFY=false`, leaving the `.retired skill supply/skills/graphify` source intact. Alternative (rejected): relax the spec to "skill always deploys, self-reports when CLI absent" — matches the browser-test precedent but breaks the clarified clean-opt-out promise.

**Alternatives considered**: Vendoring upstream's full `skill.md` + `references/` (heavier, sync burden); using `graphify install` (rejected — bypasses source of truth, patches assistant config files).

---

## D6 — Health-check, docs, and tests

**Decision**: Extend `configs/claude/scripts/check_status.sh` (services.yml parsing ~110–155; CLI detection ~169–238) to report graphify install + (no-op) auth status; update the 7 service-enumerating docs; extend `bootstrap_services.bats`, `check_status.bats`, and `tests/python/agents/test_config.py`.

**Rationale**: Matches the established per-service reporting/doc/test pattern so graphify is verifiable (SC-004) and discoverable (SC-006). Because graphify's default backend needs no credentials, "authenticated" is reported as N/A unless an optional backend key is present.

**Docs to update**: `README.md`, `docs/GETTING_STARTED.md`, `docs/CONFIGURATION.md`, `docs/COMMANDS.md`, root `CLAUDE.md`, `AGENTS.md`, and (capability note) `configs/claude/CLAUDE.md`.

**Alternatives considered**: Skipping tests (rejected — Constitution Development Workflow requires bats/pytest pass; Tier 2 wants coverage).
