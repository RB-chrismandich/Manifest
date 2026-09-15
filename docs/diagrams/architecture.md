# Architecture

> Manifest deploys guides, skills, and retained runtime integrations.

```mermaid
flowchart LR
  H[Supported harness] --> G[OMP orchestration guide]
  G --> T[task batches]
  T --> P[Parent validation]
  I[CDDL / delegation / SkillClaw] --> MP[model_policy.yml]
  MP --> CLI[Single provider CLI]
```

Interactive and noninteractive paths have separate contracts: OMP manages
interactive workers; `model_policy.yml` serves retained single-provider tools.
