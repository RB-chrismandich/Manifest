## 2026-01-29 - Prevent Command Injection in bash -c
**Vulnerability:** Unsafe construction of command strings passed to `bash -c`, allowing command injection via `GEMINI_INCLUDE_DIRS` (argument injection) or potentially model names.
**Learning:** When using `bash -c`, never interpolate variables directly into the command string. Instead, pass them as positional parameters after the command string and reference them as `$1`, `$2`, etc.
**Prevention:** Use `bash -c 'command "$1" "$2"' -- "arg1" "arg2"` pattern.

## 2026-01-30 - Insecure Temporary File Creation in Shell Scripts
**Vulnerability:** Predictable filenames in `/tmp` (e.g., `/tmp/file_$$.txt`) allow symlink attacks (CWE-377), enabling local attackers to overwrite files owned by the user running the script.
**Learning:** Shell scripts using `$$` for uniqueness in `/tmp` are vulnerable.
**Prevention:** Always use `mktemp` to create temporary files (e.g., `tmp=$(mktemp)`). It ensures unique names and safe permissions (0600).
