# Sentinel's Journal 🛡️

## 2026-02-12 - Insecure Temporary Directory Creation

**Vulnerability:** The `parallel_agent.py` script constructed a fallback temporary directory using a predictable path `/tmp/.claude_agent_outputs_{PID}`. This allowed an attacker to pre-create the directory with malicious permissions or race condition it (TOCTOU) to intercept sensitive agent outputs.

**Learning:** Using `mkdir -p` or `os.makedirs(..., exist_ok=True)` on a predictable path in a world-writable directory is inherently insecure, even if `mode=0o700` is specified, because if the directory already exists (pre-created by an attacker), the mode argument is ignored and the existing permissions are used.

**Prevention:** Always use `tempfile.mkdtemp()` (Python) or `mktemp -d` (Shell) when creating temporary directories in shared locations like `/tmp`. These functions guarantee a unique path and secure permissions (0700) atomically.
