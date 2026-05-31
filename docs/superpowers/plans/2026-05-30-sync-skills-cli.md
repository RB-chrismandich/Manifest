# sync-skills CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a `sync-skills` native CLI command that syncs `.skillshare/skills/` to all home targets and runs `skillshare sync` for the Copilot target, enabling fast day-to-day skill iteration without running bootstrap.

**Architecture:** Bootstrap deploys a thin shell script to `~/.local/bin/sync-skills` and exports `MANIFEST_ROOT` in the shell profile. The script reads `$MANIFEST_ROOT` to locate the repo, calls `skillshare sync` (non-blocking) for the Copilot target, then runs parallel `rsync --delete` to all home targets. Bootstrap's existing `deploy_home_skills` (additive, no `--delete`) is unchanged — it handles cold install; `sync-skills` handles iteration.

**Tech Stack:** Bash (`set -euo pipefail`), rsync, BATS (bats-support + bats-assert)

---

### Task 1: `scripts/sync-skills.sh` — source script and tests

**Files:**
- Create: `scripts/sync-skills.sh`
- Create: `tests/bats/sync_skills.bats`

- [ ] **Step 1: Create `tests/bats/sync_skills.bats` with failing tests**

```bash
#!/usr/bin/env bats
# Tests for scripts/sync-skills.sh

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
SCRIPT="$REPO_ROOT/scripts/sync-skills.sh"

setup() {
    export BATS_TMPDIR="${BATS_TMPDIR:-/tmp}"
    SANDBOX=$(mktemp -d "$BATS_TMPDIR/sync_skills.XXXXXX")
    MOCK_BIN="$SANDBOX/bin"
    mkdir -p "$MOCK_BIN"

    # Mock rsync: log every invocation, succeed
    cat > "$MOCK_BIN/rsync" <<'STUB'
#!/usr/bin/env bash
echo "rsync $*" >> "$RSYNC_LOG"
STUB
    chmod +x "$MOCK_BIN/rsync"
    export RSYNC_LOG="$SANDBOX/rsync.log"

    # Fake manifest root with a skills source
    export MANIFEST_ROOT="$SANDBOX/repo"
    mkdir -p "$MANIFEST_ROOT/.skillshare/skills/demo-skill"
    echo "body" > "$MANIFEST_ROOT/.skillshare/skills/demo-skill/SKILL.md"

    # Fake home with required ~/.claude/skills target
    export HOME="$SANDBOX/home"
    mkdir -p "$HOME/.claude/skills"

    export PATH="$MOCK_BIN:$PATH"
}

teardown() {
    [[ -n "$SANDBOX" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"
}

@test "exits non-zero with clear message when MANIFEST_ROOT is unset" {
    run env -u MANIFEST_ROOT bash "$SCRIPT"
    assert_failure
    assert_output --partial "MANIFEST_ROOT not set"
}

@test "exits non-zero when MANIFEST_ROOT does not exist" {
    run env MANIFEST_ROOT="/nonexistent/path" bash "$SCRIPT"
    assert_failure
    assert_output --partial "not found"
}

@test "exits non-zero when .skillshare/skills/ is missing" {
    rm -rf "$MANIFEST_ROOT/.skillshare/skills"
    run bash "$SCRIPT"
    assert_failure
    assert_output --partial "skills source not found"
}

@test "runs rsync to ~/.claude/skills/ when skillshare is absent" {
    PATH="$MOCK_BIN" run bash "$SCRIPT"
    assert_success
    assert_output --partial "skillshare not installed"
    grep -q ".claude/skills" "$RSYNC_LOG"
}

@test "calls skillshare sync when skillshare is on PATH" {
    export SKILLSHARE_LOG="$SANDBOX/ss.log"
    cat > "$MOCK_BIN/skillshare" <<'STUB'
#!/usr/bin/env bash
echo "skillshare $*" >> "$SKILLSHARE_LOG"
STUB
    chmod +x "$MOCK_BIN/skillshare"

    run bash "$SCRIPT"
    assert_success
    grep -q "skillshare sync" "$SKILLSHARE_LOG"
}

@test "skips IDE target when directory does not exist" {
    # ~/.cursor/skills does NOT exist under the fake HOME
    run bash "$SCRIPT"
    assert_success
    if [[ -f "$RSYNC_LOG" ]]; then
        run grep ".cursor/skills" "$RSYNC_LOG"
        assert_failure
    fi
}

@test "syncs IDE target when directory exists" {
    mkdir -p "$HOME/.cursor/skills"
    run bash "$SCRIPT"
    assert_success
    grep -q ".cursor/skills" "$RSYNC_LOG"
}

@test "passes --delete flag to rsync" {
    run bash "$SCRIPT"
    assert_success
    grep -q -- "--delete" "$RSYNC_LOG"
}
```

- [ ] **Step 2: Run tests to confirm they all fail**

```bash
bats tests/bats/sync_skills.bats
```

Expected: all 8 tests fail — `scripts/sync-skills.sh` does not exist yet.

- [ ] **Step 3: Create `scripts/sync-skills.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail

[[ -z "${MANIFEST_ROOT:-}" ]] && { echo "Error: MANIFEST_ROOT not set. Re-run bootstrap.sh." >&2; exit 1; }
[[ ! -d "$MANIFEST_ROOT" ]]  && { echo "Error: MANIFEST_ROOT '$MANIFEST_ROOT' not found." >&2; exit 1; }

SKILLS_SRC="$MANIFEST_ROOT/.skillshare/skills"
[[ ! -d "$SKILLS_SRC" ]] && { echo "Error: skills source not found: $SKILLS_SRC" >&2; exit 1; }

# Copilot sync via skillshare (warn and continue if not installed or fails)
if command -v skillshare > /dev/null 2>&1; then
    (cd "$MANIFEST_ROOT" && skillshare sync) || echo "Warning: skillshare sync failed — continuing"
else
    echo "Warning: skillshare not installed — skipping Copilot sync"
fi

# Home targets — parallel rsync so total time = slowest single target
rsync -a --delete "$SKILLS_SRC/" "$HOME/.claude/skills/" &
for dir in "$HOME/.cursor/skills" "$HOME/.gemini/skills" "$HOME/.codex/skills"; do
    [[ -d "$dir" ]] && rsync -a --delete "$SKILLS_SRC/" "$dir/" &
done
wait
```

Make it executable:

```bash
chmod +x scripts/sync-skills.sh
```

- [ ] **Step 4: Run tests to confirm they all pass**

```bash
bats tests/bats/sync_skills.bats
```

Expected: all 8 tests pass.

- [ ] **Step 5: Commit**

```bash
git add scripts/sync-skills.sh tests/bats/sync_skills.bats
git commit -m "feat: add sync-skills source script and BATS tests"
```

---

### Task 2: `bootstrap/lib/auth.sh` — write `MANIFEST_ROOT` to shell profile

**Files:**
- Modify: `bootstrap/lib/auth.sh` (inside `configure_shell_profile_state`, after line 253)
- Modify: `tests/bats/deploy_skills.bats` (append two new tests)

- [ ] **Step 1: Append failing tests to `tests/bats/deploy_skills.bats`**

Add the following at the bottom of `tests/bats/deploy_skills.bats`:

```bash
# ── configure_shell_profile_state — MANIFEST_ROOT ───────────────────────────

@test "configure_shell_profile_state writes MANIFEST_ROOT to shell profile" {
    local fake_home="$SANDBOX/home"
    mkdir -p "$fake_home"
    export HOME="$fake_home"
    export SHELL="/bin/bash"
    export PLATFORM="linux"
    export SCRIPT_DIR="/fake/manifest/path"

    print_step()    { :; }
    print_success() { :; }
    print_info()    { :; }
    print_warning() { :; }
    print_error()   { :; }

    # shellcheck disable=SC1090
    source "$REPO_ROOT/bootstrap/lib/auth.sh"
    configure_shell_profile_state

    grep -q 'export MANIFEST_ROOT=' "$fake_home/.bashrc"
    grep -q '/fake/manifest/path' "$fake_home/.bashrc"
}

@test "configure_shell_profile_state updates MANIFEST_ROOT on re-run with no duplicate lines" {
    local fake_home="$SANDBOX/home"
    mkdir -p "$fake_home"
    echo 'export MANIFEST_ROOT="/old/path"' > "$fake_home/.bashrc"
    export HOME="$fake_home"
    export SHELL="/bin/bash"
    export PLATFORM="linux"
    export SCRIPT_DIR="/new/path"

    print_step()    { :; }
    print_success() { :; }
    print_info()    { :; }
    print_warning() { :; }
    print_error()   { :; }

    # shellcheck disable=SC1090
    source "$REPO_ROOT/bootstrap/lib/auth.sh"
    configure_shell_profile_state

    run grep -c 'export MANIFEST_ROOT=' "$fake_home/.bashrc"
    assert_output "1"
    grep -q '/new/path' "$fake_home/.bashrc"
}
```

- [ ] **Step 2: Run the new tests to confirm they fail**

```bash
bats tests/bats/deploy_skills.bats
```

Expected: the two new `configure_shell_profile_state` tests fail; existing tests still pass.

- [ ] **Step 3: Modify `configure_shell_profile_state` in `bootstrap/lib/auth.sh`**

In `bootstrap/lib/auth.sh`, directly before the closing `}` of `configure_shell_profile_state` (after line 253 — the `print_success "Added MANIFEST_STATE_ROOT..."` line), add:

```bash
    # Write MANIFEST_ROOT — always update in case bootstrap is re-run from a new path.
    # Cross-platform safe: avoids sed -i BSD/GNU incompatibility on macOS.
    if [[ -f "$profile_file" ]]; then
        grep -v 'export MANIFEST_ROOT=' "$profile_file" > "${profile_file}.tmp" || true
        mv "${profile_file}.tmp" "$profile_file"
    fi
    {
        echo ""
        echo "# Manifest repository root (managed by bootstrap.sh)"
        echo "export MANIFEST_ROOT=\"$SCRIPT_DIR\""
    } >> "$profile_file"
    print_success "Updated MANIFEST_ROOT in $profile_file"
```

- [ ] **Step 4: Run tests to confirm they all pass**

```bash
bats tests/bats/deploy_skills.bats
```

Expected: all tests pass including the two new ones.

- [ ] **Step 5: Commit**

```bash
git add bootstrap/lib/auth.sh tests/bats/deploy_skills.bats
git commit -m "feat: write MANIFEST_ROOT to shell profile in configure_shell_profile_state"
```

---

### Task 3: `bootstrap/lib/deploy.sh` — `deploy_sync_skills()` and wiring

**Files:**
- Modify: `bootstrap/lib/deploy.sh` (add function after `sync_skillshare_targets`, call it in both deploy paths)
- Modify: `tests/bats/deploy_skills.bats` (add three new tests, update `deploy_configs` stub)

- [ ] **Step 1: Append failing tests to `tests/bats/deploy_skills.bats`**

Add the following at the bottom of `tests/bats/deploy_skills.bats`:

```bash
# ── deploy_sync_skills ───────────────────────────────────────────────────────

@test "deploy_sync_skills copies script to ~/.local/bin/sync-skills and makes it executable" {
    local fake_home="$SANDBOX/home"
    export HOME="$fake_home"
    mkdir -p "$fake_home"
    local fake_profile="$SANDBOX/profile"
    touch "$fake_profile"
    export SHELL_PROFILE_FILE="$fake_profile"
    export SCRIPT_DIR="$REPO_ROOT"

    print_step()    { :; }
    print_success() { :; }
    print_info()    { :; }

    # shellcheck disable=SC1090
    source "$REPO_ROOT/bootstrap/lib/deploy.sh"

    run deploy_sync_skills
    assert_success

    [ -f "$fake_home/.local/bin/sync-skills" ]
    [ -x "$fake_home/.local/bin/sync-skills" ]
}

@test "deploy_sync_skills adds ~/.local/bin to PATH in shell profile" {
    local fake_home="$SANDBOX/home"
    export HOME="$fake_home"
    mkdir -p "$fake_home"
    local fake_profile="$SANDBOX/profile"
    touch "$fake_profile"
    export SHELL_PROFILE_FILE="$fake_profile"
    export SCRIPT_DIR="$REPO_ROOT"

    print_step()    { :; }
    print_success() { :; }
    print_info()    { :; }

    # shellcheck disable=SC1090
    source "$REPO_ROOT/bootstrap/lib/deploy.sh"

    run deploy_sync_skills
    assert_success

    grep -q ".local/bin" "$fake_profile"
}

@test "deploy_sync_skills PATH entry is idempotent on re-run" {
    local fake_home="$SANDBOX/home"
    export HOME="$fake_home"
    mkdir -p "$fake_home"
    local fake_profile="$SANDBOX/profile"
    touch "$fake_profile"
    export SHELL_PROFILE_FILE="$fake_profile"
    export SCRIPT_DIR="$REPO_ROOT"

    print_step()    { :; }
    print_success() { :; }
    print_info()    { :; }

    # shellcheck disable=SC1090
    source "$REPO_ROOT/bootstrap/lib/deploy.sh"

    deploy_sync_skills
    deploy_sync_skills  # second run — must not duplicate the PATH line

    run grep -c ".local/bin" "$fake_profile"
    assert_output "1"
}
```

- [ ] **Step 2: Run the new tests to confirm they fail**

```bash
bats tests/bats/deploy_skills.bats
```

Expected: the three new `deploy_sync_skills` tests fail; all existing tests still pass.

- [ ] **Step 3: Add `deploy_sync_skills()` to `bootstrap/lib/deploy.sh`**

Add the following function directly after the closing `}` of `sync_skillshare_targets` (after line ~242):

```bash
# Deploy sync-skills CLI to ~/.local/bin/ and ensure it is on PATH.
# Depends on SHELL_PROFILE_FILE being set by configure_shell_profile_state.
deploy_sync_skills() {
    print_step "Deploying sync-skills CLI..."
    mkdir -p "$HOME/.local/bin"
    cp "$SCRIPT_DIR/scripts/sync-skills.sh" "$HOME/.local/bin/sync-skills"
    chmod +x "$HOME/.local/bin/sync-skills"

    if ! grep -Fq ".local/bin" "$SHELL_PROFILE_FILE" 2>/dev/null; then
        {
            echo ""
            echo "# ~/.local/bin for user-installed tools (managed by bootstrap.sh)"
            echo 'export PATH="$HOME/.local/bin:$PATH"'
        } >> "$SHELL_PROFILE_FILE"
    fi

    # Update PATH for the current bootstrap session (PATH Catch-22: profile not
    # sourced until next terminal open, but the user may run sync-skills right away).
    export PATH="$HOME/.local/bin:$PATH"

    print_success "Deployed sync-skills to $HOME/.local/bin/sync-skills"
}
```

- [ ] **Step 4: Run the three new tests to confirm they pass**

```bash
bats tests/bats/deploy_skills.bats
```

Expected: all tests pass.

- [ ] **Step 5: Wire `deploy_sync_skills` into both deploy paths**

In `bootstrap/lib/deploy.sh`, add a `deploy_sync_skills` call after each `sync_skillshare_targets` call.

**Merge path** (around line 56 — the `2)` merge case, just before `return 0`):

```bash
                    sync_skillshare_targets
                    deploy_sync_skills
                    return 0
```

**Fresh-install path** (around line 112 — after the Copilot sync comment block):

```bash
    # Project-scoped Copilot sync (non-blocking)
    sync_skillshare_targets

    # Deploy sync-skills CLI
    deploy_sync_skills
```

- [ ] **Step 6: Update the `deploy_configs (fresh)` test stub in `tests/bats/deploy_skills.bats`**

In the existing `@test "deploy_configs (fresh) puts real skill dirs in TARGET and no '~' junk"` test, add `deploy_sync_skills() { :; }` alongside the other stubs:

```bash
    write_services_config() { :; }
    deploy_cursor_configs() { :; }
    deploy_gemini_configs() { :; }
    deploy_codex_configs() { :; }
    deploy_antigravity_configs() { :; }
    sync_skillshare_targets() { :; }
    deploy_sync_skills() { :; }
```

- [ ] **Step 7: Run the full BATS suite to confirm nothing regressed**

```bash
bats tests/bats/
```

Expected: all tests pass. Count should be prior count + 5 new tests (2 auth + 3 deploy).

- [ ] **Step 8: Commit**

```bash
git add bootstrap/lib/deploy.sh tests/bats/deploy_skills.bats
git commit -m "feat: add deploy_sync_skills() and wire into bootstrap deploy paths"
```

---

### Task 4: Integration smoke test

- [ ] **Step 1: Re-run bootstrap to pick up all three changes**

```bash
./bootstrap.sh --skip-install --skip-auth
```

Expected: output includes "Updated MANIFEST_ROOT in ~/.zshrc" and "Deployed sync-skills to ~/.local/bin/sync-skills".

- [ ] **Step 2: Confirm `MANIFEST_ROOT` is in shell profile with no duplicates**

```bash
grep "MANIFEST_ROOT" ~/.zshrc   # or ~/.bashrc / ~/.bash_profile
```

Expected: exactly one line, e.g. `export MANIFEST_ROOT="/Users/.../Manifest"`.

- [ ] **Step 3: Confirm `sync-skills` is deployed and executable**

```bash
ls -la ~/.local/bin/sync-skills
```

Expected: file exists with execute bit set.

- [ ] **Step 4: Source the shell profile and run `sync-skills` from a different directory**

```bash
source ~/.zshrc   # or ~/.bashrc
cd /tmp
sync-skills
```

Expected: runs without error, syncs skills to `~/.claude/skills/`, warns if skillshare is not installed, exits 0.

- [ ] **Step 5: Verify `~/.claude/skills/` was updated**

```bash
ls ~/.claude/skills/
```

Expected: skill directories match `.skillshare/skills/` contents.

- [ ] **Step 6: Push to remote**

```bash
git push
```
