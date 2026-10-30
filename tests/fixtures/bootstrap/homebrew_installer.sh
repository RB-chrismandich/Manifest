#!/bin/bash
[[ "$(LC_ALL=C ls -ld "$(dirname "$0")")" == drwx------* ]] || exit 44
printf '%s\n' "$0" > "$BREW_TEST_PATH"
printf 'synthetic installer\n' > "$BREW_TEST_MARKER"
exit "${BREW_TEST_INSTALL_EXIT:-0}"
