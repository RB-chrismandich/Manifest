#!/usr/bin/env bash
# model_check.sh — warn-only staleness check of model_tiers pins against live
# provider listings. Never blocks: every failure degrades to SKIPPED and the
# exit code is always 0. Invoked by check_status.sh and /health-check.
#
# Report lines: OK / STALE / SKIPPED / UNSUPPORTED
# Usage: model_check.sh
#   env: MODEL_CHECK_CONFIG overrides the config path
#        MODEL_CHECK_PROBE=1 enables live one-shot CLI probes for claude/gemini
#        when no API key is set (OAuth-only machines) — one tiny LLM call per pin
#        MODEL_CHECK_CLAUDE_BIN / MODEL_CHECK_GEMINI_BIN override probe binaries
set -uo pipefail

MODEL_CHECK_CONFIG="${MODEL_CHECK_CONFIG:-$HOME/.claude/config/parallel_agent.yml}"

# list_tiers PROVIDER -> "tier<TAB>model" lines from model_tiers.<provider>
list_tiers() {
    local provider="$1"
    [[ -f "$MODEL_CHECK_CONFIG" ]] || return 0
    python3 - "$MODEL_CHECK_CONFIG" "$provider" 2>/dev/null <<'PY' || true
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
    if ! command -v "$binary" >/dev/null 2>&1; then
        echo "SKIPPED: $provider ($binary not installed)"
        return 0
    fi
    local listing
    if ! listing="$("$@" 2>/dev/null)"; then
        echo "SKIPPED: $provider (model listing failed)"
        return 0
    fi
    local tier model
    while IFS=$'\t' read -r tier model; do
        [[ -z "${model:-}" ]] && continue
        if grep -qiF "$model" <<<"$listing"; then
            echo "OK: model_tiers.$provider.$tier = $model"
        else
            echo "STALE: model_tiers.$provider.$tier = $model not in provider listing"
        fi
    done < <(list_tiers "$provider")
}

# probe_pins PROVIDER BINARY -> per-pin OK/STALE/SKIPPED via a live one-shot
# CLI call. Used when no API key is available but the OAuth-authenticated CLI
# is — without this, broken pins read as green on OAuth-only machines.
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
            *)
                echo "SKIPPED: $provider (no probe shape)"
                return 0
                ;;
        esac
        rc=$?
        if [[ $rc -eq 0 ]]; then
            echo "OK: model_tiers.$provider.$tier = $model"
        elif grep -qiE "modelnotfounderror|code: 404|not found|issue with the selected model" <<< "$out"; then
            echo "STALE: model_tiers.$provider.$tier = $model not served (live probe)"
        else
            echo "SKIPPED: model_tiers.$provider.$tier (probe failed)"
        fi
    done < <(list_tiers "$provider")
}

# maybe_probe PROVIDER BINARY -> 0 if the probe handled the provider
maybe_probe() {
    local provider="$1" binary="$2"
    if [[ "${MODEL_CHECK_PROBE:-0}" == "1" ]] && command -v "$binary" >/dev/null 2>&1; then
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
                maybe_probe claude "${MODEL_CHECK_CLAUDE_BIN:-claude}" \
                    || echo "SKIPPED: claude (no credentials)"
                return 0
            fi
            listing="$(curl -sf --connect-timeout 5 --max-time 10 https://api.anthropic.com/v1/models \
                -H "x-api-key: $ANTHROPIC_API_KEY" \
                -H "anthropic-version: 2023-06-01" 2>/dev/null)" || {
                echo "SKIPPED: claude (models endpoint unreachable)"
                return 0
            }
            ;;
        gemini)
            if [[ -z "${GOOGLE_API_KEY:-}" ]]; then
                maybe_probe gemini "${MODEL_CHECK_GEMINI_BIN:-gemini}" \
                    || echo "SKIPPED: gemini (no credentials)"
                return 0
            fi
            listing="$(curl -sf --connect-timeout 5 --max-time 10 \
                "https://generativelanguage.googleapis.com/v1beta/models?key=$GOOGLE_API_KEY" 2>/dev/null)" || {
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
        if grep -qiF "$model" <<<"$listing"; then
            echo "OK: model_tiers.$provider.$tier = $model"
        else
            echo "STALE: model_tiers.$provider.$tier = $model not in provider listing"
        fi
    done < <(list_tiers "$provider")
}

main() {
    check_api_provider claude
    check_api_provider gemini
    check_cli_provider antigravity agy agy models
    # cursor-agent --list-models needs auth; check_cli_provider degrades to
    # SKIPPED when unauthenticated, OK/STALE per tier when logged in.
    check_cli_provider cursor cursor-agent cursor-agent --list-models
    # Codex CLI exposes no model-listing command (revisit when it grows one).
    echo "UNSUPPORTED: codex (no listing command)"
    exit 0
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
