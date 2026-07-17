"""Configuration, logging, and rate-limiting infrastructure.

All other agents modules import from here. No cross-module dependencies.
"""

import asyncio
import logging
import os
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

import yaml

# ---------------------------------------------------------------------------
# Optional SDK imports — exported so other modules don't repeat the guards
# ---------------------------------------------------------------------------

try:
    from anthropic import AsyncAnthropic

    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False
    AsyncAnthropic = None  # type: ignore[assignment,misc]

try:
    import google.genai as _genai_new

    HAS_GENAI_NEW = True
    HAS_GENAI = True
except ImportError:
    _genai_new = None  # type: ignore[assignment]
    HAS_GENAI_NEW = False
    try:
        from google import genai as _genai_legacy  # type: ignore[no-redef]

        HAS_GENAI = True
    except ImportError:
        _genai_legacy = None  # type: ignore[assignment]
        HAS_GENAI = False

if HAS_GENAI_NEW:
    genai = _genai_new
elif HAS_GENAI:
    genai = _genai_legacy  # type: ignore[assignment]
else:
    genai = None


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


def load_agent_roster(roster_path: str | None = None) -> dict[str, dict]:
    """Load the `agents:` map from agent_roster.yml.

    Returns {} if the file is missing or malformed — callers treat the
    roster as an optional extensibility source, never a hard dependency.
    """
    if roster_path is None:
        roster_path = os.path.expanduser("~/.claude/config/agent_roster.yml")

    if not os.path.exists(roster_path):
        return {}

    try:
        with open(roster_path) as f:
            data = yaml.safe_load(f) or {}
    except (OSError, yaml.YAMLError):
        return {}

    agents = data.get("agents")
    return agents if isinstance(agents, dict) else {}


class Config:
    """Configuration manager for parallel agent"""

    def __init__(self, config_path: str | None = None, roster_path: str | None = None):
        if config_path is None:
            config_path = os.path.expanduser("~/.claude/config/parallel_agent.yml")

        self.config_path = config_path
        self.config = self._load_config()

        # Lazily loaded on first get_cli_agent_spec() miss against cli_agents —
        # None means "not loaded yet", {} means "loaded, empty/missing file".
        self._roster_path = roster_path
        self._roster: dict[str, dict] | None = None

    def _load_config(self) -> dict:
        """Load configuration from YAML file"""
        if not os.path.exists(self.config_path):
            return self._default_config()

        with open(self.config_path) as f:
            return yaml.safe_load(f)

    def _default_config(self) -> dict:
        """Default configuration if file doesn't exist"""
        return {
            "rate_limits": {
                "claude": {
                    "requests_per_minute": 60,
                    "tokens_per_minute": 160000,
                    "burst_size": 5,
                },
                "gemini": {
                    "requests_per_minute": 30,
                    "tokens_per_minute": 32000,
                    "burst_size": 3,
                },
                "cursor": {"requests_per_minute": 100, "burst_size": 10},
                "codex": {"requests_per_minute": 100, "burst_size": 10},
                "antigravity": {"requests_per_minute": 100, "burst_size": 10},
            },
            "timeouts": {"default": 120, "review": 600},
            "model_tiers": {
                "claude": {
                    "haiku": "claude-haiku-4-5-20251001",
                    "sonnet": "claude-sonnet-5",
                    "opus": "claude-opus-4-8",
                    "fable": "claude-fable-5",
                },
                "gemini": {
                    "flash": "gemini-3-flash-preview",
                    "pro": "gemini-3-pro-preview",
                },
                "cursor": {
                    "mini": "auto",
                    "flash": "auto",
                    "advanced": "auto",
                },
                "codex": {
                    "mini": "gpt-5.4-mini",
                    "flash": "gpt-5.4",
                    "advanced": "gpt-5.5",
                },
                # Verified current against the live `agy models` catalog on
                # 2026-07-11 (agy 1.1.1) — mirrors parallel_agent.yml
                # model_tiers.antigravity; re-verify with `agy models` before
                # changing, do not "bump" opportunistically.
                "antigravity": {
                    "mini": "Gemini 3.5 Flash (Low)",
                    "flash": "Gemini 3.5 Flash (High)",
                    "advanced": "Claude Opus 4.6 (Thinking)",
                },
            },
            "cli_agents": {
                # claude/gemini entries back the OAuth CLI fallback used when
                # the provider SDK or its API key is unavailable (see
                # agents.config.select_backend).
                "claude": {
                    "binary": "claude",
                    "base_args": [],
                    "model_args": ["--model", "{model}"],
                    "prompt_args": ["-p", "{prompt}"],
                    "output": "stdout",
                },
                "gemini": {
                    "binary": "gemini",
                    "base_args": [],
                    "model_args": ["-m", "{model}"],
                    "prompt_args": ["-p", "{prompt}"],
                    "output": "stdout",
                },
                "cursor": {
                    "binary": "cursor-agent",
                    "base_args": [
                        "--print",
                        "--output-format",
                        "text",
                        "--mode",
                        "ask",
                    ],
                    "model_args": ["--model", "{model}"],
                    "prompt_args": ["{prompt}"],
                    "output": "stdout",
                },
                "codex": {
                    "binary": "codex",
                    "base_args": [
                        "exec",
                        "--full-auto",
                        "--color",
                        "never",
                        "--output-last-message",
                        "{output_file}",
                    ],
                    "model_args": ["--model", "{model}"],
                    "output": "file_then_stdout",
                },
                "antigravity": {
                    "binary": "agy",
                    "base_args": [],
                    "model_args": ["--model", "{model}"],
                    "prompt_args": ["--print", "{prompt}"],
                    "output": "stdout",
                },
            },
            "credit_fallback": {
                "claude": ["fable", "opus", "sonnet", "haiku"],
                "cursor": ["advanced", "flash", "mini"],
                "gemini": ["pro", "flash"],
                "codex": ["advanced", "flash", "mini"],
                "antigravity": ["advanced", "flash", "mini"],
            },
            "synthesis": {
                "enabled": True,
                "threshold": 0.50,
                "model": "sonnet",
                "timeout": 300,
                "backend": "auto",
            },
            "validation": {"consensus_threshold": {"high": 0.80, "medium": 0.50}},
        }

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value by dot-notation key"""
        keys = key.split(".")
        value = self.config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
        return value if value is not None else default

    def get_cli_agent_spec(self, provider: str) -> dict | None:
        """Resolve a CLIAgent spec for `provider`.

        `cli_agents.<provider>` (parallel_agent.yml, or the hardcoded
        defaults mirroring it) remains the primary, authoritative source —
        it carries base_args/output strategy that agent_roster.yml
        deliberately does not duplicate (see agent_roster.yml header).

        A provider absent from cli_agents falls back to agent_roster.yml,
        using the roster's binary/model_args/prompt_args with generic-CLI
        defaults (base_args=[], output="stdout") for the fields the roster
        omits. This makes roster-only construction possible at THIS layer —
        no cli_agents entry, no new Python class needed for `Config`/
        `CLIAgent` to build a spec. It does NOT make a roster-only agent
        selectable or runnable end-to-end today: `cli.py`'s provider
        selection, CLI flags, and rate-limiter/model wiring are still
        hardcoded per-provider (not roster-aware). Closing that gap is
        out of this task's scope — see agent_roster.yml.
        """
        spec = self.get(f"cli_agents.{provider}")
        if spec:
            return spec

        if self._roster is None:
            self._roster = load_agent_roster(self._roster_path)

        entry = self._roster.get(provider)
        if not entry:
            return None

        return {
            "binary": entry.get("binary"),
            "base_args": [],
            "model_args": list(entry.get("model_args", [])),
            "prompt_args": list(entry.get("prompt_args", ["{prompt}"])),
            "output": "stdout",
        }


def select_backend(has_sdk: bool, has_key: bool, has_cli: bool) -> str | None:
    """Pick the execution backend for an SDK-capable provider (claude, gemini).

    The SDK is preferred only when both the package and its API key are
    present. Otherwise fall back to the provider CLI when it is on PATH —
    OAuth-authenticated CLIs work without API keys, which is the common
    subscription-login setup. As a last resort, an installed SDK may carry
    its own auth (ADC/OAuth), so try it before giving up.

    Returns "sdk", "cli", or None (provider unavailable).
    """
    if has_sdk and has_key:
        return "sdk"
    if has_cli:
        return "cli"
    if has_sdk:
        return "sdk"
    return None


# ---------------------------------------------------------------------------
# ServiceConfig
# ---------------------------------------------------------------------------


class ServiceConfig:
    """Service configuration manager reading from services.yml"""

    def __init__(self, config_path: str | None = None):
        if config_path is None:
            config_path = os.path.expanduser("~/.claude/config/services.yml")
        self.config_path = config_path
        self._data = self._load()

    def _load(self) -> dict:
        """Load services.yml or return all-enabled defaults."""
        if os.path.exists(self.config_path):
            with open(self.config_path) as f:
                data = yaml.safe_load(f) or {}
                return data
        # All-enabled defaults when file is missing
        return {
            "services": {
                "claude": {"enabled": True},
                "gemini": {"enabled": True},
                "cursor": {"enabled": True},
                "codex": {"enabled": True},
                "antigravity": {"enabled": True},
            },
            "minimum_agents": 2,
        }

    def is_enabled(self, service_name: str) -> bool:
        """Check if a service is enabled in services.yml."""
        services = self._data.get("services", {})
        svc = services.get(service_name, {})
        return bool(svc.get("enabled", True))

    @property
    def minimum_agents(self) -> int:
        """Minimum agents required for parallel orchestration."""
        return int(self._data.get("minimum_agents", 2))

    def check_minimum_agents(self, count: int) -> str | None:
        """Return a warning message if count < minimum, else None."""
        minimum = self.minimum_agents
        if count < minimum:
            return (
                f"Warning: Only {count} agent(s) enabled, "
                f"minimum recommended is {minimum}. "
                f"Parallel orchestration may produce lower-confidence results."
            )
        return None


# ---------------------------------------------------------------------------
# Logger
# ---------------------------------------------------------------------------


class Logger:
    """Centralized logging with rotation and structured output"""

    def __init__(self, config: Config):
        self.config = config
        self.correlation_id = None
        self.logger = self._setup_logger()

    def _setup_logger(self) -> logging.Logger:
        """Setup rotating file logger with structured JSON output"""
        logger = logging.getLogger("parallel_agent")
        logger.setLevel(getattr(logging, self.config.get("logging.level", "INFO")))

        # Avoid duplicate handlers
        if logger.handlers:
            return logger

        # Setup rotating file handler
        log_file = Path(
            self.config.get(
                "logging.file", "~/.claude/.agent_outputs/parallel_agent.log"
            )
        ).expanduser()
        log_file.parent.mkdir(parents=True, exist_ok=True, mode=0o700)

        handler = RotatingFileHandler(
            log_file,
            maxBytes=self.config.get("logging.max_bytes", 10485760),  # 10MB
            backupCount=self.config.get("logging.backup_count", 5),
        )

        # JSON-like structured format
        formatter = logging.Formatter(
            '{"timestamp": "%(asctime)s", "level": "%(levelname)s", "correlation_id": "%(correlation_id)s", "message": "%(message)s"}',
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

        return logger

    def set_correlation_id(self, correlation_id: str):
        """Set correlation ID for this execution"""
        self.correlation_id = correlation_id

    def _log(self, level: str, message: str, **kwargs):
        """Internal logging method with correlation ID"""
        extra = {"correlation_id": self.correlation_id or "N/A"}
        getattr(self.logger, level)(message, extra=extra, **kwargs)

    def debug(self, message: str):
        self._log("debug", message)

    def info(self, message: str):
        self._log("info", message)

    def warning(self, message: str):
        self._log("warning", message)

    def error(self, message: str):
        self._log("error", message)


# ---------------------------------------------------------------------------
# RateLimiter
# ---------------------------------------------------------------------------


class RateLimiter:
    """Token bucket rate limiter with adaptive backoff"""

    def __init__(
        self,
        requests_per_minute: int = 60,
        burst_size: int = 5,
        tokens_per_minute: int | None = None,
        **kwargs,
    ):
        self.rpm = requests_per_minute
        self.burst_size = burst_size
        self.tokens = burst_size
        self.last_refill = time.time()
        self.lock = asyncio.Lock()
        # tokens_per_minute reserved for future token-based limiting

    async def acquire(self):
        """Acquire a token, waiting if necessary"""
        async with self.lock:
            while self.tokens < 1:
                await asyncio.sleep(0.1)
                await self._refill()
            self.tokens -= 1

    async def _refill(self):
        """Refill tokens based on elapsed time"""
        now = time.time()
        elapsed = now - self.last_refill
        tokens_to_add = elapsed * self.rpm / 60
        self.tokens = min(self.burst_size, self.tokens + tokens_to_add)
        self.last_refill = now
