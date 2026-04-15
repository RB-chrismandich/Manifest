# Bolt Learning Journal

## 2026-02-07 - Bash Loop Performance

**Learning:** Calling external commands like `date` inside tight loops (e.g.,
0.1s sleep) creates significant overhead due to process forking. Replacing
`date +%s` with the builtin `$SECONDS` variable eliminates this overhead.
**Action:** Always prefer shell builtins (like `$SECONDS` for elapsed time)
over external commands inside loops.

## 2026-04-15 - Async I/O Offloading in Event Loops

**Learning:** Writing multiple files (outputs, JSON summaries) synchronously
inside an `asyncio` event loop blocks the main thread, causing significant
performance overhead in high-concurrency scripts like `parallel_agent.py`.
**Action:** Always use `asyncio.to_thread` and `asyncio.gather` to offload
blocking file I/O operations (like `open().write()`, `json.dump`, and
`Path.mkdir`) to separate threads when operating inside an async context.
