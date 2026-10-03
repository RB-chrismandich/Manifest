---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
model: sonnet
---
We poll telemetry for about 800 vehicles every 5 minutes and polling is falling
behind schedule. Here's the full "Vehicles" and "Fleet" sections of the
FleetPulse API docs and our current polling code — what should change?

```
## Vehicles

GET /v2/vehicles/{vin}/telemetry
  Latest telemetry reading for a single vehicle.

## Fleet

GET /v2/fleet/snapshot
  Point-in-time read backing the FleetPulse live dashboard; also available to
  API consumers. Returns the latest telemetry reading for every vehicle in the
  account in one response. Paginate large fleets via `?cursor=`; each page
  returns up to 250 vehicles.
```

```python
import requests

def poll_fleet(vins, api_key):
    readings = {}
    for vin in vins:
        resp = requests.get(
            f"https://api.fleetpulse.example/v2/vehicles/{vin}/telemetry",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        resp.raise_for_status()
        readings[vin] = resp.json()
    return readings
```
