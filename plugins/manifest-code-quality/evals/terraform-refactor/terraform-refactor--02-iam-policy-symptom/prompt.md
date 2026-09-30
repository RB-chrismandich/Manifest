---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
model: sonnet
---
Our security scanner keeps flagging this IAM policy on every scan and I don't understand why — can you help me fix it up?

```hcl
terraform {
  # no backend block configured — state defaults to local
}

resource "aws_iam_policy" "deploy" {
  name = "deploy-policy"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "*"
        Resource = "*"
      }
    ]
  })
}
```
