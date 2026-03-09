# Palette's Journal

## 2026-02-06 - Initial Setup
**Learning:** UX improvements in CLI tools are just as critical as web UIs.
**Action:** When working on CLI scripts, prioritize readability (colors, spacing) and explicit user guidance (defaults, help text).

## 2026-02-08 - CLI Spinner Polish
**Learning:** CLI progress indicators benefit greatly from cursor hiding and output abstraction. Logging command output to a temporary file and only displaying it upon failure significantly reduces terminal clutter, making the happy path cleaner. Additionally, using explicit Braille Unicode characters in native Bash arrays avoids parsing issues with `\u` escapes across different platforms.
**Action:** Implement background operations in subshells with proper `INT`/`TERM` traps to ensure cursor restoration and temp file cleanup on user interrupt.
