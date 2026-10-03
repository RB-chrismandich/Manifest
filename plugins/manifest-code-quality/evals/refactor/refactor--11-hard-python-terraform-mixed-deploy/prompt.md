---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
model: sonnet
---
We're adding an IAM policy and a webhook notifier to our deploy pipeline — can you run a full refactor pass across both and give me one prioritized fix list?

`iam.tf`:

```hcl
resource "aws_iam_policy" "deploy" {
  name = "deploy-pipeline-policy"

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

resource "aws_iam_role_policy_attachment" "deploy" {
  role       = aws_iam_role.deploy.name
  policy_arn = aws_iam_policy.deploy.arn
}
```

`notify.py`:

```python
import subprocess

def send_webhook(url, payload):
    cmd = f"curl -X POST -d '{payload}' {url}"
    subprocess.run(cmd, shell=True)
```
