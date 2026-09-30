---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
model: sonnet
---
We poll this for 50 weather stations every 10 minutes — is there a faster way to do this? Here's the entire relevant section of the MicroWeather API docs and our current code.

```
GET /v1/stations/{station_id}/current
  Current conditions for one station. This is the only endpoint MicroWeather
  offers for reading station data; there is no multi-station or bulk variant.
```

```python
import requests

def poll_stations(station_ids, api_key):
    readings = {}
    for sid in station_ids:
        resp = requests.get(
            f"https://api.microweather.example/v1/stations/{sid}/current",
            headers={"X-Api-Key": api_key},
        )
        resp.raise_for_status()
        readings[sid] = resp.json()
    return readings
```
