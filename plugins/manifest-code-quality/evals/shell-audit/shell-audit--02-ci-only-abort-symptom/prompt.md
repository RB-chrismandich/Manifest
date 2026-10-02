---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
model: sonnet
---
This script runs fine on my Mac but in GitHub Actions (ubuntu-latest) it exits 1 right after printing "converted a.md" — no error message, and the rest of the files are skipped. What's going on and how do I fix it?

```bash
#!/usr/bin/env bash
set -euo pipefail

converted=0
for f in docs/*.md; do
  pandoc "$f" -o "out/$(basename "${f%.md}").html"
  echo "converted $(basename "$f")"
  ((converted++))
done
echo "converted $converted files"
```
