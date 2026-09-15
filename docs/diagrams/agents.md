# Agent Workflow

> OMP-native interactive dispatch and retained single-provider integrations.

```mermaid
flowchart TD
  P[Parent agent] --> T[OMP task batch]
  T --> W[Independent child units]
  W --> P
  P --> V[Validate and aggregate evidence]
  S[Single-provider integration] --> M[model_policy.yml]
  M --> C[One provider CLI route]
```

Interactive work uses OMP task batches and parent-side evidence validation.
Noninteractive integrations resolve one CLI route through `model_policy.yml`.
