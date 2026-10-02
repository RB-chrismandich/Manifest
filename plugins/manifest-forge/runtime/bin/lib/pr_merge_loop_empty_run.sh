# shellcheck shell=bash
# pr_merge_loop_empty_run.sh — repository-scoped consecutive-empty-run
# counter for pr_merge_loop.sh (FR-018a).
#
# Split out of pr_merge_loop.sh's lib/pr_merge_loop_fp.sh (C-SIZE/CON-002,
# ceiling 600) along the counter seam: everything here owns the flock-serialized
# empty_count_<scope_hash> file under STATE_DIR — EMPTY_RUN_PY (the counter
# program), cmd_empty_run (the fp-scope-keyed CLI path), and
# _monitor_empty_run (the remote-URL-keyed path the provider monitor uses when
# the provider refuses fp-scope). Sourced, not executed — depends on the
# caller having already defined STATE_DIR, err(), and (via
# lib/pr_merge_loop_gh.sh) gh_op and _repository_scope_json (see
# pr_merge_loop.sh).

# FR-018a, scoped + serialized: the consecutive-empty counter is per
# REPOSITORY — STATE_DIR defaults to a shared XDG dir, so an unscoped file
# would let one repo's idle passes stop another repo's loop. The filename is
# keyed on the same scope hash FINGERPRINT_PY computes (host\0owner_repo).
# Read-modify-write runs under an exclusive fcntl.flock on the counter file
# itself (the flock layer of the loop_lock.sh pattern, portable via python3 —
# macOS ships no flock(1)), so concurrent `run` processes can neither split an
# incr nor observe a torn counter. Scope unresolvable (gitlab / no remote) ->
# fail closed, never touch a shared file.
EMPTY_RUN_PY='
import fcntl
import hashlib
import json
import os
import sys

state_dir, scope_json, op = sys.argv[1:4]
scope = json.loads(scope_json)
host = scope["host"].lower().rstrip(".")
owner_repo = scope["owner_repo"]
scope_hash = hashlib.sha256((host + "\0" + owner_repo).encode()).hexdigest()
path = os.path.join(state_dir, "empty_count_" + scope_hash)
fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
try:
    fcntl.flock(fd, fcntl.LOCK_EX)
    raw = os.read(fd, 64).decode("ascii", "replace").strip()
    n = int(raw) if raw.isdigit() else 0
    if op == "incr":
        n += 1
    elif op == "reset":
        n = 0
    if op != "get":
        os.lseek(fd, 0, os.SEEK_SET)
        os.ftruncate(fd, 0)
        os.write(fd, str(n).encode("ascii"))
        os.fsync(fd)
finally:
    os.close(fd)
print(n)
'

cmd_empty_run() {
    local op="${1:-get}" scope
    case "$op" in get | incr | reset) ;; *)
        err "empty-run: get|incr|reset"
        return 64
        ;;
    esac
    mkdir -p "$STATE_DIR" 2> /dev/null || true
    scope="$(gh_op fp-scope)" || {
        err "empty-run: cannot resolve repository scope — fail closed"
        return 13
    }
    python3 -c "${EMPTY_RUN_PY}" "$STATE_DIR" "$scope" "$op" || {
        err "empty-run: counter update failed"
        return 13
    }
}

# _monitor_empty_run — the cmd_run_monitor counter variant. The counter itself
# stays per-repository and flock-serialized (EMPTY_RUN_PY), but scope cannot
# come from gh_op fp-scope there — that op is exactly what the provider
# refuses. _repository_scope_json derives the identical {host, owner_repo}
# scope from the origin remote URL, so the monitor and the full path share the
# same empty_count_<scope_hash> file for a repo.
_monitor_empty_run() {
    local scope
    mkdir -p "$STATE_DIR" 2> /dev/null || true
    scope="$(_repository_scope_json)" || {
        err "monitor: cannot resolve repository scope — fail closed"
        return 13
    }
    python3 -c "${EMPTY_RUN_PY}" "$STATE_DIR" "$scope" "$1" || {
        err "monitor: counter update failed"
        return 13
    }
}
