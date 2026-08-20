# Model Selection Policy

> Which model runs a session, a sub-agent, and a turn — and why. Every number
> here is measured, not estimated; the derivation and the reproduce commands are
> in [docs/baselines/2026-07-25-credit-baseline.md](baselines/2026-07-25-credit-baseline.md).

**Last updated**: 2026-07-25
**Measured over**: 47,185 request-deduped API calls, $6,141.64 total spend

---

## The three levers, ranked

| Lever | Scope | Status | Value |
|---|---|---|---|
| Sub-agent model | per dispatch | **Adopted** — enforced | $845 |
| Session start model | per session | **Adopted** — ask-gated | ~$766 |
| Per-turn model routing | per turn | **Rejected on evidence** | **−$1,499** |

---

| Lever | Page |
|-------|------|
| 1 — Sub-agents default to Sonnet | [subagents.md](model-policy/subagents.md) |
| 2 & 3 — Sessions and turns | [sessions.md](model-policy/sessions.md) |
| 4 — Changing a lever | [changing-levers.md](model-policy/changing-levers.md) |
| Cross-harness tiers | [cross-harness.md](model-policy/cross-harness.md) |

## Related

- [docs/baselines/2026-07-25-credit-baseline.md](baselines/2026-07-25-credit-baseline.md)
  — the measurement, with reproduce commands
- [configs/claude/references/sub-agent-dispatch.md](../configs/claude/references/sub-agent-dispatch.md)
  — dispatch mechanism selection and thresholds
- [configs/claude/references/cddl-role-models.md](../configs/claude/references/cddl-role-models.md)
  — per-role tier aliases for CDDL charters
