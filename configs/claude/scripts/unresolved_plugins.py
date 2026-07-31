#!/usr/bin/env python3
"""Name installed plugins whose cache directory no longer exists (T4.5, spec 674).

Split into its own file rather than inlined into deploy.sh: a python heredoc
nested inside a shell function is where quoting bugs live, and this runs on the
restore path where a syntax error would be discovered at the worst moment.

Prints one plugin key per line, or nothing. Never raises: it runs on a restore
path that has already moved the user's live directory into a backup, and an
exception there is the worst possible moment to stop.

"Cannot tell" and "everything is fine" are DIFFERENT, and both are non-fatal: an
unreadable or malformed installed_plugins.json exits 3 with a note on stderr,
where the caller reports it, rather than exiting 0 with no output and letting a
corrupt plugins state read as a clean one.
"""

from __future__ import annotations

import json
import os
import sys


class Unreadable(Exception):
    """The state file could not be parsed -- distinct from 'nothing is wrong'."""


def unresolved(path: str) -> list[str]:
    """Installed plugin keys whose recorded installPath is gone."""
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError) as exc:
        raise Unreadable(str(exc)) from exc
    gone = set()
    plugins = data.get("plugins") if isinstance(data, dict) else None
    for key, entries in (plugins or {}).items():
        for entry in entries if isinstance(entries, list) else []:
            target = entry.get("installPath") if isinstance(entry, dict) else None
            if target and not os.path.isdir(target):
                gone.add(key)
    return sorted(gone)


USAGE = """Usage: unresolved_plugins.py <installed_plugins.json>

Print one installed-plugin key per line whose cached installPath is gone.

  --help   this text

Exit 0 = checked (output may be empty); 2 = no argument; 3 = state unreadable.
"""

if __name__ == "__main__":
    # Before opening anything. Without this, `--help` was passed straight to
    # unresolved() as a filename, printed nothing and exited 0 -- the tool
    # silently RAN instead of describing itself.
    if "--help" in sys.argv[1:] or "-h" in sys.argv[1:]:
        print(USAGE.strip())
        sys.exit(0)
    if len(sys.argv) < 2:
        print(USAGE.strip(), file=sys.stderr)
        sys.exit(2)
    try:
        names = unresolved(sys.argv[1])
    except Unreadable as exc:
        print(f"unresolved_plugins.py: cannot read state: {exc}", file=sys.stderr)
        sys.exit(3)
    for name in names:
        print(name)
