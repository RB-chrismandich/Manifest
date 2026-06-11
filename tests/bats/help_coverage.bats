#!/usr/bin/env bats
# specs/003 T039 / R6: every user-facing entry point in configs/claude/scripts/
# handles --help (usage to stdout, exit 0). Exempt with documented rationale
# (.claude/CLAUDE.md): version_pin_hook.sh (save-hook wrapper) and
# git_platform.sh (internal helper used by git_ops.sh).

setup() {
    load '../test_helper/bats-support/load'
    load '../test_helper/bats-assert/load'
    SCRIPTS="$(cd "$(dirname "$BATS_TEST_FILENAME")/../../configs/claude/scripts" && pwd)"
}

USER_FACING="branch_clean.sh check_status.sh git_ops.sh linear_ops.sh
pr_review.sh skillclaw_promote.sh sync-skills.sh version_pin.sh
browser_test.sh label_sync.sh learning_capture.sh spec_review.sh"

@test "every user-facing script: --help exits 0 and prints Usage on stdout" {
    for f in $USER_FACING; do
        run bash "$SCRIPTS/$f" --help
        [ "$status" -eq 0 ] || { echo "$f: exit $status"; false; }
        [[ "$output" == *"Usage"* || "$output" == *"USAGE"* ]] \
            || { echo "$f: no Usage in --help output"; false; }
    done
}

@test "--help output stays concise (<= 50 lines per script)" {
    # R6's <=15-line guideline applies to the minimal helps ADDED by T039;
    # pre-existing comprehensive helps (learning_capture: 44) get headroom.
    for f in $USER_FACING; do
        lines=$(bash "$SCRIPTS/$f" --help | wc -l | tr -d ' ')
        [ "$lines" -le 50 ] || { echo "$f: $lines lines"; false; }
    done
}

@test "exempt scripts are documented in .claude/CLAUDE.md" {
    doc="$SCRIPTS/../../../.claude/CLAUDE.md"
    grep -q "version_pin_hook.sh" "$doc"
    grep -q "git_platform.sh" "$doc"
}
