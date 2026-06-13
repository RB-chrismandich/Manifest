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
    measure_cli,
    write_result,
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

    @pytest.mark.asyncio
    async def test_genai_types_none_omits_config(self):
        """When genai_types is None, generate_content is called without config kwarg."""
        mock_usage = MagicMock(prompt_token_count=10, candidates_token_count=5)
        mock_response = MagicMock(text="D", usage_metadata=mock_usage)
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response

        with patch("tests.token_benchmark.harness.HAS_GENAI", True):
            with patch("tests.token_benchmark.harness.genai_types", None):
                with patch("tests.token_benchmark.harness.genai") as mock_genai:
                    mock_genai.Client.return_value = mock_client
                    with patch.dict(os.environ, {"GOOGLE_API_KEY": "test-key"}):
                        result = await measure_api_gemini("prompt", "system ctx", "gemini-3-flash-preview")

        assert result["error"] is None
        assert result["response_text"] == "D"
        call_kwargs = mock_client.models.generate_content.call_args.kwargs
        assert "config" not in call_kwargs


class TestMeasureCli:
    def test_returns_response_text_and_latency(self):
        cli_config = {"binary": "echo", "flags": []}
        result = measure_cli("hello world", cli_config)
        assert "hello world" in result["response_text"]
        assert result["latency_ms"] >= 0
        assert result["error"] is None

    def test_system_prompt_flag_appended(self):
        """--system-prompt <value> is added to the command when system_prompt is given."""
        import subprocess as sp
        real_run = sp.run
        captured = {}
        def capture_run(cmd, **kwargs):
            captured["cmd"] = cmd
            return real_run(["echo", "ok"], **{k: v for k, v in kwargs.items()})
        cli_config = {"binary": "echo", "flags": []}
        with patch("tests.token_benchmark.harness.subprocess.run", side_effect=capture_run):
            measure_cli("prompt", cli_config, system_prompt="MANIFEST CONTEXT")
        assert "--system-prompt" in captured["cmd"]
        assert "MANIFEST CONTEXT" in captured["cmd"]

    def test_system_prompt_none_omits_flag(self):
        """No --system-prompt flag when system_prompt is None."""
        import subprocess as sp
        real_run = sp.run
        captured = {}
        def capture_run(cmd, **kwargs):
            captured["cmd"] = cmd
            return real_run(["echo", "ok"], **{k: v for k, v in kwargs.items()})
        cli_config = {"binary": "echo", "flags": []}
        with patch("tests.token_benchmark.harness.subprocess.run", side_effect=capture_run):
            measure_cli("prompt", cli_config)
        assert "--system-prompt" not in captured["cmd"]

    def test_missing_binary_returns_error(self):
        cli_config = {"binary": "nonexistent_binary_12345", "flags": []}
        result = measure_cli("prompt", cli_config)
        assert result["error"] is not None
        assert result["response_text"] == ""

    def test_timeout_returns_error(self):
        import subprocess as sp
        cli_config = {"binary": "sleep", "flags": []}
        with patch("tests.token_benchmark.harness.subprocess.run",
                   side_effect=sp.TimeoutExpired(cmd=["sleep"], timeout=60)):
            result = measure_cli("100", cli_config)
        assert result["error"] == "timeout"
        assert result["response_text"] == ""


class TestWriteResult:
    def test_appends_jsonl_to_results_dir(self, tmp_path):
        record = {"run_id": "2026-06-12T00:00:00", "provider": "claude", "input_tokens": 100}
        write_result(record, "2026-06-12T00:00:00", results_dir=tmp_path)
        files = list(tmp_path.glob("*.jsonl"))
        assert len(files) == 1
        with open(files[0]) as f:
            loaded = json.loads(f.read().strip())
        assert loaded["input_tokens"] == 100

    def test_multiple_records_in_same_file(self, tmp_path):
        for i in range(3):
            write_result({"run_id": "2026-06-12T00:00:00", "i": i}, "2026-06-12T00:00:00", results_dir=tmp_path)
        files = list(tmp_path.glob("*.jsonl"))
        assert len(files) == 1
        lines = files[0].read_text().strip().splitlines()
        assert len(lines) == 3
