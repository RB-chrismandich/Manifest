## 2026-02-06 - Insecure Temporary Directory Creation in Python (CWE-377)
**Vulnerability:** The Python script `configs/claude/scripts/parallel_agent.py` used a predictable PID-based naming convention (`/tmp/.claude_agent_outputs_{os.getpid()}`) for its fallback output directory in the `_resolve_output_dir` function.
**Learning:** Python scripts using predictable names in shared directories like `/tmp` are vulnerable to symlink attacks. If an attacker pre-creates a symlink with the predicted name, actions like `mkdir` could follow the symlink and alter permissions of sensitive files, potentially leading to privilege escalation or data loss.
**Prevention:** Always use `tempfile.mkdtemp()` or `tempfile.NamedTemporaryFile()` to create temporary files or directories in Python. These functions guarantee a unique name, create the resource atomically, and set safe, restricted permissions, preventing symlink vulnerabilities.

## 2026-02-06 - Command Injection via Config Parsing (eval)
**Vulnerability:** The script `.claude/scripts/parallel_agent.sh` used `eval` to process configuration values parsed from `services.yml`. If the configuration file (located in the user's home directory) was modified by an attacker, it could lead to arbitrary command execution within the context of the script.
**Learning:** Using `eval` on data derived from external files, even if partially sanitized by `awk`, is risky and hard to audit. It creates a direct path for code injection if the sanitization logic is flawed or bypassed.
**Prevention:** Replace `eval` with a `while read` loop that iterates over the parsed output. Use strict matching (e.g., `case "$key" in ...`) to whitelist allowed variables and assign values safely, preventing execution of arbitrary commands.
