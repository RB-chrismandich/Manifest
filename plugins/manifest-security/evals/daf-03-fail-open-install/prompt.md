---
max_turns: 8
timeout_seconds: 240
allowed_tools: [Skill, Read, Glob, Grep]
model: sonnet
runs: 3
---
Can you check the firewall part of our provisioning script? The redis container publishes 6379.

```bash
if ! command -v iptables >/dev/null; then
  echo "WARN: iptables not found, skipping firewall" >&2
else
  iptables -I DOCKER-USER -p tcp --dport 6379 -j DROP 2>/dev/null
  iptables -I DOCKER-USER -p tcp --dport 6379 -s 10.1.0.0/16 -j RETURN 2>/dev/null
fi
docker run -d -p 6379:6379 redis:7
echo "✅ redis provisioned (firewalled)"
```
This runs from our CI deploy user.
