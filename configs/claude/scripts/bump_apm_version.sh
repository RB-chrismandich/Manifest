#!/usr/bin/env bash
# bump_apm_version.sh - Bump the `version:` field in apm.yml in place
#
# Usage: bump_apm_version.sh [patch|minor|major] [--file PATH] [--print]
#
#   patch|minor|major   Semver segment to bump (default: patch).
#   --file PATH         apm.yml to bump (default: ./apm.yml).
#   --print             Print the new version to stdout instead of writing
#                        the file (no mutation).
#
# Reads the top-level `version: X.Y.Z` line, increments the requested
# segment (resetting lower segments to 0), and rewrites the line in place.
# Exits non-zero with an err() message if the version line is missing or
# not a bare X.Y.Z semver.
#
# Exit codes: 0 = success; 2 = usage/parse error.

set -euo pipefail

err() { echo "bump_apm_version.sh: $*" >&2; }

usage() {
    sed -n '3,15p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

BUMP="patch"
FILE="apm.yml"
PRINT_ONLY=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --help | -h)
            usage
            exit 0
            ;;
        patch | minor | major)
            BUMP="$1"
            shift
            ;;
        --file)
            FILE="${2:-}"
            [[ -n "$FILE" ]] || {
                err "--file requires a path"
                exit 2
            }
            shift 2
            ;;
        --print)
            PRINT_ONLY=true
            shift
            ;;
        *)
            err "unrecognized argument: $1"
            exit 2
            ;;
    esac
done

[[ -f "$FILE" ]] || {
    err "no such file: $FILE"
    exit 2
}

VERSION_LINE="$(grep -m1 '^version: ' "$FILE" || true)"
[[ -n "$VERSION_LINE" ]] || {
    err "no top-level 'version:' line found in $FILE"
    exit 2
}

CURRENT="${VERSION_LINE#version: }"
CURRENT="${CURRENT%%[[:space:]]*}"

if [[ ! "$CURRENT" =~ ^([0-9]+)\.([0-9]+)\.([0-9]+)$ ]]; then
    err "unparseable version '$CURRENT' in $FILE (expected X.Y.Z)"
    exit 2
fi

MAJOR="${BASH_REMATCH[1]}"
MINOR="${BASH_REMATCH[2]}"
PATCH="${BASH_REMATCH[3]}"

case "$BUMP" in
    major)
        MAJOR=$((MAJOR + 1))
        MINOR=0
        PATCH=0
        ;;
    minor)
        MINOR=$((MINOR + 1))
        PATCH=0
        ;;
    patch)
        PATCH=$((PATCH + 1))
        ;;
esac

NEW_VERSION="${MAJOR}.${MINOR}.${PATCH}"

if [[ "$PRINT_ONLY" == true ]]; then
    echo "$NEW_VERSION"
    exit 0
fi

TMP_FILE="$(mktemp "${FILE}.XXXXXX")"
trap 'rm -f "$TMP_FILE"' EXIT

awk -v new="version: ${NEW_VERSION}" '
  !done && $0 ~ /^version: / { print new; done = 1; next }
  { print }
' "$FILE" > "$TMP_FILE"

mv "$TMP_FILE" "$FILE"
trap - EXIT

echo "$NEW_VERSION"
