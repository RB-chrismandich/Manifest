---
max_turns: 8
timeout_seconds: 240
allowed_tools: [Skill, Read]
model: sonnet
runs: 3
---
(macOS) We replaced our launchd-managed `llm-proxy` (listened on :4000, plist `~/Library/LaunchAgents/com.acme.llm-proxy.plist`) with a new proxy on :4100. I ran `./bootstrap.sh --disable-proxy` and it exited 0. Is the old one fully gone? What exactly should I check?
