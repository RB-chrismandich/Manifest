## 2026-02-12 - [Secure File Creation]
**Vulnerability:** TOCTOU Race Condition in File Creation
**Learning:** Using `touch` followed by `chmod` creates a window where a file exists with default permissions (often world-readable) before being secured. This is critical for files containing secrets like API keys.
**Prevention:** Use `umask` in a subshell to atomically create files with restrictive permissions. Example: `(umask 077; echo "secret" > file)`.
