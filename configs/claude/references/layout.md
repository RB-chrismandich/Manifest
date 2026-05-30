# Layout Reference

> Configuration-file map and the `~/.claude/` file tree. Referenced from CLAUDE.md.

## Configuration Files

| File | Purpose |
|------|---------|
| `~/.claude/config/command_config.yml` | Thresholds, tool policies, error recovery |
| `~/.claude/config/validation_criteria.yml` | Tier 1/Tier 2 validation rules with command overrides |
| `~/.claude/prompts/preflight_analysis.md` | Pre-flight analysis template |
| `~/.claude/prompts/synthesis.md` | Agent disagreement synthesis template |
| `~/.claude/prompts/validation.md` | Validation criteria template |

## File Structure

```text
~/.claude/
├── CLAUDE.md                        # This orchestration guide
├── skills/                          # Skill library (28; source: .skillshare/skills/)
│   ├── checkpoint/SKILL.md
│   ├── code-quality/SKILL.md       # Auto-triggered quality/security
│   ├── docs-diagrams/SKILL.md
│   ├── docs-improve/SKILL.md
│   ├── docs-readme/SKILL.md
│   ├── health-check/SKILL.md
│   ├── issue-prioritize/SKILL.md
│   ├── issue-triage/SKILL.md
│   ├── plan-manage/SKILL.md
│   ├── project-commit/SKILL.md
│   ├── refactor-python/SKILL.md
│   ├── refactor-shell/SKILL.md
│   └── sync-configs/SKILL.md
├── prompts/
│   ├── context_monitor.md
│   ├── preflight_analysis.md
│   ├── synthesis.md
│   ├── triage_synthesis.md
│   └── validation.md
├── config/
│   ├── command_config.yml
│   ├── linear_triage.yml
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
    ├── parallel_agent.py            # Main parallel agent orchestrator
    ├── parallel_agent.py            # Python parallel agent (Phase 3)
    ├── generate_cursor_rules.sh     # Regenerate .cursor/rules from SKILL.md
    ├── git_platform.sh              # Platform detection
    ├── git_ops.sh                   # Platform-agnostic Git operations
    └── linear_ops.sh                # Linear API operations
```
