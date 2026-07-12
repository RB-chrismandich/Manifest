#!/usr/bin/env bash
# emdash_inherit_check.sh — emdash config-inheritance probe.
#
# Reports whether a Manifest-configured agent, launched by the emdash desktop
# app in a given worktree with a given HOME, inherits the full Manifest
# configuration (skills, subagents, hooks, MCP, orchestration + repo guides).
# Single source of truth shared by /env-check (live) and
# tests/bats/emdash_inheritance.bats (fixture). See
# specs/483-emdash-support/contracts/inheritance-probe.md.
#
# Exit codes: 0 INHERITED · 1 DEGRADED · 2 BLOCKED (no <home>/.claude) · 64 usage.
set -uo pipefail

err() { if [[ -t 2 ]]; then printf '\033[0;31m%s\033[0m\n' "emdash_inherit_check.sh: $*" >&2; else printf '%s\n' "emdash_inherit_check.sh: $*" >&2; fi; }

usage() {
    cat << 'EOF'
Usage: emdash_inherit_check.sh [--home <dir>] [--worktree <dir>] [--json] [--help]

Probe whether a Manifest-configured agent launched by emdash inherits the full
config. Checks D1 skills, D2 subagents, D3 hooks (+ emdash-merge coexistence),
D4 MCP, D5 orchestration guide, D6 repo guides.

  --home <dir>      Home whose .claude/ is the deployed Manifest config (default: $HOME)
  --worktree <dir>  Worktree checkout to inspect (default: $PWD)
  --json            Machine-readable report (default: human report)
  --help            This help

Exit: 0 INHERITED · 1 DEGRADED · 2 BLOCKED (home deploy missing) · 64 usage.
EOF
}

# --- Argument parsing (before any config lookup) -----------------------------
home_dir="${HOME:-}"
worktree_dir="${PWD:-}"
json_out=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --help | -h)
            usage
            exit 0
            ;;
        --home)
            [[ $# -ge 2 ]] || {
                err "--home requires a directory argument"
                exit 64
            }
            home_dir="$2"
            shift 2
            ;;
        --worktree)
            [[ $# -ge 2 ]] || {
                err "--worktree requires a directory argument"
                exit 64
            }
            worktree_dir="$2"
            shift 2
            ;;
        --json)
            json_out=1
            shift
            ;;
        *)
            err "unknown argument: $1"
            usage >&2
            exit 64
            ;;
    esac
done

EMDASH_MARKER="${EMDASH_MARKER:-emdash-managed-hook}"

# --- BLOCKED: home deploy missing --------------------------------------------
home_claude="${home_dir%/}/.claude"
if [[ ! -d "$home_claude" ]]; then
    if [[ "$json_out" -eq 1 ]]; then
        printf '{"verdict":"BLOCKED","reason":"home deploy missing: %s","dimensions":{},"coexistence":{"emdash_hook_detected":false,"manifest_hooks_preserved":null,"worktree_permissions_intact":null}}\n' "$home_claude"
    else
        echo "emdash inheritance: BLOCKED"
        echo "  home deploy missing: $home_claude"
        echo "  run ./bootstrap.sh to deploy the Manifest config, then re-check."
    fi
    exit 2
fi

worktree_claude="${worktree_dir%/}/.claude"
home_settings="${home_claude}/settings.json"
home_merged="${home_settings}.emdash-merged"
# A `.emdash-merged` sibling is a genuine, independently-written pre/post pair
# (fixture mode). Without one (the normal live/env-check case) there is no
# pre-merge snapshot to diff against — comparing the live file to itself would
# always report "preserved/intact" even if emdash had actually dropped
# something, so track whether a real comparison is happening.
home_merge_simulated=1
[[ -f "$home_merged" ]] || {
    home_merged="$home_settings"
    home_merge_simulated=0
}
worktree_settings="${worktree_claude}/settings.local.json"
worktree_merged="${worktree_settings}.emdash-merged"
worktree_merge_simulated=1
[[ -f "$worktree_merged" ]] || {
    worktree_merged="$worktree_settings"
    worktree_merge_simulated=0
}

# --- D1 Skills ---------------------------------------------------------------
skills_count=0
if [[ -d "${home_claude}/skills" ]]; then
    while IFS= read -r _; do
        skills_count=$((skills_count + 1))
    done < <(find "${home_claude}/skills" -mindepth 2 -maxdepth 2 -name 'SKILL.md' -type f 2> /dev/null)
fi
if [[ "$skills_count" -ge 1 ]]; then
    d1_status="PASS"
    d1_detail="${skills_count} reachable"
else
    d1_status="FAIL"
    d1_detail="no SKILL.md under ${home_claude}/skills"
fi

# --- D2 Subagents ------------------------------------------------------------
home_agents=0
worktree_agents=0
if [[ -d "${home_claude}/agents" ]]; then
    while IFS= read -r _; do
        home_agents=$((home_agents + 1))
    done < <(find "${home_claude}/agents" -mindepth 1 -maxdepth 1 -name '*.md' -type f 2> /dev/null)
fi
if [[ -d "${worktree_claude}/agents" ]]; then
    while IFS= read -r _; do
        worktree_agents=$((worktree_agents + 1))
    done < <(find "${worktree_claude}/agents" -mindepth 1 -maxdepth 1 -name '*.md' -type f 2> /dev/null)
fi
agents_total=$((home_agents + worktree_agents))
if [[ "$agents_total" -ge 1 ]]; then
    d2_status="PASS"
    d2_detail="${agents_total} reachable (home ${home_agents}, repo ${worktree_agents})"
else
    d2_status="FAIL"
    d2_detail="no *.md in ${home_claude}/agents or ${worktree_claude}/agents"
fi

# --- JSON analysis (D3 hooks/coexistence + D4 MCP count) ---------------------
# Emits key=value lines parsed below.
analysis="$(
    python3 - "$home_settings" "$home_merged" "$worktree_settings" "$worktree_merged" "$EMDASH_MARKER" \
        "$home_merge_simulated" "$worktree_merge_simulated" << 'PY'
import json, sys

home_base, home_merged, wt_base, wt_merged, marker = sys.argv[1:6]
home_merge_simulated = sys.argv[6] == "1"
worktree_merge_simulated = sys.argv[7] == "1"


def load(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh), True
    except FileNotFoundError:
        return {}, True
    except Exception:
        return {}, False


def is_emdash(entry):
    blob = json.dumps(entry)
    return marker in blob or "EMDASH_HOOK_PORT" in blob


def hook_commands(data, only_manifest):
    """Flatten every hook command string in a settings 'hooks' object."""
    cmds = []
    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        return cmds
    for event in hooks.values():
        if not isinstance(event, list):
            continue
        for matcher in event:
            if not isinstance(matcher, dict):
                continue
            for entry in matcher.get("hooks", []) or []:
                if not isinstance(entry, dict):
                    continue
                if only_manifest and is_emdash(entry):
                    continue
                cmd = entry.get("command")
                if isinstance(cmd, str):
                    cmds.append(cmd)
    return cmds


def any_emdash(data):
    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        return False
    for event in hooks.values():
        if not isinstance(event, list):
            continue
        for matcher in event:
            if not isinstance(matcher, dict):
                continue
            for entry in matcher.get("hooks", []) or []:
                if isinstance(entry, dict) and is_emdash(entry):
                    return True
    return False


hb, hb_ok = load(home_base)
hm, hm_ok = load(home_merged)
wb, wb_ok = load(wt_base)
wm, wm_ok = load(wt_merged)

# D4 MCP: count servers from home settings (fallback .mcp.json handled in bash).
mcp = hb.get("mcpServers")
mcp_count = len(mcp) if isinstance(mcp, dict) else 0

# D3 home scope: Manifest hooks present in baseline, all preserved in merged.
# Tri-state result: 1 = verified preserved, 0 = verified DROPPED (corruption
# detected), 2 = unverifiable (no independent pre/post snapshot to diff --
# home_base and home_merged are the same file, so the comparison would be a
# tautology; report it honestly instead of a false-positive "true").
manifest_cmds = set(hook_commands(hb, only_manifest=True))
merged_cmds = set(hook_commands(hm, only_manifest=False))
home_manifest_hooks = len(manifest_cmds)
if home_merge_simulated:
    preserved = 1 if (manifest_cmds.issubset(merged_cmds) and hm_ok) else 0
else:
    preserved = 2

# D3 worktree scope: permissions block not corrupted by the merge.
base_perms = wb.get("permissions")
merged_perms = wm.get("permissions")
if worktree_merge_simulated:
    if wb_ok and wm_ok:
        # Intact when the permissions block is unchanged (missing on both =
        # nothing to corrupt = intact).
        perms_intact = 1 if base_perms == merged_perms else 0
    else:
        perms_intact = 0
else:
    perms_intact = 2

emdash_detected = any_emdash(hm) or any_emdash(wm)

print("mcp_count=%d" % mcp_count)
print("home_manifest_hooks=%d" % home_manifest_hooks)
print("manifest_hooks_preserved=%d" % preserved)
print("worktree_permissions_intact=%d" % perms_intact)
print("emdash_hook_detected=%d" % (1 if emdash_detected else 0))
PY
)"
analysis_rc=$?

mcp_count=0
home_manifest_hooks=0
# manifest_hooks_preserved / worktree_permissions_intact are tri-state:
# 1=verified preserved/intact, 0=verified corrupted (FAIL), 2=unverifiable (no
# independent pre/post snapshot -- live mode). Default to 2 (unverifiable)
# rather than 0 so an analysis failure isn't misreported as detected
# corruption.
manifest_hooks_preserved=2
worktree_permissions_intact=2
emdash_hook_detected=0
if [[ "$analysis_rc" -eq 0 ]]; then
    while IFS='=' read -r k v; do
        case "$k" in
            mcp_count) mcp_count="$v" ;;
            home_manifest_hooks) home_manifest_hooks="$v" ;;
            manifest_hooks_preserved) manifest_hooks_preserved="$v" ;;
            worktree_permissions_intact) worktree_permissions_intact="$v" ;;
            emdash_hook_detected) emdash_hook_detected="$v" ;;
        esac
    done <<< "$analysis"
else
    err "settings analysis failed (python3 unavailable or error)"
fi

# --- D3 Hooks (+ coexistence) ------------------------------------------------
# PASS requires Manifest hooks present and neither coexistence check having
# VERIFIED corruption (tri-state value 0). A tri-state of 2 (unverifiable --
# no simulated merge sibling on disk, i.e. a live/env-check run) is not
# treated as a failure since there is nothing to have detected; it is
# surfaced distinctly below and in --json so it is never confused with an
# actual verified-safe merge.
if [[ "$home_manifest_hooks" -ge 1 && "$manifest_hooks_preserved" -ne 0 && "$worktree_permissions_intact" -ne 0 ]]; then
    d3_status="PASS"
    if [[ "$emdash_hook_detected" -eq 1 && "$manifest_hooks_preserved" -eq 1 && "$worktree_permissions_intact" -eq 1 ]]; then
        d3_detail="manifest hooks present; preserved after emdash merge"
    elif [[ "$emdash_hook_detected" -eq 1 ]]; then
        d3_detail="manifest hooks present; emdash hook detected but no pre/post snapshot to verify preservation (live run)"
    else
        d3_detail="manifest hooks present; no emdash hook detected (nothing to preserve yet)"
    fi
else
    d3_status="FAIL"
    if [[ "$home_manifest_hooks" -lt 1 ]]; then
        d3_detail="no Manifest hooks in ${home_settings}"
    elif [[ "$manifest_hooks_preserved" -eq 0 ]]; then
        d3_detail="Manifest hooks dropped by emdash merge in ${home_merged}"
    else
        d3_detail="worktree permissions corrupted by emdash merge in ${worktree_merged}"
    fi
fi

# --- D4 MCP ------------------------------------------------------------------
if [[ "$mcp_count" -lt 1 ]]; then
    # Fallback to a project/home .mcp.json server list.
    for mcp_file in "${home_claude}/.mcp.json" "${worktree_dir%/}/.mcp.json"; do
        if [[ -f "$mcp_file" ]]; then
            alt="$(
                python3 - "$mcp_file" << 'PY'
import json, sys
try:
    d = json.load(open(sys.argv[1], encoding="utf-8"))
    s = d.get("mcpServers")
    print(len(s) if isinstance(s, dict) else 0)
except Exception:
    print(0)
PY
            )"
            if [[ "${alt:-0}" -ge 1 ]]; then
                mcp_count="$alt"
                break
            fi
        fi
    done
fi
if [[ "$mcp_count" -ge 1 ]]; then
    d4_status="PASS"
    d4_detail="${mcp_count} servers"
else
    d4_status="FAIL"
    d4_detail="no mcpServers in ${home_settings} or .mcp.json"
fi

# --- D5 Orchestration guide --------------------------------------------------
home_guide=0
repo_guide=0
[[ -r "${home_claude}/CLAUDE.md" ]] && home_guide=1
{ [[ -r "${worktree_dir%/}/CLAUDE.md" ]] || [[ -r "${worktree_claude}/CLAUDE.md" ]]; } && repo_guide=1
if [[ "$home_guide" -eq 1 && "$repo_guide" -eq 1 ]]; then
    d5_status="PASS"
    d5_detail="home+repo guides present"
elif [[ "$home_guide" -eq 1 || "$repo_guide" -eq 1 ]]; then
    d5_status="PASS"
    d5_detail="guide present (home=${home_guide}, repo=${repo_guide})"
else
    d5_status="FAIL"
    d5_detail="no CLAUDE.md in home or worktree"
fi

# --- D6 Repo guides ----------------------------------------------------------
repo_agents=0
repo_claude=0
[[ -r "${worktree_dir%/}/AGENTS.md" ]] && repo_agents=1
[[ -d "$worktree_claude" ]] && repo_claude=1
if [[ "$repo_agents" -eq 1 && "$repo_claude" -eq 1 ]]; then
    d6_status="PASS"
    d6_detail="AGENTS.md + .claude present"
else
    d6_status="FAIL"
    d6_detail="missing AGENTS.md ($repo_agents) or .claude ($repo_claude) in worktree"
fi

# --- Verdict -----------------------------------------------------------------
verdict="INHERITED"
exit_code=0
for st in "$d1_status" "$d2_status" "$d3_status" "$d4_status" "$d5_status" "$d6_status"; do
    if [[ "$st" == "FAIL" ]]; then
        verdict="DEGRADED"
        exit_code=1
        break
    fi
done

# --- Output ------------------------------------------------------------------
bool() { [[ "$1" -eq 1 ]] && echo true || echo false; }
# tri(): renders the tri-state coexistence result. "unverified" (tri-state 2)
# means no independent pre/post snapshot existed to compare (live run, no
# `.emdash-merged` sibling on disk) -- it must never be conflated with a
# verified "true", or the check silently reports success without having
# checked anything.
tri() {
    case "$1" in
        1) echo true ;;
        0) echo false ;;
        *) echo unverified ;;
    esac
}

if [[ "$json_out" -eq 1 ]]; then
    python3 - \
        "$verdict" \
        "$d1_status" "$d1_detail" "$d2_status" "$d2_detail" "$d3_status" "$d3_detail" \
        "$d4_status" "$d4_detail" "$d5_status" "$d5_detail" "$d6_status" "$d6_detail" \
        "$(bool "$emdash_hook_detected")" "$(tri "$manifest_hooks_preserved")" "$(tri "$worktree_permissions_intact")" \
        << 'PY'
import json, sys
a = sys.argv
verdict = a[1]
d = a[2:14]


def tri_json(s):
    # "unverified" -> null: no independent pre/post snapshot was available to
    # compare (live run), so this must not be reported as true or false.
    return {"true": True, "false": False}.get(s)


report = {
    "verdict": verdict,
    "dimensions": {
        "skills": {"status": d[0], "detail": d[1]},
        "subagents": {"status": d[2], "detail": d[3]},
        "hooks": {"status": d[4], "detail": d[5]},
        "mcp": {"status": d[6], "detail": d[7]},
        "guide": {"status": d[8], "detail": d[9]},
        "repo_guides": {"status": d[10], "detail": d[11]},
    },
    "coexistence": {
        "emdash_hook_detected": a[14] == "true",
        "manifest_hooks_preserved": tri_json(a[15]),
        "worktree_permissions_intact": tri_json(a[16]),
    },
}
print(json.dumps(report))
PY
else
    echo "emdash inheritance: ${verdict}"
    printf '  D1 skills       %-5s %s\n' "$d1_status" "$d1_detail"
    printf '  D2 subagents    %-5s %s\n' "$d2_status" "$d2_detail"
    printf '  D3 hooks        %-5s %s\n' "$d3_status" "$d3_detail"
    printf '  D4 mcp          %-5s %s\n' "$d4_status" "$d4_detail"
    printf '  D5 guide        %-5s %s\n' "$d5_status" "$d5_detail"
    printf '  D6 repo guides  %-5s %s\n' "$d6_status" "$d6_detail"
    echo "  coexistence: emdash_hook_detected=$(bool "$emdash_hook_detected"), manifest_hooks_preserved=$(tri "$manifest_hooks_preserved"), worktree_permissions_intact=$(tri "$worktree_permissions_intact")"
    if [[ "$emdash_hook_detected" -eq 1 ]]; then
        if [[ "$manifest_hooks_preserved" -eq 2 || "$worktree_permissions_intact" -eq 2 ]]; then
            echo "  note: emdash appends its own hook (marker-tagged) + gitignores the machine-local file; keep that injected hook uncommitted. No pre/post snapshot was available in this live run, so preservation is unverified here (verified deterministically by tests/bats/emdash_inheritance.bats against the fixture)."
        else
            echo "  note: emdash appends its own hook (marker-tagged) + gitignores the machine-local file; keep that injected hook uncommitted. Manifest hooks are preserved."
        fi
    fi
fi

exit "$exit_code"
