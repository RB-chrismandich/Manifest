# Quickstart: verifying this feature locally

Per-story verification commands (run from repo root).

## US1 — Skill consolidation

```bash
# Count: expect 69 (±1)
find .skillshare/skills -name SKILL.md | wc -l

# Deleted names gone + unreferenced (expect no output)
for n in address-pr-review-comments address-review-comments session-memory-digest \
  live-data-validation-before-merge live-data-smoke-validation \
  real-data-validation-after-green-tests verify-cli-premise \
  verify-cli-premise-before-tooling verify-tool-premise \
  verify-api-schema-before-trust verify-image-runtime-contract \
  daemon-migration-verification retire-migrated-tool-runtime \
  plugin-mcp-clean-removal; do
  [[ -d .skillshare/skills/$n ]] && echo "STILL EXISTS: $n"
  grep -rn "$n" --include="*.md" --include="*.sh" --include="*.py" --include="*.yml" . \
    | grep -v "specs/003-" | grep -v CHANGELOG && echo "REFERENCED: $n"
done

# Prune-on-deploy + library prompt
bats tests/bats/deploy_skills.bats
python3 -m pytest tests/python/test_skillclaw_evolve.py -q
```

## US2 — Docs accuracy

```bash
grep -rn "28 skills" README.md AGENTS.md          # expect: no output
# Table consistency: extract + diff each mirror against docs/COMMANDS.md (task
# provides the exact extraction; manual eyeball acceptable at review)
grep -n "Unreleased" CHANGELOG.md                  # expect: empty or truly-unreleased only
test -f docs/SPEC-SYSTEMS.md && head -5 docs/SPEC-SYSTEMS.md
bash configs/claude/scripts/generate_cursor_rules.sh && git diff --exit-code configs/cursor/rules/
```

## US3 — Script robustness

```bash
# Quote-safe parsing
d="$(mktemp -d)/it's here"; mkdir -p "$d"; cp configs/claude/config/labels.yml "$d/"
LABELS_FILE="$d/labels.yml" configs/claude/scripts/label_sync.sh --dry-run

# Timeout (pytest simulates TimeoutExpired)
python3 -m pytest tests/python/test_skillclaw_evolve.py -q -k timeout

# Guard: clean at HEAD, catches a violation
tests/lint/check_array_expansion.sh                # expect exit 0
pre-commit run check-array-expansion --all-files   # expect pass

# No test files deployed
ls configs/claude/scripts/test_*.py 2>/dev/null    # expect: no output
```

## US4 — Tests & CI

```bash
bats tests/bats/learning_capture.bats tests/bats/check_status.bats \
     tests/bats/generate_cursor_rules.bats
grep -n "cache" .github/workflows/ci.yml           # caching present
grep -n "yamllint==" .github/workflows/ci.yml      # pinned
```

## US5 — Hygiene

```bash
git check-ignore records/ && echo ignored          # expect: ignored
grep -rn "specs/002-new-agent-skills" CLAUDE.md    # expect: no stale "current plan" pointer
for s in branch_clean pr_review sync-skills version_pin skillclaw_promote \
         git_ops linear_ops check_status; do
  configs/claude/scripts/$s.sh --help >/dev/null 2>&1 || echo "NO HELP: $s"
done                                               # expect: no output
```

## Full gate (every PR)

```bash
pre-commit run --all-files
bats tests/bats/ && python3 -m pytest tests/python/ -q
shellcheck configs/claude/scripts/*.sh bootstrap.sh bootstrap/lib/*.sh
```
