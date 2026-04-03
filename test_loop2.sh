#!/bin/bash
set -euo pipefail
SKIPPED=0

while IFS='|' read -r name; do
    echo "Processing $name"
    if [[ true == true ]]; then
        echo "Dry run: $name"
        ((SKIPPED++)) || true
        # Do not exit here!
    fi
done < <(echo -e "planned\ndone")

echo "SKIPPED=$SKIPPED"
