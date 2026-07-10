# Quickstart: Pilotfish-Style Cost-Tiered Model Orchestration

Opt-in, config-only. Enabling deploys six role-agents + a delegation-policy reference to your
Claude home; the main session keeps running your usual frontier model and delegates cheaper
work to cheaper tiers, gating risky results behind a verifier.

## Enable

```bash
./bootstrap.sh --enable-pilotfish
```

This writes `pilotfish.enabled: true` to `~/.claude/config/services.yml` and deploys:

- `~/.claude/agents/{scout,Explore,mech-executor,executor,verifier,security-executor}.md`
- `~/.claude/references/pilotfish-delegation.md`
- a one-line pointer in `~/.claude/CLAUDE.md`'s Reference Index

If a same-named agent file already exists that Manifest didn't deploy, the run **aborts and
names the file** — nothing is overwritten. Resolve the collision, then re-run.

## Verify

```bash
ls ~/.claude/agents/                       # six role files
grep -m1 model ~/.claude/agents/scout.md   # model: haiku  (a built-in alias, not a raw model ID)
sed -n '/pilotfish/p' ~/.claude/CLAUDE.md  # the Reference Index pointer line
```

In your next Claude Code session, a fully-specified mechanical task is delegated to a cheaper
tier while planning/decision stays on the frontier model; mutating/judgment/security results
pass the `verifier` (CONFIRMED/REFUTED) before the orchestrator proceeds. Security-sensitive
work always routes to `security-executor`, never the cheapest tier.

## Re-tier a role (one edit)

Want a role on a cheaper/richer model? Edit that **one** role file's `model:` alias in
`configs/claude/agents/<role>.md` (e.g. `opus` → `sonnet`), then redeploy:

```bash
./bootstrap.sh --enable-pilotfish
```

Only that role changes — no policy-prose or other-role edits. Note: when a model *version* is
superseded, no edit is needed at all — the built-in aliases (`haiku`/`sonnet`/`opus`) float to
the current version automatically.

## Disable (clean reverse)

```bash
./bootstrap.sh --disable-pilotfish
```

Removes exactly the six agents, the reference, and the pointer line — nothing else. Your Claude
home returns to its pre-enable state.

## Notes

- **Does not change your main-session model** — it only adds delegation config (FR-016).
- **Claude-only** in this feature; other assistant homes are unaffected (FR-013).
- Upstream: pilotfish (MIT), vendored v1.1.0; see the header of `pilotfish-delegation.md`.
