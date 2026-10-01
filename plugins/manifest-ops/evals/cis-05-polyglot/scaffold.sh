#!/usr/bin/env bash
set -euo pipefail
git init -q
git remote add origin git@github.com:acme/infra-tools.git
cat > 'pyproject.toml' <<'EOF_0'
[project]
name = "infratools"
version = "0.1.0"
requires-python = ">=3.12,<3.13"
dependencies = ["httpx>=0.27"]

[project.optional-dependencies]
dev = ["pytest>=8", "ruff>=0.6"]

[tool.pytest.ini_options]
testpaths = ["tests"]
EOF_0
mkdir -p 'src/infratools'
cat > 'src/infratools/__init__.py' <<'EOF_1'
def region_for(env: str) -> str:
    return {"prod": "us-east-1", "dev": "us-west-2"}[env]
EOF_1
mkdir -p 'tests'
cat > 'tests/test_regions.py' <<'EOF_2'
from infratools import region_for


def test_prod_region():
    assert region_for("prod") == "us-east-1"
EOF_2
mkdir -p 'infra'
cat > 'infra/main.tf' <<'EOF_3'
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
EOF_3
