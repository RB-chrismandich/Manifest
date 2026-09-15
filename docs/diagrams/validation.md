# Validation Flow

```mermaid
flowchart TD
  W[OMP worker evidence] --> P[Parent validates]
  P --> T1[Tier 1 blocking concerns]
  P --> T2[Tier 2 advisory concerns]
  T1 --> D[Disposition]
  T2 --> D
```

The parent validates evidence and makes the final disposition. Independent
review enters this flow only on risk-based escalation from a confirmed risk
condition. The unattended gate retains a fail-closed injected single-reviewer
seam.
