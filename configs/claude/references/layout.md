# Layout Reference

> Configuration-file map and the `~/.claude/` file tree. Referenced from CLAUDE.md.

## Configuration Files

| File | Purpose |
|------|---------|
| `~/.claude/config/command_config.yml` | Thresholds, tool policies, error recovery |
| `~/.claude/config/validation_criteria.yml` | Tier 1/Tier 2 validation rules with command overrides |
| `~/.claude/prompts/preflight_analysis.md` | Pre-flight analysis template |
| `~/.claude/prompts/synthesis.md` | Agent disagreement synthesis template |
| `~/.claude/prompts/skillclaw_evolve.md` | SkillClaw evolve prompt (script-consumed) |
| `~/.claude/prompts/spec_review.md` | Spec review template (script-consumed) |
| `~/.claude/prompts/spec_review_merge.md` | Spec review merge template (script-consumed) |
| `~/.claude/prompts/validation.md` | Validation criteria template |

## File Structure

```text
~/.claude/
├── CLAUDE.md                        # This orchestration guide
├── skills/                          # Skill library (28; source: .retired skill supply/skills/)
│   ├── checkpoint/SKILL.md
│   ├── code-audit/SKILL.md       # Auto-triggered quality/security
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
│   ├── synthesis.md
│   └── validation.md
├── config/
│   ├── command_config.yml
│   ├── tracker_triage.yml
│   ├── mcp_servers.yml
│   ├── parallel_agent.yml           # Canonical model tiers source
│   ├── services.yml
│   └── validation_criteria.yml
├── .plans/                          # Plan management
│   ├── .archive/                    # Completed plans
│   ├── .abandoned/                  # Stale/abandoned plans
│   ├── TEMPLATE.md
│   └── README.md
└── scripts/
    ├── parallel_agent.py            # Parallel agent orchestrator (Python)
    ├── generate_cursor_rules.sh     # Regenerate .cursor/rules from SKILL.md
    ├── git_platform.sh              # Platform detection
    ├── git_ops.sh                   # Platform-agnostic Git operations
    └── linear_ops.sh                # Linear API operations
```
