---
max_turns: 10
timeout_seconds: 180
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
---
Can you walk me through what this `terraform plan` diff is actually going to do before I hit apply?

```
  # aws_security_group.web will be updated in-place
  ~ resource "aws_security_group" "web" {
        id   = "sg-0123456789abcdef0"
      ~ ingress {
          ~ cidr_blocks = [
              - "10.0.0.0/16",
              + "0.0.0.0/0",
            ]
            from_port = 443
            to_port   = 443
            protocol  = "tcp"
        }
    }

Plan: 0 to add, 1 to change, 0 to destroy.
```
