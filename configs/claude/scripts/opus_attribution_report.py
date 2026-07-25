#!/usr/bin/env python3
"""opus_attribution_report.py - classify Opus API requests by task class.

Attributes deduplicated Opus API requests across Claude Code transcripts to a
task class, so model-routing proposals can be costed against real spend.

Usage:
  opus_attribution_report.py [--root DIR] [--until ISO8601] [--since ISO8601]
                             [--json PATH] [--top-projects N]
Exit codes: 0 ok, 2 usage / unusable input (bad flag, bad window, bad root).
"""

import argparse
import collections
import json
import os
import statistics
import sys
from datetime import UTC, datetime

DEFAULT_ROOT = "~/.claude/projects"

# Tools whose use is mechanical / read-mostly, versus tools that mutate files.
MECHANICAL_TOOLS = {
    "Bash",
    "BashOutput",
    "Glob",
    "Grep",
    "LS",
    "NotebookRead",
    "Read",
    "TodoWrite",
}
EDIT_TOOLS = {"Edit", "MultiEdit", "NotebookEdit", "Write"}

# Anthropic relative price multipliers, expressed against fresh input = 1.0.
CACHE_READ_MULTIPLIER = 0.10
CACHE_WRITE_MULTIPLIER = 1.25


def die(code, msg):
    print(f"opus-attribution-report: {msg}", file=sys.stderr)
    sys.exit(code)


def parse_ts(raw):
    """Parse an ISO8601 transcript timestamp or --since/--until bound.

    Returns None when absent or unparseable. Bounds MUST be compared as
    datetimes, never as strings: a plain string compare silently accepts
    garbage (``"2026-..." > "banana"`` is False), which would leave the
    window unbounded and make a "reproducible" snapshot drift.
    """
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.strip())
    except ValueError:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def parse_args(argv):
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--root", default=DEFAULT_ROOT)
    p.add_argument("--since")
    p.add_argument("--until")
    p.add_argument("--json")
    p.add_argument("--top-projects", type=int, default=10)
    return p.parse_args(argv)


def collect(root, since, until):
    """Fold assistant JSONL lines into one record per API request.

    A single API response is written to the transcript as one line per content
    block, and EVERY one of those sibling lines repeats a usage object. Summing
    per line therefore multiply-counts one request (~2.2x on real corpora).
    Dedup by requestId, and note the two fields behave differently:
      - input/cache_read/cache_creation are per-request constants -> take first
      - output_tokens is CUMULATIVE across the streamed blocks   -> take max
    """
    requests = {}
    files = lines = skipped_no_timestamp = 0
    for dirpath, _, names in os.walk(root):
        project = os.path.basename(dirpath)
        for name in names:
            if not name.endswith(".jsonl"):
                continue
            files += 1
            try:
                with open(os.path.join(dirpath, name), errors="replace") as handle:
                    kept, skipped = fold_file(handle, project, requests, since, until)
            except OSError:
                continue
            lines += kept
            skipped_no_timestamp += skipped
    return requests, files, lines, skipped_no_timestamp


def fold_file(handle, project, requests, since, until):
    """Fold one transcript file into `requests`; return (kept, skipped) counts."""
    kept = skipped_no_timestamp = 0
    for line in handle:
        if '"assistant"' not in line:
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if rec.get("type") != "assistant":
            continue
        message = rec.get("message") or {}
        usage = message.get("usage") or {}
        if not usage:
            continue
        if since or until:
            stamp = parse_ts(rec.get("timestamp"))
            if stamp is None:
                skipped_no_timestamp += 1
                continue
            if since and stamp < since:
                continue
            if until and stamp > until:
                continue
        kept += 1
        key = rec.get("requestId") or message.get("id")
        entry = requests.get(key)
        if entry is None:
            entry = requests[key] = {
                "model": message.get("model", "?"),
                "project": project,
                "sidechain": bool(rec.get("isSidechain")),
                "input": usage.get("input_tokens") or 0,
                "cache_read": usage.get("cache_read_input_tokens") or 0,
                "cache_creation": usage.get("cache_creation_input_tokens") or 0,
                "output": 0,
                "types": set(),
                "tools": set(),
                "lines": 0,
            }
        entry["lines"] += 1
        entry["output"] = max(entry["output"], usage.get("output_tokens") or 0)
        for block in message.get("content", []):
            if not isinstance(block, dict):
                continue
            kind = block.get("type")
            if kind:
                entry["types"].add(kind)
            if kind == "tool_use" and block.get("name"):
                entry["tools"].add(block["name"])
    return kept, skipped_no_timestamp


def classify(entry):
    """Assign one task class, most specific first."""
    if entry["sidechain"]:
        return "subagent"
    # "fallback" marks a harness model switch, not work the model did.
    kinds = entry["types"] - {"fallback"}
    if kinds and kinds <= {"tool_use"}:
        if entry["tools"] & EDIT_TOOLS:
            return "tool_edit"
        if entry["tools"] and entry["tools"] <= MECHANICAL_TOOLS:
            return "tool_mechanical"
        return "other"
    if "thinking" in kinds:
        return "reasoning"
    if kinds == {"text"}:
        return "text_response"
    if "text" in kinds and "tool_use" in kinds:
        return "mixed"
    return "other"


def main(argv):
    if argv and argv[0] in ("--help", "-h"):
        print(__doc__.strip())
        return 0
    args = parse_args(argv)
    root = os.path.expanduser(args.root)
    if not os.path.isdir(root):
        die(2, f"transcript root not found: {root}")

    # Validate bounds up front: an unparseable --until must be a hard error,
    # not a silently-unbounded scan that still exits 0.
    bounds = {}
    for flag in ("since", "until"):
        raw = getattr(args, flag)
        if raw is None:
            bounds[flag] = None
            continue
        parsed = parse_ts(raw)
        if parsed is None:
            die(2, f"invalid --{flag} timestamp: {raw!r} (expected ISO8601)")
        bounds[flag] = parsed
    if bounds["since"] and bounds["until"] and bounds["since"] > bounds["until"]:
        die(2, f"--since {args.since!r} is after --until {args.until!r}")

    requests, files, lines, skipped = collect(root, bounds["since"], bounds["until"])

    per_class = collections.defaultdict(collections.Counter)
    outputs = collections.defaultdict(list)
    per_project = collections.defaultdict(collections.Counter)
    models = collections.Counter()
    opus = collections.Counter()

    for entry in requests.values():
        models[entry["model"]] += 1
        if "opus" not in entry["model"]:
            continue
        name = classify(entry)
        bucket = per_class[name]
        bucket["requests"] += 1
        for field in ("input", "output", "cache_read", "cache_creation"):
            bucket[field] += entry[field]
            opus[field] += entry[field]
        opus["requests"] += 1
        outputs[name].append(entry["output"])
        per_project[entry["project"]]["requests"] += 1
        per_project[entry["project"]][name] += 1

    if not opus["requests"]:
        die(2, "no Opus requests found in the scanned window")

    classes = {}
    for name, bucket in per_class.items():
        weighted = (
            bucket["input"]
            + bucket["cache_read"] * CACHE_READ_MULTIPLIER
            + bucket["cache_creation"] * CACHE_WRITE_MULTIPLIER
        )
        ordered = sorted(outputs[name])
        classes[name] = {
            "requests": bucket["requests"],
            "pct_requests": round(100 * bucket["requests"] / opus["requests"], 2),
            "input": bucket["input"],
            "output": bucket["output"],
            "cache_read": bucket["cache_read"],
            "cache_creation": bucket["cache_creation"],
            "weighted_input_units": round(weighted, 1),
            "median_output": statistics.median(ordered),
            "p90_output": ordered[int(0.9 * len(ordered))],
        }

    classified = opus["requests"] - classes.get("other", {}).get("requests", 0)
    report = {
        "scan": {
            "root": root,
            "since": args.since,
            "until": args.until,
            # NOTE: the raw files-walked count is deliberately NOT recorded
            # here. It grows with the corpus regardless of --until, so a
            # committed snapshot would show a spurious diff on every
            # regeneration. Only window-gated counts belong in the snapshot.
            "assistant_lines_with_usage": lines,
            "api_requests": len(requests),
            "overcount_factor": round(lines / len(requests), 4) if requests else 0,
            "skipped_no_timestamp": skipped,
        },
        "models": dict(models.most_common()),
        "opus_totals": dict(opus),
        "classified_pct": round(100 * classified / opus["requests"], 2),
        "classes": classes,
        "top_projects": {
            name: dict(counts)
            for name, counts in sorted(
                per_project.items(), key=lambda kv: -kv[1]["requests"]
            )[: args.top_projects]
        },
    }

    print(
        f"files={files}  assistant_lines={lines:,}  "
        f"api_requests={len(requests):,}  overcount={report['scan']['overcount_factor']}x"
    )
    print(f"opus requests={opus['requests']:,}  classified={report['classified_pct']}%")
    print()
    header = f"{'class':<16}{'reqs':>8}{'%':>7}{'output':>13}{'wtd_input':>16}{'med':>7}{'p90':>8}"
    print(header)
    for name, v in sorted(classes.items(), key=lambda kv: -kv[1]["requests"]):
        print(
            f"{name:<16}{v['requests']:>8,}{v['pct_requests']:>7.2f}"
            f"{v['output']:>13,}{v['weighted_input_units']:>16,.0f}"
            f"{v['median_output']:>7.0f}{v['p90_output']:>8,}"
        )

    if args.json:
        try:
            with open(args.json, "w") as fh:
                json.dump(report, fh, indent=1)
                fh.write("\n")
        except OSError as exc:
            die(2, f"cannot write {args.json}: {exc}")
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
