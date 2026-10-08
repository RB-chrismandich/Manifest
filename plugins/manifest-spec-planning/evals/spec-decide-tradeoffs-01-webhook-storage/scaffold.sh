#!/usr/bin/env bash
set -euo pipefail
mkdir -p specs/webhook
cat > specs/webhook/design.md <<'EOF'
# Webhook delivery storage

## Context
We need to retain delivery attempts and let operators explain/replay a failed delivery. Payload bodies may be stored separately; this decision concerns attempt metadata and status history.

## Options
A. Keep one mutable row per delivery and overwrite its status/timestamp on each retry. This keeps the current state small and cheap to read.
B. Append one immutable attempt row per retry and derive the current state from the latest attempt. This preserves the history but requires more rows and a latest-attempt query or summary.

## Decisions
EOF
