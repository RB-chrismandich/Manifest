# Agent Workflow

> OMP-native interactive dispatch and retained single-provider integrations.

**Last Updated**: 2026-11-13

```mermaid
flowchart TD
  P[Parent agent] --> T[OMP task batch<br/>up to 32 submitted items]
  T --> S[Per-item output schema<br/>when structured mode is enabled]
  S --> C[Session semaphore<br/>task.maxConcurrency]
  C --> W[Independent child units]
  W --> R[Named result slots]
  R --> V[Parent schema and candidate validation]
  V -->|valid| A[Aggregate evidence]
  V -->|missing, malformed, failed| D[DEGRADED]
  I[Single-provider integration] --> M[model_policy.yml]
  M --> CLI[One provider CLI route]
```

The batch-size ceiling is not an active-concurrency limit. OMP's session
semaphore enforces the configured `task.maxConcurrency`; the parent preserves
each named slot and marks invalid or unavailable reviews `DEGRADED`.
