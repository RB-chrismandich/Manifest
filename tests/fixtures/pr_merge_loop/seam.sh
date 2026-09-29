#!/usr/bin/env bash
op="$1"
pr="${2:-}"
printf '%s %s\n' "$op" "$pr" >> "${SEAM_CALL_LOG:?}"
if [[ "${SEAM_FP_FAIL:-}" == "$op" || "${SEAM_FP_FAIL:-}" == "${op#fp-}" ]]; then
    exit 71
fi
case "$op" in
    fp-scope)
        if [[ -n "${SEAM_SCOPE:-}" ]]; then
            printf '%s\n' "$SEAM_SCOPE"
        else
            printf '%s\n' '{"host":"github.com","owner_repo":"acme/widgets"}'
        fi
        ;;
    fp-view)
        if [[ -n "${SEAM_FP_VIEW:-}" ]]; then
            printf '%s\n' "$SEAM_FP_VIEW"
        else
            python3 - "$pr" << 'PY'
import json
import os
import sys

pr = sys.argv[1]
head = os.environ.get("SEAM_HEAD", "sha1")
head_file = os.path.join(os.environ.get("SEAM_HEAD_DIR", ""), pr)
if os.path.isfile(head_file):
    with open(head_file, encoding="utf-8") as handle:
        head = handle.read().strip()
print(json.dumps({
    "headRefOid": head,
    "baseRefName": os.environ.get("SEAM_BASE", "main"),
    "mergeable": os.environ.get("SEAM_FP_MERGEABLE", "MERGEABLE"),
    "mergeStateStatus": os.environ.get("SEAM_FP_MERGE_STATE", "CLEAN"),
    "reviewDecision": os.environ.get("SEAM_RD", "APPROVED"),
    "latestReviews": json.loads(os.environ.get("SEAM_LATEST_REVIEWS", "[]")),
    "labels": [{"name": name} for name in json.loads(os.environ.get("SEAM_LABELS", "[]"))],
    "isDraft": os.environ.get("SEAM_DRAFT", "false") == "true",
    "state": os.environ.get("SEAM_PR_STATE", "OPEN"),
}))
PY
        fi
        ;;
    fp-checks)
        if [[ -n "${SEAM_FP_CHECKS:-}" ]]; then
            printf '%s\n' "$SEAM_FP_CHECKS"
        else
            python3 - << 'PY'
import json
import os

checks = []
for index, bucket in enumerate(os.environ.get("SEAM_BUCKETS", "pass").split()):
    checks.append({
        "name": f"check-{index}",
        "bucket": bucket,
        "state": "IN_PROGRESS" if bucket == "pending" else "COMPLETED",
        "link": f"https://checks.invalid/{index}",
        "startedAt": "2026-09-19T00:00:00Z",
        "completedAt": None if bucket == "pending" else "2026-09-19T00:01:00Z",
    })
print(json.dumps(checks))
PY
        fi
        ;;
    fp-threads)
        if [[ -n "${SEAM_FP_THREADS:-}" ]]; then
            printf '%s\n' "$SEAM_FP_THREADS"
        else
            printf '%s\n' '{"data":{"repository":{"pullRequest":{"reviewThreads":{"pageInfo":{"hasNextPage":false,"endCursor":null},"nodes":[]}}}}}'
        fi
        ;;
    list) echo "${SEAM_LIST:-[]}" ;;
    checks) printf '%s\n' ${SEAM_BUCKETS-pass} ;;
    reviewdecision) echo "${SEAM_RD:-APPROVED}" ;;
    unresolved-human) echo "${SEAM_UH:-0}" ;;
    disposition) echo "${SEAM_DISP:-merge}" ;;
    mergeable) echo "${SEAM_MRG:-MERGEABLE CLEAN}" ;;
    hold) echo "${SEAM_HOLD:-false}" ;;
    author) echo "${SEAM_AUTHOR:-Copilot}" ;;
    admin-check) echo "${SEAM_ADMIN:-true}" ;;
    protection) echo "${SEAM_PROT:-enforce_admins=false required_signatures=false merge_queue=false}" ;;
    update-branch) [ "${SEAM_UPDATE_FAIL:-0}" = 1 ] && exit 1 || echo updated ;;
    add-label)
        printf '%s %s\n' "$pr" "${3:-}" >> "${SEAM_LABEL_LOG:?}"
        [ "${SEAM_LABEL_FAIL:-0}" = 1 ] && exit 1 || exit 0
        ;;
    do-merge) [ "${SEAM_MERGE_FAIL:-0}" = 1 ] && exit 1 || echo merged ;;
    headsha)
        if [[ -f "${SEAM_HEAD_DIR:?}/$pr" ]]; then cat "${SEAM_HEAD_DIR}/$pr"; else echo "${SEAM_HEAD:-sha1}"; fi
        ;;
    basebranch) echo "${SEAM_BASE:-main}" ;;
    mergecommit) echo "${SEAM_MERGE_SHA:-mergesha1}" ;;
esac
