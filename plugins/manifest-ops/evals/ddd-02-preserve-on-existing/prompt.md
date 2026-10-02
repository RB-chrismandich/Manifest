---
max_turns: 8
timeout_seconds: 240
allowed_tools: [Skill, Read]
model: sonnet
runs: 3
---
(Pasted from our dotfiles deployer repo; you don't have a checkout.)

Last month we added a repo-default MCP server entry `mcpServers.context7` to `configs/claude/settings.json`. On fresh machines and in CI it's there. On everyone's existing laptops it's missing. Deploy logs on those laptops say `settings.json: existing found — preserving (manual merge may be needed)`.

Deployer:
```bash
deploy_settings() {
  local dst="$HOME/.claude/settings.json"
  if [[ -f "$dst" ]]; then
    warn "settings.json: existing found — preserving (manual merge may be needed)"
    return 0
  fi
  cp "$SRC/settings.json" "$dst"
}
```
Users keep their own keys (API tokens, personal permissions) in that file. How do we fix this properly?
