#!/bin/sh
# Fail-closed boundary for the manifest-delegate Stop review gate.

set -u
umask 077

block() {
    printf '%s\n' "{\"decision\":\"block\",\"reason\":\"Review gate could not verify this turn ($1); make no tool calls or edits; report the failure to the developer for a decision.\"}"
}

JQ=$(command -v jq 2> /dev/null || true)
if [ -z "$JQ" ]; then
    block "jq_unavailable"
    exit 0
fi

WORK_DIR=$(mktemp -d "${TMPDIR:-/tmp}/manifest-stop-gate.XXXXXX" 2> /dev/null || true)
if [ -z "$WORK_DIR" ] || [ ! -d "$WORK_DIR" ]; then
    block "temporary_storage_unavailable"
    exit 0
fi
if ! chmod 700 "$WORK_DIR" 2> /dev/null; then
    block "temporary_storage_unavailable"
    rm -rf "$WORK_DIR" 2> /dev/null || true
    exit 0
fi
INPUT_FILE="$WORK_DIR/input.json"
OUTPUT_FILE="$WORK_DIR/decision.json"
FORWARD_FILE="$WORK_DIR/forward.json"
ERROR_FILE="$WORK_DIR/stderr.txt"
: > "$INPUT_FILE"
: > "$OUTPUT_FILE"
: > "$FORWARD_FILE"
: > "$ERROR_FILE"
if ! chmod 600 "$INPUT_FILE" "$OUTPUT_FILE" "$FORWARD_FILE" "$ERROR_FILE" 2> /dev/null; then
    block "temporary_storage_unavailable"
    rm -rf "$WORK_DIR" 2> /dev/null || true
    exit 0
fi

cleanup() {
    rm -rf "$WORK_DIR" 2> /dev/null || true
}
interrupted() {
    cleanup
    block "launcher_interrupted"
    exit 0
}
trap cleanup 0
trap interrupted HUP INT TERM

# Capture one byte beyond the 1 MiB contract without ever reading unbounded stdin.
if ! dd bs=4096 count=257 of="$INPUT_FILE" 2> /dev/null; then
    block "input_unreadable"
    exit 0
fi
INPUT_BYTES_RAW=$(wc -c < "$INPUT_FILE" 2> /dev/null || printf '%s' 1048577)
set -- $INPUT_BYTES_RAW
INPUT_BYTES=${1:-}
case "$INPUT_BYTES" in
    '' | *[!0-9]*)
        block "input_unreadable"
        exit 0
        ;;
esac
if [ "$INPUT_BYTES" -gt 1048576 ]; then
    block "input_too_large"
    exit 0
fi

# Loop safety must work even when the managed Python runtime is broken. The
# recursion guard runs FIRST, before the generic object-shape check: a guarded
# follow-up must never be mistaken for invalid input, and the guard's own jq
# projection is type-guarded so non-object payloads (arrays, scalars, strings)
# can never satisfy it — on some jq builds `.<field>` on a non-object coerces
# rather than errors, which would be a false approve.
if "$JQ" -e -s 'length == 1 and (.[0] | type == "object" and .stop_hook_active == true)' \
    "$INPUT_FILE" > /dev/null 2>&1; then
    printf '%s\n' '{"decision":"approve","reason":"stop-hook-active"}'
    exit 0
fi

if ! "$JQ" -e -s 'length == 1 and (.[0] | type == "object")' \
    "$INPUT_FILE" > /dev/null 2>&1; then
    block "invalid_input"
    exit 0
fi

# Only a genuine Stop event may take the disabled-gate approve path. Every
# other object — non-event payloads or a Stop event with no usable transcript
# — stays fail-closed rather than being silently approved. The transcript
# check mirrors the wrapper's `str.strip()` rule so both paths agree on what
# counts as malformed.
if ! "$JQ" -e -s 'length == 1 and (.[0] | .hook_event_name == "Stop")' \
    "$INPUT_FILE" > /dev/null 2>&1; then
    block "not_stop_event"
    exit 0
fi
if ! "$JQ" -e -s 'length == 1 and (.[0] | .transcript_path | type == "string" and test("\\S"))' \
    "$INPUT_FILE" > /dev/null 2>&1; then
    block "missing_transcript"
    exit 0
fi

# A disabled review gate approves without the managed runtime, so plugin-only
# installs (no bootstrap-created ~/.claude/.venv) never hit a spurious block.
# Config precedence mirrors manifest_delegate/config.py: MANIFEST_CONFIG_DIR,
# then $XDG_CONFIG_HOME/manifest, then the legacy ~/.claude/config. Only a JSON
# delegation file can be evaluated here; a winning delegation.yml or an
# unparseable file falls through to the managed runtime, which fails closed.
find_delegation_file() {
    for _dir in "$@"; do
        [ -n "$_dir" ] || continue
        if [ -f "$_dir/delegation.json" ]; then
            printf '%s\n' "$_dir/delegation.json"
            return 0
        fi
        if [ -f "$_dir/delegation.yml" ]; then
            printf '%s\n' "$_dir/delegation.yml"
            return 0
        fi
    done
    return 1
}

DELEGATION_FILE=$(find_delegation_file \
    "${MANIFEST_CONFIG_DIR:-}" \
    "${XDG_CONFIG_HOME:-${HOME:-}/.config}/manifest" \
    "${HOME:-}/.claude/config" || true)

case "$DELEGATION_FILE" in
    "")
        printf '%s\n' '{"decision":"approve","reason":"gate disabled"}'
        exit 0
        ;;
    *.json)
        if ! "$JQ" -e 'type == "object"' "$DELEGATION_FILE" > /dev/null 2>&1; then
            block "config_unparseable"
            exit 0
        fi
        if ! "$JQ" -e '.review_gate.enabled == true' "$DELEGATION_FILE" \
            > /dev/null 2>&1; then
            printf '%s\n' '{"decision":"approve","reason":"gate disabled"}'
            exit 0
        fi
        ;;
esac

RUNTIME_PYTHON="${HOME:-}/.claude/.venv/bin/python"
if [ ! -x "$RUNTIME_PYTHON" ]; then
    block "interpreter_unavailable"
    exit 0
fi
if [ -z "${CLAUDE_PLUGIN_ROOT:-}" ]; then
    block "plugin_unavailable"
    exit 0
fi
PYTHON_WRAPPER="$CLAUDE_PLUGIN_ROOT/scripts/stop_gate_hook.py"
if [ ! -f "$PYTHON_WRAPPER" ]; then
    block "plugin_unavailable"
    exit 0
fi

if ! "$RUNTIME_PYTHON" "$PYTHON_WRAPPER" --stdin-json "$INPUT_FILE" \
    > "$OUTPUT_FILE" 2> "$ERROR_FILE"; then
    block "wrapper_failed"
    exit 0
fi

if ! "$JQ" -c -s '
    if (
        length == 1 and
        (.[0] |
            type == "object" and
            ((.decision == "approve") or (.decision == "block")) and
            (.reason | if type == "string" then test("\\S") else false end)
        )
    ) then
        .[0] | {decision, reason}
    else
        error("invalid decision")
    end
' "$OUTPUT_FILE" > "$FORWARD_FILE" 2> /dev/null; then
    block "invalid_decision"
    exit 0
fi

# Forward only the privately canonicalized native fields, never raw output.
if ! cat "$FORWARD_FILE"; then
    block "decision_unreadable"
    exit 0
fi
exit 0
