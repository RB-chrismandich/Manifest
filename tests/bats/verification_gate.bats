#!/usr/bin/env bats
# Tests for configs/claude/scripts/verification_gate.sh (#360 verification gate).
# Design: docs/superpowers/specs/2026-06-18-auto-issue-dev-verification-gate-design.md

SCRIPT="$BATS_TEST_DIRNAME/../../configs/claude/scripts/verification_gate.sh"

setup() {
    TMP=$(mktemp -d "${BATS_TMPDIR:-/tmp}/vgate.XXXXXX")
}
teardown() { [[ -n "$TMP" && -d "$TMP" ]] && rm -rf "$TMP"; }

action() { python3 -c 'import json,sys;print(json.load(sys.stdin)["action"])'; }

# --- CLI ---
@test "--help exits 0, mentions review and decide" {
    run "$SCRIPT" --help
    [ "$status" -eq 0 ]; [[ "$output" == *"review"* ]]; [[ "$output" == *"decide"* ]]
}
@test "unknown subcommand non-zero" { run "$SCRIPT" bogus; [ "$status" -ne 0 ]; }

# --- decide (pure core) ---
@test "decide: reviewer_error -> draft-needs-human" {
    run "$SCRIPT" decide '{"reviewer_error":true}'
    [ "$status" -eq 0 ]; [ "$(echo "$output" | action)" = "draft-needs-human" ]
}
@test "decide: tier1 fail -> draft-needs-human" {
    run "$SCRIPT" decide '{"tier1":{"passed":false},"consensus_score":0.9}'
    [ "$(echo "$output" | action)" = "draft-needs-human" ]
}
@test "decide: tier1 pass + high consensus -> pr-open" {
    run "$SCRIPT" decide '{"tier1":{"passed":true},"tier2":{"score":0.7},"consensus_score":0.86}'
    [ "$(echo "$output" | action)" = "pr-open" ]
}
@test "decide: tier1 pass + mid consensus -> pr-open with disagreement annotation" {
    run "$SCRIPT" decide '{"tier1":{"passed":true},"tier2":{"score":0.7},"consensus_score":0.62}'
    [ "$(echo "$output" | action)" = "pr-open" ]
    [[ "$output" == *"disagreement"* || "$output" == *"consensus"* ]]
}
@test "decide: malformed -> draft-needs-human (fail closed)" {
    run "$SCRIPT" decide 'nope{'
    [ "$status" -eq 0 ]; [ "$(echo "$output" | action)" = "draft-needs-human" ]
}

# --- review (seam) ---
@test "review: seam returns gate JSON -> emitted with tier1+consensus_score" {
    cat > "$TMP/seam.sh" <<'EOF'
#!/usr/bin/env bash
echo '{"tier1":{"passed":true,"issues":[]},"tier2":{"score":0.8,"concerns":[]},"consensus_score":0.9,"verdict":"APPROVED"}'
EOF
    chmod +x "$TMP/seam.sh"
    VERIFICATION_GATE_REVIEW_CMD="$TMP/seam.sh" run "$SCRIPT" review 123
    [ "$status" -eq 0 ]
    echo "$output" | python3 -c 'import json,sys;d=json.load(sys.stdin);assert d["tier1"]["passed"] is True;assert d["consensus_score"]==0.9'
}
@test "review: parallel_agent-shaped output is adapted to gate JSON" {
    cat > "$TMP/seam.sh" <<'EOF'
#!/usr/bin/env bash
echo '{"mode":"review","agents":{},"cross_verification":{"consensus_score":86,"confidence":"high","agent_count":4},"validation":{"tier1":{"passed":true,"failures":[],"checks":{"cross_verification":{"passed":true,"score":0.86,"threshold":0.8,"weight":0.3}}},"tier2":{"score":0.9,"concerns":[]},"verdict":"APPROVED"}}'
EOF
    chmod +x "$TMP/seam.sh"
    VERIFICATION_GATE_REVIEW_CMD="$TMP/seam.sh" run "$SCRIPT" review 123
    [ "$status" -eq 0 ]
    # consensus_score must be the FRACTION (tier1 cross_verification check score), never the
    # percent-scale cross_verification.consensus_score (86) — merge_decision bands at 0.80.
    echo "$output" | python3 -c 'import json,sys;d=json.load(sys.stdin);assert d["tier1"]["passed"] is True;assert d["consensus_score"]==0.86;assert d["verdict"]=="APPROVED";assert not d.get("reviewer_error")'
}

@test "review: percent-scale consensus without the checks fraction is normalized, never passed raw" {
    cat > "$TMP/seam.sh" <<'EOF'
#!/usr/bin/env bash
echo '{"mode":"review","agents":{},"cross_verification":{"consensus_score":1,"confidence":"low","agent_count":2},"validation":{"tier1":{"passed":true,"failures":[]},"tier2":{},"verdict":"APPROVED"}}'
EOF
    chmod +x "$TMP/seam.sh"
    VERIFICATION_GATE_REVIEW_CMD="$TMP/seam.sh" run "$SCRIPT" review 123
    [ "$status" -eq 0 ]
    # 1 here means 1% — reading it as fraction 1.0 would sail past the 0.80 merge band.
    echo "$output" | python3 -c 'import json,sys;d=json.load(sys.stdin);assert d["consensus_score"]==0.01, d'
}

@test "review: parallel_agent output without validation -> reviewer_error (fail closed)" {
    cat > "$TMP/seam.sh" <<'EOF'
#!/usr/bin/env bash
echo '{"mode":"review","agents":{},"cross_verification":{"consensus_score":1},"validation":null}'
EOF
    chmod +x "$TMP/seam.sh"
    VERIFICATION_GATE_REVIEW_CMD="$TMP/seam.sh" run "$SCRIPT" review 123
    [ "$status" -eq 0 ]
    echo "$output" | python3 -c 'import json,sys;d=json.load(sys.stdin);assert d["reviewer_error"] is True'
}

@test "review: seam non-zero -> reviewer_error sentinel (fail closed)" {
    cat > "$TMP/seam.sh" <<'EOF'
#!/usr/bin/env bash
exit 1
EOF
    chmod +x "$TMP/seam.sh"
    VERIFICATION_GATE_REVIEW_CMD="$TMP/seam.sh" run "$SCRIPT" review 123
    [ "$status" -eq 0 ]
    echo "$output" | python3 -c 'import json,sys;assert json.load(sys.stdin)["reviewer_error"] is True'
}
@test "review: seam emits non-JSON -> reviewer_error sentinel" {
    cat > "$TMP/seam.sh" <<'EOF'
#!/usr/bin/env bash
echo "boom, not json"
EOF
    chmod +x "$TMP/seam.sh"
    VERIFICATION_GATE_REVIEW_CMD="$TMP/seam.sh" run "$SCRIPT" review 123
    echo "$output" | python3 -c 'import json,sys;assert json.load(sys.stdin)["reviewer_error"] is True'
}

# --- redaction is a security control: its failure must fail the gate ---------
# Codex + Cursor both filed this as HIGH. The old code ran
# `audit_log.sh redact "$(cat "$packet")"` -- one ARGV element, so a
# multi-megabyte diff exceeded ARG_MAX and exec failed -- then swallowed the
# failure with `|| true` and handed the ORIGINAL unredacted packet to the
# reviewer. These run against a COPY of the script so the sibling
# `audit_log.sh` it resolves via SCRIPT_DIR can be replaced with a failing one.

_isolated_gate() { # $1 = audit_log.sh body
    cp "$SCRIPT" "$TMP/verification_gate.sh"
    printf '%s\n' '#!/usr/bin/env bash' "$1" > "$TMP/audit_log.sh"
    printf '%s\n' '#!/usr/bin/env bash' 'exit 0' > "$TMP/git_ops.sh"
    printf '%s\n' '#!/usr/bin/env bash' "touch '$TMP/REVIEWER_RAN'" 'echo "{\"tier1\":{\"passed\":true},\"consensus_score\":0.9,\"verdict\":\"APPROVED\"}"' > "$TMP/seam.sh"
    chmod +x "$TMP"/*.sh
}

@test "review: redaction failure blocks and never invokes the reviewer" {
    _isolated_gate 'exit 1'
    VERIFICATION_GATE_REVIEW_CMD="$TMP/seam.sh" run "$TMP/verification_gate.sh" review 123
    [ "$status" -eq 0 ]
    [ ! -f "$TMP/REVIEWER_RAN" ]
    echo "$output" | python3 -c 'import json,sys;d=json.loads([l for l in sys.stdin if l.startswith("{")][-1]);assert d["reviewer_error"] is True;assert d["verdict"]=="BLOCKED"'
}

@test "review: working redaction still reaches the reviewer" {
    _isolated_gate '[ "$1" = redact ] && exec cat
exit 0'
    VERIFICATION_GATE_REVIEW_CMD="$TMP/seam.sh" run "$TMP/verification_gate.sh" review 123
    [ "$status" -eq 0 ]
    [ -f "$TMP/REVIEWER_RAN" ]
}
