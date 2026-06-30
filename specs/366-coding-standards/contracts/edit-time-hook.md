# Contract — Edit-time Lint Hook (`lint_on_edit_hook.sh`)

Behavioral contract for the PostToolUse `Write|Edit` advisory linter. Tests in
`tests/bats/lint_on_edit_hook.bats` assert every clause.

## Wiring

```jsonc
// configs/claude/settings.local.json → hooks.PostToolUse[]
{
  "matcher": "Write|Edit",
  "hooks": [ { "type": "command", "command": "~/.claude/scripts/lint_on_edit_hook.sh" } ]
}
```

Added as a **third** Write|Edit hook, after `version_pin_hook.sh` and
`spec_review.sh --silent`. Order is independent (each exits 0).

## Input

- **stdin**: Claude Code PostToolUse JSON payload.
- The hook extracts the edited path from `.tool_input.file_path`, falling back to
  top-level `.file_path` (payload shape varies by Claude Code version), using the
  same `python3` extraction as `version_pin_hook.sh`.
- If no path is found → exit 0 (nothing to do).

## Behavior

1. Resolve `file_path`; if it is under an excluded prefix
   (`.Jules/`, `node_modules/`, `.git/`, `templates/scaffold/`) → exit 0.
2. Switch on the file extension (case-insensitive) per the dispatch table
   (data-model.md). Unknown extension → exit 0.
3. For the matched linter: if `command -v <linter>` fails → exit 0 (fail-open).
4. Run the linter on the file **read-only** (no fixer flags), wrapped in `_run`
   (timeout 8 via `timeout` -> `gtimeout` -> `perl` alarm -> direct). A timed-out
   linter (exit 124/142) is surfaced as an advisory note; the hook still exits 0.
5. Emit any findings to **stderr**, prefixed `lint-on-edit: <file>:`.
6. **Always `exit 0`.**

## Output

- **stdout**: empty.
- **stderr**: advisory findings only (or nothing when clean / skipped).
- **exit code**: `0` in 100% of cases (clean, dirty, missing tool, timeout, bad
  payload, excluded path).

## Guarantees (testable)

| ID | Guarantee | Test |
|---|---|---|
| G1 | Never blocks: exit 0 even when the file has violations | feed `.py` with `import os` unused → exit 0, finding on stderr |
| G2 | Never mutates: file bytes unchanged after run | sha256 before/after a dirty `.sh` edit are equal |
| G3 | Fail-open: missing linter ⇒ exit 0, no error | run with PATH stripped of `ruff` → exit 0, no stderr error |
| G4 | Dispatch: each supported extension invokes its linter | `.sh/.py/.yml/.json/.md/.mdc` each produce a finding for a planted violation |
| G5 | Excludes honored: excluded path ⇒ no linting | edit under `templates/scaffold/` → exit 0, no finding |
| G6 | Unknown extension ⇒ no-op | edit `.txt` → exit 0, no finding |
| G7 | Bad/empty payload ⇒ exit 0 | empty stdin → exit 0 |
| G8 | macOS Bash 3.2 safe | `bash --posix`/3.2 lint via shellcheck + array-expansion check |

## Conventions (repo)

- `#!/usr/bin/env bash`; `set -uo pipefail` (NOT `-e` — must survive linter
  non-zero exits).
- `--help` flag: usage ≤15 lines, exit 0.
- Internal errors routed through `err() { echo "lint_on_edit_hook.sh: $*" >&2; }`
  (advisory linter output is separate, not via `err`).
- Empty-array expansions guarded (`"${arr[@]+"${arr[@]}"}"`).
