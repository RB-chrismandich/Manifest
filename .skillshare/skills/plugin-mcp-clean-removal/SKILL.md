---
name: plugin-mcp-clean-removal
description: Use when removing a Claude Code plugin or its bundled MCP server from a local ~/.claude environment — cleanly uninstall via CLI, verify across all state files, and clean orphans without breaking the marketplace catalog.
---
# Clean Plugin / MCP Server Removal

When asked to "remove X MCP" or "uninstall the X plugin," follow this procedure instead of hand-editing runtime JSON.

1. **Map every reference first.** Grep case-insensitively across both the repo and the live home configs so you know what is repo-managed vs. local-only:
   ```bash
   grep -rnil "<name>" . --exclude-dir=.git
   grep -rnil "<name>" ~/.claude ~/.cursor ~/.gemini ~/.codex ~/.antigravity ~/.claude.json
   ```
   If it appears in no repo files, state that the change is purely local (nothing to commit).
2. **Identify how it is installed.** Inspect `~/.claude/settings.json` (`enabledPlugins`) and `~/.claude/plugins/installed_plugins.json`. An MCP server bundled by a plugin (`plugin:<name>:<name>`) must be removed by uninstalling the plugin, not by editing `mcp_servers.yml`.
3. **Prefer the official CLI over editing JSON.** Check `claude plugin uninstall --help`, then:
   ```bash
   claude plugin uninstall <name>@<marketplace> --scope user -y
   ```
   This updates `settings.json`, `installed_plugins.json`, and the plugin list atomically.
4. **Verify removal across all surfaces:**
   ```bash
   grep -c "<name>" ~/.claude/settings.json ~/.claude/plugins/installed_plugins.json
   claude plugin list | grep -i <name> || echo "not listed"
   ```
5. **Clean orphans, keep the catalog.** Remove a leftover `~/.claude/plugins/cache/.../<name>` dir. Do **not** delete the marketplace catalog entry (`.../marketplaces/.../external_plugins/<name>`) — that is the available-to-install list and will just be restored on the next refresh.
6. **Report inert leftovers honestly.** Stale `pluginUsage` / `disabledMcpServers` entries in the active `~/.claude.json` are harmless (they point at a now-absent server); flag them and offer to scrub, but avoid hand-editing the live runtime file unless asked.
7. Note that the change takes effect on the next Claude Code session restart.
