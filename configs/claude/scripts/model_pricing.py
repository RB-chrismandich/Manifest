#!/usr/bin/env python3
"""model_pricing.py - list prices for Claude models, shared by the report CLIs.

One price table, imported by ``opus_attribution_report.py`` and
``token_cost_report.py`` so a cost figure in one report cannot silently
disagree with the other.

An UNKNOWN model resolves to ``None``, never to zero. A missing price must
surface as "unpriced" in the report -- a model silently costed at $0 is the
false-green this table exists to prevent.

Usage:
  model_pricing.py [--json]     print the price table and exit
Exit codes: 0 ok, 2 usage (unknown flag).
"""

from __future__ import annotations

import json
import sys

PROG = "model_pricing.py"

# Anthropic list price per million tokens, as (input, output).
#
# Cache tokens are priced as multiples of the model's own INPUT rate, so the
# two multipliers below apply across every row rather than per model.
#
# Deliberately NOT a family-prefix table ("claude-opus" -> ...): a prefix that
# broad would silently mis-price a future tier that shares the family name.
# Every rate here is an exact model, matched longest-prefix so dated snapshot
# ids (claude-haiku-4-5-20251001) resolve to their undated rate.
# Retired models keep their rates: this table classifies HISTORICAL transcript
# data, and dropping a retired id makes is_premium() return None (unclassified)
# for every past request that used it, silently weakening the premium audit.
PRICES: dict[str, tuple[float, float]] = {
    "claude-mythos-5": (10.00, 50.00),
    "claude-fable-5": (10.00, 50.00),  # retired 2026-08-17; priced for history
    "claude-opus-5": (5.00, 25.00),
    "claude-opus-4-8": (5.00, 25.00),
    "claude-opus-4-7": (5.00, 25.00),
    "claude-opus-4-6": (5.00, 25.00),
    "claude-sonnet-5": (3.00, 15.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-haiku-4-5": (1.00, 5.00),
}

# Cache read is billed at 0.1x the input rate; a 5-minute-TTL cache write at
# 1.25x. The 1h-TTL write is 2.0x -- transcripts do not record which TTL a
# request used, so these reports assume the 5m rate and therefore UNDERSTATE
# spend wherever 1h caching was in play. Stated so the figure is read as a
# floor, not a point estimate.
CACHE_READ_MULTIPLIER = 0.10
CACHE_WRITE_MULTIPLIER = 1.25

# Sonnet 5 carries introductory pricing ($2/$10 per MTok) through 2026-08-31.
# The table above uses list price so a baseline stays comparable after the
# intro window closes; Sonnet-5 costs are therefore an upper bound today.
INTRO_PRICING_NOTE = "claude-sonnet-5 list $3/$15; intro $2/$10 through 2026-08-31"


def rates(model: str | None) -> tuple[float, float] | None:
    """Return (input, output) $/MTok for ``model``, or None if unpriced.

    Longest-prefix match, so ``claude-haiku-4-5-20251001`` resolves to the
    ``claude-haiku-4-5`` rate while ``claude-sonnet-4-5`` (absent from the
    table) stays unpriced rather than borrowing a neighbour's rate.
    """
    if not model:
        return None
    if model in PRICES:
        return PRICES[model]
    best = ""
    for known in PRICES:
        if model.startswith(known) and len(known) > len(best):
            best = known
    return PRICES[best] if best else None


def weighted_input_units(
    input_tokens: int, cache_read: int, cache_creation: int
) -> float:
    """Fresh + cache tokens expressed in units of one fresh input token."""
    return (
        input_tokens
        + cache_read * CACHE_READ_MULTIPLIER
        + cache_creation * CACHE_WRITE_MULTIPLIER
    )


def cost_usd(
    model: str | None,
    *,
    input_tokens: int,
    output_tokens: int,
    cache_read: int,
    cache_creation: int,
) -> float | None:
    """Dollar cost of one model's usage, or None when the model is unpriced."""
    priced = rates(model)
    if priced is None:
        return None
    in_rate, out_rate = priced
    weighted = weighted_input_units(input_tokens, cache_read, cache_creation)
    return weighted / 1e6 * in_rate + output_tokens / 1e6 * out_rate


def main(argv: list[str]) -> int:
    if argv and argv[0] in ("--help", "-h"):
        print(__doc__.strip())
        return 0
    as_json = argv == ["--json"]
    if argv and not as_json:
        print(f"{PROG}: unknown argument: {argv[0]} (try --help)", file=sys.stderr)
        return 2
    if as_json:
        print(
            json.dumps(
                {
                    "prices_per_mtok": {k: list(v) for k, v in sorted(PRICES.items())},
                    "cache_read_multiplier": CACHE_READ_MULTIPLIER,
                    "cache_write_multiplier": CACHE_WRITE_MULTIPLIER,
                    "notes": [INTRO_PRICING_NOTE],
                },
                indent=1,
            )
        )
        return 0
    print(f"{'model':<24}{'$/MTok in':>12}{'$/MTok out':>12}")
    for model, (in_rate, out_rate) in sorted(PRICES.items()):
        print(f"{model:<24}{in_rate:>12.2f}{out_rate:>12.2f}")
    print()
    print(f"cache read  = {CACHE_READ_MULTIPLIER}x input rate")
    print(
        f"cache write = {CACHE_WRITE_MULTIPLIER}x input rate (5m TTL; 1h TTL is 2.0x)"
    )
    print(f"note: {INTRO_PRICING_NOTE}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
