# Contract: Delegation-Policy Reference

**Surface**: `configs/claude/references/pilotfish-delegation.md` → `~/.claude/references/`,
pointed to by one line in `configs/claude/CLAUDE.md`'s Reference Index. Consumer: the
orchestrator (main session), read on demand before delegating cost-tiered work.

## Required sections (normative)

1. **Header** — upstream attribution: pilotfish (https://github.com/Nanako0129/pilotfish),
   MIT, vendored version `v1.1.0` + date (FR-011).
2. **Model alias note** — roles use built-in Claude Code aliases (`haiku`/`sonnet`/`opus`),
   which float to current versions (`opus`→Opus 4.8, `sonnet`→Sonnet 5, `haiku`→Haiku 4.5); no
   custom alias file or `settings.json` change is deployed (data-model Entity 2; FR-016).
3. **Role table** — role → built-in alias → effort (data-model Entity 1).
4. **Delegation rules** — start at the cheapest capable role; escalate after repeated failure;
   always set an explicit `model` alias on a delegation.
5. **Selective verification rule** — gate mutating, judgment, and security work behind the
   `verifier`; MAY skip pure read-only lookups (scout/Explore) (FR-003).
6. **Security-routing rule** — security-sensitive work → `security-executor`, never the
   cheapest tier (FR-004); starter cue set: auth, crypto, secrets, input validation.

## Invariants (testable)

- **INV-1**: `configs/claude/CLAUDE.md` gains **exactly one** Reference Index line pointing at
  this file, and stays under its `context_budget.bats` cap afterward (FR-009).
- **INV-2**: The full policy prose is NOT present in `configs/claude/CLAUDE.md` (FR-014) — only
  the pointer.
- **INV-3**: Every `model` value in the role table is a built-in Claude Code alias
  (`haiku`/`sonnet`/`opus`) — no custom tier name; model availability/fallback is Claude Code's
  responsibility (FR-007), documented not implemented.
- **INV-4**: The selective-verify rule names read-only lookups as skippable and mutating/
  judgment/security as gated (FR-003, clarify Q2).
- **INV-5**: The security-routing rule is present and unweakened (FR-004) — a guardrail;
  removing/softening it is a spec violation.
