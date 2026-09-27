---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
---
Can you do a pipefail/silent-abort audit of this coverage gate before we wire it into the merge queue?

```bash
#!/usr/bin/env bash
set -euo pipefail

report="coverage.json"

total="$(jq -r '.total // empty' "$report")" || { echo "coverage-gate: failed to parse total from $report" >&2; exit 1; }
if [[ -z "$total" ]]; then
  echo "coverage-gate: no total field in $report, skipping gate" >&2
  exit 0
fi

failing="$(jq -r '.failing_files // [] | length' "$report")" || { echo "coverage-gate: failed to parse failing_files from $report" >&2; exit 1; }
if (( failing > 0 )); then
  echo "warning: $failing files below threshold" >&2
fi

echo "coverage: $total% (checked $failing flagged files)"
```
