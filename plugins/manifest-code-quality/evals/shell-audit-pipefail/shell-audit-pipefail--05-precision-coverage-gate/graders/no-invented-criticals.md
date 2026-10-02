---
type: llm
weight: 1
---
Score 1 only if the answer does NOT invent a missing-guard, missing-pipefail, unreachable-warning, or unhardened-parser bug in this script. Score 0 if it fabricates such a Critical/High issue (e.g., claiming the `failing > 0` warning is unreachable, or that the substitutions are unguarded, or that `pipefail` is missing).
