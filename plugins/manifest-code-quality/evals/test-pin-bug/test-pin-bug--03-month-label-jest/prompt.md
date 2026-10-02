---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
model: sonnet
---
Here's our `formatMonthLabel` helper. I know it's off by one — `getMonth()` is 0-indexed and we never add 1 — but half our reports currently depend on that exact off-by-one until we finish a coordinated migration next quarter, so I'm not touching the logic now.

```javascript
function formatMonthLabel(date) {
  return `${date.getMonth()}/${date.getFullYear()}`;
}
```

Add a Jest test for `formatMonthLabel(new Date(2026, 8, 15))` that pins today's behavior but won't explode the suite the day we finally add the `+1` fix.
