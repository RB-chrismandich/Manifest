"""Agent disagreement synthesis engine.

Uses any configured ``cli_agents`` provider (agy, cursor-agent, gemini, …) or,
when explicitly requested, the Anthropic SDK. Provider selection is controlled
by ``synthesis.provider`` / ``SYNTH_PROVIDER`` and ``SYNTH_CLI`` env overrides.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from agents.config import HAS_ANTHROPIC, Config, Logger

if HAS_ANTHROPIC:
    from anthropic import AsyncAnthropic

DEFAULT_PROVIDER_ORDER = (
    "antigravity",
    "cursor",
    "gemini",
    "codex",
    "claude",
)


@dataclass(frozen=True)
class SynthesisRoute:
    mode: str  # "cli" | "sdk"
    provider: str
    binary_override: str | None = None


class SynthesisEngine:
    """Handles synthesis when agents disagree"""

    def __init__(
        self,
        config: Config,
        logger: Logger | None = None,
        template_path: str | os.PathLike | None = None,
    ):
        self.config = config
        self.logger = logger
        self.synthesis_template = self._load_template(template_path)

    def _load_template(self, template_path: str | os.PathLike | None = None) -> str:
        """Load the synthesis prompt template.

        Resolution order: explicit ``template_path`` argument, the
        ``SYNTHESIS_TEMPLATE`` env var, the deployed home copy
        (``~/.claude/prompts/synthesis.md``), then the repo template next to
        this package — so fresh clones and CI exercise the repo copy instead
        of silently disabling synthesis (issue #465).
        """
        candidates: list[Path] = []
        if template_path:
            candidates.append(Path(template_path).expanduser())
        env_path = os.environ.get("SYNTHESIS_TEMPLATE")
        if env_path:
            candidates.append(Path(env_path).expanduser())
        candidates.append(Path("~/.claude/prompts/synthesis.md").expanduser())
        candidates.append(
            Path(__file__).resolve().parents[2] / "prompts" / "synthesis.md"
        )
        for candidate in candidates:
            if candidate.exists():
                with open(candidate) as f:
                    return f.read()
        if self.logger:
            tried = ", ".join(str(c) for c in candidates)
            self.logger.warning(f"Synthesis template not found: tried {tried}")
        return ""

    def _cli_provider_names(self) -> list[str]:
        order = self.config.get("synthesis.provider_order")
        if isinstance(order, list) and order:
            return [str(name) for name in order]
        agents = self.config.get("cli_agents") or {}
        if isinstance(agents, dict) and agents:
            return list(agents.keys())
        return list(DEFAULT_PROVIDER_ORDER)

    def _provider_for_synth_cli(self, cli: str) -> str | None:
        cli_name = Path(cli).name
        agents = self.config.get("cli_agents") or {}
        if not isinstance(agents, dict):
            return None
        for name, spec in agents.items():
            if not isinstance(spec, dict):
                continue
            binary = spec.get("binary", "")
            if cli == binary or cli_name == binary:
                return str(name)
        return None

    def _binary_on_path(self, binary: str) -> bool:
        if not binary:
            return False
        if os.path.isabs(binary) or binary.startswith("."):
            return os.path.isfile(binary) and os.access(binary, os.X_OK)
        return bool(shutil.which(binary))

    def _cli_provider_available(
        self, provider: str, binary_override: str | None = None
    ) -> bool:
        spec = self.config.get(f"cli_agents.{provider}")
        if not spec:
            return False
        binary = binary_override or spec.get("binary")
        return self._binary_on_path(str(binary or ""))

    def _claude_sdk_available(self) -> bool:
        return HAS_ANTHROPIC and bool(os.environ.get("ANTHROPIC_API_KEY"))

    def _resolve_synthesis_route(self) -> SynthesisRoute | None:
        backend = self.config.get("synthesis.backend", "auto")
        if backend not in ("auto", "cli", "sdk"):
            if self.logger:
                self.logger.warning(f"invalid synthesis.backend={backend!r}, using auto")
            backend = "auto"

        provider_cfg = (
            os.environ.get("SYNTH_PROVIDER")
            or self.config.get("synthesis.provider")
            or "auto"
        )
        synth_cli = os.environ.get("SYNTH_CLI")
        binary_override = synth_cli if synth_cli else None

        if provider_cfg == "auto" and synth_cli:
            inferred = self._provider_for_synth_cli(synth_cli)
            if inferred:
                provider_cfg = inferred

        if provider_cfg == "sdk" or backend == "sdk":
            return SynthesisRoute("sdk", "claude") if self._claude_sdk_available() else None

        if provider_cfg != "auto":
            ov = binary_override if synth_cli else None
            if backend != "sdk" and self._cli_provider_available(
                str(provider_cfg), ov
            ):
                return SynthesisRoute(
                    "cli",
                    str(provider_cfg),
                    binary_override=ov,
                )
            if str(provider_cfg) == "claude" and backend != "cli":
                return (
                    SynthesisRoute("sdk", "claude")
                    if self._claude_sdk_available()
                    else None
                )
            return None

        if backend == "sdk":
            return SynthesisRoute("sdk", "claude") if self._claude_sdk_available() else None

        for name in self._cli_provider_names():
            ov: str | None = None
            if synth_cli and (
                name == self._provider_for_synth_cli(synth_cli)
                or str(provider_cfg) == name
            ):
                ov = synth_cli
            if self._cli_provider_available(name, ov):
                return SynthesisRoute("cli", name, binary_override=ov)

        if backend == "auto" and self._claude_sdk_available():
            return SynthesisRoute("sdk", "claude")

        return None

    def _resolve_synthesis_backend(self) -> str | None:
        """Backward-compatible shim: returns ``cli``, ``sdk``, or ``None``."""
        route = self._resolve_synthesis_route()
        if route is None:
            return None
        return route.mode

    def _unavailable_error_message(self) -> str:
        providers = ", ".join(self._cli_provider_names())
        return (
            "Synthesis unavailable: no CLI on PATH for configured providers "
            f"({providers}). Set SYNTH_PROVIDER or SYNTH_CLI, install a panel "
            "CLI, or use synthesis.provider: sdk with ANTHROPIC_API_KEY."
        )

    async def _invoke_cli(self, route: SynthesisRoute, prompt: str) -> str:
        from agents.runners import CLIAgent

        model_tier = self.config.get("synthesis.model", "sonnet")
        timeout = self.config.get("synthesis.timeout", 300)
        agent = CLIAgent(
            route.provider,
            model=model_tier,
            timeout=timeout,
            config=self.config,
            logger=self.logger,
        )
        if route.binary_override:
            agent.binary = route.binary_override

        result = await agent._execute_impl(prompt, "synthesize")
        if result.get("status") != "complete":
            raise RuntimeError(
                result.get("error") or f"{route.provider} synthesis failed"
            )
        return result.get("output") or ""

    async def _invoke_claude_cli(self, prompt: str) -> str:
        """Backward-compatible entry for tests targeting the Claude CLI path."""
        route = SynthesisRoute("cli", "claude")
        return await self._invoke_cli(route, prompt)

    async def _invoke_claude_sdk(self, prompt: str) -> str:
        if not HAS_ANTHROPIC:
            raise RuntimeError("Anthropic SDK not available")

        client = AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
        model = self.config.get("synthesis.model", "sonnet")
        model_name = self.config.get(
            f"model_tiers.claude.{model}", "claude-sonnet-4-6"
        )
        response = await client.messages.create(
            model=model_name,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text

    async def synthesize(
        self, original_task: str, agent_results: dict, consensus: dict
    ) -> dict | None:
        """Synthesize disagreements into unified recommendation"""
        consensus_score = consensus.get("consensus_score", 100) / 100.0
        threshold = self.config.get("synthesis.threshold", 0.50)

        if consensus_score >= threshold:
            if self.logger:
                self.logger.info(
                    f"Consensus {consensus_score:.2f} >= {threshold}, skipping synthesis"
                )
            return None

        if self.logger:
            self.logger.info(
                f"Consensus {consensus_score:.2f} < {threshold}, triggering synthesis"
            )

        prompt = self._build_synthesis_prompt(original_task, agent_results)

        if not prompt:
            if self.logger:
                self.logger.warning("Failed to build synthesis prompt")
            return None

        route = self._resolve_synthesis_route()
        if route is None:
            if self.logger:
                self.logger.warning(self._unavailable_error_message())
            return {
                "triggered": True,
                "error": self._unavailable_error_message(),
                "unified_recommendation": "Synthesis failed",
            }

        if self.logger:
            self.logger.info(
                f"Synthesis using {route.mode} backend ({route.provider})"
            )

        timeout = self.config.get("synthesis.timeout", 300)
        synthesis_text = ""

        try:
            if route.mode == "cli":
                synthesis_text = await asyncio.wait_for(
                    self._invoke_cli(route, prompt), timeout=timeout
                )
            else:
                synthesis_text = await asyncio.wait_for(
                    self._invoke_claude_sdk(prompt), timeout=timeout
                )

            json_match = re.search(r"```json\s*\n(.*?)\n```", synthesis_text, re.DOTALL)
            if json_match:
                synthesis_text = json_match.group(1)

            synthesis_result = json.loads(synthesis_text)
            synthesis_result["triggered"] = True

            if self.logger:
                self.logger.info("Synthesis completed successfully")

            return synthesis_result

        except TimeoutError:
            if self.logger:
                self.logger.error(f"Synthesis timed out after {timeout}s")
            return {
                "triggered": True,
                "error": "timeout",
                "unified_recommendation": "Synthesis timed out",
            }
        except json.JSONDecodeError as e:
            if self.logger:
                self.logger.error(f"Failed to parse synthesis JSON: {e}")
            return {
                "triggered": True,
                "error": "json_parse_failed",
                "unified_recommendation": synthesis_text,
            }
        except Exception as e:
            if self.logger:
                self.logger.error(f"Synthesis failed: {e}")
            return {
                "triggered": True,
                "error": str(e),
                "unified_recommendation": "Synthesis failed",
            }

    def _build_synthesis_prompt(self, original_task: str, agent_results: dict) -> str:
        """Build synthesis prompt from template"""
        if not self.synthesis_template:
            return ""

        prompt = self.synthesis_template
        prompt = prompt.replace("{ORIGINAL_TASK}", original_task)

        if "{AGENT_OUTPUTS}" in prompt:
            sections = []
            for agent_name in sorted(agent_results):
                output = agent_results.get(agent_name, {}).get("output") or "N/A"
                sections.append(f"### {agent_name.capitalize()} Output\n\n{output}")
            prompt = prompt.replace("{AGENT_OUTPUTS}", "\n\n".join(sections))

        for agent_name in agent_results:
            output = agent_results.get(agent_name, {}).get("output", "N/A")
            prompt = prompt.replace(f"{{{agent_name.upper()}_OUTPUT}}", output)

        return prompt
