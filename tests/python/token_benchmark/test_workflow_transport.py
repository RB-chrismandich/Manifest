"""Tests for tests/token_benchmark/workflows/transport.py.

Every test injects a fake policy and fake provider adapters via
`TransportOverrides`; none reads the real model_policy.yml, makes a network
call, or imports a provider SDK.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from tests.token_benchmark.workflows.transport import TransportOverrides, invoke

FAKE_POLICY = {
    "model_tiers": {
        "claude": {"sonnet": "claude-sonnet-5[1m]"},
        "gemini": {"flash": "gemini-3-flash-preview"},
    },
}


def _request(context="full skill text"):
    return {
        "instruction": "do the thing",
        "artifacts": {"a.py": "x = 1\n"},
        "output_contract": {"files": {"solution.py": "string"}},
        "context": context,
    }


class TestInvokeSuccess:
    @pytest.mark.asyncio
    async def test_completed_call_resolves_model_and_records_no_tools(self):
        async def fake_claude(prompt, system_prompt, model_id):
            assert model_id == "claude-sonnet-5[1m]"
            assert "do the thing" in prompt
            assert system_prompt == "full skill text"
            return {
                "response_text": '{"ok": true}',
                "input_tokens": 10,
                "output_tokens": 4,
                "latency_ms": 12,
                "error": None,
            }

        overrides = TransportOverrides(
            adapters={"claude": fake_claude}, policy=FAKE_POLICY
        )
        result = await invoke(
            _request(),
            provider="claude",
            model="sonnet",
            timeout_s=5,
            overrides=overrides,
        )
        assert result["status"] == "completed"
        assert result["model"] == "claude-sonnet-5[1m]"
        assert result["effort"] == "provider-default"
        assert result["tool_access"] == []
        assert result["response_text"] == '{"ok": true}'
        assert result["input_tokens"] == 10


class TestInvokeUnsupported:
    @pytest.mark.asyncio
    async def test_unsupported_provider_never_calls_adapter(self):
        called = False

        async def fake(prompt, system_prompt, model_id):
            nonlocal called
            called = True
            return {}

        overrides = TransportOverrides(adapters={"cursor": fake}, policy=FAKE_POLICY)
        result = await invoke(
            _request(),
            provider="cursor",
            model="advanced",
            timeout_s=5,
            overrides=overrides,
        )
        assert result["status"] == "unsupported"
        assert called is False
        assert result["tool_access"] == []
        assert result["model"] is None

    @pytest.mark.asyncio
    async def test_unsupported_model_tier_never_calls_adapter(self):
        called = False

        async def fake_claude(prompt, system_prompt, model_id):
            nonlocal called
            called = True
            return {}

        overrides = TransportOverrides(
            adapters={"claude": fake_claude}, policy=FAKE_POLICY
        )
        result = await invoke(
            _request(),
            provider="claude",
            model="opus",
            timeout_s=5,
            overrides=overrides,
        )
        assert result["status"] == "unsupported"
        assert called is False
        assert "opus" in result["reason"]


class TestInvokeTimeoutAndError:
    @pytest.mark.asyncio
    async def test_timeout_reports_status_without_response(self):
        async def slow_claude(prompt, system_prompt, model_id):
            await asyncio.sleep(10)
            return {"response_text": "too late"}

        overrides = TransportOverrides(
            adapters={"claude": slow_claude}, policy=FAKE_POLICY
        )
        result = await invoke(
            _request(),
            provider="claude",
            model="sonnet",
            timeout_s=0.01,
            overrides=overrides,
        )
        assert result["status"] == "timeout"
        assert result["response_text"] is None
        assert "timeout" in result["reason"]

    @pytest.mark.asyncio
    async def test_adapter_error_is_recorded_as_error_status(self):
        async def failing_claude(prompt, system_prompt, model_id):
            return {
                "response_text": None,
                "input_tokens": None,
                "output_tokens": None,
                "latency_ms": 5,
                "error": "ANTHROPIC_API_KEY not set",
            }

        overrides = TransportOverrides(
            adapters={"claude": failing_claude}, policy=FAKE_POLICY
        )
        result = await invoke(
            _request(),
            provider="claude",
            model="sonnet",
            timeout_s=5,
            overrides=overrides,
        )
        assert result["status"] == "error"
        assert result["reason"] == "ANTHROPIC_API_KEY not set"


class TestInvokeUnknownUsage:
    @pytest.mark.asyncio
    async def test_missing_token_counts_pass_through_as_null(self):
        async def partial_claude(prompt, system_prompt, model_id):
            return {
                "response_text": "some text",
                "input_tokens": None,
                "output_tokens": None,
                "latency_ms": 8,
                "error": None,
            }

        overrides = TransportOverrides(
            adapters={"claude": partial_claude}, policy=FAKE_POLICY
        )
        result = await invoke(
            _request(),
            provider="claude",
            model="sonnet",
            timeout_s=5,
            overrides=overrides,
        )
        assert result["status"] == "completed"
        assert result["input_tokens"] is None
        assert result["output_tokens"] is None
