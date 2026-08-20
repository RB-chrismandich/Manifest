# Quick Reference

> The commands from this tutorial, in one table.

## Quick Reference

```bash
# Test all agents
~/.claude/scripts/parallel_agent.py --json "Test"

# Use specific models
~/.claude/scripts/parallel_agent.py --cursor-model advanced --claude-model opus "Task"

# Run single agent
~/.claude/scripts/parallel_agent.py --claude-only "Question"

# Analyze a file
~/.claude/scripts/parallel_agent.py --review file.py

# Reconfigure services
./bootstrap.sh --reconfigure --disable-cursor

# View configuration
cat ~/.claude/config/services.yml
cat ~/.claude/config/command_config.yml
```

---

## Related Documents

- [README.md](../README.md) - Project overview
- [Configuration Guide](../configuration/README.md) - All configuration options
- [Architecture Diagrams](../diagrams/README.md) - Visual system documentation
- [Troubleshooting](../troubleshooting/README.md) - Common problems and solutions
- [CLAUDE.md](../../CLAUDE.md) - Repository context for AI assistants

---

[← Getting Started](../GETTING_STARTED.md)
