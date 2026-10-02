---
type: llm
weight: 1
---
Score 1 only if the answer flags `publicly_accessible = true` on the production RDS instance as a public-exposure risk (it gives the instance a publicly resolvable/routable address; actual reachability then depends only on subnet routing, security groups and NACLs) AND recommends setting it to `false` and reaching the database through private subnets / VPN / bastion. Score 0 if the setting is not flagged or no fix is given.
