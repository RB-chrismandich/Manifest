#!/bin/bash

# Deployment, verification, and summary helpers for bootstrap.sh. This file is sourced, not executed.

# Restore user/runtime state from a "Backup and replace" backup.
#
# The repo only owns the contents of configs/claude (CLAUDE.md, config/,
# scripts/, skills/, …). Everything else under ~/.claude is user/runtime state
# created by Claude Code at runtime — installed plugins, chat sessions, task and
# command history, the user's own settings.json, credentials, MCP auth caches,
# and plugin data dirs (.remember, .superpowers, …). The "Backup and replace"
# path moves the entire live directory into a timestamped backup, so this helper
# copies that runtime state back into the freshly created target. Repo-owned
# entries are excluded so the redeploy below provides the authoritative copy.
restore_runtime_state() {
    local backup_dir="$1" target_dir="$2" source_dir="$3"
    [[ -d "$backup_dir" ]] || return 0

    # Build rsync excludes from the repo-owned entries (top level of source_dir,
    # including dotfiles like .plans). These are redeployed, so the fresh config
    # wins; everything else in the backup is runtime state and is restored.
    local excludes=() entry
    for entry in "$source_dir"/* "$source_dir"/.[!.]*; do
        [[ -e "$entry" || -L "$entry" ]] || continue
        excludes+=("--exclude=/$(basename "$entry")")
    done

    # .agent_outputs is recreated below as a symlink into $MANIFEST_OUTPUT_DIR
    # (under ~/.manifest, outside ~/.claude and therefore never part of the
    # backup). Restoring it here is wasted work — create_symlink rm -rf's it
    # moments later — and would be slow if the backup holds a large legacy
    # outputs directory. The authoritative outputs were never moved, so skip it.
    excludes+=("--exclude=/.agent_outputs")

    print_step "Restoring runtime state (plugins, sessions, settings.json, history) from backup"
    # -a preserves symlinks and attributes; trailing slashes copy contents.
    rsync -a "${excludes[@]}" "$backup_dir"/ "$target_dir"/ # array-safe (unconditional += above)
    print_success "Runtime state restored (repo-owned config redeployed fresh)"
}

# Deploy configuration files
deploy_configs() {
    print_header "Deploying Configuration Files"

    local source_dir="$SCRIPT_DIR/configs/claude"
    # Set by the "Backup and replace" path so the main copy path can restore
    # user/runtime state (plugins, sessions, settings.json, …) from the backup.
    local restore_from=""

    # Snapshot the live settings.local.json BEFORE any destructive path below
    # (backup-and-replace mv, --force overwrite, or the repo copy). The repo
    # ships its own settings.local.json that would otherwise clobber any MCP
    # server the user added to their live file; merge_claude_mcp_servers unions
    # the snapshot back in after the copy. Captured here (not in each branch) so
    # it predates the "Backup and replace" mv that moves the live dir aside.
    local preserved_mcp=""
    # TARGET_DIR (not a typo of the local restore_from/source_dir vars above) is
    # the global set in bootstrap.sh (~/.claude), consumed across bootstrap/lib/*.sh.
    # shellcheck disable=SC2153
    if [[ -f "$TARGET_DIR/settings.local.json" ]]; then
        preserved_mcp="$(mktemp)"
        cp "$TARGET_DIR/settings.local.json" "$preserved_mcp"
    fi
    # Snapshot the deployed command_config.yml too: install_issue_hooks.sh flips
    # runtime opt-in gates inside this repo-managed file (issue #461).
    local preserved_cmdcfg=""
    if [[ -f "$TARGET_DIR/config/command_config.yml" ]]; then
        preserved_cmdcfg="$(mktemp)"
        cp "$TARGET_DIR/config/command_config.yml" "$preserved_cmdcfg"
    fi

    # Pilotfish collision guard (spec FR-008): abort BEFORE any destructive copy if
    # an enabled pilotfish deploy would overwrite a foreign ~/.claude/agents dir.
    if ! check_pilotfish_collision "$TARGET_DIR"; then
        return 1
    fi

    # rsync is a hard dependency of every copy path below. Check it BEFORE the
    # destructive `mv` of ~/.claude — failing mid-deploy stranded all user
    # state in the timestamped backup with no recovery message (issue #320).
    if ! command_exists rsync; then
        print_error "rsync is required for deployment but was not found"
        echo ""
        echo "  Install it first:"
        case "${PLATFORM:-}" in
            macos) echo "    brew install rsync" ;;
            *) echo "    sudo apt install rsync   # or dnf/pacman/zypper equivalent" ;;
        esac
        echo ""
        exit 1
    fi

    if [[ ! -d "$source_dir" ]]; then
        print_error "Source directory not found: $source_dir"
        exit 1
    fi

    # Check for existing installation
    if [[ -d "$TARGET_DIR" ]]; then
        if [[ "$FORCE" == true ]]; then
            print_warning "Overwriting existing installation (--force)"
        else
            echo ""
            print_warning "Existing installation found at $TARGET_DIR"
            echo ""
            echo "Options:"
            echo "  1. Backup and replace"
            echo "  2. Merge (keep existing, add new)"
            echo "  3. Cancel"
            echo ""
            read -r -p "Choose option [1/2/3]: " choice

            case $choice in
                1)
                    local backup_dir
                    backup_dir="$TARGET_DIR.backup.$(date +%Y%m%d_%H%M%S)"
                    print_step "Backing up to $backup_dir"
                    mv "$TARGET_DIR" "$backup_dir"
                    # Remember the backup so the main copy path can restore
                    # runtime state (plugins, sessions, settings.json) that the
                    # mv just moved out of the live directory.
                    restore_from="$backup_dir"
                    print_success "Backup created"
                    ;;
                2)
                    print_step "Merging configurations..."
                    # Merge mode - copy only new files (skills handled separately
                    # below; the skills compat symlink must not be copied verbatim)
                    rsync -av --ignore-existing --exclude '/skills' --exclude '/agents' --exclude '/references/pilotfish-delegation.md' "$source_dir/" "$TARGET_DIR/"
                    deploy_home_skills "$SCRIPT_DIR/.skillshare/skills" "$TARGET_DIR/skills"
                    gate_graphify_skill "$TARGET_DIR/skills"
                    gate_pilotfish_agents "$TARGET_DIR" "$source_dir/agents"
                    # --ignore-existing keeps the user's settings.local.json as-is,
                    # but if it was absent the repo copy lands fresh; union back any
                    # MCP servers captured from the live file either way.
                    merge_claude_mcp_servers "$preserved_mcp" "$TARGET_DIR/settings.local.json"
                    [[ -n "$preserved_mcp" ]] && rm -f "$preserved_mcp"
                    preserve_issue_sync_gates "$preserved_cmdcfg" "$TARGET_DIR/config/command_config.yml"
                    [[ -n "$preserved_cmdcfg" ]] && rm -f "$preserved_cmdcfg"
                    # rsync --ignore-existing skipped the repo settings.local.json,
                    # so a pre-existing live file never gains repo-shipped hooks
                    # (e.g. the new SessionStart nudge). Union them in explicitly.
                    merge_settings_hooks "$source_dir/settings.local.json" "$TARGET_DIR/settings.local.json"
                    # ...and repo session defaults (env vars, skillListingBudgetFraction)
                    # the same --ignore-existing skip would strand on existing installs.
                    merge_claude_settings_defaults "$source_dir/settings.local.json" "$TARGET_DIR/settings.local.json"
                    write_deploy_stamp "$SCRIPT_DIR" "$TARGET_DIR"
                    print_success "Configurations merged"
                    # Still write services config
                    write_services_config
                    # Keep legacy output path aligned with shared state root
                    mkdir -p "$MANIFEST_OUTPUT_DIR"
                    create_symlink "$TARGET_DIR/.agent_outputs" "$MANIFEST_OUTPUT_DIR" "Claude agent outputs"
                    # Keep secondary agent configs synced in merge mode
                    deploy_cursor_configs
                    deploy_gemini_configs
                    deploy_codex_configs
                    deploy_antigravity_configs
                    sync_skillshare_targets
                    deploy_sync_skills
                    return 0
                    ;;
                3 | *)
                    print_info "Installation cancelled"
                    exit 0
                    ;;
            esac
        fi
    fi

    # Create target directory and copy files
    print_step "Creating $TARGET_DIR"
    mkdir -p "$TARGET_DIR"
    chmod 700 "$TARGET_DIR"

    # When "Backup and replace" moved the live directory aside, restore the
    # user/runtime state (installed plugins, chat sessions, history, the user's
    # own settings.json, etc.) before redeploying repo-owned config. Without
    # this, a clean replace orphans that state into the backup directory.
    if [[ -n "$restore_from" ]]; then
        restore_runtime_state "$restore_from" "$TARGET_DIR" "$source_dir"
    fi

    print_step "Copying configuration files..."
    # Copy everything EXCEPT skills (skills is a symlink -> .skillshare/skills;
    # copying it verbatim would create a broken link in ~/.claude) and agents/
    # (pilotfish role files are deployed by gate_pilotfish_agents under its toggle,
    # so a disabled or foreign ~/.claude/agents is never clobbered — spec FR-008).
    rsync -a --exclude '/skills' --exclude '/agents' --exclude '/references/pilotfish-delegation.md' "$source_dir"/ "$TARGET_DIR/"
    # Copy dot-prefixed directories (e.g. .plans/) that the glob above skips
    cp -R "$source_dir"/.[!.]* "$TARGET_DIR/" 2> /dev/null || true

    # Restore any user-added MCP servers captured before the copy above so the
    # repo's default settings.local.json does not silently drop them.
    merge_claude_mcp_servers "$preserved_mcp" "$TARGET_DIR/settings.local.json"
    [[ -n "$preserved_mcp" ]] && rm -f "$preserved_mcp"

    # Restore runtime-mutated issue-sync opt-in gates the copy just overwrote.
    preserve_issue_sync_gates "$preserved_cmdcfg" "$TARGET_DIR/config/command_config.yml"
    [[ -n "$preserved_cmdcfg" ]] && rm -f "$preserved_cmdcfg"

    # Deploy skills from the PHYSICAL skillshare source into ~/.claude/skills.
    # Must run before link_shared_assets (create_symlink skips missing targets).
    deploy_home_skills "$SCRIPT_DIR/.skillshare/skills" "$TARGET_DIR/skills"
    # Gate /graphify on its service toggle (FR-012) and reconcile any foreign
    # 'graphify install' residue (FR-010). Runs before the assistant skill symlinks.
    gate_graphify_skill "$TARGET_DIR/skills"
    gate_pilotfish_agents "$TARGET_DIR" "$source_dir/agents"

    # Make scripts executable (.py entry points too — repo perms may lack +x)
    if [[ -d "$TARGET_DIR/scripts" ]]; then
        chmod +x "$TARGET_DIR/scripts"/*.sh "$TARGET_DIR/scripts"/*.py 2> /dev/null || true
        print_success "Made scripts executable"
    fi

    # Keep legacy output path as a symlink into shared ~/.manifest state.
    mkdir -p "$MANIFEST_OUTPUT_DIR"
    create_symlink "$TARGET_DIR/.agent_outputs" "$MANIFEST_OUTPUT_DIR" "Claude agent outputs"

    # Write services configuration
    write_services_config

    # Record the deploy so the SessionStart checker can detect later drift.
    write_deploy_stamp "$SCRIPT_DIR" "$TARGET_DIR"

    print_success "Configuration files deployed to $TARGET_DIR"

    # Deploy Cursor configuration
    deploy_cursor_configs

    # Deploy Gemini configuration
    deploy_gemini_configs

    # Deploy Codex configuration
    deploy_codex_configs

    # Deploy Antigravity configuration
    deploy_antigravity_configs

    # Project-scoped Copilot sync (non-blocking)
    sync_skillshare_targets

    # Deploy sync-skills CLI
    deploy_sync_skills

    # List deployed files
    echo ""
    print_info "Deployed files:"
    list_deployed_files "$TARGET_DIR"
}

# list_deployed_files DIR — print up to 20 deployed config files.
# SIGPIPE-safe: `find | head | while` under bootstrap.sh's `set -e` killed the
# whole bootstrap (exit 141) once the target held >20 matching files — find
# dies of SIGPIPE when head exits, and pipefail surfaces it. Buffer through a
# guarded command substitution instead.
list_deployed_files() {
    local dir="$1" deployed_files file
    deployed_files=$(find "$dir" -type f \( -name "*.md" -o -name "*.yml" -o -name "*.sh" \) 2> /dev/null | head -20) || true
    while IFS= read -r file; do
        [[ -n "$file" ]] && echo "    ${file#"$HOME"/}"
    done <<< "$deployed_files"
    return 0
}

# Deploy Cursor IDE configuration (mirrors .claude with symlinks)
deploy_cursor_configs() {
    # Honor the service toggle — deploying while disabled rewrote ~/.cursor
    # against the user's explicit request (issue #321)
    if [[ "${ENABLE_CURSOR:-true}" != true ]]; then
        print_info "Cursor disabled — skipping config deployment"
        return 0
    fi

    print_step "Deploying Cursor IDE configuration..."

    local cursor_source_dir="$SCRIPT_DIR/configs/cursor"

    if [[ ! -d "$cursor_source_dir" ]]; then
        print_warning "Cursor configuration source not found: $cursor_source_dir"
        print_info "Skipping Cursor config deployment"
        return 0
    fi

    # Create .cursor directory structure
    mkdir -p "$CURSOR_TARGET_DIR/rules"

    # Copy .mdc rule files
    if [[ -d "$cursor_source_dir/rules" ]]; then
        cp "$cursor_source_dir/rules"/*.mdc "$CURSOR_TARGET_DIR/rules/" 2> /dev/null || true
        print_success "Deployed Cursor rules to $CURSOR_TARGET_DIR/rules/"
    fi

    # Copy Cursor MCP config template (global MCP server defaults)
    if [[ -f "$cursor_source_dir/mcp.json" ]]; then
        cp "$cursor_source_dir/mcp.json" "$CURSOR_TARGET_DIR/mcp.json"
        print_success "Deployed Cursor MCP config to $CURSOR_TARGET_DIR/mcp.json"
    fi

    # Link shared assets from ~/.claude to avoid duplicate copies, including shared skills.
    link_shared_assets "$CURSOR_TARGET_DIR" "Cursor" "true"

    print_success "Cursor configuration deployed to $CURSOR_TARGET_DIR"
}

# Union repo-shipped hooks into an EXISTING settings JSON that rsync's
# --ignore-existing would otherwise skip. Event-agnostic: works for any
# hooks.<event>[] shape (Gemini BeforeAgent, Claude SessionStart, …).
# Shared by deploy_gemini_configs and the Claude merge-mode path.
merge_settings_hooks() {
    local src="$1" tgt="$2"
    if ! command_exists python3; then
        print_info "python3 unavailable — skipped hooks merge into existing settings.json"
        return 0
    fi
    local rc=0
    python3 - "$src" "$tgt" << 'PYEOF' || rc=$?
import json, sys
src_path, tgt_path = sys.argv[1], sys.argv[2]
src = json.load(open(src_path))
tgt = json.load(open(tgt_path))
changed = False
for event, entries in src.get("hooks", {}).items():
    cur = tgt.setdefault("hooks", {}).setdefault(event, [])
    for e in entries:
        if e not in cur:
            cur.append(e)
            changed = True
if changed:
    with open(tgt_path, "w") as f:
        json.dump(tgt, f, indent=2)
        f.write("\n")
sys.exit(0 if changed else 3)
PYEOF
    case $rc in
        0) print_success "Merged repo hooks into existing settings.json" ;;
        3) print_info "Existing settings.json already has repo hooks - preserved" ;;
        *) print_warning "Could not merge hooks into existing settings.json (manual merge may be needed)" ;;
    esac
}

# Union repo-shipped top-level default settings (currently
# skillListingBudgetFraction, and any future scalar peer) into an EXISTING
# settings.local.json that rsync's --ignore-existing would otherwise skip, so an
# already-bootstrapped machine still receives new defaults. User-wins: a key the
# user already set is NEVER overwritten. Scope EXCLUDES permissions/hooks/
# mcpServers (their own mergers own those) and env (the settings.json env block
# only reaches spawned subprocesses, so it is never a place we ship Claude
# Code's own runtime defaults). Fail-open like its siblings: a missing python3 or
# unparseable JSON is a skip, not a stop.
merge_claude_settings_defaults() {
    local src="$1" tgt="$2"
    [[ -n "$src" && -f "$src" && -f "$tgt" ]] || return 0
    if ! command_exists python3; then
        print_info "python3 unavailable — skipped settings defaults merge into existing settings.json"
        return 0
    fi
    local rc=0
    python3 - "$src" "$tgt" << 'PYEOF' || rc=$?
import json, sys
src_path, tgt_path = sys.argv[1], sys.argv[2]
# Owned by dedicated mergers, or (env) only meaningful for subprocesses — never a
# top-level default this merger propagates.
OWNED = {"permissions", "hooks", "mcpServers", "env"}
try:
    src = json.load(open(src_path))
    tgt = json.load(open(tgt_path))
except Exception:
    sys.exit(2)
if not isinstance(tgt, dict):
    sys.exit(2)
changed = False
for k, v in src.items():
    if k in OWNED:
        continue
    if k not in tgt:  # user-wins: only fill a key the user has not set
        tgt[k] = v
        changed = True
if not changed:
    sys.exit(3)
with open(tgt_path, "w") as f:
    json.dump(tgt, f, indent=2)
    f.write("\n")
sys.exit(0)
PYEOF
    case $rc in
        0) print_success "Merged repo session defaults into existing settings.json" ;;
        3) print_info "Existing settings.json already has repo session defaults - preserved" ;;
        *) print_warning "Could not merge session defaults into existing settings.json (manual merge may be needed)" ;;
    esac
    return 0
}

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

# Preserve user-added MCP servers across a settings.local.json redeploy.
#
# The repo ships configs/claude/settings.local.json with a default mcpServers
# block. The destructive copy in deploy_configs overwrites the live
# ~/.claude/settings.local.json, which would silently drop any MCP server the
# user added there (e.g. via `claude mcp add --scope local`). deploy_configs
# snapshots the live file BEFORE the copy; this unions the snapshot's mcpServers
# back into the freshly deployed file. The USER's entry wins on key conflicts so
# their servers are kept intact — repo defaults only fill in servers the user
# does not already have. Fail-open: parse errors leave the deployed file
# untouched and warn.
merge_claude_mcp_servers() {
    local preserved="$1" tgt="$2"
    [[ -n "$preserved" && -f "$preserved" ]] || return 0
    [[ -f "$tgt" ]] || return 0
    if ! command_exists python3; then
        print_info "python3 unavailable — skipped MCP server preservation in settings.local.json"
        return 0
    fi
    local rc=0
    python3 - "$preserved" "$tgt" << 'PYEOF' || rc=$?
import json, sys
pre_path, tgt_path = sys.argv[1], sys.argv[2]
try:
    pre = json.load(open(pre_path))
    tgt = json.load(open(tgt_path))
except Exception:
    sys.exit(2)
user_servers = pre.get("mcpServers", {})
if not isinstance(user_servers, dict) or not user_servers:
    sys.exit(3)
repo_servers = tgt.get("mcpServers", {})
if not isinstance(repo_servers, dict):
    repo_servers = {}
merged = dict(repo_servers)
for name, cfg in user_servers.items():
    merged[name] = cfg  # user entry wins on conflict — keep their server intact
if merged == repo_servers:
    sys.exit(3)
tgt["mcpServers"] = merged
with open(tgt_path, "w") as f:
    json.dump(tgt, f, indent=2)
    f.write("\n")
sys.exit(0)
PYEOF
    case $rc in
        0) print_success "Preserved user MCP servers in settings.local.json" ;;
        3) print_info "No user-added MCP servers to preserve in settings.local.json" ;;
        *) print_warning "Could not preserve MCP servers in settings.local.json (manual merge may be needed)" ;;
    esac
    return 0
}

# Preserve runtime-mutated issue-sync opt-in gates across a redeploy.
# install_issue_hooks.sh flips tool_policies.{issue-sync-pr,issue-sync-commit}
# .enabled in the DEPLOYED command_config.yml (a repo-managed file); the copy
# paths overwrite it with the repo default (enabled: false), silently disabling
# the opted-in hooks (issue #461). Scope: ONLY those two enabled: gates — the
# repo copy stays authoritative for everything else. Fail-open like its
# sibling merge_claude_mcp_servers.
preserve_issue_sync_gates() {
    local preserved="$1" tgt="$2"
    [[ -n "$preserved" && -f "$preserved" ]] || return 0
    [[ -f "$tgt" ]] || return 0
    if ! command_exists python3; then
        print_info "python3 unavailable — skipped issue-sync gate preservation in command_config.yml"
        return 0
    fi
    local rc=0
    python3 - "$preserved" "$tgt" << 'PYEOF2' || rc=$?
import re, sys
pre_path, tgt_path = sys.argv[1], sys.argv[2]
HOOKS = ("issue-sync-pr", "issue-sync-commit")


def read_gate(lines, skill):
    inblk = False
    for ln in lines:
        if re.match(r"^  %s:\s*$" % re.escape(skill), ln):
            inblk = True
            continue
        if inblk and re.match(r"^  \S", ln):
            break
        if inblk:
            m = re.match(r"^    enabled:\s*(true|false)", ln)
            if m:
                return m.group(1)
    return None


def write_gate(lines, skill):
    out, inblk, changed = [], False, False
    for ln in lines:
        if re.match(r"^  %s:\s*$" % re.escape(skill), ln):
            inblk = True
            out.append(ln)
            continue
        if inblk and re.match(r"^  \S", ln):
            inblk = False
        if inblk and re.match(r"^    enabled:", ln):
            new = re.sub(r"(enabled:\s*)(true|false)", lambda m: m.group(1) + "true", ln)
            changed = changed or (new != ln)
            ln = new
        out.append(ln)
    return out, changed


try:
    pre = open(pre_path).read().splitlines(keepends=True)
    tgt = open(tgt_path).read().splitlines(keepends=True)
except Exception:
    sys.exit(2)
any_changed = False
for skill in HOOKS:
    if read_gate(pre, skill) != "true":
        continue  # only opt-ins are runtime state worth carrying over
    if read_gate(tgt, skill) == "true":
        continue
    tgt, changed = write_gate(tgt, skill)
    any_changed = any_changed or changed
if not any_changed:
    sys.exit(3)
open(tgt_path, "w").write("".join(tgt))
sys.exit(0)
PYEOF2
    case $rc in
        0) print_success "Preserved issue-sync opt-in gates in command_config.yml" ;;
        3) print_info "No issue-sync opt-in gates to preserve in command_config.yml" ;;
        *) print_warning "Could not preserve issue-sync gates in command_config.yml (re-run install_issue_hooks.sh --enable if needed)" ;;
    esac
    return 0
}

# Deploy Gemini CLI configuration (mirrors .claude with symlinks)
deploy_gemini_configs() {
    if [[ "${ENABLE_GEMINI:-true}" != true ]]; then
        print_info "Gemini disabled — skipping config deployment"
        return 0
    fi

    print_step "Deploying Gemini CLI configuration..."

    local gemini_source_dir="$SCRIPT_DIR/configs/gemini"

    if [[ ! -d "$gemini_source_dir" ]]; then
        print_warning "Gemini configuration source not found: $gemini_source_dir"
        print_info "Skipping Gemini config deployment"
        return 0
    fi

    # Create .gemini directory structure
    mkdir -p "$GEMINI_TARGET_DIR"

    # Copy GEMINI.md
    if [[ -f "$gemini_source_dir/GEMINI.md" ]]; then
        cp "$gemini_source_dir/GEMINI.md" "$GEMINI_TARGET_DIR/GEMINI.md"
        print_success "Deployed GEMINI.md to $GEMINI_TARGET_DIR/"
    fi

    # Copy settings.json (project settings, not auth)
    if [[ -f "$gemini_source_dir/settings.json" ]]; then
        # Merge with existing settings rather than overwriting (preserve auth)
        if [[ -f "$GEMINI_TARGET_DIR/settings.json" ]]; then
            merge_settings_hooks "$gemini_source_dir/settings.json" "$GEMINI_TARGET_DIR/settings.json"
        else
            cp "$gemini_source_dir/settings.json" "$GEMINI_TARGET_DIR/settings.json"
            print_success "Deployed settings.json to $GEMINI_TARGET_DIR/"
        fi
    fi

    # Link shared assets from ~/.claude to avoid duplicate copies, including shared skills.
    link_shared_assets "$GEMINI_TARGET_DIR" "Gemini" "true"

    print_success "Gemini configuration deployed to $GEMINI_TARGET_DIR"
}

# Deploy Codex configuration (mirrors shared assets from .claude)
deploy_codex_configs() {
    if [[ "${ENABLE_CODEX:-true}" != true ]]; then
        print_info "Codex disabled — skipping config deployment"
        return 0
    fi

    print_step "Deploying Codex CLI configuration..."

    # Create ~/.codex if needed but never wipe it (contains auth/history/session data)
    mkdir -p "$CODEX_TARGET_DIR"

    # Prefer repo-specific Codex guide if available; fallback to AGENTS.md at repo root
    if [[ -f "$SCRIPT_DIR/configs/codex/AGENTS.md" ]]; then
        cp "$SCRIPT_DIR/configs/codex/AGENTS.md" "$CODEX_TARGET_DIR/AGENTS.md"
        print_success "Deployed Codex AGENTS.md from configs/codex/"
    elif [[ -f "$SCRIPT_DIR/AGENTS.md" ]]; then
        cp "$SCRIPT_DIR/AGENTS.md" "$CODEX_TARGET_DIR/AGENTS.md"
        print_success "Deployed Codex AGENTS.md from repository root"
    else
        print_warning "No AGENTS.md source found for Codex config"
    fi

    # Link shared assets from ~/.claude to avoid duplicate copies, including shared skills.
    link_shared_assets "$CODEX_TARGET_DIR" "Codex" "true"

    print_success "Codex configuration deployed to $CODEX_TARGET_DIR"
}

# Deploy Antigravity configuration (mirrors .claude with symlinks, matching
# Cursor/Gemini/Codex). Antigravity shares the single source of truth in
# ~/.claude via symlinks for config, skills, and .plans.
#
# It deliberately does NOT link scripts/ (parallel_agent.py) or prompts/ (the
# orchestration guide): agy participates as a provider inside parallel_agent,
# driven purely by config — it is not an orchestrator that runs the script.
deploy_antigravity_configs() {
    if [[ "${ENABLE_ANTIGRAVITY:-true}" != true ]]; then
        print_info "Antigravity disabled — skipping config deployment"
        return 0
    fi

    print_step "Deploying Antigravity configuration..."
    mkdir -p "$ANTIGRAVITY_TARGET_DIR"

    # Prune scripts/prompts links left by an earlier bootstrap so already-deployed
    # machines converge on the reduced set. Only OUR symlinks are removed — a real
    # dir a user created is left untouched (create_symlink also backs those up).
    local orphan
    for orphan in scripts prompts; do
        # Explicit if (not `[[ ]] && rm`): under bootstrap.sh's set -e a false
        # test would return non-zero and abort the whole deploy on the common
        # fresh-install path where no stale link exists.
        if [[ -L "$ANTIGRAVITY_TARGET_DIR/$orphan" ]]; then
            rm -f "$ANTIGRAVITY_TARGET_DIR/$orphan"
        fi
    done

    # Link shared assets from ~/.claude (config, skills, .plans), excluding the
    # orchestrator wiring (scripts, prompts).
    link_shared_assets "$ANTIGRAVITY_TARGET_DIR" "Antigravity" "true" "scripts prompts"
    print_success "Antigravity configuration deployed to $ANTIGRAVITY_TARGET_DIR"
}

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

# Deploy sync-skills CLI to ~/.local/bin/ and ensure it is on PATH.
# Depends on SHELL_PROFILE_FILE being set by configure_shell_profile_state.
deploy_sync_skills() {
    print_step "Deploying sync-skills CLI..."
    mkdir -p "$HOME/.local/bin"
    cp "$SCRIPT_DIR/configs/claude/scripts/sync-skills.sh" "$HOME/.local/bin/sync-skills"
    chmod +x "$HOME/.local/bin/sync-skills"

    if ! grep -Eq '\.local/bin' "$SHELL_PROFILE_FILE" 2> /dev/null; then
        {
            echo ""
            echo "# User-installed tools (managed by bootstrap.sh)"
            # Single-quoted intentionally: $HOME/$PATH must stay literal so they
            # expand in the user's shell at profile-load time, not here.
            # shellcheck disable=SC2016
            echo 'export PATH="$HOME/.local/bin:$PATH"'
        } >> "$SHELL_PROFILE_FILE"
    fi

    # Update PATH for the current bootstrap session (PATH Catch-22: profile not
    # sourced until next terminal open, but the user may run sync-skills right away).
    export PATH="$HOME/.local/bin:$PATH"

    print_success "Deployed sync-skills to $HOME/.local/bin/sync-skills"
}

# Verify installation
# Deploy-time reconciliation review (feature 368). Report-only and fail-open:
# runs deploy_reconcile.sh in PREVIEW mode (never --remove) and prints the
# KEEP/REMOVE summary. It MUST NOT delete anything and MUST NOT abort the deploy
# (call it guarded: `reconcile_deploy_report || print_warning ...`). It does not
# touch verify_errors, so bootstrap still exits non-zero only on real verify
# failure. FR-005/FR-006; Constitution Principle V.
reconcile_deploy_report() {
    local script="$SCRIPT_DIR/configs/claude/scripts/deploy_reconcile.sh"
    [[ -f "$script" ]] || return 0
    command -v python3 > /dev/null 2>&1 || return 0
    print_step "Reviewing deployed environment for orphans (report-only)..."
    local summary
    summary="$(bash "$script" --project "$SCRIPT_DIR" 2> /dev/null | grep '^Summary:' || true)"
    if [[ -n "$summary" ]]; then
        print_info "deploy-reconcile: ${summary}"
        print_info "Run '~/.claude/scripts/deploy_reconcile.sh --project $SCRIPT_DIR' to review; add --remove to prune."
    fi
    return 0
}

verify_installation() {
    print_header "Verifying Installation"

    local errors=0

    # Check deployed files
    print_step "Checking deployed files..."

    local required_files=(
        "$TARGET_DIR/CLAUDE.md"
        "$TARGET_DIR/scripts/parallel_agent.py"
        "$TARGET_DIR/scripts/git_platform.sh"
        "$TARGET_DIR/scripts/git_ops.sh"
        "$TARGET_DIR/config/command_config.yml"
        "$TARGET_DIR/config/mcp_servers.yml"
        "$TARGET_DIR/config/validation_criteria.yml"
        "$TARGET_DIR/config/services.yml"
        "$CURSOR_TARGET_DIR/rules/orchestration.mdc"
        "$CURSOR_TARGET_DIR/mcp.json"
        "$CURSOR_TARGET_DIR/skills/code-audit/SKILL.md"
        "$GEMINI_TARGET_DIR/GEMINI.md"
        "$GEMINI_TARGET_DIR/skills/code-audit/SKILL.md"
        "$CODEX_TARGET_DIR/AGENTS.md"
        "$CODEX_TARGET_DIR/skills/code-audit/SKILL.md"
    )

    for file in "${required_files[@]}"; do
        if [[ -f "$file" ]]; then
            print_success "Found: ${file#"$HOME"/}"
        else
            print_error "Missing: ${file#"$HOME"/}"
            errors=$((errors + 1))
        fi
    done

    echo ""
    print_step "Checking shared state directories..."

    local required_state_dirs=(
        "$MANIFEST_STATE_DIR"
        "$MANIFEST_OUTPUT_DIR"
        "$MANIFEST_TMP_DIR"
        "$MANIFEST_STATE_DIR/claude"
        "$MANIFEST_STATE_DIR/gemini"
        "$MANIFEST_STATE_DIR/cursor"
        "$MANIFEST_STATE_DIR/codex"
        "$MANIFEST_STATE_DIR/codex/sessions"
    )

    local dir
    for dir in "${required_state_dirs[@]}"; do
        if [[ -d "$dir" ]]; then
            print_success "Found: ${dir#"$HOME"/}"
        else
            print_error "Missing: ${dir#"$HOME"/}"
            errors=$((errors + 1))
        fi
    done

    # Check CLI tools based on enabled services
    echo ""
    print_step "Checking enabled CLI tools..."

    local available_tools=0
    local enabled_count=0

    if [[ "$ENABLE_CLAUDE" == true ]]; then
        enabled_count=$((enabled_count + 1))
        if command_exists claude; then
            print_success "claude is available (enabled)"
            available_tools=$((available_tools + 1))
        else
            print_warning "claude is not available (enabled but not installed)"
        fi
    else
        print_info "claude is disabled"
    fi

    if [[ "$ENABLE_GEMINI" == true ]]; then
        enabled_count=$((enabled_count + 1))
        if command_exists gemini; then
            print_success "gemini is available (enabled)"
            available_tools=$((available_tools + 1))
        else
            print_warning "gemini is not available (enabled but not installed)"
        fi
    else
        print_info "gemini is disabled"
    fi

    if [[ "$ENABLE_CURSOR" == true ]]; then
        enabled_count=$((enabled_count + 1))
        if command_exists cursor-agent || [[ -f "$HOME/.local/bin/cursor-agent" ]]; then
            print_success "cursor-agent is available (enabled)"
            available_tools=$((available_tools + 1))
        else
            print_warning "cursor-agent is not available (enabled but not installed)"
        fi
    else
        print_info "cursor is disabled"
    fi

    if [[ "$ENABLE_CODEX" == true ]]; then
        enabled_count=$((enabled_count + 1))
        if command_exists codex; then
            print_success "codex is available (enabled)"
            available_tools=$((available_tools + 1))
        else
            print_warning "codex is not available (enabled but not installed)"
        fi
    else
        print_info "codex is disabled"
    fi

    # Check Git CLI tools
    if [[ "$ENABLE_GH" == true ]]; then
        if command_exists gh; then
            print_success "gh (GitHub CLI) is available"
        else
            print_warning "gh is enabled but not installed"
        fi
    else
        print_info "gh (GitHub CLI) is disabled"
    fi

    if [[ "$ENABLE_GLAB" == true ]]; then
        if command_exists glab; then
            print_success "glab (GitLab CLI) is available"
        else
            print_warning "glab is enabled but not installed"
        fi
    else
        print_info "glab (GitLab CLI) is disabled"
    fi

    # Check jq
    if command_exists jq; then
        print_success "jq is installed (required by git_ops.sh)"
    else
        print_warning "jq is not installed - git_ops.sh will have limited functionality"
    fi

    # Summary
    echo ""
    if [[ $errors -eq 0 ]]; then
        print_success "Installation verified successfully"
    else
        print_error "Installation has $errors error(s)"
    fi

    if [[ $enabled_count -lt 2 ]]; then
        print_warning "Only $enabled_count services enabled - parallel agent features require at least 2"
    elif [[ $available_tools -lt 2 ]]; then
        print_warning "Only $available_tools/$enabled_count enabled tools are installed - parallel features may be limited"
    fi

    return $errors
}

# Print final summary
print_summary() {
    print_header "Setup Complete"

    echo -e "${BOLD}Installation Summary:${NC}"
    echo ""
    echo "  Claude Config:  $TARGET_DIR"
    echo "  Cursor Config:  $CURSOR_TARGET_DIR"
    echo "  Gemini Config:  $GEMINI_TARGET_DIR"
    echo "  Codex Config:   $CODEX_TARGET_DIR"
    echo "  State Root:     $MANIFEST_STATE_DIR"
    echo "  Agent Outputs:  $MANIFEST_OUTPUT_DIR"
    echo "  Temp Files:     $MANIFEST_TMP_DIR"
    echo "  Codex Sessions: $MANIFEST_STATE_DIR/codex/sessions"
    if [[ -n "${SHELL_PROFILE_FILE:-}" ]]; then
        echo "  Shell Profile:  $SHELL_PROFILE_FILE"
    fi
    echo "  Services Config: $TARGET_DIR/config/services.yml"
    if [[ "$INSTALL_MCP" == true ]]; then
        echo "  Cursor MCP:     $CURSOR_TARGET_DIR/mcp.json"
    fi
    echo ""

    echo -e "${BOLD}Service Status:${NC}"
    echo ""
    if [[ "$ENABLE_CLAUDE" == true ]]; then
        if command_exists claude; then
            echo -e "  ${GREEN}✓${NC} claude (enabled, installed)"
        else
            echo -e "  ${YELLOW}○${NC} claude (enabled, not installed)"
        fi
    else
        echo -e "  ${YELLOW}○${NC} claude (disabled)"
    fi

    if [[ "$ENABLE_GEMINI" == true ]]; then
        if command_exists gemini; then
            echo -e "  ${GREEN}✓${NC} gemini (enabled, installed)"
        else
            echo -e "  ${YELLOW}○${NC} gemini (enabled, not installed)"
        fi
    else
        echo -e "  ${YELLOW}○${NC} gemini (disabled)"
    fi

    if [[ "$ENABLE_CURSOR" == true ]]; then
        if command_exists cursor-agent || [[ -f "$HOME/.local/bin/cursor-agent" ]]; then
            echo -e "  ${GREEN}✓${NC} cursor-agent (enabled, installed)"
        else
            echo -e "  ${YELLOW}○${NC} cursor-agent (enabled, not installed)"
        fi
    else
        echo -e "  ${YELLOW}○${NC} cursor (disabled)"
    fi

    if [[ "$ENABLE_CODEX" == true ]]; then
        if command_exists codex; then
            echo -e "  ${GREEN}✓${NC} codex (enabled, installed)"
        else
            echo -e "  ${YELLOW}○${NC} codex (enabled, not installed)"
        fi
    else
        echo -e "  ${YELLOW}○${NC} codex (disabled)"
    fi

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
        if command -v agy > /dev/null 2>&1; then
            echo -e "  ${GREEN}✓${NC} antigravity CLI (agy) installed"
        else
            echo -e "  ${YELLOW}○${NC} antigravity CLI (agy) not found — parallel-agent participation needs it"
            echo -e "    ${BLUE}→${NC} Install via the Antigravity IDE, then run: agy install"
        fi
    else
        echo -e "  ${YELLOW}○${NC} antigravity (disabled)"
    fi
    echo ""

    echo -e "${BOLD}Authentication Commands:${NC}"
    echo ""
    echo "  If any services above need authentication, run these commands:"
    echo ""
    if [[ "$ENABLE_CLAUDE" == true ]]; then
        echo -e "    Claude:  ${CYAN}claude auth login${NC}  or  ${CYAN}export ANTHROPIC_API_KEY='...'${NC}"
    fi
    if [[ "$ENABLE_GEMINI" == true ]]; then
        echo -e "    Gemini:  ${CYAN}gemini${NC} (first run prompts OAuth)  or  ${CYAN}export GEMINI_API_KEY='...'${NC}"
    fi
    if [[ "$ENABLE_CODEX" == true ]]; then
        echo -e "    Codex:   ${CYAN}codex auth login${NC}  or  ${CYAN}export OPENAI_API_KEY='...'${NC}"
    fi
    if [[ "$ENABLE_GH" == true ]]; then
        echo -e "    GitHub:  ${CYAN}gh auth login${NC}"
    fi
    if [[ "$ENABLE_GLAB" == true ]]; then
        echo -e "    GitLab:  ${CYAN}glab auth login${NC}"
    fi
    if [[ "$ENABLE_CURSOR" == true ]]; then
        echo -e "    Cursor:  ${CYAN}cursor-agent login${NC} (or set CURSOR_API_KEY)"
    fi
    if [[ "$INSTALL_MCP" == true ]]; then
        echo "    MCP OAuth:"
        echo -e "      Codex:   ${CYAN}codex mcp login sentry${NC} (repeat for context7, linear)"
        echo "      Claude/Gemini: OAuth runs automatically on first MCP tool use"
    fi
    echo ""

    echo -e "${BOLD}Reconfigure Services:${NC}"
    echo ""
    echo "  # Enable/disable services"
    echo "  ./bootstrap.sh --reconfigure --disable-cursor"
    echo "  ./bootstrap.sh --reconfigure --disable-codex"
    echo "  ./bootstrap.sh --reconfigure --enable-gemini --disable-claude"
    echo ""
    echo "  # Or edit directly:"
    echo "  \$EDITOR ~/.claude/config/services.yml"
    echo ""

    echo -e "${BOLD}Tip: Easy Access${NC}"
    echo ""
    echo "  Shell profile now includes:"
    echo "    export MANIFEST_STATE_ROOT=\"\${MANIFEST_STATE_ROOT:-\$HOME/.manifest}\""
    echo ""
    echo "  Add an alias to run 'manifest' from anywhere (optional):"
    echo ""
    if [[ "$SHELL" == *"zsh"* ]]; then
        echo -e "  ${CYAN}echo 'alias manifest=\"~/.claude/scripts/parallel_agent.py\"' >> ~/.zshrc && source ~/.zshrc${NC}"
    elif [[ "$SHELL" == *"bash"* ]]; then
        echo -e "  ${CYAN}echo 'alias manifest=\"~/.claude/scripts/parallel_agent.py\"' >> ~/.bashrc && source ~/.bashrc${NC}"
    else
        echo -e "  ${CYAN}alias manifest=\"~/.claude/scripts/parallel_agent.py\"${NC}"
        echo "  (Add to your shell profile)"
    fi
    if [[ -n "${SHELL_PROFILE_FILE:-}" ]]; then
        echo ""
        echo "  Reload your shell profile:"
        echo -e "  ${CYAN}source $SHELL_PROFILE_FILE${NC}"
    fi
    echo ""

    echo -e "${BOLD}Quick Start:${NC}"
    echo ""
    echo "  # Test parallel agents (uses enabled services only)"
    echo "  ~/.claude/scripts/parallel_agent.py --json 'Hello from all agents'"
    echo ""
    echo "  # Code review with enabled agents"
    echo "  ~/.claude/scripts/parallel_agent.py --json --review /path/to/file.py"
    echo ""
    echo "  # Use Claude Code commands"
    echo "  claude  # Start Claude Code CLI"
    echo "  # Then use: /python-refactor, /docs-improve-readme, /docs-improve, etc."
    echo ""

    echo -e "${BOLD}Documentation:${NC}"
    echo ""
    echo "  Main guide:     ~/.claude/CLAUDE.md"
    echo "  Skills:         ~/.claude/skills/"
    echo "  Cursor rules:   ~/.cursor/rules/"
    echo "  Gemini guide:   ~/.gemini/GEMINI.md"
    echo "  Codex guide:    ~/.codex/AGENTS.md"
    echo "  Config:         ~/.claude/config/"
    echo ""
}
