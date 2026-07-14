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
MANIFEST="${MANIFEST:-manifest}"
# shellcheck disable=SC2034  # CFG is a test/future-use seam; not used in this version
CFG="${SKILLCLAW_CONFIG:-${SCRIPT_DIR}/../config/skillclaw.yml}"

EVOLVED="${SKILLCLAW_EVOLVED:-$HOME/.skillclaw/skills}"
SESSIONS="${SKILLCLAW_SESSIONS:-$HOME/.skillclaw/sessions}"
TEMPLATE="${SKILLCLAW_TEMPLATE:-${SCRIPT_DIR}/../prompts/skillclaw_evolve.md}"
TRANSCRIPTS="${SKILLCLAW_TRANSCRIPTS:-$HOME/.claude/projects}"
STATE="${SKILLCLAW_STATE:-$HOME/.skillclaw/.ingest-state.json}"
REJECTED="${SKILLCLAW_REJECTED:-$HOME/.skillclaw/skills/rejected}"
# Committed library: the physical skillshare source of truth. The deployed script
# lives in ~/.claude/scripts, so locate the repo via MANIFEST_ROOT (exported by
# bootstrap into the shell profile); fall back to repo-relative when run in-tree.
COMMITTED="${SKILLCLAW_COMMITTED:-${MANIFEST_ROOT:-${SCRIPT_DIR}/../../..}/.skillshare/skills}"

# Shared audit storage; evolve.py reads SKILLCLAW_AUDIT_DIR too (default ~/.skillclaw).
export SKILLCLAW_AUDIT_DIR="${SKILLCLAW_AUDIT_DIR:-$HOME/.skillclaw}"
skillclaw_cmd() { "$MANIFEST" skillclaw "$@"; }
audit() { skillclaw_cmd audit "$@" > /dev/null 2>&1 || true; }

BRANCH_PREFIX="skillclaw/evolve-"
PR_BASE="main"

# Pipeline defaults — kept here so the audit log records the values the run
# actually used (ingest's --window-days and evolve's --token-budget), not zeros.
WINDOW_DAYS="${SKILLCLAW_WINDOW_DAYS:-30}"
TOKEN_BUDGET="${SKILLCLAW_TOKEN_BUDGET:-100000}"

APPLY=false
SKILL=""
DO_EVOLVE=true
FORCE_NEW=false

err() { if [[ -t 2 ]]; then printf '\033[0;31m%s\033[0m\n' "skillclaw-promote: $*" >&2; else printf '%s\n' "skillclaw-promote: $*" >&2; fi; }
usage_error() {
    err "$*"
    exit 2
}

usage() {
    cat << 'USAGE'
Usage: skillclaw_promote.sh [--apply] [--skill NAME] [--no-evolve]
                            [--force-new] [--status]

Turn evolved SkillClaw skills into a review PR. Dry-run by default.

  --apply       Branch, commit per skill, and open the review PR
  --skill NAME  Limit the run to a single evolved skill
  --no-evolve   Skip the evolve step (promote existing candidates only)
  --force-new   Proceed even if an open skillclaw/evolve-* PR exists
  --status      Print pipeline status from the audit log and exit
USAGE
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --help | -h)
            usage
            exit 0
            ;;
        --status)
            skillclaw_cmd audit status
            exit 0
            ;;
        --apply)
            APPLY=true
            shift
            ;;
        --skill)
            [[ $# -ge 2 ]] || usage_error "--skill needs a name"
            SKILL="$2"
            shift 2
            ;;
        --no-evolve)
            DO_EVOLVE=false
            shift
            ;;
        --force-new)
            FORCE_NEW=true
            shift
            ;;
        -*) usage_error "unknown flag: $1" ;;
        *) usage_error "unexpected argument: $1" ;;
    esac
done

run_id="$(date -u +%Y%m%dT%H%M%SZ)-$$"
RUN_DONE=false
CUR_STAGE="startup"
finalize() {
    local ec=$?
    if [[ "$RUN_DONE" != true ]]; then
        audit log "$run_id" "$CUR_STAGE" run_error message="exit ${ec}"
    fi
}
trap finalize EXIT
audit log "$run_id" "-" run_start window_days="$WINDOW_DAYS" token_budget="$TOKEN_BUDGET" apply="$APPLY"

# 0. Idempotency (Option A): one open evolve PR at a time.
open_pr() {
    if [[ -n "${SKILLCLAW_OPEN_PR:-}" ]]; then
        echo "$SKILLCLAW_OPEN_PR"
        return 0
    fi
    "$GITOPS" pr-list --search "head:${BRANCH_PREFIX}" --state open 2> /dev/null |
        grep -Eo 'https?://[^ ]+' | head -1 || true
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
    CUR_STAGE="ingest"
    _t0=$SECONDS
    echo "▸ ingest…"
    audit log "$run_id" ingest stage_start
    # Capture ingest's JSON summary (stdout) so stage_end carries the ingested
    # count → status.json totals.ingested is populated for --status/troubleshooting.
    ingest_json="$(skillclaw_cmd ingest "$TRANSCRIPTS" "$SESSIONS" --state "$STATE" \
        --window-days "$WINDOW_DAYS" 2> /dev/null)" ||
        err "ingest returned non-zero (continuing)"
    ingested_count="$(printf '%s' "$ingest_json" |
        python3 -c 'import json,sys; print(int(json.load(sys.stdin).get("ingested",0)))' \
            2> /dev/null || echo 0)"
    audit log "$run_id" ingest stage_end seconds=$((SECONDS - _t0)) ingested="$ingested_count"
fi

# 2. Scrub captured sessions (best-effort; never blocks).
if [[ -d "$SESSIONS" ]]; then
    CUR_STAGE="scrub"
    _t0=$SECONDS
    echo "▸ scrub…"
    audit log "$run_id" scrub stage_start
    skillclaw_cmd scrub "$SESSIONS" > /dev/null 2>&1 || true
    audit log "$run_id" scrub stage_end seconds=$((SECONDS - _t0))
fi

# 3. Evolve (skip with --no-evolve). evolve.py logs its own stage_start/chunk_done.
if [[ "$DO_EVOLVE" == true ]]; then
    CUR_STAGE="evolve"
    echo "▸ evolve…"
    skillclaw_cmd evolve "$SESSIONS" "$EVOLVED" --template "$TEMPLATE" \
        --committed-dir "$COMMITTED" --token-budget "$TOKEN_BUDGET" \
        --run-id "$run_id" > /dev/null ||
        err "evolve returned non-zero (continuing)"
fi

# 4. Classify + validate. A crash here (empty/non-JSON output) must fail loudly,
# not abort cryptically under `set -e`, so guard the capture explicitly.
CUR_STAGE="classify"
_t0=$SECONDS
echo "▸ classify…"
audit log "$run_id" classify stage_start
classify_args=("$EVOLVED" "$COMMITTED" --rejected-dir "$REJECTED")
[[ -n "$SKILL" ]] && classify_args+=(--skill "$SKILL")
classify_json="$(skillclaw_cmd promote "${classify_args[@]}")" ||
    {
        err "classify failed (skillclaw_promote.py returned non-zero)"
        exit 1
    }

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

# Structured candidate record (names only for promoted; dropped also carries its
# schema-validation reason — never session content). The reason aids debugging and
# matches the design doc's dropped-candidate schema ({name, reason}).
new_json="$(echo "$classify_json" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(json.dumps([c["name"] for c in d.get("promote",[]) if c.get("status")=="NEW"]))')"
changed_json="$(echo "$classify_json" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(json.dumps([c["name"] for c in d.get("promote",[]) if c.get("status")=="CHANGED"]))')"
dropped_json="$(echo "$classify_json" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(json.dumps([{"name": c["name"], "reason": c.get("reason", "")} for c in d.get("dropped",[])]))')"
audit log "$run_id" classify candidates new="$new_json" changed="$changed_json" dropped="$dropped_json"
audit log "$run_id" classify stage_end seconds=$((SECONDS - _t0))

if [[ -z "$promote_names" ]]; then
    echo "Nothing to promote."
    RUN_DONE=true
    audit log "$run_id" "-" run_end state=done total_seconds=$SECONDS
    exit 0
fi

if [[ "$APPLY" != true ]]; then
    echo ""
    echo "Dry run — re-run with --apply to open a review PR."
    RUN_DONE=true
    audit log "$run_id" "-" run_end state=done total_seconds=$SECONDS
    exit 0
fi

# 5. Stage a branch with one commit per skill, then open a PR.
CUR_STAGE="promote"
_t0=$SECONDS
echo "▸ promote…"
audit log "$run_id" promote stage_start
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
    git commit -m "skill(${name}): evolve via SkillClaw" > /dev/null
done

body="$(printf 'Auto-evolved by SkillClaw. Skills: %s\n\nProvenance: %s\nReview each commit independently; drop a skill by reverting its commit.' \
    "$promote_names" "$SESSIONS")"

git push -u origin "$branch"

pr_url="$("$GITOPS" pr-create --base "$PR_BASE" --head "$branch" \
    --title "SkillClaw: evolve ${count} skill(s)" --body "$body" \
    --label needs-review --label follow-up)"

audit log "$run_id" promote pr_opened url="$pr_url"
audit log "$run_id" promote stage_end seconds=$((SECONDS - _t0))
echo "Opened review PR: $pr_url"
RUN_DONE=true
audit log "$run_id" "-" run_end state=done total_seconds=$SECONDS
audit trim
