"""agents — parallel agent orchestration package.

Re-exports all public symbols for convenience imports.
"""

from agents.cli import main
from agents.config import (
    HAS_ANTHROPIC,
    HAS_GENAI,
    HAS_GENAI_NEW,
    AsyncAnthropic,
    Config,
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
    "HAS_ANTHROPIC",
    "HAS_GENAI",
    "HAS_GENAI_NEW",
    "AsyncAnthropic",
    "BaseAgent",
    "CLIAgent",
    "ClaudeAgent",
    "Config",
    "GeminiAgent",
    "Logger",
    "Orchestrator",
    "RateLimiter",
    "ServiceConfig",
    "SynthesisEngine",
    "ValidationEngine",
    "check_credits",
    "genai",
    "main",
]
