#!/usr/bin/env python3
"""Squash-merge-aware hygiene data gatherer for the repo-hygiene skill.

Supplies the two pieces the existing backends (pr_review.sh / branch_clean.sh)
can't, in one platform-aware pass:

  1. Open-PR diff sizes  -> detect empty zero-diff "no-op" PRs that pr_review.sh
     would otherwise call mergeable (it has no changes-count field, and a PR with
     no files produces no checks, so its disposition defaults to "merge").

  2. Branch <-> PR-state correlation -> classify every local and remote branch by
     the merge-state of its PR/MR. This is what `git branch --merged` cannot see:
     on a squash-merge repo the merged branch's tip is never an ancestor of the
     default branch, so the conservative branch_clean.sh pass reports it as "not
     merged" and the real clutter stays hidden.

Read-only. Classifies and prints JSON; never closes a PR or deletes a branch.
Supports GitHub (gh) and GitLab (glab); degrades gracefully when a CLI is
missing or unauthenticated (the gap is reported in `errors`, never swallowed).
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import shutil
import subprocess
import sys
import time

DEFAULT_PROTECTED = ["main", "master", "release/*", "hotfix/*"]


def err(msg: str) -> None:
    print(f"hygiene_gather: {msg}", file=sys.stderr)


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True)


def git(*args: str) -> str:
    return run(["git", *args]).stdout.strip()


def detect_platform() -> str:
    url = git("remote", "get-url", "origin").lower()
    if "gitlab" in url:
        return "gitlab"
    if "github" in url:
        return "github"
    return "git"


def is_protected(name: str, default: str, current: str, globs: list[str]) -> bool:
    if name in (default, current):
        return True
    return any(fnmatch.fnmatch(name, g) for g in globs)


# --- platform PR/MR queries -------------------------------------------------

def gh_refs(state: str, errors: list[str]) -> dict[str, int]:
    """headRefName -> PR number for the given state (open|merged|closed)."""
    r = run(["gh", "pr", "list", "--state", state, "--limit", "500",
             "--json", "number,headRefName"])
    if r.returncode != 0:
        errors.append(f"gh pr list --state {state}: {r.stderr.strip() or 'failed'}")
        return {}
    return {pr["headRefName"]: pr["number"] for pr in json.loads(r.stdout or "[]")}


def gh_open_sizes(errors: list[str]) -> dict[int, dict]:
    """PR number -> diff size + empty flag for OPEN PRs."""
    r = run(["gh", "pr", "list", "--state", "open", "--limit", "500",
             "--json", "number,headRefName,changedFiles,additions,deletions"])
    if r.returncode != 0:
        errors.append(f"gh pr list sizes: {r.stderr.strip() or 'failed'}")
        return {}
    out = {}
    for pr in json.loads(r.stdout or "[]"):
        cf = pr.get("changedFiles", 0)
        out[pr["number"]] = {
            "head": pr["headRefName"],
            "changedFiles": cf,
            "additions": pr.get("additions", 0),
            "deletions": pr.get("deletions", 0),
            "empty": cf == 0,
        }
    return out


def glab_refs(flag: str, errors: list[str]) -> dict[str, int]:
    r = run(["glab", "mr", "list", flag, "-P", "200", "-F", "json"])
    if r.returncode != 0:
        errors.append(f"glab mr list {flag}: {r.stderr.strip() or 'failed'}")
        return {}
    refs = {}
    for mr in json.loads(r.stdout or "[]"):
        src = mr.get("source_branch")
        if src:
            refs[src] = mr.get("iid")
    return refs


# --- branch enumeration -----------------------------------------------------

def local_branches() -> list[dict]:
    fmt = "%(refname:short)\t%(upstream:track)\t%(committerdate:unix)"
    out = git("for-each-ref", "--format", fmt, "refs/heads")
    rows = []
    for line in filter(None, out.splitlines()):
        parts = line.split("\t")
        name = parts[0]
        track = parts[1] if len(parts) > 1 else ""
        cdate = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
        rows.append({"name": name, "gone": "[gone]" in track, "committed": cdate})
    return rows


def remote_branches(default: str) -> list[str]:
    out = git("for-each-ref", "--format", "%(refname:short)", "refs/remotes/origin")
    names = []
    for line in filter(None, out.splitlines()):
        short = line[len("origin/"):] if line.startswith("origin/") else line
        if short in ("HEAD", default) or "HEAD ->" in line:
            continue
        names.append(short)
    return names


def is_ancestor(ref: str, default: str) -> bool:
    return run(["git", "merge-base", "--is-ancestor", ref, default]).returncode == 0


def classify_local(b: dict, default: str, current: str, protected_globs: list[str],
                   merged: dict, closed: dict, stale_days: int, now: int) -> dict:
    name = b["name"]
    age_days = (now - b["committed"]) // 86400 if b["committed"] else None
    base = {"name": name, "age_days": age_days,
            "pr": merged.get(name) or closed.get(name)}
    if is_protected(name, default, current, protected_globs):
        base["classification"] = "protected" if name != current else "current"
        base["safe_delete"] = False
        return base
    if name in merged:
        base["classification"] = "merged-pr"      # squash-merge safe; needs -D
        base["safe_delete"] = True
    elif is_ancestor(name, default):
        base["classification"] = "merged-ff"        # branch_clean handles via -d
        base["safe_delete"] = True
    elif b["gone"]:
        base["classification"] = "gone"             # remote deleted
        base["safe_delete"] = True
    elif name in closed:
        base["classification"] = "closed-unmerged"  # confirm: abandoned work
        base["safe_delete"] = False
    elif age_days is not None and age_days >= stale_days:
        base["classification"] = "stale"            # confirm: no PR, old
        base["safe_delete"] = False
    else:
        base["classification"] = "no-pr-active"     # keep
        base["safe_delete"] = False
    return base


def classify_remote(name: str, merged: dict, closed: dict, open_refs: dict) -> dict:
    base = {"name": name, "pr": merged.get(name) or closed.get(name) or open_refs.get(name)}
    if name in open_refs:
        base["classification"] = "open-pr"          # keep: backs an open PR
        base["safe_delete"] = False
    elif name in merged:
        base["classification"] = "merged-pr"        # safe (opt-in remote delete)
        base["safe_delete"] = True
    elif name in closed:
        base["classification"] = "closed-unmerged"  # confirm
        base["safe_delete"] = False
    else:
        base["classification"] = "no-pr"            # confirm: unknown provenance
        base["safe_delete"] = False
    return base


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Squash-merge-aware PR/branch hygiene gatherer (read-only).")
    ap.add_argument("--platform", choices=["github", "gitlab", "git"],
                    help="Override platform autodetection.")
    ap.add_argument("--stale-days", type=int, default=90,
                    help="Days without a commit before a no-PR branch is stale (default 90).")
    ap.add_argument("--protect", action="append", default=[],
                    help="Extra protected glob (repeatable). Added to defaults.")
    args = ap.parse_args()

    errors: list[str] = []
    platform = args.platform or detect_platform()
    default = git("symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD")
    default = default.split("/")[-1] if default else "main"
    current = git("rev-parse", "--abbrev-ref", "HEAD")
    protected_globs = DEFAULT_PROTECTED + args.protect
    now = int(time.time())

    open_refs: dict = {}
    merged: dict = {}
    closed: dict = {}
    sizes: dict = {}

    if platform == "github":
        if not shutil.which("gh"):
            errors.append("gh not installed — cannot correlate PR state or detect empty PRs.")
        else:
            open_refs = gh_refs("open", errors)
            merged = gh_refs("merged", errors)
            closed = gh_refs("closed", errors)
            sizes = gh_open_sizes(errors)
    elif platform == "gitlab":
        if not shutil.which("glab"):
            errors.append("glab not installed — cannot correlate MR state.")
        else:
            open_refs = glab_refs("--opened", errors)
            merged = glab_refs("--merged", errors)
            closed = glab_refs("--closed", errors)
            errors.append("gitlab: empty-MR diff sizes not gathered (glab list lacks a changes count); "
                          "check `glab mr diff <iid>` for suspected no-ops.")
    else:
        errors.append("no GitHub/GitLab remote detected — branch correlation skipped; "
                      "rely on branch_clean.sh (merged-ff / gone / stale only).")

    locals_ = [classify_local(b, default, current, protected_globs,
                              merged, closed, args.stale_days, now)
               for b in local_branches()]
    remotes = [classify_remote(n, merged, closed, open_refs)
               for n in remote_branches(default)]

    result = {
        "platform": platform,
        "default_branch": default,
        "current_branch": current,
        "stale_days": args.stale_days,
        "open_pr_sizes": sizes,                 # github only; {} otherwise
        "empty_prs": [n for n, s in sizes.items() if s["empty"]],
        "merged_pr_refs": merged,
        "closed_pr_refs": closed,
        "branches": {"local": locals_, "remote": remotes},
        "errors": errors,
    }
    print(json.dumps(result, indent=2))
    # Exit non-zero only if we could gather *nothing* useful, so callers can tell
    # "clean repo" from "couldn't look".
    return 1 if errors and not (merged or closed or open_refs or locals_) else 0


if __name__ == "__main__":
    sys.exit(main())
