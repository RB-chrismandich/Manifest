#!/usr/bin/env python3
"""
Parallel Agent Orchestrator (Python Implementation)

This is a Python rewrite of parallel_agent.sh with improved async handling,
rate limiting, and API client integration.

Usage:
    python parallel_agent.py "Your prompt here"
    python parallel_agent.py --json --validate "Your prompt"
    python parallel_agent.py --review /path/to/file
"""

import asyncio
import json
import os
import sys
import time
import argparse
import logging
import collections
import itertools
from logging.handlers import RotatingFileHandler
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
import re

try:
    import yaml
    from rich.console import Console
    from rich.table import Table
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from rich.live import Live
    from rich.panel import Panel
except ImportError:
    print("Error: Missing dependencies. Install with: pip install -r requirements.txt")
    sys.exit(1)

# Optional imports (graceful degradation)
try:
    from anthropic import AsyncAnthropic

    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

# Try new google.genai package first, fallback to legacy google-generativeai
try:
    import google.genai as genai_new

    HAS_GENAI_NEW = True
    HAS_GENAI = True
except ImportError:
    HAS_GENAI_NEW = False
    try:
        from google import genai as genai_legacy

        HAS_GENAI = True
    except ImportError:
        HAS_GENAI = False

# Unified interface
if HAS_GENAI_NEW:
    genai = genai_new
elif HAS_GENAI:
    genai = genai_legacy
else:
    genai = None


class Config:
    """Configuration manager for parallel agent"""

    def __init__(self, config_path: Optional[str] = None):
        if config_path is None:
            config_path = os.path.expanduser("~/.claude/config/parallel_agent.yml")

        self.config_path = config_path
        self.config = self._load_config()

    def _load_config(self) -> Dict:
        """Load configuration from YAML file"""
        if not os.path.exists(self.config_path):
            return self._default_config()

        with open(self.config_path, "r") as f:
            return yaml.safe_load(f)

    def _default_config(self) -> Dict:
        """Default configuration if file doesn't exist"""
        return {
            "rate_limits": {
                "claude": {"requests_per_minute": 60, "burst_size": 5},
                "gemini": {"requests_per_minute": 30, "burst_size": 3},
                "cursor": {"requests_per_minute": 100, "burst_size": 10},
                "codex": {"requests_per_minute": 100, "burst_size": 10},
            },
            "timeouts": {"default": 120, "review": 600},
            "model_tiers": {
                "claude": {
                    "haiku": "claude-haiku-4-5-20251001",
                    "sonnet": "claude-sonnet-4-5-20250929",
                    "opus": "claude-opus-4-6",
                },
                "gemini": {
                    "flash": "gemini-3-flash-preview",
                    "pro": "gemini-3-pro-preview",
                },
                "codex": {
                    "mini": "o4-mini",
                    "flash": "o3",
                    "advanced": "o3-pro",
                },
            },
            "credit_fallback": {
                "claude": ["opus", "sonnet", "haiku"],
                "cursor": ["advanced", "flash", "mini"],
                "gemini": ["pro", "flash"],
                "codex": ["advanced", "flash", "mini"],
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


class ServiceConfig:
    """Service configuration manager reading from services.yml"""

    def __init__(self, config_path: Optional[str] = None):
        if config_path is None:
            config_path = os.path.expanduser("~/.claude/config/services.yml")
        self.config_path = config_path
        self._data = self._load()

    def _load(self) -> Dict:
        """Load services.yml or return all-enabled defaults."""
        if os.path.exists(self.config_path):
            with open(self.config_path, "r") as f:
                data = yaml.safe_load(f) or {}
                return data
        # All-enabled defaults when file is missing
        return {
            "services": {
                "claude": {"enabled": True},
                "gemini": {"enabled": True},
                "cursor": {"enabled": True},
                "codex": {"enabled": True},
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

    def check_minimum_agents(self, count: int) -> Optional[str]:
        """Return a warning message if count < minimum, else None."""
        minimum = self.minimum_agents
        if count < minimum:
            return (
                f"Warning: Only {count} agent(s) enabled, "
                f"minimum recommended is {minimum}. "
                f"Parallel orchestration may produce lower-confidence results."
            )
        return None


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


class RateLimiter:
    """Token bucket rate limiter with adaptive backoff"""

    def __init__(
        self,
        requests_per_minute: int = 60,
        burst_size: int = 5,
        tokens_per_minute: int = None,
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


class ValidationEngine:
    """Validates agent outputs against tiered criteria"""

    def __init__(self, config: Config, logger: Optional["Logger"] = None):
        self.config = config
        self.logger = logger
        self.criteria = self._load_criteria()

    def _load_criteria(self) -> Dict:
        """Load validation criteria from YAML file"""
        criteria_path = Path("~/.claude/config/validation_criteria.yml").expanduser()
        if not criteria_path.exists():
            if self.logger:
                self.logger.warning(
                    f"Validation criteria file not found: {criteria_path}"
                )
            return {}

        with open(criteria_path, "r") as f:
            return yaml.safe_load(f)

    def validate(
        self,
        agent_results: Dict,
        consensus: Dict,
        mode: str,
        command: Optional[str] = None,
    ) -> Dict:
        """Validate results against tier1 and tier2 criteria"""
        # Get command-specific overrides
        overrides = {}
        if command and "command_overrides" in self.criteria:
            overrides = self.criteria["command_overrides"].get(command, {})

        # Tier 1 validation (critical)
        tier1_result = self._validate_tier1(agent_results, consensus, overrides)

        # Tier 2 validation (quality)
        tier2_result = self._validate_tier2(agent_results, overrides)

        # Compute overall verdict
        verdict = self._compute_verdict(tier1_result, tier2_result, overrides)

        return {
            "tier1": tier1_result,
            "tier2": tier2_result,
            "verdict": verdict,
            "command_overrides_applied": bool(overrides),
        }

    def _validate_tier1(
        self, agent_results: Dict, consensus: Dict, overrides: Dict
    ) -> Dict:
        """Validate Tier 1 (critical) criteria"""
        criteria = self.criteria.get("tier1", {})
        checks = {}
        failures = []
        total_weight = 0
        score = 0

        # Cross-verification check
        if criteria.get("cross_verification", {}).get("enabled", True):
            weight = criteria["cross_verification"]["weight"]
            threshold = criteria["cross_verification"].get("threshold", 0.80)
            consensus_score = consensus.get("consensus_score", 0) / 100.0

            passed = consensus_score >= threshold
            checks["cross_verification"] = {
                "passed": passed,
                "score": consensus_score,
                "threshold": threshold,
                "weight": weight,
            }

            total_weight += weight
            if passed:
                score += weight
            else:
                failures.append(
                    f"Cross-verification below threshold: {consensus_score:.2f} < {threshold}"
                )

        # Security checks
        if "security" in criteria:
            weight = criteria["security"]["weight"]
            security_result = self._check_security(agent_results, criteria["security"])
            checks["security"] = security_result
            checks["security"]["weight"] = weight

            total_weight += weight
            if security_result["passed"]:
                score += weight
            else:
                failures.extend(security_result.get("issues", []))

        # Error handling checks
        if "error_handling" in criteria:
            weight = criteria["error_handling"]["weight"]
            error_result = self._check_error_handling(
                agent_results, criteria["error_handling"]
            )
            checks["error_handling"] = error_result
            checks["error_handling"]["weight"] = weight

            total_weight += weight
            if error_result["passed"]:
                score += weight
            else:
                failures.extend(error_result.get("issues", []))

        # Breaking changes checks
        if "breaking_changes" in criteria:
            weight = criteria["breaking_changes"]["weight"]
            breaking_result = self._check_breaking_changes(
                agent_results, criteria["breaking_changes"]
            )
            checks["breaking_changes"] = breaking_result
            checks["breaking_changes"]["weight"] = weight

            total_weight += weight
            if breaking_result["passed"]:
                score += weight
            else:
                failures.extend(breaking_result.get("issues", []))

        # Overall tier1 pass/fail
        passed = len(failures) == 0
        final_score = score / total_weight if total_weight > 0 else 0

        return {
            "passed": passed,
            "score": final_score,
            "checks": checks,
            "failures": failures,
        }

    def _check_security(self, agent_results: Dict, security_criteria: Dict) -> Dict:
        """Check for security issues"""
        issues = []
        _keywords = security_criteria.get("keywords", [])

        for agent_name, result in agent_results.items():
            if result.get("status") != "complete":
                continue

            output = result.get("output", "").lower()

            # Check for hardcoded secrets
            secret_patterns = [
                r'api[_-]?key\s*=\s*["\'][^"\']+["\']',
                r'password\s*=\s*["\'][^"\']+["\']',
                r'secret\s*=\s*["\'][^"\']+["\']',
                r'token\s*=\s*["\'][^"\']+["\']',
            ]

            for pattern in secret_patterns:
                if re.search(pattern, output, re.IGNORECASE):
                    issues.append(f"[{agent_name}] Potential hardcoded secret detected")
                    break

            # Check for SQL injection patterns
            sql_patterns = [r'execute\s*\(\s*["\'].*\+', r'query\s*\(\s*["\'].*\+']
            for pattern in sql_patterns:
                if re.search(pattern, output, re.IGNORECASE):
                    issues.append(
                        f"[{agent_name}] Potential SQL injection vulnerability"
                    )
                    break

            # Check for command injection patterns
            cmd_patterns = [
                r"exec\s*\(.*user.*\)",
                r"system\s*\(.*input.*\)",
                r"shell_exec",
            ]
            for pattern in cmd_patterns:
                if re.search(pattern, output, re.IGNORECASE):
                    issues.append(
                        f"[{agent_name}] Potential command injection vulnerability"
                    )
                    break

        return {"passed": len(issues) == 0, "issues": issues}

    def _check_error_handling(self, agent_results: Dict, error_criteria: Dict) -> Dict:
        """Check for proper error handling"""
        issues = []

        for agent_name, result in agent_results.items():
            if result.get("status") != "complete":
                continue

            output = result.get("output", "").lower()

            # Check for silent failures
            if "pass" in output and "except" in output and "logging" not in output:
                issues.append(f"[{agent_name}] Potential silent failure detected")

            # Check for bare except clauses
            if re.search(r"except\s*:", output):
                issues.append(f"[{agent_name}] Bare except clause detected")

        return {"passed": len(issues) == 0, "issues": issues}

    def _check_breaking_changes(
        self, agent_results: Dict, breaking_criteria: Dict
    ) -> Dict:
        """Check for breaking changes"""
        issues = []

        for agent_name, result in agent_results.items():
            if result.get("status") != "complete":
                continue

            output = result.get("output", "").lower()

            # Check for removed/renamed functions without deprecation
            if (
                "removed" in output or "renamed" in output
            ) and "deprecated" not in output:
                issues.append(
                    f"[{agent_name}] Potential breaking change without deprecation warning"
                )

        return {"passed": len(issues) == 0, "issues": issues}

    def _validate_tier2(self, agent_results: Dict, overrides: Dict) -> Dict:
        """Validate Tier 2 (quality) criteria"""
        criteria = self.criteria.get("tier2", {})
        checks = {}
        concerns = []
        total_weight = 0
        score = 0

        # Bug detection
        if "bug_detection" in criteria:
            weight = criteria["bug_detection"]["weight"]
            bug_result = self._check_bugs(agent_results, criteria["bug_detection"])
            checks["bug_detection"] = bug_result
            checks["bug_detection"]["weight"] = weight

            total_weight += weight
            score += weight * bug_result["score"]
            concerns.extend(bug_result.get("concerns", []))

        # Performance
        if "performance" in criteria:
            weight = criteria["performance"]["weight"]
            perf_result = self._check_performance(
                agent_results, criteria["performance"]
            )
            checks["performance"] = perf_result
            checks["performance"]["weight"] = weight

            total_weight += weight
            score += weight * perf_result["score"]
            concerns.extend(perf_result.get("concerns", []))

        # Maintainability
        if "maintainability" in criteria:
            weight = criteria["maintainability"]["weight"]
            maint_result = self._check_maintainability(
                agent_results, criteria["maintainability"]
            )
            checks["maintainability"] = maint_result
            checks["maintainability"]["weight"] = weight

            total_weight += weight
            score += weight * maint_result["score"]
            concerns.extend(maint_result.get("concerns", []))

        # Test coverage
        if "test_coverage" in criteria:
            weight = criteria["test_coverage"]["weight"]
            test_result = self._check_test_coverage(
                agent_results, criteria["test_coverage"]
            )
            checks["test_coverage"] = test_result
            checks["test_coverage"]["weight"] = weight

            total_weight += weight
            score += weight * test_result["score"]
            concerns.extend(test_result.get("concerns", []))

        final_score = score / total_weight if total_weight > 0 else 0

        return {"score": final_score, "checks": checks, "concerns": concerns}

    def _check_bugs(self, agent_results: Dict, bug_criteria: Dict) -> Dict:
        """Check for common bug patterns"""
        concerns = []
        _patterns = bug_criteria.get("patterns", [])

        for agent_name, result in agent_results.items():
            if result.get("status") != "complete":
                continue

            output = result.get("output", "")

            # Check for null reference issues
            if "null" in output.lower() or "undefined" in output.lower():
                concerns.append(f"[{agent_name}] Potential null/undefined reference")

            # Check for race conditions
            if "race" in output.lower() or "concurrent" in output.lower():
                concerns.append(f"[{agent_name}] Potential race condition mentioned")

        # Score inversely proportional to concerns
        score = max(0, 1.0 - (len(concerns) * 0.2))

        return {"score": score, "concerns": concerns}

    def _check_performance(self, agent_results: Dict, perf_criteria: Dict) -> Dict:
        """Check for performance anti-patterns"""
        concerns = []

        for agent_name, result in agent_results.items():
            if result.get("status") != "complete":
                continue

            output = result.get("output", "").lower()

            # Check for O(n²) complexity mentions
            if "o(n" in output and ("²" in output or "^2" in output or "n)" in output):
                concerns.append(
                    f"[{agent_name}] Quadratic or worse complexity detected"
                )

            # Check for N+1 patterns
            if "n+1" in output or ("query" in output and "loop" in output):
                concerns.append(f"[{agent_name}] Potential N+1 query pattern")

        score = max(0, 1.0 - (len(concerns) * 0.25))

        return {"score": score, "concerns": concerns}

    def _check_maintainability(self, agent_results: Dict, maint_criteria: Dict) -> Dict:
        """Check for maintainability issues"""
        concerns = []

        for agent_name, result in agent_results.items():
            if result.get("status") != "complete":
                continue

            output = result.get("output", "").lower()

            # Check for complexity mentions
            if "complex" in output or "complicated" in output:
                concerns.append(f"[{agent_name}] Complexity concerns noted")

            # Check for unclear naming
            if "unclear" in output or "confusing" in output:
                concerns.append(f"[{agent_name}] Naming or structure concerns")

        score = max(0, 1.0 - (len(concerns) * 0.2))

        return {"score": score, "concerns": concerns}

    def _check_test_coverage(self, agent_results: Dict, test_criteria: Dict) -> Dict:
        """Check for test coverage"""
        concerns = []

        for agent_name, result in agent_results.items():
            if result.get("status") != "complete":
                continue

            output = result.get("output", "").lower()

            # Check for missing tests mentions
            if "no test" in output or "missing test" in output:
                concerns.append(f"[{agent_name}] Missing test coverage noted")

            # Check for untested edge cases
            if "edge case" in output and "test" in output:
                concerns.append(f"[{agent_name}] Edge case test coverage concerns")

        score = max(0, 1.0 - (len(concerns) * 0.3))

        return {"score": score, "concerns": concerns}

    def _compute_verdict(
        self, tier1_result: Dict, tier2_result: Dict, overrides: Dict
    ) -> str:
        """Compute overall validation verdict"""
        scoring_config = self.criteria.get("scoring", {})

        # Get thresholds
        tier2_threshold = overrides.get(
            "tier2_threshold", scoring_config.get("tier2_acceptable_threshold", 0.60)
        )

        # Determine verdict
        if not tier1_result["passed"]:
            return "BLOCKED"
        elif tier2_result["score"] >= tier2_threshold:
            return "APPROVED"
        else:
            return "NEEDS_REVIEW"


class SynthesisEngine:
    """Handles synthesis when agents disagree"""

    def __init__(self, config: Config, logger: Optional["Logger"] = None):
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
                f"model_tiers.claude.{model}", "claude-sonnet-4-5-20250929"
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


class BaseAgent:
    """Abstract base class for all agents"""

    def __init__(
        self,
        name: str,
        model: str,
        timeout: int,
        rate_limiter: RateLimiter,
        config: Config = None,
        logger: Optional[Logger] = None,
        streaming: bool = False,
        progress_callback=None,
    ):
        self.name = name
        self.model = model
        self.original_model = model  # Track original for fallback
        self.timeout = timeout
        self.rate_limiter = rate_limiter
        self.config = config or Config()
        self.logger = logger
        self.credit_fallback_used = False
        self.streaming = streaming
        self.progress_callback = progress_callback

    async def execute(self, prompt: str, mode: str = "prompt") -> Dict:
        """Execute agent with rate limiting, timeout, and credit fallback"""
        await self.rate_limiter.acquire()

        start_time = time.time()

        if self.logger:
            self.logger.info(
                f"[{self.name}] Starting execution with model {self.model}"
            )

        # Try with original model first, then fallback on credit exhaustion
        for attempt in range(3):  # Max 3 fallback attempts
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

            except asyncio.TimeoutError:
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
                        self.credit_fallback_used = True
                        await asyncio.sleep(1)  # Brief delay before retry
                        continue

                # Non-recoverable error
                if self.logger:
                    self.logger.error(f"[{self.name}] Error: {str(e)}")

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

    def _get_fallback_model(self) -> Optional[str]:
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

    async def _execute_impl(self, prompt: str, mode: str) -> Dict:
        """Implementation-specific execution logic"""
        raise NotImplementedError


class ClaudeAgent(BaseAgent):
    """Claude agent using official Anthropic SDK (API key only for now)"""

    def __init__(
        self,
        model: str = "sonnet",
        timeout: int = 120,
        rate_limiter: RateLimiter = None,
        config: Config = None,
        logger: Optional[Logger] = None,
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

    def _create_client(self) -> AsyncAnthropic:
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

    async def _execute_impl(self, prompt: str, mode: str) -> Dict:
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

    async def _execute_streaming(self, prompt: str, mode: str) -> Dict:
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


class GeminiAgent(BaseAgent):
    """Gemini agent using official Google SDK with OAuth support"""

    def __init__(
        self,
        model: str = "flash",
        timeout: int = 120,
        rate_limiter: RateLimiter = None,
        config: Config = None,
        logger: Optional[Logger] = None,
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
                    print("  [gemini] Run: gemini auth login", file=sys.stderr)
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
                        "  [gemini] Run: gemini auth login or set GOOGLE_API_KEY",
                        file=sys.stderr,
                    )
                    raise
            return genai

    def _resolve_model(self, tier: str) -> str:
        """Resolve model tier to full model name"""
        return self.config.get(f"model_tiers.gemini.{tier}", tier)

    async def _execute_impl(self, prompt: str, mode: str) -> Dict:
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

    async def _execute_streaming(self, prompt: str, mode: str) -> Dict:
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


class CursorAgent(BaseAgent):
    """Cursor agent using subprocess (shell out to cursor CLI)"""

    def __init__(
        self,
        model: str = "flash",
        timeout: int = 120,
        rate_limiter: RateLimiter = None,
        config: Config = None,
        logger: Optional[Logger] = None,
        streaming: bool = False,
        progress_callback=None,
    ):
        config = config or Config()
        super().__init__(
            "cursor",
            model,
            timeout,
            rate_limiter,
            config,
            logger,
            streaming,
            progress_callback,
        )
        self.model_name = model

    async def _execute_impl(self, prompt: str, mode: str) -> Dict:
        """Execute cursor CLI via subprocess"""
        # Check if cursor command exists
        if not self._check_cursor_available():
            return {
                "status": "missing",
                "error": "cursor command not found",
                "output": "",
            }

        # Shell out to cursor CLI (use exec to prevent command injection)
        proc = await asyncio.create_subprocess_exec(
            "cursor",
            "--model",
            self.model_name,
            prompt,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await proc.communicate()

        if proc.returncode == 0:
            return {
                "status": "complete",
                "output": stdout.decode("utf-8", errors="ignore"),
                "model": self.model_name,
                "validated": False,
            }
        else:
            return {
                "status": "failed",
                "error": stderr.decode("utf-8", errors="ignore"),
                "output": "",
            }

    def _check_cursor_available(self) -> bool:
        """Check if cursor CLI is available"""
        import shutil

        return shutil.which("cursor") is not None


class CodexAgent(BaseAgent):
    """Codex agent using subprocess (shell out to codex CLI)"""

    def __init__(
        self,
        model: str = "flash",
        timeout: int = 120,
        rate_limiter: RateLimiter = None,
        config: Config = None,
        logger: Optional[Logger] = None,
        streaming: bool = False,
        progress_callback=None,
    ):
        config = config or Config()
        super().__init__(
            "codex",
            model,
            timeout,
            rate_limiter,
            config,
            logger,
            streaming,
            progress_callback,
        )
        self.model_name = self._resolve_model(model)

    def _resolve_model(self, tier: str) -> Optional[str]:
        """Resolve model tier to full model name. Returns None for 'auto'."""
        if tier == "auto":
            return None
        resolved = self.config.get(f"model_tiers.codex.{tier}")
        return resolved if resolved else tier

    async def _execute_impl(self, prompt: str, mode: str) -> Dict:
        """Execute codex CLI via subprocess"""
        import shutil
        import tempfile

        if not shutil.which("codex"):
            return {
                "status": "missing",
                "error": "codex command not found",
                "output": "",
            }

        # Create temp file for --output-last-message
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, prefix="codex_out_"
        ) as tmp:
            output_file = tmp.name

        try:
            cmd = [
                "codex",
                "exec",
                "--full-auto",
                "--color",
                "never",
                "--output-last-message",
                output_file,
            ]

            if self.model_name:
                cmd.extend(["--model", self.model_name])

            cmd.append(prompt)

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await proc.communicate()

            # Output priority: file > stdout > stderr
            output = ""
            if os.path.exists(output_file):
                with open(output_file, "r") as f:
                    output = f.read().strip()

            if not output:
                output = stdout.decode("utf-8", errors="ignore").strip()

            if not output and proc.returncode != 0:
                return {
                    "status": "failed",
                    "error": stderr.decode("utf-8", errors="ignore"),
                    "output": "",
                    "model": self.model_name or "auto",
                }

            return {
                "status": "complete",
                "output": output,
                "model": self.model_name or "auto",
                "validated": False,
            }
        finally:
            # Cleanup temp file
            try:
                os.unlink(output_file)
            except OSError:
                pass


class Orchestrator:
    """Main orchestrator for parallel agent execution"""

    def __init__(
        self,
        agents: List[BaseAgent],
        config: Config,
        validate: bool = False,
        logger: Optional[Logger] = None,
        enable_synthesis: bool = True,
        streaming: bool = True,
    ):
        self.agents = agents
        self.config = config
        self.validate = validate
        self.logger = logger
        self.enable_synthesis = enable_synthesis
        self.streaming = streaming
        self.console = Console()

    async def execute(
        self, prompt: str, mode: str = "prompt", command: Optional[str] = None
    ) -> Dict:
        """Run all agents concurrently and synthesize results"""
        start_time = time.time()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        if self.logger:
            self.logger.info(
                f"Starting orchestration: mode={mode}, agents={len(self.agents)}"
            )

        # Run agents in parallel (with or without streaming)
        if self.streaming and all(
            hasattr(agent, "_execute_streaming") for agent in self.agents
        ):
            agent_results = await self._execute_with_streaming(prompt, mode, timestamp)
        else:
            agent_results = await self._execute_without_streaming(prompt, mode)

        # Calculate consensus
        consensus = self._calculate_consensus(agent_results)

        if self.logger:
            self.logger.info(f"Consensus score: {consensus['consensus_score']}%")

        # Synthesis (if needed and enabled)
        synthesis_result = None
        if self.enable_synthesis and self.config.get("synthesis.enabled", True):
            synthesizer = SynthesisEngine(self.config, self.logger)
            synthesis_result = await synthesizer.synthesize(
                prompt, agent_results, consensus
            )
            if synthesis_result and synthesis_result.get("triggered"):
                consensus["synthesis"] = synthesis_result
                if self.logger:
                    self.logger.info("Synthesis completed")

        # Validation (if requested)
        validation_result = None
        if self.validate:
            validation_result = self._validate_results(
                agent_results, consensus, mode, command
            )
            if self.logger:
                self.logger.info(f"Validation verdict: {validation_result['verdict']}")

        total_duration = round(time.time() - start_time, 2)
        minutes, seconds = divmod(int(total_duration), 60)
        duration_formatted = f"{minutes}m{seconds:02d}s" if minutes else f"{seconds}s"

        result = {
            "timestamp": timestamp,
            "mode": mode,
            "prompt": prompt,
            "duration_seconds": total_duration,
            "duration_formatted": duration_formatted,
            "agents": agent_results,
            "cross_verification": consensus,
            "validation": validation_result,
            "output_files": {},
        }

        # Write output files
        output_files = await self._write_output_files(result, timestamp)
        result["output_files"] = output_files

        # Log performance metrics
        if self.logger:
            self._log_performance_metrics(result, start_time)

        return result

    async def _execute_without_streaming(self, prompt: str, mode: str) -> Dict:
        """Execute agents without streaming (legacy mode)"""
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=self.console,
        ) as progress:
            _task = progress.add_task(
                f"Running {len(self.agents)} agents...", total=None
            )

            results = await asyncio.gather(
                *[agent.execute(prompt, mode) for agent in self.agents],
                return_exceptions=True,
            )

        # Build results dictionary
        agent_results = {}
        for agent, result in zip(self.agents, results):
            if isinstance(result, Exception):
                agent_results[agent.name] = {
                    "status": "failed",
                    "error": str(result),
                    "output": "",
                }
            else:
                agent_results[agent.name] = result

        return agent_results

    async def _execute_with_streaming(
        self, prompt: str, mode: str, timestamp: str
    ) -> Dict:
        """Execute agents with live streaming display"""
        agent_panels = {agent.name: "" for agent in self.agents}

        async def update_callback(agent_name: str, partial_output: str):
            """Update streaming display"""
            max_display_chars = self.config.get("streaming.max_display_chars", 500)
            agent_panels[agent_name] = partial_output[:max_display_chars]

        # Set progress callback for all agents
        for agent in self.agents:
            agent.progress_callback = update_callback

        # Create live display
        try:
            with Live(
                self._build_streaming_layout(agent_panels),
                refresh_per_second=self.config.get("streaming.refresh_rate", 4),
                console=self.console,
            ) as live:
                # Run agents in parallel
                results = await asyncio.gather(
                    *[agent.execute(prompt, mode) for agent in self.agents],
                    return_exceptions=True,
                )

                # Final update
                live.update(self._build_streaming_layout(agent_panels))

        except Exception as e:
            if self.logger:
                self.logger.warning(
                    f"Streaming display failed: {e}, falling back to non-streaming"
                )
            # Fallback to non-streaming
            return await self._execute_without_streaming(prompt, mode)

        # Build results dictionary
        agent_results = {}
        for agent, result in zip(self.agents, results):
            if isinstance(result, Exception):
                agent_results[agent.name] = {
                    "status": "failed",
                    "error": str(result),
                    "output": "",
                }
            else:
                agent_results[agent.name] = result

        return agent_results

    def _build_streaming_layout(self, agent_panels: Dict[str, str]) -> Panel:
        """Build rich panel layout for streaming display"""
        panel_text = ""
        for agent_name, output in agent_panels.items():
            status = "🔄" if output else "⏳"
            panel_text += f"\n[bold cyan]{status} {agent_name.title()}:[/bold cyan]\n"
            if output:
                panel_text += f"{output[:500]}{'...' if len(output) > 500 else ''}\n"
            else:
                panel_text += "[dim]Waiting for response...[/dim]\n"

        return Panel(panel_text, title="Parallel Agent Execution", border_style="blue")

    def _log_performance_metrics(self, result: Dict, start_time: float):
        """Log performance metrics"""
        if not self.logger:
            return

        total_duration = time.time() - start_time
        consensus_score = result["cross_verification"].get("consensus_score", 0)

        self.logger.info(f"Total duration: {total_duration:.2f}s")
        self.logger.info(f"Consensus: {consensus_score}%")

        for agent_name, agent_result in result["agents"].items():
            duration = agent_result.get("duration_seconds", 0)
            status = agent_result.get("status", "unknown")
            credit_fallback = agent_result.get("credit_fallback", False)

            self.logger.info(
                f"[{agent_name}] status={status}, duration={duration}s, "
                f"credit_fallback={credit_fallback}"
            )

    def _calculate_consensus(self, results: Dict) -> Dict:
        """Calculate cross-verification consensus score"""
        outputs = [
            r.get("output", "")
            for r in results.values()
            if r.get("status") == "complete"
        ]

        if len(outputs) < 2:
            return {
                "consensus_score": 0,
                "confidence": "low",
                "agent_count": len(outputs),
            }

        # Simple keyword-based consensus (placeholder for more sophisticated analysis)
        # Count common significant words (>4 chars) across outputs

        # Performance optimization: use collections.Counter and itertools.chain
        # to offload iterative counting logic to optimized C-backend.
        word_sets = [{word.lower() for word in output.split() if len(word) > 4} for output in outputs]
        all_words = set().union(*word_sets) if word_sets else set()
        word_counts = collections.Counter(itertools.chain.from_iterable(word_sets))

        # Calculate consensus as % of words appearing in multiple outputs
        if not all_words:
            consensus_score = 0
        else:
            common_words = sum(1 for count in word_counts.values() if count > 1)
            consensus_score = int((common_words / len(all_words)) * 100)

        # Determine confidence level
        thresholds = self.config.get("validation.consensus_threshold", {})
        if consensus_score >= thresholds.get("high", 80):
            confidence = "high"
        elif consensus_score >= thresholds.get("medium", 50):
            confidence = "medium"
        else:
            confidence = "low"

        return {
            "consensus_score": consensus_score,
            "confidence": confidence,
            "agent_count": len(outputs),
        }

    def _validate_results(
        self, results: Dict, consensus: Dict, mode: str, command: Optional[str] = None
    ) -> Dict:
        """Validate results against success criteria"""
        validator = ValidationEngine(self.config, self.logger)
        return validator.validate(results, consensus, mode, command)

    def _resolve_output_dir(self, custom_output_dir: Optional[str] = None) -> Path:
        """Resolve output directory with sandbox-aware fallback.

        Tries directories in order:
        1. custom_output_dir (if provided via --output)
        2. ~/.claude/.agent_outputs (default from config)
        3. /tmp/.claude_agent_outputs_{pid} (fallback on permission error)
        """
        if custom_output_dir:
            return Path(custom_output_dir).expanduser()

        default_dir = Path(
            self.config.get("output.directory", "~/.claude/.agent_outputs")
        ).expanduser()

        try:
            default_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            return default_dir
        except (OSError, PermissionError) as e:
            fallback = Path(f"/tmp/.claude_agent_outputs_{os.getpid()}")
            if self.logger:
                self.logger.warning(
                    f"Cannot write to {default_dir}: {e}. "
                    f"Falling back to {fallback}"
                )
            print(
                f"  Warning: Cannot write to {default_dir}, "
                f"using fallback: {fallback}",
                file=sys.stderr,
            )
            return fallback

    async def _write_output_files(
        self,
        result: Dict,
        timestamp: str,
        custom_output_dir: Optional[str] = None,
        full_output: bool = True,
    ) -> Dict:
        """Write output files to disk with sandbox-aware fallback"""
        output_dir = self._resolve_output_dir(custom_output_dir)
        output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)

        output_files = {}

        # Write individual agent outputs
        for agent_name, agent_result in result["agents"].items():
            output_file = output_dir / f"{agent_name}_{timestamp}.txt"
            with open(output_file, "w") as f:
                f.write(f"Agent: {agent_name}\n")
                f.write(f"Status: {agent_result.get('status')}\n")
                f.write(f"Model: {agent_result.get('model', 'N/A')}\n")
                f.write(f"Duration: {agent_result.get('duration_seconds')}s\n")
                if agent_result.get("credit_fallback"):
                    f.write("Credit Fallback: Yes\n")
                f.write("\n--- Output ---\n\n")

                output_text = agent_result.get("output", agent_result.get("error", ""))
                if full_output:
                    f.write(output_text)
                else:
                    # Truncate to first 1000 chars if not full output
                    f.write(output_text[:1000])
                    if len(output_text) > 1000:
                        f.write("\n\n... [truncated] ...")

            output_files[agent_name] = str(output_file)

        # Write JSON results
        json_file = output_dir / f"results_{timestamp}.json"
        with open(json_file, "w") as f:
            json.dump(result, f, indent=2)
        output_files["json"] = str(json_file)

        # Write markdown summary
        md_file = output_dir / f"summary_{timestamp}.md"
        with open(md_file, "w") as f:
            f.write("# Parallel Agent Results\n\n")
            f.write(f"**Timestamp**: {timestamp}\n")
            f.write(f"**Mode**: {result['mode']}\n")
            f.write(f"**Prompt**: {result['prompt']}\n\n")

            f.write("## Cross-Verification\n\n")
            consensus = result["cross_verification"]
            f.write(f"- **Consensus Score**: {consensus['consensus_score']}%\n")
            f.write(f"- **Confidence**: {consensus['confidence'].upper()}\n")
            f.write(f"- **Agent Count**: {consensus['agent_count']}\n\n")

            if result.get("validation"):
                f.write("## Validation\n\n")
                f.write(f"- **Verdict**: {result['validation']['verdict']}\n\n")

            f.write("## Agent Results\n\n")
            for agent_name, agent_result in result["agents"].items():
                status_icon = "✓" if agent_result.get("status") == "complete" else "✗"
                f.write(f"### {status_icon} {agent_name.title()}\n\n")
                f.write(f"- **Status**: {agent_result.get('status')}\n")
                f.write(f"- **Model**: {agent_result.get('model', 'N/A')}\n")
                f.write(f"- **Duration**: {agent_result.get('duration_seconds')}s\n")
                if agent_result.get("credit_fallback"):
                    f.write("- **Credit Fallback**: Used\n")
                if agent_result.get("error"):
                    f.write(f"- **Error**: {agent_result['error']}\n")
                f.write("\n")

        output_files["summary"] = str(md_file)

        return output_files

    def print_results(self, result: Dict, json_output: bool = False):
        """Print results in table or JSON format"""
        if json_output:
            print(json.dumps(result, indent=2))
        else:
            self._print_table(result)
            self._print_summary(result)

    def _print_table(self, result: Dict):
        """Print results as formatted table"""
        table = Table(title="Parallel Agent Results")
        table.add_column("Agent", style="cyan")
        table.add_column("Status", style="green")
        table.add_column("Time", justify="right", style="yellow")
        table.add_column("Model", style="blue")

        for agent_name, agent_result in result["agents"].items():
            status = agent_result.get("status", "unknown")
            duration = f"{agent_result.get('duration_seconds', 0):.2f}s"
            model = agent_result.get("model", "N/A")

            status_icon = "✔" if status == "complete" else "✗"
            table.add_row(
                agent_name.title(), f"{status_icon} {status}", duration, model
            )

        self.console.print(table)

    def _print_summary(self, result: Dict):
        """Print consensus summary"""
        consensus = result["cross_verification"]
        self.console.print(
            f"\n[bold]Consensus:[/bold] {consensus['consensus_score']}% ({consensus['confidence'].upper()})"
        )
        self.console.print(f"[bold]Agents:[/bold] {consensus['agent_count']}")

        if result.get("validation"):
            verdict = result["validation"]["verdict"]
            color = "green" if verdict == "APPROVED" else "red"
            self.console.print(f"[bold]Validation:[/bold] [{color}]{verdict}[/{color}]")


async def check_credits(config: Config, logger: Optional[Logger] = None) -> Dict:
    """Pre-flight credit check with minimal API calls"""
    results = {}

    # Claude credit check
    if HAS_ANTHROPIC:
        try:
            api_key = os.environ.get("ANTHROPIC_API_KEY")
            if api_key:
                client = AsyncAnthropic(api_key=api_key)
                # Make minimal call (haiku, 10 tokens)
                await asyncio.wait_for(
                    client.messages.create(
                        model="claude-haiku-4-5-20251001",
                        max_tokens=10,
                        messages=[{"role": "user", "content": "test"}],
                    ),
                    timeout=10,
                )
                results["claude"] = {"status": "available"}
            else:
                results["claude"] = {"status": "no_api_key"}
        except Exception as e:
            error_str = str(e).lower()
            if "quota" in error_str or "credit" in error_str:
                results["claude"] = {"status": "quota_exceeded", "error": str(e)}
            else:
                results["claude"] = {"status": "error", "error": str(e)}
    else:
        results["claude"] = {"status": "not_installed"}

    # Gemini credit check
    if HAS_GENAI:
        try:
            api_key = os.environ.get("GOOGLE_API_KEY")
            if HAS_GENAI_NEW:
                client = genai.Client(api_key=api_key) if api_key else genai.Client()
                await asyncio.wait_for(
                    asyncio.to_thread(
                        client.models.generate_content,
                        model="gemini-3-flash-preview",
                        contents="test",
                    ),
                    timeout=10,
                )
            else:
                if api_key:
                    genai.configure(api_key=api_key)
                model = genai.GenerativeModel("gemini-3-flash-preview")
                await asyncio.wait_for(
                    asyncio.to_thread(model.generate_content, "test"), timeout=10
                )
            results["gemini"] = {"status": "available"}
        except Exception as e:
            error_str = str(e).lower()
            if "quota" in error_str or "resource_exhausted" in error_str:
                results["gemini"] = {"status": "quota_exceeded", "error": str(e)}
            else:
                results["gemini"] = {"status": "error", "error": str(e)}
    else:
        results["gemini"] = {"status": "not_installed"}

    # Cursor (no API to check, assume available)
    results["cursor"] = {"status": "assumed_available"}

    # Codex credit check
    import shutil

    if shutil.which("codex"):
        try:
            proc = await asyncio.wait_for(
                asyncio.create_subprocess_exec(
                    "codex",
                    "exec",
                    "--full-auto",
                    "--model",
                    "o4-mini",
                    "respond with OK",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                ),
                timeout=15,
            )
            stdout, stderr = await proc.communicate()
            error_output = stderr.decode("utf-8", errors="ignore").lower()

            if any(
                p in error_output
                for p in ("quota", "credit", "rate limit", "429", "unauthorized")
            ):
                results["codex"] = {
                    "status": "quota_exceeded",
                    "error": stderr.decode("utf-8", errors="ignore"),
                }
            elif proc.returncode == 0:
                results["codex"] = {"status": "available"}
            else:
                results["codex"] = {
                    "status": "error",
                    "error": stderr.decode("utf-8", errors="ignore"),
                }
        except (asyncio.TimeoutError, Exception) as e:
            results["codex"] = {"status": "error", "error": str(e)}
    else:
        results["codex"] = {"status": "not_installed"}

    return results


async def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Parallel Agent Orchestrator")
    parser.add_argument("prompt", nargs="?", help="Prompt to send to agents")
    parser.add_argument("--json", action="store_true", help="Output JSON format")
    parser.add_argument("--validate", action="store_true", help="Validate results")
    parser.add_argument("--review", metavar="FILE", help="Code review mode")
    parser.add_argument("--analyze", metavar="FILE", help="Bug/security analysis mode")
    parser.add_argument(
        "--improve", metavar="FILE", help="Improve observation YAML mode"
    )
    parser.add_argument(
        "--check-credits", action="store_true", help="Pre-flight credit check"
    )
    parser.add_argument("--output", metavar="DIR", help="Custom output directory")
    parser.add_argument(
        "--full-output",
        action="store_true",
        default=True,
        help="Include complete outputs",
    )
    parser.add_argument(
        "--no-stream", action="store_true", help="Disable streaming output"
    )
    parser.add_argument(
        "--synthesize",
        action="store_true",
        default=True,
        help="Enable synthesis for low consensus",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=None,
        help="Timeout per agent (seconds). Defaults: review=600, analyze=900, improve=300, prompt=600",
    )
    parser.add_argument("--claude-model", default="sonnet", help="Claude model tier")
    parser.add_argument("--gemini-model", default="flash", help="Gemini model tier")
    parser.add_argument("--cursor-model", default="flash", help="Cursor model tier")
    parser.add_argument("--codex-model", default="auto", help="Codex model tier")
    parser.add_argument("--claude-only", action="store_true", help="Run only Claude")
    parser.add_argument("--gemini-only", action="store_true", help="Run only Gemini")
    parser.add_argument("--cursor-only", action="store_true", help="Run only Cursor")
    parser.add_argument("--codex-only", action="store_true", help="Run only Codex")
    parser.add_argument("--no-claude", action="store_true", help="Disable Claude agent")
    parser.add_argument("--no-cursor", action="store_true", help="Disable Cursor agent")
    parser.add_argument("--no-gemini", action="store_true", help="Disable Gemini agent")
    parser.add_argument("--no-codex", action="store_true", help="Disable Codex agent")
    parser.add_argument(
        "--status",
        action="store_true",
        help="Check agent status (delegates to check_status.sh)",
    )

    args = parser.parse_args()

    # Load configuration
    config = Config()

    # Load service configuration
    services = ServiceConfig()

    # Create logger
    logger = Logger(config)
    logger.set_correlation_id(
        f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{os.getpid()}"
    )

    # Status check mode — delegate to check_status.sh
    if args.status:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        status_script = os.path.join(script_dir, "check_status.sh")
        if os.path.exists(status_script):
            os.execv("/bin/bash", ["/bin/bash", status_script])
        else:
            print(f"Error: {status_script} not found", file=sys.stderr)
            sys.exit(1)

    # Credit check mode
    if args.check_credits:
        print("Checking API credits...")
        results = await check_credits(config, logger)
        print(json.dumps(results, indent=2))
        sys.exit(0)

    # Determine mode and prompt
    mode = "prompt"
    command = None

    if args.review:
        mode = "review"
        prompt = f"Review this file for code quality, security, and best practices: {args.review}"
    elif args.analyze:
        mode = "analyze"
        prompt = f"Analyze this file for bugs and security issues: {args.analyze}"
    elif args.improve:
        mode = "improve"
        prompt = f"Review and improve this observation YAML: {args.improve}"
    elif args.prompt:
        mode = "prompt"
        prompt = args.prompt
    else:
        parser.print_help()
        sys.exit(1)

    # Resolve timeout: explicit flag wins, then mode-based default from config
    if args.timeout is not None:
        timeout = args.timeout
    else:
        mode_timeouts = {
            "review": config.get("timeouts.review", 600),
            "analyze": config.get("timeouts.analyze", 900),
            "improve": config.get("timeouts.improve", 300),
            "prompt": config.get("timeouts.default", 600),
        }
        timeout = mode_timeouts.get(mode, 600)

    # Create rate limiters
    claude_limiter = RateLimiter(**config.get("rate_limits.claude", {}))
    gemini_limiter = RateLimiter(**config.get("rate_limits.gemini", {}))
    cursor_limiter = RateLimiter(**config.get("rate_limits.cursor", {}))
    codex_limiter = RateLimiter(**config.get("rate_limits.codex", {}))

    # Determine streaming mode
    streaming = not args.no_stream and config.get("streaming.enabled", True)

    # --- Agent selection logic ---
    # 1. Start with services.yml enabled state
    enabled = {
        "claude": services.is_enabled("claude"),
        "gemini": services.is_enabled("gemini"),
        "cursor": services.is_enabled("cursor"),
        "codex": services.is_enabled("codex"),
    }

    # 2. Apply --*-only flags (exclusive: if any set, only those run)
    only_flags = {
        "claude": args.claude_only,
        "gemini": args.gemini_only,
        "cursor": args.cursor_only,
        "codex": args.codex_only,
    }
    if any(only_flags.values()):
        for agent_name in enabled:
            enabled[agent_name] = only_flags[agent_name]

    # 3. Apply --no-* overrides (always win)
    if args.no_claude:
        enabled["claude"] = False
    if args.no_gemini:
        enabled["gemini"] = False
    if args.no_cursor:
        enabled["cursor"] = False
    if args.no_codex:
        enabled["codex"] = False

    # Build agents list
    agents = []

    if enabled["claude"]:
        if HAS_ANTHROPIC:
            agents.append(
                ClaudeAgent(
                    args.claude_model,
                    timeout,
                    claude_limiter,
                    config=config,
                    logger=logger,
                    streaming=streaming,
                )
            )
        else:
            print(
                "Warning: anthropic package not installed, skipping Claude agent",
                file=sys.stderr,
            )
            logger.warning("Anthropic package not installed")

    if enabled["gemini"]:
        if HAS_GENAI:
            agents.append(
                GeminiAgent(
                    args.gemini_model,
                    timeout,
                    gemini_limiter,
                    config=config,
                    logger=logger,
                    streaming=streaming,
                )
            )
        else:
            print(
                "Warning: google-generativeai package not installed, skipping Gemini agent",
                file=sys.stderr,
            )
            logger.warning("Google Generative AI package not installed")

    if enabled["cursor"]:
        agents.append(
            CursorAgent(
                args.cursor_model,
                timeout,
                cursor_limiter,
                config=config,
                logger=logger,
                streaming=streaming,
            )
        )

    if enabled["codex"]:
        agents.append(
            CodexAgent(
                args.codex_model,
                timeout,
                codex_limiter,
                config=config,
                logger=logger,
                streaming=streaming,
            )
        )

    # Check minimum agents
    min_warning = services.check_minimum_agents(len(agents))
    if min_warning:
        print(min_warning, file=sys.stderr)
        logger.warning(min_warning)

    if not agents:
        print(
            "Error: No agents available. Check services.yml or install dependencies.",
            file=sys.stderr,
        )
        logger.error("No agents available")
        sys.exit(1)

    # Create orchestrator and execute
    orchestrator = Orchestrator(
        agents,
        config,
        validate=args.validate,
        logger=logger,
        enable_synthesis=args.synthesize,
        streaming=streaming,
    )

    result = await orchestrator.execute(prompt, mode, command)

    # Write output files (with custom directory if provided)
    if args.output or not args.full_output:
        result["output_files"] = await orchestrator._write_output_files(
            result,
            result["timestamp"],
            custom_output_dir=args.output,
            full_output=args.full_output,
        )

    # Print results
    orchestrator.print_results(result, json_output=args.json)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nInterrupted by user", file=sys.stderr)
        sys.exit(130)
