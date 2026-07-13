#!/usr/bin/env bats
# release_workflow_hardening.bats — CI template security gate for release.yml
#
# Ensures templates/ci/github/release.yml has no run-shell-injection findings
# and no direct ${{ }} interpolation inside run: shell scripts.

REPO_ROOT="$(cd "$(dirname "$BATS_TEST_FILENAME")/../.." && pwd)"
RELEASE_YML="$REPO_ROOT/templates/ci/github/release.yml"

setup() {
    [ -f "$RELEASE_YML" ] || { echo "missing $RELEASE_YML" >&2; return 1; }
    if ! command -v semgrep >/dev/null 2>&1; then
        skip "semgrep not installed"
    fi
}

@test "release.yml: semgrep reports no run-shell-injection findings" {
    local json
    json="$(semgrep scan --config p/ci --quiet --json "$RELEASE_YML")"
    local count
    count="$(printf '%s' "$json" | python3 -c "
import json, sys
data = json.load(sys.stdin)
findings = [
    r for r in data.get('results', [])
    if 'run-shell-injection' in r.get('check_id', '')
]
print(len(findings))
")"
    [ "$count" -eq 0 ]
}

@test "release.yml: no direct \${{ }} interpolation inside run: blocks" {
    python3 - "$RELEASE_YML" <<'PY'
import re
import sys

path = sys.argv[1]
with open(path) as f:
    lines = f.readlines()

in_run = False
violations = []
for i, line in enumerate(lines, 1):
    stripped = line.strip()
    if re.match(r"run:\s*\|", stripped) or stripped == "run: |":
        in_run = True
        continue
    if in_run:
        # End of run block: next step key at same or lesser indent
        if re.match(r"^      - name:", line) or re.match(r"^      - uses:", line):
            in_run = False
        elif re.match(r"^    [a-z]", line) and not line.startswith("        "):
            in_run = False
        elif "${{" in line and not stripped.startswith("#"):
            violations.append((i, stripped))

if violations:
    for lineno, text in violations:
        print(f"line {lineno}: {text}")
    sys.exit(1)
PY
}
