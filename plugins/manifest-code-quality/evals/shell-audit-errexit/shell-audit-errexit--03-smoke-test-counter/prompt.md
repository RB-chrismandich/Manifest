---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
model: sonnet
---
I'm about to merge this smoke-test runner — can you sanity check it for `set -e` footguns before I do?

```bash
#!/usr/bin/env bash
set -euo pipefail

passed=0
failed=0

for t in tests/*.sh; do
  echo "running $t"
  if bash "$t"; then
    echo "PASS $t"
    ((passed++))
  else
    echo "FAIL $t"
    ((failed++))
  fi
done

echo "summary: $passed passed, $failed failed"
```
