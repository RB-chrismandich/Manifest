# Model Selection Policy

> Which model runs a session, a sub-agent, and a turn — and why. Request/token
> counts are historical observations; dollar equivalents and savings are estimates.
> The derivation and the reproduce commands are
> in [docs/baselines/2026-07-25-credit-baseline.md](baselines/2026-07-25-credit-baseline.md).

**Last updated**: 2026-09-08
**Historical baseline**: 47,185 request-deduped API calls, $6,141.64 estimated API-equivalent cost

Current dispatch coverage, migration and rollback:
[September dispatch increment](model-policy/dispatch-reliability.md).
Deterministic tests establish implementation behavior, not post-deployment savings.

---

## The three levers, ranked

| Lever | Scope | Status | Value |
|---|---|---|---|
| Sub-agent model | per dispatch | **Adopted** — version-gated native default; serving verification pending | $845 counterfactual |
| Session start model | per session | **Historical ask-gate retired**; current default unchanged | ~$766 historical counterfactual |
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
