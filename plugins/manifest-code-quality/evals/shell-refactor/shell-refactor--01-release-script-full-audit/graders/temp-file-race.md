---
type: llm
weight: 1
---
Score 1 only if the answer flags `tmp=/tmp/release.$$` as a predictable, shared-directory temp filename (PID-based, in world-writable `/tmp`) that is vulnerable to a symlink/race attack from another local user or process, AND recommends replacing it with `mktemp` (and ideally cleaning it up with a `trap ... EXIT`). Score 0 otherwise.
