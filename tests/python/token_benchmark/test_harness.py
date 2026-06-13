"""Tests for benchmark harness (IsolatedEnvironment + API measurement)."""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from tests.token_benchmark.harness import (
    isolated_environments,
    measure_api_claude,
    measure_api_gemini,
)


class TestIsolatedEnvironments:
    def test_creates_two_dirs(self, tmp_path):
        fixtures = tmp_path / "fixtures"
        fixtures.mkdir()
        with isolated_environments(fixtures) as (empty, manifest):
            assert empty.exists()
            assert manifest.exists()
            assert empty != manifest

    def test_empty_home_has_no_files(self, tmp_path):
        fixtures = tmp_path / "fixtures"
        fixtures.mkdir()
        with isolated_environments(fixtures) as (empty, manifest):
            assert list(empty.iterdir()) == []

    def test_manifest_home_populated_from_fixtures(self, tmp_path):
        fixtures = tmp_path / "fixtures"
        (fixtures / ".claude").mkdir(parents=True)
        (fixtures / ".claude" / "CLAUDE.md").write_text("# test manifest")
        with isolated_environments(fixtures) as (empty, manifest):
            assert (manifest / ".claude" / "CLAUDE.md").read_text() == "# test manifest"

    def test_dirs_cleaned_up_after_exit(self, tmp_path):
        fixtures = tmp_path / "fixtures"
        fixtures.mkdir()
        with isolated_environments(fixtures) as (empty, manifest):
            empty_path = empty
            manifest_path = manifest
        assert not empty_path.exists()
        assert not manifest_path.exists()

    def test_missing_fixtures_dir_ok(self, tmp_path):
        """Empty fixtures dir (before --sync-fixtures) should not raise."""
        fixtures = tmp_path / "nonexistent"
        with isolated_environments(fixtures) as (empty, manifest):
            assert empty.exists()
            assert manifest.exists()


class TestMeasureApiClaude:
    @pytest.mark.asyncio
    async def test_returns_token_counts_and_text(self):
        mock_usage = MagicMock(input_tokens=312, output_tokens=47)
        mock_content = MagicMock(text="B")
        mock_response = MagicMock(usage=mock_usage, content=[mock_content])

        mock_client = AsyncMock()
        mock_client.messages.create.return_value = mock_response

        with patch("tests.token_benchmark.harness.HAS_ANTHROPIC", True):
            with patch("tests.token_benchmark.harness.AsyncAnthropic", return_value=mock_client):
                with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
                    result = await measure_api_claude(
                        prompt_text="What is 2+2?",
                        system_prompt="",
                        model="claude-sonnet-4-6",
                    )

        assert result["input_tokens"] == 312
        assert result["output_tokens"] == 47
        assert result["response_text"] == "B"
        assert result["error"] is None

    @pytest.mark.asyncio
    async def test_missing_api_key_returns_error(self):
        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        with patch("tests.token_benchmark.harness.HAS_ANTHROPIC", True):
            with patch.dict(os.environ, env, clear=True):
                result = await measure_api_claude("prompt", "", "claude-sonnet-4-6")
        assert result["error"] is not None
        assert result["input_tokens"] is None

    @pytest.mark.asyncio
    async def test_system_prompt_passed_to_api(self):
        mock_usage = MagicMock(input_tokens=1842, output_tokens=47)
        mock_response = MagicMock(usage=mock_usage, content=[MagicMock(text="A")])
        mock_client = AsyncMock()
        mock_client.messages.create.return_value = mock_response

        with patch("tests.token_benchmark.harness.HAS_ANTHROPIC", True):
            with patch("tests.token_benchmark.harness.AsyncAnthropic", return_value=mock_client):
                with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
                    await measure_api_claude("prompt", "SYSTEM CONTEXT", "claude-sonnet-4-6")

        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert call_kwargs["system"] == "SYSTEM CONTEXT"


class TestMeasureApiGemini:
    @pytest.mark.asyncio
    async def test_returns_token_counts_and_text(self):
        mock_usage = MagicMock(prompt_token_count=308, candidates_token_count=52)
        mock_response = MagicMock(text="C", usage_metadata=mock_usage)

        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response

        with patch("tests.token_benchmark.harness.HAS_GENAI", True):
            with patch("tests.token_benchmark.harness.genai") as mock_genai:
                with patch("tests.token_benchmark.harness.genai_types") as mock_types:
                    mock_types.GenerateContentConfig.return_value = MagicMock()
                    mock_genai.Client.return_value = mock_client
                    with patch.dict(os.environ, {"GOOGLE_API_KEY": "test-key"}):
                        result = await measure_api_gemini(
                            prompt_text="What is 2+2?",
                            system_prompt="",
                            model="gemini-3-flash-preview",
                        )

        assert result["input_tokens"] == 308
        assert result["output_tokens"] == 52
        assert result["response_text"] == "C"
        assert result["error"] is None

    @pytest.mark.asyncio
    async def test_missing_api_key_returns_error(self):
        env = {k: v for k, v in os.environ.items() if k not in ("GOOGLE_API_KEY", "GEMINI_API_KEY")}
        with patch("tests.token_benchmark.harness.HAS_GENAI", True):
            with patch.dict(os.environ, env, clear=True):
                with patch("tests.token_benchmark.harness.genai") as mock_genai:
                    mock_genai.Client.side_effect = Exception("no auth")
                    result = await measure_api_gemini("prompt", "", "gemini-3-flash-preview")
        assert result["error"] is not None
