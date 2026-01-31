## 2026-01-29 - Prevent Command Injection in bash -c
**Vulnerability:** Unsafe construction of command strings passed to `bash -c`, allowing command injection via `GEMINI_INCLUDE_DIRS` (argument injection) or potentially model names.
**Learning:** When using `bash -c`, never interpolate variables directly into the command string. Instead, pass them as positional parameters after the command string and reference them as `$1`, `$2`, etc.
**Prevention:** Use `bash -c 'command "$1" "$2"' -- "arg1" "arg2"` pattern.

## 2026-01-30 - Insecure Temporary File Creation in Shell Scripts
**Vulnerability:** Predictable filenames in `/tmp` (e.g., `/tmp/file_$$.txt`) allow symlink attacks (CWE-377), enabling local attackers to overwrite files owned by the user running the script.
**Learning:** Shell scripts using `$$` for uniqueness in `/tmp` are vulnerable.
**Prevention:** Always use `mktemp` to create temporary files (e.g., `tmp=$(mktemp)`). It ensures unique names and safe permissions (0600).

## 2026-01-27 - Critical Command Injection in Shell Profile Setup
**Vulnerability:** Command injection via `GEMINI_API_KEY` input in `bootstrap.sh`. Unsanitized user input was written to shell profiles (e.g., `.zshrc`) wrapped in double quotes. A malicious input like `foo"; rm -rf /; echo "` would execute when the shell profile is sourced.
**Learning:** Even installation scripts need strict input validation and secure coding practices. Writing user input to shell startup files is a high-risk operation that requires robust escaping.
**Prevention:** Always use single quotes for string literals in generated shell code. Escape single quotes in the input data before writing. Validate input format where possible.
