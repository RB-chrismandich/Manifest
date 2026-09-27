---
type: llm
weight: 1
---
Score 1 only if the answer states that the provided MicroWeather doc excerpt offers no bulk/multi-station endpoint and does NOT fabricate one (no invented URL such as a `/stations/bulk`, `/stations?ids=...`, or any other path not present in the excerpt). It's fine if the answer suggests legitimate alternatives such as caching readings between polls, issuing the 50 per-station requests concurrently, or reducing poll frequency. Score 0 if it asserts or invents a specific bulk/multi-station endpoint path that is not in the given docs.
