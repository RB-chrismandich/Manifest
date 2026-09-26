---
max_turns: 30
timeout_seconds: 600
allowed_tools: [Skill, Read, Glob, Grep, Write, Edit, Bash]
model: sonnet
runs: 3
---
Scaffold this minimal repo in the current directory: run `git init`, `git remote add origin git@github.com:acme/infra-tools.git`, and create these files exactly:

`pyproject.toml`:
```
[project]
name = "infratools"
version = "0.1.0"
requires-python = ">=3.12,<3.13"
dependencies = ["httpx>=0.27"]

[project.optional-dependencies]
dev = ["pytest>=8", "ruff>=0.6"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

`src/infratools/__init__.py`:
```
def region_for(env: str) -> str:
    return {"prod": "us-east-1", "dev": "us-west-2"}[env]
```

`tests/test_regions.py`:
```
from infratools import region_for


def test_prod_region():
    assert region_for("prod") == "us-east-1"
```

`infra/main.tf`:
```
terraform {
  required_version = ">= 1.8"
  backend "s3" {
    bucket = "acme-tfstate"
    key    = "infra-tools/terraform.tfstate"
    region = "us-east-1"
  }
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.70" }
  }
}
```

Then set up CI/CD for this repo.
