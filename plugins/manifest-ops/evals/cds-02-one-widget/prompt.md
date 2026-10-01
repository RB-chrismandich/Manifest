---
max_turns: 6
timeout_seconds: 180
allowed_tools: [Skill, Read]
model: sonnet
runs: 3
---
(Pasted from my server; you don't have the files.)

My self-hosted dashboard mostly works, but the weather widget shows `invalid value <nil>` and the rest of the page is fine. The dashboard config has:

```yaml
- type: weather
  location: Denver, US
  api-key: ${WEATHER_API_KEY}
```

`WEATHER_API_KEY` is set in my `.env` and `docker compose config` shows no warnings. The compose service's `environment:` block has `TZ` and `DOMAIN` only. Why does just this widget break?
