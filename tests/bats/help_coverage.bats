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
label_sync.sh learning_capture.sh spec_review.sh"

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

# --- Python entry points ----------------------------------------------------
# Every .py in configs/claude/scripts/ that is a directly-invocable CLI (has
# its own --help) is gated the same way as the Bash USER_FACING list above.
# Excluded, with rationale documented in .claude/CLAUDE.md's Script
# Conventions section: _manifest_shim.py (shared library, no __main__, never
# invoked directly), budget_broker.py (interceptor wrapper — argv IS the
# wrapped command being intercepted, not its own flags, so "--help" is
# forwarded to the child process rather than handled), reconcile_core.py
# (internal read-only engine behind deploy_reconcile.sh; add_help=False and
# no direct CLI surface, per its own module docstring).
PY_USER_FACING="cddl_invoke.py cddl_loop.py command_catalog.py
generate_commands_doc.py generate_cursor_agents.py generate_cursor_mcp.py
guidance_hint.py opus_attribution_report.py parallel_agent.py
skill_usage_report.py skillclaw_audit.py skillclaw_evolve.py
skillclaw_ingest.py skillclaw_promote.py skillclaw_scrub.py smoke_test.py
token_cost_report.py tracker_registry.py"

@test "every user-facing python script: --help exits 0 and prints usage on stdout" {
    for f in $PY_USER_FACING; do
        run python3 "$SCRIPTS/$f" --help
        [ "$status" -eq 0 ] || { echo "$f: exit $status"; false; }
        lc_output="$(printf '%s' "$output" | tr '[:upper:]' '[:lower:]')"
        [[ "$lc_output" == *"usage"* ]] \
            || { echo "$f: no usage in --help output"; false; }
    done
}

@test "python --help output stays concise (<= 80 lines per script)" {
    # 80 (vs the Bash list's 50) gives headroom for argparse's fuller,
    # auto-generated option blocks (e.g. parallel_agent.py's full flag surface
    # is a legitimate ~63 lines, not a defect).
    for f in $PY_USER_FACING; do
        lines=$(python3 "$SCRIPTS/$f" --help 2>&1 | wc -l | tr -d ' ')
        [ "$lines" -le 80 ] || { echo "$f: $lines lines"; false; }
    done
}

@test "exempt python scripts are documented in .claude/CLAUDE.md" {
    doc="$SCRIPTS/../../../.claude/CLAUDE.md"
    grep -q "_manifest_shim.py" "$doc"
    grep -q "budget_broker.py" "$doc"
    grep -q "reconcile_core.py" "$doc"
}
