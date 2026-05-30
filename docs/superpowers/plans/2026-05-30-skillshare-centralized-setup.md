# skillshare Centralized Setup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adopt `skillshare` as Manifest's source-of-truth + supply-chain layer for skills, with `bootstrap.sh` owning portable home deployment and the symlink fan-out across Claude/Cursor/Gemini/Codex/Antigravity, plus project-scoped Copilot sync.

**Architecture:** The 27 skills physically move into `.skillshare/skills/`; `configs/claude/skills` becomes a relative symlink so all legacy references keep resolving. bootstrap copies the physical `.skillshare/skills/` → `~/.claude/skills` (skillshare can't expand `~`, so it is NOT the home deployer) and symlinks the other tools to it. skillshare owns only the project-relative Copilot target (`.github/skills`) and the install/audit/update lifecycle (including the external `ai-hooks-integration` skill).

**Tech Stack:** Bash (bootstrap libs), `skillshare` CLI (Homebrew, v0.19.24), `bats` (shell tests), `rsync`, YAML config.

**Spec:** `docs/superpowers/specs/2026-05-30-skillshare-centralized-setup-design.md`

---

## File Structure

| File | Responsibility | Change |
|------|----------------|--------|
| `.skillshare/skills/*` | Physical source of truth for all skills | **Create** (move 26 dirs + README.md here) |
| `configs/claude/skills` | Backward-compat pointer to source | **Replace** dir with relative symlink → `../../.skillshare/skills` |
| `.skillshare/config.yaml` | skillshare targets (Copilot only) + audit | **Modify** (drop `claude` target, set `copilot` path) |
| `.skillshare/.gitignore` | skillshare-managed ignores | **Modify** (un-ignore `config.yaml`) |
| `bootstrap/lib/common.sh` | Shared helpers incl. new `deploy_home_skills` | **Modify** (add function) |
| `bootstrap/lib/deploy.sh` | Config/skill deployment orchestration | **Modify** (rsync exclude, home skills, antigravity, copilot sync) |
| `bootstrap.sh` | Top-level vars + flow | **Modify** (add `ANTIGRAVITY_TARGET_DIR`) |
| `tests/bats/deploy_skills.bats` | Tests for skills deploy + ordering | **Create** |
| `docs/COMMANDS.md` / repo docs | Drift-guard note + skillshare role | **Modify** |

---

## Task 1: Migrate skills to `.skillshare/skills/` and add compat symlink

**Files:**
- Move: `configs/claude/skills/*` → `.skillshare/skills/`
- Replace: `configs/claude/skills` (dir → symlink)

- [ ] **Step 1: Confirm source inventory (26 dirs + README.md = 27 entries)**

Run:
```bash
cd /Users/chrismandich/Documents/GitHub/Manifest
find configs/claude/skills -maxdepth 1 -mindepth 1 | wc -l
```
Expected: `27`

- [ ] **Step 2: Move every entry into `.skillshare/skills/` (preserve git history)**

Run:
```bash
cd /Users/chrismandich/Documents/GitHub/Manifest
for entry in configs/claude/skills/*; do
  git mv "$entry" ".skillshare/skills/$(basename "$entry")"
done
```
Note: `.skillshare/skills/` already exists (empty). `git mv` stages the moves.

- [ ] **Step 3: Remove the now-empty dir and create the relative symlink**

Run:
```bash
cd /Users/chrismandich/Documents/GitHub/Manifest
rmdir configs/claude/skills
ln -s ../../.skillshare/skills configs/claude/skills
git add configs/claude/skills
```

- [ ] **Step 4: Verify the symlink resolves and globbing works through it**

Run:
```bash
ls -l configs/claude/skills
ls configs/claude/skills/code-quality/SKILL.md
```
Expected: first line shows `configs/claude/skills -> ../../.skillshare/skills`; second prints the path (proves glob/path resolution through the symlink).

- [ ] **Step 5: Verify `generate_cursor_rules.sh` still finds skills (glob is symlink-safe)**

Run:
```bash
cd /Users/chrismandich/Documents/GitHub/Manifest
bash configs/claude/scripts/generate_cursor_rules.sh --help 2>&1 | head -5
for d in configs/claude/skills/*/; do echo "$d"; done | head -3
```
Expected: the loop prints real skill subdirectories (e.g. `configs/claude/skills/a11y-audit/`), confirming `for skill_dir in "$SKILLS_DIR"/*/` resolves through the symlink.

- [ ] **Step 6: Commit**

```bash
cd /Users/chrismandich/Documents/GitHub/Manifest
git add -A
git commit -m "refactor: move skills to .skillshare/skills with compat symlink"
```

---

## Task 2: Point skillshare config at Copilot only and un-ignore it

**Files:**
- Modify: `.skillshare/config.yaml`
- Modify: `.skillshare/.gitignore`

- [ ] **Step 1: Rewrite `.skillshare/config.yaml` — drop `claude`, make `copilot` project-relative**

Replace the entire file with:
```yaml
# yaml-language-server: $schema=https://raw.githubusercontent.com/runkids/skillshare/main/schemas/project-config.schema.json
# Home deploy (~/.claude/skills + tool symlinks) is owned by bootstrap.sh, NOT
# skillshare: skillshare does not expand ~ in target paths (verified 2026-05-30).
# skillshare here only handles the project-scoped Copilot target + supply chain.
targets:
  - name: copilot
    skills:
      path: .github/skills
      mode: copy
audit:
  block_threshold: CRITICAL
```

- [ ] **Step 2: Un-ignore `config.yaml` in `.skillshare/.gitignore`**

The current file is:
```
# BEGIN SKILLSHARE MANAGED - DO NOT EDIT
logs/
trash/
backups/
config.yaml
# END SKILLSHARE MANAGED
```
Edit it to remove the `config.yaml` line (keep the rest):
```
# BEGIN SKILLSHARE MANAGED - DO NOT EDIT
logs/
trash/
backups/
# END SKILLSHARE MANAGED
```

- [ ] **Step 3: Verify config.yaml is now tracked, and sync targets `.github/skills` (no literal `~`)**

Run:
```bash
cd /Users/chrismandich/Documents/GitHub/Manifest
git check-ignore -v .skillshare/config.yaml || echo "TRACKED (good)"
skillshare sync --dry-run 2>&1 | grep -iE "target directory|copilot|github/skills|~"
```
Expected: `TRACKED (good)`; dry-run mentions `.github/skills` and shows **no** `/~/` literal-tilde path.

- [ ] **Step 4: Commit**

```bash
cd /Users/chrismandich/Documents/GitHub/Manifest
git add .skillshare/config.yaml .skillshare/.gitignore
git commit -m "chore: scope skillshare to Copilot project sync; commit config.yaml"
```

---

## Task 3: Install `ai-hooks-integration` as a tracked external skill

**Files:**
- Create: `.skillshare/skills/ai-hooks-integration/` (via skillshare)

- [ ] **Step 1: Install from GitHub (audit gate applies)**

Run:
```bash
cd /Users/chrismandich/Documents/GitHub/Manifest
skillshare install github.com/runkids/ai-hooks-integration
```
Expected: install completes; audit reports below CRITICAL (not blocked). If it prompts interactively, accept the install. If audit BLOCKS, stop and surface the finding — do not force.

- [ ] **Step 2: Verify it landed as a tracked skill**

Run:
```bash
cd /Users/chrismandich/Documents/GitHub/Manifest
ls .skillshare/skills/ai-hooks-integration/SKILL.md
skillshare list 2>&1 | grep -i ai-hooks
```
Expected: `SKILL.md` path prints; `list` shows `ai-hooks-integration`.

- [ ] **Step 3: Commit**

```bash
cd /Users/chrismandich/Documents/GitHub/Manifest
git add .skillshare/skills/ai-hooks-integration
git commit -m "feat: add ai-hooks-integration as tracked external skill"
```

---

## Task 4: Add `deploy_home_skills()` helper (TDD)

**Files:**
- Test: `tests/bats/deploy_skills.bats`
- Modify: `bootstrap/lib/common.sh`

- [ ] **Step 1: Write the failing test**

Create `tests/bats/deploy_skills.bats`:
```bash
#!/usr/bin/env bats
# Tests for bootstrap/lib/common.sh deploy_home_skills + deploy.sh skills wiring

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."

setup() {
    export BATS_TMPDIR="${BATS_TMPDIR:-/tmp}"
    SANDBOX=$(mktemp -d "$BATS_TMPDIR/deploy_skills.XXXXXX")
    # Source the helpers under test
    # shellcheck disable=SC1090
    source "$REPO_ROOT/bootstrap/lib/common.sh"
}

teardown() {
    [[ -n "$SANDBOX" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"
}

@test "deploy_home_skills copies real directories from physical source" {
    mkdir -p "$SANDBOX/src/demo-skill"
    echo "body" > "$SANDBOX/src/demo-skill/SKILL.md"

    run deploy_home_skills "$SANDBOX/src" "$SANDBOX/dest"
    assert_success

    [ -d "$SANDBOX/dest/demo-skill" ]
    [ ! -L "$SANDBOX/dest" ]
    assert_equal "$(cat "$SANDBOX/dest/demo-skill/SKILL.md")" "body"
}

@test "deploy_home_skills prunes skills removed from source" {
    mkdir -p "$SANDBOX/src/keep" "$SANDBOX/dest/stale"
    echo k > "$SANDBOX/src/keep/SKILL.md"
    echo s > "$SANDBOX/dest/stale/SKILL.md"

    run deploy_home_skills "$SANDBOX/src" "$SANDBOX/dest"
    assert_success

    [ -d "$SANDBOX/dest/keep" ]
    [ ! -e "$SANDBOX/dest/stale" ]
}

@test "deploy_home_skills fails clearly when source missing" {
    run deploy_home_skills "$SANDBOX/nonexistent" "$SANDBOX/dest"
    assert_failure
    assert_output --partial "not found"
}
```

- [ ] **Step 2: Run the test to verify it fails**

Run:
```bash
cd /Users/chrismandich/Documents/GitHub/Manifest
bats tests/bats/deploy_skills.bats
```
Expected: FAIL — `deploy_home_skills: command not found`.

- [ ] **Step 3: Implement `deploy_home_skills()` in `bootstrap/lib/common.sh`**

Append after the `link_shared_assets()` function (end of file, after line 120):
```bash

# Deploy skills into a tool's real skills dir from the PHYSICAL skillshare source.
# Always sources the real .skillshare/skills dir (never the compat symlink) and
# prunes removed skills so the destination mirrors the source of truth.
deploy_home_skills() {
    local src="$1"
    local dest="$2"

    if [[ ! -d "$src" ]]; then
        print_warning "Skill source not found: $src"
        return 1
    fi

    mkdir -p "$dest"
    rsync -a --delete "$src"/ "$dest"/
    print_success "Deployed skills: $src -> $dest"
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run:
```bash
cd /Users/chrismandich/Documents/GitHub/Manifest
bats tests/bats/deploy_skills.bats
```
Expected: 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/chrismandich/Documents/GitHub/Manifest
git add bootstrap/lib/common.sh tests/bats/deploy_skills.bats
git commit -m "feat: add deploy_home_skills helper with pruning"
```

---

## Task 5: Wire skills carve-out + home deploy into `deploy.sh` (TDD)

**Files:**
- Test: `tests/bats/deploy_skills.bats` (add integration test)
- Modify: `bootstrap/lib/deploy.sh:69` (fresh path) and `:42` (merge path)

- [ ] **Step 1: Add the failing integration test**

Append to `tests/bats/deploy_skills.bats`:
```bash

@test "deploy_configs (fresh) puts real skill dirs in TARGET and no '~' junk" {
    # Arrange an isolated TARGET and stub the heavy secondary deploys.
    export SCRIPT_DIR="$REPO_ROOT"
    export TARGET_DIR="$SANDBOX/home/.claude"
    export CURSOR_TARGET_DIR="$SANDBOX/home/.cursor"
    export GEMINI_TARGET_DIR="$SANDBOX/home/.gemini"
    export CODEX_TARGET_DIR="$SANDBOX/home/.codex"
    export ANTIGRAVITY_TARGET_DIR="$SANDBOX/home/.antigravity"
    export MANIFEST_OUTPUT_DIR="$SANDBOX/home/.manifest/outputs"
    export FORCE=true

    # shellcheck disable=SC1090
    source "$REPO_ROOT/bootstrap/lib/deploy.sh"

    # Isolate: stub secondary routines that need network/CLIs/other configs.
    write_services_config() { :; }
    deploy_cursor_configs() { :; }
    deploy_gemini_configs() { :; }
    deploy_codex_configs() { :; }
    deploy_antigravity_configs() { :; }
    sync_skillshare_targets() { :; }

    run deploy_configs
    assert_success

    # Real skill dirs landed (sampled), and skills is NOT a symlink.
    [ -d "$TARGET_DIR/skills/code-quality" ]
    [ ! -L "$TARGET_DIR/skills" ]
    # The compat symlink was never copied verbatim into the home dir.
    [ ! -e "$TARGET_DIR/skills/skills" ]
    # No literal tilde dir created anywhere under the sandbox.
    run find "$SANDBOX" -name '~' -maxdepth 6
    assert_output ""
}
```

- [ ] **Step 2: Run to verify it fails**

Run:
```bash
cd /Users/chrismandich/Documents/GitHub/Manifest
bats tests/bats/deploy_skills.bats -f "deploy_configs"
```
Expected: FAIL — `~/.claude/skills` not populated (or `code-quality` missing) because home-skills deploy isn't wired yet.

- [ ] **Step 3: Carve `skills` out of the fresh-path generic copy**

In `bootstrap/lib/deploy.sh`, replace line 69:
```bash
    cp -R "$source_dir"/* "$TARGET_DIR/"
```
with:
```bash
    # Copy everything EXCEPT skills (skills is a symlink -> .skillshare/skills;
    # copying it verbatim would create a broken link in ~/.claude). rsync mirrors
    # deploy.sh's existing idiom (line 42).
    rsync -a --exclude 'skills' "$source_dir"/ "$TARGET_DIR/"
```

- [ ] **Step 4: Add the home-skills deploy right after the config copy (fresh path)**

In `bootstrap/lib/deploy.sh`, immediately after the dot-dir copy (line 71, `cp -R "$source_dir"/.[!.]* ...`) and before the "Make scripts executable" block, insert:
```bash

    # Deploy skills from the PHYSICAL skillshare source into ~/.claude/skills.
    # Must run before link_shared_assets (create_symlink skips missing targets).
    deploy_home_skills "$SCRIPT_DIR/.skillshare/skills" "$TARGET_DIR/skills"
```

- [ ] **Step 5: Mirror the carve-out + home-skills deploy in the merge path**

In `bootstrap/lib/deploy.sh`, the merge branch (option 2, around line 42) currently is:
```bash
                    rsync -av --ignore-existing "$source_dir/" "$TARGET_DIR/"
```
Replace it with:
```bash
                    rsync -av --ignore-existing --exclude 'skills' "$source_dir/" "$TARGET_DIR/"
                    deploy_home_skills "$SCRIPT_DIR/.skillshare/skills" "$TARGET_DIR/skills"
```

- [ ] **Step 6: Run the integration test to verify it passes**

Run:
```bash
cd /Users/chrismandich/Documents/GitHub/Manifest
bats tests/bats/deploy_skills.bats
```
Expected: all tests PASS (unit + integration).

- [ ] **Step 7: Commit**

```bash
cd /Users/chrismandich/Documents/GitHub/Manifest
git add bootstrap/lib/deploy.sh tests/bats/deploy_skills.bats
git commit -m "feat: bootstrap deploys home skills from physical source, excludes symlink"
```

---

## Task 6: Add Antigravity skills symlink (TDD)

**Files:**
- Test: `tests/bats/deploy_skills.bats` (add test)
- Modify: `bootstrap.sh` (add `ANTIGRAVITY_TARGET_DIR`)
- Modify: `bootstrap/lib/deploy.sh` (add `deploy_antigravity_configs`, call it)

- [ ] **Step 1: Add the failing test**

Append to `tests/bats/deploy_skills.bats`:
```bash

@test "deploy_antigravity_configs symlinks ~/.antigravity/skills to claude skills" {
    export TARGET_DIR="$SANDBOX/home/.claude"
    export ANTIGRAVITY_TARGET_DIR="$SANDBOX/home/.antigravity"
    mkdir -p "$TARGET_DIR/skills/demo"

    # shellcheck disable=SC1090
    source "$REPO_ROOT/bootstrap/lib/deploy.sh"

    run deploy_antigravity_configs
    assert_success

    [ -L "$ANTIGRAVITY_TARGET_DIR/skills" ]
    [ -d "$ANTIGRAVITY_TARGET_DIR/skills/demo" ]
}
```

- [ ] **Step 2: Run to verify it fails**

Run:
```bash
cd /Users/chrismandich/Documents/GitHub/Manifest
bats tests/bats/deploy_skills.bats -f "antigravity"
```
Expected: FAIL — `deploy_antigravity_configs: command not found`.

- [ ] **Step 3: Declare `ANTIGRAVITY_TARGET_DIR` in `bootstrap.sh`**

In `bootstrap.sh`, after line 55 (`CODEX_TARGET_DIR="$HOME/.codex"`), add:
```bash
ANTIGRAVITY_TARGET_DIR="$HOME/.antigravity"
```

- [ ] **Step 4: Add `deploy_antigravity_configs()` to `bootstrap/lib/deploy.sh`**

After the `deploy_codex_configs()` function (after line 198), add:
```bash

# Deploy Antigravity configuration (skills symlink only — Antigravity reads
# ~/.antigravity/skills; it shares the single source of truth via symlink).
deploy_antigravity_configs() {
    print_step "Deploying Antigravity configuration..."
    mkdir -p "$ANTIGRAVITY_TARGET_DIR"
    create_symlink "$ANTIGRAVITY_TARGET_DIR/skills" "$TARGET_DIR/skills" "Antigravity skills"
    print_success "Antigravity configuration deployed to $ANTIGRAVITY_TARGET_DIR"
}
```

- [ ] **Step 5: Call it from `deploy_configs` (both paths)**

In `bootstrap/lib/deploy.sh`, in the fresh path after `deploy_codex_configs` (line 95), add:
```bash

    # Deploy Antigravity configuration
    deploy_antigravity_configs
```
And in the merge path, after `deploy_codex_configs` (line 52), add:
```bash
                    deploy_antigravity_configs
```

- [ ] **Step 6: Run the test to verify it passes**

Run:
```bash
cd /Users/chrismandich/Documents/GitHub/Manifest
bats tests/bats/deploy_skills.bats
```
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
cd /Users/chrismandich/Documents/GitHub/Manifest
git add bootstrap.sh bootstrap/lib/deploy.sh tests/bats/deploy_skills.bats
git commit -m "feat: symlink ~/.antigravity/skills to shared claude skills"
```

---

## Task 7: Add non-blocking Copilot sync via skillshare (TDD)

**Files:**
- Test: `tests/bats/deploy_skills.bats` (add tests)
- Modify: `bootstrap/lib/deploy.sh` (add `sync_skillshare_targets`, call it)

- [ ] **Step 1: Add the failing tests (present → runs; absent → no error)**

Append to `tests/bats/deploy_skills.bats`:
```bash

@test "sync_skillshare_targets runs skillshare sync when present" {
    export SCRIPT_DIR="$SANDBOX/repo"
    mkdir -p "$SCRIPT_DIR/.skillshare"
    echo "targets: []" > "$SCRIPT_DIR/.skillshare/config.yaml"

    # Stub skillshare on PATH that records invocation.
    MOCK_BIN="$SANDBOX/bin"; mkdir -p "$MOCK_BIN"
    cat > "$MOCK_BIN/skillshare" <<'STUB'
#!/usr/bin/env bash
echo "skillshare $*" >> "$SKILLSHARE_LOG"
STUB
    chmod +x "$MOCK_BIN/skillshare"
    export PATH="$MOCK_BIN:$PATH"
    export SKILLSHARE_LOG="$SANDBOX/ss.log"

    # shellcheck disable=SC1090
    source "$REPO_ROOT/bootstrap/lib/deploy.sh"

    run sync_skillshare_targets
    assert_success
    assert_output --partial "Syncing"
    grep -q "skillshare sync" "$SKILLSHARE_LOG"
}

@test "sync_skillshare_targets is a no-op (success) when skillshare absent" {
    export SCRIPT_DIR="$SANDBOX/repo"
    mkdir -p "$SCRIPT_DIR/.skillshare"
    echo "targets: []" > "$SCRIPT_DIR/.skillshare/config.yaml"
    # Empty PATH dir so `skillshare` is not found.
    export PATH="$SANDBOX/empty-bin"; mkdir -p "$SANDBOX/empty-bin"

    # shellcheck disable=SC1090
    source "$REPO_ROOT/bootstrap/lib/deploy.sh"

    run sync_skillshare_targets
    assert_success
    assert_output --partial "skipping"
}
```
Note: the second test sets `PATH` to a single empty dir; `command -v skillshare` must rely on PATH only. Restore happens via bats teardown (subshell-scoped `run`).

- [ ] **Step 2: Run to verify failure**

Run:
```bash
cd /Users/chrismandich/Documents/GitHub/Manifest
bats tests/bats/deploy_skills.bats -f "sync_skillshare_targets"
```
Expected: FAIL — `sync_skillshare_targets: command not found`.

- [ ] **Step 3: Implement `sync_skillshare_targets()` in `bootstrap/lib/deploy.sh`**

After `deploy_antigravity_configs()` (added in Task 6), add:
```bash

# Project-scoped Copilot sync via skillshare. Non-blocking: skillshare is an
# enhancement, never load-bearing. Home deploy already happened in deploy_configs.
sync_skillshare_targets() {
    if ! command -v skillshare > /dev/null 2>&1; then
        print_info "skillshare not installed — skipping project-scoped Copilot sync"
        return 0
    fi
    if [[ ! -f "$SCRIPT_DIR/.skillshare/config.yaml" ]]; then
        print_info "No .skillshare/config.yaml — skipping skillshare sync"
        return 0
    fi
    print_step "Syncing skillshare project targets (Copilot)..."
    if (cd "$SCRIPT_DIR" && skillshare sync); then
        print_success "skillshare project targets synced"
    else
        print_warning "skillshare sync failed (non-fatal) — home deploy unaffected"
    fi
}
```

- [ ] **Step 4: Call it from `deploy_configs` (fresh path) after the tool deploys**

In `bootstrap/lib/deploy.sh`, in the fresh path after the new `deploy_antigravity_configs` call (Task 6 Step 5) and before the "List deployed files" block, add:
```bash

    # Project-scoped Copilot sync (non-blocking)
    sync_skillshare_targets
```
And in the merge path, after the merge `deploy_antigravity_configs` call, add:
```bash
                    sync_skillshare_targets
```

- [ ] **Step 5: Run the tests to verify they pass**

Run:
```bash
cd /Users/chrismandich/Documents/GitHub/Manifest
bats tests/bats/deploy_skills.bats
```
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
cd /Users/chrismandich/Documents/GitHub/Manifest
git add bootstrap/lib/deploy.sh tests/bats/deploy_skills.bats
git commit -m "feat: non-blocking skillshare Copilot sync in bootstrap"
```

---

## Task 8: Documentation — skillshare role + drift guard

**Files:**
- Modify: `docs/COMMANDS.md` (or nearest skills doc) — add skillshare section
- Modify: `.claude/CLAUDE.md` (repo developer guide) — note `.skillshare/` source of truth

- [ ] **Step 1: Add a "Skill Management via skillshare" note to `.claude/CLAUDE.md`**

In `/Users/chrismandich/Documents/GitHub/Manifest/.claude/CLAUDE.md`, after the "Repository Layout" section, add:
```markdown
## Skill Management (skillshare)

Skills physically live in `.skillshare/skills/` (the source of truth, managed by
`skillshare`). `configs/claude/skills` is a backward-compat **symlink** to it —
do not replace it with a real directory.

- **Home deploy** (`~/.claude/skills` + Cursor/Gemini/Codex/Antigravity symlinks)
  is owned by `bootstrap.sh` (skillshare cannot expand `~`).
- **skillshare** owns the project-scoped Copilot target (`.github/skills`) and the
  supply-chain lifecycle: `skillshare install <repo>`, `audit`, `check`, `update`.
- `.skillshare/config.yaml` is **committed** (central infra) — edit it only when
  intentionally changing the shared setup, to avoid per-clone drift.
- Automation must read the physical `.skillshare/skills/`; shell globs are
  symlink-safe, but `find`/`os.walk` over `configs/claude/skills` need
  `-L`/`followlinks`.
```

- [ ] **Step 2: Verify the doc renders the intended structure**

Run:
```bash
cd /Users/chrismandich/Documents/GitHub/Manifest
grep -n "Skill Management (skillshare)" .claude/CLAUDE.md
```
Expected: prints the new heading line.

- [ ] **Step 3: Commit**

```bash
cd /Users/chrismandich/Documents/GitHub/Manifest
git add .claude/CLAUDE.md
git commit -m "docs: document skillshare source-of-truth and drift guard"
```

---

## Task 9: Full verification

**Files:** none (verification only)

- [ ] **Step 1: Run the full shell test suite**

Run:
```bash
cd /Users/chrismandich/Documents/GitHub/Manifest
bats tests/bats/
```
Expected: all tests PASS (including the new `deploy_skills.bats`).

- [ ] **Step 2: Lint shell + YAML**

Run:
```bash
cd /Users/chrismandich/Documents/GitHub/Manifest
shellcheck bootstrap/lib/common.sh bootstrap/lib/deploy.sh bootstrap.sh
yamllint .skillshare/config.yaml
python3 -c "import yaml; yaml.safe_load(open('.skillshare/config.yaml'))"
```
Expected: no errors (or only pre-existing shellcheck warnings unrelated to this change).

- [ ] **Step 3: End-to-end sandbox run with a fake HOME (skillshare PRESENT)**

Run:
```bash
cd /Users/chrismandich/Documents/GitHub/Manifest
SBX=$(mktemp -d /tmp/bootstrap_e2e.XXXXXX)
HOME="$SBX" ./bootstrap.sh --skip-install --skip-auth --force --disable-cursor --disable-gemini --disable-codex 2>&1 | tail -20
echo "--- skills present? ---"
ls "$SBX/.claude/skills" | head
test ! -L "$SBX/.claude/skills" && echo "claude skills is a real dir: OK"
test -L "$SBX/.antigravity/skills" && echo "antigravity symlink: OK"
find "$SBX" -name '~' -maxdepth 4    # expect: no output
rm -rf "$SBX"
```
Expected: `~/.claude/skills` is a real directory containing the skills; antigravity symlink exists; no literal `~` dir. (Adjust disable flags if those secondary deploys are needed; the assertions about `.claude/skills` must hold.)

- [ ] **Step 4: End-to-end sandbox run with skillshare HIDDEN (absent path)**

Run:
```bash
cd /Users/chrismandich/Documents/GitHub/Manifest
SBX=$(mktemp -d /tmp/bootstrap_noss.XXXXXX)
# Hide skillshare by giving PATH without its dir but keeping core tools.
HOME="$SBX" PATH="/usr/bin:/bin:/usr/sbin:/sbin" ./bootstrap.sh --skip-install --skip-auth --force --disable-cursor --disable-gemini --disable-codex 2>&1 | tail -20
ls "$SBX/.claude/skills" | head
echo "exit ok — home deploy independent of skillshare"
rm -rf "$SBX"
```
Expected: bootstrap completes; `~/.claude/skills` still populated (home deploy does not depend on skillshare); a notice that Copilot sync was skipped.

- [ ] **Step 5: Confirm clean tree**

Run:
```bash
cd /Users/chrismandich/Documents/GitHub/Manifest
git status -s
git log --oneline -9
```
Expected: clean working tree; commits from Tasks 1–8 present.

---

## Notes for the implementer

- **Do NOT run `skillshare init`** — it is already initialized; re-running can reset `config.yaml`.
- **Audit gate is real:** if `skillshare install` blocks `ai-hooks-integration` on a CRITICAL finding, stop and report — do not bypass.
- **Hook wiring is out of scope:** do not run `ai-hooks-integration`'s `install_all.py`; it is deferred until a concrete hook command is specified.
- **`--delete` in `deploy_home_skills`** enforces source-of-truth (prunes stale skills in `~/.claude/skills`). This is intentional; it changes prior `cp -R` (non-pruning) behavior.
- If `shellcheck` flags the `source` lines in tests, they already carry `# shellcheck disable=SC1090`.
