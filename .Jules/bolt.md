# Bolt Journal

## 2026-02-07 - Bash Loop Performance

**Learning:** Calling external commands like `date` inside tight loops (e.g.,
0.1s sleep) creates significant overhead due to process forking. Replacing
`date +%s` with the builtin `$SECONDS` variable eliminates this overhead.

**Action:** Always prefer shell builtins (like `$SECONDS` for elapsed time)
over external commands inside loops.

## 2025-05-15 - Offloading blocking file I/O to threads in async contexts

**Learning:** In highly concurrent scripts using `asyncio` (like
`parallel_agent.py`), blocking I/O operations such as `json.dump()`,
`open().write()`, or `Path.mkdir()` can significantly degrade performance by
blocking the async event loop.

**Action:** Use `asyncio.to_thread()` to offload these blocking file
operations to separate threads. For multiple independent file writes, collect
the tasks and execute them concurrently using `asyncio.gather()`. This prevents
event loop blockage and improves overall application throughput.
