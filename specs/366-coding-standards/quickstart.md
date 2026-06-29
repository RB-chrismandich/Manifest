# Quickstart — Coding Standards & Edit-Time Enforcement

How to use and verify the three deliverables. Assumes the branch
`366-coding-standards` is checked out.

## 1. One-time setup

```bash
pip install pre-commit
pre-commit install                 # commit-layer hooks
pre-commit run --all-files         # baseline — same command CI runs
```

The edit-time hook deploys with the rest of the config:

```bash
./bootstrap.sh                     # copies configs/claude/scripts/lint_on_edit_hook.sh
                                   # → ~/.claude/scripts/ and wires settings.local.json
```

## 2. Verify edit-time linting (US1)

In a Claude Code session (hook fires on every Write/Edit), or manually:

```bash
# Simulate a PostToolUse payload for a file with a violation:
echo '{"tool_input":{"file_path":"/abs/path/bad.py"}}' | ~/.claude/scripts/lint_on_edit_hook.sh ; echo "exit=$?"
```

Expected: a `lint-on-edit: …` advisory on **stderr**, `exit=0`, and `bad.py`
unchanged on disk. Remove `ruff` from PATH and rerun → still `exit=0`, no error
(fail-open).

## 3. Verify the no-bypass gate (US2)

```bash
# Without local hooks installed, a violation must still fail CI:
git stash -u 2>/dev/null || true
# (in CI) the lint job runs:
pre-commit run --all-files --show-diff-on-failure
```

Plant a ruff violation or a fake secret, push a PR → the `lint` job fails. This is
the gate of record; skipping `pre-commit install` locally does not bypass it.

## 4. Read the standard (US3)

```bash
$EDITOR docs/CODING_STANDARDS.md   # per-language rules + Active/Conditional/Document-only verdict
```

Linked from `CLAUDE.md`, `.claude/CLAUDE.md`, `CONTRIBUTING.md`, `AGENTS.md`.

## 5. Verify tooling currency (US4)

```bash
grep -n "terraform_tfsec" .pre-commit-config.yaml   # → no matches (deprecated, removed)
grep -nE "golangci-lint|rev:" .pre-commit-config.yaml | head   # revs current per research §5
```

## 6. Run the hook's tests

```bash
npx bats tests/bats/lint_on_edit_hook.bats         # G1–G8 from contracts/edit-time-hook.md
```

## Success signals (from spec)

- SC-001/002: a violation in a primary-language file surfaces in-session.
- SC-003: 0 edits blocked, 0 files mutated by the edit-time check.
- SC-004/007: no primary-language standard is local-only; violating PRs fail.
- SC-005: 0 deprecated tools remain.
- SC-006: every in-scope language has a documented verdict.
