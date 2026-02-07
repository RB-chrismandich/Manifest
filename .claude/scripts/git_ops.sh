#!/usr/bin/env bash
# git_ops.sh - Platform-agnostic Git operations wrapper
#
# Routes Git operations (issue/PR management) to the appropriate CLI tool:
# - GitHub: gh
# - GitLab: glab
# - Plain git: warn and suggest installation
#
# Usage: git_ops.sh <subcommand> [args...]
#
# Subcommands:
#   issue-view N          View issue/MR N
#   issue-list            List issues/MRs
#   issue-create          Create new issue/MR
#   issue-comment N       Add comment/note to issue/MR N
#   issue-close N         Close issue/MR N
#   issue-edit N          Edit issue/MR N
#   pr-create             Create pull/merge request
#   pr-view N             View PR/MR N
#   pr-list               List PRs/MRs
#   label-create          Create label

set -euo pipefail

# Get script directory for sourcing git_platform.sh
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Source platform detection
if [[ ! -f "${SCRIPT_DIR}/git_platform.sh" ]]; then
    echo "Error: git_platform.sh not found in ${SCRIPT_DIR}" >&2
    exit 1
fi

# Detect platform
if ! platform=$(bash "${SCRIPT_DIR}/git_platform.sh" 2>&1); then
    echo "Error: Failed to detect Git platform: ${platform}" >&2
    exit 1
fi

# Validate subcommand
if [[ $# -eq 0 ]]; then
    echo "Usage: git_ops.sh <subcommand> [args...]" >&2
    echo "" >&2
    echo "Subcommands:" >&2
    echo "  issue-view N       View issue/MR N" >&2
    echo "  issue-list         List issues/MRs" >&2
    echo "  issue-create       Create new issue/MR" >&2
    echo "  issue-comment N    Add comment/note to issue/MR N" >&2
    echo "  issue-close N      Close issue/MR N" >&2
    echo "  issue-edit N       Edit issue/MR N" >&2
    echo "  pr-create          Create pull/merge request" >&2
    echo "  pr-view N          View PR/MR N" >&2
    echo "  pr-list            List PRs/MRs" >&2
    echo "  label-create       Create label" >&2
    exit 1
fi

subcommand="$1"
shift

# Helper: Check if command exists
command_exists() {
    command -v "$1" &> /dev/null
}

# Helper: Warn about missing CLI tool
warn_missing_tool() {
    local tool="$1"
    local install_hint="$2"
    echo "Warning: ${tool} CLI not found. Install it to enable this operation." >&2
    echo "Install: ${install_hint}" >&2
    exit 1
}

# Helper: Fallback for plain git (no issue tracker)
warn_no_tracker() {
    echo "Warning: No issue tracker detected (plain git remote)." >&2
    echo "This operation requires GitHub (gh) or GitLab (glab) CLI." >&2
    exit 1
}

# Route operations based on platform and subcommand
case "${platform}" in
    github)
        if ! command_exists gh; then
            warn_missing_tool "GitHub" "brew install gh  # or: npm install -g @github/gh-cli"
        fi

        case "${subcommand}" in
            issue-view)
                gh issue view "$@"
                ;;
            issue-list)
                gh issue list "$@"
                ;;
            issue-create)
                gh issue create "$@"
                ;;
            issue-comment)
                gh issue comment "$@"
                ;;
            issue-close)
                gh issue close "$@"
                ;;
            issue-edit)
                gh issue edit "$@"
                ;;
            pr-create)
                gh pr create "$@"
                ;;
            pr-view)
                gh pr view "$@"
                ;;
            pr-list)
                gh pr list "$@"
                ;;
            label-create)
                gh label create "$@"
                ;;
            *)
                echo "Error: Unknown subcommand: ${subcommand}" >&2
                exit 1
                ;;
        esac
        ;;

    gitlab)
        if ! command_exists glab; then
            warn_missing_tool "GitLab" "brew install glab  # or: pip install python-gitlab-cli"
        fi

        case "${subcommand}" in
            issue-view)
                glab issue view "$@"
                ;;
            issue-list)
                glab issue list "$@"
                ;;
            issue-create)
                glab issue create "$@"
                ;;
            issue-comment)
                # GitLab uses 'note' instead of 'comment'
                glab issue note "$@"
                ;;
            issue-close)
                glab issue close "$@"
                ;;
            issue-edit)
                # GitLab uses 'update' instead of 'edit'
                glab issue update "$@"
                ;;
            pr-create)
                # GitLab uses 'mr' (merge request) instead of 'pr'
                glab mr create "$@"
                ;;
            pr-view)
                glab mr view "$@"
                ;;
            pr-list)
                glab mr list "$@"
                ;;
            label-create)
                glab label create "$@"
                ;;
            *)
                echo "Error: Unknown subcommand: ${subcommand}" >&2
                exit 1
                ;;
        esac
        ;;

    git)
        # Plain git remote - no issue tracker available
        case "${subcommand}" in
            issue-* | pr-* | label-*)
                warn_no_tracker
                ;;
            *)
                echo "Error: Unknown subcommand: ${subcommand}" >&2
                exit 1
                ;;
        esac
        ;;

    *)
        echo "Error: Unknown platform: ${platform}" >&2
        exit 1
        ;;
esac

exit 0
