## 2026-02-06 - Insecure Temporary Directory Creation (CWE-377)
**Vulnerability:** The script `.claude/scripts/parallel_agent.sh` used a predictable PID-based naming convention (`/tmp/.claude_agent_outputs_$$`) for its fallback output directory.
**Learning:** Shell scripts using predictable names in shared directories like `/tmp` are vulnerable to symlink attacks. An attacker can pre-create a symlink with the predicted name pointing to a sensitive file or directory (e.g., `/etc/passwd` or a user's home directory). When the script executes `mkdir -p` (which follows symlinks) and then `chmod 700`, it changes the permissions of the target file/directory, leading to local privilege escalation or data loss.
**Prevention:** Always use `mktemp -d` to create temporary directories. It guarantees a unique name and sets safe permissions atomically (0700). For cross-platform support (Linux/macOS), handle both template arguments (Linux: `mktemp -d template.XXXXXX`) and the `-t` flag (macOS: `mktemp -d -t prefix`).

## 2026-02-06 - Command Injection via Config Parsing (eval)
**Vulnerability:** The script `.claude/scripts/parallel_agent.sh` used `eval` to process configuration values parsed from `services.yml`. If the configuration file (located in the user's home directory) was modified by an attacker, it could lead to arbitrary command execution within the context of the script.
**Learning:** Using `eval` on data derived from external files, even if partially sanitized by `awk`, is risky and hard to audit. It creates a direct path for code injection if the sanitization logic is flawed or bypassed.
**Prevention:** Replace `eval` with a `while read` loop that iterates over the parsed output. Use strict matching (e.g., `case "$key" in ...`) to whitelist allowed variables and assign values safely, preventing execution of arbitrary commands.

## 2026-03-13 - Insecure Temporary Directory Creation in Python (CWE-377)
**Vulnerability:** The Python script `parallel_agent.py` used a predictable PID-based naming convention (`/tmp/.claude_agent_outputs_{os.getpid()}`) for its fallback output directory.
**Learning:** Python scripts using predictable names in shared directories like `/tmp` are vulnerable to symlink attacks, similar to bash scripts. An attacker could pre-create a symlink to hijack permissions or files when `.mkdir(parents=True, exist_ok=True, mode=0o700)` is called.
**Prevention:** Always use `tempfile.mkdtemp()` (or `tempfile.NamedTemporaryFile`) to create temporary directories/files in Python. It guarantees a unique name, creates it atomically, and sets safe permissions securely.
