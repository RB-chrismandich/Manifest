---
max_turns: 8
timeout_seconds: 240
allowed_tools: [Skill, Read, Glob, Grep]
model: sonnet
runs: 3
---
Review our deploy script's firewall — it's supposed to make the metrics service reachable only from our Prometheus box (10.0.4.20).

docker-compose.yml:
```yaml
services:
  metrics:
    image: acme/metrics:1.8
    ports:
      - "9100:9100"
```
deploy.sh:
```bash
docker compose up -d
iptables -I INPUT -p tcp --dport 9100 -j DROP
iptables -I INPUT -p tcp --dport 9100 -s 10.0.4.20 -j ACCEPT
echo "✅ metrics locked down to Prometheus"
```
