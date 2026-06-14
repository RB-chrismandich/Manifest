# Quickstart: Issue-Linking Git Hooks

Enable and verify the two issue-sync skills in a repository.

## Prerequisites
- `gh` (GitHub) or `glab` (GitLab) authenticated with **issue read/write** scope.
- Repo deployed via `bootstrap.sh` so `git_ops.sh`, `git_platform.sh`, and `labels.yml` are present.
- Canonical labels provisioned: `configs/claude/scripts/label_sync.sh` (one-time per repo).

## 1. Enable (opt-in)
```bash
# Enable the unified PostToolUse hooks (cross-tool)
configs/claude/scripts/install_issue_hooks.sh --enable

# Optional: also install the native post-commit hook for raw-CLI commits
configs/claude/scripts/install_issue_hooks.sh --enable --native
```
Tune behavior in `configs/claude/config/command_config.yml`:
```yaml
tool_policies:
  pr-issue-sync:    { enabled: true, hook_timeout_seconds: 5 }
  commit-issue-sync:{ enabled: true, hook_timeout_seconds: 5, commit_hook_mode: sync }
```

## 2. Verify — commit trigger (US2)
```bash
git switch -c 017-some-fix        # branch prefix → issue #17
git commit --allow-empty -m "wip" # hook fires commit-issue-sync
# Expect: issue #17 label planned → in-progress; one back-link comment
git commit --allow-empty -m "wip2"
# Expect: no second comment, no re-transition (idempotent / dedup)
```

## 3. Verify — PR trigger (US1)
```bash
git_ops.sh pr-create --title "Some fix" --body "WIP"   # or: gh pr create ...
# Expect: issue #17 label → needs-review; back-link comment; PR body gains "Closes #17"
```

## 4. Verify — missing-issue creation (US3)
```bash
git switch -c hotfix-no-number     # no resolvable issue
git_ops.sh pr-create --title "Hotfix" --body ""
# Expect: prompt "Create tracking issue from branch hotfix-no-number? [y/N]"
#  - y → dedup-checked, templated issue created (labeled 'planned'), linked back
#  - non-interactive (CI) → no creation, warning only
```

## 5. Verify — fail-open (SC-002)
```bash
GH_TOKEN=invalid git commit --allow-empty -m "tracker down"
# Expect: commit SUCCEEDS; single warning line; no block
```

## 6. Dry-run / debug
```bash
configs/claude/scripts/issue_support.sh sync-pr 42 --dry-run
configs/claude/scripts/issue_support.sh resolve --branch 017-some-fix --json
```

## 7. Disable / uninstall
```bash
configs/claude/scripts/install_issue_hooks.sh --remove   # removes hooks; keeps skills + engine
```

## Tests
```bash
bats tests/bats/issue_support.bats
shellcheck configs/claude/scripts/issue_support.sh configs/claude/scripts/install_issue_hooks.sh
yamllint configs/claude/config/command_config.yml
```
