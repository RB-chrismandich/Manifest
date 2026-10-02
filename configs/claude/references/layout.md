# Layout Reference

> Configuration-file map and the `~/.claude/` file tree. Referenced from CLAUDE.md.

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
├── CLAUDE.md                        # This orchestration guide
├── skills/                          # Plugin skill library (source: .apm/skills/)
│   ├── code-audit/SKILL.md          # Auto-triggered quality/security
│   ├── docs-generate-diagrams/SKILL.md
│   ├── docs-improve/SKILL.md
│   ├── docs-improve-readme/SKILL.md
│   ├── env-check/SKILL.md
│   ├── issue-prioritize/SKILL.md
│   ├── issue-triage/SKILL.md
│   ├── plan-manage/SKILL.md
│   ├── git-commit/SKILL.md
│   ├── python-refactor/SKILL.md
│   ├── shell-refactor/SKILL.md
│   └── config-audit/SKILL.md
├── prompts/
│   ├── context_monitor.md
│   ├── preflight_analysis.md
│   └── validation.md
├── config/
│   ├── command_config.yml
│   ├── model_policy.yml             # Single-provider model and CLI policy
│   ├── tracker_triage.yml
│   ├── mcp_servers.yml
│   ├── services.yml
│   └── validation_criteria.yml
├── .plans/                          # Plan management
│   ├── .archive/                    # Completed plans
│   ├── .abandoned/                  # Stale/abandoned plans
│   ├── TEMPLATE.md
│   └── README.md
└── scripts/
    ├── manifest_cli/                # `manifest` command router
    ├── manifest_model_policy/       # Policy loader and headless CLI helpers
    ├── generate_cursor_rules.sh     # Regenerate .cursor/rules from SKILL.md
    ├── git_platform.sh              # Platform detection
    ├── git_ops.sh                   # Platform-agnostic Git operations
    └── linear_ops.sh                # Linear API operations
```
