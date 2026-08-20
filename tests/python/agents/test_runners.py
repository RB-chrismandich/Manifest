#!/usr/bin/env python3
"""Per-module unit tests for agents.runners.

Tests BaseAgent and CLIAgent in isolation — no external agent connections required.
"""

import asyncio
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
SCRIPTS_DIR = str(REPO_ROOT / "configs" / "claude" / "scripts")
sys.path.insert(0, SCRIPTS_DIR)

from agents.config import Config, RateLimiter
from agents.runners import BaseAgent, CLIAgent, ProviderAttemptError
from manifest_model_policy import (
    FailureClass,
    ModelFallbackMode,
    classify_failure,
    resolve_chain,
)


def _make_config(tmp_path):
    return Config(
        config_path=str(tmp_path / "none.yml"),
        roster_path=str(tmp_path / "agent_roster.yml"),
    )


def _make_limiter():
    return RateLimiter(requests_per_minute=1000, burst_size=100)


class _AsyncBytesStream:
    def __init__(self, data):
        self._data = data

    async def read(self, _size=-1):
        data, self._data = self._data, b""
        return data


def _mock_process(stdout=b"", stderr=b"", returncode=0):
    """Return a subprocess-shaped mock for incremental stream acquisition."""
    proc = Mock()
    proc.stdout = _AsyncBytesStream(stdout)
    proc.stderr = _AsyncBytesStream(stderr)
    proc.returncode = returncode
    proc.wait = AsyncMock(return_value=returncode)
    proc.kill = Mock()
    return proc


# ---------------------------------------------------------------------------
# BaseAgent
# ---------------------------------------------------------------------------


class _ConcreteAgent(BaseAgent):
    """Minimal concrete implementation for testing BaseAgent."""

    async def _execute_impl(self, prompt: str, mode: str):
        return {"status": "complete", "output": "ok", "model": "test"}


class TestBaseAgent:
    @pytest.mark.parametrize(
        ("agent_name", "starting_tier", "expected"),
        (
            ("codex", "auto", ("advanced", "flash", "mini", "auto")),
            ("claude", "sonnet", ("sonnet", "haiku")),
        ),
    )
    def test_constructor_applies_configured_default_fallback_chain(
        self, tmp_path, agent_name, starting_tier, expected
    ):
        agent = _ConcreteAgent(
            agent_name,
            starting_tier,
            30,
            _make_limiter(),
            _make_config(tmp_path),
        )

        assert tuple(item.tier for item in agent.model_chain) == expected

    def test_credit_exhaustion_detection_quota(self, tmp_path):
        agent = _ConcreteAgent(
            "test", "sonnet", 30, _make_limiter(), _make_config(tmp_path)
        )
        assert agent._is_credit_exhaustion_error("quota exceeded") is True

    def test_credit_exhaustion_detection_rate_limit(self, tmp_path):
        agent = _ConcreteAgent(
            "test", "sonnet", 30, _make_limiter(), _make_config(tmp_path)
        )
        assert agent._is_credit_exhaustion_error("rate limit reached") is True

    def test_credit_exhaustion_detection_429(self, tmp_path):
        agent = _ConcreteAgent(
            "test", "sonnet", 30, _make_limiter(), _make_config(tmp_path)
        )
        assert agent._is_credit_exhaustion_error("error 429 too many") is True

    def test_no_false_positive_on_normal_error(self, tmp_path):
        agent = _ConcreteAgent(
            "test", "sonnet", 30, _make_limiter(), _make_config(tmp_path)
        )
        assert agent._is_credit_exhaustion_error("connection refused") is False

    def test_execute_returns_result(self, tmp_path):
        agent = _ConcreteAgent(
            "test", "sonnet", 30, _make_limiter(), _make_config(tmp_path)
        )
        result = asyncio.run(agent.execute("hello"))
        assert result["status"] == "complete"
        assert "duration_seconds" in result

    def test_credit_fallback_switches_executed_model(self, tmp_path):
        """Issue #304: the retry must run the fallback model, not the exhausted one."""
        config_file = tmp_path / "cfg.yml"
        config_file.write_text(
            "credit_fallback:\n  test:\n    - sonnet\n    - haiku\n"
            "model_tiers:\n  test:\n    sonnet: model-big\n    haiku: model-small\n"
        )

        models_executed = []

        class FlakyAgent(BaseAgent):
            def _resolve_model(self, tier):
                return self.config.get(f"model_tiers.test.{tier}", tier)

            async def _execute_impl(self, prompt, mode):
                models_executed.append(self.model_name)
                if not self.credit_fallback_used:
                    raise ConnectionError("provider connection failed")
                return {"status": "complete", "output": "ok", "model": self.model_name}

        agent = FlakyAgent(
            "test",
            "sonnet",
            30,
            _make_limiter(),
            Config(config_path=str(config_file)),
            model_chain=("sonnet", "haiku"),
            fallback_mode="auto",
        )
        agent.model_name = agent._resolve_model("sonnet")
        result = asyncio.run(agent.execute("hello"))
        assert result["status"] == "complete"
        assert result["credit_fallback"] is True
        assert models_executed == ["model-big", "model-small"]

    def test_execute_timeout(self, tmp_path):
        class SlowAgent(BaseAgent):
            async def _execute_impl(self, prompt, mode):
                await asyncio.sleep(10)
                return {"status": "complete", "output": "late"}

        agent = SlowAgent("slow", "sonnet", 1, _make_limiter(), _make_config(tmp_path))
        result = asyncio.run(agent.execute("hello"))
        assert result["status"] == "failed"
        assert "timeout" in result["error"]

    def test_timeout_uses_automatic_fallback_chain(self, tmp_path):
        models_executed = []

        class TimeoutThenSuccessAgent(BaseAgent):
            async def _execute_impl(self, prompt, mode):
                del prompt, mode
                models_executed.append(self.model_name)
                if len(models_executed) == 1:
                    raise TimeoutError
                return {"status": "complete", "output": "ok"}

        agent = TimeoutThenSuccessAgent(
            "codex",
            "advanced",
            0.10,
            _make_limiter(),
            _make_config(tmp_path),
            model_chain=("advanced", "flash"),
            fallback_mode="auto",
        )

        async def announce_without_delay(_decision):
            agent.credit_fallback_used = True

        agent._announce_retry = announce_without_delay

        result = asyncio.run(agent.execute("hello"))

        assert result["status"] == "complete"
        assert models_executed == ["advanced", "flash"]
        assert result["fallback_reason"] == FailureClass.TRANSIENT.value

    def test_fallback_attempts_share_one_monotonic_timeout_budget(self, tmp_path):
        models_executed = []

        class SlowFallbackAgent(BaseAgent):
            async def _execute_impl(self, prompt, mode):
                del prompt, mode
                models_executed.append(self.model_name)
                if len(models_executed) == 1:
                    await asyncio.sleep(0.12)
                    raise ConnectionError("provider unavailable")
                await asyncio.sleep(0.20)
                return {"status": "complete", "output": "late"}

        agent = SlowFallbackAgent(
            "codex",
            "advanced",
            0.20,
            _make_limiter(),
            _make_config(tmp_path),
            model_chain=("advanced", "flash"),
            fallback_mode="auto",
        )

        async def announce_without_delay(_decision):
            agent.credit_fallback_used = True

        agent._announce_retry = announce_without_delay
        started = time.monotonic()

        result = asyncio.run(agent.execute("hello"))

        elapsed = time.monotonic() - started
        assert result["status"] == "failed"
        assert models_executed == ["advanced", "flash"]
        assert elapsed < 0.27

    def test_returned_retryable_failure_advances_model_chain(
        self, tmp_path, monkeypatch
    ):
        models_executed = []

        class ReturnedFailureThenSuccess(BaseAgent):
            async def _execute_impl(self, prompt, mode):
                del prompt, mode
                models_executed.append(self.model_name)
                if len(models_executed) == 1:
                    return {
                        "status": "failed",
                        "error": "provider command failed",
                        "fallback_reason": FailureClass.RATE_LIMIT.value,
                    }
                return {"status": "complete", "output": "ok"}

        async def no_sleep(_seconds):
            return None

        monkeypatch.setattr(asyncio, "sleep", no_sleep)
        agent = ReturnedFailureThenSuccess(
            "codex",
            "advanced",
            1,
            _make_limiter(),
            _make_config(tmp_path),
            model_chain=("advanced", "flash"),
            fallback_mode="auto",
        )

        result = asyncio.run(agent.execute("hello"))

        assert result["status"] == "complete"
        assert models_executed == ["advanced", "flash"]
        assert result["fallback_reason"] == FailureClass.RATE_LIMIT.value

    def test_returned_terminal_failure_replaces_prior_retry_reason(
        self, tmp_path, monkeypatch
    ):
        class ReturnedFailures(BaseAgent):
            async def _execute_impl(self, prompt, mode):
                del prompt, mode
                reason = (
                    FailureClass.RATE_LIMIT
                    if self.model_name == "advanced"
                    else FailureClass.AUTH
                )
                return {
                    "status": "failed",
                    "error": "provider command failed",
                    "fallback_reason": reason.value,
                }

        async def no_sleep(_seconds):
            return None

        monkeypatch.setattr(asyncio, "sleep", no_sleep)
        agent = ReturnedFailures(
            "codex",
            "advanced",
            1,
            _make_limiter(),
            _make_config(tmp_path),
            model_chain=("advanced", "flash"),
            fallback_mode="auto",
        )

        result = asyncio.run(agent.execute("hello"))

        assert result["status"] == "failed"
        assert result["fallback_reason"] == FailureClass.AUTH.value
        assert len(result["model_attempts"]) == 2

    def test_interactive_confirmation_does_not_block_peer_agent(self, tmp_path):
        class RateLimitedAgent(BaseAgent):
            async def _execute_impl(self, prompt, mode):
                del prompt, mode
                await asyncio.sleep(0.01)
                error = RuntimeError("rate limit")
                error.status_code = 429
                raise error

        class PeerAgent(BaseAgent):
            async def _execute_impl(self, prompt, mode):
                del prompt, mode
                await asyncio.sleep(0.02)
                return {"status": "complete", "output": "peer-ok"}

        def confirm(_message):
            time.sleep(0.15)
            return False

        rate_limited = RateLimitedAgent(
            "codex",
            "advanced",
            1,
            _make_limiter(),
            _make_config(tmp_path),
            model_chain=("advanced", "flash"),
            fallback_mode="confirm",
            interactive=True,
            confirm_callback=confirm,
        )
        peer = PeerAgent(
            "peer", "advanced", 1, _make_limiter(), _make_config(tmp_path)
        )

        async def run_both():
            return await asyncio.gather(
                rate_limited.execute("hello"), peer.execute("hello")
            )

        first, second = asyncio.run(run_both())

        assert first["fallback_reason"] == FailureClass.RATE_LIMIT.value
        assert second["status"] == "complete"

    def test_execute_sdk_failure_uses_status_without_exposing_message(self, tmp_path):
        secret_message = "raw provider failure sk-secret-do-not-retain"

        class SDKFailureAgent(BaseAgent):
            async def _execute_impl(self, prompt, mode):
                del prompt, mode
                error = RuntimeError(secret_message)
                error.status_code = 429
                raise error

        agent = SDKFailureAgent(
            "codex",
            "advanced",
            30,
            _make_limiter(),
            _make_config(tmp_path),
            fallback_mode="confirm",
        )

        result = asyncio.run(agent.execute("private task"))

        assert result["status"] == "failed"
        assert result["fallback_reason"] == FailureClass.RATE_LIMIT.value
        assert secret_message not in str(result)


# ---------------------------------------------------------------------------
# CLIAgent
# ---------------------------------------------------------------------------


class TestCLIAgentCommandAssembly:
    def test_unknown_provider_raises(self, tmp_path):
        with pytest.raises(ValueError, match="no cli_agents config"):
            CLIAgent(
                "nonexistent",
                model="flash",
                rate_limiter=_make_limiter(),
                config=_make_config(tmp_path),
            )

    def test_codex_auto_drops_model_args_atomically(self, tmp_path):
        agent = CLIAgent(
            "codex",
            model="auto",
            rate_limiter=_make_limiter(),
            config=_make_config(tmp_path),
        )
        cmd = agent._build_command("hello", output_file=str(tmp_path / "out.txt"))
        assert agent.model_name is None
        assert "--model" not in cmd  # no dangling flag
        assert cmd[0] == "codex"
        assert cmd[-1] == "hello"  # prompt is last
        assert str(tmp_path / "out.txt") in cmd  # {output_file} substituted

    def test_codex_tier_resolves_via_model_tiers(self, tmp_path):
        agent = CLIAgent(
            "codex",
            model="mini",
            rate_limiter=_make_limiter(),
            config=_make_config(tmp_path),
        )
        cmd = agent._build_command("hello", output_file=str(tmp_path / "out.txt"))
        i = cmd.index("--model")
        assert cmd[i + 1] == "gpt-5.6-luna"

    def test_cursor_tier_resolves_via_model_tiers(self, tmp_path):
        # Deliberate behavior change: cursor now honors model_tiers.cursor
        # (the old CursorAgent passed the raw tier string through).
        # Asserts the RESOLUTION, not a particular pin: comparing against the
        # config value keeps this test about "flash maps through model_tiers"
        # instead of failing every time a provider ships a new model. The
        # inequality is what gives it teeth — a passthrough bug would leave the
        # raw tier name "flash" in the command.
        config = _make_config(tmp_path)
        agent = CLIAgent(
            "cursor",
            model="flash",
            rate_limiter=_make_limiter(),
            config=config,
        )
        cmd = agent._build_command("hello")
        i = cmd.index("--model")
        assert cmd[i + 1] == config.get("model_tiers.cursor.flash")
        assert cmd[i + 1] != "flash"

    def test_devin_headless_invocation_and_permission_mode(self, tmp_path):
        # Regression guard: devin must run headless (-p) so it cannot sit on an
        # interactive prompt, and --permission-mode auto keeps auto-approval to
        # read-only tools (nothing can answer an edit/exec prompt in this mode).
        agent = CLIAgent(
            "devin",
            model="auto",
            rate_limiter=_make_limiter(),
            config=_make_config(tmp_path),
        )
        cmd = agent._build_command("hello")
        assert cmd == ["devin", "--permission-mode", "auto", "-p", "hello"]
        assert "--model" not in cmd  # "auto" pins nothing

    def test_devin_model_is_passed_through_verbatim(self, tmp_path):
        # devin has no model_tiers block on purpose (login-gated catalog), so a
        # requested model reaches the CLI unchanged instead of being mapped to
        # an invented tier name.
        agent = CLIAgent(
            "devin",
            model="opus",
            rate_limiter=_make_limiter(),
            config=_make_config(tmp_path),
        )
        cmd = agent._build_command("hello")
        i = cmd.index("--model")
        assert cmd[i + 1] == "opus"

    def test_cursor_headless_invocation(self, tmp_path):
        # Regression guard: cursor-agent must run headless (--print) and
        # read-only (--mode ask), or it launches interactively and hangs.
        agent = CLIAgent(
            "cursor",
            model="flash",
            rate_limiter=_make_limiter(),
            config=_make_config(tmp_path),
        )
        cmd = agent._build_command("hello")
        assert cmd[0] == "cursor-agent"
        assert "--print" in cmd
        assert cmd[cmd.index("--mode") + 1] == "ask"
        assert cmd[-1] == "hello"

    def test_output_file_placeholder_dropped_when_no_file(self, tmp_path):
        # A stdout-strategy provider with a stray {output_file} placeholder
        # must not inject an empty argv element.
        config = _make_config(tmp_path)
        config.config["cli_agents"]["fake"] = {
            "binary": "fakecli",
            "base_args": ["--out", "{output_file}"],
            "model_args": ["--model", "{model}"],
            "output": "stdout",
        }
        agent = CLIAgent(
            "fake", model="auto", rate_limiter=_make_limiter(), config=config
        )
        cmd = agent._build_command("hello", output_file=None)
        assert "" not in cmd

    def test_missing_binary_field_raises_value_error(self, tmp_path):
        config = _make_config(tmp_path)
        config.config["cli_agents"]["broken"] = {
            "base_args": [],
            "model_args": ["--model", "{model}"],
            "output": "stdout",
        }
        with pytest.raises(ValueError, match="binary is required"):
            CLIAgent(
                "broken", model="flash", rate_limiter=_make_limiter(), config=config
            )

    def test_custom_model_passes_through(self, tmp_path):
        agent = CLIAgent(
            "codex",
            model="custom-model-123",
            rate_limiter=_make_limiter(),
            config=_make_config(tmp_path),
        )
        assert agent.model_name == "custom-model-123"

    def test_antigravity_command_shape(self, tmp_path):
        config = _make_config(tmp_path)
        agent = CLIAgent(
            "antigravity",
            model="flash",
            rate_limiter=_make_limiter(),
            config=config,
        )
        cmd = agent._build_command("hello")
        # agy takes --print as a flag whose VALUE is the prompt, so the correct
        # shape is: agy --model <model> --print <prompt>. The model is read from
        # config rather than hardcoded — this test is about argv ORDER, and
        # pinning an ID here made it fail on every model refresh.
        assert cmd == [
            "agy",
            "--model",
            config.get("model_tiers.antigravity.flash"),
            "--print",
            "hello",
        ]

    def test_claude_cli_command_shape(self, tmp_path):
        # claude headless: -p/--print is a BOOLEAN flag enabling print mode;
        # "hello" is a separate positional query arg that merely sits after it
        # (claude --model X -p hello == claude -p hello --model X)
        agent = CLIAgent(
            "claude",
            model="sonnet",
            rate_limiter=_make_limiter(),
            config=_make_config(tmp_path),
        )
        cmd = agent._build_command("hello")
        assert cmd == ["claude", "--model", "claude-sonnet-5[1m]", "-p", "hello"]

    def test_gemini_cli_command_shape(self, tmp_path):
        # gemini headless: -m takes the model, -p takes the prompt as its value
        agent = CLIAgent(
            "gemini",
            model="flash",
            rate_limiter=_make_limiter(),
            config=_make_config(tmp_path),
        )
        cmd = agent._build_command("hello")
        assert cmd == ["gemini", "-m", "gemini-3-flash-preview", "-p", "hello"]

    def test_default_prompt_args_is_trailing_positional(self, tmp_path):
        # cursor and codex use the default prompt_args (trailing positional)
        agent = CLIAgent(
            "codex",
            model="auto",
            rate_limiter=_make_limiter(),
            config=_make_config(tmp_path),
        )
        cmd = agent._build_command("hello", output_file=str(tmp_path / "out.txt"))
        assert cmd[-1] == "hello"
        assert "--print" not in cmd

    def test_prompt_args_substitution_preserves_prompt_with_braces(self, tmp_path):
        # A prompt containing {model} or {output_file} must NOT be template-substituted.
        # Only the surrounding template text of a prompt_args entry is substituted;
        # the prompt content itself is injected verbatim.
        config = _make_config(tmp_path)
        config.config["cli_agents"]["fake"] = {
            "binary": "fakecli",
            "base_args": [],
            "model_args": ["--model", "{model}"],
            "prompt_args": ["{prompt}"],
            "output": "stdout",
        }
        config.config["model_tiers"]["fake"] = {"flash": "fake-model-1"}
        agent = CLIAgent(
            "fake", model="flash", rate_limiter=_make_limiter(), config=config
        )
        raw_prompt = "use {model} and {output_file} literally"
        cmd = agent._build_command(raw_prompt)
        # The prompt must appear verbatim — no substitution inside its content.
        assert cmd[-1] == raw_prompt


class TestCLIAgentOutputCollection:
    def test_missing_binary(self, tmp_path, monkeypatch):
        import shutil

        monkeypatch.setattr(shutil, "which", lambda _: None)
        agent = CLIAgent(
            "codex",
            model="auto",
            rate_limiter=_make_limiter(),
            config=_make_config(tmp_path),
        )
        result = asyncio.run(agent._execute_impl("test", "prompt"))
        assert result["status"] == "missing"
        assert "codex" in result["error"]

    def test_stdout_strategy_collects_stdout(self, tmp_path):
        agent = CLIAgent(
            "cursor",
            model="flash",
            rate_limiter=_make_limiter(),
            config=_make_config(tmp_path),
        )
        result = agent._collect_output(0, b"the answer\n", b"", None)
        assert result["status"] == "complete"
        assert result["output"] == "the answer"

    def test_file_strategy_prefers_file_over_stdout(self, tmp_path):
        agent = CLIAgent(
            "codex",
            model="auto",
            rate_limiter=_make_limiter(),
            config=_make_config(tmp_path),
        )
        out = tmp_path / "out.txt"
        out.write_text("from file\n")
        result = agent._collect_output(0, b"from stdout", b"", str(out))
        assert result["output"] == "from file"

    def test_file_strategy_falls_back_to_stdout(self, tmp_path):
        agent = CLIAgent(
            "codex",
            model="auto",
            rate_limiter=_make_limiter(),
            config=_make_config(tmp_path),
        )
        out = tmp_path / "empty.txt"
        out.write_text("")
        result = agent._collect_output(0, b"from stdout", b"", str(out))
        assert result["output"] == "from stdout"

    def test_no_output_nonzero_exit_is_failed(self, tmp_path):
        agent = CLIAgent(
            "codex",
            model="auto",
            rate_limiter=_make_limiter(),
            config=_make_config(tmp_path),
        )
        result = agent._collect_output(1, b"", b"boom", None)
        assert result["status"] == "failed"
        assert "boom" not in result["error"]
        assert result["failure_summary"]["exit_status"] == 1

    def test_zero_exit_empty_stdout_is_malformed_output(self, tmp_path):
        agent = CLIAgent(
            "cursor",
            model="flash",
            rate_limiter=_make_limiter(),
            config=_make_config(tmp_path),
        )

        result = agent._collect_output(0, b"", b"", None)

        assert result["status"] == "failed"
        assert result["fallback_reason"] == FailureClass.MALFORMED_OUTPUT.value
        assert result["output"] == ""

    def test_zero_exit_empty_output_file_and_stdout_is_malformed_output(self, tmp_path):
        agent = CLIAgent(
            "codex",
            model="auto",
            rate_limiter=_make_limiter(),
            config=_make_config(tmp_path),
        )
        output_file = tmp_path / "empty-output.txt"
        output_file.write_text(" \n", encoding="utf-8")

        result = agent._collect_output(0, b"", b"", str(output_file))

        assert result["status"] == "failed"
        assert result["fallback_reason"] == FailureClass.MALFORMED_OUTPUT.value
        assert result["output"] == ""

    def test_nonzero_exit_with_stdout_is_failed(self, tmp_path):
        """Issue #308: usage text on stdout + exit 1 must not count as an answer."""
        agent = CLIAgent(
            "cursor",
            model="flash",
            rate_limiter=_make_limiter(),
            config=_make_config(tmp_path),
        )
        result = agent._collect_output(
            1, b"Usage: cursor-agent [options]", b"bad flag", None
        )
        assert result["status"] == "failed"
        assert "bad flag" not in result["error"]
        assert "Usage: cursor-agent" not in result["error"]
        assert result["output"] == ""


class TestCLIAgentExecution:
    def test_real_subprocess_roundtrip(self, tmp_path):
        """End-to-end through create_subprocess_exec using /bin/echo as the binary."""
        config = _make_config(tmp_path)
        config.config["cli_agents"]["fake"] = {
            "binary": "echo",
            "base_args": ["prefix"],
            "model_args": ["--model", "{model}"],
            "output": "stdout",
        }
        config.config["model_tiers"]["fake"] = {"flash": "fake-model-1"}
        agent = CLIAgent(
            "fake", model="flash", rate_limiter=_make_limiter(), config=config
        )
        result = asyncio.run(agent._execute_impl("hello world", "prompt"))
        assert result["status"] == "complete"
        assert result["output"] == "prefix --model fake-model-1 hello world"

    def test_provider_stdout_and_stderr_truncation_is_unknown(self, tmp_path):
        config = _make_config(tmp_path)
        config.config["cli_agents"]["bounded"] = {
            "binary": sys.executable,
            "base_args": [
                "-c",
                "import sys; sys.stdout.write('o'*70000); "
                "sys.stderr.write('e'*70000); raise SystemExit(1)",
            ],
            "prompt_args": [],
            "output": "stdout",
        }
        agent = CLIAgent(
            "bounded", model="auto", rate_limiter=_make_limiter(), config=config
        )

        result = asyncio.run(agent._execute_impl("ignored", "prompt"))

        assert result["status"] == "failed"
        assert result["fallback_reason"] == "unknown"
        assert result["failure_summary"]["truncated"] == "true"

    def test_provider_output_file_truncation_is_unknown(self, tmp_path):
        config = _make_config(tmp_path)
        config.config["cli_agents"]["bounded-file"] = {
            "binary": sys.executable,
            "base_args": [
                "-c",
                "from pathlib import Path; "
                "Path(r'{output_file}').write_text('x'*70000)",
            ],
            "prompt_args": [],
            "output": "file_then_stdout",
        }
        agent = CLIAgent(
            "bounded-file",
            model="auto",
            rate_limiter=_make_limiter(),
            config=config,
        )

        result = asyncio.run(agent._execute_impl("ignored", "prompt"))

        assert result["status"] == "failed"
        assert result["fallback_reason"] == "unknown"
        assert result["failure_summary"]["truncated"] == "true"

    def test_subprocess_stdin_is_devnull(self, tmp_path):
        """Headless CLIs must get EOF on stdin, not inherit the parent's.

        `claude -p` reads piped stdin; inheriting an open parent stdin makes it
        block until the timeout fires (observed: 300s hang). Pin stdin=DEVNULL.
        """
        from unittest.mock import patch

        config = _make_config(tmp_path)
        config.config["cli_agents"]["fake"] = {
            "binary": "echo",
            "base_args": [],
            "output": "stdout",
        }
        agent = CLIAgent(
            "fake", model="auto", rate_limiter=_make_limiter(), config=config
        )

        proc = _mock_process(b"ok")
        with patch("asyncio.create_subprocess_exec", return_value=proc) as spawn:
            asyncio.run(agent._execute_impl("hi", "prompt"))
        assert spawn.call_args.kwargs["stdin"] is asyncio.subprocess.DEVNULL

    def test_antigravity_success_parses_stdout(self, tmp_path):
        """G6: antigravity CLIAgent execution, mirroring the generic cases above."""
        from unittest.mock import patch

        agent = CLIAgent(
            "antigravity",
            model="flash",
            rate_limiter=_make_limiter(),
            config=_make_config(tmp_path),
        )
        proc = _mock_process(b"OK\n")
        with (
            patch("agents.runners.shutil.which", return_value="/usr/local/bin/agy"),
            patch("asyncio.create_subprocess_exec", return_value=proc),
        ):
            result = asyncio.run(agent._execute_impl("hello", "prompt"))
        assert result["status"] == "complete"
        assert result["output"] == "OK"

    def test_antigravity_nonzero_exit_is_failed(self, tmp_path):
        """G6: a non-credit-related nonzero exit stays a failed dict."""
        from unittest.mock import patch

        agent = CLIAgent(
            "antigravity",
            model="flash",
            rate_limiter=_make_limiter(),
            config=_make_config(tmp_path),
        )
        proc = _mock_process(b"", b"unrecognized flag: --bogus", 1)
        with (
            patch("agents.runners.shutil.which", return_value="/usr/local/bin/agy"),
            patch("asyncio.create_subprocess_exec", return_value=proc),
        ):
            result = asyncio.run(agent._execute_impl("hello", "prompt"))
        assert result["status"] == "failed"
        assert "unrecognized flag: --bogus" not in result["error"]

    def test_antigravity_credit_exhaustion_stderr_raises(self, tmp_path):
        """G4/G6: credit-exhaustion stderr must raise (not return a failed dict)
        so BaseAgent.execute can walk credit_fallback.antigravity."""
        from unittest.mock import patch

        agent = CLIAgent(
            "antigravity",
            model="advanced",
            rate_limiter=_make_limiter(),
            config=_make_config(tmp_path),
        )
        proc = _mock_process(b"", b"Error: quota exceeded", 1)
        with (
            patch("agents.runners.shutil.which", return_value="/usr/local/bin/agy"),
            patch("asyncio.create_subprocess_exec", return_value=proc),
            pytest.raises(ProviderAttemptError) as exc_info,
        ):
            asyncio.run(agent._execute_impl("hello", "prompt"))
        assert classify_failure(exc_info.value.evidence) is FailureClass.QUOTA

    def test_credit_exhaustion_pattern_in_stdout_does_not_raise(self, tmp_path):
        """A nonzero-exit answer whose STDOUT merely contains a pattern word
        (e.g. "credit") must not be misclassified as credit exhaustion — only
        stderr drives the fallback-triggering raise (generic CLIAgent path,
        exercised via antigravity)."""
        from unittest.mock import patch

        agent = CLIAgent(
            "antigravity",
            model="flash",
            rate_limiter=_make_limiter(),
            config=_make_config(tmp_path),
        )
        proc = _mock_process(
            b"your credit score summary is incomplete",
            b"unrecognized flag: --bogus",
            1,
        )
        with (
            patch("agents.runners.shutil.which", return_value="/usr/local/bin/agy"),
            patch("asyncio.create_subprocess_exec", return_value=proc),
        ):
            result = asyncio.run(agent._execute_impl("hello", "prompt"))
        assert result["status"] == "failed"
        assert "unrecognized flag: --bogus" not in result["error"]

    def test_antigravity_credit_exhaustion_triggers_fallback_walk(self, tmp_path):
        """G4: quota-signalling agy stderr on the first attempt must trigger the
        configured credit_fallback.antigravity tier walk (advanced -> flash)."""
        from unittest.mock import patch

        config = _make_config(tmp_path)
        agent = CLIAgent(
            "antigravity",
            model="advanced",
            rate_limiter=_make_limiter(),
            config=config,
        )
        agent.model_chain = resolve_chain(
            config.config, "antigravity", ("advanced", "flash")
        )
        agent.fallback_mode = ModelFallbackMode.AUTO
        calls = []

        async def fake_exec(*cmd, **kwargs):
            calls.append(cmd)
            if len(calls) == 1:
                return _mock_process(b"", b"Error: quota exceeded", 1)
            return _mock_process(b"OK")

        with (
            patch("agents.runners.shutil.which", return_value="/usr/local/bin/agy"),
            patch("asyncio.create_subprocess_exec", side_effect=fake_exec),
        ):
            result = asyncio.run(agent.execute("hello"))

        assert result["status"] == "complete"
        assert result["credit_fallback"] is True
        # The walk started at `advanced` and must have landed on `flash` — read
        # both from config so the assertion survives a model refresh, and assert
        # they differ so a no-op "walk" can't pass.
        assert agent.model_name == config.get("model_tiers.antigravity.flash")
        assert agent.model_name != config.get("model_tiers.antigravity.advanced")
        assert len(calls) == 2

    def test_timeout_kills_subprocess(self, tmp_path):
        """Issue #306: timeout cancellation must kill the child, not leak it."""
        import os
        import signal

        config = _make_config(tmp_path)
        pid_file = tmp_path / "child.pid"
        config.config["cli_agents"]["slowfake"] = {
            "binary": "sh",
            "base_args": ["-c", f"echo $$ > {pid_file} && exec sleep 30"],
            "output": "stdout",
        }
        agent = CLIAgent(
            "slowfake",
            model="auto",
            timeout=1,
            rate_limiter=_make_limiter(),
            config=config,
        )
        result = asyncio.run(agent.execute("ignored"))
        assert result["status"] == "failed"
        assert "timeout" in result["error"]
        child_pid = int(pid_file.read_text().strip())
        with pytest.raises(ProcessLookupError):
            os.kill(child_pid, signal.SIGTERM)  # already dead if #306 is fixed
