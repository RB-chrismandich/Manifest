#!/usr/bin/env bash
# help-coverage: exempt — sourced helper library, not a directly-invoked entry point
#
# apm_hash_lib.sh — shared library sourced by both apm_publish_gate.sh
# (records subject_sha256 at publish time, T048/FR-030 + T049/FR-038) and
# apm_install_verify.sh (recomputes and compares at install time, T050/
# FR-018). Two things live here specifically because both scripts must agree
# on them byte-for-byte or the publish side and the install side silently
# drift apart:
#
#   1. The canonical tree-hash routine (apm_canonical_tree_hash) and the
#      file-walk primitive it is built on (apm_walk_tree_files) — the latter
#      is also reused by apm_publish_gate.sh's content scan, so there is
#      exactly one definition of "which files under a tree count" instead of
#      two hand-synced copies.
#   2. The gate-record contract's identifying literals (the APM_GATE_RECORD_*
#      constants below) — the gate id and result strings that
#      apm_publish_gate.sh's writer and apm_install_verify.sh's reader must
#      agree on.
#
# Public surface (the only functions/vars external callers should use):
#   apm_walk_tree_files DIR        -> lists DIR's files (see below)
#   apm_canonical_tree_hash DIR    -> prints/returns 1 (see below)
#   APM_GATE_RECORD_GATE_ID, APM_GATE_RECORD_RESULT_PASS,
#   APM_GATE_RECORD_RESULT_FAIL    -> gate-record contract constants
# Everything else (_apm_hash_*) is a private implementation detail.
#
# Not a standalone entry point: source this file, do not execute it.

# --- gate-record contract (single source of truth for writer + reader) ---
# apm_publish_gate.sh's `all` subcommand writes one JSONL record per publish
# attempt using these literals; apm_install_verify.sh's record lookup
# matches on the same literals. Both scripts source this file and pass these
# constants into their respective Python blocks via env rather than
# hardcoding either value independently, so a future rename of the gate id
# or a result string can't silently drift between writer and reader.
# shellcheck disable=SC2034  # consumed by apm_publish_gate.sh / apm_install_verify.sh after sourcing this file
APM_GATE_RECORD_GATE_ID="apm_publish_gate.all"
# shellcheck disable=SC2034  # consumed by apm_publish_gate.sh / apm_install_verify.sh after sourcing this file
APM_GATE_RECORD_RESULT_PASS="pass"
# shellcheck disable=SC2034  # consumed by apm_publish_gate.sh / apm_install_verify.sh after sourcing this file
APM_GATE_RECORD_RESULT_FAIL="fail"

# --- file-tree walk (shared by hashing and by the publish gate's scan) ---

# apm_walk_tree_files DIR -> prints DIR's regular files (excluding .git),
# relative to DIR, NUL-delimited (never newline-delimited), sorted in the C
# locale (byte order — stable across machines/locales). Symlinks and
# directories are never listed. Prints nothing if DIR is missing/unreadable
# (not treated as an error here — callers that must distinguish "empty tree"
# from "unreadable DIR" check DIR themselves before calling, as
# apm_canonical_tree_hash does).
#
# NUL-delimited end to end (find -print0 -> sort -z -> a NUL-consuming read
# loop that strips the leading "./") on purpose: a filename containing a
# literal embedded newline is legal on APFS/ext4/HFS+ and git can carry one
# on POSIX, but is indistinguishable from a record separator to any
# newline-oriented pipeline (the previous `find -print | sed | sort` form).
# That let such a filename split into two synthetic relative paths, neither
# of which resolved to a real file, so its actual content was silently
# skipped by both the hash routine and the publish-gate content scan
# (Standing Constraint 3 requires indeterminate here to fail closed, not
# silently do nothing). `sort -z`/GNU `sort --zero-terminated` is present on
# both this project's BSD userland (Apple sort, verified empirically:
# `printf 'b\0a\0' | sort -z` orders correctly) and GNU coreutils (CI), so no
# third ordering mechanism (e.g. python3) is needed.
apm_walk_tree_files() {
    local dir="$1" raw
    (cd "$dir" 2> /dev/null && find . -type f ! -path './.git/*' -print0 2> /dev/null | LC_ALL=C sort -z) |
        while IFS= read -r -d '' raw; do
            printf '%s\0' "${raw#./}"
        done
}

# --- canonical tree hash ---

_apm_hash_tool=""

# _apm_hash_detect_tool — internal. Populates $_apm_hash_tool with the first
# available sha256 implementation. Returns 1 (indeterminate) if neither is
# on PATH.
_apm_hash_detect_tool() {
    if command -v shasum > /dev/null 2>&1; then
        _apm_hash_tool="shasum"
        return 0
    fi
    if command -v sha256sum > /dev/null 2>&1; then
        _apm_hash_tool="sha256sum"
        return 0
    fi
    _apm_hash_tool=""
    return 1
}

# _apm_hash_file FILE -> internal. Prints the lowercase hex sha256 digest of
# FILE, or returns 1 if it cannot be read or hashed. Requires
# _apm_hash_detect_tool to have already succeeded in this process.
_apm_hash_file() {
    local file="$1" out
    [[ -r "$file" ]] || return 1
    case "$_apm_hash_tool" in
        shasum) out="$(shasum -a 256 "$file" 2> /dev/null)" || return 1 ;;
        sha256sum) out="$(sha256sum "$file" 2> /dev/null)" || return 1 ;;
        *) return 1 ;;
    esac
    [[ -n "$out" ]] || return 1
    printf '%s\n' "${out%% *}"
}

# apm_canonical_tree_hash DIR -> prints the deterministic sha256 of DIR's
# content (walk via apm_walk_tree_files, sha256 each file, build a
# "<digest>  <relpath>\n" manifest in that sorted order, hash the manifest),
# or returns 1 (indeterminate) on any unreadable input or missing tool. This
# depends only on file contents and relative paths — never mtimes,
# permissions, or DIR's absolute location — so a hash computed at publish
# time and one recomputed at install time on a different machine agree.
# Safe to call repeatedly; leaves no state behind.
apm_canonical_tree_hash() {
    local dir="$1" rel abs digest manifest_file rc=0
    [[ -n "$dir" && -d "$dir" && -r "$dir" ]] || return 1
    _apm_hash_detect_tool || return 1

    manifest_file="$(mktemp "${TMPDIR:-/tmp}/apm-hash-manifest.XXXXXX")" || return 1

    while IFS= read -r -d '' rel; do
        [[ -z "$rel" ]] && continue
        abs="$dir/$rel"
        digest="$(_apm_hash_file "$abs")" || {
            rc=1
            break
        }
        printf '%s  %s\n' "$digest" "$rel" >> "$manifest_file"
    done < <(apm_walk_tree_files "$dir")

    if [[ $rc -eq 0 ]]; then
        _apm_hash_file "$manifest_file" || rc=1
    fi

    rm -f "$manifest_file"
    return $rc
}
