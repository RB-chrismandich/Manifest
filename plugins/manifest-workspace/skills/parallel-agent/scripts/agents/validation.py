"""Two-tier validation engine (Tier 1 blocking / Tier 2 advisory).

Independently importable: only depends on agents.config and the standard library.
"""

import json
import os
import re
from pathlib import Path

from agents.config import Config, Logger


class ValidationEngine:
    """Validates agent outputs against tiered criteria"""

    def __init__(self, config: Config, logger: Logger | None = None):
        self.config = config
        self.logger = logger
        self.criteria = self._load_criteria()

    def _load_criteria(self) -> dict:
        """Load validation criteria from the adjacent immutable JSON file."""
        criteria_path = Path(
            os.environ.get(
                "MANIFEST_VALIDATION_CRITERIA",
                Path(__file__).resolve().parents[2] / "config/validation_criteria.json",
            )
        )
        if not criteria_path.exists():
            if self.logger:
                self.logger.warning(
                    f"Validation criteria file not found: {criteria_path}"
                )
            return {}

        try:
            with open(criteria_path, encoding="utf-8") as criteria_file:
                loaded = json.load(criteria_file)
        except (OSError, json.JSONDecodeError) as error:
            if self.logger:
                self.logger.warning(f"Validation criteria unavailable: {error}")
            return {}
        return loaded if isinstance(loaded, dict) else {}

    def validate(
        self,
        agent_results: dict,
        consensus: dict,
        mode: str,
        command: str | None = None,
    ) -> dict:
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
        self, agent_results: dict, consensus: dict, overrides: dict
    ) -> dict:
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

    def _check_security(self, agent_results: dict, security_criteria: dict) -> dict:
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

    def _check_error_handling(self, agent_results: dict, error_criteria: dict) -> dict:
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
        self, agent_results: dict, breaking_criteria: dict
    ) -> dict:
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

    def _validate_tier2(self, agent_results: dict, overrides: dict) -> dict:
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

    def _check_bugs(self, agent_results: dict, bug_criteria: dict) -> dict:
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

    def _check_performance(self, agent_results: dict, perf_criteria: dict) -> dict:
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

    def _check_maintainability(self, agent_results: dict, maint_criteria: dict) -> dict:
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

    def _check_test_coverage(self, agent_results: dict, test_criteria: dict) -> dict:
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
        self, tier1_result: dict, tier2_result: dict, overrides: dict
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
