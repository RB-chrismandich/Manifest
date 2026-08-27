---
name: ai-code-audit
description: "Seven-pass audit of a codebase for AI-generation defects (architecture, async/state, error handling, security, logic, quality, iteration): evidence-traced, severity-classified, cross-verified findings. Use for \"audit this codebase\", \"find vibe-coding/AI antipatterns\"."
---

# AI-Code Audit (seven-pass guardrail audit)

Structured audit of a **local** codebase for the defects characteristic of
AI-generated/iterated code, driven by the XDG-owned guardrail records exposed
through `manifest-workspace:learning-capture` and reported in the repo's standard verdict
vocabulary. Analysis-only: never modify the target.

## Invocation

```text
/ai-code-audit [target-path] [--passes P0..P6|all] [--since <ref>]
```

| Input | Default | Meaning |
|-------|---------|---------|
| `target-path` | current repo root | Local directory to audit (check out remote code first) |
| `--passes` | `all` | Subset for re-audits (e.g. `P3` only). P0 always runs first |
| `--since <ref>` | none | Restrict P6 history analysis to commits after `<ref>`. Scopes ONLY P6 — all other passes audit the full working tree |

## Operating principles

1. **Do not trust appearance of correctness.** Trace execution and data flows;
   never report from surface pattern-matches alone.
2. **Evidence rule (hard)**: a defect finding REQUIRES a `path:line` location
   plus the trace that confirms it (e.g., "catch at x.ts:41 logs and returns
   undefined; caller y.ts:12 dereferences the result"). Anything less goes
   under **Unverified observations**, never in the findings table. For
   minified/bundled artifacts where line numbers are meaningless, cite the
   pre-bundle source (or source map) if traceable; otherwise record in P0:
   "bundled artifact — source-level audit not possible".
3. **Registry-driven**: run
   `manifest-workspace:learning-capture query --category antipattern --format json`
   before starting. Use entries tagged `arch`, `async-state`, `error-handling`,
   `security`, `dependency`, or `iteration` — including
   `provenance: session-capture` records — and apply their `detection_cue`s per
   pass.
4. **No fabrication**: a clean target yields an empty findings table and an
   explicit "no Critical/High findings" statement. Never invent defects to
   appear thorough.
5. **Scale honestly**: if the target exceeds ~50 source files, chunk by
   top-level directory — run P1–P5 per chunk, P0 and P6 globally, merge
   results — and STATE the chunking in the report header. Never silently
   truncate coverage. On merge, deduplicate by (anti-pattern, path,
   line-range) — cross-cutting findings spanning chunks (e.g., ANTI-011
   duplicates) are one finding, not one per chunk — then renumber F-N.

## Passes (fixed order)

| # | Pass | Hunt for | Evidence requirement |
|---|------|----------|----------------------|
| P0 | Inventory / orientation | Module map (imports/exports/callers), >5-import god modules, >10-consumer hotspots, AI-authorship markers (near-duplicates, style switches, unresolved TODOs) | Structural map cited by later passes |
| P1 | Architectural integrity | Dead modules (ANTI-010), orphan state decls (ANTI-017), pattern abandonment (ANTI-034), cosmetic abstractions (ANTI-008), broken abstractions (ANTI-009), monoliths (ANTI-007) | Caller/usage trace per flag; for abstractions: "would removal change behavior?" |
| P2 | Async & state lifecycle | Unhandled async ops (ANTI-016), swallowed errors in async flows (ANTI-021), races (ANTI-019), missing teardown (ANTI-018), empty/null/single-item boundary gaps (ANTI-020) | Trace catch→resolution, mount→teardown, or interleaving scenario |
| P3 | Security | Secrets (ANTI-025), injection (ANTI-001), resource-level authz/IDOR (ANTI-026), weak crypto (ANTI-027), CORS/headers (ANTI-028), data-in-logs (ANTI-029), temp files (ANTI-002); dependency existence/advisories (ANTI-030/031) | Source→sink trace; for deps: registry lookup result |
| P4 | Logic / business-rule integrity | Always-true/false or wrongly-ordered conditionals, inconsistent return types, missing entry-boundary validation incl. script/CLI positional args (ANTI-024 — a `set -u` crash or quoting is not validation; entry points owe a usage error), multi-step ops without rollback, shared-state invariants | Input-space or path enumeration for each flag |
| P5 | Quality / maintainability | 10+-line duplicates (ANTI-011), cyclomatic >10 / cognitive >15, presence-only tests (ANTI-015), log hygiene, env-var use without startup validation (ANTI-032) | Metric value or concrete instance |
| P6 | Iterative regression | Commits where security-sensitive code was modified: removed/weakened controls (ANTI-033), cross-session boundary drift (ANTI-034) | Commit-level before/after diff. If history is shallow/absent: report "P6 SKIPPED: <reason>" — never fail the audit |

## Cross-verification (critical/high only)

Before reporting, every candidate `critical` or `high` finding gets an
independent adversarial re-check: dispatch one native Task sub-agent or invoke
`manifest-workspace:parallel-agent` with ONLY the cited evidence and
the instruction to **refute** the finding. Refuted — or the evidence cannot be
re-confirmed — → downgrade to **Unverified observations** (a status change —
never re-label the severity) or drop. Mark surviving findings "verified
(cross-checked)". `medium` and below rely on the evidence rule alone. This
mirrors `security-refute-findings`; judge on completed re-checks only — a
failed/absent sub-agent is not a refutation and not a confirmation: retry it
once, and if it fails again keep the evidenced finding with status "verified
(evidence rule; cross-check unavailable)" — never drop an evidenced
critical/high because verification infrastructure failed. A valid refutation must
contradict the evidence trace or show it does not support the classification;
impact-minimization that concedes the cited facts (e.g., "the committed secret
is probably unused") does NOT refute — adjudicate it unsound, keep the finding,
and record the dissent under Unverified observations for transparency.

## Verdict (constitution Quality Gates vocabulary)

- Any verified `critical` → **BLOCKED**
- Else any verified `high` tagged `security` or `error-handling` (the guardrail
  categories overlapping Tier 1 domains; see `validation_criteria.yml`) → **BLOCKED**
- Else any verified `high` → **NEEDS_REVIEW**
- Else → **APPROVED**, including targets with only `medium`/`low`/`info`
  findings (listed but non-gating)

## Report format

```markdown
# AI-Code Audit: <target>
**Verdict**: APPROVED | NEEDS_REVIEW | BLOCKED
**Scope**: <N files, M lines; chunking: none|by-directory>; Passes: P0–P6 (P6 skipped: <reason>)

## Findings
| ID | Severity | Pass | Anti-pattern | Location | Status |
|----|----------|------|--------------|----------|--------|
| F-1 | critical | P3 | ANTI-025 hardcoded secret | src/db.py:5 | verified (cross-checked) |

### F-1 — <title>
**Evidence trace**: <the followed trace>
**Required action**: <from severity: critical=block merge/immediate; high=fix before release; medium=this cycle; low=maintenance; info=document>
**Prevention rule**: <from the registry entry>

## Unverified observations
- <candidate lacking evidence or failing cross-verification, with why>

## Capture proposals
- <recurring anti-pattern with no registry entry — offer the full invocation to fill in:
  manifest-workspace:learning-capture add --category antipattern --language <lang> --title "..." --description "..."
  --tags "<guardrail-tag>" --severity <sev> --detection-cue "..." --prevention-rule "..."
  --provenance session-capture --source ai-code-audit`>
```

## Sub-agent dispatch

Follow the bundled `sub-agent-dispatch.md` selection rules. Dispatches use the
pinned `opus` model.

Dispatch sub-agents ONLY for the cross-verification step: one adversarial
refuter per candidate `critical`/`high` finding. The passes themselves run
inline — they share the P0 orientation context and must not be split. Use
native Task sub-agents on Claude, or `manifest-workspace:parallel-agent` / inline adversarial
re-reads on other assistants. Dispatched refuters judge only the evidence they
are given and do not re-dispatch.

Dispatch on **Opus** (`subagent_model: opus`) — adversarial
verification is the documented escalation case. Pass the model explicitly; do not inherit
the session's.

## Acceptance harness

`tests/fixtures/audit-seeded/` (Manifest repo only — the harness does not ship
with deployments) plants exactly six defects; `README.md` there is the answer
key. Pass bar: ≥90% of plants found at correct severity (with six plants that
means all six), zero findings against clean files, verdict BLOCKED, single
invocation.
