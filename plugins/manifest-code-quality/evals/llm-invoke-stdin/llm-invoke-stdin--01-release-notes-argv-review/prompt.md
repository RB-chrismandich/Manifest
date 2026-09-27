---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
---
Review this release-notes summarizer before I wire it into CI — anything that'll break on a big release?

```bash
#!/usr/bin/env bash
set -euo pipefail

CONTEXT_FILE="release_notes_raw.txt"   # can be several MB for a big release

summarize() {
  claude -p "$(cat "$CONTEXT_FILE")"
}

summary="$(summarize)"
echo "$summary" > release_notes_summary.txt
```
