#!/usr/bin/env bash
# help-coverage: exempt — internal detection helper; its whole contract is to print
# the detected platform to stdout, so a --help mode would collide with that output.
# ci_platform.sh - Detect CI platform from repository configuration
# Behavioral contract: tests/bats/ci_platform.bats. Keep every consuming bundle's
# independent copy aligned with those public outputs and exit codes.
#
# Usage: ci_platform.sh
# Output: "github-actions", "gitlab-ci", or "none" to stdout
# Exit codes: 0 = success, 1 = failure (invalid override)
#
# Detection (relative to the current working directory):
#   .github/workflows/*.yml or *.yaml present -> github-actions
#   .gitlab-ci.yml present                    -> gitlab-ci
#   both present                              -> prefer whichever platform
#     matches git_platform.sh's remote detection (github -> github-actions,
#     gitlab -> gitlab-ci). If git_platform.sh returns "git" (plain/unknown
#     remote) or fails outright (no remote, not a repo), there is no remote
#     signal to break the tie, so default to github-actions.
#   neither present                           -> none
#
# Environment variables:
#   MANIFEST_CI_PLATFORM - Force a specific platform (github-actions|gitlab-ci|none)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

err() { if [[ -t 2 ]]; then printf '\033[0;31m%s\033[0m\n' "ci-platform: $*" >&2; else printf '%s\n' "ci-platform: $*" >&2; fi; }

# Allow override via env var
if [[ -n "${MANIFEST_CI_PLATFORM:-}" ]]; then
    case "${MANIFEST_CI_PLATFORM}" in
        github-actions | gitlab-ci | none)
            echo "${MANIFEST_CI_PLATFORM}"
            exit 0
            ;;
        *)
            err "Invalid MANIFEST_CI_PLATFORM value: ${MANIFEST_CI_PLATFORM}"
            err "Valid values: github-actions, gitlab-ci, none"
            exit 1
            ;;
    esac
fi

# Detect presence of CI config files in the current working directory
has_github=0
has_gitlab=0

shopt -s nullglob
github_workflows=(.github/workflows/*.yml .github/workflows/*.yaml)
shopt -u nullglob
[[ ${#github_workflows[@]} -gt 0 ]] && has_github=1

[[ -f .gitlab-ci.yml ]] && has_gitlab=1

if [[ "${has_github}" -eq 1 && "${has_gitlab}" -eq 0 ]]; then
    echo "github-actions"
    exit 0
fi

if [[ "${has_github}" -eq 0 && "${has_gitlab}" -eq 1 ]]; then
    echo "gitlab-ci"
    exit 0
fi

if [[ "${has_github}" -eq 1 && "${has_gitlab}" -eq 1 ]]; then
    # Both present: prefer whichever matches git_platform.sh's remote
    # detection. Don't reimplement remote detection here - call it.
    git_platform="$("${SCRIPT_DIR}/git_platform.sh" 2> /dev/null || echo "git")"
    case "${git_platform}" in
        github)
            echo "github-actions"
            ;;
        gitlab)
            echo "gitlab-ci"
            ;;
        *)
            # "git" (plain/unrecognized remote) or detection failure: no
            # remote signal to break the tie. Default deterministically
            # rather than leaving this case undefined.
            echo "github-actions"
            ;;
    esac
    exit 0
fi

echo "none"
exit 0
