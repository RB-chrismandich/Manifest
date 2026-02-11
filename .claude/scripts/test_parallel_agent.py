#!/usr/bin/env python3
"""
Unit tests for parallel_agent.py Phase 3 features

Run with: pytest test_parallel_agent.py -v
Or: python3 test_parallel_agent.py
"""

import asyncio
import sys
from pathlib import Path

try:
    import pytest
    HAS_PYTEST = True
except ImportError:
    HAS_PYTEST = False
    # Mock pytest.mark.asyncio for non-pytest runs
    class MockPytest:
        class mark:
            @staticmethod
            def asyncio(func):
                return func
    pytest = MockPytest()

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from parallel_agent import (
    Config, Logger, ValidationEngine, SynthesisEngine,
    RateLimiter, BaseAgent
)


class TestLogger:
    """Test Logger class"""

    def test_logger_creation(self):
        """Test logger can be created"""
        config = Config()
        logger = Logger(config)
        assert logger.logger is not None
        assert logger.correlation_id is None

    def test_correlation_id(self):
        """Test correlation ID can be set"""
        config = Config()
        logger = Logger(config)
        logger.set_correlation_id("test-123")
        assert logger.correlation_id == "test-123"

    def test_logging_methods(self):
        """Test logging methods don't crash"""
        config = Config()
        logger = Logger(config)
        logger.set_correlation_id("test")

        # These should not raise exceptions
        logger.debug("Debug message")
        logger.info("Info message")
        logger.warning("Warning message")
        logger.error("Error message")


class TestValidationEngine:
    """Test ValidationEngine class"""

    def test_validator_creation(self):
        """Test validator can be created"""
        config = Config()
        validator = ValidationEngine(config)
        assert validator.config is not None

    def test_tier1_security_check(self):
        """Test Tier 1 security validation"""
        config = Config()
        validator = ValidationEngine(config)

        # Mock agent results with potential security issue
        results = {
            'claude': {
                'status': 'complete',
                'output': 'Found hardcoded API_KEY = "secret123" in the code'
            }
        }
        consensus = {'consensus_score': 85}

        tier1_result = validator._check_security(results, {})
        # Should detect hardcoded secret
        assert not tier1_result['passed']
        assert len(tier1_result['issues']) > 0

    def test_tier1_no_security_issues(self):
        """Test Tier 1 with clean code"""
        config = Config()
        validator = ValidationEngine(config)

        results = {
            'claude': {
                'status': 'complete',
                'output': 'Code looks good, using environment variables for secrets'
            }
        }
        consensus = {'consensus_score': 85}

        tier1_result = validator._check_security(results, {})
        # Should pass
        assert tier1_result['passed']
        assert len(tier1_result['issues']) == 0

    def test_tier2_bug_detection(self):
        """Test Tier 2 bug detection"""
        config = Config()
        validator = ValidationEngine(config)

        results = {
            'claude': {
                'status': 'complete',
                'output': 'Warning: potential null reference issue detected'
            }
        }

        tier2_result = validator._check_bugs(results, {})
        # Should have concerns
        assert tier2_result['score'] < 1.0
        assert len(tier2_result['concerns']) > 0

    def test_verdict_computation(self):
        """Test verdict computation logic"""
        config = Config()
        validator = ValidationEngine(config)

        # APPROVED: tier1 passed, tier2 >= 0.60
        tier1 = {'passed': True, 'score': 1.0}
        tier2 = {'score': 0.75}
        verdict = validator._compute_verdict(tier1, tier2, {})
        assert verdict == 'APPROVED'

        # NEEDS_REVIEW: tier1 passed, tier2 < 0.60
        tier2 = {'score': 0.55}
        verdict = validator._compute_verdict(tier1, tier2, {})
        assert verdict == 'NEEDS_REVIEW'

        # BLOCKED: tier1 failed
        tier1 = {'passed': False, 'score': 0.0}
        tier2 = {'score': 0.75}
        verdict = validator._compute_verdict(tier1, tier2, {})
        assert verdict == 'BLOCKED'


class TestSynthesisEngine:
    """Test SynthesisEngine class"""

    def test_synthesis_creation(self):
        """Test synthesis engine can be created"""
        config = Config()
        synthesizer = SynthesisEngine(config)
        assert synthesizer.config is not None

    def test_synthesis_not_needed_high_consensus(self):
        """Test synthesis skipped when consensus is high"""
        config = Config()
        synthesizer = SynthesisEngine(config)

        results = {
            'gemini': {'status': 'complete', 'output': 'Use approach A'},
            'claude': {'status': 'complete', 'output': 'Use approach A'}
        }
        consensus = {'consensus_score': 85}  # High consensus

        # Should return None (synthesis not needed)
        result = asyncio.run(
            synthesizer.synthesize("Test task", results, consensus)
        )
        assert result is None

    def test_template_loading(self):
        """Test synthesis template can be loaded"""
        config = Config()
        synthesizer = SynthesisEngine(config)

        # Template should be loaded or empty string
        assert isinstance(synthesizer.synthesis_template, str)


class TestRateLimiter:
    """Test RateLimiter class"""

    def test_rate_limiter_creation(self):
        """Test rate limiter can be created"""
        limiter = RateLimiter(requests_per_minute=60, burst_size=5)
        assert limiter.rpm == 60
        assert limiter.burst_size == 5
        assert limiter.tokens == 5

    @pytest.mark.asyncio
    async def test_rate_limiter_acquire(self):
        """Test rate limiter acquire"""
        limiter = RateLimiter(requests_per_minute=60, burst_size=5)

        # Should acquire immediately
        await limiter.acquire()
        assert limiter.tokens == 4

        # Acquire all tokens
        for _ in range(4):
            await limiter.acquire()

        assert limiter.tokens == 0


class TestConfig:
    """Test Config class"""

    def test_config_creation(self):
        """Test config can be created"""
        config = Config()
        assert config.config is not None

    def test_config_get(self):
        """Test config get with dot notation"""
        config = Config()

        # Get nested value
        value = config.get('rate_limits.claude.requests_per_minute')
        assert value is not None

        # Get with default
        value = config.get('nonexistent.key', 'default')
        assert value == 'default'


def run_tests():
    """Run tests without pytest"""
    print("Running basic tests...\n")

    # Test Logger
    print("Testing Logger...")
    test = TestLogger()
    test.test_logger_creation()
    test.test_correlation_id()
    test.test_logging_methods()
    print("✓ Logger tests passed\n")

    # Test ValidationEngine
    print("Testing ValidationEngine...")
    test = TestValidationEngine()
    test.test_validator_creation()
    test.test_tier1_security_check()
    test.test_tier1_no_security_issues()
    test.test_tier2_bug_detection()
    test.test_verdict_computation()
    print("✓ ValidationEngine tests passed\n")

    # Test SynthesisEngine
    print("Testing SynthesisEngine...")
    test = TestSynthesisEngine()
    test.test_synthesis_creation()
    test.test_synthesis_not_needed_high_consensus()
    test.test_template_loading()
    print("✓ SynthesisEngine tests passed\n")

    # Test RateLimiter
    print("Testing RateLimiter...")
    test = TestRateLimiter()
    test.test_rate_limiter_creation()
    asyncio.run(test.test_rate_limiter_acquire())
    print("✓ RateLimiter tests passed\n")

    # Test Config
    print("Testing Config...")
    test = TestConfig()
    test.test_config_creation()
    test.test_config_get()
    print("✓ Config tests passed\n")

    print("All tests passed! ✓")


if __name__ == "__main__":
    # Run without pytest if available, otherwise use simple runner
    try:
        import pytest
        sys.exit(pytest.main([__file__, "-v"]))
    except ImportError:
        run_tests()
