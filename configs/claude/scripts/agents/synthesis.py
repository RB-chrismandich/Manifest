"""Agent disagreement synthesis engine.

Depends on agents.config (+ optional Anthropic SDK). Invokes Claude via CLI
(OAuth session) or SDK (API key) depending on synthesis.backend config.
"""

import asyncio
import contextlib
import json
import os
import re
import shutil
import tempfile
from pathlib import Path

from agents.config import HAS_ANTHROPIC, Config, Logger, select_backend

if HAS_ANTHROPIC:
    from anthropic import AsyncAnthropic


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

    def _claude_cli_available(self) -> bool:
        spec = self.config.get("cli_agents.claude") or {}
        binary = spec.get("binary", "claude")
        if not binary:
            return False
        if os.path.isabs(binary) or binary.startswith("."):
            return os.path.isfile(binary) and os.access(binary, os.X_OK)
        return bool(shutil.which(binary))

    def _resolve_synthesis_backend(self) -> str | None:
        raw = self.config.get("synthesis.backend", "auto")
        if raw not in ("auto", "cli", "sdk"):
            if self.logger:
                self.logger.warning(f"invalid synthesis.backend={raw!r}, using auto")
            raw = "auto"

        has_cli = self._claude_cli_available()
        has_key = bool(os.environ.get("ANTHROPIC_API_KEY"))

        if raw == "cli":
            return "cli" if has_cli else None
        if raw == "sdk":
            return "sdk" if HAS_ANTHROPIC else None
        # auto — match primary claude agent, but never fall through to a doomed SDK
        if not has_key and not has_cli:
            return None
        return select_backend(
            has_sdk=HAS_ANTHROPIC, has_key=has_key, has_cli=has_cli
        )

    def _build_claude_cli_command(
        self, prompt: str, output_file: str | None
    ) -> list[str]:
        spec = self.config.get("cli_agents.claude") or {}
        binary = spec.get("binary", "claude")
        model_tier = self.config.get("synthesis.model", "sonnet")
        model_name = self.config.get(f"model_tiers.claude.{model_tier}", model_tier)

        def subst(arg: str) -> str:
            return arg.replace("{output_file}", output_file or "").replace(
                "{model}", model_name
            )

        def subst_prompt(arg: str) -> str:
            if "{prompt}" in arg:
                return prompt.join(subst(piece) for piece in arg.split("{prompt}"))
            return subst(arg)

        cmd = [binary]
        for arg in spec.get("base_args", []):
            substituted = subst(arg)
            if substituted:
                cmd.append(substituted)
        if model_name:
            cmd += [a for a in (subst(a) for a in spec.get("model_args", [])) if a]
        for arg in spec.get("prompt_args", ["-p", "{prompt}"]):
            substituted = subst_prompt(arg)
            if substituted or "{prompt}" in arg:
                cmd.append(substituted)
        return cmd

    async def _invoke_claude_cli(self, prompt: str) -> str:
        spec = self.config.get("cli_agents.claude") or {}
        output_strategy = spec.get("output", "stdout")
        if output_strategy not in ("stdout", "file_then_stdout"):
            if self.logger:
                self.logger.warning(
                    f"unsupported cli_agents.claude.output={output_strategy!r}, "
                    "using stdout"
                )
            output_strategy = "stdout"

        output_file = None
        if output_strategy == "file_then_stdout":
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".txt", delete=False, prefix="synthesis_out_"
            ) as tmp:
                output_file = tmp.name

        cmd = self._build_claude_cli_command(prompt, output_file)
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                err = stderr.decode("utf-8", errors="ignore").strip()
                raise RuntimeError(err or f"claude exited {proc.returncode}")
            text = ""
            if (
                output_strategy == "file_then_stdout"
                and output_file
                and os.path.exists(output_file)
            ):
                with open(output_file) as f:
                    text = f.read().strip()
            if not text:
                text = stdout.decode("utf-8", errors="ignore").strip()
            return text
        except asyncio.CancelledError:
            proc.kill()
            await proc.wait()
            raise
        finally:
            if output_file:
                with contextlib.suppress(OSError):
                    os.unlink(output_file)

    async def synthesize(
        self, original_task: str, agent_results: dict, consensus: dict
    ) -> dict | None:
        """Synthesize disagreements into unified recommendation"""
        # Check if synthesis is needed
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

        # Build synthesis prompt
        prompt = self._build_synthesis_prompt(original_task, agent_results)

        if not prompt:
            if self.logger:
                self.logger.warning("Failed to build synthesis prompt")
            return None

        backend = self._resolve_synthesis_backend()
        if backend is None:
            if self.logger:
                self.logger.warning(
                    "Synthesis unavailable: no claude CLI and no ANTHROPIC_API_KEY"
                )
            return {
                "triggered": True,
                "error": (
                    "Synthesis requires claude CLI (run `claude /login`) or "
                    "ANTHROPIC_API_KEY (set synthesis.backend: sdk)"
                ),
                "unified_recommendation": "Synthesis failed",
            }

        if self.logger:
            self.logger.info(f"Synthesis using claude backend: {backend}")

        timeout = self.config.get("synthesis.timeout", 300)
        synthesis_text = ""

        try:
            if backend == "cli":
                synthesis_text = await asyncio.wait_for(
                    self._invoke_claude_cli(prompt), timeout=timeout
                )
            else:
                if not HAS_ANTHROPIC:
                    if self.logger:
                        self.logger.warning(
                            "Anthropic SDK not available, cannot synthesize"
                        )
                    return None

                client = AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
                model = self.config.get("synthesis.model", "sonnet")
                model_name = self.config.get(
                    f"model_tiers.claude.{model}", "claude-sonnet-4-6"
                )
                response = await asyncio.wait_for(
                    client.messages.create(
                        model=model_name,
                        max_tokens=4096,
                        messages=[{"role": "user", "content": prompt}],
                    ),
                    timeout=timeout,
                )
                synthesis_text = response.content[0].text

            # Parse JSON response
            json_match = re.search(
                r"```json\s*\n(.*?)\n```", synthesis_text, re.DOTALL
            )
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

        # Replace template variables
        prompt = prompt.replace("{ORIGINAL_TASK}", original_task)

        # Build one output section per agent actually present, so newer
        # providers (codex, antigravity) aren't silently dropped from
        # disagreement resolution (issue #309).
        if "{AGENT_OUTPUTS}" in prompt:
            sections = []
            for agent_name in sorted(agent_results):
                output = agent_results.get(agent_name, {}).get("output") or "N/A"
                sections.append(f"### {agent_name.capitalize()} Output\n\n{output}")
            prompt = prompt.replace("{AGENT_OUTPUTS}", "\n\n".join(sections))

        # Legacy fixed placeholders — replace for every agent present
        for agent_name in agent_results:
            output = agent_results.get(agent_name, {}).get("output", "N/A")
            prompt = prompt.replace(f"{{{agent_name.upper()}_OUTPUT}}", output)

        return prompt
