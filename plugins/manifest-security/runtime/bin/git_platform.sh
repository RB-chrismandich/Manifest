#!/usr/bin/env bash
# help-coverage: exempt — internal detection helper used by git_ops.sh; prints the
# detected platform to stdout, so it has no independent CLI surface.
# git_platform.sh - Detect Git hosting platform from remote URL
# Behavioral contract: tests/bats/ci_platform.bats. This copy is intentionally
# owned by manifest-security so CI audits never import another plugin runtime.
#
# Usage: git_platform.sh [remote_name]
# Output: "github", "gitlab", or "git" to stdout
# Exit codes: 0 = success, 1 = failure (no repo or remote)
#
# Environment variables:
#   MANIFEST_GIT_PLATFORM - Force a specific platform (github|gitlab|git)
#   MANIFEST_GIT_REMOTE   - Remote name to check (default: origin)

set -euo pipefail

err() { if [[ -t 2 ]]; then printf '\033[0;31m%s\033[0m\n' "git-platform: $*" >&2; else printf '%s\n' "git-platform: $*" >&2; fi; }

# Allow override via env var
if [[ -n "${MANIFEST_GIT_PLATFORM:-}" ]]; then
    case "${MANIFEST_GIT_PLATFORM}" in
        github | gitlab | git)
            echo "${MANIFEST_GIT_PLATFORM}"
            exit 0
            ;;
        *)
            err "Invalid MANIFEST_GIT_PLATFORM value: ${MANIFEST_GIT_PLATFORM}"
            err "Valid values: github, gitlab, git"
            exit 1
            ;;
    esac
fi

# Determine remote name (arg > env var > default)
remote_name="${1:-${MANIFEST_GIT_REMOTE:-origin}}"

# Check if we're in a git repository
if ! git rev-parse --git-dir &> /dev/null; then
    err "Not a git repository"
    exit 1
fi

# Get remote URL
if ! remote_url=$(git remote get-url "${remote_name}" 2> /dev/null); then
    err "Remote '${remote_name}' not found"
    exit 1
fi

# Detect platform from URL patterns
# Handles SSH (git@), HTTPS, and custom domains
case "${remote_url}" in
    *github.com*)
        echo "github"
        ;;
    *gitlab.com* | *gitlab.*)
        echo "gitlab"
        ;;
    *)
        # Plain git (no recognized hosting platform)
        echo "git"
        ;;
esac

exit 0
