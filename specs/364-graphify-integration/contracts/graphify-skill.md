# Contract: `/graphify` Skill

**Surface**: `.skillshare/skills/graphify/SKILL.md` (vendored, Manifest-native thin wrapper). Deployed by `deploy_home_skills()` to every enabled assistant.

## Frontmatter

```yaml
---
name: graphify
description: <one line — when to invoke: map a codebase/dir into a queryable knowledge graph via the graphify CLI>
---
```

- `name` MUST be `graphify` and MUST be unique across `.skillshare/skills/` (duplicate → `command_catalog.py` `CatalogError`, rejecting both).

## Body behavior

1. **Preflight**: check `command -v graphify`; if missing, report clearly with the install hint (`uv tool install graphifyy` / `./bootstrap.sh --enable-graphify`) and stop — do not error out.
2. **Invoke**: shell the `graphify` CLI on the requested path/URL (default: current directory), passing through user-supplied options.
3. **Report**: surface graphify's outputs (`graphify-out/GRAPH_REPORT.md`, `graph.json`, `graph.html`) location; read-only — never modify source files.

## Guarantees

- The skill is a thin wrapper over the upstream CLI — Manifest does not reimplement graph generation (graphify internals are a black box).
- Manifest does NOT run `graphify install`; the skill is delivered solely via the `.skillshare/skills/` pipeline (no patching of assistant `CLAUDE.md`/`GEMINI.md`).
- Deploys to claude/cursor/gemini/codex/antigravity when enabled; skipped for disabled assistants.

## Acceptance

- After bootstrap, `/help graphify` lists the skill and `~/.claude/skills/graphify/SKILL.md` exists (US1-AC1).
- Invoking `/graphify` with the CLI absent yields a clear "not installed" message, not a crash (FR-011/edge case).
