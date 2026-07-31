#!/usr/bin/env python3
"""Name installed plugins whose cache directory no longer exists (T4.5, spec 674).

Split into its own file rather than inlined into deploy.sh: a python heredoc
nested inside a shell function is where quoting bugs live, and this runs on the
restore path where a syntax error would be discovered at the worst moment.

Prints one plugin key per line, or nothing. Never raises: an unreadable or
malformed installed_plugins.json means "cannot tell", which must not be reported
as "everything is fine" -- but neither may it abort a restore that has already
moved the user's live directory into a backup.
"""

from __future__ import annotations

import json
import os
import sys


def unresolved(path: str) -> list[str]:
    """Installed plugin keys whose recorded installPath is gone."""
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return []
    gone = set()
    plugins = data.get("plugins") if isinstance(data, dict) else None
    for key, entries in (plugins or {}).items():
        for entry in entries if isinstance(entries, list) else []:
            target = entry.get("installPath") if isinstance(entry, dict) else None
            if target and not os.path.isdir(target):
                gone.add(key)
    return sorted(gone)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(0)
    for name in unresolved(sys.argv[1]):
        print(name)
