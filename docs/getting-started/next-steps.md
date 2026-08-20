# Next Steps

> Where to go once the basics work.

**Last Updated**: 2026-08-20

## Next Steps

### For Regular Use

1. **Integrate with Claude Code**: Commands are available as `/python-refactor`, `/docs-generate-diagrams`, etc.
2. **Review Configuration**: Read [Configuration Guide](../configuration/README.md) to customize behavior
3. **Learn Architecture**: View [Architecture Diagrams](../diagrams/README.md) to understand data flows

### For Troubleshooting

If you encounter issues:

1. Check [Troubleshooting Guide](../troubleshooting/README.md)
2. Verify service configuration: `cat ~/.claude/config/services.yml`
3. Test individual agents: `~/.claude/scripts/parallel_agent.py --claude-only "test"`

### For Advanced Usage

- **Custom Skills**: Create new slash commands in `.apm/skills/` (exposed via `configs/claude/skills/`)
- **Validation Rules**: Customize security/quality checks in `configs/claude/config/validation_criteria.yml`
- **Model Fallbacks**: Configure credit exhaustion fallback chains
- **Environment Variables**: Override defaults with `CURSOR_MODEL_ADVANCED`, `GEMINI_INCLUDE_DIRS`, etc.
- **SkillClaw (opt-in)**: Capture agent sessions and evolve skills locally — enable with
  `./bootstrap.sh --enable-skillclaw`. See [docs/SKILLCLAW.md](../SKILLCLAW.md) for details.
- **pilotfish (opt-in)**: Cost-tiered role-agents that delegate mechanical/read-only work to
  cheaper model tiers and gate results behind a verifier — enable with
  `./bootstrap.sh --enable-pilotfish` (Claude-only; does not change your main-session model).
- **devpanel (opt-in)**: Critic-gated developer/debugger/tester role-agents, gated by two shared
  adversarial validators (spec-guard, chaos-engineer) in a propose → critique → refactor loop —
  enable with `./bootstrap.sh --enable-devpanel` (Claude-only; independent of pilotfish, may be
  enabled alongside it; does not change your main-session model).

**See**: [Configuration Guide](../configuration/README.md) for advanced topics

### Using Manifest with emdash

[emdash](https://github.com/generalaction/emdash) is a desktop **harness** — not a
Manifest deploy target — that launches your agent CLIs in parallel git worktrees
using your real `HOME`. A Manifest-configured agent therefore inherits the full
config (skills, subagents, hooks, MCP, guides) **transitively**, with no `~/.emdash/`
directory to deploy. Prerequisites: run `./bootstrap.sh` first (home deploy) and
install a supported agent (Claude Code is formally verified; Codex/Gemini/Cursor are
best-effort). Verify with `/env-check`'s "emdash Inheritance" section, or run the
probe directly:

```bash
configs/claude/scripts/emdash_inherit_check.sh   # verdict INHERITED = full parity
```

See [docs/EMDASH.md](../EMDASH.md) for setup, the `.emdash.json` worktree pattern, and
the hook-coexistence caveat.

---

---

[← Getting Started](../GETTING_STARTED.md)
