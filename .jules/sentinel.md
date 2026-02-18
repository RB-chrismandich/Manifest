# Sentinel Journal - Critical Security Learnings

## 2026-02-14 - Atomic Secure File Creation in Shell Scripts
**Vulnerability:** Insecure file creation race condition (CWE-362) where sensitive files were created with default umask (world-readable) before `chmod` was applied.
**Learning:** Shell scripts using `touch file; chmod 600 file` or `command > file; chmod 600 file` expose sensitive data during the window between creation and permission change.
**Prevention:** Use `(umask 077; command > file)` pattern to ensure atomic restricted permissions upon file creation. For directories, use `mkdir -m 700 dir` or `mkdir dir; chmod 700 dir` (though `mkdir` honors umask, explicit `chmod` is safer if umask is unknown).
