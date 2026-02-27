## 2026-02-12 - [CI/ShellCheck Fixes]
**Vulnerability:** ShellCheck Warnings Blocking CI
**Learning:** ShellCheck is strict about variable usage in single quotes (SC2016) and `printf` format strings (SC2059). While SC2016 is often a false positive for things like GraphQL queries or `bash -c` strings, it must be explicitly disabled. SC2059 and SC2129 are valid robustness/style improvements.
**Prevention:** Always run `shellcheck` locally or verify CI logs for linting errors before merging shell scripts. Use `%b` for variables in `printf` format strings. Group redirects to avoid repetitive I/O operations.
