# Data Model: Proactive Code Guardrails

**Feature**: 457-proactive-code-guardrails | **Date**: 2026-07-01

## Entity 1: Anti-Pattern Registry Entry

Stored in `configs/claude/config/knowledge_base.yml` under `entries:`. Existing shape preserved; new fields are optional (additive schema evolution — every pre-existing entry remains valid).

| Field | Type | Req | Notes |
|-------|------|-----|-------|
| `id` | string `ANTI-###` | yes | Continues existing sequence; unique |
| `title` | string | yes | Short name of the failure mode |
| `category` | enum | yes | `antipattern` (existing top-level category, unchanged) |
| `language` | enum | yes | `general` for category-level rules; or one of `bash`, `python`, `typescript`, `javascript`, `go`, `terraform`, `yaml` |
| `description` | string | yes | What the failure mode is and why it matters |
| `tags` | list | yes | MUST include exactly one guardrail-category tag: `arch`, `async-state`, `error-handling`, `security`, `dependency`, `iteration` (this is how the 6 spec categories are represented without a schema change) |
| `confidence` | enum | yes | `high` / `medium` / `low` (existing) |
| `created`, `last_seen`, `occurrences`, `source` | existing | yes | Unchanged semantics; seeded entries use `source: registry-seed` |
| `severity` | enum | new, opt | `critical` / `high` / `medium` / `low` / `info` — aligned with `validation_criteria.yml` values (R3) |
| `detection_cue` | map or string | new, opt | How to spot it. Map keyed by language for per-language cues (`bash:`, `python:`, …); plain string for language-agnostic cues (R2) |
| `prevention_rule` | string | new, opt | Positive "do this instead" phrasing (FR-009); REQUIRED on seeded entries |
| `provenance` | enum | new, opt | `research-seed` / `session-capture` (FR distinguishes seeded vs captured) |

**Identity/uniqueness**: `id` unique; `learning_capture.sh` dedup remains title+language based for captures.

**Lifecycle**: seeded at implementation → captured additions via `antipattern-detect`/`learning-loop` (provenance `session-capture`) → retired by deleting the entry and regenerating `docs/KNOWLEDGE_BASE.md` via `sync-docs`.

**Validation rules**: new bats coverage asserts (a) every `severity` value is in the allowed set, (b) every seeded entry has `prevention_rule` and exactly one guardrail-category tag, (c) all 6 guardrail tags are represented, (d) entry count with guardrail tags ≥ 25 (SC-001).

## Entity 2: Audit Pass

Definitional (lives in the `ai-code-audit` SKILL.md, not in config). Fixed ordered set:

| # | Pass | Objective | Evidence requirement |
|---|------|-----------|----------------------|
| P0 | Inventory/orientation | Map modules, imports/exports, hotspots, AI-authorship markers | Structural map cited in later passes |
| P1 | Architectural integrity | Dead modules, orphan state, pattern abandonment, cosmetic abstractions | Caller/usage trace per flag |
| P2 | Async & state lifecycle | Unhandled async, swallowed errors, races, missing teardown, boundary cases | Trace catch-to-resolution / mount-to-teardown |
| P3 | Security | Secrets, injection, authz completeness, crypto, CORS/headers, dependency existence | Source→sink trace; registry check for packages |
| P4 | Logic/business-rule integrity | Conditional exhaustiveness, return-type consistency, atomicity/rollback | Input-space or path enumeration |
| P5 | Quality/maintainability | Duplication, complexity thresholds, test quality, log hygiene, env validation | Metric or concrete instance |
| P6 | Iterative regression | Security-control removal in history, cross-session boundary drift | Commit-level before/after diff; SKIPPED (stated) if history unavailable |

**State transitions**: passes run strictly in order; for targets >50 source files, P1–P5 run per top-level-directory chunk, P0 and P6 run globally, results merge before reporting (R6).

## Entity 3: Finding

One evidenced defect produced by an audit pass. Report-level structure (markdown report contract in `contracts/audit-skill-contract.md`):

| Field | Type | Notes |
|-------|------|-------|
| `anti_pattern` | ref | Registry `id` (or `UNREGISTERED` + proposed capture) |
| `pass` | enum | P0–P6 |
| `severity` | enum | Same vocabulary as registry (R3) |
| `location` | string | `path:line` — REQUIRED for defect status |
| `evidence_trace` | string | The followed trace (e.g., "catch at x:41 logs and returns undefined; caller y:12 dereferences result") |
| `status` | enum | `verified` / `unverified-observation` |
| `required_action` | derived | From severity via verdict mapping (R3) |

**State transitions**: `candidate` → (evidence check) → `unverified-observation` if no location/trace → for `critical`/`high`: adversarial re-check → `verified` or downgraded to `unverified-observation` (FR-012). `medium` and below: `verified` on evidence check alone.

## Entity 4: Severity Class → Verdict Mapping

Shared vocabulary; no new config file — the mapping is documented in the audit skill and mirrors `validation_criteria.yml` + constitution Quality Gates:

| Severity | Verdict effect | Required action |
|----------|---------------|-----------------|
| `critical` (verified) | `BLOCKED` | Immediate remediation before merge/release |
| `high` (verified, Tier 1 domain: `security`/`error-handling` tag) | `BLOCKED` | Immediate remediation (tier membership decides blocking, per `validation_criteria.yml`) |
| `high` (verified, other domains) | `NEEDS_REVIEW` | Fix before next release |
| `medium` | none (listed) | Fix within current work cycle |
| `low` | none (listed) | Maintenance cycle |
| `info` | none (listed) | Document; refactor when convenient |

## Relationships

```text
knowledge_base.yml (Registry Entry, tag=guardrail-category)
   ├─ read by → CLAUDE.md digest + references/antipatterns.md   (write-time guidance, FR-003)
   ├─ read by → code-quality skill                              (advisory checks, FR-011)
   ├─ read by → ai-code-audit skill (per-pass detection cues)   (FR-004)
   └─ written by → antipattern-detect / learning-loop via learning_capture.sh  (capture, FR-007)

ai-code-audit → Finding → severity → verdict (validation_criteria.yml vocabulary)  (FR-005/006/012)
```
