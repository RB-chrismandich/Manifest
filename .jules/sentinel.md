## 2026-01-29 - Prevent Command Injection in bash -c
**Vulnerability:** Unsafe construction of command strings passed to `bash -c`, allowing command injection via `GEMINI_INCLUDE_DIRS` (argument injection) or potentially model names.
**Learning:** When using `bash -c`, never interpolate variables directly into the command string. Instead, pass them as positional parameters after the command string and reference them as `$1`, `$2`, etc.
**Prevention:** Use `bash -c 'command "$1" "$2"' -- "arg1" "arg2"` pattern.
