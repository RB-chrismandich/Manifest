#!/bin/bash
printf '%s\n' "$@" >> "$BREW_TEST_CURL_LOG"
out=""
while [[ "$#" -gt 0 ]]; do
    case "$1" in -o | --output)
        out="$2"
        shift
        ;;
    esac
    shift
done
if [[ -n "$out" ]]; then cp "$BREW_TEST_FIXTURE" "$out"; else cat "$BREW_TEST_FIXTURE"; fi
exit "${BREW_TEST_CURL_EXIT:-0}"
