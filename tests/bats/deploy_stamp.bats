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
    # T3.8 (spec 674): the stamp keys on plugins/, the source of truth, not on
    # .apm/skills, which is now a gitignored generated mirror and would make the
    # staleness check permanently blind.
    mkdir -p "$CLONE/configs/claude" "$CLONE/plugins/manifest-docs/skills/demo" "$TGT/config"
    echo "orchestration guide" > "$CLONE/configs/claude/CLAUDE.md"
    echo "demo skill" > "$CLONE/plugins/manifest-docs/skills/demo/SKILL.md"
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
    assert_equal "$(stamp_val tree_skills)" "$(git -C "$CLONE" rev-parse HEAD:plugins)"
    assert_equal "$(stamp_val head_sha)" "$(git -C "$CLONE" rev-parse HEAD)"
    assert_equal "$(stamp_val dirty)" "false"
    assert_equal "$(stamp_val clone_path)" "$CLONE"
    assert_equal "$(stamp_val runtime_merge_status)" "unobserved"
    assert_equal "$(stamp_val degraded_components)" "0"
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
    local NONGIT="$TMP/nongit" TGT2="$TMP/t2"
    mkdir -p "$NONGIT/configs" "$TGT2/config"
    run write_deploy_stamp "$NONGIT" "$TGT2"
    assert_success
    [ ! -f "$TGT2/config/deploy_stamp" ]
}

# --- checker: deploy_stamp_check.sh ---

CHECK="$BATS_TEST_DIRNAME/../../configs/claude/scripts/deploy_stamp_check.sh"

# Build a fake HOME whose deploy_stamp points at $CLONE, deployed at its
# current (clean) HEAD. $1 overrides the dirty field (default false).
write_fake_stamp() {
    local dirty="${1:-false}"
    mkdir -p "$FHOME/.claude/config"
    cat > "$FHOME/.claude/config/deploy_stamp" << EOF
tree_configs=$(git -C "$CLONE" rev-parse HEAD:configs)
tree_skills=$(git -C "$CLONE" rev-parse HEAD:plugins)
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

# --- behind-upstream detection (defect: stale-clone drift was undetectable
# when the deploy stamp matches the clone exactly, because the clone itself
# never advanced past the last deploy — it just never pulled from origin) ---

@test "checker: nudges when clean clone matches its stamp but is behind an already-fetched origin ref" {
    setup_checker
    write_fake_stamp false   # stamp matches CLONE's current HEAD exactly
    local old_sha
    old_sha="$(git -C "$CLONE" rev-parse HEAD)"

    # Simulate a fetch that already happened elsewhere: origin/<branch> is
    # 2 commits ahead. The clone's own HEAD never moved (reset back below),
    # reproducing the observed bug: stamp == clone HEAD, but home is stale.
    git -C "$CLONE" commit --allow-empty -qm "upstream advance 1"
    git -C "$CLONE" commit --allow-empty -qm "upstream advance 2"
    git -C "$CLONE" update-ref "refs/remotes/origin/$DEF_BRANCH" "$(git -C "$CLONE" rev-parse HEAD)"
    git -C "$CLONE" reset -q --hard "$old_sha"

    run env HOME="$FHOME" MANIFEST_STATE_ROOT="$FHOME/.manifest" bash "$CHECK"
    assert_success
    assert_output --partial "behind origin/$DEF_BRANCH"
    assert_output --partial "2 commit"

    # second run with the same upstream ref: dedupes to silent
    run env HOME="$FHOME" MANIFEST_STATE_ROOT="$FHOME/.manifest" bash "$CHECK"
    assert_success
    assert_output ""
}

@test "checker: re-nudges once the fetched origin ref advances further" {
    setup_checker
    write_fake_stamp false
    local old_sha
    old_sha="$(git -C "$CLONE" rev-parse HEAD)"
    git -C "$CLONE" commit --allow-empty -qm "upstream advance 1"
    git -C "$CLONE" update-ref "refs/remotes/origin/$DEF_BRANCH" "$(git -C "$CLONE" rev-parse HEAD)"
    git -C "$CLONE" reset -q --hard "$old_sha"
    env HOME="$FHOME" MANIFEST_STATE_ROOT="$FHOME/.manifest" bash "$CHECK" > /dev/null

    # origin advances again (another fetch happened)
    git -C "$CLONE" checkout -q "$DEF_BRANCH" 2> /dev/null || true
    local newer
    newer="$(git -C "$CLONE" commit-tree -p "$(git -C "$CLONE" rev-parse "refs/remotes/origin/$DEF_BRANCH")" -m more "$(git -C "$CLONE" rev-parse HEAD^{tree})")"
    git -C "$CLONE" update-ref "refs/remotes/origin/$DEF_BRANCH" "$newer"

    run env HOME="$FHOME" MANIFEST_STATE_ROOT="$FHOME/.manifest" bash "$CHECK"
    assert_success
    assert_output --partial "behind origin/$DEF_BRANCH"
}

@test "checker: silent when clone is up to date with the fetched origin ref" {
    setup_checker
    write_fake_stamp false
    # origin/<branch> points at the exact same commit as HEAD -> 0 behind.
    git -C "$CLONE" update-ref "refs/remotes/origin/$DEF_BRANCH" "$(git -C "$CLONE" rev-parse HEAD)"

    run env HOME="$FHOME" MANIFEST_STATE_ROOT="$FHOME/.manifest" bash "$CHECK"
    assert_success
    assert_output ""
}

@test "checker: silent (never fetched) when no origin remote-tracking ref exists at all" {
    setup_checker
    write_fake_stamp false
    git -C "$CLONE" update-ref -d "refs/remotes/origin/$DEF_BRANCH" 2> /dev/null || true

    run env HOME="$FHOME" MANIFEST_STATE_ROOT="$FHOME/.manifest" bash "$CHECK"
    assert_success
    assert_output ""
}

@test "checker: nudges when the default branch name contains a slash" {
    # Regression: the resolver used `${def_branch##*/}`, which keeps only the
    # last path component — release/v2 became v2, refs/remotes/origin/v2 does
    # not exist, and the behind-check silently no-opped. Every other checker
    # test runs on a slash-free init branch, so the defect was invisible: the
    # branch name has to VARY inside the check for it to be exercised.
    setup_checker
    git -C "$CLONE" checkout -q -b release/v2
    git -C "$CLONE" symbolic-ref "refs/remotes/origin/HEAD" "refs/remotes/origin/release/v2"
    write_fake_stamp false
    local old_sha
    old_sha="$(git -C "$CLONE" rev-parse HEAD)"

    git -C "$CLONE" commit --allow-empty -qm "upstream advance"
    git -C "$CLONE" update-ref "refs/remotes/origin/release/v2" "$(git -C "$CLONE" rev-parse HEAD)"
    git -C "$CLONE" reset -q --hard "$old_sha"

    run env HOME="$FHOME" MANIFEST_STATE_ROOT="$FHOME/.manifest" bash "$CHECK"
    assert_success
    assert_output --partial "behind origin/release/v2"
    assert_output --partial "1 commit"
}

@test "checker: behind-upstream check stays silent on a feature branch" {
    setup_checker
    write_fake_stamp false
    local old_sha
    old_sha="$(git -C "$CLONE" rev-parse HEAD)"
    git -C "$CLONE" commit --allow-empty -qm "upstream advance"
    git -C "$CLONE" update-ref "refs/remotes/origin/$DEF_BRANCH" "$(git -C "$CLONE" rev-parse HEAD)"
    git -C "$CLONE" reset -q --hard "$old_sha"
    git -C "$CLONE" checkout -q -b feature/y

    run env HOME="$FHOME" MANIFEST_STATE_ROOT="$FHOME/.manifest" bash "$CHECK"
    assert_success
    assert_output ""
}

@test "checker: exits 0 even when git is unavailable on PATH" {
    setup_checker
    write_fake_stamp false
    local nobin="$TMP/nobin"
    mkdir -p "$nobin"
    local t p
    for t in bash cat mkdir; do
        p="$(command -v "$t")" && ln -s "$p" "$nobin/$t"
    done
    run env HOME="$FHOME" MANIFEST_STATE_ROOT="$FHOME/.manifest" PATH="$nobin" bash "$CHECK"
    assert_success
}

@test "wiring: repo settings.runtime.json registers the SessionStart hook" {
    # Hooks AND permissions moved out of settings.local.json: that file is inert
    # at user scope (measured), so a SessionStart hook registered there never
    # fired and its allow-entry was never read.
    run python3 -c "
import json
d = json.load(open('$REPO_ROOT/configs/claude/settings.runtime.json'))
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

@test "checker: surfaces runtime_merge_status=failed even when git hashes match" {
    setup_checker
    write_fake_stamp false
    printf 'runtime_merge_status=failed\ndegraded_components=1\n' >> "$FHOME/.claude/config/deploy_stamp"

    run env HOME="$FHOME" MANIFEST_STATE_ROOT="$FHOME/.manifest" bash "$CHECK"
    assert_success
    assert_output --partial "failed verification"
    assert_output --partial "runtime_merge_status=failed"
    assert_output --partial "degraded_components=1"

    # Identical stamp dedupes on immediate repeat
    run env HOME="$FHOME" MANIFEST_STATE_ROOT="$FHOME/.manifest" bash "$CHECK"
    assert_success
    assert_output ""
}

@test "checker: surfaces non-zero degraded_components when runtime_merge_status=merged" {
    setup_checker
    write_fake_stamp false
    printf 'runtime_merge_status=merged\ndegraded_components=2\n' >> "$FHOME/.claude/config/deploy_stamp"

    run env HOME="$FHOME" MANIFEST_STATE_ROOT="$FHOME/.manifest" bash "$CHECK"
    assert_success
    assert_output --partial "failed verification"
    assert_output --partial "degraded_components=2"
    refute_output --partial "runtime_merge_status=failed"
}

@test "checker: stays silent when runtime_merge_status=merged and degraded_components=0" {
    setup_checker
    write_fake_stamp false
    printf 'runtime_merge_status=merged\ndegraded_components=0\n' >> "$FHOME/.claude/config/deploy_stamp"

    run env HOME="$FHOME" MANIFEST_STATE_ROOT="$FHOME/.manifest" bash "$CHECK"
    assert_success
    assert_output ""
}

# --- verify_installation degraded tracking + deploy_stamp recording ---

setup_verify_sandbox() {
    VHOME="$TMP/vhome"
    VBIN="$TMP/vbin"
    mkdir -p "$VHOME" "$VBIN"
    local tool
    for tool in claude codex jq; do
        printf '#!/bin/sh\nexit 0\n' > "$VBIN/$tool"
        chmod +x "$VBIN/$tool"
    done

    export HOME="$VHOME"
    export XDG_STATE_HOME="$VHOME/.local/state"
    export SCRIPT_DIR="$CLONE"
    export TARGET_DIR="$VHOME/.claude"
    export CURSOR_TARGET_DIR="$VHOME/.cursor"
    export AGY_GEMINI_HOME="$VHOME/.gemini"
    export CODEX_TARGET_DIR="$VHOME/.codex"
    export ANTIGRAVITY_TARGET_DIR="$VHOME/.antigravity"
    export DEVIN_TARGET_DIR="$VHOME/.config/devin"
    export MANIFEST_STATE_DIR="$VHOME/.manifest"
    export MANIFEST_OUTPUT_DIR="$MANIFEST_STATE_DIR/orchestration/outputs"
    export MANIFEST_TMP_DIR="$MANIFEST_STATE_DIR/tmp"
    export ENABLE_CLAUDE=true
    export ENABLE_CODEX=true
    export ENABLE_CURSOR=false
    export ENABLE_ANTIGRAVITY=false
    export ENABLE_DEVIN=false
    export ENABLE_GH=false
    export ENABLE_GLAB=false
    unset CLAUDE_RUNTIME_MERGE_STATUS MANIFEST_HARNESS_STATES MANIFEST_DEGRADED_COMPONENTS MANIFEST_RECEIPT_UPDATED_FOR

    mkdir -p \
        "$TARGET_DIR/scripts" \
        "$TARGET_DIR/config" \
        "$CODEX_TARGET_DIR/skills/code-audit" \
        "$MANIFEST_STATE_DIR/claude" \
        "$MANIFEST_STATE_DIR/cursor" \
        "$MANIFEST_STATE_DIR/codex/sessions" \
        "$MANIFEST_STATE_DIR/antigravity" \
        "$MANIFEST_OUTPUT_DIR" \
        "$MANIFEST_TMP_DIR"
    touch \
        "$TARGET_DIR/scripts/git_platform.sh" \
        "$TARGET_DIR/config/command_config.yml" \
        "$TARGET_DIR/config/mcp_servers.yml" \
        "$TARGET_DIR/config/validation_criteria.yml" \
        "$TARGET_DIR/config/services.yml" \
        "$TARGET_DIR/CLAUDE.md" \
        "$CODEX_TARGET_DIR/AGENTS.md" \
        "$CODEX_TARGET_DIR/skills/code-audit/SKILL.md"

    # shellcheck disable=SC1091
    source "$REPO_ROOT/bootstrap/lib/common.sh"
    # shellcheck disable=SC1091
    source "$REPO_ROOT/bootstrap/lib/deploy.sh"
    export PATH="$VBIN:/usr/bin:/bin"
    write_deploy_stamp "$CLONE" "$TARGET_DIR" >/dev/null
}

vstamp_val() { grep "^$1=" "$TARGET_DIR/config/deploy_stamp" | cut -d= -f2-; }

@test "verify_installation: healthy deploy succeeds and records degraded_components=0" {
    setup_verify_sandbox
    export CLAUDE_RUNTIME_MERGE_STATUS=merged

    run verify_installation
    assert_success
    assert_output --partial "Installation verified successfully"
    assert_equal "$(vstamp_val runtime_merge_status)" "merged"
    assert_equal "$(vstamp_val degraded_components)" "0"
}

@test "verify_installation: runtime_merge_status=failed returns non-zero without success message and records stamp" {
    setup_verify_sandbox
    export CLAUDE_RUNTIME_MERGE_STATUS=failed

    run verify_installation
    assert_failure
    refute_output --partial "verified successfully"
    assert_output --partial "Runtime settings merge failed"
    assert_equal "$(vstamp_val runtime_merge_status)" "failed"
    assert_equal "$(vstamp_val degraded_components)" "1"

    run env HOME="$VHOME" MANIFEST_STATE_ROOT="$MANIFEST_STATE_DIR" bash "$CHECK"
    assert_success
    assert_output --partial "runtime_merge_status=failed"
}

@test "verify_installation: BLOCKED and DEGRADED harness states return non-zero without success message and record stamp" {
    setup_verify_sandbox
    export CLAUDE_RUNTIME_MERGE_STATUS=merged
    cat > "$VBIN/uv" << 'STUB'
#!/bin/sh
printf '{"state":"BLOCKED","harnesses":{"claude":{"state":"READY"},"codex":{"state":"BLOCKED"},"devin":{"state":"DEGRADED"}}}\n'
exit 1
STUB
    chmod +x "$VBIN/uv"
    export MANIFEST_VERIFIED_UV_BIN="$VBIN/uv"

    sync_all_native_harnesses >/dev/null
    run verify_installation
    assert_failure
    refute_output --partial "verified successfully"
    assert_output --partial "Harness codex state is BLOCKED"
    assert_output --partial "Harness devin state is DEGRADED"
    assert_equal "$(vstamp_val runtime_merge_status)" "merged"
    assert_equal "$(vstamp_val degraded_components)" "2"

    run env HOME="$VHOME" MANIFEST_STATE_ROOT="$MANIFEST_STATE_DIR" bash "$CHECK"
    assert_success
    assert_output --partial "degraded_components=2"
}

@test "verify_installation: receipt-shaped declared degradation and selected_optional missing converge at XDG receipt path" {
    setup_verify_sandbox
    export CLAUDE_RUNTIME_MERGE_STATUS=merged
    local receipt_path
    receipt_path="$(manifest_installation_receipt)"
    assert_equal "$receipt_path" "$XDG_STATE_HOME/manifest/installation.json"
    mkdir -p "$(dirname "$receipt_path")"
    python3 - "$receipt_path" <<'PY'
import json, sys
path = sys.argv[1]
doc = {
    "schema_version": 1,
    "selected_optional": ["semgrep"],
    "harnesses": {
        "codex": {
            "harness": "codex",
            "adapter_version": "1",
            "native_version": "0.1.0",
            "plugin_ids": ["manifest-ops@manifest"],
            "owned_entries": [],
            "capabilities": {
                "manifest-ops:hook:version-pin": "degraded",
                "manifest-ops:skill:version-pin": "verified",
                "executable:semgrep": "missing",
                "manifest-security:executable:semgrep": "missing",
            },
            "verified": True,
            "errors": [],
        }
    },
}
with open(path, "w", encoding="utf-8") as handle:
    json.dump(doc, handle)
PY
    run verify_installation
    assert_success
    assert_output --partial "Installation verified successfully"
    assert_equal "$(vstamp_val degraded_components)" "0"
}

@test "verify_installation: receipt fallback flags convergence.py non-convergent statuses and unselected or unpersisted missing capabilities" {
    setup_verify_sandbox
    export CLAUDE_RUNTIME_MERGE_STATUS=merged
    local receipt_path status
    receipt_path="$(manifest_installation_receipt)"
    mkdir -p "$(dirname "$receipt_path")"

    for status in disabled conflicting unknown-transport observation-unavailable requires-interactive-login; do
        python3 - "$receipt_path" "$status" <<'PY'
import json, sys
path, status = sys.argv[1], sys.argv[2]
doc = {
    "schema_version": 1,
    "selected_optional": [],
    "harnesses": {
        "codex": {
            "harness": "codex",
            "adapter_version": "1",
            "native_version": "0.1.0",
            "plugin_ids": ["manifest-workspace@manifest"],
            "owned_entries": [],
            "capabilities": {
                "manifest-ops:hook:version-pin": "degraded",
                "mcp:context7": status,
            },
            "verified": True,
            "errors": [],
        }
    },
}
with open(path, "w", encoding="utf-8") as handle:
    json.dump(doc, handle)
PY
        run verify_installation
        assert_failure
        refute_output --partial "verified successfully"
        assert_output --partial "Harness codex state is DEGRADED"
        assert_equal "$(vstamp_val degraded_components)" "1"
    done

    # Unselected missing capability (selected_optional persisted as empty) fails closed.
    python3 - "$receipt_path" <<'PY'
import json, sys
doc = {
    "schema_version": 1,
    "selected_optional": [],
    "harnesses": {
        "codex": {
            "harness": "codex",
            "verified": True,
            "errors": [],
            "capabilities": {"manifest-workspace:mcp:context7": "missing"},
        }
    },
}
with open(sys.argv[1], "w", encoding="utf-8") as handle:
    json.dump(doc, handle)
PY
    run verify_installation
    assert_failure
    assert_output --partial "Harness codex state is DEGRADED"

    # Missing optional capability without persisted selected_optional also fails closed.
    python3 - "$receipt_path" <<'PY'
import json, sys
doc = {
    "schema_version": 1,
    "harnesses": {
        "codex": {
            "harness": "codex",
            "verified": True,
            "errors": [],
            "capabilities": {"executable:semgrep": "missing"},
        }
    },
}
with open(sys.argv[1], "w", encoding="utf-8") as handle:
    json.dump(doc, handle)
PY
    run verify_installation
    assert_failure
    assert_output --partial "Harness codex state is DEGRADED"
}

@test "verify_installation: ServiceReport JSON converged=true vs converged=false distinguishes declared from undeclared degradation" {
    setup_verify_sandbox
    export CLAUDE_RUNTIME_MERGE_STATUS=merged
    cat > "$VBIN/uv" << 'STUB'
#!/bin/sh
printf 'uv: resolved environment\n' >&2
printf '{"operation":"install","state":"DEGRADED","harnesses":{"codex":{"state":"DEGRADED","converged":true},"devin":{"state":"DEGRADED","converged":false}}}\n'
STUB
    chmod +x "$VBIN/uv"
    export MANIFEST_VERIFIED_UV_BIN="$VBIN/uv"

    sync_all_native_harnesses > /dev/null 2>&1
    run verify_installation
    assert_failure
    refute_output --partial "Harness codex state"
    assert_output --partial "Harness devin state is DEGRADED"
    assert_equal "$(vstamp_val degraded_components)" "1"

    cat > "$VBIN/uv" << 'STUB'
#!/bin/sh
printf 'uv: resolved environment\n' >&2
printf '{"operation":"install","state":"DEGRADED","harnesses":{"codex":{"state":"DEGRADED","converged":true},"claude":{"state":"READY","converged":true}}}\n'
STUB
    chmod +x "$VBIN/uv"
    unset MANIFEST_HARNESS_STATES
    _set_manifest_harness_state "native_harnesses" "BLOCKED"

    sync_all_native_harnesses > /dev/null 2>&1
    run verify_installation
    assert_success
    assert_output --partial "Installation verified successfully"
    assert_equal "$(vstamp_val degraded_components)" "0"
}
