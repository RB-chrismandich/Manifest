---
type: llm
weight: 1
---
Score 1 only if the answer identifies that `GET /v2/fleet/snapshot` returns the
latest telemetry for every vehicle in the account in one (paginated) response
and recommends replacing the per-VIN loop over `GET
/v2/vehicles/{vin}/telemetry` with calls to `/v2/fleet/snapshot`, paginating via
`cursor` until exhausted and filtering to the requested VINs in-process, so the
call count is the account's fleet size ÷ 250 per page rather than ~800 per-VIN
calls. Do not require a specific call count: the snapshot pages over every
vehicle in the account, which can exceed the requested VINs.
Score 0 if the answer says no bulk/multi-vehicle endpoint exists, dismisses
`/v2/fleet/snapshot` as dashboard-only/not applicable to API consumers, only
proposes concurrency/caching/polling-frequency changes while keeping the
per-VIN loop, or invents an endpoint not present in the excerpt.
