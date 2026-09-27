---
type: llm
weight: 0.5
---
Score 1 if the answer notes that when docker IS installed but the daemon is down, `docker info >/dev/null 2>&1 && check ...` silently records nothing (no FAIL, no count), so a dead daemon is also invisible to the summary. Score 0 if not mentioned.
