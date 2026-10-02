# Git Platform Reference

> Platform detection (`git_platform.sh`) and platform-agnostic operations
> (`git_ops.sh`) for GitHub/GitLab/plain git. Referenced from CLAUDE.md.

## Git Platform Detection & Operations

The framework provides platform-agnostic Git hosting operations that work with GitHub, GitLab, and plain Git repositories.

### Platform Detection Script

**Location**: `~/.claude/scripts/git_platform.sh`

Detects the Git hosting platform from the repository's remote URL.

**Usage**:

```bash
~/.claude/scripts/git_platform.sh [remote_name]
```

**Output**: `github`, `gitlab`, or `git` to stdout

**Environment Variables**:

- `MANIFEST_GIT_PLATFORM` - Force a specific platform (github|gitlab|git)
- `MANIFEST_GIT_REMOTE` - Remote name to check (default: origin)

**Exit Codes**: 0 = success, 1 = failure (no repo or remote)

**Examples**:

```bash
# Auto-detect from origin remote
~/.claude/scripts/git_platform.sh
# Output: github

# Check a specific remote
~/.claude/scripts/git_platform.sh upstream
# Output: gitlab

# Force platform override
MANIFEST_GIT_PLATFORM=gitlab ~/.claude/scripts/git_platform.sh
# Output: gitlab
```

### Operations Wrapper Script

**Location**: `~/.claude/scripts/git_ops.sh`

Platform-agnostic wrapper for Git operations (issue/PR management). Routes
commands to `gh` (GitHub), `glab` (GitLab), or warns if neither is available.

**Usage**:

```bash
~/.claude/scripts/git_ops.sh <subcommand> [args...]
```

**Subcommands**:

| Subcommand | GitHub (`gh`) | GitLab (`glab`) | Plain git |
|------------|---------------|-----------------|-----------|
| `issue-view N` | `gh issue view N` | `glab issue view N` | warn |
| `issue-list` | `gh issue list` | `glab issue list` | warn |
| `issue-create` | `gh issue create` | `glab issue create` | warn |
| `issue-comment N` | `gh issue comment N` | `glab issue note N` | warn |
| `issue-close N` | `gh issue close N` | `glab issue close N` | warn |
| `issue-edit N` | `gh issue edit N` | `glab issue update N` | warn |
| `pr-create` | `gh pr create` | `glab mr create` | warn |
| `pr-view N` | `gh pr view N` | `glab mr view N` | warn |
| `pr-list` | `gh pr list` | `glab mr list` | warn |
| `label-create` | `gh label create` | `glab label create` | warn |

**Examples**:

```bash
# View an issue (auto-detects platform)
~/.claude/scripts/git_ops.sh issue-view 123

# Create a pull/merge request
~/.claude/scripts/git_ops.sh pr-create --title "Fix bug" --body "Description"

# List open issues
~/.claude/scripts/git_ops.sh issue-list --state open
```

**Note**: The script automatically detects the platform using `git_platform.sh`.
All arguments are passed through to the underlying CLI tool (`gh` or `glab`).
