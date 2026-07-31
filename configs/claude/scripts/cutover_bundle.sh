#!/usr/bin/env bash
# cutover_bundle.sh — install ONE bundle, then delete exactly that bundle's
# user-dir skill copies (T4.2, spec 674).
#
# Per-bundle on purpose: a single bad bundle must never strand the user with a
# half-emptied ~/.claude/skills and nothing installed. Each invocation is
# independently reversible from the Phase 0 tarball.
#
# WHAT THIS DELIBERATELY DOES NOT USE
#
#   ~/.claude/skills/.deployed-skills — measured WRONG on a live machine
#   (mtime predates SC-006; code-audit-constitution on disk and unlisted). Two
#   designs keyed the retire step on it; that would have left a live user-dir
#   copy double-loading against its plugin twin, over budget, with a green
#   deploy. The delete list comes from skill_policies.yml's `bundle:` field.
#
#   skillOverrides — `off` makes the bare name a hard Unknown command, the
#   overrides are read from user/project/local settings so `claude plugin
#   uninstall` does NOT clear them, and the write target is the file whose
#   read-modify-write race already lost this user's `model` key once.
#
# ⚠️ DEVIN: emptying ~/.claude/skills is what breaks Devin's native
# `read_config_from.claude` inheritance. Phase 2 froze that tree but left it
# populated, so Devin was safe until now. This script REFUSES unless Devin is
# either verified or explicitly waived, because that verification was bypassed.
set -euo pipefail

err() { printf 'cutover_bundle.sh: %s\n' "$*" >&2; }

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    cat << 'USAGE'
Usage: cutover_bundle.sh <bundle> [--dry-run] [--allow-unverified-devin]

Install one bundle from the Manifest marketplace, then remove exactly that
bundle's skill directories from ~/.claude/skills.

  --dry-run                  report what would be installed/removed; change nothing
  --allow-unverified-devin   proceed while Devin's inheritance is unverified
  --help                     this text
USAGE
    exit 0
fi

BUNDLE=""
DRY_RUN=0
ALLOW_DEVIN=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run) DRY_RUN=1 ;;
        --allow-unverified-devin) ALLOW_DEVIN=1 ;;
        -*)
            err "unknown argument: $1 (try --help)"
            exit 2
            ;;
        *) BUNDLE="$1" ;;
    esac
    shift
done
[[ -n "$BUNDLE" ]] || {
    err "a bundle name is required (try --help)"
    exit 2
}

STATE_DIR="${MANIFEST_STATE_DIR:-$HOME/.manifest}"
SKILLS_DIR="${MANIFEST_SKILLS_DIR:-$STATE_DIR/skills}"
CLAUDE_SKILLS="$HOME/.claude/skills"
REGISTRY="${MANIFEST_SKILL_REGISTRY:-$HOME/.claude/config/skill_policies.yml}"

# Foreign entries that are NOT Manifest's and must survive untouched. `.system`
# is Codex's; a `claude plugin init <name>` scaffold auto-loads as
# <name>@skills-dir and is the user's own work.
ALLOWLIST_RE='^(\.system|\.metadata\.json|README\.md|\.deployed-skills)$'

# --- preconditions ---------------------------------------------------------

# 1. Devin. Asked FIRST: it is the cheapest check and it answers 'should this
#    run at all', settled before any state is inspected. This is the exposure
#    the Phase 0 bypass accepted — see the header.
if [[ "$ALLOW_DEVIN" -ne 1 ]]; then
    if ! devin models list > /dev/null 2>&1; then
        err "Devin is not logged in, so its inheritance was never verified by observation."
        err "Emptying ~/.claude/skills is what breaks its read_config_from.claude path."
        err "Run: devin auth login && configs/claude/scripts/probe_devin_inheritance.sh"
        err "Or pass --allow-unverified-devin to accept the risk explicitly."
        exit 3
    fi
fi

# 2. The rollback must exist and verify BEFORE anything is deleted. Every
#    rollback the four input designs proposed is circular (they call
#    apm_ungate_domain.sh or apm-dev-sync, both retired by this cutover), so the
#    tarball is the only one that survives.
snapshot="$(find "$STATE_DIR" -maxdepth 1 -name 'pre-cutover-*.tgz' 2> /dev/null | sort | tail -1)"
if [[ -z "$snapshot" ]]; then
    err "no Phase 0 snapshot under $STATE_DIR — run cutover_snapshot.sh first"
    exit 3
fi
if ! "$(dirname "${BASH_SOURCE[0]}")/cutover_snapshot.sh" --verify > /dev/null 2>&1; then
    err "the snapshot does not verify — refusing to delete anything"
    exit 3
fi

# 3. Every sibling home must already resolve into the harness root with a
#    READABLE canary. Content, not -f: a dangling symlink passes an existence
#    test and then silently serves nothing.
for home_dir in "$HOME/.cursor" "$HOME/.gemini" "$HOME/.codex" "$HOME/.antigravity"; do
    link="$home_dir/skills"
    target="$(readlink "$link" 2> /dev/null || true)"
    case "$target" in
        "$SKILLS_DIR") ;;
        *)
            err "$link does not resolve into $SKILLS_DIR (got: ${target:-<not a symlink>})"
            err "run ./bootstrap.sh first — Phase 2 must be complete before Phase 4"
            exit 3
            ;;
    esac
    [[ -s "$link/code-audit/SKILL.md" ]] || {
        err "canary unreadable through $link — the harness tree is not serving content"
        exit 3
    }
done


# --- the delete list -------------------------------------------------------

[[ -r "$REGISTRY" ]] || {
    err "registry not readable: $REGISTRY"
    exit 3
}

# Names assigned to THIS bundle, straight from the registry.
BUNDLE_SKILLS=()
in_bundle=0
while IFS= read -r line; do
    stripped="${line%%#*}"
    stripped="${stripped%"${stripped##*[![:space:]]}"}"
    case "$stripped" in
        "  $BUNDLE:") in_bundle=1 ;;
        "    - "*) [[ "$in_bundle" -eq 1 ]] && BUNDLE_SKILLS+=("${stripped#    - }") ;;
        "  "*":") in_bundle=0 ;;
    esac
done < "$REGISTRY"

if [[ ${#BUNDLE_SKILLS[@]} -eq 0 ]]; then
    err "no skills assigned to bundle '$BUNDLE' in $REGISTRY"
    exit 3
fi
printf 'cutover_bundle.sh: %s owns %s skill(s)\n' "$BUNDLE" "${#BUNDLE_SKILLS[@]}"

if [[ "$DRY_RUN" -eq 1 ]]; then
    printf '  would install : %s@manifest\n' "$BUNDLE"
    for s in ${BUNDLE_SKILLS[@]+"${BUNDLE_SKILLS[@]}"}; do
        [[ -d "$CLAUDE_SKILLS/$s" ]] && printf '  would remove  : ~/.claude/skills/%s\n' "$s"
    done
    exit 0
fi

# --- install, then delete --------------------------------------------------

if ! claude plugin install "$BUNDLE@manifest"; then
    err "install failed for $BUNDLE@manifest — nothing was deleted"
    exit 4
fi

for s in ${BUNDLE_SKILLS[@]+"${BUNDLE_SKILLS[@]}"}; do
    [[ -d "$CLAUDE_SKILLS/$s" ]] || continue
    rm -rf "${CLAUDE_SKILLS:?}/${s:?}"
    printf '  removed ~/.claude/skills/%s\n' "$s"
done

# --- postcondition, as an ASSERTION not a warning --------------------------
#
# The design this replaces printed a warning and exited 0 for anything left
# standing. A survivor double-loads against its plugin twin with no error
# message and silently consumes listing budget, so residue must fail.
survivors=()
while IFS= read -r d; do
    name="$(basename "$d")"
    [[ "$name" =~ $ALLOWLIST_RE ]] && continue
    for s in ${BUNDLE_SKILLS[@]+"${BUNDLE_SKILLS[@]}"}; do
        [[ "$name" == "$s" ]] && survivors+=("$name")
    done
done < <(find "$CLAUDE_SKILLS" -mindepth 1 -maxdepth 1 -type d 2> /dev/null)

if [[ ${#survivors[@]} -gt 0 ]]; then
    err "these ${BUNDLE} skills survived the delete and will double-load:"
    for s in ${survivors[@]+"${survivors[@]}"}; do err "    $s"; done
    exit 5
fi

printf 'cutover_bundle.sh: %s installed; %s user-dir copies removed; no residue\n' \
    "$BUNDLE" "${#BUNDLE_SKILLS[@]}"
