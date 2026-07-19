"""Agent disagreement synthesis engine.

Uses any configured ``cli_agents`` provider via ``agents.cli_invoke``; Anthropic
SDK when ``synthesis.provider: sdk`` (or auto fallback with API key).
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path

from agents.cli_invoke import CliRoute, invoke_cli_timed, resolve_cli_route
from agents.config import HAS_ANTHROPIC, Config, Logger

if HAS_ANTHROPIC:
    from anthropic import AsyncAnthropic

# Backward-compatible alias for tests and callers.
SynthesisRoute = CliRoute


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

    def _resolve_synthesis_route(self) -> CliRoute | None:
        return resolve_cli_route(
            self.config,
            section="synthesis",
            env_prefix="SYNTH",
            allow_sdk=True,
        )

    def _resolve_synthesis_backend(self) -> str | None:
        route = self._resolve_synthesis_route()
        return route.mode if route else None

    def _cli_provider_available(
        self, provider: str, binary_override: str | None = None
    ) -> bool:
        from agents.cli_invoke import cli_provider_available

        return cli_provider_available(self.config, provider, binary_override)

    def _unavailable_error_message(self) -> str:
        from agents.cli_invoke import _provider_names

        providers = ", ".join(_provider_names(self.config, "synthesis"))
        return (
            "Synthesis unavailable: no CLI on PATH for configured providers "
            f"({providers}). Set SYNTH_PROVIDER or SYNTH_CLI, install a panel "
            "CLI, or use synthesis.provider: sdk with ANTHROPIC_API_KEY."
        )

    async def _invoke_cli(self, route: CliRoute, prompt: str) -> str:
        model_tier = self.config.get("synthesis.model", "sonnet")
        timeout = self.config.get("synthesis.timeout", 300)
        return await invoke_cli_timed(
            route,
            prompt,
            self.config,
            model_tier=model_tier,
            timeout=timeout,
            logger=self.logger,
        )

    async def _invoke_claude_cli(self, prompt: str) -> str:
        return await self._invoke_cli(CliRoute("cli", "claude"), prompt)

    async def _invoke_claude_sdk(self, prompt: str) -> str:
        if not HAS_ANTHROPIC:
            raise RuntimeError("Anthropic SDK not available")

        client = AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
        model = self.config.get("synthesis.model", "sonnet")
        model_name = self.config.get(f"model_tiers.claude.{model}", "claude-sonnet-4-6")
        response = await client.messages.create(
            model=model_name,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text

    async def synthesize(
        self, original_task: str, agent_results: dict, consensus: dict
    ) -> dict | None:
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
            self.logger.info(f"Synthesis using {route.mode} backend ({route.provider})")

        timeout = self.config.get("synthesis.timeout", 300)
        synthesis_text = ""

        try:
            if route.mode == "cli":
                synthesis_text = await self._invoke_cli(route, prompt)
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
