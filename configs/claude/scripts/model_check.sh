#!/usr/bin/env bash
# model_check.sh — warn-only staleness check of model_tiers pins against live
# provider listings. Never blocks: every failure degrades to SKIPPED and the
# exit code is always 0. Invoked by check_status.sh and /env-check.
#
# Report lines: OK / STALE / SKIPPED / UNSUPPORTED — these four exactly. Do not
# add a fifth: check_status.sh cases on this vocabulary and silently drops
# anything else, which turns an unchecked pin into a green line.
# Usage: model_check.sh
#   env: MODEL_CHECK_CONFIG overrides the config path
#        MODEL_CHECK_PROBE=1 enables live one-shot CLI probes — one tiny LLM call
#        per pin — for claude/gemini (when no API key is set: OAuth-only
#        machines), antigravity (when `agy models` fails, e.g. not logged in),
#        cursor, and codex (which has no listing command at all, so a probe is
#        the ONLY way to verify its pins). devin is deliberately never probed:
#        `devin -p` starts an interactive login when logged out.
#        MODEL_CHECK_CLAUDE_BIN / MODEL_CHECK_GEMINI_BIN override probe binaries
set -uo pipefail

# --help before any config read or provider probe: it must succeed in a clean
# environment (empty HOME, no CLIs, no credentials), so it cannot depend on
# anything the checks below look up.
if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    cat << 'EOF'
Usage: model_check.sh

Warn-only staleness check of model_tiers pins against live provider listings.
Always exits 0; every failure degrades to a SKIPPED report line.

Report lines: OK / STALE / SKIPPED / UNSUPPORTED

Environment:
  MODEL_CHECK_CONFIG          config path (default ~/.claude/config/parallel_agent.yml)
  MODEL_CHECK_PROBE=1         live one-shot CLI probes (claude, gemini, antigravity,
                              cursor, codex) — one tiny LLM call per pin. Required to
                              verify codex at all: it has no listing command. Never
                              probes devin (`devin -p` starts an interactive login).
  MODEL_CHECK_CLAUDE_BIN      override the claude probe binary
  MODEL_CHECK_GEMINI_BIN      override the gemini probe binary
EOF
    exit 0
fi

MODEL_CHECK_CONFIG="${MODEL_CHECK_CONFIG:-$HOME/.claude/config/parallel_agent.yml}"

# list_tiers PROVIDER -> "tier<TAB>model" lines from model_tiers.<provider>
list_tiers() {
    local provider="$1"
    [[ -f "$MODEL_CHECK_CONFIG" ]] || return 0
    python3 - "$MODEL_CHECK_CONFIG" "$provider" 2> /dev/null << 'PY' || true
import sys

import yaml

try:
    with open(sys.argv[1]) as f:
        cfg = yaml.safe_load(f) or {}
    tiers = (cfg.get("model_tiers") or {}).get(sys.argv[2]) or {}
    for tier, model in tiers.items():
        print(f"{tier}\t{model}")
except Exception:
    pass
PY
}

# check_cli_provider PROVIDER BINARY LIST_CMD... -> report lines
check_cli_provider() {
    local provider="$1" binary="$2"
    shift 2
    if ! command -v "$binary" > /dev/null 2>&1; then
        echo "SKIPPED: $provider ($binary not installed)"
        return 0
    fi
    local listing
    if ! listing="$("$@" 2> /dev/null)"; then
        # Listing failed (e.g. agy not logged in) — fall back to a live
        # one-shot probe per pin when opted in, instead of a permanent SKIPPED.
        maybe_probe "$provider" "$binary" ||
            echo "SKIPPED: $provider (model listing failed)"
        return 0
    fi
    local tier model
    while IFS=$'\t' read -r tier model; do
        [[ -z "${model:-}" ]] && continue
        if grep -qiF "$model" <<< "$listing"; then
            echo "OK: model_tiers.$provider.$tier = $model"
        else
            echo "STALE: model_tiers.$provider.$tier = $model not in provider listing"
        fi
    done < <(list_tiers "$provider")
}

# probe_pins PROVIDER BINARY -> per-pin OK/STALE/SKIPPED via a live one-shot
# CLI call. Used when no API key is available but the OAuth-authenticated CLI
# is (claude/gemini), or when a CLI-only provider's model-listing command
# fails (antigravity: `agy models` needs a login) — without this, broken pins
# read as green (or permanently SKIPPED) on those machines.
# Opt-in (MODEL_CHECK_PROBE=1): each pin costs one tiny LLM call.
probe_pins() {
    local provider="$1" binary="$2"
    local tier model out rc
    while IFS=$'\t' read -r tier model; do
        [[ -z "${model:-}" ]] && continue
        # </dev/null: agent CLIs drain stdin, which would swallow the rest of
        # the read loop's pin list and silently probe only the first pin.
        case "$provider" in
            claude) out="$("$binary" --model "$model" -p "Reply with exactly: OK" 2>&1 < /dev/null)" ;;
            gemini) out="$("$binary" -m "$model" -p "Reply with exactly: OK" 2>&1 < /dev/null)" ;;
            antigravity) out="$("$binary" --model "$model" -p "Reply with exactly: OK" 2>&1 < /dev/null)" ;;
            # cursor-agent aborts with "Workspace Trust Required" in an
            # untrusted directory, so a bare probe always fails. --trust clears
            # that, but trusting whatever directory the operator happened to run
            # /env-check from is not this script's call to make — so the probe
            # runs inside a throwaway temp dir and trusts that instead. --mode
            # ask keeps it read-only on top (same flag the cli_agents spec uses).
            # The subshell self-cleans via its EXIT trap and yields the CLI's
            # own status, which the shared `rc=$?` below reads.
            cursor)
                out="$(
                    probe_dir="$(mktemp -d)" || exit 1
                    trap 'rm -rf "$probe_dir"' EXIT
                    cd "$probe_dir" || exit 1
                    "$binary" --print --output-format text --mode ask --trust \
                        --model "$model" "Reply with exactly: OK" 2>&1 < /dev/null
                )"
                ;;
            # No --full-auto: a staleness probe must never be able to execute
            # anything. --skip-git-repo-check is required or codex refuses with
            # "Not inside a trusted directory" before it ever validates a model.
            codex)
                out="$("$binary" exec --skip-git-repo-check --model "$model" \
                    "Reply with exactly: OK" 2>&1 < /dev/null)"
                ;;
            # devin is deliberately unprobed. Measured 2026-07-29: while logged
            # out, `devin --model X -p ...` does not return an error — it LAUNCHES
            # an interactive login ("Welcome to Devin CLI!" then "Error: Login
            # canceled"). A health check must never try to log the operator in or
            # block on a browser, so devin is verified by its listing only.
            devin)
                echo "SKIPPED: model_tiers.$provider.$tier (no probe — devin -p starts an interactive login)"
                continue
                ;;
            *)
                echo "SKIPPED: $provider (no probe shape)"
                return 0
                ;;
        esac
        rc=$?
        if [[ $rc -eq 0 ]]; then
            echo "OK: model_tiers.$provider.$tier = $model"
        # "cannot use this model" is cursor-agent's wording (measured
        # 2026-07-29: "Cannot use this model: X. Available models: ..."). Without
        # it a genuinely dead cursor pin classified as SKIPPED — "couldn't
        # check" — which is precisely the false-green this report exists to
        # avoid. Auth/limit failures still fall through to SKIPPED on purpose:
        # they say nothing about whether the model identity is valid.
        elif grep -qiE "modelnotfounderror|code: 404|not found|issue with the selected model|cannot use this model" <<< "$out"; then
            echo "STALE: model_tiers.$provider.$tier = $model not served (live probe)"
        else
            echo "SKIPPED: model_tiers.$provider.$tier (probe failed)"
        fi
    done < <(list_tiers "$provider")
}

# maybe_probe PROVIDER BINARY -> 0 if the probe handled the provider
maybe_probe() {
    local provider="$1" binary="$2"
    if [[ "${MODEL_CHECK_PROBE:-0}" == "1" ]] && command -v "$binary" > /dev/null 2>&1; then
        probe_pins "$provider" "$binary"
        return 0
    fi
    return 1
}

# check_api_provider PROVIDER -> report lines (claude|gemini), creds-gated
check_api_provider() {
    local provider="$1" listing=""
    case "$provider" in
        claude)
            if [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
                maybe_probe claude "${MODEL_CHECK_CLAUDE_BIN:-claude}" ||
                    echo "SKIPPED: claude (no credentials)"
                return 0
            fi
            listing="$(curl -sf --connect-timeout 5 --max-time 10 https://api.anthropic.com/v1/models \
                -H "x-api-key: $ANTHROPIC_API_KEY" \
                -H "anthropic-version: 2023-06-01" 2> /dev/null)" || {
                echo "SKIPPED: claude (models endpoint unreachable)"
                return 0
            }
            ;;
        gemini)
            if [[ -z "${GOOGLE_API_KEY:-}" ]]; then
                maybe_probe gemini "${MODEL_CHECK_GEMINI_BIN:-gemini}" ||
                    echo "SKIPPED: gemini (no credentials)"
                return 0
            fi
            listing="$(curl -sf --connect-timeout 5 --max-time 10 \
                "https://generativelanguage.googleapis.com/v1beta/models?key=$GOOGLE_API_KEY" 2> /dev/null)" || {
                echo "SKIPPED: gemini (models endpoint unreachable)"
                return 0
            }
            ;;
        *)
            echo "UNSUPPORTED: $provider (no listing source)"
            return 0
            ;;
    esac
    local tier model
    while IFS=$'\t' read -r tier model; do
        [[ -z "${model:-}" ]] && continue
        if grep -qiF "$model" <<< "$listing"; then
            echo "OK: model_tiers.$provider.$tier = $model"
        else
            echo "STALE: model_tiers.$provider.$tier = $model not in provider listing"
        fi
    done < <(list_tiers "$provider")
}

# check_devin -> report lines. devin ships no model_tiers block by design: its
# catalog is login-gated, so this repo cannot enumerate it and refuses to pin
# names it never saw printed. Say so explicitly rather than printing nothing —
# a provider absent from the report reads as "checked and fine" in the
# /env-check summary. Reported as SKIPPED, not a new label: check_status.sh
# cases on OK/STALE/SKIPPED/UNSUPPORTED and would drop a fifth word uncounted,
# which would turn an unchecked provider green. If someone does add pins later,
# they get scored like any other CLI provider.
check_devin() {
    if [[ -z "$(list_tiers devin)" ]]; then
        echo "SKIPPED: devin (unpinned by design — catalog is login-gated, --model passes through)"
        return 0
    fi
    check_cli_provider devin devin devin models list
}

main() {
    check_api_provider claude
    check_api_provider gemini
    check_cli_provider antigravity agy agy models
    # cursor-agent --list-models needs auth; check_cli_provider degrades to
    # SKIPPED when unauthenticated, OK/STALE per tier when logged in.
    check_cli_provider cursor cursor-agent cursor-agent --list-models
    # Codex CLI still exposes no model-listing command (re-tested 2026-07-29:
    # no `models`, `models list`, or `--list-models`), so there is nothing to
    # grep. Pins are verifiable only via MODEL_CHECK_PROBE=1, which now has a
    # codex shape. Revisit if the CLI grows a listing command.
    echo "UNSUPPORTED: codex (no listing command)"
    check_devin
    exit 0
}

# :- guards both names: this script sets `set -u`, and that applies to callers
# that `source` it (the bats suite and check_status.sh do), where BASH_SOURCE
# can be unset and would abort with "parameter not set" instead of just
# declining to run main.
if [[ "${BASH_SOURCE[0]:-}" == "${0:-}" ]]; then
    main "$@"
fi
