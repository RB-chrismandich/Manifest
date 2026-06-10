# Contract: Empty-Array Expansion Guard

**Applies to**: new checker (tests/lint/check_array_expansion.sh or .py),
wired into `.pre-commit-config.yaml` (local repo hook) AND the CI lint job.

Detection rule (Bash 3.2 + `set -u` hazard):
- Flag `"${name[@]}"` / `"${name[*]}"` in any tracked `*.sh` file when the
  same file initializes the array as `name=()` (conditionally populated),
  UNLESS:
  - the expansion uses the guard idiom `${name[@]+"${name[@]}"}`, or
  - the line carries an inline `# array-safe` opt-out comment.

Exit behavior:
- 0 = no findings; 1 = findings listed as `file:line: array-name` (one per
  line) — fails the pre-commit hook / CI step.

Self-test obligation:
- A test fixture with a deliberate violation MUST be reported (guard works).
- The repo at HEAD MUST produce zero findings (sweep complete).

Known accepted trade-off: arrays that are always non-empty but initialized
empty require either the guard idiom or an `# array-safe` comment — a small
annotation cost for eliminating the bug class on macOS Bash 3.2.
