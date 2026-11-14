# Layout Reference

> Configuration-file map and current harness deployment paths. Referenced from `CLAUDE.md`.

## Configuration Files

| File | Purpose |
|------|---------|
| `~/.claude/config/command_config.yml` | OMP dispatch policies, thresholds, and error recovery |
| `~/.claude/config/model_policy.yml` | Provider order, model tiers, CLI routes, and fallback for single-provider tools |
| `~/.claude/config/validation_criteria.yml` | Tier 1/Tier 2 validation rules with command overrides |
| `~/.claude/prompts/preflight_analysis.md` | Pre-flight analysis template |
| `~/.claude/prompts/skillclaw_evolve.md` | SkillClaw evolve prompt (script-consumed) |
| `~/.claude/prompts/spec_review.md` | Spec review template (script-consumed) |
| `~/.claude/prompts/validation.md` | Validation criteria template |

## File Structure

```text
~/.claude/
├── CLAUDE.md                        # Claude-specific orchestration guide
├── plugins/                         # Native plugin-manager state
├── config/                           # Shared Manifest configuration
├── prompts/                          # Prompt templates
├── .plans/                           # Plan management
└── scripts/                          # Shared scripts and CLI entry points
```

## Bootstrap Options

Bootstrap is the supported installation and deployment path. Supported hosts:
macOS (Intel and Apple Silicon) and Linux (Debian/Ubuntu, RHEL/Fedora, Arch,
openSUSE).

```bash
./bootstrap.sh
./bootstrap.sh --disable-cursor
./bootstrap.sh --disable-codex --disable-cursor
./bootstrap.sh --skip-auth --force
./bootstrap.sh --install-mcp
```

Service and optional-feature switches:

```text
--enable-claude / --disable-claude
--enable-cursor / --disable-cursor
--enable-codex / --disable-codex
--enable-antigravity / --disable-antigravity
--enable-devin / --disable-devin
--enable-skillclaw / --disable-skillclaw
--enable-browser-use / --disable-browser-use
--enable-smoke / --disable-smoke
--enable-gh / --disable-gh
--enable-glab / --disable-glab
--install-mcp
```

Install each harness CLI using its current vendor-supported method; these
switches configure deployment and do not install every external CLI.

## Skill and Harness Deployment

The canonical skills are maintained under `plugins/<bundle>/skills/`.
`.apm/skills/` is a generated mirror; it is not the canonical source.

| Harness | Deployment and skill path |
|---|---|
| Claude Code | Manifest bundles use Claude's native plugin manager; the flat catalog is not installed under `~/.claude/skills/` after cutover. |
| Cursor | Per-skill rules are generated under `~/.cursor/rules/`; its flat skill fallback points to `~/.manifest/skills/`. |
| Codex | `~/.codex/AGENTS.md` is deployed separately; bundles use Codex's native plugin mechanism. A safe legacy flat-catalog fallback may link `~/.codex/skills/` to `~/.manifest/skills/`. |
| Antigravity | `~/.antigravity/skills/` links to `~/.manifest/skills/`; shared config and plans link to `~/.claude/`. The `agy` CLI reads its guide from `~/.gemini/GEMINI.md`. |
| Devin | Bootstrap configures `read_config_from.claude`; Devin reads the Claude skills and guide directly rather than receiving a duplicate skills link. |

Use `./bootstrap.sh` for deployment. Manual copies or blanket symlinks can
conflict with native plugin installation, generated rules, or user-managed
state; inspect `bootstrap/lib/deploy.sh` before attempting a manual equivalent.
