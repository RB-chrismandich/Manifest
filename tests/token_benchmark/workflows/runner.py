"""Workflow trial orchestration: fresh isolated trials, deterministic-miss
repair (at most two recovery calls, public-criteria-only), and balanced
condition rotation across repeated trials.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from tests.token_benchmark.harness import compute_cost
from tests.token_benchmark.workflows.evaluate import evaluate
from tests.token_benchmark.workflows.fixtures import (
    build_repair_request,
    build_request,
    load_fixture,
)
from tests.token_benchmark.workflows.records import (
    SCHEMA_VERSION,
    SUITE,
    validate_record,
)

MAX_REPAIR_ATTEMPTS = 2
CONDITIONS = ("none", "slim", "full")
ROTATIONS = (
    ("none", "slim", "full"),
    ("slim", "full", "none"),
    ("full", "none", "slim"),
)

InvokeFn = Callable[..., Awaitable[dict]]


@dataclass(frozen=True)
class TrialContext:
    """Settings that travel together through one trial and its repairs."""

    invoke_fn: InvokeFn
    executor: object | None
    provider: str
    model: str
    timeout_s: float


@dataclass(frozen=True)
class _RepairState:
    prior_response: str
    failed_criteria: list[str]
    attempt_index: int


def rotation_for_trial(trial_index: int, conditions: Sequence[str]) -> tuple[str, ...]:
    """Return the balanced condition order for one repetition.

    Rotates through the three canonical orderings only when the requested
    condition set is exactly {none, slim, full}; a custom subset has no
    canonical Latin square and is run in the order given.
    """
    if set(conditions) == set(CONDITIONS):
        return ROTATIONS[trial_index % len(ROTATIONS)]
    return tuple(conditions)


def _usage_reason(result: dict) -> str | None:
    if result["input_tokens"] is not None and result["output_tokens"] is not None:
        return None
    if result["status"] != "completed":
        return result.get("reason") or f"no usage: trial status {result['status']}"
    return "not reported"


def _not_needed_repair() -> dict:
    return {
        "status": "not_needed",
        "attempts": [],
        "latency_ms": 0,
        "input_tokens": None,
        "output_tokens": None,
        "cost_usd": None,
    }


def _unavailable_repair() -> dict:
    return {
        "status": "unavailable",
        "attempts": [],
        "latency_ms": 0,
        "input_tokens": None,
        "output_tokens": None,
        "cost_usd": None,
    }


async def _attempt_repair(
    fixture: dict, condition: str, ctx: TrialContext, state: _RepairState
):
    """Run one isolated recovery call. Returns (attempt_record, response_text_or_None)."""
    request = build_repair_request(
        fixture, condition, state.prior_response, state.failed_criteria
    )
    result = await ctx.invoke_fn(
        request, provider=ctx.provider, model=ctx.model, timeout_s=ctx.timeout_s
    )
    verification = None
    if result["status"] == "completed":
        verdict = evaluate(fixture, result["response_text"], executor=ctx.executor)
        verification = verdict["verification"]
    attempt = {
        "attempt_id": f"repair-{state.attempt_index}",
        "status": result["status"],
        "verification": verification,
        "input_tokens": result["input_tokens"],
        "output_tokens": result["output_tokens"],
        "latency_ms": result["latency_ms"],
        "reason": result.get("reason"),
    }
    response_text = result["response_text"] if result["status"] == "completed" else None
    return attempt, response_text


def _aggregate_repair_usage(attempts: list[dict]) -> tuple[int, int | None, int | None]:
    latency = sum(a["latency_ms"] or 0 for a in attempts)
    if any(a["input_tokens"] is None or a["output_tokens"] is None for a in attempts):
        return latency, None, None
    return (
        latency,
        sum(a["input_tokens"] for a in attempts),
        sum(a["output_tokens"] for a in attempts),
    )


async def _run_repair(
    fixture: dict,
    condition: str,
    ctx: TrialContext,
    initial_response: str,
    failed_criteria: list[str],
) -> dict:
    """At most two isolated recovery calls after a deterministic miss, each
    supplied the prior artifact plus only the failed public criterion ids."""
    attempts: list[dict] = []
    prior_response = initial_response
    status = "unresolved"
    for attempt_index in range(1, MAX_REPAIR_ATTEMPTS + 1):
        state = _RepairState(prior_response, list(failed_criteria), attempt_index)
        attempt, response_text = await _attempt_repair(fixture, condition, ctx, state)
        attempts.append(attempt)
        if attempt["verification"] == "passed":
            status = "recovered"
            break
        if response_text is not None:
            prior_response = response_text
    latency_ms, input_tokens, output_tokens = _aggregate_repair_usage(attempts)
    return {
        "status": status,
        "attempts": attempts,
        "latency_ms": latency_ms,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": compute_cost(
            {"input_tokens": input_tokens, "output_tokens": output_tokens}, ctx.model
        ),
    }


@dataclass(frozen=True)
class _TrialOutcome:
    result: dict
    verification: str
    constraint_results: dict
    repair: dict


def _build_record(
    fixture: dict,
    request: dict,
    trial_id: str,
    ctx: TrialContext,
    outcome: _TrialOutcome,
) -> dict:
    result = outcome.result
    return {
        "schema_version": SCHEMA_VERSION,
        "suite": SUITE,
        "condition": request["condition"],
        "fixture_id": fixture["fixture_id"],
        "fixture_hash": request["fixture_hash"],
        "context_hash": request["context_hash"],
        "source_revision": fixture["source_revision"],
        "trial_id": trial_id,
        "provider": ctx.provider,
        "model": result["model"],
        "effort": result["effort"],
        "tool_access": result["tool_access"],
        "status": result["status"],
        "verification": outcome.verification,
        "constraint_results": outcome.constraint_results,
        "latency_ms": result["latency_ms"],
        "input_tokens": result["input_tokens"],
        "output_tokens": result["output_tokens"],
        "cost_usd": compute_cost(result, result["model"]) if result["model"] else None,
        "usage_unavailable_reason": _usage_reason(result),
        "repair": outcome.repair,
    }


# constitution: exempt C-SIZE — plan-mandated public interface (Task 5 §5)
async def run_trial(
    fixture: dict,
    condition: str,
    *,
    invoke_fn: InvokeFn,
    executor: object | None,
    provider: str,
    model: str,
    trial_id: str,
    timeout_s: float,
) -> dict:
    """Run one fresh, isolated workflow trial with deterministic-miss repair.

    Each trial builds its own request and calls `invoke_fn` independently;
    no state is shared with any other trial's repair sequence.
    """
    ctx = TrialContext(invoke_fn, executor, provider, model, timeout_s)
    request = build_request(fixture, condition)
    result = await invoke_fn(
        request, provider=provider, model=model, timeout_s=timeout_s
    )

    verification = "unavailable"
    constraint_results: dict = {}
    repair = _not_needed_repair()
    if result["status"] == "completed":
        verdict = evaluate(fixture, result["response_text"], executor=executor)
        verification = verdict["verification"]
        constraint_results = verdict["constraint_results"]
        if verification == "unavailable":
            repair = _unavailable_repair()
        elif verification == "failed":
            repair = await _run_repair(
                fixture,
                condition,
                ctx,
                result["response_text"],
                verdict["failed_criteria"],
            )

    outcome = _TrialOutcome(result, verification, constraint_results, repair)
    return _build_record(fixture, request, trial_id, ctx, outcome)


async def run_workflow_suite(
    root: Path,
    fixture_ids: Sequence[str],
    conditions: Sequence[str],
    trials: int,
    config: TrialContext,
) -> list[dict]:
    """Run every fixture across `trials` repetitions with balanced condition
    rotation; returns one validated record per (fixture, trial, condition)."""
    records: list[dict] = []
    for fixture_id in fixture_ids:
        fixture = load_fixture(root, fixture_id)
        for trial_index in range(trials):
            for condition in rotation_for_trial(trial_index, conditions):
                trial_id = f"{fixture_id}-{condition}-run-{trial_index}"
                record = await run_trial(
                    fixture,
                    condition,
                    invoke_fn=config.invoke_fn,
                    executor=config.executor,
                    provider=config.provider,
                    model=config.model,
                    trial_id=trial_id,
                    timeout_s=config.timeout_s,
                )
                validate_record(record)
                records.append(record)
    return records
