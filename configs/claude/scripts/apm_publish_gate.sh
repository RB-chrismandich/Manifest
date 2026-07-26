#!/usr/bin/env bash
# apm_publish_gate.sh — publish preflight gate (Phase 0, T048/FR-030 +
# T049/FR-038 + SC-011). The one sanctioned exception to FR-001 (spec.md:152):
# additive, self-contained, correct under a NO-GO, and required before the
# spike's throwaway package (or any future release) may publish anything.
#
# Subcommands:
#   scan PATH       Blocking content scan (T048/FR-030). Runs the repo's
#                   gitleaks config against PATH for secrets/credentials,
#                   plus in-script regex checks for machine-local paths and
#                   private material (Decision D). Gitleaks absent or
#                   erroring REJECTS — never degrades to regex-only.
#   provenance      Provenance gate (T049/FR-038). Passes only when the
#                   checked repo's working tree is clean AND HEAD is exactly
#                   at a tag (annotated or lightweight; `git describe --tags
#                   --exact-match`). No PATH argument — it inspects the repo
#                   at $APM_GATE_REPO (default: cwd), i.e. the source the
#                   artifact is being built from, not the artifact tree
#                   itself.
#   all PATH        scan PATH, then provenance. Always appends one JSON line
#                   to the gate-records log (pass or fail — SC-011 needs a
#                   record preceding every publish attempt, not only
#                   successful ones) with the canonical tree hash of PATH.
#                   This is the sanctioned publish preflight.
#
# Exit: 0 pass / 1 gate rejected (violation found OR indeterminate) / 2 usage
# error. Fail-closed is the requirement: any subject apm_publish_gate.sh
# cannot positively validate is treated as a rejection, never a pass.
#
# Env:
#   APM_GITLEAKS_CONFIG   gitleaks config path (default: repo's .gitleaks.toml)
#   APM_PUBLISH_ALLOWLIST allowlist path (default: configs/claude/config/
#                         apm_publish_allowlist.txt)
#   APM_GATE_RECORD_FILE  gate-records JSONL path (default: committed
#                         specs/522-apm-deploy-migration/gate-records.jsonl)
#   APM_GATE_REPO         repo `provenance`/`all` check (default: $PWD)

set -euo pipefail

err() { echo "apm_publish_gate.sh: $*" >&2; }

usage() {
    cat << 'USAGE'
Usage: apm_publish_gate.sh <scan PATH | provenance | all PATH> [--help]

  scan PATH      Block on secrets/credentials (gitleaks) and machine-local
                 paths or private material (in-script regex) found in PATH.
  provenance     Pass only if the working tree is clean and HEAD is at a tag.
  all PATH       scan PATH, then provenance; always append one gate record
                 to gate-records.jsonl (see APM_GATE_RECORD_FILE).

Exit: 0 pass / 1 gate rejected or indeterminate / 2 usage error.
Env: APM_GITLEAKS_CONFIG, APM_PUBLISH_ALLOWLIST, APM_GATE_RECORD_FILE,
     APM_GATE_REPO (repo checked by provenance; default: cwd).
USAGE
}

case "${1:-}" in
    --help | -h)
        usage
        exit 0
        ;;
esac

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./apm_hash_lib.sh
source "${SCRIPT_DIR}/apm_hash_lib.sh"

REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
GITLEAKS_CONFIG_DEFAULT="${REPO_ROOT}/.gitleaks.toml"
ALLOWLIST_DEFAULT="${REPO_ROOT}/configs/claude/config/apm_publish_allowlist.txt"
GATE_RECORD_DEFAULT="${REPO_ROOT}/specs/522-apm-deploy-migration/gate-records.jsonl"

SCAN_VIOLATIONS=0

# scan_report_hit LABEL REL LINE MATCH -> records one blocking finding.
scan_report_hit() {
    SCAN_VIOLATIONS=$((SCAN_VIOLATIONS + 1))
    err "scan: [$1] $2:$3: $4"
}

# scan_category LABEL MODE PATTERN TARGET ALLOWLIST
#   MODE is a grep(1) match-mode flag letter: E (extended regex) or F (fixed
#   string). Walks TARGET's regular files (excluding .git) via
#   apm_walk_tree_files (apm_hash_lib.sh — shared with the hash routine so
#   the two walks can never drift apart, NUL-delimited end to end so an
#   embedded newline in a filename can never be misread as a record
#   separator), greps each individually (portable — no dependency on
#   GNU-only --exclude-dir), and reports every hit whose matched text is not
#   covered by an ALLOWLIST pattern. ALLOWLIST is expected to already be
#   pre-filtered (blank/#-comment lines stripped) by the caller — see
#   cmd_scan_regex. An empty-or-absent ALLOWLIST suppresses nothing (every
#   hit is reported): that is the correct fail-closed-neutral reading of "no
#   active allowlist entries", not a bug.
#
#   Defense in depth: an enumerated REL that does not resolve to a readable
#   file (should not happen once the walk is NUL-safe, but a TOCTOU race or
#   an unreadable-permissions file could still produce one) is treated as
#   INDETERMINATE and counted as a violation — mirroring how the hash
#   routine already fails closed on the identical condition — rather than
#   silently `continue`d past, which is exactly the "gate cannot determine
#   validity" case Standing Constraint 3 requires to reject.
scan_category() {
    local label="$1" mode="$2" pattern="$3" target="$4" allowlist="$5"
    local rel file hit lineno match

    while IFS= read -r -d '' rel; do
        [[ -z "$rel" ]] && continue
        file="$target/$rel"
        if [[ ! -r "$file" ]]; then
            scan_report_hit "$label" "$rel" "?" "enumerated path did not resolve to a readable file — indeterminate, rejecting"
            continue
        fi
        while IFS= read -r hit; do
            [[ -z "$hit" ]] && continue
            lineno="${hit%%:*}"
            match="${hit#*:}"
            if [[ -s "$allowlist" ]] && printf '%s\n' "$match" | grep -Eq -f "$allowlist" 2> /dev/null; then
                continue
            fi
            scan_report_hit "$label" "$rel" "$lineno" "$match"
        done < <(grep -noI"$mode" "$pattern" "$file" 2> /dev/null || true)
    done < <(apm_walk_tree_files "$target")
}

# cmd_scan_regex TARGET ALLOWLIST_RAW -> Decision D categories: machine-local
# paths (absolute /Users|/home path, literal ~<name>, machine hostname) and
# private material (operator emails, private tracker/repo URLs, .remember/
# references). Returns 1 if any non-allowlisted hit was found.
#
# ALLOWLIST_RAW is filtered exactly once here (blank lines and #-comment
# lines stripped) before any category consults it — this is the fix for a
# real bug: a blank line handed straight to `grep -f` is an EMPTY pattern,
# and at least one grep implementation (confirmed empirically: GNU grep)
# treats an empty pattern as matching every input line, which would silently
# allowlist every finding in every category. Filtering into a temp file
# means an allowlist that is absent, empty, or reduces to nothing-but-
# comments after filtering all take the same safe path: scan_category's own
# `-s "$allowlist"` check sees a missing-or-empty file and suppresses
# nothing — never "matches everything", never an error.
cmd_scan_regex() {
    local target="$1" allowlist_raw="$2" allowlist=""
    SCAN_VIOLATIONS=0

    if [[ -s "$allowlist_raw" ]]; then
        allowlist="$(mktemp "${TMPDIR:-/tmp}/apm-allowlist-filtered.XXXXXX")" || {
            err "scan: could not create filtered-allowlist temp file — indeterminate, rejecting"
            return 1
        }
        grep -v -e '^[[:space:]]*$' -e '^[[:space:]]*#' "$allowlist_raw" > "$allowlist" 2> /dev/null || true
    fi

    scan_category "machine-local-path" E '/Users/[A-Za-z0-9._<>-]+' "$target" "$allowlist"
    scan_category "machine-local-path" E '/home/[A-Za-z0-9._<>-]+' "$target" "$allowlist"
    scan_category "machine-local-path" E '~[A-Za-z<][A-Za-z0-9._<>-]*' "$target" "$allowlist"
    scan_category "private-email" E '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}' "$target" "$allowlist"
    scan_category "private-tracker-url" E 'https?://linear\.app/[A-Za-z0-9_./-]+' "$target" "$allowlist"
    scan_category "private-tracker-url" E 'https?://[A-Za-z0-9.-]+\.atlassian\.net(/[A-Za-z0-9_./-]*)?' "$target" "$allowlist"
    scan_category "private-remember-ref" F '.remember/' "$target" "$allowlist"

    local host_short host_full
    host_short="$(hostname -s 2> /dev/null || true)"
    host_full="$(hostname 2> /dev/null || true)"
    if [[ -n "$host_short" && ${#host_short} -ge 4 && "$host_short" != "localhost" ]]; then
        scan_category "machine-hostname" F "$host_short" "$target" "$allowlist"
    fi
    if [[ -n "$host_full" && "$host_full" != "$host_short" && ${#host_full} -ge 4 && "$host_full" != "localhost" ]]; then
        scan_category "machine-hostname" F "$host_full" "$target" "$allowlist"
    fi

    [[ -n "$allowlist" ]] && rm -f "$allowlist"

    [[ "$SCAN_VIOLATIONS" -eq 0 ]]
}

# cmd_scan PATH -> T048/FR-030. gitleaks first (fail-closed if absent or
# erroring — Decision A), then the Decision D regex categories.
cmd_scan() {
    local target="${1:-}"
    [[ -n "$target" ]] || {
        err "scan: PATH required"
        usage >&2
        return 2
    }
    [[ -d "$target" ]] || {
        err "scan: not a directory: $target — indeterminate, rejecting"
        return 1
    }
    [[ -r "$target" ]] || {
        err "scan: unreadable: $target — indeterminate, rejecting"
        return 1
    }

    if ! command -v gitleaks > /dev/null 2>&1; then
        err "scan: gitleaks not found on PATH — rejecting (fail-closed, no regex-only degrade)"
        return 1
    fi

    local gl_config="${APM_GITLEAKS_CONFIG:-$GITLEAKS_CONFIG_DEFAULT}"
    [[ -f "$gl_config" ]] || {
        err "scan: gitleaks config not found: $gl_config — rejecting"
        return 1
    }

    local gl_report gl_rc=0
    gl_report="$(mktemp "${TMPDIR:-/tmp}/apm-gitleaks-report.XXXXXX")" || {
        err "scan: could not create temp report file — rejecting"
        return 1
    }
    gitleaks detect --no-git --source "$target" --config "$gl_config" \
        --report-format json --report-path "$gl_report" --no-banner \
        > /dev/null 2>&1 || gl_rc=$?
    rm -f "$gl_report"

    if [[ $gl_rc -ne 0 ]]; then
        err "scan: gitleaks rejected $target (exit $gl_rc) — secret/credential finding or tool error"
        return 1
    fi

    local allowlist="${APM_PUBLISH_ALLOWLIST:-$ALLOWLIST_DEFAULT}"
    cmd_scan_regex "$target" "$allowlist" || {
        err "scan: rejected $target — machine-local path or private material found"
        return 1
    }

    return 0
}

# cmd_provenance -> T049/FR-038. Prints the tag name on stdout when it
# passes. `git describe --tags --exact-match` accepts both annotated and
# lightweight tags — either satisfies "HEAD is at a tag".
cmd_provenance() {
    local repo="${APM_GATE_REPO:-$PWD}"
    command -v git > /dev/null 2>&1 || {
        err "provenance: git not found — indeterminate, rejecting"
        return 1
    }
    git -C "$repo" rev-parse --is-inside-work-tree > /dev/null 2>&1 || {
        err "provenance: not a git repository: $repo — indeterminate, rejecting"
        return 1
    }
    [[ -z "$(git -C "$repo" status --porcelain 2> /dev/null)" ]] || {
        err "provenance: working tree is dirty: $repo"
        return 1
    }
    local tag
    tag="$(git -C "$repo" describe --tags --exact-match 2> /dev/null)" || {
        err "provenance: HEAD is not at a tagged commit: $repo"
        return 1
    }
    printf '%s\n' "$tag"
    return 0
}

# cmd_all_write_record RECORD_FILE TS SUBJECT HASH RESULT TOOL_VERSION GIT_REF
# Appends one JSON line. Always called by cmd_all (pass or fail) so SC-011's
# "record precedes every publish attempt" holds for rejected attempts too.
# The "gate" literal comes from APM_GATE_RECORD_GATE_ID (apm_hash_lib.sh) —
# the single source of truth apm_install_verify.sh's reader also uses — so
# the identifier can never drift between writer and reader.
cmd_all_write_record() {
    local record_file="$1" dir
    dir="$(dirname "$record_file")"
    mkdir -p "$dir" 2> /dev/null || true
    APM_TS="$2" APM_SUBJECT="$3" APM_HASH="$4" APM_RESULT="$5" APM_TOOL="$6" APM_REF="$7" \
        APM_GATE_ID="$APM_GATE_RECORD_GATE_ID" \
        python3 -c '
import json, os
h = os.environ.get("APM_HASH", "")
rec = {
    "ts": os.environ.get("APM_TS", ""),
    "gate": os.environ["APM_GATE_ID"],
    "subject": os.environ.get("APM_SUBJECT", ""),
    "subject_sha256": h if h else None,
    "result": os.environ.get("APM_RESULT", ""),
    "tool_version": os.environ.get("APM_TOOL", ""),
    "git_ref": os.environ.get("APM_REF", ""),
}
print(json.dumps(rec, sort_keys=True))
' >> "$record_file"
}

# cmd_all PATH -> the sanctioned publish preflight (SC-011).
cmd_all() {
    local target="${1:-}"
    [[ -n "$target" ]] || {
        err "all: PATH required"
        usage >&2
        return 2
    }

    local record_file="${APM_GATE_RECORD_FILE:-$GATE_RECORD_DEFAULT}"
    local ts
    ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

    local scan_rc=0
    cmd_scan "$target" || scan_rc=$?

    local git_ref="" prov_rc=0
    git_ref="$(cmd_provenance)" || prov_rc=$?
    if [[ -z "$git_ref" ]]; then
        git_ref="$(git -C "${APM_GATE_REPO:-$PWD}" rev-parse --short HEAD 2> /dev/null || true)"
        [[ -n "$git_ref" ]] || git_ref="unknown"
    fi

    local subject_hash=""
    if [[ -d "$target" ]]; then
        subject_hash="$(apm_canonical_tree_hash "$target" 2> /dev/null || true)"
    fi

    local tool_version="unknown"
    if command -v gitleaks > /dev/null 2>&1; then
        tool_version="gitleaks/$(gitleaks version 2> /dev/null | tr -d '\n')"
    fi

    local result="$APM_GATE_RECORD_RESULT_PASS" overall_rc=0
    if [[ $scan_rc -ne 0 || $prov_rc -ne 0 || -z "$subject_hash" ]]; then
        result="$APM_GATE_RECORD_RESULT_FAIL"
        overall_rc=1
    fi

    local subject_abs="$target"
    [[ -d "$target" ]] && subject_abs="$(cd "$target" && pwd -P)"

    cmd_all_write_record "$record_file" "$ts" "$subject_abs" "$subject_hash" "$result" "$tool_version" "$git_ref"

    if [[ $overall_rc -eq 0 ]]; then
        printf 'apm_publish_gate.sh: all PASS — %s (ref=%s)\n' "$subject_abs" "$git_ref"
    else
        err "all: REJECTED — $subject_abs (scan_rc=$scan_rc provenance_rc=$prov_rc)"
    fi
    return $overall_rc
}

main() {
    local sub="${1:-}"
    shift || true
    case "$sub" in
        scan)
            cmd_scan "$@"
            return $?
            ;;
        provenance)
            cmd_provenance "$@"
            return $?
            ;;
        all)
            cmd_all "$@"
            return $?
            ;;
        *)
            err "unknown subcommand: ${sub:-<none>}"
            usage >&2
            return 2
            ;;
    esac
}

main "$@"
exit $?
