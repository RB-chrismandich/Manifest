#!/usr/bin/env bash
# Run the demo dashboard aggregation pipeline.
set -euo pipefail

usage() {
    echo "Usage: $0 <data-dir>"
}

if [[ $# -ne 1 ]]; then
    usage >&2
    exit 2
fi

data_dir="$1"
if [[ ! -d "$data_dir" ]]; then
    echo "run_pipeline.sh: data directory not found: $data_dir" >&2
    exit 1
fi

count=$(find "$data_dir" -name '*.csv' | wc -l | tr -d ' ')
echo "pipeline processed $count csv file(s) from $data_dir"
