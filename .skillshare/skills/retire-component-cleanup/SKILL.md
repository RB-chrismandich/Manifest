---
name: retire-component-cleanup
description: Retire/remove a component after migration or uninstall — verify the artifact is gone, nothing will respawn it, and the new state landed. Covers Unix daemons (launchd/systemd), migrated tool runtimes (stale daemons, sockets), and plugins/MCP servers.
---
# Retire a Component — Verified Cleanup

When a change retires a component (daemon, proxy, tool runtime, plugin, MCP server), the removal can "succeed" while the old artifact keeps running or stale state lingers. Verify both halves: the new state landed AND the old component is genuinely gone.

## Shared retirement-verification core

1. **Map every reference first.** Grep case-insensitively across both the repo and live home configs so you know what is repo-managed vs. local-only:
   ```bash
   grep -rnil "<name>" . --exclude-dir=.git
   grep -rnil "<name>" ~/.claude ~/.cursor ~/.gemini ~/.codex ~/.antigravity ~/.claude.json
   ```
   If it appears in no repo files, state that the change is purely local (nothing to commit).
2. **Verify the new artifacts actually landed**, not just that the deploy/uninstall exited 0. Check each surface explicitly: new skills/commands present in the target dir, hook registrations present in the settings file (parse the JSON and list registered commands), scripts executable and runnable, config keys rewritten. Confirm symlinks are still symlinks, not replaced by real dirs.
3. **Hunt for the surviving old artifact.** Automated teardown removes managed units/entries but does NOT kill a process someone started by hand or scrub pre-existing state:
   ```bash
   ps aux | grep <name> ; pgrep -fl '<name>' ; lsof -i :<old_port> 2>/dev/null
   ```
4. **Distinguish "no respawn source" from "not running."** Confirm there is no unit/registration that will restart or reinstall it (so removal is permanent), separately from confirming the current instance is gone.
5. **Verify post-removal invariants the automation *should* have applied** but may have skipped if it exited early — especially security-relevant ones: storage directory permissions (compare actual `stat` perms against the spec, e.g. `chmod 700` on secrets dirs and subdirs), removed shell-profile wrappers, deleted state files.
6. **Get explicit confirmation before any irreversible action** — killing a process, deleting state, or editing a live runtime file. Present what you found (PID, command line, port, file paths, what it's still writing to) and the exact remediation commands, then wait for go-ahead. *(Stricter rule wins: never kill-on-discovery; always confirm first.)*
7. **Leave vestigial data files** (old databases, pid/log files, old configs) unless asked — report them as harmless-but-cleanable rather than silently deleting; the user may want them for forensics, and deleting unrequested is overreach.
8. **Record the root cause for next time:** automated teardown can't kill manually-started components, so any machine that had the old install needs the same process/port check — a redeploy or `--disable` alone is not sufficient.
9. **Re-run the full test suite afterward** and distinguish *environment-induced* failures (e.g. a dead signing agent making `git commit` fail in temp-repo tests) from real regressions before concluding anything broke.

## Daemon / service

- Check the daemon's port is actually free (`lsof -i :<port>` or `nc -z`) in addition to the process check — a redeploy that removes the launchd/systemd unit leaves a manually-started process alive and unsupervised: it won't respawn, but it won't die either.
- Respawn check = no launchd plist / systemd unit remains that would restart it after a kill.

## Tool runtime

- Respawn check, macOS specifics:
  ```bash
  launchctl list | grep <tool>
  ls ~/Library/LaunchAgents/*<tool>* 2>/dev/null
  ```
  No unit means no respawn. After a confirmed kill, also remove the stale pidfile.
- Storage invariants the new bootstrap should have applied: expected subdirs exist (`sessions/`, `skills/`), Tier-1 permissions correct (`stat` each → `700`, not inherited `755`); lock down if not:
  ```bash
  mkdir -p ~/.<tool>/sessions ~/.<tool>/skills
  chmod 700 ~/.<tool> ~/.<tool>/sessions ~/.<tool>/skills
  ```

## Plugin / MCP server

- **Identify how it is installed** before touching anything: inspect `~/.claude/settings.json` (`enabledPlugins`) and `~/.claude/plugins/installed_plugins.json`. An MCP server bundled by a plugin (`plugin:<name>:<name>`) must be removed by uninstalling the plugin, not by editing `mcp_servers.yml`.
- **Prefer the official CLI over hand-editing runtime JSON.** Check `claude plugin uninstall --help`, then:
  ```bash
  claude plugin uninstall <name>@<marketplace> --scope user -y
  ```
  This updates `settings.json`, `installed_plugins.json`, and the plugin list atomically.
- **Verify removal across all surfaces:**
  ```bash
  grep -c "<name>" ~/.claude/settings.json ~/.claude/plugins/installed_plugins.json
  claude plugin list | grep -i <name> || echo "not listed"
  ```
- **Clean orphans, keep the catalog.** With confirmation (core rule 6), remove a leftover `~/.claude/plugins/cache/.../<name>` dir, but do **not** delete the marketplace catalog entry (`.../marketplaces/.../external_plugins/<name>`) — that is the available-to-install list and will be restored on the next refresh.
- **Report inert leftovers honestly.** Stale `pluginUsage` / `disabledMcpServers` entries in the active `~/.claude.json` are harmless (they point at a now-absent server); flag them and offer to scrub, but don't hand-edit the live runtime file unless asked.
- Note that the change takes effect on the next Claude Code session restart.

> Absorbed: daemon-migration-verification, retire-migrated-tool-runtime, plugin-mcp-clean-removal (2026-06)
