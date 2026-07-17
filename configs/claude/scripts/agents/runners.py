"""Individual agent implementations: base class and concrete provider agents.

Dependency graph: agents.config → agents.runners (no other cross-module deps).
"""

import asyncio
import contextlib
import os
import shutil
import sys
import tempfile
import time
from typing import Any

from agents.config import (
    HAS_ANTHROPIC,
    HAS_GENAI,
    HAS_GENAI_NEW,
    Config,
    Logger,
    RateLimiter,
    genai,
)

if HAS_ANTHROPIC:
    from anthropic import AsyncAnthropic


# ---------------------------------------------------------------------------
# BaseAgent
# ---------------------------------------------------------------------------


class BaseAgent:
    """Abstract base class for all agents"""

    def __init__(
        self,
        name: str,
        model: str,
        timeout: int,
        rate_limiter: RateLimiter,
        config: Config = None,
        logger: Logger | None = None,
        streaming: bool = False,
        progress_callback=None,
    ):
        self.name = name
        self.model = model
        self.model_name = (
            model  # Concrete name; subclasses re-resolve via _resolve_model
        )
        self.original_model = model  # Track original for fallback
        self.timeout = timeout
        self.rate_limiter = rate_limiter
        self.config = config or Config()
        self.logger = logger
        self.credit_fallback_used = False
        self.streaming = streaming
        self.progress_callback = progress_callback

    async def execute(self, prompt: str, mode: str = "prompt") -> dict:
        """Execute agent with rate limiting, timeout, and credit fallback"""
        await self.rate_limiter.acquire()

        start_time = time.time()

        if self.logger:
            self.logger.info(
                f"[{self.name}] Starting execution with model {self.model}"
            )

        # Try with original model first, then fallback on credit exhaustion
        for _attempt in range(3):  # Max 3 fallback attempts
            try:
                # Use streaming or regular execution
                if self.streaming and hasattr(self, "_execute_streaming"):
                    result = await asyncio.wait_for(
                        self._execute_streaming(prompt, mode), timeout=self.timeout
                    )
                else:
                    result = await asyncio.wait_for(
                        self._execute_impl(prompt, mode), timeout=self.timeout
                    )

                result["duration_seconds"] = round(time.time() - start_time, 2)
                result["credit_fallback"] = self.credit_fallback_used

                if self.logger:
                    self.logger.info(
                        f"[{self.name}] Completed in {result['duration_seconds']}s"
                    )

                return result

            except TimeoutError:
                if self.logger:
                    self.logger.error(f"[{self.name}] Timeout after {self.timeout}s")

                return {
                    "status": "failed",
                    "error": f"timeout after {self.timeout}s",
                    "duration_seconds": round(time.time() - start_time, 2),
                    "credit_fallback": self.credit_fallback_used,
                }
            except Exception as e:
                error_str = str(e).lower()

                # Check for credit/quota exhaustion errors
                if (
                    self._is_credit_exhaustion_error(error_str)
                    and not self.credit_fallback_used
                ):
                    fallback_model = self._get_fallback_model()
                    if fallback_model:
                        if self.logger:
                            self.logger.warning(
                                f"[{self.name}] Credit exhausted, falling back: {self.model} → {fallback_model}"
                            )
                        print(
                            f"  [{self.name}] Credit exhausted, falling back: {self.model} → {fallback_model}",
                            file=sys.stderr,
                        )
                        self.model = fallback_model
                        # Re-resolve the concrete model name or the retry
                        # silently re-runs the exhausted model (issue #304)
                        self.model_name = self._resolve_model(fallback_model)
                        self.credit_fallback_used = True
                        await asyncio.sleep(1)  # Brief delay before retry
                        continue

                # Non-recoverable error
                if self.logger:
                    self.logger.error(f"[{self.name}] Error: {e!s}")

                return {
                    "status": "failed",
                    "error": str(e),
                    "duration_seconds": round(time.time() - start_time, 2),
                    "credit_fallback": self.credit_fallback_used,
                }

        # All fallback attempts exhausted
        if self.logger:
            self.logger.error(f"[{self.name}] All credit fallback attempts exhausted")

        return {
            "status": "failed",
            "error": "all credit fallback attempts exhausted",
            "duration_seconds": round(time.time() - start_time, 2),
            "credit_fallback": self.credit_fallback_used,
        }

    def _is_credit_exhaustion_error(self, error: str) -> bool:
        """Check if error indicates credit/quota exhaustion"""
        exhaustion_patterns = [
            "quota",
            "credit",
            "rate limit",
            "capacity",
            "429",
            "too many requests",
            "resource_exhausted",
        ]
        return any(pattern in error for pattern in exhaustion_patterns)

    def _resolve_model(self, tier: str) -> str | None:
        """Resolve a model tier to a concrete model name (subclasses override)."""
        return tier

    def _get_fallback_model(self) -> str | None:
        """Get next fallback model tier"""
        fallback_chain = self.config.get(f"credit_fallback.{self.name}", [])

        # Find current position in fallback chain
        try:
            current_index = fallback_chain.index(self.original_model)
            if current_index < len(fallback_chain) - 1:
                return fallback_chain[current_index + 1]
        except (ValueError, IndexError):
            pass

        return None

    async def _execute_impl(self, prompt: str, mode: str) -> dict:
        """Implementation-specific execution logic"""
        raise NotImplementedError


# ---------------------------------------------------------------------------
# ClaudeAgent
# ---------------------------------------------------------------------------


class ClaudeAgent(BaseAgent):
    """Claude agent using official Anthropic SDK (API key only for now)"""

    def __init__(
        self,
        model: str = "sonnet",
        timeout: int = 120,
        rate_limiter: RateLimiter = None,
        config: Config = None,
        logger: Logger | None = None,
        streaming: bool = False,
        progress_callback=None,
    ):
        if not HAS_ANTHROPIC:
            raise ImportError("anthropic package not installed")

        config = config or Config()
        super().__init__(
            "claude",
            model,
            timeout,
            rate_limiter,
            config,
            logger,
            streaming,
            progress_callback,
        )
        self.model_name = self._resolve_model(model)
        self.client = self._create_client()

    def _create_client(self) -> "AsyncAnthropic":
        """Create Claude client (API key required)"""
        # Anthropic SDK reads from ANTHROPIC_API_KEY env var automatically
        # No OAuth support yet, but prepared for future
        api_key = os.environ.get("ANTHROPIC_API_KEY")

        if not api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY environment variable not set\n"
                "Get your API key from: https://console.anthropic.com/\n"
                "Then: export ANTHROPIC_API_KEY='sk-...'"
            )

        return AsyncAnthropic(api_key=api_key)

    def _resolve_model(self, tier: str) -> str:
        """Resolve model tier to full model name"""
        return self.config.get(f"model_tiers.claude.{tier}", tier)

    async def _execute_impl(self, prompt: str, mode: str) -> dict:
        """Execute Claude API request"""
        response = await self.client.messages.create(
            model=self.model_name,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )

        return {
            "status": "complete",
            "output": response.content[0].text,
            "model": self.model_name,
            "validated": False,
        }

    async def _execute_streaming(self, prompt: str, mode: str) -> dict:
        """Execute Claude API request with streaming"""
        output_buffer = []

        async with self.client.messages.stream(
            model=self.model_name,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            async for text in stream.text_stream:
                output_buffer.append(text)
                if self.progress_callback:
                    await self.progress_callback(self.name, "".join(output_buffer))

        return {
            "status": "complete",
            "output": "".join(output_buffer),
            "model": self.model_name,
            "validated": False,
        }


# ---------------------------------------------------------------------------
# GeminiAgent
# ---------------------------------------------------------------------------


class GeminiAgent(BaseAgent):
    """Gemini agent using official Google SDK with OAuth support"""

    def __init__(
        self,
        model: str = "flash",
        timeout: int = 120,
        rate_limiter: RateLimiter = None,
        config: Config = None,
        logger: Logger | None = None,
        streaming: bool = False,
        progress_callback=None,
    ):
        if not HAS_GENAI:
            raise ImportError("google-generativeai package not installed")

        config = config or Config()
        super().__init__(
            "gemini",
            model,
            timeout,
            rate_limiter,
            config,
            logger,
            streaming,
            progress_callback,
        )
        self.model_name = self._resolve_model(model)
        self.client = self._create_client()

    def _create_client(self) -> Any:
        """Create Gemini client with OAuth or API key"""
        api_key = os.environ.get("GOOGLE_API_KEY")

        if HAS_GENAI_NEW:
            # Use new google.genai package
            if api_key:
                return genai.Client(api_key=api_key)
            else:
                # Use OAuth/ADC
                try:
                    return genai.Client()
                except Exception as e:
                    if self.logger:
                        self.logger.warning(f"[gemini] OAuth not configured: {e}")
                    print(
                        "  [gemini] OAuth not configured, trying without credentials",
                        file=sys.stderr,
                    )
                    print(
                        "  [gemini] Run the gemini CLI once to complete OAuth"
                        " (or set GOOGLE_API_KEY)",
                        file=sys.stderr,
                    )
                    raise
        else:
            # Use legacy google-generativeai package
            if api_key:
                genai.configure(api_key=api_key)
            else:
                # OAuth with legacy package
                try:
                    genai.configure()
                except Exception as e:
                    if self.logger:
                        self.logger.warning(f"[gemini] OAuth not configured: {e}")
                    print("  [gemini] OAuth not configured", file=sys.stderr)
                    print(
                        "  [gemini] Run the gemini CLI once to complete OAuth"
                        " or set GOOGLE_API_KEY",
                        file=sys.stderr,
                    )
                    raise
            return genai

    def _resolve_model(self, tier: str) -> str:
        """Resolve model tier to full model name"""
        return self.config.get(f"model_tiers.gemini.{tier}", tier)

    async def _execute_impl(self, prompt: str, mode: str) -> dict:
        """Execute Gemini API request"""
        if HAS_GENAI_NEW:
            # New package API
            response = await asyncio.to_thread(
                self.client.models.generate_content,
                model=self.model_name,
                contents=prompt,
            )
        else:
            # Legacy package API
            model = genai.GenerativeModel(self.model_name)
            response = await asyncio.to_thread(model.generate_content, prompt)

        return {
            "status": "complete",
            "output": response.text,
            "model": self.model_name,
            "validated": False,
        }

    async def _execute_streaming(self, prompt: str, mode: str) -> dict:
        """Execute Gemini API request with streaming"""
        output_buffer = []

        if HAS_GENAI_NEW:
            # New package streaming API
            response_stream = await asyncio.to_thread(
                self.client.models.generate_content_stream,
                model=self.model_name,
                contents=prompt,
            )
        else:
            # Legacy package streaming API
            model = genai.GenerativeModel(self.model_name)
            response_stream = await asyncio.to_thread(
                model.generate_content, prompt, stream=True
            )

        # Process stream
        for chunk in response_stream:
            if hasattr(chunk, "text"):
                output_buffer.append(chunk.text)
                if self.progress_callback:
                    await self.progress_callback(self.name, "".join(output_buffer))

        return {
            "status": "complete",
            "output": "".join(output_buffer),
            "model": self.model_name,
            "validated": False,
        }


# ---------------------------------------------------------------------------
# CLIAgent
# ---------------------------------------------------------------------------


class CLIAgent(BaseAgent):
    """Generic CLI-based agent driven by the cli_agents config block.

    All provider variation (binary, argument shape, output capture) is data in
    parallel_agent.yml — adding a CLI provider is a configuration change, not a
    new class. Args are always exec'd as a list (never a shell string).
    """

    def __init__(
        self,
        provider: str,
        model: str = "flash",
        timeout: int = 120,
        rate_limiter: RateLimiter = None,
        config: Config = None,
        logger: Logger | None = None,
        streaming: bool = False,
        progress_callback=None,
    ):
        config = config or Config()
        super().__init__(
            provider,
            model,
            timeout,
            rate_limiter,
            config,
            logger,
            streaming,
            progress_callback,
        )
        # get_cli_agent_spec falls back to agent_roster.yml when `provider`
        # has no cli_agents.<provider> entry — this is what lets a new
        # CLI-only agent be added purely via the roster, with no code
        # change and no new subclass (see Config.get_cli_agent_spec).
        spec = config.get_cli_agent_spec(provider)
        if not spec:
            raise ValueError(f"no cli_agents config for provider: {provider}")
        self.binary = spec.get("binary")
        if not self.binary:
            raise ValueError(f"cli_agents.{provider}.binary is required but missing")
        self.base_args = list(spec.get("base_args", []))
        self.model_args = list(spec.get("model_args", []))
        self.prompt_args = list(spec.get("prompt_args", ["{prompt}"]))
        self.output_strategy = spec.get("output", "stdout")
        self.model_name = self._resolve_model(model)

    def _resolve_model(self, tier: str) -> str | None:
        """Resolve model tier to full model name. Returns None for 'auto'."""
        if tier == "auto":
            return None
        resolved = self.config.get(f"model_tiers.{self.name}.{tier}")
        return resolved if resolved else tier

    def _build_command(self, prompt: str, output_file: str | None = None) -> list[str]:
        """Assemble argv: binary + base_args + optional model group + prompt_args.

        model_args are appended only when a model is resolved — the group is
        dropped atomically, so an optional model can never leave a dangling flag.
        prompt_args controls how the prompt is passed (default: trailing positional
        {prompt}).  The prompt content itself is never template-substituted — only
        the surrounding template text in a prompt_args entry is substituted, then
        the raw prompt is spliced in via {prompt}.
        """

        def _subst(arg: str) -> str:
            arg = arg.replace("{output_file}", output_file or "")
            arg = arg.replace("{model}", self.model_name or "")
            return arg

        def _subst_prompt(arg: str) -> str:
            if "{prompt}" in arg:
                # Split on the placeholder, substitute non-prompt placeholders in the
                # surrounding template text only, then rejoin with the raw prompt —
                # the prompt content itself is never template-substituted.
                return prompt.join(_subst(piece) for piece in arg.split("{prompt}"))
            return _subst(arg)

        cmd = [self.binary]
        for arg in self.base_args:
            substituted = _subst(arg)
            if substituted:
                cmd.append(substituted)
        if self.model_name:
            # Drop empty substitutions here too — a stray {output_file} in
            # model_args would otherwise inject a "" argv element
            cmd += [a for a in (_subst(a) for a in self.model_args) if a]
        for arg in self.prompt_args:
            substituted = _subst_prompt(arg)
            # Keep an empty result only when it carries the prompt itself
            # (preserves positional semantics for an empty prompt)
            if substituted or "{prompt}" in arg:
                cmd.append(substituted)
        return cmd

    def _collect_output(
        self, returncode: int, stdout: bytes, stderr: bytes, output_file: str | None
    ) -> dict:
        """Apply the provider's output strategy: file > stdout > stderr-on-error."""
        output = ""
        if output_file and os.path.exists(output_file):
            with open(output_file) as f:
                output = f.read().strip()
        if not output:
            output = stdout.decode("utf-8", errors="ignore").strip()
        if returncode != 0:
            # A nonzero exit means usage text / error banners, not an answer —
            # letting it through corrupted consensus and synthesis (issue #308).
            stderr_text = stderr.decode("utf-8", errors="ignore").strip()
            error_parts = [f"exit code {returncode}"]
            if stderr_text:
                error_parts.append(stderr_text)
            if output:
                error_parts.append(f"stdout: {output}")
            return {
                "status": "failed",
                "error": "; ".join(error_parts),
                # Kept separate from "error" (which also carries stdout text)
                # so credit-exhaustion classification checks stderr only —
                # an answer's stdout content must never trigger a false
                # "quota exceeded" fallback walk.
                "stderr": stderr_text,
                "output": "",
                "model": self.model_name or "auto",
            }
        return {
            "status": "complete",
            "output": output,
            "model": self.model_name or "auto",
            "validated": False,
        }

    async def _execute_impl(self, prompt: str, mode: str) -> dict:
        if not shutil.which(self.binary):
            return {
                "status": "missing",
                "error": f"{self.binary} command not found",
                "output": "",
            }

        output_file = None
        if self.output_strategy == "file_then_stdout":
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".txt", delete=False, prefix=f"{self.name}_out_"
            ) as tmp:
                output_file = tmp.name

        try:
            cmd = self._build_command(prompt, output_file)
            # stdin=DEVNULL so headless CLIs (e.g. `claude -p`, which reads piped
            # stdin) get immediate EOF instead of inheriting and blocking on the
            # parent's stdin until the timeout fires.
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await proc.communicate()
            except asyncio.CancelledError:
                # Timeout cancellation (asyncio.wait_for in BaseAgent.execute)
                # interrupts communicate() but leaves the child running —
                # kill it before the finally block unlinks its output file
                # out from under it (issue #306).
                proc.kill()
                await proc.wait()
                raise
            result = self._collect_output(proc.returncode, stdout, stderr, output_file)
            if result["status"] == "failed" and self._is_credit_exhaustion_error(
                result.get("stderr", "").lower()
            ):
                # Mirror the SDK agents (Claude/Gemini raise real exceptions on
                # quota errors, which BaseAgent.execute catches to walk
                # credit_fallback): a CLI provider's credit-exhaustion stderr
                # must also raise, or the configured credit_fallback chain
                # (shared by every cli_agents provider: claude/gemini CLI
                # fallback, cursor, codex, antigravity) is dead — a "failed"
                # dict never reaches BaseAgent.execute's except-block.
                raise RuntimeError(result["error"])
            return result
        finally:
            if output_file:
                with contextlib.suppress(OSError):
                    os.unlink(output_file)
