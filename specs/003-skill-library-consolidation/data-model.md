# Data Model: Skill Library Consolidation & Repo Health Hardening

**Date**: 2026-06-10 · **Plan**: [plan.md](plan.md)

## Entities

### Skill
- **Identity**: directory name under `.retired skill supply/skills/` (kebab-case, unique)
- **Fields**: `name` (frontmatter, MUST equal directory name), `description`
  (frontmatter, trigger surface — loaded into every session), body (procedure)
- **States**: `active` → `absorbed` (content merged into a survivor, directory
  deleted) | `survivor` (active + carries merged content)
- **Invariants**: valid frontmatter; no two active skills target the same
  workflow (post-consolidation); deleted names unreferenced repo-wide (FR-003)

### Duplicate Cluster (transient, this feature only)
- **Fields**: cluster id (6 total), member skills (19 total), survivor (7
  total: 5 existing names + 2 new), resolution (merge | keep-both-with-anchors)
- **Lifecycle**: identified → merged → verified (content-preservation review)
  → closed
- **Math invariant**: Σ deletions = 12; |library| 81 → 69 (±1)

### Deploy Target
- **Instances**: `~/.claude/skills` (bootstrap + sync-skills), Cursor/Gemini/
  Codex/Antigravity symlinks (follow home), `.github/skills` (retired skill supply-owned)
- **Fields**: path, deployer (bootstrap `deploy_home_skills` | `sync-skills.sh`
  | retired skill supply), mirror semantics (post-change: all mirror = prune on deploy)
- **Invariant (FR-005a)**: pruning scoped to the skills directory only; paths
  outside it untouched by skill deploys

### Library Prompt Entry (evolve pipeline)
- **Fields**: skill name, description (NEW — from frontmatter)
- **Format contract**: `- <name> — <description>` per line in `{{LIBRARY}}`
- **Fallback**: missing/unparsable description → name-only line (never fails
  the run; fail-open like the rest of the pipeline)

### Command Table Row
- **Canonical store**: `docs/COMMANDS.md`
- **Mirrors**: root `CLAUDE.md`, `AGENTS.md`, `configs/claude/CLAUDE.md`
- **Invariant (FR-006)**: mirrors textually consistent with canonical on
  change day

### Array-Expansion Guard Finding
- **Fields**: file, line, array name, verdict (unsafe | guarded | opted-out)
- **Opt-out**: `# array-safe` inline comment
- **Enforcement points**: pre-commit hook + CI lint step (both, per
  clarification)

## State Transitions

```text
Skill consolidation:
  [19 cluster members: active]
      → merge content into survivor (preserve all distinct triggers/steps,
        stricter rule wins on conflict)
      → delete 12 absorbed dirs + add 2 new survivor dirs
      → repo-wide reference sweep (0 hits for deleted names)
      → PR review (parallel-agent cross-verification, Constitution II)
      → deploy/sync run → targets converge (stale copies pruned)

records/:  untracked-ambiguous → gitignored (origin documented as unknown)
spec 002:  ACTIVE → Delivered/archived (pointer in root CLAUDE.md repointed)
CHANGELOG: [Unreleased] shipped items → dated section
```

## Validation Rules (from FRs)

| Rule | Source | Enforced by |
|---|---|---|
| Survivor frontmatter valid, name == dir | FR-001/Constitution IV | existing CI skill checks + PR review |
| No content loss in merges | FR-002 | cluster-by-cluster diff review in PR |
| Zero references to deleted names | FR-003 | grep sweep task + PR check |
| Prune only inside skills dir | FR-005a | new bats cases |
| Library prompt = name + description | FR-005 | pytest on `_library_entries` |
| No interpreter-source interpolation | FR-009 | quote-path bats cases + Tier 1 review |
| Chunk timeout → fail-continue | FR-010 | pytest TimeoutExpired simulation |
| Empty-array guard blocks violations | FR-011 | guard self-test (deliberate violation) |
