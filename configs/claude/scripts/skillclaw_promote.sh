#!/usr/bin/env bash
# skillclaw_promote.sh - Turn evolved SkillClaw skills into a review PR.
#
# Pipeline: idempotency check -> preflight -> scrub -> evolve -> classify ->
# verify -> stage branch (per-skill commits) -> git_ops pr-create.
# Dry-run by default; --apply required to branch/commit/PR. Never touches main
# directly, never force-pushes. Implements Option A: aborts if an open
# skillclaw/evolve-* PR already exists (override with --force-new).
#
# Usage: skillclaw_promote.sh [--apply] [--skill NAME] [--no-evolve] [--force-new]
#
# Env overrides (for tests): SKILLCLAW_EVOLVED, SKILLCLAW_COMMITTED,
#   SKILLCLAW_SESSIONS, SKILLCLAW_GITOPS, SKILLCLAW_OPEN_PR.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GITOPS="${SKILLCLAW_GITOPS:-${SCRIPT_DIR}/git_ops.sh}"
# shellcheck disable=SC2034  # CFG is a test/future-use seam; not used in this version
CFG="${SKILLCLAW_CONFIG:-${SCRIPT_DIR}/../config/skillclaw.yml}"

EVOLVED="${SKILLCLAW_EVOLVED:-$HOME/.skillclaw/skills}"
SESSIONS="${SKILLCLAW_SESSIONS:-$HOME/.skillclaw/sessions}"
# Committed library: the physical skillshare source of truth. The deployed script
# lives in ~/.claude/scripts, so locate the repo via MANIFEST_ROOT (exported by
# bootstrap into the shell profile); fall back to repo-relative when run in-tree.
COMMITTED="${SKILLCLAW_COMMITTED:-${MANIFEST_ROOT:-${SCRIPT_DIR}/../../..}/.skillshare/skills}"
BRANCH_PREFIX="skillclaw/evolve-"
PR_BASE="main"

APPLY=false; SKILL=""; DO_EVOLVE=true; FORCE_NEW=false

err() { echo "skillclaw-promote: $*" >&2; }
usage_error() { err "$*"; exit 2; }

while [[ $# -gt 0 ]]; do
    case "$1" in
        --apply) APPLY=true; shift ;;
        --skill) [[ $# -ge 2 ]] || usage_error "--skill needs a name"; SKILL="$2"; shift 2 ;;
        --no-evolve) DO_EVOLVE=false; shift ;;
        --force-new) FORCE_NEW=true; shift ;;
        -*) usage_error "unknown flag: $1" ;;
        *) usage_error "unexpected argument: $1" ;;
    esac
done

# 0. Idempotency (Option A): one open evolve PR at a time.
open_pr() {
    if [[ -n "${SKILLCLAW_OPEN_PR:-}" ]]; then
        echo "$SKILLCLAW_OPEN_PR"; return 0
    fi
    "$GITOPS" pr-list --search "head:${BRANCH_PREFIX}" --state open 2>/dev/null \
        | grep -Eo 'https?://[^ ]+' | head -1 || true
}
if [[ "$APPLY" == true && "$FORCE_NEW" == false ]]; then
    existing="$(open_pr)"
    if [[ -n "$existing" ]]; then
        err "an open evolve PR already exists: $existing"
        err "review/merge it first, or pass --force-new"
        exit 1
    fi
fi

# 1. Scrub captured sessions (best-effort; never blocks).
if [[ -d "$SESSIONS" ]]; then
    python3 "${SCRIPT_DIR}/skillclaw_scrub.py" "$SESSIONS" >/dev/null 2>&1 || true
fi

# 2. Evolve (skip with --no-evolve; e.g. tests / re-run on existing library).
if [[ "$DO_EVOLVE" == true ]]; then
    if command -v skillclaw >/dev/null 2>&1; then
        skillclaw evolve --mode workflow >/dev/null 2>&1 || err "evolve returned non-zero (continuing)"
    fi
fi

# 3. Classify + validate.
classify_args=("$EVOLVED" "$COMMITTED")
[[ -n "$SKILL" ]] && classify_args+=(--skill "$SKILL")
classify_json="$(python3 "${SCRIPT_DIR}/skillclaw_promote.py" "${classify_args[@]}")"

# Print the human diff table.
echo "Evolved skill candidates:"
echo "$classify_json" | python3 -c '
import json,sys
d=json.load(sys.stdin)
for c in d["promote"]:
    status=c["status"]; name=c["name"]
    print("  %-9s %s" % (status, name))
for c in d["dropped"]:
    name=c["name"]; reason=c["reason"]
    print("  DROPPED   %s  (%s)" % (name, reason))
'

promote_names="$(echo "$classify_json" | python3 -c 'import json,sys; print(" ".join(c["name"] for c in json.load(sys.stdin)["promote"]))')"

if [[ -z "$promote_names" ]]; then
    echo "Nothing to promote."
    exit 0
fi

if [[ "$APPLY" != true ]]; then
    echo ""
    echo "Dry run — re-run with --apply to open a review PR."
    exit 0
fi

# 4. Stage a branch with one commit per skill, then open a PR.
count="$(echo "$promote_names" | wc -w | tr -d ' ')"
if [[ ! -d "$COMMITTED" ]]; then
    err "committed skills dir not found: $COMMITTED"
    err "set MANIFEST_ROOT (or SKILLCLAW_COMMITTED) to the repo's .skillshare/skills"
    exit 2
fi
branch="${BRANCH_PREFIX}${count}-$(git rev-parse --short HEAD)"
git switch -c "$branch"

for name in $promote_names; do
    dest="${COMMITTED}/${name}"
    mkdir -p "$dest"
    cp "${EVOLVED}/${name}/SKILL.md" "${dest}/SKILL.md"
    git add "${dest}/SKILL.md"
    git commit -m "skill(${name}): evolve via SkillClaw" >/dev/null
done

body="$(printf 'Auto-evolved by SkillClaw. Skills: %s\n\nProvenance: %s\nReview each commit independently; drop a skill by reverting its commit.' \
    "$promote_names" "$SESSIONS")"

pr_url="$("$GITOPS" pr-create --base "$PR_BASE" --head "$branch" \
    --title "SkillClaw: evolve ${count} skill(s)" --body "$body" \
    --label needs-review --label follow-up)"

echo "Opened review PR: $pr_url"
