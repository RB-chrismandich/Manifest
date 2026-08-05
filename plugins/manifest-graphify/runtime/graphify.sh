#!/usr/bin/env bash
# Keep the network-dependent Graphify acquisition boundary explicit at runtime.
set -euo pipefail

if [[ "${UV_NO_NETWORK:-}" == "1" ]] || ! command -v graphify > /dev/null 2>&1; then
    echo "OFFLINE: manifest-graphify:executable:graphify requires network" >&2
    exit 4
fi

exec graphify "$@"
