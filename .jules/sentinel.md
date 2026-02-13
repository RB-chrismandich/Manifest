## 2026-02-12 - Argument Injection in Python Rewrite
**Vulnerability:** Argument injection in `parallel_agent.py` via `asyncio.create_subprocess_exec` without `--` delimiter.
**Learning:** The Python rewrite of the agent orchestration script missed a security precaution present in the deprecated shell script (`parallel_agent.sh`), which correctly used `--` to separate flags from arguments.
**Prevention:** Always use `--` when passing user-controlled arguments to subprocesses that might interpret them as flags, even when using `exec` style invocation.
