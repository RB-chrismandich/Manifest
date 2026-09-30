---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
model: sonnet
---
Here's our new RDS instance definition — does this look production ready before I apply it?

```hcl
resource "aws_db_instance" "primary" {
  identifier        = "acme-prod-db"
  engine            = "postgres"
  instance_class    = "db.t3.medium"
  allocated_storage = 100

  publicly_accessible = true
  storage_encrypted   = false

  username = "app_admin"
  password = var.db_password
}
```
