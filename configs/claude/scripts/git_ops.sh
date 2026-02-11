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
#   issue-comment-edit-last N  Edit last comment on issue/MR N
#   issue-close N         Close issue/MR N
#   issue-edit N          Edit issue/MR N
#   pr-create             Create pull/merge request
#   pr-view N             View PR/MR N
#   pr-list               List PRs/MRs
#   pr-review N           Review/approve PR/MR N
#   pr-merge N            Merge PR/MR N
#   release-create        Create a release
#   release-list          List releases
#   label-create          Create label
#   label-list            List labels
#   label-sync            Sync labels from registry to platform

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
    echo "  issue-comment-edit-last N  Edit last comment on issue/MR N" >&2
    echo "  issue-close N      Close issue/MR N" >&2
    echo "  issue-edit N       Edit issue/MR N" >&2
    echo "  pr-create          Create pull/merge request" >&2
    echo "  pr-view N          View PR/MR N" >&2
    echo "  pr-list            List PRs/MRs" >&2
    echo "  pr-review N        Review/approve PR/MR N" >&2
    echo "  pr-merge N         Merge PR/MR N" >&2
    echo "  release-create     Create a release" >&2
    echo "  release-list       List releases" >&2
    echo "  label-create       Create label" >&2
    echo "  label-list         List labels" >&2
    echo "  label-sync         Sync labels from registry" >&2
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
            issue-comment-edit-last)
                gh issue comment "$@" --edit-last
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
            pr-review)
                gh pr review "$@"
                ;;
            pr-merge)
                gh pr merge "$@"
                ;;
            release-create)
                gh release create "$@"
                ;;
            release-list)
                gh release list "$@"
                ;;
            label-create)
                gh label create "$@"
                ;;
            label-list)
                gh label list "$@"
                ;;
            label-sync)
                bash "${SCRIPT_DIR}/label_sync.sh" "$@"
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
            issue-comment-edit-last)
                issue_num="$1"
                shift
                last_note_id=$(glab api "projects/:id/issues/${issue_num}/notes?sort=desc&per_page=1" --jq '.[0].id')
                if [[ -n "${last_note_id}" ]]; then
                    body=""
                    while [[ $# -gt 0 ]]; do
                        case "$1" in
                            --body | -b)
                                body="$2"
                                shift 2
                                ;;
                            *) shift ;;
                        esac
                    done
                    glab api "projects/:id/issues/${issue_num}/notes/${last_note_id}" -X PUT -f "body=${body}"
                else
                    echo "Error: No comments found on issue ${issue_num}" >&2
                    exit 1
                fi
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
            pr-review)
                # GitLab uses 'mr approve' instead of 'pr review'
                glab mr approve "$@"
                ;;
            pr-merge)
                glab mr merge "$@"
                ;;
            release-create)
                glab release create "$@"
                ;;
            release-list)
                glab release list "$@"
                ;;
            label-create)
                glab label create "$@"
                ;;
            label-list)
                glab label list "$@"
                ;;
            label-sync)
                bash "${SCRIPT_DIR}/label_sync.sh" "$@"
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
            issue-* | pr-* | release-* | label-*)
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
