#!/usr/bin/env bash
# version_pin.sh - Enforce specific, hashed version pins in dependency files
#
# Detects loose dependency references (latest / missing version / unbounded
# range / missing integrity hash) in recognized files, resolves a specific
# version + integrity hash via native package-manager tooling, and either
# rewrites the file in place (on-demand) or reports the fix (--check / hook).
#
# Usage: version_pin.sh [<path>...] [--check] [--requested NAME=VERSION]... \
#                       [--rule ID] [--config FILE]
#
#   <path>...            Files/dirs to scan (default: current directory tree).
#   --check              Warn-only: report violations + fixes, make NO edits
#                        (this is the save-hook mode).
#   --requested NAME=VER Pin NAME to an exact requested version (repeatable).
#   --rule ID            Limit to one rule-set entry from the config.
#   --config FILE        Override config (default: ../config/command_config.yml).
#
# Resolution: by default the script shells out to native tooling (pip / docker).
# Set VERSION_PIN_RESOLVER to an executable to override resolution; it is called
# as: RESOLVER <ecosystem> <name> <current> <requested>  and must print
# "<version><TAB><hash>" (hash may be empty) on stdout, or exit non-zero if the
# version cannot be resolved.
#
# Exit codes: 0 = clean (or all fixed on-demand); 1 = violations remain (--check);
#             2 = usage/config error.
#
# Compatible with bash 3.2 (no associative arrays / mapfile).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG="${VERSION_PIN_CONFIG:-${SCRIPT_DIR}/../config/command_config.yml}"

CHECK_ONLY=false
RULE_FILTER=""
PATHS=()
REQUESTED_KV=()   # entries of the form "name=version"

# Counters
N_FILES=0 N_VIOLATION=0 N_FIXED=0 N_COMPLIANT=0 N_BYPASSED=0 N_UNRESOLVED=0

# Per-file working buffers (reset by read_file / process_*)
FILE_LINES=()
OUT_LINES=()
CHANGED=false   # set by process_* to signal the file needs rewriting

err() { echo "version-pin: $*" >&2; }
usage_error() { err "$*"; exit 2; }

parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --check) CHECK_ONLY=true; shift ;;
            --rule) [[ $# -ge 2 ]] || usage_error "--rule needs an argument"; RULE_FILTER="$2"; shift 2 ;;
            --config) [[ $# -ge 2 ]] || usage_error "--config needs an argument"; CONFIG="$2"; shift 2 ;;
            --requested)
                [[ $# -ge 2 ]] || usage_error "--requested needs NAME=VERSION"
                [[ "$2" == *=* ]] || usage_error "--requested must be NAME=VERSION"
                REQUESTED_KV+=("$2"); shift 2 ;;
            --) shift; while [[ $# -gt 0 ]]; do PATHS+=("$1"); shift; done ;;
            -*) usage_error "unknown flag: $1" ;;
            *) PATHS+=("$1"); shift ;;
        esac
    done
    [[ ${#PATHS[@]} -gt 0 ]] || PATHS=(".")
}

requested_for() {
    local name="$1" kv
    for kv in ${REQUESTED_KV[@]+"${REQUESTED_KV[@]}"}; do
        if [[ "$kv" == "${name}="* ]]; then echo "${kv#*=}"; return 0; fi
    done
    return 0
}

# Emit rules as TSV: id<TAB>ecosystem<TAB>hash<TAB>glob,glob,...
load_rules() {
    [[ -f "$CONFIG" ]] || usage_error "config not found: $CONFIG"
    python3 - "$CONFIG" <<'PY'
import sys, yaml
cfg = yaml.safe_load(open(sys.argv[1])) or {}
vp = cfg.get("version_pin") or {}
for r in vp.get("rules") or []:
    globs = ",".join(r.get("match") or [])
    print("\t".join([str(r.get("id","")), str(r.get("ecosystem","")),
                     str(r.get("hash","none")), globs]))
PY
}

bypass_marker() {
    python3 - "$CONFIG" <<'PY'
import sys, yaml
cfg = yaml.safe_load(open(sys.argv[1])) or {}
print((cfg.get("version_pin") or {}).get("bypass_marker", "version-pin:ignore"))
PY
}

# Match a basename against a rule's comma-separated globs.
file_matches_globs() {
    local base="$1" globs="$2" g arr
    IFS=',' read -ra arr <<< "$globs"
    for g in "${arr[@]}"; do
        # shellcheck disable=SC2053
        [[ "$base" == $g ]] && return 0
    done
    return 1
}

# Resolve "<version><TAB><hash>" for a dependency; return 1 if unresolved.
resolve() {
    local eco="$1" name="$2" current="$3" requested="${4:-}"
    if [[ -n "${VERSION_PIN_RESOLVER:-}" ]]; then
        "$VERSION_PIN_RESOLVER" "$eco" "$name" "$current" "$requested" || return 1
        return 0
    fi
    case "$eco" in
        pip)    resolve_pip "$name" "$requested" ;;
        docker) resolve_docker "$name" "$current" "$requested" ;;
        *)      return 1 ;;
    esac
}

resolve_pip() {
    local name="$1" requested="${2:-}" ver hash pip tmp f
    pip="$(command -v pip || command -v pip3 || true)"
    [[ -n "$pip" ]] || return 1
    if [[ -n "$requested" ]]; then
        ver="$requested"
    else
        ver="$("$pip" index versions "$name" 2>/dev/null \
              | sed -n 's/.*LATEST:[[:space:]]*\([^[:space:]]*\).*/\1/p' | head -1)"
    fi
    [[ -n "$ver" ]] || return 1
    hash=""
    tmp="$(mktemp -d)"
    if "$pip" download --no-deps --quiet --dest "$tmp" "${name}==${ver}" >/dev/null 2>&1; then
        f="$(find "$tmp" -maxdepth 1 -type f | head -1)"
        [[ -n "$f" ]] && hash="$(shasum -a 256 "$f" 2>/dev/null | awk '{print $1}')"
    fi
    rm -rf "$tmp"
    printf '%s\t%s\n' "$ver" "$hash"
}

resolve_docker() {
    local name="$1" current="$2" requested="${3:-}" tag digest
    command -v docker >/dev/null 2>&1 || return 1
    if [[ -n "$requested" ]]; then
        tag="$requested"
    elif [[ -n "$current" && "$current" != "latest" ]]; then
        tag="$current"   # concrete tag already present; only the digest is missing
    else
        return 1         # cannot infer a specific version from 'latest'/empty
    fi
    digest="$(docker manifest inspect "${name}:${tag}" 2>/dev/null \
             | python3 -c 'import sys,json; print(json.load(sys.stdin).get("config",{}).get("digest",""))' 2>/dev/null || true)"
    printf '%s\t%s\n' "$tag" "$digest"
}

read_file() {
    local file="$1" line
    FILE_LINES=()
    while IFS='' read -r line || [[ -n "$line" ]]; do
        FILE_LINES+=("$line")
    done < "$file"
}

write_back() {
    local file="$1" changed="$2"
    $CHECK_ONLY && return 0
    [[ "$changed" == true ]] || return 0
    [[ ${#OUT_LINES[@]} -gt 0 ]] || return 0
    printf '%s\n' "${OUT_LINES[@]}" > "$file"
}

report() {
    local state="$1" detail="$2" sym
    case "$state" in
        violation) sym="x" ;; compliant) sym="ok" ;;
        bypassed) sym="--" ;; unresolved) sym="!" ;; *) sym="-" ;;
    esac
    printf '  %-2s %-10s %s\n' "$sym" "$state" "$detail"
}

# ---- per-ecosystem processors -------------------------------------------------

process_pip() {
    local marker="$1" changed=false
    local line trimmed name ver hash resolved fixed req
    OUT_LINES=(); CHANGED=false
    [[ ${#FILE_LINES[@]} -gt 0 ]] || return 0
    for line in "${FILE_LINES[@]}"; do
        trimmed="${line#"${line%%[![:space:]]*}"}"
        if [[ -z "$trimmed" || "$trimmed" == \#* || "$trimmed" == -* ]]; then
            OUT_LINES+=("$line"); continue
        fi
        if [[ "$line" == *"$marker"* ]]; then
            OUT_LINES+=("$line"); N_BYPASSED=$((N_BYPASSED+1)); report bypassed "$trimmed"; continue
        fi
        name="$(printf '%s' "$trimmed" | sed -E 's/[[:space:]]*([A-Za-z0-9._-]+).*/\1/')"
        if [[ "$trimmed" == *"=="* && "$trimmed" == *"--hash="* ]]; then
            OUT_LINES+=("$line"); N_COMPLIANT=$((N_COMPLIANT+1)); continue
        fi
        N_VIOLATION=$((N_VIOLATION+1))
        req="$(requested_for "$name")"
        if resolved="$(resolve pip "$name" "" "$req")"; then
            ver="${resolved%%	*}"; hash="${resolved#*	}"
            fixed="${name}==${ver}"
            [[ -n "$hash" ]] && fixed="${fixed} --hash=sha256:${hash}"
            report violation "$trimmed -> $fixed"
            if $CHECK_ONLY; then OUT_LINES+=("$line")
            else OUT_LINES+=("$fixed"); changed=true; N_FIXED=$((N_FIXED+1)); fi
        else
            OUT_LINES+=("$line"); N_UNRESOLVED=$((N_UNRESOLVED+1)); report unresolved "$name (no version/tool)"
        fi
    done
    CHANGED="$changed"
}

process_docker() {
    local marker="$1" kind="$2" changed=false
    local line key ref name tag rest resolved ver digest newref re req
    OUT_LINES=(); CHANGED=false
    if [[ "$kind" == "compose" ]]; then re='^([[:space:]]*image:[[:space:]]*)([^[:space:]#]+)(.*)$'
    else re='^([[:space:]]*FROM[[:space:]]+)([^[:space:]#]+)(.*)$'; fi
    [[ ${#FILE_LINES[@]} -gt 0 ]] || return 0
    for line in "${FILE_LINES[@]}"; do
        if [[ ! "$line" =~ $re ]]; then OUT_LINES+=("$line"); continue; fi
        key="${BASH_REMATCH[1]}"; ref="${BASH_REMATCH[2]}"; rest="${BASH_REMATCH[3]}"
        if [[ "$line" == *"$marker"* ]]; then
            OUT_LINES+=("$line"); N_BYPASSED=$((N_BYPASSED+1)); report bypassed "$ref"; continue
        fi
        if [[ "$ref" == *"@sha256:"* ]]; then OUT_LINES+=("$line"); N_COMPLIANT=$((N_COMPLIANT+1)); continue; fi
        if [[ "$ref" == *:* ]]; then name="${ref%%:*}"; tag="${ref##*:}"; else name="$ref"; tag="latest"; fi
        N_VIOLATION=$((N_VIOLATION+1))
        req="$(requested_for "$name")"
        if resolved="$(resolve docker "$name" "$tag" "$req")"; then
            ver="${resolved%%	*}"; digest="${resolved#*	}"
            newref="${name}:${ver}"
            [[ -n "$digest" ]] && newref="${newref}@${digest}"
            report violation "$ref -> $newref"
            if $CHECK_ONLY; then OUT_LINES+=("$line")
            else OUT_LINES+=("${key}${newref}${rest}"); changed=true; N_FIXED=$((N_FIXED+1)); fi
        else
            OUT_LINES+=("$line"); N_UNRESOLVED=$((N_UNRESOLVED+1)); report unresolved "$name (cannot infer specific version from '$tag')"
        fi
    done
    CHANGED="$changed"
}

process_file() {
    local file="$1" eco="$2" rule_id="$3" marker
    marker="$(bypass_marker)"
    N_FILES=$((N_FILES+1))
    echo "version-pin: ${file}"
    read_file "$file"
    case "$eco" in
        pip) process_pip "$marker"; write_back "$file" "$CHANGED" ;;
        docker)
            case "$rule_id" in
                dockerfile) process_docker "$marker" dockerfile ;;
                *) process_docker "$marker" compose ;;
            esac
            write_back "$file" "$CHANGED" ;;
        *) report unresolved "ecosystem '$eco' has no parser (skipped)"; N_UNRESOLVED=$((N_UNRESOLVED+1)) ;;
    esac
}

collect_files() {
    local p
    for p in "${PATHS[@]}"; do
        if [[ -f "$p" ]]; then echo "$p"
        elif [[ -d "$p" ]]; then
            find "$p" -type f \( -name 'requirements*.txt' -o -name 'docker-compose.y*ml' \
                 -o -name 'compose.y*ml' -o -name 'Dockerfile' -o -name 'Dockerfile.*' \
                 -o -name '*.Dockerfile' \) 2>/dev/null
        else
            err "path not found: $p"
        fi
    done
}

main() {
    parse_args "$@"
    local rules; rules="$(load_rules)"
    [[ -n "$rules" ]] || usage_error "no version_pin rules in $CONFIG"

    local explicit_unmatched=true
    [[ -d "${PATHS[0]}" ]] && explicit_unmatched=false

    local file base matched id eco hash globs
    while IFS='' read -r file; do
        [[ -n "$file" ]] || continue
        base="$(basename "$file")"
        matched=false
        while IFS=$'\t' read -r id eco hash globs; do
            [[ -z "$id" ]] && continue
            [[ -n "$RULE_FILTER" && "$RULE_FILTER" != "$id" ]] && continue
            if file_matches_globs "$base" "$globs"; then
                process_file "$file" "$eco" "$id"; matched=true; break
            fi
        done <<< "$rules"
        if [[ "$matched" == false && -f "$file" ]] && $explicit_unmatched; then
            echo "version-pin: ${file}"; report unresolved "no applicable rules"
        fi
    done < <(collect_files)

    local mode="fixed"; $CHECK_ONLY && mode="reported"
    echo "Summary: ${N_FILES} files, ${N_VIOLATION} violations ${mode}, ${N_COMPLIANT} compliant, ${N_BYPASSED} bypassed, ${N_UNRESOLVED} unresolved"
    if $CHECK_ONLY && [[ $N_VIOLATION -gt 0 ]]; then return 1; fi
    return 0
}

main "$@"
