---
type: llm
weight: 1
---
Score 1 only if the answer flags `rm -rf $backup_dir/*` as an unquoted expansion, AND explains that because `backup_dir` comes from an unset/empty `$1` (no `set -u`, no validation), the token collapses to `/*` so the command effectively becomes `rm -rf /*` (wipes the filesystem root), AND proposes a fix such as quoting/validating the argument (e.g. `rm -rf "${backup_dir:?backup_dir required}"/*` or an explicit non-empty check before the `rm`). Score 0 if this hazard is missing or only called a minor style nit.
