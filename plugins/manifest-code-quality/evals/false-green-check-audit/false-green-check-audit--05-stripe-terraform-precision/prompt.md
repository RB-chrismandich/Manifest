---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
---
Before I roll this out, does this preflight script have any false-green risk — could it ever claim something passed when it wasn't actually checked?

```bash
#!/usr/bin/env bash
set -euo pipefail

passed=0
failed=0
skipped=0

report_pass() { passed=$((passed + 1)); echo "PASS: $1"; }
report_fail() { failed=$((failed + 1)); echo "FAIL: $1"; }
report_skip() { skipped=$((skipped + 1)); echo "SKIP: $1 (unverified)"; }

if [[ -n "${STRIPE_API_KEY:-}" ]]; then
  if curl -fsS -u "${STRIPE_API_KEY}:" https://api.stripe.com/v1/balance >/dev/null; then  # gitleaks:allow
    report_pass "stripe reachable"
  else
    report_fail "stripe unreachable"
  fi
else
  report_skip "stripe check needs STRIPE_API_KEY, run 'export STRIPE_API_KEY=...' to verify"
fi

if ! command -v terraform >/dev/null 2>&1; then
  report_skip "terraform not on PATH, install it to verify config"
elif ! compgen -G "*.tf" >/dev/null; then
  report_skip "no *.tf files in $(pwd), nothing to validate"
else
  if terraform validate >/dev/null; then
    report_pass "terraform config valid"
  else
    report_fail "terraform config invalid"
  fi
fi

echo "$passed passed, $failed failed, $skipped unverified"
if [[ "$failed" -gt 0 ]]; then
  echo "FAILED: $failed check(s) failed"
  exit 1
elif [[ "$skipped" -gt 0 || "$passed" -eq 0 ]]; then
  echo "PARTIAL: not everything could be verified"
  exit 1
fi
echo "ALL CHECKS PASSED"
```
