#!/usr/bin/env bats
# Tests for configs/claude/scripts/spec_review.sh

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
SCRIPT="$REPO_ROOT/configs/claude/scripts/spec_review.sh"

setup() {
    export BATS_TMPDIR="${BATS_TMPDIR:-/tmp}"
    SANDBOX=$(mktemp -d "$BATS_TMPDIR/spec_review.XXXXXX")
}

teardown() {
    [[ -n "$SANDBOX" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"
}

@test "spec_review.sh is executable and prints usage on --help" {
    run bash "$SCRIPT" --help
    assert_success
    assert_output --partial "spec-review"
    assert_output --partial "--silent"
}

@test "spec_review.sh rejects an unknown flag" {
    run bash "$SCRIPT" --bogus
    assert_failure
}

@test "discover_artifacts finds speckit spec/plan/tasks in a specs dir" {
    mkdir -p "$SANDBOX/specs/001-feature"
    : > "$SANDBOX/specs/001-feature/spec.md"
    : > "$SANDBOX/specs/001-feature/plan.md"
    : > "$SANDBOX/specs/001-feature/tasks.md"
    source "$SCRIPT"
    run discover_artifacts "$SANDBOX"
    assert_success
    assert_output --partial "spec	$SANDBOX/specs/001-feature/spec.md"
    assert_output --partial "plan	$SANDBOX/specs/001-feature/plan.md"
    assert_output --partial "tasks	$SANDBOX/specs/001-feature/tasks.md"
}

@test "discover_artifacts finds superpowers design+plan (tasks embedded in plan)" {
    mkdir -p "$SANDBOX/docs/superpowers/specs" "$SANDBOX/docs/superpowers/plans"
    : > "$SANDBOX/docs/superpowers/specs/2026-06-08-thing-design.md"
    : > "$SANDBOX/docs/superpowers/plans/2026-06-08-thing.md"
    source "$SCRIPT"
    run discover_artifacts "$SANDBOX"
    assert_success
    assert_output --partial "spec	$SANDBOX/docs/superpowers/specs/2026-06-08-thing-design.md"
    assert_output --partial "plan	$SANDBOX/docs/superpowers/plans/2026-06-08-thing.md"
    refute_output --partial "tasks	"
}

@test "discover_artifacts prints nothing when no artifacts exist" {
    source "$SCRIPT"
    run discover_artifacts "$SANDBOX"
    assert_output ""
}

@test "assemble_prompt embeds template and role-labelled artifact contents" {
    local tpl="$SANDBOX/tpl.md"; printf 'HEAD
{{ARTIFACTS}}
TAIL
' > "$tpl"
    printf 'spec body here
' > "$SANDBOX/spec.md"
    printf 'plan body here
' > "$SANDBOX/plan.md"
    source "$SCRIPT"
    run assemble_prompt "$tpl" "spec	$SANDBOX/spec.md" "plan	$SANDBOX/plan.md"
    assert_success
    assert_output --partial "HEAD"
    assert_output --partial "=== SPEC: $SANDBOX/spec.md ==="
    assert_output --partial "spec body here"
    assert_output --partial "=== PLAN: $SANDBOX/plan.md ==="
    assert_output --partial "plan body here"
    assert_output --partial "TAIL"
    refute_output --partial "{{ARTIFACTS}}"
}

_fake_gemini() {  # writes a stub gemini onto PATH inside SANDBOX
    cat > "$SANDBOX/gemini" <<'STUB'
#!/usr/bin/env bash
cat >/dev/null   # consume stdin
printf '⚠️  CLARIFICATION REQUIRED: Migration\n   ├─ Location: plan vs tasks\n   ├─ The Gap: zero-downtime vs destructive\n   ├─ Recommended Direction: split into 3 tasks\n   └─ Reason Why: locking violates the constraint\n'
STUB
    chmod +x "$SANDBOX/gemini"
}

@test "run_gemini pipes prompt through the injectable seam" {
    _fake_gemini
    source "$SCRIPT"
    SPEC_REVIEW_GEMINI="$SANDBOX/gemini" run run_gemini "any prompt"
    assert_success
    assert_output --partial "CLARIFICATION REQUIRED: Migration"
}

@test "format_findings tree passes structured findings through" {
    source "$SCRIPT"
    run format_findings "⚠️  CLARIFICATION REQUIRED: X" "tree"
    assert_output --partial "CLARIFICATION REQUIRED: X"
}

@test "format_findings reports clean when gemini returns NO_ISSUES" {
    source "$SCRIPT"
    run format_findings "NO_ISSUES" "tree"
    assert_success
    assert_output --partial "No inconsistencies found"
}

@test "format_findings json emits a JSON array" {
    source "$SCRIPT"
    run format_findings "NO_ISSUES" "json"
    assert_output --partial "[]"
}

@test "format_findings json wraps real findings as valid JSON (incl. special chars)" {
    source "$SCRIPT"
    run format_findings 'CLARIFICATION: a & b \slash "quote"' "json"
    assert_success
    # the python3-wrapped branch must produce JSON that parses and round-trips
    echo "$output" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert isinstance(d,list) and "CLARIFICATION" in d[0]'
}

@test "content_hash is stable for same content and differs on change" {
    printf 'a\n' > "$SANDBOX/x.md"; printf 'b\n' > "$SANDBOX/y.md"
    source "$SCRIPT"
    h1="$(content_hash "$SANDBOX/x.md" "$SANDBOX/y.md")"
    h2="$(content_hash "$SANDBOX/x.md" "$SANDBOX/y.md")"
    [ "$h1" = "$h2" ]
    printf 'b2\n' > "$SANDBOX/y.md"
    h3="$(content_hash "$SANDBOX/x.md" "$SANDBOX/y.md")"
    [ "$h1" != "$h3" ]
}

@test "should_run_silent skips when fewer than 2 artifacts" {
    mkdir -p "$SANDBOX/specs/001"; : > "$SANDBOX/specs/001/spec.md"
    source "$SCRIPT"
    SPEC_REVIEW_STATE="$SANDBOX/.spec-review" run should_run_silent "$SANDBOX"
    assert_failure
    assert_output --partial "fewer than 2 artifacts"
}

@test "should_run_silent runs on first change, skips on unchanged hash" {
    mkdir -p "$SANDBOX/specs/001"
    printf 's\n' > "$SANDBOX/specs/001/spec.md"
    printf 'p\n' > "$SANDBOX/specs/001/plan.md"
    source "$SCRIPT"
    export SPEC_REVIEW_STATE="$SANDBOX/.spec-review"
    run should_run_silent "$SANDBOX"; assert_success          # first time: changed
    run should_run_silent "$SANDBOX"; assert_failure          # unchanged hash
    assert_output --partial "unchanged"
    printf 'p2\n' > "$SANDBOX/specs/001/plan.md"
    run should_run_silent "$SANDBOX"; assert_success          # changed again
}

@test "on-demand review prints findings from the mocked gemini" {
    _fake_gemini
    mkdir -p "$SANDBOX/specs/001"
    printf 's\n' > "$SANDBOX/specs/001/spec.md"
    printf 'p\n' > "$SANDBOX/specs/001/plan.md"
    SPEC_REVIEW_GEMINI="$SANDBOX/gemini" SPEC_REVIEW_TEMPLATE="$REPO_ROOT/configs/claude/prompts/spec_review.md" \
        run bash "$SCRIPT" "$SANDBOX"
    assert_success
    assert_output --partial "CLARIFICATION REQUIRED: Migration"
}

@test "on-demand review on no artifacts exits 0 with nothing-to-review" {
    run bash "$SCRIPT" "$SANDBOX"
    assert_success
    assert_output --partial "nothing to review"
}

@test "silent mode writes feedback file and exits 0 (inline via NO_DETACH)" {
    _fake_gemini
    mkdir -p "$SANDBOX/specs/001"
    printf 's\n' > "$SANDBOX/specs/001/spec.md"
    printf 'p\n' > "$SANDBOX/specs/001/plan.md"
    SPEC_REVIEW_GEMINI="$SANDBOX/gemini" SPEC_REVIEW_NO_DETACH=1 \
        SPEC_REVIEW_STATE="$SANDBOX/.spec-review" \
        SPEC_REVIEW_TEMPLATE="$REPO_ROOT/configs/claude/prompts/spec_review.md" \
        run bash "$SCRIPT" --silent "$SANDBOX"
    assert_success
    assert [ -f "$SANDBOX/.spec-review/feedback.md" ]
    run cat "$SANDBOX/.spec-review/feedback.md"
    assert_output --partial "CLARIFICATION REQUIRED: Migration"
}

@test "silent mode fails open: non-zero gemini still exits 0" {
    printf '#!/usr/bin/env bash\nexit 3\n' > "$SANDBOX/gemini"; chmod +x "$SANDBOX/gemini"
    mkdir -p "$SANDBOX/specs/001"
    printf 's\n' > "$SANDBOX/specs/001/spec.md"
    printf 'p\n' > "$SANDBOX/specs/001/plan.md"
    SPEC_REVIEW_GEMINI="$SANDBOX/gemini" SPEC_REVIEW_NO_DETACH=1 \
        SPEC_REVIEW_STATE="$SANDBOX/.spec-review" \
        SPEC_REVIEW_TEMPLATE="$REPO_ROOT/configs/claude/prompts/spec_review.md" \
        run bash "$SCRIPT" --silent "$SANDBOX"
    assert_success
}

@test "silent mode is a no-op on unchanged content (second run)" {
    _fake_gemini
    mkdir -p "$SANDBOX/specs/001"
    printf 's\n' > "$SANDBOX/specs/001/spec.md"
    printf 'p\n' > "$SANDBOX/specs/001/plan.md"
    local env="SPEC_REVIEW_GEMINI=$SANDBOX/gemini SPEC_REVIEW_NO_DETACH=1 SPEC_REVIEW_STATE=$SANDBOX/.spec-review SPEC_REVIEW_TEMPLATE=$REPO_ROOT/configs/claude/prompts/spec_review.md"
    env $env bash "$SCRIPT" --silent "$SANDBOX"
    rm -f "$SANDBOX/.spec-review/feedback.md"
    env $env bash "$SCRIPT" --silent "$SANDBOX"   # unchanged -> skip, no rewrite
    assert [ ! -f "$SANDBOX/.spec-review/feedback.md" ]
}

@test "silent mode self-heals a stale lock (older than 10 min)" {
    _fake_gemini
    mkdir -p "$SANDBOX/specs/001"
    printf 's\n' > "$SANDBOX/specs/001/spec.md"
    printf 'p\n' > "$SANDBOX/specs/001/plan.md"
    mkdir -p "$SANDBOX/.spec-review/.lock"
    # age the stale lock 20 minutes into the past
    touch -t "$(date -v-20M +%Y%m%d%H%M 2>/dev/null || date -d '20 min ago' +%Y%m%d%H%M)" "$SANDBOX/.spec-review/.lock"
    SPEC_REVIEW_GEMINI="$SANDBOX/gemini" SPEC_REVIEW_NO_DETACH=1 \
        SPEC_REVIEW_STATE="$SANDBOX/.spec-review" \
        SPEC_REVIEW_TEMPLATE="$REPO_ROOT/configs/claude/prompts/spec_review.md" \
        run bash "$SCRIPT" --silent "$SANDBOX"
    assert_success
    assert [ -f "$SANDBOX/.spec-review/feedback.md" ]   # ran despite the stale lock
    assert [ ! -d "$SANDBOX/.spec-review/.lock" ]        # lock released after run
}

@test "spec-review SKILL.md has valid frontmatter and points at the engine" {
    local skill="$REPO_ROOT/.skillshare/skills/spec-review/SKILL.md"
    assert [ -f "$skill" ]
    run head -1 "$skill"; assert_output "---"
    run grep -E '^name: spec-review' "$skill"; assert_success
    run grep -E 'spec_review\.sh' "$skill"; assert_success
}

@test ".gitignore ignores the .spec-review runtime dir" {
    run grep -E '^\.spec-review/?$' "$REPO_ROOT/.gitignore"
    assert_success
}

@test "settings.local.json registers the spec_review silent save hook" {
    local s="$REPO_ROOT/configs/claude/settings.local.json"
    run python3 -c "import json; d=json.load(open('$s')); cmds=[h['command'] for m in d['hooks']['PostToolUse'] for h in m['hooks']]; assert any('spec_review.sh' in c and '--silent' in c for c in cmds), cmds"
    assert_success
}

@test "settings.local.json remains valid JSON" {
    run python3 -c "import json; json.load(open('$REPO_ROOT/configs/claude/settings.local.json'))"
    assert_success
}

@test "settings.local.json still has the pre-existing version_pin hook" {
    local s="$REPO_ROOT/configs/claude/settings.local.json"
    run python3 -c "import json; d=json.load(open('$s')); cmds=[h['command'] for m in d['hooks']['PostToolUse'] for h in m['hooks']]; assert any('version_pin' in c for c in cmds), cmds"
    assert_success
}
