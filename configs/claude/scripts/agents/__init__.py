"""agents — parallel agent orchestration package.

Re-exports all public symbols for convenience imports.
"""

from agents.cli import main
from agents.config import (
    AsyncAnthropic,
    Config,
    HAS_ANTHROPIC,
    HAS_GENAI,
    HAS_GENAI_NEW,
    Logger,
    RateLimiter,
    ServiceConfig,
    genai,
)
from agents.orchestrator import Orchestrator, check_credits
from agents.runners import (
    BaseAgent,
    ClaudeAgent,
    CLIAgent,
    GeminiAgent,
)
from agents.synthesis import SynthesisEngine
from agents.validation import ValidationEngine

__all__ = [
    "Config",
    "ServiceConfig",
    "Logger",
    "RateLimiter",
    "HAS_ANTHROPIC",
    "HAS_GENAI",
    "HAS_GENAI_NEW",
    "AsyncAnthropic",
    "genai",
    "ValidationEngine",
    "SynthesisEngine",
    "BaseAgent",
    "ClaudeAgent",
    "CLIAgent",
    "GeminiAgent",
    "Orchestrator",
    "check_credits",
    "main",
]
