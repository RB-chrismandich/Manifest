---
type: llm
weight: 1
---
Score 1 only if the answer flags the `aws_security_group.app` ingress rule (tcp/22 from `cidr_blocks = ["0.0.0.0/0"]`) as exposing SSH to the entire internet — a critical risk — AND recommends restricting the CIDR to a known/internal range, or replacing direct SSH exposure with a bastion host / SSM Session Manager. Score 0 otherwise.
