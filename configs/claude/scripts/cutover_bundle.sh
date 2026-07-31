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
# DEVIN: emptying ~/.claude/skills is what breaks Devin's native
# `read_config_from.claude` inheritance. Phase 2 froze that tree but left it
# populated, so Devin was safe until now.
#
# That was SETTLED BY OBSERVATION on 2026-07-30, and it needed no login --
# `devin skills list` reads local config and makes no API call:
#
#   * Devin lists all 108 skills with the source `(~/.claude/skills/<name>)`,
#     confirming the inheritance rather than inferring it from config.json.
#   * A nonce planted in ~/.manifest/skills was INVISIBLE (0 hits) until
#     ~/.config/devin/skills existed, and visible (1 hit) with it. So Devin
#     follows a SYMLINKED skills dir -- the open question in T2.6, whose only
#     measured fact was about a COPY.
#   * With both trees live, Devin registered 231 skills: 108 from
#     ~/.claude/skills, 108 from ~/.manifest/skills, 14 project-scoped. The
#     double-registration is real and measured, which is why the link is created
#     HERE and not in Phase 2.
#
# The gate therefore checks the thing that matters -- can Devin still reach a
# skills tree after this delete -- instead of `devin models list`, which tests
# AUTHENTICATION and would refuse on a machine where inheritance is perfectly
# fine.
set -euo pipefail

err() { printf 'cutover_bundle.sh: %s\n' "$*" >&2; }

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    cat << 'USAGE'
Usage: cutover_bundle.sh <bundle> [--dry-run] [--allow-unverified-devin]

Install one bundle from the Manifest marketplace, then remove exactly that
bundle's skill directories from ~/.claude/skills.

  --dry-run                  report what would be installed/removed; change nothing
  --allow-unverified-devin   skip the Devin inheritance check entirely
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
# Overridable so the tests cannot reach the real machine. They do not override
# HOME, and the first version of this gate created a REAL ~/.config/devin/skills
# pointing into a sandbox that teardown then deleted -- a dangling link on the
# user's machine, left by a suite that reported 7/8 green. This repo's own rule
# (T5.6) is to diff apm/plugin state around any suite that touches it.
DEVIN_SKILLS_LINK="${DEVIN_SKILLS_LINK:-$HOME/.config/devin/skills}"

# Foreign entries that are NOT Manifest's and must survive untouched. `.system`
# is Codex's; a `claude plugin init <name>` scaffold auto-loads as
# <name>@skills-dir and is the user's own work.
ALLOWLIST_RE='^(\.system|\.metadata\.json|README\.md|\.deployed-skills)$'

# A refusal, routed by mode. In a real run the first unmet precondition stops
# everything, which is the fail-closed behaviour this tool exists for. In
# --dry-run it is REPORTED and the walk continues: a preview whose whole job is
# "tell me what would happen" is useless if it exits at the first thing that
# would stop it -- and requiring a verified rollback tarball before you may even
# LOOK inverts the natural order of preview, decide, snapshot, run.
GATE_BLOCKED=0
gate_fail() {
    if [[ "$DRY_RUN" -eq 1 ]]; then
        GATE_BLOCKED=1
        printf '  WOULD BLOCK   : %s\n' "$1" >&2
        shift
        local line
        for line in "$@"; do printf '                  %s\n' "$line" >&2; done
        return 0
    fi
    err "$@"
    exit 3
}

# --- preconditions ---------------------------------------------------------

# 1. Devin. Asked FIRST: it is the cheapest check and it answers 'should this
#    run at all', settled before any state is inspected.
#
#    Not `devin models list` — that tests authentication, and a logged-out
#    Devin whose ~/.config/devin/skills resolves correctly is FINE. What must
#    hold is that Devin can still reach a skills tree once this delete empties
#    the one it inherits.
if [[ "$ALLOW_DEVIN" -ne 1 ]] && command -v devin > /dev/null 2>&1; then
    devin_link="$DEVIN_SKILLS_LINK"
    if [[ "$(readlink "$devin_link" 2> /dev/null || true)" != "$SKILLS_DIR" ]]; then
        if [[ -e "$devin_link" && ! -L "$devin_link" ]]; then
            gate_fail "$devin_link exists and is not a symlink — Devin serves its own skills there." \
                "Resolve by hand, or pass --allow-unverified-devin to proceed regardless."
        fi
        # Additive and reversible: one symlink. Created here rather than in
        # Phase 2 because until this script runs, BOTH trees are populated and
        # Devin would register every skill twice (measured: 231).
        if [[ "$DRY_RUN" -eq 1 ]]; then
            printf '  would link    : %s -> %s\n' "$devin_link" "$SKILLS_DIR"
        else
            mkdir -p "$(dirname "$devin_link")"
            ln -sfn "$SKILLS_DIR" "$devin_link"
            printf 'cutover_bundle.sh: linked %s -> %s\n' "$devin_link" "$SKILLS_DIR"
        fi
    fi
    # Verify by observation, not by the symlink's existence. `devin skills list`
    # reads local config and makes no API call, so this works logged out.
    #
    # Matched against BOTH forms: devin prints `~/.manifest/skills/<name>`, so
    # grepping only the absolute path refused on a machine whose link was
    # already correct -- a false red of exactly the kind this cutover keeps
    # producing. Found by running the tool, not by the unit tests, which pass a
    # stub that echoes whatever the test chose.
    devin_seen=0
    if [[ "$DRY_RUN" -eq 1 && ! -e "$devin_link" ]]; then
        # Reported, not silently passed: the preview genuinely cannot observe a
        # link it declined to create, and "no WOULD BLOCK line" must not be
        # readable as "Devin is verified".
        printf '  UNVERIFIABLE  : Devin — cannot observe until the link above exists\n' >&2
        devin_seen=1
    else
        # Captured, NOT piped into grep. Two reasons, both measured against the
        # real binary:
        #
        #   * `grep -q` exits on the first match and closes the pipe. devin then
        #     dies of SIGPIPE (141), and `set -o pipefail` turns a SUCCESSFUL
        #     match into a failed pipeline -- so the gate refused on a machine
        #     where Devin could see all 107 skills. The stub in the tests is a
        #     one-line echo that finishes before grep exits, so the suite never
        #     saw it.
        #   * devin prints the tilde form (`~/.manifest/skills/<name>`), so the
        #     absolute path alone does not match. Both forms are accepted; the
        #     slashes need no escaping, they are not special in ERE.
        devin_out="$(devin skills list 2> /dev/null || true)"
        if printf '%s' "$devin_out" |
            grep -qE "($SKILLS_DIR|~${SKILLS_DIR#"$HOME"})"; then
            devin_seen=1
        fi
    fi
    if [[ "$devin_seen" -ne 1 ]]; then
        gate_fail "Devin does not report any skill from $SKILLS_DIR." \
            "Emptying ~/.claude/skills would leave it with no catalog at all." \
            "Pass --allow-unverified-devin to accept that explicitly."
    fi
fi

# 2. The rollback must exist and verify BEFORE anything is deleted. Every
#    rollback the four input designs proposed is circular (they call
#    apm_ungate_domain.sh or apm-dev-sync, both retired by this cutover), so the
#    tarball is the only one that survives.
snapshot="$(find "$STATE_DIR" -maxdepth 1 -name 'pre-cutover-*.tgz' 2> /dev/null | sort | tail -1)"
if [[ -z "$snapshot" ]]; then
    gate_fail "no Phase 0 snapshot under $STATE_DIR — run cutover_snapshot.sh first"
elif ! "$(dirname "${BASH_SOURCE[0]}")/cutover_snapshot.sh" --verify > /dev/null 2>&1; then
    gate_fail "the snapshot does not verify — refusing to delete anything"
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
            gate_fail "$link does not resolve into $SKILLS_DIR (got: ${target:-<not a symlink>})" \
                "run ./bootstrap.sh first — Phase 2 must be complete before Phase 4"
            ;;
    esac
    [[ -s "$link/code-audit/SKILL.md" ]] ||
        gate_fail "canary unreadable through $link — the harness tree is not serving content"
done


# --- the delete list -------------------------------------------------------

[[ -r "$REGISTRY" ]] || gate_fail "registry not readable: $REGISTRY"

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

# 4. Nothing outside the skills tree may still POINT INTO it. Hooks are the
#    case the plan missed entirely: ~/.claude/settings.json and
#    ~/.gemini/settings.json each ran a PreToolUse hook out of
#    ~/.claude/skills/ai-hooks-integration/, so deleting that skill killed every
#    Bash tool call in the session -- a total outage from a step whose own
#    postcondition reported "no residue". Checked BEFORE the delete, because
#    afterwards the tool that would fix it cannot run.
hook_refs=()
while IFS= read -r cfg; do
    [[ -f "$cfg" ]] || continue
    while IFS= read -r ref; do
        [[ -n "$ref" ]] && hook_refs+=("${cfg}|${ref}")
    done < <(grep -ohE "$CLAUDE_SKILLS/[A-Za-z0-9_./-]+" "$cfg" 2> /dev/null | sort -u)
done < <(printf '%s\n' "$HOME/.claude/settings.json" "$HOME/.claude/settings.local.json" \
    "$HOME/.gemini/settings.json" "$HOME/.codex/config.toml")

doomed=()
for entry in ${hook_refs[@]+"${hook_refs[@]}"}; do
    ref="${entry#*|}"
    # Only a reference to a skill THIS bundle removes is a problem here.
    for s in ${BUNDLE_SKILLS[@]+"${BUNDLE_SKILLS[@]}"}; do
        [[ "$ref" == "$CLAUDE_SKILLS/$s"* ]] && doomed+=("${entry%%|*} -> $ref")
    done
done
if [[ ${#doomed[@]} -gt 0 ]]; then
    # gate_fail, not a bare exit: a preview must be able to REPORT this. It is
    # the one precondition a user cannot discover any other way, and finding it
    # by running the real thing means finding it with the session already dead.
    gate_fail "these config files reference a skill this bundle is about to delete:" \
        ${doomed[@]+"${doomed[@]}"} \
        "Repoint them at \$MANIFEST_SKILLS_DIR first — a hook that vanishes mid-session" \
        "blocks every tool call and cannot be fixed by the tool that broke it."
fi

if [[ "$DRY_RUN" -eq 1 ]]; then
    if [[ "$GATE_BLOCKED" -eq 1 ]]; then
        printf '  ---\n  %s WOULD NOT RUN: fix the WOULD BLOCK item(s) above.\n' "$BUNDLE"
    fi
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
