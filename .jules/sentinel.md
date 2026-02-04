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

## 2026-02-01 - Insecure File Permissions on Sensitive Outputs
**Vulnerability:** The parallel agent framework generated code analysis reports and stored them in directories with default umask permissions (often 755/644). This allowed other users on the system to read potentially sensitive code or vulnerability findings.
**Learning:** Default directory creation in shell scripts (`mkdir -p`) respects the user's umask, which is often too permissive for security tools. Tools handling sensitive data must explicitly manage permissions.
**Prevention:** Use `umask 0077` at the beginning of scripts handling sensitive data, and explicitly `chmod 700` directories containing sensitive outputs or configuration.

## 2026-02-05 - Insecure Secret Prompt in Shell Scripts
**Vulnerability:** Interactive shell scripts using `read` without the `-s` flag to prompt for sensitive information (like API keys) expose the secret in plain text on the terminal screen and potentially in screen recordings or shoulder surfing scenarios.
**Learning:** UX convenience should not compromise security. Users often copy-paste keys, and seeing them echoed back is a security risk.
**Prevention:** Always use `read -rs` (silent mode) when prompting for secrets. Remember to echo a newline `echo ""` afterwards as silent mode suppresses the user's enter key newline.
