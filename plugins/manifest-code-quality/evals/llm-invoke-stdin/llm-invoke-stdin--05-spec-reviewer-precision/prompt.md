---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
model: sonnet
---
Does this spec-reviewer step look production ready before I wire it into the release pipeline?

```bash
#!/usr/bin/env bash
set -euo pipefail

REVIEW_CLI="${REVIEW_CLI:-claude}"

run_reviewer() {
  printf '%s' "$1" | "$REVIEW_CLI" -p "Review this spec and list risks, one per line."
}

spec_text="$(cat spec.md)"
run_reviewer "$spec_text"
```
