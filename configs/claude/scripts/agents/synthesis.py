"""Agent disagreement synthesis engine.

Independently importable: depends on agents.config and stdlib only.
Uses Anthropic SDK when available (HAS_ANTHROPIC) for synthesis calls.
"""

import asyncio
import json
import os
import re
from pathlib import Path
from typing import Dict, Optional

from agents.config import Config, HAS_ANTHROPIC, Logger

if HAS_ANTHROPIC:
    from anthropic import AsyncAnthropic


class SynthesisEngine:
    """Handles synthesis when agents disagree"""

    def __init__(self, config: Config, logger: Optional[Logger] = None):
        self.config = config
        self.logger = logger
        self.synthesis_template = self._load_template()

    def _load_template(self) -> str:
        """Load synthesis prompt template"""
        template_path = Path("~/.claude/prompts/synthesis.md").expanduser()
        if not template_path.exists():
            if self.logger:
                self.logger.warning(f"Synthesis template not found: {template_path}")
            return ""

        with open(template_path, "r") as f:
            return f.read()

    async def synthesize(
        self, original_task: str, agent_results: Dict, consensus: Dict
    ) -> Optional[Dict]:
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

        # Execute synthesis using Claude
        try:
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
            timeout = self.config.get("synthesis.timeout", 300)

            response = await asyncio.wait_for(
                client.messages.create(
                    model=model_name,
                    max_tokens=4096,
                    messages=[{"role": "user", "content": prompt}],
                ),
                timeout=timeout,
            )

            # Parse JSON response
            synthesis_text = response.content[0].text
            # Extract JSON from markdown code blocks if present
            json_match = re.search(r"```json\s*\n(.*?)\n```", synthesis_text, re.DOTALL)
            if json_match:
                synthesis_text = json_match.group(1)

            synthesis_result = json.loads(synthesis_text)
            synthesis_result["triggered"] = True

            if self.logger:
                self.logger.info("Synthesis completed successfully")

            return synthesis_result

        except asyncio.TimeoutError:
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

    def _build_synthesis_prompt(self, original_task: str, agent_results: Dict) -> str:
        """Build synthesis prompt from template"""
        if not self.synthesis_template:
            return ""

        prompt = self.synthesis_template

        # Replace template variables
        prompt = prompt.replace("{ORIGINAL_TASK}", original_task)

        # Replace agent outputs
        for agent_name in ["gemini", "claude", "cursor"]:
            output = agent_results.get(agent_name, {}).get("output", "N/A")
            prompt = prompt.replace(f"{{{agent_name.upper()}_OUTPUT}}", output)

        return prompt
