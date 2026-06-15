#!/bin/bash
found=0
for f in "$@"; do
    out=$(grep -nE "catch\s*\{" "$f" || true)
    if [ -n "$out" ]; then
        echo "Found empty/bindingless catch in $f:"
        echo "$out"
        echo "Please use 'catch (e) {' and explicitly handle the error."
        found=1
    fi
done
if [ "$found" -eq 1 ]; then
  return 1 2>/dev/null || exit 1
else
  return 0 2>/dev/null || exit 0
fi
