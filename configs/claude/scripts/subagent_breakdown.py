#!/usr/bin/env python3
"""Local dispatch audit and estimated API-equivalent usage breakdown.

--audit delegates to subagent_audit: explicit channel coverage, bounded redacted
records, and exit 2 when scoped evidence is incomplete. Requested models never
prove what served, and current agent definitions never prove historical pins.

Breakdown mode retains input/cache-write/cache-read/output separately and folds
streaming records by request ID. Missing IDs remain separate with a diagnostic:
without identity, exact deduplication is unknowable.
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import model_pricing
from subagent_audit import audit, parse_ts
from transcript_usage import usage_key, usage_message, warn_skipped

PROG = "subagent_breakdown.py"
ATTRS = ("attributionAgent", "attributionSkill", "attributionPlugin")
DEFAULT_STAMP = "~/.claude/config/deploy_stamp"


def err(*args: object) -> None:
    print(f"{PROG}:", *args, file=sys.stderr)


def usage() -> None:
    print(
        "Usage: subagent_breakdown.py [--audit] [--root DIR] [--since TS]\n"
        "  --channel C  agent-tool (default), workflow, fork, teams, external-cli, unknown, all\n"
        "  --until TS   inclusive ISO timestamp upper bound\n"
        "  --limit N    maximum audit detail records (default 100; totals stay complete)\n"
        "  --models M   breakdown model filter, or all (default opus)\n"
        "  --json PATH  private JSON report\n"
        "Audit exit: 0 observed scoped evidence; 2 incomplete or invalid input.\n"
        "No result certifies unsupported channels or historical resolution."
    )


def stamp_deployed_at(path: str) -> str | None:
    """Read ``deployed_at`` from the bootstrap deploy stamp."""
    try:
        with open(os.path.expanduser(path), encoding="utf-8") as fh:
            for line in fh:
                key, sep, value = line.partition("=")
                if sep and key.strip() == "deployed_at":
                    return value.strip()
    except OSError:
        return None
    return None


# --------------------------------------------------------------------------
# breakdown mode
# --------------------------------------------------------------------------


def collect(root, since, until, model_terms):
    """Fold assistant lines into one record per requestId."""
    requests = {}
    for dirpath, _, names in os.walk(root):
        # Transcripts nest as <project>/<session>/subagents/[workflows/<run>/]*.jsonl,
        # so os.path.basename would label a subagent's requests "subagents" or
        # "wf_<id>" instead of the project. Always take the first path component.
        rel = os.path.relpath(dirpath, root)
        project = "." if rel == "." else rel.split(os.sep)[0]
        for name in names:
            if not name.endswith(".jsonl"):
                continue
            try:
                with open(os.path.join(dirpath, name), errors="replace") as handle:
                    fold(handle, project, requests, since, until)
            except OSError:
                continue
    if model_terms:
        requests = {
            k: v
            for k, v in requests.items()
            if any(t in (v["model"] or "").lower() for t in model_terms)
        }
    return requests


def fold(handle, project, requests, since, until):
    for line in handle:
        if '"assistant"' not in line:
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        try:
            parsed = usage_message(rec)
        except ValueError:
            warn_skipped("malformed usage record")
            continue
        if parsed is None:
            continue
        message, usage_rec = parsed
        if since or until:
            stamp = parse_ts(rec.get("timestamp"))
            if stamp is None:
                continue
            if since and stamp < since:
                continue
            if until and stamp > until:
                continue
        key = usage_key(rec, message, requests)
        entry = requests.get(key)
        if entry is None:
            entry = requests[key] = {
                "model": message.get("model", "?"),
                "project": project,
                "sidechain": bool(rec.get("isSidechain")),
                "session": rec.get("sessionId"),
                "agent_id": rec.get("agentId"),
                "branch": rec.get("gitBranch"),
                "input": usage_rec.get("input_tokens") or 0,
                "cache_read": usage_rec.get("cache_read_input_tokens") or 0,
                "cache_creation": usage_rec.get("cache_creation_input_tokens") or 0,
                "output": 0,
            }
            for attr in ATTRS:
                entry[attr] = rec.get(attr)
        entry["output"] = max(entry["output"], usage_rec.get("output_tokens") or 0)
        # Attribution can be absent on some sibling lines of one request; keep the
        # first non-null rather than letting a later bare line erase it.
        for attr in ATTRS:
            if entry.get(attr) is None and rec.get(attr) is not None:
                entry[attr] = rec.get(attr)
    return requests


def cost_of(cell):
    return model_pricing.cost_usd(
        cell["model"],
        input_tokens=cell["input"],
        output_tokens=cell["output"],
        cache_read=cell["cache_read"],
        cache_creation=cell["cache_creation"],
    )


def tally(entries, keyfn):
    """Group entries; return {key: usage dict} with per-model cost summed."""
    groups = collections.defaultdict(
        lambda: {
            "requests": 0,
            "input": 0,
            "output": 0,
            "cache_read": 0,
            "cache_creation": 0,
            "sessions": set(),
            "agents": set(),
            "models": collections.Counter(),
            "cost": 0.0,
        }
    )
    for e in entries:
        g = groups[keyfn(e)]
        g["requests"] += 1
        for f in ("input", "output", "cache_read", "cache_creation"):
            g[f] += e[f]
        g["sessions"].add(e["session"])
        g["agents"].add(e["agent_id"])
        g["models"][e["model"]] += 1
        g["cost"] += cost_of(e) or 0.0
    return groups


def show(title, groups, limit=None, width=34):
    rows = sorted(groups.items(), key=lambda kv: -kv[1]["cost"])
    if limit:
        rows = rows[:limit]
    print(f"\n== {title} ==")
    print(
        f"{'key':<{width}}{'reqs':>7}{'cost':>10}{'output':>11}"
        f"{'sessions':>10}{'dispatches':>12}"
    )
    for key, g in rows:
        print(
            f"{str(key)[: width - 1]:<{width}}{g['requests']:>7,}${g['cost']:>9,.2f}"
            f"{g['output']:>11,}{len(g['sessions']):>10,}{len(g['agents']):>12,}"
        )


def breakdown(root, since, until, terms, args):
    requests = collect(root, since, until, terms)
    side = [e for e in requests.values() if e["sidechain"]]
    main_loop = [e for e in requests.values() if not e["sidechain"]]
    total_cost = sum(cost_of(e) or 0.0 for e in side)
    print(
        f"window since={args.since} until={args.until} models={args.models!r}\n"
        f"deduped requests={len(requests):,}  "
        f"subagent(sidechain)={len(side):,}  main-loop={len(main_loop):,}  "
        f"subagent cost=${total_cost:,.2f}"
    )
    show(
        "by agent type (attributionAgent)", tally(side, lambda e: e["attributionAgent"])
    )
    show(
        "by dispatching skill (attributionSkill; None = no skill config in path)",
        tally(side, lambda e: e["attributionSkill"]),
    )
    show("by plugin", tally(side, lambda e: e["attributionPlugin"]))
    show("by project", tally(side, lambda e: e["project"]), limit=12, width=52)
    show("by branch", tally(side, lambda e: e["branch"]), limit=12, width=40)
    show(
        "agent type x model",
        tally(side, lambda e: f"{e['attributionAgent']} | {e['model']}"),
        width=46,
    )
    if args.json:
        payload = {
            k: {
                str(key): {
                    "requests": g["requests"],
                    "cost_usd": round(g["cost"], 2),
                    "output": g["output"],
                    "sessions": len(g["sessions"]),
                    "dispatches": len(g["agents"]),
                    "models": dict(g["models"]),
                }
                for key, g in sorted(grp.items(), key=lambda kv: -kv[1]["cost"])
            }
            for k, grp in (
                ("by_agent", tally(side, lambda e: e["attributionAgent"])),
                ("by_skill", tally(side, lambda e: e["attributionSkill"])),
                ("by_project", tally(side, lambda e: e["project"])),
            )
        }
        payload["totals"] = {
            "subagent_requests": len(side),
            "subagent_cost_usd": round(total_cost, 2),
        }
        with open(args.json, "w") as fh:
            json.dump(payload, fh, indent=1)
            fh.write("\n")
        print(f"\nwrote {args.json}")
    return 0


def main(argv):
    if argv and argv[0] in ("--help", "-h"):
        usage()
        return 0
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--root", default="~/.claude/projects")
    p.add_argument("--since")
    p.add_argument("--until")
    p.add_argument("--models", default="opus")
    p.add_argument("--json")
    p.add_argument("--audit", action="store_true")
    p.add_argument(
        "--channel",
        default="agent-tool",
        choices=(
            "agent-tool",
            "workflow",
            "fork",
            "teams",
            "external-cli",
            "unknown",
            "all",
        ),
    )
    p.add_argument("--stamp", default=DEFAULT_STAMP)
    p.add_argument("--limit", type=int, default=100)
    args = p.parse_args(argv)

    if args.audit and not args.since:
        # The deploy point, not the commit point: until bootstrap.sh copied the
        # hook into ~/.claude, no dispatch could have been rewritten by it.
        args.since = stamp_deployed_at(args.stamp)
        if not args.since:
            err(f"no --since and no deployed_at in {args.stamp}")
            return 2

    since, until = parse_ts(args.since), parse_ts(args.until)
    if args.since and since is None:
        err("invalid --since")
        return 2
    if args.until and until is None:
        err("invalid --until")
        return 2

    if (since and until and since > until) or not 1 <= args.limit <= 1000:
        err("invalid window or --limit (expected 1..1000)")
        return 2

    root = os.path.expanduser(args.root)
    if not os.path.isdir(root):
        err(f"transcript root not found: {root}")
        return 2

    if args.audit:
        args.until = until
        try:
            return audit(root, since, args.channel, args)
        except (OSError, ValueError):
            err("audit incomplete: cannot read evidence or write report")
            return 2

    terms = [t.strip().lower() for t in args.models.split(",") if t.strip()]
    if "all" in terms:
        terms = []
    return breakdown(root, since, until, terms, args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
