# Phase 1 Data Model: Graphify Integration

**Feature**: 364-graphify-integration | **Date**: 2026-06-28

This feature is configuration-driven; the "data" is the toggle/config state and the deployable artifacts. No database.

## Entities

### Service toggle: `graphify`

The persisted operator preference, alongside other managed services.

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `ENABLE_GRAPHIFY` | bool (shell) | `true` | Default-enabled (core-service pattern). Set by `--enable-graphify`/`--disable-graphify`. |
| `GRAPHIFY_SET` | bool (shell) | `false` | Guard: true once a CLI flag is given, so the flag wins over `services.yml`. |
| `FILE_GRAPHIFY` | string ("true"/"") | `""` | Parsed from existing `services.yml` by the awk block; must be initialized before awk. |

**State transitions**:
- Fresh run, no flag → `ENABLE_GRAPHIFY=true` (default) → installs + deploys.
- `--disable-graphify` → `ENABLE_GRAPHIFY=false`, `GRAPHIFY_SET=true` → skip install/deploy; clean state (FR-012).
- Re-run, no flag, file says `false` → `load_existing_config` applies `FILE_GRAPHIFY` (since `GRAPHIFY_SET=false`) → honors prior choice (FR-003).
- Re-run, no flag, file says `true` → stays enabled; install is a no-op (idempotent, FR-005).

### `services.yml` record (generated)

Emitted by `write_services_config()` heredoc (source of truth) into `~/.claude/config/services.yml`:

```yaml
  graphify:
    enabled: $ENABLE_GRAPHIFY      # NOT ${...:-false} — default-on
    command: graphify
    description: "AI-powered knowledge-graph generator (/graphify)"
```

Validation: `enabled` ∈ {true,false}; `command` resolvable on PATH when enabled+installed. Consumed by `check_status.sh` (health) and bootstrap (install gate). **Not** consumed by `cli.py` agent gating (D4).

### Graphify capability (runtime state, reported — not stored)

Derived status surfaced by `check_status.sh`:

| Attribute | Values | Source |
|-----------|--------|--------|
| enabled | enabled / disabled | `services.yml` |
| installed | installed / not-installed | `command -v graphify` |
| version | string / unknown | `graphify --version` |
| auth/backend | N/A (host-agent default) / configured (`GEMINI_API_KEY` etc.) | env probe |

Reportable states (SC-004): enabled-and-ready, enabled-but-not-installed, enabled-but-unauthenticated (only when an optional backend is selected).

### Skill artifact: `.skillshare/skills/graphify/SKILL.md`

| Field | Value |
|-------|-------|
| frontmatter `name` | `graphify` (must be unique — collision raises `CatalogError`) |
| frontmatter `description` | one-line trigger description |
| body | thin wrapper: validate args → shell `graphify` → report if CLI missing; read-only |

Deployed by `deploy_home_skills()` → `~/.claude/skills/graphify/` → symlinked into each enabled assistant. Pruned automatically if the source dir is removed.

### Assistant target

An enabled AI assistant (claude/cursor/gemini/codex/antigravity) whose `skills/` symlinks to `~/.claude/skills`. Disabled assistants are skipped by their `ENABLE_*` guard in `deploy.sh` — no graphify skill is placed there (FR-002 negative case).

## Relationships

```
--enable/--disable-graphify ──▶ ENABLE_GRAPHIFY (+GRAPHIFY_SET guard)
        │                              │
        ▼                              ▼
  install_graphify (gate)      write_services_config ──▶ services.yml ──▶ check_status.sh (health)
        │
        ▼
  uv tool install graphifyy ──▶ graphify CLI on PATH
                                       ▲
.skillshare/skills/graphify/SKILL.md ──┘ (shells the CLI)
        │
        ▼ deploy_home_skills()
  ~/.claude/skills/graphify ──▶ {cursor,gemini,codex,antigravity}/skills (symlink, enabled only)
```
