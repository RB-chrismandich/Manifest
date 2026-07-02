# Contract: `ai-code-audit` Skill

**Type**: User-invocable skill (`/ai-code-audit`), `.skillshare/skills/ai-code-audit/SKILL.md`
**Registered in**: `command_config.yml` `tool_policies` (policy: `conditional` — sub-agent dispatch only for Critical/High cross-verification)

## Invocation

```text
/ai-code-audit [target-path] [--passes P0..P6|all] [--since <ref>]
```

| Input | Default | Semantics |
|-------|---------|-----------|
| `target-path` | repo root of current session | Local directory to audit (checked-out code only; fetching remote code is out of scope) |
| `--passes` | `all` | Subset execution for re-audits; P0 always runs first regardless of subset |
| `--since <ref>` | none | Restricts P6 (iterative regression) to history after `<ref>` |

## Behavior guarantees

1. **Ordered passes**: P0 → P6 as defined in `data-model.md`; P6 degrades gracefully ("SKIPPED: shallow/no history") rather than failing.
2. **Chunking**: >50 source files → P1–P5 per top-level directory, P0/P6 global, merged report. The report states the chunking applied (no silent truncation).
3. **Registry-driven**: detection cues come from `knowledge_base.yml` guardrail entries, including `session-capture` entries added after ship (capture-to-active with no skill change).
4. **Evidence rule**: no `path:line` + trace → the item appears only under "Unverified observations", never as a defect.
5. **Cross-verification**: every candidate `critical`/`high` finding is re-checked by an independent adversarial sub-agent instructed to refute it from the cited evidence; refuted → downgraded. The report marks which findings were cross-verified.
6. **Non-fabrication**: a clean target yields an empty findings table and an explicit "no Critical/High findings" statement (SC-002 requires zero fabricated findings).

## Report format (skill output)

```markdown
# AI-Code Audit: <target>
**Verdict**: APPROVED | NEEDS_REVIEW | BLOCKED   (mapping per R3)
**Scope**: <N files, M lines; chunking: none|by-directory>; Passes run: P0–P6 (P6 skipped: <reason>)

## Findings
| ID | Severity | Pass | Anti-pattern | Location | Status |
|----|----------|------|--------------|----------|--------|
| F-1 | critical | P3 | ANTI-014 hardcoded secret | src/db.ts:12 | verified (cross-checked) |

### F-1 — <title>
**Evidence trace**: <the followed trace>
**Required action**: <derived from severity>
**Prevention rule**: <from registry entry>

## Unverified observations
- <candidate that lacked evidence or failed cross-verification, with why>

## Capture proposals
- <anti-pattern instances not matching any registry entry — offered for learning_capture.sh>
```

## Verdict mapping (restated from R3 — single source: constitution Quality Gates)

- Any verified `critical` → `BLOCKED`
- Else any verified `high` carrying a Tier 1 guardrail tag (`security`, `error-handling` — the only guardrail categories overlapping constitution Tier 1 domains; the remaining Tier 1 checks, cross-verification and breaking-changes, are PR-process checks outside registry scope) → `BLOCKED`
- Else any verified `high` → `NEEDS_REVIEW`
- Else → `APPROVED` (`medium`/`low`/`info` listed but non-gating)

## Acceptance harness

`tests/fixtures/audit-seeded/` (≤15 files) plants exactly: 1 swallowed async error, 1 hardcoded credential, 1 dead module, 1 single-implementation interface, 1 missing teardown, 1 unvalidated boundary input. Pass criteria: ≥90% of planted instances detected at correct severity (SC-002), zero findings against the fixture's clean files, single invocation end-to-end (SC-006).
