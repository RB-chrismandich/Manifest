# Bolt Learnings

## 2026-02-07 - Bash Loop Performance

**Learning:** Calling external commands like `date` inside tight loops (e.g.,
0.1s sleep) creates significant overhead due to process forking. Replacing
`date +%s` with the builtin `$SECONDS` variable eliminates this overhead.

**Action:** Always prefer shell builtins (like `$SECONDS` for elapsed time) over
external commands inside loops.

## 2026-04-10 - Python Async File I/O Performance

**Learning:** Writing multiple output files synchronously inside an async event
loop (like the parallel agent orchestrator) blocks the main thread and prevents
true concurrency when handling many agents. Moving I/O operations to
`asyncio.to_thread` and batching them with `asyncio.gather` eliminates event
loop blocking and speeds up finalization.

**Action:** Always offload blocking operations like `json.dump`,
`open().write()`, or `Path.mkdir()` to threads in async Python contexts to
prevent blocking the event loop.
