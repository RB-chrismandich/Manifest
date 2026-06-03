# Quickstart: New Agent Skills

**Feature**: 002-new-agent-skills | **Date**: 2026-06-01

How a maintainer uses the four new skills once implemented and deployed
(`./bootstrap.sh` copies them to `~/.claude/skills`).

---

## version-pin

```bash
# Audit + auto-fix every recognized file in the working tree
/version-pin

# Audit one file, warn-only (no edits) — same mode the save hook uses
/version-pin requirements.txt --check

# Pin a specific requested version instead of latest stable
/version-pin requirements.txt --requested requests=2.31.0
```

Register the warn-only save hook (idempotent) via the `ai-hooks-integration` skill so
`requirements.txt`, `docker-compose.yaml`, Dockerfiles, etc. are checked on write.

**Expected**: loose entries reported with the exact pinned+hashed replacement; already-pinned
and `# version-pin:ignore`-marked entries untouched; a clean second run reports no changes.

## docs-all

```bash
# Refresh all documentation in one command
/docs-all

# Force an explicit order
/docs-all --order readme,diagrams,improve
```

**Expected**: one consolidated report listing the order chosen, why, and each sub-skill's
outcome; a single sub-skill failure does not abort the others.

**Verification scenario** (manual — `docs-all` is orchestration, no script/bats):

1. Run `/docs-all` on the repo. Confirm the report lists all three sub-skills
   (`docs-readme`, `docs-diagrams`, `docs-improve`), each dispatched as a sub-agent.
2. Confirm the report states the **order** and a **reason** line, and that
   `docs-improve` appears **last**.
3. Make a change touching only architecture/imports, run again, and confirm the
   order adapts (diagrams prioritized) while the report still explains the precedence.
4. Temporarily make one sub-skill fail (e.g. point it at a missing path); confirm
   its failure is surfaced in the report and the other two still run.

## pr-review

```bash
# Triage every open PR (read-only)
/pr-review

# Machine-readable, custom staleness window
/pr-review --json --stale-days 14
```

**Expected**: one row per open PR with mergeability/checks/staleness and a recommended
disposition (keep/merge/close/needs-rebase) + rationale. No PRs are modified.

## branch-clean

```bash
# Preview deletable branches (default: dry-run, local only)
/branch-clean

# Actually delete, after confirmation
/branch-clean --apply

# Include remote branches (opt-in)
/branch-clean --apply --include-remote
```

**Expected**: candidates grouped by reason (merged / gone / stale); protected and current
branches never listed for deletion; nothing deleted without `--apply` + confirmation.

---

## Verifying the implementation

```bash
# Shell helper tests
bats tests/bats/version_pin.bats tests/bats/pr_review.bats tests/bats/branch_clean.bats

# Lint
shellcheck configs/claude/scripts/version_pin.sh configs/claude/scripts/pr_review.sh configs/claude/scripts/branch_clean.sh
yamllint configs/claude/config/command_config.yml configs/claude/config/validation_criteria.yml

# Config parses
python3 -c "import yaml; yaml.safe_load(open('configs/claude/config/command_config.yml'))"

# Skills discoverable after deploy
./bootstrap.sh && ls ~/.claude/skills | grep -E 'version-pin|docs-all|pr-review|branch-clean'
```
