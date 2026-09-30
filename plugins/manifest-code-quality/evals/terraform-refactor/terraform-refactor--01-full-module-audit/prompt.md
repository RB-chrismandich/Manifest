---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
model: sonnet
---
Give me a prioritized refactor report for this module — security first.

```hcl
resource "aws_s3_bucket" "data" {
  bucket = "acme-prod-data"
}

resource "aws_s3_bucket_acl" "data_acl" {
  bucket = aws_s3_bucket.data.id
  acl    = "public-read"
}

resource "aws_security_group" "app" {
  name = "app-sg"

  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

variable "db_password" {
  type    = string
  default = "Str0ngP@ssw0rd!"
}
```
