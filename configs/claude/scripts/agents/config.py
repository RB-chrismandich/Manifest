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


# ---------------------------------------------------------------------------
# Config directory resolution
# ---------------------------------------------------------------------------

#: Environment override for the config directory these classes read from.
#: Without it, every path here resolves to the *deployed* ``~/.claude/config``,
#: so editing a YAML in the repo has no effect until ``bootstrap.sh`` copies it
#: out — which makes "I changed the config and nothing happened" a routine and
#: entirely avoidable confusion, and makes tests dependent on ambient home state.
MANIFEST_CONFIG_DIR_ENV = "MANIFEST_CONFIG_DIR"

DEFAULT_CONFIG_DIR = "~/.claude/config"


def resolve_config_path(filename: str, explicit: str | None = None) -> str:
    """Resolve a config file path.

    Precedence: *explicit* argument > ``$MANIFEST_CONFIG_DIR`` > the deployed
    ``~/.claude/config``. The explicit argument wins over the environment on
    purpose — a caller that names a path is being specific, and an env var
    silently overriding it would make tests that pass a fixture path depend on
    the ambient environment, which is the failure mode this override exists to
    remove.
    """
    if explicit is not None:
        return explicit
    base = os.environ.get(MANIFEST_CONFIG_DIR_ENV)
    if base:
        return os.path.join(os.path.expanduser(base), filename)
    return os.path.expanduser(f"{DEFAULT_CONFIG_DIR}/{filename}")


def load_agent_roster(roster_path: str | None = None) -> dict[str, dict]:
    """Load the `agents:` map from agent_roster.yml.

    Returns {} if the file is missing or malformed — callers treat the
    roster as an optional extensibility source, never a hard dependency.
    """
    roster_path = resolve_config_path("agent_roster.yml", roster_path)

    if not os.path.exists(roster_path):
        return {}

    try:
        with open(roster_path) as f:
            data = yaml.safe_load(f) or {}
    except (OSError, yaml.YAMLError):
        return {}

    agents = data.get("agents")
    return agents if isinstance(agents, dict) else {}


def _default_config() -> dict:
    """Default configuration if file doesn't exist.

    CON-004 says data belongs in a data file, and this is the one shape that
    cannot: the function exists precisely for the case where
    `self.config_path` does not exist, so reading a file here would either
    do nothing new (deployed home — same file already checked) or, in a
    repo checkout, silently read `parallel_agent.yml` and make
    `test_defaults_match_repo_yaml` compare that file to itself. A drift
    guard that passes tautologically is worse than the duplication it
    guards, so the literal stays and the test keeps it honest.
    """
    # constitution: exempt C-DATA — the no-file fallback cannot read a file
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
            "devin": {"requests_per_minute": 100, "burst_size": 10},
        },
        "timeouts": {"default": 120, "review": 600},
        # Mirrors parallel_agent.yml model_tiers, which carries the full
        # per-provider rationale and the VERIFIED/UNVERIFIED status of every
        # pin. test_defaults_match_repo_yaml asserts the two are equal, so
        # edit both together or the suite goes red.
        "model_tiers": {
            # VERIFIED 2026-07-29 via `claude --model <id> -p`.
            "claude": {
                "haiku": "claude-haiku-4-5",
                "sonnet": "claude-sonnet-5[1m]",
                "opus": "claude-opus-5[1m]",
            },
            # UNVERIFIED — the gemini CLI is ineligible on this account
            # (free-tier Code Assist discontinued) and no API key is set.
            "gemini": {
                "flash": "gemini-3-flash-preview",
                "pro": "gemini-3-pro-preview",
            },
            # VERIFIED 2026-07-29 via `cursor-agent --model <slug> -p`;
            # replaces the inert all-"auto" placeholder. The premium ladder
            # is usage-limited until 2026-08-12, hence a grok effort ladder.
            "cursor": {
                "mini": "cursor-grok-4.5-low",
                "flash": "cursor-grok-4.5-medium",
                "advanced": "cursor-grok-4.5-high",
            },
            # VERIFIED 2026-08-02 via `codex exec --skip-git-repo-check
            # --model <id>` on a ChatGPT login. GPT-5.6 family (sol/terra/
            # luna); gpt-5.4* retire from ChatGPT-login Codex 2026-08-31.
            "codex": {
                "mini": "gpt-5.6-luna",
                "flash": "gpt-5.6-terra",
                "advanced": "gpt-5.6-sol",
            },
            # VERIFIED 2026-07-29 via `agy --model <slug> --print` (agy
            # 1.1.8). Slugs, not the display labels agy 1.1.1 listed — agy
            # accepts both, but only slugs match today's `agy models`
            # output, which is what model_check.sh greps.
            "antigravity": {
                "mini": "gemini-3.6-flash-low",
                "flash": "gemini-3.6-flash-high",
                "advanced": "claude-opus-4-6-thinking",
            },
            # devin has no tier block on purpose — its catalog is
            # login-gated and cannot be enumerated here, so --devin-model
            # passes through verbatim (see parallel_agent.yml).
        },
        "model_fallback": {
            "mode": "confirm",
            "chains": {
                "codex": ["advanced", "flash", "mini", "auto"],
                "gemini": ["pro", "flash", "auto"],
                "antigravity": ["advanced", "flash", "mini", "auto"],
                "cursor": ["advanced", "flash", "mini", "auto"],
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
                "skill_prompt_transport": "stdin",
                "skill_prompt_args": ["-p"],
                "output": "stdout",
            },
            "gemini": {
                "binary": "gemini",
                "base_args": [],
                "model_args": ["-m", "{model}"],
                "prompt_args": ["-p", "{prompt}"],
                "skill_prompt_transport": "stdin",
                "skill_prompt_args": ["-p", ""],
                "output": "stdout",
            },
            "cursor": {
                "binary": "cursor-agent",
                "base_args": [
                    "--print",
                    "--trust",
                    "--output-format",
                    "text",
                    "--mode",
                    "ask",
                ],
                "model_args": ["--model", "{model}"],
                "prompt_args": ["{prompt}"],
                "skill_prompt_transport": "stdin",
                "skill_prompt_args": [],
                "output": "stdout",
            },
            "codex": {
                "binary": "codex",
                "base_args": [
                    "exec",
                    "--sandbox",
                    "workspace-write",
                    "--color",
                    "never",
                    "--output-last-message",
                    "{output_file}",
                ],
                "model_args": ["--model", "{model}"],
                "skill_prompt_transport": "stdin",
                "skill_prompt_args": ["-"],
                "output": "file_then_stdout",
            },
            "antigravity": {
                "binary": "agy",
                "base_args": [],
                "model_args": ["--model", "{model}"],
                "prompt_args": ["--print", "{prompt}"],
                # agy silently discards piped stdin in --print mode, so the
                # skill path must pass the prompt inline like prompt_args does.
                "skill_prompt_transport": "argv",
                "skill_prompt_args": ["--print", "{prompt}"],
                "output": "stdout",
            },
            # devin: headless via -p/--print; --permission-mode auto
            # auto-approves read-only tools only (mirrors
            # parallel_agent.yml cli_agents.devin).
            "devin": {
                "binary": "devin",
                "base_args": ["--permission-mode", "auto"],
                "model_args": ["--model", "{model}"],
                "prompt_args": ["-p", "{prompt}"],
                "skill_prompt_transport": "file",
                "skill_prompt_args": ["--prompt-file", "{prompt_file}", "--print"],
                "output": "stdout",
            },
        },
        "credit_fallback": {
            "claude": ["opus", "sonnet", "haiku"],
            "cursor": ["advanced", "flash", "mini"],
            "gemini": ["pro", "flash"],
            "codex": ["advanced", "flash", "mini"],
            "antigravity": ["advanced", "flash", "mini"],
            # Empty by design: no known cheaper tiers to fall back to.
            "devin": [],
        },
        "synthesis": {
            "enabled": True,
            "threshold": 0.50,
            "model": "sonnet",
            "timeout": 300,
            "backend": "auto",
            "provider": "auto",
            "provider_order": [
                "antigravity",
                "cursor",
                "gemini",
                "codex",
                "claude",
                "devin",
            ],
        },
        "cddl_invoke": {"provider": "auto"},
        "skillclaw_evolve": {"provider": "auto"},
        "validation": {"consensus_threshold": {"high": 0.80, "medium": 0.50}},
    }


class ConfigError(ValueError):
    """parallel_agent.yml exists but cannot be used.

    Subclasses ValueError so the existing `except (OSError, ValueError)` guards
    around config loading keep working — yaml.YAMLError is already a ValueError
    subclass, so this widens nothing that was not already catchable.
    """


class Config:
    """Configuration manager for parallel agent"""

    def __init__(self, config_path: str | None = None, roster_path: str | None = None):
        self.config_path = resolve_config_path("parallel_agent.yml", config_path)
        self.config = self._load_config()

        # Lazily loaded on first get_cli_agent_spec() miss against cli_agents —
        # None means "not loaded yet", {} means "loaded, empty/missing file".
        self._roster_path = roster_path
        self._roster: dict[str, dict] | None = None

    def _load_config(self) -> dict:
        """Load configuration from YAML, or fail with the file named.

        Three outcomes, split on what the file actually says:
          - absent, or empty/comments-only  -> defaults (it states no intent)
          - valid mapping                   -> used verbatim
          - unparseable, or not a mapping   -> ConfigError

        The last case deliberately does not fall back. Substituting defaults for
        a config the user just edited and typo'd would leave a running system
        quietly ignoring them — the silent-wrong-answer failure CON-007 exists
        to prevent — and the AttributeError it used to cause surfaced far from
        the file that caused it.
        """
        if not os.path.exists(self.config_path):
            return _default_config()

        try:
            with open(self.config_path) as f:
                loaded = yaml.safe_load(f)
        except yaml.YAMLError as err:
            raise ConfigError(f"{self.config_path} is not valid YAML: {err}") from err
        except OSError as err:
            raise ConfigError(f"cannot read {self.config_path}: {err}") from err

        if loaded is None:
            return _default_config()
        if not isinstance(loaded, dict):
            raise ConfigError(
                f"{self.config_path} must contain a mapping, "
                f"got {type(loaded).__name__}"
            )
        return loaded

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
        omits. The roster-driven CLI then supplies selection flags, service
        state, rate limiting, and bounded model-chain wiring without requiring
        a provider-specific Python class.
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
        self.config_path = resolve_config_path("services.yml", config_path)
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
                "devin": {"enabled": False},
            },
            "minimum_agents": 2,
        }

    def is_enabled(self, service_name: str) -> bool:
        """Check if a service is enabled in services.yml.

        A service absent from services.yml falls back to agent_roster.yml's
        `enabled_default`, and only then to True. Without that middle step,
        every machine whose services.yml predates a newly added agent would
        silently ENABLE it — the opt-in agents (devin) would join the panel
        un-asked on exactly the machines that never opted in, and an
        unauthenticated agent returns an error rather than abstaining.
        """
        services = self._data.get("services", {})
        if service_name in services:
            svc = services.get(service_name) or {}
            return bool(svc.get("enabled", True))
        roster_entry = load_agent_roster().get(service_name)
        if isinstance(roster_entry, dict) and "enabled_default" in roster_entry:
            return bool(roster_entry["enabled_default"])
        return True

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
