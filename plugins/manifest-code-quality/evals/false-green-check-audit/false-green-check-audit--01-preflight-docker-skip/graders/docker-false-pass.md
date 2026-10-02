---
type: llm
weight: 1
---
Score 1 only if the answer identifies that when `docker` is not installed, the `else` branch calls `check "docker not installed, nothing to verify"`, which increments both `pass` and `total` — so the daemon is never actually verified yet is counted as a PASS and can make the final "ALL CHECKS PASSED" line print. Score 0 if this specific branch is not identified as a false-green bug (e.g. only the unrelated `aws`/`pg_isready` branches are discussed, or the answer says the script is safe as-is).
