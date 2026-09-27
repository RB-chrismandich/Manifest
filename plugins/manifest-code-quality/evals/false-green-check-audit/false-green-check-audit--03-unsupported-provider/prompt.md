---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
---
Quick look before this goes into our pre-commit hook — anything off with how it reports provider status?

```bash
#!/usr/bin/env bash
set -euo pipefail

check_provider() {
  local name="$1"
  case "$name" in
    github) gh auth status >/dev/null 2>&1 ;;
    gitlab) glab auth status >/dev/null 2>&1 ;;
    linear) [[ -n "${LINEAR_API_KEY:-}" ]] ;;
    *) return 0 ;;   # unknown/unsupported provider: nothing to verify
  esac
}

provider="${1:-jira}"
if check_provider "$provider"; then
  echo "OK: $provider is configured"
else
  echo "FAIL: $provider is not configured"
  exit 1
fi
```
