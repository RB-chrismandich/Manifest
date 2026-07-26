#!/usr/bin/env python3
"""token_cost_report.py - measure real token/credit spend from Claude Code transcripts.

Scans Claude Code JSONL transcripts for API-usage records and reports
uncached/cache-read/cache-write/output token totals, credit-weighted units
(Anthropic cache multipliers), and the top sessions by cache-write spend.

Claude Code writes one JSONL ``assistant`` line per content block of a single
API response, and every sibling line repeats the response's ``usage`` object
-- naively summing per line multiply-counts a single API call (measured
~2.2x overcount on the full corpus). This script dedupes by ``requestId``
before aggregating; see ``scan()`` for the per-field reducer rationale.

Usage:
  token_cost_report.py [--root DIR] [--since ISO8601] [--until ISO8601] [--json PATH]

Options:
  --root DIR    directory to scan (default: ~/.claude/projects)
  --since TS    ignore records with a top-level timestamp before TS
  --until TS    ignore records with a top-level timestamp after TS
  --json PATH   also write the raw aggregate JSON to PATH
Exit codes: 0 ok, 2 usage / unusable input (bad --since/--until value,
unreadable transcript root, empty scan window, unwritable --json path).
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

try:
    import model_pricing
except ModuleNotFoundError:  # partial deploy — --help must still answer
    model_pricing = None

PROG = "token_cost_report.py"
DEFAULT_ROOT = "~/.claude/projects"
USAGE_KEYS = (
    "input_tokens",
    "output_tokens",
    "cache_read_input_tokens",
    "cache_creation_input_tokens",
)


def _iter_lines(path):
    """Yield lines from a transcript file; unreadable files yield nothing."""
    try:
        with open(path, errors="replace") as fh:
            yield from fh
    except OSError:
        return


def err(msg: str) -> None:
    print(f"{PROG}: {msg}", file=sys.stderr)


def _parse_ts(raw: str | None) -> datetime | None:
    """Parse a top-level transcript ``timestamp`` (or a --since/--until bound).

    Returns None on missing/unparseable input so callers can treat that as
    "unknown" rather than silently including or excluding the record.
    """
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.strip())
    except ValueError:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def scan(
    root: Path, since: datetime | None, until: datetime | None
) -> tuple[collections.Counter, dict, int, collections.Counter, dict, dict]:
    """Walk ``root`` for ``*.jsonl`` transcripts, dedupe by requestId, and
    aggregate usage.

    Returns (agg, per_session, files, counts, naive_agg, per_model) where ``agg``
    is the deduped/corrected totals, ``naive_agg`` is the raw per-line sum
    (the pre-fix, overcounted figure), and ``counts`` carries the self-check
    and time-filter bookkeeping (assistant_lines, records_in_range,
    skipped_no_timestamp, missing_request_id, api_requests).
    """
    boundary_active = since is not None or until is not None
    counts: collections.Counter = collections.Counter()
    naive_agg: collections.Counter = collections.Counter()
    by_request: dict[str, dict] = {}
    fallback_seq = 0

    files = 0
    for dirpath, _, names in os.walk(root):
        for n in names:
            if not n.endswith(".jsonl"):
                continue
            files += 1
            sid = os.path.join(os.path.basename(dirpath), n)
            for line in _iter_lines(os.path.join(dirpath, n)):
                if '"usage"' not in line:
                    continue
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                m = d.get("message") or {}
                u = m.get("usage") or {}
                if not u:
                    continue

                # NOTE: every count from here down is gated by the
                # since/until filter (when active) so that a fixed --until
                # yields byte-identical totals on a live, append-only
                # corpus -- do not count anything above this filter into a
                # reported/self-check figure, or new session data written
                # between runs will make "deterministic" output drift.
                if boundary_active:
                    ts_dt = _parse_ts(d.get("timestamp", ""))
                    if ts_dt is None:
                        counts["skipped_no_timestamp"] += 1
                        continue
                    if since is not None and ts_dt < since:
                        continue
                    if until is not None and ts_dt > until:
                        continue
                counts["records_in_range"] += 1
                counts["assistant_lines"] += 1

                for k in USAGE_KEYS:
                    naive_agg[k] += u.get(k) or 0
                naive_agg["api_calls"] += 1

                rid = d.get("requestId") or m.get("id")
                if not rid:
                    counts["missing_request_id"] += 1
                    fallback_seq += 1
                    rid = f"__no_request_id__{fallback_seq}"

                entry = by_request.get(rid)
                if entry is None:
                    # requestId siblings, one JSONL line per content block of
                    # the same API response: input/cache_read/cache_creation
                    # are per-request constants (identical on every sibling,
                    # verified across the full corpus), but output_tokens is
                    # the cumulative/streaming running total -- only the
                    # LAST-written (== max) sibling holds the true total.
                    # Take FIRST for the constants, MAX for output_tokens.
                    entry = {
                        "input_tokens": u.get("input_tokens") or 0,
                        "cache_read_input_tokens": u.get("cache_read_input_tokens")
                        or 0,
                        "cache_creation_input_tokens": u.get(
                            "cache_creation_input_tokens"
                        )
                        or 0,
                        "output_tokens": u.get("output_tokens") or 0,
                        "model": m.get("model", "?"),
                        "sid": sid,
                    }
                    by_request[rid] = entry
                else:
                    out_v = u.get("output_tokens") or 0
                    if out_v > entry["output_tokens"]:
                        entry["output_tokens"] = out_v

    agg: collections.Counter = collections.Counter()
    per_session: dict = collections.defaultdict(collections.Counter)
    per_model: dict = collections.defaultdict(collections.Counter)
    for entry in by_request.values():
        for k in USAGE_KEYS:
            agg[k] += entry[k]
            per_session[entry["sid"]][k] += entry[k]
            per_model[entry["model"]][k] += entry[k]
        agg["api_calls"] += 1
        per_session[entry["sid"]]["api_calls"] += 1
        per_model[entry["model"]]["api_calls"] += 1

    counts["api_requests"] = len(by_request)
    return agg, per_session, files, counts, naive_agg, per_model


def cost_by_model(per_model: dict) -> tuple[list[dict], float, dict]:
    """Cost each model's deduped usage.

    Returns (rows, priced_total, unpriced) — rows sorted by cost descending
    with unpriced models last. ``unpriced`` maps model -> request count so an
    unknown model is reported as a hole in the total, never as $0 spend.
    """
    rows = []
    unpriced: dict = {}
    total = 0.0
    for model, c in per_model.items():
        if model_pricing is None:  # partial deploy; --help already answered above
            err(
                "model_pricing.py must sit beside this script "
                "(deploy the whole configs/claude/scripts/ directory)"
            )
            raise SystemExit(2)
        cost = model_pricing.cost_usd(
            model,
            input_tokens=c["input_tokens"],
            output_tokens=c["output_tokens"],
            cache_read=c["cache_read_input_tokens"],
            cache_creation=c["cache_creation_input_tokens"],
        )
        if cost is None:
            unpriced[model] = c["api_calls"]
        else:
            total += cost
        rows.append(
            {
                "model": model,
                "requests": c["api_calls"],
                "cost_usd": None if cost is None else round(cost, 2),
            }
        )
    rows.sort(key=lambda r: (r["cost_usd"] is None, -(r["cost_usd"] or 0)))
    return rows, total, unpriced


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog=PROG,
        description=(
            "Measure deduped token/credit spend (uncached, cache read/write, "
            "output) from Claude Code JSONL transcripts."
        ),
    )
    p.add_argument(
        "--root",
        default=DEFAULT_ROOT,
        help="directory to scan (default: %(default)s)",
    )
    p.add_argument(
        "--since",
        metavar="ISO8601",
        default=None,
        help="ignore records with a timestamp before this value",
    )
    p.add_argument(
        "--until",
        metavar="ISO8601",
        default=None,
        help="ignore records with a timestamp after this value",
    )
    p.add_argument(
        "--json",
        metavar="PATH",
        default=None,
        help="also write the raw aggregate JSON to PATH",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    # --help must succeed before any filesystem access (repo convention:
    # cli-audit-help). argparse handles -h/--help here, before scan() ever
    # touches --root, and the default is expanded at runtime, not import time.
    args = _build_parser().parse_args(argv)
    root = Path(args.root).expanduser()

    since_dt = _parse_ts(args.since) if args.since is not None else None
    if args.since is not None and since_dt is None:
        err(f"invalid --since timestamp: {args.since!r}")
        return 2
    until_dt = _parse_ts(args.until) if args.until is not None else None
    if args.until is not None and until_dt is None:
        err(f"invalid --until timestamp: {args.until!r}")
        return 2

    if not root.is_dir():
        err(f"transcript root not found: {root}")
        return 2

    agg, per_session, files, counts, naive_agg, per_model = scan(
        root, since_dt, until_dt
    )

    # Bail before the report: every share/ratio below divides by a total, so an
    # empty window used to raise a raw ZeroDivisionError traceback. An empty
    # result must also never read as a clean zero-cost run.
    if not counts["api_requests"]:
        err(
            f"no API requests found in the scanned window (root={root}, "
            f"since={args.since}, until={args.until}) — {files} file(s) walked"
        )
        return 2

    tot_in = agg["input_tokens"]
    tot_out = agg["output_tokens"]
    cr = agg["cache_read_input_tokens"]
    cc = agg["cache_creation_input_tokens"]
    print(
        f"files={files} sessions_with_usage={len(per_session)} "
        f"api_requests={counts['api_requests']} (deduped)"
    )
    print()
    # Regression guard: raw per-line count vs deduped request count, plus the
    # naive-sum overcount factor per field. An anomalous ratio here (should be
    # a small multiple, not ~1.0x) means dedup silently broke.
    line_ratio = (
        counts["assistant_lines"] / counts["api_requests"]
        if counts["api_requests"]
        else 0
    )
    print(
        f"self-check: assistant_lines(raw)={counts['assistant_lines']}  "
        f"api_requests(deduped)={counts['api_requests']}  "
        f"line_overcount_ratio={line_ratio:.2f}x"
    )
    for k in USAGE_KEYS:
        factor = naive_agg[k] / agg[k] if agg[k] else 0
        print(f"  naive-sum overcount — {k}: {factor:.2f}x  (naive={naive_agg[k]:,})")
    print()
    print(f"uncached input : {tot_in:>14,}")
    print(f"cache READ     : {cr:>14,}   (cheap: 0.1x)")
    print(f"cache WRITE    : {cc:>14,}   (expensive: 1.25x)")
    print(f"output         : {tot_out:>14,}")
    print()
    denom = cr + cc
    print(
        f"cache hit ratio (read / (read+write)) = {100 * cr / denom:.1f}%"
        if denom
        else "no cache data"
    )
    print(
        f"cache WRITE as share of all input     = {100 * cc / (cc + cr + tot_in):.1f}%"
        if (cc + cr + tot_in)
        else ""
    )
    print()
    weighted_in = tot_in * 1.0 + cr * 0.1 + cc * 1.25
    print(f"credit-weighted input units : {weighted_in:>14,.0f}")
    print(
        f"  of which cache WRITE       : {cc * 1.25:>14,.0f}  "
        f"({100 * cc * 1.25 / weighted_in:.1f}%)"
    )
    print(
        f"  of which cache READ        : {cr * 0.1:>14,.0f}  "
        f"({100 * cr * 0.1 / weighted_in:.1f}%)"
    )
    print(
        f"  of which fresh input       : {tot_in:>14,.0f}  "
        f"({100 * tot_in / weighted_in:.1f}%)"
    )
    print()
    tops = sorted(
        per_session.items(), key=lambda x: -(x[1]["cache_creation_input_tokens"])
    )[:5]
    print("top 5 sessions by cache-WRITE (prefix invalidation):")
    for s, c in tops:
        print(
            f"  {c['cache_creation_input_tokens']:>12,}  "
            f"calls={c['api_calls']:>5}  {s[:70]}"
        )
    print()
    model_rows, priced_total, unpriced = cost_by_model(per_model)
    print(f"{'model':<28}{'reqs':>9}{'cost':>13}{'% of total':>12}")
    for row in model_rows:
        if row["cost_usd"] is None:
            print(f"{row['model']:<28}{row['requests']:>9,}{'unpriced':>13}{'—':>12}")
            continue
        share = 100 * row["cost_usd"] / priced_total if priced_total else 0
        print(
            f"{row['model']:<28}{row['requests']:>9,}"
            f"{'$' + format(row['cost_usd'], ',.2f'):>13}{share:>11.1f}%"
        )
    print(f"{'TOTAL (priced)':<28}{'':>9}{'$' + format(priced_total, ',.2f'):>13}")
    if unpriced:
        detail = ", ".join(f"{m} ({n:,} reqs)" for m, n in sorted(unpriced.items()))
        print(f"UNPRICED (excluded from the total): {detail}")

    if args.json:
        try:
            Path(args.json).write_text(
                json.dumps(
                    {
                        "agg": dict(agg),
                        "cost_by_model": model_rows,
                        "cost_total_usd": round(priced_total, 2),
                        "unpriced_models": unpriced,
                        "sessions": len(per_session),
                        "assistant_lines": counts["assistant_lines"],
                        "api_requests": counts["api_requests"],
                        "naive_agg": dict(naive_agg),
                        "scan": {
                            "root": str(root),
                            "since": args.since,
                            "until": args.until,
                            "records_in_range": counts["records_in_range"],
                            "skipped_no_timestamp": counts["skipped_no_timestamp"],
                            "missing_request_id": counts["missing_request_id"],
                        },
                    },
                    indent=1,
                )
                # Trailing newline keeps the committed snapshot stable under
                # pre-commit's end-of-file-fixer across regenerations.
                + "\n"
            )
        except OSError as exc:
            err(f"cannot write {args.json}: {exc}")
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
