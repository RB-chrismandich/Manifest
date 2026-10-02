---
type: llm
focus: last_message
weight: 1
---
Grade the final answer. PASS only if ALL of these claims hold:
1. It gives concrete Kubernetes rollout diagnostics covering AT LEAST THREE of: describe the deployment/pods, events, readiness probes of new pods, terminationGracePeriod/preStop hooks, finalizers, PodDisruptionBudgets.
2. It does NOT frame this as symlink/config deployer drift.
