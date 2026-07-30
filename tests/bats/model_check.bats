#!/usr/bin/env bats
# Tests for configs/claude/scripts/model_check.sh

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
SCRIPT="$REPO_ROOT/configs/claude/scripts/model_check.sh"

setup() {
    SANDBOX=$(mktemp -d "${BATS_TMPDIR:-/tmp}/model_check.XXXXXX")
    cat > "$SANDBOX/pa.yml" <<'EOF'
model_tiers:
  antigravity:
    flash: "Gemini 3.5 Flash (High)"
    advanced: "Claude Opus 4.6 (Thinking)"
  codex:
    mini: "gpt-5.4-mini"
EOF
}

teardown() {
    [[ -n "$SANDBOX" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"
}

@test "model_check.sh exits 0 even with no providers available" {
    MODEL_CHECK_CONFIG="$SANDBOX/pa.yml" PATH="/usr/bin:/bin" run bash "$SCRIPT"
    assert_success
}

@test "list_tiers emits tier/model pairs from config" {
    source "$SCRIPT"
    MODEL_CHECK_CONFIG="$SANDBOX/pa.yml"
    run list_tiers antigravity
    assert_success
    assert_output --partial "flash	Gemini 3.5 Flash (High)"
    assert_output --partial "advanced	Claude Opus 4.6 (Thinking)"
}

@test "check_cli_provider reports OK for models present in listing" {
    mkdir -p "$SANDBOX/bin"
    cat > "$SANDBOX/bin/fakeagy" <<'EOF'
#!/usr/bin/env bash
printf 'Gemini 3.5 Flash (High)\nClaude Opus 4.6 (Thinking)\n'
EOF
    chmod +x "$SANDBOX/bin/fakeagy"
    source "$SCRIPT"
    MODEL_CHECK_CONFIG="$SANDBOX/pa.yml"
    run check_cli_provider antigravity "$SANDBOX/bin/fakeagy" "$SANDBOX/bin/fakeagy"
    assert_success
    assert_output --partial "OK: model_tiers.antigravity.flash"
    assert_output --partial "OK: model_tiers.antigravity.advanced"
}

@test "check_cli_provider reports STALE for models missing from listing" {
    mkdir -p "$SANDBOX/bin"
    cat > "$SANDBOX/bin/fakeagy" <<'EOF'
#!/usr/bin/env bash
printf 'Gemini 9 Ultra\n'
EOF
    chmod +x "$SANDBOX/bin/fakeagy"
    source "$SCRIPT"
    MODEL_CHECK_CONFIG="$SANDBOX/pa.yml"
    run check_cli_provider antigravity "$SANDBOX/bin/fakeagy" "$SANDBOX/bin/fakeagy"
    assert_success
    assert_output --partial "STALE: model_tiers.antigravity.flash = Gemini 3.5 Flash (High) not in provider listing"
}

@test "check_cli_provider skips when binary is missing" {
    source "$SCRIPT"
    MODEL_CHECK_CONFIG="$SANDBOX/pa.yml"
    run check_cli_provider antigravity "$SANDBOX/bin/nope" "$SANDBOX/bin/nope"
    assert_success
    assert_output --partial "SKIPPED: antigravity"
}

@test "check_api_provider skips without credentials" {
    source "$SCRIPT"
    MODEL_CHECK_CONFIG="$SANDBOX/pa.yml"
    ANTHROPIC_API_KEY="" run check_api_provider claude
    assert_success
    assert_output --partial "SKIPPED: claude (no credentials)"
}

# ---------------------------------------------------------------------------
# Probe mode (MODEL_CHECK_PROBE=1): live one-shot CLI probe per pin when no
# API key is available — closes the OAuth-only false-green blind spot.
# ---------------------------------------------------------------------------

setup_probe_config() {
    cat > "$SANDBOX/probe.yml" <<'YAML'
model_tiers:
  gemini:
    flash: "gemini-3-flash-preview"
  claude:
    sonnet: "claude-sonnet-4-6"
YAML
}

@test "probe disabled by default: no-credentials skip is unchanged" {
    setup_probe_config
    source "$SCRIPT"
    MODEL_CHECK_CONFIG="$SANDBOX/probe.yml"
    ANTHROPIC_API_KEY="" run check_api_provider claude
    assert_success
    assert_output --partial "SKIPPED: claude (no credentials)"
    refute_output --partial "OK:"
}

@test "probe mode reports OK when the CLI answers for the pinned model" {
    setup_probe_config
    mkdir -p "$SANDBOX/bin"
    cat > "$SANDBOX/bin/fakegemini" <<'FAKE'
#!/usr/bin/env bash
echo "OK"
exit 0
FAKE
    chmod +x "$SANDBOX/bin/fakegemini"
    source "$SCRIPT"
    MODEL_CHECK_CONFIG="$SANDBOX/probe.yml"
    GOOGLE_API_KEY="" MODEL_CHECK_PROBE=1 \
        MODEL_CHECK_GEMINI_BIN="$SANDBOX/bin/fakegemini" \
        run check_api_provider gemini
    assert_success
    assert_output --partial "OK: model_tiers.gemini.flash = gemini-3-flash-preview"
}

@test "probe mode reports STALE on model-not-found error" {
    setup_probe_config
    mkdir -p "$SANDBOX/bin"
    cat > "$SANDBOX/bin/fakegemini" <<'FAKE'
#!/usr/bin/env bash
echo "ModelNotFoundError: Requested entity was not found." >&2
echo "  code: 404" >&2
exit 1
FAKE
    chmod +x "$SANDBOX/bin/fakegemini"
    source "$SCRIPT"
    MODEL_CHECK_CONFIG="$SANDBOX/probe.yml"
    GOOGLE_API_KEY="" MODEL_CHECK_PROBE=1 \
        MODEL_CHECK_GEMINI_BIN="$SANDBOX/bin/fakegemini" \
        run check_api_provider gemini
    assert_success
    assert_output --partial "STALE: model_tiers.gemini.flash = gemini-3-flash-preview"
}

@test "probe mode reports STALE on claude bad-model error" {
    setup_probe_config
    mkdir -p "$SANDBOX/bin"
    cat > "$SANDBOX/bin/fakeclaude" <<'FAKE'
#!/usr/bin/env bash
echo "There's an issue with the selected model (claude-sonnet-4-6). It may not exist or you may not have access to it."
exit 1
FAKE
    chmod +x "$SANDBOX/bin/fakeclaude"
    source "$SCRIPT"
    MODEL_CHECK_CONFIG="$SANDBOX/probe.yml"
    ANTHROPIC_API_KEY="" MODEL_CHECK_PROBE=1 \
        MODEL_CHECK_CLAUDE_BIN="$SANDBOX/bin/fakeclaude" \
        run check_api_provider claude
    assert_success
    assert_output --partial "STALE: model_tiers.claude.sonnet = claude-sonnet-4-6"
}

@test "probe mode degrades to SKIPPED on unclassifiable CLI failure" {
    setup_probe_config
    mkdir -p "$SANDBOX/bin"
    cat > "$SANDBOX/bin/fakegemini" <<'FAKE'
#!/usr/bin/env bash
echo "network unreachable" >&2
exit 7
FAKE
    chmod +x "$SANDBOX/bin/fakegemini"
    source "$SCRIPT"
    MODEL_CHECK_CONFIG="$SANDBOX/probe.yml"
    GOOGLE_API_KEY="" MODEL_CHECK_PROBE=1 \
        MODEL_CHECK_GEMINI_BIN="$SANDBOX/bin/fakegemini" \
        run check_api_provider gemini
    assert_success
    assert_output --partial "SKIPPED: model_tiers.gemini.flash (probe failed)"
}

@test "probe mode skips provider when CLI binary is missing" {
    setup_probe_config
    source "$SCRIPT"
    MODEL_CHECK_CONFIG="$SANDBOX/probe.yml"
    GOOGLE_API_KEY="" MODEL_CHECK_PROBE=1 \
        MODEL_CHECK_GEMINI_BIN="$SANDBOX/bin/no-such-cli" \
        run check_api_provider gemini
    assert_success
    assert_output --partial "SKIPPED: gemini (no credentials"
}

@test "probe mode probes EVERY pin even when the CLI reads stdin" {
    # A CLI that drains stdin would swallow the read-loop's remaining input,
    # silently probing only the first pin (live bug found 2026-06-11).
    cat > "$SANDBOX/multi.yml" <<'YAML'
model_tiers:
  gemini:
    flash: "gemini-3-flash-preview"
    pro: "gemini-3-pro-preview"
YAML
    mkdir -p "$SANDBOX/bin"
    cat > "$SANDBOX/bin/fakegemini" <<'FAKE'
#!/usr/bin/env bash
cat > /dev/null   # drain stdin like real agent CLIs do
echo "OK"
FAKE
    chmod +x "$SANDBOX/bin/fakegemini"
    source "$SCRIPT"
    MODEL_CHECK_CONFIG="$SANDBOX/multi.yml"
    GOOGLE_API_KEY="" MODEL_CHECK_PROBE=1 \
        MODEL_CHECK_GEMINI_BIN="$SANDBOX/bin/fakegemini" \
        run check_api_provider gemini
    assert_success
    assert_output --partial "OK: model_tiers.gemini.flash"
    assert_output --partial "OK: model_tiers.gemini.pro"
}

# ---------------------------------------------------------------------------
# Antigravity probe fallback (G3): `agy models` needs a login, so
# check_cli_provider must fall back to a live per-pin probe (MODEL_CHECK_PROBE=1)
# instead of permanent SKIPPED — using a fake agy stub, no live binary.
# ---------------------------------------------------------------------------

setup_agy_stub() {
    # $1: models-subcommand behavior script body appended after the dispatch;
    # writes $SANDBOX/bin/fakeagy which fails `agy models` (not logged in) and
    # answers the probe shape `agy --model <m> -p <prompt>` per $1's exit/output.
    mkdir -p "$SANDBOX/bin"
    cat > "$SANDBOX/bin/fakeagy" <<EOF
#!/usr/bin/env bash
if [[ "\$1" == "models" ]]; then
    echo "not logged in" >&2
    exit 1
fi
$1
EOF
    chmod +x "$SANDBOX/bin/fakeagy"
}

@test "check_cli_provider falls back to live probe when agy models listing fails" {
    setup_agy_stub 'echo "OK"; exit 0'
    source "$SCRIPT"
    MODEL_CHECK_CONFIG="$SANDBOX/pa.yml"
    MODEL_CHECK_PROBE=1 run check_cli_provider antigravity "$SANDBOX/bin/fakeagy" "$SANDBOX/bin/fakeagy" models
    assert_success
    assert_output --partial "OK: model_tiers.antigravity.flash"
    assert_output --partial "OK: model_tiers.antigravity.advanced"
}

@test "check_cli_provider probe fallback reports STALE on unserved model" {
    setup_agy_stub 'echo "There'"'"'s an issue with the selected model. It may not exist."; exit 1'
    source "$SCRIPT"
    MODEL_CHECK_CONFIG="$SANDBOX/pa.yml"
    MODEL_CHECK_PROBE=1 run check_cli_provider antigravity "$SANDBOX/bin/fakeagy" "$SANDBOX/bin/fakeagy" models
    assert_success
    assert_output --partial "STALE: model_tiers.antigravity.flash"
    assert_output --partial "STALE: model_tiers.antigravity.advanced"
}

@test "check_cli_provider stays SKIPPED (model listing failed) when probe is disabled" {
    setup_agy_stub 'echo "OK"; exit 0'
    source "$SCRIPT"
    MODEL_CHECK_CONFIG="$SANDBOX/pa.yml"
    run check_cli_provider antigravity "$SANDBOX/bin/fakeagy" "$SANDBOX/bin/fakeagy" models
    assert_success
    assert_output --partial "SKIPPED: antigravity (model listing failed)"
    refute_output --partial "OK:"
}

@test "cursor listing failure now falls back to a per-pin probe, not 'no probe shape'" {
    # Inverts the previous assertion on purpose: cursor gained a probe shape, so
    # a failed listing must reach probe_pins and report PER PIN. An auth-shaped
    # failure is not evidence about model identity, so it degrades to SKIPPED
    # rather than STALE.
    cat > "$SANDBOX/cursor.yml" <<'YAML'
model_tiers:
  cursor:
    flash: "cursor-fast"
YAML
    mkdir -p "$SANDBOX/bin"
    cat > "$SANDBOX/bin/fakecursor" <<'FAKE'
#!/usr/bin/env bash
echo "unauthorized" >&2
exit 1
FAKE
    chmod +x "$SANDBOX/bin/fakecursor"
    source "$SCRIPT"
    MODEL_CHECK_CONFIG="$SANDBOX/cursor.yml"
    MODEL_CHECK_PROBE=1 run check_cli_provider cursor "$SANDBOX/bin/fakecursor" \
        "$SANDBOX/bin/fakecursor" --list-models
    assert_success
    assert_output --partial "SKIPPED: model_tiers.cursor.flash (probe failed)"
    refute_output --partial "no probe shape"
}

@test "cursor 'Cannot use this model' classifies as STALE, not SKIPPED" {
    # cursor-agent's real wording for a dead pin (measured 2026-07-29). Before
    # this pattern existed the pin read as "couldn't check", hiding a broken
    # pin behind the same label as a transient auth failure.
    cat > "$SANDBOX/cursor.yml" <<'YAML'
model_tiers:
  cursor:
    flash: "retired-model"
YAML
    mkdir -p "$SANDBOX/bin"
    cat > "$SANDBOX/bin/fakecursor" <<'FAKE'
#!/usr/bin/env bash
echo "Cannot use this model: retired-model. Available models: auto, composer-2.5" >&2
exit 1
FAKE
    chmod +x "$SANDBOX/bin/fakecursor"
    source "$SCRIPT"
    MODEL_CHECK_CONFIG="$SANDBOX/cursor.yml"
    MODEL_CHECK_PROBE=1 run probe_pins cursor "$SANDBOX/bin/fakecursor"
    assert_success
    assert_output --partial "STALE: model_tiers.cursor.flash = retired-model not served (live probe)"
    refute_output --partial "probe failed"
}

@test "devin is never probed: a probe would start an interactive login" {
    # devin -p on a logged-out machine launches a login flow instead of failing,
    # so probe_pins must refuse devin outright rather than call it.
    cat > "$SANDBOX/devin.yml" <<'YAML'
model_tiers:
  devin:
    advanced: "some-devin-model"
YAML
    mkdir -p "$SANDBOX/bin"
    # Fails the test loudly if it is ever executed.
    cat > "$SANDBOX/bin/fakedevin" <<'FAKE'
#!/usr/bin/env bash
echo "DEVIN-WAS-INVOKED" >&2
exit 1
FAKE
    chmod +x "$SANDBOX/bin/fakedevin"
    source "$SCRIPT"
    MODEL_CHECK_CONFIG="$SANDBOX/devin.yml"
    MODEL_CHECK_PROBE=1 run probe_pins devin "$SANDBOX/bin/fakedevin"
    assert_success
    assert_output --partial "no probe — devin -p starts an interactive login"
    refute_output --partial "DEVIN-WAS-INVOKED"
}

@test "check_devin reports the unpinned-by-design state instead of staying silent" {
    # devin ships no model_tiers block; a provider missing from the report reads
    # as "checked and fine" in the check_status.sh summary. SKIPPED (not a new
    # label) because check_status.sh only counts OK/STALE/SKIPPED/UNSUPPORTED.
    cat > "$SANDBOX/nodevin.yml" <<'YAML'
model_tiers:
  claude:
    opus: "claude-opus-5"
YAML
    source "$SCRIPT"
    MODEL_CHECK_CONFIG="$SANDBOX/nodevin.yml" run check_devin
    assert_success
    assert_output --partial "SKIPPED: devin (unpinned by design"
}
