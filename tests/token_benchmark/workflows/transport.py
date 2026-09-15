"""Bounded, no-tool workflow model transport.

Resolves the requested policy tier through the shared model-policy resolver
and invokes an isolated provider adapter. Credentials are read directly from
the process environment by each adapter (`measure_api_claude`/
`measure_api_gemini` in `tests/token_benchmark/harness.py`); they never
appear in the fixture request payload built by `fixtures.build_request()`,
nor in any value this module returns. No CLI, home directory, or session
state is consulted here.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

import yaml
from manifest_model_policy import ModelPolicyError
from manifest_model_policy.resolver import resolve_chain

REPO_ROOT = Path(__file__).resolve().parents[3]
MODEL_POLICY_PATH = REPO_ROOT / "configs" / "claude" / "config" / "model_policy.yml"

# Providers with a verified, isolated, no-tool API path in this repository.
# Every other harness routes through a CLI whose isolation this transport
# cannot guarantee (no verified way to suppress tool access or session
# state), so it is recorded "unsupported" rather than invoked (Task 5 #2).
SUPPORTED_PROVIDERS = ("claude", "gemini")

AdapterFn = Callable[[str, str, str], Awaitable[dict]]


@dataclass(frozen=True)
class TransportOverrides:
    """Injectable test seam: swap the provider registry and/or the policy
    document without touching real credentials, the network, or disk."""

    adapters: dict[str, AdapterFn] | None = None
    policy: dict | None = None


def load_model_policy(path: Path | None = None) -> dict:
    """Read model_policy.yml fresh; no caching, no home fallback."""
    policy_path = path or MODEL_POLICY_PATH
    with policy_path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _resolve_model_id(provider: str, tier: str, policy: dict) -> str | None:
    try:
        resolved = resolve_chain(policy, provider, [tier])
    except ModelPolicyError:
        return None
    return resolved[0].model_id


def _prompt_text(request: dict) -> str:
    """Render the fixture request as a single bounded user prompt."""
    payload = {
        "instruction": request["instruction"],
        "artifacts": request["artifacts"],
        "output_contract": request["output_contract"],
    }
    if request.get("repair"):
        payload["repair"] = request["repair"]
    return (
        "Respond with a single JSON object matching output_contract exactly, "
        "and nothing else.\n\n" + json.dumps(payload, sort_keys=True)
    )


def _unsupported(reason: str) -> dict:
    return {
        "response_text": None,
        "input_tokens": None,
        "output_tokens": None,
        "latency_ms": None,
        "model": None,
        "effort": None,
        "tool_access": [],
        "status": "unsupported",
        "reason": reason,
    }


async def _call_claude(prompt: str, system_prompt: str, model_id: str) -> dict:
    from tests.token_benchmark.harness import measure_api_claude

    return await measure_api_claude(prompt, system_prompt, model_id)


async def _call_gemini(prompt: str, system_prompt: str, model_id: str) -> dict:
    from tests.token_benchmark.harness import measure_api_gemini

    return await measure_api_gemini(prompt, system_prompt, model_id)


DEFAULT_ADAPTERS: dict[str, AdapterFn] = {
    "claude": _call_claude,
    "gemini": _call_gemini,
}


def _completed_result(result: dict, resolved_model: str, status: str, reason) -> dict:
    return {
        "response_text": result.get("response_text"),
        "input_tokens": result.get("input_tokens"),
        "output_tokens": result.get("output_tokens"),
        "latency_ms": result.get("latency_ms"),
        "model": resolved_model,
        "effort": "provider-default",
        "tool_access": [],
        "status": status,
        "reason": reason,
    }


async def invoke(
    request: dict,
    *,
    provider: str,
    model: str,
    timeout_s: float,
    overrides: TransportOverrides | None = None,
) -> dict:
    """Invoke one bounded, no-tool provider call for a single fixture request.

    `request` carries only the fixture payload and selected skill text built
    by `fixtures.build_request()`/`build_repair_request()`; it never carries
    credentials. `model` is a requested policy tier (e.g. "sonnet"), resolved
    exactly once here through `manifest_model_policy.resolver.resolve_chain`.
    An unsupported provider/tier combination, or a provider with no verified
    isolated adapter, is rejected before any call is made.
    """
    active = overrides or TransportOverrides()
    policy = active.policy if active.policy is not None else load_model_policy()
    if provider not in SUPPORTED_PROVIDERS:
        return _unsupported(f"{provider}: no verified isolated no-tool adapter")
    resolved_model = _resolve_model_id(provider, model, policy)
    if resolved_model is None:
        return _unsupported(
            f"unsupported provider/model combination: {provider}/{model}"
        )

    adapters = active.adapters or DEFAULT_ADAPTERS
    adapter = adapters.get(provider)
    if adapter is None:
        return _unsupported(f"{provider}: no adapter registered")

    system_prompt = request.get("context", "")
    prompt = _prompt_text(request)
    t0 = time.monotonic()
    try:
        result = await asyncio.wait_for(
            adapter(prompt, system_prompt, resolved_model), timeout=timeout_s
        )
    except TimeoutError:
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        return _completed_result(
            {"latency_ms": elapsed_ms},
            resolved_model,
            "timeout",
            f"exceeded {timeout_s}s timeout",
        )

    if result.get("error"):
        return _completed_result(result, resolved_model, "error", result["error"])
    return _completed_result(result, resolved_model, "completed", None)
