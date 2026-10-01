---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
model: sonnet
---
Review this deploy preflight script for false-green risk before we wire it into CI — can it ever print "ALL CHECKS PASSED" when something wasn't actually verified?

```bash
#!/usr/bin/env bash
set -euo pipefail

pass=0
total=0

check() {
  total=$((total + 1))
  echo "PASS: $1"
  pass=$((pass + 1))
}

echo "== preflight checks =="

if aws sts get-caller-identity >/dev/null 2>&1; then
  check "aws credentials valid"
else
  echo "SKIP: aws credentials not configured, skipping identity check"
fi

if command -v docker >/dev/null 2>&1; then
  docker info >/dev/null 2>&1 && check "docker daemon reachable"
else
  check "docker not installed, nothing to verify"
fi

if pg_isready -h "$DB_HOST" >/dev/null 2>&1; then
  check "database reachable"
else
  echo "FAIL: database unreachable"
fi

echo "$pass/$total checks passed"
if [[ "$pass" -eq "$total" ]]; then
  echo "ALL CHECKS PASSED"
fi
```
