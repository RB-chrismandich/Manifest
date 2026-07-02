# Quickstart: Proactive Code Guardrails

**Feature**: 457-proactive-code-guardrails

## What ships

1. **Registry**: 33 seeded anti-pattern entries in `configs/claude/config/knowledge_base.yml` (6 categories, per-language detection cues, positive prevention rules).
2. **Write-time guardrails**: compact digest in `configs/claude/CLAUDE.md` (+ mirrored guides) with full detail in `configs/claude/references/antipatterns.md`; `code-quality` skill extended to flag registry anti-patterns as non-blocking advisory feedback.
3. **Audit skill**: `/ai-code-audit <path>` — seven ordered passes, evidence-traced findings, Critical/High cross-verification, APPROVED/NEEDS_REVIEW/BLOCKED verdict.
4. **Capture loop**: `antipattern-detect` / `learning_capture.sh` write new optional fields, so confirmed anti-patterns become active in guidance and audits immediately.

## Try it (after implementation + `./bootstrap.sh`)

```bash
# 1. Registry sanity: schema + coverage invariants
bats tests/bats/knowledge_base_registry.bats

# 2. Capture round-trip with the new fields
bats tests/bats/learning_capture.bats

# 3. Budget guard: auto-loaded guidance still fits
bats tests/bats/context_budget.bats
```

```text
# 4. Behavioral smoke (agent-executed, the Verify-gate critical path):
/ai-code-audit tests/fixtures/audit-seeded
#   PASS iff: ≥90% of the 6 planted defects found at correct severity,
#             0 findings on clean fixture files, verdict = BLOCKED
#             (fixture plants a critical hardcoded credential)

# 5. Write-time prevention spot check: ask an agent for an async fetch
#    helper with error handling; output must not swallow errors, must
#    validate boundary inputs, must not hardcode secrets (SC-003).
```

## Regeneration checklist (before PR)

```bash
configs/claude/scripts/generate_cursor_rules.sh
python3 configs/claude/scripts/generate_commands_doc.py   # COMMANDS.md count/table
pre-commit run --from-ref origin/main --to-ref HEAD       # the REAL changed-file gate
bats tests/bats/ && pytest tests/python/
```

Gemini/Codex/Antigravity guide mirrors and `command_config.yml` `tool_policies` must include the new skill (drift tests will catch omissions).
