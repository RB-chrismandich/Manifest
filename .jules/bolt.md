## 2026-02-05 - Bash process fork overhead
**Learning:** Calling `date +%s` in a tight loop (100ms interval) introduces significant overhead (~2.8ms per call / ~2.8% CPU) due to process forking. The Bash builtin `$SECONDS` eliminates this overhead completely.
**Action:** Always prefer shell builtins like `$SECONDS` for elapsed time tracking in monitoring loops.
