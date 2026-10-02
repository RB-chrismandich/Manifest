---
type: llm
weight: 1
---
Score 1 only if the proposed fix stops a missing `PAGERDUTY_TOKEN` from counting as healthy AND makes that state visible: EITHER a distinct skipped/unverified status that is excluded from the "ALL SYSTEMS GREEN" reduction and printed explicitly (e.g. "1 unverified: pagerduty — set PAGERDUTY_TOKEN"), OR fail-closed handling that marks the check failed/errored with the missing-token reason surfaced in the output and a non-zero exit. Score 0 if the missing token can still produce "ALL SYSTEMS GREEN", or if it is turned into a bare False with no reason shown.
