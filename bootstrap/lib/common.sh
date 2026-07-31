#!/bin/bash

# Shared helpers for bootstrap.sh. This file is sourced, not executed.

# Skill-prune policy lives in its own module: common.sh hit its 600-line
# constitution ceiling, and "which deployed dirs should go" is a distinct
# responsibility from "copy the tree".
# shellcheck source=bootstrap/lib/skill_prune.sh
source "$(dirname "${BASH_SOURCE[0]}")/skill_prune.sh"

print_header() {
    echo ""
    echo -e "${BOLD}${BLUE}══════════════════════════════════════════════════════════════${NC}"
    echo -e "${BOLD}${BLUE}  $1${NC}"
    echo -e "${BOLD}${BLUE}══════════════════════════════════════════════════════════════${NC}"
    echo ""
}

print_step() {
    echo -e "${CYAN}→${NC} $1"
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_info() {
    echo -e "${BLUE}ℹ${NC} $1"
}

prompt_yes_no() {
    local question="$1"
    local default="${2:-y}"
    local prompt_suffix
    local response

    if [[ "$default" == "y" ]]; then
        prompt_suffix="[Y/n]"
    else
        prompt_suffix="[y/N]"
    fi

    echo -ne "${BOLD}${question}${NC} ${CYAN}${prompt_suffix}${NC}: "
    read -r response
    response="${response:-$default}"

    [[ "$response" =~ ^[Yy]([Ee][Ss])?$ ]]
}

command_exists() {
    command -v "$1" &> /dev/null
}

# Create/recreate a symlink at link_path pointing to target
create_symlink() {
    local link_path="$1"
    local target="$2"
    local label="$3"

    if [[ ! -e "$target" ]]; then
        print_warning "Symlink target not found: $target (skipping $label)"
        return 0
    fi

    # A real (non-symlink) path here is user content — back it up instead of
    # silently destroying it with rm -rf (issue #321)
    if [[ -e "$link_path" && ! -L "$link_path" ]]; then
        local backup
        backup="${link_path}.backup.$(date +%Y%m%d_%H%M%S)"
        print_warning "$link_path exists as a real path — backing up to $backup"
        mv "$link_path" "$backup"
    else
        rm -rf "$link_path"
    fi
    ln -sf "$target" "$link_path"
    print_success "Symlinked $link_path -> $target"
}

# Link shared directories from ~/.claude into another config directory.
# Third arg `include_skills=true` also links the shared skills directory.
link_shared_assets() {
    local destination_dir="$1"
    local shared_name="${2:-Config}"
    local include_skills="${3:-false}"
    # Space-separated asset names to skip for this tool (default: none). Lets a
    # tool opt out of assets it must not carry — e.g. Antigravity excludes
    # "scripts prompts" because agy is a parallel_agent provider, not an
    # orchestrator that runs parallel_agent.py.
    local exclude="${4:-}"

    local symlinks=(
        "scripts:$TARGET_DIR/scripts"
        "config:$TARGET_DIR/config"
        "prompts:$TARGET_DIR/prompts"
        ".plans:$TARGET_DIR/.plans"
    )
    if [[ "$include_skills" == "true" ]]; then
        symlinks+=("skills:$TARGET_DIR/skills")
    fi

    local entry
    for entry in "${symlinks[@]}"; do
        local name="${entry%%:*}"
        local target="${entry#*:}"
        # Skip assets this tool opted out of (whole-word match on the list).
        [[ " $exclude " == *" $name "* ]] && continue
        local link_path="$destination_dir/$name"
        create_symlink "$link_path" "$target" "${shared_name} $name"
    done
}

# Make ~/.local/bin usable for the CLIs bootstrap installs there (sync-skills,
# apm-dev-sync, manifest): create it, add it to the user's profile once, and put it
# on PATH for the rest of this run (the profile is not sourced until the next
# shell, but the user may run the CLI immediately).
#
# Shared because every installer that drops a binary there needs it — a
# --reconfigure run installs the manifest wrapper without going through
# deploy_configs, which is where this logic used to live exclusively.
ensure_local_bin_on_path() {
    mkdir -p "$HOME/.local/bin" 2> /dev/null || true

    local profile="${SHELL_PROFILE_FILE:-}"
    if [[ -n "$profile" ]] && ! grep -Eq '\.local/bin' "$profile" 2> /dev/null; then
        {
            echo ""
            echo "# User-installed tools (managed by bootstrap.sh)"
            # Single-quoted intentionally: $HOME/$PATH must stay literal so they
            # expand in the user's shell at profile-load time, not here.
            # shellcheck disable=SC2016
            echo 'export PATH="$HOME/.local/bin:$PATH"'
        } >> "$profile"
    fi

    # Idempotent: repeated calls must not stack duplicate entries onto PATH.
    case ":$PATH:" in
        *":$HOME/.local/bin:"*) ;;
        *) export PATH="$HOME/.local/bin:$PATH" ;;
    esac
}

# Ownership registry helper. Sourced from configs/claude/scripts/ because
# sync-skills.sh — a standalone CLI in ~/.local/bin — needs the same function and
# cannot source the bootstrap libraries. One implementation, two callers.
# shellcheck disable=SC1090,SC1091
if [[ -n "${SCRIPT_DIR:-}" && -f "$SCRIPT_DIR/configs/claude/scripts/apm_domains_lib.sh" ]]; then
    source "$SCRIPT_DIR/configs/claude/scripts/apm_domains_lib.sh"
elif [[ -f "${BASH_SOURCE[0]%/*}/../../configs/claude/scripts/apm_domains_lib.sh" ]]; then
    source "${BASH_SOURCE[0]%/*}/../../configs/claude/scripts/apm_domains_lib.sh"
fi

# Deploy skills into a tool's real skills dir from the PHYSICAL source tree.
# Always sources the real .apm/skills dir (never the compat symlink).
# Manifest-scoped prune (FR-005a, specs/003): skills we previously deployed and
# that have since been removed from the source of truth are pruned from dest,
# but ~/.claude/skills can legitimately hold skills installed by other
# tools/plugins — those are never in the manifest and are never touched.
deploy_home_skills() {
    local src="$1"
    local dest="$2"
    # T014/FR-027: stand down for a domain APM owns, and keep deploying the
    # rest. Per-domain, never a global off-switch — the domain name defaults to
    # the destination's basename ("skills") so callers need no new argument.
    local domain="${3:-$(basename "$dest")}"
    # T011/FR-019: an explicit per-domain selection skips everything else, so an
    # unmigrated domain can be redeployed without touching a migrated one.
    if declare -f deploy_domain_selected > /dev/null 2>&1 && ! deploy_domain_selected "$domain"; then
        print_info "Skipping $domain — not in MANIFEST_DEPLOY_DOMAINS"
        return 0
    fi
    # T2.2 (spec 674). RETIRED means owned by neither pipeline. Checked BEFORE
    # the apm branch: a retired domain is not apm's either, and falling through
    # to the two-state logic would read "unlisted" as "the legacy writer writes",
    # refill the tree, and double-load every skill against its plugin twin.
    if declare -f domain_retired > /dev/null 2>&1 && domain_retired "$domain"; then
        print_info "Skipping $domain — retired from both pipelines; plugins own it now (claude plugin update <bundle>)"
        return 0
    fi
    if declare -f apm_owns_domain > /dev/null 2>&1 && apm_owns_domain "$domain"; then
        print_info "Skipping $domain — APM owns this domain (deploy it with $APM_DOMAIN_REPLACEMENT_CMD)"
        return 0
    fi

    if [[ ! -d "$src" ]]; then
        print_error "Skill source not found: $src"
        return 1
    fi

    # Guard: a top-level directory under $src with no SKILL.md is not a skill.
    # A skill rename can leave the old-name directory behind on disk even
    # though `git status` shows nothing for it, because it still holds only
    # git-ignored content (e.g. a stray scripts/__pycache__/*.pyc) — ignored
    # files never show as untracked, so nothing flags it there. rsync/cp copy
    # the FILESYSTEM, not the git tree, so such a directory would otherwise
    # deploy as a phantom skill and break repo<->home parity (observed:
    # `.apm/skills/<old-name>` deployed as an extra 108th "skill").
    # Warn loudly rather than silently skip — a silent skip would just as
    # easily hide a genuinely malformed real skill — and exclude it from the
    # deploy so this class of drift can't recur.
    local -a bogus_names=()
    local d name
    for d in "$src"/*/; do
        [[ -d "$d" ]] || continue
        name="$(basename "$d")"
        [[ "$name" == .* ]] && continue
        if [[ ! -f "${d}SKILL.md" ]]; then
            bogus_names+=("$name")
            print_warning "Not deploying $src/$name — no SKILL.md found (not a skill; check for rename debris)"
        fi
    done

    # If dest is a stray symlink (e.g. from an older install that copied the
    # compat symlink), drop it so we deploy into a real directory, not its target.
    [[ -L "$dest" ]] && rm -f "$dest"
    mkdir -p "$dest"
    # Copy the skill tree. Prefer rsync; fall back to cp so a minimal host without
    # rsync (some slim Linux images) still deploys skills instead of silently
    # no-op'ing / hard-failing under set -e. `cp -R src/. dest/` copies CONTENTS
    # into dest and preserves symlinks-as-symlinks, matching `rsync -a src/ dest/`
    # for our merge-then-prune model (the prune step below handles removals).
    if command -v rsync > /dev/null 2>&1; then
        rsync -a "$src"/ "$dest"/
    else
        cp -R "$src"/. "$dest"/
    fi

    # Remove any non-skill directories the copy above just brought over (see
    # the SKILL.md guard above) so they never land in dest.
    local bn
    for bn in ${bogus_names[@]+"${bogus_names[@]}"}; do
        rm -rf "${dest:?}/${bn}"
    done

    # Prune previously-deployed skills now absent from the source.
    # Safety bounds: (a) an empty source (failed checkout / wrong path that
    # still exists) must never mass-prune dest — require >=1 source skill;
    # (b) manifest entries are validated as plain single-level names so a
    # corrupted manifest can never drive rm -rf outside dest.
    local manifest="$dest/.deployed-skills"
    local src_count
    src_count=$(find "$src" -mindepth 1 -maxdepth 1 -type d ! -name '.*' | wc -l | tr -d ' ')
    src_count=$((src_count - ${#bogus_names[@]}))
    prune_removed_skills "$src" "$dest" "$src_count"
    # Atomic manifest write: a failed subshell must not truncate the previous
    # manifest (that would silently disable future pruning). Bogus (non-skill)
    # directories are filtered out so they can never become a manifest entry.
    if (cd "$src" && find . -mindepth 1 -maxdepth 1 -type d ! -name '.*' |
        LC_ALL=C sort | sed 's|^\./||') > "$manifest.tmp"; then
        if [[ "${#bogus_names[@]}" -gt 0 ]]; then
            grep -vFxf <(printf '%s\n' "${bogus_names[@]}") "$manifest.tmp" > "$manifest.tmp2" || true # array-safe (length-guarded above)
            mv "$manifest.tmp2" "$manifest.tmp"
        fi
        mv "$manifest.tmp" "$manifest"
    else
        rm -f "$manifest.tmp"
    fi

    print_success "Deployed skills: $src -> $dest"
}

# Gate the /graphify skill in a deployed skills dir based on ENABLE_GRAPHIFY, and
# reconcile collisions with a foreign upstream 'graphify install' (FR-010 / FR-012).
# Call right after deploy_home_skills for the home (~/.claude) skills dir; assistant
# skill dirs symlink to it, so gating the home copy clears all targets.
gate_graphify_skill() {
    local home_skills="$1"
    local skill="$home_skills/graphify"

    if [[ "${ENABLE_GRAPHIFY:-true}" == false ]]; then
        # Clean opt-out: remove the deployed skill (the .apm/skills source stays in the
        # repo). Defensively prune any independent (non-symlink) graphify dir under the
        # assistant skill targets in case a future target stops symlinking to home.
        if [[ -e "$skill" || -L "$skill" ]]; then
            rm -rf "${home_skills:?}/graphify"
            print_info "graphify disabled - removed deployed /graphify skill"
        fi
        local d target
        for d in "$CURSOR_TARGET_DIR" "$GEMINI_TARGET_DIR" "$CODEX_TARGET_DIR" "$ANTIGRAVITY_TARGET_DIR"; do
            target="$d/skills"
            [[ -L "$target" || ! -d "$target" ]] && continue # symlink to home is already cleared
            [[ -e "$target/graphify" ]] && rm -rf "${target:?}/graphify"
        done
        return 0
    fi

    # Enabled: surface and reconcile a collision with a prior 'graphify install'. That
    # installer ships a references/ sidecar and a .graphify_version marker our thin
    # wrapper never includes; rsync -a (no --delete) leaves them behind, so their
    # presence after deploy means a foreign skill was clobbered. Surface it and
    # reconcile to the Manifest-managed wrapper rather than leaving a hybrid skill.
    if [[ -d "$skill/references" || -e "$skill/.graphify_version" ]]; then
        print_warning "Existing 'graphify install' skill detected at $skill — Manifest now manages /graphify; reconciling to the deployed wrapper."
        rm -rf "$skill/references" "$skill/.graphify_version"
    fi
}

# ---------------------------------------------------------------------------
# pilotfish cost-tiered role-agents (opt-in via --enable-pilotfish; Claude-only).
#
# configs/claude/agents/ is EXCLUDED from the wholesale rsync (deploy.sh) so a
# disabled or foreign ~/.claude/agents is never copied over — the gate is the sole
# deployer of the six role files and the .pilotfish ownership marker (it writes the
# marker itself; a shipped marker would falsely read as "Manifest-owned" after a
# disabled deploy). references/pilotfish-delegation.md still lands via rsync (unique
# name, no collision risk) and is pruned on disable. When on, the gate copies the six
# agents, stamps the marker, and injects the one-line delegation pointer into the
# deployed CLAUDE.md; when off it manifest-scoped-prunes exactly its own artifacts.
# settings.json is never touched (spec FR-016).
# ---------------------------------------------------------------------------

# The one delegation-policy pointer line added to the deployed CLAUDE.md Reference
# Index when enabled. Kept out of the committed source guide so its always-loaded
# byte budget is unaffected when pilotfish is off (FR-009/FR-014).
# Single-quoted intentionally: this is a literal markdown line with no shell
# expansion wanted (the backtick-wrapped path is doc text, not a command sub).
# shellcheck disable=SC2016
PILOTFISH_POINTER_LINE='- `~/.claude/references/pilotfish-delegation.md` — pilotfish cost-tiered delegation (role→alias, selective-verify).'

# The exact set of agent files Manifest deploys. The disable path removes ONLY these
# (plus the marker), never the whole agents dir, so a user-authored agent that
# coexists in ~/.claude/agents survives an opt-out (manifest-scoped prune, like
# deploy_home_skills). Keep in sync with configs/claude/agents/*.md.
PILOTFISH_AGENT_FILES=(scout.md Explore.md mech-executor.md executor.md verifier.md security-executor.md context-chronicler.md compatibility-translator.md dependency-guardian.md)

# Pre-deploy collision guard (spec FR-008). Called BEFORE any destructive copy: if
# pilotfish is enabled and ~/.claude/agents exists but is NOT Manifest-owned (no
# .pilotfish marker), abort ONLY when one of the six role files we would deploy is
# already present — overwriting a user's same-named agent is the real hazard. A
# differently-named user agent is no collision and must NOT block enabling (else a
# disable that left a coexisting user agent behind would deadlock the next enable).
# Returns 1 to abort, 0 when safe. No-op when pilotfish is disabled.
check_pilotfish_collision() {
    local home="$1"
    local agents="$home/agents"
    [[ "${ENABLE_PILOTFISH:-false}" == false ]] && return 0
    [[ -d "$agents" && ! -f "$agents/.pilotfish" ]] || return 0
    local a
    for a in ${PILOTFISH_AGENT_FILES[@]+"${PILOTFISH_AGENT_FILES[@]}"}; do
        if [[ -e "$agents/$a" ]]; then
            print_error "pilotfish: $agents/$a already exists and is not Manifest-owned; refusing to overwrite. Move or remove it, then re-run (nothing was changed)."
            return 1
        fi
    done
    return 0
}

# Post-copy gate (called next to gate_graphify_skill). Prune the pilotfish artifacts
# when the toggle is off (removing exactly them, SC-003); when on, deploy the six
# role files + the delegation reference from source (both rsync-excluded), stamp the
# owner marker, and inject the delegation pointer. Idempotent across both rsync paths.
#   $1 home        — deploy target home (e.g. ~/.claude)
#   $2 src_agents  — source agents dir (configs/claude/agents); used only when enabled
gate_pilotfish_agents() {
    local home="$1"
    local src_agents="${2:-}"
    local agents="$home/agents"
    local ref="$home/references/pilotfish-delegation.md"
    local guide="$home/CLAUDE.md"
    # The delegation reference is a sibling of the agents dir under configs/claude/;
    # like agents/ it is rsync-excluded and deployed here so a disabled/foreign run
    # never lands it (no copy-then-delete churn on default bootstraps).
    local src_ref=""
    [[ -n "$src_agents" ]] && src_ref="$(dirname "$src_agents")/references/pilotfish-delegation.md"

    if [[ "${ENABLE_PILOTFISH:-false}" == false ]]; then
        # Opt-out: remove exactly the deployed pilotfish artifacts and NOTHING else.
        # Manifest-scoped prune (mirrors deploy_home_skills): delete only our six role
        # files + the marker, then rmdir the agents dir ONLY if it is now empty — a
        # user-authored agent coexisting in ~/.claude/agents survives (SC-003).
        if [[ -f "$agents/.pilotfish" ]]; then
            local a
            for a in ${PILOTFISH_AGENT_FILES[@]+"${PILOTFISH_AGENT_FILES[@]}"}; do
                rm -f "$agents/$a"
            done
            rm -f "$agents/.pilotfish"
            rmdir "$agents" 2> /dev/null || true # only succeeds when empty; user agents survive
            print_info "pilotfish disabled - removed deployed role-agents"
        fi
        [[ -f "$ref" ]] && rm -f "$ref"
        remove_pilotfish_pointer "$guide"
        return 0
    fi

    # Enabled: agents/ is rsync-excluded, so deploy the six role files here. The
    # collision guard (check_pilotfish_collision, pre-rsync) already ensured no
    # non-Manifest same-named file will be overwritten. Idempotent: cp overwrites our
    # own files, the marker is re-stamped, and the pointer inject is grep-guarded — so
    # an enabled re-run reconverges to the same tree rather than skipping (it is a
    # no-op in effect, NOT a bypass of the enable path).
    mkdir -p "$agents"
    if [[ -n "$src_agents" && -d "$src_agents" ]]; then
        local f
        for f in ${PILOTFISH_AGENT_FILES[@]+"${PILOTFISH_AGENT_FILES[@]}"}; do
            [[ -f "$src_agents/$f" ]] && cp "$src_agents/$f" "$agents/$f"
        done
    fi
    if [[ -n "$src_ref" && -f "$src_ref" ]]; then
        mkdir -p "$home/references"
        cp "$src_ref" "$ref"
    fi
    : > "$agents/.pilotfish"
    inject_pilotfish_pointer "$guide"
    return 0
}

# Idempotently add PILOTFISH_POINTER_LINE to the deployed guide's Reference Index,
# anchored after the last shipped entry (antipatterns.md); falls back to the
# "## Reference Index" heading if that anchor is absent.
inject_pilotfish_pointer() {
    local guide="$1"
    [[ -f "$guide" ]] || return 0
    grep -qF 'pilotfish-delegation.md' "$guide" && return 0
    local tmp
    tmp="$(mktemp)" || return 0
    if grep -qF 'antipatterns.md' "$guide"; then
        awk -v ins="$PILOTFISH_POINTER_LINE" '
            { print }
            !done && /antipatterns\.md/ { print ins; done = 1 }
        ' "$guide" > "$tmp"
    else
        awk -v ins="$PILOTFISH_POINTER_LINE" '
            { print }
            !done && /^## Reference Index/ { print ""; print ins; done = 1 }
        ' "$guide" > "$tmp"
    fi
    if grep -qF 'pilotfish-delegation.md' "$tmp"; then
        mv "$tmp" "$guide"
    else
        rm -f "$tmp"
    fi
}

# Remove the pilotfish pointer line from the deployed guide (idempotent).
remove_pilotfish_pointer() {
    local guide="$1"
    [[ -f "$guide" ]] || return 0
    grep -qF 'pilotfish-delegation.md' "$guide" || return 0
    local tmp
    tmp="$(mktemp)" || return 0
    # A&&B||C is safe here: mv only fails if grep already failed (empty/missing
    # $tmp) or the guide path is unwritable, and either way rm -f "$tmp" is a
    # correct no-op/cleanup, not a masked error path.
    # shellcheck disable=SC2015
    grep -vF 'pilotfish-delegation.md' "$guide" > "$tmp" && mv "$tmp" "$guide" || rm -f "$tmp"
}

# ---------------------------------------------------------------------------
# devpanel critic-gated role-agents (opt-in via --enable-devpanel; Claude-only).
#
# A second, independent role-agent set: developer/debugger/tester (primaries)
# plus spec-guard/chaos-engineer (shared validators gating whichever primary
# ran). Deploys into the SAME ~/.claude/agents dir as pilotfish, on disjoint
# filenames — the two toggles are fully independent and may be enabled
# together. Mirrors gate_pilotfish_agents' mechanics exactly (own marker,
# own pointer, own manifest-scoped prune) rather than extending pilotfish's
# closed six-role set, which has its own contract (exactly six files).
# ---------------------------------------------------------------------------

# shellcheck disable=SC2016
DEVPANEL_POINTER_LINE='- `~/.claude/references/devpanel-delegation.md` — devpanel critic-gated dev/debug/test role agents (propose→critique→refactor loop).'

# The exact set of agent files Manifest deploys for devpanel. Keep in sync with
# configs/claude/agents-devpanel/*.md.
DEVPANEL_AGENT_FILES=(developer.md debugger.md tester.md spec-guard.md chaos-engineer.md performance-auditor.md)

# Pre-deploy collision guard, mirrors check_pilotfish_collision. Returns 1 to
# abort, 0 when safe. No-op when devpanel is disabled.
check_devpanel_collision() {
    local home="$1"
    local agents="$home/agents"
    [[ "${ENABLE_DEVPANEL:-false}" == false ]] && return 0
    [[ -d "$agents" && ! -f "$agents/.devpanel" ]] || return 0
    local a
    for a in ${DEVPANEL_AGENT_FILES[@]+"${DEVPANEL_AGENT_FILES[@]}"}; do
        if [[ -e "$agents/$a" ]]; then
            print_error "devpanel: $agents/$a already exists and is not Manifest-owned; refusing to overwrite. Move or remove it, then re-run (nothing was changed)."
            return 1
        fi
    done
    return 0
}

# Post-copy gate, mirrors gate_pilotfish_agents. Prune the devpanel artifacts
# when the toggle is off (removing exactly them); when on, deploy the five
# role files + the delegation reference from source, stamp the owner marker,
# and inject the delegation pointer. Idempotent across both rsync paths.
#   $1 home        — deploy target home (e.g. ~/.claude)
#   $2 src_agents  — source agents dir (configs/claude/agents-devpanel); used only when enabled
gate_devpanel_agents() {
    local home="$1"
    local src_agents="${2:-}"
    local agents="$home/agents"
    local ref="$home/references/devpanel-delegation.md"
    local guide="$home/CLAUDE.md"
    local src_ref=""
    [[ -n "$src_agents" ]] && src_ref="$(dirname "$src_agents")/references/devpanel-delegation.md"

    if [[ "${ENABLE_DEVPANEL:-false}" == false ]]; then
        # Opt-out: remove exactly the deployed devpanel artifacts and NOTHING
        # else — manifest-scoped prune, mirrors gate_pilotfish_agents. A
        # coexisting pilotfish deploy (or user-authored agent) in the same
        # dir survives; rmdir only succeeds when the dir is now empty.
        if [[ -f "$agents/.devpanel" ]]; then
            local a
            for a in ${DEVPANEL_AGENT_FILES[@]+"${DEVPANEL_AGENT_FILES[@]}"}; do
                rm -f "$agents/$a"
            done
            rm -f "$agents/.devpanel"
            rmdir "$agents" 2> /dev/null || true
            print_info "devpanel disabled - removed deployed role-agents"
        fi
        [[ -f "$ref" ]] && rm -f "$ref"
        remove_devpanel_pointer "$guide"
        return 0
    fi

    # Enabled: idempotent — cp overwrites our own files, the marker is
    # re-stamped, and the pointer inject is grep-guarded, so an enabled
    # re-run reconverges to the same tree rather than skipping.
    mkdir -p "$agents"
    if [[ -n "$src_agents" && -d "$src_agents" ]]; then
        local f
        for f in ${DEVPANEL_AGENT_FILES[@]+"${DEVPANEL_AGENT_FILES[@]}"}; do
            [[ -f "$src_agents/$f" ]] && cp "$src_agents/$f" "$agents/$f"
        done
    fi
    if [[ -n "$src_ref" && -f "$src_ref" ]]; then
        mkdir -p "$home/references"
        cp "$src_ref" "$ref"
    fi
    : > "$agents/.devpanel"
    inject_devpanel_pointer "$guide"
    return 0
}

# Idempotently add DEVPANEL_POINTER_LINE to the deployed guide's Reference
# Index, anchored after the pilotfish pointer when present (so enabling both
# toggles produces a stable, order-independent result), else after
# antipatterns.md, else the "## Reference Index" heading.
inject_devpanel_pointer() {
    local guide="$1"
    [[ -f "$guide" ]] || return 0
    grep -qF 'devpanel-delegation.md' "$guide" && return 0
    local tmp
    tmp="$(mktemp)" || return 0
    if grep -qF 'pilotfish-delegation.md' "$guide"; then
        awk -v ins="$DEVPANEL_POINTER_LINE" '
            { print }
            !done && /pilotfish-delegation\.md/ { print ins; done = 1 }
        ' "$guide" > "$tmp"
    elif grep -qF 'antipatterns.md' "$guide"; then
        awk -v ins="$DEVPANEL_POINTER_LINE" '
            { print }
            !done && /antipatterns\.md/ { print ins; done = 1 }
        ' "$guide" > "$tmp"
    else
        awk -v ins="$DEVPANEL_POINTER_LINE" '
            { print }
            !done && /^## Reference Index/ { print ""; print ins; done = 1 }
        ' "$guide" > "$tmp"
    fi
    if grep -qF 'devpanel-delegation.md' "$tmp"; then
        mv "$tmp" "$guide"
    else
        rm -f "$tmp"
    fi
}

# Remove the devpanel pointer line from the deployed guide (idempotent).
remove_devpanel_pointer() {
    local guide="$1"
    [[ -f "$guide" ]] || return 0
    grep -qF 'devpanel-delegation.md' "$guide" || return 0
    local tmp
    tmp="$(mktemp)" || return 0
    # shellcheck disable=SC2015
    grep -vF 'devpanel-delegation.md' "$guide" > "$tmp" && mv "$tmp" "$guide" || rm -f "$tmp"
}
