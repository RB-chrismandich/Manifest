---
name: retire-migrated-tool-runtime
description: Use after migrating off an external tool (proxy/daemon model) to confirm its leftover runtime is gone — stale daemons, sockets, launchd units, and unlocked storage the new code won't clean up.
---
# Retire a Migrated Tool's Leftover Runtime

After replacing a daemon/proxy-based tool with a passive/in-repo model, the new
bootstrap removes managed units but cannot kill a **manually-started** daemon or
fix pre-existing state. Verify the old runtime is actually gone.

1. **Hunt for a surviving daemon/process.** The migration may only remove launchd/
   systemd units, leaving a hand-started process alive:
   ```bash
   pgrep -fl '<tool>' ; lsof -i :<old_port> 2>/dev/null
   ```
   If found, confirm what it is, then kill it and remove its stale pidfile.
2. **Confirm nothing will respawn it:** `launchctl list | grep <tool>`,
   `ls ~/Library/LaunchAgents/*<tool>* 2>/dev/null` — no unit means no respawn.
3. **Verify the new storage invariants the bootstrap *should* have applied** but
   may have skipped if it exited early (e.g. after deploy, before tool setup):
   - expected subdirs exist (`sessions/`, `skills/`),
   - Tier-1 permissions are correct (`stat` each → `700`, not inherited `755`),
   - lock them down if not:
     ```bash
     mkdir -p ~/.<tool>/sessions ~/.<tool>/skills
     chmod 700 ~/.<tool> ~/.<tool>/sessions ~/.<tool>/skills
     ```
4. **Leave vestigial data files** (old `dashboard.db`, `config.yaml`) unless asked
   — they're harmless and nothing reads them; deleting unrequested is overreach.
5. **Get explicit go-ahead before killing a process** (it's a non-reversible system
   change), and note the root cause for next time (a manual daemon survives
   `--disable`/`--enable`, so re-check on every machine that had the old install).
6. **Re-run the full test suite** afterward and distinguish *environment-induced*
   failures (e.g. a dead signing agent making `git commit` fail in temp-repo tests)
   from real regressions before concluding anything broke.
