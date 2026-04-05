# Bolt Learning Journal

## 2026-02-07 - Bash Loop Performance

**Learning:** Calling external commands like `date` inside tight loops (e.g.,
0.1s sleep) creates significant overhead due to process forking. Replacing
`date +%s` with the builtin `$SECONDS` variable eliminates this overhead.

**Action:** Always prefer shell builtins over external commands inside loops.

## 2025-05-15 - Python Async I/O Performance

**Learning:** In asynchronous contexts like `parallel_agent.py`, doing heavy
file operations (e.g., `Path.mkdir()` and multiple file writes in
`_write_output_files`) natively on the main thread significantly blocked the
event loop. Synchronous execution on main thread measured to be ~4.5x slower.

**Action:** Use `asyncio.to_thread()` to wrap and execute all grouped blocking
I/O calls to prevent event loop blocking in high-concurrency systems.
