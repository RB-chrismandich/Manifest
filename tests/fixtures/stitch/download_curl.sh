#!/bin/bash
printf '%s\n' "$@" > "$STITCH_TEST_ARGS"
output=""
url=""
while [[ "$#" -gt 0 ]]; do
    case "$1" in
        -o)
            output="$2"
            shift
            ;;
        --url)
            url="$2"
            shift
            ;;
        -*) ;;
        *) url="$1" ;;
    esac
    shift
done
printf 'stdout diagnostic %s\n' "$url"
printf 'stderr diagnostic %s\n' "$url" >&2
printf 'synthetic asset bytes' > "$output"
exit "${STITCH_TEST_EXIT:-0}"
