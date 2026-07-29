#!/usr/bin/env bash
# apm_install_verify.sh — install-time package integrity verification
# (Phase 0, T050/FR-018). Independent of the `apm` tool itself: no native
# `apm` supply-chain capability is trusted before T005 measures one, so this
# re-derives the same canonical tree hash apm_publish_gate.sh's `all`
# subcommand recorded at publish time (via the shared apm_hash_lib.sh
# routine) and compares it against the fetched/installed tree. Works
# regardless of which registry model T005 ends up measuring (git-host or
# registry-protocol server) because it never talks to a registry itself —
# it only reads the append-only gate-records log and re-hashes local files.
#
# Record-lookup predicate: an installer always knows which ref it asked to
# install (e.g. `apm install pkg@v1.2.3` -> ref "v1.2.3"), so REF is supplied
# by the caller, not inferred. A candidate gate record must have
# gate == "apm_publish_gate.all", result == "pass", and git_ref == REF.
# Distinct-hash values among matching records are what make a lookup
# ambiguous (two DIFFERENT hashes claimed for one ref is an unresolvable
# conflict); duplicate identical records for the same ref (e.g. a rerun of
# the same publish) collapse to one candidate and are not treated as
# ambiguous. Zero candidates, more than one distinct hash, an unreadable
# records file, an unreadable tree, or a missing hash tool are all
# indeterminate and fail closed identically.
#
# Subcommand:
#   verify TREE_PATH --ref REF [--records FILE]
#
# Exit: 0 verified / 1 mismatch or indeterminate / 2 usage error.
# Env: APM_GATE_RECORD_FILE — default records file (same variable
#      apm_publish_gate.sh writes to); --records overrides it.

set -euo pipefail

err() { if [[ -t 2 ]]; then printf '\033[0;31m%s\033[0m\n' "apm_install_verify.sh: $*" >&2; else printf '%s\n' "apm_install_verify.sh: $*" >&2; fi; }

usage() {
    cat << 'USAGE'
Usage: apm_install_verify.sh verify TREE_PATH --ref REF [--records FILE]

  verify TREE_PATH --ref REF   Recompute TREE_PATH's canonical sha256 and
                                compare it to the single result:pass gate
                                record whose git_ref == REF. Any
                                indeterminacy (no record, ambiguous match,
                                unreadable tree, missing hash tool) rejects.
  --records FILE                Gate-records JSONL to read (default:
                                 APM_GATE_RECORD_FILE or the committed file).

Exit: 0 verified / 1 mismatch-or-indeterminate / 2 usage error.
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
RECORDS_DEFAULT="${REPO_ROOT}/specs/522-apm-deploy-migration/gate-records.jsonl"

# _apm_lookup_expected_hash RECORDS REF -> prints the single unambiguous
# subject_sha256 for a passing gate record matching REF, or returns 1.
# The "gate" id and "pass" result it matches on come from
# APM_GATE_RECORD_GATE_ID / APM_GATE_RECORD_RESULT_PASS (apm_hash_lib.sh) —
# the same constants apm_publish_gate.sh's writer uses — so this predicate
# can never drift from what was actually written.
_apm_lookup_expected_hash() {
    local records="$1" ref="$2"
    APM_REF="$ref" APM_GATE_ID="$APM_GATE_RECORD_GATE_ID" APM_RESULT_PASS="$APM_GATE_RECORD_RESULT_PASS" \
        python3 -c '
import json, os, sys

ref = os.environ.get("APM_REF", "")
gate_id = os.environ["APM_GATE_ID"]
result_pass = os.environ["APM_RESULT_PASS"]
hashes = set()
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        rec = json.loads(line)
    except Exception:
        continue
    if rec.get("gate") != gate_id:
        continue
    if rec.get("result") != result_pass:
        continue
    if rec.get("git_ref") != ref:
        continue
    h = rec.get("subject_sha256")
    if h:
        hashes.add(h)
if len(hashes) != 1:
    sys.exit(1)
print(next(iter(hashes)))
' < "$records"
}

cmd_verify() {
    local tree="${1:-}" ref="" records=""
    [[ -n "$tree" ]] || {
        err "verify: TREE_PATH required"
        usage >&2
        return 2
    }
    shift || true

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --ref)
                [[ -n "${2:-}" ]] || {
                    err "verify: --ref requires a value"
                    usage >&2
                    return 2
                }
                ref="$2"
                shift 2
                ;;
            --records)
                [[ -n "${2:-}" ]] || {
                    err "verify: --records requires a value"
                    usage >&2
                    return 2
                }
                records="$2"
                shift 2
                ;;
            *)
                err "verify: unknown argument: $1"
                usage >&2
                return 2
                ;;
        esac
    done

    [[ -n "$ref" ]] || {
        err "verify: --ref REF required"
        usage >&2
        return 2
    }
    records="${records:-${APM_GATE_RECORD_FILE:-$RECORDS_DEFAULT}}"

    [[ -f "$records" && -r "$records" ]] || {
        err "verify: gate-records file not found or unreadable: $records — indeterminate, rejecting"
        return 1
    }

    local expected
    expected="$(_apm_lookup_expected_hash "$records" "$ref")" || {
        err "verify: no unambiguous result:pass record for git_ref=$ref in $records — indeterminate, rejecting"
        return 1
    }
    [[ -n "$expected" ]] || {
        err "verify: recorded subject_sha256 empty for git_ref=$ref — indeterminate, rejecting"
        return 1
    }

    local actual
    actual="$(apm_canonical_tree_hash "$tree")" || {
        err "verify: could not hash $tree (unreadable tree or missing hash tool) — indeterminate, rejecting"
        return 1
    }

    if [[ "$actual" != "$expected" ]]; then
        err "verify: hash mismatch for $tree (git_ref=$ref expected=$expected actual=$actual)"
        return 1
    fi

    printf 'apm_install_verify.sh: OK %s matches git_ref=%s (%s)\n' "$tree" "$ref" "$actual"
    return 0
}

main() {
    local sub="${1:-}"
    shift || true
    case "$sub" in
        verify)
            cmd_verify "$@"
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
