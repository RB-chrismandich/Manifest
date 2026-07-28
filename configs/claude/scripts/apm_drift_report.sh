#!/usr/bin/env bash
# apm_drift_report.sh — Constitution V.4 (v3.0.0): detect and report user edits
# to deployed files. FR-034(d).
#
# V.4 was amended from "preserved and reported" to "detected and reported"
# because a package-manager deployer performs the write itself — preservation is
# not expressible by this repository. Detection is, and this is it. Without this
# script the amended principle would be weaker than the one it replaced: the old
# MUST was unachievable, but dropping to detection and then not detecting is
# strictly worse than either.
#
# Why this exists rather than `apm audit`: apm's own drift.py implements exactly
# four categories — ref, orphan, config (MCP only), and stale-file. Deployed-file
# CONTENT drift is not among them, so `apm audit` cannot see a hand-edit no
# matter how it is invoked. Verified directly: with a live canary in a deployed
# SKILL.md, `apm audit --file <lockfile>` reports "1 file(s) scanned -- no issues
# found".
#
# What it compares: the sha256 recorded in the lockfile's deployed_file_hashes at
# install time, against the file on disk now. A mismatch means someone edited a
# build output; the file is still a build output and the next deploy will
# overwrite it, which is exactly what the user needs to be told.
#
# Read-only. Never writes, never repairs.
set -euo pipefail

err() { printf 'apm_drift_report.sh: %s\n' "$*" >&2; }

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    cat << 'USAGE'
Usage: apm_drift_report.sh [--json]

Report deployed files whose content no longer matches what was installed —
the user-edit detection Constitution V.4 requires. apm cannot do this:
content drift is not one of its four drift categories.

  --json   Machine-readable output.

Exit: 0 no drift, 1 drift found, 2 usage error OR indeterminate
(a lockfile with no per-file hashes cannot be checked). Read-only.
USAGE
    exit 0
fi

JSON=false
while [[ $# -gt 0 ]]; do
    case "$1" in
        --json)
            JSON=true
            shift
            ;;
        *)
            err "unknown argument: $1 (see --help)"
            exit 2
            ;;
    esac
done

LOCKFILE="${APM_LOCKFILE:-$HOME/.apm/apm.lock.yaml}"

if [[ ! -f "$LOCKFILE" ]]; then
    # No lockfile means nothing is APM-managed. That is "nothing to check", not
    # "nothing is wrong" — say which, so an absent lockfile is never mistaken
    # for a clean bill of health.
    if [[ "$JSON" == true ]]; then
        printf '{"checked":0,"drifted":[],"missing":[],"status":"no-lockfile"}\n'
    else
        echo "No APM lockfile at $LOCKFILE — nothing is APM-managed, so nothing was checked."
    fi
    exit 0
fi

command -v python3 > /dev/null 2>&1 || {
    err "python3 is required to read the lockfile — refusing to report a clean result it did not verify"
    exit 2
}

python3 - "$LOCKFILE" "$HOME" "$JSON" << 'PY'
import hashlib
import json
import os
import sys

import yaml

lockfile, home, as_json = sys.argv[1], sys.argv[2], sys.argv[3] == "true"

try:
    data = yaml.safe_load(open(lockfile)) or {}
except Exception as exc:  # noqa: BLE001
    print(f"apm_drift_report.sh: cannot parse {lockfile}: {exc}", file=sys.stderr)
    sys.exit(2)

checked, drifted, missing = 0, [], []

for dep in data.get("dependencies") or []:
    if not isinstance(dep, dict):
        continue
    hashes = dep.get("deployed_file_hashes") or {}
    if not isinstance(hashes, dict):
        continue
    for rel, recorded in hashes.items():
        # Path-traversal guard: a corrupted lockfile must not drive reads
        # outside the home it claims to describe.
        if str(rel).startswith("/") or ".." in str(rel):
            continue
        path = os.path.join(home, str(rel))
        checked += 1
        if not os.path.exists(path):
            # Absent is a different finding from modified: the deploy owns it
            # and it is gone, which orphan-tracking would not catch either.
            missing.append(rel)
            continue
        digest = hashlib.sha256(open(path, "rb").read()).hexdigest()
        want = str(recorded).removeprefix("sha256:")
        if digest != want:
            drifted.append({"path": rel, "recorded": want[:16], "actual": digest[:16]})

if as_json:
    if checked == 0:
        status = "unverifiable"
    elif drifted or missing:
        status = "drift"
    else:
        status = "clean"
    print(json.dumps({
        "checked": checked,
        "drifted": drifted,
        "missing": missing,
        "status": status,
    }))
else:
    if checked == 0:
        print("Lockfile records no per-file hashes — content drift CANNOT be checked.")
        print("  A local-path install produces this; a published install records hashes.")
        print("  Exiting 2 (indeterminate): an unverifiable state must not read as clean.")
    elif not drifted and not missing:
        print(f"No drift: {checked} deployed file(s) match what was installed.")
    else:
        for d in drifted:
            print(f"MODIFIED  {d['path']}  (installed {d['recorded']}…, now {d['actual']}…)")
        for m in missing:
            print(f"MISSING   {m}")
        print("")
        print("Deployed files are build outputs — the next deploy WILL overwrite these.")
        print("Move any change you want to keep into the source tree (.apm/skills, configs/).")

# Exit codes: 0 clean, 1 drift found, 2 INDETERMINATE. The third is the one
# that matters — a gate whose subject it could not verify must never report
# success, or "we never checked" and "we checked and it was fine" become the
# same signal to CI.
if checked == 0:
    sys.exit(2)
sys.exit(1 if (drifted or missing) else 0)
PY
