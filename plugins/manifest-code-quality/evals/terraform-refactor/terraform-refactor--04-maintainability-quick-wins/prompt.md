---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
model: sonnet
---
Just give me the quick wins for maintainability on this module — nothing security related.

```hcl
resource "aws_instance" "web_us_east" {
  ami               = "ami-0abcdef1234567890"
  instance_type     = "t3.micro"
  availability_zone = "us-east-1a"
}

resource "aws_instance" "web_us_east_2" {
  ami               = "ami-0abcdef1234567890"
  instance_type     = "t3.micro"
  availability_zone = "us-east-1b"
}

variable "environment" {
  type = string
}
```
