# Deploy-Stamp Staleness Nudge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface when the local Manifest clone has advanced past the last `./bootstrap.sh` deploy, via a fail-open SessionStart hook that reads a stamp written at deploy time.

**Architecture:** Bootstrap writes `~/.claude/config/deploy_stamp` (git tree hashes of the two deploy sources + metadata) at the end of every deploy. A deployed `deploy_stamp_check.sh` runs as a Claude Code SessionStart hook: it re-hashes the clone's sources and nudges once when they differ, but only on a clean default branch. Comparison is source-to-source (never live-tree) so it never has to replicate merge/gating semantics.

**Tech Stack:** Bash (bootstrap + hook script), Python3 (JSON hook merge, already a bootstrap dependency), bats (tests), git plumbing (`rev-parse HEAD:<path>`).

## Global Constraints

- **Fail-open always:** every error/edge path in the hook and the stamp writer exits 0 / returns 0. A broken check must never block session start or fail a deploy.
- **Error output convention:** `err() { echo "deploy_stamp_check.sh: $*" >&2; }` is canonical; route diagnostics through it, gated behind `DEPLOY_STAMP_DEBUG=1` (a hook must not print on every session).
- **`--help` required** on the user-invocable script: usage + flags, ≤15 lines, exit 0, and the help path runs BEFORE any stamp/git lookup (works in a clean env).
- **Dirty check is scoped to `configs` and `.skillshare/skills` only** — never the whole worktree — in both the writer and the checker. Unrelated WIP must not poison the stamp or the check.
- **Stamp format:** flat `key=value` lines, six keys: `tree_configs`, `tree_skills`, `head_sha`, `dirty`, `clone_path`, `deployed_at`.
- **State root:** dedupe state lives at `${MANIFEST_STATE_ROOT:-$HOME/.manifest}/deploy_stamp_warned`.
- Bats assertions use the repo's `bats-support`/`bats-assert` helpers (`load '../test_helper/bats-*/load'`).

---

### Task 1: Generalize the hook-merge helper (`merge_gemini_hooks` → `merge_settings_hooks`)

The existing `merge_gemini_hooks()` in `bootstrap/lib/deploy.sh` is already event-agnostic (it unions every hook event from a source JSON into a target). Task 4 needs the same operation for Claude's `settings.local.json` in merge-mode. Rename it to a platform-neutral name and reuse it for both, rather than adding a near-duplicate sibling.

**Files:**
- Modify: `bootstrap/lib/deploy.sh:286` (definition) and `bootstrap/lib/deploy.sh:481` (gemini caller)
- Test: `tests/bats/gemini_hooks_merge.bats` (update 5 references)

**Interfaces:**
- Consumes: nothing new.
- Produces: `merge_settings_hooks <src_json> <tgt_json>` — unions every `hooks.<event>[]` entry present in `src` but absent from `tgt` into `tgt` (idempotent; user keys preserved). Prints `Merged repo hooks into existing settings.json` (rc 0, changed), `Existing settings.json already has repo hooks - preserved` (rc 3, no change), or a warning on parse failure. Fail-open (missing python3 → return 0).

- [ ] **Step 1: Rename the definition**

In `bootstrap/lib/deploy.sh`, change the function header at line 286:

```bash
# Union repo-shipped hooks into an EXISTING settings JSON that rsync's
# --ignore-existing would otherwise skip. Event-agnostic: works for any
# hooks.<event>[] shape (Gemini BeforeAgent, Claude SessionStart, …).
# Shared by deploy_gemini_configs and the Claude merge-mode path.
merge_settings_hooks() {
```

(Leave the body unchanged.)

- [ ] **Step 2: Update the gemini caller**

At `bootstrap/lib/deploy.sh:481`, change:

```bash
            merge_settings_hooks "$gemini_source_dir/settings.json" "$GEMINI_TARGET_DIR/settings.json"
```

- [ ] **Step 3: Update the test references**

In `tests/bats/gemini_hooks_merge.bats`, replace all 4 `run merge_gemini_hooks` invocations (lines 46, 63, 65, 81) with `run merge_settings_hooks`, and update the comment on line 2/16 to say `merge_settings_hooks`.

- [ ] **Step 4: Run the gemini hook-merge tests to verify green after rename**

Run: `bats tests/bats/gemini_hooks_merge.bats`
Expected: all tests PASS (behavior unchanged; only the name moved).

- [ ] **Step 5: Commit**

```bash
git add bootstrap/lib/deploy.sh tests/bats/gemini_hooks_merge.bats
git commit -m "refactor(bootstrap): rename merge_gemini_hooks -> merge_settings_hooks for reuse

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_019iHRkgHqwYE2sDty2oroA6"
```

---

### Task 2: `write_deploy_stamp()` helper

The unit that records what was deployed. Pure function: given a clone root and a target dir, write the stamp. Defines the stamp format the checker consumes.

**Files:**
- Modify: `bootstrap/lib/deploy.sh` (add helper near the other siblings, after `merge_settings_hooks`)
- Test: `tests/bats/deploy_stamp.bats` (new)

**Interfaces:**
- Consumes: `print_info`, `print_success` (bootstrap output helpers, stubbed in tests).
- Produces: `write_deploy_stamp <repo_root> <tgt_dir>` — writes `<tgt_dir>/config/deploy_stamp` with six `key=value` lines. Non-git `repo_root` → no stamp, return 0. `dirty` reflects `git status --porcelain -- configs .skillshare/skills` only.

- [ ] **Step 1: Write the failing tests**

Create `tests/bats/deploy_stamp.bats`:

```bash
#!/usr/bin/env bats
# write_deploy_stamp(): records deploy-source tree hashes so the SessionStart
# checker can detect a clone that advanced past the last deploy.

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."

setup() {
    TMP="$(mktemp -d)"
    CLONE="$TMP/clone"
    TGT="$TMP/target"
    mkdir -p "$CLONE/configs/claude" "$CLONE/.skillshare/skills/demo" "$TGT/config"
    echo "orchestration guide" > "$CLONE/configs/claude/CLAUDE.md"
    echo "demo skill" > "$CLONE/.skillshare/skills/demo/SKILL.md"
    git -C "$CLONE" init -q
    git -C "$CLONE" config user.email t@t.test
    git -C "$CLONE" config user.name test
    git -C "$CLONE" add -A
    git -C "$CLONE" commit -qm init

    print_info() { echo "INFO: $*"; }
    print_success() { echo "OK: $*"; }
    export -f print_info print_success 2>/dev/null || true
    # shellcheck disable=SC1091
    source "$REPO_ROOT/bootstrap/lib/deploy.sh" 2>/dev/null || true
}

teardown() { rm -rf "$TMP"; }

stamp_val() { grep "^$1=" "$TGT/config/deploy_stamp" | cut -d= -f2-; }

@test "writes a stamp with all six keys and correct tree hashes" {
    run write_deploy_stamp "$CLONE" "$TGT"
    assert_success
    [ -f "$TGT/config/deploy_stamp" ]
    assert_equal "$(stamp_val tree_configs)" "$(git -C "$CLONE" rev-parse HEAD:configs)"
    assert_equal "$(stamp_val tree_skills)" "$(git -C "$CLONE" rev-parse HEAD:.skillshare/skills)"
    assert_equal "$(stamp_val head_sha)" "$(git -C "$CLONE" rev-parse HEAD)"
    assert_equal "$(stamp_val dirty)" "false"
    assert_equal "$(stamp_val clone_path)" "$CLONE"
    [ -n "$(stamp_val deployed_at)" ]
}

@test "uncommitted change under configs marks dirty=true" {
    echo "edit" >> "$CLONE/configs/claude/CLAUDE.md"
    write_deploy_stamp "$CLONE" "$TGT"
    assert_equal "$(stamp_val dirty)" "true"
}

@test "uncommitted change OUTSIDE deploy sources keeps dirty=false" {
    mkdir -p "$CLONE/tests"
    echo "wip" > "$CLONE/tests/wip.txt"
    write_deploy_stamp "$CLONE" "$TGT"
    assert_equal "$(stamp_val dirty)" "false"
}

@test "non-git source dir writes no stamp and still returns 0" {
    NONGIT="$TMP/nongit"; mkdir -p "$NONGIT/configs" "$TGT2/config"
    TGT2="$TMP/t2"; mkdir -p "$TGT2/config"
    run write_deploy_stamp "$NONGIT" "$TGT2"
    assert_success
    [ ! -f "$TGT2/config/deploy_stamp" ]
}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `bats tests/bats/deploy_stamp.bats`
Expected: FAIL — `write_deploy_stamp: command not found` (function not yet defined).

- [ ] **Step 3: Implement `write_deploy_stamp()`**

In `bootstrap/lib/deploy.sh`, immediately after the `merge_settings_hooks` function's closing brace, add:

```bash
# Record what this deploy shipped so the SessionStart checker
# (deploy_stamp_check.sh) can detect a clone that later advanced past it.
# Source-to-source design: we stamp the git TREE hashes of the two deploy
# sources, never the live tree, so the checker never has to replicate
# merge/gating semantics. Fail-open: a non-git source (tarball copy) gets no
# stamp and the checker then stays silent. The dirty flag is scoped to the two
# deploy-source paths ONLY — unrelated worktree WIP must not poison it, or the
# checker would nudge on a clean-main deploy whose configs/skills were fresh.
write_deploy_stamp() {
    local repo_root="$1" tgt_dir="$2"
    git -C "$repo_root" rev-parse --git-dir > /dev/null 2>&1 || {
        print_info "Source is not a git checkout — skipped deploy stamp"
        return 0
    }
    local tree_configs tree_skills head_sha dirty
    tree_configs="$(git -C "$repo_root" rev-parse HEAD:configs 2> /dev/null)" || return 0
    tree_skills="$(git -C "$repo_root" rev-parse HEAD:.skillshare/skills 2> /dev/null)" || return 0
    head_sha="$(git -C "$repo_root" rev-parse HEAD 2> /dev/null)" || return 0
    if [[ -n "$(git -C "$repo_root" status --porcelain -- configs .skillshare/skills 2> /dev/null)" ]]; then
        dirty=true
    else
        dirty=false
    fi
    mkdir -p "$tgt_dir/config"
    cat > "$tgt_dir/config/deploy_stamp" << EOF
tree_configs=$tree_configs
tree_skills=$tree_skills
head_sha=$head_sha
dirty=$dirty
clone_path=$repo_root
deployed_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
EOF
    print_success "Wrote deploy stamp"
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `bats tests/bats/deploy_stamp.bats`
Expected: all 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add bootstrap/lib/deploy.sh tests/bats/deploy_stamp.bats
git commit -m "feat(bootstrap): write_deploy_stamp() records deploy-source tree hashes

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_019iHRkgHqwYE2sDty2oroA6"
```

---

### Task 3: `deploy_stamp_check.sh` SessionStart checker

The consumer. Reads the stamp, decides whether to nudge, dedupes. The bulk of the logic and the largest test surface.

**Files:**
- Create: `configs/claude/scripts/deploy_stamp_check.sh`
- Test: `tests/bats/deploy_stamp.bats` (append checker tests)

**Interfaces:**
- Consumes: the stamp written by `write_deploy_stamp` (six `key=value` keys); env `HOME`, `MANIFEST_STATE_ROOT`, `DEPLOY_STAMP_DEBUG`.
- Produces: stdout nudge text (non-empty) on stale clean-main drift, else silent. Always exits 0. Writes `${MANIFEST_STATE_ROOT:-$HOME/.manifest}/deploy_stamp_warned` = `<cur_configs>:<cur_skills>` after warning.

- [ ] **Step 1: Write the failing checker tests**

Append to `tests/bats/deploy_stamp.bats`:

```bash
# --- checker: deploy_stamp_check.sh ---

CHECK="$BATS_TEST_DIRNAME/../../configs/claude/scripts/deploy_stamp_check.sh"

# Build a fake HOME whose deploy_stamp points at $CLONE, deployed at its
# current (clean) HEAD. $1 overrides the dirty field (default false).
write_fake_stamp() {
    local dirty="${1:-false}"
    mkdir -p "$FHOME/.claude/config"
    cat > "$FHOME/.claude/config/deploy_stamp" << EOF
tree_configs=$(git -C "$CLONE" rev-parse HEAD:configs)
tree_skills=$(git -C "$CLONE" rev-parse HEAD:.skillshare/skills)
head_sha=$(git -C "$CLONE" rev-parse HEAD)
dirty=$dirty
clone_path=$CLONE
deployed_at=2026-07-03T00:00:00Z
EOF
}

# Advance the clone so its source trees differ from the stamp.
advance_clone() {
    echo "new content" >> "$CLONE/configs/claude/CLAUDE.md"
    git -C "$CLONE" add -A
    git -C "$CLONE" commit -qm advance
}

setup_checker() {
    FHOME="$TMP/home"; mkdir -p "$FHOME/.manifest"
    export HOME_BAK="$HOME"
    # origin/HEAD so the default-branch resolver finds 'main' (or the init branch)
    DEF_BRANCH="$(git -C "$CLONE" rev-parse --abbrev-ref HEAD)"
    git -C "$CLONE" symbolic-ref "refs/remotes/origin/HEAD" "refs/remotes/origin/$DEF_BRANCH" 2>/dev/null || true
}

@test "checker: silent when no stamp file" {
    setup_checker
    run env HOME="$FHOME" MANIFEST_STATE_ROOT="$FHOME/.manifest" bash "$CHECK"
    assert_success
    assert_output ""
}

@test "checker: silent when clone_path does not exist" {
    setup_checker
    mkdir -p "$FHOME/.claude/config"
    cat > "$FHOME/.claude/config/deploy_stamp" << EOF
tree_configs=x
tree_skills=y
head_sha=z
dirty=false
clone_path=$TMP/gone
deployed_at=2026-07-03T00:00:00Z
EOF
    run env HOME="$FHOME" bash "$CHECK"
    assert_success
    assert_output ""
}

@test "checker: silent on a feature branch even when hashes differ" {
    setup_checker
    write_fake_stamp
    advance_clone
    git -C "$CLONE" checkout -q -b feature/x
    run env HOME="$FHOME" MANIFEST_STATE_ROOT="$FHOME/.manifest" bash "$CHECK"
    assert_success
    assert_output ""
}

@test "checker: silent when configs dirty on main" {
    setup_checker
    write_fake_stamp
    advance_clone
    echo "uncommitted" >> "$CLONE/configs/claude/CLAUDE.md"   # dirty source
    run env HOME="$FHOME" MANIFEST_STATE_ROOT="$FHOME/.manifest" bash "$CHECK"
    assert_success
    assert_output ""
}

@test "checker: silent when hashes match and stamp clean" {
    setup_checker
    write_fake_stamp false
    run env HOME="$FHOME" MANIFEST_STATE_ROOT="$FHOME/.manifest" bash "$CHECK"
    assert_success
    assert_output ""
}

@test "checker: nudges once on clean-main drift, then dedupes" {
    setup_checker
    write_fake_stamp
    advance_clone
    run env HOME="$FHOME" MANIFEST_STATE_ROOT="$FHOME/.manifest" bash "$CHECK"
    assert_success
    assert_output --partial "Manifest deploy is stale"
    # second run: same hash → silent
    run env HOME="$FHOME" MANIFEST_STATE_ROOT="$FHOME/.manifest" bash "$CHECK"
    assert_success
    assert_output ""
}

@test "checker: re-nudges after a new commit past a warned drift" {
    setup_checker
    write_fake_stamp
    advance_clone
    env HOME="$FHOME" MANIFEST_STATE_ROOT="$FHOME/.manifest" bash "$CHECK" >/dev/null
    advance_clone   # new hash
    run env HOME="$FHOME" MANIFEST_STATE_ROOT="$FHOME/.manifest" bash "$CHECK"
    assert_success
    assert_output --partial "Manifest deploy is stale"
}

@test "checker: dirty=true stamp with matching hashes still nudges" {
    setup_checker
    write_fake_stamp true   # deployed from a dirty tree — stamp untrusted
    run env HOME="$FHOME" MANIFEST_STATE_ROOT="$FHOME/.manifest" bash "$CHECK"
    assert_success
    assert_output --partial "Manifest deploy is stale"
}

@test "checker: --help exits 0 with usage in a clean env" {
    run env HOME="$TMP/empty" bash "$CHECK" --help
    assert_success
    assert_output --partial "Usage"
}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `bats tests/bats/deploy_stamp.bats -f checker`
Expected: FAIL — script does not exist yet (`No such file or directory`).

- [ ] **Step 3: Implement the checker script**

Create `configs/claude/scripts/deploy_stamp_check.sh`:

```bash
#!/usr/bin/env bash
# deploy_stamp_check.sh — Claude Code SessionStart hook.
#
# Nudge (once) when the local Manifest clone has advanced past the last
# ./bootstrap.sh deploy. Reads ~/.claude/config/deploy_stamp (written by
# bootstrap's write_deploy_stamp) and compares the clone's current
# deploy-source git tree hashes against it. Warns ONLY on a clean default
# branch — feature-branch / dirty-tree drift is expected WIP.
#
# Fail-open: every error path exits 0 so a broken check never blocks a
# session. Diagnostics go to stderr only under DEPLOY_STAMP_DEBUG=1.
set -uo pipefail

err() { echo "deploy_stamp_check.sh: $*" >&2; }
debug() { [[ "${DEPLOY_STAMP_DEBUG:-}" == "1" ]] && err "$*"; return 0; }

usage() {
    cat << 'EOF'
Usage: deploy_stamp_check.sh [--help]

SessionStart hook: warns once when the Manifest git clone has changed
configs/ or skills since the last ./bootstrap.sh deploy. Silent (exit 0)
unless the clone is on a clean default branch AND its sources differ from
the recorded stamp. Set DEPLOY_STAMP_DEBUG=1 for stderr diagnostics.
EOF
}

case "${1:-}" in
    -h | --help)
        usage
        exit 0
        ;;
esac

main() {
    local stamp="${HOME}/.claude/config/deploy_stamp"
    [[ -f "$stamp" ]] || {
        debug "no stamp"
        return 0
    }

    local tree_configs="" tree_skills="" dirty="" clone_path="" deployed_at="" k v
    while IFS='=' read -r k v; do
        case "$k" in
            tree_configs) tree_configs="$v" ;;
            tree_skills) tree_skills="$v" ;;
            dirty) dirty="$v" ;;
            clone_path) clone_path="$v" ;;
            deployed_at) deployed_at="$v" ;;
        esac
    done < "$stamp"

    [[ -n "$clone_path" && -d "$clone_path" ]] || {
        debug "clone path missing: $clone_path"
        return 0
    }
    git -C "$clone_path" rev-parse --git-dir > /dev/null 2>&1 || {
        debug "not a git repo"
        return 0
    }

    local def_branch cur_branch
    def_branch="$(git -C "$clone_path" symbolic-ref --quiet refs/remotes/origin/HEAD 2> /dev/null)"
    def_branch="${def_branch##*/}"
    [[ -n "$def_branch" ]] || def_branch="main"
    cur_branch="$(git -C "$clone_path" rev-parse --abbrev-ref HEAD 2> /dev/null)"
    [[ "$cur_branch" == "$def_branch" ]] || {
        debug "on $cur_branch not $def_branch"
        return 0
    }

    [[ -z "$(git -C "$clone_path" status --porcelain -- configs .skillshare/skills 2> /dev/null)" ]] || {
        debug "dirty sources"
        return 0
    }

    local cur_configs cur_skills
    cur_configs="$(git -C "$clone_path" rev-parse HEAD:configs 2> /dev/null)" || return 0
    cur_skills="$(git -C "$clone_path" rev-parse HEAD:.skillshare/skills 2> /dev/null)" || return 0

    if [[ "$cur_configs" == "$tree_configs" && "$cur_skills" == "$tree_skills" && "$dirty" == "false" ]]; then
        debug "up to date"
        return 0
    fi

    local state_root="${MANIFEST_STATE_ROOT:-$HOME/.manifest}"
    local state_file="$state_root/deploy_stamp_warned"
    local combined="${cur_configs}:${cur_skills}"
    if [[ -f "$state_file" && "$(cat "$state_file" 2> /dev/null)" == "$combined" ]]; then
        debug "already warned for $combined"
        return 0
    fi

    local short_sha
    short_sha="$(git -C "$clone_path" rev-parse --short HEAD 2> /dev/null)"
    cat << EOF
⚠ Manifest deploy is stale: $clone_path ($def_branch @$short_sha) has changed
configs/ or skills since the last deploy on ${deployed_at:-unknown}.
Run ./bootstrap.sh in $clone_path to redeploy.
EOF

    mkdir -p "$state_root" 2> /dev/null || true
    printf '%s\n' "$combined" > "$state_file" 2> /dev/null || true
    return 0
}

main "$@" || true
exit 0
```

- [ ] **Step 4: Make it executable and run the checker tests**

Run:
```bash
chmod +x configs/claude/scripts/deploy_stamp_check.sh
bats tests/bats/deploy_stamp.bats
```
Expected: all tests PASS (4 writer + 9 checker).

- [ ] **Step 5: Lint the script**

Run: `shellcheck configs/claude/scripts/deploy_stamp_check.sh`
Expected: no warnings.

- [ ] **Step 6: Commit**

```bash
git add configs/claude/scripts/deploy_stamp_check.sh tests/bats/deploy_stamp.bats
git commit -m "feat(bootstrap): deploy_stamp_check.sh SessionStart staleness nudge

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_019iHRkgHqwYE2sDty2oroA6"
```

---

### Task 4: Wire into deploy paths + register the SessionStart hook

Tie the pieces into the real deploy: write the stamp in both deploy paths, union the SessionStart hook into an existing `settings.local.json` in merge-mode (which `rsync --ignore-existing` skips), and ship the hook + allow entry in the repo config.

**Files:**
- Modify: `bootstrap/lib/deploy.sh` (2 call sites: merge-mode ~line 132, main path ~line 201; +1 merge-hook call in merge-mode)
- Modify: `configs/claude/settings.local.json` (add SessionStart hook + allow entry)
- Test: `tests/bats/deploy_stamp.bats` (settings-shape assertions)

**Interfaces:**
- Consumes: `write_deploy_stamp` (Task 2), `merge_settings_hooks` (Task 1). `SCRIPT_DIR` (bootstrap global = clone root), `TARGET_DIR` (= `~/.claude`).
- Produces: no new callable; a wired deploy + shipped config.

- [ ] **Step 1: Add the SessionStart hook and allow entry to the repo config**

Edit `configs/claude/settings.local.json`. Inside the `"hooks"` object, after the `"UserPromptSubmit"` array (before the closing `}` of `"hooks"`), add:

```json
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "~/.claude/scripts/deploy_stamp_check.sh"
          }
        ]
      }
    ]
```

And add to the `permissions.allow` array (consistency with existing hook allow entries — not required for hooks to fire):

```json
    "Bash(~/.claude/scripts/deploy_stamp_check.sh:*)"
```

- [ ] **Step 2: Verify the edited JSON is valid**

Run: `python3 -c "import json; d=json.load(open('configs/claude/settings.local.json')); assert d['hooks']['SessionStart'][0]['hooks'][0]['command'].endswith('deploy_stamp_check.sh'); print('ok')"`
Expected: `ok`

- [ ] **Step 3: Wire the main deploy path**

In `bootstrap/lib/deploy.sh`, in the main copy path, immediately after the `write_services_config` call (~line 201), add:

```bash
    # Record the deploy so the SessionStart checker can detect later drift.
    write_deploy_stamp "$SCRIPT_DIR" "$TARGET_DIR"
```

- [ ] **Step 4: Wire the merge-mode path (stamp + hook union)**

In the merge-mode branch (case `2)`), after the existing `preserve_issue_sync_gates ...` line and its cleanup (~line 129, before `print_success "Configurations merged"`), add:

```bash
                    # rsync --ignore-existing skipped the repo settings.local.json,
                    # so a pre-existing live file never gains repo-shipped hooks
                    # (e.g. the new SessionStart nudge). Union them in explicitly.
                    merge_settings_hooks "$source_dir/settings.local.json" "$TARGET_DIR/settings.local.json"
                    write_deploy_stamp "$SCRIPT_DIR" "$TARGET_DIR"
```

- [ ] **Step 5: Add a wiring assertion test**

Append to `tests/bats/deploy_stamp.bats`:

```bash
@test "wiring: repo settings.local.json registers the SessionStart hook" {
    run python3 -c "
import json
d = json.load(open('$REPO_ROOT/configs/claude/settings.local.json'))
cmds = [h['command'] for m in d['hooks']['SessionStart'] for h in m['hooks']]
assert any(c.endswith('deploy_stamp_check.sh') for c in cmds), cmds
allow = d['permissions']['allow']
assert any('deploy_stamp_check.sh' in a for a in allow), 'missing allow entry'
print('wired')"
    assert_success
    assert_output --partial "wired"
}

@test "wiring: both deploy paths call write_deploy_stamp" {
    run grep -c 'write_deploy_stamp "\$SCRIPT_DIR" "\$TARGET_DIR"' "$REPO_ROOT/bootstrap/lib/deploy.sh"
    assert_output "2"
}
```

- [ ] **Step 6: Run the full test file + shellcheck the modified bootstrap lib**

Run:
```bash
bats tests/bats/deploy_stamp.bats
shellcheck bootstrap/lib/deploy.sh
```
Expected: all tests PASS; shellcheck clean.

- [ ] **Step 7: End-to-end smoke — real bootstrap writes a stamp and a fresh check is silent**

Run:
```bash
./bootstrap.sh --skip-auth --force > /dev/null 2>&1
test -f ~/.claude/config/deploy_stamp && echo "stamp written"
~/.claude/scripts/deploy_stamp_check.sh; echo "check exit: $?"
```
Expected: `stamp written`, no nudge output, `check exit: 0` (clone is on `main`; if the working tree has uncommitted plan/spec files under `configs/` the check stays silent anyway — dirty sources).

- [ ] **Step 8: Commit**

```bash
git add bootstrap/lib/deploy.sh configs/claude/settings.local.json tests/bats/deploy_stamp.bats
git commit -m "feat(bootstrap): wire deploy stamp + SessionStart nudge into both deploy paths

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_019iHRkgHqwYE2sDty2oroA6"
```

---

## Self-Review

**Spec coverage:**
- Stamp writer (Component 1) → Task 2 (+ wiring in Task 4). Six keys, scoped dirty, non-git skip: covered by tests 1–4. ✓
- Checker (Component 2), steps 1–7 of its logic → Task 3, checker tests. Default-branch resolution, clean-tree gate, tree-hash compare, dedupe: covered. ✓
- Nudge format → Task 3 implementation + `--partial "Manifest deploy is stale"` assertions. ✓
- Error handling (fail-open, `err()`, `DEPLOY_STAMP_DEBUG`, `--help`) → Global Constraints + Task 3 script + `--help` test. ✓
- Merge-mode hook gap (spec-review finding 1) → Task 1 (generalize helper) + Task 4 Step 4. ✓
- Dirty-scope mismatch (spec-review finding 3) → Global Constraint + Task 2 writer + Task 3 checker both scope to `configs .skillshare/skills`; test "uncommitted change OUTSIDE deploy sources keeps dirty=false". ✓
- `permissions.allow` consistency entry (finding 2) → Task 4 Step 1 + wiring test. ✓
- Out-of-scope items (auto-redeploy, mirror hooks, multi-clone) → not implemented, as intended. ✓

**Placeholder scan:** No TBD/TODO; every code step shows complete code; every run step states expected output. ✓

**Type/name consistency:** `merge_settings_hooks` (Task 1) is the name called in Task 4. `write_deploy_stamp <repo_root> <tgt_dir>` signature consistent across Tasks 2 and 4. Stamp keys (`tree_configs`, `tree_skills`, `head_sha`, `dirty`, `clone_path`, `deployed_at`) identical in writer (Task 2), fake-stamp test helper, and checker parser (Task 3). State file `deploy_stamp_warned` and combined-hash format `<cur_configs>:<cur_skills>` consistent between checker impl and dedupe test. ✓

**Note on Task 3 test helper ordering:** `advance_clone`/`write_fake_stamp` are defined as functions in the appended bats block and called within `@test` bodies; bats sources the whole file before running, so definition order within the file does not matter.
