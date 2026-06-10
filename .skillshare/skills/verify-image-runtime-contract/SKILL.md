---
name: verify-image-runtime-contract
description: Use before configuring a third-party container/tool via env vars or config keys you haven't confirmed it reads — verify the actual runtime contract (entrypoint, supported vars) instead of reasoning by analogy.
---
# Verify a Tool's Runtime Contract Before Configuring It

Prevents the failure mode where one working setting (`QBT_WEBUI_PORT`) creates a false analogy that a whole family of settings (`QBT_WEBUI_AUTHSUBNETWHITELIST*`) must also be honored — wasting multiple deploy/PR cycles on config the image silently ignores.

1. **Before adding env vars or config keys, confirm the binary actually reads them.** Reason-by-analogy ("`X_PORT` works, so `X_*` must map to config") is the trap. A working setting often works via a *specific* CLI flag (`--webui-port=`), not a generic env→config mapping.

2. **Read the source of truth, not the docs.** For a container, dump and read the entrypoint script:
   `docker run --rm --entrypoint="" <image> cat /entrypoint.sh` (or `sh -c 'cat $(command -v docker-entrypoint.sh)'`). Enumerate exactly which env vars it handles.

3. **If the setting isn't supported by the entrypoint, patch the config file directly** rather than passing an ignored env var. Use an `entrypoint:` wrapper that idempotently appends the setting before `exec`-ing the original entrypoint:
   ```sh
   cfg=/config/app.conf
   grep -q 'SettingKey' "$cfg" || printf '\nSettingKey=value\n' >> "$cfg"
   exec /entrypoint.sh "$@"
   ```
   Guard with `grep -q` so restarts don't accumulate duplicate lines.

4. **Verify on the real target, not just locally.** A passing local config-validate does not prove the setting took effect on the deployed host — SSH in (or check live logs / API response) and confirm the observed behavior (e.g. the endpoint stops returning `Forbidden`).

5. **Distinguish the request paths.** When a service is reachable both directly (Docker network) and via a reverse proxy, a source-IP allowlist applies only to the direct path — the proxy presents its own IP. Decide per-path whether the bypass should apply, and never widen an allowlist to the proxy IP (it would bypass auth for all proxied traffic).
