#!/usr/bin/env python3
"""block_cwd_delete.py — PreToolUse hook: never delete a live session's cwd.

Claude Code spawns every hook with ``cwd`` set to the session directory. Delete
that directory and the spawn fails before the command runs, with an error that
names the wrong thing:

    ENOENT: no such file or directory, posix_spawn '/bin/sh'

/bin/sh is present and healthy; the missing path is the *child's working
directory*, and Node attributes the errno to the binary. Reproduced directly:
``spawnSync('/bin/sh', …, {cwd: <deleted dir>})`` raises ENOENT while the same
spawn without the ``cwd`` option succeeds. Every hook in the session then fails
identically — ``echo`` no differently from ``python3`` — which is the tell that
the hooks themselves are innocent.

Measured incident, 2026-07-28T06:06Z: a session in one repo ran a
``git worktree remove`` sweep whose KEEP guard protected only its own cwd. The
list included the live cwd of a session in a *different* repo, which broke at
06:13:58 and recovered only when its Bash shell fell back to $HOME. So the
defended set is every live session's cwd, not this session's.

The project-scoped hookify rule that covered part of this could not: hookify
globs ``.claude/hookify.*.local.md`` relative to cwd, so it is armed only in
repos that carry the file, and it directed the operator to check ``pwd -P``,
which cannot see a sibling session.

DETECTION runs at two strengths, because the two failure modes pull opposite
ways.

  * TARGETS — literal arguments to a deletion verb (``git worktree remove``,
    recursive ``rm``, ``rmdir``) inside their own shell clause. Strong evidence:
    matched on equality OR containment, so removing a parent of a live cwd is
    caught too.
  * LOOSE — every path-shaped token anywhere in a command that contains a
    deletion verb. Needed because the incident command carried its targets in a
    ``for`` list and passed ``"$wt"`` to the verb, leaving argument parsing
    nothing to read. Matched on EQUALITY ONLY: a token whose role is unknown
    (a ``cd`` argument, a prompt, a log path) must not be treated as a
    deletion target just because it happens to contain someone's cwd. That
    asymmetry was found the hard way — the first version denied
    ``cd ~ && …`` on the strength of an ancestor match.

Fail-open by construction: any error, any unparseable payload, any unreadable
transcript directory prints nothing and exits 0. A guard that breaks the Bash
tool would be a worse bug than the one it prevents.

CLI:
    block_cwd_delete.py                  read hook payload on stdin
    block_cwd_delete.py --help

Escape hatch: append ``# cwd-verified`` to the command once the target is known
not to be anyone's cwd.

Env overrides (tests): CLAUDE_SESSIONS_DIR (default ~/.claude/projects),
BLOCK_CWD_DELETE_WINDOW_MIN (default 720), BLOCK_CWD_DELETE_DEBUG=1.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import shlex
import sys
import time

PROG = "block_cwd_delete.py"

# A session whose transcript has not been touched in this long is treated as
# gone. Generous on purpose: the cost of a stale entry is one extra
# confirmation, the cost of a missed live session is every hook in it.
DEFAULT_WINDOW_MIN = 720

# Only these open a directory-removal window. `mv` is deliberately absent:
# renaming a cwd breaks it the same way, but `mv` appears in far more benign
# commands and the false-positive rate is not worth it here.
DELETION_VERB = re.compile(
    r"""(?x)
    (?: \bgit \b [^;&|]*? \bworktree \s+ remove \b )
  | (?: \brm \b \s+ (?: -[^\s-]*[rR][^\s]* | --recursive \b ) )
  | (?: \brmdir \b )
    """
)

# The command was already reviewed by a human (or by the model, on the record).
OVERRIDE_MARKER = "cwd-verified"

# Tokens that cannot be paths, cheaply excluded before any filesystem work.
_NOT_A_PATH = re.compile(r"^(?:-|\$|\d+$|\W$)")


def err(*args: object) -> None:
    print(f"{PROG}:", *args, file=sys.stderr)


def usage() -> None:
    print(
        "Usage: block_cwd_delete.py [--help]\n"
        "\n"
        "PreToolUse hook for the Bash tool. Reads a hook payload on stdin and\n"
        "denies a directory removal whose target is — or contains — the working\n"
        "directory of any live Claude session, including sessions in other\n"
        "repositories.\n"
        "\n"
        "Live sessions come from the transcripts under CLAUDE_SESSIONS_DIR\n"
        "(default ~/.claude/projects) touched within\n"
        "BLOCK_CWD_DELETE_WINDOW_MIN minutes (default 720).\n"
        "\n"
        "Append `# cwd-verified` to the command to override.\n"
        "Prints nothing and exits 0 on any error or when nothing is at risk."
    )


def _last_cwd(path: str) -> str | None:
    """The `cwd` reported by the newest entry in a transcript.

    Reads the tail rather than the file: transcripts reach tens of megabytes and
    this runs on every deletion command.
    """
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as fh:
            if size > 65536:
                fh.seek(-65536, os.SEEK_END)
                fh.readline()  # discard the partial line seeking landed in
            lines = fh.read().splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        if b'"cwd"' not in line:
            continue
        try:
            record = json.loads(line)
        except ValueError:
            continue
        cwd = record.get("cwd") if isinstance(record, dict) else None
        if isinstance(cwd, str) and cwd:
            return cwd
    return None


def live_session_cwds(own_cwd: str | None) -> dict[str, str]:
    """Map each live session cwd -> the transcript that claims it."""
    holders: dict[str, str] = {}
    if own_cwd:
        holders[normalize(own_cwd)] = "this session"

    root = os.environ.get("CLAUDE_SESSIONS_DIR") or os.path.join(
        os.path.expanduser("~"), ".claude", "projects"
    )
    try:
        window = int(os.environ.get("BLOCK_CWD_DELETE_WINDOW_MIN", DEFAULT_WINDOW_MIN))
    except ValueError:
        window = DEFAULT_WINDOW_MIN
    cutoff = time.time() - window * 60

    try:
        projects = os.scandir(root)
    except OSError:
        return holders
    with projects:
        for project in projects:
            if not project.is_dir():
                continue
            try:
                entries = list(os.scandir(project.path))
            except OSError:
                continue
            for entry in entries:
                if not entry.name.endswith(".jsonl"):
                    continue
                try:
                    if entry.stat().st_mtime < cutoff:
                        continue
                except OSError:
                    continue
                cwd = _last_cwd(entry.path)
                if cwd:
                    holders.setdefault(normalize(cwd), entry.name[:-6])
    return holders


def normalize(path: str) -> str:
    """Absolute, symlink-resolved where possible, no trailing separator."""
    resolved = os.path.abspath(os.path.expanduser(path))
    with contextlib.suppress(OSError):
        resolved = os.path.realpath(resolved)
    return resolved.rstrip(os.sep) or os.sep


def _tokenize(text: str) -> list[str]:
    try:
        return shlex.split(text, comments=False)
    except ValueError:
        return re.findall(r"[^\s;&|()'\"]+", text)


def _paths(tokens: list[str], base: str) -> list[str]:
    """The tokens that could name a directory, resolved against base."""
    out: list[str] = []
    for token in tokens:
        token = token.strip().rstrip(";")
        if not token or _NOT_A_PATH.match(token):
            continue
        if "$" in token or "*" in token or "?" in token:
            continue  # unexpanded — nothing reliable to compare
        if " " in token:
            continue  # a quoted sentence (a prompt, a message), not a path
        if token.startswith(("/", "~", "./", "../")) or "/" in token:
            out.append(normalize(os.path.join(base, os.path.expanduser(token))))
    return out


def deletion_targets(command: str, cwd: str | None) -> list[str]:
    """Literal arguments to a deletion verb, clause by clause."""
    base = cwd or os.getcwd()
    out: list[str] = []
    for clause in re.split(r"[;&|\n]+", command):
        match = DELETION_VERB.search(clause)
        if not match:
            continue
        out.extend(_paths(_tokenize(clause[match.end() :]), base))
    return out


def mentioned_paths(command: str, cwd: str | None) -> list[str]:
    """Every path-shaped token in the command, whatever its role."""
    return _paths(_tokenize(command), cwd or os.getcwd())


def endangered(
    target: str, holders: dict[str, str], *, containment: bool
) -> tuple[str, str] | None:
    """The first live cwd this target would destroy, with its holder."""
    for cwd, holder in holders.items():
        if target == cwd or (containment and cwd.startswith(target + os.sep)):
            return cwd, holder
    return None


def decide(payload: dict) -> dict | None:
    if payload.get("tool_name") not in (None, "Bash"):
        return None
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    command = tool_input.get("command")
    if not isinstance(command, str) or not command.strip():
        return None
    if OVERRIDE_MARKER in command:
        return None
    if not DELETION_VERB.search(command):
        return None

    cwd = payload.get("cwd") if isinstance(payload.get("cwd"), str) else None
    holders = live_session_cwds(cwd)
    if not holders:
        return None

    # Verb arguments are strong evidence (equality or containment); a bare
    # mention is weak (equality only). See the DETECTION note in the docstring.
    for targets, containment in (
        (deletion_targets(command, cwd), True),
        (mentioned_paths(command, cwd), False),
    ):
        for target in targets:
            hit = endangered(target, holders, containment=containment)
            if hit is None:
                continue
            victim, holder = hit
            relation = "is" if target == victim else "contains"
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": (
                        f"{target} {relation} the working directory of a live "
                        f"Claude session ({victim}, held by {holder}). Deleting "
                        "it breaks every subsequent process spawn in that "
                        "session with a misleading `ENOENT ... posix_spawn "
                        "'/bin/sh'` — the shell is fine, the child's cwd is "
                        "gone.\n"
                        "\n"
                        "Before re-running: close that session, or use "
                        "ExitWorktree for a harness worktree, or leave the "
                        "cleanup until it ends. A sweep over many worktrees "
                        "must exclude EVERY live session's cwd, not only your "
                        "own.\n"
                        "\n"
                        f"If the session is already gone, re-run with the "
                        f"marker: `<command>  # {OVERRIDE_MARKER}`"
                    ),
                }
            }
    return None


def main(argv: list[str]) -> int:
    if argv and argv[0] in ("--help", "-h"):
        usage()
        return 0
    try:
        raw = sys.stdin.read()
    except (OSError, ValueError):
        return 0
    try:
        payload = json.loads(raw)
    except (ValueError, TypeError):
        return 0
    if not isinstance(payload, dict):
        return 0
    try:
        out = decide(payload)
    except Exception as exc:  # fail-open: never break the Bash tool
        if os.environ.get("BLOCK_CWD_DELETE_DEBUG") == "1":
            err(f"fail-open: {exc!r}")
        return 0
    if out is not None:
        print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
