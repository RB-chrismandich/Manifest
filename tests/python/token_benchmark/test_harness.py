"""Tests for benchmark harness (IsolatedEnvironment + API measurement)."""

import json
import os
import subprocess as sp
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from tests.token_benchmark.benchmarks import BENCHMARKS
from tests.token_benchmark.harness import (
    isolated_environments,
    measure_api_claude,
    measure_api_gemini,
    measure_cli,
    run_benchmark,
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
        with isolated_environments(fixtures) as (empty, _manifest):
            assert list(empty.iterdir()) == []

    def test_manifest_home_populated_from_fixtures(self, tmp_path):
        fixtures = tmp_path / "fixtures"
        (fixtures / ".claude").mkdir(parents=True)
        (fixtures / ".claude" / "CLAUDE.md").write_text("# test manifest")
        with isolated_environments(fixtures) as (_empty, manifest):
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

        with (
            patch("tests.token_benchmark.harness.HAS_ANTHROPIC", True),
            patch(
                "tests.token_benchmark.harness.AsyncAnthropic", return_value=mock_client
            ),
            patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}),
        ):
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
        with (
            patch("tests.token_benchmark.harness.HAS_ANTHROPIC", True),
            patch.dict(os.environ, env, clear=True),
        ):
            result = await measure_api_claude("prompt", "", "claude-sonnet-4-6")
        assert result["error"] is not None
        assert result["input_tokens"] is None

    @pytest.mark.asyncio
    async def test_system_prompt_passed_to_api(self):
        mock_usage = MagicMock(input_tokens=1842, output_tokens=47)
        mock_response = MagicMock(usage=mock_usage, content=[MagicMock(text="A")])
        mock_client = AsyncMock()
        mock_client.messages.create.return_value = mock_response

        with (
            patch("tests.token_benchmark.harness.HAS_ANTHROPIC", True),
            patch(
                "tests.token_benchmark.harness.AsyncAnthropic", return_value=mock_client
            ),
            patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}),
        ):
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

        with (
            patch("tests.token_benchmark.harness.HAS_GENAI", True),
            patch("tests.token_benchmark.harness.genai") as mock_genai,
            patch("tests.token_benchmark.harness.genai_types") as mock_types,
        ):
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
        env = {
            k: v
            for k, v in os.environ.items()
            if k not in ("GOOGLE_API_KEY", "GEMINI_API_KEY")
        }
        with (
            patch("tests.token_benchmark.harness.HAS_GENAI", True),
            patch.dict(os.environ, env, clear=True),
            patch("tests.token_benchmark.harness.genai") as mock_genai,
        ):
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

        with (
            patch("tests.token_benchmark.harness.HAS_GENAI", True),
            patch("tests.token_benchmark.harness.genai_types", None),
            patch("tests.token_benchmark.harness.genai") as mock_genai,
        ):
            mock_genai.Client.return_value = mock_client
            with patch.dict(os.environ, {"GOOGLE_API_KEY": "test-key"}):
                result = await measure_api_gemini(
                    "prompt", "system ctx", "gemini-3-flash-preview"
                )

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
        """The configured system_prompt_flag is added when a strategy exists
        (cli_config declares system_prompt_flag) and system_prompt is given."""
        import subprocess as sp

        real_run = sp.run
        captured = {}

        def capture_run(cmd, **kwargs):
            captured["cmd"] = cmd
            return real_run(["echo", "ok"], **dict(kwargs.items()))

        cli_config = {
            "binary": "echo",
            "flags": [],
            "system_prompt_flag": "--system-prompt",
        }
        with patch(
            "tests.token_benchmark.harness.subprocess.run", side_effect=capture_run
        ):
            measure_cli("prompt", cli_config, system_prompt="MANIFEST CONTEXT")
        assert "--system-prompt" in captured["cmd"]
        assert "MANIFEST CONTEXT" in captured["cmd"]

    def test_system_prompt_none_omits_flag(self):
        """No --system-prompt flag when system_prompt is None, even with a strategy."""
        import subprocess as sp

        real_run = sp.run
        captured = {}

        def capture_run(cmd, **kwargs):
            captured["cmd"] = cmd
            return real_run(["echo", "ok"], **dict(kwargs.items()))

        cli_config = {
            "binary": "echo",
            "flags": [],
            "system_prompt_flag": "--system-prompt",
        }
        with patch(
            "tests.token_benchmark.harness.subprocess.run", side_effect=capture_run
        ):
            measure_cli("prompt", cli_config)
        assert "--system-prompt" not in captured["cmd"]

    def test_system_prompt_ignored_without_strategy(self):
        """(#546/G8) A provider with NO system_prompt_flag strategy (e.g. agy,
        gemini) is NEVER invoked with a system-prompt flag, even when a
        system_prompt value is supplied — there is no verified mechanism to
        honor it."""
        import subprocess as sp

        real_run = sp.run
        captured = {}

        def capture_run(cmd, **kwargs):
            captured["cmd"] = cmd
            return real_run(["echo", "ok"], **dict(kwargs.items()))

        cli_config = {"binary": "echo", "flags": ["--print"]}  # no system_prompt_flag
        with patch(
            "tests.token_benchmark.harness.subprocess.run", side_effect=capture_run
        ):
            measure_cli("prompt", cli_config, system_prompt="MANIFEST CONTEXT")
        assert "--system-prompt" not in captured["cmd"]
        assert "MANIFEST CONTEXT" not in captured["cmd"]
        assert captured["cmd"] == ["echo", "--print", "prompt"]

    def test_missing_binary_returns_error(self):
        cli_config = {"binary": "nonexistent_binary_12345", "flags": []}
        result = measure_cli("prompt", cli_config)
        assert result["error"] is not None
        assert result["response_text"] == ""

    def test_timeout_returns_error(self):
        import subprocess as sp

        cli_config = {"binary": "sleep", "flags": []}
        with patch(
            "tests.token_benchmark.harness.subprocess.run",
            side_effect=sp.TimeoutExpired(cmd=["sleep"], timeout=60),
        ):
            result = measure_cli("100", cli_config)
        assert result["error"] == "timeout"
        assert result["response_text"] == ""


class TestRunBenchmarkCliStrategy:
    """(#546) run_benchmark's CLI branch is provider-aware: only providers with
    a verified system_prompt_flag strategy are ever invoked with a
    system-prompt flag; the rest yield an explicit unsupported outcome with
    zero subprocess invocations. All CLI calls are mocked — no live CLIs."""

    @pytest.mark.asyncio
    async def test_claude_invocation_shape_unchanged(self, tmp_path):
        """claude keeps injecting --system-prompt exactly as before #546."""
        fixtures = tmp_path / "fixtures"
        (fixtures / ".claude").mkdir(parents=True)
        (fixtures / ".claude" / "CLAUDE.md").write_text("MANIFEST TEXT")

        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            return sp.CompletedProcess(cmd, 0, stdout="B", stderr="")

        with patch(
            "tests.token_benchmark.harness.subprocess.run", side_effect=fake_run
        ):
            records = await run_benchmark(
                providers=["claude"],
                api_only=False,
                cli_only=True,
                conditions=["before", "after"],
                run_id="test-run",
                fixtures_dir=fixtures,
                results_dir=tmp_path / "results",
            )

        # subprocess.run is also hit by the scorer's HumanEval `python3 -c`
        # execution; isolate the claude CLI invocations themselves.
        claude_calls = [c for c in calls if c[0] == "claude"]
        assert len(claude_calls) == len(BENCHMARKS) * 2  # before + after, every prompt
        for cmd in claude_calls:
            assert "--system-prompt" in cmd
        assert len(records) == len(claude_calls)
        assert all(r["provider"] == "claude" for r in records)
        assert all(r["unsupported"] is False for r in records)

    @pytest.mark.asyncio
    async def test_unsupported_providers_yield_zero_invocations(self, tmp_path):
        """gemini/antigravity (no system_prompt_flag strategy) never touch
        subprocess.run and instead get an explicit unsupported row in both
        the before and after conditions."""
        fixtures = tmp_path / "fixtures"
        fixtures.mkdir()

        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            return sp.CompletedProcess(cmd, 0, stdout="", stderr="")

        with patch(
            "tests.token_benchmark.harness.subprocess.run", side_effect=fake_run
        ):
            records = await run_benchmark(
                providers=["gemini", "antigravity"],
                api_only=False,
                cli_only=True,
                conditions=["before", "after"],
                run_id="test-run",
                fixtures_dir=fixtures,
                results_dir=tmp_path / "results",
            )

        assert calls == []  # zero invocations at all, flag-bearing or otherwise
        # 2 providers * 2 conditions * len(BENCHMARKS) prompts
        assert len(records) == len(BENCHMARKS) * 2 * 2
        assert {r["condition"] for r in records} == {"before", "after"}
        assert {r["provider"] for r in records} == {"gemini", "antigravity"}
        for r in records:
            assert r["unsupported"] is True
            assert r["error"] is None  # distinct from an error outcome
            assert r["quality_score"] is None  # distinct from a scored row
            assert r["input_tokens"] is None
            assert r["response_text"] is None

    @pytest.mark.asyncio
    async def test_unsupported_warns_once_per_provider(self, tmp_path, capsys):
        """A console warning is printed the first time a provider records an
        unsupported CLI row, and never repeated for that provider — even
        though every (prompt, condition) pair for it takes the unsupported
        branch."""
        fixtures = tmp_path / "fixtures"
        fixtures.mkdir()

        await run_benchmark(
            providers=["gemini", "antigravity"],
            api_only=False,
            cli_only=True,
            conditions=["before", "after"],
            run_id="test-run",
            fixtures_dir=fixtures,
            results_dir=tmp_path / "results",
        )

        out = capsys.readouterr().out
        for provider in ("gemini", "antigravity"):
            assert out.count(f"[{provider}][cli] unsupported") == 1


class TestWriteResult:
    def test_appends_jsonl_to_results_dir(self, tmp_path):
        record = {
            "run_id": "2026-06-12T00:00:00",
            "provider": "claude",
            "input_tokens": 100,
        }
        write_result(record, "2026-06-12T00:00:00", results_dir=tmp_path)
        files = list(tmp_path.glob("*.jsonl"))
        assert len(files) == 1
        with open(files[0]) as f:
            loaded = json.loads(f.read().strip())
        assert loaded["input_tokens"] == 100

    def test_multiple_records_in_same_file(self, tmp_path):
        for i in range(3):
            write_result(
                {"run_id": "2026-06-12T00:00:00", "i": i},
                "2026-06-12T00:00:00",
                results_dir=tmp_path,
            )
        files = list(tmp_path.glob("*.jsonl"))
        assert len(files) == 1
        lines = files[0].read_text().strip().splitlines()
        assert len(lines) == 3


class TestComputeCost:
    def test_compute_cost_standard(self):
        """Standard call: input + output tokens, no cache."""
        from tests.token_benchmark.harness import compute_cost

        record = {
            "input_tokens": 1000,
            "output_tokens": 100,
            "cache_creation_tokens": None,
            "cache_read_tokens": None,
        }
        cost = compute_cost(record, "claude-sonnet-4-6")
        # 1000 * 3.00/1e6 + 100 * 15.00/1e6 = 0.003 + 0.0015 = 0.0045
        assert abs(cost - 0.0045) < 1e-8

    def test_compute_cost_with_cache_read(self):
        """Cache read tokens billed at 0.1x input rate."""
        from tests.token_benchmark.harness import compute_cost

        record = {
            "input_tokens": 1000,
            "output_tokens": 100,
            "cache_creation_tokens": None,
            "cache_read_tokens": 800,
        }
        cost = compute_cost(record, "claude-sonnet-4-6")
        # non-cache input: (1000-800) * 3.00/1e6 = 0.0006
        # cache read: 800 * 0.30/1e6 = 0.00024
        # output: 100 * 15.00/1e6 = 0.0015
        # total = 0.00234
        assert abs(cost - 0.00234) < 1e-8


class TestMeasureApiClaudeCaching:
    @pytest.mark.asyncio
    async def test_cached_condition_passes_cache_control(self):
        """When use_cache=True, system prompt is sent as a list with cache_control block."""
        mock_usage = MagicMock(
            input_tokens=1783,
            output_tokens=4,
            cache_creation_input_tokens=1718,
            cache_read_input_tokens=0,
        )
        mock_response = MagicMock(usage=mock_usage, content=[MagicMock(text="B")])
        mock_client = AsyncMock()
        mock_client.messages.create.return_value = mock_response

        with (
            patch("tests.token_benchmark.harness.HAS_ANTHROPIC", True),
            patch(
                "tests.token_benchmark.harness.AsyncAnthropic", return_value=mock_client
            ),
            patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}),
        ):
            result = await measure_api_claude(
                "What is 2+2?", "SYSTEM", "claude-sonnet-4-6", use_cache=True
            )

        call_kwargs = mock_client.messages.create.call_args.kwargs
        system_arg = call_kwargs["system"]
        # system must be a list with cache_control block
        assert isinstance(system_arg, list)
        assert system_arg[0]["type"] == "text"
        assert system_arg[0]["cache_control"] == {"type": "ephemeral"}
        assert result["cache_creation_tokens"] == 1718
        assert result["cache_read_tokens"] == 0


class TestTieredCondition:
    def test_tiered_injects_manifest_only_for_humaneval(self):
        """tiered condition: humaneval gets manifest system prompt, others get baseline."""
        from tests.token_benchmark.harness import _system_prompt_for_condition

        manifest = "MANIFEST CONTEXT"
        # humaneval → manifest
        sp = _system_prompt_for_condition("tiered", "humaneval", manifest)
        assert sp == manifest
        # mmlu → baseline
        sp = _system_prompt_for_condition("tiered", "mmlu", manifest)
        assert sp == ""
        # hellaswag → baseline
        sp = _system_prompt_for_condition("tiered", "hellaswag", manifest)
        assert sp == ""
        # truthfulqa → baseline
        sp = _system_prompt_for_condition("tiered", "truthfulqa", manifest)
        assert sp == ""
        # after → always manifest
        sp = _system_prompt_for_condition("after", "mmlu", manifest)
        assert sp == manifest
        # before → always baseline
        sp = _system_prompt_for_condition("before", "humaneval", manifest)
        assert sp == ""


class TestSyncFixturesCompression:
    def test_compression_50_produces_half_line_count(self, tmp_path):
        """--sync-fixtures --compression 50 writes first 50% of lines."""
        from tests.token_benchmark.harness import sync_fixtures

        # Create a fake source home with a CLAUDE.md of 10 lines
        src = tmp_path / "home"
        claude_dir = src / ".claude"
        claude_dir.mkdir(parents=True)
        (claude_dir / "CLAUDE.md").write_text("\n".join(f"line {i}" for i in range(10)))

        dst = tmp_path / "fixtures"
        sync_fixtures(source_home=src, fixtures_dir=dst, compression=50)

        compressed = dst.parent / "fixtures-compressed" / ".claude" / "CLAUDE.md"
        lines = compressed.read_text().splitlines()
        assert len(lines) == 5
