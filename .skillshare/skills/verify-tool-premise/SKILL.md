---
name: verify-tool-premise
description: Use before designing config or code around a CLI flag, env var, or binary — confirm it actually exists and is consumed by reading the source of truth, never reasoning by analogy from a sibling option.
---
# Verify the Tool Premise Before Building On It

A working sibling option (e.g. `QBT_WEBUI_PORT`) does NOT imply a generic mapping (e.g. `QBT_WEBUI_AUTHSUBNETWHITELIST`). Building on an assumed-but-ignored flag produces silent no-ops, repeated failed deploys, and misleading audit trails.

1. When tempted to add `SOME_ENV=x` or `--some-flag` because a related one works, STOP. Treat the assumption as unverified.
2. Read the actual source of truth, not the analogy: the image entrypoint (`docker run --rm --entrypoint="" <image> sh -c 'cat /entrypoint.sh'`), `--help` output, or upstream source/docs.
3. Grep that source for the exact name. If the variable/flag is not referenced, it is silently ignored — your change does nothing.
4. If unsupported, switch to the real mechanism: patch the config file (an entrypoint wrapper that appends settings before exec'ing the original entrypoint, guarded by an idempotency grep), or use the documented flag/path.
5. Validate the change took effect on the live target — grep the rendered config or hit the endpoint and inspect the response — not merely that the deploy exited 0.
6. Commit only after behavior is confirmed, so the history reflects verified facts rather than guesses.
