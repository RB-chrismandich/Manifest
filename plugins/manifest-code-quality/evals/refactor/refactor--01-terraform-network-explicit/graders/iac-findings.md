---
type: llm
weight: 1
---
Score 1 only if the answer gives Terraform/IaC-specific findings: it identifies BOTH (1) the `public-read` ACL on `aws_s3_bucket_acl.logs` as making the bucket's objects publicly readable, and (2) the `aws_security_group.app` ingress rule opening tcp/22 to `0.0.0.0/0` as exposing SSH to the whole internet — with a fix for each (private ACL / public access block; restrict the CIDR or remove direct SSH exposure). Score 0 if the answer gives only generic software-engineering advice (e.g. "add tests", "improve naming") without identifying these two IaC-specific issues, or misses one of them.
