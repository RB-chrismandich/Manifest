#!/bin/sh
set -eu
umask 077
git init --quiet --template= .
git remote add origin git@github.com:acme/infra-tools.git
mkdir -p src/infratools tests infra
cat > pyproject.toml <<'EOF'
[project]
name = "infratools"
version = "0.1.0"
requires-python = ">=3.12,<3.13"
dependencies = ["httpx>=0.27"]

[project.optional-dependencies]
dev = ["pytest>=8", "ruff>=0.6"]

[tool.pytest.ini_options]
testpaths = ["tests"]
EOF
cat > src/infratools/__init__.py <<'EOF'
def region_for(env: str) -> str:
    return {"prod": "us-east-1", "dev": "us-west-2"}[env]
EOF
cat > tests/test_regions.py <<'EOF'
from infratools import region_for

def test_prod_region():
    assert region_for("prod") == "us-east-1"
EOF
cat > infra/main.tf <<'EOF'
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
EOF
