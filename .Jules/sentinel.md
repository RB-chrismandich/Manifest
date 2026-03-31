## 2026-02-06 - Insecure Temporary Directory Creation (CWE-377)

**Vulnerability:** The script `.claude/scripts/parallel_agent.sh` used a predictable PID-based naming convention
(`/tmp/.claude_agent_outputs_$$`) for its fallback output directory.

**Learning:** Shell scripts using predictable names in shared directories like `/tmp` are vulnerable to symlink attacks.
An attacker can pre-create a symlink with the predicted name pointing to a sensitive file or directory
(e.g., `/etc/passwd` or a user's home directory). When the script executes `mkdir -p` (which follows symlinks) and then
`chmod 700`, it changes the permissions of the target file/directory, leading to local privilege escalation or data loss.

**Prevention:** Always use `mktemp -d` to create temporary directories. It guarantees a unique name and sets safe
permissions atomically (0700). For cross-platform support (Linux/macOS), handle both template arguments (Linux:
`mktemp -d template.XXXXXX`) and the `-t` flag (macOS: `mktemp -d -t prefix`).

## 2026-02-06 - Command Injection via Config Parsing (eval)

**Vulnerability:** The script `.claude/scripts/parallel_agent.sh` used `eval` to process configuration values parsed from
`services.yml`. If the configuration file (located in the user's home directory) was modified by an attacker, it could
lead to arbitrary command execution within the context of the script.

**Learning:** Using `eval` on data derived from external files, even if partially sanitized by `awk`, is risky and
hard to audit. It creates a direct path for code injection if the sanitization logic is flawed or bypassed.

**Prevention:** Replace `eval` with a `while read` loop that iterates over the parsed output. Use strict matching
(e.g., `case "$key" in ...`) to whitelist allowed variables and assign values safely, preventing execution of
arbitrary commands.

## 2026-02-06 - Command Injection via Config Parsing (eval) in bootstrap and parallel_agent

**Vulnerability:** The scripts `bootstrap/lib/config.sh` and `configs/claude/scripts/parallel_agent.sh` used
`eval "$config_settings"` to parse `services.yml`. An attacker with write access to this YAML file could embed
arbitrary bash commands within `enabled:` values (e.g., `enabled: false; touch /tmp/pwned`) leading to arbitrary
command execution when parsed by `awk` and executed by `eval`.

**Learning:** Using `eval` to ingest parsed configuration is inherently dangerous, even if the parsing logic seems
restrictive. A minor flaw or unexpected input in the `awk` script can result in the execution of injected commands.

**Prevention:** Avoid `eval` for variable assignments from configuration files. Use a
`while read -r line; do case "$line" in ... esac; done <<< "$parsed_config"` construct to safely match and assign
whitelisted variables.
