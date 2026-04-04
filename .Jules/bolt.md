## 2026-02-07 - Bash Loop Performance
**Learning:** Calling external commands like `date` inside tight loops (e.g., 0.1s sleep) creates significant overhead due to process forking. Replacing `date +%s` with the builtin `$SECONDS` variable eliminates this overhead.
**Action:** Always prefer shell builtins (like `$SECONDS` for elapsed time) over external commands inside loops.

## 2025-04-04 - Asyncio Event Loop Blocking I/O
**Learning:** In high-concurrency async Python scripts, standard blocking I/O operations (like `open().write()`, `json.dump`, or `Path.mkdir()`) run synchronously and block the main async event loop.
**Action:** Use `asyncio.to_thread()` to offload these blocking operations to a separate thread when performing disk I/O in async contexts.
