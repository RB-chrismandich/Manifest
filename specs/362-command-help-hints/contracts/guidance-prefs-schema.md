# Contract: Guidance Preferences Schema (`guidance.yml`)

Two-layer configuration (FR-007, clarify Q4, SC-004):
- **Shipped defaults** — committed `configs/claude/config/guidance.yml` (all-enabled, shown below).
- **User override** — gitignored `~/.claude/config/guidance_local.yml`, created on first toggle.
- **Effective prefs = defaults ← user override** (local wins, per field). A single opt-out
  toggle writes only the local file, so it never dirties the tracked tree.

## Schema

```yaml
# guidance.yml — defaults shown
enabled: true                 # global kill-switch; false ⇒ suppress everything
categories:
  hints: true                 # contextual workflow hints
  reminders: true             # best-practice reminders
  discovery: true             # PROACTIVE discovery only (guide injection / unsolicited suggestions); on-demand /help is always available
verbosity: normal             # quiet | normal | verbose
rate_limit:                   # optional per-moment overrides of rule defaults
  high-context: 30m
```

## Gating contract (authoritative resolution order)

A hint/reminder is surfaced **iff** ALL hold:
1. `enabled == true`
2. its `categories.<hint|reminder|discovery> == true`
3. its level ≥ the `verbosity` gate (`quiet` shows fewest; `verbose` shows all)
4. for `reminder` category: the `rate_limit` window for that `moment_id` has elapsed

Any failure ⇒ suppressed silently (exit 0). Disabling MUST be reliably respected — a single
opt-out yields zero subsequent surfaced items (SC-004).

## Runtime state (not in this file, not committed)

`last_fired[moment_id]` timestamps live under `~/.claude/state/guidance/` (D5). Absent/unreadable
state ⇒ treat as "never fired" (fail-open).

## Validation

| Field | Constraint |
|-------|-----------|
| `enabled`, `categories.*` | boolean |
| `verbosity` | one of `quiet`\|`normal`\|`verbose` |
| `rate_limit.<id>` | duration string (`30m`, `2h`); `id` must be a known moment |
