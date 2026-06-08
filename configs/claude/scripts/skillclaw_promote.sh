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
#   SKILLCLAW_SESSIONS, SKILLCLAW_GITOPS, SKILLCLAW_OPEN_PR, SKILLCLAW_TRANSCRIPTS,
#   SKILLCLAW_STATE, SKILLCLAW_REJECTED, SKILLCLAW_TEMPLATE.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GITOPS="${SKILLCLAW_GITOPS:-${SCRIPT_DIR}/git_ops.sh}"
# shellcheck disable=SC2034  # CFG is a test/future-use seam; not used in this version
CFG="${SKILLCLAW_CONFIG:-${SCRIPT_DIR}/../config/skillclaw.yml}"

EVOLVED="${SKILLCLAW_EVOLVED:-$HOME/.skillclaw/skills}"
SESSIONS="${SKILLCLAW_SESSIONS:-$HOME/.skillclaw/sessions}"
INGEST="${SCRIPT_DIR}/skillclaw_ingest.py"
EVOLVE="${SCRIPT_DIR}/skillclaw_evolve.py"
TEMPLATE="${SKILLCLAW_TEMPLATE:-${SCRIPT_DIR}/../prompts/skillclaw_evolve.md}"
TRANSCRIPTS="${SKILLCLAW_TRANSCRIPTS:-$HOME/.claude/projects}"
STATE="${SKILLCLAW_STATE:-$HOME/.skillclaw/.ingest-state.json}"
REJECTED="${SKILLCLAW_REJECTED:-$HOME/.skillclaw/skills/rejected}"
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

# 1. Ingest transcripts → sessions (passive; no proxy).
if [[ "$DO_EVOLVE" == true ]]; then
    python3 "$INGEST" "$TRANSCRIPTS" "$SESSIONS" --state "$STATE" >/dev/null 2>&1 \
        || err "ingest returned non-zero (continuing)"
fi

# 2. Scrub captured sessions (best-effort; never blocks).
if [[ -d "$SESSIONS" ]]; then
    python3 "${SCRIPT_DIR}/skillclaw_scrub.py" "$SESSIONS" >/dev/null 2>&1 || true
fi

# 3. Evolve (skip with --no-evolve). Suppress its stdout summary (kept clean like
# ingest); errors still surface on stderr and are reported below.
if [[ "$DO_EVOLVE" == true ]]; then
    python3 "$EVOLVE" "$SESSIONS" "$EVOLVED" --template "$TEMPLATE" >/dev/null \
        || err "evolve returned non-zero (continuing)"
fi

# 4. Classify + validate. A crash here (empty/non-JSON output) must fail loudly,
# not abort cryptically under `set -e`, so guard the capture explicitly.
classify_args=("$EVOLVED" "$COMMITTED" --rejected-dir "$REJECTED")
[[ -n "$SKILL" ]] && classify_args+=(--skill "$SKILL")
classify_json="$(python3 "${SCRIPT_DIR}/skillclaw_promote.py" "${classify_args[@]}")" \
    || { err "classify failed (skillclaw_promote.py returned non-zero)"; exit 1; }

# Print the human diff table. The .get() defaults keep this resilient if the
# JSON ever lacks a key rather than aborting the pipeline.
echo "Evolved skill candidates:"
echo "$classify_json" | python3 -c '
import json,sys
d=json.load(sys.stdin)
for c in d.get("promote", []):
    status=c["status"]; name=c["name"]
    print("  %-9s %s" % (status, name))
for c in d.get("dropped", []):
    name=c["name"]; reason=c["reason"]
    print("  DROPPED   %s  (%s)" % (name, reason))
'

dropped_count="$(echo "$classify_json" | python3 -c 'import json,sys; print(len(json.load(sys.stdin).get("dropped", [])))')"
if [[ "$dropped_count" -gt 0 ]]; then
    err "Generated candidate(s), but ${dropped_count} failed schema validation. See ${REJECTED}"
fi

promote_names="$(echo "$classify_json" | python3 -c 'import json,sys; print(" ".join(c["name"] for c in json.load(sys.stdin).get("promote", [])))')"

if [[ -z "$promote_names" ]]; then
    echo "Nothing to promote."
    exit 0
fi

if [[ "$APPLY" != true ]]; then
    echo ""
    echo "Dry run — re-run with --apply to open a review PR."
    exit 0
fi

# 5. Stage a branch with one commit per skill, then open a PR.
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
