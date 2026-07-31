#!/usr/bin/env python3
"""Prune dangling local-path dependencies from an apm.yml (T5.2b, spec 674).

`apm-dev-sync` registers its staging directory as a local-path dependency. The
staging default lives under TMPDIR, so every run leaves behind an entry that the
OS later deletes underneath apm -- and nothing in apm's own tooling notices or
removes it. Measured on this machine: eleven such entries, ten of them created
by a bats suite that shelled out to the real deploy tool on every invocation.

Only entries that are BOTH local paths AND missing from disk are removed:

  * A published-package dependency (`name@version`) is never a path and is never
    touched.
  * A local path that still EXISTS is left alone. One dependency can supply more
    than one domain, so dropping a live one while un-gating a single domain
    would silently stand down a domain nobody asked about.

Line-based rather than a pyyaml round-trip on purpose: apm writes explanatory
comments into this file (the `targets:` resolution order, the accepted-values
list) and a load/dump cycle deletes all of them.

Usage: apm_prune_dangling_deps.py <apm.yml> [--dry-run]
Exit 0 whether or not anything was pruned; 1 only on a real failure.
"""

import os
import sys


def _is_local_path(value: str) -> bool:
    return value.startswith(("/", "./", "../", "~"))


def prune(lines: list[str]) -> tuple[list[str], list[str]]:
    """Return (new_lines, removed). Walks only the `dependencies:` block."""
    out: list[str] = []
    removed: list[str] = []
    in_deps = False
    in_list = False
    list_indent = ""
    for line in lines:
        stripped = line.rstrip("\n")
        # Any top-level key ends the dependencies block.
        if stripped and not stripped.startswith((" ", "\t", "#")):
            in_deps = stripped.startswith("dependencies:")
            in_list = False
            out.append(line)
            continue
        if in_deps and stripped.strip().endswith(":") and not stripped.strip().startswith("-"):
            # A sub-key such as `apm:` or `mcp:` opens a list.
            in_list = True
            list_indent = stripped[: len(stripped) - len(stripped.lstrip())]
            out.append(line)
            continue
        if in_deps and in_list and stripped.strip().startswith("- "):
            value = stripped.strip()[2:].strip().strip("'\"")
            if _is_local_path(value) and not os.path.exists(os.path.expanduser(value)):
                removed.append(value)
                continue
        out.append(line)

    # A sub-key whose every entry was pruned must become an explicit empty list,
    # or the key reads as null and apm treats that differently from "none".
    if removed:
        out = _close_emptied_lists(out)
    return out, removed


def _close_emptied_lists(lines: list[str]) -> list[str]:
    out = list(lines)
    for i, line in enumerate(out):
        stripped = line.rstrip("\n")
        if not (stripped.startswith("  ") and stripped.strip().endswith(":")):
            continue
        nxt = out[i + 1].strip() if i + 1 < len(out) else ""
        if not nxt.startswith("- "):
            out[i] = stripped + " []\n"
    return out


USAGE = """Usage: apm_prune_dangling_deps.py <apm.yml> [--dry-run]

Remove local-path dependencies that no longer exist on disk. A published-package
dependency is never touched, and a local path that still exists is left alone --
one dependency can supply more than one domain.

  --dry-run   list what would be pruned; write nothing
  --help      this text
"""


def main(argv: list[str]) -> int:
    # Before any file lookup, per this repo's help contract.
    if "--help" in argv[1:] or "-h" in argv[1:]:
        print(USAGE.strip())
        return 0
    args = [a for a in argv[1:] if not a.startswith("-")]
    dry_run = "--dry-run" in argv[1:]
    if len(args) != 1:
        print(USAGE.strip(), file=sys.stderr)
        return 2
    path = args[0]
    if not os.path.isfile(path):
        # Nothing to prune is not a failure: apm may simply not be configured.
        return 0
    with open(path, encoding="utf-8") as fh:
        lines = fh.readlines()
    new_lines, removed = prune(lines)
    for value in removed:
        print(f"apm_prune_dangling_deps.py: dangling {value}")
    if removed and not dry_run:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.writelines(new_lines)
        os.replace(tmp, path)
        print(f"apm_prune_dangling_deps.py: pruned {len(removed)} entry(ies) from {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
