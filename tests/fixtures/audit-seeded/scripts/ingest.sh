#!/usr/bin/env bash
# Ingest a scores CSV into the demo dashboard data directory.
set -euo pipefail

src_file="$1"
dest_name="$2"

data_dir="$(dirname "$0")/../data"
mkdir -p "$data_dir"

cp "$src_file" "$data_dir/$dest_name.csv"
echo "ingested $src_file as $dest_name.csv"
