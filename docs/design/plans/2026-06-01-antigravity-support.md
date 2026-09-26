# Antigravity Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Antigravity IDE as a first-class platform target in the Manifest bootstrap system, with `configs/antigravity/` symlink hub, `ENABLE_ANTIGRAVITY` toggle, install summary reporting, and bats test coverage.

**Architecture:** `configs/antigravity/` is a pure symlink hub pointing at `../claude/` — no standalone files. Antigravity's Claude Code extension already reads `~/.claude/` natively, so skills, settings, and MCP config are inherited without any extra config. The `ENABLE_ANTIGRAVITY` toggle gates install summary reporting only; `deploy_antigravity_configs` (already implemented) remains unconditional, matching the cursor/gemini/codex pattern.

**Tech Stack:** Bash, bats-core, bats-support, bats-assert

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `configs/antigravity/` | Symlink hub: 5 links → `../claude/` |
| Create | `tests/bats/deploy_antigravity.bats` | Structural test: configs/antigravity/ symlinks |
| Modify | `tests/bats/deploy_skills.bats` | Add idempotency + resolvable-symlink tests |
| Create | `tests/bats/bootstrap_services.bats` | Toggle test: services.yml includes antigravity |
| Modify | `bootstrap/lib/config.sh` | ENABLE_ANTIGRAVITY default, arg parsing, help, parse/load/write services |
| Modify | `bootstrap.sh` | Reconfigure display + services-to-configure block |
| Modify | `bootstrap/lib/deploy.sh` | Install summary service status block |
| Modify | `CLAUDE.md` | Add configs/antigravity/ row to layout table |
| Modify | `README.md` | Add Antigravity to platform description |

---

## Task 1: Write structural test for `configs/antigravity/` (TDD)

**Files:**
- Create: `tests/bats/deploy_antigravity.bats`

- [ ] **Step 1: Create the test file**

```bash
cat > tests/bats/deploy_antigravity.bats << 'EOF'
#!/usr/bin/env bats
# Tests for configs/antigravity/ repo structure

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."

@test "configs/antigravity/ exists" {
    [ -d "$REPO_ROOT/configs/antigravity" ]
}

@test "configs/antigravity/ symlinks all point to ../claude/ and resolve" {
    local ag_dir="$REPO_ROOT/configs/antigravity"
    for name in scripts config prompts skills .plans; do
        [ -L "$ag_dir/$name" ] || (echo "Missing symlink: $name" && false)
        local target
        target=$(readlink "$ag_dir/$name")
        assert_equal "$target" "../claude/$name"
        [ -e "$ag_dir/$name" ] || (echo "Dangling symlink: $name → $target" && false)
    done
}
EOF
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
bats tests/bats/deploy_antigravity.bats
```

Expected: FAIL — `configs/antigravity` directory does not exist yet.

---

## Task 2: Create `configs/antigravity/` symlink directory

**Files:**
- Create: `configs/antigravity/` with 5 symlinks

- [ ] **Step 1: Create the directory and symlinks**

```bash
mkdir -p configs/antigravity
cd configs/antigravity
ln -s ../claude/scripts  scripts
ln -s ../claude/config   config
ln -s ../claude/prompts  prompts
ln -s ../claude/skills   skills
ln -s ../claude/.plans   .plans
cd ../..
```

- [ ] **Step 2: Verify symlinks resolve**

```bash
ls -la configs/antigravity/
# Each entry should show: name -> ../claude/name
for name in scripts config prompts skills .plans; do
    [ -e "configs/antigravity/$name" ] && echo "OK: $name" || echo "BROKEN: $name"
done
```

Expected: all 5 print `OK`.

- [ ] **Step 3: Run the structural test to verify it passes**

```bash
bats tests/bats/deploy_antigravity.bats
```

Expected: PASS (2 tests).

- [ ] **Step 4: Commit**

```bash
git add configs/antigravity/ tests/bats/deploy_antigravity.bats
git commit -m "feat: add configs/antigravity/ symlink hub with structural tests"
```

---

## Task 3: Write services.yml toggle test (TDD)

**Files:**
- Create: `tests/bats/bootstrap_services.bats`

- [ ] **Step 1: Create the test file**

```bash
cat > tests/bats/bootstrap_services.bats << 'EOF'
#!/usr/bin/env bats
# Tests for bootstrap/lib/config.sh write_services_config

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."

setup() {
    export BATS_TMPDIR="${BATS_TMPDIR:-/tmp}"
    SANDBOX=$(mktemp -d "$BATS_TMPDIR/bootstrap_services.XXXXXX")
    export SERVICES_CONFIG="$SANDBOX/config/services.yml"

    # Stub print helpers (defined in common.sh; config.sh calls them)
    print_step()    { :; }
    print_success() { :; }
    print_info()    { :; }
    print_warning() { :; }
    print_error()   { :; }

    # shellcheck disable=SC1090
    source "$REPO_ROOT/bootstrap/lib/config.sh"
}

teardown() {
    [[ -n "$SANDBOX" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"
}

@test "write_services_config emits antigravity section with enabled: false" {
    export ENABLE_CLAUDE=true ENABLE_GEMINI=true ENABLE_CURSOR=true ENABLE_CODEX=true
    export ENABLE_ANTIGRAVITY=false
    export ENABLE_GH=auto ENABLE_GLAB=auto

    run write_services_config
    assert_success

    grep -q "^  antigravity:" "$SERVICES_CONFIG"
    grep -A5 "^  antigravity:" "$SERVICES_CONFIG" | grep -q "enabled: false"
}

@test "write_services_config emits antigravity section with enabled: true" {
    export ENABLE_CLAUDE=true ENABLE_GEMINI=true ENABLE_CURSOR=true ENABLE_CODEX=true
    export ENABLE_ANTIGRAVITY=true
    export ENABLE_GH=auto ENABLE_GLAB=auto

    run write_services_config
    assert_success

    grep -q "^  antigravity:" "$SERVICES_CONFIG"
    grep -A5 "^  antigravity:" "$SERVICES_CONFIG" | grep -q "enabled: true"
}
EOF
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
bats tests/bats/bootstrap_services.bats
```

Expected: FAIL — `write_services_config` does not emit an `antigravity:` section yet.

---

## Task 4: Implement `ENABLE_ANTIGRAVITY` in `bootstrap/lib/config.sh`

**Files:**
- Modify: `bootstrap/lib/config.sh`

- [ ] **Step 1: Add default and tracking var to `init_defaults()` (after `ENABLE_CODEX=true` on line ~28)**

```bash
# In init_defaults(), after:
#     ENABLE_CODEX=true
# Add:
    ENABLE_ANTIGRAVITY=true

# After CODEX_SET=false, add:
    ANTIGRAVITY_SET=false
```

Resulting block (lines ~24–38):
```bash
    ENABLE_CLAUDE=true
    ENABLE_GEMINI=true
    ENABLE_CURSOR=true
    ENABLE_CODEX=true
    ENABLE_ANTIGRAVITY=true
    ENABLE_GH="auto"
    ENABLE_GLAB="auto"

    CLAUDE_SET=false
    GEMINI_SET=false
    CURSOR_SET=false
    CODEX_SET=false
    ANTIGRAVITY_SET=false
    GH_SET=false
    GLAB_SET=false
```

- [ ] **Step 2: Add help text to `print_bootstrap_help()` (after `--disable-codex` line ~57)**

```bash
# After:
#   echo "  --disable-codex     Disable Codex CLI"
# Add:
    echo "  --enable-antigravity   Enable Antigravity IDE (default: enabled)"
    echo "  --disable-antigravity  Disable Antigravity IDE"
```

- [ ] **Step 3: Add arg parsing cases to `parse_bootstrap_args()` (after `CODEX_SET=true` block, before `--enable-gh`)**

```bash
            --enable-antigravity)
                ENABLE_ANTIGRAVITY=true
                ANTIGRAVITY_SET=true
                shift
                ;;
            --disable-antigravity)
                ENABLE_ANTIGRAVITY=false
                ANTIGRAVITY_SET=true
                shift
                ;;
```

- [ ] **Step 4: Add `FILE_ANTIGRAVITY` to `parse_services_config()`**

In the `FILE_*=""` init block at the top of `parse_services_config()` (after `FILE_CODEX=""`):
```bash
    FILE_ANTIGRAVITY=""
```

In the `awk` script, add after the `codex:` section detection line:
```awk
            /^[[:space:]]*antigravity:/ { section="antigravity"; subsection="" }
```

In the `enabled: true` block, add:
```awk
                if (section == "antigravity") print "FILE_ANTIGRAVITY=true;"
```

In the `enabled: false` block, add:
```awk
                if (section == "antigravity") print "FILE_ANTIGRAVITY=false;"
```

- [ ] **Step 5: Add `load_existing_config()` block (after the `CODEX_SET` block)**

```bash
        if [[ "$ANTIGRAVITY_SET" == false && -n "$FILE_ANTIGRAVITY" ]]; then
            ENABLE_ANTIGRAVITY=$FILE_ANTIGRAVITY
        fi
```

- [ ] **Step 6: Add `antigravity:` section to `write_services_config()` heredoc (after the `codex:` section, before `git_cli:`)**

```bash
  # Antigravity IDE - VS Code fork with Claude Code extension
  # Install: Download from https://antigravity.sh
  antigravity:
    enabled: $ENABLE_ANTIGRAVITY
    description: "VS Code-fork IDE; inherits ~/.claude/ config via Claude Code extension"
```

- [ ] **Step 7: Run the toggle test to verify it passes**

```bash
bats tests/bats/bootstrap_services.bats
```

Expected: PASS (2 tests).

- [ ] **Step 8: Shellcheck the modified file**

```bash
shellcheck bootstrap/lib/config.sh
```

Expected: no errors or warnings.

- [ ] **Step 9: Commit**

```bash
git add bootstrap/lib/config.sh tests/bats/bootstrap_services.bats
git commit -m "feat: add ENABLE_ANTIGRAVITY toggle to bootstrap config"
```

---

## Task 5: Update `bootstrap.sh` display blocks

**Files:**
- Modify: `bootstrap.sh`

- [ ] **Step 1: Update reconfigure display in `run_reconfigure()` (around lines 119–133)**

In the `if [[ -f "$SERVICES_CONFIG" ]]; then` branch, after `local old_codex=...`:
```bash
        local old_antigravity=${FILE_ANTIGRAVITY:-unknown}
```

After `echo "  Codex:   $old_codex → $ENABLE_CODEX"`:
```bash
        echo "  Antigravity: $old_antigravity → $ENABLE_ANTIGRAVITY"
```

In the `else` branch, after `echo "  Codex:   (new) → $ENABLE_CODEX"`:
```bash
        echo "  Antigravity: (new) → $ENABLE_ANTIGRAVITY"
```

- [ ] **Step 2: Update services-to-configure block in `main()` (around lines 177–180)**

After `echo "  Codex CLI:   ..."`:
```bash
    echo "  Antigravity: $(if [[ "$ENABLE_ANTIGRAVITY" == true ]]; then echo "enabled"; else echo "disabled"; fi)"
```

- [ ] **Step 3: Shellcheck**

```bash
shellcheck bootstrap.sh
```

Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add bootstrap.sh
git commit -m "feat: add Antigravity to bootstrap reconfigure and services display"
```

---

## Task 6: Update `bootstrap/lib/deploy.sh` install summary

**Files:**
- Modify: `bootstrap/lib/deploy.sh`

- [ ] **Step 1: Add Antigravity service status block to install summary (after Codex block, ~line 517)**

After the `fi` closing the Codex block:
```bash
    if [[ "$ENABLE_ANTIGRAVITY" == true ]]; then
        local antigravity_found=false
        if [[ "$PLATFORM" == "macos" ]]; then
            if [[ -d "/Applications/Antigravity.app" ]] || [[ -d "/Applications/Antigravity IDE.app" ]]; then
                antigravity_found=true
            fi
        fi
        if [[ "$antigravity_found" == true ]]; then
            echo -e "  ${GREEN}✓${NC} antigravity (enabled, installed)"
        else
            echo -e "  ${YELLOW}○${NC} antigravity (enabled, not installed)"
        fi
    else
        echo -e "  ${RED}✗${NC} antigravity (disabled)"
    fi
```

- [ ] **Step 2: Shellcheck**

```bash
shellcheck bootstrap/lib/deploy.sh
```

Expected: no errors.

- [ ] **Step 3: Smoke-test the reconfigure path**

```bash
./bootstrap.sh --reconfigure --disable-antigravity 2>&1 | head -20
```

Expected output includes:
```
  Antigravity: true → false
```

(If `~/.claude/config/services.yml` has a prior `antigravity:` entry, it shows old value → new value; otherwise `(new) → false`.)

- [ ] **Step 4: Commit**

```bash
git add bootstrap/lib/deploy.sh
git commit -m "feat: add Antigravity to bootstrap install summary service status"
```

---

## Task 7: Add idempotency and resolvable-symlink tests to `deploy_skills.bats`

**Files:**
- Modify: `tests/bats/deploy_skills.bats`

- [ ] **Step 1: Add two tests after the existing `deploy_antigravity_configs` test (after line 116)**

```bash
@test "deploy_antigravity_configs is idempotent — second run leaves symlink intact" {
    export TARGET_DIR="$SANDBOX/home/.claude"
    export ANTIGRAVITY_TARGET_DIR="$SANDBOX/home/.antigravity"
    mkdir -p "$TARGET_DIR/skills/demo"

    # shellcheck disable=SC1090
    source "$REPO_ROOT/bootstrap/lib/deploy.sh"

    deploy_antigravity_configs          # first run
    run deploy_antigravity_configs      # second run — must not fail
    assert_success

    [ -L "$ANTIGRAVITY_TARGET_DIR/skills" ]
    [ -d "$ANTIGRAVITY_TARGET_DIR/skills/demo" ]
}

@test "deploy_antigravity_configs skills symlink target is resolvable" {
    export TARGET_DIR="$SANDBOX/home/.claude"
    export ANTIGRAVITY_TARGET_DIR="$SANDBOX/home/.antigravity"
    mkdir -p "$TARGET_DIR/skills/demo"

    # shellcheck disable=SC1090
    source "$REPO_ROOT/bootstrap/lib/deploy.sh"
    deploy_antigravity_configs

    local link_target
    link_target=$(readlink -f "$ANTIGRAVITY_TARGET_DIR/skills" 2>/dev/null || true)
    [ -e "$link_target" ] || (echo "Symlink target not resolvable: $link_target" && false)
    [ -d "$link_target" ]
}
```

- [ ] **Step 2: Run the full deploy_skills suite**

```bash
bats tests/bats/deploy_skills.bats
```

Expected: all tests PASS (existing + 2 new).

- [ ] **Step 3: Run the full bats suite to confirm no regressions**

```bash
bats tests/bats/
```

Expected: all tests PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/bats/deploy_skills.bats
git commit -m "test: add idempotency and resolvable-symlink tests for deploy_antigravity_configs"
```

---

## Task 8: Update documentation

**Files:**
- Modify: `CLAUDE.md` (repository structure table)
- Modify: `README.md` (platform description + layout)

- [ ] **Step 1: Update `CLAUDE.md` repository structure table**

Find the `configs/` block in the `## Repository Structure` section. After the `codex/` row, add:

```markdown
├── antigravity/                         # → ~/.antigravity/ (Antigravity IDE)
│   └── (symlinks to ../claude/)         # scripts, config, prompts, skills, .plans
```

- [ ] **Step 2: Update `README.md` opening description**

Find the line:
```
> Parallel LLM agent orchestration framework for Claude Code, Cursor IDE, Gemini CLI, and Codex CLI
```

Replace with:
```
> Parallel LLM agent orchestration framework for Claude Code, Cursor IDE, Gemini CLI, Codex CLI, and Antigravity IDE
```

Find the sentence:
```
orchestration system to `~/.claude/`, `~/.cursor/`, `~/.gemini/`, and `~/.codex/`, enabling Claude Code,
Cursor IDE, Gemini CLI, and Codex CLI to share guides...
```

Replace with:
```
orchestration system to `~/.claude/`, `~/.cursor/`, `~/.gemini/`, `~/.codex/`, and `~/.antigravity/`, enabling Claude Code,
Cursor IDE, Gemini CLI, Codex CLI, and Antigravity IDE to share guides...
```

- [ ] **Step 3: Verify docs render cleanly**

```bash
# Quick sanity check — no broken markdown syntax
grep -n "antigravity\|Antigravity" CLAUDE.md README.md
```

Expected: entries appear in both files with consistent capitalization.

- [ ] **Step 4: Run full bats suite one final time**

```bash
bats tests/bats/
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md README.md
git commit -m "docs: add Antigravity to platform documentation"
```

---

## Acceptance Verification

Run after all tasks complete:

```bash
# 1. Structural integrity
for name in scripts config prompts skills .plans; do
    [ -e "configs/antigravity/$name" ] && echo "OK: $name" || echo "BROKEN: $name"
done

# 2. Toggle roundtrip
./bootstrap.sh --reconfigure --disable-antigravity 2>&1 | grep -i antigravity
./bootstrap.sh --reconfigure --enable-antigravity  2>&1 | grep -i antigravity

# 3. Full test suite
bats tests/bats/

# 4. Shellcheck clean
shellcheck bootstrap.sh bootstrap/lib/config.sh bootstrap/lib/deploy.sh
```
