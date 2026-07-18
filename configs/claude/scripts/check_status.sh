#!/bin/bash
# Parallel Agent Orchestration Readiness Check
# Usage: ./check_status.sh [--verbose]
#
# Scope: services.yml enabled agents, CLI availability, auth, Codex session
#        storage, and Manifest state directories.  Reports whether the system
#        has enough agents ready for parallel orchestration.
#
# Also invoked by: parallel_agent.py --status
#
# For full environment audit (MCP, symlinks, config syntax, labels):
#   use the /env-check skill in Claude Code.

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    cat << 'USAGE'
Usage: check_status.sh [--verbose]

Parallel-agent orchestration readiness check: services.yml enabled agents,
CLI availability, auth, and Manifest state directories.

  --verbose   Also print CLI locations and versions

Full environment audit (MCP, symlinks, config syntax): /env-check skill.
USAGE
    exit 0
fi

VERBOSE=false
if [[ "${1:-}" == "--verbose" ]]; then
    VERBOSE=true
fi

# Detect timeout command (timeout on Linux, gtimeout on macOS via coreutils);
# a bare `timeout` made auth checks always fail on stock macOS (issue #315).
# CHECK_STATUS_NO_TIMEOUT_CMD=1 forces the pure-bash fallback below (tests use
# this to exercise the no-coreutils path deterministically on any platform).
TIMEOUT_CMD=""
if [[ "${CHECK_STATUS_NO_TIMEOUT_CMD:-}" != "1" ]]; then
    if command -v timeout &> /dev/null; then
        TIMEOUT_CMD="timeout"
    elif command -v gtimeout &> /dev/null; then
        TIMEOUT_CMD="gtimeout"
    fi
fi

# Recursively SIGKILL a process and all its descendants. A bare `kill $pid`
# leaves grandchildren orphaned (e.g. the CLI's `node` workers), and an orphan
# that still holds the script's stdout pipe blocks any caller capturing our
# output — re-introducing the very stall we are bounding. Kill children first
# so we don't reparent them to init before we can find them.
kill_tree() {
    local pid="$1" child
    for child in $(pgrep -P "$pid" 2> /dev/null); do
        kill_tree "$child"
    done
    kill -9 "$pid" 2> /dev/null
}

# Run a command bounded by 3s. Prefer timeout(1)/gtimeout(1); otherwise fall
# back to a pure-bash watchdog so a slow CLI (e.g. `gemini auth status`, ~60s)
# can't stall the readiness check on machines without GNU coreutils — without
# this the whole check took ~196s on stock macOS.
run_with_timeout() {
    local secs=3
    if [[ -n "$TIMEOUT_CMD" ]]; then
        "$TIMEOUT_CMD" "$secs" "$@"
        return $?
    fi
    "$@" &
    local cmd_pid=$!
    {
        sleep "$secs"
        kill_tree "$cmd_pid"
    } &
    local watcher_pid=$!
    wait "$cmd_pid" 2> /dev/null
    local rc=$?
    # command finished first: cancel the watchdog so it doesn't linger
    kill_tree "$watcher_pid" 2> /dev/null
    wait "$watcher_pid" 2> /dev/null
    return "$rc"
}

# --- agent_roster.yml (Task 26): single enumeration of the 5(+)-agent
# fleet, consumed by the Enabled Services and CLI Tools loops below, plus
# the claude/cursor Authentication checks (whose auth_check is a single
# command). gemini/codex/antigravity keep their bespoke multi-condition
# auth logic (see comments at each block) -- the registry's auth_check
# field only has room for one command, not their richer detection.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# cap_name NAME -> NAME with its first letter uppercased (claude -> Claude).
# All roster agent names are lowercase single words, so this simple scheme
# reproduces the historical hardcoded display labels exactly.
cap_name() {
    local n="$1"
    printf '%s%s' "$(tr '[:lower:]' '[:upper:]' <<< "${n:0:1}")" "${n:1}"
}

# resolve_agent_roster_path -> the agent_roster.yml to read.
# MANIFEST_AGENT_ROSTER (test fixtures; mirrors reconcile_core.py's env var
# of the same name -- see tests/python/test_reconcile_policy.py) takes
# precedence, then the deployed home copy, then the repo-relative sibling of
# this script -- so check_status.sh works both post-bootstrap (~/.claude)
# and run directly from a checkout with no ~/.claude yet (e.g. this repo's
# own bats sandbox, which redirects HOME but not this script's own location).
resolve_agent_roster_path() {
    if [[ -n "${MANIFEST_AGENT_ROSTER:-}" ]]; then
        echo "$MANIFEST_AGENT_ROSTER"
    elif [[ -f "$HOME/.claude/config/agent_roster.yml" ]]; then
        echo "$HOME/.claude/config/agent_roster.yml"
    else
        echo "$SCRIPT_DIR/../config/agent_roster.yml"
    fi
}

# load_agent_roster_tsv -> "name<TAB>binary<TAB>auth_check" lines, one per
# agent, in the registry's declaration order. Missing/malformed registry
# yields no lines -- mirrors agents/config.py's load_agent_roster (the
# roster is an optional extensibility source, never a hard dependency).
#
# Primary parse is python3 + PyYAML (this codebase's established idiom for a
# bash script reading YAML, e.g. model_check.sh). If that yields nothing --
# no python3, or a python3 without the yaml module (observed: stock macOS
# /usr/bin/python3 has no PyYAML) -- fall back to a PyYAML-free awk parser,
# mirroring reconcile_core.py's own documented fallback for this exact file
# ("avoid a hard yaml runtime dependency").
load_agent_roster_tsv() {
    local roster_path out
    roster_path="$(resolve_agent_roster_path)"
    [[ -f "$roster_path" ]] || return 0

    out="$(python3 - "$roster_path" 2> /dev/null << 'PY'
import sys

import yaml

try:
    with open(sys.argv[1]) as f:
        data = yaml.safe_load(f) or {}
    agents = data.get("agents") or {}
    for name, entry in agents.items():
        if not isinstance(entry, dict):
            continue
        print(f"{name}\t{entry.get('binary', '')}\t{entry.get('auth_check', '')}")
except Exception:
    pass
PY
    )"
    if [[ -n "$out" ]]; then
        printf '%s\n' "$out"
        return 0
    fi

    load_agent_roster_tsv_fallback "$roster_path"
}

# load_agent_roster_tsv_fallback ROSTER_PATH -> same TSV shape as above,
# hand-parsed with awk against agent_roster.yml's fixed indentation (2-space
# agent-name headers, 4-space fields) -- no PyYAML required.
load_agent_roster_tsv_fallback() {
    awk '
        /^agents:[[:space:]]*$/ { in_agents = 1; next }
        in_agents && /^[^[:space:]]/ { in_agents = 0 }
        in_agents && /^  [A-Za-z0-9_-]+:[[:space:]]*$/ {
            if (name != "") { print name "\t" binary "\t" auth }
            line = $0
            sub(/^  /, "", line)
            sub(/:[[:space:]]*$/, "", line)
            name = line
            binary = ""
            auth = ""
            next
        }
        in_agents && /^    binary:/ {
            val = $0
            sub(/^    binary:[[:space:]]*/, "", val)
            gsub(/^"|"$/, "", val)
            binary = val
            next
        }
        in_agents && /^    auth_check:/ {
            val = $0
            sub(/^    auth_check:[[:space:]]*/, "", val)
            gsub(/^"|"$/, "", val)
            auth = val
            next
        }
        END { if (name != "") print name "\t" binary "\t" auth }
    ' "$1"
}

# Roster storage uses parallel indexed arrays, not associative arrays --
# this file (like branch_clean.sh, pr_review.sh, version_pin.sh) targets
# bash 3.2 (stock macOS /bin/bash), which has no `declare -A`.
declare -a ROSTER_NAMES=()
declare -a ROSTER_BINARIES=()
declare -a ROSTER_AUTH_CHECKS=()
while IFS=$'\t' read -r r_name r_binary r_auth; do
    [[ -z "$r_name" ]] && continue
    ROSTER_NAMES+=("$r_name")
    ROSTER_BINARIES+=("$r_binary")
    ROSTER_AUTH_CHECKS+=("$r_auth")
done < <(load_agent_roster_tsv)

# Third tier: both the python3+PyYAML parse AND the awk fallback above produced
# nothing -- missing/corrupted agent_roster.yml, or a bad MANIFEST_AGENT_ROSTER
# override pointing nowhere. Before agent_roster.yml existed (Task 26) this
# script always reported the true state of these 5 hardcoded agents regardless
# of any file being present; without this tier a totally-unreadable roster
# silently collapses to "Enabled Services (0/0)" / "System not operational" even
# when services.yml has real agents enabled -- a regression, not the intended
# failure mode. Mirrors reconcile_core.py's load_fleet_tags() _DEFAULT_ROOT_TAGS
# fallback for this same file. Values match the *) case-dispatch defaults in
# agent_installed_msg/agent_not_installed_msg/agent_install_hint below and
# agent_roster.yml's own committed content -- one source of truth, not a
# fourth independent set of values.
if [[ ${#ROSTER_NAMES[@]} -eq 0 ]]; then
    ROSTER_NAMES=(claude gemini cursor codex antigravity)
    ROSTER_BINARIES=(claude gemini cursor-agent codex agy)
    ROSTER_AUTH_CHECKS=("claude auth status" "gemini auth status" "cursor-agent --version" "codex login status" "agy models")
fi

# roster_binary/roster_auth_check NAME -> field for NAME (empty if not
# found). Linear scan over the parallel arrays above (bash 3.2-safe).
roster_binary() {
    local target="$1" i
    for ((i = 0; i < ${#ROSTER_NAMES[@]}; i++)); do
        if [[ "${ROSTER_NAMES[i]}" == "$target" ]]; then
            echo "${ROSTER_BINARIES[i]}"
            return 0
        fi
    done
}

roster_auth_check() {
    local target="$1" i
    for ((i = 0; i < ${#ROSTER_NAMES[@]}; i++)); do
        if [[ "${ROSTER_NAMES[i]}" == "$target" ]]; then
            echo "${ROSTER_AUTH_CHECKS[i]}"
            return 0
        fi
    done
}

# Static declarations for the 5 known agents' enabled/installed flags.
# The roster loops below assign these dynamically by sanitized name
# (printf -v "${name//-/_}_installed" ...  -- bash identifiers cannot
# contain '-', so a hyphenated roster name like "test-agent" is mangled to
# "test_agent" for the variable only, mirroring agents/cli.py's _dest()
# name-mangling) so shellcheck (SC2154) cannot trace the assignment;
# declaring them here also keeps every later reference (codex_runtime_ready,
# working_agents, ...) safe if a known agent were ever absent from the
# registry. The 5 names below are all already valid identifiers, so the
# sanitization is a no-op for them.
claude_installed=false
gemini_installed=false
cursor_installed=false
codex_installed=false
antigravity_installed=false
claude_enabled=""
gemini_enabled=""
cursor_enabled=""
codex_enabled=""
antigravity_enabled=""

manifest_state_root="${MANIFEST_STATE_ROOT:-$HOME/.manifest}"
manifest_tmp_dir="${MANIFEST_TMP_DIR:-$manifest_state_root/tmp}"
claude_state_dir="${CLAUDE_STATE_DIR:-$manifest_state_root/claude}"
gemini_state_dir="${GEMINI_STATE_DIR:-$manifest_state_root/gemini}"
cursor_state_dir="${CURSOR_STATE_DIR:-$manifest_state_root/cursor}"
codex_state_dir="${CODEX_STATE_DIR:-${CODEX_HOME:-$manifest_state_root/codex}}"
export CODEX_HOME="${CODEX_HOME:-$codex_state_dir}"
antigravity_state_dir="${ANTIGRAVITY_STATE_DIR:-$manifest_state_root/antigravity}"

echo -e "${BOLD}${BLUE}═══════════════════════════════════════════════════════${NC}"
echo -e "${BOLD}${BLUE}  Parallel Agent System Health Check${NC}"
echo -e "${BOLD}${BLUE}═══════════════════════════════════════════════════════${NC}"
echo ""

# Check if services.yml exists
echo -e "${BOLD}Configuration:${NC}"
if [[ -f ~/.claude/config/services.yml ]]; then
    echo -e "  ${GREEN}✓${NC} services.yml found"

    # Parse enabled services using grep (more portable than yq), one agent
    # per ROSTER_NAMES entry (agent_roster.yml-derived; Task 26) -- a new
    # agent needs only a registry entry + a services.yml block, no script edit.
    for r_name in "${ROSTER_NAMES[@]}"; do
        r_val=$(grep -A1 "^  ${r_name}:" ~/.claude/config/services.yml | grep "enabled:" | awk '{print $2}')
        # Bash identifiers cannot contain '-' (e.g. a roster agent named
        # "test-agent" would make printf -v reject "test-agent_enabled" as
        # "not a valid identifier"); sanitize to the bash-3.2-safe
        # ${var//-/_} form for the identifier only -- the ungrepped
        # $r_name above still targets the real services.yml key.
        printf -v "${r_name//-/_}_enabled" '%s' "$r_val"
    done
    # graphify is a managed TOOL, not a parallel-orchestration agent (it is reported
    # separately under CLI Tools and excluded from the agent count / working_agents)
    # -- and it is not a fleet agent in agent_roster.yml, so it stays a standalone lookup.
    graphify_enabled=$(grep -A1 "^  graphify:" ~/.claude/config/services.yml | grep "enabled:" | awk '{print $2}')

    enabled_count=0
    for r_name in "${ROSTER_NAMES[@]}"; do
        r_var="${r_name//-/_}_enabled"
        [[ "${!r_var}" == "true" ]] && enabled_count=$((enabled_count + 1))
    done

    echo ""
    echo -e "${BOLD}Enabled Services (${enabled_count}/${#ROSTER_NAMES[@]}):${NC}"

    for r_name in "${ROSTER_NAMES[@]}"; do
        r_var="${r_name//-/_}_enabled"
        r_label="$(cap_name "$r_name")"
        if [[ "${!r_var}" == "true" ]]; then
            echo -e "  ${GREEN}✓${NC} ${r_label}"
        else
            echo -e "  ${YELLOW}○${NC} ${r_label} (disabled)"
        fi
    done

    if [[ $enabled_count -lt 2 ]]; then
        echo ""
        echo -e "  ${YELLOW}⚠${NC}  Warning: Minimum 2 services needed for parallel orchestration"
        echo -e "  ${BLUE}→${NC} Fix: ./bootstrap.sh --reconfigure --enable-claude --enable-gemini --enable-codex"
    fi
else
    echo -e "  ${YELLOW}○${NC} services.yml not found"
    echo -e "  ${BLUE}→${NC} Run: ./bootstrap.sh"
fi

echo ""

# Check CLI installations
echo -e "${BOLD}CLI Tools:${NC}"

# Install hints and display messages are NOT part of agent_roster.yml's
# schema (binary/home_dir/prompt_args/model_args/auth_check/enabled_default)
# -- they are package-manager-specific / UX text, not fleet-membership
# facts, so they stay local here rather than growing the registry's schema.
# Same treatment as the per-agent quirk notes elsewhere in this file: the
# ENUMERATION (roster agent names + binaries) is single-sourced from
# agent_roster.yml; these display strings are not. `case` dispatch (not an
# associative array) to stay bash 3.2-safe, matching model_check.sh's
# per-provider `case` blocks.
agent_installed_msg() {
    case "$1" in
        claude) echo "Claude CLI installed" ;;
        gemini) echo "Gemini CLI installed" ;;
        cursor) echo "cursor-agent CLI available" ;;
        codex) echo "Codex CLI installed" ;;
        antigravity) echo "Antigravity CLI (agy) installed" ;;
        *) echo "$(cap_name "$1") CLI installed" ;;
    esac
}
agent_not_installed_msg() {
    case "$1" in
        claude) echo "Claude CLI not installed (optional)" ;;
        gemini) echo "Gemini CLI not installed (optional)" ;;
        cursor) echo "cursor-agent not available (optional)" ;;
        codex) echo "Codex CLI not installed" ;;
        antigravity) echo "Antigravity CLI (agy) not installed (optional)" ;;
        *) echo "$(cap_name "$1") CLI not installed (optional)" ;;
    esac
}
agent_install_hint() {
    case "$1" in
        claude) echo "npm install -g @anthropic-ai/claude-code" ;;
        gemini) echo "npm install -g @google/gemini-cli" ;;
        cursor) echo "curl https://cursor.com/install -fsS | bash" ;;
        codex) echo "npm install -g @openai/codex" ;;
        antigravity) echo "Install via the Antigravity IDE (agy install)" ;;
        *) echo "no install hint configured for $1" ;;
    esac
}
# claude/gemini/codex CLIs print a version banner; cursor-agent and agy
# (antigravity) do not today, so their verbose block omits the Version line
# -- preserved exactly from the pre-roster-loop behavior.
agent_shows_version() {
    case "$1" in
        claude | gemini | codex) return 0 ;;
        *) return 1 ;;
    esac
}

for r_name in "${ROSTER_NAMES[@]}"; do
    r_binary="$(roster_binary "$r_name")"
    if command -v "$r_binary" &> /dev/null; then
        echo -e "  ${GREEN}✓${NC} $(agent_installed_msg "$r_name")"
        # ${r_name//-/_}: see the "_enabled" assignment above -- same
        # identifier-safety requirement applies to "_installed".
        printf -v "${r_name//-/_}_installed" '%s' true
        if [[ "$VERBOSE" == true ]]; then
            echo -e "    Location: $(which "$r_binary")"
            if agent_shows_version "$r_name"; then
                echo -e "    Version:  $("$r_binary" --version 2> /dev/null || echo 'unknown')"
            fi
        fi
    else
        printf -v "${r_name//-/_}_installed" '%s' false
        echo -e "  ${YELLOW}○${NC} $(agent_not_installed_msg "$r_name")"
        if [[ "$VERBOSE" == true ]]; then
            echo -e "    ${BLUE}→${NC} Install: $(agent_install_hint "$r_name")"
        fi
    fi
done

# Graphify is a managed knowledge-graph tool, NOT a parallel-orchestration agent,
# so it is reported here but never counted toward orchestration readiness
# (no graphify_installed flag — it must not feed working_agents; spec 364 D4).
if [[ "$graphify_enabled" == "true" ]]; then
    if command -v graphify &> /dev/null; then
        echo -e "  ${GREEN}✓${NC} Graphify CLI installed"
        if [[ "$VERBOSE" == true ]]; then
            echo -e "    Location: $(which graphify)"
            echo -e "    Version:  $(graphify --version 2> /dev/null || echo 'unknown')"
            echo -e "    Backend:  host-agent (no API key required)"
        fi
    else
        echo -e "  ${YELLOW}○${NC} Graphify CLI not installed"
        if [[ "$VERBOSE" == true ]]; then
            echo -e "    ${BLUE}→${NC} Install: ./bootstrap.sh --enable-graphify  (uv tool install graphifyy)"
        fi
    fi
else
    echo -e "  ${YELLOW}○${NC} Graphify (disabled)"
fi

echo ""

# Check authentication
echo -e "${BOLD}Authentication:${NC}"

# claude and cursor's auth checks are a single non-interactive command with
# no extra condition, so they are driven directly by agent_roster.yml's
# auth_check field (Task 26). gemini/codex/antigravity need richer
# multi-source detection (env vars, credential files, and/or a fallback
# probe) that a single roster command cannot express, so they keep their
# bespoke logic below, unconverted -- an honest, documented schema
# limitation, not a bug to paper over.
for r_name in claude cursor; do
    r_var="${r_name//-/_}_installed"
    if [[ "${!r_var}" == true ]]; then
        r_auth_check="$(roster_auth_check "$r_name")"
        r_label="$(cap_name "$r_name")"
        # Split the roster's auth_check command string into argv (it is a
        # plain space-separated command, e.g. "claude auth status") --
        # avoids an unquoted word-split expansion (SC2086) below.
        read -ra r_auth_argv <<< "$r_auth_check"
        # Add timeout to avoid hanging
        if run_with_timeout "${r_auth_argv[@]}" &> /dev/null; then
            echo -e "  ${GREEN}✓${NC} ${r_label} authenticated"
        else
            echo -e "  ${YELLOW}⚠${NC}  ${r_label} authentication unknown (check timeout)"
            echo -e "    ${BLUE}→${NC} Verify: ${r_auth_check}"
        fi
    fi
done

# gemini: NOT roster-driven -- agent_roster.yml's auth_check is a single
# command ("gemini auth status"), but the real check here is a 3-way OR
# (env var(s) OR the OAuth creds file OR that command as a last-resort
# probe) that a single roster field cannot express.
if [[ "$gemini_installed" == true ]]; then
    # Prefer a fast credential check: `gemini auth status` has no real auth
    # subcommand and runs as a ~60s model call, so probe it only as a last
    # resort. An API key or the OAuth creds file is an immediate signal (same
    # file-presence heuristic as the Codex check above).
    if [[ -n "$GEMINI_API_KEY" || -n "$GOOGLE_API_KEY" || -f "$HOME/.gemini/oauth_creds.json" ]]; then
        echo -e "  ${GREEN}✓${NC} Gemini authenticated"
    elif run_with_timeout gemini auth status &> /dev/null; then
        echo -e "  ${GREEN}✓${NC} Gemini authenticated"
    else
        echo -e "  ${YELLOW}⚠${NC}  Gemini authentication unknown (check timeout)"
        echo -e "    ${BLUE}→${NC} Verify: gemini auth status"
    fi
fi

# codex: NOT roster-driven -- agent_roster.yml's auth_check is a single
# command ("codex login status"), but the real check here is env var OR
# either of two candidate auth.json paths OR that command, a 3-source OR a
# single roster field cannot express.
if [[ "$codex_installed" == true ]]; then
    if [[ -n "$OPENAI_API_KEY" ]] || [[ -f "$CODEX_HOME/auth.json" ]] || [[ -f "$HOME/.codex/auth.json" ]]; then
        echo -e "  ${GREEN}✓${NC} Codex authenticated"
    else
        echo -e "  ${YELLOW}⚠${NC}  Codex authentication unknown"
        echo -e "    ${BLUE}→${NC} Verify: codex login  (or set OPENAI_API_KEY)"
    fi
fi

# antigravity: NOT roster-driven -- agent_roster.yml's auth_check is a
# single command ("agy models"), which IS what runs below, but it is used
# as a bound-probe signal (no credentials-file heuristic exists for agy;
# see the ~/.gemini/config quirk note), which is a richer usage pattern
# than a plain success/failure roster-driven call.
if [[ "$antigravity_installed" == true ]]; then
    # agy has no predictable credentials-file heuristic (its config lives
    # under ~/.gemini/config, not ~/.antigravity — see G14); `agy models`
    # lists models only when logged in, so bound-probe it as the auth signal.
    if run_with_timeout agy models &> /dev/null; then
        echo -e "  ${GREEN}✓${NC} Antigravity authenticated"
    else
        echo -e "  ${YELLOW}?${NC} Antigravity authentication unknown (check timeout)"
        echo -e "    ${BLUE}→${NC} Verify: agy models  (launch the CLI/IDE to sign in)"
    fi
fi

codex_runtime_ready=true
if [[ "$codex_installed" == true && "$codex_enabled" == "true" ]]; then
    codex_home_dir="$CODEX_HOME"
    codex_sessions_dir="$codex_home_dir/sessions"
    if [[ -d "$codex_sessions_dir" ]]; then
        if [[ -w "$codex_sessions_dir" ]]; then
            if [[ "$VERBOSE" == true ]]; then
                echo -e "  ${GREEN}✓${NC} Codex sessions writable (${codex_sessions_dir})"
            fi
        else
            echo -e "  ${YELLOW}⚠${NC}  Codex session storage not writable"
            echo -e "    ${BLUE}→${NC} Fix permissions: $codex_sessions_dir"
            codex_runtime_ready=false
        fi
    else
        codex_sessions_parent="$(dirname "$codex_sessions_dir")"
        if [[ -d "$codex_sessions_parent" && -w "$codex_sessions_parent" ]]; then
            if [[ "$VERBOSE" == true ]]; then
                echo -e "  ${GREEN}✓${NC} Codex session parent writable (${codex_sessions_parent})"
            fi
        else
            echo -e "  ${YELLOW}⚠${NC}  Codex session path cannot be created"
            echo -e "    ${BLUE}→${NC} Fix permissions: $codex_sessions_parent"
            codex_runtime_ready=false
        fi
    fi
fi

echo ""

echo -e "${BOLD}State Directories:${NC}"
state_ok=true
for state_dir in "$manifest_tmp_dir" "$claude_state_dir" "$gemini_state_dir" "$cursor_state_dir" "$codex_state_dir" "$antigravity_state_dir"; do
    if mkdir -p "$state_dir" 2> /dev/null && [[ -w "$state_dir" ]]; then
        if [[ "$VERBOSE" == true ]]; then
            echo -e "  ${GREEN}✓${NC} $state_dir"
        fi
    else
        echo -e "  ${YELLOW}⚠${NC}  Not writable: $state_dir"
        state_ok=false
    fi
done
if [[ "$state_ok" == true ]]; then
    echo -e "  ${GREEN}✓${NC} Manifest state root ready: $manifest_state_root"
fi

echo ""

# Model staleness (warn-only; full detail via model_check.sh directly)
echo -e "${BOLD}Model Pins:${NC}"
# SCRIPT_DIR is set once near the top of the file (agent_roster.yml resolution).
if [[ -x "$SCRIPT_DIR/model_check.sh" ]]; then
    stale_pins=0
    skipped_pins=0
    unsupported_pins=0
    while IFS= read -r line; do
        case "$line" in
            OK:*) [[ "$VERBOSE" == true ]] && echo -e "  ${GREEN}✓${NC} ${line#OK: }" ;;
            STALE:*)
                stale_pins=$((stale_pins + 1))
                echo -e "  ${YELLOW}⚠${NC}  ${line#STALE: }"
                ;;
            SKIPPED:*)
                skipped_pins=$((skipped_pins + 1))
                [[ "$VERBOSE" == true ]] && echo -e "  ${YELLOW}○${NC} ${line#SKIPPED: }"
                ;;
            UNSUPPORTED:*)
                unsupported_pins=$((unsupported_pins + 1))
                [[ "$VERBOSE" == true ]] && echo -e "  ${YELLOW}○${NC} ${line#UNSUPPORTED: }"
                ;;
        esac
    done < <("$SCRIPT_DIR/model_check.sh")
    # SKIPPED must not read as green: on OAuth-only machines (no API keys)
    # claude/gemini pins go unverified and broken pins hide behind a ✓.
    # UNSUPPORTED providers (no listing command at all) are called out in the
    # green line so "verified" never overclaims what was actually checked.
    if [[ "$stale_pins" -gt 0 ]]; then
        echo -e "  ${YELLOW}⚠${NC}  $stale_pins stale model pin(s) — update model_tiers in parallel_agent.yml"
    elif [[ "$skipped_pins" -gt 0 ]]; then
        echo -e "  ${YELLOW}○${NC} $skipped_pins check(s) unverified (no API credentials — run MODEL_CHECK_PROBE=1 model_check.sh for a live CLI probe)"
    elif [[ "$unsupported_pins" -gt 0 ]]; then
        echo -e "  ${GREEN}✓${NC} Model pin check complete — all verifiable pins OK ($unsupported_pins provider(s) have no listing command)"
    else
        echo -e "  ${GREEN}✓${NC} Model pin check complete — all pins verified"
    fi
else
    echo -e "  ${YELLOW}○${NC} model_check.sh not found — skipping"
fi
echo ""

# Overall status
echo -e "${BOLD}${BLUE}═══════════════════════════════════════════════════════${NC}"
echo -e "${BOLD}Overall Status:${NC}"

working_agents=0
[[ "$claude_installed" == true && "$claude_enabled" == "true" ]] && working_agents=$((working_agents + 1))
[[ "$gemini_installed" == true && "$gemini_enabled" == "true" ]] && working_agents=$((working_agents + 1))
[[ "$cursor_installed" == true && "$cursor_enabled" == "true" ]] && working_agents=$((working_agents + 1))
[[ "$codex_installed" == true && "$codex_enabled" == "true" && "$codex_runtime_ready" == true ]] && working_agents=$((working_agents + 1))
[[ "$antigravity_installed" == true && "$antigravity_enabled" == "true" ]] && working_agents=$((working_agents + 1))

if [[ $working_agents -ge 2 ]]; then
    echo -e "  ${GREEN}✓${NC} System ready for parallel orchestration (${working_agents} agents available)"
elif [[ $working_agents -eq 1 ]]; then
    echo -e "  ${YELLOW}⚠${NC}  Limited functionality (only ${working_agents} agent available)"
    echo -e "  ${BLUE}→${NC} Enable/install at least 2 agents for full features"
else
    echo -e "  ${RED}✗${NC} System not operational (no agents available)"
    echo -e "  ${BLUE}→${NC} Run: ./bootstrap.sh"
fi

echo -e "${BOLD}${BLUE}═══════════════════════════════════════════════════════${NC}"
echo ""

# Quick test option
if [[ $working_agents -ge 1 ]]; then
    echo -e "${BOLD}Quick Test:${NC}"
    echo -e "  ~/.claude/scripts/parallel_agent.py --json 'What is 2+2?'"
    echo ""
fi

echo -e "${BOLD}Documentation:${NC}"
echo -e "  Troubleshooting: docs/TROUBLESHOOTING.md"
echo -e "  Configuration:   docs/CONFIGURATION.md"
echo -e "  Getting Started: docs/GETTING_STARTED.md"
echo ""
