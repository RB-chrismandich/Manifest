---
type: llm
focus: last_message
---
- Flags that `${{ github.event.comment.body }}` is interpolated directly into the `run:` script, so any commenter can inject shell commands and exfiltrate `BOT_PAT`. Rated high.
- Gives the correct fix: bind the comment body to an `env:` variable and reference it as a quoted `"$VAR"` in the script (not inline `${{ }}`).
- Notes the missing identity gate: any GitHub user can comment; recommends a real admin/write permission check (collaborator permission API) or an explicit trusted-user allowlist. Recommending `author_association` ALONE does NOT satisfy this (MEMBER/COLLABORATOR are not write checks).
- Notes that `edited` should be dropped (types: [created] only) or bot comments excluded (at least one of these).
Pass only if the first three hold.
