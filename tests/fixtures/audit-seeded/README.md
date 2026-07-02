# Audit-Seeded Fixture (Answer Key)

> Acceptance harness for the `/ai-code-audit` skill (spec 457, SC-002/SC-006).
> A small "demo dashboard" project with **exactly six planted anti-patterns**;
> every other file is intentionally clean. The audit smoke test (tasks.md T019)
> scores a run against this key: ≥90% of plants detected at the correct
> severity, **zero** findings fabricated against the clean files, and verdict
> `BLOCKED` (plant 2 is a verified critical).
>
> ⚠️ Do NOT "fix" these files, add lint suppressions beyond what is present, or
> label the plants in the source — the sources must read as natural code.

## Planted defects

| # | Registry entry | Location | Expected severity | What to find |
|---|----------------|----------|-------------------|--------------|
| 1 | ANTI-021 catch-log-return-undefined | `src/orders.ts:22-23` (`getOrder`) | high | catch logs and returns `undefined`; caller `renderOrderSummary` (`src/orders.ts:30`) dereferences with `!` and crashes far from the cause. Known secondary defect in the same zone: `getOrder` passes its order ID to `fetchUser` (identifier confusion, from the source research's canonical example) — reporting it is correct, not a fabrication |
| 2 | ANTI-025 hardcoded secret | `src/db.py:5` | critical | `DB_PASSWORD` literal in source (the `gitleaks:allow` comment suppresses the pre-commit scanner for this fixture, it does not excuse the finding) |
| 3 | ANTI-010 dead/orphan module | `src/legacy_report.py` (whole module) | medium | `weekly_report` has zero callers anywhere in the fixture |
| 4 | ANTI-008 cosmetic abstraction | `src/storage.ts:3-6` | info | `IScoreStorageProviderFactory` has exactly one implementation and every consumer (`src/app.ts:9`) constructs `FileStorage` directly |
| 5 | ANTI-018 missing teardown | `src/watcher.ts:11-13` (`mount`) | medium | WebSocket message listener, window resize listener, and `setInterval` are registered but `destroy()` (line 16) removes none of them |
| 6 | ANTI-024 missing boundary validation | `scripts/ingest.sh:5-6` | high | `$1`/`$2` consumed with no presence/format check — missing args die as cryptic unbound-variable errors; any path is copied straight through as `.csv` |

## Clean files (any finding against these is a fabrication)

- `src/models.py`
- `src/util_math.py`
- `src/format.ts`
- `src/app.ts`
- `scripts/run_pipeline.sh`
- `src/db.py` apart from line 5 (`connect`/`fetch_scores` are parameterized and clean)
- `src/orders.ts` apart from `getOrder`/`renderOrderSummary` (`fetchUser` is clean)

## Expected report shape

- Verdict: `BLOCKED` (verified critical, plant 2)
- Plants 1, 2, 6 must be cross-verified (critical/high) before reporting
- P6 (iterative regression) is expected to be SKIPPED with a stated reason —
  this fixture ships without its own git history
