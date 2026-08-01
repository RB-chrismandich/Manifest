#!/bin/bash

# Deployment, verification, and summary helpers for bootstrap.sh. This file is sourced, not executed.

# foreign_state_rules BACKUP_DIR — emit rsync rules (one per line) for state that
# lives under a repo-owned NAME but that no copy path actually redeploys.
#
# restore_runtime_state excludes every top-level name present in configs/claude,
# on the premise that the redeploy right after provides the authoritative copy.
# That premise has since lapsed for two of them, and where it lapsed the exclude
# stopped meaning "the fresh deploy wins" and started meaning "delete":
#
#   skills/  — since the domain retired (SC-006, spec 674) deploy_home_skills
#              writes MANIFEST_SKILLS_DIR (~/.manifest/skills); nothing recreates
#              $TARGET_DIR/skills at all.
#   agents/  — gate_pilotfish_agents/gate_devpanel_agents deploy exactly their own
#              role files, and are documented to let a coexisting user-authored
#              agent survive an opt-out (FR-008/SC-003) — which only holds if the
#              restore carries that agent back.
#
# Measured 2026-07-31: an option-1 rerun took ~/.claude/skills/.system with it
# (Codex's own installs — imagegen, openai-docs, plugin-creator, skill-creator,
# skill-installer) and nothing put it back.
foreign_state_rules() {
    local backup_dir="$1"

    # Order matters: rsync takes the FIRST matching rule, so the re-includes must
    # precede the blanket exclude the caller would otherwise have emitted.
    #
    # Only .system is carried back. Manifest's own skill dirs stay excluded (the
    # deploy is authoritative for those), as do the apm-era manifests
    # .deployed-skills/.metadata.json, which skill_policies.yml already records as
    # untrustworthy dead state — resurrecting them restores noise, not state.
    # Guarded on .system existing so a backup without one does not leave an empty
    # skills/ dir behind.
    if [[ -d "$backup_dir/skills/.system" ]]; then
        printf '%s\n' '--include=/skills/' '--include=/skills/.system/***' '--exclude=/skills/*'
    fi
    printf '%s\n' '--exclude=/skills'

    # agents/ is restored WHOLESALE minus the files the gates own, so a user's own
    # agent survives while a stale role file or ownership marker never comes back:
    # the gate is the sole writer of both, and a restored marker would read as
    # "Manifest-owned" over files this deploy never placed.
    local role
    for role in ${PILOTFISH_AGENT_FILES[@]+"${PILOTFISH_AGENT_FILES[@]}"} \
        ${DEVPANEL_AGENT_FILES[@]+"${DEVPANEL_AGENT_FILES[@]}"}; do
        printf -- '--exclude=/agents/%s\n' "$role"
    done
    printf '%s\n' '--exclude=/agents/.pilotfish' '--exclude=/agents/.devpanel'
}

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
    local excludes=() entry base
    for entry in "$source_dir"/* "$source_dir"/.[!.]*; do
        [[ -e "$entry" || -L "$entry" ]] || continue
        base="$(basename "$entry")"
        # skills/ and agents/ hold entries no copy path redeploys, so a blanket
        # exclude there is a delete, not a deferral — foreign_state_rules emits
        # the finer rules for both (and still excludes what the deploy owns).
        case "$base" in
            skills | agents) continue ;;
        esac
        excludes+=("--exclude=/$base")
    done
    # Regenerable bytecode caches, and a live source of rsync failures: a
    # bundled venv's __pycache__ can change under rsync mid-copy, which is
    # exactly what aborted a deploy on 2026-07-30. Nothing needs them restored.
    #
    # Ordered BEFORE foreign_state_rules on purpose: rsync takes the first
    # matching rule, and those rules re-include whole subtrees (skills/.system/***),
    # so a __pycache__ living inside one would otherwise match the include first
    # and walk straight back into the failure this exclude exists to prevent.
    excludes+=("--exclude=__pycache__/" "--exclude=*.pyc")

    local rule
    while IFS= read -r rule; do
        [[ -n "$rule" ]] && excludes+=("$rule")
    done < <(foreign_state_rules "$backup_dir")

    # .agent_outputs is recreated below as a symlink into $MANIFEST_OUTPUT_DIR
    # (under ~/.manifest, outside ~/.claude and therefore never part of the
    # backup). Restoring it here is wasted work — create_symlink rm -rf's it
    # moments later — and would be slow if the backup holds a large legacy
    # outputs directory. The authoritative outputs were never moved, so skip it.
    excludes+=("--exclude=/.agent_outputs")

    print_step "Restoring runtime state (plugins, sessions, settings.json, history) from backup"
    # -a preserves symlinks and attributes; trailing slashes copy contents.
    #
    # NEVER let this abort the caller. By the time we get here the live
    # directory has already been `mv`'d into the backup, so under `set -e` a
    # non-zero rsync leaves the user with NO ~/.claude at all — one unreadable
    # file destroys the home. Runtime state is best-effort; the deploy that
    # follows is what actually matters, and the backup still holds everything.
    local rc=0
    rsync -a "${excludes[@]}" "$backup_dir"/ "$target_dir"/ || rc=$? # array-safe
    if [[ "$rc" -ne 0 ]]; then
        print_warning "Runtime state only partially restored (rsync exit $rc)."
        print_warning "Nothing was lost — the full backup is at: $backup_dir"
    else
        print_success "Runtime state restored (repo-owned config redeployed fresh)"
    fi

    verify_plugin_cache_after_restore "$target_dir"
    return 0
}

# verify_plugin_cache_after_restore — is every installed bundle still resolvable
# in the cache after a "Backup and replace" restore? (T4.5, spec 674)
#
# The rsync above deliberately swallows failure, which is correct: by then the
# live directory has been mv'd into the backup, so a non-zero exit under `set -e`
# would leave the user with NO ~/.claude at all. But swallowing it makes a
# PARTIAL restore invisible -- and post-cutover ~/.claude/plugins holds the ONLY
# copy of the user's Claude skills. One unreadable file in a 929 MB tree becomes
# an unknown subset of 108 skills silently vanishing.
#
# So: name the bundles that no longer resolve and print the exact command to get
# each back. Never fails the deploy — the deploy is not what broke.
verify_plugin_cache_after_restore() {
    local target_dir="$1"
    local installed="$target_dir/plugins/installed_plugins.json"
    [[ -r "$installed" ]] || return 0
    command_exists python3 || return 0

    local helper="$SCRIPT_DIR/configs/claude/scripts/unresolved_plugins.py"
    [[ -r "$helper" ]] || return 0

    # Exit 3 is "cannot tell", not "nothing wrong". `|| true` alone collapses
    # the two, and a corrupt installed_plugins.json after a restore is exactly
    # what this check exists to surface.
    local missing status
    missing="$(python3 "$helper" "$installed" 2> /dev/null)" && status=0 || status=$?
    if [[ "$status" -eq 3 ]]; then
        print_warning "Could not read $installed — plugin resolution is UNKNOWN."
        print_warning "    Check it by hand: claude plugin list"
        return 0
    fi
    [[ -n "$missing" ]] || return 0

    print_warning "These installed plugins no longer resolve in the cache:"
    local key
    for key in $missing; do
        print_warning "    $key  ->  claude plugin install $key"
    done
    print_warning "Also useful: claude plugin prune (removes orphaned auto-installed deps)"
}

# Deploy configuration files
deploy_configs() {
    print_header "Deploying Configuration Files"

    local source_dir="$SCRIPT_DIR/configs/claude"
    # Set by the "Backup and replace" path so the main copy path can restore
    # user/runtime state (plugins, sessions, settings.json, …) from the backup.
    local restore_from=""

    # $TARGET_DIR (~/.claude) is shared infrastructure: Gemini/Cursor/Codex/
    # Antigravity all symlink into its scripts/config/prompts/.plans/skills
    # (link_shared_assets) regardless of ENABLE_CLAUDE, so this function must
    # NOT early-return like deploy_gemini_configs/deploy_cursor_configs/etc do —
    # that would break every other enabled assistant's deploy. CLAUDE.md itself,
    # however, is Claude-CLI-specific content (nothing else reads it), so it
    # alone is excluded from the copy when Claude is disabled — matching the
    # same "disabled → don't (re)deploy the guide file" behavior used for
    # GEMINI.md/AGENTS.md, and making warn_stale_disabled_configs' "claude"
    # entry meaningful instead of a guaranteed false positive (#549).
    local claude_md_exclude=()
    if [[ "${ENABLE_CLAUDE:-true}" != true ]]; then
        claude_md_exclude=(--exclude '/CLAUDE.md')
    fi

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
    # devpanel collision guard: same rationale, independent toggle/marker, same
    # target dir (~/.claude/agents) on disjoint filenames.
    if ! check_devpanel_collision "$TARGET_DIR"; then
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
            echo "  1. Backup and replace (destructive: moves $TARGET_DIR aside first)"
            echo "  2. Add new files only (existing files are NOT updated)"
            echo "  3. Cancel"
            echo "  4. Update config: refresh repo-owned files, keep runtime state"
            echo ""
            echo "  Most re-runs want 4 — it deploys edited config without moving anything."
            echo ""
            # Options 1-3 keep their historical numbers so an operator's muscle
            # memory (and any scripted answer) still means what it always did;
            # the new non-destructive path is appended as 4.
            read -r -p "Choose option [1/2/3/4]: " choice

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
                2 | 4)
                    # Two non-destructive copy modes that differ ONLY in whether
                    # an already-deployed file may be overwritten. Everything
                    # after the rsync is shared so both land in the same state.
                    #
                    #   2 = add-only   (--ignore-existing): never touches a file
                    #       that already exists, so an edited repo-owned config
                    #       is silently NOT deployed.
                    #   4 = update     (no --ignore-existing): refreshes
                    #       repo-owned files in place.
                    #
                    # NEITHER passes --delete: a file present in $TARGET_DIR but
                    # absent from the repo is user/runtime state (plugins, chat
                    # sessions, notes) and is never removed. That is what makes 4
                    # a safe default and the reason it exists — without it the
                    # only way to deploy an edited config was option 1, which
                    # `mv`s the entire live home aside.
                    local copy_mode=()
                    if [[ "$choice" == 2 ]]; then
                        print_step "Adding new configuration files (existing files left as-is)..."
                        copy_mode=(--ignore-existing)
                    else
                        print_step "Updating repo-owned configuration (runtime state kept)..."
                    fi
                    if [[ "${ENABLE_CLAUDE:-true}" != true ]]; then
                        print_info "Claude disabled — not deploying CLAUDE.md"
                    fi
                    # Same excludes as every other copy path: skills is a compat
                    # symlink (deployed separately below, never copied verbatim),
                    # and agents/agents-devpanel plus their delegation docs are
                    # owned by the gate_* toggles.
                    rsync -av "${copy_mode[@]+"${copy_mode[@]}"}" --exclude '/skills' --exclude '/agents' --exclude '/agents-devpanel' --exclude '/references/pilotfish-delegation.md' --exclude '/references/devpanel-delegation.md' "${claude_md_exclude[@]+"${claude_md_exclude[@]}"}" "$source_dir/" "$TARGET_DIR/"
                    deploy_home_skills "$SCRIPT_DIR/.apm/skills" "${MANIFEST_SKILLS_DIR:-$TARGET_DIR/skills}" harness-skills
                    gate_graphify_skill "$TARGET_DIR/skills"
                    gate_pilotfish_agents "$TARGET_DIR" "$source_dir/agents"
                    gate_devpanel_agents "$TARGET_DIR" "$source_dir/agents-devpanel"
                    # Option 2 keeps an existing settings.local.json as-is; option 4
                    # (like the main copy path) overwrites it with the repo copy, and
                    # if it was absent the repo copy lands fresh either way. Union
                    # back the MCP servers snapshotted from the live file in all
                    # three cases.
                    merge_claude_mcp_servers "$preserved_mcp" "$TARGET_DIR/settings.local.json"
                    [[ -n "$preserved_mcp" ]] && rm -f "$preserved_mcp"
                    preserve_issue_sync_gates "$preserved_cmdcfg" "$TARGET_DIR/config/command_config.yml"
                    [[ -n "$preserved_cmdcfg" ]] && rm -f "$preserved_cmdcfg"
                    # NOTE: Claude hooks are no longer merged into settings.local.json.
                    # That file is inert at user scope (measured; see
                    # merge_claude_runtime_settings), so hooks merged there never fired.
                    # They now ship in settings.hooks.json and are merged into
                    # settings.json below. merge_settings_hooks is still used by the
                    # Gemini path, which reads its own settings.json.
                    # ...and repo session defaults (env vars, skillListingBudgetFraction)
                    # that option 2's --ignore-existing skip would strand on existing
                    # installs. Idempotent, so option 4 runs it too.
                    merge_claude_settings_defaults "$source_dir/settings.local.json" "$TARGET_DIR/settings.local.json"
                    # Hooks that must reach Claude Code's own runtime go to
                    # settings.json; settings.local.json is inert at user scope.
                    merge_claude_runtime_settings "$source_dir/settings.runtime.json" "$TARGET_DIR/settings.json"
                    install_claude_mcp_servers "$source_dir/config/mcp_user_servers.json" "$TARGET_DIR/settings.local.json"
                    write_deploy_stamp "$SCRIPT_DIR" "$TARGET_DIR"
                    if [[ "$choice" == 2 ]]; then
                        print_success "New configuration files added (existing files unchanged)"
                    else
                        print_success "Configuration updated (runtime state kept)"
                    fi
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
                    deploy_sync_skills
                    cp "$SCRIPT_DIR/configs/claude/pyproject.toml" "$TARGET_DIR/pyproject.toml"
                    cp "$SCRIPT_DIR/configs/claude/uv.lock" "$TARGET_DIR/uv.lock"
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
    if [[ "${ENABLE_CLAUDE:-true}" != true ]]; then
        print_info "Claude disabled — not deploying CLAUDE.md"
    fi
    # Copy everything EXCEPT skills (skills is a symlink -> .apm/skills;
    # copying it verbatim would create a broken link in ~/.claude), agents/
    # (pilotfish role files are deployed by gate_pilotfish_agents under its toggle,
    # so a disabled or foreign ~/.claude/agents is never clobbered — spec FR-008),
    # and agents-devpanel/ (same rationale, gate_devpanel_agents, independent toggle).
    # CLAUDE.md is excluded too when Claude is disabled (see claude_md_exclude above).
    rsync -a --exclude '/skills' --exclude '/agents' --exclude '/agents-devpanel' --exclude '/references/pilotfish-delegation.md' --exclude '/references/devpanel-delegation.md' "${claude_md_exclude[@]+"${claude_md_exclude[@]}"}" "$source_dir"/ "$TARGET_DIR/"
    # Copy dot-prefixed directories (e.g. .plans/) that the glob above skips
    cp -R "$source_dir"/.[!.]* "$TARGET_DIR/" 2> /dev/null || true

    # uv project root must live at $TARGET_DIR/ (not only via rsync) for uv sync --project
    cp "$SCRIPT_DIR/configs/claude/pyproject.toml" "$TARGET_DIR/pyproject.toml"
    cp "$SCRIPT_DIR/configs/claude/uv.lock" "$TARGET_DIR/uv.lock"

    # Restore any user-added MCP servers captured before the copy above so the
    # repo's default settings.local.json does not silently drop them.
    merge_claude_mcp_servers "$preserved_mcp" "$TARGET_DIR/settings.local.json"
    [[ -n "$preserved_mcp" ]] && rm -f "$preserved_mcp"

    # Restore runtime-mutated issue-sync opt-in gates the copy just overwrote.
    preserve_issue_sync_gates "$preserved_cmdcfg" "$TARGET_DIR/config/command_config.yml"
    [[ -n "$preserved_cmdcfg" ]] && rm -f "$preserved_cmdcfg"

    # Hooks that must reach Claude Code's own runtime go to settings.json;
    # settings.local.json is inert at user scope (see merge_claude_runtime_settings).
    merge_claude_runtime_settings "$source_dir/settings.runtime.json" "$TARGET_DIR/settings.json"
    install_claude_mcp_servers "$source_dir/config/mcp_user_servers.json" "$TARGET_DIR/settings.local.json"

    # Deploy skills from the PHYSICAL .apm/skills source into ~/.claude/skills.
    # No-op once apm owns the `skills` domain (SC-006) — see apm_domains.yml.
    # Must run before link_shared_assets (create_symlink skips missing targets).
    deploy_home_skills "$SCRIPT_DIR/.apm/skills" "${MANIFEST_SKILLS_DIR:-$TARGET_DIR/skills}" harness-skills
    register_manifest_marketplace "$SCRIPT_DIR"

    # T2.5 (spec 674): repoint every sibling home at the harness root, from HERE
    # and unconditionally. Doing it inside the per-assistant deploy functions
    # leaves --disable-<assistant> pointing at a tree Manifest no longer writes,
    # and Devin (ENABLE_DEVIN defaults FALSE) never repointed at all.
    repoint_sibling_skill_links

    # Gate /graphify on its service toggle (FR-012) and reconcile any foreign
    # 'graphify install' residue (FR-010). Runs before the assistant skill symlinks.
    gate_graphify_skill "${MANIFEST_SKILLS_DIR:-$TARGET_DIR/skills}"
    gate_pilotfish_agents "$TARGET_DIR" "$source_dir/agents"
    gate_devpanel_agents "$TARGET_DIR" "$source_dir/agents-devpanel"

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

    # Deploy Devin CLI configuration (opt-in; inheritance pin only)
    deploy_devin_config

    # Project-scoped Copilot sync (non-blocking)

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

# Manifest-tracked prune of orphan Cursor rules (spec 2026-07-11
# cursor-feature-parity WS-3 / #505). Mirrors deploy_home_skills's
# prune model (common.sh:144-171): a `.deployed-rules` manifest records the
# *.mdc basenames we shipped last deploy; anything in that manifest that is
# no longer in the source (skill renamed/removed) AND still present in dest
# gets removed. Rules never in the manifest — i.e. user-authored rules the
# user dropped into ~/.cursor/rules/ themselves — are never touched.
# orchestration.mdc and commands-index.mdc are excluded from the manifest (and
# thus never prune-eligible): they are hand/generator-maintained singletons,
# not one-per-skill.
prune_cursor_rules() {
    local src_rules_dir="$1"
    local dest_rules_dir="$2"
    local manifest="$dest_rules_dir/.deployed-rules"

    local src_rule_count
    src_rule_count=$(find "$src_rules_dir" -maxdepth 1 -type f -name '*.mdc' | wc -l | tr -d ' ')

    if [[ -f "$manifest" && "$src_rule_count" -gt 0 ]]; then
        local rule_name
        while IFS= read -r rule_name; do
            case "$rule_name" in
                '' | */* | .* | *..* | orchestration.mdc | commands-index.mdc) continue ;;
            esac
            if [[ ! -f "$src_rules_dir/$rule_name" && -f "$dest_rules_dir/$rule_name" ]]; then
                rm -f "${dest_rules_dir:?}/${rule_name}"
                print_info "Pruned orphan Cursor rule: $rule_name"
            fi
        done < "$manifest"
    fi

    # Atomic manifest write: a failed subshell must not truncate the previous
    # manifest (that would silently disable future pruning). The two
    # protected singletons are excluded at the find level so they can never
    # end up manifest-tracked / prune-eligible.
    if (cd "$src_rules_dir" && find . -maxdepth 1 -type f -name '*.mdc' \
        ! -name 'orchestration.mdc' ! -name 'commands-index.mdc' |
        LC_ALL=C sort | sed 's|^\./||') > "$manifest.tmp"; then
        mv "$manifest.tmp" "$manifest"
    else
        rm -f "$manifest.tmp"
    fi
}

# Deploy Cursor IDE configuration (mirrors .claude with symlinks)
# repoint_sibling_skill_links — point every non-Claude home's `skills` entry at
# the harness root (T2.5, spec 674).
#
# UNCONDITIONAL by design. Every existing repoint sits inside a per-assistant
# deploy function behind an early-return toggle: deploy_cursor_configs guards on
# ENABLE_CURSOR, and deploy_devin_config guards on ENABLE_DEVIN which DEFAULTS
# FALSE. So `./bootstrap.sh --disable-cursor` would leave ~/.cursor/skills
# pointing at a tree Manifest no longer writes, and Devin would get zero skills
# on a default machine -- both silently, because a stale symlink is not an error.
#
# Disabling an assistant means Manifest stops deploying ITS configs. It has never
# meant "leave that assistant's skills pointing somewhere wrong", and the two
# only became separable once the shared root moved.
repoint_sibling_skill_links() {
    local root="${MANIFEST_SKILLS_DIR:-$TARGET_DIR/skills}"
    if [[ ! -d "$root" ]]; then
        print_warning "Harness skills root missing: $root (siblings not repointed)"
        return 0
    fi

    # DEVIN IS DELIBERATELY ABSENT FROM THIS LIST UNTIL PHASE 4 (T2.6).
    #
    # Devin discovers ~/.claude/skills natively via its config.json
    # `read_config_from.claude`. Phase 2 FREEZES that tree but does not empty it
    # -- emptying is Phase 4. So creating ~/.config/devin/skills now would give
    # Devin two views of the same catalog and register every skill twice under
    # two namespaces (/devin:env-check AND /claude:env-check, measured against
    # devin 3000.2.17), halving the listing's signal density.
    #
    # The plan's argument for adding it here is that the double-registration
    # "inverts once ~/.claude/skills is empty" -- which is true, and true only
    # AFTER Phase 4. Until then Devin keeps inheriting natively and needs
    # nothing. Adding it in Phase 4, together with the emptying, is the step
    # that is actually safe.
    local home_dir
    for home_dir in "$CURSOR_TARGET_DIR" "$GEMINI_TARGET_DIR" "$CODEX_TARGET_DIR" \
        "$ANTIGRAVITY_TARGET_DIR"; do
        [[ -n "$home_dir" ]] || continue
        mkdir -p "$home_dir"
        create_symlink "$home_dir/skills" "$root" "$(basename "$home_dir") skills"
    done
}

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
        prune_cursor_rules "$cursor_source_dir/rules" "$CURSOR_TARGET_DIR/rules"
    fi

    # Copy Cursor MCP config template (global MCP server defaults)
    if [[ -f "$cursor_source_dir/mcp.json" ]]; then
        cp "$cursor_source_dir/mcp.json" "$CURSOR_TARGET_DIR/mcp.json"
        print_success "Deployed Cursor MCP config to $CURSOR_TARGET_DIR/mcp.json"
    fi

    # Copy Cursor lifecycle-hooks config (spec 2026-07-11 cursor-feature-parity
    # WS-4). Hook commands reference ~/.cursor/scripts/<name>, which
    # link_shared_assets below symlinks to $TARGET_DIR/scripts, so the
    # referenced scripts resolve regardless of copy order within this function.
    if [[ -f "$cursor_source_dir/hooks.json" ]]; then
        cp "$cursor_source_dir/hooks.json" "$CURSOR_TARGET_DIR/hooks.json"
        print_success "Deployed Cursor hooks config to $CURSOR_TARGET_DIR/hooks.json"
    fi

    # Pilotfish role-agents (spec 2026-07-11 cursor-feature-parity WS-5): the
    # same six role names with Cursor-native frontmatter
    # (configs/cursor/agents/, generated by generate_cursor_agents.py), under
    # the identical --enable-pilotfish toggle and manifest-owned prune
    # semantics as the Claude deploy. gate_pilotfish_agents/
    # check_pilotfish_collision (bootstrap/lib/common.sh) are already
    # home-agnostic (parametrized by $1 home / $2 src_agents), so both are
    # reused verbatim here rather than duplicated for Cursor.
    #
    # A pilotfish-only collision is treated as non-fatal to the rest of the
    # Cursor deploy (rules/mcp/hooks already copied above): it skips just the
    # agents step, unlike Claude's whole-deploy abort — the Cursor deploy is a
    # set of surgical file copies, not one destructive rsync of the whole
    # target, so there is no correctness reason to abort the unrelated steps.
    if check_pilotfish_collision "$CURSOR_TARGET_DIR"; then
        gate_pilotfish_agents "$CURSOR_TARGET_DIR" "$cursor_source_dir/agents"
    else
        print_warning "pilotfish: skipped Cursor role-agents deploy due to collision (see above)"
    fi

    # devpanel role-agents: same generated dir (configs/cursor/agents/, both role
    # sets land there via generate_cursor_agents.py — see that script), same
    # home-agnostic gate/collision reuse, independent toggle and non-fatal
    # collision handling as pilotfish above.
    if check_devpanel_collision "$CURSOR_TARGET_DIR"; then
        gate_devpanel_agents "$CURSOR_TARGET_DIR" "$cursor_source_dir/agents"
    else
        print_warning "devpanel: skipped Cursor role-agents deploy due to collision (see above)"
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

# Union repo-shipped RUNTIME settings (configs/claude/settings.runtime.json)
# into ~/.claude/settings.json — the file Claude Code actually reads at user
# scope. Covers hooks, permissions.allow and top-level scalar defaults
# (skillListingBudgetFraction). NOT mcpServers: measured, settings.json does not
# read that key at all — those are registered with `claude mcp add --scope user`
# by install_claude_mcp_servers below.
#
# Measured 2026-07-26 on Claude Code 2.1.220: a hook registered in
# ~/.claude/settings.local.json never fires. Controlled A/B, same hook and same
# absolute command with only the file differing — settings.json fired on every
# dispatch, settings.local.json fired zero times; an absolute path in
# settings.local.json also never fired, ruling out tilde expansion. A second
# A/B on a different event (PostToolUse:Write) reproduced it, establishing the
# defect as FILE-level rather than event- or matcher-specific. Every Claude hook
# Manifest ships therefore lives in settings.hooks.json and lands here.
#
# Creates the target if absent, expands `~` to an absolute command (the shipped
# settings.json hooks use absolute paths), and is idempotent + additive: an
# entry the user already has is never duplicated and nothing is removed.
# Fail-open like its siblings — a missing python3 is a skip, not a stop.
# Register repo-shipped MCP servers with Claude Code's OWN store.
#
# Measured 2026-07-27 (Claude Code 2.1.220): an `mcpServers` block is read from
# ~/.claude.json but NOT from ~/.claude/settings.json, and not at all from
# ~/.claude/settings.local.json where Manifest used to ship it. So sentry,
# context7, linear and atlassian have never been available on a deployed
# machine. `claude mcp add --scope user` is the supported interface and writes
# ~/.claude.json, verified by `claude mcp list` picking the entry up.
#
# Idempotent (skips a name already registered) and USER-WINS (never overwrites
# or removes an existing server of the same name). Fail-open: no `claude` on
# PATH, or a single failed add, is a warning and not a stop.
install_claude_mcp_servers() {
    local src="$1" legacy="${2:-}"
    [[ -f "$src" ]] || return 0
    # Unlike every other deploy step, this one writes OUTSIDE $TARGET_DIR:
    # `claude mcp add --scope user` writes $HOME/.claude.json. It does respect
    # HOME (verified), but a caller that redirects TARGET_DIR into a sandbox and
    # leaves HOME alone — which is exactly what several deploy tests do — would
    # otherwise mutate the developer's real MCP config. Only act when the deploy
    # target actually lives under this HOME.
    case "$TARGET_DIR" in
        "$HOME"/*) ;;
        *)
            print_info "MCP registration skipped (deploy target outside \$HOME)"
            return 0
            ;;
    esac
    if ! command_exists claude || ! command_exists python3; then
        print_info "claude CLI or python3 unavailable — skipped MCP server registration"
        return 0
    fi

    # The plan is generated into a TEMP FILE rather than piped from a process
    # substitution wrapping a heredoc. That construct works standalone but
    # misbehaves once deploy.sh is sourced by bootstrap: the heredoc body stops
    # being treated as quoted, bash brace-expands `{**a, **b}` inside the Python,
    # and the parser dies with a SyntaxError while the caller sees zero rows and
    # cheerfully reports "already registered". Same hazard as sourcing a function
    # containing a heredoc through a process-substitution FIFO. A temp file has
    # no such edge.
    local plan
    plan="$(mktemp)" || return 0
    # shellcheck disable=SC2064 # expand $plan now, not at trap time
    trap "rm -f '$plan'" RETURN

    MCP_SRC="$src" MCP_LEGACY="$legacy" MCP_HOME="$HOME/.claude.json" \
        python3 "$SCRIPT_DIR/configs/claude/scripts/mcp_plan.py" > "$plan" 2> /dev/null || {
        print_warning "Could not read MCP server definitions — skipped registration"
        return 0
    }

    local added=0 skipped=0 failed=0 name kind spec
    while IFS=$'\t' read -r name kind spec; do
        [[ -n "$name" ]] || continue
        if [[ "$kind" == "present" ]]; then
            skipped=$((skipped + 1))
            continue
        fi
        # shellcheck disable=SC2086 # spec is a deliberately word-split argv
        if [[ "$kind" == "http" ]]; then
            claude mcp add --scope user --transport http "$name" "$spec" > /dev/null 2>&1 &&
                added=$((added + 1)) || failed=$((failed + 1))
        else
            claude mcp add --scope user "$name" -- $spec > /dev/null 2>&1 &&
                added=$((added + 1)) || failed=$((failed + 1))
        fi
    done < "$plan"

    if ((failed > 0)); then
        print_warning "MCP servers: $added added, $skipped already present, $failed failed"
    elif ((added > 0)); then
        print_success "MCP servers: $added added, $skipped already present"
    else
        print_info "MCP servers already registered - preserved"
    fi
}

merge_claude_runtime_settings() {
    local src="$1" tgt="$2"
    [[ -f "$src" ]] || return 0
    if ! command_exists python3; then
        print_info "python3 unavailable — skipped runtime settings merge into settings.json"
        return 0
    fi
    local rc=0
    python3 - "$src" "$tgt" << 'PYEOF' || rc=$?
import json, os, sys

src_path, tgt_path = sys.argv[1], sys.argv[2]
try:
    src = json.load(open(src_path))
except (OSError, ValueError):
    sys.exit(4)
try:
    with open(tgt_path) as fh:
        tgt = json.load(fh)
except FileNotFoundError:
    tgt = {}
except (OSError, ValueError):
    sys.exit(4)
if not isinstance(tgt, dict):
    sys.exit(4)

changed = False

# permissions.allow: union, order-stable, never removes a user's own rule.
src_allow = ((src.get("permissions") or {}).get("allow")) or []
if src_allow:
    tgt_perms = tgt.setdefault("permissions", {})
    tgt_allow = tgt_perms.setdefault("allow", [])
    for rule in src_allow:
        if rule not in tgt_allow:
            tgt_allow.append(rule)
            changed = True

# Top-level scalar defaults: USER-WINS. A key the user already set is never
# overwritten; only genuinely absent keys are seeded.
for key, value in src.items():
    if key in ("hooks", "permissions", "_comment"):
        continue
    if key not in tgt:
        tgt[key] = value
        changed = True

for event, entries in (src.get("hooks") or {}).items():
    cur = tgt.setdefault("hooks", {}).setdefault(event, [])
    for entry in entries:
        resolved = json.loads(json.dumps(entry))
        for hook in resolved.get("hooks", []):
            cmd = hook.get("command", "")
            if cmd.startswith("~"):
                hook["command"] = os.path.expanduser(cmd)
        # Compare on the resolved form so a re-run never appends a second copy.
        if resolved not in cur:
            cur.append(resolved)
            changed = True

if changed:
    with open(tgt_path, "w") as fh:
        json.dump(tgt, fh, indent=2)
        fh.write("\n")
sys.exit(0 if changed else 3)
PYEOF
    case $rc in
        0) print_success "Merged Manifest runtime settings into settings.json" ;;
        3) print_info "settings.json already has Manifest runtime settings - preserved" ;;
        *) print_warning "Could not merge runtime settings into settings.json (manual merge may be needed)" ;;
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
    # T3.8 (spec 674): keyed on plugins/, not .apm/skills. The skills moved to
    # plugins/<bundle>/skills/ and .apm/skills is now a GITIGNORED generated
    # mirror, so HEAD:.apm/skills holds only the two root files and the dirty
    # check can never see a skill edit. Left alone, the "your deployed config
    # is stale, re-run bootstrap" nudge would never fire again.
    tree_skills="$(git -C "$repo_root" rev-parse HEAD:plugins 2> /dev/null)" || return 0
    head_sha="$(git -C "$repo_root" rev-parse HEAD 2> /dev/null)" || return 0
    if [[ -n "$(git -C "$repo_root" status --porcelain -- configs plugins 2> /dev/null)" ]]; then
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
# DEPRECATED as of T051/FR-034 — now a one-way migration shim, not a mechanism.
#
# This function exists because the issue-hook opt-in used to be written into the
# DEPLOYED command_config.yml: state stored inside a build output, which every
# deploy is free to overwrite, so the deploy had to carry it back across. That
# was compensating for the write being in the wrong place.
#
# install_issue_hooks.sh now writes ~/.manifest/issue_hooks.yml, a file no
# package owns, and nothing needs carrying. This is kept only so users who
# opted in the old way do not silently lose it on their next deploy. Once such
# opt-ins can be assumed migrated (a re-run of `install_issue_hooks.sh --enable`
# moves one), delete this function and its two call sites — do not extend it.
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
#
# Unlike deploy_gemini_configs/deploy_codex_configs, this function also does
# NOT copy a standalone home guide (no GEMINI.md/AGENTS.md analog deployed
# under ~/.antigravity). Verified live (G14, agy-batchD-groundtruth.md): the
# `agy` CLI reads its config from ~/.gemini/config (agy is Gemini-CLI
# lineage), never from ~/.antigravity, so a guide file placed there would
# simply never be read by the CLI. The Antigravity IDE's bundled Claude-Code
# extension already reads ~/.claude/CLAUDE.md natively, and agy ships its own
# builtin `antigravity_guide` skill for in-context reference. By-design
# omission — do not "fix" by deploying a guide agy cannot read.
#
# Bound-probed live (2026-07-11): `agy --print` with a prompt asking it to
# quote its context file's first heading verbatim returned the exact text of
# the Manifest-deployed ~/.gemini/GEMINI.md ("# Gemini Orchestration Guide"),
# confirming agy inherits that file as context — closing the open question
# noted in G14. So agy already receives Manifest orchestration guidance via
# the Gemini home when ENABLE_GEMINI is true; it just has no dedicated
# ~/.antigravity guide of its own (caveat: a claude+agy-only install with
# gemini disabled gives agy no home guide context at all — inherent to it
# being config-driven, not a gap this deploy step can close).
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

# Deploy Devin CLI configuration.
#
# Deliberately NOT a mirror of the Cursor/Gemini/Codex/Antigravity trees: the
# Devin CLI already discovers Manifest's deployed Claude home on its own.
# Measured against devin 3000.2.17 (2026-07-29):
#   - `devin skills list` lists every ~/.claude/skills/<name>/SKILL.md as
#     /claude:<name>, and returns ZERO of them once config.json sets
#     read_config_from.claude=false. That key — not a copy of the files — is
#     what the integration hangs on, so it is the one key deploy pins.
#   - Copying the skills into ~/.config/devin/skills does not add a skill; it
#     registers every skill a SECOND time (/devin:<name> beside /claude:<name>),
#     halving the signal density of the listing. Hence agent_roster.yml's
#     `devin.skills_sync: false` and no skills/ link here.
#   - Rules work the same way (`devin rules list` reads ~/.claude/CLAUDE.md),
#     so no duplicate global AGENTS.md is deployed either.
#
# config.json is merged user-wins, never overwritten: it is the user's own file
# (models, permissions, MCP servers, proxy). An explicit `claude: false` is
# reported, not silently flipped — the user's stated intent wins over ours.
deploy_devin_config() {
    if [[ "${ENABLE_DEVIN:-false}" != true ]]; then
        print_info "Devin disabled — skipping config deployment"
        return 0
    fi

    print_step "Deploying Devin CLI configuration..."
    mkdir -p "$DEVIN_TARGET_DIR"

    local cfg="$DEVIN_TARGET_DIR/config.json"

    if ! command_exists python3; then
        print_info "python3 unavailable — skipped $cfg inheritance pin"
        return 0
    fi

    local rc=0
    python3 - "$cfg" << 'PYEOF' || rc=$?
import json
import sys

cfg_path = sys.argv[1]
try:
    with open(cfg_path) as f:
        cfg = json.load(f)
except FileNotFoundError:
    cfg = {}
except Exception:
    sys.exit(2)  # present but unreadable/invalid — never clobber it
if not isinstance(cfg, dict):
    sys.exit(2)

sources = cfg.get("read_config_from")
if not isinstance(sources, dict):
    sources = {}

if sources.get("claude") is False:
    sys.exit(4)  # explicit user opt-out — reported, not overridden
if sources.get("claude") is True:
    sys.exit(3)  # already pinned

sources["claude"] = True
cfg["read_config_from"] = sources
with open(cfg_path, "w") as f:
    json.dump(cfg, f, indent=2)
    f.write("\n")
sys.exit(0)
PYEOF

    case $rc in
        0) print_success "Devin CLI configured to read ~/.claude (skills + rules) — $cfg" ;;
        3) print_info "Devin CLI already reads ~/.claude - preserved" ;;
        4)
            print_warning "Devin config.json sets read_config_from.claude=false — Manifest skills will NOT load"
            print_info "Set it to true in $cfg to inherit ~/.claude/skills"
            ;;
        *) print_warning "Could not update $cfg (manual edit may be needed)" ;;
    esac
    return 0
}

# NOTE: sync_skillshare_targets was removed 2026-07-27 (FR-021a). skillshare is
# deprecated; skills now live in .apm/skills as the sole source of truth. This
# also retires the project-scoped Copilot sync (.github/skills) that skillshare
# owned — a real capability loss, recorded rather than glossed. Home deploy was
# unaffected at the time: deploy_home_skills owned ~/.claude/skills until
# SC-006 (2026-07-28) handed that domain to apm.

# Deploy sync-skills CLI to ~/.local/bin/ and ensure it is on PATH.
# Depends on SHELL_PROFILE_FILE being set by configure_shell_profile_state.
deploy_sync_skills() {
    print_step "Deploying sync-skills CLI..."
    # Creates ~/.local/bin, adds it to the profile once, and exports it for this
    # run (PATH Catch-22: the profile is not sourced until the next terminal, but
    # the user may run sync-skills right away).
    ensure_local_bin_on_path
    cp "$SCRIPT_DIR/configs/claude/scripts/sync-skills.sh" "$HOME/.local/bin/sync-skills"
    chmod +x "$HOME/.local/bin/sync-skills"

    # apm-dev-sync was retired by spec 674 Phase 5 (T5.4) with its subject:
    # skills ship as plugin bundles, so there is nothing for it to sync.
    # A stale copy on PATH is worse than none -- it would run and report
    # success against a tree nothing reads any more.
    rm -f "$HOME/.local/bin/apm-dev-sync"

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

# populate_apm_owned_skills() was deleted here by spec 674 Phase 5 (T5.3).
# Its premise was that apm owns ~/.claude/skills and bootstrap must never
# leave that tree empty. Post-cutover EMPTY IS THE GOAL: the nine plugin
# bundles serve the catalog and the flat harness tree lives at
# $MANIFEST_SKILLS_DIR. Restoring it would refill ~/.claude/skills and
# double-load all 108 skills against their plugin twins.

# register_manifest_marketplace — point Claude Code at this checkout's plugin
# marketplace (T4.1, spec 674).
#
# A DIRECTORY source, not a git URL. Verified working: part-forge is configured
# exactly this way, with real version dirs in the cache. It is the mitigation
# for the measured dev-loop regression -- one `apm-dev-sync` with zero restarts
# becomes up to 9 `claude plugin update` calls plus a marketplace update and one
# session restart per iteration. A directory source removes publish and tag from
# that loop, though not the copy, the update, or the restart.
#
# NON-FATAL by design: a contributor without the claude CLI, or who declines
# plugins entirely, must still get a working bootstrap. This registers the
# marketplace; it deliberately does NOT install anything -- installing is
# cutover_bundle.sh's job, and it has preconditions this function has no
# business asserting.
register_manifest_marketplace() {
    local repo_root="$1"
    [[ -f "$repo_root/.claude-plugin/marketplace.json" ]] || return 0
    command_exists claude || {
        print_info "claude CLI not found — skipping marketplace registration"
        return 0
    }

    if claude plugin marketplace list 2> /dev/null | grep -q '\bmanifest\b'; then
        print_success "Marketplace already registered: manifest"
        return 0
    fi
    if claude plugin marketplace add "$repo_root" > /dev/null 2>&1; then
        print_success "Registered plugin marketplace: $repo_root"
    else
        # Not an error: the CLI may be too old, unauthenticated, or the user may
        # have removed it deliberately. Say so rather than failing the deploy.
        print_warning "Could not register the plugin marketplace (continuing)"
    fi
}

verify_installation() {
    print_header "Verifying Installation"

    local errors=0

    # Check deployed files
    print_step "Checking deployed files..."

    local required_files=(
        "$TARGET_DIR/scripts/parallel_agent.py"
        "$TARGET_DIR/scripts/git_platform.sh"
        "$TARGET_DIR/scripts/git_ops.sh"
        "$TARGET_DIR/config/command_config.yml"
        "$TARGET_DIR/config/mcp_servers.yml"
        "$TARGET_DIR/config/validation_criteria.yml"
        "$TARGET_DIR/config/services.yml"
        "$CURSOR_TARGET_DIR/rules/orchestration.mdc"
        "$CURSOR_TARGET_DIR/mcp.json"
        "$CURSOR_TARGET_DIR/hooks.json"
        "$GEMINI_TARGET_DIR/GEMINI.md"
        "$CODEX_TARGET_DIR/AGENTS.md"
    )

    # Skill files are verified SEPARATELY from required_files because bootstrap
    # is no longer necessarily their writer: SC-006 handed the `skills` domain to
    # apm (configs/claude/config/apm_domains.yml), so deploy_home_skills stands
    # down and these paths are populated by apm instead. Counting them as
    # bootstrap errors made a correctly-standing-down deploy exit 1 with three
    # "Missing: .cursor/skills/code-audit/SKILL.md" lines and no hint of who
    # should fix it — observed on a machine where apm had not yet run.
    #
    # The check is NOT skipped when apm owns the domain: a home with no skills is
    # genuinely broken for the user, and a check that quietly stops looking is how
    # this would go unnoticed next time. It degrades to a warning that names the
    # populate command, which is visible without blaming the wrong pipeline.
    local -a skill_files=(
        "$CURSOR_TARGET_DIR/skills/code-audit/SKILL.md"
        "$GEMINI_TARGET_DIR/skills/code-audit/SKILL.md"
        "$CODEX_TARGET_DIR/skills/code-audit/SKILL.md"
    )

    # Guarded (unlike the sibling entries above): deploy_configs skips copying
    # CLAUDE.md when Claude is disabled (see claude_md_exclude above), so
    # checking this file unconditionally would false-positive "Missing" on a
    # deliberately-disabled service.
    if [[ "${ENABLE_CLAUDE:-true}" == true ]]; then
        required_files+=("$TARGET_DIR/CLAUDE.md")
    fi

    # Guarded (unlike the sibling entries above): deploy_antigravity_configs
    # early-returns without creating anything when Antigravity is disabled, so
    # checking this file unconditionally would false-positive "Missing" on a
    # deliberately-disabled service.
    if [[ "$ENABLE_ANTIGRAVITY" == true ]]; then
        skill_files+=("$ANTIGRAVITY_TARGET_DIR/skills/code-audit/SKILL.md")
    fi
    # Devin deploys exactly one file (the read_config_from pin) — it inherits
    # skills/rules from ~/.claude rather than receiving a copy, so there is no
    # skills/<name>/SKILL.md of its own to assert.
    if [[ "${ENABLE_DEVIN:-false}" == true ]]; then
        required_files+=("$DEVIN_TARGET_DIR/config.json")
    fi

    for file in "${required_files[@]}"; do
        if [[ -f "$file" ]]; then
            print_success "Found: ${file#"$HOME"/}"
        else
            print_error "Missing: ${file#"$HOME"/}"
            errors=$((errors + 1))
        fi
    done

    local skills_apm_owned=false
    if declare -f apm_owns_domain > /dev/null 2>&1 && apm_owns_domain skills; then
        skills_apm_owned=true
    fi
    # RETIRED is the third state, and it inverts the verdict below. T1.7 made an
    # empty apm-owned tree a hard error in Phase 1, before `retired:` existed.
    # After the Phase 4 cutover an EMPTY ~/.claude/skills is the goal — the
    # bundles serve the catalog — so leaving T1.7's check unconditional would
    # print "Missing" 108 times and fail verification on every correct
    # post-cutover machine, which is the false RED this cutover keeps producing
    # in the mirror image of the false green T1.7 removed.
    local skills_retired=false
    if declare -f domain_retired > /dev/null 2>&1 && domain_retired skills; then
        skills_retired=true
    fi
    local skills_missing=0
    for file in "${skill_files[@]}"; do
        if [[ -f "$file" ]]; then
            print_success "Found: ${file#"$HOME"/}"
        elif [[ "$skills_retired" == true ]]; then
            : # expected: the plugin bundles serve this catalog now
        elif [[ "$skills_apm_owned" == true ]]; then
            print_warning "Missing (apm-owned domain): ${file#"$HOME"/}"
            skills_missing=$((skills_missing + 1))
        else
            print_error "Missing: ${file#"$HOME"/}"
            errors=$((errors + 1))
        fi
    done
    if [[ $skills_missing -gt 0 ]]; then
        # T1.7 (spec 674): a HARD error, not a warning. This branch means the
        # user has no skills at all — the domain is gated to apm and apm has not
        # populated it — yet without incrementing `errors` the function returns
        # 0 and bootstrap prints "Deployment verified". A total skills failure
        # that exits 0 is the exact false-green the cutover's gates exist to
        # remove; verifying a deployment must not pass when the deployment is
        # empty, however legitimate the reason the writer stood down.
        print_error "apm owns the 'skills' domain but has not populated it ($skills_missing missing) — run: ${APM_DOMAIN_REPLACEMENT_CMD:-apm-dev-sync}"
        errors=$((errors + 1))
    fi

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
        "$MANIFEST_STATE_DIR/antigravity"
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

    if [[ "$ENABLE_ANTIGRAVITY" == true ]]; then
        enabled_count=$((enabled_count + 1))
        if command_exists agy; then
            print_success "agy is available (enabled)"
            available_tools=$((available_tools + 1))
        else
            print_warning "agy is not available (enabled but not installed)"
        fi
    else
        print_info "antigravity is disabled"
    fi

    if [[ "${ENABLE_DEVIN:-false}" == true ]]; then
        enabled_count=$((enabled_count + 1))
        if command_exists devin; then
            print_success "devin is available (enabled)"
            available_tools=$((available_tools + 1))
        else
            print_warning "devin is not available (enabled but not installed)"
        fi
    else
        print_info "devin is disabled"
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

    # T4.4 (spec 674): verify the CLAUDE side, which nothing else does.
    #
    # Before this, verify_installation canaried exactly one file under the skills
    # tree and asserted NOTHING about ~/.claude/plugins. A user who ran
    # ./bootstrap.sh and never ran `claude plugin install` got "Installation
    # verified" with zero Manifest skills in Claude Code.
    #
    # SELF-DISABLING on purpose. It only runs once the cutover has actually
    # started -- i.e. installed_plugins.json already names at least one manifest-*
    # bundle. Checking unconditionally would report a shortfall on a correct
    # PRE-cutover machine, which is the same "permanently red gate" failure this
    # plan flags in T1.11; a gate that is always red is a gate nobody reads.
    local installed_json="$TARGET_DIR/plugins/installed_plugins.json"
    if [[ -r "$installed_json" ]] && grep -q '"manifest-' "$installed_json" 2> /dev/null; then
        local registry="$TARGET_DIR/config/skill_policies.yml"
        if [[ -r "$registry" ]]; then
            print_step "Checking installed Manifest bundles..."
            local bundle
            while IFS= read -r bundle; do
                [[ -n "$bundle" ]] || continue
                if grep -q "\"$bundle@" "$installed_json" 2> /dev/null; then
                    print_success "Bundle installed: $bundle"
                else
                    print_error "Bundle NOT installed: $bundle — run: claude plugin install $bundle@manifest"
                    errors=$((errors + 1))
                fi
            done < <(sed -n 's/^  \([a-z][a-z0-9-]*\):.*$/\1/p' "$registry")
        fi
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

# Warn when a disabled service still has a previously deployed managed config
# in its home target (#549). When a service is disabled, bootstrap skips
# deploying its configs, so any earlier copy is left in place and silently
# goes stale. Detection is presence-based (deployed copy exists while disabled),
# not content/mtime analysis; this function is warning-only and never deletes,
# moves, or modifies any file. Bash 3.2 compatible (no associative arrays).
warn_stale_disabled_configs() {
    # Each entry: <service>|<enabled-flag>|<deployed managed-config path>
    local entries=(
        "claude|${ENABLE_CLAUDE:-true}|$TARGET_DIR/CLAUDE.md"
        "gemini|${ENABLE_GEMINI:-true}|$GEMINI_TARGET_DIR/GEMINI.md"
        "cursor|${ENABLE_CURSOR:-true}|$CURSOR_TARGET_DIR/rules"
        "codex|${ENABLE_CODEX:-true}|$CODEX_TARGET_DIR/AGENTS.md"
        "antigravity|${ENABLE_ANTIGRAVITY:-true}|$ANTIGRAVITY_TARGET_DIR/config"
        "devin|${ENABLE_DEVIN:-false}|$DEVIN_TARGET_DIR/config.json"
    )
    local entry service enabled path rest
    for entry in "${entries[@]}"; do
        service="${entry%%|*}"
        rest="${entry#*|}"
        enabled="${rest%%|*}"
        path="${rest#*|}"
        # -e follows symlinks; -L also catches a dangling deployed symlink.
        if [[ "$enabled" != true ]] && { [[ -e "$path" ]] || [[ -L "$path" ]]; }; then
            print_warning "$service disabled — deployed config left in place and will go stale: $path"
        fi
    done
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
    if [[ "$ENABLE_ANTIGRAVITY" == true ]]; then
        echo "  Antigravity Config: $ANTIGRAVITY_TARGET_DIR"
    fi
    if [[ "${ENABLE_DEVIN:-false}" == true ]]; then
        echo "  Devin Config:   $DEVIN_TARGET_DIR"
    fi
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

    if [[ "${ENABLE_DEVIN:-false}" == true ]]; then
        if command -v devin > /dev/null 2>&1; then
            echo -e "  ${GREEN}✓${NC} devin CLI installed"
        else
            echo -e "  ${YELLOW}○${NC} devin CLI not found — parallel-agent participation needs it"
            echo -e "    ${BLUE}→${NC} Install: brew install --cask devin-cli"
        fi
    else
        echo -e "  ${YELLOW}○${NC} devin (disabled)"
    fi
    echo ""

    # Flag any disabled service whose deployed config is still present (#549).
    warn_stale_disabled_configs

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
    if [[ "$ENABLE_ANTIGRAVITY" == true ]]; then
        echo -e "    Antigravity: ${CYAN}agy${NC}  (launch the CLI/IDE to sign in — no separate login subcommand)"
    fi
    if [[ "${ENABLE_DEVIN:-false}" == true ]]; then
        echo -e "    Devin:   ${CYAN}devin auth login${NC}"
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
    # No "Antigravity guide:" line by design (G14/G22): the agy CLI reads
    # config from ~/.gemini/config, not ~/.antigravity, so a guide dropped
    # there would never be read — see deploy_antigravity_configs() above for
    # the full rationale.
    echo "  Config:         ~/.claude/config/"
    echo ""
}
