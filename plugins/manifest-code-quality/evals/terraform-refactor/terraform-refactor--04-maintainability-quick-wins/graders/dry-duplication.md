---
type: llm
weight: 1
---
Score 1 only if the answer flags the two near-identical `aws_instance` resources (same hardcoded `ami-0abcdef1234567890`, same `instance_type`, differing only by `availability_zone`) as duplicated/non-DRY configuration, AND recommends consolidating them via `count`/`for_each` (or a shared variable/data source for the AMI) instead of copy-pasted resource blocks. Score 0 otherwise.
