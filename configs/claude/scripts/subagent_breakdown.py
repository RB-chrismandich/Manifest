#!/usr/bin/env python3
"""subagent_breakdown.py — behavioral audit of sub-agent model selection.

Two modes over the same corpus (`~/.claude/projects`):

``--audit`` (the gate)
    Reads the ``agent-<id>.meta.json`` sidecar every dispatch writes next to its
    transcript, and asserts **zero inherited premium-model dispatches** since the
    deploy stamp. Exits 1 on violation.

    The sidecar is what makes this a behavioral check rather than another
    documentation check. ``meta.model`` records the model the dispatch
    *requested*; the transcript records the model that actually *served*. So the
    two cases MODEL-POLICY.md previously called indistinguishable are, in fact,
    distinguishable:

      requested=opus, served=opus      -> a permitted exception (adversarial
                                          verification); NOT a violation
      requested absent, served=opus    -> an inherited default; a violation

    Measured 2026-07-25: only 6 dispatches in the entire corpus ever explicitly
    requested opus. Every other premium sub-agent request — $951.70 of
    recoverable spend — was inherited.

(default) breakdown
    Groups the same deduplicated request population ``opus_attribution_report.py``
    counts, along the dispatch axes a routing policy can actually move:
    agent type, dispatching skill, plugin, session, project, branch.

Dedup rules are copied from opus_attribution_report.py deliberately: input and
cache fields are per-request constants (take first), output_tokens is cumulative
across streamed sibling lines (take max). Summing per line overcounts ~2.1x.

CHANNEL COVERAGE. Agent-tool dispatches are governed by the
``subagent_model_default.py`` PreToolUse hook. Workflow-tool agents (``agent()``
inside a Workflow script) do NOT pass through that hook — they are governed by
the script's own ``model`` option or CLAUDE_CODE_SUBAGENT_MODEL. The audit
reports the two channels separately and never lets one imply coverage of the
other; ``--channel`` scopes the exit code.
"""

from __future__ import annotations

import argparse
import collections
import glob
import json
import os
import sys
from datetime import UTC, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.expanduser("~/.claude/scripts"))
import model_pricing
from subagent_model_default import NO_MODEL_AGENTS, declared_model

PROG = "subagent_breakdown.py"
ATTRS = ("attributionAgent", "attributionSkill", "attributionPlugin")
DEFAULT_STAMP = "~/.claude/config/deploy_stamp"

# Premium is DERIVED from the price table, not hardcoded, so a newly-added model
# priced above Sonnet is caught the day it appears instead of the day someone
# remembers to extend a list.
_SONNET_INPUT_RATE = 3.00


def err(*args: object) -> None:
    print(f"{PROG}:", *args, file=sys.stderr)


def usage() -> None:
    print(
        "Usage: subagent_breakdown.py [--audit] [--since TS] [--root DIR]\n"
        "\n"
        "  --audit            assert zero INHERITED premium-model dispatches\n"
        "                     since --since; exit 1 on violation\n"
        "  --channel C        audit scope: agent-tool (default) | workflow | all\n"
        "  --since TS         ISO-8601; default = deployed_at in the deploy stamp\n"
        "  --root DIR         transcript root (default ~/.claude/projects)\n"
        "  --models M[,M]     breakdown filter, or 'all' (default: opus)\n"
        "  --json PATH        write the report as JSON\n"
        "\n"
        "Without --audit, prints the cost/usage breakdown by dispatch channel."
    )


def parse_ts(raw):
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def is_premium(model: str | None) -> bool | None:
    """True/False for a priced model; None when the model is unknown.

    None is propagated rather than folded into False so an unpriced model is
    reported as unclassified instead of silently passing the gate.
    """
    r = model_pricing.rates(model)
    if r is None:
        return None
    return r[0] > _SONNET_INPUT_RATE


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
# audit mode
# --------------------------------------------------------------------------


def transcript_models(path: str, since):
    """(models served, earliest assistant timestamp) for one agent transcript."""
    models: set[str] = set()
    first = None
    # An unreadable or truncated transcript yields whatever was parsed before the
    # error rather than discarding it: a partial read still proves which models
    # served, and the caller treats an empty result as "nothing ran in-window".
    try:
        with open(path, errors="replace") as handle:
            for line in handle:
                if '"assistant"' not in line:
                    continue
                if not line or (line[0] != "{" and line.lstrip()[:1] != "{"):
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if rec.get("type") != "assistant":
                    continue
                stamp = parse_ts(rec.get("timestamp"))
                if stamp is not None and (first is None or stamp < first):
                    first = stamp
                if since is not None and stamp is not None and stamp < since:
                    continue
                message = rec.get("message") or {}
                if message.get("model"):
                    models.add(message["model"])
    except OSError:
        pass
    return models, first


def collect_dispatches(root: str, since):
    """One record per dispatch, pairing each sidecar with its transcript."""
    out = []
    pattern = os.path.join(root, "**", "agent-*.meta.json")
    for meta_path in glob.iglob(pattern, recursive=True):
        # mtime is the last write, so it is >= every message time in the file:
        # if it precedes the window, nothing inside the file can fall inside it.
        # Cheap prefilter over thousands of transcripts; correctness is still
        # decided by the per-message timestamps below.
        if since is not None:
            try:
                if datetime.fromtimestamp(os.path.getmtime(meta_path), UTC) < since:
                    continue
            except OSError:
                continue
        try:
            with open(meta_path, encoding="utf-8") as fh:
                meta = json.load(fh)
        except (OSError, ValueError):
            continue
        if not isinstance(meta, dict):
            continue
        transcript = meta_path[: -len(".meta.json")] + ".jsonl"
        served, first = transcript_models(transcript, since)
        if not served:
            continue  # nothing ran in-window
        requested = meta.get("model")
        pinned_at_call = isinstance(requested, str) and requested.strip()
        # An agent definition's frontmatter `model:` is precedence layer 2 — a
        # deliberate choice that is NOT recorded in meta.model. Without this the
        # audit would flag every frontmatter-pinned agent (e.g.
        # pr-review-toolkit:code-reviewer, `model: opus`) as an inherited
        # default: exactly the dispatches the hook is required to leave alone.
        frontmatter_model = (
            None if pinned_at_call else declared_model(meta.get("agentType") or "")
        )
        agent_type = meta.get("agentType") or "?"
        # `fork` inherits the parent model BY DESIGN and ignores a `model` param,
        # so no dispatch can pin it and the hook deliberately skips it. Counting
        # it as a violation would make this gate permanently unachievable — the
        # audit would demand a fix that has no expressible form. Reported in its
        # own line instead, so it stays visible without being actionable-as-a-bug.
        unpinnable = agent_type.strip() in NO_MODEL_AGENTS
        out.append(
            {
                "path": meta_path,
                "agent_type": agent_type,
                "description": meta.get("description") or "",
                "requested": requested
                or (f"frontmatter:{frontmatter_model}" if frontmatter_model else None),
                "inherited": not pinned_at_call
                and frontmatter_model is None
                and not unpinnable,
                "unpinnable": unpinnable,
                "served": sorted(served),
                "workflow": f"{os.sep}workflows{os.sep}" in meta_path,
                "first": first,
            }
        )
    return out


def audit(root, since, channel, as_json):
    rows = collect_dispatches(root, since)
    if channel == "agent-tool":
        scoped = [r for r in rows if not r["workflow"]]
    elif channel == "workflow":
        scoped = [r for r in rows if r["workflow"]]
    else:
        scoped = rows

    violations, exceptions, unpinnable, unknown = [], [], [], []
    for r in scoped:
        flags = [is_premium(m) for m in r["served"]]
        if any(f is None for f in flags):
            unknown.append(r)
        if not any(f is True for f in flags):
            continue
        if r["unpinnable"]:
            unpinnable.append(r)
        elif r["inherited"]:
            violations.append(r)
        else:
            exceptions.append(r)

    since_txt = since.isoformat() if since else "(all time)"
    print(f"window since={since_txt}  root={root}")
    print(
        f"dispatches in window: {len(rows)} "
        f"(agent-tool {sum(1 for r in rows if not r['workflow'])}, "
        f"workflow {sum(1 for r in rows if r['workflow'])})"
    )
    print(f"audited channel: {channel} -> {len(scoped)} dispatch(es)")

    pinned = sum(1 for r in scoped if not r["inherited"])
    rate = (100.0 * pinned / len(scoped)) if scoped else 100.0
    print(f"explicit model pinned: {pinned}/{len(scoped)} ({rate:.1f}%)")
    print(
        f"permitted premium (deliberate: call-site or agent frontmatter): {len(exceptions)}"
    )
    for r in exceptions:
        print(
            f"    ok   {r['agent_type']}: requested={r['requested']} served={','.join(r['served'])}"
        )

    if unpinnable:
        print(
            f"unpinnable premium (agent types that ignore `model` by design, "
            f"e.g. fork): {len(unpinnable)} — not a violation, no fix exists; "
            f"lower them by changing the SESSION model"
        )
        for r in unpinnable:
            print(f"    n/a  {r['agent_type']}: served {','.join(r['served'])}")

    if unknown:
        print(f"unclassified models (not in the price table): {len(unknown)}")
        for r in unknown[:10]:
            print(f"    ??   {r['agent_type']}: served={','.join(r['served'])}")

    # The other channel is always reported, never audited silently: a clean
    # agent-tool result must not read as "sub-agent spend is under control".
    if channel == "agent-tool":
        other = [r for r in rows if r["workflow"]]
        leaked = [
            r
            for r in other
            if r["inherited"] and any(is_premium(m) is True for m in r["served"])
        ]
        print(
            f"NOT AUDITED HERE — workflow channel: {len(other)} dispatch(es), "
            f"{len(leaked)} inherited-premium (the Agent PreToolUse hook cannot reach these; "
            "pin per stage in the workflow script or set CLAUDE_CODE_SUBAGENT_MODEL)"
        )

    print(f"\nINHERITED PREMIUM DISPATCHES: {len(violations)}")
    for r in violations:
        print(
            f"    FAIL {r['agent_type']}: no model requested, served "
            f"{','.join(r['served'])}  [{os.path.basename(r['path'])}]"
        )
        if r["description"]:
            print(f"         {r['description'][:100]}")

    if as_json:
        payload = {
            "since": since_txt,
            "channel": channel,
            "dispatches": len(scoped),
            "pinned": pinned,
            "violations": [
                {
                    "agent_type": r["agent_type"],
                    "served": r["served"],
                    "description": r["description"],
                    "path": r["path"],
                }
                for r in violations
            ],
            "exceptions": [
                {
                    "agent_type": r["agent_type"],
                    "requested": r["requested"],
                    "served": r["served"],
                }
                for r in exceptions
            ],
            "unclassified": [
                {"agent_type": r["agent_type"], "served": r["served"]} for r in unknown
            ],
        }
        with open(as_json, "w") as fh:
            json.dump(payload, fh, indent=1)
            fh.write("\n")
        print(f"wrote {as_json}")

    if violations:
        err(f"{len(violations)} inherited premium-model dispatch(es) since {since_txt}")
        return 1
    print("OK — no inherited premium-model dispatches in the audited channel.")
    return 0


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
        if not line or (line[0] != "{" and line.lstrip()[:1] != "{"):
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if rec.get("type") != "assistant":
            continue
        message = rec.get("message") or {}
        usage_rec = message.get("usage") or {}
        if not usage_rec:
            continue
        if since or until:
            stamp = parse_ts(rec.get("timestamp"))
            if stamp is None:
                continue
            if since and stamp < since:
                continue
            if until and stamp > until:
                continue
        key = rec.get("requestId") or message.get("id")
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
        "--channel", default="agent-tool", choices=("agent-tool", "workflow", "all")
    )
    p.add_argument("--stamp", default=DEFAULT_STAMP)
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

    root = os.path.expanduser(args.root)
    if not os.path.isdir(root):
        err(f"transcript root not found: {root}")
        return 2

    if args.audit:
        return audit(root, since, args.channel, args.json)

    terms = [t.strip().lower() for t in args.models.split(",") if t.strip()]
    if "all" in terms:
        terms = []
    return breakdown(root, since, until, terms, args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
