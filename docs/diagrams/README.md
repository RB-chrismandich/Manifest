# Architecture Diagrams

> Mermaid diagrams of the Manifest orchestration framework, one subject per page.

Twenty diagrams, grouped by what they explain. Each page holds at most four.

| Page | Answers |
|------|---------|
| [Application & Orchestration Architecture](architecture.md) | How is the deployed tree laid out, and what runs a parallel agent invocation? |
| [Agent Dispatch](agents.md) | Which module calls which, how is a backend chosen, and what happens during a run? |
| [Validation & Consensus](validation.md) | How does skill output become a scored verdict? |
| [Model Selection](models.md) | Which model does a run get, and how is a stale pin caught? |
| [Platform & Bootstrap](platform.md) | How is the git platform detected, and what does `bootstrap.sh` do in order? |
| [Configuration & Labels](configuration.md) | How do config layers resolve, and where do labels come from? |
| [Issue Management](issues.md) | How do issues sync with commits and PRs, and what does the autonomous developer do? |
| [Skill & Development Pipelines](pipelines.md) | How does SkillClaw ingest sessions, and how does the critic loop gate work? |

## Related Documents

- [docs/README.md](../README.md) — documentation hub
- [configuration/](../configuration/README.md) — the settings these diagrams reference
- [../../CLAUDE.md](../../CLAUDE.md) — repository structure
