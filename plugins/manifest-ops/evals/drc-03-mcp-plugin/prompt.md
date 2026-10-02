---
max_turns: 8
timeout_seconds: 240
allowed_tools: [Skill, Read]
model: sonnet
runs: 3
---
I want to get rid of the `acme` MCP server in Claude Code. I deleted its entry from our `mcp_servers.yml` and redeployed, but `/mcp` still lists `plugin:acme-tools:acme`. How do I remove it cleanly?
